# UPD_Plotter_12 — ускорение centerline-компиляции и полного document pipeline

## 0. Контекст и цель

Работать с веткой:

```text
ref
```

Аудит, на котором основан этот план:

```text
report/REPORT.md
report/TECH_DEBT.md
report/summary.json
report/commands.log
```

Аудированный HEAD:

```text
47524e25b0ec3634c4460df001e3d52f10a72ce0
```

Перед началом Codex обязан выполнить:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -5 --oneline
```

Если текущий HEAD ветки `ref` уже отличается от аудированного, это не ошибка. Нужно зафиксировать новый HEAD в отчёте и проверить, какие части этого плана уже реализованы.

### Текущее подтверждённое состояние

Quality gates:

```text
lint: passed
tests: 268 passed
smoke: passed
determinism: passed
G-code safety: passed
```

Warm conversion для полного контрольного DOCX:

```text
66.221 s
61.858 s
61.779 s

median = 61.858 s
```

Основные горячие стадии полностью прогретого запуска:

```text
handwriting     ≈ 27.8 s
simplification  ≈ 20.2 s
build_paths      ≈ 8.6 s
```

То есть эти три стадии занимают почти весь пользовательский wall time.

Cold centerline compilation остаётся ещё более серьёзной проблемой:

```text
полный cold compile 169 glyphs
не завершился за 13+ минут
```

Warm font cache при этом работает нормально:

```text
169 glyphs
122 hits
0 misses
~18.4 MB
font_compile warm ≈ 1.5 s
```

---

# Главная цель UPD_Plotter_12

Сфокусироваться прежде всего на скорости.

Не добавлять большие новые пользовательские функции, пока не выполнены performance goals.

## Целевые ориентиры

Это не повод ухудшать качество ради цифры. Цели действуют только при сохранении geometry/semantic behaviour.

### Warm full-document conversion

Первый обязательный milestone:

```text
median <= 30 s
```

Целевая величина:

```text
median <= 20–25 s
```

Stretch goal:

```text
<= 15 s
```

на той же машине и том же контрольном документе.

### Cold compilation полного font corpus

Первый milestone:

```text
< 5 min
```

Цель:

```text
< 2 min
```

для тех же 169 glyphs на той же машине.

Если после профилирования станет ясно, что этот target нереален без ухудшения качества, зафиксировать фактический lower bound и причины.

### Partial cold compile

Обычный документ НЕ должен ждать компиляции всего font corpus.

Если документ реально использует, например, 40 уникальных символов:

```text
компилировать только эти 40 misses
```

и сохранять их сразу в reusable cache.

---

# Жёсткие правила performance-работ

## Правило 1 — никакой оптимизации без benchmark before/after

Каждый performance-блок должен иметь:

```text
before
after
median
stage timings
percentage change
output equivalence
```

## Правило 2 — качество не разменивать на скорость

Нельзя просто:

- уменьшить centerline resolution;
- увеличить simplification tolerance;
- ослабить collision validation;
- выключить medial/skeleton candidate;
- отключить preview;
- выключить semantic processing;

и считать это ускорением основного pipeline.

Такие режимы можно исследовать только как отдельный optional fast mode после основного correctness-preserving ускорения.

## Правило 3 — сначала убрать лишнюю работу

Порядок оптимизаций:

```text
1. не выполнять вычисление вообще, если оно не нужно;
2. не выполнять одно и то же вычисление дважды;
3. cache/reuse;
4. улучшить алгоритмическую сложность;
5. vectorization / compiled libraries;
6. parallelism;
7. только затем lower-level micro-optimization.
```

## Правило 4 — детерминизм обязателен

Параллелизация не должна менять:

```text
paths.json
page G-code
preview
accepted/rejected connections
warnings order
page order
```

Если timestamps/runtime поля различаются — это допустимо.

---

# БЛОК 1. Создать нормальную performance instrumentation

Перед серьёзными изменениями нужно получить function-level profile.

Сейчас отчёт показывает только stage-level время:

```text
handwriting
simplification
build_paths
```

Этого недостаточно.

---

## 1.1. Добавить штатный performance profile mode

Не делать profiler постоянной обязательной зависимостью runtime.

Добавить dev/audit инструмент, например:

```text
tools/profile_conversion.py
```

или расширить:

```text
tools/benchmark_conversion.py
```

Он должен уметь:

```bash
--profile
--profile-stage handwriting
--profile-stage simplification
--profile-stage build_paths
--profile-stage font_compile
```

Минимум поддержать `cProfile`.

Если доступен более удобный profiler без новой обязательной dependency, можно использовать его дополнительно.

---

## 1.2. Per-page timings

Сейчас 20 страниц агрегируются в общую цифру.

Добавить в performance report:

```text
page
glyph_count
stroke_count_before
point_count_before
candidate_pairs
accepted_connections

