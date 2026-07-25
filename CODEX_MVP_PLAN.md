# Технический план для Codex: MVP процессора документов для Ender 3

## 0. Роль Codex

Ты реализуешь локальную консольную Python-программу, которая:

1. принимает `.docx` или `.pdf` с текстовым слоем;
2. извлекает только текст;
3. заново раскладывает текст на странице A4 или A5;
4. рендерит текст готовым рукописным TTF-шрифтом в растр;
5. преобразует растр в однопиксельный скелет;
6. превращает скелет в траектории движения ручки;
7. создаёт SVG-превью;
8. создаёт G-code для Ender 3 с прошивкой TH3D и подъёмом ручки по оси Z.

Срок реализации: **1 рабочих дня**.

Работай автономно. Не добавляй веб-интерфейс, базу данных, микросервисы, Docker, OCR, обработку рукописного шаблона или создание TTF. Не расширяй scope без необходимости.

---

# 1. Главная цель MVP

Команда:

```bash
make run INPUT=examples/input.docx PAGE=A4 SIZE=normal
```

должна создать:

```text
build/
├── extracted.txt
├── page.png
├── skeleton.png
├── paths.json
├── preview.svg
├── output.gcode
└── report.json
```

Пользователь вручную:

- кладёт лист в заранее откалиброванное место;
- задаёт координаты начала листа;
- задаёт `pen_up_z` и `pen_down_z`;
- переносит `output.gcode` на принтер;
- запускает печать.

---

# 2. Жёсткие ограничения MVP

## Входит в MVP

- Python 3.11+.
- CLI.
- DOCX.
- PDF с настоящим текстовым слоем.
- Русские строчные и заглавные буквы.
- Цифры.
- Базовая пунктуация.
- Замена `ё` на `е`, `Ё` на `Е`.
- A4 и A5, книжная ориентация.
- Повторная вёрстка документа.
- Три условных размера текста: `small`, `normal`, `large`.
- Одна страница за один запуск.
- SVG-превью.
- G-code.
- Ручная калибровка расположения листа и оси Z.
- Один готовый рукописный TTF-файл, предоставленный пользователем.

## Не входит в MVP

- Создание TTF/OTF.
- Обработка заполненного шаблона почерка.
- OCR.
- Сканированные документы.
- Таблицы.
- Изображения.
- Формулы.
- Колонки.
- Сохранение исходного форматирования.
- Жирный, курсив, заголовки и списки как отдельные стили.
- Многостраничная генерация за один запуск.
- GUI.
- Отправка G-code по USB.
- Автоматический `G28`.
- Случайные ошибки, помарки и вариативность почерка.
- Редактор траекторий.
- Оптимальный математический порядок всех штрихов.

---

# 3. Ключевое архитектурное решение

Для MVP **не создавать собственный шрифт и не хранить вручную траектории каждой буквы**.

Использовать следующий быстрый пайплайн:

```text
DOCX/PDF
  ↓
обычный текст
  ↓
перенос строк
  ↓
рендер готовым рукописным TTF в чёрно-белое изображение
  ↓
бинаризация
  ↓
skeletonize
  ↓
граф пикселей
  ↓
траектории
  ↓
SVG
  ↓
G-code
```

Преимущества:

- поддержка кириллицы определяется готовым TTF;
- соединённость букв определяется выбранным рукописным TTF;
- не требуется вручную описывать десятки символов;
- не требуется делать собственный формат шрифта;
- весь физический пайплайн можно проверить за 1–2 дня.

Ограничения:

- некоторые линии будут проходиться дважды;
- в развилках возможен неестественный порядок движения;
- качество зависит от выбранного TTF;
- буквы соединятся только тогда, когда сам TTF визуально соединяет их;
- точки над буквами и отдельные элементы будут отдельными штрихами;
- это временный источник траекторий, который позже заменяется обработчиком скана.

---

# 4. Технологический стек

Использовать только Python.

## Runtime-зависимости

```text
PyMuPDF
python-docx
Pillow
numpy
scikit-image
PyYAML
svgwrite
```

## Dev-зависимости

```text
pytest
ruff
```

## Не использовать

