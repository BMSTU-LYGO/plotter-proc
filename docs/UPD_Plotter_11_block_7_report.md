# UPD_Plotter_11 — отчёт по блоку 7

## Что было сломано

Исходный аудит не мог завершить оба PDF centerline job-а: preserve и reflow
падали на visual math element `page-001-math-001`, edge 20, из-за расхождения
общего endpoint примерно на `0.041667`.

Также требовалось повторно подтвердить после всех исправлений:

- основной DOCX centerline pipeline;
- outline control;
- connections off/safe/aggressive;
- byte determinism paths/preview/G-code;
- warm performance;
- возможность полного cold benchmark.

## Как воспроизводилось

В audit artifacts оба PDF report имели:

```text
status: error
Non-adjacent route jump at edge 20
Point(... y=1.75) != Point(... y=1.7916666666666665)
```

Нормальные PDF preview и G-code не формировались.

Исходный warm DOCX baseline составлял `126.564 s`. Исходная cold попытка не
завершилась в audit window около 12 минут.

## Root cause

Этот блок не менял production-код. Он проверял исправления предыдущих блоков.

Критический PDF root cause был устранён в блоке 1: graph topology и smoothed
geometry раньше расходились в координатах общего узла. После canonical endpoint
normalization route assembler получает непрерывную geometry, не соединяя
несвязанные graph nodes.

Остальные проверяемые свойства опираются на исправления блоков 2–6:
centerline quality, performance indices, extract/tabs, deterministic provenance,
реальные report metrics и policy-neutral paginator extraction.

## Какие файлы изменены

- `docs/UPD_Plotter_11_block_7_report.md`

Production-код, configs и tests в блоке 7 не изменялись.

## Что именно изменено

Создан новый полный набор интеграционных artifacts:

- `build/UPD_Plotter_11_block_7_docx_primary_A`;
- `build/UPD_Plotter_11_block_7_docx_primary_B`;
- `build/UPD_Plotter_11_block_7_docx_outline`;
- `build/UPD_Plotter_11_block_7_pdf_preserve`;
- `build/UPD_Plotter_11_block_7_pdf_reflow`;
- `build/UPD_Plotter_11_block_7_connections_off`;
- `build/UPD_Plotter_11_block_7_connections_safe`;
- `build/UPD_Plotter_11_block_7_connections_aggressive`;
- `build/UPD_Plotter_11_block_7_performance/warm.json` и три warm run-а.

Два primary job-а и три warm job-а дополнительно сравнены без удаления или
нормализации `source_path`: после F-008 serialized paths полностью стабильны.

## Какие тесты добавлены

Новые regression tests в блоке 7 не добавлялись: интеграционная матрица не
обнаружила нового дефекта. Использованы 268 regression tests, созданные в
предыдущих блоках, и полные реальные DOCX/PDF fixtures.

## Какие команды прогнаны

### DOCX primary и determinism repeat

```bash
.venv/bin/python -m plotter_processor run plotter_pipeline_full_test.docx \
  --font assets/1.ttf --font-mode centerline --page A5 --size normal \
  --document-layout hybrid --latex mathtext --latex-stroke-mode centerline \
  --strict-latex-quality --connections safe --images auto --image-debug \
  --layout-debug --semantic-debug --connection-debug --page-numbers \
  --page-pause-seconds 1 --park-corner top_right \
  --output-dir build/UPD_Plotter_11_block_7_docx_primary_A

# Та же команда с output-dir ..._docx_primary_B
```

### DOCX outline

```bash
.venv/bin/python -m plotter_processor run plotter_pipeline_full_test.docx \
  --font assets/1.ttf --font-mode outline --page A5 --size normal \
  --document-layout hybrid --latex mathtext --latex-stroke-mode outline \
  --connections off --images auto --image-debug --layout-debug \
  --semantic-debug --latex-debug --page-numbers --page-pause-seconds 1 \
  --park-corner top_right \
  --output-dir build/UPD_Plotter_11_block_7_docx_outline
```

### PDF preserve/reflow

```bash
.venv/bin/python -m plotter_processor run plotter_pipeline_full_test.pdf \
  --font assets/1.ttf --font-mode centerline --page A5 --size normal \
  --document-layout preserve --pdf-math auto --math-debug --layout-debug \
  --semantic-debug --images auto --image-debug --page-numbers \
  --page-pause-seconds 1 --park-corner top_right \
  --output-dir build/UPD_Plotter_11_block_7_pdf_preserve

# Та же команда с --document-layout reflow и output-dir ..._pdf_reflow
```

### Connections

