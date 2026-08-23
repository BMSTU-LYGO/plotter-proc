# UPD_Plotter_11 — план исправлений после полного quality audit

## Контекст

Работать с текущим состоянием репозитория:

```text
HEAD: 708cd7ac734bd57088e4590700a56e1f39062a51
```

Исходный аудит находится в:

```text
report/
```

Ключевые файлы аудита:

```text
report/REPORT.md
report/summary.json
report/artifact_manifest.json
report/commands.log
report/visual-index.html
report/analysis/worst-glyphs.json
```

Baseline на момент аудита:

```text
lint: passed
test: 239 passed
smoke: passed

audit jobs: 10
successful: 7
failed diagnostically: 3

findings:
P0: 1
P1: 5
P2: 5
P3: 2
```

Главная цель этого этапа — не добавлять новые крупные возможности, а довести уже существующий pipeline до максимально качественного, предсказуемого и диагностируемого состояния.

---

# Общие правила работы для Codex

## 1. Сначала воспроизведение, потом исправление

Перед изменением каждой проблемы:

1. найти соответствующий finding в `report/REPORT.md`;
2. открыть связанные debug/report artifacts;
3. воспроизвести проблему на текущем HEAD;
4. добавить или подготовить regression test, который падает на текущей реализации;
5. только после этого менять production-код;
6. после исправления убедиться, что regression test проходит;
7. прогнать связанные существующие тесты;
8. после завершения блока выполнить полный:

```bash
make lint
make test
make smoke
```

Не считать проблему исправленной только потому, что один ручной пример больше не падает.

---

## 2. Не делать большой рефакторинг одновременно с bugfix

Запрещено в рамках одного изменения одновременно:

- переписывать весь centerline pipeline;
- переписывать paginator;
- заменять geometry model;
- менять глобальные thresholds;
- менять machine workspace "чтобы тест прошёл";
- отключать strict validation;
- маскировать ошибку fallback'ом без понимания причины.

Каждый bugfix должен быть локализованным и проверяемым.

---

## 3. Не ухудшать уже подтверждённые свойства

После каждого блока должны оставаться верными:

- `lint` проходит;
- все существующие тесты проходят;
- smoke проходит;
- G-code не содержит heating/home/extrusion команд;
- детерминированная geometry не ломается;
- canonical font cache продолжает работать;
- A5 DOCX pipeline продолжает завершаться;
- multi-page park/pause остаётся корректным;
- rotation raster остаётся фактически применённой к strokes;
- safe connections не становятся визуально более агрессивными.

---

## 4. Формат работы по блокам

После каждого крупного блока создать файл:

```text
docs/UPD_Plotter_11_block_<N>_report.md
```

В нём обязательно написать:

```text
Что было сломано
Как воспроизводилось
Root cause
Какие файлы изменены
Что именно изменено
Какие тесты добавлены
Какие команды прогнаны
Результат до / после
Оставшиеся ограничения
```

Не переходить к следующему крупному блоку, пока предыдущий не имеет regression coverage.

---

# БЛОК 1. Исправить критические ошибки pipeline

Этот блок имеет наивысший приоритет.

Пока он не завершён, не заниматься performance-оптимизациями или крупным cleanup.

---

## 1.1. P0 — исправить падение PDF math centerline routing

### Finding

Из аудита:

```text
F-001 — P0 BUG
PDF math centerline route aborts both layouts
```

Оба режима:

```text
PDF preserve
PDF reflow
```

падают на математической формуле:

```text
page-001-math-001
edge 20
endpoint delta ≈ 0.041667
```

Проблема происходит до формирования нормального PDF preview/G-code.

### Предполагаемый root cause из аудита

Связанные edges логически имеют общий graph node, но после smoothing их endpoint coordinates перестают быть абсолютно одинаковыми.

`route_assembler.py` ожидает точное равенство `Point`.

В результате топологически связный маршрут отклоняется как разорванный.

Связанные области:

```text
src/plotter_processor/.../centerline_font/edge_geometry.py
src/plotter_processor/.../stroke_smoother.py
src/plotter_processor/.../route_assembler.py
```

Codex должен самостоятельно найти точные актуальные пути и функции.

### Что требуется сделать

Не делать решение вида:

```python
if distance < large_epsilon:
    connect_everything()
```

Такой подход может соединить реальные разрывы geometry.

Нужно сохранить разделение:

```text
graph topology
и
rendered/smoothed geometry
```

Если два edge относятся к одному и тому же graph node, их геометрические endpoints после smoothing должны быть нормализованы относительно этого узла.

