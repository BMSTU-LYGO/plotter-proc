# Block 7

## Scope

- Branch: `swag`.
- Base: completed block 6 working tree on HEAD `88710bd`.
- Font: `assets/1.ttf`.
- Regression corpus: `assets/font-cache-corpus.txt`, 169 glyphs at the unchanged
  default resolution of 2048 px/em.
- Block 8 was not started.

## Dual-candidate winner audit

`tools/analyze_skeleton_candidates.py` now exports one deterministic row per glyph with:

```text
glyph, codepoint, candidate methods, score per method, winner, score delta,
candidate metrics, selected quality, warnings
```

The complete pre-change audit is
`build/upd12-block7-dual-candidate-audit.json`.

| Population | medial_axis | skeletonize |
|---|---:|---:|
| all 169 glyphs | 140 (82.84%) | 29 (17.16%) |
| 166 dual-candidate glyphs | 137 (82.53%) | 29 (17.47%) |

Three configured glyph overrides (`ъ`, `ы`, `ь`) use only `medial_axis`. Across the
166 dual comparisons, the absolute score delta ranged from 0.005750 to 3.159817, with
a median of 0.167150.

## Fast-first strategy

The audited primary method is `medial_axis`. It is evaluated first only when both the
font SHA-256 and complete centerline config fingerprint match the offline audit. The
fingerprint includes algorithm version, font/glyph overrides and glyph-patch identity.

The second candidate is skipped only when every check passes:

```text
glyph is an audited medial_axis winner
mask coverage >= 0.70
reconstruction extra <= 0.10
component count >= 1 and micro loops <= 4
estimated retrace <= configured maximum
junction count <= 8
short edges <= 6
all significant counters preserved
```

The thresholds were replayed against the complete dual-candidate audit. The audited
winner allowlist is required because no universal combination of the available primary
metrics cleanly separated all 137 `medial_axis` winners from all 29 `skeletonize`
winners. Threshold-only skipping would therefore be unsafe.

The final corpus behavior is:

| Path | Glyphs |
|---|---:|
| confident fast-first | 135 |
| dual-candidate safe fallback | 31 |
| configured single method | 3 |

This reduces complete candidate evaluations from 335 to 200 (40.3%). The two audited
`medial_axis` winners rejected by the confidence gate are `;` (coverage below the gate)
and `Ю` (candidate counter preservation below the gate); both safely run the second
candidate.

For an unknown font, changed config fingerprint, unaudited glyph, failed metric or
candidate exception, the existing dual-candidate behavior remains active. Original
configured method order is retained as the deterministic score tie-breaker even though
the audited execution order starts with `medial_axis`.

## Performance

| Full 169-glyph cold build | Wall | Peak RSS |
|---|---:|---:|
| block 6 dual candidates | 425.01 s | 0.98 GiB |
| block 7 fast-first | 333.87 s | 0.93 GiB |

Wall time improved by 91.14 s, or 21.4%. Output is in
`build/upd12-block7-fast-first/`; the post-change candidate audit is
`build/upd12-block7-fast-first-audit.json`.

## Geometry and quality regression proof

Every new shard was compared to its block 6 dual-candidate reference:

```text
glyphs compared             169
skeleton winner changes       0
stroke geometry changes       0
warning changes               0
selected quality changes      0
```

Candidate audit metadata intentionally records only methods actually evaluated and adds
the fast-first flag plus individual confidence checks. Excluding those runtime/audit
fields, the complete selected quality payload is equal. Geometry, topology, routing,
warnings and the selected method are unchanged.

## Tests

```text
make lint          passed
pytest             289 passed
make smoke         passed
git diff --check   passed
```

New coverage verifies that unknown fonts use both candidates, confidence requires the
audited glyph and every quality gate, and sequential/parallel geometry remains
deterministic. The 2048 px/em default was not changed and no adaptive-resolution path
was introduced.
