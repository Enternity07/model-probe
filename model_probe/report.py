import html
import json
from pathlib import Path


def write_report(report, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for case in report["cases"]:
        values = [case["id"], "通过" if case["check_passed"] else "失败", case["check_reason"],
                  case["attempts"], case["latency_ms"], case["response_text"][:400]]
        rows.append("<tr>" + "".join("<td>" + html.escape(str(value)) + "</td>" for value in values) + "</tr>")
    content = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ModelProbe 接口回归报告</title>
<style>body{{font:15px/1.7 system-ui,sans-serif;color:#172b36;background:#f4f6f8;margin:0}}main{{max-width:1150px;margin:40px auto;padding:30px;background:white;border-radius:14px}}h1{{font-size:27px}}.stats{{display:flex;gap:26px;flex-wrap:wrap;padding:20px;background:#edf3f6}}table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:24px}}th,td{{border:1px solid #d7e0e6;padding:10px;text-align:left;overflow-wrap:anywhere}}th{{background:#e8eef2}}td:last-child{{max-width:340px}}.note{{color:#536672}}</style><main>
<h1>ModelProbe 接口回归报告</h1><p>运行模式：<strong>{html.escape(report['mode'])}</strong> · 模型：{html.escape(report['model'])}</p>
<div class="stats"><span>用例 {report['case_count']}</span><span>API 成功率 {report['api_success_rate']:.0%}</span><span>格式检查通过率 {report['contract_pass_rate']:.0%}</span><span>P50 {report['latency_p50_ms']} ms</span><span>P95 {report['latency_p95_ms']} ms</span></div>
<p class="note">{html.escape(report['notice'])}</p><p class="note">{html.escape(report['latency_scope'])}</p>
<table><thead><tr><th>用例</th><th>检查结果</th><th>原因</th><th>请求次数</th><th>耗时 ms</th><th>响应内容</th></tr></thead><tbody>{''.join(rows)}</tbody></table></main></html>'''
    output.with_suffix(".html").write_text(content, encoding="utf-8")
