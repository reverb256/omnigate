"""Tests for mapper/map.py — classify()."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestClassify(unittest.TestCase):
    def test_classify_empty(self):
        from mapper.map import classify
        result = classify([])
        self.assertEqual(result, {"defer": [], "map": [], "unknown": []})

    def test_classify_defer(self):
        from mapper.map import classify
        matches = [{"source_app": "foot", "target": {"type": "defer_omarchy", "name": "foot"}}]
        result = classify(matches)
        self.assertEqual(len(result["defer"]), 1)
        self.assertEqual(result["defer"][0]["source_app"], "foot")

    def test_classify_map(self):
        from mapper.map import classify
        matches = [{"source_app": "git", "target": {"type": "pkg", "name": "git"}}]
        result = classify(matches)
        self.assertEqual(len(result["map"]), 1)
        self.assertEqual(result["map"][0]["source_app"], "git")

    def test_classify_mixed(self):
        from mapper.map import classify
        matches = [
            {"source_app": "foot", "target": {"type": "defer_omarchy", "name": "foot"}},
            {"source_app": "git", "target": {"type": "pkg", "name": "git"}},
        ]
        result = classify(matches)
        self.assertEqual(len(result["defer"]), 1)
        self.assertEqual(len(result["map"]), 1)


if __name__ == "__main__":
    unittest.main()
