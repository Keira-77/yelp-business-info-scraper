thonimport logging
import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

def fetch_html(
    url: str,
    session: Optional[requests.Session],
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 15,
) -> Tuple[Optional[str], int]:
    if session is None:
        session = requests.Session()

    try:
        response = session.get(url, headers=headers or {}, timeout=timeout)
        logging.debug("Fetched %s with status %s", url, response.status_code)
        return response.text, response.status_code
    except requests.RequestException as exc:
        logging.error("Request error for %s: %s", url, exc)
        return None, 0

def detect_page_not_found(html: Optional[str], status_code: int) -> bool:
    if status_code == 404:
        return True
    if html is None:
        return True

    lowered = html.lower()
    not_found_signals = [
        "page not found",
        "we looked everywhere",
        "404 error",
        "sorry, we couldn't find",
    ]
    return any(sig in lowered for sig in not_found_signals)

def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.string:
        # Often "Business Name - City, State - Yelp"
        return soup.title.string.split("- Yelp")[0].strip()
    return None

def _extract_rating(soup: BeautifulSoup) -> Optional[str]:
    # Look for an element with aria-label containing "star rating"
    rating_el = soup.find(attrs={"aria-label": re.compile(r"star rating", re.I)})
    if rating_el:
        label = rating_el.get("aria-label") or rating_el.get_text()
        match = re.search(r"([0-9.]+)", label)
        if match:
            return match.group(1)

    # Try meta tags with rating
    meta = soup.find("meta", attrs={"itemprop": "ratingValue"})
    if meta and meta.get("content"):
        return meta["content"].strip()

    return None

def _extract_review_count(soup: BeautifulSoup) -> Optional[str]:
    # Yelp often uses text like "844 reviews"
    pattern = re.compile(r"([0-9,]+)\s+reviews?", re.I)
    text = soup.get_text(" ", strip=True)
    match = pattern.search(text)
    if match:
        return f"{match.group(1)} reviews"
    return None

def _extract_is_claimed(soup: BeautifulSoup) -> Optional[str]:
    text = soup.get_text(" ", strip=True).lower()
    if "claimed" in text:
        return "Claimed"
    if "unclaimed" in text:
        return "Unclaimed"
    return None

def _extract_price_level(soup: BeautifulSoup) -> Optional[str]:
    # Look for a small group of dollar signs like "$$"
    pattern = re.compile(r"\${1,4}")
    text = soup.get_text(" ", strip=True)
    match = pattern.search(text)
    if match:
        return match.group(0)
    return None

def _extract_categories(soup: BeautifulSoup) -> List[str]:
    categories: List[str] = []

    # Yelp typically uses anchor tags near the header; grab a small set of category-like anchors
    for a in soup.find_all("a", href=True):
        href = a["href"]
        label = a.get_text(strip=True)
        if not label:
            continue
        # Heuristic: Yelp category links often contain "/c/" or "/search?cflt="
        if "/c/" in href or "cflt=" in href:
            if label not in categories:
                categories.append(label)

    return categories