Предпочтительный принцип:

```text
shared graph node
→ canonical endpoint position
→ adjacent edge geometries используют одну canonical coordinate
→ route assembler проверяет уже нормализованную геометрию
```

Допустим небольшой numerical tolerance только для floating-point verification, но tolerance не должен быть механизмом выбора того, какие несвязанные edges соединять.

### Обязательно проверить

1. Что edge endpoints, относящиеся к одному graph node, совпадают после smoothing.
2. Что route assembler по-прежнему отбрасывает реальный geometric gap между несвязанными узлами.
3. Что не появилось случайных bridges.
4. Что не ухудшились:
   - route count;
   - retrace;
   - connected components;
   - centerline glyph output.

### Regression tests

Добавить минимум два теста.

#### Test A — quantized shared endpoint

Создать маленький synthetic graph:

```text
edge A ---- node ---- edge B
```

После симуляции smoothing endpoints отличаются примерно на величину порядка той, что обнаружена аудитом.

Ожидание:

```text
assembler успешно собирает единый route
```

#### Test B — real gap

Два edge геометрически близки, но принадлежат разным graph nodes.

Ожидание:

```text
assembler НЕ объединяет их
```

Это защищает от слишком широкого epsilon.

### Интеграционный regression

Обязательно повторить оба исходных PDF job:

```text
pdf-centerline-preserve-a5
pdf-centerline-reflow-a5
```

Оба должны завершиться со:

```text
status = success
```

и создать:

```text
plotter-preview.svg
paths.json
output.gcode
report.json
math-debug / latex-debug
```

### После успешного исправления

Теперь, когда PDF перестал падать, провести те проверки, которые аудит не смог закончить:

- visual math suppression;
- duplicate rendering;
- absorbed PDF primitives;
- tables в PDF;
- arrows/semantic lines в PDF;
- underline duplication;
- preserve vs reflow;
- PDF preview visual comparison.

Если при этом обнаружатся новые реальные баги, не прятать их внутри этого пункта. Зафиксировать отдельными findings в block report.

### Definition of Done

Пункт считается завершённым только если:

```text
PDF preserve проходит
PDF reflow проходит
regression shared-node test проходит
real-gap negative test проходит
нет нового broad tolerance hack
make lint/test/smoke проходят
```

---

## 1.2. P1 — корректный exit code для `python -m plotter_processor`

### Finding

```text
F-002 — P1 BUG
module entrypoint reports process success for failed jobs
```

Сейчас pipeline может:

- вывести `Error:`;
- записать `report.status = error`;
- не создать нормальный результат;

но процесс:

```bash
python -m plotter_processor ...
```

возвращает:

```text
exit code 0
```

Это опасно для:

- CI;
- Makefile;
- benchmark;
- shell scripts;
- будущего automation;
- самого Codex.

### Root cause из аудита

`__main__.py` вызывает `main()`, но return value не становится process exit code.

Ожидаемая схема:

```python
raise SystemExit(main())
```

или эквивалентная корректная реализация.

### Что требуется сделать

Исправить только entrypoint semantics.

Не менять `_run()` так, чтобы она бросала исключение просто ради exit code, если текущая архитектура уже корректно возвращает код.

Нужно сохранить нормальное разделение:

```text
cli/main возвращает int
module entrypoint превращает int в process exit status
```

### Regression tests

Запустить через реальный subprocess:

```bash
python -m plotter_processor run ...
```

#### Success case

Валидный маленький input:

```text
exit code == 0
```

#### Failure case

Заведомо невалидная конфигурация/input:

```text
exit code != 0
report.status == error
```

По возможности проверить конкретно `1`, если это установленный CLI contract.

### Дополнительно проверить

Если есть console-script entrypoint из `pyproject.toml`, убедиться, что:

```text
plotter-processor ...
```

и

```text
python -m plotter_processor ...
```

ведут себя одинаково.

### Definition of Done

```text
успех → exit 0
pipeline error → non-zero
CLI text/error report сохраняются
subprocess regression test существует
```

---

## 1.3. P1 — импортировать все VML-стрелки из одного `pict`

### Finding

```text
F-003 — P1 BUG
three source VML arrows collapse to one
```

В контрольном DOCX реально находятся три `<v:line>`:

1. one-headed;
2. two-headed;
3. classic arrowhead style.

Pipeline импортирует только одну стрелку.

### Root cause из аудита

В `docx_document_reader.py::add_arrow()` находятся все линии, но фактически используется только:

```text
lines[0]
```

и создаётся один semantic object.

