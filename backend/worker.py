from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import random
import re
import time
from urllib.parse import urljoin, urlparse, parse_qs, unquote

from playwright.sync_api import sync_playwright

from database import SessionLocal
from extractor import extract_company
from models import Company, Job

try:
    # Newer playwright-stealth versions expose a Stealth class.
    from playwright_stealth import Stealth

    _stealth = Stealth()

    def apply_stealth(page):
        _stealth.apply_stealth_sync(page)
except ImportError:
    # Backward compatibility with older releases.
    from playwright_stealth import stealth_sync

    def apply_stealth(page):
        stealth_sync(page)


# -----------------------
# HUMAN BEHAVIOR
# -----------------------
def human_delay(min_seconds=1.5, max_seconds=4.0):
    time.sleep(random.uniform(min_seconds, max_seconds))


def human_scroll(page, loops=1):
    for _ in range(loops):
        page.mouse.wheel(0, random.randint(800, 2400))
        time.sleep(random.uniform(0.8, 2.2))


def normalize_linkedin_company_url(raw_url: str):
    if not raw_url:
        return None

    candidate = raw_url.strip()
    if candidate.startswith("/"):
        candidate = urljoin("https://www.linkedin.com", candidate)

    parsed = urlparse(candidate)

    # Sales Navigator often embeds the real link in query params.
    if "linkedin.com" in parsed.netloc:
        params = parse_qs(parsed.query)
        for key in ("url", "redirect", "dest", "destination"):
            embedded = params.get(key, [None])[0]
            if embedded and "linkedin.com/company/" in embedded:
                candidate = unquote(embedded)
                parsed = urlparse(candidate)
                break

    if "linkedin.com/company/" not in candidate:
        return None

    normalized = f"https://{parsed.netloc}{parsed.path}".rstrip("/")
    return normalized


def collect_company_urls(page, max_results=25):
    # Layer 1: DOM anchors that point directly to company pages.
    selectors = [
        'a[href*="linkedin.com/company/"]',
        'a[href*="/company/"]',
        'a[data-test-app-aware-link][href*="company"]',
    ]

    urls = []

    for selector in selectors:
        for anchor in page.query_selector_all(selector):
            try:
                href = anchor.get_attribute("href")
            except Exception:
                continue

            normalized = normalize_linkedin_company_url(href)
            if normalized:
                urls.append(normalized)

    # Layer 2: regex fallback directly from raw HTML for dynamic/virtualized lists.
    if len(urls) < 3:
        html = page.content()
        pattern = r"https?://(?:[\w.-]+\.)?linkedin\.com/company/[A-Za-z0-9\-_%]+/?"
        for match in re.findall(pattern, html):
            normalized = normalize_linkedin_company_url(match)
            if normalized:
                urls.append(normalized)

    # Layer 3: try loading more cards before final dedupe.
    if len(urls) < max_results:
        for _ in range(3):
            human_scroll(page, loops=1)
            human_delay(0.8, 1.6)
            for anchor in page.query_selector_all('a[href*="linkedin.com/company/"], a[href*="/company/"]'):
                try:
                    href = anchor.get_attribute("href")
                except Exception:
                    continue
                normalized = normalize_linkedin_company_url(href)
                if normalized:
                    urls.append(normalized)
            if len(urls) >= max_results:
                break

    # Deduplicate while preserving order.
    deduped = list(dict.fromkeys(urls))
    return deduped[:max_results]


# -----------------------
# SCRAPE ONE COMPANY
# -----------------------
def scrape_single(context, url):
    page = None
    try:
        page = context.new_page()
        apply_stealth(page)

        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        human_scroll(page, loops=2)
        human_delay()

        html = page.content()
        data = extract_company(html, url)

        # Safety net: keep only non-empty company records.
        if not data.get("companyName") and not data.get("industry"):
            return None

        return data

    except Exception as e:
        print(f"ERROR scraping {url}: {e}")
        return None
    finally:
        if page:
            page.close()


# -----------------------
# MAIN WORKER
# -----------------------
def run_scraper(job_id, sales_nav_url):

    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    job.status = "running"
    db.commit()

    try:
        with sync_playwright() as p:

            context = p.chromium.launch_persistent_context(
                "./session",
                headless=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true",
                args=["--disable-blink-features=AutomationControlled"],
            )

            page = context.new_page()
            apply_stealth(page)

            page.goto(sales_nav_url, timeout=90000, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5000)

            human_scroll(page, loops=2)

            urls = collect_company_urls(page, max_results=25)
            print("TOTAL COMPANY URLS:", len(urls))

            if not urls:
                # Explicitly finish when no rows are discoverable instead of silently creating empty CSV.
                print("No company URLs found on the Sales Navigator page.")

            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(scrape_single, context, url) for url in urls]

                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        db.add(Company(job_id=job_id, **result))
                        db.commit()

            context.close()

        job.status = "completed"
        db.commit()
    except Exception as e:
        print("SCRAPER JOB FAILED:", e)
        job.status = "failed"
        db.commit()
    finally:
        db.close()
