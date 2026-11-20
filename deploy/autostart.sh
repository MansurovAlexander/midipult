#!/bin/sh
# Создать /etc/init.d/S99mypult, если rootfs read-only.
# Вызывается установщиком; можно запускать вручную.
#
# Шим обязан передавать аргументы как есть: rcS вызывает его с «start»,
# а ручные `stop`/`status`/`reload` через /etc/init.d не должны запускать
# пульт заново. Старые шимы (без «$@») перезаписываются при обновлении.

SHIM="/etc/init.d/S99mypult"
TARGET="/opt/etc/init.d/S99mypult"

[ -x "$TARGET" ] || {
    echo "нет $TARGET — сначала установите пульт" >&2
    exit 1
}

if [ -x "$SHIM" ] && grep -q "$TARGET" "$SHIM" 2>/dev/null; then
    if grep -q '"\$@"' "$SHIM" 2>/dev/null; then
        echo "автозапуск уже настроен: $SHIM"
        exit 0
    fi
    echo "обновляю $SHIM: старый шим не передавал аргументы"
fi

write_shim() {
    cat > "$SHIM" <<'EOF'
#!/bin/sh
# Автозапуск пульта Станции Миди (шим на ro-rootfs).
# Аргументы передаются как есть: start / stop / status / reload.
exec /opt/etc/init.d/S99mypult "$@"
EOF
    chmod 755 "$SHIM"
}

# `-w` на ro-rootfs врёт: root «может писать» по правам, но ФС только для
# чтения. Поэтому пробуем записать и только потом идём в remount — иначе
# установка печатает «Read-only file system» как ошибку.
if write_shim 2>/dev/null; then
    echo "создан $SHIM" && exit 0
fi

echo "rootfs read-only, пробую remount rw…"
if ! mount -o remount,rw / 2>/dev/null; then
    echo "не удалось remount rw. Создайте вручную:" >&2
    echo "  mount -o remount,rw /" >&2
    echo '  написать в /etc/init.d/S99mypult: exec /opt/etc/init.d/S99mypult "$@"' >&2
    echo "  mount -o remount,ro /" >&2
    exit 1
fi

trap 'mount -o remount,ro / 2>/dev/null' EXIT INT TERM
if write_shim; then
    sync
    echo "создан $SHIM"
    mount -o remount,ro / 2>/dev/null
    trap - EXIT INT TERM
    exit 0
fi

echo "не удалось записать $SHIM" >&2
exit 1
