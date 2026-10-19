import asyncio
import sys
import unittest

# Ensure src/ is in sys.path
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from espmui.server import (
    calculate_accept_key,
    encode_ws_frame,
    decode_ws_frame,
    AsyncServer,
    WS_OP_TEXT,
)


class TestWebSocketProtocol(unittest.TestCase):
    def test_rfc6455_handshake_accept_key(self):
        """Verify WebSocket handshake key calculation against RFC 6455 test vector."""
        sample_key = "dGhlIHNhbXBsZSBub25jZQ=="
        expected_accept = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
        self.assertEqual(calculate_accept_key(sample_key), expected_accept)

    def test_encode_short_text_frame(self):
        """Verify encoding of a short unmasked text frame (< 126 bytes)."""
        payload = '{"op":"ping"}'
        frame = encode_ws_frame(payload, opcode=WS_OP_TEXT)
        # Byte 0: FIN (0x80) | Text (0x01) = 0x81
        self.assertEqual(frame[0], 0x81)
        # Byte 1: Mask bit (0) | Length
        self.assertEqual(frame[1], len(payload))
        # Payload matches
        self.assertEqual(frame[2:].decode("utf-8"), payload)

    def test_encode_extended_text_frame(self):
        """Verify encoding of an extended payload (126 to 65535 bytes)."""
        payload = "A" * 300
        frame = encode_ws_frame(payload, opcode=WS_OP_TEXT)
        self.assertEqual(frame[0], 0x81)
        self.assertEqual(frame[1], 126)  # Indicates 16-bit extended length
        length = int.from_bytes(frame[2:4], "big")
        self.assertEqual(length, 300)
        self.assertEqual(frame[4:].decode("utf-8"), payload)

    def test_decode_masked_text_frame(self):
        """Verify decoding of a masked frame sent by a client."""
        # Simulated client frame for "Hello" with mask [0x37, 0xfa, 0x21, 0x3d]
        # "Hello" in bytes: [0x48, 0x65, 0x6c, 0x6c, 0x6f]
        # Masked:
        # 0x48 ^ 0x37 = 0x7f
        # 0x65 ^ 0xfa = 0x9f
        # 0x6c ^ 0x21 = 0x4d
        # 0x6c ^ 0x3d = 0x51
        # 0x6f ^ 0x37 = 0x58
        mask = bytes([0x37, 0xfa, 0x21, 0x3d])
        masked_payload = bytes([0x7f, 0x9f, 0x4d, 0x51, 0x58])
        raw_frame = bytes([0x81, 0x85]) + mask + masked_payload

        opcode, payload, consumed = decode_ws_frame(raw_frame)
        self.assertEqual(opcode, WS_OP_TEXT)
        self.assertEqual(payload.decode("utf-8"), "Hello")
        self.assertEqual(consumed, len(raw_frame))

    def test_decode_incomplete_frame(self):
        """Verify that an incomplete frame returns None until full buffer is received."""
        raw_frame = bytes([0x81, 0x85, 0x37])  # Missing mask and payload
        opcode, payload, consumed = decode_ws_frame(raw_frame)
        self.assertIsNone(opcode)
        self.assertIsNone(payload)
        self.assertEqual(consumed, 0)


class TestAsyncServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = AsyncServer(host="127.0.0.1", port=0)
        self.received_messages = []
        self.server.on_ws_message = self._on_msg
        await self.server.start()
        # Retrieve allocated port
        self.port = self.server.port

    async def asyncTearDown(self):
        await self.server.stop()

    def _on_msg(self, client, text):
        self.received_messages.append((client, text))

    async def test_http_get_root(self):
        """Verify HTTP GET / returns 200 OK and HTML content."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()

        response = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 200 OK", response)
        self.assertIn(b"Content-Type: text/html", response)

    async def test_websocket_handshake_and_exchange(self):
        """Verify full RFC 6455 upgrade handshake and message exchange."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        ws_key = "dGhlIHNhbXBsZSBub25jZQ=="
        handshake_req = (
            f"GET /ws HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {ws_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode()
        writer.write(handshake_req)
        await writer.drain()

        # Read HTTP 101 Switching Protocols response
        resp = await reader.read(1024)
        self.assertIn(b"HTTP/1.1 101 Switching Protocols", resp)
        self.assertIn(b"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=", resp)

        # Send a masked WebSocket text message: {"op":"hello"}
        text = '{"op":"hello"}'
        mask = bytes([0x12, 0x34, 0x56, 0x78])
        raw_text = text.encode("utf-8")
        masked = bytes([b ^ mask[i % 4] for i, b in enumerate(raw_text)])
        frame = bytes([0x81, 0x80 | len(raw_text)]) + mask + masked

        writer.write(frame)
        await writer.drain()

        # Wait for server to process message
        await asyncio.sleep(0.05)
        self.assertEqual(len(self.received_messages), 1)
        self.assertEqual(self.received_messages[0][1], text)

        # Verify server broadcast
        await self.server.broadcast_text('{"op":"ack"}')
        resp_frame = await reader.read(1024)
        opcode, payload, _ = decode_ws_frame(resp_frame)
        self.assertEqual(opcode, WS_OP_TEXT)
        self.assertEqual(payload.decode("utf-8"), '{"op":"ack"}')

        writer.close()
        await writer.wait_closed()

    async def test_custom_route(self):
        """Verify custom route registration and query parameter handling."""
        async def custom_handler(reader, writer, path, headers):
            resp = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 5\r\nConnection: close\r\n\r\nHELLO"
            writer.write(resp)
            await writer.drain()

        self.server.add_route("/custom", custom_handler)

        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"GET /custom?foo=bar HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()

        resp = await reader.read(1024)
        self.assertIn(b"HTTP/1.1 200 OK", resp)
        self.assertIn(b"HELLO", resp)

        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    unittest.main()