- Django;
- FastAPI;
- Flask;
- OpenCV в MVP;
- pandas;
- shapely;
- networkx;
- fontTools;
- FontForge;
- внешние G-code-конвертеры;
- Inkscape CLI;
- LibreOffice CLI.

Все необходимые алгоритмы графа реализовать небольшими функциями на стандартных структурах Python.

---

# 5. Требования к рукописному TTF

Codex **не должен скачивать, генерировать или коммитить файл шрифта**.

Пользователь самостоятельно кладёт файл сюда:

```text
assets/handwriting.ttf
```

Добавить в `.gitignore`:

```gitignore
assets/*.ttf
assets/*.otf
```

Добавить проверку при запуске:

- файл существует;
- Pillow может его открыть;
- шрифт содержит кириллицу;
- тестовая строка не рендерится пустой.

Тестовая строка:

```text
АБВГД абвгд 0123456789
```

В README указать, что нужен **тонкий связный рукописный шрифт с поддержкой кириллицы**. Чем толще исходные линии, тем больше ложных ветвей появится после скелетизации.

---

# 6. Структура проекта

Codex должен создать проект с нуля:

```text
plotter-processor/
├── .gitignore
├── Makefile
├── README.md
├── pyproject.toml
├── assets/
│   └── .gitkeep
├── configs/
│   ├── layout.yaml
│   └── machine.yaml
├── examples/
│   └── .gitkeep
├── build/
│   └── .gitkeep
├── src/
│   └── plotter_processor/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── models.py
│       ├── document_reader.py
│       ├── text_normalizer.py
│       ├── page_renderer.py
│       ├── skeletonizer.py
│       ├── path_tracer.py
│       ├── svg_exporter.py
│       ├── gcode_exporter.py
│       ├── validator.py
│       └── pipeline.py
└── tests/
    ├── __init__.py
    ├── test_text_normalizer.py
    ├── test_document_reader.py
    ├── test_page_renderer.py
    ├── test_path_tracer.py
    ├── test_gcode_exporter.py
    └── fixtures/
        └── .gitkeep
```

Не создавать лишние уровни абстракции.

---

# 7. `pyproject.toml`

Создать минимальный проект:

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "plotter-processor"
version = "0.1.0"
description = "DOCX/PDF to pen-plotter G-code processor"
requires-python = ">=3.11"
dependencies = [
    "PyMuPDF>=1.24",
    "python-docx>=1.1",
    "Pillow>=10.4",
    "numpy>=2.0",
    "scikit-image>=0.24",
    "PyYAML>=6.0",
    "svgwrite>=1.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.6",
]

[project.scripts]
plotter-processor = "plotter_processor.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

Версии являются нижними ограничениями. Не фиксировать точные patch-версии без необходимости.

---

# 8. Конфигурация страницы

Файл `configs/layout.yaml`:

```yaml
page: A4
orientation: portrait
dpi: 200

margins_mm:
  left: 10.0
  right: 10.0
  top: 20.0
  bottom: 30.0

sizes:
  small:
    font_px: 28
    line_spacing: 1.30
    paragraph_spacing_lines: 0.50
  normal:
    font_px: 36
    line_spacing: 1.35
    paragraph_spacing_lines: 0.60
  large:
    font_px: 48
    line_spacing: 1.40
    paragraph_spacing_lines: 0.70

render:
  threshold: 180
  remove_small_objects_px: 4
  padding_px: 4
```

Поддерживаемые размеры:

```python
PAGE_SIZES_MM = {
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
}
```

Формула перевода:

```python
pixels = round(mm * dpi / 25.4)
```

Внутри рендерера использовать пиксели. В экспортёрах переводить обратно в миллиметры.

---

# 9. Конфигурация Ender 3

Файл `configs/machine.yaml`:

```yaml
machine:
  name: ender3
  firmware: th3d

page_origin_mm:
  x: 10.0
  y: 10.0

axes:
  invert_x: false
  invert_y: true

pen:
  up_z_mm: 5.0
  down_z_mm: 1.0
  settle_ms: 100

feedrate_mm_min:
  draw: 1000
  travel: 3000
  z: 500

workspace_mm:
  min_x: 0.0
  max_x: 220.0
  min_y: 0.0
  max_y: 220.0

gcode:
  home: false
  absolute_positioning: true
  units_mm: true
  decimals: 3
```

