# plotter-processor

`plotter-processor` преобразует текст из TXT, DOCX или PDF с текстовым слоем и пользовательский TTF в плавные траектории плоттера и безопасный G-code для Ender 3.

```text
TXT / DOCX / PDF + TTF
          ↓
Unicode NFC → layout в миллиметрах → outline или centerline
          ↓
font-preview.svg + plotter-preview.svg + paths.json + output.gcode
```

Режим `outline` точно повторяет обе границы заполненного TTF. Режим
`centerline` отдельно рендерит каждый уникальный глиф при 2048 px/em,
строит medial axis и кеширует сглаженные штрихи в font units.

## Установка

Требуется Python 3.11 или новее.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Поместите шрифт, например `handwriting.ttf`, в `assets/`. Получить TTF из фотографии шаблона почерка можно внешним инструментом `draw-your-font`; Node.js и сам инструмент не входят в этот проект.

## Запуск

```bash
.venv/bin/python -m plotter_processor run examples/input.txt \
  --font assets/handwriting.ttf \
  --font-mode outline \
  --page A5 \
  --size normal \
  --layout-config configs/layout.yaml \
  --machine-config configs/machine.yaml \
  --output-dir build
```

Доступны форматы страницы `A4`/`A5` и размеры `small`/`normal`/`large`.
Формат вывода всегда проверяется вместе с `--machine-config`: штатный
Ender 3 profile `configs/machine.yaml` с workspace 220×220 mm и origin 10×10 mm
физически вмещает portrait A5, но не portrait A4. Для A4 нужен
реально совместимый machine profile; pipeline откажется от такой
комбинации до чтения документа и компиляции шрифта. Флаг
`--no-optimize-travel` отключает перестановку контуров внутри глифа.

## Формулы LaTeX (MVP)

В TXT, обычном тексте DOCX и `composition` поддерживаются inline-формулы
`$...$`, `\(...\)` и блочные формулы `$$...$$`, `\[...\]`. MathText
преобразует степени и индексы, дроби, корни, греческие буквы, основные
операторы, суммы, интегралы и скобки в high-resolution ink mask, после чего
общий raster-to-centerline pipeline строит центральные линии. Shell и
системный `latex` не запускаются. Запись `\$` означает обычный знак доллара.

```bash
.venv/bin/python -m plotter_processor run examples/formulas.txt \
  --font assets/1.ttf --font-mode centerline \
  --latex mathtext --latex-stroke-mode centerline \
  --strict-latex-quality --latex-debug --output-dir build/formulas
```

Режим `--latex auto` включён по умолчанию, `--latex off` оставляет разделители
обычным текстом и добавляет предупреждение в отчёт. Default stroke mode —
`centerline`; прежний результат доступен через `--latex-stroke-mode outline`.
`--latex-debug` сохраняет mask, skeleton, graph, centerline и overlay каждой
формулы. `--strict-latex-quality` останавливает job до G-code при провале
quality gate.

Базовое подмножество Word OMML (символы, индексы, степени, дроби, корни,
скобки и n-ary operators) становится отдельным математическим элементом. Для
PDF доступен `--pdf-math auto|visual|off`: detector выделяет визуальный bbox
формулы, рендерит только этот clip и строит centerline, не печатая поглощённые
text/vector primitives второй раз. `--math-debug` сохраняет PDF clip и список
поглощённых элементов.

Это не полный TeX: не поддерживаются LaTeX-документы, `\documentclass`,
packages, TikZ, пользовательские макросы, bibliography, произвольные file
includes, внешний `latex` и shell execution. Поддерживается не весь OMML;
неизвестные узлы отмечаются конкретным warning. PDF-режим является visual
centerline reconstruction: исходная строка `.tex` не восстанавливается,
low-confidence регионы остаются обычным текстом/вектором.

## Размещение изображений

Для DOCX и PDF доступны три режима `--document-layout reflow|hybrid|preserve`.
`reflow` сохраняет прежний последовательный поток, `hybrid` удерживает сторону
anchored-рисунка и обтекает его текстом, а `preserve` отображает исходные bbox
на целевую страницу единым contain-scale. Старый `--pdf-layout reflow|preserve`
остаётся alias; конфликт двух флагов завершается понятной ошибкой.

