#!/usr/bin/env python3
"""
Check whether a downloaded/community Tesla wrap ("skin") actually matches
your specific vehicle's Custom Wraps template.

Why this matters: community wrap-sharing sites (e.g. tesla-wrap.com) host
thousands of designs tagged by model, but it's easy to end up with one built
for the WRONG variant - most commonly a pre-2025 "Model Y" design applied to
a 2025+ Model Y Premium/Performance (or vice versa), or a Model 3 design
mistaken for Model Y. These share a similar overall layout (top arch, two
side panels, tapering bottom piece) at a glance, but the panel cut lines
differ enough that the wrap will look misaligned once applied.

This script compares a skin's alpha channel against every official
teslamotors/custom-wraps template and reports the best match by IoU
(intersection-over-union of the "paintable" pixels). A correct fit scores
~0.95-1.00; a wrong-model skin usually scores 0.4-0.6.

Usage:
    python check_skin_fit.py my_skin.png templates/
    python check_skin_fit.py my_skin.png templates/modely_template.png
"""
import argparse
import glob
import os

import numpy as np
from PIL import Image


def load_mask(path, target_size=(1024, 1024)):
    img = Image.open(path).convert("RGBA")
    if img.size != target_size:
        img = img.resize(target_size)
    return np.array(img)[:, :, 3] > 127


def iou(mask_a, mask_b):
    inter = np.logical_and(mask_a, mask_b).sum()
    union = np.logical_or(mask_a, mask_b).sum()
    return inter / union if union else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("skin", help="Path to the wrap/skin PNG to check")
    parser.add_argument("templates", help="A single template PNG, or a folder of template PNGs to compare against")
    args = parser.parse_args()

    if not os.path.exists(args.skin):
        raise SystemExit(f"Skin file not found: {args.skin}")

    skin_img = Image.open(args.skin)
    if skin_img.mode != "RGBA" or skin_img.getchannel("A").getextrema() == (255, 255):
        print(f"WARNING: {args.skin} has no real transparency (mode={skin_img.mode}). "
              "If it's meant to be a wrap, it's likely missing its alpha mask - "
              "apply the correct template's alpha channel to it before use.")

    skin_mask = load_mask(args.skin)

    if os.path.isdir(args.templates):
        template_paths = sorted(glob.glob(os.path.join(args.templates, "*.png")))
    else:
        template_paths = [args.templates]

    results = []
    for p in template_paths:
        try:
            tmask = load_mask(p)
        except Exception as e:
            print(f"  (skipping {p}: {e})")
            continue
        results.append((iou(skin_mask, tmask), os.path.basename(p)))

    results.sort(reverse=True)
    print(f"\nBest matches for {os.path.basename(args.skin)}:")
    for score, name in results[:5]:
        flag = "  <-- likely correct fit" if score > 0.9 else ("  <-- WRONG MODEL/TRIM" if score < 0.7 else "")
        print(f"  {score:.3f}  {name}{flag}")


if __name__ == "__main__":
    main()
