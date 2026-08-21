# UPD_Plotter_8 — исправление mixed-layout, ускорение конвертации, улучшение соединения букв и очистка проекта

## Назначение

Этот файл — пошаговая инструкция для Codex по доработке проекта:

`https://github.com/BMSTU-LYGO/plotter-proc`

Работать нужно **в уже существующей ветке**:

`upd/plotter-7-layout-math-lines-tables`

**Новую ветку создавать нельзя.**

Обновление состоит из трёх блоков:

1. Исправить раскладку смешанных документов: текст + изображения + LaTeX + многостраничность.
2. Максимально ускорить конвертацию и убрать тяжёлые тесты, которые прогоняют весь pipeline.
3. Улучшить соединение букв, убрать ложные линии и очистить кодовую базу от старых тестов и рудиментарного кода.

Работу выполнять **строго по блокам**. После каждого блока Codex обязан остановиться, написать пользователю отдельный отчёт, показать изменённые файлы, тесты, артефакты, метрики до/после и дождаться команды на продолжение.

---

# 0. Обязательные правила

## 0.1. Работать в текущей ветке

Перед изменениями:

```bash
git fetch
git checkout upd/plotter-7-layout-math-lines-tables
git pull
git status
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
```

В отчёте сохранить имя ветки и SHA.

### Запрещено

```bash
git checkout -b ...
git switch -c ...
```

Новую ветку не создавать.

## 0.2. Не откатывать уже работающие возможности

Сохранить поддержку:

- TXT / DOCX / PDF;
- centerline и outline TTF;
- изображения;
- многостраничность и page numbers;
- page-change G-code;
- LaTeX / MathText;
- PDF math;
- `reflow / hybrid / preserve`;
- таблицы, линии, стрелки, подчёркивания;
- рукописные соединения;
- SVG preview;
- `paths.json`;
- безопасный G-code.

Цель UPD_Plotter_8 — починить текущую архитектуру, а не создать второй pipeline.

## 0.3. G-code safety

После оптимизаций по-прежнему запрещены по умолчанию:

```text
M104
M109
M140
M190
E...
```

Также не добавлять `G28` без разрешения, не парковать головку с опущенным пером, не выходить за workspace и не удалять safety validation ради скорости.

---

# 1. Что важно в текущем коде

Codex должен перепроверить актуальный HEAD, но в текущей ветке особое внимание обратить на следующие места.

## 1.1. `document_paginator.py`

`paginate_document()` одновременно занимается текстом, формулами, изображениями, exclusion zones, таблицами, page breaks и metadata.

В `hybrid/preserve` часть изображений предварительно размещается до основного прохода по элементам, после чего exclusion zones могут начать влиять на текст раньше фактического anchor.

Проверить гипотезу:

```text
картинка относится к более позднему source_order
→ exclusion zone активна с начала страницы
→ ранний текст считает область занятой
→ cursor_y перескакивает вниз
→ появляются огромные пустые интервалы
```

Это очень похоже на показанный пользователем дефект, но нужно доказать trace-логом.

## 1.2. `pipeline.py`

Сейчас один `run_pipeline()` последовательно делает:

```text
read
→ layout
→ centerline compile
→ previews
→ paths
→ handwriting
→ simplification
→ validation
→ serialization
→ gcode
→ analysis
→ reports
```

На многостраничных заданиях есть повторная работа. Оптимизировать только после измерений.

## 1.3. `handwriting.py`

Текущий `route_words()` в основном соединяет endpoint main stroke одной буквы с endpoint следующей через cubic Bezier после простых проверок distance/vertical/tangent.

При этом уже существуют:

- `StrokeAnchor`;
- `GlyphConnectionCandidate`;
- `entry_exit_anchors()`;
- config-параметры corridor/collision.

Нужно либо реально интегрировать эту архитектуру, либо удалить неиспользуемые части.

---

# 2. Подготовка общего regression fixture

Создать воспроизводимый mixed-document:

```text
tests/fixtures/layout/mixed_layout_demo.docx
tests/fixtures/layout/mixed_layout_demo.pdf
```

или детерминированный генератор:

```text
tools/generate_mixed_layout_fixture.py
```

Содержание:

1. Заголовок.
2. Несколько строк текста.
3. Картинка справа сверху.
4. Текст с обтеканием.
5. Inline LaTeX:
   `$x^2 + y^2 = r^2$`
