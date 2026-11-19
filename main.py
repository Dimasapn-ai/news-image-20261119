#!/usr/bin/env python3
"""The World In One Day - Thursday 19 November 2026.

Draws a newspaper front page that sums up the world news of
Thursday 19 November 2026 and writes it as a PNG to the output
directory ($MAKEFUN_OUTPUT_DIR, else /output) under the name
entry.png.

Pure Python standard library: the picture is painted into a pixel
buffer with hand-written drawing routines and a hand-authored
stroke font, supersampled 2x and averaged down, then encoded as a
PNG with zlib.  No network, no third-party packages, fully
deterministic: two runs write identical bytes.
"""

import math
import os
import struct
import zlib

# ------------------------------------------------------------------
# Canvas: an RGB pixel buffer painted in "final pixel" coordinates,
# internally supersampled by SS so lines and lettering come out
# smooth after the averaging pass at the end.
# ------------------------------------------------------------------

SS = 2                 # supersample factor
W = 1024               # final width
H = 1024               # final height


class Canvas:
    def __init__(self, w, h, bg):
        self.w = w * SS
        self.h = h * SS
        self.buf = bytearray(bg) * (self.w * self.h)

    def px(self, x, y, rgb):
        """Set one supersampled pixel, clipped to the canvas."""
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i] = rgb[0]
            self.buf[i + 1] = rgb[1]
            self.buf[i + 2] = rgb[2]

    def disc(self, cx, cy, r, rgb):
        """Filled circle given in final-pixel coordinates."""
        cx, cy, r = cx * SS, cy * SS, r * SS
        x0, x1 = int(cx - r - 1), int(cx + r + 1)
        y0, y1 = int(cy - r - 1), int(cy + r + 1)
        rr = r * r
        for y in range(y0, y1 + 1):
            dy = y - cy
            for x in range(x0, x1 + 1):
                dx = x - cx
                if dx * dx + dy * dy <= rr:
                    self.px(x, y, rgb)

    def rect(self, x, y, w, h, rgb):
        """Filled rectangle in final-pixel coordinates."""
        x0, y0 = int(x * SS), int(y * SS)
        x1, y1 = int((x + w) * SS), int((y + h) * SS)
        for yy in range(y0, y1):
            base = yy * self.w * 3
            for xx in range(x0, x1):
                i = base + xx * 3
                self.buf[i] = rgb[0]
                self.buf[i + 1] = rgb[1]
                self.buf[i + 2] = rgb[2]

    def line(self, x1, y1, x2, y2, thick, rgb):
        """Thick line: stamp discs along the segment."""
        dist = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(dist * SS * 1.5))
        r = thick / 2.0
        for i in range(steps + 1):
            t = i / steps
            self.disc(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, r, rgb)

    def polyline(self, pts, thick, rgb, close=False):
        seq = list(pts)
        if close and len(seq) > 2:
            seq.append(seq[0])
        for a, b in zip(seq, seq[1:]):
            self.line(a[0], a[1], b[0], b[1], thick, rgb)

    def polygon(self, pts, rgb):
        """Filled polygon, scanline even-odd fill."""
        ys = [p[1] for p in pts]
        y0, y1 = int(min(ys) * SS), int(max(ys) * SS)
        n = len(pts)
        for yy in range(y0, y1 + 1):
            yf = yy / SS
            nodes = []
            for i in range(n):
                ax, ay = pts[i]
                bx, by = pts[(i + 1) % n]
                if (ay <= yf < by) or (by <= yf < ay):
                    nodes.append(ax + (yf - ay) * (bx - ax) / (by - ay))
            nodes.sort()
            for i in range(0, len(nodes) - 1, 2):
                xa, xb = int(nodes[i] * SS), int(nodes[i + 1] * SS)
                for xx in range(xa, xb + 1):
                    self.px(xx, yy, rgb)

    def ring(self, cx, cy, r, thick, rgb):
        """Circle outline."""
        steps = max(24, int(2 * math.pi * r * SS))
        pts = [(cx + r * math.cos(2 * math.pi * i / steps),
                cy + r * math.sin(2 * math.pi * i / steps))
               for i in range(steps + 1)]
        self.polyline(pts, thick, rgb)

    def ellipse(self, cx, cy, rx, ry, rgb):
        """Filled ellipse."""
        x0, x1 = int((cx - rx) * SS), int((cx + rx) * SS)
        y0, y1 = int((cy - ry) * SS), int((cy + ry) * SS)
        for yy in range(y0, y1 + 1):
            dy = (yy / SS - cy) / ry
            for xx in range(x0, x1 + 1):
                dx = (xx / SS - cx) / rx
                if dx * dx + dy * dy <= 1.0:
                    self.px(xx, yy, rgb)

    def downscale(self):
        """Average the supersampled buffer down to W x H bytes."""
        out = bytearray(W * H * 3)
        sw = self.w
        for y in range(H):
            for x in range(W):
                r = g = b = 0
                for dy in range(SS):
                    base = ((y * SS + dy) * sw + x * SS) * 3
                    for dx in range(SS):
                        i = base + dx * 3
                        r += self.buf[i]
                        g += self.buf[i + 1]
                        b += self.buf[i + 2]
                n = SS * SS
                o = (y * W + x) * 3
                out[o] = r // n
                out[o + 1] = g // n
                out[o + 2] = b // n
        return bytes(out)


