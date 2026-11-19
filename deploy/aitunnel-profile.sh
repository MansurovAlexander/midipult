#!/bin/sh
# Создаёт (или обновляет) профиль AITUNNEL в MidiPult и делает его активным.
# Запускать НА КОЛОНКЕ:
#
#   sh deploy/aitunnel-profile.sh sk-aitunnel-xxx [base_url] [model]
#
# Ключ не печатается и не сохраняется в командной строке после вызова.

set -eu

KEY=${1:-}
if [ -z "$KEY" ]; then
    echo "usage: $0 <api-key> [base_url] [model]" >&2
    exit 2
fi

BASE=${2:-https://api.aitunnel.ru/v1}
MODEL=${3:-deepseek-v4.1-flash-1017}
ORIGIN="http://127.0.0.1:8055"
URL="$ORIGIN/cgi-bin/llm.py"

CURL=/opt/bin/curl
[ -x "$CURL" ] || CURL=curl

BODY=$(printf '{"profile_id":"aitunnel","name":"AITUNNEL DeepSeek V4.1 Flash","provider":"custom","model":"%s","base_url":"%s","key":"%s"}' \
    "$MODEL" "$BASE" "$KEY")

"$CURL" -s -X POST "$URL" \
    -H "Content-Type: application/json" \
    -H "Origin: $ORIGIN" \
    -d "$BODY" >/dev/null

"$CURL" -s -X POST "$URL" \
    -H "Content-Type: application/json" \
    -H "Origin: $ORIGIN" \
    -d '{"enabled":1}' >/dev/null

echo "ok: профиль aitunnel сохранён и активен, голосовой тумблер включён"
echo "проверка: $CURL -s '$URL?info=1'"
