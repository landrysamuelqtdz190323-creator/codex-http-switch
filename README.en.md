# Codex HTTP Switch

[中文说明](README.md) · [Research and references](docs/RESEARCH.md)

A small, reversible configuration tool for Codex users experiencing WebSocket retry loops. It selects HTTP/SSE inference using the same official OpenAI Codex backend and existing ChatGPT login. It does not run a relay, extract tokens, modify application binaries or change system proxy settings.

**This is a compatibility workaround, not a universal network fix.** ChatGPT web, Realtime and voice connections are outside its scope. API-key users and custom upstream providers are not automatically switched.

## Install and inspect

Python 3.11+ is required. This project is distributed through GitHub, not PyPI.

```bash
git clone https://github.com/landrysamuelqtdz190323-creator/codex-http-switch.git
cd codex-http-switch
python -m pip install .
codex-http-switch doctor
codex-http-switch plan
```

Use a virtual environment or pipx. `doctor` and `plan` are read-only and offline. The default path respects `CODEX_HOME`; otherwise it uses `~/.codex/config.toml`.

## Apply, restart, verify, restore

```bash
codex-http-switch apply
# Fully quit and reopen Codex before testing the original task.
codex-http-switch verify             # offline configuration check
codex-http-switch verify --online    # real request: uses login and quota
codex-http-switch restore "/path/returned/by/apply.receipt.json"
```

If credentials live in the OS keychain, first confirm that you use ChatGPT login, then use `plan --auth-mode chatgpt` or `apply --auth-mode chatgpt`. Do not supply tokens in commands or chat.

`apply` backs up the original file and changes only the provider selection and an owned profile. `restore` retains later unrelated edits and refuses conflicting provider changes. Backups may contain secrets from the original config: keep them private. POSIX modes are restricted; Windows ACLs remain the operator's responsibility.

The optional online test runs in an empty temporary directory and pins the inspected transport profile, while temporarily disabling extras for that process. Only a completed turn with the expected answer and no observed stream retry passes. It does not certify long tasks, desktop features, Dot, hosted tools or account UI. Custom profiles may behave differently from the built-in provider. See [compatibility](docs/COMPATIBILITY.md).

Current clients have removed old WebSocket feature flags and generally ignore transport overrides on the built-in `openai` ID. This tool uses a separate provider ID with `supports_websockets=false`. [Primary-source research](docs/RESEARCH.md) explains this decision and compares related projects; no third-party implementation was copied.

An optional agent Skill is provided under `skills/codex-http-switch`. Install the program first; installing the Skill alone does not install Python dependencies.

```bash
python -m unittest discover -s tests -v
```

No telemetry or automatic uploads. Do not attach auth files, full config, backups or raw conversations to issues. [Security](SECURITY.md). Independent community project, not affiliated with OpenAI. [MIT](LICENSE).
