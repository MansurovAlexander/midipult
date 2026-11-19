#!/opt/bin/python3
# -*- coding: utf-8 -*-
"""LLM через OpenAI-совместимый API: несколько профилей и переключение.

    GET  /cgi-bin/llm.py?info=1           — провайдеры, профили, активный
    POST /cgi-bin/llm.py {"enabled":1}    — включить/выключить (без правки профиля)
    POST /cgi-bin/llm.py {"profile_id","name","provider","model","base_url","key"} — сохранить профиль
    POST /cgi-bin/llm.py {"activate":"deepseek"} — сделать профиль активным
    POST /cgi-bin/llm.py {"delete":"deepseek"}   — удалить профиль
    POST /cgi-bin/llm.py {"prompt":"..."}       — вопрос к активному профилю

Ключи хранятся в /data/mypult/llm.json (600), наружу отдаётся только key_set.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

CONFIG_DIR = "/data/mypult"
CONFIG_PATH = os.path.join(CONFIG_DIR, "llm.json")
CHATS_PATH = os.path.join(CONFIG_DIR, "chats.json")

USER_AGENT = "MidiPult/0.4.68"
MAX_RESPONSE = 2 * 1024 * 1024


def read_json_response(response, limit=MAX_RESPONSE):
    """Прочитать JSON-ответ с ограничением размера.

    ValueError (включая JSONDecodeError) означает негодный ответ провайдера;
    вызывающий превращает его в 502, а не в 500.
    """
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("ответ больше %d байт" % limit)
    return json.loads(raw.decode("utf-8"))


def chat_answer(body):
    """Текст ответа из OpenAI-совместимого тела.

    None — тело не похоже на chat/completions; "" — тело корректное, но модель
    ничего не сказала (например, content: null без reasoning).
    """
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0] if isinstance(choices[0], dict) else None
    message = first.get("message") if isinstance(first, dict) else None
    if not isinstance(message, dict):
        return None
    answer = message.get("content")
    if answer is None:
        answer = message.get("reasoning")
    if isinstance(answer, list):
        parts = []
        for item in answer:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        answer = " ".join(parts)
    return str(answer or "").strip()


def normalize_provider(provider):
    """Пустой провайдер исторически означает OpenAI."""
    return str(provider or "").strip() or "openai"

# Общие тексты ошибок: используются, если у провайдера нет своего варианта.
BASE_ERRORS = {
    "codes": {
        400: "Нейросеть отклонила запрос",
        401: "Ключ API не принят",
        402: "Закончились средства на балансе нейросети",
        403: "Доступ к нейросети запрещён",
        404: "Модель не найдена",
        408: "Сервис не ответил вовремя",
        413: "Слишком большой запрос",
        429: "Слишком много запросов подряд",
        500: "Ошибка на стороне сервиса",
        502: "Сервис нейросети недоступен",
        503: "Сервис нейросети перегружен",
        504: "Сервис не ответил вовремя",
    },
    "default": "Сервис нейросети не отвечает",
}

PROVIDERS = {
    "openai": {
        "title": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"],
        "errors": {
            "types": {
                "invalid_api_key": "Ключ OpenAI не принят",
                "insufficient_quota": "Закончилась квота OpenAI",
                "rate_limit_exceeded": "Слишком много запросов к OpenAI",
                "model_not_found": "Модель OpenAI не найдена",
                "context_length_exceeded": "Слишком длинный запрос для модели",
                "server_error": "Ошибка на стороне OpenAI",
            },
            "codes": {
                401: "Ключ OpenAI не принят",
                402: "Закончились средства на балансе OpenAI",
                429: "Слишком много запросов к OpenAI",
                500: "Ошибка на стороне OpenAI",
            },
            "default": "OpenAI не отвечает",
        },
    },
    "openrouter": {
        "title": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "openai/gpt-4o-mini",
            "anthropic/claude-3.5-sonnet",
            "google/gemini-2.0-flash-001",
            "deepseek/deepseek-chat",
        ],
        "errors": {
            "types": {
                "invalid_api_key": "Ключ OpenRouter не принят",
                "insufficient_credits": "Закончились кредиты OpenRouter",
                "rate_limit_exceeded": "Слишком много запросов к OpenRouter",
                "model_not_found": "Модель OpenRouter не найдена",
                "no_endpoints_found": "У модели нет доступных провайдеров",
                "context_length_exceeded": "Слишком длинный запрос для модели",
            },
            "codes": {
                401: "Ключ OpenRouter не принят",
                402: "Закончились кредиты OpenRouter",
                404: "Модель OpenRouter не найдена",
                429: "Слишком много запросов к OpenRouter",
            },
            "default": "OpenRouter не отвечает",
        },
    },
    "deepseek": {
        "title": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-flash", "deepseek-v4-pro"],
        "errors": {
            "types": {
                "authentication_fails": "Ключ DeepSeek не принят",
                "insufficient_balance": "Закончились средства на балансе DeepSeek",
                "rate_limit_reached": "Слишком много запросов к DeepSeek",
                "invalid_request_error": "DeepSeek отклонил запрос",
                "server_error": "Ошибка на стороне DeepSeek",
            },
            "codes": {
                401: "Ключ DeepSeek не принят",
                402: "Закончились средства на балансе DeepSeek",
                429: "Слишком много запросов к DeepSeek",
                500: "Ошибка на стороне DeepSeek",
            },
            "default": "DeepSeek не отвечает",
        },
    },
    "aitunnel": {
        "title": "AITUNNEL",
        "base_url": "https://api.aitunnel.ru/v1",
        "models": ["deepseek-v4.1-flash-1017", "deepseek-v4.1-flash", "sonar"],
        "errors": {
            "types": {
                "insufficient_balance": "Закончились деньги на балансе AITUNNEL",
                "budget_exceeded": "Исчерпан бюджет ключа AITUNNEL",
                "authentication_failed": "Ключ AITUNNEL не принят",
                "permission_denied": "Ключу AITUNNEL запрещён этот запрос",
                "model_not_found": "Модель не найдена в AITUNNEL",
                "not_found": "AITUNNEL не нашёл запрошенный ресурс",
                "invalid_request": "AITUNNEL отклонил запрос",
                "sensitive_data_blocked": "Запрос заблокирован из-за чувствительных данных",
                "rate_limited": "Слишком много запросов к AITUNNEL",
                "provider_error": "Провайдер модели вернул ошибку",
                "provider_unavailable": "Модель сейчас недоступна",
                "upstream_invalid_response": "Провайдер вернул негодный ответ",
                "service_unavailable": "Сервис AITUNNEL временно недоступен",
                "internal": "Внутренняя ошибка AITUNNEL",
            },
            "codes": {
                402: "Закончились деньги на балансе AITUNNEL",
                403: "AITUNNEL запретил запрос",
                429: "Слишком много запросов к AITUNNEL",
                503: "AITUNNEL временно недоступен",
            },
            "default": "AITUNNEL не отвечает",
        },
    },
    "custom": {
        "title": "Свой сервер (OpenAI-совместимый)",
        "base_url": "",
        "models": [],
        "errors": {
            "default": "Сервис нейросети не отвечает",
        },
    },
}


def provider_errors(provider):
    """Слить общие тексты ошибок с настройками конкретного провайдера."""
    merged = {
        "types": {},
        "codes": dict(BASE_ERRORS["codes"]),
        "default": BASE_ERRORS["default"],
    }
    cfg = (PROVIDERS.get(provider or "") or {}).get("errors") or {}
    merged["types"].update(cfg.get("types") or {})
    merged["codes"].update(cfg.get("codes") or {})
    if cfg.get("default"):
        merged["default"] = cfg["default"]
    return merged


def parse_error_lines(text):
    """Разобрать строки «ключ=текст» (комментарии с # игнорируются)."""
    result = {}
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key and value:
            result[key] = value
    return result


def default_error_lines(provider):
    """Тексты провайдера в том же формате, что и пользовательские."""
    errs = provider_errors(provider)
    lines = ["# Типы ошибок провайдера"]
    for key in sorted(errs["types"]):
        lines.append("%s=%s" % (key, errs["types"][key]))
    lines.append("# HTTP-коды")
    for code in sorted(errs["codes"]):
        lines.append("%s=%s" % (code, errs["codes"][code]))
    lines.append("default=%s" % errs["default"])
    return "\n".join(lines)


def custom_error_messages(config, provider):
    """Свои тексты для провайдера; старый общий вариант — как fallback."""
    config = config or {}
    messages = config.get("error_messages")
    if isinstance(messages, dict):
        text = messages.get(provider or "")
        if isinstance(text, str) and text.strip():
            return parse_error_lines(text)
    legacy = config.get("error_messages_text")
    if isinstance(legacy, str) and legacy.strip():
        return parse_error_lines(legacy)
    return {}


def error_text(config, profile, code, etype="", ecode=""):
    """Текст ошибки: свои правки, затем провайдер, затем общий вариант."""
    provider = normalize_provider((profile or {}).get("provider"))
    custom = custom_error_messages(config, provider)
    for key in (etype, str(ecode or ""), str(code), "default"):
        if key and key in custom:
            return custom[key]
    errs = provider_errors(provider)
    for key in (etype, str(ecode or "")):
        if key and key in errs["types"]:
            return errs["types"][key]
    return errs["codes"].get(code) or errs["default"]


def fetch_models(profile, provider=None, requested_base=None):
    """Модели для провайдера: по ключу, иначе публичный каталог, иначе встроенный.

    Ключ активного профиля используется только если выбранный провайдер и
    base_url совпадают с активным — иначе каталог был бы от чужого сервиса.
    """
    active = profile or {}
    provider = normalize_provider(provider or active.get("provider"))
    requested_base = str(requested_base or "").strip()
    active_base = str(active.get("base_url") or "").strip()
    base_url = (requested_base
                or PROVIDERS.get(provider, {}).get("base_url")
                or (active_base if provider == normalize_provider(active.get("provider")) else "")
                or "").rstrip("/")

    key = ""
    if provider == normalize_provider(active.get("provider")):
        if not requested_base or requested_base.rstrip("/") == active_base.rstrip("/"):
            key = str(active.get("key") or "")

    if base_url:
        try:
            base_url = common.url_guard(base_url, allow_http=True,
                                        allow_private=True, allow_loopback=True)
        except ValueError:
            base_url = ""

    if base_url and key:
        try:
            request = urllib.request.Request(
                base_url + "/models",
                headers={"Authorization": "Bearer " + key,
                         "User-Agent": USER_AGENT})
            with common.open_url(request, timeout=20, allow_http=True,
                                 allow_private=True, allow_loopback=True, same_host=True) as response:
                data = json.loads(response.read(1024 * 1024).decode("utf-8", "replace"))
            items = data.get("data") if isinstance(data, dict) else None
            ids = sorted({str(item.get("id")) for item in (items or [])
                          if isinstance(item, dict) and item.get("id")})
            if ids:
                return ids, "key"
        except Exception:  # noqa: BLE001
            pass

    if provider == "aitunnel" or "aitunnel" in base_url:
        try:
            request = urllib.request.Request(
                "https://api.aitunnel.ru/public/aitunnel/models",
                headers={"User-Agent": USER_AGENT})
            with common.open_url(request, timeout=20, allow_http=True,
                                 allow_private=True, allow_loopback=True, same_host=True) as response:
                data = json.loads(response.read(2 * 1024 * 1024).decode("utf-8", "replace"))
            chat = data.get("chat") if isinstance(data, dict) else None
            if isinstance(chat, dict) and chat:
                return sorted(chat.keys()), "public"
        except Exception:  # noqa: BLE001
            pass

    return list(PROVIDERS.get(provider, {}).get("models") or []), "builtin"


def slug(text):
    text = re.sub(r"[^a-zа-я0-9]+", "-", (text or "").lower()).strip("-")
    return text[:40] or "profile"


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}

    if "profiles" not in data:
        profiles = []
        if data.get("provider") or data.get("key"):
            provider = data.get("provider") or "openai"
            profiles.append({
                "id": "default",
                "name": data.get("name") or PROVIDERS.get(provider, {}).get("title") or "Профиль",
                "provider": provider,
                "model": data.get("model") or "",
                "base_url": data.get("base_url") or PROVIDERS.get(provider, {}).get("base_url", ""),
                "key": data.get("key") or "",
            })
        data = {
            "enabled": bool(data.get("enabled")),
            "active": profiles[0]["id"] if profiles else None,
            "profiles": profiles,
        }

    if not isinstance(data.get("profiles"), list):
        data["profiles"] = []
    if not isinstance(data.get("max_tokens"), int):
        data["max_tokens"] = 260
    if not isinstance(data.get("system_prompt"), str):
        data["system_prompt"] = ""
    if not isinstance(data.get("error_messages"), dict):
        data["error_messages"] = {}
    if not isinstance(data.get("error_messages_text"), str):
        data["error_messages_text"] = ""
    return data


