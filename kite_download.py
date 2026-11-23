"""Download only historical index candles. Credentials stay in local memory."""
import argparse
import hashlib
import json
import os
import time
from datetime import date, datetime, time as clock, timedelta
from getpass import getpass
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pandas as pd

from strategies import TZ, prepare, timestamps

EXCHANGES = {"NIFTY 50": "NSE", "SENSEX": "BSE"}


def download(kite, symbol, start, end):
    exchange = EXCHANGES[symbol]
    matches = [row for row in kite.instruments(exchange)
               if row["tradingsymbol"] == symbol and row.get("segment") in {"INDICES", f"{exchange}-INDICES"}]
    if len(matches) != 1:
        # These identifiers are stable index tokens, unlike derivative tokens.
        known = {"NIFTY 50": 256265, "SENSEX": 265}
        token = known[symbol]
    else:
        token = matches[0]["instrument_token"]
    current, rows, empty_windows = start, [], []
    while current <= end:
        last = min(current + timedelta(days=29), end)
        # The SDK serializes wall times without UTC offsets. The API expects IST.
        candles = kite.historical_data(token, datetime.combine(current, clock(9, 15)),
                                      datetime.combine(last, clock(15, 29)), interval="minute")
        if not candles:
            empty_windows.append([str(current), str(last)])
        rows.extend(candles)
        current = last + timedelta(days=1)
        if current <= end:
            time.sleep(.5)
    if not rows:
        raise ValueError("No historical candles")
    result = pd.DataFrame(rows)
    result["date"] = timestamps(result.date)
    result = result.sort_values("date")
    if not result.date.dt.date.between(start, end).all():
        raise ValueError("Provider returned candles outside the requested date range")
    coverage = prepare(result).attrs["coverage"]
    return result, {"source": "https://kite.trade/docs/connect/v3/historical/", "symbol": symbol,
                    "exchange": exchange, "instrument_token": token, "timezone": TZ,
                    "start": str(start), "end": str(end), "rows": len(result),
                    "empty_windows": empty_windows, "coverage": coverage}


def local_login(kite):
    secret = os.environ.get("KITE_API_SECRET") or getpass("Kite API secret: ")
    print("Open the Kite login URL locally:", kite.login_url())
    callback = getpass("Paste the local callback URL or request token here: ").strip()
    token = parse_qs(urlsplit(callback).query).get("request_token", [None])[0] if "://" in callback else callback
    if not token or not secret:
        raise ValueError("Missing login response or API secret")
    return kite.generate_session(token, api_secret=secret)["access_token"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, choices=EXCHANGES)
    parser.add_argument("--from-date", type=date.fromisoformat, required=True)
    parser.add_argument("--to-date", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--login", action="store_true", help="Exchange a request token locally without printing the access token")
    args = parser.parse_args()
    if args.from_date > args.to_date or args.to_date >= datetime.now(ZoneInfo(TZ)).date():
        parser.error("Use an ordered interval ending before today's IST date")
    key = os.environ.get("KITE_API_KEY")
    token = os.environ.get("KITE_ACCESS_TOKEN")
    if not key or not (token or args.login):
        parser.error("Set KITE_API_KEY and KITE_ACCESS_TOKEN locally, or use --login")
    from kiteconnect import KiteConnect
    try:
        kite = KiteConnect(api_key=key)
        kite.set_access_token(local_login(kite) if args.login else token)
        data, manifest = download(kite, args.symbol, args.from_date, args.to_date)
    except Exception as exc:
        # Provider errors can contain request information. Do not echo them.
        raise SystemExit(f"Kite download failed ({type(exc).__name__}). Check Connect access, credentials and dates.") from None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", dir=args.output.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            data.to_csv(file, index=False)
            file.flush()
            manifest["sha256"] = hashlib.sha256(temporary.read_bytes()).hexdigest()
            temporary.replace(args.output)
        finally:
            temporary.unlink(missing_ok=True)
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Saved {len(data)} candles in {args.output}")


if __name__ == "__main__":
    main()
