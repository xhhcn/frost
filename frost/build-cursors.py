#!/usr/bin/env python3
"""
Frost cursors — single source of truth.

Every shape is defined here as SVG path data and rendered by rsvg-convert into
Xcursor files via xcursorgen. Nothing is downloaded; nothing is traced from an
existing theme. This mirrors build-theme.py: change a constant, re-run, and the
whole cursor tree is regenerated.

Design system (derived from the three shapes that survived review):

  1. One closed path per glyph wherever the silhouette allows. Overlapping
     primitives are banned — each carries its own stroke, and the overlap
     renders as a seam across the middle of the shape.
  2. fill #e8eaed, stroke #171a1f at 0.85 opacity, width 1.5 at a 24 viewBox,
     round joins and caps. Light core + dark casing means one of the two always
     clears 3:1 no matter what is behind the cursor.
  3. Line-like elements (crosshair arms, resize arrows, the four-way move) are
     outlined *shapes*, never bare strokes, so they inherit rule 2.
  3a. MIN_FEATURE: no limb may be narrower than 3.5 at the 24 viewBox. The
     stroke is centred, so a limb of width W keeps only W-1.5 of fill; below 3.5
     the fill vanishes and the limb renders as solid #171a1f, which disappears
     against a dark window. Measured, not assumed: the 1.5-wide I-beam stem this
     replaces scored 2.12:1 on #171a1f, and text is the cursor most often over
     a dark editor.
  4. No accent, anywhere. The theme's rule is that accent means *time*, and this
     file has no way to know the time: it is baked once at install and daylight.py
     has no cursor path, so an accent here would freeze — cyan at noon, still cyan
     at midnight while everything else turned indigo. A frozen accent states the
     wrong time, which is worse than stating none. It also measured worst: the day
     accent (cyan) over the day wallpaper (blue) is 1.82:1, same hue family, while
     the plain foreground is 2.83:1 and the dark casing 5.12:1.
     This is not a concession — it restores the rule the theme already had, that
     cursors do not take the accent because a cursor moves constantly and a
     changing colour under the hand is persistent noise.
  5. Badges (help/copy/alias/context-menu) are monochrome. Breeze tints them
     blue/green/red; Frost does not, because the theme allows colour exactly two
     meanings (accent = time, selection/hover/focus = state) and a third palette
     would compete with both.
  6. No drop shadow, though Breeze has one. The polarities differ: Breeze fills
     dark and outlines light, so on a light background only the dark fill shows
     and it needs a shadow to separate. Frost fills light and outlines dark, so a
     light element and a dark one are always both present — which is exactly why
     the measured worst case is 3.10:1 with no shadow at all. Tested over the real
     wallpapers: a light shadow adds nothing measurable, a heavy one visibly
     muddies the I-beam.
"""

import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ── constants ────────────────────────────────────────────────────────────────

NAME = "Frost"
COMMENT = "Frost — hand-drawn cursors"
INHERITS = "breeze_cursors"

FG = "#e8eaed"
EDGE = "#171a1f"
EDGE_OPACITY = "0.85"
STROKE_W = 1.5

# Plasma's cursor-size KCM lists whatever sizes the theme ships, so this ladder
# *is* the set of options the user sees. Breeze ships 16..96 step 8 (11 sizes,
# 15 MB); these six cover every size anyone actually selects at about a third of
# the bytes, which matters because Frost's whole payload is currently 336 KB.
SIZES = (16, 24, 32, 48, 64, 96)

# Breeze animates in 23 frames at 30 ms. 12 at 60 ms is the same 720 ms period,
# half the frames, and one fewer arbitrary number.
FRAMES = 12
FRAME_MS = 60

BODY = (f'fill="{FG}" stroke="{EDGE}" stroke-opacity="{EDGE_OPACITY}" '
        f'stroke-width="{STROKE_W}" stroke-linejoin="round" stroke-linecap="round"')
