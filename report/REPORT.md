# plotter-proc quality audit

## 1. Environment and exact HEAD

- Audit date: 2026-08-21 (Europe/Moscow); command logs use UTC.
- Branch: `master`.
- HEAD: `708cd7ac734bd57088e4590700a56e1f39062a51` (`Merge pull request #6 from BMSTU-LYGO/upd/plotter-7-layout-math-lines-tables`).
- Initial working tree: dirty only because the supplied `plotter_pipeline_full_test.docx`, `plotter_pipeline_full_test.pdf`, and audit prompt were untracked. The later `report/` tree is audit output.
- Python: 3.12.3 from `.venv/bin/python`.
- Font: `assets/1.ttf`, Pacifico Regular, SHA-256 `4dac9db3fa9ca072f7861fd916bf04bdceac6069d0f3a886f5e523d922e918f1`.
- Inputs: repository-root `plotter_pipeline_full_test.docx` and `plotter_pipeline_full_test.pdf`.
- Production code was not changed. Only audit utilities and artifacts were created under `report/`.

All CLI help, Git state and command metadata are in `logs/` and `commands.log`.

## 2. Current pipeline architecture

Actual flow on this HEAD:

```text
CLI (cli.py / __main__.py)
  -> PipelineOptions / run_pipeline (pipeline.py)
  -> read_structured_document (structured_document_reader.py)
       -> DOCX: docx_document_reader.py
       -> PDF: pdf_document_reader.py + pdf_math_detector.py
       -> TXT: SourceParagraph construction
  -> SourceDocument / Source*Element models (document_models.py)
  -> paginate_document (document_paginator.py)
       -> PageTransform (layout_models.py)
       -> paragraph shaping/layout (paragraph_layout.py, text_shaper.py)
       -> LaTeX/OMML layout (latex_layout.py, latex_renderer.py, omml_parser.py)
       -> tables (table_layout.py)
       -> image preprocess/vectorize/rotation/wrap (image_*.py, document_paginator.py)
       -> semantic lines/arrows (shape_layout.py)
  -> TTF load + centerline compile/cache (font_loader.py, centerline_font/*)
  -> outline or centerline path build (path_builder.py / centerline_path_builder.py)
  -> optimize travel (path_optimizer.py)
  -> variation and word routing (handwriting.py)
  -> simplification (path_simplifier.py)
  -> validation + per-page paths.json + SVG preview
  -> per-page G-code (gcode_exporter.py)
  -> multi-page job/G-code (multipage_gcode_exporter.py)
  -> report/debug exports (pipeline.py, layout_debug.py, semantic_debug.py)
```

Key data boundaries:

- Readers output `SourceDocument` containing provenance-bearing text, math, raster, vector, line, arrow and table elements.
- Pagination outputs page layouts containing glyph placement, graphic strokes, source element IDs and layout metadata.
- Font compilation converts requested Unicode characters to cached `CompiledCenterlineFont` glyph routes.
- Path builders output `PathDocument`; image, math, table and semantic strokes are appended to text strokes.
- Optimized/simplified `PathDocument` is the source of `paths.json`, preview, motion statistics and G-code.

Fallback/warning points observed:

- DOCX reader approximates unsupported tab-stop kinds and underline styles, and partially supports OMML/wrap modes.
- PDF reader conservatively reports low-confidence math and rasterizes complex drawings.
- LaTeX can fall back to outline unless strict centerline quality forbids it.
- Centerline compilation marks low-coverage/topology glyphs `needs_review`; routing has minimum-strokes fallback.
- Image preprocessing can return blank/no-strokes warnings.
- Pagination records placement fallbacks, overlap and overflow, but several semantic metrics are not actually measured.

Coordinate transformations occur in `PageTransform`, paragraph/table layout, raster placement, `_rotated_size()` / `_rotate_image_point()`, machine origin/inversion in G-code, and page-change parking. The same underlying raster is vectorized once per image-mode/edge key and then independently placed for its three DOCX instances.

Architecture hotspots:

| File/function | Why risky | Observable defect | Confirming test |
|---|---|---|---|
| `document_paginator.py::paginate_document` (2163-line module) | Pagination, paragraph/table/image/math/semantic placement and coordinate transforms share mutable page state | Late layout changes can alter page breaks, exclusions or object coordinates across unrelated element types | Mixed DOCX with tables, anchored image, rotation and A4/A5 transform |
| `centerline_font/route_assembler.py::assemble_component_route` | Requires exact float equality at adjoining smoothed edges | PDF math pipeline aborts on a 0.041667-unit endpoint mismatch | Current control PDF with `--pdf-math auto` |
| `docx_document_reader.py::add_arrow` | Receives one `<w:pict>` but only reads `lines[0]` | Three VML arrows in one pict become one semantic arrow | Current control DOCX; source XML contains 3 `<v:line>` nodes |
| `handwriting.py::route_words` | 805-line module; collision/tangent checks run over 5747 pairs across 20 pages | 68.4 s of a 126.6 s successful job | Current DOCX safe-connections run |
| `path_simplifier.py` call per page | Traverses already large routed geometry | 41.5 s of the same job | Current DOCX run with default machine config |
| `pdf_document_reader.py` + PDF math suppression | Text/vector absorption and visual math reconstruction are format-specific | Duplicate/missing primitives are possible; current run fails before dedup can be verified | PDF preserve/reflow control after F-001 is fixed |

Searches for `TODO`, `FIXME`, `HACK`, `NotImplemented`, `fallback`, warnings, broad exceptions and silent failures were performed. Broad exceptions in reader/cache/serializer paths generally convert dependency/decode failures into contextual warnings or typed errors; they were not counted automatically as defects.

## 3. Baseline tests/lint/smoke

| Command | Result | Duration/evidence |
|---|---|---|
| `make lint` | Initial run failed only on the newly added audit logger; audit tool was made lint-clean. Final rerun passed. | `logs/make-lint.log`, `make-lint-final.log`, `make-lint-post-analysis.log` |
| `make test` | 239 passed, 0 failed, 0 skipped | pytest 9.46 s; wrapper 10.24 s |
| `make smoke` | Passed | `build/manual-smoke/report.json`; wrapper 24.6 s |

Smoke differs from pytest: it executes `tools/smoke_full_pipeline.py` against `tests/fixtures/layout/mixed_layout_demo.docx` and produces a real pipeline job with layout debug; it is not simply another test selection.

## 4. Test document coverage

The DOCX contains Cyrillic/Latin/digits/punctuation, paragraph roles and alignments, indents/tabs/spacing, run formatting, literal LaTeX, OMML, three raster placements (including 12° rotation and square wrap), three VML arrow lines, a coverage-map table, a merged-cell table, and a long repeated-header table. The generated PDF contains the same visible document on four source pages.

The successful DOCX A5 job reports 45 text elements, 1 OMML math element, 3 rasters, 3 semantic tables/104 logical cells, 6 underline strokes, and only 1 arrow. It became 20 A5 pages.

## 5. DOCX import results

`extract` succeeded but is not a faithful structural extraction:

- It emitted 47 lines and preserved Cyrillic, `ё/ъ/ь/ы`, punctuation, tabs and literal LaTeX tokens.
- It omitted all table cell text from both substantive tables and the coverage-map table.
- It emitted the OMML introduction but not the OMML expression itself.
- The structural run does import OMML and tables: the successful job renders 4 formulas (3 literal LaTeX + 1 OMML) and reports 104 table cells. Therefore the loss is in the `extract` projection (`document_reader.py`), not the structural reader.

Artifacts: `analysis/docx-extracted.txt`, the job's `document-structure.json`, and `extracted-assets/`.

## 6. PDF import results

`extract` succeeded with 285 visual-order lines. It includes table cells and the visually reconstructed OMML expression, but naturally fragments text according to PDF line geometry. Near the anchored image, individual words become narrow single-word lines; footer text is interleaved at source-page boundaries.

Both full PDF jobs failed before path/G-code output:

```text
Source page 1, source element 'page-001-math-001':
Non-adjacent route jump at edge 20:
Point(x=52.0, y=1.75) != Point(x=52.0, y=1.7916666666666665)
```

