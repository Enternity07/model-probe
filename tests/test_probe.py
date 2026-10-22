import json
import tempfile
import unittest
from pathlib import Path

from model_probe.client import ModelClient
from model_probe.evaluation import percentile, run_suite, validate_cases, validate_content
from model_probe.mock_server import mock_server
from model_probe.report import write_report

ROOT = Path(__file__).resolve().parents[1]


class ValidationTests(unittest.TestCase):
    def test_valid_json_fields(self):
        spec = {"kind": "json", "fields": {"name": "string", "skills": "array"}}
        self.assertEqual(validate_content('{"name":"a","skills":[]}', spec), (True, "ok"))

    def test_invalid_json_and_types(self):
        spec = {"kind": "json", "fields": {"value": "number"}}
        for content in ['not json', '[1,2]', '{}', '{"value":true}', '{"value":"4"}', '{"value":1e999}']:
            with self.subTest(content=content):
                self.assertFalse(validate_content(content, spec)[0])

    def test_keyword_check(self):
        self.assertTrue(validate_content("Python API", {"kind":"contains", "words":["python"]})[0])
        self.assertFalse(validate_content("hello", {"kind":"contains", "words":["python"]})[0])

    def test_reject_invalid_cases(self):
        valid = {"id":"a", "prompt":"hello", "check":{"kind":"json", "fields":{"name":"string"}}}
        for cases in [[], [valid, valid], [{**valid,"check":None}], [{**valid,"prompt":""}],
                      [{**valid,"check":{"kind":"json","fields":{"x":[]}}}]]:
            with self.subTest(cases=cases), self.assertRaises(ValueError):
                validate_cases(cases)

    def test_percentiles_and_empty(self):
        self.assertEqual(percentile([3,1,2], .5), 2)
        self.assertEqual(percentile([3,1,2], .95), 3)
        self.assertIsNone(percentile([], .5))


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = mock_server()
        cls.base = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def client(self, **kwargs):
        return ModelClient(self.base, "fixture", "secret-value-not-for-report", allow_local_mock=True,
                           backoff=0, **kwargs)

    def test_url_constraints(self):
        for base in ["http://example.com", "https://user:pass@example.com", "https://example.com?key=x", "ftp://example.com"]:
            with self.subTest(base=base), self.assertRaises(ValueError):
                ModelClient(base, "model", "key")

    def test_bounds(self):
        for values in [{"retries":4}, {"timeout":0}, {"timeout":float("inf")}, {"retries":True}]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.client(**values)

    def test_missing_credentials(self):
        with self.assertRaises(ValueError):
            ModelClient("https://example.com", "model", "")

    def test_prompt_bounds(self):
        for prompt in ["", "x"*8001, 1]:
            with self.assertRaises(ValueError):
                self.client().complete(prompt)

    def test_normal_response(self):
        result = self.client().complete("Return JSON")
        self.assertTrue(result["api_ok"])
        self.assertEqual(result["usage"]["total_tokens"], 32)

    def test_auth_failure_is_not_retried(self):
        result = self.client(retries=3).complete("Return JSON", mock_behavior="auth_failure")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["error_code"], "http_401")
        self.assertNotIn("secret", json.dumps(result))

    def test_retry_429(self):
        result = self.client(retries=1).complete("Return JSON", mock_behavior="rate_limit_once")
        self.assertTrue(result["api_ok"])
        self.assertEqual(result["attempts"], 2)

    def test_retry_503(self):
        result = self.client(retries=1).complete("Return JSON", mock_behavior="retry_once")
        self.assertTrue(result["api_ok"])
        self.assertEqual(result["attempts"], 2)

    def test_retry_limit(self):
        result = self.client(retries=2).complete("Return JSON", mock_behavior="always_busy")
        self.assertEqual(result["attempts"], 3)
        self.assertFalse(result["api_ok"])

    def test_malformed_response(self):
        result = self.client().complete("Return JSON", mock_behavior="malformed_protocol")
        self.assertEqual(result["error_code"], "invalid_response")

    def test_timeout(self):
        result = self.client(timeout=.02, retries=0).complete("Return JSON", mock_behavior="slow")
        self.assertFalse(result["api_ok"])
        self.assertEqual(result["error_code"], "network_or_timeout")

    def test_usage_missing_is_explicit(self):
        result = self.client().complete("Return JSON", mock_behavior="no_usage")
        self.assertTrue(result["api_ok"])
        self.assertIsNone(result["usage"])

    def test_concurrent_results_and_metrics(self):
        cases = json.loads((ROOT/"datasets/cases.json").read_text(encoding="utf-8"))
        report = run_suite(self.client(retries=1), cases, workers=3)
        self.assertEqual([case["id"] for case in report["cases"]], [case["id"] for case in cases])
        self.assertEqual(report["case_count"], 12)
        self.assertEqual(report["request_attempts"], 14)
        self.assertEqual(report["api_success_rate"], 9/12)
        self.assertEqual(report["contract_pass_rate"], 7/12)
        self.assertEqual(report["known_total_tokens"], 9*32)

    def test_workers_limit(self):
        cases = json.loads((ROOT/"datasets/cases.json").read_text(encoding="utf-8"))
        for workers in [0,9,True]:
            with self.assertRaises(ValueError):
                run_suite(self.client(), cases, workers=workers)

    def test_report_escapes_response_html(self):
        cases = [{"id":"html", "prompt":"JSON", "mock_behavior":"html",
                  "check":{"kind":"json", "fields":{"name":"string"}}}]
        report = run_suite(self.client(), cases)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"report.json"
            write_report(report, path)
            text = path.with_suffix(".html").read_text(encoding="utf-8")
            self.assertNotIn("<script>", text)
            self.assertIn("&lt;script&gt;", text)
            self.assertNotIn("secret-value-not-for-report", path.read_text(encoding="utf-8"))
