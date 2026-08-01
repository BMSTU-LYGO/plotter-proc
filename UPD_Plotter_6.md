# UPD_Plotter_6

## Подробная инструкция для Codex: качество centerline, соединение букв и поддержка математических символов/рисунков

Рабочий репозиторий: `https://github.com/BMSTU-LYGO/plotter-proc`  
Базовая ветка: `master`  
Рекомендуемая рабочая ветка: `upd/plotter-6-quality-connections-assets`  
Имя итогового документа: `UPD_Plotter_6.md`

> Важно: перед началом работы Codex обязан обновить `master`, записать фактический SHA базового commit в отчёт и адаптировать названия файлов, если структура репозитория изменилась после составления этого плана.

---

# 0. Главная цель обновления

В этом обновлении нужно последовательно решить три задачи:

1. Улучшить качество центральной линии сложных букв, в первую очередь кириллических `ъ`, `ь`, `ы` в шрифте Pacifico.
2. Улучшить соединение букв внутри слов и уменьшить количество подъёмов ручки между соседними буквами.
3. Начать поддержку специальных объектов: математических Unicode-символов и векторных рисунков.

Работу выполнять тремя отдельными блоками. После каждого блока Codex должен:

- остановиться;
- выполнить все тесты;
- создать демонстрационные артефакты;
- показать пользователю, что именно было изменено;
- сравнить результат с baseline;
- перечислить ограничения;
- не переходить к следующему блоку, пока результат текущего блока не описан пользователю.

Пользователь не должен получать отчёт в стиле «всё готово». Отчёт обязан содержать конкретные файлы, команды, метрики и ссылки/пути на SVG, JSON и G-code, по которым можно проверить результат.

---

# 1. Текущее состояние проекта, которое нужно учитывать

На текущем `master` уже существует centerline-pipeline:

```text
TTF glyph
  -> raster glyph
  -> binary ink mask
  -> skeletonize / medial_axis candidates
  -> skeleton graph
  -> graph simplification
  -> route planning
  -> smoothing
  -> centerline cache
  -> page paths
  -> SVG / paths.json / G-code
```

В проекте уже присутствуют:

- `src/plotter_processor/centerline_font/compiler.py`;
- `src/plotter_processor/centerline_font/glyph_renderer.py`;
- `src/plotter_processor/centerline_font/skeleton_selector.py`;
- `src/plotter_processor/centerline_font/graph_simplifier.py`;
- `src/plotter_processor/centerline_font/route_planner.py`;
- `src/plotter_processor/centerline_font/route_assembler.py`;
- `src/plotter_processor/centerline_font/stroke_smoother.py`;
- `src/plotter_processor/centerline_path_builder.py`;
- тесты centerline в `tests/test_centerline_*.py`.

Текущая конфигурация уже умеет:

- выбирать `skeletonize`, `medial_axis` или `auto`;
- удалять короткие ответвления;
- упрощать граф;
- строить один маршрут на связный компонент;
- разрешать повтор отдельных рёбер;
- использовать ограниченные `glyph_overrides`;
- сохранять метрики качества и предупреждения;
- создавать debug-артефакты для проблемных глифов.

При этом есть важные архитектурные ограничения:

1. Центрлайн компилируется по отдельному символу `char`, а не по фактическому shaped glyph.
2. `vector_layout.py` располагает символы только по ширине `hmtx advance`.
3. Kerning, GPOS и contextual substitutions не применяются.
4. `centerline_path_builder.py` переносит штрихи каждого глифа на страницу независимо.
5. Межбуквенное соединение как отдельный этап отсутствует.
6. При отсутствии символа в основном TTF pipeline завершается ошибкой.
7. Формат документа пока является текстовым: TXT, DOCX или PDF с текстовым слоем.
8. Поддержки SVG-объектов как элементов страницы пока нет.

Не пытаться исправить всё одним большим переписыванием. Каждый новый слой должен иметь отдельный интерфейс, тесты и возможность отключения.

---

# 2. Общие правила работы Codex

## 2.1. Подготовка Git

Выполнить:

```bash
git switch master
git pull --ff-only
git rev-parse HEAD
git status --short
git switch -c upd/plotter-6-quality-connections-assets
```

Если рабочее дерево не чистое:

- не удалять чужие изменения;
- не выполнять `git reset --hard`;
- перечислить найденные изменения;
- работать только после безопасного отделения пользовательских правок.

В итоговом отчёте указать:

```text
Base branch:
Base commit:
Working branch:
Python version:
OS:
```

## 2.2. Рекомендуемые коммиты

Не делать один огромный commit. Использовать небольшие законченные коммиты, например:

```text
test: add Pacifico centerline regression corpus
feat: add centerline glyph diagnostics
feat: improve centerline candidate scoring
feat: extend per-glyph centerline overrides
feat: add centerline parameter tuner
feat: add font-specific glyph patch layer
report: add centerline quality comparison

feat: add shaped glyph layout model
feat: apply font pair positioning
feat: detect glyph entry and exit anchors
feat: connect compatible glyph strokes inside words
feat: add connection metrics and debug preview
test: add cursive word connection regressions
report: add word connection comparison

feat: add font fallback chain for symbols
feat: add symbol coverage inspection
feat: add composition manifest models
feat: import safe line-art svg assets
feat: compose text symbols and drawings
test: add special symbols and svg fixtures
report: add composition demo and limitations

docs: document plotter update 6 workflows
```

## 2.3. Что нельзя ломать

Сохранить:

- TXT, DOCX и PDF с текстовым слоем;
- A4 и A5;
- режимы `outline` и `centerline`;
- старый CLI `run`;
- старые конфигурационные файлы без обязательной миграции;
- `font-preview.svg`;
- `centerline-font-preview.svg`;
- `plotter-preview.svg`;
- `paths.json`;
- `output.gcode`;
- `report.json`;
- безопасный G-code без нагрева и extrusion;
- детерминированность при одинаковом входе и конфигурации;
- атомарную запись итоговых файлов;
- проверку границ рабочего пространства.

Запрещено:

- вшивать Pacifico или другой сторонний TTF в репозиторий без проверки лицензии;
- делать хак `if char in "ъьы"` внутри общего алгоритма без конфигурации и объяснения;
- рисовать прямую линию между любыми соседними буквами без геометрической проверки;
- соединять буквы через пробелы, переносы строк и знаки пунктуации;
- молча заменять отсутствующий математический символ похожим символом;
- исполнять JavaScript или внешние ссылки из SVG;
- загружать внешние ресурсы из SVG;
- принимать PNG/JPG за готовую векторную траекторию;
- автоматически включать экспериментальные функции без флага или конфигурации.

## 2.4. Проверки после каждого этапа

Минимум:

```bash
make test
make lint
```

Дополнительно:

```bash
.venv/bin/python -m plotter_processor --help
.venv/bin/python -m plotter_processor run --help
.venv/bin/python -m plotter_processor compile-centerline-font --help
```

После изменения сериализуемых форматов:

- добавить schema/version;
- проверить чтение старой версии;
- проверить понятную ошибку для неподдерживаемой новой версии;
- не менять старый формат без миграции.

## 2.5. Общая структура отчёта после каждого блока

После завершения каждого блока Codex должен написать пользователю сообщение по шаблону:

````markdown
## Блок N завершён — <название>

### Что было сделано
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
- `build/.../preview.svg`
- `build/.../report.json`
- `build/.../output.gcode`

### Тесты
- `make test`: ...
- `make lint`: ...

### Что пока не решено
- ...
````

После отчёта явно написать:

```text
Блок N закончен. Перехожу к Блоку N+1 только после публикации этого отчёта.
```

---

# 3. Общая baseline-проверка перед изменениями

До реализации первого блока создать baseline, чтобы не сравнивать результат «на глаз по памяти».

## 3.1. Подготовить тестовый набор

Создать директорию:

```text
tests/visual/update_6/
```

Не добавлять сам Pacifico TTF, если лицензия или способ распространения не проверены.

Поддержать переменную окружения:

```bash
PLOTTER_TEST_PACIFICO_FONT=/absolute/path/to/Pacifico-Regular.ttf
```

Если шрифт отсутствует:

- unit-тесты не должны падать;
- Pacifico integration-тесты должны быть помечены `skip` с понятной причиной;
- стандартные fixtures проекта должны продолжать проверять общий алгоритм.

Добавить тестовые тексты:

```text
tests/visual/update_6/pacifico_problem_glyphs.txt
tests/visual/update_6/pacifico_connections.txt
tests/visual/update_6/math_symbols.txt
```

Рекомендуемое содержимое первого файла:

```text
ъ ь ы
Ъ Ь Ы
объект подъём съёмка
письмо боль мышь
быстро новый обычный
ъь ыъ ьы ыь
```

Рекомендуемое содержимое второго файла:

```text
машина
обычный
подъём
письмо
быстрый
математика
соединение
программирование
```

Рекомендуемое содержимое математического файла:

```text
x² + y² = z²
√16 = 4
2 × 3 = 6
10 ÷ 2 = 5
x ≤ y
x ≥ y
x ≠ y
α + β = γ
∑ i
∫ f(x) dx
π ≈ 3.14
∞
```

## 3.2. Создать baseline-команду

Добавить скрипт:

```text
tools/update_6_baseline.py
```

Скрипт должен:

1. Принимать путь к TTF.
2. Запускать текущий centerline pipeline.
3. Сохранять результат в отдельную директорию.
4. Не перезаписывать candidate-результат.
5. Считать метрики для конкретных символов и слов.
6. Сохранять `baseline_metrics.json`.

Пример:

```bash
.venv/bin/python tools/update_6_baseline.py \
  --font "$PLOTTER_TEST_PACIFICO_FONT" \
  --output-dir build/update_6/baseline
```

## 3.3. Baseline-метрики

Сохранить минимум:

```json
{
  "base_commit": "...",
  "font_sha256": "...",
  "problem_glyphs": {
    "ъ": {},
    "ь": {},
    "ы": {}
  },
  "word_connections": {},
  "symbols": {},
  "artifacts": {}
}
```

Для глифов:

- выбранный skeleton method;
- mask coverage;
- reconstruction extra;
- centerline components;
- graph node count;
- graph edge count;
- junction count;
- endpoint count;
- retrace ratio;
- stroke count;
- point count;
- итоговая длина маршрута;
- `needs_review`;
- список warnings.

Для слов:

- количество буквенных пар;
- количество подъёмов внутри слова;
- количество штрихов основных тел букв;
- количество вторичных штрихов;
- travel distance между буквами;
- draw distance;
- предполагаемое число Z-циклов.

## 3.4. Желаемый результат baseline-этапа

Пользователь и разработчик должны получить воспроизводимое состояние «до», которое можно повторно сгенерировать той же командой.

Baseline не должен зависеть от заранее созданного `build/`.

---

# 4. БЛОК 1 — Улучшение качества centerline для сложных букв

## 4.1. Цель блока

Добиться того, чтобы буквы `ъ`, `ь`, `ы` в Pacifico после поиска центральной линии выглядели как узнаваемые буквы, сохраняли основные элементы исходного глифа и не содержали случайных ветвей, обрезанных частей, паразитных петель или грубых углов.

Алгоритм должен улучшиться не только для трёх символов, но эти три символа являются обязательным regression-набором.

## 4.2. Критерии готовности Блока 1

Блок считается готовым, когда:

- для `ъ`, `ь`, `ы` созданы сравнения до/после;
- ни один обязательный элемент буквы не потерян;
- нет паразитных коротких ветвей, заметных в итоговом SVG;
- главные вертикальные и округлые части не превращены в ломаную;
- количество компонентов соответствует реальной структуре глифа;
- centerline преимущественно проходит внутри маски;
- все изменения детерминированы;
- автоматические метрики не ухудшились без объяснения;
- при невозможности получить идеальный результат автоматически существует безопасный слой font-specific override/patch;
- обычные тестовые глифы не получили регрессию.

Не задавать универсальный числовой порог, который искусственно «проходит», но визуально ломает букву. Автоматическая метрика и визуальный regression должны использоваться вместе.

---

## Этап 1. Сделать подробную диагностику каждого проблемного глифа

### Проблема

Существующие метрики показывают общую coverage и topology, но не объясняют, где именно потерялась часть буквы или появился ложный маршрут.

### Что сделать

Расширить debug export для одного глифа.

Для каждого кандидата сохранять:

```text
00_raster.png
01_mask.png
02_distance.png
03_skeleton_skeletonize.png
04_skeleton_medial_axis.png
05_selected_skeleton.png
06_graph_nodes_edges.svg
07_routes.svg
08_smoothed_strokes.svg
09_reconstructed_mask.png
10_mask_difference.png
11_overlay.svg
metrics.json
```

В `overlay.svg` разными визуальными слоями показывать:

- границу исходной маски;
- выбранную центральную линию;
- endpoints;
- junctions;
- повторно пройденные сегменты;
- удалённые spurs/micro-loops, если возможно;
- номера компонентов и маршрутов.

Добавить CLI-команду или расширить существующую:

```bash
.venv/bin/python -m plotter_processor compile-centerline-font \
  "$PLOTTER_TEST_PACIFICO_FONT" \
  --chars "ъьы" \
  --force \
  --debug-dir build/update_6/block_1/debug
```

### Изменяемые файлы

Ожидаемо:

```text
src/plotter_processor/centerline_font/debug.py
src/plotter_processor/centerline_font/compiler.py
src/plotter_processor/centerline_font/models.py
tests/test_centerline_debug.py
```

Создать новый тестовый файл, если его нет.

### Тесты

Проверить:

- имена файлов стабильны;
- debug export не меняет результат компиляции;
- output создаётся только при указанном debug-dir или при `needs_review`;
- JSON сериализуем;
- SVG не содержит NaN/Infinity;
- повторный запуск создаёт идентичный результат.

### Желаемый результат

Для каждого из `ъ`, `ь`, `ы` можно открыть один каталог и увидеть, на каком этапе появляется дефект.

---

## Этап 2. Исправить систему оценки кандидатов skeleton

### Проблема

Текущий выбор кандидата сильно ориентирован на количество рёбер, junctions и odd vertices. Такой score способен выбрать топологически простой, но визуально неправильный centerline.

### Что сделать

1. Вынести score в отдельную модель:

```text
CenterlineCandidateScore
```

2. Хранить компоненты score отдельно, а не только одно число:

```json
{
  "total": 0.0,
  "coverage_penalty": 0.0,
  "outside_penalty": 0.0,
  "topology_penalty": 0.0,
  "spur_penalty": 0.0,
  "loop_penalty": 0.0,
  "radius_balance_penalty": 0.0,
  "endpoint_penalty": 0.0,
  "retrace_penalty": 0.0,
  "shape_preservation_penalty": 0.0
}
```

3. Не использовать edge count как практически абсолютный главный критерий.
4. Добавить метрику сохранения силуэта:
   - реконструировать приближённую маску из centerline и локального radius map;
   - сравнивать её с исходной маской;
   - отдельно считать false negative и false positive области.
5. Добавить метрику сохранения связных областей и counters.
6. Добавить штраф за исчезновение длинной части исходного skeleton.
7. Добавить штраф за endpoint, который находится далеко от ожидаемой границы stroke terminal.
8. Добавить штраф за резкие смены направления на небольшом расстоянии.
9. Все веса вынести в конфигурацию с понятными defaults.
10. В `metrics.json` сохранять полную раскладку score.

### Новая конфигурация

Предлагаемый раздел:

```yaml
centerline:
  candidate_scoring:
    coverage_weight: 4.0
    outside_weight: 4.0
    topology_weight: 1.0
    spur_weight: 2.0
    micro_loop_weight: 2.0
    radius_balance_weight: 0.5
    endpoint_weight: 1.0
    retrace_weight: 0.5
    shape_preservation_weight: 4.0
    counter_preservation_weight: 3.0
    curvature_weight: 0.5
```

Старый config без этого раздела должен продолжить работать через defaults.

### Тесты

Создать синтетические маски:

- простая линия;
- петля;
- вертикаль с округлой частью;
- две близкие вертикали;
- ложная короткая ветка;
- буквообразная маска с counter;
- маска, где простой skeleton теряет часть фигуры.

Проверить, что правильный кандидат выигрывает по объяснимым причинам.

### Желаемый результат

Для `ъ`, `ь`, `ы` выбранный candidate должен лучше совпадать с исходной формой, даже если у него немного больше рёбер, чем у визуально плохого кандидата.

---

## Этап 3. Сделать width-aware очистку skeleton

### Проблема

Одинаковый порог удаления ветвей плохо работает для тонких соединительных штрихов и толстых частей буквы.

### Что сделать