build_paths_ms
variation_ms
word_routing_ms
simplification_ms
serialization_ms
preview_ms
gcode_ms
```

Цель — увидеть:

- какие страницы самые медленные;
- зависимость от glyph count;
- зависимость от points;
- зависимость от connection candidates.

---

## 1.3. Per-function top list

Для каждого главного stage получить минимум TOP-20:

```text
function
calls
self time
cumulative time
time/call
```

---

## 1.4. Отдельный cold glyph profiler

Добавить возможность профилировать:

```text
один glyph
10 glyphs
полный corpus
```

Для каждого glyph:

```text
render
mask
label/components
distance transform
candidate 1
candidate 2
spur pruning
graph build
graph simplify
routing
smoothing
quality
serialization
```

---

## Definition of Done блока 1

Должно быть возможно одной командой получить:

```text
warm conversion profile
cold font profile
per-page timings
per-glyph timings
```

Именно эти данные использовать во всех следующих блоках.

---

# БЛОК 2. Ускорить handwriting — сейчас ~27.8 s

Это крупнейший warm bottleneck.

Основной файл:

```text
src/plotter_processor/handwriting.py
```

---

## 2.1. Самое важное — cheap rejection ДО дорогой geometry

Сейчас `_connection_candidate()` сначала делает значительную дорогую работу:

```text
contact search
Bezier connector generation
backtracking sampling
corridor calculation
collision calculation
```

а затем уже проверяет:

```text
different_line
punctuation_rule
not_letters
anchor_not_routeable
distance
vertical_offset
backward_motion
tangent_mismatch
```

Это неправильный порядок с точки зрения performance.

На основном DOCX:

```text
pairs_total ≈ 5747
accepted ≈ 1359
```

То есть большая часть кандидатов в итоге отклоняется.

Для них нельзя заранее выполнять collision scan, если уже известно, что:

```text
gap > max_join_gap
```

или:

```text
vertical > max_vertical
```

или пара запрещена punctuation rule.

### Требуемый порядок

Перестроить `_connection_candidate()` на pipeline:

```text
LEVEL 0
валидность left/right/main/anchors

LEVEL 1 — почти бесплатные проверки
different line
punctuation
letters-only
routeable anchors

LEVEL 2 — O(1) geometry
gap
vertical offset
direction/backtracking preliminary
tangent mismatch

LEVEL 3
contact/snap check

LEVEL 4
Bezier generation

LEVEL 5
corridor check

LEVEL 6 — самое дорогое
collision query
segment distance tests
```

Если пара отклонена на LEVEL 1/2:

```text
LEVEL 3–6 вообще не выполнять
```

### Важное требование

Сохранить текущий приоритет rejection reasons.

Если раньше пара классифицировалась как:

```text
distance
```

она не должна после оптимизации внезапно стать:

```text
collision
```

только из-за смены порядка.

---

## 2.2. Debug geometry строить только когда она реально нужна

Сейчас `route_words()` формирует:

```text
debug_candidates
```

для каждой пары.

Но обычный benchmark запускается без:

```text
--connection-debug
```

Добавить параметр:

```python
collect_debug: bool = False
```

или аналогичный.

В production fast path:

```text
connection debug data не строить
не хранить full curve arrays для rejected cheap candidates
не сериализовать debug metadata
```

Если включён `--connection-debug`, сохранить прежнюю полноту diagnostics.

---

## 2.3. Не хранить `connection_debug` metadata в обычном paths.json

Проверить текущую ветку:

```text
route_words()
→ result.metadata["connection_debug"]
```

Убедиться, что при обычном run без debug:

```text
это поле отсутствует
```

Это уменьшит:

- allocation;
- memory;
- JSON serialization;
- размер `paths.json`.

---

## 2.4. Segment-level obstacle index

Текущий spatial index индексирует strokes по bbox.

Но после query collision loop всё равно делает:

```text
для каждого curve point
    для каждого nearby stroke
        для каждого segment этого stroke
```

Для длинного stroke это всё ещё дорого.

Заменить/дополнить индексом сегментов:

```text
SegmentObstacle:
    stroke_id
    segment_index
    p1
    p2
    bbox
