"""Builds data/routes.json: the Pagani Air Cargo scheduled network.

Each lane is a real-world style cargo flow. Distances, recommended aircraft,
typical loads, block times and rewards are calculated from the airport and
fleet data so the network stays consistent if those files change.
Usage: python tools/build_routes.py
"""
import json
import math
from itertools import zip_longest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Clean city names for station titles
CITY = {
    "LIMC": "Milan", "KMIA": "Miami", "KCVG": "Cincinnati", "OMDW": "Dubai", "OMDB": "Dubai", "VHHH": "Hong Kong",
    "PANC": "Anchorage", "KLAX": "Los Angeles", "KONT": "Ontario", "KOAK": "Oakland", "KSEA": "Seattle",
    "KPDX": "Portland", "KPHX": "Phoenix", "KDEN": "Denver", "KSLC": "Salt Lake City", "KDFW": "Dallas/Fort Worth",
    "KIAH": "Houston", "KSAT": "San Antonio", "KMCI": "Kansas City", "KMSP": "Minneapolis", "KORD": "Chicago",
    "KDTW": "Detroit", "KEWR": "Newark", "KJFK": "New York JFK", "KBOS": "Boston", "KPHL": "Philadelphia",
    "KBWI": "Baltimore", "KATL": "Atlanta", "KCLT": "Charlotte", "KMCO": "Orlando", "KTPA": "Tampa",
    "KBNA": "Nashville", "KABQ": "Albuquerque", "KRDU": "Raleigh-Durham", "KSTL": "St. Louis", "KLCK": "Columbus Rickenbacker",
    "KRFD": "Rockford", "KSAN": "San Diego", "KLAS": "Las Vegas", "KELP": "El Paso", "KOMA": "Omaha", "KBOI": "Boise",
    "PHNL": "Honolulu", "PAFA": "Fairbanks", "PABE": "Bethel", "PAOM": "Nome", "TJSJ": "San Juan",
    "CYYZ": "Toronto", "CYHM": "Hamilton", "CYVR": "Vancouver", "CYUL": "Montréal", "CYYC": "Calgary", "CYWG": "Winnipeg",
    "MMMX": "Mexico City", "MMMY": "Monterrey", "MMGL": "Guadalajara", "SKBO": "Bogotá", "SEQM": "Quito",
    "SEGU": "Guayaquil", "SPJC": "Lima", "SCEL": "Santiago", "SAEZ": "Buenos Aires", "SBGR": "São Paulo",
    "SBKP": "Campinas", "MPTO": "Panama City", "MROC": "San José", "MGGT": "Guatemala City", "MSLP": "San Salvador",
    "MDSD": "Santo Domingo", "MKJP": "Kingston", "TNCC": "Curaçao", "MYNN": "Nassau", "SLVR": "Santa Cruz",
    "EDDF": "Frankfurt", "EDDP": "Leipzig", "EDDK": "Cologne", "EBLG": "Liège", "EBBR": "Brussels", "EHAM": "Amsterdam",
    "ELLX": "Luxembourg", "EGSS": "London Stansted", "EGNX": "East Midlands", "LFPG": "Paris CDG", "LEZG": "Zaragoza",
    "LEMD": "Madrid", "LEBL": "Barcelona", "LOWW": "Vienna", "LHBP": "Budapest", "EPWA": "Warsaw", "LTFM": "Istanbul",
    "LGAV": "Athens", "LIRF": "Rome", "EKCH": "Copenhagen", "ESSA": "Stockholm", "EIDW": "Dublin", "LPPT": "Lisbon",
    "ENGM": "Oslo", "BIKF": "Keflavík", "LSZH": "Zurich", "LKPR": "Prague", "LROP": "Bucharest",
    "OTHH": "Doha", "OERK": "Riyadh", "OEJN": "Jeddah", "OBBI": "Bahrain", "OOMS": "Muscat", "OJAI": "Amman",
    "LLBG": "Tel Aviv", "HECA": "Cairo", "DTTA": "Tunis", "GMMN": "Casablanca", "DNMM": "Lagos", "DGAA": "Accra",
    "HAAB": "Addis Ababa", "HKJK": "Nairobi", "HUEN": "Entebbe", "HTDA": "Dar es Salaam", "FAOR": "Johannesburg",
    "FACT": "Cape Town", "GOBD": "Dakar", "FZAA": "Kinshasa", "FMMI": "Antananarivo",
    "RCTP": "Taipei", "RKSI": "Seoul Incheon", "RJAA": "Tokyo Narita", "RJBB": "Osaka Kansai", "ZSPD": "Shanghai Pudong",
    "ZGGG": "Guangzhou", "ZGSZ": "Shenzhen", "ZHEC": "Ezhou", "ZBAA": "Beijing", "WSSS": "Singapore", "VTBS": "Bangkok",
    "WMKK": "Kuala Lumpur", "RPLL": "Manila", "RPLC": "Clark", "VVNB": "Hanoi", "VVTS": "Ho Chi Minh City",
    "VIDP": "Delhi", "VABB": "Mumbai", "VOMM": "Chennai", "VOBL": "Bengaluru", "VCBI": "Colombo", "OPKC": "Karachi",
    "VGHS": "Dhaka", "WIII": "Jakarta", "VNKT": "Kathmandu", "PGUM": "Guam",
    "YSSY": "Sydney", "YMML": "Melbourne", "YBBN": "Brisbane", "YPPH": "Perth", "NZAA": "Auckland", "NZCH": "Christchurch",
    "NFFN": "Nadi", "NWWW": "Nouméa", "NTAA": "Papeete", "CYFB": "Iqaluit", "BGSF": "Kangerlussuaq",
    # added with the October 2026 network growth
    "EFHK": "Helsinki", "EGLL": "London Heathrow", "FIMP": "Mauritius", "FMEE": "Réunion", "FWKI": "Lilongwe",
    "GCLP": "Gran Canaria", "HTKJ": "Kilimanjaro", "KIAD": "Washington Dulles", "KILN": "Wilmington (Ohio)",
    "LATI": "Tirana", "LDZA": "Zagreb", "LMML": "Malta", "LPLA": "Lajes (Azores)", "LPMA": "Madeira",
    "LUKK": "Chișinău", "LWSK": "Skopje", "MDST": "Santiago (DR)", "NCRG": "Rarotonga", "NFTF": "Tonga",
    "NSFA": "Samoa", "NTGJ": "Gambier Islands", "OEDF": "Dammam", "ORER": "Erbil", "PKMJ": "Majuro",
    "PTRO": "Palau", "RCKH": "Kaohsiung", "RPVM": "Cebu", "SBGL": "Rio de Janeiro", "SCIP": "Easter Island",
    "SEGS": "Galápagos", "SLLP": "La Paz", "SOCA": "Cayenne", "SUMU": "Montevideo", "TAPA": "Antigua",
    "TLPL": "St Lucia", "TNCA": "Aruba", "TNCM": "St Maarten", "TIST": "St Thomas", "TXKF": "Bermuda",
    "TFFR": "Guadeloupe", "TFFF": "Martinique", "TGPY": "Grenada", "TBPB": "Barbados", "VDPP": "Phnom Penh",
    "WADD": "Bali", "ZHHH": "Wuhan", "ZSQD": "Qingdao", "ZUUU": "Chengdu", "ZYTL": "Dalian", "ENSB": "Svalbard",
    "EKVG": "Faroe Islands", "MWCR": "Grand Cayman", "MBPV": "Turks and Caicos", "ORBI": "Baghdad",
}

