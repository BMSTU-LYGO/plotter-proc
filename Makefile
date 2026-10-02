.DEFAULT_GOAL := help

NAME := $(word 2,$(MAKECMDGOALS))

# `make font имя` и `make doc имя`: второй аргумент Make считает целью.
ifneq ($(filter font doc,$(firstword $(MAKECMDGOALS))),)
ifneq ($(strip $(NAME)),)
.PHONY: $(NAME)
$(NAME):
	@:
endif
endif

.PHONY: help font doc

help:
	@echo 'Шрифт:     make font имя[.ttf|.otf]'
	@echo 'Документ:  make doc имя[.md|.txt|.docx|.svg]'
	@echo 'Если шрифтов несколько: make doc имя FONT=имя_шрифта'
	@echo 'Для формата А4: make doc имя PAGE=A4'

font:
	@set -eu; \
	[ "$(words $(MAKECMDGOALS))" -eq 2 ] || { echo 'Укажите одно имя: make font имя' >&2; exit 2; }; \
	name='$(NAME)'; \
	case "$$name" in ''|*/*|.*) echo 'Укажите только имя файла из fonts/' >&2; exit 2;; esac; \
	input=''; \
	for candidate in "fonts/$$name" "fonts/$$name.ttf" "fonts/$$name.otf"; do \
	  if [ -f "$$candidate" ]; then input="$$candidate"; break; fi; \
	done; \
	[ -n "$$input" ] || { echo "Шрифт $$name не найден в fonts/" >&2; exit 2; }; \
	case "$$input" in *.ttf|*.otf) ;; *) echo 'Нужен файл .ttf или .otf' >&2; exit 2;; esac; \
	stem=$${input##*/}; stem=$${stem%.*}; \
	output="font-cache/$$stem/$$stem.pfc"; \
	cmake -S . -B build -DBUILD_TESTING=OFF; \
	cmake --build build --target fontc -j; \
	mkdir -p "font-cache/$$stem"; \
	build/modules/fontc/fontc "$$input" --chars-file assets/font-cache-corpus.txt --output "$$output" --force; \
	echo "Готово: $$output"

doc:
	@set -eu; \
	[ "$(words $(MAKECMDGOALS))" -eq 2 ] || { echo 'Укажите одно имя: make doc имя' >&2; exit 2; }; \
	name='$(NAME)'; \
	case "$$name" in ''|*/*|.*) echo 'Укажите только имя файла из docs/' >&2; exit 2;; esac; \
	input=''; \
	for candidate in "docs/$$name" "docs/$$name.md" "docs/$$name.txt" "docs/$$name.docx" "docs/$$name.svg"; do \
	  if [ -f "$$candidate" ]; then input="$$candidate"; break; fi; \
	done; \
	[ -n "$$input" ] || { echo "Документ $$name не найден в docs/" >&2; exit 2; }; \
	case "$$input" in *.md|*.txt|*.docx|*.svg) ;; *) echo 'Нужен файл .md, .txt, .docx или .svg' >&2; exit 2;; esac; \
	stem=$${input##*/}; stem=$${stem%.*}; \
	font_name='$(FONT)'; \
	if [ -n "$$font_name" ]; then \
	  case "$$font_name" in */*|.*) echo 'FONT должен быть именем шрифта' >&2; exit 2;; esac; \
	  case "$$font_name" in *.ttf|*.otf) font_name=$${font_name%.*};; esac; \
	  font_file="font-cache/$$font_name/$$font_name.pfc"; \
	  [ -f "$$font_file" ] || { echo "Сначала выполните: make font $$font_name" >&2; exit 2; }; \
	else \
	  set -- font-cache/*/*.pfc; \
	  [ -f "$$1" ] || { echo 'Сначала выполните: make font имя_шрифта' >&2; exit 2; }; \
	  [ "$$#" -eq 1 ] || { echo 'Шрифтов несколько: укажите FONT=имя_шрифта' >&2; exit 2; }; \
	  font_file="$$1"; \
	fi; \
	page='$(or $(PAGE),A5)'; \
	case "$$page" in A5) machine='configs/machine.yaml';; A4) machine='modules/document/fixtures/machine-a4.yaml';; *) echo 'PAGE должен быть A5 или A4' >&2; exit 2;; esac; \
	cmake -S . -B build -DBUILD_TESTING=OFF; \
	cmake --build build --target plotter_doc_cli -j; \
	build/modules/document/plotter-doc \
	  --input "$$input" --output "build/$$stem" \
	  --font "$$font_file" --font-mode centerline --page "$$page" \
	  --layout-config configs/layout.yaml --machine-config "$$machine" \
	  --artifact-level normal; \
	echo "Предпросмотр: build/$$stem/pages/page-001/plotter-preview.svg"
