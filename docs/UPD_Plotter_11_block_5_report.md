# UPD_Plotter_11 — отчёт по блоку 5

## Что было сломано

- `centerline.worst_glyphs` всегда был пустым, даже когда глифы требовали
  проверки или имели заметный retrace.
- `centerline.retraced_length_mm` всегда содержал `0.0`, хотя отдельные
  маршруты повторно проходили существующие skeleton edges.
- `classification_conflicts` и `duplicate_primitives_suppressed` выдавались
  как фиктивные нули без измерения.
- В отчёте не хватало полезных счётчиков table split/repeated header/shared
  border и отброшенных микрошрихов изображений.
- `paths.json` содержал job-local путь `output-*/extracted-assets/...`, поэтому
  одинаковые запуски в разных output directories отличались побайтно.
- Контракт команды `gcode` не объяснял различие metadata-комментариев с полным
  `run`.

## Как воспроизводилось

Исходные audit jobs показывали:

```text
needs_review: 12
retraced_length_mm: 0.0
worst_glyphs: []
classification_conflicts: 0
duplicate_primitives_suppressed: 0
```

Два одинаковых job-а имели равную geometry, но разные `paths.json` из-за:

```text
output-A/extracted-assets/image-001-<hash>.png
output-B/extracted-assets/image-001-<hash>.png
```

Повторный `gcode` из page `paths.json` давал те же non-comment команды, но
не содержал комментарии полного pipeline о странице, motion profile и времени.

Перед production-изменениями добавленные regression tests падали на
отсутствующем `_semantic_report`, старой сигнатуре `_centerline_report` и
разных байтах provenance.

## Root cause

- `_centerline_report` не агрегировал уже доступные `CenterlineGlyph.quality`
  и `CenterlineStroke.retraced_length_font_units`.
- Report assembly не анализировал итоговые semantic strokes и подставлял
  константы.
- Paginator создавал table/image данные, но не прокидывал нужные audit metrics.
- Serializer записывал runtime filesystem path без нормализации extracted asset
  identity.
- Полный pipeline обогащает G-code job-local комментариями после общей
  генерации, а subcommand по одному `paths.json` не может восстановить эти
  сведения.

## Какие файлы изменены

- `src/plotter_processor/pipeline.py`
- `src/plotter_processor/semantic_metrics.py`
- `src/plotter_processor/semantic_debug.py`
- `src/plotter_processor/path_builder.py`
- `src/plotter_processor/table_layout.py`
- `src/plotter_processor/document_paginator.py`
- `src/plotter_processor/image_vectorizer.py`
- `src/plotter_processor/document_image_layout.py`
- `src/plotter_processor/cli.py`
- `tests/test_report_metrics.py`
- `tests/test_path_builder.py`
- `tests/test_gcode_exporter.py`
- `tests/test_table_pagination.py`
- `tests/test_image_vectorizer.py`
- `README.md`
- `docs/UPD_Plotter_11_block_5_report.md`

## Что именно изменено

### Centerline/report metrics

- `retraced_length_mm` считается по фактически размещённым глифам и их
  `scale_mm_per_font_unit`; отдельно сохраняется aggregate compiled-font
  `retraced_length_font_units`.
- `retraced_length_measured` явно показывает доступность измерения.
- `worst_glyphs` содержит top-10 проблемных/retraced compiled glyphs со всеми
  требуемыми полями: glyph, codepoint, coverage, inside-mask, components,
  routes before/after, retrace ratio, method, status и warning.
- Semantic conflicts измеряются как разные semantic roles у одной и той же
  направленно-независимой geometry.
- Поскольку отдельного suppression pass нет,
  `duplicate_primitives_suppressed=null` и
  `duplicate_primitives_suppressed_measured=false`; fake-zero удалён.
- Те же semantic metrics используются в `semantic-debug/classification.json`.

### Таблицы и изображения

- Добавлены реальные `table_splits`, `repeated_headers_emitted` и
  `shared_borders_suppressed`.
- `border_count` теперь считает только table borders, без underline decorations.
- Добавлен `image_micro_strokes_suppressed`; существующие `image_strokes` и
  image cache hits/misses сохраняются.

### Deterministic paths.json

Runtime-путь extracted asset сериализуется как стабильный logical URI:

```text
asset://image-001-be58d90f81f2.png
```

Имя уже содержит content hash. `element_id`, `element_type` и logical URI
сохраняют provenance, не привязывая bytes к output directory.

