#!/usr/bin/env python3
"""
Phase 3 evaluation harness.

Scores a folder of images with no-reference image-quality metrics (NIQE,
BRISQUE) plus a colour-shift guard against a baseline, and writes one CSV per
method to results/metrics/<label>.csv.

The harness exists so that every enhancement method is scored by identical
code at identical settings. Adding a method should mean writing the method and
running this once -- nothing about the measurement changes.

-----------------------------------------------------------------------------
 THE BASELINE MUST BE data/processed/1024, NOT data/raw
-----------------------------------------------------------------------------
NIQE and BRISQUE are scale-dependent. Their MSCN normalisation uses a fixed
7x7 pixel window, so the same scene at 4000px and at 1024px yields different
texture statistics with no change in quality; NIQE additionally tiles the image
into 96x96 blocks. A baseline computed on full-resolution data/raw frames is
therefore NOT comparable with any method output computed at 1024px, and cannot
serve as "the number every method must beat".

So:
  * the no-enhancement baseline is  data/processed/1024  labelled 'baseline'
  * data/raw is scored separately,  labelled 'raw_reference', purely to
    quantify the scale effect rather than assume it

Never compare a 'raw_reference' row against a method row. The --label is
recorded on every row so this stays visible in the combined table.

-----------------------------------------------------------------------------
 USAGE
-----------------------------------------------------------------------------
  # the no-enhancement baseline (do this first)
  python scripts/evaluate.py data/processed/1024 --label baseline

  # the scale-effect reference set (optional, run once)
  python scripts/evaluate.py data/raw --label raw_reference --no-colour

  # any enhancement method, later
  python scripts/evaluate.py data/enhanced/clahe --label clahe

  # combine everything into one long-format table for comparison
  python scripts/evaluate.py --combine

Output CSV columns:
  method, filename, scene_id, width, height, niqe, brisque,
  delta_e_mean, delta_e_p95, dL_mean, da_mean, db_mean,
  baseline_niqe, baseline_brisque, niqe_delta, brisque_delta,
  load_ok, error

Rows are written in sorted filename order. Colour columns are blank when the
folder being scored IS the baseline (nothing to compare against), and when
--no-colour is passed.

Requires the wdfs env: pyiqa 0.1.16, torch (CPU is fine), opencv, numpy.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_DIR = PROJECT_ROOT / "data" / "processed" / "1024"
METRICS_DIR = PROJECT_ROOT / "results" / "metrics"
CAPTURE_CSV = PROJECT_ROOT / "data" / "metadata" / "capture_metadata.csv"
TAGS_CSV = PROJECT_ROOT / "data" / "metadata" / "degradation_tags.csv"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}

SEED = 20261009

COLUMNS = [
    "method", "filename", "scene_id", "width", "height",
    "niqe", "brisque",
    "delta_e_mean", "delta_e_p95", "dL_mean", "da_mean", "db_mean",
    "baseline_niqe", "baseline_brisque", "niqe_delta", "brisque_delta",
    "load_ok", "error",
]


# ---------------------------------------------------------------------------
#  determinism
# ---------------------------------------------------------------------------

def set_seeds(seed: int = SEED) -> None:
    """Seed everything we can.

    NOTE: NIQE and BRISQUE as implemented in pyiqa are deterministic feature
    computations -- no sampling, no dropout, no data augmentation. Seeding is
    belt-and-braces so that any future metric added here (a learned one, say)
    does not silently introduce run-to-run variation. Use --check-determinism
    to verify empirically rather than trusting this comment.
    """
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except Exception:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        torch.use_deterministic_algorithms(True, warn_only=True)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  scene lookup
# ---------------------------------------------------------------------------

def _read_csv_skip_comments(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        lines = [l for l in fh if not l.lstrip().startswith("#")]
    if not lines:
        return []
    try:
        return list(csv.DictReader(lines))
    except Exception:
        return []


def load_scene_map() -> dict[str, str]:
    """filename -> scene_id, preferring degradation_tags.csv (it has scene_id)."""
    smap: dict[str, str] = {}
    for row in _read_csv_skip_comments(TAGS_CSV):
        fn = (row.get("filename") or "").strip()
        sid = (row.get("scene_id") or "").strip()
        if fn and sid:
            smap[fn] = sid
    if smap:
        return smap

    # Fallback: derive from capture timestamps the same way the scaffold did.
    import datetime as dt
    recs = []
    for row in _read_csv_skip_comments(CAPTURE_CSV):
        fn = (row.get("filename") or "").strip()
        d, t = (row.get("date") or "").strip(), (row.get("time") or "").strip()
        if not fn:
            continue
        ts = None
        if d and t:
            try:
                ts = dt.datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M:%S")
            except ValueError:
                ts = None
        recs.append((ts, fn))
    dated = sorted([r for r in recs if r[0]], key=lambda r: r[0])
    scene, prev = 0, None
    for ts, fn in dated:
        if prev is None or (ts - prev).total_seconds() > 30:
            scene += 1
        smap[fn] = f"scene_{scene:02d}"
        prev = ts
    return smap


# ---------------------------------------------------------------------------
#  colour shift
# ---------------------------------------------------------------------------

def _rgb_to_lab(bgr):
    """BGR uint8 -> CIELAB float, L in 0..100, a/b roughly -128..127.

    Uses OpenCV's sRGB->Lab (D65). OpenCV's 32-bit float path returns true
    CIELAB ranges, unlike its 8-bit path which packs L into 0..255.
    """
    import cv2
    import numpy as np
    rgbf = bgr.astype(np.float32) / 255.0
    return cv2.cvtColor(rgbf, cv2.COLOR_BGR2LAB)


def _ciede2000(lab1, lab2):
    """Per-pixel CIEDE2000 colour difference between two CIELAB images.

    WHY CIEDE2000 RATHER THAN PLAIN CIE76 (Euclidean dE):
    CIELAB is only approximately perceptually uniform. A fixed Euclidean
    distance corresponds to visibly different amounts of colour change
    depending on where you are in the space -- notably it overstates
    differences in saturated blues and understates them in near-neutrals.
    CIEDE2000 adds lightness/chroma/hue weighting and a blue-region rotation
    term that correct for this. Since the colours this project cares about
    (brown cardboard, blue polythene, green vegetation, grey rubble) span
    exactly the regions where CIE76 misbehaves, CIEDE2000 is the right choice
    despite being slower. Implemented here directly to avoid adding
    scikit-image to the pinned dependency set.

    Returns a float32 array of per-pixel dE00.
    """
    import numpy as np

    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]

    avg_L = (L1 + L2) / 2.0
    C1 = np.sqrt(a1 ** 2 + b1 ** 2)
    C2 = np.sqrt(a2 ** 2 + b2 ** 2)
    avg_C = (C1 + C2) / 2.0

    G = 0.5 * (1 - np.sqrt((avg_C ** 7) / (avg_C ** 7 + 25.0 ** 7 + 1e-12)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p = np.sqrt(a1p ** 2 + b1 ** 2)
    C2p = np.sqrt(a2p ** 2 + b2 ** 2)
    avg_Cp = (C1p + C2p) / 2.0

    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0

    dLp = L2 - L1
    dCp = C2p - C1p

    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, dhp)
    dhp = np.where(dhp < -180, dhp + 360, dhp)
    dhp = np.where((C1p * C2p) == 0, 0.0, dhp)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp / 2.0))

    hsum = h1p + h2p
    hdiff = np.abs(h1p - h2p)
    avg_hp = np.where((C1p * C2p) == 0, hsum,
                      np.where(hdiff <= 180, hsum / 2.0,
                               np.where(hsum < 360, (hsum + 360) / 2.0,
                                        (hsum - 360) / 2.0)))

    T = (1
         - 0.17 * np.cos(np.radians(avg_hp - 30))
         + 0.24 * np.cos(np.radians(2 * avg_hp))
         + 0.32 * np.cos(np.radians(3 * avg_hp + 6))
         - 0.20 * np.cos(np.radians(4 * avg_hp - 63)))

    d_ro = 30 * np.exp(-(((avg_hp - 275) / 25.0) ** 2))
    Rc = 2 * np.sqrt((avg_Cp ** 7) / (avg_Cp ** 7 + 25.0 ** 7 + 1e-12))
    Sl = 1 + ((0.015 * ((avg_L - 50) ** 2)) / np.sqrt(20 + ((avg_L - 50) ** 2)))
    Sc = 1 + 0.045 * avg_Cp
    Sh = 1 + 0.015 * avg_Cp * T
    Rt = -np.sin(np.radians(2 * d_ro)) * Rc

    dE = np.sqrt(
        (dLp / Sl) ** 2
        + (dCp / Sc) ** 2
        + (dHp / Sh) ** 2
        + Rt * (dCp / Sc) * (dHp / Sh)
    )
    return dE.astype(np.float32)


def colour_shift(test_bgr, base_bgr) -> dict:
    """Colour change of a method's output relative to its baseline image.

    THIS IS A GUARD, NOT A DEGRADATION MEASURE. Phase 2 tagged colour_cast at
    0/77, so there is no pre-existing colour fault to correct. These numbers
    exist to catch an enhancement method INTRODUCING colour damage -- which
    NIQE and BRISQUE are structurally unable to see, because both operate on a
    single luminance channel. See notes/niqe_brisque_explained.md section 6.4.

    Returns mean and 95th-percentile dE00 (magnitude), plus the mean SIGNED
    shift in each of L*, a*, b* so the direction is visible: a method that
    uniformly yellows the image and one that uniformly blues it have the same
    dE but opposite db_mean.
    """
    import cv2
    import numpy as np

    if test_bgr.shape[:2] != base_bgr.shape[:2]:
        base_bgr = cv2.resize(base_bgr, (test_bgr.shape[1], test_bgr.shape[0]),
                              interpolation=cv2.INTER_AREA)

    lab_t = _rgb_to_lab(test_bgr)
    lab_b = _rgb_to_lab(base_bgr)
    dE = _ciede2000(lab_b, lab_t)
    diff = lab_t - lab_b
    return {
        "delta_e_mean": float(dE.mean()),
        "delta_e_p95": float(np.percentile(dE, 95)),
        "dL_mean": float(diff[..., 0].mean()),
        "da_mean": float(diff[..., 1].mean()),
        "db_mean": float(diff[..., 2].mean()),
    }


# ---------------------------------------------------------------------------
#  metrics
# ---------------------------------------------------------------------------

class MetricBank:
    """Instantiates each pyiqa metric ONCE and reuses it for every image.

    Rebuilding a metric per image re-reads the pristine model file / SVR
    weights from disk each time, which dominates runtime for cheap metrics
    like these.
    """

    def __init__(self, device: str = "cpu", metrics=("niqe", "brisque")):
        import pyiqa
        import torch
        self.device = torch.device(device)
        self.metrics = {}
        for name in metrics:
            print(f"    loading metric '{name}' ...", flush=True)
            self.metrics[name] = pyiqa.create_metric(name, device=self.device)
        self.torch = torch

    def score(self, bgr) -> dict:
        """bgr uint8 HxWx3 -> {'niqe': float, 'brisque': float}"""
        import numpy as np
        rgb = bgr[:, :, ::-1].copy()
        t = self.torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0)
        t = t.float().div(255.0).to(self.device)
        out = {}
        with self.torch.no_grad():
            for name, m in self.metrics.items():
                v = m(t)
                out[name] = float(v.item() if hasattr(v, "item") else v)
        return out


# ---------------------------------------------------------------------------
#  core run
# ---------------------------------------------------------------------------

def list_images(d: Path) -> list[Path]:
    return sorted(p for p in d.iterdir()
                  if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def run(args) -> int:
    import cv2
    import numpy as np

    image_dir: Path = args.image_dir
    label: str = args.label

    # ---- input validation, before any expensive work --------------------
    if not image_dir.exists():
        print(f"ERROR: folder does not exist: {image_dir}", file=sys.stderr)
        return 2
    if not image_dir.is_dir():
        print(f"ERROR: not a folder: {image_dir}", file=sys.stderr)
        return 2

    all_entries = [p for p in image_dir.iterdir() if p.is_file()]
    files = list_images(image_dir)
    skipped_non_image = [p.name for p in all_entries if p not in files]

    if not files:
        print(f"ERROR: no image files in {image_dir}", file=sys.stderr)
        if skipped_non_image:
            print(f"       (folder contains {len(skipped_non_image)} non-image "
                  f"file(s): {', '.join(skipped_non_image[:5])}"
                  f"{' ...' if len(skipped_non_image) > 5 else ''})",
                  file=sys.stderr)
        print(f"       Recognised extensions: "
              f"{', '.join(sorted(IMAGE_EXTS))}", file=sys.stderr)
        return 2

    out_csv = args.out or (METRICS_DIR / f"{label}.csv")
    if out_csv.exists() and not args.overwrite:
        print(f"ERROR: {out_csv} already exists.", file=sys.stderr)
        print("       Refusing to overwrite a previous method's results.",
              file=sys.stderr)
        print("       Pass --overwrite to replace it, or use a different "
              "--label.", file=sys.stderr)
        return 1

    # ---- baseline handling ----------------------------------------------
    baseline_dir: Path = args.baseline_dir
    is_self_baseline = image_dir.resolve() == baseline_dir.resolve()
    do_colour = (not args.no_colour) and (not is_self_baseline)

    baseline_scores: dict[str, dict] = {}
    if args.baseline_csv and args.baseline_csv.exists():
        for row in _read_csv_skip_comments(args.baseline_csv):
            fn = (row.get("filename") or "").strip()
            if not fn:
                continue
            try:
                baseline_scores[fn] = {
                    "niqe": float(row.get("niqe") or "nan"),
                    "brisque": float(row.get("brisque") or "nan"),
                }
            except ValueError:
                pass

    print("=" * 70)
    print(f"  Phase 3 evaluation harness")
    print("=" * 70)
    print(f"  images     : {image_dir}  ({len(files)} file(s))")
    print(f"  label      : {label}")
    print(f"  output     : {out_csv}")
    print(f"  device     : {args.device}")
    print(f"  seed       : {SEED}")
    if skipped_non_image:
        print(f"  skipping   : {len(skipped_non_image)} non-image file(s): "
              f"{', '.join(skipped_non_image[:5])}"
              f"{' ...' if len(skipped_non_image) > 5 else ''}")
    if is_self_baseline:
        print(f"  colour     : OFF - this folder IS the baseline "
              f"(nothing to compare against)")
    elif args.no_colour:
        print(f"  colour     : OFF (--no-colour)")
    else:
        print(f"  colour     : ON, vs {baseline_dir}")
    if baseline_scores:
        print(f"  baseline   : {len(baseline_scores)} score(s) loaded from "
              f"{args.baseline_csv} (for delta columns)")
    print()

    set_seeds()
    bank = MetricBank(device=args.device)
    scene_map = load_scene_map()
    if not scene_map:
        print("  WARNING: no scene map available; scene_id will be blank.")

    rows, failures = [], []
    t0 = time.perf_counter()
    per_image_times = []

    for idx, p in enumerate(files, 1):
        row = {c: "" for c in COLUMNS}
        row["method"] = label
        row["filename"] = p.name
        row["scene_id"] = scene_map.get(p.name, "")
        row["load_ok"] = "yes"

        ti = time.perf_counter()
        try:
            bgr = cv2.imread(str(p), cv2.IMREAD_COLOR)
            if bgr is None:
                raise ValueError("cv2.imread returned None "
                                 "(corrupt, unreadable, or not an image)")
            h, w = bgr.shape[:2]
            row["width"], row["height"] = w, h

            scores = bank.score(bgr)
            row["niqe"] = round(scores["niqe"], 6)
            row["brisque"] = round(scores["brisque"], 6)

            if do_colour:
                base_p = baseline_dir / p.name
                if base_p.exists():
                    base = cv2.imread(str(base_p), cv2.IMREAD_COLOR)
                    if base is not None:
                        cs = colour_shift(bgr, base)
                        for k, v in cs.items():
                            row[k] = round(v, 6)
                    else:
                        row["error"] = "baseline image unreadable"
                else:
                    row["error"] = "no matching baseline image"

            bs = baseline_scores.get(p.name)
            if bs:
                row["baseline_niqe"] = round(bs["niqe"], 6)
                row["baseline_brisque"] = round(bs["brisque"], 6)
                row["niqe_delta"] = round(scores["niqe"] - bs["niqe"], 6)
                row["brisque_delta"] = round(scores["brisque"] - bs["brisque"], 6)

        except Exception as exc:
            # One bad image must not lose the whole run.
            row["load_ok"] = "no"
            row["error"] = f"{type(exc).__name__}: {exc}"
            failures.append((p.name, row["error"]))
            if args.verbose:
                traceback.print_exc()

        dt = time.perf_counter() - ti
        per_image_times.append(dt)
        rows.append(row)

        if idx % 10 == 0 or idx == len(files):
            elapsed = time.perf_counter() - t0
            rate = elapsed / idx
            eta = rate * (len(files) - idx)
            print(f"  [{idx:>3}/{len(files)}] {p.name:<16} "
                  f"{dt:5.2f}s   elapsed {elapsed:6.1f}s   eta {eta:5.1f}s",
                  flush=True)

    total = time.perf_counter() - t0

    # ---- write ----------------------------------------------------------
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        fh.write(f"# Phase 3 metrics | method={label}\n")
        fh.write(f"# source_dir={image_dir}\n")
        fh.write(f"# baseline_dir={baseline_dir if do_colour else '(none)'}\n")
        fh.write(f"# images={len(rows)} failures={len(failures)} "
                 f"seed={SEED} device={args.device}\n")
        fh.write(f"# total_seconds={total:.2f} "
                 f"mean_seconds_per_image={total/max(1,len(rows)):.3f}\n")
        if label == "raw_reference":
            fh.write("# WARNING: full-resolution reference set. NIQE/BRISQUE "
                     "are scale-dependent; these rows are NOT comparable with "
                     "1024px method rows.\n")
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    ok = sum(1 for r in rows if r["load_ok"] == "yes")
    print()
    print(f"  wrote {len(rows)} row(s) -> {out_csv}")
    print(f"  succeeded: {ok}/{len(rows)}")
    print(f"  total runtime      : {total:.1f}s")
    print(f"  mean per image     : {total/max(1,len(rows)):.3f}s")
    if per_image_times:
        srt = sorted(per_image_times)
        print(f"  per-image min/med/max: {srt[0]:.3f}s / "
              f"{srt[len(srt)//2]:.3f}s / {srt[-1]:.3f}s")
    if failures:
        print(f"\n  {len(failures)} FAILURE(S) (recorded in the CSV, run "
              f"not aborted):")
        for n, e in failures:
            print(f"    {n}: {e}")
    return 1 if failures else 0


# ---------------------------------------------------------------------------
#  determinism check
# ---------------------------------------------------------------------------

def check_determinism(args) -> int:
    """Score a few images twice and compare bit-for-bit. Verify, don't assume."""
    import cv2
    files = list_images(args.image_dir)[: args.n_determinism]
    if not files:
        print("no images to check", file=sys.stderr)
        return 2
    print(f"Determinism check on {len(files)} image(s), two independent passes "
          f"with fresh metric objects each time.\n")

    results = []
    for run_i in (1, 2):
        set_seeds()
        bank = MetricBank(device=args.device)
        vals = {}
        for p in files:
            bgr = cv2.imread(str(p), cv2.IMREAD_COLOR)
            vals[p.name] = bank.score(bgr)
        results.append(vals)
        del bank

    allsame = True
    print(f"  {'file':<16} {'niqe run1':>14} {'niqe run2':>14} {'identical':>10}")
    for p in files:
        a = results[0][p.name]
        b = results[1][p.name]
        same = (a["niqe"] == b["niqe"]) and (a["brisque"] == b["brisque"])
        allsame &= same
        print(f"  {p.name:<16} {a['niqe']:>14.10f} {b['niqe']:>14.10f} "
              f"{'YES' if same else 'NO':>10}")
    print(f"\n  {'file':<16} {'brisque run1':>14} {'brisque run2':>14}")
    for p in files:
        a, b = results[0][p.name], results[1][p.name]
        print(f"  {p.name:<16} {a['brisque']:>14.10f} {b['brisque']:>14.10f}")

    print(f"\n  RESULT: metrics are {'DETERMINISTIC' if allsame else 'NON-DETERMINISTIC'} "
          f"run-to-run on this machine.")
    return 0 if allsame else 1