6. Block LaTeX:
   `\int_0^\infty x^2 e^{-x}\,dx = 2`
7. Ещё несколько абзацев.
8. Вторая картинка в середине текста.
9. Достаточно текста минимум на две страницы.

До изменений создать baseline:

```bash
python -m plotter_processor run \
  tests/fixtures/layout/mixed_layout_demo.pdf \
  --font assets/1.ttf \
  --font-mode centerline \
  --page A4 \
  --size normal \
  --document-layout hybrid \
  --latex auto \
  --latex-stroke-mode centerline \
  --layout-debug \
  --output-dir build/upd8-baseline
```

Зафиксировать wall-clock time, число страниц, glyphs, strokes, points, images, formulas, warnings, preview и layout-debug.

---

# БЛОК 1. Исправить mixed-layout

## 3. Цель

Документ должен выглядеть как нормальный поток, а не набор фрагментов, разнесённых по высоте страницы.

Нельзя искусственно делать vertical justification. Нужны стабильные:

```text
line_advance
paragraph_spacing
image spacing
block formula spacing
```

Большой vertical gap разрешён только если он объясняется явным blank paragraph, block element, page break или реально пересекающей строку anchored image.

---

# 4. Шаг 1.1. Найти точную причину вертикальных скачков

Для каждого размещаемого элемента временно/через debug записывать:

```json
{
  "element_id": "...",
  "type": "text/image/math/table",
  "source_order": 12,
  "source_bbox": {},
  "anchor_type": "...",
  "wrap_mode": "...",
  "cursor_y_before": 48.2,
  "cursor_y_after": 55.7,
  "active_exclusion_zones": [],
  "page_index": 0
}
```

Нужно точно ответить:

- какой элемент вызывает скачок;
- какая exclusion zone активна;
- относится ли она к текущему тексту;
- не резервируется ли место под более позднюю картинку;
- не превращается ли source `bbox.y` обычного текста в искусственный gap.

Не рефакторить вслепую.

---

# 5. Шаг 1.2. Разделить три системы позиционирования

Разделить:

```text
Flow position
    место следующего flowing element.

Anchored position
    положение floating object относительно page/margin/paragraph.

Source position
    координаты элемента в исходном документе.
```

Не использовать `cursor_y` одновременно для всех трёх задач.

Можно ввести внутреннюю модель:

```python
@dataclass(slots=True)
class AnchoredPlacement:
    element_id: str
    source_order: int
    target_rect: RectMM
    wrap_mode: str
    anchor_element_id: str | None
    active: bool = False
```

Название можно изменить.

---

# 6. Шаг 1.3. Лениво активировать exclusion zones

## Page/margin-relative image

Предварительное placement допустимо, но zone должна влиять только на строки, реально пересекающие её Y-range.

## Paragraph-relative image

Нельзя резервировать место с начала страницы.

Логика:

```text
дойти до anchor paragraph/source_order
→ активировать image
→ зарегистрировать exclusion zone
→ продолжить layout
```

Если точного anchor id нет, безопасный fallback — активация при достижении `source_order` картинки.

### Желаемый результат

Более поздняя картинка больше не сдвигает ранние абзацы вниз.

---

# 7. Шаг 1.4. Нормализовать vertical rhythm

Для текста использовать только:

```text
line_advance
paragraph_spacing
explicit blank paragraph
block spacing
```

В `reflow/hybrid` не превращать абсолютный source Y обычного текста в обязательный отступ.

Для строк одного абзаца:

```text
delta_y ≈ line_advance
```

Для абзацев:

```text
delta_y ≈ line_advance + paragraph_spacing
```

Добавить layout metric:

```json
{
  "max_unexplained_vertical_gap_mm": 0.0,
  "unexplained_vertical_gap_count": 0
}
```

Gap считать подозрительным, например если он больше `2.5 * line_advance` и нет зарегистрированной причины.

---

# 8. Шаг 1.5. Исправить положение изображений

## Inline image

Должна идти в потоке:

```text
абзац
картинка
следующий абзац
```

## Floating page/margin image

Сохранять сторону, относительные X/Y, width/height ratio и wrap mode.

## Floating paragraph image

Использовать:

