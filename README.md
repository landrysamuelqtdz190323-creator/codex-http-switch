# Codex HTTP Switch · 连接模式切换助手

[English](README.en.md) · [同类项目与依据](docs/RESEARCH.md) · [兼容性与边界](docs/COMPATIBILITY.md) · [Skill](skills/codex-http-switch/SKILL.md)

Codex 一直显示 `Reconnecting 1/5…5/5`，日志里出现 `websocket closed by server before response.completed`？

这个小工具帮助你诊断重试、预览配置，并可回滚地将 **Codex 的推理传输切换到 HTTP/SSE**。适用于使用 ChatGPT 登录的 Codex 用户。它保留 OpenAI 官方后端和现有登录，不启动本地中转代理，不提取或复制登录令牌。

**这是一种兼容方案，不是所有断连的通用解法。** HTTP 自身的超时、服务端错误、限额和网络波动仍可能发生。它也不修改 ChatGPT 网页、Realtime 或语音连接。

## 为什么做这个项目

普通网页或 YouTube 能打开，只能证明对应请求可用，不能证明 Codex 的 WebSocket 长连接稳定。另一方面，“HTTP 200”或模型列表能打开，也不能证明一次推理已经完整结束。

已有相关项目包括 [codex-proxy-launcher](https://github.com/MrWynn/codex-proxy-launcher)、[codex-helper](https://github.com/Latias94/codex-helper)、[codex-ws-proxy](https://github.com/Avilianb/codex-ws-proxy) 和 [codex-deepseek-bridge](https://github.com/JetXu-LLM/codex-deepseek-bridge)。本项目参考了它们的进程范围、诊断、可逆修改和恢复思路，独立实现配置切换，不复制其代理或补丁代码。[完整对比与许可证核对](docs/RESEARCH.md)

## 安装

需要 **Python 3.11+**。项目目前通过 GitHub 分发，尚未发布到 PyPI。

```bash
git clone https://github.com/landrysamuelqtdz190323-creator/codex-http-switch.git
cd codex-http-switch
python -m pip install .
codex-http-switch --version
```

推荐在虚拟环境中安装，或使用已安装的 `pipx install .`。Windows 可按本机 Python 安装方式把 `python` 替换为 `py -3.11`。

## 从只读检查开始

```bash
codex-http-switch doctor
codex-http-switch plan
```

`doctor` 和 `plan` 不修改配置，也不发送网络请求。默认配置路径是 `$CODEX_HOME/config.toml`；未设置时使用 `~/.codex/config.toml`。

```bash
# 指定配置文件；路径带空格时加引号
codex-http-switch plan --config "/path/to/config.toml" --json

# 可选：只读统计最近24小时的连接错误，不输出原始日志或对话
codex-http-switch doctor --logs-db "/path/to/logs_2.sqlite" --json
```

## 切换与恢复

确认计划符合你的需求后执行：

```bash
codex-http-switch apply
```

工具会保存原配置和恢复凭据，然后只增加一个自有提供商条目，并选择它。模型、上下文、MCP、插件和现有代理设置保留。**配置备份可能含有原文件中的敏感信息，仅保留在本地，不要上传。**

如果登录保存在操作系统钥匙串中，工具可能无法从 `auth.json` 判断认证方式。确认自己使用的是 ChatGPT 登录后，可显式声明：

```bash
codex-http-switch plan --auth-mode chatgpt
codex-http-switch apply --auth-mode chatgpt
```

切换后完全退出并重新打开 Codex，回到原任务复测。不要仅凭文件已保存就判断原会话已切换。项目配置、命令行 profile、组织策略和既有会话设置可能有不同优先级。

```bash
# 用 apply 返回的实际 receipt 路径恢复
codex-http-switch restore "/path/to/.http-switch-backups/GENERATED-ID.receipt.json"
```

恢复只撤销本工具拥有的字段，保留你后来修改的模型或 MCP 等无关设置。如果提供商选择或自有条目已被改动，工具会拒绝覆盖，交由你检查。它不会把整份旧配置直接覆盖回来。重复 `apply` 到已识别的 HTTP 配置是空操作。

## 验证，分清静态配置和实际请求

```bash
# 仅验证配置，不联网
codex-http-switch verify

# 明确选择联网：使用现有 Codex 登录和额度发送一次真实短请求
codex-http-switch verify --online

# 自动发现失败时指定官方 Codex 可执行文件
codex-http-switch verify --online --codex "/path/to/codex"
```

在线检查要求客户端支持 `exec --ephemeral --json`，并只接受有效 `CODEX_HOME` 下的配置。它在临时空目录运行，临时固定已检查的传输参数，关闭该诊断进程中的 MCP/插件，不改它们的保存状态。客户端仍可能加载自己的全局指令或技能元数据；请求发送到原 OpenAI 官方后端，消耗相应额度。

只有收到 `turn.completed`、预期回复且未观察到流式重试，才报告短请求通过。不输出原始模型内容、stderr 或凭据。**这不等于已验证长任务、桌面侧栏、Dot、托管工具或全部账号功能。**

## 实际修改

```toml
model_provider = "openai-http-switch"

[model_providers.openai-http-switch]
name = "OpenAI"
base_url = "https://chatgpt.com/backend-api/codex"
wire_api = "responses"
requires_openai_auth = true
supports_websockets = false
supports_standalone_web_search = true
```

为什么不直接写 `features.responses_websockets=false`？当前官方实现已移除旧开关；内置 `openai` 项也不接受一般传输覆盖。自定义条目是这里使用的路径，**同厂商不代表客户端所有功能完全等价**。[官方机制与版本边界](docs/RESEARCH.md#当前-codex-配置机制)

## 在 Codex 中使用 Skill

先安装上面的程序，再让 Codex 安装：

```text
$skill-installer install https://github.com/landrysamuelqtdz190323-creator/codex-http-switch/tree/main/skills/codex-http-switch
```

下一轮对话可说：

```text
使用 $codex-http-switch，先检查我的重连问题，展示切换计划。
```

Skill 是程序的调用说明，单独安装 `SKILL.md` 不会安装 Python 程序。

## 保护配置的边界

- 自定义上游、API-key 登录、未知认证模式、同名条目冲突，默认保留并拒绝自动切换。
- 配置符号链接不会被替换；如需处理，可用 `--config` 指定真实目标文件。
- 写入前检查并发修改，采用同目录原子替换。锁保护本工具的并发操作；不能保证与所有外部编辑器之间实现原子比较交换。
- 在 POSIX 系统上，备份目录使用 0700、备份文件使用 0600。Windows 的实际访问控制还依赖目录 ACL，不把 chmod 当作 ACL 保障。
- 本工具不改变系统代理、证书验证、应用签名或组织策略。没有遥测，没有自动上传日志。

## 开发与反馈

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

测试覆盖只读计划、幂等、敏感字段不出诊断、备份校验、并发编辑、受保护恢复及真实请求判定。跨平台 CI 只证明自动测试覆盖的行为，不代表所有桌面版本都完成了实机验证。

反馈问题时提供客户端版本、系统、匿名化错误类型和重现步骤；不要提交 `auth.json`、完整配置、备份或原始对话。详见 [SECURITY.md](SECURITY.md)。

独立社区项目，与 OpenAI 无隶属关系。代码使用 [MIT](LICENSE) 许可证。
