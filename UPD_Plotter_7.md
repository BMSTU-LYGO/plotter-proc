# UPD_Plotter_7 — изображения из PDF/DOCX, многостраничные задания и начало поддержки LaTeX

## Назначение

Пошаговая инструкция для Codex по доработке репозитория `BMSTU-LYGO/plotter-proc`.

Рабочая ветка:

```bash
git checkout master
git pull
git checkout -b upd/document-images-pagination-latex
```

Работу выполнять **строго по блокам**:

1. Векторизация изображений из PDF и DOCX.
2. Автоматическая разбивка на страницы, нумерация и пауза для смены листа.
3. Начальная поддержка LaTeX.

После каждого блока Codex обязан:

- запустить тесты и линтер;
- создать демонстрационные артефакты;
- проверить безопасность G-code;
- написать пользователю отдельный отчёт о сделанном;
- только после отчёта переходить к следующему блоку.

Нельзя выполнять все изменения одним неразделённым рефакторингом.

---

# 1. Текущее состояние, которое нужно учитывать

В проекте уже есть:

- чтение TXT, DOCX и PDF с текстовым слоем;
- TTF outline и centerline;
- HarfBuzz shaping;
- соединение рукописных букв;
- `Point`, `PlotterStroke`, `PathDocument`;
- SVG-preview, `paths.json` и безопасный G-code;
- безопасный импорт ограниченного SVG line-art;
- `compose`-pipeline для текста и SVG;
- профили движения и проверка workspace.

Критические ограничения:

1. `DocumentText` хранит только строки и теряет картинки, страницы, размеры и координаты.
2. DOCX читается через `document.paragraphs`, поэтому изображения и их порядок не сохраняются.
3. PDF reader извлекает только текстовые блоки.
4. `layout_text()` рассчитан на одну страницу и падает с `Text does not fit on one page`.
5. `PathDocument` описывает только одну физическую страницу.
6. `generate_gcode()` завершает одну страницу командами `M400`, `M84`.
7. LaTeX пока не поддерживается.

Не удалять и не переписывать без необходимости работающие centerline, handwriting, shaping, SVG importer и G-code safety.

---

# 2. Общие архитектурные правила

## 2.1. Сохранить обратную совместимость

После обновления должна работать старая команда:

```bash
python -m plotter_processor run examples/input.txt \
  --font assets/handwriting.ttf \
  --font-mode centerline \
  --page A5 \
  --size normal \
  --output-dir build
```

Короткий TXT должен по-прежнему создавать preview, paths, G-code и report. Для одной страницы не должно быть межстраничной паузы.

## 2.2. Не создавать второй формат геометрии

Все новые элементы в итоге переводить в существующие:

```python
Point
PlotterStroke
PathDocument
```

Общая цепочка:

```text
PDF/DOCX/TXT
→ структурированная модель
→ текстовые, графические и математические элементы
→ пагинация
→ PathDocument для каждой страницы
→ SVG / paths.json / G-code
```

## 2.3. Безопасность

В итоговом G-code по умолчанию запрещены:

```text
M104 M109 M140 M190
```

Также не должно быть:

- координат экструдера `E...`;
- `G28`, если он выключен;
- выхода за `workspace_mm`;
- парковки с опущенным пером;
- `M84` между страницами.

## 2.4. Детерминированность

Одинаковый input и config должны давать одинаковое число страниц, порядок элементов, координаты, штрихи и имена файлов.

## 2.5. Разделить новые модули

Рекомендуемые модули:

```text
document_models.py
structured_document_reader.py
pdf_document_reader.py
docx_document_reader.py
image_preprocessor.py
image_vectorizer.py
document_paginator.py
page_numbering.py
multipage_gcode_exporter.py
job_exporter.py
latex_parser.py
latex_renderer.py
```

Названия можно изменить, но нельзя превращать `pipeline.py` в монолит.

---

# 3. Подготовительный этап

