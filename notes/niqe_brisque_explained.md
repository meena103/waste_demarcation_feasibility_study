# NIQE and BRISQUE — what they measure, and what they cannot

**Phase 3 reference document.** Written 2026-10-09.

Every equation and factual claim below was checked against the primary sources
listed in §8, and the implementation details against the source of the version
we have pinned (`pyiqa` 0.1.16). Where something could not be verified, that is
said explicitly rather than glossed over — see §9.

**Reading order.** Each subsection states the idea in plain language first and
gives the equation second, with every symbol defined underneath. If the
notation is not helping, the sentence before it carries the full argument; the
equations are there so the thesis can be precise, not because the reasoning
depends on them.

---

## 1. What "no-reference" means, and why it is the only option here

Objective image-quality metrics come in three families, distinguished by how
much of an undistorted original they are allowed to see.

| Family | What it needs | Example |
|---|---|---|
| **Full-reference (FR)** | The complete, undistorted original image, pixel for pixel | PSNR, SSIM |
| **Reduced-reference (RR)** | A few summary statistics of the original, not the original itself | Various |
| **No-reference (NR)**, also called **blind** | Only the image being judged | NIQE, BRISQUE |

A full-reference metric answers "how far is this image from the original?" It
is the easiest question to answer well, because the answer is a comparison. The
LIVE IQA database that both of our metrics were validated on is built exactly
this way: 29 pristine reference photographs, each deliberately degraded in
known ways to produce 779 distorted versions, so that every distorted image has
a clean twin.

**Our dataset has no clean twins, and cannot have any.** There is no
undegraded original of a waste site. The hard shadow in `img_073.jpg` was cast
by the actual sun at 17:32 on 7 August; the haze in `img_012.jpg` was actual
airborne dust. Nobody holds a version of those frames without the shadow or the
dust, and no amount of care at capture time could have produced one — the
degradation is a property of the scene and the moment, not of a processing step
applied afterwards that could have been skipped.

This rules out full-reference metrics entirely. PSNR and SSIM are not merely
inconvenient here; they are undefined, because the term they would compare
against does not exist. Reduced-reference metrics fail for the same reason —
summary statistics of a clean original still require a clean original.

So the only available family is no-reference. An NR metric looks at a single
image and asks, in effect, *"does this look like the kind of image a camera
normally produces when nothing has gone wrong?"* That question can be asked of
one image in isolation, which is why it works for us. The price is that the
question is much weaker than the FR question, and §6 is about how much weaker.

> **One consequence to keep in mind throughout.** Because there is no reference,
> an NR metric cannot distinguish "information was restored" from "the image
> was made to look more like the statistics of a clean image". Those are
> different things, and only the first is what enhancement is supposed to
> achieve. This is the root of nearly every caveat in §6.

---

## 2. The shared foundation — natural scene statistics

NIQE and BRISQUE are built on the same observation, and share most of their
machinery. Understanding that shared part means most of both metrics is
already understood.

### 2.1 The core idea, in words

Photographs of the real world are not arbitrary arrays of numbers. They have
regularities that hold across subject matter, camera and photographer — a
picture of a waste site and a picture of a mountain share statistical structure
that neither shares with random noise or a computer-generated pattern.

The particular regularity both metrics use was reported by Ruderman in 1994. If
you take a photograph and, at every pixel, **subtract the local average
brightness and divide by the local contrast**, the resulting numbers follow a
distribution very close to a standard bell curve (a Gaussian with mean 0 and
variance 1) — and they do so remarkably consistently across natural images.

That normalisation does two useful things. Subtracting the local mean removes
the overall brightness, so a bright scene and a dark scene become comparable.
Dividing by the local contrast removes the local "strength" of the texture, so
a bold-textured region and a faint one become comparable. What is left is the
*shape* of local structure, stripped of brightness and contrast.

The payoff is the next sentence, and it is the hinge the whole method turns on:

> **Distortions break this regularity, and different distortions break it in
> different, characteristic ways.** Blur makes the distribution more sharply
> peaked and heavy-tailed; additive noise makes it flatter; compression leaves
> its own signature. So the *shape* of the distribution becomes a fingerprint
> of what went wrong, without ever needing to see the undistorted image.

The coefficients produced by this normalisation are called **MSCN
coefficients** — Mean-Subtracted, Contrast-Normalised.

### 2.2 The equation

For an image `I`, the MSCN coefficient at pixel position `(i, j)` is:

```
                I(i, j) − μ(i, j)
    Î(i, j)  =  ─────────────────
                  σ(i, j) + C
```
*(BRISQUE Eq. 1; NIQE Eq. 1, where C is written directly as 1)*

Where:

- **`I(i, j)`** — the brightness (luminance) of the pixel at row `i`, column `j`.
  Both metrics work on a single greyscale channel, not on colour. **Remember
  this; §6.4 depends on it.**
- **`Î(i, j)`** — ("I-hat") the MSCN coefficient: the output, one number per pixel.
- **`μ(i, j)`** — the *local mean*: the weighted average brightness in a small
  neighbourhood around `(i, j)`.
- **`σ(i, j)`** — the *local standard deviation*: how much the brightness varies
  in that same neighbourhood. This is the local contrast.
- **`C = 1`** — a small constant added to stop the fraction exploding where the
  local contrast is near zero. Without it, a perfectly flat region — a blank
  patch of sky, or a featureless slab of concrete — would divide by something
  near zero and produce meaningless huge values.
- **`i ∈ 1…M`, `j ∈ 1…N`** — the pixel indices; `M` and `N` are image height and
  width.

