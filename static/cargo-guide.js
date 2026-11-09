/* The PAC Cargo Guide: how freight, the cargo inventory and flight planning fit together. Plain HTML, no API calls,
   so it also works for visitors who aren't signed in. Keep it in step with cargo_network.py, cargo_orders.py,
   dispatch.py and cargo_programs.py when those change. */
function renderCargoGuide() {
  const S_ = [
    ["idea", "The big idea", `
      <p>At PAC, cargo isn't a number on your load sheet that disappears when you land. <b>Every shipment is a real record with its own air waybill (AWB)</b>, a real shipper and consignee, a piece count, a weight, handling codes and a history. It exists before your flight, it rides on your aircraft, and if it isn't at its final destination when you land, it <b>waits at that airport</b> for the next PAC pilot to carry it on.</p>
      <p>That's the whole idea: the airline's freight is shared. What you leave at Miami is what someone else picks up in Miami. The <b>Cargo inventory</b> page (Operations › Cargo inventory) shows all of it.</p>`],
    ["sources", "Where freight comes from", `
      <p>Freight reaches your aircraft three ways:</p>
      <table>
        <tr><th>Your flight's own cargo</th><td>When you open a flight's load sheet, PAC's dispatcher builds a full manifest for that aircraft and route: consignments from companies that really ship through that region, loaded into ULDs (containers and pallets) in real positions, with waybills, handling codes, dangerous goods and security screening. This is most of what you carry.</td></tr>
        <tr><th>Customer orders</th><td>Freight booked by forwarders that's waiting at a station <b>before anyone has booked a flight</b>. PAC's six hubs (KCVG, KMIA, LIMC, OMDW, VHHH, PANC) always hold about six orders each, and the twelve busiest other stations about two each. When you plan a scheduled flight, PAC also makes sure at least a couple of orders are waiting for that exact leg.</td></tr>
        <tr><th>Transfer freight</th><td>Freight another pilot left behind. Some consignments on every flight are booked <b>through</b> the arrival airport to somewhere further on. When that flight lands, those shipments wait at the arrival airport for their next leg.</td></tr>
      </table>`],
    ["planning", "Planning a flight with cargo", `
      <ol>
        <li><b>Pick a flight</b> on the Missions board. If you want to move waiting freight, the Cargo inventory's <b>Find a flight</b> button opens the board already filtered to flights that can carry it.</li>
        <li><b>Open the load sheet.</b> It has three tabs:
          <ul><li><b>Load &amp; limits</b>: payload, fuel, weights against the aircraft's limits, and balance.</li>
          <li><b>Cargo manifest</b>: every unit and position, what's in it, and any special handling.</li>
          <li><b>Cargo folder</b>: the paperwork, including the air waybills, the dangerous goods notice (NOTOC) and the handling timeline.</li></ul></li>
        <li><b>Add waiting freight (optional).</b> Under <b>Transfer cargo at</b> your departure airport you'll see freight that's waiting there and can travel on your flight: it's either going to your destination, or to an airport PAC flies to <b>from</b> your destination. Tick what you want to carry. Its weight comes out of your flight's own cargo, so your total payload stays the same and within limits.</li>
        <li><b>Book the flight</b>, then plan it in SimBrief as usual. The payload on your release already includes the freight you picked.</li>
        <li><b>Arrange the load (optional).</b> On the ACARS page, <b>Load planner</b> lets you drag main-deck units between positions or press <b>Auto-load</b>, with a live bar showing whether the weight sits forward, centered or aft. Saving updates your release, so you'll sign it again.</li>
        <li><b>Fly it with PAC ACARS</b> and file your PIREP.</li>
      </ol>
      <p class="muted">Nothing is reserved until you book. If you cancel the booking, any waiting freight you picked goes back to the station for someone else.</p>`],
    ["filing", "What happens when you file", `
      <p>When your PIREP is filed, every shipment on board is updated automatically:</p>
      <table>
        <tr><th>You landed at its final destination</th><td><b>Delivered</b> (or <b>Delivered late</b> if your flight was late). Its journey is complete.</td></tr>
        <tr><th>It's going further</th><td><b>Waiting</b> at your arrival airport for its next leg. It keeps its AWB and history, and it shows up on that airport's transfer list.</td></tr>
        <tr><th>You diverted</th><td><b>Held</b> at the airport you actually landed at. It can be carried on from there.</td></tr>
        <tr><th>The flight failed</th><td><b>Exception</b>. Staff can see it on the inventory.</td></tr>
        <tr><th>Staff rejected the PIREP</th><td>The cargo goes <b>back where it was</b> before the flight, as if the flight never happened. If staff later accept it, the cargo moves again. This only ever happens once per decision.</td></tr>
      </table>`],
    ["inventory", "Reading the Cargo inventory", `
      <p>Operations › Cargo inventory is the airline's warehouse view.</p>
      <ul>
        <li><b>The summary strip</b> at the top: freight waiting for an onward flight, freight on a booked flight (in the air or about to be), and freight delivered in the last 7 days.</li>
        <li><b>Freight waiting</b>: one card per station and destination, for example "KCVG → KDTW, 2 shipments, 20,830 lb, due 12 NOV". <b>Find a flight</b> opens the Missions board showing flights from that station that can carry it. <b>See the shipments</b> lists them.</li>
        <li><b>The shipment list</b>: AWB, journey (the highlighted airport is where it is now), commodity, shipper and consignee, pieces and weight, status, and when it's due. Filter by station or search for an AWB, a company or a commodity.</li>
        <li><b>A shipment's history</b>: open it from the list to see every step: order received, picked for a flight, each flight that carried it and who flew it, and delivery.</li>
      </ul>`],
    ["orders", "Customer orders and deadlines", `
      <p>Customer orders are marked <b>Customer order</b> in the list and have a <b>due</b> time based on the service the customer paid for: about 24 hours for AOG (aircraft-on-ground) parts, 36 hours for express and live animals, 48 hours for priority, temperature-controlled and valuables, 72 hours for humanitarian cargo and general freight, and 96 hours for dangerous goods. Each order gets up to a day of slack on top.</p>
      <p>If nobody picks an order up within a day after it's due, the forwarder gives it to <b>another carrier</b>: it leaves the inventory with a note in its history. Nobody is penalized, and the station is restocked with fresh orders. Orders only ever appear at real PAC stations, on routes PAC actually flies, and never send freight back where it started.</p>`],
    ["operations", "Operations and campaigns", `
      <p>Sometimes PAC runs an <b>operation</b>, such as Operation Island Supply: a shared goal to deliver a set weight of cargo to certain airports by a date. Every accepted flight that lands cargo at those airports during the operation counts automatically. You'll see the progress bar on the Home page and on the Missions board, along with the top contributors.</p>
      <p>What counts: accepted, successful cargo flights that arrive at a listed destination (the airport you actually landed at must be the one you planned). Checkrides, ferry flights, demo flights and diversions don't count. When an operation that reached its goal ends, every contributor earns its patch on their profile, plus any cash reward announced for it, paid to their wallet. A wrap-up with the final result is posted on the news feed.</p>`],
    ["paperwork", "Paperwork glossary", `
      <table>
        <tr><th>AWB (air waybill)</th><td>The contract and tracking number for one consignment. PAC's prefix is 901. The AWB follows the freight across every leg.</td></tr>
        <tr><th>ULD</th><td>Unit load device: a container (like an AKE) or a pallet (like a PAG or PMC) that freight is built up on and loaded into a position on the aircraft.</td></tr>
        <tr><th>Position</th><td>Where a unit sits: main deck positions (M01, M02…) and lower deck positions, plus bulk holds for loose freight.</td></tr>
        <tr><th>Gross and chargeable weight</th><td>Gross is what the freight weighs. Chargeable is what the customer pays for: the gross weight or the volume weight, whichever is higher.</td></tr>
        <tr><th>Special handling codes</th><td>Short codes that tell the ramp how to treat freight: for example COU (courier), PER (perishable), PIL (pharmaceuticals), AVI (live animals), VAL (valuables), HUM (human remains) and the dangerous goods codes.</td></tr>
        <tr><th>Dangerous goods and NOTOC</th><td>Dangerous goods are listed with their UN number, class and position. The NOTOC (notification to captain) tells you what's on board and where. When it's required, you sign it with the release.</td></tr>
        <tr><th>Security screening</th><td>How the freight was screened (for example X-ray) and its status: SCO means secure for cargo aircraft only, SPX means secure for passenger and cargo aircraft.</td></tr>
        <tr><th>Tracking codes</th><td>The steps on a waybill: RCS (received from shipper), MAN (manifested on a flight), DEP (departed), ARR (arrived), RCF (received from flight), NFD (consignee notified) and DLV (delivered).</td></tr>
      </table>`],
    ["faq", "Questions", `
      <p><b>Do I have to carry waiting freight?</b> No. It's optional. Your flight always has its own cargo. Picking up waiting freight is how you help the network and how freight reaches places no single flight goes.</p>
      <p><b>Does it change my pay or score?</b> No. Your flight is paid and scored the same way. Waiting freight replaces part of your own cargo, so the payload is the same.</p>
      <p><b>Why is a shipment going to an airport my flight doesn't land at?</b> It's routed through your destination. You carry it one leg; it waits there for the next.</p>
      <p><b>I cancelled my booking. What happened to the freight I picked?</b> It went back to the station, unreserved, with a note in its history.</p>
      <p><b>Can I see who flew a shipment?</b> Yes, in its history on the Cargo inventory.</p>`],
  ];
  $("#cargoGuideRoot").innerHTML = `<div class="profile-bar"><h1>PAC Cargo Guide</h1><span class="muted">How PAC's freight, the cargo inventory and flight planning fit together</span></div>
    <div class="handbook"><nav class="toc" aria-label="Cargo guide contents">${S_.map(([id, t]) => `<a href="#cg-${id}" data-cg="${id}">${t}</a>`).join("")}</nav>
    <div class="hb-body">${S_.map(([id, t, body]) => `<section id="cg-${id}"><h2>${t}</h2>${body}</section>`).join("")}</div></div>`;
  document.querySelectorAll("[data-cg]").forEach(a => a.onclick = e => { e.preventDefault(); $("#cg-" + a.dataset.cg).scrollIntoView({ behavior: "smooth" }); });
}
