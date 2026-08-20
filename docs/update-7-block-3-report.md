# Update 7 — отчёт по блоку 3

Фактический HEAD при финальной проверке:
`51e19e76287b681f1f77a90a23c91b237c0c247d`.

## Реализовано

- backward-compatible styled text model с runs и underline metadata;
- DOCX single, double и words-only underline после окончательного text layout;
- PDF underline classifier и generic semantic lines;
- DOCX VML arrows и PDF shaft+triangle/open-V detector;
- одноштриховые shafts и открытые V-heads с сохранением направления;
- structured DOCX tables, column widths, horizontal/vertical merged cells;
- размещение текста внутри cells и underline внутри таблиц;
- дедупликация shared borders по logical cell ownership;
- разбиение длинной таблицы только между строками;
- повтор header-row на последующих страницах;
- консервативное распознавание line-grid PDF tables с поглощением grid/text;
- semantic path order: directed/decorative strokes не разворачиваются optimizer;
- `--semantic-debug` и раздел `semantic_objects` в отчёте.

Основные новые модули: `text_decorations.py`, `shape_layout.py`,
`table_layout.py`, `semantic_debug.py`; расширены source models, DOCX/PDF
readers, paginator, optimizer, CLI, config, fixtures и tests.

## Демонстрационные результаты

Общая сводка: `build/update_7/candidate/block_3/demo-summary.json`.

| Сценарий | Результат |
|---|---:|
| DOCX underline strokes | 6 |
| PDF arrows | 2 |
| Simple DOCX table | 1 table / 9 cells |
| Merged DOCX table | 1 table / 14 logical cells |
| Multipage DOCX table | 108 cells / 2 pages |
| PDF line-grid table | 1 table / 9 cells |
| Classification conflicts | 0 |

Каждый demo содержит `plotter-preview.svg`, `paths.json`, `report.json`,
безопасный G-code и `semantic-debug`.

## Проверка

```bash
.venv/bin/python tools/generate_update_7_fixtures.py
.venv/bin/python tools/run_update_7_block_3_demo.py --font assets/1.ttf
make lint
make test
.venv/bin/python -m plotter_processor --help
.venv/bin/python -m plotter_processor run --help
.venv/bin/python -m plotter_processor compose --help
```

Полный test suite: `204 passed`. Lint чистый. Два одинаковых запуска simple
table создали byte-identical `paths.json`, `output.gcode` и
`plotter-preview.svg`. Все demo G-code прошли проверку отсутствия нагрева,
extrusion, `G28`, NaN и Infinity.

## Baseline

Baseline терял underline style, превращал DOCX tables в плоский текст с
`docx_table_layout_simplified`, не имел semantic arrow/table models и мог
растрировать filled PDF arrowhead. Candidate создаёт отдельные semantic
objects, поглощает использованные PDF primitives и рисует shared borders один
раз.

## Ограничения

- borderless PDF tables не распознаются;
- PDF detector поддерживает только регулярные line-based grids;
- nested/floating tables, diagonal borders, vertical text и сложные exact row
  heights пока дают controlled warning или не поддерживаются;
- DrawingML/SmartArt и custom arrowheads не поддержаны полностью;
- gradients и сложные filled shapes остаются raster fallback;
- dashed/dotted underline аппроксимируется single underline с warning;
- таблица использует единый text scale документа, без отдельного auto-fit;
- физический dry-run на подключённом плоттере не выполнялся.

Блок 3 закончен. Все три блока UPD_Plotter_7 реализованы и проверены.