1. Для каждой ветви считать локальную ширину по distance transform.
2. Оценивать ветвь не только по абсолютной длине, а по отношению:

```text
branch_length / local_stroke_width
```

3. Сохранять длинные тонкие соединительные элементы.
4. Удалять короткие боковые выступы в толстой области.
5. Не удалять ветвь, если она:
   - соединяет две значимые области;
   - является единственным путём к большой части маски;
   - соответствует выходному соединительному хвосту буквы;
   - нужна для сохранения counter/loop.
6. Добавить двухфазное pruning:
   - сначала очевидные pixel spurs;
   - затем graph-level candidate pruning с проверкой reconstruction loss.
7. Перед удалением ребра вычислять, насколько ухудшится coverage.
8. Отменять удаление, если потеря превышает конфигурационный порог.

### Предлагаемые параметры

```yaml
centerline:
  skeleton:
    spur_pruning:
      enabled: true
      min_length_width_ratio: 1.5
      max_coverage_loss: 0.01
      preserve_connector_terminals: true
      preserve_counter_edges: true
```

### Тесты

Проверить:

- тонкий длинный хвост сохраняется;
- толстый короткий spur удаляется;
- удаление не разрывает компонент;
- результат не зависит от порядка edges;
- `ъ`, `ь`, `ы` не теряют правую/левую часть.

### Желаемый результат

У проблемных букв исчезают паразитные ветви, но не исчезают реальные соединительные элементы.

---

## Этап 4. Добавить сохранение внутренних областей и counters

### Проблема

В `ь`, `ъ`, `ы` важная округлая часть может быть повреждена, если skeleton simplification неправильно обращается с петлёй или близкими ветвями.

### Что сделать

1. До skeletonization определить структуру маски:
   - внешние компоненты;
   - holes/counters;
   - площадь каждого counter;
   - bounding box;
   - ближайшие skeleton edges.
2. После simplification проверить, что для каждого значимого counter осталась окружающая маршрутная структура.
3. Не требовать замкнутый centerline для каждого counter: проверять сохранение формы, а не буквальное совпадение topology контура.
4. Добавить `counter_preservation_ratio`.
5. Добавить warning:

```text
Significant glyph counter is not represented by centerline geometry
```

6. Использовать эту метрику при выборе skeleton candidate.
7. Экспортировать counters в debug overlay.

### Тесты

Использовать синтетические формы и реальные `ь`, `ъ`, `ы`.

### Желаемый результат

Округлая часть букв остаётся читаемой и не превращается в случайную дугу или обрезанный штрих.

---

## Этап 5. Расширить `glyph_overrides`

### Проблема

Текущие overrides позволяют менять только несколько параметров. Этого недостаточно для сложных глифов и разных TTF.

### Что сделать

Поддержать override минимум для:

```text
em_resolution_px
padding_px
threshold
closing_radius_px
skeleton_method
candidate_methods
min_branch_width_factor
max_junction_cluster_px
max_micro_loop_width_factor
simplify_tolerance_px
spline_smoothing_factor
output_step_px
junction_max_angle_deg
max_retrace_ratio
candidate scoring weights
spur pruning settings
```

Overrides должны поддерживать два уровня:

1. По Unicode-символу.
2. По паре `font_sha256 + glyph_name/codepoint`.

Предлагаемая конфигурация:

```yaml
centerline:
  glyph_overrides:
    "ъ":
      skeleton_method: medial_axis
      threshold: 150
    "ь":
      skeleton_method: auto
      min_branch_width_factor: 1.2
    "ы":
      simplify_tolerance_px: 0.7

  font_overrides:
    "<font_sha256>":
      glyphs:
        "ъ":
          threshold: 148
        "ь":
          skeleton_method: medial_axis
        "ы":
          closing_radius_px: 0
```

Приоритет:

```text
default config
  < Unicode glyph override
  < font-specific glyph override
  < explicit CLI experiment override
```

### Важные требования

- неизвестный параметр должен вызывать понятную ошибку;
- типы и диапазоны валидировать;
- effective config сохранять в debug metrics;
- cache key должен учитывать effective config;
- изменение override должно инвалидировать только нужный cache результат или корректно менять общий config hash.

### Желаемый результат

Pacifico можно тонко настроить без добавления условий, влияющих на все шрифты.

---

## Этап 6. Добавить автоматический tuner параметров для отдельных глифов

### Задача

Не подбирать threshold и pruning вручную десятками запусков.

### CLI

Добавить команду:

```bash
.venv/bin/python -m plotter_processor tune-centerline-glyphs \
  "$PLOTTER_TEST_PACIFICO_FONT" \
  --chars "ъьы" \
  --layout-config configs/layout.yaml \
  --output-dir build/update_6/block_1/tuning
```

### Что делает tuner

1. Строит ограниченную сетку параметров.
2. Не перебирает бесконечное число комбинаций.
3. Для каждой комбинации сохраняет metrics.
4. Отбрасывает варианты с потерей компонентов или критической coverage.
5. Сортирует варианты по новому candidate score.
6. Сохраняет top-N preview.
7. Создаёт предлагаемый YAML override.
8. Не применяет его автоматически к основному config без явного действия.

### Минимальная сетка

```text
skeleton_method: skeletonize, medial_axis
threshold: default ± 10, default ± 20
closing_radius_px: 0, 1, 2
min_branch_width_factor: несколько безопасных значений
simplify_tolerance_px: несколько безопасных значений
spline_smoothing_factor: несколько безопасных значений
```

Количество комбинаций ограничить параметром `--max-candidates`.

### Результат

```text
build/update_6/block_1/tuning/
  summary.json
  suggested_overrides.yaml
  ъ/top_01.svg
  ъ/top_02.svg
  ...
```

### Тесты

- tuner детерминирован;
- `--max-candidates` соблюдается;
- неудачная комбинация не останавливает весь sweep;
- итоговый YAML валиден;
- top candidate действительно имеет минимальный score среди сохранённых.

### Желаемый результат

Codex может аргументированно выбрать параметры для Pacifico и показать пользователю несколько лучших вариантов.

---

## Этап 7. Добавить безопасный слой ручной коррекции сложного глифа

### Почему это нужно

Автоматическая skeletonization не гарантирует идеальный результат для каждого декоративного шрифта. Нужен контролируемый fallback, а не бесконечное усложнение общего алгоритма.

### Что сделать

Добавить поддержку font-specific centerline patch.

Patch должен быть привязан к:

```text
font_sha256
glyph_name или codepoint
patch format version
```

Формат можно сделать YAML/JSON со списком штрихов в font units:

```yaml
version: 1
font_sha256: "..."
glyphs:
  "ъ":
    mode: replace
    advance_font_units: 1000
    strokes:
      - closed: false
        points:
          - [x1, y1]
          - [x2, y2]
```

Поддержать modes:

```text
replace  — заменить автоматически найденные strokes;
append   — добавить отсутствующий stroke;
remove   — удалить явно указанный дефектный stroke по стабильному id/signature.
```

Для первой версии обязательным сделать только `replace`. Остальные modes можно оставить на будущее, если они увеличивают риск.

### Требования безопасности

- patch применяется только при совпадении font SHA;
- несовпадение SHA — ошибка или warning, но не тихое применение;
- точки валидируются;
- координаты конечны;
- минимальное количество точек проверяется;
- patch проходит те же quality checks;
- в report явно указано `source: manual_patch`;
- preview показывает, что использован patch;
- обычные пользователи без patch получают автоматический pipeline.

### Желаемый результат

Если автоматическая версия `ъ`, `ь` или `ы` всё ещё выглядит плохо, можно один раз подготовить корректный centerline именно для этого SHA Pacifico и получить стабильный результат.

---

## Этап 8. Добавить visual regression для глифов

### Что сделать

1. Создать генератор snapshot SVG/PNG.
2. Не сравнивать PNG побайтно из-за возможных различий renderer.
3. Сравнивать геометрию:
   - stroke count;
   - component count;
   - endpoints;
   - normalized sampled points;
   - Hausdorff/Chamfer distance с tolerance;
   - bounding box;
   - длину маршрута;
   - coverage metrics.
4. Для локальной проверки создавать contact sheet до/после.
5. Snapshot update должен быть явной командой.

Пример:

```bash
.venv/bin/python tools/update_centerline_snapshots.py \
  --font "$PLOTTER_TEST_PACIFICO_FONT" \
  --chars "ъьы"
```

### Желаемый результат

Следующее изменение centerline не сможет незаметно снова сломать `ъ`, `ь`, `ы`.

