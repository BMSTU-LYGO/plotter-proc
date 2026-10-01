# Frozen parity corpus

The harness captures the actual Python `read_document` and `paginate_document` boundaries by temporary in-process wrappers. `document.json` is the actual `DocumentModel`; `layout.json` includes the full `PaginatedLayout` plus debug placement/trace. Paths, canonical report, job manifest, deterministic preview SVG and combined G-code come from the same run.

`txt-basic`, `markdown-basic`, `docx-basic`, `pdf-layout`, and `svg-vector` are frozen and verified. A4 cases use `fixtures/machine-a4.yaml` because the production machine profile has a 220 mm Y workspace. The remaining centerline/table-heavy cases stay listed in `corpus.json` until captured and reviewed.

Create or verify a case:

```bash
.venv/bin/python refactor/doc-module/tools/capture_python_pipeline.py tests/fixtures/layout/cache_benchmark.txt --output /tmp/cppdoc-parity-txt --golden refactor/doc-module/golden/txt-basic --font-mode outline --workers 1
```
