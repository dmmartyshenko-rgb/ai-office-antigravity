# claudex-loop — перекрёстная связка Claude ↔ Codex

## Статус
Пауза (Claude-сторона установлена и проверена; ждёт установки и логина Codex CLI
у пользователя для перекрёстной половины). Обновлено: 2026-09-21.

## Ветка
`claude/wonderful-cori-3szmfw`.

## Цель
Рабочая связка Claudex Loop в едином сеансе CLI: host-провайдер планирует и
координирует, второй независимо ревьюит план и инспектирует код (кто строил —
не оценивает сам). Полный цикл: recon → план → ревью → сборка → инспекция.

## Артефакты
- `tools/claudex-loop/` — завендоренный исходник chaseai-yt/claudex-loop
  (commit в `.source-commit`; обновление — `git pull` апстрима + перекопировать скилы).
- `.claude/skills/{claudex-loop,claudex-route,codex-build,codex-review}/` — скилы,
  доступны как `/claudex-loop` в сеансе Claude Code с этим репо.
- `scripts/claudex/claudex.config.sh` — env-дефолты связки (Controls апстрима).
- `scripts/claudex/claudex-pair.sh` — полный цикл (парная разработка).
- `scripts/claudex/claudex-review.sh` — `mode=review` (перекрёстное ревью без сборки).
- `scripts/claudex/claudex-doctor.sh` — диагностика окружения.
- `scripts/claudex/README.md` — как пользоваться + границы.

## Следующий шаг
Пользователь ставит и логинит Codex CLI (`npm i -g @openai/codex`, `codex login`),
затем `scripts/claudex/claudex-doctor.sh` должен дать `FAIL=0` без WARN. После —
первый боевой прогон `scripts/claudex/claudex-pair.sh` на реальной задаче.

## Риски / открытые вопросы
- В окружении настройки Codex CLI не было (`which codex` пусто) — перекрёстная
  половина не проверена вживую. Апстрим-тесты 23/23 и `validate.py` пройдены,
  preflight лаунчеров проверен.
- Тот же облачный блокер, что у route-loop: Codex ходит на `api.openai.com` и
  `auth.openai.com`; в облачном окружении они были закрыты egress-прокси
  (CONNECT 403). Реальные пути: локальная машина, либо открыть сетевую политику
  окружения + передать логин/токен. Из сессии блокер не снять.
- Отношение к route-loop: оба про пару Claude + модель OpenAI, но route-loop —
  своя петля (Fable-босс + Sol-исполнитель) на `.claude/skills/route/`;
  claudex-loop — сторонний скил-набор. Не дублировать, не сливать.
