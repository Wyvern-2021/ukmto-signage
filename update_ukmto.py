import io
import json
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
OUTPUT_FILE = "incidents.json"
INDEX_URL = "https://mscio.eu/folder/documents/UKMTO%20Warnings/"
HEADERS = {
"User-Agent": "Mozilla/5.0"
}

def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()

def get_links():
r = requests.get(INDEX_URL, headers=HEADERS, timeout=30)
r.raise_for_status()
soup = BeautifulSoup(r.text, "html.parser")
results = []
for a in soup.find_all("a", href=True):
name = clean(a.get_text())
url = a["href"].strip()
if "UKMTO" not in name.upper():
continue
if ".pdf" not in url.lower():
continue
if url.startswith("/"):
url = "https://mscio.eu" + url
results.append((name, url))
return results

def get_pdf(url):
r = requests.get(url, headers=HEADERS, timeout=30)
r.raise_for_status()
reader = PdfReader(io.BytesIO(r.content))
text = ""
for page in reader.pages:
text += " " + (page.extract_text() or "")
return clean(text)

def parse(text):
m = re.search(r"(\d{3}-\d{2})", text)
if not m:
return None
number = m.group(1)
m = re.search(
r"Report Date:\s(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})",
text,
re.I
)
date = ""
if m:
for fmt in ("%d %b %Y", "%d %b %y"):
try:
date = datetime.strptime(m.group(1), fmt).strftime(
"%d %b %Y"
).upper()
break
except ValueError:
pass
m = re.search(
r"\b(ATTACK|BOARDING|HIJACK|SUSPICIOUS ACTIVITY|UAV|DRONE|MISSILE)\b",
text,
re.I
)
incident_type = m.group(1).upper() if m else "MARITIME SECURITY"
m = re.search(
r"UKMTO has received.",
text,
re.I
)
description = clean(m.group(0)) if m else text
if len(description) > 1500:
description = description[:1500] + "..."
location = "UKMTO AREA OF OPERATIONS"
m = re.search(
r"incident within the ([^.]+)",
text,
re.I
)
if m:
location = clean(m.group(1))
return {
"number": "UKMTO WARNING " + number,
"date": date,
"type": incident_type,
"location": location,
"description": description
}

def main():
print("Getting UKMTO warning index...")
try:
links = get_links()
except Exception as e:
print("ERROR:", e)
print("Keeping existing incidents.json.")
return
print("Found", len(links), "PDF links.")
if not links:
print("No warning documents found.")
print("Keeping existing incidents.json.")
return
incidents = []
for name, url in links[:30]:
try:
print("Reading:", name)
text = get_pdf(url)
incident = parse(text)
if incident:
incidents.append(incident)
except Exception as e:
print("Could not process:", name)
print(e)
if not incidents:
print("No valid warnings extracted.")
print("Keeping existing incidents.json.")
return
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
incidents.sort(key=sort_key, reverse=True)
incidents = incidents[:20]
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
json.dump(incidents, f, indent=2, ensure_ascii=False)
print("Successfully wrote", len(incidents), "warnings.")

if __name__ == "__main__":
    main()
