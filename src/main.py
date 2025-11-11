thonimport argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

# Ensure the src directory is on sys.path so namespace packages work
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from extractors.yelp_parser import fetch_html, parse_business_page, detect_page_not_found  # type: ignore
from extractors.field_mapper import map_raw_to_business  # type: ignore
from extractors.utils_time import current_timestamp  # type: ignore
from pipelines.data_cleaner import clean_business_record  # type: ignore

def load_settings(config_path: str) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "timeout": 15,
        "concurrent_requests": 1,
        "output_file": "data/sample_output.json",
        "log_level": "INFO",
    }

    if not os.path.exists(config_path):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
        logging.warning("Config file not found at %s; using defaults", config_path)
        return defaults

    with open(config_path, "r", encoding="utf-8") as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError as exc:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s [%(levelname)s] %(message)s",
            )
            logging.error("Failed to parse settings.json: %s. Using defaults.", exc)
            return defaults

    merged = {**defaults, **config}
    log_level_str = str(merged.get("log_level", "INFO")).upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    return merged

def read_input_urls(file_path: str) -> List[str]:
    if not os.path.exists(file_path):
        logging.error("Input URLs file not found: %s", file_path)
        raise FileNotFoundError(f"Input URLs file not found: {file_path}")

    urls: List[str] = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if url and not url.startswith("#"):
                urls.append(url)

    if not urls:
        logging.warning("No URLs found in %s", file_path)

    return urls

def write_output(data: List[Dict[str, Any]], output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    logging.info("Wrote %d records to %s", len(data), output_path)

def resolve_path_relative_to_root(relative_path: str) -> str:
    # Repo root is one level above src/
    root_dir = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))
    return os.path.join(root_dir, relative_path)

def scrape_urls(
    urls: List[str],
    settings: Dict[str, Any],
) -> List[Dict[str, Any]]:
    import requests

    headers = {"User-Agent": settings.get("user_agent")}
    timeout = int(settings.get("timeout", 15))

    session = requests.Session()
    results: List[Dict[str, Any]] = []

    for idx, url in enumerate(urls, start=1):
        logging.info("Processing (%d/%d): %s", idx, len(urls), url)
        try:
            html, status_code = fetch_html(
                url=url,
                session=session,
                headers=headers,
                timeout=timeout,
            )
            is_not_found = detect_page_not_found(html, status_code)

            if is_not_found or not html:
                logging.warning("Page not found or empty HTML for URL: %s", url)
                raw_data: Dict[str, Any] = {}
            else:
                raw_data = parse_business_page(html)

            timestamp = current_timestamp()
            mapped = map_raw_to_business(
                raw_data=raw_data,
                url=url,
                timestamp=timestamp,
                is_page_not_found=is_not_found,
            )
            cleaned = clean_business_record(mapped)
            results.append(cleaned)
        except Exception as exc:  # noqa: BLE001
            logging.exception("Unexpected error while scraping %s: %s", url, exc)
            # Still append a record that describes the failure
            results.append(
                {
                    "title": None,
                    "rating": None,
                    "reviewCount": None,
                    "isClaimed": None,
                    "priceLevel": None,
                    "categories": None,
                    "fullAddress": None,
                    "city": None,
                    "state": None,
                    "zipcode": None,
                    "phoneNumber": None,
                    "images": [],
                    "website": None,
                    "hours": {},
                    "businessOwnerName": None,
                    "about": None,
                    "reviewhighlights": [],
                    "businessServices": {},
                    "timestamp": current_timestamp(),
                    "url": url,
                    "is_page_not_found": True,
                    "error": str(exc),
                }
            )

    return results

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape business information from Yelp business URLs."
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input_file",
        default="data/input_urls.txt",
        help="Path to the input URLs file (default: data/input_urls.txt)",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_file",
        default=None,
        help="Path to the output JSON file (default from settings.json)",
    )
    return parser.parse_args()

def main() -> None:
    config_path = os.path.join(CURRENT_DIR, "config", "settings.json")
    settings = load_settings(config_path)

    args = parse_args()
    input_file = resolve_path_relative_to_root(args.input_file)
    output_file = (
        resolve_path_relative_to_root(args.output_file)
        if args.output_file
        else resolve_path_relative_to_root(settings.get("output_file", "data/sample_output.json"))
    )

    try:
        urls = read_input_urls(input_file)
    except FileNotFoundError as exc:
        logging.error(str(exc))
        sys.exit(1)

    if not urls:
        logging.error("No URLs to process; exiting.")
        sys.exit(1)

    results = scrape_urls(urls, settings)
    write_output(results, output_file)

if __name__ == "__main__":
    main()