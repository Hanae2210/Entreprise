"""Trouve les boutiques à démarcher pour vendre du miel, à partir d'OpenStreetMap.

Usage:
    python prospects.py                       # Ariège (09)
    python prospects.py 09 31 11 -o boutiques.csv
    python prospects.py 09 --enrich           # visite les sites web pour trouver les emails
"""

import argparse
import asyncio
import csv
import json
import re
import urllib.parse
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Tag OpenStreetMap -> catégorie affichée. L'ordre fixe la priorité dans le CSV.
CATEGORIES = {
    ("shop", "farm"): "Magasin de producteurs",
    ("shop", "deli"): "Épicerie fine",
    ("shop", "organic"): "Magasin bio",
    ("shop", "health_food"): "Magasin bio / diététique",
    ("shop", "cheese"): "Fromagerie",
    ("shop", "wine"): "Caviste",
    ("shop", "tea"): "Salon / boutique de thé",
    ("shop", "confectionery"): "Confiserie",
    ("shop", "greengrocer"): "Primeur",
    ("shop", "gift"): "Boutique cadeaux / souvenirs",
    ("shop", "convenience"): "Épicerie de proximité",
    ("tourism", "information"): "Office de tourisme",
    ("amenity", "marketplace"): "Marché",
    ("shop", "supermarket"): "Supermarché",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
FIELDS = ["catégorie", "nom", "commune", "adresse", "téléphone", "email", "site", "horaires", "osm"]


def build_query(departements: list[str]) -> str:
    areas = "".join(f'area["ISO3166-2"="FR-{d}"];' for d in departements)
    selectors = "".join(
        f'nwr["{k}"="{v}"]["name"](area.dep);' for k, v in CATEGORIES
    )
    return f"[out:json][timeout:180];({areas})->.dep;({selectors});out tags center;"


def fetch_osm(departements: list[str]) -> list[dict]:
    data = urllib.parse.urlencode({"data": build_query(departements)}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": "hanae-prospects/1.0"})
    with urllib.request.urlopen(req, timeout=200) as resp:
        return json.load(resp)["elements"]


def to_row(element: dict) -> dict | None:
    tags = element.get("tags", {})
    category = next((label for (k, v), label in CATEGORIES.items() if tags.get(k) == v), None)
    if category is None:
        return None
    street = " ".join(filter(None, [tags.get("addr:housenumber"), tags.get("addr:street")]))
    return {
        "catégorie": category,
        "nom": tags.get("name", ""),
        "commune": tags.get("addr:city", ""),
        "adresse": ", ".join(filter(None, [street, tags.get("addr:postcode")])),
        "téléphone": tags.get("phone") or tags.get("contact:phone", ""),
        "email": tags.get("email") or tags.get("contact:email", ""),
        "site": tags.get("website") or tags.get("contact:website", ""),
        "horaires": tags.get("opening_hours", ""),
        "osm": f"https://www.openstreetmap.org/{element['type']}/{element['id']}",
    }


def find_emails(text: str) -> list[str]:
    ignored = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", "example.com", "sentry")
    emails = {e.lower().rstrip(".") for e in EMAIL_RE.findall(text)}
    return sorted(e for e in emails if not any(bad in e for bad in ignored))


async def enrich_emails(rows: list[dict]) -> None:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    todo = [r for r in rows if r["site"] and not r["email"]]
    if not todo:
        return
    config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=20000)
    async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
        for row in todo:
            result = await crawler.arun(url=row["site"], config=config)
            if not result.success:
                continue
            emails = find_emails(result.html)
            if not emails:
                contact = next(
                    (l["href"] for l in result.links.get("internal", []) if "contact" in l.get("href", "").lower()),
                    None,
                )
                if contact:
                    page = await crawler.arun(url=contact, config=config)
                    if page.success:
                        emails = find_emails(page.html)
            if emails:
                row["email"] = ", ".join(emails[:3])
                print(f"  email trouvé : {row['nom']} -> {row['email']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("departements", nargs="*", default=["09"], help="codes département (défaut : 09)")
    parser.add_argument("-o", "--output", default="prospects.csv", help="fichier CSV de sortie")
    parser.add_argument("--enrich", action="store_true", help="chercher les emails sur les sites web (crawl4ai)")
    args = parser.parse_args()

    print(f"Recherche dans les départements : {', '.join(args.departements)}")
    rows = [r for r in map(to_row, fetch_osm(args.departements)) if r]
    order = list(CATEGORIES.values())
    rows.sort(key=lambda r: (order.index(r["catégorie"]), r["commune"], r["nom"]))
    print(f"{len(rows)} lieux trouvés")

    if args.enrich:
        asyncio.run(enrich_emails(rows))

    # Point-virgule + BOM : s'ouvre directement dans Excel en français.
    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Enregistré dans {args.output}")


if __name__ == "__main__":
    main()
