# UPD_Plotter_10 — абзацное форматирование, постоянный кеш centerline-шрифта, улучшение таблиц и рисунков при смене формата страницы

## Назначение

Этот документ — подробный план работ для Codex по проекту:

`https://github.com/BMSTU-LYGO/plotter-proc`

Текущее состояние, от которого нужно продолжать работу:

`upd/plotter-7-layout-math-lines-tables`

Основная цель UPD_Plotter_10 — сделать так, чтобы плоттер сохранял не только сам текст и графику, но и **логическую рукописную структуру документа**:

- заголовок остаётся заголовком;
- центрированный текст остаётся центрированным;
- красная строка остаётся красной строкой;
- левые/правые отступы сохраняются;
- табуляция работает как табуляция, а не как случайное количество пробелов;
- таблицы сохраняют пропорции;
- рисунки и таблицы адекватно переносятся между A4 и A5;
- centerline-шрифт не пересчитывается заново при каждой очистке `build`.

Работу выполнять **по блокам**.

После завершения каждого блока Codex должен:

1. остановиться;
2. написать пользователю, что именно было сделано;
3. перечислить изменённые файлы;
4. показать тесты;
5. показать демонстрационный входной документ и preview результата;
6. показать известные ограничения;
7. дождаться команды пользователя перед переходом к следующему блоку.

Не объединять все три блока в один большой рефакторинг.

---

# 0. Сначала проверить фактическое состояние текущей ветки

Перед изменениями:

```bash
git status
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git pull
```

Проверить, что работа продолжается от:

```text
upd/plotter-7-layout-math-lines-tables
```

Если локально есть незакоммиченные пользовательские изменения — **не удалять и не откатывать их**.

---

# 1. Что уже есть в проекте и что важно учитывать

По текущему состоянию проекта уже существуют:

- `SourceParagraph`;
- `SourceTextRun`;
- `SourceTextStyle`;
- DOCX reader;
- PDF reader;
- `document_paginator.py`;
- `document_image_layout.py`;
- `table_layout.py`;
- режимы `reflow / hybrid / preserve / auto`;
- A4 и A5;
- центрирование LaTeX block formulas;
- многостраничность;
- semantic tables;
- centerline font cache;
- `compile-centerline-font`;
- `--centerline-cache`;
- `--force-centerline-rebuild`;
- Makefile с `run`, `test`, `lint`, `benchmark`, `smoke`, `clean`.

Также в текущем `SourceParagraph` уже есть поле:

```python
alignment: str | None
```

а DOCX reader уже умеет читать `w:jc`.

Однако этого недостаточно.

Сейчас в модели абзаца нет нормального представления:

```text
first line indent
left indent
right indent
hanging indent
space before
space after
line spacing
tab stops
style id/name
heading/title semantic role
```

Также в `layout.yaml` пока есть только:

```yaml
layout:
  tab_spaces: 4
```

То есть табуляция фактически сведена к условному числу пробелов, чего недостаточно для сохранения документа.

В таблицах уже сохраняются:

- количество строк/столбцов;
- merged cells;
- ширины колонок;
- repeat header rows.

Но текущий layout в основном масштабирует колонки под доступную ширину, а высота строк строится слишком упрощённо.

Для centerline cache уже существует направление на постоянный каталог `.plotter-cache/font-cache`, но UPD_Plotter_10 должен довести эту архитектуру до полностью однозначного состояния и добавить понятную Makefile-команду принудительной пересборки.

---

# 2. Общие правила архитектуры для UPD_Plotter_10

## 2.1. Не хранить document semantics внутри случайных пробелов

Нельзя представлять:

```text
красную строку
центрирование
левый отступ
табуляцию
```

путём добавления в текст строки пробелов.

Нужно хранить formatting отдельно в модели документа.

## 2.2. Не смешивать source format и target geometry

Входной документ может быть A4, а печать — A5.

Поэтому нужно разделить:

```text
source document geometry
target page geometry
flow layout
anchored object transform
```

## 2.3. Не масштабировать разные оси независимо

Для рисунков, векторной графики и таблиц нельзя делать:

```text
scale_x != scale_y
```

если это приводит к визуальному искажению.

Основной fit должен быть uniform:

```python
scale = min(target_width / source_width,
            target_height / source_height)
```

а затем объект размещается относительно target content box.

## 2.4. `build/` — только результаты job

`build` должен содержать:

```text
preview
paths.json
gcode
reports
debug artifacts
benchmark results
```

Он **не должен быть единственным хранилищем дорогого centerline cache**.

Команда:

```bash
make clean
```

не должна удалять рабочий кеш шрифта.

---

# БЛОК 1. Абзацное форматирование, табуляция, красная строка, заголовки и выравнивание

# 3. Цель блока 1

Сделать так, чтобы структура обычного документа сохранялась при конвертации.

Пример исходного документа:

```text
                 ЛАБОРАТОРНАЯ РАБОТА №1

    Цель работы: изучить работу механизма...

        Первый абзац начинается с красной строки и далее
    нормально переносится на следующую строку без повторения
    первой строки.

        Второй абзац также имеет красную строку.

Термин:         Значение
Скорость:       1000 мм/мин
```

На выходе должно остаться визуально то же:

- заголовок центрирован;
- у заголовка нет случайной красной строки;
- абзацы имеют first-line indent;
- последующие строки абзаца начинаются от обычного left edge;
- табы переходят к tab stop;
- правое/левое/center/justify alignment сохраняются;
- переносы строк не уничтожают форматирование.

---

# 4. Шаг 1.1. Расширить модель `SourceParagraph`

Расширить `SourceParagraph`.

