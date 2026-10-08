#!/usr/bin/env python3
"""
Preprocess raw field photos for the waste-demarcation feasibility study.

Two jobs, both non-destructive (data/raw is never modified):

  1. Bake EXIF orientation into pixels (all 8 orientation values, including the
     four mirrored ones), then downscale so the LONG SIDE == --long-side px with
     aspect ratio preserved (no crop, no pad). Output JPEG q95, 4:4:4 (no chroma
     subsampling), with the orientation tag normalised to 1 so nothing
     double-rotates downstream (OpenCV ignores EXIF; Pillow/phones do not).

  2. Emit data/metadata/capture_metadata.csv, one row per image.
     EXIF-derived columns are filled automatically. The four scene-judgement
     columns (location_name, distance_m, scale_reference_present, notes) are
     left EMPTY on purpose -- they are human observations and must not be
     guessed. Re-running with --keep-manual preserves anything already typed
     into those columns.

Usage:
    python scripts/preprocess.py                      # full run
    python scripts/preprocess.py --verify-only        # check outputs, write nothing
    python scripts/preprocess.py --long-side 2048
    python scripts/preprocess.py --metadata-only

Deps: pip install --break-system-packages Pillow piexif opencv-python-headless numpy
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ExifTags

# ---------------------------------------------------------------- paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
METADATA_CSV = PROJECT_ROOT / "data" / "metadata" / "capture_metadata.csv"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}

CSV_COLUMNS = [
    "filename", "date", "time", "time_of_day",
    "gps_latitude", "gps_longitude", "location_name", "phone_model",
    "orientation_applied", "original_width", "original_height",
    "output_width", "output_height",
    "distance_m", "scale_reference_present", "notes",
]

# Columns that are human judgements -- never auto-filled.
MANUAL_COLUMNS = ["location_name", "distance_m", "scale_reference_present", "notes"]

# EXIF tag ids
TAG_ORIENTATION = 274
TAG_MAKE = 271
TAG_MODEL = 272
IFD_EXIF = 0x8769
IFD_GPS = 0x8825
TAG_DATETIME_ORIGINAL = 36867
TAG_DATETIME_DIGITIZED = 36868
TAG_DATETIME = 306
TAG_OFFSET_TIME_ORIGINAL = 36881

# ------------------------------------------------- EXIF orientation

# Maps EXIF Orientation (1..8) -> sequence of ops to bake into pixels.
# 2,4,5,7 are the mirrored (flipped) cases that a naive rot90-only
# implementation gets wrong.
ORIENTATION_OPS = {
    1: [],                                    # normal
    2: ["fliplr"],                            # mirrored horizontally
    3: ["rot180"],                            # rotated 180
    4: ["flipud"],                            # mirrored vertically
    5: ["transpose"],                          # mirrored horiz + rot 270 CW
    6: ["rot270"],                            # rotated 90 CW
    7: ["transverse"],                         # mirrored horiz + rot 90 CW
    8: ["rot90"],                             # rotated 270 CW
}


def apply_orientation(bgr: np.ndarray, orientation: int) -> np.ndarray:
    """Bake an EXIF orientation value into the pixel data."""
    ops = ORIENTATION_OPS.get(orientation)
    if ops is None:
        print(f"    ! unknown orientation {orientation!r}, treating as 1")
        return bgr
    out = bgr
    for op in ops:
        if op == "fliplr":
            out = out[:, ::-1]
        elif op == "flipud":
            out = out[::-1, :]
        elif op == "rot180":
            out = out[::-1, ::-1]
        elif op == "rot90":            # counter-clockwise 90
            out = np.rot90(out, 1)
        elif op == "rot270":           # clockwise 90
            out = np.rot90(out, 3)
        elif op == "transpose":        # flip across main diagonal
            out = np.rot90(out, 1)[::-1, :]
        elif op == "transverse":       # flip across anti-diagonal
            out = np.rot90(out, 3)[::-1, :]
    return np.ascontiguousarray(out)


# ------------------------------------------------- EXIF reading

def _to_float(x) -> float | None:
    try:
        if isinstance(x, tuple) and len(x) == 2:
            return float(x[0]) / float(x[1]) if x[1] else None
        if isinstance(x, Fraction):
            return float(x)
        return float(x)
    except Exception:
        return None


def dms_to_decimal(dms, ref) -> float | None:
    """Convert EXIF (degrees, minutes, seconds) + N/S/E/W ref to signed decimal degrees."""
    if not dms or len(dms) != 3:
        return None
    parts = [_to_float(v) for v in dms]
    if any(p is None for p in parts):
        return None
    deg, minute, sec = parts
    val = deg + minute / 60.0 + sec / 3600.0
    if isinstance(ref, bytes):
        ref = ref.decode("ascii", "ignore")
    if ref and str(ref).strip().upper() in ("S", "W"):
        val = -val
    return round(val, 7)


def time_of_day_bucket(hour: int | None) -> str:
    """morning 05:00-11:59 | afternoon 12:00-16:59 | evening 17:00-20:59 | night 21:00-04:59"""
    if hour is None:
        return ""
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def _clean(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bytes):
        v = v.decode("utf-8", "ignore")
    return str(v).strip().strip("\x00")


def read_exif(path: Path) -> dict:
    """Pull the fields we care about. Missing values come back as ''/None, never guessed."""
    info = {
        "orientation": 1, "orientation_in_file": None,
        "make": "", "model": "", "datetime_raw": "",
        "date": "", "time": "", "time_of_day": "",
        "gps_lat": "", "gps_lon": "",
        "width": None, "height": None,
    }
    with Image.open(path) as im:
        info["width"], info["height"] = im.size   # pre-rotation, as stored
        try:
            ex = im.getexif()
        except Exception:
            return info

        if not ex:
            return info

        raw_orient = ex.get(TAG_ORIENTATION)
        if isinstance(raw_orient, int) and 1 <= raw_orient <= 8:
            info["orientation"] = raw_orient
            info["orientation_in_file"] = raw_orient
        elif raw_orient is not None:
            info["orientation_in_file"] = raw_orient

        info["make"] = _clean(ex.get(TAG_MAKE))
        info["model"] = _clean(ex.get(TAG_MODEL))

        exif_ifd = {}
        try:
            exif_ifd = ex.get_ifd(IFD_EXIF) or {}
        except Exception:
            pass

        dt = (_clean(exif_ifd.get(TAG_DATETIME_ORIGINAL))
              or _clean(exif_ifd.get(TAG_DATETIME_DIGITIZED))
              or _clean(ex.get(TAG_DATETIME)))
        info["datetime_raw"] = dt
        if dt:
            # EXIF format: "YYYY:MM:DD HH:MM:SS"
            try:
                dpart, tpart = dt.split(" ", 1)
                info["date"] = dpart.replace(":", "-")
                info["time"] = tpart.strip()
                info["time_of_day"] = time_of_day_bucket(int(tpart.split(":")[0]))
            except Exception:
                pass

        try:
            gps = ex.get_ifd(IFD_GPS) or {}
        except Exception:
            gps = {}
        if gps:
            lat = dms_to_decimal(gps.get(2), gps.get(1))
            lon = dms_to_decimal(gps.get(4), gps.get(3))
            if lat is not None:
                info["gps_lat"] = lat
            if lon is not None:
                info["gps_lon"] = lon

    return info


# ------------------------------------------------- resize + save

def resize_long_side(bgr: np.ndarray, long_side: int) -> np.ndarray:
    """Scale so max(h, w) == long_side exactly. Aspect preserved, no crop/pad."""
    h, w = bgr.shape[:2]
    if max(h, w) == long_side:
        return bgr
    scale = long_side / float(max(h, w))
    if w >= h:
        new_w, new_h = long_side, max(1, int(round(h * scale)))
    else:
        new_h, new_w = long_side, max(1, int(round(w * scale)))
    # INTER_AREA is the correct choice for downscaling (it area-averages, so no
    # aliasing); Lanczos is for upscaling and ringing-sensitive enlargement.
    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LANCZOS4
    return cv2.resize(bgr, (new_w, new_h), interpolation=interp)


def save_jpeg_q95_444(bgr: np.ndarray, dest: Path) -> None:
    """High-quality JPEG: q95, no chroma subsampling, orientation normalised to 1.

    Saved via Pillow because OpenCV's imwrite cannot disable chroma subsampling.
    No EXIF block is written at all, so there is no orientation tag left to
    re-apply downstream.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    Image.fromarray(rgb).save(
        dest, format="JPEG", quality=95, subsampling=0,
        optimize=True, progressive=False,
    )