```text
anchor paragraph + local x/y offset
```

а не голую абсолютную координату source page.

Если target page другого размера, использовать единый contain scale, не растягивая X/Y независимо.

---

# 9. Шаг 1.6. Исправить обтекание

Для `square` wrap:

```text
+-----------------------------+
| текст текст      +--------+ |
| текст текст      | image  | |
| текст текст      |        | |
| текст текст      +--------+ |
| текст снова на всю ширину   |
+-----------------------------+
```

`available_intervals()` должен учитывать только зоны, которые:

- активны;
- относятся к текущей странице;
- пересекаются с текущей line box по Y.

Зоны выше текущей строки деактивировать/удалять.

---

# 10. Шаг 1.7. LaTeX в общем потоке

## Inline

```latex
Текст $x^2 + y^2$ продолжается здесь.
```

должен оставаться одной логической line box, если помещается.

## Block

Использовать только configured:

```text
block_spacing_before
formula height
block_spacing_after
```

без лишнего source-bbox gap.

## PDF visual math

Source bbox использовать для логической привязки, но в `hybrid` не заставлять весь flow прыгать на абсолютный исходный Y.

---

# 11. Шаг 1.8. Пагинация

Проверить 1, 2 и 3+ страниц.

При page break:

1. завершить текущую страницу;
2. создать чистый page state;
3. не переносить старые exclusion zones;
4. не терять pending image anchor;
5. не дублировать image/formula;
6. не терять первый абзац новой страницы.

Страница не должна заканчиваться на 30–40% высоты из-за элемента, который находится дальше по source order.

---

# 12. Шаг 1.9. Default layout mode

Проверить поведение:

```text
TXT  → reflow
DOCX → hybrid
PDF  → hybrid или preserve
```

Не менять default вслепую. `preserve` оставить для явного сохранения source geometry. Для rich DOCX/PDF предпочтительным должен быть качественно работающий `hybrid`.

---

# 13. Шаг 1.10. Layout debug

Добавить/улучшить слои:

```text
source bbox
mapped bbox
final bbox
anchor point
active exclusion zone
text line box
content rect
```

Желательно сохранить:

```text
layout-debug/trace.json
```

с `placement_reason`, source/target coordinates и shift.

---

# 14. Тесты блока 1

Использовать component tests:

```text
test_flow_layout.py
test_hybrid_image_layout.py
test_exclusion_zones.py
test_document_paginator.py
test_latex_layout.py
test_layout_mapping.py
```

Проверить:

1. Future image zone не влияет на предыдущий текст.
2. Paragraph image активируется только около anchor.
3. Page image влияет только на пересекающиеся строки.
4. Zone перестаёт влиять после `zone.bottom`.
5. Обычные строки имеют стабильный line spacing.
6. Нет необъяснимого большого gap.
7. Inline LaTeX остаётся в строке.
8. Block LaTeX имеет только configured spacing.
9. Image после formula сохраняет source order.
10. Mixed document переносится на следующую страницу.
11. Image не дублируется.
12. Старые zones не переходят на новую страницу.
13. `preserve` сохраняет geometry.
14. TXT `reflow` не ломается.

---

# 15. Критерии приёмки блока 1

- исчезли огромные необъяснимые интервалы;
- текст идёт естественно сверху вниз;
- картинка справа остаётся справа;
- anchored images находятся около логического source location;
- text wrap корректный;
- formula placement корректный;
- multi-page работает;
- элементы не теряются и не дублируются;
- preview соответствует `paths.json`;
- G-code безопасен.

Визуально должно быть примерно:

```text
ЗАГОЛОВОК

текст текст текст            +---------+
текст текст текст            | рисунок |
текст текст текст            |         |
текст текст текст            +---------+
текст снова на всю ширину

inline formula внутри строки

          block formula

следующий абзац
```

а не набор строк с огромными пустотами.

---

# 16. Отчёт после блока 1

```markdown
## Блок 1 завершён — mixed layout

### Причина бага
### Что изменено
### Какие файлы изменены
### Как теперь работает layout
### Как исправлено положение изображений
### Как исправлены LaTeX и pagination
### Тесты
### Демонстрационные артефакты
### До / после
### Ограничения
### Git SHA
```

После отчёта остановиться.


---

# БЛОК 2. Максимально ускорить конвертацию и убрать full-pipeline тесты

