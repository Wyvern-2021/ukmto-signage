#!/bin/bash
set -e

INDEX_URL="https://mscio.eu/folder/documents/UKMTO%20Warnings/"
OUTPUT="incidents.json"

echo "Getting UKMTO warning index..."
curl -L -A "Mozilla/5.0" -s "$INDEX_URL" > ukmto_index.html

python3 -c '
import re
import html

s = open("ukmto_index.html", encoding="utf-8").read()

urls = re.findall(
    r"(?:https?:)?//[^\"<> ]+\.pdf[^\"<> ]*|/[^\"<> ]+\.pdf[^\"<> ]*",
    html.unescape(s),
    re.I
)

for u in dict.fromkeys(urls):
    if u.startswith("/"):
        print("https://mscio.eu" + u)
    elif u.startswith("//"):
        print("https:" + u)
    else:
        print(u)
' > ukmto_links.txt

COUNT=$(wc -l < ukmto_links.txt)
echo "Found $COUNT UKMTO PDF links."

if [ "$COUNT" -eq 0 ]
then
    echo "No warning documents found."
    echo "Keeping existing incidents.json."
    exit 0
fi

rm -rf ukmto_pdfs
mkdir ukmto_pdfs

INDEX=0

while read -r URL
do
    INDEX=$((INDEX + 1))
    FILE="ukmto_pdfs/$INDEX.pdf"

    echo "Downloading warning $INDEX..."
    curl -L -A "Mozilla/5.0" -s "$URL" -o "$FILE"

    if [ ! -s "$FILE" ]
    then
        echo "Download failed."
        continue
    fi

    if ! head -c 5 "$FILE" | grep -q "%PDF-"
    then
        echo "Not a PDF."
        continue
    fi

    pdftotext -layout "$FILE" "ukmto_pdfs/$INDEX.txt" 2>/dev/null || true

done < ukmto_links.txt

echo "Processing warning documents..."

python3 - <<'PY'
import json
import glob
import re
from datetime import datetime

incidents = []

for filename in glob.glob("ukmto_pdfs/*.txt"):
    with open(filename, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    text = re.sub(r"\s+", " ", text).strip()

    match = re.search(r"(\d{3}-\d{2})", text)
    if not match:
        continue

    number = match.group(1)

    match = re.search(
        r"Report Date:\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})",
        text,
        re.I
    )

    date = ""

    if match:
        raw = match.group(1)

        for fmt in ("%d %b %y", "%d %b %Y"):
            try:
                date = datetime.strptime(raw, fmt).strftime("%d %b %Y").upper()
                break
            except ValueError:
                pass

    match = re.search(
        r"\b(ATTACK|BOARDING|HIJACK|SUSPICIOUS ACTIVITY|UAV|DRONE|MISSILE)\b",
        text,
        re.I
    )

    incident_type = (
        match.group(1).upper()
        if match
        else "MARITIME SECURITY"
    )

    match = re.search(
        r"UKMTO has received\.",
        text,
        re.I
    )

    description = (
        match.group(0).strip()
        if match
        else text
    )

    if len(description) > 1500:
        description = description[:1500] + "..."

    match = re.search(
        r"incident within the ([^.]+)",
        text,
        re.I
    )

    location = (
        match.group(1).strip()
        if match
        else "UKMTO AREA OF OPERATIONS"
    )

    incidents.append({
        "number": "UKMTO WARNING " + number,
        "date": date,
        "type": incident_type,
        "location": location,
        "description": description
    })

unique = {}

for incident in incidents:
    if incident["number"] not in unique:
        unique[incident["number"]] = incident

incidents = list(unique.values())

def sort_date(item):
    try:
        return datetime.strptime(item["date"], "%d %b %Y")
    except ValueError:
        return datetime.min

incidents.sort(key=sort_date, reverse=True)
incidents = incidents[:20]

if incidents:
    with open("incidents.json", "w", encoding="utf-8") as f:
        json.dump(
            incidents,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("Successfully wrote", len(incidents), "UKMTO incidents.")
else:
    print("No incidents extracted.")
    print("Keeping existing incidents.json.")
PY

rm -rf ukmto_pdfs
rm -f ukmto_index.html ukmto_links.txt

echo "UKMTO update complete."