## Шаг 0.1. Зафиксировать baseline

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
```

Зафиксировать:

- количество прошедших тестов;
- старые падения, если они есть;
- Python version;
- версии PyMuPDF, python-docx, Pillow, scikit-image и fonttools.

## Шаг 0.2. Создать fixtures

Нужны воспроизводимые fixtures:

1. DOCX: текст → inline PNG → текст.
2. DOCX: картинка отдельным абзацем.
3. DOCX: anchored/floating picture.
4. PDF: текст и raster image.
5. PDF: одна картинка показана два раза.
6. PDF: line, rectangle, circle и bezier.
7. TXT на 3–4 страницы A5.
8. Смешанный документ с картинкой около границы страницы.
9. TXT с простыми LaTeX-формулами.

По возможности генерировать fixtures в тестах, не хранить большие binary-файлы.

---

# БЛОК 1. Векторизация изображений из PDF и DOCX

## 4. Цель блока

Пользователь передаёт PDF или DOCX с текстом и картинками. Pipeline должен:

1. извлечь картинки;
2. сохранить порядок относительно текста;
3. очистить изображение;
4. преобразовать его в линии;
5. разместить на странице;
6. включить линии в preview, paths и G-code.

OCR не требуется. Текст внутри картинки обрабатывается как графика.

---

## 5. Шаг 1.1. Ввести структурированную модель

Добавить модель примерно такого уровня:

```python
@dataclass(frozen=True, slots=True)
class SourceDocument:
    source_path: Path
    pages: tuple["SourcePage", ...]
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class SourcePage:
    source_page_index: int
    width_pt: float | None
    height_pt: float | None
    elements: tuple["SourceElement", ...]

@dataclass(frozen=True, slots=True)
class SourceTextElement:
    id: str
    source_order: int
    source_page_index: int
    paragraphs: tuple[str, ...]
    bbox: SourceBBox | None = None

@dataclass(frozen=True, slots=True)
class SourceRasterImageElement:
    id: str
    source_order: int
    source_page_index: int
    image_path: Path
    width_px: int
    height_px: int
    displayed_width: float | None
    displayed_height: float | None
    bbox: SourceBBox | None = None

@dataclass(frozen=True, slots=True)
class SourceVectorElement:
    id: str
    source_order: int
    source_page_index: int
    strokes: tuple[PlotterStroke, ...]
    bbox: SourceBBox | None = None
```

Старый `read_document()` временно оставить как text-only adapter, но основной pipeline перевести на новую модель.

**Желаемый результат:** текст и картинки не теряются после чтения; порядок можно проверить тестом; TXT также представляется структурированным документом.

---

## 6. Шаг 1.2. Извлечение из PDF

Для каждой PDF-страницы:

1. получить `page.get_text("dict")`;
2. извлечь text blocks;
3. извлечь image blocks с bbox и binary data;
4. получить простую векторную графику через `page.get_drawings()`;
5. сохранить source order;
6. учитывать rotation, cropbox и координаты страницы.

Использовать данные конкретных отображаемых image blocks, а не только XREF-список. Одинаковый binary blob можно хранить один раз по hash, но каждое размещение должно быть отдельным element.

Артефакты:

```text
build/extracted-assets/page-001/image-001-<hash>.png
```

Простые PDF drawings переводить напрямую:

- line;
- polyline;
- rectangle;
- bezier;
- circle/ellipse.

Сложные fill, clipping, gradient и transparency не угадывать. Делать warning и fallback: растрировать только bbox и передать в image vectorizer.

Явно преобразовывать points в mm:

```text
1 pt = 25.4 / 72 mm
```

**Желаемый результат:** PDF с текстом, raster image и схемой даёт три разных типа элементов.

---

## 7. Шаг 1.3. Извлечение из DOCX

Нельзя отдельно читать `document.paragraphs` и `document.inline_shapes`: так теряется общий порядок.

Нужно обходить XML body, paragraphs и runs по порядку.

Для каждой картинки:

1. найти `w:drawing`;
2. найти `a:blip`;
3. получить `r:embed`;
4. через relationship получить blob;
5. определить формат;
6. получить размер из `wp:extent`;
7. сохранить asset;
8. вставить image element в точное место потока.

Полностью поддержать inline pictures:

- между runs;
- отдельным абзацем;
- несколько картинок в одном абзаце;
- исходный размер и пропорции.

Для `wp:anchor`:

- обнаруживать floating picture;
- читать приблизительный bbox;
- не игнорировать;
- если точная привязка пока невозможна, поместить после ближайшего абзаца и записать warning `floating_image_reflowed`.

Картинки внутри table cells не должны теряться. Табличную раскладку можно упростить с warning.

**Желаемый результат:** DOCX `текст → картинка → текст` сохраняет этот порядок.

---

## 8. Шаг 1.4. Preprocessing

Создать `image_preprocessor.py`.

Обязательные действия:

1. Pillow open;
2. EXIF transpose;
3. alpha на белый фон;
4. grayscale;
5. ограничение рабочего разрешения;
6. autocontrast;
7. слабое сглаживание;
8. удаление мелкого шума;
9. debug image.

Добавить конфигурацию:

```yaml
images:
  enabled: true
  mode: auto
  max_input_pixels: 12000000
  max_working_side_px: 1600
  background: white
  autocontrast: true
  blur_sigma: 0.6
  threshold:
    method: otsu
    value: 160
  remove_small_objects_px: 12
  edge:
    sigma: 1.2
    low_threshold: 0.08
    high_threshold: 0.20
  vector:
    simplify_tolerance_mm: 0.08
    min_stroke_length_mm: 0.35
    max_points_per_image: 100000
    max_strokes_per_image: 10000
