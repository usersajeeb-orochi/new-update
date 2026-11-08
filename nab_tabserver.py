# nab_tabserver.py — tiny WebSocket listener for the NAB Tab Reporter browser extension (ws://127.0.0.1:6789).
# Pure standard library (no `websockets` package needed). Same protocol as before:
#   extension -> {"type": "tab_info", "url": "...", "title": "..."}
import base64
import hashlib
import json
import logging
import socket
import struct
import threading
import time

PORT = 6789
_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class TabServer:
    def __init__(self, port=PORT):
        self.port = port
        self.tab_info = {"url": "", "title": "", "ts": 0.0}
        self.status = "not started"
        self.clients = 0
        self.last_msg = 0.0
        self._sock = None

    def get_tab_info(self, max_age=45.0):
        ti = self.tab_info
        if ti.get("url") and time.time() - ti.get("ts", 0) <= max_age:
            return dict(ti)
        return None

    def info(self):
        return {"status": self.status, "clients": self.clients, "port": self.port,
                "last_msg_age": round(time.time() - self.last_msg, 1) if self.last_msg else None,
                "url": self.tab_info.get("url", "")[:90]}

    # ---- lifecycle
    def start(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", self.port))
            s.listen(8)
            self._sock = s
            self.status = f"listening on 127.0.0.1:{self.port}"
            threading.Thread(target=self._accept, daemon=True, name="NAB-Tabs").start()
        except OSError as e:
            self.status = f"cannot listen on port {self.port}: {e}"
            logging.error("TabServer: " + self.status)
        return self

    def _accept(self):
        while True:
            try:
                c, _ = self._sock.accept()
                threading.Thread(target=self._client, args=(c,), daemon=True).start()
            except Exception as e:
                logging.error(f"TabServer accept: {e}")
                time.sleep(1)

    # ---- one connection
    def _client(self, c):
        try:
            c.settimeout(90)
            buf = b""
            while b"\r\n\r\n" not in buf:
                d = c.recv(4096)
                if not d:
                    return
                buf += d
                if len(buf) > 16384:
                    return
            head, rest = buf.split(b"\r\n\r\n", 1)
            hdr = {}
            for line in head.decode("latin-1").split("\r\n")[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    hdr[k.strip().lower()] = v.strip()
            origin = hdr.get("origin", "")
            key = hdr.get("sec-websocket-key")
            if not key or (origin and not origin.startswith(("chrome-extension://", "moz-extension://", "edge-extension://"))):
                c.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
                return
            acc = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
            c.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                       f"Sec-WebSocket-Accept: {acc}\r\n\r\n").encode())
            self.clients += 1
            try:
                self._frames(c, rest)
            finally:
                self.clients = max(0, self.clients - 1)
        except Exception:
            pass
        finally:
            try:
                c.close()
            except Exception:
                pass

    def _frames(self, c, buf):
        def need(n):
            nonlocal buf
            while len(buf) < n:
                d = c.recv(65536)
                if not d:
                    raise EOFError
                buf += d
            out, buf = buf[:n], buf[n:]
            return out
        msg = b""
        while True:
            b1, b2 = need(2)
            fin, op = b1 & 0x80, b1 & 0x0F
            ln, masked = b2 & 0x7F, b2 & 0x80
            if ln == 126:
                ln = struct.unpack(">H", need(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", need(8))[0]
            if ln > 1_000_000:
                return
            mask = need(4) if masked else b""
            data = need(ln) if ln else b""
            if masked:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 8:                       # close
                return
            if op == 9:                       # ping -> pong
                c.sendall(bytes([0x8A, len(data)]) + data if len(data) < 126 else b"")
                continue
            if op in (1, 0):                  # text / continuation
                msg += data
                if fin:
                    self._inbound(msg)
                    msg = b""

    def _inbound(self, raw):
        try:
            m = json.loads(raw.decode("utf-8", errors="ignore"))
        except Exception:
            return
        if isinstance(m, dict) and m.get("type") == "tab_info":
            url = str(m.get("url", ""))[:2000]
            if url.startswith(("http://", "https://")):
                self.tab_info = {"url": url, "title": str(m.get("title", ""))[:300], "ts": time.time()}
                self.last_msg = time.time()
