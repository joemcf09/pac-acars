"""Station guides.

Every PAC station gets a guide built from data (runways, weather, a satellite map, PAC's flights there).
Stations with a hand-written guide add detailed local knowledge. Facts about real airports come from the
published sources listed in each guide; PAC's own facilities and stand numbers are fictional (PAC is a virtual
airline) and are marked as such. For flight simulation only: real-world pilots use current official charts.
"""

# PAC's stands where a station guide defines them. ACARS assigns from these on arrival, sized for the aircraft
# (ICAO aerodrome reference code letter by wingspan: C up to 36 m, D up to 52 m, E up to 65 m, F up to 80 m).
PAC_STANDS = {
    "KCVG": {"F": ["P1", "P2"], "E": ["P3", "P4"], "D": ["P5", "P6"], "C": ["P7", "P8"]},
    # the other PAC hubs: six stands each on the airport's cargo area
    "VHHH": {"F": ["X12", "X13"], "E": ["X14", "X15"], "D": ["X16"], "C": ["X17"]},  # real cargo apron stands
    "KMIA": {"F": ["P1"], "E": ["P2", "P3"], "D": ["P4", "P5"], "C": ["P6"]},
    "LIMC": {"F": ["P1"], "E": ["P2", "P3"], "D": ["P4", "P5"], "C": ["P6"]},
    "OMDW": {"F": ["P1"], "E": ["P2", "P3"], "D": ["P4", "P5"], "C": ["P6"]},
    "PANC": {"F": ["PC1"], "E": ["PC2", "PC3"], "D": ["PC4", "PC5"], "C": ["PC6"]},  # not P1-P3: ANC has a real P ramp
}
# Where PAC's stands are drawn on the station map: the spots placed by PAC's founder on the satellite imagery (October 2026),
# and Hong Kong's published stand coordinates. Staff can still move them (saved in data/stand_positions.json, which overrides).
STAND_POSITIONS = {
    "KCVG": {'P1': [39.036895, -84.650989], 'P2': [39.036903, -84.651879], 'P3': [39.036911, -84.652748], 'P4': [39.036928, -84.653553], 'P5': [39.03847, -84.652909], 'P6': [39.038478, -84.652244], 'P7': [39.03847, -84.651579], 'P8': [39.038461, -84.650881]},
}
STAND_POSITIONS.update(VHHH={'X12': [22.298481, 113.921331], 'X13': [22.298753, 113.922175], 'X14': [22.298967, 113.922839], 'X15': [22.299181, 113.923506], 'X16': [22.299453, 113.924347], 'X17': [22.299667, 113.925014]})  # Hong Kong eAIP, cargo apron stand coordinates
STAND_POSITIONS.update({'KMIA': {'P1': [25.80524, -80.29572], 'P2': [25.805245, -80.295113], 'P3': [25.80525, -80.294513], 'P4': [25.805366, -80.293855], 'P5': [25.805411, -80.29311], 'P6': [25.805426, -80.292187]}, 'LIMC': {'P1': [45.61636, 8.719443], 'P2': [45.617039, 8.719389], 'P3': [45.617662, 8.719245], 'P4': [45.618165, 8.719298], 'P5': [45.618596, 8.718853], 'P6': [45.619159, 8.718676]}, 'PANC': {'PC1': [61.196735, -150.007753], 'PC2': [61.196885, -150.006262], 'PC3': [61.197014, -150.005082], 'PC4': [61.197443, -150.005157], 'PC5': [61.19734, -150.006284], 'PC6': [61.197144, -150.007657]}, 'OMDW': {'P1': [24.893006, 55.153127], 'P2': [24.893385, 55.152429], 'P3': [24.893784, 55.151721], 'P4': [24.894368, 55.150659], 'P5': [24.894816, 55.149876], 'P6': [24.895225, 55.149168]}})

# where each station's stand positions come from; 'published' positions are exact and need no placing
STAND_SOURCES = {
    "KCVG": {"final": True, "where": "South cargo complex, beside the DHL hub", "note": "PAC's stands are fictional; the PAC emblems mark the spots PAC uses."},
    "VHHH": {"published": True, "where": "Cargo apron, south side, by the cargo terminals (SuperTerminal 1 is at the southeast corner)",
             "note": "Real cargo apron stands X12 to X17, at the positions published in the Hong Kong eAIP (AD 2 VHHH, cargo apron stand coordinates)."},
    "KMIA": {"final": True, "where": 'West Cargo area, on the west side of the airport', "note": "MIA's cargo aprons have common-use cargo positions, which PAC uses; the PAC emblems mark PAC's spots."},
    "LIMC": {"final": True, "where": 'Cargo City, west of runway 17R/35L beside Terminal 1 and the tower', "note": 'The PAC emblems mark the Cargo City spots PAC uses.'},
    "OMDW": {"final": True, "where": 'Cargo apron beside runway 12/30', "note": 'The PAC emblems mark the cargo apron spots PAC uses.'},
    "PANC": {"final": True, "where": 'North cargo area', "note": "Named PC1 to PC6 so they can't be confused with Anchorage's real P ramp spots P1 to P3. The PAC emblems mark PAC's spots."},
}