### Что требуется сделать

Изменить импорт так, чтобы:

```text
1 VML pict
может породить
N semantic arrow/line objects
```

Для каждой `<v:line>` отдельно сохранить:

- source order;
- start;
- end;
- stroke;
- width;
- head;
- tail;
- arrow style;
- anchor/source identity;
- transform/position;
- provenance.

Не переиспользовать один ID для нескольких стрелок.

### Важный момент

Не должно возникнуть:

```text
semantic arrow
+
generic line
```

для одной и той же исходной VML geometry.

После исправления проверить semantic deduplication.

### Regression fixture

Сделать минимальный DOCX fixture, в одном `pict` которого находятся:

```text
arrow A: one headed
arrow B: two headed
arrow C: different/classic head
```

Ожидание:

```text
semantic arrows == 3
```

Проверить не только count, но и:

```text
head/tail semantics
source ordering
direction
stable IDs
```

### Проверка optimizer

Убедиться, что path optimizer не реверсит semantic arrow так, что head оказывается с неправильной стороны.

### Definition of Done

В исходном full-test документе:

```text
source VML arrows: 3
imported semantic arrows: 3
rendered arrows: 3
duplicates: 0
```

---

## 1.4. P1 — A4 и workspace: сделать корректный early preflight

### Finding

```text
F-004 — P1 BUG/CONFIGURATION
advertised A4 conflicts with default 220 mm workspace
```

При portrait A4 итоговая Y достигает примерно:

```text
290.448 mm
```

а стандартный Ender/machine config имеет workspace порядка:

```text
220 mm
```

Сейчас job тратит время на parsing/layout/font и падает слишком поздно.

### Главная цель

Не заставлять физически невозможный A4 "проходить".

Нельзя просто сделать:

```yaml
workspace_y: 300
```

если реальное устройство этого не поддерживает.

Нужно сделать поддержку честной и предсказуемой.

### Часть A — ранняя проверка совместимости

До дорогих стадий:

- font compilation;
- handwriting;
- images;
- path simplification;

выполнить preflight:

```text
requested page geometry
+ margins
+ orientation
+ machine origin
+ printable workspace
→ compatible / incompatible
```

Если incompatible:

- завершить job сразу;
- вернуть non-zero exit code;
- записать понятную ошибку;
- предложить пользователю варианты.

Например:

```text
A4 portrait (210×297 mm) does not fit configured XY workspace 220×220 mm.
Use a compatible machine config, supported orientation, or smaller page size.
```

### Часть B — определить честный A4 workflow

Проверить, что реально подразумевает hardware/config проекта.

Варианты могут быть:

- отдельный machine config для устройства, где A4 физически помещается;
- другая ориентация, если она физически реализуема;
- page feed / movable-paper configuration;
- явное отсутствие A4 для текущего machine profile.

Не выдумывать hardware capabilities.

Если default Ender configuration физически не позволяет A4, CLI/documentation должны говорить это прямо.

### Часть C — CLI

Проверить, не создаёт ли:

```text
--page A4
```

ложного обещания универсальной поддержки независимо от machine profile.

При необходимости оставить A4 как page format, но валидировать комбинацию:

```text
page + orientation + machine
```

### Regression tests

#### Impossible

```text
A4 portrait + 220x220 workspace
```

должен падать **до expensive processing**.

В тесте желательно проверить, что не стартовал font compile/handwriting stage.

#### Possible

Совместимый synthetic machine config с достаточным workspace должен успешно пройти.

### Definition of Done

```text
невозможная комбинация падает быстро и понятно
совместимая комбинация проходит
workspace не расширен фиктивно
README/config docs соответствуют реальному поведению
```

---

# БЛОК 2. Улучшить качество centerline шрифта

Этот блок выполнять после исправления P0 и базовых CLI/import bugs.

---

## 2.1. P1 — исправить 12 glyphs с `needs_review`

### Finding

```text
F-005 — P1 QUALITY LIMITATION
12 real glyphs need review
```

Аудит показал, что проблема относится не к абстрактному font corpus, а к символам, реально используемым в test document.

В частности:

```text
;
.
…
:
?
Щ
Ц
Ш
U
И
Й
Ю
```

Особенно низкий coverage у punctuation:

```text
; ≈ 0.609
. ≈ 0.632
… ≈ 0.633
: ≈ 0.635
? ≈ 0.678
```

У некоторых capital glyphs заметен retrace:

```text
Щ
Ц
Ш
U
И
```

### Главное ограничение

НЕ делать:

