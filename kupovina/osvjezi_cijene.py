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
import shutil
import sys
import tempfile
import unicodedata
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import date

ARCHIVE_LIST = "https://api.cijene.dev/v0/list"

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


def process_chain(archive: zipfile.ZipFile, chain: str, city: str | None):
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
            national = True  # lanac nema poslovnicu u gradu: uzmi cijene cijele Hrvatske
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


def build(zip_path: str, archive_date: str, city: str | None) -> dict:
    archive = zipfile.ZipFile(zip_path)
    names = set(archive.namelist())
    merged = defaultdict(dict)
    infos = defaultdict(dict)
    chain_meta = []
    city_stores = defaultdict(Counter)  # grad (bez dijakritika) -> pravopis -> broj poslovnica
    for idx, (code, label) in enumerate(CHAINS):
        if f"{code}/prices.csv" not in names:
            chain_meta.append({"kod": code, "naziv": label, "poslovnica": 0})
            continue
        store_count, prices, cities, national = process_chain(archive, code, city)
        for spelled, count in cities.items():
            city_stores[fold(spelled)][spelled] += count
        meta = {"kod": code, "naziv": label, "poslovnica": store_count, "proizvoda": len(prices)}
        if national:
            meta["cijelaHrvatska"] = True
        chain_meta.append(meta)
        for key, (entry, info) in prices.items():
            merged[key][idx] = entry
            infos[key][code] = info
        print(f"{label}: {store_count} poslovnica, {len(prices)} proizvoda", file=sys.stderr)

    rows = []
    for key, by_chain in merged.items():
        info_by_chain = infos[key]
        source = next(c for c in NAME_PREFERENCE + [c for c, _ in CHAINS] if c in info_by_chain)
        info = info_by_chain[source]
        name = tidy_name(info.get("name", ""))
        brand = " ".join((info.get("brand") or "").split())
        if brand and fold(brand) not in fold(name):
            name = f"{name} ({tidy_name(brand)})"
        prices = [by_chain.get(i) for i in range(len(CHAINS))]
        while prices and prices[-1] is None:
            prices.pop()
        rows.append([key, name, prices])

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
        "proizvodi": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip", help="već preuzeta arhiva (inače se preuzme najnovija)")
    parser.add_argument("--datum", help="datum arhive kad se koristi --zip (GGGG-MM-DD)")
    parser.add_argument("--grad", help="samo poslovnice u ovom gradu, npr. Zagreb")
    parser.add_argument("--izlaz", default="katalog.json", help="izlazna datoteka")
    args = parser.parse_args()

    downloaded = None
    if args.zip:
        zip_path, archive_date = args.zip, args.datum or date.today().isoformat()
    else:
        url, archive_date = latest_archive_url()
        print(f"Preuzimam {url}", file=sys.stderr)
        zip_path = downloaded = download(url)

    try:
        data = build(zip_path, archive_date, args.grad)
    finally:
        if downloaded:
            os.unlink(downloaded)  # arhiva ima oko 150 MB, ne ostavljaj je na disku
    with open(args.izlaz, "w", encoding="utf-8") as out:
        json.dump(data, out, ensure_ascii=False, separators=(",", ":"))
    print(f"Spremljeno: {args.izlaz} ({len(data['proizvodi'])} proizvoda, cijene od {archive_date})", file=sys.stderr)


if __name__ == "__main__":
    main()
