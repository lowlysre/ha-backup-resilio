"""Generate an original hero / GitHub social-preview image for this repo.

Draws a simple, original folder+sync+peers mark (no Resilio wordmark, logo,
or brand colors reused) plus a title/subtitle, entirely with Pillow
primitives so there's no dependency on any third-party artwork.

Usage: python tools/gen_social_preview.py
Outputs:
  docs/media/social-preview.png  (1280x640, for the repo's GitHub Settings ->
                                   General -> Social preview upload)
  docs/media/hero.png            (1280x400, for embedding at the top of
                                   README.md)
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "media"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FONT_DIR = Path(r"C:\Windows\Fonts")
FONT_BOLD = FONT_DIR / "segoeuib.ttf"
FONT_SEMIBOLD = FONT_DIR / "seguisb.ttf"
FONT_REGULAR = FONT_DIR / "segoeui.ttf"

# Original, non-Resilio palette: Home Assistant blue + a neutral slate/teal.
BG_TOP = (13, 20, 33)
BG_BOTTOM = (20, 30, 48)
SLATE = (100, 116, 139)
SLATE_LIGHT = (148, 163, 184)
HA_BLUE = (3, 169, 244)
TEAL = (45, 212, 191)
WHITE = (241, 245, 249)
DOT = (51, 65, 85)


def vertical_gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", size, top)
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        r = round(top[0] + (bottom[0] - top[0]) * t)
        g = round(top[1] + (bottom[1] - top[1]) * t)
        b = round(top[2] + (bottom[2] - top[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def draw_dot_grid(draw, size, spacing=28, radius=1, color=DOT):
    w, h = size
    for y in range(spacing, h, spacing):
        for x in range(spacing, w, spacing):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def draw_arrowhead(draw, tip, angle_deg, size, color):
    """Draw a small filled triangle arrowhead pointing along angle_deg at tip."""
    a = math.radians(angle_deg)
    back = math.radians(angle_deg + 180)
    spread = math.radians(28)
    p1 = tip
    p2 = (
        tip[0] + size * math.cos(back + spread),
        tip[1] + size * math.sin(back + spread),
    )
    p3 = (
        tip[0] + size * math.cos(back - spread),
        tip[1] + size * math.sin(back - spread),
    )
    draw.polygon([p1, p2, p3], fill=color)


def draw_sync_ring(draw, cx, cy, r, width, color):
    """Two ~150-degree arcs with arrowheads: a generic, non-brand-specific
    'sync' glyph (the same universal two-arrow-circle used by refresh icons
    across countless apps/OSes, not a copy of any single product's logo).
    """
    bbox = (cx - r, cy - r, cx + r, cy + r)
    draw.arc(bbox, start=-160, end=-10, fill=color, width=width)
    draw.arc(bbox, start=20, end=170, fill=color, width=width)

    def point_at(deg):
        rad = math.radians(deg)
        return (cx + r * math.cos(rad), cy + r * math.sin(rad))

    draw_arrowhead(draw, point_at(-10), -10 + 90, width * 1.6, color)
    draw_arrowhead(draw, point_at(170), 170 + 90, width * 1.6, color)


def draw_folder(draw, x, y, w, h, color):
    """A plain, generic folder glyph: back tab + front body, both rounded
    rectangles. Purely geometric, no third-party iconography referenced.
    """
    tab_w = w * 0.42
    tab_h = h * 0.18
    draw.rounded_rectangle(
        (x, y, x + tab_w, y + tab_h * 1.6), radius=h * 0.05, fill=color
    )
    body_y = y + tab_h
    draw.rounded_rectangle(
        (x, body_y, x + w, y + h), radius=h * 0.08, fill=color
    )


def draw_mark(img, cx, cy, scale=1.0):
    draw = ImageDraw.Draw(img, "RGBA")

    folder_w, folder_h = 260 * scale, 190 * scale
    fx = cx - folder_w * 0.55
    fy = cy - folder_h * 0.42
    draw_folder(draw, fx, fy, folder_w, folder_h, SLATE)

    # Peer nodes connected to the folder by dashed lines - represents
    # replication to other Resilio-connected devices (no logo involved).
    peers = [
        (cx + 210 * scale, cy - 150 * scale),
        (cx + 250 * scale, cy + 40 * scale),
        (cx + 150 * scale, cy + 190 * scale),
    ]
    anchor = (cx + 20 * scale, cy + 20 * scale)
    for px, py in peers:
        steps = 14
        for i in range(steps):
            if i % 2:
                continue
            t0 = i / steps
            t1 = (i + 1) / steps
            x0 = anchor[0] + (px - anchor[0]) * t0
            y0 = anchor[1] + (py - anchor[1]) * t0
            x1 = anchor[0] + (px - anchor[0]) * t1
            y1 = anchor[1] + (py - anchor[1]) * t1
            draw.line((x0, y0, x1, y1), fill=TEAL + (200,), width=max(2, int(3 * scale)))
        r = 10 * scale
        draw.ellipse((px - r, py - r, px + r, py + r), outline=TEAL, width=max(2, int(3 * scale)))
        draw.ellipse(
            (px - r * 0.45, py - r * 0.45, px + r * 0.45, py + r * 0.45), fill=TEAL
        )

    # Sync ring badge over the folder's corner.
    ring_cx = fx + folder_w * 0.98
    ring_cy = fy + folder_h * 0.1
    draw_sync_ring(draw, ring_cx, ring_cy, r=62 * scale, width=max(6, int(11 * scale)), color=HA_BLUE)


def render(width, height, out_path, title=True):
    img = vertical_gradient((width, height), BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(img, "RGBA")
    draw_dot_grid(draw, (width, height))

    mark_cx = width * 0.235
    mark_cy = height * 0.52
    draw_mark(img, mark_cx, mark_cy, scale=height / 640)

    if title:
        draw = ImageDraw.Draw(img, "RGBA")
        title_font = ImageFont.truetype(str(FONT_BOLD), int(height * 0.115))
        subtitle_font = ImageFont.truetype(str(FONT_REGULAR), int(height * 0.045))
        tag_font = ImageFont.truetype(str(FONT_SEMIBOLD), int(height * 0.032))

        text_x = width * 0.46
        title_y = height * 0.36
        draw.text((text_x, title_y), "Resilio Backup", font=title_font, fill=WHITE)

        subtitle_y = title_y + int(height * 0.155)
        draw.text(
            (text_x, subtitle_y),
            "Home Assistant backups, replicated with Resilio Sync",
            font=subtitle_font,
            fill=SLATE_LIGHT,
        )

        tag_y = subtitle_y + int(height * 0.11)
        tag_text = "HACS CUSTOM INTEGRATION"
        pad_x, pad_y = int(height * 0.02), int(height * 0.014)
        tbbox = draw.textbbox((0, 0), tag_text, font=tag_font)
        tw, th = tbbox[2] - tbbox[0], tbbox[3] - tbbox[1]
        draw.rounded_rectangle(
            (text_x, tag_y, text_x + tw + pad_x * 2, tag_y + th + pad_y * 2),
            radius=int(height * 0.02),
            outline=HA_BLUE,
            width=2,
        )
        draw.text((text_x + pad_x, tag_y + pad_y - tbbox[1]), tag_text, font=tag_font, fill=HA_BLUE)

    img.save(out_path)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    render(1280, 640, OUT_DIR / "social-preview.png", title=True)
    render(1280, 400, OUT_DIR / "hero.png", title=True)
