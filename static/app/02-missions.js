/* ---------------- mission board ---------------- */
const REGIONS = ["All", "US domestic", "Americas", "Transatlantic", "Europe", "Middle East & Africa", "Asia-Pacific", "Transpacific"];
S.board = S.board || "all"; S.region = "All"; S.netSearch = ""; S.netLimit = 40; S.charterSpec = null;
document.querySelectorAll("[data-board]").forEach(b => b.onclick = () => {
  S.board = b.dataset.board; S.netLimit = 40;
  const pool = S.board === "all" ? missionBoardPool() : S.board === "missions" ? [...(S.checkrides || []), ...S.missions] : S.board === "partners" ? (S.jobs || []).filter(m => m.contract) : S.board === "network" ? S.routes : S.board === "rotations" ? rotationBoardList() : S.board === "events" ? eventsBoardList() : S.board === "urgent" ? (S.urgent || []) : S.board === "jobs" ? (S.jobs || []).filter(m => !m.contract) : S.board === "trips" ? tripBoardList() : (S.charterMission ? [S.charterMission] : []);
  if (!pool.some(m => m.id === S.selected?.id)) { S.selected = S.board === "charter" ? S.charterMission || null : null; S.ofp = null; S.ofpErrors = []; S.ofpWarnings = []; S.planned = false; if (S.selected) S.aircraft = S.selected.aircraft[0]; }
  renderMissions();
});

/* "MSFS and X-Plane" types show under both simulator filters */
function fliesIn(code, sim) { return (S.fleet[code]?.sim || "MSFS").includes(sim); }
/* PAC ACARS versions: a fourth number is a hotfix, shown as "1.1.2 hotfix 1" */
function verLabel(v) { const p = String(v || "").split("."); return p.length > 3 && +p[3] ? `${p.slice(0, 3).join(".")} hotfix ${+p[3]}` : p.slice(0, 3).join("."); }
function allFlights() { return [...(S.checkrides || []), ...S.missions, ...S.routes, ...(S.tourLegs || []), ...(S.urgent || []), ...(S.jobs || []), ...(S.trips?.mine?.legs || []), ...(S.charterMission ? [S.charterMission] : []), ...(S.booking?.mission?.urgent ? [S.booking.mission] : [])]; }
/* rotations: the next leg of each, for this pilot */
function rotationBoardList() {
  const nx = S.rotationNext || {};
  return (S.rotations || []).map(r => (S.tourLegs || []).find(l => l.id === (nx[r.id] || `PAC${r.series + 1}`))).filter(Boolean);
}
function rotationStrip(m) {
  const r = (S.rotations || []).find(x => x.id === m.rotation);
  if (!r) return "";
  const pr = (S.rotationProgress || {})[r.id] || { completed: 0, laps: 0 };
  return `<div class="rot-strip" aria-label="Rotation legs">${r.legs.map((icao, i) => `${i ? `<span class="rot-leg ${i <= pr.completed ? "done" : i === m.leg ? "now" : ""}" aria-hidden="true"></span>` : ""}<span class="rot-stop ${i === m.leg - 1 || i === m.leg ? "on" : ""}">${esc(icao)}</span>`).join("")}</div>
    <p class="muted" style="font-size:13px;margin:6px 0 0">${esc(r.name)}: leg ${m.leg} of ${m.legs}. Finish the lap for <b>+${fmt(r.bonus)} points</b>.${pr.laps ? ` You've flown it ${pr.laps}×.` : ""} Flown with the ${r.aircraft.map(a => esc(S.fleet[a]?.icao || a)).join(", ")}.</p>`;
}
function specialBoxes(m) {
  let h = "";
  if (m.challenge) h += `<div class="special-box challenge"><b>Challenging airport · ${esc(m.challenge.icao)} · ${esc(m.challenge.label)}</b><p>${esc(m.challenge.note)}</p></div>`;
  if (m.handling) h += `<div class="special-box handling"><b>${esc(m.handling.label)}</b><ul>${m.handling.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul></div>`;
  return h;
}
function eventsBoardList() {
  const out = [];
  if (S.career?.checkride === "Pending") out.push(S.missions.find(m => m.id === S.checkrideId));
  (S.featured || []).forEach(id => out.push(S.routes.find(r => r.id === id)));
  const done = S.tourDone || {};
  (S.tours || []).forEach(t => { const next = done[t.id]; const leg = (S.tourLegs || []).find(l => l.id === next); if (leg) out.push(leg); });
  return out.filter(Boolean);
}

/* live missions and partner requests: how new they are and how long they stay open */
function freshTags(m) {
  if (!m.expires || m.urgent) return "";
  const now = Date.now() / 1000, left = m.expires - now;
  const isNew = m.created && now - m.created < 86400;
  const open = left <= 0 ? "Closed" : left < 86400 ? `Closes in ${Math.max(1, Math.round(left / 3600))} h` : `Open ${Math.round(left / 86400)} more ${Math.round(left / 86400) === 1 ? "day" : "days"}`;
  return `${isNew ? `<span class="tag green">New</span>` : ""}${m.live || m.contract ? `<span class="tag grey" title="Until ${new Date(m.expires * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}">${open}</span>` : ""}`;
}
/* "PAC cargo center stand P3" at Cincinnati, "PAC cargo stand X15" elsewhere */
function standName(st, caps) {
  if (!st?.stand) return "";
  const t = `${st.icao === "KCVG" ? "PAC cargo center stand" : "PAC cargo stand"} ${st.stand}`;
  return caps ? t.toUpperCase() : t;
}

/* ---------------- conflict zones: restricted (not authorized) and caution (hazard pay) airspace ---------------- */
function zoneFor(m) {
  const z = S.zones;
  if (!z?.enabled || !m?.origin || !m?.destination) return null;
  const hit = icao => z.zones.find(x => (x.prefixes || []).some(p => String(icao || "").toUpperCase().startsWith(p)));
  const ends = [hit(m.origin.icao), hit(m.destination.icao)].filter(Boolean);
  if (!ends.length) return null;
  const r = ends.filter(x => x.level === "restricted");
  return r.length ? { level: "restricted", names: [...new Set(r.map(x => x.name))] }
    : { level: "caution", names: [...new Set(ends.map(x => x.name))], pct: Math.max(...ends.map(x => x.pct || 0)) };
}
function zoneTag(m) {
  const z = zoneFor(m);
  if (!z) return "";
  return z.level === "restricted" ? `<span class="tag zone-r" title="${esc(z.names.join(", "))} is restricted airspace for PAC. The flight won't be credited.">Not authorized · ${esc(z.names.join(", "))}</span>`
    : `<span class="tag amber" title="${esc(z.names.join(", "))}: caution area">Caution · +${z.pct}% hazard pay</span>`;
}
function zoneNotice(z) {
  if (!z) return "";
  const list = (z.zones || []).map(x => x.name).join(", ") || (z.names || []).join(", ");
  if (z.level === "restricted") return `<div class="zone-box restricted"><span class="zone-stamp">Not authorized</span><div><b>Restricted airspace${list ? `: ${esc(list)}` : ""}</b>
    <p>${esc(z.text || "")} ${z.restricted_airport === false ? "A flight whose track crosses restricted airspace goes to staff review, and is only credited if staff accept it." : "You can still fly it, but the PIREP is rejected automatically: no pay, points or hours. See Handbook › Conflict zones."}</p></div></div>`;
  return `<div class="zone-box caution"><span class="zone-stamp">Caution</span><div><b>Caution area${list ? `: ${esc(list)}` : ""}</b><p>Allowed, with <b>${z.pct}% hazard pay</b> on top of your flight pay. Stay alert and keep to your planned route.</p></div></div>`;
}
/* the Briefing step's conflict-zone section: why the area is restricted or a caution area, what happens to the
   flight, and how to plan it. The website also checks the great-circle route for areas it crosses. */