# ---------------------------------------------------------------------------
#  combine
# ---------------------------------------------------------------------------

def combine(args) -> int:
    """Concatenate all results/metrics/*.csv into one long-format table."""
    metrics_dir = METRICS_DIR
    if not metrics_dir.is_dir():
        print(f"ERROR: {metrics_dir} does not exist. Run an evaluation first.",
              file=sys.stderr)
        return 2
    csvs = sorted(p for p in metrics_dir.glob("*.csv")
                  if p.name != "combined.csv")
    if not csvs:
        print(f"ERROR: no per-method CSVs in {metrics_dir}", file=sys.stderr)
        return 2

    all_rows = []
    for c in csvs:
        rs = _read_csv_skip_comments(c)
        print(f"  {c.name:<28} {len(rs):>4} row(s)")
        all_rows.extend(rs)

    out = metrics_dir / "combined.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        fh.write("# Combined long-format Phase 3 metrics table.\n")
        fh.write("# One row per (method, filename). Filter on `method`.\n")
        fh.write("# NOTE: method='raw_reference' rows are full-resolution and "
                 "are NOT comparable with 1024px rows.\n")
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in all_rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    methods = sorted({r.get("method", "") for r in all_rows})
    print(f"\n  wrote {len(all_rows)} row(s) across {len(methods)} method(s) "
          f"-> {out}")
    print(f"  methods: {', '.join(methods)}")
    return 0


