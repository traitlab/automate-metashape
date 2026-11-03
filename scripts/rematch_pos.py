#!/usr/bin/env python3
"""
Rebuild the camera positions of QBase3D-geotagged P5 missions and write them as
a <mission>_POS.txt that addPhotos.import_reference can load.

QBase3D matches each photo to its PPK camera event by EXIF capture time, which
the P5 only writes to the whole second. Within a second (2-4 photos) the order
is arbitrary, so about half of the photos get the tag of a neighbouring
exposure, 8-24 m along track.

A tag is a whole event: position, orientation and accuracy (QBase3D replaces
the camera's own IMU orientation with one from its event log). Within each
EXIF second the photos' tags are that second's events, only shuffled. This
sorts them along the flight direction (= time order) and gives them back to
the photos in filename order (= capture order). Only the images are read; the
.pgt is not needed.

Tag positions are the camera centre: the .pgt antenna position plus a fixed
lever arm (~0.31 m forward on bciwhole_p5). They differ from the .pgt by that
offset.

About 4-5% of photos, and up to 20% for some missions, get an event from the neighbouring second; these stay
misplaced by one exposure. Flag them after alignment by their camera error.

Output columns match import_reference in metashape_workflow_functions_lefolab.py:

    label,lat,lon,alt,yaw,pitch,roll,sxy,sz

label is the resolved photo path, which is what Metashape stores for photos
reached through symlinked folders (run*_main, overlap_*). Rotation is the
aerialgps: XMP orientation (the order Metashape loads), accuracy the
Camera:GPSXYAccuracy / Camera:GPSZAccuracy XMP values.

No Metashape needed:

    python scripts/rematch_pos.py /path/to/bciwhole_p5/mission10 [more missions ...]
    # -> /path/to/bciwhole_p5/mission10/mission10_POS.txt

    python scripts/rematch_pos.py /path/to/mission10 --output-dir out/
"""

import argparse
import datetime
import glob
import math
import os
import re
import sys


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("missions", nargs="+", help="Mission folder(s) containing *_Geotagged/<camera>/*.jpg")
    parser.add_argument(
        "--output-dir",
        help="Write <mission>_POS.txt here instead of into each mission folder",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace an existing <mission>_POS.txt"
    )
    return parser.parse_args(argv)


def degrees(value):
    """XMP 'D,M.MMMMH' -> signed decimal degrees."""
    d, m = value[:-1].split(",")
    v = int(d) + float(m) / 60
    return -v if value[-1] in "SW" else v


def rational(value):
    num, _, den = value.partition("/")
    return float(num) / float(den or 1)


def read_photo(path):
    """Capture second, QBase3D tag, rotation and accuracy from the photo's EXIF/XMP header."""
    with open(path, "rb") as f:
        head = f.read(131072).decode("latin-1")

    def tag(name):
        m = re.search(rf"<{name}>([^<]+)</{name}>", head)
        return m.group(1) if m else None

    when = re.search(r"(\d{4}):(\d\d):(\d\d) (\d\d):(\d\d):(\d\d)", head)
    lat, lon, alt = tag("exif:GPSLatitude"), tag("exif:GPSLongitude"), tag("exif:GPSAltitude")
    if not (when and lat and lon and alt):
        return None
    rot = [tag(f"aerialgps:GPSIMU{a}") for a in ("Yaw", "Pitch", "Roll")]
    sxy, sz = tag("Camera:GPSXYAccuracy"), tag("Camera:GPSZAccuracy")
    return {
        "second": int(
            datetime.datetime(*map(int, when.groups()), tzinfo=datetime.timezone.utc).timestamp()
        ),
        "tag": (degrees(lat), degrees(lon), rational(alt)),
        "rotation": [rational(r) if r else None for r in rot],
        "accuracy": (rational(sxy) if sxy else None, rational(sz) if sz else None),
    }


