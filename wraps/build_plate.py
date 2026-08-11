#!/usr/bin/env python3
"""
Generate a simple German/EU-style rear license plate background for
Tesla's Paint Shop "LicensePlate" feature.

Note: for anything more authentic than this (TUV inspection sticker,
state/city seal, E-suffix for electric vehicles, other countries), use the
dedicated open-source generator instead: https://license-plate.niklas.top/
(source: https://github.com/niklaswa/license-plate-generator). This script
is a minimal from-scratch fallback if you just want a plain plate quickly.

Usage:
    python build_plate.py "MS" "FB 234" "MS FB 234.png"
"""
import argparse
import math
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 420, 100  # matches Tesla's LicensePlate folder spec (community-tested)
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def find_font():
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return f
    return None


def make_plate(text_left, text_right, out_path, font_path=None):
    font_path = font_path or find_font()
    if not font_path:
        raise SystemExit("No bold font found - pass --font /path/to/font.ttf")

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W - 1, H - 1], outline="black", width=4)

    # EU blue band with 12 gold stars + country code
    band_w = 44
    d.rectangle([4, 4, band_w, H - 5], fill=(0, 51, 153))
    cx, cy, r = band_w / 2 + 2, 34, 13
    for i in range(12):
        angle = math.pi / 2 - i * (2 * math.pi / 12)
        sx, sy = cx + r * math.cos(angle), cy - r * math.sin(angle)
        star_r = 2.6
        pts = [
            (sx + (star_r if k % 2 == 0 else star_r * 0.45) * math.cos(math.pi / 2 + k * math.pi / 5),
             sy - (star_r if k % 2 == 0 else star_r * 0.45) * math.sin(math.pi / 2 + k * math.pi / 5))
            for k in range(10)
        ]
        d.polygon(pts, fill=(255, 204, 0))

    d_font = ImageFont.truetype(font_path, 20)
    bbox = d.textbbox((0, 0), "D", font=d_font)
    d.text((band_w / 2 + 2 - (bbox[2] - bbox[0]) / 2, 68), "D", font=d_font, fill="white")

    num_font = ImageFont.truetype(font_path, 62)
    full_text = f"{text_left}  {text_right}"
    bbox = d.textbbox((0, 0), full_text, font=num_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    text_x = band_w + 10 + (W - band_w - 10 - tw) / 2 - bbox[0]
    text_y = (H - th) / 2 - bbox[1]
    d.text((text_x, text_y), full_text, font=num_font, fill="black")

    # German plates use a small black separator pin/rivet, not a hyphen
    sep_bbox = d.textbbox((0, 0), text_left + "  ", font=num_font)
    pin_x = text_x + (sep_bbox[2] - sep_bbox[0]) - 14
    d.ellipse([pin_x, H / 2 - 4, pin_x + 8, H / 2 + 4], fill="black")

    img.save(out_path, optimize=True)
    print(f"{out_path}  {os.path.getsize(out_path) / 1024:.1f} KB  {img.size}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("left", help='Left group, e.g. city code "MS"')
    parser.add_argument("right", help='Right group, e.g. "FB 234"')
    parser.add_argument("out", help="Output PNG path")
    parser.add_argument("--font", help="Path to a bold TTF font (auto-detected if omitted)")
    args = parser.parse_args()
    make_plate(args.left, args.right, args.out, args.font)


if __name__ == "__main__":
    main()
