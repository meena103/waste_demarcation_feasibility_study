# Phase 3 — baseline metric analysis

Source: `baseline.csv` — 77 frames

## 1. Distributions across the baseline set (1024 px)

| metric | n | min | p25 | median | p75 | max | mean | sd |
|---|---|---|---|---|---|---|---|---|
| NIQE | 77 | 2.0309 | 2.7168 | 3.0129 | 3.3784 | 3.9995 | 3.0051 | 0.4727 |
| BRISQUE | 77 | 4.7927 | 17.0612 | 18.5764 | 22.5505 | 38.0270 | 19.3254 | 5.2303 |

### Per-scene means

| scene | n | NIQE mean | NIQE sd | BRISQUE mean | BRISQUE sd |
|---|---|---|---|---|---|
| scene_01 | 3 | 2.1137 | 0.0858 | 5.5905 | 1.2296 |
| scene_02 | 4 | 3.4312 | 0.0964 | 20.0186 | 2.4703 |
| scene_03 | 7 | 3.4453 | 0.3142 | 23.1241 | 3.0708 |
| scene_04 | 13 | 2.6759 | 0.4823 | 19.4062 | 6.5234 |
| scene_05 | 2 | 3.4828 | 0.2755 | 20.9880 | 4.0873 |
| scene_06 | 20 | 2.9532 | 0.4265 | 19.3871 | 3.9612 |
| scene_07 | 23 | 3.1124 | 0.3739 | 19.2927 | 3.9704 |
| scene_08 | 4 | 2.8791 | 0.2274 | 21.2988 | 6.7786 |
| scene_09 | 1 | 3.2934 | 0.0000 | 18.4123 | 0.0000 |

Spread of the 9 scene-level NIQE means: 2.1137 to 3.4828 (sd 0.4481). Between-scene variation of this size is the reason to aggregate at scene level before comparing methods.

## 2. Scale effect — 1024 px vs full resolution

Paired on filename: 77 frame(s) present in both sets.

| metric | 1024 px mean | full-res mean | mean diff | median diff | min diff | max diff | frames where full-res scores worse |
|---|---|---|---|---|---|---|---|
| NIQE | 3.0051 | 2.8182 | -0.1870 | -0.2820 | -1.6299 | +1.8718 | 28/77 |
| BRISQUE | 19.3254 | 17.3352 | -1.9901 | +1.3125 | -56.4752 | +25.2319 | 41/77 |

- **NIQE**: full resolution shifts the mean by **-0.1870** (-6.2% of the 1024 px mean). Correlation between the two sets across frames: r = -0.219.
- **BRISQUE**: full resolution shifts the mean by **-1.9901** (-10.3% of the 1024 px mean). Correlation between the two sets across frames: r = -0.217.

> **Interpretation.** These are the *same scenes*, unchanged in quality — the only difference is pixel dimensions. Any shift here is pure measurement artefact. It is the empirical justification for fixing the working resolution at a 1024 px long side and scoring every method there. A baseline taken from `data/raw` would be offset from every method's score by roughly this amount, for no reason connected to enhancement.

> Note the rank behaviour too: r = -0.219 for NIQE. A low correlation means the two resolutions do not even agree on the relative ordering of frames — the scale effect is not a simple offset.

## 3. Outlier frames

### NIQE — Tukey fences [1.7243, 4.3709]

No frames outside the fences.

### BRISQUE — Tukey fences [8.8273, 30.7844]

| filename | scene | value | direction | tags |
|---|---|---|---|---|
| `img_018.jpg` | scene_04 | 38.0270 | worse | none |
| `img_071.jpg` | scene_08 | 30.9841 | worse | none |
| `img_074.jpg` | scene_01 | 7.0065 | better | hard_shadow |
| `img_073.jpg` | scene_01 | 4.9724 | better | hard_shadow |
| `img_075.jpg` | scene_01 | 4.7927 | better | hard_shadow |

## 4. Do the metrics see our degradations?

For each degradation, the metric values of frames tagged `yes` are compared with frames tagged `no`. **Lower is better for both metrics**, so if a metric detects a degradation, the `yes` group should have the HIGHER mean.

