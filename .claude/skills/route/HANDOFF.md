# Технический бриф: связка «route» (Fable 5 + GPT-5.6 Sol)

## 1. Цель
Настроить и довести до рабочего состояния двухмодельный цикл разработки **`/route`**:
- **Fable 5 (Claude)** — «начальник»: ведёт интервью, пишет план, критикует, ревьюит результат. Код сам не пишет.
- **GPT-5.6 Sol (через Codex CLI)** — «исполнитель»: реализует план, вносит правки.
- Цикл крутится (план → адверсариальная критика → реализация → ревью → доработка) до одобрения Fable.

## 2. Роли и механика
- Оркестрация — на стороне Claude Code через скилл `route`.
- Делегирование исполнителю — командами вида:
  - критика плана: `codex exec --model gpt-5.6-sol "Critique this plan adversarially. Do NOT write code yet."`
  - реализация: `codex exec --model gpt-5.6-sol -s workspace-write -c model_reasoning_effort=high "Implement the plan in PLAN.md."` (флаг `-s workspace-write` обязателен — иначе исполнитель работает в режиме «только чтение» и не может писать файлы)
  - ревью: `/codex:review` (даёт плагин).

## 3. Артефакты в репозитории
- **Репозиторий:** `dmmartyshenko-rgb/ai-office-antigravity`
- **Ветка:** `claude/fable-sol-route-setup-ds26bw`
- **Файлы:**
  - `.claude/skills/route/SKILL.md` — сам скилл (петля + правила + проверка предусловий).
  - `.claude/skills/route/SETUP.md` — разовая установка (плагин + config.toml).
  - `.claude/skills/route/config.sample.toml` — готовая заготовка настроек модели.
  - `.claude/skills/route/HANDOFF.md` — этот бриф.

## 4. Среды исполнения — критично различать
| Среда | Состояние | Пригодность для запуска |
|-------|-----------|--------------------------|
| **Облачная сессия** (claude.ai/code, hostname `vm`, root) | плагин + Codex CLI + config установлены и проверены; config читается корректно | ❌ **Выход к OpenAI закрыт сетевым правилом окружения** (`HTTP CONNECT 403` на `api.openai.com`). Запускать `/route` здесь нельзя. |
| **Локальный Mac пользователя** (`E-Orlova@MacBook-Pro`, macOS, zsh; Node.js/npm есть) | целевая среда | ✅ Здесь и должен работать цикл. |

## 5. Текущий статус на Mac пользователя
Выполнено:
- ✅ `@openai/codex` (Codex CLI) установлен через npm.
- ✅ `@anthropic-ai/claude-code` установлен (после починки ошибки `ENOTEMPTY` — удалили остаточную папку в `/usr/local/lib/node_modules/@anthropic-ai/` и переустановили).
- ✅ Claude Code запущен, вход в аккаунт Anthropic выполнен.
- ✅ Источник плагина добавлен: `openai/codex-plugin-cc` (marketplace `openai-codex`).
- ✅ Плагин установлен и активен: `codex@openai-codex` v1.0.6.

Осталось (3 шага, все на Mac):
1. **Создать `~/.codex/config.toml`** (см. §6).
2. **Войти в OpenAI:** `codex login` (интерактивно, через браузер), проверить `codex login status`.
3. **Проверить связь:** `codex exec --model gpt-5.6-sol --skip-git-repo-check "ping"`.

Далее — запуск `/route` внутри репозитория `ai-office-antigravity` (там скилл подхватится автоматически).

## 6. Точная конфигурация `~/.codex/config.toml`
```toml
model = "gpt-5.6-sol"

[profiles.reviewer]
model = "gpt-5.6-sol"
model_reasoning_effort = "xhigh"
```
Правило: **не удалять** существующие записи (marketplaces / plugins / projects), если файл уже есть — только добавить эти ключи; предварительно сделать резервную копию.

## 7. Готовый блок для терминала Mac (один кусок)
```bash
mkdir -p ~/.codex
[ -f ~/.codex/config.toml ] && cp ~/.codex/config.toml ~/.codex/config.toml.bak.$(date +%s) && echo "backup сохранён"
cat > ~/.codex/config.toml <<'EOF'
model = "gpt-5.6-sol"

[profiles.reviewer]
model = "gpt-5.6-sol"
model_reasoning_effort = "xhigh"
EOF
codex login
codex login status
codex exec --model gpt-5.6-sol --skip-git-repo-check "ping"
```

## 8. Известные препятствия и риски
1. **Доступ к OpenAI обязателен.** Без выполненного `codex login` (или ключа `OPENAI_API_KEY`) цикл остановится на шаге размышления исполнителя.
2. **Имя модели `gpt-5.6-sol` не подтверждено.** Взято из исходной инструкции; возможно внутреннее/предварительное. Если OpenAI ответит «нет такой модели» — заменить значение `model` в config.toml на доступное пользователю имя.
3. **Сетевые правила.** В облачной среде OpenAI недоступен by design; воспроизводить и запускать `/route` только на локальной машине с обычным интернетом (без блокирующего VPN/прокси — на этапе установки уже ловили `ConnectionRefused`).
4. **Плагин от стороннего вендора.** `codex@openai-codex` — OpenAI, не Anthropic; стандартное предупреждение о доверии принято осознанно.
5. **Ограничение автоматизации.** Ни облачная сессия, ни Cowork не могут удалённо управлять терминалом Mac пользователя — интерактивные шаги (`codex login` в браузере, ввод команд) выполняет пользователь.

## 9. Definition of Done (критерий готовности)
- `codex login status` → «logged in».
- `codex exec --model gpt-5.6-sol "ping"` → осмысленный ответ (не 403, не «model not found»).
- В окне Claude Code внутри репозитория команда `/route` запускает цикл: интервью → `PLAN.md` → критика → реализация исполнителем с `-s workspace-write` → ревью → доработка до одобрения.

## 10. Что нужно от исполнителя Cowork
- Провести пользователя (или выполнить, где возможно) шаги §5.1–§5.3 и §7.
- При ошибке модели — скорректировать `model` в config.toml (§8.2).
- Подтвердить DoD (§9) и запустить `/route` на первой реальной задаче пользователя.
