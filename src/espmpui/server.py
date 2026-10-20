"""
Asynchronous HTTP and WebSocket RFC 6455 Server for MicroPython and Python 3.
Engineered for zero-copy streaming, non-blocking cooperative multitasking, and fault isolation.
"""

import sys

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    import uhashlib as hashlib
except ImportError:
    import hashlib

try:
    import ubinascii as binascii
except ImportError:
    import binascii

from espmpui.assets import get_asset_payload

def print_exception(exc):
    """Prints exception traceback on both MicroPython and standard Python."""
    if hasattr(sys, "print_exception"):
        sys.print_exception(exc)
    else:
        import traceback
        traceback.print_exception(exc)

# WebSocket RFC 6455 Opcodes
WS_OP_CONTINUE = 0x00
WS_OP_TEXT     = 0x01
WS_OP_BINARY   = 0x02
WS_OP_CLOSE    = 0x08
WS_OP_PING     = 0x09
WS_OP_PONG     = 0x0A

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def calculate_accept_key(sec_key: str) -> str:
    """Calculates Sec-WebSocket-Accept header per RFC 6455."""
    raw = (sec_key.strip() + WS_GUID).encode("ascii")
    sha1 = hashlib.sha1(raw).digest()
    accept = binascii.b2a_base64(sha1).decode("ascii").strip()
    return accept


def encode_ws_frame(payload, opcode: int = WS_OP_TEXT) -> bytes:
    """Encodes an unmasked server-to-client WebSocket frame."""
    if isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        data = payload

    length = len(data)
    first_byte = 0x80 | (opcode & 0x0F)

    if length < 126:
        header = bytes([first_byte, length])
    elif length <= 65535:
        header = bytes([first_byte, 126, (length >> 8) & 0xFF, length & 0xFF])
    else:
        # 64-bit length
        header = bytes([
            first_byte, 127,
            (length >> 56) & 0xFF, (length >> 48) & 0xFF,
            (length >> 40) & 0xFF, (length >> 32) & 0xFF,
            (length >> 24) & 0xFF, (length >> 16) & 0xFF,
            (length >> 8) & 0xFF, length & 0xFF
        ])

    return header + data


def decode_ws_frame(buf: bytes):
    """
    Decodes a client-to-server WebSocket frame.
    Returns (opcode, payload_bytes, total_bytes_consumed).
    If buffer is incomplete, returns (None, None, 0).
    """
    buf_len = len(buf)
    if buf_len < 2:
        return None, None, 0

    first_byte = buf[0]
    second_byte = buf[1]

    opcode = first_byte & 0x0F
    is_masked = bool(second_byte & 0x80)
    payload_len = second_byte & 0x7F

    offset = 2
    if payload_len == 126:
        if buf_len < 4:
            return None, None, 0
        payload_len = (buf[2] << 8) | buf[3]
        offset = 4
    elif payload_len == 127:
        if buf_len < 10:
            return None, None, 0
        payload_len = 0
        for i in range(8):
            payload_len = (payload_len << 8) | buf[2 + i]
        offset = 10

    mask_len = 4 if is_masked else 0
    total_needed = offset + mask_len + payload_len

    if buf_len < total_needed:
        return None, None, 0

    if is_masked:
        mask = buf[offset:offset + 4]
        offset += 4
        raw_payload = buf[offset:offset + payload_len]
        # Unmask payload
        unmasked = bytes([b ^ mask[i % 4] for i, b in enumerate(raw_payload)])
        return opcode, unmasked, total_needed
    else:
        return opcode, buf[offset:offset + payload_len], total_needed


class SimpleQueue:
    """Lightweight bounded async FIFO queue compatible with MicroPython and CPython."""

    def __init__(self, maxsize: int = 16):
        self.maxsize = maxsize
        self._items = []
        self._ev = asyncio.Event()

    def put_nowait(self, item):
        if len(self._items) >= self.maxsize:
            self._items.pop(0)  # Drop oldest frame (latest-state-wins)
        self._items.append(item)
        self._ev.set()

    def get_nowait(self):
        if self._items:
            return self._items.pop(0)
        raise IndexError("Queue empty")

    async def get(self):
        while not self._items:
            self._ev.clear()
            await self._ev.wait()
        return self._items.pop(0)