# 17. Цель блока 2

Сократить время:

```text
input document
→ paths / preview / G-code / report
```

Особенно важны:

- быстрый цикл работы Codex;
- быстрый локальный development loop;
- повторная обработка того же документа;
- повторное использование того же шрифта;
- отсутствие тяжёлых end-to-end тестов в каждом `pytest`.

Нельзя ускорять за счёт ухудшения geometry или отключения safety.

---

# 18. Шаг 2.1. Добавить stage timings

До оптимизации добавить лёгкое измерение через:

```python
time.perf_counter()
```

В `report.json`:

```json
{
  "performance": {
    "total_ms": 0,
    "read_document_ms": 0,
    "layout_ms": 0,
    "font_compile_ms": 0,
    "image_vectorization_ms": 0,
    "latex_render_ms": 0,
    "build_paths_ms": 0,
    "handwriting_ms": 0,
    "simplification_ms": 0,
    "preview_ms": 0,
    "gcode_ms": 0,
    "report_ms": 0
  }
}
```

Если stage вызывается много раз, хранить `calls`, `total_ms`, `max_ms`.

---

# 19. Шаг 2.2. Benchmark вынести из pytest

Создать:

```text
tools/benchmark_conversion.py
```

Он должен:

1. принимать input;
2. принимать font;
3. запускать conversion N раз;
4. отдельно считать cold run;
5. отдельно считать warm run;
6. выводить median;
7. сохранять JSON.

Пример:

```bash
python tools/benchmark_conversion.py \
  tests/fixtures/layout/mixed_layout_demo.pdf \
  --font assets/1.ttf \
  --runs 3 \
  --output build/benchmark-upd8.json
```

Benchmark не должен запускаться обычным `pytest`.

---

# 20. Шаг 2.3. Убрать full-pipeline tests из default test suite

Найти:

```bash
rg "run_pipeline\(" tests
rg "plotter_processor run" tests
```

Проверить тесты, которые ради одной проверки запускают весь:

```text
PDF/DOCX
→ layout
→ centerline
→ previews
→ paths
→ G-code
```

Кандидаты на аудит:

```text
tests/test_pipeline.py
tests/test_document_image_pipeline.py
tests/test_latex_pipeline.py
tests/test_latex_centerline_integration.py
tests/test_multipage_pipeline.py
tests/test_pdf_math_pipeline.py
tests/test_semantic_block3_pipeline.py
tests/test_motion_pipeline.py
tests/test_speed_benchmark.py
tests/test_update_6_baseline.py
```

Не удалять автоматически по имени. Сначала понять, что каждый тест защищает.

### Правило замены

Если проверяется reader — вызывать reader.

Если layout — paginator/layout.

Если connector — connector.

Если G-code — маленький готовый `PathDocument` + exporter.

Если image vectorization — image vectorizer.

Если LaTeX — renderer/layout.

Не запускать полный pipeline для проверки одного поля.

---

# 21. Шаг 2.4. Full smoke перенести в ручную команду

Оставить один ручной сценарий:

```text
tools/smoke_full_pipeline.py
```

или:

```text
make smoke
```

Он нужен перед релизом, но не должен тормозить каждую итерацию.

---

# 22. Шаг 2.5. Профилировать реальные hotspots

После timings один раз выполнить:

```bash
python -m cProfile -o build/pipeline.prof ...
```

Смотреть cumulative time.

Оптимизировать только реально тяжёлые места.

---

# 23. Шаг 2.6. Не генерировать одинаковые font previews на каждой странице

Проверить текущую многостраничную логику.

Желательная схема:

## Job-level

Один раз:

```text
build/font-preview.svg
build/centerline-font-preview.svg
```

для union уникальных glyphs всего задания.

## Page-level

На каждой странице:

```text
pages/page-XXX/plotter-preview.svg
pages/page-XXX/paths.json
pages/page-XXX/page.gcode
```

Не строить тяжёлый page-level font preview, если он не нужен.

---

# 24. Шаг 2.7. Компилировать centerline glyphs один раз на job

До компиляции собрать:

```text
unique body chars
∪
unique page-number chars
```

и минимизировать число вызовов `compile_centerline_font()`.

Не компилировать одинаковые glyphs отдельно для каждой страницы.

