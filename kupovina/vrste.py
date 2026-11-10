"""Vrsta proizvoda (voće, povrće, meso, ...) prema nazivu i zakonskoj kategoriji iz cjenika.

Cjenici imaju samo šest zakonskih kategorija (hrana, piće, kozmetika, sredstva za čišćenje,
proizvodi za kućanstvo, toaletne potrepštine). Finije vrste hrane određuju se po riječima u
nazivu; pravila se provjeravaju redom i prvo koje odgovara odlučuje (npr. "jogurt s bananom"
je mliječni proizvod, a ne voće, jer su mliječni proizvodi prije voća).
"""
from __future__ import annotations

import re

# Redoslijed u aplikaciji.
VRSTE = [
    "Voće", "Povrće", "Meso", "Riba i plodovi mora", "Naresci i kobasice", "Mliječni proizvodi i jaja",
    "Kruh i peciva", "Tjestenina, riža i brašno", "Ulje, umaci i začini", "Konzerve i gotova jela",
    "Namazi i paštete", "Kava, čaj i kakao", "Slatkiši i grickalice", "Smrznuto", "Pića", "Za bebe",
    "Kućni ljubimci", "Higijena i kozmetika", "Čišćenje", "Kućanstvo",
]


def _rx(*words: str) -> re.Pattern:
    """Riječi koje moraju početi na granici riječi; '=' na kraju znači cijelu riječ."""
    parts = []
    for w in words:
        if w.endswith("="):
            parts.append(re.escape(w[:-1]) + r"(?![a-z])")
        else:
            parts.append(re.escape(w))
    return re.compile(r"(?<![a-z])(" + "|".join(parts) + ")")


