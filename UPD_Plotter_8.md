# UPD_Plotter_7

## Подробная инструкция для Codex: centerline-LaTeX, сохранение положения рисунков, обтекание текстом, линии, стрелки и таблицы

Рабочий репозиторий: `https://github.com/BMSTU-LYGO/plotter-proc`  
Базовая ветка: `master`  
Последний видимый merge commit на момент составления плана: `c7e2296` (`Merge pull request #5 from BMSTU-LYGO/upd/document-images-pagination-latex`, 1 августа 2026 года)  
Рекомендуемая рабочая ветка: `upd/plotter-7-layout-math-lines-tables`  
Имя итогового документа: `UPD_Plotter_7.md`

> Важно: Codex не должен слепо считать SHA `c7e2296` актуальным. Перед началом работы нужно выполнить `git fetch`, обновить локальный `master`, записать реальный `git rev-parse HEAD` в отчёт и адаптировать названия файлов, если структура репозитория изменилась.

---

# 0. Главная цель обновления

В обновлении нужно последовательно реализовать три крупных блока.

1. **Хороший LaTeX в centerline-режиме**, включая печать формул, находящихся внутри PDF.
2. **Более точное размещение рисунков**, сохранение их исходного положения и обтекание текстом.
3. **Поддержка линий, подчёркнутого текста, стрелок и таблиц** в DOCX и PDF.

Работу выполнять строго по блокам. После каждого блока Codex обязан:

- остановить реализацию следующего блока;
- прогнать unit-, integration- и regression-тесты;
- создать демонстрационные входные документы;
- создать SVG-preview, `paths.json`, `report.json` и G-code;
- сравнить результат с baseline;
- написать пользователю отдельный подробный отчёт;
- честно перечислить ограничения;
- только после публикации отчёта переходить к следующему блоку.

Нельзя присылать пользователю сообщение вида «готово» без доказательств. В каждом отчёте должны быть:

- фактический SHA commit;
- список изменённых файлов;
- точные команды запуска;
- пути к артефактам;
- результаты тестов;
- метрики до/после;
- список известных ограничений;
- минимум один визуальный пример для каждого поддержанного сценария.

---

# 1. Текущее состояние проекта, которое необходимо учитывать

На текущем `master` уже реализованы важные части, которые нельзя дублировать или выбрасывать.

## 1.1. Уже существующий общий pipeline

Основной pipeline находится в:

- `src/plotter_processor/pipeline.py`;
- `src/plotter_processor/document_paginator.py`;
- `src/plotter_processor/document_image_layout.py`;
- `src/plotter_processor/structured_document_reader.py`;
- `src/plotter_processor/document_models.py`.

Текущий pipeline уже умеет:

- читать TXT, DOCX и PDF;
- извлекать текст;
- извлекать растровые изображения;
- извлекать часть PDF-векторной графики;
- векторизовать изображения в `outline` или `centerline`;
- разбивать документ на страницы;
- добавлять номера страниц;
- создавать отдельный G-code для каждой страницы;
- парковать перо между страницами;
- добавлять паузу на смену листа;
- создавать общий `job.json`;
- сохранять безопасный G-code без нагрева и extrusion.

## 1.2. Уже существующий LaTeX

В проекте уже присутствуют:

- `src/plotter_processor/latex_parser.py`;
- `src/plotter_processor/latex_renderer.py`;
- `src/plotter_processor/latex_layout.py`;
- вызов LaTeX-layout из `document_paginator.py`;
- параметры LaTeX в `configs/layout.yaml`;
- CLI-флаги `--latex auto|mathtext|off` и `--latex-debug`.

Текущий LaTeX pipeline примерно такой:

```text
LaTeX delimiters in text
    -> parse_latex_runs
    -> matplotlib MathText / TextPath
    -> filled glyph outlines
    -> flatten curves
    -> PlotterStroke with segment_types=("latex-outline",)
```

Главное ограничение: **формула рисуется как контур заполненного шрифта**, а не как центральная линия. Поэтому символы получаются двойными, число штрихов и подъёмов пера велико, а визуально формула отличается от рукописного centerline-текста.

Дополнительное ограничение: в `pipeline.py` LaTeX для PDF сейчас явно выключается:

```python
if options.input_path.suffix.lower() == ".pdf":
    latex_mode = "off"
```

Это сделано потому, что из PDF обычно нельзя восстановить исходную строку LaTeX. Однако для задачи плоттера не обязательно восстанавливать исходный LaTeX: достаточно корректно распознать область формулы и воспроизвести её визуальную геометрию центральными линиями.

## 1.3. Уже существующая работа с изображениями

В проекте уже присутствуют:

- `src/plotter_processor/image_preprocessor.py`;
- `src/plotter_processor/image_vectorizer.py`;
- `SourceRasterImageElement`;
- `SourceVectorElement`;
- извлечение bbox из PDF;
- частичное извлечение координат floating image из DOCX.

Текущий reflow-layout размещает изображения следующим образом:

```python
x = left + (usable_width - width) / 2
```

То есть рисунок почти всегда центрируется по ширине независимо от исходного положения. Поле `bbox` сохраняется в модели, но практически не участвует в реальном размещении. CLI уже содержит `--pdf-layout reflow|preserve`, однако текущий pipeline в основном сохраняет это значение в отчёт и не реализует полноценный режим сохранения координат.

## 1.4. Уже существующие линии и векторные объекты PDF

`pdf_document_reader.py` уже умеет извлекать часть `page.get_drawings()`:

- line;
- rectangle;
- quadrilateral/polyline;
- cubic Bézier.

Но есть ограничения:

- сложные drawing с fill часто растрируются;
- залитый треугольник наконечника стрелки может стать raster image;
- линии не классифицируются как подчёркивание, граница таблицы или стрелка;
- несколько частей одного объекта не группируются;
- нет семантической модели таблицы;
- нет сохранения стиля DOCX-run, включая underline.

## 1.5. Текущее состояние DOCX-таблиц и формул

В `docx_document_reader.py`:

- таблицы обходятся по ячейкам и превращаются в последовательность обычного текста;
- добавляется warning `docx_table_layout_simplified`;
- OMML-формулы не разбираются;
- добавляется warning `omml_equation_not_supported`;
- стиль run, включая underline, сейчас теряется;
- DrawingML shapes/connectors почти не разбираются.

## 1.6. Что нельзя сломать

После обновления должны продолжать работать:

- TXT;
- DOCX без новых объектов;
- PDF с текстовым слоем;
- A4 и A5;
- `outline` и `centerline` для обычного текста;
- старые параметры CLI;
- `--images auto|outline|centerline|off`;
- пагинация;
- номера страниц;
- 90-секундная или конфигурируемая пауза между страницами;
- парковка пера;
- word joining;
- motion profiles;
- старые конфигурационные файлы с разумными default-значениями;
- `font-preview.svg`;
- `centerline-font-preview.svg`;
- `plotter-preview.svg`;
- `paths.json`;
- `output.gcode`;
- `job.json`;
- `report.json`;
- отсутствие команд нагрева;
- отсутствие extrusion;
- отсутствие `G28`, если он явно не включён;
- проверка границ workspace;
- атомарная запись итоговых файлов;
- детерминированность результата.

---

# 2. Общие архитектурные требования

## 2.1. Не смешивать чтение документа, layout и геометрию

Сохранить разделение на три уровня.

### Уровень A. Import / source model

Отвечает за чтение исходного DOCX/PDF и создание структурированной модели:

```text
DOCX/PDF
    -> SourceDocument
    -> SourcePage
    -> SourceElement
```

На этом уровне нужно сохранить:

- исходную страницу;
- исходный порядок;
- bbox;
- текстовые runs;
- тип объекта;
- размеры;
- wrapping/anchor;
- стили;
- provenance.

### Уровень B. Layout

Отвечает за размещение объектов на целевой A4/A5:

```text
SourceElement
    -> target placement
    -> line boxes / exclusion zones
    -> page splitting
```

На этом уровне не должно быть знания о G-code.

### Уровень C. Geometry / plotting

Отвечает за превращение размещённого объекта в `PlotterStroke`:

```text
placed text/formula/image/shape/table
    -> strokes
    -> path optimization
    -> G-code
```

## 2.2. Ввести единый внутренний объект размещения

Рекомендуется добавить модуль:

```text
src/plotter_processor/layout_models.py
```

Минимальные модели:

```python
@dataclass(frozen=True, slots=True)
class RectMM:
    x: float
    y: float
    width: float
    height: float

@dataclass(frozen=True, slots=True)
class SourcePlacement:
    source_page_index: int
    source_bbox: SourceBBox | None
    target_bbox: RectMM | None
    anchor: str
    wrap_mode: str
    z_order: int

@dataclass(slots=True)
class PlacedElement:
    element_id: str
    element_type: str
    page_index: int
    bbox: RectMM
    source_bbox: SourceBBox | None
    warnings: list[str]
```

Не обязательно использовать именно эти имена, но у всех размещённых элементов должен быть единый target bbox. Это нужно для:

- сохранения позиции;
- обтекания;
- таблиц;
- debug overlay;
- вычисления layout-метрик;
- проверки overlap;
- понятного `document-structure.json`.

## 2.3. Расширить provenance штрихов

Текущий `PlotterStroke` уже содержит `element_id`, `element_type`, `source_path`. Добавить при необходимости:

```python
source_page_index: int | None
semantic_role: str | None
layout_group: str | None
preserve_order: bool = False
z_order: int = 0
```

Примеры `semantic_role`:

- `text`;
- `latex-centerline`;
- `image-centerline`;
- `underline`;
- `arrow-shaft`;
- `arrow-head`;
- `table-border`;
- `table-cell-text`;
- `pdf-line`.

Это необходимо, чтобы path optimizer не перемешивал части объекта так, что:

- наконечник стрелки печатается отдельно от её линии;
- границы таблицы перемешиваются с текстом другой таблицы;
- underline уезжает далеко от соответствующего текста;
- элементы с разным z-order меняются местами.

## 2.4. Оптимизация пути должна учитывать группы

Текущий глобальный `optimize_paths` нельзя безусловно применять ко всем новым объектам. Требование:

1. Сначала разбить strokes на логические группы.
2. Сохранить порядок групп по `page`, `z_order`, `source_order`.
3. Оптимизировать strokes только внутри группы, если это разрешено.
4. Для стрелки сохранять последовательность shaft -> head либо использовать единый маршрут.
5. Для таблицы разрешить отдельную оптимизацию border strokes, но не смешивать с текстом соседнего элемента.

Добавить тест, который гарантирует, что включение `--no-optimize-travel` и обычного optimize не меняет геометрическое положение объектов.

## 2.5. Новые функции должны быть конфигурируемыми

Добавить в `configs/layout.yaml` новые секции с default-значениями. Старый config без новых секций должен продолжать работать через defaults внутри кода.

Не делать обязательную ручную миграцию config только ради этого обновления.

## 2.6. Безопасность

Запрещено:

- запускать внешний `latex`, `pdflatex`, `xelatex` или shell-команды;
- разрешать `\input`, `\include`, file access или shell escape;
- загружать внешние URL из SVG/PDF/DOCX;
- исполнять JavaScript;
- автоматически выполнять макросы Office;
- доверять размеру изображения или таблицы без лимитов;
- создавать NaN/Infinity;
- выводить координаты за workspace;
- растрировать всю PDF-страницу без ограничений по размеру;
- молча удалять неподдерживаемый объект;
- молча печатать один объект два раза.

## 2.7. Формат отчёта после каждого блока

После каждого блока Codex пишет пользователю:

```markdown
## Блок N завершён — <название>

### Базовый commit
- `...`

### Что сделано
- ...

### Какие файлы изменены
- `path/to/file.py` — ...

### Как проверить
```bash
<точные команды>
```

### Результат до/после
| Метрика | До | После |
|---|---:|---:|
| ... | ... | ... |

### Артефакты
- `build/update_7/block_N/...`

### Тесты
- `make test`: ...
- `make lint`: ...
- targeted tests: ...

### Что пока не решено
- ...

Блок N закончен. Следующий блок начинается только после публикации этого отчёта.
```

---

# 3. Подготовительный этап: baseline перед изменениями

Этот этап выполнить один раз до Блока 1.

## Шаг 3.1. Обновить рабочую ветку

```bash
git checkout master
git pull --ff-only
git rev-parse HEAD
git checkout -b upd/plotter-7-layout-math-lines-tables
```

В `build/update_7/baseline/environment.json` сохранить:

```json
{
  "base_commit": "<actual sha>",
  "python": "<version>",
  "platform": "<platform>",
  "dependencies": {
    "pymupdf": "<version>",
    "matplotlib": "<version>",
    "fonttools": "<version>",
    "python-docx": "<version>",
    "scikit-image": "<version>"
  }
}
```

## Шаг 3.2. Прогнать текущие тесты

```bash
make install
make test
make lint
.venv/bin/python -m plotter_processor --help
.venv/bin/python -m plotter_processor run --help
```

Если baseline уже падает, не скрывать проблему. Сохранить лог в:

```text
build/update_7/baseline/tests-before.txt
```

## Шаг 3.3. Создать тестовые fixtures

Создать:

```text
tests/fixtures/update_7/
  latex/
    latex_inline.txt
    latex_block.txt
    latex_complex.txt
    latex_multipage.txt
    latex_in_docx.docx
    omml_basic.docx
    pdf_formula_text.pdf
    pdf_formula_vector.pdf
  images/
    image_left_wrap.docx
    image_right_wrap.docx
    image_top_bottom.docx
    image_absolute.docx
    image_left_wrap.pdf
    image_right_wrap.pdf
    image_preserve_position.pdf
    image_overlap.pdf
  lines_tables/
    underline_runs.docx
    underline_pdf.pdf
    arrows.docx
    arrows.pdf
    simple_table.docx
    merged_cells.docx
    multipage_table.docx
    simple_table.pdf
    table_with_underlines.docx
    table_with_arrows.docx
```

Если бинарные fixtures генерируются кодом, добавить deterministic generator:

```text
tools/generate_update_7_fixtures.py
```

Генератор должен:

- создавать документы локально;
- не обращаться в сеть;
- использовать фиксированные размеры и координаты;
- быть детерминированным;
- документировать, что именно проверяет каждый fixture.

## Шаг 3.4. Создать baseline-runner

Добавить:

```text
tools/update_7_baseline.py
```

Runner должен:

1. Принимать `--font`.
2. Запускать текущий pipeline на всех fixtures.
3. Не останавливать весь прогон из-за одного ожидаемого unsupported-сценария.
4. Сохранять stdout/stderr.
5. Сохранять `report.json`, preview и G-code.
6. Создавать общий `baseline-summary.json`.
7. Не перезаписывать candidate-результаты.

Рекомендуемая структура:

```text
build/update_7/
  baseline/
    block_1/
    block_2/
    block_3/
    baseline-summary.json
  candidate/
    block_1/
    block_2/
    block_3/
```

## Шаг 3.5. Зафиксировать текущие недостатки

В baseline-summary явно записать:

- LaTeX strokes имеют `segment_types = latex-outline`;
- сколько strokes и pen lifts создаёт каждая формула;
- PDF LaTeX mode выключен;
- OMML вызывает warning;
- исходный bbox рисунка не используется при reflow;
- рисунки центрируются;
- текст не обтекает рисунки;
- DOCX underline теряется;
- DOCX table превращается в простой текст;
- arrowhead может быть rasterized;
- PDF-линии не классифицируются.

### Желаемый результат подготовительного этапа

Есть воспроизводимый baseline, по которому можно доказать улучшение каждого блока, а не сравнивать результат «на глаз по памяти».

---

# 4. БЛОК 1 — Качественный centerline-LaTeX и формулы из PDF

# 4.1. Цель блока

После завершения Блока 1:

- формулы из TXT и DOCX рисуются центральными линиями;
- inline- и block-формулы корректно участвуют в layout;
- формулы не становятся двойным контуром;
- формулы из PDF печатаются визуально близко к исходному PDF;
- формула сохраняет положение относительно окружающего текста;
- одна формула не печатается дважды;
- полный внешний LaTeX не запускается;
- unsupported-команды завершаются понятной ошибкой или управляемым fallback;
- в отчёте есть отдельные метрики centerline-формул.

Важно разделить два сценария:

1. **Semantic LaTeX** — исходная строка формулы известна, например `$x^2$` в TXT/DOCX.
2. **Visual PDF math** — исходная строка LaTeX неизвестна; нужно воспроизвести внешний вид области формулы.

Нельзя обещать «восстановление LaTeX из PDF». Задача блока — корректная печать формулы, а не reverse engineering исходного `.tex`.

---

## Шаг 4.2. Ввести общий интерфейс математического renderer

Текущий `MathTextRenderer` возвращает outline strokes. Расширить интерфейс так, чтобы renderer мог выдавать как outline, так и centerline.

Рекомендуемые модели:

```python
@dataclass(frozen=True, slots=True)
class MathRenderRequest:
    expression: str
    size_mm: float
    stroke_mode: str
    source_kind: str

@dataclass(frozen=True, slots=True)
class RenderedMath:
    expression: str
    strokes: tuple[PlotterStroke, ...]
    width_mm: float
    height_mm: float
    baseline_mm: float
    stroke_mode: str
    source_kind: str
    quality: dict[str, object]
    warnings: tuple[str, ...]
```

Допустимые `stroke_mode`:

- `centerline` — новый default;
- `outline` — совместимый fallback и debug-сравнение.

Не ломать старые вызовы сразу. Сначала добавить новое поле/default, затем обновить call sites.

### Желаемый результат

`latex_layout.py` не должен знать детали skeletonization. Он получает готовую геометрию через единый интерфейс.

---

## Шаг 4.3. Выделить переиспользуемый raster-to-centerline pipeline

Сейчас качественный centerline существует в `centerline_font`, но тесно связан с glyph/font units. Нельзя копировать весь алгоритм в `latex_renderer.py`.

Создать общий слой, например:

```text
src/plotter_processor/raster_centerline.py
```

или:

```text
src/plotter_processor/centerline_geometry/
  __init__.py
  raster_input.py
  graph.py
  routing.py
  smoothing.py
  quality.py
```

Он должен принимать:

```python
binary_mask: np.ndarray
pixel_to_mm: float | tuple[float, float]
config: RasterCenterlineConfig
```

И возвращать:

```python
CenterlineGeometry(
    strokes=...,
    components=...,
    graph_edges=...,
    junctions=...,
    pen_lifts=...,
    retraced_length_mm=...,
    warnings=...,
)
```

Переиспользовать существующие идеи:

- `skeletonize`;
- `medial_axis`;
- candidate selection;
- spur pruning;
- junction normalization;
- graph simplification;
- one route per connected component;
- bounded smoothing;
- complexity limits.

Не обязательно сразу полностью переносить `centerline_font`. Допустим адаптер над существующими модулями, но общий код не должен расходиться в двух независимых копиях.

### Обязательные свойства

- координаты результата сразу переводятся в mm;
- не создаются соединительные линии через пустое место;
- отдельные компоненты остаются отдельными strokes;
- короткие шумовые ветви удаляются;
- повтор рёбер измеряется;
- result детерминирован;
- есть лимиты размера mask, nodes, edges, points;
- есть debug-данные до/после pruning.

### Желаемый результат

Один и тот же качественный механизм можно использовать для:

- TTF centerline;
- LaTeX centerline;
- PDF formula centerline;
- в будущем — некоторых рисунков.

---

## Шаг 4.4. Рендерить MathText в high-resolution mask

В `latex_renderer.py` добавить новый centerline backend:

```text
MathText expression
    -> high-resolution transparent/white raster
    -> binary ink mask
    -> raster_centerline
    -> PlotterStroke
```

Не строить centerline из уже flatten outline-path, если это ухудшает качество. Лучше рендерить формулу непосредственно в mask с достаточным разрешением.

Рекомендуемые параметры:

```yaml
latex:
  enabled: true
  backend: mathtext
  stroke_mode: centerline
  render_ppmm: 24
  supersample: 2
  threshold: 160
  closing_radius_px: 1
  min_component_length_mm: 0.20
  curve_tolerance_mm: 0.04
  max_render_pixels: 16000000
  max_components: 5000
  max_points: 150000
  fallback_to_outline: false
```

`render_ppmm` должен обеспечивать достаточно точные индексы, корни, дроби и греческие символы. Значение подобрать тестами, а не оставить случайным.

### Особое внимание

Проверить:

- `x^2`;
- `x_i`;
- `\frac{a}{b}`;
- `\sqrt{x}`;
- `\sum_{i=1}^{n}`;
- `\int_0^1 f(x) dx`;
- матрицу, если MathText её поддерживает;
- скобки разных размеров;
- `\alpha`, `\beta`, `\pi`;
- `\leq`, `\geq`, `\neq`;
- длинную дробную черту;
- точки над символами;
- минус и горизонтальные линии.

Горизонтальные линии формулы нельзя удалять как шум: fraction bar и radical bar — смысловые элементы.

### Желаемый результат

Формула состоит из одноштриховых центральных линий вместо обводки каждой стороны символа.

---

## Шаг 4.5. Добавить quality gate для формул

Для каждой формулы считать:

- `mask_foreground_pixels`;
- `components_before_pruning`;
- `components_after_pruning`;
- `graph_nodes`;
- `graph_edges`;
- `junction_count`;
- `strokes`;
- `points`;
- `draw_length_mm`;
- `retraced_length_mm`;
- `retrace_ratio`;
- `small_components_removed`;
- `centerline_coverage_ratio`;
- `needs_review`.

Quality gate не должен автоматически объявлять формулу хорошей только потому, что код не упал.

Примеры warning:

- `latex_centerline_many_components`;
- `latex_centerline_high_retrace`;
- `latex_centerline_low_coverage`;
- `latex_centerline_tiny_symbols_removed`;
- `latex_centerline_complexity_limited`.

При `strict`-режиме плохая формула должна останавливать job до генерации G-code.

Добавить CLI:

```text
--latex-stroke-mode centerline|outline
--strict-latex-quality
```

При этом старый `--latex mathtext` оставить рабочим.

---

## Шаг 4.6. Сохранить корректный baseline и line box

`RenderedMath.baseline_mm` должен соответствовать реальному baseline формулы после centerline conversion.

Проверить:

- inline-формула не прыгает вверх или вниз;
- нижние индексы не налезают на следующую строку;
- верхние индексы не пересекаются с предыдущей строкой;
- block formula центрируется;
- block formula учитывает spacing before/after;
- формула переносится целиком, если не помещается в строку;
- слишком широкая формула масштабируется только до `min_scale`;
- после масштабирования толщина/качество centerline не меняются из-за повторной растеризации слишком низкого качества.

Лучше сначала выбрать финальный physical size, затем рендерить mask нужного размера, а не рендерить маленькую формулу и сильно растягивать strokes.

---

## Шаг 4.7. Поддержать OMML из DOCX хотя бы для основного подмножества

Сейчас OMML только вызывает warning. Добавить отдельный parser:

```text
src/plotter_processor/omml_parser.py
```

Не пытаться сразу поддержать весь стандарт. Создать внутреннее AST либо конвертацию в безопасный MathText-compatible expression для подмножества:

- plain symbols;
- superscript;
- subscript;
- fraction;
- radical;
- parentheses;
- n-ary sum/integral;
- basic matrix;
- Greek symbols;
- relations;
- operators.

Для неподдерживаемого OMML:

- не терять объект молча;
- сохранять element id;
- выдавать понятный warning/error с названием unsupported node;
- при включённом visual fallback можно rasterize только bbox формулы из DOCX preview, если есть надёжный способ без запуска Office; иначе fallback запрещён.

В `docx_document_reader.py` формула должна становиться:

```python
SourceMathElement(
    id=...,
    expression=...,
    display_mode=...,
    source_syntax="omml",
    bbox=...,
)
```

Не прятать OMML в обычную строку текста.

### Желаемый результат

Базовые формулы Word проходят через тот же centerline renderer, что и `$...$`.

---

## Шаг 4.8. Не смешивать `SourceMathElement` и LaTeX-delimiters

Обновить `document_paginator.py`:

- `SourceTextElement` с `$...$` продолжает разбираться через `latex_parser`;
- `SourceMathElement` рендерится напрямую;
- оба сценария возвращают одинаковые `FormulaInfo` и strokes;
- source syntax сохраняется как `dollar-inline`, `bracket-block`, `omml`, `pdf-visual`;
- formula id детерминирован.

Добавить обработку `SourceMathElement` в:

- statistics;
- `document-structure.json`;
- page source ids;
- report;
- preview metadata.

---

## Шаг 4.9. Реализовать формулы из PDF как visual math regions

Главный принцип:

> Из PDF не нужно выдумывать исходную LaTeX-строку. Нужно выделить визуальную область формулы, один раз получить её ink mask и построить centerline.

Создать модуль, например:

```text
src/plotter_processor/pdf_math_detector.py
src/plotter_processor/pdf_region_renderer.py
```

### 4.9.1. Сбор признаков

В `pdf_document_reader.py` извлекать не только готовые строки, но и span-level metadata из `page.get_text("dict")` или `rawdict`:

- bbox span;
- font name;
- font size;
- flags;
- baseline/origin;
- text;
- source order;
- соседние spans;
- superscript/subscript position;
- math symbols;
- density vector drawings рядом.

### 4.9.2. Консервативное обнаружение formula region

Регион считать кандидатом, если присутствует несколько признаков:

- символы `= + − × ÷ ∑ ∫ √ ≤ ≥ ≠ ∞ α β γ π`;
- заметные baseline shifts;
- маленькие spans сверху/снизу;
- font name содержит `Math`, `Symbol`, `STIX`, `CambriaMath`, `CMSY`, `CMEX`;
- рядом есть fraction/radical lines;
- несколько spans формируют компактный математический блок;
- строка имеет высокую долю операторов и низкую долю обычных слов.

Не считать любой одиночный знак `+` формулой.

### 4.9.3. Группировка

Объединять spans и vector primitives в один formula bbox, если они:

- находятся на одной математической строке;
- пересекаются или близки;
- имеют логичную вертикальную структуру;
- относятся к одному source order range.

### 4.9.4. Рендер региона

Использовать PyMuPDF clip rendering:

```python
page.get_pixmap(matrix=..., clip=formula_rect, alpha=False)
```

Требования:

- high DPI/ppmm;
- белый background;
- crop padding 0.5–1.5 mm;
- ограничение `max_render_pixels`;
- threshold/denoise;
- centerline через общий raster pipeline;
- scale обратно в PDF coordinates;
- затем map в target page coordinates.

### 4.9.5. Исключение дублей

После создания `SourceMathElement(source_syntax="pdf-visual")` удалить или пометить поглощённые:

- text spans;
- vector lines;
- raster fragments.

Они не должны отдельно попасть в обычный text/vector pipeline.

Сохранить:

```json
{
  "formula_id": "...",
  "absorbed_text_span_ids": ["..."],
  "absorbed_vector_ids": ["..."],
  "bbox": {...}
}
```

### 4.9.6. Fallback

Если detector не уверен:

- не удалять исходные spans;
- оставить их обычным текстом/vector;
- добавить warning `pdf_math_candidate_low_confidence`;
- не растрировать всю страницу.

Добавить режим:

```text
--pdf-math auto|visual|off
```

- `auto` — только high-confidence regions;
- `visual` — более агрессивное распознавание;
- `off` — старое поведение.

### Желаемый результат

PDF с формулой печатается, даже если исходная LaTeX-строка отсутствует. В отчёте честно написано, что это visual centerline reconstruction, а не восстановление `.tex`.

---

## Шаг 4.10. Добавить debug-артефакты LaTeX/PDF math

При `--latex-debug` или новом `--math-debug` сохранять:

```text
build/.../latex-debug/
  formula-001-source.json
  formula-001-mask.png
  formula-001-skeleton.png
  formula-001-graph.svg
  formula-001-centerline.svg
  formula-001-overlay.svg
```

Для PDF дополнительно:

```text
formula-001-pdf-clip.png
formula-001-absorbed-elements.json
```

`overlay.svg` должен показывать:

- исходный outline/mask серым;
- centerline красной/контрастной линией;
- bbox;
- baseline;
- component ids.

Цвет используется только в debug preview, не влияет на G-code.

---

## Шаг 4.11. Расширить конфигурацию

Рекомендуемая секция:

```yaml
latex:
  enabled: true
  backend: mathtext
  stroke_mode: centerline
  inline_size_scale: 1.0
  block_size_scale: 1.15
  min_scale: 0.65
  render_ppmm: 24
  supersample: 2
  threshold: 160
  closing_radius_px: 1
  min_component_length_mm: 0.20
  max_render_pixels: 16000000
  max_components: 5000
  max_points: 150000
  fallback_to_outline: false
  strict_quality: false
  pdf_math:
    mode: auto
    render_ppmm: 24
    bbox_padding_mm: 0.8
    confidence_threshold: 0.75
    max_region_area_ratio: 0.35
```

В коде должны быть defaults, чтобы старый `layout.yaml` продолжал читаться.

---

## Шаг 4.12. Обновить CLI и report

Добавить параметры:

```text
--latex-stroke-mode centerline|outline
--strict-latex-quality
--pdf-math auto|visual|off
--math-debug
```

Сохранить совместимость:

```text
--latex auto|mathtext|off
--latex-debug
```

В `report.json`:

```json
{
  "latex": {
    "enabled": true,
    "backend": "mathtext",
    "stroke_mode": "centerline",
    "expressions_found": 4,
    "semantic_expressions": 2,
    "omml_expressions": 1,
    "pdf_visual_expressions": 1,
    "rendered": 4,
    "outline_fallbacks": 0,
    "strokes": 37,
    "points": 1240,
    "pen_lifts": 37,
    "needs_review": 0,
    "warnings": []
  }
}
```

Для каждой formula info сохранить source element id, page, bbox, source syntax и quality summary.

---

## Шаг 4.13. Тесты Блока 1

Добавить минимум:

```text
tests/test_raster_centerline.py
tests/test_latex_centerline_renderer.py
tests/test_latex_centerline_quality.py
tests/test_omml_parser.py
tests/test_pdf_math_detector.py
tests/test_pdf_math_pipeline.py
tests/test_latex_centerline_integration.py
```

### Unit tests

Проверить:

- deterministic mask-to-centerline;
- удаление шумовых ветвей;
- сохранение fraction bar;
- сохранение dot accents;
- route per component;
- complexity limits;
- parser delimiters;
- OMML subset;
- PDF detector confidence;
- bbox grouping;
- duplicate suppression;
- baseline calculation;
- scale calculation;
- config defaults.

### Integration tests

Проверить:

- TXT inline formula;
- TXT block formula;
- несколько формул в одной строке;
- formula переносится на следующую строку;
- formula переносится на следующую страницу;
- DOCX с `$...$`;
- DOCX OMML;
- PDF text formula;
- PDF visual/vector formula;
- centerline text + centerline formula в одном G-code;
- `--latex-stroke-mode outline` сохраняет старое поведение;
- `--pdf-math off` не включает detector;
- ошибка formula не оставляет stale G-code.

### Visual regression

Сохранить snapshots для:

- `x^2 + y^2 = z^2`;
- `\frac{a+b}{c-d}`;
- `\sqrt{x^2 + 1}`;
- `\sum_{i=1}^{n} i`;
- `\int_0^1 f(x)\,dx`;
- PDF formula fixture.

Не сравнивать PNG pixel-perfect между разными версиями библиотек, если это нестабильно. Сравнивать:

- normalized stroke geometry;
- bbox;
- counts;
- topology metrics;
- SVG snapshot после округления координат.

---

## Шаг 4.14. Метрики успеха Блока 1

Минимальные критерии:

- `latex-outline` не используется при default centerline mode;
- число двойных параллельных контуров визуально и метрически уменьшено;
- centerline formula проходит bbox/coverage threshold;
- PDF formula не дублируется;
- basic OMML поддерживается;
- baseline formula examples создают G-code;
- все координаты в пределах страницы;
- G-code безопасен;
- runtime и memory не превышают лимиты;
- обычный текст без формул не становится заметно медленнее.

### Рекомендуемые метрики до/после

| Метрика | Baseline | Candidate |
|---|---:|---:|
| Formula strokes | ... | ... |
| Formula pen lifts | ... | ... |
| Draw length, mm | ... | ... |
| Duplicate-outline ratio | ... | ... |
| PDF formulas rendered | 0 | ... |
| OMML formulas rendered | 0 | ... |
| Formula needs_review | ... | ... |
| Render time, ms | ... | ... |

---

## Шаг 4.15. Отчёт пользователю после Блока 1

Показать:

- одну inline формулу;
- одну block формулу;
- одну OMML формулу;
- одну формулу из PDF;
- preview до/после;
- число strokes и pen lifts;
- debug overlay;
- точные ограничения MathText и PDF visual reconstruction.

После отчёта написать:

```text
Блок 1 закончен. Перехожу к Блоку 2 только после публикации этого отчёта.
```

---

# 5. БЛОК 2 — Сохранение положения рисунков и обтекание текстом

# 5.1. Цель блока

После завершения Блока 2:

- рисунок располагается примерно там же, где в исходном документе;
- левый рисунок остаётся слева, правый — справа;
- размер и aspect ratio сохраняются;
- рисунок не центрируется без причины;
- текст может обтекать рисунок слева/справа;
- top-bottom wrapping поддерживается;
- inline image остаётся частью потока;
- anchored image использует anchor/wrap metadata;
- PDF layout учитывает исходные bbox;
- при невозможности точного размещения используется предсказуемый fallback с warning;
- результат остаётся в границах A4/A5.

---

## Шаг 5.2. Нормализовать source coordinates

Сейчас PDF bbox хранится в points, а часть DOCX координат — в mm. Это опасно.

Добавить явную систему координат в модели либо нормализовать все bbox к source-page mm сразу при импорте.

Рекомендуемый вариант:

```python
@dataclass(frozen=True, slots=True)
class SourceBBox:
    x0_mm: float
    y0_mm: float
    x1_mm: float
    y1_mm: float
```

Если изменение имён слишком большое, добавить `coordinate_unit` и helper conversion. Но внутри layout не должно быть догадок, points это или mm.

Для PDF:

```text
pt -> mm using 25.4 / 72
```

Для DOCX:

```text
EMU -> mm using 36000 EMU/mm
```

В `SourcePage` хранить width/height в mm либо добавить свойства `width_mm`, `height_mm`.

### Желаемый результат

Один mapping function работает одинаково для DOCX и PDF.

---

## Шаг 5.3. Расширить модель изображения

Добавить в `SourceRasterImageElement` и при необходимости `SourceVectorElement`:

```python
anchor_type: str = "flow"
wrap_mode: str = "inline"
wrap_side: str = "both"
distance_left_mm: float = 0.0
distance_right_mm: float = 0.0
distance_top_mm: float = 0.0
distance_bottom_mm: float = 0.0
relative_to_h: str | None = None
relative_to_v: str | None = None
behind_text: bool = False
z_order: int = 0
rotation_deg: float = 0.0
```

Минимальные wrap modes:

- `inline`;
- `square`;
- `top_bottom`;
- `none`/absolute;
- `behind_text` — можно импортировать, но для MVP безопаснее предупреждать и преобразовывать в `square` или `top_bottom`;
- `in_front` — аналогично, не допускать неявного пересечения с текстом.

---

## Шаг 5.4. Читать wrapping и anchor из DOCX

В `docx_document_reader.py` различать:

- `wp:inline`;
- `wp:anchor`;
- `wp:positionH`;
- `wp:positionV`;
- `wp:extent`;
- `wp:wrapSquare`;
- `wp:wrapTight`;
- `wp:wrapThrough`;
- `wp:wrapTopAndBottom`;
- `wp:wrapNone`;
- `wp:docPr`;
- distance attributes;
- `behindDoc`;
- `relativeHeight`.

Для `wrapTight` в MVP допустимо использовать rectangular bbox и warning:

```text
docx_wrap_tight_approximated_as_square
```

Не оставлять старый warning `floating_image_reflowed`, если позиция теперь действительно учитывается. Заменить на более точные warnings только при fallback.

### Желаемый результат

DOCX reader создаёт source model, достаточную для реального wrapping.

---

## Шаг 5.5. Сохранить PDF bbox и source order без принудительной сортировки только по y/x

Текущая сортировка по bbox y/x полезна для reflow, но может ломать исходный order при сложном layout.

Хранить отдельно:

- raw source order;
- visual order;
- reading order;
- bbox.

Не перезаписывать исходный id/order окончательно. Layout mode сам выбирает нужный порядок.

Для PDF добавить grouping:

- text block;
- image block;
- vector block;
- math region;
- overlapping frame.

### Желаемый результат

Режим preserve опирается на координаты, а reflow — на reading order.

---

## Шаг 5.6. Реализовать три режима layout

Рекомендуется расширить текущий `--pdf-layout` до общего document layout, сохранив alias.

Новый CLI:

```text
--document-layout reflow|hybrid|preserve
```

Совместимость:

- `--pdf-layout reflow` -> `--document-layout reflow`;
- `--pdf-layout preserve` -> `--document-layout preserve`;
- если указан только старый флаг, он работает;
- если указаны оба с разными значениями — понятная ошибка.

### `reflow`

- последовательный поток;
- inline images;
- anchored images могут быть преобразованы в top-bottom;
- минимум риска overlap;
- удобно для смены формата страницы.

### `preserve`

- source page mapping целиком;
- bbox всех элементов масштабируется и переносится на target page;
- сохраняется относительное положение;
- текст не переформатируется без крайней необходимости;
- подходит для PDF и фиксированного layout.

### `hybrid`

- рекомендуемый default для DOCX/PDF с рисунками;
- рисунки сохраняют side/approximate y;
- текст reflow вокруг exclusion zones;
- координаты могут немного сдвигаться для предотвращения overlap и выхода за страницу;
- сохраняется source order и page breaks.

Не менять default без тестов. Можно оставить `reflow` default в этом обновлении и рекомендовать `hybrid` явно, либо сделать `hybrid` default только для документов с anchored images. Решение отразить в README.

---

## Шаг 5.7. Реализовать source-to-target mapping для preserve

Создать helper:

```python
map_source_rect(
    source_rect,
    source_page_size,
    target_content_rect,
    fit="contain",
    preserve_aspect=True,
)
```

Правила:

1. Использовать единый scale для X/Y.
2. Не растягивать страницу неравномерно.
3. Центрировать mapped source page внутри target content rect.
4. Сохранять aspect ratio рисунка.
5. Не увеличивать небольшой рисунок сверх configurable factor.
6. Если target page другого aspect ratio, оставлять поля.
7. Проверять bounds.

Config:

```yaml
document_layout:
  mode: reflow
  preserve:
    fit: contain
    max_upscale: 1.10
    clip_to_page: false
```

Если объект частично выходит за source page, не обрезать молча. Добавить warning.

---

## Шаг 5.8. Реализовать exclusion zones для обтекания

Создать модель:

```python
@dataclass(frozen=True, slots=True)
class ExclusionZone:
    bbox: RectMM
    wrap_side: str
    element_id: str
```

Для каждой text line layout должен получать доступные горизонтальные intervals на её вертикальном диапазоне.

Пример:

```text
usable line: [left, right]
image zone:  [20, 70]
available:   [70 + padding, right]
```

Если картинка справа:

```text
available: [left, image.x - padding]
```

Если картинка посередине и разрешены обе стороны:

```text
available: [left, image.x-padding] + [image.right+padding, right]
```

Для MVP допустимо выбрать только более широкий interval для каждой строки, чтобы слова не прыгали между двумя колонками. Решение должно быть детерминированным.

### Изменение text layout

Не усложнять существующий `layout_text` бесконечными условиями. Лучше добавить:

```text
src/plotter_processor/flow_layout.py
```

или adapter:

```python
layout_text_in_regions(
    paragraphs,
    line_regions_provider,
    ...
)
```

