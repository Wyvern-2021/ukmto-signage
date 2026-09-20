import requests

url = "https://mscio.eu/folder/documents/UKMTO%20Warnings/"

response = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30
)

print("HTTP STATUS:", response.status_code)
print("PAGE LENGTH:", len(response.text))
print("PDF LINKS:", response.text.lower().count(".pdf"))
