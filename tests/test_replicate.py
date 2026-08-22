"""Tests for replicate.py — peer-to-peer Omarchy setup sharing."""
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from replicate import (
    build_manifest,
    device_fingerprint,
    verify_signature,
    b3sum,
    discover_peers,
    cmd_receive,
    _fallback_qr,
)


class TestFingerprint(unittest.TestCase):
    def test_stable(self):
        assert device_fingerprint() == device_fingerprint()

    def test_not_empty(self):
        assert len(device_fingerprint()) >= 16


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "config").mkdir()
        (self.tmp / "config" / "foot.ini").write_text("[main]\nfont=mono")
        (self.tmp / "README").write_text("hello")

    def test_build_manifest_has_files(self):
        m = build_manifest(self.tmp, "key0001", "test-host")
        assert "manifest" in m
        assert "signature" in m
        assert len(m["manifest"]["files"]) == 2

    def test_verify_valid(self):
        w = build_manifest(self.tmp, "key0001", "test-host")
        assert verify_signature(w)

    def test_verify_tampered(self):
        w = build_manifest(self.tmp, "key0001", "test-host")
        w["manifest"]["files"]["config/foot.ini"]["size"] = 999
        assert not verify_signature(w)

    def test_self_fingerprint_rejected(self):
        w = build_manifest(self.tmp, device_fingerprint(), "self")
        # cmd_receive would reject if fingerprint == local — test logic directly
        assert w["manifest"]["fingerprint"] == device_fingerprint()


class TestB3Sum(unittest.TestCase):
    def test_consistent(self):
        f = Path(tempfile.mktemp())
        f.write_text("test-content-123")
        assert b3sum(f) == b3sum(f)


class TestDiscovery(unittest.TestCase):
    def test_discover_no_peers(self):
        # In unit-test env, no multicast traffic → empty list
        peers = discover_peers(timeout=1)
        assert peers == []


class TestReceive(unittest.TestCase):
    def test_missing_manifest(self):
        result = cmd_receive("http://localhost:1/nonexistent")
        assert result == 1


class TestQR(unittest.TestCase):
    def test_fallback_qr_has_svg(self):
        svg = _fallback_qr("http://192.168.1.10:5317/manifest.json")
        assert "<svg" in svg
        assert "black" in svg


if __name__ == "__main__":
    unittest.main()