Значения Z и origin считать **примером**, а не готовой безопасной конфигурацией.

Не добавлять `G28`, пока `home: false`.

---

# 10. Модели данных

В `models.py` использовать `dataclasses`.

## DocumentText

```python
@dataclass(slots=True)
class DocumentText:
    paragraphs: list[str]
    source_path: Path
    warnings: list[str]
```

## RenderedPage

```python
@dataclass(slots=True)
class RenderedPage:
    width_px: int
    height_px: int
    dpi: int
    image: np.ndarray
    line_boxes: list[tuple[int, int, int, int]]
    warnings: list[str]
```

## Point

```python
@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float
```

## Stroke

```python
@dataclass(slots=True)
class Stroke:
    points: list[Point]
    source_component: int
```

## PathDocument

```python
@dataclass(slots=True)
class PathDocument:
    page_width_mm: float
    page_height_mm: float
    strokes: list[Stroke]
    warnings: list[str]
```

Все координаты `PathDocument` хранить в миллиметрах относительно левого верхнего угла листа.

---

# 11. CLI

Реализовать через стандартный `argparse`.

## Основная команда

```bash
python -m plotter_processor run input.docx \
  --font assets/handwriting.ttf \
  --page A4 \
  --size normal \
  --layout-config configs/layout.yaml \
  --machine-config configs/machine.yaml \
  --output-dir build
```

## Сокращённый entry point

```bash
plotter-processor run input.pdf \
  --font assets/handwriting.ttf \
  --page A5 \
  --size small
```

## Дополнительные команды

```bash
python -m plotter_processor extract input.docx --output build/extracted.txt
python -m plotter_processor render build/extracted.txt --font assets/handwriting.ttf
python -m plotter_processor trace build/page.png
python -m plotter_processor gcode build/paths.json
python -m plotter_processor calibrate --machine-config configs/machine.yaml
```

Команды `render`, `trace` и `gcode` нужны для отладки. Главная пользовательская команда — `run`.

---

# 12. Этап 1: создание каркаса проекта

Codex должен:

1. создать все каталоги;
2. создать `pyproject.toml`;
3. создать `.gitignore`;
4. создать YAML-конфиги;
5. добавить CLI с командами-заглушками;
6. добавить Makefile;
7. убедиться, что выполняются:

```bash
python -m pip install -e ".[dev]"
python -m plotter_processor --help
pytest
ruff check .
```

После этого переходить к функциональности.

---

# 13. Этап 2: чтение DOCX и PDF

Файл `document_reader.py`.

## DOCX

Использовать:

```python
from docx import Document
```

Алгоритм:

1. открыть документ;
2. пройти `document.paragraphs`;
3. получить `paragraph.text`;
4. сохранить пустые параграфы как пустые строки;
5. не читать таблицы;
6. вернуть `DocumentText`.

## PDF

Использовать:

```python
import pymupdf
```

Алгоритм:

1. открыть PDF;
2. для каждой страницы вызвать:

```python
page.get_text("blocks", sort=True)
```

3. взять только текстовые блоки;
4. отсортировать по координатам, если библиотека не вернула стабильный порядок;
5. объединить блоки через `\n`;
6. страницы объединить через `\n\n`;
7. если извлечено меньше 10 непробельных символов — завершить с понятной ошибкой:

```text
PDF does not contain a usable text layer. OCR is not supported in MVP.
```

## Расширения

Поддерживать только:

```text
.docx
.pdf
```

Для остальных файлов выдавать ошибку.

---

# 14. Этап 3: нормализация текста

Файл `text_normalizer.py`.

Выполнить преобразования:

```text
ё → е
Ё → Е
неразрывный пробел → обычный пробел
табуляция → четыре пробела
CRLF/CR → LF
длинная последовательность пробелов → один пробел
более двух пустых строк → две пустые строки
```

Поддерживаемые символы:

```text
А-Я
а-я
0-9
пробел
перенос строки
. , ! ? : ; - — ( ) [ ] « » " '
№ % + = / \
```

Неподдерживаемые символы:

- заменить пробелом;
- добавить предупреждение в `report.json`;
- не падать.

Нормализация не должна удалять абзацы.

---

# 15. Этап 4: перенос строк и рендер страницы

Файл `page_renderer.py`.

## Основная идея

