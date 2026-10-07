# Motion benchmark

Input: `docs/1.md`, A4, `font-cache/1/1.pfc`, 6.9714 mm, word joining, simplification and geometry optimization. The BEFORE column is a controlled F2000 replay of the same current geometry; no historical firmware capture is available. Both runs use the same acceleration settings. Every G-code line matches after replacing the draw feedrate marker, so geometry and Z are identical.

| Metric | BEFORE F2000 | AFTER F6000 |
| --- | ---: | ---: |
| Draw distance, mm | 276036.347 | 276036.347 |
| Draw moves | 347910 | 347910 |
| Feedrate changes | 22030 | 22030 |
| Pen lifts | 5499 | 5499 |
| Estimated draw time, s | 15746.059 | 15238.924 |
| Estimated total time, s | 20081.841 | 19574.706 |
| Estimated average draw speed, mm/s | 17.531 | 18.114 |
| Segments reaching cruise speed | 40.479% | 0.0115% |

AFTER draw feedrates read from `output.gcode`: **6000 only**. Its header includes `M203 X120 Y120` and `M204 P1500 T2000`; `M204 T1500` is emitted before drawing because Marlin treats these non-extruding G1 moves as travel for M204. `M205` is conditional on the firmware mode selected in `configs/machine.yaml`.

Segment lengths: p25 0.452 mm, median 0.649 mm, p75 0.932 mm; 273114/347910 segments are under 1 mm. On the stop-at-each-junction estimator, draw is 77.85% of total time, travel 7.03%, Z 6.74%, and dwell 8.38%. This is a conservative estimate because Marlin lookahead may carry speed across collinear segments. Even the ideal 276036 mm / 100 mm/s = 2760 s draw-only lower bound exceeds 3–4 minutes for this 3004-word file. The claimed 10-minute baseline must refer to a different document or measurement.

`examples/bench_F2000.gcode`, `bench_F4000.gcode` and `bench_F6000.gcode` use identical text geometry and a 100 mm calibration stroke; only drawing F differs. Regenerate them from the F6000 benchmark output with `python3 scripts/generate_motion_benchmarks.py build/motion_bench/output.gcode examples`.

Marlin commands: [M203](https://marlinfw.org/docs/gcode/M203.html), [M204](https://marlinfw.org/docs/gcode/M204.html), [M205](https://marlinfw.org/docs/gcode/M205.html). Firmware version and junction mode were not present in the repository, so M205 is disabled until confirmed on the machine.
