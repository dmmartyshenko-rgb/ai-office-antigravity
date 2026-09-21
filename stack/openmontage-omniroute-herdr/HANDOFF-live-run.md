# Хендофф: доведение живого прогона стека OpenMontage × OmniRoute × Herdr

> Этот файл — бриф для Claude Code, запущенного в терминале на Mac пользователя,
> чтобы завершить живой прогон. Ты (Claude Code) работаешь на своей обычной
> авторизации (НЕ через OmniRoute) — ты оркестратор: управляешь herdr/omniroute и
> проверяешь результат. Выполняй шаги по порядку, проверяй вывод, при отклонениях
> действуй по разделу «Грабли», в конце отчитайся коротко с доказательствами.

## Что уже сделано (состояние на момент передачи)

- Репозиторий: `~/ai-office-antigravity`, ветка `claude/openmontage-omniroute-herdr-setup-6p1cw5`.
  Обвязка: `~/ai-office-antigravity/stack/openmontage-omniroute-herdr/`.
- Рабочие клоны (вне репо): `~/ai-office-stack/repos/{OpenMontage,OmniRoute,herdr}`.
- Установлено и проверено:
  - **herdr 0.9.1** — бинарь в `~/.local/bin/herdr` (ставили официальным install.sh; brew-сборку из исходников НЕ используем — она компилирует LLVM полчаса).
  - **omniroute 3.8.50** — глобально (`npm i -g omniroute`).
  - **OpenMontage** — `.venv` (Python 3.10 через uv), зависимости + remotion-composer, `ffmpeg` есть, HyperFrames runtime доступен. `.env` создан.
- **OmniRoute хранилище пересоздано**: старый ключ шифрования был утерян → старая
  база отодвинута в `~/.omniroute/reset-backup-*`, в `~/.omniroute/.env` записан
  новый `STORAGE_ENCRYPTION_KEY`. Добавлен провайдер **stack-groq** (ключ Groq).
- **Труба проверена**: прямой запрос через роутер вернул ответ на модели
  `openai/gpt-oss-120b` (Groq). Сессия OpenMontage поднималась в Herdr (workspace
  `w1`, панель `w1:p1`), Claude Code через `omniroute run claude` стартовал.

## Единственная незакрытая проблема

Комбо `auto` при запросе от Claude Code уходит в бесплатный OpenCode и получает
**403** (`OpenCode's free tier can only be used from within OpenCode`), до Groq не
доходит. **Решение: прибить модель к `openai/gpt-oss-120b`** (Groq, уже доказанно
рабочая) вместо `auto`.

## Цель

OpenMontage-сессия: Claude Code, идущий через OmniRoute→Groq на модели
`openai/gpt-oss-120b`, отвечает на бриф внутри фоновой панели Herdr — без 403.

## Шаги (выполняй и проверяй вывод каждого)

```sh
cd ~/ai-office-antigravity/stack/openmontage-omniroute-herdr

# 1. Прибить модель к рабочей Groq-модели
sed -i '' 's|^OM_MODEL=.*|OM_MODEL="openai/gpt-oss-120b"|' .env
grep '^OM_MODEL' .env    # ждём: OM_MODEL="openai/gpt-oss-120b"

# 2. Роутер + провайдер + прямая проверка модели
bash scripts/03-omniroute-up.sh
omniroute providers list    # ждём stack-groq (active)
curl -sS --max-time 60 http://localhost:20128/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-oss-120b","messages":[{"role":"user","content":"say OK"}]}'; echo
#   ждём JSON с ответом модели (НЕ 403). Если 403/ошибка — см. «Грабли».

# 3. Перезапустить сессию OpenMontage в Herdr на прибитой модели
bash scripts/start-openmontage-session.sh stop
bash scripts/start-openmontage-session.sh start
#   запомни id панели из вывода (обычно w1:p1)

# 4. Снять первый экран панели; если Claude Code спрашивает про доверие к папке —
#    выбрать "Yes, I trust this folder"
herdr pane read w1:p1 --lines 40
#   если виден вопрос про доверие:  herdr pane send-keys w1:p1 Down Enter ; sleep 2 ; herdr pane read w1:p1 --lines 40
#   ждём основной интерфейс Claude Code с полем ввода ❯

# 5. Боевой бриф в OpenMontage и чтение ответа
herdr agent prompt w1:p1 "Прочитай AGENT_GUIDE.md в этом репозитории и кратко, 5-7 строк, перечисли доступные пайплайны и с чего начать короткий ролик. Только план, ничего не запускай и не создавай." --wait --until idle --timeout 300000
herdr agent read w1:p1 --lines 60
#   УСПЕХ = связный план по пайплайнам OpenMontage, БЕЗ 403.
```

## Грабли и как реагировать

- **Снова 403 про OpenCode** на шаге 2/5 → модель не прибилась. Проверь `grep '^OM_MODEL' .env`
  и что `start-openmontage-session.sh` запустил `omniroute run claude --model openai/gpt-oss-120b`
  (посмотри `herdr pane read w1:p1`). При нужде запусти в панели вручную:
  `herdr pane send-text w1:p1 "omniroute run claude --model openai/gpt-oss-120b --port 20128"; herdr pane send-keys w1:p1 Enter`.
- **Groq вернул ошибку квоты/модели** → у stack-groq другой каталог. Возьми доступную
  модель из `omniroute models list | grep -i groq` (или `gpt-oss`), подставь её в `OM_MODEL`
  и в curl. Как крайность — добавь Anthropic-ключ: `omniroute providers add anthropic --credential-env ANTHROPIC_API_KEY` и прибей `anthropic/claude-sonnet-4`.
- **Баннер «Incompatible Node.js Version»** (node 22.22.1 < 22.22.2) — не блокер,
  роутер работает. Если захочешь убрать: `brew upgrade node` (или поставить node@24) и перезапустить роутер.
- **Дашборд просит пароль, CHANGEME не подходит** — дашборд для этой задачи НЕ нужен
  (всё через CLI). Если нужен — `omniroute-reset-password`.
- **herdr не найден** — он в `~/.local/bin`; добавь в PATH (`export PATH="$HOME/.local/bin:$PATH"`).
- **Ключи клавиш в herdr**: подтверждения — `herdr pane send-keys <pane> Down Enter`;
  текст — `herdr pane send-text <pane> "..."` затем `... send-keys <pane> Enter`.

## Полезное

- Статус: `bash scripts/start-openmontage-session.sh status` и `bash scripts/doctor.sh`.
- Посмотреть сессию глазами: `herdr` (детач — `ctrl+b q`).
- Остановить всё: `bash scripts/start-openmontage-session.sh stop`.
- Когда закончишь — обнови журнал `~/ai-office-antigravity/map/journal/montage-stack.md`
  (что получилось, на какой модели, был ли 403) и, если репо чистое, закоммить.

## Отчёт в конце

Коротко и с доказательствами: заработало ли (да/нет), на какой модели ответил агент,
не было ли 403, id панели, и что осталось (например «Groq слабоват для агентной работы,
для боевого качества добавить Anthropic-ключ»).
