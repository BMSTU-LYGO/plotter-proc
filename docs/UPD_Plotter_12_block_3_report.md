# Block 3

## Baseline

- Branch: `swag`.
- Base HEAD: `c72c2f2510d4abb7be8e49e5c6116e906f4facab`.
- Input: `plotter_pipeline_full_test.docx`, A5, normal size, centerline font,
  safe connections, hybrid layout, one warm run.
- Baseline artifact: `build/upd12-block2-final-v2.json`.

| Metric | Baseline |
|---|---:|
| Full wall | 53.946 s |
| Simplification | 20.693 s |
| Handwriting | 14.140 s |
| Build paths | 9.128 s |

## Profile evidence

The full baseline simplification profile is stored in
`build/upd12-block3-before-profile.json`. Under `cProfile` it recorded:

| Function/counter | Baseline |
|---|---:|
| `simplify_path_document()` | 43.438 s cumulative |
| `_rdp_with_deviation()` | 6,453 calls / 39.961 s cumulative |
| `math.hypot()` | 47,581,924 calls |
| built-in `min()` | 40,263,183 calls |
| built-in `max()` | 40,380,931 calls |

The final short-corpus profile is stored in
`build/upd12-block3-final-profile.json`. Only 69 of 276 strokes required RDP;
the remaining compatible glyph occurrences used cached retained-point indices.
The cache key itself takes 0.0028 s cumulative and is no longer a bottleneck.

## Complexity metrics

Every page report now records stroke count, point count, maximum points in one
stroke, median points per stroke and p95 before routing, after routing and after
simplification.

Aggregate counts for the 20-page document:

| Phase | Strokes | Points | Maximum points/stroke |
|---|---:|---:|---:|
| Before `route_words` | 7,812 | 7,135,492 | 3,201 |
| After `route_words` | 6,453 | 7,141,840 | 6,592 |
| After simplification | 6,453 | 111,715 | 113 |

Per-page median points/stroke increases from a range of 747–1,041 before routing
to 747–1,152 after routing. Per-page p95 increases from 1,598–2,212 to
2,217.85–2,973.75. This confirms that word joining creates longer RDP inputs.

## Root cause

The scalar Python RDP loop calculated square roots and clamped projections with
Python `min/max` for tens of millions of point/segment comparisons. It also repeated
the same reduction for translated copies of the same glyph contour across pages.

## Changes

1. RDP compares squared distance with squared epsilon and takes one square root only
   for the reported maximum observed deviation.
2. Intervals longer than 64 points use NumPy vectorized projection, clipping,
   squared-distance and `argmax`; shorter intervals retain a low-overhead scalar
   fast path.
3. `_dedupe()` also compares squared distances and avoids `hypot` in its hot loop.
4. An ephemeral per-run `SimplificationTemplateCache` stores retained-point indices.
   Its strict key contains font identity, character, effective scale, contour,
   closed/open state, point count, direction endpoints and epsilon. Translation is
   deliberately excluded.
5. Cache reuse happens after `route_words`, so routing, anchor and collision decisions
   still inspect the original geometry. Joined strokes and graphics continue through
   the optimized RDP path.
6. With handwriting variation enabled, template reuse is conservatively disabled.
   RDP then operates directly in final millimetres, so scale jitter cannot consume
   more than the configured 0.06 mm error budget.
7. Stable counters report `unique_templates_simplified`,
   `glyph_occurrences_reused`, and `post_join_strokes_processed`.

Final counters over 20 pages:

```text
unique_templates_simplified      256
glyph_occurrences_reused       4,535
post_join_strokes_processed    1,662
```

## Tests

```text
make lint                         passed
pytest                            276 passed
make smoke                        passed
targeted tests                    27 passed
git diff --check                  passed
```

New tests verify scalar/vectorized RDP equality, cache reuse for translated glyphs,
complexity metrics and rejection of incompatible point sequences sharing the same
font/character/scale identity.

## Benchmark before

| Metric | Before |
|---|---:|
| Full wall | 53.946 s |
| Simplification | 20.693 s |
| Handwriting | 14.140 s |
| Build paths | 9.128 s |

## Benchmark after

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Full wall | 53.946 s | 36.357 s | -32.6% |
| Simplification | 20.693 s | 3.988 s | -80.7% |
| Handwriting | 14.140 s | 13.912 s | -1.6% |
| Build paths | 9.128 s | 8.895 s | -2.6% |

The preferred block target (`simplification < 5 s`) is met. Raw final result:
`build/upd12-block3-final.json`.

## Geometry/quality comparison

Connection metrics for every page are exactly equal to the block 2 baseline. All
6,453 strokes retain identical ordering and metadata, including closed/open state,
source glyphs, connection IDs, segment types, semantic roles and layout roles.

Nineteen of twenty `paths.json` files are byte-identical. Page 8 contains one extra
retained point in one otherwise identical stroke. The measured bidirectional
vertex-to-polyline deviation is `0.058104467 mm`, below the configured and required
`0.06 mm` limit. The point count changes from 111,714 to 111,715; stroke topology is
unchanged.

## Regressions

No correctness regression was found. The one-point difference is within the existing
RDP error budget and does not affect topology or connection semantics. An intermediate
cache-key collision found during benchmarking was fixed by including point count and
endpoint direction, and is covered by a regression test.

## Remaining bottleneck

Handwriting is again the largest measured warm stage at 13.912 s, followed by
build paths at 8.895 s. Within simplification, the remaining work is vectorized RDP
for joined/graphic strokes and linear dedupe; the stage is already below the desired
5-second target. Build-path template allocation belongs to block 4 and was not
modified here.
