# UPD_Plotter_3

## Подробный план для Codex: режим TTF → центральные линии → G-code

---

## 0. Контекст задачи

Основной репозиторий:

```text
https://github.com/BMSTU-LYGO/plotter-proc
```

Ветка, которую нужно взять за основу:

```text
master
```

Внешний генератор рукописного TTF:

```text
https://github.com/danilo-znamerovszkij/draw-your-font
```

### Главное архитектурное условие

`draw-your-font` не входит в `plotter-proc` и не изменяется.

Он используется как отдельный готовый инструмент:

```text
фотография почерка
        ↓
draw-your-font без изменений
        ↓
handwriting.ttf
```

Вся новая логика добавляется только в `plotter-proc`:

```text
handwriting.ttf
        ↓
рендер каждого уникального глифа в высоком разрешении
        ↓
получение центральной линии
        ↓
сглаживание и очистка
        ↓
кеш однолинейных глифов
        ↓
layout текста
        ↓
paths.json
        ↓
plotter-preview.svg
        ↓
G-code
```

Пользователь должен продолжать работать с обычным `.ttf`.

Никаких дополнительных файлов от `draw-your-font` требовать нельзя.

---

# 1. Текущее состояние проекта

На момент составления этого плана проект уже содержит векторный pipeline:

```text
TXT / DOCX / PDF + TTF
        ↓
Unicode NFC
        ↓
layout в миллиметрах
        ↓
контуры TTF через fontTools
        ↓
flatten кривых
        ↓
paths.json v2
        ↓
plotter-preview.svg
        ↓
безопасный G-code
```

Текущие основные файлы:

```text
src/plotter_processor/
├── __init__.py
├── __main__.py
├── cli.py
├── config.py
├── curve_flattener.py
├── document_reader.py
├── font_loader.py
├── gcode_exporter.py
├── glyph_outline.py
├── models.py
├── path_builder.py
├── path_optimizer.py
├── pipeline.py
├── svg_exporter.py
├── text_normalizer.py
├── validator.py
└── vector_layout.py
```

Текущий pipeline строит траектории из замкнутых TTF-контуров:

```python
font.glyph_set[positioned.glyph_name].draw(...)
```

Поэтому плоттер проходит по обеим границам толстого штриха.

Это нормальное поведение обычного TTF, а не ошибка `fontTools`.

---

# 2. Главная цель обновления

Добавить второй режим обработки шрифта:

```text
outline
centerline
```

## Режим `outline`

Сохраняет текущее поведение:

```text
TTF outline → flatten → paths
```

Особенности:

- максимально точно повторяет заполненный TTF;
- создаёт двойную обводку толстых штрихов;
- остаётся для обратной совместимости;
- используется для диагностики и сравнения.

## Режим `centerline`

Новый режим:

```text
TTF glyph
    ↓
чистый high-resolution raster
    ↓
binary mask
    ↓
centerline skeleton
    ↓
graph
    ↓
strokes
    ↓
smooth polylines
    ↓
paths
```

Особенности:

- каждый толстый штрих превращается в одну центральную линию;
- `draw-your-font` остаётся без изменений;
- фотография повторно не обрабатывается;
- OCR не используется;
- распознавание символов не используется;
- символ определяется через `cmap` самого TTF;
- результат кешируется по хешу TTF и настройкам алгоритма.

---

# 3. Целевой пользовательский сценарий

## 3.1. Создание TTF

Пользователь отдельно запускает оригинальный `draw-your-font`.

Пример:

```bash
npx draw-your-font make page-1.jpg page-2.jpg \
  --name "My Hand"
```

Результат:

```text
MyHand.ttf
```

`plotter-proc` не должен запускать Node.js и не должен зависеть от исходных фотографий.

## 3.2. Компиляция центральных линий

Новая отдельная команда:

```bash
plotter-processor compile-centerline-font assets/MyHand.ttf \
  --output build/fonts/MyHand.centerline.json \
  --preview build/fonts/MyHand.centerline.svg \
  --debug-dir build/fonts/MyHand-debug
```

## 3.3. Полный запуск

```bash
plotter-processor run examples/input.txt \
  --font assets/MyHand.ttf \
  --font-mode centerline \
  --page A5 \
  --size normal \
  --layout-config configs/layout.yaml \
  --machine-config configs/machine.yaml \
  --output-dir build/job
```

При отсутствии готового кеша команда должна скомпилировать необходимые глифы автоматически.

## 3.4. Старый режим

```bash
plotter-processor run examples/input.txt \
  --font assets/Pacifico-Regular.ttf \
  --font-mode outline \
  --page A5 \
  --size normal \
  --output-dir build/outline-job
```

## 3.5. Режим по умолчанию

Для обратной совместимости на первом этапе:

```text
--font-mode outline
```

После стабилизации centerline можно отдельно решить, менять ли default.

В рамках этого задания default не менять.

---

# 4. Желаемые артефакты

Для запуска в режиме `centerline`:

```text
build/job/
├── extracted.txt
├── font-preview.svg
├── centerline-font-preview.svg
├── plotter-preview.svg
├── paths.json
├── output.gcode
└── report.json
```

Назначение:

| Файл | Содержание |
|---|---|
| `extracted.txt` | нормализованный текст |
| `font-preview.svg` | исходный заполненный TTF |
| `centerline-font-preview.svg` | центральные линии уникальных глифов |
| `plotter-preview.svg` | реальные траектории на странице |
| `paths.json` | траектории в page-mm-top-left |
| `output.gcode` | безопасный G-code |
| `report.json` | режим, кеш, статистика и предупреждения |

Глобальный кеш:

```text
build/font-cache/
└── <cache-key>/
    ├── manifest.json
    ├── centerlines.json
    ├── preview.svg
    └── debug/
```

---

# 5. Ограничения задачи

В MVP не делать:

1. OCR.
2. Обработку исходных фотографий.
3. Изменение `draw-your-font`.
4. Восстановление реального порядка движений руки.
5. Определение давления ручки.
6. Полный OpenType shaping.
7. Нейросетевое восстановление штрихов.
8. Ручной редактор глифов.
9. Скелетизацию всей страницы.
10. Растеризацию страницы при 200 DPI.
11. Автоматическое объединение соседних букв в одно движение.
12. Изменение безопасной логики G-code.
13. Команды нагрева.
14. Extrusion.
15. `G28` по умолчанию.

