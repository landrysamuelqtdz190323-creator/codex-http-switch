from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from . import __version__
from .core import SwitchError, apply, config_path, doctor, parse, plan, read, restore


def codex_binary(explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which("codex")
    if found:
        return found
    # Official desktop locations; no modified binary or token extraction.
    for path in (
        "/Applications/Codex.app/Contents/Resources/codex",
        "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
    ):
        if Path(path).is_file():
            return path
    raise SwitchError("Codex executable not found; pass --codex with the official client path.")


def verify(path: Path, online: bool, binary: str | None, timeout: int) -> dict:
    result = doctor(path)
    if result.get("status") != "already-http":
        raise SwitchError("An HTTP profile is not active in the selected config. Run doctor or plan first.")
    if not online:
        return {**result, "status": "config-valid", "message": "No network request sent. Use verify --online for a real, quota-consuming Codex turn."}
    if path != config_path():
        raise SwitchError("Online verification supports only the effective CODEX_HOME/config.toml, to avoid testing a different config or credential store.")
    doc = parse(read(path)).unwrap()
    args = [codex_binary(binary), "exec", "--ephemeral", "--json", "--skip-git-repo-check",
            "--sandbox", "read-only", "-c", 'model_reasoning_effort="low"', "-c", "features.apps=false"]
    # Pin the inspected user profile instead of accidentally testing a project override.
    provider = doc["model_provider"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", provider):
        raise SwitchError("This provider name cannot be passed safely to the diagnostic CLI.")
    args += ["-c", "model_provider=" + json.dumps(provider)]
    for key, value in doc["model_providers"][provider].items():
        if key in ("name", "base_url", "wire_api", "requires_openai_auth", "supports_websockets", "supports_standalone_web_search"):
            args += ["-c", f"model_providers.{provider}.{key}=" + json.dumps(value)]
    for section in ("mcp_servers", "plugins"):
        for key in doc.get(section, {}):
            if not re.fullmatch(r"[A-Za-z0-9_@/-]+", key):
                raise SwitchError("A plugin/MCP name cannot be isolated safely by this CLI version. Verification skipped; settings preserved.")
            args += ["-c", f"{section}.{key}.enabled=false"]
    args += ["Reply with exactly CODEX_HTTP_SWITCH_OK. Do not call tools or read files. This is a short connection diagnostic."]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="codex-http-switch-probe-") as work:
        proc = subprocess.Popen(args, cwd=work, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                start_new_session=(os.name != "nt"))
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                proc.kill()
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            proc.communicate()
            return {"status": "probe-failed", "completed": False, "reason": "timeout", "network_tested": True}
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
        except ValueError:
            pass
    replies = [e["item"].get("text", "").strip() for e in events
               if isinstance(e.get("item"), dict) and e["item"].get("type") == "agent_message"]
    retries = bool(re.search(r"stream disconnected|retrying sampling", stderr, re.I))
    completed = proc.returncode == 0 and any(e.get("type") == "turn.completed" for e in events)
    passed = completed and replies == ["CODEX_HTTP_SWITCH_OK"] and not retries
    # Deliberately omit raw model output, stderr, tool content and credentials.
    return {"status": "probe-passed" if passed else "probe-failed", "completed": completed,
            "expected_reply_received": replies == ["CODEX_HTTP_SWITCH_OK"],
            "stream_retry_observed": retries, "exit_code": proc.returncode,
            "duration_seconds": round(time.monotonic() - started, 2), "network_tested": True,
            "scope": "short CLI inference only; desktop and long-task behavior require separate checks"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Codex HTTP Switch — reversible HTTP/SSE configuration for ChatGPT-login users.")
    parser.add_argument("--version", action="version", version=__version__)
    subs = parser.add_subparsers(dest="command", required=True)
    for command in ("doctor", "plan", "apply", "restore", "verify"):
        sub = subs.add_parser(command)
        sub.add_argument("--config", help="Existing config.toml; defaults to CODEX_HOME or ~/.codex")
        sub.add_argument("--json", action="store_true", help="Machine-readable output")
        if command in ("plan", "apply"):
            sub.add_argument("--auth-mode", choices=("auto", "chatgpt"), default="auto",
                             help="Explicitly confirm ChatGPT login when credentials live in the OS keychain")
        if command == "doctor":
            sub.add_argument("--logs-db", type=Path, help="Optional local Codex logs_2.sqlite; counts only, opened read-only")
        if command == "restore":
            sub.add_argument("receipt", type=Path)
        if command == "verify":
            sub.add_argument("--online", action="store_true", help="Send a real, quota-consuming ephemeral Codex request")
            sub.add_argument("--codex", help="Path to the official Codex executable")
            sub.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    path = config_path(args.config)
    try:
        if args.command == "doctor":
            result = doctor(path, args.logs_db)
        elif args.command == "plan":
            result = plan(path, args.auth_mode)
        elif args.command == "apply":
            result = apply(path, args.auth_mode)
        elif args.command == "restore":
            result = restore(path, args.receipt.expanduser().absolute())
        else:
            if not 1 <= args.timeout <= 600:
                raise SwitchError("Timeout must be between 1 and 600 seconds.")
            result = verify(path, args.online, args.codex, args.timeout)
    except (SwitchError, OSError) as e:
        # Filesystem exceptions show paths at most; avoid TOML/CLI credential dumps.
        result = {"status": "error", "message": str(e) if isinstance(e, SwitchError) else "Filesystem or process error; settings preserved where possible. Check local permissions and executable availability."}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Codex HTTP Switch:", result["status"])
        for key, value in result.items():
            if key != "status":
                print(f"  {key}: {value}")
        if result.get("restart_required"):
            print("  Next: fully quit and reopen Codex, then resume the original task.")
    return 1 if result["status"] in ("error", "probe-failed", "needs-attention") else 0