def rematch(photos):
    """Reassign the events within each EXIF second in flight order.

    Sets p["event"] to the photo whose tag (position, rotation, accuracy) p should get.
    Returns a summary count.
    """
    lat0 = math.radians(photos[0]["tag"][0])
    m_n = 111132.954 - 559.822 * math.cos(2 * lat0)
    m_e = 111412.84 * math.cos(lat0)

    by_second = {}
    for p in photos:
        by_second.setdefault(p["second"], []).append(p)
    seconds = sorted(by_second)
    centre = {
        s: (
            sum(p["tag"][0] for p in by_second[s]) / len(by_second[s]),
            sum(p["tag"][1] for p in by_second[s]) / len(by_second[s]),
        )
        for s in seconds
    }

    counts = {"changed": 0, "unchanged": 0, "single": 0, "no direction": 0}
    for i, s in enumerate(seconds):
        group = by_second[s]
        if len(group) == 1:
            group[0]["event"] = group[0]
            counts["single"] += 1
            continue
        # Flight direction from the neighbouring seconds' centres
        a = centre[seconds[i - 1]] if i > 0 and seconds[i - 1] >= s - 2 else centre[s]
        b = centre[seconds[i + 1]] if i + 1 < len(seconds) and seconds[i + 1] <= s + 2 else centre[s]
        vn, ve = (b[0] - a[0]) * m_n, (b[1] - a[1]) * m_e
        if math.hypot(vn, ve) < 1:
            for p in group:
                p["event"] = p
            counts["no direction"] += len(group)
            continue
        events = sorted(group, key=lambda e: e["tag"][0] * m_n * vn + e["tag"][1] * m_e * ve)
        for p, e in zip(group, events):  # group is already in filename order
            p["event"] = e
            counts["changed" if e is not p else "unchanged"] += 1
    return counts


def write_pos(photos, path):
    fmt = lambda v, nd: "" if v is None else f"{v:.{nd}f}"
    with open(path, "w") as f:
        f.write("label,lat,lon,alt,yaw,pitch,roll,sxy,sz\n")
        for p in photos:
            e = p["event"]
            lat, lon, alt = e["tag"]
            yaw, pitch, roll = e["rotation"]
            sxy, sz = e["accuracy"]
            f.write(
                f"{p['label']},{lat:.9f},{lon:.9f},{alt:.4f},"
                f"{fmt(yaw, 3)},{fmt(pitch, 3)},{fmt(roll, 3)},{fmt(sxy, 4)},{fmt(sz, 4)}\n"
            )


def main(argv):
    args = parse_args(argv)
    for mission in args.missions:
        mission = os.path.normpath(mission)
        name = os.path.basename(mission)
        out_dir = args.output_dir or mission
        out = os.path.join(out_dir, f"{name}_POS.txt")
        if os.path.exists(out) and not args.overwrite:
            print(f"[rematch_pos] {name}: {out} exists, skipped (use --overwrite)")
            continue

        files = sorted(glob.glob(os.path.join(mission, "*_Geotagged", "*", "*.[jJ][pP][gG]")))
        if not files:
            print(f"[rematch_pos] {name}: no geotagged photos, skipped")
            continue
        photos, skipped = [], []
        for f in files:
            p = read_photo(f)
            if p is None:
                skipped.append(os.path.basename(f))
                continue
            p["label"] = os.path.realpath(f)
            photos.append(p)

        counts = rematch(photos)
        os.makedirs(out_dir, exist_ok=True)
        write_pos(photos, out)
        print(
            f"[rematch_pos] {name}: {len(photos)} photos, {counts['changed']} moved, "
            f"{counts['unchanged']} unchanged, {counts['single']} alone in their second, "
            f"{counts['no direction']} without flight direction, {len(skipped)} skipped (no tag/time) -> {out}"
        )
        if skipped:
            print(f"    skipped: {', '.join(skipped[:10])}{' ...' if len(skipped) > 10 else ''}")


if __name__ == "__main__":
    main(sys.argv[1:])
