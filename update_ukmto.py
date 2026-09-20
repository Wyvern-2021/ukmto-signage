import io
import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


OUTPUT_FILE = Path("incidents.json")
UKMTO_URL = "https://www.ukmto.org/recent-incidents"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; UKMTO-Signage/1.0)"
}


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def get_pdf_links():
    response = requests.get(
        UKMTO_URL,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    links = set()

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()

        if ".pdf" not in href.lower():
            continue

        if href.startswith("/"):
            href = "https://www.ukmto.org" + href

        if "ukmto.org" in href:
            links.add(href)

    return sorted(links)


def read_pdf(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    reader = PdfReader(io.BytesIO(response.content))

    pages = []

    for page in reader.pages:
        page_text = page.extract_text()

        if page_text:
            pages.append(page_text)

    return clean(" ".join(pages))


def parse_warning(text):
    warning = re.search(
        r"(\d{3}-\d{2})",
        text
    )

    if not warning:
        return None

    number = warning.group(1)

    date_match = re.search(
        r"Report Date:\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
        text,
        re.IGNORECASE
    )

    if date_match:
        raw_date = date_match.group(1)

        try:
            date = datetime.strptime(
                raw_date,
                "%d %b %Y"
            ).strftime("%d %b %Y").upper()
        except ValueError:
            date = raw_date.upper()
    else:
        date = ""

    type_match = re.search(
        r"(ATTACK|SUSPICIOUS ACTIVITY|BOARDING|HIJACK|MISSILE|UAV|DRONE)",
        text,
        re.IGNORECASE
    )

    if type_match:
        incident_type = type_match.group(1).upper()
    else:
        incident_type = "MARITIME SECURITY"

    description_match = re.search(
        r"UKMTO has received(.+)",
        text,
        re.IGNORECASE
    )

    if description_match:
        description = clean(
            "UKMTO has received " + description_match.group(1)
        )
    else:
        description = text

    if len(description) > 1500:
        description = description[:1500] + "..."

    return {
        "number": "UKMTO WARNING " + number,
        "date": date,
        "type": incident_type,
        "location": "UKMTO AREA OF OPERATIONS",
        "description": description
    }


def main():
    print("Retrieving UKMTO warning documents...")

    try:
        links = get_pdf_links()
    except Exception as error:
        print("ERROR retrieving UKMTO page:")
        print(error)
        print("Keeping existing incidents.json.")
        return

    print("Found", len(links), "PDF links.")

    if not links:
        print("No UKMTO PDF links were found.")
        print("Keeping existing incidents.json.")
        return

    incidents = []

    for link in links:
        try:
            print("Reading:", link)

            text = read_pdf(link)
            incident = parse_warning(text)

            if incident:
                incidents.append(incident)

        except Exception as error:
            print("Could not process", link)
            print(error)

    if not incidents:
        print("No valid UKMTO warnings were extracted.")
        print("Keeping existing incidents.json.")
        return

    unique = {}

    for incident in incidents:
        unique[incident["number"]] = incident

    incidents = list(unique.values())

    def sort_date(item):
        try:
            return datetime.strptime(
                item["date"],
                "%d %b %Y"
            )
        except ValueError:
            return datetime.min

    incidents.sort(
        key=sort_date,
        reverse=True
    )

    incidents = incidents[:20]

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            incidents,
            file,
            indent=2,
            ensure_ascii=False
        )
        file.write("\n")

    print(
        "Successfully wrote",
        len(incidents),
        "UKMTO incidents."
    )


if __name__ == "__main__":
    main()
