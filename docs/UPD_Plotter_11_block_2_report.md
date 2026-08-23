# UPD_Plotter_11 — Block 2 Report

## Что было сломано

F-005 помечал 12 реально используемых glyphs как `needs_review`:

```text
; . … : ? Щ Ц Ш U И Й Ю
```

У punctuation отчётный coverage был 0.609078–0.678169. Capitals имели
coverage 0.865277–0.930506, но получали warning о потере significant
counter. У `Щ/Ц/Ш/U/И/Й/Ю` также был retrace 0.156193–0.256257,
но отчёт не отделял топологически неизбежный retrace от excess.

## Как воспроизводилось

Выполнена forced compile всех 12 glyphs из `assets/1.ttf` при
2048 px/em с per-glyph debug. Baseline полностью совпал с
`report/analysis/worst-glyphs.json`:

- `.`: coverage 0.632283, 1 component, 1 route;
- `:`: coverage 0.635286, 2 components, 2 routes;
- `;`: coverage 0.609078, 2 components, 2 routes;
- `…`: coverage 0.632771, 3 components, 3 routes;
- `?`: coverage 0.678169, 2 components, 2 routes;
- capitals: inside-mask 1.0, one route per physical component, counter warning.

Для diagnostic regression был добавлен tiny variable-width mark, который
некорректно оценивался global-radius reconstruction.

## Root cause

Сами selected skeletons и routes были визуально и топологически
корректны:

- `;` сохранял dot и lower curved component;
- `:` сохранял две физически отдельные components;
- `…` сохранял три components;
- `?` имел один route для hook и отдельный route для dot;
- capitals не теряли components и не выходили за mask.

Defect был в final quality reconstruction. `score_quality()` брал один
median radius по всем skeleton pixels и делал uniform binary dilation. Для
tiny marks и штрихов переменной толщины это:

- занижало coverage;
- заливало часть реальных counters;
- создавало false `needs_review`, хотя centerline оставался внутри mask.

Local radius reconstruction на тех же неизменённых skeletons дала
coverage 0.940719–0.993705 и counter preservation 1.0 для всех 12 glyphs.

## Какие файлы изменены

- `configs/layout.yaml`
- `docs/centerline-quality-v3.md`
- `src/plotter_processor/centerline_font/candidate_score.py`
- `src/plotter_processor/centerline_font/compiler.py`
- `src/plotter_processor/centerline_font/debug.py`
- `src/plotter_processor/centerline_font/quality.py`
- `src/plotter_processor/centerline_font/route_quality.py`
- `src/plotter_processor/centerline_font/skeleton_selector.py`
- `src/plotter_processor/centerline_font/skeletonizer.py`
- `tests/test_centerline_corpus.py`
- `tests/test_centerline_debug.py`
- `tests/test_centerline_quality_v3.py`
- `tests/test_centerline_routing.py`

## Что именно изменено

- Общая local-radius reconstruction вынесена из spur-pruning utility и
  используется final quality evaluation и debug reconstruction.
- Global `min_mask_coverage=0.70`, counter threshold и strict quality gate не
  ослаблялись.
- Candidate-selection geometry/scoring не переведены на новую metric, чтобы
  не менять выбор skeleton во время quality bugfix. Debug JSON явно
  маркирует candidate metric как `median_radius_candidate_score`, а final
  quality как `local_radius`.
- Top-level glyph metrics теперь содержат `short_edges`, `micro_loops`,
  `minimum_one_route_retrace_length` и `excess_retrace_length`.
- Theoretical minimum retrace считается exact open Chinese-postman matching
  для каждой component. У всех target capitals фактический retrace
  равен этому минимуму; excess = 0.
- Cache `algorithm_version` поднят с 6 до 7, чтобы version-6 cache с
  false review statuses не переиспользовался.

## Per-glyph diagnostic harness

Для каждого из 12 glyphs в `build/glyph-debug/U+XXXX-*` созданы:

```text
00_raster.png
01_mask.png
02_distance.png
03_skeleton_skeletonize.png
04_skeleton_medial_axis.png
05_selected_skeleton.png
06_graph_nodes_edges.svg
07_routes.svg
08_smoothed_strokes.svg
09_reconstructed_mask.png
10_mask_difference.png
11_overlay.svg
metrics.json
```

