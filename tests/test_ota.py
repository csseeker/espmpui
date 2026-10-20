import asyncio
import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from espmpui.ota import OTAHandler, MockOTAPartition, parse_multipart_boundary
from espmpui.app import App


class TestMultipartParsing(unittest.TestCase):
    def test_parse_multipart_boundary(self):
        """Verify boundary extraction from Content-Type header."""
        header = "multipart/form-data; boundary=---------------------------974767299852498929531610575"
        boundary = parse_multipart_boundary(header)
        self.assertEqual(boundary, b"---------------------------974767299852498929531610575")

        header2 = "multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW"
        self.assertEqual(parse_multipart_boundary(header2), b"----WebKitFormBoundary7MA4YWxkTrZu0gW")

    def test_missing_or_invalid_boundary(self):
        """Verify None returned for invalid or missing boundary."""
        self.assertIsNone(parse_multipart_boundary("text/html"))
        self.assertIsNone(parse_multipart_boundary(""))
        self.assertIsNone(parse_multipart_boundary(None))


class TestStreamingOTA(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.partition = MockOTAPartition(size=2 * 1024 * 1024)
        self.ota = OTAHandler(target_partition=self.partition, chunk_size=512)

    async def test_stream_binary_firmware(self):
        """Verify streaming 64 KB firmware payload in small chunks with SHA-256 verification."""
        # Generate 64 KB synthetic firmware binary
        firmware_bytes = bytes([i % 256 for i in range(65536)])
        expected_sha = hashlib.sha256(firmware_bytes).hexdigest()

        boundary = b"----WebKitFormBoundarySimulatedOTA123"
        multipart_data = (
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="firmware"; filename="firmware.bin"\r\n'
            b"Content-Type: application/octet-stream\r\n\r\n"
            + firmware_bytes +
            b"\r\n--" + boundary + b"--\r\n"
        )

        stream = asyncio.StreamReader()
        stream.feed_data(multipart_data)
        stream.feed_eof()

        res = await self.ota.process_upload_stream(stream, boundary, len(multipart_data))

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["bytes_written"], 65536)
        self.assertEqual(res["sha256"], expected_sha)
        self.assertTrue(self.partition.is_boot_set)
        # Verify written data matches original exactly
        self.assertEqual(self.partition.get_written_data(), firmware_bytes)

    async def test_streaming_does_not_buffer_entire_file(self):
        """Verify that streaming writer never retains more than max buffer limit in memory."""
        # Test with peak buffer monitoring
        self.ota.peak_buffer_size = 0
        firmware_bytes = os.urandom(32768)
        boundary = b"----TestBoundaryPeakRAM"
        body = (
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="update"; filename="app.bin"\r\n\r\n'
            + firmware_bytes +
            b"\r\n--" + boundary + b"--\r\n"
        )

        stream = asyncio.StreamReader()
        stream.feed_data(body)
        stream.feed_eof()

        res = await self.ota.process_upload_stream(stream, boundary, len(body))
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["bytes_written"], 32768)
        # Peak RAM buffer must remain strictly under 4 KB
        self.assertLess(self.ota.peak_buffer_size, 4096)

    async def test_empty_payload_rejected(self):
        """Verify empty uploads are rejected without setting boot partition."""
        boundary = b"----BoundaryEmpty"
        body = (
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="firmware"; filename="empty.bin"\r\n\r\n'
            b"\r\n--" + boundary + b"--\r\n"
        )
        stream = asyncio.StreamReader()
        stream.feed_data(body)
        stream.feed_eof()

        res = await self.ota.process_upload_stream(stream, boundary, len(body))
        self.assertEqual(res["status"], "error")
        self.assertFalse(self.partition.is_boot_set)


class TestOTAAppIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = App(title="OTA Node")
        self.partition = MockOTAPartition()
        self.ota = self.app.enable_ota(partition=self.partition)
        await self.app.start(host="127.0.0.1", port=0)
        self.port = self.app.server.port

    async def asyncTearDown(self):
        await self.app.server.stop()

    async def test_get_api_ota_status(self):
        """Verify GET /api/ota/status returns partition info."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"GET /api/ota/status HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        await writer.drain()

        resp = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 200 OK", resp)
        self.assertIn(b'"running_partition"', resp)
        self.assertIn(b'"next_update_partition"', resp)

    async def test_post_api_ota_upload_success(self):
        """Verify POST /api/ota/upload streams binary firmware and returns 200 OK with SHA."""
        test_payload = b"MICROPYTHON_TEST_FIRMWARE_BINARY_DATA_BLOCK"
        boundary = "---------------------------OTAAppTestBoundary123"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="firmware.bin"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + test_payload + f"\r\n--{boundary}--\r\n".encode()

        headers = (
            f"POST /api/ota/upload HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.port}\r\n"
            f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
            f"Content-Length: {len(body)}\r\n\r\n"
        ).encode()

        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(headers + body)
        await writer.drain()

        resp = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 200 OK", resp)
        self.assertIn(b'"status": "ok"', resp)
        self.assertIn(b'"sha256"', resp)
        self.assertTrue(self.partition.is_boot_set)


if __name__ == "__main__":
    unittest.main()