def encode_png(rgb, w, h):
    """Minimal, correct PNG writer (8-bit RGB, filter 0 rows)."""
    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body +
                struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]
    idat = zlib.compress(bytes(raw), 9)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", idat) + chunk(b"IEND", b""))


# ------------------------------------------------------------------
# A stroke font, authored by hand for this program.  Each glyph is
# a list of strokes; each stroke is a list of (x, y) points on a
# 4-wide, 6-tall grid with y pointing down, (0, 0) at the top left
# of the character cell.  Letters are drawn by stroking the
# segments with a round pen.
# ------------------------------------------------------------------

FONT = {
    "A": [[(0, 6), (2, 0), (4, 6)], [(0.9, 4.1), (3.1, 4.1)]],
    "B": [[(0, 0), (0, 6)],
          [(0, 0), (2.5, 0), (3.6, 0.9), (3.6, 2.1), (2.5, 3), (0, 3)],
          [(0, 3), (2.7, 3), (3.8, 3.9), (3.8, 5.1), (2.7, 6), (0, 6)]],
    "C": [[(3.8, 1.2), (2.9, 0.3), (1.2, 0.3), (0.3, 1.2), (0.3, 4.8),
           (1.2, 5.7), (2.9, 5.7), (3.8, 4.8)]],
    "D": [[(0, 0), (0, 6)],
          [(0, 0), (2.3, 0), (3.7, 1.5), (3.7, 4.5), (2.3, 6), (0, 6)]],
    "E": [[(3.6, 0), (0, 0), (0, 6), (3.6, 6)], [(0, 3), (2.7, 3)]],
    "F": [[(3.6, 0), (0, 0), (0, 6)], [(0, 3), (2.7, 3)]],
    "G": [[(3.8, 1.2), (2.9, 0.3), (1.2, 0.3), (0.3, 1.2), (0.3, 4.8),
           (1.2, 5.7), (2.9, 5.7), (3.8, 4.8), (3.8, 3.5), (2.3, 3.5)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(2, 0), (2, 6)], [(0.9, 0), (3.1, 0)], [(0.9, 6), (3.1, 6)]],
    "J": [[(3.7, 0), (3.7, 4.5), (2.9, 5.7), (1.2, 5.7), (0.3, 4.9)]],
    "K": [[(0, 0), (0, 6)], [(3.8, 0), (0.4, 2.9)], [(1.0, 2.2), (3.8, 6)]],
    "L": [[(0, 0), (0, 6), (3.6, 6)]],
    "M": [[(0, 6), (0, 0), (2, 3.2), (4, 0), (4, 6)]],
    "N": [[(0, 6), (0, 0), (4, 6), (4, 0)]],
    "O": [[(2, 0), (3.1, 0.4), (3.9, 1.6), (3.9, 4.4), (3.1, 5.6),
           (2, 6), (0.9, 5.6), (0.1, 4.4), (0.1, 1.6), (0.9, 0.4), (2, 0)]],
    "P": [[(0, 6), (0, 0)],
          [(0, 0), (2.5, 0), (3.7, 0.9), (3.7, 2.2), (2.5, 3.1), (0, 3.1)]],
    "Q": [[(2, 0), (3.1, 0.4), (3.9, 1.6), (3.9, 4.4), (3.1, 5.6),
           (2, 6), (0.9, 5.6), (0.1, 4.4), (0.1, 1.6), (0.9, 0.4), (2, 0)],
          [(2.5, 4.3), (4.1, 6.1)]],
    "R": [[(0, 6), (0, 0)],
          [(0, 0), (2.5, 0), (3.7, 0.9), (3.7, 2.2), (2.5, 3.1), (0, 3.1)],
          [(1.7, 3.1), (3.9, 6)]],
    "S": [[(3.7, 1.2), (2.8, 0.3), (1.2, 0.3), (0.3, 1.1), (0.4, 2.2),
           (1.3, 2.9), (2.7, 3.3), (3.7, 4.1), (3.6, 5.1), (2.7, 5.8),
           (1.1, 5.8), (0.2, 5.0)]],
    "T": [[(0, 0), (4, 0)], [(2, 0), (2, 6)]],
    "U": [[(0, 0), (0, 4.5), (0.5, 5.5), (1.3, 6), (2.7, 6), (3.5, 5.5),
           (4, 4.5), (4, 0)]],
    "V": [[(0, 0), (2, 6), (4, 0)]],
    "W": [[(0, 0), (0.7, 6), (2, 3.4), (3.3, 6), (4, 0)]],
    "X": [[(0, 0), (4, 6)], [(4, 0), (0, 6)]],
    "Y": [[(0, 0), (2, 2.7)], [(4, 0), (2, 2.7), (2, 6)]],
    "Z": [[(0, 0), (4, 0), (0, 6), (4, 6)]],
    "0": [[(2, 0), (3.0, 0.4), (3.6, 1.6), (3.6, 4.4), (3.0, 5.6),
           (2, 6), (1.0, 5.6), (0.4, 4.4), (0.4, 1.6), (1.0, 0.4), (2, 0)]],
    "1": [[(1.1, 1.3), (2.3, 0), (2.3, 6)], [(0.9, 6), (3.3, 6)]],
    "2": [[(0.3, 1.2), (1.1, 0.3), (2.9, 0.3), (3.7, 1.2), (3.6, 2.3),
           (0.2, 6), (3.8, 6)]],
    "3": [[(0.3, 1.0), (1.2, 0.2), (2.8, 0.2), (3.7, 1.0), (3.6, 2.1),
           (2.7, 2.9), (1.5, 3.0)],
          [(1.5, 3.0), (2.8, 3.1), (3.7, 4.0), (3.6, 5.1), (2.7, 5.8),
           (1.1, 5.8), (0.2, 5.0)]],
    "4": [[(2.9, 6), (2.9, 0), (0.2, 4.3), (4, 4.3)]],
    "5": [[(3.7, 0), (0.3, 0), (0.3, 2.7), (2.5, 2.5), (3.7, 3.3),
           (3.7, 4.9), (2.8, 5.8), (1.0, 5.8), (0.2, 5.0)]],
    "6": [[(3.6, 1.1), (2.7, 0.3), (1.2, 0.3), (0.3, 1.4), (0.2, 4.5),
           (1.1, 5.7), (2.8, 5.7), (3.7, 4.8), (3.7, 3.6), (2.8, 2.8),
           (1.2, 2.8), (0.3, 3.5)]],
    "7": [[(0.2, 0), (3.8, 0), (1.6, 6)]],
    "8": [[(2, 0.2), (2.9, 0.5), (3.2, 1.4), (2.8, 2.4), (2, 2.8),
           (1.2, 2.4), (0.8, 1.4), (1.1, 0.5), (2, 0.2)],
          [(2, 2.8), (3.0, 3.2), (3.5, 4.3), (3.0, 5.5), (2, 5.9),
           (1.0, 5.5), (0.5, 4.3), (1.0, 3.2), (2, 2.8)]],
    "9": [[(0.4, 4.9), (1.3, 5.7), (2.8, 5.7), (3.7, 4.6), (3.8, 1.5),
           (2.9, 0.3), (1.2, 0.3), (0.3, 1.2), (0.3, 2.5), (1.2, 3.3),
           (2.8, 3.3), (3.8, 2.5)]],
    ".": [[(2, 5.55), (2, 5.7)]],
    ",": [[(2.1, 5.1), (1.8, 6.1)]],
    ":": [[(2, 1.1), (2, 1.25)], [(2, 4.9), (2, 5.05)]],
    ";": [[(2, 1.1), (2, 1.25)], [(2.1, 4.9), (1.8, 6.1)]],
    "-": [[(0.7, 3), (3.3, 3)]],
    "/": [[(0.7, 6), (3.3, 0)]],
    "!": [[(2, 0), (2, 4.0)], [(2, 5.55), (2, 5.7)]],
    "?": [[(0.4, 1.1), (1.2, 0.2), (2.8, 0.2), (3.6, 1.1), (3.5, 2.2),
           (2.6, 3.0), (2, 3.6), (2, 4.3)], [(2, 5.55), (2, 5.7)]],
    "'": [[(2, 0), (1.7, 1.3)]],
    '"': [[(1.3, 0), (1.1, 1.3)], [(2.9, 0), (2.7, 1.3)]],
    "+": [[(2, 1.2), (2, 4.8)], [(0.5, 3), (3.5, 3)]],
    "=": [[(0.6, 2.2), (3.4, 2.2)], [(0.6, 3.8), (3.4, 3.8)]],
    "(": [[(3.2, 0), (1.8, 1.2), (1.2, 3), (1.8, 4.8), (3.2, 6)]],
    ")": [[(0.8, 0), (2.2, 1.2), (2.8, 3), (2.2, 4.8), (0.8, 6)]],
    "$": [[(3.7, 1.2), (2.8, 0.3), (1.2, 0.3), (0.3, 1.1), (0.4, 2.2),
           (1.3, 2.9), (2.7, 3.3), (3.7, 4.1), (3.6, 5.1), (2.7, 5.8),
           (1.1, 5.8), (0.2, 5.0)], [(2, -0.2), (2, 6.2)]],
    "%": [[(1, 0.3), (1.7, 0.6), (1.8, 1.4), (1.2, 2.0), (0.5, 1.7),
           (0.4, 0.9), (1, 0.3)],
          [(0.7, 6), (3.3, 0)],
          [(3, 4.0), (3.7, 4.3), (3.8, 5.1), (3.2, 5.7), (2.5, 5.4),
           (2.4, 4.6), (3, 4.0)]],
    "&": [[(3.5, 5.9), (0.9, 2.7), (0.5, 1.7), (0.8, 0.6), (1.9, 0.2),
           (2.7, 0.9), (2.4, 2.0), (0.7, 3.4), (0.5, 4.8), (1.3, 5.8),
           (2.7, 5.6), (3.6, 4.4)]],
}

