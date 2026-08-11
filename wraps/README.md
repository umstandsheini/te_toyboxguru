# Tesla Custom Wraps & License Plates

Notes and small tools built while making custom Paint Shop wraps and license
plates for a Tesla, on top of [teslamotors/custom-wraps](https://github.com/teslamotors/custom-wraps).
Tesla's own repo covers the *Wraps* feature reasonably well; the *License
Plate* feature and several practical gotchas below aren't documented
anywhere official.

## Two separate features, two separate USB folders

| | Folder | Size limit | Dimensions | Filename limit |
|---|---|---|---|---|
| Wraps | `Wraps` (root of USB) | 1 MB | 512-1024px, square | 30 chars, alphanumeric + `_` `-` space |
| License Plate | `LicensePlate` (root of USB) | 0.5 MB | 420x100 (EU) / 420x200 (US) - varies by region, community-tested | 32 chars, alphanumeric only |

The `LicensePlate` folder isn't mentioned in Tesla's own repo at all - there's
an [open issue asking for it to be documented](https://github.com/teslamotors/custom-wraps/issues/13).
Both folders must sit at the USB root (not nested), and per Tesla's existing
Wraps requirements the drive shouldn't also contain map/firmware update files
or (for a drive that's also used for TeslaCam) a root-level `TeslaCam` folder.

## Front plate vs rear plate: two completely different mechanisms

This tripped us up initially. Per community testing ([tff-forum.de](https://tff-forum.de/t/custom-wraps-tauschboerse/404754/37)):

- **Rear plate**: rendered through a separate **digital plate holder** (its
  own 3D element), fed by the `LicensePlate` folder file. Straightforward,
  no relation to your wrap texture at all.
- **Front plate**: there's no such holder - the plate has to be **painted
  directly into the wrap PNG itself**, at the front bumper panel, and it
  needs to be slightly warped/perspective-distorted to look right on that
  panel's curve. See `wrap_helpers.warp_trapezoid` below.

If you only add a rear plate and wonder why the front looks blank (or still
shows the stock plate), this is why - they're unrelated features.

### Gotchas found building the front plate

- **Pad before you warp, not after.** `PIL.Image.transform(..., Image.QUAD)`
  samples a *narrower slice of the source* at whichever edge you inset for
  the perspective effect. If you warp the plate image at its native size,
  that inset crops directly into the plate's own edge content (we cut the
  left/right edges of a plate clean off this way). Add transparent padding
  equal to the inset first, then warp the padded canvas - now the inset eats
  into the padding instead of the artwork. See `warp_trapezoid()`.
- **The panel may render upside down.** On the Model Y template used here,
  the front bumper panel's UV mapping displays whatever you paint there
  rotated 180 degrees in the in-car 3D preview. There's no way to know this
  in advance from the flat 2D template - place a test plate, look at it in
  the car (or ask whoever's testing for you), and rotate 180 if needed. This
  might be template/model-specific rather than universal.
- Real license plate generation is its own rabbit hole (TUV inspection
  stickers, state/city seals, E-suffix for EVs, other countries' formats) -
  don't reinvent this. Use the dedicated open-source generator instead:
  [license-plate.niklas.top](https://license-plate.niklas.top/) ([source](https://github.com/niklaswa/license-plate-generator)).
  `build_plate.py` here is only a minimal fallback for a plain plate.

## Checking whether a downloaded skin actually fits your car

**This is the most common practical problem with community wraps.** Sites
like [tesla-wrap.com](https://www.tesla-wrap.com/) host thousands of
designs "for Model Y" etc., but Tesla has *multiple, incompatible templates
per model* - e.g. plain `modely` (pre-2025) vs `modely-2025-base` /
`-premium` / `-performance` (post-refresh) have different panel cut lines.
A skin built for the wrong one will look subtly (or not so subtly)
misaligned once applied - overlapping seams, art bleeding across panel
boundaries, etc.

We found this the hard way: half a set of downloaded skins turned out to be
built for the 2025+ Model Y Premium/Performance template, not the plain
`modely` template our (2022) car actually uses, despite the download page
saying "Model Y" in both cases.

`check_skin_fit.py` catches this automatically: it compares a skin's alpha
channel against every official template by IoU (intersection-over-union).
A correct fit scores ~0.95-1.00; a wrong template scores ~0.4-0.6.

```bash
# grab the official templates once
mkdir templates && cd templates
for m in modely modely-2025-base modely-2025-premium modely-2025-performance \
         modely-l model3 model3-2024-base model3-2024-performance \
         models-2021 models-2025-plaid modelx-2021 cybertruck; do
  curl -sLo "${m}_template.png" \
    "https://raw.githubusercontent.com/teslamotors/custom-wraps/master/${m}/template.png"
done
cd ..

python check_skin_fit.py my_downloaded_skin.png templates/
```

Also worth checking: some skins are plain RGB with no alpha channel at all
(instead of being properly masked to the car's silhouette), which the script
flags too. Fix with `wrap_helpers.apply_template_mask(skin, template_path)` -
it replaces the skin's alpha with the official template's, so anything
outside the actual paintable panels (or inside a cutout like the panoramic
glass roof) becomes transparent as it should be.

## Building a wrap programmatically

`wrap_helpers.py` has the pieces used to generate a full custom wrap without
touching an image editor: a metallic-gradient-plus-flake-noise base texture
(tuned to stay under Tesla's 1MB limit - naive per-pixel noise blows past it
easily), turning black-line-art clipart into a colored decal, a contrast
pill background for logos, the perspective warp (with the padding fix
above), and the final template-mask clipping step. Combine them however you
like; see this repo's git history / the light-show side of this project for
the pattern of loading a template, compositing layers with
`Image.alpha_composite`, then clipping with `apply_template_mask` last.
