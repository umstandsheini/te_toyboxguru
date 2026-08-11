#!/usr/bin/env python3
"""
Analyze one or more Tesla custom light show .fseq files: light-channel
activity/coverage, flash timing, and closure command usage (with budget
checks against Tesla's documented per-closure command limits).

Useful for reverse-engineering how existing/downloaded shows are built, or
for sanity-checking your own generated shows before copying them to a USB
drive (in addition to running Tesla's own validator.py, which only checks
the file header - not command limits or channel content).

Usage:
    python analyze_shows.py path/to/LightShow/          # analyze every .fseq in a folder
    python analyze_shows.py show1.fseq show2.fseq       # analyze specific files
"""
import argparse
import glob
import os
import struct

import numpy as np

NAMES = ['L_OUTER', 'R_OUTER', 'L_INNER', 'R_INNER', 'L_SIG', 'R_SIG', 'L_CH4', 'R_CH4',
         'L_CH5', 'R_CH5', 'L_CH6', 'R_CH6', 'L_TURN', 'R_TURN', 'L_FOG', 'R_FOG',
         'L_AUXP', 'R_AUXP', 'L_MARK', 'R_MARK', 'L_REPEAT', 'R_REPEAT', 'L_RTURN', 'R_RTURN',
         'BRAKE', 'L_TAIL', 'R_TAIL', 'REVERSE', 'REARFOG', 'PLATE', 'L_FALCON', 'R_FALCON',
         'L_FDOOR', 'R_FDOOR', 'L_MIRROR', 'R_MIRROR', 'L_FWIN', 'L_RWIN', 'R_FWIN', 'R_RWIN',
         'LIFTGATE', 'L_FHANDLE', 'L_RHANDLE', 'R_FHANDLE', 'R_RHANDLE', 'CHARGEPORT', 'U1', 'U2']

CLOSURE_IDX = {30: 'L_FALCON', 31: 'R_FALCON', 32: 'L_FDOOR', 33: 'R_FDOOR',
               34: 'L_MIRROR', 35: 'R_MIRROR', 36: 'L_FWIN', 37: 'L_RWIN',
               38: 'R_FWIN', 39: 'R_RWIN', 40: 'LIFTGATE',
               41: 'L_FHANDLE', 42: 'L_RHANDLE', 43: 'R_FHANDLE', 44: 'R_RHANDLE',
               45: 'CHARGEPORT'}

# Per-closure command budgets from Tesla's README (counted separately per
# individual closure; only Open/Dance/Close/Stop transitions count, not Idle).
CLOSURE_LIMITS = {
    'CHARGEPORT': 3, 'LIFTGATE': 6,
    'L_MIRROR': 20, 'R_MIRROR': 20,
    'L_FWIN': 6, 'L_RWIN': 6, 'R_FWIN': 6, 'R_RWIN': 6,
    'L_FALCON': 6, 'R_FALCON': 6, 'L_FDOOR': 6, 'R_FDOOR': 6,
    'L_FHANDLE': 20, 'L_RHANDLE': 20, 'R_FHANDLE': 20, 'R_RHANDLE': 20,
}


def load_fseq(path):
    with open(path, 'rb') as f:
        data = f.read()
    if data[0:4] != b'PSEQ':
        return None
    start_offset, = struct.unpack('<H', data[4:6])
    minor, major = data[6], data[7]
    channel_count, frame_count, step_time = struct.unpack('<IIB', data[10:19])
    compression = data[20] & 0x0F
    arr = np.frombuffer(data[start_offset:start_offset + frame_count * channel_count], dtype=np.uint8)
    if arr.size < frame_count * channel_count:
        frame_count = arr.size // channel_count
        arr = arr[:frame_count * channel_count]
    arr = arr.reshape(frame_count, channel_count)
    return dict(channel_count=channel_count, frame_count=frame_count, step_time=step_time,
                minor=minor, major=major, compression=compression, arr=arr)


def analyze(path):
    info = load_fseq(path)
    if info is None:
        print(f"{os.path.basename(path)}: not a PSEQ file, skipping")
        return
    arr = info['arr']
    cc = info['channel_count']
    fc = info['frame_count']
    step = info['step_time']
    duration = fc * step / 1000.0
    name = os.path.basename(path)
    print(f"\n=== {name} === ch={cc} frames={fc} step={step}ms dur={duration:.1f}s "
          f"v{info['major']}.{info['minor']} comp={info['compression']}")

    if cc < 46:
        print("  (fewer than 46 channels, unusual/short model, skipping detail)")
        return

    # light channel activity: coverage %, and where in the song (quartiles)
    light_idx = [i for i in range(min(cc, 46)) if i not in CLOSURE_IDX]
    any_light = (arr[:, light_idx] > 0).any(axis=1)
    total_on_frac = any_light.mean()
    q = np.array_split(any_light, 4)
    quartile_activity = [f"{seg.mean()*100:.0f}%" for seg in q]
    print(f"  light activity: {total_on_frac*100:.0f}% of song has some light on; by quartile: {quartile_activity}")

    flash_counts, flash_durs, used_light_channels = [], [], []
    for i in light_idx:
        col = arr[:, i]
        on = col > 0
        edges = np.where(np.diff(on.astype(int)) == 1)[0]
        if len(edges) == 0:
            continue
        used_light_channels.append(NAMES[i])
        flash_counts.append(len(edges))
        offs = np.where(np.diff(on.astype(int)) == -1)[0]
        durs = []
        for e in edges:
            after = offs[offs > e]
            if len(after):
                durs.append((after[0] - e) * step)
        flash_durs.extend(durs)
    if used_light_channels:
        print(f"  used light channels ({len(used_light_channels)}): {used_light_channels}")
        if flash_durs:
            print(f"  total flash events: {sum(flash_counts)}, avg duration: {np.mean(flash_durs):.0f}ms, "
                  f"median: {np.median(flash_durs):.0f}ms, min/max: {min(flash_durs):.0f}/{max(flash_durs):.0f}ms")

    # closures: command sequences + budget check
    for i, cname in CLOSURE_IDX.items():
        if i >= cc:
            continue
        col = arr[:, i]
        if not (col > 0).any():
            continue
        changes = np.where(np.diff(col.astype(int)) != 0)[0] + 1
        cmd_events = [(c * step / 1000.0, col[c]) for c in changes if col[c] != 0]
        limit = CLOSURE_LIMITS.get(cname)
        over = limit is not None and len(cmd_events) > limit
        flag = "  <-- OVER LIMIT" if over else ""
        print(f"  closure {cname}: {len(cmd_events)}/{limit if limit else '?'} commands{flag} "
              f"at times(s)={[f'{t:.1f}' for t, v in cmd_events]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="A folder of .fseq files, or one/more .fseq file paths")
    args = parser.parse_args()

    files = []
    for p in args.paths:
        if os.path.isdir(p):
            files.extend(sorted(glob.glob(os.path.join(p, "*.fseq"))))
        else:
            files.append(p)

    for path in files:
        analyze(path)


if __name__ == "__main__":
    main()
