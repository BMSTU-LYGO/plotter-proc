# UPD_Plotter_4

## План для Codex: исправление центральной линии и одна непрерывная траектория на букву

## 0. Основа

Репозиторий:

```text
https://github.com/BMSTU-LYGO/plotter-proc
```

Исходная ветка:

```text
upd/ttf-centerline-pipeline
```

Создать рабочую ветку:

```bash
git checkout upd/ttf-centerline-pipeline
git pull
git checkout -b upd/centerline-one-stroke-routing
```

Текущий pipeline уже умеет:

```text
TTF → raster glyph → mask → skeleton → graph → strokes
    → paths.json → SVG → безопасный G-code
```

Сохраняются режимы `outline` и `centerline`, кеш, preview и существующая безопасность G-code.

## 1. Текущие проблемы

### 1.1. Не все буквы нормально приводятся к одной линии

Сейчас junction определяется по условию `degree >= 3` в 8-связном пиксельном графе. На диагональных изгибах это создаёт ложные пересечения. Из-за них нормальная линия буквы дробится на короткие рёбра.

Кроме того, для всех глифов выбирается один skeleton-метод. `medial_axis` и `skeletonize` дают разное качество, поэтому один метод не подходит всем буквам.

### 1.2. Очень много подъёмов ручки

Сейчас `stroke_extractor.py` создаёт один `CenterlineStroke` на каждый `SkeletonEdge`.

Текущий `junction_pairing.py` является заглушкой и возвращает strokes без соединения.

`path_optimizer.py` переставляет и разворачивает готовые strokes, но не объединяет части буквы.

Поэтому одна связная буква может состоять из большого количества отдельных движений.

## 2. Цель

Новый pipeline:

```text
TTF glyph
    ↓
несколько skeleton-кандидатов
    ↓
исправление топологии
    ↓
чистый граф
    ↓
маршрут по графу
    ↓
одна непрерывная траектория на связный компонент
    ↓
минимальный повтор существующих линий
    ↓
paths.json → G-code
```

Главный инвариант:

```text
число выходных strokes = число связных компонентов глифа
```

Примеры:

```text
а, б, ж, ф, щ → обычно 1 stroke
ё              → тело + две отдельные точки = 3 strokes
й              → тело + отдельный верхний знак = 2 strokes
!              → линия + точка = 2 strokes
```

Нельзя соединять раздельные части прямой линией: это испортит символ. Поэтому правильная цель — один stroke на один связный компонент.

## 3. Почему нужен эйлеров маршрут

Для связного неориентированного графа:

- 0 нечётных вершин → Euler circuit;
- 2 нечётные вершины → Euler path;
- больше 2 нечётных вершин → пройти все рёбра один раз одним движением нельзя.

При числе нечётных вершин больше двух нужно минимально повторить уже существующие рёбра:

1. Найти нечётные вершины.
2. Выбрать две вершины, которые останутся началом и концом.
3. Остальные нечётные вершины попарно соединить кратчайшими путями.
4. Продублировать рёбра этих путей.
5. Построить Euler path.
6. Собрать один непрерывный stroke.

Запрещено добавлять новые геометрические линии вне skeleton.

## 4. Новые модули

Добавить:

```text
src/plotter_processor/centerline_font/
├── topology.py
├── graph_simplifier.py
├── skeleton_selector.py
├── edge_geometry.py
├── route_models.py
├── shortest_paths.py
├── odd_matching.py
├── eulerizer.py
├── route_planner.py
├── route_assembler.py
└── route_quality.py
```

Изменить:

```text
centerline_font/config.py
centerline_font/compiler.py
centerline_font/debug.py
centerline_font/models.py
centerline_font/quality.py
centerline_font/serializer.py
centerline_font/skeleton_graph.py
centerline_font/skeletonizer.py
centerline_font/stroke_smoother.py
centerline_path_builder.py
pipeline.py
```

## 5. Этап 0 — baseline

Запустить:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
make test
make lint

