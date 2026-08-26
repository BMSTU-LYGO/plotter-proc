Да. Я бы `UPD_Plotter_18` сделал **в первую очередь математическим обновлением**, а уже последнюю треть посвятил SVG, сложному DOCX/PDF и рисункам.

Сейчас у проекта уже есть хороший MVP: inline/block LaTeX, MathText → raster → centerline, базовый OMML и visual reconstruction формул из PDF. Но README прямо фиксирует, что это пока подмножество TeX/OMML, а PDF-математика восстанавливается визуально. ([GitHub][1]) Поэтому здесь есть куда очень сильно углубляться. Плюс у Matplotlib есть возможность получать MathText как vector paths, а не обязательно сначала рендерить всю формулу в растр — это стоит использовать как основу для более качественного math pipeline. ([Matplotlib][2])

# UPD_Plotter_18 — Math/LaTeX 2.0, сложные документы, SVG и графика

## Общие правила для Codex

Работай **строго в той ветке, в которой задача была запущена**.

Не создавать новую ветку и не переключаться на другую.

Главная цель `UPD_Plotter_18`:

> **сделать математические формулы полноценной частью plotter pipeline, а не отдельной растровой вставкой, значительно расширить поддержку LaTeX/OMML/PDF math и после этого улучшить сложную векторную графику документов.**

Приоритеты внутри обновления:

```text
1. LaTeX / Math
2. Word OMML
3. PDF Math
4. SVG
5. DOCX/PDF diagrams
6. Raster images
```

То есть если приходится выбирать между новой графической фичей и качеством формул — **выбирать формулы**.

---

# Экономия токенов Codex

Работать максимально точечно.

Перед текущими двумя пунктами использовать:

```text
rg
git status
git diff
существующие math/latex tests
существующие OMML tests
существующие PDF math tests
```

Не читать весь репозиторий.

Не перечитывать целиком большие pipeline/layout файлы, если достаточно найти конкретные функции.

Не создавать длинные `.md`-отчёты.

Не писать подробный reasoning в чат.

После каждого пункта писать **ровно одно короткое предложение**:

```text
18-X: сделано <что изменено>, проверено <чем>.
```

Например:

```text
18-4: добавлен кеш centerline математических glyph, проверено LaTeX corpus и determinism tests.
```

---

# Правила коммитов

Выполнять **строго по 2 пункта за один коммит**.

После `1-2`:

```bash
git add -A
git commit -m "18-2"
```

После `3-4`:

```bash
git add -A
git commit -m "18-4"
```

И так далее.

Название:

```text
18-X
```

где `X` — номер последнего полностью закрытого пункта.

Если один пункт не закончен корректно — **коммит не делать**.

---

# Обязательные остановки

После каждых:

```text
3 коммита
=
6 пунктов
```

обязательно остановиться.

Точки остановки:

```text
18-6
18-12
18-18
```

После `18-6` написать только:

```text
Остановился после 18-6. Готов продолжить с 18-7.
```

После `18-12`:

```text
Остановился после 18-12. Готов продолжить с 18-13.
```

Без команды пользователя следующий блок не начинать.

---

# Блок 1 — новое ядро LaTeX / Math

## Пункт 1 — ввести единый Math Expression Model

Создать или привести к единому виду внутреннее представление математического выражения, чтобы TXT LaTeX, DOCX OMML и обнаруженная PDF-математика после соответствующего parsing могли использовать общий math pipeline.

Минимально модель должна различать:

```text
symbols
operators
functions
fractions
roots
subscripts
superscripts
delimiters
n-ary operators
text inside math
groups
rows / sequences
```

При этом **не нужно писать собственный полный TeX parser с нуля** — модель должна служить нормализованным промежуточным представлением там, где это практично.

Архитектура:

```text
LaTeX ─────┐
           │
OMML ──────┼──→ Math Expression
           │
PDF math ──┘
                 ↓
             Math layout
                 ↓
             Plot geometry
```

**Готово, если:** downstream math renderer не требует знать, пришла формула из TXT, DOCX или другого поддерживаемого структурированного источника там, где семантика известна.

---

## Пункт 2 — нормализация и validation LaTeX до rendering

Добавить отдельный этап разбора/нормализации LaTeX expression до geometry, который корректно определяет поддерживаемые конструкции, синтаксические ошибки и unsupported commands.

Нужно отличать:

```text
валидная поддерживаемая формула
валидная, но частично неподдерживаемая
синтаксически неправильная
опасная / запрещённая конструкция
```

Ошибки должны выглядеть примерно:

```text
Unsupported LaTeX command: \foo
Formula 3, page 2
```

а не как traceback Matplotlib.

Сохранить текущую безопасность:

* не запускать shell;
* не выполнять `\input`;
* не выполнять `\include`;
* не выполнять пользовательские команды;
* не выполнять произвольные packages.

**Готово, если:** bad/unsupported expressions диагностируются до G-code и имеют понятные warnings/errors.

### После 1–2

Запустить:

* existing LaTeX tests;
* parser tests;
* strict-quality tests;
* determinism.

```bash
git add -A
git commit -m "18-2"
```

---

# Пункт 3 — vector-first MathText rendering

Переделать основной путь формул так, чтобы для поддерживаемого MathText сначала пытаться получать **векторную геометрию символов и их реальное расположение**, а не обязательно рендерить целую формулу в high-resolution bitmap.

Использовать публичные возможности Matplotlib вроде vector text/path API через изолированный adapter, не размазывая Matplotlib-specific код по всему проекту. Matplotlib поддерживает конвертацию MathText в paths, поэтому такой путь технически возможен. ([Matplotlib][2])

Pipeline желательно приблизить к:

```text
LaTeX
  ↓
Math layout
  ↓
positioned glyphs + structural strokes
  ↓
glyph centerline
  ↓
plot paths
```

вместо:

```text
LaTeX
  ↓
одна большая PNG/mask
  ↓
skeleton всей формулы
```

Старый raster path оставить как fallback.

**Готово, если:** базовые формулы можно построить через vector-first path, а raster pipeline используется только когда новый renderer не может корректно обработать выражение.

---

# Пункт 4 — отдельный кеш математических glyph

Не строить centerline символа `x`, `α`, `∫`, `=` или цифры заново в каждой формуле.

Добавить reusable math glyph cache, учитывающий:

```text
math font
glyph
font variant
centerline settings
algorithm version
```

Например:

```text
x
α
β
π
∞
∫
∑
=
+
-
(
)
```

должны компилироваться один раз.

Transform:

```text
cached glyph
    ↓
scale
    ↓
position from math layout
    ↓
final formula
```

**Готово, если:** стоимость повторяющейся формулы зависит в основном от layout и transform, а не повторной skeletonization всех символов.

### После 3–4

Запустить:

* formula geometry tests;
* math cache tests;
* visual regression;
* benchmark нескольких повторных формул.

```bash
git add -A
git commit -m "18-4"
```

---

# Пункт 5 — аналитические линии для математических конструкций

Там, где LaTeX structure явно задаёт прямую линию, не нужно пытаться восстанавливать её через raster skeleton.

Строить напрямую:

```text
fraction bar
overline
underline
root vinculum
matrix delimiters при возможности
```

Например:

```text
      x + 1
     ───────
      x - 1
```

горизонтальная линия дроби должна сразу становиться **одним stroke**, а не толстой полосой → raster → skeleton.

**Готово, если:** структурные линии формул представлены минимальным количеством чистых centerline strokes.

---

# Пункт 6 — Math Quality Gate 2.0

Расширить текущую проверку качества формул так, чтобы она анализировала не только факт получения centerline, но и структурные свойства результата.

Проверять минимум:

```text
empty geometry
NaN / Inf
слишком много components
неожиданно большой bbox
потерянные glyph
потерянные fraction/root lines
слишком большой retrace
аномально большое число pen lifts
выход за ожидаемый formula bbox
```

В `--strict-latex-quality` ошибка должна остановить job **до генерации G-code**.

В обычном режиме — warning + безопасный fallback, если он существует.

**Готово, если:** явно повреждённая формула не может тихо превратиться в «успешный» G-code.

### После 5–6

Запустить:

* lint;
* LaTeX tests;
* vector/raster comparison;
* math quality tests;
* determinism;
* geometry regression;
* G-code safety;
* representative DOCX/PDF integration.

```bash
git add -A
git commit -m "18-6"
```

# ОБЯЗАТЕЛЬНО ОСТАНОВИТЬСЯ

Написать:

```text
Остановился после 18-6. Готов продолжить с 18-7.
```

---

# Блок 2 — полноценный LaTeX layout, сложные формулы, OMML и PDF Math

## Пункт 7 — правильный inline math baseline

Исправить размещение inline-формул относительно обычного рукописного текста.

Например:

```text
Функция f(x) = x² + 1 является...
```

не должна выглядеть как:

```text
Функция      является...
        f(x)
```

Нужно учитывать:

```text
ascent
descent
baseline
formula height
normal text baseline
```

Именно baseline, а не просто центр bbox.

Проверить:

```text
x
x²
x_i
\frac{1}{2}
\sqrt{x}
\int_0^1 x dx
```

внутри обычного предложения.

**Готово, если:** inline math визуально стоит на одной естественной строке с handwriting text.

---

# Пункт 8 — полноценный display math layout

Блочные:

```latex
$$ ... $$
```

и:

```latex
\[ ... \]
```

должны становиться отдельными layout objects.

Нужно корректно учитывать:

```text
центрирование
vertical spacing before
vertical spacing after
formula bbox
page margins
pagination
```

Большая формула не должна пересекать соседний текст.

Если формула не помещается в остаток страницы, она должна целиком переходить на следующую страницу, если это возможно.

**Готово, если:** display equations корректно участвуют в pagination и сохраняют layout на A4/A5.

### После 7–8

```bash
git add -A
git commit -m "18-8"
```

---

# Пункт 9 — улучшить большие операторы, индексы и скобки

Добиться качественного отображения:

```latex
\sum_{i=0}^{n}
\prod_{k=1}^{m}
\int_0^\infty
\iint
\lim_{x\to0}
```

и конструкций:

```latex
\left(...)
\right)
\left[...\right]
\left\{...\right\}
```

Размер delimiters должен зависеть от содержимого.

Проверить сложные вложенные конструкции:

```latex
\left(
  \frac{x^2+1}
       {\sqrt{1-x}}
\right)
```

и nested superscript/subscript.

**Готово, если:** большие операторы, limits и scalable delimiters сохраняют правильное относительное положение и не разваливаются после centerline conversion.

---

# Пункт 10 — расширить набор поддерживаемых математических конструкций

Добавить/довести до рабочего состояния наиболее полезные для университетских документов конструкции.

Приоритет:

```text
\frac
\sqrt
\sqrt[n]
\sum
\prod
\int
\iint
\iiint
\lim
\sin
\cos
\tan
\cot
\ln
\log
\exp
\min
\max
\vec
\hat
\bar
\overline
\underline
\dot
\ddot
\mathbf
\mathrm
\mathit
\mathcal
\text
```

а также основные:

```text
Greek letters
relations
arrows
set operators
logic operators
partial derivatives
nabla
infinity
```

Не пытаться обещать «полный TeX».

Нужно получить **большое, явно протестированное университетское подмножество LaTeX**.

**Готово, если:** каждая заявленная конструкция присутствует в regression corpus и либо корректно рисуется, либо имеет конкретную понятную диагностику.

### После 9–10

```bash
git add -A
git commit -m "18-10"
```

---

# Пункт 11 — matrices, cases и многострочные формулы

Добавить поддержку наиболее важных многострочных mathematical structures.

Минимально:

```latex
\begin{matrix}
...
\end{matrix}
```

если текущий backend позволяет реализовать это безопасно,

либо собственное нормализованное представление для:

```text
matrix
pmatrix
bmatrix
cases
aligned-like rows
```

Примеры:

```latex
\begin{pmatrix}
a & b \\
c & d
\end{pmatrix}
```

и:

```text
f(x) = {
  x²,  x ≥ 0
  -x,  x < 0
}
```

Не обязательно поддерживать абсолютно весь синтаксис LaTeX environments.

Главное — нормальная математика для:

* матриц;
* систем;
* кусочно-заданных функций;
* нескольких строк вычисления.

**Готово, если:** эти структуры имеют корректные строки/столбцы, spacing, delimiters и pagination как единый formula object.

---

# Пункт 12 — серьёзно расширить DOCX OMML → Math pipeline

Расширить текущую поддержку Word Equation, чтобы математические объекты Word максимально преобразовывались в тот же Math Expression / geometry pipeline, что и LaTeX.

Покрыть минимум:

```text
fractions
subscript
superscript
sub+sup
radicals
n-ary
delimiters
functions
accents
limits
matrices
equation arrays
grouping
ordinary math runs
```

Особое внимание уделить:

```text
sin/cos/log/ln
дробь в степени
вложенным формулам
Unicode mathematical operators
```

потому что OMML → LaTeX преобразования имеют реальные edge cases даже в активно развиваемых сторонних проектах. ([GitHub][3])

Не превращать неизвестный OMML node молча в неправильный текст.

Для неизвестного элемента:

```text
warning
+
safe fallback
```

**Готово, если:** создан фиксированный DOCX corpus с native Word equations, который проходит geometry и semantic regression.

### После 11–12

Запустить:

* lint;
* full LaTeX corpus;
* inline baseline tests;
* display math tests;
* matrices/cases;
* OMML corpus;
* determinism;
* pagination regression;
* geometry regression;
* G-code safety;
* formula benchmark.

```bash
git add -A
git commit -m "18-12"
```

# ОБЯЗАТЕЛЬНО ОСТАНОВИТЬСЯ

Написать:

```text
Остановился после 18-12. Готов продолжить с 18-13.
```

---

# Блок 3 — PDF Math, SVG и сложная графика документов

## Пункт 13 — улучшить PDF Math reconstruction

Улучшить текущий `--pdf-math auto|visual|off`, чтобы формулы в PDF определялись точнее и не смешивались с обычным текстом/линиями.

Detector должен учитывать комбинации:

```text
font/style changes
superscript/subscript positioning
math symbols
fraction-like lines
dense operator regions
baseline structure
nearby text primitives
```

Нужно снизить:

```text
false positive
false negative
двойную печать
```

Если PDF уже содержит хорошую vector geometry формулы, предпочитать её сохранение, а не ненужную растеризацию.

Low-confidence region должен сохранять безопасный fallback.

**Готово, если:** corpus PDF с обычным текстом и математикой показывает более стабильное выделение formula regions без поглощения соседнего текста.

---

# Пункт 14 — native SVG input

Добавить SVG как полноценный входной формат:

```bash
plotter-processor run drawing.svg ...
```

SVG paths должны по возможности проходить:

```text
SVG
 ↓
vector paths
 ↓
normalize transforms
 ↓
flatten curves при необходимости
 ↓
simplify
 ↓
route
 ↓
G-code
```

а не:

```text
SVG
→ bitmap
→ tracing
```

Поддержать минимум:

```text
path
line
polyline
polygon
rect
circle
ellipse
основные transforms
viewBox
```

Text внутри SVG можно обрабатывать отдельно через понятный fallback.

**Готово, если:** простой векторный чертёж сохраняет свою геометрию до G-code без raster round-trip.

### После 13–14

```bash
git add -A
git commit -m "18-14"
```

---

# Пункт 15 — улучшить DOCX/PDF схемы и shapes

Расширить существующую semantic обработку линий, стрелок и фигур.

Приоритет:

```text
straight arrows
double arrows
rectangles
circles
ellipses
connectors
simple flowchart shapes
grouped simple shapes
```

Геометрические элементы должны по возможности превращаться непосредственно в plot paths.

Особенно важно корректно сохранять:

```text
позицию
размер
направление стрелки
связь с текстом
```

Не делать raster screenshot всей страницы только ради простой схемы.

**Готово, если:** типовая учебная схема из Word/PDF переносится как vector geometry.

---

# Пункт 16 — несколько режимов обработки растровых изображений

Для raster image добавить явные стратегии:

```text
outline
centerline
hatching
```

`outline` — выделяет основные контуры.

`centerline` — подходит для line-art/сканов схем.

`hatching` — передаёт светлоту изображения плотностью штрихов.

Режим должен задаваться конфигом/CLI, но существующее default behaviour не ломать.

Для сложного изображения перед генерацией тысяч strokes применять ограничения:

```text
min feature size
max path count
simplification
target resolution
```

**Готово, если:** одна и та же картинка может осмысленно преобразовываться минимум двумя разными plotter-oriented способами.

### После 15–16

```bash
git add -A
git commit -m "18-16"
```

---

# Пункт 17 — общий complex-document regression corpus

Создать компактный, но сильный regression corpus документов.

Он должен обязательно содержать:

### LaTeX

```text
inline math
display math
fraction
nested fraction
roots
powers
indices
Greek
integrals
sums
limits
functions
large delimiters
matrices
cases
multi-line formulas
```

### DOCX

```text
native OMML equations
table + equation
equation + image
formula near page break
diagram + text
```

### PDF

```text
vector formula
mixed text/math
formula near diagram
line-based table
```

### SVG

```text
curves
lines
transforms
arrows
closed paths
```

Для math corpus обязательно хранить representative SVG preview для визуального сравнения.

**Готово, если:** дальнейшее изменение math/document pipeline можно проверить одной автоматической regression-командой.

---

# Пункт 18 — финальный Math/Document audit

Провести полный аудит `UPD_Plotter_18` и сравнить новый math pipeline со старым.

Проверить минимум:

```text
правильность parsing
formula bbox
inline baseline
display positioning
pagination
centerline quality
pen lifts
math cache hits
vector-first usage
raster fallback usage
OMML coverage
PDF math coverage
SVG geometry
G-code safety
determinism
performance
```

В итоговый `report.json` добавить компактную math statistics секцию, если такой информации ещё нет.

Например:

```text
math:
  formulas_total
  latex
  omml
  pdf_visual
  vector_rendered
  raster_fallback
  cache_hits
  warnings
  quality_failures
```

Не создавать отдельный огромный `.md` report, если существующего report/audit механизма достаточно.

**Готово, если:** новый pipeline стабильно обрабатывает regression corpus и не ухудшает обычные документы без формул.

### После 17–18

Запустить полный доступный набор:

```text
lint
unit tests
LaTeX regression corpus
LaTeX malformed corpus
inline math tests
display math tests
matrix/cases tests
OMML DOCX corpus
PDF math corpus
SVG integration
image integration
DOCX integration
PDF integration
pagination regression
determinism
geometry regression
G-code safety
math cache tests
benchmark
```

После успешной проверки:

```bash
git add -A
git commit -m "18-18"
```

# ОБЯЗАТЕЛЬНО ОСТАНОВИТЬСЯ

Написать только:

```text
UPD_Plotter_18 завершён на 18-18; Math/LaTeX, OMML, PDF Math и vector regression выполнены.
```

---

# Критичные ограничения UPD_Plotter_18

## 1. LaTeX — главный приоритет

Если какой-либо secondary feature начинает слишком раздувать обновление, в первую очередь должны быть полностью закончены:

```text
18-1 — 18-12
```

То есть **Math/LaTeX + OMML**.

SVG/images можно урезать, math — нельзя.

---

## 2. Не обещать полный TeX

Не пытаться реализовать:

```latex
\documentclass
\usepackage
TikZ
bibliography
arbitrary macros
\input
\include
shell escape
```

Это не LaTeX compiler.

Цель:

> **очень хорошая поддержка формул в LaTeX syntax.**

---

## 3. Не запускать системный LaTeX автоматически

Основной безопасный режим должен продолжать работать без:

```text
pdflatex
xelatex
lualatex
shell
```

Если когда-нибудь будет добавлен полноценный внешний TeX backend, это отдельная optional feature с отдельной security моделью, а не задача этого этапа.

---

## 4. Vector-first, но raster fallback сохранить

Правильная архитектура:

```text
               ┌─ vector-first ─→ centerline
Math expression│
               └─ raster fallback → centerline
```

Нельзя удалить существующий рабочий fallback раньше, чем новый path докажет качество на regression corpus.

---

## 5. Не skeletonize всю формулу без необходимости

Если формула:

```latex
\frac{x+1}{y}
```

содержит:

```text
x
+
1
y
fraction line
```

то желательно:

* reusable glyph geometry для символов;
* аналитический stroke для fraction bar;
* layout transform.

Не превращать всё каждый раз в одну огромную картинку.

---

## 6. Math glyph cache должен быть независим от документа

Повторный:

```text
∫
x
π
=
```

в другом документе не должен требовать заново компилировать тот же math glyph при одинаковых настройках.

---

## 7. Formula layout и document layout — разные уровни

Сначала:

```text
LaTeX
→ внутренний layout формулы
→ formula bbox
```

потом:

```text
formula bbox
→ document layout
→ page
```

Document paginator не должен сам понимать внутреннюю структуру дробей и интегралов.

---

## 8. Не подгонять формулу растяжением по X/Y

Если выражение не помещается, нельзя просто сделать:

```text
scale_x = 0.6
scale_y = 1.0
```

и исказить математику.

Масштабировать пропорционально.

---

## 9. Не переносить обычную inline-формулу посередине структуры

Нельзя получить:

```text
\frac{x +
[NEW LINE]
1}{y}
```

Простая formula object должна быть atomic для document line breaking.

Многострочные environments имеют собственные правила.

---

## 10. Формула не должна становиться handwriting variation

Обычный текст может иметь Handwriting 2.0 variation.

Математическая геометрия должна оставаться значительно стабильнее, чтобы:

```text
=
≠
+
-
×
∫
√
```

не искажались случайным handwriting transform.

Если variation применяется — только через отдельный очень консервативный `math handwriting profile`.

---

## 11. Mathematical semantics важнее минимизации pen lifts

Нельзя ради непрерывного stroke соединить:

```text
числитель
fraction bar
знаменатель
```

линией, которой в формуле не существует.

Routing может повторять существующие линии или менять порядок strokes, но не должен добавлять ложную математическую геометрию.

---

## 12. OMML не превращать бездумно в строку LaTeX

Если Word already содержит структурную информацию:

```text
fraction
radical
matrix
n-ary
```

предпочтительно переводить её в общий Math Model.

LaTeX-like string можно сохранять для debug/extract, но она не обязана быть единственным internal representation.

---

## 13. PDF Math не должен печататься два раза

После поглощения primitives formula region эти:

```text
text primitives
vector lines
formula geometry
```

не должны отдельно снова попадать в output.

Это уже принцип текущего pipeline, его обязательно сохранить. ([GitHub][1])

---

## 14. SVG не растрировать без причины

Если вход уже содержит Bézier/vector geometry — сохранить её.

---

## 15. Не делать OCR в UPD_Plotter_18

OCR формул/сканов — отдельная большая задача.

В этом этапе:

```text
PDF with text/vector layer → да
native DOCX math → да
LaTeX syntax → да
SVG → да

photo formula → OCR → не здесь
```

---

# Главный тестовый LaTeX corpus

Я бы прямо обязательно заставил Codex покрыть такие формулы.

### Простая

```latex
x^2 + y^2 = z^2
```

### Дробь

```latex
\frac{x^2 + 1}{x - 1}
```

### Вложенная дробь

```latex
\frac{1}{1 + \frac{1}{x}}
```

### Корень

```latex
\sqrt{x^2 + y^2}
```

### Корень степени n

```latex
\sqrt[3]{x+1}
```

### Интеграл

```latex
\int_0^\infty x^2 e^{-x}\,dx
```

### Сумма

```latex
\sum_{n=1}^{\infty} \frac{1}{n^2}
```

### Предел

```latex
\lim_{x \to 0} \frac{\sin x}{x} = 1
```

### Производная

```latex
\frac{d}{dx}f(x)
```

### Частная производная

```latex
\frac{\partial f}{\partial x}
```

### Большие скобки

```latex
\left(
\frac{x+1}{x-1}
\right)^2
```

### Вектор

```latex
\vec{F} = m\vec{a}
```

### Греческие буквы

```latex
\alpha + \beta = \gamma
```

### Матрица

```latex
\begin{pmatrix}
1 & 2 \\
3 & 4
\end{pmatrix}
```

если выбранный parser/backend поддерживает environment через новый слой.

### Система

```text
x + y = 10
2x - y = 5
```

через поддерживаемый cases/aligned representation.

### Длинная университетская формула

```latex
f(x)=\frac{1}{\sigma\sqrt{2\pi}}
e^{-\frac{(x-\mu)^2}{2\sigma^2}}
```

### Формула внутри текста

```text
Из соотношения $E = mc^2$ следует...
```

### Несколько формул в строке

```text
Если $x>0$, то $x^2>0$.
```

---

# Особенно важный визуальный тест

Сделать один отдельный документ примерно такого вида:

```text
Математический тест плоттера

Квадратное уравнение:
ax² + bx + c = 0

Формула корней:

       -b ± √(b² - 4ac)
x = ───────────────────
              2a

Интеграл:

∞
⌠
⎮ x²e⁻ˣ dx = 2
⌡
0

Предел:

          sin(x)
lim       ────── = 1
x → 0       x

Матрица:

⎛ 1  2 ⎞
⎜      ⎟
⎝ 3  4 ⎠
```

И сохранять его как один из canonical visual regression examples.

---

# Что должно измениться концептуально

### Сейчас

```text
LaTeX
  ↓
MathText
  ↓
high-resolution raster
  ↓
mask
  ↓
skeleton
  ↓
centerline
```

Это уже работает как MVP. ([GitHub][1])

### После UPD_Plotter_18

Желательно:

```text
                 LaTeX
                   │
                   ▼
             normalize/parse
                   │
                   ▼
            Math Expression
                   │
                   ▼
              Math Layout
                   │
         ┌─────────┴─────────┐
         │                   │
    positioned glyphs   structural lines
         │                   │
         ▼                   ▼
     glyph cache        direct strokes
         │                   │
         └─────────┬─────────┘
                   ▼
            Math Geometry
                   │
              quality gate
                   │
                   ▼
            Document Layout
                   │
                   ▼
                G-code
```

И только fallback:

```text
unsupported vector case
        ↓
high-res raster
        ↓
centerline
```

---

# Метрики в конце

Codex должен вывести максимально короткую сводку, например:

```text
UPD_Plotter_18

LaTeX corpus: PASS
Inline baseline: PASS
Display math: PASS
OMML corpus: PASS
PDF Math: PASS
SVG: PASS

Math formulas: 84
Vector-first: 77
Raster fallback: 7
Quality failures: 0

Determinism: PASS
Geometry: PASS
G-code safety: PASS
```

Особенно полезна метрика:

```text
vector-first / raster-fallback
```

Потому что в итоге хочется, чтобы нормальные формулы почти всегда шли через качественный новый путь.

---

# Полная последовательность коммитов

Первый заход — **Math Core**:

```text
18-1
18-2
COMMIT 18-2

18-3
18-4
COMMIT 18-4

18-5
18-6
COMMIT 18-6

STOP
```

Второй заход — **Math Layout + LaTeX + OMML**:

```text
18-7
18-8
COMMIT 18-8

18-9
18-10
COMMIT 18-10

18-11
18-12
COMMIT 18-12

STOP
```

Третий заход — **PDF Math + SVG + Graphics**:

```text
18-13
18-14
COMMIT 18-14

18-15
18-16
COMMIT 18-16

18-17
18-18
COMMIT 18-18

STOP
```

То есть:

```text
18-2
18-4
18-6
STOP

18-8
18-10
18-12
STOP

18-14
18-16
18-18
STOP
```

**18 пунктов → 9 коммитов → 3 захода Codex.**

И здесь я бы действительно считал **пункты 1–12 основными**, а `13–18` вторичными. После `UPD_Plotter_18` цель должна быть не просто «плоттер умеет что-то нарисовать по `$...$`», а **можно взять нормальный вузовский документ с дробями, интегралами, суммами, индексами, матрицами и Word Equation — и формулы будут выглядеть как математические формулы, иметь нормальные центральные линии и не превращаться в кашу из skeletonized bitmap.**

[1]: https://github.com/BMSTU-LYGO/plotter-proc "GitHub - BMSTU-LYGO/plotter-proc · GitHub"
[2]: https://matplotlib.org/3.9.3/api/text_api.html?utm_source=chatgpt.com "matplotlib.text — Matplotlib 3.9.3 documentation"
[3]: https://github.com/docling-project/docling/issues/3120?utm_source=chatgpt.com "OMML-to-LaTeX conversion produces incorrect output for fractions, math operators, and functions · Issue #3120 · docling-project/docling · GitHub"
