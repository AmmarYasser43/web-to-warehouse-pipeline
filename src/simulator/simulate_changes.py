"""
Simulates a "next run" of the scraper, because books.toscrape.com never changes.

Reads a raw run (books_raw_<date>.json) and writes a NEW raw run with a later date:
  - price changes
  - removed books
  - new books
  - category changes
  - a few books going out of stock
It also writes sim_changes_<date>.json listing exactly what was changed, so the
SQL results (price changes / new / removed / category changes) can be verified.

Usage:
    python simulate_changes.py                       # latest raw JSON, +1 day
    python simulate_changes.py data/raw/books_raw_2026-10-24.json --days 7
    python simulate_changes.py --seed 7 --removed 30 --new 30
"""
import argparse
import glob
import json
import os
import random
import re
import sys
from datetime import date, timedelta

import pandas as pd

BASE_URL = "https://books.toscrape.com/"
RATING_WORDS = ["One", "Two", "Three", "Four", "Five"]


def parse_price(text):
    return float(re.sub(r"[^\d.]", "", str(text)))


def fmt_price(value):
    return f"£{value:.2f}"


def simulate(books, new_date, rng, n_removed, n_new, price_pct, n_category, n_stock):
    books = [dict(b) for b in books]
    existing_urls = {b["URL"] for b in books}
    categories = sorted({b["Category"] for b in books})
    log = {"price_changed": [], "removed": [], "new": [],
           "category_changed": [], "availability_changed": []}

    # --- removed books ---
    n_removed = min(n_removed, len(books))
    removed_idx = set(rng.sample(range(len(books)), n_removed))
    for i in sorted(removed_idx):
        log["removed"].append({"URL": books[i]["URL"], "Title": books[i]["Title"]})
    remaining = [i for i in range(len(books)) if i not in removed_idx]

    # --- price changes (-20% .. +20%) ---
    n_price = min(round(len(remaining) * price_pct), len(remaining))
    for i in rng.sample(remaining, n_price):
        old = parse_price(books[i]["Price"])
        new = round(old * rng.uniform(0.8, 1.2), 2)
        if new == old:
            new = round(old + 0.5, 2)
        books[i]["Price"] = fmt_price(new)
        log["price_changed"].append({"URL": books[i]["URL"], "Title": books[i]["Title"],
                                     "old_price": old, "new_price": new})

    # --- category changes ---
    for i in rng.sample(remaining, min(n_category, len(remaining))):
        old = books[i]["Category"]
        new = rng.choice([c for c in categories if c != old])
        books[i]["Category"] = new
        log["category_changed"].append({"URL": books[i]["URL"], "Title": books[i]["Title"],
                                        "old_category": old, "new_category": new})

    # --- some books go out of stock ---
    for i in rng.sample(remaining, min(n_stock, len(remaining))):
        if "In stock" in str(books[i]["Availability"]):
            books[i]["Availability"] = "Out of stock"
            log["availability_changed"].append({"URL": books[i]["URL"], "Title": books[i]["Title"]})

    # --- drop removed books ---
    books = [b for i, b in enumerate(books) if i not in removed_idx]

    # --- new books (fake URLs, never reuse a URL that existed before) ---
    k = 1
    for _ in range(n_new):
        while f"{BASE_URL}catalogue/simulated-book-{k}_{900 + k}/index.html" in existing_urls:
            k += 1
        url = f"{BASE_URL}catalogue/simulated-book-{k}_{900 + k}/index.html"
        existing_urls.add(url)
        book = {
            "Title": f"Simulated Book {k}",
            "Category": rng.choice(categories),
            "Price": fmt_price(round(rng.uniform(10, 60), 2)),
            "Rating": rng.choice(RATING_WORDS),
            "Availability": "In stock",
            "URL": url,
        }
        books.append(book)
        log["new"].append({"URL": url, "Title": book["Title"], "Category": book["Category"]})

    # --- every row of the new run gets the new run's timestamp ---
    scraped_at = f"{new_date.isoformat()}T10:00:00+00:00"
    for b in books:
        b["Scraped_at"] = scraped_at

    return books, log


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", nargs="?", default=None)
    parser.add_argument("--days", type=int, default=1, help="days after the input run")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--removed", type=int, default=20)
    parser.add_argument("--new", type=int, default=20)
    parser.add_argument("--category", type=int, default=15)
    parser.add_argument("--stock", type=int, default=10)
    parser.add_argument("--price-pct", type=float, default=0.10)
    args = parser.parse_args()

    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    RAW_DIR = os.path.join(BASE_DIR, "data", "raw")

    input_file = args.input_file
    if input_file is None:
        files = sorted(glob.glob(os.path.join(RAW_DIR, "books_raw_*.json")))
        if not files:
            sys.exit(f"No books_raw_*.json found in {RAW_DIR}")
        input_file = files[-1]

    input_date = date.fromisoformat(
        re.search(r"\d{4}-\d{2}-\d{2}", os.path.basename(input_file)).group())
    new_date = input_date + timedelta(days=args.days)

    json_out = os.path.join(RAW_DIR, f"books_raw_{new_date}.json")
    csv_out = os.path.join(RAW_DIR, f"books_raw_{new_date}.csv")
    log_out = os.path.join(RAW_DIR, f"sim_changes_{new_date}.json")
    if os.path.exists(json_out) or os.path.exists(csv_out):
        sys.exit(f"{json_out} already exists - refusing to overwrite. "
                 f"Use a different --days value or delete it first.")

    with open(input_file, "r", encoding="utf-8") as f:
        books = json.load(f)

    rng = random.Random(args.seed)
    new_books, log = simulate(books, new_date, rng, args.removed, args.new,
                              args.price_pct, args.category, args.stock)

    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(new_books, f, ensure_ascii=False, indent=4)
    pd.DataFrame(new_books).to_csv(csv_out, index=False, encoding="utf-8-sig")
    with open(log_out, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=4)

    print(f"Input : {input_file} ({len(books)} books)")
    print(f"Output: {json_out} ({len(new_books)} books)")
    print(f"        {csv_out}")
    print(f"Log   : {log_out}")
    for key, items in log.items():
        print(f"  {key:22s}: {len(items)}")


if __name__ == "__main__":
    main()