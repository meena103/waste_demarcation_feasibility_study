# Phase 2 — Degradation Audit

**Dataset:** 77 frames, 9 scenes, `data/processed/1024/`
**Tagged by:** Vaibhav Meena
**Rules frozen:** 08/10/2026 (`notes/degradation_rules.md`); Amendments 1
(`hard_shadow`) and 2 (`haze_dust`) on 2026-10-09, both wording only, 0 tags
changed. A third candidate amendment (`glare` size threshold) was deliberately
declined — see §6.
**Tagging order seed:** `RANDOM_SEED = 20261008`
**Audit generated:** 2026-10-09, from `scripts/audit_summary.py`
**Revision:** rev 3 — adds the within-scene consistency analysis (§7) and the
`glare` methodological limitation (§6)
**Inputs:** `data/metadata/degradation_tags.csv`, `data/metadata/degradation_proxies.csv`

---

## 1. Validation status — **CLEAN**

Tag file is complete and valid: 462/462 cells filled, every value exactly `yes`
or `no`, no blanks, no stray values. No formatting normalisation was required
or performed at any point. All 29 `none = yes` rows are internally consistent,
every row carries at least one tag, and no row has all six columns `no`.

`scripts/audit_summary.py` reports **0 validation problems**.

### Changes made by the tagger since rev 1

Two rows were revised by the tagger after the first audit flagged them. Both
are the tagger's own judgement; no tag was altered by anyone else.

| filename | scene | change | effect |
|---|---|---|---|
| `img_017.jpg` | scene_04 | `none`: `yes` → `no` (keeping `hard_shadow = yes`) | Resolves the only mutual-exclusivity conflict. `none` 30 → 29 frames. |
| `img_024.jpg` | scene_05 | `low_contrast`: `yes` → `no` | Resolves the only two-directional tag/proxy disagreement. `low_contrast` 14 → 13 frames, and 5 → 4 scenes, since scene_05 now has no `low_contrast` frame. |

Both changes reduce the dataset's internal tension, and the `low_contrast`
change is consistent with the frozen rule: `img_024.jpg` has a 97th-percentile
clipped-shadow fraction, so it contains true blacks, which under the rule
("no true blacks anywhere") points to `no`.

The counts throughout this document reflect the revised tags.

---

## 2. Counts — per scene first

**Per-scene counts are the defensible figures** and are what should be quoted.
Scenes 06 and 07 together hold 43 of 77 frames (56%), so per-frame percentages
largely report how long those two bursts ran, not how common a degradation is.

| degradation | **scenes** | **% of 9 scenes** | frames | % of 77 frames |
|---|---|---|---|---|
| `hard_shadow` | **5** | **56%** | 29 | 38% |
| `low_contrast` | **4** | **44%** | 13 | 17% |
| `glare` | **4** | **44%** | 10 | 13% |
| `haze_dust` | **3** | **33%** | 5 | 6% |
| `colour_cast` | **0** | **0%** | 0 | 0% |
| `none` | **5** | **56%** | 29 | 38% |

`hard_shadow` is now the only degradation reaching five of nine scenes.
`low_contrast` and `glare` tie on scene coverage at four of nine, but
`low_contrast` affects more frames (13 vs 10) and more of them in isolation
(10 vs 4).

### Scene-by-scene detail

| scene | frames | haze_dust | hard_shadow | glare | colour_cast | low_contrast | none |
|---|---|---|---|---|---|---|---|
| scene_01 | 3 | – | 3/3 | – | – | – | 0 |
| scene_02 | 4 | – | – | – | – | – | **4/4** |
| scene_03 | 7 | – | 5/7 | 3/7 | – | 1/7 | 0 |
| scene_04 | 13 | 3/13 | 4/13 | 2/13 | – | 3/13 | 3 |
| scene_05 | 2 | 1/2 | – | 2/2 | – | – | 0 |
| scene_06 | 20 | – | 5/20 | – | – | 8/20 | 7 |
| scene_07 | 23 | 1/23 | 12/23 | 3/23 | – | – | 11 |
| scene_08 | 4 | – | – | – | – | – | **4/4** |
| scene_09 | 1 | – | – | – | – | 1/1 | 0 |

