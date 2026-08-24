# Block 5

## Baseline

- Branch: `swag`.
- Base HEAD: `c72c2f2510d4abb7be8e49e5c6116e906f4facab`.
- Input: `plotter_pipeline_full_test.docx`, 20 A5 pages, normal size,
  centerline font, safe connections, hybrid layout, one warm run.
- Block 4 baseline: `build/upd12-block4-final.json`.

| Metric | Baseline |
|---|---:|
| Full warm wall | 32.521 s |
| Build paths | 6.724 s |
| Handwriting | 14.429 s |
| Simplification | 4.023 s |

## Root cause

After pagination, the 20 pages were processed sequentially even though handwriting,
simplification, validation and per-page artifact generation do not require another
page's mutable state. These stages contain substantial Python loops, so threads would
remain constrained by the GIL.

The existing cross-page simplification cache was the main determinism hazard. If each
worker populated missing templates in its own completion order, one closed glyph on
page 8 selected a different valid RDP index set. Therefore templates are now primed
in page/stroke order after applying the same travel orientation as page processing.

## Changes

1. Extracted a module-level, pure-ish `process_page()` boundary. It receives an
   explicit `PageProcessRequest` and returns `PageProcessResult`; it does not mutate
   pipeline-global warnings, reports, jobs or timing structures.
2. Added `ProcessPoolExecutor` page workers. Large raw path documents are inherited
   through Linux `fork` copy-on-write and jobs submit only page indices, avoiding
   repeated serialization of millions of source points.
3. Added `--workers auto`, `--workers N` and `--workers 1` to the CLI and benchmark
   tool. `workers=1` remains the deterministic sequential reference.
4. The automatic policy is `min(cpu_count, 4, page_count)`. On the 12-core benchmark
   host, four workers reached approximately 4.98 GiB peak aggregate process-tree RSS;
   using all 12 cores would be unsafe for the current large path representation.
5. Worker completion order cannot affect output. Results, page jobs, reports,
   warnings and merged timing rows are sorted by `page_index` in the main process.
6. Workers write only their own `pages/page-XXX/` artifacts. Combined G-code, root
   preview, `job.json` and root `report.json` remain main-process outputs.
7. Added deterministic simplification-cache priming and worker timing merge support.
   CPU stage totals in a parallel report are sums across workers; full wall remains
   the latency metric.

## Regression matrix

| Workers | Warm wall | Change from workers=1 | Artifact differences |
|---:|---:|---:|---:|
| 1 | 32.068 s | reference | 0 |
| 2 | 24.491 s | -23.6% | 0 |
| 4 | 19.975 s | -37.7% | 0 |

Artifacts:

- `build/upd12-block5-final-workers1.json`
- `build/upd12-block5-final-workers2.json`
- `build/upd12-block5-final.json`
- RAM measurement run: `build/upd12-block5-memory.json`

All 62 production artifacts (`paths.json`, per-page and combined G-code, and plotter
previews) are byte-identical across workers 1, 2 and 4. Aggregate and per-page
statistics, warnings, connection metrics, semantic metrics, stroke ordering and
topology are equal. Maximum geometry deviation is `0.0 mm`.

## Benchmark result

| Metric | Block 4 | Block 5 | Change |
|---|---:|---:|---:|
| Full warm wall | 32.521 s | 19.975 s | -38.6% |

The block requirement `<= 30 s` and target `<= 20–25 s` are both met. The final
default is `auto`, which resolves to four workers for this 20-page workload.

## Tests

```text
make lint                         passed
pytest                            282 passed
make smoke                        passed
workers 1/2/4 artifact matrix     passed
git diff --check                  passed
```

New tests cover CLI default/override parsing, the automatic worker cap, page-count
bounding and merging worker timings into the performance report.

## Remaining bottleneck

Raw centerline path construction remains sequential because it uses the shared cache
from block 4 and materializes millions of `Point` objects. It takes roughly 6.3 s in
the final run. Cold centerline compilation also remains unchanged. Both belong to
later blocks; block 6 was not started.
