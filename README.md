# ai-office-antigravity

Два инструмента в одном репо. Оба бесплатные.

1. **Xiaomi MiMo Code CLI** — инструкция установки + скрипт
2. **MiMo Code Telegram Bot** — AI-кодер в Telegram, задеплоенный на Vercel

---

## Часть 1 — MiMo Code CLI (бесплатно)

### Требования
- Node.js 18+
- macOS, Linux или Windows (через WSL/Git Bash)

### Установка

**macOS / Linux:**
```bash
curl -fsSL https://mimo.xiaomi.com/install | bash
```

**Все платформы (npm):**
```bash
npm install -g @xiaomi-mimo/cli
```

**Скрипт (этот репо):**
```bash
bash install_mimo_code.sh
```

### Запуск
```bash
mimo
```

> При первом запуске выбери **MiMo Auto** — бесплатно, без регистрации, без ключа.

### Решение проблем

**WSL — артефакты при копировании:**
```bash
sudo apt install xsel
```

**Голосовой ввод:**
```bash
brew install sox        # macOS
sudo apt install sox    # Ubuntu/Debian
```

---

## Часть 2 — MiMo Code Telegram Bot (бесплатно)

AI-помощник по коду в Telegram. Использует **xiaomi/mimo-v2-flash:free** через OpenRouter — бесплатно, зарегистрироваться можно без карты.

### Деплой на Vercel — 3 шага

**Шаг 1. Получи ключи**

| Что | Где взять | Цена |
|---|---|---|
| Telegram токен | [@BotFather](https://t.me/BotFather) → /newbot | Бесплатно |
| OpenRouter API ключ | [openrouter.ai/keys](https://openrouter.ai/keys) | Бесплатно |

**Шаг 2. Задеплой на Vercel**
- [vercel.com](https://vercel.com) → New Project → Import этот репо
- Добавь переменные окружения:
  - `TELEGRAM_BOT_TOKEN`
  - `OPENROUTER_API_KEY`

**Шаг 3. Установи webhook**

Открой в браузере:
```
https://api.telegram.org/bot<ТОКЕН>/setWebhook?url=https://<твой-домен>.vercel.app/api/webhook
```

### Команды бота
- `/start` — приветствие
- `/help` — справка
- Любой текст → ответ AI-кодера

---

## Ссылки
- [MiMo Code GitHub](https://github.com/XiaomiMiMo/MiMo-Code)
- [OpenRouter — mimo-v2-flash:free](https://openrouter.ai/xiaomi/mimo-v2-flash:free)
- [MiMo API Platform](https://platform.xiaomimimo.com)