Scenes where each degradation appears at all:

- `hard_shadow` — scene_01, 03, 04, 06, 07
- `low_contrast` — scene_03, 04, 06, 09
- `glare` — scene_03, 04, 05, 07
- `haze_dust` — scene_04, 05, 07
- `colour_cast` — **none**
- `none` (clean) — scene_02, 04, 06, 07, 08

Two scenes (02 and 08) are entirely clean; two (01 and 05) have no clean frame
at all.

### Co-occurrence matrix (per frame; diagonal = that tag's own count)

| | haze_dust | hard_shadow | glare | colour_cast | low_contrast |
|---|---|---|---|---|---|
| **haze_dust** | **5** | 1 | 1 | 0 | 2 |
| **hard_shadow** | 1 | **29** | 4 | 0 | 0 |
| **glare** | 1 | 4 | **10** | 0 | 1 |
| **colour_cast** | 0 | 0 | 0 | **0** | 0 |
| **low_contrast** | 2 | 0 | 1 | 0 | **13** |

All exact combinations (complete, not truncated):

| frames | scenes | combination |
|---|---|---|
| 29 | – | *no degradation* (`none = yes`) |
| 24 | 5 | `hard_shadow` alone |
| 10 | 3 | `low_contrast` alone |
| 4 | 3 | `glare` alone |
| 4 | 2 | `hard_shadow` + `glare` |
| 2 | 1 | `haze_dust` + `low_contrast` |
| 1 | 1 | `haze_dust` + `hard_shadow` |
| 1 | 1 | `glare` + `low_contrast` |
| 1 | 1 | `haze_dust` + `glare` |
| 1 | 1 | `haze_dust` alone |

Two structural observations. First, degradations here are **mostly isolated** —
39 of the 48 degraded frames carry exactly one tag (24 `hard_shadow`,
10 `low_contrast`, 4 `glare`, 1 `haze_dust`), so this is not a dataset where
everything is wrong at once. Second, `hard_shadow` and `low_contrast`
**never co-occur** (0 frames), which is exactly what the rules predict:
a frame with a deep shadow has true blacks, and the `low_contrast` rule
requires none. The tagging is internally consistent with the rule wording —
and the tagger's revision of `img_024.jpg` moved it further in that direction,
not away from it.

---

## 3. Tag vs proxy disagreements

69 flags at the top/bottom-decile threshold (was 71 at rev 1; the tagger's
revision of `img_024.jpg` cleared two). Framing, per the frozen rules:
**where a tag and a proxy conflict, the proxy is presumed wrong.** These flags
are read as evidence about *rule wording*, not about the tagging.

### 3.1 `colour_cast` — 16 flags, all one direction — **proxy confound**

All 16 are `colour_cast = no` while `greyworld_deviation` or `lab_chroma_mean`
sits in the top decile; spread over scenes 04, 05, 06, 07. No flags the other way.

This is the textbook failure of the grey-world assumption, documented in advance
in `scripts/degradation_proxies.py`. Both metrics measure *how far the scene is
from average-grey*, which in a waste-site photograph is dominated by real
subject colour — soil, plastic, vegetation. They cannot distinguish "the
illuminant tinted everything" from "there is a lot of brown in shot".

The tags are further supported by capture metadata: all 77 frames are one
device (OnePlus 9 Pro 5G), one lens, auto white balance, 74 of 77 in the
afternoon. A consistent, correctly-balanced illuminant across the set is the
expected outcome, and `colour_cast = 0` records that. **No rule change needed.**

### 3.2 `haze_dust` — 16 flags, all one direction — **proxy confound (wording gap now closed)**

