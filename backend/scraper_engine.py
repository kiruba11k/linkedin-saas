import re
import json

def extract_by_label(page, labels):
    elements = page.query_selector_all("div, span, li")

    for el in elements:
        try:
            text = el.inner_text().lower()
            for label in labels:
                if label in text:
                    return el.inner_text().strip()
        except:
            continue
    return None


def extract_json(page):
    scripts = page.query_selector_all("script")
    for s in scripts:
        try:
            data = json.loads(s.inner_text())
            if isinstance(data, dict):
                return data
        except:
            continue
    return None


def extract_employee(text):
    if not text:
        return None
    match = re.search(r"\d+[,-]?\d*\+?\s*employees", text.lower())
    return match.group(0) if match else text


def extract_year(text):
    if not text:
        return None
    match = re.search(r"(19|20)\d{2}", text)
    return match.group(0) if match else None


def smart_extract(page, field):

    content = page.content()

    strategies = {
        "industry": [
            lambda: extract_by_label(page, ["industry"]),
        ],

        "employees": [
            lambda: extract_employee(extract_by_label(page, ["employees"])),
        ],

        "founded": [
            lambda: extract_year(extract_by_label(page, ["founded"])),
            lambda: extract_year(content)
        ],

        "location": [
            lambda: extract_by_label(page, ["headquarters", "location"]),
        ]
    }

    for fn in strategies.get(field, []):
        try:
            res = fn()
            if res:
                return res
        except:
            continue

    return None


def extract_company(page):

    return {
        "companyName": page.query_selector("h1").inner_text(),

        "industry": smart_extract(page, "industry"),
        "employeeCountRange": smart_extract(page, "employees"),
        "employeeDisplayCount": smart_extract(page, "employees"),
        "foundedYear": smart_extract(page, "founded"),
        "headquarters": smart_extract(page, "location")
    }