`--layout-debug` создаёт `layout-debug/source-layout.svg`,
`target-layout.svg`, `placement-overlay.svg` и `placement.json`. В отчёте раздел
`document_layout` содержит displacement, scale, wrapping, overlap и overflow.

## Семантические линии, стрелки и таблицы

DOCX сохраняет single/double/words-only underline, VML-стрелки и структуру
простых таблиц, включая horizontal/vertical merged cells и повтор header-row.
Для PDF консервативно классифицируются line-based tables, стрелки,
подчёркивания и обычные линии — один primitive может принадлежать только одному
semantic object. Табличные shared borders строятся один раз.

Флаг `--semantic-debug` создаёт `semantic-debug/classification.json` и SVG для
исходных primitives, таблиц, стрелок и подчёркиваний. Счётчики находятся в
разделе `semantic_objects` файла `report.json`.

## Профили скорости

`safe` повторяет прежние Z и скорости и остаётся профилем по умолчанию.
`balanced` и `fast` — начальные кандидаты: их нужно проверить с конкретной
ручкой и держателем. На большом числе штрихов высота Z и пауза после опускания
часто экономят больше времени, чем одно увеличение draw feedrate.

```bash
make benchmark FONT=assets/1.ttf PROFILE=safe
make benchmark FONT=assets/1.ttf PROFILE=balanced
make benchmark FONT=assets/1.ttf PROFILE=fast
```

Для обычного запуска добавьте `--motion-profile safe|balanced|fast`. Разбивка
draw/travel/Z/dwell находится в разделе `motion` файла `report.json`. Вернуться
к безопасным параметрам можно с `--motion-profile safe`.

Перед `balanced` или `fast` создайте калибровочные файлы:

```bash
.venv/bin/python -m plotter_processor calibrate-pen --motion-profile safe
.venv/bin/python -m plotter_processor calibrate-speed --motion-profile safe
```

Они не содержат нагрева, extrusion или `G28`; после теста перо поднято. Карта
теста и таблица осмотра находятся в `docs/speed-calibration-results.md`.

Сравнение двух готовых заданий:

```bash
.venv/bin/python -m plotter_processor compare-jobs \
  build/benchmark-safe build/benchmark-balanced \
  --output build/benchmark-comparison.json
```

## Однолинейный режим

`draw-your-font` остаётся отдельным неизменённым инструментом. Сначала
создайте им обычный TTF:

```bash
npx draw-your-font make page-1.jpg page-2.jpg --name "My Hand"
```

Затем передайте только полученный TTF:

```bash
.venv/bin/python -m plotter_processor run examples/input.txt \
  --font assets/MyHand.ttf \
  --font-mode centerline \
  --page A5 \
  --size normal \
  --output-dir build/centerline-job
```

При первом запуске уникальные глифы компилируются в
`1-font-cache`. Этот постоянный кеш отделён от результатов в
`build`, поэтому очистка старых заданий его не удаляет.
Последующие запуски используют частичный кеш. Отдельная предварительная
компиляция:

```bash
.venv/bin/python -m plotter_processor compile-centerline-font \
  assets/MyHand.ttf \
  --text-file examples/input.txt \
  --output build/fonts/MyHand.centerline.json \
  --preview build/fonts/MyHand.centerline.svg \
  --debug-dir build/fonts/MyHand-debug
```

Полезные параметры:

- `--centerline-cache PATH` — использовать конкретный JSON-кеш;
- `--force-centerline-rebuild` — пересобрать кеш;
- `--strict-centerline-quality` — остановиться на слабом глифе;
- `--font-mode outline` — сохранить прежнее поведение с двойной обводкой.

Centerline — автоматическое приближение. Сложные пересечения могут требовать
настройки `configs/layout.yaml`; качество результата ограничено качеством TTF.
Перед печатью обязательно проверьте `font-preview.svg`,
`centerline-font-preview.svg`, `plotter-preview.svg` и предупреждения отчёта.

### Постоянный centerline cache