# (vrsta, uzorak) - provjerava se redom. Prva pravila su "jaki" znakovi koji nadjačavaju okus ili
# sastojak u nazivu (npr. "kokošja kocka" je začin, "pileća pašteta" namaz, "vafel s kakaom" slatkiš).
# Prazna vrsta znači: ne svrstavaj (npr. vitamini).
FOOD_RULES = [
    ("Kućni ljubimci", _rx("za pse=", "za macke=", "za mace", "za mac.", "za psa=", "macj", "pseci", "pseca", "pedigr",
                           "whiskas", "kitekat", "gourmet=", "mm gold", "za ps.", "hrana za ps", "felix=", "friskies", "purina", "sheba=", "perfect fit", "dentastix",
                           "cesar=", "darling=", "gourmet gold", "bellosan", "mila's world", "posl.za pse",
                           "posl za pse", "hrana za pse", "hrana za mac", "pijesak za mac", "brit=")),
    ("Za bebe", _rx("kasic", "djecja hrana", "djec.hrana", "hrana djec", "djecji obrok", "hipp=", "hippis", "nan=", "optipro", "bebivita",
                    "bebimil", "adaptirano", "aptamil", "mlijecna formula", "frutek", "pelen", "babylove", "pampers",
                    "huggies", "lupilu", "pouch", "kasa voc", "frutolino")),
    ("Smrznuto", _rx("smrznut", "zamrznut", "smrz.", "smrz=", "sladoled", "slado", "slad.", "ledene kocke", "quattro", "sorbet", "strukl", "proljetne rolice", "pakirani led", "frozen", "pommes", "pom frit",
                     "riblji stapic", "corneto", "cornetto", "magnum=", "ledo=")),
    ("Pića", _rx("ledeni caj", "ice tea", "icetea", "ice coffee", "cedevita", "smoothie", "smoot.")),
    ("Slatkiši i grickalice", _rx("vafel", "vafl", "napolitank", "keks", "kolac", "biskvit", "pillows", "jastuc",
                                  "bombon", "strudl", "zv. gum", "zv.gum", "zvakac", "zvakac", "zele=", "cajno pecivo",
                                  "cajni kolut", "slano pecivo", "kolutic", "napolit", "croissant", "kroasan", "rolino", "bobi=",
                                  "gum.bomb", "bomb.", "karamel", "zvakanj", "prekrasni", "7 day", "makovnjac", "orehnjac", "buhtl", "madeleine", "rahat", "mozart",
                                  "gummi", "mallow", "pringles", "bake rolls", "mogyi", "korneti", "after eight", "plazma", "rolsi", "pez=", "knoppers", "medenja",
                                  "doritos", "chupa", "fisherman", "brownie", "panettone", "pandoro", "frutiguti",
                                  "karemel", "liz.", "vjencic", "kuglice")),
    ("", _rx("vitamin", "multivita", "magnezij", "tab.sum", "tabl.sum", "sumece=", "dodatak prehrani", "proteini.si", "tinktura", "creatin", "kreatin",
         "polleo", "prot.shake")),
    ("Konzerve i gotova jela", _rx("rio mare", "eva=", "delamaris", "tuna salata", "tuna u ", "tunjevina u", "komadi tune",
                                   "u biljnom ulju", "u bilj. ulju", "u suncokretovom ulju", "u maslinovom ulju", "u ulju",
                                   "talianetta", "noodle", "u casi", "mesni dorucak", "mesni ragu", "gulas goved",
                                   "govedi gulas", "juha", "juhe=", "instant juh", "kompot", "punjena paprik",
                                   "punjene paprik", "carnex", "sarma", "varivo", "grah s", "grah sa", "ragu=", "fileki", "tripice", "komp.", "duvec", "hase=", "hase ", "pizza", "pizze")),
    ("Ulje, umaci i začini", _rx("zacin", "kotanyi", "fant=", "vegeta", "kocka=", "kocke za juhu", "hren=", "polpa",
                                 "mutti", "temeljac", "dodatak jelima", "maggi", "umak za", "kotany", "tartuf", "pasir", "uma.", "majon", "salsa", "dod. jel", "mayonnaise",
                                 "tartar", "garam masala", "um.", "pelat", "feferon")),
    ("Namazi i paštete", _rx("pasteta", "pastet", "namaz", "nam.", "pate=", "puter", "apimel", "marm.")),
    ("Mliječni proizvodi i jaja", _rx("top.listic", "toast top", "topljeni sir", "sir u listic", "mlijec.", "yopro", "skyr", "sirana", "alpro", "sirutka",
                                      "burrata", "gauda", "zott")),
    ("Tjestenina, riža i brašno", _rx("prasak za pec", "kvasac", "limunska kiselina", "aroma=", "konzervans", "dolcela",
                                      "tjesten", "tjest.", "tortel", "raviol", "njok", "spaget", "spaghett", "krupica",
                                      "krema za", "kremfix", "dr.oetker", "dr. oetker", "cokolino", "lino crunch",
                                      "rizolino", "zitne pahulj", "medolino", "cheerios", "nestle fitness", "pasutic",
                                      "fuzi", "krpice", "bucatini", "chifferi", "ruote", "tj.", "tj=", "bulgur",
                                      "lisnato tij", "tijesto", "oblatn", "bras.", "brasn", "soda bikarbon",
                                      "mafalde", "svrdla", "skoljkic", "tjes.", "granola", "cini minis", "oras.",
                                      "orasc", "orasi")),
    ("Kava, čaj i kakao", _rx("kava=", "kave=", "kavu=", "kavom=", "coffee", "espresso", "cappuc", "capuc", "nescafe",
                              "jacobs", "barcaffe", "franck", "caj=", "caja=", "cajevi", "tea=", "kakao",
                              "kapsule za kav", "ledena kava", "lavazza", "kap.", "kapsul", "nesquik", "kavovina", "cikorij")),
    ("Slatkiši i grickalice", _rx("cokol", "coko", "choco", "cok.", "cok=", "praline", "linzer", "bombonijer", "torta",
                                  "tortica", "rolad", "desert", "kinder", "milka", "twix", "snickers", "mars=", "bounty",
                                  "oreo", "haribo", "gumene", "gumioza", "zozole", "bananko", "domacica", "jaffa",
                                  "petit beurre", "kreker", "stapic", "perec", "musli plocic", "proteinska plocic",
                                  "plocic", "croissant", "kroasan", "cips", "chips", "flips", "smoki", "kroki", "grickal",
                                  "gric=", "kikiriki", "pistac", "lizalic", "duplo=", "kitkat", "kit kat", "raffael",
                                  "bajadera", "ferrero", "kviki", "lion=", "airwaves", "orbit=", "tic tac", "drazej",
                                  "rondo=", "ki-ki", "kiki=", "tutti frutti", "nacho", "chio", "bruschett", "maretti",
                                  "snack", "pomsticks", "pom-bar", "express=", "elephant", "nesquik bar", "medenjak",
                                  "lizal", "mentol", "kokic", "corny", "griotte", "hubba", "ploc.", "napol.")),
    ("Pića", _rx("sok=", "sokovi", "nektar", "voda=", "vode=", "mineraln", "gazirana", "negazirana", "pivo", "piva=",
                 "vino", "vina=", "rakij", "liker", "votk", "vodk", "gin=", "whisk", "viski", "rum=", "konjak",
                 "brand=", "brandy", "kruskovac", "visnjevac", "orahovac", "travaric", "sljivovic", "aperol", "radler",
                 "cider", "spritz", "nap.", "shake", "starbucks", "estate", "grasevina", "malvazij", "merlot",
                 "cabernet", "chardonnay", "plavac", "frankovka", "pinot", "teran", "babic", "posip", "zlahtina",
                 "traminac", "rizling", "cola", "pepsi", "fanta", "sprite", "schweppes", "napitak", "sirup",
                 "energetsk", "red bull", "jamnica", "jana=", "studena", "pelinkovac", "gemist", "prosecco", "sampanj")),
    ("Konzerve i gotova jela", _rx("konzerva", "konzerve=", "konzervir", "gotovo jelo", "gotova jela", "pasulj",
                                   "jelo u", "podravka jelo", "gulas u", "lunch", "pizza", "pizze", "salata s",
                                   "gotova salata")),
    ("Naresci i kobasice", _rx("sunk", "salam", "kulen", "prsut", "mortadel", "hrenov", "kobasic", "kob.", "kob=",
                               "slanin", "panceta", "pancet", "narezak", "pecenic", "kranjsk", "debrecin", "budol",
                               "budjol", "tirolsk", "sudzuk", "cabaj", "kobas", "parizer", "panona", "cajna=", "cvarci", "naresci", "jeger", "extrawurst", "poliko", "poli=", "pik hamburger", "delko", "dimcek",
                               "prsa dimljen", "dimljena pileca prsa", "dimljena pureca prsa", "prsa u ovitku",
                               "pileca prsa nar", "pureca prsa nar", "zimska", "pikant", "safalad", "mesni sir",
                               "leberkas", "pecena sunka", "frankfurt", "virsl")),
    # Riba u ulju, umaku ili salati je konzerva i u trgovini stoji uz konzerve, ne uz ribarnicu.
    ("Konzerve i gotova jela", re.compile(r"(?<![a-z])(tun|sardin|skus|incun|srdel|bakalar|haring)[a-z]*\b.*(ulj|umak|umak|salat|povrc|konzerv)")),
    ("Riba i plodovi mora", _rx("riba=", "ribe=", "ribu=", "ribl", "tuna", "tune=", "tunj", "sardin", "losos", "oslic",
                                "skusa", "skus=", "lignj", "kozic", "skamp", "dagnj", "vongole", "bakalar", "incun",
                                "srdel", "orad", "brancin", "pastrv", "haring", "plodovi mora", "hobotnic", "sipa=", "kavijar", "sushi", "surimi", "gamberi", "racic", "inc.")),
    ("Meso", _rx("piletin", "pilec", "pileca", "pileci", "pile=", "puretin", "purec", "pureca", "pureci", "junetin",
                 "junec", "juneca", "junece", "svinjetin", "svinjsk", "teletin", "telec", "teleca", "janjetin", "janjec",
                 "mljeveno meso", "mljeveno mijes", "odrezak", "odresci", "batak", "zabatak", "krilc", "rebarc", "rebra",
                 "cevap", "pljeskavic", "mesni", "meso=", "mesa=", "biftek", "ramstek", "svinjski vrat", "kare=",
                 "but=", "file=", "fileti", "medaljon", "gulas", "kobasice za rostilj", "steak", "sirloin", "kracic", "cordon bleu")),
    ("Kruh i peciva", _rx("kruh", "pecivo", "peciva", "kifl", "baguet", "bageti", "toast=", "tost=", "zemick", "lepinj",
                          "pogac", "tortilj", "tortilla", "burek", "pita=", "pite=", "grisol", "grissini", "krafn", "pereci", "grisin", "dvopek",
                          "prepecenac", "hamburger pecivo", "hot dog pecivo", "pinsa", "focaccia", "mlinci",
                          "listovi za pite")),
    ("Mliječni proizvodi i jaja", _rx("mlijek", "mlijecn", "jogurt", "kefir", "acidofil", "sir=", "sira=", "sirni",
                                      "sirevi", "sir ", "ribanac", "vrhnj", "maslac=", "maslaca", "skuta", "mozzarell",
                                      "gouda", "edamer", "trapist", "parmezan", "parmigian", "feta=", "mascarpone",
                                      "ricott", "cottage", "zrnati", "kajmak", "puding", "jaja=", "jaje=", "jaje ",
                                      "milbona", "dukat", "z bregov", "zbregov", "meggle", "president", "ementaler",
                                      "camembert", "brie=", "grcki tip", "lassi", "ayran", "margarin", "actimel",
                                      "danonino", "danone")),
    ("Namazi i paštete", _rx("dzem", "marmelad", "pekmez", "med=", "meda=", "nutella", "argeta",
                             "maslac od kikiriki", "lino lada", "eurokrem", "humus", "hummus", "ajvar")),
    ("Tjestenina, riža i brašno", _rx("makaron", "penne", "fusill", "farfalle", "tagliatel", "lazanj", "lasagn",
                                      "riza=", "rizu=", "rize=", "rizoto", "brasno", "secer=", "secera=", "palent",
                                      "kus kus", "couscous", "griz", "zob", "zobene", "pahuljic", "musli", "muesli",
                                      "corn flakes", "cornflakes", "zitaric", "kvinoj", "quinoa", "heljd", "jecam",
                                      "proso", "rezanci", "ramen", "capellini", "linguine", "bavette", "rigate", "rigatoni", "tortiglioni",
                                      "fettucc", "pappardelle", "orecchiette", "conchiglie", "gnocchi", "puzic",
                                      "surle", "fidelini", "vermicelli", "mrvice", "puding u prahu", "slag", "zelatin", "mak=",
                                      "lesnjak", "orah", "bademi", "badem", "ljesnjak", "sezam", "rogac", "bucine golice", "chia", "lan=", "suncokretove sjemenke",
                                      "sjemenk", "grah=", "leca", "slanutak", "mahunark", "kasa=")),
    ("Ulje, umaci i začini", _rx("ulje", "ulja=", "maslinovo", "ocat", "aceto", "umak", "umaci", "kecap", "ketchup",
                                 "majonez", "senf", "sol=", "soli=", "papar", "paprika mljev", "mljevena paprika",
                                 "zac.", "origano", "bosiljak", "persin susen", "cimet", "vanilin", "pasiran", "pelati",
                                 "rajcica sjeck", "sjeckana rajcica", "koncentrat", "preljev", "dressing", "pesto",
                                 "tabasco", "soja sos", "soya", "worcester", "chili", "kurkum", "lovor", "timijan",
                                 "ruzmarin", "kopar")),
    # Voće i povrće samo kad je riječ na početku naziva ("Banane", "Podravka miješana salata"), inače je obično okus
    # ("žele kocke naranča", "štrudlice jabuka").
    ("Voće", _rx("banan", "jabuk", "krusk", "naranc", "mandarin", "limun", "limet", "grozd", "kivi", "jagod", "borovnic",
                 "malin", "kupin", "avokad", "ananas", "lubenic", "dinj", "breskv", "nektarin", "sljiv", "smokv",
                 "marelic", "tresnj", "visnj", "grejp", "kaki=", "mango", "papaj", "dunj", "kokos=", "kokosov",
                 "datulj", "brusnic", "ribiz", "suho voce", "suhe sljive", "groz", "voce=")),
    ("Povrće", _rx("krumpir", "luk=", "luka=", "lukovic", "mladi luk", "cesnjak", "mrkv", "rajcic", "paprik", "krastav",
                   "salata", "kupus", "brokul", "cvjetac", "karfiol", "tikvic", "patlidzan", "spinat", "spinac", "mahun",
                   "blitv", "poriluk", "celer", "rotkv", "gljiv", "sampinjon", "cikl", "kelj", "rikol", "radic",
                   "matovilac", "komorac", "batat", "bundev", "kukuruz", "grasak", "artiso", "sparog", "djumbir",
                   "dumbir", "persin", "povrce", "maslin")),
]
# Koliko prvih riječi naziva gledaju pravila za voće i povrće (okusi voća su češći od povrća).
HEAD_WORDS = {"Voće": 2, "Povrće": 3}

