#!/usr/bin/env python3
"""Descriptor-bound, size-limited clipboard history persistence."""
import json
import os
import secrets
import stat
import sys

MAX_HISTORY_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 300
MAX_TEXT_BYTES = 16 * 1024
STATE_DIR = os.path.join(
    os.environ.get("XDG_STATE_HOME", os.path.join(os.path.expanduser("~"), ".local", "state")),
    "omarchy-clipboard",
)
EMPTY = b'{"items":[]}\n'


def valid_state(data):
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(value, dict) or not isinstance(value.get("items"), list) or len(value["items"]) > MAX_ENTRIES:
        return False
    if "bootId" in value and not isinstance(value["bootId"], str):
        return False
    for item in value["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("pinned", False), bool):
            return False
        if "capturedAt" in item and (isinstance(item["capturedAt"], bool) or not isinstance(item["capturedAt"], (int, float))):
            return False
        if item.get("kind") == "text":
            if not isinstance(item.get("text"), str) or len(item["text"].encode("utf-8")) > MAX_TEXT_BYTES:
                return False
        elif item.get("kind") == "image":
            if not isinstance(item.get("path"), str) or len(item["path"]) > 4096:
                return False
            if not isinstance(item.get("mime"), str) or len(item["mime"]) > 128:
                return False
        else:
            return False
    return True


def open_state_dir():
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    fd = os.open(STATE_DIR, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        os.close(fd)
        raise PermissionError("unsafe state directory")
    return fd


def read_state(dirfd):
    try:
        fd = os.open("history.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dirfd)
    except FileNotFoundError:
        return EMPTY
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > MAX_HISTORY_BYTES:
            return EMPTY
        data = bytearray()
        while len(data) <= MAX_HISTORY_BYTES:
            chunk = os.read(fd, min(65536, MAX_HISTORY_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        data = bytes(data)
        return data if len(data) <= MAX_HISTORY_BYTES and valid_state(data) else EMPTY
    finally:
        os.close(fd)


def write_state(dirfd, data):
    if len(data) > MAX_HISTORY_BYTES or not valid_state(data):
        raise ValueError("invalid history state")
    name = ".history-" + secrets.token_hex(16)
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dirfd)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    except BaseException:
        os.unlink(name, dir_fd=dirfd)
        raise
    finally:
        os.close(fd)
    os.replace(name, "history.json", src_dir_fd=dirfd, dst_dir_fd=dirfd)
    os.fsync(dirfd)


action = sys.argv[1] if len(sys.argv) > 1 else ""
directory = None
try:
    directory = open_state_dir()
    if action == "read":
        sys.stdout.buffer.write(read_state(directory))
    elif action == "write":
        write_state(directory, sys.stdin.buffer.read(MAX_HISTORY_BYTES + 1))
    else:
        raise ValueError("read or write required")
except Exception:
    if action == "read":
        sys.stdout.buffer.write(EMPTY)
    else:
        raise
finally:
    if directory is not None:
        os.close(directory)
