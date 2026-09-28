#!/usr/bin/env python3
"""Trouve les commerces autour d'une adresse et récupère leurs coordonnées.

Sources :
  1. OpenStreetMap (données ouvertes) : nom, adresse, téléphone, e-mail, site web.
  2. Le site web de la boutique (page d'accueil + page contact / mentions légales)
     quand OpenStreetMap n'a pas l'e-mail ou le téléphone.

Résultat : un fichier CSV (séparateur « ; ») qui s'ouvre dans Numbers ou Excel.

Exemple :
  python3 prospection_miel.py --adresse "12 rue de la Paix, 69001 Lyon" --rayon 5000
"""

import argparse
import csv
import html
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.robotparser

USER_AGENT = "prospection-miel/1.0 (outil de prospection locale)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Types de commerces OpenStreetMap susceptibles de vendre du miel.
TYPES_COMMERCES = {
    "deli": "Épicerie fine",
    "farm": "Produits de la ferme",
    "organic": "Magasin bio",
    "health_food": "Diététique / bio",
    "greengrocer": "Primeur",
    "cheese": "Fromagerie",
    "bakery": "Boulangerie",
    "pastry": "Pâtisserie",
    "confectionery": "Confiserie",
    "chocolate": "Chocolaterie",
    "tea": "Salon de thé / thés",
    "coffee": "Torréfacteur / café",
    "wine": "Cave à vin",
    "butcher": "Boucherie",
    "gift": "Boutique cadeaux",
    "convenience": "Supérette / épicerie",
    "general": "Épicerie générale",
    "supermarket": "Supermarché",
}
TYPES_PAR_DEFAUT = [t for t in TYPES_COMMERCES if t != "supermarket"]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TEL_RE = re.compile(r"(?:\+33\s?|0)[1-9](?:[\s.-]?\d{2}){4}")
LIEN_CONTACT_RE = re.compile(
    r'href=["\']([^"\']*(?:contact|mentions|legal|a-propos|apropos|about)[^"\']*)["\']',
    re.IGNORECASE,
)
EXTENSIONS_IMAGES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
EMAILS_IGNORES = ("example.", "sentry", "wixpress", "domain.", "email.com", "votre")


def telecharger(url, donnees=None, timeout=30):
    requete = urllib.request.Request(url, data=donnees, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(requete, timeout=timeout) as reponse:
        charset = reponse.headers.get_content_charset() or "utf-8"
        return reponse.read().decode(charset, errors="replace")


def geocoder(adresse):
    params = urllib.parse.urlencode({"q": adresse, "format": "json", "limit": 1})
    resultats = json.loads(telecharger(f"{NOMINATIM_URL}?{params}"))
    if not resultats:
        sys.exit(f"Adresse introuvable : {adresse}")
    return float(resultats[0]["lat"]), float(resultats[0]["lon"])


def chercher_commerces(lat, lon, rayon, types):
    filtre = "|".join(types)
    requete = f"""
    [out:json][timeout:60];
    (
      nwr["shop"~"^({filtre})$"]["name"](around:{rayon},{lat},{lon});
    );
    out center tags;
    """
    donnees = urllib.parse.urlencode({"data": requete}).encode()
    return json.loads(telecharger(OVERPASS_URL, donnees, timeout=90))["elements"]


def distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def premier_tag(tags, *cles):
    for cle in cles:
        if tags.get(cle):
            return tags[cle].split(";")[0].strip()
    return ""


def formater_adresse(tags):
    rue = " ".join(filter(None, [tags.get("addr:housenumber"), tags.get("addr:street")]))
    ville = " ".join(filter(None, [tags.get("addr:postcode"), tags.get("addr:city")]))
    return ", ".join(filter(None, [rue, ville]))


def extraire_emails(texte):
    texte = html.unescape(texte).replace("[at]", "@").replace("(at)", "@")
    emails = []
    for email in EMAIL_RE.findall(texte):
        email = email.lower().strip(".")
        if email.endswith(EXTENSIONS_IMAGES) or any(m in email for m in EMAILS_IGNORES):
            continue
        if email not in emails:
            emails.append(email)
    return emails


def extraire_telephones(texte):
    tels = []
    for tel in TEL_RE.findall(html.unescape(texte)):
        tel = re.sub(r"[\s.-]", "", tel)
        if tel not in tels:
            tels.append(tel)
    return tels


def autorise_par_robots(url, cache):
    racine = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(url))
    if racine not in cache:
        robots = urllib.robotparser.RobotFileParser(racine + "/robots.txt")
        try:
            robots.read()
        except Exception:
            robots = None
        cache[racine] = robots
    robots = cache[racine]
    return robots is None or robots.can_fetch(USER_AGENT, url)


