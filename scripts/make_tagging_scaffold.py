#!/usr/bin/env python3
"""
Generate the Phase 2 tagging scaffold: data/metadata/degradation_tags.csv

Two jobs:

  1. SCENE CLUSTERING. Group the 77 frames into scenes from their capture
     timestamps in capture_metadata.csv. A new scene starts when the gap to
     the previous frame exceeds --gap-seconds (default 30).

     Why this matters: the dataset is burst-heavy (one scene has 20 frames in
     91s, another 23 in 132s). Counting degradations per FRAME would weight
     those scenes 20x against a single-frame scene, so every downstream count
     needs a scene_id to collapse on.

  2. RANDOMISED TAGGING ORDER. Assigns tagging_order as a seeded permutation
     of 1..N and sorts the CSV by it, so the user tags in an order
     uncorrelated with filename, time and scene.

     Why: tagging burst frames consecutively invites anchoring - you tag
     frame 2 the same as frame 1 because you just saw it, not because you
     judged it. Shuffling breaks that. It also means near-duplicate frames
     get judged independently, which turns inconsistency into a visible
     signal instead of a hidden one.

     The seed is FIXED and recorded in the CSV header, the rules document and
     this file, so the ordering is reproducible and defensible.

IMPORTANT: the degradation columns are written EMPTY. They are the user's own
visual judgement and must not be pre-filled or guessed by any script.

Usage:
    python scripts/make_tagging_scaffold.py
    python scripts/make_tagging_scaffold.py --gap-seconds 30 --seed 20261008
    python scripts/make_tagging_scaffold.py --report-only   # print, write nothing

Re-running will NOT clobber tags you have already entered unless you pass
--overwrite; by default it refuses to overwrite a file that has any tag
values in it.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_CSV = PROJECT_ROOT / "data" / "metadata" / "capture_metadata.csv"
TAGS_CSV = PROJECT_ROOT / "data" / "metadata" / "degradation_tags.csv"

# ---------------------------------------------------------------------------
#  FROZEN PARAMETERS - change these only with a note in the rules document.
# ---------------------------------------------------------------------------
RANDOM_SEED = 20261008      # generation date, used as the permutation seed
GAP_SECONDS = 30            # new scene when the inter-frame gap exceeds this
# ---------------------------------------------------------------------------

DEGRADATION_COLUMNS = [
    "haze_dust", "hard_shadow", "glare", "colour_cast", "low_contrast", "none",
]
COLUMNS = (["tagging_order", "filename", "scene_id"]
           + DEGRADATION_COLUMNS + ["notes"])


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        print(f"ERROR: {path} not found. Run scripts/preprocess.py first.",
              file=sys.stderr)
        raise SystemExit(2)
    out = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            fn = (row.get("filename") or "").strip()
            date = (row.get("date") or "").strip()
            time = (row.get("time") or "").strip()
            if not fn:
                continue
            ts = None
            if date and time:
                try:
                    ts = dt.datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    ts = None
            out.append({"filename": fn, "ts": ts})
    if not out:
        print(f"ERROR: no rows read from {path}", file=sys.stderr)
        raise SystemExit(2)

    undated = [r["filename"] for r in out if r["ts"] is None]
    if undated:
        print(f"WARNING: {len(undated)} file(s) have no usable timestamp and will "
              f"each become their own scene: {', '.join(undated[:5])}"
              + (" ..." if len(undated) > 5 else ""))
    return out


def cluster_scenes(records: list[dict], gap_seconds: int) -> list[dict]:
    """Assign scene_id by chronological gap. Undated frames get their own scene."""
    dated = sorted((r for r in records if r["ts"] is not None), key=lambda r: r["ts"])
    undated = [r for r in records if r["ts"] is None]

    scene = 0
    prev = None
    for r in dated:
        if prev is None or (r["ts"] - prev).total_seconds() > gap_seconds:
            scene += 1
        r["scene_num"] = scene
        prev = r["ts"]

    for r in sorted(undated, key=lambda x: x["filename"]):
        scene += 1
        r["scene_num"] = scene

    all_recs = dated + undated
    for r in all_recs:
        r["scene_id"] = f"scene_{r['scene_num']:02d}"
    return all_recs


def scene_report(records: list[dict], gap_seconds: int) -> list[tuple]:
    scenes: dict[str, list[dict]] = {}
    for r in records:
        scenes.setdefault(r["scene_id"], []).append(r)

    print(f"\n=== SCENE CLUSTERING (gap threshold {gap_seconds}s) ===")
    print(f"{len(records)} frames -> {len(scenes)} scenes\n")
    print(f"  {'scene_id':<10} {'n':>3}  {'span(s)':>8}  first frame      time range")
    print(f"  {'-'*10} {'-'*3}  {'-'*8}  {'-'*16} {'-'*40}")
    rows = []
    for sid in sorted(scenes):
        grp = sorted(scenes[sid], key=lambda r: (r["ts"] or dt.datetime.min, r["filename"]))
        ts0, ts1 = grp[0]["ts"], grp[-1]["ts"]
        span = (ts1 - ts0).total_seconds() if (ts0 and ts1) else 0
        tr = f"{ts0} -> {ts1}" if ts0 else "(no timestamp)"
        print(f"  {sid:<10} {len(grp):>3}  {span:>8.0f}  {grp[0]['filename']:<16} {tr}")
        rows.append((sid, len(grp), span))

    sizes = [n for _, n in sorted((s, n) for s, n, _ in rows)]
    print(f"\n  scene sizes: {sizes}")
    print(f"  largest scene is {max(sizes)} frames "
          f"({max(sizes)/len(records)*100:.0f}% of the dataset) - this is why "
          f"per-scene counts matter")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gap-seconds", type=int, default=GAP_SECONDS)
    ap.add_argument("--seed", type=int, default=RANDOM_SEED)
    ap.add_argument("--capture-csv", type=Path, default=CAPTURE_CSV)
    ap.add_argument("--out", type=Path, default=TAGS_CSV)
    ap.add_argument("--report-only", action="store_true",
                    help="print the clustering and exit without writing")
    ap.add_argument("--overwrite", action="store_true",
                    help="overwrite even if the existing file already has tags")
    args = ap.parse_args()

    records = load_records(args.capture_csv)
    records = cluster_scenes(records, args.gap_seconds)
    scene_report(records, args.gap_seconds)

    # --- randomised tagging order, seeded ---------------------------------
    # random.Random is used rather than numpy so the ordering does not depend
    # on the numpy version's RNG internals.
    import random
    rng = random.Random(args.seed)
    ordered = sorted(records, key=lambda r: r["filename"])   # deterministic base
    perm = list(range(1, len(ordered) + 1))
    rng.shuffle(perm)
    for r, p in zip(ordered, perm):
        r["tagging_order"] = p

    rows = sorted(ordered, key=lambda r: r["tagging_order"])

    print(f"\n=== TAGGING ORDER ===")
    print(f"  seeded permutation, seed = {args.seed}")
    print(f"  first 10: {', '.join(r['filename'] for r in rows[:10])}")
    adj = sum(1 for i in range(1, len(rows))
              if rows[i]["scene_id"] == rows[i-1]["scene_id"])
    print(f"  adjacent same-scene pairs after shuffling: {adj}/{len(rows)-1} "
          f"(low is good - it means burst frames are not tagged back to back)")

    if args.report_only:
        print("\n--report-only: nothing written.")
        return 0

    # --- refuse to clobber real work --------------------------------------
    if args.out.exists() and not args.overwrite:
        existing_tags = 0
        try:
            # NOTE: the file we write begins with '#' comment lines, so the
            # comments MUST be stripped before csv.DictReader sees it -
            # otherwise DictReader treats the first comment as the header,
            # every column lookup returns None, and this guard silently
            # finds zero tags and happily destroys the user's work.
            with args.out.open(newline="", encoding="utf-8-sig") as fh:
                data_lines = [l for l in fh if not l.lstrip().startswith("#")]
            for row in csv.DictReader(data_lines):
                for c in DEGRADATION_COLUMNS:
                    if (row.get(c) or "").strip():
                        existing_tags += 1
        except Exception as exc:
            # If we cannot tell, refuse rather than risk overwriting.
            print(f"\nREFUSING TO OVERWRITE: could not read {args.out} to check "
                  f"for existing tags ({exc}). Pass --overwrite to force.",
                  file=sys.stderr)
            return 1
        if existing_tags:
            print(f"\nREFUSING TO OVERWRITE: {args.out} already contains "
                  f"{existing_tags} tag value(s).", file=sys.stderr)
            print("Pass --overwrite if you really want to discard them.",
                  file=sys.stderr)
            return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        fh.write(f"# Phase 2 degradation tagging scaffold\n")
        fh.write(f"# Generated by scripts/make_tagging_scaffold.py\n")
        fh.write(f"# RANDOM_SEED = {args.seed}   (tagging_order is a seeded "
                 f"permutation; reproducible)\n")
        fh.write(f"# SCENE_GAP_SECONDS = {args.gap_seconds}   (new scene when the "
                 f"inter-frame gap exceeds this)\n")
        fh.write(f"# Frames: {len(rows)}   Scenes: "
                 f"{len({r['scene_id'] for r in rows})}\n")
        fh.write(f"#\n")
        fh.write(f"# FILL IN the six degradation columns with yes / no. Work top to\n")
        fh.write(f"# bottom - the rows are already in the randomised tagging order.\n")
        fh.write(f"# Rules: notes/degradation_rules.md (freeze it before you start)\n")
        fh.write(f"# 'none' must be mutually exclusive with the other five.\n")
        fh.write(f"#\n")
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({
                "tagging_order": r["tagging_order"],
                "filename": r["filename"],
                "scene_id": r["scene_id"],
                **{c: "" for c in DEGRADATION_COLUMNS},
                "notes": "",
            })

    print(f"\nwrote {len(rows)} rows -> {args.out}")
    print("degradation columns intentionally EMPTY - they are your judgement to make.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
