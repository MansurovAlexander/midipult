# AITUNNEL и веб-поиск (форк)

Этот репозиторий — форк [RoBiN19666/midipult](https://github.com/RoBiN19666/midipult)
с тремя правками, которые нужны для работы нейросети через
[AITUNNEL](https://aitunnel.ru) на Станции Миди.

## Что изменено относительно upstream

Все изменения — в `cgi-bin/llm.py`.

1. **`User-Agent` в запросах к API.** Без него облачные шлюзы
   (в частности Cloudflare перед `opencode.ai`) отвечают `403` с ошибкой
   `error code: 1010`, потому что Python-клиент представляется как
   `Python-urllib`.
2. **Устойчивый разбор ответа.** Некоторые провайдеры за агрегатором
   возвращают `message.content = null` (например, если ответ ушёл только
   в `reasoning`). Раньше это роняло `llm.py` в `500`; теперь код берёт
   `content`, при `null` — `reasoning`, а при пустом результате отдаёт
   понятную ошибку `502`.
3. **Веб-поиск AITUNNEL.** Для профилей с `base_url`, содержащим
   `aitunnel.ru`, в запрос добавляется серверный инструмент:

   ```json
   "tools": [{
     "type": "aitunnel:web_search",
     "parameters": {
       "engine": "parallel",
       "mode": "basic",
       "max_results": 3,
       "max_uses": 1
     }
   }]
   ```

   Модель сама решает, нужен ли поиск: на «какая погода» сходит в сеть,
   на «17 × 23» — нет. Движок `parallel/basic` выбран потому, что
   корректно работает с русским языком.

Дополнительно из ответа перед озвучкой вырезаются сноски `[1]` и markdown
(`**`, `` ` ``, `#`, `>`), чтобы TTS не читал разметку.

## Установка

1. На колонке должен быть root, Entware и Luna на `127.0.0.1:8099`
   (см. основной README).
2. Создайте каталог веб-рута (установщик его не создаёт):

   ```sh
   mkdir -p /data/myweb
   ```

3. Скачайте форк и запустите установщик:

   ```sh
   cd /tmp && rm -rf mp && mkdir mp && cd mp
   wget -O f.zip https://github.com/MansurovAlexander/midipult/archive/refs/heads/main.zip
   unzip -q f.zip && cd midipult-main
   sh deploy/install.sh
   ```

   С Windows удобнее `deploy/push-to-station.ps1 -Station <IP>`.

## Настройка профиля AITUNNEL

Через панель: `http://<IP>:8055` → «Нейросеть» → свой сервер:

- Base URL: `https://api.aitunnel.ru/v1`
- Модель: `deepseek-v4.1-flash-1017`
- Ключ: `sk-aitunnel-...`

Или на колонке одной командой:

```sh
sh deploy/aitunnel-profile.sh sk-aitunnel-...
```

Скрипт создаёт профиль, делает его активным и включает голосовой тумблер.

## Стоимость

- обычная реплика без поиска — около 0.01 ₽;
- реплика с веб-поиском — около 1 ₽ (движок Parallel, режим `basic`,
  один поиск на запрос, до 3 результатов).

Чтобы поиск был дешевле, можно поменять `engine`/`mode` на
`parallel/fast` (около 0.20 ₽), но он рассчитан на английский и японский;
для русского лучше оставить `basic`. Другой вариант — `exa` (около 1.40 ₽)
или `perplexity` (около 1 ₽).

## Синхронизация с upstream

```sh
git remote add upstream https://github.com/RoBiN19666/midipult.git
git fetch upstream
git merge upstream/main
```

Если upstream изменит `cgi-bin/llm.py`, при конфликте нужно сохранить
наши три правки из раздела «Что изменено».

## Ограничения

- Веб-поиск включается только для профилей AITUNNEL (по `base_url`).
  Для других провайдеров поведение не меняется.
- Правки не попадают в релизы upstream и не публикуются как пакет:
  установка идёт из исходников этого форка.