GLYPH = f'fill="{EDGE}" fill-opacity="0.92"'
GLYPH_LINE = (f'fill="none" stroke="{EDGE}" stroke-opacity="0.92" '
              f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"')

# ── reusable geometry ────────────────────────────────────────────────────────

ARROW = "M3,3 L3,19 L7.3,15 L10.3,21.3 L12.7,20.1 L9.5,14 L15.3,14 Z"


def scaled_arrow(s, ox=3.0, oy=3.0):
    """The default arrow scaled about its tip, so a badge has room bottom-right."""
    def f(m):
        x, y = float(m.group(1)), float(m.group(2))
        return f"{ox + (x - ox) * s:.2f},{oy + (y - oy) * s:.2f}"
    return re.sub(r"(-?\d+\.?\d*),(-?\d+\.?\d*)", f, ARROW)


BADGE_CX, BADGE_CY, BADGE_R = 17.3, 17.3, 5.3


def badge(glyph):
    """Monochrome corner badge: light disc, dark casing, dark glyph."""
    return (f'<circle cx="{BADGE_CX}" cy="{BADGE_CY}" r="{BADGE_R}" {BODY}/>\n  {glyph}')


def spinner(cx, cy, r, width, arc=0.70):
    """
    Busy indicator: a gapped ring, monochrome, same light-core/dark-casing pairing
    as every filled shape — see design rules 2 and 4.

    Uniform width with round caps, not a tapered comet: Frost's taskbar indicator
    is a uniform capsule, and this is that capsule bent into a circle. The gap
    travelling round the ring is what reads as motion; the taper would be a
    second, competing motion cue borrowed from a different design language.

    Casing is +2.2, not +1.5: an arc has no fill for the stroke to sit on, so the
    casing is all there is on either side. At +1.5 each side gets 0.75 and
    antialiasing keeps it from ever reaching full #171a1f.
    """
    circ = 2 * math.pi * r
    dash = f'{circ * arc:.2f} {circ * (1 - arc):.2f}'
    common = (f'cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke-linecap="round" '
              f'stroke-dasharray="{dash}"')
    return (f'<g transform="rotate(__FROST_SPIN__ {cx} {cy})">'
            f'<circle {common} stroke="{EDGE}" stroke-opacity="{EDGE_OPACITY}" '
            f'stroke-width="{width + 2.2}"/>'
            f'<circle {common} stroke="{FG}" stroke-width="{width}"/>'
            f'</g>')


def circle_path(cx, cy, r):
    """
    A closed circle as two 180-degree arcs.

    Not `a r,r 0 1 1 -0.01,0`: that near-degenerate single arc leaves a 0.01
    gap, and with a 1.5 round-capped stroke the gap renders as a visible nub at
    twelve o'clock on every circle in the theme.
    """
    return (f'M{cx},{cy - r} a{r},{r} 0 1 1 0,{2 * r} '
            f'a{r},{r} 0 1 1 0,{-2 * r} Z')


def ring_with_bar(cx, cy, r_out, r_in, half_w, angle=45):
    """
    "No entry" sign, built as an outline rather than by masking.

    fill-rule only governs the fill; the stroke follows every subpath regardless.
    So punching a bar-shaped hole with even-odd parity gives the right fill and
    the wrong outline — the bar's rectangle gets stroked straight across the
    ring band.

    Instead compute the actual boundary: outer_disc minus (inner_circle minus
    bar). That difference is exactly two circular segments, each bounded by one
    edge of the bar (a chord at distance half_w from centre) and the inner arc
    beyond it. Stroking that yields the outer circle, two inner arcs and two bar
    edges — precisely the lines the glyph should have, and no others.
    """
    c = math.sqrt(r_in ** 2 - half_w ** 2)          # half-chord length
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)

    def R(x, y):
        return f"{cx + x * ca - y * sa:.3f},{cy + x * sa + y * ca:.3f}"

    # Sweep flags derived in the un-rotated frame (y down, so +y is on screen
    # below centre); rotation preserves orientation, so they carry over.
    seg_near = f'M{R(-c, half_w)} L{R(c, half_w)} A{r_in},{r_in} 0 0 1 {R(-c, half_w)} Z'
    seg_far = f'M{R(-c, -half_w)} L{R(c, -half_w)} A{r_in},{r_in} 0 0 0 {R(-c, -half_w)} Z'
    return (f'<path fill-rule="evenodd" {BODY} '
            f'd="{circle_path(cx, cy, r_out)} {seg_near} {seg_far}"/>')