- глобальное снижение `coverage` threshold;
- отключение quality gate;
- замену всего skeleton algorithm;
- один универсальный override для всех символов;
- "auto-pass", скрывающий проблему в отчёте.

Цель — улучшить саму геометрию.

---

## 2.2. Сначала создать per-glyph диагностический harness

До изменения алгоритма добавить удобный способ для одного glyph получить:

```text
input outline/mask
all candidate skeletons
selected candidate
graph before routing
route after routing
final normalized strokes
coverage
inside-mask ratio
components
endpoints
junctions
short edges
micro loops
odd vertices
retrace ratio
selected method
quality decision
```

Артефакты должны сохраняться, например:

```text
build/glyph-debug/<codepoint>-<glyph>/
```

или в другом логичном debug location.

Нужен отдельный SVG/PNG не только общий `centerline-font-preview.svg`.

### Зачем

Без per-glyph view любые изменения `skeletonize`, `medial_axis`, pruning или routing будут гаданием.

---

## 2.3. Маленькая пунктуация

Для:

```text
.
:
;
…
```

отдельно исследовать причину низкого coverage.

У маленьких замкнутых/почти круглых масок обычная skeleton metric может давать плохую оценку, хотя визуально glyph корректен.

Нужно различить два случая:

### A. geometry реально плохая

Тогда исправлять candidate generation / normalization.

### B. geometry визуально корректна, но metric неприменима к tiny glyph

Тогда корректировать quality evaluation **для класса маленьких marks**, а не глобально.

Например, для punctuation может быть важнее:

- stroke centroid inside mask;
- component count;
- normalized radius;
- distance-to-mask;
- topology;

чем обычный coverage ratio.

Но такое изменение должно быть доказано fixture'ами.

### Для `;`

Сохранить две компоненты:

```text
dot
lower curved/comma part
```

Не пытаться соединить их одной линией.

### Для `:`

Ожидаются две физически отдельные компоненты.

Подъём пера между ними нормален.

---

## 2.4. Вопросительный знак `?`

По аудиту:

```text
before routes: 6
after routes: 2
components: 2
```

Проверить:

- верхнюю основную компоненту;
- нижнюю точку;
- routing основной кривой;
- spur после medial axis;
- ненужные ответвления;
- визуальную форму крюка.

Цель:

```text
основная часть — один качественный route
точка — отдельная component
```

---

## 2.5. Capital/Cyrillic с retrace

Отдельно исследовать:

```text
Щ
Ц
Ш
И
Й
Ю
U
```

Не всегда retrace является ошибкой.

Для connected graph с несколькими odd vertices часть повторного прохода может быть топологически неизбежной.

Поэтому для каждого glyph определить:

```text
minimum theoretical trail/retrace
actual retrace
excess retrace
```

Оптимизировать только **excess retrace**.

### Возможные направления

Codex должен проверить их по коду, а не внедрять вслепую:

- выбор другого skeleton candidate;
- pruning маленьких ветвей;
- snapping junctions;
- graph cleanup до Euler routing;
- выбор более удачной traversal order;
- Chinese-postman/minimum-route strategy;
- локальные glyph overrides только для действительно проблемных shapes.

### Требование

После исправления нельзя увеличивать:

- component count;
- pen lifts;
- geometry outside glyph mask.

---

## 2.6. Regression corpus для 12 glyphs

Добавить fixture/test, содержащий именно эти символы.

Для каждого хранить numeric bounds.

Не требовать точного равенства float metrics, если это сделает тест хрупким.

Проверять разумные constraints:

```text
component count
coverage >= target
retrace <= target
route count
inside-mask >= target
quality != needs_review
```

Там, где `needs_review` остаётся объективно оправданным, описать почему.

Цель не обязательно искусственно получить:

```text
169/169 auto-pass
```

Цель — получить визуально и топологически правильный результат.

### Definition of Done

- все 12 glyphs просмотрены отдельно;
- для каждого есть debug artifacts;
- причины `needs_review` классифицированы;
- реально плохие glyphs улучшены;
- не применено глобальное ослабление quality gate;
- full font regression проходит.

---

# БЛОК 3. Ускорить основной warm pipeline

---

## 3.1. P1 — warm conversion ≈126.7 s

### Finding

```text
F-006 — P1 PERFORMANCE BOTTLENECK
warm primary conversion takes ~126.7 s
```

Основной успешный job:

```text
~126.564 s
```

repeat:

```text
~126.815 s
```

То есть проблема воспроизводима и не связана с cold font cache.

Основные стадии:

```text
handwriting:    ~68.382 s  (~54.0%)
simplification: ~41.468 s  (~32.8%)
build paths:     ~8.933 s   (~7.1%)
```

Handwriting + simplification:

```text
~86.8% общего времени
```

Font compile при warm cache:

```text
~1.474 s
```

Следовательно, **не оптимизировать сейчас font cache**.

---

## 3.2. Сначала profiler

Не делать micro-optimizations по ощущениям.

Запустить profiler отдельно на:

```text
handwriting
path simplification
```

Получить:

- cumulative time;
- call count;
- avg time;
- worst functions;
- масштабирование относительно количества paths/strokes.

Предпочтительно использовать:

```text
cProfile / py-spy / scalene
```

в зависимости от уже доступных зависимостей.

Не добавлять тяжёлую runtime dependency в production только ради профилирования.

---

## 3.3. Проверить потенциальную O(N²) геометрию

Особенно проверить:

### Handwriting

- collision checks между каждым новым connector и всеми strokes;
- repeated bbox calculations;
- repeated shapely geometry construction;
- repeated nearest-point calculations;
- corridor tests;
- tangent calculation;
- anchors, вычисляемые многократно;
- одна и та же glyph geometry, пересчитываемая для разных проверок.

### Simplifier

- repeated full-list scans;
- pairwise segment checks;
- repeated point distance;
- repeated normalization;
- simplification отдельно для уже одинаковых/cached paths;
- обработку очень коротких strokes.

---

## 3.4. Spatial indexing / cached geometry

Если profiler подтверждает spatial bottleneck, рассмотреть:

```text
uniform grid
R-tree / STRtree
bbox spatial bins
prepared geometry
```

Но вводить их только там, где измерение показывает выигрыш.

Для connector collision check предпочтительно запрашивать:

```text
только strokes, bbox которых пересекает candidate corridor
```

а не весь документ.

---

## 3.5. Не менять geometry ради скорости

Performance fix должен сохранять:

```text
paths geometry
accepted/rejected connections
page layout
stroke count
G-code semantics
```

Для main fixture до/после сравнить:

- SHA geometry после нормализации provenance;
- accepted connection pairs;
- stroke count;
- draw/travel;
- warnings;
- page count.

---

## 3.6. Починить benchmark workflow

Аудитный:

```text
cold + 3 warm
```

benchmark не закончил даже первый cold run примерно за 12 минут.

Нужно выяснить:

1. реально ли cold font compilation настолько медленная;
2. завис ли benchmark;
3. выполняет ли он лишнюю работу;
4. нет ли отсутствующего progress/stage timeout;
5. корректно ли отделены:
   - font cold compile;
   - document conversion;
   - warm conversion.

Сделать benchmark таким, чтобы можно было запускать отдельно:

```bash
--cold-only
--warm-only
--warm-runs N
```

и видеть stage progress.

Не использовать timeout как способ скрыть performance problem.

---

## 3.7. Цель performance блока

Не задавать произвольный target без измерений, но ожидать **существенного** сокращения доминирующих стадий.

После оптимизации повторить минимум:

```text
3 warm runs
```

Записать:

```text
before
after
median
percentage improvement
geometry equivalence
```

### Definition of Done

- bottleneck подтверждён profiler'ом;
- минимум одна dominant stage ускорена измеримо;
- output geometry не изменилась непреднамеренно;
- warm benchmark воспроизводим;
- результаты записаны в block report.

---

# БЛОК 4. Исправить дополнительные ошибки импорта и layout

---

## 4.1. P2 — `extract` должен включать таблицы и OMML

### Finding

```text
F-007 — P2 BUG
DOCX extract omits tables and OMML content
```

Структурный import умеет видеть таблицы и OMML, но команда:

```bash
plotter_processor extract ...
```

выдаёт только top-level paragraphs.

Это значит, что `extract` сейчас не является полноценной textual projection документа.

### Что сделать

Сначала определить формальный контракт команды `extract`.

Предлагаемый контракт:

```text
выдать текст документа в стабильном source reading order,
включая paragraph text, table cell text и доступное textual representation math
```

### Таблицы

Для таблиц сохранить logical reading order:

```text
row 1 cell 1
row 1 cell 2
...
row 2 ...
```

Не дублировать содержимое merged cells.

Repeated header в source extraction должен появляться один раз как source content, а не размножаться по pagination output.

### OMML

Нужно выбрать стабильное textual representation:

- нормализованный math text;
- LaTeX-like representation;
- существующий semantic math text, если он уже есть.

Не терять expression полностью.

### Regression

Fixture:

- обычный paragraph;
- merged table;
- repeated-header table;
- OMML;
- paragraph after table.

Проверить reading order.

---

## 4.2. P2 — полноценные center/right/decimal tab stops

### Finding

```text
F-011 — P2 QUALITY LIMITATION
center/right DOCX tabs are approximated
```

Сейчас позиция stop сохраняется, но semantics вида:

```text
center
right
decimal
```

теряются или аппроксимируются.

### Что требуется

Tab placement должен учитывать **реальную ширину следующего text run/token**.

#### Left tab

```text
start_x = stop_x
```

#### Right tab

```text
end_x = stop_x
start_x = stop_x - rendered_width
```

#### Center tab

```text
center_x = stop_x
start_x = stop_x - rendered_width / 2
```

#### Decimal tab

Нужно найти decimal separator в следующем token/run и выровнять separator по stop.

Поддержать хотя бы:

```text
.
,
```

в зависимости от текста.

### Важно

Нельзя просто вычислять количество пробелов.

Tab geometry должна работать в миллиметрах после font metrics/layout.

### Regression

Создать минимальный DOCX с одинаковым stop:

```text
left
center
right
decimal
```

и измерить ожидаемые glyph bounds.

Тестировать также A4→A5 scaling.

---

## 4.3. P2 — safe и aggressive connections сейчас неразличимы на stress corpus

### Finding

```text
F-010 — P2 QUALITY LIMITATION
aggressive connections do not change this stress corpus
```

На audit corpus:

```text
safe:       105 accepted
aggressive: 105 accepted
```

Output byte-identical.

При этом rejection labels иногда отличаются.

### Это не обязательно bug

Сначала понять, есть ли в реализации реальная behavioral difference между режимами.

#### Если difference существует

Добавить targeted fixture, где:

```text
safe rejects
aggressive accepts
```

но при этом:

- collision guard остаётся;
- punctuation guard остаётся;
- connector визуально допустим.

#### Если intended difference фактически отсутствует

Упростить/document semantics.

Не держать два пользовательских режима только ради разных thresholds, которые никогда не влияют на output.

### Нельзя

Делать aggressive более опасным только ради того, чтобы тесты показали разницу.

---

# БЛОК 5. Сделать отчёты и артефакты действительно полезными

---

## 5.1. P2 — заполнить реальные centerline/report metrics

### Finding

```text
F-009 — P2 OBSERVABILITY
key report fields are empty or hard-coded
```

Аудит нашёл:

```text
centerline.worst_glyphs = []
```

при наличии 12 `needs_review`.

Aggregate:

```text
retraced_length_mm = 0
```

при ненулевом retrace отдельных glyphs.

Также:

```text
classification conflicts
suppressed duplicates
```

в некоторых местах hard-coded в 0.

### Что требуется

Нужно различать:

```text
реально измеренный ноль
```

и:

```text
метрика вообще не вычислялась
```

Лучше:

```json
{
  "value": 0,
  "measured": true
}
```

или:

```json
null
```

для unavailable — в зависимости от текущей schema philosophy.

Не выдавать fake-zero.

### centerline.worst_glyphs

Заполнять top-N реально используемых/скомпилированных проблемных glyphs.

Минимальные поля:

```text
glyph
codepoint
coverage
inside-mask
components
routes before
routes after
retrace ratio
method
quality status
warning
```

### Aggregate retrace

Считать из фактических route/glyph data.

### Semantic classification/dedup

Если conflicts/suppression реально считаются — прокинуть фактические значения.

Если нет — `null/not available`, а не hard-coded 0.

### Таблицы и изображения

По возможности добавить observability для:

```text
table splits
repeated headers emitted
shared borders suppressed
image strokes
micro strokes
image cache hits
```

Но не расширять schema бесконечно — только то, что пригодилось в аудите.

### Regression

Known fixture с:

- retraced glyph;
- `needs_review`;
- semantic duplicate/conflict.

Проверить, что report содержит ненулевые реальные значения.

---

## 5.2. P2 — byte deterministic `paths.json`

### Finding

```text
F-008 — P2 MAINTAINABILITY/OBSERVABILITY
paths.json is not byte-deterministic
```

Geometry полностью deterministic.

Различается только job-local:

```text
source_path
```

к извлечённым image assets внутри output directory.

### Цель

При одинаковом input/config:

```text
paths.json
```

должен быть идентичным независимо от того, в какой output directory запущен job.

### Возможные варианты

Использовать:

```text
input-relative asset identity
content hash
stable source element ID
logical URI
```

