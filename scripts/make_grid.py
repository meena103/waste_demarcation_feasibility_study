#!/usr/bin/env python3
"""
Build a side-by-side comparison figure for one image across every method.

Supervisors read pictures faster than tables. This produces the picture, with
the numbers printed under each panel so the figure stands on its own.

Method folders are AUTO-DISCOVERED under data/enhanced/<method>/. Adding a new
enhancement method means creating its output folder -- nothing here changes.

    results/grids/<imagename>_grid.png

Usage
-----
    python scripts/make_grid.py img_012
    python scripts/make_grid.py img_012.jpg
    python scripts/make_grid.py data/processed/1024/img_012.jpg   # path is fine

    # all six standing representative frames in one call
    python scripts/make_grid.py --all-representative

    # detail at native pixel scale, with a locator thumbnail for context
    python scripts/make_grid.py img_012 --crop 400,300,320,240

    # full frame with a magnified inset in the corner
    python scripts/make_grid.py img_012 --inset 400,300,320,240

    # clean figure for slides, no numbers
    python scripts/make_grid.py img_012 --metrics-off

Notes
-----
* The unenhanced frame from data/processed/1024 is ALWAYS the first panel and
  is labelled "BASELINE (unenhanced original)".
* NIQE / BRISQUE are read from results/metrics/<method>.csv when present.
  Both are lower-is-better and the figure says so on every panel.
* Mean CIEDE2000 colour shift is printed per method panel. The baseline has no
  dE by definition -- it is its own reference -- so the figure says
  "dE00: n/a (is the reference)" rather than printing 0.00 as if it were a
  result.
* A missing metrics CSV never blocks the picture; the metric line renders as
  unavailable instead.

Requires: matplotlib (Agg backend), opencv, numpy. No torch, no pyiqa.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")           # headless: never try to open a window
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = PROJECT_ROOT / "data" / "processed" / "1024"
ENHANCED_DIR = PROJECT_ROOT / "data" / "enhanced"
METRICS_DIR = PROJECT_ROOT / "results" / "metrics"
GRID_DIR = PROJECT_ROOT / "results" / "grids"
TAGS_CSV = PROJECT_ROOT / "data" / "metadata" / "degradation_tags.csv"

BASELINE_LABEL = "baseline"
DEGRADATIONS = ["haze_dust", "hard_shadow", "glare", "colour_cast", "low_contrast"]
IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"]

REPRESENTATIVE = [
    "img_001.jpg",   # scene_02  clean reference
    "img_073.jpg",   # scene_01  hard_shadow (purest)
    "img_066.jpg",   # scene_07  hard_shadow (largest scene)
    "img_027.jpg",   # scene_06  low_contrast
    "img_004.jpg",   # scene_03  glare
    "img_012.jpg",   # scene_04  haze_dust
]

# Panel geometry. 5.5in at 200dpi = 1100px per panel, which stays legible when
# a 3-panel figure is shrunk to fit a projector.
DEFAULT_PANEL_W_IN = 5.5
DEFAULT_DPI = 200


# ---------------------------------------------------------------------------
#  small helpers
# ---------------------------------------------------------------------------

def read_csv_skip_comments(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        lines = [l for l in fh if not l.lstrip().startswith("#")]
    return list(csv.DictReader(lines)) if lines else []


def resolve_name(raw: str) -> str | None:
    """Accept 'img_012', 'img_012.jpg', or any path to it. -> 'img_012.jpg'.

    Returns the filename as it exists in the baseline folder, or None.
    """
    cand = Path(raw).name
    stem = Path(cand).stem

    p = BASELINE_DIR / cand
    if p.exists():
        return p.name
    for ext in IMAGE_EXTS:
        p = BASELINE_DIR / f"{stem}{ext}"
        if p.exists():
            return p.name
    # last resort: case-insensitive stem match
    for p in sorted(BASELINE_DIR.glob("*")):
        if p.is_file() and p.stem.lower() == stem.lower():
            return p.name
    return None


def discover_methods() -> list[str]:
    """Every subfolder of data/enhanced/ that contains at least one image."""
    if not ENHANCED_DIR.is_dir():
        return []
    out = []
    for d in sorted(ENHANCED_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if any(p.suffix.lower() in IMAGE_EXTS for p in d.iterdir() if p.is_file()):
            out.append(d.name)
    return out


def load_rgb(path: Path):
    """Load an image as RGB uint8.

    OpenCV returns BGR. Matplotlib expects RGB. Getting this backwards swaps
    blue and red -- blue polythene would render orange, which is precisely the
    material distinction this project exists to preserve. The conversion is
    here, once, and is covered by --self-test.
    """
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError(f"could not read image: {path}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def parse_region(s: str, w: int, h: int) -> tuple[int, int, int, int]:
    """'x,y,w,h' -> clamped integer box inside the image."""
    try:
        parts = [int(float(v)) for v in s.replace(" ", "").split(",")]
    except ValueError:
        raise ValueError(f"could not parse region {s!r}; expected x,y,w,h")
    if len(parts) != 4:
        raise ValueError(f"region needs 4 numbers (x,y,w,h), got {len(parts)}")
    x, y, rw, rh = parts
    if rw <= 0 or rh <= 0:
        raise ValueError("region width and height must be positive")
    x = max(0, min(x, w - 1))
    y = max(0, min(y, h - 1))
    rw = max(1, min(rw, w - x))
    rh = max(1, min(rh, h - y))
    return x, y, rw, rh


# ---------------------------------------------------------------------------
#  metrics / tags
# ---------------------------------------------------------------------------

def load_metrics_for(filename: str, methods: list[str]) -> dict[str, dict]:
    """method -> {'niqe':float|None, 'brisque':float|None, 'de':float|None,
                  'csv_found':bool}"""
    out = {}
    for m in methods:
        rec = {"niqe": None, "brisque": None, "de": None, "csv_found": False}
        csv_path = METRICS_DIR / f"{m}.csv"
        rows = read_csv_skip_comments(csv_path)
        if rows:
            rec["csv_found"] = True
            for r in rows:
                if (r.get("filename") or "").strip() == filename:
                    for key, col in (("niqe", "niqe"), ("brisque", "brisque"),
                                     ("de", "delta_e_mean")):
                        v = (r.get(col) or "").strip()
                        if v:
                            try:
                                rec[key] = float(v)
                            except ValueError:
                                pass
                    break
        out[m] = rec
    return out


def load_tags(filename: str) -> dict:
    for r in read_csv_skip_comments(TAGS_CSV):
        if (r.get("filename") or "").strip() == filename:
            return r
    return {}


def tag_caption(tags: dict) -> tuple[str, str]:
    """-> (scene_id, 'tag, tag' or 'clean (none)' or 'untagged')"""
    if not tags:
        return "", "untagged"
    scene = (tags.get("scene_id") or "").strip()
    pos = [d for d in DEGRADATIONS if (tags.get(d) or "").strip() == "yes"]
    if pos:
        return scene, ", ".join(pos)
    if (tags.get("none") or "").strip() == "yes":
        return scene, "clean (none)"
    return scene, "untagged"


def metric_lines(method: str, rec: dict, is_baseline: bool,
                 baseline_rec: dict | None) -> list[str]:
    """The text block printed under a panel."""
    if not rec["csv_found"]:
        return [f"metrics unavailable", f"(no results/metrics/{method}.csv)"]

    lines = []
    if rec["niqe"] is None and rec["brisque"] is None:
        lines.append("no row for this image in the CSV")
    else:
        def fmt(name, val, base):
            if val is None:
                return f"{name} n/a"
            s = f"{name} {val:.2f}"
            if (not is_baseline) and base is not None:
                d = val - base
                arrow = "better" if d < 0 else ("worse" if d > 0 else "same")
                s += f" ({d:+.2f} {arrow})"
            return s

        bn = baseline_rec["niqe"] if baseline_rec else None
        bb = baseline_rec["brisque"] if baseline_rec else None
        lines.append(fmt("NIQE", rec["niqe"], bn) + "   ↓ lower is better")
        lines.append(fmt("BRISQUE", rec["brisque"], bb) + "   ↓ lower is better")

    if is_baseline:
        lines.append("ΔE00: n/a (is the reference)")
    elif rec["de"] is None:
        lines.append("ΔE00: n/a")
    else:
        lines.append(f"ΔE00 vs baseline: {rec['de']:.2f}   "
                     f"↓ lower = less colour shift")
    return lines


# ---------------------------------------------------------------------------
#  figure
# ---------------------------------------------------------------------------

def build_grid(filename: str, args) -> Path | None:
    methods = [BASELINE_LABEL] + discover_methods()
    n_methods_found = len(methods) - 1

    # ---- gather panels ---------------------------------------------------
    panels = []           # (label, rgb|None, note)
    for m in methods:
        src = (BASELINE_DIR if m == BASELINE_LABEL else ENHANCED_DIR / m) / filename
        if not src.exists():
            panels.append((m, None, "image not produced by this method"))
            continue
        try:
            panels.append((m, load_rgb(src), ""))
        except Exception as exc:
            panels.append((m, None, f"unreadable: {type(exc).__name__}"))

    if panels[0][1] is None:
        print(f"ERROR: baseline image missing or unreadable: "
              f"{BASELINE_DIR / filename}", file=sys.stderr)
        print(f"       ({panels[0][2]})", file=sys.stderr)
        return None

    base_rgb = panels[0][1]
    bh, bw = base_rgb.shape[:2]

    # ---- mismatched sizes: resize method output to the baseline ---------
    size_warnings = []
    fixed = []
    for label, img, note in panels:
        if img is not None and img.shape[:2] != (bh, bw):
            size_warnings.append(f"{label} {img.shape[1]}x{img.shape[0]}")
            img = cv2.resize(img, (bw, bh), interpolation=cv2.INTER_AREA)
        fixed.append((label, img, note))
    panels = fixed

    # ---- crop / inset ----------------------------------------------------
    region = None
    if args.crop:
        region = parse_region(args.crop, bw, bh)
    elif args.inset:
        region = parse_region(args.inset, bw, bh)

    crop_mode = bool(args.crop)
    if crop_mode and region:
        x, y, rw, rh = region
        panels = [(l, (im[y:y + rh, x:x + rw] if im is not None else None), n)
                  for l, im, n in panels]

    # ---- metrics + tags --------------------------------------------------
    mrecs = load_metrics_for(filename, methods)
    baseline_rec = mrecs.get(BASELINE_LABEL)
    tags = load_tags(filename)
    scene, tagstr = tag_caption(tags)

    # ---- layout ----------------------------------------------------------
    n = len(panels)
    disp_h, disp_w = panels[0][1].shape[:2] if panels[0][1] is not None else (bh, bw)
    aspect = disp_h / disp_w

    panel_w = args.panel_width
    panel_h = panel_w * aspect

    # Reserve only as much vertical space as the caption actually needs rather
    # than a fixed slab -- a fixed reservation left a band of dead white space
    # under single-panel figures.
    max_lines = 0
    if not args.metrics_off:
        for _lab, _im, _nt in panels:
            _ls = metric_lines(_lab, mrecs.get(_lab, {"csv_found": False}),
                               _lab == BASELINE_LABEL, baseline_rec)
            max_lines = max(max_lines, len(_ls))
    text_h = 0.0 if args.metrics_off else (0.16 + 0.19 * max_lines)

    # Title band, in inches, built from what is actually drawn:
    #   suptitle + (optional subtitle) + room for each panel's own title.
    # Under-reserving here made the subtitle collide with the panel title.
    has_sub = (n_methods_found == 0) or bool(size_warnings)
    SUPTITLE_IN = 0.34
    SUBTITLE_IN = 0.24 if has_sub else 0.0
    PANELTITLE_IN = 0.32
    title_h = SUPTITLE_IN + SUBTITLE_IN + PANELTITLE_IN

    # Locator band: the thumbnail is LOCATOR_W_IN wide plus its small caption.
    LOCATOR_W_IN = 1.45
    locator_h = 0.0
    if crop_mode and args.locator:
        locator_h = LOCATOR_W_IN * (bh / bw) + 0.26

    fig_w = panel_w * n
    fig_h = panel_h + text_h + title_h + locator_h

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=args.dpi)

    # Explicit geometry rather than tight_layout: matplotlib's defaults leave
    # a lot of white space, and this figure is going on a projector.
    left, right = 0.012, 0.988
    bottom = (text_h + locator_h) / fig_h
    top = 1.0 - (title_h / fig_h)
    gap = 0.008
    avail = (right - left) - gap * (n - 1)
    pw = avail / n

    for i, (label, img, note) in enumerate(panels):
        ax = fig.add_axes([left + i * (pw + gap), bottom, pw, top - bottom])
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_linewidth(1.2)
            s.set_edgecolor("#333333")

        if img is None:
            ax.set_facecolor("#f0f0f0")
            ax.text(0.5, 0.5, note or "unavailable", ha="center", va="center",
                    transform=ax.transAxes, fontsize=10, color="#aa0000",
                    wrap=True)
        else:
            ax.imshow(img, interpolation="nearest" if crop_mode else "antialiased")
            # inset magnifier
            if (not crop_mode) and region and args.inset:
                x, y, rw, rh = region
                ax.add_patch(Rectangle((x, y), rw, rh, fill=False,
                                       edgecolor="#ffcc00", linewidth=2.0))
                sub = img[y:y + rh, x:x + rw]
                # inset occupies the lower-right third
                iw = 0.38
                ih = iw * (rh / rw) * (disp_w / disp_h)
                iax = ax.inset_axes([1 - iw - 0.015, 0.015, iw, ih])
                iax.imshow(sub, interpolation="nearest")
                iax.set_xticks([]); iax.set_yticks([])
                for s in iax.spines.values():
                    s.set_edgecolor("#ffcc00"); s.set_linewidth(2.0)

        is_base = (label == BASELINE_LABEL)
        title = ("BASELINE (unenhanced original)" if is_base
                 else f"method: {label}")
        ax.set_title(title, fontsize=12 if is_base else 11,
                     fontweight="bold" if is_base else "semibold",
                     color="#000000" if is_base else "#1a1a1a", pad=6)

        if not args.metrics_off:
            lines = metric_lines(label, mrecs.get(label, {"csv_found": False}),
                                 is_base, baseline_rec)
            ax.text(0.5, -0.012, "\n".join(lines), transform=ax.transAxes,
                    ha="center", va="top", fontsize=9, family="monospace",
                    linespacing=1.5, color="#222222")

    # ---- locator thumbnail for crop mode --------------------------------
    if crop_mode and args.locator and region:
        x, y, rw, rh = region
        lw_in = LOCATOR_W_IN
        lax = fig.add_axes([left, 0.04 / fig_h, lw_in / fig_w,
                            (lw_in * (bh / bw)) / fig_h])
        lax.imshow(base_rgb)
        lax.add_patch(Rectangle((x, y), rw, rh, fill=False,
                                edgecolor="#ffcc00", linewidth=2.0))
        lax.set_xticks([]); lax.set_yticks([])
        lax.set_title("crop location", fontsize=8, pad=3)

    # ---- title / caption -------------------------------------------------
    bits = [f"{filename}"]
    if scene:
        bits.append(scene)
    bits.append(f"tags: {tagstr}")
    if crop_mode and region:
        bits.append(f"crop {region[2]}×{region[3]} at ({region[0]},{region[1]}) "
                    f"— native pixel scale")
    elif region and args.inset:
        bits.append(f"inset {region[2]}×{region[3]} at ({region[0]},{region[1]})")
    title = "   |   ".join(bits)

    # Scale the title down if it would overrun the figure width. A clipped
    # title on a projector is worse than a slightly smaller one. Rough metric:
    # a bold character at size s occupies about 0.62*s/72 inches.
    t_size = 13.0
    while t_size > 7.5 and len(title) * 0.62 * t_size / 72.0 > (fig_w - 0.3):
        t_size -= 0.5
    fig.text(0.5, 1.0 - (SUPTITLE_IN * 0.60) / fig_h, title,
             ha="center", va="center", fontsize=t_size, fontweight="bold")

    sub = []
    if n_methods_found == 0:
        sub.append("No method folders under data/enhanced/ yet — "
                   "baseline only.")
    else:
        sub.append(f"{n_methods_found} method(s) vs baseline.")
    if size_warnings:
        sub.append("Resized to baseline dims: " + "; ".join(size_warnings) + ".")
    if sub:
        subtitle = "  ".join(sub)
        s_size = 9.0
        while s_size > 6.0 and len(subtitle) * 0.52 * s_size / 72.0 > (fig_w - 0.3):
            s_size -= 0.5
        fig.text(0.5, 1.0 - (SUPTITLE_IN + SUBTITLE_IN * 0.55) / fig_h,
                 subtitle, ha="center", va="center", fontsize=s_size,
                 color="#555555", style="italic")

    GRID_DIR.mkdir(parents=True, exist_ok=True)
    out = args.out or (GRID_DIR / f"{Path(filename).stem}_grid.png")
    fig.savefig(out, dpi=args.dpi, facecolor="white",
                bbox_inches=None, pad_inches=0)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
#  self-test
# ---------------------------------------------------------------------------

def self_test(args) -> int:
    import shutil
    import tempfile

    passed, failed = 0, []

    def check(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            print(f"  [ OK ] {name}")
        else:
            failed.append(name)
            print(f"  [FAIL] {name} {detail}")

    print("=" * 72)
    print("  make_grid.py self-test")
    print("=" * 72)

    tmp = Path(tempfile.mkdtemp(prefix="gridtest_"))
    try:
        # ---- CHANNEL ORDER: the disaster test ---------------------------
        print("\n-- channel order (BGR vs RGB) --")
        # Build an image with unambiguous pure colours, written via OpenCV
        # (so it is stored BGR-on-disk the normal way), then check what
        # load_rgb returns and what ends up in the rendered PNG.
        h = w = 60
        img_bgr = np.zeros((h, w * 3, 3), np.uint8)
        img_bgr[:, 0:w] = (0, 0, 255)        # BGR -> pure RED
        img_bgr[:, w:2 * w] = (0, 255, 0)    # pure GREEN
        img_bgr[:, 2 * w:] = (255, 0, 0)     # pure BLUE
        src = tmp / "colours.png"
        cv2.imwrite(str(src), img_bgr)

        rgb = load_rgb(src)
        check("load_rgb: red block reads as (255,0,0)",
              tuple(rgb[h // 2, w // 2]) == (255, 0, 0),
              f"got {tuple(rgb[h//2, w//2])}")
        check("load_rgb: green block reads as (0,255,0)",
              tuple(rgb[h // 2, w + w // 2]) == (0, 255, 0),
              f"got {tuple(rgb[h//2, w + w//2])}")
        check("load_rgb: blue block reads as (0,0,255)",
              tuple(rgb[h // 2, 2 * w + w // 2]) == (0, 0, 255),
              f"got {tuple(rgb[h//2, 2*w + w//2])}")

        # Round-trip through an actual matplotlib figure and read the PNG back.
        figp = tmp / "rt.png"
        f = plt.figure(figsize=(3, 1), dpi=100)
        a = f.add_axes([0, 0, 1, 1]); a.set_xticks([]); a.set_yticks([])
        a.imshow(rgb, interpolation="nearest")
        f.savefig(figp, dpi=100, pad_inches=0); plt.close(f)
        back = cv2.cvtColor(cv2.imread(str(figp), cv2.IMREAD_COLOR),
                            cv2.COLOR_BGR2RGB)
        H, W = back.shape[:2]
        rp = back[H // 2, W // 6]
        gp = back[H // 2, W // 2]
        bp = back[H // 2, 5 * W // 6]

        def dominant(px):
            return int(np.argmax(px.astype(int)))

        check("rendered PNG: left block is RED-dominant", dominant(rp) == 0,
              f"got rgb={tuple(rp)}")
        check("rendered PNG: middle block is GREEN-dominant", dominant(gp) == 1,
              f"got rgb={tuple(gp)}")
        check("rendered PNG: right block is BLUE-dominant", dominant(bp) == 2,
              f"got rgb={tuple(bp)}")
        check("blue did NOT turn orange (the polythene failure)",
              dominant(bp) == 2 and bp[2] > bp[0],
              f"got rgb={tuple(bp)}")

        # ---- name resolution --------------------------------------------
        print("\n-- name resolution --")
        real = sorted(BASELINE_DIR.glob("*.jpg"))
        if real:
            nm = real[0].name
            stem = real[0].stem
            check("resolves bare stem", resolve_name(stem) == nm)
            check("resolves with extension", resolve_name(nm) == nm)
            check("resolves a full path", resolve_name(str(real[0])) == nm)
            check("unknown name returns None",
                  resolve_name("definitely_not_here_xyz") is None)
        else:
            check("baseline folder has images", False, "(no jpgs found)")

        # ---- region parsing ----------------------------------------------
        print("\n-- region parsing --")
        check("parses x,y,w,h", parse_region("10,20,30,40", 100, 100)
              == (10, 20, 30, 40))
        check("clamps oversize region",
              parse_region("90,90,999,999", 100, 100) == (90, 90, 10, 10))
        bad = False
        try:
            parse_region("1,2,3", 100, 100)
        except ValueError:
            bad = True
        check("rejects a 3-number region", bad)
        bad2 = False
        try:
            parse_region("1,2,0,5", 100, 100)
        except ValueError:
            bad2 = True
        check("rejects zero width", bad2)

        # ---- figure actually written and non-trivial ---------------------
        print("\n-- figure output --")
        if real:
            class A:
                pass
            a = A()
            a.crop = None; a.inset = None; a.metrics_off = False
            a.panel_width = DEFAULT_PANEL_W_IN; a.dpi = 120
            a.locator = True; a.out = tmp / "g.png"
            out = build_grid(real[0].name, a)
            check("figure file was created", out is not None and out.exists())
            if out and out.exists():
                sz = out.stat().st_size
                check(f"figure is non-trivial in size ({sz/1024:.0f} KB)",
                      sz > 40_000)
                im = cv2.imread(str(out))
                check("figure has sensible dimensions "
                      f"({im.shape[1]}x{im.shape[0]})",
                      im is not None and im.shape[1] > 500 and im.shape[0] > 400)
                check("figure is not blank",
                      im is not None and im.std() > 10,
                      f"(std {im.std():.1f})" if im is not None else "")

            # crop mode
            a.crop = "100,100,200,150"; a.out = tmp / "gc.png"
            out2 = build_grid(real[0].name, a)
            check("crop mode writes a figure", out2 and out2.exists())
            # inset mode
            a.crop = None; a.inset = "100,100,200,150"; a.out = tmp / "gi.png"
            out3 = build_grid(real[0].name, a)
            check("inset mode writes a figure", out3 and out3.exists())
            # metrics off
            a.inset = None; a.metrics_off = True; a.out = tmp / "gm.png"
            out4 = build_grid(real[0].name, a)
            check("metrics-off writes a figure", out4 and out4.exists())
            if out and out4 and out.exists() and out4.exists():
                check("metrics-off figure is shorter than the annotated one",
                      cv2.imread(str(out4)).shape[0] < cv2.imread(str(out)).shape[0])

        # ---- corrupt / missing handling ----------------------------------
        print("\n-- robustness --")
        corrupt = tmp / "broken.jpg"
        corrupt.write_bytes(b"\xff\xd8\xff\xe0 not a jpeg")
        raised = False
        try:
            load_rgb(corrupt)
        except ValueError:
            raised = True
        check("corrupt file raises a clear ValueError", raised)

        check("metric_lines handles a missing CSV",
              "unavailable" in " ".join(
                  metric_lines("x", {"csv_found": False}, False, None)))
        check("baseline panel says dE is n/a, not 0.00",
              any("n/a (is the reference)" in l for l in metric_lines(
                  "baseline",
                  {"csv_found": True, "niqe": 3.0, "brisque": 20.0, "de": None},
                  True, None)))
        check("method panel shows direction vs baseline",
              any("better" in l for l in metric_lines(
                  "m", {"csv_found": True, "niqe": 2.0, "brisque": 18.0,
                        "de": 1.0}, False,
                  {"niqe": 3.0, "brisque": 20.0})))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 72)
    if failed:
        print(f"  {len(failed)} FAILURE(S): {', '.join(failed)}")
        print("=" * 72)
        return 1
    print(f"  ALL {passed} SELF-TESTS PASSED")
    print("=" * 72)
    return 0


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        prog="make_grid.py",
        description=(
            "Build a side-by-side comparison figure for one image across every "
            "method found under data/enhanced/, annotated with NIQE, BRISQUE "
            "and colour shift. Writes results/grids/<name>_grid.png."
        ),
        epilog=(
            "EXAMPLES\n"
            "  python scripts/make_grid.py img_012\n"
            "  python scripts/make_grid.py img_012.jpg\n"
            "  python scripts/make_grid.py --all-representative\n"
            "  python scripts/make_grid.py img_012 --crop 400,300,320,240\n"
            "  python scripts/make_grid.py img_012 --inset 400,300,320,240\n"
            "  python scripts/make_grid.py img_012 --metrics-off\n"
            "  python scripts/make_grid.py --self-test\n"
            "\n"
            "CROP vs INSET\n"
            "  --inset  keeps the whole frame visible and magnifies one region\n"
            "           in the corner. Best for routine supervisor reports:\n"
            "           context and a hint of texture in one picture.\n"
            "  --crop   shows ONLY the region, at native pixel scale, with a\n"
            "           small locator thumbnail. Best when you need to defend\n"
            "           a claim about texture, halos or noise, where the\n"
            "           inset is too small to settle the argument.\n"
            "\n"
            "ADDING A METHOD\n"
            "  Create data/enhanced/<method>/ with the same filenames. It is\n"
            "  auto-discovered; nothing in this script needs editing.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("image", nargs="?",
                    help="image name: img_012, img_012.jpg, or a path to it")
    ap.add_argument("--all-representative", action="store_true",
                    help="generate grids for the six standing representative "
                         "frames (" + ", ".join(Path(f).stem
                                                for f in REPRESENTATIVE) + ")")
    ap.add_argument("--crop", type=str, metavar="X,Y,W,H",
                    help="show only this region, at native pixel scale")
    ap.add_argument("--inset", type=str, metavar="X,Y,W,H",
                    help="show the full frame with this region magnified in "
                         "the corner")
    ap.add_argument("--no-locator", dest="locator", action="store_false",
                    help="in --crop mode, omit the small locator thumbnail")
    ap.add_argument("--metrics-off", action="store_true",
                    help="clean figure with no numbers, for slides")
    ap.add_argument("--panel-width", type=float, default=DEFAULT_PANEL_W_IN,
                    metavar="IN", help=f"panel width in inches "
                                       f"(default {DEFAULT_PANEL_W_IN})")
    ap.add_argument("--dpi", type=int, default=DEFAULT_DPI,
                    help=f"output DPI (default {DEFAULT_DPI}; "
                         f"{DEFAULT_PANEL_W_IN}in x {DEFAULT_DPI}dpi = "
                         f"{int(DEFAULT_PANEL_W_IN*DEFAULT_DPI)}px per panel)")
    ap.add_argument("--out", type=Path,
                    help="explicit output path (single image only)")
    ap.add_argument("--self-test", action="store_true",
                    help="verify channel order, name resolution, region "
                         "parsing, figure output and error handling")
    args = ap.parse_args()

    if args.self_test:
        return self_test(args)

    if args.crop and args.inset:
        ap.error("use --crop or --inset, not both")

    if not BASELINE_DIR.is_dir():
        print(f"ERROR: baseline folder not found: {BASELINE_DIR}", file=sys.stderr)
        print("       Run scripts/preprocess.py first.", file=sys.stderr)
        return 2

    methods = discover_methods()
    if not methods:
        print(f"NOTE: no method folders found under {ENHANCED_DIR}.")
        print("      Producing a single-panel figure of the unenhanced "
              "baseline.")
        print("      Add data/enhanced/<method>/ and re-run to compare; "
              "methods are auto-discovered.\n")
    else:
        print(f"methods discovered: {', '.join(methods)}\n")

    if args.all_representative:
        if args.out:
            print("ERROR: --out cannot be used with --all-representative",
                  file=sys.stderr)
            return 2
        targets = []
        for f in REPRESENTATIVE:
            r = resolve_name(f)
            if r is None:
                print(f"  WARNING: representative image not found: {f}")
            else:
                targets.append(r)
        if not targets:
            print("ERROR: none of the representative images were found",
                  file=sys.stderr)
            return 2
    else:
        if not args.image:
            ap.error("give an image name, or use --all-representative")
        r = resolve_name(args.image)
        if r is None:
            print(f"ERROR: no image matching {args.image!r} in {BASELINE_DIR}",
                  file=sys.stderr)
            near = [p.stem for p in sorted(BASELINE_DIR.glob('*'))
                    if p.is_file()][:6]
            if near:
                print(f"       Available names look like: "
                      f"{', '.join(near)} ...", file=sys.stderr)
            return 2
        targets = [r]

    written = []
    for t in targets:
        try:
            out = build_grid(t, args)
        except Exception as exc:
            print(f"  FAILED {t}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if out:
            im = cv2.imread(str(out))
            dims = f"{im.shape[1]}x{im.shape[0]}" if im is not None else "?"
            print(f"  wrote {out}  ({dims}, "
                  f"{out.stat().st_size/1024:.0f} KB)")
            written.append(out)

    print(f"\n{len(written)}/{len(targets)} figure(s) written to {GRID_DIR}")
    return 0 if len(written) == len(targets) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(130)
