# PLOTTER — FAST WRITING + WORD ROUTING

Проект:  
https://github.com/BMSTU-LYGO/plotter-proc

Работать с текущей C++-реализацией проекта.

## Цель

На этом этапе сделать только три вещи:

1. объединять пользовательский `.pfc` со специальным предкомпилированным `.pfc`;
2. писать все рисующие XY-движения на одной максимальной скорости;
3. сократить количество `pen up / pen down` внутри одного слова до примерно 1–2 проходов, если топология символов не требует большего.

Не заниматься сейчас:

- вариативностью букв;
- baseline noise;
- несколькими версиями glyph;
- разными скоростными профилями;
- curvature-aware feedrate;
- изменением высоты подъёма пера;
- page-level TSP;
- большим архитектурным рефакторингом.

---

## 1. Объединение пользовательского PFC со специальным PFC

Есть:

```text
user.pfc
special.pfc
```

`special.pfc` заранее скомпилирован и общий для всех пользовательских шрифтов.

При подготовке пользовательского шрифта собрать итоговый:

```text
user.pfc
+
special.pfc
↓
merged.pfc
```

Правило:

```text
если codepoint есть в user.pfc:
    использовать пользовательский glyph

иначе если codepoint есть в special.pfc:
    добавить glyph из special.pfc

иначе:
    оставить существующее поведение missing glyph
```

Важно:

- glyph из `special.pfc` не изменять;
- не масштабировать его под пользовательский шрифт;
- не деформировать;
- не делать runtime fallback;
- физически добавлять недостающие glyph в итоговый `.pfc`;
- пользовательский glyph всегда имеет приоритет;
- не создавать дубликаты codepoint.

Если special PFC несколько, порядок должен быть deterministic:

```text
user
→ special-common
→ special-extra
```

Добавить статистику:

```text
user_glyphs
special_glyphs_added
duplicate_special_glyphs_skipped
missing_codepoints
```

---

## 2. Один быстрый draw feedrate

Не использовать несколько профилей скорости.

Убрать или отключить:

```text
TIGHT
NORMAL
FAST
```

Все рисующие XY-движения выполнять с одним configurable draw feedrate.

Начальное значение:

```text
draw_feedrate = 6000 mm/min
```

То есть:

```text
100 mm/s
```

Если в проекте уже есть:

```text
feedrate.draw
```

использовать его.

Не создавать второй параметр.

Не вставлять `F` перед каждым сегментом.

Предпочтительно:

```gcode
G1 F6000
G1 ...
G1 ...
G1 ...
```

а не:

```gcode
G1 F6000 ...
G1 F6000 ...
G1 F6000 ...
```

Z-параметры и высоту подъёма пера не менять.

---

## 3. Существующую оптимизацию кривых сохранить

Не откатывать уже сделанные:

```text
centerline
→ cleanup
→ smoothing / Bezier
→ adaptive resampling
→ routing
→ G-code
```

Не добавлять новую curvature-based velocity logic.

Следить только за тем, чтобы не появлялось массово бессмысленных микросегментов.

---

## 4. Перейти к word-level routing

Главная задача этого этапа — перестать автоматически поднимать перо на границе каждого glyph.

Сейчас условно:

```text
glyph1
UP
glyph2
UP
glyph3
UP
```

Нужно:

```text
WORD
↓
максимально длинный непрерывный маршрут
↓
UP только там, где это реально необходимо
```

Цель:

```text
обычное слово:
1–2 pen-down groups
```

Исключения:

- `й`;
- `ё`;
- отдельные точки;
- диакритика;
- топологически отдельные компоненты, которые нельзя корректно встроить в основной маршрут.

Не соединять компоненты искусственными линиями через пустое пространство.

---

## 5. Собрать strokes на уровне слова

После layout собрать strokes всех glyph одного слова в общей системе координат.

Для каждого stroke необходимо знать минимум:

```cpp
struct Stroke {
    Point start;
    Point end;
    Polyline path;
    bool reversible;
    bool auxiliary;
};
```

Использовать существующие структуры проекта, если они уже есть.

`reversible` означает возможность писать stroke:

```text
start → end
```

или:

```text
end → start
```

без изменения визуального результата.

---

## 6. Оптимизировать порядок strokes внутри слова

Для каждого слова подобрать порядок strokes с приоритетом:

```text
1. минимальное количество pen lifts
2. минимальная длина pen-up travel
```

Использовать:

- изменение направления stroke;
- выбор лучшей точки начала;
- выбор лучшей точки окончания;
- соединение совместимых strokes;
- routing между glyph одного слова.

Не оптимизировать сейчас всю страницу.

---

## 7. Safe joins между соседними glyph

Если:

```text
stroke A end
```

находится достаточно близко к:

```text
stroke B start
```

можно оставить перо опущенным.

Добавить:

```text
max_word_join_distance_mm
```

Начать примерно с:

```text
1.0–2.0 mm
```

Соединение разрешать только если переход:

- короткий;
- не проходит через середину другой буквы;
- не создаёт длинную диагональ;
- не проходит через большое пустое пространство;
- визуально соответствует нормальному межбуквенному переходу.

Не строить сейчас сложные декоративные Bezier-соединения.

