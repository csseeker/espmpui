"""
Wi-Fi Provisioning, Captive Portal, and DNS Interception for espmui.
Supports asynchronous network scanning, zero-friction mobile onboarding,
and RFC 1035 DNS interception for captive portals.
"""

import json
import sys

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    import usocket as socket
except ImportError:
    import socket

def print_exception(exc):
    """Prints exception traceback on both MicroPython and standard Python."""
    if hasattr(sys, "print_exception"):
        sys.print_exception(exc)
    else:
        import traceback
        traceback.print_exception(exc)


def parse_dns_query(data: bytes):
    """
    Parses an incoming DNS query datagram.
    Returns dict with tx_id, domain, qtype, qclass, or None if malformed.
    """
    if len(data) < 12:
        return None

    tx_id = data[:2]
    qdcount = (data[4] << 8) | data[5]
    if qdcount < 1:
        return None

    labels = []
    idx = 12
    data_len = len(data)

    while idx < data_len:
        label_len = data[idx]
        if label_len == 0:
            idx += 1
            break
        # Pointer
        if (label_len & 0xC0) == 0xC0:
            idx += 2
            break
        idx += 1
        if idx + label_len > data_len:
            return None
        labels.append(data[idx:idx + label_len].decode("utf-8", "ignore"))
        idx += label_len

    if idx + 4 > data_len:
        return None

    qtype = (data[idx] << 8) | data[idx + 1]
    qclass = (data[idx + 2] << 8) | data[idx + 3]
    domain = ".".join(labels)

    return {
        "tx_id": tx_id,
        "domain": domain,
        "qtype": qtype,
        "qclass": qclass,
        "q_end": idx + 4,
    }


def build_dns_response(query_packet: bytes, target_ip: str = "192.168.4.1") -> bytes:
    """
    Builds an RFC 1035 DNS response redirecting any A-record query to target_ip.
    """
    query = parse_dns_query(query_packet)
    if not query:
        return None

    tx_id = query["tx_id"]
    q_end = query["q_end"]
    question_data = query_packet[12:q_end]

    # Flags: 0x8180 (Standard query response, No error, Recursion available)
    flags = b"\x81\x80"
    counts = b"\x00\x01\x00\x01\x00\x00\x00\x00"  # QDCOUNT=1, ANCOUNT=1, NSCOUNT=0, ARCOUNT=0

    # Answer section (A Record)
    # Name pointer: 0xC00C (points to offset 12 in the packet)
    # Type: 0x0001 (A), Class: 0x0001 (IN), TTL: 60s, Len: 4
    ip_parts = [int(p) for p in target_ip.split(".")]
    ip_bytes = bytes(ip_parts)
    answer = b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + ip_bytes

    return tx_id + flags + counts + question_data + answer


class DNSServer:
    """Lightweight asynchronous UDP DNS server for captive portal interception."""

    def __init__(self, target_ip: str = "192.168.4.1", port: int = 53, host: str = "0.0.0.0"):
        self.target_ip = target_ip
        self.port = port
        self.host = host
        self.sock = None
        self._running = False
        self._task = None

    async def start(self):
        """Binds UDP socket and starts non-blocking interception loop."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        try:
            self.sock.bind((self.host, self.port))
        except OSError:
            # Re-raise or fallback if port is restricted
            pass
        self._running = True
        self._task = asyncio.create_task(self._serve_loop())

    async def _serve_loop(self):
        """Asynchronous datagram receive loop with cooperative yields."""
        while self._running:
            try:
                data, addr = self.sock.recvfrom(512)
                if data:
                    resp = build_dns_response(data, self.target_ip)
                    if resp:
                        self.sock.sendto(resp, addr)
            except OSError:
                # Socket would block or no packet ready
                pass
            except Exception as ex:
                print_exception(ex)
            # Cooperative yield
            await asyncio.sleep(0.02)

    async def stop(self):
        """Stops the DNS server and releases socket."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


class MockWLAN:
    """Mock WLAN driver for desktop testing and simulation."""

    def __init__(self):
        self._active = False
        self._connected = False
        self._config = ("192.168.1.100", "255.255.255.0", "192.168.1.1", "1.1.1.1")
        self.mock_scan_results = []
        self.connect_succeeds = True
        self.last_ssid = ""
        self.last_password = ""

    def active(self, val=None):
        if val is not None:
            self._active = bool(val)
        return self._active

    def scan(self):
        return self.mock_scan_results

    def connect(self, ssid, password):
        self.last_ssid = ssid
        self.last_password = password
        self._connected = self.connect_succeeds

    def disconnect(self):
        self._connected = False

    def isconnected(self):
        return self._connected

    def status(self):
        return 1000 if self._connected else 0

    def ifconfig(self, config=None):
        if config is not None:
            self._config = config
        return self._config


