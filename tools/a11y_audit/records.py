"""The log's records: one line per focus, utterance, window change or tree node."""

import re
from pathlib import Path

RECORD = re.compile(r"^\[(\w+)\] t=(\d+) ?(.*)$")
TOKEN = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)|(\S+)')
BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
# A log entry holds about 4 KB, so the app splits a longer record: the rest follows in `[more]` entries.
MORE = re.compile(r"^\[more\] t=\d+ (.*)$")


def unquote(value):
    if not (value.startswith('"') and value.endswith('"')):
        return value
    out, chars = [], iter(value[1:-1])
    for c in chars:
        if c == "\\":
            nxt = next(chars, "")
            out.append("\n" if nxt == "n" else nxt)
        else:
            out.append(c)
    return "".join(out)


def parse_fields(text):
    """`key=value` pairs plus bare flags (`heading`, `clickable`, `FOCUSED`…)."""
    fields, flags = {}, []
    for key, value, flag in TOKEN.findall(text):
        if key:
            fields[key] = unquote(value)
        else:
            flags.append(flag)
    fields["flags"] = flags
    fields["issues"] = fields["issues"].split(",") if "issues" in fields else []
    if m := BOUNDS.fullmatch(fields.get("bounds", "")):
        fields["bounds"] = [int(v) for v in m.groups()]
    return fields


def parse_record(line):
    m = RECORD.match(line)
    if not m:
        return None
    kind, t, rest = m.group(1), int(m.group(2)), m.group(3)
    record = {"kind": kind, "t": t}
    if kind == "speech":
        record["text"] = unquote(rest.strip())
    elif kind == "tree":
        stripped = rest.lstrip(" ")
        if stripped.startswith(("begin", "end", "no active window")):
            record["marker"] = stripped
        else:
            record["depth"] = (len(rest) - len(stripped)) // 2
            record.update(parse_fields(stripped))
    else:
        record.update(parse_fields(rest))
    return record


def joined(lines):
    """The log's lines with each record the app split over `[more]` entries put back together."""
    result = []
    for line in lines:
        more = MORE.match(line)
        if more and result:
            result[-1] += more.group(1)
        else:
            result.append(line)
    return result


def parse_lines(text):
    return [r for r in map(parse_record, joined(text.splitlines())) if r]


def parse_session(path):
    return parse_lines(Path(path).read_text(encoding="utf-8"))


def label(node):
    return (node.get("text") or node.get("desc") or "").strip()


def dumps(records):
    """Each `[tree]` dump as (fields of its begin marker, nodes), in log order."""
    result, current = [], None
    for r in records:
        if r["kind"] != "tree":
            continue
        marker = r.get("marker", "")
        if marker.startswith("begin"):
            current = (parse_fields(marker[len("begin"):]), [])
            result.append(current)
        elif marker:
            current = None
        elif current is not None:
            current[1].append(r)
    return result
