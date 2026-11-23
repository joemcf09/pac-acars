const VIEWS = ["privacy", "roster", "home", "dashboard", "missions", "bids", "acars", "fleet", "stations", "downloads", "career", "stats", "finance", "shop", "live", "logbook", "gallery", "handbook", "cargoguide", "staff", "liverylib", "creative", "commercial", "fleetmgr", "operations", "academy", "messages", "profile", "pilots", "updates"];
function hasCap(cap) { return !!(S.me && (S.me.staff || (S.me.staff_caps || []).includes(cap))); }
const TOUR_ORDER = {};
function applyCore(d) {
  if (d.partners) S.partners = d.partners;
  if (d.hubs) S.hubs = d.hubs;
  Object.assign(S, { airframes: d.airframes || [], tourLegs: d.tour_legs || [], tours: d.tours || [], featured: d.featured || [],
    activeEvents: d.active_events || [], career: d.career || {}, ranks: d.ranks || [], checkrideId: d.checkride_id || "PAC001",
    tourDone: Object.fromEntries(Object.entries(d.tour_progress || {}).map(([k, v]) => [k, v.next])),
    rotations: d.rotations || [], rotationProgress: d.rotation_progress || {},
    rotationNext: Object.fromEntries(Object.entries(d.rotation_progress || {}).map(([k, v]) => [k, v.next])) });
}
async function refreshCore({profileOnly = false} = {}) {
  if (!initialCoreNavigation) {
  try { const d = await api("/api/bootstrap"); S.settings = d.settings; S.booking = d.booking; applyCore(d); } catch (e) { /* offline */ }
  }
  if (!S.me) return;  // visitors: nothing personal to load
  paintBid();
  if (profileOnly) return;
  await Promise.allSettled([
    (async () => { try { S.ratings = await api("/api/ratings"); S.checkrides = S.ratings.families.map(f => f.mission).filter(Boolean); } catch (e) { /* ignore */ } })(),
    (async () => { loadMe(); })(),
    loadZones(),
    (async () => { try { S.jobs = await api("/api/jobs"); const n = S.jobs.filter(j => !j.contract).length, jc = $("#jobsCount"); if (jc) { jc.textContent = n; jc.hidden = !n; } } catch (e) { /* ignore */ } })(),
    (async () => { try { S.urgent = await api("/api/urgent"); const c = $("#urgentCount"); if (c) { c.textContent = S.urgent.length; c.hidden = !S.urgent.length; } } catch (e) { /* ignore */ } })()
  ]);
  if (!S.planningDraftChecked) {
    if (S.selected) S.planningDraftChecked = true;
    else await restorePlanningDraft(true);
    if (!$("#view-missions").hidden) renderMissions();
  }
}
function eventMatches(e, m) {
  if (e.categories?.length && !e.categories.includes(m.category)) return false;
  if (e.regions?.length && !e.regions.includes(m.region)) return false;
  if (e.airports?.length && !e.airports.some(a => a === m.origin.icao || a === m.destination.icao)) return false;
  return true;
}
function bonusTags(m) {
  const t = (S.activeEvents || []).filter(e => eventMatches(e, m)).map(e => `<span class="tag">${esc(e.name)} ×${e.multiplier}</span>`);
  if ((S.featured || []).includes(m.id)) t.push(`<span class="tag dark">Featured ×1.25</span>`);
  return t.join("");
}
function rankImg(name, cls = "") {
  const r = (S.ranks || []).find(x => x.name === name);
  return r?.insignia ? `<img class="insignia ${cls}" src="${r.insignia}" alt="${esc(name)} insignia" loading="lazy">` : "";
}
function rankFor(ac) { return S.fleet[ac]?.unlock_rank || (S.ranks || []).find(r => r.unlocks.includes(ac))?.name || ""; }
/* dispatch paperwork: the captain reviews and signs the release (and the NOTOC) before PAC ACARS starts */
function needsSignature(b) {
  return !!b && !b.legacy_release && !b.signed && (b.dispatch?.version || 1) >= 2 && (b.release_required ?? (S.settings?.require_release_signature !== false));
}
function paperNote(b) {
  if (!b || (b.dispatch?.version || 1) < 2) return "";
  const signed = !!b.signed, required = needsSignature(b);
  const heading = signed ? "Release signed — ready for ACARS" : b.release_amended ? "Flight plan changed — review and sign again" : "Release unsigned — action required";
  return `<section role="status" style="margin:16px 0;padding:22px;border:2px solid ${signed ? '#237b48' : '#a76500'};border-left-width:8px;background:${signed ? '#edf8f0' : '#fff5dc'};color:#20252b">
    <strong style="display:block;font-size:21px;margin-bottom:8px">${heading}</strong>
    <p>${signed ? 'Your release acknowledgment is recorded. Other flight eligibility checks still apply.' : 'Review the route, fuel, load, weather and handling plan. Acknowledge the NOTOC when dangerous goods are carried.'}</p>
    ${!b.ofp ? '<p><b>Import your final SimBrief OFP first.</b> A later plan change requires a new signature.</p>' : ''}
    <p>${required ? '<b>Flight tracking is blocked until you sign.</b>' : signed ? '' : 'Signing is optional under the current staff rule.'}</p>
    <a class="btn" href="/dispatch" target="_blank" rel="noopener">${signed ? 'View signed release' : 'Review and sign release →'}</a>
    <button class="btn" style="color:#8b0000;background:#fff;border:2px solid #8b0000" type="button" onclick="importRevisedSimbrief(this)">Import revised SimBrief plan</button>
    ${b.aircraft === 'B738F' ? '<a class="btn" style="color:#8b0000;background:#fff;border:2px solid #8b0000" href="/load-planner" target="_blank" rel="noopener">737 load planner</a>' : ''}
    ${b.aircraft === 'B722F' ? '<a class="btn" style="color:#8b0000;background:#fff;border:2px solid #8b0000" href="/load-planner-727" target="_blank" rel="noopener">727 load planner</a>' : ''}
    ${!['B738F', 'B722F'].includes(b.aircraft) && !(b.dispatch || {}).ferry ? '<a class="btn" style="color:#8b0000;background:#fff;border:2px solid #8b0000" href="/load-planner-all" target="_blank" rel="noopener">Load planner</a>' : ''}
    <button class="btn" style="color:#8b0000;background:#fff;border:2px solid #8b0000" type="button" onclick="sendToSayIntentions(this)">Send to SayIntentions</button>
  </section>`;
}
let revisedSimbriefBusy = false;
async function importRevisedSimbrief(button) {
  if (!S.booking || revisedSimbriefBusy) return;
  if (!confirm("Generate your updated OFP in SimBrief first. Import its latest plan now? This rebuilds your dispatch release and requires a fresh review and signature, even if you import the same plan again.")) return;
  revisedSimbriefBusy = true;
  button.disabled = true;
  button.textContent = "Importing from SimBrief…";
  let imported = false;
  try {
    const result = await api('/api/acars/app/ofp', {method:'POST', body:{}});
    imported = true;
    const data = await api('/api/bootstrap');
    S.booking = data.booking;
    applyCore(data);
    paintBid();
    renderAcars();
    if (location.hash === '#bids') await loadBids();
    toast('SimBrief plan imported. Review and sign the revised dispatch release.' + (result.warnings?.length ? ' ' + result.warnings.join(' ') : ''));
  } catch (e) {
    toast(imported ? 'Plan imported, but the page could not refresh. Reload the page and review the revised release.' : 'SimBrief import failed: ' + e.message);
  } finally {
    revisedSimbriefBusy = false;
    button.disabled = false;
    button.textContent = 'Import revised SimBrief plan';
  }
}

let releaseRefreshing = false;
async function refreshReleaseGate() {
  if (!S.booking || releaseRefreshing || document.hidden) return;
  releaseRefreshing = true;
  const requested = S.booking.requested_at;
  try {
    const d = await api('/api/dispatch');
    if (!S.booking || S.booking.requested_at !== requested || d.requested_at !== requested) return;
    S.booking.signed = d.signed;
    S.booking.release_amended = d.release_amended;
    S.booking.release_required = d.signature_required;
    const panel = document.getElementById('releasePreflight');
    if (panel) panel.innerHTML = paperNote(S.booking);
    const btn = document.getElementById('dispatchBtn');   // the ACARS strip's button follows the signature too
    if (btn) btn.textContent = needsSignature(S.booking) ? "Review and sign paperwork" : "Dispatch release";
    const hn = document.getElementById('homeNext');   // the Home page's "Do this next" follows the signature too
    if (hn) hn.innerHTML = homeNextHTML(S.status);
    if (location.hash === '#bids') await loadBids();
  } catch (e) { /* Keep last state; server independently enforces the start gate. */ }
  finally { releaseRefreshing = false; }
}
window.addEventListener('focus', refreshReleaseGate);
// the release was signed in its own tab (which then closes itself): update ACARS straight away
try { new BroadcastChannel("pac-release").onmessage = () => refreshReleaseGate(); } catch (_) {}
window.addEventListener('storage', e => { if (e.key === "pac-release-signed") refreshReleaseGate(); });
document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshReleaseGate(); });
function needsRating(m, ac) {   // the family's type rating, while ratings are required ("" when not needed)
  const r = S.ratings;
  if (!r?.required || m.id === S.checkrideId || m.type_checkride || m.contract) return "";
  const f = (r.families || []).find(x => x.types.includes(ac));
  return f && !f.rated ? f.family : "";
}
function lockedByRank(m, ac) {
  if (m.type_checkride && S.ratings?.direct_entry) return false;   // direct entry: any type checkride, any rank
  return S.settings.enforce_ranks && m.id !== S.checkrideId && !(S.career.unlocked || []).includes(ac);
}
function flyMission(id, preferredAircraft = null) {
  const inList = (l) => l.some(m => m.id === id);
  S.board = inList(S.missions) ? "missions" : inList(S.urgent || []) ? "urgent" : (S.jobs || []).some(x => x.id === id && x.contract) ? "partners" : inList(S.jobs || []) ? "jobs" : inList(S.routes) && !(S.featured || []).includes(id) ? "network" : (S.tourLegs || []).some(x => x.id === id && x.rotation) ? "rotations" : "events";
  S.selected = null; S.ofp = null; S.ofpErrors = []; S.ofpWarnings = []; S.planned = false;
  show("missions");
  setTimeout(() => {
    selectMission(id);
    if (S.selected?.id === id && preferredAircraft && !S.fleet[preferredAircraft]?.retired && fleetOrder(S.selected).includes(preferredAircraft)) {
      S.aircraft = preferredAircraft;
      S.airframe = defaultAirframe(S.selected, preferredAircraft);
      renderDossier();
    }
  }, 30);
}
function openPhoto(src, caption) {
  $("#photoBig").src = src; $("#photoBig").alt = caption; $("#photoCap").textContent = caption; $("#photoDlg").showModal();
}
const CATEGORY_LIST = ["Humanitarian", "Medical", "Urgent", "Heavy lift", "Express", "Premium", "Sports & events", "Scheduled", "Charter", "Tour", "Ferry", "Checkride"];
const REGION_LIST = ["US domestic", "Americas", "Transatlantic", "Europe", "Middle East & Africa", "Asia-Pacific", "Transpacific"];
const fmtDate = s => new Date(s + "T00:00:00Z").toLocaleDateString("en-US", { day: "numeric", month: "short", timeZone: "UTC" });