---

# 6. Почему нельзя скелетизировать целую страницу

Запрещённый pipeline:

```text
A5 page
    ↓
PNG 200 DPI
    ↓
skeleton
```

Он приводит к:

- пиксельным ступенькам;
- тысячам лишних точек;
- плохому качеству маленьких букв;
- зависимости от размера страницы;
- повторной обработке одинаковых символов;
- разным результатам для одного глифа;
- тяжёлому кешированию.

Правильный pipeline:

```text
один уникальный glyph
    ↓
2048 px на em
    ↓
centerline
    ↓
font units
    ↓
кеш
```

После этого один и тот же глиф масштабируется и размещается на странице векторно.

---

# 7. Новая структура модулей

Добавить пакет:

```text
src/plotter_processor/centerline_font/
├── __init__.py
├── models.py
├── config.py
├── glyph_renderer.py
├── mask_processor.py
├── skeletonizer.py
├── skeleton_graph.py
├── stroke_extractor.py
├── junction_pairing.py
├── stroke_smoother.py
├── quality.py
├── cache.py
├── compiler.py
├── preview.py
└── serializer.py
```

Добавить интеграционные файлы:

```text
src/plotter_processor/
├── centerline_path_builder.py
├── cli.py
├── models.py
├── pipeline.py
├── validator.py
└── svg_exporter.py
```

Добавить тесты:

```text
tests/
├── fixtures/
│   ├── centerline/
│   └── fonts/
├── test_centerline_glyph_renderer.py
├── test_centerline_mask_processor.py
├── test_centerline_skeletonizer.py
├── test_centerline_skeleton_graph.py
├── test_centerline_stroke_extractor.py
├── test_centerline_stroke_smoother.py
├── test_centerline_quality.py
├── test_centerline_cache.py
├── test_centerline_compiler.py
├── test_centerline_path_builder.py
├── test_pipeline_centerline.py
└── test_cli_centerline.py
```

---

# 8. Этап 0 — зафиксировать baseline

## Действия

Создать новую ветку:

```bash
git checkout master
git pull
git checkout -b upd/ttf-centerline-pipeline
```

Установить проект:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Запустить:

```bash
make test
make lint
```

Выполнить текущий demo с обычным TTF:

```bash
.venv/bin/python -m plotter_processor run examples/input.txt \
  --font assets/handwriting.ttf \
  --page A5 \
  --size normal \
  --layout-config configs/layout.yaml \
  --machine-config configs/machine.yaml \
  --output-dir build/baseline
```

## Зафиксировать

- текущее количество тестов;
- `paths.json`;
- `font-preview.svg`;
- `plotter-preview.svg`;
- `output.gcode`;
- `report.json`;
- число contours;
- число points;
- draw distance;
- travel distance.

## Желаемый результат

Текущий `master` полностью воспроизводим до начала изменений.

## Коммит

```text
chore: capture current outline pipeline baseline
```

---

# 9. Этап 1 — добавить зависимости

Текущие runtime-зависимости включают:

```text
PyMuPDF
python-docx
PyYAML
fonttools
```

Для centerline pipeline добавить:

```toml
"Pillow>=10.0",
"numpy>=2.0",
"scipy>=1.13",
"scikit-image>=0.24",
```

Не добавлять `opencv-python`, если он не нужен для конкретной функции.

Не добавлять `networkx`: граф скелета достаточно мал и должен быть реализован через простые структуры Python.

## Проверки

```bash
.venv/bin/python -m pip install -e ".[dev]"
make test
make lint
```

## Желаемый результат

Проект устанавливается на Python 3.11+ без системного OpenCV.

## Коммит

```text
build: add centerline image processing dependencies
```

---

# 10. Этап 2 — добавить конфигурацию centerline

Расширить:

```text
configs/layout.yaml
```

Добавить отдельную секцию:

```yaml
centerline:
  algorithm_version: 1

  render:
    em_resolution_px: 2048
    padding_px: 128
    threshold: 160
    closing_radius_px: 1

  skeleton:
    method: medial_axis
    min_branch_width_factor: 1.5
    max_junction_cluster_px: 64

  strokes:
    tangent_sample_px: 10
    junction_max_angle_deg: 35.0
    resample_step_px: 2.0
    simplify_tolerance_px: 1.0
    spline_smoothing_factor: 0.04
    output_step_px: 3.0
    max_points_per_stroke: 1000

  quality:
    min_mask_coverage: 0.82
    max_reconstruction_extra: 0.25
    max_endpoint_factor: 8.0
    fail_on_low_quality: false

  cache:
    enabled: true
    directory: build/font-cache

  debug:
    enabled: false
```

## Правила валидации

- `em_resolution_px >= 512`;
- `padding_px >= 16`;
- threshold от 1 до 254;
- radii неотрицательны;
- angle от 0 до 90;
- шаги положительны;
- smoothing factor неотрицателен;
- coverage от 0 до 1;
- extra от 0 до 1;
- `max_points_per_stroke >= 2`.

## Желаемый результат

Все параметры находятся в одном конфиге и попадают в cache key.

## Коммит

```text
feat: add validated centerline configuration
```

---

# 11. Этап 3 — определить внутренние модели

Создать:

```text
centerline_font/models.py
```

Минимальные модели:

```python
@dataclass(frozen=True, slots=True)
class RasterGlyph:
    char: str
    codepoint: int
    glyph_name: str
    width: int
    height: int
    baseline_x_px: float
    baseline_y_px: float
    pixels_per_font_unit: float
    advance_font_units: int
    grayscale: np.ndarray


@dataclass(frozen=True, slots=True)
class SkeletonNode:
    id: int
    kind: str
    x: float
    y: float
    pixels: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class SkeletonEdge:
    id: int
    start_node_id: int
    end_node_id: int
    pixels: tuple[tuple[int, int], ...]
    closed: bool


@dataclass(frozen=True, slots=True)
class CenterlineStroke:
    id: int
    points: tuple[Point, ...]
    closed: bool


@dataclass(frozen=True, slots=True)
class CenterlineGlyph:
    char: str
    codepoint: int
    glyph_name: str
    advance_font_units: int
    strokes: tuple[CenterlineStroke, ...]
    warnings: tuple[str, ...]
    quality: dict[str, float | int | bool]


@dataclass(slots=True)
class CompiledCenterlineFont:
    font_path: Path
    font_sha256: str
    units_per_em: int
    ascent: int
    descent: int
    line_gap: int
    glyphs: dict[str, CenterlineGlyph]
    warnings: list[str]
```

