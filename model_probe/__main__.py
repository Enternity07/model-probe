import argparse
import json
import os
from pathlib import Path

from .client import ModelClient
from .evaluation import run_suite
from .mock_server import mock_server
from .report import write_report

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="ModelProbe 模型 API 格式检查与回归评测")
    parser.add_argument("mode", choices=["demo", "online"])
    parser.add_argument("--cases", type=Path, default=ROOT / "datasets" / "cases.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "latest.json")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()
    try:
        cases = json.loads(args.cases.read_text(encoding="utf-8"))
        if args.mode == "demo":
            with mock_server() as base:
                client = ModelClient(base, "local-fixture", "mock-placeholder", allow_local_mock=True,
                                     retries=args.retries, backoff=.01)
                report = run_suite(client, cases, workers=args.workers, mode="mock")
        else:
            client = ModelClient(os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
                                 os.environ.get("LLM_MODEL", ""), os.environ.get("LLM_API_KEY", ""),
                                 retries=args.retries)
            report = run_suite(client, cases, workers=args.workers, mode="online")
        write_report(report, args.output)
        print(json.dumps({key: value for key, value in report.items() if key != "cases"}, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, f"错误：{error}\n")


if __name__ == "__main__":
    main()
