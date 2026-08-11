#!/usr/bin/env python3
"""
Reusable helpers for building Tesla Custom Wraps programmatically instead
of hand-painting the template in an image editor. See README.md in this
folder for the full writeup of how these fit together and the gotchas found
building them (front vs rear license plate integration, template fitment
checking, the padding-before-warp bug, etc).
"""
import numpy as np
from PIL import Image, ImageDraw


def metallic_base(size, dark_rgb, light_rgb, seed=42, flake_strength=6.0, highlight_power=2.2):
    """A flat metallic-looking texture: diagonal highlight band (simulates
    light catching a curved body panel) + blurred fine noise (metal flake),
    tuned to stay compressible (pure per-pixel noise blows up PNG size well
    past Tesla's 1MB wrap limit - blur it slightly first)."""
    from PIL import ImageFilter
    W, H = size
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]

    dark = np.array(dark_rgb, dtype=np.float32)
    light = np.array(light_rgb, dtype=np.float32)
    band = np.sin((xx / W) * np.pi * 1.3 + (yy / H) * np.pi * 0.6 - 1.2)
    band = (band - band.min()) / (band.max() - band.min())
    band = band ** highlight_power
    color = dark[None, None, :] + (light - dark)[None, None, :] * band[:, :, None]

    flake = rng.normal(0, 1, (H, W)).astype(np.float32)
    flake_img = Image.fromarray(((flake - flake.min()) / (flake.max() - flake.min()) * 255).astype(np.uint8))
    flake_img = flake_img.filter(ImageFilter.GaussianBlur(radius=0.6))
    flake = (np.array(flake_img).astype(np.float32) - 127.5) / 127.5 * flake_strength
    color = np.clip(color + flake[:, :, None], 0, 255)

    base = Image.fromarray(color.astype(np.uint8), mode="RGB").convert("RGBA")
    base.putalpha(255)
    return base


def recolor_line_art(path, rgb=(225, 235, 250)):
    """Load a black-lines-on-white PNG/WEBP and turn it into a transparent
    RGBA image where the line color is `rgb` - handy for turning a plain
    clipart/coloring-book image into a decal that reads well on a dark
    metallic base. Also crops to the actual content bounding box."""
    src = Image.open(path).convert("L")
    arr = np.array(src).astype(np.float32)
    alpha = np.clip(255 - arr, 0, 255).astype(np.uint8)
    rgba = np.zeros((*arr.shape, 4), dtype=np.uint8)
    rgba[:, :, 0], rgba[:, :, 1], rgba[:, :, 2] = rgb
    rgba[:, :, 3] = alpha
    img = Image.fromarray(rgba, mode="RGBA")
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def pill_behind(logo_img, pad=10, fill=(255, 255, 255, 235)):
    """A rounded white pill placed behind a logo so it stays legible on a
    dark base (useful for any logo whose own colors are close in value to
    your base color and would otherwise blend in)."""
    pill = Image.new("RGBA", (logo_img.width + pad * 2, logo_img.height + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(pill)
    d.rounded_rectangle([0, 0, pill.width - 1, pill.height - 1], radius=pill.height // 2, fill=fill)
    return pill


def warp_trapezoid(img, inset):
    """Subtle trapezoid perspective warp (top edge pulled in by `inset` on
    each side) to suggest a curved surface, e.g. for a front license plate
    baked into a bumper panel.

    IMPORTANT gotcha: PIL's QUAD transform samples a NARROWER slice of the
    source at the inset edge. If you warp the image at its native size, that
    inset crops directly into your actual content (we cut a plate's edges
    off this way before catching it). Always pad with transparent margin
    equal to the inset FIRST, then warp the padded canvas - the inset then
    eats into the padding instead of your artwork.
    """
    pad = inset + 4
    padded = Image.new("RGBA", (img.width + pad * 2, img.height), (0, 0, 0, 0))
    padded.alpha_composite(img, (pad, 0))
    pw, ph = padded.size
    quad = (inset, 0, 0, ph, pw, ph, pw - inset, 0)
    return padded.transform((pw, ph), Image.QUAD, quad, resample=Image.BICUBIC)


def apply_template_mask(canvas, template_path):
    """Clip `canvas` (RGBA) to the exact silhouette of an official
    teslamotors/custom-wraps template.png, so anything painted outside the
    car's actual paintable panels (or into a cutout like a glass roof) gets
    discarded rather than showing up as a stray colored patch."""
    tmpl = Image.open(template_path).convert("RGBA")
    tmpl_alpha = np.array(tmpl)[:, :, 3]
    arr = np.array(canvas).astype(np.uint8)
    arr[:, :, 3] = tmpl_alpha
    return Image.fromarray(arr, mode="RGBA")
