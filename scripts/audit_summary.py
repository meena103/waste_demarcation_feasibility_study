#!/usr/bin/env python3
"""
Phase 2 audit summary: reads the user's completed degradation_tags.csv and
reports counts, co-occurrence, validation errors, tag-vs-proxy disagreements,
and a suggested set of representative images.

Produces, in order:
  1. Per-frame and per-scene counts, side by side (per-frame alone is
     misleading on this dataset - two scenes hold 43 of the 77 frames).
  2. Co-occurrence matrix of degradation pairs.
  3. Validation: `none` alongside another tag, rows with no tag at all,
     and any value that is not exactly yes/no.
  4. Disagreement report: tags that point the opposite way from their proxy
     measurement. This is a rule-sharpening tool, not a correction list.
  5. A SUGGESTED set of 4-6 representative images from distinct scenes.
     A suggestion for the user to confirm or reject - not a decision.

Usage:
    python scripts/audit_summary.py
    python scripts/audit_summary.py --decile 10     # disagreement threshold
    python scripts/audit_summary.py --no-proxies

Exits 0 on a clean audit, 1 if validation problems were found, 2 if the tag
file is unusable (missing or still empty).
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAGS_CSV = PROJECT_ROOT / "data" / "metadata" / "degradation_tags.csv"
PROXIES_CSV = PROJECT_ROOT / "data" / "metadata" / "degradation_proxies.csv"

DEGRADATIONS = ["haze_dust", "hard_shadow", "glare", "colour_cast", "low_contrast"]
ALL_TAGS = DEGRADATIONS + ["none"]

TRUE_VALUES = {"yes", "y", "true", "1"}
FALSE_VALUES = {"no", "n", "false", "0"}
CANONICAL = {"yes", "no"}

# Which proxy supports which tag, and in which direction.
#   (metric, direction) - "high" means a high percentile supports tag=yes,
#   "low" means a low percentile supports tag=yes.
PROXY_FOR_TAG: dict[str, list[tuple[str, str]]] = {
    "haze_dust":     [("dark_channel_mean", "high"), ("transmission_mean", "low")],
    "glare":         [("clipped_highlight_frac", "high"),
                      ("clipped_highlight_frac_255", "high")],
    "hard_shadow":   [("dark_region_largest_frac", "high"),
                      ("clipped_shadow_frac", "high")],
    "low_contrast":  [("luminance_p05_p95_spread", "low"), ("rms_contrast", "low")],
    "colour_cast":   [("greyworld_deviation", "high"), ("lab_chroma_mean", "high")],
}


def read_csv_skip_comments(path: Path) -> list[dict]:
    """Read a CSV whose header may be preceded by '#' comment lines."""
    with path.open(newline="", encoding="utf-8-sig") as fh:
        lines = [l for l in fh if not l.lstrip().startswith("#")]
    if not lines:
        return []
    return list(csv.DictReader(lines))


def normalise(v: str) -> str | None:
    """-> 'yes' | 'no' | None (unrecognised/blank)."""
    s = (v or "").strip().lower()
    if s in TRUE_VALUES:
        return "yes"
    if s in FALSE_VALUES:
        return "no"
    return None


def die(msg: str, hints: list[str] | None = None, code: int = 2) -> None:
    print("\n" + "=" * 74)
    print("  CANNOT PRODUCE AUDIT SUMMARY")
    print("=" * 74)
    print(f"  {msg}")
    if hints:
        print("\n  What to do:")
        for h in hints:
            print(f"    - {h}")
    print()
    raise SystemExit(code)


def bar(n: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return ""
    filled = int(round(n / total * width))
    return "#" * filled + "." * (width - filled)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tags", type=Path, default=TAGS_CSV)
    ap.add_argument("--proxies", type=Path, default=PROXIES_CSV)
    ap.add_argument("--decile", type=float, default=10.0,
                    help="disagreement threshold in percentile points (default 10 "
                         "= top/bottom decile)")
    ap.add_argument("--no-proxies", action="store_true")
    args = ap.parse_args()

    # ------------------------------------------------------------------ load
    if not args.tags.exists():
        die(f"Tag file not found: {args.tags}",
            ["Run:  python scripts/make_tagging_scaffold.py",
             "Then fill in the six degradation columns with yes/no."])

    rows = read_csv_skip_comments(args.tags)
    if not rows:
        die(f"Tag file has no data rows: {args.tags}",
            ["Regenerate it:  python scripts/make_tagging_scaffold.py"])

    missing_cols = [c for c in ["filename", "scene_id"] + ALL_TAGS
                    if c not in rows[0]]
    if missing_cols:
        die(f"Tag file is missing required column(s): {', '.join(missing_cols)}",
            [f"Expected columns: tagging_order, filename, scene_id, "
             f"{', '.join(ALL_TAGS)}, notes",
             "Regenerate with:  python scripts/make_tagging_scaffold.py"])

    # ---- is it actually filled in? -------------------------------------
    filled = sum(1 for r in rows for c in ALL_TAGS if (r.get(c) or "").strip())
    rows_with_any = sum(1 for r in rows
                        if any((r.get(c) or "").strip() for c in ALL_TAGS))
    if filled == 0:
        die("The tag file is still completely empty - there is nothing to summarise.",
            [f"Open {args.tags} and fill the six degradation columns with yes/no.",
             "Work top to bottom; the rows are already in randomised tagging order.",
             "Freeze notes/degradation_rules.md before you start.",
             "Re-run this script when you have tagged at least some rows."])

    total_rows = len(rows)
    if rows_with_any < total_rows:
        print(f"NOTE: {rows_with_any}/{total_rows} rows have any tag filled in. "
              f"This is a PARTIAL audit.\n")

    # ------------------------------------------------- normalise + validate
    bad_values: list[tuple[str, str, str]] = []
    untagged: list[str] = []
    none_conflicts: list[tuple[str, list[str]]] = []

    tags: dict[str, dict[str, str]] = {}
    for r in rows:
        fn = (r.get("filename") or "").strip()
        rec: dict[str, str] = {}
        for c in ALL_TAGS:
            raw = (r.get(c) or "").strip()
            nv = normalise(raw)
            if raw and raw.lower() not in CANONICAL:
                bad_values.append((fn, c, raw))
            if nv is None:
                rec[c] = ""
            else:
                rec[c] = nv
        tags[fn] = rec

        if not any(rec[c] for c in ALL_TAGS):
            untagged.append(fn)
        else:
            positives = [c for c in ALL_TAGS if rec[c] == "yes"]
            if "none" in positives and len(positives) > 1:
                none_conflicts.append((fn, [p for p in positives if p != "none"]))

    scene_of = {(r.get("filename") or "").strip(): (r.get("scene_id") or "").strip()
                for r in rows}
    scenes = sorted({s for s in scene_of.values() if s})

    # =================================================== 1. counts
    print("=" * 74)
    print(" 1. DEGRADATION COUNTS - per frame vs per scene")
    print("=" * 74)
    print(f"  frames: {total_rows}    scenes: {len(scenes)}")
    print()
    print(f"  {'degradation':<16} {'frames':>7} {'%':>6}   {'scenes':>7} {'%':>6}   "
          f"{'per-frame bar':<28}")
    print(f"  {'-'*16} {'-'*7} {'-'*6}   {'-'*7} {'-'*6}   {'-'*28}")

    frame_counts, scene_counts = {}, {}
    for c in ALL_TAGS:
        fc = sum(1 for fn in tags if tags[fn].get(c) == "yes")
        sc_set = {scene_of.get(fn, "") for fn in tags if tags[fn].get(c) == "yes"}
        sc_set.discard("")
        frame_counts[c] = fc
        scene_counts[c] = len(sc_set)
        print(f"  {c:<16} {fc:>7} {fc/total_rows*100:>5.0f}%   "
              f"{len(sc_set):>7} {len(sc_set)/max(1,len(scenes))*100:>5.0f}%   "
              f"{bar(fc, total_rows):<28}")

    print()
    print("  Per-frame percentages are weighted by burst length: the two biggest")
    print("  scenes hold 43 of 77 frames, so a degradation present in just those")
    print("  two scenes would look like ~56% of the dataset. Quote per-scene")
    print("  counts in the thesis, and say that is what you are quoting.")

    print("\n  --- frames per scene (for weighting context) ---")
    per_scene = Counter(scene_of.get(fn, "") for fn in tags)
    for s in scenes:
        print(f"    {s}: {per_scene[s]:>2} frame(s)   {bar(per_scene[s], max(per_scene.values()), 20)}")

    # =================================================== 2. co-occurrence
    print("\n" + "=" * 74)
    print(" 2. CO-OCCURRENCE MATRIX (per frame; diagonal = that tag's own count)")
    print("=" * 74)
    hdr = "  " + " " * 16 + "".join(f"{d[:7]:>9}" for d in DEGRADATIONS)
    print(hdr)
    for a in DEGRADATIONS:
        line = f"  {a:<16}"
        for b in DEGRADATIONS:
            n = sum(1 for fn in tags
                    if tags[fn].get(a) == "yes" and tags[fn].get(b) == "yes")
            line += f"{n:>9}"
        print(line)

    combos = Counter()
    for fn, rec in tags.items():
        pos = tuple(c for c in DEGRADATIONS if rec.get(c) == "yes")
        if pos:
            combos[pos] += 1
    if combos:
        print("\n  --- most common exact combinations ---")
        for combo, n in combos.most_common(8):
            sc = len({scene_of.get(fn, "") for fn, rec in tags.items()
                      if tuple(c for c in DEGRADATIONS if rec.get(c) == "yes") == combo})
            print(f"    {n:>3} frame(s) / {sc} scene(s): {' + '.join(combo)}")

    # =================================================== 3. validation
    print("\n" + "=" * 74)
    print(" 3. VALIDATION")
    print("=" * 74)
    problems = 0

    if none_conflicts:
        problems += len(none_conflicts)
        print(f"\n  [FAIL] {len(none_conflicts)} row(s) have none=yes alongside another tag.")
        print("         'none' must be mutually exclusive with all five others.")
        for fn, others in none_conflicts:
            print(f"           {fn}: none=yes but also {', '.join(others)}")
    else:
        print("\n  [ OK ] no row has none=yes alongside another tag")

    if untagged:
        problems += len(untagged)
        print(f"\n  [FAIL] {len(untagged)} row(s) have no tag at all "
              f"(every column blank or unrecognised):")
        for fn in untagged[:20]:
            print(f"           {fn}")
        if len(untagged) > 20:
            print(f"           ... and {len(untagged)-20} more")
        print("         Every row needs either none=yes or at least one degradation=yes.")
    else:
        print("  [ OK ] every row has at least one tag")

    if bad_values:
        problems += len(bad_values)
        print(f"\n  [FAIL] {len(bad_values)} cell(s) are not exactly 'yes' or 'no':")
        for fn, col, raw in bad_values[:20]:
            print(f"           {fn}  {col} = {raw!r}")
        if len(bad_values) > 20:
            print(f"           ... and {len(bad_values)-20} more")
        print("         Use lowercase 'yes' or 'no' only.")
    else:
        print("  [ OK ] all filled cells are exactly 'yes' or 'no'")

    # all-no rows: not an error, but worth surfacing
    all_no = [fn for fn, rec in tags.items()
              if all(rec.get(c) == "no" for c in ALL_TAGS)]
    if all_no:
        print(f"\n  [NOTE] {len(all_no)} row(s) have every column = no, including none.")
        print("         That is contradictory in spirit: if nothing is wrong, none should")
        print("         be yes. Consider setting none=yes for these.")
        for fn in all_no[:10]:
            print(f"           {fn}")

    # =================================================== 4. disagreements
    print("\n" + "=" * 74)
    print(" 4. TAG vs PROXY DISAGREEMENTS")
    print("=" * 74)

    proxies: dict[str, dict] = {}
    if not args.no_proxies:
        if not args.proxies.exists():
            print(f"\n  proxy file not found ({args.proxies}) - skipping.")
            print("  Generate it with:  python scripts/degradation_proxies.py")
        else:
            for r in read_csv_skip_comments(args.proxies):
                proxies[(r.get("filename") or "").strip()] = r

    if proxies:
        hi = 100.0 - args.decile
        lo = args.decile
        print(f"\n  Flagging where a tag contradicts its proxy's percentile rank")
        print(f"  (top/bottom {args.decile:.0f}%: >= {hi:.0f} or <= {lo:.0f}).")
        print(f"\n  READ THIS AS: 'my rule may be worded loosely here', NOT 'my tag is")
        print(f"  wrong'. The proxies confuse scene content with degradation - grey")
        print(f"  concrete reads as haze, white sacks read as glare. Your eye wins.")

        found = 0
        for tag, metrics in PROXY_FOR_TAG.items():
            lines = []
            for fn, rec in tags.items():
                tv = rec.get(tag)
                if tv not in ("yes", "no"):
                    continue
                px = proxies.get(fn)
                if not px:
                    continue
                for metric, direction in metrics:
                    key = f"{metric}_pct"
                    raw = (px.get(key) or "").strip()
                    if not raw:
                        continue
                    try:
                        pct = float(raw)
                    except ValueError:
                        continue
                    supports_yes = (pct >= hi) if direction == "high" else (pct <= lo)
                    supports_no = (pct <= lo) if direction == "high" else (pct >= hi)
                    if tv == "no" and supports_yes:
                        lines.append(f"      {fn} [{scene_of.get(fn,'?')}]  "
                                     f"{tag}=no  but {metric} pct={pct:.0f} "
                                     f"({direction} = degraded)")
                    elif tv == "yes" and supports_no:
                        lines.append(f"      {fn} [{scene_of.get(fn,'?')}]  "
                                     f"{tag}=yes but {metric} pct={pct:.0f} "
                                     f"(opposite extreme)")
            if lines:
                found += len(lines)
                print(f"\n    --- {tag} ({len(lines)} flag(s)) ---")
                for l in lines[:12]:
                    print(l)
                if len(lines) > 12:
                    print(f"      ... and {len(lines)-12} more")
        if found == 0:
            print("\n    none - tags and proxies broadly agree at this threshold.")
        else:
            print(f"\n  {found} flag(s) total. Clusters within ONE scene usually mean the")
            print("  scene has unusual content, not that you mis-tagged. The same flag")
            print("  recurring across MANY scenes is the signal that a rule needs")
            print("  rewording.")

    # =================================================== 5. representatives
    print("\n" + "=" * 74)
    print(" 5. SUGGESTED REPRESENTATIVE IMAGES (for you to confirm or reject)")
    print("=" * 74)

    chosen: list[tuple[str, str, str]] = []
    used_scenes: set[str] = set()

    # one clean image first
    clean = [fn for fn, rec in tags.items() if rec.get("none") == "yes"]
    if clean:
        pick = sorted(clean)[0]
        chosen.append((pick, scene_of.get(pick, "?"), "clean (none=yes)"))
        used_scenes.add(scene_of.get(pick, "?"))

    # then the most common degradations, each from an unused scene
    ranked = sorted(DEGRADATIONS, key=lambda d: scene_counts.get(d, 0), reverse=True)
    for d in ranked:
        if len(chosen) >= 6:
            break
        cands = [fn for fn, rec in tags.items()
                 if rec.get(d) == "yes" and scene_of.get(fn, "?") not in used_scenes]
        if not cands:
            continue
        # prefer a frame where this is the ONLY degradation - a cleaner exemplar
        solo = [fn for fn in cands
                if sum(1 for c in DEGRADATIONS if tags[fn].get(c) == "yes") == 1]
        pick = sorted(solo or cands)[0]
        only = " (only this degradation)" if pick in solo else " (co-occurring)"
        chosen.append((pick, scene_of.get(pick, "?"), f"{d}{only}"))
        used_scenes.add(scene_of.get(pick, "?"))

    if not chosen:
        print("\n  Cannot suggest a set yet - no tags are filled in far enough.")
    else:
        print(f"\n  {len(chosen)} image(s), all from DISTINCT scenes "
              f"({len(used_scenes)} scene(s) used):\n")
        for fn, sid, why in chosen:
            print(f"    {fn:<14} {sid:<10} {why}")
        if len(chosen) < 4:
            print(f"\n  Only {len(chosen)} found. Tag more rows, or some degradations")
            print("  may not be present in enough distinct scenes.")
        uncovered = [d for d in DEGRADATIONS
                     if not any(d in why for _, _, why in chosen)
                     and scene_counts.get(d, 0) > 0]
        if uncovered:
            print(f"\n  NOT covered by this set (scene collision): {', '.join(uncovered)}")
            print("  Those degradations only occur in scenes already used above.")
        print("\n  This is a SUGGESTION. It optimises for scene diversity and clean")
        print("  single-degradation exemplars, which is not the same as being")
        print("  visually representative. Override it freely.")

    # =================================================== summary
    print("\n" + "=" * 74)
    if problems == 0:
        print(f"  AUDIT CLEAN - {rows_with_any}/{total_rows} rows tagged, "
              f"no validation problems.")
        print("=" * 74)
        return 0
    print(f"  {problems} VALIDATION PROBLEM(S) - fix the [FAIL] items above and re-run.")
    print("=" * 74)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted")
        sys.exit(130)
