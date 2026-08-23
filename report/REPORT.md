# Повторный quality audit — 2026-08-23

## Итог

Текущее состояние ветки `ref` прошло повторный аудит. Блокирующих дефектов и
регрессий не обнаружено: lint, 268 tests, smoke, основная DOCX/PDF-матрица,
детерминизм и независимая проверка G-code завершились успешно.

Аудит выполнен на `HEAD 47524e25b0ec3634c4460df001e3d52f10a72ce0` с
намеренно незакоммиченными изменениями блоков UPD_Plotter_11. Эти изменения
не модифицировались в рамках cleanup отчёта.

## Quality gates

| Проверка | Результат |
|---|---|
| `make lint` | passed |
| `make test` | 268 passed за 20.81 s |
| `make smoke` | passed |
| `make font-cache-status FONT=assets/1.ttf` | valid, v7, 169 glyphs, 18,393,613 bytes |
| `git diff --check` | passed |

## Интеграционная матрица

| Job | Status | Pages | Strokes | Points | Warnings | Overlaps, mm² |
|---|---|---:|---:|---:|---:|---:|
| DOCX centerline / hybrid / safe | ok | 20 | 6,453 | 111,714 | 0 | 0 |
| DOCX outline / hybrid / off | ok | 20 | 11,840 | 241,964 | 1 | 0 |
| PDF centerline / preserve | ok | 32 | 8,215 | 104,939 | 40 | 1,634.989986 |
| PDF centerline / reflow | ok | 33 | 8,217 | 104,957 | 40 | 0 |
| Connections off | ok | 1 | 634 | 10,445 | 0 | 0 |
| Connections safe | ok | 1 | 529 | 10,603 | 0 | 0 |
| Connections aggressive | ok | 1 | 529 | 10,603 | 0 | 0 |

Основной DOCX job: draw `71,014.932 mm`, travel `54,960.241 mm`, 1,359
соединений из 5,747 пар, длина коннекторов `1,543.326153 mm`. Четыре формулы
отрисованы без fallback и `needs_review`.

PDF preserve и reflow оба отрисовали 3 visual math expressions, 83 strokes и
996 points без math fallback. Наложения preserve соответствуют контракту
сохранения исходной раскладки; тот же документ в reflow имеет нулевые
наложения. 40 предупреждений в каждом PDF job относятся к low-confidence math
candidates и rasterization сложных drawings и не прерывают pipeline.

Connection corpus подтвердил 105 соединений из 510 в safe и aggressive против
0 в off. Safe/aggressive дают одинаковую геометрию на этом корпусе, но разные
причины отклонений; различие режимов дополнительно покрыто targeted regression
test из блока 4.

## Детерминизм

Два независимых запуска основного DOCX job дали побайтово одинаковые:

- `20/20 paths.json`;
- `20/20 page.gcode`;
- `20/20` page previews;
- корневые G-code и preview.

Контрольные SHA-256:

```text
paths.json aggregate  349071f6d2c4e5df4bc69d962acf960ae4f841abb75aeef2e32e2e82fb1f3550
page.gcode aggregate   867d2a7500d191c1a9dfb32659cd7167feee902a8b255c0ca61694748719a3a8
page previews aggregate 51bda6ace27fb912e919aaf6cc8e52da663a716fd7a0b31e5914797387f4da83
root output.gcode      1d0642fb8e285beacb7e0e8a29e7abe6a2f0c69b9863fcb9eedc4d3c67426816
root preview           50dcdc5e90cd985bd9469cb33e8f541d7c688873fff142887258fde087049d4a
```

`report.json` целиком не сравнивался: он по контракту содержит output path и
runtime timings. Стабильные geometry/render outputs сравнивались напрямую.

## Безопасность G-code

Независимый построчный scanner проверил 203 файла и 2,555,004 активных команд.
Результат: 0 heating (`M104/M109/M140/M190`), 0 homing (`G28`), 0 extrusion
(`E`), 0 `NaN/Infinity`, 0 выходов XY за workspace и 0 неожиданных Z.

## Производительность

Три warm-run: `66.221 s`, `61.858 s`, `61.779 s`; медиана `61.858 s`.
На двух полностью прогретых запусках основные затраты стабильны:

| Stage | Run 2 | Run 3 |
|---|---:|---:|
| handwriting | 27.754 s | 27.912 s |
| simplification | 20.124 s | 20.250 s |
| build_paths | 8.625 s | 8.639 s |

Cold full-font benchmark не повторялся, потому что compiler после блока 7 не
менялся. Последняя условная попытка блока 7 не завершила `font_compile` за
13+ минут и была остановлена; это внесено в техдолг.

## Статус исходных findings

Regression suite из 268 tests покрывает F-001–F-013. Повторная реальная
матрица подтверждает исправление прежнего P0 на PDF math и отсутствие
регрессий в DOCX/PDF layout, centerline, connections, semantic metrics,
pagination, motion и G-code contract. Подробности исправлений остаются в
`docs/UPD_Plotter_11_block_1_report.md` … `_8_report.md`.

## Хранение артефактов

Тяжёлые runtime outputs создавались во временном каталоге и после агрегации не
сохраняются в Git. В `report/` оставлены только этот отчёт, реестр техдолга,
машиночитаемая сводка, manifest, журнал команд, snapshot среды и входной
connection corpus. Это уменьшает шум, не меняя production-код и тесты.

См. [TECH_DEBT.md](TECH_DEBT.md) и [summary.json](summary.json).