---

# 25. Шаг 2.8. Cache тяжёлых преобразований

## Font centerline cache

Key:

```text
font sha256
+
centerline config version
+
glyph
```

Существующий cache не ломать.

## Image vectorization cache

Одинаковая картинка не должна повторно проходить:

```text
preprocess
→ threshold
→ skeleton
→ graph
→ routing
```

Key:

```text
image sha256
+
mode
+
relevant image config
```

Хранить local geometry; placement делать отдельно.

## LaTeX cache

Key:

```text
expression
+
display mode
+
stroke mode
+
render_ppmm
+
relevant latex config
```

Хранить local strokes.

## PDF visual math cache

Key:

```text
clip/image hash
+
render config
```

---

# 26. Шаг 2.9. Cache статистику вывести в report

```json
{
  "cache": {
    "font": {"hits": 0, "misses": 0},
    "images": {"hits": 0, "misses": 0},
    "latex": {"hits": 0, "misses": 0}
  }
}
```

Пользователь должен видеть, почему warm run быстрее.

---

# 27. Шаг 2.10. Ускорить измерение текста

Проверить `_text_width()`, shaping и line breaking.

Если одна и та же буква/token измеряется много раз, использовать memoization:

```text
(font identity, text, scale, shaping options)
→ advance
```

Cache ограничить жизнью job или безопасным размером.

---

# 28. Шаг 2.11. По возможности убрать `PageSpec(... height=1_000_000)` для paragraph line breaking

Сейчас обычный абзац может раскладываться на искусственной очень высокой странице.

Лучше выделить чистую функцию:

```python
layout_paragraph_lines(...)
```

которая возвращает line groups без page semantics.

Потом paginator распределяет линии по реальным страницам.

Плюсы:

- меньше лишней работы;
- проще mixed layout;
- проще cache;
- проще тесты;
- меньше риска page-layout side effects.

Но делать этот рефакторинг только если он оправдан profiling и не создаёт огромный риск.

---

# 29. Шаг 2.12. Debug artifacts только по debug-флагам

Проверить:

```text
latex-debug
math-debug
image-debug
layout-debug
semantic-debug
connection-debug
```

Обычный production run не должен генерировать:

- masks;
- skeleton PNG/SVG;
- overlays;
- огромный debug JSON.

---

# 30. Шаг 2.13. Уменьшить лишнюю сериализацию

Проверить:

- многократный `json.dumps`;
- повторное глубокое `asdict()`;
- копирование сотен тысяч points;
- повторную сериализацию geometry.

Не делать микрооптимизацию без profiler evidence.

---

# 31. Шаг 2.14. Не добавлять multiprocessing первым решением

Сначала:

1. убрать повторную работу;
2. добавить cache;
3. убрать повторные previews;
4. ускорить layout;
5. уменьшить test overhead.

Только потом, если всё ещё нужно, рассматривать parallel image processing.

---

# 32. Критерии производительности

Сравнивать на одинаковом:

```text
input
font
layout config
machine config
hardware
```

Измерить:

```text
baseline cold
baseline warm
new cold
new warm
```

Желательный ориентир:

```text
cold: минимум ~1.5x быстрее
warm: минимум ~2x быстрее
```

Если фактический bottleneck не позволяет — показать честные цифры и объяснение.

---

# 33. Test-suite performance

Измерить:

```bash
time pytest -q
```

до и после.

Default pytest не должен запускать реальные full conversions.

---

# 34. Критерии приёмки блока 2

- есть stage timings;
- есть benchmark tool;
- есть baseline;
- есть after metrics;
- повторная работа удалена;
- full-pipeline tests убраны из default pytest;
- component coverage сохранён;
- conversion заметно быстрее;
- warm cache работает;
- geometry не изменилась неожиданно;
- safety сохранена.

---

# 35. Отчёт после блока 2

```markdown
## Блок 2 завершён — производительность

### Baseline
### Найденные hotspots
### Что оптимизировано
### Cache
### Какие full-pipeline tests были удалены/заменены
### Время pytest до/после
### Conversion benchmark до/после
### Cold run
### Warm run
### Изменённые файлы
### Ограничения
### Git SHA
```

После отчёта остановиться.


---

# БЛОК 3. Улучшить соединение букв и очистить кодовую базу

# 36. Цель блока 3