Пример желаемой модели:

```python
@dataclass(frozen=True, slots=True)
class SourceParagraph:
    runs: tuple[SourceTextRun, ...]
    alignment: str | None = None

    first_line_indent_mm: float | None = None
    hanging_indent_mm: float | None = None

    left_indent_mm: float | None = None
    right_indent_mm: float | None = None

    space_before_mm: float | None = None
    space_after_mm: float | None = None
    line_spacing: float | None = None

    tab_stops_mm: tuple[float, ...] = ()

    style_id: str | None = None
    style_name: str | None = None
    semantic_role: str | None = None

    bbox: SourceBBox | None = None
```

Точное название полей можно изменить.

Главное — информация должна быть структурированной.

---

# 5. Шаг 1.2. Ввести нормализованный semantic role

Не привязывать downstream layout напрямую к Word style name.

Например Word может иметь:

```text
Title
Heading 1
Heading 2
Заголовок 1
CustomHeading
Normal
Body Text
```

Нужно преобразовывать source style в ограниченный внутренний набор:

```text
title
heading_1
heading_2
heading_3
body
quote
list
unknown
```

Для MVP достаточно:

```text
title
heading_1
heading_2
heading_3
body
```

Если style неизвестен — трактовать его как обычный body paragraph.

---

# 6. Шаг 1.3. DOCX: читать direct paragraph formatting

Из `w:pPr` нужно извлекать минимум.

## Alignment

```xml
<w:jc w:val="left"/>
<w:jc w:val="center"/>
<w:jc w:val="right"/>
<w:jc w:val="both"/>
```

Нормализовать:

```text
left
center
right
justify
```

Word aliases:

```text
start
end
both
distribute
```

Для MVP:

```text
both / distribute → justify
```

## Indentation

Из:

```xml
<w:ind
    w:left="..."
    w:right="..."
    w:firstLine="..."
    w:hanging="..."
/>
```

twips перевести в mm:

```python
mm = twips * 25.4 / 1440
```

Хранить отдельно:

```text
left_indent_mm
right_indent_mm
first_line_indent_mm
hanging_indent_mm
```

## Spacing

Из:

```xml
<w:spacing
    w:before="..."
    w:after="..."
    w:line="..."
    w:lineRule="..."
/>
```

Минимум поддержать:

```text
before
after
auto line spacing
```

## Tab stops

Из:

```xml
<w:tabs>
    <w:tab w:val="left" w:pos="..."/>
</w:tabs>
```

Поддержать минимум `left tab`.

`decimal`, `bar`, leader dots — warning + безопасный fallback.

---

# 7. Шаг 1.4. DOCX: учитывать style inheritance

Форматирование часто находится не непосредственно в paragraph XML, а в стиле.

Нужно получить effective paragraph formatting:

```text
document defaults
→ base style
→ inherited style
→ paragraph style
→ direct paragraph formatting
```

Direct formatting имеет высший приоритет.

Можно реализовать:

```python
resolve_paragraph_format(...)
```

который возвращает нормализованный объект.

---

# 8. Шаг 1.5. Не путать first-line indent и left indent

## Красная строка

```text
        первая строка текста...
вторая строка начинается отсюда...
третья строка начинается отсюда...
```

Это:

```text
first_line_indent_mm > 0
left_indent_mm = 0
```

## Отступ всего абзаца

```text
        первая строка
        вторая строка
        третья строка
```

Это:

```text
left_indent_mm > 0
```

## Hanging indent

```text
1.   Очень длинный пункт списка,
     который переносится сюда.
```

Это отдельная geometry, не first-line indent.

---

# 9. Шаг 1.6. Изменить paragraph line layout

Line layout должен получать:

```text
paragraph format
+
available content interval
```

Для первой строки:

```python
first_line_left = content_left + left_indent + first_line_indent
```

Для остальных:

```python
line_left = content_left + left_indent
```

Правая граница:

```python
line_right = content_right - right_indent
```

Hanging indent учитывать отдельно.

---

# 10. Шаг 1.7. Центрирование

При:

```text
alignment = center
```

центрировать line box относительно **доступной ширины абзаца**, а не физического листа.

То есть indents должны учитываться.

---

# 11. Шаг 1.8. Правое выравнивание

Для:

```text
alignment = right
```

последний glyph строки должен приходить примерно к:

```text
content_right - right_indent
```

Не делать это добавлением пробелов.

---

# 12. Шаг 1.9. Justify

Для непоследних строк:

```text
alignment = justify
```

увеличивать расстояние **между словами**, а не буквами.

Не justify:

- последнюю строку;
- строку из одного слова;
- заголовок;
- block formula.

Добавить clamp вроде:

```text
max_extra_space_per_word
```

---

# 13. Шаг 1.10. Настоящая табуляция

`tab_spaces: 4` оставить только как fallback для TXT.

Нужно реализовать tab stop logic.

Если текущая X:

```text
34 mm
```

tab stops:

```text
20, 40, 60, 80
```

то `\t`:

```text
34 → 40 mm
```

а не `+4 пробела`.

Добавить config:

```yaml
paragraphs:
  default_tab_interval_mm: 12.5
```

---

# 14. Шаг 1.11. Tab stops учитывать paragraph left edge

Если:

```text
paragraph left = 20 mm
interval = 12 mm
```

default stops:

```text
32
44
56
68
...
```

Custom DOCX stops имеют приоритет.

---

# 15. Шаг 1.12. Заголовки

Сохранять:

```text
semantic role
alignment
relative visual hierarchy
spacing before/after
```

Для `title/heading` нельзя автоматически добавлять красную строку.

