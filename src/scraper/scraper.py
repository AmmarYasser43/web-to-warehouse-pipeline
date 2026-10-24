import pandas as pd
import os
import time
import json
import csv
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"
HEADERS = {"User-Agent": "UniversityDataEngineeringProject/1.0 (educational use)"}
DELAY_SECONDS = 1      # rate limit between requests
MAX_RETRIES = 3
TIMEOUT = 15


def main():
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
    os.makedirs(RAW_DIR, exist_ok=True)
    print(f"Saving to: {RAW_DIR}")


    today = datetime.now().strftime("%Y-%m-%d")
    output_file = os.path.join(RAW_DIR, f"books_raw_{today}.json")
    csv_file = os.path.join(RAW_DIR, f"books_raw_{today}.csv")

    def get_soup(url):
        """GET a page with delay + retry, and return a BeautifulSoup object."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                time.sleep(DELAY_SECONDS)
                response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                response.raise_for_status()
                response.encoding = "utf-8"   # otherwise £ becomes Â£
                return BeautifulSoup(response.text, "html.parser")
            except requests.RequestException as e:
                print(f"  Attempt {attempt}/{MAX_RETRIES} failed: {e}")
                time.sleep(2 ** attempt)
        return None

    def parse_book(card, category, page_url):
        link = card.select_one("h3 a")
        rating_elem = card.select_one("p.star-rating")
        rating = next((c for c in rating_elem["class"] if c != "star-rating"), None)
        return {
            "Title": link["title"],
            "Category": category,
            "Price": card.select_one("p.price_color").get_text(strip=True),
            "Rating": rating,
            "Availability": card.select_one("p.availability").get_text(strip=True),
            "URL": urljoin(page_url, link["href"]),
            "Scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    # ==========================================
    # Load existing data (resume support)
    # ==========================================
    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as file:
            books = json.load(file)
            print(f"Loaded {len(books)} existing books from JSON.")
    else:
        books = []
        print("No existing JSON found. Starting fresh.")

    scraped_urls = {book["URL"] for book in books if "URL" in book}

    def save():
        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(books, file, ensure_ascii=False, indent=4)
        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(books, file, ensure_ascii=False, indent=4)
        if books:
            pd.DataFrame(books).to_csv(csv_file, index=False, encoding="utf-8-sig")

    # ==========================================
    # Extract books category by category
    # ==========================================
    print("Starting data extraction...")
    home = get_soup(BASE_URL)
    if home is None:
        print("Could not load the home page. Aborting.")
        return

    categories = [
        (a.get_text(strip=True), urljoin(BASE_URL, a["href"]))
        for a in home.select("div.side_categories ul li ul li a")
    ]
    total_categories = len(categories)

    try:
        for index, (category, category_url) in enumerate(categories, start=1):
            print(f"[{index}/{total_categories}] Category: {category}")
            page_url = category_url
            new_in_category = 0

            while page_url:
                soup = get_soup(page_url)
                if soup is None:
                    print(f"Failed to load: {page_url}")
                    break

                for card in soup.select("article.product_pod"):
                    try:
                        book = parse_book(card, category, page_url)
                    except Exception as e:
                        print(f"Error parsing a book on {page_url}: {e}")
                        continue
                    if book["URL"] in scraped_urls:
                        continue
                    books.append(book)
                    scraped_urls.add(book["URL"])
                    new_in_category += 1

                next_link = soup.select_one("li.next a")
                page_url = urljoin(page_url, next_link["href"]) if next_link else None

            save()   # save after each category
            print(f"Saved | New: {new_in_category} | Total scraped: {len(books)}")
    finally:
        save()   # also saves if you press Ctrl+C

    print(f"Extraction completed. Total books: {len(books)}")


if __name__ == "__main__":
    main()