### G-code contract

Выбран вариант A: subcommand гарантирует functional equivalence. Для одного
`paths.json` и machine config все non-comment motion commands совпадают с
page-level G-code полного `run`. Byte identity не обещается из-за job-local
metadata comments. Контракт добавлен в README, CLI help и regression test.

## Какие тесты добавлены

- Synthetic retraced `needs_review` glyph проверяет ненулевой retrace и полный
  `worst_glyphs` payload.
- Два одинаковых semantic primitives с разными ролями дают один измеренный
  classification conflict, а unavailable suppression остаётся `null`.
- Два `PathDocument` с одинаковым extracted asset в `output-A/output-B`
  сериализуются в одинаковые bytes и стабильный `asset://` URI.
- Full-run metadata и subcommand G-code сравниваются по non-comment commands.
- Multipage table regression проверяет split count, emitted repeated headers и
  suppressed shared borders.
- Image vectorizer проверяет наличие измеренного micro-stroke counter.

## Какие команды прогнаны

```bash
.venv/bin/pytest -q tests/test_report_metrics.py tests/test_path_builder.py \
  tests/test_gcode_exporter.py

.venv/bin/pytest -q tests/test_report_metrics.py tests/test_path_builder.py \
  tests/test_gcode_exporter.py tests/test_image_vectorizer.py \
  tests/test_table_pagination.py tests/test_table_auto_row_height.py \
  tests/test_table_scaling.py tests/test_cli.py

.venv/bin/python -m plotter_processor run \
  tests/fixtures/update_7/images/image_absolute.docx ... \
  --output-dir build/UPD_Plotter_11_block_5_determinism_A

.venv/bin/python -m plotter_processor run \
  tests/fixtures/update_7/images/image_absolute.docx ... \
  --output-dir build/UPD_Plotter_11_block_5_determinism_B

.venv/bin/python -m plotter_processor run examples/centerline_glyph_corpus.txt \
  --font assets/1.ttf --page A5 --font-mode centerline --no-page-numbers \
  --output-dir build/UPD_Plotter_11_block_5_metrics

.venv/bin/python -m plotter_processor gcode \
  build/UPD_Plotter_11_block_5_determinism_A/paths.json \
  --output build/UPD_Plotter_11_block_5_regenerated.gcode

make lint
make test
make smoke
make font-cache-status FONT=assets/1.ttf
git diff --check
```

10 G-code artifacts дополнительно проверены на heating, homing, extrusion и
non-finite coordinate commands.

## Результат до / после

| Проверка | До | После |
|---|---:|---:|
| Audit `worst_glyphs` | 0 записей | top-10 заполнен |
| Audit aggregate retrace | fake `0.0 mm` | measured actual-layout value |
| Centerline corpus retrace | unavailable | `107.453619 mm` |
| Centerline corpus compiled retrace | unavailable | `34867.192112 font units` |
| Semantic conflicts | hard-coded `0` | измеренное значение |
| Duplicate suppression | hard-coded `0` | `null`, measured=false |
| Image micro strokes | отсутствовало | measured (`7` на fixture) |
| paths SHA in output A/B | разные | одинаковые `3c07de2e...` |
| Regenerated G-code bytes | отличаются | отличаются по контракту A |
| Regenerated motion commands | совпадают | совпадают и покрыты тестом |
| Test suite | 262 passed | 266 passed |

Итоговый gate:

```text
lint: passed
test: 266 passed
smoke: passed
font cache: version 7, 169 glyphs, valid
G-code safety: 10 files checked, 0 unsafe
```

## Оставшиеся ограничения

- `worst_glyphs` ограничен десятью compiled glyphs и не ранжируется по частоте
  использования в документе; физический retrace при этом считается по всем
  фактическим размещениям.
- Semantic conflict требует совпадения geometry после округления до `1e-6`;
  near-overlap без одинаковых точек конфликтом не считается.
- Реального semantic duplicate suppression pass пока нет, поэтому значение
  честно остаётся unavailable (`null`).
- `shared_borders_suppressed` измеряет невыведенные cell-grid edges, а не
  дальнейшее объединение коллинеарных strokes optimizer-ом.
- Logical URI стабилизирует extracted assets. Обычный внешний `source_path`
  сохраняется без изменения, чтобы не терять пользовательский provenance.
- `gcode` subcommand не восстанавливает page/job metadata, которого нет в
  `paths.json`; byte identity сознательно не является контрактом.