.venv/bin/python -m plotter_processor run examples/input.txt   --font assets/handwriting.ttf   --font-mode centerline   --page A5   --size normal   --layout-config configs/layout.yaml   --machine-config configs/machine.yaml   --output-dir build/before-routing
```

Сохранить:

```text
centerline-font-preview.svg
plotter-preview.svg
paths.json
report.json
output.gcode
```

Зафиксировать метрики:

- количество глифов;
- connected components;
- graph nodes;
- graph edges;
- strokes;
- подъёмы;
- draw distance;
- travel distance;
- среднее strokes на glyph;
- десять худших glyphs.

Коммит:

```text
chore: capture centerline routing baseline
```

## 6. Этап 1 — конфигурация

Обновить `configs/layout.yaml`:

```yaml
centerline:
  algorithm_version: 2

  skeleton:
    method: auto
    candidate_methods:
      - skeletonize
      - medial_axis
    use_crossing_number: true
    suppress_corner_diagonals: true
    min_branch_width_factor: 1.5
    max_junction_cluster_px: 64
    max_micro_loop_width_factor: 2.0

  routing:
    strategy: one_stroke_per_component
    allow_retrace: true
    minimize_retrace_length: true
    max_retrace_ratio: 0.45
    exact_matching_max_odd_vertices: 20
    fallback_strategy: minimum_strokes
    deterministic: true

  strokes:
    tangent_sample_px: 10
    junction_max_angle_deg: 35.0
    resample_step_px: 2.0
    simplify_tolerance_px: 1.0
    spline_smoothing_factor: 0.04
    output_step_px: 3.0
    max_points_per_stroke: 3000
```

Поддержать стратегии:

```text
edge
minimum_strokes
one_stroke_per_component
```

Default:

```text
one_stroke_per_component
```

Все параметры должны участвовать в cache key.

Коммит:

```text
feat: add centerline topology and routing configuration
```

## 7. Этап 2 — модели маршрута

Расширить `SkeletonNode`:

```python
@dataclass(frozen=True, slots=True)
class SkeletonNode:
    id: int
    kind: str
    x: float
    y: float
    pixels: tuple[tuple[int, int], ...]
    component_id: int
    crossing_number: int
```

Расширить `SkeletonEdge`:

```python
@dataclass(frozen=True, slots=True)
class SkeletonEdge:
    id: int
    start_node_id: int
    end_node_id: int
    pixels: tuple[tuple[int, int], ...]
    closed: bool
    component_id: int
    length_px: float
```

Добавить:

```python
@dataclass(frozen=True, slots=True)
class RouteEdgeStep:
    edge_id: int
    reversed: bool
    duplicated: bool
    occurrence: int


@dataclass(frozen=True, slots=True)
class ComponentRoute:
    component_id: int
    steps: tuple[RouteEdgeStep, ...]
    start_node_id: int
    end_node_id: int
    closed: bool
    original_length_px: float
    retraced_length_px: float
    retrace_ratio: float


@dataclass(frozen=True, slots=True)
class SmoothedEdge:
    edge_id: int
    start_node_id: int
    end_node_id: int
    component_id: int
    points: tuple[Point, ...]
    length_font_units: float
    closed: bool
```

Добавить в `CenterlineStroke`:

```python
component_id: int = 0
retraced_length_font_units: float = 0.0
```

Коммит:

```text
feat: add centerline graph route models
```

## 8. Этап 3 — crossing number

Создать `topology.py`.

Соседи обходятся по кругу. Вычислять:

```python
CN = 0.5 * sum(abs(Pi - P(i+1)))
```

Классификация:

```text
CN == 0 → isolated
CN == 1 → endpoint
CN == 2 → regular
CN >= 3 → junction candidate
```

Добавить подавление диагональной связи: диагональ не считается отдельной, если существует ортогональный путь через соседний пиксель.

API:

```python
def topology_neighbors(
    pixel,
    skeleton,
    *,
    suppress_corner_diagonals: bool,
) -> tuple[tuple[int, int], ...]:
    ...


