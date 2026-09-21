#!/bin/bash
set -e

INDEX_URL="https://mscio.eu/folder/documents/UKMTO%20Warnings/"
OUTPUT="incidents.json"

echo "Getting UKMTO warning index..."

curl -L \
  -A "Mozilla/5.0" \
  -s \
  "$INDEX_URL" \
  -o ukmto_index.html

python3 -c '
import re
import html

with open("ukmto_index.html", encoding="utf-8") as f:
    s = f.read()

s = html.unescape(s)

urls = re.findall(
    r"(?:https?:)?//[^\"<> ]+\.pdf(?:[^\"<> ]*)|/[^\"<> ]+\.pdf(?:[^\"<> ]*)",
    s,
    re.I
)

seen = set()

for u in urls:
    if u.startswith("/"):
        u = "https://mscio.eu" + u
    elif u.startswith("//"):
        u = "https:" + u

    if u not in seen:
        seen.add(u)
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
mkdir -p ukmto_pdfs

INDEX=0

while read -r URL
do
    INDEX=$((INDEX + 1))

    FILE="ukmto_pdfs/$INDEX.pdf"
    TEXT="ukmto_pdfs/$INDEX.txt"

    echo "Downloading warning $INDEX..."

    curl -L \
      -A "Mozilla/5.0" \
      -s \
      "$URL" \
      -o "$FILE"

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

    pdftotext \
      -layout \
      "$FILE" \
      "$TEXT" \
      2>/dev/null || true

done < ukmto_links.txt
echo "===== DEBUG: FIRST UKMTO TEXT FILES ====="