Решить две задачи:

1. убрать лишние/ложные линии между буквами;
2. удалить из проекта то, что больше реально не нужно.

Главное правило:

```text
лучше один дополнительный подъём пера,
чем неправильная линия через букву
```

Нельзя максимизировать число соединений ценой визуального брака.

---

# 37. Шаг 3.1. Собрать regression corpus проблемных слов

Создать:

```text
tests/fixtures/joining/problem_words.txt
```

Добавить:

- реальные слова, где сейчас видны лишние линии;
- слова с `ъ`;
- слова с `ь`;
- слова с `ы`;
- слова с `й`;
- слова с `ё`;
- слова с высокими и низкими точками соединения;
- пунктуацию;
- короткие и длинные слова.

Достаточно 30–50 слов.

Сохранять:

```text
build/joining-before.svg
build/joining-after.svg
```

---

# 38. Шаг 3.2. Использовать anchors, а не только endpoints main stroke

В проекте уже есть:

```text
StrokeAnchor
GlyphConnectionCandidate
entry_exit_anchors()
```

Нужно либо интегрировать их в production `route_words()`, либо удалить как мёртвую архитектуру.

Предпочтительно интегрировать.

Для каждой пары букв:

```text
left glyph
→ candidate exit anchors

right glyph
→ candidate entry anchors
```

После этого выбирать лучший безопасный вариант.

---

# 39. Шаг 3.3. Scoring connection candidate

Для кандидата учитывать:

```text
distance
vertical offset
tangent mismatch
backtracking
corridor quality
collision count
connector length
```

Можно использовать `GlyphConnectionCandidate`.

Пример логики score:

```text
score =
    distance penalty
  + tangent penalty
  + vertical penalty
  + collision penalty
  + outside-ink penalty
```

Точная формула не важна. Важно, чтобы решение было детерминированным и объяснимым.

---

# 40. Шаг 3.4. Реально использовать corridor validation

Проверить config:

```yaml
min_corridor_inside_ratio
allow_connector_outside_ink
outside_ink_margin_mm
```

Если параметры остаются, они должны реально участвовать в алгоритме.

Для connector:

1. discretize curve;
2. проверить допустимый corridor;
3. посчитать inside ratio;
4. проверить пересечения с чужими strokes;
5. reject, если линия создаёт диагональный shortcut через букву.

### Safe mode

```text
сомнительно → reject
```

### Aggressive mode

Можно увеличить допустимую distance/tangent, но collision checks не отключать.

---

# 41. Шаг 3.5. Не создавать Bezier, если буквы уже соприкасаются

Если:

```text
distance < epsilon
```

или strokes реально пересекаются около границы glyphs, использовать:

```text
snap / merge endpoints
```

а не отдельный connector.

Это должно убрать короткие лишние «усики».

---

# 42. Шаг 3.6. Reject плохие synthetic connectors

Не создавать connector, если:

- gap больше max distance;
- большой vertical offset;
- большой tangent mismatch;
- curve идёт назад влево;
- connector пересекает внутренний stroke;
- connector проходит через secondary stroke/diacritic;
- corridor ratio ниже threshold;
- collision count выше допустимого.

Не соединять любой ценой.

---

# 43. Шаг 3.7. Диакритика остаётся отдельной

Для `ё`, `й` и похожих glyphs:

- main cursive body может участвовать в word route;
- dots/diacritics должны оставаться secondary strokes;
- connector не должен проходить через них.

---

# 44. Шаг 3.8. Убрать overlap connector с существующим stroke

Если начало connector повторяет конец левой буквы или конец connector повторяет начало правой:

```text
trim duplicated segment
```

Делать dedupe только около boundary connector.

Не применять глобальный aggressive dedupe ко всей centerline geometry, потому что retrace внутри glyph иногда нужен routing-алгоритму.

---

# 45. Шаг 3.9. Улучшить `connection-debug`

В SVG показать:

- exit anchor;
- entry anchor;
- candidate curve;
- accepted curve;
- rejected curve;
- collision point.

Также сохранить JSON:

```text
connection-debug.json
```

Пример:

```json
{
  "left": "л",
  "right": "и",
  "accepted": false,
  "reason": "collision",
  "distance_mm": 1.1,
  "tangent_mismatch_deg": 23,
  "corridor_inside_ratio": 0.42
}
```