Не пытаться воспроизводить исходную вёрстку документа. Создать новую страницу.

## Алгоритм

1. загрузить страницу A4/A5;
2. перевести миллиметры в пиксели;
3. создать белое grayscale-изображение;
4. загрузить TTF через `PIL.ImageFont.truetype`;
5. разбить каждый абзац на слова;
6. накапливать слова в строке;
7. измерять кандидатную строку через `font.getbbox()` или `draw.textbbox()`;
8. если строка шире доступной области — завершить предыдущую строку;
9. пустой абзац создаёт дополнительный вертикальный отступ;
10. если следующая строка выходит за нижнее поле — завершить с ошибкой overflow;
11. рендерить текст чёрным на белом фоне;
12. сохранить `build/page.png`.

## Важное решение

Рендерить **строки**, а не отдельные буквы. Это позволяет выбранному рукописному TTF самостоятельно формировать визуальные соединения между буквами.

## Проверка соединённости

После рендера посчитать connected components внутри нескольких слов. Не использовать это как строгий критерий ошибки, но добавить предупреждение, если почти каждая буква стала отдельным компонентом:

```text
Selected font does not appear to be connected. Use a connected handwriting font.
```

## Overflow

В MVP одна страница. При переполнении:

```text
Text does not fit on one page with selected size. Choose a smaller size or split the document.
```

Не уменьшать размер автоматически.

---

# 16. Этап 5: бинаризация и скелетизация

Файл `skeletonizer.py`.

Вход: `page.png` или массив из `RenderedPage`.

Алгоритм:

```python
ink = image < threshold
ink = morphology.remove_small_objects(
    ink,
    min_size=remove_small_objects_px,
)
skeleton = morphology.skeletonize(ink)
```

Сохранить диагностический файл:

```text
build/skeleton.png
```

Белый фон, чёрный скелет.

Добавить проверки:

- скелет не пустой;
- количество пикселей не превышает разумный лимит;
- нет чернил за пределами полей;
- не осталось гигантской компоненты размером почти со страницу.

---

# 17. Этап 6: преобразование скелета в граф

Файл `path_tracer.py`.

Не использовать `networkx`.

## Граф

Каждый пиксель скелета — узел:

```python
Node = tuple[int, int]  # row, col
```

Соседи — восемь соседних пикселей:

```text
(-1, -1), (-1, 0), (-1, 1),
( 0, -1),          ( 0, 1),
( 1, -1), ( 1, 0), ( 1, 1)
```

Чтобы диагональные соединения не давали лишние короткие циклы:

- разрешать диагональное ребро;
- но если два узла уже соединены через ортогональный общий пиксель, диагональное ребро можно не добавлять.

Хранить:

```python
adjacency: dict[Node, set[Node]]
```

---

# 18. Этап 7: компоненты и порядок штрихов

## Connected components

Разделить граф на компоненты DFS/BFS.

Сортировать компоненты:

1. по средней или минимальной `y`;
2. затем по минимальной `x`.

Это примерно соответствует порядку строк слева направо и сверху вниз.

## Построение маршрута компоненты

Нужно физически пройти все рёбра компоненты.

Для MVP использовать DFS-walk:

1. найти узлы нечётной степени;
2. если они есть — начать с самого левого из них;
3. иначе начать с самого левого верхнего узла;
4. выполнить DFS по рёбрам;
5. при возврате добавлять обратное движение в маршрут;
6. одно ребро может быть пройдено дважды;
7. результат — один непрерывный маршрут на компоненту.

Это не оптимально, зато:

- покрывает весь скелет;
- не требует сложной оптимизации;
- минимизирует количество подъёмов ручки;
- реализуется за несколько десятков строк.

## Соседний приоритет

При выборе следующего ребра использовать эвристику:

1. продолжать примерно в текущем направлении;
2. затем выбирать ближайший непосещённый сосед;
3. при равенстве выбирать меньший `x`, затем `y`.

Это уменьшит резкие хаотичные повороты.

---

# 19. Упрощение траекторий

Пиксельные маршруты слишком большие.

Реализовать Ramer–Douglas–Peucker в `path_tracer.py`.

Примерный epsilon:

```yaml
trace:
  simplify_epsilon_px: 0.8
  min_stroke_points: 2
```

