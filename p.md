# FAST_PIPELINE_REFACTOR — упрощение и максимальное ускорение plotter-proc

Репозиторий: `https://github.com/BMSTU-LYGO/plotter-proc`

## Цель

Максимально упростить и ускорить основной pipeline обработки текста.

Новая схема:

```text
INPUT
  ↓
извлечение текста
  ↓
tokenization
  ↓
готовый font cache
  ↓
сборка букв в слова
  ↓
1–2 непрерывных stroke на слово
  ↓
раскладка words → lines → pages
  ↓
G-code
```

Главный принцип:

> Runtime не должен строить шрифт, выполнять TTF→centerline, skeletonization или другую тяжёлую обработку glyph. Runtime должен брать готовую геометрию букв из cache, трансформировать координаты, соединять буквы в слова и раскладывать слова по страницам.

Сначала изучи текущую реализацию и переиспользуй существующий код там, где это возможно. Не делай полный rewrite проекта.

---

# 1. Замерить текущий pipeline

Перед изменениями:

1. Найти текущие этапы:
   - загрузка/компиляция шрифта;
   - glyph generation;
   - connections;
   - layout;
   - pagination;
   - optimization;
   - G-code generation.
2. Определить, какие операции выполняются повторно для одинаковых glyph.
3. Найти наиболее дорогие этапы.
4. Добавить/использовать минимальные timing-метрики для сравнения старого и нового pipeline.

Зафиксировать baseline на одном небольшом и одном многостраничном русском документе.

Не заниматься unrelated refactoring.

---

# 2. Готовый Font Cache

Убрать тяжёлую обработку шрифта из runtime.

Создать/адаптировать предварительно скомпилированный формат font cache.

Минимальная структура glyph:

```text
Glyph
- char / glyph_id
- advance
- width
- baseline
- entry_point
- exit_point
- strokes[]
```

`strokes` содержит готовые координаты траекторий.

Например:

```text
"а" → Glyph(...)
"б" → Glyph(...)
"в" → Glyph(...)
```

Runtime:

```text
char
 ↓
O(1) lookup
 ↓
готовые strokes
```

Если в проекте уже существует подходящий centerline/font cache — НЕ создавать второй параллельный формат. Упростить существующий и использовать его.

Добавить отдельную offline-компиляцию шрифта, если её ещё нет:

```bash
plotter-font-compile <font> -o <cache>
```

Все дорогие операции допустимы здесь:

```text
TTF
→ outline
→ centerline/skeleton
→ cleanup
→ entry/exit calculation
→ serialization
```

Но они не должны выполняться при обычной конвертации документа.

### Commit

После выполнения:

```text
FAST-1 font cache moved out of runtime
```

---

# 3. Fast Glyph Loader

Реализовать максимально дешёвое получение glyph.

Font cache загружается один раз на job/process.

Не читать cache с диска отдельно для каждой буквы.

Нужен интерфейс уровня:

```python
glyph = font.get(char)
```

После загрузки font cache получение glyph должно быть обычным lookup без повторного:

- parsing;
- skeletonization;
- graph building;
- centerline generation;
- SVG conversion.

Предусмотреть fallback для отсутствующего символа, но fallback не должен незаметно запускать тяжёлую компиляцию всего шрифта.

---

# 4. WordBuilder

Добавить отдельный простой компонент:

```text
WordBuilder
```

Вход:

```text
"привет"
```

Процесс:

```text
п → cache
р → cache
и → cache
в → cache
е → cache
т → cache
```

Разместить glyph последовательно с учётом `advance`.

Соединять:

```text
exit(previous) → entry(next)
```

не отдельным глобальным optimizer после построения документа, а непосредственно при сборке слова.

Цель:

```text
word → 1 primary stroke
```

или, когда это геометрически невозможно:

```text
word → primary stroke + secondary stroke
```

То есть обычное слово должно требовать примерно 1–2 циклов:

```text
PEN_DOWN
...
PEN_UP
```

