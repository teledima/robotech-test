from threading import Thread

from tcp.server import TcpServer


class Worker:
  def __init__(self, tcp_host: str, tcp_port: int) -> None:
    self._tcp_server = TcpServer(tcp_host, tcp_port)

  def run(self):
    tcp_thread = Thread(target=self._tcp_server.run, daemon=True)
    tcp_thread.start()
    tcp_thread.join()
