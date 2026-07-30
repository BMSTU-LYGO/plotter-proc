# UPD_Plotter_1

## Подробный технический план для Codex: переход `plotter-proc` на прямой пайплайн TTF → SVG → G-code

**Рабочий репозиторий:** `https://github.com/BMSTU-LYGO/plotter-proc`  
**Рекомендуемая ветка:** `upd/vector-ttf-pipeline`  
**Главная цель:** убрать растровый рендеринг, бинаризацию и скелетизацию. Программа должна загружать пользовательский TTF, извлекать из него исходные векторные контуры, раскладывать текст на A4/A5, создавать SVG, преобразовывать кривые в траектории и передавать их генератору G-code.

---

# 0. Роль Codex и правила работы

Работай в существующем репозитории. Новый репозиторий не создавай, если нет объективной технической причины. Текущая структура уже содержит полезные модули чтения документов, конфигурации станка, валидации и генерации G-code — их нужно сохранить и адаптировать.

Работай поэтапно. После каждого этапа:

1. запускай тесты;
2. запускай линтер;
3. проверяй CLI;
4. фиксируй результат отдельным коммитом;
5. не переходи дальше, пока текущий этап не работает.

Не пытайся улучшать старую скелетизацию. Она должна быть исключена из основного pipeline.

---

# 1. Почему требуется переделка

Текущий pipeline работает примерно так:

```text
DOCX/PDF
   ↓
текст
   ↓
TTF рисуется через Pillow в PNG
   ↓
threshold / бинаризация
   ↓
skeletonize
   ↓
обход пиксельного графа
   ↓
SVG polyline
   ↓
G-code
```

Из-за этого исходные кривые TTF теряются. Появляются:

- пиксельные ступеньки;
- дёрганые линии;
- лишние ответвления;
- повторные проходы;
- тысячи лишних точек;
- зависимость качества от DPI, threshold и параметров skeletonize.

Новый pipeline:

```text
TXT / DOCX / PDF с текстовым слоем
                ↓
         извлечение текста
                ↓
      нормализация Unicode
                ↓
       загрузка пользовательского TTF
                ↓
       проверка требуемых глифов
                ↓
     раскладка текста в миллиметрах
                ↓
   извлечение контуров прямо из TTF
                ↓
       точный font-preview.svg
                ↓
 адаптивное разбиение кривых на линии
                ↓
        plotter-preview.svg
                ↓
             paths.json
                ↓
       безопасный output.gcode
```

В новом основном pipeline не должно быть PNG, DPI, threshold, skeleton и пиксельного графа.

---

# 2. Продуктовое ограничение, которое считается нормальным

Обычный TTF содержит **контуры формы букв**, а не центральную траекторию движения руки.

Следовательно, плоттер будет проходить:

- по внешнему контуру буквы;
- по внутреннему контуру;
- по отверстиям;
- по отдельным компонентам символов.

Например, у `О` будет внешний и внутренний замкнутый контур. Это допустимо.

Не нужно:

- искать центральную линию;
- восстанавливать порядок человеческих штрихов;
- скелетизировать символ;
- пытаться превратить контурный TTF в однолинейный шрифт.

Главная цель обновления — плавный, предсказуемый и воспроизводимый результат.

---

# 3. Использование `draw-your-font`

`draw-your-font` использовать как отдельный внешний инструмент:

```text
фотография почерка
        ↓
draw-your-font
        ↓
my-handwriting.ttf
        ↓
plotter-proc
        ↓
SVG + paths.json + G-code
```

Внутри `plotter-proc` пользователь передаёт готовый файл:

```bash
plotter-processor run examples/input.txt \
  --font assets/my-handwriting.ttf \
  --page A5 \
  --size normal \
  --output-dir build
```

На этом обновлении не нужно:

- запускать Node.js из Python;
- добавлять npm-зависимости;
- копировать код `draw-your-font`;
- создавать TTF внутри команды `run`;
- делать редактор почерка.

---

# 4. Что оставить, заменить и убрать

## 4.1. Оставить и адаптировать

```text
src/plotter_processor/
├── __init__.py
├── __main__.py
├── cli.py
├── config.py
├── document_reader.py
├── gcode_exporter.py
├── models.py
├── pipeline.py
├── text_normalizer.py
└── validator.py
```

## 4.2. Полностью переделать

```text
src/plotter_processor/svg_exporter.py
```

Он должен создавать:

- `font-preview.svg` — точные кривые TTF;
- `plotter-preview.svg` — реальные линейные траектории плоттера.

## 4.3. Исключить из основного pipeline

```text
src/plotter_processor/page_renderer.py
src/plotter_processor/skeletonizer.py
src/plotter_processor/path_tracer.py
```

На время миграции можно перенести их в:

```text
src/plotter_processor/legacy/
```

Но `pipeline.py` и команда `run` не должны их импортировать.

---

# 5. Целевая структура