---

# 46. Шаг 3.10. Метрики соединений

В report:

```json
{
  "handwriting": {
    "pairs_total": 0,
    "accepted": 0,
    "rejected": 0,
    "rejected_distance": 0,
    "rejected_tangent": 0,
    "rejected_collision": 0,
    "rejected_corridor": 0,
    "snapped_existing_contact": 0,
    "connector_length_mm": 0
  }
}
```

---

# 47. Шаг 3.11. Убрать дублирующий config

Проверить одновременное наличие:

```yaml
handwriting:
  joining:
```

и:

```yaml
connections:
```

Оставить один canonical section, желательно:

```yaml
connections:
  enabled: false
  mode: safe
  ...
```

Если backward compatibility нужна, старый ключ временно принимать с warning, но default config должен содержать один источник истины.

---

# 48. Шаг 3.12. Решить судьбу `connection_models.py`

Варианты:

## A. Использовать

Интегрировать `StrokeAnchor` и `GlyphConnectionCandidate` в production algorithm.

## B. Удалить

Если после упрощения модели не нужны.

Не оставлять неиспользуемые структуры «на потом».

---

# 49. Шаг 3.13. Аудит тестов

Выполнить:

```bash
find tests -type f -name "test_*.py" | sort
```

Для каждого файла определить, что он реально защищает.

Удалить:

- тесты старой архитектуры;
- дубли;
- update-specific tests, которые больше не нужны;
- tests удалённых config fields;
- end-to-end tests, уже заменённые component tests;
- старые visual regressions, если они полностью дублируются новым corpus.

Особенно проверить:

```text
test_update_6_baseline.py
test_centerline_visual_regression.py
test_centerline_corpus.py
test_pipeline.py
```

Не удалять полезные centerline unit tests только ради уменьшения количества файлов.

---

# 50. Шаг 3.14. Аудит production modules

Выполнить:

```bash
find src/plotter_processor -type f -name "*.py" | sort
```

Для каждого файла проверить:

- импортируется ли он;
- вызываются ли public functions;
- нет ли superseded implementation;
- нет ли двух реализаций одной задачи.

Особое внимание:

```text
old layout helpers
old image placement helpers
old connection helpers
old pagination compatibility
old benchmark helpers
old config compatibility
```

---

# 51. Шаг 3.15. Удалить unused imports/functions/constants

Запустить:

```bash
ruff check .
```

Для подозрительных символов использовать:

```bash
rg "function_name" .
```

Не удалять CLI entry points только потому, что обычный reference search их не нашёл.

---

# 52. Шаг 3.16. Упростить `pipeline.py`

После блоков 1–2 посмотреть на `run_pipeline()`.

Если он остаётся слишком большим, выделить внутренние stages:

```text
prepare_job()
layout_job()
compile_job_font()
build_page_paths()
finalize_page()
export_job()
```

Не создавать десятки лишних классов. Цель — читаемый pipeline, а не abstraction ради abstraction.

---

# 53. Шаг 3.17. Удалить устаревшую config-путаницу

Проверить:

```yaml
document_import:
  pdf_layout:
```

и:

```yaml
document_layout:
  mode:
```

Если старый config key не используется — удалить его из default config.

CLI alias `--pdf-layout` можно сохранить как compatibility alias к `--document-layout`.

В config должен быть один source of truth.

---

# 54. Шаг 3.18. Обновить README

README должен описывать только актуальное:

- document layout modes;
- benchmark conversion;
- connection modes;
- manual smoke;
- актуальные config keys.

Удалить устаревшие команды и параметры.

---

# 55. Финальные tests соединений

Проверить:

1. Нормальное соединение двух букв.
2. Уже соприкасающиеся буквы — нет лишнего connector.
3. Далёкие буквы — pen lift.
4. Большой vertical offset — pen lift.
5. Tangent mismatch — pen lift.
6. Collision — pen lift.
7. Плохой corridor — pen lift.
8. Connector не пересекает diacritic.
9. `ё` сохраняет точки отдельно.
10. `й` сохраняет secondary stroke отдельно.
11. Между словами нет соединения.
12. Через punctuation нет соединения.
13. Backward connector запрещён.
14. Результат детерминирован.
15. Regression corpus не создаёт ложных диагоналей.

