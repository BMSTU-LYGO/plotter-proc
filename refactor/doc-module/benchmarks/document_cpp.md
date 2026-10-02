# C++ document pipeline benchmark status

Measured 2026-10-02 on this workspace. One cold `txt-basic` run with the frozen corpus harness took 0.023471 s in C++ and 2.049645 s in Python (87.3× total speedup). This is a single run, not a statistically reliable benchmark. The harness records raw timings in `parity-report.json`; repeat with `--benchmark --runs N` for robust results.

The five-case native parity pass measured page/glyph/stroke counts and G-code safety. Page counts and safety pass in all five, but DOCX/PDF geometry and stroke provenance remain outside parity. Stage-specific speedups, warm-cache speedup, and peak-memory reduction have not yet been measured; no production performance claim should use the single-run result.