Не делать дорогую глобальную graph optimization ради соединения букв.

---

# 5. Безопасные соединения букв

Соединение должно выглядеть как естественный рукописный переход.

Использовать простой дешёвый connector:

```text
previous.exit
      ↓
короткая smooth curve
      ↓
next.entry
```

Допустимы quadratic/cubic Bézier или существующий дешёвый алгоритм проекта.

Не соединять буквы прямой линией через всю букву, если entry/exit находятся в неудобных местах.

Сохранить существующие хорошие правила соединений, если они уже реализованы.

Не делать тяжёлый поиск оптимального маршрута.

---

# 6. Secondary strokes

Отдельные элементы букв не должны ломать primary stroke.

Например:

- точки;
- кратка `й`;
- отдельные элементы glyph;
- другие disconnected components.

Сначала строить основную траекторию слова:

```text
primary
```

После неё объединять доступные вторичные элементы:

```text
secondary
```

Цель — минимизировать число поднятий пера, но не ценой неправильной геометрии.

Структура результата:

```text
WordGeometry
- width
- primary_stroke
- secondary_strokes
- bbox
```

Предпочтительно:

```text
1 primary + 0/1 secondary route
```

Если конкретный glyph объективно требует большего количества disconnected strokes, не портить букву искусственным соединением.

### Commit

После блоков 3–6:

```text
FAST-2 build connected words directly from cached glyphs
```

---

# 7. Word Cache

Добавить лёгкий in-memory cache уже собранных слов.

Ключ должен учитывать параметры, реально влияющие на геометрию, например:

```text
(font_id, size, word)
```

и другие параметры только если они действительно изменяют strokes.

Пример:

```text
("handwriting", 12, "система")
        ↓
WordGeometry
```

При повторном появлении слова не выполнять повторно:

```text
glyph lookup
→ positioning
→ connection building
```

Не создавать сложную cache infrastructure. Достаточно bounded in-memory LRU, если этого хватает.

---

# 8. Fast Layout

Для быстрого режима реализовать простой layout:

```text
words → lines → pages
```

Иметь:

```text
page_width
page_height

margin_left
margin_right
margin_top
margin_bottom

line_height
word_spacing
```

Алгоритм:

```text
если word помещается в текущую строку:
    добавить

иначе:
    перейти на новую строку

если новая строка не помещается:
    создать новую страницу
```

Сложность должна быть O(number_of_words).

Не использовать тяжёлый document-layout engine в fast text mode.

Обязательно сохранить:

- `\n`;
- пустые строки;
- абзацы;
- перенос страницы, если он присутствует во входном представлении и его можно дешёво определить.

---

# 9. Page representation

После layout получить простую структуру:

```text
Document
 ├── Page
 │    ├── WordGeometry
 │    ├── WordGeometry
 │    └── ...
 ├── Page
 └── ...
```

Каждый `WordGeometry` уже содержит окончательные strokes и position/transform.

Не выполнять после этого повторную обработку отдельных glyph.

### Commit

После блоков 7–9:

```text
FAST-3 add word cache and linear page layout
```

---

# 10. Упростить hot path

Проанализировать основной runtime pipeline.

В FAST text pipeline не должны выполняться без необходимости:

- TTF → centerline;
- skeletonization;
- outline extraction;
- повторная обработка glyph;
- повторный SVG parsing;
- глобальная оптимизация соединений букв;
- дорогая handwriting post-processing;
- сложный hybrid layout;
- глобальный route optimizer для каждой буквы.

Не удалять существующие возможности проекта, если они нужны другим режимам.

Сделать fast pipeline основным/явным путём для обычной печати текста, а сложные возможности оставить отдельными optional paths.

---

# 11. G-code

Передавать в G-code generator уже готовые page strokes.

Последовательность:

```text
Page
 ↓
WordGeometry
 ↓
primary stroke
 ↓
secondary strokes
 ↓
next word
```

