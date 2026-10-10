# Degradation Tagging Rules — Phase 2

**Status: FROZEN — amended twice post-hoc (wording only). See Amendments.**

Rules frozen on: `08/10/2026` — the wording in force for the whole tagging run.
**Do not change this date.** It is the provenance of the 77 tags.

Last amended on: `09/10/2026` — Amendments 1 (`hard_shadow`) and 2
(`haze_dust`), both wording only. **Zero tag values were changed by either.**
A third candidate amendment (`glare` size threshold) was deliberately declined;
see Decision Note A.

Tagged by: `Vaibhav Meena`

---

## How to use this document

The rules below are **drafts written for you to argue with**. Read each one,
change the wording until it matches what you would actually defend, then write
the freeze date above and stop editing.

The point of freezing is that a rule changed halfway through makes the first
half of the tagging incomparable with the second half. If you find a rule is
wrong *after* freezing, that is fine — but you must note the change, the date,
and **re-tag every image already tagged** under the new wording. Record any
such change in the Amendments section at the bottom.

**Tag in the order given by `tagging_order` in `data/metadata/degradation_tags.csv`,
not in filename order.** That column is a seeded random permutation
(`RANDOM_SEED = 20261008`). The ordering is deliberate: the dataset contains
burst sequences of near-identical frames, and tagging those consecutively
invites you to copy your previous answer rather than judge the image. The
shuffle also means re-tagging a burst frame later acts as an unplanned
consistency check on yourself.

Each of the six columns takes exactly **`yes`** or **`no`**. Not blank, not
`y`/`n`, not `1`/`0`, not `maybe`. `scripts/audit_summary.py` will flag
anything else.

---

## The six categories

Each rule is meant to be a yes/no decision you can make in **two or three
seconds** at normal viewing size. If you find yourself zooming in, measuring,
or deliberating for a minute, the rule is too vague — sharpen the wording
rather than agonising over the image.

### 1. `haze_dust`

> **Tag `yes` if** the frame shows a distinguishable far field **and** that
> distant part of the scene is visibly washed out toward grey or grey-brown,
> so that distant edges have lower contrast than nearby edges in the same
> image. If there is no distinguishable far field — a close-up of a single
> bin, a frame filled by one surface — the test does not apply: tag `no`.

**Amended 2026-10-09** — wording only, no tags changed. See Amendment 2 below
for the original frozen sentence and the evidence. The visible-depth
precondition was already stated in this rule's commentary during the tagging
run; the amendment moves it into the rule sentence where it belongs.

The test is the **near-versus-far contrast difference within the one image**,
not overall brightness. An evenly bright image is not hazy.

### 2. `hard_shadow`

> **Tag `yes` if** the frame contains one or more visually obvious shadow
> regions with a recognisably sharp edge, and their **combined** area is
> roughly a tenth or more of the frame.

**Amended 2026-10-09** — wording only, no tags changed. See Amendment 1 below
for the original frozen sentence and the evidence. This wording describes the
criterion that was actually applied during the 08/10/2026 tagging run.

Three conditions:

1. **Sharp boundary.** The shadow has a recognisable edge where it meets the
   lit area. Soft overall dimness is not a hard shadow — that is
   `low_contrast` or nothing.
2. **Combined area ≥ roughly 10% of the frame.** Add up the shadow regions you
   can actually see as shadow. A shadow broken into two or three patches by an
   object lying across it still counts as one shadow for the area test — do not
   require a single unbroken region.
3. **It must read as cast shadow, not as a dark object.** A black tyre, a dark
   bin or an open doorway is dark subject matter, not a shadow. If you would
   describe it as "a dark thing" rather than "a shadow", tag `no`.

Judge 10% by eye: a region about a third of the frame width and a third of its
height is roughly 10%. Do not measure. A thin shadow line across a corner
fails the area test.

**What does not count toward the area:** general gloom, the darker half of an
unevenly lit frame with no visible edge, or every pixel that happens to be
darker than average. The area is the shadow you can point at and trace the
edge of — not the total of all dark pixels.

### 3. `glare`

> **Tag `yes` if** there are shiny or blown-out patches that read as pure
> white with no detail inside them, whether from direct sun, a specular
> reflection off plastic or metal, or wet ground.