```text
plotter-proc/
├── assets/
│   └── .gitkeep
├── configs/
│   ├── layout.yaml
│   └── machine.yaml
├── examples/
│   ├── input.txt
│   ├── input.docx
│   └── input.pdf
├── src/plotter_processor/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── document_reader.py
│   ├── font_loader.py
│   ├── glyph_outline.py
│   ├── vector_layout.py
│   ├── curve_flattener.py
│   ├── path_builder.py
│   ├── path_optimizer.py
│   ├── svg_exporter.py
│   ├── gcode_exporter.py
│   ├── models.py
│   ├── pipeline.py
│   ├── text_normalizer.py
│   └── validator.py
├── tests/
│   ├── conftest.py
│   ├── test_document_reader.py
│   ├── test_font_loader.py
│   ├── test_vector_layout.py
│   ├── test_glyph_outline.py
│   ├── test_curve_flattener.py
│   ├── test_path_optimizer.py
│   ├── test_svg_exporter.py
│   ├── test_gcode_exporter.py
│   ├── test_pipeline.py
│   └── test_cli.py
├── README.md
├── Makefile
├── pyproject.toml
└── UPD_Plotter_1.md
```

Названия допускается слегка изменить, но ответственность модулей должна оставаться разделённой.

---

# 6. Основные зависимости

Сохранить Python `>=3.11`.

Добавить в `pyproject.toml`:

```toml
"fonttools>=4.0"
```

Использовать:

```python
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
```

Для геометрии не парсить SVG-строки регулярными выражениями. Использовать pen API `fontTools`.

После завершения миграции проверить необходимость:

```text
Pillow
numpy
scikit-image
```

Если новый код их не использует — удалить из основных зависимостей.

`uharfbuzz` пока не обязателен. Для MVP достаточно `cmap`, `hmtx`, базовых метрик, пробелов и переноса строк.

---

# 7. Этап 0 — подготовка ветки и фиксация исходного состояния

## Действия

```bash
git checkout -b upd/vector-ttf-pipeline
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
make test
make lint
.venv/bin/python -m plotter_processor --help
```

Зафиксировать текущие форматы:

- `paths.json`;
- `report.json`;
- `output.gcode`;
- аргументы CLI;
- структуру `layout.yaml` и `machine.yaml`.

## Желаемый результат

Исходное состояние воспроизводимо. Известны текущие тесты, ошибки и форматы данных.

## Критерии приёмки

- ветка создана;
- установка проходит либо все исходные ошибки документированы;
- старый pipeline ещё не сломан;
- известны точки совместимости с G-code exporter.

---

# 8. Этап 1 — обновить конфигурацию

## 8.1. `pyproject.toml`

Добавить `fonttools`. Старые растровые зависимости пока не удалять.

## 8.2. Новый `configs/layout.yaml`

Убрать из актуальных настроек:

- DPI;
- threshold;
- remove_small_objects;
- skeleton;
- `simplify_epsilon_px`.

Добавить:

```yaml
pages:
  A4:
    width_mm: 210.0
    height_mm: 297.0
  A5:
    width_mm: 148.0
    height_mm: 210.0

margins_mm:
  left: 10.0
  right: 10.0
  top: 10.0
  bottom: 10.0

sizes:
  small:
    em_size_mm: 4.0
    line_height_multiplier: 1.25
    paragraph_spacing_mm: 2.0
  normal:
    em_size_mm: 5.0
    line_height_multiplier: 1.25
    paragraph_spacing_mm: 2.5
  large:
    em_size_mm: 6.5
    line_height_multiplier: 1.30
    paragraph_spacing_mm: 3.0

vector:
  flatten_tolerance_mm: 0.08
  min_segment_length_mm: 0.03
  max_points_per_contour: 5000
  max_recursion_depth: 20
  optimize_travel: true

preview:
  plotter_stroke_width_mm: 0.20
  show_page_border: true

layout:
  missing_glyph_policy: error
  tab_spaces: 4
```

Сохранить CLI `--size small|normal|large`, но теперь он выбирает `em_size_mm`.

## Желаемый результат

Вся геометрия нового pipeline задаётся в миллиметрах.

## Критерии приёмки

- YAML валиден;
- A4/A5 загружаются;
- размеры small/normal/large загружаются;
- новый код не требует DPI;
- ошибка конфигурации содержит имя отсутствующего поля.

## Коммит

```text
refactor: add vector pipeline configuration
```

---

# 9. Этап 2 — расширить модели данных

Обновить `models.py`.

Рекомендуемые модели:

```python
@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float
```

```python
@dataclass(frozen=True, slots=True)
class PageSpec:
    name: str
    width_mm: float
    height_mm: float
```

```python
@dataclass(frozen=True, slots=True)
class FontMetrics:
    units_per_em: int
    ascent: int
    descent: int
    line_gap: int
```

```python
@dataclass(frozen=True, slots=True)
class PositionedGlyph:
    char: str
    codepoint: int
    glyph_name: str
    x_mm: float
    baseline_y_mm: float
    advance_mm: float
    scale_mm_per_font_unit: float
    line_index: int
    glyph_index: int
```

