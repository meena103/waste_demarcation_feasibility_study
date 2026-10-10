#!/usr/bin/env python3
"""
Analyse the CSVs produced by scripts/evaluate.py.

Answers, from real numbers rather than assumption:

  1. NIQE / BRISQUE distributions across the baseline set (min, median, max,
     quartiles) and the per-scene means.
  2. The SCALE EFFECT: baseline (1024px) vs raw_reference (full resolution),
     quantified per frame and in aggregate. This is the empirical
     justification for fixing the working resolution.
  3. Outlier frames on either metric, with their degradation tags.
  4. Whether the metrics actually SEE our degradations: do frames the tagger
     marked as degraded score worse than frames marked clean? Reported per
     degradation, at frame level and at scene level, with a distribution-free
     significance test. A null result is a real result and is reported as one.
  5. Method comparison, once more than one method has been evaluated.

Usage:
    python scripts/analyse_metrics.py
    python scripts/analyse_metrics.py --baseline baseline --raw raw_reference
    python scripts/analyse_metrics.py --out results/phase3_baseline_analysis.md

Needs only numpy + the CSVs. No torch, no pyiqa.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
METRICS_DIR = PROJECT_ROOT / "results" / "metrics"
TAGS_CSV = PROJECT_ROOT / "data" / "metadata" / "degradation_tags.csv"

DEGRADATIONS = ["haze_dust", "hard_shadow", "glare", "colour_cast", "low_contrast"]
METRICS = ["niqe", "brisque"]


def read_csv_skip_comments(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        lines = [l for l in fh if not l.lstrip().startswith("#")]
    return list(csv.DictReader(lines)) if lines else []


def fnum(row, key):
    v = (row.get(key) or "").strip()
    if not v:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except ValueError:
        return None


def mannwhitney_u_p(x, y):
    """Two-sided Mann-Whitney U with a normal approximation and tie correction.

    Distribution-free, so it makes no normality assumption -- appropriate for
    small, possibly skewed metric samples. Implemented here to avoid adding
    scipy.stats as a hard dependency of the analysis path.

    Returns (U, p). p is approximate and unreliable for very small n; the
    caller must say so.
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        return float("nan"), float("nan")
    allv = np.concatenate([x, y])
    order = allv.argsort()
    ranks = np.empty(len(allv), float)
    ranks[order] = np.arange(1, len(allv) + 1)
    # average ranks for ties
    _, inv, counts = np.unique(allv, return_inverse=True, return_counts=True)
    for i, c in enumerate(counts):
        if c > 1:
            ranks[inv == i] = ranks[inv == i].mean()
    R1 = ranks[:n1].sum()
    U1 = R1 - n1 * (n1 + 1) / 2.0
    U = min(U1, n1 * n2 - U1)
    mu = n1 * n2 / 2.0
    tie_term = sum(c ** 3 - c for c in counts)
    n = n1 + n2
    sigma2 = (n1 * n2 / 12.0) * ((n + 1) - tie_term / (n * (n - 1))) if n > 1 else 0
    if sigma2 <= 0:
        return U, float("nan")
    z = (U - mu) / math.sqrt(sigma2)
    p = 2 * 0.5 * math.erfc(abs(z) / math.sqrt(2))
    return U, min(1.0, p)