def fouiller_site(site, robots_cache, delai):
    """Lit la page d'accueil puis quelques pages contact / mentions légales."""
    if not site.startswith("http"):
        site = "https://" + site
    pages, emails, tels = [site], [], []
    vues = set()
    while pages and len(vues) < 4:
        url = pages.pop(0)
        if url in vues or not autorise_par_robots(url, robots_cache):
            continue
        vues.add(url)
        try:
            contenu = telecharger(url, timeout=15)
        except Exception:
            continue
        emails += [e for e in extraire_emails(contenu) if e not in emails]
        tels += [t for t in extraire_telephones(contenu) if t not in tels]
        if url == site:
            for lien in LIEN_CONTACT_RE.findall(contenu)[:5]:
                lien = urllib.parse.urljoin(site, html.unescape(lien))
                if urllib.parse.urlparse(lien).netloc == urllib.parse.urlparse(site).netloc:
                    pages.append(lien)
        time.sleep(delai)
    return emails, tels


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--adresse", help="Adresse de départ (ex. « 12 rue de la Paix, Lyon »)")
    parser.add_argument("--lat", type=float, help="Latitude (à la place de --adresse)")
    parser.add_argument("--lon", type=float, help="Longitude (à la place de --adresse)")
    parser.add_argument("--rayon", type=int, default=5000, help="Rayon de recherche en mètres (défaut : 5000)")
    parser.add_argument(
        "--types",
        default=",".join(TYPES_PAR_DEFAUT),
        help="Types de commerces séparés par des virgules. Possibles : " + ", ".join(TYPES_COMMERCES),
    )
    parser.add_argument("--sortie", default="prospects_miel.csv", help="Fichier CSV à créer")
    parser.add_argument("--sans-sites", action="store_true", help="Ne pas visiter les sites web des boutiques")
    parser.add_argument("--delai", type=float, default=1.0, help="Pause en secondes entre deux pages web")
    args = parser.parse_args()

    if args.lat is not None and args.lon is not None:
        lat, lon = args.lat, args.lon
    elif args.adresse:
        lat, lon = geocoder(args.adresse)
    else:
        parser.error("indique --adresse, ou bien --lat et --lon")

    types = [t.strip() for t in args.types.split(",") if t.strip()]
    print(f"Recherche dans un rayon de {args.rayon} m autour de {lat:.5f}, {lon:.5f}…")
    elements = chercher_commerces(lat, lon, args.rayon, types)
    print(f"{len(elements)} commerces trouvés sur OpenStreetMap.")

    prospects, robots_cache = [], {}
    for i, el in enumerate(elements, 1):
        tags = el.get("tags", {})
        el_lat = el.get("lat", el.get("center", {}).get("lat"))
        el_lon = el.get("lon", el.get("center", {}).get("lon"))
        site = premier_tag(tags, "website", "contact:website", "url")
        email = premier_tag(tags, "email", "contact:email")
        tel = premier_tag(tags, "phone", "contact:phone", "contact:mobile")
        source = "OpenStreetMap"

        if site and not args.sans_sites and (not email or not tel):
            print(f"  [{i}/{len(elements)}] site de {tags['name']}…")
            emails_site, tels_site = fouiller_site(site, robots_cache, args.delai)
            if not email and emails_site:
                email, source = ", ".join(emails_site[:3]), "OpenStreetMap + site web"
            if not tel and tels_site:
                tel, source = tels_site[0], "OpenStreetMap + site web"

        prospects.append({
            "Nom": tags["name"],
            "Type": TYPES_COMMERCES.get(tags.get("shop"), tags.get("shop", "")),
            "Téléphone": tel,
            "E-mail": email,
            "Site web": site,
            "Adresse": formater_adresse(tags),
            "Distance (km)": round(distance_km(lat, lon, el_lat, el_lon), 2) if el_lat else "",
            "Horaires": tags.get("opening_hours", ""),
            "Source": source,
            "Carte": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
            "Statut": "À contacter",
            "Notes": "",
        })

    prospects.sort(key=lambda p: (p["Distance (km)"] == "", p["Distance (km)"] or 0))
    with open(args.sortie, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(prospects[0]) if prospects else ["Nom"], delimiter=";")
        writer.writeheader()
        writer.writerows(prospects)

    avec_tel = sum(1 for p in prospects if p["Téléphone"])
    avec_mail = sum(1 for p in prospects if p["E-mail"])
    print(f"\n{len(prospects)} prospects enregistrés dans {args.sortie}")
    print(f"  avec téléphone : {avec_tel}   avec e-mail : {avec_mail}")


if __name__ == "__main__":
    main()
