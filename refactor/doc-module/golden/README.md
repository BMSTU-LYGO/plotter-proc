# Frozen parity corpus

The harness captures the actual Python `read_document` and `paginate_document` boundaries by temporary in-process wrappers. `document.json` is the actual `DocumentModel`; `layout.json` includes the full `PaginatedLayout` plus debug placement/trace. Paths, canonical report, job manifest, deterministic preview SVG and combined G-code come from the same run.

`txt-basic` and `markdown-basic` are frozen and verified. The other cases in `corpus.json` register the required TXT, Markdown, DOCX, PDF and SVG coverage with A4/A5 and outline/centerline modes. They are intentionally unfrozen in Block 1 because DOCX/PDF/SVG and centerline generation cost materially more; capture them one at a time after reviewing the resulting diffs.

Create or verify a case:

```bash
.venv/bin/python refactor/doc-module/tools/capture_python_pipeline.py tests/fixtures/layout/cache_benchmark.txt --output /tmp/cppdoc-parity-txt --golden refactor/doc-module/golden/txt-basic --font-mode outline --workers 1
```
