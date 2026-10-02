# Конвейер документов для плоттера

Самодостаточный проект на C++20: `fontc` готовит `.pfc`, а `plotter-doc` строит G-code.
Пользователь передаёт собственный шрифт TrueType или OpenType через `--font`; шрифты не хранятся в репозитории.


## Зависимости

Нужны CMake 3.20+, компилятор C++20, FreeType, Zlib и Threads.

## Сборка

```bash
cmake -S . -B build -DBUILD_TESTING=OFF
cmake --build build -j
```

Для тестов включите `BUILD_TESTING`; тесты документа контролирует `PLOTTER_DOC_BUILD_TESTS`.

```bash
cmake -S . -B build -DBUILD_TESTING=ON -DPLOTTER_DOC_BUILD_TESTS=ON
cmake --build build -j
ctest --test-dir build --output-on-failure
```

## Запуск

```bash
build/modules/fontc/fontc <path/to/font.ttf> \
  --chars-file assets/font-cache-corpus.txt --output build/font.pfc
build/modules/document/plotter-doc \
  --input examples/benchmark_50_words.txt --output build/result \
  --font build/font.pfc --font-mode centerline
```

Для обводки букв передайте `--font <path/to/font.ttf> --font-mode outline`.

## Страницы и настройки плоттера

Настройки листа находятся в `configs/layout.yaml`, а рабочая зона и перо — в `configs/machine.yaml`.

```bash
build/modules/document/plotter-doc --input examples/benchmark_50_words.txt \
  --output build/a4-document --font build/font.pfc --font-mode centerline --page A4 \
  --layout-config configs/layout.yaml --machine-config modules/document/fixtures/machine-a4.yaml \
  --page-numbers --optimize --simplify
```

Текст разбивается на страницы. Результат включает `output.gcode`, `job.json`, `report.json` и `pages/page-XXX/paths.json`.
SVG-предпросмотр первой страницы: `pages/page-001/plotter-preview.svg`; откройте его до отправки G-code на плоттер.
Полный список параметров: `build/modules/document/plotter-doc --help`.
