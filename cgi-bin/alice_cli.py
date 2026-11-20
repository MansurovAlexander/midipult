#!/opt/bin/python3
# -*- coding: utf-8 -*-
"""Алиса через отладочный CLI `maind --cli` (идея из yapanel-web).

CLI принимает строки-команды:
    c — отменить диалог (быстро, локально);
    s — начать диалог (микрофон включается без «Алисы»);
    q — текстовый запрос, следующая строка — текст;
    o — пауза плеера; l/n — трек; x — выход.

Важно: если закрыть stdin, CLI завершает диалог. Поэтому для «слушать» держим
процесс открытым (сессия) и закрываем только после ответа. Для отмены хватает
короткого процесса.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time

QUASAR = "/system/vendor/quasar"
MAIND = os.path.join(QUASAR, "maind")
LIBS = os.path.join(QUASAR, "libs")
START_DELAY = 0.35
CLOSE_DELAY = 0.5

_lock = threading.Lock()
_session = None


def available():
    return os.path.isfile(MAIND) and os.access(MAIND, os.X_OK)


def _spawn():
    if not available():
        raise RuntimeError("нет %s" % MAIND)
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = LIBS
    return subprocess.Popen(
        [MAIND, "--cli"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
        close_fds=True,
    )


def _write(proc, line):
    try:
        proc.stdin.write((line + "\n").encode("utf-8"))
        proc.stdin.flush()
    except (BrokenPipeError, OSError, ValueError):
        pass


def _close(proc, timeout=2.0):
    try:
        proc.stdin.close()
    except (OSError, ValueError):
        pass
    try:
        proc.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=1.0)
        return
    except (subprocess.TimeoutExpired, OSError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def close_session(cancel=True):
    """Закрыть удерживаемую сессию.

    cancel=True (по умолчанию) отправляет станции «c» и даёт ей сыграть
    штатный сигнал отмены — так делаем только при тишине/сбое.
    cancel=False просто закрывает stdin: диалог уже завершён, лишний звук
    завершения после распознанной фразы не нужен.
    """
    global _session
    with _lock:
        proc, _session = _session, None
        if proc is None:
            return False
        if cancel:
            _write(proc, "c")
            time.sleep(CLOSE_DELAY)
        _close(proc)
        return True


def listen():
    """Начать диалог и держать его открытым до close_session()."""
    global _session
    with _lock:
        if _session is not None:
            _close(_session)
            _session = None
        proc = _spawn()
        time.sleep(START_DELAY)
        _write(proc, "s")
        _session = proc
    return True


def cancel():
    """Отменить текущий диалог."""
    if _session is not None:
        return close_session()
    proc = _spawn()
    try:
        time.sleep(START_DELAY)
        _write(proc, "c")
        time.sleep(CLOSE_DELAY)
    finally:
        _close(proc)
    return True


def query(text):
    """Текстовый запрос к Алисе (аналог набора в приложении)."""
    text = " ".join(str(text or "").split())
    if not text:
        raise ValueError("пустой запрос")
    proc = _spawn()
    try:
        time.sleep(START_DELAY)
        _write(proc, "q")
        time.sleep(0.5)
        _write(proc, text)
        time.sleep(0.5)
    finally:
        _close(proc, timeout=20.0)
    return True