The identical preserve/reflow failure localizes the blocker below PDF layout mode, in centerline route assembly for the first reconstructed visual formula. PDF math suppression, deduplication, arrows, tables and preserve-vs-reflow quality could not be evaluated downstream and are marked not tested rather than assumed correct.

## 7. Layout and A4/A5 results

A5 hybrid completed in both centerline and outline with 20 pages. The reported A4-source to A5 `PageTransform` is:

- source 210.008611 × 297.003611 mm;
- source content rect 174.025278 × 264.00125 mm;
- target content rect 128 × 182 mm;
- uniform scale 0.689391;
- offset (1.611011, -1.029198) mm.

No A5 object overflow or remaining overlap was reported. Centerline and outline retain the same page count, transform, paragraph-format counts, table counts and semantic counts. Small downstream vertical shifts occur because outline and centerline formula/text geometry differ; page-6 inline image Y differs by about 0.214 mm.

The requested A4 reference failed during machine-coordinate validation at `X25.835 Y290.448`: `configs/machine.yaml` limits Y to 220 mm while portrait A4 plus origin requires more. The CLI exposes `--page A4`, but the default machine config cannot produce that page. No A4-vs-A5 visual comparison is therefore claimed.

## 8. Typography and paragraph formatting

The structural report exposes 149 paragraphs, 1 title, 9 headings, 6 first-line indents, 5 centered, 1 right-aligned, 6 justified and 1 custom-tab paragraph. The document structure preserves numeric first-line/hanging/left/right indents and semantic role instead of replacing them with spaces.

The importer warns `docx_tab_stop_approximated:center` and `docx_tab_stop_approximated:right`. Actual tab positions are retained numerically, but alignment semantics for those two stop kinds are approximated. Bold/italic/strike/super/sub metadata is present in the structural input, while this audit has no raster renderer to make a reliable human visual judgment. Underlines are separately covered in section 15.

## 9. Centerline glyph quality

The font covers all 125 unique non-whitespace characters emitted by DOCX extraction; the focus characters `ъ ь ы й ё . : ; ?` all exist in the TTF. No fallback font was required.

The compiled cache contains 169 glyphs: 157 auto-passed and 12 `needs_review`. The current `report.json` leaves `centerline.worst_glyphs` empty, so `analysis/worst-glyphs.json` derives the required ranking from the actual cache. Worst 10:

| Glyph | Coverage | Method | Components | Before/after routes | Retrace | Warning |
|---|---:|---|---:|---:|---:|---|
| `;` | 0.609078 | medial_axis | 2 | 2/2 | 0 | low mask coverage |
| `.` | 0.632283 | skeletonize | 1 | 1/1 | 0 | low mask coverage |
| `…` | 0.632771 | skeletonize | 3 | 3/3 | 0 | low mask coverage |
| `:` | 0.635286 | skeletonize | 2 | 2/2 | 0 | low mask coverage |
| `?` | 0.678169 | medial_axis | 2 | 6/2 | 0 | low mask coverage |
| `Щ` | 0.884182 | skeletonize | 1 | 5/1 | 0.228439 | needs review |
| `Ц` | 0.865277 | skeletonize | 1 | 3/1 | 0.168092 | needs review |
| `Ш` | 0.919697 | skeletonize | 1 | 5/1 | 0.256257 | needs review |
| `U` | 0.914971 | skeletonize | 1 | 3/1 | 0.188806 | needs review |
| `И` | 0.914971 | skeletonize | 1 | 3/1 | 0.188806 | needs review |

The main report also flags `Й`, `Ю`, plus the listed glyphs. `fallback_glyphs` reports `*`, `+`, `Ж`. Separate per-glyph SVGs are not emitted by the production run; the whole `centerline-font-preview.svg` and derived JSON are supplied for review.

## 10. Glyph routing and pen lifts

Across 169 compiled glyphs: 204 connected components, 680 graph edges/routes before consolidation, 204 routes after, and 476 internal pen lifts saved. The report claims `one_stroke_per_component` and the cache confirms one route per component for focus lowercase `ъ/ь/ы/ж/щ/ф` where compiled. Diacritics and disconnected marks still require physical lifts. Exact focus metrics are in `analysis/worst-glyphs.json`.