PARCELS = "Overnight express parcels"
ECOM = "E-commerce parcels"
MAIL = "Mail and priority documents"
HUB_US = "KCVG"  # PAC main hub

# (origin, destination, cargo, priority) grouped by region.
LANES = {
    "US domestic": [
        *[(HUB_US, d, PARCELS, "High") for d in ["KLAX", "KONT", "KOAK", "KSEA", "KPDX", "KPHX", "KDEN", "KSLC", "KDFW", "KIAH",
                                                  "KSAT", "KMCI", "KMSP", "KORD", "KDTW", "KEWR", "KJFK", "KBOS", "KPHL", "KBWI",
                                                  "KATL", "KCLT", "KMCO", "KMIA", "KTPA", "KBNA", "KABQ", "KRDU", "KSTL", "KLAS",
                                                  "KELP", "KOMA", "KBOI", "KSAN"]],
        *[(o, HUB_US, ECOM, "Standard") for o in ["KLAX", "KONT", "KOAK", "KSEA", "KDFW", "KIAH", "KORD", "KEWR", "KJFK",
                                                   "KATL", "KMIA", "KPHX", "KDEN", "KBOS"]],
        ("KMIA", "KJFK", "Fresh-cut flowers redistributed from South America", "High"),
        ("KMIA", "KORD", "Perishables and flowers", "High"),
        ("KLCK", "KONT", "Retail distribution freight", "Standard"),
        ("KRFD", "KONT", ECOM, "Standard"),
        ("KLAX", "PHNL", "General cargo and US mail", "Standard"),
        ("KONT", "PHNL", "Retail resupply and mail", "Standard"),
        ("PHNL", "KLAX", "Tropical fruit and returns", "Standard"),
        ("KSEA", "PANC", "Alaska resupply: groceries and hardware", "Standard"),
        ("PANC", "PAFA", "Interior Alaska freight and mail", "Standard"),
        ("PANC", "PABE", "Bush resupply: food, fuel parts and mail", "High"),
        ("PANC", "PAOM", "Western Alaska resupply", "Standard"),
        ("KMIA", "TJSJ", "Pharmaceutical materials and retail goods", "Standard"),
        ("TJSJ", "KMIA", "Finished pharmaceuticals", "High"),
    ],
    "Americas": [
        ("SKBO", "KMIA", "Fresh-cut roses and carnations", "High"),
        ("SEQM", "KMIA", "Long-stem roses", "High"),
        ("SEGU", "KMIA", "Shrimp and tropical fruit", "High"),
        ("SPJC", "KMIA", "Asparagus, blueberries and avocados", "High"),
        ("SCEL", "KMIA", "Fresh salmon and cherries", "High"),
        ("SAEZ", "KMIA", "Beef, wine and leather goods", "Standard"),
        ("SBKP", "KMIA", "Auto parts and machinery", "Standard"),
        ("MROC", "KMIA", "Medical devices and pineapples", "High"),
        ("MGGT", "KMIA", "Coffee, textiles and produce", "Standard"),
        ("MMGL", "KLAX", "Electronics and berries", "Standard"),
        ("MMMY", HUB_US, "Automotive components (just-in-time)", "High"),
        (HUB_US, "MMMY", "Automotive components (just-in-time)", "High"),
        ("KMIA", "SBGR", "Machinery, pharma and electronics", "Standard"),
        ("KMIA", "SCEL", "Mining spares and consumer goods", "Standard"),
        ("KMIA", "SKBO", "Electronics and consumer goods", "Standard"),
        ("KMIA", "SPJC", "Mining equipment spares", "Standard"),
        ("KMIA", "SAEZ", "Pharmaceuticals and electronics", "Standard"),
        ("KMIA", "MPTO", "Regional distribution freight", "Standard"),
        ("KMIA", "MMMX", "Consumer electronics", "Standard"),
        ("KMIA", "MDSD", "Textile inputs and general cargo", "Standard"),
        ("KMIA", "MKJP", "Retail and food service freight", "Standard"),
        ("KMIA", "TNCC", "General cargo and mail", "Standard"),
        ("KMIA", "MYNN", "Island resupply", "Standard"),
        ("KMIA", "MSLP", "Apparel inputs", "Standard"),
        ("CYHM", HUB_US, ECOM, "Standard"),
        ("CYYZ", HUB_US, "Automotive parts", "Standard"),
        (HUB_US, "CYYZ", PARCELS, "High"),
        ("CYVR", "PANC", "Seafood and general cargo", "Standard"),
        ("CYUL", "CYFB", "Arctic resupply: food and building materials", "High"),
    ],
    "Transatlantic": [
        ("LIMC", "KJFK", "Luxury fashion and machinery", "Standard"),
        ("KJFK", "LIMC", "Pharmaceuticals and aircraft parts", "Standard"),
        ("LIMC", "KORD", "Industrial machinery", "Standard"),
        ("LIMC", "KMIA", "Italian machinery, fashion and food", "Standard"),
        ("KMIA", "LIMC", "Perishables and aerospace parts", "Standard"),
        ("EDDF", "KORD", "Automotive and pharma", "Standard"),
        ("ELLX", "KIAH", "Oil and gas equipment", "Standard"),
        ("KIAH", "ELLX", "Aerospace components", "Standard"),
        ("EHAM", "KMIA", "Flowers, bulbs and electronics", "High"),
        ("EBLG", "KJFK", "E-commerce and pharma", "Standard"),
        ("EGSS", "KJFK", MAIL, "Standard"),
        ("KATL", "LFPG", "Aircraft parts and medical supplies", "Standard"),
        ("BIKF", "KJFK", "Fresh Icelandic seafood", "High"),
        ("LEZG", "MMMX", "Fashion retail stock", "High"),
        ("LEZG", "SBGR", "Fashion retail stock", "High"),
        ("LIMC", "SBGR", "Industrial machinery and pharma", "Standard"),
        ("SBKP", "LIMC", "Fruit, flowers and auto parts", "Standard"),
    ],
    "Europe": [
        *[("LIMC", d, "Express freight and road-feeder overflow", "Standard") for d in
          ["EDDP", "EBLG", "EDDF", "EDDK", "EHAM", "LFPG", "EGSS", "EGNX", "LEMD", "LEBL", "LOWW", "LHBP", "EPWA",
           "LTFM", "LGAV", "LIRF", "EKCH", "ESSA", "EIDW", "LPPT", "LKPR", "LROP"]],
        *[(o, "LIMC", ECOM, "Standard") for o in ["EDDP", "EBLG", "EDDK", "EGNX", "LFPG", "LTFM"]],
        ("ENGM", "LIMC", "Fresh Norwegian salmon", "High"),
        ("BIKF", "EGSS", "Fresh seafood", "High"),
    ],
    "Middle East & Africa": [
        *[("LIMC", d, c, p) for d, c, p in [
            ("OMDW", "Machinery and luxury goods", "Standard"), ("OTHH", "Industrial equipment", "Standard"),
            ("OERK", "Construction and energy equipment", "Standard"), ("HECA", "Pharmaceuticals", "High"),
            ("DTTA", "Textile inputs", "Standard"), ("GMMN", "Automotive components", "Standard"),
            ("DNMM", "Machinery and consumer goods", "Standard"), ("HAAB", "Humanitarian and medical supplies", "High"),
            ("HKJK", "Pharmaceuticals and machinery", "Standard"), ("FAOR", "Mining and automotive spares", "Standard"),
            ("DGAA", "Medical supplies and consumer goods", "Standard"), ("GOBD", "General cargo", "Standard")]],
        ("HKJK", "EHAM", "Kenyan roses", "High"),
        ("HKJK", "LIMC", "Flowers and fresh vegetables", "High"),
        ("HUEN", "EBLG", "Nile perch and flowers", "High"),
        ("FACT", "EHAM", "Citrus and table grapes", "High"),
        ("FAOR", "EDDF", "Automotive parts", "Standard"),
        ("OMDW", "LIMC", "Transshipped Asian electronics", "Standard"),
        ("OMDW", "EBLG", ECOM, "Standard"),
        ("OMDW", "HKJK", "Consumer electronics and spares", "Standard"),
        ("OMDW", "FAOR", "Consumer electronics", "Standard"),
        ("OMDW", "HAAB", "Humanitarian relief stock", "High"),
        ("OMDW", "FZAA", "Mining spares and relief supplies", "High"),
        ("OMDW", "HTDA", "General cargo", "Standard"),
        ("OMDW", "OJAI", "Relief and consumer goods", "Standard"),
        ("OMDW", "OBBI", "Regional feeder freight", "Standard"),
        ("OMDW", "OOMS", "Regional feeder freight", "Standard"),
        ("OMDW", "OEJN", "Consumer goods and food", "Standard"),
        ("OMDW", "HECA", "General cargo", "Standard"),
        ("LLBG", "LIMC", "Medical devices and electronics", "Standard"),
        ("FMMI", "OMDW", "Vanilla and textiles", "Standard"),
    ],
    "Asia-Pacific": [
        ("VHHH", "OMDW", "Electronics and garments", "Standard"),
        ("OMDW", "VHHH", "Perishables and general cargo", "Standard"),
        ("VHHH", "LIMC", "Consumer electronics", "Standard"),
        ("VHHH", "EDDP", ECOM, "Standard"),
        ("VHHH", "WSSS", "Electronics and components", "Standard"),
        ("WSSS", "VHHH", "Semiconductors", "High"),
        ("VHHH", "RCTP", "Components and parcels", "Standard"),
        ("VHHH", "RPLL", "Consumer goods", "Standard"),
        ("VVNB", "VHHH", "Smartphones and electronics", "High"),
        ("VVTS", "VHHH", "Garments and electronics", "Standard"),
        ("VTBS", "VHHH", "Hard drives and fresh fruit", "Standard"),
        ("WMKK", "VHHH", "Semiconductors and rubber gloves", "Standard"),
        ("RPLC", "VHHH", "Electronics components", "Standard"),
        ("ZGSZ", "OMDW", ECOM, "Standard"),
        ("ZSPD", "LIMC", "Electronics and machinery", "Standard"),
        ("ZHEC", "EDDP", ECOM, "Standard"),
        ("VGHS", "LIMC", "Ready-made garments", "High"),
        ("VIDP", "LIMC", "Garments and pharmaceuticals", "Standard"),
        ("VABB", "OMDW", "Pharmaceuticals and fresh produce", "High"),
        ("VOMM", "OMDW", "Automotive parts", "Standard"),
        ("VOBL", "EBLG", "Pharmaceuticals", "High"),
        ("VCBI", "OMDW", "Tea and garments", "Standard"),
        ("OPKC", "OMDW", "Textiles and surgical instruments", "Standard"),
        ("WIII", "WSSS", "Consumer goods", "Standard"),
        ("VIDP", "VNKT", "Relief and consumer goods", "Standard"),
        ("ENGM", "VHHH", "Fresh Norwegian salmon", "High"),
        ("YSSY", "NZAA", "Mail and general cargo", "Standard"),
        ("NZAA", "YSSY", "Dairy and kiwifruit", "Standard"),
        ("NZAA", "VHHH", "Kiwifruit, meat and dairy", "High"),
        ("YSSY", "VHHH", "Fresh seafood and wine", "High"),
        ("YMML", "WSSS", "Fresh meat and produce", "High"),
        ("YPPH", "WSSS", "Crayfish and mining spares", "High"),
        ("WSSS", "YPPH", "Mining equipment spares", "Standard"),
        ("YBBN", "NWWW", "Island resupply", "Standard"),
        ("YSSY", "NFFN", "Island resupply and mail", "Standard"),
        ("NZAA", "NTAA", "Island resupply", "Standard"),
        ("PHNL", "PGUM", "Military mail and retail freight", "Standard"),
        ("PGUM", "RPLL", "General cargo", "Standard"),
    ],
    "Transpacific": [
        ("VHHH", "PANC", "Electronics bound for the US", "High"),
        ("RCTP", "PANC", "Semiconductors", "High"),
        ("RKSI", "PANC", "Electronics and auto parts", "Standard"),
        ("RJAA", "PANC", "Automotive and precision parts", "Standard"),
        ("ZSPD", "PANC", ECOM, "Standard"),
        ("ZGGG", "PANC", ECOM, "Standard"),
        ("PANC", "KORD", "Transpacific electronics", "Standard"),
        ("PANC", HUB_US, "Transpacific e-commerce", "Standard"),
        ("PANC", "KLAX", "Electronics and apparel", "Standard"),
        ("PANC", "KDFW", "Electronics and apparel", "Standard"),
        ("PANC", "KMIA", "Electronics for Latin America", "Standard"),
        ("KLAX", "RJAA", "Fresh produce and pharma", "Standard"),
        ("KORD", "PANC", "Machinery and pharma for Asia", "Standard"),
        ("PANC", "VHHH", "US exports: meat, cherries and machinery", "Standard"),
        ("KLAX", "RKSI", "Beef, fruit and aerospace parts", "Standard"),
        ("KSEA", "RKSI", "Cherries and seafood", "High"),
    ],
}
SERIES = {"US domestic": 1000, "Americas": 2000, "Transatlantic": 3000, "Europe": 4000,
          "Middle East & Africa": 5000, "Asia-Pacific": 6000, "Transpacific": 7000}