```python
@dataclass(slots=True)
class PlotterStroke:
    id: int
    points: list[Point]
    closed: bool
    glyph_index: int | None = None
    char: str | None = None
    contour_index: int | None = None
```

```python
@dataclass(slots=True)
class PathDocument:
    page_width_mm: float
    page_height_mm: float
    strokes: list[PlotterStroke]
    warnings: list[str]
    metadata: dict[str, object]
```

## Координатная система

После layout:

- X и Y в миллиметрах;
- начало страницы — левый верхний угол;
- X вправо;
- Y вниз.

TTF:

- font units;
- Y вверх.

Преобразование выполняется один раз при размещении глифа.

## `paths.json`

Рекомендуемый формат:

```json
{
  "format": "plotter-paths",
  "version": 2,
  "page": {
    "width_mm": 148.0,
    "height_mm": 210.0
  },
  "metadata": {
    "coordinate_system": "page-mm-top-left",
    "pipeline": "ttf-vector"
  },
  "strokes": [
    {
      "id": 0,
      "glyph_index": 0,
      "char": "П",
      "contour_index": 0,
      "closed": true,
      "points": [[10.0, 15.0], [10.2, 14.8]]
    }
  ],
  "warnings": []
}
```

Сохранить совместимость с `gcode_exporter.py` либо обновить сериализатор и exporter одновременно.

## Желаемый результат

Новые модули обмениваются типизированными объектами в миллиметрах. NumPy не нужен.

## Критерии приёмки

- JSON записывается и читается обратно;
- нет DPI в `PathDocument`;
- координаты имеют понятную систему;
- G-code exporter получает список штрихов в mm.

## Коммит

```text
refactor: introduce vector path data models
```

---

# 10. Этап 3 — загрузка и проверка TTF

Создать:

```text
src/plotter_processor/font_loader.py
```

## Ответственность

- проверить существование файла;
- открыть TTF через `TTFont`;
- получить `glyphSet`;
- получить `getBestCmap()`;
- получить `head.unitsPerEm`;
- получить `hhea.ascent`, `descent`, `lineGap`;
- получить `hmtx.metrics`;
- проверять символы входного текста;
- закрывать файл.

Рекомендуемый интерфейс:

```python
@dataclass(slots=True)
class LoadedFont:
    path: Path
    font: TTFont
    glyph_set: Mapping[str, object]
    cmap: dict[int, str]
    metrics: FontMetrics
    advances: dict[str, int]

    def glyph_name_for_char(self, char: str) -> str:
        ...

    def advance_for_glyph(self, glyph_name: str) -> int:
        ...
```

Желательно реализовать context manager.

## Проверка символов

После нормализации текста:

1. собрать уникальные печатные символы;
2. исключить пробелы и переводы строк;
3. проверить каждый codepoint в `cmap`;
4. при отсутствии остановить pipeline.

Ошибка:

```text
Font is missing 2 required glyphs: "ё" (U+0451), "—" (U+2014)
```

Пробел может не иметь контура, но должен иметь advance. Fallback — `0.33 * unitsPerEm` с warning.

Composite glyphs (`ё`, `й`) не разбирать вручную, если `glyph.draw(pen)` корректно раскрывает компоненты.

## Желаемый результат

Программа заранее обнаруживает несовместимый шрифт и получает реальные метрики TTF.

## Критерии приёмки

- валидный TTF открывается;
- повреждённый TTF даёт контролируемую ошибку;
- missing glyph показывает Unicode-код;
- advance берётся из `hmtx`;
- composite glyph не падает;
- файл закрывается.

## Тесты

Создать `tests/test_font_loader.py`. Не использовать системные шрифты. Тестовый TTF генерировать через `FontBuilder` во временной директории.

## Коммит

```text
feat: load and validate TTF fonts with fontTools
```

---

# 11. Этап 4 — добавить TXT

Обновить `document_reader.py`.

Поддержать `.txt` в UTF-8 и UTF-8 with BOM (`utf-8-sig`). Сохранить DOCX и PDF с текстовым слоем.

TXT нужен для быстрого тестирования:

```bash
plotter-processor run examples/input.txt --font assets/handwriting.ttf ...
```

## Критерии приёмки

- кириллица читается;
- переводы строк сохраняются;
- пустой файл даёт понятную ошибку;
- неизвестное расширение отклоняется.

## Коммит

```text
feat: support UTF-8 text input
```

---

# 12. Этап 5 — векторная раскладка текста

Создать:

```text
src/plotter_processor/vector_layout.py
```

## Вход

- нормализованные абзацы;
- `LoadedFont`;
- `PageSpec`;
- margins;
- выбранный size;
- line height;
- paragraph spacing.

## Выход

