# C++ document module migration

This directory contains the isolated C++20 rewrite. The existing Python pipeline remains available as the parity reference. The native `plotter-doc` CLI is built from `cpp/tools/doc_run.cpp`; `plotter-doc-import` emits versioned document IR.

## Available now

- TXT, Markdown, DOCX and SVG import adapters. The four frozen import cases pass `tools/compare_cpp_import.py` for pages, element IDs/types/order, text and SVG geometry.
- Centerline rendering from precompiled `.pfc` fonts and true TTF/OTF outline rendering through FreeType. The vendored FreeType headers retain their upstream license at `vendor/freetype2/COPYRIGHT.debian`; a compatible runtime library is still required.
- Basic text layout, paragraph indents, tabs, line spacing, underlining, strikethrough, pagination and page numbers; vector paths; bounded PNG outline tracing (legacy pixel runs remain available); table borders and simple PFC cell text; linear math glyphs; source-page preserve/contain/reflow transforms; deterministic handwriting variation; geometry optimization and simplification.
- YAML page/machine profiles, keep-out and workspace preflight, multipage G-code generation and analysis, typed direct-Document pipeline entry, reports and artifact writing.

## Remaining parity work

The native runtime is experimental. PNG outlines use deterministic binary boundary tracing, which still differs from the Python Canny/skeleton/vectorization pipeline. Table cell text and math cover simple linear content; complex formulas, anchored flow in hybrid layout, and exact Python glyph positioning still need work. The versioned binary import cache is active for asset-free documents; DOCX assets are deliberately left uncached to avoid stale paths. A fixed thread pool can process independent outline/vector pages in order via `--threads auto|N`. Full end-to-end parity and performance gates are pending. Unsupported content returns an explicit error instead of a partial drawing.

The old Python implementation has not been changed or removed. The complete migration criteria are in `CPP_DOCUMENT_PIPE_REWRITE.md` at the repository root.

## Current frozen corpus comparison

`tools/compare_cpp_python_parity.py` checks four frozen cases. Page counts and G-code safety pass in all four. TXT, Markdown, and SVG also match glyph and stroke counts. DOCX has 2049 strokes versus 2050 and matches 1197 glyphs. Exact stroke bounds and provenance still differ; raster-image parity is deferred. These are quality gaps, so the Python production path remains intact.
