```md
# UPD — REAL PLOTTER SPEED / MARLIN MOTION TUNING

Проект:

https://github.com/BMSTU-LYGO/plotter-proc

Работать с текущим `master`.

## Цель

Предыдущая оптимизация практически не изменила реальную скорость письма.

Нужно найти и устранить причину, по которой повышение скорости в pipeline не приводит к ускорению физического плоттера.

Целевая скорость:

```text
текущий документ: ~10 минут
цель: ~3–4 минуты
```

На этом этапе НЕ менять:

- геометрию букв;
- Bezier/smoothing;
- handwriting variation;
- PFC/font pipeline;
- высоту `pen up / pen down`;
- word routing, если он уже работает корректно;
- layout.

Работаем только с:

```text
G-code feedrate
+
Marlin motion limits
+
acceleration
+
junction / jerk
+
проверка реального G-code
```

---

# 1. Проверить реальный источник feedrate

Найти весь код и конфиги, откуда берётся скорость:

```text
draw feedrate
travel feedrate
Z feedrate
acceleration
max feedrate
jerk / junction deviation
```

Особенно проверить:

```text
configs/machine.yaml
Makefile
CLI overrides
defaults в C++
G-code generator
```

Не должно быть ситуации, когда:

```text
config = F6000
```

а в G-code остаётся:

```text
F1200
F2000
F2700
```

Для draw должен использоваться один speed.

---

# 2. Сделать один быстрый draw feedrate

Установить основной draw feedrate:

```yaml
draw: 6000
```

То есть:

```text
100 mm/s
```

Использовать его для всех XY moves с опущенным пером.

НЕ делать:

```text
TIGHT / NORMAL / FAST
```

НЕ менять скорость по кривизне.

Все draw strokes:

```gcode
G1 F6000
```

Travel оставить отдельным.

Не писать `F6000` перед каждым `G1`.

Feedrate указывать только когда он реально меняется.

---

# 3. Проверить generated G-code

После генерации автоматически проверить итоговый `.gcode`.

Для XY draw moves вывести список всех встреченных feedrate.

Ожидаемый результат:

```text
DRAW feedrates:
6000
```

Не должно оставаться:

```text
1200
2000
2700
...
```

кроме Z или других специально отличающихся операций.

Если старые feedrate остаются — найти источник и удалить старую velocity classification.

---

# 4. Добавить управление Marlin motion limits

Одного `F6000` недостаточно.

Добавить в machine config параметры физического движения XY.

Например:

```yaml
motion:
  max_xy_feedrate_mm_s: 120
  draw_acceleration_mm_s2: 1500
  travel_acceleration_mm_s2: 2000
  xy_jerk_mm_s: 15
```

Названия адаптировать под существующий config style.

Все значения configurable.

Не хардкодить tuning parameters внутри generator.

---

# 5. Генерировать Marlin setup в начале G-code

В начале документа выставлять необходимые motion settings.

Для максимального XY feedrate использовать Marlin:

```gcode
M203
```

Для acceleration:

```gcode
M204
```

Для classic jerk, если он поддерживается текущей прошивкой:

```gcode
M205
```

Примерно:

```gcode
M203 X120 Y120
M204 P1500 T2000
M205 X15 Y15
```

Но перед реализацией проверить существующую версию/конфигурацию Marlin проекта.

Не отправлять неподдерживаемые команды вслепую.

Если используется Junction Deviation вместо Classic Jerk — использовать соответствующую существующей прошивке настройку.

---

# 6. Не ограничивать скорость C++ pipeline

Проверить весь путь:

```text
config
→ document processor
→ route
→ G-code generator
```

Найти:

- `min()`;
- clamp;
- старые velocity classes;
- локальные hardcoded feedrates;
- дефолт `2000`;
- автоматическое снижение скорости на curves.

Для текущего fast mode всё это не должно снижать `draw` ниже заданного `6000`.

---

# 7. Сделать диагностический benchmark

Добавить небольшой benchmark G-code.

Одна и та же тестовая строка должна генерироваться с:

```text
F2000
F4000
F6000
```

Например:

```text
машина машина машина
```

Геометрия во всех трёх вариантах должна быть абсолютно одинаковой.

Меняется только feedrate.

Сохранить:

```text
bench_F2000.gcode
bench_F4000.gcode
bench_F6000.gcode
```

Они нужны для физического теста плоттера.

---

# 8. Добавить estimator времени

Добавить простой анализ итогового G-code.

Считать минимум:

```text
draw_distance_mm
travel_distance_mm
z_distance_mm

draw_moves
travel_moves
pen_lifts

feedrate_changes

estimated_draw_time
estimated_travel_time
estimated_z_time
estimated_total_time
```

Но учитывать acceleration хотя бы приближённо.

Не считать время исключительно:

```text
distance / max_feedrate
```

для коротких сегментов.

Для сегмента использовать trapezoidal/triangular motion approximation с заданным acceleration.

Минимум:

```text
если segment достаточно длинный:
    accelerate
    cruise
    decelerate
иначе:
    triangular velocity profile
