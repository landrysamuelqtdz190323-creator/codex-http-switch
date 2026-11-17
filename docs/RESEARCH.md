# 同类项目与实现依据

检索日期：2026-11-16，Asia/Taipei。以下依据官方仓库的 README、清单、源码和问题记录；没有执行这些项目的安装脚本，也没有复制其实现代码。仓库功能介绍不等于本项目已完成对它们的运行验证。

## 找到了哪些相关项目

| 项目 | 已核对的功能与许可 | 值得参考 | 与本项目的边界 |
| --- | --- | --- | --- |
| [MrWynn/codex-proxy-launcher](https://github.com/MrWynn/codex-proxy-launcher) | 为 Codex Desktop 设置进程级 HTTP_PROXY、HTTPS_PROXY、ALL_PROXY；提供 start/stop/restart/status/log；支持 macOS、Windows。MIT。 | 把连接配置限制在目标应用，并提供清晰的状态和生命周期命令。 | 它让 HTTP 和 WebSocket 使用指定代理，不负责将推理传输切到 HTTP/SSE。Windows Store 启动方式还涉及临时用户环境变量。本项目不借此改系统或用户代理。 |
| [Latias94/codex-helper](https://github.com/Latias94/codex-helper) | 本地中转代理、多个上游和客户端预设，提供能力检查、重试观察、可逆客户端 patch。Cargo.toml 声明 MIT OR Apache-2.0；根目录未见独立 LICENSE 文件。 | 分开报告配置、真实请求和能力状态；明确代理归属、退出及撤销行为。 | 它可改变上游路由和身份形态，部分预设涉及 auth facade 与第三方密钥。本项目不实现 relay、不改 auth.json、不记录请求内容。 |
| [Avilianb/codex-ws-proxy](https://github.com/Avilianb/codex-ws-proxy) | 默认分支为 codex-ws-proxy。接受本机 Responses WebSocket，将其转成上游 HTTP POST + SSE；移除传入身份头并注入独立上游密钥。检索时 README 和根目录未见许可声明。 | 明确区分“客户端仍用 WS、代理向上游用 SSE”与“客户端直接选 HTTP”两种方案。 | 这是持有上游凭据的协议桥，不是配置切换工具。涉及请求字段和身份头改写，不适合作为本项目的轻量实现依赖；没有明确许可时也不复制代码。 |
| [JetXu-LLM/codex-deepseek-bridge](https://github.com/JetXu-LLM/codex-deepseek-bridge) | 本地 Responses 兼容桥，让 Codex 使用 DeepSeek；setup 使用可逆配置块，提供 restore、doctor 和报告。Apache-2.0。 | 可重复 setup、可恢复的修改、密钥不经命令行传参，以及清晰区分普通配置和桌面补丁。 | 它切换到 DeepSeek 上游，另有可选桌面程序补丁。本项目保留 OpenAI 官方后端，不修改应用包，不重签名，不增加密钥存储。 |

功能与许可的直接出处：[launcher README](https://github.com/MrWynn/codex-proxy-launcher/blob/main/README.md)、[launcher LICENSE](https://github.com/MrWynn/codex-proxy-launcher/blob/main/LICENSE)；[helper README](https://github.com/Latias94/codex-helper/blob/main/README.md)、[helper Cargo.toml](https://github.com/Latias94/codex-helper/blob/main/Cargo.toml)；[WS bridge README](https://github.com/Avilianb/codex-ws-proxy/blob/codex-ws-proxy/README.md)；[DeepSeek bridge README](https://github.com/JetXu-LLM/codex-deepseek-bridge/blob/main/README.md)、[LICENSE](https://github.com/JetXu-LLM/codex-deepseek-bridge/blob/main/LICENSE)。

这次检索确认了代理启动器、协议桥和可逆配置管理工具；没有据此声称 GitHub 上不存在其他同类方案。它们的目标和信任边界不同，不能把任意“WS→SSE 代理”当作原账号原后端的直接替代。

## 当前 Codex 配置机制

1. **旧开关已经移除。** 官方 [features 源码](https://github.com/openai/codex/blob/main/codex-rs/features/src/lib.rs)把 responses_websockets 和 responses_websockets_v2 标为 Stage::Removed；false 不能被当作当前传输已禁用的证明。
2. **内置 openai 项不能一般性覆盖。** 官方 [model-provider-info 源码](https://github.com/openai/codex/blob/main/codex-rs/model-provider-info/src/lib.rs)的 merge_configured_model_providers 保留内置 OpenAI 的身份、推理路由与认证，一般只接收该项的模型目录 URL 覆盖。不能把写入 model_providers.openai.supports_websockets=false 本身当作修复成功。
3. **自定义提供商可以选择 HTTP。** 同一源码定义 supports_websockets，并允许非保留 ID 扩展提供商；requires_openai_auth 启用原有 OpenAI 登录机制，name=OpenAI 参与 OpenAI 身份判断。ChatGPT 认证对应的默认后端为 https://chatgpt.com/backend-api/codex。[官方 app-server 说明](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations#codex-app-server-behavior)也明确 supports_websockets=false 在其配置中选择 HTTP/SSE。这里支持的是特定配置路径，不是对所有桌面版本的保证。
4. **自定义项不代表功能完全等价。** 官方仓库的 [问题 #57000](https://github.com/openai/codex/issues/57000)记录过 HTTPS-only 提供商配置与 Dot 侧栏可见性的交互；该报告后来关闭，仍说明不能用一次短推理成功推断账号界面、Dot、托管工具和全部历史会话能力都相同。

## 本项目吸收的做法

- 聚焦 Codex 的推理传输配置；不提供通用 ChatGPT 网页、Realtime 或语音连接修复。
- 默认只读诊断与计划，切换时仅修改必要字段，保留模型、上下文、MCP、插件和现有代理设置。
- 备份采用私有权限，恢复时检查冲突并保留后续无关修改，避免整份旧配置覆盖新设置。
- 区分“配置存在”“配置有效”“真实请求完整完成”；在线验证需用户显式选择，并说明会使用登录及额度。
- 不运行代理、不托管 token、不收集原始对话或完整日志；不因 HTTP 200、模型列表或工具注册成功就宣布流式请求恢复。
- 把 HTTP-only 作为可回滚的兼容方案；重启后仍需原任务复测，HTTP/SSE 自身的超时、服务端错误和限额问题不会自动消失。