# ── shapes: name -> (svg body, hotspot x/24, hotspot y/24) ───────────────────

SHAPES = {}

SHAPES["default"] = (f'<path {BODY} d="{ARROW}"/>', 3 / 24, 3 / 24)

# Pointer. Rebuilt from three overlapping rounded rects into one closed path.
# Reading order: up the index finger's left edge, over the tip, down its right
# edge, then three knuckle humps for the folded fingers, round the palm, out to
# the thumb and back. The humps are what make it read as a hand rather than a
# thumbs-up; without them the silhouette is a sock.
# The finger spans x 10.35..13.65 so its centre is exactly 12 — the hotspot
# ratio is 0.5, so the hotspot has to land on the fingertip.
SHAPES["pointer"] = (f'<path {BODY} d="'
                     'M10.35,13.5 V5.1 a1.65,1.65 0 0 1 3.3,0 V12.4 '
                     'a1.1,1.1 0 0 1 2.2,0 V13.1 '
                     'a1.1,1.1 0 0 1 2.2,0 V13.8 '
                     'a1.1,1.1 0 0 1 2.2,0 V17.7 '
                     'q0,3.2 -3.2,3.2 H12.7 '
                     'q-1.8,0 -2.8,-1.4 L7.1,16.7 '
                     'q-1.0,-1.3 0.4,-2.1 q1.4,-0.9 2.2,0.5 L10.35,15.8 Z"/>',
                     0.5, 3 / 24)

# Stem 3.4 wide and serifs 3.0 thick, up from 1.5 each — see design rule 3a.
SHAPES["text"] = (f'<path {BODY} d="'
                  'M7.8,3 H16.2 V6.0 H13.7 V18.0 H16.2 V21 H7.8 V18.0 '
                  'H10.3 V6.0 H7.8 Z"/>',
                  0.5, 11 / 24)

# Shaft 3.6, was 3.4 — it cleared the contrast gate but broke design rule 3a.
SHAPES["resize-2way"] = (f'<path {BODY} d="'
                         'M2,11 L6,7 L6,9.2 L18,9.2 L18,7 L22,11 '
                         'L18,15 L18,12.8 L6,12.8 L6,15 Z"/>',
                         0.5, 0.5)

# Crosshair: one plus polygon, no centre gap. Breeze has no gap either, and at
# 16px a gap eats the whole glyph. Arms are 3.6 wide per design rule 3a.
SHAPES["crosshair"] = (f'<path {BODY} d="'
                       'M10.2,1.8 H13.8 V10.2 H22.2 V13.8 H13.8 V22.2 '
                       'H10.2 V13.8 H1.8 V10.2 H10.2 Z"/>', 0.5, 0.5)

# cell: same construction, arms pulled in — it marks a table cell, not a pixel.
SHAPES["cell"] = (f'<path {BODY} d="'
                  'M10.2,4.2 H13.8 V10.2 H19.8 V13.8 H13.8 V19.8 '
                  'H10.2 V13.8 H4.2 V10.2 H10.2 Z"/>', 0.5, 0.5)

SHAPES["not-allowed"] = (ring_with_bar(12, 11, 8.2, 5.3, 1.4), 0.5, 11 / 24)

# Four-way move. Shaft half-width 1.5, arrowhead half-width 3.6, tips at 1.5/22.5.
SHAPES["fleur"] = (f'<path {BODY} d="'
                   'M12,1.5 L15.6,5.6 L13.5,5.6 L13.5,10.5 L18.4,10.5 L18.4,8.4 '
                   'L22.5,12 L18.4,15.6 L18.4,13.5 L13.5,13.5 L13.5,18.4 L15.6,18.4 '
                   'L12,22.5 L8.4,18.4 L10.5,18.4 L10.5,13.5 L5.6,13.5 L5.6,15.6 '
                   'L1.5,12 L5.6,8.4 L5.6,10.5 L10.5,10.5 L10.5,5.6 L8.4,5.6 Z"/>',
                   0.5, 0.5)