Canonical cache хранится в `1-font-cache`, отдельно от job artifacts
в `build/`. Namespace имеет вид
`<font-sha256>/<centerline-config-fingerprint>/centerlines.json`; рядом атомарно
записывается `metadata.json`. В identity входят содержимое TTF, версия алгоритма,
render/skeleton/routing/stroke/quality settings, glyph/font overrides и содержимое
glyph patch. Формат страницы, margins, pagination, machine и G-code settings cache
не инвалидируют.

```bash
make clean                         # удаляет только build
make cache-clean                   # явно удаляет весь reusable cache
make font-cache-rebuild FONT=assets/1.ttf
make font-cache-status FONT=assets/1.ttf
```

`font-cache-rebuild` компилирует воспроизводимый corpus из
`assets/font-cache-corpus.txt`. Другой corpus можно передать через
`FONT_CACHE_CORPUS=assets/custom-corpus.txt`. Rebuild одного TTF обновляет только
его namespace и не удаляет кеши других шрифтов.

При обычном `run --force-centerline-rebuild` принудительно пересобираются только
глифы текущего документа. `compile-centerline-font --force` пересобирает весь
переданный `--text-file`/`--chars`, сохраняя прочие валидные entries того же
namespace. Без `--force` компилируются только misses. Изменение алгоритма или
релевантного fingerprint автоматически выбирает новый namespace, поэтому ручная
очистка для корректности не требуется.

Если менялся только layout, достаточно `make test`. После изменений skeleton,
routing, threshold, smoothing, cache schema или overrides выполните
`make font-cache-rebuild FONT=assets/1.ttf`.

Quality v3 сравнивает `skeletonize` и `medial_axis` по геометрии и
топологии, нормализует junction-кластеры и удаляет spur относительно
локальной толщины. Отдельный глиф можно настроить через
`centerline.glyph_overrides`. Полный отчёт и regression-корпус описаны в
`docs/centerline-quality-v3.md`.

`--connections off|safe|aggressive` управляет рукописными переходами между
буквами одного слова. `safe` использует entry/exit anchors, проверяет distance,
vertical offset, tangent, backtracking, corridor и collisions; сомнительная
пара остаётся с подъёмом пера. `aggressive` расширяет геометрические допуски,
но не отключает punctuation, backtracking и collision validation. Режимы
различаются только на парах, пересекающих расширенные distance/angle/vertical
пороги; на конкретном тексте их output может совпадать. Точки `ё`, дуга `й` и
другая диакритика
остаются отдельными strokes. `--join-writing` сохранён как compatibility-флаг
для safe-поведения.

Canonical-настройки находятся только в секции `connections` файла
`configs/layout.yaml`. Флаг `--connection-debug` создаёт
`connection-debug.svg` и `connection-debug.json`; в `report.json` доступны
`pairs_total`, `accepted`, причины отказов, `snapped_existing_contact` и
`connector_length_mm`.

### Один непрерывный маршрут на компонент

Centerline cache version 2 строит topology-aware граф с crossing number и
автоматически сравнивает `skeletonize` с `medial_axis`. Для каждого связного
компонента строится Euler path/circuit. Если граф имеет больше двух нечётных
вершин, минимально повторяются только существующие skeleton-рёбра — новые
соединительные линии через пустое место не добавляются.

Обычно связная буква (`а`, `ж`, `ф`, `щ`) становится одним движением. Отдельные
точки и знаки остаются отдельными движениями: `ё` обычно имеет три маршрута,
`й` — два, `!` — два. В `report.json` доступны `pen_lifts_saved`,
`retraced_length_mm`, `retrace_ratio`, fallback и худшие глифы. Если повтор
слишком велик, используется minimum-trails fallback.

Основные параметры находятся в `centerline.skeleton` и `centerline.routing`
файла `configs/layout.yaml`. Перед физическим запуском проверьте routed preview
и debug проблемных глифов; повторный проход по линии может визуально утолщать
чернила.

Полезные команды:

