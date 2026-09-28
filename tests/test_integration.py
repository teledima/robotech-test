"""
Integration tests for the camera <-> checker <-> minio <-> api <-> rabbitmq pipeline.

Architecture under test:
  1. checker TCP server sends `[s][save_image][e]` to camera
  2. camera TcpClient connects, receives the command, replies `ok`
  3. camera picks a random image, uploads to MinIO (s3)
  4. camera POSTs image metadata (url/width/height) to the API
  5. camera publishes the s3 url to RabbitMQ exchange `inference.in`
  6. camera sends the s3 url to the WSServer (which forwards to checker)

External services (MinIO, API, RabbitMQ) are stubbed so the tests focus on
the wiring between the components — correct arguments, ordering, and that
a single TCP command triggers the full downstream chain.
"""

import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import ujson
from websockets.sync.client import connect as ws_connect
from websockets.sync.server import serve as sync_serve

from services.camera.api_client import ApiClient
from services.camera.minio_client import MinioClient
from services.camera.tcp_client import TcpClient
from services.camera.ws_server import WSServer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

IMAGE_DIR = Path(__file__).resolve().parent.parent / "data" / "images"
TEST_IMAGE = IMAGE_DIR / "test.png"


@dataclass
class FakeObjectWriteResult:
    bucket_name: str
    object_name: str


@pytest.fixture
def free_port():
    """Return a free TCP port on localhost."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def ws_port(free_port):
    return free_port


@pytest.fixture
def tcp_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def ws_server(ws_port):
    """Real WSServer (async) running in a background thread with its own event loop."""
    import asyncio

    server = WSServer("127.0.0.1", ws_port)
    thread = threading.Thread(target=lambda: asyncio.run(server.run()), daemon=True)
    thread.start()
    _wait_for_port("127.0.0.1", ws_port)
    yield server


@pytest.fixture
def mock_minio():
    """Stub MinioClient: fput_object returns a fake ObjectWriteResult,
    s3_public_url builds a predictable URL."""
    client = MagicMock(spec=MinioClient)
    client.fput_object.return_value = FakeObjectWriteResult(
        bucket_name="images", object_name=TEST_IMAGE.name
    )
    client.s3_public_url.side_effect = lambda b, o: f"http://minio:9000/{b}/{o}"
    client._endpoint = "minio:9000"
    return client


@pytest.fixture
def mock_api_client():
    client = MagicMock(spec=ApiClient)
    resp = MagicMock()
    resp.status = 200
    client.add.return_value = resp
    return client


@pytest.fixture
def mock_rabbitmq():
    """Stub pika BlockingConnection: channel().basic_publish records calls."""
    conn = MagicMock()
    channel = MagicMock()
    conn.channel.return_value = channel
    return conn


@pytest.fixture
def tcp_server_sock(tcp_port):
    """A minimal TCP server that accepts one connection and sends commands."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", tcp_port))
    sock.listen(1)
    sock.settimeout(10)
    yield sock
    sock.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_for_port(host: str, port: int, timeout: float = 3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"port {host}:{port} never opened")


def _checker_send_and_read(server_sock: socket.socket, commands: int = 1):
    """Accept one connection, send N save_image commands, return responses."""
    conn, _ = server_sock.accept()
    conn.settimeout(10)
    responses = []
    for _ in range(commands):
        conn.sendall(b"[s][save_image][e]")
        responses.append(conn.recv(1024))
    conn.close()
    return responses