def save_config(config):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        pass
    common.write_json(CONFIG_PATH, config, indent=2)


def public_profile(profile):
    if not profile:
        return None
    return {
        "id": profile.get("id"),
        "name": profile.get("name"),
        "provider": normalize_provider(profile.get("provider")),
        "model": profile.get("model") or "",
        "base_url": profile.get("base_url") or "",
        "key_set": bool(profile.get("key")),
    }


def active_profile(config):
    profiles = config.get("profiles") or []
    active = config.get("active")
    for profile in profiles:
        if profile.get("id") == active:
            return profile
    return profiles[0] if profiles else None


def info(config=None):
    config = config or load_config()
    profiles = config.get("profiles") or []
    active = active_profile(config)
    chats = load_chats()
    chat = active_chat(chats)
    provider = normalize_provider((active or {}).get("provider"))
    stored = ""
    messages = config.get("error_messages")
    if isinstance(messages, dict):
        stored = str(messages.get(provider) or "")
    if not stored:
        stored = str(config.get("error_messages_text") or "")
    return {
        "ok": True,
        "providers": [
            {"id": key, "title": value["title"], "base_url": value["base_url"], "models": value["models"]}
            for key, value in PROVIDERS.items()
        ],
        "profiles": [public_profile(item) for item in profiles],
        "active": active.get("id") if active else None,
        "active_name": active.get("name") if active else None,
        "voice_enabled": voice_enabled(config),
        # Совместимость со старым API: enabled теперь означает голосовой тумблер.
        "enabled": voice_enabled(config),
        "system_prompt": str(config.get("system_prompt") or ""),
        "error_messages_text": stored or default_error_lines(provider),
        "error_messages_custom": bool(stored),
        "config": public_profile(active),
        "max_tokens": int(config.get("max_tokens") or 260),
        "chats": [chat_public(item) for item in chats.get("chats") or []],
        "active_chat": chat.get("id") if chat else None,
        "active_chat_name": chat.get("name") if chat else None,
    }


