# plotter-processor

Локальная Python-программа для преобразования текста из DOCX или PDF с
текстовым слоем в SVG-превью и G-code для Ender 3 с ручкой, поднимаемой
по оси Z.

Программа заново раскладывает текст на одной странице A4/A5, рендерит его
рукописным TTF, скелетизирует изображение и превращает скелет в траектории.

## Ограничения MVP

Поддерживаются русский текст, цифры, базовая пунктуация, A4/A5 и размеры
`small`, `normal`, `large`. Один запуск обрабатывает одну страницу.

Не поддерживаются OCR, сканированные PDF, таблицы, изображения, формулы,
колонки, исходное форматирование, многостраничный вывод и передача G-code
по USB. Переполненный документ нужно уменьшить или разделить вручную.

## Установка

Требуется Python 3.11 или новее:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m plotter_processor --help
```

Либо:

```bash
make install
make test
make lint
```

## Рукописный шрифт

Положите файл в `assets/handwriting.ttf`. Шрифт не входит в репозиторий и
игнорируется Git. Нужен тонкий связный рукописный TTF с кириллицей. Толстые
линии создают ложные ответвления после скелетизации.

Программа проверяет, что Pillow открывает файл, тестовая строка не пуста и
кириллические глифы присутствуют.

## Настройка принтера

Перед запуском отредактируйте `configs/machine.yaml`:

- `page_origin_mm` — координаты начала листа;
- `invert_x`, `invert_y` — направления осей относительно листа;
- `up_z_mm`, `down_z_mm` — безопасные положения ручки;
- `feedrate_mm_min` — скорости рисования, travel и Z;
- `workspace_mm` — реальные допустимые границы станка.

Значения в репозитории являются примерами. При стандартном workspace
220×220 мм книжный A4 не помещается по Y и будет безопасно отклонён
валидатором. Используйте A5 либо физически корректную конфигурацию станка.

## Калибровка

Начинайте с A5:

```bash
.venv/bin/python -m plotter_processor calibrate \
  --machine-config configs/machine.yaml \
  --page A5 \
  --output build/calibration.gcode
```

Файл сначала обходит контрольные углы с поднятой ручкой, затем рисует
квадрат 20×20 мм. Полная рамка включается только явно:

```bash
.venv/bin/python -m plotter_processor calibrate --page A5 --full-page-frame
```

Рекомендуемый порядок физической проверки: travel с поднятой ручкой,
квадрат 20×20 мм, слово `Привет`, строка с цифрами, небольшой абзац.

## Запуск

```bash
.venv/bin/python -m plotter_processor run examples/input.docx \
  --font assets/handwriting.ttf \
  --page A5 \
  --size normal \
  --layout-config configs/layout.yaml \
  --machine-config configs/machine.yaml \
  --output-dir build
```

Эквивалент через Make:

```bash
make run INPUT=examples/input.docx PAGE=A5 SIZE=normal
```

Отладочные команды:

```bash
python -m plotter_processor extract input.docx --output build/extracted.txt
python -m plotter_processor render build/extracted.txt --font assets/handwriting.ttf
python -m plotter_processor trace build/page.png --page A5
python -m plotter_processor gcode build/paths.json
```

## Результаты

Успешный `run` создаёт:

- `extracted.txt` — извлечённый текст;
- `page.png` — заново свёрстанная страница;
- `skeleton.png` — диагностический однопиксельный скелет;
- `paths.json` — траектории в миллиметрах;
- `preview.svg` — физически масштабированное превью;
- `output.gcode` — команды принтера;
- `report.json` — статус, предупреждения и статистика.

При ошибке создаётся `report.json`, процесс возвращает код 1, а
`output.gcode` удаляется.

## Безопасность

Never run generated G-code before checking pen-up and pen-down Z values,
page origin, axis inversion and workspace limits. Keep G28 disabled until
the mounted pen has been tested safely.

Никогда не запускайте созданный G-code, не проверив значения Z поднятой и
опущенной ручки, начало страницы, инверсию осей и границы рабочей области.
Не включайте G28, пока установленная ручка не испытана безопасным способом.

## Решение проблем

- `PDF does not contain a usable text layer` — PDF является сканом; OCR в
  MVP отсутствует.
- `Text does not fit on one page` — выберите меньший размер или разделите
  документ.
- `Selected font does not appear to be connected` — выберите связный
  рукописный шрифт.
- `outside workspace limits` — исправьте origin, инверсию осей, формат
  страницы или границы workspace.
- `Font does not appear to contain Cyrillic glyphs` — используйте TTF с
  русским алфавитом.
