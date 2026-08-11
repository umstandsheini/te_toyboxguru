# TeslaCam USB setup: partitioning and folder-structure gotchas

Notes from getting Dashcam/Sentry Mode recording working on a plain USB
flash drive, on a vehicle where it initially refused to recognize the drive
at all (touchscreen showed 0 bytes of storage / an error, no TeslaCam icon).
None of this is documented anywhere official.

## Multi-partition support is inconsistent across vehicles/software versions

The common community pattern (and what [Tesla's own manual](https://www.tesla.com/ownersmanual/2012_2020_models/en_gb/GUID-F311BBCA-2532-4D04-B88C-DBA784ADEE21.html)
describes) is: one exFAT drive, split into two partitions, so Dashcam/Sentry
and Music (or Light Show) can share a single stick. This genuinely works on
some vehicles - a 128GB stick with `LightShow` on a small FAT32 partition and
`TeslaCam` on the remaining exFAT partition has been running fine on one car
in this project the whole time.

On a second vehicle (different car, different software build), the exact
same two-partition layout consistently failed for the camera feature - drive
showed 0 bytes, dashcam icon greyed out or missing - **regardless of
partition order** (tried `TeslaCam` as partition 1 and as partition 2, both
failed the same way). This matches a known failure mode reported as far back
as 2020 ([TeslaMotorsClub thread](https://teslamotorsclub.com/tmc/threads/2020-24-6-9-no-more-multiple-partitions-for-dashcam-and-sentry.200657/)):
after a software update, a two-partition drive (FAT32 + ext4) started
showing *"too many partitions detected; please reformat the drive using your
computer"* and both Dashcam and USB Music stopped working, despite having
worked identically before that update.

Also notable: Tesla's own in-car **"Format USB Drive"** automatic-format
feature is only offered at all when the inserted drive already has "one or
fewer partitions" - so if your drive shows up as formattable in the car but
your multi-partition drive doesn't, that's consistent with this vehicle
being partition-count-sensitive.

**Takeaway:** don't assume a two-partition Dashcam+LightShow (or
Dashcam+Music) stick will work on every car/software version. If the camera
won't recognize a multi-partition drive, the reliable fallback is a single
whole-disk partition dedicated to `TeslaCam` (+ `LockChime.wav` +
`LicensePlate`, see below), and a **separate physical stick** for
`LightShow`/`Wraps`. See [marcone/teslausb](https://github.com/marcone/teslausb)
if you want genuine simultaneous Dashcam+LightShow+Music from one physical
device - it runs on a Raspberry Pi and presents each purpose as its own
separate virtual USB drive (its own gadget-mode LUN, backed by its own
`*_disk.bin` image file) rather than as partitions on one disk, which
sidesteps this whole class of problem.

## `LicensePlate` and `LockChime.wav` are NOT partition-exclusive with TeslaCam

Unlike `LightShow` (which is ignored outright if a root-level `TeslaCam`
folder exists on the same partition - a hard, confirmed requirement), plain
files placed alongside `TeslaCam` on the same partition cause no known
conflict:

- `LicensePlate/<file>.png` - confirmed working side-by-side with `TeslaCam`
  on the same partition.
- `LockChime.wav` - goes at the root of the same partition used for
  Dashcam; no separate partition needed.

So a single-partition Dashcam stick can (and should) also carry
`LicensePlate/` and `LockChime.wav` directly on it.

## THE FIX: the `TeslaCam` folder needs the right nested structure to be recognized

**This is what actually fixed the "0 bytes / error, drive not usable"
problem on the second vehicle described above.** Single-partitioning the
drive (previous section) was not enough by itself - the partition still
showed as unusable/0 bytes for the camera until this was done too.

The obvious assumption - just create an empty `TeslaCam` folder (or
`TeslaCam/RecentClips`, `TeslaCam/SavedClips`, `TeslaCam/SentryClips`
directly) and let the car fill it in - **did not work and left the
partition unrecognized**. Newer Tesla software has clip encryption enabled
by default, which nests everything one level deeper:

```
TeslaCam/
  EncryptedClips/
    RecentClips/
    SavedClips/
    SentryClips/
      <event-timestamp>/
        event.json
        thumb.png
        <timestamp>-front.mp4
        <timestamp>-back.mp4
        <timestamp>-left_repeater.mp4
        <timestamp>-right_repeater.mp4
```

(Confirmed by inspecting an actual populated TeslaCam drive from a working
car - the real structure is `TeslaCam/EncryptedClips/...`, not
`TeslaCam/...` directly.)

**The fix:** the previously-unrecognized `TeslaCam` folder was pre-seeded
with this exact structure - real `RecentClips` files, a real
`SentryClips/<event>/` folder with its `event.json`/`thumb.png`, and
Tesla's own `-README_de.txt` placeholder files copied into each level.
Immediately after that, the partition was recognized as usable and the
camera error was gone - no other change was made in between. Creating this
folder structure (with real, non-empty files in it, not just empty
directories) is the fix.

If you disable clip encryption in the car (Controls > Safety > *Encrypt
Dashcam Recordings*), the flat `TeslaCam/RecentClips` etc. structure (without
`EncryptedClips`) is presumably what gets used instead - not verified here.
