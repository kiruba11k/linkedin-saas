import json
import re


def clean_html(html):
    return re.sub(r"<[^>]+>", " ", html)


def extract_json_ld(html):
    matches = re.findall(
        r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>",
        html,
        re.DOTALL | re.IGNORECASE,
    )

    objects = []
    for match in matches:
        try:
            parsed = json.loads(match)
        except Exception:
            continue

        if isinstance(parsed, list):
            objects.extend([item for item in parsed if isinstance(item, dict)])
        elif isinstance(parsed, dict):
            objects.append(parsed)

    return objects


def extract_meta_content(html, prop_names):
    for prop in prop_names:
        pattern = rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']'
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def regex_find(text, pattern):
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0).strip() if match else None


def pick_company_entity(json_objects):
    for obj in json_objects:
        entity_type = str(obj.get("@type", "")).lower()
        if "organization" in entity_type or "corporation" in entity_type:
            return obj
    return json_objects[0] if json_objects else {}


def extract_company(html, url):

    text = clean_html(html)
    json_ld_objects = extract_json_ld(html)
    entity = pick_company_entity(json_ld_objects)

    # Multi-layer extraction like production scrapers:
    # 1) JSON-LD entity, 2) metadata tags, 3) regex fallback.
    company_name = (
        entity.get("name")
        or extract_meta_content(html, ["og:title", "twitter:title"])
        or regex_find(text, r"\b[A-Z][A-Za-z0-9&\- ]{2,}\b")
    )

    industry = (
        entity.get("industry")
        or extract_meta_content(html, ["og:description", "description"])
        or regex_find(
            text,
            r"(Software|Technology|AI|Finance|Consulting|Internet|IT Services|Marketing|Healthcare)",
        )
    )

    employee = (
        regex_find(text, r"\d{1,3}(?:,\d{3})*(?:\+)?\s*employees")
        or regex_find(text, r"\d{1,3}(?:-\d{1,3})?\s*employees")
    )

    founded = (
        entity.get("foundingDate")
        or regex_find(text, r"(?:Founded\s*)?(19|20)\d{2}")
    )

    headquarters = (
        entity.get("address", {}).get("addressLocality")
        if isinstance(entity.get("address"), dict)
        else None
    ) or regex_find(text, r"\b[A-Z][A-Za-z ]+,\s*[A-Z][A-Za-z ]+\b")

    return {
        "companyName": company_name,
        "industry": industry,
        "employeeCountRange": employee,
        "employeeDisplayCount": employee,
        "linkedinCompanyUrl": url,
        "foundedYear": founded,
        "headquarters": headquarters,
    }