```

Spatial cells должны содержать segment IDs.

Тогда collision query получает только те segments, которые реально находятся возле connector bbox.

### Сохранить семантику

Особые правила игнорирования:

```text
left stroke near start
right stroke near end
boundary_ignore
```

должны остаться.

---

## 2.5. Batch/vectorized distance tests

После segment-level filter проверить profiler.

Если `_point_segment_distance()` всё ещё занимает значимое время:

- собрать curve points в NumPy arrays;
- собрать candidate segments;
- вычислять distance batch/vectorized;

либо использовать более эффективный segment/curve distance algorithm.

Не подключать тяжёлую geometry framework без измеренного выигрыша.

---

## 2.6. Cache stroke classification и anchors

Для каждого glyph сейчас во время route_words выполняются:

```text
classify_strokes()
_orient_for_anchors()
entry_exit_anchors()
```

Проверить, не вычисляется ли одна и та же информация повторно для одного и того же glyph instance.

Создать ephemeral per-page cache:

```text
glyph_index
→ classified main stroke
→ oriented main
→ entry
→ exit
→ bbox
```

Этот cache не должен попадать в persistent artifacts.

---

## 2.7. Benchmark блока

Сделать microbenchmark отдельно:

```text
route_words only
```

на:

```text
1 page
5 pages
20 pages
```

Обязательно сравнить:

```text
accepted
rejected
reasons
connector coordinates
final paths
```

### Цель блока 2

Желательно:

```text
27.8 s → < 10 s
```

Первый acceptable milestone:

```text
< 15 s
```

---

# БЛОК 3. Ускорить simplification — сейчас ~20.2 s

Основной файл:

```text
src/plotter_processor/path_simplifier.py
```

Текущий RDP реализован в Python и для каждого interval сканирует points циклом.

---

## 3.1. Сначала выяснить реальную complexity на текущем document

Добавить metrics:

```text
stroke count
points before
points after
max points in one stroke
median points/stroke
95 percentile points/stroke
```

Особенно сравнить:

```text
до route_words
после route_words
```

Гипотеза: объединение glyphs в длинные word-strokes делает RDP значительно дороже.

---

## 3.2. Не упрощать один и тот же glyph тысячи раз

Большая часть текста состоит из повторяющихся glyph shapes.

Сейчас pipeline:

```text
compiled glyph
→ размножить по всем occurrences
→ variation
→ join words
→ RDP всего document
```

Исследовать двухступенчатую simplification.

### Stage A — glyph template simplification

До размещения/word joining:

```text
каждый уникальный glyph stroke
```

упрощать один раз.

Ключ cache:

```text
font hash
centerline config
glyph
effective scale / size
simplification tolerance
```

Так как translation и rotation не меняют RDP geometry, их не нужно включать в key.

Для uniform scale учитывать tolerance корректно:

```text
font-unit tolerance = mm tolerance / scale
```

### Stage B — post-join lightweight simplification

После создания connectors:

- не гонять полный RDP заново по всем glyph points;
- упрощать только connector/new boundary sections;
- либо использовать значительно более лёгкий final dedupe.

---

## 3.3. Conservative error budget при handwriting scale jitter

Variation может менять scale.

Чтобы pre-simplification не превысила текущий:

```text
max_deviation_mm
```

использовать conservative tolerance относительно максимального возможного scale jitter.

Например принцип:

```text
template_epsilon =
final_epsilon / max_possible_variation_scale
```

Точную формулу получить из текущей config.

---

## 3.4. Оптимизировать сам RDP

Даже после template reuse RDP останется нужен для graphics/connectors.

Текущий inner loop на Python:

```text
for index in range(start + 1, end):
    ...
    math.hypot(...)
```

Исследовать:

### Вариант A — NumPy vectorized interval distance

Для больших intervals:

```text
xs
ys
projection
distance_squared
argmax
```

vectorized.

### Вариант B — специализированная библиотека

Только если dependency лёгкая и benchmark показывает заметный выигрыш.

### Вариант C — compiled optional accelerator

Numba/Cython/Rust только после A/B и только если оправдано.

Не делать compiled extension первым шагом.

---

## 3.5. Работать с squared distance

В inner loop не нужен `sqrt`, пока сравнивается максимум.

Использовать:

```text
distance_squared
epsilon_squared
```

и извлекать sqrt только для итогового `observed`, если это необходимо report.

---

## 3.6. Fast path для коротких strokes

Если:

```text
len(points) <= threshold
```

или bbox/point geometry уже гарантированно проста, не запускать полноценный RDP machinery.

Threshold определить benchmark'ом.

---

## 3.7. Regression geometry

Для каждого варианта сравнить с текущим output.

Требование:

```text
max geometric deviation <= текущего configured max_deviation_mm
```

На аудите ориентир:

```text
<= 0.06 mm
```

Также не должны измениться:

```text
stroke topology
closed/open
semantic roles
word connections
```

### Цель блока 3

Желательно:

```text
20.2 s → < 5 s
```

Первый milestone:

```text
< 8 s
```

---

# БЛОК 4. Ускорить build_paths — сейчас ~8.6 s

Для centerline основная функция:

```text
build_centerline_paths()
```

Она для каждого occurrence каждого glyph создаёт новый Python `Point` для каждой точки cached centerline.

---

## 4.1. Кеш transformed glyph templates

Многие glyph occurrences имеют одинаковый:

```text
char
scale_mm_per_font_unit
```

До translation.

Создать per-run cache:

```text
(char, scale)
→ tuple/list local transformed points in mm
```

То есть один раз вычислить:

```text
x_local = point.x * scale
y_local = -point.y * scale
```

Для каждого occurrence остаётся только translation:

```text
x = glyph.x + x_local
y = baseline + y_local
```

---

## 4.2. Совместить с pre-simplified templates

Если блок 3 вводит template simplification, build_paths должен использовать уже:

```text
transformed + simplified template
```

а не исходные oversampled cached centerline points.

Это должно уменьшить одновременно:

```text
build_paths
handwriting collision segment count
simplification
JSON size
G-code generation
```

То есть этот блок имеет downstream effect.

---

## 4.3. Не создавать лишние copies

Профилировать:

```text
list(...)
replace(...)
tuple concatenation
Point allocation
source_glyph_indices copies
segment_types copies
```

Оптимизировать только после measurement.

---

## 4.4. Возможный packed internal representation

Только если после template caching build_paths всё ещё >3–4 s.

Рассмотреть внутреннее представление points как:

```text
Nx2 numpy array
```

на hot stages.

Конвертировать в `Point` objects только на boundary API/artifact serialization.

Это уже более серьёзная архитектурная оптимизация.

НЕ делать её до измерения эффекта blocks 2–4.

---

## Цель блока 4

```text
8.6 s → < 2–3 s
```

---

# БЛОК 5. Параллельная обработка страниц

После локальных алгоритмических оптимизаций включить CPU parallelism.

Контрольный документ:

```text
20 pages
```

После pagination страницы в основном независимы.

Сейчас pipeline обрабатывает их последовательно.

---

## 5.1. Выделить pure-ish `process_page()`

Из pipeline вынести функцию уровня:

```text
input:
    PageLayout
    compiled font / font templates
    page config
    joining config
    simplification config
    machine config

