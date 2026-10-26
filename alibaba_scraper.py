"""
ALIBABA STEP 6 (remade): scrape EVERY product on a results page, then go to the next page.

Steps 1-5 (unchanged): find the container and cards, open a product link, and read the product
                       fields (extract_product) into a CSV row.
Step 6 (remade)      : for page 1, 2, 3 ... up to page 100:
                       a) open the results page
                       b) scroll down until every product card on that page has loaded
                       c) collect the links of ALL cards on the page
                       d) open each link in a NEW tab, read the fields, close the tab, come back
                       e) append each row to the CSV right away
                       f) move to the next page

You can restart at any time: products already in the CSV are skipped.

Setup:
    pip install selenium
    (Google Chrome must be installed.)
Run:
    python alibaba_step6_all_pages.py                       # pages 1 to 100
    python alibaba_step6_all_pages.py --last-page 2         # a short test run first
    python alibaba_step6_all_pages.py --first-page 37       # continue from page 37
    python alibaba_step6_all_pages.py --fresh               # delete the old CSV and start over
"""
import argparse
import csv
import os
import time
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from selenium import webdriver
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

URL = (
    "https://www.alibaba.com/trade/search?spm=a2700.product_ggs_search.tabTop.2.21c413a0ausxNS"
    "&tab=all&has4Tab=true&pro=false&SearchText=scissors"
)

# ===================================================================== STEP 1 (unchanged)
# The class lists we accept for the container. The script succeeds if ANY ONE is found.
CONTAINER_CLASSES = [
    "organic-list app-organic-search-mb-20 viewtype-list",
    "organic-list app-organic-search-mb-20 viewtype-gallery",   # <- second variant goes here
]


def to_css(class_string, tag="div"):
    """Turn  'organic-list viewtype-list'  into  'div.organic-list.viewtype-list'."""
    return tag + "".join("." + name for name in class_string.split())


SELECTORS = [to_css(c) for c in CONTAINER_CLASSES]


def detect_container(driver):
    """Return (selector, element) for the first variant found on the page, else False."""
    for selector in SELECTORS:
        found = driver.find_elements(By.CSS_SELECTOR, selector)
        if found:
            return selector, found[0]
    return False


# ===================================================================== STEP 2 (unchanged)
CARD_CLASSES = "fy26-product-card-wrapper list-card fy26-product-card searchx-offer-item"
CARD = to_css(CARD_CLASSES)


def find_cards(driver):
    """Detect the container again, then look for cards INSIDE it.
    Returns a list of card elements, or False if there are none yet."""
    detected = detect_container(driver)
    if not detected:
        return False
    selector, container = detected
    cards = container.find_elements(By.CSS_SELECTOR, CARD)
    return cards or False


def one_line(element, limit=100):
    """The visible text of an element as one short line (for a quick preview)."""
    text = element.get_attribute("textContent") or ""
    return " ".join(text.split())[:limit]


# ===================================================================== STEP 3 (unchanged)
def first_card_links(driver):
    """Find the first card again and return its <a href> elements.
    Returns False while the card has no links yet, so WebDriverWait keeps waiting."""
    cards = find_cards(driver)
    if not cards:
        return False
    first_card = cards[0]
    # Cards further down the page may only fill in when they are on screen,
    # so we scroll the first card into view before looking for its links.
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", first_card)
    anchors = first_card.find_elements(By.CSS_SELECTOR, "a[href]")
    return anchors or False


def pick_product_link(links):
    """A card can hold several links (product, supplier, chat...).
    We prefer the one that points to a product detail page; otherwise the first link."""
    for text, href in links:
        if "/product-detail/" in href:
            return href
    return links[0][1] if links else None


# ===================================================================== STEP 4 (remade, version 4)
# a) the company card. It is found by an ATTRIBUTE, not a class:
#    [data-module-name="..."]   (square brackets, attribute name, equals sign, value in quotes)
#    '*' means any tag, because we don't know which tag it is.
COMPANY_CARD = '*[data-module-name="module_3_tab_mini_company_card"]'

# b) the product modules: <div class="module_title"> and so on (a class, so we use to_css)
MODULES = ["module_title", "module_comment", "module_price", "module_3_tab_key_attribute"]


def wait_and_find(driver, selector, timeout=20):
    """Wait until `selector` matches something, and return the list of matches ([] if none).

    Product pages load more content while you scroll, so each check that finds nothing
    scrolls the page down a little, then WebDriverWait checks again.
    """
    def check(d):
        found = d.find_elements(By.CSS_SELECTOR, selector)
        if found:
            return found
        d.execute_script("window.scrollBy(0, 700);")
        return False

    try:
        return WebDriverWait(
            driver, timeout, poll_frequency=0.5,
            ignored_exceptions=(StaleElementReferenceException,),
        ).until(check)
    except TimeoutException:
        return []