---

## Этап 9. Финальная проверка и отчёт по Блоку 1

### Команды

```bash
make test
make lint

.venv/bin/python -m plotter_processor compile-centerline-font \
  "$PLOTTER_TEST_PACIFICO_FONT" \
  --chars "ъьы" \
  --force \
  --debug-dir build/update_6/block_1/final-debug \
  --preview build/update_6/block_1/centerline-preview.svg

.venv/bin/python -m plotter_processor run \
  tests/visual/update_6/pacifico_problem_glyphs.txt \
  --font "$PLOTTER_TEST_PACIFICO_FONT" \
  --font-mode centerline \
  --page A5 \
  --size normal \
  --output-dir build/update_6/block_1/page
```

### Таблица отчёта

Для каждого символа:

| Глиф | Candidate до | Candidate после | Strokes до/после | Components до/после | Coverage до/после | Extra до/после | Review до/после | Источник |
|---|---|---|---:|---:|---:|---:|---|---|
| ъ | | | | | | | | auto/override/patch |
| ь | | | | | | | | auto/override/patch |
| ы | | | | | | | | auto/override/patch |

### Обязательный отчёт пользователю после Блока 1

Codex должен объяснить простыми словами:

- почему буквы выглядели плохо;
- на каком этапе появлялся дефект;
- что изменено в общем алгоритме;
- какие настройки добавлены специально для конкретного font SHA;
- использовался ли manual patch;
- где лежит SVG до/после;
- какие ограничения остались.

После публикации отчёта переходить к Блоку 2.

---

# 5. БЛОК 2 — Соединение букв внутри слов и уменьшение подъёмов ручки

## 5.1. Цель блока

Сделать так, чтобы основная линия рукописного слова писалась максимально непрерывно. Подъём ручки между соседними буквами допускается только когда безопасное соединение невозможно или когда структура символа действительно требует отдельного штриха.

Не требуется искусственно превращать каждое слово в одну линию любой ценой. Приоритет:

1. читаемость;
2. отсутствие лишних линий;
3. естественное направление письма;
4. сокращение подъёмов.

## 5.2. Важное различие

Есть два разных источника разрыва:

1. Глифы расположены неправильно из-за отсутствия kerning/GPOS/shaping.
2. Даже правильно расположенные centerline strokes не объединены в один маршрут.

Нельзя решать только второй пункт прямой линией. Сначала нужно исправить модель layout, затем строить соединители.

## 5.3. Критерии готовности Блока 2

- пробелы и переносы никогда не соединяются;
- пунктуация не соединяется без явно разрешённого правила;
- соседние строчные рукописные буквы соединяются при подходящей геометрии;
- соединитель имеет плавные касательные;
- соединитель не пересекает counter или чужой штрих;
- отклонённое соединение оставляет обычный подъём ручки;
- точки/диакритика могут рисоваться отдельными штрихами;
- основное тело слова имеет значительно меньше подъёмов;
- все решения видны в debug preview и report;
- функция отключается конфигурацией/CLI.

---

## Этап 1. Ввести модель shaped glyph и font identity

### Проблема

Текущий `PositionedGlyph` хранит `char`, `glyph_name` и advance. Для полноценного позиционирования и fallback-font этого недостаточно.

### Что сделать

Добавить модели:

```python
FontIdentity
ShapedGlyph
ShapedRun
TextRun
```

Пример полей `ShapedGlyph`:

```text
source_characters
glyph_id
glyph_name
font_id
font_path
font_sha256
cluster_index
x_advance_font_units
y_advance_font_units
x_offset_font_units
y_offset_font_units
x_mm
baseline_y_mm
scale_mm_per_font_unit
line_index
glyph_index
word_index
```

Сохранить compatibility adapter в `PositionedGlyph`, если полная замена слишком рискованна.

### Важное изменение centerline cache

Centerline glyph должен уметь индексироваться не только по `char`, но и по:

```text
font_sha256 + glyph_name
```

Причина: OpenType shaping способен выбирать alternate/contextual glyph, который нельзя однозначно описать одним Unicode-char.

### Миграция

- поднять версию centerline cache;
- добавить reader старой версии;
- старые entries по char можно мигрировать через glyph name;
- не читать старый cache как новый молча.

### Тесты

- один Unicode char -> один glyph;
- несколько chars -> ligature glyph, если поддержано шрифтом;
- один char -> alternate glyph;
- одинаковое glyph name в двух шрифтах не конфликтует;
- cache key меняется при смене font SHA.

### Желаемый результат

Следующие этапы работают с реальным glyph identity, а не только с исходным символом.

---

## Этап 2. Добавить shaping/позиционирование текста

### Рекомендуемый подход

Использовать HarfBuzz через Python binding, например `uharfbuzz`, если зависимость подходит проекту.

Не писать собственный полный GPOS parser.

### Что сделать

Создать:

```text
src/plotter_processor/text_shaper.py
```

Интерфейс:

```python
shape_text_run(text, font, *, direction, script, language, features) -> ShapedRun
```

Для русского текста defaults:

```text
direction: ltr
script: Cyrl
language: ru
```

Учитывать:

- glyph substitutions;
- pair positioning;
- x/y offsets;
- advances;
- clusters;
- combining marks;
- ligatures, если есть.

### Fallback

Если HarfBuzz недоступен:

- установка проекта должна явно сообщать о зависимости;
- не делать тихий упрощённый layout в режиме `shaped`;
- старый layout может сохраниться как `layout_engine: legacy`;
- новый режим — `layout_engine: harfbuzz`.

После стабилизации можно сделать HarfBuzz default, но не в первом commit.

### CLI/config

```yaml
layout:
  engine: harfbuzz
  language: ru
  script: Cyrl
  direction: ltr
  features: []
```

CLI override:

```bash
--layout-engine legacy|harfbuzz
```

### Проверка Pacifico

Сравнить bounding box и позиции для:

```text
обычный
письмо
подъём
быстрый
```

Сохранить SVG:

```text
legacy-layout.svg
harfbuzz-layout.svg
```

### Тесты

- line wrapping использует shaped advances;
- cluster не разрывается посередине ligature/combining sequence;
- `word_index` сохраняется;
- одинаковый input даёт одинаковый layout;
- legacy mode не изменился.

### Желаемый результат

Буквы располагаются так, как предусмотрено таблицами шрифта, до попытки соединения centerline.

---

## Этап 3. Классифицировать штрихи глифа

### Задача

Отделить основной пишущий штрих от вторичных элементов.

Для каждого centerline glyph определить:

```text
main_stroke
secondary_strokes
entry_candidates
exit_candidates
diacritic_strokes
closed_component_strokes
```

### Эвристики main stroke

Использовать комбинацию:

- длина;
- площадь/масштаб обслуживаемой маски;
- положение относительно baseline;
- наличие endpoints слева/справа;
- близость к соседним буквам;
- topology component size;
- горизонтальный охват.

Не считать самый длинный stroke автоматически правильным во всех случаях.

### Метаданные

Расширить centerline cache:

```json
{
  "stroke_roles": {
    "0": "main",
    "1": "secondary",
    "2": "diacritic"
  }
}
```

Если классификация не уверена:

```text
role: unknown
confidence: <value>
```

В safe mode неизвестный stroke не использовать для межбуквенного соединения.

### Тесты

- `й`, `ё` имеют основное тело и отдельную диакритику;
- `ы` корректно классифицируется с учётом нескольких частей;
- `ъ`, `ь` имеют ожидаемый main stroke;
- closed symbol вроде `о` получает допустимые entry/exit candidates через route orientation, но не ломает петлю.

### Желаемый результат

Pipeline понимает, какой штрих нужно продолжить к следующей букве, а какие элементы нужно дорисовать отдельно.

---

## Этап 4. Находить entry/exit anchors глифа

### Что такое anchor

Anchor — кандидат точки, через которую ручка входит в букву или выходит из неё.

Для каждого кандидата хранить:

```text
point
tangent
side: left|right|top|bottom
role: entry|exit|both
confidence
stroke_id
point_index
baseline_offset
```

### Поиск кандидатов

1. Рассматривать endpoints main stroke.
2. Для closed route разрешить выбор точки разрыва на контуре маршрута.
3. Предпочитать entry слева, exit справа для LTR.
4. Проверять положение относительно baseline и x-height band.
5. Проверять направление tangent.
6. Не выбирать точку внутри плотного junction cluster.
7. Не выбирать диакритику.
8. Не выбирать точку, если соединение разрушит обязательную петлю.