```

Это нужно, чтобы видеть реальную разницу между:

```text
F2000
F4000
F6000
```

при коротких strokes.

---

# 9. Проверить acceleration bottleneck

После estimator вывести:

```text
requested_speed
estimated_average_draw_speed
```

Например:

```text
requested: 100 mm/s
average:   31 mm/s
```

Если средняя скорость намного ниже requested, определить почему:

```text
short segments
acceleration
junction limits
firmware max feedrate
```

Вывести процент draw path, где машина теоретически успевает достигнуть заданного `F6000`.

Метрика:

```text
segments_reaching_cruise_speed_ratio
```

---

# 10. Проверить длины XY segments

Для итогового документа вывести:

```text
min_segment_mm
p25_segment_mm
median_segment_mm
p75_segment_mm
mean_segment_mm
max_segment_mm
```

И:

```text
segments_lt_0_1mm
segments_lt_0_25mm
segments_lt_0_5mm
segments_lt_1mm
```

Ничего автоматически не менять в geometry на этом этапе.

Нужно понять, насколько acceleration ограничивает текущую траекторию.

---

# 11. Не менять Z

Текущие:

```text
pen up/down height
Z feedrate
settle
```

оставить без изменений.

Это отдельная оптимизация.

В этом update не использовать уменьшение Z distance для получения красивых benchmark results.

---

# 12. Word routing

Не переписывать существующий word routing.

Только добавить метрику:

```text
pen_lifts_per_word
```

и убедиться, что предыдущая оптимизация действительно работает.

Если среднее всё ещё сильно больше:

```text
2
```

только зафиксировать это в финальном отчёте.

Не смешивать исправление routing с motion tuning этого update.

---

# 13. Убрать конфликтующие machine configs

Проверить:

```text
Makefile
configs/
scripts/
CLI
tests
```

Должен существовать один понятный источник machine parameters.

Если разные команды используют:

```text
machine.yaml
machine-a4.yaml
hardcoded defaults
```

привести это к однозначной системе.

Нельзя допускать ситуацию:

```text
пользователь меняет machine.yaml
```

но генератор реально читает другой файл.

---

# 14. Fast preset не нужен

Не создавать:

```text
slow
normal
fast
turbo
```

На данном этапе нужен один рабочий режим — максимально быстрый.

Текущий основной config должен использовать новые быстрые параметры.

---

# 15. Tests

Добавить тесты:

### Feedrate

Проверить:

```text
draw = F6000
```

и отсутствие старых draw speeds.

### Marlin preamble

Проверить наличие корректных:

```text
M203
M204
M205 / используемой альтернативы
```

### Feedrate duplication

Не должно быть:

```gcode
G1 F6000 ...
G1 F6000 ...
G1 F6000 ...
```

если feedrate не изменяется.

### Config

Проверить, что изменение machine config реально отражается в generated G-code.

### Estimator

Проверить:

```text
F4000 быстрее F2000
F6000 быстрее F4000
```

для достаточно длинной траектории.

И проверить acceleration-limited короткий segment.

---

# 16. Benchmark текущего документа

На том же документе, который раньше писал около 10 минут, вывести:

```text
BEFORE
draw feedrate:
draw distance:
draw moves:
feedrate changes:
pen lifts:
estimated draw time:
estimated total time:
estimated average XY speed:

AFTER
draw feedrate:
draw distance:
draw moves:
feedrate changes:
pen lifts:
estimated draw time:
estimated total time:
estimated average XY speed:
```

Геометрия должна остаться практически идентичной.

---

# 17. Главный критерий

После update итоговый G-code должен использовать:

```text
draw = 6000 mm/min
```

и Marlin не должен быть искусственно ограничен старыми acceleration / max-feedrate settings.

Требуется получить существенное сокращение estimated execution time.

Целевой порядок:

```text
было: ~10 минут
цель: ~3–4 минуты
```

Если estimator показывает, что даже после motion tuning 3–4 минуты недостижимы:

НЕ придумывать дополнительные оптимизации.

В финальном отчёте точно указать bottleneck:

```text
X% acceleration limited
Y% draw time
Z% travel
N% Z/pen lifts
```

---

# 18. Порядок работ

Выполнять:

```text
1. найти все источники feedrate
2. убрать старую multi-speed logic
3. установить single F6000
4. проверить generated G-code
5. добавить machine motion parameters
6. добавить Marlin preamble
7. устранить конфликты machine configs
8. добавить motion time estimator
9. добавить diagnostic metrics
10. создать F2000/F4000/F6000 benchmark
11. regression tests
12. benchmark полного документа
```

---

# 19. Git

Коммиты:

```text
SPEED-1  single draw feedrate
SPEED-2  Marlin motion config
SPEED-3  machine config cleanup
SPEED-4  motion estimator
SPEED-5  benchmark and regression tests
```

После каждого commit:

```text
build PASS
tests PASS
```

---

# 20. Формат ответа

Не писать длинные отчёты.

После каждого блока:

```text
DONE: ...
TESTS: ...
METRIC: ...
```

В финале только:

```text
BEFORE
...

AFTER
...

BOTTLENECK
...

CHANGED FILES
...
```

---

# Важно

Не считать задачу выполненной только потому, что в конфиге появилось:

```text
6000
```

Нужно доказать через итоговый generated G-code, что:

1. draw moves реально используют `F6000`;
2. старые `F1200/F2000/F2700` удалены;
3. Marlin motion limits выставляются достаточно высоко;
4. estimator показывает реальное ускорение;
5. тестовые `F2000/F4000/F6000` дают разные ожидаемые времена;
6. параметры берутся именно из того machine config, который используется при реальном запуске.
```