def crossing_number(pixel, skeleton) -> int:
    ...


def classify_skeleton_pixel(pixel, skeleton, config) -> str:
    ...
```

Тесты:

- линия;
- диагональ;
- диагональный поворот;
- L;
- T;
- X;
- loop;
- loop с хвостом;
- 2×2 block.

Критерий: обычный изгиб не создаёт junction.

Коммит:

```text
feat: classify skeleton topology with crossing numbers
```

## 9. Этап 4 — переделать skeleton graph

В `skeleton_graph.py` убрать основную классификацию через `degrees >= 3`.

Новый порядок:

```text
connected components
→ crossing-number classification
→ junction clusters
→ endpoints
→ dots
→ loop anchors
→ edges
```

Каждый node и edge получает `component_id`.

При traversal использовать `topology_neighbors`.

Если у regular pixel несколько возможных продолжений, считать это ошибкой топологии, а не выбирать случайно минимальный пиксель.

Добавить валидацию:

```python
def validate_skeleton_graph(
    skeleton,
    nodes,
    edges,
) -> GraphValidation:
    ...
```

Проверять:

- все pixels покрыты;
- все topology-links покрыты;
- нет duplicate regular pixels;
- нет duplicate links;
- нет zero-length edges;
- start/end принадлежат одному component;
- loops корректны.

Коммит:

```text
refactor: build topology-aware centerline graphs
```

## 10. Этап 5 — упрощение графа

Создать `graph_simplifier.py`.

Реализовать:

1. Удаление коротких endpoint-spurs относительно локальной толщины.
2. Слияние близких junction nodes, принадлежащих одному толстому пересечению.
3. Удаление только доказанно ложных микропетель.
4. Сжатие degree-2 nodes в одно edge.
5. Удаление duplicate edges.

API:

```python
def simplify_skeleton_graph(
    nodes,
    edges,
    *,
    distance,
    config,
) -> tuple[list[SkeletonNode], list[SkeletonEdge], GraphSimplificationReport]:
    ...
```

Нельзя удалять самостоятельные компоненты, точки и настоящие петли `о`, `О`, `0`, `8`.

Коммит:

```text
feat: simplify centerline graphs before routing
```

## 11. Этап 6 — выбор skeleton-кандидата

Создать `skeleton_selector.py`.

Для каждого глифа построить:

```text
skeletonize
medial_axis
```

Для каждого:

```text
skeleton
→ graph
→ simplify
→ предварительная оценка маршрута
→ score
```

Hard failures:

- потерян component;
- пустой graph;
- missing links;
- zero-length edge.

Score учитывать:

- mask coverage;
- extra area;
- lost components;
- suspicious junctions;
- spur count;
- odd vertex count;
- estimated retrace ratio;
- edge count.

Tie-break должен быть детерминированным.

API:

```python
def select_best_skeleton(mask, config) -> SelectedSkeleton:
    ...
```

Debug:

```text
candidate-skeletonize.svg
candidate-medial-axis.svg
candidate-comparison.json
```

Коммит:

```text
feat: select the best skeleton candidate per glyph
```

## 12. Этап 7 — сглаживать edges до сборки маршрута

Нельзя сглаживать полный Euler route одной spline: она срежет junction и создаст новые диагонали.

Правильный порядок:

```text
graph edge
→ font coordinates
→ RDP
→ spline с фиксированными endpoints
→ SmoothedEdge
→ route assembly
```

Создать `edge_geometry.py`:

```python
def build_smoothed_edge_geometry(
    edges,
    raster,
    config,
) -> tuple[dict[int, SmoothedEdge], list[str]]:
    ...
```

Требования:

- endpoints фиксированы;
- reverse использует обратный список тех же points;
- duplicated edge не сглаживается повторно;
- loop сохраняется;
- edge id сохраняется.

Коммит:

```text
refactor: smooth graph edges before route assembly
```

## 13. Этап 8 — кратчайшие пути

Создать `shortest_paths.py`.

Вес edge:

```text
геометрическая длина edge в пикселях
```

Реализовать deterministic Dijkstra.

API:

```python
@dataclass(frozen=True, slots=True)
class ShortestPath:
    start_node_id: int
    end_node_id: int
    edge_ids: tuple[int, ...]
    node_ids: tuple[int, ...]
    length_px: float
