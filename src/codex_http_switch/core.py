from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid

import tomlkit

ALIAS = "openai-http-switch"
BACKUPS = ".http-switch-backups"
ENDPOINT = "https://chatgpt.com/backend-api/codex"
PROFILE = {
    "name": "OpenAI",  # The client uses this identity for OpenAI backend routes.
    "base_url": ENDPOINT,
    "wire_api": "responses",
    "requires_openai_auth": True,
    "supports_websockets": False,
    "supports_standalone_web_search": True,
}


class SwitchError(Exception):
    """An actionable error safe to show without echoing configuration values."""


def config_path(value: str | None = None) -> Path:
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    return Path(value).expanduser().absolute() if value else (home / "config.toml").absolute()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parse(raw: bytes):
    try:
        return tomlkit.parse(raw.decode("utf-8"))
    except (UnicodeError, ValueError, tomlkit.exceptions.ParseError):
        raise SwitchError("Invalid TOML; no changes made. Fix the syntax locally first.") from None


def read(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise SwitchError("Config must be an existing regular file, not a symlink. Use --config with its actual target.")
    try:
        return path.read_bytes()
    except OSError:
        raise SwitchError("Cannot read the selected config file.") from None


def auth_mode(path: Path) -> str:
    """Read only auth-file metadata; never return or copy credential values."""
    if os.environ.get("OPENAI_API_KEY"):
        return "api-key"
    try:
        data = json.loads((path.parent / "auth.json").read_text())
    except (OSError, ValueError):
        return "unknown"
    if not isinstance(data, dict):
        return "unknown"
    mode = data.get("auth_mode")
    if mode in ("chatgpt", "chatgptAuthTokens"):
        return "chatgpt"
    if mode in ("apikey", "api_key") or data.get("OPENAI_API_KEY"):
        return "api-key"
    if isinstance(data.get("tokens"), dict) and data["tokens"].get("access_token"):
        return "chatgpt"
    return "unknown"


def is_http_profile(profile) -> bool:
    return isinstance(profile, dict) and all(profile.get(k) == v for k, v in PROFILE.items())


def plan(path: Path, declared_auth: str = "auto") -> dict:
    doc = parse(read(path)).unwrap()
    provider = doc.get("model_provider", "openai")
    profiles = doc.get("model_providers", {})
    if not isinstance(provider, str):
        raise SwitchError("model_provider must be a provider name.")
    if not isinstance(profiles, dict):
        raise SwitchError("model_providers must be a TOML table.")
    detected = auth_mode(path)
    if detected == "api-key":
        raise SwitchError("API-key authentication was detected; it will not be routed to the ChatGPT backend.")
    # Current clients ignore general transport overrides on the built-in ID.
    if provider != "openai" and is_http_profile(profiles.get(provider)):
        return {"status": "already-http", "changes": [], "restart_required": False}
    if provider != "openai":
        raise SwitchError("A custom provider is active. It is preserved; this tool switches only the built-in OpenAI provider.")
    if ALIAS in profiles:
        raise SwitchError("The tool's provider name already exists. Resolve the conflict locally; it will not be overwritten.")
    builtin = profiles.get("openai", {})
    if not isinstance(builtin, dict):
        raise SwitchError("The OpenAI provider entry must be a table.")
    for value in (doc.get("openai_base_url"), builtin.get("base_url")):
        if value and str(value).rstrip("/") != ENDPOINT:
            raise SwitchError("A custom OpenAI endpoint is configured. It is preserved; automatic switching is refused.")
    mode = detected if declared_auth == "auto" else declared_auth
    if mode != "chatgpt":
        raise SwitchError("This release supports ChatGPT login only. If login lives in the OS keychain, confirm it locally and use --auth-mode chatgpt. API-key and unknown modes are preserved.")
    return {"status": "change-proposed", "changes": ["select HTTP/SSE provider", "add owned OpenAI HTTP profile"],
            "endpoint": ENDPOINT, "profile": ALIAS, "restart_required": True}


@contextlib.contextmanager
def lock(path: Path):
    p = path.with_name(path.name + ".http-switch.lock")
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise SwitchError("Another switch operation (or a stale lock) exists. No changes made.") from None
    try:
        os.close(fd)
        yield
    finally:
        p.unlink(missing_ok=True)


def private_write(path: Path, raw: bytes):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def replace(path: Path, old: bytes, new: bytes):
    """Atomic replacement, with an optimistic edit check immediately beforehand."""
    fd, temp = tempfile.mkstemp(prefix="." + path.name + ".http-switch-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(new)
            f.flush()
            os.fsync(f.fileno())
        if read(path) != old:
            raise SwitchError("The config changed during this operation. No overwrite performed.")
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def apply(path: Path, declared_auth: str = "auto") -> dict:
    with lock(path):
        old = read(path)
        proposed = plan(path, declared_auth)
        if read(path) != old:
            raise SwitchError("The config changed during planning. No changes made.")
        if proposed["status"] == "already-http":
            return proposed
        doc = parse(old)
        doc["model_provider"] = ALIAS
        if "model_providers" not in doc:
            doc["model_providers"] = tomlkit.table()
        table = tomlkit.table()
        table.add(tomlkit.comment("Managed by codex-http-switch; restore using the returned receipt."))
        for k, v in PROFILE.items():
            table.add(k, v)
        doc["model_providers"][ALIAS] = table
        new = tomlkit.dumps(doc).encode()
        folder = path.parent / BACKUPS
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
            raise SwitchError("Backup directory is not a regular directory; no changes made.")
        folder.mkdir(mode=0o700, exist_ok=True)
        if os.name != "nt":
            folder.chmod(0o700)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:10]
        backup = folder / (stamp + ".toml")
        receipt = folder / (stamp + ".receipt.json")
        state = {"tool": "codex-http-switch", "schema": 1, "config": str(path),
                 "backup_file": backup.name, "before_sha256": digest(old), "after_sha256": digest(new),
                 "profile": ALIAS}
        # A manifest is written before replacing config so recovery data survives a crash.
        private_write(backup, old)
        private_write(receipt, (json.dumps(state, indent=2) + "\n").encode())
        replace(path, old, new)
        return {"status": "applied", "receipt": str(receipt), "backup": str(backup),
                "restart_required": True, "changes": proposed["changes"]}


def restore(path: Path, receipt_path: Path) -> dict:
    with lock(path):
        if receipt_path.is_symlink() or receipt_path.parent.resolve() != (path.parent / BACKUPS).resolve():
            raise SwitchError("Receipt must be a regular file in this config's private backup directory.")
        try:
            state = json.loads(receipt_path.read_text())
        except (OSError, ValueError):
            raise SwitchError("Cannot read the receipt.") from None
        if (not isinstance(state, dict) or state.get("tool") != "codex-http-switch" or state.get("schema") != 1
                or state.get("profile") != ALIAS or state.get("config") != str(path)):
            raise SwitchError("Receipt does not match this configuration.")
        name = state.get("backup_file", "")
        if not isinstance(name, str) or not name or Path(name).name != name:
            raise SwitchError("Invalid backup filename.")
        backup = receipt_path.parent / name
        original = read(backup)
        if digest(original) != state.get("before_sha256"):
            raise SwitchError("Backup checksum mismatch; no changes made.")
        before = parse(original)
        old = read(path)
        current = parse(old)
        profiles = current.get("model_providers", {})
        if (not isinstance(profiles, dict) or current.get("model_provider") != ALIAS
                or not isinstance(profiles.get(ALIAS), dict) or dict(profiles[ALIAS]) != PROFILE):
            raise SwitchError("Provider selection or owned profile changed after apply. Resolve it locally; no overwrite performed.")
        if "model_provider" in before:
            current["model_provider"] = before["model_provider"]
        else:
            del current["model_provider"]
        del current["model_providers"][ALIAS]
        if not current["model_providers"] and "model_providers" not in before:
            del current["model_providers"]
        replace(path, old, tomlkit.dumps(current).encode())
        return {"status": "restored", "restart_required": True,
                "unrelated_current_settings_preserved": True}


def log_summary(db: Path) -> dict:
    """No prompt, token, account ID or entire log body leaves this function."""
    if not db.is_file():
        return {"available": False}
    since = int(dt.datetime.now(dt.timezone.utc).timestamp()) - 86400
    try:
        with contextlib.closing(sqlite3.connect(db.absolute().as_uri() + "?mode=ro", uri=True, timeout=2)) as conn:
            rows = conn.execute("SELECT ts,feedback_log_body FROM logs WHERE ts>=? AND target IN "
                                "('codex_core::responses_retry','codex_core::client') ORDER BY id DESC LIMIT 200",
                                (since,)).fetchall()
    except sqlite3.Error:
        return {"available": False, "reason": "Unsupported or unavailable log database"}
    websocket = sum("websocket closed" in (b or "").lower() for _, b in rows)
    return {"available": True, "lookback_hours": 24, "matching_websocket_errors": websocket,
            "broken_pipe_errors": sum("broken pipe" in (b or "").lower() for _, b in rows),
            "http_fallback_events": sum("falling back to HTTP" in (b or "") for _, b in rows),
            "raw_log_bodies_included": False}


def doctor(path: Path, logs_db: Path | None = None) -> dict:
    result = {"config_exists": path.is_file(), "config_symlink": path.is_symlink(),
              "auth_mode": auth_mode(path), "network_tested": False}
    try:
        result.update(plan(path))
    except (SwitchError, OSError) as e:
        result.update(status="needs-attention", message=str(e))
    if logs_db:
        result["logs"] = log_summary(logs_db)
    return result
