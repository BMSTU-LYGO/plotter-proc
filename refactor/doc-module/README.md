# C++ document module migration

This directory contains the isolated C++20 rewrite. The existing Python pipeline remains available as the parity reference. The native `plotter-doc` CLI is built from `cpp/tools/doc_run.cpp`; `plotter-doc-import` emits versioned document IR.

## Available now

- TXT, Markdown, DOCX, PDF and SVG import adapters. The five frozen import cases pass `tools/compare_cpp_import.py` for pages, element IDs/types/order, text and SVG geometry.
- Centerline rendering from precompiled `.pfc` fonts and true TTF/OTF outline rendering through FreeType. The vendored FreeType headers retain their upstream license at `vendor/freetype2/COPYRIGHT.debian`; a compatible runtime library is still required.
- Basic text layout, paragraph indents, tabs, line spacing, underlining, strikethrough, pagination and page numbers; vector paths; PNG dark-pixel runs; table borders and simple PFC cell text; linear math glyphs; source-page preserve/contain/reflow transforms; deterministic handwriting variation; geometry optimization and simplification.
- YAML page/machine profiles, keep-out and workspace preflight, multipage G-code generation and analysis, typed direct-Document pipeline entry, reports and artifact writing.

## Remaining parity work

The native runtime is experimental. Raster output is currently PNG scanline paths, not the Python image vectorizer. Table cell text and math cover simple linear content; bold/italic DOCX styling, complex formulas, anchored flow/hybrid layout, and exact Python glyph positioning still need work. A versioned binary stage-cache store and fixed thread pool are present as isolated libraries, but are not yet wired into the production pipeline. Typed IR decoding, full end-to-end parity and performance gates are pending. Unsupported content returns an explicit error instead of a partial drawing. PDF import currently invokes Poppler command-line tools, not Python.

The old Python implementation has not been changed or removed. The complete migration criteria are in `CPP_DOCUMENT_PIPE_REWRITE.md` at the repository root.