`line_regions_provider(y_top, y_bottom)` возвращает доступные intervals.

### Желаемый результат

Текст реально обтекает bbox изображения, а не просто печатается до/после него.

---

## Шаг 5.9. Размещать изображение близко к source bbox

Для hybrid mode использовать scoring кандидатов.

Кандидаты:

- исходная mapped position;
- сдвиг вниз до ближайшего свободного места;
- привязка к левому краю;
- привязка к правому краю;
- top-bottom fallback.

Score:

```text
score =
    source_displacement_weight * normalized_center_distance
  + overlap_weight * overlap_area
  + page_overflow_weight * overflow_area
  + reading_order_weight * order_violation
  + resize_weight * abs(log(output_scale/source_scale))
```

Выбирать минимальный score.

Не использовать случайность.

Config:

```yaml
document_layout:
  hybrid:
    image_padding_mm: 2.0
    max_vertical_shift_mm: 25.0
    max_horizontal_shift_mm: 20.0
    allow_side_switch: false
    fallback: top_bottom
```

Если левый рисунок не помещается слева, сначала уменьшить до допустимого min scale, затем сдвинуть вниз, и только потом менять wrap mode.

---

## Шаг 5.10. Не менять размер рисунка без необходимости

Текущий `_image_size` ограничивает размер, но не учитывает исходную страницу и placement.

Новые правила:

1. Использовать displayed size из DOCX/PDF, если он известен.
2. Сохранять aspect ratio.
3. Не увеличивать изображение по умолчанию.
4. Уменьшать только при выходе за target bounds.
5. Записывать scale factor в report.
6. При значительном уменьшении выдавать warning.

Warnings:

- `image_scaled_down_to_fit`;
- `image_position_shifted`;
- `image_wrap_fallback_top_bottom`;
- `image_overlap_avoided`;
- `image_source_position_unavailable`.

---

## Шаг 5.11. Поддержать несколько изображений и конфликтующие зоны

Проверить случаи:

- две картинки слева одна под другой;
- картинки слева и справа;
- пересекающиеся anchors;
- картинка рядом с формулой;
- картинка рядом с таблицей;
- картинка на границе страницы;
- anchored image переезжает на следующую страницу;
- текст продолжается после изображения;
- маленький остаток строки не используется, если туда не помещается слово.

Layout solver должен завершаться за ограниченное время. Не использовать бесконечный iterative relaxation.

Добавить лимит количества placement attempts на элемент.

---

## Шаг 5.12. Векторные PDF-рисунки размещать по тем же правилам

`SourceVectorElement` не должен всегда центрироваться. Для него использовать тот же placement/wrap pipeline, что и для raster image.

Отличия:

- source vector geometry уже в mm;
- масштабировать strokes относительно bbox;
- сохранять line topology;
- не растрировать без необходимости;
- provenance `pdf-vector` сохраняется.

---

## Шаг 5.13. Добавить source/output overlay preview

Создать:

```text
build/.../layout-debug/
  source-layout.svg
  target-layout.svg
  placement-overlay.svg
  placement.json
```

`placement-overlay.svg` должен показывать:

- source mapped bbox пунктиром;
- output bbox сплошной линией;
- displacement vector;
- exclusion zone;
- text line boxes;
- page bounds;
- element id.

В `placement.json`:

```json
{
  "elements": [
    {
      "id": "...",
      "source_bbox_mm": {...},
      "mapped_bbox_mm": {...},
      "output_bbox_mm": {...},
      "wrap_mode": "square",
      "scale": 0.92,
      "center_displacement_mm": 3.4,
      "overlap_area_mm2": 0.0,
      "fallbacks": []
    }
  ]
}
```

---

## Шаг 5.14. Обновить `document-structure.json`

Для каждого элемента сохранить:

- source page;
- source bbox;
- source size;
- target page;
- target bbox;
- wrap mode;
- anchor;
- scale;
- shift;
- warnings;
- source order;
- output order.

Не ограничиваться только `layout_mode` и asset path.

---

## Шаг 5.15. Обновить report

Добавить:

```json
{
  "document_layout": {
    "mode": "hybrid",
    "images": 3,
    "images_with_source_bbox": 3,
    "images_wrapped": 2,
    "images_top_bottom": 1,
    "position_preserved": 2,
    "position_fallbacks": 1,
    "mean_center_displacement_mm": 4.2,
    "max_center_displacement_mm": 9.1,
    "mean_scale_factor": 0.94,
    "overlaps_remaining": 0
  }
}
```

Отдельно для каждого image/vector element.

---

## Шаг 5.16. Тесты Блока 2

Добавить:

```text
tests/test_layout_mapping.py
tests/test_exclusion_zones.py
tests/test_flow_layout.py
tests/test_docx_image_anchors.py
tests/test_pdf_preserve_layout.py
tests/test_hybrid_image_layout.py
tests/test_layout_debug_export.py
```

### Unit tests

- point/mm conversion;
- EMU/mm conversion;
- preserve mapping;
- aspect ratio;
- max upscale;
- exclusion intervals;
- left wrap;
- right wrap;
- top-bottom wrap;
- candidate scoring;
- no overlap;
- deterministic placement;
- bounds validation.

### Integration tests

- DOCX image left + wrapped text;
- DOCX image right + wrapped text;
- DOCX inline image;
- DOCX top-bottom;
- PDF image at top-right;
- PDF image in middle-left;
- PDF vector figure;
- two images;
- image across page break;
- image plus LaTeX;
- A4 source -> A5 target;
- A5 source -> A4 target;
- `reflow`, `hybrid`, `preserve` comparison.

### Regression tests

Старый plain TXT должен выдавать идентичную геометрию, кроме явно документированных metadata fields.

---

## Шаг 5.17. Метрики успеха Блока 2

Минимальные критерии:

- left/right placement сохраняется в тестовых документах;
- mean center displacement в hybrid mode ниже заданного threshold;
- нет overlaps text/image;
- aspect ratio error < 0.5%;
- нет выхода за page bounds;
- top-bottom fallback виден в report;
- reflow старых документов не ломается;
- preserve mode реально меняет размещение, а не только metadata;
- G-code содержит strokes изображения один раз.

Рекомендуемые threshold для fixtures:

```text
preserve mode center displacement <= 1.0 mm after page mapping
hybrid mode center displacement <= 10.0 mm for normal cases
aspect ratio relative error <= 0.005
remaining overlap area == 0
page overflow area == 0
```

---

## Шаг 5.18. Отчёт пользователю после Блока 2

Показать минимум три примера:

1. рисунок слева с текстом справа;
2. рисунок справа с текстом слева;
3. PDF preserve/hybrid до и после.

В отчёте показать:

- source preview;
- output preview;
- overlay bbox;
- displacement;
- scale;
- wrap mode;
- fallback warnings.

После отчёта написать:

```text
Блок 2 закончен. Перехожу к Блоку 3 только после публикации этого отчёта.
```

---

# 6. БЛОК 3 — Линии, подчёркивание, стрелки и таблицы

# 6.1. Цель блока

После завершения Блока 3 проект должен:

- сохранять подчёркнутый текст из DOCX;
- печатать underline в PDF;
- печатать обычные линии;
- печатать стрелки из схем;
- сохранять направление стрелки;
- печатать простые DOCX-таблицы;
- поддерживать merged cells;
- печатать границы таблицы одной линией, без двойных общих borders;
- размещать текст внутри ячеек;
- переносить длинную таблицу на несколько страниц;
- консервативно распознавать PDF-таблицы;
- не путать fraction bar, underline, table border и arrow shaft.

---

## Шаг 6.2. Расширить source text model до styled runs

Текущий `SourceTextElement.paragraphs: tuple[str, ...]` недостаточен.

Добавить backward-compatible модели:

```python
@dataclass(frozen=True, slots=True)
class SourceTextStyle:
    underline: str | None = None
    strike: bool = False
    bold: bool = False
    italic: bool = False
    font_size_pt: float | None = None
    baseline_shift: str | None = None

@dataclass(frozen=True, slots=True)
class SourceTextRun:
    text: str
    style: SourceTextStyle
    bbox: SourceBBox | None = None

@dataclass(frozen=True, slots=True)
class SourceParagraph:
    runs: tuple[SourceTextRun, ...]
    alignment: str | None = None
    bbox: SourceBBox | None = None
```

`SourceTextElement` может временно содержать и старое `paragraphs`, и новые `styled_paragraphs`, либо перейти на новую модель с helper property `.paragraphs_text`.

Главное: не переписывать весь pipeline за один commit без тестов. Сделать миграцию поэтапно.

### Желаемый результат

Стиль underline не теряется на этапе чтения DOCX/PDF.

---

## Шаг 6.3. Читать underline из DOCX

В `docx_document_reader.py` читать:

- `w:u`;
- `w:val`;
- style inheritance, если возможно;
- paragraph/run direct formatting;
- `none`/`false`;
- single;
- double;
- words-only;
- dotted/dashed — можно поддержать позже либо приблизить с warning.

MVP обязательно:

- single underline;
- double underline;
- words-only underline.

Для unsupported style:

```text
docx_underline_style_approximated:<style>
```

Не рисовать underline для пустого run.

---

## Шаг 6.4. Создавать underline после окончательного text layout

Underline нельзя строить до переноса строк. Его геометрия зависит от фактических glyph positions.

После layout:

1. Сгруппировать glyphs по source run и line index.
2. Найти start/end X по фактическим glyph bbox/advance.
3. Вычислить underline Y относительно baseline.
4. Создать `PlotterStroke`.
5. Разбить underline на несколько линий, если run перенесён.
6. Для words-only не проводить линию через пробелы.
7. Для double underline создать две параллельные линии с configurable gap.

Config:

```yaml
text_decorations:
  underline:
    offset_em: 0.12
    double_gap_mm: 0.45
    min_length_mm: 0.5
    join_adjacent_runs_gap_mm: 0.3
```

Если TTF содержит underline metrics, использовать их. Иначе fallback из em-size.

Штрих:

```python
semantic_role = "underline"
element_type = "text-decoration"
preserve_order = True
```

### Желаемый результат

