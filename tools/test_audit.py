"""Rules over hand-written session lines. Run with `python3 -m unittest tools/test_audit.py`."""

import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import audit  # noqa: E402

PKG = "com.example.app"


def run(*lines):
    records = [audit.parse_record(line) for line in lines]
    return audit.run_rules([r for r in records if r])


def tree(*nodes, window=None):
    """A dump of the app's window; each node is `(depth, fields)`. `window` writes the newer begin marker."""
    title = f' window="{window}"' if window is not None else ""
    return (
        [f"[tree] t=1 begin pkg={PKG}{title}"]
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


class StructureTest(unittest.TestCase):

    def test_list_declaring_fewer_items_than_it_shows(self):
        result = run(*tree(
            (1, "id=options class=View collection=2x1 bounds=[0,0][400,300] size=200x150dp"),
            (2, "id=- class=Button text=\"A\" item=0,0 clickable bounds=[0,0][400,96] size=200x48dp"),
            (2, "id=- class=Button text=\"B\" item=1,0 clickable bounds=[0,100][400,196] size=200x48dp"),
            (2, "id=- class=Button text=\"C\" clickable bounds=[0,200][400,296] size=200x48dp"),
        ))
        [f] = rules(result, "LIST_SEMANTICS")
        self.assertIn("'C'", f["detail"])

    def test_scrollable_list_is_skipped(self):
        result = run(*tree(
            (1, "id=feed class=View collection=50x1 scrollable bounds=[0,0][400,300] size=200x150dp"),
            (2, "id=- class=Button text=\"A\" item=0,0 clickable bounds=[0,0][400,96] size=200x48dp"),
        ))
        self.assertEqual(rules(result, "LIST_SEMANTICS"), [])

    def test_list_scrolled_by_a_pager_inside_is_skipped(self):
        """An image pager in a product card: the card declares 6 images, the pager inside only has the visible one."""
        result = run(*tree(
            (1, "id=- class=View collection=1x6 bounds=[0,0][400,300] size=200x150dp"),
            (2, "id=- class=View collection=1x2147483647 scrollable bounds=[0,0][400,300] size=200x150dp"),
            (3, "id=image class=View item=0,2 bounds=[0,0][400,300] size=200x150dp"),
        ))
        self.assertEqual(rules(result, "LIST_SEMANTICS"), [])

    def test_single_item_list_is_reported_as_such(self):
        """A one-image pager inside a card: TalkBack says "List" in the card's speech for nothing to navigate."""
        result = run(*tree(
            (1, "id=- class=View clickable bounds=[0,0][400,500] size=200x250dp"),
            (2, "id=- class=View collection=1x1 bounds=[0,0][400,300] size=200x150dp"),
            (3, "id=image class=View bounds=[0,0][400,300] size=200x150dp"),
        ))
        [f] = rules(result, "LIST_SEMANTICS")
        self.assertIn("single item", f["detail"])

    def test_screen_without_any_title(self):
        result = run(*tree((1, "id=a class=TextView text=\"Hi\" heading bounds=[0,0][96,96] size=48x48dp"), window=""))
        self.assertEqual(len(rules(result, "SCREEN_TITLE")), 1)

    def test_pane_title_counts_as_title(self):
        result = run(*tree((1, "id=a class=View pane=\"Chat\" bounds=[0,0][96,96] size=48x48dp"), window=""))
        self.assertEqual(rules(result, "SCREEN_TITLE"), [])
        self.assertEqual(result["titles"], ["Chat"])

    def test_older_log_without_window_field_is_not_judged(self):
        result = run(*tree((1, "id=a class=TextView text=\"Hi\" bounds=[0,0][96,96] size=48x48dp")))
        self.assertEqual(rules(result, "SCREEN_TITLE"), [])

    def test_focus_moved_by_the_app_after_activation(self):
        result = run(
            *tree((1, "id=opt class=Button text=\"Shipping\" clickable bounds=[0,800][400,896] size=200x48dp"), window="Chat"),
            f"[focus] t=10 pkg={PKG} id=opt class=Button text=\"Shipping\" clickable bounds=[0,800][400,896] size=200x48dp",
            f"[click] t=500 pkg={PKG} id=opt class=Button text=\"Shipping\" clickable bounds=[0,800][400,896] size=200x48dp",
            f"[focus] t=900 pkg={PKG} id=close class=Button desc=\"Close\" clickable bounds=[0,0][96,96] size=48x48dp",
        )
        [f] = rules(result, "FOCUS_MOVED_AFTER_ACTION")
        self.assertIn("'Close'", f["detail"])
        self.assertIn("400dp above", f["detail"])

    def test_keyboard_opening_after_activation_still_counts(self):
        """The keyboard is another app's window: it doesn't make the focus move legitimate."""
        result = run(
            *tree((1, "id=- class=View clickable bounds=[0,800][400,896] size=200x48dp"), window="Chat"),
            f"[click] t=500 pkg={PKG} id=- class=View clickable bounds=[0,800][400,896] size=200x48dp",
            "[window] t=600 pkg=com.example.keyboard class=android.inputmethodservice.SoftInputWindow text=\"\"",
            f"[focus] t=700 pkg={PKG} id=- class=EditText text=\"\" clickable bounds=[0,900][400,996] size=200x48dp",
        )
        [f] = rules(result, "FOCUS_MOVED_AFTER_ACTION")
        self.assertIn("View at [0,800][400,896]", f["detail"])
        self.assertIn("EditText at [0,900][400,996]", f["detail"])
        self.assertIn("50dp below", f["detail"])

    def test_new_window_after_activation_is_expected(self):
        result = run(
            f"[click] t=500 pkg={PKG} id=opt class=Button text=\"Open\" clickable bounds=[0,800][400,896] size=200x48dp",
            f"[window] t=600 pkg={PKG} class=android.app.Dialog text=\"Details\"",
            f"[focus] t=900 pkg={PKG} id=close class=Button desc=\"Close\" clickable bounds=[0,0][96,96] size=48x48dp",
        )
        self.assertEqual(rules(result, "FOCUS_MOVED_AFTER_ACTION"), [])

    def test_text_that_appeared_without_being_spoken(self):
        lines = (
            tree((1, "id=a class=TextView text=\"Hi\" bounds=[0,0][96,96] size=48x48dp"), window="Chat")
            + tree(
                (1, "id=a class=TextView text=\"Hi\" bounds=[0,0][96,96] size=48x48dp"),
                (1, "id=b class=TextView text=\"Your order is ready\" bounds=[0,100][96,196] size=48x48dp"),
                window="Chat",
            )
        )
        self.assertEqual(run(*lines)["appeared"], ["Your order is ready"])
        spoken = run(*lines, "[speech] t=50 \"your order  is ready\"")
        self.assertEqual(spoken["appeared"], [])

    def test_spoken_without_the_sender_prefix(self):
        self.assertTrue(audit.was_spoken("Bot: Here are the delivery options", audit.normalized("Here are the delivery options")))


def write_png(path, pixels):
    """RGBA PNG with each row using the next of the five filters, to exercise every decoding path."""
    width, channels = len(pixels[0]), 4
    raw, prev = bytearray(), bytes(width * channels)
    for y, row in enumerate(pixels):
        line = bytes(v for rgb in row for v in (*rgb, 255))
        kind, out = y % 5, bytearray()
        for i, v in enumerate(line):
            a = line[i - channels] if i >= channels else 0
            b, c = prev[i], prev[i - channels] if i >= channels else 0
            pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
            predictor = (0, a, b, (a + b) >> 1, a if pa <= pb and pa <= pc else b if pb <= pc else c)[kind]
            out.append((v - predictor) & 0xFF)
        raw += bytes([kind]) + out
        prev = line

    def chunk(kind, body):
        return len(body).to_bytes(4, "big") + kind + body + zlib.crc32(kind + body).to_bytes(4, "big")

    header = width.to_bytes(4, "big") + len(pixels).to_bytes(4, "big") + bytes([8, 6, 0, 0, 0])
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


def text_block(background, text, width=40, height=20):
    """A background with a horizontal bar of text color in the middle."""
    return [[text if 8 <= y < 12 and 4 <= x < 36 else background for x in range(width)] for y in range(height)]


class ContrastTest(unittest.TestCase):

    def test_png_round_trip_through_every_filter(self):
        pixels = [[((x * 37 + y) % 256, (y * 11) % 256, (x * y) % 256) for x in range(13)] for y in range(10)]
        with tempfile.TemporaryDirectory() as folder:
            write_png(Path(folder) / "s.png", pixels)
            _, _, decoded = audit.read_png(Path(folder) / "s.png")
        self.assertEqual(decoded, pixels)

    def run_with_screenshot(self, pixels):
        with tempfile.TemporaryDirectory() as folder:
            write_png(Path(folder) / "screen-end.png", pixels)
            lines = tree((1, "id=a class=TextView text=\"Sale\" heading bounds=[0,0][40,20] size=20x10dp"), window="Shop")
            records = [audit.parse_record(line) for line in lines]
            return audit.run_rules(records, Path(folder) / "screen-end.png")

    def test_light_grey_on_white_fails(self):
        [f] = rules(self.run_with_screenshot(text_block((255, 255, 255), (200, 200, 200))), "TEXT_CONTRAST")
        self.assertEqual(f["conformance"], "failure")

    def test_mid_grey_on_white_passes_only_if_large(self):
        [f] = rules(self.run_with_screenshot(text_block((255, 255, 255), (130, 130, 130))), "TEXT_CONTRAST")
        self.assertEqual(f["conformance"], "advisory")

    def test_black_on_white_passes(self):
        self.assertEqual(rules(self.run_with_screenshot(text_block((255, 255, 255), (0, 0, 0))), "TEXT_CONTRAST"), [])

    def test_wcag_reference_ratios(self):
        self.assertAlmostEqual(audit.contrast_ratio((0, 0, 0), (255, 255, 255)), 21, places=1)
        self.assertAlmostEqual(audit.contrast_ratio((118, 118, 118), (255, 255, 255)), 4.54, places=2)


class KeyboardTest(unittest.TestCase):
    A = "id=a class=Button text=\"A\" clickable bounds=[0,0][20,10] size=10x5dp"
    B = "id=b class=Button text=\"B\" clickable bounds=[20,0][40,10] size=10x5dp"
    C = "id=c class=Button text=\"C\" clickable bounds=[0,10][20,20] size=10x5dp"

    def run_pass(self, focus_per_step, ring_on=("a", "b"), extra=()):
        """One dump and one screenshot per step; the focused button gets a dark ring if listed in ring_on."""
        boxes = {"a": (0, 0, 20, 10), "b": (20, 0, 40, 10), "c": (0, 10, 20, 20)}
        lines = []
        with tempfile.TemporaryDirectory() as folder:
            steps = Path(folder) / "keyboard"
            steps.mkdir()
            for i, focused in enumerate(focus_per_step):
                nodes = [(1, f + (" INPUT_FOCUSED" if f.startswith(f"id={focused} ") else "")) for f in (self.A, self.B, self.C)]
                lines += tree(*nodes, window="Shop")
                pixels = [[(255, 255, 255)] * 40 for _ in range(20)]
                if focused in ring_on:
                    left, top, right, bottom = boxes[focused]
                    for x in range(left, right):
                        pixels[top][x] = pixels[bottom - 1][x] = (0, 0, 0)
                write_png(steps / f"step-{i:02}.png", pixels)
            records = [audit.parse_record(line) for line in lines + list(extra)]
            return audit.run_keyboard_rules(records, steps)

    def test_full_cycle_reaching_everything_with_visible_focus(self):
        result = self.run_pass([None, "a", "b", "c", "a"], ring_on=("a", "b", "c"))
        self.assertEqual(result["keyboard"]["ending"], "cycle")
        self.assertEqual(result["findings"], [])

    def test_focus_without_visible_change(self):
        result = self.run_pass([None, "a", "b", "c", "a"], ring_on=("a", "b"))
        [f] = rules(result, "FOCUS_NOT_VISIBLE")
        self.assertEqual(f["node"]["id"], "c")

    def test_stop_outside_the_accessibility_tree_with_no_visible_change(self):
        result = self.run_pass([None, "a", None, "b", None, "a"], ring_on=("a", "b"))
        [f] = rules(result, "FOCUS_NOT_VISIBLE")
        self.assertIsNone(f["node"])
        self.assertIn("steps 2, 4", f["detail"])

    def test_element_that_lost_focus_right_away(self):
        reset = f"[input] t=9 pkg={PKG} " + self.C
        result = self.run_pass([None, "a", "b", "a"], extra=[reset])
        [f] = rules(result, "KEYBOARD_UNREACHABLE")
        self.assertIn("lost it", f["detail"])

    def test_element_skipped_in_a_cycle(self):
        result = self.run_pass([None, "a", "b", "a"])
        [f] = rules(result, "KEYBOARD_UNREACHABLE")
        self.assertEqual(f["node"]["id"], "c")
        self.assertIn("full TAB cycle", f["detail"])

    def test_focus_that_stops_moving_points_to_a_trap(self):
        result = self.run_pass([None, "a", "b", "b", "b"])
        self.assertEqual(result["keyboard"]["ending"], "stuck")
        [f] = rules(result, "KEYBOARD_UNREACHABLE")
        self.assertIn("2.1.2", f["detail"])


class AtfTest(unittest.TestCase):
    SALE = "id=a class=TextView text=\"Sale\" bounds=[0,0][40,20] size=20x10dp"

    def atf(self, check, kind="ERROR", element="id=a class=TextView bounds=[0,0][40,20]"):
        return f'[atf] t=20 check={check} type={kind} {element} msg="Some message"'

    def test_error_takes_the_table_conformance_and_the_tree_node(self):
        result = run(*tree((1, self.SALE)), self.atf("TextContrastCheck"), "[atf] t=21 end results=1")
        [f] = rules(result, "ATF:TextContrastCheck")
        self.assertEqual((f["conformance"], f["wcag"], f["source"]), ("failure", ["1.4.3"], "atf"))
        self.assertEqual(f["node"]["text"], "Sale")
        self.assertEqual(f["detail"], "Some message")
        self.assertEqual(result["atf"], {"results": "1"})

    def test_warning_is_advisory(self):
        [f] = rules(run(*tree((1, self.SALE)), self.atf("TextContrastCheck", "WARNING")), "ATF:TextContrastCheck")
        self.assertEqual(f["conformance"], "advisory")

    def test_touch_target_follows_wcag_size(self):
        small = "id=a class=Button text=\"Go\" clickable bounds=[0,0][40,40] size=20x20dp"
        medium = "id=a class=Button text=\"Go\" clickable bounds=[0,0][40,40] size=40x40dp"
        element = "id=a class=Button bounds=[0,0][40,40]"
        [f] = rules(run(*tree((1, small)), self.atf("TouchTargetSizeCheck", element=element)), "ATF:TouchTargetSizeCheck")
        self.assertEqual(f["conformance"], "failure")
        [f] = rules(run(*tree((1, medium)), self.atf("TouchTargetSizeCheck", element=element)), "ATF:TouchTargetSizeCheck")
        self.assertEqual(f["conformance"], "advisory")

    def test_result_without_element(self):
        [f] = rules(run(*tree((1, self.SALE)), self.atf("TraversalOrderCheck", element="")), "ATF:TraversalOrderCheck")
        self.assertIsNone(f["node"])

    def test_matches_an_element_without_id_by_bounds(self):
        icon = "id=- class=View clickable bounds=[0,0][96,96] size=48x48dp issues=NO_LABEL"
        result = run(*tree((1, icon)), self.atf("SpeakableTextPresentCheck", element="id=- class=View bounds=[0,0][96,96]"))
        [ours] = rules(result, "NO_LABEL")
        self.assertEqual(ours["overlaps"], "ATF:SpeakableTextPresentCheck")
        self.assertEqual(len(rules(result, "ATF:SpeakableTextPresentCheck")), 1)

    def test_contrast_measured_by_atf_is_not_measured_again(self):
        with tempfile.TemporaryDirectory() as folder:
            write_png(Path(folder) / "screen-end.png", text_block((255, 255, 255), (200, 200, 200)))
            lines = tree((1, self.SALE)) + [self.atf("TextContrastCheck")]
            result = audit.run_rules([audit.parse_record(line) for line in lines], Path(folder) / "screen-end.png")
        self.assertEqual(rules(result, "TEXT_CONTRAST"), [])
        self.assertEqual(len(rules(result, "ATF:TextContrastCheck")), 1)

    def test_skipped_contrast_is_reported(self):
        end = '[atf] t=21 end results=0 skipped=contrast reason="no screenshot below API 30"'
        result = run(*tree((1, self.SALE)), end)
        self.assertEqual(result["atf"]["reason"], "no screenshot below API 30")

    def test_older_captures_have_no_atf(self):
        self.assertIsNone(run(*tree((1, self.SALE)))["atf"])


if __name__ == "__main__":
    unittest.main()