```python
@dataclass(slots=True)
class LayoutResult:
    glyphs: list[PositionedGlyph]
    warnings: list[str]
    line_count: int
    character_count: int
    used_width_mm: float
    used_height_mm: float
```

## Размер

```text
scale_mm_per_font_unit = em_size_mm / units_per_em
```

## Baseline

```text
baseline_y = top_margin + ascent * scale
```

## Высота строки

```text
natural_line_height = (ascent - descent + line_gap) * scale
line_advance = natural_line_height * line_height_multiplier
```

Учитывать, что descent обычно отрицательный.

## Размещение

Для каждого символа:

1. определить glyph name;
2. получить advance width;
3. перевести advance в mm;
4. создать `PositionedGlyph`;
5. увеличить X.

Пробел влияет на X, но не создаёт контур.

## Перенос строк

- перенос по словам;
- пробел не должен появляться в начале новой строки;
- если слово шире строки, переносить по символам;
- явный `\n` всегда создаёт новую строку;
- неразрывный пробел запрещает перенос внутри связки.

## Переполнение

Если строка выходит за нижнее поле:

```text
Text does not fit on one page
```

Не обрезать текст молча.

## Unicode

Нормализовать NFC. Поддержать `ё`, тире, кавычки, табы и CRLF.

## Kerning

Полный GPOS не обязателен. Для MVP допустим режим:

```json
"shaping": "basic-cmap-hmtx"
```

## Критерии приёмки

- `Привет, мир!` корректно размещается;
- перенос рассчитывается по advance;
- длинное слово переносится;
- переполнение останавливает pipeline;
- A4/A5 отличаются;
- нет DPI и пикселей.

## Тесты

- одна строка;
- несколько слов;
- перенос;
- абзацы;
- длинное слово;
- overflow;
- разные размеры;
- разные поля.

## Коммит

```text
feat: add millimeter-based text layout
```

---

# 13. Этап 6 — извлечение точных контуров

Создать:

```text
src/plotter_processor/glyph_outline.py
```

## Правила

Для точного SVG использовать `SVGPathPen` и `TransformPen`.

Преобразование точки:

```text
page_x = glyph_x_mm + font_x * scale
page_y = baseline_y_mm - font_y * scale
```

Аффинное преобразование:

```text
(scale, 0, 0, -scale, glyph_x_mm, baseline_y_mm)
```

Для каждого `PositionedGlyph`:

1. создать `SVGPathPen`;
2. обернуть в `TransformPen`;
3. вызвать `glyph.draw(pen)`;
4. получить `d`;
5. сохранить metadata.

Пример:

```xml
<path
  data-char="П"
  data-glyph-name="uni041F"
  data-glyph-index="0"
  d="M ..."
  fill="black"
  stroke="none"
/>
```

Пробел и пустые glyphs не создают path.

## Критерии приёмки

- SVG содержит `Q`/`C` или корректные контуры;
- координаты в mm;
- Y не перевёрнут;
- текст не зеркальный;
- composite glyph работает;
- PNG не создаётся.

## Тесты

- line contour;
- quadratic;
- closed contour;
- несколько контуров;
- transform;
- composite glyph;
- empty glyph.

## Коммит

```text
feat: extract exact glyph outlines from TTF
```

---

# 14. Этап 7 — адаптивное разбиение кривых

Создать:

```text
src/plotter_processor/curve_flattener.py
```

Реализовать:

```python
class CurveFlatteningPen(BasePen):
    ...
```

Методы:

```python
_moveTo
_lineTo
_curveToOne
_qCurveToOne
_closePath
_endPath
```

## Алгоритм

Использовать рекурсивное деление De Casteljau.

Кривая считается достаточно плоской, если расстояние управляющих точек до хорды не превышает:

```text
flatten_tolerance_mm
```

Рекомендуемое значение:

```text
0.08 мм
```

При превышении допуска делить в `t = 0.5`.

## Защита

- `max_recursion_depth`, например 20;
- `max_points_per_contour`;
- проверка NaN/inf;
- удаление соседних дублей;
- сохранение endpoint при достижении лимита;
- warning в отчёт.

## Минимальная длина

Удалять точки ближе `min_segment_length_mm`, но сохранять последнюю точку.

## Замкнутые контуры

В модели хранить:

```text
closed = true
```

Первую точку не дублировать. Замыкание добавляет SVG/G-code exporter.

## Критерии приёмки

- прямая не получает сотни точек;
- округлая буква выглядит плавно;
- меньший tolerance даёт больше точек;
- больший tolerance даёт меньше точек;
- нет пиксельных ступенек;
- число точек ограничено.

## Тесты

- line;
- quadratic;
- cubic;
- close path;
- open path;
- max depth;
- duplicate removal;
- tolerance comparison.

## Коммит

```text
feat: flatten font curves into smooth plotter paths
```

---

# 15. Этап 8 — построить `paths.json`

Создать:

```text
src/plotter_processor/path_builder.py
```

Для каждого размещённого глифа:

1. получить glyph;
2. применить transform;
3. запустить `CurveFlatteningPen`;
4. получить контуры;
5. создать `PlotterStroke`;
6. записать `glyph_index`, `char`, `contour_index`, `closed`, `points`.

Пропускать контур только если:

- меньше двух уникальных точек;
- длина равна нулю;
- все точки совпадают.

Пропуск записывать как warning.

## Статистика

Добавить:

```text
characters
glyphs
lines
contours
strokes
points
closed_contours
open_contours
draw_distance_mm
travel_distance_mm
estimated_time_minutes
bounding_box_mm
```

Удалить `skeleton_pixels`.

## Порядок

Первый вариант:

- глифы в порядке текста;
- контуры в порядке шрифта.

## Критерии приёмки

- нет DPI;
- нет skeleton metadata;
- точки внутри страницы;
- символы идут по тексту;
- файл читается G-code exporter.

## Коммит

```text
feat: build plotter paths directly from font outlines
```

---

# 16. Этап 9 — оптимизация travel

Создать:

```text
src/plotter_processor/path_optimizer.py
```

Оптимизация не должна менять форму.

Разрешено внутри одного глифа:

- выбирать ближайший следующий контур;
- разворачивать открытый контур;
- для закрытого контура циклически выбирать ближайшую стартовую вершину.

Между глифами сохранять текстовый порядок.

Настройка:

```yaml
vector:
  optimize_travel: true
```

CLI:

```text
--no-optimize-travel
```

## Критерии приёмки

- draw distance не меняется;
- travel distance не увеличивается;
- число штрихов не меняется;
- форма не меняется;
- порядок символов не меняется.

## Коммит

```text
feat: reduce pen-up travel between glyph contours
```

---

# 17. Этап 10 — два SVG-превью

Полностью переделать `svg_exporter.py`.

## 17.1. `font-preview.svg`

Показывает обычный заполненный TTF.

```xml
<svg
  xmlns="http://www.w3.org/2000/svg"
  width="148mm"
  height="210mm"
  viewBox="0 0 148 210">
```

Глифы:

```xml
<path d="..." fill="black" stroke="none" />
```

Использовать точные команды TTF, не flattened points.

## 17.2. `plotter-preview.svg`

Показывает реальные движения ручки:

```xml
<path
  d="M ... L ... Z"
  fill="none"
  stroke="black"
  stroke-width="0.2"
  stroke-linecap="round"
  stroke-linejoin="round"
/>
```

Для каждого path сохранить metadata символа и контура.

## Общие требования

- размеры в mm;
- viewBox в mm;
- UTF-8;
- XML escaping;
- белый фон;
- опциональная рамка страницы.

## Критерии приёмки

- оба SVG валидны;
- открываются браузером и Inkscape;
- exact preview содержит кривые;
- plotter preview содержит линии;
- bounding box совпадает;
- текст не зеркальный и не перевёрнут.

## Тесты

Парсить XML, не сравнивать весь файл строкой.

## Коммит

```text
feat: export exact font and plotter SVG previews
```

---

# 18. Этап 11 — адаптировать G-code exporter

Максимально сохранить `gcode_exporter.py`.

Для каждого штриха:

1. поднять ручку;
2. перейти к первой точке со скоростью travel;
3. опустить ручку;
4. пройти точки со скоростью draw;
5. если `closed`, вернуться к первой точке;
6. поднять ручку.

Скорости брать из `machine.yaml`:

```yaml
feedrate_mm_min:
  draw: 1000
  travel: 3000
  z: 500
```

Сохранить:

- `page_origin_mm`;
- `invert_x`;
- `invert_y`;
- `workspace_mm`;
- `up_z_mm`;
- `down_z_mm`.

## Безопасность Ender 3 без нагрева

G-code не должен содержать:

```text
M104
M109
M140
M190
```

Не должен содержать extrusion `E...`.

Не добавлять `G28` по умолчанию.

Допустимые основные команды:

```text
G21
G90
G0
G1
M400
M84
```

XY и Z форматировать примерно до 3 знаков после запятой. Не выводить одинаковые подряд команды и сегменты нулевой длины.

До записи G-code проверить workspace. При ошибке удалить `output.gcode`.

## Критерии приёмки

- pen-up/down работают;
- feedrates берутся из YAML;
- нет heating;
- нет extrusion;
- нет G28;
- closed contour замыкается;
- workspace validation работает.

## Тесты

- открытый штрих;
- закрытый штрих;
- несколько штрихов;
- origin;
- invert X/Y;
- workspace overflow;
- отсутствие запрещённых команд;
- duplicate points.

## Коммит

```text
refactor: generate safe G-code from vector contours
```

---

# 19. Этап 12 — переписать `pipeline.py`

Новый порядок:

```python
load configs
read document
normalize text
write extracted.txt
load font
validate required glyphs
layout text in millimeters
export font-preview.svg
build flattened strokes
optimize travel
save paths.json
export plotter-preview.svg
validate page and machine bounds
calculate statistics
generate output.gcode
write report.json
```