## Требования

- не хранить абсолютные координаты страницы;
- strokes хранить в font units;
- ось X вправо;
- ось Y вверх;
- baseline равен 0;
- координаты конечны;
- результат детерминирован.

## Коммит

```text
feat: define centerline font domain models
```

---

# 12. Этап 4 — высококачественный рендер одного глифа

Создать:

```text
centerline_font/glyph_renderer.py
```

## Цель

Получить чистую grayscale-маску конкретного Unicode-глифа из TTF.

Не рендерить всю строку и всю страницу.

## API

```python
def render_glyph(
    font_path: str | Path,
    char: str,
    *,
    units_per_em: int,
    em_resolution_px: int,
    padding_px: int,
) -> RasterGlyph:
    ...
```

## Требования

1. Использовать `Pillow.ImageFont.truetype`.
2. Рендерить с baseline anchor.
3. Использовать белый фон и чёрный glyph.
4. Не обрезать ascender, descender и marks.
5. Размер canvas рассчитывать из font metrics, а не из bbox одного символа.
6. Сохранять связь pixel coordinates ↔ font units.
7. Получать advance из существующего `LoadedFont`, а не из Pillow.
8. Не использовать hinting-зависимые маленькие размеры.
9. Использовать одинаковый canvas scale для всех glyphs одного font.
10. Не применять threshold внутри renderer.

## Рекомендуемая система координат

```text
pixels_per_font_unit = em_resolution_px / units_per_em
```

Canvas:

```text
width = max(
    advance_px + 2 * padding_px,
    glyph_bbox_width_px + 2 * padding_px,
)
```

Вертикальное положение:

```text
baseline_y_px = padding_px + ascent * pixels_per_font_unit
```

Преобразование обратно:

```python
font_x = (pixel_x - origin_x_px) / pixels_per_font_unit
font_y = (baseline_y_px - pixel_y) / pixels_per_font_unit
```

## Отдельная команда диагностики

Временно добавить internal helper:

```bash
python -m plotter_processor.centerline_font.glyph_renderer \
  assets/handwriting.ttf \
  --chars "АБЖОФЩёёй0!"
  --output-dir build/render-debug
```

## Желаемый результат

Для всех тестовых глифов:

- чистый белый фон;
- чёрный заполненный glyph;
- одинаковая шкала;
- корректная baseline;
- сохранены точки `ё`, `й`, `.`, `!`;
- ничего не обрезано.

## Коммит

```text
feat: render individual TTF glyphs at stable em resolution
```

---

# 13. Этап 5 — получить бинарную маску

Создать:

```text
centerline_font/mask_processor.py
```

## API

```python
def build_ink_mask(
    raster: RasterGlyph,
    *,
    threshold: int,
    closing_radius_px: int,
) -> np.ndarray:
    ...
```

## Pipeline

```text
grayscale
    ↓
threshold
    ↓
небольшой binary closing
    ↓
connected components
```

Так как raster создан программно, не использовать:

- Sauvola;
- удаление теней;
- коррекцию перспективы;
- OCR;
- сильную morphology.

## Правила

```python
mask = raster.grayscale < threshold
```

Допускается:

```python
binary_closing(mask, disk(1))
```

Не выполнять глобальный `remove_small_objects`.

Причина: маленький компонент может быть:

- точкой над `ё`;
- знаком над `й`;
- точкой;
- двоеточием;
- частью `!`.

## Проверки

- mask boolean;
- mask не пуст;
- mask не касается края canvas;
- connected component count сохраняется в diagnostics.

## Желаемый результат

Чистая бинарная маска без потери маленьких компонентов.

## Коммит

```text
feat: build clean glyph masks without dropping marks
```

---

# 14. Этап 6 — proof of concept до интеграции

До создания полноценного pipeline необходимо пройти отдельный quality gate.

Использовать тестовый набор:

```text
А Б В Д Ж Й К М О Р Ф Х Ц Ч Ш Щ
а б в д ж й к м о р ф х ц ч ш щ
ё 0 8 . ! :
```

Для каждого символа сохранить:

```text
build/centerline-poc/<codepoint>/
├── 01-raster.png
├── 02-mask.png
├── 03-skeleton.png
├── 04-graph.svg
├── 05-strokes.svg
└── 06-overlay.png
```

## Критерии прохождения gate

- glyph не обрезан;
- mask совпадает с TTF;
- точки не пропали;
- у `О`, `о`, `0`, `8` есть замкнутые центральные линии;
- у `Ж`, `Ф`, `Щ` нет случайных длинных диагоналей;
- нет двойной обводки;
- результат детерминирован;
- повторный запуск даёт byte-identical JSON.

Не переходить к интеграции с `pipeline.py`, пока gate не пройден.

## Коммит

```text
test: add centerline proof-of-concept quality fixtures
```

---

# 15. Этап 7 — построить skeleton

Создать:

```text
centerline_font/skeletonizer.py
```

## API

```python
@dataclass(frozen=True, slots=True)
class SkeletonResult:
    mask: np.ndarray
    distance: np.ndarray
    component_labels: np.ndarray


def build_skeleton(mask: np.ndarray, *, method: str) -> SkeletonResult:
    ...
```

## Основной метод

Начать с:

```python
skimage.morphology.medial_axis(
    mask,
    return_distance=True,
    rng=0,
)
```

Преимущества:

- возвращает центральную ось;
- возвращает distance map;
- distance map даёт локальную толщину;
- фиксированный `rng=0` обеспечивает детерминированность.

## Fallback

Допускается конфигурационный метод:

```text
skeletonize
```

Он нужен только для сравнения качества в тестах.

Default:

```text
medial_axis
```

## Требования

- обрабатывать каждый connected component отдельно;
- не соединять компоненты;
- сохранять loops;
- сохранять точки;
- не менять исходную mask;
- не использовать случайность без фиксированного seed.

## Желаемый результат

Толстый TTF-штрих превращается в центральный однопиксельный skeleton.

## Коммит

