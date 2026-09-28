import os

from dotenv import load_dotenv
from worker.worker import Worker


def main():
  load_dotenv()
  TCP_HOST = os.getenv("TCP_HOST", "127.0.0.1")
  TCP_PORT = int(os.getenv("TCP_PORT", 4096))

  worker = Worker(tcp_host=TCP_HOST, tcp_port=TCP_PORT)
  worker.run()

if __name__ == "__main__":
  main()