Удалить импорты:

```python
numpy
page_renderer
skeletonizer
path_tracer
```

Удалить результаты:

```text
page.png
skeleton.png
```

## Новый `report.json`

```json
{
  "status": "ok",
  "pipeline": "ttf-vector",
  "input": "examples/input.txt",
  "font": "assets/my-handwriting.ttf",
  "page": "A5",
  "size": "normal",
  "shaping": "basic-cmap-hmtx",
  "statistics": {
    "characters": 120,
    "glyphs": 103,
    "lines": 8,
    "contours": 185,
    "strokes": 185,
    "points": 3120,
    "closed_contours": 180,
    "open_contours": 5,
    "draw_distance_mm": 2480.2,
    "travel_distance_mm": 810.5,
    "estimated_time_minutes": 2.75
  },
  "warnings": [],
  "outputs": {
    "extracted": "build/extracted.txt",
    "font_preview": "build/font-preview.svg",
    "plotter_preview": "build/plotter-preview.svg",
    "paths": "build/paths.json",
    "gcode": "build/output.gcode"
  }
}
```

## Успешный результат

```text
build/
├── extracted.txt
├── font-preview.svg
├── plotter-preview.svg
├── paths.json
├── output.gcode
└── report.json
```

## Ошибки

Обрабатывать:

- invalid font;
- missing glyph;
- text overflow;
- invalid config;
- page overflow;
- workspace overflow;
- serialization errors.

При ошибке:

- `report.json` существует;
- `output.gcode` отсутствует;
- exit code ненулевой.

## Коммит

```text
refactor: replace raster pipeline with direct TTF vectors
```

---

# 20. Этап 13 — обновить CLI

Основная команда остаётся:

```bash
plotter-processor run INPUT \
  --font FONT \
  --page A5 \
  --size normal \
  --layout-config configs/layout.yaml \
  --machine-config configs/machine.yaml \
  --output-dir build
```

Старые `render` и `trace` удалить либо заменить.

Рекомендуемые debug-команды:

```bash
plotter-processor extract input.docx --output build/extracted.txt
plotter-processor font-info assets/handwriting.ttf
plotter-processor svg build/extracted.txt --font assets/handwriting.ttf --page A5 --size normal --output-dir build
plotter-processor gcode build/paths.json --machine-config configs/machine.yaml --output build/output.gcode
```

`font-info` выводит:

- path;
- family/style;
- unitsPerEm;
- ascent/descent/lineGap;
- glyph count;
- cmap count;
- Cyrillic coverage.

Exit codes:

- `0` — успех;
- `1` — ошибка pipeline;
- `2` — ошибка argparse.

## Коммит

```text
refactor: update CLI for vector font workflow
```

---

# 21. Этап 14 — обновить validator

Удалить:

- Pillow font checks;
- skeleton statistics;
- pixel bounds.

Добавить:

## Проверка TTF

- файл существует;
- TTFont открывается;
- `unitsPerEm > 0`;
- есть `cmap`;
- есть `hmtx`;
- требуемые glyphs присутствуют.

## Проверка geometry

- минимум две уникальные точки;
- finite coordinates;
- length > 0;
- число точек не превышает лимит.

## Проверка page

- размеры положительные;
- margins корректны;
- paths внутри страницы.

## Проверка machine

Сохранить transform и workspace validation.

## Коммит

```text
refactor: validate vector fonts and millimeter paths
```

---

# 22. Этап 15 — удалить legacy

Только после работающего end-to-end pipeline.

```bash
rg "page_renderer|skeletonizer|path_tracer|numpy|skimage|PIL"
```

Удалить или переместить старые файлы. Удалить неиспользуемые зависимости.

Критерии:

- `run` не импортирует legacy;
- установка проходит без `scikit-image`;
- `page.png` и `skeleton.png` не создаются;
- тесты проходят.

## Коммит

```text
chore: remove obsolete raster and skeleton pipeline
```

---

# 23. Этап 16 — тесты

Все тесты работают без сети и принтера.

## Unit tests

Обязательные модули:

```text
font_loader
vector_layout
glyph_outline
curve_flattener
path_builder
path_optimizer
svg_exporter
validator
gcode_exporter
```

## End-to-end TXT

Вход:

```text
Привет, мир!
Ёжик идёт домой.
1234567890
```

Проверить:

- шесть выходных файлов;
- status ok;
- SVG валиден;
- paths не пуст;
- G-code не пуст;
- нет heating.

## End-to-end DOCX

Создать DOCX во временной директории через `python-docx`.

## End-to-end PDF

Создать PDF с текстовым слоем через PyMuPDF.

## Negative cases

- missing `ё`;
- повреждённый TTF;
- page overflow;
- workspace overflow;
- пустой текст.

## Тестовый шрифт

Не использовать системный TTF. Генерировать шрифт через `FontBuilder` в `tests/conftest.py`.

