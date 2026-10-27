"""scripts/strategy_c/download_spy_databento.py — STRATEGY_ID = C,
Experiment C2 confirmation-data acquisition: SPY trades + mbp-1
(continuous top-of-book NBBO) from Databento's EQUS.MINI dataset, same
schemas/window as the QQQ discovery sample (2026-02-24 to 2026-05-24),
per docs/strategy_c/STRATEGY_C_RESEARCH_LOG.md's C2 pre-registration.
Cost confirmed via metadata.get_cost BEFORE this job was submitted:
trades $0.52 + mbp-1 $19.90 = $20.42, within the remaining Databento
free credit (no new purchase/subscription). Mirrors
download_qqq_databento.py exactly (same per-day batch download +
per-day streaming Parquet conversion, memory-constrained machine).

Usage:
    python scripts/strategy_c/download_spy_databento.py --submit
    python scripts/strategy_c/download_spy_databento.py --status
    python scripts/strategy_c/download_spy_databento.py --download-and-convert
"""
import argparse
import gc
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dotenv import load_dotenv

load_dotenv()

import databento as db

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATASET = "EQUS.MINI"
SYMBOLS = ["SPY"]
SCHEMAS = ["trades", "mbp-1"]
START = "2026-02-24"
END = "2026-05-24"

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "strategy_c", "raw")
NORMALIZED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "strategy_c", "normalized")
JOB_IDS_PATH = os.path.join(RAW_DIR, "batch_job_ids_spy.txt")


def get_client():
    return db.Historical(os.environ["DATABENTO_API_KEY"])


def submit():
    client = get_client()
    os.makedirs(RAW_DIR, exist_ok=True)
    job_ids = []
    for schema in SCHEMAS:
        job = client.batch.submit_job(
            dataset=DATASET, symbols=SYMBOLS, schema=schema,
            start=START, end=END, encoding="dbn", compression="zstd",
        )
        job_id = job["id"]
        job_ids.append((schema, job_id))
        print(f"Submitted job for schema={schema}: job_id={job_id}  state={job.get('state')}")
    with open(JOB_IDS_PATH, "w") as f:
        for schema, job_id in job_ids:
            f.write(f"{schema},{job_id}\n")
    print(f"\nJob IDs saved -> {JOB_IDS_PATH}")


def status():
    client = get_client()
    if not os.path.exists(JOB_IDS_PATH):
        print("No submitted jobs found -- run --submit first.")
        return False
    with open(JOB_IDS_PATH) as f:
        job_ids = [line.strip().split(",") for line in f if line.strip()]
    all_jobs = {j["id"]: j for j in client.batch.list_jobs()}
    all_done = True
    for schema, job_id in job_ids:
        job = all_jobs.get(job_id)
        if job is None:
            print(f"  {schema} ({job_id}): NOT FOUND in job list")
            all_done = False
            continue
        state = job.get("state")
        print(f"  {schema} ({job_id}): state={state}")
        if state != "done":
            all_done = False
    print("\nALL DONE -- ready to download" if all_done else "\nStill processing, check again later.")
    return all_done


def daily_dir_for(schema: str) -> str:
    return os.path.join(NORMALIZED_DIR, f"SPY_{schema}_daily")


def download_and_convert(limit: int = None):
    client = get_client()
    if not os.path.exists(JOB_IDS_PATH):
        print("No submitted jobs found -- run --submit first.")
        return
    with open(JOB_IDS_PATH) as f:
        job_ids = [line.strip().split(",") for line in f if line.strip()]

    converted_count = 0
    for schema, job_id in job_ids:
        if limit is not None and converted_count >= limit:
            break
        job_dir = os.path.join(RAW_DIR, job_id)
        out_dir = daily_dir_for(schema)
        os.makedirs(out_dir, exist_ok=True)

        already_have_raw = os.path.isdir(job_dir) and any(
            f.endswith(".dbn.zst") or f.endswith(".dbn") for f in os.listdir(job_dir))
        if not already_have_raw:
            print(f"\nDownloading files for schema={schema}, job_id={job_id}...")
            downloaded = client.batch.download(output_dir=RAW_DIR, job_id=job_id)
            print(f"  Downloaded {len(downloaded)} file(s)")

        if not os.path.isdir(job_dir):
            print(f"  WARNING: expected per-job directory not found: {job_dir}")
            continue
        dbn_files = sorted(f for f in os.listdir(job_dir) if f.endswith(".dbn.zst") or f.endswith(".dbn"))
        if not dbn_files:
            print(f"  WARNING: no .dbn(.zst) file found for job {job_id} in {job_dir}")
            continue

        for fname in dbn_files:
            if limit is not None and converted_count >= limit:
                break
            date_match = re.search(r"(\d{8})", fname)
            if not date_match:
                print(f"  WARNING: could not parse date from {fname}, skipping")
                continue
            date_str = date_match.group(1)
            out_path = os.path.join(out_dir, f"{date_str}.parquet")
            if os.path.exists(out_path):
                continue
            fpath = os.path.join(job_dir, fname)
            store = db.DBNStore.from_file(fpath)
            df = store.to_df()
            df.to_parquet(out_path)
            print(f"  {fname} -> {out_path}  ({len(df):,} rows)")
            del store, df
            gc.collect()
            converted_count += 1

    print(f"\nConverted {converted_count} new daily file(s) this run.")
    remaining = 0
    for schema, job_id in job_ids:
        job_dir = os.path.join(RAW_DIR, job_id)
        out_dir = daily_dir_for(schema)
        if os.path.isdir(job_dir):
            n_raw = sum(1 for f in os.listdir(job_dir) if f.endswith(".dbn.zst") or f.endswith(".dbn"))
            n_done = sum(1 for f in os.listdir(out_dir)) if os.path.isdir(out_dir) else 0
            print(f"  {schema}: {n_done}/{n_raw} days converted")
            remaining += max(0, n_raw - n_done)
    print("ALL SCHEMAS FULLY CONVERTED" if remaining == 0 else f"{remaining} day(s) remaining -- rerun to continue")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--download-and-convert", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if args.submit:
        submit()
    elif args.status:
        status()
    elif args.download_and_convert:
        download_and_convert(limit=args.limit)
    else:
        print("Specify --submit, --status, or --download-and-convert")


if __name__ == "__main__":
    main()