# --------------------------------------------------------------------------- network growth, October 2026
# Appended after the original lanes so every existing PAC number stays the same. One lane per line:
#   ORIGIN DEST PRIORITY(H/S) cargo
MORE = {
    "US domestic": """
PANC PADQ S Kodiak resupply: groceries, hardware and mail
PADQ PANC H Fresh Kodiak seafood
PANC PAKN S Bristol Bay cannery supplies
PAKN PANC H Fresh sockeye salmon (summer season)
PANC PAOT H Northwest Arctic resupply: food, building materials and mail
PANC PABR H Arctic resupply to Utqiagvik
PAFA PABR S North Slope community freight
PANC PASC H North Slope oil-field equipment
PAFA PASC S Oil-field spares and camp supplies
KSEA PAKT S Southeast Alaska resupply
PAKT KSEA H Fresh salmon and halibut
KSEA PAJN S Juneau resupply and US mail
PAJN PANC S Inter-Alaska freight
PHNL PHTO S Inter-island freight and mail
PHTO PHNL H Papayas, orchids and macadamias
PHNL PHOG S Inter-island freight
PHOG PHNL S Pineapples and produce
KLAX KJFK H Fresh produce and entertainment equipment
KJFK KLAX S E-commerce parcels
KORD KLAX S Pharmaceuticals and machinery
KMIA KLAX H Fresh-cut flowers redistributed west
KEWR KMIA S Retail and pharmaceutical freight
KDFW KMIA S Oil-field equipment for Latin America
KATL KLAX S Automotive and retail freight
KAFW KONT S E-commerce parcels
KONT KAFW S Retail distribution freight
KMEM KSEA S Overnight express parcels
KSDF KDEN S Overnight express parcels
KIND KOAK S Overnight express parcels
KILN KLAX S Overnight express parcels
KILN KMIA S Overnight express parcels
KSFO HUB_US S Semiconductors and electronics
HUB_US KSFO H Overnight express parcels
""",
    "Americas": """
SBGR KMIA H Pharmaceuticals and fresh papaya
SBGL KMIA S Oil-field spares and general cargo
SBEG KMIA S Electronics from the Manaus free zone
KMIA SBEG S Electronic components for Manaus assembly lines
SBRF KMIA H Mangoes and grapes from the São Francisco valley
SBFZ KMIA H Spiny lobster and melons
SBKP SCEL S Brazilian automotive parts
SCEL SBKP H Chilean salmon and wine
SBKP SAEZ S Automotive components
SAEZ SBKP S Pharmaceuticals and machinery
SAEZ SCEL S General cargo
SCEL SPJC S Mining spares and wine
SPJC SCEL S Asparagus and alpaca textiles
SPJC SKBO S Regional express freight
SKBO SPJC S Pharmaceuticals and flowers
SKBO MPTO H Fresh flowers for transshipment
MPTO SKBO S Electronics from the Colón free zone
MPTO SEQM S Free-zone electronics
MPTO MROC S Regional distribution freight
MPTO MGGT S Free-zone consumer goods
MPTO MDSD S Free-zone consumer goods
MPTO SPJC S Electronics and apparel
TNCC MPTO S Regional transshipment freight
SKRG KMIA H Medellín flowers and textiles
SKCL KMIA S Flowers and cane-sugar products
KMIA SKRG S Textile inputs
SUMU KMIA S Beef and pharmaceuticals
SGAS KMIA S Beef, chia and leather
KMIA SGAS S Electronics and machinery
SLVR KMIA S Brazil nuts and quinoa
KMIA SLVR S Agricultural machinery spares
SLVR SLLP S Fresh produce up to the Altiplano
SLLP SLVR S Quinoa and tin concentrate samples
SPJC SPZO S Hotel and tourism supplies for Cusco
SPZO SPJC S Alpaca textiles and quinoa
SEGU SEGS H Galápagos island resupply
SEQM SEGU S Domestic express freight
MMMX KLAX S Avocados and automotive parts
MMMX KMIA S Fresh produce and electronics
MMMX MMUN S Hotel and resort supplies
MMUN KMIA S Return freight and seafood
MMQT HUB_US H Aerospace and automotive components
HUB_US MMQT H Automotive components (just-in-time)
MMTJ MMMX S Medical devices from Baja manufacturers
MMGL MMMX S Electronics
MMMY KLAX S Appliances and electronics
MMMX MGGT S Consumer goods
MHLM KMIA H Bananas and garments
KMIA MHLM S Apparel inputs
MNMG KMIA S Coffee, cigars and fresh beef
MZBZ KMIA S Seafood and citrus
KMIA MZBZ S Resort supplies
MROC MPTO S Medical devices
KMIA TBPB S General cargo and mail
TBPB TTPP S Inter-island feeder freight
TTPP KMIA S Seafood and energy-sector returns
KMIA TTPP S Energy-sector equipment
TJSJ TNCM S Island resupply
KMIA TIST S US Virgin Islands resupply and mail
TJSJ TLPL S Island resupply
TJSJ TGPY S Island resupply
TGPY TJSJ S Nutmeg and spices
TJSJ TAPA S Island resupply
KMIA MWCR S Retail and resort supplies
KMIA MBPV S Resort supplies
KMIA TXKF S Bermuda resupply
KJFK TXKF S Bermuda mail and retail freight
KMIA MTPP H Humanitarian relief and food
KMIA MDPC S Resort supplies
KMIA MDST S Apparel inputs and electronics
MDST KMIA S Cigars and cocoa
KMIA SMJP S Mining spares and general cargo
KMIA SYCJ H Offshore oil-field equipment
SYCJ KMIA S Seafood and rum
KMIA TNCA S Island resupply
CYYZ CYVR S Domestic express freight
CYVR CYYZ S Seafood and e-commerce parcels
CYYZ CYYC S Domestic express freight
CYYC CYYZ H Fresh Alberta beef
CYYZ CYWG S Domestic express freight
CYEG CYZF H Northern mine resupply
CYWG CYYQ H Hudson Bay resupply
CYUL CYVP H Nunavik resupply
CYHZ CYUL H Live lobster and seafood
CYFB CYRB H High Arctic research station resupply
HUB_US CYUL H Overnight express parcels
HUB_US CYVR H Overnight express parcels
CYYZ KMIA S Pharmaceuticals and consumer goods
SBGR SCEL S Machinery
SBGR SAEZ S Pharmaceuticals
SBGR SKBO S Electronics
SBGR SPJC S Machinery
SBGR SBEG S Inputs for the Manaus free zone
SBEG SBGR S Motorcycles and electronics from Manaus
SBGR SBRF S Domestic express freight
SBGR SBPA S Domestic express freight
SBPA SBGR S Leather and machinery
SBGR SBCF S Domestic express freight
SBCF SBGR S Gemstones and automotive parts
SBGR SBFZ S Domestic express freight
SBEG SBTT H Amazon river-town resupply
SCEL SCFA H Mining spares for the Atacama
SCFA SCEL S Mining returns and assay samples
SCEL SCCI H Patagonian resupply
SCCI SCEL H Fresh king crab and lamb
SAEZ SAWH S Tierra del Fuego resupply
SAWH SAEZ H Fresh king crab
SAEZ SAME S Domestic express freight
SAME SAEZ S Wine and dried fruit
SAEZ SUMU S Regional express freight
SCEL SCIP S Rapa Nui island resupply
""",
    "Transatlantic": """
EDDF KJFK S Pharmaceuticals and machinery
KJFK EDDF S Aircraft parts and pharmaceuticals
EDDF KATL S Automotive parts
KATL EDDF S Medical devices and aerospace parts
EDDP HUB_US S E-commerce parcels
HUB_US EDDP H Transatlantic express parcels
EGSS HUB_US S E-commerce parcels
HUB_US EGSS H Transatlantic express parcels
EGLL KJFK H Pharmaceuticals and priority documents
KJFK EGLL S Financial documents and electronics
EGSS KORD S Machinery and whisky
LFPG KJFK S Luxury goods and wine
KJFK LFPG S Aerospace parts
LFPG TFFR S Guadeloupe resupply
LFPG TFFF S Martinique resupply
TFFF LFPG H Bananas and fresh fish
LFPG SOCA S Space-centre equipment for French Guiana
EHAM KJFK H Flowers and pharmaceuticals
EHAM KIAD S Pharmaceuticals
EBLG KMEM S Express parcels
EINN KJFK H Medical devices
LPPT SBGR S Machinery and wine
LEMD SBGR S Pharmaceuticals and machinery
LEMD SKBO S Pharmaceuticals and machinery
SKBO LEMD H Fresh-cut flowers
LIMC CYYZ S Machinery
CYYZ LIMC S Aerospace parts
LIMC KATL S Pharmaceuticals
LIMC KIAD S Luxury goods and machinery
BIKF KBOS H Fresh Icelandic seafood
KJFK BIKF S Retail goods and mail
EKCH BGSF H Greenland resupply
BGSF BGGH H Nuuk resupply
LTFM KJFK S Textiles and dried fruit
LTFM KORD S Machinery and textiles
EDDF CYYZ S Automotive parts
CYYZ EDDF S Machinery and pharmaceuticals
CYUL LFPG S Aerospace parts
LFPG CYUL S Pharmaceuticals and wine
KMIA LEMD S Perishables and pharmaceuticals
LEMD KMIA S Fashion and machinery
KMIA EHAM H Fresh fish and flowers
LPPT LPLA S Azores resupply
""",
    "Europe": """
EDDP EGNX S Express parcels
EDDP LEBL S Express parcels
EDDP LIRF S Express parcels
EDDP EPWA S Express parcels
EDDP LKPR S Express parcels
EDDP LBSF S Express parcels
EDDP EVRA S Express parcels
EDDP EYVI S Express parcels
EDDP EETN S Express parcels
EDDP EFHK S Express parcels
EDDP LDZA S Express parcels
EDDP LYBE S Express parcels
EDDP LROP S Express parcels
EBLG LPPT S E-commerce parcels
EBLG LEMD S E-commerce parcels
EBLG LIRF S E-commerce parcels
EBLG LGAV S E-commerce parcels
EBLG LTFM S E-commerce parcels
EGNX EIDW S Express parcels and mail
EGNX EGPD S Express parcels
EGNX EGAA S Mail and express parcels
EGNX EDDK S Express parcels
LIMC LMML S Island resupply
LICC LIMC H Sicilian citrus and produce
LIMC LIEE S Sardinia resupply
LGAV LGIR S Crete island resupply
LGIR LGAV H Fresh produce and olive oil
LCLK LIMC S Halloumi and pharmaceuticals
LTFM UBBB S General cargo
LTFM UGTB S General cargo
LTFM LYBE S Textiles and consumer goods
UBBB LIMC S Oil and gas spares returns
ENGM ENBO S North Norway resupply
ENBO ENTC S Arctic Norway freight
ENTC ENSB H Svalbard resupply
ENSB ENTC S Research samples and returns
ENGM ENVA S Domestic express freight
ENBR LIMC H Fresh Norwegian salmon
EFHK ESSA S Express parcels
EKCH EKVG S Faroe Islands resupply
EKVG EKCH H Fresh Faroese salmon
EKCH BIKF S Iceland resupply
EGPD ENBR H Offshore oil and gas spares
LXGB EGSS S Gibraltar resupply
EGSS LXGB S Gibraltar mail and retail freight
LOWW LQSA S General cargo
LOWW LWSK S General cargo
LIMC LATI S General cargo
LROP LUKK S General cargo
EPKT EDDP S E-commerce parcels
LPPT LPMA S Madeira resupply
LEMD GCLP S Canary Islands resupply
GCLP LEMD H Tomatoes and fresh fish
LEMD LEBL S Domestic express freight
EIDW EGNX S Express parcels
EDDF LTFM S Machinery
EDDF EGSS S Express freight
""",
    "Middle East & Africa": """
HAAB HKJK S Regional express freight
HKJK HAAB H Flowers for onward connection
HAAB FAOR S Consumer goods
FAOR HAAB S Mining spares
HAAB DNMM S Regional transshipment freight
HAAB DGAA S Regional transshipment freight
HAAB FZAA H Relief supplies
HAAB HSSK H Humanitarian relief
HAAB HCMM H Humanitarian food aid
HAAB HDAM S Port transshipment freight
HAAB HRYR S General cargo
HAAB FLKK S General cargo
HAAB HUEN S General cargo
HAAB FNLU S Oil-field spares
HAAB LIMC H Fresh flowers and vegetables
HAAB EBLG H Ethiopian roses
HAAB OMDW S Coffee and leather goods
HKJK HKMO S Domestic express freight
HKJK HRYR S General cargo
HKJK HUEN S General cargo
HKJK HTKJ S Safari lodge supplies
HKJK FAOR S Flowers and tea
HKJK HTDA S General cargo
HKJK OMDW H Avocados and green beans
HKJK EGSS H Green beans and baby corn
HUEN OMDW H Fresh Nile perch
HTMW HKJK H Fresh Lake Victoria fish
HTDA OMDW S Cashews and spices
FAOR FACT S Domestic express freight
FACT FAOR S Wine and fruit
FAOR FQMA S Regional freight
FAOR FLKK S Mining spares
FAOR FVRG S General cargo
FAOR FWKI S General cargo
FAOR FYWH S General cargo
FBSK FAOR H Rough diamonds (high-value consignment)
FAOR FZQA H Mining equipment for the Copperbelt
FZQA FAOR S Copper cathode samples and returns
FAOR FIMP S General cargo
FAOR FMMI S General cargo
FAOR FNLU S Oil-field and mining spares
FAOR DNMM S General cargo
FAOR LIMC S Automotive parts and minerals
FIMP FMEE S Island express freight
FMEE FIMP S Island express freight
DNMM DGAA S Regional freight
DNMM DNAA S Domestic express freight
DNMM DIAP S Regional freight
DIAP LFPG H Mangoes and pineapples
GOBD LFPG H Fresh vegetables and fish
DIAP GOBD S Regional freight
GMMN LFPG S Automotive wiring and textiles
GMMN GOBD S General cargo
GMMX LFPG S Handicrafts and fresh produce
DAAG LFPG S General cargo
HECA EBLG H Fresh vegetables and citrus
HECA OMDW S Textiles and produce
HECA OERK S General cargo
HECA OEJN S Textiles and produce
OMDW ORBI S Reconstruction supplies
OMDW ORER S Oil-field equipment
OMDW OEDF S Petrochemical spares
OMDW OLBA S Relief and consumer goods
OMDW OKKK S Consumer goods
OMDW HSSK H Humanitarian relief
OMDW HCMM H Humanitarian food aid
OMDW HDAM S Port transshipment freight
OMDW OYAA H Humanitarian relief and medical supplies
OMDW OTHH S Regional feeder freight
OTHH OERK S General cargo
OTHH LIMC S Fresh food and consumer goods
OERK OEJN S Domestic express freight
OEJN OERK S Domestic express freight
OEJN HAAB S General cargo
OBBI OERK S Regional freight
OLBA LIMC S Fresh produce and jewellery
LIMC DAAG S Machinery
LIMC GMMX S Consumer goods
LIMC OLBA S Pharmaceuticals
LIMC LLBG S Machinery and pharmaceuticals
LIMC OBBI S Aluminium industry spares
LIMC OKKK S Luxury goods and machinery
LLBG LCLK S General cargo
""",
    "Asia-Pacific": """
ZSPD ZBAA S Domestic express freight
ZBAA ZSPD S Domestic express freight
ZGGG ZUUU S Consumer electronics
ZUUU ZGGG S Laptops and electronics
ZUCK ZSPD S Laptops and electronics
ZHHH ZGGG S Optical fibre and electronics
ZLXY ZSPD S Semiconductors
ZSHC ZBAA S E-commerce parcels
ZSNJ ZGSZ S Electronics
ZBTJ ZSPD S Automotive parts
ZYTL RJAA S Seafood and electronics
ZSQD RKSI S Seafood and textiles
ZSAM RCTP S Electronics and textiles
RJAA RKSI S Precision parts
RKSI RJAA S Semiconductors and electronics
RJBB RKSI S Precision parts
RJCC RJAA H Fresh Hokkaido seafood and dairy
RJFF RJBB S Semiconductors
RKPK RJBB S Automotive parts
RKSI ZSPD S Semiconductors and displays
RKSI VHHH S Semiconductors and displays
RJAA VHHH S Precision parts and cosmetics
RJAA RCTP S Semiconductor equipment
RCKH RJAA S Semiconductors
RCTP RJBB S Semiconductors
RJBB ZSPD S Machinery and electronics
WSSS WMKK S Electronics components
WMKK WSSS S Semiconductors
WSSS WIII S Consumer goods
WSSS VTBS S Electronics components
VTBS WSSS S Hard drives and fresh fruit
VTBS VDPP S General cargo
VDPP VTBS S Garments
VTBS VLVT S General cargo
VTBS VYYY S General cargo
VYYY VTBS S Garments and seafood
VVTS WSSS S Electronics and seafood
VVNB ZGGG S Smartphones and components
RPLL RPVM S Domestic express freight
RPVM RPLL S Dried mangoes and furniture
RPMD RPLL S Bananas and pineapples
WADD WSSS H Fresh tuna
WSSS WADD S Hotel and resort supplies
WBKK WMKK S General cargo
WBGG WMKK S General cargo
WMKK VTBS S Electronics components
VIDP VABB S Domestic express freight
VABB VIDP S Domestic express freight
VOBL VIDP S Electronics and pharmaceuticals
VOCI OMDW H Fresh fish and vegetables
VOHS OMDW H Pharmaceuticals
VAAH OMDW S Textiles and chemicals
VECC VGHS S General cargo
VEGT VIDP S Assam tea
VABB VCBI S General cargo
VGHS VHHH S Garments
VECC VQPR S Bhutan resupply
VIDP VNKT H Relief and consumer goods for Nepal
UAAA OMDW S Consumer goods
UAAA EDDP S Asia–Europe e-commerce
YSSY YMML S Domestic express freight
YMML YSSY S Domestic express freight
YSSY YBBN S Domestic express freight
YSSY YPPH S Domestic express freight
YPPH YSSY S Crayfish and mining returns
YMML YPPH S Domestic express freight
YSSY YPDN S Top End resupply
YPPH YPKA H Mining camp resupply
YPPH YPPD H Iron-ore mining spares
YBBN YBCS S Far North Queensland freight
YBCS AYPY S Papua New Guinea resupply
YBBN AYPY S Mining spares for Papua New Guinea
NZAA NZCH S Domestic express freight
NZCH NZAA S Domestic express freight
NZWN NZCH S Domestic freight
NZAA NFFN S Island resupply
NFFN NZAA H Fresh fish
NZAA NSFA S Samoa resupply
NZAA NFTF S Tonga resupply
NZAA NCRG S Cook Islands resupply
YSSY NVVV S Vanuatu resupply
YBBN AGGH S Solomon Islands resupply
NFFN NSTU S Island freight and mail
PGUM PTRO S Palau resupply
PHNL PKMJ S Marshall Islands resupply
NTAA NTGJ S Gambier Islands resupply
WSSS YSSY S Electronics and consumer goods
YSSY WSSS S Fresh produce and wine
VHHH YSSY S Electronics and e-commerce
YMML VHHH H Live rock lobster
VABB LIMC H Pharmaceuticals
VIDP EDDF S Garments and pharmaceuticals
VIDP EBLG S Pharmaceuticals
VTBS OMDW S Fresh fruit and electronics
WSSS OMDW S Electronics
""",
    "Transpacific": """
PANC RKSI S US exports: machinery and meat
PANC RJAA S US exports: cherries and pharmaceuticals
PANC ZSPD S US exports: machinery and pharmaceuticals
PANC KONT S Transpacific e-commerce
PANC KMEM S Transpacific express parcels
PANC KSDF S Transpacific express parcels
PANC KIND S Transpacific express parcels
PANC KJFK S Electronics and apparel
PANC KATL S Electronics and apparel
PANC KILN S Transpacific e-commerce
RJBB PANC S Automotive and precision parts
ZBAA PANC S Electronics
RPLC PANC S Electronics components
VVNB PANC H Smartphones bound for the US
PHNL RJAA S Tropical fruit and returns
RJAA PHNL S Japanese retail goods
PHNL YSSY S General cargo
YSSY PHNL S Australian beef and wine
PHNL NZAA S General cargo
KSEA RJAA S Cherries and seafood
PANC KSEA H Fresh Copper River salmon
""",
}