The test is **loss of detail**, not brightness. A bright but still-textured
white surface (a clean wall, a white sack with visible weave) is `no`. If you
can see no texture at all inside the bright patch, it is `yes`.

**No minimum patch size is specified. This is deliberate — see the note below.
Not an oversight.**

#### Note (2026-10-09): why no size threshold was set

The draft of this rule carried an unresolved note asking whether a single small
specular dot should count, and suggesting a fingertip-sized minimum. **That
threshold was never set, and it is deliberately being left unset.**

During the 08/10/2026 tagging run no fixed size threshold was in force.
`glare` was judged purely on **visible loss of detail** — whether a bright
patch reads as pure white with no texture inside it — with the patch-size
question settled by eye, case by case, without a stated cut-off.

Setting a number now would not describe the criterion that was applied; it
would **newly decide borderline cases** that were decided some other way at
tagging time. That is the one move that would compromise what makes these tags
citable: they were produced blind, in seeded random order, before any proxy
measurement was consulted. A retrospective threshold would convert a
documented judgement into an undocumented re-tag.

**State this as a limitation, because it is one.** Specifically:

- `glare` is the only degradation whose proxy disagreements run in **both
  directions** (10 frames tagged `no` with top-decile clipped highlights, and
  `img_063.jpg` tagged `yes` at percentile 9). Two-directional disagreement is
  the signature of a criterion that was not fixed in advance. The other four
  categories disagree one-directionally, consistent with a stable rule meeting
  a confounded proxy.
- The cost of the weaker wording is low: `glare` is **Priority 2** in the
  method plan, affecting 4 of 9 scenes and 10 frames, and the achievable gain
  is bounded anyway — median clipped-highlight area across the set is **0.11%
  of pixels**.
- If a reviewer presses on this, the remedy is a **documented re-tag**, not a
  retrospective amendment: fix a threshold, then re-tag the 10 `glare = yes`
  frames plus the near-threshold `no` frames (`img_001`, `img_002`, `img_013`,
  `img_015`, `img_034`, `img_035`, `img_046`, `img_061`, `img_064`,
  `img_067`) — roughly 20 frames — and record it in the Amendments table as a
  re-tag with its own date.

### 4. `colour_cast`

> **Tag `yes` if** the whole image is tinted toward one colour — yellow,
> blue, brown or green — such that something you know to be neutral grey or
> white does not look neutral.

Must be **global**. One brown pile of soil in an otherwise neutral frame is
the subject, not a cast. Ask: does the *entire* frame, including things that
should be grey, lean one way?

### 5. `low_contrast`

> **Tag `yes` if** the image is flat overall: there are **no true blacks
> anywhere and no true whites anywhere**. The darkest thing in the frame is a
> mid-grey and the brightest thing is also a mid-grey.

Both halves required. A frame with deep shadows *and* a washed-out sky is not
low contrast — it is high contrast with other problems. The question is
whether the whole tonal range is squeezed into the middle.

Note this will often co-occur with `haze_dust`. That is expected and fine;
they are different observations (one is about near-versus-far, the other about
the global tonal range). Tag both if both are true.

### 6. `none`

> **Tag `yes` only if** all five of the above are `no` — the image has no
> visible problem that would justify enhancement.

**`none` is mutually exclusive with every other category.** If `none = yes`,
all five others must be `no`, and vice versa. This is a hard validation rule,
not a guideline; `scripts/audit_summary.py` will flag any row that breaks it.

A useful phrasing of the test: *would I bother enhancing this image at all?*
If no, `none = yes`.

---

## Handling ambiguity

The single rule: **tag `yes` only if you would defend that call to an
examiner.**

If you are genuinely unsure after a few seconds, tag `no` and write why in the
`notes` column. This biases the dataset toward under-reporting degradation,
which is the safer direction — it means any enhancement benefit you later
measure is not inflated by generously-tagged marginal cases. An examiner can
challenge an over-tagged dataset far more easily than an under-tagged one.

Specific habits worth adopting:

- **Do not compare against the other images.** Judge each frame on its own.
  Relative judgement drifts as you go and makes the first and last images
  incomparable.