```

При превышении лимита завершаться понятной ошибкой и удалять stale G-code.

---

## 9. Шаг 1.5. Векторизация

Создать `image_vectorizer.py`.

### `outline`

```text
grayscale
→ edge detection
→ contours
→ flatten
→ simplify
→ remove short strokes
→ scale to mm
```

Использовать для фотографий, схем и логотипов, когда нужны границы.

### `centerline`

```text
grayscale
→ threshold
→ binary mask
→ remove noise
→ skeletonize/medial axis
→ graph tracing
→ simplify
→ route
```

Использовать для чёрно-белых штриховых рисунков. Переиспользовать существующие идеи skeleton/routing, но не TTF glyph cache.

### `auto`

Детерминированно выбирать по:

- бинарности;
- foreground ratio;
- edge density;
- доле белого фона;
- числу уровней яркости.

Выбранный режим записывать в report.

Нельзя:

- делать отдельный stroke на пиксель;
- генерировать миллионы точек;
- соединять независимые контуры через пустое место;
- скрывать fallback.

---

## 10. Шаг 1.6. Размещение изображения

Для DOCX inline image:

- переводить размер из EMU в mm;
- сохранять пропорции;
- ограничивать шириной usable area;
- считать атомарным блоком;
- переносить целиком, если не хватает высоты.

Для PDF:

```yaml
document_import:
  pdf_layout: reflow
  preserve_source_page_breaks: true
```

В MVP:

- source PDF page начинает логическую секцию;
- элементы сортируются по `(y, x, source_order)`;
- текст reflow-ится;
- изображение масштабируется по bbox;
- простая vector graphics сохраняется как линии;
- в report писать `layout_mode: reflow`.

Интервалы:

```yaml
images:
  spacing_before_mm: 2.0
  spacing_after_mm: 2.0
  default_width_ratio: 0.75
  max_height_ratio: 0.60
```

---

## 11. Шаг 1.7. Интеграция в paths

Присваивать metadata:

```python
element_id="page-001-image-002"
element_type="raster-image"
source_path=".../image-002.png"
segment_types=("image-outline",)
```

Для PDF drawing:

```python
element_type="pdf-vector"
segment_types=("pdf-line", "pdf-bezier")
```

Все image strokes проходят:

- clipping;
- finite validation;
- simplification;
- workspace validation;
- preview;
- общий G-code exporter.

Группировать штрихи одного рисунка, чтобы travel optimization не разрушал порядок.

---

## 12. Шаг 1.8. CLI и артефакты

Добавить:

```text
--images auto|outline|centerline|off
--image-debug
--pdf-layout reflow|preserve
```

Default: `--images auto`.

Создавать:

```text
build/
├── extracted-assets/
├── image-debug/
├── document-structure.json
├── plotter-preview.svg
├── paths.json
├── output.gcode
└── report.json
```

`document-structure.json` хранит элементы, порядок, bbox, asset path, mode и warnings без binary data.

В report добавить:

```json
{
  "document_import": {
    "source_pages": 2,
    "text_elements": 8,
    "raster_images_found": 3,
    "raster_images_vectorized": 3,
    "pdf_vector_elements": 2,
    "images_skipped": 0,
    "image_strokes": 147,
    "image_points": 2810
  }
}
```

---

## 13. Тесты блока 1

Добавить:

```text
test_structured_document_reader.py
test_pdf_document_reader.py
test_docx_document_reader.py
test_image_preprocessor.py
test_image_vectorizer.py
test_document_image_pipeline.py
```

Проверить:

1. PDF image block извлекается.
2. Один blob в двух местах даёт два placements.
3. PDF vector line остаётся линией.
4. DOCX inline image сохраняет порядок.
5. Anchored image не игнорируется.
6. Image в table cell не теряется.
7. Transparent PNG получает белый фон.
8. Большая картинка уменьшается до лимита.
9. Белая картинка даёт warning.
10. Сложность ограничивается safe limits.
11. `--images off` пишет warning.
12. Image strokes есть в preview, paths и G-code.
13. Старый TXT работает.
14. G-code безопасен.

## Критерии приёмки блока 1

- PDF и DOCX с картинками обрабатываются без ручного извлечения;
- порядок текста и картинок сохранён;
- картинка видна в preview;
- линии картинки есть в paths и G-code;
- картинка не выходит за поля;
- лимиты сложности работают;
- старые тесты не сломаны.

## Отчёт пользователю после блока 1

```markdown
## Блок 1 завершён: изображения из PDF/DOCX