Two levels are reported. Frame level uses all 77 frames but they are not independent (they cluster in 9 scenes), so its p-values are optimistic. Scene level aggregates to one value per scene first and is the defensible test, but has at most 9 points and very little power. Both are shown so the weakness is visible.

Frames with tags: 77/77

### NIQE

| degradation | n yes | n no | mean(yes) | mean(no) | diff | direction | U | p (approx) |
|---|---|---|---|---|---|---|---|---|
| `haze_dust` | 5 | 72 | 3.0632 | 3.0011 | +0.0621 | detected (worse when tagged) | 165.0 | 0.7565 |
| `hard_shadow` | 29 | 48 | 2.8642 | 3.0903 | -0.2261 | OPPOSITE (better when tagged) | 524.0 | 0.0706 |
| `glare` | 10 | 67 | 3.2675 | 2.9660 | +0.3016 | detected (worse when tagged) | 209.0 | 0.0562 |
| `colour_cast` | 0 | 77 | — | — | — | not present in the dataset | — | — |
| `low_contrast` | 13 | 64 | 3.0430 | 2.9974 | +0.0455 | detected (worse when tagged) | 412.0 | 0.9566 |

Scene level (NIQE) — scene mean metric vs fraction of frames in that scene carrying the tag:

| degradation | scenes with | scenes without | mean(with) | mean(without) | diff | direction |
|---|---|---|---|---|---|---|
| `haze_dust` | 3 | 6 | 3.0904 | 3.0193 | +0.0711 | detected |
| `hard_shadow` | 5 | 4 | 2.8601 | 3.2716 | -0.4115 | OPPOSITE |
| `glare` | 4 | 5 | 3.1791 | 2.9341 | +0.2450 | detected |
| `colour_cast` | 0 | 9 | — | — | — | not testable |
| `low_contrast` | 4 | 5 | 3.0920 | 3.0038 | +0.0881 | detected |

### BRISQUE

| degradation | n yes | n no | mean(yes) | mean(no) | diff | direction | U | p (approx) |
|---|---|---|---|---|---|---|---|---|
| `haze_dust` | 5 | 72 | 20.9235 | 19.2144 | +1.7092 | detected (worse when tagged) | 143.0 | 0.4443 |
| `hard_shadow` | 29 | 48 | 18.3083 | 19.9398 | -1.6316 | OPPOSITE (better when tagged) | 652.5 | 0.6474 |
| `glare` | 10 | 67 | 20.1668 | 19.1998 | +0.9671 | detected (worse when tagged) | 275.0 | 0.3632 |
| `colour_cast` | 0 | 77 | — | — | — | not present in the dataset | — | — |
| `low_contrast` | 13 | 64 | 18.6780 | 19.4568 | -0.7788 | OPPOSITE (better when tagged) | 362.0 | 0.4628 |

Scene level (BRISQUE) — scene mean metric vs fraction of frames in that scene carrying the tag:

| degradation | scenes with | scenes without | mean(with) | mean(without) | diff | direction |
|---|---|---|---|---|---|---|
| `haze_dust` | 3 | 6 | 19.8956 | 17.9719 | +1.9237 | detected |
| `hard_shadow` | 5 | 4 | 17.3601 | 20.1794 | -2.8193 | OPPOSITE |
| `glare` | 4 | 5 | 20.7028 | 16.9415 | +3.7613 | detected |
| `colour_cast` | 0 | 9 | — | — | — | not testable |
| `low_contrast` | 4 | 5 | 20.0824 | 17.4377 | +2.6447 | detected |

> **How to read a null result here.** If the differences are small and the directions inconsistent, that is the expected outcome, not a failure of the experiment. Neither metric was built for shadow, haze, glare or contrast degradation — see `notes/niqe_brisque_explained.md` §6.1. A null result is positive evidence that these metrics cannot stand alone as degradation measures for this dataset, and strengthens the case for reporting them only alongside the colour-shift measure and the visual grids.

## 5. Method comparison

*No enhancement methods evaluated yet — baseline only.*