output:
    PageJob
    page report
    artifacts payload
```

Функция не должна мутировать общие global structures.

---

## 5.2. Parallel workers

Так как hot stages содержат много Python loops, `ThreadPoolExecutor` может не дать реального ускорения из-за GIL.

Исследовать:

```text
ProcessPoolExecutor
```

или multiprocessing.

Количество workers:

```text
--workers auto
--workers N
--workers 1
```

Default `auto` после стабилизации.

---

## 5.3. Ограничить RAM

Не запускать автоматически:

```text
workers = cpu_count
```

если каждый worker несёт большие path objects.

Сделать разумный cap.

Например initial policy:

```text
min(cpu_count, 4)
```

с возможностью override.

Но финальную политику определить измерением RAM.

---

## 5.4. Детерминированное merge

Workers могут завершаться в любом порядке.

Итог всегда собирать:

```text
sorted(page_index)
```

Warning/report ordering также должен быть стабильным.

---

## 5.5. Artifact writing

Каждый worker может писать только в собственный:

```text
pages/page-XXX/
```

Корневые:

```text
job.json
root preview
root G-code
report.json
```

формировать после merge в главном процессе.

---

## 5.6. Regression

Сравнить:

```text
workers=1
workers=2
workers=4
```

Ожидание:

```text
paths byte-identical
page gcode byte-identical
preview byte-identical
same warnings
same connection metrics
same semantic metrics
```

---

## Цель блока 5

После blocks 2–4 и page parallelism full warm wall должен выйти минимум в:

```text
<= 30 s
```

Цель:

```text
<= 20–25 s
```

---

# БЛОК 6. Радикально ускорить cold centerline compilation

Это отдельная проблема от warm document conversion.

Основные файлы:

```text
src/plotter_processor/centerline_font/compiler.py
src/plotter_processor/centerline_font/skeleton_selector.py
src/plotter_processor/centerline_font/skeletonizer.py
src/plotter_processor/centerline_font/cache.py
```

---

## 6.1. Per-glyph profiling до изменений

Для representative glyphs:

```text
.
:
;
?
а
ж
ф
щ
Ш
Щ
Ю
U
```

получить breakdown.

Не оптимизировать вслепую.

---

## 6.2. Убрать повторный EDT/label между skeleton candidates

Сейчас `select_best_skeleton()` в auto проходит по каждому method.

Каждый `build_skeleton()` заново вычисляет:

```python
ndimage.label(source)
ndimage.distance_transform_edt(source)
```

Но эти данные зависят только от ink mask, а не от метода skeletonization.

Нужно сделать shared preprocessing:

```text
SkeletonInput:
    source mask
    component labels
    component count
    distance transform