### Что сделано
### Какие файлы изменены
### Как работает pipeline
### Что проверено
### Демонстрационные результаты
### Ограничения
### Как запустить
```


---

# БЛОК 2. Разбивка на страницы, нумерация и пауза 1.5 минуты

## 14. Цель блока

Если контент не помещается на одну страницу выбранного формата, pipeline должен:

- автоматически создать нужное число страниц;
- не завершаться ошибкой overflow;
- пронумеровать страницы снизу по центру;
- создать отдельные артефакты каждой страницы;
- создать единый G-code всего задания;
- после каждой страницы, кроме последней:
  - поднять перо;
  - отъехать в настроенный угол;
  - дождаться завершения движения;
  - ждать 90 секунд;
  - начать следующую страницу;
- не отключать шаговые двигатели между страницами.

---

## 15. Шаг 2.1. Ввести модель многостраничного задания

Не хранить несколько физических страниц в одном `PathDocument`.

Добавить:

```python
@dataclass(slots=True)
class PageJob:
    page_index: int
    page_number: int
    path_document: PathDocument
    source_element_ids: tuple[str, ...]
    warnings: list[str]
    metadata: dict[str, object]

@dataclass(slots=True)
class PlotterJob:
    page_spec: PageSpec
    pages: list[PageJob]
    warnings: list[str]
    metadata: dict[str, object]
```

`PathDocument` остаётся моделью одной страницы.

**Желаемый результат:** page-level геометрия отделена от job-level управления.

---

## 16. Шаг 2.2. Заменить overflow error на paginator

Создать:

```python
paginate_document(...)
```

или класс:

```python
DocumentPaginator
```

Текущий `layout_text()` можно оставить как низкоуровневый helper для одной страницы.

### Алгоритм текста

1. Вычислить usable width/height.
2. Зарезервировать footer.
3. Разбить параграфы на tokens и shaped clusters.
4. Формировать строки.
5. Проверять высоту строки до добавления.
6. При переполнении завершать страницу.
7. Продолжать с текущего token на новой странице.
8. Не терять и не дублировать символы.
9. Не создавать пустые первую или последнюю страницы.

### Длинное слово

Если слово шире usable width:

- переносить по glyph cluster;
- не разрывать HarfBuzz cluster;
- записывать `forced_word_break`;
- если отдельный glyph шире страницы — понятная ошибка.

### Параграфы

- пустой параграф сохраняет вертикальный интервал;
- paragraph spacing не создаёт пустую страницу;
- параграф может продолжаться на следующей странице.

**Желаемый результат:** длинный TXT автоматически создаёт несколько страниц.

---

## 17. Шаг 2.3. Смешанный контент

Изображение или vector element считать атомарным блоком.

Правила:

1. Если помещается в остаток страницы — разместить.
2. Если не помещается — перенести на следующую.
3. Если больше полной usable area — уменьшить с сохранением пропорций.
4. Не разрезать изображение между страницами в MVP.
5. Не заходить в footer.
6. Сохранять spacing before/after.
7. Уважать explicit/source page breaks.

Для PDF по default сохранить начало новой source page, если:

```yaml
pagination:
  preserve_source_page_breaks: true
```

**Желаемый результат:** `текст → картинка → текст` переносится без наложений.

---

## 18. Шаг 2.4. Зарезервировать footer

Добавить:

```yaml
pagination:
  enabled: true
  preserve_source_page_breaks: true
  footer:
    enabled: true
    reserved_height_mm: 8.0
    baseline_from_bottom_mm: 4.5
    format: "{page}"
    size: small
    font_mode: centerline
