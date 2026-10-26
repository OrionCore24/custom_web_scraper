"""
STEP 4: Scrape NBA player stats for every season from 2026-27 down to 2017-18.

Builds on steps 1-3 (open the page, find the table, find the dropdowns).
New in this step:
  - choose each season in the Season dropdown
  - choose "All" in the page-size dropdown so every player is shown
  - wait (explicit waits, no fixed sleeps) until the table has finished updating
  - read the table, add a Season column, check duplicates and missing values
  - save everything to nba_player_stats_2017-18_to_2026-27.csv

Setup:
    pip install selenium pandas
Run:
    python step4_scrape_seasons.py
    python step4_scrape_seasons.py --headless     # no visible browser window
"""
import argparse
import logging
import re
from functools import wraps

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

# ----------------------------------------------------------------------------- settings
URL = "https://www.nba.com/stats/players/traditional"

# Both dropdowns share one class, so we tell them apart by their PARENT <div>.
DROPDOWN = "select.DropDown_select__l0YXl"
SEASON_SELECT = "div.Block_blockContent___l4IE " + DROPDOWN   # season lives here
PLAYER_SELECT = "div.Crom_base__heTBP " + DROPDOWN            # the "All" dropdown lives here
TABLE = "table.Crom_table__PJugT"
BODY = "tbody.Crom_body__PXe4p"

# 2026-27, 2025-26, ... 1999-2000
SEASONS = [f"{y}-{str(y + 1)[-2:]}" for y in range(2026, 1999, -1)]
OUTPUT_CSV = "nba_player_stats_2000-01_to_2026-27.csv"

SEASON_RE = re.compile(r"^\d{4}-\d{2}$")
DEFAULT_PAGE_SIZE = 50   # rows the site shows before "All" is chosen
MAX_ATTEMPTS = 3         # tries per season before giving up on it

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s")
log = logging.getLogger("nba")