def show(label, elements, limit=3):
    """Print how many elements were found, plus a short preview of the first few."""
    if not elements:
        print(f"  {label}: NOT FOUND")
        return
    print(f"  {label}: {len(elements)} found")
    for number, element in enumerate(elements[:limit], start=1):
        try:
            print(f"    {number}. <{element.tag_name}> {one_line(element, 90) or '(no text)'}")
        except StaleElementReferenceException:
            print(f"    {number}. (the page redrew this element)")


# ===================================================================== STEP 5 (remade)
OUTPUT_CSV = "alibaba_products.csv"

# The CSV columns, in this order
COLUMNS = [
    "product_name", "product_url", "price_raw", "currency", "moq",
    "attributes", "supplier_name", "scraped_at",
]

DEFAULT_CURRENCY = "Indonesia"    # the "currency" column is filled with this fixed text


def test_id_selector(value):
    """Selector for an element marked with a test id.
    You wrote two spellings: data-testid="..." and data-test-id="...".
    The comma means "this OR that", so either spelling is accepted."""
    return f'*[data-testid="{value}"], *[data-test-id="{value}"]'


# Where each value lives on the product page
TITLE_H1 = "div.module_title h1"                                          # <h1> inside div.module_title
PRICE = test_id_selector("pc-purchase-current-price")
MOQ = test_id_selector("pc-purchase-effective-moq")
KEY_ATTRIBUTE_ROWS = test_id_selector("three-column-key-attributes-row")  # one element per attribute row
SUPPLIER_CARD = test_id_selector("three-column-mini-company-card")


def clean_text(element, limit=300):
    """Text of an element as one clean line ('' if the page redrew the element)."""
    try:
        return one_line(element, limit)
    except StaleElementReferenceException:
        return ""


def leaf_texts(driver, element):
    """The text pieces inside an element, one per innermost tag.
    Example: <div><span>Grade</span><span>Premium</span></div>  ->  ['Grade', 'Premium']"""
    try:
        return driver.execute_script(
            r"""const root = arguments[0];
               const clean = t => (t || '').replace(/\s+/g, ' ').trim();
               const leaves = [...root.querySelectorAll('*')]
                   .filter(e => e.children.length === 0)
                   .map(e => clean(e.textContent)).filter(t => t);
               if (leaves.length) return leaves;
               const own = clean(root.textContent);
               return own ? [own] : [];""",
            element)
    except StaleElementReferenceException:
        return []


def read_key_attributes(driver, rows):
    """Turn every attribute row into a (label, value) pair.
    Usually the first text piece is the label and the rest is the value."""
    pairs = []
    for row in rows:
        leaves = leaf_texts(driver, row)
        text = " ".join(leaves)
        if len(leaves) >= 2:
            label, value = leaves[0], " ".join(leaves[1:])
        elif ":" in text:                                  # one piece like "Grade: Premium"
            label, value = [part.strip() for part in text.split(":", 1)]
        else:
            label, value = text, ""
        label = label.rstrip(": ").strip()
        if label:
            pairs.append((label, value))
    return pairs


def format_attributes(pairs):
    """Join all (label, value) pairs into ONE text cell for the CSV, for example:
    'Blade Material: Stainless steel; Handle Material: Plastic; Grade: Premium'"""
    parts = [f"{label}: {value}" if value else label for label, value in pairs]
    return "; ".join(parts)


def read_supplier_name(driver, card):
    """The supplier name from the company card: the text of its first link,
    or else its first piece of text. Returns (name, how_it_was_found)."""
    try:
        links = [clean_text(a) for a in card.find_elements(By.TAG_NAME, "a")]
    except StaleElementReferenceException:
        links = []
    links = [text for text in links if text]
    if links:
        return links[0], "text of the first link in the card"
    pieces = leaf_texts(driver, card)
    if pieces:
        return pieces[0], "first piece of text in the card"
    return "", ""


