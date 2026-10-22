# ModelProbe 模型接口回归评测工具

一个纯 Python 的模型 API 接入与格式回归工具，包含请求适配、有界并发、超时、有限重试、结构化输出检查与 JSON/HTML 报告。用于练习 AI 应用的测试和工程交付。

## 离线开始

需要 Python 3.10+，没有第三方依赖。以下命令启动本机模拟服务，不调用真实模型、不需要密钥：

```bash
python -m model_probe demo --workers 3 --output reports/demo.json
python -m unittest discover -s tests -v
```

打开生成的 `reports/demo.html` 查看报告。内置 **12 个用例**，覆盖 JSON 字段、字段类型、关键词、429/503 后恢复、鉴权失败、协议损坏和空响应。

模拟服务会故意制造失败，所以演示报告里部分用例失败是预期结果，不是单元测试失败。演示比例不能代表任何大模型的真实能力。

## 在线模式

PowerShell 配置示例：

```powershell
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_MODEL="服务商当前可用的模型名"
$env:LLM_API_KEY="你的密钥"
python -m model_probe online --workers 1 --retries 1 --output reports/online.json
```

只有显式使用 `online` 才会访问外部模型接口。一次运行每个用例可能最多请求 `1 + retries` 次，在线模式可能产生费用。故障注入标记只发送给本机 mock，真实在线模式只发送常规模型请求。真实在线回归结果需要自己执行，本次没有付费模型实测。

## 已实现

- Chat Completions 请求、JSON 输出格式与模型名配置。
- 只允许 HTTPS，测试模式显式允许本机 HTTP；拒绝带凭据的 URL 与自动重定向。
- 并发数限制为 1 到 8；重试次数为 0 到 3，429 和部分 5xx / 网络错误按指数等待重试。
- JSON 对象、必需字段和基础类型检查，以及关键词检查。
- 区分 API 请求成功与输出格式检查通过，保留失败原因、请求次数、完整响应耗时、P50/P95 与接口返回的 Token 用量。
- JSON 和静态 HTML 报告，模型输出进行 HTML 转义，不记录请求密钥和供应商错误正文。
- 本机模拟服务和自动化回归测试，支持不依赖外部 API 的复现。

## 结构

```text
model_probe/client.py       请求协议、超时和重试
model_probe/evaluation.py   用例校验、有界并发和指标汇总
model_probe/mock_server.py  本机故障注入与预设响应
model_probe/report.py       JSON 与 HTML 报告
datasets/cases.json         12 个演示回归用例
tests/test_probe.py         自动化测试
```

## 指标的解释范围

字段类型正确不代表回答语义正确。P50/P95 是成功 API 调用的完整请求耗时，包含重试等待，不是 TTFT，也不是受控生产压测。缺少 Token 用量时明确记录缺失，不根据字符串长度猜测费用。当前没有语义评分、在线监控、流式输出或跨模型排名。

## 修改用例

`--cases path/to/cases.json` 可指定自己的题集，最多 100 条；每条包含唯一 id、prompt 和 check。支持 `json` 与 `contains` 两种检查，具体字段见样例。当前只做字段和基础类型校验，不是完整 JSON Schema 验证器。

协议参考：[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) 与 [错误码](https://api-docs.deepseek.com/quick_start/error_codes/)。

本项目为 AI 辅助编程学习作品，代码和报告保留验证范围。请亲自复现、修改并记录自己的实现。许可证见 `LICENSE`。