The aggregate report's `retraced_length_mm` is 0 even though individual cached glyphs such as `Щ/Ш/Ц` have non-zero retrace ratios. This is an observability inconsistency, not evidence that the routes contain no retrace.

## 11. Word connections

The unchanged stress corpus is in `analysis/connection-corpus.txt`.

| Mode | Pairs | Accepted | Rejected | Pen lifts/strokes | Connector draw |
|---|---:|---:|---:|---:|---:|
| off | 510 | 0 | 510 | 634 | 0 mm |
| safe | 510 | 105 | 405 | 529 | 108.705 mm |
| aggressive | 510 | 105 | 405 | 529 | 108.705 mm |

Safe rejection leaders are tangent mismatch 192, collision 109, distance 29, backward motion 27, anchor-not-routeable 22, punctuation 20. Safe saves 105 lifts without maximizing acceptance. Aggressive changes some rejection labels/threshold outcomes but produces byte-identical preview, G-code and path geometry to safe on this corpus. This does not prove aggressive is generally redundant, but this control input does not distinguish its output.

Connection-debug SVG/JSON exists for each single-page control. The multi-page primary job has page-level debug JSON. The schema does not expose enough ranked geometric risk fields to objectively select “10 most suspicious” accepted and rejected pairs without inventing a score; human review is required.

## 12. LaTeX / OMML / PDF math

DOCX strict centerline math passed:

- 4 expressions: 2 inline, 2 block;
- provenance: 3 `semantic-latex`, 1 `omml`;
- 40 centerline strokes, 431 points, 40 pen lifts;
- 0 outline fallbacks and 0 `needs_review` formulas;
- coverage ratios 0.842760–0.945704; retrace ratios 0.122719–0.188255.

Fraction, superscript/integral/baseline/clipping require human preview review. PDF `--pdf-math auto` identifies candidates and emits low-confidence warnings, but the first visual formula triggers F-001 before suppression/dedup metrics can be trusted.

## 13. Images and vectorization

Three source image instances were found and vectorized into 95 strokes / 391 points. The repeated raster produced 2 in-process image-cache hits and 1 miss. Modes and placement are preserved in `document-structure.json`; preprocessing images are in `image-debug/`.

The report does not expose thin-line survival, grayscale block behavior, micro-strokes, spurs, double contours, pen lifts per image, or geometry drift. Therefore disappearance/merging quality is not asserted automatically. Open the extracted raster beside page 6 in `visual-index.html`.

## 14. Rotation and wrapping

Rotation is fixed on current HEAD relative to `docs/update-7-block-2-report.md`:

- source `page-001-image-025` has `rotation_deg: 12.0`;
- `document_paginator.py` computes a rotated AABB and calls `_rotate_image_point()` for every vectorized stroke point;
- output contains 29 strokes for the rotated element;
- their measured bounds are approximately X 56.011–92.012, Y 158.031–178.407 mm, which is not the unrotated raster geometry.

The anchored raster retains source bbox, `anchor=anchored`, `wrap_mode=square`, 3 mm left/right and 2 mm top/bottom distances. It is mapped to page 7 with 0 displacement, 0 overlap and 0 overflow. Automated metrics do not detect aesthetically poor narrow columns, so page 7 remains a human-review target.

## 15. Tables / arrows / underlines

Tables: three semantic tables (including the coverage map), 104 logical cells, two merged cells in the merge-test table, one repeated-header row per table, and 14 produced table pages. Auto-height was applied to 31 rows. The long table splits across pages, but shared-border deduplication, text/border intersections, row-only splitting and actual header repetition are not explicitly counted in `report.json`; use table debug and pages 8–18.

Arrows: source XML contains three VML `<v:line>` nodes (one-headed, two-headed, classic), while the job reports/renders one arrow. `add_arrow()` selects only `lines[0]` from the enclosing pict, confirming a real import bug. The optimizer preserves semantic arrow direction for the one imported object.

Underlines: six semantic underline strokes are reported, covering single/double/words-only construction. Vertical offset, words-only gaps and absence of glyph duplication require human SVG review. PDF duplicate-rendering could not be tested.

## 16. Pagination

The primary job has 20 page directories, page reports, `paths.json`, per-page previews/G-code, root job manifest, root preview and combined G-code. Page numbers are enabled; 19 page changes use `pause_seconds=1` and park `top_right`.

