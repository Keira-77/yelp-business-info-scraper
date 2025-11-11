thonimport re
from typing import Any, Dict, List

def _clean_text(value: str) -> str:
    # Normalize whitespace and strip ends
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()

def _clean_string_or_none(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = _clean_text(value)
        return cleaned if cleaned else None
    return value

def clean_business_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform light normalization of a business record.
    - Trim and collapse whitespace on string fields
    - Normalize nested strings in lists and dicts
    """
    cleaned: Dict[str, Any] = {}

    for key, value in record.items():
        if isinstance(value, str):
            cleaned[key] = _clean_string_or_none(value)
        elif isinstance(value, list):
            new_list: List[Any] = []
            for item in value:
                if isinstance(item, str):
                    new_list.append(_clean_text(item))
                elif isinstance(item, dict):
                    new_list.append(clean_business_record(item))
                else:
                    new_list.append(item)
            cleaned[key] = new_list
        elif isinstance(value, dict):
            nested: Dict[str, Any] = {}
            for n_key, n_value in value.items():
                if isinstance(n_value, str):
                    nested[n_key] = _clean_string_or_none(n_value)
                else:
                    nested[n_key] = n_value
            cleaned[key] = nested
        else:
            cleaned[key] = value

    # Basic normalization for reviewCount such as "844 reviews"
    review = cleaned.get("reviewCount")
    if isinstance(review, str):
        match = re.search(r"([0-9,]+)", review)
        if match:
            # Keep the original style "844 reviews" but ensure number is normalized
            number = match.group(1).replace(",", "")
            cleaned["reviewCount"] = f"{number} reviews"

    return cleaned