def load_chats():
    try:
        with open(CHATS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    chats = data.get("chats") if isinstance(data, dict) else None
    if not isinstance(chats, list) or not chats:
        chats = [{"id": "chat-1", "name": "Чат 1", "messages": []}]
        data = {"active": "chat-1", "chats": chats}
        save_chats(data)
    if not data.get("active") or not any(c.get("id") == data["active"] for c in chats):
        data["active"] = chats[0].get("id")
    return data


def save_chats(data):
    try:
        common.write_json(CHATS_PATH, data, indent=2)
    except OSError:
        pass


def active_chat(data):
    for chat in data.get("chats") or []:
        if chat.get("id") == data.get("active"):
            return chat
    return (data.get("chats") or [None])[0]


def chat_public(chat):
    return {
        "id": chat.get("id"),
        "name": chat.get("name"),
        "messages": len(chat.get("messages") or []),
    }


def voice_enabled(config):
    """Тумблер относится только к голосовым вопросам, не к текстовому API."""
    if "voice_enabled" in config:
        return bool(config.get("voice_enabled"))
    return bool(config.get("enabled"))


def ask(prompt, system=None):
    config = load_config()
    profile = active_profile(config)
    if not profile:
        common.fail(400, "Нет профиля LLM", hint="Добавьте профиль и ключ")
        return
    if not profile.get("key"):
        common.fail(400, "Не задан API-ключ", hint="Вставьте ключ и нажмите «Сохранить»")
        return

    model = str(profile.get("model") or "").strip()
    if not model:
        common.fail(400, "Не выбрана модель",
                    hint="Выберите модель в карточке «Нейросеть»")
        return

    provider = normalize_provider(profile.get("provider"))
    base_url = (profile.get("base_url") or PROVIDERS.get(provider, {}).get("base_url") or "").rstrip("/")
    if not base_url:
        common.fail(400, "Не задан base_url для своего провайдера")
        return
    try:
        base_url = common.url_guard(base_url, allow_http=True, allow_private=True,
                                    allow_loopback=True)
    except ValueError as exc:
        common.fail(400, "Некорректный base_url: %s" % exc)
        return

    chats = load_chats()
    chat = active_chat(chats)

    messages = []
    if not system:
        system = str(config.get("system_prompt") or "").strip()
    if system:
        messages.append({"role": "system", "content": system})
    messages.extend((chat.get("messages") or [])[-10:])
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        # Длина ответа настраивается в панели (260 / 700 / 1400).
        "max_tokens": common.to_int(config.get("max_tokens"), 260, 50, 2000),
    }
    if provider == "deepseek":
        # Без «размышлений» deepseek-flash отвечает ~1.5 с вместо 10–15 с.
        payload["thinking"] = {"type": "disabled"}
    # AITUNNEL: серверный веб-поиск. Модель сама решает, когда искать.
    if "aitunnel.ru" in base_url:
        payload["tools"] = [{
            "type": "aitunnel:web_search",
            "parameters": {"engine": "parallel", "mode": "basic",
                           "max_results": 3, "max_uses": 1},
        }]
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + profile["key"],
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with common.open_url(request, timeout=90, allow_http=True,
                             allow_private=True, allow_loopback=True, same_host=True) as response:
            body = read_json_response(response)
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read(2000).decode("utf-8", "replace")
        except OSError:
            pass
        hint = ""
        etype = ""
        ecode = ""
        try:
            data = json.loads(raw) if raw.strip() else {}
            err = data.get("error") if isinstance(data, dict) else None
            if isinstance(err, dict):
                etype = str(err.get("type") or "")
                ecode = str(err.get("code") or "")
                message = str(err.get("message") or "").strip()
                if message:
                    hint = message
        except (ValueError, TypeError):
            pass
        short = error_text(config, profile, exc.code, etype, ecode)
        # Ошибка провайдера всегда отдаётся как 502: наружу не должны утекать
        # 401/402 провайдера, которые не отличить от PIN/биллинга самого пульта.
        common.fail(502, short, hint=hint[:300], detail=raw[:400],
                    error_type=etype or None, provider_status=exc.code)
        return
    except ValueError as exc:
        common.fail(502, "Неожиданный ответ API", detail=str(exc)[:200])
        return
    except (urllib.error.URLError, OSError) as exc:
        common.fail(502, "Нет связи с сервисом нейросети",
                    hint="Проверь интернет на колонке; если провайдер блокирует "
                         "сеть, попробуй base_url https://ru-api.aitunnel.ru/v1",
                    detail=str(exc)[:200])
        return

    answer = chat_answer(body)
    if answer is None:
        common.fail(502, "Неожиданный ответ API", detail=str(body)[:400])
        return
    # Ссылки на источники и markdown в озвучке не нужны.
    answer = re.sub(r"\[\d+\]", "", answer)
    answer = re.sub(r"[*_`#>]+", "", answer)
    answer = re.sub(r"\s{2,}", " ", answer).strip()
    if not answer:
        common.fail(502, "Модель вернула пустой ответ", detail=str(body)[:400])
        return
    history = chat.setdefault("messages", [])
    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": answer})
    chat["messages"] = history[-20:]
    save_chats(chats)

    common.ok(answer=answer, model=payload["model"], provider=provider,
              profile=profile.get("name"), chat=chat.get("name"),
              chat_id=chat.get("id"), usage=body.get("usage"))


