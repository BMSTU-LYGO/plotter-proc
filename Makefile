.DEFAULT_GOAL := help

NAME := $(word 2,$(MAKECMDGOALS))

# Сборка напрямую компилятором C++: CMake для make font/doc не нужен.
ifeq ($(origin CXX),default)
CXX := $(shell command -v g++ || command -v c++ || command -v gcc)
endif
CPPFLAGS += -Imodules/fontc/include -Imodules/document/include -Ithird_party/freetype2
CXXFLAGS += -std=c++20 -O2 -pthread -MMD -MP
LDLIBS += -l:libfreetype.so.6 -lz -pthread -lstdc++
JOBS ?= 2
CHARS ?= examples/centerline_glyph_corpus.txt
# For font 1, 9.76 mm per em makes an ordinary capital about 7 mm high.
SIZE_MM ?= 9.76
JOIN_WORDS ?= 1

FONT_SOURCES := $(wildcard modules/fontc/src/*.cpp)
DOC_SOURCES := $(wildcard modules/document/src/*.cpp) modules/document/tools/doc_run.cpp
DOC_FONT_SOURCES := modules/fontc/src/compiled_font.cpp modules/fontc/src/pfc.cpp modules/fontc/src/runtime_font.cpp
FONT_OBJECTS := $(patsubst %.cpp,build/obj/%.o,$(FONT_SOURCES))
DOC_OBJECTS := $(patsubst %.cpp,build/obj/%.o,$(DOC_SOURCES) $(DOC_FONT_SOURCES))
ALL_OBJECTS := $(sort $(FONT_OBJECTS) $(DOC_OBJECTS))

build/obj/%.o: %.cpp Makefile
	@mkdir -p "$(@D)"
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c "$<" -o "$@"

build/modules/fontc/fontc: $(FONT_OBJECTS)
	@mkdir -p "$(@D)"
	$(CXX) $^ -o "$@" $(LDLIBS)

build/modules/document/plotter-doc: $(DOC_OBJECTS)
	@mkdir -p "$(@D)"
	$(CXX) $^ -o "$@" $(LDLIBS)

-include $(ALL_OBJECTS:.o=.d)

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
	@echo 'Для формата А5: make doc имя PAGE=A5'
	@echo 'С предпросмотром: make doc имя PREVIEW=1'
	@echo 'Размер букв: make doc имя SIZE_MM=8'
	@echo 'Без соединения слов: make doc имя JOIN_WORDS=0'

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
	[ -f "$(CHARS)" ] || { echo "Список символов $(CHARS) не найден" >&2; exit 2; }; \
	case "$$input" in *.ttf|*.otf) ;; *) echo 'Нужен файл .ttf или .otf' >&2; exit 2;; esac; \
	stem=$${input##*/}; stem=$${stem%.*}; \
	output="font-cache/$$stem/$$stem.pfc"; \
	$(MAKE) --no-print-directory -j$(JOBS) build/modules/fontc/fontc; \
	mkdir -p "font-cache/$$stem"; \
	build/modules/fontc/fontc "$$input" --chars-file "$(CHARS)" --output "$$output" --force; \
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
	preview='$(or $(PREVIEW),0)'; \
	case "$$preview" in 0) preview_arg='--no-preview';; 1) preview_arg='';; *) echo 'PREVIEW должен быть 0 или 1' >&2; exit 2;; esac; \
	join_words='$(JOIN_WORDS)'; \
	case "$$join_words" in 0) join_arg='';; 1) join_arg='--join-words';; *) echo 'JOIN_WORDS должен быть 0 или 1' >&2; exit 2;; esac; \
	page='$(or $(PAGE),A4)'; \
	case "$$page" in A5) machine='configs/machine.yaml';; A4) machine='configs/machine-a4.yaml';; *) echo 'PAGE должен быть A5 или A4' >&2; exit 2;; esac; \
	$(MAKE) --no-print-directory -j$(JOBS) build/modules/document/plotter-doc; \
	build/modules/document/plotter-doc \
	  --input "$$input" --output "build/$$stem" \
	  --font "$$font_file" --font-mode centerline --page "$$page" \
	  --layout-config configs/layout.yaml --machine-config "$$machine" \
	  --artifact-level normal --size-mm "$(SIZE_MM)" --simplify --optimize $$join_arg $$preview_arg; \
	if [ "$$preview" = 1 ]; then echo "Предпросмотр: build/$$stem/pages/page-001/plotter-preview.svg"; fi
