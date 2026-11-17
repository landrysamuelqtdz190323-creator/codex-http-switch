---
name: codex-http-switch
description: Diagnose Codex WebSocket retry loops, preview a reversible HTTP/SSE configuration switch, and apply or restore it when requested. For Codex ChatGPT-login inference, not ChatGPT web or Realtime.
---

# Codex HTTP Switch

Use the `codex-http-switch` CLI. If it is missing, obtain the program from `https://github.com/landrysamuelqtdz190323-creator/codex-http-switch` and install it in an appropriate Python environment when installation is within the user's request. The Skill alone does not install the program.

Start with `doctor --json` and `plan --json`; these are offline and read-only. Optional `doctor --logs-db <path>` returns error counts, not raw logs. A connection failure in a browser, WebSocket, CLI turn and model-catalog refresh are distinct evidence.

When the user has requested the switch and the plan matches that scope, run `apply --json`, retain the returned receipt path, and explain that the desktop client must be fully restarted before the original task is retried. Preserve API-key users, custom upstreams, model choices, MCP/plugin settings and unrelated changes. For keychain-only login, ask the user to identify the login mode rather than obtaining a token; `--auth-mode chatgpt` is appropriate only after that mode is established.

`verify` is an offline configuration check. `verify --online` sends a real request through the existing official client and consumes quota; use it when actual connection verification is authorized. It only verifies that short CLI turn. Do not equate a saved field, HTTP 200 or model-list success with a completed inference. Desktop features, Dot, hosted tools and long tasks require separate checks.

For restoration use `restore <receipt-path> --json`. If it reports a conflict, inspect the changed fields and preserve later user edits rather than copying an entire old config over the current one.

Keep auth files, config backups, raw request bodies and original conversation logs local. Use the project's README and docs/COMPATIBILITY.md for version and verification boundaries; no generic ChatGPT, Realtime, proxy, account or binary modification is implied by this workflow.