# ------------------------------------------------- manual-column preservation

def load_existing_manual(csv_path: Path) -> dict[str, dict]:
    if not csv_path.exists():
        return {}
    out = {}
    try:
        with csv_path.open(newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                fn = (row.get("filename") or "").strip()
                if fn:
                    out[fn] = {c: (row.get(c) or "").strip() for c in MANUAL_COLUMNS}
    except Exception as exc:
        print(f"  ! could not read existing CSV ({exc}); manual columns start empty")
    return out


# ------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--long-side", type=int, default=1024)
    ap.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="default: data/processed/<long_side>/")
    ap.add_argument("--metadata-csv", type=Path, default=METADATA_CSV)
    ap.add_argument("--metadata-only", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--no-keep-manual", dest="keep_manual", action="store_false",
                    help="discard hand-entered values in the manual columns")
    args = ap.parse_args()

    raw_dir = args.raw_dir
    out_dir = args.out_dir or (PROJECT_ROOT / "data" / "processed" / str(args.long_side))

    if not raw_dir.is_dir():
        print(f"ERROR: raw dir not found: {raw_dir}", file=sys.stderr)
        return 2

    files = sorted(p for p in raw_dir.iterdir()
                   if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if not files:
        print(f"ERROR: no images in {raw_dir}", file=sys.stderr)
        return 2
    print(f"raw dir : {raw_dir}")
    print(f"out dir : {out_dir}")
    print(f"images  : {len(files)}   target long side: {args.long_side}px\n")

    if args.verify_only:
        return verify(out_dir, files, args.long_side)

    existing_manual = load_existing_manual(args.metadata_csv) if args.keep_manual else {}
    rows, rotated, failures = [], 0, []

    for p in files:
        try:
            meta = read_exif(p)
        except Exception as exc:
            failures.append((p.name, f"EXIF read failed: {exc}"))
            continue

        ow, oh = meta["width"], meta["height"]
        orient = meta["orientation"]
        out_w = out_h = ""

        if not args.metadata_only:
            bgr = cv2.imread(str(p), cv2.IMREAD_COLOR)
            if bgr is None:
                failures.append((p.name, "cv2.imread returned None"))
                continue
            bgr = apply_orientation(bgr, orient)
            bgr = resize_long_side(bgr, args.long_side)
            dest = out_dir / f"{p.stem}.jpg"
            save_jpeg_q95_444(bgr, dest)
            out_h, out_w = bgr.shape[:2]
        else:
            dest = out_dir / f"{p.stem}.jpg"
            if dest.exists():
                with Image.open(dest) as im:
                    out_w, out_h = im.size

        if orient != 1:
            rotated += 1

        phone = " ".join(x for x in (meta["make"], meta["model"]) if x)
        # Avoid "OnePlus OnePlus 9 Pro" style duplication.
        if meta["make"] and meta["model"].lower().startswith(meta["make"].lower()):
            phone = meta["model"]

        manual = existing_manual.get(p.name, {})
        rows.append({
            "filename": p.name,
            "date": meta["date"],
            "time": meta["time"],
            "time_of_day": meta["time_of_day"],
            "gps_latitude": meta["gps_lat"],
            "gps_longitude": meta["gps_lon"],
            "location_name": manual.get("location_name", ""),
            "phone_model": phone,
            "orientation_applied": orient,
            "original_width": ow,
            "original_height": oh,
            "output_width": out_w,
            "output_height": out_h,
            "distance_m": manual.get("distance_m", ""),
            "scale_reference_present": manual.get("scale_reference_present", ""),
            "notes": manual.get("notes", ""),
        })

    args.metadata_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.metadata_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {len(rows)} rows -> {args.metadata_csv}")
    print(f"images needing rotation (orientation != 1): {rotated}")
    if failures:
        print(f"\n{len(failures)} FAILURES:")
        for n, why in failures:
            print(f"  {n}: {why}")

    if not args.metadata_only:
        print()
        verify(out_dir, files, args.long_side)
    return 1 if failures else 0


def verify(out_dir: Path, src_files, long_side: int) -> int:
    """Confirm every output exists and has long side exactly `long_side`."""
    print("=== VERIFICATION ===")
    if not out_dir.is_dir():
        print(f"FAIL: output dir missing: {out_dir}")
        return 1
    missing, bad, ok = [], [], 0
    for p in src_files:
        dest = out_dir / f"{p.stem}.jpg"
        if not dest.exists():
            missing.append(dest.name)
            continue
        with Image.open(dest) as im:
            w, h = im.size
            orient = (im.getexif() or {}).get(TAG_ORIENTATION)
        if max(w, h) != long_side:
            bad.append(f"{dest.name} ({w}x{h}, long side {max(w, h)})")
        elif orient not in (None, 1):
            bad.append(f"{dest.name} (orientation tag still {orient})")
        else:
            ok += 1
    extra = [p.name for p in out_dir.iterdir()
             if p.is_file() and p.name not in {f"{s.stem}.jpg" for s in src_files}]
    print(f"inputs                 : {len(src_files)}")
    print(f"outputs with long side exactly {long_side}px : {ok}")
    print(f"missing outputs        : {missing or 'none'}")
    print(f"off-spec outputs       : {bad or 'none'}")
    print(f"unexpected extra files : {extra or 'none'}")
    good = not missing and not bad and ok == len(src_files)
    print(f"RESULT: {'OK' if good else 'FAIL'}")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
