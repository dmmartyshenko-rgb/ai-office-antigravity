# Журнал: harness-builder

## 2026-09-03 — Создан скил harness-builder
Контракт-спецификация «Harness Engineer» оформлена как скил среды
`.claude/skills/harness-builder/SKILL.md` (по конвенции репозитория, а не
`.claudecode/skills/*.md` из исходного текста). Содержание сохранено: 4 слоя
защиты, 6 столпов (Constrain / Inform / Verify / Correct / State & Memory /
Safety), 4-шаговый протокол, шаблон SafeAgentOrchestrator, few-shot примеры.
Отличия от исходника: модель в шаблоне обновлена с устаревшей
`claude-3-5-sonnet` на `claude-sonnet-5`; добавлен абзац о разграничении
с Hermes (процессный харнес vs харнес-код).