The local mean and local standard deviation are themselves weighted sums over
the neighbourhood:

```
    μ(i, j)  =  Σ   Σ   w(k,l) · I(i+k, j+l)
               k=−K l=−L
```
*(BRISQUE Eq. 2 / NIQE Eq. 2)*

```
                  ┌──────────────────────────────────────────┐
    σ(i, j)  =   √│ Σ   Σ   w(k,l) · [I(i+k, j+l) − μ(i,j)]² │
                  └k=−K l=−L                                 ┘
```
*(BRISQUE Eq. 3 / NIQE Eq. 3)*

Where:

- **`w(k,l)`** — the weights of a **2-D circularly-symmetric Gaussian window**,
  sampled out to 3 standard deviations and rescaled so all the weights sum to 1.
  "Circularly symmetric" means it treats all directions alike; "Gaussian" means
  pixels nearer the centre count for more than pixels at the edge of the window.
- **`K = L = 3`** — the window half-width, in both papers' implementations. So
  the window runs from −3 to +3 in each direction: a **7×7 pixel window**.

`pyiqa` 0.1.16 uses exactly this: `kernel_size = 7`, `kernel_sigma = 7/6`.

**What the window size means in practice.** 7×7 is small — about 0.7% of the
width of our 1024 px frames. So "local" really is local: these statistics
describe texture at the scale of a few pixels, not the scale of objects. A
metric built on them is sensitive to grain, edge sharpness and fine texture,
and comparatively insensitive to large-scale properties like *where the shadow
falls* or *how the scene is lit*. §6.1 returns to why that matters for us.

---

## 3. BRISQUE