```

При одинаковой длине выбирать лексикографически меньший путь по edge ids.

Кешировать shortest paths между odd nodes.

Коммит:

```text
feat: calculate deterministic weighted graph paths
```

## 14. Этап 9 — matching нечётных вершин

Создать `odd_matching.py`.

Для числа odd nodes до `exact_matching_max_odd_vertices` использовать точный bitmask DP.

Для больших патологических графов допускается добавить:

```toml
networkx>=3.3
```

и использовать minimum-weight matching как fallback.

API:

```python
def minimum_odd_node_matching(
    odd_node_ids,
    shortest_paths,
) -> MatchingResult:
    ...
```

Результат должен минимизировать суммарную длину повторных путей и быть детерминированным.

Коммит:

```text
feat: match odd graph nodes with minimum retrace cost
```

## 15. Этап 10 — открытая эйлеризация

Создать `eulerizer.py`.

Случаи:

```text
0 odd → circuit без повторов
2 odd → path без повторов
>2 odd → выбрать start/end и сопоставить остальные odd nodes
```

Для каждой возможной пары start/end:

1. Удалить их из matching.
2. Найти minimum matching остальных.
3. Посчитать длину дублируемых shortest paths.
4. Выбрать минимальную.

Создать multigraph occurrences:

```python
@dataclass(frozen=True, slots=True)
class RoutedEdgeOccurrence:
    occurrence_id: int
    source_edge_id: int
    start_node_id: int
    end_node_id: int
    duplicated: bool
    weight: float
```

Рассчитать:

```text
retrace_ratio = duplicated_length / original_length
```

Если ratio выше лимита, использовать fallback.

Коммит:

```text
feat: eulerize glyph components with minimum retracing
```

## 16. Этап 11 — Euler route

Создать `route_planner.py`.

Реализовать deterministic Hierholzer algorithm.

API:

```python
def plan_component_route(component) -> ComponentRoute:
    ...


def plan_glyph_routes(nodes, edges, config) -> list[ComponentRoute]:
    ...
```

Проверки:

- каждый original edge использован хотя бы один раз;
- occurrence не используется дважды;
- соседние route steps топологически смежны;
- нет перехода между components;
- нет неизвестного edge;
- число routes равно числу connected components.

Коммит:

```text
feat: plan one Euler route per glyph component
```

## 17. Этап 12 — fallback minimum strokes

Если one-stroke требует слишком большого retrace, использовать `minimum_strokes`.

Для компонента с `2k` odd vertices минимальное число trails:

```text
max(1, k)
```

Реализовать через virtual node:

1. Соединить virtual node со всеми odd vertices.
2. Построить Euler circuit.
3. Разрезать по virtual edges.
4. Удалить virtual edges.
5. Получить минимальный набор trails без повторного рисования.

Warning:

```text
Glyph "Ж": one-stroke retrace ratio 0.72; used 3-stroke fallback
```

Коммит:

```text
feat: add minimum-trail fallback for costly glyph graphs
```

## 18. Этап 13 — сборка одной кривой

Создать `route_assembler.py`.

API:

```python
def assemble_component_route(
    route,
    edge_geometry,
) -> CenterlineStroke:
    ...
```

Алгоритм:

1. Получить points edge.
2. Развернуть при `reversed`.
3. Проверить совпадение конца предыдущего edge с началом нового.
4. Удалить duplicate junction point.
5. Добавить points.
6. Не применять spline после сборки.
7. Повторный edge добавлять теми же points в обратном или прямом порядке.

Если points не стыкуются:

```text
ошибка, а не новая соединительная линия
```

Один component создаёт один `CenterlineStroke`.

Коммит:

```text
feat: assemble Euler routes into continuous glyph strokes
```

## 19. Этап 14 — изменить compiler

Текущую цепочку:

```python
build_skeleton
prune_short_spurs
build_skeleton_graph
extract_raw_strokes
pair_strokes_by_tangent
smooth_strokes
```

заменить:

```python
selected = select_best_skeleton(mask, config)