# Advance widths in grid units (glyph cell is 4 wide, plus tracking).
ADV = {" ": 3.0, "I": 3.6, "1": 4.4, ".": 2.8, ",": 2.8, ":": 2.8,
       ";": 2.8, "'": 2.4, "!": 2.8, "-": 4.2}
DEFAULT_ADV = 5.0


def text_width(text, size):
    """Width in final pixels of a string drawn at cap-height size."""
    unit = size / 6.0
    total = 0.0
    for ch in text:
        total += ADV.get(ch, DEFAULT_ADV)
    return total * unit


def draw_text(cv, x, y, text, size, rgb, align="left"):
    """Draw text with its cap top at y.  Returns the drawn width."""
    unit = size / 6.0
    thick = max(1.1, size * 0.14)
    w = text_width(text, size)
    if align == "center":
        x -= w / 2.0
    elif align == "right":
        x -= w
    pen = x
    for ch in text.upper():
        strokes = FONT.get(ch)
        if strokes:
            for stroke in strokes:
                pts = [(pen + gx * unit, y + gy * unit)
                       for gx, gy in stroke]
                cv.polyline(pts, thick, rgb)
        pen += ADV.get(ch, DEFAULT_ADV) * unit
    return w


def fit_size(text, size, max_w):
    """Shrink size until the text fits max_w; return the size."""
    while size > 6 and text_width(text, size) > max_w:
        size -= 1
    return size


