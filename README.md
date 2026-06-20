# Xiaomi MiMo Code — Инструкция по установке

MiMo Code — это AI-агент для написания кода от Xiaomi, совместимый с интерфейсом Anthropic Claude Code.

---

## Требования

- Node.js 18 или новее
- macOS, Linux, или Windows (через WSL / Git Bash)

---

## Установка

### Способ 1 — одна команда (macOS / Linux)

```bash
curl -fsSL https://mimo.xiaomi.com/install | bash
```

### Способ 2 — через npm (все платформы)

```bash
npm install -g @xiaomi-mimo/cli
```

---

## Запуск

```bash
mimo
```

При первом запуске мастер настройки предложит выбрать канал подключения.

---

## Начальная конфигурация

При первом запуске выберите один из вариантов подключения:

| Вариант | Описание |
|---|---|
| **MiMo Auto** | Бесплатно, нулевая конфигурация, анонимный канал |
| **Xiaomi MiMo Platform** | Вход через OAuth-аккаунт Xiaomi |
| **Миграция из Claude Code** | Перенос существующей аутентификации Claude |
| **Пользовательский провайдер** | Любой OpenAI-совместимый API |

---

## Конфигурационный файл

Настройки хранятся в:
- **Проект:** `.mimocode/mimocode.json`
- **Глобально:** `~/.config/mimocode/mimocode.json`

---

## Решение проблем

### WSL — артефакты при копировании текста

```bash
sudo apt install xsel
```

### Голосовой ввод (опционально)

```bash
# macOS
brew install sox

# Ubuntu / Debian
sudo apt install sox
```

---

## Ссылки

- [GitHub репозиторий MiMo-Code](https://github.com/XiaomiMiMo/MiMo-Code)
- [Документация Xiaomi MiMo Platform](https://mimo.mi.com/docs/en-US/tokenplan/integration/mimo-code)
- [Claude Code + MiMo интеграция](https://mimo.mi.com/docs/en-US/tokenplan/integration/claudecode)
