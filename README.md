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

Поддерживаются страницы `A4`/`A5` и размеры `small`/`normal`/`large`. Флаг `--no-optimize-travel` отключает перестановку контуров внутри глифа.

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

При первом запуске уникальные глифы компилируются в `build/font-cache`.
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

## Результаты

- `extracted.txt` — извлечённый нормализованный текст;
- `font-preview.svg` — точные заполненные кривые TTF;
- `centerline-font-preview.svg` — таблица центральных линий уникальных глифов;
- `plotter-preview.svg` — реальные линейные движения ручки;
- `paths.json` — версионированные траектории в системе page-mm-top-left;
- `output.gcode` — движения XY/Z без нагрева, extrusion и G28 по умолчанию;
- `report.json` — статус, предупреждения, статистика и пути артефактов.

Один запуск создаёт одну страницу. OCR, восстановление порядка рукописных штрихов и полный OpenType shaping/GPOS не поддерживаются. Если в TTF отсутствует требуемый глиф или текст не помещается, команда завершается с кодом 1, сохраняет error-report и не оставляет `output.gcode`.

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

Тесты работают без сети, принтера и системных TTF.
