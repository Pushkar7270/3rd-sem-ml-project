#!/usr/bin/env python3
"""Download the IBM Telco Customer Churn dataset.

Usage:
    python scripts/download_data.py            # skip if present
    python scripts/download_data.py --force    # re-download
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = PROJECT_ROOT / "data" / "raw" / "Telco-Customer-Churn.csv"
URLS = [
    "https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv",
    "https://raw.githubusercontent.com/IBM/telco-customer-churn/main/data/Telco-Customer-Churn.csv",
]
EXPECTED_ROWS = 7043
EXPECTED_COLUMNS = {
    "customerID",
    "gender",
    "SeniorCitizen",
    "Partner",
    "Dependents",
    "tenure",
    "PhoneService",
    "MultipleLines",
    "InternetService",
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
    "Contract",
    "PaperlessBilling",
    "PaymentMethod",
    "MonthlyCharges",
    "TotalCharges",
    "Churn",
}


def validate(path: Path) -> None:
    frame = pd.read_csv(path)
    missing = EXPECTED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Downloaded file is missing columns: {sorted(missing)}")
    if len(frame) != EXPECTED_ROWS:
        raise ValueError(f"Expected {EXPECTED_ROWS} rows, got {len(frame)}")
    churn_rate = frame["Churn"].str.lower().eq("yes").mean()
    print(
        f"Validated {len(frame):,} rows, {len(frame.columns)} columns, churn rate {churn_rate:.1%}"
    )


def download(target: Path, force: bool = False) -> Path:
    if target.exists() and not force:
        print(f"Dataset already exists at {target} (use --force to re-download)")
        validate(target)
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for url in URLS:
        print(f"Downloading {url} ...")
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
            target.write_bytes(data)
            validate(target)
            print(f"Saved to {target}")
            return target
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            last_error = exc
            print(f"  failed: {exc}")
            target.unlink(missing_ok=True)
    raise SystemExit(f"Could not download the dataset: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    download(args.output, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
