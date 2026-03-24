from concurrent.futures import ThreadPoolExecutor
import os
import random
import time

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
def human_delay():
    time.sleep(random.uniform(2, 5))


def human_scroll(page):
    page.mouse.wheel(0, random.randint(1000, 3000))
    time.sleep(random.uniform(1, 3))


# -----------------------
# SCRAPE ONE COMPANY
# -----------------------
def scrape_single(browser, url):
    try:
        page = browser.new_page()
        apply_stealth(page)

        page.goto(url, timeout=60000)
        page.wait_for_load_state("networkidle")

        human_scroll(page)
        human_delay()

        html = page.content()
        data = extract_company(html, url)

        page.close()
        return data

    except Exception as e:
        print("ERROR:", e)
        return None


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

            browser = p.chromium.launch_persistent_context(
                "./session",
                headless=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true",
                args=["--disable-blink-features=AutomationControlled"],
            )

            page = browser.new_page()
            apply_stealth(page)

            page.goto(sales_nav_url, timeout=60000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5000)

            human_scroll(page)

            cards = page.query_selector_all("li")

            urls = []
            for card in cards[:10]:
                try:
                    link = card.query_selector("a")
                    if link:
                        href = link.get_attribute("href")
                        if href and "linkedin.com" in href:
                            urls.append(href)
                except Exception:
                    continue

            # Deduplicate while preserving order.
            urls = list(dict.fromkeys(urls))

            print("TOTAL URLS:", len(urls))

            # 🔥 PARALLEL SCRAPING
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(scrape_single, browser, url) for url in urls]

                for future in futures:
                    result = future.result()
                    if result:
                        db.add(Company(job_id=job_id, **result))
                        db.commit()

            browser.close()

        job.status = "completed"
        db.commit()
    except Exception as e:
        print("SCRAPER JOB FAILED:", e)
        job.status = "failed"
        db.commit()
    finally:
        db.close()
