# Centerline quality v3

Ветка: `upd/plotter-central-line-improove`. База: `97274fe`.
Регрессионный корпус: `examples/centerline_glyph_corpus.txt`.
Шрифт: `assets/1.ttf`, 2048 px/em.

## Команда

```bash
.venv/bin/python -m plotter_processor compile-centerline-font assets/1.ttf \
  --text-file examples/centerline_glyph_corpus.txt \
  --output build/block2-corpus/font.centerline.json \
  --preview build/block2-corpus/font.centerline.svg \
  --debug-dir build/block2-corpus/debug --force
```

## Метрики

Для `skeletonize` и `medial_axis` отдельно сохраняются coverage,
reconstruction extra, balance расстояния до границы, endpoints,
junctions, micro loops, short edges, components и odd vertices. Selector
выбирает кандидата по взвешенной совокупности метрик.

Порог coverage откалиброван на 0,70: прежние 0,82 ложно
отправляли на review тонкие, но топологически целые глифы. Новый порог
сохраняет review для малых знаков со слабой реконструкцией. Строгий
режим останавливает генерацию на таком глифе и сохраняет debug.

## Per-glyph overrides

```yaml
centerline:
  glyph_overrides:
    "ж":
      skeleton_method: medial_axis
      simplify_tolerance_px: 0.7
      min_branch_width_factor: 1.2
      max_retrace_ratio: 0.55
```

Override влияет только на указанный Unicode-символ и входит в ключ кэша.

## Результат на `assets/1.ttf`

| Метрика | Значение |
|---|---:|
| Уникальных глифов | 87 |
| Auto passed | 83 (95,40%) |
| Needs review | 4 (`.`, `:`, `;`, `?`) |
| Failed / lost components | 0 |
| Минимальный inside-mask ratio | 1,0 |
| `medial_axis` / `skeletonize` | 24 / 63 |
| Удалено spur-пикселей | 8113 |

Целевой gate 95% выполнен. Все centerline-пиксели остались внутри
маски; потерянных связных компонентов нет. Четыре малых знака оставлены
для ручного осмотра, а не искусственно подняты агрессивным repair.