def wrap_text(text, size, max_w):
    """Greedy word wrap; returns a list of lines."""
    words = text.split()
    lines = []
    cur = ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if text_width(trial, size) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ------------------------------------------------------------------
# Palette
# ------------------------------------------------------------------

PAPER = (247, 243, 232)
CARD = (253, 251, 244)
INK = (20, 28, 48)
NAVY = (23, 42, 84)
RED = (178, 30, 30)
GOLD = (198, 138, 24)
GRAY = (92, 96, 104)
WHITE = (255, 255, 255)
SKY = (205, 226, 244)
OCEAN = (64, 118, 190)
BROWN = (110, 72, 40)
TEAL = (18, 128, 120)
ORANGE = (232, 116, 26)
YELLOW = (246, 196, 49)
GREEN = (38, 120, 62)
SKIN1 = (240, 200, 160)
SKIN2 = (222, 178, 132)
SKIN3 = (196, 148, 104)


def border_box(cv, x, y, w, h, rgb, thick=2.5):
    cv.polyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)],
                thick, rgb, close=True)


# ------------------------------------------------------------------
# The lead scene: a globe, the three flags, and three leaders
# seated at a summit table.
# ------------------------------------------------------------------

def draw_globe(cv, cx, cy, r):
    cv.ellipse(cx, cy, r, r, SKY)
    # land-ish blobs
    cv.ellipse(cx - r * 0.35, cy - r * 0.3, r * 0.34, r * 0.22, GREEN)
    cv.ellipse(cx + r * 0.3, cy + r * 0.25, r * 0.38, r * 0.26, GREEN)
    cv.ellipse(cx + r * 0.42, cy - r * 0.42, r * 0.2, r * 0.15, GREEN)
    cv.ring(cx, cy, r, 3, NAVY)
    for f in (-0.55, 0.0, 0.55):
        pts = []
        for i in range(25):
            t = math.pi * i / 24
            pts.append((cx + r * f * math.sin(t) * 1.6 / 1.6
                        if False else cx + r * math.sin(t) * f,
                        cy - r * math.cos(t)))
        cv.polyline(pts, 1.6, NAVY)
    for f in (-0.5, 0.05, 0.6):
        y = cy + r * f
        half = r * math.sqrt(max(0.0, 1 - f * f))
        cv.line(cx - half, y, cx + half, y, 1.6, NAVY)


