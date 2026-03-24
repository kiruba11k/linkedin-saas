from playwright.sync_api import sync_playwright
from database import SessionLocal
from models import Company, Job
from scraper_engine import extract_company
import time, random


def human_delay():
    time.sleep(random.uniform(2, 4))


def run_scraper(job_id, sales_nav_url):

    db = SessionLocal()

    job = db.query(Job).filter(Job.id == job_id).first()
    job.status = "running"
    db.commit()

    with sync_playwright() as p:

        browser = p.chromium.launch_persistent_context(
            "./session",
            headless=True
        )

        page = browser.new_page()
        page.goto(sales_nav_url)
        time.sleep(5)

        for _ in range(3):

            cards = page.query_selector_all("li")

            for card in cards[:5]:

                try:
                    text = card.inner_text().lower()

                    if "employees" not in text:
                        continue

                    link_el = card.query_selector("a")
                    if not link_el:
                        continue

                    link = link_el.get_attribute("href")

                    detail = browser.new_page()
                    detail.goto(link)
                    time.sleep(4)

                    data = extract_company(detail)

                    company = Company(
                        job_id=job_id,
                        linkedinCompanyUrl=link,
                        **data
                    )

                    db.add(company)
                    db.commit()

                    detail.close()
                    human_delay()

                except:
                    continue

            try:
                page.click('button[aria-label="Next"]')
                time.sleep(5)
            except:
                break

        browser.close()

    job.status = "completed"
    db.commit()
    db.close()
