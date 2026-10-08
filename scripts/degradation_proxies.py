#!/usr/bin/env python3
"""
Objective proxy measurements for the Phase 2 degradation audit.

Reads every image in data/processed/1024/ and writes one row per image to
data/metadata/degradation_proxies.csv, with a percentile rank across the set
for every metric.

=============================================================================
 THESE ARE NOT TAGS.
=============================================================================
Every number here is a pixel statistic. None of them perceives anything. They
exist for exactly two purposes:

  1. to make outliers obvious without the user having to judge absolute
     scales (hence the percentile columns), and
  2. to be compared against the user's visual tags AFTERWARDS, so that
     disagreements can reveal a badly-worded rule.

They cannot substitute for visual tagging, because each one confuses the
degradation it targets with ordinary scene content. A grey concrete yard
scores as hazy. A white sack scores as glare. Brown soil scores as a colour
cast. A deliberately shallow-focus close-up scores as blur. In a dataset of
outdoor waste-site photographs, all four of those are normal subject matter,
so the false-positive rate on real scenes is high by construction. Known
failure modes are documented per metric below and in the generated CSV's
companion notes.

Usage (in the wdfs env):
    python scripts/degradation_proxies.py
    python scripts/degradation_proxies.py --image-dir data/processed/1024
    python scripts/degradation_proxies.py --no-percentiles

Deps: opencv-python 4.14, numpy 2.2.6. CPU only; no GPU, no torch.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = PROJECT_ROOT / "data" / "processed" / "1024"
OUT_CSV = PROJECT_ROOT / "data" / "metadata" / "degradation_proxies.csv"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}

# ---------------------------------------------------------------------------
#  Metric documentation: name -> (what it measures, known failure modes)
#  Printed by --explain and written to the sidecar notes file.
# ---------------------------------------------------------------------------
METRIC_DOCS: dict[str, tuple[str, str]] = {
    "dark_channel_mean": (
        "Mean of the dark channel (per-pixel min across B,G,R, then a local "
        "minimum filter over a 15x15 window). Haze adds airlight to every "
        "channel, so even the darkest channel stops being dark. Higher = "
        "more haze-like.",
        "Rises for any genuinely bright, low-saturation scene. A white wall, "
        "overcast sky, dry pale dust underfoot or bare concrete all push it up "
        "with no haze present. Falls to near zero if anything deeply "
        "shadowed is in frame, so one dark bin can mask real haze.",
    ),
    "dark_channel_p95": (
        "95th percentile of the dark channel. Targets the haziest region "
        "rather than the frame average.",
        "Dominated by the single brightest low-saturation patch, so a small "
        "sunlit white object sets it high on an otherwise clear image.",
    ),
    "atmospheric_light": (
        "Estimated airlight: mean intensity of the brightest 0.1% of "
        "dark-channel pixels, as in He et al.'s dark channel prior. Proxy for "
        "how bright the haze veil is.",
        "Assumes the brightest haze-like pixels ARE the airlight. A specular "
        "highlight or blown-out sky hijacks the estimate entirely.",
    ),
    "transmission_mean": (
        "Mean estimated transmission t = 1 - 0.95 * darkchannel/airlight. "
        "1.0 = perfectly clear, 0.0 = fully occluded. LOWER = more haze.",
        "Inherits every weakness of the airlight estimate above, and is "
        "undefined-ish for very dark images where airlight is small.",
    ),
    "transmission_p05": (
        "5th percentile of estimated transmission - the most occluded part of "
        "the frame.",
        "A single blown-out region can drive this low independently of haze.",
    ),
    "clipped_highlight_frac": (
        "Fraction of pixels with luminance >= 250 (near-saturated). Glare "
        "proxy.",
        "Cannot tell blown-out glare from legitimately white subject matter - "
        "white sacks, painted markings, paper, sunlit metal. Also misses "
        "glare that is bright but not quite clipped.",
    ),
    "clipped_highlight_frac_255": (
        "Fraction of pixels at a hard 255 in any channel - true clipping, "
        "where information is actually lost.",
        "JPEG compression at q95 can shift values by a few levels, so true "
        "255 counts are slightly noisy. Still misses near-clipping.",
    ),
    "clipped_shadow_frac": (
        "Fraction of pixels with luminance <= 5. Crushed-shadow proxy.",
        "A dark bin, a tyre or a doorway reads identically to a crushed "
        "shadow. Says nothing about whether the dark region has a sharp edge.",
    ),
    "dark_region_frac": (
        "Fraction of pixels below 0.45 * mean luminance - i.e. 'much darker "
        "than the rest of this image'. Scale-free large-dark-region proxy.",
        "Relative to the image's own mean, so a uniformly dark image has a "
        "small dark_region_frac while a bright image with one dark object has "
        "a large one. Measures contrast of placement, not shadow.",
    ),
    "dark_region_edge_sharpness": (
        "Mean Sobel gradient magnitude along the boundary of the largest "
        "connected dark region (dilate minus erode gives the boundary band). "
        "Targets the 'sharp edge' half of the hard-shadow rule - cast shadows "
        "have crisp boundaries, ambient dimness does not.",
        "A dark OBJECT also has a sharp boundary, and scores the same as a "
        "cast shadow. This is the single most confounded metric here: it "
        "cannot distinguish 'shadow with a sharp edge' from 'dark thing'. "
        "Treat it as 'there is a well-defined dark region', nothing more.",
    ),
    "dark_region_largest_frac": (
        "Area fraction of the largest connected dark component - pairs with "
        "the 10% area condition in the hard_shadow rule.",
        "Connectivity is fragile: a shadow broken by a bright object becomes "
        "several small components and under-reports.",
    ),
    "rms_contrast": (
        "Standard deviation of luminance, normalised to 0-1. The standard "
        "global contrast measure.",
        "A bimodal image (half very dark, half very bright) scores high even "
        "though the midtones are empty. High RMS contrast does not mean the "
        "image looks good.",
    ),
    "luminance_p05_p95_spread": (
        "5th-to-95th percentile luminance range, 0-1. Directly operationalises "
        "'no true blacks and no true whites' - a low value means the tonal "
        "range is squeezed into the middle.",
        "Outlier-robust by design, so it ignores small genuinely-black or "
        "genuinely-white patches. An image with a tiny deep shadow still reads "
        "as low spread.",
    ),
    "michelson_contrast": (
        "(p99 - p01) / (p99 + p01) on luminance. An alternative contrast "
        "formulation, less sensitive to the bulk distribution.",
        "Driven entirely by the tails, so a handful of clipped pixels at "
        "either end saturates it toward 1.",
    ),
    "greyworld_deviation": (
        "Euclidean distance of the per-channel means from perfect grey "
        "(mean_R = mean_G = mean_B), normalised. Colour-cast proxy under the "
        "grey-world assumption.",
        "The grey-world assumption fails whenever the scene genuinely is not "
        "colour-neutral on average. Brown soil, green vegetation and orange "
        "plastic are all real subject colour, not cast - and this metric "
        "cannot tell the difference.",
    ),
    "lab_mean_a": (
        "Mean a* in CIELAB: negative = green, positive = magenta/red. "
        "Perceptually uniform, so a given deviation means roughly the same "
        "amount of visible tint anywhere in the space.",
        "Still confounded by real scene colour. Vegetation drags a* negative; "
        "brick and soil drag it positive.",
    ),
    "lab_mean_b": (
        "Mean b* in CIELAB: negative = blue, positive = yellow. Usually the "
        "more informative of the two for daylight/shade colour casts.",
        "Open shade genuinely is blue and late sun genuinely is yellow, so a "
        "large |b*| can be a correct record of the light rather than a fault.",
    ),
    "lab_chroma_mean": (
        "Mean sqrt(a*^2 + b*^2) - overall colourfulness.",
        "High for a vivid, correctly-exposed scene. Not a defect measure on "
        "its own; only useful next to lab_mean_a / lab_mean_b.",
    ),
    "laplacian_variance": (
        "Variance of the Laplacian - the standard cheap focus measure. Lower "
        "= blurrier.",
        "Confounds blur with scene content: a smooth wall scores low while a "
        "gravel pile scores high at identical focus. Also depends on "
        "resolution, so these values are only comparable because every image "
        "is exactly 1024px on the long side.",
    ),
    "tenengrad": (
        "Mean squared Sobel gradient magnitude - a second sharpness measure "
        "that degrades differently from Laplacian variance.",
        "Same content confound as laplacian_variance; agreement between the "
        "two is more trustworthy than either alone.",
    ),
    "mean_luminance": (
        "Mean luminance, 0-1. Overall exposure.",
        "Says nothing about distribution - a correctly exposed image and a "
        "half-black/half-white one can share a mean of 0.5.",
    ),
    "std_luminance": (
        "Standard deviation of luminance, 0-255 scale. Same quantity as "
        "rms_contrast, retained unnormalised for convenience.",
        "See rms_contrast.",
    ),
    "saturation_mean": (
        "Mean HSV saturation, 0-1. Context for the colour-cast metrics.",
        "Haze and glare both desaturate, so a low value is ambiguous between "
        "them.",
    ),
}


# ---------------------------------------------------------------------------
#  metric computation
# ---------------------------------------------------------------------------

def dark_channel(bgr: np.ndarray, patch: int = 15) -> np.ndarray:
    """Per-pixel channel minimum, then a local min filter (erosion)."""
    min_ch = bgr.min(axis=2)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (patch, patch))
    return cv2.erode(min_ch, kernel)


def estimate_airlight(bgr: np.ndarray, dc: np.ndarray, top_frac: float = 0.001) -> float:
    """Mean intensity of the brightest top_frac of dark-channel pixels."""
    flat = dc.reshape(-1)
    n = max(1, int(flat.size * top_frac))
    idx = np.argpartition(flat, -n)[-n:]
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).reshape(-1)
    return float(grey[idx].mean())


def largest_dark_component(dark_mask: np.ndarray) -> tuple[np.ndarray, float]:
    """Largest connected component of dark_mask; returns (mask, area_fraction)."""
    num, labels, stats, _ = cv2.connectedComponentsWithStats(
        dark_mask.astype(np.uint8), connectivity=8)
    if num <= 1:
        return np.zeros_like(dark_mask, dtype=bool), 0.0
    # label 0 is background
    areas = stats[1:, cv2.CC_STAT_AREA]
    big = int(np.argmax(areas)) + 1
    mask = (labels == big)
    return mask, float(mask.sum()) / mask.size


def boundary_sharpness(grey: np.ndarray, mask: np.ndarray) -> float:
    """Mean Sobel gradient magnitude in a thin band around a region boundary."""
    if not mask.any():
        return 0.0
    m = mask.astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    band = (cv2.dilate(m, k) - cv2.erode(m, k)).astype(bool)
    if not band.any():
        return 0.0
    gx = cv2.Sobel(grey, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(grey, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(gx * gx + gy * gy)
    return float(mag[band].mean())


def compute_metrics(path: Path) -> dict | None:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        return None

    h, w = bgr.shape[:2]
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    greyf = grey.astype(np.float64)

    # --- haze: dark channel prior -------------------------------------------
    dc = dark_channel(bgr, patch=15)
    dcf = dc.astype(np.float64)
    airlight = estimate_airlight(bgr, dc)
    a_safe = max(airlight, 1e-6)
    transmission = 1.0 - 0.95 * (dcf / a_safe)
    transmission = np.clip(transmission, 0.0, 1.0)

    # --- clipping ------------------------------------------------------------
    clipped_hi = float((grey >= 250).mean())
    clipped_hi_255 = float((bgr.max(axis=2) >= 255).mean())
    clipped_lo = float((grey <= 5).mean())

    # --- dark regions (hard-shadow proxy) -----------------------------------
    mean_lum = float(greyf.mean())
    dark_thresh = 0.45 * mean_lum
    dark_mask = greyf < dark_thresh
    dark_frac = float(dark_mask.mean())
    # clean up speckle before connected components
    dm = cv2.morphologyEx(dark_mask.astype(np.uint8), cv2.MORPH_OPEN,
                          cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    big_mask, big_frac = largest_dark_component(dm.astype(bool))
    edge_sharp = boundary_sharpness(greyf, big_mask)

    # --- contrast ------------------------------------------------------------
    p01, p05, p95, p99 = np.percentile(greyf, [1, 5, 95, 99])
    rms_contrast = float(greyf.std() / 255.0)
    spread = float((p95 - p05) / 255.0)
    mich = float((p99 - p01) / (p99 + p01)) if (p99 + p01) > 0 else 0.0

    # --- colour --------------------------------------------------------------
    means = bgr.reshape(-1, 3).mean(axis=0)          # B, G, R
    grand = float(means.mean())
    greyworld = float(np.linalg.norm(means - grand) / 255.0)

    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    # OpenCV 8-bit LAB: L in 0..255, a/b offset by 128
    lab_a = lab[:, :, 1].astype(np.float64) - 128.0
    lab_b = lab[:, :, 2].astype(np.float64) - 128.0
    lab_mean_a = float(lab_a.mean())
    lab_mean_b = float(lab_b.mean())
    lab_chroma = float(np.sqrt(lab_a ** 2 + lab_b ** 2).mean())

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat_mean = float(hsv[:, :, 1].mean() / 255.0)

    # --- sharpness -----------------------------------------------------------
    lap_var = float(cv2.Laplacian(greyf, cv2.CV_64F).var())
    gx = cv2.Sobel(greyf, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(greyf, cv2.CV_64F, 0, 1, ksize=3)
    tenengrad = float((gx * gx + gy * gy).mean())

    return {
        "filename": path.name,
        "width": w,
        "height": h,
        "dark_channel_mean": dcf.mean() / 255.0,
        "dark_channel_p95": float(np.percentile(dcf, 95)) / 255.0,
        "atmospheric_light": airlight / 255.0,
        "transmission_mean": float(transmission.mean()),
        "transmission_p05": float(np.percentile(transmission, 5)),
        "clipped_highlight_frac": clipped_hi,
        "clipped_highlight_frac_255": clipped_hi_255,
        "clipped_shadow_frac": clipped_lo,
        "dark_region_frac": dark_frac,
        "dark_region_largest_frac": big_frac,
        "dark_region_edge_sharpness": edge_sharp,
        "rms_contrast": rms_contrast,
        "luminance_p05_p95_spread": spread,
        "michelson_contrast": mich,
        "greyworld_deviation": greyworld,
        "lab_mean_a": lab_mean_a,
        "lab_mean_b": lab_mean_b,
        "lab_chroma_mean": lab_chroma,
        "laplacian_variance": lap_var,
        "tenengrad": tenengrad,
        "mean_luminance": mean_lum / 255.0,
        "std_luminance": float(greyf.std()),
        "saturation_mean": sat_mean,
    }


METRIC_ORDER = [
    "dark_channel_mean", "dark_channel_p95", "atmospheric_light",
    "transmission_mean", "transmission_p05",
    "clipped_highlight_frac", "clipped_highlight_frac_255",
    "clipped_shadow_frac", "dark_region_frac", "dark_region_largest_frac",
    "dark_region_edge_sharpness",
    "rms_contrast", "luminance_p05_p95_spread", "michelson_contrast",
    "greyworld_deviation", "lab_mean_a", "lab_mean_b", "lab_chroma_mean",
    "laplacian_variance", "tenengrad",
    "mean_luminance", "std_luminance", "saturation_mean",
]


def percentile_ranks(values: list[float]) -> list[float]:
    """Rank each value 0-100 across the set (average rank for ties)."""
    n = len(values)
    if n <= 1:
        return [50.0] * n
    arr = np.asarray(values, dtype=np.float64)
    order = arr.argsort()
    ranks = np.empty(n, dtype=np.float64)
    ranks[order] = np.arange(n, dtype=np.float64)
    # average ranks for ties
    for v in np.unique(arr):
        idx = np.where(arr == v)[0]
        if idx.size > 1:
            ranks[idx] = ranks[idx].mean()
    return list(np.round(ranks / (n - 1) * 100.0, 1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image-dir", type=Path, default=IMAGE_DIR)
    ap.add_argument("--out", type=Path, default=OUT_CSV)
    ap.add_argument("--no-percentiles", action="store_true")
    ap.add_argument("--explain", action="store_true",
                    help="print what each metric measures and its failure modes, then exit")
    args = ap.parse_args()

    if args.explain:
        print("=" * 78)
        print(" PROXY METRICS - what each measures, and how it lies")
        print("=" * 78)
        for name in METRIC_ORDER:
            what, fails = METRIC_DOCS[name]
            print(f"\n{name}")
            print(f"  MEASURES : {what}")
            print(f"  FAILS ON : {fails}")
        print("\n" + "=" * 78)
        print(" None of these is a tag. See notes/degradation_rules.md.")
        print("=" * 78)
        return 0

    if not args.image_dir.is_dir():
        print(f"ERROR: image dir not found: {args.image_dir}", file=sys.stderr)
        print("Run scripts/preprocess.py first.", file=sys.stderr)
        return 2

    files = sorted(p for p in args.image_dir.iterdir()
                   if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if not files:
        print(f"ERROR: no images in {args.image_dir}", file=sys.stderr)
        return 2

    print(f"image dir : {args.image_dir}")
    print(f"images    : {len(files)}")
    print("computing proxies (CPU only, no GPU needed)...")

    rows, failures = [], []
    for i, p in enumerate(files, 1):
        m = compute_metrics(p)
        if m is None:
            failures.append(p.name)
            continue
        rows.append(m)
        if i % 20 == 0 or i == len(files):
            print(f"  {i}/{len(files)}")

    if not rows:
        print("ERROR: no images could be read", file=sys.stderr)
        return 1

    # --- percentile ranks ---------------------------------------------------
    columns = ["filename", "width", "height"] + METRIC_ORDER
    if not args.no_percentiles:
        for name in METRIC_ORDER:
            pr = percentile_ranks([r[name] for r in rows])
            for r, v in zip(rows, pr):
                r[f"{name}_pct"] = v
        columns += [f"{n}_pct" for n in METRIC_ORDER]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        fh.write("# Objective proxy measurements - NOT degradation tags.\n")
        fh.write("# Generated by scripts/degradation_proxies.py\n")
        fh.write("# Each *_pct column is that metric's percentile rank (0-100) across\n")
        fh.write("# this image set, so outliers are visible without judging absolute scales.\n")
        fh.write("# Run with --explain for what each metric measures and its failure modes.\n")
        fh.write("# Do NOT consult this file while visually tagging; it is a cross-check only.\n")
        fh.write("#\n")
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            out = {}
            for k in columns:
                v = r.get(k, "")
                out[k] = round(v, 6) if isinstance(v, float) else v
            w.writerow(out)

    print(f"\nwrote {len(rows)} rows x {len(columns)} columns -> {args.out}")
    if failures:
        print(f"FAILED to read {len(failures)}: {', '.join(failures)}")

    # --- sidecar notes ------------------------------------------------------
    notes = args.out.with_name(args.out.stem + "_README.md")
    with notes.open("w", encoding="utf-8") as fh:
        fh.write("# Proxy metrics - what each measures and how it lies\n\n")
        fh.write("Generated by `scripts/degradation_proxies.py`.\n\n")
        fh.write("**These are not tags.** They are pixel statistics that correlate "
                 "loosely with perceived degradation. Where a proxy and a visual tag "
                 "disagree, assume the proxy is wrong.\n\n")
        for name in METRIC_ORDER:
            what, fails = METRIC_DOCS[name]
            fh.write(f"## `{name}`\n\n**Measures:** {what}\n\n**Fails on:** {fails}\n\n")
    print(f"wrote metric documentation -> {notes}")

    # --- console distribution summary --------------------------------------
    print("\n=== DISTRIBUTIONS ACROSS THE SET ===")
    print(f"  {'metric':<30} {'min':>10} {'p25':>10} {'median':>10} {'p75':>10} {'max':>10}")
    print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    for name in METRIC_ORDER:
        v = np.array([r[name] for r in rows], dtype=np.float64)
        q = np.percentile(v, [25, 50, 75])
        print(f"  {name:<30} {v.min():>10.4f} {q[0]:>10.4f} {q[1]:>10.4f} "
              f"{q[2]:>10.4f} {v.max():>10.4f}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