def save_profile(config, data):
    profiles = config.get("profiles") or []
    raw_pid = str(data.get("profile_id") or "").strip()
    pid = slug(raw_pid) if raw_pid else ""
    profile = next((item for item in profiles
                    if slug(str(item.get("id") or "")) == pid), None) if pid else None

    name = str(data.get("name") or "").strip()
    provider = str(data.get("provider") or "").strip()
    if provider and provider not in PROVIDERS:
        common.fail(400, "Неизвестный провайдер", providers=list(PROVIDERS))
        return None

    if profile is None:
        base_name = name or (PROVIDERS.get(provider, {}).get("title") if provider else "Профиль")
        existing = {slug(str(item.get("id") or "")) for item in profiles}
        # profile_id позволяет вызывающему (deploy/aitunnel-profile.sh) получить
        # стабильный id: повторный запуск обновит профиль, а не создаст дубль.
        root = pid or slug(base_name)
        candidate = root
        suffix = 2
        while candidate in existing:
            candidate = "%s-%d" % (root, suffix)
            suffix += 1
        profile = {"id": candidate, "name": base_name, "provider": normalize_provider(provider),
                   "model": "", "base_url": "", "key": ""}
        profiles.append(profile)

    if name:
        profile["name"] = name
    if provider:
        profile["provider"] = provider
        if not data.get("base_url") and provider != "custom":
            profile["base_url"] = PROVIDERS[provider]["base_url"]

    model = str(data.get("model") or "").strip()
    if model:
        profile["model"] = model

    base_url = str(data.get("base_url") or "").strip()
    if base_url:
        if not base_url.startswith(("http://", "https://")):
            common.fail(400, "Base URL должен начинаться с http:// или https://")
            return None
        profile["base_url"] = base_url

    key = str(data.get("key") or "").strip()
    if key:
        profile["key"] = key

    config["profiles"] = profiles
    config["active"] = profile["id"]
    if "voice_enabled" in data or "enabled" in data:
        value = common.truthy(data.get("voice_enabled", data.get("enabled")))
        config["voice_enabled"] = value
        config["enabled"] = value
    return profile