Он должен содержать минимум несколько кириллических букв, цифры, пунктуацию, пробел, quadratic contour, отверстие и пустой glyph.

## Проверка SVG

Парсить XML через `ElementTree`.

## Проверка G-code

Обязательные проверки:

```python
assert "M104" not in gcode
assert "M109" not in gcode
assert "M140" not in gcode
assert "M190" not in gcode
assert "G28" not in gcode
```

Отдельно проверить отсутствие extrusion token `E`.

## Коммит

```text
test: cover direct TTF to G-code pipeline
```

---

# 24. Этап 17 — README

README должен описывать только новый pipeline.

Указать:

- TXT/DOCX/PDF;
- загрузку TTF;
- прямое извлечение контуров;
- два SVG;
- paths;
- G-code.

Удалить описание:

- PNG;
- skeleton;
- threshold;
- `page.png`;
- `skeleton.png`;
- команды `trace`.

Добавить предупреждение:

> Обычный TTF содержит контуры букв. Плоттер проходит по внешним и внутренним контурам. Это не восстановление центральной линии человеческого штриха.

Добавить краткий раздел про получение TTF через `draw-your-font`.

Запуск:

```bash
.venv/bin/python -m plotter_processor run examples/input.txt \
  --font assets/handwriting.ttf \
  --page A5 \
  --size normal \
  --layout-config configs/layout.yaml \
  --machine-config configs/machine.yaml \
  --output-dir build
```

Сохранить раздел безопасности:

- проверить Z;
- проверить origin;
- проверить invert axes;
- dry-run с поднятой ручкой;
- не включать G28;
- начать с A5 и маленького квадрата.

## Коммит

```text
docs: document direct vector TTF workflow
```

---

# 25. Этап 18 — Makefile

Сохранить:

```text
install
test
lint
run
clean
```

Defaults:

```text
FONT=assets/handwriting.ttf
PAGE=A5
SIZE=normal
```

Добавить `demo`, запускающий `examples/input.txt`.

`clean` не должен удалять пользовательские TTF.

## Коммит

```text
chore: update development commands for vector pipeline
```

---

# 26. Пользовательский сценарий

1. Пользователь получает `my-handwriting.ttf`.
2. Кладёт его в `assets/`.
3. Подготавливает TXT/DOCX/PDF.
4. Запускает `plotter-processor run`.
5. Открывает `font-preview.svg`.
6. Открывает `plotter-preview.svg`.
7. Проверяет `report.json`.
8. Проверяет G-code.
9. Делает dry-run с поднятой ручкой.
10. Рисует маленький тест, затем страницу.

---

# 27. Обязательные критерии готовности

## Архитектура

- [ ] `run` не использует PNG.
- [ ] `run` не использует skeleton.
- [ ] `run` не использует pixel graph.
- [ ] контуры берутся напрямую из TTF.
- [ ] layout выполняется в миллиметрах.

## TTF

- [ ] используется fontTools.
- [ ] проверяется cmap.
- [ ] используется hmtx.
- [ ] используется unitsPerEm.
- [ ] используются ascent/descent.
- [ ] composite glyphs поддерживаются.
- [ ] missing glyph даёт понятную ошибку.

## Layout

- [ ] A4 работает.
- [ ] A5 работает.
- [ ] small/normal/large работают.
- [ ] перенос слов работает.
- [ ] overflow обнаруживается.
- [ ] `ё` работает.

## SVG

- [ ] создаётся `font-preview.svg`.
- [ ] создаётся `plotter-preview.svg`.
- [ ] размеры в mm.
- [ ] корректный viewBox.
- [ ] exact preview использует кривые.
- [ ] plotter preview показывает реальные линии.
- [ ] текст не зеркальный.

## Paths

- [ ] создаётся `paths.json`.
- [ ] координаты в mm.
- [ ] нет DPI.
- [ ] нет skeleton metadata.
- [ ] closed contours корректны.
- [ ] нет NaN/inf.
- [ ] нет zero-length segments.

## G-code

- [ ] создаётся `output.gcode`.
- [ ] pen-up/down работают.
- [ ] feedrates из YAML.
- [ ] workspace validation работает.
- [ ] нет M104/M109/M140/M190.
- [ ] нет extrusion E.
- [ ] нет G28 по умолчанию.

## Ошибки

- [ ] при ошибке есть `report.json`.
- [ ] при ошибке нет `output.gcode`.
- [ ] invalid TTF обрабатывается.
- [ ] missing glyph обрабатывается.
- [ ] page overflow обрабатывается.
- [ ] workspace overflow обрабатывается.

## Тесты

- [ ] `make test` проходит.
- [ ] `make lint` проходит.
- [ ] тесты не требуют сети.
- [ ] тесты не требуют принтера.
- [ ] тесты не требуют системного TTF.
- [ ] есть TXT/DOCX/PDF end-to-end.

---

# 28. Запрещённые решения

Codex не должен:

