# Примеры блока 2 Update 7

- `image-left-square-wrap.docx` — рисунок остаётся слева, текст идёт справа;
- `image-right-square-wrap.docx` — рисунок остаётся справа, текст идёт слева;
- `pdf-image-right.pdf` — сравнение `reflow` и `preserve` на одном входе.

```bash
.venv/bin/python tools/run_update_7_block_2_demo.py --font assets/1.ttf
```

Каждое задание создаёт preview, paths, report, безопасный G-code и
`layout-debug` с source/target/overlay SVG и `placement.json`.