### Closed stroke orientation

Для замкнутого маршрута можно:

- выбрать точку начала;
- циклически повернуть список points;
- выбрать направление обхода;
- сохранить closed geometry, но открыть маршрут логически в выбранной точке, если это допустимо для письма.

Не менять `closed` без отдельного поля, описывающего route opening.

### Debug

Экспортировать anchors стрелками и номерами.

### Тесты

- стабильный выбор при одинаковом input;
- зеркальные/близкие candidates получают стабильный tie-break;
- tangents корректно разворачиваются при reverse stroke;
- anchors не выходят за glyph bounds.

### Желаемый результат

У каждой подходящей буквы есть понятная точка входа и выхода для межбуквенного соединения.

---

## Этап 5. Построить оценку совместимости соседних букв

### Новая модель

```text
GlyphConnectionCandidate
```

Поля:

```text
left_glyph_index
right_glyph_index
left_exit
right_entry
distance_mm
exit_angle_deg
entry_angle_deg
tangent_mismatch_deg
vertical_offset_mm
corridor_inside_ratio
collision_count
score
accepted
rejection_reason
```

### Правила запрета

Не соединять:

- разные строки;
- разные слова;
- пары через пробел;
- пары через tab/newline;
- обычную пунктуацию;
- символы с разными writing direction;
- слишком далёкие anchors;
- anchors с несовместимыми tangents;
- маршрут, пересекающий запрещённую область;
- сомнительный glyph role в safe mode.

### Конфигурация

```yaml
connections:
  enabled: true
  mode: safe
  max_distance_mm: 1.5
  max_vertical_offset_mm: 1.2
  max_tangent_mismatch_deg: 55.0
  min_corridor_inside_ratio: 0.55
  allow_connector_outside_ink: true
  outside_ink_margin_mm: 0.35
  connect_letters_only: true
  connect_across_punctuation: false
```

Значения являются стартовыми и должны быть откалиброваны на реальном размере текста.

### Score

Score должен учитывать:

- distance;
- tangent mismatch;
- vertical offset;
- collision risk;
- выход за допустимый corridor;
- confidence anchors;
- необходимость сильного изгиба;
- длину будущего connector.

### Желаемый результат

Для каждой пары букв есть объяснимое решение: соединить или оставить подъём, с причиной в report.

---

## Этап 6. Строить плавный connector

### Геометрия

Использовать cubic Bézier или другую гладкую кривую с заданными касательными.

Для cubic Bézier:

```text
P0 = left exit
P3 = right entry
P1 = P0 + normalized(exit tangent) * handle_1
P2 = P3 - normalized(entry tangent) * handle_2
```

Длины handles ограничить расстоянием между буквами и конфигурацией.

### Требования

- continuity минимум G1;
- без острого угла в P0/P3;
- без loop/self-intersection;
- без обратного движения на большое расстояние;
- не пересекать counter соседней буквы;
- не выходить далеко за bounding corridor слова;
- дискретизация использует текущие правила `output_step`;
- connector получает собственный metadata type.

### Валидация connector

До принятия:

1. Sample curve.
2. Проверить bounds.
3. Проверить пересечения с запрещёнными strokes.
4. Проверить расстояние до масок двух глифов.
5. Проверить максимальную curvature.
6. Проверить минимальную длину сегментов.
7. Проверить, что curve не идёт назад слишком далеко по X.

### Fallback

Если validation не прошла:

- не пытаться «починить любой ценой»;
- сохранить pen lift;
- записать rejection reason.

### Тесты

- совместимые горизонтальные anchors;
- небольшой вертикальный offset;
- слишком большой разрыв;
- противоположные tangents;
- collision;
- self-intersection candidate;
- одинаковые points;
- очень короткий connector.

### Желаемый результат

Принятый connector выглядит как естественное продолжение stroke, а не как прямая перемычка.

---

## Этап 7. Объединять маршруты внутри слова

### Что сделать

Создать отдельный этап после построения page-space glyph strokes:

```text
build_centerline_paths
  -> classify page strokes
  -> plan word connections
  -> merge connected main strokes
  -> schedule secondary strokes
  -> final PathDocument
```

Рекомендуемый новый модуль:

```text
src/plotter_processor/word_connector.py
```

### Объединение

Если пара принята:

```text
left main stroke
+ connector points
+ right main stroke
= один PlotterStroke
```

Правильно обработать orientation:

- reverse left stroke при необходимости;
- reverse right stroke при необходимости;
- rotate opened closed route;
- dedupe P0/P3;
- сохранить mapping исходных glyph indices.

### Модель provenance

Расширить `PlotterStroke` или metadata:

```text
source_glyph_indices
source_chars
segment_types: glyph|connector|retrace
word_index
connection_ids
```

Не ломать старый `paths.json` reader. Поднять версию или добавить optional fields.

### Вторичные strokes

Рекомендуемый режим:

1. Сначала написать main chain слова.
2. Затем дорисовать diacritics и secondary strokes.
3. Оптимизировать их порядок внутри слова.
4. Не соединять вторичные strokes с основной цепью ложными линиями.

### Желаемый результат

Основное тело слова может стать одним stroke, даже если точки над `й/ё` остаются отдельными.

---

## Этап 8. Добавить режимы соединения

### Config

```yaml
connections:
  enabled: false
  mode: safe
```

Режимы:

```text
off        — старое поведение;
safe       — соединять только уверенные пары;
aggressive — разрешать более широкий набор, но сохранять validation.
```

CLI:

```bash
--connections off|safe|aggressive
```

### Обратная совместимость

На первом релизе default рекомендуется `off` или `safe` в зависимости от результатов тестов.

Нельзя включать aggressive по умолчанию.

### Желаемый результат

Пользователь может сравнить старый и новый режим без изменения кода.

---

## Этап 9. Добавить метрики подъёмов внутри слов

### В `report.json`

Добавить:

```json
{
  "connections": {
    "mode": "safe",
    "letter_pairs_total": 0,
    "eligible_pairs": 0,
    "connected_pairs": 0,
    "rejected_pairs": 0,
    "pen_lifts_inside_words_before": 0,
    "pen_lifts_inside_words_after": 0,
    "pen_lifts_saved": 0,
    "main_word_chains": 0,
    "connector_draw_length_mm": 0.0,
    "rejections_by_reason": {},
    "per_word": []
  }
}
```

Для каждого слова:

```json
{
  "text": "обычный",
  "line_index": 0,
  "glyph_count": 7,
  "connections": 5,
  "remaining_internal_lifts": 1,
  "secondary_strokes": 0,
  "rejected_pairs": []
}
```

### Preview

Создать отдельный:

```text
connection-debug.svg
```

Отображать:

- glyph strokes;
- accepted connectors;
- rejected candidate connectors пунктиром;
- anchor arrows;
- номера слов;
- причины отказа в отдельном JSON/легенде.

### Желаемый результат

Можно точно сказать, где остался подъём ручки и почему.

---

## Этап 10. Regression corpus слов

### Обязательные слова

```text
машина
обычный
подъём
письмо
быстрый
математика
соединение
программирование
```

Добавить пары, которые нельзя соединять:

```text
слово слово
текст,текст
текст-текст
й ё
AБ
```

### Автоматические критерии

Для каждого слова считать:

- pairs total;
- connected pairs;
- remaining lifts;
- connector length;
- maximum connector curvature;
- collisions;
- bounds violations.

Требования:

- collisions = 0;
- bounds violations = 0;
- connection across spaces = 0;
- connection across line breaks = 0;
- deterministic output;
- safe mode не должен ухудшать читаемость regression SVG.

Целевой ориентир для тестового набора Pacifico:

- сократить подъёмы между основными телами соседних строчных букв минимум на 70%;
- желательный результат — 85% и выше;
- не достигать процента за счёт неправильных линий.

### Желаемый результат

Подъёмы уменьшаются измеримо, а не только визуально.

---

## Этап 11. Физическая проверка Блока 2

### Подготовить G-code

Сгенерировать три версии одного текста:

```text
connections-off
connections-safe
connections-aggressive
```

Не запускать aggressive на принтере до просмотра SVG и dry-run.

### Проверить физически

- нет чернильных клякс на anchors;
- connector не слишком тонкий/короткий;
- ручка не тормозит резко;
- нет обратного рывка;
- слово читается;
- количество Z-движений реально уменьшилось;
- соединитель не проходит через внутреннюю область буквы.

