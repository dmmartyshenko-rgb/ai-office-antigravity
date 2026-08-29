#!/usr/bin/env python3
"""Тестовый сценарий Hermes Megamap (Этап 4 ТЗ): создание домена и обработка
встречи. Гоняется в изолированном temp-каталоге, реальное хранилище не трогает.

Проверяет: init → add-raw (Triage) → consolidate (слои 1/2/3) → lint (код 0)
→ decay (авто-Пауза по бездействию) → инварианты (append-only, дедупликация,
unmatched, TTL). Выход 0 — все проверки прошли.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
failures = []


def check(name: str, cond: bool, detail: str = ""):
    print(f"  [{'ok' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def cli(root: Path, *args, expect: int = 0) -> str:
    env = dict(os.environ, HERMES_ROOT=str(root))
    r = subprocess.run([sys.executable, str(SCRIPTS / "hermes_cli.py"), *args],
                       capture_output=True, text=True, cwd=root, env=env)
    out = r.stdout + r.stderr
    if r.returncode != expect:
        check(f"cli {' '.join(args)} → код {expect}", False, out.strip())
    return out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="hermes-megamap-test-"))
    root = tmp / "store"
    root.mkdir()
    try:
        print("1. init")
        os.chdir(root)
        cli(root, "init")
        check("структура создана", (root / "buffer").is_dir()
              and (root / "INDEX.md").is_file()
              and (root / ".hermes" / "metadata.db").is_file())

        print("2. Triage: создание домена + заметка о встрече")
        cli(root, "add-raw",
            "@new-project test-drive | Test Drive | Обкатка системы памяти")
        cli(root, "add-raw",
            "@test-drive ! Встреча по запуску\n"
            "Обсудили план обкатки, решили начать с CLI.\n"
            "Почему: CLI — самый короткий путь до рабочего цикла.\n"
            "Следующий шаг: прогнать consolidate на реальных заметках")
        cli(root, "add-raw",
            "@new-contact anna-smirnova | Анна Смирнова | Ближний круг / партнёр по проекту")
        # заметка без @ — должна притянуться гравитацией к test-drive
        cli(root, "add-raw", "Мелкая идея по test-drive: добавить бейдж статуса")
        # заметка-сирота — не должна никуда привязаться
        cli(root, "add-raw", "Абстрактная мысль ни о чём конкретном")
        check("Triage не тронул INDEX (инвариант)",
              "test-drive" not in (root / "INDEX.md").read_text(encoding="utf-8"))
        check("в буфере 5 заметок",
              len(list((root / "buffer").glob("*.md"))) == 5)

        print("3. Дедупликация")
        out = cli(root, "add-raw", "Абстрактная мысль ни о чём конкретном", expect=1)
        check("дубликат отвергнут по hash", "дубликат" in out)

        print("4. Consolidate")
        out = cli(root, "consolidate", expect=2)  # 2 = остались unmatched
        idx = (root / "INDEX.md").read_text(encoding="utf-8")
        check("домен test-drive в INDEX", "test-drive" in idx)
        check("контакт anna-smirnova в INDEX", "anna-smirnova" in idx)
        map_td = (root / "domains/projects/test-drive.md").read_text(encoding="utf-8")
        check("«Следующий шаг» обновлён из заметки",
              "прогнать consolidate на реальных заметках" in map_td)
        log_td = (root / "logs/projects/test-drive.log.md").read_text(encoding="utf-8")
        check("встреча записана в журнал (слой 3)", "Встреча по запуску" in log_td
              and "**Почему:** CLI — самый короткий путь" in log_td)
        check("новая запись журнала — сверху (append-only, новые выше старых)",
              log_td.find("Встреча по запуску") < log_td.find("Домен создан"))
        check("gravity-заметка привязалась к test-drive",
              "бейдж статуса" in log_td)
        check("обработанные оригиналы в cold/sources/",
              len(list((root / "cold/sources").glob("*.md"))) == 4)
        check("сирота осталась в буфере как unmatched",
              len(list((root / "buffer").glob("*.md"))) == 1 and "не удалось привязать" in out)

        print("5. Линтер зелёный")
        out = cli(root, "lint")
        check("lint → OK", "OK:" in out)

        print("6. Линтер ловит нарушения")
        orphan = root / "domains/projects/orphan.md"
        orphan.write_text("# Сирота\n", encoding="utf-8")
        step_backup = map_td
        (root / "domains/projects/test-drive.md").write_text(
            re.sub(r"(## Следующий шаг\n).*?(?=\n## )",
                   r"\1—\n", step_backup, flags=re.DOTALL), encoding="utf-8")
        out = cli(root, "lint", expect=1)
        check("ловит карту-сироту", "сирота" in out)
        check("ловит пустой «Следующий шаг» у активного проекта",
              "Следующий шаг» пуст" in out)
        orphan.unlink()
        (root / "domains/projects/test-drive.md").write_text(step_backup,
                                                             encoding="utf-8")
        cli(root, "lint")

        print("7. Decay: авто-Пауза по бездействию")
        stale = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d %H:%M")
        for rel in ["logs/projects/test-drive.log.md",
                    "logs/relationships/anna-smirnova.log.md"]:
            p = root / rel
            p.write_text(re.sub(r"### \d{4}-\d{2}-\d{2} \d{2}:\d{2}",
                                f"### {stale}", p.read_text(encoding="utf-8")),
                         encoding="utf-8")
        cli(root, "decay")
        idx = (root / "INDEX.md").read_text(encoding="utf-8")
        map_td = (root / "domains/projects/test-drive.md").read_text(encoding="utf-8")
        map_as = (root / "domains/relationships/anna-smirnova.md").read_text(encoding="utf-8")
        check("проект переведён в Пауза (INDEX + карта)",
              re.search(r"test-drive \| Проект \| Пауза", idx) is not None
              and "Пауза. Обновлено" in map_td)
        check("блокер зафиксирован в карте проекта", "Decay:" in map_td)
        check("Friend Health Score пересчитан и контакт в Паузе",
              re.search(r"Friend Health Score\n0/100", map_as) is not None
              and "Пауза (авто-decay" in map_as)
        out = cli(root, "lint")
        check("после decay линтер зелёный", "OK:" in out)

        print("8. Audit: TTL буфера")
        pending = next((root / "buffer").glob("*.md"))
        pending.write_text(re.sub(r"created: \S+",
                                  f"created: {(datetime.now() - timedelta(days=30)).isoformat(timespec='seconds')}",
                                  pending.read_text(encoding="utf-8")),
                           encoding="utf-8")
        out = cli(root, "decay")
        check("просроченная заметка буфера поймана аудитом", "TTL" in out)

        print("9. status-дашборд")
        out = cli(root, "status")
        check("status показывает INDEX и буфер",
              "HERMES MEGAMAP" in out and "Буфер (L0): 1" in out)
    finally:
        os.chdir("/")
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print(f"\nFAIL: {len(failures)} проверок провалено: {failures}")
        return 1
    print("\nPASS: тестовый сценарий пройден полностью")
    return 0


if __name__ == "__main__":
    sys.exit(main())