OLD_STAND_NAMES = {"KCVG": {f"N{i}": f"P{i}" for i in range(1, 9)}}  # stands were N1-N8 when PAC was on the north side
STAND_INFO = {"F": "Code F (up to 80 m span): 747-8F", "E": "Code E (up to 65 m): 777F, A330-200P2F, 747-200F, 747-400F",
              "D": "Code D (up to 52 m): MD-11F, A300-600F, 767-300F, 757-200F", "C": "Code C (up to 36 m): 737s, 727-200F"}

AIRCRAFT_CODE = {"B748F": "F", "B77F": "E", "B742F": "E", "B744F": "E", "MD11F": "D", "A306F": "D", "A332F": "E", "B763F": "D", "B752F": "D",
                 "B738F": "C", "B732F": "C", "B733F": "C", "B722F": "C"}

GUIDES = {
    "KCVG": {
        "name": "Cincinnati/Northern Kentucky International",
        "role": "PAC main hub",
        "updated": "October 2026 (FAA Chart Supplement cycle of August 6, 2026)",
        "glance": [
            ["ICAO / IATA", "KCVG / CVG"],
            ["Location", "8 miles SW of Covington, Kentucky, serving Cincinnati, Ohio"],
            ["Elevation", "896 ft"],
            ["Magnetic variation", "6° W"],
            ["Reference point", "N39°02.93' W084°40.07'"],
            ["Airspace", "Class B; tower 24 hours"],
            ["ARTCC", "Indianapolis Center"],
            ["Rescue and firefighting", "Index D (Index E on request)"],
            ["Customs", "Landing rights airport"],
            ["Fuel", "Jet A, 100LL"],
        ],
        "sections": [
            {"title": "Cargo at Cincinnati", "body": [
                "CVG is the only airport in North America that is a hub for two express networks at once. DHL Express "
                "arrived in 2009 and now runs one of its three global hubs here, on about 194 acres, with roughly 130 "
                "flights a day. Amazon Air opened its $1.5 billion Air Hub in August 2021 on about 650 acres on the "
                "south side of the airfield, with an option on more land to the north.",
                "Cargo has made up more than half of the airport's landed weight (about 54% in airport figures), which keeps landing fees low for the "
                "passenger airlines. Atlas Air, a major contract operator for both DHL and Amazon, runs a large "
                "operations center near the airport. FedEx's operation is in the west service area, where the "
                "original DHL hub once stood.",
                "General, non-express freight is the newest part of the story. The airport is developing North Cargo "
                "Village (also called the Global Logistics Park) on the north side of the campus, with forwarding "
                "warehouses, freighter facilities and a sort center planned. Its first building, an 80,000 sq ft "
                "airside warehouse, sits on an airside ramp rebuilt with more than $33 million of federal funds.",
            ]},
            {"title": "PAC at Cincinnati", "fictional": True, "body": [
                "PAC leases a block of eight stands on the south cargo complex, alongside the DHL hub. It's a natural "
                "neighbor: Atlas Air, one of PAC's partners, flies for DHL from the same ramp, and the complex has the "
                "space, equipment and customs presence a heavy freighter operation needs. PAC's build-up of ULDs, "
                "dangerous goods acceptance and customs clearance for international arrivals are handled on the complex.",
                "PAC Operations Control (the OCC that answers your ACARS messages) is based here. Stands are allocated by "
                "aircraft size, and ACARS sends yours at top of descent. The south complex sits by the south ends of 18C/36C "
                "and 18L/36R, so with south flow (landing 18C or 18L) the taxi in is short.",
                "{stand_layout}",
            ], "stand_where": True,  # the "Where on the ramp" column and {stand_layout} are worked out from the stand positions
               "table": {"head": ["Stand", "Size", "PAC aircraft", "Where on the ramp"],
                         "rows": [["P1, P2", "Code F (up to 80 m span)", "747-8F", ""],
                                  ["P3, P4", "Code E (up to 65 m)", "777F, 747-200F", ""],
                                  ["P5, P6", "Code D (up to 52 m)", "MD-11F, A300-600F, 767-300F, 757-200F", ""],
                                  ["P7, P8", "Code C (up to 36 m)", "737s, 727-200F", ""]]},
             "note": "PAC's lease and stand numbers are fictional (PAC is a virtual airline); the south cargo complex is real and "
                     "is DHL's hub. The PAC emblems on the map show exactly which parking spots PAC uses."},
            {"title": "Runways", "table": {
                "head": ["Runway", "Length × width", "Approach", "Lighting and glidepath", "Notes"],
                "rows": [
                    ["09 / 27", "12,001 × 150 ft", "09: ILS/DME · 27: ILS (CAT I/II SA)", "MALSR both ends, 3.0° PAPI (TCH 70/67 ft)",
                     "Longest runway; crosses 18C/36C mid-field. 09 landing distance 11,640 ft."],
                    ["18C / 36C", "11,000 × 150 ft", "18C: ILS (CAT I/II SA) · 36C: ILS CAT II/III", "36C ALSF-2; 3.0° PAPI (TCH 71/77 ft)",
                     "36C slopes up 0.6%."],
                    ["18L / 36R", "10,000 × 150 ft", "18L: ILS · 36R: ILS CAT II/III", "36R ALSF-2; 3.0° PAPI (TCH 71/70 ft)", ""],
                    ["18R / 36L", "8,000 × 150 ft", "18R and 36L: ILS CAT II", "ALSF-2 both ends",
                     "Closed to passenger aircraft over 140 ft span; cargo aircraft are not restricted by that rule."],
                ]},
             "note": "All runways are grooved concrete or asphalt over concrete, with centerline lights and high-intensity edge lights. "
                     "The three parallel runways are aligned 174°/354° true (18/36 magnetic)."},
            {"title": "Frequencies", "table": {
                "head": ["Service", "Frequency", "Use"],
                "rows": [
                    ["D-ATIS arrival", "134.375", ""], ["D-ATIS departure", "135.3", ""],
                    ["Clearance Delivery", "120.4", "Older sources list 127.175; 120.4 is current"],
                    ["Cincinnati Ground", "121.7", ""],
                    ["Cincinnati Tower", "118.3", "Runways 09/27 and 18C/36C"],
                    ["Cincinnati Tower", "118.975", "Runway 18L/36R"],
                    ["Cincinnati Tower", "133.325", "Runway 18R/36L"],
                    ["Cincinnati Approach", "119.7", "Arriving from 090° to 269°"],
                    ["Cincinnati Approach", "123.875", "Arriving from 270° to 089°"],
                    ["Cincinnati Departure", "126.65", "Departing 001° to 180°"],
                    ["Cincinnati Departure", "128.7", "Departing 181° to 360°"],
                    ["Ramp Control", "130.375", "Ramp 3 taxilane and North taxilane (north side, North Cargo Village)"],
                    ["Ramp Control", "130.90", "Ramps 1N/1S and 2N/2S taxilanes (terminal ramps)"],
                    ["DHL Ramp Control", "129.475", "South cargo complex: the DHL hub, and PAC's stands"],
                    ["Amazon Ramp Control", "130.5", "Amazon Air Hub only"],
                    ["UNICOM", "122.95", ""], ["Emergency", "121.5", ""],
                ]}},
            {"title": "Arriving", "body": [
                "Pick up the arrival ATIS on 134.375 early. Arrivals from the published STARs (CINCE and JAKIE among "
                "them) are handed to Cincinnati Approach: 119.7 if you're arriving from the east and south half (090° to "
                "269°), 123.875 from the west and north (270° to 089°).",
                "In low visibility, 36C and 36R have CAT II/III ILS; 18R and 36L have CAT II; 18C and 27 have special "
                "authorization CAT I/II. PAC's standard practice: with north flow, plan 36C or 36R; with south flow, "
                "18C or 18L. Expect the runway in the ATIS and plan the taxi before you start the approach.",
                "After landing, Tower hands you to Ground on 121.7. For PAC's stands on the south cargo complex, Ground "
                "will hand you to DHL Ramp Control on 129.475 at the edge of the ramp: give your PAC callsign and stand "
                "number. Don't call Amazon Ramp (130.5): it controls only the Amazon Air Hub.",
            ]},
            {"title": "On the ground", "body": [
                "The airport uses surface surveillance: keep the transponder (with altitude reporting) and ADS-B on "
                "whenever you're moving on the airport.",
                "Aircraft with a wingspan of 214 ft or more must taxi at 15 mph or less. In PAC's fleet that's the "
                "747-8F (224 ft); the 777F, at about 213 ft, is just under the limit.",
                "Birds are reported on and around the airport: keep a lookout on approach and departure.",
                "Taxi routes depend on the runway in use and on south-side express traffic. Follow Ground's route "
                "exactly. The DHL and Amazon hubs run large banks of arrivals and departures (DHL alone has about 130 "
                "flights a day), so expect busy taxiways when a bank is moving.",
            ]},
            {"title": "Departing", "body": [
                "Departure ATIS is on 135.3 and Clearance Delivery on 120.4. Departures are handed to Cincinnati "
                "Departure: 126.65 for the eastern half (001° to 180°), 128.7 for the western half (181° to 360°).",
                "Simultaneous or successive departures from 18L, 18C, 36L, 36C and 36R are approved, with the "
                "headings diverging no more than 2 miles from the end of the runway, for noise abatement. The published "
                "obstacle departure headings are 004° off the 36s, 184° off 18C and 18L, a right turn to 200° off 18R, "
                "and 274° off 27. Follow your clearance or SID if one is assigned.",
                "Heavy departures: hot, humid summer afternoons at a field elevation of 896 ft cut takeoff performance. "
                "With a full 747 or 777, ask for the longer 09/27 (12,001 ft) or 18C/36C (11,000 ft).",
            ]},
            {"title": "Noise abatement", "body": [
                "There are noise-sensitive areas north and south of the airport. Between 2200 and 0700 local, the "
                "runway is assigned on noise-abatement grounds, so expect it to differ from the daytime runway, and "
                "fly the departure procedures precisely.",
            ]},
            {"title": "Winter operations", "body": [
                "De-icing season runs roughly from October to April. The airport runs a common-use de-icing pad, Pad 13, "
                "as the primary pad for scheduled operators; other pads are used only when needed. Wait for the pad's "
                "lights and the de-icing crew before entering a position, and work out your holdover time before taxiing "
                "to the runway.",
                "Snow removal is coordinated from the same area, so expect taxi routes to change during snow events.",
            ]},
            {"title": "Who's who on the cargo ramps", "table": {
                "head": ["Operator", "Where", "Ramp frequency"],
                "rows": [
                    ["DHL Express hub", "South cargo complex", "129.475"],
                    ["PAC (fictional), leased stands P1-P8", "South cargo complex, beside DHL", "129.475 (DHL Ramp)"],
                    ["North Cargo Village (general freight)", "North side", "130.375 (North taxilane)"],
                    ["Amazon Air Hub", "South side", "130.5"],
                    ["FedEx", "West service area", "Ground 121.7 / as instructed"],
                    ["Terminal ramps (passenger)", "Central terminal area", "130.90"],
                ]}},
        ],
        "sources": [
            ["FAA Chart Supplement (via AirNav and SkyVector), effective August 6, 2026", "https://www.airnav.com/airport/KCVG"],
            ["FAA Aeronautical Information Publication, Kentucky aerodromes", "https://www.faa.gov/air_traffic/publications/atpubs/aip_html/part3_ad_2.0_kentucky.html"],
            ["CVG Airport operations memoranda: winter operations and de-icing Pad 13", "https://csinfo.cvgairport.com"],
            ["Air Cargo Week: CVG cargo growth, DHL, Amazon and Atlas Air", "https://aircargoweek.com/cvg-ready-for-take-off"],
            ["FreightWaves: CVG's airside general cargo warehouse", "https://www.freightwaves.com/?p=566333"],
            ["AJOT: CVG Global Logistics Park and the rebuilt airside ramp", "https://www.ajot.com/news/first-site-at-cvg-airport-global-logistics-park-breaks-ground"],
            ["Cincinnati Enquirer (via AOL): DHL and Amazon operations at CVG", "https://www.aol.com/news/epicenter-e-commerce-cvgs-booming-032004496.html"],
        ],
    },
}


def stand_for(icao, aircraft, rng):
    """A PAC stand at a station that has them, sized for the aircraft; None elsewhere."""
    stands = PAC_STANDS.get(icao)
    if not stands:
        return None
    code = AIRCRAFT_CODE.get(aircraft, "D")
    order = "CDEF"
    for c in order[order.index(code):]:  # the right size, or the next size up if none is defined
        if stands.get(c):
            return rng.choice(stands[c])
    return None