def _more_lanes(text):
    out = []
    for line in text.strip().splitlines():
        o, d, p, cargo = line.split(" ", 3)
        o, d = (HUB_US if x == "HUB_US" else x for x in (o, d))
        out.append((o, d, cargo.strip(), "High" if p == "H" else "Standard"))
    return out


EXTRA = {region: _more_lanes(text) for region, text in MORE.items()}

# Aircraft preferences for the new lanes, by sector length. Each lane offers up to two MSFS and two X-Plane types,
# so pilots on either simulator find work everywhere, and the 757, 767, MD-11F and 747-200F see more of the network.
BANDS = [  # (up to nm, MSFS types, X-Plane types)
    (900, ["B738F", "B722F", "A306F"], ["B733F", "B732F", "B752F"]),
    (2000, ["A306F", "B738F", "MD11F", "B722F"], ["B752F", "B763F", "B733F", "B732F"]),
    (3200, ["MD11F", "A306F", "B77F"], ["B763F", "B752F", "B742F"]),
    (99999, ["MD11F", "B77F", "B748F"], ["B742F", "B763F"]),
]


def balanced_types(o, d, dist, shortest_rwy, fleet):
    """Two MSFS and two X-Plane types that can fly the sector, rotated per lane so the work is spread around."""
    spin = sum(map(ord, o + d))
    msfs, xp = next((m, x) for top, m, x in BANDS if dist <= top)

    def ok(k):
        return k in fleet and fleet[k]["range_nm"] >= dist * 1.05 and fleet[k]["min_rwy_ft"] <= shortest_rwy

    def pick(types):
        fit = [k for k in types if ok(k)]
        if len(fit) > 1:
            r = spin % len(fit)
            fit = fit[r:] + fit[:r] if spin % 3 else fit
        return fit[:2]

    m, x = pick(msfs), pick(xp)
    if not m:   # nothing in the band fits (a short runway, say): any MSFS type that does
        m = [k for k in fleet if fleet[k].get("sim") == "MSFS" and ok(k)][:2]
    if not x:
        x = [k for k in fleet if fleet[k].get("sim") == "X-Plane" and ok(k)][:2]
    first, second = (x, m) if spin % 2 else (m, x)
    return [k for pair in zip_longest(first, second) for k in pair if k][:4]