class WSClient:
    """Represents a connected WebSocket client with atomic write serialization."""

    def __init__(self, reader, writer, server):
        self.reader = reader
        self.writer = writer
        self.server = server
        self.out_queue = SimpleQueue(maxsize=16)
        self.is_alive = True
        self.writer_task = None

    def start(self):
        self.writer_task = asyncio.create_task(self._write_loop())

    async def _write_loop(self):
        """Dedicated writer task to prevent WebSocket frame interleaving."""
        try:
            while self.is_alive:
                frame = await self.out_queue.get()
                if frame is None:
                    break
                self.writer.write(frame)
                await self.writer.drain()
                # Cooperative yield
                await asyncio.sleep(0)
        except (OSError, Exception):
            pass
        finally:
            await self.close()

    def send_frame(self, frame: bytes):
        """Pushes frame into outbound queue with latest-state-wins drop policy."""
        if not self.is_alive:
            return
        self.out_queue.put_nowait(frame)

    async def close(self):
        """Safely closes connection and deregisters client."""
        if not self.is_alive:
            return
        self.is_alive = False
        try:
            self.writer.close()
            if hasattr(self.writer, "wait_closed"):
                await self.writer.wait_closed()
        except Exception:
            pass
        self.server._remove_client(self)


def is_awaitable(obj):
    """Checks if an object can be awaited in MicroPython or standard Python."""
    return hasattr(obj, "__await__") or type(obj).__name__ in ("generator", "coroutine")


