# Pametna košarica

Popis kupnje koji za svaki proizvod pokaže u kojoj je trgovini najjeftiniji.

- **Aplikacija:** https://claude.ai/artifact/CZQQ7Py62XqanJHkg8B8zq (privatna, otvara je samo vlasnik)
- **Trgovine:** Konzum, Lidl, Kaufland, Spar, Plodine, Eurospin, Studenac, Tommy

## Kako radi

1. `osvjezi_cijene.py` preuzme dnevnu arhivu cjenika s https://api.cijene.dev/v0
   (javni podaci koje trgovci moraju objavljivati po Odluci NN 75/2025) i napravi
   `katalog.json`: za svaki proizvod najčešću cijenu u svakom lancu, s akcijskom
   cijenom kad je proizvod na akciji.
2. `index.html` je aplikacija. Učita `katalog.json`, a popis, odabrane trgovine,
   grad i kupone sprema u bazu artefakta (dokument `kosarica/glavna`).
3. Cijene se osvježavaju jednom dnevno: zakazani zadatak pokrene skriptu (s gradom
   iz dokumenta `kosarica/glavna`) i ponovno objavi `katalog.json` uz aplikaciju.

Kuponi iz aplikacija trgovina (Lidl Plus, Kaufland Card XTRA i sl.) nisu javni, pa
ih korisnik dodaje u aplikaciji ručno ili sa snimke zaslona.

## Ručno pokretanje

```sh
python3 osvjezi_cijene.py                  # cijela Hrvatska
python3 osvjezi_cijene.py --grad Split     # samo poslovnice u Splitu
python3 osvjezi_cijene.py --zip arhiva.zip --datum 2026-11-09
```

Skripta koristi samo standardnu Python biblioteku (Python 3.9+). Arhiva ima oko
150 MB i obrada traje manje od minute.
