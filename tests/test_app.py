"""Tests for the wizard UI — screen builders + honest labels."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from journey import ScanCounts, Beat, auto_advance

# Import the app module constants without triggering flet import
import ast
app_src = (REPO / "app.py").read_text()

# Extract LABELS dict from source (no flet import needed for this)
tree = ast.parse(app_src)
LABELS = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "LABELS" for t in node.targets
    ):
        # Evaluate the dict literal safely
        LABELS = ast.literal_eval(node.value)
        break


class TestLabels(unittest.TestCase):
    def test_labels_exist(self):
        self.assertIsNotNone(LABELS)

    def test_map_label_human(self):
        self.assertIn("map", LABELS)
        self.assertEqual(LABELS["map"], "Coming with you")

    def test_defer_label_human(self):
        self.assertIn("defer", LABELS)
        self.assertEqual(LABELS["defer"], "Already in Omarchy")

    def test_unknown_label_human(self):
        self.assertIn("unknown", LABELS)
        self.assertEqual(LABELS["unknown"], "Needs a decision")

    def test_no_linux_label_honest(self):
        self.assertIn("no_linux", LABELS)
        self.assertIn("Windows only", LABELS["no_linux"])

    def test_no_internal_terms_in_labels(self):
        for k, v in LABELS.items():
            if not v:
                continue
            for forbidden in ("defer", "skip", "noise", "real_unknown"):
                if k == forbidden:
                    continue  # key name is fine
                self.assertNotIn(forbidden, v.lower(),
                                 f"label for {k} leaks internals: {v}")


class TestScreenContent(unittest.TestCase):
    def test_look_screen_text_in_source(self):
        self.assertIn("We found your programs", app_src)
        self.assertIn("Your old Windows stays", app_src)

    def test_choose_screen_text_in_source(self):
        self.assertIn("Choose what to bring", app_src)
        self.assertIn("Pre-selected", app_src)

    def test_keep_screen_mentions_dual_boot(self):
        self.assertIn("next to", app_src.lower())
        self.assertIn("do not format", app_src.lower())

    def test_land_screen_super_space(self):
        self.assertIn("Super+Space", app_src)

    def test_no_ai_jargon_in_source(self):
        for forbidden in ("LLM", "Needle", "chatbot", "model", "fine-tune"):
            self.assertNotIn(forbidden, app_src,
                             f"wizard source contains forbidden word: {forbidden}")


if __name__ == "__main__":
    unittest.main()