---

# 56. Критерии приёмки блока 3

- исчезли лишние линии;
- сомнительные пары дают pen lift;
- хорошие пары продолжают соединяться;
- connection metrics появились;
- anchor models либо используются, либо удалены;
- duplicate connection config удалён;
- старые full-pipeline tests удалены;
- старые update-specific tests удалены, если больше не нужны;
- superseded production code очищен;
- `ruff check .` проходит;
- component tests проходят;
- manual smoke проходит отдельно.

---

# 57. Отчёт после блока 3

```markdown
## Блок 3 завершён — соединения и cleanup

### Причина лишних линий
### Новый алгоритм выбора соединения
### Когда теперь создаётся pen lift
### До / после на problem words
### Какие production files удалены/объединены
### Какие tests удалены
### Какие tests остались и что они защищают
### Какие config keys удалены
### Время pytest
### Manual smoke
### Git SHA
```

После отчёта остановиться.

---

# 58. Финальный manual smoke всего UPD_Plotter_8

## TXT

```bash
python -m plotter_processor run \
  examples/input.txt \
  --font assets/1.ttf \
  --font-mode centerline \
  --page A5 \
  --size normal \
  --output-dir build/final-txt
```

## Mixed DOCX

```bash
python -m plotter_processor run \
  tests/fixtures/layout/mixed_layout_demo.docx \
  --font assets/1.ttf \
  --font-mode centerline \
  --page A4 \
  --size normal \
  --document-layout hybrid \
  --latex auto \
  --connections safe \
  --output-dir build/final-docx
```

## Mixed PDF

```bash
python -m plotter_processor run \
  tests/fixtures/layout/mixed_layout_demo.pdf \
  --font assets/1.ttf \
  --font-mode centerline \
  --page A4 \
  --size normal \
  --document-layout hybrid \
  --pdf-math auto \
  --connections safe \
  --output-dir build/final-pdf
```

---

# 59. Что проверить в финальных артефактах

Для каждого job:

```text
report.json
job.json
plotter-preview.svg
paths.json / page paths
output.gcode
```

Проверить:

- правильное число страниц;
- правильный порядок текста;
- правильное положение картинок;
- правильное положение формул;
- отсутствие огромных ложных пробелов;
- отсутствие лишних линий между буквами;
- page numbers;
- park/pause;
- отсутствие нагрева;
- отсутствие extrusion;
- отсутствие выхода за workspace.

---

# 60. Итоговые метрики для пользователя

Codex должен показать таблицу:

| Метрика | До UPD_Plotter_8 | После |
|---|---:|---:|
| Conversion cold, ms | ... | ... |
| Conversion warm, ms | ... | ... |
| `pytest -q`, s | ... | ... |
| Unexplained vertical gaps | ... | ... |
| Wrong image placements | ... | ... |
| Connected letter pairs | ... | ... |
| Rejected unsafe joins | ... | ... |
| Connector collisions | ... | ... |
| Full-pipeline tests in default pytest | ... | 0 |
| Production modules | ... | ... |
| Test files | ... | ... |

---

# 61. Что НЕ делать

Не нужно:

- создавать новую ветку;
- переписывать проект с нуля;
- добавлять neural network;
- добавлять OCR;
- менять механику принтера;
- увеличивать draw speed;
- переписывать LaTeX renderer без измеримой причины;
- делать multiprocessing «на всякий случай»;
- удалять полезные unit tests;
- удалять safety validation;
- соединять 100% пар букв любой ценой.

---

# 62. Главные приоритеты

```text
1. Correct layout.
2. Correct geometry.
3. No false connector lines.
4. Fast conversion.
5. Fast developer test loop.
6. Clean code.
```

---

# 63. Желаемое конечное состояние

После UPD_Plotter_8 пользователь передаёт:

```text
PDF / DOCX
```

с:

```text
текстом
+
картинками
+
формулами
+
несколькими страницами
```

и получает:

```text
аккуратно свёрстанные страницы
+
картинки примерно на исходных местах
+
корректные формулы
+
естественный рукописный текст
+
без лишних соединительных диагоналей
+
быструю конвертацию
+
быстрый test suite
+
чистую кодовую базу
+
безопасный G-code
```

Это и является конечным результатом UPD_Plotter_8.