1. Рендерить TTF в PNG для получения траекторий.
2. Применять threshold или skeletonize.
3. Обходить пиксельный граф.
4. Конвертировать SVG в PNG и обратно.
5. Парсить SVG regex-ами для геометрии.
6. Делать FontForge/Inkscape обязательной зависимостью.
7. Создавать веб-интерфейс или базу данных.
8. Подключать OCR.
9. Генерировать TTF из фото внутри Python pipeline.
10. Восстанавливать человеческую траекторию руки.
11. Включать нагрев.
12. Включать G28 по умолчанию.
13. Отключать workspace validation.
14. Молча пропускать missing glyph.
15. Молча обрезать текст.
16. Оставлять частично записанный G-code.

---

# 29. Рекомендуемые коммиты

```text
refactor: add vector pipeline configuration
refactor: introduce vector path data models
feat: load and validate TTF fonts with fontTools
feat: support UTF-8 text input
feat: add millimeter-based text layout
feat: extract exact glyph outlines from TTF
feat: flatten font curves into smooth plotter paths
feat: build plotter paths directly from font outlines
feat: reduce pen-up travel between glyph contours
feat: export exact font and plotter SVG previews
refactor: generate safe G-code from vector contours
refactor: replace raster pipeline with direct TTF vectors
refactor: update CLI for vector font workflow
refactor: validate vector fonts and millimeter paths
chore: remove obsolete raster and skeleton pipeline
test: cover direct TTF to G-code pipeline
docs: document direct vector TTF workflow
chore: update development commands for vector pipeline
```

---

# 30. Финальная ручная проверка

```bash
rm -rf build
make test
make lint
```

```bash
.venv/bin/python -m plotter_processor font-info assets/handwriting.ttf
```

```bash
.venv/bin/python -m plotter_processor run \
  examples/input.txt \
  --font assets/handwriting.ttf \
  --page A5 \
  --size normal \
  --layout-config configs/layout.yaml \
  --machine-config configs/machine.yaml \
  --output-dir build
```

Ожидаемые файлы:

```text
build/extracted.txt
build/font-preview.svg
build/output.gcode
build/paths.json
build/plotter-preview.svg
build/report.json
```

Проверить отсутствие старых файлов:

```bash
test ! -e build/page.png
test ! -e build/skeleton.png
```

Проверить запрещённые команды:

```bash
! grep -E 'M104|M109|M140|M190|G28' build/output.gcode
! grep -E '(^|[[:space:]])E-?[0-9]' build/output.gcode
```

Проверить JSON:

```bash
python -m json.tool build/paths.json >/dev/null
python -m json.tool build/report.json >/dev/null
```

Проверить SVG:

```bash
python - <<'PY'
from pathlib import Path
from xml.etree import ElementTree

for name in ("font-preview.svg", "plotter-preview.svg"):
    ElementTree.parse(Path("build") / name)
    print(name, "OK")
PY
```

---

# 31. Формат финального отчёта Codex

После реализации предоставить:

````markdown
## Выполнено

- ...

## Изменённые файлы

- `path/to/file.py` — описание

## Удалённые или перемещённые legacy-файлы

- ...

## Новые зависимости

- `fonttools` — назначение

## Команды проверки

```bash
make test
make lint
```

## Результаты

- tests: X passed
- lint: passed
- end-to-end: passed

## Создаваемые артефакты

- `build/font-preview.svg`
- `build/plotter-preview.svg`
- `build/paths.json`
- `build/output.gcode`
- `build/report.json`

## Известные ограничения

- TTF рисуется по контурам, а не по центральной линии.
- Полный OpenType shaping/GPOS пока не реализован.
- OCR не поддерживается.
- Один запуск формирует одну страницу.
````

Не считать работу завершённой, если тесты не проходят, SVG не открывается, pipeline использует skeleton или G-code содержит нагрев.

---

# 32. Технические ориентиры

- Текущий проект: `https://github.com/BMSTU-LYGO/plotter-proc`
- Создание TTF из фото: `https://github.com/danilo-znamerovszkij/draw-your-font`
- `TTFont`: `https://fonttools.readthedocs.io/en/latest/ttLib/`
- fontTools pens: `https://fonttools.readthedocs.io/en/latest/pens/`
- `SVGPathPen`: `https://fonttools.readthedocs.io/en/latest/pens/svgPathPen.html`

---

# 33. Краткое определение готового результата

Готовый проект принимает текст и пользовательский TTF, напрямую извлекает плавные контуры TTF, размещает их на A4/A5 в миллиметрах, создаёт точное SVG-превью шрифта, отдельное превью реальных движений плоттера, сохраняет `paths.json` и создаёт безопасный G-code для Ender 3 без нагрева, экструзии и автоматического homing.

Главная архитектурная проверка:

```text
В проекте больше нет TTF → PNG → skeleton.
```

Итоговый pipeline:

```text
text + TTF → smooth SVG contours → paths.json → safe G-code
```
