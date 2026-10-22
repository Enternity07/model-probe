"""Small, bounded Chat Completions transport. Never log credentials or error bodies."""
import json
import math
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_RESPONSE = 512 * 1024
RETRY_STATUSES = {429, 500, 502, 503, 504}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ModelClient:
    def __init__(self, base_url, model, api_key, *, timeout=20, retries=1,
                 backoff=.2, allow_local_mock=False):
        url = urlsplit(base_url)
        local = (url.scheme == "http" and url.hostname in {"127.0.0.1", "::1"}
                 and allow_local_mock)
        if (url.scheme != "https" and not local) or not url.hostname:
            raise ValueError("API 地址必须是 HTTPS；本机 HTTP 仅供显式 mock 测试")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("API 地址不能包含凭据、查询或片段")
        if not model or not api_key:
            raise ValueError("model 和 API key 不能为空")
        if not .01 <= timeout <= 120 or not math.isfinite(timeout):
            raise ValueError("timeout 需为 0.01 到 120 秒")
        if type(retries) is not int or not 0 <= retries <= 3:
            raise ValueError("retries 需为 0 到 3 的整数")
        if not 0 <= backoff <= 2 or not math.isfinite(backoff):
            raise ValueError("backoff 需为 0 到 2 秒")
        self.base, self.model, self.key = base_url.rstrip("/"), model, api_key
        self.timeout, self.retries, self.backoff = timeout, retries, backoff
        self.local = local

    def complete(self, prompt, *, json_mode=True, mock_behavior="normal"):
        if not isinstance(prompt, str) or not 1 <= len(prompt) <= 8000:
            raise ValueError("prompt 需为 1 到 8000 字符")
        started = time.perf_counter()
        payload = {"model": self.model, "messages": [
            {"role": "system", "content": "按用户要求回答。要求 JSON 时只输出 JSON 对象。"},
            {"role": "user", "content": prompt}], "max_tokens": 300, "temperature": 0}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if urlsplit(self.base).hostname == "api.deepseek.com":
            payload["thinking"] = {"type": "disabled"}
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + self.key}
        if self.local:
            headers.update({"X-Mock-Behavior": mock_behavior, "X-Request-Id": uuid.uuid4().hex})
        status, error_code, content, usage = None, None, "", None
        for attempt in range(1, self.retries + 2):
            transient = False
            opener = build_opener(ProxyHandler({}), NoRedirect()) if self.local else build_opener(NoRedirect())
            request = Request(self.base + "/chat/completions",
                              data=json.dumps(payload).encode(), headers=headers)
            try:
                with opener.open(request, timeout=self.timeout) as response:
                    status = response.status
                    raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise ValueError("response_too_large")
                body = json.loads(raw)
                message = body["choices"][0]["message"]
                if message.get("role") != "assistant" or not isinstance(message.get("content"), str):
                    raise ValueError("invalid_message")
                if body["choices"][0].get("finish_reason") == "length":
                    raise ValueError("truncated_response")
                content = message["content"]
                if not content.strip():
                    raise ValueError("empty_response")
                candidate = body.get("usage")
                if isinstance(candidate, dict) and type(candidate.get("total_tokens")) is int and candidate["total_tokens"] >= 0:
                    usage = {"total_tokens": candidate["total_tokens"]}
                error_code = None
                break
            except HTTPError as error:
                status = error.code
                error_code = "http_" + str(status)
                transient = status in RETRY_STATUSES
                error.close()
            except (TimeoutError, URLError):
                status, error_code, transient = None, "network_or_timeout", True
            except (ValueError, KeyError, IndexError, TypeError, AttributeError, UnicodeDecodeError):
                error_code = "invalid_response"
            if not transient or attempt > self.retries:
                break
            time.sleep(self.backoff * 2 ** (attempt - 1))
        return {"api_ok": error_code is None, "status": status, "error_code": error_code,
                "attempts": attempt, "response_text": content if error_code is None else "",
                "usage": usage if error_code is None else None,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3)}