> **Resolved 2026-10-09.** Amendment 2 in `notes/degradation_rules.md` promoted
> the visible-depth precondition from the rule's commentary into the rule
> sentence. Meaning unchanged, **0 tag values changed**; the original sentence
> is preserved verbatim in that amendment entry.

All 16 are `haze_dust = no` with a high dark channel / low transmission, across
scenes 01, 04, 06, 07, 08. No flags the other way — every frame tagged `yes`
also measures hazy, so the positive tags are unanimously corroborated.

The dark channel prior rises for any bright, low-saturation surface: dry pale
dust underfoot, bare concrete, overcast sky. Those are the normal ground cover
here, so a high dark channel is expected on clear frames.

**Wording gap, now closed.** The rule as frozen carried an unresolved draft
note — *"consider whether you want to require visible depth in the frame as a
precondition. Suggested: if there is no distinguishable far field, `no`."* The
rule body already said "An image with no visible distance … cannot show haze —
tag `no`", so the precondition was in force and evidently applied; it simply
sat in commentary rather than in the rule sentence. Amendment 2 moves it into
the sentence, which makes the 16 flags fully explicable (close-ups with pale
ground, no far field, correctly `no`) and pre-empts an examiner asking why
high-haze-scoring frames are untagged.

The one-directional disagreement pattern is itself the evidence that the
precondition was applied consistently: a precondition applied erratically would
produce flags in both directions, as `glare` does (§3.3, §6).

### 3.3 `glare` — 11 flags — **proxy confound, plus the specular-dot threshold**

Ten are `glare = no` with clipped highlights in the top decile (scenes 02, 04,
06, 07); one is the reverse.

The clipped-highlight fraction cannot separate blown-out glare from
legitimately white subject matter — and the frozen rule explicitly makes that
distinction ("a white sack with visible weave is `no`"; the test is *loss of
detail*, not brightness). So the metric is measuring the thing the rule
deliberately excludes. Absolute values are tiny throughout: median clipped
fraction is 0.11% of pixels, so these "top decile" frames differ from the rest
by fractions of a percent of the image.

**Wording gap — deliberately left open.** The glare rule kept its unresolved
draft note on whether a single small specular dot counts. With clipped areas
this small, that threshold does most of the work separating `yes` from `no`.
A decision was taken on 2026-10-09 **not** to set it retrospectively; the
reasoning and the resulting limitation are recorded in full at **§6**.

| flag | reading |
|---|---|
| `img_063.jpg` [scene_07] `glare=yes`, clipped pct=9 | Proxy confound. Glare judged on visible loss of detail; this frame also has the set's highest `greyworld_deviation` and `lab_chroma_mean` (both pct=100), so a bright specular patch can read as glare without reaching the clipping threshold the proxy counts. |

### 3.4 `low_contrast` — 13 flags, now all one direction — **definitional mismatch**

All 13 are `low_contrast = no` with a bottom-decile spread (scenes 01, 04, 05,
06, 07). **No flags in the other direction.**

> At rev 1 there were 15 flags, two of them on `img_024.jpg`
> (`low_contrast = yes` against spread pct 98 / rms pct 99) — the only
> strongly two-directional disagreement in the audit. The tagger has since
> revised that frame to `low_contrast = no`, which clears both flags and leaves
> every remaining `low_contrast` tag uncontradicted by its proxy. The revision
> is consistent with the frozen rule: the frame's 97th-percentile clipped-shadow
> fraction means it contains true blacks, and the rule requires none anywhere.

The 13 remaining flags are a **definitional mismatch rather than a confound**.
The frozen rule
requires *both* "no true blacks anywhere" *and* "no true whites anywhere".
`luminance_p05_p95_spread` is deliberately outlier-robust: it discards the
darkest and brightest 5% of pixels, so a frame with a small genuinely-black
patch still scores as low spread — while the rule, which asks whether *anything*
in the frame is truly black, correctly says `no`. The proxy is answering a
narrower question than the rule asks. Six of the 13 fall in scene_07, which has
zero `low_contrast` tags and the most `hard_shadow` — consistent with frames
that have real deep shadows, hence true blacks, hence not low-contrast.