def extract_product(driver, product_url):
    """Read every field and return (row_dict, details_dict). Missing fields stay empty ('')."""
    row = {column: "" for column in COLUMNS}
    details = {"pairs": [], "supplier_how": "", "supplier_pieces": []}

    # product_name: the <h1> inside div.module_title
    h1 = wait_and_find(driver, TITLE_H1, timeout=15)
    row["product_name"] = clean_text(h1[0]) if h1 else ""

    # product_url: the link we followed in step 3
    row["product_url"] = product_url

    # price_raw, currency, moq
    price = wait_and_find(driver, PRICE, timeout=15)
    row["price_raw"] = clean_text(price[0]) if price else ""
    row["currency"] = DEFAULT_CURRENCY
    moq = wait_and_find(driver, MOQ, timeout=15)
    row["moq"] = clean_text(moq[0]) if moq else ""

    # attributes: read ALL attribute rows and put them together in one cell
    attribute_rows = wait_and_find(driver, KEY_ATTRIBUTE_ROWS, timeout=15)
    pairs = read_key_attributes(driver, attribute_rows)
    details["pairs"] = pairs
    row["attributes"] = format_attributes(pairs)

    # supplier_name: from the mini company card
    card = wait_and_find(driver, SUPPLIER_CARD, timeout=15)
    if card:
        row["supplier_name"], details["supplier_how"] = read_supplier_name(driver, card[0])
        details["supplier_pieces"] = leaf_texts(driver, card[0])

    # scraped_at: the time we read the page
    row["scraped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return row, details


def save_to_csv(rows, path):
    """Write a header line and one line per product.
    'utf-8-sig' lets Excel show special characters correctly when you open the file."""
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# ===================================================================== STEP 6 (remade)
FIRST_PAGE = 1
LAST_PAGE = 100
DELAY_BETWEEN_PRODUCTS = 3   # seconds to pause between products (be polite to the site)


def is_blocked(url):
    """Alibaba's verification pages have 'punish' or 'captcha' in the address."""
    url = url.lower()
    return "punish" in url or "captcha" in url


def build_page_url(page):
    """The search URL for page N: the same URL plus a 'page=N' parameter.
    ASSUMPTION: Alibaba reads 'page' from the address. The script checks this at run time
    (if page 2 shows the same products as page 1, it stops and tells you)."""
    parts = urlparse(URL)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if page > 1:
        query["page"] = str(page)
    else:
        query.pop("page", None)
    return urlunparse(parts._replace(query=urlencode(query)))


class CardLoader:
    """Used with WebDriverWait. Each check scrolls down a little and counts the cards.
    It returns the count once the page is at the bottom and the count has stopped growing
    (4 checks in a row), meaning every card on this page has loaded."""
    def __init__(self, card_selector):
        self.card_selector = card_selector
        self.last = -1
        self.stable = 0

    def __call__(self, driver):
        count = len(driver.find_elements(By.CSS_SELECTOR, self.card_selector))
        at_bottom = driver.execute_script(
            "return window.innerHeight + window.scrollY >= document.body.scrollHeight - 5;")
        self.stable = self.stable + 1 if (count == self.last and at_bottom) else 0
        self.last = count
        if self.stable >= 4:
            return count
        driver.execute_script("window.scrollBy(0, 1000);")
        return False


def load_all_cards(driver, card_selector, timeout=90):
    """Scroll until all cards on the page have loaded. Returns how many cards there are."""
    loader = CardLoader(card_selector)
    try:
        return WebDriverWait(driver, timeout, poll_frequency=0.5).until(loader)
    except TimeoutException:
        return loader.last      # use whatever has loaded so far


def collect_page_urls(driver, card_selector):
    """The product link of EVERY card on the page, in order, without duplicates.
    One JavaScript call reads all cards at once, so nothing can go stale."""
    data = driver.execute_script(
        r"""return [...document.querySelectorAll(arguments[0])].map(card =>
               [...card.querySelectorAll('a[href]')].map(a => [(a.textContent || '').trim().slice(0, 50), a.href]));""",
        card_selector)
    urls = []
    for card_links in data:
        links = [(" ".join(text.split()), href) for text, href in card_links]
        url = pick_product_link(links)          # prefers the '/product-detail/' link
        if url and url not in urls:
            urls.append(url)
    return urls


def load_done_urls(path):
    """The product_url values already saved in the CSV (so a restart skips them)."""
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8-sig") as file:
        return {row.get("product_url", "") for row in csv.DictReader(file)} - {""}


def append_row(path, row):
    """Add ONE row to the end of the CSV (and the header line if the file is new)."""
    is_new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def scrape_in_new_tab(driver, search_tab, product_url):
    """Open the product in a NEW tab, read its fields, close the tab, and go back to the
    search tab. Returns (status, row, details). status is 'ok' or 'blocked'.

    The 'finally' part always runs, even after an error, so we never get stuck in the wrong tab.
    """
    driver.switch_to.new_window("tab")        # opens a new tab and switches to it
    try:
        driver.get(product_url)
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        now = driver.current_url.lower()
        if "punish" in now or "captcha" in now:
            return "blocked", None, None
        row, details = extract_product(driver, product_url)
        return "ok", row, details
    finally:
        driver.close()                         # close the product tab
        driver.switch_to.window(search_tab)    # back to the search results tab


def main():
    parser = argparse.ArgumentParser(description="Scrape Alibaba search results page by page")
    parser.add_argument("--first-page", type=int, default=FIRST_PAGE)
    parser.add_argument("--last-page", type=int, default=LAST_PAGE)
    parser.add_argument("--delay", type=float, default=DELAY_BETWEEN_PRODUCTS,
                        help="seconds to pause between products")
    parser.add_argument("--fresh", action="store_true", help="delete the old CSV and start over")
    args = parser.parse_args()

    if args.fresh and os.path.exists(OUTPUT_CSV):
        try:
            os.remove(OUTPUT_CSV)
        except PermissionError:
            print(f"Could not delete {OUTPUT_CSV}. Close it in Excel and run again.")
            return

    seen = load_done_urls(OUTPUT_CSV)
    print(f"Pages {args.first_page} to {args.last_page}. "
          f"Products already in {OUTPUT_CSV}: {len(seen)} (they will be skipped).")

    print("Starting Chrome...")
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)

    saved, failed, pages_done = 0, [], []
    stop_reason = f"reached page {args.last_page}"
    last_page_urls = set()
    try:
        search_tab = driver.current_window_handle      # the tab that stays on the results pages
        stop = False

        for page in range(args.first_page, args.last_page + 1):
            print()
            print(f"=== Page {page} of {args.last_page} ===")

            # a) open the results page (two attempts)
            selector = None
            for attempt in (1, 2):
                driver.get(build_page_url(page))
                if is_blocked(driver.current_url):
                    break
                try:
                    selector, _ = WebDriverWait(driver, 30, poll_frequency=0.5).until(detect_container)
                    break
                except TimeoutException:
                    print(f"  The product list did not appear (try {attempt}/2).")

            if is_blocked(driver.current_url):
                print("  BLOCKED: Alibaba is showing a verification page.")
                print("  Solve it by hand in a normal browser, then run again with --first-page "
                      f"{page}.")
                stop_reason = f"blocked on page {page}"
                break
            if selector is None:
                stop_reason = f"no product list on page {page} (end of results, or a page problem)"
                break

            # b) scroll until every card has loaded
            card_selector = f"{selector} {CARD}"
            try:
                WebDriverWait(driver, 30, poll_frequency=0.5).until(
                    lambda d: d.find_elements(By.CSS_SELECTOR, card_selector))
            except TimeoutException:
                stop_reason = f"no product cards on page {page} (end of results)"
                break
            card_count = load_all_cards(driver, card_selector)

            # c) the links of ALL cards on this page
            urls = collect_page_urls(driver, card_selector)
            print(f"  {card_count} cards loaded, {len(urls)} product links found")

            if urls and set(urls) == last_page_urls:
                stop_reason = (f"page {page} shows the same products as the page before. "
                               "The 'page' parameter may not work, or the results ended")
                break
            last_page_urls = set(urls)

            new_urls = [u for u in urls if u not in seen]
            print(f"  {len(new_urls)} new, {len(urls) - len(new_urls)} already saved")
            pages_done.append(page)

            # d) + e) each product in a new tab, then save its row
            for number, product_url in enumerate(new_urls, start=1):
                print(f"  [{page}.{number}/{len(new_urls)}] {product_url[:90]}")
                try:
                    status, row, details = scrape_in_new_tab(driver, search_tab, product_url)
                except WebDriverException as error:
                    print(f"      FAILED: {type(error).__name__}. Moving on.")
                    failed.append(product_url)
                    continue

                if status == "blocked":
                    print("      BLOCKED: Alibaba is showing a verification page instead of the product.")
                    print(f"      Solve it by hand in a normal browser, then run again with --first-page {page}.")
                    stop_reason = f"blocked on a product of page {page}"
                    stop = True
                    break

                append_row(OUTPUT_CSV, row)
                seen.add(product_url)
                saved += 1
                print(f"      {row['product_name'][:60] or '(no name)'} | {row['price_raw'] or '(no price)'}"
                      f" | {row['supplier_name'][:30] or '(no supplier)'}")
                time.sleep(args.delay)

            if stop:
                break
            # f) the loop now moves on to the next page

    except Exception as error:
        stop_reason = f"error: {error}"

    finally:
        driver.quit()
        print()
        print("Browser closed.")

    print()
    print("Finished step 6:")
    print(f"  Stopped because      : {stop_reason}")
    print(f"  Pages processed      : {len(pages_done)}" + (f" ({pages_done[0]} to {pages_done[-1]})" if pages_done else ""))
    print(f"  Products saved (now) : {saved}")
    print(f"  Failed products      : {len(failed)}")
    print(f"  Total products in CSV: {len(seen)}")
    print(f"  File                 : {OUTPUT_CSV}")


if __name__ == "__main__":
    main()