# ----------------------------------------------------------------------------- small helpers
def retry_stale(attempts=3):
    """A 'stale element' error means the page redrew the element we were holding.
    The fix is simply to find it again, so we retry the whole function."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            for i in range(attempts):
                try:
                    return fn(*args, **kwargs)
                except StaleElementReferenceException:
                    if i == attempts - 1:
                        raise
        return wrapper
    return decorator


def wait(driver, timeout):
    """An explicit wait that checks every 0.5s and ignores 'not there yet' errors."""
    return WebDriverWait(
        driver, timeout, poll_frequency=0.5,
        ignored_exceptions=(NoSuchElementException, StaleElementReferenceException),
    )


def label_of(option):
    # textContent works even when the dropdown is closed (.text can be empty)
    return (option.get_attribute("textContent") or "").strip()


def option_labels(select_el):
    return [label_of(o) for o in Select(select_el).options]


def selected_label(select_el):
    return label_of(Select(select_el).first_selected_option)


def row_count(driver):
    return driver.execute_script(
        "return document.querySelectorAll(arguments[0]).length", BODY + " tr")


def table_signature(driver):
    """A fingerprint of the table (first rows + row count). It changes when new data loads."""
    return driver.execute_script(
        """const b = document.querySelector(arguments[0]);
           if (!b) return null;
           const r = [...b.querySelectorAll('tr')];
           return r.slice(0, 3).map(x => x.textContent).join('|') + '#' + r.length;""",
        BODY)

def make_driver(headless):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(90)
    return driver


def open_page(driver):
    """Step 1 + 2: open the page and wait until the table has rows."""
    driver.get(URL)
    wait(driver, 45).until(EC.presence_of_element_located((By.CSS_SELECTOR, TABLE)))
    wait(driver, 45).until(lambda d: row_count(d) > 0)
    try:  # a cookie banner can cover the dropdowns
        WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
    except TimeoutException:
        pass
    log.info("Page is active: %s (%d rows)", driver.title, row_count(driver))


@retry_stale()
def report_dropdowns(driver):
    """Step 3: show every dropdown and its current value (so you can see the page defaults)."""
    for el in driver.find_elements(By.CSS_SELECTOR, DROPDOWN):
        log.info("Dropdown %-12s current = %s", el.get_attribute("name") or "(no name)",
                 selected_label(el))


# ----------------------------------------------------------------------------- step 4: dropdowns
@retry_stale()
def find_season_dropdown(driver):
    """The <select> inside Block_blockContent whose options look like '2024-25'."""
    for el in driver.find_elements(By.CSS_SELECTOR, SEASON_SELECT):
        if el.get_attribute("name") == "Season":
            return el
        if any(SEASON_RE.match(label) for label in option_labels(el)):
            return el
    raise NoSuchElementException("Season dropdown not found")


@retry_stale()
def find_player_dropdown(driver):
    """The <select> inside Crom_base that has an 'All' option."""
    for el in driver.find_elements(By.CSS_SELECTOR, PLAYER_SELECT):
        if "All" in option_labels(el):
            return el
    raise NoSuchElementException("Dropdown with an 'All' option not found")


@retry_stale()
def choose_option(driver, finder, label):
    """Pick `label` in the dropdown returned by `finder`. Returns True if it changed."""
    el = finder(driver)
    labels = option_labels(el)
    if label not in labels:
        raise ValueError(f"Option {label!r} is not offered by this dropdown")
    if selected_label(el) == label:
        return False
    index = labels.index(label)
    try:
        Select(el).select_by_index(index)
    except (ElementNotInteractableException, ElementClickInterceptedException):
        # Fallback: set it with JavaScript and tell the page it changed
        driver.execute_script(
            "arguments[0].selectedIndex = arguments[1];"
            "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", el, index)
    return True


class StableRows:
    """Used with WebDriverWait: true once the row count stops changing for 3 checks in a row."""
    def __init__(self, needed=3):
        self.needed, self.last, self.hits = needed, -1, 0

    def __call__(self, driver):
        n = row_count(driver)
        self.hits = self.hits + 1 if (n > 0 and n == self.last) else 0
        self.last = n
        return n if self.hits >= self.needed else False


def wait_table_stable(driver, timeout=60):
    return wait(driver, timeout).until(StableRows())


def extract_table(driver):
    """Read headers and every row in ONE JavaScript call (much faster than cell-by-cell)."""
    return driver.execute_script(
        """const table = document.querySelector(arguments[0]);
           const body = document.querySelector(arguments[1]);
           const headers = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
           const rows = [...body.querySelectorAll('tr')]
               .map(tr => [...tr.querySelectorAll('td')].map(td => td.textContent.trim()));
           return {headers: headers, rows: rows};""",
        TABLE, BODY)


def build_dataframe(headers, rows, season):
    headers = [h or "RANK" for h in headers]           # the first header cell is blank
    seen, names = {}, []
    for h in headers:                                   # make sure column names are unique
        seen[h] = seen.get(h, 0) + 1
        names.append(h if seen[h] == 1 else f"{h}_{seen[h]}")

    clean, mismatched = [], 0
    for row in rows:
        if not row:
            continue
        if len(row) != len(names):
            mismatched += 1
            row = (row + [""] * len(names))[:len(names)]
        clean.append(row)
    if mismatched:
        log.warning("%s: %d rows had a different number of cells than headers", season, mismatched)

    df = pd.DataFrame(clean, columns=names)
    df.insert(0, "Season", season)
    return df


NEXT_BUTTON = "//button[@title='Next Page' or @aria-label='Next Page' or @aria-label='Next']"


def collect_remaining_pages(driver, rows, max_pages=60):
    """Fallback if 'All' did not show every player: click 'Next' until it is disabled.
    NOTE: the Next-button locator above is a best guess; check it with Inspect if this runs."""
    for _ in range(max_pages):
        buttons = driver.find_elements(By.XPATH, NEXT_BUTTON)
        if not buttons or not buttons[0].is_enabled():
            break
        before = table_signature(driver)
        driver.execute_script("arguments[0].click();", buttons[0])
        try:
            wait(driver, 15).until(lambda d: table_signature(d) != before)
        except TimeoutException:
            break
        wait_table_stable(driver)
        rows.extend(extract_table(driver)["rows"])
    return rows


def scrape_season(driver, season):
    """Select one season + 'All', wait for the table, and return it as a DataFrame."""
    # 1) Season dropdown
    before = table_signature(driver)
    changed = choose_option(driver, find_season_dropdown, season)
    wait(driver, 15).until(lambda d: selected_label(find_season_dropdown(d)) == season)
    if changed:
        try:
            wait(driver, 30).until(lambda d: table_signature(d) != before)
        except TimeoutException:
            log.warning("%s: table did not visibly change after choosing the season", season)

    try:  # a season with no data shows an empty table
        wait(driver, 15).until(lambda d: row_count(d) > 0)
    except TimeoutException:
        log.warning("%s: no rows in the table (no data for this season)", season)
        return pd.DataFrame()

    # 2) "All" in the page-size dropdown
    changed_all = choose_option(driver, find_player_dropdown, "All")
    wait(driver, 15).until(lambda d: selected_label(find_player_dropdown(d)) == "All")
    if changed_all:
        try:
            wait(driver, 20).until(lambda d: row_count(d) > DEFAULT_PAGE_SIZE)
        except TimeoutException:
            log.warning("%s: still %d rows after choosing 'All'", season, row_count(driver))

    # 3) Wait until the number of rows stops changing, then read the table
    wait_table_stable(driver)
    data = extract_table(driver)
    rows = data["rows"]

    # 4) Don't just trust "All": check the result
    if len(rows) <= DEFAULT_PAGE_SIZE:
        log.warning("%s: only %d rows after 'All'. Trying pagination as a fallback.", season, len(rows))
        rows = collect_remaining_pages(driver, rows)

    return build_dataframe(data["headers"], rows, season)


# ----------------------------------------------------------------------------- validation + output
def clean_and_validate(df):
    # Empty cells and "-" both mean "no value"
    df = df.replace({"": pd.NA, "-": pd.NA})

    # Turn numeric-looking columns into numbers (leave names/teams as text)
    for col in df.columns:
        if col in ("Season", "PLAYER", "TEAM"):
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() == df[col].notna().sum():
            df[col] = converted

    # Exact duplicate rows (for example from overlapping pages) are removed
    exact = int(df.duplicated().sum())
    if exact:
        log.warning("Removed %d exact duplicate rows", exact)
        df = df.drop_duplicates().reset_index(drop=True)

    # Same player + team + season twice is suspicious, so report it but keep it
    if {"PLAYER", "TEAM"} <= set(df.columns):
        same = int(df.duplicated(subset=["Season", "PLAYER", "TEAM"]).sum())
        if same:
            log.warning("%d rows share the same Season + PLAYER + TEAM (kept, please check)", same)

    missing = df.isna().sum()
    missing = missing[missing > 0]
    if missing.empty:
        log.info("Missing values: none")
    else:
        log.info("Missing values per column: %s", missing.to_dict())
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true", help="run Chrome without a window")
    args = parser.parse_args()

    driver = make_driver(args.headless)
    frames, counts = [], {}
    try:
        open_page(driver)           # steps 1-2
        report_dropdowns(driver)    # step 3

        available = option_labels(find_season_dropdown(driver))
        log.info("Seasons offered by the site: %s ... %s (%d)", available[0], available[-1], len(available))

        for season in SEASONS:
            if season not in available:
                log.warning("%s is not offered by the site, skipping", season)
                counts[season] = 0
                continue

            df = None
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    log.info("Scraping %s (try %d/%d)", season, attempt, MAX_ATTEMPTS)
                    df = scrape_season(driver, season)
                    break
                except (WebDriverException, ValueError) as error:
                    log.warning("%s failed: %s", season, str(error).splitlines()[0] if str(error) else type(error).__name__)
                    if attempt < MAX_ATTEMPTS:
                        try:
                            open_page(driver)   # reload a clean page, then try again
                        except WebDriverException as reload_error:
                            log.warning("Reload failed: %s", type(reload_error).__name__)

            if df is None or df.empty:
                log.error("%s: no data collected, moving on", season)
                counts[season] = 0
                continue
            frames.append(df)
            counts[season] = len(df)
            log.info("%s: %d player records", season, len(df))
    finally:
        driver.quit()

    if not frames:
        log.error("Nothing was scraped, so no CSV was written.")
        return

    combined = clean_and_validate(pd.concat(frames, ignore_index=True))
    combined.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print("\nPlayer records per season (before duplicate removal):")
    for season in SEASONS:
        print(f"  {season}: {counts.get(season, 0)}")
    print(f"\nTotal records saved: {len(combined)}")
    print(f"File: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()