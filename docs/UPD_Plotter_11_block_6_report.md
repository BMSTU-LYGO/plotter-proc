# UPD_Plotter_11 — отчёт по блоку 6

## Что было сломано

`document_paginator.py` содержал около 2200 строк и одновременно отвечал за
page state, текст, таблицы, формулы, semantic shapes, raster/vector placement,
rotation, wrapping и debug bookkeeping.

Это не было runtime-багом, но делало image placement policy трудно
изолируемой и повышало риск будущих изменений paginator.

## Как воспроизводилось

До cleanup:

```text
src/plotter_processor/document_paginator.py: 2203 lines
```

Pure helpers для raster/vector placement находились внутри paginator:

```text
rotation bbox
rotation of image stroke points
scaled wrap padding
raster/vector placement
overlap fallback
placement report payload
serialized RectMM parsing
```

Часть поведения была покрыта integration tests, но rotation point, полный
placement payload и существующий hybrid overlap fallback не имели прямой
characterization coverage.

## Root cause

Image/vector placement развивался как набор внутренних helpers одного большого
модуля. Эти функции уже были cohesive и почти чистыми, но оставались связаны с
paginator только местом определения, а не необходимостью доступа к page state.

## Какие файлы изменены

- `src/plotter_processor/document_paginator.py`
- `src/plotter_processor/graphic_placement.py`
- `tests/test_image_page_scaling.py`
- `docs/UPD_Plotter_11_block_6_report.md`

## Что именно изменено

В новый `graphic_placement.py` без изменения вычислений вынесены:

- `rotated_size`;
- `rotate_image_point`;
- `scaled_padding`;
- `place_raster`;
- `place_vector`;
- общий private `_place_graphic`;
- `placement_record`;
- `payload_rect`.

Paginator импортирует эти функции и сохраняет прежние private aliases внутри
модуля, поэтому его внутренние call sites не переписывались и policy не
менялась.

Не изменялись:

- pagination algorithm;
- table splitting;
- image wrapping rules и thresholds;
- rotation math;
- A4/A5 transform;
- warnings/fallback names;
- placement/debug schema.

Размер основного модуля уменьшился:

```text
document_paginator.py: 2203 -> 1972 lines
graphic_placement.py:             257 lines
```

В этом блоке выполнен только один cohesive extraction. Следующие units не
переносились, потому что план требует проверять каждый перенос отдельно.

## Какие тесты добавлены

В `test_image_page_scaling.py` добавлены characterization tests:

- rotation 90° для фактической точки stroke и точный placement report payload;
- существующий hybrid overlap policy с fallback в `top_bottom` и точным
  warning `image_wrap_fallback_top_bottom`.

Tests теперь импортируют placement helpers прямо из нового модуля, поэтому unit
проверяется независимо от paginator orchestration.

Существующие image anchor, mixed layout, scaling и vectorizer regressions также
были прогнаны после extraction.

## Какие команды прогнаны

Baseline и after выполнялись одной и той же полной командой:

```bash
.venv/bin/python -m plotter_processor run plotter_pipeline_full_test.docx \
  --font assets/1.ttf --font-mode centerline --page A5 --size normal \
  --document-layout hybrid --latex mathtext --latex-stroke-mode centerline \
  --strict-latex-quality --connections safe --images auto --image-debug \
  --layout-debug --semantic-debug --connection-debug --page-numbers \
  --page-pause-seconds 1 --park-corner top_right \
  --output-dir build/UPD_Plotter_11_block_6_baseline

.venv/bin/python -m plotter_processor run plotter_pipeline_full_test.docx \
  ... \
  --output-dir build/UPD_Plotter_11_block_6_after

.venv/bin/pytest -q tests/test_image_page_scaling.py \
  tests/test_mixed_layout_regression.py tests/test_docx_image_anchors.py \
  tests/test_image_vectorizer.py

make lint
make test
make smoke
make font-cache-status FONT=assets/1.ttf
git diff --check
```

Дополнительно сравнивались page count, report layout geometry, root/page
warnings и SHA-256 для placements, paths, G-code, previews и debug artifacts.
49 G-code файлов проверены на heating, homing, extrusion и non-finite
coordinate commands.

## Результат до / после

| Проверка | Baseline | After |
|---|---:|---:|
| Page count | 20 | 20 |
| Root warnings | 0 | 0 |
| Page warnings | identical | identical |
| Document layout geometry | baseline | identical |
| `placement.json` | baseline | byte-identical |
| `trace.json` | baseline | byte-identical |
| Page `paths.json` | 20 | 20 byte-identical |
| Page G-code | 20 | 20 byte-identical |
| Root G-code | baseline | byte-identical |
| Layout debug files | 5 | 5 byte-identical |
| Semantic debug files | 6 | 6 byte-identical |
| Connection debug files | 40 | 40 byte-identical |
| Image debug files | 3 | 3 byte-identical |
| Preview SVG files | 23 | 23 byte-identical |

Aggregate hashes:

```text
root G-code:
1d0642fb8e285beacb7e0e8a29e7abe6a2f0c69b9863fcb9eedc4d3c67426816

all page paths:
349071f6d2c4e5df4bc69d962acf960ae4f841abb75aeef2e32e2e82fb1f3550

layout debug:
bd1be56a2a4043176efe37498dbf6b93a759cbf91f70045c957f6d80df48d7d1

all compared debug artifacts:
cb136c1b7d44e51884ca0cf6fa3114e46061e253af72cec3794611772da8232c
```

Quality gate:

```text
lint: passed
test: 268 passed
smoke: passed
font cache: version 7, 169 glyphs, valid
G-code safety: 49 files checked, 0 unsafe
git diff --check: passed
```

Root `report.json` целиком побайтно не сравнивался, поскольку он закономерно
содержит разные output-directory paths и runtime performance timings. Все
требуемые стабильные report fields сравнивались отдельно.

## Оставшиеся ограничения

- Главная orchestration-функция `paginate_document` всё ещё крупная; этот блок
  сознательно не превращался в rewrite.
- Page state, text, table, math и debug collection остаются в paginator и могут
  быть кандидатами для отдельных будущих extraction с таким же baseline gate.
- Новый модуль сохраняет существующую image wrapping policy, включая её
  approximations и fallback warnings; качество policy в этом cleanup не
  пересматривалось.
- Private aliases в paginator оставлены для минимального diff и совместимости
  внутренних/исторических imports. Новый прямой API покрыт unit tests.
