# Centerline curve benchmark

Reproduce with the existing `fonts/1.ttf` at 512 px/em and a corpus containing
`имшжоафдПривет мир!`. Compile it once with the previous `fontc` binary and once
with the current binary, then run `fontc_curve_compare old.pfc new.pfc`.

The comparison uses 5 mm/em. The old time estimate assumes a 2000 mm/min draw
feed; the new estimate uses 2700/2000/1200 mm/min based on turn angle. These
are ideal motion times and do not include Marlin acceleration or pen travel.

| Glyph | Points old | Points new | Segments old | Segments new | Draw mm old | Draw mm new | Time s old | Time s new |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| и | 380 | 37 | 377 | 36 | 7.797 | 7.691 | 0.234 | 0.199 |
| м | 444 | 47 | 438 | 46 | 10.013 | 9.927 | 0.300 | 0.271 |
| ш | 524 | 57 | 520 | 56 | 11.916 | 11.790 | 0.357 | 0.299 |
| ж | 492 | 64 | 491 | 63 | 14.606 | 14.407 | 0.438 | 0.445 |
| о | 244 | 53 | 243 | 52 | 6.071 | 5.960 | 0.182 | 0.140 |
| а | 346 | 32 | 344 | 31 | 8.182 | 8.084 | 0.245 | 0.231 |
| ф | 692 | 78 | 688 | 77 | 17.816 | 17.942 | 0.534 | 0.503 |
| д | 610 | 77 | 607 | 76 | 14.347 | 14.190 | 0.430 | 0.386 |
| Привет мир! | 4718 | 484 | 4688 | 473 | 107.331 | 105.973 | 3.220 | 2.798 |

The `ж` estimate is slightly slower because more of its segments fall into
the tight turn speed zone. The draw length of `ф` rises by less than 1%.
Across every glyph in the sample PFC, segments below 0.05 mm fell from 6307
to 2; segments below 0.10 mm fell from 6742 to 125.