def describe(vals):
    a = np.asarray([v for v in vals if v is not None], float)
    if a.size == 0:
        return None
    return {
        "n": int(a.size), "min": float(a.min()), "p25": float(np.percentile(a, 25)),
        "median": float(np.median(a)), "p75": float(np.percentile(a, 75)),
        "max": float(a.max()), "mean": float(a.mean()), "sd": float(a.std(ddof=1)) if a.size > 1 else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metrics-dir", type=Path, default=METRICS_DIR)
    ap.add_argument("--baseline", default="baseline", help="label of the baseline run")
    ap.add_argument("--raw", default="raw_reference", help="label of the full-res run")
    ap.add_argument("--out", type=Path, help="also write the report to this file")
    args = ap.parse_args()

    out_lines = []

    def emit(s=""):
        print(s)
        out_lines.append(s)

    base_csv = args.metrics_dir / f"{args.baseline}.csv"
    if not base_csv.exists():
        print(f"ERROR: baseline CSV not found: {base_csv}", file=sys.stderr)
        print("Run:  python scripts/evaluate.py data/processed/1024 "
              "--label baseline", file=sys.stderr)
        return 2

    base = [r for r in read_csv_skip_comments(base_csv) if r.get("load_ok") == "yes"]
    if not base:
        print(f"ERROR: no usable rows in {base_csv}", file=sys.stderr)
        return 2

    tags = {r["filename"]: r for r in read_csv_skip_comments(TAGS_CSV)}

    emit("# Phase 3 — baseline metric analysis")
    emit()
    emit(f"Source: `{base_csv.name}` — {len(base)} frames")
    emit()

    # ---------------------------------------------------------------- 1
    emit("## 1. Distributions across the baseline set (1024 px)")
    emit()
    emit("| metric | n | min | p25 | median | p75 | max | mean | sd |")
    emit("|---|---|---|---|---|---|---|---|---|")
    for m in METRICS:
        d = describe([fnum(r, m) for r in base])
        if d:
            emit(f"| {m.upper()} | {d['n']} | {d['min']:.4f} | {d['p25']:.4f} | "
                 f"{d['median']:.4f} | {d['p75']:.4f} | {d['max']:.4f} | "
                 f"{d['mean']:.4f} | {d['sd']:.4f} |")
    emit()

    scenes = sorted({r.get("scene_id", "") for r in base if r.get("scene_id")})
    emit("### Per-scene means")
    emit()
    emit("| scene | n | NIQE mean | NIQE sd | BRISQUE mean | BRISQUE sd |")
    emit("|---|---|---|---|---|---|")
    for s in scenes:
        rs = [r for r in base if r.get("scene_id") == s]
        dn = describe([fnum(r, "niqe") for r in rs])
        db = describe([fnum(r, "brisque") for r in rs])
        if dn and db:
            emit(f"| {s} | {dn['n']} | {dn['mean']:.4f} | {dn['sd']:.4f} | "
                 f"{db['mean']:.4f} | {db['sd']:.4f} |")
    emit()
    sn = describe([describe([fnum(r, "niqe") for r in base
                             if r.get("scene_id") == s])["mean"] for s in scenes])
    if sn:
        emit(f"Spread of the 9 scene-level NIQE means: "
             f"{sn['min']:.4f} to {sn['max']:.4f} (sd {sn['sd']:.4f}). "
             f"Between-scene variation of this size is the reason to aggregate "
             f"at scene level before comparing methods.")
    emit()

    # ---------------------------------------------------------------- 2
    emit("## 2. Scale effect — 1024 px vs full resolution")
    emit()
    raw_csv = args.metrics_dir / f"{args.raw}.csv"
    if not raw_csv.exists():
        emit(f"*Not computed — `{raw_csv.name}` not found. Run:*")
        emit()
        emit("```")
        emit("python scripts/evaluate.py data/raw --label raw_reference --no-colour")
        emit("```")
    else:
        raw = {r["filename"]: r for r in read_csv_skip_comments(raw_csv)
               if r.get("load_ok") == "yes"}
        pairs = [(r, raw[r["filename"]]) for r in base if r["filename"] in raw]
        emit(f"Paired on filename: {len(pairs)} frame(s) present in both sets.")
        emit()
        emit("| metric | 1024 px mean | full-res mean | mean diff | "
             "median diff | min diff | max diff | frames where full-res scores worse |")
        emit("|---|---|---|---|---|---|---|---|")
        for m in METRICS:
            b = np.array([fnum(r1, m) for r1, r2 in pairs], float)
            rr = np.array([fnum(r2, m) for r1, r2 in pairs], float)
            diff = rr - b
            worse = int((diff > 0).sum())
            emit(f"| {m.upper()} | {b.mean():.4f} | {rr.mean():.4f} | "
                 f"{diff.mean():+.4f} | {np.median(diff):+.4f} | "
                 f"{diff.min():+.4f} | {diff.max():+.4f} | "
                 f"{worse}/{len(diff)} |")
        emit()
        for m in METRICS:
            b = np.array([fnum(r1, m) for r1, r2 in pairs], float)
            rr = np.array([fnum(r2, m) for r1, r2 in pairs], float)
            rel = 100.0 * (rr - b).mean() / abs(b.mean())
            rho = float(np.corrcoef(b, rr)[0, 1]) if len(b) > 2 else float("nan")
            emit(f"- **{m.upper()}**: full resolution shifts the mean by "
                 f"**{(rr-b).mean():+.4f}** ({rel:+.1f}% of the 1024 px mean). "
                 f"Correlation between the two sets across frames: r = {rho:.3f}.")
        emit()
        emit("> **Interpretation.** These are the *same scenes*, unchanged in "
             "quality — the only difference is pixel dimensions. Any shift here "
             "is pure measurement artefact. It is the empirical justification "
             "for fixing the working resolution at a 1024 px long side and "
             "scoring every method there. A baseline taken from `data/raw` "
             "would be offset from every method's score by roughly this amount, "
             "for no reason connected to enhancement.")
        emit()
        if len(pairs) > 2:
            rho_n = float(np.corrcoef(
                [fnum(a, "niqe") for a, _ in pairs],
                [fnum(b_, "niqe") for _, b_ in pairs])[0, 1])
            emit(f"> Note the rank behaviour too: r = {rho_n:.3f} for NIQE. "
                 f"{'A high correlation means the two resolutions mostly agree on which frames are relatively worse, even though the absolute level shifts.' if rho_n > 0.7 else 'A low correlation means the two resolutions do not even agree on the relative ordering of frames — the scale effect is not a simple offset.'}")
        emit()

    # ---------------------------------------------------------------- 3
    emit("## 3. Outlier frames")
    emit()
    for m in METRICS:
        vals = np.array([fnum(r, m) for r in base], float)
        q1, q3 = np.percentile(vals, [25, 75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        out = [(r, fnum(r, m)) for r in base
               if fnum(r, m) is not None and (fnum(r, m) < lo or fnum(r, m) > hi)]
        out.sort(key=lambda t: -t[1])
        emit(f"### {m.upper()} — Tukey fences [{lo:.4f}, {hi:.4f}]")
        emit()
        if not out:
            emit("No frames outside the fences.")
        else:
            emit("| filename | scene | value | direction | tags |")
            emit("|---|---|---|---|---|")
            for r, v in out:
                t = tags.get(r["filename"], {})
                pos = [d for d in DEGRADATIONS if (t.get(d) or "") == "yes"] or (
                    ["none"] if (t.get("none") or "") == "yes" else ["?"])
                emit(f"| `{r['filename']}` | {r.get('scene_id','')} | {v:.4f} | "
                     f"{'worse' if v > hi else 'better'} | {', '.join(pos)} |")
        emit()

    # ---------------------------------------------------------------- 4
    emit("## 4. Do the metrics see our degradations?")
    emit()
    emit("For each degradation, the metric values of frames tagged `yes` are "
         "compared with frames tagged `no`. **Lower is better for both "
         "metrics**, so if a metric detects a degradation, the `yes` group "
         "should have the HIGHER mean.")
    emit()
    emit("Two levels are reported. Frame level uses all 77 frames but they are "
         "not independent (they cluster in 9 scenes), so its p-values are "
         "optimistic. Scene level aggregates to one value per scene first and "
         "is the defensible test, but has at most 9 points and very little "
         "power. Both are shown so the weakness is visible.")
    emit()

    tagged = [r for r in base if r["filename"] in tags]
    emit(f"Frames with tags: {len(tagged)}/{len(base)}")
    emit()

    for m in METRICS:
        emit(f"### {m.upper()}")
        emit()
        emit("| degradation | n yes | n no | mean(yes) | mean(no) | diff | "
             "direction | U | p (approx) |")
        emit("|---|---|---|---|---|---|---|---|---|")
        for d in DEGRADATIONS:
            ys = [fnum(r, m) for r in tagged if (tags[r["filename"]].get(d) or "") == "yes"]
            ns = [fnum(r, m) for r in tagged if (tags[r["filename"]].get(d) or "") == "no"]
            ys = [v for v in ys if v is not None]
            ns = [v for v in ns if v is not None]
            if not ys or not ns:
                emit(f"| `{d}` | {len(ys)} | {len(ns)} | — | — | — | "
                     f"not present in the dataset | — | — |")
                continue
            diff = float(np.mean(ys) - np.mean(ns))
            U, p = mannwhitney_u_p(ys, ns)
            direction = ("detected (worse when tagged)" if diff > 0
                         else "OPPOSITE (better when tagged)")
            emit(f"| `{d}` | {len(ys)} | {len(ns)} | {np.mean(ys):.4f} | "
                 f"{np.mean(ns):.4f} | {diff:+.4f} | {direction} | {U:.1f} | "
                 f"{p:.4f} |")
        emit()

        # scene level
        emit(f"Scene level ({m.upper()}) — scene mean metric vs fraction of "
             f"frames in that scene carrying the tag:")
        emit()
        emit("| degradation | scenes with | scenes without | mean(with) | "
             "mean(without) | diff | direction |")
        emit("|---|---|---|---|---|---|---|")
        scene_mean = {}
        for s in scenes:
            vs = [fnum(r, m) for r in base if r.get("scene_id") == s]
            vs = [v for v in vs if v is not None]
            if vs:
                scene_mean[s] = float(np.mean(vs))
        for d in DEGRADATIONS:
            with_s = sorted({tags[r["filename"]]["scene_id"] for r in tagged
                             if (tags[r["filename"]].get(d) or "") == "yes"})
            wo_s = [s for s in scenes if s not in with_s]
            a = [scene_mean[s] for s in with_s if s in scene_mean]
            b = [scene_mean[s] for s in wo_s if s in scene_mean]
            if not a or not b:
                emit(f"| `{d}` | {len(a)} | {len(b)} | — | — | — | "
                     f"not testable |")
                continue
            diff = float(np.mean(a) - np.mean(b))
            emit(f"| `{d}` | {len(a)} | {len(b)} | {np.mean(a):.4f} | "
                 f"{np.mean(b):.4f} | {diff:+.4f} | "
                 f"{'detected' if diff > 0 else 'OPPOSITE'} |")
        emit()

    emit("> **How to read a null result here.** If the differences are small "
         "and the directions inconsistent, that is the expected outcome, not a "
         "failure of the experiment. Neither metric was built for shadow, "
         "haze, glare or contrast degradation — see "
         "`notes/niqe_brisque_explained.md` §6.1. A null result is positive "
         "evidence that these metrics cannot stand alone as degradation "
         "measures for this dataset, and strengthens the case for reporting "
         "them only alongside the colour-shift measure and the visual grids.")
    emit()

    # ---------------------------------------------------------------- 5
    others = sorted(p.stem for p in args.metrics_dir.glob("*.csv")
                    if p.stem not in {args.baseline, args.raw, "combined"})
    emit("## 5. Method comparison")
    emit()
    if not others:
        emit("*No enhancement methods evaluated yet — baseline only.*")
    else:
        emit("| method | n | NIQE mean | ΔNIQE vs baseline | BRISQUE mean | "
             "ΔBRISQUE | mean ΔE00 | mean dL* | mean da* | mean db* |")
        emit("|---|---|---|---|---|---|---|---|---|---|")
        bmap = {r["filename"]: r for r in base}
        for lbl in others:
            rows = [r for r in read_csv_skip_comments(args.metrics_dir / f"{lbl}.csv")
                    if r.get("load_ok") == "yes"]
            if not rows:
                continue
            dn = describe([fnum(r, "niqe") for r in rows])
            db_ = describe([fnum(r, "brisque") for r in rows])
            pn = [fnum(r, "niqe") - fnum(bmap[r["filename"]], "niqe")
                  for r in rows if r["filename"] in bmap
                  and fnum(r, "niqe") is not None]
            pb = [fnum(r, "brisque") - fnum(bmap[r["filename"]], "brisque")
                  for r in rows if r["filename"] in bmap
                  and fnum(r, "brisque") is not None]
            de = [fnum(r, "delta_e_mean") for r in rows]
            de = [v for v in de if v is not None]
            dl = [fnum(r, "dL_mean") for r in rows]; dl = [v for v in dl if v is not None]
            da = [fnum(r, "da_mean") for r in rows]; da = [v for v in da if v is not None]
            dbb = [fnum(r, "db_mean") for r in rows]; dbb = [v for v in dbb if v is not None]
            emit(f"| {lbl} | {dn['n']} | {dn['mean']:.4f} | "
                 f"{np.mean(pn):+.4f} | {db_['mean']:.4f} | {np.mean(pb):+.4f} | "
                 f"{np.mean(de) if de else float('nan'):.3f} | "
                 f"{np.mean(dl) if dl else float('nan'):+.3f} | "
                 f"{np.mean(da) if da else float('nan'):+.3f} | "
                 f"{np.mean(dbb) if dbb else float('nan'):+.3f} |")
        emit()
        emit("> Negative ΔNIQE / ΔBRISQUE = the metric improved. A large mean "
             "ΔE00 with improved NIQE is the warning sign described in "
             "`notes/niqe_brisque_explained.md` §6.4: texture statistics got "
             "better while colour moved, and the metrics cannot see the colour "
             "move.")
    emit()

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        print(f"\n[written to {args.out}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
