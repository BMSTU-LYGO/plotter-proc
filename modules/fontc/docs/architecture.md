# C++ centerline font pipeline

## Architecture

`fontc` is an offline-only C++20 compiler:

```text
TTF → FreeType raster → binary mask → Guo–Hall thinning → spur pruning
    → skeleton graph → graph cleanup → Euler routing → RDP/Chaikin
    → integer font units → one PFC file
```

Runtime uses `RuntimeFont`/`PfcFont` only. These headers do not include FreeType,
do not accept TTF paths and cannot invoke compilation. A missing glyph resolves
to precompiled `?`; loading a cache without `?` is an explicit error.

## Build

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
```

The only production dependency is FreeType. OpenCV is not used.

## Compile

```sh
build/modules/fontc/fontc assets/1.ttf \
  --chars-file assets/font-cache-corpus.txt \
  --output build/font.pfc \
  --resolution 1024 --threads auto --force
```

Compilation is deterministic across worker counts. Each worker owns its own
`FT_Face`; output glyphs are sorted by Unicode codepoint.

## PFC1 format

The little-endian header contains magic/version, algorithm version, 256-bit
font/config fingerprints, metrics and glyph count. A sorted fixed-size index
maps codepoint to bounded payload offset/size. Payloads contain advance,
strokes and integer font-unit points. The writer uses temp file, `fsync` and
atomic rename; no JSON shards or manifests are produced.

## Regression and benchmark

```sh
ctest --test-dir build -R 'pipeline_regression|pfc|runtime_font'
build/modules/fontc/fontc_benchmark assets/1.ttf assets/font-cache-corpus.txt /tmp/fontc-benchmark
```

The regression gate checks the required Cyrillic set, non-empty geometry,
bounds and byte-identical single/multi-thread output. The benchmark reports the
512/768/1024/1536/2048 resolution matrix, compile/load time, peak RSS, PFC size,
stroke/point counts and lookup throughput.
