import asyncio
import os
import threading
import time
from pathlib import Path
from typing import TypedDict

import dotenv
import pika

from .api_client import ApiClient
from .minio_client import MinioClient
from .tcp_client import TcpClient
from .ws_server import WSServer


class Config(TypedDict):
    ws_host: str
    ws_port: int
    tcp_host: str
    tcp_port: int
    minio_endpoint: str
    rabbitmq_host: str
    rabbitmq_port: int
    api_host: str
    api_port: int
    image_folder: str


def ws_server_thread():
    ws_host = os.getenv("WS_HOST", "127.0.0.1")
    ws_port = int(os.getenv("WS_PORT", 1234))
    ws_server = WSServer(ws_host, ws_port)

    return threading.Thread(target=asyncio.run, args=[ws_server.run()])


def tcp_client_target(*args):
    while True:
        with TcpClient(*args) as client:
            try:
                client.start()
            except ConnectionRefusedError:
                print(f'[tcp][{client.addr}] error while connecting to {client._server_host}:{client._server_port}\n'
                      f'[tcp][{client.addr}] reattempting connection in 5 seconds')
                time.sleep(5)
            except TimeoutError:
                print(f'[tcp][{client.addr}] timed out')


def load_config():
    dotenv.load_dotenv()

    cfg = Config(
        ws_host=os.getenv("WS_HOST", "127.0.0.1"),
        ws_port=int(os.getenv("WS_PORT", 1234)),
        tcp_host=os.environ.get('TCP_HOST', 'localhost'),
        tcp_port=os.environ.get('TCP_PORT', 4096),
        minio_endpoint=os.environ.get('MINIO_ENDPOINT', 'localhost:9000'),
        rabbitmq_host=os.environ.get('RABBITMQ_HOST', 'localhost'),
        rabbitmq_port=os.environ.get('RABBITMQ_PORT', 5672),
        api_host=os.environ.get('API_HOST', 'localhost'),
        api_port=os.environ.get('API_PORT', 8000),
        image_folder=os.environ.get('IMAGE_FOLDER', 'data/images'),
    )

    if not Path(cfg['image_folder']).exists():
        print(f'images path {cfg['image_folder']} doesnt exist')
        raise ValueError

    return cfg


if __name__ == "__main__":
    config = load_config()

    ws_server = WSServer(config['ws_host'], config['ws_port'])
    ws_thread = threading.Thread(target=asyncio.run, args=[ws_server.run()], daemon=True)

    minio = MinioClient(
        endpoint=config['minio_endpoint'],
        secure=False,
    )
    rabbitmq = pika.BlockingConnection(
        pika.ConnectionParameters(
            config['rabbitmq_host'],
            config['rabbitmq_port'],
            connection_attempts=5,
            retry_delay=5,
        )
    )
    api_client = ApiClient(host=config['api_host'], port=config['api_port'])

    tcp_thread = threading.Thread(
        target=tcp_client_target,
        args=[
            config['tcp_host'],
            config['tcp_port'],
            config['image_folder'],
            config['ws_host'],
            config['ws_port'],
            minio,
            rabbitmq,
            api_client,
        ],
        daemon=True,
    )

    ws_thread.start()
    tcp_thread.start()

    ws_thread.join()
    tcp_thread.join()