### Артефакты

```text
build/update_6/block_2/off/
build/update_6/block_2/safe/
build/update_6/block_2/aggressive/
build/update_6/block_2/comparison.json
build/update_6/block_2/contact-sheet.svg
```

---

## Этап 12. Обязательный отчёт пользователю после Блока 2

Отчёт должен содержать таблицу:

| Текст | Подъёмы внутри слов до | После safe | Сэкономлено | Connected pairs | Rejected pairs | Причина оставшихся подъёмов |
|---|---:|---:|---:|---:|---:|---|

Отдельно объяснить:

- добавлен ли HarfBuzz;
- применились ли kerning/GPOS;
- как выбираются entry/exit anchors;
- как строится connector;
- какие буквы всё ещё не соединяются;
- сколько дополнительных draw millimeters добавили соединители;
- насколько уменьшились Z-циклы;
- какой режим рекомендуется как default.

После публикации отчёта переходить к Блоку 3.

---

# 6. БЛОК 3 — Начальная поддержка математических символов и рисунков

## 6.1. Цель блока

Добавить первую безопасную и расширяемую версию поддержки:

1. Unicode математических символов.
2. Отдельного fallback TTF для символов, отсутствующих в рукописном шрифте.
3. Простых векторных рисунков в SVG.
4. Компоновки текста и рисунков на одной странице.

Это начальная поддержка. Не пытаться в этом блоке сделать полноценный LaTeX renderer или автоматическую векторизацию фотографий.

## 6.2. Scope первой версии

### Поддержать

- Unicode chars: `± × ÷ ≠ ≤ ≥ ≈ √ ∑ ∫ ∞ π α β γ` и другие, если они есть в выбранном font/fallback font;
- superscript Unicode, если он есть в шрифте;
- line-art SVG;
- SVG basic shapes;
- SVG path data;
- масштабирование, перенос и fit в заданный прямоугольник;
- текст и SVG как элементы одной композиции;
- preview, paths.json, report.json и G-code.

### Не поддерживать в первой версии

- автоматическое преобразование LaTeX в формулу;
- MathML layout;
- сложные дроби с автоматической версткой;
- PNG/JPG raster-to-vector;
- фотографии;
- цветную заливку как штриховку;
- SVG filters;
- JavaScript;
- external href;
- embedded fonts;
- CSS из сети;
- SVG animation;
- `<foreignObject>`;
- текстовые SVG elements без явной конвертации в path.

---

## Этап 1. Добавить отчёт покрытия символов шрифтом

### Расширить `font-info`

Добавить:

```bash
.venv/bin/python -m plotter_processor font-info font.ttf --coverage math
```

Выводить:

```text
Math symbols supported: N/M
Missing common symbols: ...
Greek supported: N/M
Superscripts supported: N/M
```

Добавить machine-readable output:

```bash
--json build/font-coverage.json
```

### Категории

Создать стабильные наборы:

```text
basic_math
relations
operators
calculus
greek_lower
greek_upper
superscripts
arrows
```

Хранить их в модуле:

```text
src/plotter_processor/unicode_coverage.py
```

### Важно

Не утверждать, что символ поддержан, только потому что codepoint есть в Unicode. Проверять cmap конкретного TTF.

### Тесты

- fixture font с частью символов;
- список missing стабилен;
- JSON содержит codepoint, char и Unicode name;
- неизвестная coverage group даёт ошибку.

### Желаемый результат

До запуска пользователь понимает, какие математические символы Pacifico реально содержит.

---

## Этап 2. Добавить fallback font chain

### Проблема

Рукописный TTF часто не содержит `∫`, `∑`, `√`, `≤` и греческие символы.

### Что сделать

Добавить конфигурацию:

```yaml
fonts:
  primary: assets/handwriting.ttf
  fallbacks:
    - role: math
      path: assets/math-symbols.ttf
    - role: symbols
      path: assets/symbols.ttf
```

CLI для старого `run`:

```bash
--fallback-font path/to/math-symbols.ttf
```

Можно разрешить повторяемый аргумент.

### Выбор шрифта

Для каждого Unicode cluster:

1. Проверить primary cmap.
2. Затем fallbacks по порядку.
3. Выбрать первый подходящий font.
4. Сформировать shaped run для выбранного font.
5. Не смешивать font посередине combining cluster.
6. Если glyph отсутствует везде — понятная ошибка со списком проверенных fonts.

### Масштабирование fallback

Символы разных TTF должны визуально соответствовать строке.

Добавить параметры:

```yaml
fonts:
  fallback_alignment:
    strategy: x_height_or_em
    math_scale: 0.95
    baseline_shift_mm: 0.0
```

Если x-height отсутствует, использовать em/ascent metrics.

Не делать скрытый hard-coded offset для конкретного файла.

### Centerline cache

- отдельный cache по font SHA;
- glyph key по font identity + glyph name;
- report показывает, какой font использован для каждого fallback glyph.

### Preview

Разрешить debug color coding fonts, но итоговый plotter preview остаётся одноцветным.

### Тесты

- primary содержит символ;
- символ берётся из первого fallback;
- символ берётся из второго fallback;
- символ отсутствует везде;
- baseline alignment;
- line wrap с разными advances;
- cache не конфликтует.

### Желаемый результат

Текст с математическими Unicode-символами проходит pipeline даже при неполном основном рукописном TTF.

---

## Этап 3. Ввести общую модель элементов документа

### Проблема

Текущая модель содержит только paragraphs текста. Для рисунков нужна композиция элементов.

### Новые модели

```python
PlotterDocument
DocumentElement
TextElement
SymbolElement
SvgElement
ElementPlacement
```

Каждый элемент содержит:

```text
id
type
source
position
size
z_order
transform
style/options
```

### Обратная совместимость

TXT/DOCX/PDF преобразуются в:

```text
PlotterDocument(elements=[TextElement(...)])
```

Старый внешний CLI должен продолжить работать.

### Новая pipeline-структура

```text
read input
  -> PlotterDocument
  -> layout each element
  -> generate element paths
  -> transform to page coordinates
  -> validate bounds
  -> combine PathDocument
  -> optimize safe travel
  -> export SVG/JSON/G-code
```

### Желаемый результат

Текст и рисунок используют общий безопасный выходной pipeline.

---

## Этап 4. Добавить композиционный manifest

### Рекомендуемый формат

Добавить новый opt-in формат:

```text
.plotter.yaml
```

Пример:

```yaml
version: 1
page: A5

fonts:
  primary: assets/handwriting.ttf
  fallbacks:
    - role: math
      path: assets/math-symbols.ttf

elements:
  - id: title
    type: text
    text: "Формула площади круга"
    x_mm: 10
    y_mm: 12
    width_mm: 128
    size: normal
    font_mode: centerline

  - id: formula
    type: text
    text: "S = πr²"
    x_mm: 20
    y_mm: 35
    width_mm: 100
    size: large
    font_mode: centerline

  - id: diagram
    type: svg
    path: assets/circle-diagram.svg
    x_mm: 30
    y_mm: 60
    width_mm: 80
    height_mm: 70
    fit: contain
```

### CLI

```bash
.venv/bin/python -m plotter_processor compose \
  examples/math_diagram.plotter.yaml \
  --machine-config configs/machine.yaml \
  --output-dir build/update_6/block_3/composition
```

### Валидация manifest

- version обязателен;
- неизвестные поля — ошибка или строгий warning по политике проекта;
- duplicate id — ошибка;
- path разрешать относительно manifest;
- запрет выхода за разрешённую рабочую директорию можно сделать configurable;
- размеры положительные;
- page bounds проверяются;
- циклические includes запрещены;
- первая версия без includes предпочтительна.

### Тесты

- valid manifest;
- missing field;
- invalid type;
- duplicate id;
- bad relative path;
- element outside page;
- old run не затронут.

### Желаемый результат

Можно описать страницу с текстом, формулой и рисунком одним файлом.

---

## Этап 5. Добавить безопасный SVG importer

### Новый модуль

```text
src/plotter_processor/svg_importer.py
```

### Поддерживаемые элементы первой версии

```text
path
line
polyline
polygon
rect
circle
ellipse
g
```

Поддержать transforms:

```text
translate
scale
rotate
matrix
```

Transforms должны корректно наследоваться через группы.

### Что делать с fill/stroke

Первая версия ориентирована на line-art.

Правила:

1. `stroke` geometry импортируется как траектория.
2. Basic shape конвертируется в path.
3. Filled-only object:
   - по default ошибка/skip с warning;
   - не пытаться автоматически skeletonize весь рисунок без отдельного режима.
4. Можно добавить явно включаемый режим:

```text
filled_shape_mode: outline
```

Это рисует границу fill, а не центральную линию заливки.

### Безопасность SVG

Полностью запретить/игнорировать с ошибкой:

```text
script
foreignObject
image
use с внешним href
external stylesheets
external fonts
filter
animation
on* event attributes
network URLs
file URLs
```

Использовать безопасный XML parser.

Ограничить:

- размер файла;
- количество XML nodes;
- количество path commands;
- итоговое количество points;
- recursion depth;
- длину строк attribute;
- число transforms.

### Нормализация

1. Прочитать `viewBox`.
2. Применить transforms.
3. Flatten Bézier с существующим curve flattener или общим модулем.
4. Dedupe points.
5. Удалить слишком короткие segments по config.
6. Масштабировать в target box.
7. Применить `contain`, `cover` или `stretch`; default `contain`.
8. Перевести в page-mm-top-left.
9. Проверить bounds.
10. Создать `PlotterStroke` с provenance `element_id`.

### Tests fixtures

Создать собственные минимальные SVG в `tests/fixtures/svg/`:

```text
line.svg
polyline.svg
circle.svg
bezier.svg
nested_transform.svg
multi_path.svg
unsafe_script.svg
unsafe_external_image.svg
huge_path.svg
```

### Желаемый результат

Простой line-art рисунок безопасно превращается в те же paths и G-code, что и текст.

---

## Этап 6. Добавить управление порядком рисования элементов

### Проблема

При наличии текста и рисунка нельзя произвольно перемешивать strokes разных элементов, если это нарушит ожидаемый порядок.

### Что сделать

Поддержать:

```yaml
z_order: 10
travel_group: formula
preserve_stroke_order: true
```

Правила:

1. Сортировать elements по `z_order`, затем по порядку manifest.
2. Оптимизировать travel только внутри разрешённой group.
3. Не переставлять strokes элемента при `preserve_stroke_order: true`.
4. Для text по default сохранять порядок строк и слов.
5. Для SVG можно разрешить локальную оптимизацию.
6. В report показать фактический order.

### Желаемый результат

Рисунок не начинает печататься посередине слова, если manifest этого не просил.

---

## Этап 7. Добавить symbol и composition preview

Создать:

```text
composition-preview.svg
font-source-preview.svg
```

В debug preview показывать:

- bounds каждого element;
- id;
- тип;
- font role;
- fallback glyphs;
- SVG strokes;
- overflow;
- clipping;
- порядок рисования.

Итоговый `plotter-preview.svg` остаётся точным представлением движения ручки.

### Желаемый результат

До генерации G-code пользователь видит, где находится формула и рисунок.

---

## Этап 8. Расширить `paths.json` и `report.json`

### Optional metadata stroke

```json
{
  "element_id": "diagram",
  "element_type": "svg",
  "font_id": null,
  "glyph_name": null,
  "source_path": "assets/circle-diagram.svg"
}
```

Для symbol:

```json
{
  "element_id": "formula",
  "element_type": "text",
  "char": "∫",
  "codepoint": "U+222B",
  "font_role": "math",
  "font_sha256": "...",
  "glyph_name": "integral"
}
```

### Report composition

```json
{
  "composition": {
    "version": 1,
    "element_count": 3,
    "text_elements": 2,
    "svg_elements": 1,
    "fallback_glyph_count": 4,
    "missing_symbols": [],
    "unsafe_svg_features_rejected": [],
    "elements": []
  }
}
```

### Желаемый результат

Каждый stroke можно связать с исходным текстом, символом или рисунком.

---

## Этап 9. Создать demo математической страницы

Не добавлять сторонние font-файлы без лицензии.

Добавить:

```text
examples/math_diagram.plotter.yaml
examples/assets/circle-diagram.svg
examples/assets/axis-plot.svg
```

SVG fixtures создать самостоятельно как простую line-art геометрию.

Demo должен содержать:

```text
Формула площади круга
S = πr²
```

И рисунок окружности с радиусом.

Второй demo:

```text
x² + y² = z²
√16 = 4
x ≤ y
∫ f(x) dx
```

Если default fixture font не содержит symbols, demo README должен объяснять, как передать fallback font.

### Команда

```bash
.venv/bin/python -m plotter_processor compose \
  examples/math_diagram.plotter.yaml \
  --output-dir build/update_6/block_3/demo
```

### Желаемый результат

Пользователь получает страницу A5 с обычным текстом, математическими символами и SVG-рисунком.

---

## Этап 10. Негативные и security-тесты SVG

Проверить, что pipeline отклоняет:

- `<script>`;
- `javascript:` URL;
- внешнюю картинку;
- `file:///...`;
- entity expansion;
- чрезмерно большой path;
- слишком глубокие groups;
- NaN/Infinity coordinates;
- invalid transform;
- пустой SVG;
- SVG без viewBox и без width/height;
- unsupported text element.

Ошибка должна:

- не оставлять `output.gcode`;
- создавать error report;
- содержать element id и источник;
- не раскрывать лишние системные пути, кроме переданного пользователем файла.

### Желаемый результат

SVG importer нельзя использовать как способ загрузить внешний ресурс или перегрузить pipeline бесконечной геометрией.

---

## Этап 11. Финальная проверка Блока 3

### Команды

```bash
make test
make lint

.venv/bin/python -m plotter_processor font-info \
  "$PLOTTER_TEST_PACIFICO_FONT" \
  --coverage math \
  --json build/update_6/block_3/pacifico-coverage.json

.venv/bin/python -m plotter_processor compose \
  examples/math_diagram.plotter.yaml \
  --output-dir build/update_6/block_3/demo
```

Проверить:

- preview;
- paths.json;
- report.json;
- G-code;
- workspace bounds;
- отсутствие нагрева/extrusion;
- корректный fallback font;
- отсутствие внешних SVG resources.

---

## Этап 12. Обязательный отчёт пользователю после Блока 3

Отчёт должен содержать:

### Поддерживаемые символы

| Символ | Codepoint | Основной font | Fallback font | Glyph | Результат |
|---|---|---|---|---|---|

### Поддерживаемые SVG features

| Feature | Поддерживается | Ограничения |
|---|---|---|
| path | да | flattened |
| circle | да | converted to path |
| text | нет | convert to path before import |
| image | нет | запрещено |
| script | нет | запрещено |

### Артефакты

- composition preview;
- plotter preview;
- paths JSON;
- report;
- output G-code;
- font coverage JSON.

### Ограничения

Обязательно прямо написать:

- LaTeX пока не поддерживается;
- PNG/JPG пока не поддерживаются;
- filled illustrations пока не skeletonize автоматически;
- качество математического символа зависит от fallback TTF;
- сложный SVG text нужно заранее конвертировать в path.

---

# 7. Интеграция трёх блоков

После реализации всех блоков выполнить полный сценарий:

1. Взять Pacifico как primary font.
2. Взять отдельный font с математическими symbols как fallback.
3. Подготовить composition с русским текстом.
4. Включить улучшенный centerline.
5. Включить safe word connections.
6. Добавить формулу.
7. Добавить line-art SVG.
8. Сгенерировать A5 preview и G-code.

Пример итоговой страницы:

```text
Обычный подъём пера между буквами должен исчезнуть.
Площадь круга вычисляется по формуле S = πr².
[рисунок окружности с радиусом]
```

## Интеграционные метрики

Сохранить:

```json
{
  "centerline": {
    "problem_glyphs_passed": 3,
    "manual_patches_used": 0
  },
  "connections": {
    "pen_lifts_inside_words_before": 0,
    "pen_lifts_inside_words_after": 0,
    "pen_lifts_saved": 0
  },
  "symbols": {
    "primary_glyphs": 0,
    "fallback_glyphs": 0,
    "missing": 0
  },
  "svg": {
    "elements": 0,
    "strokes": 0,
    "points": 0,
    "unsafe_features": 0
  }
}
```

---

# 8. Общие тесты, обязательные перед завершением UPD_Plotter_6

## 8.1. Unit tests

Проверить:

- config parsing;
- glyph override validation;
- font-specific override selection;
- score calculation;
- width-aware pruning;
- counter metrics;
- tuner;
- patch validation;
- shaped glyph model;
- HarfBuzz adapter;
- anchor selection;
- connector scoring;
- Bézier validation;
- stroke merge;
- fallback font selection;
- Unicode coverage;
- manifest parser;
- SVG parser;
- SVG transforms;
- SVG security;
- provenance serialization.

