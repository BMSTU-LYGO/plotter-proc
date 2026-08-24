# Block 4

## Baseline

- Branch: `swag`.
- Base HEAD: `c72c2f2510d4abb7be8e49e5c6116e906f4facab`.
- Input: `plotter_pipeline_full_test.docx`, A5, normal size, centerline font,
  safe connections, hybrid layout, one warm run.
- Baseline artifact: `build/upd12-block3-final.json`.

| Metric | Baseline |
|---|---:|
| Full wall | 36.357 s |
| Build paths | 8.895 s |
| Handwriting | 13.912 s |
| Simplification | 3.988 s |

## Profile evidence

The full baseline profile is stored in `build/upd12-block4-before-profile.json`.
Under `cProfile` it recorded:

| Function/counter | Baseline |
|---|---:|
| `build_centerline_paths()` | 40 calls / 13.465 s cumulative |
| `_dedupe()` | 7,280 calls / 4.158 s cumulative |
| point equality | 7,126,592 calls |
| list append | 7,141,152 calls |

The final short-corpus profile is stored in
`build/upd12-block4-final-profile.json`. Local template lookup, scale and dedupe take
only 0.067 s, while page-space point materialization takes 0.524 s of the 0.594 s
profiled build stage. This identifies output `Point` allocation as the remaining
bottleneck.

## Root cause

Every glyph occurrence repeated font-unit scaling and dedupe for the same character
and scale. Repeated page structures additionally recreated identical immutable
page-space points even when character, scale, x and baseline were all equal.

## Changes

1. Added an ephemeral per-run `CenterlinePathTemplateCache` keyed by exact
   `(font SHA, character, scale)`.
2. A cache miss scales and deduplicates every contour once into local millimetres;
   subsequent occurrences perform translation only.
3. A second exact-position cache keyed by
   `(font SHA, character, scale, x, baseline)` reuses immutable `Point` objects for
   repeated headers/page structures. Every `PlotterStroke` still receives its own
   mutable list, so routing mutations cannot leak between occurrences.
4. Cache state remains in memory only and is shared across all pages of one pipeline
   run. It is not serialized into `paths.json` or persistent font cache files.
5. Per-page performance rows expose stable counters for local template hits/misses,
   positioned hits/misses, local points built and output points allocated.

Final counters over 6,820 glyph occurrences:

```text
local template hits             6,628
local template misses             192
local points built             246,701
positioned template hits         1,358
positioned template misses       5,462
output points allocated      5,719,291
```

## Pre-simplified template experiment

The block requirement to consider transformed + pre-simplified templates was tested
with a conservative split of the 0.06 mm error budget. It reduced build paths to
1.113 s, but changed connection decisions (page 1 accepted 89 instead of 58) and
document topology (5,921 instead of 6,453 strokes). The experiment failed the quality
gate and was completely removed. The accepted implementation never changes geometry
before handwriting.

## Tests

```text
make lint                         passed
pytest                            279 passed
make smoke                        passed
targeted tests                    31 passed
git diff --check                  passed
```

New tests verify translation reuse, scale-key separation, exact positioned reuse,
independent mutable stroke lists, shared immutable points and the performance-counter
schema.

## Benchmark before

| Metric | Before |
|---|---:|
| Full wall | 36.357 s |
| Build paths | 8.895 s |
| Handwriting | 13.912 s |
| Simplification | 3.988 s |

## Benchmark after

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Full wall | 36.357 s | 32.521 s | -10.6% |
| Build paths | 8.895 s | 6.724 s | -24.4% |
| Handwriting | 13.912 s | 14.429 s | +3.7% |
| Simplification | 3.988 s | 4.023 s | +0.9% |

Raw final result: `build/upd12-block4-final.json`. The handwriting and
simplification differences are single-run noise; their inputs and artifacts are
byte-identical.

The desired `<2–3 s` build target was not reached. Reaching it while preserving exact
connection semantics requires a packed/lazy internal point representation, because
the final profile attributes nearly all remaining time to millions of required
page-space `Point` objects. That architectural change is not introduced without a
separate measured design and broader handwriting API work.

## Geometry/quality comparison

All 62 production artifacts (`paths.json`, per-page and combined G-code, and plotter
previews) are byte-identical to the block 3 baseline. The directory diff contains
exactly 22 expected report/structure files whose timing and new counter fields differ.

Aggregate handwriting metrics and every per-page connection decision are exactly
equal. Stroke ordering, topology, closed/open state, semantic roles, connection IDs,
coordinates and final point count are unchanged. Maximum geometry deviation is
therefore `0.0 mm`.

## Regressions

No correctness regression was found. Exact-position reuse shares only frozen `Point`
instances and creates a fresh points list per stroke. The rejected early-simplification
experiment is not present in the final code.

## Remaining bottleneck

The final build-path profile is dominated by materializing page-space points for
unique positions. A packed/lazy representation could address this, but it affects
handwriting, collision indexing and serialization together. The next planned block is
page parallelism; it was not started here.
