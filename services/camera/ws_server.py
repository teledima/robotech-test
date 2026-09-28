from websockets import ConnectionClosed
from websockets.asyncio.server import serve


class WSServer:
    def __init__(self, host, port):
        self._host = host
        self._port = port
        self._messages = list()
        self._checker_socket = None

    async def echo(self, websocket):
        try:
            print('[ws] got connection from ', websocket.remote_address)
            async for message in websocket:
                if message == 'is_checker':
                    print('[ws] checker_socket available')
                    self._checker_socket = websocket
                else:
                    self._messages.append(message)

            if self._checker_socket is not None:
                while self._messages:
                    await self._checker_socket.send(self._messages.pop())
                
        except ConnectionClosed:
            print(f'[ws] connection {websocket.remote_address} closed')
            return

    async def run(self):
        server = await serve(self.echo, self._host, self._port)
        await server.serve_forever()
