import json
import socket
import threading
from collections import deque

PORT = 5555


class NetClient:
    """Tiny JSON-lines TCP client. Messages are read in a background thread."""

    def __init__(self):
        self.sock = None
        self.connected = False
        self.inbox = deque()
        self.inbox_lock = threading.Lock()
        self.send_lock = threading.Lock()

    def connect(self, host, port=PORT, timeout=3):
        self.close()
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = sock
        self.connected = True
        threading.Thread(
            target=self._reader, args=(sock,), daemon=True
        ).start()

    def _reader(self, sock):
        buf = b""
        try:
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except ValueError:
                        continue
                    with self.inbox_lock:
                        self.inbox.append(msg)
        except OSError:
            pass

        # Only report a disconnect if this is still the active socket
        # (close() sets self.sock to None first).
        if sock is self.sock:
            self.connected = False
            with self.inbox_lock:
                self.inbox.append({"t": "disconnected"})

    def send(self, msg):
        if not self.connected or self.sock is None:
            return False
        data = (json.dumps(msg) + "\n").encode("utf-8")
        try:
            with self.send_lock:
                self.sock.sendall(data)
            return True
        except OSError:
            self.connected = False
            return False

    def poll(self):
        """Return and clear all received messages."""
        with self.inbox_lock:
            msgs = list(self.inbox)
            self.inbox.clear()
        return msgs

    def unget(self, msgs):
        """Put unprocessed messages back at the front of the queue."""
        with self.inbox_lock:
            self.inbox.extendleft(reversed(msgs))

    def close(self):
        sock, self.sock = self.sock, None
        self.connected = False
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass