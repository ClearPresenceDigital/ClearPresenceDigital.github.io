#!/usr/bin/env python3
"""
Lead Scraper — Scrapes Google Maps listings for a given query.
Outputs structured JSON + Excel with contact info and listing quality data.

Usage:
    source venv/bin/activate
    python3 scraper.py "plumbers east brunswick nj"
    python3 scraper.py "plumbers east brunswick nj" --max 10
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import random
import logging
from datetime import datetime, timezone
from urllib.parse import quote_plus

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "leads.db")

# ---------------------------------------------------------------------------
# SQLite CRM database
# ---------------------------------------------------------------------------

def init_db():
    """Create the leads table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            -- Scraped data
            name            TEXT,
            address         TEXT,
            phone           TEXT,
            website         TEXT,
            rating          REAL,
            review_count    INTEGER,
            category        TEXT,
            maps_link       TEXT UNIQUE,
            photo_url       TEXT,

            -- Quality signals
            photo_count     INTEGER,
            has_description INTEGER,
            has_services    INTEGER,
            owner_responds  INTEGER,
            newest_review   TEXT,
            has_hours       INTEGER,

            -- Lead scoring
            lead_score      INTEGER,
            score_reasons   TEXT,

            -- CRM tracking
            contact_status  TEXT DEFAULT 'new',
            last_contacted  TEXT,
            notes           TEXT,

            -- Metadata
            query           TEXT,
            scraped_at      TEXT,
            updated_at      TEXT
        )
    """)
    conn.commit()
    conn.close()
    log.info(f"Database ready: {DB_PATH}")


def upsert_leads(listings, query):
    """Insert or update leads, preserving CRM fields on re-scrape."""
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()

    for lead in listings:
        # Check if this lead already exists (by maps_link)
        row = conn.execute(
            "SELECT contact_status, last_contacted, notes, scraped_at FROM leads WHERE maps_link = ?",
            (lead["maps_link"],)
        ).fetchone()

        if row:
            # Update scraped fields, preserve CRM fields
            conn.execute("""
                UPDATE leads SET
                    name=?, address=?, phone=?, website=?, rating=?, review_count=?,
                    category=?, photo_url=?, photo_count=?, has_description=?,
                    has_services=?, owner_responds=?, newest_review=?, has_hours=?,
                    lead_score=?, score_reasons=?, query=?, updated_at=?
                WHERE maps_link=?
            """, (
                lead["name"], lead["address"], lead["phone"], lead["website"],
                lead["rating"], lead["review_count"], lead["category"],
                lead["photo_url"], lead.get("photo_count"),
                lead.get("has_description", False), lead.get("has_services", False),
                lead.get("owner_responds", False), lead.get("newest_review", ""),
                lead.get("has_hours", False),
                lead.get("lead_score", 0), lead.get("score_reasons", ""),
                query, now,
                lead["maps_link"],
            ))
        else:
            # New lead
            conn.execute("""
                INSERT INTO leads (
                    name, address, phone, website, rating, review_count,
                    category, maps_link, photo_url, photo_count, has_description,
                    has_services, owner_responds, newest_review, has_hours,
                    lead_score, score_reasons, contact_status, query, scraped_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)
            """, (
                lead["name"], lead["address"], lead["phone"], lead["website"],
                lead["rating"], lead["review_count"], lead["category"],
                lead["maps_link"], lead["photo_url"], lead.get("photo_count"),
                lead.get("has_description", False), lead.get("has_services", False),
                lead.get("owner_responds", False), lead.get("newest_review", ""),
                lead.get("has_hours", False),
                lead.get("lead_score", 0), lead.get("score_reasons", ""),
                query, now, now,
            ))

    conn.commit()
    conn.close()
    log.info(f"Upserted {len(listings)} leads into database")


# ---------------------------------------------------------------------------
# Lead scoring
# ---------------------------------------------------------------------------

def score_lead(listing):
    """Score a listing's quality. Higher score = worse quality = better prospect.

    Returns (score, list_of_reasons).
    """
    score = 0
    reasons = []

    review_count = listing.get("review_count") or 0
    rating = listing.get("rating")
    photo_count = listing.get("photo_count") or 0
    has_desc = listing.get("has_description", False)
    has_svc = listing.get("has_services", False)
    owner_resp = listing.get("owner_responds", False)
    newest = listing.get("newest_review", "")
    website = listing.get("website", "")

    if review_count < 10:
        score += 3
        reasons.append("<10 reviews")

    if not owner_resp:
        score += 2
        reasons.append("no owner responses")

    if photo_count < 5:
        score += 2
        reasons.append("<5 photos")

    if rating is not None and rating < 4.0:
        score += 2
        reasons.append(f"rating {rating}")

    if not has_desc:
        score += 1
        reasons.append("no description")

    if not has_svc:
        score += 1
        reasons.append("no services listed")

    if _review_is_stale(newest):
        score += 2
        reasons.append("no recent reviews")

    if not website:
        score += 1
        reasons.append("no website")

    return score, reasons


def _review_is_stale(newest_review_text):
    """Return True if the newest review is 6+ months old or absent."""
    if not newest_review_text:
        return True
    text = newest_review_text.lower()
    # "a year ago", "2 years ago", etc.
    if "year" in text:
        return True
    # "N months ago" where N >= 6
    m = re.search(r'(\d+)\s*month', text)
    if m and int(m.group(1)) >= 6:
        return True
    return False


# ---------------------------------------------------------------------------
# Browser setup
# ---------------------------------------------------------------------------

def create_driver():
    """Create a headless Chromium driver with anti-detection flags."""
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    # Suppress logging noise
    opts.add_argument("--log-level=3")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])

    # Try common chromedriver locations
    for path in ["/usr/bin/chromedriver", "/usr/lib/chromium-browser/chromedriver",
                 "/snap/bin/chromium.chromedriver"]:
        if os.path.exists(path):
            service = Service(executable_path=path)
            return webdriver.Chrome(service=service, options=opts)

    # Fall back to letting Selenium find it
    return webdriver.Chrome(options=opts)


# ---------------------------------------------------------------------------
# Phase 1 — Collect listings from search results
# ---------------------------------------------------------------------------

def scroll_results_panel(driver, max_listings):
    """Scroll the Maps results panel to load more listings."""
    # The scrollable results feed — try multiple selectors
    feed = None
    selectors = [
        'div[role="feed"]',
        'div.m6QErb.DxyBCb.kA9KIf.dS8AEf',
        'div.m6QErb',
    ]
    for sel in selectors:
        try:
            feed = driver.find_element(By.CSS_SELECTOR, sel)
            if feed:
                break
        except NoSuchElementException:
            continue

    if not feed:
        log.warning("Could not find results feed panel to scroll")
        return

    last_count = 0
    stale_rounds = 0
    max_stale = 5

    while stale_rounds < max_stale:
        # Scroll down inside the feed
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
        time.sleep(1.5 + random.random())

        # Count how many listing links we have now
        links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/maps/place/"]')
        current_count = len(links)
        log.info(f"  Scrolled — {current_count} listings visible")

        if current_count >= max_listings:
            break
        if current_count == last_count:
            stale_rounds += 1
        else:
            stale_rounds = 0
        last_count = current_count


def extract_listings_from_search(driver, max_listings):
    """Extract listing cards from the search results page."""
    listings = []
    seen_names = set()

    # Find all listing anchor elements
    cards = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/maps/place/"]')
    log.info(f"Found {len(cards)} listing links on page")

    for card in cards:
        if len(listings) >= max_listings:
            break
        try:
            href = card.get_attribute("href") or ""
            aria = card.get_attribute("aria-label") or ""

            if not href or "/maps/place/" not in href:
                continue

            name = aria.strip()
            if not name:
                continue
            if name in seen_names:
                continue
            seen_names.add(name)

            # Try to get rating, review count, and category from nearby text
            # These are typically in the card's parent container
            parent = card
            try:
                parent = card.find_element(By.XPATH, "./..")
            except Exception:
                pass

            text_block = parent.text if parent else ""

            rating = extract_rating(text_block)
            review_count = extract_review_count(text_block)
            category = extract_category(text_block, name)

            listings.append({
                "name": name,
                "rating": rating,
                "review_count": review_count,
                "category": category,
                "maps_link": href,
                # Filled in Phase 2
                "address": "",
                "phone": "",
                "website": "",
                "photo_url": "",
                # Quality signals (Phase 2)
                "photo_count": 0,
                "has_description": False,
                "has_services": False,
                "owner_responds": False,
                "newest_review": "",
                "has_hours": False,
                # Scoring (set after Phase 2)
                "lead_score": 0,
                "score_reasons": "",
            })
            log.info(f"  [{len(listings)}] {name} ({rating}* / {review_count} reviews)")

        except StaleElementReferenceException:
            continue
        except Exception as e:
            log.debug(f"  Skipping card: {e}")
            continue

    return listings


def extract_rating(text):
    """Pull a rating like '4.5' from text."""
    m = re.search(r'\b([1-5](?:\.\d)?)\b', text)
    if m:
        val = float(m.group(1))
        if 1.0 <= val <= 5.0:
            return val
    return None


def extract_review_count(text):
    """Pull a review count like '(123)' or '123 reviews' from text."""
    # Match patterns like (123), (1,234), (1.2K)
    m = re.search(r'\(([0-9,]+)\)', text)
    if m:
        return int(m.group(1).replace(",", ""))
    m = re.search(r'(\d[\d,]*)\s*review', text, re.IGNORECASE)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def extract_category(text, name):
    """Try to extract the business category from the text block."""
    lines = text.split("\n")
    # Category is often the line right after rating info
    for i, line in enumerate(lines):
        line = line.strip()
        # Skip the name, rating lines, price indicators
        if line == name or not line:
            continue
        if re.match(r'^[0-9(.$]', line):
            continue
        if "review" in line.lower():
            continue
        # A line that looks like a category (short, no digits at start)
        if len(line) < 60 and not line.startswith("Open") and not line.startswith("Closed"):
            return line
    return ""


# ---------------------------------------------------------------------------
# Phase 2 — Get details for each listing
# ---------------------------------------------------------------------------

def scrape_listing_detail(driver, listing):
    """Open a listing's Maps page and extract detail info."""
    url = listing["maps_link"]
    driver.get(url)

    # Wait for the detail panel to load
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="main"]'))
        )
    except TimeoutException:
        log.warning(f"  Timeout loading detail page for: {listing['name']}")
        return

    # Give extra time for dynamic content
    time.sleep(1.5)

    # --- Phone ---
    listing["phone"] = extract_detail_field(
        driver,
        selectors=[
            'button[data-tooltip="Copy phone number"]',
            'button[aria-label*="Phone"]',
            'button[data-item-id*="phone"]',
            'a[href^="tel:"]',
        ],
        attr_patterns=["aria-label", "href", "data-item-id"],
        text_pattern=r'[\(\d][\d\s\-\(\)]{6,}',
    )

    # --- Website ---
    listing["website"] = extract_detail_field(
        driver,
        selectors=[
            'a[data-tooltip="Open website"]',
            'a[data-item-id="authority"]',
            'a[aria-label*="Website"]',
            'a[aria-label*="website"]',
        ],
        attr_patterns=["href"],
        href_filter=True,
    )

    # --- Address ---
    listing["address"] = extract_detail_field(
        driver,
        selectors=[
            'button[data-tooltip="Copy address"]',
            'button[data-item-id*="address"]',
            'button[aria-label*="Address"]',
        ],
        attr_patterns=["aria-label"],
        text_pattern=r'\d+.*(?:St|Ave|Rd|Blvd|Dr|Ln|Way|Ct|Pl|Hwy|Pike|Pkwy|Route)',
    )

    # --- Photo URL ---
    try:
        photo_el = driver.find_element(
            By.CSS_SELECTOR, 'button[jsaction*="photo"] img, div.RZ66Rb img, img.p0Hhde'
        )
        src = photo_el.get_attribute("src") or ""
        if src and "googleusercontent" in src:
            listing["photo_url"] = src
    except (NoSuchElementException, Exception):
        pass

    # --- Quality Signals ---
    _extract_quality_signals(driver, listing)


def _extract_quality_signals(driver, listing):
    """Extract quality signals from the currently loaded detail page."""
    page_text = ""
    try:
        main_el = driver.find_element(By.CSS_SELECTOR, 'div[role="main"]')
        page_text = main_el.text
    except Exception:
        pass

    # Photo count — look for "Photos" button with count in aria-label
    listing["photo_count"] = 0
    try:
        photo_btns = driver.find_elements(
            By.CSS_SELECTOR,
            'button[aria-label*="photo" i], button[aria-label*="Photo" i]'
        )
        for btn in photo_btns:
            aria = btn.get_attribute("aria-label") or ""
            m = re.search(r'(\d[\d,]*)\s*photo', aria, re.IGNORECASE)
            if m:
                listing["photo_count"] = int(m.group(1).replace(",", ""))
                break
        # Fallback: count thumbnail images in photo area
        if listing["photo_count"] == 0:
            thumbs = driver.find_elements(By.CSS_SELECTOR, 'button[jsaction*="photo"]')
            if thumbs:
                listing["photo_count"] = len(thumbs)
    except Exception:
        pass

    # Has description — About / description section
    listing["has_description"] = False
    try:
        desc_selectors = [
            'div[aria-label*="About"]',
            'div.PYvSYb',   # description block
            'span[jsan*="description"]',
        ]
        for sel in desc_selectors:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if els:
                listing["has_description"] = True
                break
        # Also check page text for "About" section markers
        if not listing["has_description"] and re.search(r'\bAbout\b.*\bFrom the business\b', page_text, re.S):
            listing["has_description"] = True
    except Exception:
        pass

    # Has services section
    listing["has_services"] = False
    try:
        svc_els = driver.find_elements(By.CSS_SELECTOR, 'div[aria-label*="Services"]')
        if svc_els:
            listing["has_services"] = True
        elif "Services" in page_text and re.search(r'\bService\w*\b.*\$', page_text):
            listing["has_services"] = True
    except Exception:
        pass

    # Owner responds to reviews
    listing["owner_responds"] = False
    try:
        resp_els = driver.find_elements(By.XPATH,
            '//*[contains(text(),"Response from the owner") or contains(text(),"Response from")]'
        )
        if resp_els:
            listing["owner_responds"] = True
    except Exception:
        pass

    # Newest review date
    listing["newest_review"] = ""
    try:
        review_dates = driver.find_elements(By.CSS_SELECTOR, 'span.rsqaWe')
        if review_dates:
            listing["newest_review"] = review_dates[0].text.strip()
        else:
            # Fallback: look for "X ago" patterns in review area
            m = re.search(r'(\d+\s+(?:day|week|month|year)s?\s+ago|a\s+(?:day|week|month|year)\s+ago)', page_text)
            if m:
                listing["newest_review"] = m.group(0)
    except Exception:
        pass

    # Has hours
    listing["has_hours"] = False
    try:
        hours_els = driver.find_elements(By.CSS_SELECTOR,
            'div[aria-label*="Hours"], button[data-item-id*="oh"], table.eK4R0e'
        )
        if hours_els:
            listing["has_hours"] = True
        elif re.search(r'(Open 24 hours|Opens|Closed|Hours)', page_text):
            listing["has_hours"] = True
    except Exception:
        pass


def extract_detail_field(driver, selectors, attr_patterns=None, text_pattern=None, href_filter=False):
    """Try multiple CSS selectors to extract a detail field value."""
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
        except NoSuchElementException:
            continue

        # For website links, grab the href directly
        if href_filter:
            href = el.get_attribute("href") or ""
            if href and href.startswith("http") and "google" not in href:
                return href
            # Sometimes the aria-label has the URL
            aria = el.get_attribute("aria-label") or ""
            if aria and "." in aria and " " not in aria.strip():
                url = aria.strip()
                if not url.startswith("http"):
                    url = "https://" + url
                return url
            continue

        # Try aria-label and other attributes
        if attr_patterns:
            for attr in attr_patterns:
                val = el.get_attribute(attr) or ""
                if val:
                    if attr == "href" and val.startswith("tel:"):
                        return val.replace("tel:", "").strip()
                    if text_pattern:
                        m = re.search(text_pattern, val)
                        if m:
                            return m.group(0).strip()
                    elif val:
                        # Clean up aria-label text like "Address: 123 Main St"
                        cleaned = re.sub(r'^[^:]+:\s*', '', val).strip()
                        if cleaned:
                            return cleaned

        # Fall back to element text
        text = el.text.strip()
        if text:
            if text_pattern:
                m = re.search(text_pattern, text)
                if m:
                    return m.group(0).strip()
            else:
                return text

    return ""


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_outputs(listings, query, output_dir="output"):
    """Save listings to JSON and Excel files."""
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r'[^a-z0-9]+', '_', query.lower()).strip('_')
    base = f"{slug}_{timestamp}"

    json_path = os.path.join(output_dir, f"{base}.json")
    xlsx_path = os.path.join(output_dir, f"{base}.xlsx")

    # JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(listings, f, indent=2, ensure_ascii=False)
    log.info(f"JSON saved: {json_path}")

    # Excel
    df = pd.DataFrame(listings)
    # Reorder columns — scoring first, then contact info, then signals
    col_order = [
        "lead_score", "score_reasons",
        "name", "address", "phone", "website",
        "rating", "review_count", "category",
        "photo_count", "has_description", "has_services",
        "owner_responds", "newest_review", "has_hours",
        "maps_link", "photo_url",
    ]
    for c in col_order:
        if c not in df.columns:
            df[c] = ""
    df = df[col_order]
    df.to_excel(xlsx_path, index=False, engine="openpyxl")
    log.info(f"Excel saved: {xlsx_path}")

    return json_path, xlsx_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Google Maps listings for a search query."
    )
    parser.add_argument("query", help='Search query, e.g. "plumbers east brunswick nj"')
    parser.add_argument("--max", type=int, default=20, dest="max_listings",
                        help="Maximum number of listings to scrape (default: 20)")
    parser.add_argument("--min-score", type=int, default=5,
                        help="Minimum lead score to include in output (default: 5)")
    parser.add_argument("--all", action="store_true",
                        help="Output all listings with scores (no filtering)")
    args = parser.parse_args()

    query = args.query
    max_listings = args.max_listings
    min_score = args.min_score
    show_all = args.all

    log.info(f"Query: {query}")
    log.info(f"Max listings: {max_listings}")

    # Build the search URL (force English with hl=en)
    search_url = f"https://www.google.com/maps/search/{quote_plus(query)}?hl=en"

    driver = create_driver()
    try:
        # ── Phase 1: Collect listings from search results ──
        log.info("Phase 1: Loading search results...")
        driver.get(search_url)

        # Handle consent / cookie dialogs (multiple languages)
        try:
            consent_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH,
                    '//button['
                    'contains(text(),"Accept all") or '
                    'contains(text(),"Reject all") or '
                    'contains(text(),"Accept") or '
                    'contains(text(),"Alles accepteren") or '
                    'contains(text(),"Alles afwijzen") or '
                    'contains(text(),"Tout accepter") or '
                    'contains(text(),"Alle akzeptieren") or '
                    'contains(text(),"Aceptar todo")'
                    ']'))
            )
            consent_btn.click()
            log.info("Dismissed consent dialog")
            time.sleep(2)
        except TimeoutException:
            pass  # No consent dialog

        # Also try form-based consent (some regions use a form)
        try:
            form_btns = driver.find_elements(By.CSS_SELECTOR,
                'form[action*="consent"] button, '
                'div[role="dialog"] button, '
                'div[jsname] button[jsname]'
            )
            for btn in form_btns:
                txt = btn.text.lower()
                if any(w in txt for w in ["accept", "accepter", "akzeptieren", "aceptar", "accepteren"]):
                    btn.click()
                    log.info("Dismissed consent dialog (form)")
                    time.sleep(2)
                    break
        except Exception:
            pass

        # Wait for results to load
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/maps/place/"]'))
            )
        except TimeoutException:
            log.error("No search results loaded. Google may be blocking or the query returned no results.")
            driver.save_screenshot("/tmp/scraper_debug.png")
            log.error("Screenshot saved to /tmp/scraper_debug.png for debugging")
            sys.exit(1)

        time.sleep(2)

        # Scroll to load more results
        log.info("Scrolling to load more listings...")
        scroll_results_panel(driver, max_listings)

        # Extract listing data from search cards
        listings = extract_listings_from_search(driver, max_listings)
        log.info(f"Phase 1 complete: {len(listings)} listings collected")

        if not listings:
            log.error("No listings found. Exiting.")
            sys.exit(1)

        # ── Phase 2: Get details for each listing ──
        log.info("Phase 2: Scraping detail pages...")
        for i, listing in enumerate(listings):
            log.info(f"  [{i+1}/{len(listings)}] {listing['name']}")
            try:
                scrape_listing_detail(driver, listing)
            except Exception as e:
                log.warning(f"  Failed to get details: {e}")

            # Polite delay between requests
            delay = 2 + random.random() * 1.5
            time.sleep(delay)

        log.info("Phase 2 complete")

        # ── Phase 3: Score leads ──
        log.info("Phase 3: Scoring leads...")
        for listing in listings:
            score, reasons = score_lead(listing)
            listing["lead_score"] = score
            listing["score_reasons"] = ", ".join(reasons)

        # Sort by score descending (worst quality = best prospect first)
        listings.sort(key=lambda x: x["lead_score"], reverse=True)

        # ── Save to database ──
        init_db()
        upsert_leads(listings, query)

        # ── Filter for output ──
        if show_all:
            output_listings = listings
        else:
            output_listings = [l for l in listings if l["lead_score"] >= min_score]

        high_priority = len([l for l in listings if l["lead_score"] >= min_score])

        # ── Save filtered output to JSON / Excel ──
        output_dir = os.path.join(SCRIPT_DIR, "output")
        json_path, xlsx_path = save_outputs(output_listings, query, output_dir)

        # ── Print summary ──
        print(f"\n{'='*60}")
        print(f"  {high_priority} high-priority leads out of {len(listings)} total (saved to DB)")
        print(f"  Query: {query}")
        print(f"  JSON:  {json_path}")
        print(f"  Excel: {xlsx_path}")
        print(f"  DB:    {DB_PATH}")
        print(f"{'='*60}\n")

        for l in output_listings:
            phone = l.get("phone", "—") or "—"
            website = l.get("website", "—") or "—"
            if len(website) > 30:
                website = website[:30] + "..."
            reasons = l.get("score_reasons", "")
            print(f"  [SCORE {l['lead_score']:>2}] {l['name'][:35]:<35} | {phone:<16} | {website}")
            if reasons:
                print(f"           → {reasons}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