Если source font size известен, использовать его как relative scale hint.

---

# 16. Шаг 1.13. Не использовать Word font как output font

Source может быть Times New Roman, а output — пользовательский рукописный TTF.

Переносить:

```text
размер/иерархию
alignment
indent
spacing
```

но glyph geometry брать из handwriting TTF.

---

# 17. Шаг 1.14. Relative font size policy

Ввести config примерно:

```yaml
paragraphs:
  preserve_relative_font_size: true
  min_font_scale: 0.80
  max_font_scale: 1.60

  semantic_scale:
    title: 1.35
    heading_1: 1.25
    heading_2: 1.15
    heading_3: 1.08
    body: 1.00
```

Source size использовать как hint, но clamp-ить.

---

# 18. Шаг 1.15. Paragraph spacing

Переносить:

```text
space_before
space_after
```

но с ограничениями, например:

```yaml
paragraphs:
  max_space_before_mm: 12
  max_space_after_mm: 12
```

---

# 19. Шаг 1.16. PDF formatting

PDF обычно не содержит настоящего paragraph style.

Поэтому:

```text
DOCX = semantic fidelity
PDF = conservative visual approximation
```

Для PDF можно сохранять alignment и консервативно определять first-line indent/heading по geometry, но не выдумывать semantics при низкой уверенности.

---

# 20. Шаг 1.17. TXT

TXT не содержит styles.

Поддержать:

- `\t` через default tab stops;
- пустые строки;
- существующий reflow.

Не превращать первую строку TXT автоматически в title.

---

# 21. Шаг 1.18. Paragraph debug

В `layout-debug` показать:

```text
content left
paragraph left
first-line left
paragraph right
baseline
alignment
tab stops
```

В JSON:

```json
{
  "paragraph_id": "page-001-text-003",
  "semantic_role": "body",
  "alignment": "justify",
  "left_indent_mm": 0,
  "right_indent_mm": 0,
  "first_line_indent_mm": 10,
  "tab_stops_mm": [25, 50, 75],
  "line_count": 4
}
```

---

# 22. Шаг 1.19. Демонстрационный DOCX

Создать:

```text
tests/fixtures/layout/paragraph_formatting_demo.docx
```

Содержимое:

1. `Title`, центрированный.
2. `Heading 1`, слева.
3. Paragraph с красной строкой.
4. Paragraph с left indent.
5. Paragraph с right indent.
6. Center paragraph.
7. Right paragraph.
8. Justified paragraph.
9. Paragraph с custom tab stops.
10. Несколько `\t`.
11. Block formula.
12. Картинка после текста.
13. Минимум две страницы.

---

# 23. Тесты блока 1

Добавить:

```text
test_docx_paragraph_formatting.py
test_paragraph_layout.py
test_tab_stops.py
test_paragraph_alignment.py
```

Обязательные сценарии:

1. `w:jc=center` → center.
2. `w:jc=right` → right.
3. `w:jc=both` → justify.
4. `firstLine` сохраняется.
5. `left` indent сохраняется.
6. `right` indent сохраняется.
7. `hanging` не превращается в first-line indent.
8. Style inheritance работает.
9. Direct formatting переопределяет style.
10. Title получает semantic role.
11. Heading 1 получает semantic role.
12. `\t` двигается к следующему tab stop.
13. Custom tab stop используется.
14. Default tab stop используется.
15. Center учитывает indents.
16. Right учитывает right indent.
17. Justify не растягивает последнюю строку.
18. Красная строка только у первой line box.
19. Page break не теряет paragraph format.
20. Форматирование внутри table cell не ломается.

---

# 24. Критерии приёмки блока 1

- заголовок остаётся визуально заголовком;
- центрирование сохраняется;
- right alignment сохраняется;
- justify выглядит адекватно;
- красная строка сохраняется;
- left/right indent сохраняются;
- tab работает как tab stop;
- перенос строк не ломает first-line indent;
- page break не теряет formatting;
- output font остаётся пользовательским handwriting TTF;
- preview и paths используют одну geometry.

---

# 25. Отчёт после блока 1

```markdown
## Блок 1 завершён — форматирование абзацев

### Что раньше терялось
### Что теперь хранится в SourceParagraph
### Как читаются DOCX styles
### Как работает красная строка
### Как работает табуляция
### Alignment: left / center / right / justify
### Заголовки
### Изменённые файлы
### Тесты
### Preview demo DOCX
### Ограничения
### Git SHA
```

После этого остановиться.


---

# БЛОК 2. Постоянный centerline font cache вне build + Makefile-команды управления кешем

# 26. Цель блока 2

Полная компиляция TTF в centerline дорогая.

Она не должна выполняться заново только потому, что:

```bash
make clean
```

удалил старые job artifacts.

Нужна архитектура:

```text
build/
    job artifacts only

.plotter-cache/
    reusable expensive caches
```

---

# 27. Важное замечание по текущему состоянию

В текущей ветке уже есть движение в правильную сторону:

```yaml
centerline:
  cache:
    enabled: true
    directory: .plotter-cache/font-cache
```

и README уже описывает `.plotter-cache/font-cache`.

Поэтому **не создавать второй параллельный cache-механизм**.

Задача блока 2:

1. проверить, что вся production-логика действительно использует этот путь;
2. убрать остаточные зависимости от `build/font-cache`;
3. сделать cache versioning однозначным;
4. добавить Makefile-команды;
5. сделать принудительную пересборку безопасной;
6. протестировать, что `make clean` кеш не трогает.

---

# 28. Шаг 2.1. Найти все cache paths

Выполнить:

```bash
rg "font-cache|plotter-cache|centerline-cache|cache.directory|cache_dir" .
```

Составить таблицу:

```text
файл
старое поведение
актуальное поведение
нужно менять?
```

После cleanup должен существовать один canonical default:

```text
.plotter-cache/font-cache
```

---

# 29. Шаг 2.2. Проверить `.gitignore`

Убедиться, что:

```text
.plotter-cache/
```

игнорируется Git.

Cache не должен попадать в repository.

---

# 30. Шаг 2.3. `make clean` не удаляет cache

Команда:

```bash
make clean
```

должна чистить:

```text
build/
```

но не:

```text
.plotter-cache/
```

Закрепить это тестом или Makefile smoke-check.

---

# 31. Шаг 2.4. Добавить отдельную команду очистки кеша

Добавить:

```bash
make cache-clean
```

Она удаляет:

```text
.plotter-cache/
```

и при необходимости создаёт пустой каталог заново.

Пользователь должен явно понимать, что следующий centerline run после этого будет cold.

---

# 32. Шаг 2.5. Добавить команду пересборки font cache

Основная команда:

```bash
make font-cache-rebuild FONT=assets/1.ttf
```

Допустим короткий alias:

```bash
make cache-rebuild FONT=assets/1.ttf
```

Но canonical target лучше назвать:

```text
font-cache-rebuild
```

Команда должна:

1. определить указанный TTF;
2. определить его cache namespace;
3. инвалидировать entries именно этого шрифта;
4. запустить centerline compilation с `--force`;
5. собрать заранее canonical glyph corpus;
6. сохранить результат в `.plotter-cache/font-cache`;
7. вывести понятный summary.

---

# 33. Шаг 2.6. Создать canonical corpus для rebuild

Нельзя перестраивать только символы из одного случайного demo-файла.

Создать:

```text
assets/font-cache-corpus.txt
```

Содержимое минимум:

```text
А-Я
а-я
Ёё
0-9
основная русская пунктуация
ASCII punctuation
математические ASCII symbols
```

При необходимости добавить:

```text
A-Z
a-z
```

если латиница используется в документах.

Не включать тысячи Unicode-глифов, которые пользовательский TTF всё равно не содержит.

---

# 34. Шаг 2.7. Makefile variables

Добавить:

```make
CACHE_DIR ?= .plotter-cache
FONT_CACHE_DIR ?= $(CACHE_DIR)/font-cache
FONT_CACHE_CORPUS ?= assets/font-cache-corpus.txt
```

Чтобы поддерживалось:

```bash
make font-cache-rebuild \
  FONT=assets/MyHand.ttf \
  FONT_CACHE_CORPUS=assets/custom-corpus.txt
```

---

# 35. Шаг 2.8. Cache identity зависит от содержимого font

Имя файла недостаточно.

`assets/1.ttf` может быть заменён другим TTF под тем же именем.

Cache key должен включать:

```text
font SHA256
```

---

# 36. Шаг 2.9. Cache identity зависит от algorithm version

В config уже есть:

```yaml
centerline:
  algorithm_version: 6
```

Использовать version как часть cache identity.

Пример:

```text
font_hash
+
algorithm_version
+
relevant_centerline_config_hash
+
glyph
```

---

# 37. Шаг 2.10. Сделать fingerprint только релевантной centerline-конфигурации

Не инвалидировать font cache из-за:

```text
A4/A5
page margins
G-code feedrate
images
tables
pagination
```

Но инвалидировать при изменении:

```text
render resolution
threshold
closing
skeleton candidate methods
spur pruning
routing
stroke smoothing
glyph overrides
font overrides
```

Создать детерминированный:

```python
centerline_config_fingerprint(...)
```

---

# 38. Шаг 2.11. Partial cache должен сохраниться

Если cache содержит:

```text
а б в г д
```

а новый документ требует:

```text
а б в г д е ё
```

ожидаемо:

```text
hits: а б в г д
misses: е ё
```

Пересобираются только misses.

Не пересобирать весь font corpus при каждом новом символе.

---

# 39. Шаг 2.12. Определить force semantics

## `--force-centerline-rebuild`

Для обычного `run`:

```text
игнорировать существующие entries только для required glyphs
и пересобрать required glyphs
```

## `compile-centerline-font --force`

Перестраивает указанный corpus.

## `make font-cache-rebuild`

Делает полный rebuild canonical corpus указанного font.

Это различие описать в README.

---

# 40. Шаг 2.13. Rebuild одного font не удаляет остальные

Если cache содержит:

```text
font A
font B
font C
```

команда:

```bash
make font-cache-rebuild FONT=fontA.ttf
```

не должна удалять cache B и C.

Если текущая структура этого не позволяет — переработать namespace.

Желательный вариант:

```text
.plotter-cache/font-cache/
    <font_sha256>/
        metadata.json
        glyphs/
```

или эквивалент.

---

# 41. Шаг 2.14. Atomic cache writes

Не писать cache напрямую в конечный файл, если процесс может оборваться.

Использовать:

```text
temporary path
→ write
→ close
→ atomic replace
```

При Ctrl+C не должен оставаться валидно названный, но битый cache entry.

---

# 42. Шаг 2.15. Cache metadata

Сохранить диагностическую metadata:

```json
{
  "font_sha256": "...",
  "font_path_hint": "assets/1.ttf",
  "algorithm_version": 6,
  "config_fingerprint": "...",
  "created_at": "...",
  "glyph_count": 123
}
```

`font_path_hint` — только информация, не identity.

---

# 43. Шаг 2.16. Желательно добавить cache status

Можно добавить:

```bash
make font-cache-status FONT=assets/1.ttf
```

или CLI:

```bash
python -m plotter_processor font-cache-info assets/1.ttf
```

Вывод:

```text
cache directory
font SHA
algorithm version
config fingerprint
cached glyph count
cache size
```

Это желательно, но не блокирует MVP.

---

# 44. Шаг 2.17. Codex workflow после этого блока

README должен чётко объяснять.

## Если менялся только layout

Например:

```text
paragraph alignment
tables
image placement
pagination
```

делать:

```bash
make test
```

и **не перестраивать centerline cache**.

## Если менялся centerline algorithm

Например:

```text
skeleton
routing
spur pruning
threshold
smoothing
cache schema
glyph override processing
```

Codex должен вызвать:

```bash
make font-cache-rebuild FONT=assets/1.ttf
```

---

# 45. Шаг 2.18. Автоматическая invalidation всё равно обязательна

Makefile-команда не должна быть единственной защитой.

Если:

```text
algorithm_version
или config fingerprint
```

не совпадают, runtime должен считать entry stale и пересобрать его.

Нельзя полагаться на память разработчика.

---

# 46. Шаг 2.19. Benchmark cache

На одном документе измерить:

```text
cold run
warm run
```

После warm run:

```bash
make clean
```

и запустить документ ещё раз.

Ожидаемо:

```text
warm before clean ≈ warm after clean
```

Потому что `.plotter-cache` не удалён.

---

# 47. Тесты блока 2

Добавить:

```text
test_centerline_cache_location.py
test_centerline_cache_versioning.py
test_centerline_cache_invalidation.py
```

Обязательные проверки:

1. Default cache вне `build`.
2. `build` не используется как implicit cache.
3. Font SHA входит в identity.
4. Algorithm version invalidates cache.
5. Relevant centerline config invalidates cache.
6. Page size не invalidates font cache.
7. Machine/G-code config не invalidates font cache.
8. Partial cache компилирует только misses.
9. Force rebuild реально перестраивает glyph.
10. Rebuild font A не удаляет font B.
11. Corrupted entry безопасно пересобирается.
12. Atomic write не оставляет partial target.
13. `make clean` не удаляет cache.
14. `make cache-clean` удаляет cache.
15. `make font-cache-rebuild` создаёт usable cache.

---

# 48. Критерии приёмки блока 2

- centerline cache физически находится вне `build`;
- cache ignored by Git;
- `make clean` cache не трогает;
- есть `make cache-clean`;
- есть `make font-cache-rebuild FONT=...`;
- algorithm changes инвалидируют stale cache;
- warm run не пересчитывает существующие glyphs;
- A4/A5 не создают дубли centerline cache;
- разные output directories используют один reusable cache;
- README содержит понятный workflow для Codex.

---

# 49. Отчёт после блока 2

```markdown
## Блок 2 завершён — постоянный font cache

### Где теперь хранится cache
### Как устроен cache key
### Что инвалидирует cache
### Новые Makefile-команды
### make clean
### make cache-clean
### make font-cache-rebuild
### Cold/warm benchmark
### Warm run после make clean
### Изменённые файлы
### Тесты
### Git SHA
```

После этого остановиться.


---

# БЛОК 3. Улучшить таблицы и рисунки + корректный перенос A4 → A5 и A5 → A4

# 50. Цель блока 3

Сделать единый понятный механизм адаптации source document к выбранному target page.

Ключевой сценарий:

```text
input DOCX/PDF:
    A4

output:
    A5
```

При этом:

- таблица не вылезает за лист;
- колонки сохраняют пропорции;
- текст в таблице переносится;
- строка таблицы увеличивается по высоте, если нужно;
- рисунок сохраняет aspect ratio;
- рисунок остаётся примерно в том же логическом месте;
- рисунок справа остаётся справа;
- рисунок по центру остаётся около центра;
- floating image не внезапно становится block image;
- source order сохраняется;
- многостраничность корректна.

---

# 51. Шаг 3.1. Ввести единый `PageTransform`

Не размазывать page scaling по разным модулям.

Создать один небольшой helper/model.

Пример:

```python
@dataclass(frozen=True, slots=True)
class PageTransform:
    source_page_width_mm: float
    source_page_height_mm: float

    source_content_rect: RectMM
    target_content_rect: RectMM

    scale: float
    offset_x_mm: float
    offset_y_mm: float
```

Методы:

```python
map_point()
map_rect()
scale_length()
map_relative_x()
map_relative_y()
```

Он должен использоваться для:

```text
images
PDF vectors
tables
anchored geometry
layout-debug
```

---

# 52. Шаг 3.2. Сопоставлять content box, а не только физический лист

При A4 → A5 важнее:

```text
source printable/content area
→ target printable/content area
```

чем:

```text
0..210 → 0..148
```

Если source margins известны — использовать их.

Если неизвестны — fallback на source page bounds.

---

# 53. Шаг 3.3. Uniform scale

Для preserve:

```python
scale = min(
    target_content_width / source_content_width,
    target_content_height / source_content_height,
)
```

Если config ограничивает upscale:

```python
scale = min(scale, max_upscale)
```

Не использовать независимый X/Y scale для image geometry.

---

# 54. Шаг 3.4. Hybrid mode: сохранять relative placement

В `hybrid` текст reflow-ится, поэтому абсолютный Y source page не всегда нужно копировать.

Для floating object хранить:

```text
left/right/center affinity
paragraph anchor
relative x position
local y offset
wrap mode
```

Пример:

```text
source image:
    справа
    около 75% content width

target:
    тоже справа
    примерно в той же логической зоне
```

---