Дополнительно:

- удалить последовательные одинаковые точки;
- удалить точки, расстояние между которыми меньше `0.05 мм`;
- не сглаживать петли сложными сплайнами;
- не использовать SciPy.

После упрощения перевести пиксели в миллиметры:

```python
x_mm = x_px * 25.4 / dpi
y_mm = y_px * 25.4 / dpi
```

---

# 20. Формат `paths.json`

Создавать удобный для отладки JSON:

```json
{
  "page": {
    "width_mm": 210.0,
    "height_mm": 297.0,
    "dpi": 200
  },
  "strokes": [
    {
      "component": 0,
      "points": [
        [12.345, 21.100],
        [12.510, 21.240],
        [12.800, 21.500]
      ]
    }
  ],
  "warnings": []
}
```

Округлять координаты до 3–4 знаков только при сериализации. Внутри программы хранить `float`.

---

# 21. SVG-превью

Файл `svg_exporter.py`.

SVG должен:

- иметь физический размер страницы в миллиметрах;
- иметь `viewBox`;
- рисовать поля тонкой пунктирной рамкой;
- рисовать рабочие траектории чёрными линиями;
- не заливать контуры;
- рисовать начало каждого штриха маленькой окружностью;
- опционально рисовать travel movements светлой пунктирной линией;
- сохраняться в `build/preview.svg`.

Пример:

```xml
<polyline
  points="..."
  fill="none"
  stroke="black"
  stroke-width="0.25"
  stroke-linecap="round"
  stroke-linejoin="round"
/>
```

SVG и G-code обязаны использовать один `PathDocument`.

---

# 22. Генерация G-code

Файл `gcode_exporter.py`.

## Начало файла

Если включены соответствующие настройки:

```gcode
; Generated by plotter-processor
G21
G90
G0 Z5.000 F500
```

Не добавлять `G28`, если `home: false`.

## Для каждого штриха

```gcode
G0 Z{pen_up_z} F{z_feedrate}
G0 X{start_x} Y{start_y} F{travel_feedrate}
G1 Z{pen_down_z} F{z_feedrate}
G4 P{settle_ms}
G1 X{x1} Y{y1} F{draw_feedrate}
G1 X{x2} Y{y2}
...
G0 Z{pen_up_z} F{z_feedrate}
```

Не повторять `F` на каждой строке, если скорость не изменилась.

## Конец файла

```gcode
G0 Z{pen_up_z} F{z_feedrate}
; End
```

Не перемещать каретку домой автоматически.

---

# 23. Преобразование координат страницы в координаты принтера

Входные координаты:

```text
(0, 0) = левый верхний угол бумаги
```

Конфигурация принтера задаёт:

```text
page_origin_mm.x
page_origin_mm.y
invert_x
invert_y
```

Базовое преобразование:

```python
machine_x = origin_x + page_x
machine_y = origin_y + page_y
```

При инверсии:

```python
page_x = page_width_mm - page_x
page_y = page_height_mm - page_y
```

После преобразования обязательно проверить workspace.

Если хотя бы одна точка выходит за пределы:

- не создавать `output.gcode`;
- записать ошибку;
- завершить процесс с ненулевым кодом.

---

# 24. Валидатор

Файл `validator.py`.

До генерации G-code проверить:

- документ не пустой;
- TTF существует;
- страница поддерживается;
- размер поддерживается;
- `pen_up_z > pen_down_z`;
- скорости положительные;
- все точки конечные;
- нет `NaN`;
- каждый штрих содержит минимум две точки;
- все машинные координаты находятся внутри workspace;
- число G-code-команд не превышает заданный лимит;
- длина траектории не равна нулю.

Добавить приблизительную статистику:

```text
characters
paragraphs
strokes
points_before_simplification
points_after_simplification
draw_distance_mm
travel_distance_mm
estimated_time_minutes
```

Оценка времени может быть грубой:

```python
time_min = draw_distance / draw_feedrate + travel_distance / travel_feedrate
```

Подъёмы Z можно не учитывать или учитывать приблизительно.

---

# 25. `report.json`

Пример:

```json
{
  "status": "ok",
  "input": "examples/input.docx",
  "page": "A4",
  "size": "normal",
  "statistics": {
    "characters": 812,
    "paragraphs": 5,
    "strokes": 193,
    "points": 8402,
    "draw_distance_mm": 4120.5,
    "travel_distance_mm": 980.2,
    "estimated_time_minutes": 4.45
  },
  "warnings": [
    "Character '©' was replaced with a space"
  ],
  "outputs": {
    "preview": "build/preview.svg",
    "gcode": "build/output.gcode"
  }
}
```

При ошибке:

```json
{
  "status": "error",
  "error": "Text does not fit on one page",
  "warnings": []
}
```

---

# 26. Команда калибровки

Реализовать:

```bash
python -m plotter_processor calibrate \
  --machine-config configs/machine.yaml \
  --page A4 \
  --output build/calibration.gcode
```

Она создаёт:

1. подъём ручки;
2. перемещение к четырём углам полезной области листа;
3. короткий тест опускания в безопасной точке;
4. прямоугольник размером примерно `20 × 20 мм`;
5. подъём ручки.

По умолчанию `calibrate` не должен рисовать полную рамку A4: сначала достаточно малого теста.

Добавить `--full-page-frame` как явный флаг.

---

# 27. Makefile

Создать:

```makefile
PYTHON ?= python3
INPUT ?= examples/input.docx
FONT ?= assets/handwriting.ttf
PAGE ?= A4
SIZE ?= normal
BUILD ?= build

.PHONY: install test lint run extract calibrate clean

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

run:
	$(PYTHON) -m plotter_processor run "$(INPUT)" \
		--font "$(FONT)" \
		--page "$(PAGE)" \
		--size "$(SIZE)" \
		--layout-config configs/layout.yaml \
		--machine-config configs/machine.yaml \
		--output-dir "$(BUILD)"

extract:
	$(PYTHON) -m plotter_processor extract "$(INPUT)" \
		--output "$(BUILD)/extracted.txt"

calibrate:
	$(PYTHON) -m plotter_processor calibrate \
		--machine-config configs/machine.yaml \
		--page "$(PAGE)" \
		--output "$(BUILD)/calibration.gcode"

clean:
	rm -rf "$(BUILD)"
	mkdir -p "$(BUILD)"
	touch "$(BUILD)/.gitkeep"
```

---

# 28. Pipeline orchestration

Файл `pipeline.py`.

Функция:

```python
def run_pipeline(options: PipelineOptions) -> PipelineResult:
    ...
```

Порядок:

1. загрузить конфиги;
2. проверить входы;
3. извлечь документ;
4. сохранить `extracted.txt`;
5. нормализовать текст;
6. рендерить страницу;
7. сохранить `page.png`;
8. skeletonize;
9. сохранить `skeleton.png`;
10. построить траектории;
11. сохранить `paths.json`;
12. валидировать траектории;
13. создать SVG;
14. преобразовать координаты;
15. валидировать workspace;
16. создать G-code;
17. создать `report.json`;
18. вывести краткое резюме в консоль.

При любой ошибке:

- показать понятное сообщение;
- создать `report.json`;
- вернуть exit code `1`;
- не оставлять частично созданный небезопасный G-code.

Писать G-code сначала во временный файл и переименовывать только после успешной валидации.

---

# 29. Тесты

Не пытаться покрыть всё. Покрыть критический путь.

## `test_text_normalizer.py`

Проверить:

- `ё → е`;
- схлопывание пробелов;
- сохранение абзацев;
- предупреждение о неподдерживаемом символе.

## `test_document_reader.py`

Программно создать маленький DOCX во временной директории и проверить извлечение.

PDF-тест:

- создать минимальный PDF через PyMuPDF;
- вставить текст;
- сохранить;
- прочитать;
- проверить наличие текста.

Не хранить бинарные fixtures, если их можно создать в тесте.

## `test_page_renderer.py`

Использовать системный тестовый шрифт только в тестах, если он доступен. Если нет — пропустить integration test через `pytest.skip`.

Проверить:

- размеры страницы;
- поля;
- overflow;
- непустое изображение.

## `test_path_tracer.py`

Создать вручную маленькие бинарные изображения:

- прямая;
- буква `T`;
- петля;
- две компоненты.

Проверить:

- все пиксельные рёбра покрыты;
- траектория не пустая;
- число компонентов корректно;
- упрощение уменьшает число точек.

