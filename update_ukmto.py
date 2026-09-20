import io
import json
import re
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

OUTPUT_FILE = Path("incidents.json")
MSCIO_WARNINGS_URL = (
"https://mscio.eu/folder/documents/UKMTO%20Warnings/"
)
HEADERS = {
"User-Agent": "Mozilla/5.0 (compatible; UKMTO-Signage/1.0)"
}

def clean(text):
return re.sub(r"\s+", " ", text or "").strip()

def get_warning_links():
print("Getting UKMTO warning index...")
response = requests.get(
MSCIO_WARNINGS_URL,
headers=HEADERS,
timeout=30
)
response.raise_for_status()
soup = BeautifulSoup(response.text, "html.parser")
links = []
for link in soup.find_all("a", href=True):
name = clean(link.get_text(" ", strip=True))
href = link["href"].strip()
if not name:
continue
if "UKMTO" not in name.upper():
continue
if not href.lower().endswith(".pdf"):
continue
if href.startswith("/"):
href = "https://mscio.eu" + href
if href.startswith("http"):
links.append((name, href))
return links

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
text = page.extract_text()
if text:
pages.append(text)
return clean(" ".join(pages))

def parse_warning(text):
warning_match = re.search(
r"(\d{3}-\d{2})\s[–-]\s([A-Z][A-Z ]+)",
text,
re.IGNORECASE
)
if not warning_match:
return None
number = warning_match.group(1)
incident_type = clean(warning_match.group(2)).upper()
date_match = re.search(
r"Report Date:\s(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})",
text,
re.IGNORECASE
)
date = ""
if date_match:
raw_date = date_match.group(1)
for date_format in (
"%d %b %Y",
"%d %b %y"
):
try:
date = datetime.strptime(
raw_date,
date_format
).strftime("%d %b %Y").upper()
break
except ValueError:
pass
description_match = re.search(
r"UKMTO has received.",
text,
re.IGNORECASE
)
if description_match:
description = clean(description_match.group(0))
else:
description = text
if len(description) > 1500:
description = description[:1500].rstrip() + "..."
location = "UKMTO AREA OF OPERATIONS"
location_match = re.search(
r"incident within the ([^.]+)",
text,
re.IGNORECASE
)
if not location_match:
location_match = re.search(
r"incident in the ([^.]+)",
text,
re.IGNORECASE
)
if location_match:
location = clean(location_match.group(1))
return {
"number": "UKMTO WARNING " + number,
"date": date,
"type": incident_type,
"location": location,
"description": description
}

def main():
print("Retrieving UKMTO warnings...")
try:
links = get_warning_links()
except Exception as error:
print("ERROR retrieving warning index:")
print(error)
print("Keeping existing incidents.json.")
return
print("Found", len(links), "UKMTO warning documents.")
if not links:
print("No warning documents found.")
print("Keeping existing incidents.json.")
return
incidents = []
# The MSCIO list is newest first.
# Process the newest 30 documents.
for name, url in links[:30]:
try:
print("Reading:", name)
text = read_pdf(url)
incident = parse_warning(text)
if incident:
incidents.append(incident)
except Exception as error:
print("Could not process:", name)
print(error)
if not incidents:
print("No valid UKMTO warnings were extracted.")
print("Keeping existing incidents.json.")
return
# Keep the FIRST occurrence of each warning number.
# The MSCIO directory lists updates before the original warning,
# so this preserves the latest version.
unique = {}
for incident in incidents:
number = incident["number"]
if number not in unique:
unique[number] = incident
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
# Keep the 20 newest warnings.
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
file.write("
")
print(
"Successfully wrote",
len(incidents),
"UKMTO warnings to incidents.json"
)

if __name__ == "__main__":
main()
