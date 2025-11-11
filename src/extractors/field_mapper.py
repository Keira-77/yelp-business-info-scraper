thonfrom typing import Any, Dict, List

def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

def map_raw_to_business(
    raw_data: Dict[str, Any],
    url: str,
    timestamp: str,
    is_page_not_found: bool,
) -> Dict[str, Any]:
    """
    Normalize the raw extracted data into the expected business schema.
    Ensures all fields exist with sensible defaults.
    """
    categories = raw_data.get("categories")
    if isinstance(categories, list):
        categories_str = ",".join(cat.strip() for cat in categories if str(cat).strip())
    elif isinstance(categories, str):
        categories_str = categories.strip()
    else:
        categories_str = None

    images = _as_list(raw_data.get("images"))
    review_highlights = _as_list(raw_data.get("reviewhighlights"))
    business_services = raw_data.get("businessServices") or {}

    if not isinstance(business_services, dict):
        business_services = {}

    hours = raw_data.get("hours") or {}
    if not isinstance(hours, dict):
        hours = {}

    mapped: Dict[str, Any] = {
        "title": raw_data.get("title"),
        "rating": raw_data.get("rating"),
        "reviewCount": raw_data.get("reviewCount"),
        "isClaimed": raw_data.get("isClaimed"),
        "priceLevel": raw_data.get("priceLevel"),
        "categories": categories_str,
        "fullAddress": raw_data.get("fullAddress"),
        "city": raw_data.get("city"),
        "state": raw_data.get("state"),
        "zipcode": raw_data.get("zipcode"),
        "phoneNumber": raw_data.get("phoneNumber"),
        "images": images,
        "website": raw_data.get("website"),
        "hours": hours,
        "businessOwnerName": raw_data.get("businessOwnerName"),
        "about": raw_data.get("about"),
        "reviewhighlights": review_highlights,
        "businessServices": business_services,
        "timestamp": timestamp,
        "url": url,
        "is_page_not_found": bool(is_page_not_found),
    }

    return mapped