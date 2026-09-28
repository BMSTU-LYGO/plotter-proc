from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from plotter_processor.config import load_yaml
from plotter_processor.document_models import SourcePage, SourceTableElement, SourceTextElement
from plotter_processor.fast_font import FastFont
from plotter_processor.fast_layout import FastLayout, FastLayoutConfig, FastLayoutResult
from plotter_processor.fast_word import WordBuilder
from plotter_processor.gcode_exporter import generate_gcode, write_gcode_atomic
from plotter_processor.structured_document_reader import read_structured_document


@dataclass(frozen=True, slots=True)
class FastPipelineResult:
    pages: int
    report_path: Path
    timings_ms: dict[str, float]
    layout: FastLayoutResult


def run_fast_pipeline(
    input_path: Path,
    cache_path: Path,
    output_dir: Path,
    *,
    machine_config_path: Path = Path("configs/machine.yaml"),
    layout_config: FastLayoutConfig = FastLayoutConfig(),
    fallback_char: str | None = "?",
    word_cache_size: int = 512,
) -> FastPipelineResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}

    started = time.perf_counter()
    document = read_structured_document(input_path, pdf_math_mode="off")
    text = _plain_text(document.pages)
    timings["text_extraction"] = _elapsed_ms(started)

    started = time.perf_counter()
    font = FastFont.load(cache_path, fallback_char=fallback_char)
    timings["font_cache_load"] = _elapsed_ms(started)

    builder = WordBuilder(font, cache_size=word_cache_size)
    started = time.perf_counter()
    laid_out = FastLayout(layout_config).layout(text, builder)
    timings["word_build_and_layout"] = _elapsed_ms(started)

    machine = load_yaml(machine_config_path)
    started = time.perf_counter()
    for index, page in enumerate(laid_out.pages, 1):
        write_gcode_atomic(
            generate_gcode(page, machine, page_number=index),
            output_dir / f"page-{index:03d}.gcode",
        )
    timings["gcode"] = _elapsed_ms(started)
    timings["total"] = sum(timings.values())

    report = {
        "pipeline": "fast-text",
        "pages": len(laid_out.pages),
        "words_total": laid_out.words_total,
        "pen_down_count": laid_out.pen_down_count,
        "pen_up_count": laid_out.pen_down_count,
        "avg_pen_down_per_word": laid_out.avg_pen_down_per_word,
        "word_cache_hits": laid_out.cache_hits,
        "word_cache_misses": laid_out.cache_misses,
        "missing_chars": sorted(laid_out.missing_chars),
        "timings_ms": timings,
    }
    report_path = output_dir / "fast-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return FastPipelineResult(len(laid_out.pages), report_path, timings, laid_out)


def _plain_text(pages: tuple[SourcePage, ...]) -> str:
    page_text: list[str] = []
    for page in pages:  # DocumentModel pages are intentionally flattened for fast mode.
        blocks: list[str] = []
        for element in page.elements:
            if isinstance(element, SourceTextElement):
                blocks.extend(element.paragraphs)
            elif isinstance(element, SourceTableElement):
                blocks.extend(
                    "\t".join(cell.paragraphs[0].text if cell.paragraphs else "" for cell in row)
                    for row in _table_rows(element)
                )
        page_text.append("\n".join(blocks))
    return "\f".join(page_text)


def _table_rows(table: SourceTableElement) -> list[list[object]]:
    rows: list[list[object]] = [[] for _ in range(table.rows)]
    for cell in table.cells:
        rows[cell.row].append(cell)
    return rows


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 3)
