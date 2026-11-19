# Публикация на GitHub

Проект подготовлен к публикации: личные данные, секреты, локальные логи и
скриншоты с реальными IP/SSID исключены через `.gitignore`.

## Что намеренно не попадает в репозиторий

| Путь | Почему |
|---|---|
| `.mypult-station` | IP вашей колонки |
| `.mypult-hash` | локальное состояние деплоя |
| `push.log` | журнал заливки с адресами |
| `tests/*.png`, `tests/shot-*.png` | скриншоты с IP, SSID и подпиской |
| `__pycache__/`, `*.pyc` | сборочный мусор |
| `/data/mypult/*` | токены, ключи LLM, VPN-подписка, DNS, PIN — **никогда** не коммитить |
| `auth.json`, `volume.json`, `ring.json` | создаются только на устройстве |

Секреты создаются на колонке в `/data/mypult` с правами `600` и в исходниках
отсутствуют. Резервная копия из панели тоже содержит ключи — её нельзя
прикладывать к issue или коммитить.

## Вариант A — через git (рекомендуется)

Установите [Git for Windows](https://git-scm.com/download/win), затем в папке проекта:

```powershell
git init
git add .
git status                 # просмотрите список: не должно быть секретов и IP
git commit -m "Initial commit: MidiPult"
git branch -M main
git remote add origin https://github.com/<ваш-логин>/<репозиторий>.git
git push -u origin main
```

Если `git status` показывает что-то лишнее — добавьте путь в `.gitignore`
и повторите `git add .`.

## Вариант B — через веб-интерфейс GitHub

1. Создайте пустой репозиторий (без README).
2. На странице репозитория: **Add file → Upload files**.
3. Перетащите папки `cgi-bin`, `deploy`, `docs`, `init.d`, `lighttpd`,
   `service`, `tests` и файлы:
   - `index.html`, `index.py`, `manifest.json`, `favicon.ico`,
     `icon-192.png`, `icon-512.png`, `icon.png`, `icon-circle.png`;
   - `README.md`, `FAQ.md`, `SECURITY.md`, `CHANGELOG.md`, `LICENSE`, `.gitignore`;
   - `version.json`.
4. Не загружайте `tests/*.png`, `.mypult-station`, `push.log`, `auth.json`,
   `llm.json`, `vpn.json` и прочие файлы из `/data/mypult`.

## CI на GitHub

В репозитории есть workflow `.github/workflows/ci.yml`. Он запускается на
каждый push в `main` и на каждый pull_request и проверяет то же, что
описано в `AGENTS.md`:

- синтаксис Python — `compileall` для `cgi-bin`, `service`, `tests` и
  `py_compile index.py`;
- синтаксис shell — `sh -n` для всех `deploy/*.sh` и `init.d/S99mypult`;
- тесты — `tests/test_units.py` (235), `tests/static_checks.py` (122) и
  `tests/run_cgi_tests.py` (42).

Условия прогона: Ubuntu, Python 3.12, Node 24, права `contents: read`,
таймаут 15 минут; новый прогон той же ветки отменяет предыдущий
(`concurrency` + `cancel-in-progress`). Статус виден в PR на вкладке
**Checks**; по правилам проекта PR не мержится с красным CI.

CI проверяет только код в репозитории. Установка, `preflight.sh` и работа
железа (Luna, Glagol, IPC, свет, кольцо) на живой Станции Миди в CI **не**
проверяются — об этом по-прежнему пишут в описании PR.

Локальный запуск тех же тестов — в разделе 4 `AGENTS.md`:

```sh
python tests/test_units.py
python tests/static_checks.py
python tests/run_cgi_tests.py
```

Тест на переводах строк считает текстовыми `.html`, `.py`, `.conf`, `.sh`,
`.md`, `.json`, `.ps1`, `.cmd`, `.yml` и `S99mypult`: CRLF допустим только в
`.ps1`/`.cmd` (`.gitattributes`, `eol=crlf`). BOM разрешён только в `.ps1` и
обязателен там, где есть не-ASCII (иначе PowerShell 5.1 читает файл как ANSI
и кириллица ломается); у `.ps1` дополнительно проверяются UTF-8 и отсутствие
NUL. Именно на этом падал `deploy/push-to-station.ps1`, сохранённый в
UTF-16LE: `.gitattributes` перекодировал переводы строк, но NUL-байты
остались.

## Проверка перед публикацией

```powershell
# реальные адреса, токены LLM, подписки, PIN
Select-String -Path *.md,*.html,*.json,cgi-bin\*.py,service\*.py,deploy\* `
  -Pattern "192\.168\.(?!1\.100)|y0__|sk-[A-Za-z0-9]{10,}|vless://|vmess://|trojan://|Session_id|mypult_token="
```

Ожидаемый результат — пусто (кроме учебных примеров вида `192.168.1.100`).

Дополнительно проверьте, что не попали:

- `auth.json` (PIN-хэш и токен);
- `llm.json` (ключи провайдеров);
- `vpn.json` (подписка);
- `chats.json` (личные вопросы к нейросети);
- логи `voice.log`, `mypult.log`.

## Лицензия

Проект распространяется по MIT (`LICENSE`). Замените имя правообладателя,
если публикуете от своего имени.

## Скриншоты для README

Сделайте свои на тестовой сети без реальных данных: подписка VPN и SSID
должны быть фиктивными, IP — из диапазона `192.168.1.x`. Не показывайте
карточку «Нейросеть» с ключом и «Резервная копия» с реальными настройками.
