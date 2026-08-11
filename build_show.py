#!/usr/bin/env python3
"""
Build a Tesla custom Light Show .fseq (FSEQ v2 Uncompressed, 48-channel) file
directly from an audio file, without needing xLights.

The FSEQ format, the 48-channel layout, and the closure command encoding were
all reverse-engineered from teslamotors/light-show (README, validator.py, and
the official example show) - see README.md in this repo for the full writeup.

Usage:
    python build_show.py "song.mp3" "song.fseq"

Then copy both "song.mp3" and "song.fseq" (same base name!) into a
top-level "LightShow" folder on a FAT32/exFAT USB drive with no root-level
"TeslaCam" folder, and plug it into the car.
"""
import argparse
import struct

import numpy as np
import librosa

STEP_MS = 20
CHANNELS = 48

# ---- 48-channel map (0-based), matches Tesla Model S.xmodel NodeNames ----
L_OUTER, R_OUTER = 0, 1
L_INNER, R_INNER = 2, 3
L_SIG, R_SIG = 4, 5
L_CH4, R_CH4 = 6, 7
L_CH5, R_CH5 = 8, 9
L_CH6, R_CH6 = 10, 11
L_TURN, R_TURN = 12, 13
L_FOG, R_FOG = 14, 15
L_AUXP, R_AUXP = 16, 17
L_MARK, R_MARK = 18, 19
L_REPEAT, R_REPEAT = 20, 21
L_RTURN, R_RTURN = 22, 23
BRAKE = 24
L_TAIL, R_TAIL = 25, 26
REVERSE = 27
REARFOG = 28
PLATE = 29
L_FALCON, R_FALCON = 30, 31
L_FDOOR, R_FDOOR = 32, 33
L_MIRROR, R_MIRROR = 34, 35
L_FWIN, L_RWIN, R_FWIN, R_RWIN = 36, 37, 38, 39
LIFTGATE = 40
L_FHANDLE, L_RHANDLE, R_FHANDLE, R_RHANDLE = 41, 42, 43, 44
CHARGEPORT = 45

# Boolean light channels: 0 = off, 255 = on (instant).
ON = 255
# Closure channels use a 0-100% scale packed into a byte (round(pct*255/100)):
# Idle=0, Open=25%, Dance=50%, Close=75%, Stop=100%.
OPEN, DANCE, CLOSE, STOP = 63, 127, 191, 255

# Per-closure command budgets (Open/Dance/Close/Stop transitions only,
# counted separately per individual closure - Idle doesn't count).
CLOSURE_LIMITS = {
    "CHARGEPORT": 3, "LIFTGATE": 6, "L_MIRROR": 20, "R_MIRROR": 20,
    "L_FWIN": 6, "L_RWIN": 6, "R_FWIN": 6, "R_RWIN": 6,
    "L_FALCON": 6, "R_FALCON": 6, "L_FDOOR": 6, "R_FDOOR": 6,
    "L_FHANDLE": 20, "L_RHANDLE": 20, "R_FHANDLE": 20, "R_RHANDLE": 20,
}


def t2f(t):
    return int(round(t * 1000.0 / STEP_MS))


def pulse(canvas, channels, start_s, dur_s, value=ON):
    f0 = t2f(start_s)
    f1 = min(t2f(start_s + dur_s), canvas.shape[0])
    if f0 >= canvas.shape[0] or f1 <= f0:
        return
    for ch in (channels if isinstance(channels, (list, tuple)) else [channels]):
        canvas[f0:f1, ch] = value


def hold(canvas, channel, start_s, end_s, value):
    f0 = max(0, t2f(start_s))
    f1 = min(t2f(end_s), canvas.shape[0])
    if f1 > f0:
        canvas[f0:f1, channel] = value


def analyze_audio(path):
    y, sr = librosa.load(path, sr=44100, mono=True)
    duration = len(y) / sr
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    tempo = float(np.asarray(tempo).reshape(-1)[0])
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True, units="frames")
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)
    rms = librosa.feature.rms(y=y)[0]
    rms_times = librosa.times_like(rms, sr=sr)
    rms_norm = rms / rms.max()
    return dict(duration=duration, tempo=tempo, beat_times=beat_times,
                onset_times=onset_times, rms=rms_norm, rms_times=rms_times)