```

Один раз на glyph:

```text
preprocess mask
```

и передавать одинаковый result обоим candidates:

```text
medial_axis
skeletonize
```

### Требование

Output обоих algorithms должен быть побайтово/геометрически эквивалентен старому, кроме runtime metadata.

Это low-risk optimization.

---

## 6.3. Ускорить `prune_short_spurs()`

Текущая логика может много раз делать:

```text
degrees over whole raster
endpoint scans
candidate mask copies
coverage reconstruction
distance_transform_edt
```

Особенно дорого:

```text
_coverage_loss()
→ reconstruct_with_local_radius(before)
→ reconstruct_with_local_radius(after)
```

Для каждого tentative removal.

### Улучшение A — cache reconstruction before

Для одного pruning state:

```text
before reconstruction
```

считать один раз, а не заново для каждой ветви.

После accepted removal:

```text
cached before = accepted after
```

---

## 6.4. Локальный coverage delta вместо full-frame reconstruction

Исследовать возможность считать влияние удаления branch только в локальном ROI:

```text
branch bbox
+ max local radius
```

Вне ROI before/after идентичны.

Следовательно, не нужно делать full image EDT для каждой tentative branch.

### Очень важно

Результат `coverage_loss` должен совпадать со старым алгоритмом в пределах численной погрешности.

Добавить property/regression tests.

---

## 6.5. Не пересчитывать degrees целиком после локального удаления

После удаления короткой ветви degrees меняются только возле удалённых pixels/junction.

Вместо:

```text
ndimage.convolve(full mask)
```

каждую итерацию рассмотреть incremental/local update.

Если profiler показывает, что degree convolution незначительна на фоне EDT, оставить как есть.

---

## 6.6. Parallel glyph compilation

Сейчас:

```python
for char in missing:
    _compile_glyph(...)
```

идёт последовательно.

Glyphs полностью независимы до merge в `CompiledCenterlineFont`.

Добавить parallel compile.

### Рекомендуемый подход

```text
ProcessPoolExecutor
```

Worker должен:

1. один раз загрузить font;
2. получить char/config;
3. вернуть serializable CenterlineGlyph.

Не загружать TTF заново для каждого glyph внутри одного worker.

Использовать worker initializer или эквивалент.

---

## 6.7. Детерминированный merge glyph results

Независимо от completion order:

```text
sort by codepoint
```

перед merge/cache write.

Warnings также сортировать детерминированно.

---

## 6.8. Управление workers

Добавить:

```text
--centerline-workers auto|N
```

и config/API equivalent.

Начальный auto cap выбрать с учётом RAM.

2048px/em masks и skeleton arrays могут быть тяжёлыми.

Не допустить OOM ради скорости.

---

## 6.9. Частичный cache должен сохраняться во время долгого build

Сейчас полный cache по сути обновляется после завершения missing glyph loop.

Если process остановлен через 10 минут, уже вычисленные glyphs нельзя терять.

Сделать one of:

### Вариант A — per-glyph shard cache

```text
namespace/
    manifest.json
    glyphs/
        U+0041.json
        U+0042.json
        ...
```

### Вариант B — checkpoint batches

После каждых:

```text
N glyphs
```

атомарно обновлять cache.

Предпочтительнее sharded cache, если архитектурно аккуратно.

---

## 6.10. Cache schema v8

Если вводится sharded cache:

Identity должна по-прежнему включать:

```text
font SHA
algorithm version
centerline config fingerprint
glyph patches/overrides
```

Нельзя допустить использование glyph из другого algorithm fingerprint.

---

## 6.11. Warm loading тоже ускорить

Сейчас canonical cache порядка:

```text
18.4 MB JSON
```

Даже warm font compile ~1.5 s.

Sharded/indexed cache позволит загружать только:

```text
requested glyphs
```

вместо всего corpus.

Для документа с 40 chars не читать 169 glyphs и весь 18 MB файл.

---

## 6.12. Lazy glyph loading

`CompiledCenterlineFont` может хранить lightweight loader/index:

```text
char -> cache entry/path
```

и материализовывать glyph только при первом обращении.

Если это усложняет модели слишком сильно — оставить на второй этап после sharding.

---

## Цель блока 6

Полный 169-glyph cold build:

```text
first milestone < 5 min
target < 2 min
```

Partial 30–50 glyph cold document должен быть существенно быстрее полного corpus.

---

# БЛОК 7. Оптимизация выбора skeleton candidate без потери качества

Этот блок выполнять ПОСЛЕ shared-preprocessing/pruning/parallelism.

---

## 7.1. Проверить статистику победителей

На 169 glyph corpus собрать:

```text
glyph
candidate methods
score each
winner
score delta
quality
```

Посчитать:

```text
% medial_axis winners
% skeletonize winners
```

---

## 7.2. Fast-first candidate strategy

Если статистика показывает, что один method выигрывает подавляющее большинство glyphs, можно исследовать:

```text
primary candidate
→ quality/score confidence check
→ второй candidate только если результат пограничный
```

Но это нельзя внедрять только по performance.

Нужно доказать, что selection остаётся тем же на regression corpus.

---

## 7.3. Confidence criterion

Второй candidate можно пропускать только когда первый имеет явно хороший профиль:

```text
coverage
extra
topology
retrace
junction count
short edges
quality gate
```

Порог определить offline сравнением полного dual-candidate corpus.

---

## 7.4. Safe fallback

Для неизвестного/new font:

```text
если confidence недостаточен
→ считать оба candidates как сейчас
```

---

## 7.5. Не менять default resolution пока не исчерпаны безопасные оптимизации

`2048 px/em` не уменьшать в первых performance blocks.

Adaptive resolution можно исследовать только отдельным experimental benchmark:

```text
1024 → quality gate → 2048 fallback
```

и только если golden geometry/quality это допускают.

Не делать это обязательным default в UPD_Plotter_12 без убедительных доказательств.

---

# БЛОК 8. Убрать лишнюю работу и I/O из обычного run

Когда hot CPU stages станут быстрее, вторичные расходы станут заметнее.

---

## 8.1. Font preview cache

Сейчас каждый run формирует:

```text
font-preview.svg
centerline-font-preview.svg
```

Эти previews зависят в основном от font/cache/config, а не от document output directory.

Добавить reusable preview cache по fingerprint.

При cache hit:

```text
copy/link existing preview
```

или не генерировать его повторно.

---

## 8.2. Artifact levels

Сохранить хороший default UX, но разделить:

```text
normal
debug
audit
```

### normal

Обязательно:

```text
output.gcode
plotter-preview.svg
report.json
job.json
paths.json
```

### debug

Добавляет:

```text
font preview
centerline preview
connection debug
layout debug
semantic debug
math debug
image debug
```

Если текущий UX требует font previews всегда, сначала измерить их цену. Не убирать без причины.

---

## 8.3. Не строить debug data при disabled debug

Проверить все subsystems:

```text
connection
layout
semantic
math
image
centerline
```

На обычном run не должны создаваться крупные промежуточные debug structures, если они потом не сохраняются.

---

## 8.4. JSON serialization

После снижения point count проверить долю:

```text
save_path_document
report writing
job manifest
```

Если это >5–10% runtime:

- использовать более компактный writer;
- не делать лишние intermediate dict copies;
- не сериализовать duplicate metadata per page.

Не менять публичный format без version bump.

---

# БЛОК 9. Incremental document cache

Это не главный первый optimization, но полезно для повторных прогонов одного документа.

---

## 9.1. Cache source parsing

Key:

```text
input SHA256
reader version
relevant import options
```

Cache:

```text
structured document model
source layout
extracted asset identities
```

---

## 9.2. Cache pagination/layout

Key должен включать:

```text
source model hash
page
size
document layout mode
font metrics identity
paragraph/layout config fingerprint
```

Не включать machine motion config, если он не влияет на layout.

---

## 9.3. Cache pre-handwriting page paths

Для same document/font/layout:

```text
base glyph paths + graphics
```

можно reuse между motion-profile runs.

Handwriting config и variation seed должны входить в следующий-stage key.

---

## 9.4. Stage cache graph

Желательно оформить dependency chain:

```text
source bytes
  ↓
