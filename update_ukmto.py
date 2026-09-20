import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


UKMTO_URL = "https://www.ukmto.org/recent-incidents"
OUTPUT_FILE = Path("incidents.json")


def clean_text(text):
    """Collapse whitespace and tidy scraped text."""
    return re.sub(r"\s+", " ", text or "").strip()


def get_incidents():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/131 Safari/537.36"
        )
    }

    response = requests.get(
        UKMTO_URL,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    incidents = []

    # Look for links/cards associated with UKMTO incident records.
    for link in soup.find_all("a", href=True):

        text = clean_text(link.get_text(" ", strip=True))

        if not text:
            continue

        # Incident entries normally contain a date.
        date_match = re.search(
            r"\b(\d{1,2}/\d{1,2}/\d{4})\b",
            text
        )

        if not date_match:
            continue

        date_text = date_match.group(1)

        # Identify the incident type where possible.
        incident_type = "MARITIME SECURITY"

        for possible_type in [
            "Attack",
            "Boarding",
            "Hijack",
            "Suspicious Activity",
            "Suspicious Approach",
            "Advisory",
            "Sighting",
            "Other",
        ]:
            if possible_type.lower() in text.lower():
                incident_type = possible_type.upper()
                break

        # Remove the date from the remaining text.
        description = clean_text(
            text.replace(date_text, "", 1)
        )

        if not description:
            continue

        incidents.append(
            {
                "number": "",
                "date": date_text,
                "type": incident_type,
                "location": "UKMTO AREA OF OPERATIONS",
                "description": description,
            }
        )

    return incidents


def load_existing():
    """Load the previous feed so we never overwrite good data with nothing."""
    if not OUTPUT_FILE.exists():
        return []

    try:
        with OUTPUT_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, list) else []

    except Exception:
        return []


def main():
    print("Retrieving UKMTO Recent Incidents...")

    try:
        incidents = get_incidents()
    except Exception as exc:
        print(f"ERROR: Unable to retrieve UKMTO data: {exc}")
        print("Keeping the existing incidents.json.")
        return

    # Never replace valid data with an empty result.
    if not incidents:
        print("WARNING: UKMTO returned no incidents.")
        print("Keeping the existing incidents.json.")
        return

    # Remove duplicates while preserving order.
    unique = []
    seen = set()

    for incident in incidents:
        key = (
            incident.get("date"),
            incident.get("type"),
            incident.get("description"),
        )

        if key not in seen:
            seen.add(key)
            unique.append(incident)

    # Keep the newest records first and limit the feed.
    unique = unique[:20]

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(
        f"Successfully wrote {len(unique)} incidents "
        f"to {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
