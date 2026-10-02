# C++ document pipeline benchmark

Command run from the repository root:

```bash
.venv/bin/python refactor/doc-module/tools/compare_cpp_python_parity.py \
  --cpp /tmp/plotter-doc-full \
  --python .venv/bin/python \
  --case txt-basic --benchmark --runs 2 \
  --output /tmp/cppdoc-parity-txt-cache
```

The two C++ invocations shared the harness cache directory. The first was cold; the second loaded the cached document import. Wall time includes process startup and artifact writing. Native stage values are emitted by the pipeline report and do not necessarily sum to wall time.

| Metric | Cold cache | Warm cache |
| --- | ---: | ---: |
| Wall time (s) | 0.022509 | 0.022030 |
| Import (ms) | 0.462865 | 0.221910 |
| Layout (ms) | 0.329990 | 0.339738 |
| Path and geometry (ms) | 0.842949 | 0.843028 |
| G-code (ms) | 9.857985 | 9.790170 |
| Peak RSS (KiB) | 14908 | 15676 |
| Cache hits | 0 | 1 |
| Cache misses | 1 | 0 |

The matching Python capture runs took 1.887115 s and 1.851485 s. The harness deliberately reports Python stage timings, peak RSS, and cache statistics as unavailable because `capture_python_pipeline.py` does not expose equivalent metrics.

TXT parity passed page count (1), stroke count (45), glyph count (30), and the generated G-code state scan (1506 commands). Stroke bounding boxes and provenance still differ. The report contains the first twelve unmatched bounding-box and provenance entries plus their totals:

`/tmp/cppdoc-parity-txt-cache/parity-report.json`

This is a two-run local measurement of `/tmp/plotter-doc-full`, intended to verify the native timing and cache-reporting path. It is not a throughput or regression threshold.