parsed document
  ↓
paginated layout
  ↓
base paths
  ↓
handwriting
  ↓
simplification
  ↓
G-code
```

При изменении только:

```text
motion profile
```

не повторять всё сверху.

---

# БЛОК 10. PDF semantic reconstruction — техдолг P1

Performance — главный приоритет, но после speed blocks закрыть наиболее важный quality debt из нового отчёта.

Аудит:

```text
PDF preserve: 40 warnings
PDF reflow:   40 warnings
```

Причины:

```text
low-confidence math candidates
rasterized complex drawings
```

---

## 10.1. Создать маленький размеченный PDF corpus

Категории:

```text
normal text
inline math
block math
table
arrow
underline
diagram
complex drawing
raster image
```

Для каждого region иметь expected semantic class.

---

## 10.2. Метрики math detector

Добавить:

```text
precision
recall
false positives
false negatives
absorbed primitive count
```

Не снижать warning threshold просто для уменьшения числа warnings.

---

## 10.3. Golden preserve/reflow previews

Нужны visual regression fixtures.

Особенно:

```text
preserve source overlaps
reflow zero-overlap
formula suppression
drawing rasterization
```

---

# БЛОК 11. Semantic duplicate suppression — техдолг P2

Сейчас:

```text
duplicate_primitives_suppressed = null
measured = false
```

Это честнее fake-zero, но pipeline ещё не измеряет эту часть.

---

## 11.1. Формальный duplicate contract

Разделить:

```text
exact duplicate
near duplicate
shared table border
intentional overlap
```

Не смешивать эти классы.

---

## 11.2. Измеряемый suppression pass

Добавить counters:

```text
exact_duplicates_seen
exact_duplicates_suppressed
near_duplicates_seen
near_duplicates_suppressed
```

Near duplicate не подавлять автоматически без безопасного критерия.

---

# БЛОК 12. Connection corpus — показать разницу safe/aggressive

Аудит:

```text
safe       105 / 510
aggressive 105 / 510
```

Geometry одинаковая.

Targeted unit fixture уже показывает difference, но пользовательский corpus — нет.

Добавить несколько реальных слов/пар, где:

```text
gap
vertical
tangent
```

лежат между safe и aggressive thresholds.

Требование:

```text
safe output hash != aggressive output hash
```

на специальном corpus.

Collision/punctuation safety в aggressive не отключать.

---

# БЛОК 13. Make audit

Аудит сейчас воспроизводим через `commands.log`, но не одной командой.

Добавить:

```bash
make audit
```

Он должен:

1. создать temp output root;
2. выполнить lint/test/smoke;
3. выполнить короткую integration matrix;
4. выполнить warm benchmark;
5. выполнить safety scanner;
6. агрегировать summary;
7. сохранить compact report;
8. удалить тяжёлые temporary outputs.

Не делать full 169 cold compile частью обычного `make audit`.

Для него отдельная команда:

```bash
make benchmark-font-cold
```

---

# БЛОК 14. Paginator cleanup — только после performance

`document_paginator.py` всё ещё примерно 1972 строки.

Не делать его рефакторинг одновременно с hot-path optimization.

После speed blocks можно аккуратно вынести:

```text
text placement
table placement
math placement
page state/debug orchestration
```

по одному responsibility.

Каждый extraction обязан оставлять:

```text
byte-identical paths
byte-identical previews
byte-identical G-code
```

для integration fixture.

---

# БЛОК 15. Разбить большой dirty diff на логические commits

Новый аудит отмечает integration risk:

```text
большой незакоммиченный набор изменений UPD_Plotter_11
```

Перед дальнейшими крупными performance changes привести историю в состояние, пригодное для bisect.

Рекомендуемые логические группы:

```text
fixes correctness
centerline quality
performance baseline
report/observability
determinism
paginator cleanup
audit artifacts
```

Не делать один огромный commit UPD_Plotter_12.

---

# БЛОК 16. Финальный benchmark matrix

После завершения speed blocks повторить исходный benchmark на той же машине.

---

## 16.1. Warm DOCX

Минимум:

```text
5 warm runs
```

Не один.

Считать:

```text
min
median
p90/max
```

---

## 16.2. Stage comparison

Таблица:

| Stage | Before | After | Improvement |
|---|---:|---:|---:|
| font_compile warm | ~1.5 s | ... | ... |
| build_paths | ~8.6 s | ... | ... |
| handwriting | ~27.8 s | ... | ... |
| simplification | ~20.2 s | ... | ... |
| total | 61.858 s median | ... | ... |

---

## 16.3. Cold font

Изолированный temporary cache:

```text
full 169 glyph
```

Запустить минимум:

```text
1 cold
```

Также:

```text
20 glyphs
50 glyphs
169 glyphs
```

Построить scaling table.

---

## 16.4. Worker scaling

Для document:

```text
workers=1
workers=2
workers=4
workers=auto
```

Для font:

```text
centerline-workers=1
2
4
auto
```

Записать:

```text
wall time
CPU time
peak RAM
speedup
efficiency
```

---

# БЛОК 17. Quality equivalence gate

Performance improvement считается успешным только если сравнение с baseline проходит.

---

## 17.1. Geometry

Для каждой страницы:

```text
stroke count
component count
closed/open
semantic role
```

Если coordinates не byte-identical из-за нового simplifier:

```text
max deviation <= 0.06 mm
```

или более строгий текущий contract.

---

## 17.2. Connections

Должны совпасть:

```text
pairs_total
accepted
rejected
rejection reasons
snapped_existing_contact
connector length
```

если optimization не меняла connection policy.

---

## 17.3. Centerline

Для full corpus:

```text
selected skeleton method
needs_review
coverage
retrace
component count
route count
```

не должны ухудшиться.

Если candidate fast-path меняет selected method — это отдельное quality decision, а не просто optimization.

---

## 17.4. Determinism

Повторить два runs.

Требовать byte identity:

```text
paths.json
page.gcode
page previews
root G-code
root preview
```

---

## 17.5. G-code safety

Повторить независимый scanner:

```text
0 heating
0 G28
0 extrusion
0 NaN/Inf
0 XY workspace violations
0 unexpected Z
```

---

# Рекомендуемый порядок реализации

Строго:

```text
BLOCK 1   instrumentation/profile

