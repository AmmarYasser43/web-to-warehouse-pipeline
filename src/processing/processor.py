import os
import re
import sys
import glob
import pandas as pd

RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def clean(df):
    df = df.copy()
    rows_in = len(df)

    # 1) Missing values in the important columns
    df = df.dropna(subset=["Title", "Price", "URL"])

    # 2) Whitespace
    df["Title"] = df["Title"].str.strip()
    df["Category"] = df["Category"].str.strip()

    # 3) Types
    df["Price"] = pd.to_numeric(
        df["Price"].astype(str).str.replace(r"[^\d.]", "", regex=True),
        errors="coerce",
    )
    df["Rating"] = df["Rating"].map(RATINGS)
    df["In_stock"] = df["Availability"].str.contains("In stock", case=False, na=False)
    df["Scraped_at"] = pd.to_datetime(df["Scraped_at"], utc=True)

    # 4) Validation: price must exist and be >= 0
    df = df[df["Price"].notna() & (df["Price"] >= 0)]

    # 5) Duplicates: URL is the unique key
    df = df.drop_duplicates(subset="URL", keep="last")

    # Report (titles are only reported, not deleted: different books can share a title)
    print(f"Rows in: {rows_in} | Rows out: {len(df)} | Removed: {rows_in - len(df)}")
    print(f"Rows with unknown rating: {df['Rating'].isna().sum()}")
    print(f"Duplicate titles (check manually): {df['Title'].duplicated().sum()}")
    return df


def main(input_file=None):
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
    PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    # No file given -> use the latest raw CSV
    if input_file is None:
        input_file = sorted(glob.glob(os.path.join(RAW_DIR, "books_raw_*.csv")))[-1]

    run_date = re.search(r"\d{4}-\d{2}-\d{2}", os.path.basename(input_file)).group()
    df = clean(pd.read_csv(input_file))

    output_file = os.path.join(PROCESSED_DIR, f"books_clean_{run_date}.csv")
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"Saved -> {output_file}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)