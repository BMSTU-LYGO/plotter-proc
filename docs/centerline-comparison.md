# Outline vs centerline comparison

Input: `examples/input.txt`; font: `assets/1.ttf`; page: A5 normal.

| Metric | Outline baseline | Centerline |
|---|---:|---:|
| strokes | 60 closed contours | 112 non-repeating strokes |
| points | 1576 | 33392 |
| draw distance | 562.434 mm | 258.608 mm |
| travel distance | 165.325 mm | 157.253 mm |
| estimated time | 0.618 min | 0.311 min |

The centerline result reduces drawing distance by about 54% and does not
trace both boundaries of filled strokes. Automatic quality checks mark 12
complex glyphs for preview review; their diagnostics are generated under
`build/final-centerline/debug`.

The higher point count comes from high-resolution font-unit sampling and is
bounded per stroke. G-code contains no heating, extrusion or default `G28`.