BLOCK 2   handwriting cheap rejection/debug fast path
BLOCK 3   simplification/template reuse
BLOCK 4   build_paths template cache

BLOCK 5   page parallelism

BLOCK 6   cold font shared preprocessing/pruning/parallel glyph compile/cache
BLOCK 7   optional skeleton candidate fast-first

BLOCK 8   debug/I/O cleanup
BLOCK 9   incremental document cache

BLOCK 10  PDF semantic debt
BLOCK 11  duplicate metrics
BLOCK 12  connection corpus
BLOCK 13  make audit
BLOCK 14  paginator cleanup
BLOCK 15  commit cleanup

BLOCK 16–17 final benchmark + equivalence gate
```

---

# Что я ожидаю получить после первых 6 блоков

Именно это является главным результатом UPD_Plotter_12.

## Warm document

Текущий:

```text
~61.9 s
```

После алгоритмических optimizations до parallelism желательно:

```text
~25–35 s
```

После page parallelism:

```text
~15–25 s
```

Конкретный результат зависит от CPU.

---

## Cold font

Текущий:

```text
>13 min
```

После:

```text
shared EDT/labels
optimized pruning
parallel glyph workers
incremental/sharded cache
```

ожидается многократное ускорение.

Главная цель — убрать ситуацию, когда пользователь на новой машине может ждать centerline font десятки минут.

---

# Особо важные конкретные точки кода для Codex

Проверить в первую очередь:

```text
src/plotter_processor/handwriting.py
    route_words()
    _connection_candidate()
    _collision_points()
    _StrokeObstacleIndex

