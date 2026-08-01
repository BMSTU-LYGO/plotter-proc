# Блок 1 — centerline-LaTeX и visual PDF math

## База

- Base SHA: `c7e2296e2349438e97eef85de43da039f1b4a543`.
- Ветка: `upd/plotter-7-layout-math-lines-tables`.
- Изменения находятся в рабочем дереве и не создают фиктивный final SHA.

## Реализовано

- общий deterministic mask-to-centerline слой с bounded complexity;
- MathText high-resolution mask и centerline как default;
- совместимый `outline` mode и управляемый fallback;
- quality metrics, strict gate и расширенные debug artifacts;
- basic OMML parser и отдельные `SourceMathElement`;
- консервативный PDF math detector и visual clip reconstruction;
- suppression поглощённых PDF text/vector primitives;
- provenance, source/target bbox и formula details в report;
- CLI: `--latex-stroke-mode`, `--strict-latex-quality`, `--pdf-math`, `--math-debug`.

## Baseline и candidate

| Сценарий | Baseline | Candidate |
|---|---:|---:|
| Complex formula strokes / pen lifts | 42 | 37 |
| Complex formula draw length | 498.652 mm | 274.438 mm |
| Complex formula outline strokes | 42 | 0 |
| Basic OMML formulas | 0 | 1 |
| PDF text formula regions | 0 | 1 |
| PDF vector formula regions | 0 | 1 |

Длина рисования complex semantic formulas уменьшилась на 44.964%, все три
формулы прошли strict quality gate без `needs_review`.

## Проверка

```bash
.venv/bin/python tools/generate_update_7_fixtures.py
.venv/bin/python tools/update_7_baseline.py --font assets/1.ttf --timeout-seconds 60
.venv/bin/python -m plotter_processor run \
  tests/fixtures/update_7/latex/latex_complex.txt \
  --font assets/1.ttf --font-mode centerline \
  --latex mathtext --latex-stroke-mode centerline \
  --strict-latex-quality --latex-debug --page A5 \
  --output-dir build/update_7/candidate/block_1/latex-complex
.venv/bin/python -m plotter_processor run \
  tests/fixtures/update_7/latex/pdf_formula_text.pdf \
  --font assets/1.ttf --font-mode outline --pdf-math auto --math-debug \
  --page A5 --output-dir build/update_7/candidate/block_1/pdf-formula-text
.venv/bin/python tools/compare_update_7.py
make test
make lint
```

## Ограничения

- MathText остаётся подмножеством LaTeX, внешний TeX не запускается.
- OMML поддержан частично; неизвестные nodes дают точный warning.
- PDF mode воспроизводит visual region и не восстанавливает исходный `.tex`.
- Low-confidence PDF regions не поглощаются и остаются старой геометрией.
- Формула PDF сохраняет reading order и source bbox, но точное coordinate-preserve
  размещение относится к Блоку 2.
- OCR сканированных формул не выполняется.
- Физический dry-run требует подключённого плоттера и в этой среде не выполнялся.