**B**lind/**R**eferenceless **I**mage **S**patial **QU**ality **E**valuator.
Mittal, Moorthy & Bovik, 2012.

### 3.1 What it does, in words

BRISQUE takes the MSCN coefficients from §2, measures the shape of their
distribution with a handful of numbers, and then **asks a machine-learning
model, trained on human opinion scores, what quality rating a human would have
given an image with that shape**. It is a learned predictor of human judgement.

It measures the shape in two ways.

**First, the distribution of the MSCN coefficients themselves.** For a clean
image this is near-Gaussian; distortion changes its peakedness and tail weight.
BRISQUE fits a *generalised Gaussian distribution* — a bell curve with an extra
dial controlling how pointy or flat it is — and records the two dial settings.

**Second, the relationship between neighbouring coefficients.** Even after
normalisation, adjacent MSCN coefficients are not independent: their *signs*
follow a regular pattern in clean images, and distortion disturbs it. BRISQUE
captures this by multiplying each coefficient by its neighbour in four
directions and examining the distribution of those products. These product
distributions are lopsided, so a plain symmetric bell curve will not fit them;
an *asymmetric* generalised Gaussian is used, with separate spread parameters
for the left and right halves.

### 3.2 Fitting the MSCN coefficients — the GGD

The **generalised Gaussian distribution (GGD)** with zero mean:

```
                       α            ⎡    ⎛ |x| ⎞^α ⎤
    f(x; α, σ²)  =  ─────────  exp  ⎢ − ⎜ ─── ⎟    ⎥
                    2β Γ(1/α)       ⎣    ⎝  β  ⎠    ⎦
```
*(BRISQUE Eq. 4)*

with

```
              ┌────────┐
    β  =  σ  √│ Γ(1/α) │          (BRISQUE Eq. 5)
              │ ─────── │
              └ Γ(3/α) ┘
```

Where:

- **`x`** — a value a coefficient might take.
- **`f(x; α, σ²)`** — how likely that value is; the curve being fitted.
- **`α`** (alpha) — the **shape parameter**: the "pointiness" dial. `α = 2` gives
  exactly the normal bell curve; `α = 1` gives a sharply peaked, heavy-tailed
  Laplacian shape; large `α` gives a flat-topped box-like shape. **This is the
  single number that most directly encodes "how un-natural is this image".**
- **`σ²`** (sigma squared) — the **variance**: how spread out the distribution is.
- **`β`** (beta) — a scale factor derived from `α` and `σ²` by Eq. 5; not an
  independent quantity, just bookkeeping that makes the formula come out right.
- **`Γ(·)`** — the **gamma function**, `Γ(a) = ∫₀^∞ t^(a−1) e^(−t) dt` for `a > 0`
  (BRISQUE Eq. 6). A standard mathematical function that extends the factorial
  to non-integers. It appears only to normalise the curve so its total area is
  1; no intuition about it is needed.

A zero-mean form is used because MSCN distributions are symmetric about zero.
The two parameters are estimated by moment matching (Sharifi & Leon-Garcia,
1995).

**This yields 2 features: `α` and `σ²`.**

### 3.3 Fitting the neighbour products — the AGGD

Four pairwise products are formed, one per direction — horizontal, vertical,
main diagonal, secondary diagonal — each at a distance of one pixel:

```
    H (i, j)  =  Î(i, j) · Î(i,   j+1)      horizontal          (Eq. 7)
    V (i, j)  =  Î(i, j) · Î(i+1, j  )      vertical            (Eq. 8)
    D1(i, j)  =  Î(i, j) · Î(i+1, j+1)      main diagonal       (Eq. 9)
    D2(i, j)  =  Î(i, j) · Î(i+1, j−1)      secondary diagonal  (Eq. 10)
```

Each of these four sets of products is fitted with an **asymmetric generalised
Gaussian distribution (AGGD)**, which is the GGD with the left and right sides
allowed to differ:

```
                      ⎧      ν             ⎡   ⎛ −x ⎞^ν ⎤
                      ⎪ ───────────── exp  ⎢ −⎜ ─── ⎟   ⎥     for x < 0
                      ⎪ (βl+βr)Γ(1/ν)      ⎣   ⎝ βl ⎠   ⎦
    f(x; ν, σl², σr²) = ⎨
                      ⎪      ν             ⎡   ⎛  x ⎞^ν ⎤
                      ⎪ ───────────── exp  ⎢ −⎜ ─── ⎟   ⎥     for x ≥ 0
                      ⎩ (βl+βr)Γ(1/ν)      ⎣   ⎝ βr ⎠   ⎦
```
*(BRISQUE Eq. 12)*

with

```
               ┌────────┐                      ┌────────┐
    βl = σl · √│ Γ(1/ν) │        βr = σr · √│ Γ(1/ν) │
               │ ─────── │                     │ ─────── │
               └ Γ(3/ν) ┘                      └ Γ(3/ν) ┘
```
*(Eq. 13, Eq. 14)*

Where:

- **`ν`** (nu) — the shape parameter, the same "pointiness" dial as `α` above.
- **`σl²`, `σr²`** — the **left** and **right** scale parameters: how far the
  distribution spreads below zero and above zero respectively. If they are
  equal the AGGD collapses back to an ordinary GGD; the gap between them is the
  skew.
- **`βl`, `βr`** — derived scale factors, as `β` was before.

A fourth quantity, the **mean** of the fitted distribution, is also recorded:

```
                       Γ(2/ν)
    η  =  (βr − βl) · ────────
                       Γ(1/ν)
```
*(BRISQUE Eq. 15)*

- **`η`** (eta) — where the centre of mass of the distribution sits. Zero if the
  fit is symmetric; non-zero to the extent that it leans one way.

**So each of the four directions yields 4 numbers — `η`, `ν`, `σl²`, `σr²` —
giving 16 features.**

### 3.4 Counting to 36

| Features | Source |
|---|---|
| `f1 – f2` | Shape and variance, from the GGD fit to the MSCN coefficients |
| `f3 – f6` | Shape, mean, left variance, right variance — AGGD fit to **H** products |
| `f7 – f10` | …AGGD fit to **V** products |
| `f11 – f14` | …AGGD fit to **D1** products |
| `f15 – f18` | …AGGD fit to **D2** products |

That is **18 features at one scale**. Everything is then recomputed on a
half-resolution copy of the image (low-pass filtered and downsampled by 2),
because distortions affect structure differently at different scales. The
papers note that going beyond two scales added little.

**2 scales × 18 features = 36 features per image.**

### 3.5 From features to a score — and why "opinion-aware" matters

The 36 features are fed to a **support vector regressor (SVR)** with a **radial
basis function (RBF) kernel**, implemented with LIBSVM. The SVR has been trained
to map the 36 numbers onto **DMOS** — Difference Mean Opinion Score — the
average quality rating that human observers gave an image, collected in the
LIVE IQA database.

**This makes BRISQUE *opinion-aware*.** It is not computing a property of the
image in the abstract; it is predicting what a group of people said, about
images like the ones it was trained on. That training set is specific:

- **29 reference images**, **779 distorted versions**
- **five distortion types**: JPEG2000 compression, JPEG compression, additive
  white Gaussian noise, Gaussian blur, and a Rayleigh fast-fading channel
  simulation

Which leads directly to the limitation the authors state themselves: opinion-
aware models *"can only assess quality degradations arising from the distortion
types that they have been trained on."* That sentence, from the NIQE paper
describing BRISQUE and its peers, is the one to quote in the thesis. §6.1 is
its consequence for us.

In `pyiqa` 0.1.16 the trained SVR is shipped as fixed weights; the final score
is `kernel_features @ sv_coef − rho`, with `gamma = 0.05` and `rho = −153.591`
for the default model. **Nothing is trained or fitted on our data** — we are
applying a model trained in 2012 on someone else's photographs.

---

## 4. NIQE

**N**atural **I**mage **Q**uality **E**valuator. Mittal, Soundararajan & Bovik,
2013.

### 4.1 What it does, in words

NIQE uses **the same 36 features** as BRISQUE. The difference is entirely in
what it does with them.

Instead of learning a mapping to human scores, NIQE builds a **statistical
model of what those 36 numbers look like for pristine photographs**, and then
scores a test image by **how far its own 36 numbers sit from that model**. No
human ratings are involved. No distorted images are involved either — the model
is built from clean photographs only.

The authors' terminology, worth using precisely in the thesis:

- **Opinion-unaware (OU)** — never trained on human opinion scores.
- **Distortion-unaware (DU)** — never exposed to distorted images at all.

BRISQUE is **OA-DA** (opinion-aware, distortion-aware). NIQE is **OU-DU**, which
the authors call *"completely blind"*. The entire point of the paper is that
you can get competitive quality prediction with neither ingredient.

### 4.2 The pristine model

The reference model was built from **125 natural images**, sizes ranging from
480×320 to 1280×720, taken from copyright-free Flickr material and the Berkeley
image segmentation database, chosen so none overlapped with the test content.

Each image is divided into `P × P` patches, the 36 features are computed per
patch, and all the patches' feature vectors together are summarised by a single
**multivariate Gaussian (MVG)** — a bell curve in 36 dimensions:

```
                                  1                ⎡   1                       ⎤
    f_X(x₁,…,x_k)  =  ───────────────────────  exp ⎢ − ─ (x − ν)ᵀ Σ⁻¹ (x − ν) ⎥
                       (2π)^(k/2) |Σ|^(1/2)        ⎣   2                       ⎦
```
*(NIQE Eq. 9)*

Where:

- **`x₁,…,x_k`** — the `k = 36` NSS features.
- **`ν`** (nu) — the **mean vector**: the average value of each of the 36 features
  across all pristine patches. "What a clean photograph looks like, on average."
- **`Σ`** (capital sigma) — the **covariance matrix**, 36×36: how much each
  feature varies, *and* how the features vary together. This second part matters
  — it encodes that certain combinations are normal and others are not, even
  when each individual feature looks unremarkable.
- **`Σ⁻¹`** — the matrix inverse of `Σ`.
- **`|Σ|`** — the determinant of `Σ`.
- **`(x − ν)ᵀ`** — the transpose of the difference vector; a row-times-matrix-
  times-column arrangement that produces a single number.

`ν` and `Σ` are estimated by standard maximum likelihood. In `pyiqa` they are
loaded from a shipped file (`niqe_modelparameters.mat`) — **the pristine model
is fixed and is not recomputed from our images.**

### 4.3 Patch selection by sharpness — and a detail that is widely misreported

When building the pristine model, not every patch is used. The reasoning: every
real photograph contains some regions limited by defocus blur — any single-lens
camera has finite depth of field — and humans weight their quality judgements
towards the *sharp* parts of an image. So the model should be built from patches
that are actually in focus.

Sharpness is measured using the local standard deviation field `σ(i, j)` from
§2.2, which is already computed:

```
    δ(b)  =  Σ Σ      σ(i, j)
            (i,j) ∈ patch b
```
*(NIQE Eq. 4)*

Where:

- **`b`** — the patch index, `b = 1, 2, …, B`.
- **`δ(b)`** (delta) — the patch's total local activity: high for a detailed,
  in-focus, high-contrast patch; low for a smooth, blurred, or flat one.

Patches with `δ > T` are kept, where `T` is a fraction `p` of the **peak patch
sharpness in that image**. The paper uses **`p = 0.75`**, and reports only small
performance changes for `p` in `[0.6, 0.9]`. The patch size is **96×96**, with
stable behaviour reported from 32×32 to 160×160.

> **The detail that is frequently stated incorrectly.** The sharpness threshold
> is applied when **building the pristine model**. It is **not** applied to the
> image being scored. The NIQE paper is explicit: *"The sharpness criterion (4)
> is not applied to these patches because loss of sharpness in distorted images
> is indicative of distortion and neglecting them would lead to incorrect
> evaluation of the distortion severity."*
>
> The logic is sound — if you discarded the blurred patches of a blurry image,
> you would throw away the evidence of the blur. **We verified that `pyiqa`
> 0.1.16 follows the paper**: its `niqe()` function divides the test image into
> 96×96 blocks and uses **all** of them, with no sharpness filtering anywhere in
> the scoring path.

**Why this still matters for our frames.** Even though no patches are dropped
at scoring time, the *pristine model itself* was built only from sharp,
detail-rich patches. The yardstick therefore encodes "what a clean **sharp,
textured** photograph looks like". Our frames contain substantial areas of bare
concrete, dry pale dust and flat ground — regions that are genuinely low in
detail and are the subject matter, not a defect. Those patches are included in
the test image's fit but are under-represented in the reference model, which
can push the distance up for reasons that have nothing to do with degradation.
This is a structural mismatch between the model and our imagery, and it is a
reason to treat absolute NIQE values here with particular suspicion.

### 4.4 The score

The test image is divided into 96×96 patches, the same 36 features are computed
per patch, a second MVG is fitted to *those*, and the score is the distance
between the two models:

```
                              ┌─────────────────────────────────────────┐
                              │              ⎛ Σ₁ + Σ₂ ⎞⁻¹              │
    D(ν₁, ν₂, Σ₁, Σ₂)  =   √  │ (ν₁ − ν₂)ᵀ  ⎜ ─────── ⎟   (ν₁ − ν₂)    │
                              └              ⎝    2    ⎠                ┘
```
*(NIQE Eq. 10)*

Where:

- **`ν₁`, `Σ₁`** — mean vector and covariance of the **pristine** model.
- **`ν₂`, `Σ₂`** — mean vector and covariance fitted to the **test image**.
- **`(ν₁ − ν₂)`** — how far the test image's average feature values sit from the
  pristine average. This is the heart of it: a 36-number difference.
- **`(Σ₁ + Σ₂)/2`** — the averaged covariance, used to weight that difference.
  Directions in which clean images naturally vary a lot are discounted;
  directions in which they are consistent are weighted heavily. This makes the
  measure a **Mahalanobis-type distance** rather than a plain Euclidean one —
  it is "how many standard deviations away", not "how many units away".
- **`√`** — the square root makes the result a distance rather than a squared
  distance.

In `pyiqa` 0.1.16 the inverse is computed as a **pseudo-inverse**
(`torch.linalg.pinv`), which is a numerical safeguard for when the averaged
covariance matrix is near-singular.

**NIQE is therefore not a quality score in any absolute sense. It is a distance
from a 36-dimensional model of clean photographs.** Calling it "quality" is a
shorthand that the thesis should use carefully.

### 4.5 How it compares to BRISQUE

On the LIVE IQA database, median SROCC across 1000 train–test splits, all
distortions pooled:

| Metric | Type | SROCC (all) |
|---|---|---|
| BRISQUE | NR, opinion-aware, distortion-aware | 0.9395 |
| **NIQE** | **NR, opinion-unaware, distortion-unaware** | **0.9135** |
| SSIM | Full-reference | 0.9129 |
| PSNR | Full-reference | 0.8636 |

NIQE gets within 0.03 of BRISQUE while using neither human scores nor distorted
examples, and beats both classic full-reference metrics. That is the result
that made the paper notable — and note the comparison is **on the distortions
BRISQUE was trained for**, which is the most favourable possible ground for
BRISQUE.

---

## 5. Direction and scale

**Lower is better for both.** `pyiqa` records this explicitly:
`lower_better: True` for both `niqe` and `brisque`.

Nominal ranges, as declared by `pyiqa` 0.1.16:

| Metric | Declared range | What it really is |
|---|---|---|
| NIQE | `~0, ~100` | An unbounded non-negative distance. 0 would mean the test image's 36-feature model exactly coincides with the pristine model. There is no upper bound in the mathematics. |
| BRISQUE | `~0, ~150` | An SVR output trained to reproduce LIVE DMOS values, which run roughly 0–100. Because it is a regression output it can and does fall outside that range. |

Note the tildes in `pyiqa`'s own declarations. These are **nominal guidance,
not mathematical bounds.**

### These are not absolute scales

This section exists because it is the single easiest way to write something
indefensible in a thesis.

Our one verified measurement so far, from the environment check, is
`img_001.jpg`: **NIQE 3.4569, BRISQUE 21.1052.**

**A NIQE of 3.4569 does not mean "3.4569 units of badness".** It means: the
distance between the 36-dimensional Gaussian fitted to this image's patches and
the 36-dimensional Gaussian fitted to 125 pristine photographs in 2013 is
3.4569, in units determined by the averaged covariance matrix. That number is
meaningful **only** in comparison with other numbers computed:

- by the **same implementation** (`pyiqa` 0.1.16 NIQE differs from MATLAB's
  `niqe`, which is why `pyiqa` ships them as separate metrics, `niqe` and
  `niqe_matlab`),
- at the **same image size** (see §6.3),
- on the **same kind of content**.

There is no published threshold separating "good" from "bad". Claims of the
form *"NIQE below 4 indicates good quality"* appear in the wild and have no
basis in either paper. **Report differences, never absolute levels.** The
defensible sentence is "method A reduced NIQE relative to the unenhanced frame
by X on average across 9 scenes", not "method A achieved good quality (NIQE
3.1)".

---

## 6. The caveats that matter for this study

This is the most important section in the document. Each caveat below is a
reason a reviewer could reject a conclusion drawn from these metrics, so each
is stated plainly rather than hedged.

### 6.1 These metrics were built for different degradations than ours

Both metrics were developed and validated on **natural photographs with
synthetic distortions applied afterwards**. The LIVE IQA database's five
distortion types are: **JPEG2000 compression, JPEG compression, additive white
Gaussian noise, Gaussian blur, and Rayleigh fast-fading channel errors.**

Set that against what Phase 2 found in our dataset:

| Our degradation | Scenes affected | In the LIVE distortion set? |
|---|---|---|
| `hard_shadow` | 5 / 9 | **No** |
| `low_contrast` | 4 / 9 | **No** |
| `glare` | 4 / 9 | **No** |
| `haze_dust` | 3 / 9 | **No** |
| `colour_cast` | 0 / 9 | **No** |

**Not one of our degradations is a distortion either metric was built or
validated for.** Our degradations are properties of the *scene and the
illumination* — where the sun was, what was in the air, what the ground was
made of. The LIVE distortions are corruptions of the *signal* applied after a
clean capture: compression artifacts, sensor noise, lens blur, transmission
errors.

This is a category difference, not a difference of degree. A hard-edged shadow
is a perfectly natural optical phenomenon; a correctly exposed photograph of a
shadow is not a corrupted image in the sense these metrics model. There is no
reason internal to the papers to expect either metric to track shadow severity,
and BRISQUE in particular is explicitly limited by its authors to the
distortions it was trained on.

The consequence for the thesis: **NIQE and BRISQUE cannot be presented as
measuring how degraded our frames are.** At most they measure whether an
enhancement step has pushed an image's fine-scale texture statistics toward or
away from those of clean photographs, which is a narrower and different claim.

### 6.2 Enhancement can improve these metrics while making the image worse

This is the failure mode most likely to produce a wrong conclusion, because it
produces a *favourable-looking* wrong conclusion.

**The mechanism.** Both metrics reward MSCN statistics that resemble those of
clean natural photographs. Operations that sharpen edges, amplify local
contrast, or add fine high-frequency texture move those statistics toward the
"natural" model — **whether or not any real information was recovered**. An
aggressive unsharp mask applied to a hazy frame does not recover the occluded
detail; it manufactures local contrast where there was none. The resulting
image can score better on both metrics while containing no more genuine
information about the scene, and possibly less, if the operation has amplified
noise or introduced halos.

Recall the structural point from §1: with no reference available, **neither
metric can distinguish "information restored" from "statistics made to look
natural"**. The two are indistinguishable by construction. This is not a bug in
the implementations; it is a limit of what no-reference assessment can do.

**Published evidence.** Chen et al. (IEEE Transactions on Multimedia, 2023)
built SQUARE-LOL, a large database of **enhanced** low-light images with human
quality ratings, and evaluated existing blind IQA models against those ratings.
Their measured correlations with human opinion on enhanced images:

| Metric | SROCC | PLCC |
|---|---|---|
| **NIQE** | **0.276** | **0.286** |
| **BRISQUE** | **0.658** | **0.649** |
| (their proposed IACA model, for context) | 0.875 | 0.878 |

Compare those NIQE figures with the 0.9135 it achieves on LIVE (§4.5). The
authors' conclusion, verbatim: *"the performance of conventional BIQA methods
is significantly below the desired level. Due to the intrinsic differences
between the enhanced low-light images and the normal-light images, the readily
deployed IQA models may not suffice in the low-light enhancement scenarios."*

**What this citation does and does not establish.** It is strong, directly
relevant, peer-reviewed evidence that **NIQE correlates poorly with human
judgement specifically on enhanced images** — which is exactly our use case,
since Phase 3 evaluates enhancement. It concerns low-light enhancement rather
than shadow/haze/glare enhancement, so it is close but not identical to our
setting; it should be cited as strong supporting evidence, not as a result
about our exact problem. Note also that BRISQUE holds up considerably better
than NIQE in their table — a reason to report both rather than NIQE alone.

**The specific sharpening mechanism described above — that sharpening and local
contrast boosting push NSS statistics toward "natural" regardless of real
information recovery — is our own reasoning from how the metrics are
constructed.** It follows directly from §2 and §4.4, but we did not find a
published study isolating that exact mechanism, and it should be presented as
our analysis rather than attributed to a source. See §9.

### 6.3 Scale dependence — why the fixed 1024 px long side is required

The MSCN normalisation uses a **fixed 7×7 pixel window** (§2.2). A fixed-size
window covers different amounts of *scene* depending on image resolution. At
4000 px wide, a 7×7 window spans a tiny fraction of an object; at 1024 px, it
spans roughly four times as much. The texture statistics it measures therefore
change with resolution, **for the same scene, with no change in quality.**

NIQE adds a second scale dependence: the image is divided into **96×96 blocks**,
and `pyiqa` crops to a whole number of blocks before scoring. For our frames:

| Frame size | Blocks (scale 1) | Pixels actually used | Discarded |
|---|---|---|---|
| 1024 × 770 (landscape, 73 frames) | 10 × 8 = 80 | 960 × 768 | 64 px of width, 2 px of height |
| 770 × 1024 (portrait, 4 frames) | 8 × 10 = 80 | 768 × 960 | 2 px of width, 64 px of height |

Both orientations give the same 80 blocks, so landscape and portrait frames are
at least comparable in how much data the metric sees — convenient, and worth
stating in the thesis.

**This is why `scripts/preprocess.py` resizes every frame to exactly 1024 px on
the long side, and why that must not be varied between conditions.** Comparing
a NIQE value computed at 1024 px against one computed at 4000 px is
meaningless. Every number in Phase 3 must come from the same pipeline at the
same resolution. Any enhancement method that changes output resolution must
have its output resampled back to 1024 before scoring.

### 6.4 Both metrics are nearly blind to colour

**This is the most consequential caveat for our specific task.**

Both metrics operate on a **single luminance channel**. Verified in `pyiqa`
0.1.16: NIQE uses `test_y_channel = True` with `color_space = 'yiq'`, converting
to the Y (luma) channel before any processing. BRISQUE is stricter still — its
implementation *asserts* `test_y_channel = True` and refuses to run otherwise.

Luminance is a weighted sum of the colour channels. Two images with identical
luminance but completely different colour are, to these metrics, **the same
image**. It follows that:

> **NIQE and BRISQUE cannot detect a colour distortion that preserves
> luminance.** A method that shifts every hue, desaturates the frame, or
> introduces a colour cast can leave both scores unchanged — or improve them.

**Why this matters more here than in a general imaging study.** The downstream
task of this project is material discrimination in waste: distinguishing brown
cardboard from blue polythene from green vegetation from grey rubble.
**Colour is the primary cue for that task.** A method that cleans up texture
statistics while flattening the brown/blue distinction would be scored as an
improvement by both metrics while actively destroying the information the
application depends on.

**This is the direct, concrete argument for the Lab colour-shift check.**
Measuring the shift in CIELAB `a*` and `b*` between the original and enhanced
frame covers exactly the failure mode NIQE and BRISQUE are structurally unable
to see. The two measurement families are complementary, not redundant:

| What it catches | NIQE / BRISQUE | Lab colour-shift |
|---|---|---|
| Texture / sharpness statistics drifting from natural | **Yes** | No |
| Hue rotation, desaturation, colour cast introduced | **No** | **Yes** |
| Material-discriminating colour distinctions flattened | **No** | **Yes** |

Running NIQE and BRISQUE without a colour measure would leave the project's
most important failure mode completely unmonitored. That is the argument, and
it is strong enough to state as a design requirement rather than a nicety.

(A secondary note: `colour_cast` was tagged `0/77` in Phase 2, so there is no
colour degradation to *correct*. The colour-shift measure is therefore a
**guard against enhancement introducing colour damage**, not a measure of
existing damage. Those are different purposes and the thesis should not conflate
them.)

### 6.5 Sample size and correlation structure

Metrics will be computed on **77 frames across 9 scenes**. Two scenes supply 43
of the 77 frames (56%).

**The 77 frames are not 77 independent observations.** Frames within a scene
share site, illumination, time of day and camera settings, so their metric
values are correlated. A standard error computed as though n = 77 would be too
small, and a significance test on that basis would be invalid.

**Aggregate within scene first, then across the nine scenes**, and say so
explicitly when reporting. The effective sample size for any claim about
"enhancement method A vs B" is closer to 9 than to 77.

**One refinement from the Phase 2 audit (§7 of
`results/phase2_degradation_audit.md`).** Measured frame-to-frame similarity
within scenes never exceeds 0.851, and frames tagged the same are no more alike
than frames tagged differently. The burst frames are therefore **not**
near-duplicates — the photographer was moving between shots. The correlation
within a scene runs through **shared conditions, not repeated framing**, so the
effective sample is somewhat larger than 9. Scene-level aggregation remains the
defensible choice; the caveat is about correlation, not duplication.

### 6.6 Secondary limitations worth one line each

- **Implementation ≠ paper.** `pyiqa`'s `niqe` and `niqe_matlab` give different
  numbers for the same image. Fix one implementation and version for all of
  Phase 3, and name it in the thesis. Ours is `pyiqa` 0.1.16, metric `niqe`.
- **The pristine model is frozen and foreign.** NIQE's reference is 125
  photographs selected in 2013. No Indian urban waste site is in it. Our frames
  are out-of-domain for the yardstick itself.
- **BRISQUE's training set is equally foreign** — 29 reference photographs, none
  resembling our subject matter.
- **CPU-only execution** affects runtime, not values. NIQE and BRISQUE are cheap;
  this only matters for the deep metrics if we add them.

---

## 7. How we will use them, and what they can support

### What we will do

1. Compute NIQE and BRISQUE with `pyiqa` 0.1.16 on every frame, before and after
   each enhancement method, all at exactly 1024 px long side.
2. Compute a **CIELAB colour-shift measure** on the same frames, for the reason
   in §6.4.
3. Aggregate **within scene first, then across the 9 scenes** (§6.5).
4. Report **changes** relative to the unenhanced frame, never absolute levels
   (§5).
5. Present **visual grids** of the representative images from Phase 2 alongside
   every table of numbers.

### Claims these metrics CAN support

- *"Method A moved the no-reference quality statistics of these frames further
  from / closer to those of clean natural photographs than method B did,
  consistently across N of 9 scenes."*
- *"Method A degraded NIQE and BRISQUE relative to the unenhanced frames."* — a
  **negative** result is the stronger kind here. If a method makes both metrics
  worse, that is good evidence something went wrong, because the failure mode in
  §6.2 biases these metrics toward *flattering* enhancement. A method that
  cannot even game a gameable metric has a real problem.
- *"The ranking of methods by NIQE is / is not stable across scenes."* —
  consistency across the 9 scenes is itself a finding, independent of whether
  the absolute direction means anything.

### Claims these metrics CANNOT support

- ✗ *"Method A improved image quality."* Not licensed. They measure distance
  from a natural-scene-statistics model, not quality, and on enhanced images
  NIQE's correlation with human judgement has been measured at **SROCC 0.276**
  (§6.2).
- ✗ *"Method A reduced haze / recovered shadow detail."* Not licensed. Neither
  metric models those degradations at all (§6.1). Degradation-specific claims
  must come from the Phase 2 visual tags and the visual grids.
- ✗ *"Method A is better for waste material discrimination."* Not licensed, and
  **actively dangerous**: a method can improve both metrics while destroying the
  colour distinctions the task depends on (§6.4).
- ✗ *"NIQE 3.1 is good quality."* Not licensed. There is no such threshold (§5).
- ✗ *"The improvement is statistically significant (n = 77)."* Not licensed.
  n is effectively closer to 9 (§6.5).

### The reporting rule

**Never report NIQE or BRISQUE alone.** Every table carries, at minimum:

1. NIQE **and** BRISQUE (they disagree informatively — see §6.2, where BRISQUE
   correlates with human opinion more than twice as well as NIQE on enhanced
   images),
2. the **Lab colour-shift** measure, and
3. a pointer to the **visual grid** for the representative frames.

And the limitations in §6.1, §6.2 and §6.4 are stated in the thesis text where
the results are presented — not relegated to a future-work section. They are
properties of the measurement, not open questions.

---

## 8. Sources

All of the following were retrieved and read for this document.

**Primary papers**

1. A. Mittal, A. K. Moorthy, and A. C. Bovik, "No-Reference Image Quality
   Assessment in the Spatial Domain," *IEEE Transactions on Image Processing*,
   vol. 21, no. 12, pp. 4695–4708, December 2012. DOI: 10.1109/TIP.2012.2214050.
   Full text: <https://live.ece.utexas.edu/publications/2012/TIP%20BRISQUE.pdf>
   — *Source for: MSCN Eqs. 1–3, GGD Eqs. 4–6, pairwise products Eqs. 7–10,
   AGGD Eqs. 12–15, Table I feature layout, the 18-per-scale / 36-total count,
   two-scale design, SVR-RBF via LIBSVM, LIVE IQA validation set composition,
   window size K = L = 3, C = 1.*

2. A. Mittal, R. Soundararajan, and A. C. Bovik, "Making a 'Completely Blind'
   Image Quality Analyzer," *IEEE Signal Processing Letters*, vol. 20, no. 3,
   pp. 209–212, March 2013.
   Full text: <http://live.ece.utexas.edu/research/Quality/niqe_spl.pdf>
   — *Source for: OU/DU terminology, patch selection Eq. 4 with p = 0.75, patch
   size 96×96, the 125-image pristine corpus, MVG Eq. 9, distance Eq. 10, the
   explicit statement that the sharpness criterion is NOT applied to test
   patches, and the Table I SROCC comparison.*

**Supporting sources**

3. H. R. Sheikh, M. F. Sabir, and A. C. Bovik, "A statistical evaluation of
   recent full reference image quality assessment algorithms," *IEEE
   Transactions on Image Processing*, vol. 15, no. 11, pp. 3440–3451, 2006.
   — The **LIVE IQA database**: 29 reference images, 779 distorted images, five
   distortion types, DMOS scores. This is what BRISQUE was trained on and what
   both metrics were validated against. Cited as reference [27] in the BRISQUE
   paper and [2] in the NIQE paper; bibliographic details taken from those
   reference lists.

4. D. L. Ruderman, "The statistics of natural images," *Network: Computation in
   Neural Systems*, vol. 5, no. 4, pp. 517–548, 1994.
   — The original observation that locally mean-subtracted, contrast-normalised
   luminances tend toward a unit normal Gaussian for natural images. The
   foundation both metrics rest on. Cited as [15] in BRISQUE and [10] in NIQE.

5. D. Martin, C. Fowlkes, D. Tal, and J. Malik, "A database of human segmented
   natural images…," *Int. Conf. Computer Vision*, vol. 2, pp. 416–423, 2001.
   — The **Berkeley segmentation database**, one of the two sources of NIQE's
   125 pristine images (with copyright-free Flickr material).

6. K. Sharifi and A. Leon-Garcia, "Estimation of shape parameter for generalized
   Gaussian distributions in subband decompositions of video," *IEEE Trans.
   Circuits Syst. Video Technol.*, vol. 5, no. 1, pp. 52–56, 1995.
   — The moment-matching method used to fit the GGD parameters.

7. N. E. Lasmar, Y. Stitou, and Y. Berthoumieu, "Multiscale skewed heavy tailed
   model for texture analysis," *IEEE Int. Conf. Image Processing*, pp. 2281–
   2284, 2009.
   — The AGGD model and its moment-matching parameter estimation.

**Evidence on the enhancement failure mode (§6.2)**

8. B. Chen, L. Zhu, H. Zhu, W. Yang, L. Song, and S. Wang, "Gap-closing Matters:
   Perceptual Quality Evaluation and Optimization of Low-Light Image
   Enhancement," *IEEE Transactions on Multimedia*, 2023.
   DOI: 10.1109/TMM.2023.3312851. Preprint: <https://arxiv.org/abs/2302.11464>
   — *Source for: the SQUARE-LOL database of human-rated enhanced low-light
   images, and the measured correlations with human opinion on enhanced images
   — NIQE SROCC 0.276 / PLCC 0.286, BRISQUE SROCC 0.658 / PLCC 0.649 — together
   with the authors' conclusion that conventional blind IQA methods perform
   "significantly below the desired level" on enhanced images.* Figures read
   directly from Table III of the arXiv v5 full text.

**Implementation**

9. C. Chen and J. Mo, "IQA-PyTorch: PyTorch Toolbox for Image Quality
   Assessment," 2022. <https://github.com/chaofengc/IQA-PyTorch>
   — The implementation we use, pinned at **version 0.1.16**. Implementation
   details in this document were read directly from the installed package
   source: `pyiqa/archs/niqe_arch.py`, `pyiqa/archs/brisque_arch.py`, and
   `pyiqa/default_model_configs.py`.
   — *Verified from source: NIQE block size 96×96 with cropping to whole blocks,
   two scales, Y-channel via YIQ, pristine parameters loaded from
   `niqe_modelparameters.mat`, pseudo-inverse in the distance computation, no
   sharpness filtering in the scoring path; BRISQUE kernel size 7 with sigma
   7/6, Y-channel assertion, RBF kernel with gamma = 0.05 and rho = −153.591;
   `lower_better: True` and nominal score ranges `~0,~100` (NIQE) and `~0,~150`
   (BRISQUE) for both.*

**Project-internal**

10. `results/phase2_degradation_audit.md` — degradation prevalence per scene,
    the scene clustering, and the frame-similarity finding in §6.5.
11. `scripts/preprocess.py` — the 1024 px long-side normalisation.
12. `notes/degradation_rules.md` — the frozen tagging rules.

---

## 9. What could not be verified

Stated explicitly so nothing in this document is cited with more confidence than
it has earned.

1. **The sharpening-gaming mechanism (§6.2).** The claim that *sharpening and
   local contrast enhancement push MSCN statistics toward the "natural" model
   regardless of whether real information was recovered* is **our own reasoning**
   from the construction of the metrics (§2, §4.4). It follows directly from the
   fact that both metrics score fine-scale texture statistics and have no
   reference to compare against — but we did not find a published study
   isolating that exact mechanism. **Present it as our analysis, not as a cited
   result.** The Chen et al. citation supports the broader and separately
   verified claim that NR-IQA metrics correlate poorly with human judgement on
   enhanced images; it does not establish the specific mechanism.

2. **Typical value ranges for our kind of imagery.** No source gives expected
   NIQE or BRISQUE ranges for outdoor waste-site photography. The `~0–100` and
   `~0–150` figures in §5 are `pyiqa`'s own nominal declarations, not measured
   or theoretical bounds. Our only verified measurement to date is
   `img_001.jpg`: NIQE 3.4569, BRISQUE 21.1052. **The empirical distribution
   across our 77 frames has not yet been computed**; it should be, early in
   Phase 3, and reported as a dataset property before any method comparison.

3. **The relative weighting of the LIVE distortion types** in BRISQUE's trained
   SVR — i.e. which distortions dominate its predictions — is not reported in
   the paper and we did not attempt to recover it from the shipped weights. This
   would be the rigorous way to say *how* out-of-domain our frames are, and it
   remains unquantified.

4. **Whether NIQE's flat-region sensitivity (§4.3) materially affects our
   frames.** The argument is structural: the pristine model was built from sharp
   patches, our frames contain large genuinely-flat regions. We have not
   measured the size of the effect. It is a reasoned concern, not a demonstrated
   one, and is labelled as such in §4.3.
