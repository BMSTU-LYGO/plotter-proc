# plotter-processor

`plotter-processor` преобразует текст из TXT, DOCX или PDF с текстовым слоем и пользовательский TTF в плавные траектории плоттера и безопасный G-code для Ender 3.

```text
TXT / DOCX / PDF + TTF
          ↓
Unicode NFC → layout в миллиметрах → контуры fontTools
          ↓
font-preview.svg + plotter-preview.svg + paths.json + output.gcode
```

В основном pipeline нет рендеринга PNG, бинаризации, skeletonize или обхода пиксельного графа.

> Обычный TTF содержит контуры букв. Плоттер проходит по внешним и внутренним контурам. Это не восстановление центральной линии человеческого штриха.

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
  --page A5 \
  --size normal \
  --layout-config configs/layout.yaml \
  --machine-config configs/machine.yaml \
  --output-dir build
```

Поддерживаются страницы `A4`/`A5` и размеры `small`/`normal`/`large`. Флаг `--no-optimize-travel` отключает перестановку контуров внутри глифа.

Полезные команды:

```bash
.venv/bin/python -m plotter_processor extract input.docx --output build/extracted.txt
.venv/bin/python -m plotter_processor font-info assets/handwriting.ttf
.venv/bin/python -m plotter_processor gcode build/paths.json --output build/output.gcode
```

## Результаты

- `extracted.txt` — извлечённый нормализованный текст;
- `font-preview.svg` — точные заполненные кривые TTF;
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
