# Centerline visual regression

Generate the comparison with `assets/1.ttf`:

```bash
plotter-processor run examples/input.txt --font assets/1.ttf \
  --font-mode outline --output-dir build/visual-outline
plotter-processor run examples/input.txt --font assets/1.ttf \
  --font-mode centerline --output-dir build/visual-centerline
```

Inspect `font-preview.svg`, `centerline-font-preview.svg`,
`plotter-preview.svg`, dots/marks, loops, junctions and baseline alignment.
Generated artifacts stay under ignored `build/`; tests do not depend on a
system font or byte-fragile SVG snapshots.
