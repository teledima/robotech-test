import mimetypes
import os
import socket
import time
from pathlib import Path
from random import Random

import ujson
from minio.api import ObjectWriteResult
from pika import BaseConnection
from PIL import Image
from websockets.sync.client import connect

from .api_client import ApiClient
from .minio_client import MinioClient


class TcpClient:
    def __init__(
            self,
            server_host: str,
            server_port: int,
            image_folder: str,
            ws_host: str,
            ws_port: int,
            minio: MinioClient,
            rabbitmq: BaseConnection,
            api_client: ApiClient,
        ):
        self._server_host = server_host
        self._server_port = server_port
        self._image_folder = image_folder
        self._ws_host = ws_host
        self._ws_port = ws_port
        self._minio = minio
        self._rabbitmq = rabbitmq
        self._api_client = api_client

        self._images = Path(image_folder)
        self._rnd = Random(os.urandom(100))
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        print(f'[tcp][{self.addr}] close connection')
        self._sock.close()

    @property
    def addr(self):
        host, port = self._sock.getsockname()
        return f'{host}:{port}'

    def _open_image(self, path: Path):
        with open(path, mode='rb') as file:
            while buff := file.read(1024):
                yield buff

    def _save_to_s3(self, path: Path) -> ObjectWriteResult:
        if not path.is_file():
            raise ValueError('path not file', str(path))

        content_type, _ = mimetypes.guess_type(str(path))
        if not content_type:
            content_type = 'application/octet-stream'

        return self._minio.fput_object(
            bucket_name='images',
            object_name=path.name,
            file_path=str(path),
            content_type=content_type,
        )

    def _save_metadata(self, url: str, path: Path):
        with Image.open(path) as img:
            self._api_client.add(url, img.size[0], img.size[1])

    def _save_to_queue(self, s3_url):
        payload = {
            'url': s3_url,
        }

        ch = self._rabbitmq.channel()
        ch.basic_publish(
            'inference.in',
            'inference.in',
            ujson.dumps(payload),
        )
        ch.close()

    def _send_message_to_ws(self, s3_url):
        with connect(f'ws://{self._ws_host}:{self._ws_port}') as websocket:
            payload = {
                'url': s3_url,
            }
            websocket.send(ujson.dumps(payload))

    def start(self):
        try:
            self._sock.connect((self._server_host, self._server_port))
        except ConnectionRefusedError:
            print(f'[tcp][{self.addr}] error while connecting to {(self._server_host, self._server_port)}\n'
                  f'[tcp][{self.addr}] reattempting connection in 5 seconds')
            time.sleep(5)
            return

        self._sock.settimeout(10)

        buff = ''
        COMMAND = '[s][save_image][e]'
        while True:
            data = self._sock.recv(16)

            buff += data.decode('utf-8')

            idx = buff.find(COMMAND)
            if idx > -1:
                print(f'[tcp][{self.addr}] make photo')
                self._sock.sendall('ok'.encode('utf-8'))
                buff = buff[idx + len(COMMAND):]
                img_path = self._rnd.choice([img for img in self._images.iterdir()])

                try:
                    out = self._save_to_s3(img_path)
                except ValueError as e:
                    if e.args[0] == 'path not file':
                        print('path not file:', e.args[1])
                        break
                    raise

                url = self._minio.s3_public_url(out.bucket_name, out.object_name)
                self._save_metadata(url, img_path)
                self._save_to_queue(url)
                self._send_message_to_ws(url)