LEGAL = {
    "kozmetika": "Higijena i kozmetika",
    "toaletne potrepstine": "Higijena i kozmetika",
    "sredstva za ciscenje": "Čišćenje",
    "proizvodi za kucanstvo": "Kućanstvo",
}
NONFOOD_RULES = [
    ("Za bebe", _rx("pelen", "pampers", "huggies", "babylove", "dojenc", "bocica", "duda", "dude=")),
    ("Higijena i kozmetika", _rx("sampon", "regenerator", "balzam za kos", "gel za tus", "kupka", "sapun", "krema",
                                 "losion", "dezodor", "deo=", "antiperspir", "pasta za zube", "zubna pasta", "cetkic",
                                 "vodica za usta", "brijac", "brijanj", "uloz", "tampon", "toaletni papir", "papir toalet",
                                 "vlazne maramic", "maramic", "vata", "stapici za usi", "lak za kos", "boja za kos",
                                 "parfem", "kolonjsk", "ruz=", "maskara", "puder", "nivea", "dove=", "gillette",
                                 "maska za lice", "maska za kos", "serum", "za tijelo", "lactovit", "lak za nokt", "odstranjivac laka")),
    ("Čišćenje", _rx("deterdz", "omeksiv", "sredstvo za", "sredstva za", "ocistac", "cistac", "izbjeljiv", "varikin",
                     "tablete za perilic", "kapsule za pranje", "kapsule za perilic", "sol za perilic", "sjajilo",
                     "osvjezivac", "spuzv", "krpa", "krpe=", "wc=", "odstranjivac", "pranje posud", "za pod=",
                     "za staklo", "ariel", "persil", "lenor", "jar=", "fairy", "somat", "finish", "domestos",
                     "cillit", "pronto", "ajax", "mr. proper", "mr proper", "scala")),
    ("Kućanstvo", _rx("ubrus", "papirnati ruc", "kuhinjski ruc", "kuhinjski papir", "salvet", "vrecic", "vrece",
                      "folij", "papir za pecenje", "baterij", "zarulj", "svijec", "upaljac", "sibic", "cas=", "case=",
                      "tanjur", "posud", "lonac", "tava", "pribor", "rukavic", "cetka", "metla", "kanta", "vjesalic")),
]


