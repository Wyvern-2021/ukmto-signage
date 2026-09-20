import io
import json
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
OUTPUT_FILE = "incidents.json"
INDEX_URL = "https://mscio.eu/folder/documents/UKMTO%20Warnings/"
HEADERS = {"User-Agent": "Mozilla/5.0"}
print("Getting UKMTO warning index...")
response = requests.get(
INDEX_URL,
headers=HEADERS,
timeout=30
)
response.raise_for_status()
soup = BeautifulSoup(
response.text,
"html.parser"
)
links = []
for a in soup.find_all("a", href=True):
name = a.get_text(" ", strip=True)
url = a["href"].strip()
if "UKMTO" in name.upper() and ".pdf" in url.lower():
if url.startswith("/"):
url = "https://mscio.eu" + url
links.append((name, url))
print("Found", len(links), "PDF links.")
if len(links) == 0:
print("No warning documents found.")
print("Keeping existing incidents.json.")
else:
incidents = []
for name, url in links[:30]:
print("Reading:", name)
pdf_response = requests.get(
url,
headers=HEADERS,
timeout=30
)
pdf_response.raise_for_status()
reader = PdfReader(
io.BytesIO(pdf_response.content)
)
text = ""
for page in reader.pages:
page_text = page.extract_text()
if page_text:
text = text + " " + page_text
text = re.sub(
r"\s+",
" ",
text
).strip()
warning_match = re.search(
r"(\d{3}-\d{2})",
text
)
if not warning_match:
print("No warning number found.")
continue
number = warning_match.group(1)
date = ""
date_match = re.search(
r"Report Date:\s(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})",
text,
re.IGNORECASE
)
if date_match:
raw_date = date_match.group(1)
try:
date = datetime.strptime(
raw_date,
"%d %b %y"
).strftime("%d %b %Y").upper()
except ValueError:
try:
date = datetime.strptime(
raw_date,
"%d %b %Y"
).strftime("%d %b %Y").upper()
except ValueError:
date = raw_date.upper()
incident_type = "MARITIME SECURITY"
type_match = re.search(
r"\b(ATTACK|BOARDING|HIJACK|SUSPICIOUS ACTIVITY|UAV|DRONE|MISSILE)\b",
text,
re.IGNORECASE
)
if type_match:
incident_type = type_match.group(1).upper()
description = text
description_match = re.search(
r"UKMTO has received.",
text,
re.IGNORECASE
)
if description_match:
description = description_match.group(0).strip()
if len(description) > 1500:
description = description[:1500] + "..."
location = "UKMTO AREA OF OPERATIONS"
location_match = re.search(
r"incident within the ([^.]+)",
text,
re.IGNORECASE
)
if location_match:
location = location_match.group(1).strip()
incidents.append(
{
"number": "UKMTO WARNING " + number,
"date": date,
"type": incident_type,
"location": location,
"description": description
}
)
unique = {}
for incident in incidents:
number = incident["number"]
if number not in unique:
unique[number] = incident
incidents = list(unique.values())
if len(incidents) > 0:
incidents.sort(
key=lambda item: item["date"],
reverse=True
)
incidents = incidents[:20]
with open(
OUTPUT_FILE,
"w",
encoding="utf-8"
) as file:
json.dump(
incidents,
file,
indent=2,
ensure_ascii=False
)
print(
"Successfully wrote",
len(incidents),
"UKMTO warnings."
)
else:
print("No valid warnings extracted.")
print("Keeping existing incidents.json.")
