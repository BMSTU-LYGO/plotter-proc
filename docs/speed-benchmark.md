# Benchmark скорости

Фиксированный тест: `examples/benchmark_50_words.txt`, ровно 50 слов; A5, normal, centerline, optimize travel.

База: commit `c2e08a6538af170d2fbce4a7cce3610da0c65f51`. Шрифт: `assets/1.ttf`.
Принтер: Ender 3; прошивка: TH3D. Тип крепления ручки уточняется перед физическим тестом.

## Запуск

```bash
make benchmark FONT=assets/1.ttf PROFILE=safe
```

Для замера полной конверсии с отдельными cold/warm режимами:

```bash
.venv/bin/python tools/benchmark_conversion.py plotter_pipeline_full_test.docx \
  --font assets/1.ttf --cold-only

.venv/bin/python tools/benchmark_conversion.py plotter_pipeline_full_test.docx \
  --font assets/1.ttf --warm-only --warm-runs 3 --connections safe
```

`--cold-only` использует изолированный временный font cache.
`--warm-only` использует канонический cache и не тратит cold compile
перед замером. Во время каждого прогона печатаются stage progress и
длительности.

## Результаты

| Метрика | safe | balanced | fast |
|---|---:|---:|---:|
| Фактическое время, с | нужен замер | нужен замер | нужен замер |
| Идеальное время, с | 512,70 | 215,00 | 142,23 |
| Draw / travel / Z / dwell, с | 153,77 / 22,91 / 304,32 / 31,70 | 102,52 / 15,27 / 84,53 / 12,68 | 76,89 / 11,45 / 47,55 / 6,34 |
| Strokes / pen lifts / points | 317 / 317 / 5516 | 317 / 317 / 5516 | 317 / 317 / 5516 |
| G-code commands / short ratio | 6472 / 4,75% | 6472 / 4,75% | 6472 / 4,75% |
| Дефекты | нужен осмотр | нужен осмотр | нужен осмотр |

Фактическое время, касание бумаги, потерю шагов и качество начала линий нужно
заполнить после прогона на реальном станке.

## Программное сравнение

До bounded simplification: 354328 точек. После: 5516 (−98,44%).
Максимальное измеренное отклонение 0,059664 мм при допуске 0,06 мм.
Штрихи и подъёмы не изменились. Balanced сокращает идеальную оценку на
297,40 с относительно safe; геометрия профилей идентична.

Оценка анализатора G-code чуть выше PathDocument, потому что он консервативно
считает первое XY-движение от machine origin и первичный подъём Z; расхождение
объяснено, а число XY/Z/dwell-команд совпадает.
