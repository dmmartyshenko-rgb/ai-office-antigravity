#!/bin/bash
# Installer for Xiaomi MiMo Code CLI
set -e

echo "=== Установка Xiaomi MiMo Code ==="
echo

if ! command -v node &> /dev/null; then
    echo "ОШИБКА: Node.js не найден."
    echo "Установи Node.js 18+ с https://nodejs.org и запусти скрипт снова."
    exit 1
fi

NODE_VER=$(node --version)
echo "Node.js: $NODE_VER"
echo

if command -v curl &> /dev/null; then
    echo "Устанавливаю через curl..."
    curl -fsSL https://mimo.xiaomi.com/install | bash
else
    echo "curl не найден — устанавливаю через npm..."
    npm install -g @xiaomi-mimo/cli
fi

echo
echo "Готово! Запусти:"
echo
echo "  mimo"
echo
