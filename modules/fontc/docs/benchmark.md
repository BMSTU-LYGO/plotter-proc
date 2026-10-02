# fontc benchmark

Run from the repository root after a Release build:

```sh
build/modules/fontc/fontc_benchmark assets/1.ttf assets/font-cache-corpus.txt /tmp/fontc-benchmark
```

The executable emits a Markdown table for 512, 768, 1024, 1536 and 2048 px/em
including wall time, peak RSS, glyph/stroke/point counts, PFC size, load time and
lookup throughput. Results are intentionally generated on the target machine;
hardware-dependent numbers are not hard-coded here.

## Validation run

Corpus: `assets/font-cache-corpus.txt`, 169 compiled glyphs, one unavailable codepoint skipped.

| resolution | compile_ms | peak_rss_kb | strokes | points | pfc_bytes | load_ms | lookup_per_sec |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 512 | 721.606 | 328728 | 397 | 67106 | 543264 | 0.444 | 1.02e8 |
| 768 | 2604.53 | 328728 | 402 | 62250 | 504436 | 0.444 | 8.63e7 |
| 1024 | 6173.51 | 328728 | 405 | 24945 | 206008 | 0.441 | 8.70e7 |
| 1536 | 20792.2 | 328728 | 405 | 50240 | 408368 | 0.790 | 7.98e7 |
| 2048 | 47630.9 | 521504 | 407 | 28318 | 233000 | 0.327 | 6.81e7 |
