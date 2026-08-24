# Block 6

## Scope and baseline

- Branch: `swag`.
- Base HEAD: `88710bd` (`12-5 done`).
- Font: `assets/1.ttf`, 2048 px/em, algorithm version 7.
- Full corpus: `assets/font-cache-corpus.txt`, 169 unique non-space glyphs.
- Representative profile: `.:;?ажфщШЩЮU`.
- Existing deleted `plotter_pipeline_full_test.docx/.pdf` and untracked `input.docx/.pdf`
  were not touched.

The pre-change representative cold profile took 98.772 s for 12 glyphs. It confirmed
that candidate-independent labeling and EDT were performed twice per glyph:

| Stage total, 12 glyphs | Before |
|---|---:|
| component labeling | 0.657 s |
| distance transform | 9.018 s |
| spur pruning | 7.841 s |
| total wall | 98.772 s |

Raw evidence: `build/upd12-block6-baseline-representative.json` and its `.prof` file.

## Changes

1. Added `SkeletonInput` shared preprocessing. Component labels, component count and
   distance transform are now computed once per glyph and supplied unchanged to both
   `skeletonize` and `medial_axis` candidates. In the controlled profile this halved
   labeling (0.657 -> 0.325 s) and candidate-independent EDT (9.018 -> 4.551 s).
2. `prune_short_spurs()` now lazily caches the reconstruction of the current accepted
   state. It is computed only for a real tentative removal and is reused until an
   accepted removal replaces it. The candidate reconstruction remains full-frame, so
   the coverage formula is unchanged.
3. A local ROI reconstruction was investigated but not enabled. Nearest-skeleton
   reassignment can extend outside a naive branch bounding box; keeping the full new
   reconstruction is the safe exact implementation. A randomized regression test proves
   that the cached formula equals the original full reconstruction formula exactly.
4. Whole-frame degree convolution was retained. The baseline profile placed EDT,
   candidate morphology, reconstruction and quality work above degree calculation, so an
   incremental degree structure would add correctness risk without addressing the current
   dominant cost.
5. Added process-parallel glyph compilation. Every worker loads the TTF once in its
   initializer, compiles independent glyph jobs, and closes the font at process exit.
   Results are merged by codepoint, independent of completion order.
6. Added API `workers=auto|N` support and CLI `--centerline-workers auto|N` for both the
   document pipeline and `compile-centerline-font`. API calls remain sequential by default
   for compatibility; the CLI/pipeline default is `auto`.
7. The measured auto policy is `min(cpu_count, 4, glyph_count)`. Four workers used about
   0.98 GiB peak RSS for the full corpus. An eight-worker A/B run was stopped after it
   completed fewer glyphs in the same interval because memory-bandwidth contention made it
   slower; its already written 67 shards remained intact.
8. Added per-glyph shard cache schema v8:

   ```text
   namespace/
       manifest.json
       glyphs/U+XXXXXX.json
       centerlines.json
   ```

   The manifest identity contains font SHA-256, algorithm version and the complete
   centerline config fingerprint, which already includes glyph patches and applicable
   font/glyph overrides. Every completed glyph is written atomically before manifest
   update, so interruption loses no completed shard.
9. Warm requests load only requested shards instead of the complete 169-glyph canonical
   JSON. A pure shard hit no longer rewrites the canonical cache or manifest. The legacy
   canonical cache remains readable and is retained as a compatibility artifact.

## Performance results

| Workload | Workers | Hits / misses | Wall | Peak RSS |
|---|---:|---:|---:|---:|
| full cold, 169 glyphs | 4 | 0 / 169 | 425.01 s | 0.98 GiB |
| partial cold, 40 glyphs | 4 | 0 / 40 | 109.18 s | 0.90 GiB |
| warm requested subset, 40 glyphs | auto | 40 / 0 | 2.61 s | 0.14 GiB |

The partial cold request is 3.89x faster than the full cold corpus. A four-glyph A/B
run fell from roughly 24.8 s sequential to 19.0 s with two workers. The full cold result
is an estimated 3.3x faster than the 12-glyph baseline extrapolated to 169 glyphs, but it
does **not** meet the block's first milestone of less than five minutes. The remaining
dominant work is the two full skeleton candidate pipelines and quality analysis; changing
candidate selection belongs to block 7 and was deliberately not done here.

Artifacts:

- `build/upd12-block6-full/`
- `build/upd12-block6-partial-40/`
- `build/upd12-block6-workers1/`
- `build/upd12-block6-workers2/`
- `build/upd12-block6-optimized-representative.json`

## Determinism and quality proof

The representative set `.?аж` was compiled with the pre-block-6 code from `HEAD` in an
isolated `/tmp` checkout and with the new code. The following fields are exactly equal:

```text
glyph geometry      true
quality payloads    true
warnings            true
font metrics        true
serialized config   true
preview SVG          byte-identical
```

Independent new-code builds with one and two workers also produced byte-identical
canonical JSON and preview SVG. Unit coverage additionally checks both skeleton methods
byte-for-byte with and without shared preprocessing, exact cached/full coverage loss,
sequential/parallel glyph equality, deterministic glyph order, worker bounds, and recovery
from a valid shard after the canonical file is removed.

## Verification

```text
make lint          passed
pytest             288 passed
make smoke         passed
git diff --check   passed
```

No block 7 changes were made.
