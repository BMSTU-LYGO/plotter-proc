# Компилятор однолинейного шрифта

`fontc` превращает файл шрифта в компактный двоичный файл `.pfc`. Документный конвейер читает готовый файл при запуске; компиляция шрифта ему не нужна.

Сборка и запуск из корня проекта:

```bash
cmake -S . -B build -DBUILD_TESTING=OFF
cmake --build build -j
build/modules/fontc/fontc assets/1.ttf --chars-file assets/font-cache-corpus.txt --output build/font.pfc
```

Шрифт передаётся пользователем. Подробности формата и алгоритма — в [описании устройства](docs/architecture.md).
