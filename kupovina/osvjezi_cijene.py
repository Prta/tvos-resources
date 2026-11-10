#!/usr/bin/env python3
"""Obrada dnevnih cjenika trgovina za aplikaciju "Pametna košarica".

Preuzme dnevnu arhivu cjenika s https://api.cijene.dev/v0 (javni podaci koje
trgovci moraju objavljivati po Odluci NN 75/2025) i napravi jednu kompaktnu
JSON datoteku (katalog.json) s cijenom svakog proizvoda u svakom lancu.

Primjeri:
    python3 osvjezi_cijene.py                       # cijela Hrvatska, danas
    python3 osvjezi_cijene.py --grad Split          # samo poslovnice u Splitu
    python3 osvjezi_cijene.py --zip 2026-11-09.zip  # već preuzeta arhiva

Cijena lanca je najčešća cijena među poslovnicama (u odabranom gradu ili u
cijeloj Hrvatskoj). Akcijska cijena se uzima kad je proizvod na akciji u barem
pola poslovnica u kojima se prodaje.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import date

ARCHIVE_LIST = "https://api.cijene.dev/v0/list"
KONZUM_OFFERS = "https://www.konzum.hr/web/posebne-ponude?page={page}&per_page=100"
KAUFLAND_OFFERS = "https://www.kaufland.hr/ponuda/pregled.html"
EUROSPIN_OFFERS = "https://www.eurospin.hr/akcija/"
PLODINE_CARD = "https://www.plodine.hr/akcije/218/plodine-card-ponude-i-kuponi"
# Riječi s Plodine kupona koje ne pomažu pri traženju proizvoda u cjeniku.
PLODINE_STOPWORDS = {"odabrane", "vrste", "ili", "proizvod", "trajni", "polutrajni", "zemlja", "podrijetla", "smrznuto"}
USER_AGENT = "PametnaKosarica/1.0 (osobna usporedba cijena; github.com/Prta/tvos-resources)"

# Redoslijed je bitan: aplikacija cijene čita po indeksu lanca.
CHAINS = [
    ("konzum", "Konzum"),
    ("lidl", "Lidl"),
    ("kaufland", "Kaufland"),
    ("spar", "Spar"),
    ("plodine", "Plodine"),
    ("eurospin", "Eurospin"),
    ("studenac", "Studenac"),
    ("tommy", "Tommy"),
]
# Poštanska područja na obali; cijene lanaca na obali često se razlikuju od kontinentalnih.
COASTAL_ZIP_PREFIXES = {"20", "21", "22", "23", "51", "52", "53"}
# Iz kojeg lanca se uzima naziv proizvoda kad ga prodaje više lanaca.
NAME_PREFERENCE = ["kaufland", "lidl", "spar", "tommy", "konzum", "studenac", "eurospin", "plodine"]


def fold(text: str) -> str:
    """Mala slova bez dijakritika, za usporedbu naziva gradova."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch)).replace("đ", "d").strip()