def build_lights(canvas, info):
    """Beat-synced light choreography. Targets ~75-85% "some light on"
    coverage and dense, short (100-300ms) flashes, matching the design
    patterns measured across dozens of real community-made shows (see
    README.md) - much denser than a naive "one flash per beat" approach."""
    duration = info["duration"]
    beat_times = info["beat_times"]
    onset_times = info["onset_times"]
    rms_times = info["rms_times"]
    rms_norm = info["rms"]
    tempo = info["tempo"]

    def energy_at(t):
        idx = np.searchsorted(rms_times, t)
        idx = min(max(idx, 0), len(rms_norm) - 1)
        return rms_norm[idx]

    beat_interval = 60.0 / tempo
    main_dur = min(max(0.55 * beat_interval, 0.12), 0.28)
    accent_dur = min(max(0.35 * beat_interval, 0.08), 0.16)

    low_moves = [[L_SIG, R_SIG], [L_AUXP, R_AUXP, L_MARK, R_MARK]]
    med_moves = [[L_TURN], [R_TURN], [L_TAIL, R_TAIL], [L_FOG, R_FOG]]
    high_moves = [
        [L_OUTER, R_OUTER, L_INNER, R_INNER],
        [BRAKE, L_RTURN, R_RTURN],
        [L_TURN, R_TURN],
        [L_CH4, R_CH4, L_CH5, R_CH5, L_CH6, R_CH6],
    ]
    accent_channels = [L_REPEAT, R_REPEAT, L_MARK, R_MARK, L_AUXP, R_AUXP]

    low_i = med_i = high_i = acc_i = 0
    for t in beat_times:
        e = energy_at(t)
        if e < 0.30:
            mv = low_moves[low_i % len(low_moves)]; low_i += 1
            dur = main_dur
        elif e < 0.45:
            mv = med_moves[med_i % len(med_moves)]; med_i += 1
            dur = main_dur
        else:
            mv = high_moves[high_i % len(high_moves)]; high_i += 1
            dur = main_dur * 1.15
        pulse(canvas, mv, t, dur)

        # half-beat accent to raise density/coverage and add texture
        t2 = t + beat_interval / 2.0
        if t2 < duration:
            ch = accent_channels[acc_i % len(accent_channels)]; acc_i += 1
            pulse(canvas, [ch], t2, accent_dur)

    # sparkle layer on percussive onsets that aren't already beats
    sparkle_channels = [L_REPEAT, R_REPEAT, L_MARK, R_MARK]
    for t in onset_times:
        if np.min(np.abs(beat_times - t)) < 0.08:
            continue
        e = energy_at(t)
        if e >= 0.30:
            ch = sparkle_channels[int(t * 10) % len(sparkle_channels)]
            pulse(canvas, [ch], t, 0.12)


