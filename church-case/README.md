# church-case — харнес церковного дисциплинарного дела

Сбор доказательств → расшифровка → эпизоды → каноническая квалификация →
представление в церковный орган → атака от лица Ответчика → валидация →
подпись человеком.

- Правила и правовой контур — [CLAUDE.md](CLAUDE.md)
- Роли и промпты субагентов — [AGENTS.md](AGENTS.md)
- Процедура по стадиям — [procedure/stages.md](procedure/stages.md)
- Формат эпизода — [schema/episode.schema.json](schema/episode.schema.json)
- Шаблоны — [templates/](templates/)

**Материалы дела в git не попадают** (`private/` в .gitignore; репозиторий публичный).

## Как передать материалы

Облачная сессия Claude не видит папки на вашем компьютере. Варианты:

1. **Запустить харнес локально** (лучший вариант для приватности):
   ```bash
   git clone <этот репозиторий> && cd ai-office-antigravity
   pip install mlx-whisper      # Mac M1–M4 (иначе: pip install faster-whisper)
   brew install ffmpeg
   python3 church-case/scripts/find_materials.py --term "Фамилия" --term "Организация"
   python3 church-case/scripts/ingest_whatsapp.py "~/Downloads/Чат WhatsApp с ….zip"
   python3 church-case/scripts/ingest_whatsapp.py --extra "~/Материалы/Сергей"
   python3 church-case/scripts/transcribe.py
   python3 church-case/scripts/scan_candidates.py --author "Имя Ответчика в чате"
   ```
   Дальше — Claude Code локально (`claude` в папке репо) ведёт роли 3–9.
2. **Через Google Drive**: файл должен быть доступен подключённому к сессии
   аккаунту Google (не «по ссылке» у другого аккаунта). Большой zip
   (сотни МБ) коннектор может не отдать — тогда выложить распакованные
   `_chat.txt` и аудио порциями (папка ≤ ~50 МБ), либо вариант 1.
3. **Экспорт WhatsApp**: чат → ⋮ → Ещё → Экспорт чата → **С медиафайлами**.
   Без медиа аудио не будет — ingest предупредит.

Облачный контейнер эфемерен: всё в `private/` исчезнет вместе с сессией.
Для долгой работы — локальный запуск или отдельный **приватный** репозиторий
для материалов.

## Команды

| Шаг | Команда | Выход |
|---|---|---|
| Поиск на компьютере | `scripts/find_materials.py --term …` | `private/work/found.csv` (опись, без копирования) |
| Приём | `scripts/ingest_whatsapp.py <zip>` | `private/work/manifest.json`, `messages.jsonl` |
| Расшифровка | `scripts/transcribe.py` | `private/work/transcripts/<sha256>.json` |
| Кандидаты | `scripts/scan_candidates.py --author …` | `private/work/candidates.jsonl` |
| Валидация | `scripts/check_case.py [--strict]` | FAIL/WARN, код выхода |
| Приложение | `scripts/build_dossier.py` | `private/drafts/prilozhenie_epizody.md` |
| Тест харнеса | `bash tests/run_tests.sh` | «ВСЕ ТЕСТЫ ПРОЙДЕНЫ» |

Критерий «готово» к подписи: `check_case.py --strict` чисто, red team
(`private/drafts/redteam.md`) не содержит `breaks` по пунктам обвинения,
юрисдикция подтверждена документом уровня A, юрист вычитал.
