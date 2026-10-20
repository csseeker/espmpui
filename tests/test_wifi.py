import asyncio
import socket
import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from espmpui.wifi import (
    DNSServer,
    parse_dns_query,
    build_dns_response,
    WiFiManager,
    MockWLAN,
    CaptivePortal,
)
from espmpui.server import AsyncServer


class TestDNSCaptiveProtocol(unittest.TestCase):
    def test_parse_dns_query_standard(self):
        """Verify parsing standard DNS query for connectivitycheck.gstatic.com."""
        # Standard DNS query for "connectivitycheck.gstatic.com", QTYPE=A (1), QCLASS=IN (1), TxID=0x1234
        tx_id = b"\x12\x34"
        flags = b"\x01\x00"  # Standard query
        counts = b"\x00\x01\x00\x00\x00\x00\x00\x00"  # QDCOUNT=1, ANCOUNT=0, NSCOUNT=0, ARCOUNT=0

        # QNAME: 17connectivitycheck 7gstatic 3com 0
        qname = (
            b"\x11connectivitycheck"
            b"\x07gstatic"
            b"\x03com"
            b"\x00"
        )
        qtype_qclass = b"\x00\x01\x00\x01"  # Type A, Class IN
        packet = tx_id + flags + counts + qname + qtype_qclass

        query = parse_dns_query(packet)
        self.assertIsNotNone(query)
        self.assertEqual(query["tx_id"], tx_id)
        self.assertEqual(query["domain"], "connectivitycheck.gstatic.com")
        self.assertEqual(query["qtype"], 1)
        self.assertEqual(query["qclass"], 1)

    def test_parse_dns_query_malformed(self):
        """Verify that malformed or truncated DNS packets do not raise exceptions."""
        self.assertIsNone(parse_dns_query(b""))
        self.assertIsNone(parse_dns_query(b"\x12\x34\x01"))
        self.assertIsNone(parse_dns_query(b"\x00" * 11))

    def test_build_dns_response(self):
        """Verify constructing RFC 1035 compliant A-record response."""
        tx_id = b"\xaa\xbb"
        qname = b"\x06google\x03com\x00"
        qtype_qclass = b"\x00\x01\x00\x01"
        packet = tx_id + b"\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + qname + qtype_qclass

        resp = build_dns_response(packet, target_ip="192.168.4.1")
        self.assertIsNotNone(resp)
        self.assertEqual(resp[:2], tx_id)
        # Flags: 0x8180 (Response, Recursion Available)
        self.assertEqual(resp[2:4], b"\x81\x80")
        # Questions: 1, Answers: 1
        self.assertEqual(resp[4:8], b"\x00\x01\x00\x01")
        # Tail should contain target IP bytes: 192.168.4.1 -> [192, 168, 4, 1]
        self.assertEqual(resp[-4:], bytes([192, 168, 4, 1]))


class TestDNSServerAsync(unittest.IsolatedAsyncioTestCase):
    async def test_dns_server_udp_interception(self):
        """Verify DNSServer intercepts UDP query on localhost and returns A-record."""
        dns = DNSServer(target_ip="192.168.4.1", port=15353, host="127.0.0.1")
        await dns.start()

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_sock.setblocking(False)

        # Build query packet for captive.apple.com
        tx_id = b"\x34\x12"
        qname = b"\x07captive\x05apple\x03com\x00"
        qtype_qclass = b"\x00\x01\x00\x01"
        query_packet = tx_id + b"\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + qname + qtype_qclass

        client_sock.sendto(query_packet, ("127.0.0.1", 15353))

        resp = None
        for _ in range(50):
            await asyncio.sleep(0.02)
            try:
                resp, _ = client_sock.recvfrom(512)
                if resp:
                    break
            except OSError:
                pass
        client_sock.close()

        await dns.stop()

        self.assertIsNotNone(resp)
        self.assertEqual(resp[:2], tx_id)
        self.assertEqual(resp[-4:], bytes([192, 168, 4, 1]))


class TestWiFiManager(unittest.IsolatedAsyncioTestCase):
    async def test_mock_wlan_scanning(self):
        """Verify scanning nearby networks and formatting RSSI signal bars."""
        wlan = MockWLAN()
        # Add mock scan results: (ssid, bssid, channel, rssi, authmode, hidden)
        wlan.mock_scan_results = [
            (b"HomeNetwork", b"\x00\x11\x22\x33\x44\x55", 1, -50, 3, False),
            (b"WeakGuest", b"\x00\x11\x22\x33\x44\x56", 6, -85, 4, False),
            (b"OpenCafe", b"\x00\x11\x22\x33\x44\x57", 11, -65, 0, False),
            (b"", b"\x00\x11\x22\x33\x44\x58", 6, -60, 3, True),  # Hidden SSID
        ]

        mgr = WiFiManager(wlan_sta=wlan)
        networks = await mgr.scan_networks()

        self.assertEqual(len(networks), 3)  # Hidden network skipped
        # Highest RSSI first
        self.assertEqual(networks[0]["ssid"], "HomeNetwork")
        self.assertEqual(networks[0]["rssi"], -50)
        self.assertTrue(networks[0]["secure"])
        self.assertEqual(networks[0]["bars"], 4)

        self.assertEqual(networks[1]["ssid"], "OpenCafe")
        self.assertFalse(networks[1]["secure"])
        self.assertEqual(networks[1]["bars"], 3)

        self.assertEqual(networks[2]["ssid"], "WeakGuest")
        self.assertTrue(networks[2]["secure"])
        self.assertEqual(networks[2]["bars"], 1)

    async def test_connect_success(self):
        """Verify successful async Wi-Fi connection with IP retrieval."""
        wlan = MockWLAN()
        wlan.connect_succeeds = True
        mgr = WiFiManager(wlan_sta=wlan)

        res = await mgr.connect("HomeNetwork", "secret123", timeout=2.0)
        self.assertEqual(res["status"], "connected")
        self.assertEqual(res["ssid"], "HomeNetwork")
        self.assertEqual(res["ip"], "192.168.1.100")
        self.assertTrue(mgr.is_connected())

    async def test_connect_failure_does_not_raise(self):
        """Verify failed connection returns clean error dictionary without raising."""
        wlan = MockWLAN()
        wlan.connect_succeeds = False
        mgr = WiFiManager(wlan_sta=wlan)

        res = await mgr.connect("HomeNetwork", "wrongpass", timeout=0.5)
        self.assertEqual(res["status"], "failed")
        self.assertIn("error", res)
        self.assertFalse(mgr.is_connected())


class TestCaptivePortalIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = AsyncServer(host="127.0.0.1", port=0)
        self.wlan = MockWLAN()
        self.wlan.mock_scan_results = [
            (b"FastWiFi", b"\x00\x01\x02\x03\x04\x05", 1, -55, 3, False)
        ]
        self.wifi_mgr = WiFiManager(wlan_sta=self.wlan)
        self.portal = CaptivePortal(self.server, self.wifi_mgr, ap_ip="192.168.4.1")
        self.portal.attach()
        await self.server.start()
        self.port = self.server.port

    async def asyncTearDown(self):
        await self.portal.stop()
        await self.server.stop()

    async def test_android_generate_204_captive_redirect(self):
        """Verify Android /generate_204 probe triggers 302 redirect to portal."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"GET /generate_204 HTTP/1.1\r\nHost: connectivitycheck.gstatic.com\r\n\r\n")
        await writer.drain()

        resp = await reader.read(1024)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 302 Found", resp)
        self.assertIn(b"Location: http://192.168.4.1/", resp)

    async def test_apple_hotspot_detect_redirect(self):
        """Verify Apple /hotspot-detect.html probe triggers 302 redirect."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"GET /hotspot-detect.html HTTP/1.1\r\nHost: captive.apple.com\r\n\r\n")
        await writer.drain()

        resp = await reader.read(1024)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 302 Found", resp)
        self.assertIn(b"Location: http://192.168.4.1/", resp)

    async def test_windows_ncsi_redirect(self):
        """Verify Windows /ncsi.txt probe triggers 302 redirect."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"GET /ncsi.txt HTTP/1.1\r\nHost: www.msftncsi.com\r\n\r\n")
        await writer.drain()

        resp = await reader.read(1024)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 302 Found", resp)
        self.assertIn(b"Location: http://192.168.4.1/", resp)

    async def test_api_wifi_scan_endpoint(self):
        """Verify GET /api/wifi/scan returns JSON array of nearby networks."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"GET /api/wifi/scan HTTP/1.1\r\nHost: 192.168.4.1\r\n\r\n")
        await writer.drain()

        resp = await reader.read(2048)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 200 OK", resp)
        self.assertIn(b"FastWiFi", resp)
        self.assertIn(b'"status": "ok"', resp)

    async def test_api_wifi_connect_endpoint(self):
        """Verify POST /api/wifi/connect initiates connection and reports status."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        body = b'{"ssid":"FastWiFi","password":"secretpassword"}'
        req = (
            b"POST /api/wifi/connect HTTP/1.1\r\n"
            b"Host: 192.168.4.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        )
        writer.write(req)
        await writer.drain()

        resp = await reader.read(2048)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 200 OK", resp)
        self.assertIn(b'"status": "connected"', resp)

    async def test_setup_route_serves_html(self):
        """Verify GET /setup serves 200 OK with html content."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"GET /setup HTTP/1.1\r\nHost: 192.168.4.1\r\n\r\n")
        await writer.drain()

        resp = await reader.read(2048)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 200 OK", resp)
        self.assertIn(b"Content-Type: text/html", resp)


class TestAppCaptiveIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_app_enable_captive_portal(self):
        """Verify App.enable_captive_portal activates portal and routes."""
        from espmpui.app import App
        app = App(title="Provisioning Node")
        portal = app.enable_captive_portal(ap_ssid="Test-AP", ap_ip="192.168.4.1", dns_port=15354)
        self.assertIsNotNone(app.portal)
        self.assertEqual(portal.ap_ip, "192.168.4.1")

        # Start on port 0
        await app.start(host="127.0.0.1", port=0)
        port = app.server.port

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /generate_204 HTTP/1.1\r\nHost: connectivitycheck.gstatic.com\r\n\r\n")
        await writer.drain()

        resp = await reader.read(1024)
        writer.close()
        await writer.wait_closed()

        await app.portal.stop()
        await app.server.stop()

        self.assertIn(b"HTTP/1.1 302 Found", resp)


if __name__ == "__main__":
    unittest.main()
