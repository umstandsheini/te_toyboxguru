# te_toyboxguru

Reverse-engineered docs, gotchas, and small Python tools for three separate
Tesla USB-based features - Light Show, Custom Wraps/License Plate, and the
TeslaCam Dashcam/Sentry drive - none of which are properly documented by
Tesla itself. Built while setting all three up (and debugging why they
wouldn't work together) on real vehicles.

## What's in this repo

| | Covers | Start here |
|---|---|---|
| **Light Show** (root of repo) | Generate custom `.fseq` light shows from any song in Python, no xLights required. Full FSEQ v2 binary format writeup, the 48-channel hardware map, closure command encoding + budgets, and design patterns pulled from real shows. | `build_show.py`, [Quick start](#quick-start) below |
| [`wraps/`](wraps/) | Custom Wraps & License Plate Paint Shop features - front vs rear plate handling (two unrelated mechanisms), the padding-before-warp bug, and a tool to check whether a downloaded skin actually fits your specific vehicle template. | [`wraps/README.md`](wraps/README.md) |
| [`dashcam/`](dashcam/) | TeslaCam USB setup gotchas, including a **confirmed fix** for a drive showing 0 bytes/unusable on the camera: creating the actual (undocumented) `TeslaCam/EncryptedClips/...` folder structure newer Tesla software expects. Also why a two-partition Dashcam+LightShow stick that works on one car can fail outright on another. | [`dashcam/README.md`](dashcam/README.md) |

The rest of this file covers the Light Show generator specifically.

This started as a reverse-engineering exercise: [teslamotors/light-show](https://github.com/teslamotors/light-show)
documents the *requirements* for a custom show (folder layout, audio format,
keyboard shortcuts inside xLights) but never publishes the actual `.fseq`
binary format or the byte-level meaning of the closure commands. Both were
worked out here by reading the FSEQ v2 spec from the [FPP project](https://github.com/FalconChristmas/fpp/blob/master/docs/FSEQ_Sequence_File_Format.txt),
and cross-referencing Tesla's own example show's `.xsq` (human-readable
effect definitions) against the actual bytes in the paired `.fseq`.

## Quick start

```bash
pip install numpy librosa

python build_show.py "My Song.mp3" "My Song.fseq"
```

Then copy **both** `My Song.mp3` and `My Song.fseq` (same base name!) into a
top-level `LightShow` folder on a FAT32/exFAT/ext3/ext4 USB drive. The drive
must **not** have a root-level `TeslaCam` folder (that's a hard requirement -
if your Sentry/Dashcam recordings share a stick, they need their own
separate partition; see [`dashcam/`](dashcam/) for partitioning gotchas).
Plug it into the car
- front USB-C, or the glovebox port (often the most reliable one for data).
In Toybox > Light Show > Schedule Show, your song should appear in the
dropdown once the requirements are met (popup title says "Custom Light Show",
not just "Light Show").

Sanity-check any `.fseq` (yours or a downloaded one) before it goes on a
drive:

```bash
python analyze_shows.py "My Song.fseq"        # one file
python analyze_shows.py path/to/LightShow/     # every .fseq in a folder
```

This reports light-channel coverage/flash timing and, importantly, checks
every closure's command count against Tesla's documented per-closure budget
(Tesla's own `validator.py` only checks the file header, not this).

## The FSEQ v2 format

A `.fseq` is dead simple once you know the layout: a 32-byte header,
followed by one byte per channel per frame, frame after frame, in a fixed
`step_ms` interval (Tesla recommends 20ms; 15-100ms all work).

| Offset | Type | Field |
|---|---|---|
| 0-3 | `char[4]` | magic, must be `PSEQ` |
| 4-5 | `u16` | offset to channel data (32 if there are no variable headers) |
| 6 | `u8` | minor version (0) |
| 7 | `u8` | major version (2, for FSEQ v2.0) |
| 8-9 | `u16` | standard header length (32) |
| 10-13 | `u32` | channel count per frame |
| 14-17 | `u32` | frame count |
| 18 | `u8` | step time in ms |
| 19 | `u8` | flags, must be 0 |
| 20 | `u8` | compression type (0 = uncompressed) + block count high nibble |
| 21 | `u8` | compression block count, low byte |
| 22 | `u8` | number of sparse ranges (0) |
| 23 | `u8` | reserved |
| 24-31 | `u64` | free-form unique id, not checked |

Tesla's vehicle firmware accepts **48** channels (all lights + closures on
Model S/X/3/Y, superset-compatible) or **200** channels (adds Cybertruck's
individually-addressable light bar segments and interior RGB). This project
only targets the 48-channel cross-vehicle layout. See `build_show.py`'s FSEQ
2.0 header spec comment for the exact byte packing used, or the full spec at
[FalconChristmas/fpp](https://github.com/FalconChristmas/fpp/blob/master/docs/FSEQ_Sequence_File_Format.txt).

### The 48-channel map

Extracted from `NodeNames` in `Tesla Model S.xmodel` (inside Tesla's own
`tesla_xlights_show_folder.zip`), 0-indexed:

| # | Channel | # | Channel | # | Channel |
|---|---|---|---|---|---|
| 0/1 | Outer Main Beam L/R | 16/17 | Aux Park L/R | 32/33 | Front Door L/R |
| 2/3 | Inner Main Beam L/R | 18/19 | Side Marker L/R | 34/35 | Mirror L/R |
| 4/5 | Signature L/R | 20/21 | Side Repeater L/R | 36/37 | Front/Rear Window L |
| 6/7 | Channel 4 L/R | 22/23 | Rear Turn L/R | 38/39 | Front/Rear Window R |
| 8/9 | Channel 5 L/R | 24 | Brake | 40 | Liftgate |
| 10/11 | Channel 6 L/R | 25/26 | Tail L/R | 41/42 | Front/Rear Door Handle L |
| 12/13 | Front Turn L/R | 27 | Reverse | 43/44 | Front/Rear Door Handle R |
| 14/15 | Front Fog L/R | 28 | Rear Fog | 45 | Charge Port |
| | | 29 | License Plate | 46/47 | unused/reserved |
| | | 30/31 | Falcon Door L/R | | |

Boolean light channels (headlights, turn signals, brake, tail, fog, etc.):
**0 = off, 255 = on** (instant). Several of them also support gradual ramping
via intermediate byte values (see Tesla's README), but plain 0/255 works
fine everywhere.

### Closure command encoding

Not documented anywhere by Tesla - reverse-engineered by loading their
official example show into a hex/struct parser and correlating the known
xLights "brightness %" palette values (`C_SLIDER_Brightness=25/50/75` in the
`.xsq`) against the byte actually present in the `.fseq` at that timestamp:

| Command | Byte value | xLights hotkey |
|---|---|---|
| Idle | `0` | *(empty timeline)* |
| Open | `63` (25%) | Q |
| Dance | `127` (50%) | A |
| Close | `191` (75%) | Z |
| Stop | `255` (100%) | F |

Applies to: Charge Port, Liftgate, Falcon Doors, Front Doors, Mirrors,
Windows, Door Handles. Each closure has its own per-show command budget
(only Open/Dance/Close/Stop count, not Idle):

| Closure | Budget | Notes |
|---|---|---|
| Charge Port | 3 | supports Dance |
| Liftgate | 6 | supports Dance; ~14.5s to open, ~4s to close (physically slow!) |
| Mirrors | 20 | does **not** support Dance |
| Windows | 6 per corner | supports Dance |
| Falcon/Front Doors | 6 | supports Dance (Falcon only) |
| Door Handles | 20 | Model S only |

Physical actuation is **slow** relative to the ~20ms frame rate - budget
enough hold time before switching states or the movement won't visibly
complete: Mirrors/Charge Port ~2s, Windows ~4s, Liftgate open ~14.5s(!) /
close ~4s. `Dance` additionally requires the closure to *already* be open
first (except windows, which are exempt from that rule) - always place an
`Open` command with enough delay before the first `Dance`.

## Design patterns (measured from ~20 real community/Tesla shows)

Running `analyze_shows.py` over a folder of downloaded/official shows
surfaced patterns that aren't in any doc:

- **Density**: real shows keep *some* light on 70-95% of the runtime, with
  2-3x more flash events per second than a naive "one flash per beat"
  generator produces. Flashes are short (often a fixed 100-250ms) and
  frequent, not sparse.
- **Closures start immediately** - the first Mirror/Window/Charge Port
  command usually lands in the first 1-10% of the song, never saved for a
  single late finale. If you stop watching before the "big finish," you'll
  miss everything.
- **Liftgate** is normally used as **two full** `Open → Dance → Close`
  cycles (6/6 commands) spread across the show, not one.
- **Windows are open/dancing 80-95%+ of the runtime**, and closed only
  briefly (a few seconds) right before the show ends - not repeatedly
  opened and closed. The show's music only plays through the cabin
  speakers, so a window held shut for a long stretch makes it noticeably
  harder to hear from outside. `Close` should really only ever be a brief
  transition, never a sustained state.
- **Mirrors flutter continuously** throughout the whole song (7-20 short
  open/close commands spread out), not in one or two isolated bursts.
- Activity often follows the song's own dynamic arc (building through the
  first half, tapering at the very end) rather than staying flat throughout.
- Not every show scores the *entire* track - some officially-included
  examples (a ~24s Olympics fanfare, a ~36s Paw Patrol intro) only
  choreograph a short recognizable hook rather than the full song length.

## Other things that aren't obvious from the official docs

- There's a **"Dance Moves" checkbox** in the car's own Toybox UI when
  scheduling a show, separate from the `.fseq` content. If unchecked,
  windows/mirrors/trunk/charge port never move for that playback, no matter
  what's in the file - only the lights run. Check this first if closures
  "don't work."
- The car needs **generous open space all around it** to run closures.
  Mirrors, the liftgate, and Falcon doors all have obstacle/pinch sensors
  that silently skip or abort a movement if something (a wall, a low garage
  ceiling, a neighboring car) is too close - a very common reason closures
  "just don't move" that has nothing to do with the file.
- If the physical car doesn't have a given powered part (e.g. no powered
  liftgate on some trims), that channel is simply a no-op; the rest of the
  show plays normally.
- Audio must be sampled at 44.1kHz; 48kHz files will drift out of sync.
- Light Show only runs in Park, and no one should be in the cabin when it
  plays (interior speakers, can get loud).
- Repeated heavy mirror-actuator use has some wear-and-tear concern in the
  community (Tesla shipped an actuator wear-protection improvement in
  firmware 2025.2.3) - if a show will run very often, consider not always
  maxing out the mirror command budget.

## Credits

Format reverse-engineering and generator built while prototyping custom
shows for a personal Tesla. Official Tesla resources: the
[teslamotors/light-show](https://github.com/teslamotors/light-show) repo
(requirements, `validator.py`, the xLights project template and example
shows used for reverse-engineering) and the [FPP FSEQ format spec](https://github.com/FalconChristmas/fpp/blob/master/docs/FSEQ_Sequence_File_Format.txt).
