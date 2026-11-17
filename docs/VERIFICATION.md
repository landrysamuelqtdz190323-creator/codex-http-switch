# 首版验证记录

日期：2026-11-16。此记录不含原始个人配置、凭据、账号标识或私人对话。

## 本地行为测试

使用 Python 3.12 运行 `python -m unittest discover -s tests -v`。覆盖：只读计划、幂等、后续配置保留、恢复冲突、篡改备份、收据作用域、符号链接、无效 TOML、并发编辑检查、API-key 模式拒绝、日志输出脱敏和在线请求判定。

单元测试中的输入、密钥标记及日志内容都是合成测试数据。

## 最终命令的真实短请求

在 macOS arm64、Codex CLI `0.169.0-alpha.11.1` 上，对本机已有 HTTP 配置运行了本项目的 `verify --online --json`。未再修改该机器配置，客户端使用既有登录。

结果摘要：

```json
{
  "status": "probe-passed",
  "completed": true,
  "expected_reply_received": true,
  "stream_retry_observed": false,
  "exit_code": 0,
  "duration_seconds": 8.54,
  "network_tested": true
}
```

这个结果只说明这一次短 CLI 请求完成。8.54 秒不是其他机器或任务的速度承诺；没有把它当作长任务、桌面侧栏、Dot 或托管工具的验收。Windows/Linux 的真实登录和网络路径没有在这台机器上实测。

## 包和自动化

本地已构建 sdist 与 Python wheel，并检查命令入口和 Skill 格式。仓库配置跨平台 CI；其结果应以 GitHub Actions 实际运行状态为准，而非此文档预先宣称。
