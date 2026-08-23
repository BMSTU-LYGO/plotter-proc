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

Порог coverage остаётся 0,70. Final quality evaluation реконструирует
штрих по local radius map skeleton, а не одним global median radius. Это
корректно оценивает штрихи переменной толщины и tiny punctuation,
не ослабляя quality gate. Candidate selection сохраняет свою отдельную
median-radius scoring metric, что явно отмечено в debug JSON.

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
| Auto passed | 87 (100%) |
| Needs review | 0 |
| Failed / lost components | 0 |
| Минимальный inside-mask ratio | 1,0 |
| Минимальный local-radius coverage | 0,918286 |
| `medial_axis` / `skeletonize` | 72 / 15 |
| Удалено spur-пикселей | 487 |

Целевой gate выполнен для всех 87 regression glyphs. Все centerline-пиксели
остались внутри маски; потерянных связных компонентов нет. Canonical
corpus из 169 glyphs также имеет 169 auto-pass, 0 needs-review и 0 lost
components.
