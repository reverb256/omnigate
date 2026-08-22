"""Tests for wizard_label mapping."""
import unittest
from verbs import wizard_label, leftover_verdict, WIZARD_LABELS


class TestWizardLabel(unittest.TestCase):
    def test_skip_label(self):
        self.assertEqual(wizard_label("skip"), "Stays on your old drive (games)")

    def test_defer_label(self):
        self.assertEqual(wizard_label("defer"), "Omarchy already has this")

    def test_containerize_label(self):
        self.assertEqual(wizard_label("containerize"), "Runs in a Windows box (later)")

    def test_no_linux_label(self):
        self.assertEqual(wizard_label("no_linux"), "Windows only — boot Windows")

    def test_real_unknown_label(self):
        self.assertEqual(wizard_label("real_unknown"), "Needs a decision")

    def test_unknown_verb_falls_back(self):
        self.assertEqual(wizard_label("bogus"), "Needs a decision")

    def test_carenado_windows_only(self):
        v = leftover_verdict("Carenado C172N Flight Sim", "windows")
        self.assertEqual(v["verb"], "no_linux")
        self.assertEqual(v["wizard_label"], "Windows only — boot Windows")

    def test_cyberpunk_skip(self):
        v = leftover_verdict("Cyberpunk 2077", "windows")
        self.assertEqual(v["verb"], "skip")
        self.assertEqual(v["wizard_label"], "Stays on your old drive (games)")

    def test_adobe_containerize(self):
        v = leftover_verdict("Adobe Photoshop 2026", "windows")
        self.assertEqual(v["verb"], "containerize")
        self.assertEqual(v["wizard_label"], "Runs in a Windows box (later)")

    def test_all_labels_no_internal_terms(self):
        for verb, label in WIZARD_LABELS.items():
            if not label:
                continue
            for leak in ("real_unknown", "table hit", "no Linux path"):
                self.assertNotIn(leak, label.lower(),
                                 f"label for {verb} leaks: {label}")


if __name__ == "__main__":
    unittest.main()
