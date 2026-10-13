import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from my_slides.browser import QA_RULES_VERSION
from my_slides.visual_review import visual_status


class VisualEvidenceTests(unittest.TestCase):
    def test_evidence_is_bound_to_deck_spec_rules_and_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "slides").mkdir()
            (base / "specs" / "units").mkdir(parents=True)
            deck = base / "slides" / "index.html"
            spec = base / "specs" / "units" / "unit.md"
            deck.write_text("deck", encoding="utf-8")
            spec.write_text("spec", encoding="utf-8")
            sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
            directory = base / ".state" / "visual" / sha(deck)[:16]
            directory.mkdir(parents=True)
            shot = directory / "desktop-p001.png"
            shot.write_bytes(b"png data")
            evidence = {"deck_sha256": sha(deck), "spec_sha256": {"unit": sha(spec)},
                        "rules_version": QA_RULES_VERSION,
                        "screenshots": [{"unit_id": "unit", "file": shot.name, "sha256": sha(shot)}]}
            (directory / "measurements.json").write_text(json.dumps({"evidence": evidence}))
            self.assertTrue(visual_status(base, "unit")["evidence_current"])
            review = {"deck_sha256": sha(deck), "spec_sha256": sha(spec),
                      "rules_version": QA_RULES_VERSION, "images": [shot.name]}
            (directory / "review-unit.json").write_text(json.dumps(review))
            self.assertTrue(visual_status(base, "unit")["agent_review_current"])
            shot.write_bytes(b"changed")
            self.assertFalse(visual_status(base, "unit")["evidence_current"])
            shot.write_bytes(b"png data")
            spec.write_text("new spec")
            self.assertFalse(visual_status(base, "unit")["agent_review_current"])
            spec.write_text("spec")
            self.assertFalse(visual_status(base, "unit", html_current=False)["evidence_current"])


if __name__ == "__main__":
    unittest.main()