def draw_flag_us(cv, x, y, w, h):
    stripes = 7
    for i in range(stripes):
        col = RED if i % 2 == 0 else WHITE
        cv.rect(x, y + h * i / stripes, w, h / stripes + 1, col)
    cv.rect(x, y, w * 0.45, h * 4 / stripes, NAVY)
    for r in range(3):
        for c in range(4):
            cv.disc(x + 5 + c * (w * 0.45 - 8) / 3,
                    y + 4.5 + r * (h * 4 / stripes - 8) / 2, 1.6, WHITE)
    border_box(cv, x, y, w, h, INK, 1.6)


def draw_flag_cn(cv, x, y, w, h):
    cv.rect(x, y, w, h, (222, 41, 16))
    cv.disc(x + w * 0.2, y + h * 0.28, 4.2, YELLOW)
    for dx, dy in ((0.42, 0.14), (0.47, 0.32), (0.42, 0.5), (0.48, 0.66)):
        cv.disc(x + w * dx, y + h * dy, 1.9, YELLOW)
    border_box(cv, x, y, w, h, INK, 1.6)


def draw_flag_ru(cv, x, y, w, h):
    cv.rect(x, y, w, h / 3 + 1, WHITE)
    cv.rect(x, y + h / 3, w, h / 3 + 1, (30, 80, 180))
    cv.rect(x, y + 2 * h / 3, w, h / 3 + 1, (208, 40, 40))
    border_box(cv, x, y, w, h, INK, 1.6)


