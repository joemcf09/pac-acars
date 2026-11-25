/* ---------------------------------------------------------------- company: P&L, CEO desk, fleet market, complaints, roles */
function plStatement(list) {
  if (!list || !list.length) return "";
  const m = list[0], rows = (obj, sign) => Object.entries(obj).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="r ${moneyCls(sign * v)}">${money(sign * v)}</td></tr>`).join("");
  const opts = list.map((x, i) => `<option value="${i}">${new Date(x.month + "-02").toLocaleString("en-US", { month: "long", year: "numeric" })}</option>`).join("");
  return `<section class="panel pl-panel"><h2>Profit and loss statement <select id="plMonth" class="pl-pick">${opts}</select></h2><div id="plBody">${plTable(m)}</div></section>`;
}
function plTable(m) {
  const line = (obj, sign) => Object.entries(obj).map(([k, v]) => `<tr><td class="ind">${esc(k)}</td><td class="r">${money(sign * v)}</td></tr>`).join("");
  const sum = o => Object.values(o).reduce((a, b) => a + b, 0);
  return `<table class="fin-table pl-table"><tbody>
    <tr class="pl-h"><td>Freight revenue <span class="muted">(${m.flights} flights)</span></td><td class="r"><b>${money(m.revenue)}</b></td></tr>
    <tr class="pl-h"><td>Operating costs</td><td class="r">${money(-sum(m.operating))}</td></tr>${line(m.operating, -1)}
    <tr class="pl-t"><td>Operating profit</td><td class="r ${moneyCls(m.operating_profit)}"><b>${money(m.operating_profit)}</b></td></tr>
    ${Object.keys(m.people).length ? `<tr class="pl-h"><td>Paid to pilots</td><td class="r">${money(-sum(m.people))}</td></tr>${line(m.people, -1)}` : ""}
    ${Object.keys(m.other).length ? `<tr class="pl-h"><td>Fleet and company</td><td class="r">${money(sum(m.other))}</td></tr>${line(m.other, 1)}` : ""}
    <tr class="pl-t"><td>Net result</td><td class="r ${moneyCls(m.net)}"><b>${money(m.net)}</b></td></tr></tbody></table>`;
}
document.addEventListener("change", e => { if (e.target.id === "plMonth" && S.fin) $("#plBody").innerHTML = plTable(S.fin.statements[+e.target.value]); });
const cDate = t => t ? new Date(t * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "never";
async function loadCrewRest() {
  const el = $("#crewRestNote"); if (!el) return;
  try {
    const d = await api("/api/crew-rest"), m = d.me;
    el.innerHTML = m.away ? `<div class="notice crew-rest ${m.kind === "own" && m.night > 1 ? "warn" : ""}"><b>🛏 Crew rest · ${esc(m.station)}</b> ${esc(m.text)}</div>` : "";
  } catch (e) { el.innerHTML = ""; }
}
async function staffCeo() {
  const body = $("#staffBody"); body.innerHTML = `<p class="muted">Loading the CEO desk…</p>`;
  let d; try { d = await api("/api/staff/ceo"); } catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const hubs = d.hubs.map(h => `<div class="ceo-hub${h.visited_this_quarter ? " done" : ""}"><div class="ceo-hub-h"><b>${esc(h.icao)}</b> ${esc(h.city)}${h.visited_this_quarter ? '<span class="tag green">Visited this quarter</span>' : '<span class="tag amber">Visit due</span>'}</div>
    <div class="ceo-hub-s"><span>Waiting<b>${h.waiting} · ${fmt(h.waiting_lbs)} lb</b></span><span>On time (30 days)<b>${h.on_time_pct == null ? "–" : h.on_time_pct + "%"}</b></span><span>Arrivals<b>${h.arrivals_30d}</b></span></div>
    <div class="muted">Aircraft here: ${Object.entries(h.aircraft).map(([k, v]) => `${v} ${esc(k.toLowerCase())}`).join(", ") || "none"} · last visit ${cDate(h.last_visit)}</div>
    ${d.location === h.icao ? `<div class="ceo-here">📍 You're here</div>` : `<button class="btn ghost small" type="button" data-travel="${esc(h.icao)}">Travel here</button>`}<div class="ceo-travel" data-travel-box="${esc(h.icao)}"></div></div>`).join("");
  const acc = d.accounts.length ? d.accounts.map(a => `<tr><td><b>${esc(a.shipper)}</b></td><td><span class="tag ${a.tier === "At risk" ? "" : "amber"}">${esc(a.tier)}</span> ${a.score}</td><td>${a.on_time} on time · ${a.late} late · ${a.failed} failed</td><td>${a.station ? `Fly to <b>${esc(a.station)}</b>` : "–"}</td></tr>`).join("")
    : `<tr><td colspan="4" class="muted">Every shipper is in good standing. Nobody needs a visit.</td></tr>`;
  body.innerHTML = `<p class="muted">Your work as CEO. You're at <b>${esc(d.location || "–")}</b>. Arriving at a hub counts as a hub visit, however you get there: fly a PAC flight, ride along on a freighter, buy a commercial ticket or charter a jet (use <b>Travel here</b>). Arriving at a struggling shipper's home station and their standing goes up by ${d.visit_bonus} for ${d.visit_days} days. Company cash: <b>${money(d.cash)}</b>.</p>
    <h3>Hub visits <span class="muted">(aim for every hub each quarter)</span></h3><div class="ceo-hubs">${hubs}</div>
    <div id="ceoRest"></div>
    ${(() => { const n = d.hub_network; if (!n) return "";
      return `<h3>Hub network <span class="muted">(${n.count} of ${n.max} hubs · opening one costs ${money(n.open_cost)} up front and ${money(n.monthly_cost)} a month)</span></h3>
      ${n.opened.length ? `<p class="muted">Opened by PAC: ${n.opened.map(o => `<b>${esc(o.icao)}</b> ${esc(o.city)} <button class="btn ghost small" type="button" data-hub-close="${esc(o.icao)}">Close</button>`).join(" · ")}</p>` : ""}
      <p class="muted" style="margin:4px 0">Where PAC already flies most (last 90 days):</p>
      <div class="row" style="flex-wrap:wrap;gap:8px">${n.candidates.length ? n.candidates.map(c => `<button class="btn ghost small" type="button" data-hub-open="${esc(c.icao)}" title="${c.arrivals_90d} arrivals by ${c.pilots} pilots in 90 days">Open ${esc(c.icao)} · ${esc(c.city)} (${c.arrivals_90d} arr.)</button>`).join("") : `<span class="muted">No candidates yet.</span>`}</div>
      <div class="row" style="gap:8px;margin-top:8px"><input id="hubIcao" placeholder="Or any airport ICAO" maxlength="4" style="max-width:170px;text-transform:uppercase"><button class="btn small" type="button" id="hubOpenBtn">Open hub</button></div>`; })()}
    <h3>Key accounts that need you</h3><div class="table-wrap"><table class="fin-table"><thead><tr><th>Shipper</th><th>Standing</th><th>Last 90 days</th><th>Visit</th></tr></thead><tbody>${acc}</tbody></table></div>
    <h3>Letter from the CEO <span class="muted">(${new Date(d.letter.month + "-02").toLocaleString("en-US", { month: "long", year: "numeric" })})</span></h3>
    ${d.letter.posted ? `<p class="notice">Posted ${cDate(d.letter.posted)}. You can edit and post it again.</p>` : `<p class="muted">Drafted from last month's real numbers. Edit it to sound like you, then post it to the news feed.</p>`}
    <textarea id="ceoLetter" rows="14" style="width:100%">${esc(d.letter.draft)}</textarea><p><button class="btn" id="ceoPost" type="button">Post to the news feed</button></p>
    <h3>Pilot of the month</h3>${d.awards.length ? `<ul>${d.awards.map(a => `<li><b>${esc(new Date(a.month + "-02").toLocaleString("en-US", { month: "long", year: "numeric" }))}:</b> ${a.name ? `${esc(a.name)} · ${a.flights} flights, ${a.hours} h, ${a.smooth} smooth landings` : "nobody flew enough that month"}</li>`).join("")}</ul>` : `<p class="muted">Chosen automatically on the 1st of each month and announced in the news.</p>`}
    <h3>Recent visits</h3>${d.visits.length ? `<ul>${d.visits.map(v => `<li>${cDate(v.time)}: ${v.kind === "hub" ? `hub visit, ${esc(v.place)}` : `account visit to ${esc(v.shipper)} at ${esc(v.place)}`}</li>`).join("")}</ul>` : `<p class="muted">None yet.</p>`}`;
  const openHub = async icao => {
    icao = String(icao || "").toUpperCase().trim(); if (!icao) return;
    const n = d.hub_network || {};
    if (!confirm(`Open a PAC hub at ${icao}? It costs ${money(n.open_cost)} now and ${money(n.monthly_cost)} a month in station costs.`)) return;
    try { const r = await api("/api/staff/ceo/hub", { method: "POST", body: { icao } }); toast(`${r.city} is now a PAC hub.`); location.reload(); }
    catch (e) { toast(e.message); }
  };
  body.querySelectorAll("[data-hub-open]").forEach(b => b.onclick = () => openHub(b.dataset.hubOpen));
  if ($("#hubOpenBtn")) $("#hubOpenBtn").onclick = () => openHub($("#hubIcao").value);
  body.querySelectorAll("[data-hub-close]").forEach(b => b.onclick = async () => {
    if (!confirm(`Close the ${b.dataset.hubClose} hub? Its monthly station costs stop; the setup cost isn't refunded.`)) return;
    try { await api("/api/staff/ceo/hub", { method: "POST", body: { action: "close", icao: b.dataset.hubClose } }); location.reload(); } catch (e) { toast(e.message); }
  });
  body.querySelectorAll("[data-travel]").forEach(btn => btn.onclick = async () => {
    const to = btn.dataset.travel, box = body.querySelector(`[data-travel-box="${to}"]`);
    box.innerHTML = `<p class="muted">Your assistant is checking the options…</p>`;
    try {
      const q = await api(`/api/staff/ceo/travel?to=${encodeURIComponent(to)}`);
      box.innerHTML = `<p class="muted" style="margin:6px 0">${esc(q.from)} → ${esc(q.to)} · ${fmt(q.distance_nm)} nm</p>` + q.options.map(o => `<button class="ceo-trip" type="button" data-how="${esc(o.kind)}">
        <span><b>${esc(o.label)}</b><small>${esc(o.note)}</small></span><em>${o.cost ? money(o.cost) : "Free"}</em></button>`).join("");
      box.querySelectorAll("[data-how]").forEach(b2 => b2.onclick = async () => {
        try {
          const r = await api("/api/staff/ceo/travel", { method: "POST", body: { to, how: b2.dataset.how } });
          toast(`Arrived at ${r.location}${r.cost ? ` · ${money(r.cost)} executive travel` : ""}${r.visits.some(v => v.kind === "hub") ? " · hub visit logged" : ""}.`);
          staffCeo();
        } catch (e) { toast(e.message); }
      });
    } catch (e) { box.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; }
  });
  api("/api/crew-rest").then(r => { const h = r.hq, el = $("#ceoRest"); if (el) el.innerHTML = `<h3>KCVG crew rest rooms <span class="muted">(${h.used} of ${h.rooms} beds in use${h.used ? ` · saving $${fmt(h.saved_per_night)} a night in hotels` : ""})</span></h3><p class="muted">${h.guests.length ? h.guests.map(g => esc(g.name || g.pilot_id)).join(", ") : "All rooms free tonight."}</p>`; }).catch(() => { });
  body.insertAdjacentHTML("beforeend", `<div id="growthBox"><p class="muted">Loading network and safety…</p></div>`);
  staffGrowth();
  $("#ceoPost").onclick = async () => { try { await api("/api/staff/ceo/letter", { method: "POST", body: { month: d.letter.month, body: $("#ceoLetter").value } }); toast("Letter posted."); staffCeo(); } catch (e) { toast(e.message); } };
}
async function staffGrowth() {
  const box = $("#growthBox"); if (!box) return;
  let d; try { d = await api("/api/staff/growth"); } catch (e) { box.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const a = d.audit;
  const ST = { proposed: '<span class="tag amber">Waiting for its proving flight</span>', proven: '<span class="tag green">Proven: on the schedule</span>', cancelled: '<span class="tag dark">Cancelled</span>' };
  box.innerHTML = `
    <h3>Safety audit <span class="muted">(last 12 months)</span> ${a.flights < 10 ? '<span class="tag">Not enough flights yet</span>' : a.passed ? '<span class="tag green">Passed</span>' : '<span class="tag">Needs work</span>'}</h3>
    <div class="ceo-hub-s"><span>Flights<b>${a.flights}</b></span><span>Avg landing<b>${a.avg_rate == null ? "–" : a.avg_rate + " fpm"}</b></span><span>Hard landings<b>${a.hard_pct}%</b></span><span>On time<b>${a.on_time == null ? "–" : a.on_time + "%"}</b></span><span>Groundings<b>${a.aog}</b></span><span>Ramp findings<b>${a.findings} in ${a.inspections}</b></span></div>
    <ul class="audit">${a.checks.map(c => `<li>${c.ok ? "✓" : "✗"} ${esc(c.text)}</li>`).join("")}</ul>
    <h3>Open a new route <span class="muted">(the first flight anyone files between the two airports proves it)</span></h3>
    <div class="mkt-order"><label>From <input id="prO" placeholder="KCVG" maxlength="4" size="6"></label><label>To <input id="prD" placeholder="EGNX" maxlength="4" size="6"></label><button class="btn" id="prGo" type="button">Propose route</button></div>
    ${d.proposals.length ? `<div class="table-wrap"><table class="fin-table"><tbody>${d.proposals.map(p => `<tr><td><b>${esc(p.origin)}–${esc(p.dest)}</b></td><td>${ST[p.status] || esc(p.status)}</td><td class="muted">${cDate(p.proposed)}</td><td>${p.status === "proposed" ? `<button class="btn ghost" type="button" data-prx="${p.id}">Cancel</button>` : ""}</td></tr>`).join("")}</tbody></table></div>` : ""}
    <h3>Next hub candidates <span class="muted">(busiest non-hub stations, last 90 days)</span></h3>
    ${d.candidates.length ? `<ol>${d.candidates.map(c => `<li><b>${esc(c.icao)}</b>: ${c.arrivals_90d} arrivals by ${c.pilots} pilot${c.pilots === 1 ? "" : "s"}</li>`).join("")}</ol>` : `<p class="muted">Not enough traffic yet.</p>`}
    <h3>Ramp inspections</h3>
    ${d.ramp.length ? `<ul>${d.ramp.map(r => `<li>${cDate(r.time)} · ${esc(r.station)} · ${esc(r.pilot || "")}: ${r.findings.length ? r.findings.map(esc).join(" ") : "no findings"}</li>`).join("")}</ul>` : `<p class="muted">About one arrival in ${12} gets a ramp inspection. None yet.</p>`}
    <h3>Mentoring <span class="muted">(both pilots get $${d.mentor_bonus} after the mentee's first ${d.mentor_flights} flights)</span></h3>
    <div class="mkt-order"><label>Mentor <input id="mnA" placeholder="PAC0001" size="9"></label><label>New pilot <input id="mnB" placeholder="PAC0007" size="9"></label><button class="btn" id="mnGo" type="button">Pair them</button></div>
    ${d.mentors.length ? `<ul>${d.mentors.map(m => `<li>${esc(m.mentor_name || m.mentor)} → ${esc(m.mentee_name || m.mentee)}: ${m.status === "done" ? "complete" : `${m.flights} of ${d.mentor_flights} flights`}</li>`).join("")}</ul>` : ""}
    <h3>Seniority <span class="muted">(senior pilots get first pick on new trips for 12 hours)</span></h3>
    <ol>${d.seniority.map(p => `<li>${esc(p.name || p.pilot_id)} <span class="muted">${esc(p.pilot_id)}</span></li>`).join("")}</ol>`;
  const post = async (act, x) => { try { await api(`/api/staff/growth/${act}`, { method: "POST", body: x }); staffGrowth(); return true; } catch (e) { toast(e.message); } };
  $("#prGo").onclick = async () => { if (await post("propose", { origin: $("#prO").value, dest: $("#prD").value })) toast("Route proposed: it opens after its proving flight."); };
  box.querySelectorAll("[data-prx]").forEach(b => b.onclick = () => post("cancel_route", { id: +b.dataset.prx }));
  $("#mnGo").onclick = async () => { if (await post("mentor", { mentor: $("#mnA").value, mentee: $("#mnB").value })) toast("Mentoring pair set up."); };
}
async function staffMarket() {
  const body = $("#staffBody"); body.innerHTML = `<p class="muted">Loading the fleet market…</p>`;
  let d; try { d = await api("/api/staff/market"); } catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const WAY = { new: "Buy new", conversion: "Buy used + convert", used: "Buy used", lease: "Lease", wet: "Wet lease (ACMI)" };
  const filter = S.mktWay || "all";
  const list = d.offers.filter(o => filter === "all" || o.way === filter);
  const price = o => o.price ? money(o.price) : o.monthly ? `${money(o.monthly)} <small>/ month</small>` : `${money(o.weekly)} <small>/ week</small>`;
  const card = o => `<div class="mkt-card"><div class="mkt-co">${o.logo ? `<img src="${esc(o.logo)}" alt="${esc(o.company_name)}">` : `<span class="mkt-name">${esc(o.company_name || "Second-hand market")}</span>`}<small>${esc(o.company_kind || "Used aircraft")}${o.company_country ? " · " + esc(o.company_country) : ""}</small></div>
    <div class="mkt-ac"><b>${esc(o.aircraft_name)}</b><span class="tag dark">${esc(WAY[o.way])}</span></div><p class="muted">${esc(o.what)}</p>
    <div class="mkt-foot"><span class="mkt-price">${price(o)}</span><span class="muted">ready in ${o.lead_days} days</span><button class="btn" type="button" data-offer="${esc(o.id)}">Choose</button></div></div>`;
  const owned = d.fleet.map(f => `<tr><td><b>${esc(f.reg)}</b></td><td>${esc(f.type)}</td><td>${esc(f.status)}</td><td>${esc(f.ownership === "wet_lease" ? "Wet lease" : f.ownership === "leased" ? "Leased" : f.ownership === "owned" ? "Bought" : "Original fleet")}${f.owner_company ? " · " + esc(d.companies[f.owner_company]?.name || "") : ""}</td><td>${f.lease_rate ? money(f.lease_rate) + (f.ownership === "wet_lease" ? "/wk" : "/mo") : ""}</td><td><button class="btn ghost" type="button" data-back="${esc(f.reg)}">${f.sale_value != null ? "Sell · " + money(f.sale_value) : "Return"}</button></td></tr>`).join("");
  body.innerHTML = `<p class="muted">How real cargo airlines get aircraft. Company cash: <b>${money(d.cash)}</b>. Purchases are paid now; leases are charged monthly; wet leases are paid up front by the week.</p>
    <div class="mkt-filter">${["all", "new", "conversion", "used", "lease", "wet"].map(k => `<button type="button" class="btn ${filter === k ? "" : "ghost"}" data-way="${k}">${k === "all" ? "All" : WAY[k]}</button>`).join("")}</div>
    ${filter === "new" || filter === "all" ? `<p class="notice">${esc(d.companies.airbus.note)}</p>` : ""}
    <div class="mkt-grid">${list.map(card).join("") || `<p class="muted">No offers of this kind for PAC's types.</p>`}</div>
    <div id="mktForm"></div>
    ${owned ? `<h3>PAC's aircraft</h3><p class="muted">Selling the last aircraft of a type takes that type out of the fleet; buying or leasing one brings it back.</p><div class="table-wrap"><table class="fin-table"><thead><tr><th>Reg</th><th>Type</th><th>Status</th><th>How</th><th>Rate</th><th></th></tr></thead><tbody>${owned}</tbody></table></div>` : ""}
    <p class="muted mkt-disc">${esc(d.disclaimer)}</p>`;
  body.querySelectorAll("[data-way]").forEach(b => b.onclick = () => { S.mktWay = b.dataset.way; staffMarket(); });
  body.querySelectorAll("[data-back]").forEach(b => b.onclick = async () => { if (!b.dataset.armed) { b.dataset.armed = 1; b.textContent = "Tap again to confirm"; return; }
    try { const r = await api(`/api/staff/market/return/${encodeURIComponent(b.dataset.back)}`, { method: "POST" }); toast(`${b.dataset.back} ${r.note}.`); staffMarket(); } catch (e) { toast(e.message); } });
  body.querySelectorAll("[data-offer]").forEach(b => b.onclick = () => {
    const o = d.offers.find(x => x.id === b.dataset.offer);
    $("#mktForm").innerHTML = `<section class="panel mkt-order"><h3>${esc(WAY[o.way])}: ${esc(o.aircraft_name)}${o.company_name ? " from " + esc(o.company_name) : ""}</h3>
      <label>Registration <input id="mktReg" placeholder="N306PC" maxlength="8"></label>
      <label>Based at <select id="mktHub">${d.hubs.map(h => `<option>${h}</option>`).join("")}</select></label>
      ${o.way === "wet" ? `<label>Weeks <input id="mktWeeks" type="number" min="1" max="12" value="4"></label>` : ""}
      <p class="muted">${o.way === "new" ? "Delivered at the factory: you fly it home." : `Delivered at your chosen hub in ${o.lead_days} days.`}</p>
      <button class="btn" id="mktGo" type="button">Confirm</button> <button class="btn ghost" id="mktX" type="button">Cancel</button></section>`;
    $("#mktForm").scrollIntoView({ behavior: "smooth" });
    $("#mktX").onclick = () => { $("#mktForm").innerHTML = ""; };
    $("#mktGo").onclick = async () => { try { const r = await api("/api/staff/market/order", { method: "POST", body: { offer: o.id, reg: $("#mktReg").value, hub: $("#mktHub").value, weeks: $("#mktWeeks")?.value } });
      toast(`${r.reg} ordered: ready at ${r.deliver_to} on ${cDate(r.deliver_at)}.`); staffMarket(); } catch (e) { toast(e.message); } };
  });
}
async function staffComplaints(body = $("#staffBody")) {
  body.innerHTML = `<p class="muted">Loading complaints…</p>`;
  let d; try { d = await api("/api/staff/complaints"); } catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const R = Object.fromEntries(d.responses.map(r => [r.key, r]));
  body.innerHTML = `<p class="muted">Shippers write in after a late or failed delivery. How PAC answers changes their standing for 90 days. Goodwill costs come out of company cash.</p>
    ${d.complaints.map(c => `<div class="cmp ${c.status}"><div><b>${esc(c.shipper)}</b> <span class="tag ${c.kind === "failed" ? "" : "amber"}">${c.kind === "failed" ? "Failed shipment" : "Late delivery"}</span> <span class="muted">AWB ${esc(c.awb)} · ${esc(c.station || "")} · ${cDate(c.created)}</span></div>
      <p>${c.kind === "failed" ? `"Our shipment never arrived. We need to understand what happened and whether we can keep relying on PAC."` : `"Our shipment arrived late and our customer noticed. Please make sure it doesn't happen again."`}</p>
      ${c.standing ? `<p class="muted">Account standing: ${esc(c.standing.tier)} (${c.standing.score})</p>` : ""}
      ${c.status === "open" ? `<div class="cmp-acts">${d.responses.map(r => `<button class="btn ${r.key === "apology" ? "ghost" : ""}" type="button" data-c="${c.id}" data-r="${r.key}">${esc(r.label)} <small>+${r.delta}${r.cost ? " · " + money(r.cost) : ""}</small></button>`).join("")}</div>`
        : `<p class="tag green">Answered: ${esc(R[c.response]?.label || c.response)}</p>`}</div>`).join("") || `<p class="muted">No complaints. Keep the freight on time.</p>`}`;
  body.querySelectorAll("[data-c]").forEach(b => b.onclick = async () => { try { const r = await api(`/api/staff/complaints/${b.dataset.c}`, { method: "POST", body: { response: b.dataset.r } }); toast(`${r.shipper}: standing +${r.delta}.`); staffComplaints(body); } catch (e) { toast(e.message); } });
}
/* ---------------- Commercial (scoped: Commercial Director + full admin) ---------------- */
async function loadCommercial() {
  const root = $("#commercialRoot");
  if (!root) return;
  S.commercialTab = S.commercialTab || "complaints";
  const tabs = [["complaints", "Complaints"], ["accounts", "Shipper accounts"], ["lanes", "Lane reputation"], ["featured", "Featured shipments"]];
  root.innerHTML = `<div class="profile-bar"><h1>Commercial</h1><span class="muted">Shipper relations and freight marketing: answer complaints, watch account standing and lane reputation, and spotlight featured shipments.</span></div>
    <div class="msg-tabs" style="margin-bottom:16px">${tabs.map(([k, t]) => `<button class="${S.commercialTab === k ? "on" : ""}" data-xtab="${k}">${t}</button>`).join("")}</div>
    <div id="commercialBody"></div>`;
  root.querySelectorAll("[data-xtab]").forEach(b => b.onclick = () => { S.commercialTab = b.dataset.xtab; loadCommercial(); });
  const body = $("#commercialBody");
  if (S.commercialTab === "accounts") commAccounts(body);
  else if (S.commercialTab === "lanes") commLanes(body);
  else if (S.commercialTab === "featured") { body.innerHTML = `<div id="commShipments"></div>`; loadShipmentEditor($("#commShipments")); }
  else staffComplaints(body);
}
const TIER_TAG = { "Preferred": "green", "Good": "grey", "Under review": "amber", "At risk": "" };
function tierTag(t) { return `<span class="tag ${TIER_TAG[t] || "grey"}" style="margin:0">${esc(t)}</span>`; }
async function commAccounts(body) {
  body.innerHTML = `<p class="muted">Loading shipper accounts…</p>`;
  let d; try { d = await api("/api/staff/accounts"); } catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const row = a => `<tr><td><b>${esc(a.shipper)}</b></td><td>${tierTag(a.tier)} <span class="muted">${a.score}</span></td><td class="r">${fmt(a.on_time)}</td><td class="r">${fmt(a.late)}</td><td class="r">${fmt(a.failed)}</td><td class="r">${fmt(a.rolled)}</td><td class="r">${fmt(a.shipments)}</td></tr>`;
  body.innerHTML = `<p class="muted" style="max-width:90ch">Every shipper's standing over the last 90 days. On-time deliveries raise it; late, failed and rolled shipments lower it. Answering complaints well and keeping freight on time wins an account back.</p>
    ${d.needs_attention.length ? `<div class="notice" style="border-left:3px solid var(--red)"><b>Needs attention (${d.needs_attention.length}):</b> ${d.needs_attention.map(a => esc(a.shipper) + " · " + esc(a.tier)).join(" &nbsp;|&nbsp; ")}</div>` : ""}
    ${d.accounts.length ? `<div class="table-wrap"><table class="fin-table"><thead><tr><th>Shipper</th><th>Standing</th><th class="r">On time</th><th class="r">Late</th><th class="r">Failed</th><th class="r">Rolled</th><th class="r">Shipments</th></tr></thead><tbody>${d.accounts.map(row).join("")}</tbody></table></div>` : `<p class="muted">No shipper activity in the last 90 days yet.</p>`}`;
}
async function commLanes(body) {
  body.innerHTML = `<p class="muted">Loading lane reputation…</p>`;
  let d; try { d = await api("/api/staff/lanes"); } catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  body.innerHTML = `<p class="muted" style="max-width:90ch">How PAC performs on each route in customers' eyes over the last 90 days. Strong lanes attract more orders; weak ones get fewer. Weakest lanes first.</p>
    ${d.lanes.length ? `<div class="table-wrap"><table class="fin-table"><thead><tr><th>Lane</th><th>Reputation</th><th class="r">Flights</th><th class="r">On time</th><th class="r">Late</th><th class="r">Care issues</th><th class="r">Failed</th></tr></thead><tbody>${d.lanes.map(l => `<tr><td><b>${esc(l.origin)} → ${esc(l.destination)}</b></td><td>${tierTag(l.tier)} <span class="muted">${l.score}</span></td><td class="r">${fmt(l.flights)}</td><td class="r">${fmt(l.on_time)}</td><td class="r">${fmt(l.late)}</td><td class="r">${fmt(l.care_issues)}</td><td class="r">${fmt(l.failed)}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">No lane activity in the last 90 days yet.</p>`}`;
}
async function staffRoles() {
  const body = $("#staffBody"); body.innerHTML = `<p class="muted">Loading roles…</p>`;
  let d; try { d = await api("/api/staff/roles"); } catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const by = {}; d.holders.forEach(h => (by[h.role] = by[h.role] || []).push(h));
  body.innerHTML = `<p class="muted">Management work follows the role, not the account. Hand a role to a pilot and its tasks move with it. Only the CEO can change roles.</p>
    <div class="table-wrap"><table class="fin-table"><thead><tr><th>Role</th><th>What they own</th><th class="r">Weekly pay</th><th>Held by</th></tr></thead><tbody>
    ${d.roles.map(r => `<tr><td><b>${esc(r.title)}</b></td><td class="muted">${esc(r.does)}<details><summary>What to watch and do</summary><p><b>Watch:</b> ${esc(r.watch)}</p><p><b>Action:</b> ${esc(r.action)}</p></details></td><td class="r">${r.pay ? "$" + r.pay.toLocaleString("en-US") + "/wk" : "—"}</td><td>${(by[r.key] || []).map(h => `${esc(h.name || h.pilot_id)} <span class="muted">${esc(h.pilot_id)}</span>${d.can_assign ? ` <button class="btn ghost" type="button" data-rm="${esc(h.pilot_id)}|${r.key}">Remove</button>` : ""}`).join("<br>") || '<span class="muted">Open</span>'}</td></tr>`).join("")}</tbody></table></div>
    ${d.can_assign ? `<section class="panel mkt-order"><h3>Give a role</h3><label>Pilot ID <input id="roPid" placeholder="PAC0002"></label><label>Role <select id="roRole">${d.roles.map(r => `<option value="${r.key}">${esc(r.title)}</option>`).join("")}</select></label><button class="btn" id="roGo" type="button">Give role</button></section>` : ""}`;
  const send = async x => { try { await api("/api/staff/roles", { method: "POST", body: x }); staffRoles(); } catch (e) { toast(e.message); } };
  body.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { const [p, r] = b.dataset.rm.split("|"); send({ pilot_id: p, role: r, remove: true }); });
  if ($("#roGo")) $("#roGo").onclick = () => send({ pilot_id: $("#roPid").value, role: $("#roRole").value });
}

async function staffRelief(host = $("#staffBody")) {
  const body = host;
  body.innerHTML = `<p class="muted">Checking disaster alerts…</p>`;
  let d;
  try { d = await api("/api/staff/relief"); } catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const when = t => t ? new Date(t * 1000).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "never";
  const tag = { draft: '<span class="tag amber">Waiting for review</span>', later: '<span class="tag amber">Remind later</span>', posted: '<span class="tag green">Posted</span>',
    held: '<span class="tag">Held</span>', dismissed: '<span class="tag dark">Dismissed</span>', closed: '<span class="tag dark">Closed</span>' };
  const checks = [["facts", "The facts match the linked source, and nothing is exaggerated or guessed."],
    ["help", "The affected country has asked for, or accepted, international relief flights, so an airlift from a UN depot is realistic."],
    ["tone", "The wording is calm and respectful: no hype, nothing that makes it sound exciting."],
    ["links", "The “How to help” links go to real, active appeals."],
    ["timing", "The timing is right: the event is active or recent and relief flights are relevant now. For something that just happened and may not need an airlift yet, waiting a day or two is fine."]];
  const draftHTML = x => {
    const open = x.status === "draft" || x.status === "later";
    return `<details class="relief-draft" ${open && x === d.drafts.find(y => y.status === "draft" || y.status === "later") ? "open" : ""}>
    <summary><b>${esc(x.label || x.title)}</b> <span class="muted mono">· ${esc(x.alert)} · drafted ${esc(when(x.created))}</span> ${tag[x.status] || ""}</summary>
    <div class="relief-draft-body">
      ${x.held ? `<p><b>Held:</b> ${esc(x.reason)}</p>` : `
      <div class="relief-facts"><div><small>Route</small><b class="mono">${esc(x.origin)} → ${esc(x.destination)}</b></div><div><small>Distance</small><b>${fmt(x.distance_nm)} nm</b></div>
        <div><small>Aircraft</small><b>${esc(S.fleet[x.aircraft]?.name || x.aircraft)}</b></div><div><small>Payload</small><b>${fmt(x.payload_kg)} kg</b></div></div>
      <p class="muted" style="font-size:14px">From the humanitarian depot at ${esc(x.depot_city)} to ${esc(x.dest_name || x.dest_city)}, ${fmt(x.event_to_airport_nm)} nm from the event. ${esc(x.severity || "")}</p>
      <p style="font-size:14px">Cargo: ${x.cargo.map(i => `${esc(i.item)} (${esc(i.pieces)})`).join(" · ")}</p>`}
      <p style="font-size:14px">Source: <a href="${esc(x.report_url)}" target="_blank" rel="noopener">GDACS alert</a>${x.mission_id ? ` · Mission <b class="mono">${esc(x.mission_id)}</b>` : ""}${x.status === "later" && x.post_after ? ` · Remind after ${esc(when(x.post_after))}` : ""}</p>
      ${open ? `<form class="relief-form" data-id="${esc(x.id)}">
        <label>Aircraft <select name="aircraft">${(x.aircraft_options || []).map(t => `<option value="${esc(t)}" ${t === x.aircraft ? "selected" : ""}>${esc(S.fleet[t]?.name || t)}</option>`).join("")}</select></label>
        <label>Note added to the briefing (optional)<textarea name="note" rows="2" maxlength="600">${esc(x.note || "")}</textarea></label>
        <fieldset><legend>How to help links (title | https:// link, one per line)</legend><textarea name="helplinks" rows="3">${esc(x.help.map(h => h.join(" | ")).join("\n"))}</textarea></fieldset>
        <button class="btn ghost small" type="button" data-act="edit">Save changes</button>
        <fieldset class="relief-checks"><legend>Before you post: all five must be ticked</legend>${checks.map(([k, t]) => `<label><input type="checkbox" name="${k}"> ${t}</label>`).join("")}</fieldset>
        <div class="row" style="gap:10px;flex-wrap:wrap"><button class="btn small" type="button" data-act="post" disabled>Post mission</button>
          <button class="btn ghost small" type="button" data-act="later">Remind me in 24 hours</button><button class="btn ghost small" type="button" data-act="dismiss">Dismiss</button></div>
        <p class="muted" style="font-size:13px">Dismissed drafts never come back for the same event.</p></form>`
      : x.status === "posted" ? `<button class="btn ghost small" type="button" data-close="${esc(x.id)}">Close this mission now</button>` : ""}
    </div></details>`;
  };
  body.innerHTML = `<p class="muted" style="max-width:90ch">Drafts come from real <a href="https://www.gdacs.org/" target="_blank" rel="noopener">GDACS</a> alerts at Orange or Red level for earthquakes, tropical cyclones, floods and volcanoes from the last two weeks. Nothing is posted until you review it. Events that ended more than three days ago are skipped, and events in PAC's conflict zones are held. Last checked: ${esc(when(d.fetched))}.</p>
    ${d.error ? `<div class="notice err">Couldn't reach GDACS on the last check (${esc(d.error)}). It tries again within the hour.</div>` : ""}
    ${d.drafts.length ? d.drafts.map(draftHTML).join("") : `<p>No drafts. When a serious disaster is reported, a draft appears here for you to review.</p>`}`;
  const send = async (id, act, payload) => {
    try { await api(`/api/staff/relief/${encodeURIComponent(id)}/${act}`, { method: "POST", body: payload || {} }); return true; } catch (e) { toast(e.message); return false; }
  };
  body.querySelectorAll(".relief-form").forEach(f => {
    const id = f.dataset.id, post = f.querySelector('[data-act="post"]');
    const ready = () => { post.disabled = !checks.every(([k]) => f[k].checked); };
    checks.forEach(([k]) => f[k].onchange = ready);
    const edits = () => ({ aircraft: f.aircraft.value, note: f.note.value,
      help: f.helplinks.value.split("\n").map(l => l.split("|").map(x => x.trim())).filter(p => p.length >= 2).map(p => [p[0], p.slice(1).join("|")]) });
    f.querySelector('[data-act="edit"]').onclick = async () => { if (await send(id, "edit", edits())) { toast("Draft saved."); staffRelief(host); } };
    post.onclick = async () => {
      if (!(await send(id, "edit", edits()))) return;
      const checksOn = Object.fromEntries(checks.map(([k]) => [k, f[k].checked]));
      if (await send(id, "post", { checks: checksOn })) { toast("Relief mission posted."); staffRelief(host); }
    };
    f.querySelector('[data-act="later"]').onclick = async () => { if (await send(id, "later", { hours: 24 })) { toast("We'll keep it for later."); staffRelief(host); } };
    f.querySelector('[data-act="dismiss"]').onclick = async () => { if (await send(id, "dismiss")) { toast("Dismissed."); staffRelief(host); } };
  });
  body.querySelectorAll("[data-close]").forEach(b => b.onclick = async () => { if (await send(b.dataset.close, "close")) { toast("Mission closed."); staffRelief(host); } });
}
