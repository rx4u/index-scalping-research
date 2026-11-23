"""Build a self-contained research dashboard from local report CSVs."""
import argparse
import json
from pathlib import Path

import pandas as pd


def build(report, out):
    report = Path(report)

    def records(name):
        path = report / name
        return json.loads(pd.read_csv(path).to_json(orient="records")) if path.exists() else []

    payload = {"metrics": records("index_metrics.csv"), "trades": records("index_trades.csv"),
               "options": records("option_proxy_metrics.csv"), "optionTrades": records("option_proxy_trades.csv"),
               "manifest": json.loads((report / "manifest.json").read_text())}
    for name in ("option_proxy_manifest", "source_crosscheck"):
        path = report / f"{name}.json"
        if path.exists():
            payload["manifest"][name] = json.loads(path.read_text())
    data = json.dumps(payload, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("dashboard.html").read_text()
    Path(out).write_text(template.replace("/*REPORT_DATA*/null", data, 1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", default="reports")
    parser.add_argument("--out", default="reports/dashboard.html")
    args = parser.parse_args()
    build(args.reports, args.out)
