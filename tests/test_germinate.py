import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("germinate_app", ROOT / "germinate.py")
APP = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class GerminateTests(unittest.TestCase):
    def setUp(self):
        self.rules = APP.load_json(ROOT / "config" / "rules.json")
        self.source = {"name": "Test", "collector_type": "html"}
        self.checked_at = "2026-08-30T00:00:00+00:00"

    def test_relevant_grant_is_candidate(self):
        link = APP.Link("Regenerative ecosystem restoration grant", "https://example.org/call")
        result = APP.classify(link, self.source, self.rules, self.checked_at)
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, "candidate")

    def test_loan_is_rejected(self):
        link = APP.Link("Sustainable agriculture loan", "https://example.org/loan")
        result = APP.classify(link, self.source, self.rules, self.checked_at)
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, "rejected")

    def test_irrelevant_navigation_is_ignored(self):
        link = APP.Link("Contact us", "https://example.org/contact")
        self.assertIsNone(APP.classify(link, self.source, self.rules, self.checked_at))

    def test_interactive_source_is_flagged(self):
        source = {"name": "Search portal", "collector_type": "interactive_search"}
        link = APP.Link("Rural sustainability grant", "https://example.org/search")
        result = APP.classify(link, source, self.rules, self.checked_at)
        self.assertEqual(result.decision, "needs_specialized_collector")

    def test_duplicate_urls_are_removed(self):
        first = APP.Result("Source", "html", "First", "https://example.org/call", "review", 1, "", "", "", self.checked_at, "")
        better = APP.Result("Source", "html", "Better", "https://example.org/call", "candidate", 5, "", "", "", self.checked_at, "")
        results = APP.deduplicate([first, better])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Better")


if __name__ == "__main__":
    unittest.main()
