# UPD_Plotter_11 — Block 1 Report

## Что было сломано

- F-001: PDF centerline math падал на route edge 20 из-за разных
  rendered endpoints одного graph node.
- F-002: `python -m plotter_processor` отбрасывал return value `main()` и
  возвращал exit 0 для failed job.
- F-003: DOCX reader находил все VML `<v:line>` в `<w:pict>`, но
  импортировал только `lines[0]`.
- F-004: portrait A4 с origin 10×10 mm не помещался в штатный
  workspace 220×220 mm, но pipeline тратил время на import/layout/font
  и падал только на G-code validation.

## Как воспроизводилось

- Исходный PDF preserve за 2.5 s завершался с
  `Non-adjacent route jump at edge 20: Point(..., 1.75) != Point(..., 1.791666...)`.
  Процесс при этом ошибочно возвращал exit 0.
- Synthetic route `edge A -> shared node -> edge B` воспроизвёл
  quantized delta. Negative fixture с двумя node IDs воспроизвёл
  реальный gap.
- Subprocess с missing input создавал `report.status=error`, печатал
  `Error:`, но возвращал 0.
- Minimal DOCX fixture с тремя lines в одном pict давал одну
  semantic arrow.
- Full-test portrait A4 падал после примерно 24.5 s на
  machine Y около 290.448 mm.

## Root cause

- Raster math geometry строила endpoints из `edge.pixels`, тогда как
  graph junction имел отдельную canonical medoid coordinate. Route assembler
  корректно не принимал разорванную rendered geometry.
- `__main__.py` вызывал `main()` без `SystemExit`.
- `add_arrow()` жёстко выбирал первую VML line.
- Page format и machine profile валидировались независимо; полная
  workspace validation выполнялась лишь при G-code export.

## Какие файлы изменены

- `src/plotter_processor/centerline_font/edge_geometry.py`
- `src/plotter_processor/raster_centerline.py`
- `src/plotter_processor/document_paginator.py`
- `src/plotter_processor/__main__.py`
- `src/plotter_processor/docx_document_reader.py`
- `src/plotter_processor/document_models.py`
- `src/plotter_processor/document_image_layout.py`
- `src/plotter_processor/validator.py`
- `src/plotter_processor/pipeline.py`
- `README.md`
- `tests/test_centerline_routing.py`
- `tests/test_document_paginator.py`
- `tests/test_cli.py`
- `tests/test_docx_arrows.py`
- `tests/test_pipeline_preflight.py`

## Что именно изменено

- Добавлена топологическая endpoint normalization: node ID выбирает
  canonical point, а не distance epsilon. Route assembler остался strict.
- После снятия P0 был обнаружен и отдельно покрыт
  ранее скрытый defect: PDF semantic lines переносились с A4 на A5
  без scale и выходили за page bounds. Semantic geometry теперь применяет
  `PageTransform.scale`.
- Module entrypoint теперь делает `raise SystemExit(main())`.
- Каждая VML line импортируется отдельно с unique stable ID,
  source order, direction, start/end head styles, stroke color, width и
  pict/line source identity. `pict` не попадает повторно в generic image path.
- Page/workspace preflight выполняется до `read_structured_document`,
  font compilation, image processing, handwriting и simplification. README явно
  описывает, что default Ender profile не поддерживает portrait A4.

## Какие тесты добавлены

- Shared-node quantized endpoint и real-gap negative route tests.
- A4→A5 semantic-line scaling regression.
- Real subprocess success/failure tests для `python -m plotter_processor`.
- Minimal three-arrow VML pict fixture с count/order/IDs/direction/head/style/color/width.
- Impossible A4 preflight test с monkeypatch, доказывающим, что document
  reader не запускался.
- Compatible synthetic A4 workspace integration test.

## Какие команды прогнаны

- Исходные `pdf-centerline-preserve-a5` и `pdf-centerline-reflow-a5`.
- Full-test DOCX outline A5 hybrid с semantic debug.
- Targeted pytest suites для routing, raster centerline, LaTeX integration, paginator,
  CLI, VML arrows, optimizer, validator, G-code и preflight.
- `make lint`
- `make test`
- `make smoke`
- Independent G-code scan для PDF preserve/reflow, full-test DOCX и smoke.

## Результат до / после

| Проверка | До | После |
|---|---:|---:|
| PDF preserve | error edge 20 | ok, 32 target pages |
| PDF reflow | error edge 20 | ok, 33 target pages |
| Visual PDF formulas | blocked | 3 rendered; coverage 0.918776–0.984466 |
| Shared graph endpoint | delta 0.041667 | exact canonical node point |
| Distinct-node real gap | not covered | rejected by strict assembler |
| Failed module run | exit 0 | exit 1, error report preserved |
| Successful module run | exit 0 | exit 0 |
| Full-test VML arrows | 1 semantic/rendered | 3 semantic/rendered, 0 generic duplicates |
| Default A4 failure | late, about 24.5 s | preflight, 1.34 s, exit 1 |
| Compatible synthetic A4 | not covered | ok, G-code created |
| Full pytest | 239 passed baseline | 247 passed |

В optimized full-test paths все три arrow shafts сохраняют
`preserve_order=true` и исходное направление X; optimizer не перенёс
arrow head на противоположный конец.

PDF jobs создали root preview/G-code/report/job manifest и для каждой
страницы `paths.json`, preview, G-code и report. Math debug содержит mask,
skeleton, graph, centerline, overlay, source и absorbed-element artifacts. Два
visual-math candidate имеют explicit absorbed-element records; один из них
поглощает `drawing-0`.

Quality gate:

- lint: passed;
- test: 247 passed;
- smoke: passed;
- G-code safety: passed; `M104`, `M109`, `M140`, `M190`, `G28`, extrusion `E`,
  `NaN`, `Infinity` не найдены.

## Оставшиеся ограничения

- После разблокировки PDF выявлены отдельные fidelity findings,
  которые не маскировались в F-001: control PDF даёт 0 semantic tables,
  0 arrows, 39 generic lines и 32 underlines; часть table/arrow drawings импортируется
  как raster. Это требует отдельного PDF semantic-fidelity finding, а не
  расширения bugfix F-001.
- Preserve/reflow создают 32/33 A5 pages и имеют разные preview hashes.
  Semantic lines больше не выходят за bounds, но preserve placement и
  классификация underline/table borders требуют отдельного визуального
  и layout investigation.
- Report fields `classification_conflicts` и `duplicate_primitives_suppressed` всё ещё
  равны hard-coded zero; поэтому отсутствие duplicate rendering не объявляется
  доказанным. Это остаётся F-009 из плана.
- Штатный machine profile по-прежнему физически не поддерживает
  portrait A4; workspace не изменялся.
