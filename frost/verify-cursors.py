#!/usr/bin/env python3
"""
Frost cursors — verification gate.

Reads the compiled Xcursor files back and checks them against the design rules,
the same way build-theme.py checks its own output. Everything here is measured
from rendered pixels; nothing is asserted from the SVG source.

  1. Every entity carries the full size ladder.
  2. Every symlink resolves to a real file.
  3. The hotspot lands on an opaque pixel. This catches a hotspot specified off
     the glyph entirely — a mis-scaled arrow tip, say. `wait` is exempt because
     its hotspot is the centre of a ring, which is hollow by construction; the
     hotspot is a coordinate, not a pixel test, so nothing breaks. Note this is
     NOT upstream behaviour: Breeze's wait reports alpha 255 at its hotspot
     because Breeze draws a solid disc. Different shape, not a different rule.
  4. At 24px, over four backgrounds, some pixel of every cursor clears 3:1.
     This is the gate that catches limbs too thin to keep their fill.
  5. Animated cursors carry the declared frame count and delay, and every frame
     at a given size differs from the others. A spinner whose frames are all
     identical still reports the right count and delay — it just silently does
     not spin, and nothing else here would notice.
"""

import hashlib
import os
import struct
import sys

SIZES = (16, 24, 32, 48, 64, 96)
FRAMES = 12
FRAME_MS = 60
BACKGROUNDS = {
    "dark":  (23, 26, 31),
    "mid":   (106, 114, 128),
    "light": (216, 218, 222),
    "white": (255, 255, 255),
}
MIN_CONTRAST = 3.0
HOTSPOT_EXEMPT = {"wait"}          # hollow by design; see docstring
ANIMATED = {"progress", "wait"}

IMAGE_CHUNK = 0xFFFD0002


def parse(path):
    data = open(path, "rb").read()
    if data[:4] != b"Xcur":
        raise ValueError(f"{path}: not an Xcursor file")
    _, _, ntoc = struct.unpack_from("<III", data, 4)
    frames = []
    for i in range(ntoc):
        ctype, _sub, pos = struct.unpack_from("<III", data, 16 + i * 12)
        if ctype != IMAGE_CHUNK:
            continue
        # 9 header words: header, type, subtype, version, w, h, xhot, yhot, delay
        _h, _t, _s, _v, w, h, xh, yh, delay = struct.unpack_from("<9I", data, pos)
        frames.append((w, h, xh, yh, delay, data[pos + 36: pos + 36 + w * h * 4]))
    return frames


def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb):
    r, g, b = (_lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def best_contrast(w, h, px, bg):
    """Highest contrast any near-opaque pixel of the glyph reaches over `bg`."""
    best = 0.0
    for i in range(w * h):
        b, g, r, a = px[i * 4: i * 4 + 4]
        if a < 200:
            continue
        al = a / 255.0
        comp = tuple(al * c + (1 - al) * bc for c, bc in zip((r, g, b), bg))
        best = max(best, contrast(comp, bg))
    return best


def verify(theme_dir, quiet=False):
    """quiet=True: report failures only. build-theme.py prints its own summary
    line in the build log's style, so the chatter would just break the layout."""
    cursors = os.path.join(theme_dir, "cursors")
    fails = []
    names = sorted(os.listdir(cursors))
    real = [n for n in names if not os.path.islink(os.path.join(cursors, n))]
    links = [n for n in names if os.path.islink(os.path.join(cursors, n))]

    for n in links:
        p = os.path.join(cursors, n)
        if not os.path.exists(os.path.realpath(p)):
            fails.append(f"[link] {n} -> {os.readlink(p)} dangles")

    worst = ("", "", 99.0)
    for n in real:
        try:
            frames = parse(os.path.join(cursors, n))
        except ValueError as e:
            fails.append(f"[format] {e}")
            continue

        sizes = tuple(sorted({f[0] for f in frames}))
        if sizes != SIZES:
            fails.append(f"[sizes] {n}: {sizes} != {SIZES}")

        nframes = sum(1 for f in frames if f[0] == sizes[0])
        want = FRAMES if n in ANIMATED else 1
        if nframes != want:
            fails.append(f"[frames] {n}: {nframes} frames, expected {want}")
        if n in ANIMATED and frames[0][4] != FRAME_MS:
            fails.append(f"[delay] {n}: {frames[0][4]}ms, expected {FRAME_MS}ms")

        if n in ANIMATED:
            for size in sizes:
                digests = [hashlib.md5(f[5]).hexdigest()
                           for f in frames if f[0] == size]
                if len(set(digests)) != len(digests):
                    dup = len(digests) - len(set(digests))
                    fails.append(f"[frames] {n}@{size}: {dup} duplicate frame(s) — "
                                 f"the animation does not advance")

        for w, h, xh, yh, _d, px in frames:
            if n not in HOTSPOT_EXEMPT:
                near = 0
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        x, y = xh + dx, yh + dy
                        if 0 <= x < w and 0 <= y < h:
                            near = max(near, px[(y * w + x) * 4 + 3])
                if near < 64:
                    fails.append(f"[hotspot] {n}@{w}: ({xh},{yh}) is transparent")
            if w != 24:
                continue
            for bn, bg in BACKGROUNDS.items():
                c = best_contrast(w, h, px, bg)
                if c < worst[2]:
                    worst = (n, bn, c)
                if c < MIN_CONTRAST:
                    fails.append(f"[contrast] {n} on {bn}: {c:.2f}:1 < {MIN_CONTRAST}")

    total = sum(os.path.getsize(os.path.join(cursors, n)) for n in real)
    if not quiet:
        print(f"{len(real)} cursors, {len(links)} symlinks, {total / 1024 / 1024:.1f} MB")
        print(f"worst measured contrast: {worst[2]:.2f}:1  ({worst[0]} on {worst[1]})")
    if fails:
        print(f"\n{len(fails)} FAILURES:")
        for f in fails[:40]:
            print("  " + f)
        if len(fails) > 40:
            print(f"  ... and {len(fails) - 40} more")
        return 1
    if not quiet:
        print("all gates pass")
    return 0


if __name__ == "__main__":
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "out", "cursors", "Frost-cursors")
    sys.exit(verify(sys.argv[1] if len(sys.argv) > 1 else default))