- **Do not look at the proxy measurements while tagging.**
  `data/metadata/degradation_proxies.csv` exists to be compared with your tags
  *afterwards*. Reading it first contaminates the thing it is meant to check.
- **Do not go back and revise earlier rows** once you have moved on, except in
  a single deliberate review pass at the end. If you do a review pass, note
  that you did.
- **Near-duplicate burst frames may legitimately get different tags** if a
  degradation is marginal in one and clear in another. Do not force
  consistency; the disagreement is information.
- **Fatigue is real.** 77 images is enough to drift. Take a break every ~25
  images and note roughly where your breaks fell.

---

## What these tags are, and are not

These tags are the **ground truth** for Phase 2. The objective proxies in
`degradation_proxies.csv` are *not* ground truth and cannot replace them —
they measure pixel statistics that correlate loosely with what you perceive,
and each has failure modes that would mislabel these images (documented in
`scripts/degradation_proxies.py`). Where a tag and a proxy disagree, the
default assumption is that the proxy is wrong and your eye is right. The
disagreement report exists to help you find rules that are *worded* badly, not
to overrule your judgement.

---

## Amendments after freezing

Record any rule change here, with the date and what you re-tagged.

| # | Date | Rule changed | What changed | Images re-tagged |
|---|---|---|---|---|
| 1 | 2026-10-09 | `hard_shadow` | Area test re-worded: "that dark region covers ≥10%" → "one or more visually obvious sharp-edged shadow regions whose **combined** area is ≥~10%". Added an explicit exclusion for dark *objects* and for total-dark-pixel readings. | **None — zero tag values changed.** Wording only. |
| 2 | 2026-10-09 | `haze_dust` | Visible-depth precondition promoted from the rule's commentary into the rule sentence itself. No change of meaning. | **None — zero tag values changed.** Wording only. |
| — | 2026-10-09 | `glare` | **No change made.** Decision recorded not to set a size threshold retrospectively. See the note under rule 3 and Decision Note A below. | None. |

### Amendment 1 — `hard_shadow` area test

**Original frozen wording (08/10/2026), verbatim — this is the sentence that
was in force while all 77 frames were tagged:**

> **Tag `yes` if** there is a distinctly darker region with a recognisably
> sharp edge, and that dark region covers **roughly a tenth or more** of the
> frame.
>
> Two conditions, both required: **sharp boundary** and **≥10% of frame**. Soft
> overall dimness is not a hard shadow — that is `low_contrast` or nothing.
> A thin shadow line across a corner fails the area test.
>
> Judge 10% by eye: a region about a third of the frame width and a third of its
> height is roughly 10%. Do not measure.

**Why it was amended.** The phrase "that dark region covers roughly a tenth or
more of the frame" is ambiguous between two readings, and measurement against
the 77 processed frames shows that *neither literal reading reproduces the
tagging*:

| Reading of "that dark region covers ≥10% of frame" | Frames qualifying |
|---|---|
| One **contiguous** dark region ≥10% of the frame | **0 / 77** — the largest single connected dark region found anywhere in the set is **5.08%** (`img_066.jpg`) |
| **Total** dark area ≥10% of the frame | **74 / 77** — total dark area ranges **9.7% – 29.0%** across the set |
| **As actually tagged** | **29 / 77** |

Source: `dark_region_largest_frac` and `dark_region_frac` in
`data/metadata/degradation_proxies.csv`, produced by
`scripts/degradation_proxies.py`.

The applied criterion therefore sat demonstrably *between* the two literal
readings — it was neither one unbroken region nor every relatively-dark pixel,
but the summed area of the shadow regions visible as shadow. The amended
wording states that criterion explicitly.

**The tags were not changed, and that is the correct direction of fix.** The
defect was in the sentence, not in the judgements. Two pieces of evidence that
the judgements were applied consistently:

1. `hard_shadow` and `low_contrast` **never co-occur** — 0 of 77 frames carry
   both. This is exactly what the rule set predicts: a frame with a real
   sharp-edged shadow contains true blacks, and the `low_contrast` rule
   requires that there be none anywhere. An inconsistently-applied shadow rule
   would not produce a clean zero here.
