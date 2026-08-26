# UPD_Plotter_19 SuperFast benchmark

Generated with `PYTHONPATH=src .venv/bin/python tools/benchmark_superfast.py`.

| Scenario | Mode | Pen up/down | Draw, mm | Travel, mm | Retrace, mm | Estimated, s | Words 1 / 2 / >2 passes |
|---|---|---:|---:|---:|---:|---:|---:|
| `Привет, как дела?` | Normal | 6 / 6 | 24.40 | 9.72 | 0.00 | 3.270 | 2 / 1 / 0 |
| `Привет, как дела?` | SuperFast | 5 / 5 | 25.80 | 8.32 | 1.40 | 2.948 | 3 / 0 / 0 |
| `ж м т ш щ ы ь ъ` | Normal | 16 / 16 | 19.20 | 33.99 | 0.00 | 7.048 | 0 / 8 / 0 |
| `ж м т ш щ ы ь ъ` | SuperFast | 8 / 8 | 30.40 | 22.79 | 11.20 | 4.472 | 8 / 0 / 0 |
| Multiline | Normal | 34 / 34 | 136.80 | 123.13 | 0.00 | 19.835 | 4 / 3 / 7 |
| Multiline | SuperFast | 24 / 24 | 149.75 | 110.18 | 12.95 | 16.594 | 7 / 7 / 0 |

Across the three deterministic scenarios SuperFast removes 19 pen lifts and reduces estimated physical time by 6.139 seconds; every benchmark word is completed in one or two passes.