Independent combined-G-code inspection found exactly 19 `G4 P1000` page waits. Each sampled transition raises Z, parks (`X153 Y215` for this config), issues `M400`, waits, then starts the next page with Z up. Final motion is `G0 Z5`; job ends with `M400`, `M84`.

## 17. G-code safety

The audit scanned 67 generated G-code files independently. Results:

- no `M104/M109/M140/M190/G28`;
- no extrusion `E` moves;
- no NaN/Infinity;
- no XY outside configured 0–220 mm workspace;
- Z values match the selected safe/balanced profiles;
- successful jobs end with pen up.

The A4 job is correctly blocked rather than emitting unsafe coordinates. Full results are in `summary.json`.

Re-running the `gcode` subcommand from `connections-safe/paths.json` produces functionally identical non-comment commands, but not byte-identical output because the full run adds page/motion/estimate comments that the subcommand does not reconstruct.

## 18. Cache behaviour

`make font-cache-status FONT=assets/1.ttf` reports a valid canonical entry in `1-font-cache`, algorithm version 6, 169 glyphs, 18,341,377 bytes. The main jobs had 122 hits / 0 misses. Cache identity includes font hash, algorithm version and configuration fingerprint; writes use atomic replacement and metadata. Partial hits are covered by tests and observed warm runs reuse the same entry.

`make clean` was not executed because it destructively replaces user `build/` artifacts. Makefile inspection verifies it only removes `$(BUILD)`, while `cache-clean` separately removes `$(CACHE_DIR)`. `make cache-clean` was not executed. The interrupted benchmark used `TemporaryDirectory` and did not delete or overwrite canonical cache.

## 19. Performance

Successful primary centerline A5 wall/stage total: 126.564 s. Top three stages:

1. handwriting: 68.382 s (54.0%);
2. simplification: 41.468 s (32.8%);
3. build paths: 8.933 s (7.1%).

Layout was 1.921 s, LaTeX 1.523 s, font compile 1.474 s (warm cache), G-code 2.706 s, and image vectorization 0.303 s. The repeat was 126.815 s, confirming this is not a one-off cold-cache cost.

The isolated `tools/benchmark_conversion.py` cold+3-warm run did not complete run 0 after approximately 12 minutes and was interrupted; only extraction/document-structure partial artifacts exist. This is recorded as incomplete, not converted into invented cold/warm numbers. The long cold compilation plus full conversion is itself performance evidence, but precise cold/warm median remains unavailable.

For the representative connection job, balanced changes estimated job time from 901.627 s to 389.484 s, a theoretical 56.8% reduction. Geometry and lift count stay at 529. This is a static estimate only; physical calibration is still required.

## 20. Determinism

Two identical primary DOCX jobs with the same warm canonical cache produced byte-identical root `output.gcode` and `plotter-preview.svg`. Page `paths.json` is not byte-identical because image strokes embed job-local `source_path` strings. After removing only `source_path`, every page path document is equal; geometry is deterministic.

`report.json` differs only in `outputs` paths and `performance` timings. This is a provenance serialization issue, not nondeterministic geometry.

## 21. Documentation vs implementation

| Claim | Current implementation | Verified by | Status |
|---|---|---|---|
| DOCX raster rotation is preserved | Per-point rotation around rotated bbox is implemented and 12° strokes are present | source metadata, paths, paginator code | verified; old update-7 note is outdated |
| Uniform A4/A5 `PageTransform` | A5 transform is uniform and reported | report/layout debug | partially verified; A4 output blocked by machine workspace |
| Persistent cache outside build | Canonical `1-font-cache`; clean/cache-clean are separate | Makefile, cache status, warm hits | verified (README uses current path; parts of UPD mention older `.plotter-cache`) |
| Paragraph semantics/geometry | Roles, alignments and numeric indents persist | document structure/report | verified; center/right tabs approximated |
| Repeated table header | Source model records one header row and table spans pages | document structure | partially verified; actual repeated output lacks explicit metric |
| Basic OMML | One OMML expression imports/renders centerline | formula provenance | verified for fixture |
| PDF visual math suppression | Detector runs | error report | not reproducible downstream because F-001 blocks both jobs |
| Semantic deduplication metrics | Report fields exist | `pipeline.py` | outdated/insufficient: conflict/suppression fields are hard-coded zero |
| Word connections | off/safe/aggressive CLI and metrics work | three controls | verified; aggressive indistinguishable on this corpus |
| One route per component | 204 components -> 204 routes | cache/report | verified, with retrace on some glyphs |
| Safe G-code | No heat/home/extrusion/nonfinite/out-of-range commands | independent scan | verified for successful jobs |
| Deterministic output | Geometry/G-code/preview stable | repeat hashes | partially verified; `paths.json` bytes vary by provenance path |