def draw_lead_scene(cv, x, y, w, h):
    cv.rect(x, y, w, h, (224, 236, 246))
    border_box(cv, x, y, w, h, NAVY, 2.5)
    draw_globe(cv, x + 66, y + h / 2, 44)
    # flags on poles behind the table
    flags = (draw_flag_us, draw_flag_cn, draw_flag_ru)
    for i, draw_flag in enumerate(flags):
        fx = x + 168 + i * 82
        cv.line(fx, y + 16, fx, y + h - 30, 3, GRAY)
        draw_flag(cv, fx + 3, y + 14, 58, 36)
    # three leaders: heads and shoulders behind the table
    people = ((x + 196, NAVY, SKIN1), (x + 278, (52, 52, 58), SKIN2),
              (x + 360, (24, 24, 30), SKIN3))
    for cx, suit, skin in people:
        cv.rect(cx - 21, y + h - 42, 42, 22, suit)
        cv.disc(cx, y + h - 52, 13.5, skin)
    # the table, with the declaration on it
    cv.polygon([(x + 150, y + h - 24), (x + w - 18, y + h - 24),
                (x + w - 34, y + h - 4), (x + 166, y + h - 4)], BROWN)
    cv.rect(x + 258, y + h - 30, 44, 12, WHITE)
    border_box(cv, x + 258, y + h - 30, 44, 12, GRAY, 1.2)


# ------------------------------------------------------------------
# Panel icons
# ------------------------------------------------------------------

def icon_scales(cv, x, y):
    cx = x + 52
    cv.line(cx, y + 14, cx, y + 96, 5, NAVY)
    cv.line(cx - 38, y + 24, cx + 38, y + 24, 5, NAVY)
    cv.disc(cx, y + 14, 5, GOLD)
    for sx in (cx - 38, cx + 38):
        cv.line(sx, y + 24, sx - 11, y + 58, 2.4, INK)
        cv.line(sx, y + 24, sx + 11, y + 58, 2.4, INK)
        pts = [(sx + 13 * math.cos(math.pi * i / 12),
                y + 58 + 9 * math.sin(math.pi * i / 12))
               for i in range(13)]
        cv.polyline(pts, 3.4, GOLD)
        cv.line(sx - 13, y + 58, sx + 13, y + 58, 2.4, INK)
    cv.line(cx - 22, y + 100, cx + 22, y + 100, 5, NAVY)