```

Основной контент не должен заходить в `reserved_height_mm`.

Номер размещать снизу по центру. Центрирование выполнять по реальной ширине glyph sequence, а не по числу символов.

---

## 19. Шаг 2.5. Двухпроходная нумерация

Сначала paginator должен узнать `page_count`.

Затем второй проход:

1. сформировать строку номера;
2. проверить glyph coverage;
3. измерить ширину;
4. вычислить centered X;
5. добавить strokes номера;
6. обновить preview и paths.

Default format:

```text
1
2
3
```

Сразу заложить поддержку:

```yaml
format: "{page}/{pages}"
```

но не делать её default.

### Шрифт номера

Приоритет:

1. основной font;
2. отдельный `page_number_font`;
3. fallback font.

Если цифр нет — ошибка до G-code.

**Желаемый результат:** каждая страница имеет правильный номер снизу по центру.

---

## 20. Шаг 2.6. Артефакты страниц

Структура:

```text
build/
├── pages/
│   ├── page-001/
│   │   ├── font-preview.svg
│   │   ├── plotter-preview.svg
│   │   ├── paths.json
│   │   ├── page.gcode
│   │   └── report.json
│   ├── page-002/
│   └── page-003/
├── plotter-preview.svg
├── output.gcode
├── job.json
└── report.json
```

Для одной страницы сохранить старые корневые файлы.

Для нескольких страниц:

- корневой `output.gcode` — общее задание;
- `pages/page-NNN/page.gcode` — ручной запуск одной страницы;
- preview каждой страницы — отдельный;
- `job.json` — список страниц и файлов.

---

## 21. Шаг 2.7. Настройки смены листа

Добавить в `machine.yaml`:

```yaml
page_change:
  enabled: true
  pause_seconds: 90
  park:
    mode: corner
    corner: top_right
    inset_mm: 5.0
  wait_command: dwell
  keep_steppers_enabled: true
```

Не хардкодить координаты парковки.

Park point должна:

- вычисляться относительно page size и `page_origin_mm`;
- учитывать `invert_x` и `invert_y`;
- проверяться через workspace;
- выполняться только с поднятым пером.

Дополнительно поддержать:

```yaml
park:
  mode: machine_point
  x_mm: 210.0
  y_mm: 10.0
```

---

## 22. Шаг 2.8. Job-level G-code exporter

Создать:

```python
generate_job_gcode(
    job: PlotterJob,
    machine_config: dict,
    ...
) -> str
```

Не склеивать готовые `page.gcode`, потому что в них есть повторные headers и `M84`.

### Общая последовательность

Начало:

```gcode
; Generated by plotter-processor
; Pages: 3
G21
G90
G0 Z<up_z> F<z_feed>
```

Перед страницей:

```gcode
; ===== PAGE 1/3 START =====
```

Между страницами:

```gcode
G0 Z<up_z> F<z_feed>
; PAGE 1/3 COMPLETE
G0 X<park_x> Y<park_y> F<travel_feed>
M400
; CHANGE PAPER - WAIT 90 SECONDS
G4 P90000
; ===== PAGE 2/3 START =====
```

Финал:

```gcode
G0 Z<up_z> F<z_feed>
M400
M84
; End
```

### Обязательные свойства

- `M84` один раз в конце;
- пауз `page_count - 1`;
- default pause — `G4 P90000`;
- pen-up до park move;
- `M400` перед dwell;
- после pause перо поднято;
- workspace проверяется;
- command limit учитывает весь job;
- нет heating/extrusion;
- нет `G28` по default.

---

## 23. Шаг 2.9. Отдельные page.gcode

Каждый `page-NNN/page.gcode`:

- запускает только одну страницу;
- имеет собственный header;
- имеет final `M84`;
- не имеет page-change pause;
- содержит номер страницы в комментарии.

Это нужно для повторной печати испорченного листа.

---

## 24. Шаг 2.10. CLI

Добавить:

```text
--paginate / --no-paginate
--page-numbers / --no-page-numbers
--page-pause-seconds 90
--park-corner top_left|top_right|bottom_left|bottom_right
```

CLI имеет приоритет над YAML.

Default:

- pagination включена;
- page numbers включены;
- pause = 90;
- corner из config.

Пример:

```bash
python -m plotter_processor run examples/long-document.docx \
  --font assets/handwriting.ttf \
  --font-mode centerline \
  --page A5 \
  --paginate \
  --page-numbers \
  --page-pause-seconds 90 \
  --output-dir build/long-document