def _extract_address_block(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    address_text = None

    # Try <address> tag first
    address_tag = soup.find("address")
    if address_tag:
        address_text = address_tag.get_text(" ", strip=True)

    # Fallback: look for an element with "address" in aria-label or similar
    if not address_text:
        candidate = soup.find(attrs={"aria-label": re.compile("address", re.I)})
        if candidate:
            address_text = candidate.get_text(" ", strip=True)

    if not address_text:
        return {
            "fullAddress": None,
            "city": None,
            "state": None,
            "zipcode": None,
        }

    # Try to split city, state, zip from the end of the string
    # Example: "3600 Kirby Dr Ste D Houston, TX 77098"
    city = state = zipcode = None
    full_address = address_text

    match = re.search(
        r"(?P<city>[^,]+),\s*(?P<state>[A-Z]{2})\s+(?P<zip>[0-9]{5}(?:-[0-9]{4})?)$",
        address_text,
    )
    if match:
        city = match.group("city").strip()
        state = match.group("state").strip()
        zipcode = match.group("zip").strip()

    return {
        "fullAddress": full_address,
        "city": city,
        "state": state,
        "zipcode": zipcode,
    }

def _extract_phone_number(soup: BeautifulSoup) -> Optional[str]:
    text = soup.get_text(" ", strip=True)
    # Basic US phone pattern
    match = re.search(
        r"(\(\d{3}\)\s*\d{3}[-\s]?\d{4})",
        text,
    )
    if match:
        return match.group(1)
    return None

def _extract_images(soup: BeautifulSoup, max_images: int = 10) -> List[str]:
    urls: List[str] = []
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if "yelp" in src and "photo" in src:
            if src not in urls:
                urls.append(src)
        if len(urls) >= max_images:
            break
    return urls

def _extract_website(soup: BeautifulSoup) -> Optional[str]:
    for a in soup.find_all("a", href=True):
        href = a["href"]
        label = a.get_text(" ", strip=True).lower()
        if "business website" in label or "website" in label:
            # Some Yelp links redirect through /biz_redir; keep the original href
            return href
    return None

def _extract_hours(soup: BeautifulSoup) -> Dict[str, str]:
    hours: Dict[str, str] = {}
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # Look for a table with hours info
    table = None
    for candidate in soup.find_all("table"):
        if "hours" in candidate.get_text(" ", strip=True).lower():
            table = candidate
            break

    if not table:
        return hours

    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        day_text = cells[0].get_text(" ", strip=True)
        value_text = cells[1].get_text(" ", strip=True)
        for d in days:
            if day_text.startswith(d):
                hours[d] = value_text
                break

    return hours

def _extract_owner_name(soup: BeautifulSoup) -> Optional[str]:
    text = soup.get_text(" ", strip=True)
    # Heuristic: look for "Business owner:" or similar pattern
    match = re.search(r"Business owner:\s*([A-Z][\w\s\.\-]+)", text)
    if match:
        return match.group(1).strip()
    return None

def _extract_about(soup: BeautifulSoup) -> Optional[str]:
    # Look for sections with "About the Business" style headings
    headings = soup.find_all(["h2", "h3"])
    for h in headings:
        if "about the business" in h.get_text(" ", strip=True).lower():
            # Take the following sibling paragraph(s)
            about_parts: List[str] = []
            sib = h.find_next_sibling()
            while sib and sib.name in {"p", "div"}:
                text = sib.get_text(" ", strip=True)
                if text:
                    about_parts.append(text)
                sib = sib.find_next_sibling()
            if about_parts:
                return " ".join(about_parts)
    return None

def _extract_review_highlights(soup: BeautifulSoup, max_reviews: int = 5) -> List[str]:
    highlights: List[str] = []

    # Try to find blockquotes or emphasized review snippets
    for el in soup.find_all(["q", "blockquote", "p"]):
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        # Simple heuristic to filter out very short or obviously non-review text
        if len(text) < 40:
            continue
        if "review of" in text.lower():
            continue
        highlights.append(f"“{text}”")
        if len(highlights) >= max_reviews:
            break

    return highlights

def _extract_business_services(soup: BeautifulSoup) -> Dict[str, bool]:
    services: Dict[str, bool] = {}

    # Yelp typically lists amenities as checkmarked items
    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)
        if not text:
            continue
        lowered = text.lower()
        if any(keyword in lowered for keyword in ["delivery", "takeout", "take-out", "curbside"]):
            services["Offers Delivery"] = "delivery" in lowered
            services["Offers Takeout"] = "takeout" in lowered or "take-out" in lowered
        if "vegan" in lowered:
            services["Vegan Options"] = True
        if "women-owned" in lowered or "women owned" in lowered:
            services["Women-owned"] = True
        if "wheelchair" in lowered:
            services["Wheelchair Accessible"] = True

    return services

def parse_business_page(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    address_info = _extract_address_block(soup)

    parsed: Dict[str, Any] = {
        "title": _extract_title(soup),
        "rating": _extract_rating(soup),
        "reviewCount": _extract_review_count(soup),
        "isClaimed": _extract_is_claimed(soup),
        "priceLevel": _extract_price_level(soup),
        "categories": _extract_categories(soup),
        "fullAddress": address_info.get("fullAddress"),
        "city": address_info.get("city"),
        "state": address_info.get("state"),
        "zipcode": address_info.get("zipcode"),
        "phoneNumber": _extract_phone_number(soup),
        "images": _extract_images(soup),
        "website": _extract_website(soup),
        "hours": _extract_hours(soup),
        "businessOwnerName": _extract_owner_name(soup),
        "about": _extract_about(soup),
        "reviewhighlights": _extract_review_highlights(soup),
        "businessServices": _extract_business_services(soup),
    }

    logging.debug("Parsed business data keys: %s", list(parsed.keys()))
    return parsed