CHAT_NAME_LIMIT = 40


def clean_chat_name(raw):
    """Имя чата: без лишних пробелов, кавычек и управляющих символов."""
    name = " ".join(str(raw or "").split()).strip()
    return name.strip("\"'«»“”").strip()


def unique_chat_name(items, name):
    """Не давать двум чатам одинаковое имя: «Работа», «Работа 2», …"""
    base = name
    taken = {clean_chat_name(item.get("name")).casefold() for item in items}
    index = 2
    while name.casefold() in taken:
        name = "%s %d" % (base, index)
        index += 1
    return name


def chat_switch(data):
    chats = load_chats()
    items = chats.get("chats") or []
    current = chats.get("active")
    index = next((i for i, item in enumerate(items) if item.get("id") == current), 0)

    if common.truthy(data.get("chat_new")):
        name = clean_chat_name(data.get("chat_name"))
        if len(name) > CHAT_NAME_LIMIT:
            common.fail(413, "Имя чата длиннее %d символов" % CHAT_NAME_LIMIT)
            return None
        number = len(items) + 1
        chat_id = "chat-%d" % number
        while any(item.get("id") == chat_id for item in items):
            number += 1
            chat_id = "chat-%d" % number
        chat = {"id": chat_id, "name": name or ("Чат %d" % number), "messages": []}
        chat["name"] = unique_chat_name(items, chat["name"])
        items.append(chat)
        chats["active"] = chat["id"]
    elif data.get("chat_rename") is not None:
        target = str(data.get("chat_rename") or current)
        chat = next((item for item in items if item.get("id") == target), None)
        if chat is None:
            common.fail(404, "Чат не найден: %s" % target)
            return None
        name = clean_chat_name(data.get("chat_name"))
        if not name:
            common.fail(400, "Пустое имя чата")
            return None
        if len(name) > CHAT_NAME_LIMIT:
            common.fail(413, "Имя чата длиннее %d символов" % CHAT_NAME_LIMIT)
            return None
        others = [item for item in items if item.get("id") != target]
        chat["name"] = unique_chat_name(others, name)
    elif data.get("chat_delete") is not None:
        target = str(data.get("chat_delete") or current)
        items = [item for item in items if item.get("id") != target]
        if not items:
            items = [{"id": "chat-1", "name": "Чат 1", "messages": []}]
        if chats.get("active") == target:
            chats["active"] = items[min(index, len(items) - 1)]["id"]
    elif data.get("chat_select") is not None:
        target = str(data.get("chat_select"))
        if not any(item.get("id") == target for item in items):
            common.fail(404, "Чат не найден: %s" % target)
            return None
        chats["active"] = target
    else:
        delta = 1 if common.truthy(data.get("chat_next")) else -1
        chats["active"] = items[(index + delta) % len(items)]["id"]

    chats["chats"] = items
    save_chats(chats)
    return chats