```

---

## 25. Шаг 2.11. Report и время

Добавить:

```json
{
  "pagination": {
    "enabled": true,
    "page_count": 3,
    "page_numbers": true,
    "page_number_format": "{page}",
    "pause_seconds": 90,
    "pause_count": 2,
    "total_pause_seconds": 180,
    "park_mode": "corner",
    "park_corner": "top_right"
  },
  "pages": [
    {
      "page": 1,
      "characters": 1200,
      "text_elements": 8,
      "image_elements": 1,
      "strokes": 940,
      "draw_distance_mm": 3200.4,
      "gcode": "pages/page-001/page.gcode"
    }
  ]
}
```

Время разделить:

```json
{
  "ideal_motion_time_seconds": 1000,
  "page_change_pause_time_seconds": 180,
  "estimated_job_time_seconds": 1180
}
```

---

## 26. Тесты блока 2

Добавить:

```text
test_document_paginator.py
test_page_numbering.py
test_multipage_gcode_exporter.py
test_multipage_pipeline.py
```

Обязательные сценарии:

1. Короткий документ → 1 page.
2. Overflow на одну строку → 2 pages.
3. Длинный input → стабильный page count.
4. Символы не потеряны.
5. Символы не продублированы.
6. Пустой paragraph не создаёт пустую page.
7. Длинное слово переносится.
8. Image переносится целиком.
9. Большой image уменьшается.
10. Footer зарезервирован.
11. Page number centered.
12. Номера `1`, `2`, `3`.
13. Общий G-code содержит `N-1` pauses.
14. Перед pause есть pen-up.
15. Перед pause есть park move.
16. Перед `G4 P90000` есть `M400`.
17. `M84` отсутствует между pages.
18. `M84` есть в конце.
19. Page G-code не содержит межстраничную pause.
20. Park workspace violation вызывает ошибку.
21. Command limit считается для job.
22. Старый one-page pipeline работает.
23. Heating/extrusion отсутствуют.

## Критерии приёмки блока 2

- overflow больше не завершает pipeline;
- создаются несколько pages;
- каждая page пронумерована;
- общий G-code содержит 90 секунд между pages;
- pen поднят до парковки;
- принтер паркуется в настроенном углу;
- motors не отключаются до финала;
- есть отдельные G-code страниц;
- report содержит page-level статистику.

## Отчёт пользователю после блока 2

```markdown
## Блок 2 завершён: многостраничная печать

### Что сделано
### Как работает перенос
### Нумерация страниц
### Смена страницы в G-code
### Проверки безопасности
### Тестовый документ и число страниц
### Ограничения
### Как запустить
```


---

# БЛОК 3. Начало поддержки LaTeX

## 27. Цель блока

Добавить первую рабочую поддержку математических формул без попытки реализовать полный TeX.

Поддержать LaTeX-подобные выражения внутри TXT, обычного текста DOCX и composition text:

```text
Квадрат суммы: $(a+b)^2 = a^2 + 2ab + b^2$.

$$
\int_0^1 x^2 dx = \frac{1}{3}
$$
```

Формула должна:

- распознаваться отдельно от текста;
- превращаться в vector paths;
- участвовать в layout и pagination;
- быть видна в preview;
- попадать в paths и G-code.

---

## 28. Границы MVP

### Поддержать

- inline `$...$`;
- inline `\(...\)`;
- block `$$...$$`;
- block `\[...\]`;
- superscript/subscript;
- fractions;
- square roots;
- Greek letters;
- common operators;
- sums/integrals;
- brackets;
- escaped dollar `\$`.

### Пока не поддерживать

- полный LaTeX document;
- `\documentclass`;
- packages;
- TikZ;
- user macros;
- bibliography;
- shell execution;
- внешний системный `latex`;
- arbitrary file includes;
- полный OMML → LaTeX;
- восстановление LaTeX из PDF.

Эти ограничения явно записать в README и report.

---

## 29. Шаг 3.1. Ввести MathElement

Расширить source model:

```python
@dataclass(frozen=True, slots=True)
class SourceMathElement:
    id: str
    source_order: int
    source_page_index: int
    expression: str
    display_mode: bool
    source_syntax: str
```

Layout model:

```python
@dataclass(frozen=True, slots=True)
class MathLayoutElement:
    expression: str
    strokes: tuple[PlotterStroke, ...]
    width_mm: float
    height_mm: float
    baseline_mm: float
    display_mode: bool
```

После rendering formula ведёт себя как vector element с известным bbox.

---

## 30. Шаг 3.2. Безопасный parser

Создать `latex_parser.py`.

Parser возвращает последовательность:

```text
TextRun
MathRun
TextRun
MathBlock
TextRun
```

Правила:

- `\$` не открывает formula;
- незакрытый delimiter → понятная ошибка с позицией;
- пустая formula запрещена;
- `$$...$$` проверять раньше `$...$`;
- block может быть многострочным;
- ограничить длину expression;
- ограничить число formulas;
- не использовать регулярное выражение, которое может катастрофически тормозить на длинном input.

Config:

```yaml
latex:
  enabled: true
  backend: mathtext
  max_expression_length: 4000
  max_elements_per_document: 500
```

---

## 31. Шаг 3.3. MVP renderer без shell

Предпочтительный backend:

- добавить `matplotlib` dependency;
- использовать MathText;
- получить vector path формулы;
- перевести path в `PlotterStroke` через существующий curve flattener.

Не использовать:

```python
subprocess.run(["latex", ...])
os.system(...)
shell=True
```

Добавить abstraction:

```python
class MathRenderer(Protocol):
    def measure(self, expression: str, size_mm: float) -> MathMetrics: ...
    def render(self, expression: str, size_mm: float) -> RenderedMath: ...

