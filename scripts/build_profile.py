"""Build Vamsi's GitHub profile README panels as crisp, self-contained SVGs.

GitHub strips custom CSS from READMEs, so each styled panel is rendered as an SVG
with embedded IBM Plex Mono WOFF2 fonts and an 8x8 Bayer-dithered animated aurora.

Usage: python3 scripts/build_profile.py
"""

import base64
import hashlib
import io
import math
import random
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONTS = ROOT / "fonts"

# Panels are drawn at 880 units (matching GitHub's README column width).
W = 880

# Midnight monochrome palette with electric blue accent.
MIDNIGHT = "#02070A"
SURFACE = "#071017"
SURFACE_2 = "#0B1620"
LINE = "#16232D"
LINE_STRONG = "#1E5A80"
TEXT = "#E6EDF2"
SECOND = "#8B98A4"
MUTED = "#52606B"
ACCENT = "#0297DE"
OK = "#3FB950"
WARN = "#D29922"
AURORA = ["#02070A", "#0A2A4A", "#0E4F80", "#0297DE", "#FFFFFF"]

MONO_ADVANCE = 0.6  # IBM Plex Mono advance per em


# ---------------------------------------------------------------- fonts & svg helpers

def font_faces() -> str:
    rules = []
    for weight, filename in ((400, "mono-400.woff2"), (500, "mono-500.woff2")):
        data = base64.b64encode((FONTS / filename).read_bytes()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:IBM;font-weight:{weight};font-style:normal;"
            f"src:url(data:font/woff2;base64,{data}) format('woff2')}}"
        )
    return "".join(rules)


FONT_STYLE = font_faces()


def svg_doc(width: int, height: int, title: str, body: list[str], extra_style: str = "") -> str:
    style = (
        FONT_STYLE
        + f"text{{font-family:IBM,'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;"
        f"fill:{SECOND};white-space:pre}}"
        f".p{{fill:{TEXT}}}.m{{fill:{MUTED}}}.a{{fill:{ACCENT}}}.ok{{fill:{OK}}}.warn{{fill:{WARN}}}.w{{font-weight:500}}"
        "image{image-rendering:pixelated}"
        + extra_style
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">'
        f"<title>{escape(title)}</title><style>{style}</style>{''.join(body)}</svg>\n"
    )


def txt(x: float, y: float, content: str, size: int = 14, cls: str = "", anchor: str = "start") -> str:
    c = f' class="{cls}"' if cls else ""
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text x="{x:g}" y="{y:g}" font-size="{size}"{c}{a} xml:space="preserve">{escape(content)}</text>'


def rect(x: float, y: float, w: float, h: float, fill: str = "none", stroke: str = "", rx: float = 0) -> str:
    r_attr = f' rx="{rx:g}"' if rx else ""
    if stroke:
        return (
            f'<rect x="{x + 0.5:g}" y="{y + 0.5:g}" width="{w - 1:g}" height="{h - 1:g}"'
            f'{r_attr} fill="{fill}" stroke="{stroke}"/>'
        )
    return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}"{r_attr} fill="{fill}"/>'


def hline(x1: float, x2: float, y: float, color: str = LINE) -> str:
    return f'<line x1="{x1:g}" y1="{y + 0.5:g}" x2="{x2:g}" y2="{y + 0.5:g}" stroke="{color}"/>'


def vline(x: float, y1: float, y2: float, color: str = LINE) -> str:
    return f'<line x1="{x + 0.5:g}" y1="{y1:g}" x2="{x + 0.5:g}" y2="{y2:g}" stroke="{color}"/>'


def window_bar(x: float, y: float, w: float, index: str, label: str, note: str = "") -> list[str]:
    h = 28
    parts = [
        rect(x, y, w, h, SURFACE),
        hline(x, x + w, y + h - 1, LINE),
        rect(x + 8, y + 6, 16, 16, "#0B2233"),
        txt(x + 16, y + 18, index, 12, "a w", "middle"),
        txt(x + 32, y + 18, label, 12, "p w"),
    ]
    if note:
        parts.append(txt(x + w - 12, y + 18, note, 12, "m", "end"))
    return parts


