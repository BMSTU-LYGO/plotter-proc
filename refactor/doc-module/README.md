# Document module migration

This directory contains the isolated C++20 document pipeline migration.
The existing Python pipeline remains the reference implementation until
stage and end-to-end parity are measured on the golden corpus.

The first milestone covers canonical golden captures, a buildable C++ module
skeleton, explicit measurement units, and the four stage data contracts:
`DocumentModel`, `LayoutModel`, `PathDocument`, and `PlotterJob`.

See `CPP_DOCUMENT_PIPE_REWRITE.md` at the repository root for the migration
sequence and parity gates.