class AsyncServer:
    """Async HTTP and WebSocket server."""

    def __init__(self, host: str = "0.0.0.0", port: int = 80):
        self.host = host
        self.port = port
        self.server = None
        self.clients = set()
        self.routes = {}
        self.on_ws_message = None
        self.on_ws_connect = None
        self.on_ws_disconnect = None
        self._running = False

    def add_route(self, path: str, handler):
        """Registers a custom HTTP endpoint handler."""
        self.routes[path] = handler

    async def start(self):
        """Starts the server."""
        self._running = True
        self.server = await asyncio.start_server(self._handle_connection, self.host, self.port)
        # Capture actual allocated port (if port 0 was passed)
        if hasattr(self.server, "sockets") and self.server.sockets:
            sock = self.server.sockets[0]
            self.port = sock.getsockname()[1]

    async def stop(self):
        """Stops the server and disconnects clients."""
        self._running = False
        for client in list(self.clients):
            await client.close()
        self.clients.clear()
        if self.server:
            self.server.close()
            if hasattr(self.server, "wait_closed"):
                await self.server.wait_closed()

    def _remove_client(self, client: WSClient):
        if client in self.clients:
            self.clients.remove(client)
            if self.on_ws_disconnect:
                try:
                    self.on_ws_disconnect(client)
                except Exception as ex:
                    print_exception(ex)

    def broadcast_sync(self, text: str, exclude: WSClient = None):
        """Broadcasts text message immediately to connected WebSocket clients (zero task overhead)."""
        if not self.clients:
            return
        frame = encode_ws_frame(text, opcode=WS_OP_TEXT)
        for client in list(self.clients):
            if client != exclude and client.is_alive:
                client.send_frame(frame)

    async def broadcast_text(self, text: str, exclude: WSClient = None):
        """Async broadcast helper (compatible with existing await callers)."""
        self.broadcast_sync(text, exclude)

    def send_sync(self, client: WSClient, text: str):
        """Sends text message to a specific client synchronously."""
        if client and client.is_alive:
            frame = encode_ws_frame(text, opcode=WS_OP_TEXT)
            client.send_frame(frame)

    async def send_text(self, client: WSClient, text: str):
        """Sends text message to a specific client."""
        self.send_sync(client, text)

    async def _handle_connection(self, reader, writer):
        """Handles inbound connection (either HTTP or WebSocket upgrade)."""
        client = None
        try:
            # Read HTTP request line and headers
            header_lines = []
            while True:
                line = await reader.readline()
                if not line or line == b"\r\n":
                    break
                header_lines.append(line.decode("utf-8", "ignore").strip())

            if not header_lines:
                writer.close()
                return

            req_line = header_lines[0].split()
            if len(req_line) < 2:
                writer.close()
                return

            _method, path = req_line[0], req_line[1]

            # Parse headers into dict
            headers = {"method": _method}
            for h in header_lines[1:]:
                if ":" in h:
                    k, v = h.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            # Check for WebSocket Upgrade
            is_ws = (
                headers.get("upgrade", "").lower() == "websocket"
                and "upgrade" in headers.get("connection", "").lower()
            )

            if is_ws:
                sec_key = headers.get("sec-websocket-key", "")
                accept_key = calculate_accept_key(sec_key)

                handshake_resp = (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n"
                ).encode("ascii")

                writer.write(handshake_resp)
                await writer.drain()

                client = WSClient(reader, writer, self)
                self.clients.add(client)
                client.start()

                if self.on_ws_connect:
                    try:
                        self.on_ws_connect(client)
                    except Exception as ex:
                        print_exception(ex)

                # WebSocket frame reading loop
                read_buf = bytearray()
                while self._running and client.is_alive:
                    chunk = await reader.read(512)
                    if not chunk:
                        break  # EOF / Connection closed by client
                    read_buf.extend(chunk)

                    while True:
                        opcode, payload, consumed = decode_ws_frame(read_buf)
                        if opcode is None:
                            break
                        # Consume frame from buffer
                        read_buf = read_buf[consumed:]

                        if opcode == WS_OP_CLOSE:
                            # Echo close frame and exit
                            client.send_frame(encode_ws_frame(b"", opcode=WS_OP_CLOSE))
                            return
                        elif opcode == WS_OP_PING:
                            client.send_frame(encode_ws_frame(payload, opcode=WS_OP_PONG))
                        elif opcode == WS_OP_TEXT:
                            try:
                                text = payload.decode("utf-8")
                                if self.on_ws_message:
                                    self.on_ws_message(client, text)
                            except Exception as ex:
                                print_exception(ex)

            else:
                # Regular HTTP Request
                clean_path = path.split("?")[0]
                if clean_path in self.routes:
                    handler = self.routes[clean_path]
                    try:
                        res = handler(reader, writer, path, headers)
                        if is_awaitable(res):
                            await res
                    except Exception as ex:
                        print_exception(ex)
                    finally:
                        try:
                            writer.close()
                            if hasattr(writer, "wait_closed"):
                                await writer.wait_closed()
                        except Exception:
                            pass
                    return

                elif clean_path in ("/", "/index.html"):
                    payload, is_gzip = get_asset_payload()
                    content_len = len(payload)

                    encoding_header = "Content-Encoding: gzip\r\n" if is_gzip else ""
                    headers_resp = (
                        "HTTP/1.1 200 OK\r\n"
                        "Content-Type: text/html; charset=utf-8\r\n"
                        f"{encoding_header}"
                        f"Content-Length: {content_len}\r\n"
                        "Connection: close\r\n"
                        "Cache-Control: max-age=3600\r\n\r\n"
                    ).encode("ascii")

                    writer.write(headers_resp)
                    await writer.drain()

                    # Chunked streaming with explicit cooperative yield
                    chunk_size = 1024
                    for i in range(0, content_len, chunk_size):
                        writer.write(payload[i:i + chunk_size])
                        await writer.drain()
                        await asyncio.sleep(0)  # Cooperative yield
                else:
                    not_found = (
                        "HTTP/1.1 404 Not Found\r\n"
                        "Content-Type: text/plain\r\n"
                        "Content-Length: 9\r\n"
                        "Connection: close\r\n\r\n"
                        "Not Found"
                    ).encode("ascii")
                    writer.write(not_found)
                    await writer.drain()

                writer.close()
                if hasattr(writer, "wait_closed"):
                    await writer.wait_closed()

        except (OSError, Exception) as exc:
            if not isinstance(exc, OSError):
                print_exception(exc)
        finally:
            if client:
                await client.close()