function zoneBriefing(m, a) {
  const z0 = zoneFor(m);
  if (!S.zones?.enabled) return "";
  const info = id => (S.zones.zones || []).find(x => x.id === id) || {};
  const list = a ? (a.zones || []).map(x => ({ ...info(x.id), ...x })) : [];
  if (!a && !z0) return "";
  const lvl = a ? a.level : z0.level;
  const ends = a ? list.filter(x => (a.airports || []).includes(x.id)) : [];
  const over = a ? list.filter(x => (a.crossings || []).includes(x.id)) : [];
  const why = zs => zs.filter(x => x.note).map(x => `<li><b>${esc(x.name)}:</b> ${esc(x.note)}</li>`).join("");
  const pct = a ? a.pct : z0.pct;
  if (lvl === "restricted" && (a ? a.restricted_airport : true)) {
    const r = a ? ends.filter(x => x.level === "restricted") : [];
    return `<section class="zone-brief restricted"><span class="zone-stamp">Not authorized</span><div>
      <span class="kicker">RESTRICTED AIRSPACE</span><h3>${esc((r.length ? r.map(x => x.name) : z0.names).join(", "))} is closed to PAC operations</h3>
      <p>PAC follows the same airspace rules as a real US cargo carrier. This flight stays on the board, and you can still choose to fly it, but like a real airline it isn't authorized:</p>
      <ul><li>The PIREP is <b>rejected automatically</b> when you file it.</li><li><b>No pay, points or hours</b>, and it doesn't count towards rank, tours or awards.</li><li>The aircraft and your location still move, so you'd need to get back out.</li></ul>
      ${r.length && why(r) ? `<h4>Why it's restricted</h4><ul>${why(r)}</ul>` : ""}
      <p class="muted" style="font-size:13px">Looking for credited work? Pick another flight from this station. Handbook › Conflict zones has the full list.</p></div></section>`;
  }
  if (lvl === "restricted") {
    const r = over.filter(x => x.level === "restricted");
    return `<section class="zone-brief restricted"><span class="zone-stamp">Route warning</span><div>
      <span class="kicker">ROUTE CROSSES RESTRICTED AIRSPACE</span><h3>The direct route passes over ${esc(r.map(x => x.name).join(", "))}</h3>
      <p>Both airports are open, but the shortest path between them crosses airspace PAC doesn't fly over. Plan your route around it, just like real crews do.</p>
      <ul><li>In SimBrief, check the route map before you generate. If it crosses ${esc(r.map(x => x.name).join(" or "))}, pick another route or add waypoints to go around.</li>
        <li>If your <b>flown track</b> crosses restricted airspace, the PIREP goes to <b>staff review</b> and is only credited if staff accept it.</li>
        <li>Expect a longer flight and more fuel than the straight line.</li></ul>
      ${why(r) ? `<h4>Why it's restricted</h4><ul>${why(r)}</ul>` : ""}
      ${list.some(x => x.level === "caution") ? `<h4>Also a caution area</h4><ul>${why(list.filter(x => x.level === "caution"))}</ul><p class="muted" style="font-size:13px">Hazard pay applies to caution flights whose route stays clear of restricted airspace.</p>` : ""}</div></section>`;
  }
  const c = a ? list : [];
  return `<section class="zone-brief caution"><span class="zone-stamp">Caution</span><div>
    <span class="kicker">CAUTION AREA · +${pct}% HAZARD PAY</span><h3>This flight ${a && over.length && !ends.length ? "crosses" : "operates in"} ${esc((c.length ? c.map(x => x.name) : z0.names).join(", "))}</h3>
    <p>Flights here are allowed, and PAC pays <b>${pct}% hazard pay</b> on top of your flight pay, like real crews get for higher-risk operations.</p>
    <ul><li>Keep to your planned route and altitude. Don't shortcut over neighboring restricted countries.</li><li>Expect busier security procedures and possible short-notice changes.</li></ul>
    ${why(c) ? `<h4>Why it's a caution area</h4><ul>${why(c)}</ul>` : ""}</div></section>`;
}
async function fillZoneBrief(m) {
  if (!S.zones?.enabled || !m?.origin || !m?.destination) return;
  try {
    const r = await api(`/api/conflict-zones?dep=${encodeURIComponent(m.origin.icao)}&arr=${encodeURIComponent(m.destination.icao)}`);
    const el = $("#zoneBrief"); if (!el || el.dataset.for !== m.id) return;
    el.innerHTML = r.assessment ? zoneBriefing(m, r.assessment) : "";
  } catch (e) { /* the airport check above still shows */ }
}
async function loadZones() { try { S.zones = await api("/api/conflict-zones"); } catch (e) { S.zones = null; } }

function waybillHtml(m) {
  const dist = m.distance_nm || gcnm(m.origin, m.destination);
  return `<button class="waybill${zoneFor(m)?.level === "restricted" ? " wb-restricted" : ""}" role="option" data-id="${esc(m.id)}" data-priority="${m.priority}" data-kind="${m.charter ? "charter" : ""}" aria-selected="${S.selected?.id === m.id}">
      <span class="tab" aria-hidden="true"></span>
      <span class="wb-body">
        <span><span class="wb-title">${esc(m.title)}</span><br><span class="wb-meta">${esc(m.id)} · ${esc(m.region === "Live" ? m.category : (m.region || m.category))} · ${m.priority} priority</span>${bonusTags(m)}${freshTags(m)}${m.tour ? `<span class="tag dark">Tour leg ${m.leg}/${m.legs}</span>` : ""}${m.rotation ? `<span class="tag dark">Rotation leg ${m.leg}/${m.legs}</span>` : ""}${m.challenge ? `<span class="tag amber" title="${esc(m.challenge.note)}">${esc(m.challenge.label)}</span>` : ""}${m.handling ? `<span class="tag dark">${esc(m.handling.label.split(" · ")[0])}</span>` : ""}${m.gravel_kit ? `<span class="tag amber" title="Unpaved gravel runway — Boeing 737-200 with the gravel kit required">❄ Gravel kit · 737-200 only</span>` : ""}${m.ferry && !m.job_kind ? `<span class="tag grey">No cargo · +$${fmt(m.ferry_bonus || 0)} ferry bonus</span>` : ""}${m.category === "Checkride" ? `<span class="tag amber">Checkride</span>` : ""}${S.me?.location?.icao === m.origin.icao ? `<span class="tag green">You're here</span>` : ""}${zoneTag(m)}${m.contract ? `${m.operator.logo ? `<img class="wb-partner" src="${esc(m.operator.logo)}" alt="${esc(m.operator.name)}">` : ""}<span class="tag dark">Crew hire · ${esc(m.operator.callsign)}</span><span class="tag green">+$${fmt(m.contract_bonus)} bonus</span>` : ""}${m.job_kind === "ferry" ? `<span class="tag grey">Ferry · ${esc(m.fixed_airframe)}</span>` : ""}${m.job_kind === "cargo" ? `<span class="tag grey">${esc(m.job_type)}</span>` : ""}${m.urgent ? `<br><span class="urgent-strip"><span class="tag" style="margin:0">URGENT ×1.5</span><span>Offer expires in <span class="countdown" data-countdown="${m.expires}"></span></span><span>· deliver by ${zulu(m.deliver_by)}</span></span>` : ""}</span>
        <span class="wb-reward num">${m.reward}<small>points</small></span>
        <span class="route"><span class="icao">${m.origin.icao}</span><span class="leg"><span class="num">${fmt(dist)} nm</span></span><span class="icao">${m.destination.icao}</span></span>
        <span class="wb-foot"><span>Cargo <b>${esc(m.cargo)}</b></span><span>Load <b class="num">${m.payload_lbs ? fmt(m.payload_lbs) + " lb" : "None"}</b></span><span>Block <b>${hm(m.target_block_min)}</b></span><span>${m.charter ? "Aircraft" : "Recommended"} <b>${m.aircraft.map(a => S.fleet[a]?.icao || a).join(", ")}</b></span></span>
      </span></button>`;
}

/* trip pairings: multi-day trips with duty limits and layover rest */
async function loadTrips() { try { S.trips = await api("/api/trips"); } catch (e) { S.trips = { open: [], mine: null, rules: {} }; } if (S.board === "trips") renderMissions(); }
function tripBoardList() { const t = S.trips?.mine; return t ? [t.legs[t.legs_done]].filter(Boolean) : []; }
async function tripAction(id, action) {
  if (action === "drop" && !confirmDrop()) return;
  try { S.trips = await api(`/api/trips/${encodeURIComponent(id)}/${action}`, { method: "POST" }); } catch (e) { toast(e.message || "That didn't work."); }
  renderMissions();
}
function confirmDrop() { const b = document.getElementById("tripDropBtn"); if (b && b.dataset.armed) return true; if (b) { b.dataset.armed = 1; b.textContent = "Tap again to drop the trip"; } return false; }
function tripCard(t, mine) {
  const ac = S.fleet[t.aircraft]?.name || t.aircraft;
  const legs = t.legs.map((l, i) => `<li class="${mine && i < t.legs_done ? "done" : mine && i === t.legs_done ? "next" : ""}"><b>${esc(l.origin.icao)}→${esc(l.destination.icao)}</b> <small>day ${l.trip.day} · ${hm(l.target_block_min)}${l.trip.layover ? ` · layover ${esc(l.destination.city || l.destination.icao)}` : ""}</small></li>`).join("");
  const rest = mine && t.next_after && t.next_after * 1000 > Date.now() ? `<p class="trip-rest">Layover rest: leg ${t.legs_done + 1} opens <span class="countdown" data-countdown="${t.next_after}"></span>.</p>` : "";
  return `<div class="trip-card${mine ? " mine" : ""}"><div class="trip-head"><b>${esc(t.id)}</b><span class="tag dark">${esc(ac)}</span><span class="tag grey">${t.days} ${t.days === 1 ? "day" : "days"} · ${t.legs.length} legs · ${hm(t.block_min)} block</span></div>
    <div class="trip-stations">${t.stations.map(esc).join(" → ")}</div><ol class="trip-legs">${legs}</ol>${rest}
    <div class="trip-foot"><span class="muted">Per diem about $${fmt(t.per_diem_estimate)}, paid for the real time away from ${esc(t.hub)}</span>
    ${mine ? `<button class="btn ghost" id="tripDropBtn" type="button" onclick="tripAction('${esc(t.id)}','drop')">Drop trip</button>` : S.trips?.mine ? "" : `<button class="btn" type="button" onclick="tripAction('${esc(t.id)}','bid')">Bid for this trip</button>`}</div></div>`;
}
function tripsPanel() {
  const T = S.trips; if (!T) return `<p class="muted">Loading trips…</p>`;
  const r = T.rules || {};
  return `<div class="trips-wrap"><p class="muted">Real cargo pilots fly trips: several legs over a few days, away from base, then home. Bid for one trip at a time and fly its legs in order in the aircraft type shown. Duty days stay within ${r.max_duty_h || 13} hours, and each layover means at least ${r.rest_h || 10} hours' rest (real time) before the next leg opens. Per diem is paid when you're back at base.</p>
    ${T.mine ? `<h4>Your trip</h4>${tripCard(T.mine, true)}` : ""}
    <h4>Open trips</h4>${(T.open || []).length ? `<div class="trip-grid">${T.open.map(t => tripCard(t, false)).join("")}</div>` : `<p class="muted">No open trips right now. New ones are posted through the week.</p>`}</div>`;
}

function renderMissions() {
  if (S.me?.id && !S.laneMap) loadLanes().then(() => { if (!$("#view-missions")?.hidden) renderMissions(); });
  loadFeaturedShipment();
  renderFeaturedShipment();
  loadBoardCampaigns();
  renderBoardCampaigns();
  clearTimeout(S._boardSearchTimer);
  renderBoardTools();
  renderMissionChoiceBar();
  updateBrowseSummary();
  $("#boardPagination").hidden = S.board === "charter";
  $("#sortBar").hidden = S.board === "charter";
  document.querySelectorAll("[data-board]").forEach(b => b.setAttribute("aria-selected", b.dataset.board === S.board));
  $("#netMapWrap").hidden = S.board !== "network";
  const acSel = `<select id="acFilter" aria-label="Filter by aircraft"><option value="">Recommended for any aircraft</option>${Object.entries(S.fleet).map(([k,a]) =>
      `<option value="${k}" ${S.acFilter===k?"selected":""}>Recommended for the ${esc(a.name)}</option>`).join("")}</select>` +
    `<select id="simFilter" aria-label="Filter by simulator"><option value="">Any simulator</option>${["MSFS", "X-Plane"].map(x => `<option ${S.simFilter === x ? "selected" : ""}>${x}</option>`).join("")}</select>` +
    `<select id="divFilter" aria-label="Filter by division"><option value="">Any division</option>${divisions().map(d => `<option value="${esc(d.name)}" ${S.divFilter === d.name ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select>`;
  let list = [];
  if (S.board === "all") {
    $("#boardTitle").textContent = "All flying opportunities";
    $("#filters").innerHTML = acSel;
    list = missionBoardPool();
    $("#boardCount").textContent = "Missions, scheduled routes, jobs, partner work and your next tour or rotation legs.";
  } else if (S.board === "missions") {
    $("#boardTitle").textContent = "Mission board";
    const board = [...S.missions, ...(S.checkrides || [])];  // the living board first; type checkrides after (own filter, and Career)
    const cats = ["All", ...new Set(board.map(m => m.category))];
    $("#filters").innerHTML = cats.map(c => `<button class="chip" aria-pressed="${S.filter === c}" data-cat="${esc(c)}">${esc(c)}</button>`).join("") + acSel;
    document.querySelectorAll("[data-cat]").forEach(b => b.onclick = () => { S.filter = b.dataset.cat; renderMissions(); });
    list = board.filter(m => (S.filter === "All" || m.category === S.filter) && (!S.acFilter || m.aircraft.some(a => a === S.acFilter)));
    const nLive = list.filter(m => m.live).length;
    $("#boardCount").textContent = S.filter === "All"
      ? `${nLive} open ${nLive === 1 ? "mission" : "missions"}. The board changes every day: new work arrives as other missions close.`
      : `${list.length} ${list.length === 1 ? "mission" : "missions"}`;
  } else if (S.board === "network") {
    $("#boardTitle").textContent = "Scheduled network";
    $("#filters").innerHTML = REGIONS.map(r => `<button class="chip" aria-pressed="${S.region === r}" data-region="${esc(r)}">${esc(r)}</button>`).join("") +
      `<span class="net-od"><input type="search" id="netFrom" placeholder="From (ICAO or city)" value="${esc(S.netFrom || "")}" aria-label="Departure">
        <button type="button" class="btn ghost small" id="netSwap" title="Swap departure and destination" aria-label="Swap departure and destination">⇄</button>
        <input type="search" id="netTo" placeholder="To (ICAO or city)" value="${esc(S.netTo || "")}" aria-label="Destination"></span>` +
      `<input type="search" id="netSearch" placeholder="Search ICAO, city or cargo" value="${esc(S.netSearch)}" aria-label="Search routes">` + acSel;
    document.querySelectorAll("[data-region]").forEach(b => b.onclick = () => { S.region = b.dataset.region; S.netLimit = 40; renderMissions(); });
    $("#netSearch").oninput = e => { S.netSearch = e.target.value; S.netLimit = 40; clearTimeout(S._nt); S._nt = setTimeout(() => { renderMissions(); const i = $("#netSearch"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }, 200); };
    const odInput = id => { const i = $(id); i.oninput = e => { S[id === "#netFrom" ? "netFrom" : "netTo"] = e.target.value; S.netLimit = 40; clearTimeout(S._nt); S._nt = setTimeout(() => { renderMissions(); const j = $(id); j.focus(); j.setSelectionRange(j.value.length, j.value.length); }, 200); }; };
    odInput("#netFrom"); odInput("#netTo");
    $("#netSwap").onclick = () => { [S.netFrom, S.netTo] = [S.netTo || "", S.netFrom || ""]; S.netLimit = 40; renderMissions(); };
    const q = S.netSearch.trim().toUpperCase(), qf = (S.netFrom || "").trim().toUpperCase(), qt = (S.netTo || "").trim().toUpperCase();
    const at = (ap, x) => !x || [ap.icao, ap.city, ap.name].some(v => (v || "").toUpperCase().includes(x));
    list = S.routes.filter(r => at(r.origin, qf) && at(r.destination, qt) && (S.region === "All" || r.region === S.region) && (!S.acFilter || r.aircraft.includes(S.acFilter)) &&
      (!S.simFilter || r.aircraft.some(a => fliesIn(a, S.simFilter))) &&
      (!q || [r.origin.icao, r.destination.icao, r.origin.city, r.destination.city, r.cargo, r.id].some(x => (x || "").toUpperCase().includes(q))));
    const stations = new Set(S.routes.flatMap(r => [r.origin.icao, r.destination.icao]));
    $("#boardCount").textContent = `${list.length} of ${S.routes.length} routes · ${stations.size} stations worldwide`;
    // Draw after all shared filters have been applied.
  } else if (S.board === "trips") {
    $("#boardTitle").textContent = "Trip pairings";
    if (!S.trips || Date.now() - (S._tripsAt || 0) > 60000) { S._tripsAt = Date.now(); loadTrips(); }
    $("#filters").innerHTML = tripsPanel();
    list = tripBoardList();
    $("#boardCount").textContent = S.trips?.mine ? `Trip ${S.trips.mine.id}: leg ${S.trips.mine.legs_done + 1} of ${S.trips.mine.legs.length} is next.` : "Bid for a trip to see its legs here.";
  } else if (S.board === "jobs") {
    $("#boardTitle").textContent = "Job board";
    const kinds = [["all", "All work"], ["cargo", "Cargo jobs"], ["ferry", "Ferry flights"]];
    $("#filters").innerHTML = kinds.map(([k, l]) => `<button class="chip" aria-pressed="${(S.jobKind || "all") === k}" data-jk="${k}">${l} <small>${k === "all" ? (S.jobs || []).length : (S.jobs || []).filter(j => j.job_kind === k).length}</small></button>`).join("") +
      `<span class="muted" style="font-size:13px;flex-basis:100%">A new set of cargo and ferry jobs every day at 0000Z; partner crew requests arrive through the day. Contract flying: partner airlines short of crew pay ${1.5}× your hourly rate plus a shortage bonus, flying their aircraft under their callsign.</span>`;
    $("#filters").querySelectorAll("[data-jk]").forEach(b => b.onclick = () => { S.jobKind = b.dataset.jk; renderMissions(); });
    list = (S.jobs || []).filter(j => (S.jobKind || "all") === "all" || j.job_kind === S.jobKind);
    $("#boardCount").textContent = `${list.length} jobs available today`;
  } else if (S.board === "partners") {
    $("#boardTitle").textContent = "Partner crew requests";
    const P = S.partners || {};
    $("#filters").innerHTML = `<div class="partner-grid" style="width:100%">${Object.values(P).map(p => `<button type="button" class="partner-card ${S.partnerFilter === p.key ? "on" : ""}" data-partner="${p.key}">
        <img src="${esc(p.logo)}" alt="${esc(p.name)}"><p>${esc(p.relationship)}</p>
        <div><small class="muted">Hub</small> <b>${esc(p.hub)}</b> <small class="muted">${esc(p.hub_name)}</small></div>
        <div class="net" title="Jumpseat network">${p.network.map(n => `<span>${n}</span>`).join("")}</div></button>`).join("")}</div>`;
    document.querySelectorAll("[data-partner]").forEach(b => b.onclick = () => { S.partnerFilter = S.partnerFilter === b.dataset.partner ? null : b.dataset.partner; renderMissions(); });
    list = (S.jobs || []).filter(m => m.contract && (!S.partnerFilter || m.operator?.key === S.partnerFilter));
    $("#boardCount").textContent = `${list.length} open crew ${list.length === 1 ? "request" : "requests"}${S.partnerFilter ? " from " + (P[S.partnerFilter]?.name || "") : ""}. Partners short of qualified captains hire PAC pilots to fly their aircraft under their callsign. New requests arrive through the day and each stays open for a day or so. Click a partner to filter.`;
  } else if (S.board === "urgent") {
    $("#boardTitle").textContent = "Urgent requests";
    $("#filters").innerHTML = `<span class="muted" style="font-size:14px">New requests arrive about every 40 minutes, up to six at a time. Each uses an aircraft that's already in position.</span>`;
    list = S.urgent || [];
    $("#boardCount").textContent = list.length ? `${list.length} open ${list.length === 1 ? "request" : "requests"}. Deliver before the deadline for ×1.5 points and full revenue.` : "No urgent requests right now. Check back soon.";
  } else if (S.board === "rotations") {
    $("#boardTitle").textContent = "Rotations";
    $("#filters").innerHTML = `<span class="muted" style="font-size:14px">A rotation is a freighter's working pattern: several legs flown in order, ending where it started. Each shows your next leg. Finish a lap for the rotation bonus, then fly it again whenever you like.</span>` + acSel;
    list = rotationBoardList().filter(m => !S.acFilter || m.aircraft.includes(S.acFilter));
    const laps = Object.values(S.rotationProgress || {}).reduce((a, p) => a + (p.laps || 0), 0);
    $("#boardCount").textContent = `${(S.rotations || []).length} rotations${laps ? ` · you've flown ${laps} full ${laps === 1 ? "lap" : "laps"}` : ""}`;
  } else if (S.board === "events") {
    $("#boardTitle").textContent = "Events & tours";
    $("#filters").innerHTML = (S.activeEvents || []).map(e => `<span class="tag" style="font-size:13px;padding:5px 10px">${esc(e.name)} ×${e.multiplier} until ${fmtDate(e.end)}</span>`).join("") || `<span class="muted" style="font-size:14px">No event running right now.</span>`;
    list = eventsBoardList();
    $("#boardCount").textContent = `${(S.featured || []).length} featured routes this month (×1.25) and the next leg of each tour.`;
  } else {
    $("#boardTitle").textContent = "Charter a flight";
    $("#filters").innerHTML = "";
    $("#boardCount").textContent = "Any airport, any aircraft in the fleet, any load it can carry.";
    renderCharterForm();
    renderHeld(); renderDossier();
    return;
  }
  if (!$("#acFilter")) $("#filters").insertAdjacentHTML("beforeend", acSel);
  list = boardSearchList(list);
  if (S.fromHere && S.me?.location && S.board !== "charter") list = list.filter(m => m.origin.icao === S.me.location.icao);
  if (S.simFilter && S.board !== "charter") list = list.filter(m => m.aircraft.some(a => fliesIn(a, S.simFilter)));
  if (S.divFilter && S.board !== "charter") list = list.filter(m => (m.aircraft || []).some(a => divOf(a) === S.divFilter));
  if (S.boardReadyOnly && S.board !== "charter") list = list.filter(boardReadyAtStation);
  if (S.board !== "charter") {
    const blk = m => m.target_block_min || 0;
    const len = S.lenFilter || "any";
    list = list.filter(m => len === "any" || (len === "short" ? blk(m) < 120 : len === "medium" ? blk(m) >= 120 && blk(m) <= 300 : blk(m) > 300));
    const by = S.sortBy || "default";
    const pay = m => m.contract ? (m.target_block_min / 60) * (S.me?.pay_rate || 100) * 1.5 + (m.contract_bonus || 0) : (m.target_block_min / 60) * (S.me?.pay_rate || 100) + (m.ferry_bonus || 0);
    if (by !== "default") list = [...list].sort((a, b) => by === "short" ? blk(a) - blk(b) : by === "long" ? blk(b) - blk(a) : by === "points" ? (b.reward || 0) - (a.reward || 0) : pay(b) - pay(a));
    const bar = $("#sortBar");
    if (bar) bar.innerHTML = `<label class="muted" style="font-size:13px">Sort <select id="sortSel">${[["default", "Suggested"], ["short", "Shortest first"], ["long", "Longest first"], ["points", "Most points"], ["pay", "Best pay for me"]].map(([k, l]) => `<option value="${k}" ${by === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      ${[["any", "Any length"], ["short", "Under 2 h"], ["medium", "2–5 h"], ["long", "Over 5 h"]].map(([k, l]) => `<button class="chip" aria-pressed="${len === k}" data-len="${k}">${l}</button>`).join("")}`;
    if (bar) { bar.hidden = false; $("#sortSel").onchange = e => { S.sortBy = e.target.value; renderMissions(); }; bar.querySelectorAll("[data-len]").forEach(b => b.onclick = () => { S.lenFilter = b.dataset.len; renderMissions(); }); }
  } else if ($("#sortBar")) $("#sortBar").hidden = true;
  if (!S.sortBy || S.sortBy === 'default') {
    const score = m => (m.origin.icao === S.me?.location?.icao ? 4 : 0) + (boardMatchTypes(m).some(a=>boardQualified(m,a)&&boardAvailable(m,a)) ? 2 : 0);
    list = [...list].sort((a,b)=>score(b)-score(a));
  }
  if (S.board === 'network' && !S.selected) drawNetwork(list);
  const shown = boardPage(list);
  $("#sortBar").insertAdjacentHTML("beforeend",shipmentFilterNote());
  const count = $('#boardCount');
  count.textContent = `${shown.length} shown${list.length > shown.length ? ` of ${list.length} matching flights` : ''} · ${count.textContent}`;
  if (S.fromHere || S.simFilter || S.divFilter || S.acFilter || (S.lenFilter && S.lenFilter !== 'any') || S.netSearch || S.region && S.region !== 'All' || S.filter !== 'All') {
    $('#sortBar').insertAdjacentHTML('beforeend', `<span class="journey-filter-note">${S.simFilter ? esc(S.simFilter) + ' filter active · ' : ''}${S.divFilter ? esc(S.divFilter) + ' only · ' : ''}<button type="button" class="btn ghost small" onclick="resetMissionFilters()">Reset filters</button></span>`);
  }
  $("#manifest").innerHTML = shown.map(boardCard).join("") || `<div class="empty">No flights match these filters. <button type="button" class="btn ghost small" onclick="resetMissionFilters()">Reset filters</button></div>`;
  if ($("#acFilter")) $("#acFilter").onchange = e => { S.acFilter = e.target.value; renderMissions(); };
  if ($("#simFilter")) $("#simFilter").onchange = e => { S.simFilter = e.target.value; renderMissions(); };
  if ($("#divFilter")) $("#divFilter").onchange = e => { S.divFilter = e.target.value; S.boardPage = 1; renderMissions(); };
  const more = $("#moreRoutes"); if (more) more.onclick = () => { S.netLimit += 40; renderMissions(); };
  tickCountdowns();
  document.querySelectorAll(".waybill").forEach(b => b.onclick = () => selectMission(b.dataset.id));
  renderHeld();
  renderDossier();
}

/* network map */
function drawNetwork(list) {
  if (!HAS_MAP) return;
  if (!S.netMap) {
    const base = makeBaseMap($("#netMap"), { theme: "light", style: S.settings.map_style === "dark" ? "light" : (S.settings.map_style || "light") });
    S.netMap = base.map; S.netMap.setView([30, 10], 2);
    S.netLayers = { routes: L.layerGroup().addTo(S.netMap), stations: L.layerGroup().addTo(S.netMap), sel: L.layerGroup().addTo(S.netMap) };
    const lg = L.control({ position: "bottomleft" });
    lg.onAdd = () => { const d = L.DomUtil.create("div", "net-legend"); d.textContent = "Click a station to list its routes"; return d; };
    lg.addTo(S.netMap);
  }
  setTimeout(() => S.netMap.invalidateSize(), 30);
  if (S.netWx === undefined) loadNetworkWx(() => { S._netKey = null; if (S.board === "network") drawNetwork(list); });
  wxLegend(S.netMap);
  const key = list.map(r => r.id).join(",") + (S.netWx ? ":wx" : "");
  if (S._netKey !== key) {
    S._netKey = key;
    S.netLayers.routes.clearLayers(); S.netLayers.stations.clearLayers();
    const count = {};
    list.forEach(r => {
      L.polyline(gcPath(r.origin, r.destination), { color: "#C80000", weight: 1, opacity: .35, interactive: false }).addTo(S.netLayers.routes);
      [r.origin, r.destination].forEach(a => count[a.icao] = { a, n: (count[a.icao]?.n || 0) + 1 });
    });
    Object.values(count).forEach(({ a, n }) => {
      const main = a.icao === "KCVG", hub = main || Object.keys(S.hubs || {}).includes(a.icao);
      L.circleMarker([a.lat, a.lon], { radius: main ? 10 : hub ? 7 : Math.min(6, 2.5 + n / 2), color: wxColor(a.icao) || "#fff", weight: wxColor(a.icao) ? 3 : main ? 3 : 1.5, fillColor: hub ? "#C80000" : "#1E2126", fillOpacity: 1 })
        .bindTooltip(`${a.icao} · ${esc(a.city)}${main ? " · main hub" : hub ? " · gateway" : ""} (${n})`, { className: "stn-tip", direction: "top" })
        .on("click", () => { S.netSearch = a.icao; S.netLimit = 40; renderMissions(); })
        .addTo(S.netLayers.stations);
    });
    if (list.length && list.length < S.routes.length) {
      const b = L.latLngBounds(list.flatMap(r => [[r.origin.lat, r.origin.lon], [r.destination.lat, r.destination.lon]]));
      S.netMap.fitBounds(b, { padding: [30, 30], maxZoom: 6 });
    } else S.netMap.setView([30, 10], 2);
  }
  highlightNetRoute();
}
const WX_COLORS = { VFR: "#1f9d55", MVFR: "#2b6fd6", IFR: "#d62b2b", LIFR: "#b02bd6" };
function wxColor(icao) { return S.netWx && WX_COLORS[S.netWx[icao]]; }
async function loadNetworkWx(after) {
  if (S.netWx !== undefined) { after && after(); return; }
  S.netWx = null;
  try { const r = await api("/api/weather/network"); S.netWx = r; } catch (e) { S.netWx = null; }
  after && after();
}
function wxLegend(map) {
  if (!S.netWx || map._wxLegend) return;
  const c = L.control({ position: "bottomright" });
  c.onAdd = () => { const d = L.DomUtil.create("div", "wx-legend"); d.innerHTML = `<b style="color:var(--ink)">Live weather</b>${Object.entries(WX_COLORS).map(([k, v]) => `<span><i style="background:${v}"></i>${k}</span>`).join("")}`; return d; };
  c.addTo(map); map._wxLegend = c;
}
function highlightNetRoute() {
  if (!S.netLayers) return;
  S.netLayers.sel.clearLayers();
  const m = S.selected;
  if (m && S.board === "network") L.polyline(gcPath(m.origin, m.destination), { color: "#C80000", weight: 3.5 }).addTo(S.netLayers.sel);
}
function gcPath(a, b, n = 32) { // great-circle arc, unwrapped across the antimeridian
  const r = x => x * Math.PI / 180, d = x => x * 180 / Math.PI;
  const p1 = r(a.lat), l1 = r(a.lon), p2 = r(b.lat), l2 = r(b.lon);
  const D = 2 * Math.asin(Math.sqrt(Math.sin((p2 - p1) / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin((l2 - l1) / 2) ** 2));
  if (!D) return [[a.lat, a.lon], [b.lat, b.lon]];
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const f = i / n, A = Math.sin((1 - f) * D) / Math.sin(D), B = Math.sin(f * D) / Math.sin(D);
    const x = A * Math.cos(p1) * Math.cos(l1) + B * Math.cos(p2) * Math.cos(l2);
    const y = A * Math.cos(p1) * Math.sin(l1) + B * Math.cos(p2) * Math.sin(l2);
    const z = A * Math.sin(p1) + B * Math.sin(p2);
    pts.push([d(Math.atan2(z, Math.hypot(x, y))), d(Math.atan2(y, x))]);
  }
  return unwrap(pts);
}

/* charter */
function renderCharterForm() {
  const c = S.charterSpec || (S.charterSpec = { origin: "", destination: "", aircraft: "B738F", payload_lbs: "", cargo: "General cargo", priority: "Standard", flight_number: "", _o: null, _d: null });
  const f = S.fleet[c.aircraft];
  const knownCargo = S.cargoTypes.includes(c.cargo);
  $("#manifest").innerHTML = `${charterCustomerPanel(c)}<form class="charter-form" id="charterForm" autocomplete="off">
    <div class="grid2">
      ${apField("Departure", "o", c._o)}
      ${apField("Arrival", "d", c._d)}
    </div>
    <div class="grid2">
      <div class="field"><label for="ch_ac">Aircraft</label><select id="ch_ac">${fleetCodes().map(k => [k, S.fleet[k]]).map(([k, a]) => `<option value="${k}" ${k === c.aircraft ? "selected" : ""}>${esc(a.name)}${a.sim && a.sim !== "MSFS" ? " (" + esc(a.sim) + ")" : ""}</option>`).join("")}</select></div>
      <div class="field"><label for="ch_pl">Cargo weight (lb)</label><input id="ch_pl" type="number" min="0" step="any" value="${esc(c.payload_lbs)}" placeholder="Up to ${fmt(f.max_payload_lbs)}"></div>
    </div>
    <div class="grid2">
      ${c.customer_id ? `<div class="field"><label>Cargo</label><input value="${esc(c.cargo)}" readonly aria-readonly="true"><small class="muted">Set by the customer's shipment. Choose Independent charter to carry something else.</small></div>` : ""}<div class="field" ${c.customer_id ? "hidden" : ""}><label for="ch_cargo">Cargo</label><select id="ch_cargo">${S.cargoTypes.map(t => `<option ${t === c.cargo ? "selected" : ""}>${esc(t)}</option>`).join("")}<option value="__other" ${knownCargo ? "" : "selected"}>Something else…</option></select>
        <input id="ch_cargo_other" placeholder="Describe the cargo" value="${knownCargo ? "" : esc(c.cargo)}" style="margin-top:6px" ${knownCargo ? "hidden" : ""}></div>
      <div class="field"><label for="ch_pr">Priority</label><select id="ch_pr">${["Standard", "High", "Critical"].map(p => `<option ${p === c.priority ? "selected" : ""}>${p}</option>`).join("")}</select></div>
    </div>
    <div class="field"><label for="ch_fn">Flight number (optional)</label><input id="ch_fn" value="${esc(c.flight_number)}" placeholder="Leave blank for an automatic PAC8xxx number" maxlength="7"></div>
    <div class="row"><button class="btn" type="submit">Build charter</button><span class="muted" style="font-size:13px">You'll plan it in SimBrief next, like any mission.</span></div>
  </form>`;
  bindApField("o"); bindApField("d");
  bindCharterCustomers(c);
  $("#ch_ac").onchange = e => { c.aircraft = e.target.value; renderCharterForm(); };
  $("#ch_pl").oninput = e => c.payload_lbs = e.target.value;
  $("#ch_cargo").onchange = e => { if (e.target.value === "__other") { c.cargo = ""; $("#ch_cargo_other").hidden = false; $("#ch_cargo_other").focus(); } else { c.cargo = e.target.value; $("#ch_cargo_other").hidden = true; } };
  $("#ch_cargo_other").oninput = e => c.cargo = e.target.value;
  $("#ch_pr").onchange = e => c.priority = e.target.value;
  $("#ch_fn").oninput = e => c.flight_number = e.target.value;
  $("#charterForm").onsubmit = async e => {
    e.preventDefault();
    try {
      const r = await api("/api/charter/quote", { method: "POST", body: { origin: c.origin, destination: c.destination, aircraft: c.aircraft,
        payload_lbs: Number(c.payload_lbs), cargo: c.cargo, priority: c.priority, flight_number: c.flight_number, customer_id: c.customer_id || "", shipment_id: c.shipment_id || "" } });
      c.flight_number = r.mission.charter.flight_number;
      S.charterMission = r.mission; S.charterWarnings = r.warnings;
      S.selected = null; selectMission(r.mission.id);
      $("#ch_fn").value = c.flight_number;
    } catch (err) { toast(err.message); }
  };
}
function apField(label, k, a) {
  const c = S.charterSpec;
  return `<div class="field ap-field"><label for="ch_${k}">${label}</label>
    <input id="ch_${k}" value="${esc(k === "o" ? c.origin : c.destination)}" placeholder="ICAO, IATA, city or airport" role="combobox" aria-expanded="false" aria-controls="ch_${k}_list">
    <ul class="ap-list" id="ch_${k}_list" role="listbox" hidden></ul>
    <div class="ap-picked" id="ch_${k}_picked">${a ? `${esc(a.name)} · ${esc(a.city)}, ${a.country} · longest runway ${fmt(a.rwy_ft)} ft` : ""}</div></div>`;
}
function bindApField(k) {
  const c = S.charterSpec, inp = $(`#ch_${k}`), list = $(`#ch_${k}_list`);
  let results = [];
  const pick = a => {
    if (k === "o") { c.origin = a.icao; c._o = a; } else { c.destination = a.icao; c._d = a; }
    inp.value = a.icao; list.hidden = true; inp.setAttribute("aria-expanded", "false");
    $(`#ch_${k}_picked`).textContent = `${a.name} · ${a.city}, ${a.country} · longest runway ${fmt(a.rwy_ft)} ft`;
  };
  inp.oninput = () => {
    const q = inp.value.trim();
    if (k === "o") { c.origin = q.toUpperCase(); c._o = null; } else { c.destination = q.toUpperCase(); c._d = null; }
    $(`#ch_${k}_picked`).textContent = "";
    clearTimeout(inp._t);
    if (q.length < 2) { list.hidden = true; return; }
    inp._t = setTimeout(async () => {
      results = await api("/api/airports/search?q=" + encodeURIComponent(q)).catch(() => []);
      list.innerHTML = results.map((a, i) => `<li><button type="button" data-i="${i}"><b>${a.icao}</b><span>${esc(a.name)}<br><small>${esc(a.city)}, ${a.country}${a.iata ? " · " + a.iata : ""}</small></span><small>${fmt(a.rwy_ft)} ft</small></button></li>`).join("")
        || `<li style="padding:8px 10px;color:var(--steel);font-size:14px">No airport matches "${esc(q)}".</li>`;
      list.hidden = false; inp.setAttribute("aria-expanded", "true");
      list.querySelectorAll("button").forEach(b => b.onmousedown = e => { e.preventDefault(); pick(results[b.dataset.i]); });
    }, 180);
  };
  inp.onkeydown = e => {
    if (e.key === "Enter" && !list.hidden && results[0]) { e.preventDefault(); pick(results[0]); }
    if (e.key === "ArrowDown" && !list.hidden) { e.preventDefault(); list.querySelector("button")?.focus(); }
    if (e.key === "Escape") list.hidden = true;
  };
  list.onkeydown = e => {
    const items = [...list.querySelectorAll("button")], i = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); items[Math.min(i + 1, items.length - 1)]?.focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); i <= 0 ? inp.focus() : items[i - 1].focus(); }
    if (e.key === "Enter") { e.preventDefault(); pick(results[+document.activeElement.dataset.i]); }
    if (e.key === "Escape") { list.hidden = true; inp.focus(); }
  };
  inp.onblur = () => setTimeout(() => { if (!list.contains(document.activeElement)) list.hidden = true; }, 150);
}
function renderHeld() {
  const b = S.booking;
  $("#heldBanner").innerHTML = b ? `<div class="held"><span>You hold <b>${esc(b.flight_number)}</b> · ${esc(b.mission.title)} · ${b.mission.origin.icao} to ${b.mission.destination.icao} on the ${esc(S.fleet[b.aircraft].name)}</span>
    <button class="btn" onclick="show('acars')">Open ACARS</button></div>` : "";
}
function selectMission(id) {
  if ((id === (S.checkrideId||'PAC001') || String(id).startsWith('TR-')) && S.booking?.mission?.id !== id) { openTraining(id); return; }
  const m = S.booking?.mission?.id === id ? S.booking.mission : allFlights().find(x => x.id === id);
  if (!m) return;
  if (!S.selected && !$("#view-missions").hidden) S.missionBrowseScrollY = window.scrollY;
  if (S.selected?.id !== id) { S.ofp = null; S.ofpErrors = []; S.ofpWarnings = []; S.planned = false; S.aircraft = m.aircraft[0]; S.airframe = S.pendingAirframe || (m.urgent && m.suggested_airframe) || defaultAirframe(m, S.aircraft); S.pendingAirframe = null; S.briefReviewed = false; S.plannerDraftRestored = false; S.cargoChange = null; S.cargoPending = null; }
  if (S.selected?.id !== id && (S.acFilter || S.simFilter || S.boardQualifiedOnly || S.boardAvailableOnly)) {
    const matched = boardMatchTypes(m)[0];
    if (matched) { S.aircraft = matched; S.airframe = defaultAirframe(m,matched); }
  }
  if (S.selected?.id !== id) applyPlanningDraft(m, readPlanningDraft());
  S.selected = m;
  document.querySelectorAll(".waybill").forEach(b => b.setAttribute("aria-selected", b.dataset.id === id));
  renderDossier();
  highlightNetRoute();
  $("#dossier").scrollIntoView({ behavior: "smooth" });
  $("#dossier").focus({preventScroll:true});
}
function backToFlights() {
  S.selected = null;
  S.plannerDraftRestored = false;
  renderDossier();
  if (S.board === "network") {
    S._netKey = null;
    renderMissions();
  }
  requestAnimationFrame(() => {
    window.scrollTo({ top: S.missionBrowseScrollY || 0 });
    $("#manifest").focus({ preventScroll: true });
  });
}
function discordWidget(site) {   // the live Discord server widget on the home page (Staff › Site and rules › Letters and links)
  const id = String(site?.discord_widget || "").match(/\d{17,20}/)?.[0];
  if (!id) return "";
  const inv = String(site.discord_invite || "").trim();
  return `<div class="section-h"><div><div class="kicker">Community</div><h2>Join the crew room</h2><p>The PAC Discord is where pilots swap screenshots, talk routes and get help. See who's around right now.</p></div>${inv ? `<a class="btn ghost small" href="${esc(inv)}" target="_blank" rel="noopener">Join our Discord</a>` : ""}</div>
  <div style="display:flex;flex-wrap:wrap;gap:24px;align-items:flex-start">
    <iframe loading="lazy" src="https://discord.com/widget?id=${id}&theme=dark" title="PAC Discord" width="350" height="420" style="max-width:100%;border:0;border-radius:8px;flex:0 0 auto;background:#2b2d31" allowtransparency="true" loading="lazy" sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts"></iframe>
    <ul style="flex:1 1 260px;margin:0;padding-left:18px;line-height:1.7">
      <li>Get your rank role and your own <b>/pilot</b> card.</li>
      <li>News, NOTAMs and new liveries as soon as they're out.</li>
      <li>Help with PAC ACARS, SimBrief and your sim setup.</li>
      <li>Find someone to fly a group flight or an event with.</li></ul></div>`;
}
function filingIcao() { const c = String(S.settings?.filing_icao || "").toUpperCase(); return /^[A-Z]{3}$/.test(c) ? c : "PGI"; }
function atcCallsign(m) { return (m.operator?.code || filingIcao()) + m.id.replace(/\D/g, ""); }
function simbriefRemarks(m) {
  return m.operator ? `PAC PILOT HIRED TO FILL IN FOR ${m.operator.name.toUpperCase()} CREW SHORTAGE. ${m.id} FLOWN BY ${(displayName(S.profile || {}) || "PAC CAPTAIN").toUpperCase()} ${S.profile?.pilot_id || ""}`.trim()
    : `CALLSIGN PAGANI. PAGANI AIR CARGO MISSION ${m.id} ${m.title.toUpperCase()}`;
}
function vatsimFilingDetails(m, aircraft, ofp) {
  ofp = ofp || {};
  const ac = S.fleet[aircraft] || {};
  const rows = [
    ["Network callsign", atcCallsign(m)],
    ["Aircraft type", ofp.aircraft_icao || ac.icao || ac.simbrief_type || aircraft],
    ["Departure", ofp.origin?.icao || m.origin.icao],
    ["Destination", ofp.destination?.icao || m.destination.icao],
    ["Alternate", ofp.alternate?.icao],
    ["Cruise altitude", ofp.cruise_ft ? `FL${Math.round(ofp.cruise_ft / 100)}` : ""],
    ["Route", ofp.route],
    ["PAC remarks", simbriefRemarks(m)],
  ].filter(([, value]) => value);
  return `${atcCallsign(m)} · VATSIM flight plan\n${rows.map(([label, value]) => `${label}: ${value}`).join("\n")}`;
}
function simbriefUtcParts(value) {
  const s = String(value || "").trim();
  if (/^\d{10,13}$/.test(s)) {
    const timestamp = Number(s) * (s.length === 13 ? 1 : 1000);
    if (Number.isFinite(timestamp)) {
      const date = new Date(timestamp);
      if (!Number.isNaN(date.getTime())) return { date: date.toISOString().slice(0, 10), time: date.toISOString().slice(11, 16) };
    }
  }
  let match = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (match) return { date: `${match[1]}-${match[2]}-${match[3]}`, time: `${match[4]}:${match[5]}` };
  match = s.match(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})/);
  if (match) return { date: `${match[1]}-${match[2]}-${match[3]}`, time: `${match[4]}:${match[5]}` };
  match = s.match(/^(\d{2}):(\d{2})$/);
  if (match) return { date: "", time: `${match[1]}:${match[2]}` };
  if (/^\d{4}$/.test(s)) return { date: "", time: `${s.slice(0, 2)}:${s.slice(2)}` };
  return { date: "", time: "" };
}
function validUtcDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}
function vatsimIcaoFpl(m, aircraft, ofp, values) {
  const ac = S.fleet[aircraft] || {}, origin = ofp.origin?.icao || m.origin.icao;
  const destination = ofp.destination?.icao || m.destination.icao;
  const type = String(ofp.aircraft_icao || ac.icao || ac.simbrief_type || "").toUpperCase();
  const equipmentValue = values.equipment !== undefined ? values.equipment : ofp.equipment;
  const equipment = String(equipmentValue || "").toUpperCase().replace(/\s/g, "");
  const equipmentParts = equipment.match(/^([LMHJ])-?([A-Z0-9]{1,24})\/([A-Z0-9]{1,8})$/);
  const time = String(values.departureTime || "").replace(/\D/g, "");
  const date = String(values.flightDate || "");
  const speed = String(values.speed || ofp.cruise_tas_kt || "").replace(/\D/g, "");
  const route = String(ofp.route || "").trim().replace(/\s+/g, " ").toUpperCase();
  const levelFt = Number(ofp.cruise_ft) || 0;
  const eetMin = Math.round(Number(ofp.est_enroute_min) || 0);
  const missing = [];
  if (!/^[A-Z0-9]{2,8}$/.test(atcCallsign(m).toUpperCase())) missing.push("valid PAC callsign");
  if (!/^[A-Z0-9]{2,4}$/.test(type)) missing.push("aircraft type");
  if (!equipmentParts && !/^[A-Z0-9]{1,24}\/[A-Z0-9]{1,8}$/.test(equipment)) missing.push("actual aircraft equipment and surveillance codes");
  if (!/^\d{4}$/.test(time) || Number(time.slice(0, 2)) > 23 || Number(time.slice(2)) > 59) missing.push("departure time in UTC");
  if (!validUtcDate(date)) missing.push("flight date in UTC");
  if (!/^\d{3,4}$/.test(speed) || Number(speed) < 1) missing.push("planned cruise speed in knots");
  if (!/^[A-Z]{4}$/i.test(origin || "") || !/^[A-Z]{4}$/i.test(destination || "")) missing.push("departure and destination ICAO codes");
  if (!route) missing.push("SimBrief route");
  if (!(levelFt > 0)) missing.push("SimBrief cruise altitude");
  if (!(eetMin > 0 && eetMin < 6000)) missing.push("SimBrief estimated enroute time");
  if (missing.length) return { text: "", missing };

  const mtowKg = Number(ac.mtow_lbs) * 0.45359237;
  const wake = equipmentParts?.[1] || (mtowKg > 136000 ? "H" : mtowKg > 0 && mtowKg <= 7000 ? "L" : "M");
  const equipmentCodes = equipmentParts ? `${equipmentParts[2]}/${equipmentParts[3]}` : equipment;
  const level = `${levelFt >= 18000 ? "F" : "A"}${String(Math.round(levelFt / 100)).padStart(3, "0")}`;
  const eet = `${String(Math.floor(eetMin / 60)).padStart(2, "0")}${String(eetMin % 60).padStart(2, "0")}`;
  const alternate = ofp.alternate?.icao ? ` ${ofp.alternate.icao.toUpperCase()}` : "";
  const dateOfFlight = date.slice(2, 4) + date.slice(5, 7) + date.slice(8, 10);
  const remarks = simbriefRemarks(m).toUpperCase().replace(/[^A-Z0-9 ]/g, " ").replace(/\s+/g, " ").trim().slice(0, 100);
  const rules = (values.rules || ofp.flight_rules) === "V" ? "V" : "I";
  const flightType = (values.flightType || ofp.flight_type) === "S" ? "S" : "N";
  const callsign = atcCallsign(m).toUpperCase();
  return {
    text: `(FPL-${callsign}-${rules}${flightType}\n-${type}/${wake}-${equipmentCodes}\n-${origin.toUpperCase()}${time}\n-N${speed.padStart(4, "0")}${level} ${route}\n-${destination.toUpperCase()}${eet}${alternate}\n-DOF/${dateOfFlight} RMK/${remarks})`,
    missing: [],
  };
}
async function sendToSayIntentions(btn) {
  btn.disabled = true; const was = btn.textContent; btn.textContent = "Sending…";
  try { await api("/api/sayintentions/push", { method: "POST" }); toast("Sent to SayIntentions. Start your SayIntentions flight and your crew will know the plan."); }
  catch (e) { toast(/API key/i.test(e.message) ? "Link your SayIntentions account first: Resources › Downloads › SayIntentions.AI (or just fly once with PAC ACARS running)." : e.message, 9000); }
  finally { btn.disabled = false; btn.textContent = was; }
}
function vatsimFilingPanel(m, aircraft, ofp) {
  const scheduled = simbriefUtcParts(ofp.departure_time_utc);
  const flightDate = scheduled.date || new Date().toISOString().slice(0, 10);
  const equipment = ofp.equipment || [ofp.equipment_category, ofp.equipment_navigation].filter(Boolean).join("-")
    + (ofp.equipment_transponder ? `/${ofp.equipment_transponder}` : "");
  return `<div class="notice vatsim-filing" style="margin:12px 0"><b>File on VATSIM or IVAO</b>
    <p class="muted" style="margin:4px 0 10px;font-size:13px">PAC cannot file directly through VATSIM's documented API. File in your approved pilot client; copy these details to keep the PAC callsign and remarks when SimBrief's network filing omits them.</p>
    ${(ofp.prefile?.vatsim || ofp.prefile?.ivao) ? `<p style="margin:0 0 6px;font-size:13px"><b>One click:</b> open a flight plan already filled in from your SimBrief OFP (route, times and remarks). Check it, then send it.</p><div class="row" style="margin:0 0 10px">${ofp.prefile.vatsim ? `<a class="btn small" href="${esc(ofp.prefile.vatsim)}" target="_blank" rel="noopener">Prefile on VATSIM</a>` : ""}${ofp.prefile.ivao ? `<a class="btn small" href="${esc(ofp.prefile.ivao)}" target="_blank" rel="noopener">Prefile on IVAO</a>` : ""}</div>` : ""}
    <p style="margin:0 0 10px;font-size:13px"><a href="https://my.vatsim.net/pilots/flightplan" target="_blank" rel="noopener">Open VATSIM flight planning</a> · <a href="https://fpl.ivao.aero" target="_blank" rel="noopener">Open IVAO flight planning</a></p>
    <p class="muted" style="margin:0 0 10px;font-size:13px">Flying offline with AI ATC? <b>BeyondATC</b> and <b>SayIntentions</b> load your latest SimBrief plan by themselves. After you book, the <b>Send to SayIntentions</b> button on the ACARS page also briefs your SayIntentions crew on the PAC flight.</p>
    <button class="btn ghost small" type="button" data-vatsim-copy>Copy filing details</button>
    <details style="margin-top:8px"><summary>Build ICAO FPL for VATSIM import</summary>
      <p class="muted" style="font-size:13px;margin:6px 0">PAC prefills the equipment and surveillance codes from your SimBrief OFP. Confirm they match your aircraft, check the UTC departure time/date and flight rules/type, then review the message. Copy it into VATSIM's <b>Import ICAO FPL</b> box and click <b>Process</b>.</p>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px;margin:8px 0">
        <label style="display:grid;gap:4px;font-size:13px;font-weight:600">Equipment/surveillance codes<input data-vatsim-equipment autocomplete="off" value="${esc(equipment)}" placeholder="Provided by SimBrief when available"></label>
        <label style="display:grid;gap:4px;font-size:13px;font-weight:600">Departure time (UTC)<input data-vatsim-time type="time" value="${esc(scheduled.time)}"></label>
        <label style="display:grid;gap:4px;font-size:13px;font-weight:600">Flight date (UTC)<input data-vatsim-date type="date" value="${esc(flightDate)}"></label>
        <label style="display:grid;gap:4px;font-size:13px;font-weight:600">Cruise speed (knots)<input data-vatsim-speed inputmode="numeric" value="${esc(ofp.cruise_tas_kt || "")}" placeholder="e.g. 441"></label>
        <label style="display:grid;gap:4px;font-size:13px;font-weight:600">Flight rules<select data-vatsim-rules><option value="I" ${ofp.flight_rules === "I" ? "selected" : ""}>IFR</option><option value="V" ${ofp.flight_rules === "V" ? "selected" : ""}>VFR</option></select></label>
        <label style="display:grid;gap:4px;font-size:13px;font-weight:600">Flight type<select data-vatsim-flight-type><option value="N" ${ofp.flight_type !== "S" ? "selected" : ""}>Non-scheduled</option><option value="S" ${ofp.flight_type === "S" ? "selected" : ""}>Scheduled</option></select></label>
      </div>
      <textarea data-vatsim-icao-output readonly rows="6" aria-label="ICAO flight plan message"></textarea>
      <div class="row" style="margin-top:6px"><button class="btn ghost small" type="button" data-vatsim-icao-copy disabled>Copy ICAO FPL for VATSIM import</button><span class="muted" data-vatsim-icao-status role="status"></span></div>
    </details>
    <details style="margin-top:8px"><summary>View filing details</summary><textarea data-vatsim-details readonly rows="8">${esc(vatsimFilingDetails(m, aircraft, ofp))}</textarea></details></div>`;
}
function wireVatsimFiling(root, m, aircraft, ofp) {
  const button = root.querySelector("[data-vatsim-copy]");
  if (!button) return;
  button.onclick = async () => {
    const field = root.querySelector("[data-vatsim-details]");
    try { await navigator.clipboard.writeText(vatsimFilingDetails(m, aircraft, ofp)); toast("VATSIM filing details copied."); }
    catch (e) {
      if (!field) { toast("Could not copy VATSIM filing details."); return; }
      field.closest("details").open = true; field.focus(); field.select();
      toast("Clipboard unavailable. Filing details are selected; press Ctrl+C.");
    }
  };
  const buildButton = root.querySelector("[data-vatsim-icao-copy]");
  if (!buildButton) return;
  const output = root.querySelector("[data-vatsim-icao-output]");
  const status = root.querySelector("[data-vatsim-icao-status]");
  const values = () => ({
    equipment: root.querySelector("[data-vatsim-equipment]").value,
    departureTime: root.querySelector("[data-vatsim-time]").value,
    flightDate: root.querySelector("[data-vatsim-date]").value,
    speed: root.querySelector("[data-vatsim-speed]").value,
    rules: root.querySelector("[data-vatsim-rules]").value,
    flightType: root.querySelector("[data-vatsim-flight-type]").value,
  });
  const refresh = () => {
    const result = vatsimIcaoFpl(m, aircraft, ofp, values());
    output.value = result.text || "Complete the required fields above to generate an ICAO flight plan.";
    buildButton.disabled = !!result.missing.length;
    status.textContent = result.missing.length ? `Still needed: ${result.missing.join(", ")}.` : "Ready to import. Review all values before filing.";
  };
  root.querySelectorAll("[data-vatsim-equipment], [data-vatsim-time], [data-vatsim-date], [data-vatsim-speed], [data-vatsim-rules], [data-vatsim-flight-type]").forEach(el => {
    el.addEventListener("input", refresh); el.addEventListener("change", refresh);
  });
  buildButton.onclick = async () => {
    const field = root.querySelector("[data-vatsim-icao-output]");
    try { await navigator.clipboard.writeText(field.value); toast("ICAO flight plan copied. Paste it into VATSIM's Import ICAO FPL dialog."); }
    catch (e) { field.focus(); field.select(); toast("Clipboard unavailable. The ICAO flight plan is selected; press Ctrl+C."); }
  };
  refresh();
}
/* A partner airline's real tail for a contract flight: the same pick as the server's partner_tail() */
function partnerTail(m, ac) {
  if (!m?.contract) return null;
  const regs = (S.partners || {})[m.operator?.key]?.registrations?.[ac] || [];
  if (!regs.length) return null;
  return regs[[...`${m.id}|${ac}`].reduce((a, ch) => a + ch.charCodeAt(0), 0) % regs.length];
}
/* SimBrief airframes: the pilot's own per simulator, then PAC's, then SimBrief's standard type */
function dualSim(ac) { return fliesIn(ac, "MSFS") && fliesIn(ac, "X-Plane"); }
function planSim(ac) {
  if (!dualSim(ac)) return fliesIn(ac, "X-Plane") ? "X-Plane" : "MSFS";
  if (!S.planSim) { try { S.planSim = localStorage.getItem("pac.planSim") || ""; } catch (e) { S.planSim = ""; } }
  return S.planSim || "MSFS";
}
function myAirframes(ac) { return (S.settings?.simbrief_airframes || {})[ac] || {}; }
function myAirframe(ac, sim) { return myAirframes(ac)[sim || planSim(ac)] || ""; }
function simPicker(ac) {   // only for aircraft flown in both sims when the pilot has their own airframe saved
  if (!dualSim(ac) || !Object.keys(myAirframes(ac)).length) return "";
  const cur = planSim(ac);
  return `<div class="sim-pick" role="group" aria-label="Simulator you're planning for"><span>Planning for</span>${["MSFS", "X-Plane"].map(x =>
    `<button type="button" data-psim="${x}" class="${x === cur ? "on" : ""}" aria-pressed="${x === cur}">${x}</button>`).join("")}
    <small class="muted">uses ${myAirframe(ac, cur) ? "your" : S.fleet[ac]?.simbrief_airframe ? "PAC's" : "SimBrief's standard"} ${esc(cur)} airframe</small></div>`;
}
document.addEventListener("click", e => {
  const b = e.target.closest("[data-psim]"); if (!b) return;
  S.planSim = b.dataset.psim; try { localStorage.setItem("pac.planSim", S.planSim); } catch (err) { /* private window */ }
  if (S.selected && !$("#view-missions")?.hidden) renderDossier();
  if (!$("#view-bids")?.hidden) loadBids();
});
// volumetric loading: when the hold fills before the weight limit, the server sends the payload that fits (S.volCap)
function planPayload(m, ac) {
  const vc = S.volCap?.[`${m.id}|${ac}`];
  return vc ? vc.lbs : Math.min(m.payload_lbs, S.fleet[ac]?.max_payload_lbs || m.payload_lbs);
}
function volNoteHtml(vc, m) {
  if (!vc) return "";
  return `<div class="notice" style="margin-bottom:10px"><b>Volume limited.</b> This freight averages ${fmt(vc.density_kg_m3)} kg/m³, so the hold (${fmt(vc.volume_ft3)} ft³ usable) is full at ${fmt(vc.lbs)} lb of the ${fmt(vc.from_lbs)} lb consignment. You'll carry ${fmt(vc.lbs)} lb. After the flight is filed, the remaining ${fmt(vc.from_lbs - vc.lbs)} lb becomes waiting freight at ${esc(m?.origin?.icao || "the origin")} for another pilot to select. PAC charges the customer on chargeable weight; recovery freight is marked prepaid on its next flight.</div>`;
}
function simbriefUrl(m, ac) {
  const fl = S.fleet[ac];
  const num = m.id.replace(/\D/g, "");
  const al = m.operator?.code || filingIcao();      // PAC flights are filed as PGI on the networks: PAC is Polar Air Cargo's code
  const p = new URLSearchParams({ airline: al, fltnum: num, orig: m.origin.icao, dest: m.destination.icao, type: myAirframe(ac) || fl.simbrief_airframe || fl.simbrief_type,   // the pilot's own airframe, then PAC's, then SimBrief's default
    cargo: (planPayload(m, ac) / 1000).toFixed(1), pax: "0", units: "LBS", callsign: al + num,
    manualrmk: simbriefRemarks(m) });
  if (S.airframe && (S.airframes || []).some(a => a.reg === S.airframe && a.type === ac)) p.set("reg", S.airframe);
  else if (partnerTail(m, ac)) p.set("reg", partnerTail(m, ac));      // the partner's own aircraft, not SimBrief's default tail
  if (S.extraFuel > 0) p.set("addedfuel", (S.extraFuel / 1000).toFixed(1));   // the pilot's discretionary extra fuel, in thousands of lb
  const h = S.planHelp?.[`${m.id}|${ac}`];
  if (h && S.usePlanHelp !== false) {  // the planning helper's suggestions, pre-filled in SimBrief
    p.set("fl", String(h.cruise_fl * 100));
    if (h.alternate) p.set("altn", h.alternate.icao);
  }
  return "https://www.simbrief.com/system/dispatch.php?" + p.toString();
}
