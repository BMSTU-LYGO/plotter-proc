# UPD_Plotter_11 — отчёт по блоку 4

## Что было сломано

- F-007: `extract` для DOCX выводил только top-level paragraphs,
  теряя table cells и OMML expression.
- F-011: DOCX сохранял позицию tab stop, но терял вид
  `center`, `right` и `decimal`. До paginator tab также заменялся
  пробелами в `normalize_text`.
- F-010: safe/aggressive давали byte-identical output на audit stress
  corpus, поэтому не было доказательства реальной behavioral boundary.

## Как воспроизводилось

- Control `extract plotter_pipeline_full_test.docx` давал 47 lines,
  не включал текст 104 logical table cells и OMML formula.
- Минимальный DOCX `paragraph → merged/repeated-header table → OMML →
  paragraph` терял все между двумя paragraph.
- Minimal paragraphs с одинаковым stop сохраняли только
  `tab_stops_mm`; reader выдавал `docx_tab_stop_approximated:center/right/decimal`.
- Audit connection corpus повторно дал 105 accepted / 405 rejected
  и connector length 108.704851 mm в обоих режимах.

Regression tests для extract и tab model/API падали до production changes.
Интеграционный tab + active image-zone test отдельно выявил
потерю `\t` в normalization.

## Root cause

- `document_reader.py` имел отдельный legacy DOCX path через
  `python-docx.paragraphs` вместо уже готовой structured source model.
- `_ParagraphFormat` и `SourceParagraph` хранили только `float`
  position, поэтому alignment semantics не могла дойти до layout.
- `normalize_text` безусловно заменял tab на четыре пробела.
- Flow-around-image path принимал plain string и не мог применить
  typed tab semantics.
- Aggressive mode уже имел реальное отличие: он расширяет
  distance, angle и vertical thresholds. Audit corpus просто не содержал
  пары на этой границе.

## Какие файлы изменены

- `src/plotter_processor/document_reader.py`
- `src/plotter_processor/document_models.py`
- `src/plotter_processor/docx_document_reader.py`
- `src/plotter_processor/text_normalizer.py`
- `src/plotter_processor/paragraph_layout.py`
- `src/plotter_processor/document_paginator.py`
- `src/plotter_processor/table_layout.py`
- `src/plotter_processor/document_image_layout.py`
- `tests/test_document_reader.py`
- `tests/test_docx_paragraph_formatting.py`
- `tests/test_paragraph_layout.py`
- `tests/test_tab_stops.py`
- `tests/test_handwriting.py`
- `README.md`
- `docs/UPD_Plotter_11_block_4_report.md`

## Что именно изменено

- `extract` теперь делает текстовую проекцию `SourceDocument`
  в source-page/source-order.
- Table cells выводятся по `(row, column)`. Structured table уже
  содержит только logical merged-cell owners, поэтому duplicate text нет.
- Repeated header берётся из source table один раз, а не из
  pagination fragments.
- `SourceMathElement.expression` выводится как stable LaTeX-like OMML text.
- Добавлен `SourceTabStop(position_mm, alignment)` для `left`, `center`,
  `right`, `decimal`; legacy `tab_stops_mm` сохранён для compatibility.
- Layout измеряет advance следующего token через font metrics.
  Right выравнивает token end, center — midpoint, decimal — начало
  `.` или `,`.
- Preserve/hybrid умножает source stop на `PageTransform.scale`;
  reflow сохраняет source millimetres.
- Structured paragraphs с tab metadata сохраняют `\t` в normalization.
- Typed-tab paragraph с active image zone консервативно размещается
  ниже zone, затем проходит через typed millimetre layout.
- README фиксирует extract contract и точную safe/aggressive boundary.

Global thresholds, collision policy, punctuation guards, machine workspace и
font geometry не менялись.

## Какие тесты добавлены

- DOCX extract reading order с paragraph, horizontal merged cell, repeated
  header, normal cells, OMML fraction и paragraph after math.