Подчёркивание находится непосредственно под соответствующим текстом и корректно переносится по строкам.

---

## Шаг 6.5. Распознавать underline в PDF

В PDF underline может быть отдельным drawing line.

Добавить classifier:

```text
src/plotter_processor/pdf_line_classifier.py
```

Для горизонтальной линии определить кандидата underline, если:

- линия находится близко под text span;
- X-range совпадает с text span;
- длина похожа на ширину текста;
- vertical distance соответствует font size;
- линия не является частью grid;
- линия не является fraction bar внутри math region;
- линия не является arrow shaft.

Если confidence высокий:

- связать line с text element;
- semantic role `underline`;
- не дублировать как generic line.

Если confidence низкий:

- оставить generic line;
- добавить classification metadata;
- не удалять.

### Приоритет классификации

Рекомендуемый порядок:

1. math-region absorption;
2. table-grid detection;
3. arrow detection;
4. underline association;
5. generic line.

Иначе fraction bar может ошибочно стать underline, а table border — стрелкой.

---

## Шаг 6.6. Добавить модели линий и shapes

В `document_models.py` добавить, например:

```python
@dataclass(frozen=True, slots=True)
class SourceLineElement:
    id: str
    source_order: int
    source_page_index: int
    start: SourcePoint
    end: SourcePoint
    line_width_mm: float | None
    dash_style: str | None
    bbox: SourceBBox | None
    semantic_role: str = "line"

@dataclass(frozen=True, slots=True)
class SourceArrowElement:
    id: str
    source_order: int
    source_page_index: int
    points: tuple[SourcePoint, ...]
    head_at_start: bool
    head_at_end: bool
    head_style: str
    bbox: SourceBBox | None
```

Можно использовать generic `SourceShapeElement`, но не складывать все shape semantics в непроверяемый dict.

---

## Шаг 6.7. Улучшить импорт PDF drawing primitives

Текущий код растрирует drawing, если есть fill. Для простых геометрических объектов это слишком грубо.

До raster fallback отдельно распознавать:

- filled triangle;
- simple polygon;
- open polyline;
- line with arrow-like triangle at endpoint;
- rectangle without complex fill;
- orthogonal grid.

Для filled triangle:

- сохранить polygon outline;
- для arrowhead по возможности преобразовать в две стороны `V`, чтобы плоттер не обводил толстый залитый треугольник двойным контуром;
- не растрировать весь drawing.

Сложный fill/gradient по-прежнему можно rasterize с warning.

---

## Шаг 6.8. Распознавать стрелки в PDF

Создать detector:

```text
src/plotter_processor/arrow_detector.py
```

Алгоритм:

1. Найти line/polyline shaft candidates.
2. Найти triangle/V-shape candidates.
3. Сопоставить arrowhead с endpoint shaft по distance и angle.
4. Проверить, что head ориентирован наружу от shaft.
5. Сгруппировать в один `SourceArrowElement`.
6. Удалить поглощённые primitive elements из generic списка.
7. Сохранить confidence.

Параметры:

```yaml
shapes:
  arrows:
    endpoint_tolerance_mm: 1.2
    angle_tolerance_deg: 25
    min_shaft_length_mm: 2.0
    head_min_size_mm: 0.8
    head_max_size_mm: 8.0
```

Не объединять близкие несвязанные линии.

---

## Шаг 6.9. Читать стрелки и connectors из DOCX

Поддержать основной DrawingML/VML subset:

- straight line;
- connector;
- `a:ln`;
- `a:headEnd`;
- `a:tailEnd`;
- line geometry;
- position/extent/transform;
- rotation;
- flip H/V.

Минимальные arrow styles:

- none;
- triangle;
- stealth;
- open;
- oval — можно приблизить или warning.

Преобразовать к centerline geometry:

- shaft — одна линия/polyline;
- open head — две линии;
- filled triangle — две стороны V либо три стороны, configurable;
- направление обязательно сохранить.

Config:

```yaml
shapes:
  arrows:
    filled_head_mode: open_v
    preserve_closed_head: false
```

### Желаемый результат

Стрелка печатается как естественная линия с наконечником, а не как растровая картинка или двойная обводка.

---

## Шаг 6.10. Добавить generic line plotting

Обычная линия должна:

- сохранять start/end;
- масштабироваться вместе со страницей в preserve mode;
- участвовать в hybrid placement;
- иметь минимум две точки;
- не дублироваться;
- не удаляться path simplifier;
- иметь semantic role;
- попадать в report.

Dash styles:

- solid — обязательно;
- dashed/dotted — можно приблизить отдельными segments;
- если unsupported, warning и solid fallback только при явном config.

Не превращать короткий dash в шум при simplification.

---

## Шаг 6.11. Добавить модель таблицы

В `document_models.py`:

```python
@dataclass(frozen=True, slots=True)
class SourceTableCell:
    row: int
    column: int
    row_span: int
    column_span: int
    paragraphs: tuple[SourceParagraph, ...]
    width_mm: float | None
    height_mm: float | None
    borders: CellBorders
    vertical_alignment: str | None

@dataclass(frozen=True, slots=True)
class SourceTableElement:
    id: str
    source_order: int
    source_page_index: int
    rows: int
    columns: int
    cells: tuple[SourceTableCell, ...]
    column_widths_mm: tuple[float, ...]
    bbox: SourceBBox | None
    repeat_header_rows: int = 0
```

Не хранить таблицу как строку с табами. Нужна структурированная модель.

---

## Шаг 6.12. Читать DOCX-таблицы

Поддержать:

- `w:tbl`;
- `w:tblGrid`;
- `w:gridCol`;
- `w:tr`;
- `w:tc`;
- `w:tcW`;
- `w:gridSpan`;
- `w:vMerge`;
- cell margins;
- table alignment;
- borders;
- header row marker;
- текстовые runs внутри ячейки;
- изображения/formulas в ячейке — хотя бы через контролируемый unsupported/fallback на первом этапе.

Обновить `docx_document_reader.py`, чтобы warning `docx_table_layout_simplified` исчезал для поддержанных таблиц.

Для сложных features:

- nested table;
- diagonal border;
- floating table;
- text direction;
- cell shading;
- exact row height;

добавлять конкретные warnings, а не один общий.

---

## Шаг 6.13. Реализовать table layout

Создать:

```text
src/plotter_processor/table_layout.py
```

Pipeline:

```text
SourceTableElement
    -> resolve column widths
    -> layout text in each cell
    -> compute row heights
    -> resolve merged cells
    -> paginate by rows
    -> create border strokes
    -> create cell text glyphs/strokes
```

### Column widths

1. Использовать source widths, если известны.
2. Масштабировать таблицу целиком, если она шире usable width.
3. Не сжимать ниже configurable minimum text scale без ошибки.
4. При неизвестных widths распределять по content weight.
5. Сохранять merged spans.

### Row heights

- minimum из source;
- увеличить под wrapped text;
- учитывать padding;
- учитывать formula/image, если поддержано;
- не обрезать текст.

### Cell text

- wrapping внутри cell width;
- horizontal alignment left/center/right;
- vertical alignment top/center/bottom;
- styled runs и underline;
- centerline font mode;
- word joining не должен соединять текст разных ячеек.

### Borders

- shared border рисовать один раз;
- объединять collinear segments;
- не создавать двойные линии между соседними cells;
- outer border и inner border различать metadata;
- merged cells не должны иметь внутренние удалённые borders.

### Желаемый результат

Простая 3×3 таблица имеет правильную сетку и текст в соответствующих ячейках.

---

## Шаг 6.14. Пагинация таблиц

Таблица может не помещаться на одну страницу.

Правила MVP:

1. Не разрывать строку таблицы между страницами.
2. Если строка выше usable page — понятная ошибка либо controlled scale fallback.
3. Переносить таблицу только между строками.
4. Повторять header rows, если они помечены.
5. На новой странице рисовать верхнюю границу.
6. На предыдущей странице рисовать нижнюю границу.
7. Сохранять table id и continuation metadata.
8. Page number footer не должен пересекаться с таблицей.

В `PageLayout.metadata`:

```json
{
  "table_fragments": [
    {
      "table_id": "table-001",
      "rows": [0, 1, 2],
      "continued_from_previous": false,
      "continues_next": true
    }
  ]
}
```

---

## Шаг 6.15. Консервативно распознавать PDF-таблицы

Создать:

```text
src/plotter_processor/pdf_table_detector.py
```

Поддержать только line-based tables на первом этапе.

Алгоритм:

1. Собрать horizontal/vertical line segments.
2. Snap близкие координаты с маленьким tolerance.
3. Найти прямоугольную connected grid.
4. Проверить минимальное число строк/колонок.
5. Исключить одиночные рамки изображений.
6. Исключить underline/fraction/arrow.
7. Построить cells по intersections.
8. Назначить text spans ячейкам по bbox center/intersection.
9. Создать `SourceTableElement`.
10. Поглотить использованные line/text primitives, чтобы не печатать дважды.

Config:

```yaml
tables:
  pdf_detection:
    enabled: true
    snap_tolerance_mm: 0.6
    intersection_tolerance_mm: 0.8
    min_rows: 2
    min_columns: 2
    min_cell_width_mm: 3.0
    min_cell_height_mm: 3.0
    confidence_threshold: 0.80
```

Если confidence ниже threshold:

- не создавать semantic table;
- оставить generic lines/text;
- добавить warning.

Не пытаться в этом блоке распознавать borderless tables без линий.

---

## Шаг 6.16. Определить приоритеты классификации линий

Создать единый orchestrator классификации PDF primitives:

```text
raw text spans + raw drawings
    -> math detector
    -> table detector
    -> arrow detector
    -> underline detector
    -> generic shapes
```

Каждый primitive должен иметь state:

- `unclaimed`;
- `claimed_by_math`;
- `claimed_by_table`;
- `claimed_by_arrow`;
- `claimed_by_underline`;
- `generic`.

Один primitive не может быть поглощён двумя semantic objects.

Сохранять trace в debug JSON.

---

## Шаг 6.17. Интегрировать shapes/tables в paginator

`document_paginator.py` должен уметь обрабатывать:

- `SourceMathElement`;
- `SourceRasterImageElement`;
- `SourceVectorElement`;
- `SourceLineElement`;
- `SourceArrowElement`;
- `SourceTableElement`;
- styled text.

Не превращать paginator в один файл на 1000+ строк без структуры. Вынести:

- formula layout;
- image placement;
- shape layout;
- table layout;
- text decoration;

в отдельные модули.

Paginator должен координировать страницы, а не содержать все алгоритмы геометрии.

---

## Шаг 6.18. Добавить порядок печати semantic objects

Рекомендуемый default:

1. table borders / generic lines behind text;
2. images/vector drawings;
3. text/formulas;
4. underlines и foreground arrows, если исходный z-order требует;
5. page number.

Однако не навязывать один порядок всем документам. Использовать `z_order` и `source_order`.

Для таблицы рассмотреть два режима:

```yaml
tables:
  draw_order: borders_first
```

`borders_first` удобен для стабильной сетки. Text strokes внутри ячеек не должны объединяться с border strokes.

---

## Шаг 6.19. Обновить path optimizer

Добавить tests и поддержку:

- preserve group order;
- preserve arrow parts;
- preserve table grouping;
- не объединять underline с ближайшим glyph stroke;
- не разворачивать arrow shaft, если это меняет logical direction metadata;
- можно разворачивать generic line только если geometry эквивалентна и semantic direction отсутствует;
- не удалять короткие arrowhead strokes;
- не удалять короткие table corner segments.

---

## Шаг 6.20. Добавить debug preview для линий и таблиц

Создать:

```text
build/.../semantic-debug/
  primitives.svg
  classification.svg
  classification.json
  tables.svg
  arrows.svg
  underlines.svg
```

В classification preview разные semantic roles показывать разными debug-цветами.

В production `plotter-preview.svg` цвет можно оставить единым, но добавить `data-element-type` и `data-semantic-role`.

---

## Шаг 6.21. Обновить report

Добавить:

```json
{
  "semantic_objects": {
    "underlines": 4,
    "generic_lines": 7,
    "arrows": 3,
    "tables": 2,
    "table_cells": 18,
    "table_pages": 3,
    "pdf_table_candidates": 2,
    "pdf_tables_accepted": 1,
    "classification_conflicts": 0,
    "duplicate_primitives_suppressed": 23
  }
}
```

Для таблиц:

- rows/columns;
- merged cells;
- pages;
- scale;
- borders;
- border strokes after dedupe;
- cell text overflow;
- warnings.

Для arrows:

- source kind;
- direction;
- shaft length;
- head style;
- detection confidence.

---

## Шаг 6.22. Тесты Блока 3

Добавить:

```text
tests/test_styled_text_models.py
tests/test_docx_underlines.py
tests/test_pdf_line_classifier.py
tests/test_arrow_detector.py
tests/test_docx_arrows.py
tests/test_table_models.py
tests/test_docx_table_reader.py
tests/test_table_layout.py
tests/test_table_pagination.py
tests/test_pdf_table_detector.py
tests/test_semantic_primitive_claims.py
tests/test_semantic_path_order.py
```

### Underline tests

- single underline;
- double underline;
- words-only;
- line wrap;
- two adjacent underlined runs;
- underline inside table cell;
- PDF underline;
- fraction bar not misclassified;
- table border not misclassified.

### Arrow tests

- DOCX straight arrow;
- DOCX two-headed arrow;
- PDF line + triangle;
- PDF open V arrow;
- rotated arrow;
- short line not treated as arrow;
- table border plus nearby triangle not merged;
- direction preserved.

### Table tests

- 2×2;
- 3×3;
- merged horizontal cells;
- merged vertical cells;
- variable column widths;
- wrapped cell text;
- underlined cell text;
- formula in cell, если поддерживается;
- table across pages;
- repeated header;
- shared borders deduplicated;
- PDF line grid;
- image frame not detected as table;
- borderless PDF table rejected with warning.

### Integration tests

- DOCX: text + underline + image wrap + table;
- DOCX: table + formula + arrow;
- PDF: formula + table + arrow;
- multipage document with table and page numbers;
- centerline text and semantic lines in one G-code;
- safe G-code.

---

## Шаг 6.23. Метрики успеха Блока 3

Минимальные критерии:

- DOCX underline geometry совпадает с text run;
- simple PDF underline classified correctly;
- simple arrows retain direction;
- arrowhead не растрируется в тестовых fixtures;
- DOCX simple table сохраняет rows/columns;
- shared borders нарисованы один раз;
- table text находится внутри cells;
- multipage table разбивается между rows;
- PDF line table high-confidence detector работает;
- нет primitive double printing;
- classification conflicts == 0;
- все strokes находятся в bounds;
- G-code безопасен.

Рекомендуемые численные проверки:

```text
underline horizontal distance to expected <= 0.5 mm
arrow endpoint/head gap <= 0.7 mm
cell text bbox inside cell with tolerance <= 0.3 mm
shared border duplicate count == 0
table row split count == 0
remaining primitive claims > 1 == 0
```

---

## Шаг 6.24. Отчёт пользователю после Блока 3

Показать:

- подчёркнутый текст DOCX;
- стрелку DOCX или PDF;
- простую таблицу;
- merged cells;
- multipage table;
- classification debug для PDF.

В отчёте отдельно написать, что пока не поддерживается, например:

- borderless PDF tables;
- сложные gradients;
- SmartArt;
- nested tables;
- диагональные borders;
- полный DrawingML;
- сложные custom arrowheads.

После отчёта написать:

```text
Блок 3 закончен. Все три блока UPD_Plotter_7 реализованы и проверены.
```

---

# 7. Общие тесты перед завершением UPD_Plotter_7

## 7.1. Полный test suite

```bash
make test
make lint
```

Дополнительно:

```bash
.venv/bin/python -m plotter_processor --help
.venv/bin/python -m plotter_processor run --help
.venv/bin/python -m plotter_processor compose --help
```

## 7.2. Backward compatibility matrix

Проверить:

| Input | Font mode | Images | LaTeX | Layout | Expected |
|---|---|---|---|---|---|
| TXT plain | outline | off | off | reflow | old flow works |
| TXT plain | centerline | off | off | reflow | old centerline works |
| TXT LaTeX | centerline | off | centerline | reflow | formulas work |
| DOCX plain | centerline | auto | auto | reflow | no regression |
| DOCX images | centerline | auto | auto | hybrid | wrapping works |
| DOCX table | centerline | auto | auto | hybrid | table works |
| PDF text | centerline | auto | off | reflow | old path works |
| PDF formula | centerline | auto | auto | preserve | visual math works |
| PDF images | centerline | auto | auto | preserve | position preserved |
| PDF table | centerline | auto | auto | preserve | table/lines work |

## 7.3. Determinism

Два одинаковых запуска должны создавать одинаковые:

- `paths.json`;
- `job.json`;
- normalized SVG geometry;
- report metrics;
- G-code;
- formula region decisions;
- image placements;
- line classifications;
- table detection results.

Timestamp не включать в сравниваемую часть либо вынести отдельно.

## 7.4. Performance

Измерить:

- LaTeX render time per formula;
- PDF formula clip render time;
- centerline graph time;
- hybrid placement time per image;
- flow layout time;
- DOCX table parse time;
- PDF table detector time;
- peak memory;
- total job time.

Не допустить заметного замедления plain TXT без новых объектов.

Рекомендуемое требование:

```text
plain TXT pipeline slowdown <= 10%
```

Для сложных объектов сохранять метрики отдельно.

## 7.5. Complexity limits

Проверить ошибки для:

- слишком большой formula mask;
- слишком сложная formula graph;
- слишком большое изображение;
- слишком много exclusion zones;
- слишком много PDF drawing primitives;
- слишком большая таблица;
- слишком много cells;
- слишком длинная строка в cell;
- слишком много pages.

Ошибки должны быть понятными и не оставлять stale G-code.

## 7.6. G-code safety

Проверить отсутствие:

```text
M104
M109
M140
M190
extrusion E coordinates
G28 без явного разрешения
NaN
Infinity
координат вне workspace
отрицательных Z вне config
неограниченных dwell
```

Проверить, что multipage pause/park не сломаны новыми объектами.

## 7.7. Physical dry-run

До печати ручкой:

1. Запустить G-code с поднятым пером.
2. Проверить границы A5.
3. Проверить формулу с дробью и индексами.
4. Проверить рисунок с обтеканием.
5. Проверить стрелку.
6. Проверить таблицу 3×3.
7. Проверить смену страницы.
8. Только после этого опускать перо.

---

# 8. Рекомендуемая структура новых и изменяемых файлов

Ориентировочно:

```text
src/plotter_processor/
  document_models.py                 # расширить source model
  structured_document_reader.py      # сохранить общий entrypoint
  docx_document_reader.py            # styled runs, anchors, OMML, tables, arrows
  pdf_document_reader.py             # spans, primitives, source coordinates
  pipeline.py                        # новые options/report, минимум алгоритмов
  document_paginator.py              # orchestration, вынести тяжёлую логику

  layout_models.py                   # RectMM, PlacedElement, ExclusionZone
  flow_layout.py                     # text around exclusion zones
  document_layout.py                 # reflow/hybrid/preserve orchestration
  placement_solver.py                # deterministic candidate scoring
  layout_debug_exporter.py

  raster_centerline.py               # общий mask-to-centerline adapter
  latex_renderer.py                  # centerline render mode
  latex_layout.py                    # baseline/line integration
  latex_parser.py                    # сохранить delimiters
  omml_parser.py                     # supported OMML subset
  pdf_math_detector.py
  pdf_region_renderer.py

  text_decorations.py                # underline geometry
  shape_models.py                    # если не в document_models
  shape_layout.py
  arrow_detector.py
  pdf_line_classifier.py
  pdf_table_detector.py
  semantic_primitive_claims.py

  table_layout.py
  table_borders.py
  table_paginator.py

  path_optimizer.py                  # semantic groups/order
  models.py                          # stroke provenance fields
  svg_exporter.py                    # data-semantic-role

configs/
  layout.yaml                        # latex/layout/shapes/tables defaults

examples/
  update_7/
    latex-centerline.txt
    latex-and-image.docx
    wrapped-image.docx
    arrows-and-table.docx
    formula-table.pdf

fixtures or tests/fixtures/update_7/
  ...

tests/
  test_raster_centerline.py
  test_latex_centerline_renderer.py
  test_omml_parser.py
  test_pdf_math_detector.py
  test_layout_mapping.py
  test_exclusion_zones.py
  test_flow_layout.py
  test_docx_image_anchors.py
  test_pdf_preserve_layout.py
  test_docx_underlines.py
  test_pdf_line_classifier.py
  test_arrow_detector.py
  test_docx_arrows.py
  test_docx_table_reader.py
  test_table_layout.py
  test_table_pagination.py
  test_pdf_table_detector.py
  test_semantic_path_order.py

tools/
  generate_update_7_fixtures.py
  update_7_baseline.py
  compare_update_7.py
```