class WiFiManager:
    """
    Hardware-abstracted Wi-Fi manager for MicroPython (ESP32/Pico W) and CPython desktop.
    Handles background scanning, credential verification, and SoftAP management.
    """

    def __init__(self, wlan_sta=None, wlan_ap=None):
        if wlan_sta is not None:
            self.sta = wlan_sta
        else:
            try:
                import network
                self.sta = network.WLAN(network.STA_IF)
            except (ImportError, AttributeError):
                self.sta = MockWLAN()

        if wlan_ap is not None:
            self.ap = wlan_ap
        else:
            try:
                import network
                self.ap = network.WLAN(network.AP_IF)
            except (ImportError, AttributeError):
                self.ap = MockWLAN()

        self.current_ssid = ""
        self.current_ip = ""

    def start_ap(self, ssid: str = "espmui-Setup", password: str = None, ip: str = "192.168.4.1"):
        """Activates SoftAP with standard captive gateway configuration."""
        self.ap.active(True)
        if hasattr(self.ap, "config"):
            try:
                if password:
                    self.ap.config(essid=ssid, password=password, authmode=3)
                else:
                    self.ap.config(essid=ssid, authmode=0)
            except Exception:
                pass
        if hasattr(self.ap, "ifconfig"):
            try:
                self.ap.ifconfig((ip, "255.255.255.0", ip, ip))
            except Exception:
                pass

    def stop_ap(self):
        """Deactivates SoftAP."""
        if self.ap:
            self.ap.active(False)

    async def scan_networks(self):
        """
        Asynchronously scans for nearby Wi-Fi networks.
        Deduplicates SSIDs, filters hidden networks, and calculates RSSI signal quality bars.
        """
        self.sta.active(True)
        await asyncio.sleep(0.01)

        raw_results = self.sta.scan()

        seen = {}
        for entry in raw_results:
            # entry: (ssid, bssid, channel, rssi, authmode, hidden)
            ssid_raw = entry[0]
            if isinstance(ssid_raw, (bytes, bytearray)):
                ssid = ssid_raw.decode("utf-8", "ignore").strip()
            else:
                ssid = str(ssid_raw).strip()

            if not ssid:
                continue

            rssi = entry[3]
            authmode = entry[4]

            # Signal bars (1 to 4)
            if rssi >= -60:
                bars = 4
            elif rssi >= -70:
                bars = 3
            elif rssi >= -80:
                bars = 2
            else:
                bars = 1

            secure = authmode > 0

            # Deduplicate by SSID, retaining highest signal strength
            if ssid not in seen or seen[ssid]["rssi"] < rssi:
                seen[ssid] = {
                    "ssid": ssid,
                    "rssi": rssi,
                    "bars": bars,
                    "secure": secure,
                    "channel": entry[2] if len(entry) > 2 else 1,
                }

        networks = list(seen.values())
        networks.sort(key=lambda x: x["rssi"], reverse=True)
        return networks

    async def connect(self, ssid: str, password: str, timeout: float = 12.0) -> dict:
        """
        Attempts to connect to target AP without terminating SoftAP.
        Returns result dict with status, ip, ssid, or error message.
        """
        self.sta.active(True)
        self.sta.connect(ssid, password)

        elapsed = 0
        step = 0.25

        while elapsed < timeout:
            await asyncio.sleep(step)
            elapsed += step
            if self.sta.isconnected():
                ip = self.sta.ifconfig()[0] if hasattr(self.sta, "ifconfig") else "192.168.1.100"
                self.current_ssid = ssid
                self.current_ip = ip
                return {
                    "status": "connected",
                    "ssid": ssid,
                    "ip": ip,
                    "gateway": self.sta.ifconfig()[2] if hasattr(self.sta, "ifconfig") else "",
                }

        return {
            "status": "failed",
            "error": "Connection timed out or invalid password",
        }

    def is_connected(self) -> bool:
        """Returns True if station interface is actively connected."""
        return bool(self.sta and self.sta.isconnected())

    def get_status(self) -> dict:
        """Returns current Wi-Fi telemetry and operational mode."""
        sta_connected = self.is_connected()
        ip = self.current_ip
        if sta_connected and hasattr(self.sta, "ifconfig"):
            ip = self.sta.ifconfig()[0]

        return {
            "connected": sta_connected,
            "ssid": self.current_ssid if sta_connected else "",
            "ip": ip,
            "ap_active": bool(self.ap and self.ap.active()),
        }


