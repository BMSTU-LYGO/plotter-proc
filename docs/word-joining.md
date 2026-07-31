# Связное письмо

Функция включается явно флагом `--join-writing` и работает только
в centerline-режиме. Между словами и строками перо всегда поднимается.
Пунктуация и вторичные компоненты `ё`, `й`, `!`, `?`, `:` не используются как
соединительные линии.

```bash
.venv/bin/python -m plotter_processor run examples/benchmark_50_words.txt \
  --font assets/1.ttf --font-mode centerline --page A5 --size normal \
  --motion-profile fast --join-writing --output-dir build/block3-final-fast
```

Алгоритм выбирает направления основных штрихов через dynamic programming
и добавляет cubic Bézier только при gap до 3 мм и угле до 105°. Debug SVG
показывает штрихи, entry/exit и travel разными слоями.

## Benchmark 50 слов

- candidates: 256;
- joins: 79 (30,86%);
- lifts: 317 → 238 (−24,92% от всех подъёмов);
- connector length: 89,70 мм;
- average gap: 1,04 мм;
- ideal fast time: 142,18 → 130,81 с.

Вариативность в `handwriting.variation` отключена по умолчанию. Одинаковый
seed даёт одинаковую геометрию. Перед печатью обязательно проверьте
`handwriting-debug.svg`: естественность connector-линий требует визуальной
оценки на конкретном шрифте.
