import urllib3


class ApiClient:
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._client =  urllib3.PoolManager()

    def add(self, url: str, width: int, height: int) -> urllib3.response.HTTPResponse:
        return self._client.request(
            'POST',
            f'http://{self._host}:{self._port}/images/',
            json={
                'url': url,
                'width': width,
                'height': height,
            },
        )
