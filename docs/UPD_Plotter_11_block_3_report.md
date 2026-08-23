# UPD_Plotter_11 — отчёт по блоку 3

## Что было сломано

Warm conversion основного `plotter_pipeline_full_test.docx` занимала
около 126.7 s. Handwriting и simplification занимали 86.8% времени,
хотя font cache был тёплым.

Старый `tools/benchmark_conversion.py` всегда запускал cold compile
перед warm runs, не показывал stage progress и не включал
`connections=safe`, то есть не измерял primary handwriting workload.

## Как воспроизводилось

Аудиторский warm baseline:

| Стадия | Время |
|---|---:|
| total | 126.564 s |
| handwriting | 68.382 s |
| simplification | 41.468 s |
| build paths | 8.933 s |
| font compile | 1.474 s |

Для профилирования тот же job был запущен через `cProfile`.
Профиль сохранён в:

```text
build/UPD_Plotter_11_block_3_baseline.prof
```

Под profiler, который заметно увеличивает absolute time:

| Функция | Calls | Cumulative |
|---|---:|---:|
| `route_words` | 20 | 155.916 s |
| `_connection_candidate` | 5,747 | 147.061 s |
| `_collision_points` | 5,641 | 146.441 s |
| handwriting `_distance` | 167,823,253 | 43.990 s |
| `simplify_path_document` | 20 | 89.204 s |
| `_rdp_with_deviation` | 204,559/6,453 | 85.641 s |
| simplifier `_point_segment_distance` | 40,446,537 | 75.698 s |

## Root cause

Handwriting collision check имел два слоя лишней работы:

1. каждый connector просматривал все strokes страницы;
2. для left/right stroke distance до anchor считался до дешёвой
   проверки bbox сегмента. Это давало 167.8 млн distance calls.

Simplifier использовал рекурсивный RDP с list slicing, списком
всех distances на каждом уровне и созданием временного `Point`
для каждой distance. На длинном adversarial stroke также был возможен
`RecursionError`.

Cold benchmark не зависал: полная каноническая сборка 169 glyphs
в блоке 2 завершилась примерно за 18.7 min. Проблемой workflow
было смешение этого cold compile с document conversion без прогресса.

## Какие файлы изменены

- `src/plotter_processor/handwriting.py`
- `src/plotter_processor/path_simplifier.py`
- `src/plotter_processor/performance.py`
- `src/plotter_processor/pipeline.py`
- `tools/benchmark_conversion.py`
- `tests/test_handwriting.py`
- `tests/test_motion_pipeline.py`
- `tests/test_performance.py`
- `tests/test_speed_benchmark.py`
- `docs/speed-benchmark.md`
- `docs/UPD_Plotter_11_block_3_report.md`

## Что именно изменено

- Для stroke obstacles добавлен детерминированный uniform-grid index
  с cell size 4 mm. Query возвращает только strokes, пересекающие
  bbox candidate corridor, в исходном stroke order.
- Внутри stroke проверка segment bbox выполняется до anchor distance.
  Условия collision/boundary ignore не менялись.
- Recursive RDP заменён на iterative stack с index ranges и keep bitmap.
  Tie-breaking остался first maximum, а error budget и `max_observed_deviation_mm`
  сохранены.
- `StageTimings` получил optional callback для start/completed events.
- Benchmark получил mutually exclusive `--cold-only` / `--warm-only`,
  `--warm-runs N`, `--connections`, stage progress и отдельную статистику.
  Старый `--runs` сохранён как скрытый compatibility alias.
- Primary benchmark явно использует safe connections, mathtext centerline
  и page numbers, поэтому handwriting workload не пропускается.

Geometry thresholds, connection policy, page layout, simplification tolerance,
machine workspace и font algorithm в блоке 3 не менялись.

## Какие тесты добавлены

- adversarial stroke из 1,500 points завершает simplification без
  recursion failure и сохраняет endpoints/error bound;
