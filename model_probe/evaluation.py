import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

TYPE_CHECKS = {"string": lambda x: isinstance(x, str),
               "number": lambda x: type(x) is int or (type(x) is float and math.isfinite(x)),
               "boolean": lambda x: type(x) is bool,
               "array": lambda x: isinstance(x, list),
               "object": lambda x: isinstance(x, dict)}


def validate_content(content, specification):
    if specification["kind"] == "contains":
        passed = all(word.lower() in content.lower() for word in specification["words"])
        return passed, "ok" if passed else "missing_keyword"
    try:
        value = json.loads(content)
    except (ValueError, TypeError):
        return False, "not_json"
    if not isinstance(value, dict):
        return False, "not_json_object"
    for key, expected in specification["fields"].items():
        if key not in value:
            return False, "missing_field:" + key
        if not TYPE_CHECKS[expected](value[key]):
            return False, "wrong_type:" + key
    return True, "ok"


def validate_cases(cases):
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        raise ValueError("题集需包含 1 到 100 条记录")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"] or case["id"] in seen:
            raise ValueError("用例 id 必须是唯一的非空字符串")
        seen.add(case["id"])
        if not isinstance(case.get("prompt"), str) or not 1 <= len(case["prompt"]) <= 8000:
            raise ValueError("每个用例需有有效 prompt")
        spec = case.get("check", {})
        if not isinstance(spec, dict):
            raise ValueError("check 必须是对象")
        if spec.get("kind") == "json":
            fields = spec.get("fields")
            if not isinstance(fields, dict) or not fields or any(not isinstance(t, str) or t not in TYPE_CHECKS for t in fields.values()):
                raise ValueError("JSON 检查需定义字段与有效类型")
        elif spec.get("kind") == "contains":
            words = spec.get("words")
            if not isinstance(words, list) or not words or not all(isinstance(w, str) and w for w in words):
                raise ValueError("contains 检查需提供非空关键词列表")
        else:
            raise ValueError("仅支持 json 或 contains 检查")
    return cases


def percentile(values, ratio):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * ratio) - 1)]


def run_suite(client, cases, *, workers=2, mode="mock"):
    validate_cases(cases)
    if type(workers) is not int or not 1 <= workers <= 8:
        raise ValueError("workers 需为 1 到 8")
    started = time.perf_counter()

    def run_case(case):
        result = client.complete(case["prompt"], json_mode=case["check"]["kind"] == "json",
                                 mock_behavior=case.get("mock_behavior", "normal"))
        passed, reason = validate_content(result["response_text"], case["check"]) if result["api_ok"] else (False, result["error_code"])
        return {"id": case["id"], "prompt": case["prompt"], "check": case["check"],
                **result, "check_passed": passed, "check_reason": reason}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(run_case, cases))
    latencies = [row["latency_ms"] for row in rows if row["api_ok"]]
    usage_rows = [row for row in rows if row["usage"] is not None]
    return {"mode": mode, "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": client.model, "workers": workers, "case_count": len(rows),
            "api_success_rate": sum(row["api_ok"] for row in rows) / len(rows),
            "contract_pass_rate": sum(row["check_passed"] for row in rows) / len(rows),
            "latency_p50_ms": percentile(latencies, .50), "latency_p95_ms": percentile(latencies, .95),
            "latency_scope": "成功 API 调用的完整请求耗时，包含重试等待，不是首 Token 延迟",
            "request_attempts": sum(row["attempts"] for row in rows),
            "known_total_tokens": sum(row["usage"]["total_tokens"] for row in usage_rows),
            "cases_without_usage": len(rows) - len(usage_rows),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "notice": "mock 使用程序预设响应验证接入与故障处理；格式和关键词检查不等于语义正确性或模型通用能力。",
            "cases": rows}