# Single arrow, drawn pointing up; the build rotates it for the other three.
SHAPES["arrow"] = (f'<path {BODY} d="'
                   'M12,1.8 L18.2,9.0 L14.2,9.0 L14.2,22.2 L9.8,22.2 L9.8,9.0 '
                   'L5.8,9.0 Z"/>', 0.5, 1.8 / 24)

# Open hand: four scalloped knuckle bumps along the top instead of four separate
# fingers with gaps — at 24px the gaps close up into mush anyway, and the
# scallop survives downscaling. Middle bump tallest, pinky shortest.
SHAPES["openhand"] = (f'<path {BODY} d="'
                      'M6.8,14.0 V8.4 '
                      'a1.45,1.45 0 0 1 2.9,0 V7.2 '
                      'a1.45,1.45 0 0 1 2.9,0 V7.0 '
                      'a1.45,1.45 0 0 1 2.9,0 V8.6 '
                      'a1.4,1.4 0 0 1 2.8,0 V16.6 '
                      'q0,4.2 -4.2,4.2 H11.8 '
                      'q-2.0,0 -3.1,-1.6 L4.7,14.9 '
                      'q-1.0,-1.3 0.4,-2.2 q1.4,-0.9 2.3,0.5 Z"/>', 0.5, 0.5)

# Closed hand. Same vocabulary as openhand but squat, with shallow bumps and a
# thumb ridge on the left — the silhouette difference (tall vs wide, deep vs
# shallow scallop) is what distinguishes grab from grabbing at 24px.
SHAPES["closedhand"] = (f'<path {BODY} d="'
                        'M6.0,15.4 V11.6 '
                        'a1.45,1.45 0 0 1 2.9,0 V11.2 '
                        'a1.45,1.45 0 0 1 2.9,0 V11.2 '
                        'a1.45,1.45 0 0 1 2.9,0 V11.6 '
                        'a1.4,1.4 0 0 1 2.8,0 V16.8 '
                        'q0,4.0 -4.0,4.0 H10.6 '
                        'q-4.6,0 -4.6,-4.6 V16.4 '
                        'q-1.6,-0.2 -1.6,-1.6 q0,-1.3 1.6,-1.5 Z"/>', 0.5, 0.5)

# ── badged arrows ────────────────────────────────────────────────────────────

_A78 = scaled_arrow(0.78)

SHAPES["help"] = (
    f'<path {BODY} d="{_A78}"/>\n  ' + badge(
        f'<path {GLYPH_LINE} d="M15.55,16.0 a1.75,1.75 0 1 1 1.9,1.95 v0.75"/>'
        f'<circle cx="17.45" cy="20.35" r="0.85" {GLYPH}/>'),
    3 / 24, 3 / 24)

SHAPES["copy"] = (
    f'<path {BODY} d="{_A78}"/>\n  ' + badge(
        f'<path {GLYPH} d="M16.5,14.5 H18.1 V16.5 H20.1 V18.1 H18.1 V20.1 '
        f'H16.5 V18.1 H14.5 V16.5 H16.5 Z"/>'),
    3 / 24, 3 / 24)

SHAPES["alias"] = (
    f'<path {BODY} d="{_A78}"/>\n  ' + badge(
        f'<path {GLYPH_LINE} d="M14.9,19.7 L19.7,14.9 M16.7,14.9 H19.7 V17.9"/>'),
    3 / 24, 3 / 24)

SHAPES["context-menu"] = (
    f'<path {BODY} d="{_A78}"/>\n  ' + badge(
        f'<path {GLYPH_LINE} d="M14.7,15.3 H19.9 M14.7,17.3 H19.9 M14.7,19.3 H19.9"/>'),
    3 / 24, 3 / 24)

# ── magnifiers ───────────────────────────────────────────────────────────────