- Reader-to-layout DOCX fixture для left/center/right/decimal с измерением
  glyph bounds.
- Numeric paragraph tests: left edge, midpoint, right edge и decimal separator
  совпадают с stop.
- A4→A5 test: `PageTransform.scale=0.7392996109`; source stop 40 mm
  превращается в target x `39.571984` при left margin 10 mm.
- Integration test доказывает typed right-tab alignment при активной
  anchored-image exclusion zone.
- Targeted connection test: gap 2.5 mm отклоняется safe по
  distance и принимается aggressive.
- Negative connection tests: aggressive по-прежнему отклоняет
  collision и punctuation.

## Какие команды прогнаны

```bash
.venv/bin/python -m plotter_processor extract plotter_pipeline_full_test.docx \
  --output build/UPD_Plotter_11_block_4_extracted.txt

.venv/bin/python -m plotter_processor run plotter_pipeline_full_test.docx \
  ... --document-layout hybrid --connections safe \
  --output-dir build/UPD_Plotter_11_block_4_control

.venv/bin/python -m plotter_processor run report/analysis/connection-corpus.txt \
  ... --connections safe \
  --output-dir build/UPD_Plotter_11_block_4_connections_safe

.venv/bin/python -m plotter_processor run report/analysis/connection-corpus.txt \
  ... --connections aggressive \
  --output-dir build/UPD_Plotter_11_block_4_connections_aggressive

make lint
make test
make smoke
make font-cache-status FONT=assets/1.ttf
git diff --check
```

30 generated G-code files дополнительно проверены на отсутствие
heating, homing, extrusion и non-finite coordinates.

## Результат до / после

| Проверка | До | После |
|---|---:|---:|
| Control extract lines | 47 | 150 |
| Extracted logical table cells | 0 | 104 |
| Extracted OMML expressions | 0 | 1 |
| Control tab approximation warnings | 2 | 0 |
| Control pages | 20 | 20 |
| Control strokes / points | 6453 / 111714 | 6453 / 111714 |
| Control draw distance | 71014.932 mm | 71014.932 mm |
| Layout overlap / overflow | 0 / 0 | 0 / 0 |
| Connections accepted / rejected | 1359 / 4388 | 1359 / 4388 |

Правильная tab geometry изменила только page 5 control job.
Travel distance выросла с 54895.811 до 54960.241 mm, потому что
tabbed paragraph теперь без overlap размещается ниже active image zone.
Draw geometry/count и page count не ухудшились.

Audit stress corpus остался byte-identical:

```text
safe:       510 pairs, 105 accepted, 405 rejected, 108.704851 mm
aggressive: 510 pairs, 105 accepted, 405 rejected, 108.704851 mm
paths SHA256 (both): dc4b0637996aa7667c3aa840a90790b4c2bda49964ba3781277930b51a5ee85d
```

Targeted boundary corpus:

```text
safe:       rejected (distance)
aggressive: accepted, 1 connector
aggressive + crossing obstacle: rejected (collision)
aggressive + punctuation:       rejected (punctuation_rule)
```

Quality gate:

```text
lint: passed
test: 262 passed
smoke: passed
font cache: version 7, 169 glyphs, valid
G-code safety: passed
```

## Оставшиеся ограничения

- Extract выводит только supported textual OMML representation.
  Unsupported OMML nodes остаются ограничением parser.
- Nested DOCX tables по-прежнему не поддерживаются structured
  reader и не расширялись ради extract.
- Decimal tab выравнивает первый `.` или `,` в следующем
  token. Если separator нет, token выравнивается по right edge.
- `bar` tabs не рисуют vertical bar; unknown tab kinds по-прежнему
  дают controlled left approximation warning.
- Aggressive не обязан отличаться на каждом тексте. Он остаётся
  safe относительно collision, punctuation и backward-motion guards.