def png_data(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------- 8x8 Bayer dithered aurora

BAYER8 = [
    [(v / 64.0) + (1.0 / 128.0) for v in row]
    for row in (
        (0, 32, 8, 40, 2, 34, 10, 42),
        (48, 16, 56, 24, 50, 18, 58, 26),
        (12, 44, 4, 36, 14, 46, 6, 38),
        (60, 28, 52, 20, 62, 30, 54, 22),
        (3, 35, 11, 43, 1, 33, 9, 41),
        (51, 19, 59, 27, 49, 17, 57, 25),
        (15, 47, 7, 39, 13, 45, 5, 37),
        (63, 31, 55, 23, 61, 29, 53, 21),
    )
]


class Noise2D:
    """Fast pure-Python 2D gradient noise with precomputed permutation & gradient tables."""

    def __init__(self, seed: int = 7) -> None:
        rng = random.Random(seed)
        p = list(range(256))
        rng.shuffle(p)
        self.perm = p + p
        angles = [rng.uniform(0, 2.0 * math.pi) for _ in range(256)]
        self.gx = [math.cos(a) for a in angles]
        self.gy = [math.sin(a) for a in angles]

    def sample(self, x: float, y: float) -> float:
        xi = math.floor(x)
        yi = math.floor(y)
        xf = x - xi
        yf = y - yi
        xi &= 255
        yi &= 255

        perm = self.perm
        gx = self.gx
        gy = self.gy

        p0 = perm[xi] + yi
        p1 = perm[xi + 1] + yi

        g00 = perm[p0] & 255
        g10 = perm[p1] & 255
        g01 = perm[p0 + 1] & 255
        g11 = perm[p1 + 1] & 255

        n00 = gx[g00] * xf + gy[g00] * yf
        n10 = gx[g10] * (xf - 1.0) + gy[g10] * yf
        n01 = gx[g01] * xf + gy[g01] * (yf - 1.0)
        n11 = gx[g11] * (xf - 1.0) + gy[g11] * (yf - 1.0)

        u = xf * xf * xf * (xf * (xf * 6.0 - 15.0) + 10.0)
        v = yf * yf * yf * (yf * (yf * 6.0 - 15.0) + 10.0)

        top = n00 + u * (n10 - n00)
        bottom = n01 + u * (n11 - n01)
        return (top + v * (bottom - top)) * 1.9

    def fbm(self, x: float, y: float) -> float:
        total = 0.0
        amp = 0.5
        for _ in range(4):
            total += amp * (self.sample(x, y) * 0.5 + 0.5)
            x *= 2.02
            y *= 2.02
            amp *= 0.5
        val = 0.5 + (total / 0.9375 - 0.5) * 2.4
        if val <= 0.0:
            return 0.0
        if val >= 1.0:
            return 1.0
        return val


def smoothstep(e0: float, e1: float, x: float) -> float:
    k = (x - e0) / (e1 - e0)
    if k <= 0.0:
        return 0.0
    if k >= 1.0:
        return 1.0
    return k * k * (3.0 - 2.0 * k)


def aurora_frame(noise: Noise2D, cols: int, rows: int, t: float) -> Image.Image:
    curtains = 4
    height = 0.38
    spread = 0.06
    sway = 1.4
    turbulence = 0.8
    rays = 12.0
    length = 0.85
    glow = 1.1
    intensity = 0.95
    drift = 0.25
    decay = 15.0 + (2.2 - 15.0) * length
    colors_n = len(AURORA)
    aspect = cols / rows

    # Precompute column-dependent curtain edge/ray/patch terms (constant over y for a given t!)
    x_vals = [(((c + 0.5) / cols) - 0.5) * aspect + t * drift * 0.04 for c in range(cols)]
    curtain_cols: list[list[tuple[float, float, float]]] = []
    for i in range(curtains):
        depth = i / max(curtains - 1, 1)
        depth_weight = 1.0 - 0.5 * depth
        t_edge = t * 0.035 + i * 1.7
        t_turb = t * 0.07 + i
        t_rx = t * 0.03 + i
        t_ray = t * 0.045 + i
        t_ray2 = i * 4.0 + t * 0.02
        t_patch = t * 0.02 + i * 2.0
        decay_i = decay * (1.0 + i * 0.4)

        col_data: list[tuple[float, float, float]] = []
        for x in x_vals:
            edge = (
                height
                + i * spread
                + sway * 0.11 * noise.sample(x * 0.55 + i * 3.1, t_edge)
                + turbulence * 0.05 * noise.sample(x * 2.1 - i * 1.3, t_turb)
            )
            rx = (x + noise.sample(x * 0.8, t_rx) * (0.25 + 0.35 * sway)) * rays
            ray = 0.2 + 0.8 * smoothstep(0.25, 0.75, noise.fbm(rx + i * 9.0, t_ray))
            ray *= 0.75 + 0.25 * noise.sample(rx * 3.2, t_ray2)
            patch = 0.3 + 0.7 * smoothstep(0.25, 0.7, noise.fbm(x * 0.45 + i * 5.0, t_patch))
            col_data.append((edge, ray, patch * depth_weight, decay_i))  # type: ignore[arg-type]
        curtain_cols.append(col_data)  # type: ignore[arg-type]

    buf = bytearray(cols * rows)
    exp = math.exp
    scale_colors = colors_n - 1
    for r in range(rows):
        py = 1.0 - (r + 0.5) / rows
        b_row = BAYER8[r & 7]
        row_off = r * cols
        for c in range(cols):
            light = 0.0
            for i in range(curtains):
                edge, ray, pw, decay_i = curtain_cols[i][c]  # type: ignore[misc]
                above = py - edge
                abs_above = above if above >= 0.0 else -above
                if above > 0.0:
                    curtain = exp(-abs_above * decay_i)
                    haze = exp(-abs_above * 5.0) * 0.09
                else:
                    curtain = exp(-abs_above * 48.0)
                    haze = exp(-abs_above * 14.0) * 0.05
                rim = exp(-abs_above * 34.0) * glow
                light += (curtain * ray + rim * (0.5 + 0.5 * ray) + haze) * pw

            tone = (1.0 - exp(-light * 1.25)) * intensity
            if tone < 0.0:
                tone = 0.0
            elif tone > 1.0:
                tone = 1.0
            scaled = tone * scale_colors
            idx = int(scaled)
            if scaled - idx > b_row[c & 7] and idx < scale_colors:
                idx += 1
            buf[row_off + c] = idx

    img = Image.frombytes("P", (cols, rows), bytes(buf))
    flat: list[int] = []
    for hex_c in AURORA:
        flat.extend((int(hex_c[1:3], 16), int(hex_c[3:5], 16), int(hex_c[5:7], 16)))
    img.putpalette(flat)
    return img


FRAMES = 14
SECONDS_PER_FRAME = 0.24
TIME_SCALE = 2.0


def animated_frames(frames: list[str], x: float, y: float, w: float, h: float) -> list[str]:
    order = list(range(len(frames))) + list(range(len(frames) - 2, 0, -1))
    steps = len(order)
    times = ";".join(f"{k / steps:.4f}" for k in range(steps))
    duration = steps * SECONDS_PER_FRAME
    parts = []
    for n, data in enumerate(frames):
        values = ";".join("1" if f == n else "0" for f in order)
        uri = f"data:image/png;base64,{data}"
        parts.append(
            f'<image x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" preserveAspectRatio="none" '
            f'href="{uri}" xlink:href="{uri}" opacity="{1 if n == 0 else 0}">'
            f'<animate attributeName="opacity" values="{values}" keyTimes="{times}" '
            f'dur="{duration:g}s" calcMode="discrete" repeatCount="indefinite"/></image>'
        )
    return parts


# ---------------------------------------------------------------- header panel (880 x 284)

def build_header() -> str:
    strip, scene_h, details_h = 28, 140, 116
    H = strip + scene_h + details_h
    cell = 2
    noise = Noise2D(seed=7)
    frames = []
    for n in range(FRAMES):
        t = 11.0 + n * SECONDS_PER_FRAME * TIME_SCALE
        scene = aurora_frame(noise, W // cell, scene_h // cell, t)
        frames.append(png_data(scene.resize((scene.width * 2, scene.height * 2), Image.NEAREST)))

    body = [
        rect(0, 0, W, H, MIDNIGHT),
        rect(0, 0, W, strip, SURFACE),
        txt(12, 19, "Vamsi", 12, "p w"),
        txt(92, 19, "BUILDING", 12, "p w"),
        txt(W - 12, 19, "github.com/bvamc", 12, "m", "end"),
        *animated_frames(frames, 0, strip, W, scene_h),
        hline(0, W, strip - 1),
    ]

    # Four pixels cycle clockwise to mark active building.
    extra_style = (
        "@keyframes building{0%,24%{opacity:1}25%,100%{opacity:.2}}"
        ".building{animation:building 1.2s steps(1,end) infinite}"
        "@media(prefers-reduced-motion:reduce){.building{animation:none}}"
    )
    for step, (px, py) in enumerate(((71, 10), (77, 10), (77, 16), (71, 16))):
        body.append(
            f'<rect class="building" x="{px}" y="{py}" width="4" height="4" '
            f'fill="{ACCENT}" style="animation-delay:-{(4 - step) * 0.3:g}s"/>'
        )

    # 3-column bento bar below the aurora
    top = strip + scene_h
    col1, col2 = 376, 592
    body += [
        rect(0, top, W, details_h, MIDNIGHT),
        hline(0, W, top),
        f'<text x="24" y="{top + 56}" font-size="48" '
        f'style="font-family:Arial,Helvetica,sans-serif;letter-spacing:-1.8px" '
        f'class="p">Vamsi</text>',
        txt(24, top + 84, "Software Engineer", 13.5, "p"),
        vline(col1, top, H),
        vline(col2, top, H),
        txt(col1 + 20, top + 32, "WORKING AT", 10, "m"),
        txt(col1 + 20, top + 60, "Amazon FinTech", 13, "p w"),
        txt(col1 + 20, top + 82, "financial platforms", 12, ""),
        txt(col2 + 20, top + 32, "FOCUS", 10, "m"),
        txt(col2 + 20, top + 60, "distributed systems", 13, "p w"),
        txt(col2 + 20, top + 82, "AI workflows & agent infra", 12, "a"),
    ]

    body.append(rect(0, 0, W, H, "none", LINE))
    return svg_doc(
        W,
        H,
        "Vamsi (bvamc): Software Engineer at Amazon FinTech. Focused on distributed systems, AI workflows & agent infra.",
        body,
        extra_style,
    )


# ---------------------------------------------------------------- project tile 1: whatsloaded (440 x 307)

def build_tile_whatsloaded() -> str:
    half = W // 2
    ih = round(half * 630 / 1200)  # 231
    H = 28 + ih + 48  # 307
    body = [rect(0, 0, half, H, MIDNIGHT)]
    body += window_bar(0, 0, half, "2", "whatsloaded", "claude · codex · kiro")

    # Preview canvas (y: 28 .. 259)
    cy = 28
    body.append(rect(0, cy, half, ih, "#040A0E"))

    # Inner miniature window card
    px, py, pw, ph = 18, cy + 16, half - 36, ih - 32
    body.append(rect(px, py, pw, ph, SURFACE, LINE))
    body.append(rect(px + 1, py + 1, pw - 2, 24, SURFACE_2))
    body.append(hline(px, px + pw, py + 24, LINE))
    body.append(txt(px + 12, py + 16, "❯ whatsloaded matrix · doctor", 11, "p w"))
    body.append(txt(px + pw - 12, py + 16, "127.0.0.1:4319", 10, "a", "end"))

    # Cross-tool matrix rows (pixel-aligned columns)
    col_x = (px + 12, px + 118, px + 174, px + 228)
    body.append(txt(col_x[0], py + 44, "SERVER", 10, "m"))
    body.append(txt(col_x[1], py + 44, "claude", 10, "m"))
    body.append(txt(col_x[2], py + 44, "codex", 10, "m"))
    body.append(txt(col_x[3], py + 44, "kiro", 10, "m"))
    body.append(txt(px + pw - 12, py + 44, "tokens", 10, "m", "end"))
    rows = [
        ("github", "u p", "u", "u a", "~5.4k", "ok", "warn"),
        ("playwright", "u", "u", "·", "~4.2k", "ok", "ok"),
        ("postgres-mcp", "l", "·", "·", "missing", "ok", "warn"),
        ("linear", "-u", "·", "a", "~3.1k", "m", "ok"),
    ]
    for i, (name, c1, c2, c3, tok, st1, st2) in enumerate(rows):
        ry = py + 62 + i * 18
        body.append(txt(col_x[0], ry, name, 10.5, "p"))
        body.append(txt(col_x[1], ry, c1, 10.5, st1))
        body.append(txt(col_x[2], ry, c2, 10.5, st2))
        body.append(txt(col_x[3], ry, c3, 10.5, "a" if c3 != "·" else "m"))
        body.append(txt(px + pw - 12, ry, tok, 10.5, "warn" if tok == "missing" else "p", "end"))

    # Context token bar + footer inside preview card
    by = py + ph - 52
    body.append(hline(px, px + pw, by, LINE))
    body.append(txt(px + 12, by + 18, "context budget", 10, "m"))
    body.append(txt(px + pw - 12, by + 18, "12.7k used · 3 idle (30d)", 10, "a", "end"))
    body.append(rect(px + 12, by + 26, pw - 24, 6, "#0B1620"))
    body.append(rect(px + 12, by + 26, 210, 6, ACCENT))
    body.append(rect(px + 222, by + 26, 78, 6, WARN))
    body.append(txt(px + 12, by + 44, "AST-safe diffs · undo manifest ready", 10, "ok"))

    # Tile footer bar
    fy = 28 + ih
    body.append(hline(0, half, fy, LINE))
    body.append(txt(16, fy + 29, "See & manage what your AI agents load", 13, "p"))
    body.append(txt(half - 16, fy + 29, "cli / web", 12, "m", "end"))
    body.append(rect(0, 0, half, H, "none", LINE))
    return svg_doc(half, H, "whatsloaded: See & manage what your AI agents load", body)


# ---------------------------------------------------------------- project tile 2: CleanTabs (440 x 307)

def build_tile_cleantabs() -> str:
    half = W // 2
    ih = round(half * 630 / 1200)  # 231
    H = 28 + ih + 48  # 307
    body = [rect(0, 0, half, H, MIDNIGHT)]
    body += window_bar(0, 0, half, "3", "CleanTabs", "chrome mv3 · local ai")

    # Preview canvas (y: 28 .. 259)
    cy = 28
    body.append(rect(0, cy, half, ih, "#040A0E"))

    # Inner miniature cockpit
    px, py, pw, ph = 18, cy + 16, half - 36, ih - 32
    body.append(rect(px, py, pw, ph, SURFACE, LINE))
    body.append(rect(px + 1, py + 1, pw - 2, 24, SURFACE_2))
    body.append(hline(px, px + pw, py + 24, LINE))
    body.append(txt(px + 12, py + 16, "topic clusters · on-device LanguageModel", 11, "p w"))
    body.append(txt(px + pw - 12, py + 16, "42 tabs", 10, "a", "end"))

    # 3 cluster cards side-by-side
    clusters = [
        ("Distributed Sys", "11 tabs", ["raft-paper.pdf", "temporal-go/sdk", "kafka-acks.md"], ACCENT),
        ("AI Tooling", "8 tabs", ["modelcontext.io", "claude-hooks", "mcp-inspector"], OK),
        ("Duplicates", "6 stale", ["localhost:3000 ×3", "github/pulls ×2", "docs-search ×2"], WARN),
    ]
    cw = (pw - 36) // 3
    for idx, (title, count, items, color) in enumerate(clusters):
        cx = px + 12 + idx * (cw + 6)
        cy_card = py + 36
        body.append(rect(cx, cy_card, cw, 110, MIDNIGHT, LINE))
        body.append(rect(cx + 1, cy_card + 1, cw - 2, 3, color))
        body.append(txt(cx + 8, cy_card + 20, title, 10, "p w"))
        body.append(txt(cx + 8, cy_card + 33, count, 9.5, "a" if color == ACCENT else ("ok" if color == OK else "warn")))
        body.append(hline(cx, cx + cw, cy_card + 42, LINE))
        for j, item in enumerate(items):
            body.append(txt(cx + 8, cy_card + 58 + j * 16, item, 9.5, ""))

    # Bottom restore snapshot bar
    by = py + ph - 34
    body.append(hline(px, px + pw, by, LINE))
    body.append(txt(px + 12, by + 21, "● restore snapshot saved before close · zero cloud sync", 10, "ok"))

    # Tile footer bar
    fy = 28 + ih
    body.append(hline(0, half, fy, LINE))
    body.append(txt(16, fy + 29, "Clean messy browser sessions locally", 13, "p"))
    body.append(txt(half - 16, fy + 29, "extension", 12, "m", "end"))
    body.append(rect(0, 0, half, H, "none", LINE))
    return svg_doc(half, H, "CleanTabs: Clean messy browser sessions locally", body)


# ---------------------------------------------------------------- link chips (height 36)

ICONS = {
    "linkedin": (
        '<path fill="{c}" d="M6.94 5a2 2 0 1 1-4-.002 2 2 0 0 1 4 .002zM7 8.48H3V21h4V8.48zm6.32 0H9.34V21h3.94v-6.57'
        'c0-3.66 4.77-4 4.77 0V21H22v-7.93c0-6.17-7.06-5.94-8.72-2.91l.04-1.68z"/>'
    ),
    "mail": (
        '<g fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="2" y="4" width="20" height="16" rx="2"/>'
        '<path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></g>'
    ),
}


def build_chip(icon: str, label: str) -> str:
    h = box = 36
    width = int(box + 12 + len(label + "  ↗") * 13 * MONO_ADVANCE + 14)
    width += width % 2
    body = [
        rect(0, 0, width, h, MIDNIGHT),
        f'<g transform="translate({(box - 16) / 2} {(h - 16) / 2}) scale({16 / 24})">'
        + ICONS[icon].format(c=SECOND)
        + "</g>",
        vline(box, 0, h, LINE),
        txt(box + 12, 23, label, 13, "p"),
        txt(width - 12, 23, "↗", 13, "m", "end"),
        rect(0, 0, width, h, "none", LINE),
    ]
    return svg_doc(width, h, label, body)


# ---------------------------------------------------------------- main

def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    outputs = {
        "header.svg": build_header(),
        "tile-whatsloaded.svg": build_tile_whatsloaded(),
        "tile-cleantabs.svg": build_tile_cleantabs(),
        "chip-linkedin.svg": build_chip("linkedin", "linkedin.com/in/vamsidharbada"),
        "chip-email.svg": build_chip("mail", "vamsidharreddybada@gmail.com"),
    }

    hashes: dict[str, str] = {}
    for name, content in outputs.items():
        ET.fromstring(content)
        out_path = ASSETS / name
        out_path.write_text(content, encoding="utf-8")
        hashes[name] = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
        print(f"{name}: {len(content.encode('utf-8')) // 1024} KB (valid XML)")

    readme_html = (
        f'<p align="center"><img src="./assets/header.svg?v={hashes["header.svg"]}" width="100%" '
        f'alt="Vamsi (bvamc): Software Engineer at Amazon FinTech in Seattle, WA. '
        f'Focused on distributed systems and AI workflows."></p>\n\n'
        f'<a href="https://github.com/bvamc/whatsloaded"><img src="./assets/tile-whatsloaded.svg?v={hashes["tile-whatsloaded.svg"]}" '
        f'width="50%" alt="whatsloaded: See &amp; manage what your AI agents load"></a>'
        f'<a href="https://github.com/bvamc/CleanTabs"><img src="./assets/tile-cleantabs.svg?v={hashes["tile-cleantabs.svg"]}" '
        f'width="50%" alt="CleanTabs: Clean messy browser sessions locally"></a>\n\n'
        f'<p align="center">'
        f'<a href="https://www.linkedin.com/in/vamsidharbada/"><img src="./assets/chip-linkedin.svg?v={hashes["chip-linkedin.svg"]}" height="36" alt="LinkedIn"></a> '
        f'<a href="mailto:vamsidharreddybada@gmail.com"><img src="./assets/chip-email.svg?v={hashes["chip-email.svg"]}" height="36" alt="Email"></a>'
        f'</p>\n'
    )
    (ROOT / "README.md").write_text(readme_html, encoding="utf-8")
    print("Updated README.md with cache-busted SVG embeds.")


if __name__ == "__main__":
    main()