No individual flag in this category now requires attention. **Closed.**

### 3.5 `hard_shadow` — 13 flags — **the real rule-wording finding (now amended)**

> **Resolved 2026-10-09.** This finding prompted Amendment 1 in
> `notes/degradation_rules.md`: the `hard_shadow` area test was re-worded to
> state the criterion actually applied. **No tag values were changed.** The
> original frozen sentence is preserved verbatim in that amendment entry. The
> analysis below is retained as the evidence that motivated it, and still
> describes the wording in force during the tagging run.

Eight are `hard_shadow = no` with high dark-region/clipped-shadow measures;
five are `hard_shadow = yes` with a bottom-decile largest-dark-region.

The rule as frozen on 08/10/2026 retained the draft's unresolved 10%
ambiguity. It read: *"there is a distinctly darker region with a recognisably
sharp edge, and that dark region covers roughly a tenth or more of the frame"*,
with "Two conditions, both required: sharp boundary and ≥10% of frame."

Measured against the images, neither literal reading of "that dark region"
reproduces 29 tags:

| reading of "that dark region covers ≥10%" | images qualifying |
|---|---|
| one **contiguous** dark region ≥10% of frame | **0 / 77** (largest found anywhere: 5.08%, `img_066.jpg`) |
| **total** dark area ≥10% of frame | **74 / 77** (range 9.7%–29.0%) |
| as actually tagged | 29 / 77 |

So the operative criterion sits between the two — presumably the summed area of
the visually obvious sharp-edged shadow, which is neither one connected
component nor all dark pixels. The five `yes`-but-low-proxy flags
(`img_005`, `img_053`, `img_054`, `img_058`, `img_075`) are exactly what that
gap predicts: shadows real and sharp-edged, but fragmented or thinner than one
contiguous tenth of the frame.