```text
feat: derive deterministic medial axes for glyph masks
```

---

# 16. Этап 8 — очистить короткие spur-ветви

Не удалять ветви по одному глобальному числу пикселей.

Использовать локальную толщину из distance map.

Создать функцию:

```python
def prune_short_spurs(
    skeleton: np.ndarray,
    distance: np.ndarray,
    *,
    min_branch_width_factor: float,
) -> np.ndarray:
    ...
```

## Правило удаления

Удалять ветвь только если:

1. она начинается endpoint;
2. заканчивается junction;
3. её длина меньше:

```text
median_local_width * min_branch_width_factor
```

где:

```text
local_width = 2 * distance
```

4. ветвь не является отдельным component;
5. удаление не уничтожает весь component;
6. удаление не разрывает основной путь.

## Никогда не удалять автоматически

- isolated component;
- loop;
- точки над буквами;
- пунктуацию;
- component, состоящий из нескольких пикселей без junction.

## Желаемый результат

Удаляются только очевидные маленькие усики, а настоящие части глифа сохраняются.

## Коммит

```text
feat: prune centerline spurs using local stroke width
```

---

# 17. Этап 9 — построить граф skeleton

Создать:

```text
centerline_font/skeleton_graph.py
```

## Классификация пикселей по 8-связности

```text
0 соседей  → isolated
1 сосед    → endpoint
2 соседа   → regular
3+ соседей → junction pixel
```

## Junction cluster

Несколько соседних junction pixels объединять в один логический node.

Выбирать medoid:

```text
реальный пиксель cluster, ближайший к centroid
```

Не создавать внутренние рёбра внутри junction cluster.

## Graph model

```python
nodes: list[SkeletonNode]
edges: list[SkeletonEdge]
```

Каждый edge:

- соединяет nodes;
- содержит последовательные соседние pixels;
- не содержит backtracking;
- не повторяет другой edge;
- может быть closed.

## Loops

Если component не имеет endpoint и junction:

1. выбрать anchor с минимальным `(y, x)`;
2. пройти loop один раз;
3. создать `closed=True`;
4. не дублировать стартовую точку в конце.

## Isolated components

Если component слишком мал для обычного edge:

- не удалять;
- пометить как `dot`;
- преобразовать позже в micro-stroke.

## Инвариант покрытия

Каждый skeleton pixel должен принадлежать:

- node cluster;
- либо одному edge.

Каждая связь соседних regular pixels должна использоваться один раз.

## Валидация

```python
def validate_graph_coverage(
    skeleton: np.ndarray,
    nodes: list[SkeletonNode],
    edges: list[SkeletonEdge],
) -> None:
    ...
```

## Желаемый результат

Получен корректный граф без повторного обхода одних и тех же участков.

## Коммит

```text
feat: convert glyph skeletons into validated graphs
```

---

# 18. Этап 10 — извлечь raw strokes

Создать:

```text
centerline_font/stroke_extractor.py
```

## Базовое правило MVP

```text
один graph edge = один raw stroke
```

Это безопаснее, чем DFS с возвратами.

Нельзя добавлять пиксели возвратного пути, чтобы вернуться к junction.

Каждый участок должен рисоваться максимум один раз.

## Направление open stroke

Детерминированный выбор:

1. endpoint с меньшим Y в font coordinates;
2. при равенстве — меньший X;
3. реальный порядок письма не угадывать.

## Closed stroke

- начинать с детерминированного anchor;
- `closed=True`;
- не повторять начальную точку в конце.

## Dot component

Преобразовать в короткий micro-stroke.

Длина должна быть связана с толщиной:

```text
max(2 px, median_component_width * 0.75)
```

Не хранить stroke с одной точкой.

## Результат

```python
list[CenterlineStroke]
```

## Желаемый результат

Центральные линии существуют без двойного прохода и без DFS-backtracking.

## Коммит

```text
feat: extract non-repeating raw centerline strokes
```

---

# 19. Этап 11 — pairing в junction

После базового варианта добавить осторожное объединение edges через junction.

Создать:

```text
centerline_font/junction_pairing.py
```

## Цель

Снизить число обрывков и подъёмов ручки, не создавая ложных линий.

## Метод

Для каждого edge у junction:

1. взять последние `tangent_sample_px` точек;
2. вычислить нормализованную tangent;
3. сравнить все пары;
4. оценить плавность продолжения.

Пример score:

```python
score = dot(tangent_a, -tangent_b)
```

Соединять, если угол не больше:

```text
junction_max_angle_deg
```

## Ограничения

- каждый edge участвует максимум в одной паре на junction;
- pairing должен быть детерминирован;
- при неоднозначном равенстве не соединять;
- T-junction может оставить боковую ветвь отдельной;
- X-junction обычно даёт две пары противоположных линий;
- не соединять edges из разных connected components;
- не добавлять новую геометрию между далеко расположенными точками.

## Quality gate

Сравнить preview до и после pairing для:

```text
Ж К М Ф Х ж к м ф х
```

Если pairing ухудшает хотя бы критические fixture, оставить базовый edge mode default и pairing сделать experimental.

## Желаемый результат

Длинные визуально непрерывные линии не разрезаются без необходимости.

## Коммит

```text
feat: pair centerline edges by tangent continuity
```

---

# 20. Этап 12 — упростить и сгладить линии

Создать:

```text
centerline_font/stroke_smoother.py
```

## Pipeline

```text
raw pixel stroke
    ↓
удаление соседних дублей
    ↓
resampling по длине дуги
    ↓
Ramer–Douglas–Peucker
    ↓
параметрическая B-spline
    ↓
повторный sampling
    ↓
font units
```

## Требования

1. Endpoints open stroke фиксированы.
2. Junction endpoints фиксированы.
3. Closed loop остаётся closed.
4. Не соединять разные strokes.
5. Не использовать random.
6. Не удалять реальные острые углы полностью.
7. Не создавать self-intersection, которой не было.
8. Не выходить далеко за исходную mask.
9. Не обрезать массив до `max_points_per_stroke`.
10. При превышении лимита постепенно увеличивать tolerance и добавлять warning.

## B-spline

Использовать SciPy.

Количество smoothing рассчитывать относительно:

- длины stroke;
- median radius;
- числа точек.

Начальный смысл параметра:

```text
spline_smoothing_factor = 0.04
```