class MathTextRenderer:
    ...
```

Это позволит позже подключить full TeX backend без переписывания paginator.

---

## 32. Шаг 3.4. Math path → PlotterStroke

Для path commands:

1. обработать `MOVETO`;
2. обработать `LINETO`;
3. обработать quadratic/cubic curves;
4. обработать `CLOSEPOLY`;
5. flatten curves;
6. удалить duplicate points;
7. simplify;
8. scale to mm;
9. корректно преобразовать Y axis;
10. вычислить bbox.

Metadata:

```python
element_type="latex"
source_chars=expression
segment_types=("latex-outline",)
```

В MVP формулы можно рисовать outline. Не прогонять formula glyphs через centerline cache рукописного TTF.

---

## 33. Шаг 3.5. Inline layout

Inline formula должна:

- измеряться до размещения;
- иметь advance width;
- выравниваться по baseline текста;
- переноситься целиком;
- не разрываться посередине;
- увеличивать line height, если выше текста.

Если formula шире строки:

1. уменьшить до `min_scale`;
2. если всё ещё не помещается — вынести как block;
3. записать warning.

---

## 34. Шаг 3.6. Block layout

Block formula должна:

- размещаться на отдельной строке;
- центрироваться;
- иметь spacing before/after;
- быть атомарной при pagination;
- переноситься целиком;
- уменьшаться только до minimum scale.

Config:

```yaml
latex:
  inline_size_scale: 1.0
  block_size_scale: 1.15
  block_spacing_before_mm: 2.0
  block_spacing_after_mm: 2.0
  block_alignment: center
  min_scale: 0.65
  curve_tolerance_mm: 0.04
```

---

## 35. Шаг 3.7. DOCX и PDF

### DOCX

На первом этапе:

- распознавать `$...$` и другие delimiters в text runs;
- обнаруживать OMML;
- если OMML нельзя преобразовать, писать `omml_equation_not_supported`;
- не игнорировать equation молча.

### PDF

Не восстанавливать исходный LaTeX. Формулы PDF обрабатываются как:

- text glyphs;
- PDF vector drawings;
- raster image;

через блок 1.

---

## 36. Шаг 3.8. CLI

Добавить:

```text
--latex auto|mathtext|off
--latex-debug
```

Default: `auto`.

Поведение:

- delimiters нет → старый pipeline;
- delimiters есть → MathText;
- `off` оставляет delimiters буквальным текстом и пишет warning;
- debug сохраняет отдельный SVG/JSON каждой формулы.

---

## 37. Шаг 3.9. Артефакты и report

Создавать:

```text
build/latex-debug/formula-001.svg
build/latex-debug/formula-001.json
```

Report:

```json
{
  "latex": {
    "enabled": true,
    "backend": "mathtext",
    "expressions_found": 4,
    "inline_expressions": 3,
    "block_expressions": 1,
    "rendered": 4,
    "fallbacks": 0,
    "unsupported": []
  }
}
```

Для ошибки указывать:

- formula index;
- delimiter;
- source page;
- source element;
- source position;
- backend error.

---

## 38. Тесты блока 3

Добавить:

```text
test_latex_parser.py
test_latex_renderer.py
test_latex_layout.py
test_latex_pipeline.py
```

Обязательные тесты:

1. `$x^2$`.
2. `\(x_1 + x_2\)`.
3. `$$\frac{a}{b}$$`.
4. `\[\sqrt{x}\]`.
5. Greek letters.
6. Sum/integral.
7. Escaped `\$`.
8. Незакрытый delimiter.
9. Пустая formula.
10. Expression length limit.
11. Inline formula между словами.
12. Inline formula переносится целиком.
13. Высокая formula увеличивает line height.
14. Block formula центрируется.
15. Block formula переносится на следующую page.
16. Formula strokes есть в preview.
17. Formula strokes есть в paths.
18. Formula strokes есть в G-code.
19. Unsupported command даёт понятную ошибку.
20. `--latex off` детерминирован.
21. Нет subprocess/shell.
22. G-code безопасен.

## Критерии приёмки блока 3

Файл:

```text
Формула сокращённого умножения:
$(a+b)^2 = a^2 + 2ab + b^2$.

Площадь под графиком:

$$
\int_0^1 x^2 dx = \frac{1}{3}
$$
```

должен успешно дать:

- рукописный обычный текст;
- vector formula paths;
- inline formula в строке;
- centered block formula;
- корректную pagination;
- preview, paths, G-code и report.

## Отчёт пользователю после блока 3

```markdown
## Блок 3 завершён: начальная поддержка LaTeX

