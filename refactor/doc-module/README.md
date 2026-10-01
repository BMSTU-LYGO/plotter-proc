# C++ document module migration

This directory contains the isolated C++20 rewrite. The existing Python pipeline remains available and is the reference for parity checks. The new CLI is `plotter-doc`, built from `cpp/tools/doc_run.cpp`; `plotter-doc-import` emits versioned document IR without running Python.

## Implemented

- Frozen Python golden corpus for TXT, Markdown, DOCX, PDF and SVG. `python3 tools/compare_cpp_import.py <plotter-doc-import>` checks page and element identity, text, source order, and SVG contour geometry. All five current golden imports pass this structural check.
- C++ source adapters, typed models, versioned JSON stage IR, YAML page and machine profile loader, path validation, centerline PFC font layout, basic pagination and page numbers, vector path assembly, path optimization and simplification, multipage G-code with analyzer, and report/artifact writing.
- A native orchestrator for supported content. It reads a source, lays out text with a precompiled `.pfc` font, builds paths, validates generated G-code and writes artifacts. An SVG and a synthetic PFC text document pass focused end-to-end smoke checks.

## Remaining parity work

The current native runtime is experimental. It does not yet draw raster images, tables or math, and it cannot reproduce the old outline font mode or rich document layout modes. It reports an error for these contents so a partial drawing is not treated as a complete result. Typed IR decoding, production binary caches, handwriting transforms, thread pool, full end-to-end parity and performance gates are also pending. The PDF adapter uses Poppler command-line tools (`pdftotext`, `pdftocairo`) for native import; it does not invoke the Python pipeline.

The old Python implementation has not been changed or removed. See `CPP_DOCUMENT_PIPE_REWRITE.md` at the repository root for the complete migration criteria.
