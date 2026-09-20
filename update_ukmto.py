import requests
from bs4 import BeautifulSoup

url = "https://mscio.eu/folder/documents/UKMTO%20Warnings/"

response = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30
)

response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

pdf_url = None

for link in soup.find_all("a", href=True):
    href = link["href"]

    if ".pdf" in href.lower():
        pdf_url = href
        break

if pdf_url.startswith("/"):
    pdf_url = "https://mscio.eu" + pdf_url

print("TEST PDF:", pdf_url)

pdf = requests.get(
    pdf_url,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=30
)

print("PDF STATUS:", pdf.status_code)
print("PDF SIZE:", len(pdf.content))
print("PDF HEADER:", pdf.content[:5])