### Что поддерживается
### Что пока не поддерживается
### Как реализовано
### Проверенные формулы
### Артефакты
### Тесты
### Как запустить
```

---

# 39. Финальная интеграция

## 39.1. Полный прогон

```bash
pytest
ruff check .
python -m plotter_processor --help
python -m plotter_processor run --help
```

End-to-end:

```bash
# Старый короткий TXT
python -m plotter_processor run tests/fixtures/short.txt \
  --font assets/handwriting.ttf \
  --font-mode centerline \
  --page A5 \
  --output-dir build/final-short

# DOCX с изображениями и несколькими страницами
python -m plotter_processor run tests/fixtures/mixed.docx \
  --font assets/handwriting.ttf \
  --font-mode centerline \
  --images auto \
  --paginate \
  --page-pause-seconds 90 \
  --page A5 \
  --output-dir build/final-docx

# Документ с формулами
python -m plotter_processor run tests/fixtures/latex.txt \
  --font assets/handwriting.ttf \
  --font-mode centerline \
  --latex mathtext \
  --paginate \
  --page A5 \
  --output-dir build/final-latex
```

## 39.2. Проверить preview вручную

- текст внутри полей;
- картинки не перевёрнуты;
- пропорции сохранены;
- нет чрезмерного числа штрихов;
- независимые линии не соединены через пустое место;
- page numbers снизу по центру;
- footer не пересекается с content;
- formulas читаемы и не обрезаны.

## 39.3. Проверить G-code автоматически

```text
M104 — отсутствует
M109 — отсутствует
M140 — отсутствует
M190 — отсутствует
E-coordinate — отсутствует
G28 — отсутствует по default
M84 — один раз в конце общего G-code
G4 P90000 — page_count - 1 раз
```

Для каждой pause:

```text
pen up
→ park move
→ M400
→ G4 P90000
→ next page
```

## 39.4. Physical dry-run

1. Поднять ручку над бумагой.
2. Запустить двухстраничный G-code.
3. Проверить park corner.
4. Проверить реальные 90 секунд.
5. Убедиться, что motors не отключаются.
6. Проверить начало следующей страницы.
7. Только после этого делать тест с опущенной ручкой.

---

# 40. Финальный отчёт Codex

```markdown
# UPD_Plotter_7 завершён

## Итог блока 1
- PDF images: ...
- DOCX images: ...
- vectorization modes: ...
- limitations: ...

## Итог блока 2
- pagination: ...
- page count: ...
- numbering: ...
- park/pause: ...
- page artifacts: ...

## Итог блока 3
- LaTeX syntax: ...
- backend: ...
- limitations: ...

## Изменённые модули
- ...

## Новые тесты
- ...

## Полный прогон
- pytest: ...
- ruff: ...
- end-to-end: ...

## Безопасность G-code
- heating: отсутствует
- extrusion: отсутствует
- G28 default: отсутствует
- M84: только в конце
- page pause: 90 секунд

## Команды запуска
```bash
...
```

## Что рекомендуется для UPD_Plotter_8
- ...
```

---

# 41. Что не делать в этом обновлении

Не реализовывать сейчас:

- OCR;
- распознавание текста внутри картинок;
- pixel-perfect PDF layout;
- полный Word layout engine;
- полную поддержку floating wrapping;
- разрезание картинки между страницами;
- цветную многоручечную печать;
- hatch-заливку;
- полный TeX Live;
- TikZ;
- user LaTeX packages;
- восстановление LaTeX из PDF;
- идеальный OMML converter;
- автоматическую физическую смену бумаги.

Такие случаи нужно либо детерминированно упростить с warning, либо завершить понятной ошибкой.

---

# 42. Ожидаемый конечный результат

После выполнения UPD_Plotter_7 пользователь передаёт PDF или DOCX с текстом, картинками, большим объёмом и базовыми LaTeX-формулами.

Программа:

1. извлекает текст и изображения;
2. сохраняет порядок элементов;
3. переводит изображения в плоттерные линии;
4. раскладывает контент на A4/A5;
5. создаёт нужное число страниц;
6. добавляет номер снизу по центру;
7. создаёт preview и paths каждой страницы;
8. создаёт отдельный G-code каждой страницы;
9. создаёт единый G-code задания;
10. после каждой страницы поднимает перо;
11. паркуется в настроенном углу;
12. ждёт 90 секунд;
13. продолжает следующую страницу;
14. переводит базовые LaTeX-формулы в vector paths;
15. не использует нагрев и экструзию;
16. сохраняет подробный report;
17. отчитывается пользователю после каждого блока.