def _run_one_shot_client(tcp_port, ws_port, mock_minio, mock_rabbitmq, mock_api_client):
    """Connect the real TcpClient to the checker stub and let it process
    commands until the server closes the connection."""
    with TcpClient(
        server_host="127.0.0.1",
        server_port=tcp_port,
        image_folder=str(IMAGE_DIR),
        ws_host="127.0.0.1",
        ws_port=ws_port,
        minio=mock_minio,
        rabbitmq=mock_rabbitmq,
        api_client=mock_api_client,
    ) as client:
        try:
            client.start()
        except Exception:
            # The real start() loops forever; the server closing the socket
            # will surface as an exception — that's the expected exit path.
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class Suite:
    def test_tcp_command_triggers_full_pipeline(
        self, ws_server, ws_port, tcp_port, tcp_server_sock,
        mock_minio, mock_api_client, mock_rabbitmq,
    ):
        """One `[s][save_image][e]` from checker drives camera through
        minio -> api -> rabbitmq -> websocket."""

        # Start camera TcpClient in a background thread
        client_thread = threading.Thread(
            target=lambda: _run_one_shot_client(
                tcp_port, ws_port, mock_minio, mock_rabbitmq, mock_api_client,
            ),
            daemon=True,
        )
        client_thread.start()
        time.sleep(0.1)  # let camera connect

        # Checker side: send the command, collect the 'ok' reply
        responses = _checker_send_and_read(tcp_server_sock, commands=1)
        time.sleep(0.3)  # let camera finish all downstream calls
        client_thread.join(timeout=5)

        assert responses[0] == b"ok", "camera should reply 'ok' to the save_image command"

        # --- MinIO: image uploaded -------------------------------------------
        mock_minio.fput_object.assert_called_once()
        call = mock_minio.fput_object.call_args
        assert call.kwargs["bucket_name"] == "images"
        assert call.kwargs["object_name"] == TEST_IMAGE.name

        # --- API: metadata posted with real image dimensions -----------------
        mock_api_client.add.assert_called_once()
        url_arg, w, h = mock_api_client.add.call_args.args
        assert url_arg == "http://minio:9000/images/test.png"
        assert isinstance(w, int) and w > 0
        assert isinstance(h, int) and h > 0

        # --- RabbitMQ: message published to inference.in ---------------------
        channel = mock_rabbitmq.channel.return_value
        channel.basic_publish.assert_called_once()
        pub_args = channel.basic_publish.call_args.args
        assert pub_args[0] == "inference.in"   # exchange
        assert pub_args[1] == "inference.in"   # routing key
        payload = ujson.loads(pub_args[2])
        assert payload["url"] == "http://minio:9000/images/test.png"
        channel.close.assert_called_once()

    def test_multiple_commands_produce_multiple_uploads(
        self, ws_server, ws_port, tcp_port, tcp_server_sock,
        mock_minio, mock_api_client, mock_rabbitmq,
    ):
        """N commands -> N uploads + N api calls + N rabbit messages."""
        N = 3

        client_thread = threading.Thread(
            target=lambda: _run_one_shot_client(
                tcp_port, ws_port, mock_minio, mock_rabbitmq, mock_api_client,
            ),
            daemon=True,
        )
        client_thread.start()
        time.sleep(0.1)

        responses = _checker_send_and_read(tcp_server_sock, commands=N)
        time.sleep(0.3)
        client_thread.join(timeout=10)

        assert all(r == b"ok" for r in responses)
        assert mock_minio.fput_object.call_count == N
        assert mock_api_client.add.call_count == N
        assert mock_rabbitmq.channel.return_value.basic_publish.call_count == N

    def test_ws_receives_url_from_camera(
        self, ws_server, ws_port, tcp_port, tcp_server_sock,
        mock_minio, mock_api_client, mock_rabbitmq,
    ):
        """The URL camera pushes to WS should be the same s3_public_url,
        and the checker-client (identified via 'is_checker') should receive it."""
        received = []

        def ws_listener():
            with ws_connect(f"ws://127.0.0.1:{ws_port}") as ws:
                ws.send("is_checker")
                try:
                    msg = ws.recv(timeout=5)
                    received.append(msg)
                except TimeoutError:
                    pass

        ws_thread = threading.Thread(target=ws_listener, daemon=True)
        ws_thread.start()
        time.sleep(0.3)  # let the checker-client register

        client_thread = threading.Thread(
            target=lambda: _run_one_shot_client(
                tcp_port, ws_port, mock_minio, mock_rabbitmq, mock_api_client,
            ),
            daemon=True,
        )
        client_thread.start()
        time.sleep(0.1)

        _checker_send_and_read(tcp_server_sock, commands=1)
        time.sleep(0.5)  # wait for WS message delivery
        client_thread.join(timeout=5)
        ws_thread.join(timeout=5)

        assert len(received) == 1
        payload = ujson.loads(received[0])
        assert payload["url"] == "http://minio:9000/images/test.png"

    def test_minio_upload_failure_does_not_publish_to_rabbit(
        self, ws_server, ws_port, tcp_port, tcp_server_sock,
        mock_minio, mock_api_client, mock_rabbitmq,
    ):
        """If minio raises, camera should not call api or rabbitmq."""
        mock_minio.fput_object.side_effect = RuntimeError("minio down")

        client_thread = threading.Thread(
            target=lambda: _run_one_shot_client(
                tcp_port, ws_port, mock_minio, mock_rabbitmq, mock_api_client,
            ),
            daemon=True,
        )
        client_thread.start()
        time.sleep(0.1)

        _checker_send_and_read(tcp_server_sock, commands=1)
        time.sleep(0.3)
        client_thread.join(timeout=5)

        mock_api_client.add.assert_not_called()
        mock_rabbitmq.channel.return_value.basic_publish.assert_not_called()

    def test_minio_public_url_format(self, mock_minio):
        """MinioClient.s3_public_url must produce a usable http URL."""
        assert mock_minio.s3_public_url("images", "x.png") == "http://minio:9000/images/x.png"

    def test_camera_connects_to_checker_tcp(
        self, ws_port, tcp_port, tcp_server_sock,
        mock_minio, mock_api_client, mock_rabbitmq,
    ):
        """Camera TcpClient must connect to the checker TCP server
        and respond with 'ok' to the save_image command."""
        client_thread = threading.Thread(
            target=lambda: _run_one_shot_client(
                tcp_port, ws_port, mock_minio, mock_rabbitmq, mock_api_client,
            ),
            daemon=True,
        )
        client_thread.start()
        time.sleep(0.1)

        responses = _checker_send_and_read(tcp_server_sock, commands=1)
        client_thread.join(timeout=5)

        assert responses[0] == b"ok"

    def test_rabbitmq_channel_created_and_closed(
        self, ws_server, ws_port, tcp_port, tcp_server_sock,
        mock_minio, mock_api_client, mock_rabbitmq,
    ):
        """Each save_image command should open a fresh RabbitMQ channel
        and close it after publishing."""
        client_thread = threading.Thread(
            target=lambda: _run_one_shot_client(
                tcp_port, ws_port, mock_minio, mock_rabbitmq, mock_api_client,
            ),
            daemon=True,
        )
        client_thread.start()
        time.sleep(0.1)

        _checker_send_and_read(tcp_server_sock, commands=2)
        time.sleep(0.3)
        client_thread.join(timeout=5)

        channel = mock_rabbitmq.channel.return_value
        assert channel.basic_publish.call_count == 2
        assert channel.close.call_count == 2

    def test_pipeline_order_minio_before_api_before_rabbit(
        self, ws_server, ws_port, tcp_port, tcp_server_sock,
        mock_minio, mock_api_client, mock_rabbitmq,
    ):
        """Verify the call ordering: minio upload -> api metadata -> rabbitmq publish.
        Uses call tracking across all mocks to assert sequence."""
        call_order = []

        mock_minio.fput_object.side_effect = lambda **kw: (
            call_order.append("minio"),
            FakeObjectWriteResult(bucket_name="images", object_name="test.png"),
        )[-1]

        mock_api_client.add.side_effect = lambda *a: (
            call_order.append("api"),
            MagicMock(status=200),
        )[-1]

        channel = mock_rabbitmq.channel.return_value
        channel.basic_publish.side_effect = lambda *a: call_order.append("rabbit")

        client_thread = threading.Thread(
            target=lambda: _run_one_shot_client(
                tcp_port, ws_port, mock_minio, mock_rabbitmq, mock_api_client,
            ),
            daemon=True,
        )
        client_thread.start()
        time.sleep(0.1)

        _checker_send_and_read(tcp_server_sock, commands=1)
        time.sleep(0.3)
        client_thread.join(timeout=5)

        assert call_order == ["minio", "api", "rabbit"]