src/plotter_processor/path_simplifier.py
    simplify_path_document()
    _rdp_with_deviation()

src/plotter_processor/centerline_path_builder.py
    build_centerline_paths()

src/plotter_processor/pipeline.py
    per-page sequential loops
    build_paths timing
    handwriting timing
    simplification timing

src/plotter_processor/centerline_font/compiler.py
    compile_centerline_font()
    _compile_glyph()

src/plotter_processor/centerline_font/skeleton_selector.py
    select_best_skeleton()

src/plotter_processor/centerline_font/skeletonizer.py
    build_skeleton()
    prune_short_spurs()
    _coverage_loss()
    reconstruct_with_local_radius()

src/plotter_processor/centerline_font/cache.py
```

---

# Что НЕ делать

В этом обновлении не надо:

- переходить на нейросеть для centerline;
- переписывать проект на другой язык целиком;
- снижать качество rasterization;
- уменьшать 2048 px/em просто ради benchmark;
- отключать collision validation;
- увеличивать simplification tolerance;
- выключать safe mode;
- удалять semantic processing;
- заменять весь paginator;
- ставить десятки новых тяжёлых dependencies;
- делать GPU обязательным;
- хранить cache внутри build;
- удалять canonical cache в benchmark;
- делать page/glyph parallelism недетерминированным.

---

# Performance regression tests

Добавить быстрые tests/benchmarks, которые не зависят от wall time обычного CI слишком жёстко.

## Algorithmic counters

Для handwriting проверить:

```text
cheap_rejected_pairs
beziers_built
collision_queries
segments_tested
```

Например:

```text
если 1000 пар отсекаются distance rule,
collision_queries для них = 0
```

Это более стабильный regression test, чем `time < X`.

---

## Simplifier

Проверить:

```text
unique templates simplified
glyph occurrences reused
post-join strokes processed
```

---

## Font compiler

Проверить:

```text
distance_transform calls per glyph
```

В auto с двумя candidates shared EDT должен вычисляться один раз.

Проверить parallel merge determinism.

---

# Отчёт после каждого блока

Создавать:

```text
docs/UPD_Plotter_12_block_<N>_report.md
```

Структура:

```text
# Block N

## Baseline
## Profile evidence
## Root cause
## Changes
## Tests
## Benchmark before
## Benchmark after
## Geometry/quality comparison
## Regressions
## Remaining bottleneck
```

После каждого performance-блока обязательно сообщать пользователю:

```text
Было:
handwriting 27.8 s

Стало:
handwriting X s

Ускорение:
Y%

Полный warm:
61.9 s → Z s

Quality:
identical / max deviation ...
```

Не писать просто:

```text
"оптимизировано"
```

---

# Финальный файл

После UPD_Plotter_12 создать:

```text
docs/UPD_Plotter_12_FINAL_REPORT.md
```

В нём:

```text
1. Base HEAD
2. Final HEAD
3. Hardware / Python / workers
4. Warm benchmark before/after
5. Cold font benchmark before/after
6. Handwriting profile before/after
7. Simplifier profile before/after
8. Build paths before/after
9. Page parallel scaling
10. Font worker scaling
11. Cache design
12. Quality equivalence
13. Determinism
14. G-code safety
15. Remaining performance bottlenecks
16. Remaining technical debt
17. Recommendation for UPD_Plotter_13
```

Обязательная итоговая таблица:

| Metric | Before | After | Improvement |
|---|---:|---:|---:|
| Warm full DOCX median | 61.858 s | ... | ... |
| Handwriting | ~27.8 s | ... | ... |
| Simplification | ~20.2 s | ... | ... |
| Build paths | ~8.6 s | ... | ... |
| Warm font compile | ~1.5 s | ... | ... |
| Cold 20 glyphs | ... | ... | ... |
| Cold 50 glyphs | ... | ... | ... |
| Cold 169 glyphs | >13 min / incomplete | ... | ... |
| Peak RAM | ... | ... | ... |

---

# Главный критерий успеха

UPD_Plotter_12 считается успешным не тогда, когда код выглядит "оптимизированным", а когда:

```text
полный document pipeline стал заметно быстрее;
новый font перестал компилироваться непрактично долго;
повторные runs используют reusable work;
результат визуально и геометрически не ухудшился;
детерминизм и G-code safety сохранились.
```