вместо absolute/job-local extracted path.

### Важно

Не потерять provenance.

Нужно иметь возможность понять, из какого source object произошёл stroke.

### Regression

Один input запустить:

```text
output-A/
output-B/
```

Сравнить:

```text
sha256(paths.json)
```

Ожидание:

```text
identical
```

---

## 5.3. P3 — привести `gcode` subcommand и full run к понятному контракту

### Finding

```text
F-012 — P3 MAINTAINABILITY
G-code subcommand omits full-run metadata comments
```

Motion commands совпадают, байты — нет.

### Сначала определить контракт

Есть два допустимых варианта.

#### Вариант A

Команда `gcode` гарантирует только functional equivalence.

Тогда это нужно документировать и тестировать сравнением non-comment commands.

#### Вариант B

Ожидается byte-identical regeneration.

Тогда вынести common header/comment generation в shared code.

### Не делать

Не дублировать комментарий-generating logic в двух командах.

---

# БЛОК 6. Безопасный cleanup архитектуры paginator

---

## 6.1. P3 — слишком большой `document_paginator.py`

### Finding

```text
F-013 — P3 MAINTAINABILITY
paginator concentrates too many policies
```

Модуль около:

```text
2163 lines
```

и одновременно содержит:

- page state;
- paragraphs;
- tables;
- images;
- formulas;
- semantic objects;
- rotation;
- debug bookkeeping.

### Это НЕ блок для rewrite

Проводить только после того, как предыдущие correctness regression tests уже существуют.

### Цель

Разделить cohesive placement logic, не меняя policy.

Например, потенциальные отдельные units:

```text
TextPlacement
TablePlacement
ImagePlacement
MathPlacement
SemanticShapePlacement
PageState/PageCursor
DebugCollector
```

Точные названия определить по текущему коду.

### Метод

1. выбрать один изолируемый кусок;
2. покрыть текущую behavior тестами;
3. вынести без изменения результата;
4. сравнить output;
5. только потом следующий кусок.

### Обязательная проверка

После каждого extraction/refactor сравнить full fixture:

```text
page count
placement geometry
paths geometry
warnings
debug artifacts
G-code
```

### Запрещено

Одновременно с этим блоком менять:

- pagination algorithm;
- table splitting policy;
- image wrapping policy;
- rotation math;
- A4/A5 transform policy.

---

# БЛОК 7. Повторный полный интеграционный прогон

После исправления всех предыдущих блоков заново прогнать исходный full-test document.

Использовать те же основные сценарии, что в аудите.

---

## 7.1. DOCX primary

```text
DOCX
centerline
A5
hybrid
safe connections
strict math
layout debug
semantic debug
connection debug
```

---

## 7.2. DOCX outline control

```text
DOCX
outline
A5
hybrid
connections off
```

---

## 7.3. PDF preserve

Теперь обязан завершаться успешно.

---

## 7.4. PDF reflow

Теперь обязан завершаться успешно.

---

## 7.5. Connections

```text
off
safe
aggressive
```

Сравнить результаты.

---

## 7.6. Determinism

Два одинаковых job.

Проверить:

```text
paths.json
preview
G-code
```

После F-008 `paths.json` также должен быть byte-identical.

---

## 7.7. Performance

Выполнить:

```text
3 warm
```

и, если cold benchmark после блока 3 стал практически выполним:

```text
1 cold
```

Не удалять canonical user cache.

---

# БЛОК 8. Финальный quality gate

Перед завершением UPD_Plotter_11 должны пройти:

```bash
make lint
make test
make smoke
```

Также выполнить независимый G-code safety scan.

Проверить отсутствие:

```text
M104
M109
M140
M190
G28
extrusion E
NaN
Infinity
```

---

# Финальные критерии по исходным findings

## F-001 PDF math route

```text
DONE:
PDF preserve success
PDF reflow success
shared endpoint regression exists
real-gap negative regression exists
```

## F-002 CLI exit status

```text
DONE:
failed run returns non-zero
successful run returns zero
```

## F-003 VML arrows

```text
DONE:
3 source arrows → 3 semantic/rendered arrows
correct head/tail
no duplicates
```

## F-004 A4/workspace

```text
DONE:
impossible config fails at preflight
compatible config works
no fake workspace expansion
```

## F-005 centerline glyphs

```text
DONE:
12 glyphs individually analysed
actual geometry issues improved
quality metrics truthful
no global gate weakening
```

## F-006 performance

```text
DONE:
dominant functions profiled
warm conversion measurably faster
geometry preserved
benchmark reproducible
```