## 22. Ranked findings

Counts: **P0 1, P1 5, P2 5, P3 2** (13 total).

### F-001 — P0 BUG — PDF math centerline route aborts both layouts

- Observed: preserve and reflow fail on `page-001-math-001`, edge 20, endpoint delta 0.041667.
- Expected: visual math yields a valid continuous route or a controlled formula fallback; the PDF job completes.
- Reproduction: commands in `logs/job-pdf-centerline-preserve-a5.log` and `job-pdf-centerline-reflow-a5.log`.
- Evidence: both error `report.json` files and `latex-debug/` partial artifacts.
- Likely root cause: smoothed edges that share a graph node no longer have byte-equal endpoint coordinates; `route_assembler.py` uses exact `Point` equality.
- Files: `centerline_font/edge_geometry.py`, `stroke_smoother.py`, `route_assembler.py`; PDF math raster path feeds this code.
- Confidence: high. Direction: normalize shared-node endpoints before assembly and retain strict topology validation; do not merely add a broad tolerance that can bridge real gaps.
- Regression: the exact control PDF in preserve/reflow plus a unit route whose adjacent endpoint coordinates differ only by smoothing quantization.
- Risk/effort: medium / M.

### F-002 — P1 BUG — module entrypoint reports process success for failed jobs

- Observed: A4/PDF commands print `Error:` and write `status:error`, but shell exit code is 0.
- Expected: failed pipeline returns non-zero.
- Reproduction: any failing `python -m plotter_processor run ...` command above.
- Root cause: `__main__.py` calls `main()` without `raise SystemExit(main())`; `_run()` correctly returns 1 but it is discarded.
- Files: `src/plotter_processor/__main__.py`, `cli.py::_run`.
- Confidence: high. Regression: subprocess test for a known invalid run via `python -m`.
- Risk/effort: low / S.

### F-003 — P1 BUG — three source VML arrows collapse to one

- Observed: XML has 3 `<v:line>` nodes; import/report/debug has 1 arrow.
- Expected: three semantic arrows with correct head/tail/style.
- Reproduction: successful DOCX jobs; inspect `semantic-debug/arrows.svg`.
- Root cause: `docx_document_reader.py::add_arrow()` queries all lines but reads only index 0 and returns a single element.
- Confidence: high. Direction: emit each line with stable order/IDs; preserve per-line stroke metadata.
- Regression: one pict containing one-headed, two-headed and classic VML lines; assert 3 arrows and no raster duplicate.
- Risk/effort: low / S.

### F-004 — P1 BUG/CONFIGURATION — advertised A4 conflicts with default 220 mm workspace

- Observed: portrait A4 job reaches Y290.448 and is rejected.
- Expected: supported page/config combination either generates safely or fails at preflight with actionable compatibility guidance before expensive processing.
- Root cause: CLI page choices are independent of machine workspace/origin; validation occurs late.
- Files: `cli.py`, `pipeline.py`, `validator.py`, `configs/machine.yaml`.
- Confidence: high. Direction: early page-vs-workspace validation and an explicit supported A4 machine/landscape configuration; do not expand Ender workspace limits falsely.
- Regression: A4 + 220 mm machine rejects before layout/font compilation; compatible A4 config succeeds.
- Risk/effort: low / S-M.

### F-005 — P1 QUALITY LIMITATION — 12 real glyphs need review

