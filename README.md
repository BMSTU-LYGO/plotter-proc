# Plotter Processor

Plotter Processor преобразует TXT, DOCX, PDF и SVG-документы в векторные
траектории, preview и безопасный G-code для плоттера. Конвейер поддерживает
обычный и однолинейный текст, изображения, таблицы, диаграммы, LaTeX/OMML и
визуальные формулы из PDF.

Основной запуск выполняется командой:

```bash
plotter-processor run <input> --font <font.ttf> [флаги]
```

`<input>` — исходный документ. Обязательный `--font` задаёт TTF-шрифт для
текста, а `--output-dir` — каталог результата. Булевы флаги применяются без
значения. Для первого запуска обычно достаточно указать входной файл, шрифт и
каталог сборки; параметры ниже позволяют отдельно управлять качеством,
разметкой, математикой, изображениями, диагностикой и G-code.

## Готовые профили Makefile

Три базовых сценария хранят все профильные флаги в
`configs/run_conf.yaml`. В Makefile остаются только короткие команды; входной
файл, шрифт и корневой каталог сборки можно переопределить переменными `INPUT`,
`FONT` и `BUILD`:

```bash
make run-fast INPUT=document.docx FONT=assets/1.ttf
make run-balanced INPUT=document.docx FONT=assets/1.ttf
make run-quality INPUT=document.docx FONT=assets/1.ttf
```

- `run-fast` — максимально быстрая печать с motion profile `fast`,
  `aggressive`-соединениями, объединением букв и минимальными артефактами.
- `run-balanced` — повседневная печать с безопасными соединениями и балансом
  скорости/качества.
- `run-quality` — строгая обработка формул, таблиц и диаграмм с audit-артефактами.

Результаты сохраняются соответственно в `build/super-fast`,
`build/balanced` и `build/quality`. Менять состав профилей следует в
`configs/run_conf.yaml`, а не в рецептах Makefile.

## Флаги команды `run`

### --help

- без значения

### --font

- `<путь к TTF>`

### --page

- `A4`
- `A5`

### --size

- `small`
- `normal`
- `large`

### --layout-config

- `<путь к YAML-конфигурации разметки>`

### --machine-config

- `<путь к YAML-конфигурации плоттера>`

### --output-dir

- `<путь к каталогу>`

### --preset

- `fast`
- `quality`
- `debug`

### --no-optimize-travel

- без значения

### --font-mode

- `outline`
- `centerline`

### --centerline-cache

- `<путь к JSON>`

### --stage-cache

- `<путь к каталогу кэша этапов>`

### --force-centerline-rebuild

- без значения

### --strict-centerline-quality

- без значения

### --motion-profile

- `safe`
- `balanced`
- `fast`

### --join-writing

- без значения

### --layout-engine

- `legacy`
- `harfbuzz`

### --connections

- `off`
- `safe`
- `aggressive`

### --connection-debug

- без значения

### --images

- `auto`
- `outline`
- `centerline`
- `hatching`
- `off`

### --image-debug

- без значения

### --pdf-layout

- `reflow`
- `preserve`

### --document-layout

- `reflow`
- `hybrid`
- `preserve`

### --layout-debug

- без значения

### --semantic-debug

- без значения

### --paginate

- без значения

### --no-paginate

- без значения

### --page-numbers

- без значения

### --no-page-numbers

- без значения

### --page-pause-seconds

- `<неотрицательное число>`

### --park-corner

- `top_left`
- `top_right`
- `bottom_left`
- `bottom_right`

### --latex

- `auto`
- `mathtext`
- `off`

### --latex-debug

- без значения

### --latex-stroke-mode

- `centerline`
- `outline`

### --strict-latex-quality

- без значения

### --pdf-math

- `auto`
- `visual`
- `off`

### --math-debug

- без значения

### --workers

- `auto`
- `<положительное целое число>`

### --centerline-workers

- `auto`
- `<положительное целое число>`

### --artifacts

- `minimal`
- `normal`
- `debug`
- `audit`
