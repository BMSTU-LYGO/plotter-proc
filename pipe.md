# Текущий pipeline plotter-processor

В проекте существуют два маршрута обработки:

1. `plotter-fast` — основной быстрый путь для обычного текста. Он работает только с заранее скомпилированным centerline font cache и не обрабатывает TTF во время печати.
2. `plotter-processor run` — полный advanced pipeline для сложных документов, изображений, формул, нескольких шрифтов и режимов сохранения исходной раскладки.

## 1. Подготовка шрифта offline

Тяжёлая обработка TTF вынесена в отдельную команду:

```bash
plotter-font-compile assets/1.ttf \
  --text input.txt \
  -o font-cache/<font>/centerlines.json
```

Схема компиляции:

```text
TTF
  -> cmap и метрики шрифта
  -> raster glyph
  -> mask
  -> skeleton/centerline
  -> построение маршрута внутри glyph
  -> cleanup и smoothing
  -> entry/exit anchors
  -> готовые strokes
  -> JSON cache и glyph shards
```

Кэш содержит:

```text
CompiledPlotterFont
  font_sha256
  units_per_em
  ascent/descent/line_gap
  glyphs: dict[char, CenterlineGlyph]

CenterlineGlyph
  char/codepoint/glyph_name
  advance_font_units
  strokes[]
  entry_anchor
  exit_anchor
  stroke_metadata
```

Компилятор находится в `src/plotter_processor/centerline_font/compiler.py`, сериализация — в `serializer.py`, offline CLI — в `font_compile_cli.py`.

## 2. Быстрый текстовый pipeline

Запуск:

```bash
plotter-fast input.txt \
  --cache font-cache/<font> \
  --output-dir build/fast
```

Также поддерживается извлечение текста из DOCX и PDF через существующий structured document reader.

Общая схема:

```text
TXT / Markdown / DOCX / PDF
  -> read_structured_document
  -> извлечение абзацев и текста таблиц
  -> tokenization с сохранением \n и \f
  -> FastFont.load(cache), один раз на процесс
  -> WordBuilder
  -> bounded in-memory word LRU
  -> FastLayout: words -> lines -> pages
  -> PathDocument для каждой страницы
  -> generate_gcode
  -> единый output.gcode + fast-report.json
```

### FastFont

`src/plotter_processor/fast_font.py` загружает монолитный cache или canonical sharded cache. Повторная загрузка того же пути в процессе возвращает уже загруженный объект.

Lookup выполняется как обычный `dict.get(char)`. Отсутствующий символ использует только заранее скомпилированный fallback glyph. Runtime никогда не запускает TTF parsing, rasterization, skeletonization или font compilation.

### WordBuilder

`src/plotter_processor/fast_word.py` собирает слово сразу из готовых glyph:

```text
word
  -> O(1) lookup каждого символа
  -> перенос strokes на накопленный advance
  -> выбор primary stroke
  -> quadratic connector: previous.exit -> next.entry
  -> disconnected элементы в secondary strokes
  -> WordGeometry
```

`WordGeometry` содержит текст, ширину в font units, primary strokes, secondary strokes и список отсутствующих символов.

Готовые слова сохраняются в bounded LRU. Повторяющееся слово не проходит повторную сборку glyph и connectors.

### FastLayout

`src/plotter_processor/fast_layout.py` выполняет один линейный проход по токенам:

```text
слово помещается -> добавить в текущую строку
не помещается    -> начать новую строку
строка не помещается по высоте -> создать новую страницу
\n                -> новая строка
\f                -> новая страница
```

Учитываются размеры страницы, поля, высота строки и расстояние между словами. По умолчанию fast CLI использует плотные безопасные поля 2 мм, зазор 0.5 мм между line boxes, минимальный baseline-шаг по реальным метрикам шрифта и компактный межсловный пробел. Очень длинное слово целиком масштабируется до ширины рабочей области страницы.

После размещения `WordGeometry` преобразуется в `PlotterStroke` с окончательными координатами страницы. Отдельная обработка glyph после layout не выполняется.

### G-code и метрики

`src/plotter_processor/gcode_exporter.py` получает готовый `PathDocument`. Для каждого stroke формируется один цикл перемещения, `PEN_DOWN`, рисования и `PEN_UP`. Все страницы дополнительно объединяются в готовый `output.gcode`; между ними добавляются подъём пера, парковка и безопасная пауза для смены листа.

Сохраняются существующие проверки workspace, keep-out zones, feedrate, координат и лимита команд. Heating и extrusion команды не генерируются.

`fast-report.json` содержит:

- время извлечения текста;
- время загрузки font cache;
- время сборки слов и layout;
- время генерации G-code;
- общее время;
- число страниц и слов;
- cache hits/misses;
- отсутствующие символы;
- `pen_down_count`, `pen_up_count`, `avg_pen_down_per_word`.

## 3. Advanced pipeline

Запуск:

```bash
plotter-processor run input.docx \
  --font assets/1.ttf \
  --output-dir build/advanced
```

Схема:

```text
input
  -> structured document reader
  -> document model
  -> выбор reflow/hybrid/preserve layout
  -> paragraph/document layout и pagination
  -> font registry и fallback fonts
  -> outline или centerline font path
  -> glyph path materialization
  -> images / SVG / math paths
  -> handwriting variation и word routing
  -> simplification / optional optimization
  -> page geometry и safety validation
  -> preview, reports и debug artifacts
  -> multipage G-code
```

Advanced pipeline расположен главным образом в `src/plotter_processor/pipeline.py`. Он поддерживает:

- TXT, DOCX, PDF и SVG;
- изображения и векторные элементы;
- таблицы, формулы и page-aware layout;
- outline и centerline режимы;
- fallback fonts;
- сохранение или перестройку раскладки документа;
- handwriting variation и сложные соединения;
- preview/debug/audit артефакты;
- stage cache и параллельную обработку страниц.

В centerline-режиме advanced pipeline всё ещё может вызвать `compile_centerline_font` при отсутствии нужного glyph в cache. Поэтому для обычной быстрой печати текста следует использовать `plotter-fast`.

## 4. Граница между режимами

```text
                         input
                           |
                 structured text extraction
                           |
             +-------------+-------------+
             |                           |
       FAST TEXT                      ADVANCED
             |                           |
   precompiled font cache       font registry / outline /
             |                 centerline compiler fallback
        WordBuilder                       |
             |                  complex document layout
       word LRU cache                     |
             |                 images / math / handwriting
       linear layout                      |
             +-------------+-------------+
                           |
                    PathDocument pages
                           |
                  validation and G-code
```

`plotter-fast` следует выбирать для обычного текста, когда главные требования — скорость и малое число поднятий пера. Advanced pipeline нужен, когда документ содержит нетекстовую геометрию или требует точного сохранения сложной исходной структуры.