def magnifier(sign):
    """
    Lens as a filled disc, not an annulus.

    An annulus thin enough to read as a lens rim (band ~1.5) has its two 1.5
    strokes almost touching, which fills the band solid anyway at 24px. A filled
    light disc with a dark casing is the same construction as the corner badges,
    and gives the +/- glyph a light field to sit on.
    """
    cx, cy, r = 10.2, 10.2, 6.2
    k = math.sqrt(0.5)
    hx, hy = cx + k * r, cy + k * r
    # Same casing trick as the spinner: a wider dark bar under a lighter core.
    seg = f'd="M{hx:.2f},{hy:.2f} L20.8,20.8" fill="none" stroke-linecap="round"'
    handle = (f'<path {seg} stroke="{EDGE}" stroke-opacity="{EDGE_OPACITY}" '
              f'stroke-width="{1.9 + STROKE_W}"/>'
              f'<path {seg} stroke="{FG}" stroke-width="1.9"/>')
    glyph = f'<path {GLYPH} d="M7.0,9.4 H13.4 V11.0 H7.0 Z"/>'
    if sign == "in":
        glyph += f'<path {GLYPH} d="M9.4,7.0 H11.0 V13.4 H9.4 Z"/>'
    return handle + f'<path {BODY} d="{circle_path(cx, cy, r)}"/>' + glyph


SHAPES["zoom-in"] = (magnifier("in"), 10.4 / 24, 10.4 / 24)
SHAPES["zoom-out"] = (magnifier("out"), 10.4 / 24, 10.4 / 24)

# ── animated ─────────────────────────────────────────────────────────────────

SHAPES["progress"] = (f'<path {BODY} d="{ARROW}"/>\n  ' + spinner(17.6, 17.6, 4.0, 1.8),
                      3 / 24, 3 / 24)

# wait stays a bare spinner: no arrow, because the state is "you cannot point at
# anything". Distinct from not-allowed (also a ring) by the gap and the empty
# centre — not-allowed has a closed ring and a solid bar through it.
SHAPES["wait"] = (spinner(12, 11, 7.0, 2.4), 0.5, 11 / 24)

ANIMATED = {"progress", "wait"}

# ── entities: cursor file name -> (shape, rotation in degrees) ───────────────

ENTITIES = {
    "default": ("default", 0),
    "pointer": ("pointer", 0),
    "text": ("text", 0),
    "vertical-text": ("text", 90),
    "progress": ("progress", 0),
    "wait": ("wait", 0),
    "crosshair": ("crosshair", 0),
    "cell": ("cell", 0),
    "help": ("help", 0),
    "not-allowed": ("not-allowed", 0),
    "no-drop": ("not-allowed", 0),
    "dnd-no-drop": ("not-allowed", 0),
    "copy": ("copy", 0),
    "alias": ("alias", 0),
    "context-menu": ("context-menu", 0),
    "openhand": ("openhand", 0),
    # Breeze makes closedhand and grabbing symlinks to dnd-move, which means
    # dnd-move must BE the closed fist — its hotspot is centred (0.5,0.5), not
    # an arrow tip. Drawing it as an arrow-plus-badge would render `grabbing`
    # as an arrow.
    "dnd-move": ("closedhand", 0),
    "fleur": ("fleur", 0),
    "all-scroll": ("fleur", 0),
    "zoom-in": ("zoom-in", 0),
    "zoom-out": ("zoom-out", 0),
    "up-arrow": ("arrow", 0),
    "right-arrow": ("arrow", 90),
    "down-arrow": ("arrow", 180),
    "left-arrow": ("arrow", 270),
    "center_ptr": ("arrow", 0),
    "size_hor": ("resize-2way", 0),
    "left_side": ("resize-2way", 0),
    "right_side": ("resize-2way", 0),
    "col-resize": ("resize-2way", 0),
    "size_ver": ("resize-2way", 90),
    "top_side": ("resize-2way", 90),
    "bottom_side": ("resize-2way", 90),
    "row-resize": ("resize-2way", 90),
    "size_fdiag": ("resize-2way", 45),
    "top_left_corner": ("resize-2way", 45),
    "bottom_right_corner": ("resize-2way", 45),
    "size_bdiag": ("resize-2way", -45),
    "top_right_corner": ("resize-2way", -45),
    "bottom_left_corner": ("resize-2way", -45),
    "x-cursor": ("default", 0),
    "wayland-cursor": ("default", 0),
    "right_ptr": ("default", 0),
}

