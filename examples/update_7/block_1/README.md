# Полный пример блока 1 Update 7

Это один демонстрационный комплект из двух входных документов, потому что
нативная Word-формула OMML существует только в DOCX, а visual-реконструкция
формулы проверяется только на PDF.

- `semantic-omml.docx` проверяет обычный centerline-текст, inline- и block-LaTeX,
  а также настоящую формулу Word OMML.
- `pdf-visual-math.pdf` проверяет high-confidence текстовую формулу PDF,
  формулу с векторной чертой дроби, clip-rendering и подавление повторной
  отрисовки поглощённых PDF-примитивов.
- Для каждой формулы включены centerline quality gate и debug-артефакты.
- Каждый запуск создаёт SVG-preview, `paths.json`, `report.json` и безопасный
  `output.gcode` без нагрева, extrusion и `G28`.

Запуск всего примера:

```bash
.venv/bin/python tools/run_update_7_block_1_demo.py --font assets/1.ttf
```

Итоговая сводка находится в
`build/update_7/block_1-example/demo-summary.json`.