nodes, edges, simplify_report = simplify_skeleton_graph(
    list(selected.nodes),
    list(selected.edges),
    distance=selected.distance,
    config=config,
)

edge_geometry, geometry_warnings = build_smoothed_edge_geometry(
    edges,
    raster,
    config,
)

routes = plan_glyph_routes(nodes, edges, config)

strokes = [
    assemble_component_route(route, edge_geometry)
    for route in routes
]

validate_route_coverage(edges, routes)
validate_strokes(strokes)
```

`junction_pairing.py` убрать из default pipeline.

Установить:

```text
algorithm_version: 2
```

Коммит:

```text
refactor: compile centerlines through graph routing
```

## 20. Этап 15 — quality metrics

Переделать `quality.py`.

Добавить:

```text
skeleton_method
mask_components
centerline_components
graph_nodes
graph_edges
junctions
odd_vertices
strokes_before_routing
strokes_after_routing
pen_lifts_saved
retraced_edges
retraced_length
retrace_ratio
spurs_removed
junctions_merged
false_junctions_removed
fallback_used
```

Hard failures:

- edge не покрыт;
- route использует неизвестный edge;
- non-adjacent jump;
- потерян component;
- corrupted Euler traversal;
- NaN/Infinity.

Soft warnings:

- высокий retrace;
- много junction;
- fallback;
- низкая coverage;
- skeleton methods дали близкий неоднозначный score.

Коммит:

```text
feat: score glyph topology and routing quality
```

## 21. Этап 16 — cache version 2

Обновить serializer:

```text
plotter-centerline-font version 2
```

Stroke:

```json
{
  "id": 0,
  "component_id": 0,
  "closed": false,
  "retraced_length_font_units": 120.5,
  "points": [[10.0, 20.0], [11.0, 21.0]]
}
```

Старый кеш v1 автоматически пересобирать.

Кеш инвалидируется при изменении:

- TTF SHA;
- algorithm version;
- topology config;
- routing config;
- smoothing config.

Коммит:

```text
feat: store routed centerline glyphs in cache format v2
```

## 22. Этап 17 — debug

Для каждого глифа сохранять:

```text
01-raster.png
02-mask.png
03-candidates.svg
04-selected-skeleton.png
05-original-graph.svg
06-simplified-graph.svg
07-odd-nodes.svg
08-eulerization.svg
09-route.svg
10-final-overlay.png
report.json
```

В debug SVG показывать:

- endpoints;
- odd nodes;
- junctions;
- edge ids;
- route step ids;
- начало/конец;
- duplicated edges;
- подъёмы между components.

Для связного тела буквы должно быть:

```text
один start marker
один end marker
нет pen-up внутри тела
```

Коммит:

```text
feat: visualize glyph topology and Euler routes
```

## 23. Этап 18 — preview и path builder

`centerline-font-preview.svg` должен отображать финальные routed strokes.

Под каждым glyph:

```text
components=1 strokes=1 retrace=13.9%
```

`centerline_path_builder.py` не должен разбивать длинный stroke.

Добавить metadata:

```python
{
    "routing_strategy": "one_stroke_per_component",
    "centerline_version": 2,
}
```

Коммиты:

```text
feat: show one-stroke routing metrics in font preview
refactor: preserve routed glyph strokes in page paths
```

## 24. Этап 19 — path optimizer

Проверить, что optimizer может:

- переставить disconnected components;
- развернуть весь open route;
- выбрать start closed route.

Он не должен:

- разбивать route;
- удалять retraced segment;
- соединять disconnected components;
- менять внутренний порядок Euler steps.

Добавить соответствующие тесты.

Коммит:

```text
test: preserve one-stroke glyph routes during path optimization
```

## 25. Этап 20 — report.json

Добавить:

```json
{
  "routing_strategy": "one_stroke_per_component",
  "glyph_components": 67,
  "graph_edges_before_routing": 412,
  "strokes_after_routing": 67,
  "pen_lifts_before_routing": 411,
  "pen_lifts_after_routing": 66,
  "pen_lifts_saved": 345,
  "original_draw_length_mm": 1820.4,
  "retraced_length_mm": 121.8,
  "retrace_ratio": 0.0669,
  "fallback_glyphs": []
}
```

Добавить список худших глифов по retrace ratio.

Коммит:

```text
feat: report centerline pen-lift and retrace statistics
```

## 26. Этап 21 — unit tests

Обязательные графы:

- линия;
- кольцо;
- T;
- X;
- H;
- звезда;
- петля с хвостом;
- две раздельные линии;
- три точки;
- диагональный поворот.

Для каждого проверять:

- component count;
- odd vertices;
- route count;
- retrace length;
- edge coverage;
- отсутствие jumps;
- deterministic result.

Ожидания:

```text
линия → 1 route, 0 retrace
кольцо → 1 closed route, 0 retrace
T → 1 route с минимальным retrace
X → 1 route с минимальным retrace
2 components → 2 routes
```

Коммит:

```text
test: cover centerline topology and Euler routing
```

## 27. Этап 22 — тесты кириллицы

Fixture должен содержать:

```text
а б в д ж й к м о р ф х ц ч ш щ
А Б В Д Ж Й К М О Р Ф Х Ц Ч Ш Щ
ё 0 8 . ! :
```

Acceptance:

- связный glyph → 1 stroke;
- disconnected glyph → strokes == components;
- `о`, `О`, `0` → closed route;
- `ё` сохраняет две точки;
- `й` сохраняет знак;
- `ж`, `ф`, `щ` не дробятся;
- нет новых диагоналей;
- нет двойной линии;
- output deterministic.

Коммит:

```text
test: verify one-stroke routes for Cyrillic glyphs
```

## 28. Этап 23 — E2E

Запустить документ:

```text
Сегодня небольшой плоттер аккуратно выводит пробный
абзац рукописным шрифтом на чистом листе бумаги.
Ёжик идёт домой.
АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩ
абвгдеёжзийклмнопрстуфхцчшщ
1234567890.,!?
```

Проверить:

- pipeline ok;
- cache version 2;
- one-stroke strategy;
- strokes существенно меньше baseline;
- второй запуск использует кеш;
- preview и paths deterministic;
- G-code безопасен.

Главный критерий:

```text
strokes_after == сумма connected components всех glyph placements
```

если fallback не использовался.

Коммит:

```text
test: cover one-stroke centerline pipeline end to end
```

## 29. Этап 24 — визуальная приёмка

Проверить:

- нет двойной обводки;
- нет параллельных centerlines;
- нет ложных диагоналей;
- изгибы не становятся junction;
- петли и точки сохранены;
- связная буква рисуется одним stroke;
- повторные участки проходят по существующей линии;
- spline не срезает junction;
- подъёмы только между disconnected components.

Не принимать работу, если `ж`, `ф`, `щ` по-прежнему состоят из множества strokes.

## 30. Этап 25 — реальный плоттер

Тестовый текст:

```text
а б ж о ф щ
ё й
А Ж О Ф Щ
0128
```

Перед запуском:

1. Проверить все SVG.
2. Включить route debug.
3. Проверить report.
4. Сделать dry-run.
5. Начать с A5.
6. Не включать нагрев.
7. Не включать `G28` без проверки механики.

Acceptance:

- тело связной буквы рисуется без подъёма;
- retrace не портит форму;
- точки рисуются отдельно;
- нет движения с опущенной ручкой через пустое место.

## 31. Критерии готовности

### Топология

- [ ] Crossing number.
- [ ] Suppress corner diagonals.
- [ ] False junctions сокращены.
- [ ] Degree-2 chains объединены.
- [ ] Graph coverage валиден.
- [ ] Components, loops и dots сохранены.

### Skeleton

- [ ] Режим `auto`.
- [ ] Сравнение `skeletonize` и `medial_axis`.
- [ ] Детерминированный выбор.
- [ ] Candidate diagnostics.

### Routing

- [ ] Один route на component.
- [ ] Euler circuit/path.
- [ ] Minimum retrace для >2 odd nodes.
- [ ] Только существующие edges.
- [ ] Нет connector lines.
- [ ] Полное покрытие.
- [ ] Fallback.
- [ ] Retrace ratio.

### Output

- [ ] Один component → один `CenterlineStroke`.
- [ ] Один `CenterlineStroke` → один `PlotterStroke`.
- [ ] Optimizer не разбивает route.
- [ ] Cache v2.
- [ ] Report показывает lifts и retrace.
- [ ] Debug показывает duplicated edges.

### Совместимость и безопасность

- [ ] `outline` работает.
- [ ] `draw-your-font` не меняется.
- [ ] `paths.json` совместим.
- [ ] G-code exporter не переписан.
- [ ] Нет heating.
- [ ] Нет extrusion.
- [ ] Нет `G28` по умолчанию.
- [ ] Bounds проверяются.

## 32. Порядок коммитов

```text
chore: capture centerline routing baseline
feat: add centerline topology and routing configuration
feat: add centerline graph route models
feat: classify skeleton topology with crossing numbers
refactor: build topology-aware centerline graphs
feat: simplify centerline graphs before routing
feat: select the best skeleton candidate per glyph
refactor: smooth graph edges before route assembly
feat: calculate deterministic weighted graph paths
feat: match odd graph nodes with minimum retrace cost
feat: eulerize glyph components with minimum retracing
feat: plan one Euler route per glyph component
feat: add minimum-trail fallback for costly glyph graphs
feat: assemble Euler routes into continuous glyph strokes
refactor: compile centerlines through graph routing
feat: score glyph topology and routing quality
feat: store routed centerline glyphs in cache format v2
feat: visualize glyph topology and Euler routes
feat: show one-stroke routing metrics in font preview
refactor: preserve routed glyph strokes in page paths
test: preserve one-stroke glyph routes during path optimization
feat: report centerline pen-lift and retrace statistics
test: cover centerline topology and Euler routing
test: verify one-stroke routes for Cyrillic glyphs
test: cover one-stroke centerline pipeline end to end
docs: document one-stroke routing and retracing
```

## 33. Финальная проверка

```bash
make test
make lint

