# FAST benchmark

Input: `docs/1.md`; font: `font-cache/1/1.pfc`; A4, 6.9714 mm, geometry optimization and word joining enabled. Baseline is the pre-change `build/1/output.gcode`. Estimated time uses modal feedrates and travel/Z distances; it excludes acceleration.

| Metric | Before | After |
| --- | ---: | ---: |
| Pen lifts | 5,382 | 5,499 |
| Effective feedrate changes | 110,105 | 22,030 |
| Estimated time, seconds | 14,408.763 | 6,842.313 |
| Draw segments | 348,077 | 347,868 |

After: 3,004 words, average 1.603 pen-down groups per word. The stricter 2 mm straight join limit increases total lifts by 117 compared with the earlier 2.5 mm curved joining rule; this preserves letter geometry when a join is uncertain.

The regression corpus in `examples/fast_word_regression.txt` produced one body pass for `мама`, `машина`, `данные`, `значение`, and `переписать`; `й` had a separate upper pass and `ё` retained two separate dots. Across 17 words, the average was 1.471 pen-down groups per word, with no draw segments below 0.05 mm.