Не hardcode конкретное абсолютное `s`.

## Проверки

- минимум две уникальные точки;
- closed stroke минимум три уникальные точки;
- координаты finite;
- длина > 0;
- максимальный gap не превышает разумный порог;
- endpoints не сместились.

## Желаемый результат

Линии плавные, без пиксельной лесенки, но форма глифа сохраняется.

## Коммит

```text
feat: fit smooth deterministic curves to centerline strokes
```

---

# 21. Этап 13 — преобразовать pixels в font units

Все результаты кеша хранить в font coordinates.

## Формулы

```python
font_x = (pixel_x - origin_x_px) / pixels_per_font_unit
font_y = (baseline_y_px - pixel_y) / pixels_per_font_unit
```

## Требования

- X вправо;
- Y вверх;
- baseline 0;
- advance берётся из `hmtx`;
- `unitsPerEm` берётся из TTF;
- координаты округлять до 0.001 font unit или разумной фиксированной точности;
- один и тот же glyph даёт byte-identical output.

## Проверка alignment

Сделать overlay:

```text
исходный TTF outline
+
centerline в тех же font coordinates
```

Проверить:

- baseline;
- ascenders;
- descenders;
- dots;
- advance;
- side bearings.

## Коммит

```text
feat: normalize compiled centerlines into font coordinates
```

---

# 22. Этап 14 — оценка качества

Создать:

```text
centerline_font/quality.py
```

## Минимальные метрики

### Mask coverage

Насколько расширенная центральная линия покрывает исходную mask.

```text
coverage = reconstructed ∩ original / original
```

### Extra area

Насколько reconstructed line выходит за исходную mask.

```text
extra = reconstructed outside original / reconstructed
```

### Component preservation

Сравнить:

- component count исходной mask;
- component count centerline.

### Endpoint anomaly

Слишком большое количество endpoints относительно сложности глифа.

### BBox drift

Centerline bbox не должен сильно отличаться от ink bbox.

### Long jump

Между соседними точками не должно быть случайного длинного отрезка.

## Поведение

При плохом качестве:

```json
{
  "needs_review": true,
  "warnings": [
    "Centerline mask coverage below threshold",
    "Connected component was lost"
  ]
}
```

По умолчанию:

```text
fail_on_low_quality: false
```

То есть pipeline заканчивает работу, но предупреждает.

При включённом strict mode:

```text
fail_on_low_quality: true
```

низкое качество вызывает ошибку до G-code.

## Желаемый результат

Плохой glyph не проходит в output молча.

## Коммит

```text
feat: score centerline quality and flag weak glyphs
```

---

# 23. Этап 15 — debug export

Создать:

```text
centerline_font/preview.py
```

Для каждого проблемного glyph сохранять:

```text
debug/U+0416-Ж/
├── 01-raster.png
├── 02-mask.png
├── 03-distance.png
├── 04-skeleton.png
├── 05-pruned.png
├── 06-graph.svg
├── 07-raw-strokes.svg
├── 08-smoothed.svg
├── 09-overlay.png
└── report.json
```

## Overlay

- серый: исходный glyph;
- красный: centerline;
- зелёный: endpoints;
- синий: junctions;
- подпись: quality metrics.

## Debug policy

Если `debug.enabled=false`:

- не создавать большие PNG для всех глифов;
- сохранять debug только для `needs_review=true`.

Если `debug.enabled=true`:

- сохранять все стадии для всех compiled glyphs.

## Желаемый результат

Каждую ошибку можно локализовать по конкретному этапу.

## Коммит

```text
feat: export per-glyph centerline diagnostics
```

---

# 24. Этап 16 — формат кеша

Создать:

```text
centerline_font/serializer.py
```

## Формат

```json
{
  "format": "plotter-centerline-font",
  "version": 1,
  "algorithm_version": 1,
  "font": {
    "path": "assets/MyHand.ttf",
    "sha256": "...",
    "units_per_em": 1000,
    "ascent": 800,
    "descent": -200,
    "line_gap": 0
  },
  "settings": {
    "em_resolution_px": 2048,
    "threshold": 160
  },
  "glyphs": {
    "uni0410": {
      "char": "А",
      "codepoint": 1040,
      "advance": 650,
      "strokes": [
        {
          "id": 0,
          "closed": false,
          "points": [
            [44.125, 0.0],
            [52.814, 120.311]
          ]
        }
      ],
      "quality": {
        "needs_review": false,
        "mask_coverage": 0.91
      },
      "warnings": []
    }
  },
  "warnings": []
}
```

## Валидация

- format и version;
- SHA-256;
- unitsPerEm > 0;
- glyph names уникальны;
- codepoint соответствует char;
- advance > 0;
- stroke id уникален;
- минимум две точки;
- closed stroke минимум три;
- finite coordinates;
- нет duplicate соседних points;
- координаты в разумных пределах;
- JSON UTF-8;
- `ensure_ascii=False`.

## Atomic write

Писать:

```text
centerlines.json.tmp
```

Затем atomic rename.

## Желаемый результат

Повреждённый или неполный кеш не может быть принят pipeline.

## Коммит

```text
feat: serialize and validate centerline font caches
```

---

# 25. Этап 17 — cache key

Создать:

```text
centerline_font/cache.py
```

## Cache key включает

```text
SHA-256 bytes TTF
algorithm_version
все centerline settings
Python package version
```

Не включать:

- путь файла;
- дату изменения;
- output directory;
- текст документа;
- страницу A4/A5.

## Логика

```python
def get_or_compile_glyphs(
    font: LoadedFont,
    chars: set[str],
    config: CenterlineConfig,
) -> CompiledCenterlineFont:
    ...
```

### Частичный кеш

Если в кеше уже есть:

```text
А Б В
```

а текст требует:

```text
А Б В Г Д
```

скомпилировать только:

```text
Г Д
```

Затем атомарно обновить кеш.

## Lock

Для MVP достаточно lock-файла:

```text
<cache-key>/.lock
```

Не допускать одновременную запись двумя процессами.

## Желаемый результат

Повторный запуск текста выполняется быстро и не пересчитывает одинаковые glyphs.

## Коммит

```text
feat: cache compiled centerline glyphs by font hash
```

---

# 26. Этап 18 — compiler service

Создать:

```text
centerline_font/compiler.py
```

