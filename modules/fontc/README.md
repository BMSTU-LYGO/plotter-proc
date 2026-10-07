# Компилятор однолинейного шрифта

`fontc` превращает файл шрифта в компактный двоичный файл `.pfc`. Документный конвейер читает готовый файл при запуске; компиляция шрифта ему не нужна.

Сборка и запуск из корня проекта:

```bash
cmake -S . -B build -DBUILD_TESTING=OFF
cmake --build build -j
build/modules/fontc/fontc assets/1.ttf --chars-file assets/font-cache-corpus.txt --output build/font.pfc
```

Шрифт передаётся пользователем. Подробности формата и алгоритма — в [описании устройства](docs/architecture.md).

Недостающие символы можно физически добавить из готовых специальных кешей:

```bash
build/modules/fontc/fontc merge user.pfc --special-pfc special-common.pfc --special-pfc special-extra.pfc --output merged.pfc
```

При подготовке TTF те же `--special-pfc` добавляют символы перед записью итогового кеша.
Приоритет: пользовательский символ, затем первый специальный кеш, затем остальные в порядке аргументов.
Координаты и advance специальных символов копируются точно, без масштабирования;
метрики итогового кеша остаются пользовательскими. Для согласованного физического размера
специальные кеши следует заранее готовить в той же системе font units.
`--chars-file` в режиме `merge` необязателен и задаёт корпус для подсчёта отсутствующих codepoint.
Команда выводит `user_glyphs`, `special_glyphs_added`, `duplicate_special_glyphs_skipped`,
`missing_codepoints`; существующий файл заменяется только с `--force`.
