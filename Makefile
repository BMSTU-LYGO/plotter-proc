PYTHON ?= .venv/bin/python
INPUT ?= examples/input.txt
FONT ?= assets/handwriting.ttf
PAGE ?= A5
SIZE ?= normal
BUILD ?= build

.PHONY: install test lint run demo extract calibrate clean

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
		--layout-config configs/layout.yaml \
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

clean:
	rm -rf "$(BUILD)"
	mkdir -p "$(BUILD)"
	touch "$(BUILD)/.gitkeep"
