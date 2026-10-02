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


class NodeRulesTest(unittest.TestCase):

    def test_clickable_without_role_is_flagged(self):
        result = run(*tree((1, "id=card class=View clickable bounds=[0,0][96,96] size=48x48dp")))
        [f] = rules(result, "NO_ROLE")
        self.assertEqual(f["node"]["id"], "card")
        self.assertEqual(f["conformance"], "failure")

    def test_role_on_a_role_only_child_is_advisory(self):
        result = run(*tree(
            (1, "id=card class=View clickable bounds=[0,0][96,96] size=48x48dp"),
            (2, "id=- class=Button bounds=[0,0][96,96] size=48x48dp"),
        ))
        [f] = rules(result, "NO_ROLE")
        self.assertEqual(f["conformance"], "advisory")

    def test_role_read_as_content_is_advisory(self):
        result = run(
            f"[focus] t=10 pkg={PKG} id=stop class=View clickable bounds=[0,0][96,96] size=48x48dp",
            "[speech] t=11 Button, Stop",
            f"[focus] t=5000 pkg={PKG} id=menu class=Button text=\"Menu\" clickable bounds=[0,100][96,196] size=48x48dp",
            "[speech] t=5001 Menu, Button",
        )
        [f] = rules(result, "NO_ROLE")
        self.assertEqual(f["conformance"], "advisory")
        self.assertIn("'Button'", f["detail"])

    def test_button_or_role_description_has_a_role(self):
        result = run(*tree(
            (1, "id=a class=Button text=\"Go\" clickable bounds=[0,0][96,96] size=48x48dp"),
            (1, "id=b class=View text=\"Shoes\" role=\"Tab\" clickable bounds=[0,0][96,96] size=48x48dp"),
        ))
        self.assertEqual(rules(result, "NO_ROLE"), [])

    def test_checkable_and_selected_conflict(self):
        result = run(*tree((1, "id=tab class=View text=\"Women\" role=\"Tab\" checked=true selected clickable bounds=[0,0][96,96] size=48x48dp")))
        self.assertEqual(len(rules(result, "CONFLICTING_STATE")), 1)

    def test_selected_alone_does_not_conflict(self):
        result = run(*tree((1, "id=tab class=View text=\"Women\" role=\"Tab\" selected clickable bounds=[0,0][96,96] size=48x48dp")))
        self.assertEqual(rules(result, "CONFLICTING_STATE"), [])

    def test_clickable_inside_clickable_is_nested(self):
        result = run(*tree(
            (1, "id=card class=Button clickable bounds=[0,0][400,400] size=200x200dp"),
            (3, "id=add class=Button desc=\"Add\" clickable bounds=[300,300][396,396] size=48x48dp"),
            (1, "id=next class=Button text=\"Next\" clickable bounds=[0,500][96,596] size=48x48dp"),
        ))
        [f] = rules(result, "NESTED_ACTIONABLE")
        self.assertEqual(f["node"]["id"], "card")
        self.assertIn("'Add'", f["detail"])


class RawTextTest(unittest.TestCase):

    def test_resource_key_spoken(self):
        result = run(f"[focus] t=10 pkg={PKG} id=a class=View bounds=[0,0][96,96] size=48x48dp", "[speech] t=11 accessibility.loading.text")
        self.assertEqual(len(rules(result, "RAW_TEXT_SPOKEN")), 1)

    def test_html_in_tree_text(self):
        result = run(*tree((1, "id=a class=TextView text=\"Hello<br>world\" bounds=[0,0][96,96] size=48x48dp")))
        [f] = rules(result, "RAW_TEXT_SPOKEN")
        self.assertIn("<br>", f["detail"])

    def test_domains_and_prices_are_not_raw(self):
        self.assertIsNone(audit.raw_text("Visit shop.example.com today"))
        self.assertIsNone(audit.raw_text("Price 1.299,99 €"))
        self.assertIsNone(audit.raw_text("Rock & roll"))


if __name__ == "__main__":
    unittest.main()