## `test_gcode_exporter.py`

Проверить:

- присутствуют `G21` и `G90`;
- отсутствует `G28` по умолчанию;
- ручка поднимается перед travel;
- координаты форматируются;
- workspace violation вызывает ошибку.

---

# 30. README

README должен содержать:

1. назначение;
2. ограничения MVP;
3. установку;
4. куда положить TTF;
5. настройку `machine.yaml`;
6. запуск;
7. калибровку;
8. описание outputs;
9. предупреждение о безопасности;
10. troubleshooting.

Обязательное предупреждение:

```text
Never run generated G-code before checking pen-up and pen-down Z values,
page origin, axis inversion and workspace limits. Keep G28 disabled until
the mounted pen has been tested safely.
```

Добавить русский вариант предупреждения.

---

# 31. Порядок реализации на 1–2 дня

## День 1, первая половина

### Блок A — 1–2 часа

- структура проекта;
- `pyproject.toml`;
- конфиги;
- модели;
- CLI;
- Makefile.

### Блок B — 2–3 часа

- DOCX reader;
- PDF reader;
- нормализатор;
- тесты readers/normalizer.

### Блок C — 3–4 часа

- расчёт страницы;
- word wrapping;
- Pillow render;
- overflow;
- `page.png`.

К концу блока должно выполняться:

```text
DOCX/PDF → page.png
```

## День 1, вторая половина

### Блок D — 2–3 часа

- бинаризация;
- skeletonize;
- `skeleton.png`.

### Блок E — 3–5 часов

- граф;
- компоненты;
- DFS walk;
- упрощение;
- `paths.json`.

К концу дня должно выполняться:

```text
DOCX/PDF → page.png → skeleton.png → paths.json
```

## День 2

### Блок F — 1–2 часа

- SVG exporter;
- визуальная проверка.

### Блок G — 2–3 часа

- G-code exporter;
- координатное преобразование;
- workspace validation.

### Блок H — 1–2 часа

- pipeline;
- report;
- временный файл;
- error handling.

### Блок I — 2–3 часа

- тесты;
- калибровочный G-code;
- README;
- прогон на Ender 3;
- настройка скоростей и Z.

---

# 32. Приоритеты при нехватке времени

Если срок заканчивается, приоритеты такие:

1. DOCX.
2. A4.
3. `normal`.
4. Рендер.
5. Скелет.
6. SVG.
7. G-code.
8. PDF.
9. A5.
10. `small`/`large`.
11. Диагностические улучшения.

Нельзя выкидывать:

- SVG;
- workspace validation;
- запрет `G28` по умолчанию;
- проверку Z;
- сохранение промежуточных файлов.

Можно временно выкинуть:

- расчёт времени;
- travel-линии в SVG;
- расширенную статистику;
- команду `trace`;
- A5;
- отдельные CLI-команды кроме `run` и `calibrate`.

---

# 33. Критерии готовности

MVP считается готовым только при выполнении всех обязательных пунктов:

- [ ] Проект устанавливается одной командой.
- [ ] CLI показывает help.
- [ ] DOCX извлекается.
- [ ] PDF с текстовым слоем извлекается.
- [ ] `ё` заменяется на `е`.
- [ ] Русский текст рендерится выбранным TTF.
- [ ] Работает перенос слов.
- [ ] Соблюдаются поля.
- [ ] Overflow выдаёт понятную ошибку.
- [ ] Создаётся `page.png`.
- [ ] Создаётся `skeleton.png`.
- [ ] Создаётся `paths.json`.
- [ ] Создаётся `preview.svg`.
- [ ] Создаётся `output.gcode`.
- [ ] `G28` отсутствует по умолчанию.
- [ ] Все координаты проверяются по workspace.
- [ ] Ручка поднимается перед travel.
- [ ] Ошибка не оставляет небезопасный G-code.
- [ ] `pytest` проходит.
- [ ] `ruff check .` проходит.
- [ ] Одна тестовая фраза физически написана Ender 3.

Тестовая фраза:

```text
Сьешь еще этих мягких французских булок, да выпей чаю. 0123456789
```

После нормализации:

```text
Сьешь еще этих мягких французских булок, да выпей чаю. 0123456789
```

---

