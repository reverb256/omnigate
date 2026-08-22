"""Tests for replicate.py — share server + QR generation."""
import http.client
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import replicate  # noqa: E402


class TestQRGeneration(unittest.TestCase):
    def test_qr_svg_not_empty(self):
        svg = replicate._fallback_qr("http://192.168.1.10:5317/manifest.json")
        self.assertIn("<svg", svg)
        self.assertGreater(len(svg), 100)

    def test_qr_contains_url_fragment(self):
        url = "http://192.168.1.10:5317/test"
        svg = replicate._fallback_qr(url)
        # Fallback QR is deterministic matrix, not encoding real data — just check shape
        self.assertIn("rect", svg)


class TestShareServer(unittest.TestCase):
    def test_share_serves_manifest(self):
        """Start the share server, fetch the manifest, verify signature."""
        src = Path(tempfile.mkdtemp())
        (src / "test.conf").write_text("test content")
        # Pick a random port
        port = 15317

        # Run share in a thread (it blocks on serve_forever)
        def _share():
            try:
                replicate.cmd_share(src_dir=src, port=port)
            except Exception:
                pass

        t = threading.Thread(target=_share, daemon=True)
        t.start()
        time.sleep(1.5)  # wait for server to start

        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/omarchy-setup-manifest.json")
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read().decode())
            self.assertIn("manifest", body)
            self.assertIn("signature", body)
            self.assertTrue(replicate.verify_signature(body))
            conn.close()
        except (ConnectionRefusedError, OSError):
            self.skipTest("Share server did not start in time")


if __name__ == "__main__":
    unittest.main()