`metrics.json` содержит candidate metrics, selected method, graph/routing/final
metrics, coverage, inside-mask, components, endpoints, junctions, short edges,
micro loops, odd vertices, retrace, theoretical/excess retrace и quality decision.

## Какие regression tests добавлены

- Tiny variable-width mark доказывает local-radius quality reconstruction.
- Debug artifact test проверяет short-edge, micro-loop и retrace metrics.
- T-graph test проверяет theoretical minimum и zero excess retrace.
- Numeric corpus компилирует все 12 glyphs и проверяет:
  - coverage >= 0.94;
  - inside-mask >= 0.999;
  - expected component/route count для punctuation;
  - `quality_status=auto_passed`;
  - per-capital retrace bounds;
  - theoretical retrace > 0 и excess retrace = 0.

## Команды и проверки

- Baseline forced compile 12 glyphs при 2048 px/em с debug artifacts.
- Targeted pytest для quality, routing, debug, skeletonizer, candidate score,
  counter analysis и 12-glyph corpus.
- Final forced compile 12 glyphs при 2048 px/em в `build/glyph-debug/`.
- `make font-cache-rebuild FONT=assets/1.ttf BUILD=build/UPD_Plotter_11_block_2`.
- Warm strict-quality check 12 glyphs: 12 cache hits, 0 misses.
- `make lint`.
- `make test`.
- `make smoke`.
- Independent smoke G-code safety scan.

## Результ до / после

| Glyph | Coverage до | Coverage после | Components/routes | Retrace | Excess | Status после |
|---|---:|---:|---:|---:|---:|---|
| `;` | 0.609078 | 0.969844 | 2/2 | 0 | 0 | auto_passed |
| `.` | 0.632283 | 0.950799 | 1/1 | 0 | 0 | auto_passed |
| `…` | 0.632771 | 0.950428 | 3/3 | 0 | 0 | auto_passed |
| `:` | 0.635286 | 0.949118 | 2/2 | 0 | 0 | auto_passed |
| `?` | 0.678169 | 0.940719 | 2/2 | 0 | 0 | auto_passed |
| `Щ` | 0.884182 | 0.953198 | 1/1 | 0.228439 | 0 | auto_passed |
| `Ц` | 0.865277 | 0.951046 | 1/1 | 0.168092 | 0 | auto_passed |
| `Ш` | 0.919697 | 0.958051 | 1/1 | 0.256257 | 0 | auto_passed |
| `U` | 0.914971 | 0.956284 | 1/1 | 0.188806 | 0 | auto_passed |
| `И` | 0.914971 | 0.956284 | 1/1 | 0.188806 | 0 | auto_passed |
| `Й` | 0.905985 | 0.955476 | 2/2 | 0.166527 | 0 | auto_passed |
| `Ю` | 0.930506 | 0.993705 | 1/1 | 0.156193 | 0 | auto_passed |

Geometry, selected method, component count, route count и retrace ratio у target glyphs
не изменились. Изменилась только корректность final quality
measurement.

Canonical corpus result:

```text
glyphs: 169
auto_passed: 169
needs_review: 0
lost_components: 0
minimum_coverage: 0.918286 (щ)
minimum_inside_mask: 1.0
maximum_retrace_ratio: 0.444358 (ж)
glyphs_with_excess_retrace: 0
cache_version: 7
cache_valid: true
```

Quality gate:

- lint: passed;
- test: 250 passed;
- smoke: passed;
- smoke G-code safety: passed.

## Оставшиеся ограничения

- Retrace ratio у capitals не равен нулю, но exact matching доказывает,
  что excess retrace нет. Его уменьшение потребует больше pen lifts
  и нарушит one-route-per-component policy.
- Candidate selector всё ещё использует median-radius reconstruction для
  сравнительного scoring. В этом блоке его не меняли, чтобы не
  вносить широкие geometry changes вместе с quality bugfix.
- Full cold canonical rebuild занял примерно 18.7 минут и не показывал
  stage progress. Это подтверждает performance/benchmark limitation для блока 3;
  warm strict check занял 2.9 s.