for FILE in ukmto_pdfs/*.txt
do
    echo "===== $FILE ====="
    sed -n '1,100p' "$FILE"
    echo
done

echo "===== END DEBUG ====="


echo "Processing warning documents..."

python3 - <<'PY'
import glob
import json
import re
from datetime import datetime


def clean_text(text):
    text = text.replace("\xa0", " ")
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def normalise_spaces(text):
    return re.sub(r"\s+", " ", text).strip()


def extract_warning_number(text):
    patterns = [
        r"\b(\d{3})[- ](\d{2})\s*[–-]\s*[A-Z]",
        r"\bUKMTO\s+WARNING\s+(\d{3})[- ](\d{2})",
        r"\b(\d{3})[- ](\d{2})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return f"{match.group(1)}-{match.group(2)}"

    return ""


def extract_type(text):
    # The normal UKMTO heading is:
    # 134-26 – ATTACK – Update 001

    match = re.search(
        r"\b\d{3}[- ]\d{2}\s*[–-]\s*"
        r"(ATTACK|BOARDING|HIJACK|SUSPICIOUS ACTIVITY|"
        r"UAV|DRONE|MISSILE|OTHER)\b",
        text,
        re.I
    )

    if match:
        return match.group(1).upper()

    # Fallback to searching the body.
    for incident_type in (
        "SUSPICIOUS ACTIVITY",
        "ATTACK",
        "BOARDING",
        "HIJACK",
        "MISSILE",
        "DRONE",
        "UAV",
    ):
        if re.search(r"\b" + re.escape(incident_type) + r"\b", text, re.I):
            return incident_type

    return "MARITIME SECURITY"


def extract_report_datetime(text):
    match = re.search(
        r"Report Date:\s*Report Time:.*?\n"
        r"\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})"
        r"\s+(\d{3,4})\s*UTC",
        text,
        re.I | re.S
    )

    if not match:
        match = re.search(
            r"Report Date:.*?"
            r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})"
            r"\s+(\d{3,4})\s*UTC",
            text,
            re.I | re.S
        )

    if not match:
        return "", ""

    raw_date = match.group(1)
    raw_time = match.group(2).zfill(4)

    parsed_date = ""

    for fmt in ("%d %b %y", "%d %b %Y"):
        try:
            parsed_date = datetime.strptime(
                raw_date,
                fmt
            ).strftime("%d %b %Y").upper()
            break
        except ValueError:
            pass

    if not parsed_date:
        parsed_date = raw_date.upper()

    return parsed_date, raw_time + " UTC"


def extract_location(text):
    patterns = [
        r"incident within the ([^.]+)",
        r"incident in the ([^.]+)",
        r"incident approximately ([^.]+)",
        r"incident near ([^.]+)",
        r"incident off ([^.]+)",
        r"incident ([^.]*\bStrait of Hormuz\b[^.]*)",
        r"incident ([^.]*\bBab el Mandeb\b[^.]*)",
        r"incident ([^.]*\bGulf of Aden\b[^.]*)",
        r"incident ([^.]*\bArabian Sea\b[^.]*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            location = normalise_spaces(match.group(1))

            location = re.sub(
                r"\s+(?:A vessel|The vessel|A tanker|The tanker)\b.*$",
                "",
                location,
                flags=re.I
            )

            if len(location) > 120:
                location = location[:120].rstrip(" ,;:")

            if location:
                return location.upper()

    # Look for common named maritime areas in the text.
    areas = [
        "STRAIT OF HORMUZ",
        "BAB EL MANDEB",
        "GULF OF ADEN",
        "ARABIAN SEA",
        "RED SEA",
        "GULF OF OMAN",
        "PERSIAN GULF",
        "INDIAN OCEAN",
    ]

    for area in areas:
        if re.search(r"\b" + re.escape(area) + r"\b", text, re.I):
            return area

    return "LOCATION NOT SPECIFIED"


def extract_vessel(text):
    # Only return a vessel name where the document explicitly
    # associates a name with a vessel. Do not guess.

    patterns = [
        r"\b(?:M/V|MV|M\.V\.)\s+([A-Z0-9][A-Z0-9 .,'&()/\-]{2,60})",
        r"\b(?:M/T|MT|M\.T\.)\s+([A-Z0-9][A-Z0-9 .,'&()/\-]{2,60})",
        r"\bvessel\s+named\s+([A-Z0-9][A-Z0-9 .,'&()/\-]{2,60})",
        r"\bship\s+named\s+([A-Z0-9][A-Z0-9 .,'&()/\-]{2,60})",
    ]

    stop_words = {
        "WHILE",
        "WHICH",
        "WAS",
        "HAS",
        "HAD",
        "REPORTING",
        "REPORTED",
        "TRANSITING",
        "TRANSITED",
        "IN",
        "AT",
        "OFF",
        "NEAR",
        "FROM",
        "TO",
        "AND",
        "THE",
        "A",
        "AN",
    }

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if not match:
            continue

        vessel = normalise_spaces(match.group(1))

        # Stop at common sentence boundaries.
        vessel = re.split(
            r"\s+(?:while|which|was|has|had|reported|transiting|"
            r"in|at|off|near|from|to|and|the)\b",
            vessel,
            maxsplit=1,
            flags=re.I
        )[0]

        vessel = vessel.strip(" .,:;()-")

        words = vessel.split()

        while words and words[-1].upper() in stop_words:
            words.pop()

        vessel = " ".join(words)

        if 2 <= len(vessel) <= 60:
            return vessel.upper()

    return "VESSEL NOT NAMED"


def extract_description(text):
    # Find the UKMTO narrative.
    match = re.search(
        r"(UKMTO has received.*?)(?=\n?\s*Vessels are advised\b|"
        r"\n?\s*Vessels are requested\b|"
        r"\n?\s*Vessels operating\b|$)",
        text,
        re.I | re.S
    )

    if match:
        description = normalise_spaces(match.group(1))
    else:
        # Fallback: locate the first narrative sentence after the header.
        lines = [
            normalise_spaces(line)
            for line in text.splitlines()
            if normalise_spaces(line)
        ]

        description = ""

        for line in lines:
            if re.search(r"\bUKMTO has received\b", line, re.I):
                description = line
                break

        if not description:
            description = normalise_spaces(text)

    if len(description) > 900:
        description = description[:897].rstrip() + "..."

    return description


incidents = []

for filename in glob.glob("ukmto_pdfs/*.txt"):
    try:
        with open(
            filename,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:
            raw_text = f.read()
    except OSError:
        continue

    if not raw_text.strip():
        continue

    text = clean_text(raw_text)
    number = extract_warning_number(text)

    if not number:
        continue

    incident_type = extract_type(text)
    date, time = extract_report_datetime(text)
    location = extract_location(text)
    vessel = extract_vessel(text)
    description = extract_description(text)

    # Detect whether this document is an update.
    is_update = bool(
        re.search(
            r"\bUPDATE\s+\d+\b",
            text,
            re.I
        )
    )

    incidents.append({
        "number": "UKMTO WARNING " + number,
        "warning_number": number,
        "date": date,
        "time": time,
        "type": incident_type,
        "location": location,
        "vessel": vessel,
        "description": description,
        "is_update": is_update,
    })


# UKMTO publishes updates alongside the original warning.
# Keep only the newest document for each warning number.
by_number = {}

for incident in incidents:
    key = incident["warning_number"]

    if key not in by_number:
        by_number[key] = incident
        continue

    # Because the UKMTO index normally lists the update first,
    # prefer the update if one is encountered.
    if incident["is_update"] and not by_number[key]["is_update"]:
        by_number[key] = incident


incidents = list(by_number.values())


def sort_key(item):
    try:
        date_part = datetime.strptime(
            item["date"],
            "%d %b %Y"
        )
    except ValueError:
        date_part = datetime.min

    time_part = item.get("time", "")

    try:
        hour = int(time_part[:2])
        minute = int(time_part[2:4])
    except (ValueError, TypeError):
        hour = 0
        minute = 0

    return (
        date_part,
        hour,
        minute
    )


incidents.sort(
    key=sort_key,
    reverse=True
)

# Keep enough incidents for the ticker and display.
incidents = incidents[:30]

# Remove the internal field before writing JSON.
for incident in incidents:
    incident.pop("is_update", None)

with open(
    "incidents.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        incidents,
        f,
        indent=2,
        ensure_ascii=False
    )

print(
    "Successfully wrote",
    len(incidents),
    "UKMTO incidents."
)

if incidents:
    latest = incidents[0]

    print(
        "Latest:",
        latest["number"],
        "|",
        latest["type"],
        "|",
        latest["date"],
        latest["time"]
    )

    print(
        "Location:",
        latest["location"]
    )

    print(
        "Vessel:",
        latest["vessel"]
    )
PY

# rm -rf ukmto_pdfs
rm -f ukmto_index.html ukmto_links.txt

echo "UKMTO update complete."