def _head(name: str) -> str:
    """Prve 0-3 riječi naziva (bez oznaka blagajne poput "B_")."""
    words = re.sub(r"^(b|br)_", "", name).split()
    return [" ".join(words[:k]) for k in range(4)]


def categorize(name: str, legal: str) -> str:
    """Vrsta proizvoda; prazno kad se ne može odrediti."""
    n = name
    legal = legal or ""
    pets = FOOD_RULES[0][1]
    if legal in LEGAL:
        # Neprehrana: najprije posebna pravila (hrana za ljubimce, pelene, papir), zatim zakonska kategorija.
        if pets.search(n):
            return "Kućni ljubimci"
        for label, rx in NONFOOD_RULES:
            if label != "Kućanstvo" and rx.search(n):
                return label
        return LEGAL[legal]
    if legal in ("pice", "pica"):
        for label, rx in FOOD_RULES:
            if label == "Pića" and rx.search(n):
                return label  # ledeni čaj, ice coffee
            if label in ("Kava, čaj i kakao", "Mliječni proizvodi i jaja") and rx.search(n):
                return label
        return "Pića"
    if legal in ("", "neprehrana"):
        for label, rx in NONFOOD_RULES[:3]:  # bebe, higijena, čišćenje
            if rx.search(n):
                return label
    head = _head(n)
    for label, rx in FOOD_RULES:
        if rx.search(head[HEAD_WORDS[label]] if label in HEAD_WORDS else n):
            return label
    if legal in ("", "neprehrana"):
        for label, rx in NONFOOD_RULES:
            if rx.search(n):
                return label
    return ""