def icon_tanker(cv, x, y):
    # flames above the deck
    cv.polygon([(x + 26, y + 62), (x + 36, y + 30), (x + 44, y + 48),
                (x + 52, y + 26), (x + 60, y + 62)], ORANGE)
    cv.polygon([(x + 34, y + 62), (x + 42, y + 42), (x + 50, y + 62)],
               YELLOW)
    cv.disc(x + 74, y + 30, 8, (168, 168, 168))
    cv.disc(x + 86, y + 22, 10, (188, 188, 188))
    # hull and superstructure
    cv.rect(x + 62, y + 58, 26, 18, WHITE)
    border_box(cv, x + 62, y + 58, 26, 18, INK, 1.8)
    cv.rect(x + 14, y + 72, 76, 7, RED)
    cv.polygon([(x + 4, y + 79), (x + 100, y + 79), (x + 88, y + 98),
                (x + 16, y + 98)], NAVY)
    # waves
    for wy in (y + 106, y + 116):
        pts = [(x + 4 + i * 6, wy + 3 * math.sin(i * 1.1))
               for i in range(17)]
        cv.polyline(pts, 2.4, OCEAN)


def icon_bridge(cv, x, y):
    for tx in (x + 22, x + 80):
        cv.rect(tx, y + 26, 7, 66, NAVY)
    cv.line(x + 25, y + 26, x + 6, y + 74, 2.2, GRAY)
    cv.line(x + 25, y + 26, x + 44, y + 74, 2.2, GRAY)
    cv.line(x + 83, y + 26, x + 62, y + 74, 2.2, GRAY)
    cv.line(x + 83, y + 26, x + 100, y + 74, 2.2, GRAY)
    # deck with a broken middle
    cv.line(x + 4, y + 74, x + 44, y + 74, 5, INK)
    cv.line(x + 62, y + 74, x + 102, y + 74, 5, INK)
    cv.line(x + 44, y + 74, x + 51, y + 84, 4, INK)
    cv.line(x + 62, y + 74, x + 55, y + 84, 4, INK)
    # starburst at the break
    cx, cy = x + 53, y + 66
    for i in range(8):
        a = 2 * math.pi * i / 8
        cv.line(cx + 5 * math.cos(a), cy + 5 * math.sin(a),
                cx + 13 * math.cos(a), cy + 13 * math.sin(a), 3, ORANGE)
    cv.disc(cx, cy, 4, RED)
    pts = [(x + 4 + i * 6, y + 104 + 3 * math.sin(i * 1.2))
           for i in range(17)]
    cv.polyline(pts, 2.4, OCEAN)


def icon_chart(cv, x, y):
    cv.line(x + 14, y + 12, x + 14, y + 100, 3.5, INK)
    cv.line(x + 14, y + 100, x + 100, y + 100, 3.5, INK)
    for i, bh in enumerate((22, 38, 56)):
        cv.rect(x + 24 + i * 22, y + 100 - bh, 15, bh, TEAL)
    pts = [(x + 22, y + 74), (x + 46, y + 56), (x + 66, y + 62),
           (x + 92, y + 28)]
    cv.polyline(pts, 5, RED)
    cv.polygon([(x + 92, y + 28), (x + 80, y + 30), (x + 88, y + 40)],
               RED)


# ------------------------------------------------------------------
# The front page
# ------------------------------------------------------------------

def panel(cv, x, y, w, h, icon, headline, sub):
    cv.rect(x, y, w, h, CARD)
    border_box(cv, x, y, w, h, NAVY, 2.5)
    icon(cv, x + 12, y + 14)
    tx = x + 134
    tw = w - 134 - 14
    size = fit_size(headline, 27, tw)
    lines = wrap_text(headline, size, tw)
    ly = y + 18
    for line in lines[:2]:
        draw_text(cv, tx, ly, line, size, INK)
        ly += size + 9
    sy = y + 88
    for line in wrap_text(sub, 18.5, tw)[:3]:
        draw_text(cv, tx, sy, line, 18.5, GRAY)
        sy += 24


