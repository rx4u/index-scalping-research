"""Download the free, pinned inputs and rebuild the research dashboard."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"


def read_json(path):
    return json.loads(path.read_text())


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def fetch(url, path, checksum):
    if path.is_file() and digest(path) == checksum:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
    try:
        with urlopen(url, timeout=60) as source, temporary.open("wb") as target:
            shutil.copyfileobj(source, target)
        if digest(temporary) != checksum:
            raise ValueError(f"Checksum mismatch for {url}")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def run(cache, out):
    manifest = read_json(EVIDENCE / "manifest.json")
    config = manifest["configuration"]
    tasks = []
    for instrument, spec in config["instruments"].items():
        repository = spec["source"].removeprefix("https://github.com/")
        base = f"https://raw.githubusercontent.com/{repository}/{spec['revision']}"
        # Include only files intersecting the fixed study window.
        directory = cache / spec["revision"]
        spec["csv"] = []
        for name, checksum in manifest["inputs"][instrument]["sha256"].items():
            period = name.removesuffix(".csv").rsplit("_", 1)[-1]
            if period < config["start"][:len(period)] or period > config["end"][:len(period)]:
                continue
            path = directory / name
            spec["csv"].append(str(path))
            tasks.append((f"{base}/1min/{period[:4]}/{name}", path, checksum))
    options = read_json(EVIDENCE / "option_proxy_manifest.json")
    check = read_json(EVIDENCE / "source_crosscheck.json")
    base = options["source"].replace("/tree/", "/resolve/")
    for name, checksum in options["sha256"].items():
        symbol, expiry = name.split("_", 1)
        tasks.append((f"{base}/options/{symbol}/{expiry}", cache / name, checksum))
    for instrument, result in check["instruments"].items():
        name = f"{instrument.split()[0]}.parquet"
        tasks.append((f"{base}/index/{name}", cache / name, result["secondary_sha256"]))

    print(f"Fetching or verifying {len(tasks)} public data files", flush=True)
    with ThreadPoolExecutor(max_workers=6) as workers:
        list(workers.map(lambda task: fetch(*task), tasks))

    out.mkdir(parents=True, exist_ok=True)
    config_path = out / "public_config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    commands = [
        ("research.py", "--config", config_path, "--out", out),
        ("option_proxy.py", "--reports", out, "--inputs", cache),
        ("source_crosscheck.py", "--config", config_path, "--inputs", cache,
         "--out", out / "source_crosscheck.json"),
        ("dashboard.py", "--reports", out, "--out", out / "dashboard.html"),
    ]
    for script, *args in commands:
        print(f"Running {script}", flush=True)
        subprocess.run([sys.executable, str(ROOT / script), *map(str, args)], check=True)
    print(f"Dashboard saved to {out / 'dashboard.html'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "data" / "public")
    parser.add_argument("--out", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    run(args.cache.resolve(), args.out.resolve())