def main():
    data = common.params()
    action_keys = ("prompt", "enabled", "voice_enabled", "activate", "delete", "provider", "name", "profile_id",
                   "max_tokens", "system_prompt", "error_messages_text", "models",
                   "chat_next", "chat_prev", "chat_new", "chat_select",
                   "chat_delete", "chat_rename")
    if common.truthy(data.get("info")) or not any(key in data for key in action_keys):
        common.respond(200, info())
        return

    config = load_config()

    if data.get("max_tokens") is not None:
        config["max_tokens"] = common.to_int(data.get("max_tokens"), 260, 50, 2000)
        save_config(config)
        common.respond(200, info(config))
        return

    if data.get("system_prompt") is not None:
        prompt = str(data.get("system_prompt") or "").strip()
        if len(prompt) > 4000:
            common.fail(413, "Промпт длиннее 4000 символов")
            return
        config["system_prompt"] = prompt
        save_config(config)
        common.respond(200, info(config))
        return

    if data.get("models") is not None:
        profile = active_profile(config)
        provider = data.get("provider") or (profile or {}).get("provider")
        models, source = fetch_models(profile, provider, data.get("base_url"))
        common.respond(200, {"ok": True, "models": models, "source": source,
                             "provider": normalize_provider(provider)})
        return

    if data.get("error_messages_text") is not None:
        messages = str(data.get("error_messages_text") or "")
        if len(messages) > 4000:
            common.fail(413, "Слишком длинный список сообщений об ошибках")
            return
        profile = active_profile(config)
        provider = (profile or {}).get("provider") or "openai"
        if not isinstance(config.get("error_messages"), dict):
            config["error_messages"] = {}
        if messages.strip():
            config["error_messages"][provider] = messages
        else:
            config["error_messages"].pop(provider, None)
        config.pop("error_messages_text", None)
        save_config(config)
        common.respond(200, info(config))
        return

    if any(key in data for key in ("chat_next", "chat_prev", "chat_new", "chat_select",
                                   "chat_delete", "chat_rename")):
        if chat_switch(data) is None:
            return
        common.respond(200, info(config))
        return

    if data.get("activate") is not None:
        pid = str(data.get("activate") or "").strip()
        if not any(item.get("id") == pid for item in config.get("profiles") or []):
            common.fail(404, "Профиль не найден: %s" % pid)
            return
        config["active"] = pid
        if "voice_enabled" in data or "enabled" in data:
            value = common.truthy(data.get("voice_enabled", data.get("enabled")))
            config["voice_enabled"] = value
            config["enabled"] = value
        save_config(config)
        common.respond(200, info(config))
        return

    if data.get("delete") is not None:
        pid = str(data.get("delete") or "").strip()
        config["profiles"] = [item for item in config.get("profiles") or [] if item.get("id") != pid]
        if config.get("active") == pid:
            config["active"] = config["profiles"][0]["id"] if config["profiles"] else None
        save_config(config)
        common.respond(200, info(config))
        return

    if data.get("prompt") is not None:
        prompt = str(data.get("prompt") or "").strip()
        if not prompt:
            common.fail(400, "Пустой запрос")
            return
        if len(prompt) > 4000:
            common.fail(413, "Запрос длиннее 4000 символов")
            return
        ask(prompt, data.get("system"))
        return

    # только тумблер голосовых вопросов, без правки профиля
    if ("voice_enabled" in data or "enabled" in data) and not any(
            key in data for key in ("provider", "name", "profile_id")):
        value = common.truthy(data.get("voice_enabled", data.get("enabled")))
        config["voice_enabled"] = value
        config["enabled"] = value
        save_config(config)
        common.respond(200, info(config))
        return

    profile = save_profile(config, data)
    if profile is None:
        return
    save_config(config)
    common.respond(200, info(config))


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
    except Exception as exc:  # noqa: BLE001
        try:
            common.fail(500, "Внутренняя ошибка llm.py: %s" % exc)
        except Exception:
            pass
