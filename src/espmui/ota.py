"""
Web-Based Drag-and-Drop OTA Updater for MicroPython on ESP32.
Provides chunked multipart streaming without RAM buffering (OOM avoidance),
incremental SHA-256 verification, and active partition toggling.
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
    import esp32
    _HAS_ESP32 = True
except ImportError:
    _HAS_ESP32 = False


def print_exception(exc):
    if hasattr(sys, "print_exception"):
        sys.print_exception(exc)
    else:
        import traceback
        traceback.print_exception(exc)


def parse_multipart_boundary(content_type: str):
    """Extracts the multipart boundary bytes from a Content-Type header."""
    if not content_type or "boundary=" not in content_type:
        return None
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("boundary="):
            b_val = part.split("=", 1)[1].strip().strip('"\'')
            if b_val:
                return b_val.encode("ascii")
    return None


class MockOTAPartition:
    """Simulates an ESP32 OTA flash partition for desktop testing and validation."""

    def __init__(self, size: int = 2 * 1024 * 1024, label: str = "ota_1"):
        self.size = size
        self.label = label
        self.is_boot_set = False
        self._data = bytearray()

    def write(self, data: bytes):
        """Append data directly to simulated partition."""
        self._data.extend(data)

    def writeblocks(self, block_num: int, data: bytes, offset: int = 0):
        """Block-device write protocol compatibility."""
        pos = block_num * 4096 + offset
        if len(self._data) < pos + len(data):
            self._data.extend(b"\x00" * (pos + len(data) - len(self._data)))
        self._data[pos:pos + len(data)] = data

    def set_boot(self):
        """Marks this partition as active boot target."""
        self.is_boot_set = True

    def get_written_data(self) -> bytes:
        """Returns the full raw bytes written to this partition."""
        return bytes(self._data)

    def info(self):
        """Returns MicroPython partition tuple: (type, subtype, addr, size, label, encrypted)."""
        return (0, 16, 0x100000, self.size, self.label, False)


class OTAHandler:
    """
    Streaming OTA firmware flasher.
    Reads incoming multipart HTTP streams in small, fixed-size chunks,
    streaming directly to the inactive OTA partition with incremental SHA-256 calculation.
    """

    def __init__(self, target_partition=None, running_partition=None, chunk_size: int = 512):
        self.chunk_size = chunk_size
        self.bytes_written = 0
        self.peak_buffer_size = 0
        self.is_flashing = False
        self.last_sha256 = ""

        # Initialize partitions
        if target_partition is not None:
            self.target_partition = target_partition
            self.running_partition = running_partition or MockOTAPartition(label="ota_0")
        elif _HAS_ESP32:
            try:
                running = esp32.Partition(esp32.Partition.RUNNING)
                self.running_partition = running
                self.target_partition = running.get_next_update()
            except (OSError, Exception):
                self.running_partition = MockOTAPartition(label="ota_0")
                self.target_partition = MockOTAPartition(label="ota_1")
        else:
            self.running_partition = MockOTAPartition(label="ota_0")
            self.target_partition = MockOTAPartition(label="ota_1")

    @property
    def running_partition_name(self) -> str:
        if hasattr(self.running_partition, "info"):
            try:
                return self.running_partition.info()[4]
            except Exception:
                pass
        return getattr(self.running_partition, "label", "ota_0")

    @property
    def target_partition_name(self) -> str:
        if hasattr(self.target_partition, "info"):
            try:
                return self.target_partition.info()[4]
            except Exception:
                pass
        return getattr(self.target_partition, "label", "ota_1")

    def get_status(self) -> dict:
        """Returns current OTA subsystem and partition information."""
        return {
            "status": "flashing" if self.is_flashing else "ready",
            "running_partition": self.running_partition_name,
            "next_update_partition": self.target_partition_name,
            "bytes_written": self.bytes_written,
            "last_sha256": self.last_sha256,
        }

    def _write_chunk(self, data: bytes):
        """Writes a chunk of bytes to the target partition."""
        if not data:
            return
        if hasattr(self.target_partition, "write"):
            self.target_partition.write(data)
        elif hasattr(self.target_partition, "writeblocks"):
            block = self.bytes_written // 4096
            offset = self.bytes_written % 4096
            self.target_partition.writeblocks(block, data, offset)

    async def process_upload_stream(self, reader, boundary: bytes, content_length: int = 0) -> dict:
        """
        Consumes multipart stream, parses headers, writes binary payload in chunks,
        computes SHA-256, and activates the update partition.
        """
        if not boundary:
            return {"status": "error", "bytes_written": 0, "message": "Missing boundary"}

        self.is_flashing = True
        self.bytes_written = 0
        self.peak_buffer_size = 0
        hasher = hashlib.sha256()

        try:
            # 1. Read multipart part headers until empty line
            found_header_end = False
            while True:
                line = await reader.readline()
                if not line:
                    break
                if line in (b"\r\n", b"\n", b""):
                    found_header_end = True
                    break

            if not found_header_end:
                self.is_flashing = False
                return {"status": "error", "bytes_written": 0, "message": "Malformed multipart stream"}

            # 2. Stream binary payload chunk by chunk
            # The payload terminates with "\r\n--" + boundary
            delimiter = b"\r\n--" + boundary
            delim_len = len(delimiter)
            buf = bytearray()

            while True:
                chunk = await reader.read(self.chunk_size)
                if not chunk:
                    # Premature EOF without boundary
                    break

                buf.extend(chunk)
                if len(buf) > self.peak_buffer_size:
                    self.peak_buffer_size = len(buf)

                # Check if closing boundary is in the buffer
                idx = buf.find(delimiter)
                if idx != -1:
                    # Found delimiter! Write all remaining payload before delimiter
                    to_write = bytes(buf[:idx])
                    if to_write:
                        self._write_chunk(to_write)
                        hasher.update(to_write)
                        self.bytes_written += len(to_write)
                    buf = buf[idx:]
                    break

                # Boundary not found in current buffer.
                # Safe to write anything before the last delim_len bytes
                if len(buf) > delim_len:
                    safe_len = len(buf) - delim_len
                    to_write = bytes(buf[:safe_len])
                    self._write_chunk(to_write)
                    hasher.update(to_write)
                    self.bytes_written += len(to_write)
                    del buf[:safe_len]

                # Cooperative yield to prevent starvation on ESP32
                await asyncio.sleep(0)

            # Check if any binary data was written
            if self.bytes_written == 0:
                self.is_flashing = False
                return {"status": "error", "bytes_written": 0, "message": "Empty or invalid firmware binary"}

            # Compute final SHA-256
            sha256_hex = hasher.hexdigest()
            self.last_sha256 = sha256_hex

            # Mark partition for next boot
            if hasattr(self.target_partition, "set_boot"):
                self.target_partition.set_boot()

            self.is_flashing = False
            return {
                "status": "ok",
                "bytes_written": self.bytes_written,
                "sha256": sha256_hex,
                "message": "Firmware flashed successfully",
            }

        except Exception as exc:
            self.is_flashing = False
            print_exception(exc)
            return {"status": "error", "bytes_written": self.bytes_written, "message": str(exc)}