## 8.2. Integration tests

Проверить:

- old TXT run outline;
- old TXT run centerline;
- DOCX;
- PDF text layer;
- centerline cache hit/miss;
- Pacifico problem glyphs при наличии env font;
- connection off/safe/aggressive;
- fallback symbols;
- composition manifest;
- text + SVG;
- output G-code safety.

## 8.3. Determinism

Два одинаковых запуска должны давать одинаковые:

- centerline cache;
- paths.json;
- SVG geometry;
- report metrics;
- G-code;
- connection decisions;
- SVG import result.

Допускается различие только в явно документированных timestamp fields. Лучше не включать timestamp в сравниваемые артефакты или вынести отдельно.

## 8.4. Performance

Записать:

- время компиляции `ъ`, `ь`, `ы` без cache;
- время с cache;
- время tuner;
- время shaping 1000 chars;
- время connection planner;
- время SVG import для fixture;
- peak memory для большого SVG fixture.

Не допустить, чтобы обычный текст без новых функций стал заметно медленнее.

## 8.5. G-code safety

Проверить отсутствие:

```text
M104
M109
M140
M190
E-координат extrusion
G28 без явного разрешения
координат вне workspace
NaN
Infinity
```

---

# 9. Definition of Done всего обновления

UPD_Plotter_6 считается выполненным только когда выполнены все пункты:

## Блок 1

- `ъ`, `ь`, `ы` имеют улучшенный centerline;
- есть debug до/после;
- есть regression tests;
- есть общий алгоритмический improvement;
- при необходимости есть безопасный font-specific patch;
- пользователь получил отдельный отчёт.

## Блок 2

- применяется корректное позиционирование glyphs или явно описанный ограниченный fallback;
- entry/exit anchors вычисляются;
- safe connectors проходят validation;
- strokes объединяются внутри слов;
- подъёмы измеряются;
- пробелы/строки не соединяются;
- пользователь получил отдельный отчёт.

## Блок 3

- coverage math symbols проверяется;
- fallback font chain работает;
- composition model существует;
- `.plotter.yaml` читается;
- line-art SVG импортируется безопасно;
- text + formula + drawing выходят в единый G-code;
- пользователь получил отдельный отчёт.

## Общие требования

- `make test` проходит;
- `make lint` проходит;
- README обновлён;
- CLI help обновлён;
- новые конфиги документированы;
- старый CLI не сломан;
- output безопасен;
- итоговые артефакты сохранены;
- известные ограничения перечислены честно.

---

# 10. Рекомендуемая структура новых файлов

Ориентировочно:

```text
src/plotter_processor/
  text_shaper.py
  word_connector.py
  connection_models.py
  unicode_coverage.py
  font_fallback.py
  composition_models.py
  composition_reader.py
  composition_pipeline.py
  svg_importer.py
  svg_security.py

src/plotter_processor/centerline_font/
  candidate_score.py
  counter_analysis.py
  glyph_patch.py
  glyph_tuner.py
  stroke_roles.py
  anchors.py

examples/
  math_diagram.plotter.yaml
  assets/
    circle-diagram.svg
    axis-plot.svg

tests/
  test_centerline_candidate_score.py
  test_centerline_counter_analysis.py
  test_centerline_glyph_patch.py
  test_centerline_glyph_tuner.py
  test_text_shaper.py
  test_word_connector.py
  test_connection_anchors.py
  test_font_fallback.py
  test_unicode_coverage.py
  test_composition_reader.py
  test_svg_importer.py
  test_svg_security.py
  test_composition_pipeline.py
  fixtures/svg/
  visual/update_6/

tools/
  update_6_baseline.py
  compare_update_6.py
  update_centerline_snapshots.py
```

Не создавать все модули механически, если часть логики естественно помещается в существующий файл. Но не складывать candidate scoring, shaping, connector и SVG import в один `pipeline.py`.

---

# 11. Обновление README

Добавить разделы:

```text
Centerline quality tuning
Font-specific glyph overrides
Manual centerline patches
Word connections
Layout engines
Fallback fonts
Unicode math symbols
Composition manifests
SVG line-art import
Security limitations
```

Привести команды:

```bash
# Диагностика глифов
plotter-processor compile-centerline-font ...

# Tuner
plotter-processor tune-centerline-glyphs ...

# Соединение слов
plotter-processor run ... --connections safe

# Проверка math coverage
plotter-processor font-info ... --coverage math

# Композиция текста и рисунка
plotter-processor compose page.plotter.yaml ...
```

Объяснить разницу:

```text
Unicode math symbols != LaTeX layout
SVG line-art != raster image vectorization
safe connections != соединение любой пары букв
font-specific patch != универсальный алгоритм
```

---

# 12. Финальный отчёт пользователю после всех трёх блоков

Codex должен предоставить единый итоговый отчёт.

## 12.1. Краткий результат

```text
Блок 1: качество сложных глифов — выполнено/частично.
Блок 2: соединение букв — выполнено/частично.
Блок 3: symbols и SVG — выполнено/частично.
```

## 12.2. Таблица ключевых метрик

| Метрика | Baseline | После Блока 1 | После Блока 2 | После Блока 3 |
|---|---:|---:|---:|---:|
| Problem glyphs needs_review | | | | |
| Подъёмы внутри слов | | | | |
| Centerline cache glyphs | | | | |
| Fallback symbols | | | | |
| SVG elements | | | | |
| Tests passed | | | | |

## 12.3. Файлы и артефакты

Указать реальные пути:

```text
build/update_6/baseline/
build/update_6/block_1/
build/update_6/block_2/
build/update_6/block_3/
build/update_6/integration/
```

## 12.4. Рекомендованные defaults

Codex должен обосновать:

- какой skeleton method/config оставить default;
- нужен ли Pacifico-specific override;
- нужен ли manual patch;
- включать ли `connections: safe` по умолчанию;
- какой layout engine использовать;
- какой SVG mode считать стабильным;
- какие features оставить experimental.

## 12.5. Известные ограничения

Не скрывать:

- буквы, которые всё ещё выглядят хуже;
- пары букв, которые не удалось безопасно соединить;
- remaining pen lifts;
- symbols, отсутствующие в font chain;
- unsupported SVG features;
- отсутствие LaTeX;
- отсутствие PNG/JPG vectorization;
- необходимость физического теста на принтере.

---

# 13. Порядок реализации без пропусков

Codex должен выполнять работу именно в таком порядке:

```text
0. Baseline

БЛОК 1
1. Glyph debug
2. Candidate score
3. Width-aware pruning
4. Counter preservation
5. Extended overrides
6. Parameter tuner
7. Font-specific patch fallback
8. Visual regression
9. Block 1 report

БЛОК 2
10. Shaped glyph model
11. Text shaping / positioning
12. Stroke roles
13. Entry/exit anchors
14. Pair compatibility
15. Smooth connector
16. Word route merge
17. Connection modes
18. Metrics/debug
19. Regression corpus
20. Physical check
21. Block 2 report

БЛОК 3
22. Font coverage
23. Fallback font chain
24. Document elements
25. Composition manifest
26. Safe SVG importer
27. Element draw order
28. Composition preview
29. Metadata/report
30. Demo page
31. Security tests
32. Block 3 report

33. Full integration
34. README
35. Final report
```

Не начинать с ручного исправления трёх букв. Сначала создать диагностику и baseline.

Не начинать соединение букв до введения word boundaries и безопасных anchors.

Не начинать поддержку PNG/JPG в рамках этого update.

---

# 14. Главный желаемый результат для пользователя

После выполнения UPD_Plotter_6 пользователь должен получить следующую практическую возможность:

1. Запустить Pacifico через centerline pipeline.
2. Получить читаемые `ъ`, `ь`, `ы`.
3. Напечатать рукописное слово с существенно меньшим количеством подъёмов ручки.
4. Увидеть в отчёте, какие пары букв были соединены и какие не были.
5. Написать строку с математическими Unicode-символами через fallback TTF.
6. Добавить на страницу простой SVG-рисунок.
7. Получить единый preview, paths.json и безопасный G-code.
8. Проверить отдельный отчёт после каждого блока, а не только итоговое сообщение.

Качество и безопасность важнее формального утверждения, что «все буквы соединены» или «все картинки поддерживаются».