/* ================= Split-flap board ================= */
const FLAP_CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.";
const FB_COLS = [["time", 4, "Time"], ["flight", 7, "Flight"], ["from", 4, "From"], ["to", 4, "To"], ["type", 4, "Type"], ["tail", 6, "Tail"], ["pilot", 10, "Pilot"], ["status", 10, "Status"], ["remark", 9, "Remark"]];
const FB_ROWS = 7;
const flapQueue = new Set();
let flapRunning = false;
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
function fbTone(st) {
  if (/ARRIVED|AT GATE|LANDED/.test(st)) return "green";
  if (/EN ROUTE|CLIMB|DESCEND|APPROACH|DEPART|TAXI|PUSH|BOARD/.test(st)) return "amber";
  if (/INCIDENT|DIVERT|GO AROUND|LATE/.test(st)) return "red";
  if (/BOOKED/.test(st)) return "blue";
  return "";
}
function buildBoard(el) {
  el.innerHTML='<tbody><tr><td>Loading flight board…</td></tr></tbody>';
}
function setBoard(el, rows) {
  const list=(rows || []).filter(r=>r.flight || r.from || r.to);
  el.innerHTML=`<caption>${el.id==='fbDep'?'Departures':'Arrivals and active flights'} · ${list.length} displayed · UTC</caption><thead><tr>${FB_COLS.map(([k,n,l])=>`<th scope="col">${esc(l)}</th>`).join('')}</tr></thead><tbody>${list.length?list.map(row=>`<tr data-tone="${fbTone(row.status || '')}">${FB_COLS.map(([k])=>`<td class="board-cell board-${k}" title="${esc(row[k] || '')}">${k==='status'?`<span class="board-status">${esc(row[k] || '—')}</span>`:esc(row[k] || '—')}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${FB_COLS.length}" class="board-empty">No flights to display right now.</td></tr>`}</tbody>`;
}
function runFlaps() {
  flapRunning = true;
  let last = 0;
  const tick = ts => {
    if (ts - last < 55) { requestAnimationFrame(tick); return; }
    last = ts;
    for (const cell of flapQueue) {
      let steps = +cell.dataset.steps;
      if (steps <= 0) { cell.textContent = cell.dataset.target; flapQueue.delete(cell); continue; }
      cell.dataset.steps = String(steps - 1);
      cell.textContent = steps === 1 ? cell.dataset.target : FLAP_CHARS[1 + Math.floor(Math.random() * (FLAP_CHARS.length - 1))];
      cell.classList.remove("tick"); void cell.offsetWidth; cell.classList.add("tick");
    }
    if (flapQueue.size) requestAnimationFrame(tick); else flapRunning = false;
  };
  requestAnimationFrame(tick);
}
async function refreshBoard() {
  clearTimeout(S.boardTimer);
  if ($("#view-home").hidden || !$("#flapboard")) return;
  try {
    const b = await api("/api/va/board");
    setBoard($("#fbDep"), b.departures);
    setBoard($("#fbArr"), b.arrivals);
    $("#boardFreshness").textContent = "Updated " + new Date().toISOString().slice(11,19) + " UTC";
  } catch (e) { if ($("#boardFreshness")) $("#boardFreshness").textContent="Update unavailable · showing last received information"; }
  S.boardTimer = setTimeout(refreshBoard, 30000);
}
function tickClock() {
  clearTimeout(S.clockTimer);
  const c = $("#fbClock");
  if (!c || $("#view-home").hidden) return;
  const d = new Date();
  c.textContent = `${String(d.getUTCHours()).padStart(2, "0")}${String(d.getUTCMinutes()).padStart(2, "0")}Z`;
  S.clockTimer = setTimeout(tickClock, 5000);
}

/* ================= Home ================= */
let homeLoadPending = null;
function loadHome() {
  if (homeLoadPending) return homeLoadPending;
  homeLoadPending = (async () => {
    try {
      // Bootstrap already supplies fleet/routes. Home does not need checkride/job-board data.
      const [h, st, urgent] = await Promise.all([
        api("/api/va/home"), api("/api/acars/status").catch(() => ({})),
        S.me ? api("/api/urgent").catch(() => []) : Promise.resolve([])
      ]);
      S.home = h; S.urgent = urgent;
      await renderHome(h, st);
    } catch (e) { toast(e.message); }
  })().finally(() => { homeLoadPending = null; });
  return homeLoadPending;
}
let homeWeatherObserver = null;
function whenHomeMapVisible(callback) {
  if (homeWeatherObserver) { homeWeatherObserver.disconnect(); homeWeatherObserver = null; }
  const element = $("#homeMap");
  if (!element) return;
  if (!("IntersectionObserver" in window)) { callback(); return; }
  const observer = new IntersectionObserver(entries => {
    if (!entries.some(entry => entry.isIntersecting)) return;
    observer.disconnect();
    if (homeWeatherObserver === observer) homeWeatherObserver = null;
    if (element.isConnected) callback();
  }, {rootMargin: "200px"});
  homeWeatherObserver = observer;
  observer.observe(element);
}
function networkPartners(h) {
  // each network's logo shows only once staff switch it on, after that network has accepted PAC (Staff › Site and rules › Flying online)
  const n = h.network_logos || {};
  const nets = [n.show && n.vatsim ? { name: "VATSIM", href: "https://www.vatsim.net", logo: n.vatsim } : null,
                n.ivao_show && n.ivao ? { name: "IVAO", href: "https://us.ivao.aero/pilots/virtual-airlines", logo: n.ivao } : null].filter(Boolean);
  if (!nets.length) return "";
  return `<div class="section-h" id="network-partners"><div><div class="kicker">Online networks</div><h2>Fly online with ${nets.map(x => x.name).join(" and ")}</h2>
      <p>${nets.some(x => x.name === "IVAO") ? `PAC is an <a href="https://us.ivao.aero/pilots/virtual-airlines" target="_blank" rel="noopener"><b>IVAO Certified Virtual Airline</b></a> (IVAO United States). ` : ""}Live air traffic control from real people, all over the world, free to join. PAC flights file as <b>${esc(filingIcao())}</b>, spoken “Pagani”.</p></div></div>
    <div class="net-partners">${nets.map(x => `<a class="net-logo" href="${x.href}" target="_blank" rel="noopener"><img src="${esc(x.logo)}" alt="${x.name}"></a>`).join("")}</div>`;
}
async function fillHomeCampaigns() {
  const el = $("#homeCampaigns"); if (!el || !S.me?.id) return;
  try {
    const d = await api("/api/pilot/cargo-campaigns"); if (!el.isConnected) return;
    const live = (d.campaigns || []).filter(c => c.phase === "Active");
    el.innerHTML = live.length ? `<div class="section-h"><div><div class="kicker">Operation in progress</div><h2>Fly for the shared goal</h2></div><button class="btn ghost small" data-stats-tab="campaigns">All campaigns</button></div>
      ${live.map(c => { const left = Math.max(0, Math.ceil((c.ends - Date.now() / 1000) / 86400)); return `<div class="home-op">${c.patch ? `<img src="${esc(c.patch)}" alt="">` : ""}<div class="home-op-body"><h3>${esc(c.title)}</h3>
        <div class="cargo-progress"><strong>${fmt(c.cargo_lbs)} <small>/ ${fmt(c.target_lbs)} lb to ${c.destinations.map(esc).join(" · ")}</small></strong><span>${c.pct}%</span></div>
        <progress max="100" value="${c.pct}">${c.pct}%</progress>
        <p class="muted" style="margin:4px 0 10px">${fmt(c.flights)} ${c.flights === 1 ? "delivery" : "deliveries"} · ${fmt(c.pilots)} ${c.pilots === 1 ? "pilot" : "pilots"} · ${left} day${left === 1 ? "" : "s"} left${c.personal_lbs > 0 ? ` · You: <b>${fmt(c.personal_lbs)} lb</b>` : ""}${c.reward_cash > 0 ? ` · Reward: patch + $${fmt(c.reward_cash)}` : ""}</p>
        <button class="btn small" onclick="S.boardCampaignId='${Number(c.id)}';show('missions')">Find flights to ${esc(c.destinations[0])} and more →</button></div></div>`; }).join("")}` : "";
  } catch (e) { el.innerHTML = ""; }
}
// Real-world tools and platforms PAC flies with. Edit freely. "kind" is the little label on each card.
const TECH_PARTNERS = [
  { name: "SayIntentions.AI", kind: "Integration", url: "https://www.sayintentions.ai",
    logo: "/static/tools/sayintentions-logo.png", logoAlt: "SayIntentions.AI", logoClass: "si-logo",
    desc: "AI air traffic control. PAC links to it through VA-Link, so the flights you fly there log straight back to your PAC logbook." },
  { name: "SimBrief by Navigraph", kind: "Dispatch", url: "https://www.simbrief.com",
    // Navigraph's official logo files, unmodified (light and dark versions), per their brand guidelines
    logo: "/static/tools/navigraph-logo.svg", logoDark: "/static/tools/navigraph-logo-black.svg", logoAlt: "Navigraph",
    desc: "Every PAC dispatch release is built on a SimBrief OFP: real fuel, weights and routing for your flight." },
  { name: "TFDi Design", kind: "Fleet", url: "https://www.tfdidesign.com",
    desc: "The study-level MD-11, flown in PAC colours as the MD-11F." },
  { name: "iniBuilds", kind: "Fleet", url: "https://www.inibuilds.com",
    desc: "The A300-600F, one of PAC's widebody freighters." },
  { name: "VATSIM", kind: "Network", url: "https://vatsim.net",
    desc: 'Fly PAC online with live human ATC. On the network you are PGI, spoken "Pagani".' },
  { name: "IVAO", kind: "Network", url: "https://ivao.aero",
    desc: "PAC also flies on IVAO's online network." },
];

async function renderHome(h, st) {
  const t = h.totals, f = h.founder || {}, site = h.site;
  const codes = fleetCodes();
  const heroAc = S.fleet.B77F || S.fleet[codes[0]];
  const live = st && st.live && (st.tracking || st.complete === false) ? st : null;
  const hubs = [["KCVG", "Cincinnati", "Main hub"], ["LIMC", "Milan Malpensa", "European gateway"], ["KMIA", "Miami", "Latin America gateway"],
    ["OMDW", "Dubai World Central", "Middle East & Africa"], ["VHHH", "Hong Kong", "Asia gateway"], ["PANC", "Anchorage", "Transpacific tech stop"],
    ...Object.entries(S.hubs || {}).filter(([k]) => !["KCVG", "LIMC", "KMIA", "OMDW", "VHHH", "PANC"].includes(k)).map(([k, v]) => [k, v, "PAC hub"])];
  const routeCount = ic => S.routes.filter(r => r.origin.icao === ic || r.destination.icao === ic).length;
  const [news, shots] = await Promise.all([loadNews(), api("/api/gallery?limit=8").catch(() => [])]);
  $("#homeRoot").innerHTML = `
  <section class="hero${S.me ? " hero-slim" : ""}">
    <img class="bg" fetchpriority="high" decoding="async" ${illSrc(S.me ? "ill-briefing-room" : "ill-ramp-night", "100vw", "20261113")} alt=""><span class="ill-tag">Illustration</span>
    <div class="hero-in">
      ${live ? `<div class="live-pill"><i></i>${esc(S.booking?.flight_number || "")} in the air · ${esc(st.phase_label)}</div>` : ""}
      <img class="wm" src="/static/pac-wordmark-white.png" alt="Pagani Air Cargo">
      ${S.me ? `<h1>Welcome back, ${esc(S.me.name)}</h1>
      <p>Your briefing, your bookings and what needs a crew today are on your dashboard.</p>
      <div class="row"><button class="btn light" onclick="show('dashboard')">Go to your dashboard</button><button class="btn ghost" onclick="show('missions')">Book a flight</button></div>`
      : `<h1>Real freight. Real paperwork. Real consequences.</h1>
      <p>Pagani Air Cargo is a cargo-only virtual airline for Microsoft Flight Simulator and X-Plane. Every load has a waybill, a deadline and somewhere to be.</p>
      <div class="row"><a class="btn light" href="#apply" id="heroApply">Apply to fly</a>${PUBLIC_VIEWS.includes("live") ? `<button class="btn ghost" onclick="show('live')">Watch a flight live</button>` : `<button class="btn ghost" onclick="(S.me ? show('network') : location.href='/network')">See the cargo network</button>`}<button class="btn ghost" onclick="show('fleet')">Meet the fleet</button></div>`}
    </div>
  </section>
  ${S.me ? "" : `<section class="proof-band"><div class="proof-in">
    <div><span>Pilots</span><b>${fmt(t.pilots)}</b></div>
    ${t.flights ? `<div><span>Flights flown</span><b>${fmt(t.flights)}</b></div><div><span>Freight delivered</span><b>${fmtLbShort(t.cargo)} <small>lb</small></b></div>` : `<div><span>Routes</span><b>${fmt(t.routes)}</b></div><div><span>Stations</span><b>${fmt(t.stations)}</b></div>`}
    <div><span>Freighter types</span><b>${Object.keys(S.fleet).length}</b></div></div></section>`}
  <section class="stat-band"${S.me ? "" : " hidden"}><div class="stat-band-in">
    <div><span>Pilots</span><b>${fmt(t.pilots)}</b></div>
    ${t.flights ? `<div><span>Flights flown</span><b>${fmt(t.flights)}</b></div>
    <div><span>Block hours</span><b>${esch(t.hours)}</b></div>
    <div><span>Cargo delivered</span><b>${fmtLbShort(t.cargo)} lb</b></div>` : `<div><span>Aircraft types</span><b>${Object.keys(S.fleet).length}</b></div><div><span>Main hub</span><b>KCVG</b></div><div><span>Simulators</span><b>MSFS · XP</b></div>`}
    <div><span>Routes</span><b>${fmt(t.routes)}</b></div>
    <div><span>Stations</span><b>${fmt(t.stations)}</b></div>
    <div><span>Aircraft</span><b>${fmt(t.airframes)}</b></div>
  </div></section>
  ${whyPacHTML()}

  ${news.length ? `<div class="section-h"><div><div class="kicker">Company news</div><h2>What's happening at PAC</h2></div></div>${newsCards(news)}` : ""}

  ${shots.length ? `<div class="section-h"><div><div class="kicker">From the flight deck</div><h2>Gallery</h2></div><button class="btn ghost small" onclick="show('gallery')">See all screenshots</button></div>${shotTiles(shots.slice(0, 8), "home")}` : ""}

  <div class="section-h"><div><div class="kicker">Live from the ops center</div><h2>Departures and arrivals</h2></div><span class="muted" style="font-size:13px">Updates every 30 seconds · times in UTC</span></div>
  <div class="flapboard ops-board" id="flapboard" aria-live="off">
    <div class="fb-head"><div class="fb-title"><i>✈</i>DEPARTURES</div><div class="fb-clock" id="fbClock">----Z</div></div>
    <div class="board-scroll" tabindex="0" role="region" aria-label="Departures flight table"><table class="fb-table" id="fbDep"></table></div>
    <div class="fb-sep"></div>
    <div class="fb-head"><div class="fb-title"><i style="transform:rotate(90deg)">✈</i>ARRIVALS &amp; ACTIVE FLIGHTS</div></div>
    <div class="board-scroll" tabindex="0" role="region" aria-label="Arrivals flight table"><table class="fb-table" id="fbArr"></table></div><div class="board-foot"><span>Every PAC pilot's booked and active flights, then the latest arrivals. OPEN rows are featured routes anyone can fly.</span><span id="boardFreshness" role="status">Waiting for flight data…</span></div>
  </div>

  <div id="homeCampaigns"></div>
  ${h.events.length ? `<div class="section-h"><div><div class="kicker">On now</div><h2>Events</h2></div><button class="btn ghost small" onclick="show('career')">All events and tours</button></div>
  <div class="two-col">${h.events.map(e => `<div class="event-card"><h3>${esc(e.name)} <span class="tag">×${e.multiplier} points</span></h3><div class="when">${fmtDate(e.start)} – ${fmtDate(e.end)}</div><p style="margin:8px 0 0">${esc(e.description)}</p></div>`).join("")}</div>` : ""}

  ${(S.urgent || []).length ? `<div class="section-h"><div><div class="kicker">Needs a crew now</div><h2>Urgent requests</h2></div><button class="btn ghost small" onclick="S.board='urgent';show('missions')">All urgent requests</button></div>
  <div class="urgent-cards">${S.urgent.map(m => m.relief ? reliefCard(m) : `<div class="urgent-card"><div class="muted" style="font-size:12px;letter-spacing:.08em">${esc(m.urgent_kind.toUpperCase())} · ${esc(m.id)}</div>
    <h3>${esc(m.title)}</h3><div class="rt">${m.origin.icao} → ${m.destination.icao}</div>
    <div class="muted" style="font-size:13px">${esc(S.fleet[m.aircraft[0]]?.name || "")} ${esc(m.suggested_airframe || "")} · ${fmt(m.payload_lbs)} lb</div>
    <div style="font-size:13px">Offer expires in <span class="countdown" data-countdown="${m.expires}"></span> · deliver by ${zulu(m.deliver_by)}</div>
    <button class="btn small" style="align-self:flex-start;position:relative;z-index:1" onclick="flyMission('${m.id}')">Take this flight</button></div>`).join("")}</div>` : ""}

  <div class="section-h"><div><div class="kicker">The liveries</div><h2>${(NUM_WORDS[codes.length] || codes.length).toString().replace(/^./, c => c.toUpperCase())} freighters, one red</h2><p>Flown in Microsoft Flight Simulator and X-Plane.</p></div><button class="btn ghost small" onclick="show('fleet')">Fleet details</button></div>
  <div class="livery-grid">${[...codes].sort((a, b) => (b === "B77F") - (a === "B77F")).map(k => `<button data-photo="${k}" aria-label="Enlarge the ${esc(S.fleet[k].name)}"><img src="${esc(displayPhoto(S.fleet[k].thumb || S.fleet[k].photo))}" alt="" loading="lazy"><span>${esc(S.fleet[k].name)}${S.fleet[k].sim === "X-Plane" ? " · XP" : ""}</span></button>`).join("")}${codes.length % 3 === 2 ? `<button class="livery-more" onclick="show('fleet')"><b>Meet the whole fleet</b><small>Specs, airframes and where they are now</small></button>` : ""}</div>

  <div class="section-h"><div><div class="kicker">The network</div><h2>${fmt(t.routes)} routes across ${fmt(t.stations)} stations</h2></div><button class="btn ghost small" onclick="S.board='network';show('missions')">Browse the network</button></div>
  <div class="net-split"><div id="homeMap"></div>
    <div class="net-side"><h3 style="margin:0">Hubs and gateways</h3>
      <ul class="hub-list">${hubs.map(([ic, name, role]) => `<li><span><b>${ic}</b> ${esc(name)}<br><small class="muted">${role}</small></span><span class="muted">${routeCount(ic)} routes</span></li>`).join("")}</ul>
    </div></div>

  <div class="section-h"><div><div class="kicker">Operations</div><h2>In the air and just arrived</h2></div></div>
  <div class="two-col">
    <div class="live-card">${live ? `
      <div class="muted">In the air now</div>
      <div class="fn">${esc(S.booking?.flight_number || "")}</div>
      <div>${esc(S.booking?.mission.origin.icao)} to ${esc(S.booking?.mission.destination.icao)} · ${esc(S.fleet[S.booking?.aircraft]?.name || "")}${S.booking?.airframe ? " · " + esc(S.booking.airframe) : ""}</div>
      <div class="live-grid">
        <div><span>Phase</span><b>${esc(st.phase_label)}</b></div>
        <div><span>Altitude</span><b>${fmt(st.live.alt_ft)} ft</b></div>
        <div><span>Ground speed</span><b>${fmt(st.live.gs)} kt</b></div>
        <div><span>To go</span><b>${fmt(st.dtg_nm)} nm</b></div>
      </div>
      <button class="btn small" style="margin-top:14px" onclick="show('acars')">Open ACARS</button>` : `
      <div class="muted">In the air now</div><div class="fn" style="font-size:22px;margin:6px 0">No flights airborne</div>
      <p class="muted" style="margin:0 0 12px">${S.booking ? `${esc(S.booking.flight_number)} is booked and waiting at ${esc(S.booking.mission.origin.icao)}.` : "The ramp is quiet. Pick a mission and get something moving."}</p>
      <button class="btn small" onclick="show('${S.booking ? "acars" : "missions"}')">${S.booking ? "Open ACARS" : "Book a flight"}</button>`}
    </div>
    <div class="panel" style="padding:4px 20px 8px"><h3 style="margin:14px 0 4px">Recent arrivals</h3>
      ${h.recent.length ? `<ul class="arrivals">${h.recent.map(r => `<li><b>${esc(r.flight_number)}</b><span>${r.dep} – ${r.arr} · ${esc(S.fleet[r.aircraft]?.icao || r.aircraft)}<br><small class="muted">${esc(r.name || "")}</small></span><span>${r.landing_rate != null ? r.landing_rate + " fpm" : ""} <span class="tag grey">${r.grade}</span></span></li>`).join("")}</ul>`
        : `<p class="muted">No accepted flights yet. The first PIREP filed will appear here.</p>`}
    </div>
  </div>

  <div class="section-h"><div><div class="kicker">Our story</div><h2>Why PAC exists</h2></div></div>
  <article class="founder pac-story"><figure class="story-fig"><img ${illSrc("ill-hq-dusk", "(max-width: 760px) 100vw, 560px")} alt="Illustration of the PAC headquarters and freight terminal at KCVG at dusk, with PAC freighters on the apron" loading="lazy" width="1600" height="900"><span class="ill-tag">Illustration</span></figure>
    <div><blockquote>${esc(site.story)}</blockquote></div></article>

  ${Object.keys(S.partners || {}).length ? `<div class="section-h"><div><div class="kicker">Partners</div><h2>Flying alongside the biggest names in cargo</h2><p>When these operators are short of qualified captains, they hire PAC pilots to fly their aircraft. PAC crews also ride their freighters on partner jumpseat agreements.</p></div><button class="btn ghost small" onclick="S.board='partners';show('missions')">Partner crew requests</button></div>
  <div class="partner-strip">${Object.values(S.partners).map(p => `<img src="${esc(p.logo)}" alt="${esc(p.name)}" title="${esc(p.name)}">`).join("")}</div>
  <p class="muted" style="font-size:12px;margin:6px 0 0">Partnerships are simulated for Pagani Air Cargo, a flight simulation virtual airline. Names and logos are trademarks of their owners and don't imply endorsement.</p>` : ""}

  ${networkPartners(h)}

  <div class="section-h"><div><div class="kicker">Tools &amp; technology</div><h2>What PAC flies with</h2><p>The platforms and add-ons behind every PAC flight. We integrate directly with some of them.</p></div></div>
  <div class="tech-grid">${TECH_PARTNERS.map(p => `<a class="tech-card"${p.url ? ` href="${esc(p.url)}" target="_blank" rel="noopener"` : ""}><span class="tech-kind">${esc(p.kind)}</span>${p.logo ? `<span class="tech-logo"><img class="light ${esc(p.logoClass || '')}" src="${esc(p.logo)}" alt="${esc(p.logoAlt || p.name)}" loading="lazy"><img class="dark ${esc(p.logoClass || '')}" src="${esc(p.logoDark || p.logo)}" alt="${esc(p.logoAlt || p.name)}" loading="lazy"></span>` : ""}<b>${esc(p.name)}</b><span class="tech-desc">${esc(p.desc)}</span></a>`).join("")}</div>
  <p class="muted" style="font-size:12px;margin:8px 0 0">Product and company names are trademarks of their respective owners. Pagani Air Cargo is a non-commercial flight-simulation community; these references don't imply endorsement or affiliation beyond the integrations noted.</p>

  ${(() => { const de = S.settings?.direct_entry_checkrides !== false;   // direct entry: aircraft come from checkrides, not rank
    return `<div class="section-h"><div><div class="kicker">Career path</div><h2>From cadet to Senior Captain</h2><p>${de
      ? "Rank and pay grow with your hours and average score. Aircraft come from checkrides: pass the type checkride for any aircraft family, at any rank."
      : "Earn your stripes with hours and a good average score. Every rank opens up bigger aircraft."}</p></div><button class="btn ghost small" onclick="show('career')">Your progress</button></div>
  <div class="career-path">${(S.ranks || []).map(r => `<figure>${rankImg(r.name)}<b>${esc(r.name)}</b><small>${r.name === "Cadet" ? "Approved application" : r.hours ? `${r.hours} hours${r.avg ? `, avg ${r.avg}+` : ""}` : de ? "Line or any type checkride" : "Checkride passed"}</small>
    <small>${de ? (r.pay ? `$${r.pay}/h flight pay` : "") : r.unlocks.length ? r.unlocks.map(a => esc(S.fleet[a]?.icao || a)).join(", ") : "737 checkride"}</small></figure>`).join("")}</div>`; })()}

  ${discordWidget(site)}

  <div class="section-h" id="apply"><div><div class="kicker">Join the crew</div><h2>Fly for Pagani Air Cargo</h2></div><button class="btn ghost small" onclick="show('handbook')">Read the handbook</button></div>
  <div class="apply">
    <div class="pitch"><h2>Get your wings in red</h2><p style="margin:0">${esc(site.recruiting)}</p>
      <ol><li>Apply below. Staff review every application.</li><li>Choose a supported training airport for your free 737 line checkride. ACARS grades it.</li><li>Join the line as a Second Officer on the 737 and 727, and work your way to the 747-8F.</li></ol></div>
    <form id="applyForm" autocomplete="on">
      <div class="field"><label for="ap_name">Full name</label><input id="ap_name" name="name" required autocomplete="name"></div>
      <div class="field"><label for="ap_email">Email</label><input id="ap_email" name="email" type="email" required autocomplete="email"></div>
      <div class="field"><label for="ap_country">Country</label><input id="ap_country" name="country" autocomplete="country-name"></div>
      <div class="field"><label for="ap_discord">Discord username (optional)</label><input id="ap_discord" name="discord"></div>
      <div class="field"><label for="ap_sim">Simulator</label><select id="ap_sim" name="simulator"><option>MSFS 2024</option><option>MSFS 2020</option><option>X-Plane 12</option><option>X-Plane 11</option><option>Prepar3D</option></select></div>
      <div class="field"><label for="ap_exp">Simulator experience</label><select id="ap_exp" name="experience"><option>New to airliners</option><option>Under 100 hours</option><option>100–500 hours</option><option>500+ hours</option><option>Real-world pilot</option></select></div>
      <div class="field"><label for="ap_hub">Preferred hub</label><select id="ap_hub" name="hub">${hubs.map(([ic, n]) => `<option value="${ic}">${ic} ${esc(n)}</option>`).join("")}</select></div>
      <div class="field full"><label for="ap_source">Where did you hear about us?</label><select id="ap_source" name="source">
        <option value="">— Select —</option><option>Reddit</option><option>Simdispatch (VA directory)</option><option>VA-List.com</option>
        <option>X-Plane Community forum</option><option>X-Plane.org forums</option><option>Flightsim.to</option><option>Hangar Addons</option>
        <option>My Next Airline</option><option>VATSIM forum</option><option>IVAO forum</option><option>Discord</option>
        <option>A friend / word of mouth</option><option>Other</option></select></div>
      <div class="field full"><label for="ap_why">Why do you want to fly with PAC?</label><textarea id="ap_why" name="motivation" rows="3"></textarea></div>
      <label class="full" style="display:flex;gap:10px;font-size:14px;align-items:flex-start"><input type="checkbox" name="agree" style="margin-top:3px;accent-color:#fff"> I've read the <a href="#handbook" onclick="show('handbook');return false">pilot handbook</a> and will fly by its rules.</label>
      <p class="full ap-privacy">Staff use your details only to review your application and, if you join, to run your PAC account. See the <a href="#privacy" onclick="show('privacy');return false">privacy policy</a>.</p>
      <div class="full"><button class="btn light" type="submit" style="background:#fff;color:var(--red);border-color:#fff">Submit application</button></div>
    </form>
  </div>
  ${siteFooter(site)}`;
  homeLayout();
  fillHomeCampaigns(); buildBoard($("#fbDep")); buildBoard($("#fbArr")); refreshBoard(); tickClock(); tickCountdowns();
  bindShots($("#homeRoot"), shots, () => loadHome());
  const hero = $("#homeRoot .hero");
  gfHomeStrip();
  const notices = news.filter(n => n.kind === 'notam');
  if (S.me && hero && notices.length) hero.insertAdjacentHTML('afterend', `<section class="home-notices" aria-label="Latest company notices"><div class="home-notices-heading"><b>Latest notices</b><span>${notices.length} company notice${notices.length===1?'':'s'} · Select a title to read</span></div>${notices.map(n=>`<details${n.important?' class="notice-important"':''}><summary>${n.important?'<span class="notice-priority">Important</span>':''}${esc(n.title)}</summary><div class="home-notice-body">${esc(n.body || 'No further details.')}<small>${esc(n.author || 'PAC Operations')}${n.time?' · '+new Date(n.time*1000).toLocaleDateString('en-US'):''}</small></div></details>`).join('')}</section>`);
  if (hero && S.me) hero.insertAdjacentHTML('afterend', `<section class="home-next" id="homeNext">${homeNextHTML(st)}</section>`);
  if (hero && S.me && !S.me.activity) loadMe().then(() => { const hn = $("#homeNext"); if (hn) hn.innerHTML = homeNextHTML(st); }).catch(() => {});
  if ($("#heroApply")) $("#heroApply").onclick = e => { e.preventDefault(); $("#apply").scrollIntoView({ behavior: "smooth" }); };
  document.querySelectorAll("[data-photo]").forEach(b => b.onclick = () => { const a = S.fleet[b.dataset.photo]; openPhoto(a.photo, a.name); });
  if ($("#applyForm")) $("#applyForm").onsubmit = async e => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target).entries()); fd.agree = !!e.target.agree.checked;
    try {
      await api("/api/applications", { method: "POST", body: fd });
      e.target.innerHTML = `<div class="full"><h3 style="font-size:22px;margin:0 0 8px">Application received</h3><p style="margin:0">Thanks, ${esc(fd.name.split(" ")[0])}. Staff will review it shortly. Once approved, your next step is the 737 line checkride.</p></div>`;
    } catch (err) { toast(err.message); }
  };
  if (HAS_MAP) {
    if (S.homeMap) S.homeMap.remove();
    S.homeDots = [];
    const base = makeBaseMap($("#homeMap"), { theme: "light", style: S.settings.map_style === "dark" ? "light" : (S.settings.map_style || "light") });
    S.homeMap = base.map; S.homeMap.setView([30, 5], 2); S.homeMap.scrollWheelZoom.disable(); setTimeout(() => S.homeMap && S.homeMap.invalidateSize(), 200); try { new ResizeObserver(() => S.homeMap && S.homeMap.invalidateSize()).observe($("#homeMap")); } catch (e) { /* older browsers */ }
    const count = {};
    S.routes.forEach(r => {
      L.polyline(gcPath(r.origin, r.destination), { color: "#C80000", weight: 1, opacity: .3, interactive: false }).addTo(S.homeMap);
      [r.origin, r.destination].forEach(a => count[a.icao] = { a, n: (count[a.icao]?.n || 0) + 1 });
    });
    Object.values(count).forEach(({ a, n }) => {
      const main = a.icao === "KCVG", hub = hubs.some(h => h[0] === a.icao);
      (S.homeDots ||= []).push([a.icao, L.circleMarker([a.lat, a.lon], { radius: main ? 9 : hub ? 6 : 3, color: "#fff", weight: main ? 3 : 1, fillColor: hub ? "#C80000" : "#1E2126", fillOpacity: 1 })
        .bindTooltip(`${a.icao} · ${esc(a.city)} (${n})`, { className: "stn-tip", direction: "top" }).addTo(S.homeMap)]);
    });
    setTimeout(() => S.homeMap.invalidateSize(), 60);
    whenHomeMapVisible(() => loadNetworkWx(() => {
      if (!S.netWx || !S.homeMap) return;
      (S.homeDots || []).forEach(([ic, mk]) => { const c = wxColor(ic); if (c) mk.setStyle({ color: c, weight: 2.5 }); });
      wxLegend(S.homeMap);
    }));
  }
}

/* ================= Transfer hours (pilot side) ================= */
const trDate = t => new Date(t * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
async function fillTransfers() {
  const el = $("#transferPanel");
  if (!el) return;
  let d;
  try { d = await api("/api/transfers"); } catch (e) { el.innerHTML = ""; return; }
  S.transfers = d;
  const r = d.rules, last = d.requests[0];
  const tag = st => `<span class="tag ${st === "Pending" ? "amber" : st === "Approved" ? "green" : ""}">${esc(st)}</span>`;
  const history = d.requests.map(q => `<div class="tr-hist">
      <div><b>${q.status === "Approved" ? `${esch(q.credited)} hours credited` : q.status === "Pending" ? "Waiting for staff" : "Not verified"}</b> ${tag(q.status)}
        <span class="muted small">sent ${trDate(q.submitted)}${q.reviewed_at ? ` · reviewed ${trDate(q.reviewed_at)}` : ""}</span></div>
      <div class="muted small">${q.sources.map(s => `${esc(s.name)} (${esch(s.hours)} h claimed${q.status === "Approved" ? s.approved ? `, ${esch(s.verified)} verified` : ", not verified" : ""})`).join(" · ")}</div>
      ${q.note ? `<div class="small">Staff note: ${esc(q.note)}</div>` : ""}</div>`).join("");
  el.innerHTML = `<section class="panel tr-panel" aria-labelledby="trHead">
    <div class="tr-top"><div><span class="kicker">Experience from other airlines</span><h2 id="trHead">Transfer hours</h2>
      <p class="muted" style="margin:4px 0 0;max-width:72ch">Flown at another virtual airline or on VATSIM/IVAO? Send your verified hours and PAC credits <b>half of them, up to ${r.cap} hours</b>, towards rank. That can take you as far as Senior First Officer; Captain is earned at PAC. The checkride, your average score and type ratings still apply, and transfer hours never add pay, points or leaderboard hours.</p></div>
      <div class="tr-now"><span>Credited now</span><b>${esch(d.transfer_hours)} h</b><small>${d.transfer_hours > r.cap ? "set by staff" : `of ${r.cap} max`}</small></div></div>
    ${d.can_request ? `<div class="row" style="align-items:center;gap:12px;margin-top:12px"><button class="btn" type="button" id="trOpen">${d.is_appeal ? "Appeal with new proof" : "Request transfer hours"}</button>
        <span class="muted small">${d.is_appeal ? "This is your one appeal. " : ""}Open until ${trDate(d.closes)}.</span></div>`
      : d.why_not ? `<p class="small muted" style="margin:12px 0 0">${esc(d.why_not)}</p>` : ""}
    ${history ? `<div class="tr-history">${history}</div>` : ""}</section>`;
  const b = $("#trOpen"); if (b) b.onclick = openTransferForm;
}
function openTransferForm() {
  const d = S.transfers, r = d.rules, dlg = $("#transferDlg");
  $("#trTitle").textContent = d.is_appeal ? "Appeal: transfer hours" : "Request transfer hours";
  const row = i => `<fieldset class="tr-src" data-src="${i}"><legend>Source ${i + 1}${i ? ` <button type="button" class="btn ghost small" data-src-del="${i}">Remove</button>` : ""}</legend>
    <div class="tr-grid">
      <label>Type<select name="kind"><option value="va">Virtual airline</option><option value="network">VATSIM or IVAO</option></select></label>
      <label>Name<input name="name" maxlength="80" placeholder="e.g. Delta Virtual Airlines" required></label>
      <label class="wide">Logbook or profile link<input name="url" type="url" maxlength="300" placeholder="https://…" required></label>
      <label>Hours shown<input name="hours" type="number" min="0.1" step="0.1" required></label>
      <label>Screenshot showing your name or pilot ID and the hours<input name="proof" type="file" accept="image/png,image/jpeg,image/webp" required></label>
    </div></fieldset>`;
  let n = 1;
  const paint = () => {
    $("#trBody").innerHTML = `<form id="trForm" class="tr-form">
      <p class="small" style="margin:0">Each source needs a link to your logbook or profile page and a screenshot of it. <b>The screenshot must show your name or pilot ID together with your hours</b>: many VA systems need a login, so staff may not be able to open the link and will go by the screenshot. If staff can't confirm it's you, they may ask for a quick Discord screen share.</p>
      <ul class="small muted" style="margin:0;padding-left:18px">
        <li>Hours at different virtual airlines add up.</li>
        <li>VATSIM/IVAO hours are usually the same flights as your VA hours, so they don't add on top: staff use whichever total is larger.</li>
        <li>PAC credits half of the verified total, up to ${r.cap} hours. ${d.is_appeal ? "This is your appeal, so there's no further request after it." : "You get one request and one appeal."}</li>
      </ul>
      <div id="trSrcs">${Array.from({ length: n }, (_, i) => row(i)).join("")}</div>
      ${n < r.max_sources ? `<button type="button" class="btn ghost small" id="trAdd" style="align-self:flex-start">+ Add another source</button>` : ""}
      <label>Anything staff should know? (optional)<textarea name="comment" maxlength="1000" rows="2" placeholder="e.g. my pilot ID there was DAL1234"></textarea></label>
      <div class="tr-est small" id="trEst"></div>
      <div class="auth-err" id="trErr" role="alert"></div>
      <div class="row"><button class="btn" type="submit">Send to staff</button><button class="btn ghost" type="button" data-tr-cancel>Cancel</button></div></form>`;
    $("#trAdd") && ($("#trAdd").onclick = () => { keep(); n++; paint(); restore(); });
    document.querySelectorAll("[data-src-del]").forEach(b => b.onclick = () => { keep(); saved.splice(+b.dataset.srcDel, 1); n--; paint(); restore(); });
    $("[data-tr-cancel]").onclick = () => dlg.close();
    $("#trForm").oninput = est;
    $("#trForm").onsubmit = send;
    est();
  };
  let saved = [];
  const srcEls = () => [...document.querySelectorAll("#trSrcs [data-src]")];
  const keep = () => { saved = srcEls().map(f => ({ kind: f.querySelector("[name=kind]").value, name: f.querySelector("[name=name]").value, url: f.querySelector("[name=url]").value, hours: f.querySelector("[name=hours]").value, file: f.querySelector("[name=proof]").files[0] || null })); };
  const restore = () => srcEls().forEach((f, i) => { const v = saved[i]; if (!v) return;
    f.querySelector("[name=kind]").value = v.kind; f.querySelector("[name=name]").value = v.name; f.querySelector("[name=url]").value = v.url; f.querySelector("[name=hours]").value = v.hours;
    if (v.file) { const dt = new DataTransfer(); dt.items.add(v.file); f.querySelector("[name=proof]").files = dt.files; } });
  const est = () => {
    let va = 0, net = 0;
    srcEls().forEach(f => { const h = Number(f.querySelector("[name=hours]").value) || 0; f.querySelector("[name=kind]").value === "network" ? net += h : va += h; });
    const base = Math.max(va, net), cr = Math.min(r.cap, Math.round(base * r.share * 10) / 10);
    $("#trEst").innerHTML = base ? `If staff verify everything: <b>${esch(Math.round(base * 10) / 10)} h</b>${va && net ? ` (the larger of ${esch(va)} h VA and ${esch(net)} h network)` : ""} → <b>${esch(cr)} h credited</b>${base * r.share > r.cap ? ` (capped at ${r.cap})` : ""}.` : "";
  };
  const send = async e => {
    e.preventDefault();
    const btn = e.target.querySelector("[type=submit]"), fd = new FormData(), list = [];
    srcEls().forEach((f, i) => {
      list.push({ kind: f.querySelector("[name=kind]").value, name: f.querySelector("[name=name]").value.trim(), url: f.querySelector("[name=url]").value.trim(), hours: f.querySelector("[name=hours]").value });
      const file = f.querySelector("[name=proof]").files[0]; if (file) fd.append(`proof${i}`, file);
    });
    fd.append("sources", JSON.stringify(list));
    fd.append("comment", e.target.comment.value);
    btn.disabled = true; btn.textContent = "Sending…"; $("#trErr").textContent = "";
    try {
      const res = await fetch("/api/transfers", { method: "POST", body: fd });
      const out = await res.json().catch(() => ({ error: `Sending failed (HTTP ${res.status}).` }));
      if (!res.ok) throw new Error(out.error);
      dlg.close(); toast("Sent. Staff will check your logbook and you'll hear back by email."); fillTransfers();
    } catch (err) { $("#trErr").textContent = err.message; btn.disabled = false; btn.textContent = "Send to staff"; }
  };
  paint();
  if (!dlg.open) dlg.showModal();
}

/* ================= Career ================= */
async function loadCareer() {
  try { const [c, , , wallet] = await Promise.all([api("/api/va/career"), refreshCore(), loadMe(), api("/api/pilot/wallet-transactions?page=1")]); S.careerData = c; S.walletData = wallet; renderCareer(c); S.statsData = null; fillCollection(); fillRatings(); fillCargoAwards(); fillTransfers(); } catch (e) {
    $('#careerRoot').innerHTML = '<div class="journey-intro"><div><h1>Career is temporarily unavailable</h1><p role="status">We could not load your career information. Your progress has not changed.</p></div><button class="btn" onclick="loadCareer()">Try again</button></div>';
  }
}
function renderCareer(c) {
  const k = c.career, ranks = S.ranks, featured = c.featured.map(id => S.routes.find(r => r.id === id)).filter(Boolean);
  const pct = (v, t) => Math.max(0, Math.min(100, Math.round((Number(v) || 0) / t * 100)));
  const lbl = { smoothest: ["Smoothest landing", r => `${r.value} fpm`], cargo: ["Most cargo delivered", r => `${fmt(r.value)} lb`],
    hours: ["Most block hours", r => `${esch(r.value)} h`], score: ["Best average score", r => `${r.value}`], points_all_time: ["Points, all time", r => fmt(r.value)] };
  const month = new Date(c.leaderboards.month + "-01T00:00:00Z").toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
  $("#careerRoot").innerHTML = `
  <div class="profile-bar"><h1>Career</h1><div class="row"><span class="muted">${esc(displayName(S.profile))} · ${esc(k.pilot.id)}</span><button class="btn small" onclick="openLicence()">Pilot license</button></div></div>
  <nav class="journey-sections" aria-label="Career sections">${[['overview','Overview'],['qualifications','Qualifications'],['wallet','Pay & wallet'],['activities','Activities'],['awards','Awards & records']].map(([id,label]) => `<button type="button" data-career-section="${id}">${label}</button>`).join('')}<button type="button" onclick="openPilotGuide()">First-flight guide ↗</button></nav>
  <section data-career-pane="overview" aria-label="Career overview">
  <div class="journey-intro"><div><span class="kicker">Your next chapter</span><h2>Choose your aircraft. Find your next flight.</h2><p>Qualifications and aircraft positioning are separate from rank and pay. Start with the aircraft you want to fly.</p></div><div class="row"><button class="btn" onclick="setCareerSection('qualifications')">View qualifications →</button><button class="btn ghost" onclick="show('missions')">Find a flight</button></div></div>
  <article class="rank-card">
    <div class="rank-main">
      ${rankImg(k.rank, "big")}
      <div class="rank-body">
      <div class="muted" style="color:rgba(255,255,255,.7)">Current rank</div>
      <div class="rank">${esc(k.rank)}</div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:4px">
        <div><span style="font-size:12px;opacity:.7;display:block">Hours</span><b style="font-size:20px">${esch(k.hours)}</b>${k.transfer_hours ? `<small style="display:block;opacity:.7;font-size:11px">incl. ${esch(k.transfer_hours)} transfer</small>` : ""}</div>
        <div><span style="font-size:12px;opacity:.7;display:block">Accepted flights</span><b style="font-size:20px">${k.flights}</b></div>
        <div><span style="font-size:12px;opacity:.7;display:block">Avg score (last ${10})</span><b style="font-size:20px">${k.avg_score ?? "–"}</b></div>
      </div>
      <div style="margin-top:8px"><span style="font-size:12px;opacity:.7;display:block;margin-bottom:6px">Aircraft</span>
        <div class="ac-locks">${fleetCodes().map(a => { const open = k.unlocked.includes(a);
          return `<span class="${open ? "open" : "locked"}" style="${open ? "" : "background:transparent;color:rgba(255,255,255,.55);border-color:#444"}">${esc(S.fleet[a].icao)}${open ? "" : ` · ${esc(rankFor(a))}`}</span>`; }).join("")}</div>
      </div>
      </div>
      <div class="patch-ladder">${ranks.map((r, i) => `<figure class="${i < k.rank_index ? "done" : i === k.rank_index ? "now" : ""}">${rankImg(r.name)}<figcaption>${esc(r.name)}</figcaption></figure>`).join("")}</div>
    </div>
    <div class="rank-next">
      ${k.checkride === "Pending" && k.checkride_last && !k.checkride_last.passed ? `<div class="notice err"><b>Your last checkride attempt (${new Date(k.checkride_last.when * 1000).toLocaleDateString("en-US", { day: "numeric", month: "short" })}) didn't pass:</b> ${esc(k.checkride_last.reasons.join(", "))}. Every other part can be fine; these are automatic fails on a checkride.</div>` : ""}
      ${k.checkride === "Pending" ? `<div class="notice"><b>Your rank-progression checkride.</b> ${S.ratings?.direct_entry ? "Or book a type checkride for any aircraft family in Qualifications instead: passing one also counts as this checkride for rank progression (it rates you on that family, not the 737). " : ""}Fly PAC001 from your chosen training airport on the 737-800BCF. Dedicated training and company positioning are free. To pass: score 80 or better, land no firmer than 600 fpm and no higher than 1.8 G, with at most one bounce. An overspeed penalty reduces your score but doesn't automatically fail you; a position jump still does. <button class="btn small" style="margin-top:8px" onclick="flyMission('${S.checkrideId}')">Fly the checkride</button></div>` : ""}
      ${k.appointed ? `<h2 style="margin:0">Appointed ${esc(k.rank)}</h2><p style="margin:0">This rank was set by staff, so it doesn't depend on hours or score.${k.earned_rank !== k.rank ? ` On flying alone you'd be ${esc(k.earned_rank)}.` : ""}</p>
        <p class="muted" style="margin:0;font-size:13px">Every aircraft your rank covers is unlocked. Staff can return you to earned progression in Staff › Roster.</p>`
      : k.next ? `<h2 style="margin:0">Next: ${esc(k.next)}</h2>
        ${k.requirements.map(r => `<div class="req"><span>${esc(r.label)}</span><span class="muted">${r.value != null ? `${r.value} / ${r.target}` : r.done ? "Done" : "Not yet"}</span>
          ${r.target ? `<div class="bar ${r.done ? "ok" : ""}"><i style="width:${r.done ? 100 : pct(r.value, r.target)}%"></i></div>` : ""}</div>`).join("")}
        <p class="muted" style="margin:0;font-size:13px">Unlocks ${ranks.find(r => r.name === k.next)?.unlocks.map(a => esc(S.fleet[a].name)).join(", ") || "nothing new"}.
        ${c.enforce_ranks ? "Rank limits are enforced: you can only book unlocked aircraft." : "Rank limits are not enforced right now, so every aircraft stays bookable. Staff can switch this on."}</p>`
        : `<h2 style="margin:0">Top of the ladder</h2><p style="margin:0">You've reached Senior Captain. Every aircraft in the fleet is yours.</p>`}
    </div>
  </article>
  <div id="transferPanel"></div>
  </section>
  <section data-career-pane="wallet" aria-label="Pay and wallet" hidden><div id="careerWallet">${walletPanel(S.me, S.walletData)}</div></section>
  <section data-career-pane="activities" aria-label="Events tours and rotations" hidden>
  <div class="section-h"><div><h2>Events</h2><p>Bonus points on matching flights while an event is running.</p></div></div>
  <div class="two-col">${c.events.filter(e => e.state !== "past").map(e => `<div class="event-card" style="${e.state === "active" ? "" : "border-left-color:var(--line)"}">
    <h3>${esc(e.name)} <span class="tag ${e.state === "active" ? "" : "grey"}">${e.state === "active" ? "On now" : "Upcoming"}</span> <span class="tag dark">×${e.multiplier}</span></h3>
    <div class="when">${fmtDate(e.start)} – ${fmtDate(e.end)}${e.categories.length ? " · " + e.categories.join(", ") : ""}${e.regions.length ? " · " + e.regions.join(", ") : ""}${e.airports.length ? " · " + e.airports.join(", ") : ""}</div>
    <p style="margin:8px 0 0">${esc(e.description)}</p></div>`).join("") || `<p class="muted">No events scheduled. Staff can add them.</p>`}</div>

  <div class="section-h"><div><h2>Featured routes this month</h2><p>×1.25 points on each. A new set every month, one per region.</p></div></div>
  <div class="manifest">${featured.map(waybillHtml).join("")}</div>

  <div class="section-h"><div><h2>Tours</h2><p>Fly the legs in order to finish the tour, earn the bonus and the badge.</p><p>Your tour progress stays with you. Aircraft belong to the shared PAC fleet: choose any available aircraft permitted for your next leg. A booking reserves it for that flight only; after filing, it stays at the arrival airport and becomes available unless maintenance is required. Normal pilot travel and aircraft ferry pricing applies.</p></div></div>
  <div class="tour-grid">${c.tours.map(t => { const pr = c.tour_progress[t.id];
    return `<div class="tour"><div class="row" style="justify-content:space-between"><h3>${esc(t.name)}</h3><span class="tag dark">+${fmt(t.bonus)} pts</span></div>
      <p class="muted" style="margin:0;font-size:14px">${esc(t.description)}</p>
      <div class="legs">${t.legs.map((ic, i) => `${i ? `<em></em>` : ""}<span class="${i <= pr.completed && pr.completed ? "done" : i === pr.completed ? "next" : ""}">${ic}</span>`).join("")}</div>
      <div class="row" style="justify-content:space-between"><span class="muted" style="font-size:13px">${pr.completed} of ${pr.total} legs · ${t.aircraft.map(a => esc(S.fleet[a].icao)).join(" or ")}</span>
      ${pr.next ? `<button class="btn small" onclick="flyMission('${pr.next}')">${pr.completed ? "Fly next leg" : "Start the tour"}</button>` : `<span class="tag green">Complete</span>`}</div></div>`; }).join("")}</div>

  ${(c.rotations || []).length ? `<div class="section-h"><div><h2>Rotations</h2><p>Multi-leg freighter patterns, flown in order and back to the start. Every full lap pays the bonus, as often as you like.</p></div></div>
  <div class="tour-grid">${c.rotations.filter(r => r.aircraft?.length).map(r => { const pr = (c.rotation_progress || {})[r.id] || { completed: 0, total: r.legs.length - 1, laps: 0, next: null };
    return `<div class="tour"><div class="row" style="justify-content:space-between"><h3>${esc(r.name)}</h3><span class="tag dark">+${fmt(r.bonus)} pts a lap</span></div>
      <p class="muted" style="margin:0;font-size:14px">${esc(r.description)}</p>
      <div class="legs">${r.legs.map((ic, i) => `${i ? `<em></em>` : ""}<span class="${i <= pr.completed && pr.completed ? "done" : i === pr.completed ? "next" : ""}">${ic}</span>`).join("")}</div>
      <div class="row" style="justify-content:space-between"><span class="muted" style="font-size:13px">${pr.completed} of ${pr.total} legs${pr.laps ? ` · ${pr.laps} ${pr.laps === 1 ? "lap" : "laps"} flown` : ""} · ${fmt(r.total_nm || 0)} nm · ${r.aircraft.map(a => esc(S.fleet[a]?.icao || a)).join(", ")}</span>
      ${pr.next ? `<button class="btn small" onclick="flyMission('${pr.next}')">${pr.completed ? "Fly next leg" : pr.laps ? "Fly it again" : "Start the rotation"}</button>` : ""}</div></div>`; }).join("")}</div>` : ""}

  </section>
  <section data-career-pane="qualifications" aria-label="Qualifications" hidden>
  <div class="journey-intro"><div><span class="kicker">Training travel is on PAC</span><h2>Your aircraft qualifications</h2><p>Choose Start checkride below. Dedicated training leaves your normal station and operational fleet untouched. Or choose an available fleet aircraft with free company travel included when booked. No paid aircraft delivery is needed.</p><p>Already generated a SimBrief plan? Generate a new one if your checkride route changes.</p></div><button class="btn ghost" onclick="openPilotGuide('checkride')">How checkrides work</button></div>
  <div class="section-h"><div><h2>Type ratings</h2><p id="ratingsText">Loading…</p></div></div>
  <div class="rating-grid" id="ratingsGrid"></div></section>
  <section data-career-pane="awards" aria-label="Awards and records" hidden>
  ${collectionPanel()}
  <section id="cargoCareerAwards"></section>
  <div class="section-h"><div><h2>Awards</h2><p>${c.badges.filter(b => b.earned).length} of ${c.badges.length} earned.</p></div></div>
  <div class="badge-grid">${c.badges.map(b => `<div class="medal ${b.earned ? "earned" : ""}"><div class="m">${b.earned ? "PAC" : Math.min(99, Math.round(b.value / b.target * 100)) + "%"}</div>
    <div><b>${esc(b.name)}</b><small>${esc(b.description)}</small>${!b.earned && b.target > 1 ? `<small>${esc(String(b.value))} / ${b.target}</small>` : ""}</div></div>`).join("")}</div>

  <div class="section-h"><div><h2>Leaderboards</h2><p>${month}, accepted flights only.</p></div></div>
  <div class="lb-grid">${Object.entries(lbl).map(([key, [title, f]]) => `<div class="lb"><h3>${title}</h3>${c.leaderboards[key].length
    ? `<ol>${c.leaderboards[key].map((r, i) => `<li><b class="n">${i + 1}</b><span>${esc(r.name || r.pilot_id)}${r.flight_number ? `<br><small class="muted">${esc(r.flight_number)} · ${esc(r.arr)}</small>` : ""}</span><b>${f(r)}</b></li>`).join("")}</ol>`
    : `<p class="empty muted">No flights yet${key === "score" ? " (needs 3 flights)" : ""}.</p>`}</div>`).join("")}</div></section>`;
  $('#careerRoot').querySelectorAll('[data-career-section]').forEach(b => b.onclick = () => setCareerSection(b.dataset.careerSection));
  setCareerSection(S.careerSection || 'overview', false);
  document.querySelectorAll("#careerRoot .waybill").forEach(b => b.onclick = () => flyMission(b.dataset.id));
}

/* ================= Footer, privacy policy and consent notice ================= */
const contactEmail = () => S.home?.site?.contact_email || "ops@pac-va.com";
function siteFooter(site) {
  const mail = esc(site?.contact_email || contactEmail()), discord = site?.discord_invite;
  const year = new Date().getFullYear();
  return `<footer class="site-foot" aria-label="About this website">
    <div class="sf-grid">
      <div class="sf-brand"><img src="/static/pac-wordmark-white.png" alt="Pagani Air Cargo" width="120">
        <p>Pagani Air Cargo is a virtual airline for flight simulation. It is a free, non-commercial hobby community: it is not a real airline, carries no real cargo, and is not affiliated with any real-world airline or aviation company.</p></div>
      <div class="sf-links" role="navigation" aria-label="Pilots"><h3>Pilots</h3><a href="#apply" onclick="show('home');setTimeout(()=>$('#apply')?.scrollIntoView({behavior:'smooth'}),100);return false">Apply to fly</a><a href="#handbook" onclick="show('handbook');return false">Pilot handbook</a><a href="#fleet" onclick="show('fleet');return false">The fleet</a><a href="#gallery" onclick="show('gallery');return false">Gallery</a><a href="#roster" onclick="show('roster');return false">Roster &amp; flight log</a>${S.me ? `<a href="#downloads" onclick="show('downloads');return false">Downloads</a>` : ""}</div>
      <div class="sf-links" role="navigation" aria-label="Contact"><h3>Contact</h3><a href="mailto:${mail}">${mail}</a>${discord ? `<a href="${esc(discord)}" target="_blank" rel="noopener">PAC on Discord</a>` : ""}<a href="#privacy" onclick="show('privacy');return false">Privacy policy</a><a href="#piracy" onclick="show('piracy');return false">Anti-piracy policy</a></div>
      <div class="sf-small"><h3>Credits</h3><p>Weather: NOAA Aviation Weather Center. Maps: &copy; OpenStreetMap contributors and Esri. Radar: RainViewer. Flight planning: SimBrief by Navigraph. Partner aircraft photos: Wikimedia Commons, credited on each card.</p></div>
    </div>
    ${site?.interline_badge ? `<div style="margin:20px 0 0"><a href="https://interline.pac-va.com" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:11px;text-decoration:none;padding:10px 15px;border:1px solid #2c3037;border-radius:9px;background:#0E2A47">
      <svg width="40" height="22" viewBox="0 0 92 48" aria-hidden="true"><path d="M 40.69 40.71 A 18 18 0 1 1 49.86 32.51" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round"/><path d="M 51.31 7.29 A 18 18 0 1 1 42.14 15.49" fill="none" stroke="#D8AD53" stroke-width="7" stroke-linecap="round"/></svg>
      <span style="line-height:1.25"><span style="display:block;font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:#9fb0cf;font-weight:700">Founding Member of</span><span style="display:block;font-size:13px;font-weight:700;color:#fff;letter-spacing:.03em">INTERLINE FREIGHT PARTNERS</span></span></a></div>` : ""}
    <p class="sf-legal">Airline, team, series and brand names, logos and aircraft types belong to their owners; partnerships and sponsorships are simulated and referenced for realism only, implying no affiliation or endorsement. For flight simulation only: not for real-world navigation or flight planning.</p>
    <p class="sf-legal">&copy; ${year} Pagani Air Cargo · pac-va.com</p>
  </footer>`;
}
/* the public pilot roster and flight log: anyone can see it (VATSIM and IVAO look for it), first name and initial only */
async function loadRoster() {
  const root = $("#rosterRoot");
  root.innerHTML = `<p class="muted">Loading the roster…</p>`;
  let d; try { d = await api("/api/public/roster"); } catch (e) { root.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const date = t => t ? new Date(t * 1000).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" }) : "–";
  root.innerHTML = `<div class="profile-bar"><h1>Roster &amp; flight log</h1><span class="muted">Every active PAC pilot and the airline's latest accepted flights</span></div>
    <div class="ro-sum"><div><span>Active pilots</span><b>${fmt(d.totals.pilots)}</b></div><div><span>Flights flown</span><b>${fmt(d.totals.flights)}</b></div>
      <div><span>Block hours</span><b>${fmt(Math.round(d.totals.hours))}</b></div><div><span>Network callsign</span><b>${esc(d.callsign)} · PAGANI</b></div></div>
    <section class="ro-sec"><h2>Pilot roster</h2>
      <div class="ro-wrap"><table class="ro-table"><thead><tr><th>Pilot ID</th><th>Pilot</th><th>Rank</th><th>Hub</th><th class="num">Hours</th><th class="num">Flights</th><th>Joined</th></tr></thead>
      <tbody>${d.pilots.map(p => `<tr><td><b>${esc(p.id)}</b></td><td>${esc(p.name)}${p.staff ? ' <span class="tag grey">Staff</span>' : ""}</td><td>${esc(p.rank)}</td><td>${esc(p.hub || "–")}</td><td class="num">${(p.hours || 0).toFixed(1)}</td><td class="num">${fmt(p.flights)}</td><td>${date(p.joined)}</td></tr>`).join("") || `<tr><td colspan="7" class="muted">No pilots yet.</td></tr>`}</tbody></table></div></section>
    <section class="ro-sec"><h2>Flight log</h2><p class="muted" style="margin:0 0 8px">The latest ${d.flights.length} accepted flights. On VATSIM and IVAO, PAC flights file as ${esc(d.callsign)} with the same number (PAC9613 files as ${esc(d.callsign)}9613), spoken “Pagani”.</p>
      <div class="ro-wrap"><table class="ro-table"><thead><tr><th>Date</th><th>Flight</th><th>Pilot</th><th>From</th><th>To</th><th>Aircraft</th><th class="num">Block</th><th>Status</th></tr></thead>
      <tbody>${d.flights.map(f => `<tr><td>${new Date(f.filed_at * 1000).toISOString().slice(0, 10)}</td><td><b>${esc(f.flight_number)}</b></td><td>${f.pilot_id ? `${esc(f.pilot_id)} · ` : ""}${esc(f.pilot)}</td><td>${esc(f.dep)}</td><td>${esc(f.arr)}</td><td title="${esc(f.aircraft_name)}">${esc(S.fleet?.[f.aircraft]?.icao || f.aircraft)}</td><td class="num">${hm(f.block_min)}</td><td>${esc(f.status)}</td></tr>`).join("") || `<tr><td colspan="8" class="muted">No flights yet.</td></tr>`}</tbody></table></div></section>`;
}
/* Anti-piracy policy (VATSIM's virtual airline policy section 8.11 asks every VA to have and enforce one) */
function renderPiracy() {
  const mail = esc(contactEmail());
  const sec = (t, b) => `<section><h2>${t}</h2>${b}</section>`;
  $("#piracyRoot").innerHTML = `<div class="profile-bar"><h1>Anti-piracy policy</h1><span class="muted">Last updated November 10, 2026</span></div>
  <div class="privacy">
    <p class="lead">Pagani Air Cargo flies only with legally obtained software. Pirated simulators, aircraft, scenery and add-ons hurt the developers who make flight simulation possible, and they have no place at PAC.</p>
    ${sec("What's not allowed", `<ul>
      <li>Using, sharing, requesting or linking to pirated or cracked software: simulators, aircraft, scenery, utilities or any other add-on.</li>
      <li>Sharing license keys, account logins or files you don't have the right to share, in PAC's Discord, website, forums or direct messages.</li>
      <li>Asking other members for help with software that was obtained illegally.</li></ul>`)}
    ${sec("What PAC does about it", `<ul>
      <li>Posts that break this policy are removed.</li>
      <li>A first offense gets a written warning. A second offense, or any distribution of pirated software, means removal from PAC, and PAC won't accept a new application.</li>
      <li>PAC can't see what software is installed on your computer, so this policy works on trust and reports. If PAC learns that a flight was flown with pirated software (a screenshot, a post, a report), that flight isn't accepted.</li>
      <li>If a developer or rights holder tells PAC about an infringement, PAC acts on it promptly and, where a network partnership requires it, reports it to that network in writing.</li></ul>`)}
    ${sec("Freeware and paid add-ons", `<p>Freeware is welcome, downloaded from its author or an official library. Paid add-ons must come from the developer or an authorized store. Liveries made by PAC for an aircraft are only for owners of that aircraft.</p>`)}
    ${sec("Reporting", `<p>If you see piracy in PAC's community, email <a href="mailto:${mail}">${mail}</a> or message a staff member on Discord. Reports are handled privately.</p>`)}
  </div>`;
}

function renderPrivacy() {
  const mail = esc(contactEmail());
  const sec = (t, b) => `<section><h2>${t}</h2>${b}</section>`;
  $("#privacyRoot").innerHTML = `<div class="profile-bar"><h1>Privacy policy</h1><span class="muted">Last updated November 23, 2026</span></div>
  <div class="privacy">
    <p class="lead">Pagani Air Cargo (PAC) is a free, non-commercial virtual airline for flight simulator pilots, run by Joseph Pagani. This page explains what information the PAC website and the PAC ACARS app collect, why, who else sees it, and the choices you have. Questions or requests: <a href="mailto:${mail}">${mail}</a>.</p>
    ${sec("What we collect", `<ul>
      <li><b>Your application:</b> name, email address, country, Discord username (optional), simulator, experience, preferred hub and your note to us.</li>
      <li><b>Your PAC account:</b> pilot ID, name, rank, home base, current location in PAC's network, and anything you add to your profile, such as a photo or bio. Your password is stored only as a salted hash: nobody, staff included, can read it.</li>
      <li><b>Your flights:</b> while PAC ACARS tracks a flight it records what your simulator reports (position, altitude, speeds, phase of flight, fuel, weights and landing data), plus your flight plan, dispatch paperwork, messages to PAC dispatch, and the resulting report, score and logbook entry.</li>
      <li><b>Optional details you choose to add:</b> your VATSIM CID or IVAO VID, SimBrief username, SayIntentions.AI key, problem reports with screenshots, and gallery uploads.</li>
      <li><b>Technical records:</b> our web server keeps short logs of requests (IP address, browser and the page asked for) to keep the site secure and running. They're overwritten automatically.</li>
      <li><b>Anonymous page counts:</b> to see which parts of the site are used and how fast it loads, the site counts each page you open, whether you were signed in, the kind of screen (phone, tablet or computer), how long the first page took to load, and any error in the site's own script. These are kept only as daily totals, with no cookie, no IP address and no pilot ID. To count different visitors in a day without knowing who they are, PAC mixes your address and browser with a random key that changes daily and is deleted, with these fingerprints, the next day.</li></ul>`)}
    ${sec("Cookies and storage on your device", `<p>PAC uses <b>one essential cookie</b> to keep you signed in (for up to 30 days if you tick <i>Keep me signed in</i>). The site also saves a few preferences in your browser, such as your theme, design and filters. PAC has <b>no advertising, analytics or tracking cookies</b>, and doesn't follow you around other websites. The anonymous page counts above use no cookie and store nothing on your device.</p>`)}
    ${sec("Why we use it", `<ul><li>To review applications and run your membership: your account, checkrides, ratings, ranks and in-sim pay.</li>
      <li>To track, score and review your flights, and show them in your logbook and stats.</li>
      <li>To run the community: the pilot roster, leaderboards, the live map, news and Discord.</li>
      <li>To contact you about PAC, for example your welcome letter or a sign-in link.</li>
      <li>To keep the site secure and fix problems.</li></ul>
      <p>If you're in the EU or UK: we rely on our legitimate interest in running the virtual airline you joined, and on your consent for the optional details above, which you can remove at any time.</p>`)}
    ${sec("What other pilots and visitors can see", `<p>Your name, pilot ID, rank and flights appear to other PAC members on the roster, boards, leaderboards and live map. The home page shows recent flights, and staff may make the live map public. Departures, arrivals and landing cards may be posted in PAC's Discord. Your email address, password and private settings are never shown.</p>`)}
    ${sec("Services that help run PAC", `<p>We don't sell or rent your information. These services handle some of it on PAC's behalf, or when you use them:</p><ul>
      <li><b>DigitalOcean</b> hosts the PAC server and its backups.</li>
      <li><b>Cloudflare</b> runs PAC's domain and forwards mail sent to ${mail}.</li>
      <li><b>Resend</b> delivers the emails PAC sends.</li>
      <li><b>Discord</b>, if you join PAC's server.</li>
      <li><b>SimBrief (Navigraph)</b>, when you plan a flight with your SimBrief account.</li>
      <li><b>VATSIM and IVAO</b>: if you add your ID, PAC reads their public network data to see whether you flew online.</li>
      <li><b>SayIntentions.AI</b>, only if you link your account.</li>
      <li><b>Map, weather and radar providers</b> (OpenStreetMap, Esri, RainViewer, NOAA): your browser loads map pictures and weather from them when you view a map.</li></ul>`)}
    ${sec("How long we keep it", `<p>Your account and flights are kept while you're a PAC pilot. If you leave, ask us and we'll remove your account. Your flights can either stay in PAC's history under "former pilot" or be erased completely, as you prefer. Staff clear out applications that weren't accepted after review, and you can ask us to delete yours at any time. Server backups roll over within a few weeks.</p>`)}
    ${sec("Your choices and rights", `<p>You can see and change most of your details yourself in Settings and your profile. You can also ask us, at <a href="mailto:${mail}">${mail}</a>, for a copy of your information, a correction, or deletion. We'll reply within 30 days. If you're in the EU or UK and unhappy with our answer, you can complain to your data protection authority.</p>`)}
    ${sec("Security", `<p>The site is served over HTTPS only, passwords are hashed, staff tools need a staff account, and the server is backed up. No system is perfectly secure, so please use a password you don't use elsewhere.</p>`)}
    ${sec("Children", `<p>PAC is for pilots aged 13 and over. If you're under 16 and in the EU or UK, please ask a parent or guardian before applying.</p>`)}
    ${sec("Changes", `<p>If this policy changes, we'll update the date at the top and post a note in PAC's news for anything significant.</p>`)}
  </div>`;
}
function consentNotice() {
  try { if (localStorage.getItem("pac-consent") === "1") return; } catch (e) { /* storage blocked: show it each visit */ }
  if (document.getElementById("consentBar")) return;
  const bar = document.createElement("div");
  bar.id = "consentBar"; bar.className = "consent-bar"; bar.setAttribute("role", "region"); bar.setAttribute("aria-label", "Privacy notice");
  bar.innerHTML = `<p><b>Your privacy.</b> PAC uses one essential cookie to keep you signed in and saves your preferences on this device. No advertising or tracking: page visits are only counted anonymously. By continuing, you agree to this and to how we handle your information in our <a href="#privacy" onclick="show('privacy');return false">privacy policy</a>.</p>
    <div class="row"><button type="button" class="btn small" id="consentOk">OK</button><button type="button" class="btn ghost small" onclick="show('privacy')">Read the policy</button></div>`;
  document.body.append(bar);
  $("#consentOk").onclick = () => { try { localStorage.setItem("pac-consent", "1"); } catch (e) { /* private window */ } bar.remove(); };
}

/* ================= Handbook ================= */
async function loadHandbook() {
  try { S.vaConfig = S.vaConfig || await api("/api/va/config"); renderHandbook(S.vaConfig); } catch (e) { toast(e.message); }
}
function renderHandbook(cfg) {
  const ck = cfg.checkride, rv = cfg.review, tc = cfg.type_checkride || { min_score: 80, min_rate: -600, max_g: 1.8, max_approach_speed_spread: 35, max_sustained_descent_fpm: 1300, min_nm: 250, max_nm: 1000 };
  const sections = [
    ["training-policy", "Company-funded checkrides", trainingPolicyHTML()],
    ["first-flight", "Your first flight", `<p>Start with your qualification or a cargo mission. The guide explains each step and the difference between pilot travel and aircraft delivery.</p><button class="btn" onclick="openPilotGuide()">Open first-flight guide</button>`],
    ["travel", "Travel and aircraft delivery", travelGuideHTML()],
    ["welcome", "Welcome", `<p>${esc(S.home?.site?.intro || "Pagani Air Cargo is a virtual cargo airline for flight simulator pilots.")}</p>
      <p>This handbook is the rulebook for every PAC flight. It's short on purpose. Read it once before your checkride and come back when something changes.</p>`],
    ["joining", "Joining and the checkride", `<p>Apply from the home page. Staff review every application and assign you a pilot ID. Your first flight is the line checkride:</p>
      <table><tr><th>Flight</th><td>PAC001, from your chosen training airport</td></tr><tr><th>Aircraft</th><td>Boeing 737-800BCF / BDSF</td></tr>
      <tr><th>To pass</th><td>Arrive at the booked destination, score ${ck.min_score} or better, land no firmer than ${Math.abs(ck.min_rate)} fpm at no more than ${ck.max_g} G, and have no more than one bounce. Overspeed penalties reduce score but aren't automatic failures; position jumps still fail.</td></tr></table>
      <p>ACARS grades the checkride automatically when you file the PIREP. If it doesn't pass, fly it again. There's no limit on attempts, and checkrides cost you nothing (see Company-funded checkrides).</p>
      ${cfg.direct_entry ? `<p><b>Already fly a bigger type?</b> You can start with that family's type checkride instead (Career › Qualifications). An accepted pass counts as your line checkride and rates you on that family; it doesn't give you the 737.</p>` : ""}`],
    ["ranks", "Ranks and aircraft", `<p>Rank depends on your hours (PAC hours plus any transfer hours staff have credited, see Transfer hours below), and on your average score over your last ${cfg.avg_window} accepted flights once you have at least ${cfg.avg_min_flights}.</p>
      ${cfg.type_ratings_required ? `<p>A rank makes aircraft <b>available</b> to you. Each aircraft family also needs its type rating before you fly it: passing the line checkride (PAC001) in the 737 gives you the whole 737 family (737-200C, 737-300SF and 737-800BCF); for anything else, fly that family's short type checkride from Career › Qualifications.</p>` : `<p>Reaching a rank unlocks its aircraft straight away: you can fly them as soon as you hold the rank.</p>`}
      <table><tr><th></th><th>Rank</th><th>Hours</th><th>Average score</th><th>${cfg.type_ratings_required ? "Makes available" : "Unlocks"}</th></tr>${cfg.ranks.map(r => `<tr><td style="width:52px">${rankImg(r.name)}</td><td><b>${esc(r.name)}</b></td><td>${r.name === "Cadet" ? "–" : r.hours}</td><td>${r.avg || "–"}</td><td>${r.checkride && r.hours === 0 ? "Checkride passed. " : ""}${r.unlocks.map(a => esc(S.fleet[a]?.name || a)).join(", ") || "Checkride only"}</td></tr>`).join("")}</table>`],
    ...(S.zones?.enabled ? [["zones", "Conflict zones", `<p>PAC is a US cargo carrier, so it follows the same airspace rules a US carrier would. Some areas are <b>restricted</b> and some are <b>caution areas</b>. Flights there stay on the board and you can still fly them, but the consequences follow the real-world rules.</p>
      <table><tr><th>Restricted</th><td>Not authorized. A flight that departs from, lands in or is planned to a restricted country is <b>rejected automatically</b>: no pay, points or hours. If your track crosses restricted airspace, the PIREP goes to staff review and is only credited if staff accept it. Plan your route around these areas.</td></tr>
      <tr><th>Caution</th><td>Allowed, with <b>hazard pay</b> on top of your flight pay for flights to, from or across the area.</td></tr>
      <tr><th>Before you book</th><td>Flights are tagged on the board, and you confirm you understand before requesting one.</td></tr></table>
      <table><tr><th>Area</th><th>Status</th><th>Hazard pay</th></tr>${S.zones.zones.map(z => `<tr><td><b>${esc(z.name)}</b><br><small class="muted">${esc(z.note || "")}</small></td><td>${z.level === "restricted" ? "Restricted" : "Caution"}</td><td>${z.level === "caution" ? `+${z.pct}%` : "–"}</td></tr>`).join("")}</table>
      <p class="muted" style="font-size:13px">Based on the FAA's rules for US operators. Staff update the list when the real world changes.</p>`]] : []),
    ["activity", "Staying active", `<p>PAC pilots fly at least once every <b>${S.settings?.activity_days || 45} days</b>. Your home page shows the date your next flight is due. It counts from your last flight, the day you joined, or the end of your last leave, whichever is latest. Any accepted flight counts.</p>
      <p><b>Reminder:</b> if your Discord account is linked, PAC Operations sends you a direct message about a week before the date. A leave of absence pauses the clock.</p>
      <p>Past your date with no leave? Fly any flight to get back on track.</p>`],
    ["leave", "Leave of absence", `<p>Life happens: vacations, moves, busy weeks at work, a new simulator to set up. Take a leave of absence from your home page (<b>Away for a while?</b>): choose how long, up to ${S.settings?.leave_max_days || 60} days at a time and 120 days a year, and add a reason if you like (only staff see it).</p>
      <p>While you're away, the roster shows you as <b>On leave</b>. Your leave ends on its own on the date you chose, or earlier when you press <b>I'm back</b> or file a flight.</p>`],
    ["cargofolder", "Cargo folder and debrief", `<p><b>Cargo folder:</b> on the load sheet step, and in the printed release, every shipment on your flight comes with its full paperwork. <b>Air waybill</b>: the contract of carriage, with shipper, consignee and forwarder, pieces, gross and chargeable weight, dimensions, rates and charges, the harmonized (customs) code, packaging, special handling codes and temperature. <b>Special handling</b>: what each code means and how to treat the cargo. <b>Warehouse screening</b>: the checks the origin warehouse made before the cargo reached your aircraft (count, weight, packaging, security screening method, invoice and export customs). <b>Tracking</b>: the shipment's status codes, as real cargo systems show them (BKD booked, RCS received, MAN manifested, DEP departed, ARR arrived, DLV delivered).</p>
      <p>Chargeable weight is the greater of the real weight and the volumetric weight (the volume in cubic centimeters divided by 6,000): light, bulky cargo is charged for the space it takes. Shippers, consignees, forwarders and ground handlers are real companies that do this kind of business at both ends of the route. The shipments themselves, their values and reference numbers are fictional, made for flight simulation, and no business relationship with PAC is implied.</p>
      <p><b>After-action review:</b> every filed flight's debrief has a planned-versus-actual table (block time, trip fuel, payload, landing weight against the limit, fuel at touchdown against the final reserve), what the customer said about the delivery, the dispatcher's summary with takeaways for your next flight, and the delivery result of each air waybill. It explains your grade; it doesn't change it.</p>`],
    ["transfers", "Transfer hours", `<p>Hours you flew at another virtual airline or on VATSIM/IVAO can count towards your PAC rank. Send a request from <b>Career</b> within 60 days of joining (pilots who joined before the program opened have until January 4, 2027).</p>
      <table><tr><th>What counts</th><td>Hours in your logbook at another virtual airline, or your VATSIM/IVAO pilot hours. Up to 3 sources, each with the link to the logbook or profile page and a screenshot that shows <b>your name or pilot ID together with the hours</b>. Many VA systems need a login, so staff may go by the screenshot, and may ask for a quick Discord screen share if they can't confirm it's you.</td></tr>
      <tr><th>What doesn't</th><td>Personal or offline logbooks, single-player career modes (such as MSFS career), and hours that can't be traced to you.</td></tr>
      <tr><th>Adding up</th><td>Hours at different virtual airlines add up. VATSIM/IVAO hours are usually the same flights, so they don't add on top of VA hours: the larger total is used.</td></tr>
      <tr><th>Credit</th><td><b>Half</b> of the verified hours, up to <b>75 hours</b>. That can take you as far as Senior First Officer; Captain and Senior Captain are earned at PAC.</td></tr>
      <tr><th>Still required</th><td>The line checkride (or a type checkride), your average score (3 PAC flights before it counts) and type ratings.</td></tr>
      <tr><th>Never</th><td>Pay, points, wallet money, leaderboard hours or PAC totals.</td></tr>
      <tr><th>Requests</th><td>One request and one appeal. Staff check every link, and you hear back by email and on Career.</td></tr></table>`],
    ["divisions", "Fleet divisions", `<p>PAC's fleet is organized in four divisions. They're labels, not separate rules: your rank and ratings decide what you fly, and you can fly in any division you qualify for.</p>
      <table><tr><th>Division</th><th>Aircraft</th><th>What it flies</th></tr>${divisions().map(d => `<tr><td><b>${esc(d.name)}</b></td><td>${Object.keys(S.fleet || {}).filter(k => divOf(k) === d.name && !S.fleet[k].retired).map(k => esc(S.fleet[k].name)).join(", ") || "–"}</td><td>${esc(d.blurb || "")}</td></tr>`).join("")}</table>
      <p>Most pilots start in <b>PAC Feeder</b> on the 737s. The division shows on the Fleet page, on every flight, in your logbook and in My stats, and the mission board can show one division at a time.</p>`],
    ["planning", "Planning a flight", `<p><b>Pick a flight</b> from Missions (special operations), the Scheduled network, Events &amp; tours, Partners, or build a Charter. The flight page then walks you through four tabs:</p>
      <ul><li><b>Briefing:</b> the cargo, any special handling, live weather at both ends and what the flight earns the company.</li>
      <li><b>Aircraft:</b> pick a type your rank and ratings allow, then an airframe <b>at your departure airport</b>. Every aircraft is tracked by registration and stays where it last landed. If none of the right type is there, jumpseat to one, have one delivered, or fly a ferry (see Travel and aircraft delivery).</li>
      <li><b>Load sheet:</b> a preliminary load sheet built before you plan: the cargo units and their positions, the weights against the aircraft's limits, and PAC's fuel estimate. It carries over to the dispatch release.</li>
      <li><b>SimBrief &amp; request:</b> PAC's plan suggestions, an optional <b>Extra fuel</b> box (carrying extra is never penalized), and <b>Generate OFP</b>. A small SimBrief window builds the plan with the aircraft, route, callsign and cargo already filled in, closes by itself, and the OFP comes straight in. You can also open SimBrief yourself, click Generate Flight, then press <b>Fetch latest OFP</b>. The OFP must match the departure and destination.</li></ul>
      <p><b>Request the flight.</b> The airframe is reserved for you until you file the PIREP or cancel. If you request without a plan, PAC keeps watching SimBrief for up to 90 minutes and attaches the OFP when you generate it, with the paperwork updated.</p>`],
    ["flying", "Flying with ACARS", `<ul><li>Sign the dispatch release first (see Dispatch paperwork). Load at a stand at the departure airport with the parking brake set. On the website's ACARS page press <b>Open in PAC ACARS</b>, then <b>Start tracking</b> in the app. ACARS won't start more than 5 nm from the airport or in the air.</li>
      <li>Every phase is detected automatically, from pushback to on-block. OUT, OFF, ON and IN times are logged like the real system.</li>
      <li>Keep 250 kt or less below 10,000 ft and 30 kt or less while taxiing.</li>
      <li>GSX or slew moves on the ground (stand to runway, runway to stand) are allowed and logged as ground repositions${S.settings.allow_ground_reposition === false ? ", but are currently scored as position jumps" : ""}. Moves in the air are always penalized.</li>
      <li>To finish, park at the stand, set the parking brake and shut down all engines, with PAC ACARS still open. If PAC ACARS can't read your aircraft's parking brake (some add-ons), being stopped with all engines off for 60 seconds also puts you on block. If your sim or PC crashes, restart PAC ACARS and press Resume flight.</li>
      <li>Fly in real time. ACARS detects sim-rate acceleration and pauses (see Flight integrity).</li></ul>`],
    ["integrity", "Flight integrity", `<ul><li><b>Sim rate:</b> while you're parked at the stand (loading, boarding, unloading) you can speed the sim up as much as you like. Once you're moving, or in the air, more than 10 seconds above 1× sends the flight to staff review.</li>
      <li><b>Pauses:</b> short pauses are fine. More than 10 minutes paused in the air sends the flight to review.</li>
      <li><b>Tail clearance:</b> ACARS compares recorded ground pitch with the type's approximate clearance reference. Crossing it sends the PIREP to staff for review; pitch alone does not prove contact or automatically ground the aircraft.</li>
      <li><b>Takeoff analysis:</b> every PIREP shows rotation speed, liftoff speed and pitch, ground roll, runway remaining and initial climb, with a downloadable takeoff card.</li></ul>`],
    ["urgent", "Urgent requests", `<p>Every 40 minutes or so a new urgent request appears (AOG engines, blood products, line-stop parts, ship and data-center spares, antivenom, rescue teams, grid repairs and more), up to six at a time. Each uses an aircraft that's already in position.</p>
      <ul><li>Book it before the offer expires.</li><li>Block in before the delivery deadline for ×1.5 points and full revenue. Miss it and the customer takes half the revenue back.</li></ul>`],
    ["staffletters", "For staff: approving pilots and letters", `<p>Applications arrive under Staff › Applications. Approving one gives the pilot the next free ID (PAC0002, PAC0003 and so on), creates their record, and opens the <b>welcome letter</b>, ready to send.</p>
      <ul><li><b>The welcome letter</b> carries the pilot ID, home base, a one-time sign-in link (good for 7 days), the first steps and the Discord invite. Copy it, open it in your mail program, or download it as HTML.</li>
      <li><b>Declining</b> opens a courteous decline letter, with your note as the reason if you wrote one.</li>
      <li><b>Staff › Roster › Letter</b> sends a pilot a fresh sign-in link if theirs lapsed.</li>
      <li><b>PAC can send the letters itself.</b> Under <b>Staff › Site and rules › Email</b>, give PAC the airline's own mailbox (Gmail and Outlook need an app password, not your normal password; PAC fills in the server settings for common providers). With <b>Send the welcome letter automatically</b> on, approving an application sends it in one click. If the mail server is unreachable, the pilot is still created and the letter opens for you to send by hand.</li>
      <li>Set the website address, Discord invite and who letters are signed by under <b>Staff › Site and rules › Letters and links</b>. The address matters once PAC is on a server: sign-in links use it.</li>
      <li>Pilots choose their own passwords, which are stored as salted hashes. Nobody, staff included, can read them.</li>
      <li><b>Removing a pilot:</b> Staff › Roster › <b>Remove</b>. It shows what will be affected, then asks you to type the pilot ID. Their account, password, sign-in links, API keys, ratings, goals and wallet go; anything booked is released. Choose whether to <b>keep their flights in PAC's history</b> (shown as a former pilot, so airline totals stay right) or <b>erase everything</b>. Setting a pilot to <b>Inactive</b> instead keeps everything and just parks the account. Pilot IDs are never reused, unless <b>Reuse pilot IDs</b> is switched on for testing (Staff › Site and rules), which hands a removed pilot's ID to the next pilot. Turn that off before PAC goes live.</li></ul>`],
    ["crewbadge", "Your crew badge", `<p>Every PAC pilot gets a <b>crew identification badge</b> on the profile page, like the airport ID a real cargo crew wears airside. It carries your photo, name, rank, pilot ID, home base, issue and expiry dates, the areas you're cleared for (ramp, cargo build-up and the movement area, plus operations control for staff), your type ratings and a badge number.</p>
      <ul><li>Click the badge to turn it over for the conditions of use and your ratings.</li>
      <li><b>Download badge</b> saves it as a picture with the lanyard, for your Discord avatar or a forum signature.</li>
      <li>It updates by itself: earn a type rating or a promotion and the badge shows it.</li></ul>`],
    ["stationguides", "Station guides and downloads", `<p><b>Stations</b> has a guide for every airport in PAC's network: a satellite map with the runways drawn on, live weather, which PAC aircraft each runway suits, your record there and links to charts. Open one from the Stations page or from <b>Station guide</b> on any flight.</p>
      <ul><li><b>KCVG</b>, PAC's main hub, has a full guide: the cargo operation (DHL, Amazon, FedEx, North Cargo Village), runways with ILS categories, every frequency including the four ramp controls, arrival, ground, departure, noise and winter procedures, and PAC's stands P1 to P8 on the south cargo complex beside the DHL hub. ACARS assigns your Cincinnati stand from these, sized for your aircraft.</li>
      <li><b>Which stand to start on:</b> when you book from a hub with PAC stands, PAC puts you on one, chosen by aircraft size. It's shown on the flight page, on My bids, in the dispatch release and on the ACARS page, and PAC ACARS confirms it when you start tracking. Aircraft keep their stand between flights, so you start where you last parked, and PAC moves you if another aircraft is on it. <b>It's a convenience, not a rule:</b> start from any stand you like. Where you park is never scored, flagged or reviewed.</li>
      <li><b>PAC's other hubs</b> have stands too: Hong Kong uses real cargo apron stands X12 to X17 at their published positions; Miami, Milan Malpensa, Dubai World Central and Anchorage (PC1 to PC6) have stands on their cargo areas that staff can fine-tune on the satellite map. ACARS assigns these by aircraft size as well. PAC emblems mark the stands on the satellite map; staff use <b>Position stands</b> to drag them onto the ramp.</li>
      <li><b>Downloads</b> (Resources › Downloads) has PAC ACARS and other files from staff, SimBrief airframe sheets for every PAC aircraft, and the handbook and station guide to print. Your copy of PAC ACARS comes set up for the airline's website already. PAC liveries are on the <b>Fleet</b> page under each aircraft, with credit to their painters.</li></ul>`],
    ["missionboard", "The mission board", `<p>The mission board is alive: about 14 missions are open at a time, each for a few days, and new work arrives as others close. Missions come from real kinds of air-cargo work, many of them seasonal: Valentine's roses from Bogotá, Chilean cherries before Chinese New Year, durian and mango seasons, Alaskan king crab, smartphone launches and the 11.11 shopping festival, hurricane, typhoon and cyclone relief in their seasons, Beaujolais Nouveau in November, fashion weeks, Formula 1 and motorcycle flyaway races, pro football, basketball, baseball and hockey games abroad, European clubs' summer tours, stock cars to Mexico City, show horses, the winter World Cup circuit and stadium concert tours, the Antarctic season through Christchurch, and year-round work like vaccines on the cold chain, AOG engines, ship spares, data-center servers, rhino reintroductions, honeybees and satellites.</p>
      <ul><li>Several missions always leave from where you are. The same route doesn't come back within ten days.</li>
      <li><b>New</b> marks a mission that arrived in the last day; the gray tag shows how long it stays open.</li>
      <li>PAC's original hand-written missions come back from time to time, and the line checkride is always there.</li></ul>`],
    ["jobs", "Job board", `<p>A fresh set of cargo and ferry jobs appears every day at 0000Z, with several leaving from wherever you are. Partner crew requests arrive through the day instead, each open for a day or so.</p>
      <ul><li><b>Cargo jobs:</b> one-off work of every kind: racehorses and zoo animals, Grand Prix freight, museum art, satellites and wind-turbine parts, radiopharmaceuticals, wildfire equipment and more, to airports all over the world.</li>
      <li><b>Ferry flights:</b> move a PAC aircraft to where it's needed. The company pays the cost; you earn your hourly rate plus a ferry bonus.</li>
      <li><b>Partner crew requests</b> are listed separately under Missions › Partners (see Partners).</li>
      <li>Every board can be sorted by length, points or pay, and filtered to short, medium or long flights.</li></ul>`],
    ["groupflight", "Weekly group flight (optional)", `<p>Each week there's one suggested route under Crew room › Group flight. Nobody has to take part, and it changes nothing about your rank, pay or ratings.</p>
      <ul><li>Fly it at the set time (Saturdays at 23:00 UTC) if you'd like company, or on your own any time from a day before to two days after. Offline or online, voice chat or none: it all counts the same.</li><li>The route goes out from Cincinnati one week and back home the next, on 737-friendly scheduled routes, so if you flew out, you and your aircraft are already in place for the return.</li><li><b>Book the flight</b> opens it on the mission board, ready to plan. You can add yourself to a "planning to fly" list if you like, but you don't have to.</li><li>Every accepted PIREP on the route in that window shows under "Flown this week".</li></ul>
      <p>Staff can change the day and time, set a different route or briefing for any week, switch it off, and copy or post the Discord announcement from the Staff panel on the page.</p>`],
    ["online", "Flying online", `<p>Add your VATSIM CID or IVAO VID in Settings. ACARS checks the network's public feed every 5 minutes in the air. Seen on the network for at least 60% of the checks earns a 10% points bonus and marks the PIREP as flown online.</p>`],
    ["pay", "Pay and travel", `<ul><li><b>Pay:</b> every accepted flight pays an hourly rate by rank (Second Officer $55/h, First Officer $95/h, Senior First Officer $130/h, Captain $210/h, Senior Captain $280/h) plus 5% of the flight's profit. Pending flights are paid once staff accept them. Checkrides are company-funded training and aren't paid.</li>
      <li><b>Skill bonuses</b>, up to $475 a flight: grade A +$150 (B +$50), butter landing under 100 fpm +$100 (smooth under 200 fpm +$40, both with no bounce), trip fuel within 3% of the OFP +$75, the on-time bonus on a Critical or High priority flight +$50, stable approach +$50, and a clean flight with no review flags +$50.</li>
      <li><b>Your location</b> is where your last flight ended. You fly from there.</li>
      <li><b>Jumpseating</b> moves you somewhere else, paid from your wallet: a seat on a PAC freighter where PAC flies (cheap), or an airline ticket to anywhere (dearer).</li>
      <li>Ferry flights move you along with the aircraft, and pay you for the hours.</li></ul>`],
    ["ratings", "Type ratings and checkrides", `<p>${cfg.type_ratings_required ? "Each aircraft family needs a <b>type rating</b> before you fly regular work in it." : "Your rank decides what you can fly. <b>Type ratings</b> are optional: they go on your license and show what you've proved you can fly, but you don't need one to fly a type your rank has unlocked."} Ratings follow real-world families: one rating covers the 737-200C, 737-300SF and 737-800BCF; the 757 and 767 share one; the 747 classic and the 747-8 are separate.</p>
      <ul><li><b>How to earn one:</b> Career › Qualifications › <b>Book checkride</b>. It's a short company sector (${tc.min_nm} to ${tc.max_nm} nm) in that type, in a dedicated training aircraft or an available fleet aircraft, with free travel (see Company-funded checkrides). To pass: score ${tc.min_score} or better, land no firmer than ${Math.abs(tc.min_rate)} fpm at no more than ${tc.max_g} G, and have no more than one bounce. A steady approach allows up to ${tc.max_approach_speed_spread} kt of speed variation and sustained descent rates down to ${tc.max_sustained_descent_fpm} fpm below 500 ft. Overspeed penalties reduce score but aren't automatic failures; position jumps still fail. Staff accept the report, then the rating is yours.</li>
        ${cfg.direct_entry ? `<li><b>Already fly a type?</b> You can take any type checkride at any rank. An accepted passing report unlocks that family for line flights and also counts as your line checkride. Rank and pay keep their existing progression rules; this does not grant other aircraft ratings.</li>` : ""}
      <li><b>Already rated:</b> every type you flew with PAC before ratings began, and the 737 family once you pass the line checkride in the 737.</li>
      <li>Passing adds the checkride date to that type on your license. Staff can grant or remove ratings, or switch the requirement off (Staff › Site and rules).</li></ul>`],
    ["dispatchpaper", "Dispatch paperwork, goals and Discord", `<p>The <b>dispatch release</b> prints like real operational paperwork: the release with fuel, weights and signatures, a navigation log (when your SimBrief plan has waypoints), weather and NOTAMs, the loadsheet, the cargo manifest, <b>shipment details</b>, the NOTOC and the <b>ground handling</b> timeline. Print it or save it as a PDF from its toolbar; <b>Classic layout</b> shows the previous design.</p>
      <p><b>Shipment details:</b> every air waybill on the manifest has a shipper, a consignee and a forwarder: real companies that fit the cargo and both ends of the route (a GE Aerospace spare engine for an airline's grounded aircraft, Mowi salmon for a European wholesaler, WFP relief stock for a field team). Each shipment says why it's flying, how to handle it, and when the consignee gets it after you land. The shipments themselves are fictional.</p>
      <p><b>Ground handling:</b> the timeline from cargo acceptance, build-up, weighing and loading to doors closed, and from on-block through offload, customs and release at the other end.</p>
      <p><b>Sign the release:</b> like a real captain, you review the release and sign it before departure (with the NOTOC when dangerous goods are on board). Press <b>Sign release</b> on the paperwork; the release tab closes by itself and you're back on the page you came from. PAC ACARS starts once it's signed. A new SimBrief plan changes the fuel and weights, so it amends the release and you sign again.</p>
      <ul><li><b>Goals</b> (My stats): set targets such as 50 block hours this month, 5 new airports by a date, or 10 A grades this year. Progress updates as you fly.</li>
      <li><b>Discord</b> (Staff › Site and rules): paste a channel webhook to post departures and arrivals automatically. Landing cards and monthly recaps get a <b>Post to Discord</b> button.</li></ul>`],
    ["approach", "Approach profile and live traffic", `<p><b>Approach profile:</b> every flight in your logbook shows its final approach against an ideal 3° glidepath, measured by distance to the runway threshold, with a shaded band one dot either side like an ILS glideslope. Below it, your speed and sink rate, with the sink rate a 3° path needs at your groundspeed. The gate table shows how you crossed 1,000, 500 and 200 ft: on slope, slightly high or low (within one dot, still fine), high or low, or well off.</p>
      <p><b>Live traffic and weather radar:</b> on the ACARS map, choose <b>VATSIM traffic</b> or <b>IVAO traffic</b> to see who's flying around you (hover an aircraft for its callsign, type, altitude and route), and tick <b>Weather radar</b> for current precipitation (radar by RainViewer). Both refresh by themselves and are remembered.</p>`],
    ["planhelper", "Flight plan suggestions", `<p>The <b>SimBrief &amp; request</b> tab on every flight shows PAC's plan suggestions:</p>
      <ul><li><b>Cruise level:</b> the highest standard level for your direction (odd thousands eastbound, even westbound), no higher than the leg needs or the aircraft can reach.</li>
      <li><b>Fuel estimate:</b> trip, 5% contingency, alternate, 30 minutes final reserve and taxi.</li>
      <li><b>Runways:</b> the runway most likely in use at each end from the current wind, with headwind and crosswind, among runways long enough for your aircraft.</li>
      <li><b>Alternate:</b> the nearest suitable airport 40 to 250 nm from your destination.</li>
      <li>With <b>Use the cruise level and alternate in SimBrief</b> ticked, the plan you generate starts from them. SimBrief still works out the real numbers.</li></ul>`],
    ["stats", "My stats, airport collection and appearance", `<p><b>My stats</b> (My career › My stats) shows every flight you've flown: totals, a map of your routes and airports, hours by aircraft, flights per month, your records (click one to open that flight) and streaks.</p>
      <ul><li><b>Airport collection:</b> every airport you fly to or from counts. Milestones at 10, 25, 50 and 100 airports, 5, 10 and 25 countries, and all six continents earn awards.</li>
      <li><b>Monthly recap:</b> pick a month for your month in review, and download it as an image to keep or share.</li>
      <li><b>Dark mode:</b> Settings › Appearance: automatic (follows Windows), light or dark.</li>
      <li><b>Design:</b> Settings › Appearance › Design switches between <b>Load Sheet</b> (a dark side rail with load-sheet style headings) and <b>Classic</b> (the red top bar). It's remembered on each computer.</li></ul>`],
    ["signin", "Signing in", `<p>Pilots sign in with their <b>PAC pilot ID</b> and password. Visitors can see the home page, the fleet, the gallery and this handbook, and apply to fly.</p>
      <ul><li>New pilots receive a one-time <b>welcome link</b> from staff to choose their password. A forgotten password works the same way: ask staff for a sign-in link.</li>
      <li>Change your password in <b>Settings</b>. <b>Keep me signed in</b> remembers you on your computer for 30 days.</li>
      <li>PAC ACARS signs in once and stays signed in; sign out in the app's Settings.</li></ul>`],
    ["acarsapp", "The PAC ACARS app", `<p>Flights are tracked by the <b>PAC ACARS app</b>, a compact window that runs next to your simulator. Download it from the ACARS page (installer or portable zip).</p>
      <ul><li>Book your flight on the website, then press <b>Open in PAC ACARS</b> on the ACARS page. The app opens (or comes to the front) with the flight loaded and the right simulator selected. Press <b>Start tracking</b> in the app.</li>
      <li>The app reads MSFS or X-Plane, handles dispatch messages, weather and online checks, and keeps the website's ACARS page updated live.</li>
      <li>On block, the app hands the flight record to the website, which scores it. File from the app, or open the full report on the website.</li>
      <li><b>File anyway:</b> if the flight doesn't go on block after landing, press <b>File anyway</b> in the app. The PIREP goes to staff review.</li>
      <li>If the app or your PC restarts mid-flight, open the app again and press <b>Resume flight</b>. The flight in progress is saved on your PC and on the PAC website every minute, so any copy of PAC ACARS can resume it.</li>
      <li>PAC ACARS selects the simulator that's running (X-Plane or MSFS). Otherwise it picks what you last flew that aircraft type in.</li>
      <li><b>My bids</b> (and the flight pill in the header) always takes you back to your booked flight, with Open or Resume in PAC ACARS, the live flight page, the dispatch release and cancel.</li>
      <li><b>Flight plan:</b> press <b>Fetch OFP from SimBrief</b> in the app to load your plan (fuel, weights, route, alternate) before pushback.</li>
      <li><b>Messages:</b> a chime and a flashing <b>MSG</b> light tell you PAC Operations has sent something. Click MSG to read and acknowledge. Chime and volume are in the app's Settings.</li>
      <li><b>Compact mode</b> shrinks the app to a slim strip (phase, altitude, speeds, distance to go, last message) that stays on top. <b>Full</b> brings it back.</li>
      <li><b>Tray icon:</b> PAC ACARS sits in the notification area with a colored dot (green tracking, amber new message, blue on block, red problem). Minimizing the window mid-flight hides it to the tray. Closing it mid-flight asks whether to keep tracking in the tray or save the flight and quit; you can resume it later. To quit PAC ACARS completely, right-click the tray icon › Quit PAC ACARS.</li>
      <li>On block, the app shows your landing: rate, G, runway, touchdown point, centerline, float, wind and the grade.</li>
      <li>The first time, your browser asks whether to open PAC ACARS. Tick "always allow" to skip that next time.</li></ul>`],
    ["dispatchmsg", "Talking to dispatch", `<p>Use the <b>Dispatch</b> panel in the PAC ACARS app during a tracked flight. PAC Operations replies in the ACARS log after a short pause.</p>
      <ul><li><b>Delay:</b> report the minutes and the cause. Delays for ATC, weather, ground handling, late cargo or a technical fault are taken off your block time when judging a late delivery.</li>
      <li><b>Diversion:</b> declare it before landing. It then counts as a diversion (−10) instead of a failed delivery, at any airport.</li>
      <li><b>Fuel check</b> compares your fuel on board with your OFP. <b>ETA</b> asks for your arrival time. <b>Free text</b> gets a reply for stands, hotels, load questions and more.</li>
      <li>Dispatch also sends the final loadsheet at pushback and your arrival stand at top of descent.</li></ul>`],
    ["maintenance", "Maintenance write-ups", `<p>Report faults as <b>write-ups</b>, filed under real ATA chapters: during the flight (PAC ACARS › Dispatch › Fault), on the PIREP screen, or later from the flight in your logbook.</p>
      <ul><li><b>Deferred:</b> the aircraft keeps flying, and the fault must be fixed within 3 days (category B) or 10 days (category C). Deferred items appear on the next pilot's paperwork and airframe choice. When one runs out of time, the aircraft is grounded.</li>
      <li><b>Grounding:</b> the aircraft is out of service from arrival until maintenance clears it.</li>
      <li>Hard landings, tail strikes and A-checks open write-ups automatically. Staff clear them in Staff › Maintenance.</li>
      <li>Partner aircraft aren't PAC's to maintain: note faults in your PIREP remarks and they'll be passed on.</li></ul>`],
    ["partners", "Partners", `<p>${Object.values(S.partners || {}).map(p => esc(p.name)).join(", ")} sometimes run short of qualified captains through sickness, duty limits or training backlogs. When they do, they hire PAC pilots. Find the requests under Missions › Partners; new ones arrive through the day, and each stays open for a day or so.</p>
      <ul><li>You fly the partner's aircraft, not a PAC airframe, under its callsign and ICAO code. SimBrief opens with the partner's code, and the remarks note that a PAC pilot was hired to fill in.</li>
      <li>You're given one of the partner's real registrations for that type. It goes in SimBrief, on your paperwork and in your logbook.</li>
      <li>The partner pays for the aircraft, fuel and fees. You earn 1.5× your hourly rate plus a shortage bonus, and PAC earns a crew placement fee.</li>
      <li>Your landing and takeoff cards show a real photo of the partner's aircraft and its logo, marked "Flown for" the partner.</li></ul>
      <ul><li><b>Partner jumpseats:</b> when both ends of a trip are in a partner's network, you can ride its freighter for less than an airline ticket.</li></ul>
      <p class="muted" style="font-size:13px">The partnerships are simulated for a flight simulation virtual airline. Names and logos are trademarks of their owners; their use doesn't imply sponsorship or endorsement. Logos from Wikimedia Commons: FedEx Express, UPS, Qatar Airways, Emirates SkyCargo and Cathay Pacific (public domain); Atlas Air Worldwide logo by Atlas Air Worldwide Holdings, Inc., CC BY-SA 4.0. Aircraft photos on partner cards are freely licensed photos from Wikimedia Commons, credited on each card to their photographer with their license.</p>`],
    ["economics", "Airline economics", `<p>Every flight earns freight revenue and pays for fuel, landing and navigation fees, cargo handling, crew, maintenance, aircraft ownership and overhead. Profit goes into the company cash shown on the Finance page.</p>
      <ul><li><b>Revenue</b> grows with weight and distance. Premium, medical, urgent and heavy-lift work pays more. Dedicated charters are priced per aircraft hour, so a light load still pays.</li>
      <li><b>Relief flights</b> carry the smallest markup. The company doesn't profit much from disasters.</li>
      <li><b>You control costs:</b> fuel burned, block time, and incidents. A hard landing inspection, tail strike repairs or a diversion all come out of profit.</li>
      <li>Ferry flights earn nothing, so plan where your aircraft end up.</li>
      <li>Each flight's detail panel shows an estimate before you book, and each PIREP shows the actual figures.</li></ul>`],
    ["scoring", "Scoring", `<p>Every flight starts at 100.</p><table><tr><th>Item</th><th>Effect</th></tr>
      <tr><td>Landing −250 to −400 / −400 to −600 / below −600 fpm</td><td>−5 / −15 / −35</td></tr><tr><td>Landing below −1,000 fpm</td><td>Flight failed</td></tr>
      <tr><td>Landing load over 1.8 G / 2.5 G</td><td>−10 / −20</td></tr><tr><td>Trip fuel burned more than 15% / 25% over plan (burning less, e.g. after a shortcut, never costs points)</td><td>−5 / −10</td></tr>
      <tr><td>Landing below final reserve fuel</td><td>−15</td></tr><tr><td>Landing over the aircraft's max landing weight (up to 5% / more than 5% over)</td><td>−10 / −20</td></tr><tr><td>Overspeed below 10,000 ft / fast taxi / bounce</td><td>−5 / −3 / −5 each</td></tr>
      <tr><td>Position jump or slew in the air</td><td>−15</td></tr><tr><td>Airborne without a gate departure / a second takeoff roll</td><td>−10 / −10</td></tr>
      <tr><td>Diversion declared to dispatch / diverted to the OFP alternate undeclared / parked elsewhere</td><td>−10 / −20 / −40 and failed</td></tr>
      <tr><td>Critical or High priority within 10% of planned block</td><td>+5</td></tr><tr><td>Late: over 25% (urgent) or 35% (standard)</td><td>−10 / −5</td></tr></table>
      <p>Grades: A 90+, B 80+, C 70+, D 60+, F below. Points are the flight's reward scaled by your score, plus any event, featured-route or tour bonus.</p>`],
    ["review", "PIREP review", `<p>Flights scoring ${rv.auto_accept_score} or more with no flags are accepted automatically. Anything flagged goes to staff for review:</p>
      <ul><li>Landing firmer than ${Math.abs(rv.hard_landing_fpm)} fpm or above ${rv.max_landing_g} G</li><li>Diverted or failed flights</li><li>Position jumps or slew in the air</li><li>Ground pitch crossing the tail-clearance reference (possible contact, not confirmed)</li><li>More than 10 minutes paused in the air, or more than 10 seconds above 1× sim rate once moving</li><li>More than ${rv.max_bounces} bounce${rv.max_bounces === 1 ? "" : "s"}</li><li>Score below ${rv.auto_accept_score}</li></ul>
      <p>Pending and rejected flights stay in your logbook, but only accepted flights count towards hours, rank, points, awards and leaderboards.</p>`],
    ["airframes", "Airframes and maintenance", `<ul><li>A landing firmer than ${Math.abs(rv.hard_landing_fpm)} fpm grounds the airframe for a hard-landing inspection until staff release it.</li>
      <li>Every ${cfg.a_check_hours} flight hours the airframe is due an A-check and is grounded until staff sign it off.</li>
      <li>Every 6,000 flight hours it's due a heavy (C) check. It's done at one of PAC's maintenance bases: Cincinnati (KCVG), Milan (LIMC) or Hong Kong (VHHH). The aircraft can fly just one more flight, a ferry to the nearest base (it shows on the mission board), then spends 3 to 5 days in the hangar. Booking checks ahead: if a flight would leave too few hours to reach a base afterwards, it's refused and you're asked to pick another aircraft.</li>
      <li>A landing below −1,000 fpm damages the airframe. It stays out of service until staff return it.</li>
      <li>Staff manage the fleet: they add and remove airframes, and add, edit or retire aircraft types. Retired types can't be booked.</li></ul>`],
    ["events", "Events, featured routes and tours", `<ul><li><b>Events</b> such as Relief Week multiply the points on matching flights while they run.</li>
      <li><b>Featured routes</b> change every month, one per region, and pay ×${cfg.featured_mult}.</li>
      <li><b>Rotations</b> are freighter working patterns: several legs flown in order, back to where they started. Every full lap pays the rotation bonus and you can fly them as often as you like. Find them on the Rotations tab.</li>
      <li><b>Challenge</b> missions go to demanding airports (altitude, terrain, short or gravel runways, the Arctic, remote islands); the dossier says what to watch for. <b>Special cargo</b> missions (dangerous goods, live animals, valuables, outsize loads) come with handling notes. <b>Ferry</b> missions carry no cargo and pay the ferry bonus.</li>
      <li><b>Tours</b> are multi-leg journeys flown in order with a set aircraft type. Finishing a tour pays a one-off bonus and earns its badge:</li></ul>
      <table><tr><th>Tour</th><th>Route</th><th>Aircraft</th><th>Bonus</th></tr>${cfg.tours.map(t => `<tr><td>${esc(t.name)}</td><td>${t.legs.join(" – ")}</td><td>${t.aircraft.map(a => esc(S.fleet[a].icao)).join(", ")}</td><td>${fmt(t.bonus)}</td></tr>`).join("")}</table>`],
    ["conduct", "Conduct", `<p>Fly honestly and help each other. Report problems with ACARS rather than working around them. Staff decisions on reviews are final, but you can always ask why.</p>`],
  ];
  // reading order: who we are and how to join first, then planning and flying, then the rules, then everything else; staff notes last, for staff only
  const ORDER = ["welcome", "joining", "training-policy", "first-flight", "travel", "ranks", "transfers", "leave", "activity", "divisions", "ratings", "planning", "zones", "planhelper", "dispatchpaper", "cargofolder", "acarsapp", "flying",
    "dispatchmsg", "integrity", "scoring", "review", "pay", "partners", "missionboard", "jobs", "urgent", "events", "online", "maintenance", "airframes", "economics",
    "stationguides", "approach", "stats", "crewbadge", "signin", "conduct", "staffletters"];
  const pos = id => { const i = ORDER.indexOf(id); return i < 0 ? 99 : i; };
  sections.sort((a, b) => pos(a[0]) - pos(b[0]));
  if (!S.me?.staff) { const i = sections.findIndex(x => x[0] === "staffletters"); if (i >= 0) sections.splice(i, 1); }
  if (!S.settings?.activity_rule_on) { const i = sections.findIndex(x => x[0] === "activity"); if (i >= 0) sections.splice(i, 1); }
  $("#handbookRoot").innerHTML = `<div class="profile-bar"><h1>Pilot handbook</h1><span class="muted">Standards for every Pagani Air Cargo flight</span></div>
    <div class="handbook"><nav class="toc" aria-label="Handbook contents">${sections.map(([id, t]) => `<a href="#hb-${id}" data-hb="${id}">${t}</a>`).join("")}</nav>
    <div class="hb-body">${sections.map(([id, t, body]) => `<section id="hb-${id}"><h2>${t}</h2>${body}</section>`).join("")}</div></div>`;
  document.querySelectorAll("[data-hb]").forEach(a => a.onclick = e => { e.preventDefault(); $("#hb-" + a.dataset.hb).scrollIntoView({ behavior: "smooth" }); });
}

/* ================= Staff ================= */
S.staffTab = "reviews";
/* ===================== Crew mail ===================== */
function messageTime(seconds) {
  if (!Number.isFinite(Number(seconds)) || Number(seconds) <= 0) return "";
  return new Date(Number(seconds) * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}
async function loadMessages() {
  const root = $("#messagesRoot"); if (!root) return;
  const box = S.msgBox || "inbox";
  root.innerHTML = `<p class="muted">Loading crew mail…</p>`;
  let d; try { d = await api("/api/messages?box=" + encodeURIComponent(box)); }
  catch (e) { root.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  updateMsgBadge(d.unread);
  const tabs = [["inbox", "Inbox"], ["unread", "Unread" + (d.unread ? ` (${d.unread})` : "")], ["sent", "Sent"]];
  const empty = box === "sent" ? "You haven't sent any mail yet." : box === "unread" ? "No unread mail." : "Your inbox is empty.";
  root.innerHTML = `<div class="profile-bar"><h1>Crew mail</h1><button class="btn" id="msgCompose">Compose</button></div>
    <p class="muted">Send a note to another pilot. Staff can message the whole crew.</p>
    <div class="msg-tabs">${tabs.map(([k, t]) => `<button class="${box === k ? "on" : ""}" data-msgbox="${k}">${t}</button>`).join("")}</div>
    <div class="msg-list">${d.messages.length ? d.messages.map(m => msgRow(m, box)).join("") : `<p class="muted" style="padding:18px">${empty}</p>`}</div>`;
  $("#msgCompose").onclick = () => openCompose();
  root.querySelectorAll("[data-msgbox]").forEach(b => b.onclick = () => { S.msgBox = b.dataset.msgbox; loadMessages(); });
  root.querySelectorAll("[data-msg]").forEach(b => b.onclick = () => openMessage(+b.dataset.msg));
}
function msgRow(m, box) {
  const who = box === "sent" ? `To ${esc(m.recipient_name)}` : `From ${esc(m.sender_name)}`;
  return `<button type="button" class="msg-row ${!m.read && m.incoming ? "unread" : ""}" data-msg="${m.id}">
    <span class="msg-dot" aria-hidden="true"></span>
    <span class="msg-who">${who}</span>
    <span class="msg-subj"><b>${esc(m.subject)}</b> <span class="muted">${esc(m.body)}</span></span>
    <span class="msg-time">${messageTime(m.time)}</span></button>`;
}
async function openMessage(id) {
  let dlg = document.getElementById("msgDlg");
  if (!dlg) { dlg = document.createElement("dialog"); dlg.id = "msgDlg"; dlg.className = "msg-dlg"; document.body.appendChild(dlg); }
  dlg.innerHTML = `<p class="muted" style="padding:24px">Loading…</p>`; if (!dlg.open) dlg.showModal();
  try {
    const m = await api("/api/messages/" + id);
    const meta = m.incoming ? `From ${esc(m.sender_name)}${m.sender === "SYSTEM" ? "" : ` · ${esc(m.sender)}`}` : `To ${esc(m.recipient_name)} · ${esc(m.recipient)}`;
    dlg.innerHTML = `<article class="msg-read">
      <div class="msg-read-head"><b>${esc(m.subject)}</b><div class="muted">${meta} · ${messageTime(m.time)}</div></div>
      <div class="msg-read-body">${esc(m.body).replace(/\n/g, "<br>")}</div>
      <div class="msg-read-actions">
        ${m.incoming && m.replyable !== false ? `<button class="btn small" type="button" id="msgReply">Reply</button>` : ""}
        <button class="btn ghost small" type="button" id="msgDel">Delete</button>
        <button class="btn ghost small" type="button" onclick="this.closest('dialog').close()">Close</button></div></article>`;
    if (m.incoming && m.replyable !== false) $("#msgReply").onclick = () => { dlg.close(); openCompose(m.sender, "Re: " + m.subject.replace(/^\s*re:\s*/i, "")); };
    $("#msgDel").onclick = async () => {
      try { await api("/api/messages/" + id + "/delete", { method: "POST", body: {} }); dlg.close(); loadMessages(); }
      catch (e) { toast(e.message); }
    };
    loadMessages();                       // reading marked it read: refresh the list and badge behind the dialog
  } catch (e) { dlg.innerHTML = `<div style="padding:24px"><p>${esc(e.message)}</p><button class="btn small" onclick="this.closest('dialog').close()">Close</button></div>`; }
}
async function openCompose(to, subject) {
  let dlg = document.getElementById("composeDlg");
  if (!dlg) { dlg = document.createElement("dialog"); dlg.id = "composeDlg"; dlg.className = "msg-dlg"; document.body.appendChild(dlg); }
  if (!S.msgRecipients) { try { S.msgRecipients = await api("/api/messages/recipients"); } catch (e) { S.msgRecipients = { pilots: [], can_broadcast: false }; } }
  const R = S.msgRecipients;
  dlg.innerHTML = `<form class="msg-compose"><h2>New message</h2>
    <label>To<select name="to">${R.can_broadcast ? `<option value="ALL">Everyone · all pilots</option>` : ""}${R.pilots.map(p => `<option value="${esc(p.id)}" ${to === p.id ? "selected" : ""}>${esc(p.name)} · ${esc(p.id)}</option>`).join("")}</select></label>
    <label>Subject<input name="subject" maxlength="140" value="${esc(subject || "")}" placeholder="Subject"></label>
    <label>Message<textarea name="body" rows="8" placeholder="Write your message…"></textarea></label>
    <div class="msg-read-actions"><button class="btn small" type="submit">Send</button><button class="btn ghost small" type="button" onclick="this.closest('dialog').close()">Cancel</button></div></form>`;
  if (!dlg.open) dlg.showModal();
  dlg.querySelector(".msg-compose").onsubmit = async e => {
    e.preventDefault(); const f = e.target;
    try {
      const r = await api("/api/messages", { method: "POST", body: { to: f.to.value, subject: f.subject.value, body: f.body.value } });
      toast(r.sent > 1 ? `Sent to ${r.sent} pilots.` : "Message sent."); dlg.close();
      if (!$("#view-messages").hidden) { S.msgBox = "sent"; loadMessages(); }
    } catch (err) { toast(err.message); }
  };
}