- obstacle index возвращает только bbox-overlapping strokes в source order;
- benchmark help содержит cold/warm modes и `--warm-runs`;
- `StageTimings` эмитит ordered start/completed events с elapsed time.

Перед production fix новые obstacle-index/benchmark tests падали
из-за отсутствующих API. Длинный adversarial corpus покрывает
прежний recursion-depth risk.

## Какие команды прогнаны

```bash
.venv/bin/python -m cProfile -o build/UPD_Plotter_11_block_3_baseline.prof \
  -m plotter_processor run plotter_pipeline_full_test.docx ... --connections safe

.venv/bin/python -m plotter_processor run plotter_pipeline_full_test.docx \
  ... --connections safe --output-dir build/UPD_Plotter_11_block_3_after_final

.venv/bin/python tools/benchmark_conversion.py plotter_pipeline_full_test.docx \
  --font assets/1.ttf --warm-only --warm-runs 3 --connections safe \
  --output build/UPD_Plotter_11_block_3_benchmark/conversion.json

.venv/bin/python -m cProfile -o build/UPD_Plotter_11_block_3_final.prof \
  -m plotter_processor run plotter_pipeline_full_test.docx ... --connections safe

make lint
make test
make smoke
git diff --check
```

Дополнительно проверены 28 generated G-code files: нет
heating, homing, extrusion и non-finite coordinates.

## Результат до / после

Три warm runs:

| Run | Wall time | Handwriting | Simplification | Font cache |
|---:|---:|---:|---:|---|
| 1 | 66.826 s | 27.974 s | 20.369 s | 122 hits / 0 misses |
| 2 | 65.779 s | 28.189 s | 20.150 s | 122 hits / 0 misses |
| 3 | 62.008 s | 28.039 s | 20.320 s | 122 hits / 0 misses |
| median | 65.779 s | 28.039 s | 20.320 s | warm |

Сравнение с audit baseline:

| Метрика | До | После, median | Изменение |
|---|---:|---:|---:|
| total warm wall | 126.564 s | 65.779 s | -48.03% |
| handwriting | 68.382 s | 28.039 s | -59.00% |
| simplification | 41.468 s | 20.320 s | -51.00% |
| build paths | 8.933 s | 8.599 s | -3.74% |

Post-fix profiler:

| Метрика | До | После |
|---|---:|---:|
| profiler total | 253.987 s | 124.203 s |
| `_collision_points` cumulative | 146.441 s | 44.950 s |
| handwriting `_distance` calls | 167,823,253 | 373,229 |
| `_rdp_with_deviation` cumulative | 85.641 s | 40.177 s |

Все 20 page-level `paths.json` во всех трёх runs имеют одинаковые
SHA после удаления только job-local `source_path`. Они также
совпадают с immediate pre-fix baseline блока 3.

Неизменные output metrics:

```text
pages: 20
strokes: 6453
points: 111714
draw_distance_mm: 71014.932
travel_distance_mm: 54895.811
accepted connections: 1359
rejected connections: 4388
warnings: 2
```

Quality gate:

```text
lint: passed
test: 254 passed
smoke: passed
G-code safety: passed
```

## Оставшиеся ограничения

- Cold full-font compile по-прежнему дорогой: около 18.7 min для
  169 glyphs. В блоке 3 font algorithm/cache не оптимизировали,
  так как warm profile показал другие dominant stages.
- RDP сохраняет ту же worst-case quadratic complexity. Текущее
  изменение убрало recursion/slicing/all-distance-list overhead без
  изменения geometry.
- Handwriting collision остаётся крупнейшей stage (~28 s), но
  дальнейшая замена segment model/index была бы более рискованной
  и не нужна для Definition of Done этого блока.
- Stage progress показывает per-call events; на 20-page document он
  подробный. Это намеренно: длительная страница больше не
  выглядит как зависший benchmark.