При сомнении делать `pen up`.

---

## 8. Auxiliary components

Отдельные элементы символов помечать как:

```text
auxiliary = true
```

Примеры:

```text
й → верхний элемент
ё → две точки
```

Основную часть слова писать сначала максимально непрерывно.

После этого выполнять auxiliary-компоненты отдельными короткими проходами.

Примеры целевого поведения:

```text
машина
→ 1 pen-down group
```

или максимум:

```text
машина
→ 2 pen-down groups
```

А:

```text
моё
```

может требовать дополнительного прохода для точек `ё`.

---

## 9. Не поднимать перо на границе glyph автоматически

Удалить логику вида:

```text
glyph finished
→ pen up
```

Граница glyph сама по себе не должна приводить к подъёму пера.

Поднимать перо только если:

```text
нет допустимого следующего stroke
```

или:

```text
следующий компонент auxiliary / disconnected
```

Routing должен выполняться на уровне слова.

---

## 10. Добавить WordRoute

Нужен отдельный этап:

```text
Glyph routes
↓
WordRouteBuilder
↓
WordRoute
↓
G-code
```

`WordRoute` должен описывать физическую последовательность:

```text
DRAW
DRAW
DRAW
TRAVEL
DRAW
```

Можно использовать существующие типы проекта.

Главное — отделить:

```text
геометрию glyph
```

от:

```text
физического порядка выполнения strokes внутри слова
```

---

## 11. Использовать простой greedy routing

Exact solver сейчас не нужен.

Достаточно:

```text
current endpoint
↓
найти следующий невыполненный stroke
↓
проверить normal/reversed orientation
↓
выбрать лучший допустимый переход
```

Cost:

```text
continuous draw = минимальная стоимость

short safe pen-down join = небольшая стоимость

pen-up transition = большая стоимость
```

Главная оптимизируемая величина:

```text
number_of_pen_lifts
```

---

## 12. Защита от неправильных соединений

Если соединение сомнительное:

```text
pen up
```

Лучше получить один лишний подъём, чем испортить букву.

Обязательно проверить символы:

```text
ж
ф
х
т
д
б
в
й
ё
```

Не ломать существующий topology-aware routing внутри glyph.

---

## 13. Метрики

Для документа считать:

```text
word_count

pen_down_count
pen_lift_count

pen_lifts_per_word_avg

words_with_1_pen_down
words_with_2_pen_down
words_with_3plus_pen_down

draw_length_mm
pen_up_travel_mm

gcode_draw_segments
gcode_travel_segments

feedrate_change_count
```

Главная метрика:

```text
pen_lifts_per_word_avg
```

Цель:

```text
обычный русский текст:
≈ 1–2
```

---

## 14. Сравнение с текущим G-code

Использовать текущий `output.gcode` как baseline.

До изменений посчитать:

```text
pen_lift_count
draw_length_mm
travel_length_mm
draw_segment_count
travel_segment_count
feedrate_change_count
estimated_execution_time
```

После изменений вывести:

```text
BEFORE → AFTER
```

Особенно сравнить:

```text
pen lifts
feedrate changes
estimated execution time
```

---

## 15. Regression tests

Минимальный набор:

```text
мама
машина
данные
значение
переписать
йод
моё
ёлка
```

Проверить:

- обычные слова не получают лишних подъёмов;
- `й` сохраняет отдельный верхний компонент;
- `ё` сохраняет обе точки;
- нет длинных неправильных соединений;
- topology glyph не меняется;
- пользовательский glyph имеет приоритет над special PFC;
- special glyph добавляется только если пользовательского нет;
- итоговый текст остаётся читаемым.

---

## 16. Порядок реализации

Делать строго в таком порядке:

```text
1. PFC merge
2. single fast draw feedrate
3. убрать лишние F changes
4. word-level stroke collection
5. reversible stroke routing
6. safe inter-glyph joins
7. auxiliary components
8. metrics
9. regression tests
10. benchmark against output.gcode
```

---

## 17. Git

Коммиты:

```text
FAST-1  PFC merge
FAST-2  single draw feedrate
FAST-3  WordRoute
FAST-4  word stroke optimizer
FAST-5  safe joins + auxiliary components
FAST-6  metrics/tests/benchmark
```

После каждого commit проект должен собираться, существующие тесты должны проходить.

---

## 18. Формат отчёта Codex

Писать в чат минимум.

После каждого commit:

```text
DONE: ...
TESTS: ...
METRIC: ...
```

Финальный отчёт:

```text
BEFORE
pen lifts:
feedrate changes:
estimated time:

AFTER
pen lifts:
feedrate changes:
estimated time:
```

Плюс список изменённых файлов.

---

# Критерий готовности

PFC:

```text
user.pfc
+
special.pfc
↓
merged.pfc
```

Runtime использует один готовый cache.

Письмо:

```text
Word
↓
Word-level stroke routing
↓
обычно 1–2 pen-down groups
↓
single fast draw feedrate
↓
G-code
```

При конфликте приоритетов:

```text
1. корректная геометрия
2. минимальное количество подъёмов пера
3. минимальный travel
```

Нельзя ухудшать форму букв только ради уменьшения количества pen lifts.
