# ai-office-antigravity

Два инструмента в одном репозитории:
1. **Xiaomi MiMo Code CLI** — инструкция установки + скрипт
2. **MiMo Code Telegram Bot** — AI-кодер в Telegram, задеплоенный на Vercel

---

## Часть 1 — Установка MiMo Code CLI

### Требования
- Node.js 18+
- macOS, Linux или Windows (через WSL/Git Bash)

### Установка

**macOS / Linux (одна команда):**
```bash
curl -fsSL https://mimo.xiaomi.com/install | bash
```

**Все платформы (npm):**
```bash
npm install -g @xiaomi-mimo/cli
```

**Скрипт автоустановки (этот репо):**
```bash
bash install_mimo_code.sh
```

### Запуск
```bash
mimo
```

При первом запуске выбери канал подключения:

| Вариант | Описание |
|---|---|
| MiMo Auto | Бесплатно, нулевая конфигурация, анонимно |
| Xiaomi MiMo Platform | Вход через OAuth-аккаунт Xiaomi |
| Миграция из Claude Code | Перенос существующей аутентификации |
| Пользовательский провайдер | Любой OpenAI-совместимый API |

### Расположение конфига
- Проект: `.mimocode/mimocode.json`
- Глобально: `~/.config/mimocode/mimocode.json`

### Решение проблем

**WSL — артефакты при копировании:**
```bash
sudo apt install xsel
```

**Голосовой ввод (опционально):**
```bash
# macOS
brew install sox
# Ubuntu/Debian
sudo apt install sox
```

---

## Часть 2 — MiMo Code Telegram Bot

AI-помощник по коду в Telegram на базе MiMo V2.5 Pro.

### Что умеет
- Отвечает на вопросы по коду (Python, JS, SQL и др.)
- Дебажит куски кода
- Объясняет концепции
- Отвечает на русском или английском в зависимости от твоего языка

### Деплой на Vercel

**1. Форкни репо и запушь на GitHub**

**2. Получи креденшелы**
- Telegram токен: [@BotFather](https://t.me/BotFather) → /newbot
- MiMo API ключ: [platform.xiaomimimo.com](https://platform.xiaomimimo.com)

**3. Создай проект в Vercel**
- New Project → Import this repo
- Добавь переменные окружения:
  - `TELEGRAM_BOT_TOKEN` — токен от BotFather
  - `MIMO_API_KEY` — ключ с платформы MiMo (начинается на `sk-`)

**4. Задеплой**

**5. Установи webhook в Telegram**
```
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<твой-vercel-домен>/api/webhook
```

### Команды бота
- `/start` — приветствие
- `/help` — список команд
- Любой текст → ответ AI-кодера

---

## Ссылки
- [MiMo Code GitHub](https://github.com/XiaomiMiMo/MiMo-Code)
- [MiMo API Platform](https://platform.xiaomimimo.com)
- [MiMo API Docs](https://mimo.mi.com/docs/en-US/tokenplan/quick-access)
