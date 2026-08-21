# Update 7 — отчёт по блоку 2

## Результат

Блок 2 реализован поверх фактического commit
`06a72e061d154a24a2a806863e5cd2911279c5f8`. Изменения не затрагивают
реализацию блока 1 и сохраняют прежний `reflow` как default.

Реализовано:

- все внутренние source bbox DOCX/PDF нормализованы в миллиметры;
- DOCX reader импортирует inline/anchor, horizontal/vertical position,
  square/top-bottom/none wrap, distances, behind-text, z-order и rotation metadata;
- добавлен `--document-layout reflow|hybrid|preserve`, старый `--pdf-layout`
  сохранён как совместимый alias с проверкой конфликтов;
- contain-mapping использует единый X/Y scale и ограничивает upscale;
- hybrid сохраняет левую/правую сторону и использует exclusion zones для текста;
- inline остаётся в потоке, top-bottom сдвигает последующий текст ниже рисунка;
- raster images и PDF vectors проходят общий placement и bounds-check;
- в `document-structure.json` записываются source/target bbox, anchor, wrap,
  scale, shift, warnings и координатная единица;
- `report.json` содержит отдельный раздел `document_layout`;
- `--layout-debug` создаёт source/target/overlay SVG и `placement.json`.

## Изменённые файлы блока 2

- `src/plotter_processor/layout_models.py`;
- `src/plotter_processor/layout_debug.py`;
- `src/plotter_processor/document_models.py`;
- `src/plotter_processor/docx_document_reader.py`;
- `src/plotter_processor/pdf_document_reader.py`;
- `src/plotter_processor/document_paginator.py`;
- `src/plotter_processor/document_image_layout.py`;
- `src/plotter_processor/pipeline.py`;
- `src/plotter_processor/cli.py`;
- `configs/layout.yaml`;
- `README.md`;
- `tools/generate_update_7_fixtures.py`;
- `tools/run_update_7_block_2_demo.py`;
- `tests/test_layout_mapping.py`;
- `tests/test_exclusion_zones.py`;
- `tests/test_flow_layout.py`;
- `tests/test_docx_image_anchors.py`;
- `tests/test_pdf_preserve_layout.py`;
- `tests/test_hybrid_image_layout.py`;
- `tests/test_layout_debug_export.py`;
- `tests/test_docx_document_reader.py`;
- `examples/update_7/block_2/*`.

## Baseline и метрики

| Сценарий | Baseline | Блок 2 |
|---|---:|---:|
| DOCX left: центр рисунка X | 74.00 mm | 41.29 mm |
| DOCX right: центр рисунка X | 74.00 mm | 112.22 mm |
| PDF reflow: центр target bbox X | 74.00 mm | 74.00 mm |
| PDF preserve: центр target bbox X | — | 110.68 mm |
| PDF preserve displacement после mapping | — | 0.00 mm |
| DOCX hybrid scale | — | 1.000 |
| PDF preserve contain-scale | — | 0.864864 |
| Text/image overlap во всех demo | не измерялся | 0.00 mm² |
| Page overflow во всех demo | не измерялся | 0.00 mm² |

Baseline центрировал и левый, и правый DOCX-рисунок на `X=74 mm`. Candidate
сохраняет сторону. В каждом задании raster image представлен одним element id
и векторизован ровно один раз; повторной печати объекта нет.

## Демонстрации

Входы:

- `examples/update_7/block_2/image-left-square-wrap.docx`;
- `examples/update_7/block_2/image-right-square-wrap.docx`;
- `examples/update_7/block_2/pdf-image-right.pdf`.

Результаты находятся в `build/update_7/candidate/block_2`:

- `docx-left-hybrid/plotter-preview.svg` и `layout-debug/placement-overlay.svg`;
- `docx-right-hybrid/plotter-preview.svg` и `layout-debug/placement-overlay.svg`;
- `pdf-right-reflow/plotter-preview.svg`;
- `pdf-right-preserve/plotter-preview.svg` и `layout-debug/placement-overlay.svg`;
- общая сводка: `demo-summary.json`.

Каждый каталог содержит `paths.json`, `report.json`, `output.gcode`,
`document-structure.json` и полный `layout-debug`.

## Команды проверки

```bash
.venv/bin/python tools/generate_update_7_fixtures.py
.venv/bin/python tools/run_update_7_block_2_demo.py --font assets/1.ttf
make lint
make test
```

Фактический результат: lint без ошибок, полный набор `191 passed`; после
добавления отдельной top-bottom integration-проверки — `192 passed`. Все четыре
demo-job имеют status `ok`. G-code проверен: нет нагрева, extrusion, `G28`,
NaN или Infinity.

## Ограничения

- DOCX `wrapTight` и `wrapThrough` аппроксимируются прямоугольным square bbox;
- `behindText` безопасно преобразуется в square wrap;
- paragraph-relative vertical anchor сохраняет сторону, а Y привязывает к
  текущей позиции потока — это не полный алгоритм Microsoft Word;
- preserve фиксирует bbox графики, но текст вокруг неё всё ещё проходит через
  безопасный exclusion-flow, а не воспроизводит координаты каждого PDF glyph;
- rotation metadata импортируется, но поворот raster strokes пока не применяется;
- сложные конфликтующие anchors используют ограниченный детерминированный
  поиск и могут перейти в top-bottom fallback с warning;
- физический dry-run на подключённом плоттере в этой среде не выполнялся.

Блок 2 закончен. Переход к блоку 3 возможен только после отдельного указания.
