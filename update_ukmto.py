import io
import json
import re
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

OUTPUT_FILE = Path("incidents.json")
UKMTO_RECENT_URL = "https://www.ukmto.org/recent-incidents"
HEADERS = {
"User-Agent": (
"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
"AppleWebKit/537.36 (KHTML, like Gecko) "
"Chrome/140.0 Safari/537.36"
)
}

def clean(text):
return re.sub(r"\s+", " ", text or "").strip()

def load_existing():
if not OUTPUT_FILE.exists():
return []
try:
with OUTPUT_FILE.open("r", encoding="utf-8") as f:
data = json.load(f)
return data if isinstance(data, list) else []
except Exception as exc:
print(f"Could not read existing incidents.json: {exc}")
return []

def download_pdf(url):
response = requests.get(
url,
headers=HEADERS,
timeout=30,
)
response.raise_for_status()
content_type = response.headers.get("content-type", "").lower()
if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
raise ValueError("Response was not a PDF")
return response.content

def parse_warning_pdf(pdf_bytes, url):
reader = PdfReader(io.BytesIO(pdf_bytes))
pages = []
for page in reader.pages:
try:
text = page.extract_text() or ""
pages.append(text)
except Exception:
pass
text = clean("
".join(pages))
if not text:
return None
# Warning number and type.
warning_match = re.search(
r"(\d{3}-\d{2})\s-\s([A-Z][A-Z ]+)",
text,
re.IGNORECASE,
)
if not warning_match:
return None
number = warning_match.group(1)
incident_type = clean(warning_match.group(2)).upper()
# Report date.
date_match = re.search(
r"Report Date:\s(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
text,
re.IGNORECASE,
)
if not date_match:
return None
raw_date = date_match.group(1)
try:
date_obj = datetime.strptime(raw_date, "%d %b %Y")
display_date = date_obj.strftime("%d %b %Y").upper()
except ValueError:
display_date = raw_date.upper()
# Try to find the location.
location = ""
location_patterns = [
r"incident\s+[^.]{0,150}?\b(?:of|near|off|south of|north of|east of|west of)\s+([^.
]+)",
r"^\s([A-Z][A-Za-z .'-]+,\s[A-Z][A-Za-z .'-]+)\s$",
]
for pattern in location_patterns:
match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
if match:
candidate = clean(match.group(1))
if 3 <= len(candidate) <= 100:
location = candidate
break
# The main incident narrative normally begins with:
# "UKMTO has received..."
description_match = re.search(
r"(UKMTO has received.?)(?:Vessels are advised|watchkeepers@ukmto.org|UKMTO UK Maritime)",
text,
re.IGNORECASE | re.DOTALL,
)
if description_match:
description = clean(description_match.group(1))
else:
description = text
if len(description) > 1500:
description = description[:1497].rstrip() + "..."
return {
"number": f"UKMTO WARNING {number}",
"date": display_date,
"type": incident_type,
"location": location or "UKMTO AREA OF OPERATIONS",
"description": description,
"_url": url,
}

def find_pdf_links():
"""
Try to discover UKMTO PDF links from the Recent Incidents page.
UKMTO currently renders much of this page dynamically, so this may
return zero links. That is treated as a failed acquisition rather
than an empty incident feed.
"""
response = requests.get(
UKMTO_RECENT_URL,
headers=HEADERS,
timeout=30,
)
response.raise_for_status()
soup = BeautifulSoup(response.text, "html.parser")
links = set()
for link in soup.find_all("a", href=True):
href = link["href"].strip()
if ".pdf" not in href.lower():
continue
if "ukmto.org" not in href:
if href.startswith("/"):
href = "https://www.ukmto.org" + href
else:
continue
links.add(href)
return sorted(links)

def main():
print("Retrieving UKMTO warning documents...")
existing = load_existing()
try:
pdf_links = find_pdf_links()
except Exception as exc:
print(f"ERROR: Could not retrieve UKMTO warning links: {exc}")
print("Keeping existing incidents.json.")
return
print(f"Found {len(pdf_links)} UKMTO PDF links.")
if not pdf_links:
print(
"UKMTO did not expose warning PDF links in the automated "
"page response."
)
print("Keeping existing incidents.json.")
return
incidents = []
for url in pdf_links:
try:
pdf = download_pdf(url)
incident = parse_warning_pdf(pdf, url)
if incident:
incidents.append(incident)
except Exception as exc:
print(f"Skipping {url}: {exc}")
if not incidents:
print("No valid UKMTO warnings could be extracted.")
print("Keeping existing incidents.json.")
return
# Newest first.
def sort_key(item):
try:
return datetime.strptime(
item["date"],
"%d %b %Y",
)
except Exception:
return datetime.min
incidents.sort(key=sort_key, reverse=True)
# Remove duplicate warning numbers, keeping the newest version.
unique = {}
for incident in incidents:
unique[incident["number"]] = incident
incidents = list(unique.values())
# Keep the 20 most recent warnings.
incidents = incidents[:20]
# Remove the private URL field before writing the public JSON.
for incident in incidents:
incident.pop("_url", None)
with OUTPUT_FILE.open("w", encoding="utf-8") as f:
json.dump(
incidents,
f,
indent=2,
ensure_ascii=False,
)
f.write("
")
print(
f"Successfully wrote {len(incidents)} UKMTO warnings "
f"to {OUTPUT_FILE}"
)

if __name__ == "__main__":
main()
