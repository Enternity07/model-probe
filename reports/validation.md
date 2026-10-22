# 本地验证记录

验证日期：2026-10-22。环境：Windows、Python 3.12.14。

- `python -m unittest discover -s tests -v`：20 项测试全部通过。
- `python -m model_probe demo --workers 3 --output reports/demo.json`：完成 12 个预设回归用例、14 次本机 HTTP 请求，输出 JSON 和 HTML。
- 预设结果包含 9 个 API 成功响应、7 个格式检查通过结果；其他失败是为了验证鉴权错误、损坏协议、空响应、错误 JSON 和缺少字段的处理。
- 429、503 单次故障恢复、有限重试、请求超时、有界并发、用量缺失与 HTML 转义均经过自动化测试。
- 报告没有请求密钥或供应商错误正文。
- 未调用真实在线大模型，未进行语义质量评估、生产压测、公网部署或远程 GitHub Actions 验证。演示延迟和 Token 数来自模拟服务，不能用来比较真实模型。