# 34. Проверка физического результата

Проводить тесты последовательно:

## Тест 1

Только travel с поднятой ручкой.

Цель:

- проверить origin;
- проверить направления X/Y;
- проверить границы.

## Тест 2

Один квадрат `20 × 20 мм`.

Цель:

- проверить `pen_down_z`;
- проверить давление;
- проверить масштаб.

## Тест 3

Одно слово:

```text
Привет
```

Цель:

- проверить связность;
- проверить скелет;
- проверить скорость.

## Тест 4

Одна строка с цифрами и пунктуацией.

## Тест 5

Небольшой абзац.

Не запускать сразу целую страницу.

---

# 35. Известные дефекты, которые допустимы в MVP

Не считать блокерами:

- некоторые участки обводятся дважды;
- порядок штрихов отличается от человеческого;
- точка над `й` пишется до или после основной буквы;
- в отдельных местах ручка поднимается чаще, чем человек;
- буквы выглядят как выбранный TTF, а не как почерк пользователя;
- сложный PDF извлекается в неправильном порядке;
- длинный документ требует ручного разделения;
- соединение зависит от конкретного TTF.

Считать блокерами:

- выход за workspace;
- неверное опускание/поднятие ручки;
- G-code создаётся после ошибки;
- текст выходит за поля без сообщения;
- часть строк молча исчезает;
- координаты содержат `NaN`;
- неизвестные символы ломают процесс;
- программа автоматически выполняет homing без явного разрешения.

---

# 36. Архитектурный шов для следующей версии

После MVP будет добавлен модуль обработки заполненного скана:

```text
scan_template/
├── template_renderer.py
├── scan_reader.py
├── marker_detector.py
├── cell_cropper.py
├── glyph_skeletonizer.py
└── glyph_library.py
```

Он должен выдавать источник траекторий, совместимый с layout/G-code pipeline.

Для этого сейчас не привязывать `gcode_exporter` к Pillow или TTF. Он должен принимать только `PathDocument`.

Будущая схема:

```text
готовый TTF → raster page → skeleton → PathDocument
```

заменится или дополнится:

```text
скан шаблона → glyph paths
текст → glyph composition → PathDocument
```

Всё после `PathDocument` останется без изменений:

```text
PathDocument → SVG → validation → G-code
```

---

# 37. Что не делать Codex

- Не пытаться реализовать распознавание порядка человеческих штрихов.
- Не пытаться автоматически создавать TTF.
- Не использовать нейросети.
- Не делать OCR.
- Не писать сервер.
- Не создавать микросервисы.
- Не делать плагины.
- Не добавлять базу данных.
- Не делать GUI.
- Не оптимизировать преждевременно.
- Не строить сложную систему классов.
- Не прятать параметры принтера в код.
- Не скачивать шрифты.
- Не отключать safety validation ради успешного теста.
- Не добавлять `G28` без явного конфига.
- Не считать SVG необязательным.
- Не удалять промежуточные файлы после запуска.

---

# 38. Финальный сценарий демонстрации

```bash
git clone <repo>
cd plotter-processor
python3 -m venv .venv
source .venv/bin/activate
make install

# Пользователь кладёт свой TTF:
cp /path/to/handwriting.ttf assets/handwriting.ttf

# Настраивает configs/machine.yaml

make test
make calibrate PAGE=A4

# После безопасной физической калибровки:
make run INPUT=examples/demo.docx PAGE=A4 SIZE=normal
```

Ожидаемый вывод:

```text
Input: examples/demo.docx
Characters: 812
Page: A4 portrait
Strokes: 193
Preview: build/preview.svg
G-code: build/output.gcode
Warnings: 0
Status: OK
```

---

# 39. Финальное требование к Codex

Сначала реализуй полный вертикальный путь на простейшем DOCX:

```text
DOCX → page.png → skeleton.png → paths.json → preview.svg → output.gcode
```

Только после успешного вертикального пути добавляй PDF, A5, дополнительные размеры и улучшения.

В конце:

1. запусти `pytest`;
2. запусти `ruff check .`;
3. выполни demo pipeline;
4. проверь, что `output.gcode` не содержит `G28`;
5. проверь диапазоны всех координат;
6. выведи список созданных файлов;
7. кратко перечисли известные ограничения.