## API

```python
def compile_centerline_font(
    font: LoadedFont,
    chars: set[str],
    config: CenterlineConfig,
    *,
    debug_dir: Path | None = None,
) -> CompiledCenterlineFont:
    ...
```

Для каждого char:

```text
cmap lookup
    ↓
render
    ↓
mask
    ↓
skeleton
    ↓
prune
    ↓
graph
    ↓
extract
    ↓
pair
    ↓
smooth
    ↓
font units
    ↓
quality
```

## Ошибки должны содержать

- char;
- codepoint;
- glyph name;
- stage;
- исходную exception.

Пример:

```text
Failed to compile centerline for "Ж" (U+0416, uni0416) at skeleton_graph:
graph coverage mismatch
```

## Желаемый результат

Один публичный сервис управляет полной компиляцией глифов.

## Коммит

```text
feat: compile requested TTF glyphs into centerlines
```

---

# 27. Этап 19 — CLI `compile-centerline-font`

Изменить:

```text
src/plotter_processor/cli.py
```

Добавить команду:

```bash
plotter-processor compile-centerline-font FONT
```

Аргументы:

```text
FONT
--chars TEXT
--text-file PATH
--output PATH
--preview PATH
--debug-dir PATH
--layout-config PATH
--force
--strict-quality
```

Правила:

- требуется `--chars` или `--text-file`;
- whitespace игнорируется;
- chars нормализуются NFC;
- `--force` пересчитывает кеш;
- `--strict-quality` включает fail-on-low-quality.

Пример:

```bash
plotter-processor compile-centerline-font assets/MyHand.ttf \
  --chars "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя0123456789.,!?" \
  --output build/MyHand.centerline.json \
  --preview build/MyHand.centerline.svg \
  --debug-dir build/MyHand-debug
```

## Желаемый результат

Centerline compiler можно запускать отдельно до генерации G-code.

## Коммит

```text
feat: add compile-centerline-font CLI command
```

---

# 28. Этап 20 — расширить параметры `run`

Добавить:

```text
--font-mode outline|centerline
--centerline-cache PATH
--force-centerline-rebuild
--strict-centerline-quality
```

Default:

```text
outline
```

## PipelineOptions

Расширить:

```python
@dataclass(slots=True)
class PipelineOptions:
    input_path: Path
    font_path: Path
    font_mode: str
    centerline_cache_path: Path | None
    force_centerline_rebuild: bool
    strict_centerline_quality: bool
    page: str
    size: str
    layout_config_path: Path
    machine_config_path: Path
    output_dir: Path
    optimize_travel: bool = True
```

## Валидация CLI

- unknown mode → error;
- cache не соответствует TTF → пересобрать либо error;
- centerline mode без readable TTF → error;
- outline mode игнорирует centerline options с warning или parser error.

## Коммит

```text
feat: add centerline font mode to run command
```

---

# 29. Этап 21 — построить page paths из кеша

Создать:

```text
src/plotter_processor/centerline_path_builder.py
```

## API

```python
def build_centerline_paths(
    compiled_font: CompiledCenterlineFont,
    glyphs: list[PositionedGlyph],
    page: PageSpec,
) -> PathDocument:
    ...
```

## Преобразование точки

Centerline cache:

```text
font units
X вправо
Y вверх
baseline 0
```

Page:

```text
millimeters
X вправо
Y вниз
```

Формула:

```python
page_x = positioned.x_mm + point.x * positioned.scale_mm_per_font_unit
page_y = positioned.baseline_y_mm - point.y * positioned.scale_mm_per_font_unit
```

## PlotterStroke

```python
PlotterStroke(
    id=len(strokes),
    points=points,
    closed=centerline_stroke.closed,
    glyph_index=positioned.glyph_index,
    char=positioned.char,
    contour_index=centerline_stroke.id,
)
```

## Metadata

```python
metadata={
    "coordinate_system": "page-mm-top-left",
    "pipeline": "ttf-centerline",
    "centerline_format": "plotter-centerline-font",
    "centerline_version": 1,
    "font_sha256": compiled_font.font_sha256,
}
```

## Требования

- не flatten повторно;
- не rasterize страницу;
- не сглаживать повторно в page units;
- удалить только соседние duplicate points;
- сохранить closed;
- проверить границы страницы.

## Желаемый результат

`paths.json v2` содержит однолинейные траектории.

## Коммит

```text
feat: build page paths from cached centerline glyphs
```

---

# 30. Этап 22 — интеграция в pipeline

Изменить:

```text
src/plotter_processor/pipeline.py
```

## Общая часть остаётся

```text
load configs
read document
normalize
page
layout
font validation
```

## Branch `outline`

Оставить текущую логику без изменений:

```text
extract_exact_outlines
build_paths
```

## Branch `centerline`

```text
уникальные chars из layout
    ↓
load or compile centerline cache
    ↓
build_centerline_paths
```

## `font-preview.svg`

Всегда строить через текущие точные TTF outlines.

Он показывает исходный шрифт.

## `centerline-font-preview.svg`

В centerline mode строить таблицу уникальных скомпилированных glyphs.

## `plotter-preview.svg`

Строить через текущий `export_plotter_preview(paths, ...)`.

## Report

Centerline:

```json
{
  "status": "ok",
  "pipeline": "ttf-centerline",
  "font_mode": "centerline",
  "font": "assets/MyHand.ttf",
  "font_sha256": "...",
  "centerline_cache": "...",
  "centerline": {
    "compiled_glyphs": 32,
    "cache_hits": 29,
    "cache_misses": 3,
    "needs_review": 2
  }
}
```

Outline:

```json
{
  "pipeline": "ttf-vector",
  "font_mode": "outline",
  "warnings": [
    "Outline mode follows both boundaries of filled TTF strokes"
  ]
}
```

## Error handling

При любой ошибке до конца pipeline:

- удалить `output.gcode`;
- записать error-report;
- не оставлять partial centerline cache;
- не удалять ранее валидный кеш.

## Коммит

```text
feat: integrate cached centerline glyphs into main pipeline
```

---

# 31. Этап 23 — preview центральных глифов

Добавить функцию:

```python
def export_centerline_font_preview(
    compiled_font: CompiledCenterlineFont,
    glyph_names: list[str],
    output_path: Path,
) -> None:
    ...
```

