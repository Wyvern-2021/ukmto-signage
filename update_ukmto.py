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
response = requests.get(INDEX_URL, headers=HEADERS, timeout=30)
response.raise_for_status()
soup = BeautifulSoup(response.text, "html.parser")
links = [
(
a.get_text(" ", strip=True),
a["href"].strip() if a["href"].startswith("http") else "https://mscio.eu" + a["href"]
)
for a in soup.find_all("a", href=True)
if "UKMTO" in a.get_text(" ", strip=True).upper()
and ".pdf" in a["href"].lower()
]
print("Found", len(links), "PDF links.")
if not links:
print("No warning documents found.")
print("Keeping existing incidents.json.")
else:
incidents = []
for name, url in links[:30]:
print("Reading:", name)
try:
pdf_response = requests.get(
url,
headers=HEADERS,
timeout=30
)
pdf_response.raise_for_status()
reader = PdfReader(
io.BytesIO(pdf_response.content)
)
text = " ".join(
page.extract_text() or ""
for page in reader.pages
)
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
continue
number = warning_match.group(1)
date_match = re.search(
r"Report Date:\s(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})",
text,
re.IGNORECASE
)
date = ""
if date_match:
for date_format in ("%d %b %Y", "%d %b %y"):
try:
date = datetime.strptime(
date_match.group(1),
date_format
).strftime("%d %b %Y").upper()
break
except ValueError:
pass
type_match = re.search(
r"\b(ATTACK|BOARDING|HIJACK|SUSPICIOUS ACTIVITY|UAV|DRONE|MISSILE)\b",
text,
re.IGNORECASE
)
incident_type = (
type_match.group(1).upper()
if type_match
else "MARITIME SECURITY"
)
description_match = re.search(
r"UKMTO has received.",
text,
re.IGNORECASE
)
description = (
description_match.group(0).strip()
if description_match
else text
)
if len(description) > 1500:
description = description[:1500] + "..."
location_match = re.search(
r"incident within the ([^.]+)",
text,
re.IGNORECASE
)
location = (
location_match.group(1).strip()
if location_match
else "UKMTO AREA OF OPERATIONS"
)
incidents.append(
{
"number": "UKMTO WARNING " + number,
"date": date,
"type": incident_type,
"location": location,
"description": description
}
)
except Exception as error:
print("Could not process:", name)
print(error)
unique = {}
for incident in incidents:
if incident["number"] not in unique:
unique[incident["number"]] = incident
incidents = list(unique.values())
def sort_key(item):
try:
return datetime.strptime(
item["date"],
"%d %b %Y"
)
except ValueError:
return datetime.min
incidents.sort(
key=sort_key,
reverse=True
)
incidents = incidents[:20]
if incidents:
open(
OUTPUT_FILE,
"w",
encoding="utf-8"
).write(
json.dumps(
incidents,
indent=2,
ensure_ascii=False
)
)
print(
"Successfully wrote",
len(incidents),
"UKMTO warnings."
)
else:
print("No valid warnings extracted.")
print("Keeping existing incidents.json.")