```bash
.venv/bin/python -m plotter_processor extract input.docx --output build/extracted.txt
.venv/bin/python -m plotter_processor font-info assets/handwriting.ttf
.venv/bin/python -m plotter_processor gcode build/paths.json --output build/output.gcode
```

Команда `gcode` гарантирует functional equivalence с page-level G-code полного
`run`: последовательность всех non-comment motion-команд одинакова для одного
`paths.json` и machine config. Byte identity не является контрактом, потому что
полный pipeline добавляет job-local комментарии о странице, motion profile и
расчётном времени, которых нет в `paths.json`. Поэтому регенерированный файл
следует сравнивать после исключения строк-комментариев (`; ...`).

`extract` выдаёт стабильную текстовую проекцию в source reading order:
абзацы, logical cells таблиц по строкам/столбцам и LaTeX-like representation
доступных OMML expressions. Merged cells не дублируются, а repeated
header выводится один раз как source content.

## Результаты

- `extracted.txt` — извлечённый нормализованный текст;
- `font-preview.svg` — точные заполненные кривые TTF;
- `centerline-font-preview.svg` — таблица центральных линий уникальных глифов;
- `plotter-preview.svg` — реальные линейные движения ручки;
- `paths.json` — версионированные траектории в системе page-mm-top-left;
- `output.gcode` — движения XY/Z без нагрева, extrusion и G28 по умолчанию;
- `report.json` — статус, предупреждения, статистика и пути артефактов.

Один job может содержать несколько страниц с page-level `paths.json`, preview
и G-code, а также общие `job.json`, `plotter-preview.svg` и `output.gcode`.
OCR и восстановление порядка рукописных штрихов не поддерживаются. Если в TTF
отсутствует требуемый глиф или geometry не проходит safety validation, команда
завершается с кодом 1, сохраняет error-report и не оставляет G-code.

## Безопасность

Перед рисованием:

1. Проверьте `up_z_mm`, `down_z_mm`, `page_origin_mm`, `invert_x` и `invert_y` в `configs/machine.yaml`.
2. Выполните dry-run с поднятой ручкой.
3. Не включайте `G28`, пока не проверена механика держателя.
4. Начните с A5 и маленького калибровочного квадрата.
5. Просмотрите оба SVG и `report.json`, затем проверьте G-code.

Генератор проверяет machine workspace и не выводит команды нагрева `M104/M109/M140/M190` или extrusion `E`.

## Разработка

```bash
make install
make test
make lint
make demo FONT=assets/handwriting.ttf
```

Обычный `pytest` содержит только component tests. Полную конвертацию перед
релизом запускайте отдельно:

```bash
make smoke
```

Cold/warm benchmark конвертации также вынесен из pytest:

```bash
.venv/bin/python tools/benchmark_conversion.py \
  tests/fixtures/layout/mixed_layout_demo.docx \
  --font assets/1.ttf --runs 3 --output build/benchmark-conversion.json
```

В JSON сохраняются отдельный cold run, warm runs, median, stage timings и
cache hits/misses. Тесты работают без сети, принтера и системных TTF.

## Абзацное форматирование

DOCX-абзацы сохраняют выравнивание `left`, `center`, `right` и `justify`,
красную строку, левые/правые отступы и пользовательские tab stops. Стили
Title и Heading переносятся как семантические роли, а не как пробелы.

## Centerline cache

Постоянный cache глифов лежит в `1-font-cache` в корне проекта.

```bash
make font-cache-rebuild FONT=assets/1.ttf
make font-cache-status FONT=assets/1.ttf
make cache-clean
```

`make clean` удаляет только build-артефакты и не удаляет `1-font-cache`.

## A4/A5 document scaling

При изменении формата листа единый `PageTransform` равномерно сопоставляет source
content box с target content box. Рисунки сохраняют пропорции, поворот и
left/center/right affinity. Таблицы сохраняют пропорции колонок, автоматически
увеличивают строки и делятся между строками при переносе на следующую страницу.

- `reflow` — переверстать текст и блочные объекты.
- `hybrid` — reflow текста с сохранением логической позиции floating-объектов.
- `preserve` — перенести source geometry через `PageTransform`.
- `auto` — выбрать безопасный режим по типу входного документа.
