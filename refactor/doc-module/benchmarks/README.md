# Native versus frozen-Python parity benchmark

Run the bounded parity suite after building the native CLI:

```bash
python3 refactor/doc-module/tools/compare_cpp_python_parity.py \
  --cpp build/refactor/doc-module/cpp/plotter-doc \
  --output /tmp/cppdoc-parity
```

Add `--benchmark --runs 3` for three isolated full-pipeline timings of each implementation. The command writes `parity-report.json` and retains native artifacts per case for failures. It never writes benchmark claims into this repository: timings remain in the report only when both commands completed every requested run.

The comparator uses the verified cases from `golden/corpus.json`. It checks page count, glyph count when both schemas expose it, stroke count, exact rounded stroke bounding-box multisets, provenance tuples, and a conservative generated-G-code state scan. Frozen cases include page numbers unless their corpus entry sets `"page_numbers": false`; the harness passes `--page-numbers` to the native CLI accordingly. Native and Python artifact schemas differ, so fields with no matching representation are marked `unavailable`; those are not parity passes. Bounds are currently rounded to 0.001 mm for stable diagnostics. The `--tolerance-mm` value is recorded in the report for a future nearest-neighbour geometry comparator; it does not relax the current exact multiset check.
