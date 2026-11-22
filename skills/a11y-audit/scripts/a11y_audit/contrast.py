"""Text contrast measured on a screenshot, with a PNG reader from the standard library."""

import zlib
from collections import Counter
from pathlib import Path

# Below this share of the node's pixels the background is an image or a gradient: contrast is not measured.
UNIFORM_BACKGROUND = 0.4


def read_png(path):
    """(width, height, rows of RGB tuples) of an 8-bit, non-interlaced RGB or RGBA PNG, as screencap writes."""
    data = Path(path).read_bytes()
    pos, chunks, header = 8, [], None
    while pos < len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            header = body
        elif kind == b"IDAT":
            chunks.append(body)
        pos += 12 + length
    width, height = int.from_bytes(header[0:4], "big"), int.from_bytes(header[4:8], "big")
    depth, color, interlace = header[8], header[9], header[12]
    if depth != 8 or color not in (2, 6) or interlace:
        raise ValueError("only 8-bit non-interlaced RGB/RGBA PNGs are supported")
    channels = 4 if color == 6 else 3
    raw, stride = zlib.decompress(b"".join(chunks)), width * channels
    rows, prev = [], bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        if kind == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif kind == 2:
            line = bytearray((a + b) & 0xFF for a, b in zip(line, prev))
        elif kind == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif kind == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b, c = prev[i], prev[i - channels] if i >= channels else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        rows.append(line)
        prev = line
    return width, height, [[tuple(row[x:x + 3]) for x in range(0, stride, channels)] for row in rows]


def luminance(rgb):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_contrast(pixels, bounds):
    """(background, foreground, ratio) inside the bounds, or None when the background is not uniform.
    The background is the most frequent color; the text is, among the next most frequent, the one that
    contrasts most with it (anti-aliasing leaves in-between colors)."""
    left, top, right, bottom = bounds
    top, bottom = max(top, 0), min(bottom, len(pixels))
    left, right = max(left, 0), min(right, len(pixels[0]) if pixels else 0)
    if right - left < 4 or bottom - top < 4:
        return None
    step = 2 if (right - left) * (bottom - top) > 40000 else 1
    exact = Counter(pixels[y][x] for y in range(top, bottom, step) for x in range(left, right, step))
    # Near colors are counted together; each group is measured by its most frequent exact color.
    groups, representative = Counter(), {}
    for color, n in exact.most_common():
        key = tuple(v >> 3 for v in color)
        groups[key] += n
        representative.setdefault(key, color)
    (key, n), *others = groups.most_common(4)
    if n < UNIFORM_BACKGROUND * sum(groups.values()) or not others:
        return None
    background = representative[key]
    foreground = max((representative[k] for k, _ in others), key=lambda color: contrast_ratio(color, background))
    return background, foreground, contrast_ratio(foreground, background)