2. Of the 29 `hard_shadow` frames, 24 carry that tag and nothing else, and the
   tag is distributed across 5 of the 9 scenes rather than concentrated in one
   burst — so it is not an artifact of one run of near-duplicate frames.

Re-tagging under the amended wording would therefore change nothing except to
re-derive the same 29 frames, while destroying the property that makes the
original tags citable: that they were produced blind, in a seeded random order,
before any proxy measurement was consulted. Amending the wording preserves
that; re-tagging would not.

**Caveat on the evidence, stated for completeness.** The proxy columns quoted
above are not a direct measure of "shadow". `dark_region_frac` thresholds at
0.45 × each image's own mean luminance, which is not the eye's notion of
shadow, and `dark_region_largest_frac` uses connected components, so a shadow
interrupted by a bright object splits into several small pieces and
under-reports. Both limitations are documented in
`data/metadata/degradation_proxies_README.md`. The measurements are used here
only to establish that the two *literal* readings of the original sentence
bracket the tagging — 0 on one side, 74 on the other, 29 in the middle — which
does not depend on the proxy being a good shadow detector.

---

### Amendment 2 — `haze_dust` visible-depth precondition

**Original frozen wording (08/10/2026), verbatim — this is the sentence that
was in force while all 77 frames were tagged:**

> **Tag `yes` if** the distant part of the scene is visibly washed out toward
> grey or grey-brown, so that distant edges have lower contrast than nearby
> edges in the same image.
>
> The test is the **near-versus-far contrast difference within the one image**,
> not overall brightness. An evenly bright image is not hazy. An image with no
> visible distance (a close-up of a single bin) cannot show haze — tag `no`.
>
> *Draft note:* consider whether you want to require visible depth in the frame
> as a precondition. Suggested: if there is no distinguishable far field, `no`.

**Why it was amended.** The visible-depth precondition was already stated —
"An image with no visible distance … cannot show haze — tag `no`" — but it sat
in the explanatory paragraph rather than in the rule sentence, with an
unresolved draft note beside it suggesting the same thing. A reader checking
the rule sentence alone would not have seen it. The amendment moves it into the
sentence and drops the now-redundant draft note. **The meaning is unchanged.**

**Evidence that the precondition was applied during tagging.** All 16
`haze_dust` proxy disagreements run in **one direction only**: frames tagged
`haze_dust = no` whose dark-channel / transmission measures sit in the top
decile, spread across scenes 01, 04, 06, 07 and 08. There are **zero**
disagreements in the other direction — every one of the 5 frames tagged
`haze_dust = yes` is corroborated by its proxy.

That pattern is what a correctly-applied precondition produces: close-range
frames with pale dust or bare concrete score high on the dark-channel prior
(a documented failure mode of that metric) but were correctly tagged `no`
because they show no far field. A precondition applied inconsistently would
produce disagreements in both directions, as `glare` does.

**Zero tag values were changed by this amendment.** As with Amendment 1, the
defect was in where the sentence put the precondition, not in the judgements.

### Decision Note A — `glare` size threshold deliberately left unset

**Decision (2026-10-09): do not set a minimum specular-patch size.** No rule
text was changed. The full reasoning is recorded under rule 3 above; in short:
no threshold was in force at tagging time, `glare` was judged on visible loss
of detail, and setting a number retrospectively would newly decide borderline
cases rather than describe the criterion applied — compromising the provenance
of the blind, seeded-order tagging.

This is recorded as a **deliberate methodological choice, and as a limitation**.
`glare` is the only category with two-directional proxy disagreement, which is
the honest signature of an unfixed criterion. A documented re-tag of roughly 20
frames remains available if a reviewer presses; see rule 3 for the frame list.

---

## Reference: the tagging run

- Frames to tag: **77**
- Scenes: **9** (clustered on a 30-second capture-gap threshold)
- Tagging order seed: **`RANDOM_SEED = 20261008`**
- Scene sizes: 3, 4, 7, 13, 2, 20, 23, 4, 1

Two scenes account for 43 of the 77 frames. Per-frame counts will therefore
over-represent those two scenes; `scripts/audit_summary.py` reports per-scene
counts alongside per-frame ones for that reason.
