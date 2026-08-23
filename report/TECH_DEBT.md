# Технический долг — 2026-08-23

Ниже только подтверждённые повторным аудитом ограничения. Исправления в этом
проходе не вносились: задача была очистить отчёт и заново оценить состояние.

## P1 — cold centerline compilation непрактично долгая

Последняя попытка полного cold compile на временном cache не завершила
`font_compile` за 13+ минут. Warm cache валиден и даёт 122 hits / 0 misses, но
первый запуск на новой машине остаётся операционным риском.

Предлагаемое закрытие: профилировать cold glyph compilation; компилировать
фактически используемое подмножество инкрементально; добавить ограниченный
cold benchmark в CI с явным бюджетом времени и без удаления canonical cache.

## P1 — PDF semantic reconstruction остаётся эвристической

Оба PDF режима завершаются, но дают по 40 предупреждений о low-confidence math
candidates и rasterized complex drawings. Preserve также сохраняет
`1,634.989986 mm²` исходных visual overlaps; reflow устраняет их.

Предлагаемое закрытие: отдельный размеченный PDF corpus, precision/recall для
math detection, классификация complex drawings и визуальные golden tests для
preserve/reflow. Наложения preserve не следует автоматически считать багом.

## P2 — горячие стадии занимают большую часть warm runtime

На полностью прогретом run 2 handwriting занимает `27.754 s`, simplification
`20.124 s`, build_paths `8.625 s` при общем wall `61.858 s`. Первые две стадии
составляют около 77% wall time.

Предлагаемое закрытие: per-page flame/profile data, устранение повторной
обработки неизменившихся paths, затем benchmark-gate с проверкой идентичности
geometry и допустимого отклонения не более 0.06 mm.

## P2 — paginator остаётся монолитным

`document_paginator.py` содержит 1,972 строки; далее идут `pipeline.py` (935),
`handwriting.py` (847) и `docx_document_reader.py` (757). Ранее вынесенная
graphic placement уменьшила связанность, но page state, text, table, math и
debug orchestration всё ещё сосредоточены в paginator.

Предлагаемое закрытие: извлекать по одному responsibility за изменение,
сохраняя byte-identical paths/preview/G-code и полный gate после каждого шага.

## P2 — safe/aggressive corpus не показывает геометрическую границу

На сохранённом corpus оба режима дают 105/510 соединений и одинаковую
геометрию, хотя distribution причин отклонения различается. Граница поведения
есть в targeted unit fixture, но не видна на пользовательском audit corpus.

Предлагаемое закрытие: добавить короткие реальные слова с gap/tangent значениями
между safe и aggressive thresholds и закрепить разные output hashes.

## P2 — semantic duplicate suppression не измеряется

`duplicate_primitives_suppressed` честно остаётся `null` с
`measured=false`; semantic conflict считает только точное совпадение geometry
после округления до `1e-6`. Near-overlap отдельной метрикой не покрыт.

Предлагаемое закрытие: определить контракт duplicate/near-duplicate, добавить
измеряемый suppression pass и fixtures, не смешивая его с table shared-border
suppression.

## P3 — аудит пока не оформлен одной штатной командой

Матрица воспроизводима по `commands.log`, но запуск, агрегация, safety scan и
удаление временных outputs выполняются отдельными командами. Старый audit
накапливал 723 MB и 689 tracked files.

Предлагаемое закрытие: штатная команда `make audit` с temporary output root,
компактной JSON-сводкой, хешами и автоматическим cleanup; тяжёлые outputs
публиковать только как CI artifacts с retention policy.

## P3 — ограничения форматов и provenance

Поддержка LaTeX/OMML не является полной; nested DOCX tables и некоторые tab
leader/layout случаи остаются ограниченными. Для extracted assets стабилен
logical URI, но внешний `source_path` намеренно сохраняет пользовательский путь
и может отличаться между машинами. `gcode` subcommand не обязан быть
byte-identical с полным pipeline без отсутствующих page/job metadata.

Предлагаемое закрытие: документировать поддерживаемое подмножество как contract
tests и расширять его только отдельными fixtures, не скрывая fallback.

## Интеграционный риск

Рабочее дерево содержит большой незакоммиченный набор изменений блоков 2–8.
Он прошёл полный gate, но остаётся сложным для review/bisect до разбиения на
логические commits. Cleanup отчёта не изменял этот production diff.