Preview должен показывать:

- char;
- glyph name;
- baseline;
- advance box;
- centerline;
- `needs_review`;
- число strokes;
- число points.

SVG:

```xml
fill="none"
stroke="black"
stroke-linecap="round"
stroke-linejoin="round"
```

В normal preview не показывать graph nodes.

В debug preview показывать:

- start/end;
- stroke numbers;
- junctions;
- direction arrows.

## Желаемый результат

До печати можно отдельно оценить качество каждого глифа.

## Коммит

```text
feat: export compiled centerline font preview
```

---

# 32. Этап 24 — path optimizer

Текущий optimizer работает внутри `glyph_index` и может:

- менять порядок strokes;
- разворачивать open stroke;
- менять старт closed stroke.

Это подходит для centerline.

Добавить тесты:

1. Open centerline может быть развёрнут.
2. Closed loop сохраняет closed.
3. Geometry не меняется.
4. Stroke не дублируется.
5. Глифы текста не переставляются.
6. Deterministic output.
7. `--no-optimize-travel` сохраняет исходный порядок.

Не добавлять глобальную перестановку символов.

## Коммит

```text
test: validate path optimization for centerline glyphs
```

---

# 33. Этап 25 — validator

Расширить сообщения, не ломая существующие проверки.

Текущий текст:

```text
Font outlines produced no drawable paths
```

Заменить на нейтральный:

```text
Font processing produced no drawable paths
```

Добавить centerline-specific проверки:

- cache hash соответствует TTF;
- glyph существует;
- stroke имеет минимум две unique points;
- closed stroke минимум три;
- point finite;
- page bounds;
- max points;
- no zero length;
- no suspicious jump больше configurable limit;
- metadata pipeline valid.

## Коммит

```text
refactor: validate outline and centerline path documents uniformly
```

---

# 34. Этап 26 — G-code safety regression

`gcode_exporter.py` не переписывать без необходимости.

Обязательные regression checks:

- нет `M104`;
- нет `M109`;
- нет `M140`;
- нет `M190`;
- нет extrusion `E`;
- `G28` отсутствует при `home: false`;
- `G90` при absolute mode;
- `G21` при mm;
- Z up/down работают;
- workspace bounds работают;
- machine axis inversion работает;
- atomic write работает.

Centerline mode должен использовать тот же `PathDocument`, поэтому G-code слой не должен знать о типе шрифта.

## Коммит

```text
test: preserve G-code safety in centerline mode
```

---

# 35. Этап 27 — unit tests

## Renderer

Проверить:

- baseline;
- descender;
- upper marks;
- no clipping;
- deterministic image;
- advance from TTF.

## Mask

Проверить:

- threshold;
- no empty mask;
- points preserved;
- components preserved;
- no global small-object deletion.

## Skeleton

Синтетические фигуры:

```text
thick horizontal line
thick vertical line
diagonal
ring
figure eight
T-junction
X-junction
two dots
loop with tail
```

## Graph

Проверить:

- coverage;
- no repeated regular pixel;
- loops;
- dots;
- junction cluster;
- zero-length edge forbidden.

## Extractor

Проверить:

- no backtracking;
- each edge once;
- closed handling;
- micro-stroke;
- deterministic orientation.

## Smoother

Проверить:

- endpoints fixed;
- closed remains closed;
- no NaN;
- no zero-length;
- point limit;
- deterministic output.

## Cache

Проверить:

- SHA mismatch;
- config mismatch;
- partial compilation;
- atomic write;
- corrupt JSON;
- unsupported version;
- lock.

---

# 36. Этап 28 — integration tests

Использовать TTF fixture, создаваемый самими тестами через `fontTools`.

Fixture должен содержать:

```text
А
Ж
О
Ф
Щ
а
ж
о
ё
й
0
8
.
!
space
```

Не зависеть от системных шрифтов и сети.

## E2E centerline

```bash
plotter-processor run tests/fixtures/input.txt \
  --font tests/fixtures/fonts/centerline-test.ttf \
  --font-mode centerline \
  --page A5 \
  --size normal \
  --output-dir build/test-centerline
```

Проверить:

- status ok;
- pipeline `ttf-centerline`;
- cache создан;
- second run cache hit;
- paths format v2;
- SVG существует;
- G-code существует;
- нет unsafe commands;
- output deterministic;
- centerline strokes меньше outline contours для тестового толстого глифа;
- точки `ё`, `й`, `!` не пропали.

## E2E outline regression

Старый запуск должен остаться успешным и давать прежний формат.

---

# 37. Этап 29 — визуальный regression набор

Добавить:

```text
tests/visual/
├── expected/
├── generated/
└── README.md
```

Текст:

```text
Привет, мир!
Ёжик идёт домой.
АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩ
абвгдеёжзийклмнопрстуфхцчшщ
1234567890
.,!?:
```

Сохранять:

```text
font-preview.svg
centerline-font-preview.svg
plotter-preview.svg
comparison.md
```

## Acceptance

- нет двойной параллельной обводки;
- `О`, `о`, `0` имеют одну центральную петлю;
- `8` сохраняет обе петли;
- `ё` сохраняет две точки;
- `й` сохраняет верхний знак;
- `!` сохраняет точку;
- `Ж`, `Ф`, `Щ` не имеют случайных диагоналей;
- линии не выглядят как пиксельная лестница;
- соседние glyphs не соединяются случайно;
- baseline совпадает с TTF.

---

# 38. Этап 30 — README

Обновить корневой README.

Добавить раздел:

```markdown
## Однолинейный режим

Шрифт можно создать внешним инструментом draw-your-font без изменений.

```bash
npx draw-your-font make page-1.jpg page-2.jpg --name "My Hand"
```

Затем передайте полученный TTF:

```bash
plotter-processor run input.txt \
  --font assets/MyHand.ttf \
  --font-mode centerline \
  --page A5 \
  --size normal \
  --output-dir build
```

При первом запуске глифы компилируются в центральные линии и
сохраняются в кеше. Последующие запуски используют кеш.

Режим `outline` повторяет обе границы обычного TTF.
Режим `centerline` строит приблизительную центральную линию.
```

Обязательно честно указать:

- centerline является автоматическим приближением;
- сложные пересечения могут требовать настройки;
- нужно проверять preview;
- TTF от `draw-your-font` должен визуально выглядеть корректно;
- качество исходного TTF ограничивает качество centerline.

