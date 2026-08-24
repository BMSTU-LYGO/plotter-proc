# Block 2

## Baseline

- Branch: `swag`.
- Base HEAD: `c72c2f2510d4abb7be8e49e5c6116e906f4facab`.
- Input: `plotter_pipeline_full_test.docx`, A5, normal size, centerline font,
  safe connections, hybrid layout, one warm run.
- Baseline artifact: `build/upd12-block1-after.json`.

The measured handwriting stage was the largest warm bottleneck:

| Scope | `route_words` baseline |
|---|---:|
| Page 1 | 1.525 s |
| Pages 1–5 | 9.186 s |
| Pages 1–20 | 27.933 s |

The full warm run took 67.240 s, of which the aggregate handwriting stage took
27.948 s. The document contained 5,747 candidate pairs; 1,359 were accepted and
4,388 rejected.

## Profile evidence

The block 1 profile on `examples/benchmark_50_words.txt` showed:

| Function | Calls | Cumulative |
|---|---:|---:|
| `route_words()` | 1 | 3.958 s |
| `_connection_candidate()` | 256 | 3.164 s |
| `_collision_points()` | 242 | 3.130 s |

The final block 2 profile shows:

| Function | Calls | Cumulative |
|---|---:|---:|
| `route_words()` | 1 | 3.154 s |
| `_connection_candidate()` | 256 | 2.305 s |
| `_collision_points()` | 110 | 2.277 s |

The short profiled handwriting stage fell from 3.961 s to 3.179 s (-19.7%), while
collision queries fell from 242 to 110 (-54.5%). The final profile is stored in
`build/upd12-block2-profile-final.json` and
`build/upd12-block2-profile-final-run-000.prof`.

## Root cause

Rejected pairs paid for diagnostic allocations, Bezier construction and collision
scanning before inexpensive rules had a chance to reject them. Collision lookup
filtered only whole strokes by bounding box, after which every segment of each
nearby stroke was inspected. Entry/exit anchors could also be derived twice while
orienting a glyph.

## Changes

1. `_connection_candidate()` now preserves rejection-reason priority while applying
   cheap validity, punctuation, letter, routeability, distance, vertical and safe
   direction/tangent checks before expensive connector and collision work.
2. `route_words(..., collect_debug=False)` builds full rejected-candidate diagnostics
   only for `--connection-debug`. Normal `paths.json` files do not contain
   `connection_debug` metadata; debug mode retains complete curve diagnostics.
3. Collision lookup now uses a two-level spatial index. Coarse cells select strokes;
   lazily built per-stroke cells contain segment IDs and return only overlapping
   `SegmentObstacle` records. Boundary-ignore rules for the left and right strokes
   are unchanged.
4. Classification is performed once per routed glyph, and `_orient_for_anchors()`
   returns its already computed anchors. Anchors are recalculated only if reversal
   changes orientation.
5. Per-page and aggregate reports now expose stable algorithmic counters:
   `cheap_rejected_pairs`, `beziers_built`, `collision_queries`, and
   `segments_tested`.
6. NumPy distance batching was not added: after segment filtering, the final profile
   is dominated by lazy segment-index construction rather than
   `_point_segment_distance()`, and the acceptable `<15 s` milestone is met without
   a new geometry dependency.

## Tests

```text
make lint                         passed
pytest                            273 passed
make smoke                        passed
targeted tests                    31 passed
```

New coverage verifies that 1,000 distance-rejected pairs build no Beziers and issue
no collision queries, normal mode omits debug metadata, debug mode retains complete
geometry, and the segment index returns the expected obstacles.

## Benchmark before

| Metric | Before |
|---|---:|
| Full wall | 67.240 s |
| Handwriting stage | 27.948 s |
| `route_words`, page 1 | 1.525 s |
| `route_words`, pages 1–5 | 9.186 s |
| `route_words`, pages 1–20 | 27.933 s |

## Benchmark after

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Full wall | 67.240 s | 53.946 s | -19.8% |
| Handwriting stage | 27.948 s | 14.140 s | -49.4% |
| `route_words`, page 1 | 1.525 s | 0.450 s | -70.5% |
| `route_words`, pages 1–5 | 9.186 s | 3.552 s | -61.3% |
| `route_words`, pages 1–20 | 27.933 s | 14.139 s | -49.4% |

The acceptable block milestone (`route_words < 15 s`) is met. Raw final result:
`build/upd12-block2-final-v2.json`.

Final algorithmic counters on the 20-page document:

```text
pairs_total             5,747
accepted                1,359
rejected                4,388
cheap_rejected_pairs    1,617
beziers_built           4,024
collision_queries       2,255
segments_tested     3,257,918
```

## Geometry/quality comparison

All 62 production artifacts (`paths.json`, per-page and combined G-code, and
plotter previews) are byte-identical to the block 1 baseline. Aggregate connection
results are also exactly equal:

```text
accepted connections       1,359
rejected connections       4,388
snapped existing contact     106
connector length       1,543.326153 mm
```

Every rejection-reason count is unchanged, including distance, routeability,
backward motion, tangent mismatch, vertical offset, collision, letters,
punctuation and corridor. Maximum output geometry deviation is therefore `0.0 mm`.

## Regressions

No correctness regression was found. Reports differ from baseline only because the
new algorithmic counters and timing values are present. Debug work is opt-in, and
normal conversion artifacts remain deterministic.

## Remaining bottleneck

The final short profile shows lazy `_StrokeSegmentIndex.build()` as the main
handwriting cost. For the overall warm conversion, simplification is now the largest
stage at 20.693 s, followed by handwriting at 14.140 s and build paths at 9.128 s.
Those belong to blocks 3 and 4; they were not modified in this block.
