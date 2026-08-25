PYTHON ?= .venv/bin/python
INPUT ?= examples/input.txt
FONT ?= assets/handwriting.ttf
PAGE ?= A5
SIZE ?= normal
BUILD ?= build
CACHE_DIR ?= 1-font-cache
FONT_CACHE_DIR ?= $(CACHE_DIR)
FONT_CACHE_CORPUS ?= assets/font-cache-corpus.txt
LAYOUT_CONFIG ?= configs/layout.yaml

PROFILE ?= safe

.PHONY: install test lint run demo extract calibrate benchmark benchmark-pipeline smoke audit \
	audit-benchmark clean cache-clean font-cache-rebuild cache-rebuild font-cache-status

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

run:
	$(PYTHON) -m plotter_processor run "$(INPUT)" \
		--font "$(FONT)" \
		--page "$(PAGE)" \
		--size "$(SIZE)" \
		--layout-config "$(LAYOUT_CONFIG)" \
		--machine-config configs/machine.yaml \
		--output-dir "$(BUILD)"

demo: run

extract:
	$(PYTHON) -m plotter_processor extract "$(INPUT)" \
		--output "$(BUILD)/extracted.txt"

calibrate:
	$(PYTHON) -m plotter_processor calibrate \
		--machine-config configs/machine.yaml \
		--page "$(PAGE)" \
		--output "$(BUILD)/calibration.gcode"

benchmark:
	$(PYTHON) -m plotter_processor run examples/benchmark_50_words.txt \
		--font "$(FONT)" --font-mode centerline --page A5 --size normal \
		--motion-profile "$(PROFILE)" --output-dir "$(BUILD)/benchmark-$(PROFILE)"

benchmark-pipeline:
	$(PYTHON) tools/benchmark_conversion.py examples/benchmark_50_words.txt \
		--font assets/1.ttf --font-mode centerline --connections safe \
		--workers 1 --warm-runs 3 \
		--output "$(BUILD)/benchmark-pipeline.json"

audit:
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) smoke
	$(MAKE) audit-benchmark
	@echo "Audit passed: lint, tests, centerline smoke, determinism, G-code safety, cache checks and benchmark."

audit-benchmark:
	$(PYTHON) tools/benchmark_conversion.py examples/benchmark_50_words.txt \
		--font assets/1.ttf --font-mode centerline --connections safe \
		--workers 1 --warm-only --warmup-runs 1 --warm-runs 2 --verify \
		--output "$(BUILD)/audit-benchmark.json"

clean:
	rm -rf "$(BUILD)"
	mkdir -p "$(BUILD)"
	printf '\n' > "$(BUILD)/.gitkeep"

cache-clean:
	@test -n "$(CACHE_DIR)" && test "$(CACHE_DIR)" != "/"
	rm -rf "$(CACHE_DIR)"
	mkdir -p "$(FONT_CACHE_DIR)"
	@echo "Centerline cache removed. The next centerline run will be cold: $(FONT_CACHE_DIR)"

font-cache-rebuild:
	@test -f "$(FONT)" || (echo "Font not found: $(FONT)"; exit 1)
	@test -f "$(FONT_CACHE_CORPUS)" || (echo "Corpus not found: $(FONT_CACHE_CORPUS)"; exit 1)
	mkdir -p "$(BUILD)"
	$(PYTHON) -m plotter_processor compile-centerline-font "$(FONT)" \
		--text-file "$(FONT_CACHE_CORPUS)" \
		--layout-config "$(LAYOUT_CONFIG)" \
		--cache-directory "$(FONT_CACHE_DIR)" \
		--preview "$(BUILD)/font-cache-rebuild-preview.svg" \
		--force
	@echo "Rebuilt canonical centerline corpus for $(FONT) in $(FONT_CACHE_DIR)"

cache-rebuild: font-cache-rebuild

font-cache-status:
	@test -f "$(FONT)" || (echo "Font not found: $(FONT)"; exit 1)
	$(PYTHON) -m plotter_processor font-cache-info "$(FONT)" \
		--layout-config "$(LAYOUT_CONFIG)" \
		--cache-directory "$(FONT_CACHE_DIR)"
smoke:
	$(PYTHON) tools/smoke_full_pipeline.py tests/fixtures/layout/mixed_layout_demo.docx \
		--font assets/1.ttf --layout-debug