Two caveats before reading this as a problem with the tagging. The proxy's
"dark" is a *relative* threshold (below 0.45 × that image's mean luminance),
which is not the same as the eye's "shadow"; and its connected-component step
is fragile — a shadow interrupted by a bright object splits into several small
components and under-reports, which is documented as a known failure mode.

**Action taken:** this was the one item an examiner was most likely to probe,
because the frozen wording implied a measurement that no image in the set
satisfies. The *wording* was fixed, not the tags — Amendment 1 (2026-10-09)
re-words the area test as the combined area of visually obvious sharp-edged
shadow regions, adds an explicit exclusion for dark *objects*, and rules out
the total-dark-pixel reading. The original sentence is quoted verbatim in the
amendment with its 08/10/2026 freeze date, so the provenance of the 77 tags
remains inspectable.

Fixing the sentence rather than re-tagging is the right direction because the
tags are self-consistent: `hard_shadow` never co-occurs with `low_contrast`
(0/77), exactly as the rule set requires, and 24 of the 29 tagged frames carry
that tag alone, spread over 5 of 9 scenes rather than concentrated in one
burst. Re-tagging would re-derive the same frames while destroying the property
that makes these tags citable — that they were produced blind, in seeded random
order, before any proxy was consulted.

### 3.6 Summary of disagreement readings

| degradation | flags | direction | more likely explanation |
|---|---|---|---|
| `colour_cast` | 16 | all one way | **Proxy confound** — grey-world assumption fails on real scene colour |
| `haze_dust` | 16 | all one way | **Proxy confound** (pale ground raises dark channel). Depth precondition moved into the rule sentence by **Amendment 2**; 0 tags changed. |
| `glare` | 11 | 10 / 1 | **Proxy confound** — metric measures brightness, rule measures detail loss. Specular-dot threshold **deliberately left unset**; see §6. |
| `low_contrast` | 13 | all one way | **Definitional mismatch** — proxy is outlier-robust, rule is not. Two-directional flag on `img_024` cleared by the tagger's rev-2 revision. |
| `hard_shadow` | 13 | 8 / 5 | **Loosely-worded rule** — "≥10% of frame" was unresolved and unsatisfiable as literally written. **Resolved by Amendment 1 (2026-10-09), wording only, no tags changed.** |

---

## 4. Representative images

Six frames, all from **distinct scenes**, covering every degradation present in
the dataset plus one clean reference. Each is a single-degradation exemplar
(exactly one tag), so it isolates the effect under test.

| # | filename | scene | role | why this frame |
|---|---|---|---|---|
| 1 | `img_001.jpg` | scene_02 | **clean reference** | scene_02 is 4/4 clean — an uncontested baseline, not a marginal call |
| 2 | `img_073.jpg` | scene_01 | **hard_shadow** (purest) | scene_01 is 3/3 `hard_shadow` and nothing else; no confounding tags anywhere in the scene |
| 3 | `img_066.jpg` | scene_07 | **hard_shadow** (largest scene) | scene_07 is 23 frames (30% of the set) and holds 12 of the 29 `hard_shadow` tags; this frame has the set's largest contiguous dark region (5.08%) |
| 4 | `img_027.jpg` | scene_06 | **low_contrast** | flattest `low_contrast` frame in scene_06 (p05–p95 spread 0.659, lowest in that scene), which holds 8 of the 14 `low_contrast` tags |
| 5 | `img_004.jpg` | scene_03 | **glare** | the only single-degradation `glare` frame in scene_03 |
| 6 | `img_012.jpg` | scene_04 | **haze_dust** | the **only** frame in the whole set tagged `haze_dust` with no other degradation |

`hard_shadow` gets two slots because it is the most prevalent degradation
(5/9 scenes, 29 frames) and because scene_01 and scene_07 are different in
kind — a small evening scene versus the largest afternoon burst.

**`colour_cast` has no representative, by construction:** zero frames are
tagged with it. Do not substitute a high-`greyworld_deviation` frame as a
stand-in — that would import the proxy confound discussed in §3.1 as if it
were ground truth.

Alternate if a different mix is preferred: `img_072.jpg` (scene_09) is a
single-frame scene tagged `low_contrast` only, and would add a ninth-scene
exemplar at the cost of dropping one `hard_shadow` slot.

*This set is a suggestion optimised for scene diversity and single-degradation
clarity. Confirm or substitute as judgement dictates.*

---

## 5. Method-choice justification

> Across the nine scenes of the captured set, degradation is dominated by
> tonal and illumination faults rather than by atmospheric or colorimetric
> ones. Hard-edged shadow is the single most widespread condition, present in
> five of nine scenes and 29 of 77 frames, and is the only degradation to
> exceed half the scenes; globally flat low contrast follows at four of nine
> scenes and 13 frames, and glare also at four of nine scenes but only 10
> frames and just four of those in isolation. Haze or airborne dust is
> confined to three of nine scenes and five frames, while colour cast is
> entirely absent — no frame in the set exhibits it, which is consistent with
> the whole corpus having been captured on a single device under auto white
> balance in afternoon daylight. Enhancement effort is therefore prioritised
> toward spatially-adaptive tone and illumination correction, since that is
> the family that addresses the two leading conditions at once: CLAHE as the
> classical baseline, and Retinex-family decomposition together with learned
> exposure correction as the stronger comparators, because a sharp-edged
> shadow occupying a fraction of the frame requires local rather than global
> tonal adjustment, and because the measured absence of co-occurrence between
> hard shadow and low contrast (0 of 77 frames) indicates the two arise from
> genuinely different capture situations and should be evaluated separately
> rather than as one combined "poor tonality" case. Highlight recovery and
> local tone mapping are retained as a secondary priority on the strength of
> glare's four-scene spread, though with two caveats that bound the expected
> gain: clipped-highlight area is small throughout the set (median 0.11% of
> pixels), and four of the ten glare frames co-occur with hard shadow, so part
> of any measured improvement would be attributable to the tonal correction
> already applied under the first priority. Dehazing — whether
> dark-channel-prior or learned — is explicitly deprioritised to a
> confirmatory role: with haze tagged in only three scenes and five frames,
> and only one of those frames carrying haze alone, the set cannot support a
> defensible comparison between dehazing methods, and the objective
> dark-channel proxy is independently unreliable here because the pale dust
> and bare concrete that dominate the ground plane raise it on visibly clear
> frames. White-balance correction, whether grey-world or learned, is excluded
> from the evaluation altogether: with zero tagged instances there is no
> degradation for it to correct, and applying it would risk removing the
> genuine subject colour of soil and plastic that the grey-world statistic
> mistakes for a cast.

### Priority list

- **Priority 1 — spatially-adaptive tone / illumination correction.**
  CLAHE (classical baseline); Retinex-family decomposition and learned exposure
  correction (comparators). Targets `hard_shadow` (**5/9 scenes, 29 frames** —
  the widest-spread degradation) and `low_contrast` (**4/9 scenes, 13 frames**).
  Because the two never co-occur (0/77), together they account for **42 of the
  48 degraded frames** — 88% of everything tagged as degraded. Evaluate the two
  conditions separately.
- **Priority 2 — highlight recovery / local tone mapping.**
  Targets `glare` (**4/9 scenes, 10 frames**). Equal scene coverage to
  `low_contrast` but fewer frames and only 4 in isolation. Worth testing;
  expect a bounded effect — clipped-highlight area is a fraction of a percent
  of pixels throughout, and 4 of the 10 frames also carry `hard_shadow`, so
  attribution will be partly confounded with Priority 1.
- **Deprioritised — dehazing (DCP or learned).**
  `haze_dust` in only **3/9 scenes, 5 frames**, 3 of them in one scene and only
  1 carrying haze alone. Report as a qualitative observation on those frames;
  do not stage a method comparison the sample cannot support.
- **Excluded — white balance (grey-world or learned).**
  `colour_cast` = **0/77**. No target degradation. The proxy's 16 flags are a
  documented grey-world confound on real scene colour, not evidence of cast.

**Sampling caveat to carry into Phase 3.** The 77 frames are not 77 independent
observations: two scenes supply 43 of them. Any Phase 3 statistic computed per
frame will understate variance. Aggregate within scene first, then across the
nine scenes, and state that this is what was done.

Note the refinement from §7: the frames within a burst are **not** near-
duplicates — measured frame-to-frame similarity never exceeds 0.851, and frames
tagged the same are no more alike than frames tagged differently. The
correlation within a scene therefore runs through shared site, lighting and
time of day rather than through repeated framing, so the effective sample is
somewhat larger than nine. Scene-level aggregation remains the defensible
choice; the caveat is about correlation, not duplication.

---

## 6. Methodological limitation — `glare` has no size threshold

**This is a limitation, stated as one.** It is also a deliberate choice, not an
oversight.

The `glare` rule as frozen on 08/10/2026 carried an unresolved draft note
asking whether a single small specular dot should count, suggesting a
fingertip-sized minimum. **No threshold was ever set, and none was in force
during the tagging run.** `glare` was judged purely on visible loss of detail —
whether a bright patch reads as pure white with no texture inside it — with
patch size settled by eye, case by case, without a stated cut-off.

A decision was taken on 2026-10-09 **not to set one retrospectively.** Setting
a number now would not describe the criterion that was applied; it would newly
decide borderline cases that were decided some other way at tagging time. That
would compromise the one property that makes these tags citable — that they
were produced blind, in seeded random order, before any proxy was consulted.
A retrospective threshold converts a documented judgement into an undocumented
re-tag.

**The honest residual.** `glare` is the only degradation whose proxy
disagreements run in **both directions**: 10 frames tagged `no` with
top-decile clipped highlights, and `img_063.jpg` tagged `yes` at percentile 9.
Two-directional disagreement is the signature of a criterion that was not fixed
in advance. The other four categories disagree one-directionally, which is what
a stable rule meeting a confounded proxy looks like. This asymmetry should not
be explained away: it is real, and it is specific to `glare`.

**Why the cost is low.** `glare` is **Priority 2** in the method plan (§5),
affecting 4 of 9 scenes and 10 frames, only 4 of them in isolation. The
achievable gain is bounded independently of the tagging: median
clipped-highlight area across the set is **0.11% of pixels**.

**The remedy, if a reviewer presses.** Not a retrospective amendment, but a
**documented re-tag**: fix a threshold, re-tag the 10 `glare = yes` frames plus
the near-threshold `no` frames (`img_001`, `img_002`, `img_013`, `img_015`,
`img_034`, `img_035`, `img_046`, `img_061`, `img_064`, `img_067`) — roughly 20
frames — and record it in the Amendments table as a re-tag with its own date,
distinct from the wording-only amendments.

---

## 7. Within-scene consistency

Checked across all nine scenes after the rev-2 tag revisions, because
near-identical frames tagged differently is the one pattern that would be
genuinely diagnostic of inconsistent rule application.

**Method.** For every chronologically adjacent pair of frames within a scene,
frame-to-frame similarity was computed as `1 − mean|Δ|` on 96×96 greyscale
thumbnails. This measures *how alike two pictures are*, not whether either is
degraded — it is not a degradation proxy and carries none of the confounds
discussed in §3.

**Result: the burst frames are not near-duplicates.**

| | similarity |
|---|---|
| Adjacent pairs tagged **the same** (n=34) | min 0.707, median 0.769, max 0.851 |
| Adjacent pairs tagged **differently** (n=34) | 0.701 – 0.783 |
| Pairs ≥0.95 similar with differing tags | **0** |
| Pairs ≥0.97 similar with differing tags | **0** |

The two distributions **overlap completely**. No pair anywhere in the set
exceeds 0.851 similarity, and same-tagged pairs are not measurably more alike
than differently-tagged ones.

**What this means.** The working assumption from the scene-clustering stage —
that the bursts are sequences of near-identical frames — is **wrong**. The
photographer was moving between shots, so each frame in a burst is a genuinely
different view of the same site. Consequently, two frames seconds apart
carrying different tags is fully explained by their being different pictures,
and **no within-scene tag difference requires re-examination**.

This also softens, but does not remove, the Phase 3 sampling caveat: frames
within a scene are correlated through shared site, lighting and time of day,
not through duplicate framing. Scene-level aggregation remains the right
approach, but the effective sample is somewhat larger than 9 independent
observations would suggest.

---

## 8. Images warranting a second look

Screened against the tagger's own frozen rules, **not** against proxy
disagreement — the proxy is presumed wrong on this imagery (§3), so a
disagreement alone is not grounds for re-examination. Inclusion required a
reason internal to the rules: a frame appearing to fail an explicit
precondition, a tag combination that is incoherent under the rule texts, or a
within-scene inconsistency the rules cannot explain.

**One frame qualifies.**

### `img_003.jpg` — scene_03 — currently `glare = yes`, `low_contrast = yes`

This is the only frame in the set carrying both tags, and under the frozen rule
texts the two assert opposite things about the same image:

- `glare` requires "blown-out patches that read as **pure white** with no
  detail inside them" — i.e. the frame contains true whites.
- `low_contrast` requires "**no true blacks anywhere and no true whites
  anywhere** … the brightest thing in the frame is also a mid-grey" — i.e. the
  frame contains no true whites.

The rules cannot both hold. By comparison, `hard_shadow` + `low_contrast` —
the same kind of contradiction — occurs **0 times** in 77 frames, so this
appears to be an isolated case rather than a systematic reading of the rules.

**Question for the tagger, not a recommendation:** in this frame, does the
bright white polystyrene sheeting read as blown-out with no detail (supporting
`glare`, which would make `low_contrast` inapplicable), or as bright but still
textured (supporting `low_contrast`, which would make `glare` inapplicable)?
Note also that the frame contains a black umbrella, which the `low_contrast`
rule's "no true blacks anywhere" condition would need to accommodate.

### Assessed and cleared — no re-examination needed

**`img_063.jpg`** — scene_07, `glare = yes` at clipped-highlight percentile 9.
Flagged here only because it is the frame where the unstated size threshold
(§6) is load-bearing. **Assessed against the rule, it holds:** the frozen rule
explicitly admits "a specular reflection off plastic or metal", and the frame
is dappled sunlight through trees falling on glossy plastic sheeting and a bin
lid, producing many small blown-out patches rather than one large one. The low
percentile reflects each patch being individually small, not an absence of
glare. The tag is defensible under the rule as written; the only open question
is the one already recorded at §6, and it is a documentation gap, not a doubt
about this frame.

**All other frames.** No within-scene inconsistency (§7), no other incoherent
tag combination, and no frame tagged `haze_dust = yes` that lacks a far field.
The remaining 69 proxy disagreements are confounds or definitional mismatches
already accounted for in §3 and are **not** grounds for revisiting any tag.

---

## Appendix — provenance

| artifact | source |
|---|---|
| Tags | `data/metadata/degradation_tags.csv` (77 rows, 462/462 cells, tagged under the rules as frozen 08/10/2026) |
| Rules | `notes/degradation_rules.md` — frozen 08/10/2026; Amendment 1 on 2026-10-09 re-worded `hard_shadow` (wording only, 0 tags changed, original sentence preserved verbatim) |
| Proxies | `data/metadata/degradation_proxies.csv` (77 × 49; 23 metrics + 23 percentile ranks) |
| Proxy documentation | `data/metadata/degradation_proxies_README.md` |
| Scene clustering | 30s capture-gap threshold; stable for any threshold 23–40s |
| Tagging order | seeded permutation, `RANDOM_SEED = 20261008` |
| Scripts | `scripts/make_tagging_scaffold.py`, `scripts/degradation_proxies.py`, `scripts/audit_summary.py` |

Outstanding items requiring the tagger's decision:

1. ~~`img_017.jpg` — resolve `none` + `hard_shadow` conflict.~~ **Closed
   2026-10-09** by the tagger: `none` → `no`, `hard_shadow = yes` retained.
2. ~~`hard_shadow` rule — define whether "≥10% of frame" is total shadow area or
   one contiguous region.~~ **Closed 2026-10-09 by Amendment 1** (wording only,
   0 tags changed).
3. ~~`haze_dust` rule — promote the visible-depth precondition from commentary
   into the rule sentence.~~ **Closed 2026-10-09 by Amendment 2** (wording
   only, 0 tags changed).
4. ~~`glare` rule — state the minimum specular-patch size.~~ **Closed
   2026-10-09 by decision: deliberately left unset.** Recorded as a
   methodological limitation at §6 and as Decision Note A in the rules
   document. A documented re-tag of ~20 frames remains available if required.
6. `img_003.jpg` — `glare` + `low_contrast` are contradictory under the frozen
   rule texts. **Open — needs the tagger's reading** (§8).
5. ~~`img_024.jpg` / `img_023.jpg` (scene_05) — optional confirming look at the
   pair.~~ **Closed 2026-10-09** by the tagger: `img_024.jpg` `low_contrast`
   → `no`. Both frames in scene_05 now agree with their proxies.