# ---------------------------------------------------------------------------

def self_test(args) -> int:
    """Exercise every code path that does NOT require pyiqa.

    Verifies: CIEDE2000 against the Sharma et al. (2005) reference data, the
    colour-shift direction convention, the scene join, CSV schema, and all the
    error-handling paths (missing folder, empty folder, non-image file,
    unreadable image, overwrite protection).

    Does not require torch or pyiqa, so it can be run anywhere to check the
    harness itself is sound before committing to a long metric run.
    """
    import shutil
    import tempfile
    import numpy as np
    import cv2

    passed, failed = 0, []

    def check(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            print(f"  [ OK ] {name}")
        else:
            failed.append(name)
            print(f"  [FAIL] {name} {detail}")

    print("=" * 70)
    print("  evaluate.py self-test (no pyiqa / torch required)")
    print("=" * 70)

    # -- CIEDE2000 against the official reference data --------------------
    print("\n-- CIEDE2000 vs Sharma, Wu & Dalal (2005) reference pairs --")
    cases = [
        (50.0, 2.6772, -79.7751, 50.0, 0.0, -82.7485, 2.0425),
        (50.0, 3.1571, -77.2803, 50.0, 0.0, -82.7485, 2.8615),
        (50.0, 2.8361, -74.0200, 50.0, 0.0, -82.7485, 3.4412),
        (50.0, -1.3802, -84.2814, 50.0, 0.0, -82.7485, 1.0000),
        (50.0, 0.0, 0.0, 50.0, -1.0, 2.0, 2.3669),
        (50.0, 2.49, -0.001, 50.0, -2.49, 0.0009, 7.1792),
        (50.0, 2.5, 0.0, 73.0, 25.0, -18.0, 27.1492),
        (50.0, 2.5, 0.0, 56.0, -27.0, -3.0, 31.9030),
        (60.2574, -34.0099, 36.2677, 60.4626, -34.1751, 39.4387, 1.2644),
        (22.7233, 20.0904, -46.6940, 23.0331, 14.9730, -42.5619, 2.0373),
        (90.9257, -0.5406, -0.9208, 88.6381, -0.8985, -0.7239, 1.5381),
        (2.0776, 0.0795, -1.1350, 0.9033, -0.0636, -0.5514, 0.9082),
    ]
    worst = 0.0
    for L1, a1, b1, L2, a2, b2, exp in cases:
        got = float(_ciede2000(np.array([[[L1, a1, b1]]], np.float32),
                               np.array([[[L2, a2, b2]]], np.float32))[0, 0])
        worst = max(worst, abs(got - exp))
    check(f"all {len(cases)} reference pairs within 2e-3 (worst {worst:.6f})",
          worst < 2e-3)

    # -- colour-shift conventions -----------------------------------------
    print("\n-- colour-shift behaviour --")
    base = np.full((48, 48, 3), 128, np.uint8)
    cs_same = colour_shift(base, base)
    check("identical images give dE 0 and zero signed shifts",
          all(abs(v) < 1e-6 for v in cs_same.values()))

    yellower = base.copy(); yellower[:, :, 0] = 90   # less blue -> yellower
    bluer = base.copy();    bluer[:, :, 0] = 180
    cy, cb = colour_shift(yellower, base), colour_shift(bluer, base)
    check("yellow shift gives positive b*", cy["db_mean"] > 1.0,
          f"(got {cy['db_mean']:+.2f})")
    check("blue shift gives negative b*", cb["db_mean"] < -1.0,
          f"(got {cb['db_mean']:+.2f})")
    check("both shifts give positive dE", cy["delta_e_mean"] > 0
          and cb["delta_e_mean"] > 0)

    brighter = np.full((48, 48, 3), 180, np.uint8)
    cl = colour_shift(brighter, base)
    check("brightening gives positive L*", cl["dL_mean"] > 1.0,
          f"(got {cl['dL_mean']:+.2f})")

    check("mismatched sizes are handled (baseline resized)",
          colour_shift(np.full((24, 24, 3), 200, np.uint8), base) is not None)

    # -- scene join --------------------------------------------------------
    print("\n-- scene join --")
    smap = load_scene_map()
    check("scene map is non-empty", len(smap) > 0, f"(got {len(smap)})")
    if smap:
        check("scene ids look like scene_NN",
              all(s.startswith("scene_") for s in smap.values()))

    # -- error handling ----------------------------------------------------
    print("\n-- error handling --")
    tmp = Path(tempfile.mkdtemp(prefix="evaltest_"))
    try:
        class A:  # minimal args stand-in
            pass

        def mkargs(d, label="t", **kw):
            a = A()
            a.image_dir = d
            a.label = label
            a.baseline_dir = DEFAULT_BASELINE_DIR
            a.baseline_csv = Path("/nonexistent.csv")
            a.out = tmp / f"{label}.csv"
            a.no_colour = True
            a.overwrite = False
            a.device = "cpu"
            a.verbose = False
            for k, v in kw.items():
                setattr(a, k, v)
            return a

        missing = tmp / "does_not_exist"
        check("missing folder returns 2 (not a crash)",
              run(mkargs(missing)) == 2)

        empty = tmp / "empty"; empty.mkdir()
        check("empty folder returns 2", run(mkargs(empty)) == 2)

        nonimg = tmp / "nonimg"; nonimg.mkdir()
        (nonimg / "notes.txt").write_text("not an image")
        check("folder with only non-image files returns 2",
              run(mkargs(nonimg)) == 2)

        # overwrite protection
        guard = tmp / "guard.csv"
        guard.write_text("x")
        a = mkargs(DEFAULT_BASELINE_DIR, out=guard)
        check("refuses to overwrite an existing CSV", run(a) == 1)

        # CSV schema
        check("COLUMNS contains the join keys",
              all(c in COLUMNS for c in ("method", "filename", "scene_id")))
        check("COLUMNS contains both metrics",
              all(c in COLUMNS for c in ("niqe", "brisque")))
        check("COLUMNS contains all colour columns",
              all(c in COLUMNS for c in ("delta_e_mean", "delta_e_p95",
                                         "dL_mean", "da_mean", "db_mean")))

        # corrupt-image handling, via a stub metric bank
        corrupt = tmp / "corrupt"; corrupt.mkdir()
        good = cv2.imread(str(sorted(DEFAULT_BASELINE_DIR.glob("*.jpg"))[0]))
        cv2.imwrite(str(corrupt / "good.jpg"), good)
        (corrupt / "broken.jpg").write_bytes(b"\xff\xd8\xff\xe0 not a jpeg")

        global MetricBank
        real_bank = MetricBank

        class StubBank:
            def __init__(self, *a, **k):
                pass

            def score(self, bgr):
                return {"niqe": 1.0, "brisque": 2.0}

        MetricBank = StubBank
        try:
            rc = run(mkargs(corrupt, label="corrupt"))
            rows = _read_csv_skip_comments(tmp / "corrupt.csv")
            check("corrupt image does not abort the run (other rows survive)",
                  len(rows) == 2)
            check("corrupt image is recorded with load_ok=no",
                  any(r["load_ok"] == "no" for r in rows))
            check("good image in the same folder still scored",
                  any(r["load_ok"] == "yes" and r["niqe"] for r in rows))
            check("run returns 1 when some images failed", rc == 1)
        finally:
            MetricBank = real_bank
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 70)
    if failed:
        print(f"  {len(failed)} FAILURE(S): {', '.join(failed)}")
        print("=" * 70)
        return 1
    print(f"  ALL {passed} SELF-TESTS PASSED")
    print("  (metric computation itself is NOT covered here - it needs pyiqa)")
    print("=" * 70)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="evaluate.py",
        description=(
            "Phase 3 evaluation harness: score a folder of images with NIQE, "
            "BRISQUE and a CIEDE2000 colour-shift guard, and write "
            "results/metrics/<label>.csv."
        ),
        epilog=(
            "EXAMPLES\n"
            "  # 1. the no-enhancement baseline, at the working resolution\n"
            "  python scripts/evaluate.py data/processed/1024 --label baseline\n"
            "\n"
            "  # 2. the full-resolution reference set, to quantify the scale\n"
            "  #    effect (NOT a baseline -- not comparable with 1024px rows)\n"
            "  python scripts/evaluate.py data/raw --label raw_reference "
            "--no-colour\n"
            "\n"
            "  # 3. any enhancement method\n"
            "  python scripts/evaluate.py data/enhanced/clahe --label clahe \\\n"
            "      --baseline-csv results/metrics/baseline.csv\n"
            "\n"
            "  # 4. verify the metrics are deterministic\n"
            "  python scripts/evaluate.py data/processed/1024 --label x "
            "--check-determinism\n"
            "\n"
            "  # 5. combine every per-method CSV into one table\n"
            "  python scripts/evaluate.py --combine\n"
            "\n"
            "WHY THE BASELINE IS data/processed/1024 AND NOT data/raw\n"
            "  NIQE and BRISQUE are scale-dependent (fixed 7x7 normalisation\n"
            "  window; NIQE tiles into 96x96 blocks). Numbers computed on\n"
            "  4000px frames are not comparable with method outputs computed\n"
            "  at 1024px. data/raw is scored only as a labelled reference set\n"
            "  so the scale effect is measured rather than assumed.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("image_dir", nargs="?", type=Path,
                    help="folder of images to score")
    ap.add_argument("--label", type=str,
                    help="method name, recorded on every row and used for the "
                         "output filename (results/metrics/<label>.csv)")
    ap.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR,
                    help="folder of unenhanced images to measure colour shift "
                         "against (default: data/processed/1024)")
    ap.add_argument("--baseline-csv", type=Path,
                    default=METRICS_DIR / "baseline.csv",
                    help="baseline metrics CSV, used to fill the *_delta "
                         "columns (default: results/metrics/baseline.csv)")
    ap.add_argument("--out", type=Path,
                    help="explicit output path (default "
                         "results/metrics/<label>.csv)")
    ap.add_argument("--no-colour", action="store_true",
                    help="skip the colour-shift columns")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace an existing output CSV (refuses by default)")
    ap.add_argument("--device", type=str, default="cpu",
                    help="torch device (default cpu; this project is CPU-only)")
    ap.add_argument("--check-determinism", action="store_true",
                    help="score a few images twice and report whether the "
                         "results are bit-identical, then exit")
    ap.add_argument("--n-determinism", type=int, default=3,
                    help="how many images to use for --check-determinism")
    ap.add_argument("--combine", action="store_true",
                    help="concatenate results/metrics/*.csv into "
                         "combined.csv and exit")
    ap.add_argument("--self-test", action="store_true",
                    help="verify the harness itself (CIEDE2000 against "
                         "published reference data, colour-shift directions, "
                         "scene join, CSV schema, error handling). Needs "
                         "neither torch nor pyiqa.")
    ap.add_argument("--verbose", action="store_true",
                    help="print full tracebacks on per-image failures")
    args = ap.parse_args()

    if args.self_test:
        return self_test(args)
    if args.combine:
        return combine(args)

    if args.image_dir is None:
        ap.error("image_dir is required (or use --combine)")
    if args.check_determinism:
        return check_determinism(args)
    if not args.label:
        ap.error("--label is required")
    if "/" in args.label or "\\" in args.label:
        ap.error("--label must not contain path separators")

    return run(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(130)
