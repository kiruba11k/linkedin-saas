import re
import json

def clean_html(html):
    return re.sub(r'<[^>]+>', ' ', html)

def extract_json(html):
    matches = re.findall(
        r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
        html,
        re.DOTALL
    )
    for m in matches:
        try:
            return json.loads(m)
        except:
            continue
    return {}

def regex_find(text, pattern):
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0) if match else None

def extract_company(html, url):

    text = clean_html(html)
    json_data = extract_json(html)

    employee = regex_find(text, r"\d{1,3}(,\d{3})*(\+)?\s*employees")
    founded = regex_find(text, r"(19|20)\d{2}")
    location = regex_find(text, r"[A-Za-z\s]+,\s?[A-Za-z\s]+")

    return {
        "companyName": json_data.get("name") or regex_find(text, r"[A-Z][A-Za-z0-9 &\-]{2,}"),
        "industry": regex_find(text, r"(Software|Technology|AI|Finance|Consulting|Internet|IT)"),
        "employeeCountRange": employee,
        "employeeDisplayCount": employee,
        "linkedinCompanyUrl": url,
        "foundedYear": json_data.get("foundingDate") or founded,
        "headquarters": location
    }
