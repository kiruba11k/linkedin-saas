import json
import os
import re
from urllib import error, request


GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "15"))


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


def _clean_company_field(value):
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return None

    cleaned = str(value).strip()
    if not cleaned:
        return None

    lowered = cleaned.lower()
    if lowered in {"unknown", "n/a", "na", "none", "null", "not found"}:
        return None

    return cleaned


def _build_groq_prompt(html, url):
    trimmed_html = html[:100000]
    return f"""
Extract company details from this LinkedIn company page HTML.
Return ONLY valid JSON with these exact keys:
companyName, industry, employeeCountRange, employeeDisplayCount, linkedinCompanyUrl, foundedYear, headquarters

Rules:
- Use null for unknown values.
- foundedYear must be just a 4-digit year when possible.
- employeeDisplayCount can equal employeeCountRange.
- linkedinCompanyUrl should be this URL: {url}
- Never return markdown, code fences, or extra text.

HTML:
{trimmed_html}
""".strip()


def _extract_json_from_llm_response(raw_response):
    if not raw_response:
        return {}

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_response, re.DOTALL)
    if fenced:
        raw_response = fenced.group(1)

    obj_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
    candidate = obj_match.group(0) if obj_match else raw_response

    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def extract_company_with_groq(html, url):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {}

    payload = {
        "model": GROQ_MODEL,
        "temperature": 0,
        "max_tokens": 350,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": _build_groq_prompt(html, url),
            }
        ],
    }

    req = request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=GROQ_TIMEOUT_SECONDS) as response:
            raw_body = response.read().decode("utf-8")
    except (error.HTTPError, error.URLError, TimeoutError):
        return {}

    try:
        body = json.loads(raw_body)
        message = body["choices"][0]["message"]["content"]
    except Exception:
        return {}

    extracted = _extract_json_from_llm_response(message)
    cleaned = {
        "companyName": _clean_company_field(extracted.get("companyName")),
        "industry": _clean_company_field(extracted.get("industry")),
        "employeeCountRange": _clean_company_field(extracted.get("employeeCountRange")),
        "employeeDisplayCount": _clean_company_field(extracted.get("employeeDisplayCount")),
        "linkedinCompanyUrl": url,
        "foundedYear": _clean_company_field(extracted.get("foundedYear")),
        "headquarters": _clean_company_field(extracted.get("headquarters")),
    }

    if not cleaned["employeeDisplayCount"] and cleaned["employeeCountRange"]:
        cleaned["employeeDisplayCount"] = cleaned["employeeCountRange"]

    return cleaned


def should_use_groq(base_data):
    required_for_quality = [
        base_data.get("companyName"),
        base_data.get("industry"),
        base_data.get("headquarters"),
    ]

    missing_count = sum(1 for item in required_for_quality if not item)
    return missing_count >= 2


def merge_company_data(base_data, llm_data):
    if not llm_data:
        return base_data

    merged = dict(base_data)
    for key in merged:
        if not merged.get(key):
            merged[key] = llm_data.get(key)

    if not merged.get("employeeDisplayCount") and merged.get("employeeCountRange"):
        merged["employeeDisplayCount"] = merged["employeeCountRange"]

    return merged


def extract_company(html, url):

    text = clean_html(html)
    json_ld_objects = extract_json_ld(html)
    entity = pick_company_entity(json_ld_objects)

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

    base_data = {
        "companyName": _clean_company_field(company_name),
        "industry": _clean_company_field(industry),
        "employeeCountRange": _clean_company_field(employee),
        "employeeDisplayCount": _clean_company_field(employee),
        "linkedinCompanyUrl": url,
        "foundedYear": _clean_company_field(founded),
        "headquarters": _clean_company_field(headquarters),
    }

    if should_use_groq(base_data):
        llm_data = extract_company_with_groq(html, url)
        return merge_company_data(base_data, llm_data)

    return base_data