Не выполнять повторную геометрическую реконструкцию.

Сохранить существующие:

- machine bounds;
- safety checks;
- feedrate;
- pen up/down commands;
- preview;
- validation.

Не ломать существующие профили плоттера.

---

# 12. Минимизировать PEN_UP/PEN_DOWN

Добавить метрики:

```text
words_total
pen_down_count
pen_up_count
avg_pen_down_per_word
```

Целевой показатель для обычного русского текста:

```text
avg_pen_down_per_word ≈ 1–2
```

Не считать пробел отдельным stroke.

Между словами разрешён `PEN_UP`.

Не соединять разные слова искусственной линией.

---

# 13. Performance

После реализации прогнать те же документы, что использовались для baseline.

Вывести:

```text
OLD:
font preparation:
glyph generation:
connections:
layout:
optimization:
gcode:
total:

NEW:
font cache load:
word building:
layout:
gcode:
total:
```

Также:

```text
speedup = old_total / new_total
```

Отдельно проверить cold и warm run.

Цель — убрать CPU-heavy font processing из обычного runtime и получить максимально близкий к линейному pipeline.

---

# 14. Проверки

Обязательно проверить:

1. русский текст;
2. прописные/строчные;
3. цифры;
4. базовую пунктуацию;
5. несколько абзацев;
6. несколько страниц;
7. длинные слова;
8. повторяющиеся слова;
9. буквы с disconnected components;
10. отсутствие glyph в cache;
11. корректные границы страницы;
12. отсутствие выхода G-code за machine bounds;
13. отсутствие запрещённых heating/extrusion commands.

Добавить unit tests минимум для:

```text
font cache lookup
word construction
glyph connection
word cache
line wrapping
pagination
pen-down counting
```

---

# 15. Совместимость

Не ломать существующие сложные режимы ради fast path.

Архитектурно желательно:

```text
                 input
                   ↓
              text extraction
                   ↓
             ┌─────┴─────┐
             ↓           ↓
         FAST TEXT    ADVANCED
             ↓           ↓
       cached font    existing pipeline
             ↓
       WordBuilder
             ↓
       FastLayout
             ↓
             └─────┬─────┘
                   ↓
                 G-code
```

Но не создавать лишнюю абстракцию, если текущую архитектуру можно упростить меньшим изменением.

---

# 16. Критерий готовности

Работа считается выполненной, когда обычный русский текст проходит путь:

```text
text
→ tokenize
→ cached glyph lookup
→ connected WordGeometry
→ lines
→ pages
→ G-code
```

без runtime font compilation.

Основной runtime должен быть близок к:

```text
O(chars + generated_points)
```

Повторяющиеся слова должны переиспользовать `WordGeometry`.

Большинство слов должно строиться с 1–2 опусканиями пера.

Результат должен автоматически разбиваться на страницы.

---

# Правила работы

1. Сначала изучи текущий код и используй существующие реализации, где они уже решают задачу.
2. Не переписывай проект с нуля.
3. Не добавляй dependency без реальной необходимости.
4. Не делай unrelated refactoring.
5. Не ухудшай качество существующего рукописного шрифта.
6. Не удаляй advanced functionality — выведи её из fast hot path.
7. После каждого указанного блока сделай commit с указанным названием.
8. После каждого commit запускай релевантные tests.
9. Если тест упал — исправь до следующего commit.
10. Не останавливайся для подтверждения между блоками, если нет блокирующей неоднозначности.
11. В чат пиши минимально: выполненные блоки, commit, tests, benchmark.
12. В конце дай короткий отчёт:

```text
Commits:
Tests:
Old runtime:
New runtime:
Speedup:
Avg pen-down/word:
Changed architecture:
Remaining bottlenecks:
```

Главный приоритет в спорных решениях:

```text
1. Runtime speed
2. Минимум PEN_UP/PEN_DOWN
3. Корректная геометрия букв
4. Простота реализации
5. Обратная совместимость advanced modes
```