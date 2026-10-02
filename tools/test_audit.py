"""Rules over hand-written session lines. Run with `python3 -m unittest tools/test_audit.py`."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import audit  # noqa: E402

PKG = "com.example.app"


def run(*lines):
    records = [audit.parse_record(line) for line in lines]
    return audit.run_rules([r for r in records if r])


def tree(*nodes):
    """A dump of the app's window; each node is `(depth, fields)`."""
    return (
        [f"[tree] t=1 begin pkg={PKG}"]
        + [f"[tree] t=2 {'  ' * depth}{fields}" for depth, fields in nodes]
        + ["[tree] t=3 end nodes=0"]
    )


def rules(result, rule):
    return [f for f in result["findings"] if f["rule"] == rule]


class ConformanceTest(unittest.TestCase):

    def test_target_under_24dp_fails_wcag(self):
        result = run(*tree((1, "id=a class=Button text=\"Go\" clickable bounds=[0,0][40,40] size=20x20dp issues=SMALL_TARGET")))
        [f] = rules(result, "SMALL_TARGET")
        self.assertEqual(f["conformance"], "failure")
        self.assertEqual(f["wcag"], ["2.5.8"])

    def test_target_between_24_and_48dp_is_advisory(self):
        result = run(*tree((1, "id=a class=Button text=\"Go\" clickable bounds=[0,0][80,80] size=40x40dp issues=SMALL_TARGET")))
        [f] = rules(result, "SMALL_TARGET")
        self.assertEqual(f["conformance"], "advisory")

    def test_no_heading_is_advisory(self):
        result = run(*tree((1, "id=a class=TextView text=\"Hello\" bounds=[0,0][80,80] size=40x40dp")))
        [f] = rules(result, "NO_HEADING")
        self.assertEqual(f["conformance"], "advisory")

    def test_role_before_label_is_advisory(self):
        result = run(
            f"[focus] t=10 pkg={PKG} id=a class=Button bounds=[0,0][96,96] size=48x48dp",
            "[speech] t=11 Button, Send",
            f"[focus] t=5000 pkg={PKG} id=b class=Button text=\"Menu\" bounds=[0,100][96,196] size=48x48dp",
            "[speech] t=5001 Menu, Button",
        )
        [f] = rules(result, "ROLE_BEFORE_LABEL")
        self.assertEqual(f["conformance"], "advisory")
        self.assertIn("2.5.3", f["wcag"])

    def test_no_label_is_failure_and_counted_by_criterion(self):
        result = run(*tree((1, "id=a class=Button clickable bounds=[0,0][96,96] size=48x48dp issues=NO_LABEL")))
        [f] = rules(result, "NO_LABEL")
        self.assertEqual(f["conformance"], "failure")
        self.assertEqual(result["summary_by_wcag"]["4.1.2"]["failure"], 1)
        self.assertEqual(result["summary_by_wcag"]["4.1.2"]["level"], "A")

    def test_every_rule_names_known_criteria(self):
        for name, rule in audit.RULES.items():
            for criterion in rule["wcag"]:
                self.assertIn(criterion, audit.WCAG, name)


if __name__ == "__main__":
    unittest.main()
