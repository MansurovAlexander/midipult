# AGENTS.md — правила работы над форком MidiPult

Этот файл обязателен для любого агента и человека, который меняет код форка
[MidiPult](https://github.com/RoBiN19666/midipult) для Яндекс Станции Миди.

## 1. Что это за проект

Форк с доработками под провайдеров нейросетей (AITUNNEL, OpenAI, OpenRouter,
DeepSeek) и голосовой пульт на самой колонке.

Стек: Python 3 (CGI, только stdlib), lighttpd, shell и ES5-JS без сборки и CDN.
Устройство — Яндекс Станция Миди (Cucumber) с root, Entware и Luna.

## 2. Границы архитектуры

| Слой | Где |
|---|---|
| Интерфейс | `index.html` |
| CGI API | `cgi-bin/*.py` |
| Голосовой демон | `service/voice_daemon.py` |
| Установка | `deploy/*.sh`, `deploy/*.ps1` |
| Документация | `README.md`, `docs/**` |

Правила:

- CGI не тянет внешние зависимости — только stdlib и общий `cgi-bin/common.py`.
- UI без сборщиков, фреймворков и внешних CDN.
- Новый провайдер добавляется в `PROVIDERS` в `cgi-bin/llm.py` вместе со своей
  картой ошибок (`errors.types`, `errors.codes`, `errors.default`).
- Команды Алисы (музыка, треки, громкость) не отдаются в LLM — это зона
  `voice_daemon.py`.
- Секреты (ключи, токены, `llm.json`, `runtime.env`) не попадают в репозиторий.

## 3. Процесс разработки — жёсткий порядок

1. Ветка от `main`: `feat/…`, `fix/…`, `docs/…`, `chore/…`.
2. Правки и локальные проверки.
3. **Ревьюер** (`reviewer`) читает diff и ищет дефекты.
4. Если вердикт `CHANGES_REQUESTED` — исправить и повторить ревью.
5. **Только после `APPROVED`** — **аудитор документации** (`docs-auditor`).
6. Изменения оформляются **Pull Request** в `main`; мерж — только после
   `APPROVED` и обновления документации.
7. Прямой push в `main` запрещён. Все изменения — через PR, чтобы их можно было
   отслеживать.

Нельзя:

- мержить без `APPROVED`;
- вызывать аудитора документации до ревью;
- смешивать в одном PR независимые задачи;
- править код за ревьюера или документацию вместо аудитора.

Если суб-агент недоступен, работу не завершать молча: сообщить и остановиться.

## 4. Проверки перед PR

Python:

```sh
python -c "import ast; ast.parse(open('cgi-bin/llm.py', encoding='utf-8').read())"
python -c "import ast; ast.parse(open('service/voice_daemon.py', encoding='utf-8').read())"
```

Shell:

```sh
for f in deploy/*.sh; do sh -n "$f"; done
sh -n init.d/S99mypult
```

JS (встроенный скрипт в `index.html`) — извлечь и проверить:

```sh
python - <<'PY'
import re
html = open('index.html', encoding='utf-8').read()
blocks = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S)
big = max(blocks, key=len)
open('/tmp/ui_check.js', 'w', encoding='utf-8').write(big)
PY
node --check /tmp/ui_check.js
```

Тесты:

```sh
python tests/test_units.py       # 192 проверки
python tests/static_checks.py    # 121 проверка
python tests/run_cgi_tests.py    # 42 проверки
```

На колонке (если есть доступ):

```sh
MYPULT_NO_PACKAGES=1 sh deploy/preflight.sh
```

### 4.1. CI

Те же проверки автоматически идут в GitHub Actions —
`.github/workflows/ci.yml` (Python 3.12, Node 24, Ubuntu):

- `python -m compileall -q cgi-bin service tests` и
  `python -m py_compile index.py`;
- `for f in deploy/*.sh; do sh -n "$f"; done` и `sh -n init.d/S99mypult`;
- `tests/test_units.py`, `tests/static_checks.py`, `tests/run_cgi_tests.py`.

Workflow запускается на push в `main` и на каждый pull_request, имеет
`permissions: contents: read`, отменяет устаревший прогон той же ветки
(`concurrency` + `cancel-in-progress`) и ограничен 15 минутами. Локальные
проверки выше не заменяются: CI не видит колонку и не проверяет железо.

### 4.2. Переводы строк и BOM

`tests/static_checks.py` считает текстовыми `.html`, `.py`, `.conf`, `.sh`,
`.md`, `.json`, `.ps1`, `.cmd`, `.yml` и `S99mypult`. CRLF запрещён везде,
кроме `.ps1`/`.cmd` (для них в `.gitattributes` задано `eol=crlf`);
BOM допустим только у `.ps1`. Остальные файлы — LF и без BOM, иначе
`static_checks` падает на проверке «файлы без CRLF (кроме .ps1/.cmd) и BOM».

Проверка читает файлы как байты и не распознаёт повреждённую кодировку:
`.ps1` со смешанными UTF-16LE/UTF-8 строками проходит её, но PowerShell
такой файл не выполняет (так было с `deploy/push-to-station.ps1`).
Кодировку `.ps1` проверяйте отдельно — например, `file` в Git Bash или
открытием в редакторе; в CI такой дефект не ловится.

В описании PR указать, что проверено на живой Станции Миди, а что — нет.

## 5. Стиль кода

- Python: 4 пробела, stdlib, без `eval` и внешних пакетов.
- JS: ES5-совместимый, как в существующем `index.html`, без сборки.
- Идентификаторы и commit-сообщения — английский; интерфейс и документация — русский.
- Conventional Commits: `feat(llm): …`, `fix(voice): …`, `docs: …`.
- Сообщения об ошибках для пользователя — короткие, человеческие, на русском.

## 6. Секреты и приватность

- Не коммитить ключи API, токены, `llm.json`, `runtime.env`, дампы устройства.
- В PR не прикладывать реальные ключи и MAC-адреса.
- Логи и скриншоты перед публикацией чистить от персональных данных.

## 7. Definition of Done

- Ревью `APPROVED`.
- Документация обновлена `docs-auditor`.
- Проверки из раздела 4 пройдены, CI на GitHub зелёный.
- Есть отметка о тесте на живой колонке (или явно указано, что не проверялось).
- PR смержен в `main`.
