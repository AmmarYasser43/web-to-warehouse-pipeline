import os
import re
import sys
import glob
from datetime import date

import pandas as pd
import pyodbc


def get_connection():
    """Windows authentication by default; set DB_USER / DB_PASSWORD for SQL login."""
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    server = os.getenv("DB_SERVER", r"DESKTOP-BVMNIQD\MSSQLSERVEREXPRE")
    database = os.getenv("DB_NAME", "products_db")
    conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
    if os.getenv("DB_USER"):
        conn_str += f"UID={os.getenv('DB_USER')};PWD={os.getenv('DB_PASSWORD', '')};"
    else:
        conn_str += "Trusted_Connection=yes;"
    conn_str += "TrustServerCertificate=yes;"
    return pyodbc.connect(conn_str)


def py(value):
    """NaN -> None, numpy types -> plain Python (pyodbc needs this)."""
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def load(df, run_date, conn):
    cur = conn.cursor()

    # 1) categories: insert the new ones, then read back name -> id
    cur.execute("SELECT name, category_id FROM dbo.categories")
    cat_ids = {name: cid for name, cid in cur.fetchall()}
    new_categories = [(c,) for c in df["Category"].dropna().unique() if c not in cat_ids]
    if new_categories:
        cur.executemany("INSERT INTO dbo.categories (name) VALUES (?)", new_categories)
        cur.execute("SELECT name, category_id FROM dbo.categories")
        cat_ids = {name: cid for name, cid in cur.fetchall()}

    # 2) products: new -> INSERT, existing -> UPDATE current state
    cur.execute("SELECT url FROM dbo.products")
    existing_urls = {row[0] for row in cur.fetchall()}

    to_insert, to_update = [], []
    for r in df.itertuples():
        cat_id = cat_ids.get(r.Category)
        if r.URL in existing_urls:
            to_update.append((r.Title, cat_id, run_date, r.URL))
        else:
            to_insert.append((r.URL, r.Title, cat_id, run_date, run_date))

    if to_insert:
        cur.executemany(
            """INSERT INTO dbo.products
               (url, title, category_id, first_seen_date, last_seen_date, is_active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            to_insert,
        )
    if to_update:
        cur.executemany(
            """UPDATE dbo.products
               SET title = ?, category_id = ?, last_seen_date = ?, is_active = 1
               WHERE url = ?""",
            to_update,
        )

    # 3) removed products: active before, not seen in this run
    cur.execute(
        "UPDATE dbo.products SET is_active = 0 WHERE is_active = 1 AND last_seen_date < ?",
        run_date,
    )
    removed = cur.rowcount

    # 4) price_history: one row per product for this snapshot date
    cur.execute("SELECT url, product_id FROM dbo.products")
    product_ids = {url: pid for url, pid in cur.fetchall()}

    cur.execute("SELECT product_id FROM dbo.price_history WHERE snapshot_date = ?", run_date)
    already_loaded = {row[0] for row in cur.fetchall()}   # makes re-running the same file safe

    history = []
    for r in df.itertuples():
        pid = product_ids[r.URL]
        if pid in already_loaded:
            continue
        rating = py(r.Rating)
        history.append((
            pid,
            run_date,
            py(r.Price),
            int(rating) if rating is not None else None,
            py(r.In_stock),
            cat_ids.get(r.Category),
            py(r.Scraped_at),
        ))
    if history:
        cur.executemany(
            """INSERT INTO dbo.price_history
               (product_id, snapshot_date, price, rating, in_stock, category_id, scraped_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            history,
        )

    print(f"Run {run_date}: {len(df)} books | new products: {len(to_insert)} | "
          f"updated: {len(to_update)} | marked removed: {removed} | "
          f"history rows added: {len(history)}")


def main(input_file=None):
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

    if input_file is None:
        input_file = sorted(glob.glob(os.path.join(PROCESSED_DIR, "books_clean_*.csv")))[-1]

    run_date = date.fromisoformat(
        re.search(r"\d{4}-\d{2}-\d{2}", os.path.basename(input_file)).group()
    )
    df = pd.read_csv(input_file)

    conn = get_connection()
    try:
        load(df, run_date, conn)
        conn.commit()          # everything or nothing
        print("Loaded successfully.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)