def cents(value: str) -> int | None:
    value = (value or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        amount = round(float(value) * 100)
    except ValueError:
        return None
    return amount if amount > 0 else None


def tidy_name(name: str) -> str:
    """Nazive pisane VELIKIM SLOVIMA pretvori u normalna slova."""
    name = " ".join(name.split())
    if name.endswith("_OC"):
        name = name[:-3].rstrip()  # Kauflandova interna oznaka
    letters = [ch for ch in name if ch.isalpha()]
    if letters and sum(ch.isupper() for ch in letters) / len(letters) > 0.8:
        name = name.lower()
        name = name[:1].upper() + name[1:]
    return name


def product_key(chain: str, product_id: str, barcode: str) -> str:
    digits = "".join(ch for ch in (barcode or "") if ch.isdigit()).lstrip("0")
    if len(digits) >= 8 and ":" not in (barcode or ""):
        return digits
    # Bez pravog EAN-a proizvod se ne može usporediti s drugim lancima.
    return f"{chain}:{product_id}"


def open_csv(archive: zipfile.ZipFile, path: str):
    return csv.DictReader(io.TextIOWrapper(archive.open(path), encoding="utf-8", newline=""))


def latest_archive_url() -> tuple[str, str]:
    with urllib.request.urlopen(ARCHIVE_LIST, timeout=60) as resp:
        archives = json.load(resp)["archives"]
    newest = max(archives, key=lambda a: a["date"])
    return newest["url"], newest["date"]


def download(url: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    with urllib.request.urlopen(url, timeout=600) as resp, tmp:
        shutil.copyfileobj(resp, tmp, length=1 << 20)
    return tmp.name


def fetch_konzum_card_prices(delay: float = 1.0, max_pages: int = 60) -> dict:
    """MultiPlusCard cijene s Konzumove stranice "Posebne ponude".

    Službeni cjenici ne sadrže cijene uz karticu vjernosti, ali ih Konzum javno
    prikazuje uz proizvode na akciji. Vraća {konzum_product_id: [(centi, od, do)]},
    datumi su "GGGG-MM-DD" ili "".
    """
    found = {}
    for page in range(1, max_pages + 1):
        req = urllib.request.Request(KONZUM_OFFERS.format(page=page), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8", "replace")
        tiles = text.split('<article class="product-item')[1:]
        new = 0
        for tile in tiles:
            pid = re.search(r'data-ga-id="([^"]+)"', tile)
            card = re.search(r'MultiPlusCard cijena:\s*<strong>\s*([\d.,]+)\s*€', tile)
            if not pid or not card or pid.group(1) in found:
                continue
            amount = card.group(1)
            if "," in amount:
                amount = amount.replace(".", "")
            until = re.search(r'Vrijedi do:\s*<strong>\s*(\d{1,2})\.(\d{1,2})\.(\d{4})', tile)
            until_iso = f"{until.group(3)}-{int(until.group(2)):02d}-{int(until.group(1)):02d}" if until else ""
            price = cents(amount)
            if price:
                found[pid.group(1)] = [(price, "", until_iso)]
                new += 1
        if not tiles or (new == 0 and page > 1 and not any("MultiPlusCard cijena" in t for t in tiles)):
            break
        time.sleep(delay)  # pristojan razmak između zahtjeva
    return found


def fetch_kaufland_card_prices() -> dict:
    """Cijene uz Kaufland Card XTRA iz podataka stranice s tjednom ponudom.

    Stranica sadrži JSON s ponudama ovog i sljedećeg tjedna; ponude uz karticu imaju
    polje loyaltyFormattedPrice. Vraća {kaufland_artikl: [(centi, od, do), ...]}.
    """
    req = urllib.request.Request(KAUFLAND_OFFERS, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as resp:
        text = resp.read().decode("utf-8", "replace")
    anchor = text.find('"offerData":')
    if anchor < 0:
        raise ValueError("na stranici nema podataka o ponudi")
    decoder = json.JSONDecoder()
    data, pos = None, anchor
    for _ in range(5000):  # traži objekt koji sadrži "offerData"
        pos = text.rfind("{", 0, pos)
        if pos < 0:
            break
        try:
            obj, _ = decoder.raw_decode(text, pos)
        except ValueError:
            continue
        if isinstance(obj, dict) and "offerData" in obj:
            data = obj
            break
    if data is None:
        raise ValueError("podaci o ponudi se ne mogu pročitati")
    found = defaultdict(set)
    for cycle in data["offerData"].get("cycles", []):
        for category in cycle.get("categories", []):
            for offer in category.get("offers", []):
                card = offer.get("loyaltyFormattedPrice")
                article = offer.get("klNr")
                if not card or not article:
                    continue
                price = cents(card.replace("€", "").strip())
                if price:
                    found[article].add((price, offer.get("dateFrom") or "", offer.get("dateTo") or ""))
    return {article: sorted(periods, key=lambda p: p[1]) for article, periods in found.items()}


def fetch_eurospin_offers() -> dict:
    """Tjedne akcije s Eurospinove stranice "Akcija".

    Eurospin dio tjednih akcija ne upisuje u službeni cjenik (npr. 9. 11. 2026. trajno
    mlijeko 3,5% 1 l: cjenik 1,09 €, akcija 0,65 €). Stranica uz svaku akciju ima
    sliku nazvanu po šifri proizvoda (".../smt/12111901.jpg" = šifra "012111901").
    Vraća {eurospin_product_id: [(centi, od, do)]}.
    """
    req = urllib.request.Request(EUROSPIN_OFFERS, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8", "replace")
    today = date.today()

    def day(d: str, m: str) -> str:
        when = date(today.year, int(m), int(d))
        if (when - today).days < -180:  # akcija preko Nove godine
            when = date(today.year + 1, int(m), int(d))
        elif (when - today).days > 180:
            when = date(today.year - 1, int(m), int(d))
        return when.isoformat()

    found = defaultdict(set)
    for item in text.split('class="sn_promo_grid_item"')[1:]:
        dates = re.search(r'date_current_promo">\s*(\d{1,2})\.(\d{1,2})\.\s*-\s*(\d{1,2})\.(\d{1,2})\.', item)
        image = re.search(r'/smt/(\d+)\.(?:jpe?g|png|webp)', item)
        price = re.search(r'itemprop="price">\s*€\s*([\d.,]+)', item)
        if not (dates and image and price):
            continue
        amount = price.group(1)
        if "," in amount:
            amount = amount.replace(".", "")
        cents_value = cents(amount)
        if cents_value:
            period = (cents_value, day(dates.group(1), dates.group(2)), day(dates.group(3), dates.group(4)))
            found[image.group(1).zfill(9)].add(period)
    return {pid: sorted(periods, key=lambda p: p[1]) for pid, periods in found.items()}


def city_zip_prefixes(archive: zipfile.ZipFile, names: set) -> dict:
    """Prve dvije znamenke poštanskog broja za svaki grad, iz poslovnica svih lanaca."""
    seen = defaultdict(Counter)
    for code, _ in CHAINS:
        if f"{code}/stores.csv" not in names:
            continue
        for row in open_csv(archive, f"{code}/stores.csv"):
            zipcode = (row.get("zipcode") or "").strip()
            if len(zipcode) == 5 and zipcode.isdigit() and row.get("city", "").strip():
                seen[fold(row["city"])][zipcode[:2]] += 1
    return {city: counts.most_common(1)[0][0] for city, counts in seen.items()}


def nearby_stores(stores: dict, city: str, prefixes: dict) -> tuple[dict, str]:
    """Poslovnice najbliže gradu bez vlastite poslovnice: isto poštansko područje, inače ista regija."""
    target = prefixes.get(fold(city))
    if not target:
        return {}, ""
    def prefix(store):
        return prefixes.get(fold(store.get("city", "")))
    same_area = {sid: s for sid, s in stores.items() if prefix(s) == target}
    if same_area:
        return same_area, "područje"
    coastal = target in COASTAL_ZIP_PREFIXES
    same_region = {sid: s for sid, s in stores.items()
                   if prefix(s) and (prefix(s) in COASTAL_ZIP_PREFIXES) == coastal}
    return same_region, ("obala" if coastal else "kontinent") if same_region else ""


def fetch_plodine_card_items() -> list:
    """Kuponi s Plodine Card stranice; cijena je samo na slici kupona."""
    req = urllib.request.Request(PLODINE_CARD, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8", "replace")
    items = []
    for card in text.split('<article class="card')[1:]:
        image = re.search(r'class="card__img"[^>]*src="([^"]+)"', card)
        title = re.search(r'class="card__title">([^<]*)<', card)
        desc = re.search(r'class="card__description">([^<]*)<', card)
        qty = re.search(r'class="card__quantity">([^<]*)<', card)
        if not image:
            continue
        clean = lambda m: " ".join(html_unescape(m.group(1)).split()) if m else ""
        items.append({"slika": image.group(1), "naslov": clean(title), "opis": clean(desc), "kolicina": clean(qty)})
    return items


def parse_quantity(text: str, anywhere: bool = False):
    """Količina u osnovnoj jedinici: "0,7 l" -> (700, "ml"), "1 kg" -> (1000, "g"). Raspone ne čita."""
    text = fold(text).replace(",", ".")
    pattern = r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\b"
    m = re.search(pattern, text) if anywhere else re.fullmatch(r"\s*" + pattern + r"\s*", text)
    if not m or re.search(r"\d\s*-\s*\d", text if not anywhere else m.group(0)):
        return None
    value, unit = float(m.group(1)), m.group(2)
    return (value * 1000, "g") if unit == "kg" else (value * 1000, "ml") if unit == "l" else (value, unit)


def is_sold_by_weight(info: dict, name: str) -> bool:
    """Roba na vagu: jedinica kg, količina 1 kg ili prazna, a naziv nema količinu."""
    unit = fold(info.get("unit") or "").replace(" ", "")
    if unit not in ("kg", "1kg") or parse_quantity(name, anywhere=True):
        return False
    qty = fold(info.get("quantity") or "").replace(" ", "").replace(",", ".").replace("kg", "")
    try:
        return qty == "" or abs(float(qty) - 1) < 1e-6
    except ValueError:
        return False


def html_unescape(value: str) -> str:
    import html
    return html.unescape(value)


def prepare_plodine(directory: str, previous: str | None) -> None:
    """Pripremi Plodine kupone za čitanje: popis, slike koje još nisu pročitane i pregledne listove."""
    os.makedirs(directory, exist_ok=True)
    cache = {}
    if previous and os.path.exists(previous):
        with open(previous, encoding="utf-8") as f:
            cache = json.load(f).get("plodineSlike", {})
    items = fetch_plodine_card_items()
    todo = [it for it in items if it["slika"] not in cache]
    with open(os.path.join(directory, "popis.json"), "w", encoding="utf-8") as f:
        json.dump({"kuponi": items, "procitano": {k: v for k, v in cache.items() if any(i["slika"] == k for i in items)}},
                  f, ensure_ascii=False, indent=1)
    for n, it in enumerate(todo, 1):
        it["broj"] = n
        req = urllib.request.Request(it["slika"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp, open(os.path.join(directory, f"kupon_{n:02d}.jpg"), "wb") as out:
            out.write(resp.read())
        time.sleep(0.3)
    with open(os.path.join(directory, "za_citanje.json"), "w", encoding="utf-8") as f:
        json.dump(todo, f, ensure_ascii=False, indent=1)
    sheets = make_contact_sheets(directory, len(todo))
    print(f"Plodine Card: {len(items)} kupona, {len(todo)} novih za čitanje, listova: {sheets}", file=sys.stderr)


def make_contact_sheets(directory: str, count: int, per_sheet: int = 6) -> int:
    """Složi slike kupona po 6 na jedan list s brojem, da se pročitaju odjednom (treba Pillow)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return 0
    sheets = 0
    for start in range(1, count + 1, per_sheet):
        numbers = list(range(start, min(count, start + per_sheet - 1) + 1))
        cell = 540
        sheet = Image.new("RGB", (cell * 3, cell * ((len(numbers) + 2) // 3)), "white")
        draw = ImageDraw.Draw(sheet)
        for i, n in enumerate(numbers):
            img = Image.open(os.path.join(directory, f"kupon_{n:02d}.jpg")).convert("RGB")
            img.thumbnail((cell, cell))
            x, y = (i % 3) * cell, (i // 3) * cell
            sheet.paste(img, (x, y))
            draw.rectangle([x, y, x + 70, y + 50], fill="black")
            draw.text((x + 12, y + 8), f"#{n}", fill="white", font_size=32)
        sheets += 1
        sheet.save(os.path.join(directory, f"list_{sheets}.jpg"), quality=88)
    return sheets


def plodine_card_prices(directory: str, archive: zipfile.ZipFile, merged: dict, infos: dict) -> tuple[dict, dict]:
    """Poveži pročitane Plodine kupone s cjenikom: ista marka/naziv i ista redovna cijena kao na kuponu."""
    with open(os.path.join(directory, "popis.json"), encoding="utf-8") as f:
        listing = json.load(f)
    readings = dict(listing.get("procitano", {}))
    new_path = os.path.join(directory, "ocitano.json")
    todo_path = os.path.join(directory, "za_citanje.json")
    if os.path.exists(new_path) and os.path.exists(todo_path):
        with open(todo_path, encoding="utf-8") as f:
            todo = {it["broj"]: it["slika"] for it in json.load(f)}
        with open(new_path, encoding="utf-8") as f:
            for r in json.load(f):
                url = todo.get(r.get("broj"))
                if url:
                    readings[url] = {k: r.get(k) for k in ("stara", "nova", "posto", "uvjet")}
    idx = [c for c, _ in CHAINS].index("plodine")
    candidates = [(key, fold(infos[key]["plodine"].get("name", "") + " " + (infos[key]["plodine"].get("brand") or "")))
                  for key, by_chain in merged.items() if idx in by_chain and "plodine" in infos[key]]
    prices, kept = {}, {}
    for it in listing["kuponi"]:
        r = readings.get(it["slika"])
        if not r:
            continue
        kept[it["slika"]] = r
        old, new, pct = r.get("stara"), r.get("nova"), r.get("posto")
        percent_only = old is None and new is None and isinstance(pct, (int, float)) and 0 < pct < 100
        if not percent_only:
            if not isinstance(new, int) or not isinstance(old, int) or not 0 < new < old:
                continue
            if isinstance(pct, (int, float)) and abs(old * (100 - pct) / 100 - new) > 6:
                print(f"  Plodine: izračun se ne slaže, preskačem {it['opis']} ({old}, {new}, {pct}%)", file=sys.stderr)
                continue
        words = lambda text: [w for w in re.findall(r"[a-z0-9]+", fold(text)) if len(w) >= 3 and w not in PLODINE_STOPWORDS]
        brand = words(it["opis"])[:2]
        kinds = words(it["naslov"])[:4]
        if not brand and not kinds:
            continue
        qty = parse_quantity(it["kolicina"])
        matched = []
        for key, name in candidates:
            name_words = set(re.findall(r"[a-z0-9]+", name))
            # Marka mora biti ista riječ (dopušten je zadnji znak: "Gligora" ~ "gligor"), ne samo početak
            # ("Aromar" nije "aromatizirana").
            same_word = lambda b: any(x == b or (len(b) >= 5 and abs(len(x) - len(b)) <= 1 and x[:len(b) - 1] == b[:len(b) - 1])
                                      for x in name_words)
            # Vrsta proizvoda: "keksi" ~ "keks", "pileca" ne ~ "pile", kratke riječi ("gel", "sir") cijele.
            kind = lambda k: k in name_words if len(k) <= 3 else any(x.startswith(k[:5 if len(k) >= 6 else 4]) for x in name_words)
            if brand and not any(same_word(b) for b in brand):
                continue
            # Vrsta proizvoda mora se poklopiti (marka sama nije dovoljna: PIK radi i Debrecinku i Tirolsku),
            # osim kad je u samom nazivu proizvoda puni naziv s kupona od barem dvije riječi i ista
            # količina ("Amaro 18 Isolabella 0,7 l"; kod raspona "300-440 g" količina nije poznata).
            own_name = set(re.findall(r"[a-z0-9]+", fold(infos[key]["plodine"].get("name", ""))))
            full_name_match = len(brand) >= 2 and all(b in own_name for b in brand) and qty is not None
            if kinds and not full_name_match and not (any(kind(k) for k in kinds) if brand else all(kind(k) for k in kinds[:2])):
                continue
            if qty:  # ista količina kao na kuponu, ako je cjenik navodi
                info = infos[key]["plodine"]
                have = parse_quantity(f"{info.get('quantity', '')}") or parse_quantity(info.get("name", ""), anywhere=True)
                if have and (have[1] != qty[1] or abs(have[0] - qty[0]) > qty[0] * 0.01):
                    continue
            current = merged[key][idx]
            base = current[1] if isinstance(current, list) else current
            final = current[0] if isinstance(current, list) else current
            if percent_only:
                matched.append((key, round(final * (100 - pct) / 100)))
            elif abs(base - old) <= old * 0.04 and new < final:
                # Redovna cijena s kupona mora odgovarati cjeniku (cijene se malo razlikuju po poslovnici).
                matched.append((key, new))
        if not matched:
            what = f"cijenom {old/100:.2f}" if old else "markom"
            print(f"  Plodine: nema proizvoda s {what} za {it['opis'] or it['naslov']} {it['kolicina']}", file=sys.stderr)
        activate = ["kupon"] if r.get("uvjet") == "kupon" else []  # "Aktiviraj kupon" u aplikaciji
        for key, price in matched[:15 if percent_only else 8]:
            prices[key] = [[price, "", ""] + activate]
    return prices, kept


def process_chain(archive: zipfile.ZipFile, chain: str, city: str | None, prefixes: dict | None = None):
    stores = {}
    for row in open_csv(archive, f"{chain}/stores.csv"):
        stores[row["store_id"]] = row
    cities = Counter(" ".join(s.get("city", "").split()) for s in stores.values() if s.get("city", "").strip())
    national = False
    if city:
        wanted = fold(city)
        in_city = {sid: s for sid, s in stores.items() if fold(s.get("city", "")).startswith(wanted)}
        if in_city:
            stores = in_city
        else:
            # Lanac nema poslovnicu u gradu: uzmi najbliže područje, a ako ga nema, cijelu Hrvatsku.
            near, _ = nearby_stores(stores, city, prefixes or {})
            if near:
                stores = near
                national = sorted({" ".join(s.get("city", "").split()).title() for s in near.values()})
            else:
                national = True
    if not stores:
        return 0, {}, cities, national

    products = {}
    for row in open_csv(archive, f"{chain}/products.csv"):
        products[row["product_id"]] = row

    effective = defaultdict(Counter)   # proizvod -> najčešća konačna cijena
    regular = defaultdict(Counter)     # proizvod -> redovna cijena kad je na akciji
    on_sale = Counter()
    seen = defaultdict(set)
    for row in open_csv(archive, f"{chain}/prices.csv"):
        sid = row["store_id"]
        if sid not in stores or row.get("available") == "0":
            continue
        pid = row["product_id"]
        if sid in seen[pid]:
            continue  # neki lanci isti redak objave više puta
        price = cents(row["price"])
        special = cents(row["special_price"])
        if price is None and special is None:
            continue
        seen[pid].add(sid)
        final = min(p for p in (price, special) if p is not None)
        effective[pid][final] += 1
        if special is not None:
            on_sale[pid] += 1
            before = max(p for p in (price, cents(row["best_price_30"]), 0) if p is not None)
            if before > special:
                regular[pid][before] += 1

    result = {}
    for pid, counts in effective.items():
        info = products.get(pid)
        if not info:
            continue
        final = counts.most_common(1)[0][0]
        store_count = len(seen[pid])
        # Cijena u centima, ili [akcijska, redovna] kad je proizvod na akciji.
        entry = final
        if on_sale[pid] * 2 >= store_count and regular[pid]:
            before = regular[pid].most_common(1)[0][0]
            if before > final:
                entry = [final, before]
        key = product_key(chain, pid, info.get("barcode", ""))
        result[key] = (entry, info)
    return len(stores), result, cities, national


def build(zip_path: str, archive_date: str, city: str | None, card_sources: dict | None = None,
          plodine_dir: str | None = None) -> dict:
    archive = zipfile.ZipFile(zip_path)
    names = set(archive.namelist())
    merged = defaultdict(dict)
    infos = defaultdict(dict)
    chain_meta = []
    city_stores = defaultdict(Counter)  # grad (bez dijakritika) -> pravopis -> broj poslovnica
    prefixes = city_zip_prefixes(archive, names) if city else {}
    for idx, (code, label) in enumerate(CHAINS):
        if f"{code}/prices.csv" not in names:
            chain_meta.append({"kod": code, "naziv": label, "poslovnica": 0})
            continue
        store_count, prices, cities, national = process_chain(archive, code, city, prefixes)
        for spelled, count in cities.items():
            city_stores[fold(spelled)][spelled] += count
        meta = {"kod": code, "naziv": label, "poslovnica": store_count, "proizvoda": len(prices)}
        if national is True:
            meta["cijelaHrvatska"] = True
        elif national:
            meta["zamjenskiGradovi"] = national  # poslovnice iz najbližeg područja
        chain_meta.append(meta)
        for key, (entry, info) in prices.items():
            merged[key][idx] = entry
            infos[key][code] = info
        print(f"{label}: {store_count} poslovnica, {len(prices)} proizvoda", file=sys.stderr)

    # Cijene uz kartice vjernosti i akcije sa stranica trgovina koje nisu u cjeniku:
    # {kod: [[centi, od, do], ...]}, samo kad su niže od cijene iz cjenika.
    cards = []
    plodine_cache = {}
    chain_codes = [c for c, _ in CHAINS]
    for chain, (card_name, by_article, for_everyone) in (card_sources or {}).items():
        if not by_article or f"{chain}/products.csv" not in names:
            continue
        idx = chain_codes.index(chain)
        id_to_key = {row["product_id"]: product_key(chain, row["product_id"], row.get("barcode", ""))
                     for row in open_csv(archive, f"{chain}/products.csv")}
        card_prices = {}
        for article, periods in by_article.items():
            key = id_to_key.get(article)
            current = merged.get(key, {}).get(idx) if key else None
            if current is None:
                continue
            final = current[0] if isinstance(current, list) else current
            lower = [list(p) for p in periods if p[0] < final]
            if lower:
                card_prices[key] = lower
        source = {"lanac": chain, "naziv": card_name, "cijene": card_prices}
        if for_everyone:
            source["svi"] = True  # akcija za sve kupce, ne treba kartica
        cards.append(source)
        print(f"{card_name}: {len(by_article)} cijena na stranici, {len(card_prices)} povezano s cjenikom", file=sys.stderr)

    if plodine_dir and "plodine/products.csv" in names:
        try:
            prices, kept = plodine_card_prices(plodine_dir, archive, merged, infos)
            cards.append({"lanac": "plodine", "naziv": "Plodine Card", "cijene": prices})
            plodine_cache.update(kept)
            print(f"Plodine Card: {len(kept)} pročitanih kupona, {len(prices)} proizvoda povezano s cjenikom", file=sys.stderr)
        except Exception as exc:
            print(f"Upozorenje: Plodine Card kuponi nisu obrađeni ({exc})", file=sys.stderr)

    rows = []
    brands, brand_index = [], {}
    junk_brands = {"", "#", "-", "no brand", "nobrand", "n/a", "ostalo", "razno", "vlastite potrebe"}
    for key, by_chain in merged.items():
        info_by_chain = infos[key]
        source = next(c for c in NAME_PREFERENCE + [c for c, _ in CHAINS] if c in info_by_chain)
        info = info_by_chain[source]
        name = tidy_name(info.get("name", ""))
        if is_sold_by_weight(info, name):
            name = re.sub(r"\s+kg$", "", name, flags=re.I) + " /kg"  # na vagu: cijena je po kilogramu (npr. svježe banane)
        brand = " ".join((info.get("brand") or "").split())
        if brand and fold(brand) not in fold(name):
            name = f"{name} ({tidy_name(brand)})"
        prices = [by_chain.get(i) for i in range(len(CHAINS))]
        while prices and prices[-1] is None:
            prices.pop()
        row = [key, name, prices]
        # Marka (proizvođač) za grupiranje u aplikaciji: indeks u popisu "marke".
        nice = tidy_name(brand) if brand and fold(brand) not in junk_brands else ""
        if nice:
            if nice not in brand_index:
                brand_index[nice] = len(brands)
                brands.append(nice)
            row.append(brand_index[nice])
        rows.append(row)

    # Proizvodi koje prodaje više lanaca prvi, jer se njih najviše isplati uspoređivati.
    rows.sort(key=lambda r: (-sum(p is not None for p in r[2]), fold(r[1])))
    cities = []
    for spellings in city_stores.values():
        # Pravopis s dijakriticima i normalnim velikim slovima ima prednost pred "ZAGREB".
        best = max(spellings, key=lambda c: (not c.isupper(), any(ord(ch) > 127 for ch in c), spellings[c]))
        cities.append([best, sum(spellings.values())])
    cities.sort(key=lambda c: (-c[1], fold(c[0])))
    return {
        "datum": archive_date,
        "grad": city or "",
        "lanci": chain_meta,
        "gradovi": cities,
        "kartice": cards,
        "plodineSlike": plodine_cache,  # već pročitane slike kupona, da se sutra ne čitaju opet
        "marke": brands,
        "proizvodi": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip", help="već preuzeta arhiva (inače se preuzme najnovija)")
    parser.add_argument("--datum", help="datum arhive kad se koristi --zip (GGGG-MM-DD)")
    parser.add_argument("--grad", help="samo poslovnice u ovom gradu, npr. Zagreb")
    parser.add_argument("--izlaz", default="katalog.json", help="izlazna datoteka")
    parser.add_argument("--plodine-pripremi", metavar="MAPA",
                        help="samo pripremi Plodine Card kupone za čitanje (popis, slike, listovi) i završi")
    parser.add_argument("--plodine", metavar="MAPA", help="mapa s pročitanim Plodine Card kuponima")
    parser.add_argument("--prethodni", metavar="KATALOG", help="prethodni katalog.json (već pročitani Plodine kuponi)")
    parser.add_argument("--bez-kartica", action="store_true",
                        help="ne preuzimaj cijene uz kartice vjernosti ni akcije sa stranica trgovina")
    args = parser.parse_args()

    if args.plodine_pripremi:
        prepare_plodine(args.plodine_pripremi, args.prethodni)
        return

    card_sources = {}
    if not args.bez_kartica:
        for chain, card_name, fetch, for_everyone in (
            ("konzum", "MultiPlusCard", fetch_konzum_card_prices, False),
            ("kaufland", "Kaufland Card XTRA", fetch_kaufland_card_prices, False),
            ("eurospin", "Eurospin akcija", fetch_eurospin_offers, True),
        ):
            try:
                card_sources[chain] = (card_name, fetch(), for_everyone)
            except Exception as exc:  # stranice trgovina nisu obvezne, cjenici rade i bez njih
                print(f"Upozorenje: {card_name} cijene nisu preuzete ({exc})", file=sys.stderr)

    downloaded = None
    if args.zip:
        zip_path, archive_date = args.zip, args.datum or date.today().isoformat()
    else:
        url, archive_date = latest_archive_url()
        print(f"Preuzimam {url}", file=sys.stderr)
        zip_path = downloaded = download(url)

    try:
        data = build(zip_path, archive_date, args.grad, card_sources, args.plodine)
    finally:
        if downloaded:
            os.unlink(downloaded)  # arhiva ima oko 150 MB, ne ostavljaj je na disku
    with open(args.izlaz, "w", encoding="utf-8") as out:
        json.dump(data, out, ensure_ascii=False, separators=(",", ":"))
    print(f"Spremljeno: {args.izlaz} ({len(data['proizvodi'])} proizvoda, cijene od {archive_date})", file=sys.stderr)


if __name__ == "__main__":
    main()
