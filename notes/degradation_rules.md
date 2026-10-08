# Degradation Tagging Rules — Phase 2

**Status: DRAFT — edit, then freeze.**

Rules frozen on: `08/10/2026` *(write the date here before you tag the first image)*

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

> **Tag `yes` if** the distant part of the scene is visibly washed out toward
> grey or grey-brown, so that distant edges have lower contrast than nearby
> edges in the same image.

The test is the **near-versus-far contrast difference within the one image**,
not overall brightness. An evenly bright image is not hazy. An image with no
visible distance (a close-up of a single bin) cannot show haze — tag `no`.

*Draft note:* consider whether you want to require visible depth in the frame
as a precondition. Suggested: if there is no distinguishable far field, `no`.

### 2. `hard_shadow`

> **Tag `yes` if** there is a distinctly darker region with a recognisably
> sharp edge, and that dark region covers **roughly a tenth or more** of the
> frame.

Two conditions, both required: **sharp boundary** and **≥10% of frame**. Soft
overall dimness is not a hard shadow — that is `low_contrast` or nothing.
A thin shadow line across a corner fails the area test.

Judge 10% by eye: a region about a third of the frame width and a third of its
height is roughly 10%. Do not measure.

### 3. `glare`

> **Tag `yes` if** there are shiny or blown-out patches that read as pure
> white with no detail inside them, whether from direct sun, a specular
> reflection off plastic or metal, or wet ground.

The test is **loss of detail**, not brightness. A bright but still-textured
white surface (a clean wall, a white sack with visible weave) is `no`. If you
can see no texture at all inside the bright patch, it is `yes`.

*Draft note:* decide whether a single small specular dot counts. Suggested:
ignore specks smaller than roughly a fingertip at normal viewing size.

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

| Date | Rule changed | What changed | Images re-tagged |
|---|---|---|---|
|  |  |  |  |

---

## Reference: the tagging run

- Frames to tag: **77**
- Scenes: **9** (clustered on a 30-second capture-gap threshold)
- Tagging order seed: **`RANDOM_SEED = 20261008`**
- Scene sizes: 3, 4, 7, 13, 2, 20, 23, 4, 1

Two scenes account for 43 of the 77 frames. Per-frame counts will therefore
over-represent those two scenes; `scripts/audit_summary.py` reports per-scene
counts alongside per-frame ones for that reason.