# 55. Шаг 3.5. Image sizing policy

Для каждого image учитывать:

```text
source displayed size
source page size
target page size
available interval
```

При A4 → A5 preferred size:

```python
preferred_width = source_displayed_width * page_scale
preferred_height = source_displayed_height * page_scale
```

Затем clamp:

```text
available width
available height
max width/height ratios
```

Aspect ratio сохранять обязательно.

---

# 56. Шаг 3.6. Не растягивать маленькие картинки без причины

Если source displayed width известен, он имеет приоритет.

Не делать автоматически:

```text
image width = 75% page
```

если source image была маленькой.

`default_width_ratio` использовать только как fallback при отсутствии source dimensions.

---

# 57. Шаг 3.7. Raster и vector должны использовать общую placement policy

Raster и vector могут по-разному получать local strokes.

Но page placement должен быть общий:

```text
local geometry
→ PageTransform / anchored placement
→ target geometry
```

PDF vector diagram и PNG image не должны иметь две несовместимые системы масштабирования.

---

# 58. Шаг 3.8. Rotation

Если source image содержит:

```text
rotation_deg
```

rotation сохранять.

Для wrapping/collision достаточно вычислять axis-aligned bbox уже после rotation.

Сложный polygon text-wrap в этом обновлении не нужен.

---

# 59. Шаг 3.9. Масштабировать image padding

Source:

```text
distance_left
distance_right
distance_top
distance_bottom
```

масштабировать вместе со страницей.

Добавить clamp:

```text
minimum readable padding
maximum reasonable padding
```

чтобы padding на A5 не стал нелепым.

---

# 60. Шаг 3.10. Таблица не должна всегда занимать всю available width

Текущий подход вида:

```python
scale = available_width / sum(source_widths)
```

может растягивать небольшую source table на всю страницу.

Новая policy:

```python
preferred_width = source_table_width * page_scale
target_width = min(preferred_width, available_width)
```

Если source width неизвестна — fallback к старой flow policy.

---

# 61. Шаг 3.11. Сохранять пропорции колонок

Если source:

```text
30 / 60 / 30 mm
```

то target должен сохранять:

```text
1 : 2 : 1
```

Если source widths отсутствуют или невалидны:

```text
equal columns
```

и warning/debug note.

---

# 62. Шаг 3.12. Минимальная ширина колонки

Добавить config:

```yaml
tables:
  min_column_width_mm: ...
```

Но если сумма minimum widths не помещается на A5, не делать overflow молча.

Fallback:

```text
uniform controlled shrink
+
warning
```

---

# 63. Шаг 3.13. Auto row height

Фиксированная row height недостаточна.

Алгоритм:

1. определить target column widths;
2. определить content width каждой cell;
3. layout текста внутри cell;
4. получить число line boxes;
5. вычислить required text height;
6. добавить top/bottom padding;
7. для row взять maximum required height.

То есть:

```python
row_height = max(
    cell_required_height
    for each relevant cell
)
```

---

# 64. Шаг 3.14. Учитывать source row height

Если DOCX задаёт явную высоту:

- использовать как preferred/min height;
- масштабировать через page scale;
- если reflow text требует больше — увеличивать.

Не обрезать текст ради source height.

---

# 65. Шаг 3.15. Cell padding

Расширить config:

```yaml
tables:
  cell_padding_mm: 1.2
  min_cell_padding_mm: 0.7
  max_cell_padding_mm: 2.0
  scale_padding_with_page: true
```

A4 → A5 может немного уменьшать padding, но не до нуля.

---

# 66. Шаг 3.16. Paragraph formatting внутри cell

Результат блока 1 должен работать внутри cell.

Поддерживать:

```text
left
center
right
first line indent
tabs
```

Если indent слишком велик для узкой cell — clamp с warning/debug note.

---

# 67. Шаг 3.17. Vertical alignment cell

В `SourceTableCell` уже есть:

```python
vertical_alignment
```

Проверить, что DOCX reader реально читает:

```text
top
center
bottom
```

После auto row height смещать cell text по vertical alignment.

---

# 68. Шаг 3.18. Merged cells

Сохранить:

```text
row_span
column_span
```

При auto row height учитывать merged cells.

Не рисовать внутреннюю границу через merged cell.

Shared border рисовать один раз.

---

# 69. Шаг 3.19. Borders

Улучшить:

- outer border;
- shared border deduplication;
- merged geometry;
- безопасное масштабирование line width;
- single-line fallback для неизвестного border style.

Таблицу не растеризовать.

---

# 70. Шаг 3.20. Pagination таблиц

Если table не помещается:

```text
разрывать между rows
```

а не посередине произвольной geometry.

Если:

```text
repeat_header_rows > 0
```

повторять header на новой странице.

---

# 71. Шаг 3.21. Не ломать row-span при page break

Если page break попадает внутрь row-span group:

- попытаться перенести весь связанный row group;
- если group выше целой страницы — использовать fallback и warning.

Не оставлять half-merged cell без корректной border geometry.

---

# 72. Шаг 3.22. Table text scaling

При A4 → A5 порядок действий:

1. page-scale table;
2. reflow cell text;
3. увеличить row height;
4. только затем при необходимости немного уменьшить cell text.

Добавить:

```yaml
tables:
  min_text_scale: 0.75
```

Не делать текст нечитаемым ради того, чтобы таблица любой ценой осталась на одной странице.

---

# 73. Шаг 3.23. Table placement

Для разных layout modes:

## Preserve

```text
map source table bbox → target bbox
```

## Hybrid

```text
сохранить source width примерно
сохранить left/center/right affinity
оставить source order
размещать как block в flow
```