# Verified against /usr/share/icons/breeze_cursors/cursors: every one of these is
# a symlink there with the same target, including the ones that look wrong
# (size-hor really does point at default upstream — the hyphenated spellings are
# legacy names X never used).
ALIASES = {
    "00000000000000020006000e7e9ffc3f": "progress",
    "00008160000006810000408080010102": "size_ver",
    "03b6e0fcb3499374a867c041f52298f0": "not-allowed",
    "08e8e1c95fe2fc01f976f1e063a24ccd": "progress",
    "1081e37283d90000800003c07f3ef6bf": "copy",
    "3085a0e285430894940527032f8b26df": "alias",
    "3ecb610c1bf2410f44200f48c40d3599": "progress",
    "4498f0e0c1937ffe01fd06f973665830": "dnd-move",
    "5c6cd98b3f3ebcb1f9c7f1c204630408": "help",
    "6407b0e94181790501fd1e167b474872": "copy",
    "640fb0e74195791501fd1ed57b41487f": "alias",
    "9081237383d90e509aa00f00170e968f": "dnd-move",
    "9d800788f1b08800ae810202380a0822": "pointer",
    "a2a266d0498c3104214a47bd64ab0fc8": "alias",
    "arrow": "default",
    "b66166c04f8c3109214a4fbd64a50fc8": "copy",
    "circle": "not-allowed",
    "closedhand": "dnd-move",
    "color-picker": "default",
    "cross": "crosshair",
    "crossed_circle": "not-allowed",
    "d9ce0ab605698f320427677b458ad60b": "help",
    "dnd-copy": "copy",
    "dnd-none": "dnd-move",
    "draft": "default",
    "e29285e634086352946a0e7090d73106": "pointer",
    "e-resize": "size_hor",
    "ew-resize": "size_hor",
    "fcf21c00b30f7e3f83fe0dfd12e71cff": "dnd-move",
    "forbidden": "no-drop",
    "grab": "openhand",
    "grabbing": "closedhand",
    "half-busy": "progress",
    "hand1": "pointer",
    "hand2": "pointer",
    "h_double_arrow": "size_hor",
    "ibeam": "text",
    "left_ptr": "default",
    "left_ptr_help": "help",
    "left_ptr_watch": "progress",
    "link": "alias",
    "move": "dnd-move",
    "ne-resize": "size_bdiag",
    "nesw-resize": "size_bdiag",
    "n-resize": "size_ver",
    "ns-resize": "size_ver",
    "nw-resize": "size_fdiag",
    "nwse-resize": "size_fdiag",
    "pencil": "default",
    "pirate": "default",
    "plus": "cell",
    "pointing_hand": "pointer",
    "question_arrow": "help",
    "sb_h_double_arrow": "size_hor",
    "sb_v_double_arrow": "size_ver",
    "se-resize": "size_fdiag",
    "size_all": "fleur",
    "size-bdiag": "default",
    "size-fdiag": "default",
    "size-hor": "default",
    "size-ver": "default",
    "split_h": "col-resize",
    "split_v": "row-resize",
    "s-resize": "size_ver",
    "sw-resize": "size_bdiag",
    "tcross": "crosshair",
    "top_left_arrow": "default",
    "v_double_arrow": "size_ver",
    "watch": "wait",
    "whats_this": "help",
    "w-resize": "size_hor",
    "xterm": "text",
}

# ── rendering ────────────────────────────────────────────────────────────────


def svg_for(shape, angle=0, spin=0.0):
    body, _, _ = SHAPES[shape]
    body = body.replace("__FROST_SPIN__", f"{spin:.3f}")
    g = f'<g transform="rotate({angle} 12 12)">{body}</g>' if angle else body
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{g}</svg>'


