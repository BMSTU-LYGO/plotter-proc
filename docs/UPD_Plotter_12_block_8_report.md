# Block 8

## Scope and measurements

- Branch: `swag`.
- Input: `input.docx`, 20 A5 pages, centerline mode, safe connections, hybrid layout.
- Warm font cache: 122 hits, 0 misses.
- Block 9 was not started.

The first nominal warm run found 80 missing font shards and was used only to warm the
cache. The following fully warm run is the valid block baseline:

| Cost | Time | Share of 23.959 s wall |
|---|---:|---:|
| all preview work | 589.306 ms | 2.46% |
| per-page path JSON serialization | 838.224 ms | 3.50% |
| report serialization | 0.764 ms | 0.003% |

JSON serialization remains below the plan's 5–10% intervention threshold. Public path,
job and report formats were therefore left unchanged; no version bump or compact-format
compatibility risk was introduced.

Raw baseline: `build/upd12-block8-warm-baseline.json`.

## Artifact levels

Added `--artifacts normal|debug|audit` and the matching `PipelineOptions.artifact_level`
API. The default is `normal`.

### normal

Normal runs retain production artifacts:

```text
output.gcode
plotter-preview.svg
report.json
job.json
paths.json (or per-page paths.json for multipage jobs)
```

They no longer extract font outlines, build centerline preview data, or write
`font-preview.svg` / `centerline-font-preview.svg`. Existing explicit debug flags remain
valid in normal mode, so this is not a loss of CLI control.

### debug

Debug enables the existing connection, layout, semantic, LaTeX/math and image debug
collection paths and adds both font previews. A subsystem writes an artifact only when it
has applicable source data; debug mode does not enable handwriting connections or alter
production geometry merely to create a debug file.

### audit

Audit includes debug artifacts and additionally supplies `centerline-debug/` to cold
glyph compilation. Cached glyph hits do not rebuild large centerline intermediate data.

The report records `artifact_level`, preview cache hits/misses, and paths of debug
directories that were actually created.

## Reusable font preview cache

Added an atomic SHA-256 preview cache under the configured centerline cache directory.
The identity includes a preview schema version and all output-affecting inputs.

Outline preview identity includes:

```text
font SHA, page dimensions, border option,
glyph char/name/index, position, baseline and scale
```

Centerline preview identity includes:

```text
font SHA, complete centerline config fingerprint, requested character set
```

On a hit, the exact cached SVG is copied into the requested output directory. On a miss,
the preview is rendered to a temporary file and atomically published before copying.

Two identical debug runs on `mixed_layout_demo.docx` produced:

| Run | Preview cache | Preview stage |
|---|---:|---:|
| first | 0 hits / 2 misses | 187.075 ms |
| second | 2 hits / 0 misses | 105.391 ms |

Both outline and centerline preview SVGs were byte-identical between runs.

## Disabled debug audit

The pipeline now resolves effective debug flags once. In normal mode, unless an explicit
debug flag is provided:

- connection routing receives `collect_debug=False`;
- layout receives no debug directory;
- semantic debug stroke aggregation/export is skipped;
- LaTeX/math receives no debug directory;
- image preprocessing receives no debug path;
- centerline compilation receives no debug directory;
- font preview glyph lists and exact outlines are not built.

This prevents large intermediate debug structures from being constructed and discarded.

## Performance and regression proof

| Fully warm run | Wall | Preview stage |
|---|---:|---:|
| before, previews always enabled | 23.959 s | 589.306 ms |
| normal artifact level | 21.354 s | 269.847 ms |

Normal wall improved by 10.9%; preview work decreased by 54.2%. The wall difference also
contains normal run-to-run variation in parallel handwriting and serialization, so only
the directly measured preview-stage reduction is attributed to artifact suppression.

Sixty-three production artifacts were compared byte-for-byte between baseline and normal:

```text
combined G-code and preview
job manifest
20 page path JSON files
20 page G-code files
20 page plotter previews
```

Differences: `0`.

Artifacts:

- `build/upd12-block8-warm-baseline.json`
- `build/upd12-block8-normal.json`
- `build/upd12-block8-debug-first/`
- `build/upd12-block8-debug-second/`

## Verification

```text
make lint          passed
pytest             293 passed
make smoke         passed
git diff --check   passed
```

New tests cover exact cache materialization, fingerprint invalidation, normal artifact
contents, debug artifact activation, preview cache counters and CLI parsing.