## Reflow

```text
обычный block element
fit inside content width
```

---

# 74. Шаг 3.24. Получать source table geometry из DOCX

Если у DOCX table нет полноценного bbox, вычислять approximation.

Использовать:

```text
grid column widths
table preferred width
table alignment
table indent
```

При необходимости расширить `SourceTableElement`:

```python
alignment: str | None
left_indent_mm: float | None
preferred_width_mm: float | None
```

---

# 75. Шаг 3.25. Читать DOCX `tblPr`

Из `tblPr` читать минимум:

```text
tblW
jc
tblInd
```

То есть:

```text
preferred width
alignment
table indent
```

Этого достаточно для заметно более правильного A4 → A5 placement.

---

# 76. Шаг 3.26. PDF tables

Для detected PDF table использовать source bbox.

При A4 → A5:

```text
bbox → PageTransform → target bbox
```

Row/column proportions сохранять.

DOCX-specific properties для PDF не выдумывать.

---

# 77. Шаг 3.27. Общий placement report

В `report.json` добавить source→target diagnostics.

Пример:

```json
{
  "source_page": "A4",
  "target_page": "A5",
  "page_scale": 0.68,
  "objects": [
    {
      "id": "image-1",
      "type": "image",
      "source_bbox": {},
      "target_bbox": {},
      "scale": 0.68,
      "placement_mode": "paragraph_anchor"
    },
    {
      "id": "table-1",
      "type": "table",
      "source_width_mm": 160,
      "target_width_mm": 108,
      "scale": 0.675
    }
  ]
}
```

---

# 78. Шаг 3.28. Debug overlay A4 → A5

`layout-debug` должен показывать:

```text
source page outline
source content rect
source object bbox
target page outline
target content rect
target bbox
```

Подписывать:

```text
scale
anchor
placement mode
```

---

# 79. Шаг 3.29. Fixture A4 → A5

Создать:

```text
tests/fixtures/layout/a4_to_a5_layout_demo.docx
```

Содержание:

1. A4 source page.
2. Centered title.
3. Text с first-line indent.
4. Маленькая image справа сверху.
5. Большая image по центру.
6. Table 3×5.
7. Неравные column widths.
8. Horizontal merged cell.
9. Vertical merged cell.
10. Header row.
11. Длинный text в одной cell.
12. Table около низа страницы.
13. Достаточно контента для второй страницы.

---

# 80. Шаг 3.30. Протестировать четыре комбинации

Минимум:

```text
A4 source → A4 target
A4 source → A5 target
A5 source → A5 target
A5 source → A4 target
```

Основной acceptance case:

```text
A4 → A5
```

---

# 81. Шаг 3.31. Что считается корректным A4 → A5

Не нужен pixel-perfect Word renderer.

Нужно сохранить:

```text
relative hierarchy
approximate placement
aspect ratio
table proportions
source order
alignment
```

Допустимо:

- больше line wraps;
- увеличенная row height;
- перенос table на следующую страницу;
- небольшое смещение floating image ради collision avoidance.

Недопустимо:

- distorted image;
- table за page bounds;
- перепутанные columns;
- text поверх border;
- right image стала left image;
- header потерян;
- merged cells сломались.

---

# 82. Тесты блока 3

Добавить:

```text
test_page_transform.py
test_image_page_scaling.py
test_table_scaling.py
test_table_auto_row_height.py
test_table_pagination.py
test_docx_table_properties.py
```

## Page transform

1. A4 → A5 uniform scale.
2. A5 → A4 сохраняет aspect.
3. Source center maps near target center.
4. Right-affine object остаётся справа.
5. Margins учитываются.

## Images

6. Raster aspect ratio сохраняется.
7. Vector aspect ratio сохраняется.
8. Small image не растягивается.
9. Oversized image уменьшается.
10. Wrap padding масштабируется.
11. Paragraph-anchored image остаётся около anchor.
12. Page-anchored image сохраняет relative position.

## Tables

13. Column ratios сохраняются.
14. Small table не растягивается на 100% без причины.
15. Wide table уменьшается.
16. Text wrapping увеличивает row height.
17. Cell padding сохраняется.
18. Vertical alignment работает.
19. Horizontal merge не имеет внутренней border.
20. Vertical merge работает.
21. Header повторяется после page break.
22. Table не разрывается внутри обычной row.
23. Row-span page break защищён.
24. Long cell content не выходит за border.
25. A4 table помещается на A5 или корректно разбивается.

---

# 83. Критерии приёмки блока 3

- A4 → A5 работает на demo;
- images сохраняют aspect ratio;
- images остаются примерно в source position;
- right/left/center affinity сохраняется;
- tables сохраняют column ratios;
- rows имеют auto height;
- text не выходит за cell;
- merged cells корректны;
- header rows повторяются;
- table безопасно пагинируется;
- object overflow либо отсутствует, либо явно reported;
- layout-debug показывает source→target transform.

---

# 84. Отчёт после блока 3

```markdown
## Блок 3 завершён — таблицы, рисунки и A4/A5 scaling

### Общий PageTransform
### A4 → A5
### Как масштабируются изображения
### Как сохраняется положение изображений
### Как масштабируются таблицы
### Auto row height
### Merged cells
### Pagination таблиц
### Изменённые файлы
### Тесты
### Demo preview A4 → A5
### Ограничения
### Git SHA
```

После этого остановиться.

---

# 85. Финальный regression fixture UPD_Plotter_10

После трёх блоков сделать:

```text
tests/fixtures/layout/upd10_full_demo.docx
```

Source format:

```text
A4
```

Внутри:

