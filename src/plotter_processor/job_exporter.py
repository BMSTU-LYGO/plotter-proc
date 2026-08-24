from __future__ import annotations

import json
from pathlib import Path

from plotter_processor.job_models import PlotterJob
from plotter_processor.schemas import JOB_SCHEMA_VERSION


def save_job_manifest(job: PlotterJob, output_path: str | Path) -> None:
    path = Path(output_path)
    single_page = len(job.pages) == 1
    preview_enabled = job.metadata.get("artifact_level") != "minimal"
    payload = {
        "format": "plotter-job",
        "version": JOB_SCHEMA_VERSION,
        "page": {
            "name": job.page_spec.name,
            "width_mm": job.page_spec.width_mm,
            "height_mm": job.page_spec.height_mm,
        },
        "page_count": len(job.pages),
        "warnings": job.warnings,
        "metadata": job.metadata,
        "pages": [
            {
                "page_index": page.page_index,
                "page_number": page.page_number,
                "source_element_ids": list(page.source_element_ids),
                "warnings": page.warnings,
                "metadata": page.metadata,
                "directory": "." if single_page else f"pages/page-{page.page_number:03d}",
                "preview": (
                    "plotter-preview.svg" if single_page
                    else f"pages/page-{page.page_number:03d}/plotter-preview.svg"
                ) if preview_enabled else None,
                "paths": (
                    "paths.json" if single_page
                    else f"pages/page-{page.page_number:03d}/paths.json"
                ),
                "gcode": (
                    "output.gcode" if single_page
                    else f"pages/page-{page.page_number:03d}/page.gcode"
                ),
                "report": "report.json" if single_page else f"pages/page-{page.page_number:03d}/report.json",
            }
            for page in job.pages
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