def compose():
    cv = Canvas(W, H, PAPER)
    # page frame
    border_box(cv, 14, 14, W - 28, H - 28, INK, 5)
    border_box(cv, 25, 25, W - 50, H - 50, INK, 1.8)

    # ---- masthead ----
    draw_text(cv, W / 2, 42, "ONE DAY - ONE PICTURE - THE WHOLE WORLD",
              19, GRAY, align="center")
    title = "THE WORLD IN ONE DAY"
    ts = fit_size(title, 66, 940)
    draw_text(cv, W / 2, 70, title, ts, NAVY, align="center")
    cv.line(48, 158, W - 48, 158, 3, INK)
    # date band
    cv.rect(40, 172, W - 80, 66, INK)
    date = "THURSDAY 19 NOVEMBER 2026"
    ds = fit_size(date, 46, 900)
    draw_text(cv, W / 2, 172 + (66 - ds) / 2, date, ds, WHITE,
              align="center")
    cv.line(48, 252, W - 48, 252, 4, RED)

    # ---- lead story ----
    draw_text(cv, 48, 268, "LEAD STORY - SHENZHEN", 23, RED)
    head1 = "TRUMP, XI AND PUTIN MEET"
    head2 = "IN FIRST TRILATERAL SUMMIT"
    hs = fit_size(head2, 48, 928)
    draw_text(cv, 48, 302, head1, hs, INK)
    draw_text(cv, 48, 302 + hs + 14, head2, hs, INK)
    scene_y = 302 + 2 * hs + 34
    draw_lead_scene(cv, 48, scene_y, 440, 128)
    sub = ("\"PEACE DECLARATION\" ON NUCLEAR RISKS AND ENERGY, "
           "AGREED AT A 90-MINUTE MEETING - THE FIRST TIME THE "
           "LEADERS OF THE US, CHINA AND RUSSIA HAVE SAT DOWN "
           "TOGETHER.")
    sy = scene_y + 4
    for line in wrap_text(sub, 23, 452):
        draw_text(cv, 516, sy, line, 23, INK)
        sy += 30

    # ---- four panels ----
    pw, ph = 452, 148
    px = (48, 524)
    py = (566, 726)
    panel(cv, px[0], py[0], pw, ph, icon_scales,
          "WORLD COURT: MYANMAR COMMITTED GENOCIDE",
          "THE ICJ RULES ON THE ROHINGYA - THE FIRST RULING OF "
          "ITS KIND.")
    panel(cv, px[1], py[0], pw, ph, icon_tanker,
          "HORMUZ IN FLAMES AS IRAN WIDENS ATTACKS",
          "KUWAIT AND BAHRAIN HIT, TANKERS BURN - THE IEA CALLS "
          "IT THE GREATEST EVER THREAT TO ENERGY SECURITY.")
    panel(cv, px[0], py[1], pw, ph, icon_bridge,
          "UKRAINE HITS KERCH BRIDGE A THIRD TIME",
          "THE STRIKE ON THE CRIMEA LINK HALTS RAIL TRAFFIC - "
          "THE THIRD HIT IN FOUR DAYS.")
    panel(cv, px[1], py[1], pw, ph, icon_chart,
          "ANTHROPIC SETS AN IPO RECORD",
          "AN $81.3 BILLION RAISE VALUES THE AI COMPANY AT "
          "$1.5 TRILLION.")

    # ---- footer band ----
    cv.rect(40, 890, W - 80, 108, NAVY)
    foot = [
        "VAN GOGH SELLS FOR $190.4M - AN ARTIST RECORD AT SOTHEBY'S",
        "GTA VI LAUNCHES WORLDWIDE - THE WAIT IS OVER",
        "HOUTHI MISSILE DAMAGES SAUDI FUND TOWER IN RIYADH",
        "DENMARK BACKS GREENLAND DEFENCE DEAL, UNANIMOUSLY",
    ]
    fy = 900
    for line in foot:
        fs = fit_size(line, 20, 900)
        draw_text(cv, W / 2, fy, line, fs, WHITE, align="center")
        fy += 26

    return encode_png(cv.downscale(), W, H)


def main():
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    data = compose()
    path = os.path.join(outdir, "entry.png")
    with open(path, "wb") as fh:
        fh.write(data)
    print("wrote %s (%d bytes)" % (path, len(data)))


if __name__ == "__main__":
    main()