```text
centered Title
Heading 1
красная строка
justify paragraph
right-aligned line
tab-separated values
inline LaTeX
block LaTeX
image справа
image по центру
table с разными колонками
merged cells
header row
несколько страниц
```

Запустить на A4:

```bash
python -m plotter_processor run \
  tests/fixtures/layout/upd10_full_demo.docx \
  --font assets/1.ttf \
  --font-mode centerline \
  --page A4 \
  --document-layout auto \
  --layout-debug \
  --output-dir build/upd10-a4
```

Потом тот же input на A5:

```bash
python -m plotter_processor run \
  tests/fixtures/layout/upd10_full_demo.docx \
  --font assets/1.ttf \
  --font-mode centerline \
  --page A5 \
  --document-layout auto \
  --layout-debug \
  --output-dir build/upd10-a5
```

---

# 86. Проверка cache в финальном regression

Перед regression:

```bash
make font-cache-rebuild FONT=assets/1.ttf
```

Запустить job.

После этого:

```bash
make clean
```

и снова запустить centerline A5 job.

Ожидаемо:

```text
font cache hits сохраняются
полная centerline compilation не запускается заново
```

---

# 87. Финальная проверка Makefile

После UPD_Plotter_10 Makefile должен содержать минимум:

```text
install
test
lint
run
demo
extract
calibrate
benchmark
smoke
clean

cache-clean
font-cache-rebuild
```

Желательно:

```text
font-cache-status
```

Не забыть обновить `.PHONY`.

---

# 88. README

Добавить раздел:

## Абзацное форматирование

Описать:

```text
center
right
justify
first-line indent
left/right indent
tab stops
title/headings
```

Добавить:

## Centerline cache

Команды:

```bash
make font-cache-rebuild FONT=assets/1.ttf
make cache-clean
```

Отдельно написать:

```text
make clean не удаляет .plotter-cache
```

Добавить:

## A4/A5 document scaling

Объяснить:

```text
reflow
hybrid
preserve
auto
```

и поведение image/table при target page другого размера.

---

# 89. Метрики в `report.json`

## Paragraph formatting

```json
{
  "paragraph_formatting": {
    "paragraphs_total": 0,
    "titles": 0,
    "headings": 0,
    "first_line_indents": 0,
    "centered": 0,
    "right_aligned": 0,
    "justified": 0,
    "custom_tab_stops": 0
  }
}
```

## Font cache

```json
{
  "cache": {
    "font": {
      "directory": ".plotter-cache/font-cache",
      "hits": 0,
      "misses": 0,
      "rebuilt": 0,
      "algorithm_version": 6
    }
  }
}
```

## Page transform

```json
{
  "page_transform": {
    "source_width_mm": 210,
    "source_height_mm": 297,
    "target_width_mm": 148,
    "target_height_mm": 210,
    "scale": 0.0
  }
}
```

## Tables/images

```json
{
  "layout_objects": {
    "images_scaled": 0,
    "tables_scaled": 0,
    "tables_paginated": 0,
    "table_rows_auto_height": 0,
    "object_overflow_count": 0
  }
}
```

---

# 90. Финальные команды проверки

Выполнить:

```bash
make lint
make test
```

Затем:

```bash
make font-cache-rebuild FONT=assets/1.ttf
```

Затем:

```bash
make smoke
```

После smoke:

```bash
make clean
```

и повторить один centerline demo, чтобы убедиться, что cache не исчез.

---

# 91. Что НЕ делать в UPD_Plotter_10

Не нужно:

- переписывать centerline algorithm без причины;
- добавлять neural network;
- добавлять OCR;
- заменять DOCX parser целиком;
- удалять `reflow/hybrid/preserve`;
- превращать tables в raster;
- превращать весь document в screenshot;
- хранить first-line indent через spaces;
- хранить font cache внутри job directory;
- инвалидировать font cache из-за A4/A5;
- искажать image aspect ratio;
- насильно растягивать каждую table на всю width;
- делать pixel-perfect Word renderer.

---

# 92. Приоритеты реализации

```text
1. Сохранить paragraph semantics.
2. Красная строка и alignment.
3. Настоящие tab stops.
4. Надёжный reusable font cache.
5. Однозначная Makefile-команда rebuild.
6. Единый A4/A5 transform.
7. Корректные images.
8. Корректные tables.
9. Debug и метрики.
10. Cleanup только затронутого кода.
```

---

# 93. Ожидаемое конечное состояние

После UPD_Plotter_10 пользователь берёт обычный A4 DOCX:

```text
                 Заголовок

        Первый абзац с красной строки и нормальным
текстом, который сохраняет структуру исходного документа.

        Второй абзац.

Параметр:       Значение
Скорость:       1000

           [рисунок справа]

+----------+-------------------+
| №        | Результат         |
+----------+-------------------+
| 1        | длинный текст...  |
+----------+-------------------+
```

выбирает:

```text
--page A5
```

и получает рукописный документ, где:

- заголовок остаётся заголовком;
- красные строки сохраняются;
- alignment сохраняется;
- tabs сохраняют колоночную структуру;
- рисунки уменьшаются пропорционально и остаются примерно на исходной стороне/позиции;
- таблицы сохраняют пропорции;
- строки таблиц увеличиваются из-за переноса текста при необходимости;
- многостраничность работает;
- centerline font берётся из постоянного cache;
- `make clean` не заставляет пересчитывать весь TTF;
- после изменения centerline algorithm Codex может выполнить одну команду:

```bash
make font-cache-rebuild FONT=assets/1.ttf
```

Именно это является конечным результатом UPD_Plotter_10.