---

# 39. Этап 31 — реальный тест на Ender 3

Перед физическим запуском:

1. Просмотреть `font-preview.svg`.
2. Просмотреть `centerline-font-preview.svg`.
3. Просмотреть `plotter-preview.svg`.
4. Проверить `report.json`.
5. Проверить page origin.
6. Проверить invert X/Y.
7. Выполнить dry-run с ручкой сверху.
8. Использовать A5.
9. Использовать короткий текст.
10. Не включать нагрев.
11. Не включать homing без проверки держателя.

Тест:

```text
Аа Ёё Жж Йй Оо Фф Щщ
0123456789
```

Зафиксировать:

- TTF;
- настройки centerline;
- SVG;
- paths;
- G-code;
- фото результата;
- тип ручки;
- скорость;
- размер em;
- замечания.

---

# 40. Критерии готовности MVP

## Совместимость

- [ ] `draw-your-font` не изменён.
- [ ] На вход нужен только обычный TTF.
- [ ] Старый `outline` режим работает.
- [ ] `paths.json` остаётся version 2.
- [ ] G-code exporter не знает о centerline.

## Centerline

- [ ] Каждый glyph обрабатывается отдельно.
- [ ] Resolution не зависит от страницы.
- [ ] Результат хранится в font units.
- [ ] Нет двойной обводки.
- [ ] Нет DFS-backtracking.
- [ ] Loops поддерживаются.
- [ ] Dots поддерживаются.
- [ ] Junctions обрабатываются детерминированно.
- [ ] Линии сглажены.
- [ ] Quality metrics рассчитаны.
- [ ] Плохие glyphs отмечены.

## Кеш

- [ ] Cache key включает TTF SHA и настройки.
- [ ] Частичный кеш поддерживается.
- [ ] Запись атомарная.
- [ ] Повреждённый кеш отклоняется.
- [ ] Повторный запуск использует cache hit.

## CLI

- [ ] Есть `compile-centerline-font`.
- [ ] Есть `--font-mode centerline`.
- [ ] Есть `--force-centerline-rebuild`.
- [ ] Есть strict quality.
- [ ] Ошибки возвращают exit code 1.

## Артефакты

- [ ] `font-preview.svg`.
- [ ] `centerline-font-preview.svg`.
- [ ] `plotter-preview.svg`.
- [ ] `paths.json`.
- [ ] `output.gcode`.
- [ ] `report.json`.
- [ ] debug по плохим glyphs.

## Безопасность

- [ ] Нет heating.
- [ ] Нет extrusion.
- [ ] Нет `G28` по умолчанию.
- [ ] Bounds проверяются.
- [ ] Ошибка не оставляет G-code.
- [ ] Dry-run описан.

## Тесты

- [ ] `make test`.
- [ ] `make lint`.
- [ ] Тесты без сети.
- [ ] Тесты без системного TTF.
- [ ] Outline regression проходит.
- [ ] Centerline E2E проходит.
- [ ] Output детерминирован.

---

# 41. Порядок коммитов

```text
chore: capture current outline pipeline baseline
build: add centerline image processing dependencies
feat: add validated centerline configuration
feat: define centerline font domain models
feat: render individual TTF glyphs at stable em resolution
feat: build clean glyph masks without dropping marks
test: add centerline proof-of-concept quality fixtures
feat: derive deterministic medial axes for glyph masks
feat: prune centerline spurs using local stroke width
feat: convert glyph skeletons into validated graphs
feat: extract non-repeating raw centerline strokes
feat: pair centerline edges by tangent continuity
feat: fit smooth deterministic curves to centerline strokes
feat: normalize compiled centerlines into font coordinates
feat: score centerline quality and flag weak glyphs
feat: export per-glyph centerline diagnostics
feat: serialize and validate centerline font caches
feat: cache compiled centerline glyphs by font hash
feat: compile requested TTF glyphs into centerlines
feat: add compile-centerline-font CLI command
feat: add centerline font mode to run command
feat: build page paths from cached centerline glyphs
feat: integrate cached centerline glyphs into main pipeline
feat: export compiled centerline font preview
test: validate path optimization for centerline glyphs
refactor: validate outline and centerline path documents uniformly
test: preserve G-code safety in centerline mode
test: cover centerline compiler end to end
docs: document external draw-your-font workflow
```

---

# 42. Финальная проверка

```bash
git checkout upd/ttf-centerline-pipeline

python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"

make test
make lint

rm -rf build/final-centerline

.venv/bin/python -m plotter_processor compile-centerline-font \
  assets/handwriting.ttf \
  --text-file examples/input.txt \
  --output build/final-centerline/font.centerline.json \
  --preview build/final-centerline/font.centerline.svg \
  --debug-dir build/final-centerline/debug

.venv/bin/python -m plotter_processor run examples/input.txt \
  --font assets/handwriting.ttf \
  --font-mode centerline \
  --centerline-cache build/final-centerline/font.centerline.json \
  --page A5 \
  --size normal \
  --layout-config configs/layout.yaml \
  --machine-config configs/machine.yaml \
  --output-dir build/final-centerline/job
```

Проверить:

```text
build/final-centerline/font.centerline.json
build/final-centerline/font.centerline.svg
build/final-centerline/job/extracted.txt
build/final-centerline/job/font-preview.svg
build/final-centerline/job/centerline-font-preview.svg
build/final-centerline/job/plotter-preview.svg
build/final-centerline/job/paths.json
build/final-centerline/job/output.gcode
build/final-centerline/job/report.json
```

---

# 43. Итоговая архитектура

```text
draw-your-font без изменений
        ↓
обычный handwriting.ttf
        ↓
plotter-proc
        ├── outline mode
        │      └── TTF contours → двойная обводка
        │
        └── centerline mode
               ├── glyph raster 2048 px/em
               ├── binary mask
               ├── medial axis
               ├── graph
               ├── non-repeating strokes
               ├── smoothing
               ├── font-unit cache
               └── page paths → G-code
```

Главный принцип:

> Не пытаться изменять формат TTF и не изменять `draw-your-font`. Обычный TTF остаётся источником формы и метрик, а `plotter-proc` самостоятельно компилирует каждый глиф в однолинейное приближение и кеширует результат.

