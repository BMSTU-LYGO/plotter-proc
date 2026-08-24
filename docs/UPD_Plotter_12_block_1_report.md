# Block 1

## Baseline

- Branch: `swag`.
- Base HEAD: `c72c2f2510d4abb7be8e49e5c6116e906f4facab`.
- Audited HEAD from the plan: `47524e25b0ec3634c4460df001e3d52f10a72ce0`.
- Python: 3.12.3.
- CPU: AMD Ryzen 5 5500U, 6 cores / 12 threads.
- RAM: 14 GiB.
- Existing untracked `UPD_Plotter_12.md` was not modified.

The branch already had aggregate `StageTimings` and a cold/warm conversion benchmark,
but no cProfile mode, function TOP-20, per-page metrics, or per-glyph compiler timings.

Audited warm baseline:

```text
median              61.858 s
font_compile         ~1.5 s
build_paths           8.6 s
handwriting          27.8 s
simplification       20.2 s
```

Current single warm baseline run on HEAD `c72c2f2`:

```text
wall                 66.826 s
font_compile          2.575 s
build_paths           8.390 s
handwriting          27.959 s
simplification       20.446 s
```

Raw result: `build/upd12-block1-before.json`.

## Profile evidence

The new stage profiler was exercised on `examples/benchmark_50_words.txt` for the
`handwriting` stage. Its leading cumulative entries were:

| Function | Calls | Self | Cumulative |
|---|---:|---:|---:|
| `route_words()` | 1 | 0.009 s | 3.958 s |
| `_connection_candidate()` | 256 | 0.009 s | 3.164 s |
| `_collision_points()` | 242 | 1.367 s | 3.130 s |
| built-in `min` | 3,406,473 | 1.156 s | 1.274 s |
| built-in `max` | 2,501,727 | 0.912 s | 1.107 s |

This confirms that block 2 should start with collision/cheap-rejection work.

A real cold compile of glyph `.` produced:

| Glyph stage | Time |
|---|---:|
| render | 16.840 ms |
| mask | 106.664 ms |
| label/components | 37.641 ms |
| distance transform | 529.416 ms |
| candidate 1 | 1,042.713 ms |
| candidate 2 | 422.971 ms |
| spur pruning | 128.056 ms |
| graph build | 57.694 ms |
| graph simplify | 0.549 ms |
| routing | 0.659 ms |
| smoothing | 0.761 ms |
| quality | 895.210 ms |
| serialization | 0.014 ms |
| total measured glyph work | 4,184.690 ms |

The function profile also recorded eight EDT calls with 1.780 s cumulative time. This
supports the shared-preprocessing and pruning hypotheses reserved for block 6.

Raw profiles:

- `build/upd12-block1-profile-smoke.json`
- `build/upd12-block1-profile-smoke-run-000.prof`
- `build/upd12-block1-cold-one.json`
- `build/upd12-block1-cold-one.prof`

## Root cause

The old report aggregated all 20 pages into stage totals. It could not correlate runtime
with glyphs, point count, or connection candidates, and it could not distinguish variation
from word routing. The cold compiler similarly exposed only total font compilation time, so
repeated EDT, candidate selection, pruning, and quality costs were invisible.

## Changes

1. `tools/benchmark_conversion.py` now supports:

   ```bash
   --profile
   --profile-stage handwriting
   --profile-stage simplification
   --profile-stage build_paths
   --profile-stage font_compile
   --profile-top N
   ```

   It writes standard `.prof` data and embeds a cumulative TOP-N function list in JSON.
   Every row contains function, calls, primitive calls, self time, cumulative time, and
   self time per call. The default and minimum list size is 20.

2. The normal performance report now contains `performance.pages`, with one deterministic
   row per page and all required fields:

   ```text
   page, glyph_count, stroke_count_before, point_count_before,
   candidate_pairs, accepted_connections,
   build_paths_ms, variation_ms, word_routing_ms, simplification_ms,
   serialization_ms, preview_ms, gcode_ms
   ```

3. `tools/profile_centerline_font.py` provides isolated cold profiling with a temporary
   cache and supports one glyph, ten glyphs, the full corpus, or an explicit glyph string:

   ```bash
   .venv/bin/python tools/profile_centerline_font.py \
     --font assets/1.ttf --glyph-count 1

   .venv/bin/python tools/profile_centerline_font.py \
     --font assets/1.ttf --glyph-count 10

   .venv/bin/python tools/profile_centerline_font.py \
     --font assets/1.ttf --glyph-count all
   ```

4. Cold glyph instrumentation records render, mask, labeling, EDT, both candidates, spur
   pruning, graph build/simplify, routing, smoothing, quality, serialization, and total time.
   Collection is activated only by the audit tool. `cProfile` and `pstats` are Python stdlib;
   no runtime dependency was added.

## Tests

```text
make lint                         passed
pytest                            271 passed
make smoke                        passed
targeted tests                    22 passed
git diff --check                  passed
conversion profile smoke          passed
cold one-glyph profile            passed
```

New unit coverage checks stage-selective profiling, required TOP-list fields, the complete
per-page schema, and the complete per-glyph schema.

## Benchmark before

One unprofiled warm run:

| Metric | Before |
|---|---:|
| Full wall | 66.826 s |
| Font compile | 2.575 s |
| Build paths | 8.390 s |
| Handwriting | 27.959 s |
| Simplification | 20.446 s |

## Benchmark after

One unprofiled warm run:

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Full wall | 66.826 s | 67.240 s | +0.62% |
| Font compile | 2.575 s | 2.571 s | -0.16% |
| Build paths | 8.390 s | 8.940 s | +6.56% |
| Handwriting | 27.959 s | 27.948 s | -0.04% |
| Simplification | 20.446 s | 20.359 s | -0.42% |

Block 1 adds observability rather than an optimization. The 0.62% wall difference is within
single-run noise; stage variation, especially build paths, is also visible between the two
runs. No performance target is claimed from this block.

Raw result: `build/upd12-block1-after.json`.

## Geometry/quality comparison

All 62 generated `paths.json`, G-code, and `plotter-preview.svg` artifacts from the before
and after full-document runs are byte-identical. Aggregate values also remained identical:

```text
strokes       6,453
points      111,714
glyphs        6,820
pages            20
```

Therefore maximum geometry deviation is exactly `0.0 mm`; connection policy and output
semantics were not changed.

## Regressions

No correctness regression was found. Normal runs now execute only lightweight per-page
`perf_counter` measurements. Function and per-glyph profiling remain opt-in audit paths.

## Remaining bottleneck

The first measured targets for the next blocks are:

1. handwriting collision work (`_collision_points`, built-in min/max loops);
2. simplification at 20.359 s on the full document;
3. build-path allocation at 8.940 s;
4. cold glyph candidate/EDT/quality work, with repeated EDT visible in the profile.

Block 2 must use the generated per-page and function data before changing connection logic.
