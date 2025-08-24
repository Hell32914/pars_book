"""
Books to Scrape → Excel/CSV parser
- Пагинация (все страницы или ограничение)
- Чистые поля: title, price(float), rating(int 1–5), availability, product_url
- Опционально: category, description, upc, image_url и др. (из карточки)
- Параметры CLI: --max-pages, --output, --details, --start-url
"""

from __future__ import annotations
import argparse
import time
import re
from typing import Optional, Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import pandas as pd

START_URL = "https://books.toscrape.com/catalogue/page-1.html"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/119.0.0.0 Safari/537.36"
    )
}

def backoff_sleep(attempt: int) -> None:
    time.sleep(min(2 ** attempt, 10))

def get_soup(url: str, session: requests.Session, max_retries: int = 3, timeout: int = 20) -> BeautifulSoup:
    last_exc = None
    for attempt in range(max_retries):
        try:
            resp = session.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code in (429,) or 500 <= resp.status_code < 600:
                backoff_sleep(attempt)
                continue
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            last_exc = e
            backoff_sleep(attempt)
    raise RuntimeError(f"Failed to load {url}: {last_exc}")

def parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", text.replace(",", "."))
    return float(m.group(1)) if m else None

def parse_rating(tag) -> Optional[int]:
    if not tag:
        return None
    mapping = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
    for cls in tag.get("class", []):
        if cls in mapping:
            return mapping[cls]
    return None

def parse_list_page(soup: BeautifulSoup, base_url: str) -> List[Dict]:
    items = []
    for card in soup.select("article.product_pod"):
        a = card.select_one("h3 a")
        title = a.get("title") or a.get_text(strip=True)
        product_url = urljoin(base_url, a.get("href"))

        price_tag = card.select_one("p.price_color")
        rating_tag = card.select_one("p.star-rating")
        avail_tag = card.select_one("p.instock.availability")

        items.append({
            "title": title,
            "price": parse_price(price_tag.get_text(strip=True) if price_tag else ""),
            "rating": parse_rating(rating_tag),
            "availability": " ".join(avail_tag.get_text(strip=True).split()) if avail_tag else None,
            "product_url": product_url,
        })
    return items

def find_next_page(soup: BeautifulSoup, current_url: str) -> Optional[str]:
    a = soup.select_one("li.next a")
    return urljoin(current_url, a.get("href")) if a else None

def parse_details(product_url: str, session: requests.Session) -> Dict[str, Optional[str]]:
    soup = get_soup(product_url, session=session)

    category = None
    crumbs = soup.select("ul.breadcrumb li a")
    if len(crumbs) >= 3:
        category = crumbs[-1].get_text(strip=True)

    description = None
    header = soup.select_one("#product_description")
    if header:
        p = header.find_next("p")
        if p:
            description = p.get_text(strip=True)

    details = {}
    table = soup.select_one("table.table")
    if table:
        for row in table.select("tr"):
            th, td = row.find("th"), row.find("td")
            if th and td:
                key = th.get_text(strip=True).lower().replace(" ", "_")
                details[key] = td.get_text(strip=True)

    img = soup.select_one(".item.active img") or soup.select_one("img")
    image_url = urljoin(product_url, img.get("src")) if img and img.get("src") else None

    return {"category": category, "description": description, "image_url": image_url, **details}

def scrape(start_url: str, max_pages: Optional[int], with_details: bool) -> pd.DataFrame:
    session = requests.Session()
    url = start_url
    page = 0
    rows: List[Dict] = []

    while url:
        page += 1
        soup = get_soup(url, session=session)
        items = parse_list_page(soup, base_url=url)

        if with_details:
            for it in items:
                try:
                    extra = parse_details(it["product_url"], session=session)
                    it.update(extra)
                except Exception as e:
                    it["details_error"] = str(e)

        rows.extend(items)
        if max_pages and page >= max_pages:
            break
        url = find_next_page(soup, current_url=url)

    df = pd.DataFrame(rows)
    if not df.empty:
        df.drop_duplicates(subset=["product_url"], inplace=True)
        preferred = ["title", "price", "rating", "availability", "category", "product_url", "description", "image_url"]
        cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
        df = df[cols]
    return df

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-url", default=START_URL)
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--output", default="books.xlsx")
    args = parser.parse_args()

    max_pages = None if args.max_pages == 0 else args.max_pages
    df = scrape(args.start_url, max_pages, args.details)

    if df.empty:
        print("No data collected.")
        return

    if args.output.lower().endswith(".csv"):
        df.to_csv(args.output, index=False, encoding="utf-8-sig")
    else:
        df.to_excel(args.output, index=False, engine="openpyxl")
    print(f"Saved {len(df)} records → {args.output}")

if __name__ == "__main__":
    main()
