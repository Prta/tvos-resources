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

Cijene uz kartice vjernosti nisu u službenim cjenicima, ali ih dvije trgovine javno
objavljuju na svojim stranicama (robots.txt to dopušta):

- **Konzum MultiPlusCard**: https://www.konzum.hr/web/posebne-ponude, jedna stranica u sekundi
- **Kaufland Card XTRA**: JSON s tjednom ponudom na https://www.kaufland.hr/ponuda/pregled.html

Eurospin dio tjednih akcija ne upisuje u službeni cjenik (npr. 9. 11. 2026. trajno mlijeko
3,5% 1 l: cjenik 1,09 €, akcija 0,65 €). Te akcije skripta preuzima sa stranice
https://www.eurospin.hr/akcija/ i povezuje s cjenikom po šifri iz naziva slike proizvoda.

Skripta ih povezuje s cjenikom po šifri artikla trgovine i sprema s razdobljem
važenja; isključuje se s `--bez-kartica`.

Eurospin dio tjednih akcija ne upisuje u službeni cjenik (npr. 9. 11. 2026. trajno mlijeko
3,5% 1 l: cjenik 1,09 €, akcija 0,65 €). Te akcije skripta preuzima sa stranice
https://www.eurospin.hr/akcija/ i povezuje s cjenikom po šifri iz naziva slike proizvoda.

**Plodine Card** ponude i kupone Plodine objavljuju samo kao slike
(https://www.plodine.hr/akcije/218/plodine-card-ponude-i-kuponi). Postupak u dva koraka:

1. `--plodine-pripremi MAPA --prethodni stari_katalog.json` preuzme popis kupona, skine slike
   koje još nisu pročitane i složi ih po 6 na pregledne listove (`list_N.jpg`).
2. Netko s modelom za slike (dnevni zadatak) zapiše `MAPA/ocitano.json`:
   `[{"broj": 1, "stara": 1549, "nova": 1299, "posto": 16, "uvjet": "kupon" | "ponuda"}]`
   (cijene u centima; `stara`/`nova` su `null` kad kupon ima samo postotak).
3. `--plodine MAPA` u glavnom pokretanju poveže kupone s cjenikom: marka mora biti ista riječ,
   vrsta proizvoda i količina moraju se poklopiti, a redovna cijena s kupona smije se od cjenika
   razlikovati najviše 4%. Pročitane slike spremaju se u `plodineSlike` u katalogu, pa se
   sljedeći dan čitaju samo nove.

**Grad bez poslovnice lanca** (npr. Studenac objavljuje cjenike samo za 20 supermarketa,
nijedan u Zagrebu): uzimaju se poslovnice iz istog poštanskog područja, a ako ih nema, iz iste
regije (obala ili kontinent), prema poštanskim brojevima iz poslovnica svih lanaca.

Ostale trgovine (stanje 9. 11. 2026.): Lidl Plus, Spar, Studenac (Moj Studenac) i dio
Konzuma (MultiPlus BONUS, „Kupon po tvom” s povratom u BONUS eurima) imaju osobne kupone
samo u aplikaciji; aplikacija ih čita sa snimki zaslona (i duge snimke, izrezane na dijelove).

## Ručno pokretanje

```sh
python3 osvjezi_cijene.py                  # cijela Hrvatska
python3 osvjezi_cijene.py --grad Split     # samo poslovnice u Splitu
python3 osvjezi_cijene.py --zip arhiva.zip --datum 2026-11-09
```

Skripta koristi samo standardnu Python biblioteku (Python 3.9+). Arhiva ima oko
150 MB; obrada s preuzimanjem MultiPlusCard cijena traje oko 3 minute.
