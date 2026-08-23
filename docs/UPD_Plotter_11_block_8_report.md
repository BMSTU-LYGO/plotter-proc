# UPD_Plotter_11 — отчёт по блоку 8

## Что было сломано

Исходный audit имел формально зелёные lint/test/smoke, но три диагностически
неуспешных integration job-а и критическое падение обоих PDF math routes.
Поэтому прежний gate не подтверждал работоспособность всей исправленной
матрицы и безопасность итоговых G-code artifacts.

Блоку 8 требовалось независимо перепроверить текущее состояние после всех
bugfix/refactor блоков, без новых production-изменений.

## Как воспроизводилось

Baseline аудита:

```text
lint: passed
test: 239 passed
smoke: passed
audit jobs: 7 successful, 3 diagnostically failed
```

Финальный gate запускался на текущем общем working tree после завершения
интеграционной матрицы блока 7. Safety scan не использовал внутренний validator
pipeline и анализировал уже записанные `.gcode` файлы самостоятельно.

## Root cause

Это контрольный блок, а не отдельный bugfix. Исходная проблема заключалась в
том, что unit/smoke gate сам по себе не покрывал реальные PDF/DOCX artifacts и
не гарантировал отсутствие опасных machine-команд во всех сформированных
файлах.

Предыдущие блоки устранили конкретные root causes. Блок 8 подтверждает, что их
совместное состояние не внесло регрессий.

## Какие файлы изменены

- `docs/UPD_Plotter_11_block_8_report.md`

Production-код, configs и tests в блоке 8 не изменялись.

## Что именно изменено

- Повторно выполнен полный lint.
- Повторно выполнены все regression tests.
- Повторно выполнен mixed-layout smoke pipeline.
- Независимым scanner проверены все `.gcode` artifacts во всём `build/`.
- Повторно проверен canonical font cache.
- Проверен `git diff --check`.

Safety scanner:

1. удалял комментарии после `;`;
2. анализировал только активные команды;
3. отдельно искал heating commands, homing, extrusion parameter и non-finite
   coordinate/feed values;
4. завершался с non-zero status при любом нарушении или отсутствии файлов.

## Какие тесты добавлены

Новые tests в контрольном блоке не добавлялись. Полный набор из 268 tests уже
содержит regression coverage findings F-001–F-013 из предыдущих блоков.

## Какие команды прогнаны

```bash
make lint
make test
make smoke

find build -name '*.gcode' -print0 | xargs -0 \
  .venv/bin/python -c '<independent safety scanner>'

make font-cache-status FONT=assets/1.ttf
git diff --check
```

## Результат до / после

| Проверка | Audit baseline | Final block 8 |
|---|---:|---:|
| lint | passed | passed |
| tests | 239 passed | 268 passed |
| smoke | passed | passed |
| diagnostically successful audit scenarios | 7 / 10 | вся block 7 matrix успешна |
| PDF preserve/reflow | error / error | ok / ok |
| G-code files independently scanned | ограниченный audit set | 473 |
| Active G-code commands scanned | не зафиксировано | 5,943,991 |
| Safety violations | 0 в доступных outputs | 0 |

Результат independent scan:

```text
files=473
active_commands=5943991
heating M104/M109/M140/M190: 0
homing G28: 0
extrusion E: 0
NaN/Infinity: 0
total violations: 0
```

Canonical font cache:

```text
algorithm version: 7
glyphs: 169
size: 18,393,613 bytes
exists: true
valid: true
```

Итог:

```text
lint: passed
test: 268 passed
smoke: passed
G-code safety: passed
font cache: valid
git diff --check: passed
```

## Оставшиеся ограничения

- Cold compilation полного working glyph set остаётся непрактично долгой:
  попытка блока 7 не завершила `font_compile` за 13+ минут.
- PDF preserve намеренно сохраняет исходные visual overlaps; PDF reflow
  завершает тот же документ без remaining overlaps.
- PDF math detection всё ещё сообщает low-confidence candidates и rasterizes
  complex drawings; это контролируемые предупреждения, а не pipeline failure.
- Safe/aggressive совпадают на исходном audit connection corpus; behavioral
  boundary подтверждён отдельной regression fixture.
- Этот файл является отчётом только блока 8. Отдельный сводный
  `UPD_Plotter_11 Final Report` из следующего раздела плана здесь не создавался.