def gc(a, b):
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dl = math.radians(b["lon"] - a["lon"])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 3440.065 * math.asin(min(1, math.sqrt(h)))


def main():
    ap = json.loads((DATA / "airports.json").read_text(encoding="utf-8"))
    F = ap["fields"]
    airports = {r[0]: dict(zip(F, r)) for r in ap["rows"]}
    fleet = json.loads((DATA / "fleet.json").read_text(encoding="utf-8"))
    # smallest capable aircraft first on short sectors, biggest first on long ones
    order_short = ["B738F", "B722F", "B733F", "B732F", "A306F", "B752F", "B763F", "MD11F", "B77F", "B748F", "B742F"]
    order_long = ["B77F", "B748F", "MD11F", "B742F", "B763F", "A306F", "B752F", "B738F", "B722F", "B733F", "B732F"]
    routes, seen, missing = [], set(), set()
    for region, lanes in LANES.items():
        n = SERIES[region]
        legacy = len(lanes)
        for i, (o, d, cargo, prio) in enumerate(lanes + EXTRA.get(region, [])):
            if (o, d) in seen:
                continue
            if o not in airports or d not in airports:
                missing.update(x for x in (o, d) if x not in airports)
                continue
            seen.add((o, d))
            A, B = airports[o], airports[d]
            dist = gc(A, B)
            shortest_rwy = min(A["rwy_ft"] or 99999, B["rwy_ft"] or 99999)
            trunk = A["size"] == "L" and B["size"] == "L" and dist > 700
            order = (["A306F", "B752F", "B738F", "B722F", "B763F", "MD11F", "B77F", "B748F"] if trunk and dist < 2200
                     else order_short if dist < 2200 else order_long)
            fits = [k for k in order if k in fleet and fleet[k]["range_nm"] >= dist * 1.05 and fleet[k]["min_rwy_ft"] <= shortest_rwy]
            if not fits:
                fits = [k for k in order_long if fleet[k]["range_nm"] >= dist * 0.9][:1] or ["B77F"]
            fits = fits[:4]
            if i >= legacy:
                fits = balanced_types(o, d, dist, shortest_rwy, fleet) or fits
            lead = fleet[fits[0]]
            # load factor varies by lane (steady, repeatable per route) and drops on very long sectors
            lf = 0.6 + (sum(map(ord, o + d)) % 26) / 100
            if dist > 4400:
                lf *= 0.75
            elif dist > 3500:
                lf *= 0.88
            payload = int(round(lead["max_payload_lbs"] * lf / 500) * 500)
            block = round(25 + 20 + dist / lead["cruise_ktas"] * 60 * 1.05)
            reward = int(round((dist * 0.14 + payload / 1000 * 1.2) * (1.15 if prio == "High" else 1.0) / 10) * 10)
            n += 1
            ca, cb = CITY.get(o, A["city"]), CITY.get(d, B["city"])
            routes.append({
                "id": f"PAC{n}", "title": f"{ca} to {cb}", "category": "Scheduled", "region": region, "priority": prio,
                "origin": {"icao": o, "name": A["name"], "city": ca, "country": A["country"], "lat": A["lat"], "lon": A["lon"]},
                "destination": {"icao": d, "name": B["name"], "city": cb, "country": B["country"], "lat": B["lat"], "lon": B["lon"]},
                "aircraft": fits, "cargo": cargo, "payload_lbs": payload, "target_block_min": block, "reward": reward,
                "distance_nm": round(dist),
                "briefing": (f"Scheduled {region} rotation, {round(dist):,} nm. {cargo} on a typical load of {payload:,} lb. "
                             f"Shortest runway on the sector is {shortest_rwy:,} ft."),
            })
    (DATA / "routes.json").write_text(json.dumps(routes, indent=1, ensure_ascii=False), encoding="utf-8")
    print(len(routes), "routes;", len({r['origin']['icao'] for r in routes} | {r['destination']['icao'] for r in routes}), "stations")
    if missing:
        print("missing airports:", sorted(missing))


if __name__ == "__main__":
    main()