## F-007 extract

```text
DONE:
table content included
OMML included
reading order stable
merged cells not duplicated
```

## F-008 determinism

```text
DONE:
same input/config in different output dirs → identical paths.json
```

## F-009 reports

```text
DONE:
worst_glyphs populated
retrace aggregate real
no hard-coded fake-zero metrics
```

## F-010 connections

```text
DONE:
safe/aggressive behavior either demonstrated by fixture or semantics simplified/documented
```

## F-011 tabs

```text
DONE:
left/center/right/decimal stops have geometric tests
```

## F-012 gcode regeneration

```text
DONE:
contract explicitly defined and tested
```

## F-013 paginator

```text
DONE:
at least the highest-value cohesive responsibilities extracted safely,
or block explicitly deferred if regression risk is higher than benefit
```

---

# Приоритет выполнения

Строго рекомендуемый порядок:

```text
1. F-001 PDF centerline/math crash
2. F-002 CLI exit codes
3. F-003 VML arrows
4. F-004 A4/workspace preflight

5. F-005 centerline worst glyphs

6. F-006 handwriting/simplification performance

7. F-007 DOCX extract
8. F-011 tab semantics
9. F-010 connection-mode distinction

10. F-009 report observability
11. F-008 deterministic paths.json
12. F-012 gcode regeneration contract

13. F-013 paginator cleanup

14. full integration rerun
```

Причина порядка:

- сначала убрать hard failures;
- затем исправить самые заметные ошибки результата;
- затем улучшать скорость;
- затем закрыть fidelity/observability;
- рефакторинг делать только после сильного regression coverage.

---

# Что НЕ делать в UPD_Plotter_11

Не выполнять следующие работы без отдельного нового finding:

- OCR для PDF;
- нейросеть для centerline;
- новый font engine;
- переписывание PDF math detector;
- полная замена paginator;
- полная замена Word parser;
- глобальная настройка centerline thresholds;
- удаление strict quality checks;
- искусственное расширение machine workspace;
- поддержка десятков новых DrawingML/SmartArt элементов;
- redesign font cache;
- физическая оптимизация `balanced/fast` без калибровки реального устройства.

Главный принцип этого этапа:

> Сначала сделать существующий основной pipeline правильным, качественным, быстрым и измеримым. Только после этого расширять feature set.

---

# Что Codex должен сообщать после каждого блока

После блока вывести пользователю краткое резюме:

```text
Блок N завершён.

Исправлено:
- ...

Root cause:
- ...

Изменённые файлы:
- ...

Добавленные regression tests:
- ...

Проверки:
lint: ...
test: ...
smoke: ...

До:
...

После:
...

Оставшиеся ограничения:
...
```

Если проблема не исправлена полностью — не писать `завершено`.

Написать:

```text
PARTIAL
```

и явно объяснить, что осталось.

---

# Финальный отчёт UPD_Plotter_11

После завершения всех работ создать:

```text
docs/UPD_Plotter_11_FINAL_REPORT.md
```

Структура:

```text
# UPD_Plotter_11 Final Report

## 1. Base commit
## 2. Final commit / working tree
## 3. Summary
## 4. Fixed findings
## 5. Partially fixed findings
## 6. Deferred findings
## 7. Regression tests added
## 8. DOCX full pipeline result
## 9. PDF preserve result
## 10. PDF reflow result
## 11. Centerline quality before/after
## 12. Connection quality before/after
## 13. Performance before/after
## 14. A4/A5 behavior
## 15. Report/observability improvements
## 16. Determinism
## 17. G-code safety
## 18. Remaining TOP problems
## 19. Recommendation for UPD_Plotter_12
```

В финале обязательно привести таблицу:

| Finding | Before | After | Status |
|---|---|---|---|
| F-001 | PDF crash | ... | fixed/partial |
| F-002 | exit 0 on error | ... | ... |
| F-003 | 1/3 arrows | ... | ... |
| F-004 | late A4 failure | ... | ... |
| F-005 | 12 needs_review | ... | ... |
| F-006 | ~126.7 s warm | ... | ... |
| F-007 | extract incomplete | ... | ... |
| F-008 | paths bytes differ | ... | ... |
| F-009 | missing/fake metrics | ... | ... |
| F-010 | safe=aggressive | ... | ... |
| F-011 | tabs approximated | ... | ... |
| F-012 | gcode comments differ | ... | ... |
| F-013 | paginator monolith | ... | ... |

Не скрывать regressions и не менять статус finding на `fixed`, если acceptance criteria не выполнены.