- Observed: `.;:…?` have 0.609–0.678 coverage; `Щ/Ц/Ш/U/И/Й/Ю` are also flagged. These appear in real input.
- Expected: recognizable punctuation/caps with stable components and bounded retrace.
- Evidence: `analysis/worst-glyphs.json`, centerline preview/cache.
- Root cause: small punctuation masks and complex multi-stem topology score poorly under current candidate/routing configuration.
- Confidence: high for metrics; visual severity requires human review.
- Direction: targeted candidate/patch work only after reviewing per-glyph geometry; avoid global threshold changes.
- Regression: exact worst-10 corpus with coverage/component/retrace bounds and snapshots.
- Risk/effort: medium / M.

### F-006 — P1 PERFORMANCE BOTTLENECK — warm primary conversion takes ~126.7 s

- Observed: handwriting + simplification consume 109.85 s (86.8%); repeat is equally slow; isolated cold benchmark did not finish in audit window.
- Expected: warm cache materially reduces repeated full conversion and large stages remain bounded.
- Likely root cause: repeated geometric collision/routing and simplification traversal per page/stroke.
- Files: `handwriting.py`, `path_simplifier.py`, pipeline page loop.
- Confidence: high for stage localization. Direction: profile complexity and cache spatial queries/repeated calculations; do not optimize font compilation first.
- Regression: stage timing ceiling on fixture/representative corpus, separate from correctness tests.
- Risk/effort: medium / M-L.

### F-007 — P2 BUG — DOCX `extract` omits tables and OMML content

- Observed/expected: 47-line DOCX output lacks cell values and OMML expression that are structurally imported and visible; extract should define and meet a document-order text contract.
- Root cause: `document_reader.py` projects only top-level text paragraphs.
- Regression: extract merged/repeated-header tables and OMML in stable reading order.
- Risk/effort: medium / M.

### F-008 — P2 MAINTAINABILITY/OBSERVABILITY — `paths.json` is not byte-deterministic

- Observed: page paths differ only by output-local extracted-asset `source_path`; geometry is identical.
- Expected: deterministic serialization should use stable input-relative/content-addressed provenance.
- Files: image vectorizer/path serializer.
- Regression: identical runs in different output dirs have identical paths bytes.
- Risk/effort: low / S.

### F-009 — P2 OBSERVABILITY — key report fields are empty or hard-coded

- Observed: `centerline.worst_glyphs=[]` despite 12 flags; aggregate retrace is 0 despite glyph retrace; classification conflicts and suppressed duplicates are hard-coded 0; table/image quality metrics are absent.
- Expected: report distinguishes measured zero from unexposed metrics.
- Files: `pipeline.py::_centerline_report` and report assembly.
- Regression: schema tests populated from known conflicting/retraced fixtures.
- Risk/effort: low-medium / M.

### F-010 — P2 QUALITY LIMITATION — aggressive connections do not change this stress corpus

- Observed: safe/aggressive have identical 105 accepted, strokes, connector length and bytes, though rejection categories differ.
- Expected: if modes are user-facing, a documented corpus should demonstrate their behavioral boundary.
- Direction: add a fixture that crosses aggressive-only thresholds or document that collision/tangent guards intentionally dominate.
- Risk/effort: low / S.

### F-011 — P2 QUALITY LIMITATION — center/right DOCX tabs are approximated

- Observed: explicit warnings for center/right tab stops; positions persist but stop alignment semantics are lost.
- Expected: tabbed columns align by stop kind and decimal/center/right anchor.
- Files: `docx_document_reader.py`, paragraph/tab layout.
- Regression: center/right/decimal tabs with measured glyph bounds.
- Risk/effort: medium / M.

### F-012 — P3 MAINTAINABILITY — G-code subcommand omits full-run metadata comments

- Observed: non-comment commands are identical, bytes are not.
- Expected: either document semantic equivalence or share header generation when byte identity is desired.
- Risk/effort: low / S.

### F-013 — P3 MAINTAINABILITY — paginator concentrates too many policies

- Observed: 2163-line module owns page state, tables, images, formulas, semantic objects, rotation and debug bookkeeping.
- Expected: independently testable placement units without changing policy.
- Direction: only extract cohesive helpers after correctness regressions exist; no rewrite.
- Risk/effort: medium-high / L.

## 23. TOP-5 improvements