Не создавать каждый файл механически, если логика компактно помещается в существующий модуль. Но запрещено складывать LaTeX-centerline, image wrapping, arrow detection и table layout в один `pipeline.py` или `document_paginator.py`.

---

# 9. Рекомендуемая последовательность commits

Каждый commit должен быть рабочим и проходить targeted tests.

## Подготовка

1. `test: add update 7 fixtures and baseline runner`
2. `refactor: add normalized source and target layout models`

## Блок 1

3. `refactor: extract reusable raster centerline geometry`
4. `feat: render mathtext formulas as centerlines`
5. `feat: add formula quality metrics and debug artifacts`
6. `feat: parse basic docx omml formulas`
7. `feat: detect and centerline visual formulas in pdf`
8. `test: add latex and pdf math regression suite`
9. `docs: document centerline latex workflow`

## Блок 2

10. `feat: preserve docx image anchor and wrapping metadata`
11. `feat: add source-aware preserve layout mapping`
12. `feat: add exclusion-zone text flow`
13. `feat: add deterministic hybrid image placement`
14. `feat: export layout placement debug artifacts`
15. `test: add wrapped image and preserve-layout regression suite`
16. `docs: document document layout modes`

## Блок 3

17. `feat: preserve styled text runs and underlines`
18. `feat: classify pdf lines and underlines`
19. `feat: import docx and pdf arrows as centerline shapes`
20. `feat: add structured docx table model and reader`
21. `feat: layout and paginate tables`
22. `feat: detect line-based pdf tables`
23. `refactor: preserve semantic path groups during optimization`
24. `test: add lines arrows and tables regression suite`
25. `docs: document semantic shapes and tables`

## Завершение

26. `chore: update cli config examples and reports for update 7`
27. `docs: add update 7 final verification report`

Не объединять все изменения в один огромный commit.

---

# 10. Команды для демонстрации результата

Команды адаптировать к фактическим fixtures и шрифту.

## Блок 1

```bash
.venv/bin/python -m plotter_processor run \
  tests/fixtures/update_7/latex/latex_complex.txt \
  --font assets/handwriting.ttf \
  --font-mode centerline \
  --latex mathtext \
  --latex-stroke-mode centerline \
  --latex-debug \
  --page A5 \
  --output-dir build/update_7/candidate/block_1/latex-complex
```

```bash
.venv/bin/python -m plotter_processor run \
  tests/fixtures/update_7/latex/pdf_formula_vector.pdf \
  --font assets/handwriting.ttf \
  --font-mode centerline \
  --pdf-math auto \
  --document-layout preserve \
  --math-debug \
  --page A5 \
  --output-dir build/update_7/candidate/block_1/pdf-formula
```

## Блок 2

```bash
.venv/bin/python -m plotter_processor run \
  tests/fixtures/update_7/images/image_left_wrap.docx \
  --font assets/handwriting.ttf \
  --font-mode centerline \
  --images centerline \
  --document-layout hybrid \
  --layout-debug \
  --page A5 \
  --output-dir build/update_7/candidate/block_2/left-wrap
```

```bash
.venv/bin/python -m plotter_processor run \
  tests/fixtures/update_7/images/image_preserve_position.pdf \
  --font assets/handwriting.ttf \
  --font-mode centerline \
  --document-layout preserve \
  --layout-debug \
  --page A5 \
  --output-dir build/update_7/candidate/block_2/pdf-preserve
```

## Блок 3

```bash
.venv/bin/python -m plotter_processor run \
  tests/fixtures/update_7/lines_tables/table_with_underlines.docx \
  --font assets/handwriting.ttf \
  --font-mode centerline \
  --document-layout hybrid \
  --semantic-debug \
  --page A5 \
  --output-dir build/update_7/candidate/block_3/table-underlines
```

```bash
.venv/bin/python -m plotter_processor run \
  tests/fixtures/update_7/lines_tables/arrows.pdf \
  --font assets/handwriting.ttf \
  --font-mode centerline \
  --document-layout preserve \
  --semantic-debug \
  --page A5 \
  --output-dir build/update_7/candidate/block_3/pdf-arrows
```

---

# 11. Definition of Done по блокам

## Блок 1 считается завершённым, если

- [ ] MathText формулы имеют centerline stroke mode;
- [ ] default формулы не рисуются двойным outline;
- [ ] inline layout корректен;
- [ ] block layout корректен;
- [ ] basic OMML поддержан;
- [ ] PDF visual math region печатается;
- [ ] absorbed PDF primitives не дублируются;
- [ ] quality metrics сохраняются;
- [ ] debug artifacts создаются;
- [ ] strict mode работает;
- [ ] tests проходят;
- [ ] пользователь получил отдельный отчёт.

## Блок 2 считается завершённым, если

- [ ] source coordinates нормализованы;
- [ ] DOCX anchor/wrap читаются;
- [ ] preserve layout реально сохраняет bbox;
- [ ] hybrid layout реализован либо явно обоснован другой эквивалент;
- [ ] left/right image placement сохраняется;
- [ ] text wrapping работает;
- [ ] aspect ratio сохраняется;
- [ ] overlap предотвращается;
- [ ] layout debug создаётся;
- [ ] report содержит displacement/scale;
- [ ] tests проходят;
- [ ] пользователь получил отдельный отчёт.

## Блок 3 считается завершённым, если

- [ ] styled text model существует;
- [ ] DOCX underline печатается;
- [ ] PDF underline классифицируется;
- [ ] generic lines печатаются;
- [ ] DOCX arrows печатаются;
- [ ] PDF arrows распознаются для базовых fixtures;
- [ ] DOCX tables имеют структурированную модель;
- [ ] merged cells поддерживаются;
- [ ] shared borders deduplicated;
- [ ] table text размещается внутри cells;
- [ ] multipage table работает;
- [ ] line-based PDF table detector работает консервативно;
- [ ] primitive double printing отсутствует;
- [ ] tests проходят;
- [ ] пользователь получил отдельный отчёт.

---

# 12. Definition of Done всего UPD_Plotter_7

Обновление считается полностью завершённым только при выполнении всех условий:

- [ ] все три блока завершены отдельно;
- [ ] после каждого блока опубликован отдельный отчёт;
- [ ] `make test` проходит;
- [ ] `make lint` проходит;
- [ ] README обновлён;
- [ ] CLI help обновлён;
- [ ] `configs/layout.yaml` обновлён;
- [ ] старые configs работают через defaults;
- [ ] plain TXT не сломан;
- [ ] plain DOCX не сломан;
- [ ] plain PDF не сломан;
- [ ] centerline text не сломан;
- [ ] word joining не сломан;
- [ ] pagination не сломана;
- [ ] page numbering не сломан;
- [ ] park/pause между страницами не сломан;
- [ ] output G-code безопасен;
- [ ] все новые объекты имеют provenance;
- [ ] duplicate printing исключён;
- [ ] debug artifacts доступны;
- [ ] baseline/candidate comparison сохранён;
- [ ] известные ограничения перечислены честно;
- [ ] физический dry-run выполнен хотя бы на A5.

---

# 13. Что сознательно не входит в UPD_Plotter_7

Чтобы обновление не превратилось в бесконечную задачу, не включать без отдельного согласования:

- полный TeX engine;
- внешние LaTeX packages;
- TikZ;
- восстановление исходного `.tex` из PDF;
- OCR сканированных формул;
- handwriting recognition;
- borderless PDF table detection;
- полный SmartArt;
- полный DrawingML;
- сложные gradients и transparency;
- nested tables;
- диагональные table borders;
- произвольные Word text boxes;
- точное воспроизведение всех Office wrapping polygons;
- цветную многоперьевую печать;
- заливку областей штриховкой;
- автоматическую смену пера.

Если в процессе реализации одна из этих функций понадобится для basic fixture, Codex должен остановиться, описать причину и предложить минимальный безопасный fallback, а не незаметно расширять scope.

---

# 14. Финальный отчёт Codex

После всех блоков создать:

```text
docs/update-7-final-report.md
build/update_7/final-summary.json
```

В final report включить:

1. Base SHA и final SHA.
2. Список commits.
3. Архитектурную схему.
4. Поддерживаемые входные объекты.
5. Ограничения.
6. Таблицу baseline/candidate.
7. Ссылки на previews.
8. Результаты tests/lint.
9. Performance metrics.
10. G-code safety checks.
11. Результат physical dry-run.
12. Рекомендации для следующего обновления.

Пример итоговой таблицы:

| Возможность | До UPD 7 | После UPD 7 | Ограничения |
|---|---|---|---|
| LaTeX из TXT/DOCX | outline | centerline | MathText subset |
| OMML | warning | basic subset | не весь OMML |
| Формулы PDF | отключены | visual centerline | без восстановления `.tex` |
| Позиция рисунков | центрирование | preserve/hybrid | tight wrap approximated |
| Обтекание | нет | square/top-bottom | polygon wrap limited |
| Underline | теряется | поддержан | редкие styles approximated |
| Стрелки | generic/raster | semantic centerline | basic shapes |
| DOCX tables | plain text | structured grid | nested tables unsupported |
| PDF tables | generic lines | line-grid detection | borderless unsupported |

Финальное сообщение пользователю не должно скрывать remaining warnings и manual review cases.
