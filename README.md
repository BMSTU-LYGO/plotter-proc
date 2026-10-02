# Конвейеры плоттера

Новые модули находятся в `refactor`. Прежний конвейер на Питоне сохранён; [его подробное описание](docs/старый-конвейер.md).

## Сборка

Нужны компилятор С++20, система сборки и библиотеки шрифтов и сжатия.

```bash
cmake -S refactor/extraction_module/cpp/fontc -B build/fontc
cmake --build build/fontc -j
cmake -S refactor/doc-module/cpp -B build/doc -DPLOTTER_DOC_BUILD_TESTS=OFF
cmake --build build/doc -j
```

## Запуск

Обычный шрифт — обводка букв:

```bash
build/doc/plotter-doc --input examples/benchmark_50_words.txt --output build/result --font assets/1.ttf --font-mode outline
```

Однолинейный шрифт сначала компилируется, затем передаётся конвейеру:

```bash
build/fontc/fontc assets/1.ttf --chars-file assets/font-cache-corpus.txt --output build/font.pfc
build/doc/plotter-doc --input examples/benchmark_50_words.txt --output build/result --font build/font.pfc --font-mode centerline
```

Отдельная команда разбирает документ и выводит его промежуточное представление:

```bash
build/doc/plotter-doc-import refactor/doc-module/fixtures/basic.md > build/document.json
```

## Возможности

- Компилятор шрифтов готовит файл однолинейных букв для повторного использования.
- Документный конвейер читает `.txt`, `.md`, `.docx` и `.svg`; строит разметку страниц и траектории пера.
- Поддерживаются обводка букв, однолинейное письмо, переносы, номера страниц, простые таблицы и формулы, настройки листа и плоттера, кэширование этапов.
- Результат: управляющие команды плоттера, отчёт и промежуточные файлы в каталоге, указанном через `--output`.
- Новый конвейер пока экспериментальный: точное совпадение геометрии и происхождения штрихов с прежним конвейером ещё проверяется. Картинки пока исключены из этой работы.