def build_closures(canvas, duration):
    """Duration-relative closure placement so everything scales to any
    song length. Key lessons baked in here (see README.md for the why):
      - closures start within the first few seconds, never saved for a
        single late finale
      - liftgate uses its full 6-command budget as two Open/Dance/Close
        cycles when the song is long enough
      - windows open once and DANCE for nearly the whole remaining show,
        only closing briefly right at the end (holding "Close" as a long
        state makes the cabin-only audio much harder to hear from outside)
      - mirrors flutter in several bursts spread across the whole runtime
    """

    # Charge port: hard budget of 3 commands total -> one sequence, early.
    cp_open_t = max(3.0, 0.03 * duration)
    cp_open_dur = 2.2
    cp_dance_t = cp_open_t + cp_open_dur + 0.3
    cp_dance_dur = min(8.0, max(3.0, 0.03 * duration))
    cp_close_t = cp_dance_t + cp_dance_dur
    cp_close_dur = 2.2
    hold(canvas, CHARGEPORT, cp_open_t, cp_open_t + cp_open_dur, OPEN)
    hold(canvas, CHARGEPORT, cp_dance_t, cp_dance_t + cp_dance_dur, DANCE)
    hold(canvas, CHARGEPORT, cp_close_t, cp_close_t + cp_close_dur, CLOSE)
    print(f"  charge port: open@{cp_open_t:.1f} dance@{cp_dance_t:.1f} close@{cp_close_t:.1f}")

    # Liftgate: budget 6 -> two full Open/Dance/Close cycles (~14.5s open,
    # ~4s close), one near the start, one later, if the song is long enough.
    def liftgate_cycle(t0, dance_dur):
        open_dur = 14.5
        d_t = t0 + open_dur + 0.3
        c_t = d_t + dance_dur
        close_dur = 4.5
        hold(canvas, LIFTGATE, t0, t0 + open_dur, OPEN)
        hold(canvas, LIFTGATE, d_t, d_t + dance_dur, DANCE)
        hold(canvas, LIFTGATE, c_t, c_t + close_dur, CLOSE)
        return c_t + close_dur

    lg1_start = max(1.0, 0.02 * duration)
    lg1_end = liftgate_cycle(lg1_start, dance_dur=8.0)
    print(f"  liftgate cycle 1: open@{lg1_start:.1f} ... end@{lg1_end:.1f}")

    lg2_start = 0.82 * duration
    if lg2_start > lg1_end + 5.0 and lg2_start + 27.0 < duration - 1.0:
        lg2_end = liftgate_cycle(lg2_start, dance_dur=6.0)
        print(f"  liftgate cycle 2: open@{lg2_start:.1f} ... end@{lg2_end:.1f}")
    else:
        print("  liftgate cycle 2: skipped (song too short to fit cleanly)")

    # Windows: open once, dance for nearly the rest of the show, close
    # briefly right at the end. Front pair and rear pair are staggered
    # slightly for a bit of texture. Budget is 6 per corner; this uses 3.
    open_dur = 4.2
    close_dur = 4.2
    close_lead = 6.0  # start closing this many seconds before the song ends
    pairs = [(L_FWIN, R_FWIN, 0.0), (L_RWIN, R_RWIN, 1.5)]
    for a, b, stagger in pairs:
        o = max(6.0, 0.06 * duration) + stagger
        dance_start = o + open_dur + 0.3
        close_start = max(dance_start + 1.0, duration - close_lead + stagger)
        for ch in (a, b):
            hold(canvas, ch, o, o + open_dur, OPEN)
            hold(canvas, ch, dance_start, close_start, DANCE)
            hold(canvas, ch, close_start, close_start + close_dur, CLOSE)
        print(f"  windows {a}/{b}: open@{o:.1f}s, dance until {close_start:.1f}s, close near end")

    # Mirrors: budget 20 -> 5 bursts of 2 cycles (4 commands each = 20
    # total), spread evenly across the whole song starting right at the
    # opening. If you plan to run a show very often, consider dialing this
    # down (e.g. 3 bursts) - mirror actuators do wear with heavy repeated use.
    fractions = [0.02, 0.25, 0.5, 0.75, 0.95]
    cycle = 4.2
    for frac in fractions:
        t0 = max(0.5, frac * duration)
        if t0 + cycle * 2 > duration - 0.5:
            t0 = max(0.5, duration - cycle * 2 - 0.5)
        for c in range(2):
            o0 = t0 + c * cycle
            c0 = o0 + cycle / 2
            hold(canvas, L_MIRROR, o0, c0, OPEN)
            hold(canvas, R_MIRROR, o0, c0, OPEN)
            hold(canvas, L_MIRROR, c0, o0 + cycle, CLOSE)
            hold(canvas, R_MIRROR, c0, o0 + cycle, CLOSE)
        print(f"  mirrors burst @ {t0:.1f}s (2 cycles)")


def write_fseq(out_path, canvas, frame_count):
    header = bytearray(32)
    header[0:4] = b"PSEQ"
    struct.pack_into("<H", header, 4, 32)   # offset to channel data (no variable headers)
    header[6] = 0                             # minor version
    header[7] = 2                             # major version -> FSEQ 2.0
    struct.pack_into("<H", header, 8, 32)    # standard header length
    struct.pack_into("<I", header, 10, CHANNELS)
    struct.pack_into("<I", header, 14, frame_count)
    header[18] = STEP_MS
    header[19] = 0
    header[20] = 0   # compression type 0 (uncompressed) + 0 compression blocks
    header[21] = 0
    header[22] = 0   # sparse ranges
    header[23] = 0
    header[24:32] = (0).to_bytes(8, "little")
    with open(out_path, "wb") as f:
        f.write(header)
        f.write(canvas.tobytes())


def build_show(audio_path, out_fseq_path):
    print(f"=== {audio_path} ===")
    info = analyze_audio(audio_path)
    duration = info["duration"]
    print(f"  duration={duration:.1f}s tempo={info['tempo']:.1f}bpm beats={len(info['beat_times'])}")

    frame_count = int(np.ceil(duration * 1000.0 / STEP_MS)) + 10
    canvas = np.zeros((frame_count, CHANNELS), dtype=np.uint8)

    build_lights(canvas, info)
    build_closures(canvas, duration)
    write_fseq(out_fseq_path, canvas, frame_count)
    print(f"  wrote {out_fseq_path} ({frame_count} frames, {frame_count*STEP_MS/1000:.1f}s)")
    return canvas, frame_count


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio", help="Path to a 44.1kHz .mp3 or .wav file")
    parser.add_argument("out_fseq", help="Output .fseq path (same base name as the audio file)")
    args = parser.parse_args()
    build_show(args.audio, args.out_fseq)


if __name__ == "__main__":
    main()
