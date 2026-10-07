# Centerline curve benchmark

Reproduce with the existing `fonts/1.ttf` at 512 px/em and a corpus containing
`имшжоафдПривет мир!`. Compile it once with the previous `fontc` binary and once
with the current binary, then run `fontc_curve_compare old.pfc new.pfc`.

The comparison uses 5 mm/em. The old time estimate assumes a 2000 mm/min draw
feed; the new estimate uses 2700/2000/1200 mm/min based on turn angle. These
are ideal motion times and do not include Marlin acceleration or pen travel.

| Glyph | Points old | Points new | Segments old | Segments new | Draw mm old | Draw mm new | Time s old | Time s new |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| и | 380 | 36 | 377 | 35 | 7.797 | 7.691 | 0.234 | 0.200 |
| м | 444 | 49 | 438 | 48 | 10.013 | 9.931 | 0.300 | 0.267 |
| ш | 524 | 58 | 520 | 57 | 11.916 | 11.791 | 0.357 | 0.299 |
| ж | 492 | 64 | 491 | 63 | 14.606 | 14.405 | 0.438 | 0.447 |
| о | 244 | 63 | 243 | 62 | 6.071 | 5.965 | 0.182 | 0.139 |
| а | 346 | 32 | 344 | 31 | 8.182 | 8.085 | 0.245 | 0.231 |
| ф | 692 | 79 | 688 | 78 | 17.816 | 17.942 | 0.534 | 0.501 |
| д | 610 | 80 | 607 | 79 | 14.347 | 14.191 | 0.430 | 0.386 |
| Привет мир! | 4718 | 499 | 4688 | 488 | 107.331 | 105.988 | 3.220 | 2.796 |

The `ж` estimate is slightly slower because more of its segments fall into
the tight turn speed zone. The draw length of `ф` rises by less than 1%.
Across every glyph in the sample PFC, segments below 0.05 mm fell from 6307
to 4; segments below 0.10 mm fell from 6742 to 171.
