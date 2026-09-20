import io
import json
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
INDEX_URL = "https://mscio.eu/folder/documents/UKMTO%20Warnings/"
OUTPUT_FILE = "incidents.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}
print("Getting UKMTO warning index...")
response = requests.get(INDEX_URL, headers=HEADERS, timeout=30)
response.raise_for_status()
soup = BeautifulSoup(response.text, "html.parser")
links = []
for link in soup.find_all("a", href=True):
name = link.get_text(" ", strip=True)
url = link["href"].strip()
if "UKMTO" not in name.upper():
continue
if ".pdf" not in url.lower():
continue
if url.startswith("/"):
url = "https://mscio.eu" + url
links.append((name, url))
print("Found", len(links), "UKMTO PDF links.")
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
text += " " + page_text
text = re.sub(r"\s+", " ", text).strip()
number_match = re.search(
r"(\d{3}-\d{2})",
text
)
if not number_match:
print("No warning number found.")
continue
number = number_match.group(1)
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
description = description_match.group(0)
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
if incidents:
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
"UKMTO incidents."
)
else:
print("No incidents extracted.")
print("Keeping existing incidents.json.")