rm -rf build/final-one-stroke

.venv/bin/python -m plotter_processor compile-centerline-font   assets/handwriting.ttf   --text-file examples/input.txt   --output build/final-one-stroke/font.centerline.json   --preview build/final-one-stroke/font.centerline.svg   --debug-dir build/final-one-stroke/debug   --force

.venv/bin/python -m plotter_processor run examples/input.txt   --font assets/handwriting.ttf   --font-mode centerline   --centerline-cache build/final-one-stroke/font.centerline.json   --page A5   --size normal   --layout-config configs/layout.yaml   --machine-config configs/machine.yaml   --output-dir build/final-one-stroke/job
```

Проверить:

```text
font.centerline.json
font.centerline.svg
debug/
font-preview.svg
centerline-font-preview.svg
plotter-preview.svg
paths.json
output.gcode
report.json
```

## 34. Итоговая архитектура

Старая схема:

```text
skeleton → каждый edge отдельно → много strokes → много подъёмов
```

Новая схема:

```text
TTF glyph
→ лучший skeleton
→ topology-aware graph
→ graph simplification
→ minimum-length eulerization
→ один route на component
→ один continuous stroke
→ минимум подъёмов
```

Главный принцип:

> Связное тело буквы рисуется одним непрерывным движением. Если граф нельзя пройти по одному разу, плоттер минимально повторяет уже существующий участок, а не поднимает ручку и не рисует новую соединительную линию.