1. **Repair shared-endpoint normalization in centerline route assembly.** This immediately unblocks the entire PDF path and removes the only P0. Touch edge smoothing/assembly only; do not redesign PDF math detection. Add the exact PDF and quantized-adjacency tests. Expected effect: preserve/reflow reach previews/G-code. Risk M, effort M.
2. **Propagate CLI failure through `python -m`.** This prevents false-green automation and makes every future quality gate trustworthy. Change only `__main__.py`; add subprocess exit-code coverage. Expected effect: failures become machine-detectable. Risk low, effort S.
3. **Emit every VML line in a pict.** This restores two missing arrows without changing generic layout or optimizer behavior. Preserve source order/head style and add one three-arrow regression. Expected effect: 3/3 semantic arrows. Risk low, effort S.
4. **Target the real 12-glyph review set.** Start with punctuation and then high-retrace caps using per-glyph evidence/snapshots. Do not globally change thresholds or replace the centerline algorithm. Expected effect: clearer punctuation and fewer unnecessary retraces/lifts. Risk M, effort M.
5. **Add early page/workspace compatibility and a truthful A4 path.** Reject impossible configs before expensive work and provide a compatible machine/orientation config rather than enlarging physical bounds. Expected effect: predictable A4 reference behavior and no late 24 s failure. Risk low, effort S-M.

Performance work on handwriting/simplification should follow these correctness changes; it is the next candidate after TOP-5.

## 24. NOT NOW

- No centerline algorithm rewrite or global threshold tuning.
- No OCR/ML reconstruction for PDFs while deterministic visual math already exists but is blocked by one route defect.
- No full paginator rewrite; first add regressions around the confirmed failures.
- No rare Word feature expansion beyond the demonstrated VML/tab cases.
- No physical `balanced`/`fast` claim without calibration on the actual machine.
- No cache redesign; canonical cache is valid and warm hits work.
- No performance micro-optimization of font/image/LaTeX stages before the dominant handwriting/simplification costs.

## 25. Recommended regression tests

1. PDF visual math with slightly quantized adjoining edge endpoints completes in preserve and reflow.
2. `python -m plotter_processor run` returns non-zero when `report.status=error`.
3. One DOCX pict containing three VML lines yields three arrows with correct heads/styles and no duplicate generic line.
4. Impossible page/workspace combinations fail before read/layout/font compile; compatible A4 succeeds.
5. Worst-10 glyph snapshots and numeric coverage/component/retrace bounds.
6. DOCX extract includes merged table text, repeated-header table text once in source order, and OMML text.
7. Same input in different output directories produces byte-identical `paths.json`.
8. Report tests prove conflict/suppression/retrace/worst-glyph metrics are measured, not constants.
9. A corpus with at least one safe-rejected/aggressive-accepted pair while collision protection remains enforced.
10. Center/right/decimal tab-stop geometry assertions.
11. Multi-page transition test for 19 pauses/parks and final pen-up.
12. Rotated raster regression asserting actual stroke transform, not only metadata.

## 26. Artifacts for human review

Open `visual-index.html` first. Highest-value manual views:

1. `jobs/docx-centerline-hybrid-a5/pages/page-006/plotter-preview.svg` — raster vectorization and 12° rotation.
2. `jobs/docx-centerline-hybrid-a5/pages/page-007/plotter-preview.svg` — anchored square wrapping and narrow-column quality.
3. `jobs/docx-centerline-hybrid-a5/semantic-debug/arrows.svg` — only one of three arrows.
4. `jobs/docx-centerline-hybrid-a5/semantic-debug/tables.svg` and pages 8–18 — merges, borders, repeated headers and page splits.
5. `jobs/docx-centerline-hybrid-a5/centerline-font-preview.svg` plus `analysis/worst-glyphs.json` — punctuation and Cyrillic/capital retrace.
6. `jobs/connections-safe/connection-debug.svg` versus aggressive — visual safety of the 105 accepted connectors.
7. `jobs/docx-centerline-hybrid-a5/layout-debug/placement-overlay.svg` — A4-source to A5 placements.

No SVG→PNG renderer was available in the environment, so visual claims requiring human perception are explicitly left for review. All machine-verifiable geometry, counts, hashes and safety checks are in `summary.json`.