def hotspot(shape, angle, size):
    """Rotate the shape's hotspot with the shape, then scale to `size`."""
    _, hx, hy = SHAPES[shape]
    x, y = hx * 24, hy * 24
    if angle:
        a = math.radians(angle)
        dx, dy = x - 12, y - 12
        x = 12 + dx * math.cos(a) - dy * math.sin(a)
        y = 12 + dx * math.sin(a) + dy * math.cos(a)
    k = size / 24.0
    return max(0, min(size - 1, round(x * k))), max(0, min(size - 1, round(y * k)))


def render_png(shape, angle, size, path, spin=0.0):
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(svg_for(shape, angle, spin))
        tmp = f.name
    subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), tmp, "-o", path],
                   check=True)
    os.unlink(tmp)


def build(outdir):
    cursors = os.path.join(outdir, "cursors")
    os.makedirs(cursors, exist_ok=True)
    work = tempfile.mkdtemp(prefix="frost-cursors-")
    made = 0
    try:
        for name, (shape, angle) in sorted(ENTITIES.items()):
            cfg = os.path.join(work, f"{name}.cfg")
            lines = []
            nframes = FRAMES if shape in ANIMATED else 1
            for fi in range(nframes):
                spin = 360.0 * fi / FRAMES
                for size in SIZES:
                    png = os.path.join(work, f"{name}-{size}-{fi}.png")
                    render_png(shape, angle, size, png, spin)
                    hx, hy = hotspot(shape, angle, size)
                    if nframes > 1:
                        lines.append(f"{size} {hx} {hy} {png} {FRAME_MS}")
                    else:
                        lines.append(f"{size} {hx} {hy} {png}")
            with open(cfg, "w") as f:
                f.write("\n".join(lines) + "\n")
            subprocess.run(["xcursorgen", cfg, os.path.join(cursors, name)], check=True)
            made += 1

        links = 0
        for link, target in sorted(ALIASES.items()):
            # Resolve chains (grabbing -> closedhand -> dnd-move) down to the real
            # file so no symlink on the user's desktop can dangle.
            seen, t = set(), target
            while t in ALIASES and t not in ENTITIES and t not in seen:
                seen.add(t)
                t = ALIASES[t]
            if t not in ENTITIES:
                print(f"  !! alias {link} -> {target} resolves to {t}, which is "
                      f"not an entity — skipped", file=sys.stderr)
                continue
            p = os.path.join(cursors, link)
            if os.path.lexists(p):
                os.unlink(p)
            os.symlink(t, p)
            links += 1
    finally:
        shutil.rmtree(work, ignore_errors=True)

    with open(os.path.join(outdir, "index.theme"), "w") as f:
        f.write(f"[Icon Theme]\nName={NAME}\nComment={COMMENT}\nInherits={INHERITS}\n")
    with open(os.path.join(outdir, "cursor.theme"), "w") as f:
        f.write(f"[Icon Theme]\nName={NAME}\nInherits={INHERITS}\n")
    return made, links


THEME_DIR = "Frost-cursors"     # NOT "Frost": icons/Frost is the icon theme, whose
                                # Inherits= chain is for icons and cannot also serve
                                # cursor inheritance. index.theme still says Name=Frost,
                                # so the KCM shows "Frost" either way.
TOOLS = ("rsvg-convert", "xcursorgen")


def missing_tools():
    """Which required binaries are absent. Callers degrade rather than fail."""
    return [t for t in TOOLS if not shutil.which(t)]


def default_out():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "out", "cursors", THEME_DIR)


if __name__ == "__main__":
    # No time-of-day argument: the cursor set is period-independent by design.
    out = sys.argv[1] if len(sys.argv) > 1 else default_out()
    gone = missing_tools()
    if gone:
        print(f"!! missing: {', '.join(gone)} "
              f"(Arch: pacman -S librsvg xorg-xcursorgen)", file=sys.stderr)
        sys.exit(2)
    n, l = build(out)
    total = sum(os.path.getsize(os.path.join(out, "cursors", f))
                for f in os.listdir(os.path.join(out, "cursors"))
                if not os.path.islink(os.path.join(out, "cursors", f)))
    print(f"{n} cursors + {l} symlinks -> {out}   ({total/1024/1024:.1f} MB)")