```bash
.venv/bin/python -m plotter_processor run report/analysis/connection-corpus.txt \
  --font assets/1.ttf --font-mode centerline --page A5 --size normal \
  --document-layout reflow --connections <off|safe|aggressive> \
  --connection-debug --no-page-numbers --page-pause-seconds 1 \
  --output-dir build/UPD_Plotter_11_block_7_connections_<mode>
```

### Performance и gates

```bash
.venv/bin/python tools/benchmark_conversion.py plotter_pipeline_full_test.docx \
  --font assets/1.ttf --warm-only --warm-runs 3 --connections safe \
  --page A5 --size normal --font-mode centerline --document-layout hybrid \
  --output build/UPD_Plotter_11_block_7_performance/warm.json

make lint
make test
make smoke
make font-cache-status FONT=assets/1.ttf
git diff --check
```

Отдельно был запущен conditional cold+warm benchmark на temporary cache. Cold
`font_compile` не завершился за 13+ минут, поэтому попытка была остановлена как
непрактичная. Canonical `1-font-cache` не удалялся и остался валиден.

## Результат до / после

### Основные документы

| Job | Audit | Block 7 | Pages | Strokes | Points |
|---|---|---|---:|---:|---:|
| DOCX primary | ok | ok | 20 | 6453 | 111714 |
| DOCX outline | ok | ok | 20 | 11840 | 241964 |
| PDF preserve | error edge 20 | ok | 32 | 8215 | 104939 |
| PDF reflow | error edge 20 | ok | 33 | 8217 | 104957 |

DOCX primary сохранил:

```text
draw: 71014.932 mm
travel: 54960.241 mm
warnings: 0
overlaps: 0
```

Оба PDF job-а отрисовали `3` visual math expressions, `83` math strokes и
`996` math points без fallback/needs_review. Reflow имеет `0` remaining
overlaps. Preserve завершился корректно, но сохраняет исходные визуальные
наложения (`1634.989986 mm²`) по контракту preserve.

### Connections

| Mode | Accepted / total | Strokes | Connector length | paths SHA-256 |
|---|---:|---:|---:|---|
| off | 0 / 510 | 634 | 0 mm | `a70f08f2...` |
| safe | 105 / 510 | 529 | 108.704851 mm | `dc4b0637...` |
| aggressive | 105 / 510 | 529 | 108.704851 mm | `dc4b0637...` |

Safe/aggressive geometry на audit corpus одинакова, но rejection distribution
различается. Aggressive-only boundary подтверждён targeted regression из блока
4; collision, punctuation и backward-motion guards остаются активными.

### Determinism

Два primary job-а:

```text
20/20 paths.json: byte-identical
20/20 page previews: byte-identical
20/20 page G-code: byte-identical
root preview: byte-identical
root G-code: byte-identical
```

Root hashes:

```text
plotter-preview.svg:
50dcdc5e90cd985bd9469cb33e8f541d7c688873fff142887258fde087049d4a

output.gcode:
1d0642fb8e285beacb7e0e8a29e7abe6a2f0c69b9863fcb9eedc4d3c67426816
```

Все три performance run-а также дали одинаковые paths, previews и G-code.

### Performance

| Warm run | Wall | Handwriting | Simplification | Font cache |
|---:|---:|---:|---:|---|
| 1 | 66.638 s | 27.808 s | 20.188 s | 122 hits / 0 misses |
| 2 | 61.971 s | 27.853 s | 20.177 s | 122 hits / 0 misses |
| 3 | 68.234 s | 30.765 s | 23.582 s | 122 hits / 0 misses |
| median | 66.638 s | — | — | warm |

По отношению к audit baseline `126.564 s` median улучшен на `47.35%`.
Относительно блока 3 (`65.779 s`) изменение `+1.31%`, то есть результат
стабилен в обычном шуме workstation benchmark.

Cold full-font compile не завершился за 13+ минут и не включён в числовую
статистику. Условие плана «если стал практически выполним» не выполнено.

### Quality gate

```text
lint: passed
test: 268 passed
smoke: passed
font cache: version 7, 169 glyphs, valid
G-code safety: 203 files checked, 0 unsafe
git diff --check: passed
```

## Оставшиеся ограничения

- Cold compilation полного 122-glyph working set на временный cache остаётся
  непрактично долгой: более 13 минут без завершения `font_compile`.
- PDF preserve намеренно сохраняет исходное расположение и связанные visual
  overlaps; для устранения overlaps предназначен reflow.
- PDF math detection оставляет low-confidence warnings и rasterizes complex
  drawings; route больше не падает, но это не полная semantic reconstruction.
- Safe/aggressive совпадают на исходном audit corpus; различие режимов
  подтверждается отдельным targeted boundary fixture, а не этим текстом.
- Outline control ожидаемо содержит предупреждение о прохождении обеих границ
  заполненных TTF strokes.