class CaptivePortal:
    """
    Coordinates Wi-Fi provisioner, captive HTTP interception, and DNS server.
    """

    def __init__(self, server, wifi_manager: WiFiManager = None, ap_ip: str = "192.168.4.1", dns_port: int = 53):
        self.server = server
        self.wifi_mgr = wifi_manager or WiFiManager()
        self.ap_ip = ap_ip
        self.dns_server = DNSServer(target_ip=ap_ip, port=dns_port)

    def attach(self):
        """Registers captive redirection and provisioning REST routes onto server."""
        # 1. Android, iOS, Windows Captive Probe Redirection
        captive_probe_paths = [
            "/generate_204",
            "/gen_204",
            "/canonical.html",
            "/hotspot-detect.html",
            "/ncsi.txt",
            "/connecttest.txt",
            "/redirect",
            "/mobile/status.php",
            "/check_network_status.txt",
        ]
        for path in captive_probe_paths:
            self.server.add_route(path, self._handle_captive_probe)

        # 2. REST API Routes
        self.server.add_route("/api/wifi/scan", self._handle_api_scan)
        self.server.add_route("/api/wifi/connect", self._handle_api_connect)
        self.server.add_route("/api/wifi/status", self._handle_api_status)
        self.server.add_route("/setup", self._handle_setup_page)

    async def _handle_setup_page(self, reader, writer, path, headers):
        """Serves the onboarding portal frontend bundle on /setup."""
        from espmui.assets import get_asset_payload
        payload, is_gzip = get_asset_payload()
        content_len = len(payload)
        encoding_header = "Content-Encoding: gzip\r\n" if is_gzip else ""
        headers_resp = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            f"{encoding_header}"
            f"Content-Length: {content_len}\r\n"
            "Connection: close\r\n"
            "Cache-Control: no-cache\r\n\r\n"
        ).encode("ascii")
        writer.write(headers_resp)
        await writer.drain()

        try:
            chunk_size = 1024
            for i in range(0, content_len, chunk_size):
                writer.write(payload[i:i + chunk_size])
                await writer.drain()
                await asyncio.sleep(0)
        except (OSError, Exception):
            pass

    async def _handle_captive_probe(self, reader, writer, path, headers):
        """Redirects captive probe requests to the captive setup portal."""
        redirect_resp = (
            f"HTTP/1.1 302 Found\r\n"
            f"Location: http://{self.ap_ip}/\r\n"
            f"Content-Length: 0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii")
        writer.write(redirect_resp)
        await writer.drain()

    async def _handle_api_scan(self, reader, writer, path, headers):
        """API: Asynchronously scans nearby networks and returns JSON list."""
        networks = await self.wifi_mgr.scan_networks()
        payload = json.dumps({"status": "ok", "networks": networks}).encode("utf-8")
        resp = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii") + payload
        writer.write(resp)
        await writer.drain()

    async def _handle_api_connect(self, reader, writer, path, headers):
        """API: Reads JSON credentials and initiates non-blocking connection."""
        content_len = int(headers.get("content-length", 0))
        body = b""
        if content_len > 0:
            body = await reader.read(content_len)

        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            data = {}

        ssid = data.get("ssid", "").strip()
        password = data.get("password", "")

        if not ssid:
            err = json.dumps({"status": "error", "message": "SSID required"}).encode("utf-8")
            resp = (
                f"HTTP/1.1 400 Bad Request\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(err)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("ascii") + err
            writer.write(resp)
            await writer.drain()
            return

        res = await self.wifi_mgr.connect(ssid, password)
        payload = json.dumps(res).encode("utf-8")
        resp = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii") + payload
        writer.write(resp)
        await writer.drain()

    async def _handle_api_status(self, reader, writer, path, headers):
        """API: Returns current Wi-Fi status."""
        status = self.wifi_mgr.get_status()
        payload = json.dumps({"status": "ok", "wifi": status}).encode("utf-8")
        resp = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii") + payload
        writer.write(resp)
        await writer.drain()

    async def start(self):
        """Starts DNS server."""
        await self.dns_server.start()

    async def stop(self):
        """Stops DNS server."""
        await self.dns_server.stop()
