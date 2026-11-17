function displayPhoto(src, width = 800) {
  if (!src || !/^\/(?:api\/fleet\/[^/]+\/photo(?:\?|$)|gallery\/|static\/fleet\/)/.test(src)) return src;
  return '/media/image?src=' + encodeURIComponent(src) + '&w=' + width;
}
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
// a PAC air waybill number opens its public tracking page (pac-va.com/track/901-10000123)
const trackAwb = a => /^\d{3}-\d{8}$/.test(a || "") ? `<a class="mono awb-track" href="/track/${a}" target="_blank" rel="noopener" title="Open the public tracking page">${esc(a)}</a>` : esc(a);
const fmt = n => n == null || isNaN(n) ? "–" : Math.round(n).toLocaleString("en-US");
const hm = min => { if (min == null) return "–"; min = Math.round(min); return `${Math.floor(min/60)}h ${String(min%60).padStart(2,"0")}m`; };
const hms = s => { s = Math.max(0, Math.round(s||0)); return `${String(Math.floor(s/3600)).padStart(2,"0")}:${String(Math.floor(s%3600/60)).padStart(2,"0")}:${String(s%60).padStart(2,"0")}`; };
const zulu = t => t ? new Date(t*1000).toISOString().substr(11,5).replace(":","") + "Z" : "––––";

let initialCoreNavigation = false;
const S = { missions: [], fleet: {}, settings: {}, phases: [], booking: null,
  filter: "All", acFilter: "", selected: null, aircraft: null, ofp: null, ofpErrors: [], ofpWarnings: [], planned: false,
  status: null, pollTimer: null, map: null, layers: {}, pirep: null, cargoTransferIds: {} };

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined });
  const data = await res.json().catch(() => ({ error: `The ACARS server answered with an error (HTTP ${res.status}). Check the ACARS console window.` }));
  if (!res.ok) {
    const err = new Error(data.error || `Request failed (${res.status})`);
    err.status = res.status; err.data = data;
    if (res.status === 401 && S.me) { S.me = null; S.authPilot = null; applyAuth(); openSignIn("Your sign-in has ended. Please sign in again."); }
    throw err;
  }
  if (S.me && (path === '/api/airframes' || Array.isArray(data.airframes))) {
    const frames=path==='/api/airframes'?data:data.airframes;
    try{const response=await fetch('/api/fleet-reservations',{cache:'no-store'});if(response.ok){const info=await response.json();for(const a of frames){a.reservation=info.reservations?.[a.reg]||null;a.liveOperation=info.active_airframes?.[a.reg]||null;}}}catch(e){/* Existing availability remains visible if reservation details are unavailable. */}
  }
  return data;
}
let toastT;
function toast(msg, ms = 5200) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => t.hidden = true, ms); }

/* ---------------- navigation ---------------- */
const PUBLIC_VIEWS = ["home", "network", "track", "fleet", "handbook", "cargoguide", "gallery", "privacy", "piracy", "roster"];   // "live" joins when staff make the live map public
function show(view) {
  if (view === "reports" && location.hash !== "#reports") captureReportContext();
  if (/^career\/(overview|qualifications|wallet|activities|awards)$/.test(view)) {
    S.careerSection = view.split('/')[1]; view = 'career';
  }
  if (view === "staff" && S.me && !S.me.staff) view = "home";   // the staff area isn't there for pilots
  if (view === "liverylib" && S.me && !hasCap("liveries")) view = "home";   // scoped section: full admin or the Livery Manager only
  if (view === "creative" && S.me && !hasCap("creative")) view = "home";   // scoped section: full admin or the Creative / Media Director only
  if (view === "commercial" && S.me && !hasCap("commercial")) view = "home";   // scoped section: full admin or the Commercial Director only
  if (!S.me && !PUBLIC_VIEWS.includes(view)) {  // a members' page: sign in first, then go there
    openSignIn(null, view);
    if (!document.querySelector(".view:not([hidden])")) view = "home"; else return;
  }
  document.querySelectorAll("nav button[data-view]").forEach(b => b.setAttribute("aria-current", b.dataset.view === view));
  closeNavigation();
  document.querySelectorAll('#mainNav .nav-group').forEach(g => g.querySelector('.nav-disclosure').classList.toggle('nav-current', !!g.querySelector('[data-view="' + view + '"]')));
  document.querySelectorAll(".view").forEach(v => v.hidden = v.id !== "view-" + view);
  if (view === "network" || view === "track") {   // the public pages, shown inside the site so the menu stays
    const f = document.getElementById(view + "Frame"); if (f && !f.src) f.src = "/" + view + "?embed=1";
  }
  if (view === "acars") { renderAcars(); poll(); setTimeout(() => S.map && S.map.invalidateSize(), 50); }
  if (view === "logbook") loadLogbook();
  if (view === "profile") loadProfile();
  if (view === "fleet") loadFleet();
  if (view === "home") loadHome();
  if (view === "dashboard") { loadPilotBriefing(); loadCrewRest(); }
  if (view === "career") loadCareer();
  if (view === "finance") loadFinance();
  if (view === "shop") loadShop();
  if (view === "live") openLive(); else closeLive();
  if (view === "acars") showAcarsDownload();
  if (view === "gallery") loadGallery();
  if (view === "bids") loadBids();
  if (view === "stats") loadStats();
  if (view === "pilots") loadPilots(S.pilotOpen);
  if (view === "stations") loadStations();
  if (view === "cargo") loadCargo();
  if (view === "downloads") loadDownloads();
  if (view === "handbook") loadHandbook();
  if (view === "cargoguide") renderCargoGuide();
  if (view === "privacy") renderPrivacy();
  if (view === "piracy") renderPiracy();
  if (view === "roster") loadRoster();
  if (view === "staff") loadStaff();
  if (view === "liverylib") loadLiveryLib();
  if (view === "creative") loadCreative();
  if (view === "commercial") loadCommercial();
  if (view === "messages") loadMessages();
  if (view === "reports") loadProblemReports();
  if (view === "updates") loadWhatsNew();
  if (view === "crewplans") loadCrewPlans();
  if (view === "groupflight") loadGroupFlight();
  scrollTo({ top: 0 });
  if (view === "missions") { renderPilotStrip(); renderMissions(); refreshCore().then(() => { if (!$("#view-missions").hidden) renderMissions(); }); }
  location.hash = view === "career" ? "career/" + (S.careerSection || "overview") : view === "pilots" && S.pilotOpen ? "pilots/" + S.pilotOpen : view;
}
document.querySelectorAll("nav button[data-view]").forEach(b => b.onclick = () => show(b.dataset.view));
// the PAC logo always goes home and back to the top, even when the address already says #home
document.querySelector("header .brand")?.addEventListener("click", e => {
  if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;      // open in a new tab as usual
  e.preventDefault();
  if (location.hash !== "#home") history.pushState(null, "", "#home");
  show("home");
  scrollTo({ top: 0, behavior: "smooth" });
});
function closeNavigation() {
  document.querySelectorAll('.pac-nav-v2 .nav-disclosure').forEach(b => { b.setAttribute('aria-expanded','false'); document.getElementById(b.getAttribute('aria-controls')).hidden=true; });
  $('#navToggle').setAttribute('aria-expanded','false'); $('#mainNav').classList.remove('mobile-open');
}
document.querySelectorAll('.pac-nav-v2 .nav-disclosure').forEach(b => b.onclick = () => {
  const open=b.getAttribute('aria-expanded')!=='true';
  document.querySelectorAll('.pac-nav-v2 .nav-disclosure').forEach(other => {other.setAttribute('aria-expanded','false');document.getElementById(other.getAttribute('aria-controls')).hidden=true;});
  b.setAttribute('aria-expanded',String(open)); document.getElementById(b.getAttribute('aria-controls')).hidden=!open;
});
$('#navToggle').onclick=()=>{const open=$('#navToggle').getAttribute('aria-expanded')!=='true';closeNavigation();$('#navToggle').setAttribute('aria-expanded',String(open));$('#mainNav').classList.toggle('mobile-open',open);};
document.addEventListener('keydown',e=>{if(e.key==='Escape'){const b=document.querySelector('.pac-nav-v2 .nav-disclosure[aria-expanded="true"]') || document.querySelector('#navToggle[aria-expanded="true"]');if(b){closeNavigation();b.focus();}}});
document.addEventListener('click',e=>{if(!e.target.closest('.pac-nav-v2'))closeNavigation();else if(e.target.closest('#accountMenu button'))closeNavigation();});
function fitNav() {
 document.querySelectorAll('#mainNav .nav-group').forEach(g=>g.hidden=![...g.querySelectorAll('[data-view]')].some(b=>!b.classList.contains('auth-hidden')));
 if(!S.me) { closeNavigation(); }
}
let fitT = null;
window.addEventListener("resize", () => { clearTimeout(fitT); fitT = setTimeout(fitNav, 60); });
if (window.ResizeObserver) new ResizeObserver(() => { clearTimeout(fitT); fitT = setTimeout(fitNav, 30); }).observe(document.querySelector("header .pilot") || document.body);
document.fonts?.ready.then(fitNav);

addEventListener("hashchange", () => {
  const pm = location.hash.match(/^#pilots\/(PAC\d{4})$/i);       // a pilot's profile: #pilots/PAC0002
  if (pm) { if (S.pilotOpen !== pm[1].toUpperCase() || $("#view-pilots").hidden) openPilot(pm[1].toUpperCase()); return; }
  const v = location.hash.slice(1);
  if (/^career\/(overview|qualifications|wallet|activities|awards)$/.test(v)) {
    const section = v.split('/')[1];
    if (!$('#view-career').hidden) setCareerSection(section, false);
    else show(v);
    return;
  }
  const cur = document.querySelector("nav button[aria-current='true']")?.dataset.view;
  if (v && v !== cur && document.getElementById("view-" + v)) show(v);
});

/* ---------------- settings ---------------- */
const RANK_ABBR = { "Senior Captain": "Sr. Capt.", "Captain": "Capt.", "First Officer": "F/O", "Second Officer": "S/O", "Senior First Officer": "SFO", "Flight Engineer": "F/E" };
function displayName(p) { return [RANK_ABBR[p.rank] || p.rank, p.name].filter(Boolean).join(" "); }
function renderPilot() {
  const p = S.profile || {};
  $("#pilotLabel").innerHTML = `${esc(displayName(p))}<small class="pid"> · ${esc(p.pilot_id || S.settings.pilot_id)}</small>`;
  $("#pilotThumb").src = p.photo || "/static/pilot-photo.jpg";
}
function isFounder() { return !!S.me && S.me.id === (S.settings?.pilot_id || "PAC0001"); }
async function renderDiscordLink() {
  const el = $("#discordLink"); if (!el) return;
  let d; try { d = await api("/api/discord/me"); } catch (e) { el.hidden = true; return; }
  el.hidden = !d.enabled;
  if (!d.enabled) return;
  el.innerHTML = `<b>Discord</b> ${d.linked ? `<span class="tag green">Linked${d.discord_name ? ` as ${esc(d.discord_name)}` : ""}</span>
      <button class="btn ghost small" type="button" id="dcUnlink">Unlink</button>`
    : `<button class="btn ghost small" type="button" id="dcLink">Link my Discord account</button>`}
    <p class="muted" style="margin:4px 0 0;font-size:13px" id="dcMsg">${d.linked ? "The PAC Operations bot gives you your rank role and shows your PAC card with /pilot."
      : `Get your rank role and your own /pilot card in the PAC Discord${d.invite ? ` (<a href="${esc(d.invite)}" target="_blank" rel="noopener" style="color:var(--red)">join here</a>)` : ""}.`}</p>`;
  if ($("#dcLink")) $("#dcLink").onclick = async () => {
    try { const r = await api("/api/discord/code", { method: "POST" });
      $("#dcMsg").innerHTML = `In the PAC Discord, type <code class="si-code">/link ${esc(r.code)}</code> within ${r.minutes} minutes.`; }
    catch (e) { toast(e.message); }
  };
  if ($("#dcUnlink")) $("#dcUnlink").onclick = async () => {
    try { await api("/api/discord/unlink", { method: "POST" }); toast("Discord unlinked."); renderDiscordLink(); } catch (e) { toast(e.message); }
  };
}
$("#openSettings").onclick = () => {
  renderDiscordLink();
  const f = $("#settingsForm");
  const repo = $("#s_repo")?.closest("label"); if (repo) repo.hidden = !S.me?.staff;   // an airline rule: staff only
  for (const el of f.elements) if (el.name) { if (el.type === "checkbox") el.checked = S.settings[el.name] !== false; else el.value = S.settings[el.name] ?? ""; }
  $("#settingsDlg").showModal();
};
$("#settingsForm").onsubmit = async e => {
  e.preventDefault();
  const body = {}; for (const el of e.target.elements) if (el.name && !el.closest("[hidden]")) body[el.name] = el.type === "checkbox" ? el.checked : el.value.trim();
  body.vatsim_cid = (body.vatsim_cid || "").replace(/\D/g, ""); body.ivao_vid = (body.ivao_vid || "").replace(/\D/g, "");
  S.settings = await api("/api/settings", { method: "POST", body });
  renderPilot(); $("#settingsDlg").close(); toast("Settings saved.");
  if (S.base && S.map) { S.base.setStyle(S.settings.map_style); const ms = $("#mapStyle"); if (ms) ms.value = S.settings.map_style; }
  renderAcars();
};
document.querySelectorAll("[data-close]").forEach(b => b.onclick = () => b.closest("dialog").close());
$("#photoDlg").onclick = e => { if (e.target.id === "photoDlg" || e.target.id === "photoBig") e.currentTarget.close(); };

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
  if (S.board === 'network') drawNetwork(list);
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
  if (S.selected?.id !== id) { S.ofp = null; S.ofpErrors = []; S.ofpWarnings = []; S.planned = false; S.aircraft = m.aircraft[0]; S.airframe = S.pendingAirframe || (m.urgent && m.suggested_airframe) || defaultAirframe(m, S.aircraft); S.pendingAirframe = null; }
  if (S.selected?.id !== id && (S.acFilter || S.simFilter || S.boardQualifiedOnly || S.boardAvailableOnly)) {
    const matched = boardMatchTypes(m)[0];
    if (matched) { S.aircraft = matched; S.airframe = defaultAirframe(m,matched); }
  }
  S.selected = m;
  document.querySelectorAll(".waybill").forEach(b => b.setAttribute("aria-selected", b.dataset.id === id));
  renderDossier();
  highlightNetRoute();
  $("#dossier").scrollIntoView({ behavior: "smooth" });
  $("#dossier").focus({preventScroll:true});
}
function discordWidget(site) {   // the live Discord server widget on the home page (Staff › Site and rules › Letters and links)
  const id = String(site?.discord_widget || "").match(/\d{17,20}/)?.[0];
  if (!id) return "";
  const inv = String(site.discord_invite || "").trim();
  return `<div class="section-h"><div><div class="kicker">Community</div><h2>Join the crew room</h2><p>The PAC Discord is where pilots swap screenshots, talk routes and get help. See who's around right now.</p></div>${inv ? `<a class="btn ghost small" href="${esc(inv)}" target="_blank" rel="noopener">Join our Discord</a>` : ""}</div>
  <div style="display:flex;flex-wrap:wrap;gap:24px;align-items:flex-start">
    <iframe src="https://discord.com/widget?id=${id}&theme=dark" title="PAC Discord" width="350" height="420" style="max-width:100%;border:0;border-radius:8px;flex:0 0 auto;background:#2b2d31" allowtransparency="true" loading="lazy" sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts"></iframe>
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
function simbriefUrl(m, ac) {
  const fl = S.fleet[ac];
  const num = m.id.replace(/\D/g, "");
  const al = m.operator?.code || filingIcao();      // PAC flights are filed as PGI on the networks: PAC is Polar Air Cargo's code
  const p = new URLSearchParams({ airline: al, fltnum: num, orig: m.origin.icao, dest: m.destination.icao, type: myAirframe(ac) || fl.simbrief_airframe || fl.simbrief_type,   // the pilot's own airframe, then PAC's, then SimBrief's default
    cargo: (Math.min(m.payload_lbs, fl.max_payload_lbs) / 1000).toFixed(1), pax: "0", units: "LBS", callsign: al + num,
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
/* ---------------- Flight planning: four steps on tabs (Briefing, Aircraft, Load sheet, SimBrief & request) ---------------- */
try { S.extraFuel = Number(localStorage.getItem("pac-extra-fuel")) || 0; } catch (_) {}
const DTABS = [["brief", "Briefing"], ["aircraft", "Aircraft"], ["load", "Load sheet"], ["plan", "SimBrief & request"]];
function dossierAcReady(m) {
  if (m.training || m.contract || m.charter) return !!(S.aircraft || m.charter);
  const ac = S.aircraft;
  if (!ac || lockedByRank(m, ac) || needsRating(m, ac)) return false;
  if (S.settings.enforce_airframes === false) return true;
  const a = (S.airframes || []).find(x => x.reg === S.airframe);
  return !!(a && a.type === ac && a.status === "Available" && a.location === m.origin.icao);
}
function lsKey(m) {
  const transfers = (S.cargoTransferIds?.[m.id] || []).slice().sort().join(",");
  return `${m.id}|${m.charter ? m.aircraft[0] : S.aircraft}|${m.charter ? "" : S.airframe || ""}|${transfers}`;
}
function dossierTabDone(m, t) {
  if (t === "brief") return S.dTab !== "brief";
  if (t === "aircraft") return dossierAcReady(m);
  if (t === "load") return !!(S.lsSeen || {})[lsKey(m)];
  if (t === "plan") return !!(S.ofp && !S.ofpErrors.length);
  return false;
}
function dossierBlockers(m) {   // the readiness check, short: only shown when something needs arranging
  if (S.booking) return "";
  const ac = S.aircraft, dep = m.origin.icao, here = S.me?.location?.icao, out = [];
  if (S.me?.enforce_location && here !== dep && !m.type_checkride && m.category !== "Checkride" && m.id !== S.checkrideId)
    out.push(`You're at <b>${esc(here || "an unknown station")}</b>; this flight leaves from <b>${esc(dep)}</b>. <button type="button" class="btn small" onclick="openJumpseat('${esc(dep)}')">Travel to ${esc(dep)}</button>`);
  const rating = needsRating(m, ac);
  if (rating) out.push(`You need the <b>${esc(rating)}</b> type rating for the ${esc(S.fleet[ac]?.name || ac)}. <button type="button" class="btn ghost small" onclick="show('career/qualifications')">Qualifications</button>`);
  if (lockedByRank(m, ac)) out.push(`The ${esc(S.fleet[ac]?.name || ac)} unlocks at ${esc(rankFor(ac))}. Pick another type on the Aircraft step.`);
  if (!out.length) return "";
  return `<div class="dp-blockers" role="status"><b>Arrange first</b><ul>${out.map(x => `<li>${x}</li>`).join("")}</ul></div>`;
}
function dossierHeader(m) {
  const dist = m.distance_nm || gcnm(m.origin, m.destination);
  const date = t => new Date(t * 1000).toLocaleString("en-US", { timeZone: "UTC", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) + "Z";
  const chips = [
    ["Distance", `${fmt(dist)} nm`], ["Est. block", hm(m.target_block_min)],
    ["Payload", m.payload_lbs ? `${fmt(m.payload_lbs)} lb` : "Ferry"],
    m.reward ? ["Reward", `${fmt(m.reward)} pts`] : null,
    Number(m.deliver_by) > 0 ? ["Arrive by", date(m.deliver_by)] : null,
  ].filter(Boolean);
  const stn = (a, label) => `<div class="dp-stn"><small>${label}</small><b>${esc(a.icao)}</b><span>${esc(a.city || a.name || "")}</span><a href="#stations" class="st-link" data-station="${esc(a.icao)}">Station guide</a></div>`;
  return `<div class="dp-head">
    <div class="dp-top"><button type="button" class="dp-back" onclick="document.getElementById('manifest').scrollIntoView({block:'start'});document.getElementById('manifest').focus({preventScroll:true})">← Back to flights</button>
      <span class="dp-kind">${esc(m.id)} · ${esc(m.category)} · ${esc(m.priority)} priority</span>
      <button type="button" class="dp-crew" onclick="planSelectedWithCrew()">Plan with crew →</button></div>
    <h2>${esc(m.title)}</h2>
    <div class="dp-route">${stn(m.origin, "From")}<span class="dp-arrow" aria-hidden="true"><i></i></span>${stn(m.destination, "To")}</div>
    <div class="dp-chips">${chips.map(([k, v]) => `<div><span>${k}</span><b>${esc(v)}</b></div>`).join("")}<div id="payChip" class="dp-pay"><span>Your pay</span><b>…</b></div></div>
  </div>`;
}
function renderDossier() {
  const m = S.selected, d = $("#dossier");
  d.hidden = !m;
  if (!m) { d.innerHTML = `<div class="d-body"><h2>Choose a mission</h2><p class="muted">Pick a waybill from the list to read the briefing, plan it in SimBrief and request it for your next flight.</p></div>`; return; }
  if (S.dTabFor !== m.id) { S.dTab = "brief"; S.dTabFor = m.id; }
  const held = !!S.booking, tab = S.dTab || "brief", ix = DTABS.findIndex(t => t[0] === tab);
  const next = DTABS[ix + 1], prev = DTABS[ix - 1];
  d.innerHTML = `${dossierHeader(m)}
  <div class="dp-tabs" role="tablist" aria-label="Plan this flight">${DTABS.map(([k, label], i) => {
    const done = k !== tab && dossierTabDone(m, k);
    return `<button type="button" role="tab" id="dpt-${k}" aria-controls="dpPane" aria-selected="${k === tab}" tabindex="${k === tab ? 0 : -1}" data-tab="${k}" class="${done ? "done" : ""}"><span class="n">${done ? "✓" : i + 1}</span>${label}</button>`;
  }).join("")}</div>
  ${dossierBlockers(m)}
  <div class="dp-pane" id="dpPane" role="tabpanel" aria-labelledby="dpt-${tab}" tabindex="-1">${held && tab !== "brief"
    ? `<div class="notice">You already hold ${esc(S.booking.flight_number)}. Fly it or cancel it from ACARS before requesting another flight.</div>`
    : tab === "brief" ? paneBrief(m) : tab === "aircraft" ? paneAircraft(m) : tab === "load" ? paneLoad(m) : panePlan(m)}</div>
  <div class="dp-foot">${prev ? `<button type="button" class="btn ghost small" data-go="${prev[0]}">← ${prev[1]}</button>` : "<span></span>"}
    ${next && !(held && ix >= 0) ? `<button type="button" class="btn" data-go="${next[0]}">Next: ${next[1]} →</button>` : ""}</div>`;
  loadDossierEcon(m);
  if (tab === "brief") { loadDossierWx(m); fillZoneBrief(m); }
  if (tab === "load" && !held) loadLoadsheet(m);
  if (tab === "plan" && !held) { loadPlanHelper(m); ensureLoadsheet(m).then(() => planVsLoad(m)).catch(() => {}); }
  const go = t => { S.dTab = t; renderDossier(); const top = $("#dossier").getBoundingClientRect().top; if (top < 0) $("#dossier").scrollIntoView({ behavior: "smooth", block: "start" }); $("#dpPane")?.focus({ preventScroll: true }); };
  d.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => go(b.dataset.tab));
  d.querySelectorAll("[data-go]").forEach(b => b.onclick = () => go(b.dataset.go));
  d.querySelector(".dp-tabs").onkeydown = e => {
    const keys = { ArrowRight: 1, ArrowLeft: -1 }; if (!keys[e.key]) return;
    e.preventDefault(); const j = (ix + keys[e.key] + DTABS.length) % DTABS.length; go(DTABS[j][0]); $(`#dpt-${DTABS[j][0]}`)?.focus();
  };
  if (held) return;
  d.querySelectorAll("input[name=ac]").forEach(r => r.onchange = () => { S.aircraft = r.value; S.ofp = null; S.ofpErrors = []; S.airframe = defaultAirframe(m, r.value); renderDossier(); });
  d.querySelectorAll("input[name=af]").forEach(r => r.onchange = () => { S.airframe = r.value; renderDossier(); });
  d.querySelectorAll("[data-ferry]").forEach(b => b.onclick = () => ferryAirframe(b.dataset.ferry, m));
  d.querySelectorAll("[data-repo]").forEach(b => b.onclick = e => { e.preventDefault(); openReposition(b.dataset.repo, () => selectMission(m.id)); });
  if (tab !== "plan") return;
  $("#sbPlan").onclick = () => { S.planned = true; startDossierWatch(); setTimeout(renderDossier, 300); };
  if ($("#sbGen")) $("#sbGen").onclick = () => simbriefGenerate(m);
  if ($("#sbExtra")) $("#sbExtra").oninput = e => {
    const v = Math.max(0, Math.min(Number(e.target.max) || 1e6, Math.round(Number(e.target.value) || 0)));
    S.extraFuel = v; try { localStorage.setItem("pac-extra-fuel", String(v)); } catch (_) {}
    const sb = $("#sbPlan"); if (sb) sb.href = simbriefUrl(m, m.charter ? m.aircraft[0] : S.aircraft);
  };
  if ($("#sbGenCancel")) $("#sbGenCancel").onclick = e => { e.preventDefault(); simbriefGenStop(true); };
  if ($("#watchStop")) $("#watchStop").onclick = e => { e.preventDefault(); stopDossierWatch(); renderDossier(); };
  $("#sbFetch").onclick = () => importOfp();
  $("#ofpParse").onclick = () => importOfp($("#ofpRaw").value);
  $("#ofpFile").onchange = async e => { const f = e.target.files[0]; if (f) importOfp(await f.text()); };
  $("#request").onclick = () => requestMission(S.ofp);
  $("#requestNoOfp").onclick = () => { if (confirm("Fly without an OFP? Fuel and timing will be scored against the mission target only.")) requestMission(null); };
  if (S.ofp && !S.ofpErrors.length) wireVatsimFiling(d, m, m.charter ? m.aircraft[0] : S.aircraft, S.ofp);
}
function gravelNote(m) {
  if (!m.gravel_kit) return "";
  const names = (m.aircraft || []).map(a => S.fleet[a]?.name || a).join(" or ") || "Boeing 737-200C Advanced";
  return `<div class="notice" style="margin-bottom:10px;border-color:#b06a00;background:rgba(176,106,0,.08)">
    <b>❄ Gravel strip — gravel kit required.</b> This mission operates to or from an unpaved gravel runway. Only the <b>${esc(names)}</b> fitted with the gravel kit is cleared here, so it's the only type offered.</div>`;
}
function paneBrief(m) {
  const ok = !dossierBlockers(m) && !S.booking;
  return `${gravelNote(m)}${missionCargoBrief(m)}
    <div id="zoneBrief" data-for="${esc(m.id)}">${zoneBriefing(m, null)}</div>
    ${m.rotation ? rotationStrip(m) : ""}${specialBoxes(m)}
    ${m.contract && m.operator?.logo ? `<div class="dp-operator"><img src="${esc(m.operator.logo)}" alt=""><span><b>${esc(m.operator.name)}</b> is short of a qualified captain: ${esc(m.shortage_reason || "crew shortage")}. PAC pilot hired to fill in.</span></div>` : ""}
    ${m.charter ? (S.charterWarnings || []).map(w => `<div class="notice">${esc(w)}</div>`).join("") : ""}
    ${S.booking?.dep_stand?.icao === m.origin.icao ? `<p class="muted" style="font-size:13px">PAC has you parked at stand <b>${esc(S.booking.dep_stand.stand)}</b> at ${esc(m.origin.icao)} (any stand is fine).</p>` : ""}
    <div><h3 class="dp-h">Weather</h3><div class="wx-panel" id="wxPanel"><span class="muted" style="font-size:13px">Loading live weather…</span></div></div>
    <details class="dp-more"><summary>PAC's economics <span class="muted">· what the company earns on this flight</span></summary><div id="econPanel"><span class="muted" style="font-size:13px">Estimating…</span></div></details>
    ${ok && zoneFor(m)?.level === "restricted" ? `<p class="dp-ready" style="border-color:#c0262d;background:rgba(192,38,45,.07)"><b>You're qualified, but this flight isn't authorized.</b> You can still fly it, but it won't be credited (see the restricted airspace box above).</p>` : ok ? `<p class="dp-ready">No location, rating or rank blocker found. Pick your aircraft next; final checks run when you request the flight. <button type="button" class="linkish" onclick="openPilotGuide('${m.type_checkride || m.category === "Checkride" ? "checkride" : "cargo"}')">Step-by-step guide</button></p>` : ""}`;
}
function paneAircraft(m) {
  const types = m.charter ? `<p class="dp-lead">Charter aircraft: <b>${esc(S.fleet[m.aircraft[0]].name)}</b>. Change it in the charter form and rebuild.</p>` : `
    <h3 class="dp-h">Aircraft type</h3>
    ${gravelNote(m)}
    <p class="muted dp-sub">${m.tour || m.rotation || m.types_only || m.category === "Checkride" ? "This flight is for the types listed here." : "Any aircraft in the fleet can fly this mission. Starred types are the best fit for the load and airports."}</p>
    <div class="ac-pick" role="radiogroup" aria-label="Aircraft">${fleetOrder(m).map(a => { const lock = lockedByRank(m, a);
      return `<label title="${lock ? "Unlocks at " + esc(rankFor(a)) : ""}" style="${lock ? "opacity:.5" : ""}"><input type="radio" name="ac" value="${a}" ${S.aircraft === a ? "checked" : ""} ${lock ? "disabled" : ""}>${esc(S.fleet[a].name)}${m.aircraft.includes(a) ? " ★" : ""}${S.fleet[a].sim === "X-Plane" ? ' <small class="muted">XP</small>' : ""}${lock ? " · " + esc(rankFor(a)) : needsRating(m, a) ? ` · <small class="muted" title="Fly the ${esc(needsRating(m, a))} type checkride from Career › Qualifications first">needs ${esc(needsRating(m, a))} rating</small>` : ""}</label>`; }).join("")}</div>
    ${capacityNote(m, S.aircraft)}`;
  const ptail = partnerTail(m, S.aircraft);
  const poss = n => /s$/i.test(n) ? `${n}'` : `${n}'s`;   // "UPS Airlines'", "Atlas Air's"
  const tail = m.contract ? `<div class="notice">You fly <b>${esc(poss(m.operator.name))}</b> ${ptail ? `<b>${esc(ptail)}</b>, one of their ${esc(S.fleet[S.aircraft]?.name || "")}s,` : "aircraft"} under callsign <b>${esc(m.operator.callsign)}</b> (${esc(m.id)}). No PAC airframe is used${ptail ? `: SimBrief gets ${esc(ptail)} as the registration. Load ${esc(m.operator.name)} livery if you have it.` : `: load any ${esc(S.fleet[S.aircraft]?.name || "")} livery you like.`}</div>`
    : `<h3 class="dp-h">Airframe</h3>${airframePicker(m, S.aircraft)}`;
  return `${types}${tail}<details class="journey-help"><summary>Aircraft missing? Understand travel and ferry options</summary>${travelGuideHTML()}</details>`;
}
function paneLoad(m) {
  if (m.training) return `<div class="notice">Training flight: no cargo is carried, so there's no load sheet. Plan it in SimBrief with an empty hold.</div>`;
  return `<div id="lsPanel" class="ls-wrap"><span class="muted" style="font-size:13px">Building the preliminary load sheet…</span></div>`;
}
function panePlan(m) {
  const ofpOk = S.ofp && !S.ofpErrors.length;
  const step = !S.planned && !S.ofp ? 1 : !ofpOk ? 2 : 3;
  const noun = m.category === "Ferry" ? "ferry" : m.charter ? "charter" : m.category === "Scheduled" ? "flight" : "mission";
  const ls = (S.lsCache || {})[lsKey(m)];
  return `<div class="dp-plan-grid">
    <div><h3 class="dp-h">Flight plan suggestions</h3><div id="planPanel"><span class="muted" style="font-size:13px">Working it out…</span></div></div>
    <ol class="steps">
      <li data-n="1" class="${step > 1 ? "done" : "current"}">
        <h3>Generate the plan in SimBrief</h3>
        <p class="muted" style="font-size:13px;margin:0 0 8px">Filled in for you: ${esc(S.fleet[m.charter ? m.aircraft[0] : S.aircraft]?.name || "")}${S.airframe && !m.contract ? ` (${esc(S.airframe)})` : ""}, route, callsign and <span id="sbCargo">${ls && !ls.ferry ? `<b>${fmt(ls.totals.weight_lbs)} lb</b> of cargo from your load sheet` : "the cargo weight"}</span>.</p>
        <div class="sb-extra"><label for="sbExtra">Extra fuel <small>(lb, your call)</small></label>
          <input id="sbExtra" type="number" min="0" max="${Math.round((S.fleet[m.charter ? m.aircraft[0] : S.aircraft]?.mtow_lbs || 400000) * 0.2)}" step="500" inputmode="numeric" value="${S.extraFuel || ""}" placeholder="0">
          <small class="muted">On top of SimBrief's trip, contingency, alternate and reserve. Carrying extra is never penalized; PAC only pays for fuel you burn.</small></div>
        ${simPicker(m.charter ? m.aircraft[0] : S.aircraft)}
        ${S.settings.simbrief_api ? `
        <div class="row"><button type="button" class="btn" id="sbGen" ${S.sbGen ? "disabled" : ""}>${S.sbGen ? "Generating in SimBrief…" : S.ofp ? "Generate a new OFP" : "Generate OFP"}</button>
          <a class="btn ghost small" id="sbPlan" href="${simbriefUrl(m, m.charter ? m.aircraft[0] : S.aircraft)}" target="_blank" rel="noopener">Or open SimBrief yourself</a></div>
        <p class="muted" style="font-size:13px;margin:6px 0 0">${S.sbGen ? "Finish in the SimBrief window. It closes by itself when the plan is ready, and the OFP comes straight in here. <a href=\"#\" id=\"sbGenCancel\">Cancel</a>" : "A small SimBrief window builds the plan with these details and closes by itself; the OFP is imported here automatically. Sign in to SimBrief in that window if it asks. Allow pop-ups for this site."}</p>`
        : `<a class="btn" id="sbPlan" href="${simbriefUrl(m, m.charter ? m.aircraft[0] : S.aircraft)}" target="_blank" rel="noopener">Open SimBrief with this ${noun}</a>
        <p class="muted" style="font-size:13px;margin:6px 0 0">In SimBrief, click <b>Generate Flight</b>, then come back here. Filling in the form alone does not create a plan.</p>`}
        <p class="muted" style="font-size:13px;margin:4px 0 0">Flying online? Connect to VATSIM or IVAO as <b>${esc(atcCallsign(m))}</b>${m.operator ? "" : `, spoken “Pagani ${esc(m.id.replace(/\D/g, ""))}” (<code>CALLSIGN PAGANI</code> is already in the remarks)`}.</p>
      </li>
      <li data-n="2" class="${step > 2 ? "done" : step === 2 ? "current" : ""}">
        <h3>Import the OFP</h3>
        <div class="row"><button class="btn small" id="sbFetch">Fetch latest OFP</button><span class="muted" style="font-size:13px">${S.settings.simbrief_username || S.settings.simbrief_userid ? `SimBrief: ${esc(S.settings.simbrief_username || S.settings.simbrief_userid)}` : `Add your SimBrief login in Settings`}</span></div>
        ${S.dWatch && S.dWatch.sel === m.id ? `<p class="watch-note"><i></i>Watching SimBrief for your new plan. It's imported here automatically as soon as you generate it. <a href="#" id="watchStop">Stop</a></p>` : ""}
        <details style="margin-top:8px"><summary>Paste or upload an OFP instead</summary>
          <textarea id="ofpRaw" placeholder="Paste the SimBrief OFP as JSON or XML"></textarea>
          <div class="row" style="margin-top:6px"><input type="file" id="ofpFile" accept=".json,.xml"><button class="btn ghost small" id="ofpParse">Import pasted OFP</button></div>
        </details>
        ${ofpCard()}
        ${ofpOk ? vatsimFilingPanel(m, m.charter ? m.aircraft[0] : S.aircraft, S.ofp) : ""}
        <div id="planVsLoad"></div>
      </li>
      <li data-n="3" class="${step === 3 ? "current" : ""}">
        <h3>Request the ${noun}</h3>
        <p class="muted" style="font-size:13px;margin:0 0 8px">Reserves this flight. Your release keeps the units and positions from the load sheet, with fuel and weights from your OFP. Then review and sign it before tracking in PAC ACARS.</p>
        <div class="row"><button class="btn" id="request" ${ofpOk ? "" : "disabled"}>Request ${noun}</button>
        <button class="btn ghost small" id="requestNoOfp" title="Fly without an OFP">Request without OFP</button></div>
        ${!ofpOk ? `<p class="journey-reason" role="status">${S.ofp ? "Resolve the OFP issues listed above, then request the flight." : "Generate your flight in SimBrief, then use Fetch latest OFP to enable the main request button."} You can also use Request without OFP; booking checks still apply.</p>` : ""}
      </li>
    </ol></div>`;
}

/* The preliminary load sheet: built before SimBrief from the mission, the type and PAC's fuel estimate */
async function ensureLoadsheet(m) {
  if (m.training) return null;
  const key = lsKey(m);
  S.lsCache ||= {};
  if (S.lsCache[key]) return S.lsCache[key];
  // same mission and type with another tail: keep the same units (the seed), just a new tail on the sheet
  const prior = Object.entries(S.lsCache).find(([k]) => k.startsWith(`${m.id}|${m.charter ? m.aircraft[0] : S.aircraft}|`))?.[1];
  const ls = await api("/api/plan/loadsheet", { method: "POST", body: { mission_id: m.id, charter: m.charter, aircraft: m.charter ? m.aircraft[0] : S.aircraft, airframe: m.contract ? null : S.airframe, seed: prior?.seed, cargo_transfer_ids: S.cargoTransferIds?.[m.id] || [] } });
  return (S.lsCache[key] = ls);
}
async function loadLoadsheet(m) {
  const el = $("#lsPanel"); if (!el) return;
  const key = lsKey(m);
  S.lsSeen ||= {};
  try {
    const ls = await ensureLoadsheet(m);
    if ($("#lsPanel") !== el || lsKey(m) !== key) return;
    el.innerHTML = loadsheetHTML(ls, m);
    if (!S.lsSeen[key]) { S.lsSeen[key] = true; d_markTab("load"); }
    el.querySelectorAll("[data-pos]").forEach(c => c.onclick = () => lsFocus(el, c.dataset.pos));
    wireTransferCargo(el, ls, m);
    wireCargoFolder(el, ls);
    wireLsTabs(el, ls);
  } catch (e) {
    el.innerHTML = `<div class="notice">${esc(e.message)}${(S.cargoTransferIds?.[m.id] || []).length ? ' <button type="button" class="linkish" data-clear-transfers>Clear selected transfer cargo</button>' : ""}</div>`;
    el.querySelector("[data-clear-transfers]")?.addEventListener("click", () => {
      S.cargoTransferIds[m.id] = [];
      loadLoadsheet(m);
    });
  }
}
function d_markTab(k) { const b = $(`#dpt-${k}`); if (b && b.getAttribute("aria-selected") !== "true") { b.classList.add("done"); b.querySelector(".n").textContent = "✓"; } }
function lsFocus(root, pos) {
  root.querySelectorAll(".on").forEach(x => x.classList.remove("on"));
  root.querySelectorAll(`[data-pos="${CSS.escape(pos)}"]`).forEach(x => x.classList.add("on"));
  const row = root.querySelector(`tr[data-pos="${CSS.escape(pos)}"]`);
  if (row) { const box = row.closest(".ls-table-wrap"); if (box) box.scrollTop = row.offsetTop - box.clientHeight / 2; }
}
const LS_CLASS = p => p.dg ? "dg" : p.shc.some(c => ["PER", "PIL", "COL", "PES", "PEF", "CRT", "EAT"].includes(c)) ? "cool" : p.shc.includes("VAL") ? "val" : p.shc.some(c => ["AOG", "HEA", "BIG"].includes(c)) ? "heavy" : p.shc.includes("AVI") ? "avi" : "gen";
function deckRow(list, byPos, cap, label) {
  return `<div class="ls-deck-row"><span class="ls-deck-label">${label}</span><div class="ls-cells">${list.map(pos => {
    const p = byPos[pos], fill = p ? Math.max(.08, Math.min(1, p.weight_lbs / cap)) : 0;
    return p ? `<button type="button" class="ls-cell ${LS_CLASS(p)}" data-pos="${esc(pos)}" title="${esc(`${pos} · ${p.unit} · ${p.contents} · ${fmt(p.weight_lbs)} lb${p.dg ? " · DG " + p.dg : ""}`)}" aria-label="${esc(`${pos}, ${p.contents}, ${fmt(p.weight_lbs)} pounds`)}"><i style="height:${Math.round(fill * 100)}%"></i><span>${esc(pos.replace(" BULK", ""))}</span></button>`
      : `<span class="ls-cell empty" title="${esc(pos)} · empty"><span>${esc(pos.replace(" BULK", ""))}</span></span>`;
  }).join("")}</div></div>`;
}
/* Load sheet step, in three tabs so the page stays short: load and limits, the manifest, the cargo folder */
function lsTabsHTML(ls, units) {
  if (ls.ferry || !units) return "";
  const n = (ls.shipments || []).filter(x => x.awb_doc).length, tab = S.lsTab || "load";
  const t = [["load", "Load & limits"], ["manifest", `Cargo manifest · ${units} unit${units === 1 ? "" : "s"}`], ...(n ? [["folder", `Cargo folder · ${n} air waybill${n === 1 ? "" : "s"}`]] : [])];
  return `<div class="ls-tabs" role="tablist">${t.map(([k, l]) => `<button type="button" role="tab" data-lstab="${k}" aria-selected="${k === tab}">${l}</button>`).join("")}</div>`;
}
function wireLsTabs(el, ls) {
  el.querySelectorAll("[data-lstab]").forEach(b => b.onclick = () => {
    S.lsTab = b.dataset.lstab;
    el.querySelectorAll("[data-lstab]").forEach(x => x.setAttribute("aria-selected", x === b));
    el.querySelectorAll("[data-lspane]").forEach(p => p.hidden = p.dataset.lspane !== S.lsTab);
  });
  el.querySelectorAll(".ls-cell[data-pos]").forEach(c => c.addEventListener("click", () => {
    const p = (ls.positions || []).find(x => x.pos === c.dataset.pos), sh = p && (ls.shipments || []).find(x => x.awb === p.awb), box = el.querySelector("#lsUnit");
    if (p && box) box.innerHTML = `<b class="mono">${esc(p.pos)}</b> · <span class="mono">${esc(p.unit)}</span> · ${esc(p.contents)} · ${fmt(p.weight_lbs)} lb · ${p.pieces} pcs${sh ? ` · ${esc(sh.shipper.name)} → ${esc(sh.consignee.name)}` : ""} · AWB <span class="mono">${esc(p.awb)}</span>`;
  }));
}
function loadsheetHTML(ls, m) {
  const L = ls.loadsheet, f = ls.fuel, byPos = Object.fromEntries((ls.positions || []).map(p => [p.pos, p]));
  const gauge = c => { const pct = Math.min(100, Math.round(c.value / Math.max(1, c.limit) * 100));
    return `<div class="ls-gauge ${c.ok ? (pct > 97 ? "tight" : "") : "over"}"><div class="ls-g-top"><span>${esc(c.name)}</span><b>${fmt(c.value)}</b><small>${esc(c.code)} ${fmt(c.limit)}</small></div><div class="ls-bar"><i style="width:${pct}%"></i></div><small class="ls-margin">${c.ok ? `${fmt(c.margin)} lb margin` : `${fmt(-c.margin)} lb OVER the limit`}</small></div>`; };
  const partial = !ls.ferry && ls.payload_requested > ls.totals.weight_lbs + 50;
  const units = (ls.positions || []).length, tail = ls.tail && ls.tail !== "—" ? ls.tail : "";
  const transferIds = new Set(ls.cargo_transfer_ids || []);
  const transferOptions = ls.transfer_options || [];
  return `
  <div class="ls-title"><div><span class="kicker">Preliminary load sheet</span><h3>${esc(ls.aircraft_name)}${tail ? ` · <span class="mono">${esc(tail)}</span>` : ""} · ${esc(ls.origin.icao)} → ${esc(ls.destination.icao)}</h3>
    <p class="muted">${ls.ferry ? "Ferry flight: the hold is empty." : `${units} unit${units === 1 ? "" : "s"} · ${fmt(ls.totals.pieces)} pieces · ${fmt(ls.totals.weight_lbs)} lb · ${(ls.shipments || []).length} shipment${(ls.shipments || []).length === 1 ? "" : "s"}`}</p></div>
    <span class="ls-status ${ls.ok ? "ok" : "bad"}">${ls.ok ? "Within limits" : "Over a limit"}</span></div>
  ${transferOptions.length ? `<section class="ls-transfer"><h4>Transfer cargo at ${esc(ls.origin.icao)}</h4><p class="muted">Select freight already at this station and routed through ${esc(ls.destination.icao)}. It keeps its original AWB and is delivered only when it reaches its final destination. ${fmt(ls.cargo_transfer_weight_lbs || 0)} lb selected.</p>
    <div class="ls-transfer-list">${transferOptions.map(x => `<label><input type="checkbox" data-transfer-id="${esc(x.id)}" ${transferIds.has(x.id) ? "checked" : ""}><span><b>${esc(x.awb)}</b> · ${esc(x.commodity || "Cargo")} · ${fmt(x.gross_weight_lbs)} lb · ${fmt(x.pieces)} pcs · final ${esc(x.destination)}${x.claimed_by_me ? ` <span class="tag lane-pref">Held for you</span>` : ""}${x.truck_nm ? ` <span class="tag grey" title="PAC flies it to your destination; the last leg goes by road">last ${fmt(x.truck_nm)} nm by truck</span>` : ""}</span><small>${esc(x.shipper || "—")} → ${esc(x.consignee || "—")}</small>${(x.notes || []).map(n => `<small class="ls-note"><b>Handover note from ${esc(n.pilot)} at ${esc(n.station || "")}:</b> ${esc(n.text)}</small>`).join("")}</label>`).join("")}</div></section>` : ""}
  ${partial ? `<div class="notice">The ${esc(ls.aircraft_name)} carries up to ${fmt(ls.limits.max_payload)} lb, so you'll take ${fmt(ls.totals.weight_lbs)} lb of the ${fmt(ls.payload_requested)} lb consignment.</div>` : ""}
  ${!ls.ok ? `<div class="notice err">This load and fuel go over a structural limit${ls.checks.some(c => c.code === "MTOW" && !c.ok) ? ": SimBrief will cut the cargo to fit under the take-off weight limit" : ""}. Pick a larger type on the Aircraft step, or plan less fuel or cargo.</div>` : ""}
  ${lsTabsHTML(ls, units)}
  <div class="ls-pane" data-lspane="load" ${(S.lsTab || "load") === "load" || !units ? "" : "hidden"}>
  ${ls.ferry ? "" : `<div class="ls-deck" aria-label="Cargo positions, nose on the left">
    <div class="ls-nose" aria-hidden="true">NOSE</div>
    <div class="ls-decks">${deckRow(ls.deck.main, byPos, ls.deck.cap, `Main deck · ${esc(ls.deck.uld)}`)}${ls.deck.lower.length ? deckRow(ls.deck.lower, byPos, ls.deck.lcap, `Lower · ${esc(ls.deck.luld)}`) : ""}</div></div>
    <div class="ls-legend"><span class="gen">General</span><span class="cool">Temperature / perishable</span><span class="val">Valuable</span><span class="heavy">Heavy / AOG / outsize</span><span class="avi">Live animals</span><span class="dg">Dangerous goods</span><span class="muted">Bar height = weight against the unit's ${fmt(ls.deck.cap)} lb limit. Click a unit.</span></div>
    <div class="ls-unit muted" id="lsUnit">Click a unit on the deck to see what's in it.</div>`}
  <div class="ls-grid">
    <section><h4>Weights (lb)</h4>
      <table class="ls-calc"><tbody>
        <tr><td>Dry operating weight</td><td>${fmt(L.dow)}</td></tr>
        <tr><td>+ Payload</td><td>${fmt(L.payload)}</td></tr>
        <tr class="sum"><td>Zero fuel weight</td><td>${fmt(L.zfw)}</td></tr>
        <tr><td>+ Take-off fuel</td><td>${fmt(L.tof)}</td></tr>
        <tr class="sum"><td>Take-off weight</td><td>${fmt(L.tow)}</td></tr>
        <tr><td>− Trip fuel</td><td>${fmt(L.trip)}</td></tr>
        <tr class="sum"><td>Landing weight</td><td>${fmt(L.law)}</td></tr>
        <tr class="under"><td>Underload before limits</td><td>${fmt(L.underload)}</td></tr></tbody></table>
      <p class="muted ls-fine">${ls.dow_source?.kind === "learned" ? `Dry operating weight from ${ls.dow_source.flights} recent PAC flights on this type (their SimBrief plans).` : "Dry operating weight estimated from published limits; it becomes exact once a few PAC flights on this type have been filed with an OFP."}</p>
    </section>
    <section><h4>Against the limits</h4>${ls.checks.map(gauge).join("")}</section>
    <section><h4>Fuel estimate (lb)</h4>
      <table class="ls-calc"><tbody>
        <tr><td>Trip</td><td>${fmt(f.trip)}</td></tr><tr><td>Contingency 5%</td><td>${fmt(f.contingency)}</td></tr>
        <tr><td>Alternate${ls.alternate ? ` ${esc(ls.alternate.icao)}` : ""}</td><td>${fmt(f.alternate)}</td></tr>
        <tr><td>Final reserve 30 min</td><td>${fmt(f.final_reserve)}</td></tr><tr><td>Taxi</td><td>${fmt(f.taxi)}</td></tr>
        <tr class="sum"><td>Block fuel</td><td>${fmt(f.block)}</td></tr>
        <tr class="under"><td>Minimum release fuel</td><td>${fmt(ls.min_release_fuel)}</td></tr></tbody></table>
    </section>
    <section><h4>Balance and trim</h4>
      <div class="ls-bal"><div><span>MAC at ZFW</span><b>${L.mac_zfw}%</b></div><div><span>MAC at TOW</span><b>${L.mac_tow}%</b></div>${L.mac_ldw != null ? `<div><span>MAC at landing</span><b>${L.mac_ldw}%</b></div>` : ""}
        <div><span>Stab trim</span><b>${esc(L.trim)}</b></div><div><span>DOI / DLI</span><b>${L.doi} / ${L.dli}</b></div>
        <div><span>Crew</span><b>${esc(L.crew)}</b></div><div><span>Cruise</span><b>FL${String(ls.cruise_fl).padStart(3, "0")}</b></div></div>
      <p class="muted ls-fine">Main deck ${fmt(ls.totals.main_lbs)} lb · lower hold ${fmt(ls.totals.lower_lbs)} lb. ${L.cg_source === "calculated" ? "CG and trim calculated from documented weight-and-balance data." : L.cg_source === "provisional" ? "CG calculated from approximate weight-and-balance data (the sources are in the load planner)." : "CG and trim are PAC estimates for this type."}${ls.balance && ls.balance.available && !ls.balance.within_envelope ? ` <b style="color:#b00000">${esc(ls.balance.advice || "")}</b>` : ""}</p>
      ${ls.balance?.loadmaster ? `<p class="ls-fine" title="${esc(ls.balance.loadmaster.items.map(i => `${i[0]}: ${i[1]}/${i[2]}`).join("\n"))}"><b>Loadmaster score ${ls.balance.loadmaster.score}/100 · ${esc(ls.balance.loadmaster.grade)}</b> <span class="muted">${esc(ls.balance.loadmaster.items.filter(i => i[1] < i[2]).map(i => i[0]).join(" · ") || "Nothing to improve.")} Rearrange units in the load planner to improve it.</span></p>` : ""}
    </section>
  </div>
  ${(ls.dg || []).length ? `<section class="ls-dg"><h4>Dangerous goods (NOTOC preview)</h4><ul>${ls.dg.map(g => `<li><b>${esc(g.un)}</b> ${esc(g.name)} · class ${esc(g.cls)}${g.sub ? ` (${esc(g.sub)})` : ""} · ${esc(g.net)} · <span class="mono">${esc(g.pos)}</span>${g.cao ? ' · <span class="tag">Cargo aircraft only</span>' : ""}${ls.erg?.[g.un] ? ` · ERG ${esc(ls.erg[g.un].erg)}` : ""}</li>`).join("")}</ul></section>` : ""}
  </div>
  <div class="ls-pane" data-lspane="manifest" ${S.lsTab === "manifest" && units ? "" : "hidden"}>
  ${units ? `<div class="ls-man"><div class="ls-table-wrap"><table class="ls-table"><thead><tr><th>Pos</th><th>Unit</th><th>AWB</th><th>Contents</th><th>SHC</th><th class="r">Pcs</th><th class="r">Weight</th></tr></thead><tbody>
    ${ls.positions.map(p => `<tr data-pos="${esc(p.pos)}"><td class="mono">${esc(p.pos)}</td><td class="mono">${esc(p.unit)}</td><td class="mono">${trackAwb(p.awb)}</td><td>${esc(p.contents)}</td><td>${p.shc.map(c => `<span class="shc${c === p.dg ? " dg" : ""}">${esc(c)}</span>`).join(" ")}</td><td class="r">${fmt(p.pieces)}</td><td class="r">${fmt(p.weight_lbs)}</td></tr>`).join("")}
    </tbody><tfoot><tr><td colspan="5">Total</td><td class="r">${fmt(ls.totals.pieces)}</td><td class="r">${fmt(ls.totals.weight_lbs)}</td></tr></tfoot></table></div></div>` : ""}
  </div>
  <div class="ls-pane" data-lspane="folder" ${S.lsTab === "folder" && units ? "" : "hidden"}>
  ${cargoFolderHTML(ls)}
  </div>
  <p class="muted ls-fine">Preliminary, for planning. Fuel is PAC's estimate; when you request the flight, the dispatch release keeps these units, positions and waybills and takes fuel and weights from your SimBrief OFP. Simulation paperwork, not an aircraft weight-and-balance approval.</p>`;
}
function wireTransferCargo(el, ls, m) {
  el.querySelectorAll("[data-transfer-id]").forEach(input => input.onchange = () => {
    const ids = [...el.querySelectorAll("[data-transfer-id]:checked")].map(x => x.dataset.transferId);
    const weight = ids.reduce((sum, id) => sum + Number(ls.transfer_options.find(x => x.id === id)?.gross_weight_lbs || 0), 0);
    const limit = Math.min(Number(ls.payload_requested || 0), Number(ls.limits.max_payload || 0));
    if (weight > limit) {
      input.checked = false;
      toast(`Transfer cargo cannot exceed this flight's ${fmt(limit)} lb payload plan.`);
      return;
    }
    S.cargoTransferIds[m.id] = ids;
    delete S.lsCache?.[lsKey(m)];
    loadLoadsheet(m);
  });
}
/* The cargo folder: the full air waybill, special handling, warehouse acceptance and tracking for each shipment */
const CF_KEYW = 24;
const cfLine = (k, v) => { const pad = " ".repeat(CF_KEYW); const parts = String(v ?? "-").split("\n"); return parts.map((x, i) => (i ? pad : (k + "").toUpperCase().padEnd(CF_KEYW)) + x).join("\n"); };
const cf2 = v => Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const cf1 = v => Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const CF_SHC = { GEN: "General cargo", HUM: "Human remains", PER: "Perishable", PIL: "Pharmaceuticals", COL: "Cool goods", PES: "Fish and seafood", PEF: "Flowers",
  ICE: "Dry ice", AVI: "Live animals", VAL: "Valuable cargo", AOG: "Aircraft on ground (parts)", HEA: "Heavy cargo (150 kg or more per piece)", BIG: "Outsize cargo",
  RLI: "Lithium-ion batteries", RCM: "Corrosive", RNG: "Non-flammable gas", RFL: "Flammable liquid", RMD: "Miscellaneous dangerous goods", CAO: "Cargo aircraft only",
  EAT: "Foodstuffs", CRT: "Controlled room temperature", MAL: "Mail", XPS: "Express", ELI: "Lithium-ion batteries in equipment", ELM: "Lithium metal batteries in equipment",
  SPX: "Special handling", FRO: "Frozen goods", PEM: "Meat", HUM_: "" };
const cfDims = a => a.dims.map(g => `${g.n} X ${g.l} X ${g.w} X ${g.h} CM`).join("\n");
function cfAwb(ls, s) {
  const a = s.awb_doc, o = ls.origin, de = ls.destination, sh = s.shc || [], dg = (ls.dg || []).filter(g => g.awb === s.awb);
  return [
    "AIR CARGO WAYBILL  /  CONTRACT OF CARRIAGE",
    "=".repeat(78),
    cfLine("Air waybill", s.awb), cfLine("Issuing carrier", `${a.carrier} (${a.code})`), cfLine("Issued", `${a.issued} AT ${a.issued_at}`),
    ...(a.charter_customer ? [cfLine("Charter customer", a.charter_customer)] : []),
    cfLine("Shipper", s.shipper.name.toUpperCase()), cfLine("Shipper address", a.shipper_addr),
    cfLine("Consignee", s.consignee.name.toUpperCase()), cfLine("Consignee address", a.consignee_addr),
    cfLine("Freight forwarder", (s.agent || "Direct from shipper").toUpperCase()), cfLine("Notify party", (s.notify || "Consignee").toUpperCase()),
    cfLine("Origin ground handler", a.origin_handler || "-"), cfLine("Destination handler", a.dest_handler || "-"),
    "",
    cfLine("Airport of departure", `${o.icao}  ${(o.city || o.name || "").toUpperCase()}`), cfLine("Airport of destination", `${de.icao}  ${(de.city || de.name || "").toUpperCase()}`),
    cfLine("Requested flight", ls.mission_id ? `${ls.mission_id} (ON REQUEST)` : "UNASSIGNED"),
    cfLine("Pieces / gross weight", `${s.pieces} / ${cf1(a.kg)} KG  (${fmt(s.weight_lbs)} LB)`), cfLine("Chargeable weight", `${cf1(a.chg_kg)} KG  (RATE CLASS ${a.rate_class})`),
    cfLine("Dimensions / volume", cfDims(a) + `\n${a.vol_m3.toFixed(3)} CBM  (VOLUMETRIC ${cf1(a.vol_kg)} KG AT 6,000 CM3/KG)`),
    cfLine("Rate / total", `USD ${cf2(a.rate)} PER KG / USD ${cf2(a.freight)}`),
    cfLine("Other charges", a.others.map(c => `${c.code}  ${c.what.padEnd(24)} USD ${cf2(c.amt).padStart(10)}`).join("\n")),
    cfLine("Total prepaid", `USD ${cf2(a.total)}`),
    "",
    cfLine("Nature and quantity", s.contents.toUpperCase()), cfLine("Customs description", a.hs_desc), cfLine("Harmonized code", a.hs || "NOT APPLICABLE (POSTAL)"),
    cfLine("Packaging", a.packaging), cfLine("Special handling", sh.join(" ") || "GEN"), cfLine("Temperature range", a.temp),
    cfLine("Dangerous goods", dg.length ? [...new Set(dg.map(g => `${g.un} ${g.name} CLASS ${g.cls}`.toUpperCase()))].join("\n") : "NOT DECLARED"),
    cfLine("Declared value carriage", a.dv_carriage), cfLine("Declared value customs", a.dv_customs),
    cfLine("Handling information", a.handling_info), cfLine("Units on board", (s.units || []).join(" ") || "-"),
  ].join("\n");
}
function cfHandling(ls, s) {
  const a = s.awb_doc, sh = s.shc || [];
  return [
    "CARGO ACCEPTANCE AND SPECIAL-HANDLING INSTRUCTIONS",
    "=".repeat(78),
    cfLine("Cargo material", s.contents.toUpperCase()), cfLine("Shipper", s.shipper.name.toUpperCase()), cfLine("Consignee", s.consignee.name.toUpperCase()),
    cfLine("Freight forwarder", (s.agent || "Direct").toUpperCase()), cfLine("Service", s.service),
    cfLine("Packaging", a.packaging), cfLine("Package dimensions", cfDims(a)),
    cfLine("Total volume", `${a.vol_m3.toFixed(3)} CBM`), cfLine("Gross / chargeable", `${cf1(a.kg)} / ${cf1(a.chg_kg)} KG`),
    cfLine("Commodity HS code", a.hs || "-"), cfLine("Temperature", a.temp),
    "",
    "SPECIAL HANDLING CODES",
    ...(sh.length ? sh : ["GEN"]).map(c => "  " + c.padEnd(6) + (CF_SHC[c] || "See handling information").toUpperCase()),
    "",
    "HANDLING INSTRUCTIONS",
    ...((s.handling || []).length ? s.handling : [a.handling_info]).map(h => "  - " + h.toUpperCase()),
    "",
    "WHY THIS SHIPMENT IS FLYING",
    "  " + (s.story || "-").toUpperCase(),
  ].join("\n");
}
function cfScreening(ls, s) {
  const a = s.awb_doc;
  return [
    "ORIGIN WAREHOUSE ACCEPTANCE / SECURITY RECORD",
    "=".repeat(78),
    cfLine("Air waybill", s.awb), cfLine("Route", `${ls.origin.icao} TO ${ls.destination.icao}`), cfLine("Accepted by", a.origin_handler || "-"),
    "",
    ...a.checks.map(c => `[X] ${c.at}  ${c.what}\n                   ${c.note}`),
    "",
    cfLine("Security method", `${a.screen.method}  ${a.screen.why}`), cfLine("Security status", `${a.screen.status}  (SECURE FOR CARGO AIRCRAFT ONLY)`),
    cfLine("E-CSD reference", a.screen.ecsd), cfLine("Screened", a.screen.at),
    ...(a.export ? [cfLine("Export reference", a.export)] : []),
    cfLine("Warehouse release", `${a.release_at}  ALL CHECKS SIGNED OFF`),
  ].join("\n");
}
function cfTracking(ls, s) {
  const a = s.awb_doc;
  return [
    `SHIPMENT TRACKING  /  AWB ${s.awb}  /  ${ls.origin.icao} TO ${ls.destination.icao}`,
    "=".repeat(78),
    "CODE  TIME          STATION  STATUS",
    ...a.track.map(t => `${t.code.padEnd(6)}${t.at.padEnd(14)}${t.where.padEnd(9)}${t.what}`),
    "",
    "PLANNED AGAINST THE SCHEDULE. CODES FOLLOW IATA CARGO-IMP:",
    "BKD BOOKED  RCS RECEIVED FROM SHIPPER  MAN MANIFESTED  DEP DEPARTED  ARR ARRIVED",
    "RCF RECEIVED FROM FLIGHT  TRS TRANSFERRED  NFD CONSIGNEE NOTIFIED  DLV DELIVERED",
  ].join("\n");
}
const CF_TABS = [["awb", "Air waybill", cfAwb], ["shc", "Special handling", cfHandling], ["scr", "Warehouse screening", cfScreening], ["trk", "Tracking", cfTracking]];
function cargoFolderHTML(ls) {
  const sh = (ls.shipments || []).filter(s => s.awb_doc);
  if (ls.ferry || !sh.length) return "";
  const i = Math.min(S.cfShip || 0, sh.length - 1), tab = S.cfTab || "awb", s = sh[i];
  const body = (CF_TABS.find(t => t[0] === tab) || CF_TABS[0])[2](ls, s);
  return `<div class="cf">
    <p class="muted ls-fine">The paperwork behind every shipment on this flight: the contract of carriage, how to handle it, what the warehouse checked before it reached your aircraft, and where it is now. Shippers and consignees are real companies that fit the cargo and the route; the shipments, values and references are fictional, for flight simulation, with no affiliation implied.</p>
    <div class="cf-bar"><label class="cf-pick">Air waybill <select data-cf-ship>${sh.map((x, j) => `<option value="${j}" ${j === i ? "selected" : ""}>${esc(x.awb)} · ${esc(x.shipper.name)} → ${esc(x.consignee.name)}</option>`).join("")}</select></label>
      <span class="cf-sum">${/^\d{3}-\d{8}$/.test(s.awb || "") ? `<a href="/track/${s.awb}" target="_blank" rel="noopener">Track ${esc(s.awb)}</a> · ` : ""}${s.pieces} pcs · ${cf1(s.awb_doc.kg)} kg · ${esc((s.shc || []).join(" ") || "GEN")} · ${esc(s.service)}</span></div>
    <div class="cf-tabs" role="tablist">${CF_TABS.map(([k, l]) => `<button type="button" role="tab" data-cf-tab="${k}" aria-selected="${k === tab}">${l}</button>`).join("")}</div>
    <pre class="cf-doc" tabindex="0">${esc(body)}</pre></div>`;
}
function wireCargoFolder(el, ls) {
  const redraw = () => { const old = el.querySelector(".cf"); if (!old) return; const t = document.createElement("div"); t.innerHTML = cargoFolderHTML(ls); old.replaceWith(t.firstElementChild); wireCargoFolder(el, ls); };
  el.querySelectorAll("[data-cf-tab]").forEach(b => b.onclick = () => { S.cfTab = b.dataset.cfTab; redraw(); });
  const sel = el.querySelector("[data-cf-ship]"); if (sel) sel.onchange = () => { S.cfShip = +sel.value; redraw(); };
}
/* After the OFP comes in: how SimBrief's plan compares with the preliminary load sheet */
function planVsLoad(m) {
  const el = $("#planVsLoad"), ls = (S.lsCache || {})[lsKey(m)], o = S.ofp;
  if (ls && !ls.ferry && $("#sbCargo")) $("#sbCargo").innerHTML = `<b>${fmt(ls.totals.weight_lbs)} lb</b> of cargo from your load sheet`;
  if (!el || !ls || !o) return;
  const rows = [["Payload", ls.loadsheet.payload, o.payload_lbs], ["Zero fuel weight", ls.loadsheet.zfw, o.zfw_lbs], ["Block fuel", ls.fuel.block, o.block_fuel_lbs], ["Take-off weight", ls.loadsheet.tow, o.tow_lbs]];
  el.innerHTML = `<div class="ls-vs"><b>Load sheet vs. your OFP</b><table><thead><tr><th></th><th class="r">Load sheet</th><th class="r">OFP</th><th class="r">Diff</th></tr></thead><tbody>${rows.map(([k, a, b]) => {
    const dlt = b == null ? null : b - a, big = dlt != null && k === "Payload" && Math.abs(dlt) > 500;
    return `<tr class="${big ? "warn" : ""}"><td>${k}</td><td class="r">${fmt(a)}</td><td class="r">${fmt(b)}</td><td class="r">${dlt == null ? "–" : (dlt > 0 ? "+" : "") + fmt(dlt)}</td></tr>`; }).join("")}</tbody></table>
    <small class="muted">${Math.abs((o.payload_lbs || 0) - ls.loadsheet.payload) > 500 ? "Your OFP payload differs from the load sheet: the release re-weighs the units to match SimBrief." : "The release takes SimBrief's fuel and weights."}</small></div>`;
}
async function loadDossierEcon(m) {
  const el = $("#econPanel"), chip = $("#payChip");
  if (!el && !chip) return;
  const setChip = (v, t) => { const c = $("#payChip"); if (c) { c.querySelector("b").textContent = v; if (t) c.title = t; } };
  if (m.training) { if (el) el.innerHTML = "<p>Company-funded checkride: $0 cost to you. Accepted reports earn standard flight pay and applicable skill or gear bonuses; no profit share, reward points or commercial cargo credit.</p>"; setChip("Checkride", "Company-funded: standard flight pay if accepted"); return; }
  const ac = m.charter ? m.aircraft[0] : S.aircraft, ofp = S.ofp && !S.ofpErrors?.length ? S.ofp : null;
  const key = `${m.id}|${ac}|${ofp?.request_id || ""}`;
  try {
    S.econCache ||= {};
    const e = S.econCache[key] || await api("/api/economics/estimate", { method: "POST", body: { mission_id: m.id, charter: m.charter, aircraft: ac, ofp } });
    S.econCache[key] = e;
    if (S.selected?.id !== m.id) return;
    const me = S.me || await loadMe();
    const hrs = (e.block_min || m.target_block_min || 60) / 60;
    let payLine = "", total = null;
    if (me && m.contract) {
      const rate = me.pay_rate * (m.contract_rate_mult || 1.5), fly = hrs * rate; total = fly + (m.contract_bonus || 0);
      payLine = `<div class="notice" style="border-color:#1f9d55;background:var(--ok-wash);margin-top:10px"><b>Your pay:</b> ${money(fly, true)} (${hrs.toFixed(1)} h at $${Math.round(rate)}/h, ${m.contract_rate_mult || 1.5}× your rate) + ${money(m.contract_bonus || 0, true)} shortage bonus = <b>${money(total, true)}</b>, plus up to $475 in skill bonuses. Paid into your wallet when the PIREP is accepted.</div>`;
    } else if (me && m.category !== "Ferry") {
      const fly = hrs * me.pay_rate, share = Math.max(0, e.profit) * me.profit_share_pct / 100; total = fly + share;
      payLine = `<div class="notice" style="border-color:#1f9d55;background:var(--ok-wash);margin-top:10px"><b>Your pay:</b> ${money(fly, true)} (${hrs.toFixed(1)} h at $${me.pay_rate}/h as ${esc(me.rank)}) + ${money(share, true)} profit share (${me.profit_share_pct}% of PAC's profit) = <b>${money(total, true)}</b>, plus up to $475 in skill bonuses for flying it well. Paid into your wallet when the PIREP is accepted.</div>`;
    } else if (me) {
      total = hrs * me.pay_rate + (m.ferry_bonus || 0);
      payLine = `<div class="notice" style="border-color:#1f9d55;background:var(--ok-wash);margin-top:10px"><b>Your pay:</b> ${money(hrs * me.pay_rate, true)} (${hrs.toFixed(1)} h at $${me.pay_rate}/h)${m.ferry_bonus ? ` + ${money(m.ferry_bonus, true)} ferry bonus` : ""}. Ferry flights earn PAC nothing, but you're still paid.</div>`;
    }
    setChip(total == null ? "–" : money(total, true), "Before skill bonuses (up to $475). Details under PAC's economics on the Briefing step.");
    const box = $("#econPanel");
    const zq = zoneFor(m);
    if (zq && zq.level === "caution" && total != null) payLine = payLine.replace("</div>", ` <b>+ ${zq.pct}% hazard pay</b> for the caution area.</div>`);
    if (zq?.level === "restricted") setChip("$0 · not credited", "Restricted airspace: this flight is rejected automatically when filed, so it pays nothing.");
    else if (zq?.level === "caution" && total != null) setChip(money(total + hrs * (me?.pay_rate || 0) * zq.pct / 100, true), `Includes ${zq.pct}% hazard pay. Skill bonuses come on top.`);
    if (box) box.innerHTML = payLine + econBox(e, `${S.fleet[ac]?.icao || ""} plan`, ofp ? "Based on your OFP" : "Based on typical fuel burn and the mission load");
  } catch (err) { if ($("#econPanel")) $("#econPanel").innerHTML = `<span class="muted" style="font-size:13px">${esc(err.message)}</span>`; setChip("–"); }
}
function defaultAirframe(m, ac) {
  if(m.training)return m.training.reg||null;
  if (m.contract) return null;
  if (m.fixed_airframe) return m.fixed_airframe;
  const here = (S.airframes || []).filter(a => a.type === ac && a.status === "Available" && a.location === m.origin.icao);
  if (here.length) return here[0].reg;
  if (S.settings.enforce_airframes === false) return (S.airframes || []).find(a => a.type === ac && a.status === "Available")?.reg || null;
  return null;
}
function airframePicker(m, ac) {
  if(m.training)return `<p class="notice">${m.training.mode==='dedicated'?'Dedicated training aircraft · no operational tail reserved':'Training aircraft: '+esc(m.training.reg)} · $0 training cost</p>`;
  if (m.fixed_airframe) {
    const a = (S.airframes || []).find(x => x.reg === m.fixed_airframe);
    return `<div class="af-pick"><label class="sel"><input type="radio" name="af" value="${m.fixed_airframe}" checked><b style="font-family:var(--mono)">${m.fixed_airframe}</b><span>at ${esc(a?.location || m.origin.icao)} · this ferry is for this aircraft</span></label></div>`;
  }
  const list = (S.airframes || []).filter(a => a.type === ac);
  if (!list.length) return `<div class="notice">There are no ${esc(S.fleet[ac].name)} airframes in the fleet. ${S.me?.staff ? 'Add one in Staff › Airframes.' : 'Ask Dispatch to make an aircraft available.'}</div>`;
  const strict = S.settings.enforce_airframes !== false, dep = m.origin.icao;
  const away = a => a.lat == null ? 99999 : gcnm(a, m.origin);
  const sorted = [...list].sort((a, b) => (b.location === dep) - (a.location === dep) || (b.status === "Available") - (a.status === "Available") || away(a) - away(b));
  const rows = sorted.map(a => {
    const here = a.location === dep, ok = a.status === "Available" && (here || !strict);
    const right = a.status !== "Available" ? `<span class="tag ${a.status === "Booked" ? "dark" : "amber"}">${esc(a.status === "Booked" ? "Reserved" : a.status)}</span><span class="journey-reason">${esc(reservationSummary(a))}. ${a.status === "Booked" ? "Reserved for another flight. Choose an available tail or check again later." : "This tail is unavailable. Choose another or contact Dispatch."}</span>`
      : here ? `<span class="tag green">At ${dep}</span>` : strict ? `<button type="button" class="btn ghost small" data-ferry="${a.reg}">Fly it to ${dep}</button>${S.settings.shop_enabled === false ? `<span class="journey-reason">Aircraft delivery is unavailable while the PAC shop is closed.</span>` : S.me?.location?.icao === dep ? ` <button type="button" class="btn ghost small" data-repo="${a.reg}" title="Paid aircraft delivery to your PAC location">Have it ferried</button>` : `<span class="journey-reason">Have it ferried: travel to ${esc(dep)} first. Your PAC location is ${esc(S.me?.location?.icao || 'not loaded')}.</span>`}` : `<span class="tag grey">Moves on booking</span>`;
    return `<label class="${ok ? "" : "off"}"><input type="radio" name="af" value="${a.reg}" ${S.airframe === a.reg ? "checked" : ""} ${ok ? "" : "disabled"}><b>${a.reg}</b>${a.name ? `<i class="af-name">“${esc(a.name)}”</i>` : ""}<span>at ${a.location}${!here && a.lat != null ? ` · ${fmt(away(a))} nm away` : ""} · ${esch(a.hours || 0)} h${(a.open_items || []).length ? `<span class="af-mx" title="${esc(a.open_items.map(i => `ATA ${String(i.ata).padStart(2, "0")} ${i.description}`).join("; "))}">${a.open_items.length} deferred ${a.open_items.length === 1 ? "item" : "items"}</span>` : ""}</span>${right}</label>`;
  }).join("");
  const none = strict && !list.some(a => a.location === dep && a.status === "Available");
  return `<div class="af-pick" role="radiogroup" aria-label="Airframe">${rows}</div>${none ? `<p class="muted" style="font-size:13px;margin:0 0 10px">${m.type_checkride ? `No ${esc(S.fleet[ac].icao)} is available at ${dep}. <button type="button" class="btn ghost small" onclick="show('career/qualifications')">Free checkride travel</button>` : `No ${esc(S.fleet[ac].icao)} is available at ${dep}. Ferry one in, pick another type, or ask staff to reposition one.`}</p>` : ""}`;
}
async function ferryAirframe(reg, m) {
  const a = S.airframes.find(x => x.reg === reg);
  try {
    const r = await api("/api/charter/quote", { method: "POST", body: { origin: a.location, destination: m.origin.icao, aircraft: a.type, payload_lbs: 0, cargo: "Ferry flight (no cargo)", priority: "Standard" } });
    S.charterSpec = { origin: a.location, destination: m.origin.icao, aircraft: a.type, payload_lbs: 0, cargo: "Ferry flight (no cargo)", priority: "Standard", flight_number: r.mission.charter.flight_number, _o: null, _d: null };
    S.charterMission = r.mission; S.charterWarnings = r.warnings; S.board = "charter"; S.selected = null; S.pendingAirframe = reg;
    renderMissions(); selectMission(r.mission.id);
    toast(`Ferry flight built: ${reg} from ${a.location} to ${m.origin.icao}.`);
  } catch (e) { toast(e.message); }
}
const wxCard = (label, icao, w) => {
  const m = w?.metar;
  return `<div class="wx-card"><div class="wx-top"><span><b>${esc(icao)}</b> <small>${label}</small></span><span class="fcat ${m ? m.category : "NA"}">${m ? m.category : "NO DATA"}</span></div>
    ${m ? `<div class="wx-sum">${esc(m.summary)}</div><div class="raw">${esc(m.raw)}</div>` : `<div class="wx-sum muted">No current METAR for this airport.</div>`}
    ${w?.taf ? `<details><summary>TAF</summary><div>${esc(w.taf.lines.join("\n"))}</div></details>` : ""}</div>`;
};
/* Flight planning helper: cruise level, fuel estimate, likely runways and an alternate */
async function loadPlanHelper(m) {
  const el = $("#planPanel"); if (!el) return;
  const ac = S.aircraft || m.aircraft[0], key = `${m.id}|${ac}`;
  S.planHelp ||= {};
  try {
    const h = S.planHelp[key] || await api("/api/plan/helper", { method: "POST", body: { mission_id: m.id, charter: m.charter ? S.charterSpec : undefined, aircraft: ac } });
    S.planHelp[key] = h;
    if ($("#planPanel") !== el) return;
    const f = h.fuel, rw = (label, r) => `<div class="ph-rwy"><span>${label} ${esc(r.icao)}</span><b>${r.runway ? "Rwy " + esc(r.runway) : "–"}</b>
        <small>${r.headwind_kt != null ? `${r.headwind_kt >= 0 ? r.headwind_kt + " kt headwind" : Math.abs(r.headwind_kt) + " kt TAILWIND"} · ${r.crosswind_kt} kt crosswind from the ${r.cross_from}${r.gust_kt ? ` · gusting ${r.gust_kt}` : ""}` : esc(r.note || "")}</small>
        ${r.wind ? `<small>Wind ${esc(r.wind)}</small>` : ""}</div>`;
    el.innerHTML = `<div class="plan-help">
      <div class="ph-row"><div><span>Cruise</span><b>FL${String(h.cruise_fl).padStart(3, "0")}</b></div><div><span>Distance</span><b>${fmt(h.distance_nm)} nm</b></div>
        <div><span>Block time</span><b>${Math.floor(f.est_block_min / 60)}h ${String(f.est_block_min % 60).padStart(2, "0")}m</b></div>
        <div><span>Alternate</span><b>${h.alternate ? esc(h.alternate.icao) : "–"}</b>${h.alternate ? `<small>${esc(h.alternate.city || "")} · ${h.alternate.distance_nm} nm</small>` : ""}</div></div>
      <p class="muted ph-why">${esc(h.cruise_why)}.</p>
      <div class="ph-fuel"><span>Fuel estimate (lb)</span>
        <div>Trip <b>${fmt(f.trip)}</b></div><div>Contingency 5% <b>${fmt(f.contingency)}</b></div><div>Alternate <b>${fmt(f.alternate)}</b></div>
        <div>Final reserve 30 min <b>${fmt(f.final_reserve)}</b></div><div>Taxi <b>${fmt(f.taxi)}</b></div><div class="tot">Block fuel <b>${fmt(f.block)}</b></div></div>
      <div class="ph-rwys">${rw("Departure", h.departure)}${rw("Arrival", h.arrival)}</div>
      <label class="ph-use"><input type="checkbox" id="usePlan" ${S.usePlanHelp !== false ? "checked" : ""}> Use the cruise level and alternate in SimBrief</label>
      <p class="muted" style="margin:0;font-size:12px">Estimates to plan with. SimBrief works out the real numbers from winds, weights and the route; runways follow the current wind${h.weather_ok ? "" : " (no live weather right now)"}, but ATC decides.</p></div>`;
    $("#usePlan").onchange = e => { S.usePlanHelp = e.target.checked; const sb = $("#sbPlan"); if (sb) sb.href = simbriefUrl(m, ac); };
    const sb = $("#sbPlan"); if (sb) sb.href = simbriefUrl(m, ac);
  } catch (e) { el.innerHTML = `<span class="muted" style="font-size:13px">${esc(e.message)}</span>`; }
}
async function loadDossierWx(m) {
  const el = $("#wxPanel"); if (!el) return;
  const alt = S.ofp?.alternate?.icao || (S.booking?.mission?.id === m.id ? S.booking.ofp?.alternate?.icao : null);
  const ids = [m.origin.icao, m.destination.icao, alt].filter(Boolean);
  const key = ids.join(",");
  try {
    const w = (S.wxCache?.[key] && Date.now() - S.wxCache[key].t < 300000) ? S.wxCache[key].d : await api("/api/weather?taf=1&ids=" + key);
    (S.wxCache ||= {})[key] = { t: Date.now(), d: w };
    if ($("#wxPanel") !== el) return;
    el.innerHTML = wxCard("Departure", m.origin.icao, w[m.origin.icao]) + wxCard("Destination", m.destination.icao, w[m.destination.icao]) + (alt ? wxCard("Alternate", alt, w[alt]) : "");
  } catch (e) { el.innerHTML = `<span class="muted" style="font-size:13px">${esc(e.message)}</span>`; }
}
function fleetOrder(m) {
  if (m.tour || m.rotation || m.types_only || m.category === "Checkride") return m.aircraft.filter(a => S.fleet[a] && !S.fleet[a].retired);
  const all = Object.keys(S.fleet).filter(a => !S.fleet[a].retired);
  return [...m.aircraft.filter(a => S.fleet[a]), ...all.filter(a => !m.aircraft.includes(a))];
}
function capacityNote(m, ac) {
  const f = S.fleet[ac];
  if (!f) return "";
  if (f.max_payload_lbs < m.payload_lbs)
    return `<div class="notice" style="margin-bottom:10px">The ${esc(f.name)} carries up to ${fmt(f.max_payload_lbs)} lb. You'll deliver a partial load of the ${fmt(m.payload_lbs)} lb consignment.</div>`;
  if (!m.aircraft.includes(ac))
    return `<div class="notice" style="margin-bottom:10px">Not a recommended type for this mission. Check runway length and performance at ${m.origin.icao} and ${m.destination.icao} before you plan.</div>`;
  return "";
}
/* Navigraph Charts can load a SimBrief plan straight in (route, procedures, charts), as other VAs offer. */
function navigraphUrl(ofp) {
  return ofp?.request_id ? `https://charts.navigraph.com/flights/simbrief-instant-import?requestId=${encodeURIComponent(ofp.request_id)}` : null;
}
function navigraphBtn(ofp, cls = "btn ghost") {
  const u = navigraphUrl(ofp);
  return u ? `<a class="${cls} navigraph-btn" href="${u}" target="_blank" rel="noopener" title="Opens this SimBrief plan in Navigraph Charts">🗺️ Navigraph Charts</a>`
    : `<a class="${cls} navigraph-btn" href="https://charts.navigraph.com/" target="_blank" rel="noopener" title="Import your SimBrief plan into PAC to open this flight in Navigraph straight away">🗺️ Navigraph Charts</a>`;
}
function ofpCard() {
  if (!S.ofp) return "";
  const o = S.ofp;
  return `<div class="ofp-card" style="margin-top:10px">
    ${S.ofpErrors.map(e => `<div class="notice err" style="margin-bottom:6px">${esc(e)}</div>`).join("")}
    ${S.ofpWarnings.map(e => `<div class="notice" style="margin-bottom:6px">${esc(e)}</div>`).join("")}
    <b>${esc((o.airline||"") + (o.flight_number||""))}</b> ${o.origin?.icao}/${esc(o.origin?.runway)} to ${o.destination?.icao}/${esc(o.destination?.runway)} ${o.alternate ? "· alternate " + o.alternate.icao : ""}
    <div class="ofp-grid num">
      <div><span>Aircraft</span>${esc(o.aircraft_icao)} ${esc(o.registration)}</div>
      <div><span>Cruise</span>FL${Math.round(o.cruise_ft/100)}</div>
      <div><span>Block time</span>${hm(o.est_block_min)}</div>
      <div><span>Block fuel</span>${fmt(o.block_fuel_lbs)} lb</div>
      <div><span>Trip fuel</span>${fmt(o.trip_fuel_lbs)} lb</div>
      <div><span>Payload</span>${fmt(o.payload_lbs)} lb</div>
      <div><span>ZFW</span>${fmt(o.zfw_lbs)} lb</div>
      <div><span>TOW</span>${fmt(o.tow_lbs)} lb</div>
      <div><span>Distance</span>${fmt(o.distance_nm)} nm</div>
    </div>
    <div class="route-str">${esc(o.route)}</div>
    ${navigraphUrl(o) ? `<div class="row" style="margin-top:8px">${navigraphBtn(o, "btn ghost small")}<span class="muted" style="font-size:13px">Route, procedures and charts for this plan, in Navigraph.</span></div>` : ""}</div>`;
}
/* Automatic OFP: after "Open SimBrief", watch for the new plan and import it the moment it's generated */
function stopDossierWatch() { if (S.dWatch) clearTimeout(S.dWatch.timer); S.dWatch = null; }
function startDossierWatch() {
  if (!(S.settings.simbrief_username || S.settings.simbrief_userid) || !S.selected) return;
  stopDossierWatch();
  const w = S.dWatch = { since: Date.now() / 1000 - 60, sel: S.selected.id, until: Date.now() + 20 * 60e3, timer: null };
  const tick = async () => {
    if (S.dWatch !== w) return;
    if (S.selected?.id !== w.sel || Date.now() > w.until || S.booking || $("#view-missions").hidden) { stopDossierWatch(); if (!$("#view-missions").hidden) renderDossier(); return; }
    try {
      const r = await api("/api/ofp/import", { method: "POST", body: { mission_id: S.selected.id, charter: S.selected.charter, aircraft: S.aircraft } });
      const gen = Number(r.ofp?.generated || 0);
      if (S.dWatch === w && r.ofp && (!gen || gen >= w.since) && r.ofp.request_id !== S.ofp?.request_id) {
        const sw = ofpAircraft(r); S.ofp = r.ofp; S.ofpErrors = r.errors; S.ofpWarnings = r.warnings; stopDossierWatch(); renderDossier();
        toast(r.errors.length ? "Your SimBrief plan doesn't match this flight: " + r.errors[0] : sw ? `Your SimBrief plan arrived. Switched to the ${S.fleet[sw].name} to match it.` : "Your SimBrief plan arrived and was imported.");
        return;
      }
    } catch (e) { /* no plan yet: keep watching */ }
    if (S.dWatch === w) w.timer = setTimeout(tick, 15000);
  };
  w.timer = setTimeout(tick, 12000);
}
function ofpAircraft(r) {   // PAC switched to the type the SimBrief plan is for (one this flight allows): follow it
  if (!r.aircraft || r.aircraft === S.aircraft || !S.fleet[r.aircraft] || S.selected?.charter) return null;
  S.aircraft = r.aircraft; S.airframe = defaultAirframe(S.selected, r.aircraft); return r.aircraft;
}
/* One-click OFP through the SimBrief API: PAC's server signs the request (the key never reaches the browser), SimBrief's
   own window generates the plan, and when that window closes the plan is fetched by its id. */
function simbriefGenStop(closeWin) {
  const g = S.sbGen; if (!g) return;
  clearInterval(g.timer); if (closeWin && g.win && !g.win.closed) g.win.close();
  S.sbGen = null; if (S.selected) renderDossier();
}
async function simbriefGenerate(m) {
  simbriefGenStop(true);
  const win = window.open("about:blank", "SBworker", "width=600,height=315");   // opened on the click, so pop-up blockers allow it
  if (!win) { toast("Allow pop-ups for this site to generate the OFP, or use Open SimBrief yourself."); return; }
  const ac = m.charter ? m.aircraft[0] : S.aircraft;
  const q = new URL(simbriefUrl(m, ac)).searchParams;
  const ts = Math.round(Date.now() / 1000), out = (location.origin + "/").replace("http://", "");
  let sig;
  try { sig = await api("/api/simbrief/apicode", { method: "POST", body: { orig: q.get("orig"), dest: q.get("dest"), type: q.get("type"), timestamp: ts, outputpage: out } }); }
  catch (e) { win.close(); toast(e.message); return; }
  const f = document.createElement("form");
  f.method = "get"; f.action = "https://www.simbrief.com/ofp/ofp.loader.api.php"; f.target = "SBworker"; f.style.display = "none";
  const add = (k, v) => { const i = document.createElement("input"); i.type = "hidden"; i.name = k; i.value = v; f.append(i); };
  q.forEach((v, k) => add(k, v));
  add("apicode", sig.apicode); add("outputpage", out); add("timestamp", String(ts));
  document.body.append(f); f.submit(); f.remove();
  const g = S.sbGen = { win, id: sig.ofp_id, sel: m.id, started: Date.now(), timer: null };
  g.timer = setInterval(() => {
    if (S.sbGen !== g) return clearInterval(g.timer);
    if (Date.now() - g.started > 15 * 60e3) { simbriefGenStop(true); toast("SimBrief took too long. Try again, or use Open SimBrief yourself."); return; }
    if (!win.closed) return;
    clearInterval(g.timer); S.sbGen = null;
    if (S.selected?.id === g.sel) importGenerated(g.id, 0); else renderDossier();
  }, 600);
  S.planned = true; renderDossier();
}
async function importGenerated(id, tries) {   // the window can close a moment before SimBrief has saved the plan
  try {
    const r = await api("/api/ofp/import", { method: "POST", body: { mission_id: S.selected.id, charter: S.selected.charter, aircraft: S.aircraft, ofp_id: id } });
    const sw = ofpAircraft(r); S.ofp = r.ofp; S.ofpErrors = r.errors; S.ofpWarnings = r.warnings; S.planned = true;
    renderDossier();
    toast(r.errors.length ? "Your SimBrief plan doesn't match this flight: " + r.errors[0] : sw ? `OFP generated and imported. Switched to the ${S.fleet[sw].name} to match it.` : "OFP generated and imported.");
  } catch (e) {
    if (tries < 3 && /hasn't finished/.test(e.message)) { setTimeout(() => importGenerated(id, tries + 1), 2500); return; }
    renderDossier(); toast(e.message);
  }
}
async function importOfp(raw, ofpId) {
  try {
    const r = await api("/api/ofp/import", { method: "POST", body: { mission_id: S.selected.id, charter: S.selected.charter, aircraft: S.aircraft, raw, ofp_id: ofpId } });
    const sw = ofpAircraft(r); S.ofp = r.ofp; S.ofpErrors = r.errors; S.ofpWarnings = r.warnings; S.planned = true;
    renderDossier();
    toast(r.errors.length ? "Your SimBrief plan doesn't match this flight: " + r.errors[0] : sw ? `OFP imported. Switched to the ${S.fleet[sw].name} to match your plan.` : "OFP imported.");
  } catch (e) { toast(e.message); }
}
async function requestMission(ofp, zoneAck = false) {
  try {
    const seed = (S.lsCache || {})[lsKey(S.selected)]?.seed;   // the preliminary load sheet becomes the release's load
    try {
      S.booking = await api("/api/booking", { method: "POST", body: { mission_id: S.selected.id, charter: S.selected.charter, aircraft: S.selected.charter ? S.selected.aircraft[0] : S.aircraft, ofp, airframe: S.airframe, manifest_seed: seed, zone_ack: zoneAck, cargo_transfer_ids: S.cargoTransferIds?.[S.selected.id] || [] } });
    } catch (e) {
      if (e.data?.needs_zone_ack) return confirmZone(e.data.zone, () => requestMission(ofp, true));
      throw e;
    }
    paintBid();
    refreshCore();
    toast(`${S.booking.flight_number} requested. Review and sign your dispatch release before starting ACARS.`);
    show("acars");
  } catch (e) { toast(e.message); }
}

function confirmZone(z, go) {
  const dlg = $("#zoneDlg");
  $("#zoneTitle").textContent = z.level === "restricted" ? "Restricted airspace" : "Caution area";
  $("#zoneBody").innerHTML = `${zoneNotice(z)}
    <label class="switch-row" style="margin:0"><input type="checkbox" id="zoneAck"><span>${z.level === "restricted"
      ? (z.restricted_airport ? "I understand this flight isn't authorized and won't be credited." : "I understand staff review this flight, and it's only credited if they accept it. I'll plan around the restricted airspace.")
      : "I understand the risks of flying into a caution area."}</span></label>
    <div class="row"><button class="btn" id="zoneGo" disabled>${z.level === "restricted" ? "Request anyway" : "Request flight"}</button><button class="btn ghost" data-close>Cancel</button></div>`;
  $("#zoneAck").onchange = e => { $("#zoneGo").disabled = !e.target.checked; };
  $("#zoneGo").onclick = () => { dlg.close(); go(); };
  dlg.querySelectorAll("[data-close]").forEach(b => b.onclick = () => dlg.close());
  if (!dlg.open) dlg.showModal();
}

/* ---------------- ACARS ---------------- */
const RAIL = ["PREFLIGHT","PUSHBACK","TAXI_OUT","TAKEOFF","INITIAL_CLIMB","CLIMB","CRUISE","DESCENT","APPROACH","LANDING","TAXI_IN","ARRIVED"];
function phaseName(k) { return (S.phases.find(p => p[0] === k) || [k, k])[1]; }

function renderAcars() {
  const a = $("#acars"), b = S.booking;
  if (!b) {
    if (S.map) { S.map.remove(); S.map = null; }
    a.innerHTML = `<div class="empty-acars"><h2>No mission loaded</h2><p>Request a mission from the board. It will appear here, ready to track from pushback to on-block.</p><button class="btn" onclick="show('missions')">Go to the mission board</button></div>`;
    $("#pirepPanel").innerHTML = ""; return;
  }
  if ($("#acarsReady")) return; // already built, poll() updates it
  const m = b.mission, o = b.ofp;
  a.innerHTML = `<div id="acarsReady">
    <div id="releasePreflight">${paperNote(b)}</div>
    <p class="muted" style="font-size:13px;margin:6px 0 0">🗒️ Radio cheat sheet is ready — <a id="radioReady" target="_blank" rel="noopener">download for this flight</a>. Gate to gate, prefilled with your callsign, airports and runways.</p>
    <div class="strip">
      <div><div class="fn">${esc(b.flight_number)}</div></div>
      <div class="rt"><b>${m.origin.icao}</b> to <b>${m.destination.icao}</b>${o?.alternate ? ` · alternate ${o.alternate.icao}` : ""}<br>${esc(S.fleet[b.aircraft].name)}${b.airframe ? " · " + esc(b.airframe) : b.partner_reg ? " · " + esc(b.partner_reg) : o?.registration ? " · " + esc(o.registration) : ""} · ${fmt(o?.payload_lbs || Math.min(m.payload_lbs, S.fleet[b.aircraft].max_payload_lbs))} lb ${esc(m.category.toLowerCase())} cargo</div>
      <div class="controls">
        <span class="conn" id="conn"><i></i><span>Not tracking</span></span>
        <a class="btn ghost" href="/dispatch" target="_blank" rel="noopener" id="dispatchBtn">${needsSignature(b) ? "Review and sign paperwork" : "Dispatch release"}</a>
        <a class="btn ghost" id="unicomBtn" target="_blank" rel="noopener" title="Ready-to-send Unicom calls for this flight, for when no ATC is online">📻 Unicom calls</a>
        <a class="btn ghost" id="radioBtn" target="_blank" rel="noopener" title="Full gate-to-gate ATC radio cheat sheet, filled for this flight">🗒️ Radio cheat sheet</a>
        ${navigraphBtn(b.ofp)}
        <a class="btn" id="openApp" href="${appLink(b)}" title="Opens PAC ACARS on this PC with this flight loaded">Open in PAC ACARS</a>
        <button class="btn ghost" id="cancelBtn">Cancel mission</button>
      </div>
    </div>
    <div class="rail" id="rail"></div>
    <div class="acars-grid">
      <div class="left">
        <div class="readouts" id="readouts"></div>
        <div id="map"></div>
      </div>
      <div class="right">
        <div class="oooi" id="oooi"></div>
        <div class="log-head"><span>ACARS messages</span><span id="elapsed" class="num"></span></div>
        <div class="log" id="log" aria-live="polite"></div>
        <div class="hint" id="hint"></div>
      </div>
    </div></div>`;
  (function () {
    const ub = $("#unicomBtn"); if (!ub) return;
    const q = new URLSearchParams();
    const cs = (o && o.callsign) || b.flight_number || "";
    if (cs) q.set("cs", cs);
    if (m.origin?.icao) q.set("dep", m.origin.icao);
    if (m.destination?.icao) q.set("arr", m.destination.icao);
    if (o?.cruise_ft) q.set("crz", "FL" + String(Math.round(o.cruise_ft / 100)).padStart(3, "0"));
    ub.href = "/unicom/flight?" + q.toString();
    // Radio cheat sheet: same flight data, with the spoken callsign built from the filing code and telephony word.
    const rq = new URLSearchParams();
    const digits = String(b.flight_number || "").replace(/\D/g, "");
    const op = (m && m.operator) || {};
    const code = op.code || (o && o.airline) || "PGI";                 // filing code, e.g. PGI (or a partner's)
    const telRaw = op.callsign || "PAGANI";                            // spoken airline name: a partner's, else PAC's
    const tel = telRaw === telRaw.toUpperCase() ? telRaw.charAt(0) + telRaw.slice(1).toLowerCase() : telRaw;
    if (code && digits) rq.set("fn", code + digits);
    rq.set("callword", tel + (digits ? " " + digits : ""));
    if (m.origin?.icao) rq.set("dep", m.origin.icao);
    if (m.destination?.icao) rq.set("arr", m.destination.icao);
    const rurl = "/radio/flight?" + rq.toString();
    const rb = $("#radioBtn"); if (rb) rb.href = rurl;
    const rr = $("#radioReady"); if (rr) rr.href = rurl;
  })();
  $("#openApp").onclick = () => {
    setTimeout(async () => {
      const app = await checkApp();
      if (!app) toast("PAC ACARS didn't open. Start it once yourself (the installed app, or start_acars.bat) so Windows learns the link, then press Open in PAC ACARS again.", 9000);
    }, 5000);
  };
  $("#cancelBtn").onclick = cancelMission;
  checkApp();
  initMap();
  paintStatus(S.status || {});
}
/* The PAC ACARS app does the tracking. The website opens it with the flight loaded (pacacars:// links,
   registered by the app and its installer) and follows the flight live. */
const APP_PING = "http://127.0.0.1:5070/api/ping";
function appLink(b) {
  const sim = (S.fleet[b.aircraft]?.sim || "MSFS").includes("X-Plane") ? "X-Plane" : "MSFS";
  return `pacacars://open?flight=${encodeURIComponent(b.flight_number)}&sim=${encodeURIComponent(sim)}`;
}
async function checkApp() {
  let app = null;
  try {
    const ctl = new AbortController(); setTimeout(() => ctl.abort(), 1500);
    app = await fetch(APP_PING, { signal: ctl.signal }).then(r => r.json());
  } catch (e) { app = null; }
  S.appInfo = app || false;
  clearTimeout(S.appTimer);
  if (!$("#view-acars").hidden) S.appTimer = setTimeout(checkApp, 10000);
  return app;
}

const HAS_MAP = typeof L !== "undefined";
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/";
const esriAttr = "Tiles &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors";
const MAP_STYLES = {
  dark:      { label: "Dark", layers: [[ESRI + "Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", 16], [ESRI + "Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}", 16]], attr: esriAttr },
  light:     { label: "Light", layers: [[ESRI + "Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", 16], [ESRI + "Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}", 16]], attr: esriAttr },
  street:    { label: "Street", layers: [["https://tile.openstreetmap.org/{z}/{x}/{y}.png", 19]], attr: "&copy; OpenStreetMap contributors" },
  satellite: { label: "Satellite", layers: [[ESRI + "World_Imagery/MapServer/tile/{z}/{y}/{x}", 18], [ESRI + "Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", 18]], attr: "Imagery &copy; Esri, Maxar, Earthstar Geographics" },
  offline:   { label: "Offline outline", layers: [], attr: "Natural Earth" },
};
/* Conflict zones on the maps: restricted areas hatched red, caution areas hatched amber, with a legend and an
   on/off switch (remembered on this computer). Only drawn while staff have the rules switched on. */
let zoneMapData;
function loadZoneMap() { return zoneMapData ||= fetch("/api/conflict-zones/map").then(r => r.ok ? r.json() : null).catch(() => null); }
function zonesShown() { try { return localStorage.getItem("pac.zonesOnMap") !== "0"; } catch (e) { return true; } }
function setZonesShown(on) { try { localStorage.setItem("pac.zonesOnMap", on ? "1" : "0"); } catch (e) { /* private window */ } }
const ZONE_COL = { restricted: "#d4111e", caution: "#f0a000" };
function zoneHatchDefs() {   // SVG hatch patterns the flat maps fill zones with
  if (document.getElementById("zoneHatchDefs")) return;
  document.body.insertAdjacentHTML("beforeend", `<svg id="zoneHatchDefs" width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
    ${Object.entries(ZONE_COL).map(([k, c]) => `<pattern id="zh-${k}" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <rect width="8" height="8" fill="${c}" fill-opacity="0.16"/><line x1="0" y1="0" x2="0" y2="8" stroke="${c}" stroke-width="2.4" stroke-opacity="0.55"/></pattern>`).join("")}</defs></svg>`);
}
function zoneTip(p) {
  return `<b>${esc(p.name)}</b><br>${p.level === "restricted" ? "Restricted: not authorized for PAC" : `Caution area: +${p.pct}% hazard pay`}${p.note ? `<br><small>${esc(p.note)}</small>` : ""}`;
}
function zoneLegendHtml(on) {
  return `<label class="zone-legend"><input type="checkbox" data-zone-toggle ${on ? "checked" : ""}><b>Conflict zones</b>
    <span><i style="--c:${ZONE_COL.restricted}"></i>Restricted</span><span><i style="--c:${ZONE_COL.caution}"></i>Caution</span></label>`;
}
async function addZoneOverlay(map) {
  const data = await loadZoneMap();
  if (!data?.features?.length || !map._container?.isConnected) return;
  zoneHatchDefs();
  map.createPane("zones").style.zIndex = 350;
  const layer = L.geoJSON(data, { pane: "zones", renderer: L.svg({ pane: "zones" }),
    style: f => ({ color: ZONE_COL[f.properties.level], weight: 1.4, dashArray: f.properties.level === "caution" ? "5 4" : null, opacity: 0.9,
                   fillColor: `url(#zh-${f.properties.level})`, fillOpacity: 1 }),
    onEachFeature: (f, l) => l.bindTooltip(zoneTip(f.properties), { sticky: true, className: "zone-tip" }) });
  if (zonesShown()) layer.addTo(map);
  const ctl = L.control({ position: "bottomright" });
  ctl.onAdd = () => { const d = L.DomUtil.create("div", "leaflet-bar zone-legend-wrap"); d.innerHTML = zoneLegendHtml(zonesShown());
    L.DomEvent.disableClickPropagation(d);
    d.querySelector("[data-zone-toggle]").onchange = e => { setZonesShown(e.target.checked); e.target.checked ? layer.addTo(map) : map.removeLayer(layer); };
    return d; };
  ctl.addTo(map);
}
async function addZoneOverlayGlobe(map, wrap) {
  const data = await loadZoneMap();
  if (!data?.features?.length) return;
  for (const [k, c] of Object.entries(ZONE_COL)) {   // the same hatch as an image for MapLibre
    const cv = document.createElement("canvas"); cv.width = cv.height = 16; const x = cv.getContext("2d");
    x.fillStyle = c + "29"; x.fillRect(0, 0, 16, 16); x.strokeStyle = c + "8c"; x.lineWidth = 3;
    x.beginPath(); x.moveTo(-4, 4); x.lineTo(4, -4); x.moveTo(-4, 20); x.lineTo(20, -4); x.moveTo(12, 20); x.lineTo(20, 12); x.stroke();
    if (!map.hasImage(`zh-${k}`)) map.addImage(`zh-${k}`, x.getImageData(0, 0, 16, 16));
  }
  map.addSource("zones", { type: "geojson", data });
  const before = map.getLayer("tracks") ? "tracks" : undefined;
  map.addLayer({ id: "zones-fill", type: "fill", source: "zones", paint: { "fill-pattern": ["concat", "zh-", ["get", "level"]] } }, before);
  map.addLayer({ id: "zones-line", type: "line", source: "zones", paint: { "line-color": ["match", ["get", "level"], "restricted", ZONE_COL.restricted, ZONE_COL.caution], "line-width": 1.4, "line-opacity": 0.9 } }, before);
  const vis = on => ["zones-fill", "zones-line"].forEach(id => map.setLayoutProperty(id, "visibility", on ? "visible" : "none"));
  vis(zonesShown());
  const pop = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: "zone-tip" });
  map.on("mousemove", "zones-fill", e => { map.getCanvas().style.cursor = "help"; pop.setLngLat(e.lngLat).setHTML(zoneTip(e.features[0].properties)).addTo(map); });
  map.on("mouseleave", "zones-fill", () => { map.getCanvas().style.cursor = ""; pop.remove(); });
  wrap.insertAdjacentHTML("beforeend", `<div class="zone-legend-wrap globe-legend">${zoneLegendHtml(zonesShown())}</div>`);
  wrap.querySelector(".globe-legend [data-zone-toggle]").onchange = e => { setZonesShown(e.target.checked); vis(e.target.checked); };
}

let worldData;
function loadWorld() { return worldData ||= fetch("/static/vendor/world.json").then(r => r.json()).catch(() => null); }

/* Builds a base map that always works: an offline Natural Earth outline underneath,
   with online tiles on top. If the tiles fail to load, the map falls back to the outline. */
function makeBaseMap(el, { theme = "dark", style } = {}) {
  const map = L.map(el, { worldCopyJump: true, minZoom: 2 });
  map.createPane("world").style.zIndex = 150;
  const dark = theme === "dark";
  el.style.background = dark ? "#14171b" : "#dfe6ec";
  loadWorld().then(w => {
    if (!w) return;
    try {
    const r = L.canvas({ pane: "world" });
    L.geoJSON(w.land, { pane: "world", renderer: r, interactive: false,
      style: { color: dark ? "#4a515c" : "#aab2bc", weight: 0.8, fillColor: dark ? "#262a31" : "#f4f5f7", fillOpacity: 1 } }).addTo(map);
    L.geoJSON(w.borders, { pane: "world", renderer: r, interactive: false,
      style: { color: dark ? "#3a4049" : "#c3c9d0", weight: 0.6, dashArray: "2 3" } }).addTo(map);
    } catch (e) { /* map was closed before the outline loaded */ }
  });
  const base = { map, tiles: [], note: null };
  base.setStyle = key => {
    const st = MAP_STYLES[key] || MAP_STYLES.dark;
    base.tiles.forEach(t => map.removeLayer(t)); base.tiles = [];
    if (base.note) { base.note.remove(); base.note = null; }
    let loaded = 0, failed = 0;
    st.layers.forEach(([url, maxNativeZoom], i) => {
      const t = L.tileLayer(url, { maxNativeZoom, maxZoom: 18, attribution: i ? "" : st.attr, crossOrigin: false });
      t.on("tileload", () => loaded++);
      t.on("tileerror", () => {
        failed++;
        if (failed >= 6 && loaded === 0 && !base.note) {
          base.tiles.forEach(x => map.removeLayer(x)); base.tiles = [];
          base.note = L.control({ position: "bottomleft" });
          base.note.onAdd = () => { const d = L.DomUtil.create("div", "map-note"); d.textContent = `${st.label} tiles are unavailable. Showing the offline outline map.`; return d; };
          base.note.addTo(map);
        }
      });
      t.addTo(map); base.tiles.push(t);
    });
  };
  base.setStyle(style || (dark ? "dark" : "light"));
  addZoneOverlay(map);
  return base;
}

function initMap() {
  if (S.map) S.map.remove();
  S.map = null;
  if (!HAS_MAP) { $("#map").innerHTML = '<p style="padding:20px;color:var(--scope-dim)">The map library did not load. Restart the ACARS server.</p>'; return; }
  const base = makeBaseMap($("#map"), { theme: "dark", style: S.settings.map_style || "dark" });
  S.map = base.map; S.base = base; S.follow = S.follow ?? false;
  const b = S.booking, m = b.mission, rp = b.ofp?.route_points || [];
  const plan = [[m.origin.lat, m.origin.lon], ...rp.map(p => [p[0], p[1]]), [m.destination.lat, m.destination.lon]];
  S.layers.plan = L.polyline(unwrap(plan), { color: "#FFFFFF", weight: 1.8, opacity: .8, dashArray: "6 6" }).addTo(S.map);
  S.layers.wpts = L.layerGroup(rp.filter(p => p[2] && !/^(TOC|TOD)$/.test(p[2])).map(p =>
    L.circleMarker([p[0], p[1]], { radius: 2.5, color: "#fff", weight: 1, fillColor: "#1B1E23", fillOpacity: 1 })
      .bindTooltip(p[2], { permanent: true, direction: "right", offset: [4, 0], className: "wpt-tip" })));
  S.layers.track = L.polyline([], { color: "#FF3B3B", weight: 3 }).addTo(S.map);
  [m.origin, m.destination, b.ofp?.alternate].filter(Boolean).forEach((a, i) =>
    L.circleMarker([a.lat, a.lon], { radius: 6, color: "#fff", weight: 2, fillColor: i === 2 ? "#8E96A3" : "#C80000", fillOpacity: 1 })
      .bindTooltip(a.icao, { permanent: true, direction: "top", offset: [0, -6], className: "apt-tip" }).addTo(S.map));
  S.layers.ac = L.marker([m.origin.lat, m.origin.lon], { icon: planeIcon(0), zIndexOffset: 1000 }).addTo(S.map);
  S.map.fitBounds(S.layers.plan.getBounds(), { padding: [40, 40] });
  const toggleWpts = () => S.map.getZoom() >= 6 ? S.layers.wpts.addTo(S.map) : S.layers.wpts.remove();
  S.map.on("zoomend", toggleWpts); toggleWpts();
  S.map.on("dragstart", () => { if (S.follow) { S.follow = false; const f = $("#followChk"); if (f) f.checked = false; } });

  const ctl = L.control({ position: "topright" });
  ctl.onAdd = () => {
    const d = L.DomUtil.create("div", "map-ctl");
    d.innerHTML = `<select id="mapStyle" aria-label="Map style">${Object.entries(MAP_STYLES).map(([k, v]) => `<option value="${k}" ${k === (S.settings.map_style || "dark") ? "selected" : ""}>${v.label}</option>`).join("")}</select>
      <label><input type="checkbox" id="followChk" ${S.follow ? "checked" : ""}>Follow aircraft</label>
      <button class="btn ghost small" id="fitRoute" style="padding:3px 8px">Whole route</button>
      <div class="map-ctl-row"><select id="trafficSel" aria-label="Live traffic"><option value="">No traffic</option><option value="VATSIM">VATSIM traffic</option><option value="IVAO">IVAO traffic</option></select>
        <label><input type="checkbox" id="radarChk">Weather radar</label><span class="live-note" id="liveNote" role="status"></span></div>`;
    L.DomEvent.disableClickPropagation(d);
    d.querySelector("#mapStyle").onchange = async e => {
      base.setStyle(e.target.value); S.settings.map_style = e.target.value;
      api("/api/settings", { method: "POST", body: { map_style: e.target.value } }).catch(() => {});
    };
    d.querySelector("#followChk").onchange = e => { S.follow = e.target.checked; if (S.follow && S.status?.live) S.map.panTo([S.status.live.lat, S.status.live.lon]); };
    d.querySelector("#fitRoute").onclick = () => { S.follow = false; d.querySelector("#followChk").checked = false; S.map.fitBounds(S.layers.plan.getBounds(), { padding: [40, 40] }); };
    const ts = d.querySelector("#trafficSel"), rc = d.querySelector("#radarChk");
    ts.value = localStorage.getItem("pac-traffic") || ""; rc.checked = localStorage.getItem("pac-radar") === "1";
    ts.onchange = () => { localStorage.setItem("pac-traffic", ts.value); refreshTraffic(); };
    rc.onchange = () => { localStorage.setItem("pac-radar", rc.checked ? "1" : "0"); refreshRadar(); };
    return d;
  };
  ctl.addTo(S.map);
  // live traffic and weather radar
  S.layers.traffic = L.layerGroup().addTo(S.map);
  clearInterval(S.trafficT); clearInterval(S.radarT);
  S.trafficT = setInterval(refreshTraffic, 30000); S.radarT = setInterval(refreshRadar, 600000);
  let moveT; S.map.on("moveend", () => { clearTimeout(moveT); moveT = setTimeout(refreshTraffic, 600); });
  refreshTraffic(); refreshRadar();
  new ResizeObserver(() => S.map && S.map.invalidateSize()).observe($("#map"));
}
/* ---------------- live traffic (VATSIM / IVAO) and weather radar on the ACARS map ---------------- */
function liveNote(t) { const n = $("#liveNote"); if (n) n.textContent = t || ""; }
function trafficIcon(h) {
  return L.divIcon({ className: "traffic-ic", iconSize: [18, 18], iconAnchor: [9, 9],
    html: `<svg width="18" height="18" viewBox="0 0 24 24" style="transform:rotate(${h || 0}deg)"><path d="M12 2c.8 0 1.3.9 1.3 2v5.2l7.7 4.4v2l-7.7-2.3v4.6l2.2 1.6v1.6L12 20.2l-3.5 1v-1.6l2.2-1.6v-4.6L3 15.6v-2l7.7-4.4V4c0-1.1.5-2 1.3-2z"/></svg>` });
}
async function refreshTraffic() {
  if (!S.map || !S.layers?.traffic || $("#view-acars").hidden || document.hidden) return;
  const net = localStorage.getItem("pac-traffic") || "";
  if (!net) { S.layers.traffic.clearLayers(); liveNote(""); return; }
  const b = S.map.getBounds().pad(0.1);
  const wrap = v => ((v + 540) % 360) - 180;
  const bbox = [Math.max(-90, b.getSouth()), wrap(b.getWest()), Math.min(90, b.getNorth()), wrap(b.getEast())].map(v => v.toFixed(3)).join(",");
  try {
    const r = await api(`/api/traffic?net=${net}&bbox=${bbox}`);
    S.layers.traffic.clearLayers();
    r.planes.forEach(p => {
      if (S.booking && p.cs && p.cs.replace(/\s/g, "") === (S.booking.flight_number || "").replace(/\s/g, "")) return;  // that's you
      L.marker([p.lat, p.lon], { icon: trafficIcon(p.hdg), keyboard: false })
        .bindTooltip(`<b>${esc(p.cs || "")}</b> ${esc(p.type || "")}<br>${p.alt != null ? (p.alt >= 18000 ? "FL" + Math.round(p.alt / 100) : fmt(p.alt) + " ft") : ""}${p.gs != null ? ` · ${p.gs} kt` : ""}${p.dep || p.arr ? `<br>${esc(p.dep || "?")} → ${esc(p.arr || "?")}` : ""}`, { direction: "top", offset: [0, -8] })
        .addTo(S.layers.traffic);
    });
    liveNote(`${r.count} on ${net}`);
  } catch (e) { S.layers.traffic.clearLayers(); liveNote(`${net} unavailable`); }  // never leave another network's traffic showing
}
async function refreshRadar() {
  if (!S.map) return;
  const on = localStorage.getItem("pac-radar") === "1";
  if (!on) { if (S.layers?.radar) { S.layers.radar.remove(); S.layers.radar = null; } return; }
  try {
    const res = await fetch("https://api.rainviewer.com/public/weather-maps.json");
    const w = await res.json(), last = (w.radar?.past || []).slice(-1)[0];
    if (!last) throw new Error("no radar frames");
    if (S.layers.radar) S.layers.radar.remove();
    // RainViewer radar: free tiles up to zoom 7, stretched beyond; color scheme 2, smoothed, with snow
    S.layers.radar = L.tileLayer(`${w.host}${last.path}/256/{z}/{x}/{y}/2/1_1.png`, { opacity: 0.6, maxNativeZoom: 7, maxZoom: 18, zIndex: 350,
      attribution: 'Radar <a href="https://www.rainviewer.com/" target="_blank" rel="noopener">RainViewer</a>' }).addTo(S.map);
  } catch (e) { liveNote("Radar unavailable"); }
}

function unwrap(pts) { // keep lines continuous across the antimeridian
  const out = []; let off = 0;
  pts.forEach((p, i) => { if (i) { const d = p[1] + off - out[i-1][1]; if (d > 180) off -= 360; else if (d < -180) off += 360; } out.push([p[0], p[1] + off]); });
  return out;
}
function planeIcon(h) {
  if (!HAS_MAP) return null;
  return L.divIcon({ className: "", iconSize: [28, 28], iconAnchor: [14, 14],
    html: `<svg width="28" height="28" viewBox="0 0 24 24" style="transform:rotate(${h}deg)"><path fill="#fff" stroke="#C80000" stroke-width="1" d="M12 2c.8 0 1.3.9 1.3 2v5.2l7.7 4.4v2l-7.7-2.3v4.6l2.2 1.7v1.6L12 20.3l-3.5 1v-1.6l2.2-1.7v-4.6L3 15.6v-2l7.7-4.4V4c0-1.1.5-2 1.3-2z"/></svg>` });
}
async function cancelMission() {
  const tracking = S.status?.tracking;
  if (!confirm(tracking ? "Abort this flight and release the mission? Nothing is logged." : "Release this mission back to the board?")) return;
  await api("/api/booking", { method: "DELETE" });
  S.booking = null; S.status = null; S.pirep = null;
  if (S.map) { S.map.remove(); S.map = null; }
  $("#acars").innerHTML = ""; renderAcars(); toast("Mission released."); paintBid();
  if (!$("#view-bids").hidden) loadBids();
}
async function poll() {
  clearTimeout(S.pollTimer);
  if ($("#view-acars").hidden || !S.booking) return;
  try {
    const st = await api("/api/acars/status");
    S.status = st;
    paintStatus(st);
    paintBid();
  } catch (e) { /* server restarting */ }
  S.pollTimer = setTimeout(poll, 1000);
}
function paintStatus(st) {
  if (!$("#acarsReady")) return;
  const live = st.live;
  const conn = $("#conn");
  conn.className = "conn" + (st.error ? " err" : st.connected ? " on" : "");
  conn.querySelector("span").textContent = st.remote ? (st.error ? "PAC ACARS not responding" : st.connected ? `PAC ACARS · ${st.source}` : `PAC ACARS · connecting to ${st.source}`)
    : st.complete ? "Flight complete" : "Not tracking";
  const tracking = st.tracking;
  $("#openApp").hidden = !!st.complete;
  $("#openApp").textContent = tracking ? "Show PAC ACARS" : "Open in PAC ACARS";
  $("#cancelBtn").textContent = st.complete ? "Discard flight" : tracking ? "Abort flight" : "Cancel mission";
  if (st.error && !tracking && S._lastErr !== st.error) { S._lastErr = st.error; toast(st.error); }

  // phase rail
  const cur = st.phase || "PREFLIGHT";
  const reached = {}; (st.timeline || []).forEach(p => reached[p.phase] = reached[p.phase] || p.t);
  const curIdx = RAIL.indexOf(cur === "GO_AROUND" ? "APPROACH" : cur);
  $("#rail").innerHTML = RAIL.map((p, i) => {
    let cls = i < curIdx ? "past" : "";
    if (p === cur) cls = "now";
    if (cur === "GO_AROUND" && p === "APPROACH") cls = "ga";
    const label = cur === "GO_AROUND" && p === "APPROACH" ? "Go-around" : phaseName(p);
    return `<div class="${cls}">${label}<small>${reached[p] ? zulu(reached[p]) : "&nbsp;"}</small></div>`;
  }).join("");

  const r = live || {};
  const vs = r.vs_fpm;
  $("#readouts").innerHTML = [
    ["Altitude", live ? fmt(r.alt_ft) : "–", "ft"],
    ["Indicated", live ? fmt(r.ias) : "–", "kt"],
    ["Ground speed", live ? fmt(r.gs) : "–", "kt"],
    ["Vertical speed", live ? (vs > 0 ? "+" : "") + fmt(vs) : "–", "fpm"],
    ["Heading", live ? String(Math.round(r.hdg)).padStart(3, "0") : "–", "°T"],
    ["Fuel on board", live ? fmt(r.fuel_lbs) : "–", "lb"],
    ["To destination", st.dtg_nm != null ? fmt(st.dtg_nm) : "–", "nm"],
    ["Flown", fmt(st.distance_nm), "nm"],
  ].map(([k, v, u]) => `<div><span>${k}</span><b>${v}</b><em>${u}</em></div>`).join("");

  const o = st.oooi || {};
  $("#oooi").innerHTML = [["Out", o.out], ["Off", o.off], ["On", o.on], ["In", o.in]].map(([k, t]) => `<div><span>${k}</span><b>${zulu(t)}</b></div>`).join("");
  $("#elapsed").textContent = st.block_elapsed_s ? "Block " + hms(st.block_elapsed_s) : "";

  const log = $("#log"), atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 30;
  log.innerHTML = (st.messages || []).map(m => `<div><span class="z">${m.z}</span><span class="${m.kind === "phase" ? "phase" : m.kind === "oooi" ? "oooi-m" : m.kind === "warn" ? "warn" : m.kind === "wx" ? "wx" : m.kind === "dl" ? "dl" : m.kind === "ul" ? "ul" : ""}">${esc(m.text)}</span></div>`).join("")
    || `<div><span class="z">––––</span><span>Awaiting logon</span></div>`;
  if (atBottom) log.scrollTop = log.scrollHeight;

  $("#hint").innerHTML = hintFor(st);

  if (S.map && st.track) {
    const pts = st.track.map(p => [p[0], p[1]]);
    if (live) pts.push([r.lat, r.lon]);
    S.layers.track.setLatLngs(unwrap(pts));
    if (live) {
      S.layers.ac.setLatLng([r.lat, r.lon]);
      const svg = S.layers.ac.getElement()?.querySelector("svg");
      if (svg) svg.style.transform = `rotate(${r.hdg}deg)`;
      if (S.follow) S.map.panTo([r.lat, r.lon], { animate: false });
    }
  }
  if (st.complete && !S.pirep) loadPirepDraft();
}
function hintFor(st) {
  const p = st.phase, r = st.live;
  if (!st.tracking && !st.complete) return `Load the aircraft at <b>${S.booking.dep_stand?.icao === S.booking.mission.origin.icao ? standName(S.booking.dep_stand) + " at " + esc(S.booking.mission.origin.icao) : "a stand at " + esc(S.booking.mission.origin.icao)}</b>${S.booking.dep_stand?.icao === S.booking.mission.origin.icao ? " (or any other stand)" : ""} with the parking brake set, press <b>Open in PAC ACARS</b>, then start tracking in the app. The flight shows here live.<br><span class="muted">${
    S.appInfo ? `PAC ACARS ${esc(verLabel(S.appInfo.version))} is running on this PC.` : S.appInfo === false ? `PAC ACARS isn't running on this PC. Nothing happens when you press the button? <a href="#" onclick="event.preventDefault();$('#acarsDownload .dl-card') ? scrollTo({ top: 0, behavior: 'smooth' }) : show('handbook')">Get PAC ACARS</a>.` : ""}</span>`;
  if (st.remote && st.error) return `<b>${esc(st.error)}</b>`;
  if (!r) return "Waiting for simulator data…";
  const tips = {
    PREFLIGHT: "Release the parking brake to push back. The OUT time is logged when you start moving.",
    PUSHBACK: "Start engines and taxi. Taxi phase begins above 5 kt with engines running.",
    TAXI_OUT: "Keep taxi speed under 30 kt, or reposition to the runway with GSX. Takeoff is detected above 50 kt.",
    TAKEOFF: "Rotate. OFF time is logged at liftoff.",
    INITIAL_CLIMB: "Climb phase begins at 1,500 ft above ground.",
    CLIMB: "Cruise is detected once you level off near your planned altitude. Keep 250 kt below 10,000 ft.",
    CRUISE: "Position reports go out every 10 minutes. Descent is detected when you leave cruise altitude.",
    DESCENT: "Approach phase begins below 4,000 ft AGL near the destination or with gear down.",
    APPROACH: "Touchdown rate and G load are captured at the first contact with the runway.",
    GO_AROUND: "Go-around logged. Approach resumes once you are descending again.",
    LANDING: st.landing ? `Touchdown <b>${st.landing.rate_fpm} fpm</b> at ${st.landing.g} G. Slow to taxi speed.` : "Rolling out.",
    TAXI_IN: "Taxi or reposition to the stand, then park, set the parking brake and shut down all engines to go on block.",
    ARRIVED: "On block. Review and file your PIREP below.",
  };
  return tips[p] || "";
}

/* ---------------- PIREP ---------------- */
async function loadPirepDraft() {
  try { S.pirep = await api("/api/pirep/draft"); renderPirep(); $("#pirepPanel").scrollIntoView({ behavior: "smooth" }); }
  catch (e) { toast(e.message); }
}
function breakdownRows(items) {
  return items.map(([k, d]) => `<tr><td>${esc(pacScoreLabel(k))}</td><td class="${d < 0 ? "neg" : d > 0 ? "pos" : ""}">${d > 0 ? "+" : ""}${d}</td></tr>`).join("");
}
function renderPirep() {
  const p = S.pirep;
  if (!p) { $("#pirepPanel").innerHTML = ""; return; }
  $("#pirepPanel").innerHTML = `<div class="pirep">
    <div class="score"><span>Flight grade</span><span class="g">${p.grade}</span><span class="s">${p.score} / 100</span><span>${p.points} points</span><span class="st">${esc(p.status)}${p.demo ? " (demo)" : ""}</span></div>
    <div class="body">
      <h2 style="margin:0">Pilot report for ${esc(p.flight_number)}</h2>
      ${checkrideBanner(p)}
      ${pacDebrief(p)}
      ${econBox(p.economics)}
      ${p.pay ? `<div class="notice" style="border-color:#1f9d55;background:var(--ok-wash)">Your pay: <b>${money(p.pay.flight_pay, true)}</b> flight pay (${p.pay.hours} h at $${p.pay.rate}/h)${p.pay.profit_share ? ` + <b>${money(p.pay.profit_share, true)}</b> profit share` : ""}${p.pay.contract_bonus ? ` + <b>${money(p.pay.contract_bonus, true)}</b> shortage bonus` : ""}${p.pay.ferry_bonus ? ` + <b>${money(p.pay.ferry_bonus, true)}</b> ferry bonus` : ""}${p.pay.hazard_pay ? ` + <b>${money(p.pay.hazard_pay, true)}</b> hazard pay` : ""}${p.pay.skill_total ? ` + <b>${money(p.pay.skill_total, true)}</b> skill bonus` : ""} = <b>${money(p.pay.total, true)}</b>${p.review_status === "Pending" ? ", paid once staff accept the PIREP" : ""}.
        ${p.pay.skill?.length ? `<div style="margin-top:6px;font-size:13px">Flown well: ${p.pay.skill.map(x => `${esc(x.label)} <b>+$${x.amount}</b>`).join(" · ")}</div>` : `<div style="margin-top:6px;font-size:13px">No skill bonus this time. An A grade, a smooth landing, fuel on plan, an on-time and stable approach and a clean flight each pay extra.</div>`}</div>` : ""}
      ${integrityNote(p.integrity)}
      <h3 style="margin:4px 0 0;font-size:18px">Landing</h3>
      ${landingSection("cardDraft", { ...cardData(p), la: p.landing_analysis })}
      ${approachChart(p.landing_analysis)}
      ${p.takeoff_analysis ? `<h3 style="margin:10px 0 0;font-size:18px">Takeoff</h3>${takeoffSection("toDraft", cardData(p))}${takeoffChart(p.takeoff_analysis)}` : ""}
      <div class="kv num">
        <div><span>Route flown</span><b>${p.dep} to ${p.arr}</b></div>
        <div><span>Block time</span><b>${hm(p.block_min)}</b></div>
        <div><span>Flight time</span><b>${hm(p.flight_min)}</b></div>
        <div><span>Planned block</span><b>${hm(p.target_block_min)}</b></div>
        <div><span>Landing rate</span><b>${p.landing_rate ?? "–"} fpm</b></div>
        <div><span>Landing load</span><b>${p.landing_g ?? "–"} G</b></div>
        <div><span>Fuel used</span><b>${fmt(p.fuel_used_lbs)} lb</b></div>
        <div><span>Trip burn / plan</span><b>${fmt(p.trip_burn_lbs)} / ${fmt(p.planned_trip_lbs)} lb</b></div>
        <div><span>Distance flown</span><b>${fmt(p.distance_nm)} nm</b></div>
        <div><span>Cargo delivered</span><b>${p.status === "Failed" ? 0 : fmt(p.payload_lbs)}${p.mission_payload_lbs && p.payload_lbs < p.mission_payload_lbs ? " of " + fmt(p.mission_payload_lbs) : ""} lb</b>${p.loaded_lbs && p.loaded_lbs > p.payload_lbs ? `<small class="muted" style="display:block;font-size:12px">OFP payload ${fmt(p.loaded_lbs)} lb</small>` : ""}</div>
        <div><span>Max altitude</span><b>${fmt(p.max_alt)} ft</b></div>
        <div><span>Bounces</span><b>${p.bounces}</b></div>
      </div>
      
      ${p.bonuses?.length ? `<table class="breakdown"><tbody><tr><td>Base points</td><td>${fmt(p.base_points)}</td></tr>${p.bonuses.map(b => `<tr><td>${esc(b[0])}</td><td class="pos">+${fmt(b[1])}</td></tr>`).join("")}<tr><td><b>Total points</b></td><td>${fmt(p.points)}</td></tr></tbody></table>` : ""}
      ${p.demo ? "" : p.review_status === "Accepted" ? `<div class="muted" style="font-size:14px">No flags. This PIREP will be accepted automatically.</div>`
        : `<div class="notice">This PIREP will go to staff review: ${esc(p.flags.join(", "))}. It counts towards your career once accepted.</div>`}
      <div class="field"><label for="remarks">Remarks for dispatch</label><textarea id="remarks" style="min-height:70px;font-family:var(--font);font-size:14px" placeholder="Weather, delays, NOTOC, anything dispatch should know"></textarea></div>
      <div class="row"><button class="btn ghost" type="button" id="faultBtn">Report a fault</button> <button class="btn" id="fileBtn">File PIREP</button><span class="muted" style="font-size:13px">Filing closes the flight and writes it to your logbook.</span></div>
    </div></div>`;
  $("#fileBtn").onclick = filePirep;
  if ($("#faultBtn")) $("#faultBtn").onclick = () => S.booking?.airframe ? openFaultAfter(S.booking.airframe, null, S.booking.flight_number)
    : toast("Partner aircraft aren't PAC's to maintain. Note the fault in your remarks.");
  pacReportNav($("#pirepPanel .body"));
  bindCard("cardDraft", cardData(p));
  if (p.takeoff_analysis) bindTakeoffCard("toDraft", cardData(p));
}
/* Checkride result, at the top of the report: a perfect score doesn't pass a checkride on its own */
function checkrideReason(r, p) {
  if (/unstable approach/i.test(r)) return `unstable approach (${esc(p.landing_analysis?.stability_note || "approach outside the limits")})`;
  return esc(r);
}
function checkrideBanner(p) {
  const out = [];
  if (p.checkride) out.push(p.checkride.passed
    ? `<div class="ck-banner pass"><b>Line checkride passed.</b> Welcome to the line, Second Officer. It also gives you the B737 qualification once this report is accepted.</div>`
    : `<div class="ck-banner fail"><b>Line checkride not passed:</b> ${p.checkride.reasons.map(r => checkrideReason(r, p)).join("; ")}. Your score doesn't change this: every checkride standard has to be met. Fly it again whenever you're ready; retakes are free.</div>`);
  const t = p.type_checkride;
  if (t) out.push(t.passed
    ? `<div class="ck-banner pass"><b>${esc(t.family)} type checkride passed.</b> The ${esc(t.family)} rating is yours ${p.review_status === "Accepted" ? "as soon as you file this report" : "once staff accept this report"}${S.career?.checkride === "Pending" ? ", and it also counts as your line checkride, so rank progression opens up" : ""}.</div>`
    : `<div class="ck-banner fail"><b>${esc(t.family)} type checkride not passed:</b> ${t.reasons.map(r => checkrideReason(r, p)).join("; ")}. Your score of ${p.score} doesn't change this: every checkride standard has to be met (score 80+, landing no firmer than 600 fpm and no higher than 1.8 G, at most one bounce, and a steady approach). Overspeed penalties affect score but aren't automatic failures. Fly it again from Career › Qualifications; retakes are free.</div>`);
  return out.join("");
}
async function filePirep() {
  try {
    const r = await api("/api/pirep", { method: "POST", body: { remarks: $("#remarks").value } });
    const ck = r.type_checkride || r.checkride;
    toast(`PIREP filed: ${r.flight_number} graded ${r.grade}, ${r.points} points${r.paid ? `, ${money(r.paid.total, true)} paid to your wallet` : ""}${r.review_status === "Pending" ? ". It's waiting for staff review." : "."}${ck ? (ck.passed ? ` ${r.type_checkride ? r.type_checkride.family + " type" : "Line"} checkride passed.` : ` Checkride not passed: ${ck.reasons.join(", ")}.`) : ""}`);
    loadMe();
    refreshCore();
    showReveal(r.unlocked);
    S.booking = null; S.status = null; S.pirep = null;
    if (S.map) { S.map.remove(); S.map = null; }
    $("#acars").innerHTML = ""; $("#pirepPanel").innerHTML = "";
    show("logbook");
    offerDeliveryReceipt(r.id);
  } catch (e) { toast(e.message); }
}

/* ---------------- Logbook ---------------- */
async function loadLogbook() {
  if (!$("#manualPirepOpen")) { $("#lbNote").insertAdjacentHTML("beforebegin", '<button type="button" class="btn ghost" id="manualPirepOpen">Submit a manual PIREP</button>'); $("#manualPirepOpen").onclick=openManualReport; }
  const who = S.me?.staff && S.lbPilot && S.lbPilot !== S.me.id ? S.lbPilot : "";
  const { pireps, totals: t } = await api("/api/logbook" + (who ? `?pilot=${encodeURIComponent(who)}` : ""));
  if (S.me?.staff) {                     // staff can open any pilot's logbook
    if (!S.lbRoster) { try { S.lbRoster = (await api("/api/staff/overview")).roster || []; } catch (e) { S.lbRoster = []; } }
    const opts = S.lbRoster.map(p => `<option value="${esc(p.id)}" ${p.id === (who || S.me.id) ? "selected" : ""}>${esc(p.id)} · ${esc(p.name)}${p.id === S.me.id ? " (you)" : ""}</option>`).join("");
    if (opts && !$("#lbWho")) $("#lbNote").insertAdjacentHTML("beforebegin", `<div class="field" style="max-width:340px;margin:8px 0 0"><label for="lbWho">Pilot <span class="tag grey">Staff</span></label><select id="lbWho"></select></div>`);
    if ($("#lbWho")) { $("#lbWho").innerHTML = opts; $("#lbWho").onchange = e => { S.lbPilot = e.target.value; loadLogbook(); }; }
  }
  $("#totals").innerHTML = [
    ["Flights", fmt(t.flights)], ["Block hours", t.block_hours], ["Cargo moved", fmt(t.cargo_lbs) + " lb"],
    ["Points", fmt(t.points)], ["Average landing", t.avg_landing != null ? t.avg_landing + " fpm" : "–"], ["Average score", t.avg_score ?? "–"],
  ].map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("");
  $("#lbNote").textContent = "Totals count accepted flights only. Failed checkride attempts count toward career hours and flight count but do not grant a qualification." + (pireps.some(p => p.demo) ? " Demo flights are listed but never counted." : "");
  $("#lbBody").innerHTML = pireps.map(p => `<tr data-id="${p.id}">
    <td>${new Date(p.filed_at * 1000).toISOString().substr(0, 10)}</td><td><b>${esc(p.flight_number)}</b></td><td>${esc(p.mission_title)}</td>
    <td>${p.dep} – ${p.arr}</td><td>${esc(S.fleet[p.aircraft]?.icao || p.aircraft)}${divOf(p.aircraft) ? `<br><small class="muted">${esc(divShort(divOf(p.aircraft)))}</small>` : ""}</td><td>${hm(p.block_min)}</td>
    <td>${p.landing_rate ?? "–"} fpm</td><td>${fmt(p.fuel_used_lbs)} lb</td><td>${p.source === "Manual" ? "Unscored · Manual" : `${p.score} (${p.grade})`}</td>
    <td><span class="badge b-${p.status.split(" ")[0]} ${p.status.includes("late") ? "late" : ""}">${esc(p.status)}</span>${p.demo ? '<span class="badge b-demo">Demo</span>' : ""}${p.checkride_result ? `<span class="tag ${p.checkride_result.passed ? "green" : ""} lb-ck" title="${esc(p.checkride_result.passed ? "All checkride standards met" : "Reason: " + p.checkride_result.reasons.join(", "))}">${p.checkride_result.kind === "type" ? esc(p.checkride_result.family || "Type") : "Line"} checkride ${p.checkride_result.passed ? "passed" : "not passed"}</span>` : ""}</td>
    <td>${p.demo ? "–" : `<span class="tag ${p.review_status === "Accepted" ? "green" : p.review_status === "Pending" ? "amber" : ""}" style="margin:0">${esc(p.review_status || "Accepted")}</span>`}</td>
    <td>${fmt(p.points)}</td></tr>`).join("")
    || `<tr><td colspan="12" class="empty">No flights logged yet. Fly a mission and file the PIREP to start your logbook.</td></tr>`;
  document.querySelectorAll("#lbBody tr[data-id]").forEach(tr => tr.onclick = () => openDetail(tr.dataset.id));
}
let detailMap;
function tickCountdowns() {
  const now = Date.now() / 1000;
  document.querySelectorAll("[data-countdown]").forEach(el => {
    const left = +el.dataset.countdown - now;
    el.textContent = left <= 0 ? "expired" : `${Math.floor(left / 3600)}h ${String(Math.floor(left % 3600 / 60)).padStart(2, "0")}m`;
  });
}
setInterval(tickCountdowns, 20000);

/* ================= Promotion and badge reveal ================= */
function showReveal(u) {
  if (!u || (!u.rank && !(u.badges || []).length)) return;
  const el = document.createElement("div");
  el.className = "reveal"; el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true");
  const sparks = Array.from({ length: 36 }, (_, i) => { const a = i / 36 * Math.PI * 2, r = 220 + Math.random() * 260;
    return `<span class="spark" style="--dx:${Math.cos(a) * r}px;--dy:${Math.sin(a) * r}px;background:${i % 3 ? "#FFC845" : "#C80000"};animation-delay:${Math.random() * .35}s"></span>`; }).join("");
  const r = u.rank;
  el.innerHTML = `${sparks}<div class="reveal-inner">
    ${r ? `<div class="reveal-kicker">PROMOTION</div><img class="reveal-patch" src="${r.insignia}" alt="${esc(r.to)} insignia">
      <h2>${esc(r.to)}</h2><p>Congratulations, ${esc(displayName(S.profile || {}))}. You've been promoted from ${esc(r.from)}.</p>
      ${r.unlocks?.length ? `<p>Now unlocked: <b>${r.unlocks.map(a => esc(S.fleet[a]?.name || a)).join(", ")}</b></p>` : ""}` : `<div class="reveal-kicker">NEW ${u.badges.length === 1 ? "AWARD" : "AWARDS"}</div>`}
    ${(u.badges || []).length ? `<div class="reveal-badges">${u.badges.map((b, i) => `<div class="reveal-badge" style="animation-delay:${(r ? .9 : .2) + i * .18}s"><i>PAC</i><b>${esc(b.name)}</b><small>${esc(b.description)}</small></div>`).join("")}</div>` : ""}
    <button class="btn" style="margin-top:14px;background:#fff;color:var(--red);border-color:#fff" type="button">Continue</button></div>`;
  document.body.appendChild(el);
  const close = () => el.remove();
  el.querySelector("button").onclick = close; el.querySelector("button").focus();
  el.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
}

/* ================= Airframe pages ================= */
async function openAirframe(reg) {
  try {
    const h = await api("/api/airframes/" + encodeURIComponent(reg)), a = h.airframe, ac = S.fleet[a.type] || {};
    $("#detailTitle").textContent = `${a.reg}${a.name ? ` “${a.name}”` : ""} · ${ac.name || a.type}`;
    $("#detailBody").innerHTML = `
      <div class="landing-wrap" style="grid-template-columns:minmax(220px,340px) minmax(0,1fr)">
        <img src="${esc(displayPhoto(ac.thumb || ac.photo))}" alt="" style="width:100%;border-radius:6px;aspect-ratio:16/9;object-fit:cover">
        <div class="la-facts">
          <div><span>Now at</span><b>${esc(a.location)}</b><small>${esc(a.status)}</small></div>
          <div><span>Hours / cycles</span><b>${esch(a.hours || 0)} / ${a.cycles || 0}</b></div>
          <div><span>A-check due in</span><b>${esch(Math.max(0, a.check_due_in))} h</b></div>
          <div><span>Heavy check due in</span><b>${a.heavy_due_in == null ? "–" : esch(Math.max(0, a.heavy_due_in)) + " h"}</b></div>
          <div><span>Flights</span><b>${h.flights.length}</b></div>
          <div><span>Profit earned</span><b class="${moneyCls(h.profit)}">${money(h.profit)}</b></div>
          <div><span>Last flown by</span><b>${esc(h.flights[h.flights.length - 1]?.pilot || "–")}</b><small>${esc(a.last_flight || "")}</small></div>
        </div></div>
      ${a.note ? `<div class="notice">${esc(a.note)}</div>` : ""}
      ${S.me?.staff && a.status === "Booked" ? `<div class="notice" style="border-left:3px solid #c80000">
        <b>Dispatch override.</b> ${esc(reservationSummary(a))}.
        <div class="row" style="margin-top:8px"><button class="btn small" type="button" id="afRelease" data-reg="${esc(a.reg)}">Cancel booking &amp; free this aircraft</button></div></div>` : ""}
      <h3 style="margin:4px 0 0;font-size:17px">Maintenance</h3><div id="afMx"><span class="muted" style="font-size:13px">Loading…</span></div>
      <div style="border:1px solid var(--line)"><div id="detailMap"></div></div>
      ${h.flights.length ? `<div class="table-wrap"><table class="fin-table"><thead><tr><th>Date</th><th>Flight</th><th>Route</th><th>Pilot</th><th class="r">Block</th><th class="r">Landing</th><th class="r">Profit</th></tr></thead><tbody>
        ${h.flights.slice().reverse().map(f => `<tr data-open="${f.id}" style="cursor:pointer"><td>${new Date(f.filed_at * 1000).toISOString().substr(0, 10)}</td><td><b>${esc(f.flight_number)}</b></td><td>${f.dep} – ${f.arr}</td><td>${esc(f.pilot || "")}</td>
          <td class="r">${hm(f.block_min)}</td><td class="r">${f.landing_rate ?? "–"} fpm</td><td class="r ${moneyCls(f.profit)}">${money(f.profit)}</td></tr>`).join("")}</tbody></table></div>`
        : `<p class="muted">No flights logged on ${esc(a.reg)} yet.</p>`}`;
    $("#detailDlg").showModal();
    document.querySelectorAll("#detailBody [data-open]").forEach(tr => tr.onclick = () => openDetail(tr.dataset.open));
    const relBtn = $("#afRelease");
    if (relBtn) relBtn.onclick = async () => {
      const who = a.reservation ? `${a.reservation.pilot_name || a.reservation.pilot_id}'s booking` : "the booking holding this aircraft";
      if (!confirm(`Cancel ${who} and make ${a.reg} available again? The pilot's flight is cancelled and the mission goes back on the board.`)) return;
      relBtn.disabled = true; relBtn.textContent = "Freeing…";
      try {
        const r = await api("/api/staff/booking/release", { method: "POST", body: { reg: a.reg } });
        toast(r.had_booking ? `${a.reg} freed. Cancelled ${esc(r.flight || "a flight")} (${esc(r.pilot || "")}).` : `${a.reg} is available again.`);
        $("#detailDlg").close();
        try { S.airframes = await api("/api/airframes"); } catch (e) { /* keep */ }
        if (S.view === "fleet") show("fleet");
      } catch (e) { toast(e.message); relBtn.disabled = false; relBtn.textContent = "Cancel booking & free this aircraft"; }
    };
    api(`/api/maintenance?reg=${encodeURIComponent(a.reg)}&all=1`).then(r => { const el = $("#afMx"); if (el) el.innerHTML = mxItems(r.items); }).catch(() => {});
    if (detailMap) detailMap.remove();
    if (!HAS_MAP) return;
    detailMap = makeBaseMap($("#detailMap"), { theme: "light", style: "light" }).map;
    const bounds = [];
    h.flights.forEach(f => { const A = h.airports[f.dep], B = h.airports[f.arr]; if (A && B) { const path = gcPath({ lat: A[0], lon: A[1] }, { lat: B[0], lon: B[1] }); L.polyline(path, { color: "#C80000", weight: 2, opacity: .6 }).addTo(detailMap); bounds.push(...path); } });
    Object.entries(h.airports).forEach(([ic, ll]) => L.circleMarker(ll, { radius: ic === a.location ? 8 : 4, color: "#fff", weight: 2, fillColor: ic === a.location ? "#C80000" : "#1E2126", fillOpacity: 1 })
      .bindTooltip(ic + (ic === a.location ? " · here now" : ""), { direction: "top", className: "stn-tip", permanent: ic === a.location }).addTo(detailMap));
    const here = AIRPORT_LL(a);
    if (bounds.length) detailMap.fitBounds(L.latLngBounds(bounds), { padding: [24, 24] }); else if (here) detailMap.setView(here, 5); else detailMap.setView([30, 0], 2);
    if (!h.airports[a.location] && here) L.circleMarker(here, { radius: 8, color: "#fff", weight: 2, fillColor: "#C80000", fillOpacity: 1 }).bindTooltip(a.location + " · here now", { permanent: true, direction: "top", className: "stn-tip" }).addTo(detailMap);
    setTimeout(() => detailMap.invalidateSize(), 80);
  } catch (e) { toast(e.message); }
}
const AIRPORT_LL = a => a.lat != null ? [a.lat, a.lon] : null;

/* ================= ACARS messages to dispatch, and maintenance ================= */
const ATA_LIST = [[5, "Time limits and inspections"], [21, "Air conditioning and pressurization"], [22, "Autoflight"], [23, "Communications"],
  [24, "Electrical power"], [26, "Fire protection"], [27, "Flight controls"], [28, "Fuel"], [29, "Hydraulic power"], [30, "Ice and rain protection"],
  [31, "Indicating and recording"], [32, "Landing gear and brakes"], [33, "Lights"], [34, "Navigation"], [36, "Pneumatic"], [49, "APU"],
  [50, "Cargo compartments"], [52, "Doors"], [53, "Fuselage"], [71, "Power plant"], [80, "Engine starting"]];
const ataSelect = (name = "ata", sel = 49) => `<select name="${name}" id="mf_${name}">${ATA_LIST.map(([n, l]) => `<option value="${n}" ${n === sel ? "selected" : ""}>ATA ${String(n).padStart(2, "0")} · ${l}</option>`).join("")}</select>`;
const faultFields = () => `<div class="full"><label for="mf_ata">System</label>${ataSelect()}</div>
  <div class="full"><label for="mf_desc">What's wrong</label><input id="mf_desc" name="description" maxlength="300" placeholder="e.g. APU fails to start on the first attempt" required></div>
  <div><label for="mf_sev">Can it keep flying?</label><select id="mf_sev" name="severity"><option value="deferred">Yes: defer it</option><option value="grounding">No: ground it on arrival</option></select></div>
  <div><label for="mf_cat">If deferred, fix within</label><select id="mf_cat" name="category"><option value="C">10 days (category C)</option><option value="B">3 days (category B)</option></select></div>`;
function mxItems(items, staff = false) {
  if (!items.length) return `<p class="muted" style="margin:0;font-size:14px">No write-ups.</p>`;
  const when = t => new Date(t * 1000).toISOString().substr(0, 10);
  return `<div class="mx-list">${items.map(i => `<div class="mx-item ${i.status === "cleared" ? "cleared" : i.severity}">
    <span class="ata">ATA ${String(i.ata).padStart(2, "0")}</span>
    <span><b>${esc(i.description)}</b><br><small class="muted">${esc(i.ata_name || "")} · ${i.reg} · ${i.flight ? esc(i.flight) + " · " : ""}${when(i.time)}${i.status === "cleared" ? ` · cleared ${when(i.cleared_time)}: ${esc(i.note || "")}` :
      i.severity === "grounding" ? " · <b style='color:var(--red)'>Grounding</b>" : ` · deferred cat ${i.category}, due ${when(i.due)}${i.overdue ? " · <b style='color:var(--red)'>OVERDUE</b>" : ""}`}</small></span>
    ${staff && i.status !== "cleared" ? `<span class="row" style="flex-wrap:nowrap"><input data-mxnote="${i.id}" placeholder="Rectification" style="border:1px solid var(--line);border-radius:3px;padding:6px 8px;width:170px">
      <button class="btn small" type="button" data-mxclear="${i.id}">Clear</button>
      ${i.severity === "grounding" ? `<button class="btn ghost small" type="button" data-mxdefer="${i.id}">Defer</button>` : `<button class="btn ghost small" type="button" data-mxground="${i.id}">Ground</button>`}</span>` : "<span></span>"}</div>`).join("")}</div>`;
}
function openFaultAfter(reg, pirepId, flight) {
  const dlg = $("#msgDlg"), form = $("#msgForm");
  form.innerHTML = `<p class="full" style="margin:0">Write up a fault on <b>${esc(reg)}</b> from ${esc(flight)}.</p>` + faultFields() + `<div class="full row"><button class="btn" type="submit">Write it up</button></div>`;
  form.onsubmit = async e => {
    e.preventDefault();
    const body = { ...Object.fromEntries(new FormData(form).entries()), reg, pirep_id: pirepId, flight };
    try { await api("/api/maintenance", { method: "POST", body }); dlg.close(); toast(`Write-up opened on ${reg}.`); refreshCore(); } catch (err) { toast(err.message); }
  };
  dlg.showModal();
}
async function staffMx() {
  let open = [], all = [];
  try { [open, all] = await Promise.all([api("/api/maintenance").then(r => r.items), api("/api/maintenance?all=1").then(r => r.items)]); } catch (e) { toast(e.message); }
  $("#staffBody").innerHTML = `<p class="muted" style="margin:0 0 12px;font-size:14px">Open write-ups across the fleet. Clearing a grounding item returns the aircraft to service once nothing else grounds it. Deferred items ground the aircraft automatically when they run past their deadline.</p>
    <h3 style="margin:0 0 8px">Open (${open.length})</h3>${mxItems(open, true)}
    <h3 style="margin:18px 0 8px">Recently cleared</h3>${mxItems(all.filter(i => i.status === "cleared").slice(0, 15))}`;
  const act = async (id, body, msg) => { try { await api("/api/staff/maintenance/" + id, { method: "POST", body }); toast(msg); await refreshCore(); staffMx(); } catch (e) { toast(e.message); } };
  document.querySelectorAll("[data-mxclear]").forEach(b => b.onclick = () => act(b.dataset.mxclear, { action: "clear", note: document.querySelector(`[data-mxnote="${b.dataset.mxclear}"]`).value }, "Write-up cleared."));
  document.querySelectorAll("[data-mxdefer]").forEach(b => b.onclick = () => act(b.dataset.mxdefer, { action: "defer", category: "C" }, "Deferred for 10 days."));
  document.querySelectorAll("[data-mxground]").forEach(b => b.onclick = () => act(b.dataset.mxground, { action: "ground" }, "Aircraft grounded."));
}

/* ================= My stats, records, airport collection and monthly recap ================= */
async function loadStats() {
  const version = ++cargoStatsVersion, pilot = S.me?.id;
  if (S.cargoMap) { S.cargoMap.remove(); S.cargoMap = null; }
  if (S.statsMap) { S.statsMap.remove(); S.statsMap = null; }
  if (S.statsTab === 'passport' || S.statsTab === 'campaigns') return loadCargoPanel(version);
  const root = $("#statsRoot");
  root.innerHTML = `<div class="profile-bar"><h1>My stats</h1></div><p class="muted">Loading…</p>`;
  let s, r;
  try { [s, r] = await Promise.all([api("/api/stats"), api("/api/recap")]); } catch (e) { root.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  if (version !== cargoStatsVersion || S.me?.id !== pilot) return;
  S.statsData = s;
  const t = s.totals, c = s.collection, rec = s.records;
  const tile = (label, value, sub = "") => `<div><span>${label}</span><b>${value}</b>${sub ? `<small>${sub}</small>` : ""}</div>`;
  const hrs = h => `${Math.floor(h)}h ${String(Math.round((h % 1) * 60)).padStart(2, "0")}m`;
  const recCard = (k, label, fmtv) => rec[k] ? `<button type="button" class="rec" data-pirep="${rec[k].id}"><span>${label}</span><b>${fmtv(rec[k].value)}</b>
      <small>${esc(rec[k].flight)} · ${esc(rec[k].dep)}–${esc(rec[k].arr)} · ${esc(S.fleet[rec[k].aircraft]?.icao || rec[k].aircraft)} · ${esc(rec[k].date)}</small></button>` : "";
  const next = (have, steps) => steps.find(x => x > have);
  const bar = (label, have, steps) => {
    const n = next(have, steps), prev = [...steps].reverse().find(x => x <= have) || 0;
    const pct = n ? Math.round((have - prev) / (n - prev) * 100) : 100;
    return `<div class="coll"><div class="row" style="justify-content:space-between"><b>${label}</b><span>${have}${n ? ` / ${n}` : " · all milestones"}</span></div>
      <div class="coll-bar"><i style="width:${pct}%"></i></div>
      <div class="coll-steps">${steps.map(x => `<span class="${have >= x ? "on" : ""}">${x}</span>`).join("")}</div></div>`;
  };
  const maxTypeH = Math.max(1, ...s.by_type.map(x => x.hours)), maxMonth = Math.max(1, ...s.months.map(m => m.flights));
  root.innerHTML = `<div class="profile-bar"><h1>My stats</h1><span class="muted">Every accepted and pending flight you've flown (demo flights aren't counted).</span></div>
    ${cargoStatsNav()}
    ${t.flights ? "" : `<div class="notice">No flights yet. Your stats, records and airport collection build up as you fly.</div>`}
    <div class="stat-tiles">${tile("Flights", fmt(t.flights), `${t.grades.A} A grades`)}${tile("Block hours", hrs(t.hours))}${tile("Distance", fmt(t.distance_nm) + " nm")}
      ${tile("Cargo moved", fmt(t.cargo_lbs) + " lb", `${fmt(t.cargo_lbs / 2204.6)} tonnes`)}${tile("Average landing", t.avg_landing != null ? t.avg_landing + " fpm" : "–")}${tile("Average score", t.avg_score ?? "–")}</div>

    <div class="section-h"><div><h2>Goals</h2><p>Set targets for yourself; progress updates as you fly.</p></div></div>
    <div id="goalsBox"></div>

    <div class="section-h"><div><h2>Where you've been</h2><p>${c.airports} airports in ${c.countries} ${c.countries === 1 ? "country" : "countries"} on ${c.continents} ${c.continents === 1 ? "continent" : "continents"}. Bigger dots are airports you visit often.</p></div></div>
    <div class="stats-map" id="statsMap"></div>

    <div class="section-h"><div><h2>Airport collection</h2><p>Milestones earn awards on your Career page.</p></div></div>
    <div class="coll-grid">${bar("Airports", c.airports, c.milestones.airports)}${bar("Countries", c.countries, c.milestones.countries)}${bar("Continents", c.continents, c.milestones.continents)}</div>
    ${c.country_list.length ? `<p class="muted" style="font-size:13px;margin:8px 0 0">Countries: ${c.country_list.map(esc).join(" · ")}</p>` : ""}

    <div class="stats-2">
      ${(() => { const by = {}; s.by_type.forEach(x => { const dv = divOf(x.code) || "Other"; by[dv] = by[dv] || { hours: 0, flights: 0 }; by[dv].hours += x.hours; by[dv].flights += x.flights; });
        const rows = Object.entries(by).sort((a, b) => b[1].hours - a[1].hours), top = Math.max(1, ...rows.map(r => r[1].hours));
        return rows.length ? `<section><h2>Hours by division</h2>${rows.map(([n, v]) => `<div class="hbar"><span>${esc(n)}</span><div><i style="width:${v.hours / top * 100}%"></i></div><b>${hrs(v.hours)}</b><small>${v.flights} ${v.flights === 1 ? "flight" : "flights"}</small></div>`).join("")}</section>` : ""; })()}
      <section><h2>Hours by aircraft</h2>${s.by_type.length ? s.by_type.map(x => `<div class="hbar"><span>${esc(S.fleet[x.code]?.name || x.name)}</span><div><i style="width:${x.hours / maxTypeH * 100}%"></i></div><b>${hrs(x.hours)}</b><small>${x.flights} ${x.flights === 1 ? "flight" : "flights"}</small></div>`).join("") : `<p class="muted">–</p>`}</section>
      <section><h2>Flights per month</h2><div class="mbars">${s.months.map(m => `<div title="${m.month}: ${m.flights} flights, ${m.hours} h"><i style="height:${m.flights / maxMonth * 100}%"></i><b>${m.flights || ""}</b><span>${new Date(m.month + "-01T00:00Z").toLocaleDateString("en-US", { month: "short", timeZone: "UTC" })}</span></div>`).join("")}</div></section>
    </div>

    <div class="section-h"><div><h2>Records</h2><p>Click one to open that flight.</p></div></div>
    <div class="rec-grid">
      ${recCard("softest_landing", "Softest landing", v => `${v} fpm`)}${recCard("longest_distance", "Longest flight", v => `${fmt(v)} nm`)}
      ${recCard("longest_block", "Longest block time", v => hrs(v / 60))}${recCard("heaviest_load", "Heaviest load", v => `${fmt(v)} lb`)}
      ${recCard("most_points", "Most points", v => fmt(v))}
      <div class="rec"><span>Streaks</span><b>${s.streaks.a_grades} A's in a row</b><small>Longest run of flying days: ${s.streaks.days}</small></div>
      ${s.favourites.route ? `<div class="rec"><span>Favorite route</span><b>${esc(s.favourites.route.dep)}–${esc(s.favourites.route.arr)}</b><small>${s.favourites.route.flights} ${s.favourites.route.flights === 1 ? "flight" : "flights"}</small></div>` : ""}
      ${s.favourites.airport ? `<div class="rec"><span>Favorite airport</span><b>${esc(s.favourites.airport.icao)}</b><small>${esc(s.favourites.airport.city || s.favourites.airport.name)} · ${s.favourites.airport.visits} visits</small></div>` : ""}
    </div>

    <div class="section-h" id="recap"><div><h2>Monthly recap</h2><p>Your month in review, to keep or share.</p></div>
      <select id="recapMonth" aria-label="Month">${(r.months.length ? r.months : [r.month]).map(m => `<option value="${m}" ${m === r.month ? "selected" : ""}>${new Date(m + "-01T00:00Z").toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" })}</option>`).join("")}</select></div>
    <div id="recapBody"></div>`;
  root.querySelectorAll("[data-pirep]").forEach(b => b.onclick = () => openDetail(+b.dataset.pirep));
  $("#recapMonth").onchange = async e => { const month = e.target.value; try { const recap = await api(`/api/recap?month=${month}`); if (version === cargoStatsVersion && $('#recapMonth')?.value === month && S.me?.id === pilot) renderRecap(recap); } catch (err) { toast(err.message); } };
  renderRecap(r);
  loadGoals();
  if (HAS_MAP) {
    if (S.statsMap) { S.statsMap.remove(); S.statsMap = null; }
    const base = makeBaseMap($("#statsMap"), { theme: document.documentElement.dataset.theme === "dark" ? "dark" : "light" });
    const m = S.statsMap = base.map;
    // routes across the date line (Hong Kong to Anchorage, say) go over the Pacific, not the long way round
    const wrap = (a, b) => { const lon = b[1] - a[1] > 180 ? b[1] - 360 : b[1] - a[1] < -180 ? b[1] + 360 : b[1]; return [a, [b[0], lon]]; };
    s.routes.forEach(x => L.polyline(wrap(x.from, x.to), { color: "#C80000", weight: Math.min(5, 1.2 + x.flights * 0.6), opacity: 0.65 })
      .bindTooltip(`${x.dep}–${x.arr} · ${x.flights} ${x.flights === 1 ? "flight" : "flights"}`).addTo(m));
    const maxV = Math.max(1, ...s.airports.map(a => a.visits));
    s.airports.forEach(a => L.circleMarker([a.lat, a.lon], { radius: 4 + a.visits / maxV * 8, color: "#fff", weight: 1.5, fillColor: "#C80000", fillOpacity: 0.95 })
      .bindTooltip(`<b>${esc(a.icao)}</b> ${esc(a.city || a.name)}<br>${a.visits} ${a.visits === 1 ? "visit" : "visits"} · first ${a.first}`)
      .bindPopup(`<b>${esc(a.icao)}</b> ${esc(a.city || a.name)}<br>${a.visits} visits<br><button type="button" class="btn ghost small" data-passport-airport="${esc(a.icao)}">View cargo passport stamp</button>`).addTo(m));
    if (s.airports.length) m.fitBounds(s.airports.map(a => [a.lat, a.lon]), { padding: [30, 30], maxZoom: 6 }); else m.setView([30, -40], 2);
  } else $("#statsMap").innerHTML = `<p class="muted" style="padding:20px">The map needs an internet connection.</p>`;
}

async function loadGoals() {
  const el = $("#goalsBox"); if (!el) return;
  let g; try { g = await api("/api/goals"); } catch (e) { el.innerHTML = ""; return; }
  const fmtv = (v, u) => u === "hours" ? `${v}` : fmt(v);
  el.innerHTML = `<div class="goal-grid">${g.goals.map(x => `<div class="goal ${x.done ? "done" : x.expired ? "missed" : ""}">
      <div class="goal-top"><b>${esc(x.title)}</b><button type="button" class="goal-x" data-goal="${x.id}" aria-label="Remove this goal" title="Remove">×</button></div>
      <div class="coll-bar"><i style="width:${x.pct}%"></i></div>
      <small>${x.done ? "Reached" : x.expired ? "Not reached in time" : `${fmtv(x.value, x.unit)} of ${fmt(x.target)} ${esc(x.unit)}${x.days_left != null ? ` · ${x.days_left} ${x.days_left === 1 ? "day" : "days"} left` : ""}`}</small></div>`).join("")}
    <form class="goal goal-add" id="goalForm"><b>Add a goal</b>
      <div class="goal-line"><input id="gTarget" type="number" min="1" step="any" placeholder="50" required aria-label="How much">
        <select id="gKind" aria-label="What">${Object.entries(g.kinds).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></div>
      <div class="goal-line"><select id="gPeriod" aria-label="When"><option value="month">this month (every month)</option><option value="year">this year</option><option value="deadline">by a date</option><option value="ever">in total</option></select>
        <input id="gDate" type="date" hidden aria-label="Date"></div>
      <button class="btn small" type="submit">Add</button></form></div>`;
  $("#gPeriod").onchange = e => { $("#gDate").hidden = e.target.value !== "deadline"; };
  $("#goalForm").onsubmit = async e => {
    e.preventDefault();
    try { await api("/api/goals", { method: "POST", body: { target: +$("#gTarget").value, kind: $("#gKind").value, period: $("#gPeriod").value, deadline: $("#gDate").value } }); loadGoals(); }
    catch (err) { toast(err.message); }
  };
  el.querySelectorAll("[data-goal]").forEach(b => b.onclick = async () => { try { await api(`/api/goals/${b.dataset.goal}`, { method: "DELETE" }); loadGoals(); } catch (e) { toast(e.message); } });
}

function renderRecap(r) {
  const el = $("#recapBody");
  if (!el) return;
  if (!r.flights) { el.innerHTML = `<div class="notice">No flights in ${esc(r.label)} yet.</div>`; return; }
  const d = (a, b) => a === b ? "" : `<small class="${a > b ? "up" : "down"}">${a > b ? "▲" : "▼"} ${Math.abs(Math.round((a - b) * 10) / 10)} vs ${new Date(r.vs_previous.month + "-01T00:00Z").toLocaleDateString("en-US", { month: "short", timeZone: "UTC" })}</small>`;
  el.innerHTML = `<div class="recap">
    <div class="recap-head"><img src="/static/pac-wordmark-white.png" alt="PAC"><div><span>Month in review</span><b>${esc(r.label)}</b></div></div>
    <div class="stat-tiles recap-tiles">
      <div><span>Flights</span><b>${r.flights}</b>${d(r.flights, r.vs_previous.flights)}</div><div><span>Block hours</span><b>${r.hours}</b>${d(r.hours, r.vs_previous.hours)}</div>
      <div><span>Distance</span><b>${fmt(r.distance_nm)} nm</b></div><div><span>Cargo</span><b>${fmt(r.cargo_lbs)} lb</b></div>
      <div><span>Points</span><b>${fmt(r.points)}</b></div><div><span>Earned</span><b>${money(r.earned, true)}</b></div></div>
    <div class="recap-row">
      ${r.best_landing ? `<div><span>Best landing</span><b>${r.best_landing.rate} fpm</b><small>${esc(r.best_landing.flight)} into ${esc(r.best_landing.arr)}</small></div>` : ""}
      ${r.top_route ? `<div><span>Top route</span><b>${esc(r.top_route.dep)}–${esc(r.top_route.arr)}</b><small>${r.top_route.flights} ${r.top_route.flights === 1 ? "flight" : "flights"}</small></div>` : ""}
      ${r.top_aircraft ? `<div><span>Most flown</span><b>${esc(S.fleet[r.top_aircraft.code]?.icao || r.top_aircraft.code)}</b><small>${r.top_aircraft.hours} h</small></div>` : ""}
      <div><span>Grades</span><b>${Object.entries(r.grades).filter(([, n]) => n).map(([g, n]) => `${n}×${g}`).join(" ") || "–"}</b><small>average ${r.avg_score ?? "–"}</small></div>
    </div>
    ${r.new_airports.length ? `<p>New airports this month: <b>${r.new_airports.map(esc).join(", ")}</b></p>` : ""}
    ${r.cargo_passport ? `<p>Cargo Passport: <b>${r.cargo_passport.stamps.length} new stamps</b>${r.cargo_passport.stamps.length ? ` · ${r.cargo_passport.stamps.map(esc).join(', ')}` : ''}</p><p>Collections completed: <b>${r.cargo_passport.collections.length ? r.cargo_passport.collections.map(esc).join(', ') : 'None this month'}</b> · accepted deliveries only</p>` : ''}
  </div>
  <div class="row" style="margin-top:10px"><button class="btn small" type="button" id="recapImg">Download recap image</button>${S.settings?.discord_enabled ? `<button class="btn ghost small" type="button" id="recapDc">Post to Discord</button>` : ""}</div>`;
  $("#recapImg").onclick = async () => { const cv = await recapCanvas(r); const a = document.createElement("a"); a.download = `PAC-recap-${r.month}.png`; a.href = cv.toDataURL("image/png"); a.click(); };
  if ($("#recapDc")) $("#recapDc").onclick = async e => shareToDiscord(await recapCanvas(r), `📦 ${r.label} in review: ${r.flights} flights, ${r.hours} hours`, `PAC-recap-${r.month}.png`, e.currentTarget);
}

async function recapCanvas(r) {
  const W = 1080, H = 1350 + (r.cargo_passport ? 220 : 0), cv = document.createElement("canvas"); cv.width = W; cv.height = H;
  const g = cv.getContext("2d");
  try { await document.fonts.ready; } catch (e) { /* default font */ }
  const F = (w, px) => `${w} ${px}px Saira, system-ui, sans-serif`;
  g.fillStyle = "#15171b"; g.fillRect(0, 0, W, H);
  g.fillStyle = "#C80000"; g.fillRect(0, 0, W, 300);
  const logo = await new Promise(res => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = "/static/pac-wordmark-white.png"; });
  if (logo) g.drawImage(logo, 72, 64, 200, 200 * logo.height / logo.width);
  g.fillStyle = "#fff"; g.font = F(600, 30); g.fillText("MONTH IN REVIEW", 72, 184);
  g.font = F(800, 66); g.fillText(r.label, 72, 256);
  const tiles = [["FLIGHTS", String(r.flights)], ["BLOCK HOURS", String(r.hours)], ["DISTANCE", `${fmt(r.distance_nm)} nm`],
                 ["CARGO", `${fmt(r.cargo_lbs)} lb`], ["POINTS", fmt(r.points)], ["EARNED", money(r.earned, true)]];
  tiles.forEach(([k, v], i) => {
    const x = 72 + (i % 2) * 480, y = 350 + Math.floor(i / 2) * 170;
    g.fillStyle = "#1f2228"; g.fillRect(x, y, 456, 146);
    g.fillStyle = "#8E96A3"; g.font = F(600, 24); g.fillText(k, x + 28, y + 46);
    g.fillStyle = "#fff"; g.font = F(800, 56); g.fillText(v, x + 28, y + 112);
  });
  let y = 890;
  const line = (k, v, sub) => {
    g.fillStyle = "#8E96A3"; g.font = F(600, 24); g.fillText(k, 72, y);
    g.fillStyle = "#fff"; g.font = F(700, 40); g.fillText(v, 72, y + 48);
    const w = g.measureText(v).width;  // measured in the big font, before switching to the small one
    if (sub) { g.fillStyle = "#b8bec8"; g.font = F(400, 26); g.fillText(sub, 72 + w + 24, y + 46); }
    y += 104;
  };
  if (r.best_landing) line("BEST LANDING", `${r.best_landing.rate} fpm`, `${r.best_landing.flight} into ${r.best_landing.arr}`);
  if (r.top_route) line("TOP ROUTE", `${r.top_route.dep} – ${r.top_route.arr}`, `${r.top_route.flights} ${r.top_route.flights === 1 ? "flight" : "flights"}`);
  if (r.new_airports.length) line("NEW AIRPORTS", r.new_airports.slice(0, 6).join("  "), r.new_airports.length > 6 ? `+${r.new_airports.length - 6} more` : "");
  if (r.cargo_passport) {
    line('NEW CARGO PASSPORT STAMPS', String(r.cargo_passport.stamps.length), 'accepted deliveries');
    line('CARGO COLLECTIONS COMPLETED', String(r.cargo_passport.collections.length), 'this month');
  }
  g.fillStyle = "#C80000"; g.fillRect(0, H - 110, W, 110);
  g.fillStyle = "#fff"; g.font = F(700, 32); g.fillText(`${S.profile?.name || S.me?.name || ""}`.toUpperCase(), 72, H - 46);
  g.font = F(500, 26); const idt = `${S.me?.id || ""} · PAGANI AIR CARGO`; g.fillText(idt, W - 72 - g.measureText(idt).width, H - 46);
  return cv;
}

/* type ratings on the Career page */
async function fillRatings() {
 const el=$('#ratingsGrid');if(!el)return;
 try{const [ratings,career]=await Promise.all([api('/api/ratings'),api('/api/va/career')]);S.ratings=ratings;S.career=career.career;S.checkrides=S.ratings.families.map(f=>f.mission).filter(Boolean);
 $('#ratingsText').textContent='Company-funded checkrides. Choose a dedicated training session or an available fleet aircraft. Both use the same passing standards.';
 el.innerHTML=lineCheckrideCard(S.career?.checkride,S.career?.checkride_via)+S.ratings.families.map(f=>`<div class="rating ${f.rated?'rt-held':f.unlocked?'rt-open':'rt-locked'}"><div class="rating-top"><h3>${esc(f.family)}</h3>${f.rated?'<span class="tag green">✓ Qualified</span>':f.unlocked?'<span class="tag amber">Not yet rated</span>':'<span class="tag">Locked</span>'}</div><p>${f.type_names.map(esc).join(' · ')}</p><p>${f.rated?'<b class="rt-ok">You can fly these types.</b>':f.unlocked?'Available to train':'Unlocks at '+esc(f.unlock_rank)}</p>${f.unlocked?`<button class="btn ${f.rated?'ghost':''}" data-training-course="${esc(f.checkride_id)}">${f.rated?'Retake checkride (optional)':'Start checkride'}</button>`:''}</div>`).join('');
 el.querySelectorAll('[data-training-course]').forEach(x=>x.onclick=()=>openTraining(x.dataset.trainingCourse));
 }catch(e){$('#ratingsText').textContent=e.message;el.innerHTML='<button class="btn" onclick="fillRatings()">Retry qualifications</button>';}
}

/* the airport collection on the Career page */
function collectionPanel() {
  return `<div class="section-h"><div><h2>Airport collection</h2><p id="collText">Loading…</p></div><button class="btn ghost small" onclick="show('stats')">My stats and records</button></div>
    <div class="coll-grid" id="collCareer"></div>`;
}
async function fillCollection() {
  const el = $("#collCareer"); if (!el) return;
  try {
    const s = S.statsData || await api("/api/stats"); S.statsData = s; const c = s.collection;
    $("#collText").textContent = `${c.airports} airports in ${c.countries} ${c.countries === 1 ? "country" : "countries"} on ${c.continents} ${c.continents === 1 ? "continent" : "continents"}.`;
    const bar = (label, have, steps) => { const n = steps.find(x => x > have), prev = [...steps].reverse().find(x => x <= have) || 0;
      return `<div class="coll"><div class="row" style="justify-content:space-between"><b>${label}</b><span>${have}${n ? ` / ${n}` : " · all milestones"}</span></div>
        <div class="coll-bar"><i style="width:${n ? Math.round((have - prev) / (n - prev) * 100) : 100}%"></i></div></div>`; };
    el.innerHTML = bar("Airports", c.airports, c.milestones.airports) + bar("Countries", c.countries, c.milestones.countries) + bar("Continents", c.continents, c.milestones.continents);
  } catch (e) { el.innerHTML = ""; }
}

/* ================= Station guides ================= */
document.addEventListener("click", e => { const a = e.target.closest("[data-station]"); if (!a) return; e.preventDefault(); openStation(a.dataset.station); });
function openStation(icao) { S.stationIcao = icao; show("stations"); }
async function loadStations() {
  const root = $("#stationsRoot");
  if (S.stationIcao) return loadStation(S.stationIcao);
  let list; try { list = S.stationList || (S.stationList = await api("/api/stations")); } catch (e) { root.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  root.innerHTML = `<div class="profile-bar"><h1>Stations</h1><span class="muted">${list.length} airports in PAC's network. KCVG has a full station guide.</span></div>
    <input id="stSearch" class="st-search" placeholder="Search by ICAO, city or airport name" aria-label="Search stations">
    <div class="st-grid" id="stGrid"></div>`;
  const draw = q => {
    q = (q || "").trim().toLowerCase();
    const shown = list.filter(x => !q || [x.icao, x.iata, x.name, x.city, x.country].some(v => (v || "").toLowerCase().includes(q)));
    $("#stGrid").innerHTML = shown.slice(0, 120).map(x => `<button class="st-card ${x.guide ? "has-guide" : ""}" type="button" data-st="${esc(x.icao)}">
        <span class="st-icao">${esc(x.icao)}</span><span class="st-name">${esc(x.city || x.name)}</span><small>${esc(x.name)} · ${esc(x.country)}</small>
        <span class="st-tags">${x.main_hub ? `<span class="tag">Main hub</span>` : x.hub ? `<span class="tag dark">PAC hub</span>` : ""}${x.partner_hub ? `<span class="tag grey">${esc(x.partner_hub)} hub</span>` : ""}${x.guide ? `<span class="tag green">Full guide</span>` : ""}${x.visits ? `<span class="tag grey">${x.visits} ${x.visits === 1 ? "visit" : "visits"}</span>` : ""}</span></button>`).join("")
      + (shown.length > 120 ? `<p class="muted">Showing 120 of ${shown.length}. Search to narrow it down.</p>` : "") + (!shown.length ? `<p class="muted">No station matches.</p>` : "");
    $("#stGrid").querySelectorAll("[data-st]").forEach(b => b.onclick = () => { S.stationIcao = b.dataset.st; loadStation(b.dataset.st); scrollTo(0, 0); });
  };
  $("#stSearch").oninput = e => draw(e.target.value);
  draw("");
}

/* ================= Persistent cargo inventory ================= */
async function loadCargo() {
  const root = $("#cargoRoot");
  if (!root) return;
  S.cargoView = S.cargoView || "waiting";
  root.innerHTML = `<div class="profile-bar"><h1>Cargo inventory</h1><span class="muted">Every PAC shipment keeps its air waybill from first pickup to final delivery, across pilots and flights. <a href="#cargoguide" onclick="show('cargoguide');return false">How cargo works →</a></span></div>
    <div class="cgo-tabs" role="tablist" aria-label="Cargo inventory sections">
      <button type="button" role="tab" data-cgo-tab="waiting">Freight waiting</button>
      <button type="button" role="tab" data-cgo-tab="shipments">All shipments</button>
      <button type="button" role="tab" data-cgo-tab="network">Warehouses and lanes</button>
    </div>
    <div class="cgo-pane" data-pane="waiting">
      <section id="cgoSeasons" class="cgo-seasons" aria-label="Cargo seasons running now"></section>
      <section id="cgoWaiting" class="cgo-waiting" aria-label="Freight waiting at stations"></section>
    </div>
    <div class="cgo-pane" data-pane="network">
      <section id="cgoSheds" class="cgo-sheds" aria-label="Warehouses"></section>
      <section id="cgoLanes" class="cgo-lanes" aria-label="Lane reputation"></section>
    </div>
    <div class="cgo-pane" data-pane="shipments">
    <div class="cgo-strip" id="cgoStrip" role="tablist" aria-label="Cargo views"></div>
    <div class="cargo-filters">
      <label>Station<select id="cargoStation"><option value="ALL">All stations</option></select></label>
      <label class="cargo-search">Search<input id="cargoSearch" type="search" maxlength="80" placeholder="AWB, shipper, consignee or commodity"></label>
      <label class="cgo-all" id="cgoAllWrap" hidden><input type="checkbox" id="cgoAll"> Older deliveries too</label>
    </div>
    <p class="muted cargo-results" id="cargoResults" role="status">Loading cargo…</p>
    <div class="cgo-table-wrap"><table class="cgo-table"><thead><tr><th>Air waybill</th><th>Journey</th><th>Commodity</th><th class="r">Pieces · weight</th><th>Status</th><th>Due / since</th></tr></thead>
      <tbody id="cargoList"></tbody></table></div>
    </div>
    <p class="muted cargo-note">Movements are recorded when a PIREP is filed. Shippers and consignees are real companies chosen to fit the route; the shipments are fictional.</p>`;
  const station = $("#cargoStation"), search = $("#cargoSearch");
  const cargoTab = t => {
    S.cargoTab = t; try { localStorage.setItem("pac-cargo-tab", t); } catch (e) { /* private window */ }
    root.querySelectorAll("[data-cgo-tab]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.cgoTab === t)));
    root.querySelectorAll(".cgo-pane").forEach(p => { p.hidden = p.dataset.pane !== t; });
  };
  let savedTab = S.cargoTab; if (!savedTab) { try { savedTab = localStorage.getItem("pac-cargo-tab"); } catch (e) { savedTab = null; } }
  cargoTab(["waiting", "shipments", "network"].includes(savedTab) ? savedTab : "waiting");
  root.querySelectorAll("[data-cgo-tab]").forEach(b => b.onclick = () => cargoTab(b.dataset.cgoTab));
  let overview;
  try {
    const [stations, ov] = await Promise.all([api("/api/cargo/stations"), api("/api/cargo/overview")]);
    overview = ov;
    station.innerHTML = `<option value="ALL">All stations</option>` + stations.map(x => `<option value="${esc(x.icao)}">${esc(x.icao)} · ${fmt(x.shipments)}</option>`).join("");
    if (stations.some(x => x.icao === S.cargoStation)) station.value = S.cargoStation;
  } catch (e) { $("#cargoResults").textContent = e.message; return; }
  if (S.cargoSearch) search.value = S.cargoSearch;
  const c = overview.counts;
  const views = [["waiting", "Waiting for onward flight", c.waiting, c.overdue ? `${c.overdue} over ${overview.overdue_hours} h` : "at PAC stations"],
    ["transit", "On a booked flight", c.transit, "in the air or about to be"], ["delivered", "Delivered", c.delivered, "last 7 days"],
    ...(c.exceptions ? [["exceptions", "Exceptions", c.exceptions, "need a look"]] : [])];
  const drawStrip = () => { $("#cgoStrip").innerHTML = views.map(([k, l, n, sub]) => `<button type="button" role="tab" data-cgo-view="${k}" aria-selected="${S.cargoView === k}" class="${k === "waiting" && c.overdue ? "warn" : ""}"><small>${l}</small><b>${fmt(n)}</b><span>${esc(sub)}</span></button>`).join(""); };
  drawStrip();
  const ago = h => h < 1 ? "under an hour" : h < 48 ? `${Math.round(h)} h` : `${Math.round(h / 24)} days`;
  const sheds = overview.sheds || [];
  $("#cgoSheds").innerHTML = sheds.length ? `<h2>Warehouses</h2>${sheds.some(x => x.pct >= 85) ? `<p class="notice" style="margin:0 0 10px">${sheds.filter(x => x.pct >= 85).map(x => `<b>${esc(x.station)} shed ${x.pct}% full</b>`).join(", ")}: no new customer orders there until freight flies out. Every shipment you carry from there helps.</p>` : ""}
    <div class="shed-grid">${sheds.map(x => `<div class="shed shed-${esc(x.level.toLowerCase())}"><div class="shed-top"><b class="mono">${esc(x.station)}</b><span>${esc(x.level)}</span></div>
      <div class="shed-bar" role="img" aria-label="${esc(x.station)} shed ${x.pct}% full"><i style="width:${Math.min(100, x.pct)}%"></i></div>
      <small class="muted">${fmt(x.lbs)} of ${fmt(x.capacity)} lb · ${fmt(x.shipments)} shipment${x.shipments === 1 ? "" : "s"}</small></div>`).join("")}</div>` : "";
  loadLanes(true).then(list => {
    const el = $("#cgoLanes"); if (!el) return;
    const weak = list.filter(L => L.tier === "Under review" || L.tier === "At risk"), strong = list.filter(L => L.tier === "Preferred" || L.tier === "Good").slice(0, 6);
    const row = L => `<tr><td class="mono"><b>${esc(L.origin)}</b> → <b>${esc(L.destination)}</b> <small class="muted">${esc(L.city_from || "")} to ${esc(L.city_to || "")}</small></td>
      <td><span class="tag ${({ Preferred: "lane-pref", Good: "lane-good", "Under review": "lane-review", "At risk": "lane-risk" })[L.tier]}">${esc(L.tier)}</span></td><td class="r mono">${L.score}</td>
      <td class="r">${L.flights}</td><td class="r">${L.on_time}</td><td class="r">${L.late}</td><td class="r">${L.care_issues}</td></tr>`;
    el.innerHTML = list.length ? `<h2>Lane reputation</h2><p class="muted" style="max-width:90ch">Shippers remember how PAC performs on each route. On-time, careful deliveries raise a lane's score; late flights, damaged or spoiled freight and failed flights lower it. Strong lanes get more customer orders. Scores start at 70 and cover the last 90 days.</p>
      <div class="aar-wrap"><table class="aar-table"><thead><tr><th>Lane</th><th>Standing</th><th class="r">Score</th><th class="r">Flights</th><th class="r">On time</th><th class="r">Late</th><th class="r">Freight issues</th></tr></thead><tbody>
      ${weak.length ? `<tr><td colspan="7"><b>Needs attention</b></td></tr>${weak.map(row).join("")}` : ""}${strong.length ? `<tr><td colspan="7"><b>Strongest lanes</b></td></tr>${strong.map(row).join("")}` : ""}</tbody></table></div>` : "";
    const acc = S.accountList || [];
    const weakAcc = acc.filter(a => a.tier === "Under review" || a.tier === "At risk");
    const actionable = weakAcc.filter(a => a.station && a.waiting), idle = weakAcc.filter(a => !(a.station && a.waiting));
    const chip = a => a.tier === "At risk" ? `<span class="acct-chip risk">Slipping away</span>` : `<span class="acct-chip review">Needs a win</span>`;
    if (weakAcc.length) {
      const counts = {}; actionable.forEach(a => counts[a.station] = (counts[a.station] || 0) + 1);
      const stations = Object.keys(counts).sort((x, y) => counts[y] - counts[x] || x.localeCompare(y));
      const filterRow = stations.length > 1 ? `<div class="acct-filter"><button type="button" class="acct-pill active" data-acct-filter="">All (${actionable.length})</button>${stations.map(s => `<button type="button" class="acct-pill" data-acct-filter="${esc(s)}">${esc(s)} (${counts[s]})</button>`).join("")}</div>` : "";
      el.insertAdjacentHTML("beforeend", `<h2>Accounts that need you</h2><p class="muted" style="max-width:90ch">These shippers have been let down lately, so they're sending more of their freight to other carriers. Fly their cargo and deliver it on time to win them back.</p>
        ${filterRow}
        ${actionable.length ? `<div class="acct-grid">${actionable.map(a => `<article class="acct-card ${a.tier === "At risk" ? "risk" : "review"}" data-acct-station="${esc(a.station)}">
          <div class="acct-top"><b>${esc(a.shipper)}</b>${chip(a)}</div>
          <p class="muted">${a.waiting} shipment${a.waiting === 1 ? "" : "s"} waiting at <b>${esc(a.station)}</b></p>
          <button type="button" class="btn small" data-acct-fly="${esc(a.station)}">Find their freight →</button></article>`).join("")}</div>
        <p class="muted acct-empty" hidden>No slipping accounts have freight waiting at that station right now.</p>` : `<p class="muted">None of the slipping accounts have freight waiting right now. Their cargo will be back on the boards as stations restock.</p>`}
        ${idle.length ? `<p class="muted" style="font-size:13px">${idle.length} more account${idle.length === 1 ? "" : "s"} slipping (${idle.slice(0, 5).map(a => esc(a.shipper)).join(", ")}${idle.length > 5 ? "…" : ""}) with no freight waiting from them right now.</p>` : ""}
        <p class="muted" style="font-size:12px">Company names are used for flight simulation only and imply no relationship with PAC.</p>`);
    } else if (acc.length) {
      el.insertAdjacentHTML("beforeend", `<h2>Customer accounts</h2><p class="muted">Every shipper is happy with PAC right now. Keep delivering on time to keep it that way.</p>`);
    }
    el.querySelectorAll("[data-acct-fly]").forEach(b => b.onclick = () => {
      resetMissionFilters(); Object.assign(S, { board: "all", parkedOrigin: b.dataset.acctFly, shipmentFilterTitle: `Freight waiting at ${b.dataset.acctFly}` });
      show("missions");
    });
    el.querySelectorAll("[data-acct-filter]").forEach(btn => btn.onclick = () => {
      const f = btn.dataset.acctFilter;
      el.querySelectorAll(".acct-pill").forEach(p => p.classList.toggle("active", p === btn));
      let shown = 0;
      el.querySelectorAll(".acct-card[data-acct-station]").forEach(c => {
        const hit = !f || c.dataset.acctStation === f; c.hidden = !hit; if (hit) shown++;
      });
      const empty = el.querySelector(".acct-empty"); if (empty) empty.hidden = shown > 0;
    });
  });
  $("#cgoSeasons").innerHTML = (overview.seasons || []).length ? `<h2>In season now</h2><div class="cgo-season-grid">${overview.seasons.map(x => `<article class="cgo-season-card">
      <div class="kicker">Until ${esc(x.until)}</div><h3>${esc(x.name)}</h3><p>${esc(x.blurb)}</p>
      <p class="muted">${x.waiting ? `${fmt(x.waiting)} shipment${x.waiting === 1 ? "" : "s"} waiting: ${esc(x.cargo)}` : "New orders arrive as stations restock."}</p>
      ${x.lanes.length ? `<div class="row" style="gap:6px;flex-wrap:wrap">${x.lanes.map(l => `<button type="button" class="btn small ghost" data-cgo-fly="${esc(l.station)}|${esc(l.destination)}">${esc(l.station)} → ${esc(l.destination)} (${l.n})</button>`).join("")}</div>` : ""}
    </article>`).join("")}</div>` : "";
  if ((overview.coming || []).length) $("#cgoSeasons").insertAdjacentHTML("beforeend", `<h2>Coming up on the cargo calendar</h2><div class="cgo-coming">${overview.coming.map(x => `<article>
      <div class="kicker">From ${esc(new Date(x.starts + "T12:00:00Z").toLocaleDateString("en-US", { month: "long", day: "numeric" }))}</div><h3>${esc(x.name)}</h3><p>${esc(x.blurb)}</p></article>`).join("")}</div>`);
  $("#cgoWaiting").innerHTML = overview.waiting.length ? `<h2>Freight waiting</h2><p class="muted">Cargo sitting at a station for its next leg. Fly it there and it's yours to deliver.</p>
    <div class="cgo-wait-grid">${overview.waiting.slice(0, 12).map(w => `<article class="cgo-wait ${w.overdue ? "overdue" : ""}">
      <div class="cgo-wait-route"><b>${esc(w.station)}</b><span aria-hidden="true">→</span><b>${esc(w.destination)}</b></div>
      <p>${fmt(w.shipments)} shipment${w.shipments === 1 ? "" : "s"} · ${fmt(w.weight_lbs)} lb</p>
      <p class="muted">${w.due ? `Due ${cargoInventoryDate(w.due)}` : `Waiting ${ago(w.waiting_h)}`}${w.overdue ? " · <b>overdue</b>" : ""}</p>
      ${(w.fly_to || []).length ? `<button type="button" class="btn small" data-cgo-fly="${esc(w.station)}|${esc(w.destination)}|${esc(w.fly_to.join(","))}">Find a flight →</button>${w.direct_route ? "" : `<small class="muted" style="display:block;margin-top:4px">Fly to ${esc(w.fly_to.slice(0, 3).join(", "))}${w.fly_to.length > 3 ? "…" : ""}</small>`}` : `<span class="muted cgo-nodirect">No PAC flight reaches ${esc(w.destination)} from ${esc(w.station)} yet</span>`}
      <button type="button" class="linkish" data-cgo-show="${esc(w.station)}|${esc(w.destination)}">See the shipments</button></article>`).join("")}</div>` : "";
  document.querySelectorAll("#cgoWaiting [data-cgo-fly], #cgoSeasons [data-cgo-fly]").forEach(b => b.onclick = () => {
    const [from, to, via] = b.dataset.cgoFly.split("|");
    resetMissionFilters(); Object.assign(S, { board: "all", parkedOrigin: from, shipmentDestinations: (via || to).split(","), shipmentFilterTitle: `Freight waiting at ${from} for ${to}` });
    show("missions");
  });
  let dest = "";
  $("#cgoWaiting").querySelectorAll("[data-cgo-show]").forEach(b => b.onclick = () => {
    const [from, to] = b.dataset.cgoShow.split("|"); S.cargoView = "waiting"; station.value = from; dest = to; drawStrip(); refresh(); cargoTab("shipments");
  });
  let requestNo = 0, searchTimer;
  const statusWord = { AT_STATION: "Waiting", HELD_AT_STATION: "Held (diversion)", BOOKED: "On a booked flight", DELIVERED: "Delivered", DELIVERED_LATE: "Delivered late", EXCEPTION: "Exception" };
  const refresh = async () => {
    const request = ++requestNo;
    S.cargoStation = station.value; S.cargoSearch = search.value.trim();
    $("#cgoAllWrap").hidden = S.cargoView !== "delivered";
    const params = new URLSearchParams({ view: S.cargoView, station: S.cargoStation, q: S.cargoSearch, ...(dest ? { destination: dest } : {}), ...($("#cgoAll").checked ? { all: "1" } : {}) });
    $("#cargoResults").textContent = "Loading cargo…";
    try {
      const result = await api(`/api/cargo/shipments?${params}`);
      if (request !== requestNo || $("#view-cargo").hidden) return;
      const shown = result.shipments || [];
      $("#cargoResults").innerHTML = (result.total ? `${fmt(result.total)} shipment${result.total === 1 ? "" : "s"}${result.total > result.limit ? ` (showing the first ${result.limit})` : ""}` : "No shipments here right now.")
        + (dest ? ` going to <b>${esc(dest)}</b> · <button type="button" class="linkish" id="cgoClearDest">show all destinations</button>` : "");
      $("#cgoClearDest")?.addEventListener("click", () => { dest = ""; refresh(); });
      $("#cargoList").innerHTML = shown.map(x => {
        const via = x.current_station !== x.origin && x.current_station !== x.destination;
        const atOrigin = x.current_station === x.origin;
        const journey = atOrigin ? `<b class="cgo-now" title="Where it is now">${esc(x.origin)}</b> → <b>${esc(x.destination)}</b>`
          : `<b>${esc(x.origin)}</b> → ${via || x.status === "AT_STATION" || x.status === "HELD_AT_STATION" ? `<b class="cgo-now" title="Where it is now">${esc(x.current_station)}</b> → ` : ""}<b>${esc(x.destination)}</b>`;
        return `<tr class="cgo-row" data-cargo-id="${esc(x.id)}" tabindex="0" aria-expanded="false">
          <td class="mono cgo-awb">${trackAwb(x.awb)}</td><td class="mono">${journey}${x.leg_nm ? `<small class="muted cgo-leg" title="Great-circle distance from where it is now, and a typical jet's block time">${fmt(x.leg_nm)} nm · about ${Math.floor(x.leg_block_min / 60)}h ${String(x.leg_block_min % 60).padStart(2, "0")}m</small>` : ""}</td>
          <td><span class="cgo-com">${esc(x.commodity || "—")}</span>${x.season_name ? ` <span class="tag cgo-season">${esc(x.season_name)}</span>` : ""}<small class="muted">${esc(x.shipper || "")} → ${esc(x.consignee || "")}</small></td>
          <td class="r mono">${fmt(x.pieces)} · ${fmt(x.gross_weight_lbs)} lb</td>
          <td><span class="cargo-status ${esc((x.status || "").toLowerCase())}">${esc(statusWord[x.status] || x.status)}</span></td>
          <td class="cgo-when">${x.deadline && (x.status === "AT_STATION" || x.status === "HELD_AT_STATION") ? `<span class="${x.deadline * 1000 < Date.now() ? "cgo-late" : ""}">Due ${cargoInventoryDate(x.deadline)}</span>` : cargoInventoryDate(x.updated_at)}${x.last_flight ? `<small class="muted">${esc(x.last_flight)}</small>` : x.is_order ? `<small class="muted">Customer order</small>` : ""}</td></tr>`;
      }).join("") || "";
      $("#cargoList").querySelectorAll(".cgo-row").forEach(tr => {
        const toggle = () => toggleCargoHistory(tr);
        tr.onclick = e => { if (!e.target.closest("a")) toggle(); }; tr.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } };
      });
    } catch (e) {
      if (request === requestNo) { $("#cargoResults").textContent = "Cargo inventory could not be loaded."; $("#cargoList").innerHTML = `<tr><td colspan="6"><p class="notice err">${esc(e.message)}</p></td></tr>`; }
    }
  };
  $("#cgoStrip").onclick = e => { const b = e.target.closest("[data-cgo-view]"); if (!b) return; S.cargoView = b.dataset.cgoView; dest = ""; drawStrip(); refresh(); };
  station.onchange = () => { dest = ""; refresh(); };
  $("#cgoAll").onchange = refresh;
  search.oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(refresh, 250); };
  await refresh();
}

function cargoInventoryDate(timestamp) {
  if (!timestamp) return "—";
  const d = new Date(timestamp * 1000);
  return `${String(d.getUTCDate()).padStart(2, "0")} ${d.toLocaleString("en-US", { month: "short", timeZone: "UTC" }).toUpperCase()} ${String(d.getUTCHours()).padStart(2, "0")}${String(d.getUTCMinutes()).padStart(2, "0")}Z`;
}

const CARGO_EVENT = {
  BOOKED: e => `Booked on ${e.flight_number || "a PAC flight"}`,
  TRANSFER_BOOKED: e => `Booked for its next leg on ${e.flight_number || "a PAC flight"}`,
  TRANSFER_CANCELLED: e => `Booking cancelled, waiting at ${e.to_station || "the station"} again`,
  FLIGHT_ARRIVAL: e => (e.details?.care ? (x => x + ` · ${e.details.care.label}`) : (x => x))(e.details?.trucked_from ? `Arrived ${e.to_station}, then by truck to ${e.details.final_destination}: delivered${e.status === "DELIVERED_LATE" ? " late" : ""}` : ({ DELIVERED: `Arrived ${e.to_station}, delivered`, DELIVERED_LATE: `Arrived ${e.to_station}, delivered late`, AT_STATION: `Arrived ${e.to_station}, waiting for its next leg`,
    HELD_AT_STATION: `Diverted to ${e.to_station}, held there`, EXCEPTION: `Arrived ${e.to_station}: exception` }[e.status] || `Arrived ${e.to_station}`)),
  ORDER_RECEIVED: e => `Order received at ${e.to_station}${e.details?.truck_from ? ` (flies to ${e.details.truck_from}, then by truck)` : ""}${e.details?.deadline ? `, due by ${cargoInventoryDate(e.details.deadline)}` : ""}`,
  ORDER_WITHDRAWN: e => `Not picked up in time: moved to another carrier`,
  CLAIMED: e => `Held for ${e.pilot_name || e.pilot_id || "a pilot"}'s next flight (24 hours)`,
  TRANSFER_RELEASED: e => `Back on the shelf at ${esc(e.from_station || "")}: the flight it was booked on sat unflown for three days`,
  FLIGHT_REJECTED: e => `Flight rejected, back at ${e.to_station}`,
  FLIGHT_NOT_CREDITED: e => `Flight not credited; cargo offloaded and inspected at ${e.to_station}`,
  FLIGHT_REINSTATED: e => `Flight accepted after review, at ${e.to_station}`,
};

function cargoNotesHTML(notes, canNote) {
  const list = (notes || []).map(n => `<li><b>${esc(n.pilot_name || n.pilot_id)}</b> <small class="muted">${esc(n.pilot_id)} · at ${esc(n.station || "")} · ${cargoInventoryDate(n.created_at)}</small>${S.me?.staff ? ` <button type="button" class="linkish" data-note-del="${n.id}">Remove</button>` : ""}<p>${esc(n.text)}</p></li>`).join("");
  return `${list ? `<h4>Handover notes</h4><ul class="cgo-note-list">${list}</ul>` : ""}
    ${canNote ? `<form class="cgo-note-form"><label for="cgoNote">Leave a handover note for the next pilot</label><textarea id="cgoNote" maxlength="280" rows="2" placeholder="For example: AKE in M04, straps checked. Consignee wants it before 0600Z."></textarea><button class="btn small" type="submit">Add note</button></form>` : ""}`;
}
function bindCargoNotes(root, id) {
  const box = root.querySelector(`[data-notes-for="${id}"]`); if (!box) return;
  const f = box.querySelector("form");
  if (f) f.onsubmit = async e => {
    e.preventDefault(); e.stopPropagation();
    try { const r = await api(`/api/cargo/shipments/${encodeURIComponent(id)}/notes`, { method: "POST", body: { text: f.querySelector("textarea").value } }); box.innerHTML = cargoNotesHTML(r.notes, true); bindCargoNotes(root, id); toast("Note left for the next pilot."); }
    catch (err) { toast(err.message); }
  };
  box.querySelectorAll("[data-note-del]").forEach(b => b.onclick = async ev => {
    ev.stopPropagation();
    try { await api(`/api/staff/cargo/notes/${b.dataset.noteDel}`, { method: "DELETE" }); b.closest("li").remove(); } catch (err) { toast(err.message); }
  });
  box.onclick = ev => ev.stopPropagation();
}
async function toggleCargoHistory(tr) {
  const open = tr.nextElementSibling?.classList.contains("cgo-hist");
  if (open) { tr.nextElementSibling.remove(); tr.setAttribute("aria-expanded", "false"); return; }
  tr.setAttribute("aria-expanded", "true");
  const row = document.createElement("tr"); row.className = "cgo-hist";
  row.innerHTML = `<td colspan="6"><p class="muted">Loading history…</p></td>`;
  tr.after(row);
  try {
    const { shipment, movements, notes = [], can_note, claim = {} } = await api(`/api/cargo/shipments/${encodeURIComponent(tr.dataset.cargoId)}`);
    const d = shipment.data || {}, a = d.awb_doc || {};
    row.firstElementChild.innerHTML = `<div class="cgo-hist-grid">
      <ol class="cgo-events">${(movements || []).map(e => `<li><span class="cargo-event-time">${cargoInventoryDate(e.event_time)}</span>
        <span><b>${esc((CARGO_EVENT[e.event_type] || (x => (x.event_type || "").replaceAll("_", " ").toLowerCase()))(e))}</b>
        ${e.pilot_id ? `<small class="muted">${esc(e.pilot_name || "")} ${esc(e.pilot_id)}</small>` : ""}
        ${e.pirep_id ? `<button type="button" class="linkish" data-pirep="${e.pirep_id}">PIREP</button>` : ""}</span></li>`).join("") || "<li class='muted'>No movements yet.</li>"}</ol>
      <dl class="cgo-facts"><dt>Tracking</dt><dd>${trackAwb(shipment.awb)}</dd><dt>Shipper</dt><dd>${esc(shipment.shipper)}</dd><dt>Consignee</dt><dd>${esc(shipment.consignee)}</dd>
        ${d.agent ? `<dt>Forwarder</dt><dd>${esc(d.agent)}</dd>` : ""}<dt>Handling</dt><dd>${esc((shipment.handling || []).join(" · ") || (d.shc || []).join(" ") || "General")}</dd>
        ${a.chg_kg ? `<dt>Chargeable</dt><dd>${cf1(a.chg_kg)} kg</dd>` : ""}${a.temp ? `<dt>Temperature</dt><dd>${esc(a.temp)}</dd>` : ""}
        ${shipment.security_status ? `<dt>Security</dt><dd>${esc(shipment.security_status)}</dd>` : ""}</dl></div>
      <div class="cgo-claim">${claim.mine ? `<b>Held for you</b> until ${cargoInventoryDate(claim.until)}. Book a flight from ${esc(shipment.current_station)} and tick it under Transfer cargo. <button type="button" class="btn small ghost" data-unclaim="${esc(shipment.id)}">Release it</button>`
        : claim.held ? `<span class="muted">Held by ${esc(claim.by)} until ${cargoInventoryDate(claim.until)}.</span>`
        : claim.can ? `<button type="button" class="btn small" data-claim="${esc(shipment.id)}">Hold for my next flight (24 h)</button> <small class="muted">Or in Discord: <code>/claim ${esc(shipment.awb)}</code></small>` : ""}</div>
      <div class="cgo-notes" data-notes-for="${esc(shipment.id)}">${cargoNotesHTML(notes, can_note)}</div>`;
    row.querySelectorAll("[data-claim],[data-unclaim]").forEach(b => b.onclick = async ev => {
      ev.stopPropagation();
      try { await api(`/api/cargo/shipments/${encodeURIComponent(b.dataset.claim || b.dataset.unclaim)}/claim`, { method: b.dataset.claim ? "POST" : "DELETE" }); toast(b.dataset.claim ? "Held for your next flight for 24 hours." : "Released."); tr.nextElementSibling?.remove(); toggleCargoHistory(tr); }
      catch (err) { toast(err.message); }
    });
    row.querySelectorAll("[data-pirep]").forEach(b => b.onclick = ev => { ev.stopPropagation(); openDetail(+b.dataset.pirep); });
    bindCargoNotes(row, shipment.id);
  } catch (e) { row.firstElementChild.innerHTML = `<p class="notice err">${esc(e.message)}</p>`; }
}

/* PAC's stands on the station map: emblems with the stand number; staff can drag them into place */
function drawStands(m, d) {
  const icon = x => L.divIcon({ className: "pac-stand-ic", iconSize: [36, 44], iconAnchor: [18, 22],
    html: `<div class="pac-stand${x.placed ? "" : " approx"}"><span class="pac-logo" aria-hidden="true"></span><b>${esc(x.stand)}</b></div>` });
  if (S.stLayer) S.stLayer.remove();
  S.stLayer = L.layerGroup().addTo(m);
  S.stMarkers = {};
  d.stand_map.forEach(x => {
    const mk = L.marker([x.lat, x.lon], { icon: icon(x), draggable: false, keyboard: false, zIndexOffset: 500 })
      .bindTooltip(`<b>PAC stand ${esc(x.stand)}</b><br>${esc(x.info)}${x.placed ? "" : "<br><i>Approximate position</i>"}`, { direction: "top", offset: [0, -18] })
      .addTo(S.stLayer);
    S.stMarkers[x.stand] = mk;
  });
  const ramp = () => {  // close enough that neighboring stands (about 90 m apart) don't overlap
    const b = L.latLngBounds(d.stand_map.map(x => [x.lat, x.lon]));
    m.setView(b.getCenter(), Math.max(17, Math.min(18, m.getBoundsZoom(b, false, L.point(80, 80)))));
  };
  // zoomed out, the stands merge into one PAC badge; zoom in (or click it) to see each stand
  const center = L.latLngBounds(d.stand_map.map(x => [x.lat, x.lon])).getCenter();
  const group = L.marker(center, { keyboard: false, zIndexOffset: 600, icon: L.divIcon({ className: "pac-stand-ic", iconSize: [64, 44], iconAnchor: [32, 22],
    html: `<div class="pac-stand pac-group"><span class="pac-logo" aria-hidden="true"></span><b>${d.stand_map.length} stands</b></div>` }) })
    .bindTooltip("PAC's stands: click to zoom in", { direction: "top", offset: [0, -18] }).on("click", ramp);
  const sync = () => {
    const near = m.getZoom() >= 16 || S.stEditing;
    if (near) { if (m.hasLayer(group)) group.remove(); if (!m.hasLayer(S.stLayer)) S.stLayer.addTo(m); }
    else { if (m.hasLayer(S.stLayer)) S.stLayer.remove(); if (!m.hasLayer(group)) group.addTo(m); }
  };
  m.on("zoomend", sync); sync();
  if ($("#stZoomRamp")) $("#stZoomRamp").onclick = ramp;
  if (!$("#stPlace")) return;
  const editing = on => {
    S.stEditing = on; sync();
    Object.values(S.stMarkers).forEach(mk => on ? mk.dragging.enable() : mk.dragging.disable());
    $("#stPlace").hidden = on; $("#stPlaceBar").hidden = !on;
    $("#stMapNote").textContent = on ? "Drag each PAC emblem onto its parking spot on the ramp, then save." : $("#stMapNote").textContent;
    if (on) ramp();
  };
  $("#stPlace").onclick = () => editing(true);
  $("#stPlaceCancel").onclick = () => { S.stEditing = false; loadStation(d.icao); };
  $("#stPlaceSave").onclick = async () => {
    const positions = Object.fromEntries(Object.entries(S.stMarkers).map(([n, mk]) => { const ll = mk.getLatLng(); return [n, [ll.lat, ll.lng]]; }));
    try { await api(`/api/staff/stations/${d.icao}/stands`, { method: "POST", body: { positions } }); S.stEditing = false; toast("Stand positions saved."); loadStation(d.icao); }
    catch (e) { toast(e.message, 8000); }
  };
  $("#stPlaceReset").onclick = async () => {
    if (!confirm("Put the stands back in the approximate row?")) return;
    try { await api(`/api/staff/stations/${d.icao}/stands`, { method: "POST", body: { reset: true } }); loadStation(d.icao); } catch (e) { toast(e.message); }
  };
}
/* Describe where PAC's stands are, from their positions on the map: rows (north to south) and order along each row */
function standLayout(sm) {
  if (!sm || !sm.length) return null;
  const placed = sm.some(x => x.placed);
  const num = id => parseInt(String(id).replace(/\D/g, ""), 10) || 0;
  // meters east and north of the stands' center (one fixed reference, so latitude differences can't skew east-west distances)
  const lat0 = sm.reduce((t, x) => t + x.lat, 0) / sm.length, lon0 = sm.reduce((t, x) => t + x.lon, 0) / sm.length;
  const xy = x => [(x.lon - lon0) * 111320 * Math.cos(lat0 * Math.PI / 180), (x.lat - lat0) * 111320];
  const dist = (a, b) => { const [ax, ay] = xy(a), [bx, by] = xy(b); return Math.hypot(ax - bx, ay - by); };
  // rows: find the direction the stands line up along (principal axis), then split wherever there's a gap of more
  // than ~25 m across it. Works for rows close together, single rows in any direction, and diagonal rows.
  const P = sm.map(xy), mx = P.reduce((t, p) => t + p[0], 0) / P.length, my = P.reduce((t, p) => t + p[1], 0) / P.length;
  // try the principal direction and the one at right angles; keep whichever gives fewer rows (two rows of four, not
  // four columns of two), as a person would read the layout
  const splitAlong = ang => {
    const across = x => { const [px, py] = xy(x); return -Math.sin(ang) * (px - mx) + Math.cos(ang) * (py - my); };
    const sorted = [...sm].sort((a, b) => across(a) - across(b)), out = [[sorted[0]]];
    for (let k = 1; k < sorted.length; k++) {
      if (across(sorted[k]) - across(sorted[k - 1]) > 25) out.push([sorted[k]]); else out[out.length - 1].push(sorted[k]);
    }
    return out;
  };
  // try every direction (5 degree steps); among those that give narrow rows, keep the fewest rows; on a tie, the tightest
  let rows = null, best = null;
  for (let deg = 0; deg < 180; deg += 5) {
    const ang = deg * Math.PI / 180, cand = splitAlong(ang);
    const across = x => { const [px, py] = xy(x); return -Math.sin(ang) * (px - mx) + Math.cos(ang) * (py - my); };
    const spread = Math.max(...cand.map(r => Math.max(...r.map(across)) - Math.min(...r.map(across))));
    const ok = spread <= 35;  // a real row is narrow: its stands sit within ~35 m of a line
    if (!best || (ok && !best.ok) || (ok === best.ok && (cand.length < best.n || (cand.length === best.n && spread < best.spread)))) { best = { ok, n: cand.length, spread }; rows = cand; }
  }
  const cen = r => [r.reduce((t, x) => t + xy(x)[0], 0) / r.length, r.reduce((t, x) => t + xy(x)[1], 0) / r.length];
  // name the rows by how they sit relative to each other
  let names;
  if (rows.length === 1) names = ["single row"];
  else {
    const cs = rows.map(cen), spanE = Math.max(...cs.map(c => c[0])) - Math.min(...cs.map(c => c[0])), spanN = Math.max(...cs.map(c => c[1])) - Math.min(...cs.map(c => c[1]));
    const ns = spanN >= spanE;
    rows = rows.map((r, i) => ({ r, c: cs[i] })).sort((p, q) => ns ? q.c[1] - p.c[1] : q.c[0] - p.c[0]).map(o => o.r);
    const ends = ns ? ["north", "south"] : ["east", "west"];
    names = rows.map((_, i) => i === 0 ? `${ends[0]} row` : i === rows.length - 1 ? `${ends[1]} row` : rows.length === 3 ? "middle row" : `row ${i + 1}`);
  }
  const ord = n => n + (n % 10 === 1 && n !== 11 ? "st" : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th");
  const where = {}, parts = [];
  rows.forEach((r, i) => {
    const pts = r.map(xy), spanE = Math.max(...pts.map(p => p[0])) - Math.min(...pts.map(p => p[0])), spanN = Math.max(...pts.map(p => p[1])) - Math.min(...pts.map(p => p[1]));
    const ew = spanE >= spanN, axis = ew ? 0 : 1;                       // the row's main direction
    const first = r.reduce((m, x) => num(x.stand) < num(m.stand) ? x : m, r[0]);  // numbering starts here
    const vals = r.map(x => xy(x)[axis]), hi = xy(first)[axis] >= Math.max(...vals) - 1;
    const side = ew ? (hi ? "east" : "west") : (hi ? "north" : "south");
    [...r].sort((a, b) => hi ? xy(b)[axis] - xy(a)[axis] : xy(a)[axis] - xy(b)[axis]).forEach((x, k) => { where[x.stand] = { row: names[i], pos: k + 1, side }; });
    const ids = r.map(x => x.stand).sort((a, b) => num(a) - num(b));
    parts.push({ lo: num(ids[0]), text: `${ids.length > 2 ? `${ids[0]}–${ids[ids.length - 1]}` : ids.join(" and ")}${rows.length > 1 ? ` along the ${names[i]}` : ""}${r.length > 1 ? `, numbered from the ${side}` : ""}` });
  });
  parts.sort((a, b) => a.lo - b.lo);
  const list = parts.map(p => p.text);
  const joined = list.length > 1 ? `${list.slice(0, -1).join("; ")}; and ${list[list.length - 1]}` : list[0];
  const sentence = placed
    ? (rows.length === 1 ? `The stands are in a single row: ${joined}. The PAC emblems on the map mark each one.`
      : `The stands are in ${rows.length === 2 ? "two" : rows.length} rows: ${joined}. The PAC emblems on the map mark each one.`)
    : "Their exact spots are marked by the PAC emblems on the map once staff have placed them.";
  const describe = ids => {
    const w = ids.map(n => where[n]).filter(Boolean);
    if (!placed || !w.length) return "On the map";
    if (w.every(x => x.row === w[0].row && x.side === w[0].side)) {
      const pos = w.map(x => x.pos).sort((a, b) => a - b).map(ord);
      const rowTxt = w[0].row === "single row" ? "" : `${w[0].row[0].toUpperCase() + w[0].row.slice(1)}, `;
      const txt = `${rowTxt}${pos.join(" and ")} from the ${w[0].side}`;
      return txt[0].toUpperCase() + txt.slice(1);
    }
    return w.map((x, i) => `${ids[i]}: ${x.row}, ${ord(x.pos)} from the ${x.side}`).join("; ");
  };
  return { sentence, describe };
}
async function loadStation(icao) {
  const root = $("#stationsRoot");
  root.innerHTML = `<p class="muted">Loading ${esc(icao)}…</p>`;
  let d; try { d = await api(`/api/stations/${encodeURIComponent(icao)}`); } catch (e) { root.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  const g = d.guide, st = d.stats, lay = standLayout(d.stand_map);
  const fill = t => lay ? String(t).replace("{stand_layout}", lay.sentence) : String(t).replace("{stand_layout}", "");
  const withWhere = sct => !sct.stand_where || !lay ? sct.table
    : { ...sct.table, rows: sct.table.rows.map(r => [...r.slice(0, -1), lay.describe(String(r[0]).split(/,\s*/))]) };
  const table = t => `<div class="st-tablewrap"><table class="st-table"><thead><tr>${t.head.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead>
    <tbody>${t.rows.map(r => `<tr>${r.map((c, i) => `<td${i === 0 ? ' class="k"' : ""}>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  const glance = g?.glance || [["ICAO / IATA", `${d.icao} / ${d.iata || "–"}`], ["Location", `${d.city || ""}${d.country ? ", " + d.country : ""}`],
    ["Elevation", d.elev_ft != null ? `${fmt(d.elev_ft)} ft` : "–"], ["Runways", `${d.runways.length}, longest ${fmt(d.runways[0]?.length_ft || 0)} ft`]];
  root.innerHTML = `<div class="st-back"><button class="btn ghost small" type="button" id="stBack">← All stations</button>
      <button class="btn ghost small" type="button" id="stPrint">Print guide</button></div>
    <div class="st-head"><div><h1 class="st-h1">${esc(d.icao)}</h1><div class="st-sub">${esc(g?.name || d.name)}${g?.role ? ` · <b>${esc(g.role)}</b>` : d.hub ? " · <b>PAC hub</b>" : ""}</div>
      <div class="muted">${esc(d.city || "")}${d.country ? ", " + esc(d.country) : ""}${d.partner_hubs.length ? ` · hub of ${d.partner_hubs.map(esc).join(", ")}` : ""}</div></div>
      ${g ? `<div class="st-updated muted">Guide updated ${esc(g.updated)}</div>` : ""}</div>
    <div class="st-top">
      <section class="st-panel"><h2>At a glance</h2><dl class="st-dl">${glance.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl></section>
      <section class="st-panel st-mapwrap"><div id="stMap" class="st-map"></div>
        ${d.stand_map ? `<div class="st-mapbar"><button class="btn ghost small" type="button" id="stZoomRamp">Zoom to PAC ramp</button>
          ${S.me?.staff ? `<button class="btn ghost small" type="button" id="stPlace">Position stands</button><span id="stPlaceBar" hidden><button class="btn small" type="button" id="stPlaceSave">Save positions</button>
            <button class="btn ghost small" type="button" id="stPlaceCancel">Cancel</button><button class="btn ghost small" type="button" id="stPlaceReset" title="Back to the approximate row">Reset</button></span>` : ""}</div>` : ""}
        <small class="muted" id="stMapNote">Satellite imagery with the runways drawn from their published thresholds.${d.stand_map ? (d.stand_map.some(x => x.placed) ? " PAC emblems mark PAC's stands." : " PAC's stand positions are approximate until staff place them.") : ""}</small></section>
    </div>
    <section class="st-panel"><h2>Weather now</h2><div id="stWx" class="st-wx muted">Loading the latest METAR and TAF…</div></section>
    ${!g && d.stand_map ? `<section class="st-panel st-fiction"><h2>PAC stands <span class="tag ${d.stand_source?.published ? "green" : "amber"}">${d.stand_source?.published ? "Published positions" : "PAC (fictional)"}</span></h2>
      <p>${esc(d.stand_source?.where || "")}. Stands are allocated by aircraft size, and ACARS sends yours at top of descent.${lay && d.stand_map.some(x => x.placed) ? " " + esc(lay.sentence.replace(" The PAC emblems on the map mark each one.", "")) : ""}</p>
      ${table({ head: ["Stand", "Size", "PAC aircraft", "Where on the ramp"], rows: (() => {
        const bySize = {}; d.stand_map.forEach(x => (bySize[x.size] ||= []).push(x.stand));
        return ["F", "E", "D", "C"].filter(k => bySize[k]).map(k => { const [code, ac] = (d.stand_map.find(x => x.size === k).info || "").split(": ");
          return [bySize[k].join(", "), code, ac || "", lay ? lay.describe(bySize[k]) : "On the map"]; }); })() })}
      ${d.stand_source?.note ? `<p class="st-note">${esc(d.stand_source.note)}</p>` : ""}</section>` : ""}
    ${g ? "" : `<section class="st-panel"><h2>Runways</h2>${table({ head: ["Runway", "Length × width", "Headings (true)", "PAC aircraft that can use it"],
        rows: d.runways.map(r => [r.ids, `${fmt(r.length_ft)} × ${fmt(r.width_ft || 0)} ft`, `${r.headings[0]}° / ${r.headings[1]}°`, r.types.join(", ") || "None"]) })}</section>`}
    ${(g?.sections || []).map(sct => `<section class="st-panel ${sct.fictional ? "st-fiction" : ""}"><h2>${esc(sct.title)}${sct.fictional ? ` <span class="tag amber">PAC (fictional)</span>` : ""}</h2>
        ${(sct.body || []).map(p => fill(p)).filter(Boolean).map(p => `<p>${esc(p)}</p>`).join("")}${sct.table ? table(withWhere(sct)) : ""}${sct.note ? `<p class="st-note">${esc(sct.note)}</p>` : ""}</section>`).join("")}
    ${g ? `<section class="st-panel"><h2>Which PAC aircraft fit which runway</h2>${table({ head: ["Runway", "Length", "PAC aircraft that can use it"], rows: d.runways.map(r => [r.ids, `${fmt(r.length_ft)} ft`, r.types.join(", ")]) })}</section>` : ""}
    <section class="st-panel"><h2>Your record here</h2>${st.flights ? `<p>${st.flights} ${st.flights === 1 ? "flight" : "flights"} (${st.departures} out, ${st.arrivals} in). Last: <a href="#" data-pirep="${st.last.id}">${esc(st.last.flight_number)} ${esc(st.last.dep)}–${esc(st.last.arr)}</a>.${st.best_landing ? ` Best landing here: <a href="#" data-pirep="${st.best_landing.id}">${st.best_landing.landing_rate} fpm</a>.` : ""}</p>` : `<p class="muted">You haven't flown here yet.</p>`}</section>
    <section class="st-panel"><h2>Charts</h2><p>${d.charts.map(([t, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)}</a>`).join(" · ")}</p>
      <p class="st-note">PAC guides are for flight simulation. Always fly from current charts for the AIRAC cycle you're using.</p></section>
    ${g?.sources ? `<section class="st-panel"><h2>Sources</h2><ul class="st-sources">${g.sources.map(([t, u]) => `<li><a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)}</a></li>`).join("")}</ul></section>` : ""}`;
  $("#stBack").onclick = () => { S.stationIcao = null; loadStations(); };
  $("#stPrint").onclick = () => print();
  root.querySelectorAll("[data-pirep]").forEach(a => a.onclick = e => { e.preventDefault(); openDetail(+a.dataset.pirep); });
  // satellite map with the runways drawn on
  if (HAS_MAP && d.runways.length) {
    if (S.stMap) { S.stMap.remove(); S.stMap = null; }
    const m = S.stMap = L.map("stMap", { zoomControl: true, attributionControl: true, scrollWheelZoom: false });
    MAP_STYLES.satellite.layers.forEach(([u, z], i) => L.tileLayer(u, { maxNativeZoom: z, maxZoom: 19, attribution: i ? "" : MAP_STYLES.satellite.attr }).addTo(m));
    const pts = [];
    d.runways.forEach(r => {
      const [a, b] = r.ends; pts.push(a, b);
      L.polyline([a, b], { color: "#fff", weight: 3, opacity: .85 }).addTo(m);
      const [ia, ib] = r.ids.split("/");
      [[a, ia], [b, ib]].forEach(([p, lab]) => L.marker(p, { icon: L.divIcon({ className: "rwy-lab", html: esc(lab), iconSize: [34, 18], iconAnchor: [17, 9] }) }).addTo(m));
    });
    m.fitBounds(pts, { padding: [20, 20] });
    if (d.stand_map) drawStands(m, d);
  } else if (!HAS_MAP) $("#stMap").innerHTML = `<p class="muted" style="padding:20px">The map needs an internet connection.</p>`;
  // live weather
  try {
    const w = (await api(`/api/weather?taf=1&ids=${encodeURIComponent(d.icao)}`))[d.icao] || {};
    $("#stWx").classList.remove("muted");
    $("#stWx").innerHTML = `<div class="mono">${esc(w.metar?.raw || "No METAR available")}</div>${w.metar?.summary ? `<p>${esc(w.metar.summary)}</p>` : ""}
      ${w.taf?.lines?.length ? `<div class="mono st-taf">${w.taf.lines.map(esc).join("<br>")}</div>` : ""}`;
  } catch (e) { $("#stWx").textContent = "Weather isn't available right now."; }
}

/* ================= Downloads center ================= */
async function loadDownloads() {
  const root = $("#downloadsRoot");
  let d; try { d = await api("/api/downloads"); } catch (e) { root.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  const staff = !!S.me?.staff, mb = b => b >= 1_048_576 ? `${(b / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`;
  const ac = d.acars;
  const byCat = Object.fromEntries(d.categories.map(c => [c, d.files.filter(f => f.category === c)]));
  // web addresses in descriptions become links
  const linkify = t => esc(t).replace(/\bhttps?:\/\/[^\s<]+[^\s<.,;:!?)]/g, u => `<a href="${u}" target="_blank" rel="noopener">${u}</a>`);
  const simKey = sim => /x-?plane/i.test(sim || "") ? "xp" : /msfs/i.test(sim || "") ? "msfs" : "";
  const fileRow = f => `<div class="dl-row" data-dl-id="${f.id}" data-sim="${simKey(f.sim)}" data-ac="${esc(f.aircraft || "")}"><div><b>${esc(f.title)}</b>${f.version ? ` <span class="tag grey">v${esc(f.version)}</span>` : ""}${f.aircraft ? ` <span class="tag dark">${esc(S.fleet[f.aircraft]?.icao || f.aircraft)}</span>` : ""}${f.sim ? ` <span class="tag grey">${esc(f.sim)}</span>` : ""}
      ${f.description ? `<p style="white-space:pre-line">${linkify(f.description)}</p>` : ""}<small class="muted">${esc(f.filename)} · ${mb(f.size)} · ${f.downloads} ${f.downloads === 1 ? "download" : "downloads"} · added ${new Date(f.uploaded * 1000).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" })}</small></div>
      <div class="dl-actions"><a class="btn small" href="/api/downloads/${f.id}/file">Download</a>${staff ? `<button class="btn ghost small" type="button" data-dl-edit="${f.id}">Edit</button><button class="btn ghost small" type="button" data-dl-del="${f.id}">Remove</button>` : ""}</div></div>`;
  // the livery filter: simulator and aircraft, remembered on this computer
  const liveries = byCat.Livery || [];
  let pref = {}; try { pref = JSON.parse(localStorage.getItem("pac-dl-filter") || "{}"); } catch (e) { pref = {}; }
  const acList = [...new Set(liveries.map(f => f.aircraft).filter(Boolean))]
    .sort((a, b) => (S.fleet[a]?.name || a).localeCompare(S.fleet[b]?.name || b, undefined, { numeric: true }));
  const shortName = k => (S.fleet[k]?.name || k).replace(/^(Boeing|Airbus|McDonnell Douglas)\s+/, "");
  const liveryFilter = liveries.length > 4 && staff ? `<div class="dl-filter" role="group" aria-label="Filter liveries">
      <div class="dl-chips" data-group="sim"><span class="dl-flabel">Simulator</span>${[["", "All"], ["msfs", "MSFS"], ["xp", "X-Plane"]].map(([v, l]) => `<button type="button" class="dl-chip" data-v="${v}" aria-pressed="${(pref.sim || "") === v}">${l}</button>`).join("")}</div>
      <div class="dl-chips" data-group="ac"><span class="dl-flabel">Aircraft</span><button type="button" class="dl-chip" data-v="" aria-pressed="${!pref.ac}">All</button>${acList.map(k => `<button type="button" class="dl-chip" data-v="${esc(k)}" aria-pressed="${pref.ac === k}">${esc(shortName(k))}</button>`).join("")}</div>
      <span class="muted dl-count" id="dlCount" aria-live="polite"></span></div>` : "";
  root.innerHTML = `<div class="profile-bar"><h1>Downloads</h1><span class="muted">Everything you need to fly for PAC. Liveries are on the <a href="#fleet" onclick="show('fleet');return false">Fleet page</a>, under each aircraft.</span></div>
    <section class="dl-sec"><h2>PAC ACARS</h2>
      ${ac ? `<div class="dl-row"><div><b>PAC ACARS ${esc(verLabel(ac.version))}</b><p>Tracks your flights from MSFS or X-Plane, talks to PAC Operations and files your PIREP.</p></div>
        <div class="dl-actions">${ac.installer ? `<a class="btn small" href="${esc(ac.installer.url)}">Installer (${ac.installer.size_mb} MB)</a>` : ""}${ac.portable ? `<a class="btn ghost small" href="${esc(ac.portable.url)}">Portable zip (${ac.portable.size_mb} MB)</a>` : ""}</div></div>`
        : `<p class="muted">No PAC ACARS build here yet.${staff ? " Build it on Windows with <code>acars_client\\build\\build_acars.bat</code>, then upload <code>PAC-ACARS-…-portable.zip</code> or <code>PAC-ACARS-Setup-….exe</code> from your <code>static\\downloads</code> folder." : " Ask staff to upload one."}</p>`}
      ${staff ? `<div class="row" style="margin-top:10px;align-items:center">
        <label class="btn ghost small" style="cursor:pointer">Upload a PAC ACARS build…<input type="file" id="acarsUp" accept=".exe,.zip" hidden></label>
        ${ac?.installer ? `<button class="btn ghost small" type="button" data-acars-del="${esc(ac.installer.file)}">Remove ${esc(ac.installer.file)}</button>` : ""}
        ${ac?.portable ? `<button class="btn ghost small" type="button" data-acars-del="${esc(ac.portable.file)}">Remove ${esc(ac.portable.file)}</button>` : ""}
        <span class="muted" id="acarsUpMsg" style="font-size:13px">Pilots download it from here once uploaded.</span></div>` : ""}</section>
    <section class="dl-sec" id="siCard"></section>
    ${d.categories.filter(c => byCat[c].length || c === "Livery" || c === "Document").map(c => `<section class="dl-sec"><h2>${{ Livery: "Liveries", Checklist: "Checklists", Document: "Documents", Scenery: "Scenery", Other: "Other files" }[c]}</h2>
      ${c === "Livery" ? liveryFilter : ""}
      ${c === "Livery" ? `<div class="notice" style="display:flex;gap:14px;align-items:center;flex-wrap:wrap"><span style="flex:1;min-width:240px"><b>PAC liveries are on the Fleet page.</b> Each one sits with its aircraft, with a preview and credit to its painter, for MSFS and X-Plane.</span><button class="btn small" type="button" onclick="show('fleet')">Get liveries on the Fleet page →</button></div>${byCat[c].length && staff ? `<p class="muted" style="font-size:13px">Staff: the files below are older copies. Delete them to free space; pilots get liveries from the Fleet page.</p>` : ""}` : ""}${byCat[c].length && (c !== "Livery" || staff) ? `<div ${c === "Livery" ? 'id="dlLiveries"' : ""}>${byCat[c].map(fileRow).join("")}</div>${c === "Livery" ? `<p class="muted" id="dlNone" hidden>No liveries for that aircraft in that simulator yet.</p>` : ""}` : ""}
      ${c === "Document" ? `
        <div class="dl-row"><div><b>KCVG station guide</b><p>Cincinnati in detail: runways, frequencies, cargo ramps, procedures and PAC's stands.</p></div><div class="dl-actions"><button class="btn ghost small" type="button" data-station="KCVG">Open to print</button></div></div>
        <div class="dl-row"><div><b>Unicom cheat sheet (no ATC online)</b><p>What to do and exactly what to say on VATSIM or IVAO Unicom 122.800 when there's no controller — phase by phase, with copy-paste text calls.</p></div><div class="dl-actions"><a class="btn ghost small" href="/unicom" target="_blank" rel="noopener">VATSIM / combined</a><a class="btn ghost small" href="/unicom/ivao" target="_blank" rel="noopener">IVAO</a><a class="btn small" href="/unicom/flight" target="_blank" rel="noopener">⚡ Generate for a flight</a></div></div>` : ""}</section>`).join("")}
    <section class="dl-sec"><h2>SimBrief airframes</h2>
      <p class="muted" style="margin:0 0 10px">Set up a SimBrief airframe for each PAC aircraft so your plans use PAC's weights. Prefer your own (different engines, weights or equipment)? Paste its Internal ID under <b>My SimBrief airframe</b> and PAC's Generate OFP button will plan with it, as long as it's the same aircraft type. Where there's a ready-made PAC airframe, press <b>Add PAC's airframe to SimBrief</b>. Otherwise, in SimBrief: Account › Airframes › New airframe, choose the type and enter the values below. Plans made with PAC's Generate OFP button already use PAC's airframes.</p>
      <div class="sb-grid">${d.simbrief.map(x => `<div class="sb-card"><div class="sb-top"><b>${esc(x.name)}</b><span class="tag dark">${esc(x.simbrief_type)}</span></div>
        <dl><dt>Empty (OEW)</dt><dd>${fmt(x.oew_lbs)} lb</dd><dt>Max zero fuel</dt><dd>${fmt(x.mzfw_lbs)} lb</dd><dt>Max takeoff</dt><dd>${fmt(x.mtow_lbs)} lb</dd>
          <dt>Max landing</dt><dd>${fmt(x.mlw_lbs)} lb</dd><dt>Max payload</dt><dd>${fmt(x.max_payload_lbs)} lb</dd><dt>Callsign</dt><dd>${esc(x.airline)} / ${esc(x.callsign)}</dd></dl>
        <small class="muted">${x.registrations.length ? `PAC tails: ${x.registrations.slice(0, 6).map(esc).join(", ")}${x.registrations.length > 6 ? "…" : ""}` : "No PAC tails yet"}</small>
        ${x.simbrief_airframe ? `<a class="btn small" href="https://dispatch.simbrief.com/airframes/share/${encodeURIComponent(x.simbrief_airframe)}" target="_blank" rel="noopener" title="Adds PAC's ready-made airframe to your SimBrief fleet">Add PAC's airframe to SimBrief ↗</a>` : ""}
        <a class="btn ghost small" href="/api/downloads/simbrief/${encodeURIComponent(x.code)}.txt">Download sheet</a>
        ${S.me ? (() => { const sims = ["MSFS", "X-Plane"].filter(z => fliesIn(x.code, z)), mine = myAirframes(x.code);
          return `<div class="sb-mine" data-sb-type="${esc(x.code)}"><b style="font-size:13px">My SimBrief airframe <span class="muted" style="font-weight:400">(optional, must be a ${esc(x.icao)})</span></b>
            ${sims.map(z => `<label>${sims.length > 1 ? esc(z) : `<span class="sr-only">${esc(z)}</span>`}<input data-sb-sim="${z}" value="${esc(mine[z] || "")}" placeholder="Internal ID, e.g. 277074_1793915409207" autocomplete="off"></label>`).join("")}
            <div class="row"><button class="btn small" type="button" data-sb-save>Save</button>${Object.keys(mine).length ? `<button class="btn ghost small" type="button" data-sb-clear>Use PAC's</button>` : ""}</div>
            <small class="muted">Plans use: ${sims.map(z => `${sims.length > 1 ? esc(z) + " " : ""}<b>${mine[z] ? "your airframe" : x.simbrief_airframe ? "PAC's airframe" : `SimBrief's standard ${esc(x.simbrief_type)}`}</b>`).join(" · ")}</small>
            ${sims.length > 1 ? `<small class="muted">Fly this type in both sims with different add-ons? Save one for each, then pick the sim when you generate the OFP.</small>` : ""}</div>`; })() : ""}</div>`).join("")}</div></section>
    ${staff ? `<section class="dl-sec dl-upload"><h2>Upload a file <span class="tag grey">Staff</span></h2>
      <form id="dlForm" class="dl-form">
        <div class="field"><label for="dlFile">File (zip, pdf, image, text; up to 2 GB)</label><input id="dlFile" name="file" type="file" required></div>
        <div class="field"><label for="dlTitle">Title</label><input id="dlTitle" name="title" placeholder="PAC 777F livery" required></div>
        <div class="field"><label for="dlCat">Category</label><select id="dlCat" name="category">${d.categories.map(c => `<option>${c}</option>`).join("")}</select></div>
        <div class="field"><label for="dlAc">Aircraft</label><select id="dlAc" name="aircraft"><option value="">Any / not aircraft-specific</option>${Object.entries(S.fleet).filter(([, v]) => !v.retired).map(([k, v]) => `<option value="${k}">${esc(v.name)}</option>`).join("")}</select></div>
        <div class="field"><label for="dlSim">Simulator</label><select id="dlSim" name="sim"><option value="">Any</option><option>MSFS</option><option>MSFS 2024</option><option>X-Plane</option></select></div>
        <div class="field"><label for="dlVer">Version</label><input id="dlVer" name="version" placeholder="1.0"></div>
        <div class="field full"><label for="dlDesc">Description</label><textarea id="dlDesc" name="description" rows="2" maxlength="2000" placeholder="Which add-on it's for, how to install it"></textarea></div>
        <div class="full row"><button class="btn small" type="submit">Upload</button><span class="muted" id="dlProg" style="font-size:13px"></span></div></form></section>` : ""}`;
  loadSiCard();
  if ($("#acarsUp")) $("#acarsUp").onchange = e => {
    const file = e.target.files[0]; if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.upload.onprogress = ev => { if (ev.lengthComputable) $("#acarsUpMsg").textContent = `Uploading ${file.name}… ${Math.round(ev.loaded / ev.total * 100)}%`; };
    xhr.onload = () => { let r = {}; try { r = JSON.parse(xhr.responseText); } catch (err) { /* not JSON */ }
      if (xhr.status === 200) { toast(r.file && r.file !== file.name ? `PAC ACARS uploaded as ${r.file}. Pilots can download it now.` : "PAC ACARS uploaded. Pilots can download it now."); loadDownloads(); }
      else { $("#acarsUpMsg").textContent = ""; toast(r.error || `Upload failed (HTTP ${xhr.status}).`, 9000); } };
    xhr.onerror = () => { $("#acarsUpMsg").textContent = ""; toast("Upload failed."); };
    xhr.open("POST", "/api/staff/acars/build"); xhr.send(fd);
  };
  document.querySelectorAll("[data-sb-type]").forEach(box => {
    const save = async v => {
      try {
        const r = await api("/api/my/airframes", { method: "POST", body: { type: box.dataset.sbType, airframes: v } });
        S.settings.simbrief_airframes = r.simbrief_airframes;
        toast(Object.values(v).some(Boolean) ? "Saved. PAC's Generate OFP button now plans with your airframe." : "Back to PAC's airframe.");
        loadDownloads();
      } catch (e) { toast(e.message); }
    };
    box.querySelector("[data-sb-save]").onclick = () => { const v = {}; box.querySelectorAll("[data-sb-sim]").forEach(i => v[i.dataset.sbSim] = i.value.trim()); save(v); };
    const clr = box.querySelector("[data-sb-clear]"); if (clr) clr.onclick = () => save({});
  });
  document.querySelectorAll("[data-acars-del]").forEach(b => b.onclick = async () => {
    if (!confirm(`Remove ${b.dataset.acarsDel}? Pilots won't be able to download it.`)) return;
    try { await api(`/api/staff/acars/build/${encodeURIComponent(b.dataset.acarsDel)}`, { method: "DELETE" }); loadDownloads(); } catch (e) { toast(e.message); }
  });
  if ($("#dlHandbook")) $("#dlHandbook").onclick = () => { show("handbook"); setTimeout(() => print(), 600); };
  const applyFilter = () => {
    const rows = [...root.querySelectorAll("#dlLiveries .dl-row")];
    let shown = 0;
    rows.forEach(r => { const ok = (!pref.sim || !r.dataset.sim || r.dataset.sim === pref.sim) && (!pref.ac || r.dataset.ac === pref.ac); r.hidden = !ok; if (ok) shown++; });
    if ($("#dlCount")) $("#dlCount").textContent = shown === rows.length ? `${rows.length} liveries` : `Showing ${shown} of ${rows.length}`;
    if ($("#dlNone")) $("#dlNone").hidden = shown > 0;
  };
  root.querySelectorAll(".dl-chips").forEach(g => g.querySelectorAll(".dl-chip").forEach(b => b.onclick = () => {
    pref[g.dataset.group] = b.dataset.v;
    g.querySelectorAll(".dl-chip").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    try { localStorage.setItem("pac-dl-filter", JSON.stringify(pref)); } catch (e) { /* private window */ }
    applyFilter();
  }));
  if (pref.ac && !acList.includes(pref.ac)) pref.ac = "";
  applyFilter();
  // staff: edit a file's details without re-uploading it
  root.querySelectorAll("[data-dl-edit]").forEach(b => b.onclick = () => {
    const f = d.files.find(x => String(x.id) === b.dataset.dlEdit), row = b.closest(".dl-row");
    row.hidden = false;
    row.innerHTML = `<form class="dl-form dl-edit">
      <div class="field"><label>Title</label><input name="title" value="${esc(f.title)}" maxlength="120" required></div>
      <div class="field"><label>Category</label><select name="category">${d.categories.map(c => `<option ${c === f.category ? "selected" : ""}>${c}</option>`).join("")}</select></div>
      <div class="field"><label>Version</label><input name="version" value="${esc(f.version || "")}" maxlength="20"></div>
      <div class="field"><label>Aircraft</label><select name="aircraft"><option value="">Any / not aircraft-specific</option>${Object.entries(S.fleet).filter(([k, v]) => !v.retired || k === f.aircraft).map(([k, v]) => `<option value="${k}" ${k === f.aircraft ? "selected" : ""}>${esc(v.name)}</option>`).join("")}</select></div>
      <div class="field"><label>Simulator</label><select name="sim">${["", "MSFS", "MSFS 2024", "X-Plane"].map(v => `<option value="${v}" ${v === (f.sim || "") ? "selected" : ""}>${v || "Any"}</option>`).join("")}</select></div>
      <div class="field full"><label>Description</label><textarea name="description" rows="4" maxlength="2000">${esc(f.description || "")}</textarea></div>
      <div class="full row"><button class="btn small" type="submit">Save</button><button class="btn ghost small" type="button" data-cancel>Cancel</button>
        <span class="muted" style="font-size:13px">${esc(f.filename)} stays as it is.</span></div></form>`;
    row.querySelector("[data-cancel]").onclick = () => loadDownloads();
    row.querySelector("form").onsubmit = async e => {
      e.preventDefault();
      const body = Object.fromEntries(new FormData(e.target));
      try { await api(`/api/staff/downloads/${f.id}`, { method: "POST", body }); toast("Saved."); loadDownloads(); } catch (err) { toast(err.message); }
    };
    row.querySelector("input").focus();
  });
  root.querySelectorAll("[data-dl-del]").forEach(b => b.onclick = async () => {
    if (!confirm("Remove this file from the downloads center?")) return;
    try { await api(`/api/staff/downloads/${b.dataset.dlDel}`, { method: "DELETE" }); loadDownloads(); } catch (e) { toast(e.message); }
  });
  if ($("#dlForm")) $("#dlForm").onsubmit = e => {
    e.preventDefault();
    const fd = new FormData(e.target), xhr = new XMLHttpRequest(), btn = e.target.querySelector("button");
    btn.disabled = true;
    xhr.upload.onprogress = ev => { if (ev.lengthComputable) $("#dlProg").textContent = `Uploading… ${Math.round(ev.loaded / ev.total * 100)}%`; };
    xhr.onload = () => { btn.disabled = false; let r = {}; try { r = JSON.parse(xhr.responseText); } catch (err) { /* not JSON */ }
      if (xhr.status === 200) { toast("Uploaded."); loadDownloads(); } else { $("#dlProg").textContent = ""; toast(r.error || `Upload failed (HTTP ${xhr.status}).`, 8000); } };
    xhr.onerror = () => { btn.disabled = false; $("#dlProg").textContent = ""; toast("Upload failed. Is the PAC website still running?"); };
    xhr.open("POST", "/api/staff/downloads"); xhr.send(fd);
  };
}

/* ================= PAC's email account ================= */
async function renderGroupBox(g) {
  const box = $("#groupBox"); if (!box) return;
  try { g = g || await api("/api/staff/group"); } catch (e) { box.innerHTML = `<span class="muted" style="font-size:13px">${esc(e.message)}</span>`; return; }
  const save = async body => { try { renderGroupBox(await api("/api/staff/group", { method: "POST", body })); } catch (e) { toast(e.message); } };
  box.innerHTML = `<label class="switch-row" style="margin:0 0 8px"><input type="checkbox" id="grpOn" ${g.enabled ? "checked" : ""}><span><b>Share PAC with the group hub</b><br><span class="muted" style="font-size:13px">Off: the feed answers nobody, even with the key.</span></span></label>
    <div class="field" style="margin:0 0 8px"><label for="grpUrl">Feed address</label><input id="grpUrl" readonly value="${esc(g.url)}" style="width:100%;font-family:var(--mono);font-size:12px"></div>
    <div class="field" style="margin:0 0 8px"><label for="grpKey">Group key</label><input id="grpKey" readonly value="${esc(g.key)}" style="width:100%;font-family:var(--mono);font-size:12px"></div>
    <div class="row" style="gap:8px;margin:0 0 6px"><button class="btn small" type="button" id="grpCopy">Copy address and key</button>
      <button class="btn ghost small" type="button" id="grpNew" title="The old key stops working at once">New key</button></div>
    <p class="muted" style="font-size:13px;margin:4px 0 0">In the hub, open <b>Settings</b> and paste both. Keep the key to people you'd show the roster to: anyone with it can see pilots' names and hours.</p>`;
  $("#grpOn").onchange = e => save({ enabled: e.target.checked }).then(() => toast(e.target.checked ? "Group feed on." : "Group feed off."));
  $("#grpNew").onclick = () => { if (confirm("Make a new group key? The hub stops reading PAC until you paste the new one into its Settings.")) save({ new_key: true }).then(() => toast("New key made.")); };
  $("#grpCopy").onclick = async () => {
    const text = `Feed address: ${g.url}\nGroup key: ${g.key}`;
    try { await navigator.clipboard.writeText(text); toast("Copied."); } catch (e) { $("#grpKey").select(); toast("Select and copy the key by hand."); }
  };
}
async function renderZoneBox() {
  const el = $("#zoneBox"); if (!el) return;
  let d; try { d = await api("/api/staff/conflict-zones"); } catch (e) { el.innerHTML = `<span class="muted">${esc(e.message)}</span>`; return; }
  el.innerHTML = `<label class="switch-row"><input type="checkbox" id="zoneOn" ${d.enabled ? "checked" : ""}><span><b>Enforce conflict zones</b><br><span class="muted" style="font-size:13px">${d.enabled ? "On: flights are tagged, pilots confirm before booking, and the rules apply when PIREPs are filed." : "Off: nothing is tagged or enforced. Switch on once the rules are announced."}</span></span></label>
    <div class="table-wrap"><table class="staff-table"><thead><tr><th>Area</th><th>Status</th><th>Hazard pay</th><th>Note</th></tr></thead><tbody>
    ${d.zones.map(z => `<tr data-zone="${z.id}"><td><b>${esc(z.name)}</b><br><small class="muted">${esc(z.prefixes.join(", "))}</small></td>
      <td><select data-zl aria-label="Status for ${esc(z.name)}">${[["restricted", "Restricted"], ["caution", "Caution"], ["off", "Off"]].map(([v, t]) => `<option value="${v}" ${z.level === v ? "selected" : ""}>${t}</option>`).join("")}</select></td>
      <td><input type="number" min="0" max="50" step="1" value="${z.pct}" data-zp style="width:70px" aria-label="Hazard pay % for ${esc(z.name)}"> %</td>
      <td><small class="muted">${esc(z.note)}</small></td></tr>`).join("")}</tbody></table></div>
    <p class="muted" style="font-size:13px;margin:6px 0">Hazard pay only applies to caution areas: it's a percentage of flight pay, paid with the flight.</p>
    <div class="row"><button class="btn small" type="button" id="zoneSave">Save conflict zones</button></div>`;
  $("#zoneSave").onclick = async () => {
    const zones = {};
    el.querySelectorAll("[data-zone]").forEach(tr => zones[tr.dataset.zone] = { level: tr.querySelector("[data-zl]").value, pct: Number(tr.querySelector("[data-zp]").value) });
    try { await api("/api/staff/conflict-zones", { method: "POST", body: { enabled: $("#zoneOn").checked, zones } }); toast("Conflict zones saved."); await loadZones(); renderZoneBox(); }
    catch (e) { toast(e.message); }
  };
}
async function renderBotBox() {
  const el = $("#botBox"); if (!el) return;
  const st = S.settings || {};
  let live = {}; try { live = await api("/api/staff/discord-bot"); } catch (e) { /* older server */ }
  const fld = (id, label, val, ph = "") => `<div class="field"><label for="${id}">${label}</label><input id="${id}" value="${esc(val ?? "")}" placeholder="${esc(ph)}" autocomplete="off"></div>`;
  el.innerHTML = `<label class="switch-row"><input type="checkbox" id="botOn" ${st.discord_bot_enabled ? "checked" : ""}><span><b>Run the PAC Discord bot</b><br><span class="muted" style="font-size:13px">${live.online ? `🟢 Online · ${live.linked} pilot${live.linked === 1 ? "" : "s"} linked` : st.discord_bot_enabled ? "🔴 Not connected yet. Is the pac-discord service set up and the token right?" : "Off."}</span></span></label>
    <div class="mail-grid">
      <div class="field"><label for="botToken">Bot token</label><input id="botToken" type="password" autocomplete="off" placeholder="${st.discord_bot_token_set ? "Saved. Paste a new one to replace it." : "Developer Portal › Bot › Reset Token"}"></div>
      ${fld("botGuild", "Server ID <span class=\"muted\" style=\"font-weight:400\">(optional)</span>", st.discord_guild, "only if the bot is in several servers")}
      ${fld("botChFlights", "Channel for PIREPs", st.discord_ch_flights, "flight-log")}
      ${fld("botChNews", "Channel for promotions, new pilots and shop", st.discord_ch_news, "announcements")}
      ${fld("botChWelcome", "Channel for welcomes", st.discord_ch_welcome, "welcome")}
      ${fld("botChNotams", "Channel for company NOTAMs", st.discord_ch_notams, "notams")}
      ${fld("botPilotRole", "Role for every linked pilot", st.discord_pilot_role, "PAC Pilot")}
      ${fld("botStaffRole", "Role for staff", st.discord_staff_role, "PAC Staff")}
    </div>
    <label class="switch-row"><input type="checkbox" id="botRanks" ${st.discord_rank_roles !== false ? "checked" : ""}><span><b>Rank roles</b><br><span class="muted" style="font-size:13px">Linked pilots get a role named after their PAC rank (Cadet, Second Officer… Senior Captain), changed automatically on promotion. The bot creates missing roles; its own role must sit above them.</span></span></label>
    <h4 style="margin:18px 0 4px">Dispatch channel</h4>
    <p class="muted" style="font-size:13px;margin:0 0 8px">The bot posts new work as it appears on the mission board, most urgent first, and keeps the board moving even when nobody's signed in. Leave the channel empty to switch this off.</p>
    <div class="mail-grid">
      ${fld("botChDispatch", "Channel for new work", st.discord_ch_dispatch, "dispatch")}
      <div class="field"><label for="botDispHour">Most posts per hour</label><input id="botDispHour" type="number" min="1" max="30" step="1" value="${esc(st.discord_dispatch_per_hour ?? 4)}"></div>
    </div>
    ${[["botDispMissions", "discord_dispatch_missions", "New missions", "Relief, medical, AOG, seasonal and other missions as they open (a few a day)."],
       ["botDispPartners", "discord_dispatch_partners", "Partner crew requests", "When a partner airline needs a PAC captain (one every hour or two)."],
       ["botDispUrgent", "discord_dispatch_urgent", "Urgent requests", "Short-notice jobs with a deliver-by time (open for a few hours)."]]
      .map(([id, k, t, d]) => `<label class="switch-row"><input type="checkbox" id="${id}" ${st[k] !== false ? "checked" : ""}><span><b>${t}</b><br><span class="muted" style="font-size:13px">${d}</span></span></label>`).join("")}
    <h4 style="margin:18px 0 4px">Butter board</h4>
    <p class="muted" style="font-size:13px;margin:0 0 8px">Every accepted PIREP with a landing at or softer than the limit is also posted to the butter board: "🧈 Alex greased the 737-800 into MTPP at -48 fpm!" Leave the channel empty to switch it off.</p>
    <div class="mail-grid">${fld("botChButter", "Butter board channel", st.discord_ch_butter, "butter-board")}
      <div class="field"><label for="botButterFpm">Softer than (fpm)</label><input id="botButterFpm" type="number" min="10" max="300" step="10" value="${esc(st.discord_butter_fpm ?? 100)}"></div></div>
    <h4 style="margin:18px 0 4px">Weekly recap</h4>
    <p class="muted" style="font-size:13px;margin:0 0 8px">Every Monday at 14:00 UTC (9 AM in Cincinnati in winter), the bot posts last week at PAC: flights, hours and cargo, the smoothest landing, the top three for hours, promotions and new pilots. Linked pilots are tagged. A week with no flights, promotions or new pilots is skipped.</p>
    <label class="switch-row"><input type="checkbox" id="botRecap" ${st.discord_recap_enabled !== false ? "checked" : ""}><span><b>Post the weekly recap</b></span></label>
    <div class="mail-grid">${fld("botChRecap", "Channel for the recap <span class=\"muted\" style=\"font-weight:400\">(blank: the announcements channel)</span>", st.discord_ch_recap, st.discord_ch_news || "announcements")}</div>
    <div class="row" style="margin:6px 0 4px"><button class="btn ghost small" type="button" id="botRecapPrev">Preview last week's recap</button></div>
    <div id="botRecapOut"></div>
    <h4 style="margin:18px 0 4px">Bot trap</h4>
    <p class="muted" style="font-size:13px;margin:0 0 8px">A channel that tells people not to post. Spam bots post everywhere, so anyone who posts there (except staff, moderators and the server's own bots) is removed straight away and their messages from the last 24 hours are deleted. It's a soft ban, so a real person can rejoin. The bot's role needs <b>Ban Members</b> and <b>Manage Messages</b>, placed above ordinary members' roles. Leave the channel empty to switch the trap off.</p>
    <div class="mail-grid">
      ${fld("botChTrap", "Bot-trap channel", st.discord_ch_honeypot, "do-not-post")}
      ${fld("botChModlog", "Staff channel for trap reports <span class=\"muted\" style=\"font-weight:400\">(optional)</span>", st.discord_ch_modlog, "staff-log")}
    </div>
    <div class="row" style="margin-top:8px"><button class="btn small" type="button" id="botSave">Save Discord bot settings</button></div>`;
  $("#botRecapPrev").onclick = async () => {
    const out = $("#botRecapOut"); out.innerHTML = `<span class="muted" style="font-size:13px">Loading…</span>`;
    try {
      const r = await api("/api/staff/weekly-recap"), who = x => esc(x.pilot || x.pilot_id);
      const d0 = new Date(r.start * 1000), d1 = new Date((r.end - 1) * 1000), f = d => d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
      out.innerHTML = `<div class="notice" style="font-size:14px"><b>PAC weekly recap · ${f(d0)} – ${f(d1)}</b> ${r.posted ? '<span class="tag green">Posted</span>' : '<span class="tag grey">Not posted yet</span>'}<br>
        ${r.flights ? `${r.flights} flights · ${r.hours} block hours · ${fmt(r.cargo_lbs)} lb of cargo · ${r.pilots} pilot${r.pilots === 1 ? "" : "s"}` : "No flights last week."}<br>
        ${r.top_landing ? `🧈 Smoothest landing: ${who(r.top_landing)}, ${r.top_landing.landing_rate} fpm (${esc(r.top_landing.flight_number)} into ${esc(r.top_landing.arr)})<br>` : ""}
        ${r.top_hours.length ? `⏱️ Most hours: ${r.top_hours.map(x => `${who(x)} ${x.hours} h`).join(", ")}<br>` : ""}
        ${r.promotions.length ? `🎖️ Promotions: ${r.promotions.map(x => `${who(x)} to ${esc(x.rank)}`).join(", ")}<br>` : ""}
        ${r.new_pilots.length ? `✈️ New pilots: ${r.new_pilots.map(x => `${who(x)} (${esc(x.pilot_id)})`).join(", ")}` : ""}
        ${!r.flights && !r.promotions.length && !r.new_pilots.length ? "<br><span class=\"muted\">Nothing to post, so this week would be skipped.</span>" : ""}</div>`;
    } catch (e) { out.innerHTML = `<span class="muted">${esc(e.message)}</span>`; }
  };
  $("#botSave").onclick = async () => {
    const body = { discord_bot_enabled: $("#botOn").checked, discord_guild: $("#botGuild").value.trim(), discord_ch_flights: $("#botChFlights").value.trim(),
      discord_ch_news: $("#botChNews").value.trim(), discord_ch_welcome: $("#botChWelcome").value.trim(), discord_ch_notams: $("#botChNotams").value.trim(), discord_ch_honeypot: $("#botChTrap").value.trim(), discord_recap_enabled: $("#botRecap").checked, discord_ch_butter: $("#botChButter").value.trim(), discord_butter_fpm: Math.max(10, Math.min(300, parseInt($("#botButterFpm").value, 10) || 100)), discord_ch_recap: $("#botChRecap").value.trim(), discord_ch_modlog: $("#botChModlog").value.trim(), discord_pilot_role: $("#botPilotRole").value.trim(),
      discord_staff_role: $("#botStaffRole").value.trim(), discord_rank_roles: $("#botRanks").checked,
      discord_ch_dispatch: $("#botChDispatch").value.trim(), discord_dispatch_missions: $("#botDispMissions").checked,
      discord_dispatch_partners: $("#botDispPartners").checked, discord_dispatch_urgent: $("#botDispUrgent").checked,
      discord_dispatch_per_hour: Math.max(1, Math.min(30, parseInt($("#botDispHour").value, 10) || 4)) };
    if ($("#botToken").value.trim()) body.discord_bot_token = $("#botToken").value.trim();
    try { S.settings = await api("/api/settings", { method: "POST", body }); toast("Discord bot settings saved. The bot picks them up within a minute."); renderBotBox(); }
    catch (e) { toast(e.message); }
  };
}
function renderSiBox() {
  const el = $("#siBox"); if (!el) return;
  const st = S.settings || {};
  el.innerHTML = `<label class="switch-row"><input type="checkbox" id="siOn" ${st.si_enabled ? "checked" : ""}><span><b>Brief pilots' SayIntentions crews</b><br><span class="muted" style="font-size:13px">Sends each pilot's PAC flight to SayIntentions when they book, change or finish it. Pilots link their account on the Downloads page, or PAC ACARS links it for them.</span></span></label>
    <div class="mail-grid">
      <div class="field"><label for="siKey">VA-Link API key</label><input id="siKey" type="password" autocomplete="off" placeholder="${st.si_key_set ? "Saved. Type a new one to replace it." : "From the VA Manager page"}"></div>
      <div class="field"><label for="siCoupon">Members' coupon code</label><input id="siCoupon" value="${esc(st.si_coupon || "")}" placeholder="Shown to PAC pilots only"></div>
      <div class="field"><label for="siFreq">Dispatcher frequency</label><input id="siFreq" value="${esc(st.si_dispatcher_freq || "")}" placeholder="118.94"></div>
    </div>
    <div class="field"><label for="siNotes">Airline notes for the AI <span class="muted" style="font-weight:400">(traditions, rules, personality: added to every briefing)</span></label>
      <textarea id="siNotes" rows="4" placeholder="e.g. Dispatchers sign off with &quot;Move the Impossible!&quot;. Relief flights get priority handling at every PAC station.">${esc(st.si_notes || "")}</textarea></div>
    <div class="row" style="margin-top:8px"><button class="btn small" type="button" id="siSave">Save SayIntentions settings</button>
      <button class="btn ghost small" type="button" id="siTest" ${st.si_ready ? "" : "disabled"}>Brief my own crew now</button>
      <span class="muted" id="siMsg" style="font-size:13px">${st.si_ready ? "Ready." : st.si_key_set ? "Switched off." : "Add PAC's VA-Link key to start."}</span></div>`;
  $("#siSave").onclick = async () => {
    const body = { si_enabled: $("#siOn").checked, si_coupon: $("#siCoupon").value.trim(), si_dispatcher_freq: $("#siFreq").value.trim(), si_notes: $("#siNotes").value };
    if ($("#siKey").value.trim()) body.si_va_key = $("#siKey").value.trim();
    try { S.settings = await api("/api/settings", { method: "POST", body }); toast("SayIntentions settings saved."); renderSiBox(); } catch (e) { toast(e.message); }
  };
  $("#siTest").onclick = async () => {
    $("#siMsg").textContent = "Sending…";
    try { await api("/api/sayintentions/push", { method: "POST" }); $("#siMsg").textContent = "Sent. Start a SayIntentions flight to hear it."; }
    catch (e) { $("#siMsg").textContent = e.message; }
  };
}
async function loadSiCard() {
  const el = $("#siCard"); if (!el) return;
  let s; try { s = await api("/api/sayintentions"); } catch (e) { el.remove(); return; }
  if (!s.enabled && !s.coupon) { el.remove(); return; }
  const when = t => t ? new Date(t * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
  el.innerHTML = `<h2>SayIntentions.AI <span class="tag">Alliance partner</span></h2>
    <div class="dl-row"><div><b>AI ATC that knows you fly for PAC</b>
      <p>File in SimBrief with airline <b>PGI</b> and ATC calls you <b>PAGANI</b>.${s.ready ? ` Your company dispatcher${s.frequency ? ` on <b>${esc(s.frequency)}</b>` : ""}, cabin crew and co-pilot are briefed on your PAC flight whenever you book or change one.` : ""}</p>
      ${s.coupon ? `<p>PAC pilots get <b>10% off SayIntentions.AI Premium</b> with code <code class="si-code">${esc(s.coupon)}</code> <button class="btn ghost small" type="button" id="siCopy">Copy</button></p>` : ""}
      <ol class="si-steps"><li>In the SayIntentions pilot portal, open your account settings and choose <b>Pagani Air Cargo</b> as your virtual airline.</li>
        <li>Plan every PAC flight in SimBrief with airline <b>PGI</b>.</li>
        ${s.ready ? `<li>Fly with PAC ACARS running: it links your SayIntentions account by itself. Or paste your SayIntentions API key below (it's on your SayIntentions account page).</li>` : ""}</ol>
      ${s.ready ? `<p class="si-status ${s.key_set ? (s.ok === false ? "bad" : "good") : ""}">${!s.key_set ? "Not linked yet."
        : s.ok === false ? `Linked, but the last briefing didn't go through: ${esc(s.error || "")}`
        : s.last ? `Linked. Your crew were last briefed ${esc(when(s.last))}.` : "Linked. Your crew are briefed when you book your next flight."}</p>
      <div class="row" style="align-items:flex-end"><div class="field" style="flex:1;max-width:380px;margin:0"><label for="siPilotKey">SayIntentions API key</label><input id="siPilotKey" type="password" autocomplete="off" placeholder="${s.key_set ? "Saved. Paste a new one to replace it." : "From your SayIntentions account page"}"></div>
        <button class="btn small" type="button" id="siPilotSave">Save</button>${s.key_set ? `<button class="btn ghost small" type="button" id="siPilotPush">Brief my crew now</button><button class="btn ghost small" type="button" id="siPilotForget">Unlink</button>` : ""}</div>` : ""}
    </div></div>`;
  if ($("#siCopy")) $("#siCopy").onclick = () => navigator.clipboard.writeText(s.coupon).then(() => toast("Coupon code copied."));
  if ($("#siPilotSave")) $("#siPilotSave").onclick = async () => {
    const k = $("#siPilotKey").value.trim(); if (!k) { toast("Paste your SayIntentions API key first."); return; }
    try { await api("/api/sayintentions/key", { method: "POST", body: { api_key: k } }); toast("SayIntentions linked."); loadSiCard(); } catch (e) { toast(e.message); }
  };
  if ($("#siPilotPush")) $("#siPilotPush").onclick = async () => {
    try { await api("/api/sayintentions/push", { method: "POST" }); toast("Your SayIntentions crew have been briefed."); } catch (e) { toast(e.message); }
    loadSiCard();
  };
  if ($("#siPilotForget")) $("#siPilotForget").onclick = async () => {
    try { await api("/api/sayintentions/key", { method: "POST", body: { api_key: "" } }); toast("SayIntentions unlinked."); loadSiCard(); } catch (e) { toast(e.message); }
  };
}
async function loadMailBox() {
  const el = $("#mailBox"); if (!el) return;
  let m; try { m = await api("/api/staff/mail"); } catch (e) { el.innerHTML = `<span class="muted">${esc(e.message)}</span>`; return; }
  const when = t => t ? new Date(t * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
  const fld = (id, label, val, ph = "", type = "text") => `<div class="field"><label for="${id}">${label}</label><input id="${id}" type="${type}" value="${esc(val ?? "")}" placeholder="${esc(ph)}" autocomplete="off"></div>`;
  el.innerHTML = `<div class="mail-grid">
      ${fld("mlFrom", "PAC's email address", m.mail_from, "operations@paganiaircargo.com", "email")}
      ${fld("mlName", "Shown as", m.mail_from_name, "Pagani Air Cargo")}
      ${fld("mlPass", "App password", "", m.password_set ? "Saved. Type a new one to replace it." : "From your mail provider", "password")}
      ${fld("mlHost", "Mail server", m.smtp_host, "filled in for common providers")}
      ${fld("mlPort", "Port", m.smtp_port, "587", "number")}
      <div class="field"><label for="mlSec">Security <span class="muted" style="font-weight:400">(Check the connection finds a port that works)</span></label><select id="mlSec">${[["starttls", "STARTTLS (587, 2587)"], ["ssl", "SSL (465, 2465)"], ["none", "None"]].map(([v, l]) => `<option value="${v}" ${m.smtp_security === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>
      ${fld("mlUser", "Sign-in name (if different)", m.smtp_user, "usually the address above")}
      ${fld("mlReply", "Replies go to (optional)", m.mail_reply_to, "", "email")}
    </div>
    <label class="switch-row"><input type="checkbox" id="mlAutoW" ${m.auto_welcome ? "checked" : ""}><span><b>Send the welcome letter automatically</b> <span class="muted" style="font-size:13px">the moment an application is approved</span></span></label>
    <label class="switch-row"><input type="checkbox" id="mlAutoD" ${m.auto_decline ? "checked" : ""}><span><b>Send the decline letter automatically</b> <span class="muted" style="font-size:13px">off by default, so you can word it yourself first</span></span></label>
    <div class="row" style="margin-top:8px"><button class="btn small" type="button" id="mlSave">Save email settings</button>
      <button class="btn ghost small" type="button" id="mlTest" ${m.ready ? "" : "disabled"}>Send a test letter…</button>
      <button class="btn ghost small" type="button" id="mlDiag">Check the connection</button>
      <span class="muted" style="font-size:13px">${m.last_error ? `<span style="color:var(--red)">${esc(m.last_error)}</span>`
        : m.last_ok ? `Last sent ${esc(when(m.last_ok))} to ${esc(m.last_to || "")}` : m.ready ? "Ready. Nothing sent yet." : "Not set up: letters are copied by hand."}</span></div>`;
  $("#mlSave").onclick = async () => {
    const body = { mail_from: $("#mlFrom").value, mail_from_name: $("#mlName").value, mail_reply_to: $("#mlReply").value,
      smtp_host: $("#mlHost").value, smtp_port: $("#mlPort").value || 587, smtp_security: $("#mlSec").value, smtp_user: $("#mlUser").value };
    if ($("#mlPass").value) body.smtp_pass = $("#mlPass").value;
    try { await api("/api/staff/mail", { method: "POST", body }); toast("Email settings saved."); loadMailBox(); refreshCore(); }
    catch (e) { toast(e.message, 8000); }
  };
  $("#mlAutoW").onchange = e => api("/api/staff/mail", { method: "POST", body: { auto_welcome: e.target.checked } }).then(() => toast("Saved.")).catch(err => toast(err.message));
  $("#mlAutoD").onchange = e => api("/api/staff/mail", { method: "POST", body: { auto_decline: e.target.checked } }).then(() => toast("Saved.")).catch(err => toast(err.message));
  $("#mlDiag").onclick = async e => {
    const btn = e.currentTarget; btn.disabled = true; btn.textContent = "Checking…";
    let d; try { d = await api("/api/staff/mail/diagnose", { method: "POST" }); } catch (err) { toast(err.message, 8000); btn.disabled = false; btn.textContent = "Check the connection"; return; }
    btn.disabled = false; btn.textContent = "Check the connection";
    const tick = v => v === true ? "✓" : v === false ? "✗" : "–";
    $("#linkTitle").textContent = "Email connection check";
    $("#linkUrl").closest(".row").hidden = true; $("#linkDlg").querySelector(".dlg-body > p.muted").hidden = true;
    $("#linkText").innerHTML = `<p class="muted" style="font-size:13px">Server <b>${esc(d.host)}</b> · sign-in name <b>${esc(d.user)}</b> · app password <b>${d.password_length} characters</b>${/gmail|google/i.test(d.host || "") && d.password_length && d.password_length !== 16 ? ` <span style="color:var(--red)">(a Google app password is 16)</span>` : ""}</p>
      ${d.advice ? `<div class="notice" style="margin:8px 0">${esc(d.advice)}${d.suggest ? ` <button class="btn small" type="button" id="mlUseSuggest" style="margin-left:6px">Use port ${d.suggest.smtp_port}</button>` : ""}</div>` : ""}
      ${d.steps.map(([n, ok, note]) => `<p>${tick(ok)} <b>${esc(n)}</b> — ${esc(note)}</p>`).join("")}
      ${d.ports.map(p => `<div class="diag-port"><b>Port ${p.port} (${esc(p.security.toUpperCase())})</b>
        <div>${tick(p.connect)} Connect &nbsp; ${tick(p.secure)} Secure &nbsp; ${tick(p.login)} Sign in</div>
        <small class="muted">${esc(p.note || "")}</small>
        ${(p.server_said || []).length ? `<div class="diag-said">${p.server_said.map(x => esc(x)).join("<br>")}</div>` : ""}
        ${p.auth_methods ? `<small class="muted">Sign-in methods offered: ${esc(p.auth_methods.join(", "))}</small>` : ""}</div>`).join("")}
      ${d.ports.some(p => p.connect) ? `<p class="muted" style="font-size:13px;margin-top:10px">If both ports stop at <b>Secure</b> or <b>Sign in</b> with a dropped connection, antivirus mail scanning is the usual cause: switch off "mail shield" or "scan outgoing email" and check again.</p>` : ""}`;
    if (!$("#linkDlg").open) $("#linkDlg").showModal();
    if ($("#mlUseSuggest")) $("#mlUseSuggest").onclick = async () => {
      $("#mlPort").value = d.suggest.smtp_port; $("#mlSec").value = d.suggest.smtp_security; $("#linkDlg").close();
      $("#mlSave").click();
    };
  };
  $("#mlTest").onclick = async e => {
    const own = $("#mlFrom").value.trim();
    const to = prompt("Send the test letter to which address?\n\nTo check how pilots receive PAC's letters, use an address that isn't PAC's own, such as your personal email or the address mail-tester.com gives you.", localStorage.getItem("pac-mail-test-to") || own);
    if (to === null) return;
    if (to.trim() && to.trim() !== own) localStorage.setItem("pac-mail-test-to", to.trim());
    const btn = e.currentTarget; btn.disabled = true; btn.textContent = "Sending…";
    try { const r = await api("/api/staff/mail/test", { method: "POST", body: { to: to.trim() || own } });
      toast(r.changed ? `Test sent to ${r.to}. Port ${r.changed.smtp_port} worked, so PAC has saved that.` : `Test sent to ${r.to}.`, r.changed ? 9000 : 5000); }
    catch (err) { toast(err.message, 10000); }
    finally { btn.disabled = false; btn.textContent = "Send a test letter…"; loadMailBox(); }
  };
}

/* ================= Discord ================= */
async function loadDiscordBox() {
  const el = $("#discordBox"); if (!el) return;
  let d; try { d = await api("/api/staff/discord"); } catch (e) { el.innerHTML = `<span class="muted">${esc(e.message)}</span>`; return; }
  const when = t => t ? new Date(t * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
  el.innerHTML = `<div class="row" style="margin:0 0 8px;flex-wrap:nowrap">
      <input id="dcUrl" type="password" autocomplete="off" placeholder="${d.webhook_set ? `Webhook saved (${esc(d.webhook_hint)}). Paste a new one to replace it.` : "https://discord.com/api/webhooks/…"}" style="flex:1;border:1px solid var(--line);padding:7px 9px">
      <button class="btn small" type="button" id="dcSave">Save</button>${d.webhook_set ? `<button class="btn ghost small" type="button" id="dcRemove">Remove</button>` : ""}</div>
    <label class="switch-row"><input type="checkbox" id="dcDep" ${d.departures ? "checked" : ""}><span><b>Post departures</b> <span class="muted" style="font-size:13px">when the takeoff roll begins</span></span></label>
    <label class="switch-row"><input type="checkbox" id="dcArr" ${d.arrivals ? "checked" : ""}><span><b>Post arrivals</b> <span class="muted" style="font-size:13px">when the PIREP is filed, with the landing and grade</span></span></label>
    <div class="row" style="margin-top:8px"><button class="btn ghost small" type="button" id="dcTest" ${d.webhook_set ? "" : "disabled"}>Send a test message</button>
      <span class="muted" style="font-size:13px">${d.last_error ? `<span style="color:var(--red)">Last problem: ${esc(d.last_error)}</span>` : d.last_ok ? `Last posted ${esc(when(d.last_ok))}` : d.webhook_set ? "Nothing posted yet." : "Not set up."}</span></div>`;
  const save = async body => { try { const r = await api("/api/staff/discord", { method: "POST", body }); S.settings.discord_enabled = !!r.webhook_set; loadDiscordBox(); toast("Discord settings saved."); } catch (e) { toast(e.message, 8000); } };
  $("#dcSave").onclick = () => { const v = $("#dcUrl").value.trim(); if (!v) { toast("Paste the webhook address first."); return; } save({ webhook: v }); };
  if ($("#dcRemove")) $("#dcRemove").onclick = () => { if (confirm("Stop posting to Discord and forget the webhook?")) save({ webhook: "" }); };
  $("#dcDep").onchange = e => save({ departures: e.target.checked });
  $("#dcArr").onchange = e => save({ arrivals: e.target.checked });
  $("#dcTest").onclick = async () => { try { await api("/api/staff/discord/test", { method: "POST" }); toast("Test message sent. Check your Discord channel."); } catch (e) { toast(e.message, 8000); } loadDiscordBox(); };
}
async function shareToDiscord(canvas, text, filename, btn) {
  if (btn) { btn.disabled = true; btn.textContent = "Posting…"; }
  try { await api("/api/discord/share", { method: "POST", body: { image: canvas.toDataURL("image/png"), text, filename } }); toast("Posted to Discord."); }
  catch (e) { toast(e.message, 8000); }
  finally { if (btn) { btn.disabled = false; btn.textContent = "Post to Discord"; } }
}

/* ================= My bids ================= */
// keep the header pill current on every page (the ACARS page updates it every second)
setInterval(async () => {
  if (!S.me || !S.booking || !$("#view-acars").hidden || document.hidden) return;
  try { S.status = await api("/api/acars/status"); paintBid(); } catch (e) { /* offline */ }
}, 30000);
function gcNm(a, b) {
  if (!a || !b) return null;
  const r = Math.PI / 180, dLat = (b.lat - a.lat) * r, dLon = (b.lon - a.lon) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLon / 2) ** 2;
  return 2 * 3440.065 * Math.asin(Math.sqrt(h));
}
function paintBid() {
  const b = S.booking, pill = $("#bidPill"), n = $("#bidsCount");
  if (n) { n.hidden = !b; n.textContent = b ? "1" : ""; }
  if (!pill) return;
  pill.hidden = !b;
  if (!b) return;
  const st = S.status || {};
  const live = st.tracking && !st.complete, done = st.complete;
  pill.className = "bid-pill" + (live ? " live" : done ? " done" : "");
  pill.innerHTML = `<i></i><b>${esc(b.flight_number)}</b><span class="rt"> ${esc(b.mission.origin.icao)}–${esc(b.mission.destination.icao)}${live && st.phase_label ? ` · ${esc(st.phase_label)}` : done ? " · on block" : ""}</span>`;
  pill.title = `Your bid: ${b.flight_number} ${b.mission.origin.icao} to ${b.mission.destination.icao}${live && st.phase_label ? ", " + st.phase_label : ""}`;
}
async function loadBids() {
  const root = $("#bidsRoot");
  const b = S.booking;
  if (!b) {
    root.innerHTML = `<div class="profile-bar"><h1>My bids</h1></div>
      <div class="bid-empty"><b>No bids right now.</b><p class="muted">Pick a flight on the mission board, the partner crew requests or the job board. It will wait here until you fly it.</p>
      <button class="btn" onclick="show('missions')">Go to the mission board</button></div>`;
    return;
  }
  let st = {}, hello = {}, statusAvailable = false;
  try { [st, hello] = await Promise.all([api("/api/acars/status"), api("/api/acars/app/hello")]); statusAvailable = true; } catch (e) { /* explicitly show unavailable status */ }
  if (st.booking?.requested_at === b.requested_at && st.booking?.flight_number === b.flight_number) { b.signed=st.booking.signed; b.release_amended=st.booking.release_amended; }
  S.status = st; paintBid();
  const m = b.mission, cp = hello.checkpoint, ac = S.fleet[b.aircraft] || {};
  S.ofpWatch = hello.ofp_watch;
  if (!b.ofp && hello.booking?.ofp) { S.booking = hello.booking; return loadBids(); }  // the plan arrived in the background
  const status = st.complete ? ["done", "On block. The PIREP is ready to review and file."]
    : st.tracking && st.remote ? ["live", `Being tracked in PAC ACARS (${esc(st.source || "")}) · ${esc(st.phase_label || "")}`]
    : cp ? ["saved", `Under way: saved in ${esc((cp.phase || "").replace("_", " ").toLowerCase())} at ${new Date(cp.saved_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}. Open PAC ACARS and press Resume flight.`]
    : ["booked", b.dep_stand?.stand ? `Booked. PAC has you on ${standName(b.dep_stand)} (any stand is fine). Load the aircraft, then open it in PAC ACARS.` : "Booked. Load the aircraft at the stand, then open it in PAC ACARS."];
  root.innerHTML = `<div class="profile-bar"><h1>My bids</h1><span class="muted">One flight at a time: fly it or cancel it to bid on another.</span></div>
    <article class="bid-card ${status[0]}">
      <div class="bid-head"><div><div class="bid-fn">${esc(b.flight_number)}</div><div class="muted">${esc(m.title)}</div></div>
        <div class="bid-route"><b>${esc(m.origin.icao)}</b><span>→</span><b>${esc(m.destination.icao)}</b></div></div>
      <div class="bid-facts">
        <div><span>Aircraft</span><b>${esc(ac.name || b.aircraft)}</b>${b.airframe ? `<small>${esc(b.airframe)}</small>` : m.operator ? `<small>${esc(m.operator.name)} aircraft</small>` : ""}</div>
        <div><span>Cargo</span><b>${fmt(m.payload_lbs)} lb</b><small>${esc(m.cargo || "")}</small></div>
        <div><span>Distance</span><b>${fmt(m.distance_nm || gcNm(m.origin, m.destination))} nm</b><small>${m.target_block_min ? `about ${Math.floor(m.target_block_min / 60)}h ${String(m.target_block_min % 60).padStart(2, "0")}m` : ""}</small></div>
        <div><span>Booked</span><b>${b.requested_at ? new Date(b.requested_at * 1000).toLocaleDateString("en-US", { day: "numeric", month: "short" }) : "–"}</b><small>${b.ofp ? "SimBrief OFP attached" : S.ofpWatch ? "Watching SimBrief for the plan" : "No OFP yet"}</small></div>
      </div>
      ${flowHTML(b, st, cp)}
      ${status[0] === "booked" ? "" : `<div class="bid-status"><i></i>${status[1]}</div>`}
      ${!b.ofp && !st.complete && !st.tracking ? bookedPlanPanel(b) : ""}
      ${b.ofp && !st.complete && !st.tracking ? vatsimFilingPanel(m, b.aircraft, b.ofp) : ""}
      ${!b.ofp && !st.complete && !st.tracking ? `<p class="watch-note" style="margin:0">${S.ofpWatch ? `<i></i>PAC is watching SimBrief for this flight's plan until ${new Date(S.ofpWatch.until * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}. Generate it in SimBrief and it's attached automatically, with the dispatch paperwork updated. <a href="#" id="ofpWatchStop">Stop</a>`
        : `No SimBrief plan attached. <a href="#" id="ofpWatchStart">Watch SimBrief for it</a> (or fetch it in PAC ACARS).`}</p>` : ""}
      ${st.complete ? "" : preparationPanel(b, st, statusAvailable)}
      ${st.complete || st.tracking ? "" : paperNote(b)}
      <div class="row">
        ${st.complete ? `<button class="btn" onclick="show('acars')">Review and file the PIREP</button>`
          : `<a class="btn" href="${appLink(b)}" onclick="setTimeout(checkApp, 5000)">${st.tracking ? "Show PAC ACARS" : cp ? "Resume in PAC ACARS" : "Open in PAC ACARS"}</a>
             <button class="btn ghost" onclick="show('acars')">${st.tracking ? "Follow live" : "Flight page"}</button>`}
        <a class="btn ghost" href="/dispatch" target="_blank" rel="noopener">${needsSignature(b) ? "Review and sign paperwork" : "Dispatch release"}</a>
        ${navigraphBtn(b.ofp)}
        ${st.complete ? "" : `<button class="btn ghost" onclick="cancelMission()">${st.tracking || cp ? "Abort flight" : "Cancel bid"}</button>`}
      </div>
    </article>`;
  wireVatsimFiling(root, m, b.aircraft, b.ofp);
}

/* The flight workflow: where this flight is (Book → Plan → Sign → Fly → File → Debrief) and the one thing to do next */
function flightFlow(b, st = {}, cp = null) {
  const m = b.mission, dep = m.origin.icao, here = S.me?.location?.icao;
  const positioned = m.training?.mode === "dedicated" || here === dep || S.me?.enforce_location === false || !here;
  const planned = !!b.ofp, signed = !needsSignature(b) && !b.release_amended, flying = !!(st.tracking && !st.complete) || !!cp, landed = !!st.complete;
  const steps = [["Book", true], ["Plan", planned || flying || landed], ["Sign", (signed && planned) || flying || landed], ["Fly", landed], ["File", false], ["Debrief", false]];
  const stand = b.dep_stand?.icao === dep && b.dep_stand?.stand ? `${standName(b.dep_stand)} at ${dep}` : `a stand at ${dep}`;
  let next;
  if (landed) next = { step: 4, title: "Review and file your PIREP", text: "You're on block. Check the flight summary, add any remarks and file it. Your debrief and grade come straight after.", btn: `<button class="btn" type="button" onclick="show('acars')">Review and file the PIREP →</button>` };
  else if (st.tracking) next = { step: 3, title: "Fly the flight", text: `PAC ACARS is tracking ${esc(b.flight_number)}${st.phase_label ? ` (${esc(st.phase_label.toLowerCase())})` : ""}. Fly to ${esc(m.destination.icao)}, park and set the brake. ACARS stops by itself on block.`, btn: `<button class="btn" type="button" onclick="show('acars')">Follow the flight live →</button>` };
  else if (cp) next = { step: 3, title: "Resume your flight", text: "This flight was saved part-way. Load the simulator where you left off, open PAC ACARS and press Resume flight.", btn: `<a class="btn" href="${appLink(b)}">Resume in PAC ACARS →</a>` };
  else if (!positioned) next = { step: 0, title: `Get to ${esc(dep)} first`, text: `This flight leaves from ${esc(dep)}, but PAC has you at ${esc(here)}. Fly a leg there, or buy a jumpseat or company travel from your wallet.`, btn: `<button class="btn" type="button" onclick="show('career/wallet')">Travel to ${esc(dep)} →</button>` };
  else if (!planned) next = { step: 1, title: "Plan the flight in SimBrief", text: `Generate the OFP for ${esc(S.fleet[b.aircraft]?.name || b.aircraft)}. The route, callsign and ${m.payload_lbs ? fmt(m.payload_lbs) + " lb of cargo are" : "load is"} filled in for you. The plan attaches here by itself.`, btn: `<button class="btn" type="button" onclick="document.querySelector('#bpGen, #bpOpen')?.scrollIntoView({ behavior: 'smooth', block: 'center' })">Plan in SimBrief ↓</button>` };
  else if (!signed) next = { step: 2, title: b.release_amended ? "Your plan changed: sign the release again" : "Review and sign your dispatch release", text: "Read the release, load sheet, cargo folder and NOTOC, then sign. ACARS won't start this flight until the release is signed.", btn: `<a class="btn" href="/dispatch?sign=1" target="_blank" rel="noopener">Review and sign →</a>` };
  else next = { step: 3, title: "Load up and open PAC ACARS", text: `Load the ${esc(S.fleet[b.aircraft]?.name || b.aircraft)} at <b>${stand}</b> with the parking brake set, then open the flight in PAC ACARS and start tracking.`, btn: `<a class="btn" href="${appLink(b)}" onclick="setTimeout(checkApp, 5000)">Open in PAC ACARS →</a>` };
  return { steps, next };
}
function flowStripHTML(steps, cur) {
  return `<ol class="flow-strip" aria-label="Flight workflow">${steps.map(([l, done], i) => `<li class="${done ? "done" : i === cur ? "now" : ""}" ${i === cur ? 'aria-current="step"' : ""}><span>${done ? "✓" : String(i + 1).padStart(2, "0")}</span>${l}</li>`).join("")}</ol>`;
}
function flowHTML(b, st, cp, compact = false) {
  const { steps, next } = flightFlow(b, st, cp);
  if (compact && next.step === 1) next.btn = `<button class="btn" type="button" onclick="show('bids')">Plan it on My bids →</button>`;
  return `${flowStripHTML(steps, next.step)}
    <div class="do-next${compact ? " compact" : ""}" role="status"><span class="kicker">Do this next${compact ? ` · ${esc(b.flight_number)}` : ""}</span><b>${next.title}</b><p>${next.text}</p>${next.btn}</div>`;
}

/* Home: the signed-in pilot's flight in progress (one next action) and their activity date */
function homeNextHTML(st) {
  const parts = [];
  if (S.booking) parts.push(flowHTML(S.booking, st || S.status || {}, null, true));
  if (typeof activityHTML === "function") parts.push(activityHTML(S.me));
  return parts.filter(Boolean).join("");
}

/* Staying active: the date the next flight is due, and a leave of absence that pauses the clock */
function activityHTML(me) {
  const a = me?.activity;
  if (!a) return "";
  const day = t => new Date(t * 1000).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  const left = a.days_left, rel = left < 0 ? `${-left} day${left === -1 ? "" : "s"} ago` : left === 0 ? "today" : left === 1 ? "tomorrow" : `in ${left} days`;
  const opts = [7, 14, 21, 30, 45, 60, 90].filter(d => d <= Math.min(a.leave_max_days, a.leave_days_left_year));
  const form = opts.length ? `<details class="act-leave"><summary>Away for a while? Take a leave of absence</summary>
      <form id="leaveForm" class="act-form"><label>How long<select name="days">${opts.map(d => `<option value="${d}" ${d === 14 ? "selected" : ""}>${d} days</option>`).join("")}</select></label>
        <label>Reason <small>(optional, staff only)</small><input name="reason" maxlength="200" placeholder="Vacation, new simulator setup, busy at work…"></label>
        <button class="btn small" type="submit">Start my leave</button></form>
      <p class="muted">${a.enabled ? "The clock stops while you're away and the" : "The"} roster shows you as On leave, so staff and other pilots know you're away. Filing a flight ends it early. Up to ${a.leave_max_days} days at a time, ${a.leave_days_left_year} days left this year.</p></details>` : "";
  if (a.state === "leave") return `<div class="act-card leave" id="actCard"><span class="kicker">On leave of absence</span>
      <b>Back by ${day(a.leave.until)}</b><p>${a.enabled ? `Your next flight is due ${day(a.due)}, ${a.policy_days} days after your leave ends.` : "The roster shows you as On leave. Enjoy the time away; PAC will be here when you're back."}${a.leave.reason ? ` Reason on file: “${esc(a.leave.reason)}”.` : ""}</p>
      <button class="btn small ghost" type="button" id="leaveEnd">I'm back: end my leave</button></div>`;
  if (!a.enabled) return form ? `<div class="act-card plain" id="actCard">${form}</div>` : "";
  const cls = a.state === "overdue" ? "overdue" : a.state === "soon" ? "soon" : "ok";
  const head = a.state === "overdue" ? `Your next flight was due ${day(a.due)} (${rel})` : `Next flight due by ${day(a.due)} (${rel})`;
  const text = a.state === "overdue" ? `Fly any PAC flight to stay on the active roster.${a.auto_inactive ? " Pilots past their date are marked Inactive until they fly again." : ""}`
    : `PAC pilots fly at least once every ${a.policy_days} days. ${a.last_flight ? `Your last flight was ${day(a.last_flight)}.` : "Your first flight starts the clock."} Any flight counts.`;
  return `<div class="act-card ${cls}" id="actCard"><span class="kicker">Stay active</span><b>${head}</b><p>${text}</p>
    <div class="row">${a.state !== "ok" ? `<button class="btn small" type="button" onclick="show('missions')">Find a flight →</button>` : ""}</div>${form}</div>`;
}
async function refreshActivity() { await loadMe(); const h = $("#homeNext"); if (h) { h.innerHTML = homeNextHTML(S.status); } }
document.addEventListener("submit", async e => {
  if (e.target.id !== "leaveForm") return;
  e.preventDefault();
  const f = e.target, b = f.querySelector("button");
  b.disabled = true;
  try { await api("/api/pilot/leave", { method: "POST", body: { days: +f.days.value, reason: f.reason.value } }); toast("Leave of absence started. Enjoy the time off."); await refreshActivity(); }
  catch (err) { toast(err.message); b.disabled = false; }
});
document.addEventListener("click", async e => {
  if (e.target.id !== "leaveEnd") return;
  e.target.disabled = true;
  try { await api("/api/pilot/leave", { method: "DELETE" }); toast("Welcome back! Your leave has ended."); await refreshActivity(); }
  catch (err) { toast(err.message); e.target.disabled = false; }
});

/* My bids: plan a booked flight in SimBrief (checkrides and flights requested without an OFP) */
function bookedPlanPanel(b) {
  const api1 = !!S.settings?.simbrief_api, gen = S.sbBooked;
  return `<div class="notice" style="margin:0"><b>Plan this flight in SimBrief</b>
    <p class="muted" style="margin:4px 0 10px;font-size:13px">Filled in for you: ${esc(S.fleet[b.aircraft]?.name || b.aircraft)}, route, callsign and ${b.mission.payload_lbs ? fmt(b.mission.payload_lbs) + " lb of " + (b.mission.training ? "ballast" : "cargo") : "an empty hold"}. The plan attaches to this flight and updates your dispatch release.</p>
    ${simPicker(b.aircraft)}
    <div class="row">${api1 ? `<button type="button" class="btn" id="bpGen" ${gen ? "disabled" : ""}>${gen ? "Generating in SimBrief…" : "Generate OFP"}</button>` : ""}
      <a class="btn ${api1 ? "ghost" : ""}" id="bpOpen" href="${esc(bookedSimbriefUrl(b))}" target="_blank" rel="noopener">${api1 ? "Or open SimBrief yourself" : "Open SimBrief with this flight"}</a>
      <button type="button" class="btn ghost" id="bpFetch">Fetch latest OFP</button></div>
    <p class="muted" style="margin:6px 0 0;font-size:12px">${gen ? "Finish in the SimBrief window. It closes by itself and the plan attaches here." : api1 ? "A small SimBrief window builds the plan and closes by itself. Allow pop-ups for this site." : "In SimBrief, click Generate Flight, then come back and press Fetch latest OFP."}</p></div>`;
}
function bookedSimbriefUrl(b) {
  const keep = S.airframe; S.airframe = b.airframe || b.mission.training?.reg || null;
  try { return simbriefUrl(b.mission, b.aircraft); } finally { S.airframe = keep; }
}
async function attachBookedOfp(body, tries = 0) {
  try {
    await api("/api/acars/app/ofp", { method: "POST", body });
    const r = await api("/api/acars/app/hello"); if (r.booking) S.booking = r.booking;
    toast("SimBrief plan attached. Review and sign your dispatch release before starting PAC ACARS.");
  } catch (e) {
    if (tries < 3 && body.ofp_id && /finished|not found|no plan|yet/i.test(e.message)) { setTimeout(() => attachBookedOfp(body, tries + 1), 2500); return; }
    toast(e.message, 8000);
  }
  S.sbBooked = null; if (!$("#view-bids").hidden) loadBids();
}
async function bookedSimbriefGenerate(b) {
  const win = window.open("about:blank", "SBworker", "width=600,height=315");   // opened on the click, so pop-up blockers allow it
  if (!win) { toast("Allow pop-ups for this site to generate the OFP, or use Open SimBrief yourself."); return; }
  const q = new URL(bookedSimbriefUrl(b)).searchParams;
  const ts = Math.round(Date.now() / 1000), out = (location.origin + "/").replace("http://", "");
  let sig;
  try { sig = await api("/api/simbrief/apicode", { method: "POST", body: { orig: q.get("orig"), dest: q.get("dest"), type: q.get("type"), timestamp: ts, outputpage: out } }); }
  catch (e) { win.close(); toast(e.message); return; }
  const f = document.createElement("form");
  f.method = "get"; f.action = "https://www.simbrief.com/ofp/ofp.loader.api.php"; f.target = "SBworker"; f.style.display = "none";
  const add = (k, v) => { const i = document.createElement("input"); i.type = "hidden"; i.name = k; i.value = v; f.append(i); };
  q.forEach((v, k) => add(k, v));
  add("apicode", sig.apicode); add("outputpage", out); add("timestamp", String(ts));
  document.body.append(f); f.submit(); f.remove();
  const g = S.sbBooked = { started: Date.now() };
  loadBids();
  const timer = setInterval(() => {
    if (S.sbBooked !== g) return clearInterval(timer);
    if (Date.now() - g.started > 15 * 60e3) { clearInterval(timer); S.sbBooked = null; if (!win.closed) win.close(); toast("SimBrief took too long. Try again, or use Open SimBrief yourself."); loadBids(); return; }
    if (!win.closed) return;
    clearInterval(timer);
    attachBookedOfp({ ofp_id: sig.ofp_id });
  }, 600);
}
document.addEventListener("click", e => {
  const t = e.target.closest("#bpGen, #bpFetch"); if (!t || !S.booking) return;
  e.preventDefault();
  if (t.id === "bpGen") bookedSimbriefGenerate(S.booking);
  else { t.disabled = true; t.textContent = "Fetching…"; attachBookedOfp({}); }
});

document.addEventListener("click", async e => {
  const t = e.target.closest("#ofpWatchStop, #ofpWatchStart"); if (!t) return;
  e.preventDefault();
  try { await api("/api/ofp/watch", { method: "POST", body: { on: t.id === "ofpWatchStart" } }); loadBids(); }
  catch (err) { toast(err.message); }
});

/* ================= PAC ACARS app download ================= */
async function showAcarsDownload() {
  const el = $("#acarsDownload"); if (!el) return;
  let d = null;
  try { d = await api("/api/acars/app/download"); } catch (e) { d = null; }
  if (!d?.version) { el.innerHTML = ""; return; }
  el.innerHTML = `<div class="dl-card"><img src="/static/pac-acars-icon.png" alt=""><div><b>PAC ACARS ${esc(verLabel(d.version))} for Windows</b><br>
      <span class="muted" style="font-size:13px">Track flights in a compact window next to your simulator. See Handbook › The PAC ACARS app.</span></div>
    <span style="flex:1"></span>
    ${d.installer ? `<a class="btn small" href="${esc(d.installer.url)}" download>Download installer · ${d.installer.size_mb} MB</a>` : ""}
    ${d.portable ? `<a class="btn ghost small" href="${esc(d.portable.url)}" download>Portable zip · ${d.portable.size_mb} MB</a>` : ""}</div>`;
}

/* ================= Company news, NOTAMs and gallery ================= */
let newsLoadPending = null;
function loadNews() {
  if (newsLoadPending) return newsLoadPending;
  newsLoadPending = (async () => {
    try { S.news = await api("/api/news?limit=8"); } catch (e) { S.news = []; }
    return S.news;
  })().finally(() => { newsLoadPending = null; });
  return newsLoadPending;
}
function notamBars(list) {
  // one line on the board: the titles, opened for the full notices (keeps the flights near the top of the page)
  const ns = (list || []).filter(n => n.kind === "notam").slice(0, 3);
  if (!ns.length) return "";
  const bar = n => `<div class="notam-bar ${n.important ? "important" : ""}"><b class="k">CO NOTAM</b><span><b>${esc(n.title)}</b>${n.body ? ` · ${esc(n.body.length > 260 ? n.body.slice(0, 257).replace(/\s+\S*$/, "") + "…" : n.body)}` : ""}</span></div>`;
  return `<details class="notam-fold"><summary class="notam-bar ${ns.some(n => n.important) ? "important" : ""}"><b class="k">CO NOTAM${ns.length > 1 ? "S" : ""}</b><span><b>${ns.length} company notice${ns.length === 1 ? "" : "s"}:</b> ${ns.map(n => esc(n.title)).join(" · ")}</span><i class="nf-more">Read</i></summary>${ns.map(bar).join("")}</details>`;
}
function newsCards(list) {
  return `<div class="news-grid">${(list || []).slice(0, 6).map(n => `<article class="news-card ${n.kind} ${n.important ? "important" : ""}">
    <small>${n.kind === "notam" ? "Company NOTAM" : "News"} · ${new Date(n.time * 1000).toLocaleDateString("en-US", { day: "numeric", month: "short" })} · ${esc(n.author || "PAC Operations")}</small>
    <h3>${esc(n.title)}</h3>${n.body ? (n.body.length > 260 ? `<p class="news-preview">${esc(n.body.slice(0, 257).replace(/\s+\S*$/, ""))}…</p><details class="news-full"><summary>Read more<span class="sr-only">: ${esc(n.title)}</span></summary><p>${esc(n.body)}</p></details>` : `<p>${esc(n.body)}</p>`) : ""}${n.expires ? `<small>Valid until ${new Date(n.expires * 1000).toLocaleDateString("en-US", { day: "numeric", month: "short" })}</small>` : ""}</article>`).join("")}</div>`;
}
function shotTiles(list, cls = "") {
  return `<div class="shots ${cls}">${(list || []).map(g => `<button type="button" class="shot" data-shot="${g.id}" aria-label="Open screenshot${g.caption ? ": " + esc(g.caption) : ""}">
    <img src="${esc(displayPhoto(g.thumb_url))}" alt="" loading="lazy">${g.featured ? `<span class="star">Featured</span>` : ""}
    <span class="cap">${g.caption ? `<b>${esc(g.caption)}</b><br>` : ""}${esc(g.pilot || "")}${g.flight_number ? ` · ${esc(g.flight_number)} ${g.dep}–${g.arr}` : ""}</span></button>`).join("")}</div>`;
}
function bindShots(root, list, after) {
  if (!root) return;
  root.querySelectorAll("[data-shot]").forEach(b => b.onclick = () => openShot(list.find(x => x.id == b.dataset.shot), after));
}
function openShot(g, after) {
  if (!g) return;
  $("#shotTitle").textContent = g.caption || (g.flight_number ? `${g.flight_number} · ${g.dep} to ${g.arr}` : "Screenshot");
  $("#shotBody").innerHTML = `<div class="shot-view"><img src="${esc(g.url)}" alt="${esc(g.caption || "")}">
    <div class="meta"><span>${esc(g.pilot || "")}${g.flight_number ? ` · <a href="#" id="shotPirep">${esc(g.flight_number)} ${g.dep}–${g.arr}</a>` : ""} · ${new Date(g.time * 1000).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" })}</span>
      <span style="flex:1"></span><a class="btn ghost small" href="${esc(g.url)}" download>Download</a>
      ${S.me?.staff ? `<button class="btn ghost small" type="button" id="shotFeat">${g.featured ? "Unfeature" : "Feature on home page"}</button>` : ""}
      ${S.me && (S.me.staff || g.pilot_id === S.me.id) ? `<button class="btn ghost small" type="button" id="shotDel">Delete</button>` : ""}</div></div>`;
  $("#shotDlg").showModal();
  if ($("#shotPirep")) $("#shotPirep").onclick = e => { e.preventDefault(); $("#shotDlg").close(); openDetail(g.pirep_id); };
  if ($("#shotFeat")) $("#shotFeat").onclick = async () => { await api(`/api/gallery/${g.id}`, { method: "POST", body: { featured: !g.featured } }); $("#shotDlg").close(); toast(g.featured ? "No longer featured." : "Featured on the home page."); after && after(); };
  if ($("#shotDel")) $("#shotDel").onclick = async () => { if (!confirm("Delete this screenshot?")) return; await api(`/api/gallery/${g.id}`, { method: "DELETE" }); $("#shotDlg").close(); toast("Screenshot deleted."); after && after(); };
}
async function uploadShots(input, pirepId, caption) {
  const files = [...(input.files || [])];
  if (!files.length) return false;
  const fd = new FormData(); files.forEach(f => fd.append("shots", f));
  if (pirepId) fd.append("pirep_id", pirepId);
  if (caption) fd.append("caption", caption);
  toast(`Uploading ${files.length} ${files.length === 1 ? "screenshot" : "screenshots"}…`);
  const res = await fetch("/api/gallery", { method: "POST", body: fd });
  const r = await res.json().catch(() => ({ error: `Upload failed (HTTP ${res.status}).` }));
  if (!res.ok) { toast(r.error); return false; }
  toast(`${r.added} added${r.errors?.length ? `. Skipped: ${r.errors.join(" ")}` : ""}.`);
  return true;
}
async function loadGallery() {
  let list = [];
  try { list = await api("/api/gallery?limit=120"); } catch (e) { toast(e.message); }
  $("#galleryRoot").innerHTML = `<div class="profile-bar"><h1>Gallery</h1><span class="muted">${list.length} ${list.length === 1 ? "screenshot" : "screenshots"} from PAC flights</span></div>
    <div class="upload-row"><input id="galCap" placeholder="Caption (optional)" style="border:1px solid var(--line);border-radius:3px;padding:8px 10px;min-width:260px">
      <label class="btn" style="cursor:pointer">Add screenshots<input type="file" id="galFile" accept="image/jpeg,image/png,image/webp" multiple hidden></label>
      <span class="muted" style="font-size:13px">JPG, PNG or WebP, up to 15 MB each. To attach them to a flight, add them from the flight's page in the logbook.</span></div>
    ${list.length ? shotTiles(list) : `<p class="muted">No screenshots yet. Add some from your flights.</p>`}`;
  $("#galFile").onchange = async e => { if (await uploadShots(e.target, null, $("#galCap").value)) loadGallery(); };
  bindShots($("#galleryRoot"), list, loadGallery);
}

/* ================= Pilot wallet, location and jumpseat ================= */
async function loadMe() {
  // the career record adds to the sign-in identity (id, name, staff); it must never replace it
  try { S.me = { ...(S.authPilot || {}), ...(await api("/api/pilot/me")), ...(S.authPilot ? { id: S.authPilot.id, staff: S.authPilot.staff } : {}) }; }
  catch (e) { S.me = S.authPilot || null; }
  renderPilotStrip();
  if (S.me?.new_paystub) showPayNotice(S.me.new_paystub);
  updateMsgBadge(S.me?.unread_messages || 0);
  return S.me;
}
function updateMsgBadge(n) {
  const el = document.getElementById("msgCount");
  if (!el) return;
  el.textContent = n > 99 ? "99+" : n;
  el.hidden = !n;
}
function renderPilotStrip() {
  const el = $("#pilotStrip"), me = S.me;
  if (!el || !me) return;
  if (!$("#boardNotams")) el.insertAdjacentHTML("beforebegin", `<div id="boardNotams"></div>`);
  (S.news ? Promise.resolve(S.news) : loadNews()).then(n => { const b = $("#boardNotams"); if (b) b.innerHTML = notamBars(n); });
  el.innerHTML = `<span>You're at</span><b class="loc">${esc(me.location?.icao || "")}</b><span class="muted">${esc(me.location?.city || me.location?.name || "")}</span>
    <span class="sp"></span><span>Wallet <b class="wal ${moneyCls(me.balance)}">${money(me.balance, true)}</b></span>
    <label style="display:flex;gap:6px;align-items:center;cursor:pointer"><input type="checkbox" id="fromHere" ${S.fromHere ? "checked" : ""} style="accent-color:var(--red)">Only flights from ${esc(me.location?.icao || "here")}</label>
    <button class="btn small" type="button" onclick="openJumpseat()">Jumpseat</button>
    ${Number(me.balance) <= 0 ? `<span class="ux-wallet-help">Taking a type checkride? <button type="button" class="journey-text-button" onclick="show('career/qualifications')">Check free company travel →</button></span>` : ''}`;
  $("#fromHere").onchange = e => { S.fromHere = e.target.checked; renderMissions(); };
}
async function openJumpseat(to) {
  const me = S.me || await loadMe();
  $("#jsFrom").innerHTML = `You're at <b>${esc(me.location.icao)}</b> ${esc(me.location.name || "")}. Wallet <b>${money(me.balance, true)}</b>.`;
  $("#jsBal").textContent = "";
  const picks = new Set(Object.keys(S.hubs || { KCVG: 1, LIMC: 1, KMIA: 1, OMDW: 1, VHHH: 1, PANC: 1 }));
  if (S.selected) picks.add(S.selected.origin.icao);
  (S.urgent || []).forEach(u => picks.add(u.origin.icao));
  picks.delete(me.location.icao);
  $("#jsPicks").innerHTML = [...picks].map(ic => `<button class="chip" type="button" data-jpick="${ic}">${ic}${ic === S.selected?.origin.icao ? " · selected flight" : (S.urgent || []).some(u => u.origin.icao === ic) ? " · urgent" : ""}</button>`).join("");
  document.querySelectorAll("[data-jpick]").forEach(b => b.onclick = () => { $("#js_to").value = b.dataset.jpick; quoteJump(b.dataset.jpick); });
  const inp = $("#js_to"), list = $("#js_list");
  inp.value = to || ""; $("#jsQuote").innerHTML = ""; $("#jsGo").disabled = true;
  inp.oninput = () => { clearTimeout(inp._t); const q = inp.value.trim(); if (q.length < 2) { list.hidden = true; return; }
    inp._t = setTimeout(async () => { const res = await api("/api/airports/search?q=" + encodeURIComponent(q)).catch(() => []);
      list.innerHTML = res.map((a, i) => `<li><button type="button" data-i="${i}"><b>${a.icao}</b><span>${esc(a.name)}<br><small>${esc(a.city)}, ${a.country}</small></span><small></small></button></li>`).join("");
      list.hidden = !res.length; list.querySelectorAll("button").forEach(b => b.onmousedown = e => { e.preventDefault(); const a = res[b.dataset.i]; inp.value = a.icao; list.hidden = true; quoteJump(a.icao); }); }, 180); };
  inp.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); list.hidden = true; quoteJump(inp.value.trim().toUpperCase()); } };
  $("#jumpDlg").showModal();
  if (to) quoteJump(to);
}
async function quoteJump(to) {
  try {
    const q = await api("/api/pilot/jumpseat/quote", { method: "POST", body: { to } });
    const bal = S.me.balance;
    $("#jsQuote").innerHTML = `<p class="muted" style="margin:0 0 8px">${esc(q.from.icao)} to <b style="color:var(--ink)">${esc(q.to.icao)}</b> ${esc(q.to.name)} · ${fmt(q.distance_nm)} nm</p>
      <div class="js-opts">${q.options.map((o, i) => `<label class="js-opt"><input type="radio" name="jsopt" value="${o.kind}" ${i === 0 ? "checked" : ""}><span>${o.logo ? `<img src="${esc(o.logo)}" alt="">` : ""}<b>${esc(o.label)}</b><br><small class="muted">${esc(o.note)}</small></span><b class="cost ${o.cost > bal ? "neg-money" : ""}">${money(o.cost, true)}</b></label>`).join("")}</div>`;
    const go = $("#jsGo"); go.disabled = false;
    go.onclick = async () => {
      const kind = document.querySelector("input[name=jsopt]:checked").value;
      try {
        const r = await api("/api/pilot/jumpseat", { method: "POST", body: { to: q.to.icao, kind } });
        $("#jumpDlg").close(); toast(`Arrived at ${r.location}. ${money(r.cost, true)} spent, ${money(r.balance, true)} left.`);
        await loadMe(); renderMissions();
      } catch (e) { toast(e.message); }
    };
  } catch (e) { $("#jsQuote").innerHTML = `<div class="notice">${esc(e.message)}</div>`; $("#jsGo").disabled = true; }
}
function walletPanel(me, wallet) {
  if (!me) return "";
  const kinds = { flight_pay: "Flight pay", profit_share: "Profit share", skill_bonus: "Skill bonus", contract_bonus: "Shortage bonus", ferry_bonus: "Ferry bonus", hazard_pay: "Hazard pay", jumpseat: "Travel", shop: "PAC shop", gear_bonus: "Gear bonus", adjustment: "Staff adjustment", campaign: "Campaign reward", per_diem: "Per diem", mentoring: "Mentoring bonus", hotel: "Hotel stay", base_pay: "Weekly base pay", training_travel: "Training travel" };
  const entries = wallet?.transactions || [];
  const pager = wallet && wallet.pages > 1 ? `<nav class="wallet-pages" aria-label="Wallet transaction pages" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:12px 14px;border-top:1px solid var(--line)">
    <span class="muted" role="status">Transactions ${(wallet.page - 1) * wallet.per_page + 1}–${Math.min(wallet.page * wallet.per_page, wallet.total)} of ${wallet.total}</span>
    <div class="row" style="gap:8px"><button class="btn small outline" type="button" onclick="loadWalletPage(${wallet.page - 1})" ${wallet.page <= 1 ? "disabled" : ""}>Previous</button>
    <span class="muted">Page ${wallet.page} of ${wallet.pages}</span><button class="btn small outline" type="button" onclick="loadWalletPage(${wallet.page + 1})" ${wallet.page >= wallet.pages ? "disabled" : ""}>Next</button></div></nav>` : "";
  return `<div class="section-h"><div><h2>Pay and wallet</h2><p>${esc(me.rank)}s earn $${me.pay_rate} per block hour, plus ${me.profit_share_pct}% of each flight's profit, and a weekly base for flying. Spend it on jumpseats to reposition.</p></div><div class="row" style="gap:8px"><button class="btn small outline" onclick="openPaystub()">Pay statement</button><button class="btn small" onclick="openJumpseat()">Jumpseat</button></div></div>
    <div class="wallet-hero"><div><span>Wallet</span><b>${money(me.balance, true)}</b></div><div><span>Location</span><b>${esc(me.location?.icao || "")}</b></div>
      <div><span>Earned all time</span><b>${money(me.earned, true)}</b></div><div><span>Spent on travel</span><b>${money(me.spent_travel, true)}</b></div></div>
    <p style="margin:10px 0 0"><a href="#shop" onclick="show('shop');return false" style="color:var(--red);font-weight:700">Visit the PAC shop →</a>${me.spent_shop ? ` <span class="muted">· ${money(me.spent_shop, true)} spent there so far</span>` : ""}</p>
    ${entries.length ? `<section class="panel" style="margin-top:14px"><table class="fin-table"><thead><tr><th>Date</th><th>Type</th><th>Details</th><th class="r">Amount</th></tr></thead><tbody>
      ${entries.map(t => `<tr><td>${new Date(t.time * 1000).toISOString().substr(0, 10)}</td><td>${esc(kinds[t.kind] || t.kind)}</td><td>${esc(t.description)}</td><td class="r ${moneyCls(t.amount)}"><b>${t.amount > 0 ? "+" : ""}${money(t.amount, true)}</b></td></tr>`).join("")}</tbody></table>${pager}</section>` : `<p class="muted">No wallet transactions yet.</p>`}`;
}
async function loadWalletPage(page) {
  try {
    const wallet = await api("/api/pilot/wallet-transactions?page=" + encodeURIComponent(page));
    if (!$("#careerWallet")) return;
    S.walletData = wallet;
    $("#careerWallet").innerHTML = walletPanel(S.me, wallet);
  } catch (e) { toast(e.message); }
}

/* ---------------- pay statements ---------------- */
function paystubHTML(s) {
  const me = S.me || {};
  const row = l => `<tr><td>${esc(l.label)}</td><td class="r ${moneyCls(l.amount)}"><b>${l.amount > 0 ? "+" : ""}${money(l.amount, true)}</b></td></tr>`;
  return `<article class="paystub">
    <div class="ps-head"><div class="ps-brand"><img class="ps-logo" src="/static/pac-logo.png" alt="PAC"><span class="ps-name">Pagani Air Cargo</span></div>
      <div class="ps-title"><h2>Pay Statement</h2><div class="muted">${esc(s.period || "")}</div></div></div>
    <div class="ps-meta">
      <div><span>Pilot</span><b>${esc(me.id || "")} · ${esc(displayName(S.profile) || me.name || "")}</b></div>
      <div><span>Rank</span><b>${esc(s.rank || me.rank || "")}</b></div>
      <div><span>Pay period</span><b>${esc(s.period_label || "")}</b></div>
      <div><span>Flying</span><b>${s.flights} flight${s.flights === 1 ? "" : "s"} · ${esch(s.block_hours)} block h</b></div>
    </div>
    <table class="fin-table ps-table"><thead><tr><th>Earnings</th><th class="r">Amount</th></tr></thead>
      <tbody>${s.lines.map(row).join("") || `<tr><td class="muted">No earnings this period</td><td></td></tr>`}</tbody>
      <tfoot><tr><td><b>Gross earnings</b></td><td class="r"><b>${money(s.gross, true)}</b></td></tr></tfoot></table>
    ${s.deductions.length ? `<table class="fin-table ps-table"><thead><tr><th>Deductions</th><th class="r">Amount</th></tr></thead>
      <tbody>${s.deductions.map(row).join("")}</tbody>
      <tfoot><tr><td><b>Total deductions</b></td><td class="r"><b>${money(s.deductions_total, true)}</b></td></tr></tfoot></table>` : ""}
    <div class="ps-summary"><div><span>Net pay</span><b class="${moneyCls(s.net)}">${money(s.net, true)}</b></div>
      <div><span>Wallet balance</span><b>${money(s.balance, true)}</b></div></div>
    <p class="ps-note">This pay statement is simulated for flight simulation only. No real money is paid out; PAC wallet dollars exist only inside Pagani Air Cargo.</p>
    <div class="ps-actions"><button class="btn small outline" type="button" onclick="window.print()">Print / save as PDF</button>
      <button class="btn small" type="button" onclick="this.closest('dialog').close()">Close</button></div>
  </article>`;
}
async function openPaystub(period) {
  let dlg = document.getElementById("paystubDlg");
  if (!dlg) { dlg = document.createElement("dialog"); dlg.id = "paystubDlg"; dlg.className = "paystub-dlg"; document.body.appendChild(dlg); }
  dlg.innerHTML = `<div class="paystub"><p class="muted" style="padding:28px 24px">Loading your pay statement…</p></div>`;
  if (!dlg.open) dlg.showModal();
  try {
    const s = await api("/api/pilot/paystub" + (period ? "?period=" + encodeURIComponent(period) : ""));
    dlg.innerHTML = paystubHTML(s);
  } catch (e) {
    dlg.innerHTML = `<div class="paystub"><p style="padding:24px">We couldn't load the pay statement. ${esc(e.message || "")}</p><div class="ps-actions"><button class="btn small" onclick="this.closest('dialog').close()">Close</button></div></div>`;
  }
}
function showPayNotice(p) {
  if (!p || !p.period || S.payNoticeShown === p.period) return;
  S.payNoticeShown = p.period;
  api("/api/pilot/paystub/seen", { method: "POST", body: { period: p.period } }).catch(() => {});   // once seen, it won't return
  let el = document.getElementById("payNotice");
  if (!el) { el = document.createElement("div"); el.id = "payNotice"; el.className = "pay-notice"; document.body.appendChild(el); }
  el.innerHTML = `<button class="pn-x" type="button" aria-label="Dismiss" onclick="this.closest('.pay-notice').remove()">×</button>
    <div class="pn-ic">PAC</div>
    <div class="pn-body"><b>You've been paid!</b>
      <span>Your pay statement for ${esc(p.period_label || "the latest period")} is ready — ${money(p.net, true)} net.</span>
      <button class="btn small" type="button" onclick="document.getElementById('payNotice').remove();openPaystub('${esc(p.period)}')">View pay statement</button></div>`;
}



/* ================= Live map =================
   Everyone flying for PAC right now, from what their PAC ACARS reports every few seconds. */
function planeIcon(f, sel) {
  const col = f.on_ground ? "#9aa1ab" : "#d4111e";
  return L.divIcon({ className: "live-plane" + (sel ? " sel" : ""), iconSize: [30, 30], iconAnchor: [15, 15],
    html: `<svg viewBox="0 0 32 32" width="30" height="30" style="transform:rotate(${f.hdg || 0}deg)"><path d="M16 2l2.4 9.6 10.6 6v2.6l-10.6-3.2-.8 7.4 3.6 2.6V29L16 27.6 10.8 29v-2l3.6-2.6-.8-7.4-10.6 3.2v-2.6l10.6-6z" fill="${col}" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/></svg>` });
}
function openLive() {
  const root = $("#liveRoot");
  if (!S.live) {
    root.innerHTML = `<div class="profile-bar"><h1>Live map</h1><span class="muted" id="liveCount">Looking for PAC flights…</span></div>
      <div class="live-wrap"><div id="liveMap" class="live-map"></div><aside class="live-list" id="liveList"></aside></div>
      <p class="muted" style="font-size:13px;margin-top:8px">Positions come from PAC ACARS and update every 10 seconds. A flight leaves the map when it's on block, or if PAC ACARS stops reporting for two minutes.</p>`;
    const base = makeBaseMap($("#liveMap"), { theme: document.documentElement.dataset.theme === "light" ? "light" : "dark", style: S.settings?.map_style });
    base.map.setView([39.05, -84.66], 3);
    S.live = { base, markers: {}, layer: L.layerGroup().addTo(base.map), sel: null, fitted: false, view: "flat" };
    liveViewSwitch();
  }
  setTimeout(() => S.live?.base.map.invalidateSize(), 50);
  if (liveViewPref() === "globe" && S.live.view !== "globe") setLiveView("globe");
  else if (S.live.view === "globe") setTimeout(() => S.live?.globe?.map.resize(), 50);
  pacParkedInit();
  pacParkedRefresh(true);
  pollLive();
  clearInterval(S.liveTimer); S.liveTimer = setInterval(pollLive, 10000);
}
function closeLive() { clearInterval(S.liveTimer); S.liveTimer = null; }
async function pollLive() {
  if (!S.live) return;
  let d; try { d = await api("/api/live"); } catch (e) { $("#liveCount").textContent = e.message; return; }
  const L_ = S.live, map = L_.base.map, flights = d.flights;
  L_.flights = flights;
  pacParkedRefresh();
  $("#liveCount").textContent = flights.length ? `${flights.length} PAC flight${flights.length === 1 ? "" : "s"} in the air or on the move` : "Nobody's flying for PAC right now.";
  L_.layer.clearLayers(); L_.markers = {};
  flights.forEach(f => {
    const sel = L_.sel === f.flight;
    if (f.track?.length > 1) L.polyline(f.track, { color: "#d4111e", weight: sel ? 3 : 2, opacity: sel ? .9 : .55 }).addTo(L_.layer);
    if (sel && f.arr_pos) L.polyline([[f.lat, f.lon], f.arr_pos], { color: "#d4111e", weight: 1.5, dashArray: "5 6", opacity: .7 }).addTo(L_.layer);
    const mk = L.marker([f.lat, f.lon], { icon: planeIcon(f, sel), zIndexOffset: sel ? 1000 : 0 }).addTo(L_.layer);
    mk.bindTooltip(`<b>${esc(f.flight)}</b> ${esc(f.aircraft)}<br>${esc(f.dep || "")} → ${esc(f.arr || "")}`, { direction: "top", offset: [0, -12] });
    mk.on("click", () => { L_.sel = f.flight; pollLive(); });
    L_.markers[f.flight] = mk;
  });
  if (!L_.fitted && flights.length) {
    L_.fitted = true;
    if (flights.length === 1) map.setView([flights[0].lat, flights[0].lon], 5);
    else map.fitBounds(flights.map(f => [f.lat, f.lon]), { padding: [60, 60], maxZoom: 6 });
  }
  const fl = ft => ft >= 18000 ? `FL${String(Math.round(ft / 100)).padStart(3, "0")}` : `${fmt(ft)} ft`;
  $("#liveList").innerHTML = flights.length ? flights.map(f => `<button type="button" class="live-item ${L_.sel === f.flight ? "sel" : ""}" data-live="${esc(f.flight)}">
      <div class="live-top"><b>${esc(f.flight)}</b><span class="tag ${f.on_ground ? "grey" : ""}">${esc(f.phase_label || "")}</span></div>
      <div>${esc(f.dep || "")} → ${esc(f.arr || "")} · ${esc(f.aircraft)}${f.reg ? ` · ${esc(f.reg)}` : ""}</div>
      ${f.pilot ? `<div class="muted">${esc(f.pilot)}</div>` : ""}
      ${L_.sel === f.flight ? `<div class="live-detail">${f.mission ? `<div>${esc(f.mission)}</div>` : ""}${f.cargo ? `<div class="muted">${esc(f.cargo)}</div>` : ""}
        <div class="live-nums"><span><small>Altitude</small>${f.on_ground ? "Ground" : fl(f.alt_ft)}</span><span><small>Ground speed</small>${fmt(f.gs)} kt</span><span><small>To go</small>${f.dtg_nm != null ? fmt(f.dtg_nm) + " nm" : "–"}</span></div></div>` : ""}
    </button>`).join("") : `<p class="muted" style="padding:16px">When a pilot starts a flight in PAC ACARS, it appears here.</p>`;
  document.querySelectorAll("[data-live]").forEach(b => b.onclick = () => {
    L_.sel = L_.sel === b.dataset.live ? null : b.dataset.live;
    const f = flights.find(x => x.flight === b.dataset.live);
    if (L_.sel && f) liveFocus(f.lat, f.lon, 5);
    pollLive();
  });
  globeSync();
}

/* ================= PAC shop =================
   Pilots spend wallet earnings on patches, crew-badge frames, jumpseat passes, aircraft repositions and naming
   rights for an airframe. Prices and rules live on the server (shop.py). */
const PATCH_MARKS = {
  palm: `<path d="M48 75l5-30M28 46q20-25 42 0M32 36q24-18 35 9" fill="none" stroke-width="6" stroke-linecap="round"/><path d="M30 77h42" stroke-width="4"/>`,
  mountain: `<path d="M22 73l21-38 12 20 8-13 17 31z" fill="none" stroke-width="5"/><path d="M37 46l6 6 6-6" fill="none" stroke-width="3"/>`,
  box: `<path d="M28 42l22-12 22 12v27L50 81 28 69zM28 42l22 13 22-13M50 55v26M39 36l23 13" fill="none" stroke-width="4"/>`,
  waves: `<path d="M23 48q9-12 18 0t18 0t18 0M23 61q9-12 18 0t18 0t18 0M23 74q9-12 18 0t18 0t18 0" fill="none" stroke-width="4"/>`,
  sun: `<path d="M23 65h54M32 61a18 18 0 0 1 36 0M50 30v9M24 42l8 6M76 42l-8 6M34 73h32" fill="none" stroke-width="4"/>`,
  moon: `<path d="M58 34a20 20 0 1 0 14 34 16 16 0 1 1-14-34z"/>`,
  cross: `<path d="M44 30h12v14h14v12H56v14H44V56H30V44h14z"/>`,
  jet: `<path d="M50 24l5 22 20 10v6l-20-5-2 14 7 5v4l-10-3-10 3v-4l7-5-2-14-20 5v-6l20-10z"/>`,
  star: `<path d="M50 26l7 16 17 1-13 11 4 17-15-9-15 9 4-17-13-11 17-1z"/>`,
  hub: `<circle cx="50" cy="50" r="7"/><path d="M50 26v14M50 60v14M26 50h14M60 50h14M33 33l10 10M57 57l10 10M33 67l10-10M57 43l10-10" stroke-width="5" stroke-linecap="round" fill="none"/>`,
  crown: `<path d="M28 64l-2-28 13 12 11-18 11 18 13-12-2 28z"/><rect x="28" y="66" width="44" height="6" rx="2"/>`,
};
function patchSVG(p, size = 64) {
  const id = "pc" + Math.random().toString(36).slice(2, 7);
  return `<svg class="patch" width="${size}" height="${size}" viewBox="0 0 100 100" role="img" aria-label="${esc(p.name)} patch">
    <title>${esc(p.name)}</title><defs><path id="${id}" d="M18 50a32 32 0 0 1 64 0"/></defs>
    <circle cx="50" cy="50" r="48" fill="${p.accent}"/><circle cx="50" cy="50" r="44" fill="${p.colour}"/>
    <circle cx="50" cy="50" r="44" fill="none" stroke="${p.accent}" stroke-width="1.5" stroke-dasharray="2 2.5" opacity=".7"/>
    <g fill="${p.accent}" stroke="${p.accent}" transform="translate(12 16) scale(.76)">${PATCH_MARKS[p.mark] || PATCH_MARKS.star}</g>
    <text font-size="${p.name.length > 14 ? 7.8 : 9.5}" font-weight="800" letter-spacing="${p.name.length > 14 ? 0.4 : 1}" fill="${p.accent}" font-family="var(--sans, sans-serif)"><textPath href="#${id}" startOffset="50%" text-anchor="middle">${esc(p.name.toUpperCase().slice(0, 18))}</textPath></text>
  </svg>`;
}
const frameCls = flair => flair?.frame ? `frame-${flair.frame}` : "";
// a patch with a hover (and keyboard-focus) card saying what it is
const patchTip = (p, size) => `<span class="patch-tip" tabindex="0">${patchSVG(p, size)}<span class="tip" role="tooltip"><b>${esc(p.name)}</b>${p.blurb ? `<span>${esc(p.blurb)}</span>` : ""}<small>PAC shop patch</small></span></span>`;
const patchStrip = (flair, size = 40) => flair?.patches?.length ? `<div class="patch-strip">${flair.patches.map(p => patchTip(p, size)).join("")}</div>` : "";

function collectibleArt(i){let shape='';
if(i.art==='mug')shape='<path d="M130 38h18a20 20 0 0 1 0 40h-18" fill="none" stroke="#a90000" stroke-width="10"/><path d="M66 25h70v64q0 20-35 20T66 89z" fill="#c80000"/><ellipse cx="101" cy="25" rx="35" ry="8" fill="#f8e8df"/><text x="101" y="68">PAC</text>';
if(i.art==='tag')shape='<path d="M40 40l25-20h120v74H65L40 74z" fill="#c80000"/><circle cx="58" cy="57" r="6" fill="white"/><text x="124" y="53">PAC</text><text x="124" y="76" style="font-size:10px">REMOVE BEFORE FLIGHT</text>';
if(i.art==='uld')shape='<path d="M58 103V45L85 20h75v83z" fill="#c5cbd0" stroke="#62717f" stroke-width="3"/><path d="M84 22v79M59 52h100M60 96h100" stroke="#929ba5" stroke-width="3"/><rect x="99" y="59" width="48" height="25" fill="#c80000"/><text x="123" y="77" style="font-size:16px">PAC</text>';
if(i.art==='plane')shape='<path d="M104 90v18M76 111h58" stroke="#6d7883" stroke-width="5"/><path d="M26 65q0-9 30-9h91l25-32h18l-10 35 23 8-28 9H55q-29-1-29-11" fill="#c80000"/><path d="M95 66l-27 26h24l37-25" fill="#b5c0ca"/><text x="172" y="50" style="font-size:11px">PAC</text><text x="110" y="38" style="fill:#263849;font-size:13px">'+(i.id==='model727'?'727 CLASSICS':'737 FREIGHTER')+'</text>';
if(i.art==='pennant')shape='<path d="M49 20v95" stroke="#d5ac69" stroke-width="6"/><path d="M53 23h137l-35 35 35 35H53z" fill="'+(i.id==='miami'?'#146f76':'#c80000')+'"/><text x="110" y="53">PAC</text><text x="110" y="77" style="font-size:13px">'+(i.id==='miami'?'MIAMI':'CVG CREW')+'</text>';
if(i.art==='plaque')shape='<rect x="37" y="28" width="147" height="69" rx="5" fill="#27394b" stroke="#c3a465" stroke-width="5"/><text x="110" y="59">PAC</text><text x="110" y="80" style="font-size:12px">CARGO CREW</text>';
return `<svg viewBox="0 0 220 130" role="img" aria-label="${esc(i.name)}" class="collectible-art"><ellipse cx="110" cy="118" rx="70" ry="5" fill="#24384a" opacity=".08"/><g font-family="sans-serif" font-weight="bold" text-anchor="middle" fill="white" font-size="24">${shape}</g></svg>`;}

function publicShelf(flair){
 const items=flair?.shelf||[];
 return items.length?`<section class="crew-shelf"><h3>Crew collection</h3><div class="shelf-slots">${items.map(i=>`<div>${collectibleArt(i)}<b>${esc(i.name)}</b></div>`).join('')}</div></section>`:'';
}
function shopShelf(c){
 const items=(c.shelf||[]).map(id=>(c.collectibles||[]).find(i=>i.id===id&&i.owned)).filter(Boolean);
 return `<section class="crew-shelf"><h2>A little corner of PAC, made yours.</h2><p>Choose up to three owned collectibles for your public pilot profile. Removing one from display keeps it in your collection.</p><div class="shelf-slots">${[0,1,2].map(n=>{const i=items[n];return i?`<div>${collectibleArt(i)}<b>${esc(i.name)}</b><button class="btn ghost small" data-shelf="${i.id}">Remove from shelf</button></div>`:`<div class="shelf-empty"><span aria-hidden="true">＋</span><b>Room for a favorite</b><small>Choose a collectible below</small></div>`}).join('')}</div>${(S.shopTab==='mine')?'<button class="btn ghost small" data-stab="collectibles">Manage collectibles</button>':''}</section>`;
}
async function openReposition(preselect, after){
 if(preselect)return confirmReposition(preselect,after);
 try{S.airframes=await api('/api/airframes');}catch(e){toast(e.message);return;}
 let dlg=document.querySelector('#shopAircraftPicker');if(dlg)dlg.remove();
 dlg=document.createElement('dialog');dlg.id='shopAircraftPicker';dlg.className='shop-aircraft-picker';
 const here=S.shop?.location||S.me?.location?.icao;
 dlg.innerHTML=`<div class="shop-picker-head"><h2>Bring an aircraft to ${esc(here||'your station')}</h2><button class="btn ghost small" id="shopPickerClose">Close</button></div><p>Aircraft delivery moves the aircraft to you. It does not move your pilot or grant a qualification. Review the exact quote before confirming.</p><p>For a checkride, check <a href="#career/qualifications" id="pickerTraining">free company travel</a> first.</p><label for="shopAircraftSearch">Find a registration, aircraft type or airport</label><input id="shopAircraftSearch" type="search" placeholder="For example: N738PC or KMIA"><div id="shopAircraftResults" class="shop-picker-grid" aria-live="polite"></div>`;
 document.body.append(dlg);
 function render(){const q=dlg.querySelector('input').value.trim().toLowerCase();const rows=(S.airframes||[]).filter(a=>[a.reg,a.type,S.fleet[a.type]?.name,a.location].join(' ').toLowerCase().includes(q));
 dlg.querySelector('#shopAircraftResults').innerHTML=rows.map(a=>{const reason=!S.shop?.enabled&&S.shop?'Shop temporarily closed':a.location===here?'Already at your station':a.status!=='Available'?a.status||'Unavailable':'';return `<article><h3>${esc(a.reg)}</h3><p>${esc(S.fleet[a.type]?.name||a.type)}</p><p><b>${esc(a.location)}</b> → <b>${esc(here||'your station')}</b></p><p>${esc(reason||'Available for a delivery quote')}</p><button class="btn small" data-deliver="${esc(a.reg)}" ${reason?'disabled':''}>Review delivery quote</button></article>`;}).join('')||'<p>No aircraft match your search.</p>';
 dlg.querySelectorAll('[data-deliver]').forEach(b=>b.onclick=()=>{dlg.close();confirmReposition(b.dataset.deliver,after);});}
 dlg.querySelector('input').oninput=render;dlg.querySelector('#shopPickerClose').onclick=()=>dlg.close();dlg.querySelector('#pickerTraining').onclick=()=>dlg.close();render();dlg.showModal();dlg.querySelector('input').focus();
}

async function loadShop() {
  try { S.shop = await api("/api/shop"); renderShop(); } catch (e) { toast(e.message); }
}
const SHOP_TABS = [["all", "Everything"], ["passes", "Passes"], ["gear", "Pilot gear"], ["collectibles", "Collectibles"], ["patches", "Patches"], ["frames", "Badge frames"], ["services", "Aircraft"], ["mine", "My collection"]];
function shopDate(t) { return new Date(t * 1000).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" }); }
function renderShop() {
  const c = S.shop, bal = c.balance, tab = S.shopTab || "all";
  const collectibles = c.collectibles || [];
  const buyable = [...collectibles.filter(i => !i.owned), ...c.patches.filter(p => !p.owned), ...c.frames.filter(f => !f.owned), ...c.perks.filter(p => p.owned < p.max), ...c.timed, ...c.gear].filter(i => i.on_sale);
  const prices = [...buyable.map(i => i.price), c.naming_price];
  const within = prices.filter(p => p <= bal).length, next = prices.filter(p => p > bal).sort((a, b) => a - b)[0];
  const pctNext = next ? Math.min(100, Math.round(bal / next * 100)) : 100;
  const need = it => bal < it.price && it.on_sale ? `<small class="muted">${money(it.price - bal)} to go</small>` : "";
  const priceBtn = (it, label = "Buy") => !it.on_sale ? `<span class="tag grey">No longer on sale</span>`
    : `<button class="btn small" type="button" data-buy="${it.id}" ${bal < it.price || !c.enabled ? "disabled" : ""}>${label} · ${money(it.price)}</button>`;
  const ticket = (it, art) => `<div class="shop-ticket"><span class="tk-icon">${art}</span><span class="tk-name">${esc(it.name.split(" · ")[0].toUpperCase())}</span><span class="tk-stub">${it.days ? `${it.days} DAYS` : it.max ? `×${it.max} MAX` : "PAC"}</span></div>`;
  const card = (it, art, body, act, cls = "") => `<article class="shop-item ${cls}" data-cat="${it.cat}">
    <div class="shop-art">${art}</div><div class="shop-kind">${it.label}</div><h3>${esc(it.name)}</h3><p>${body}</p><div class="shop-act">${act}</div></article>`;

  const sections = {
    collectibles: `<p class="shop-note">Cosmetic keepsakes to collect and display. No pay or qualification advantage.</p><div class="shop-grid">${collectibles.map(i => card({...i,cat:"collectibles",label:"Collectible"},collectibleArt(i),esc(i.blurb),i.owned ? `<span class="tag green">Owned</span><button class="btn ghost small" data-shelf="${i.id}" ${!i.displayed && (c.shelf||[]).length>=3 ? 'disabled' : ''}>${i.displayed?'Remove from shelf':'Display on shelf'}</button>${!i.displayed && (c.shelf||[]).length>=3?'<small>All three spaces are filled. Remove an item first.</small>':''}` : priceBtn(i)+need(i),i.owned?'owned':'')).join('')}</div>`,
    passes: `<div class="shop-grid">
      ${c.perks.map(p => card({ ...p, cat: "passes", label: "Pass" }, ticket(p, p.icon),
        esc(p.blurb) + (p.id === "hard_landing_pass" && c.landing_eligible.length ? `<br><b>${c.landing_eligible.length} of your PIREPs qualify.</b>` : ""),
        p.owned >= p.max ? `<span class="tag green">You have ${p.owned}, the most you can hold</span>${p.id === "hard_landing_pass" ? useLanding(p) : ""}`
          : `${priceBtn(p, p.owned ? `Buy another (you have ${p.owned})` : "Buy")}${need(p)}${p.id === "hard_landing_pass" && p.owned ? useLanding(p) : ""}`)).join("")}
      ${c.timed.map(p => card({ ...p, cat: "passes", label: "Timed pass" }, ticket(p, p.icon), esc(p.blurb),
        `${p.expires ? `<span class="tag green">Active until ${shopDate(p.expires)}</span>` : ""}${priceBtn(p, p.expires ? `Add ${p.days} days` : "Buy")}${need(p)}`, p.expires ? "owned" : "")).join("")}
    </div>`,
    gear: `<p class="shop-note">Each piece adds to the pay of every flight you file while it lasts. Your gear adds <b>+${c.gear_bonus}%</b> right now; all gear together tops out at +${c.gear_cap}%.</p>
      <div class="shop-grid">${c.gear.map(g => card({ ...g, cat: "gear", label: `Gear · +${g.bonus}% pay · ${g.days} days` }, `<div class="gear-art">${g.icon}</div>`, esc(g.blurb),
        `${g.expires ? `<span class="tag green">Yours until ${shopDate(g.expires)}</span>` : ""}${priceBtn(g, g.expires ? `Renew (+${g.days} days)` : "Buy")}${need(g)}`, g.expires ? "owned" : "")).join("")}</div>`,
    patches: `<div class="shop-grid">${c.patches.map(p => card({ ...p, cat: "patches", label: "Patch" }, patchSVG(p, 96),
        esc(p.blurb) + (p.until && p.on_sale ? `<br><b class="shop-limited">On sale until ${shopDate(Date.parse(p.until + "T00:00:00Z") / 1000)}</b>` : ""),
        p.owned ? `<span class="tag green">${(c.featured_patches||[]).includes(p.id)?"Featured on profile":"Owned"}</span>` : priceBtn(p) + need(p), p.owned ? "owned" : "")).join("")}</div>`,
    frames: `<div class="shop-grid">${c.frames.map(f => card({ ...f, cat: "frames", label: "Crew badge frame" },
        `<div class="frame-demo frame-${f.id}"><img src="${esc(S.profile?.photo || "/static/pilot-photo-default.svg")}" alt=""></div>`, esc(f.blurb),
        !f.owned ? priceBtn(f) + need(f) : f.worn ? `<span class="tag green">Wearing</span> <button class="btn ghost small" type="button" data-wear="">Take off</button>`
          : `<button class="btn ghost small" type="button" data-wear="${f.id}">Wear</button>`, f.owned ? "owned" : "")).join("")}</div>`,
    services: `<div class="shop-training"><h3>Taking a type checkride?</h3><p>Check <a href="#career/qualifications">free company travel in Qualifications</a> first. It moves you to an available training aircraft. Aircraft delivery moves the aircraft to your current station and costs wallet funds.</p></div><div class="shop-grid wide">
      ${card({ cat: "services", label: "Service", name: "Aircraft reposition" }, `<div class="gear-art">🛫</div>`,
        `Have a PAC aircraft ferried to you at <b>${esc(c.location)}</b>, ready to fly. ${money(c.reposition.base)} plus ${money(c.reposition.per_nm * 100)} per 100 nm.`,
        `<button class="btn small" type="button" id="shopRepo" ${c.enabled ? "" : "disabled"}>Choose an aircraft</button>`)}
      <article class="shop-item" data-cat="services"><div class="shop-art"><div class="gear-art">🏷️</div></div><div class="shop-kind">Naming rights</div><h3>Name a PAC aircraft</h3>
        <p>It shows wherever the registration does, with your name beside it. Renaming one you named is free; staff can remove unsuitable names.</p>
        <div class="field" style="margin:6px 0 0"><label for="nmReg">Aircraft</label><select id="nmReg">${(S.airframes || []).filter(a => !a.name || a.named_by === S.me?.id).map(a => `<option value="${a.reg}">${a.reg} · ${esc(S.fleet[a.type]?.name || a.type)}${a.name ? ` · “${esc(a.name)}”` : ""}</option>`).join("")}</select></div>
        <div class="field" style="margin:6px 0 0"><label for="nmName">Name</label><input id="nmName" maxlength="24" placeholder="Spirit of Cincinnati"></div>
        <div class="shop-act"><button class="btn small" type="button" id="nmGo" ${c.enabled ? "" : "disabled"}>Name it · ${money(c.naming_price)}</button>${bal < c.naming_price ? `<small class="muted">${money(c.naming_price - bal)} to go</small>` : ""}
        ${c.named.length ? `<small>Yours: ${c.named.map(a => `<b>${esc(a.reg)}</b> “${esc(a.name)}”`).join(", ")}</small>` : ""}</div></article>
    </div>`,
  };
  function useLanding(p) {
    if (!c.landing_eligible.length) return `<small class="muted">None of your recent PIREPs qualify right now.</small>`;
    return `<select id="hlPirep" style="margin-top:6px">${c.landing_eligible.map(r => `<option value="${r.id}">${esc(r.flight_number)} ${esc(r.dep)}–${esc(r.arr)} · ${r.landing_rate ?? "?"} fpm · ${esc(r.review_status)}</option>`).join("")}</select>
      <button class="btn ghost small" type="button" id="hlUse">Use a pass on it</button>`;
  }
  const mine = [
    ...collectibles.filter(i=>i.owned).map(i=>["✈",i.name,i.displayed?"on your shelf":"owned collectible"]),
    ...c.gear.filter(g => g.expires).map(g => [g.icon, g.name, `+${g.bonus}% pay until ${shopDate(g.expires)}`]),
    ...c.timed.filter(t => t.expires).map(t => [t.icon, t.name, `active until ${shopDate(t.expires)}`]),
    ...c.perks.filter(p => p.owned).map(p => [p.icon, p.name, `${p.owned} to use`]),
    ...c.frames.filter(f => f.owned).map(f => ["🪪", `${f.name} frame`, f.worn ? "wearing" : "owned"]),
    ...c.patches.filter(p => p.owned).map(p => ["🧵", `${p.name} patch`, (c.featured_patches||[]).includes(p.id)?"featured on profile":"owned"]),
    ...c.named.map(a => ["🏷️", `${a.reg} “${a.name}”`, "your aircraft name"])];
  sections.mine = mine.length ? `<div class="shop-mine">${mine.map(([i, n, w]) => `<div><span class="mi">${i}</span><b>${esc(n)}</b><span class="muted">${esc(w)}</span></div>`).join("")}</div>`
    : `<p class="muted">Nothing yet. Your first patch is a few flights away.</p>`;
  const titles = { collectibles: ["Collectibles", "Little reminders of the flights, the fleet and the crew."], passes: ["Passes", "Bend the rules, just a little."], gear: ["Pilot gear", "Kit that pays its way."], patches: ["Patches", "Collectible designs for your profile and crew badge. These are shop purchases, not earned qualifications."],
    frames: ["Crew badge frames", "Round your photo and crew badge. Own several, wear one."], services: ["Aircraft", "Move one to you, or give one its name."], mine: ["My purchases", "What you own and when it runs out."] };
  const show = tab === "all" ? ["passes", "gear", "collectibles", "patches", "frames", "services"] : [tab];

  $("#shopRoot").innerHTML = `
  <div class="profile-bar"><h1>PAC shop</h1><span class="muted">Something for your next flight. Something to call your own.</span></div>
  ${c.enabled ? "" : `<div class="notice">The PAC shop is closed at the moment. What you've bought still works.</div>`}
  <div class="shop-hero2">
    <div><small>YOUR PAC WALLET</small><span>Welcome to the crew shop. Find your next favorite.</span><b>${money(bal, true)}</b>
      <span>${within} of ${prices.length} items within reach${next ? ` — ${money(next - bal)} to the next one` : " — everything's within reach"}.</span>
      <div class="sh-bar"><i style="width:${pctNext}%"></i></div><small>${next ? `${pctNext}% of the way to the next item on the shelf` : "Treat yourself."}</small></div>
    <div class="sh-side"><div><small>Gear bonus</small><b>+${c.gear_bonus}%</b></div><div><small>Fleet pass</small><b>${c.fleet_pass ? `until ${shopDate(c.fleet_pass)}` : "–"}</b></div>
      <div><small>You're at</small><b>${esc(c.location)}</b></div></div>
  </div>
  <div class="shop-tabs" role="tablist">${SHOP_TABS.map(([k, t]) => `<button role="tab" data-stab="${k}" aria-selected="${tab === k}">${t}${k === "mine" && mine.length ? ` <span class="count">${mine.length}</span>` : ""}</button>`).join("")}</div>
  ${["all","collectibles","mine"].includes(tab)?shopShelf(c):""}
  ${["patches","mine"].includes(tab)?patchShowcase(c):""}
  ${show.map(k => `<div class="section-h"><div><h2>${titles[k][0]}</h2><p>${titles[k][1]}</p></div></div>${sections[k]}`).join("")}`;

  document.querySelectorAll("[data-stab]").forEach(b => b.onclick = () => { S.shopTab = b.dataset.stab; renderShop(); });
  document.querySelectorAll("[data-buy]").forEach(b => b.onclick = async () => {
    const it = [...collectibles, ...c.patches, ...c.frames, ...c.perks, ...c.timed, ...c.gear].find(x => x.id === b.dataset.buy);
    if (!confirm(`Buy ${it.name} for ${money(it.price, true)}? Your wallet after purchase: ${money(bal-it.price, true)}.${it.kind === "collectible" ? " Cosmetic only; display it on your profile shelf." : ""}`)) return;
    b.disabled = true;
    try { S.shop = await api("/api/shop/buy", { method: "POST", body: { item: it.id } }); toast(`${it.name} is yours.`); await afterShop(); }
    catch (e) { toast(e.message); b.disabled = false; }
  });
  document.querySelectorAll("[data-shelf]").forEach(b=>b.onclick=async()=>{
    const items=[...(c.shelf||[])], id=b.dataset.shelf, at=items.indexOf(id);
    if(at>=0)items.splice(at,1);else items.push(id);
    b.disabled=true;
    try{S.shop=await api("/api/shop/shelf",{method:"POST",body:{items}});await afterShop();toast(at>=0?"Removed from your shelf.":"Displayed on your profile.");}
    catch(e){toast(e.message);b.disabled=false;}
  });
  document.querySelectorAll("[data-wear]").forEach(b => b.onclick = async () => {
    try { S.shop = await api("/api/shop/wear", { method: "POST", body: { frame: b.dataset.wear || null } }); await afterShop(); } catch (e) { toast(e.message); }
  });
  if ($("#hlUse")) $("#hlUse").onclick = async () => {
    const id = +$("#hlPirep").value;
    if (!confirm("Use a hard landing pass? That PIREP becomes accepted and paid.")) return;
    try { S.shop = await api("/api/shop/use", { method: "POST", body: { item: "hard_landing_pass", pirep_id: id } }); toast("Done: that flight is accepted and paid."); await afterShop(); }
    catch (e) { toast(e.message); }
  };
  if ($("#shopRepo")) $("#shopRepo").onclick = () => openReposition();
  if ($("#nmGo")) $("#nmGo").onclick = async () => {
    const reg = $("#nmReg").value, name = $("#nmName").value.trim();
    if (!reg || !name) { toast("Choose an aircraft and type a name."); return; }
    const renaming = (S.airframes || []).some(a => a.reg === reg && a.named_by === S.me?.id);
    if (!confirm(renaming ? `Rename ${reg} “${name}”? It's free.` : `Name ${reg} “${name}” for ${money(c.naming_price)}?`)) return;
    try { S.shop = await api("/api/shop/name", { method: "POST", body: { reg, name } }); toast(`${reg} is now “${name}”.`); await afterShop(); }
    catch (e) { toast(e.message); }
  };
}
async function afterShop() {
  await loadMe();
  try { S.airframes = await api("/api/airframes"); } catch (e) { /* keep the old list */ }
  try { const r = await api("/api/profile"); S.profile = r.profile; renderPilot(); } catch (e) { /* not fatal */ }
  renderShop();
}
async function confirmReposition(preselect, after) {
  const here = S.shop?.location || S.me?.location?.icao;
  const list = (S.airframes || []).filter(a => a.status === "Available" && a.location !== here);
  if (!list.length) { toast("No aircraft are free to move right now."); return; }
  const pick = preselect || prompt(`Which aircraft should PAC ferry to ${here}? Type its registration.\n\n${list.slice(0, 40).map(a => `${a.reg}  ${S.fleet[a.type]?.icao || a.type} at ${a.location}`).join("\n")}`);
  if (!pick) return;
  try {
    const q = await api("/api/shop/reposition/quote", { method: "POST", body: { reg: pick.trim().toUpperCase() } });
    if (!confirm(`Ferry ${q.reg} from ${q.from} to ${q.to} (${fmt(q.distance_nm)} nm)?\nRegular price: ${money(q.regular_cost)}\n${q.use_pass ? `Ferry pass: save ${money(q.savings)} (25%). One pass will be used.\n` : ""}Final wallet charge: ${money(q.cost)}`)) return;
    const r = await api("/api/shop/reposition", { method: "POST", body: { reg: q.reg, quote: { from: q.from, to: q.to, cost: q.cost, use_pass: q.use_pass } } });
    toast(`${r.reg} is waiting for you at ${r.to}. ${money(r.cost)} spent.`);
    try { S.airframes = await api("/api/airframes"); } catch (e) { /* keep */ }
    await loadMe();
    if (after) after(); else if (S.shop) loadShop();
  } catch (e) { toast(e.message); }
}

/* ================= Finance ================= */
const money = (v, dec = false) => { if (v == null || isNaN(v)) return "–"; const a = Math.abs(v), sg = v < 0 ? "−" : "";
  return a >= 1e6 ? `${sg}$${(a / 1e6).toFixed(a >= 1e7 ? 1 : 2)}M` : a >= 1e4 && !dec ? `${sg}$${Math.round(a / 1000)}k` : `${sg}$${Math.round(a).toLocaleString("en-US")}`; };
const moneyCls = v => v > 0 ? "pos-money" : v < 0 ? "neg-money" : "";
const COST_NAMES = { fuel: "Fuel", ownership: "Aircraft ownership", maintenance: "Maintenance", crew: "Crew", overhead: "Overhead", landing_fees: "Landing fees",
  navigation: "Navigation", handling: "Cargo handling", hard_landing_inspection: "Hard landing inspection", tail_strike_repairs: "Tail strike repairs",
  damage_repairs: "Damage repairs (deductible)", diversion: "Diversion costs" };
function econBox(e, title = "PAC's flight economics", note = "") {
  if (!e) return "";
  return `<div class="econ-box"><div class="econ-head">
      <div><span>${esc(title)}</span><b style="font-size:15px">${e.yield_per_kg != null ? `$${e.yield_per_kg}/kg` : ""}</b></div>
      <div><span>Revenue</span><b>${money(e.revenue, true)}</b></div><div><span>Costs</span><b>${money(e.total_cost ?? e.cost, true)}</b></div>
      <div><span>Profit${e.margin != null ? ` · ${e.margin}%` : ""}</span><b class="${moneyCls(e.profit)}">${money(e.profit, true)}</b></div></div>
    <div class="econ-lines">${Object.entries(e.costs || {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<span>${esc(COST_NAMES[k] || k)} <b>${money(v, true)}</b></span>`).join("")}</div>
    ${(e.notes || []).some(n => !/^Contract priced on the /i.test(n)) || note ? `<div style="padding:0 14px 10px;font-size:13px;color:var(--steel)">${esc([...(e.notes || []).filter(n => !/^Contract priced on the /i.test(n)), note].filter(Boolean).join(" · "))}</div>` : ""}</div>`;
}
async function loadFinance() {
  try { S.fin = await api("/api/finance"); renderFinance(S.fin); } catch (e) { toast(e.message); }
}
function renderFinance(f) {
  const t = f.totals, mth = f.this_month;
  const tl = f.timeline.length ? [[f.timeline[0][0] - 3600, f.starting_capital], ...f.timeline] : [];
  const t0 = tl.length ? tl[0][0] : 0;
  const cashChart = tl.length > 1 ? (() => {
    const vals = tl.map(x => x[1]), lo = Math.min(...vals), hi = Math.max(...vals), pad = Math.max(1, (hi - lo) * 0.15);
    return svgChart({ xDomain: [0, tl.length - 1], xLabel: v => { const x = tl[Math.round(v)]; return x ? new Date(x[0] * 1000).toISOString().substr(5, 5) : ""; },
      left: { domain: [lo - pad, hi + pad], fmt: v => hi - lo < 5e6 ? `$${(v / 1e6).toFixed(2)}M` : money(v) }, series: [{ pts: tl.map((x, i) => [i, x[1]]), color: "#C80000", fill: "rgba(200,0,0,.08)", width: 2.5 }], height: 240 });
  })() : `<p class="muted" style="padding:20px">The cash chart starts with your first accepted flight.</p>`;
  if (f.summary) {        // pilots: how the airline is doing and their share of it; staff see the full books
    $("#financeRoot").innerHTML = `
    <div class="profile-bar"><h1>Finance</h1><span class="muted">How Pagani Air Cargo is doing</span></div>
    <div class="fin-hero">
      <div class="cash"><span>Company cash</span><b>${money(f.cash)}</b><span style="margin-top:4px">started with ${money(f.starting_capital)}</span></div>
      <div><span>Profit this month</span><b class="${moneyCls(mth.profit)}">${money(mth.profit)}</b><span>${mth.flights} flights</span></div>
      <div><span>Profit all time</span><b class="${moneyCls(t.profit)}">${money(t.profit)}</b></div>
      <div><span>Shared with pilots</span><b>${money(f.profit_share_paid)}</b><span>5% of every flight's profit</span></div>
      <div><span>Your share so far</span><b class="pos-money">${money(f.my_share)}</b><span>from ${f.my_flights} accepted flight${f.my_flights === 1 ? "" : "s"}</span></div>
    </div>
    <div class="chart-box"><h3>Company cash</h3>${cashChart}</div>
    <p class="muted" style="margin-top:14px">Every accepted flight earns the airline revenue and costs fuel, crew, handling and maintenance. You get 5% of each flight's profit on top of your pay, so efficient, on-time flying pays twice.${f.best_type ? ` PAC's most profitable type so far is the <b>${esc(S.fleet[f.best_type.aircraft]?.name || f.best_type.aircraft)}</b>.` : ""}</p>`;
    return;
  }
  const maxCost = Math.max(1, ...Object.values(f.cost_split));
  const typeRows = f.by_type.map(r => `<tr><td><b>${esc(S.fleet[r.aircraft]?.icao || r.aircraft)}</b> <span class="muted">${esc(S.fleet[r.aircraft]?.name || "")}</span></td><td class="r">${r.flights}</td><td class="r">${esch(r.block_h)}</td>
    <td class="r">${money(r.revenue)}</td><td class="r">${money(r.cost)}</td><td class="r ${moneyCls(r.profit)}"><b>${money(r.profit)}</b></td><td class="r">${r.revenue ? Math.round(r.profit / r.revenue * 100) + "%" : "–"}</td>
    <td class="r ${moneyCls(r.profit)}">${r.block_h ? money(r.profit / r.block_h, true) : "–"}</td></tr>`).join("");
  $("#financeRoot").innerHTML = `
  <div class="profile-bar"><h1>Finance</h1><span class="muted">Jet fuel $${Number(f.fuel_price).toFixed(2)}/gal · change prices in Staff › Site and rules</span></div>
  <div class="fin-hero">
    <div class="cash"><span>Company cash</span><b>${money(f.cash)}</b><span style="margin-top:4px">started with ${money(f.starting_capital)}${f.profit_share_paid ? ` · ${money(f.profit_share_paid)} shared with pilots` : ""}</span></div>
    <div><span>Profit this month</span><b class="${moneyCls(mth.profit)}">${money(mth.profit)}</b><span>${mth.flights} flights</span></div>
    <div><span>Revenue this month</span><b>${money(mth.revenue)}</b></div>
    <div><span>Profit all time</span><b class="${moneyCls(t.profit)}">${money(t.profit)}</b></div>
    <div><span>Revenue all time</span><b>${money(t.revenue)}</b><span>costs ${money(t.cost)}</span></div>
  </div>
  <div class="chart-box"><h3>Company cash</h3>${cashChart}</div>
  ${plStatement(f.statements)}
  ${f.insurance ? `<section class="panel"><h2>Insurance</h2><p class="panel-sub">Hull and liability cover: <b>${money(f.insurance.monthly)}</b> a month for the fleet. After an incident PAC pays only the deductible (${money(f.insurance.deductible.wide)} widebody, ${money(f.insurance.deductible.narrow)} narrowbody); the insurer pays the rest. ${f.insurance.claims_12m ? `${f.insurance.claims_12m} claim${f.insurance.claims_12m === 1 ? "" : "s"} in the last 12 months add ${f.insurance.loading_pct}% to the premium.` : "No claims in the last 12 months."} ${esc(f.insurance.note)}</p>
    <div class="table-wrap" style="border:0"><table class="fin-table"><thead><tr><th>Type</th><th class="r">Aircraft</th><th class="r">Value each</th><th class="r">Premium / month</th></tr></thead><tbody>${f.insurance.lines.map(l => `<tr><td>${esc(l.name)}</td><td class="r">${l.aircraft}</td><td class="r">${money(l.value)}</td><td class="r">${money(l.monthly)}</td></tr>`).join("")}</tbody></table></div></section>` : ""}
  <div class="fin-grid">
    <section class="panel"><h2>By aircraft type</h2>
      ${typeRows ? `<div class="table-wrap" style="border:0"><table class="fin-table"><thead><tr><th>Type</th><th class="r">Flights</th><th class="r">Block h</th><th class="r">Revenue</th><th class="r">Costs</th><th class="r">Profit</th><th class="r">Margin</th><th class="r">Profit / hour</th></tr></thead><tbody>${typeRows}</tbody></table></div>`
        : `<p class="panel-sub" style="padding-bottom:16px">No accepted flights yet. Each PIREP now carries revenue, costs and profit.</p>`}</section>
    <section class="panel"><h2>Where the money goes</h2>
      ${Object.keys(f.cost_split).length ? `<div class="cost-bars">${Object.entries(f.cost_split).map(([k, v]) => `<div><span>${esc(COST_NAMES[k] || k)}</span><i style="width:${Math.max(2, v / maxCost * 100)}%"></i><b style="text-align:right">${money(v)}</b></div>`).join("")}</div>`
        : `<p class="panel-sub" style="padding-bottom:16px">Cost breakdown appears after your first accepted flight.</p>`}</section>
  </div>
  <div class="fin-grid">
    <section class="panel"><h2>By kind of flying</h2>
      ${f.by_category.length ? `<table class="fin-table"><thead><tr><th>Category</th><th class="r">Flights</th><th class="r">Revenue</th><th class="r">Profit</th><th class="r">Margin</th></tr></thead><tbody>
        ${f.by_category.map(r => `<tr><td>${esc(r.category)}</td><td class="r">${r.flights}</td><td class="r">${money(r.revenue)}</td><td class="r ${moneyCls(r.profit)}"><b>${money(r.profit)}</b></td><td class="r">${r.revenue ? Math.round(r.profit / r.revenue * 100) + "%" : "–"}</td></tr>`).join("")}</tbody></table>`
        : `<p class="panel-sub" style="padding-bottom:16px">Nothing flown yet.</p>`}
      <p class="panel-sub" style="padding:8px 20px 14px">Relief contracts carry the smallest markup. The company doesn't profit much from disasters.</p></section>
    <section class="panel"><h2>Most profitable routes</h2>
      ${f.best_routes.length ? `<table class="fin-table"><tbody>${f.best_routes.map(r => `<tr><td><b>${esc(r.route)}</b></td><td class="r">${r.flights}×</td><td class="r ${moneyCls(r.profit)}"><b>${money(r.profit)}</b></td></tr>`).join("")}</tbody></table>` : `<p class="panel-sub" style="padding-bottom:16px">No routes yet.</p>`}
      ${f.worst_routes.length ? `<h3 style="padding:10px 20px 0;margin:0">Loss-makers</h3><table class="fin-table"><tbody>${f.worst_routes.map(r => `<tr><td>${esc(r.route)}</td><td class="r">${r.flights}×</td><td class="r neg-money"><b>${money(r.profit)}</b></td></tr>`).join("")}</tbody></table>` : ""}</section>
  </div>
  <section class="panel" style="margin-top:24px"><h2>Ledger</h2>
    ${f.ledger.length ? `<div class="table-wrap" style="border:0"><table class="fin-table"><thead><tr><th>Date</th><th>Flight</th><th>Route</th><th>Type</th><th class="r">Revenue</th><th class="r">Costs</th><th class="r">Profit</th></tr></thead><tbody>
      ${f.ledger.map(r => `<tr data-ledger="${r.id}" style="cursor:pointer"><td>${new Date(r.filed_at * 1000).toISOString().substr(0, 10)}</td><td><b>${esc(r.flight_number)}</b></td><td>${r.dep} – ${r.arr}</td><td>${esc(S.fleet[r.aircraft]?.icao || r.aircraft)}</td>
        <td class="r">${money(r.revenue, true)}</td><td class="r">${money(r.cost, true)}</td><td class="r ${moneyCls(r.profit)}"><b>${money(r.profit, true)}</b></td></tr>`).join("")}</tbody></table></div>`
      : `<p class="panel-sub" style="padding-bottom:16px">Every accepted PIREP appears here with its revenue and costs.</p>`}</section>`;
  document.querySelectorAll("[data-ledger]").forEach(tr => tr.onclick = () => openDetail(tr.dataset.ledger));
}

/* ================= Pilot license ================= */
function guilloche(x, W, H, color, alpha) {
  x.save(); x.strokeStyle = color; x.globalAlpha = alpha; x.lineWidth = 1.2;
  for (let k = 0; k < 18; k++) {
    x.beginPath();
    for (let px = 0; px <= W; px += 6) {
      const y = H / 2 + Math.sin(px / (60 + k * 3) + k) * (H * 0.28) + Math.sin(px / 23 + k * 0.7) * 14 + (k - 9) * 9;
      px ? x.lineTo(px, y) : x.moveTo(px, y);
    }
    x.stroke();
  }
  x.restore();
}
function roundRect(x, X, Y, W, H, r) { x.beginPath(); x.moveTo(X + r, Y); x.arcTo(X + W, Y, X + W, Y + H, r); x.arcTo(X + W, Y + H, X, Y + H, r); x.arcTo(X, Y + H, X, Y, r); x.arcTo(X, Y, X + W, Y, r); x.closePath(); }
function mrz(s, n) { return (s.toUpperCase().replace(/[^A-Z0-9]+/g, "<") + "<".repeat(n)).slice(0, n); }

/* ================= Crew ID badge =================
   An airport-style crew identification badge on a PAC lanyard. Click it to flip; download it as a PNG. */
const BADGE_AREAS = { ramp: "RAMP", cargo: "CARGO", aoa: "AOA", occ: "OCC" };
const BADGE_IATA = { KCVG: "CVG", KMIA: "MIA", LIMC: "MXP", OMDW: "DWC", VHHH: "HKG", PANC: "ANC", KMEM: "MEM", KSDF: "SDF", KILN: "ILN", KPAE: "PAE" };
function badgeIata(icao) {
  icao = String(icao || "KCVG").toUpperCase();
  return BADGE_IATA[icao] || (/^K[A-Z]{3}$/.test(icao) ? icao.slice(1) : icao.slice(-3));
}
function badgeInfo(p = S.profile || {}, car = S.career || {}, staff = S.me?.staff) {
  const id = String(p.pilot_id || "PAC0001");
  const n = parseInt(id.replace(/\D/g, ""), 10) || 1;
  const areas = ["RAMP", "CARGO", "AOA"];                       // every pilot: ramp, cargo build-up, movement area
  if (staff) areas.push("OCC");                                 // staff also get operations control
  const ratings = [...new Set((p.type_ratings || []).filter(r => r.status !== "Inactive").map(r => r.type))];
  const since = p.member_since ? new Date(p.member_since + "T00:00:00Z") : null;
  const expires = since ? new Date(Date.UTC(since.getUTCFullYear() + 3, since.getUTCMonth(), since.getUTCDate())) : null;
  const d = x => x ? x.toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).toUpperCase() : "—";
  const code = (p.base || "KCVG").match(/\b[A-Z]{4}\b/)?.[0] || (p.base || "KCVG").split(/[ ,/]/)[0].slice(0, 4).toUpperCase();
  const iata = badgeIata(code);
  return { p, car, id, n, name: displayName(p), rank: car.rank || p.rank || "Pilot", roles: p.roles || [], base: code, iata,
    badgeNo: `${iata}-${String(n).padStart(5, "0")}`, areas, ratings, issued: d(since), expires: d(expires),
    docNo: `PAC${String(since ? since.getUTCFullYear() % 100 : 26).padStart(2, "0")}${String(n * 7919 % 100000).padStart(5, "0")}`,
    expired: expires ? Date.now() > expires.getTime() : false, photo: p.photo || "/static/pilot-photo.jpg" };
}
/* fine line security pattern (guilloche), drawn as an SVG background */
function badgeGuilloche(seed) {
  let path = "";
  for (let k = 0; k < 14; k++) {
    let d = "";
    for (let x = 0; x <= 260; x += 4) {
      const y = 200 + Math.sin((x + k * 9 + seed) / 23) * (40 + k * 7) + Math.sin((x - k * 13) / 9) * 6;
      d += (x ? "L" : "M") + x + " " + y.toFixed(1);
    }
    path += `<path d="${d}"/>`;
  }
  return `<svg class="crewid-guil" viewBox="0 0 260 400" preserveAspectRatio="none" aria-hidden="true"><g fill="none" stroke-width=".45">${path}</g></svg>`;
}
function badgeHtml(p, car, staff, opts = {}) {
  const b = badgeInfo(p, car, staff);
  const flair = (p || S.profile || {}).flair;
  const micro = ("PAGANI AIR CARGO · " + b.badgeNo + " · ").repeat(12);
  const mrz = `PAC<<${(b.p.name || b.name).toUpperCase().replace(/[^A-Z]+/g, "<")}`.padEnd(30, "<").slice(0, 30) + "\n" + `${b.docNo}<${b.iata}<${b.id}`.padEnd(30, "<").slice(0, 30);
  return `<div class="crewid-wrap">
    <div class="lanyard" aria-hidden="true"><i class="strap l"></i><i class="strap r"></i><i class="clip"></i></div>
    <div class="crewid ${frameCls(flair)}" ${opts.own ? 'id="crewBadge"' : ""} tabindex="0" role="button" aria-label="Crew identification badge for ${esc(b.name)}. Activate to turn it over.">
      <div class="crewid-inner">
        <div class="crewid-face crewid-front">
          ${badgeGuilloche(b.n * 17)}
          <div class="crewid-top"><img src="/static/pac-wordmark-white.png" alt="Pagani Air Cargo"><span>CREW</span></div>
          <div class="crewid-micro" aria-hidden="true">${esc(micro)}</div>
          <div class="crewid-body">
            <div class="crewid-photo"><img src="${esc(b.photo)}" alt="Portrait of ${esc(b.name)}"><i class="holo" aria-hidden="true"></i>
              <span class="crewid-seal" aria-hidden="true"><svg viewBox="0 0 60 60"><defs><path id="sealArc${b.n}" d="M30 30m-21 0a21 21 0 1 1 42 0a21 21 0 1 1-42 0"/></defs><circle cx="30" cy="30" r="27" fill="none" stroke-width="1.6"/><circle cx="30" cy="30" r="16" fill="none" stroke-width=".8"/><text font-size="6.2" font-weight="700" letter-spacing="1"><textPath href="#sealArc${b.n}">PAC OPERATIONS CONTROL · VERIFIED ·</textPath></text><text x="30" y="33" font-size="8" font-weight="800" text-anchor="middle">${esc(b.iata)}</text></svg></span>
            </div>
            <div class="crewid-id">
              <b class="crewid-name">${esc(b.name)}</b>
              <span class="crewid-rank">${esc(b.rank)}</span>
              ${b.roles.length ? `<span class="crewid-role">${esc(b.roles.join(" · "))}</span>` : ""}
              <div class="crewid-no">${esc(b.id)}</div>
              <div class="crewid-rows"><span>Base</span><b>${esc(b.base)}</b><span>Issued</span><b>${esc(b.issued)}</b><span>Expires</span><b class="${b.expired ? "exp" : ""}">${esc(b.expires)}</b></div>
            </div>
          </div>
          <div class="crewid-areas">${b.areas.map(a => `<span>${esc(a)}</span>`).join("")}${(flair?.patches || []).slice(0, 4).map(x => patchTip(x, 22)).join("")}<img class="crewid-ghost" src="${esc(b.photo)}" alt="" aria-hidden="true"></div>
          <div class="crewid-ratings"><span>Type ratings</span>${b.ratings.length ? `<div>${b.ratings.map(r => `<i>${esc(r)}</i>`).join("")}</div>`
            : `<p class="muted" style="margin:2px 0 0;font-size:11px">In training</p>`}</div>
          <i class="crewid-kine" aria-hidden="true"></i>
          <div class="crewid-strip"><svg viewBox="0 0 220 28" preserveAspectRatio="none" class="crewid-bars" aria-hidden="true">${badgeBars(b.badgeNo)}</svg><small>${esc(b.badgeNo)}</small><small class="crewid-doc">DOC ${esc(b.docNo)}</small></div>
        </div>
        <div class="crewid-face crewid-back">
          ${badgeGuilloche(b.n * 31 + 5)}
          <div class="crewid-mag" aria-hidden="true"></div>
          <div class="crewid-backtext">
            <div class="crewid-backhead"><span class="crewid-chip" aria-hidden="true"></span><div><b>Conditions of use</b><small>Airside identification · PAC Security Programme</small></div></div>
            <p>This badge stays with the holder and must be worn visibly airside. It isn't transferable. If found, please return it to PAC Operations Control, Cincinnati.</p>
            <div class="crewid-rows"><span>Type ratings</span><b>${b.ratings.length ? esc(b.ratings.join(" · ")) : "In training"}</b><span>Badge</span><b>${esc(b.badgeNo)}</b><span>Document</span><b>${esc(b.docNo)}</b></div>
            <div class="crewid-sign"><span>Holder's signature</span><i>${esc(b.p.name || b.name)}</i>
              <span class="crewid-stamp" aria-hidden="true">ISSUED<br><b>${esc(b.issued)}</b><br>${esc(b.iata)} BADGE OFFICE</span></div>
            <pre class="crewid-mrz" aria-hidden="true">${esc(mrz)}</pre>
            <small>Pagani Air Cargo is a virtual airline. This badge is for flight simulation and has no real-world validity.</small>
          </div>
        </div>
      </div>
    </div>
    <div class="row crewid-actions"><button class="btn ghost small" type="button" data-badge-flip>Turn it over</button>
      ${opts.own ? `<button class="btn ghost small" type="button" id="badgeDl">Download badge</button><a class="btn ghost small" href="/badge-login" style="text-decoration:none">Sign in with this badge</a>` : ""}</div>
  </div>`;
}
/* a simple barcode pattern from the badge number (decorative) */
function badgeBars(text) {
  let x = 0, out = "";
  for (const ch of String(text)) {
    const c = ch.charCodeAt(0);
    for (let i = 0; i < 4; i++) { const w = ((c >> i) & 1) ? 2.4 : 1.1; if (i % 2 === 0) out += `<rect x="${x.toFixed(2)}" y="0" width="${w.toFixed(2)}" height="28"/>`; x += w + 0.9; }
  }
  return out;
}
function wireBadge() {
  document.querySelectorAll(".crewid-wrap").forEach(w => {
    const el = w.querySelector(".crewid"); if (!el) return;
    const flip = () => el.classList.toggle("flipped");
    el.onclick = flip;
    el.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flip(); } };
    const fb = w.querySelector("[data-badge-flip]"); if (fb) fb.onclick = e => { e.stopPropagation(); flip(); };
  });
  if ($("#badgeDl")) $("#badgeDl").onclick = async e => {
    e.stopPropagation();
    const btn = e.currentTarget; btn.disabled = true;
    try { const cv = await drawBadge(); const a = document.createElement("a"); a.download = `PAC-crew-badge-${badgeInfo().id}.png`; a.href = cv.toDataURL("image/png"); a.click(); }
    catch (err) { toast("The badge image couldn't be made."); }
    finally { btn.disabled = false; }
  };
}
/* the badge as a PNG, drawn at print size */
async function drawBadge() {
  try { await document.fonts?.ready; } catch (e) { }
  const b = badgeInfo();
  const [photo, wm] = await Promise.all([loadImg(b.photo), loadImg("/static/pac-wordmark-white.png")]);
  const W = 648, H = 1008, cv = document.createElement("canvas");
  cv.width = W * 2; cv.height = H + 150;                              // front and back side by side, room for the lanyard above
  const x = cv.getContext("2d");
  const F = (w, sz) => `${w} ${sz}px Saira, "Segoe UI", system-ui, sans-serif`, M = sz => `600 ${sz}px "IBM Plex Mono", Consolas, monospace`;
  const top = 150;
  x.fillStyle = "#6B7078"; x.fillRect(0, 0, W * 2, H + 150);
  // fine-line security pattern (guilloche), as on the on-screen badge
  const guil = (ox, col) => {
    x.save(); roundRect(x, ox + 24, top, W - 48, H - 60, 28); x.clip(); x.strokeStyle = col; x.lineWidth = 1;
    for (let k = 0; k < 18; k++) {
      x.beginPath();
      for (let gx = 0; gx <= W; gx += 6) {
        const gy = top + (H - 60) / 2 + Math.sin((gx + k * 14 + b.n * 17) / 36) * (60 + k * 11) + Math.sin((gx - k * 20) / 14) * 9;
        gx ? x.lineTo(ox + gx, gy) : x.moveTo(ox + gx, gy);
      }
      x.stroke();
    }
    x.restore();
  };
  // lanyard: two straps meeting at the clip, as on screen
  const cx = W / 2, clipY = top - 34;
  [[-1, 0], [1, 0]].forEach(([dir]) => {
    x.save(); x.translate(cx + dir * 14, clipY); x.rotate(dir * 19 * Math.PI / 180);
    const g2 = x.createLinearGradient(-16, 0, 16, 0);
    g2.addColorStop(0, "#9e0000"); g2.addColorStop(.45, "#C80000"); g2.addColorStop(1, "#e23b3b");
    x.fillStyle = g2; x.fillRect(-16, -clipY - 10, 32, clipY + 14); x.restore();
  });
  const cg = x.createLinearGradient(0, clipY, 0, clipY + 46);
  cg.addColorStop(0, "#e7eaee"); cg.addColorStop(.55, "#9aa0a8"); cg.addColorStop(1, "#c3c8ce");
  x.fillStyle = cg; roundRect(x, cx - 44, clipY, 88, 46, 7); x.fill();
  x.strokeStyle = "rgba(0,0,0,.3)"; x.lineWidth = 2; roundRect(x, cx - 44, clipY, 88, 46, 7); x.stroke();
  x.fillStyle = "#6B7078"; roundRect(x, cx - 26, clipY + 12, 52, 24, 4); x.fill();
  // card
  x.fillStyle = "#fff"; roundRect(x, 24, top, W - 48, H - 60, 28); x.fill();
  guil(0, "rgba(200,0,0,.13)");
  x.save(); roundRect(x, 24, top, W - 48, H - 60, 28); x.clip();
  x.fillStyle = "#C80000"; x.fillRect(24, top, W - 48, 96);
  // microprint strip under the header
  x.fillStyle = "#fff3f3"; x.fillRect(24, top + 96, W - 48, 14);
  x.fillStyle = "#a40000"; x.font = M(8); x.fillText(("PAGANI AIR CARGO · " + b.badgeNo + " · ").repeat(10), 30, top + 106);
  const wmH = 34, wmW2 = wm.width / wm.height * wmH;
  x.drawImage(wm, 56, top + 32, wmW2, wmH);
  x.fillStyle = "#fff"; x.font = F(800, 34); x.textAlign = "right"; x.fillText("CREW", W - 56, top + 64); x.textAlign = "left";
  // photo
  const px = 56, py = top + 132, pw = 216, ph = 272;
  x.save(); roundRect(x, px, py, pw, ph, 10); x.clip(); x.fillStyle = "#ddd"; x.fillRect(px, py, pw, ph);
  const s = Math.max(pw / photo.width, ph / photo.height);
  x.drawImage(photo, px + (pw - photo.width * s) / 2, py + (ph - photo.height * s) / 2, photo.width * s, photo.height * s);
  const g = x.createLinearGradient(px, py, px + pw, py + ph);
  g.addColorStop(0, "rgba(255,255,255,0)"); g.addColorStop(.45, "rgba(255,255,255,.22)"); g.addColorStop(.55, "rgba(255,255,255,0)");
  x.fillStyle = g; x.fillRect(px, py, pw, ph); x.restore();
  x.strokeStyle = "#e3e5e8"; x.lineWidth = 2; roundRect(x, px, py, pw, ph, 10); x.stroke();
  // holographic sheen and the verification seal over the photo's corner
  const hg = x.createLinearGradient(px, py, px + pw, py + ph);
  [[.3, "rgba(255,120,200,0)"], [.42, "rgba(255,120,200,.22)"], [.5, "rgba(120,220,255,.26)"], [.58, "rgba(255,240,140,.22)"], [.7, "rgba(255,240,140,0)"]].forEach(([o, c]) => hg.addColorStop(o, c));
  x.fillStyle = hg; x.fillRect(px, py, pw, ph);
  x.save(); x.translate(px + pw - 20, py + ph - 34); x.rotate(-14 * Math.PI / 180); x.globalAlpha = .62;
  x.strokeStyle = x.fillStyle = "#7a1aa0"; x.lineWidth = 3; x.beginPath(); x.arc(0, 0, 46, 0, Math.PI * 2); x.stroke();
  x.lineWidth = 1.5; x.beginPath(); x.arc(0, 0, 27, 0, Math.PI * 2); x.stroke();
  x.font = F(700, 9); const seal = "PAC OPERATIONS CONTROL · VERIFIED · ";
  [...seal].forEach((ch, i) => { x.save(); x.rotate(i / seal.length * Math.PI * 2); x.fillText(ch, -3, -33); x.restore(); });
  x.font = F(800, 15); x.textAlign = "center"; x.fillText(b.iata, 0, 6); x.textAlign = "left"; x.restore();
  // name block
  const tx = px + pw + 28;
  x.fillStyle = "#1E2126"; x.font = F(800, 38);
  const maxW = W - 56 - tx, lines = [];        // wrap the name to the space beside the photo
  b.name.split(" ").forEach(w => { const t = lines.length ? lines[lines.length - 1] + " " + w : w; if (lines.length && x.measureText(t).width <= maxW) lines[lines.length - 1] = t; else lines.push(w); });
  const name = lines.join("\n");
  name.split("\n").forEach((ln, i) => x.fillText(ln, tx, py + 40 + i * 42));
  x.fillStyle = "#5E6470"; x.font = F(600, 21); x.fillText(b.rank, tx, py + 40 + name.split("\n").length * 42 + 6);
  x.fillStyle = "#C80000"; x.font = M(30); x.fillText(b.id, tx, py + 40 + name.split("\n").length * 42 + 48);
  // facts
  let fy = py + ph + 56;
  [["BASE", b.base], ["ISSUED", b.issued], ["EXPIRES", b.expires]].forEach(([k, v]) => {
    x.fillStyle = "#5E6470"; x.font = F(600, 17); x.fillText(k, 56, fy);
    x.fillStyle = "#1E2126"; x.font = F(700, 25); x.fillText(String(v), 230, fy); fy += 44;
  });
  // access areas
  fy += 10; x.fillStyle = "#5E6470"; x.font = F(600, 17); x.fillText("ACCESS", 56, fy); fy += 16;
  let ax = 56;
  b.areas.forEach(a => {
    x.font = F(800, 23); const w = x.measureText(a).width + 34;
    x.fillStyle = "#1E2126"; roundRect(x, ax, fy, w, 44, 4); x.fill();
    x.fillStyle = "#fff"; x.fillText(a, ax + 17, fy + 31); ax += w + 10;
  });
  fy += 76;
  // ratings
  if (b.ratings.length) {
    x.fillStyle = "#5E6470"; x.font = F(600, 17); x.fillText("TYPE RATINGS", 56, fy); fy += 30;
    x.font = M(20); x.fillStyle = "#1E2126";
    let line = "";                                     // wrap onto as many lines as the ratings need
    b.ratings.forEach((r, i) => {
      const next = line ? `${line}  ·  ${r}` : r;
      if (x.measureText(next).width > W - 112) { x.fillText(line, 56, fy); fy += 30; line = r; } else line = next;
      if (i === b.ratings.length - 1 && line) { x.fillText(line, 56, fy); fy += 40; }
    });
  }
  // ghost portrait and the colour-shifting strip
  const gw = 54, gh = 68, gxp = W - 56 - gw, gyp = top + H - 60 - 118 - 30 - gh;
  x.save(); x.globalAlpha = .16; x.filter = "grayscale(1) contrast(1.4)";
  const gs = Math.max(gw / photo.width, gh / photo.height); x.beginPath(); x.rect(gxp, gyp, gw, gh); x.clip();
  x.drawImage(photo, gxp + (gw - photo.width * gs) / 2, gyp + (gh - photo.height * gs) / 2, photo.width * gs, photo.height * gs); x.restore();
  const kg = x.createLinearGradient(56, 0, W - 56, 0);
  ["#c0c4c9", "#f6e3a8", "#b9e4f5", "#f2b9da", "#c0c4c9"].forEach((c, i) => kg.addColorStop(i / 4, c));
  x.fillStyle = kg; roundRect(x, 56, top + H - 60 - 118 - 22, W - 112, 10, 5); x.fill();
  // barcode
  const by = top + H - 60 - 118;
  x.fillStyle = "#1E2126";
  let bx = 56;
  for (const ch of b.badgeNo) {
    const c = ch.charCodeAt(0);
    for (let i = 0; i < 4; i++) { const w = ((c >> i) & 1) ? 6 : 2.6; if (i % 2 === 0) x.fillRect(bx, by, w, 54); bx += w + 2.4; }
  }
  x.font = M(19); x.fillStyle = "#5E6470"; x.fillText(b.badgeNo, 56, by + 80);
  x.font = M(17); x.textAlign = "right"; x.fillText(`DOC ${b.docNo}`, W - 56, by + 80); x.textAlign = "left";
  x.restore();
  // ---- the back
  const o = W;
  x.fillStyle = "#fff"; roundRect(x, o + 24, top, W - 48, H - 60, 28); x.fill();
  guil(o, "rgba(30,33,38,.09)");
  x.save(); roundRect(x, o + 24, top, W - 48, H - 60, 28); x.clip();
  x.fillStyle = "#1E2126"; x.fillRect(o + 24, top + 40, W - 48, 64);                     // magnetic stripe
  const chip = x.createLinearGradient(o + 56, top + 140, o + 126, top + 194);
  chip.addColorStop(0, "#f3dc93"); chip.addColorStop(.55, "#c9a24b"); chip.addColorStop(1, "#e9cf86");
  x.fillStyle = chip; roundRect(x, o + 56, top + 140, 70, 54, 8); x.fill();
  x.strokeStyle = "#8f6f2c"; x.lineWidth = 2; roundRect(x, o + 56, top + 140, 70, 54, 8); x.stroke();
  x.beginPath(); x.moveTo(o + 79, top + 140); x.lineTo(o + 79, top + 194); x.moveTo(o + 103, top + 140); x.lineTo(o + 103, top + 194); x.moveTo(o + 56, top + 167); x.lineTo(o + 126, top + 167); x.stroke();
  x.fillStyle = "#1E2126"; x.font = F(800, 26); x.fillText("Conditions of use", o + 146, top + 166);
  x.fillStyle = "#5E6470"; x.font = F(600, 16); x.fillText("Airside identification · PAC Security Programme", o + 146, top + 190);
  const wrap = (txt, yy, max, lh) => { let line = ""; txt.split(" ").forEach(w => { const t = line ? line + " " + w : w; if (x.measureText(t).width > max) { x.fillText(line, o + 56, yy); yy += lh; line = w; } else line = t; }); if (line) x.fillText(line, o + 56, yy); return yy + lh; };
  x.fillStyle = "#1E2126"; x.font = F(500, 19);
  let yb = wrap("This badge stays with the holder and must be worn visibly airside. It isn't transferable. If found, please return it to PAC Operations Control, Cincinnati.", top + 248, W - 112, 28);
  yb += 14;
  [["TYPE RATINGS", b.ratings.length ? b.ratings.join(" · ") : "In training"], ["BADGE", b.badgeNo], ["DOCUMENT", b.docNo]].forEach(([k, v]) => {
    x.fillStyle = "#5E6470"; x.font = F(600, 16); x.fillText(k, o + 56, yb);
    x.fillStyle = "#1E2126"; x.font = F(700, 20); yb = wrap(String(v), yb + 26, W - 112, 26) + 6;
  });
  yb += 20; x.fillStyle = "#5E6470"; x.font = F(600, 16); x.fillText("HOLDER'S SIGNATURE", o + 56, yb);
  x.strokeStyle = "#c9cdd2"; x.lineWidth = 1.5; x.beginPath(); x.moveTo(o + 56, yb + 62); x.lineTo(o + W - 220, yb + 62); x.stroke();
  x.fillStyle = "#1b2a6b"; x.font = `italic 40px "Brush Script MT","Segoe Script","Snell Roundhand",cursive`; x.fillText(b.p.name || b.name, o + 66, yb + 54);
  x.save(); x.translate(o + W - 130, yb + 30); x.rotate(9 * Math.PI / 180); x.globalAlpha = .72;
  x.strokeStyle = x.fillStyle = "#c80000"; x.lineWidth = 3; roundRect(x, -78, -40, 156, 80, 8); x.stroke();
  x.textAlign = "center"; x.font = F(800, 14); x.fillText("ISSUED", 0, -16); x.font = F(800, 18); x.fillText(b.issued, 0, 8);
  x.font = F(800, 12); x.fillText(`${b.iata} BADGE OFFICE`, 0, 28); x.textAlign = "left"; x.restore();
  const mrz = [`PAC<<${(b.p.name || b.name).toUpperCase().replace(/[^A-Z]+/g, "<")}`.padEnd(30, "<").slice(0, 30), `${b.docNo}<${b.iata}<${b.id}`.padEnd(30, "<").slice(0, 30)];
  x.fillStyle = "rgba(255,255,255,.85)"; x.fillRect(o + 24, top + H - 60 - 150, W - 48, 86);
  x.fillStyle = "#1E2126"; x.font = M(26); mrz.forEach((ln, i) => x.fillText(ln, o + 50, top + H - 60 - 112 + i * 34));
  x.fillStyle = "#5E6470"; x.font = F(500, 14);
  wrap("Pagani Air Cargo is a virtual airline. This badge is for flight simulation and has no real-world validity.", top + H - 60 - 34, W - 112, 18);
  x.restore();
  return cv;
}

async function drawLicence(front, back) {
  try { await document.fonts?.ready; } catch (e) { }
  const p = S.profile, car = S.career || {}, st = S.pstats?.totals || {};
  const insignia = (S.ranks || []).find(r => r.name === car.rank)?.insignia;
  const [photo, wmW, wmR, patch] = await Promise.all([loadImg(p.photo), loadImg("/static/pac-wordmark-white.png"), loadImg("/static/pac-wordmark-red.png"), loadImg(insignia)]);
  const F = (w, sz) => `${w} ${sz}px Saira, "Segoe UI", system-ui, sans-serif`, M = sz => `600 ${sz}px "IBM Plex Mono", Consolas, monospace`;
  const W = 1712, H = 1080, R = 56;
  const ratings = [...new Map((p.type_ratings || []).filter(r => r.status !== "Inactive").map(r => [r.type, r])).values()];
  const issued = p.member_since ? new Date(p.member_since + "T00:00:00Z").toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).toUpperCase() : "—";

  // ---------- front ----------
  let x = front.getContext("2d");
  x.clearRect(0, 0, W, H); roundRect(x, 0, 0, W, H, R); x.save(); x.clip();
  let g = x.createLinearGradient(0, 0, W, H); g.addColorStop(0, "#FFFFFF"); g.addColorStop(1, "#F1F2F5");
  x.fillStyle = g; x.fillRect(0, 0, W, H);
  guilloche(x, W, H + 200, "#C80000", 0.07);
  x.fillStyle = "#C80000"; x.fillRect(0, 0, W, 170);
  guilloche(x, W, 170, "#FFFFFF", 0.08);
  if (wmW) x.drawImage(wmW, 64, 52, 66 * wmW.width / wmW.height, 66);
  x.fillStyle = "#fff"; x.textAlign = "right"; x.font = F(800, 50); x.fillText("FLIGHT CREW LICENSE", W - 64, 90);
  x.font = F(600, 24); x.globalAlpha = .9; x.fillText("PAGANI AIR CARGO · VIRTUAL AIRLINE", W - 64, 132); x.globalAlpha = 1;
  // photo
  const px = 64, py = 220, pw = 380, ph = 475;
  x.save(); roundRect(x, px, py, pw, ph, 18); x.clip(); x.fillStyle = "#ddd"; x.fillRect(px, py, pw, ph);
  if (photo) { const sc = Math.max(pw / photo.width, ph / photo.height); x.drawImage(photo, px + (pw - photo.width * sc) / 2, py + (ph - photo.height * sc) / 2, photo.width * sc, photo.height * sc); }
  x.restore(); roundRect(x, px, py, pw, ph, 18); x.strokeStyle = "#1E2126"; x.lineWidth = 3; x.stroke();
  // hologram
  const hx = px + pw - 20, hy = py + ph - 30;
  for (let i = 0; i < 7; i++) { x.beginPath(); x.arc(hx, hy, 82 - i * 9, 0, Math.PI * 2); x.strokeStyle = `hsla(${i * 50}, 90%, 60%, .35)`; x.lineWidth = 7; x.stroke(); }
  x.beginPath(); x.arc(hx, hy, 34, 0, Math.PI * 2); x.fillStyle = "rgba(255,255,255,.75)"; x.fill();
  if (wmR) x.drawImage(wmR, hx - 26, hy - 9, 52, 52 * wmR.height / wmR.width);
  // fields
  const fx = 500; let fy = 250;
  const field = (label, value, size = 44, w = 0) => { x.textAlign = "left"; x.fillStyle = "#5E6470"; x.font = F(700, 20); x.fillText(label, fx + w, fy);
    x.fillStyle = "#1E2126"; x.font = F(700, size); x.fillText(value, fx + w, fy + size + 6); };
  field("NAME", (p.name || "").toUpperCase(), 54); fy += 110;
  field("PILOT ID", p.pilot_id || "—"); field("RANK", (car.rank || p.rank || "").toUpperCase(), 44, 330); fy += 100;
  field("HOME BASE", (p.base || "").split(" ")[0] || "KCVG"); field("ISSUED", issued, 44, 330); fy += 100;
  field("CALLSIGN", (p.callsign || "—").toUpperCase(), 44); field("STATUS", "CURRENT", 44, 330);
  // insignia
  if (patch) { const h = 390, w = h * patch.width / patch.height; x.drawImage(patch, W - 64 - w, 225, w, h); }
  // signature
  x.fillStyle = "#1c2f7a"; x.font = `italic 400 54px "Segoe Script", "Brush Script MT", cursive`; x.textAlign = "left";
  x.fillText(p.name || "", px + 10, py + ph + 78);
  x.strokeStyle = "#1E2126"; x.lineWidth = 1.5; x.beginPath(); x.moveTo(px, py + ph + 94); x.lineTo(px + pw, py + ph + 94); x.stroke();
  x.fillStyle = "#5E6470"; x.font = F(600, 16); x.fillText("HOLDER'S SIGNATURE", px, py + ph + 118);
  // ratings chips
  x.fillStyle = "#5E6470"; x.font = F(700, 20); x.fillText("TYPE RATINGS", fx, 745);
  let cx = fx, cy = 765;
  ratings.forEach(r => { x.font = F(800, 30); const tw = x.measureText(r.type).width + 34; if (cx + tw > W - 64) { cx = fx; cy += 58; }
    x.fillStyle = "#1E2126"; roundRect(x, cx, cy, tw, 48, 6); x.fill(); x.fillStyle = "#fff"; x.fillText(r.type, cx + 17, cy + 35); cx += tw + 12; });
  // MRZ
  x.fillStyle = "rgba(30,33,38,.06)"; x.fillRect(0, H - 150, W, 150);
  const names = (p.name || "").trim().split(/\s+/); const last = names.pop() || ""; const firsts = names.join(" ");
  x.fillStyle = "#1E2126"; x.font = M(40); x.textAlign = "left";
  x.fillText(mrz(`PL PAC ${last}  ${firsts}`, 44), 64, H - 90);
  x.fillText(mrz(`${p.pilot_id || ""}  ${car.rank || ""}  ${(p.base || "KCVG").split(" ")[0]}  ${(p.member_since || "").replace(/-/g, "").slice(2)}`, 44), 64, H - 40);
  x.restore();

  // ---------- back ----------
  x = back.getContext("2d");
  x.clearRect(0, 0, W, H); roundRect(x, 0, 0, W, H, R); x.save(); x.clip();
  g = x.createLinearGradient(0, 0, W, H); g.addColorStop(0, "#1E2126"); g.addColorStop(1, "#0f1013");
  x.fillStyle = g; x.fillRect(0, 0, W, H);
  guilloche(x, W, H + 300, "#C80000", 0.14);
  x.fillStyle = "#C80000"; x.fillRect(0, 0, 22, H);
  x.fillStyle = "#fff"; x.textAlign = "left"; x.font = F(800, 42); x.fillText("TYPE RATINGS AND PRIVILEGES", 70, 100);
  x.fillStyle = "rgba(255,255,255,.55)"; x.font = F(600, 22); x.fillText(`${(p.name || "").toUpperCase()} · ${p.pilot_id || ""}`, 70, 140);
  const rows = (p.type_ratings || []).filter(r => r.status !== "Inactive").slice(0, 12);
  const colW = (W - 140 - 40) / 2;
  rows.forEach((r, i) => {
    const col = i % 2, row = Math.floor(i / 2), X = 70 + col * (colW + 40), Y = 190 + row * 82;
    x.fillStyle = "rgba(255,255,255,.06)"; roundRect(x, X, Y, colW, 68, 8); x.fill();
    x.fillStyle = "#C80000"; roundRect(x, X, Y, 130, 68, 8); x.fill();
    x.fillStyle = "#fff"; x.font = F(800, 30); x.textAlign = "center"; x.fillText(r.type, X + 65, Y + 45);
    x.textAlign = "left"; x.font = F(700, 26); x.fillText((r.name || "").slice(0, 30), X + 150, Y + 32);
    x.fillStyle = "rgba(255,255,255,.6)"; x.font = F(500, 20); x.fillText(`${r.role || "Captain"}${r.notes ? " · " + r.notes.slice(0, 28) : ""}`, X + 150, Y + 57);
  });
  const sy = H - 250;
  const stat = (label, val, X) => { x.fillStyle = "rgba(255,255,255,.55)"; x.font = F(700, 20); x.textAlign = "left"; x.fillText(label, X, sy); x.fillStyle = "#fff"; x.font = F(800, 46); x.fillText(val, X, sy + 54); };
  stat("CAREER RANK", (car.rank || "—").toUpperCase(), 70);
  stat("PAC FLIGHTS", String(st.flights ?? car.flights ?? 0), 620);
  stat("PAC HOURS", (st.block_hours ?? car.pac_hours ?? 0).toFixed(1), 900);
  if (patch) { const h = 250, w = h * patch.width / patch.height; x.drawImage(patch, W - 70 - w, sy - 70, w, h); }
  x.fillStyle = "rgba(255,255,255,.45)"; x.font = F(500, 19);
  x.fillText("Issued by Pagani Air Cargo Operations, Cincinnati. Valid for flight simulation use only.", 70, H - 60);
  x.restore();
}
async function openLicence() {
  $("#licenceDlg").showModal();
  try {
    if (!S.pstats || !S.profile) { const r = await api("/api/profile"); S.profile = r.profile; S.pstats = r.stats; }
    await refreshCore();
    await drawLicence($("#licFront"), $("#licBack"));
  } catch (e) { toast(e.message); }
  const dl = (cv, side) => cv.toBlob(b => { const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = `PAC-license-${S.profile.pilot_id}-${side}.png`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); }, "image/png");
  $("#licDlFront").onclick = () => dl($("#licFront"), "front");
  $("#licDlBack").onclick = () => dl($("#licBack"), "back");
}

/* ================= Partner flights on the cards ================= */
// a partner flight's number is the partner's code plus digits (UPS2414, FDX123, CPA020)
function partnerForFlight(flight) {
  const f = String(flight || "");
  return Object.values(S.partners || {}).find(p => p.code && f.startsWith(p.code) && /^\d+$/.test(f.slice(p.code.length))) || null;
}
async function partnerCard(c) {
  const partner = partnerForFlight(c.flight);
  if (!partner) return null;
  if (!S.partnerPhotos) { try { S.partnerPhotos = await api("/api/partner-photos"); } catch (e) { S.partnerPhotos = {}; } }
  return { partner, photo: S.partnerPhotos[`${partner.key}|${c.aircraft}`] || null };
}
function drawCardLogo(x, wm, pc) {
  if (!wm) return;
  if (!pc) { x.drawImage(wm, 52, 50, 56 * wm.width / wm.height, 56); return; }
  // partner logos are in color: set them on a white plate so every one reads on the photo
  const b = logoBox(wm);   // crop the empty margin some logo files carry, so the plate hugs the logo
  const h = 64, w = Math.min(300, h * b.w / b.h), pad = 14;
  x.fillStyle = "rgba(255,255,255,.94)"; x.beginPath(); if (x.roundRect) x.roundRect(40, 40, w + pad * 2, h + pad * 2, 10); else x.rect(40, 40, w + pad * 2, h + pad * 2); x.fill();
  x.drawImage(wm, b.x, b.y, b.w, b.h, 40 + pad, 40 + pad, w, h);
}
function logoBox(img) {
  const full = { x: 0, y: 0, w: img.width, h: img.height };
  try {
    const c = document.createElement("canvas"); c.width = img.width; c.height = img.height;
    const g = c.getContext("2d"); g.drawImage(img, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height).data;
    let x0 = c.width, y0 = c.height, x1 = -1, y1 = -1;
    for (let y = 0; y < c.height; y++) for (let xx = 0; xx < c.width; xx++) {
      const i = (y * c.width + xx) * 4;
      // count a pixel as logo if it isn't transparent and isn't plain white
      if (d[i + 3] > 24 && !(d[i] > 245 && d[i + 1] > 245 && d[i + 2] > 245)) { if (xx < x0) x0 = xx; if (xx > x1) x1 = xx; if (y < y0) y0 = y; if (y > y1) y1 = y; }
    }
    if (x1 < x0 || y1 < y0) return full;
    return { x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 };
  } catch (e) { return full; }
}
function drawPhotoCredit(x, ph, W, PH) {
  // the photographer and the license, as the license requires
  const t = `Photo: ${ph.artist || "Unknown photographer"} · ${ph.licence || ""} · Wikimedia Commons`.slice(0, 110);
  x.save(); x.textAlign = "right"; x.font = `500 17px Saira, "Segoe UI", system-ui, sans-serif`; x.fillStyle = "rgba(255,255,255,.72)";
  x.shadowColor = "rgba(0,0,0,.8)"; x.shadowBlur = 4; x.fillText(t, W - 24, PH - 14); x.restore();
}

/* ================= Takeoff card and analysis ================= */
async function drawTakeoffCard(canvas, c) {
  try { await document.fonts?.ready; } catch (e) { }
  const W = 1080, H = 1350; canvas.width = W; canvas.height = H;
  const x = canvas.getContext("2d"), F = (w, sz) => `${w} ${sz}px Saira, "Segoe UI", system-ui, sans-serif`;
  const ac = S.fleet[c.aircraft] || {}, ta = c.ta || {};
  const insignia = (S.ranks || []).find(r => r.name === c.rank)?.insignia;
  const pc = await partnerCard(c);   // flown for a partner airline: their photo (credited) and their logo
  const [photo, wm, patch] = await Promise.all([loadImg(pc?.photo?.url || ac.photo), loadImg(pc ? pc.partner.logo : "/static/pac-wordmark-white.png"), loadImg(insignia)]);
  x.fillStyle = "#141619"; x.fillRect(0, 0, W, H);
  const PH = 640;
  if (photo) { const sc = Math.max(W / photo.width, PH / photo.height), w = photo.width * sc, h = photo.height * sc; x.drawImage(photo, (W - w) / 2, (PH - h) / 2, w, h); }
  let gr = x.createLinearGradient(0, 0, 0, PH); gr.addColorStop(0, "rgba(0,0,0,.55)"); gr.addColorStop(.35, "rgba(0,0,0,0)"); gr.addColorStop(1, "rgba(0,0,0,.8)");
  x.fillStyle = gr; x.fillRect(0, 0, W, PH);
  drawCardLogo(x, wm, pc);
  if (pc?.photo) drawPhotoCredit(x, pc.photo, W, PH);
  x.textAlign = "right"; x.fillStyle = "#fff"; x.font = F(800, 64); x.fillText(c.flight, W - 52, 104);
  x.font = F(700, 28); x.fillStyle = "#FFC845"; x.fillText("TAKEOFF", W - 52, 146);
  x.textAlign = "left"; x.font = F(700, 36); x.fillStyle = "#fff"; x.fillText(ac.name || c.aircraft, 52, PH - 60);
  x.font = F(500, 28); x.fillStyle = "rgba(255,255,255,.8)"; x.fillText([c.airframe, c.sim || ac.sim, c.date].filter(Boolean).join("  ·  "), 52, PH - 22);
  x.fillStyle = "#C80000"; x.fillRect(0, PH, W, 108);
  x.fillStyle = "#fff"; x.font = F(800, 70); x.fillText(`${c.dep}  →  ${c.arr}`, 52, PH + 80);
  if (ta.runway) { x.textAlign = "right"; x.font = F(700, 40); x.fillText(`RWY ${ta.runway}`, W - 52, PH + 72); x.textAlign = "left"; }
  // pitch gauge 0..16 deg with the tail-strike zone
  const cx = 300, cy = 1030, R = 210, max = 16, lim = ta.tail_limit || 12;
  const ang = v => Math.PI + Math.min(Math.max(v, 0), max) / max * Math.PI;
  [[0, lim - 2, "#4BD07F"], [lim - 2, lim, "#FFC845"], [lim, max, "#FF4D4D"]].forEach(([a, b, col]) => { x.beginPath(); x.strokeStyle = col; x.lineWidth = 34; x.arc(cx, cy, R, ang(a) + .01, ang(b) - .01); x.stroke(); });
  x.fillStyle = "rgba(255,255,255,.5)"; x.font = F(600, 22); x.textAlign = "center";
  [0, 4, 8, 12, 16].forEach(v => { const a = ang(v); x.fillText(`${v}°`, cx + Math.cos(a) * (R - 58), cy + Math.sin(a) * (R - 58) + 8); });
  const pv = ta.max_pitch_ground ?? ta.liftoff_pitch;
  if (pv != null) { const a = ang(pv); x.strokeStyle = "#fff"; x.lineWidth = 10; x.lineCap = "round"; x.beginPath(); x.moveTo(cx, cy); x.lineTo(cx + Math.cos(a) * (R - 18), cy + Math.sin(a) * (R - 18)); x.stroke();
    x.fillStyle = "#fff"; x.beginPath(); x.arc(cx, cy, 16, 0, Math.PI * 2); x.fill(); }
  x.fillStyle = "#fff"; x.font = F(800, 92); x.fillText(pv != null ? `${pv}°` : "–", cx, cy + 98);
  x.fillStyle = ta.tail_strike ? "#FF4D4D" : "#4BD07F"; x.font = F(700, 28);
  x.fillText(ta.tail_strike ? "TAIL STRIKE" : ta.tail_margin != null ? `${ta.tail_margin}° TAIL MARGIN` : "PITCH ON THE GROUND", cx, cy + 142);
  x.textAlign = "left";
  [["ROTATE", ta.rotate_ias != null ? `${ta.rotate_ias} kt` : "–"], ["LIFTOFF", ta.liftoff_ias != null ? `${ta.liftoff_ias} kt` : "–"],
   ["GROUND ROLL", ta.roll_ft != null ? `${fmt(ta.roll_ft)} ft` : "–"], ["INITIAL CLIMB", ta.climb_fpm != null ? `${fmt(ta.climb_fpm)} fpm` : "–"]].forEach(([l, v], i) => {
    const y = 820 + i * 92; x.fillStyle = "rgba(255,255,255,.55)"; x.font = F(600, 24); x.fillText(l, 600, y); x.fillStyle = "#fff"; x.font = F(700, 46); x.fillText(v, 600, y + 50); });
  x.fillStyle = "#C80000"; x.fillRect(W - 52 - 150, 792, 150, 150);
  x.fillStyle = "#fff"; x.textAlign = "center"; x.font = F(800, 46); x.fillText(ta.rotation_rate != null ? `${ta.rotation_rate}` : "–", W - 52 - 75, 872);
  x.font = F(600, 22); x.fillText("°/s ROTATION", W - 52 - 75, 910);
  x.fillStyle = "#0b0c0e"; x.fillRect(0, H - 170, W, 170);
  let fx = 52; if (patch) { const ph = 130, pw = ph * patch.width / patch.height; x.drawImage(patch, fx, H - 150, pw, ph); fx += pw + 26; }
  x.textAlign = "left"; x.fillStyle = "#fff"; x.font = F(700, 40); x.fillText(c.pilot || "", fx, H - 92);
  x.fillStyle = "rgba(255,255,255,.6)"; x.font = F(500, 28); x.fillText(c.rank || "", fx, H - 52);
  x.textAlign = "right"; x.fillStyle = "rgba(255,255,255,.45)"; x.font = F(700, 24); x.fillText(pc ? `FLOWN FOR ${pc.partner.name.toUpperCase()}` : "PAGANI AIR CARGO", W - 52, H - 88);
  x.font = F(500, 22); x.fillText([ta.remaining_ft != null ? `${fmt(ta.remaining_ft)} ft of runway left` : "", ta.touchback ? "Touched back down" : ""].filter(Boolean).join("  ·  "), W - 52, H - 54);
  x.textAlign = "left";
}
function takeoffDiagram(ta) {
  if (ta?.start_ft == null || !ta.runway_length_ft || ta.liftoff_ft == null) return "";
  const L = ta.runway_length_ft, VW = 1000, VH = 190, rx0 = 20, rx1 = 980, ry = 62, rh = 80;
  const X = ft => rx0 + Math.max(0, Math.min(L, ft)) / L * (rx1 - rx0);
  return `<div class="rwy-strip"><svg viewBox="0 0 ${VW} ${VH}" role="img" aria-label="Takeoff roll on runway ${esc(ta.runway)}">
    <rect x="${rx0}" y="${ry}" width="${rx1 - rx0}" height="${rh}" fill="#3a3d43" rx="3"/>
    <line x1="${rx0 + 40}" y1="${ry + rh / 2}" x2="${rx1 - 10}" y2="${ry + rh / 2}" stroke="#e9e9e9" stroke-width="2" stroke-dasharray="18 14"/>
    <text x="${rx0 + 10}" y="${ry + rh / 2 + 9}" fill="#fff" font-size="26" font-weight="700" font-family="Saira, sans-serif">${esc(ta.runway)}</text>
    <line x1="${X(ta.start_ft)}" y1="${ry + rh / 2}" x2="${X(ta.liftoff_ft)}" y2="${ry + rh / 2}" stroke="#FFC845" stroke-width="7" stroke-linecap="round"/>
    <circle cx="${X(ta.start_ft)}" cy="${ry + rh / 2}" r="10" fill="#FFC845" stroke="#fff" stroke-width="3"/>
    <circle cx="${X(ta.liftoff_ft)}" cy="${ry + rh / 2}" r="13" fill="#FF3B3B" stroke="#fff" stroke-width="3"/>
    <text x="${X(ta.liftoff_ft)}" y="${ry - 16}" fill="#fff" font-size="28" text-anchor="middle" font-family="Saira, sans-serif">Liftoff ${fmt(ta.liftoff_ft)} ft</text>
    <text x="${X(ta.start_ft)}" y="${ry + rh + 34}" fill="#FFC845" font-size="24" text-anchor="start" font-family="Saira, sans-serif">Roll ${fmt(ta.roll_ft)} ft</text>
    ${ta.remaining_ft != null ? `<text x="${rx1}" y="${ry + rh + 34}" fill="#8E96A3" font-size="24" text-anchor="end" font-family="Saira, sans-serif">${fmt(ta.remaining_ft)} ft remaining</text>` : ""}
  </svg></div>`;
}
function takeoffChart(ta) {
  const pts = (ta?.series || []).filter(p => p[4] != null);
  if (pts.length < 5) return "";
  const lim = ta.tail_limit;
  return `<div class="chart-box"><h3>Rotation and liftoff</h3><div class="legend"><span><i style="background:#C80000"></i>Pitch (°, left)</span><span><i style="background:#1E2126"></i>Indicated airspeed (kt, right)</span>${lim ? `<span><i style="background:#FF8A3D"></i>Ground pitch reference ${lim}° (before liftoff)</span>` : ""}</div>
    ${svgChart({ xDomain: [pts[0][0], pts[pts.length - 1][0]], xLabel: v => `${Math.round(v)}s`, left: { domain: [-2, 20], fmt: v => `${Math.round(v)}°` }, right: { domain: [0, niceMax(Math.max(...pts.map(p => p[3])) * 1.1)], fmt: v => Math.round(v) },
      marks: [{ x: 0, label: "Liftoff", color: "#C80000" }],
      series: [{ pts: pts.map(p => [p[0], p[4]]), color: "#C80000", width: 2.5 }, { pts: pts.map(p => [p[0], p[3]]), color: "#1E2126", axis: "r" },
               ...(lim && pts[0][0] < 0 ? [{ pts: [[pts[0][0], lim], [Math.min(0, pts[pts.length - 1][0]), lim]], color: "#FF8A3D", width: 1.5 }] : [])] })}</div>`;
}
function takeoffSection(id, c) {
  const ta = c.ta;
  if (!ta) return "";
  const cells = [
    ["Runway", ta.runway ? `${ta.airport} ${ta.runway}` : "–", ta.runway_length_ft ? `${fmt(ta.runway_length_ft)} ft long` : ""],
    ["Rotate", ta.rotate_ias != null ? `${ta.rotate_ias} kt` : "–", ta.rotation_rate != null ? `${ta.rotation_rate}°/s rotation rate` : ""],
    ["Liftoff", `${ta.liftoff_ias} kt`, ta.liftoff_pitch != null ? `${ta.liftoff_pitch}° pitch` : ""],
    ["Pitch on the ground", ta.max_pitch_ground != null ? `${ta.max_pitch_ground}°` : "–", ta.tail_limit ? (ta.tail_strike ? `Tail strike: limit ${ta.tail_limit}°` : `${ta.tail_margin}° below the ${ta.tail_limit}° tail-strike pitch`) : ""],
    ["Ground roll", ta.roll_ft != null ? `${fmt(ta.roll_ft)} ft` : "–", ta.remaining_ft != null ? `${fmt(ta.remaining_ft)} ft of runway left` : ""],
    ["Initial climb", ta.climb_fpm != null ? `${fmt(ta.climb_fpm)} fpm` : "–", ta.time_to_1000_s != null ? `1,000 ft after ${ta.time_to_1000_s} s` : ""],
  ];
  return `<div class="landing-wrap"><div class="landing-card"><canvas id="${id}" width="1080" height="1350" aria-label="Takeoff card for ${esc(c.flight)}"></canvas>
      <div class="row"><button class="btn small" type="button" data-dl-card="${id}">Download takeoff card</button></div></div>
    <div><div class="la-facts">${cells.map(([l, v, sub]) => `<div><span>${l}</span><b style="${l === "Pitch on the ground" && ta.tail_strike ? "color:var(--red)" : ""}">${esc(v)}</b>${sub ? `<small>${esc(sub)}</small>` : ""}</div>`).join("")}</div>
      ${ta.touchback ? `<div class="notice" style="margin-top:12px">The wheels touched the runway again after liftoff. Rotate a little more positively to the target pitch.</div>` : ""}
      ${takeoffDiagram(ta)}</div></div>`;
}
function bindTakeoffCard(id, c) {
  const cv = document.getElementById(id); if (!cv) return;
  drawTakeoffCard(cv, c);
  const dc = document.querySelector(`[data-dc-card="${id}"]`);
  if (dc) dc.onclick = () => shareToDiscord(cv, `🛬 ${c.flight} ${c.dep}–${c.arr} · ${c.rate ?? "–"} fpm · grade ${c.grade}`, `${c.flight}-${c.dep}-${c.arr}-landing.png`, dc);
  document.querySelector(`[data-dl-card="${id}"]`).onclick = () => cv.toBlob(b => { const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = `${c.flight}-${c.dep}-takeoff.png`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); }, "image/png");
}
function integrityNote(integ) {
  if (!integ) return "";
  const bits = [];
  if (integ.paused_air_min >= 1) bits.push(`paused ${integ.paused_air_min} min in flight`);
  if (integ.accel_s >= 10) bits.push(`sim rate up to ${integ.max_rate}× for ${Math.round(integ.accel_s / 60)} min`);
  return bits.length ? `<div class="notice">Integrity: ${esc(bits.join(", "))}. Flights over the limits go to staff review.</div>` : "";
}

/* ================= Landing card, analysis, charts, replay ================= */
function loadImg(src) { return new Promise(res => { if (!src) return res(null); const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = src; }); }
const RATE_ZONES = [[100, "#4BD07F", "BUTTER"], [250, "#A6E05A", "SMOOTH"], [400, "#FFC845", "FIRM"], [600, "#FF8A3D", "HEAVY"], [1000, "#FF4D4D", "HARD"]];
function rateVerdict(r) { if (r == null) return "–"; const a = Math.abs(r); return (RATE_ZONES.find(z => a <= z[0]) || RATE_ZONES[4])[2]; }
function sideText(ft) { return ft == null ? "–" : Math.abs(ft) < 1 ? "On centerline" : `${fmt(Math.abs(ft))} ft ${ft > 0 ? "right" : "left"}`; }

async function drawLandingCard(canvas, c) {
  try { await document.fonts?.ready; } catch (e) { /* ignore */ }
  const W = 1080, H = 1350; canvas.width = W; canvas.height = H;
  const x = canvas.getContext("2d");
  const F = (w, sz) => `${w} ${sz}px Saira, "Segoe UI", system-ui, sans-serif`;
  const ac = S.fleet[c.aircraft] || {};
  const insignia = (S.ranks || []).find(r => r.name === c.rank)?.insignia;
  const pc = await partnerCard(c);   // flown for a partner airline: their photo (credited) and their logo
  const [photo, wm, patch] = await Promise.all([loadImg(pc?.photo?.url || ac.photo), loadImg(pc ? pc.partner.logo : "/static/pac-wordmark-white.png"), loadImg(insignia)]);
  const la = c.la || {};
  x.fillStyle = "#141619"; x.fillRect(0, 0, W, H);
  // photo
  const PH = 640;
  if (photo) {
    const sc = Math.max(W / photo.width, PH / photo.height), w = photo.width * sc, h = photo.height * sc;
    x.drawImage(photo, (W - w) / 2, (PH - h) / 2, w, h);
  }
  let gr = x.createLinearGradient(0, 0, 0, PH);
  gr.addColorStop(0, "rgba(0,0,0,.55)"); gr.addColorStop(.35, "rgba(0,0,0,0)"); gr.addColorStop(.72, "rgba(0,0,0,.05)"); gr.addColorStop(1, "rgba(0,0,0,.8)");
  x.fillStyle = gr; x.fillRect(0, 0, W, PH);
  drawCardLogo(x, wm, pc);
  if (pc?.photo) drawPhotoCredit(x, pc.photo, W, PH);
  x.textAlign = "right"; x.fillStyle = "#fff"; x.font = F(800, 64); x.fillText(c.flight, W - 52, 104);
  x.font = F(600, 28); x.fillStyle = "rgba(255,255,255,.85)"; x.fillText(c.date, W - 52, 146);
  x.textAlign = "left"; x.font = F(700, 36); x.fillStyle = "#fff"; x.fillText(ac.name || c.aircraft, 52, PH - 60);
  x.font = F(500, 28); x.fillStyle = "rgba(255,255,255,.8)"; x.fillText([c.airframe, c.sim || ac.sim].filter(Boolean).join("  ·  "), 52, PH - 22);
  // red band
  x.fillStyle = "#C80000"; x.fillRect(0, PH, W, 108);
  x.fillStyle = "#fff"; x.font = F(800, 70); x.fillText(`${c.dep}  →  ${c.arr}`, 52, PH + 80);
  if (la.runway) { x.textAlign = "right"; x.font = F(700, 40); x.fillText(`RWY ${la.runway}`, W - 52, PH + 72); x.textAlign = "left"; }
  // gauge
  const cx = 300, cy = 1030, R = 210, max = 1000;
  const ang = v => Math.PI + Math.min(Math.abs(v), max) / max * Math.PI;
  let from = 0;
  RATE_ZONES.forEach(([lim, col]) => { x.beginPath(); x.strokeStyle = col; x.lineWidth = 34; x.arc(cx, cy, R, ang(from) + .01, ang(lim) - .01); x.stroke(); from = lim; });
  x.fillStyle = "rgba(255,255,255,.5)"; x.font = F(600, 22); x.textAlign = "center";
  [0, 250, 500, 750, 1000].forEach(v => { const a = ang(v); x.fillText(String(v), cx + Math.cos(a) * (R - 58), cy + Math.sin(a) * (R - 58) + 8); });
  if (c.rate != null) {
    const a = ang(c.rate);
    x.strokeStyle = "#fff"; x.lineWidth = 10; x.lineCap = "round";
    x.beginPath(); x.moveTo(cx, cy); x.lineTo(cx + Math.cos(a) * (R - 18), cy + Math.sin(a) * (R - 18)); x.stroke();
    x.fillStyle = "#fff"; x.beginPath(); x.arc(cx, cy, 16, 0, Math.PI * 2); x.fill();
  }
  x.fillStyle = "#fff"; x.font = F(800, 92); x.fillText(c.rate != null ? String(c.rate) : "–", cx, cy + 98);
  x.fillStyle = (RATE_ZONES.find(z => Math.abs(c.rate ?? 9999) <= z[0]) || RATE_ZONES[4])[1];
  x.font = F(700, 30); x.fillText(`FPM  ·  ${rateVerdict(c.rate)}`, cx, cy + 142);
  // stats column
  x.textAlign = "left";
  const stats = [["LANDING LOAD", c.g != null ? `${Number(c.g).toFixed(2)} G` : "–"],
    ["TOUCHDOWN", la.touchdown_ft != null ? `${fmt(la.touchdown_ft)} ft` : "–"],
    ["CENTERLINE", la.centerline_ft != null ? sideText(la.centerline_ft).replace(" right", " R").replace(" left", " L") : "–"],
    ["FLOAT", la.float_s != null ? `${la.float_s} s` : "–"]];
  stats.forEach(([l, v], i) => {
    const y = 820 + i * 92;
    x.fillStyle = "rgba(255,255,255,.55)"; x.font = F(600, 24); x.fillText(l, 600, y);
    x.fillStyle = "#fff"; x.font = F(700, 46); x.fillText(v, 600, y + 50);
  });
  // grade
  x.fillStyle = "#C80000"; x.fillRect(W - 52 - 150, 792, 150, 150);
  x.fillStyle = "#fff"; x.textAlign = "center"; x.font = F(800, 120); x.fillText(c.grade || "–", W - 52 - 75, 910);
  x.font = F(600, 24); x.fillText(c.score != null ? `${c.score} / 100` : "", W - 52 - 75, 978);
  // footer
  x.fillStyle = "#0b0c0e"; x.fillRect(0, H - 170, W, 170);
  let fx = 52;
  if (patch) { const ph = 130, pw = ph * patch.width / patch.height; x.drawImage(patch, fx, H - 150, pw, ph); fx += pw + 26; }
  x.textAlign = "left"; x.fillStyle = "#fff"; x.font = F(700, 40); x.fillText(c.pilot || "", fx, H - 92);
  x.fillStyle = "rgba(255,255,255,.6)"; x.font = F(500, 28); x.fillText(c.rank || "", fx, H - 52);
  x.textAlign = "right"; x.fillStyle = "rgba(255,255,255,.45)"; x.font = F(700, 24); x.fillText(pc ? `FLOWN FOR ${pc.partner.name.toUpperCase()}` : "PAGANI AIR CARGO", W - 52, H - 88);
  x.font = F(500, 22);
  const windLine = la.wind ? (la.wind.cross_kt != null ? `Wind ${la.wind.text.replace(" at ", "/")} · XW ${la.wind.cross_kt} kt ${la.wind.cross_from === "left" ? "L" : "R"}` : `Wind ${la.wind.text}`) : "";
  x.fillText([la.stable === true ? "Stable approach" : la.stable === false ? "Unstable approach" : "", windLine].filter(Boolean).join("  ·  "), W - 52, H - 54);
  x.textAlign = "left";
}

function runwayDiagram(la) {
  if (la?.touchdown_ft == null || !la.runway_length_ft) return "";
  const L = la.runway_length_ft, Wd = la.runway_width_ft || 150;
  const VW = 1000, VH = 200, pad = 20, rx0 = pad, rx1 = VW - pad, ry = 62, rh = 80;
  const X = ft => rx0 + Math.max(0, Math.min(L, ft)) / L * (rx1 - rx0);
  const Y = off => ry + rh / 2 + Math.max(-1, Math.min(1, off / (Wd / 2))) * (rh / 2 - 4);
  const tdx = X(la.touchdown_ft), tdy = Y(la.centerline_ft || 0);
  const bars = [0, 500, 1000, 1500, 2000, 2500, 3000].filter(f => f < L);
  return `<div class="rwy-strip"><svg viewBox="0 0 ${VW} ${VH}" role="img" aria-label="Touchdown point on runway ${esc(la.runway)}">
    <rect x="${rx0}" y="${ry}" width="${rx1 - rx0}" height="${rh}" fill="#3a3d43" rx="3"/>
    ${Array.from({ length: 10 }, (_, i) => `<rect x="${rx0 + 6}" y="${ry + 6 + i * 5}" width="10" height="3" fill="#e9e9e9"/>`).join("")}
    <line x1="${rx0 + 40}" y1="${ry + rh / 2}" x2="${rx1 - 10}" y2="${ry + rh / 2}" stroke="#e9e9e9" stroke-width="2" stroke-dasharray="18 14"/>
    ${bars.slice(1).map(f => `<rect x="${X(f) - 6}" y="${ry + 8}" width="12" height="${f === 1000 ? 16 : 8}" fill="#e9e9e9" opacity="${f === 1000 ? 1 : .7}"/><rect x="${X(f) - 6}" y="${ry + rh - 8 - (f === 1000 ? 16 : 8)}" width="12" height="${f === 1000 ? 16 : 8}" fill="#e9e9e9" opacity="${f === 1000 ? 1 : .7}"/>`).join("")}
    <text x="${rx0 + 26}" y="${ry + rh / 2 + 7}" fill="#fff" font-size="26" font-weight="700" font-family="Saira, sans-serif">${esc(la.runway)}</text>
    <circle cx="${tdx}" cy="${tdy}" r="13" fill="#FF3B3B" stroke="#fff" stroke-width="3"/>
    <line x1="${tdx}" y1="${ry - 6}" x2="${tdx}" y2="${ry - 22}" stroke="#FF3B3B" stroke-width="3"/>
    <text x="${tdx}" y="${ry - 28}" fill="#fff" font-size="28" text-anchor="middle" font-family="Saira, sans-serif">Touchdown ${fmt(la.touchdown_ft)} ft</text>
    ${la.rollout_ft ? `<line x1="${tdx}" y1="${ry + rh + 14}" x2="${X(la.touchdown_ft + la.rollout_ft)}" y2="${ry + rh + 14}" stroke="#FFC845" stroke-width="3"/><text x="${X(la.touchdown_ft + la.rollout_ft)}" y="${ry + rh + 44}" fill="#FFC845" font-size="26" text-anchor="end" font-family="Saira, sans-serif">Slowed to 40 kt in ${fmt(la.rollout_ft)} ft</text>` : ""}
    <text x="${rx1}" y="${ry - 12}" fill="#8E96A3" font-size="22" text-anchor="end" font-family="Saira, sans-serif">${fmt(L)} × ${fmt(Wd)} ft</text>
  </svg></div>`;
}

function svgChart({ series, xDomain, left, right, xLabel = v => v, marks = [], bands = [], height = 230 }) {
  const W = 1000, H = height, m = { l: 58, r: right ? 58 : 16, t: 18, b: 30 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const X = v => m.l + (v - xDomain[0]) / ((xDomain[1] - xDomain[0]) || 1) * iw;
  const Yf = d => v => m.t + ih - (v - d[0]) / ((d[1] - d[0]) || 1) * ih;
  const YL = Yf(left.domain), YR = right ? Yf(right.domain) : null;
  const ticks = (d, n = 4) => Array.from({ length: n + 1 }, (_, i) => d[0] + (d[1] - d[0]) * i / n);
  let out = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img">`;
  bands.forEach((b, i) => { const x0 = X(Math.max(b.x0, xDomain[0])), x1 = X(Math.min(b.x1, xDomain[1])); if (x1 > x0) out += `<rect x="${x0}" y="${m.t}" width="${x1 - x0}" height="${ih}" fill="${i % 2 ? "#f6f7f9" : "#ffffff"}"/>${x1 - x0 > 60 ? `<text x="${x0 + 5}" y="${m.t + 13}" font-size="11" fill="#8E96A3">${esc(b.label)}</text>` : ""}`; });
  ticks(left.domain).forEach(v => { out += `<line x1="${m.l}" x2="${W - m.r}" y1="${YL(v)}" y2="${YL(v)}" stroke="#E6E8EC"/><text x="${m.l - 8}" y="${YL(v) + 4}" font-size="12" text-anchor="end" fill="#5E6470">${left.fmt(v)}</text>`; });
  if (right) ticks(right.domain).forEach(v => { out += `<text x="${W - m.r + 8}" y="${YR(v) + 4}" font-size="12" fill="#5E6470">${right.fmt(v)}</text>`; });
  ticks(xDomain, 6).forEach(v => { out += `<text x="${X(v)}" y="${H - 8}" font-size="12" text-anchor="middle" fill="#5E6470">${xLabel(v)}</text>`; });
  series.forEach(se => {
    const Y = se.axis === "r" ? YR : YL;
    const pts = se.pts.filter(p => p[1] != null).map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`);
    if (!pts.length) return;
    if (se.fill) out += `<polygon points="${X(se.pts[0][0])},${m.t + ih} ${pts.join(" ")} ${X(se.pts[se.pts.length - 1][0])},${m.t + ih}" fill="${se.fill}"/>`;
    out += `<polyline points="${pts.join(" ")}" fill="none" stroke="${se.color}" stroke-width="${se.width || 2}" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`;
  });
  marks.forEach(mk => { out += `<line x1="${X(mk.x)}" x2="${X(mk.x)}" y1="${m.t}" y2="${m.t + ih}" stroke="${mk.color || "#1E2126"}" stroke-dasharray="4 4"/><text x="${X(mk.x) + 5}" y="${m.t + ih - 6}" font-size="12" fill="${mk.color || "#1E2126"}">${esc(mk.label)}</text>`; });
  return out + `</svg>`;
}
const niceMax = v => { const p = Math.pow(10, Math.floor(Math.log10(Math.max(1, v)))); return Math.ceil(v / p) * p; };

function profileChart(profile, timeline, startT) {
  if (!profile || profile.length < 3) return "";
  const tmax = profile[profile.length - 1][0] / 60;
  const altMax = niceMax(Math.max(...profile.map(p => p[3])) * 1.08), iasMax = niceMax(Math.max(...profile.map(p => Math.max(p[5], p[6]))) * 1.08);
  const names = { PREFLIGHT: "Pre", PUSHBACK: "Push", TAXI_OUT: "Taxi", TAKEOFF: "T/O", INITIAL_CLIMB: "", CLIMB: "Climb", CRUISE: "Cruise", DESCENT: "Descent", APPROACH: "App", GO_AROUND: "GA", LANDING: "", TAXI_IN: "Taxi", ARRIVED: "" };
  const tl = (timeline || []).map(t => ({ phase: t.phase, x: (t.t - startT) / 60 }));
  const bands = tl.map((t, i) => ({ x0: t.x, x1: tl[i + 1]?.x ?? tmax, label: names[t.phase] ?? "" }));
  return `<div class="chart-box"><h3>Flight profile</h3><div class="legend"><span><i style="background:#C80000"></i>Altitude</span><span><i style="background:#1E2126"></i>Indicated airspeed</span><span><i style="background:#2b7fd6"></i>Ground speed</span></div>
    ${svgChart({ xDomain: [0, tmax], xLabel: v => `${Math.round(v)}m`, left: { domain: [0, altMax], fmt: v => v >= 1000 ? `${Math.round(v / 1000)}k` : Math.round(v) }, right: { domain: [0, iasMax], fmt: v => `${Math.round(v)}` }, bands,
      series: [{ pts: profile.map(p => [p[0] / 60, p[3]]), color: "#C80000", fill: "rgba(200,0,0,.12)", width: 2.5 },
               { pts: profile.map(p => [p[0] / 60, p[5]]), color: "#1E2126", axis: "r" }, { pts: profile.map(p => [p[0] / 60, p[6]]), color: "#2b7fd6", axis: "r", width: 1.5 }] })}</div>`;
}
/* Approach profile: the final approach against the ideal 3-degree glidepath, by distance to the threshold */
async function loadGlideChart(id) {
  const el = $("#glideChart"); if (!el) return;
  let r;
  try { r = await api(`/api/pireps/${id}/approach`); } catch (e) { return; }
  if ($("#glideChart") !== el || !r.approach) return;
  el.innerHTML = glideChartHtml(r.approach);
}
function glideChartHtml(a) {
  const pts = a.points, W = 760, H = 290, L = 54, R = 16, T = 14, B = 34;
  const maxNm = Math.min(12, Math.max(4, Math.ceil(a.max_nm)));
  const tan = d => Math.tan(d * Math.PI / 180), FT_NM = 6076.12;
  const ideal = nm => Math.max(0, nm * FT_NM * tan(a.glide_deg) + a.tch_ft);
  const pathAt = (nm, deg) => Math.max(0, nm * FT_NM * tan(deg) + a.tch_ft);
  const topFt = Math.max(1000, Math.ceil(Math.max(ideal(maxNm), ...pts.map(p => p.agl)) / 500) * 500);
  const x = nm => L + (W - L - R) * (1 - nm / maxNm), y = ft => T + (H - T - B) * (1 - ft / topFt);
  const line = arr => arr.map(([n, f], i) => `${i ? "L" : "M"}${x(n).toFixed(1)},${y(f).toFixed(1)}`).join("");
  const steps = Array.from({ length: maxNm * 4 + 1 }, (_, i) => i / 4);
  const band = line(steps.map(n => [n, pathAt(n, a.glide_deg + a.dot_deg)])) + steps.slice().reverse().map(n => `L${x(n).toFixed(1)},${y(pathAt(n, a.glide_deg - a.dot_deg)).toFixed(1)}`).join("") + "Z";
  const grid = [...Array(maxNm + 1).keys()].map(n => `<line x1="${x(n)}" x2="${x(n)}" y1="${T}" y2="${H - B}" class="gc-grid"/><text x="${x(n)}" y="${H - B + 16}" class="gc-tick" text-anchor="middle">${n}</text>`).join("")
    + Array.from({ length: topFt / 500 + 1 }, (_, i) => i * 500).map(f => `<line x1="${L}" x2="${W - R}" y1="${y(f)}" y2="${y(f)}" class="gc-grid"/><text x="${L - 6}" y="${y(f) + 4}" class="gc-tick" text-anchor="end">${fmt(f)}</text>`).join("");
  const gates = a.gates.map(g => `<circle cx="${x(g.nm)}" cy="${y(g.ft)}" r="4.5" class="gc-gate"/>`).join("");
  const main = `<svg viewBox="0 0 ${W} ${H}" class="glide-svg" role="img" aria-label="Approach profile against a ${a.glide_deg}-degree glidepath">
    ${grid}<path d="${band}" class="gc-band"/><path d="${line(steps.map(n => [n, ideal(n)]))}" class="gc-ideal"/>
    <path d="${line(pts.map(p => [p.nm, p.agl]))}" class="gc-path"/>${gates}
    <rect x="${x(0) - 2}" y="${H - B - 3}" width="4" height="6" class="gc-thr"/>
    <text x="${(L + W - R) / 2}" y="${H - 2}" class="gc-tick" text-anchor="middle">Distance to the runway threshold (nm)</text></svg>`;
  // speed and sink rate over the same distance
  const H2 = 170, T2 = 10, B2 = 26;
  const ias = pts.map(p => p.ias), vsAll = pts.map(p => p.vs).concat(pts.map(p => -p.gs * 101.27 * tan(a.glide_deg)));
  const iLo = Math.floor((Math.min(...ias) - 5) / 10) * 10, iHi = Math.ceil((Math.max(...ias) + 5) / 10) * 10;
  const vLo = Math.min(-1200, Math.floor(Math.min(...vsAll) / 200) * 200), vHi = Math.max(0, Math.ceil(Math.max(...vsAll) / 200) * 200);
  const yI = v => T2 + (H2 - T2 - B2) * (1 - (v - iLo) / Math.max(1, iHi - iLo)), yV = v => T2 + (H2 - T2 - B2) * (1 - (v - vLo) / (vHi - vLo));
  const l2 = (arr, yf) => arr.map(([n, v], i) => `${i ? "L" : "M"}${x(n).toFixed(1)},${yf(v).toFixed(1)}`).join("");
  const sub = `<svg viewBox="0 0 ${W} ${H2}" class="glide-svg" role="img" aria-label="Speed and sink rate on final">
    ${[...Array(maxNm + 1).keys()].map(n => `<line x1="${x(n)}" x2="${x(n)}" y1="${T2}" y2="${H2 - B2}" class="gc-grid"/><text x="${x(n)}" y="${H2 - B2 + 15}" class="gc-tick" text-anchor="middle">${n}</text>`).join("")}
    <text x="${L - 6}" y="${yI(iHi) + 4}" class="gc-tick" text-anchor="end">${iHi} kt</text><text x="${L - 6}" y="${yI(iLo) + 4}" class="gc-tick" text-anchor="end">${iLo} kt</text>
    <text x="${W - R}" y="${yV(vLo) - 4}" class="gc-tick" text-anchor="end">${fmt(vLo)} fpm</text>
    <line x1="${L}" x2="${W - R}" y1="${yV(0)}" y2="${yV(0)}" class="gc-grid" style="stroke-dasharray:2 3"/><text x="${W - R}" y="${yV(0) - 4}" class="gc-tick" text-anchor="end">0 fpm</text>
    <path d="${l2(pts.map(p => [p.nm, -p.gs * 101.27 * tan(a.glide_deg)]), yV)}" class="gc-ideal"/>
    <path d="${l2(pts.map(p => [p.nm, p.vs]), yV)}" class="gc-vs"/><path d="${l2(pts.map(p => [p.nm, p.ias]), yI)}" class="gc-ias"/></svg>`;
  // stabilized-approach practice: within one dot is acceptable
  const verdict = d => { const a = Math.abs(d), w = d > 0 ? "high" : "low";
    return a < 0.5 ? "On slope" : a <= 1 ? `Slightly ${w}` : a <= 2 ? w[0].toUpperCase() + w.slice(1) : `Well ${w}`; };
  const cls = d => Math.abs(d) <= 1 ? "ok" : Math.abs(d) <= 2 ? "warn" : "bad";
  const table = a.gates.length ? `<table class="gate-table"><thead><tr><th>Gate</th><th>Distance</th><th>Glidepath</th><th>Speed</th><th>Sink rate</th></tr></thead><tbody>
    ${a.gates.map(g => `<tr><td><b>${fmt(g.ft)} ft</b></td><td>${g.nm.toFixed(1)} nm</td><td class="${cls(g.dots)}">${verdict(g.dots)} <span class="muted">(${g.dev_ft > 0 ? "+" : ""}${g.dev_ft} ft, ${g.dots > 0 ? "+" : ""}${g.dots} dots)</span></td>
      <td>${g.ias} kt</td><td class="${g.vs < -1100 ? "bad" : g.vs < -900 ? "warn" : ""}">${fmt(g.vs)} fpm</td></tr>`).join("")}</tbody></table>` : "";
  return `<div class="chart-box glide-box"><h3>Approach profile${a.runway ? ` · runway ${esc(a.runway)}` : ""}</h3>
    <div class="legend"><span><i style="background:#C80000"></i>Your path</span><span><i class="dash"></i>Ideal ${a.glide_deg}° glidepath</span><span><i style="background:rgba(30,33,38,.12)"></i>Within one dot</span></div>
    ${main}
    <div class="legend"><span><i style="background:#2b5fb4"></i>Indicated airspeed</span><span><i style="background:#1E2126"></i>Sink rate</span><span><i class="dash"></i>Sink rate a ${a.glide_deg}° path needs at your groundspeed</span></div>
    ${sub}${table}</div>`;
}
function approachChart(la) {
  if (!la?.series || la.series.length < 5) return "";
  const pts = la.series.filter(p => p[0] >= -120 && p[0] <= 20);
  if (pts.length < 5) return "";
  const aglMax = niceMax(Math.max(...pts.map(p => p[1]), 100) * 1.05);
  const vsMin = Math.min(-1200, Math.floor(Math.min(...pts.map(p => p[2])) / 200) * 200);
  return `<div class="chart-box"><h3>Final approach and touchdown</h3><div class="legend"><span><i style="background:#C80000"></i>Height above ground (ft, left)</span><span><i style="background:#1E2126"></i>Vertical speed (fpm, right)</span></div>
    ${svgChart({ xDomain: [pts[0][0], pts[pts.length - 1][0]], xLabel: v => `${Math.round(v)}s`, left: { domain: [0, aglMax], fmt: v => Math.round(v) }, right: { domain: [vsMin, 200], fmt: v => Math.round(v) },
      marks: [{ x: 0, label: "Touchdown", color: "#C80000" }],
      series: [{ pts: pts.map(p => [p[0], p[1]]), color: "#C80000", fill: "rgba(200,0,0,.10)", width: 2.5 }, { pts: pts.map(p => [p[0], p[2]]), color: "#1E2126", axis: "r" }] })}</div>`;
}
function landingFacts(la, rate, g) {
  const a = la?.approach || {};
  const cells = [
    ["Touchdown", rate != null ? `${rate} fpm` : "–", rateVerdict(rate).toLowerCase().replace(/^./, c => c.toUpperCase())],
    ["Landing load", g != null ? `${Number(g).toFixed(2)} G` : "–", ""],
    ["Runway", la?.runway ? `${la.airport} ${la.runway}` : "–", la?.runway_length_ft ? `${fmt(la.runway_length_ft)} ft long` : ""],
    ["Touchdown point", la?.touchdown_ft != null ? `${fmt(la.touchdown_ft)} ft` : "–", la?.touchdown_ft != null ? "past the threshold" : ""],
    ["Centerline", la?.centerline_ft != null ? sideText(la.centerline_ft) : "–", ""],
    ["Float", la?.float_s != null ? `${la.float_s} s` : "–", "from 50 ft to touchdown"],
    ["Approach", la?.stable === true ? "Stable" : la?.stable === false ? "Unstable" : "–", [la?.stability_note && la.stable === false ? la.stability_note : a.ias_min != null ? `${a.ias_min}–${a.ias_max} kt below 1,000 ft` : "", a.vs_500 != null ? `${a.vs_500} fpm at 500 ft` : ""].filter(Boolean).join(" · ")],
    ["Wind", la?.wind ? la.wind.text : "–", la?.wind ? (la.wind.cross_kt != null ? `${la.wind.cross_kt} kt crosswind from the ${la.wind.cross_from}${la.wind.gust_cross_kt ? ` (${la.wind.gust_cross_kt} in gusts)` : ""} · ${la.wind.head_kt >= 0 ? la.wind.head_kt + " kt headwind" : Math.abs(la.wind.head_kt) + " kt tailwind"}` : `${la.wind.station} METAR`) : "recorded at touchdown"],
    ["Rollout", la?.rollout_ft ? `${fmt(la.rollout_ft)} ft` : "–", la?.rollout_ft ? "to 40 kt" : ""],
  ];
  return `<div class="la-facts">${cells.map(([l, v, sub]) => `<div><span>${l}</span><b>${esc(v)}</b>${sub ? `<small>${esc(sub)}</small>` : ""}</div>`).join("")}</div>`;
}
function landingSection(id, c) {
  return `<div class="landing-wrap"><div class="landing-card"><canvas id="${id}" width="1080" height="1350" aria-label="Landing card for ${esc(c.flight)}"></canvas>
      <div class="row"><button class="btn small" type="button" data-dl-card="${id}">Download landing card</button>${S.settings?.discord_enabled ? `<button class="btn ghost small" type="button" data-dc-card="${id}">Post to Discord</button>` : `<span class="muted" style="font-size:13px">PNG, ready for Discord</span>`}</div></div>
    <div>${landingFacts(c.la, c.rate, c.g)}${runwayDiagram(c.la)}${c.la ? "" : `<p class="muted" style="font-size:13px;margin:10px 0 0">Runway and approach details are recorded for flights flown with this version of ACARS onwards.</p>`}</div></div>`;
}
function bindCard(id, c) {
  const cv = document.getElementById(id); if (!cv) return;
  drawLandingCard(cv, c);
  document.querySelector(`[data-dl-card="${id}"]`).onclick = () => cv.toBlob(b => {
    const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = `${c.flight}-${c.dep}-${c.arr}-landing.png`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }, "image/png");
}
function cardData(src) {
  return { flight: src.flight_number, dep: src.dep, arr: src.arr, aircraft: src.aircraft, airframe: src.airframe || src.registration, rate: src.landing_rate, g: src.landing_g,
    grade: src.grade, score: src.score, la: src.landing_analysis, ta: src.takeoff_analysis, rank: src.pilot_rank || S.career?.rank,
    // the pilot who flew it and the simulator they flew it in (a logbook entry knows both; a flight just filed is the viewer's own)
    pilot: src.pilot_name ? [RANK_ABBR[src.pilot_rank] || "", src.pilot_name].filter(Boolean).join(" ") : displayName(S.profile || {}),
    sim: src.source && src.source !== "Demo" ? src.source : "",
    date: new Date((src.filed_at || Date.now() / 1000) * 1000).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" }) };
}

let replayTimer = null;
function setupReplay(map, profile, fallbackTrack) {
  clearInterval(replayTimer);
  const pts = (profile?.length > 2 ? profile.map(p => ({ t: p[0], lat: p[1], lon: p[2], alt: p[3], ias: p[5], gs: p[6], vs: p[7], hdg: p[8] }))
    : (fallbackTrack || []).map((p, i) => ({ t: i * 30, lat: p[0], lon: p[1], alt: p[2], ias: null, gs: null, vs: null, hdg: 0 })));
  if (pts.length < 2) return;
  const path = unwrap(pts.map(p => [p.lat, p.lon]));
  pts.forEach((p, i) => { p.lat = path[i][0]; p.lon = path[i][1]; });
  L.polyline(path, { color: "#C80000", weight: 2, opacity: .35 }).addTo(map);
  const flown = L.polyline([], { color: "#C80000", weight: 3.5 }).addTo(map);
  const plane = L.marker([pts[0].lat, pts[0].lon], { icon: planeIcon(pts[0].hdg), zIndexOffset: 1000 }).addTo(map);
  const T = pts[pts.length - 1].t, bar = $("#replayRange"), read = $("#replayRead"), btn = $("#replayPlay");
  let cur = T, playing = false;
  const at = t => { let i = pts.findIndex(p => p.t >= t); if (i <= 0) return [pts[Math.max(0, i)], Math.max(0, i)]; const a = pts[i - 1], b = pts[i], f = (t - a.t) / ((b.t - a.t) || 1);
    return [{ lat: a.lat + (b.lat - a.lat) * f, lon: a.lon + (b.lon - a.lon) * f, alt: a.alt + (b.alt - a.alt) * f, ias: b.ias, gs: b.gs, vs: b.vs, hdg: b.hdg }, i]; };
  const draw = () => {
    const [p, i] = at(cur);
    plane.setLatLng([p.lat, p.lon]); const el = plane.getElement()?.querySelector("svg"); if (el) el.style.transform = `rotate(${p.hdg || 0}deg)`;
    flown.setLatLngs([...pts.slice(0, i).map(q => [q.lat, q.lon]), [p.lat, p.lon]]);
    bar.value = String(Math.round(cur / T * 1000));
    read.innerHTML = `<b>${hms(cur)}</b> · ${fmt(p.alt)} ft${p.ias != null ? ` · ${fmt(p.ias)} kt IAS · ${fmt(p.gs)} kt GS · ${p.vs > 0 ? "+" : ""}${fmt(p.vs)} fpm` : ""}`;
  };
  bar.oninput = () => { cur = +bar.value / 1000 * T; draw(); };
  btn.onclick = () => {
    playing = !playing; btn.textContent = playing ? "Pause" : "Play replay";
    if (playing && cur >= T) cur = 0;
    clearInterval(replayTimer);
    if (playing) replayTimer = setInterval(() => { cur = Math.min(T, cur + (+$("#replaySpeed").value) * 0.05); draw(); if (cur >= T) { playing = false; btn.textContent = "Play replay"; clearInterval(replayTimer); } }, 50);
  };
  draw();
}
$("#detailDlg").addEventListener("close", () => clearInterval(replayTimer));

async function openDetail(id) {
  const p = await api("/api/logbook/" + id), d = p.detail;
  if (p.source === "Manual") { manualReportDetail(p); return; }
  p.landing_analysis = d.landing_analysis; p.pilot_rank = d.pilot_rank; p.takeoff_analysis = d.takeoff_analysis;
  const c = cardData(p);
  const startT = d.oooi?.out ? (d.timeline?.[0]?.t ?? d.oooi.out) : 0;
  $("#detailTitle").textContent = `${p.flight_number} · ${p.dep} to ${p.arr}`;
  $("#detailBody").innerHTML = `
    ${S.me?.staff || p.pilot_id===S.me?.id ? `<button type="button" class="btn ghost" onclick="openDeliveryReceipt(${Number(id)})">View delivery receipt →</button>` : ''}
    <div class="kv num">
      <div><span>Mission</span><b>${esc(p.mission_title)}</b></div><div><span>Result</span><b>${esc(p.status)} · ${p.grade} (${p.score})</b></div>
      <div><span>Aircraft</span><b>${esc(S.fleet[p.aircraft]?.name || p.aircraft)}${p.airframe ? " · " + esc(p.airframe) : ""}</b></div><div><span>Simulator</span><b>${esc(p.source)}</b></div>
      <div><span>Out / Off</span><b>${zulu(d.oooi.out)} / ${zulu(d.oooi.off)}</b></div><div><span>On / In</span><b>${zulu(d.oooi.on)} / ${zulu(d.oooi.in)}</b></div>
      <div><span>Block / flight</span><b>${hm(p.block_min)} / ${hm(p.flight_min)}</b></div><div><span>Distance</span><b>${fmt(p.distance_nm)} nm</b></div>
    </div>
    ${pacDebrief(p, d)}
    ${econBox(d.economics)}
    ${integrityNote(d.integrity)}
    ${d.online ? `<div class="muted" style="font-size:14px">${d.online.share >= 0.6 ? `Flown online on ${esc(d.online.network)}${d.online.callsign ? " as " + esc(d.online.callsign) : ""}.` : `Seen on ${esc(d.online.network || "the network")} for ${Math.round((d.online.share || 0) * 100)}% of the flight (60% earns the online bonus).`}</div>` : ""}
    <h3 style="margin:8px 0 0;font-size:18px">Landing</h3>
    ${d.landing ? `<p class="muted" style="font-size:13px;margin:2px 0 0">How the touchdown was measured: ${d.landing.rate_source === "sim_touchdown" ? `the simulator's touchdown rate (${esc(d.landing.touchdown_fpm)} fpm)` : d.landing.rate_source === "first_contact" ? "the first wheel contact (vertical speed)" : "the vertical speed indicator just before contact"}${d.landing.vs_rate_fpm != null ? ` · vertical speed indicator ${esc(d.landing.vs_rate_fpm)} fpm` : ""}${d.landing.contact_gap_s != null ? ` · last sample ${esc(d.landing.contact_gap_s)} s before contact` : ""} · ${esc(p.source || "")}${(() => {
      const ser = (d.landing_analysis?.series || []).filter(x => x[0] >= -6 && x[0] < 0);
      if (!ser.length) return "";
      const at = k => ser.reduce((b, x) => Math.abs(x[0] + k) < Math.abs(b[0] + k) ? x : b);
      return `<br>Before touchdown: ${[5, 3, 2, 1, 0.5].map(k => { const x = at(k); return `${x[0]} s ${x[2]} fpm at ${x[1]} ft`; }).filter((v, i, a) => a.indexOf(v) === i).join(" · ")}`; })()}</p>` : ""}
    ${landingSection("cardDetail", c)}
    <div id="glideChart"></div>
    ${approachChart(d.landing_analysis)}
    ${d.takeoff_analysis ? `<h3 style="margin:8px 0 0;font-size:18px">Takeoff</h3>${takeoffSection("toDetail", c)}${takeoffChart(d.takeoff_analysis)}` : ""}
    ${profileChart(d.profile, d.timeline, startT)}
    <h3 style="margin:8px 0 0;font-size:18px">Screenshots</h3>
    <div id="pirepShots"><span class="muted" style="font-size:13px">Loading…</span></div>
    <h3 style="margin:8px 0 0;font-size:18px">Replay</h3>
    <div style="border:1px solid var(--line)"><div id="detailMap"></div>
      <div class="replay-bar"><button class="btn small" id="replayPlay" type="button">Play replay</button>
        <input type="range" id="replayRange" min="0" max="1000" value="1000" aria-label="Replay position">
        <select id="replaySpeed" aria-label="Replay speed"><option value="30">×30</option><option value="60" selected>×60</option><option value="120">×120</option><option value="300">×300</option></select>
        <span class="replay-read" id="replayRead"></span></div></div>
    
    ${d.bonuses?.length ? `<table class="breakdown"><tbody><tr><td>Base points</td><td>${fmt(d.base_points)}</td></tr>${d.bonuses.map(b => `<tr><td>${esc(b[0])}</td><td class="pos">+${fmt(b[1])}</td></tr>`).join("")}</tbody></table>` : ""}
    ${d.checkride ? `<div class="notice ${d.checkride.passed ? "" : "err"}">Checkride ${d.checkride.passed ? "passed" : "not passed: " + esc(d.checkride.reasons.join(", "))}</div>` : ""}
    <div class="row"><span class="tag ${p.review_status === "Accepted" ? "green" : p.review_status === "Pending" ? "amber" : ""}" style="margin:0">Review: ${esc(p.review_status || "Accepted")}</span>
      ${(JSON.parse(p.flags || "[]")).map(f => `<span class="tag amber" style="margin:0">${esc(f)}</span>`).join("")}${p.review_note ? `<span class="muted" style="font-size:14px">Staff: ${esc(p.review_note)}</span>` : ""}</div>
    ${p.remarks ? `<div><h3>Remarks</h3><p style="margin:0">${esc(p.remarks)}</p></div>` : ""}
    <details><summary>ACARS message log (${d.messages.length})</summary><div class="log" style="background:var(--scope);color:var(--scope-text);max-height:300px;margin-top:8px;padding:10px 14px">
      ${d.messages.map(m => `<div><span class="z">${m.z}</span><span>${esc(m.text)}</span></div>`).join("")}</div></details>
    <div class="row">${p.airframe ? `<button class="btn ghost small" type="button" id="pirepFault">Report a fault on ${esc(p.airframe)}</button>` : ""}${d.dispatch ? `<a class="btn ghost small" href="/dispatch?pirep=${id}" target="_blank" rel="noopener">Dispatch paperwork</a>` : ""}${S.me?.staff ? `<button class="btn ghost small" id="delPirep">Delete this PIREP</button>` : ""}</div>`;
  pacReportNav($("#detailBody"));
  $("#detailDlg").showModal();
  bindCard("cardDetail", c);
  if (d.takeoff_analysis) bindTakeoffCard("toDetail", c);
  loadGlideChart(id);
  const loadPirepShots = async () => {
    const list = await api(`/api/gallery?pirep=${id}`).catch(() => []);
    const el = $("#pirepShots"); if (!el) return;
    el.innerHTML = `<div class="upload-row"><input id="psCap" placeholder="Caption (optional)" style="border:1px solid var(--line);border-radius:3px;padding:7px 10px;min-width:240px">
        <label class="btn small" style="cursor:pointer">Add screenshots<input type="file" id="psFile" accept="image/jpeg,image/png,image/webp" multiple hidden></label></div>
      ${list.length ? shotTiles(list) : `<p class="muted" style="margin:0;font-size:14px">No screenshots for this flight yet.</p>`}`;
    $("#psFile").onchange = async e => { if (await uploadShots(e.target, id, $("#psCap").value)) loadPirepShots(); };
    bindShots(el, list, loadPirepShots);
  };
  loadPirepShots();
  if ($("#pirepFault")) $("#pirepFault").onclick = () => openFaultAfter(p.airframe, id, p.flight_number);
  if ($("#delPirep")) $("#delPirep").onclick = async () => { if (!confirm("Delete this PIREP? It comes off the pilot's logbook and career.")) return; await api("/api/logbook/" + id, { method: "DELETE" }); $("#detailDlg").close(); loadLogbook(); };
  if (detailMap) detailMap.remove();
  if (!HAS_MAP) return;
  const lightStyle = { dark: "light", street: "street", satellite: "satellite", offline: "offline" }[S.settings.map_style] || "light";
  detailMap = makeBaseMap($("#detailMap"), { theme: "light", style: lightStyle }).map;
  const ap = d.ofp ? [d.ofp.origin, d.ofp.destination] : [];
  ap.filter(Boolean).forEach(a => L.circleMarker([a.lat, a.lon], { radius: 5, color: "#fff", weight: 2, fillColor: "#C80000", fillOpacity: 1 })
    .bindTooltip(a.icao, { permanent: true, direction: "top", offset: [0, -5], className: "apt-tip" }).addTo(detailMap));
  const line = L.polyline(unwrap((d.profile?.length > 2 ? d.profile.map(q => [q[1], q[2]]) : d.track.map(t => [t[0], t[1]]))), { opacity: 0 }).addTo(detailMap);
  if (line.getLatLngs().length > 1) detailMap.fitBounds(line.getBounds(), { padding: [24, 24] }); else detailMap.setView([20, 0], 2);
  setupReplay(detailMap, d.profile, d.track);
  setTimeout(() => detailMap.invalidateSize(), 80);
}

/* ================= VA core ================= */
const VIEWS = ["privacy", "roster", "home", "dashboard", "missions", "bids", "acars", "fleet", "stations", "downloads", "career", "stats", "finance", "shop", "live", "logbook", "gallery", "handbook", "cargoguide", "staff", "liverylib", "creative", "commercial", "messages", "profile", "pilots", "updates"];
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
// Virtual airline directories PAC is listed in. Their badges are live images from the directory (the rank updates
// by itself) and link to PAC's listing there. Add another directory by adding a line.
const DIRECTORY_BADGES = [
  { name: "VA-List", img: "https://va-list.com/php/rankimage.php?id=1231", href: "https://va-list.com/pagani-air-cargo-1231" },
];
function directoryBadges() {
  if (!DIRECTORY_BADGES.length) return "";
  return `<div class="dir-badges" id="dirBadges"><span class="muted">Find us on</span>${DIRECTORY_BADGES.map(b =>
    `<a href="${esc(b.href)}" target="_blank" rel="noopener" title="Pagani Air Cargo on ${esc(b.name)}"><img src="${esc(b.img)}" alt="Pagani Air Cargo on ${esc(b.name)}" loading="lazy" referrerpolicy="no-referrer-when-downgrade" onerror="this.closest('a').remove(); if (!document.querySelector('#dirBadges a')) document.querySelector('#dirBadges')?.remove()"></a>`).join("")}</div>`;
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
    desc: "AI air traffic control. PAC links to it through VA-Link, so the flights you fly there log straight back to your PAC logbook." },
  { name: "SimBrief by Navigraph", kind: "Dispatch", url: "https://www.simbrief.com",
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
    <img class="bg" fetchpriority="high" decoding="async" src="/static/illustrations/${S.me ? "ill-briefing-room" : "ill-ramp-night"}.webp?v=20261113" alt=""><span class="ill-tag">Illustration</span>
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
  ${directoryBadges()}
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
  <article class="founder pac-story"><figure class="story-fig"><img src="/static/illustrations/ill-hq-dusk.webp" alt="Illustration of the PAC headquarters and freight terminal at KCVG at dusk, with PAC freighters on the apron" loading="lazy" width="1600" height="900"><span class="ill-tag">Illustration</span></figure>
    <div><blockquote>${esc(site.story)}</blockquote></div></article>

  ${Object.keys(S.partners || {}).length ? `<div class="section-h"><div><div class="kicker">Partners</div><h2>Flying alongside the biggest names in cargo</h2><p>When these operators are short of qualified captains, they hire PAC pilots to fly their aircraft. PAC crews also ride their freighters on partner jumpseat agreements.</p></div><button class="btn ghost small" onclick="S.board='partners';show('missions')">Partner crew requests</button></div>
  <div class="partner-strip">${Object.values(S.partners).map(p => `<img src="${esc(p.logo)}" alt="${esc(p.name)}" title="${esc(p.name)}">`).join("")}</div>
  <p class="muted" style="font-size:12px;margin:6px 0 0">Partnerships are simulated for Pagani Air Cargo, a flight simulation virtual airline. Names and logos are trademarks of their owners and don't imply endorsement.</p>` : ""}

  ${networkPartners(h)}

  <div class="section-h"><div><div class="kicker">Tools &amp; technology</div><h2>What PAC flies with</h2><p>The platforms and add-ons behind every PAC flight. We integrate directly with some of them.</p></div></div>
  <div class="tech-grid">${TECH_PARTNERS.map(p => `<a class="tech-card"${p.url ? ` href="${esc(p.url)}" target="_blank" rel="noopener"` : ""}><span class="tech-kind">${esc(p.kind)}</span><b>${esc(p.name)}</b><span class="tech-desc">${esc(p.desc)}</span></a>`).join("")}</div>
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
  $("#privacyRoot").innerHTML = `<div class="profile-bar"><h1>Privacy policy</h1><span class="muted">Last updated November 3, 2026</span></div>
  <div class="privacy">
    <p class="lead">Pagani Air Cargo (PAC) is a free, non-commercial virtual airline for flight simulator pilots, run by Joseph Pagani. This page explains what information the PAC website and the PAC ACARS app collect, why, who else sees it, and the choices you have. Questions or requests: <a href="mailto:${mail}">${mail}</a>.</p>
    ${sec("What we collect", `<ul>
      <li><b>Your application:</b> name, email address, country, Discord username (optional), simulator, experience, preferred hub and your note to us.</li>
      <li><b>Your PAC account:</b> pilot ID, name, rank, home base, current location in PAC's network, and anything you add to your profile, such as a photo or bio. Your password is stored only as a salted hash: nobody, staff included, can read it.</li>
      <li><b>Your flights:</b> while PAC ACARS tracks a flight it records what your simulator reports (position, altitude, speeds, phase of flight, fuel, weights and landing data), plus your flight plan, dispatch paperwork, messages to PAC dispatch, and the resulting report, score and logbook entry.</li>
      <li><b>Optional details you choose to add:</b> your VATSIM CID or IVAO VID, SimBrief username, SayIntentions.AI key, problem reports with screenshots, and gallery uploads.</li>
      <li><b>Technical records:</b> our web server keeps short logs of requests (IP address, browser and the page asked for) to keep the site secure and running. They're overwritten automatically.</li></ul>`)}
    ${sec("Cookies and storage on your device", `<p>PAC uses <b>one essential cookie</b> to keep you signed in (for up to 30 days if you tick <i>Keep me signed in</i>). The site also saves a few preferences in your browser, such as your theme, design and filters. PAC has <b>no advertising, analytics or tracking cookies</b>, and doesn't follow you around other websites.</p>`)}
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
  bar.innerHTML = `<p><b>Your privacy.</b> PAC uses one essential cookie to keep you signed in and saves your preferences on this device. No advertising or tracking. By continuing, you agree to this and to how we handle your information in our <a href="#privacy" onclick="show('privacy');return false">privacy policy</a>.</p>
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
      <li><b>Tail strikes:</b> ACARS records pitch through the takeoff roll and compares it with each type's tail-strike pitch. A tail strike costs 25 points, grounds the airframe for inspection and goes to review.</li>
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
      <tr><td>Tail strike</td><td>−25</td></tr>
      <tr><td>Diversion declared to dispatch / diverted to the OFP alternate undeclared / parked elsewhere</td><td>−10 / −20 / −40 and failed</td></tr>
      <tr><td>Critical or High priority within 10% of planned block</td><td>+5</td></tr><tr><td>Late: over 25% (urgent) or 35% (standard)</td><td>−10 / −5</td></tr></table>
      <p>Grades: A 90+, B 80+, C 70+, D 60+, F below. Points are the flight's reward scaled by your score, plus any event, featured-route or tour bonus.</p>`],
    ["review", "PIREP review", `<p>Flights scoring ${rv.auto_accept_score} or more with no flags are accepted automatically. Anything flagged goes to staff for review:</p>
      <ul><li>Landing firmer than ${Math.abs(rv.hard_landing_fpm)} fpm or above ${rv.max_landing_g} G</li><li>Diverted or failed flights</li><li>Position jumps or slew in the air</li><li>A tail strike</li><li>More than 10 minutes paused in the air, or more than 10 seconds above 1× sim rate once moving</li><li>More than ${rv.max_bounces} bounce${rv.max_bounces === 1 ? "" : "s"}</li><li>Score below ${rv.auto_accept_score}</li></ul>
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
    <span class="msg-time">${when(m.time)}</span></button>`;
}
async function openMessage(id) {
  let dlg = document.getElementById("msgDlg");
  if (!dlg) { dlg = document.createElement("dialog"); dlg.id = "msgDlg"; dlg.className = "msg-dlg"; document.body.appendChild(dlg); }
  dlg.innerHTML = `<p class="muted" style="padding:24px">Loading…</p>`; if (!dlg.open) dlg.showModal();
  try {
    const m = await api("/api/messages/" + id);
    const meta = m.incoming ? `From ${esc(m.sender_name)} · ${esc(m.sender)}` : `To ${esc(m.recipient_name)} · ${esc(m.recipient)}`;
    dlg.innerHTML = `<article class="msg-read">
      <div class="msg-read-head"><b>${esc(m.subject)}</b><div class="muted">${meta} · ${when(m.time)}</div></div>
      <div class="msg-read-body">${esc(m.body).replace(/\n/g, "<br>")}</div>
      <div class="msg-read-actions">
        ${m.incoming ? `<button class="btn small" type="button" id="msgReply">Reply</button>` : ""}
        <button class="btn ghost small" type="button" id="msgDel">Delete</button>
        <button class="btn ghost small" type="button" onclick="this.closest('dialog').close()">Close</button></div></article>`;
    if (m.incoming) $("#msgReply").onclick = () => { dlg.close(); openCompose(m.sender, "Re: " + m.subject.replace(/^\s*re:\s*/i, "")); };
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

/* ---------------- Livery library (scoped: Livery Manager + full admin) ---------------- */
async function apiForm(path, formData, method = "POST") {
  const res = await fetch(path, { method, body: formData });   // no Content-Type: the browser sets the multipart boundary
  const data = await res.json().catch(() => ({ error: `The ACARS server answered with an error (HTTP ${res.status}).` }));
  if (!res.ok) { const e = new Error(data.error || `Request failed (${res.status})`); e.status = res.status; throw e; }
  return data;
}
async function loadLiveryLib() {
  const root = $("#liveryLibRoot");
  if (!root) return;
  root.innerHTML = `<div class="profile-bar"><h1>Livery library</h1><span class="muted">The PAC paint library across MSFS and X-Plane. Add, update and retire liveries here; pilots get them on the Fleet page.</span></div><p class="muted">Loading liveries…</p>`;
  try {
    const data = await api("/api/fleet/liveries");
    S.liveryMaxMb = data.max_mb || 600;
    renderLiveryLib(root, data.liveries || []);
  } catch (e) {
    root.innerHTML = `<div class="profile-bar"><h1>Livery library</h1></div><div class="notice">${esc(e.message)}</div>`;
  }
}
function renderLiveryLib(root, liveries) {
  const byType = {};
  liveries.forEach(l => (byType[l.type] = byType[l.type] || []).push(l));
  const codes = Object.keys(byType).sort((a, b) => (S.fleet[a]?.name || a).localeCompare(S.fleet[b]?.name || b));
  const card = l => {
    const sub = l.kind === "file"
      ? `${l.size ? (l.size >= 1048576 ? (l.size / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(l.size / 1024)) + " KB") : "file"} · uploaded`
      : `link${l.host ? " · " + esc(l.host) : ""}`;
    return `<article class="liv-card">
      <div class="liv-thumb">${l.preview ? `<img src="${esc(l.preview)}" alt="" loading="lazy">` : `<span class="liv-noimg">No preview</span>`}</div>
      <div class="liv-body">
        <h3>${esc(l.title || "PAC house colors")}</h3>
        <p class="liv-meta"><span class="tag grey">${esc(l.sim || "MSFS")}</span> ${esc(l.painter || "—")}${l.registration ? ` · ${esc(l.registration)}` : ""}</p>
        <p class="muted" style="font-size:12px;margin:2px 0">${sub} · ${fmt(l.downloads || 0)} download${(l.downloads || 0) === 1 ? "" : "s"}</p>
        ${l.notes ? `<p class="liv-notes">${esc(l.notes)}</p>` : ""}
      </div>
      <div class="liv-actions"><button class="btn ghost small" data-liv-edit="${esc(l.id)}">Edit</button><button class="btn ghost small" data-liv-del="${esc(l.id)}">Delete</button></div>
    </article>`;
  };
  root.innerHTML = `<div class="profile-bar"><h1>Livery library</h1><span class="muted">The PAC paint library across MSFS and X-Plane. Pilots get these on the Fleet page.</span></div>
    <div class="row" style="margin:0 0 14px"><button class="btn" type="button" id="livAdd">Add a livery</button><span class="muted" style="font-size:13px;align-self:center">${liveries.length} liver${liveries.length === 1 ? "y" : "ies"} · files up to ${S.liveryMaxMb} MB, or link to flightsim.to</span></div>
    ${codes.length ? codes.map(c => `<section class="liv-sec"><h2>${esc(S.fleet[c]?.name || c)}</h2><div class="liv-grid">${byType[c].map(card).join("")}</div></section>`).join("")
      : `<div class="notice">No liveries yet. Add the first one with the button above.</div>`}`;
  $("#livAdd").onclick = () => openLiveryDialog(null);
  root.querySelectorAll("[data-liv-edit]").forEach(b => b.onclick = () => openLiveryDialog(liveries.find(l => l.id === b.dataset.livEdit)));
  root.querySelectorAll("[data-liv-del]").forEach(b => b.onclick = () => deleteLivery(liveries.find(l => l.id === b.dataset.livDel)));
}
function openLiveryDialog(livery) {
  const edit = !!livery, l = livery || {};
  const types = Object.keys(S.fleet).sort((a, b) => (S.fleet[a].name || a).localeCompare(S.fleet[b].name || b));
  let dlg = $("#liveryDlg");
  if (!dlg) { dlg = document.createElement("dialog"); dlg.id = "liveryDlg"; dlg.className = "liv-dlg"; document.body.appendChild(dlg); }
  dlg.innerHTML = `<form id="liveryForm" method="dialog">
    <h2>${edit ? "Edit livery" : "Add a livery"}</h2>
    <div class="liv-form">
      <div class="field"><label for="liv_type">Aircraft type</label><select id="liv_type" name="type" required>${types.map(t => `<option value="${esc(t)}"${l.type === t ? " selected" : ""}>${esc(S.fleet[t].name || t)}</option>`).join("")}</select></div>
      <div class="field"><label for="liv_sim">Simulator</label><select id="liv_sim" name="sim"><option value="MSFS"${l.sim !== "X-Plane" ? " selected" : ""}>MSFS</option><option value="X-Plane"${l.sim === "X-Plane" ? " selected" : ""}>X-Plane</option></select></div>
      <div class="field"><label for="liv_title">Title</label><input id="liv_title" name="title" maxlength="80" placeholder="PAC house colors" value="${esc(l.title || "")}"></div>
      <div class="field"><label for="liv_painter">Painter <span class="req">*</span></label><input id="liv_painter" name="painter" maxlength="60" required placeholder="Who painted it" value="${esc(l.painter || "")}"></div>
      <div class="field full"><label for="liv_painter_link">Painter link (optional)</label><input id="liv_painter_link" name="painter_link" placeholder="https://flightsim.to/…" value="${esc(l.painter_link || "")}"></div>
      <div class="field"><label for="liv_reg">Registration (optional)</label><input id="liv_reg" name="registration" maxlength="12" placeholder="N738PC" value="${esc(l.registration || "")}"></div>
      <div class="field"><label for="liv_version">Version (optional)</label><input id="liv_version" name="version" maxlength="20" placeholder="1.0" value="${esc(l.version || "")}"></div>
      <div class="field full"><label for="liv_notes">Notes (optional)</label><textarea id="liv_notes" name="notes" maxlength="500" rows="2" placeholder="Anything pilots should know">${esc(l.notes || "")}</textarea></div>
      <div class="field full"><label for="liv_file">Livery file (.zip, .7z, .rar${edit ? ", leave empty to keep" : ""})</label><input id="liv_file" name="file" type="file" accept=".zip,.7z,.rar"></div>
      <div class="field full"><label for="liv_url">…or a link to where it's hosted</label><input id="liv_url" name="url" placeholder="https://flightsim.to/…" value="${esc(l.url || "")}"></div>
      <div class="field full"><label for="liv_preview">Preview image (optional, PNG/JPEG/WebP)</label><input id="liv_preview" name="preview" type="file" accept="image/png,image/jpeg,image/webp">${edit && l.preview ? `<label class="liv-rmv"><input type="checkbox" name="remove_preview"> Remove the current preview</label>` : ""}</div>
    </div>
    <p class="liv-err notice" id="liveryErr" hidden></p>
    <div class="row liv-dlg-foot"><button class="btn" type="submit" id="livSave">${edit ? "Save changes" : "Add livery"}</button><button class="btn ghost" type="button" id="livCancel">Cancel</button></div>
  </form>`;
  $("#livCancel").onclick = () => dlg.close();
  $("#liveryForm").onsubmit = async e => {
    e.preventDefault();
    const btn = $("#livSave"), err = $("#liveryErr");
    err.hidden = true; btn.disabled = true;
    try {
      const form = e.target, fd = new FormData();
      ["type", "sim", "title", "painter", "painter_link", "registration", "version", "notes", "url"].forEach(k => fd.append(k, (form.elements[k]?.value || "").trim()));
      const file = form.elements.file?.files?.[0]; if (file) fd.append("file", file);
      const pv = form.elements.preview?.files?.[0]; if (pv) fd.append("preview", pv);
      if (edit && form.elements.remove_preview?.checked) fd.append("remove_preview", "1");
      await apiForm(edit ? "/api/staff/liveries/" + encodeURIComponent(l.id) : "/api/staff/liveries", fd, "POST");
      dlg.close();
      toast(edit ? "Livery updated." : "Livery added.");
      loadLiveryLib();
    } catch (ex) { err.textContent = ex.message; err.hidden = false; } finally { btn.disabled = false; }
  };
  dlg.showModal();
}
async function deleteLivery(l) {
  if (!l) return;
  if (!confirm(`Delete the ${S.fleet[l.type]?.name || l.type} livery "${l.title || "PAC house colors"}"? This removes it from the Fleet page and deletes its file.`)) return;
  try { await apiForm("/api/staff/liveries/" + encodeURIComponent(l.id), new FormData(), "DELETE"); toast("Livery deleted."); loadLiveryLib(); }
  catch (e) { toast(e.message); }
}
/* ---------------- Media & comms (scoped: Creative / Media + full admin) ---------------- */
async function loadCreative() {
  const root = $("#creativeRoot");
  if (!root) return;
  S.creativeTab = S.creativeTab || "photos";
  const tabs = [["photos", "Promo photos"], ["news", "Announcements & NOTAMs"]];
  root.innerHTML = `<div class="profile-bar"><h1>Media &amp; comms</h1><span class="muted">Promo photos on partner mission cards, plus site announcements and company NOTAMs (also posted to Discord).</span></div>
    <div class="msg-tabs" style="margin-bottom:16px">${tabs.map(([k, t]) => `<button class="${S.creativeTab === k ? "on" : ""}" data-ctab="${k}">${t}</button>`).join("")}</div>
    <div id="creativeBody"></div>`;
  root.querySelectorAll("[data-ctab]").forEach(b => b.onclick = () => { S.creativeTab = b.dataset.ctab; loadCreative(); });
  const body = $("#creativeBody");
  if (S.creativeTab === "news") staffNews(undefined, body); else staffPartnerPhotos(body);
}
async function loadStaff() {
  try { S.staff = await api("/api/staff/overview"); renderStaff(); } catch (e) { toast(e.message); }
}
function renderStaff() {
  const d = S.staff;
  const pendingReviews = d.reviews.filter(r => r.review_status === "Pending").length;
  const pendingApps = d.applications.filter(a => a.status === "Pending").length;
  const tabs = [["ceo", "CEO desk", 0], ["market", "Fleet market", 0], ["complaints", "Complaints", 0], ["roles", "Roles", 0], ["reports", "Problem reports", 0], ["health", "Operations health", 0], ["campaigns", "Cargo campaigns", 0], ["relief", "Relief missions", 0], ["cargostock", "Cargo stock", 0], ["reviews", "PIREP review", pendingReviews], ["applications", "Applications", pendingApps], ["transfers", "Transfer hours", d.transfer_pending || 0], ["activity", "Activity", d.activity_overdue || 0], ["engagement", "Engagement", d.engagement_pending || 0], ["roster", "Roster", 0],
    ["news", "News", 0], ["mx", "Maintenance", d.airframes.reduce((n, a) => n + (a.open_items || []).length, 0)], ["types", "Fleet types", 0], ["pphotos", "Partner photos", 0], ["airframes", "Airframes", d.airframes.filter(a => ["Maintenance", "Inspection", "A-check due", "Heavy check due", "Heavy check", "Damaged"].includes(a.status)).length], ["events", "Events", 0], ["site", "Site and rules", 0]];
  const GROUPS = [["Company", ["ceo", "market", "complaints", "roles"]], ["Pilots", ["reviews", "applications", "transfers", "activity", "engagement", "roster"]],
    ["Operations", ["reports", "health", "events", "news"]], ["Cargo", ["campaigns", "relief", "cargostock"]], ["Fleet", ["airframes", "mx", "types", "pphotos"]], ["Settings", ["site"]]];
  const T = Object.fromEntries(tabs.map(t => [t[0], t]));
  if (!T[S.staffTab]) S.staffTab = "reviews";
  const groupOf = k => (GROUPS.find(([, ks]) => ks.includes(k)) || GROUPS[0])[0];
  const cur = groupOf(S.staffTab);
  const gCount = ks => ks.reduce((n, k) => n + (T[k]?.[2] || 0), 0);
  $("#staffRoot").innerHTML = `<div class="profile-bar"><h1>Staff</h1><span class="muted">Running the airline. Only staff accounts can see this area.</span></div>
    <div class="staff-groups" role="tablist">${GROUPS.map(([g, ks]) => `<button role="tab" data-sg="${g}" aria-selected="${g === cur}">${g}${gCount(ks) ? `<span class="count">${gCount(ks)}</span>` : ""}</button>`).join("")}</div>
    <div class="staff-tabs" role="tablist">${GROUPS.find(([g]) => g === cur)[1].map(k => T[k]).filter(Boolean).map(([k, t, n]) => `<button role="tab" data-st="${k}" aria-selected="${S.staffTab === k}">${t}${n ? `<span class="count">${n}</span>` : ""}</button>`).join("")}</div>
    <div id="staffBody"></div>`;
  document.querySelectorAll("[data-sg]").forEach(b => b.onclick = () => { const ks = GROUPS.find(([g]) => g === b.dataset.sg)[1]; S.staffTab = ks.find(k => T[k]?.[2]) || ks[0]; renderStaff(); });
  document.querySelectorAll("[data-st]").forEach(b => b.onclick = () => { S.staffTab = b.dataset.st; renderStaff(); });
  ({ ceo: staffCeo, market: staffMarket, complaints: staffComplaints, roles: staffRoles, reports: staffProblemReports, health: staffOperationsHealth, campaigns: staffCargoCampaigns, relief: staffRelief, cargostock: staffCargoStock, reviews: staffReviews, applications: staffApps, transfers: staffTransfers, activity: staffActivity, engagement: staffEngagement, roster: staffRoster, news: staffNews, mx: staffMx, types: staffTypes, pphotos: staffPartnerPhotos, airframes: staffAirframes, events: staffEvents, site: staffSite })[S.staffTab]();
}
/* Staff › Engagement: new pilots who never flew and lapsed pilots, with a one-click reminder */
async function staffEngagement() {
  const body = $("#staffBody");
  body.innerHTML = `<p class="muted">Loading engagement…</p>`;
  let d;
  try { d = await api("/api/staff/engagement/roster"); } catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const day = t => t ? new Date(t * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "–";
  const reach = p => `${p.has_email ? '<span class="tag green" title="Has email">✉</span>' : '<span class="tag" title="No email on file">no email</span>'} ${p.linked_discord ? '<span class="tag green" title="Linked Discord">Discord</span>' : ''}`;
  const nudged = p => p.opted_out ? '<span class="tag dark">Opted out</span>' : p.nudges_sent ? `${p.nudges_sent} sent` : '<span class="muted">none yet</span>';
  const btn = p => p.has_email && !p.opted_out ? `<button class="btn ghost small" data-nudge="${esc(p.pilot_id)}">Send reminder</button>` : `<span class="muted">–</span>`;
  body.innerHTML = `
    <p class="muted" style="max-width:85ch">New pilots who haven't flown their first flight, and pilots who've gone quiet. PAC emails them automatically — never-flown at <b>3, 7 and 14 days</b> after joining, lapsed at <b>30 and 60 days</b> since their last flight — plus a Discord DM for linked pilots. Each nudge sends once and stops; the monthly report takes over after. Use <b>Send reminder</b> to nudge someone now. Pilots on leave are left alone.</p>
    <div class="notice" style="margin:0 0 12px"><b>Test it on yourself.</b> Send a sample reminder to any inbox — it records nothing and doesn't touch any pilot. Leave the address blank to use your profile email.
      <span class="row" style="gap:8px;margin-top:6px;align-items:center;flex-wrap:wrap">
        <select id="engTestTag" aria-label="Reminder type"><option value="new3">First-flight · day 3</option><option value="new7">First-flight · day 7</option><option value="new14">First-flight · day 14</option><option value="lapse30">Lapsed · 30 days</option><option value="lapse60">Lapsed · 60 days</option></select>
        <input id="engTestTo" type="email" placeholder="send to… (optional)" style="min-width:220px" autocomplete="email">
        <button class="btn ghost small" id="engTestSend" type="button">Send test</button></span></div>
    <div class="row" style="gap:18px;margin:8px 0 14px">
      <span><span class="tag green">Active</span> ${d.active_count}</span>
      <span><span class="tag amber">Never flown</span> ${d.never_count}</span>
      <span><span class="tag">Lapsed</span> ${d.lapsed_count}</span>
      ${d.hq_idle_count ? `<span><span class="tag amber">At ${esc(d.hq || "HQ")}, not flying</span> ${d.hq_idle_count}</span>` : ""}</div>
    <h3 style="margin:14px 0 6px">Never flown <span class="muted">(${d.never_count})</span></h3>
    <div class="aar-wrap"><table class="aar-table"><thead><tr><th>Pilot</th><th>Joined</th><th>Reach</th><th>Reminders</th><th></th></tr></thead>
      <tbody>${d.never.map(p => `<tr><td><b class="mono">${esc(p.pilot_id)}</b> ${esc(p.name || "")}${p.at_hq ? ' <span class="tag amber" title="Sitting at HQ without flying">At HQ</span>' : ""}</td>
        <td>${day(p.joined)} <small class="muted">${p.age_days}d ago</small></td><td>${reach(p)}</td><td>${nudged(p)}</td><td>${btn(p)}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">Nobody — every pilot has flown. 🎉</td></tr>`}</tbody></table></div>
    <h3 style="margin:18px 0 6px">Lapsed <span class="muted">(${d.lapsed_count})</span></h3>
    <div class="aar-wrap"><table class="aar-table"><thead><tr><th>Pilot</th><th>Last flight</th><th>Reach</th><th>Reminders</th><th></th></tr></thead>
      <tbody>${d.lapsed.map(p => `<tr><td><b class="mono">${esc(p.pilot_id)}</b> ${esc(p.name || "")}${p.at_hq ? ' <span class="tag amber" title="Sitting at HQ without flying">At HQ</span>' : ""}</td>
        <td>${day(p.last_flight)} <small class="muted">${p.idle_days}d ago</small></td><td>${reach(p)}</td><td>${nudged(p)}</td><td>${btn(p)}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">Nobody lapsed right now.</td></tr>`}</tbody></table></div>`;
  body.querySelectorAll("[data-nudge]").forEach(b => b.onclick = async () => {
    b.disabled = true; const was = b.textContent; b.textContent = "Sending…";
    try { const r = await api("/api/staff/engagement/nudge", { method: "POST", body: { pilot: b.dataset.nudge } }); toast(r.message || "Reminder sent."); staffEngagement(); }
    catch (e) { toast(e.message); b.disabled = false; b.textContent = was; }
  });
  const tb = body.querySelector("#engTestSend");
  if (tb) tb.onclick = async () => {
    const tag = body.querySelector("#engTestTag").value, to = body.querySelector("#engTestTo").value.trim(), w = tb.textContent;
    tb.disabled = true; tb.textContent = "Sending…";
    try { const r = await api("/api/staff/engagement/send-test", { method: "POST", body: to ? { tag, to } : { tag } }); toast(r.message || "Sent."); }
    catch (e) { toast(e.message); }
    tb.disabled = false; tb.textContent = w;
  };
}
/* Staff › Activity: every pilot's next-flight-due date, who is on leave and who is overdue */
async function staffCargoStock() {
  const body = $("#staffBody");
  body.innerHTML = `<p class="muted">Loading cargo stock…</p>`;
  let d;
  try { d = await api("/api/staff/cargo-stock"); } catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const P = d.policy;
  const when = d.last_stocked ? new Date(d.last_stocked * 1000).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "not yet";
  body.innerHTML = `<div class="notice" style="margin:0 0 12px;${P.enabled ? "" : "border-color:var(--line)"}"><label style="display:flex;gap:8px;align-items:center;font-weight:700"><input type="checkbox" id="stockOn" ${P.enabled ? "checked" : ""}> Customer orders ${P.enabled ? "on" : "off"}</label>
    <p style="margin:6px 0 0;font-size:14px">${P.enabled ? "PAC's hubs and busiest stations keep real-company freight waiting for pilots, topped up at most every 30 minutes. Orders nobody flies go to another carrier a day after their deadline." : "Off: no new orders are created. Orders already waiting stay until they're flown or their deadline passes."}</p></div>
    <form id="stockForm" class="row" style="gap:14px;align-items:flex-end;margin-bottom:10px">
      <label>Shipments waiting at each hub<br><input name="hub" type="number" min="0" max="40" value="${P.hub_target}" style="width:90px"></label>
      <label>At each other station<br><input name="station" type="number" min="0" max="20" value="${P.station_target}" style="width:90px"></label>
      <label>How many other stations<br><input name="stations" type="number" min="0" max="60" value="${P.stations}" style="width:90px"></label>
      <button class="btn small" type="submit">Save</button>
      <button class="btn ghost small" type="button" id="stockNow">Restock now</button></form>
    <p class="muted" style="max-width:90ch;font-size:14px">Hubs: ${d.hubs.map(esc).join(", ")}. The other stations are the ones with the most scheduled departures. A target is a minimum: freight pilots leave behind adds to it. About ${Math.round(d.truck_share * 100)}% of new orders go to a town near a PAC destination with the last leg by truck. Freight on a booking left unflown for ${d.idle_release_h / 24} days goes back on the shelf. Last restocked: ${esc(when)}.</p>
    <div class="aar-wrap"><table class="aar-table"><thead><tr><th>Station</th><th class="r">Target</th><th class="r">Waiting now</th><th class="r">Of which customer orders</th><th class="r">Weight</th><th>Shed</th></tr></thead><tbody>
    ${d.stations.map(x => `<tr><td><b class="mono">${esc(x.icao)}</b> ${esc(x.city || "")} ${x.hub ? '<span class="tag dark">Hub</span>' : ""}</td><td class="r">${x.target}</td><td class="r ${x.waiting < x.target ? "aar-bad" : ""}">${x.waiting}</td><td class="r">${x.orders}</td><td class="r mono">${fmt(x.weight_lbs)} lb</td><td>${x.shed_pct}% <small class="muted">${esc(x.shed_level)} · room for ${fmt(x.shed_capacity)} lb</small></td></tr>`).join("")}
    </tbody></table></div>`;
  $("#stockOn").onchange = async e => {
    try { await api("/api/settings", { method: "POST", body: { cargo_orders_enabled: e.target.checked } }); toast(e.target.checked ? "Customer orders on." : "Customer orders off."); staffCargoStock(); }
    catch (err) { toast(err.message); e.target.checked = !e.target.checked; }
  };
  $("#stockForm").onsubmit = async e => {
    e.preventDefault(); const f = e.target;
    try { await api("/api/settings", { method: "POST", body: { cargo_orders_hub_target: +f.hub.value, cargo_orders_station_target: +f.station.value, cargo_orders_stations: +f.stations.value } }); toast("Saved. Stations top up on the next restock."); staffCargoStock(); }
    catch (err) { toast(err.message); }
  };
  $("#stockNow").onclick = async () => {
    try { const r = await api("/api/staff/cargo-stock/restock", { method: "POST" }); toast(`Restocked: ${r.created} new order${r.created === 1 ? "" : "s"}${r.withdrawn ? `, ${r.withdrawn} expired` : ""}.`); staffCargoStock(); }
    catch (err) { toast(err.message); }
  };
}
async function staffActivity() {
  const body = $("#staffBody");
  body.innerHTML = `<p class="muted">Loading activity…</p>`;
  let d;
  try { d = await api("/api/staff/activity"); } catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const day = t => t ? new Date(t * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "–";
  const chip = { overdue: '<span class="tag">Overdue</span>', soon: '<span class="tag amber">Due soon</span>', leave: '<span class="tag dark">On leave</span>', ok: '<span class="tag green">Active</span>' };
  const c = d.counts, P = d.policy;
  const onoff = `<div class="notice" style="margin:0 0 12px;${P.enabled ? "" : "border-color:var(--line)"}"><label style="display:flex;gap:8px;align-items:center;font-weight:700"><input type="checkbox" id="actOn" ${P.enabled ? "checked" : ""}> Activity rule ${P.enabled ? "ON" : "OFF"}</label>
    <p style="margin:6px 0 0;font-size:14px">${P.enabled ? "Pilots see their next-flight-due date on Home, linked pilots get a Discord reminder, and the handbook explains the rule." : "Off: pilots see no due date, get no reminders and the handbook doesn't mention it. Leave of absence works either way, and pilots on leave show below. Switch the rule on whenever PAC is big enough to need it."}</p></div>`;
  body.innerHTML = onoff + `<p class="muted" style="max-width:85ch">${P.enabled ? "" : "<b>When switched on:</b> "}Pilots fly at least once every <b>${P.days} days</b>. The date counts from their last flight, joining, or the end of their last leave, whichever is latest. Linked pilots get a Discord DM ${P.remind_days} days before. ${P.auto_inactive ? "<b>Overdue pilots are marked Inactive automatically</b> and become Active again when they fly." : "Nobody is marked Inactive automatically: use the roster when you decide to."}</p>
    <div class="row" style="gap:18px;margin:8px 0 12px"><span>${chip.overdue} ${c.overdue}</span><span>${chip.soon} ${c.soon}</span><span>${chip.leave} ${c.leave}</span><span>${chip.ok} ${c.ok}</span></div>
    <form id="actPolicy" class="row" style="gap:12px;align-items:flex-end;margin-bottom:14px">
      <label>Fly at least every<br><input name="days" type="number" min="14" max="180" value="${P.days}" style="width:80px"> days</label>
      <label>Remind<br><input name="remind" type="number" min="1" max="30" value="${P.remind_days}" style="width:70px"> days before</label>
      <label>Longest leave<br><input name="leave" type="number" min="7" max="120" value="${P.leave_max_days}" style="width:70px"> days</label>
      <label style="flex-direction:row;gap:6px;display:flex;align-items:center"><input name="auto" type="checkbox" ${P.auto_inactive ? "checked" : ""}> Mark overdue pilots Inactive automatically</label>
      <button class="btn small" type="submit">Save</button></form>
    <div class="aar-wrap"><table class="aar-table"><thead><tr><th>Pilot</th><th>State</th><th>Last flight</th><th>Next flight due</th><th>Roster status</th><th>Leave</th></tr></thead><tbody>
    ${d.pilots.map(p => `<tr><td><b class="mono">${esc(p.pilot_id)}</b> ${esc(p.name)}</td><td>${chip[p.state]}</td><td>${day(p.last_flight)}</td>
      <td>${day(p.due)} <small class="muted">${p.days_left < 0 ? `${-p.days_left} days over` : `${p.days_left} days left`}</small></td><td>${esc(p.status)}</td>
      <td>${p.leave ? `Until ${day(p.leave.until)}${p.leave.reason ? `<br><small class="muted">${esc(p.leave.reason)}</small>` : ""}` : "–"}</td></tr>`).join("")}
    </tbody></table></div>`;
  $("#actOn").onchange = async e => {
    try { await api("/api/settings", { method: "POST", body: { activity_rule_on: e.target.checked } }); S.settings.activity_rule_on = e.target.checked; toast(e.target.checked ? "Activity rule switched on." : "Activity rule switched off."); staffActivity(); }
    catch (err) { toast(err.message); e.target.checked = !e.target.checked; }
  };
  $("#actPolicy").onsubmit = async e => {
    e.preventDefault(); const f = e.target;
    try { await api("/api/settings", { method: "POST", body: { activity_days: +f.days.value, activity_remind_days: +f.remind.value, leave_max_days: +f.leave.value, activity_auto_inactive: f.auto.checked } }); toast("Activity policy saved."); staffActivity(); }
    catch (err) { toast(err.message); }
  };
}
const statusCls = s => ({ Pending: "pending", Rejected: "rejected", Accepted: "accepted" })[s] || "";
/* Staff › Partner photos: the Wikimedia Commons photo each partner flight's landing card uses, with its credit */
async function staffPartnerPhotos(body = $("#staffBody")) {
  body.innerHTML = `<p class="muted">Loading partner photos…</p>`;
  let rows;
  try { rows = await api("/api/staff/partner-photos"); } catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const paint = list => {
    body.innerHTML = `<p class="muted" style="max-width:80ch">Landing and takeoff cards for partner flights use a real photo of that airline's aircraft, picked automatically from Wikimedia Commons. Only photos whose license allows reuse are used, and each card credits the photographer and license. New combinations are fetched in the background, so refresh in a minute if some are still missing.</p>
    <div class="pp-grid">${list.map(r => `<article class="pp-card">
      <div class="pp-img">${r.url ? `<img src="${esc(r.url)}" alt="${esc(r.partner_name + " " + r.aircraft_name)}" loading="lazy">` : `<span>${r.off ? "Using the PAC photo" : r.error ? "No photo yet" : "Fetching…"}</span>`}</div>
      <div class="pp-body"><b>${esc(r.partner_name)}</b> · ${esc(r.aircraft_name)}
        ${r.url ? `<small>Photo: ${esc(r.artist || "")} · ${esc(r.licence || "")}${r.pinned ? " · pinned" : ""} · <a href="${esc(r.page || "#")}" target="_blank" rel="noopener">Commons page</a></small>` : r.error && !r.off ? `<small class="muted">${/urlopen|timed out|Tunnel|resolve|reach/i.test(r.error) ? "Couldn't reach Wikimedia Commons yet. The site tries again automatically every few hours." : esc(r.error)}</small>` : ""}
        <div class="row" style="margin-top:8px">
          ${r.off ? `<button class="btn small" data-pp="auto" data-k="${esc(r.partner)}" data-t="${esc(r.aircraft)}">Use a Commons photo</button>`
            : `<button class="btn ghost small" data-pp="next" data-k="${esc(r.partner)}" data-t="${esc(r.aircraft)}">Next photo</button>
               <button class="btn ghost small" data-pp="pac" data-k="${esc(r.partner)}" data-t="${esc(r.aircraft)}">Use PAC photo</button>
               <button class="btn ghost small" data-pp="browse" data-k="${esc(r.partner)}" data-t="${esc(r.aircraft)}">Browse photos</button>`}
        </div></div></article>`).join("")}</div>`;
    body.querySelectorAll("[data-pp]").forEach(b => b.onclick = async () => {
      if (b.dataset.pp === "browse") { const r = list.find(x => x.partner === b.dataset.k && x.aircraft === b.dataset.t); return browsePartnerPhotos(r, list, paint, body); }
      const file = null;
      b.disabled = true; b.textContent = "Working…";
      try { const list2 = await api(`/api/staff/partner-photos/${b.dataset.k}/${b.dataset.t}`, { method: "POST", body: { action: b.dataset.pp, file } }); S.partnerPhotos = null; paint(list2); toast("Partner photo updated."); }
      catch (e) { toast(e.message); paint(list); }
    });
  };
  paint(rows);
}
/* every freely licensed photo found for one partner and type, side by side; click one to use it */
async function browsePartnerPhotos(r, list, back, body = $("#staffBody")) {
  const head = `<div class="row" style="align-items:center;gap:12px;margin-bottom:8px"><button class="btn ghost small" id="ppBack">← Back to all partners</button>
    <b>${esc(r.partner_name)} · ${esc(r.aircraft_name)}</b></div>`;
  body.innerHTML = head + `<p class="muted">Searching Wikimedia Commons…</p>`;
  $("#ppBack").onclick = () => back(list);
  let cands;
  try { cands = await api(`/api/staff/partner-photos/${r.partner}/${r.aircraft}/browse`); }
  catch (e) { body.innerHTML = head + `<div class="notice err">${esc(e.message)}</div>`; $("#ppBack").onclick = () => back(list); return; }
  body.innerHTML = head + (cands.length ? `<p class="muted">${cands.length} freely licensed photo${cands.length === 1 ? "" : "s"} found. Click the one you want on the cards.</p>
    <div class="pp-grid">${cands.map((c, i) => `<article class="pp-card pp-pick${c.current ? " is-current" : ""}" data-i="${i}" tabindex="0" role="button">
      <div class="pp-img"><img src="${esc(c.preview)}" alt="" loading="lazy"></div>
      <div class="pp-body">${c.current ? `<b class="pp-tag">In use now</b>` : ""}<small>Photo: ${esc(c.artist)} · ${esc(c.licence)} · <a href="${esc(c.page)}" target="_blank" rel="noopener">Commons page</a></small></div>
    </article>`).join("")}</div>` : `<p class="muted">No freely licensed photos of this aircraft were found on Commons. The cards will keep using the PAC photo.</p>`);
  $("#ppBack").onclick = () => back(list);
  body.querySelectorAll(".pp-pick").forEach(el => {
    const choose = async ev => {
      if (ev.target.closest("a")) return;
      const c = cands[+el.dataset.i];
      if (c.current) return back(list);
      el.style.opacity = .5;
      try {
        const list2 = await api(`/api/staff/partner-photos/${r.partner}/${r.aircraft}`, { method: "POST", body: { action: "pin", file: c.file } });
        S.partnerPhotos = null; toast("Photo chosen."); back(list2);
      } catch (e) { el.style.opacity = 1; toast(e.message); }
    };
    el.onclick = choose; el.onkeydown = ev => { if (ev.key === "Enter") choose(ev); };
  });
}
function staffReviews() {
  const list = S.staff.reviews;
  $("#staffBody").innerHTML = list.length ? list.map(r => `<div class="q-item ${statusCls(r.review_status)}">
    <div><b>${esc(r.flight_number)}</b> · ${esc(r.mission_title)} <span class="tag ${r.review_status === "Pending" ? "amber" : r.review_status === "Rejected" ? "" : "green"}">${r.review_status}</span>
      <div class="meta">${new Date(r.filed_at * 1000).toISOString().substr(0, 16).replace("T", " ")}Z · ${esc(r.pilot || "")} · ${r.dep} – ${r.arr}${r.arr !== r.planned_arr ? ` (planned ${r.planned_arr})` : ""} · ${esc(S.fleet[r.aircraft]?.icao || r.aircraft)}${r.airframe ? " " + esc(r.airframe) : ""}
      · landing ${r.landing_rate ?? "–"} fpm / ${r.landing_g ?? "–"} G · score ${r.score == null ? "Unscored · Manual" : `${r.score} (${r.grade})`} · ${esc(r.status)} · ${fmt(r.points)} pts</div>
      ${r.flags.length ? `<div style="margin-top:6px">${r.flags.map(f => `<span class="tag amber" style="margin:0 6px 0 0">${esc(f)}</span>`).join("")}</div>` : ""}
      ${[["checkride", "Line checkride"], ["type_checkride", "Type checkride"]].filter(([k]) => r[k]).map(([k, l]) => r[k].passed
        ? `<div style="margin-top:6px"><span class="tag green" style="margin:0">${l} passed${r[k].passed_after_review ? " after review" : ""}</span></div>`
        : `<div class="notice err" style="margin-top:8px;font-size:13px"><b>${l} not passed:</b> ${esc(r[k].reasons.join(", "))}. Accepting the PIREP doesn't change this. If a penalty was ACARS misreading something, waive it below and the checkride is checked again. Otherwise the pilot flies it again.</div>`).join("")}
      ${r.review_note ? `<div class="meta" style="margin-top:4px">Staff note: ${esc(r.review_note)}</div>` : ""}</div>
    ${r.breakdown.some(x => x[1] < 0) ? `<details class="waive" style="grid-column:1/-1"><summary>Adjust penalties</summary>
      <p class="muted" style="font-size:13px;margin:6px 0">Waive a penalty when ACARS misread something. Score, grade and points are recalculated, and the waiver stays visible on the PIREP.</p>
      ${r.breakdown.map((x, i) => x[1] < 0 ? `<label style="display:flex;gap:8px;font-size:14px;padding:3px 0"><input type="checkbox" data-waive="${r.id}" value="${i}" style="accent-color:var(--red)">${esc(x[0])} <b class="neg">${x[1]}</b></label>` : "").join("")}
      ${r.airframe ? `<label style="display:flex;gap:8px;font-size:14px;padding:6px 0 3px"><input type="checkbox" data-release="${r.id}" style="accent-color:var(--red)">Also return ${esc(r.airframe)} to service if it was grounded by this flight</label>` : ""}
      <div class="row" style="margin-top:6px"><input placeholder="Reason (shown on the PIREP)" data-wnote="${r.id}" style="border:1px solid var(--line);border-radius:3px;padding:6px 9px;min-width:280px"><button class="btn small" data-waive-go="${r.id}">Waive selected</button></div></details>` : ""}
    <div class="q-actions"><button class="btn ghost small" data-open-pirep="${r.id}">Details</button>
      <input placeholder="${r.manual ? "Required: reason for your decision (5+ characters)" : "Note to the pilot (optional)"}" data-note="${r.id}" aria-label="Review note">
      ${r.manual && r.review_status === "Pending" ? `<label style="display:flex;gap:6px;align-items:center;font-size:13px"><input type="checkbox" data-complete="${r.id}"> Deliver the booked cargo and move the aircraft and pilot to ${esc(r.arr)}</label>` : ""}
      ${(r.manual ? r.review_status === "Pending" : r.review_status !== "Accepted") ? `<button class="btn small" data-review="${r.id}" data-act="accept">Accept</button>` : ""}
      ${r.manual ? (r.review_status === "Pending" ? `<button class="btn ghost small" data-review="${r.id}" data-act="reject">Reject</button>` : "")
        : `<label style="display:flex;gap:6px;align-items:center;font-size:13px" title="Untick only if the flight didn't really happen; the cargo then goes back to ${esc(r.dep)}"><input type="checkbox" data-keep="${r.id}" checked> If rejected, the cargo stays at ${esc(r.arr)} (flown, not credited)</label>
          <button class="btn ghost small" data-review="${r.id}" data-act="reject">${r.review_status === "Rejected" ? "Update rejection" : "Reject"}</button>`}</div></div>`).join("")
    : `<div class="empty">No PIREPs filed yet.</div>`;
  const ab = S.staff.aborts || [];   // ACARS 1.1.7: flights pilots aborted in the last 14 days
  if (ab.length) $("#staffBody").insertAdjacentHTML("beforeend", `<h3 style="margin:24px 0 6px">Aborted flights · last 14 days</h3>
    <p class="muted" style="font-size:13px;margin:0 0 8px">Nothing was filed for these. Many aborts on one flight or by one pilot can point to a sim, ACARS or planning problem worth a word.</p>
    <table class="staff-table"><thead><tr><th>When</th><th>Pilot</th><th>Flight</th><th>Route</th><th>Got to</th><th>Reason</th></tr></thead><tbody>${ab.map(a => `<tr>
      <td class="mono">${new Date(a.at * 1000).toISOString().substr(5, 11).replace("T", " ")}Z</td><td>${esc(a.pilot || a.pilot_id || "")}</td>
      <td>${esc(a.flight || "")} <span class="muted">${esc(a.aircraft || "")}</span></td><td>${esc(a.dep || "")}–${esc(a.arr || "")}</td>
      <td>${esc((a.phase || "before start").replace(/_/g, " ").toLowerCase())}${a.flown_nm ? ` · ${fmt(a.flown_nm)} nm` : ""}${a.auto_started ? ` <span class="tag grey">auto-started</span>` : ""}</td>
      <td>${esc(a.reason || "—")} <span class="muted">(${esc(a.source || "")})</span></td></tr>`).join("")}</tbody></table>`);
  document.querySelectorAll("[data-review]").forEach(b => b.onclick = async () => {
    try { await api("/api/staff/reviews/" + b.dataset.review, { method: "POST", body: { action: b.dataset.act, note: document.querySelector(`[data-note="${b.dataset.review}"]`).value, complete_flight: !!document.querySelector(`[data-complete="${b.dataset.review}"]`)?.checked, keep_cargo: document.querySelector(`[data-keep="${b.dataset.review}"]`)?.checked ?? true } });
    toast(b.dataset.act === "accept" ? "PIREP accepted." : "PIREP rejected."); loadStaff(); } catch(e) { toast(e.message); }
  });
  document.querySelectorAll("[data-open-pirep]").forEach(b => b.onclick = () => openDetail(b.dataset.openPirep));
  document.querySelectorAll("[data-waive-go]").forEach(b => b.onclick = async () => {
    const id = b.dataset.waiveGo;
    const items = [...document.querySelectorAll(`[data-waive="${id}"]:checked`)].map(x => x.value);
    try {
      const r = await api(`/api/staff/reviews/${id}/waive`, { method: "POST", body: { items, note: document.querySelector(`[data-wnote="${id}"]`).value,
        release_airframe: !!document.querySelector(`[data-release="${id}"]`)?.checked } });
      toast(`Recalculated: ${r.score == null ? "Unscored · Manual" : `${r.score} (${r.grade})`}, ${r.points} points.`); loadStaff(); refreshCore();
    } catch (e) { toast(e.message); }
  });
}
function staffApps() {
  const list = S.staff.applications, old = list.filter(a => a.status !== "Pending" && !a.on_roster);
  const srcCount = {}; list.forEach(a => { if (a.source) srcCount[a.source] = (srcCount[a.source] || 0) + 1; });
  const srcRows = Object.entries(srcCount).sort((x, y) => y[1] - x[1]);
  const srcTally = srcRows.length ? `<div class="notice" style="margin:0 0 12px"><b>Where applicants come from</b> <span class="muted">(all ${list.length} applications)</span>
    <div class="row" style="gap:8px;margin-top:6px;flex-wrap:wrap">${srcRows.map(([s, n]) => `<span class="tag">${esc(s)} <b>${n}</b></span>`).join("")}${list.some(a => !a.source) ? `<span class="tag dark">Not asked / blank <b>${list.filter(a => !a.source).length}</b></span>` : ""}</div></div>` : "";
  $("#staffBody").innerHTML = srcTally + (old.length ? `<div class="row" style="justify-content:space-between;align-items:center;margin-bottom:12px;gap:12px;flex-wrap:wrap">
      <span class="muted" style="font-size:14px">${old.length} reviewed application${old.length === 1 ? "" : "s"} from people who aren't on the roster (declined, or pilots since removed).</span>
      <button class="btn ghost small" id="clearOldApps">Clear old applications</button></div>` : "") + (list.length ? list.map(a => `<div class="q-item ${statusCls(a.status === "Approved" ? "Accepted" : a.status)}">
    <div><b>${esc(a.name)}</b> <span class="tag ${a.status === "Pending" ? "amber" : a.status === "Approved" ? "green" : ""}">${a.status}${a.pilot_id ? " · " + a.pilot_id : ""}</span>
      <div class="meta">${esc(a.email)} · ${esc(a.country || "–")} · ${esc(a.simulator || "")} · ${esc(a.experience || "")} · prefers ${esc(a.hub || "–")}${a.discord ? " · Discord " + esc(a.discord) : ""}${a.source ? ' · <b>via ' + esc(a.source) + "</b>" : ""} · ${new Date(a.submitted * 1000).toISOString().substr(0, 10)}</div>
      ${a.motivation ? `<p style="margin:6px 0 0;max-width:80ch">${esc(a.motivation)}</p>` : ""}${a.note ? `<div class="meta">Note: ${esc(a.note)}</div>` : ""}</div>
    <div class="q-actions">${a.status === "Pending" ? `<input placeholder="Note (optional)" data-anote="${a.id}" aria-label="Note">
      <button class="btn small" data-app="${a.id}" data-act="approve">Approve</button><button class="btn ghost small" data-app="${a.id}" data-act="reject">Decline</button>` : ""}
      ${!a.on_roster ? `<button class="btn ghost small" data-app-del="${a.id}" title="Delete this application">Delete</button>` : ""}</div></div>`).join("")
    : `<div class="empty">No applications yet. They arrive from the form on the home page.</div>`);
  document.querySelectorAll("[data-app-del]").forEach(b => b.onclick = async () => {
    const a = list.find(x => String(x.id) === b.dataset.appDel);
    if (!confirm(`Delete ${a.name}'s application${a.status === "Pending" ? ", without approving or declining it" : ""}? This can't be undone.`)) return;
    try { await api("/api/staff/applications/" + a.id, { method: "DELETE" }); toast(`${a.name}'s application deleted.`); loadStaff(); }
    catch (e) { toast(e.message); }
  });
  if ($("#clearOldApps")) $("#clearOldApps").onclick = async () => {
    if (!confirm(`Delete ${old.length} old application${old.length === 1 ? "" : "s"}?\n\nApplications from pilots on the roster and ones still waiting for review are kept.`)) return;
    try { const r = await api("/api/staff/applications/clear-old", { method: "POST", body: {} }); toast(`${r.deleted} old application${r.deleted === 1 ? "" : "s"} deleted.`); loadStaff(); }
    catch (e) { toast(e.message); }
  };
  document.querySelectorAll("[data-app]").forEach(b => b.onclick = async () => {
    const r = await api("/api/staff/applications/" + b.dataset.app, { method: "POST", body: { action: b.dataset.act, note: document.querySelector(`[data-anote="${b.dataset.app}"]`)?.value } });
    const m = r.mail || {};
    toast(r.pilot_id ? (m.sent ? `Approved as ${r.pilot_id}. Welcome letter sent to ${m.to}.` : `Approved as ${r.pilot_id}.`)
                     : (m.sent ? `Application declined. Letter sent to ${m.to}.` : "Application declined."));
    loadStaff();
    if (!m.sent) {
      const why = { no_mail: "PAC's email account isn't set up yet, so this letter wasn't sent. Set it up under <b>Staff › Site and rules › Email</b> and PAC will send future letters the moment you approve someone.",
                    no_address: "This applicant didn't give an email address, so there's nobody to send to.",
                    off: r.pilot_id ? "Automatic sending is switched off for welcome letters (Staff › Site and rules › Email)." : "Decline letters aren't sent automatically. Send this one yourself, or switch it on under Staff › Site and rules › Email." }[m.why]
                  || (m.error ? `PAC tried to send this letter but the mail server refused: ${esc(m.error)}` : "");
      if (r.pilot_id) openLetter("accepted", { pid: r.pilot_id, why }); else openLetter("rejected", { name: r.name, email: r.email, reason: r.reason, why });
    }
  });
}
/* Staff › Transfer hours: check each source's public logbook, then approve (credit is worked out) or reject with a reason */
async function staffTransfers() {
  const body = $("#staffBody");
  body.innerHTML = `<p class="muted">Loading transfer requests…</p>`;
  let d;
  try { d = await api("/api/staff/transfers"); } catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const r = d.rules;
  const credit = (srcs) => { let va = 0, net = 0; srcs.forEach(s => { if (!s.ok) return; s.kind === "network" ? net += s.h : va += s.h; });
    const base = Math.max(va, net); return { base: Math.round(base * 10) / 10, cr: Math.min(r.cap, Math.round(base * r.share * 10) / 10) }; };
  body.innerHTML = `<p class="muted" style="max-width:85ch">Open each link and check that the <b>name or pilot ID matches</b> and the <b>hours</b> are what the pilot says. If a link needs a login (common with vAMSYS, Newsky and phpVMS), go by the screenshot: it must show the pilot's name or ID together with the hours. Not sure? Leave it pending and ask the pilot for a quick Discord screen share. Tick the sources you could verify and correct the hours if needed. PAC credits half of the verified total, up to ${r.cap} hours: VA hours add up, VATSIM/IVAO hours don't stack on top of VA hours (the larger total counts). Approving never lowers hours already set in the Roster.</p>
    ${d.requests.length ? d.requests.map(q => `<div class="q-item ${statusCls(q.status === "Approved" ? "Accepted" : q.status)}" data-trq="${q.id}">
      <div><b>${esc(q.pilot_name || q.pilot_id)}</b> · ${esc(q.pilot_id)} <span class="tag ${q.status === "Pending" ? "amber" : q.status === "Approved" ? "green" : ""}">${esc(q.status)}</span>
        ${q.requests_by_pilot > 1 ? `<span class="tag dark">${q.requests_by_pilot} requests (appeal)</span>` : ""}
        <div class="meta">Sent ${trDate(q.submitted)} · currently ${esch(q.current_hours)} transfer h${q.reviewed_at ? ` · reviewed ${trDate(q.reviewed_at)} by ${esc(q.reviewed_by || "")}, ${esch(q.credited || 0)} h credited` : ""}</div>
        ${q.comment ? `<p class="small" style="margin:6px 0 0;max-width:80ch">Pilot's note: ${esc(q.comment)}</p>` : ""}
        <table class="tr-staff"><thead><tr><th>Verified</th><th>Source</th><th>Logbook</th><th>Proof</th><th>Claimed</th><th>Verified hours</th></tr></thead><tbody>
        ${q.sources.map((s, i) => `<tr><td>${q.status === "Pending" ? `<input type="checkbox" data-tok="${i}" style="accent-color:var(--red);width:18px;height:18px" aria-label="Verified">` : s.approved ? "✓" : "✗"}</td>
          <td><b>${esc(s.name)}</b><br><small class="muted">${s.kind === "network" ? "VATSIM/IVAO" : "Virtual airline"}</small></td>
          <td><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">Open link ↗</a><br><small class="muted" style="word-break:break-all">${esc(s.url)}</small></td>
          <td>${s.proof ? `<a href="${esc(s.proof)}" target="_blank" rel="noopener">Screenshot ↗</a>` : "–"}</td>
          <td>${esch(s.hours)} h</td>
          <td>${q.status === "Pending" ? `<input type="number" min="0" step="0.1" value="${s.hours}" data-thr="${i}" style="width:90px" aria-label="Verified hours">` : s.approved ? `${esch(s.verified)} h` : "–"}</td></tr>`).join("")}</tbody></table>
        ${q.status === "Pending" ? `<div class="small" data-trest style="margin-top:6px"></div>` : ""}
        ${q.note ? `<div class="meta" style="margin-top:4px">Staff note: ${esc(q.note)}</div>` : ""}</div>
      <div class="q-actions">${q.status === "Pending" ? `<input placeholder="Note to the pilot (required to reject)" data-trnote aria-label="Note to the pilot">
        <button class="btn small" data-trgo="approve">Approve</button><button class="btn ghost small" data-trgo="reject">Reject</button>` : ""}</div></div>`).join("")
    : `<div class="empty">No transfer requests yet. Pilots send them from Career.</div>`}`;
  body.querySelectorAll("[data-trq]").forEach(card => {
    const q = d.requests.find(x => String(x.id) === card.dataset.trq);
    if (q.status !== "Pending") return;
    const read = () => q.sources.map((s, i) => ({ kind: s.kind, ok: card.querySelector(`[data-tok="${i}"]`).checked, h: Number(card.querySelector(`[data-thr="${i}"]`).value) || 0 }));
    const show = () => { const c = credit(read()); card.querySelector("[data-trest]").innerHTML = c.base ? `Verified total <b>${esch(c.base)} h</b> → <b>${esch(c.cr)} h</b> credited${c.base * r.share > r.cap ? ` (capped at ${r.cap})` : ""}.` : `<span class="muted">Tick the sources you verified to see the credit.</span>`; };
    card.oninput = show; card.onchange = show; show();
    card.querySelectorAll("[data-trgo]").forEach(b => b.onclick = async () => {
      const act = b.dataset.trgo, src = read();
      const c = credit(src);
      if (act === "approve" && !confirm(`Credit ${c.cr} transfer hours to ${q.pilot_name || q.pilot_id}?`)) return;
      b.disabled = true;
      try {
        const out = await api(`/api/staff/transfers/${q.id}`, { method: "POST", body: { action: act, note: card.querySelector("[data-trnote]").value, sources: src.map(s => ({ approved: s.ok, verified: s.h })) } });
        toast(act === "approve" ? `${out.credited} h credited${out.mailed ? ", pilot emailed" : ""}.` : `Request rejected${out.mailed ? ", pilot emailed" : ""}.`);
        loadStaff();
      } catch (e) { toast(e.message); b.disabled = false; }
    });
  });
}
function staffRoster() {
  const noCid = S.staff.roster.filter(p => (p.status || "Active") === "Active" && !p.vatsim_cid).length;
  $("#staffBody").innerHTML = `<div class="row" style="justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px">
      <span class="muted" style="font-size:13px">${noCid ? `<span class="tag amber">${noCid}</span> active pilot${noCid === 1 ? " has" : "s have"} no VATSIM CID — needed for the VATSIM VA roster. Ask them to add it in Settings.` : "Every active pilot has a VATSIM CID on file. ✓"}</span>
      <a class="btn ghost small" href="/api/staff/roster.csv" download>⬇ Download audit roster (CSV)</a></div>
    <div class="table-wrap"><table class="staff-table"><thead><tr><th>ID</th><th>Name</th><th title="VATSIM CID / IVAO VID — needed for the VATSIM VA roster">Network IDs</th><th>Rank</th><th>Hours</th><th>Flights</th><th>Avg</th><th>Wallet</th><th>Transfer hrs</th><th title="Home hub: where the pilot is based">Hub</th><th>Checkride</th><th>Rank setting</th><th title="Cleared to fly the Kodiak for Pagani Remote Aviation">PRA</th><th>Status</th><th></th></tr></thead><tbody>
    ${S.staff.roster.map(p => `<tr data-pilot="${p.id}"><td><b>${p.id}</b>${p.staff ? ' <span class="tag dark">Staff</span>' : ""}</td><td>${esc(p.name)}<br><small class="muted">${esc(p.email || "")}</small></td>
      <td style="white-space:nowrap;font-size:13px">${p.vatsim_cid ? `VATSIM ${esc(p.vatsim_cid)}` : ((p.status || "Active") === "Active" ? '<span class="tag amber">no VATSIM</span>' : '<span class="muted">—</span>')}${p.ivao_vid ? `<br>IVAO ${esc(p.ivao_vid)}` : ""}</td>
      <td style="white-space:nowrap">${rankImg(p.rank)}${esc(p.rank)}${p.rank_override ? ' <span class="tag dark">Appointed</span>' : ""}</td>
      <td>${esch(p.hours)}</td><td>${p.flights}</td><td>${p.avg_score ?? "–"}</td>
      <td style="white-space:nowrap"><b class="${moneyCls(p.balance)}">${money(p.balance, true)}</b><br><small class="muted">at ${esc(p.location || "–")}</small>
        <div class="row" style="margin-top:4px;flex-wrap:nowrap"><input type="number" step="50" placeholder="±$" data-wamt="${p.id}" style="width:80px" aria-label="Wallet adjustment"><button class="btn ghost small" type="button" data-wadj="${p.id}">Adjust</button></div></td>
      <td><input type="number" min="0" step="0.1" value="${p.transfer_hours || 0}" data-f="transfer_hours" aria-label="Transfer hours" style="width:90px"></td>
      <td><select data-f="hub" aria-label="Home hub">${Object.keys(S.hubs || { KCVG: 1, LIMC: 1, KMIA: 1, OMDW: 1, VHHH: 1, PANC: 1 }).map(h => `<option ${h === (p.hub || "KCVG") ? "selected" : ""}>${h}</option>`).join("")}</select><br><small class="muted">at ${esc(p.location || "–")}</small></td>
      <td><select data-f="checkride" aria-label="Checkride">${["Pending", "Passed", "Waived"].map(o => `<option ${o === p.checkride ? "selected" : ""}>${o}</option>`).join("")}</select></td>
      <td><select data-f="rank_override" aria-label="Rank setting"><option value="">Earned by flying</option>${(S.ranks || []).map(r => `<option ${r.name === p.rank_override ? "selected" : ""}>${esc(r.name)}</option>`).join("")}</select></td>
      <td><input type="checkbox" data-f="pra" ${p.pra ? "checked" : ""} aria-label="Cleared for Pagani Remote Aviation" style="accent-color:var(--red);width:18px;height:18px"></td>
      <td><select data-f="status" aria-label="Status">${["Active", "On leave", "Inactive"].map(o => `<option ${o === p.status ? "selected" : ""}>${o}</option>`).join("")}</select></td>
      <td style="white-space:nowrap"><button class="btn small" data-save-pilot="${p.id}">Save</button>
        <button class="btn ghost small" type="button" data-signin="${p.id}" title="A one-time link to set or reset their password">Sign-in link</button>
        <button class="btn ghost small" type="button" data-letter="${p.id}" title="A letter with a fresh sign-in link, ready to send">Letter</button>
        ${p.id === S.me?.id ? "" : `<button class="btn ghost small danger" type="button" data-remove="${p.id}" title="Remove this pilot from PAC">Remove</button>`}
        <button class="btn ghost small" type="button" data-ratings="${p.id}" title="Grant or remove type ratings">Ratings</button></td></tr>`).join("")}</tbody></table></div>
    <p class="muted" style="font-size:13px">Transfer hours count towards rank, not towards PAC totals or leaderboards. Pilots normally request them under Career (reviewed in the Transfer hours tab); editing them here is for corrections. Tick <b>PRA</b> for pilots cleared to fly the Kodiak for Pagani Remote Aviation; they show in that division on the group hub. Each pilot signs in with their own pilot ID; <b>Sign-in link</b> makes a one-time link to set or reset a pilot's password.</p>`;
  document.querySelectorAll("[data-signin]").forEach(b => b.onclick = () => showSigninLink(b.dataset.signin));
  document.querySelectorAll("[data-ratings]").forEach(b => b.onclick = () => staffRatings(b.dataset.ratings));
  document.querySelectorAll("[data-letter]").forEach(b => b.onclick = () => openLetter("reminder", { pid: b.dataset.letter }));
  document.querySelectorAll("[data-remove]").forEach(b => b.onclick = () => removePilot(b.dataset.remove));
  document.querySelectorAll("[data-wadj]").forEach(b => b.onclick = async () => {
    const amt = Number(document.querySelector(`[data-wamt="${b.dataset.wadj}"]`).value);
    if (!amt) { toast("Enter an amount, negative to deduct."); return; }
    try { await api("/api/staff/wallet/" + b.dataset.wadj, { method: "POST", body: { amount: amt, note: amt > 0 ? "Staff advance / bonus" : "Staff deduction" } }); toast("Wallet updated."); loadStaff(); loadMe(); } catch (e) { toast(e.message); }
  });
  document.querySelectorAll("[data-save-pilot]").forEach(b => b.onclick = async () => {
    const tr = b.closest("tr"), body = {}; tr.querySelectorAll("[data-f]").forEach(el => body[el.dataset.f] = el.type === "checkbox" ? el.checked : el.value);
    try { await api("/api/staff/roster/" + b.dataset.savePilot, { method: "POST", body }); toast(`${b.dataset.savePilot} saved.`); loadStaff(); refreshCore(); } catch (e) { toast(e.message); }
  });
}
async function staffNews(edit, body = $("#staffBody")) {
  let list = [];
  try { list = await api("/api/staff/news"); } catch (e) { toast(e.message); }
  const n = edit ? list.find(x => x.id === edit) : null;
  const now = Date.now() / 1000;
  body.innerHTML = `<form class="form-card" id="newsForm">
      <h3 class="full" style="margin:0">${n ? "Edit post" : "Post news or a company NOTAM"}</h3>
      <div class="field"><label for="nw_kind">Type</label><select id="nw_kind" name="kind"><option value="news" ${n?.kind === "news" ? "selected" : ""}>News</option><option value="notam" ${n?.kind === "notam" ? "selected" : ""}>Company NOTAM</option></select></div>
      <div class="field"><label for="nw_days">Show for (days, empty = until deleted)</label><input id="nw_days" name="days" type="number" min="0" step="1" value="${n?.expires ? Math.max(1, Math.round((n.expires - now) / 86400)) : ""}"></div>
      <div class="field full"><label for="nw_title">Title</label><input id="nw_title" name="title" maxlength="120" value="${esc(n?.title || "")}" required></div>
      <div class="field full"><label for="nw_body">Text</label><textarea id="nw_body" name="body" rows="3" maxlength="2000">${esc(n?.body || "")}</textarea></div>
      <label class="full" style="display:flex;gap:8px;align-items:center"><input type="checkbox" name="important" ${n?.important ? "checked" : ""} style="accent-color:var(--red)"> Important (shown first, in red)</label>
      <label class="full" style="display:flex;gap:8px;align-items:center"><input type="checkbox" name="discord" ${n ? "" : "checked"} style="accent-color:var(--red)"> ${n ? "Post the updated version to Discord too" : "Post it to Discord too (NOTAMs go to the NOTAM channel, news to announcements)"}</label>
      <p class="muted full" style="margin:0;font-size:13px">News appears on the home page. Company NOTAMs also show as a banner on the home page and mission board, and are sent to pilots as ACARS messages when they start tracking, so keep them short: one rule or warning each. Use News for longer announcements.</p>
      <div class="full row"><button class="btn" type="submit">${n ? "Save" : "Post"}</button>${n ? `<button class="btn ghost" type="button" id="nwCancel">Cancel</button>` : ""}</div></form>
    <div class="table-wrap"><table class="staff-table"><thead><tr><th>Posted</th><th>Type</th><th>Title</th><th>Until</th><th></th></tr></thead><tbody>
    ${list.map(x => `<tr><td>${new Date(x.time * 1000).toISOString().substr(0, 10)}</td><td>${x.kind === "notam" ? '<span class="tag amber" style="margin:0">NOTAM</span>' : '<span class="tag grey" style="margin:0">News</span>'}${x.important ? ' <span class="tag" style="margin:0">Important</span>' : ""}</td>
      <td><b>${esc(x.title)}</b><br><small class="muted">${esc((x.body || "").slice(0, 110))}</small></td><td>${x.expires ? (x.expires < now ? "Expired" : new Date(x.expires * 1000).toISOString().substr(0, 10)) : "–"}</td>
      <td style="white-space:nowrap"><button class="btn small" type="button" data-nedit="${x.id}">Edit</button> <button class="btn ghost small" type="button" data-ndel="${x.id}" aria-label="Delete">×</button></td></tr>`).join("")}</tbody></table></div>`;
  $("#newsForm").onsubmit = async e => {
    e.preventDefault();
    const body2 = Object.fromEntries(new FormData(e.target).entries());
    body2.important = !!e.target.important.checked; body2.discord = !!e.target.discord.checked; if (n) body2.id = n.id;
    try { await api("/api/staff/news", { method: "POST", body: body2 }); toast(n ? "Post updated." : "Posted."); S.news = null; staffNews(undefined, body); } catch (err) { toast(err.message); }
  };
  if ($("#nwCancel")) $("#nwCancel").onclick = () => staffNews(undefined, body);
  body.querySelectorAll("[data-nedit]").forEach(b => b.onclick = () => staffNews(+b.dataset.nedit, body));
  body.querySelectorAll("[data-ndel]").forEach(b => b.onclick = async () => { if (!confirm("Delete this post?")) return; await api("/api/staff/news/" + b.dataset.ndel, { method: "DELETE" }); S.news = null; staffNews(undefined, body); });
}
const TYPE_FIELDS = [
  ["code", "Type code", "text", "e.g. B744F"], ["name", "Name", "text", "Boeing 747-400F"], ["icao", "ICAO type", "text", "B744"],
  ["simbrief_type", "SimBrief type", "text", "B744"], ["simbrief_airframe", "SimBrief airframe ID (optional)", "text", "277074_1793915409207"], ["sim", "Simulator", "select", ["MSFS", "X-Plane", "MSFS and X-Plane"]],
  ["sim_model", "Add-on aircraft", "text", ""], ["division", "Division", "text", "PAC"], ["role", "Role", "text", ""],
  ["unlock_rank", "Unlocked at rank", "rank", ""], ["max_payload_lbs", "Max payload (lb)", "number", ""], ["mtow_lbs", "MTOW (lb)", "number", ""],
  ["range_nm", "Typical range (nm)", "number", ""], ["min_rwy_ft", "Runway needed (ft)", "number", ""], ["cruise_ktas", "Cruise speed (kt TAS)", "number", ""],
  ["mach", "Cruise Mach", "number", ""], ["tailstrike_pitch", "Tail-strike pitch (°)", "number", ""], ["fuel_burn_pph", "Fuel burn (lb/h)", "number", ""],
  ["maint_per_bh", "Maintenance ($/block h)", "number", ""], ["ownership_per_bh", "Ownership ($/block h)", "number", ""],
  ["engines", "Engines", "text", ""], ["crew", "Flight crew", "text", ""], ["main_deck", "Main deck", "text", ""], ["entered_service", "Type in service since", "number", ""],
  ["description", "Description", "textarea", ""]];
async function staffTypes(editCode) {
  let d;
  try { d = await api("/api/staff/fleet-types"); } catch (e) { toast(e.message); return; }
  S.staffTypesData = d;
  const t = editCode === "__new" ? { code: "", sim: "MSFS", unlock_rank: "" } : d.types.find(x => x.code === editCode);
  const form = t ? `<form class="form-card" id="typeForm">
      <h3 class="full" style="margin:0">${editCode === "__new" ? "Add an aircraft type" : `Edit ${esc(t.name)}`}</h3>
      ${TYPE_FIELDS.map(([k, label, kind, ph]) => {
        const v = t[k] ?? "";
        const input = kind === "select" ? `<select id="tf_${k}" name="${k}">${ph.map(o => `<option ${o === v ? "selected" : ""}>${o}</option>`).join("")}</select>`
          : kind === "rank" ? `<select id="tf_${k}" name="${k}"><option value="">${editCode === "__new" ? "Second Officer (default)" : `Default (${esc(t.unlock_rank_effective || "")})`}</option>${d.ranks.map(o => `<option ${o === v ? "selected" : ""}>${o}</option>`).join("")}</select>`
          : kind === "textarea" ? `<textarea id="tf_${k}" name="${k}" rows="3">${esc(v)}</textarea>`
          : `<input id="tf_${k}" name="${k}" type="${kind}" ${kind === "number" ? 'step="any"' : ""} value="${esc(v)}" placeholder="${esc(ph)}" ${k === "code" && editCode !== "__new" ? "readonly" : ""}>`;
        return `<div class="field ${kind === "textarea" ? "full" : ""}"><label for="tf_${k}">${label}</label>${input}</div>`;
      }).join("")}
      ${editCode !== "__new" ? `<div class="field half"><label for="tf_photo">Photo</label><input id="tf_photo" type="file" accept="image/png,image/jpeg,image/webp"></div>` : `<p class="muted full" style="margin:0;font-size:13px">Fuel burn and cost fields are estimated from the payload if left empty. Add a photo after saving.</p>`}
      <div class="full row"><button class="btn" type="submit">${editCode === "__new" ? "Add type" : "Save type"}</button><button class="btn ghost" type="button" id="typeCancel">Cancel</button></div></form>` : "";
  $("#staffBody").innerHTML = `${form || `<div class="row" style="margin-bottom:14px"><button class="btn" type="button" id="typeNew">Add an aircraft type</button>
      <span class="muted" style="font-size:13px">Retired types can't be booked but stay in logbooks. Types with airframes or logged flights can't be deleted.</span></div>`}
    <div class="table-wrap"><table class="staff-table"><thead><tr><th>Type</th><th>Name</th><th>Sim</th><th>Payload</th><th>Range</th><th>Unlocks at</th><th>Airframes</th><th>Flights</th><th>Status</th><th></th></tr></thead><tbody>
    ${d.types.map(x => `<tr><td><b>${esc(x.code)}</b><br><small class="muted">${esc(x.icao)} · SimBrief ${esc(x.simbrief_type)}${x.simbrief_airframe ? " · custom airframe" : ""}</small></td><td>${esc(x.name)}</td><td>${esc(x.sim || "MSFS")}</td>
      <td>${fmt(x.max_payload_lbs)} lb</td><td>${fmt(x.range_nm)} nm</td><td>${esc(x.unlock_rank_effective)}</td><td>${x.airframes}</td><td>${x.pireps}</td>
      <td>${x.retired ? '<span class="tag grey" style="margin:0">Retired</span>' : '<span class="tag green" style="margin:0">Active</span>'}${x.custom_type ? ' <span class="tag dark">Added</span>' : ""}</td>
      <td style="white-space:nowrap"><button class="btn small" type="button" data-tedit="${x.code}">Edit</button>
        <button class="btn ghost small" type="button" data-tretire="${x.code}" data-r="${x.retired ? 0 : 1}">${x.retired ? "Restore" : "Retire"}</button>
        <button class="btn ghost small" type="button" data-tdel="${x.code}" aria-label="Delete ${esc(x.code)}">×</button></td></tr>`).join("")}</tbody></table></div>`;
  if ($("#typeNew")) $("#typeNew").onclick = () => staffTypes("__new");
  if ($("#typeCancel")) $("#typeCancel").onclick = () => staffTypes();
  document.querySelectorAll("[data-tedit]").forEach(b => b.onclick = () => { staffTypes(b.dataset.tedit); scrollTo({ top: 0, behavior: "smooth" }); });
  document.querySelectorAll("[data-tretire]").forEach(b => b.onclick = async () => {
    const retire = b.dataset.r === "1";
    if (retire && !confirm(`Retire the ${b.dataset.tretire}? It can't be booked until you restore it.`)) return;
    try { await api(`/api/staff/fleet-types/${b.dataset.tretire}/retire`, { method: "POST", body: { retired: retire } }); toast(retire ? "Type retired." : "Type restored."); await refreshCore(); staffTypes(); } catch (e) { toast(e.message); }
  });
  document.querySelectorAll("[data-tdel]").forEach(b => b.onclick = async () => {
    if (!confirm(`Delete the ${b.dataset.tdel} type completely?`)) return;
    try { await api(`/api/staff/fleet-types/${b.dataset.tdel}`, { method: "DELETE" }); toast("Type deleted."); await refreshCore(); staffTypes(); } catch (e) { toast(e.message); }
  });
  const f = $("#typeForm");
  if (f) f.onsubmit = async e => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(f).entries());
    try {
      const r = await api("/api/staff/fleet-types", { method: "POST", body });
      const file = $("#tf_photo")?.files?.[0];
      if (file) { const fd = new FormData(); fd.append("photo", file); await fetch(`/api/fleet/${r.code}/photo`, { method: "POST", body: fd }); }
      toast(r.new ? `${r.code} added. Now add airframes for it in Staff › Airframes.` : `${r.code} saved.`);
      const d2 = await api("/api/bootstrap"); S.fleet = d2.fleet; applyCore(d2); staffTypes();
    } catch (err) { toast(err.message); }
  };
}
const AF_STATUS = ["Available", "Maintenance", "Inspection", "A-check due", "Heavy check due", "Heavy check", "Damaged", "Stored"];
function staffAirframes() {
  const types = fleetCodes();
  $("#staffBody").innerHTML = `<form class="form-card" id="afAdd"><div class="field"><label for="af_reg">Registration</label><input id="af_reg" name="reg" placeholder="N805PC" required></div>
    <div class="field"><label for="af_type">Type</label><select id="af_type" name="type">${types.map(t => `<option value="${t}">${esc(S.fleet[t].name)}</option>`).join("")}</select></div>
    <div class="field"><label for="af_loc">Location (ICAO)</label><input id="af_loc" name="location" value="KCVG" required></div>
    <div class="field" style="align-self:end"><button class="btn" type="submit">Add airframe</button></div></form>
    <div class="table-wrap"><table class="staff-table"><thead><tr><th>Registration</th><th>Type</th><th>Location</th><th>Status</th><th>Hours</th><th>Cycles</th><th>A-check in</th><th>Last flight</th><th></th></tr></thead><tbody>
    ${S.staff.airframes.map(a => `<tr data-reg="${a.reg}"><td><a href="#" data-af-open="${a.reg}" style="color:var(--ink)"><b style="font-family:var(--mono)">${a.reg}</b></a>${a.name ? `<br><small>“${esc(a.name)}” · named by ${esc(a.named_by_name || a.named_by)} <a href="#" data-af-unname="${a.reg}" style="color:var(--red)">remove</a></small>` : ""}${a.note ? `<br><small class="muted">${esc(a.note)}</small>` : ""}</td>
      <td><select data-f="type" aria-label="Type">${fleetCodes(true).map(t => `<option value="${t}" ${t === a.type ? "selected" : ""}>${esc(S.fleet[t].icao)}${S.fleet[t].retired ? " (retired)" : ""}</option>`).join("")}</select></td>
      <td><input data-f="location" value="${a.location}" aria-label="Location" style="width:80px"></td>
      <td>${a.status === "Booked" ? `<span class="tag dark">Booked</span>` : `<select data-f="status" aria-label="Status">${AF_STATUS.map(o => `<option ${o === a.status ? "selected" : ""}>${o}</option>`).join("")}</select>`}</td>
      <td>${esch(a.hours || 0)}</td><td>${a.cycles || 0}</td><td>${esch(Math.max(0, a.check_due_in))} h</td><td>${esc(a.last_flight || "–")}</td>
      <td style="white-space:nowrap">${a.status === "Booked" ? "" : `<button class="btn small" data-af-save="${a.reg}">Save</button> <button class="btn ghost small" data-af-rename="${a.reg}" title="Give this airframe a new registration. Its hours, history and write-ups go with it.">Rename</button> <button class="btn ghost small" data-af-check="${a.reg}" title="Sign off an A-check and return to service">Sign off check</button> <button class="btn ghost small" data-af-del="${a.reg}" aria-label="Remove ${a.reg}">×</button>`}</td></tr>`).join("")}</tbody></table></div>`;
  const save = async (reg, extra = {}) => {
    const tr = document.querySelector(`tr[data-reg="${reg}"]`), body = { reg, ...extra };
    tr.querySelectorAll("[data-f]").forEach(el => body[el.dataset.f] = el.value.toUpperCase ? (el.dataset.f === "location" ? el.value.toUpperCase() : el.value) : el.value);
    Object.assign(body, extra);
    try { S.staff.airframes = await api("/api/staff/airframes", { method: "POST", body }); toast(`${reg} saved.`); staffAirframes(); refreshCore(); } catch (e) { toast(e.message); }
  };
  document.querySelectorAll("[data-af-save]").forEach(b => b.onclick = () => save(b.dataset.afSave));
  document.querySelectorAll("[data-af-unname]").forEach(b => b.onclick = async e => {
    e.preventDefault();
    if (!confirm(`Remove the name from ${b.dataset.afUnname}? The pilot isn't refunded.`)) return;
    try { await api("/api/staff/shop/name", { method: "POST", body: { reg: b.dataset.afUnname } }); toast("Name removed."); loadStaff(); } catch (err) { toast(err.message); }
  });
  document.querySelectorAll("[data-af-open]").forEach(a => a.onclick = e => { e.preventDefault(); openAirframe(a.dataset.afOpen); });
  document.querySelectorAll("[data-af-rename]").forEach(b => b.onclick = async () => {
    const from = b.dataset.afRename, to = (prompt(`New registration for ${from}?\nIts hours, cycles, flight history and write-ups move with it.`) || "").trim().toUpperCase();
    if (!to || to === from) return;
    try {
      const r = await api(`/api/staff/airframes/${encodeURIComponent(from)}/rename`, { method: "POST", body: { to } });
      S.staff.airframes = r.airframes; const m = r.renamed;
      toast(`${m.from} is now ${m.to}${m.flights ? ` · ${m.flights} flight${m.flights === 1 ? "" : "s"} moved` : ""}${m.write_ups ? ` · ${m.write_ups} write-up${m.write_ups === 1 ? "" : "s"} moved` : ""}.`);
      staffAirframes(); refreshCore();
    } catch (e) { toast(e.message); }
  });
  document.querySelectorAll("[data-af-check]").forEach(b => b.onclick = () => save(b.dataset.afCheck, { status: "Available", reset_check: true }));
  document.querySelectorAll("[data-af-del]").forEach(b => b.onclick = async () => {
    if (!confirm(`Remove ${b.dataset.afDel} from the fleet?`)) return;
    try { S.staff.airframes = await api("/api/staff/airframes/" + b.dataset.afDel, { method: "DELETE" }); staffAirframes(); refreshCore(); } catch (e) { toast(e.message); }
  });
  $("#afAdd").onsubmit = async e => {
    e.preventDefault(); const body = Object.fromEntries(new FormData(e.target).entries()); body.location = body.location.toUpperCase();
    if (S.staff.airframes.some(a => a.reg === body.reg.toUpperCase())) { toast("That registration already exists."); return; }
    try { S.staff.airframes = await api("/api/staff/airframes", { method: "POST", body }); toast(`${body.reg.toUpperCase()} added.`); staffAirframes(); refreshCore(); } catch (err) { toast(err.message); }
  };
}
function staffEvents(edit) {
  const e = edit || { id: "", name: "", start: "", end: "", multiplier: 1.25, categories: [], regions: [], airports: [], description: "" };
  const checks = (name, list, sel) => list.map(x => `<label style="display:inline-flex;align-items:center;gap:6px;margin:0 14px 8px 0;font-size:14px;white-space:nowrap"><input type="checkbox" name="${name}" value="${esc(x)}" ${sel.includes(x) ? "checked" : ""} style="accent-color:var(--red);flex:none;width:16px;height:16px;min-height:0;margin:0;padding:0">${esc(x)}</label>`).join("");
  $("#staffBody").innerHTML = `<form class="form-card" id="evForm"><input type="hidden" name="id" value="${esc(e.id)}">
      <div class="field half"><label for="ev_name">Event name</label><input id="ev_name" name="name" value="${esc(e.name)}" required></div>
      <div class="field"><label for="ev_start">Start</label><input id="ev_start" type="date" name="start" value="${e.start}" required></div>
      <div class="field"><label for="ev_end">End</label><input id="ev_end" type="date" name="end" value="${e.end}" required></div>
      <div class="field"><label for="ev_mult">Points multiplier</label><input id="ev_mult" type="number" step="0.05" min="1" max="3" name="multiplier" value="${e.multiplier}"></div>
      <div class="field half"><label for="ev_ap">Airports (ICAO, comma separated; empty = any)</label><input id="ev_ap" name="airports" value="${esc(e.airports.join(", "))}"></div>
      <div class="field full"><label>Categories (none ticked = any)</label><div>${checks("categories", CATEGORY_LIST, e.categories)}</div></div>
      <div class="field full"><label>Regions (none ticked = any)</label><div>${checks("regions", REGION_LIST, e.regions)}</div></div>
      <div class="field full"><label for="ev_desc">Description</label><textarea id="ev_desc" name="description" rows="2">${esc(e.description)}</textarea></div>
      <div class="full row"><button class="btn" type="submit">${e.id ? "Save event" : "Add event"}</button>${e.id ? `<button class="btn ghost" type="button" id="evCancel">Cancel</button>` : ""}</div></form>
    ${S.staff.events.map(ev => `<div class="q-item"><div><b>${esc(ev.name)}</b> <span class="tag dark">×${ev.multiplier}</span>
      <div class="meta">${ev.start} to ${ev.end}${ev.categories.length ? " · " + ev.categories.join(", ") : ""}${ev.regions.length ? " · " + ev.regions.join(", ") : ""}${ev.airports.length ? " · " + ev.airports.join(", ") : ""}</div>
      <p style="margin:4px 0 0">${esc(ev.description)}</p></div>
      <div class="q-actions"><button class="btn ghost small" data-ev-edit="${esc(ev.id)}">Edit</button><button class="btn ghost small" data-ev-del="${esc(ev.id)}">Delete</button></div></div>`).join("")}`;
  $("#evForm").onsubmit = async ev => {
    ev.preventDefault(); const f = ev.target, fd = new FormData(f);
    const body = { id: fd.get("id"), name: fd.get("name"), start: fd.get("start"), end: fd.get("end"), multiplier: Number(fd.get("multiplier")),
      categories: fd.getAll("categories"), regions: fd.getAll("regions"), airports: fd.get("airports").split(/[,\s]+/).filter(Boolean), description: fd.get("description") };
    try { await api("/api/staff/events", { method: "POST", body }); toast("Event saved."); await loadStaff(); refreshCore(); } catch (err) { toast(err.message); }
  };
  if ($("#evCancel")) $("#evCancel").onclick = () => staffEvents();
  document.querySelectorAll("[data-ev-edit]").forEach(b => b.onclick = () => staffEvents(S.staff.events.find(x => x.id === b.dataset.evEdit)));
  document.querySelectorAll("[data-ev-del]").forEach(b => b.onclick = async () => {
    if (!confirm("Delete this event?")) return;
    await api("/api/staff/events/" + encodeURIComponent(b.dataset.evDel), { method: "DELETE" }); loadStaff(); refreshCore();
  });
}
function staffSite() {
  const r = S.staff.rules, st = S.staff.site;
  $("#staffBody").innerHTML = `<div class="two-col" style="align-items:start">
    <section class="panel" style="padding:4px 20px 12px"><h2 style="padding:14px 0 0">Airline rules</h2>
      <label class="switch-row"><input type="checkbox" data-rule="enforce_airframes" ${r.enforce_airframes ? "checked" : ""}><span><b>Airframes must be at the departure airport</b><br><span class="muted" style="font-size:13px">Pilots fly the aircraft that's physically there, or ferry one in first. Off: any available airframe of the type can be used, and it moves to wherever it lands.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="reuse_pilot_ids" ${r.reuse_pilot_ids ? "checked" : ""}><span><b>Reuse pilot IDs <span class="tag amber">Testing</span></b><br><span class="muted" style="font-size:13px">While this is on, a removed pilot's ID is given to the next pilot, so you can test joining over and over. <b>Turn it off before PAC goes live</b>, or a new pilot could inherit an old pilot's ID.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="require_type_ratings" ${r.require_type_ratings ? "checked" : ""}><span><b>Type ratings required</b><br><span class="muted" style="font-size:13px">Pilots need the type rating for an aircraft family before flying it (earned with a short checkride; types already flown count).</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="shop_enabled" ${r.shop_enabled !== false ? "checked" : ""}><span><b>PAC shop open</b><br><span class="muted" style="font-size:13px">Pilots can spend wallet money on patches, frames, jumpseat passes, aircraft repositions and naming rights. Closing it keeps what they've already bought.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="live_map_public" ${r.live_map_public ? "checked" : ""}><span><b>Live map on the public site</b><br><span class="muted" style="font-size:13px">Visitors can watch PAC flights on the live map (flight numbers, aircraft and routes; never pilots' names). Members always see it.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="enforce_pilot_location" ${r.enforce_pilot_location ? "checked" : ""}><span><b>Pilots fly from where they are</b><br><span class="muted" style="font-size:13px">A pilot's location is where their last flight ended. To fly from anywhere else they jumpseat there, paid from their wallet.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="direct_entry_checkrides" ${r.direct_entry_checkrides !== false ? "checked" : ""}><span><b>Direct entry type checkrides</b><br><span class="muted" style="font-size:13px">Experienced pilots can take any type checkride regardless of rank or hours. An accepted passing report unlocks that family for line flights. Rank and pay keep their existing progression rules. Turning this off restores rank-based access.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="require_release_signature" ${r.require_release_signature === true ? "checked" : ""}><span><b>Captain signs the release</b><br><span class="muted" style="font-size:13px">Pilots review and sign the dispatch release (and the NOTOC when dangerous goods are on board) before PAC ACARS will start the flight.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="enforce_ranks" ${r.enforce_ranks ? "checked" : ""}><span><b>Enforce rank limits</b><br><span class="muted" style="font-size:13px">Pilots can only book aircraft their rank has unlocked, and must pass the checkride before flying the line.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="allow_ground_reposition" ${r.allow_ground_reposition ? "checked" : ""}><span><b>Allow ground repositioning</b><br><span class="muted" style="font-size:13px">GSX or slew moves on the ground are logged but not penalized.</span></span></label>
      <h2 style="padding:14px 0 0">Economics</h2>
      <div class="grid2" style="margin:6px 0 10px">
        <div class="field"><label for="ec_fuel">Jet fuel price (USD per gallon)</label><input id="ec_fuel" type="number" step="0.01" min="0.5" max="10" value="${S.settings.fuel_price_gal ?? 2.85}"></div>
        <div class="field"><label for="ec_cap">Starting capital (USD)</label><input id="ec_cap" type="number" step="100000" min="0" value="${S.settings.starting_capital ?? 25000000}"></div>
      </div>
      <button class="btn small" type="button" id="ecSave">Save economics</button>
      <h2 style="padding:14px 0 0">Flying online</h2>
      <p class="muted" style="font-size:13px;margin:4px 0 8px">The ICAO code PAC flights are filed under on VATSIM and IVAO, and in SimBrief. PAC itself is Polar Air Cargo's code, so the networks see PAC flights as ${esc(filingIcao())}9613, spoken “Pagani 9613”. The website keeps showing PAC9613.</p>
      <div class="row" style="align-items:flex-end;gap:10px;margin:0 0 6px"><div class="field" style="margin:0"><label for="filingIcao">Network ICAO code</label><input id="filingIcao" maxlength="3" value="${esc(filingIcao())}" style="width:90px;text-transform:uppercase"></div>
        <button class="btn small" type="button" id="filingSave">Save</button></div>
      <h3 style="margin:14px 0 4px;font-size:15px">VATSIM logo</h3>
      <p class="muted" style="font-size:13px;margin:0 0 8px">VATSIM's virtual airline policy (section 8.4) requires the VATSIM logo on the home page, linked to www.vatsim.net, <b>before</b> you apply, so switch this on when you're getting ready to apply. The home page section is titled "Online networks" and says only that PAC pilots fly there, so it doesn't claim a partnership PAC doesn't have yet. PAC includes the official full-color logo from VATSIM's public logo pack. If VATSIM updates its logo, download the new pack from <a href="https://vats.im/logo" target="_blank" rel="noopener">vats.im/logo</a> and upload the no-tagline version (PNG, WebP or SVG) here.</p>
      <label class="switch-row" style="margin:0 0 8px"><input type="checkbox" id="vatsimShow" ${S.settings?.vatsim_partner_section ? "checked" : ""}><span><b>Show the VATSIM partner section on the home page</b><br><span class="muted" style="font-size:13px">Required by VATSIM before applying.</span></span></label>
      <div class="row" id="netLogoBox" style="align-items:center;gap:12px;margin:0 0 6px"></div>
      <h3 style="margin:14px 0 4px;font-size:15px">IVAO logo</h3>
      <p class="muted" style="font-size:13px;margin:0 0 8px">IVAO asks certified virtual airlines to show the IVAO Virtual Airline logo they provide on the home page, linked to ivao.aero. Upload the file IVAO sends you (PNG, WebP or SVG), then switch the section on once IVAO has accepted PAC. Use it exactly as provided: no recoloring, cropping or added background.</p>
      <label class="switch-row" style="margin:0 0 8px"><input type="checkbox" id="ivaoShow" ${S.settings?.ivao_partner_section ? "checked" : ""}><span><b>Show the IVAO logo on the home page</b><br><span class="muted" style="font-size:13px">Only once IVAO has accepted PAC, or when IVAO asks for it as part of the review.</span></span></label>
      <div class="row" id="ivaoLogoBox" style="align-items:center;gap:12px;margin:0 0 6px"></div>
      <h2 style="padding:14px 0 0">Backups</h2>
      <p class="muted" style="font-size:13px;margin:4px 0 8px">The logbook, roster, airframes, profile and settings are copied automatically every time ACARS starts. The last 14 copies are kept.</p>
      <div id="backupList" class="muted" style="font-size:13px">Loading…</div>
      <div class="row" style="margin:10px 0 6px"><button class="btn small" type="button" id="backupNow">Back up now</button></div>
      <h2 style="padding:14px 0 0">Full backup</h2>
      <p class="muted" style="font-size:13px;margin:4px 0 8px">One file with everything that's yours: logbook, settings, profile and photo, home-page text, fleet edits and photos, gallery and sign-in. Keep a copy somewhere safe, or use it to move PAC to another computer or a server.</p>
      <div class="row" style="margin:0 0 6px"><a class="btn small" href="/api/staff/backup/download" download>Download a full backup</a>
        <label class="btn ghost small" style="cursor:pointer">Restore from a backup…<input type="file" id="restoreFile" accept=".zip" hidden></label></div>
      <h2 style="padding:14px 0 0">Email</h2>
      <p class="muted" style="font-size:13px;margin:4px 0 8px">PAC's own mailbox, so letters come from the airline rather than your personal address. Gmail and Outlook need an <b>app password</b>, not your normal one.</p>
      <div id="mailBox"><span class="muted" style="font-size:13px">Loading…</span></div>
      <h2 style="padding:14px 0 0">SayIntentions.AI</h2>
      <p class="muted" style="font-size:13px;margin:4px 0 8px">PAC is in the SayIntentions.AI Virtual Airline Alliance. With PAC's VA-Link key, each pilot's AI dispatcher, cabin crew and co-pilot are told about their PAC flight whenever they book or change one.</p>
      <div id="siBox"></div>
      <h2 style="padding:14px 0 0">Discord</h2>
      <p class="muted" style="font-size:13px;margin:4px 0 8px">Post departures and arrivals to a Discord channel. In Discord: channel settings › Integrations › Webhooks › New Webhook › Copy Webhook URL, and paste it here.</p>
      <div id="discordBox"><span class="muted" style="font-size:13px">Loading…</span></div>
      <h2 style="padding:14px 0 0">Discord bot</h2>
      <p class="muted" style="font-size:13px;margin:4px 0 8px">PAC Operations, PAC's own bot: <code>/flights</code>, <code>/live</code>, <code>/pilot</code> and <code>/link</code>, rank roles for linked pilots, and posts for accepted PIREPs, promotions, new pilots and shop purchases. It runs on the server next to PAC (see deploy/DEPLOY.md, section 10).</p>
      <div id="botBox"></div>
      <h2 style="padding:14px 0 0">Conflict zones</h2>
      <p class="muted" style="font-size:13px;margin:4px 0 8px">Airspace a US cargo carrier wouldn't fly into or over. <b>Restricted</b>: flights stay on the board, but one that departs from, lands in or is planned to that country is rejected automatically, and one whose track crosses it goes to PIREP review. <b>Caution</b>: allowed, with hazard pay on top of flight pay. The list starts from the FAA's rules for US operators and Russia (closed to US carriers); change any area as the real world changes.</p>
      <div id="zoneBox"><span class="muted" style="font-size:13px">Loading…</span></div>
      <h2 style="padding:14px 0 0">Pagani Aviation Group</h2>
      <p class="muted" style="font-size:13px;margin:4px 0 8px">The group hub reads PAC's roster, hours and Anchorage arrivals from a private feed, and adds each pilot's Pagani Remote Aviation hours. Names, ranks, hours and flights are shared; emails, Discord, network IDs and wallets never are. Tick <b>PRA</b> in Pilots for anyone cleared to fly the Kodiak.</p>
      <div id="groupBox"><span class="muted" style="font-size:13px">Loading…</span></div>
      <h2 style="padding:14px 0 0">Loadsheet to the cockpit (Hoppie's ACARS)</h2>
      <p class="muted" style="font-size:13px;margin:4px 0 8px">PAC Load Control sends the loadsheet to the aircraft as <b>PACLD</b>. Paste PAC's Hoppie logon code here. It's kept on the server only and is never shown again.</p>
      <div id="hoppieBox"><span class="muted" style="font-size:13px">Loading…</span></div>
    </section>
    <form class="panel" id="siteForm" style="padding:4px 20px 18px;display:flex;flex-direction:column;gap:12px"><h2 style="padding:14px 0 0;margin:0">Home page text</h2>
      ${[["tagline", "Headline", 1], ["intro", "Introduction", 3], ["story", "PAC story", 7], ["recruiting", "Recruiting message", 3]].map(([k, l, rows]) =>
        `<div class="field"><label for="site_${k}">${l}</label><textarea id="site_${k}" name="${k}" rows="${rows}" style="width:100%;border:1px solid var(--line);border-radius:3px;padding:8px 10px;font-family:var(--font);font-size:14px">${esc(st[k])}</textarea></div>`).join("")}
      <h2 style="padding:14px 0 0;margin:0">Letters and links</h2>
      <p class="muted" style="font-size:13px;margin:0">Used in the letters PAC writes to applicants and in sign-in links.</p>
      ${[["public_url", "Website address pilots use", "https://fly.paganiaircargo.com"], ["discord_invite", "Discord invite", "https://discord.gg/…"], ["discord_widget", "Discord server ID (live widget on the home page; blank hides it)", "Paste the server ID or Discord's widget code"],
         ["letters_from", "Letters signed by", "Capt. Joseph Pagani"]].map(([k, l, ph]) =>
        `<div class="field"><label for="site_${k}">${l}</label><input id="site_${k}" name="${k}" placeholder="${ph}" value="${esc(st?.[k] || "")}" style="width:100%;border:1px solid var(--line);border-radius:3px;padding:8px 10px;font:inherit;background:var(--white);color:var(--ink)"></div>`).join("")}
      <h2 style="padding:14px 0 0;margin:0">Alliances</h2>
      <label class="field" style="display:flex;flex-direction:row;align-items:center;gap:8px;cursor:pointer"><input type="checkbox" id="site_interline_badge" name="interline_badge" ${st?.interline_badge ? "checked" : ""}> <span>Show the “Founding Member of Interline Freight Partners” badge in the site footer</span></label>
      <div class="row"><button class="btn" type="submit">Save home page and letters</button>
        <button class="btn ghost small" type="button" id="previewAccept">Preview the welcome letter</button></div></form></div>`;
  loadMailBox();
  renderSiBox();
  renderBotBox();
  renderZoneBox();
  loadDiscordBox();
  renderGroupBox();
  if ($("#previewAccept")) $("#previewAccept").onclick = () => openLetter("accepted", { pid: S.me?.id });
  if ($("#restoreFile")) $("#restoreFile").onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    if (!confirm(`Restore PAC from ${f.name}? Everything is replaced with what's in the backup. Your current data is backed up first, so this can be undone.`)) { e.target.value = ""; return; }
    const fd = new FormData(); fd.append("backup", f);
    toast("Restoring…");
    const res = await fetch("/api/staff/backup/restore", { method: "POST", body: fd });
    const r = await res.json().catch(() => ({ error: `Restore failed (HTTP ${res.status}).` }));
    if (!res.ok) { toast(r.error, 9000); e.target.value = ""; return; }
    alert(`Restored. Your previous data was saved as ${r.safety_backup} in the backups list. The page will now reload; you may need to sign in again.`);
    location.reload();
  };
  document.querySelectorAll("[data-rule]").forEach(el => el.onchange = async () => {
    S.settings = await api("/api/settings", { method: "POST", body: { [el.dataset.rule]: el.checked } });
    S.staff.rules[el.dataset.rule] = el.checked; toast("Rule updated.");
  });
  const showBackups = r => { $("#backupList").innerHTML = `<div>Folder: <span style="font-family:var(--mono);font-size:12px">${esc(r.folder)}</span></div>` +
    (r.backups.length ? `<ul style="margin:6px 0 0;padding-left:18px">${r.backups.slice(0, 6).map(b => `<li>${esc(b.name)} · ${fmt(b.size_kb)} KB</li>`).join("")}</ul>${r.backups.length > 6 ? `<div>…and ${r.backups.length - 6} older</div>` : ""}` : "<div>No backups yet.</div>") +
    `<div style="margin-top:6px">To restore, close ACARS and copy the files from a backup folder back into <span style="font-family:var(--mono);font-size:12px">data</span>.</div>`; };
  api("/api/staff/backups").then(showBackups).catch(() => {});
  const drawNetLogo = (url, uploaded) => {
    $("#netLogoBox").innerHTML = (url ? `<span class="net-logo" style="padding:10px 16px"><img src="${esc(url)}" alt="VATSIM" style="height:40px"></span>
        <span class="muted" style="font-size:13px">${uploaded ? "Your uploaded file" : "Built in"}</span>` : "")
      + `<label class="btn ghost small" style="cursor:pointer">Replace<input type="file" id="netLogoFile" accept="image/png,image/webp,image/svg+xml" hidden></label>`
      + (uploaded ? `<button class="btn ghost small" type="button" id="netLogoDel">Use the built-in logo</button>` : "");
    $("#netLogoFile").onchange = async e => {
      const file = e.target.files[0]; if (!file) return;
      const fd = new FormData(); fd.append("file", file);
      try { const r = await fetch("/api/staff/network-logo", { method: "POST", body: fd }); const d = await r.json(); if (!r.ok) throw new Error(d.error);
        drawNetLogo(d.logos.vatsim, true); toast("VATSIM logo replaced. It's now on the home page."); } catch (err) { toast(err.message); }
    };
    if ($("#netLogoDel")) $("#netLogoDel").onclick = async () => {
      if (!confirm("Go back to the built-in VATSIM logo?")) return;
      drawNetLogo((await api("/api/staff/network-logo", { method: "DELETE" })).logos.vatsim, false); toast("Back to the built-in VATSIM logo.");
    };
  };
  const drawIvaoLogo = url => {
    $("#ivaoLogoBox").innerHTML = (url ? `<span class="net-logo" style="padding:10px 16px"><img src="${esc(url)}" alt="IVAO" style="height:40px"></span>` : `<span class="muted" style="font-size:13px">No IVAO logo uploaded yet.</span>`)
      + `<label class="btn ghost small" style="cursor:pointer">${url ? "Replace" : "Upload the IVAO logo"}<input type="file" id="ivaoLogoFile" accept="image/png,image/webp,image/svg+xml" hidden></label>`
      + (url ? `<button class="btn ghost small" type="button" id="ivaoLogoDel">Remove</button>` : "");
    $("#ivaoLogoFile").onchange = async e => {
      const file = e.target.files[0]; if (!file) return;
      const fd = new FormData(); fd.append("file", file);
      try { const r = await fetch("/api/staff/network-logo?net=ivao", { method: "POST", body: fd }); const d = await r.json(); if (!r.ok) throw new Error(d.error);
        drawIvaoLogo(d.logos.ivao); toast("IVAO logo uploaded."); } catch (err) { toast(err.message); }
    };
    if ($("#ivaoLogoDel")) $("#ivaoLogoDel").onclick = async () => {
      if (!confirm("Remove the IVAO logo?")) return;
      drawIvaoLogo((await api("/api/staff/network-logo?net=ivao", { method: "DELETE" })).logos.ivao); toast("IVAO logo removed.");
    };
  };
  api("/api/va/home").then(h => { drawNetLogo(h.network_logos?.vatsim, h.network_logos?.vatsim_uploaded); drawIvaoLogo(h.network_logos?.ivao); }).catch(() => { drawNetLogo(null); drawIvaoLogo(null); });
  $("#ivaoShow").onchange = async e => {
    try { S.settings = await api("/api/settings", { method: "POST", body: { ivao_partner_section: e.target.checked } });
      toast(e.target.checked ? "The IVAO logo is on the home page (once uploaded)." : "The IVAO logo is hidden."); }
    catch (err) { e.target.checked = !e.target.checked; toast(err.message); }
  };
  $("#vatsimShow").onchange = async e => {
    try { S.settings = await api("/api/settings", { method: "POST", body: { vatsim_partner_section: e.target.checked } });
      toast(e.target.checked ? "The VATSIM partner section is on the home page." : "The VATSIM partner section is hidden."); }
    catch (err) { e.target.checked = !e.target.checked; toast(err.message); }
  };
  $("#filingSave").onclick = async () => {
    const code = $("#filingIcao").value.trim().toUpperCase();
    if (!/^[A-Z]{3}$/.test(code)) { toast("The network code is three letters, like PGI."); return; }
    try { S.settings = await api("/api/settings", { method: "POST", body: { filing_icao: code } }); toast(`PAC flights now file as ${code} on VATSIM and IVAO.`); }
    catch (e) { toast(e.message); }
  };
  $("#ecSave").onclick = async () => {
    S.settings = await api("/api/settings", { method: "POST", body: { fuel_price_gal: Number($("#ec_fuel").value) || 2.85, starting_capital: Number($("#ec_cap").value) || 0 } });
    toast("Economics saved. New prices apply to flights filed from now on.");
  };
  $("#backupNow").onclick = async () => { try { const r = await api("/api/staff/backups", { method: "POST" }); showBackups(r); toast("Backup saved."); } catch (e) { toast(e.message); } };
  const hoppieBox = async () => {
    const h = await api("/api/staff/hoppie").catch(() => ({}));
    $("#hoppieBox").innerHTML = `<div class="row" style="gap:8px;align-items:center;flex-wrap:wrap"><span class="tag ${h.configured ? "green" : "amber"}">${h.configured ? "Connected" : "Not set up"}</span>
      <input type="password" id="hoppieCode" autocomplete="off" placeholder="${h.configured ? "Paste a new code to replace it" : "Hoppie logon code"}" style="max-width:260px">
      <button class="btn small" type="button" id="hoppieSave">Save</button>${h.configured ? `<button class="btn ghost small" type="button" id="hoppieClear">Turn off</button>` : ""}</div>`;
    $("#hoppieSave").onclick = async () => { try { await api("/api/staff/hoppie", { method: "POST", body: { logon: $("#hoppieCode").value } }); toast("Saved."); hoppieBox(); } catch (err) { toast(err.message); } };
    if ($("#hoppieClear")) $("#hoppieClear").onclick = async () => { await api("/api/staff/hoppie", { method: "POST", body: { logon: "" } }); hoppieBox(); };
  };
  if ($("#hoppieBox")) hoppieBox();
  $("#siteForm").onsubmit = async e => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.target).entries());
    body.interline_badge = $("#site_interline_badge").checked;   // checkboxes are absent from FormData when off; send the real state
    S.staff.site = await api("/api/staff/site", { method: "POST", body }); toast("Home page updated.");
  };
}

/* ---------------- Fleet ---------------- */
/* PAC's fleet divisions (Feeder, Mainline, Heavy, Heritage): the server labels each type */
const DIVISION_FALLBACK = [{ name: "PAC Feeder", short: "Feeder" }, { name: "PAC Mainline", short: "Mainline" }, { name: "PAC Heavy", short: "Heavy" }, { name: "PAC Heritage", short: "Heritage" }];
const divisions = () => (S.divisions && S.divisions.length ? S.divisions : DIVISION_FALLBACK);
const divOf = code => S.fleet?.[code]?.division || "";
const divShort = name => (divisions().find(d => d.name === name) || {}).short || String(name || "").replace(/^PAC\s+/, "");
const FLEET_ORDER = ["B738F", "B722F", "A306F", "MD11F", "B77F", "B748F", "B732F", "B733F", "B752F", "B763F", "B742F"];
const simTag = a => a?.sim && a.sim !== "MSFS" ? `<span class="tag ${a.sim === "X-Plane" ? "dark" : "grey"}" style="margin-left:6px">${esc(a.sim)}</span>` : "";
const NUM_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen"];
S.fleetSim = "All";
const tonnes = lb => (lb / 2204.62).toFixed(1);
async function loadFleet() {
  try {
    const [r] = await Promise.all([api("/api/fleet"), refreshCore()]);
    S.fleet = r.fleet; S.fleetStats = r.stats; S.liveries = r.liveries || []; S.discordInvite = r.discord_invite || ""; S.liveryMaxMb = r.livery_max_mb;
    renderFleet();
  } catch (e) { toast(e.message); }
}
function fleetCodes(includeRetired = false) {
  const all = [...FLEET_ORDER.filter(k => S.fleet[k]), ...Object.keys(S.fleet).filter(k => !FLEET_ORDER.includes(k))];
  return includeRetired ? all : all.filter(k => !S.fleet[k].retired);
}
function simCount(sim) { return Object.values(S.fleet).filter(a => (a.sim || "MSFS").includes(sim)).length; }
function aogBoard() {
  const list = (S.airframes || []).filter(a => a.aog);
  if (!list.length) return "";
  const when = t => t ? new Date(t * 1000).toISOString().slice(5, 16).replace("T", " ") + "Z" : "–";
  const step = (a, n) => { const st = a.aog.status === "repairing" ? 2 : 1; return n < st ? "done" : n === st ? "now" : ""; };
  return `<section class="aog-board" aria-label="Aircraft on ground">
    <h2>🔧 Aircraft on ground</h2>
    <p class="muted">Grounded away from maintenance. Fly the recovery mission to get the parts and engineers there: the aircraft returns to service when the repair is done.</p>
    ${list.map(a => { const g = a.aog; return `<div class="aog-card">
      <div class="aog-top"><b>${esc(a.reg)}</b> <span class="muted">${esc(S.fleet[a.type]?.name || a.type)} · at ${esc(g.station)}</span><span class="aog-title">${esc(g.title)}</span></div>
      <ol class="aog-steps"><li class="done">Grounded after ${esc(g.cause_flight || "its last flight")}</li>
        <li class="${step(a, 1)}">${g.status === "awaiting_parts" ? (g.contractor ? `Contractor flying ${fmt(g.weight_lbs)} lb of parts in, due ${when(g.parts_due)}` : `Waiting for ${fmt(g.weight_lbs)} lb of parts and the ${esc(g.team || "engineers")} from ${esc(g.hub)}`) : "Parts and engineers on site"}</li>
        <li class="${step(a, 2)}">${g.status === "repairing" ? `Repair under way, back in service about ${when(g.repair_until)}` : "Repair"}</li>
        <li>Back in service</li></ol>
      ${g.status === "awaiting_parts" && g.mission_id && !g.contractor ? `<button class="btn small" onclick="show('missions')">Fly recovery mission ${esc(g.mission_id)} →</button>` : ""}
    </div>`; }).join("")}
  </section>`;
}
function renderFleet() {
  const all = fleetCodes(), st = S.fleetStats || {};
  const divNames = divisions().map(d => d.name);
  const bySim = S.fleetSim === "All" ? all : all.filter(k => (S.fleet[k].sim || "MSFS").includes(S.fleetSim));
  const codes = (S.fleetDiv ? bySim.filter(k => divOf(k) === S.fleetDiv) : bySim)
    .sort((a, b) => (divNames.indexOf(divOf(a)) + 99) % 99 - (divNames.indexOf(divOf(b)) + 99) % 99);
  const flights = codes.reduce((a, k) => a + (st[k]?.flights || 0), 0), hours = codes.reduce((a, k) => a + (st[k]?.block_hours || 0), 0);
  const longest = codes.reduce((a, k) => S.fleet[k].range_nm > S.fleet[a].range_nm ? k : a, codes[0]);
  const heaviest = codes.reduce((a, k) => S.fleet[k].max_payload_lbs > S.fleet[a].max_payload_lbs ? k : a, codes[0]);
  $("#fleetRoot").innerHTML = `
  <div class="fleet-head">
    <div><h1>The fleet</h1><p class="muted" style="margin:6px 0 0">${NUM_WORDS[all.length] ? NUM_WORDS[all.length][0].toUpperCase() + NUM_WORDS[all.length].slice(1) : all.length} freighter types, from a gravel-kit 737-200 to the nose-loading 747s.</p>${liveryCredits()}
      <div class="filters" style="margin-top:12px">${[["All", all.length], ["MSFS", simCount("MSFS")], ["X-Plane", simCount("X-Plane")]].map(([k, n]) => `<button class="chip" data-fsim="${k}" aria-pressed="${S.fleetSim === k}">${k === "All" ? "Whole fleet" : k} (${n})</button>`).join("")}</div>
      <div class="filters" style="margin-top:8px" aria-label="Divisions"><button class="chip" data-fdiv="" aria-pressed="${!S.fleetDiv}">All divisions</button>${divisions().map(d => `<button class="chip" data-fdiv="${esc(d.name)}" aria-pressed="${S.fleetDiv === d.name}">${esc(d.short)} (${bySim.filter(k => divOf(k) === d.name).length})</button>`).join("")}</div></div>
    <div class="fleet-sum">
      <div><span>Aircraft types</span><b>${all.length}</b></div>
      <div><span>Heaviest payload</span><b>${tonnes(S.fleet[heaviest].max_payload_lbs)} t</b></div>
      <div><span>Longest range</span><b>${fmt(S.fleet[longest].range_nm)} nm</b></div>
      <div><span>Fleet flights / hours</span><b>${fmt(flights)} / ${esch(hours)}</b></div>
    </div>
  </div>
  ${aogBoard()}
  <nav class="fleet-jump" aria-label="Jump to aircraft">${codes.map(k => `<a href="#ac-${k}" data-jump="${k}"><img src="${esc(displayPhoto(S.fleet[k].thumb || S.fleet[k].photo, 400))}" alt="" loading="lazy"><span>${esc(S.fleet[k].icao)}${S.fleet[k].sim === "X-Plane" ? ' <span class="tag dark" style="font-size:10px;padding:1px 5px">XP</span>' : ""}<small>${esc(S.fleet[k].name)}</small></span></a>`).join("")}</nav>
  ${codes.map((k, i) => (i === 0 || divOf(k) !== divOf(codes[i - 1]) ? divisionHead(divOf(k)) : "") + fleetSheet(k)).join("") || `<p class="muted">No aircraft in that division for this simulator.</p>`}
  ${fleetCodes(true).some(k => S.fleet[k].retired) ? `<p class="muted" style="font-size:14px">Retired from the fleet: ${fleetCodes(true).filter(k => S.fleet[k].retired).map(k => esc(S.fleet[k].name)).join(", ")}. Past flights on these types stay in the logbook.</p>` : ""}`;
  document.querySelectorAll("#fleetRoot [data-af]").forEach(b => { b.onclick = () => openAirframe(b.dataset.af); b.onkeydown = e => { if (e.key === "Enter") openAirframe(b.dataset.af); }; });
  document.querySelectorAll("[data-fsim]").forEach(b => b.onclick = () => { S.fleetSim = b.dataset.fsim; renderFleet(); });
  document.querySelectorAll("[data-fdiv]").forEach(b => b.onclick = () => { S.fleetDiv = b.dataset.fdiv; renderFleet(); });
  document.querySelectorAll("[data-jump]").forEach(a => a.onclick = e => { e.preventDefault(); $("#ac-" + a.dataset.jump).scrollIntoView({ behavior: "smooth" }); });
  document.querySelectorAll("[data-zoom]").forEach(b => b.onclick = () => { const a = S.fleet[b.dataset.zoom]; $("#photoBig").src = a.photo; $("#photoBig").alt = a.name; $("#photoCap").textContent = `${a.name}${a.registrations?.length ? " · " + a.registrations.join(", ") : ""}`; $("#photoDlg").showModal(); });
  document.querySelectorAll("[data-routes]").forEach(b => b.onclick = () => { S.board = "network"; S.acFilter = b.dataset.routes; S.region = "All"; S.netSearch = ""; S.selected = null; show("missions"); });
  document.querySelectorAll("[data-charter]").forEach(b => b.onclick = () => {
    S.charterSpec = { ...(S.charterSpec || { origin: "", destination: "", payload_lbs: "", cargo: "General cargo", priority: "Standard", flight_number: "", _o: null, _d: null }), aircraft: b.dataset.charter };
    S.board = "charter"; S.selected = S.charterMission || null; show("missions");
  });
  document.querySelectorAll("[data-edit-ac]").forEach(b => b.onclick = () => { S.editingAc = b.dataset.editAc; renderFleet(); $("#ac-" + S.editingAc).scrollIntoView({ block: "nearest" }); });
  if (S.editingAc) bindFleetEdit(S.editingAc);
  bindLiveries();
}
function divisionHead(name) {
  const d = divisions().find(x => x.name === name);
  return d ? `<div class="div-head" id="div-${esc(d.short.toLowerCase())}"><h2>${esc(d.name)}</h2>${d.blurb ? `<p class="muted">${esc(d.blurb)}</p>` : ""}</div>` : "";
}
function fleetSheet(k) {
  const a = S.fleet[k], st = S.fleetStats?.[k] || {}, editing = S.editingAc === k;
  return `<article class="ac-sheet" id="ac-${k}">
    <div class="ac-top">
      <button class="ac-photo" data-zoom="${k}" aria-label="Enlarge photo of the ${esc(a.name)}"><img src="${esc(displayPhoto(a.photo))}" alt="Pagani Air Cargo ${esc(a.name)}" loading="lazy"><span class="code">${esc(a.icao)}</span></button>
      <div class="ac-info">
        <div class="ac-div">${esc(a.division || "PAC")} · ${esc(a.sim || "MSFS")}</div>
        <h2 class="ac-name">${esc(a.name)}</h2>
        <div class="ac-role">${esc(a.role || "")}</div>
        <p class="ac-desc">${esc(a.description || "")}</p>
        <div class="regs">${(S.airframes || []).filter(x => x.type === k).length} airframes in the fleet</div>
        <div class="ac-actions">
          <button class="btn small" data-routes="${k}">See its ${st.routes || 0} scheduled routes</button>
          <button class="btn ghost small" data-charter="${k}">Charter this aircraft</button>
          ${S.me?.staff ? `<button class="btn ghost small" data-edit-ac="${k}" ${editing ? "hidden" : ""}>Edit</button>` : ""}
        </div>
      </div>
    </div>
    <div class="spec-grid">
      <div><span>Max payload</span><b>${fmt(a.max_payload_lbs)} lb</b><small>${tonnes(a.max_payload_lbs)} t</small></div>
      <div><span>Max takeoff weight</span><b>${fmt(a.mtow_lbs)} lb</b><small>${tonnes(a.mtow_lbs)} t</small></div>
      <div><span>Typical range</span><b>${fmt(a.range_nm)} nm</b><small>with a typical load</small></div>
      <div><span>Cruise</span><b>Mach ${a.mach ?? "–"}</b><small>about ${a.cruise_ktas} kt true</small></div>
      <div><span>Runway needed</span><b>${fmt(a.min_rwy_ft)} ft</b><small>typical at heavy weights</small></div>
      <div><span>Engines</span><b>${esc(a.engines || "–")}</b></div>
      <div><span>Flight crew</span><b>${esc(a.crew || "–")}</b></div>
      <div><span>Main deck</span><b>${esc(a.main_deck || "–")}</b></div>
      <div><span>Type in service since</span><b>${a.entered_service || "–"}</b></div>
      <div><span>Simulator</span><b>${esc(a.sim || "MSFS")}</b><small>${a.sim_model ? esc(a.sim_model) + " · " : ""}SimBrief ${esc(a.simbrief_type)}</small></div>
    </div>
    <div class="af-list">${(S.airframes || []).filter(x => x.type === k).map(x => `<span class="af-chip ${["Maintenance", "Inspection", "A-check due", "Heavy check due", "Heavy check", "Damaged"].includes(x.status) ? "grounded" : x.status === "Booked" ? "booked" : ""}" data-af="${x.reg}" role="button" tabindex="0" title="Open ${x.reg}'s history"><b>${x.reg}</b> at ${x.location} · ${esc(reservationSummary(x))} · ${esch(x.hours || 0)} h, ${x.cycles || 0} cycles${(x.open_items || []).length ? ` <span class="af-mx">${x.open_items.length} MX</span>` : ""}${x.aog ? ` <span class="af-mx" style="background:#b00000;color:#fff">AOG</span>` : ""}</span>`).join("") || `<span class="muted" style="font-size:13px">No airframes. Add them in Staff › Airframes.</span>`}</div>
    ${liverySection(k)}
    <div class="ac-stats">
      <div><span>PAC flights</span><b>${fmt(st.flights)}</b></div>
      <div><span>Block hours</span><b>${esch(st.block_hours || 0)}</b></div>
      <div><span>Cargo flown</span><b>${fmt(st.cargo_lbs)} lb</b></div>
      <div><span>Average landing</span><b>${st.avg_landing != null ? st.avg_landing + " fpm" : "–"}</b></div>
      <div><span>Last flown</span><b>${st.last_flown ? new Date(st.last_flown * 1000).toISOString().substr(0, 10) : "–"}</b></div>
    </div>
    ${editing ? `<form class="ac-edit" id="acEdit" autocomplete="off">
      <div class="field"><label for="ae_div">Division</label><select id="ae_div" name="division">${divisions().map(d => `<option ${d.name === a.division ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select></div>
      <div class="field"><label for="ae_role">Role</label><input id="ae_role" name="role" value="${esc(a.role || "")}"></div>
      <div class="field full"><label for="ae_desc">Description</label><textarea id="ae_desc" name="description" rows="4">${esc(a.description || "")}</textarea></div>
      <div class="field"><label for="ae_eng">Engines</label><input id="ae_eng" name="engines" value="${esc(a.engines || "")}"></div>
      <div class="field"><label for="ae_crew">Flight crew</label><input id="ae_crew" name="crew" value="${esc(a.crew || "")}"></div>
      <div class="field"><label for="ae_deck">Main deck</label><input id="ae_deck" name="main_deck" value="${esc(a.main_deck || "")}"></div>
      <div class="field"><label for="ae_sim">Simulator</label><select id="ae_sim" name="sim">${["MSFS", "X-Plane", "MSFS and X-Plane"].map(o => `<option ${o === (a.sim || "MSFS") ? "selected" : ""}>${o}</option>`).join("")}</select></div>
      <div class="field"><label for="ae_simmodel">Add-on aircraft</label><input id="ae_simmodel" name="sim_model" value="${esc(a.sim_model || "")}" placeholder="e.g. iniBuilds A300-600R(F)"></div>
      <div class="field full row">
        <label class="btn ghost small" for="ae_photo">Change photo</label><input type="file" id="ae_photo" accept="image/png,image/jpeg,image/webp" hidden>
        <button class="btn ghost small" type="button" id="ae_photo_reset">Use original photo</button>
        <span style="flex:1"></span>
        <button class="btn ghost" type="button" id="ae_cancel">Cancel</button>
        <button class="btn" type="submit">Save</button>
      </div>
    </form>` : ""}
  </article>`;
}
function bindFleetEdit(k) {
  const f = $("#acEdit"); if (!f) return;
  f.onsubmit = async e => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(f).entries());
    try { S.fleet[k] = await api("/api/fleet/" + k, { method: "POST", body }); S.editingAc = null; renderFleet(); toast(`${S.fleet[k].name} saved.`); }
    catch (err) { toast(err.message); }
  };
  $("#ae_cancel").onclick = () => { S.editingAc = null; renderFleet(); };
  $("#ae_photo").onchange = async e => {
    const file = e.target.files[0]; if (!file) return;
    const fd = new FormData(); fd.append("photo", file);
    try {
      const res = await fetch(`/api/fleet/${k}/photo`, { method: "POST", body: fd }); const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      S.fleet[k] = d; renderFleet(); toast("Photo updated.");
    } catch (err) { toast(err.message); }
  };
  $("#ae_photo_reset").onclick = async () => { S.fleet[k] = await api(`/api/fleet/${k}/photo`, { method: "DELETE" }); renderFleet(); toast("Original photo restored."); };
}

/* ---------------- Pilots: the roster and other pilots' profiles ---------------- */
function openPilot(pid) { S.pilotOpen = pid; show("pilots"); }
async function loadPilots(pid) {
  const root = $("#pilotsRoot");
  if (pid) return renderPilotPage(pid);
  root.innerHTML = `<div class="profile-bar"><h1>Pilots</h1></div><p class="muted">Loading the roster…</p>`;
  try { S.pilots = (await api("/api/pilots")).pilots; } catch (e) { root.innerHTML = `<div class="profile-bar"><h1>Pilots</h1></div><p class="muted">${esc(e.message)}</p>`; return; }
  renderRoster();
}
const ROSTER_SORTS = [["hours", "Most hours"], ["flights", "Most flights"], ["recent", "Flown recently"], ["joined", "Newest"], ["id", "Pilot ID"]];
function renderRoster() {
  const all = S.pilots || [], q = (S.pilotQ || "").trim().toLowerCase(), sort = S.pilotSort || "hours";
  const shown = all.filter(p => S.pilotInactive || p.status !== "Inactive")
    .filter(p => !q || [p.name, p.pilot_id, p.rank, p.base, p.location, p.country].join(" ").toLowerCase().includes(q));
  const by = { hours: (a, b) => b.hours - a.hours, flights: (a, b) => b.flights - a.flights, recent: (a, b) => (b.last_flight || 0) - (a.last_flight || 0),
               joined: (a, b) => (b.joined || 0) - (a.joined || 0), id: (a, b) => a.pilot_id.localeCompare(b.pilot_id) }[sort];
  shown.sort((a, b) => by(a, b) || a.pilot_id.localeCompare(b.pilot_id));
  const active = all.filter(p => p.status === "Active").length, hours = all.reduce((s, p) => s + (p.hours || 0), 0);
  const inactive = all.filter(p => p.status === "Inactive").length;
  const when = t => t ? new Date(t * 1000).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" }) : "–";
  $("#pilotsRoot").innerHTML = `
  <div class="profile-bar"><h1>Pilots</h1><span class="muted">${fmt(active)} active ${active === 1 ? "pilot" : "pilots"} · ${esch(hours)} hours between them</span></div>
  <div class="roster-tools">
    <input type="search" id="pilotQ" placeholder="Search by name, ID, rank or airport" value="${esc(S.pilotQ || "")}" aria-label="Search pilots">
    <div class="filters" role="group" aria-label="Sort pilots">${ROSTER_SORTS.map(([k, l]) => `<button class="chip" type="button" data-psort="${k}" aria-pressed="${sort === k}">${l}</button>`).join("")}</div>
    ${inactive ? `<label class="roster-inact"><input type="checkbox" id="pilotInact" ${S.pilotInactive ? "checked" : ""}> Show inactive (${inactive})</label>` : ""}
  </div>
  ${shown.length ? `<div class="table-wrap roster-wrap"><table class="roster-table">
    <thead><tr><th>Pilot</th><th>Rank</th><th class="num">Hours</th><th class="num">Flights</th><th class="num">Avg score</th><th>Base</th><th>Now at</th><th>Last flight</th></tr></thead>
    <tbody>${shown.map(p => `<tr data-pilot-open="${esc(p.pilot_id)}" tabindex="0" aria-label="Open ${esc(p.name)}'s profile">
      <td><div class="roster-who"><img src="${esc(p.photo)}" alt="" loading="lazy"><div><b>${esc(p.name)}</b>${p.staff ? ' <span class="tag dark">Staff</span>' : ""}<small>${esc(p.pilot_id)}${p.status !== "Active" ? " · " + esc(p.status) : ""}${p.country ? " · " + esc(p.country) : ""}</small></div></div></td>
      <td><div class="roster-rank">${rankImg(p.rank)}<span>${esc(p.rank)}</span></div></td>
      <td class="num">${esch(p.hours || 0)}</td><td class="num">${fmt(p.flights)}</td><td class="num">${p.avg_score ?? "–"}</td>
      <td>${esc(p.base || "–")}</td><td>${esc(p.location || "–")}</td><td>${when(p.last_flight)}</td></tr>`).join("")}</tbody>
  </table></div>` : `<div class="empty">No pilots match “${esc(S.pilotQ || "")}”.</div>`}`;
  const qEl = $("#pilotQ");
  qEl.oninput = () => { S.pilotQ = qEl.value; const at = qEl.selectionStart; renderRoster(); const n = $("#pilotQ"); n.focus(); n.setSelectionRange(at, at); };
  document.querySelectorAll("[data-psort]").forEach(b => b.onclick = () => { S.pilotSort = b.dataset.psort; renderRoster(); });
  if ($("#pilotInact")) $("#pilotInact").onchange = e => { S.pilotInactive = e.target.checked; renderRoster(); };
  document.querySelectorAll("[data-pilot-open]").forEach(tr => {
    tr.onclick = () => openPilot(tr.dataset.pilotOpen);
    tr.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openPilot(tr.dataset.pilotOpen); } };
  });
}
async function renderPilotPage(pid) {
  const root = $("#pilotsRoot");
  root.innerHTML = `<div class="profile-bar"><h1>Pilot</h1></div><p class="muted">Loading…</p>`;
  let d; try { d = await api("/api/pilots/" + encodeURIComponent(pid)); }
  catch (e) { root.innerHTML = `<div class="profile-bar"><button class="btn ghost small" type="button" id="backRoster">← All pilots</button></div><p class="muted">${esc(e.message)}</p>`;
              $("#backRoster").onclick = () => { S.pilotOpen = null; show("pilots"); }; return; }
  if (S.pilotOpen !== pid) return;                      // they've moved on while this loaded
  const p = d.profile, c = d.career, t = d.stats.totals, mine = d.you;
  const since = p.member_since ? new Date(p.member_since + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "long", year: "numeric" }) : "–";
  const ratings = [...new Map((p.type_ratings || []).filter(r => r.status !== "Inactive").map(r => [r.type, r])).values()];
  root.innerHTML = `
  <div class="profile-bar"><button class="btn ghost small" type="button" id="backRoster">← All pilots</button>
    <div class="row">${mine ? `<button class="btn ghost small" type="button" onclick="show('profile')">Edit my profile</button>` : ""}</div></div>
  <article class="crew-card">
    <div class="crew-photo">
      <img src="${esc(p.photo || "/static/pilot-photo-default.svg")}" alt="Portrait of ${esc(p.name)}" class="${frameCls(p.flair)}">
      <div class="profile-rank-block">${c.rank ? rankImg(c.rank) : `<img class="wm" src="/static/pac-wordmark-white.png" alt="">`}<span class="profile-rank-caption">${esc(c.rank || p.rank || "PAC pilot")}</span><span class="profile-pilot-id">${esc(p.pilot_id)}</span></div>
    </div>
    <div class="crew-main">
      <div class="crew-rank">${esc(c.rank)} · ${esc(p.pilot_id)}${d.staff ? ' · <span class="tag dark">Staff</span>' : ""}${d.status !== "Active" ? ` · <span class="status-pill off">${esc(d.status)}</span>` : ""}</div>
      <h2 class="crew-name">${esc(p.name)}</h2>
      <div class="crew-title">${esc(p.title || "PAC line pilot")}</div>
      ${(p.roles || []).length ? `<div class="crew-roles">${p.roles.map(r => `<span class="role-chip">${esc(r)}</span>`).join("")}</div>` : ""}
      ${patchStrip(p.flair, 44)}${campaignPatchShelf(p.flair)}${publicShelf(p.flair)}
      ${p.bio ? `<p class="crew-bio">${esc(p.bio)}</p>` : ""}
      <div class="crew-facts">
        <div><span>Home base</span><b>${esc(p.base) || "–"}</b></div>
        <div><span>Now at</span><b>${esc(d.location) || "–"}</b></div>
        ${d.country ? `<div><span>Country</span><b>${esc(d.country)}</b></div>` : ""}
        <div><span>With Pagani Air Cargo since</span><b>${since}</b></div>
        <div><span>Total hours</span><b class="num">${esch(c.hours || 0)}</b></div>
        <div><span>Checkride</span><b>${esc(c.checkride || "Pending")}</b></div>
      </div>
      ${ratings.length ? `<div class="endorse"><span class="lbl">Type ratings</span>${ratings.map(r => `<b title="${esc(r.name)}">${esc(r.type)}</b>`).join("")}</div>` : ""}
    </div>
  </article>
  ${(S.me?.staff || mine) && (p.type_ratings || []).length ? `<section class="panel" style="margin:0 0 24px">
      <h2>Type ratings${mine ? "" : ' <span class="tag grey">Staff view</span>'}</h2>
      <p class="panel-sub">PAC hours come from accepted PIREPs on every aircraft in the rating's family (checkrides that didn't pass don't count). Recency counts PAC landings in the last 90 days.</p>
      <div class="table-wrap" style="border:0"><table class="ratings">
        <thead><tr><th>Type</th><th>Aircraft</th><th>Issued</th><th class="num">PAC hrs</th><th class="num">Prior hrs</th><th class="num">Total</th><th>Recency</th><th>Status</th></tr></thead>
        <tbody>${p.type_ratings.map(r => { const h = ratingHours(r, d.stats); return `<tr>
          <td><span class="rt-code">${esc(r.type)}</span></td>
          <td><div class="rt-name">${esc(r.name)}</div>${r.notes ? `<div class="rt-notes">${esc(r.notes)}</div>` : ""}</td>
          <td style="white-space:nowrap">${r.issued ? esc(r.issued) : "–"}</td>
          <td class="num">${esch(h.pac)}</td><td class="num">${esch(h.prior)}</td><td class="num"><b>${esch(h.total)}</b></td>
          <td>${recencyHtml(h, r)}</td>
          <td><span class="status-pill ${r.status === "Active" ? "" : "off"}">${esc(r.status || "Active")}</span></td></tr>`; }).join("")}</tbody></table></div>
    </section>` : ""}
  <section class="panel crewid-panel crewid-public">
    <h2>Crew badge</h2>
    <p class="panel-sub">${esc(p.name)}'s PAC airport identification. Click it to turn it over.</p>
    ${badgeHtml(p, c, d.staff, { own: mine })}
  </section>
  <div class="pilot-grid">
    <section class="panel">
      <h2>Career with PAC</h2>
      <div class="career">
        <div><span>Flights</span><b>${fmt(t.flights)}</b></div>
        <div><span>Block hours</span><b>${esch(t.block_hours || 0)}</b></div>
        <div><span>Cargo delivered</span><b>${fmt(t.cargo_lbs)} lb</b></div>
        <div><span>Distance flown</span><b>${fmt(t.distance_nm)} nm</b></div>
        <div><span>Average score</span><b>${t.avg_score ?? "–"}</b></div>
        <div><span>Best landing</span><b>${t.best_landing != null ? t.best_landing + " fpm" : "–"}</b></div>
        <div><span>Airports visited</span><b>${fmt(d.collection.airports)}</b></div>
        <div><span>Countries</span><b>${fmt(d.collection.countries)}</b></div>
      </div>
    </section>
    <section class="panel">
      <h2>Recent flights</h2>
      ${d.stats.recent.length ? `<ul class="recent pilot-recent">${d.stats.recent.map(r => `<li ${S.me?.staff || mine ? `data-pirep-open="${r.id}" tabindex="0" class="clickable"` : ""}>
          <b>${esc(r.flight_number)}</b><span>${esc(r.dep)} – ${esc(r.arr)} · ${esc(S.fleet[r.aircraft]?.icao || r.aircraft)}<small>${new Date(r.filed_at * 1000).toLocaleDateString("en-US", { day: "numeric", month: "short" })}${r.landing_rate != null ? ` · ${r.landing_rate} fpm` : ""}</small></span>
          <span class="grade-chip g-${esc(r.grade || "")}">${esc(r.grade || "–")}</span></li>`).join("")}</ul>`
        : `<p class="panel-sub" style="padding-bottom:16px">No flights filed yet.</p>`}
    </section>
    <section class="panel">
      <h2>Awards</h2>
      ${d.awards.length ? `<ul class="pilot-awards">${d.awards.map(a => `<li><b>${esc(a.name)}</b><span>${esc(a.description)}</span></li>`).join("")}</ul>`
        : `<p class="panel-sub" style="padding-bottom:16px">No awards yet.</p>`}
    </section>
  </div>
  <section class="panel" style="margin-top:24px">
    <h2>Where ${mine ? "you've" : esc(p.name.split(" ")[0]) + " has"} flown</h2>
    <p class="panel-sub">${fmt(d.collection.airports)} airports in ${fmt(d.collection.countries)} ${d.collection.countries === 1 ? "country" : "countries"}.</p>
    <div class="stats-map pilot-map" id="pilotMap"></div>
  </section>`;
  $("#backRoster").onclick = () => { S.pilotOpen = null; show("pilots"); };
  wireBadge();
  root.querySelectorAll("[data-pirep-open]").forEach(li => {
    li.onclick = () => openDetail(+li.dataset.pirepOpen);
    li.onkeydown = e => { if (e.key === "Enter") openDetail(+li.dataset.pirepOpen); };
  });
  if (HAS_MAP) {
    if (S.pilotMap) { S.pilotMap.remove(); S.pilotMap = null; }
    const m = S.pilotMap = makeBaseMap($("#pilotMap"), { theme: document.documentElement.dataset.theme === "dark" ? "dark" : "light" }).map;
    const wrap = (a, b) => { const lon = b[1] - a[1] > 180 ? b[1] - 360 : b[1] - a[1] < -180 ? b[1] + 360 : b[1]; return [a, [b[0], lon]]; };
    d.map.routes.forEach(x => L.polyline(wrap(x.from, x.to), { color: "#C80000", weight: Math.min(5, 1.2 + x.flights * 0.6), opacity: 0.65 })
      .bindTooltip(`${x.dep}–${x.arr} · ${x.flights} ${x.flights === 1 ? "flight" : "flights"}`).addTo(m));
    const maxV = Math.max(1, ...d.map.airports.map(a => a.visits));
    d.map.airports.forEach(a => L.circleMarker([a.lat, a.lon], { radius: 4 + a.visits / maxV * 8, color: "#fff", weight: 1.5, fillColor: "#C80000", fillOpacity: 0.95 })
      .bindTooltip(`<b>${esc(a.icao)}</b> ${esc(a.city || a.name)}<br>${a.visits} ${a.visits === 1 ? "visit" : "visits"}`).addTo(m));
    if (d.map.airports.length) m.fitBounds(d.map.airports.map(a => [a.lat, a.lon]), { padding: [30, 30], maxZoom: 6 }); else m.setView([35, -40], 2);
  } else $("#pilotMap").innerHTML = `<p class="muted" style="padding:20px">The map needs an internet connection.</p>`;
}

/* ---------------- Liveries (Fleet page) ---------------- */
function liveriesFor(k) { return (S.liveries || []).filter(l => l.type === k); }
function andList(xs) { return xs.length < 2 ? xs.join("") : xs.slice(0, -1).join(", ") + " and " + xs[xs.length - 1]; }
function liveryCredits() {
  const seen = new Map();
  (S.liveries || []).forEach(l => { if (l.painter && !seen.has(l.painter.toLowerCase())) seen.set(l.painter.toLowerCase(), l); });
  if (!seen.size) return "";
  const names = [...seen.values()].map(l => l.painter_link ? `<a href="${esc(l.painter_link)}" target="_blank" rel="noopener">${esc(l.painter)}</a>` : `<b>${esc(l.painter)}</b>`);
  return `<p class="liv-credits">🎨 PAC liveries painted by ${andList(names)}. Thank you!</p>`;
}
function fileSize(b) { return b >= 1048576 ? `${Math.round(b / 1048576)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`; }
function liveryCard(l) {
  const a = S.fleet[l.type] || {}, meta = [l.sim, l.model, l.version && "v" + l.version].filter(Boolean).map(esc).join(" · ");
  const by = l.painter_link ? `<a href="${esc(l.painter_link)}" target="_blank" rel="noopener">${esc(l.painter)}</a>` : esc(l.painter);
  const get = l.kind === "link"
    ? `<a class="btn small" href="${esc(l.download)}" target="_blank" rel="noopener">Get it on ${esc(l.host || "the painter's page")}</a>`
    : l.needs_signin && !S.me
      ? `<button class="btn small" type="button" data-liv-signin>Sign in to download</button>`
      : `<a class="btn small" href="${esc(l.download)}" download>Download${l.size ? " · " + fileSize(l.size) : ""}</a>`;
  return `<div class="liv-card" id="liv-${esc(l.id)}">
    <img src="${esc(l.preview || a.thumb || a.photo || "/static/pac-logo.png")}" alt="${esc(l.title)} livery on the ${esc(a.name || l.type)}" loading="lazy">
    <div class="liv-body">
      <div class="liv-title">${esc(l.title)}${l.registration ? ` <span class="liv-reg">${esc(l.registration)}</span>` : ""}</div>
      <div class="liv-by">Painted by ${by}</div>
      ${meta ? `<div class="liv-meta">${meta}</div>` : ""}
      ${l.notes ? `<p class="liv-notes">${esc(l.notes)}</p>` : ""}
      <div class="liv-actions">${get}<span class="liv-count">${fmt(l.downloads)} download${l.downloads === 1 ? "" : "s"}</span></div>
      ${S.me?.staff ? `<div class="liv-staff"><button type="button" data-liv-edit="${esc(l.id)}">Edit</button><button type="button" data-liv-del="${esc(l.id)}">Remove</button></div>` : ""}
    </div>
  </div>`;
}
function liverySection(k) {
  const a = S.fleet[k], list = liveriesFor(k), form = S.liveryForm?.type === k ? S.liveryForm : null;
  const ask = S.discordInvite ? `<a href="${esc(S.discordInvite)}" target="_blank" rel="noopener">Talk to us on Discord</a>` : "Get in touch with PAC staff";
  return `<section class="ac-liv" aria-label="Liveries for the ${esc(a.name)}">
    <div class="liv-head"><h3>Liveries</h3>${list.length ? `<span class="muted">${list.length}</span>` : ""}<span style="flex:1"></span>
      ${S.me?.staff && !form ? `<button class="btn ghost small" type="button" data-liv-add="${k}">Add livery</button>` : ""}</div>
    ${list.length ? `<div class="liv-grid">${list.map(liveryCard).join("")}</div>`
      : `<p class="liv-empty">No PAC livery for the ${esc(a.name)} yet. Painting one? ${ask}: you'll get full credit here.</p>`}
    ${form ? liveryForm(k, form) : ""}
  </section>`;
}
function liveryForm(k, f) {
  const l = f.id ? (S.liveries || []).find(x => x.id === f.id) || {} : {}, a = S.fleet[k];
  const src = f.src || (l.kind === "link" ? "link" : "file"), val = n => esc(l[n] ?? "");
  return `<form class="ac-edit liv-form" id="livForm" autocomplete="off">
    <h4 class="full" style="margin:0">${f.id ? "Edit livery" : `New livery for the ${esc(a.name)}`}</h4>
    <div class="field"><label for="lv_title">Name of the livery</label><input id="lv_title" name="title" value="${val("title")}" placeholder="PAC house colors" maxlength="80"></div>
    <div class="field"><label for="lv_painter">Painter</label><input id="lv_painter" name="painter" value="${val("painter")}" required maxlength="60"></div>
    <div class="field"><label for="lv_plink">Painter's page (optional)</label><input id="lv_plink" name="painter_link" type="url" value="${val("painter_link")}" placeholder="https://flightsim.to/profile/…"></div>
    <div class="field"><label for="lv_sim">Simulator</label><select id="lv_sim" name="sim">${["MSFS", "X-Plane"].map(o => `<option ${o === (l.sim || ((a.sim || "MSFS") === "X-Plane" ? "X-Plane" : "MSFS")) ? "selected" : ""}>${o}</option>`).join("")}</select></div>
    <div class="field"><label for="lv_model">Add-on aircraft</label><input id="lv_model" name="model" value="${esc(l.model ?? a.sim_model ?? "")}" placeholder="e.g. TFDi MD-11" maxlength="80"></div>
    <div class="field"><label for="lv_ver">Version (optional)</label><input id="lv_ver" name="version" value="${val("version")}" maxlength="20"></div>
    <div class="field"><label for="lv_reg">Registration (optional)</label><input id="lv_reg" name="registration" value="${val("registration")}" placeholder="N110PC" maxlength="12"></div>
    <div class="field"><label for="lv_prev">Preview picture (optional)</label><input id="lv_prev" name="preview" type="file" accept="image/png,image/jpeg,image/webp"></div>
    <div class="field full"><label for="lv_notes">Notes for pilots (optional)</label><textarea id="lv_notes" name="notes" rows="2" maxlength="500" placeholder="Install: unzip into your Community folder.">${val("notes")}</textarea></div>
    <fieldset class="field full liv-src"><legend>Where pilots get it</legend>
      <label><input type="radio" name="src" value="file" ${src === "file" ? "checked" : ""}> Upload the file here <small class="muted">(.zip, .7z or .rar, up to ${S.liveryMaxMb || 600} MB; signed-in pilots only)</small></label>
      <label><input type="radio" name="src" value="link" ${src === "link" ? "checked" : ""}> Link to where the painter hosts it <small class="muted">(open to everyone)</small></label>
      ${src === "file" ? `<input id="lv_file" name="file" type="file" accept=".zip,.7z,.rar">${l.kind === "file" ? `<small class="muted">Leave empty to keep the current file${l.size ? ` (${fileSize(l.size)})` : ""}.</small>` : ""}`
        : `<input id="lv_url" name="url" type="url" value="${l.kind === "link" ? esc(l.url || "") : ""}" placeholder="https://flightsim.to/file/…">`}
    </fieldset>
    <div class="field full row">
      <span class="liv-progress muted" id="lv_prog" aria-live="polite"></span>
      <span style="flex:1"></span>
      <button class="btn ghost" type="button" id="lv_cancel">Cancel</button>
      <button class="btn" type="submit" id="lv_save">${f.id ? "Save" : "Add livery"}</button>
    </div>
  </form>`;
}
function sendForm(url, fd, onProgress) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", url);
    x.upload.onprogress = e => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    x.onload = () => { let d = {}; try { d = JSON.parse(x.responseText); } catch (e) { /* not JSON */ }
      x.status < 300 ? resolve(d) : reject(new Error(d.error || (x.status === 413 ? "That file is too large for the server." : `Upload failed (HTTP ${x.status}).`))); };
    x.onerror = () => reject(new Error("The upload was interrupted. Check your connection and try again."));
    x.send(fd);
  });
}
function bindLiveries() {
  document.querySelectorAll("[data-liv-signin]").forEach(b => b.onclick = () => openSignIn("Sign in to download PAC liveries."));
  document.querySelectorAll("[data-liv-add]").forEach(b => b.onclick = () => { S.liveryForm = { type: b.dataset.livAdd, id: null }; renderFleet(); $("#livForm")?.scrollIntoView({ block: "nearest" }); $("#lv_painter")?.focus(); });
  document.querySelectorAll("[data-liv-edit]").forEach(b => b.onclick = () => { const l = S.liveries.find(x => x.id === b.dataset.livEdit); S.liveryForm = { type: l.type, id: l.id }; renderFleet(); $("#livForm")?.scrollIntoView({ block: "nearest" }); });
  document.querySelectorAll("[data-liv-del]").forEach(b => b.onclick = async () => {
    const l = S.liveries.find(x => x.id === b.dataset.livDel);
    if (!confirm(`Remove “${l.title}” by ${l.painter}? Its file is deleted from the server.`)) return;
    try { S.liveries = (await api(`/api/staff/liveries/${l.id}`, { method: "DELETE" })).liveries; renderFleet(); toast("Livery removed."); }
    catch (err) { toast(err.message); }
  });
  const f = $("#livForm"); if (!f) return;
  const keep = () => { S.liveryForm.draft = Object.fromEntries([...new FormData(f).entries()].filter(([, v]) => typeof v === "string")); };
  f.querySelectorAll("input[name=src]").forEach(r => r.onchange = () => { keep(); S.liveryForm.src = r.value; renderFleet(); restoreDraft(); });
  function restoreDraft() {
    const d = S.liveryForm?.draft, g = $("#livForm"); if (!d || !g) return;
    for (const [n, v] of Object.entries(d)) { const el = g.elements[n]; if (n !== "src" && el && el.type !== "file") el.value = v; }
  }
  $("#lv_cancel").onclick = () => { S.liveryForm = null; renderFleet(); };
  f.onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(f), src = fd.get("src"), file = f.elements.file?.files?.[0];
    fd.delete("src"); fd.append("type", S.liveryForm.type);
    if (!f.elements.preview.files.length) fd.delete("preview");
    if (src === "file") { fd.delete("url"); if (!file) fd.delete("file"); else fd.append("url", ""); }
    const was = S.liveryForm.id ? (S.liveries.find(x => x.id === S.liveryForm.id) || {}).kind : null;
    if (src === "file" && !file && was !== "file") { toast("Choose the livery file, or switch to a link."); return; }
    if (src === "link" && !String(fd.get("url") || "").trim()) { toast("Add the link to where the livery is hosted."); return; }
    const btn = $("#lv_save"), prog = $("#lv_prog");
    btn.disabled = true; prog.textContent = file ? "Uploading… 0%" : "Saving…";
    try {
      const url = S.liveryForm.id ? `/api/staff/liveries/${S.liveryForm.id}` : "/api/staff/liveries";
      const d = await sendForm(url, fd, p => { prog.textContent = p < 1 ? `Uploading… ${Math.round(p * 100)}%` : "Checking the file…"; });
      S.liveries = d.liveries; S.liveryForm = null; renderFleet(); toast(`Livery by ${d.livery.painter} ${url.endsWith("liveries") ? "added" : "saved"}.`);
      $("#liv-" + d.livery.id)?.scrollIntoView({ block: "nearest" });
    } catch (err) { btn.disabled = false; prog.textContent = ""; toast(err.message); }
  };
}

/* ---------------- Profile ---------------- */
const RANKS = ["Cadet", "Second Officer", "First Officer", "Senior First Officer", "Captain", "Senior Captain"];
const RATING_STATUS = ["Active", "In training", "Lapsed", "Inactive"];

async function loadProfile() {
  try {
    const [r] = await Promise.all([api("/api/profile"), refreshCore({profileOnly: true})]);
    S.profile = r.profile; S.pstats = r.stats;
    if (!S.editingProfile) renderProfile();
    renderPilot();
  } catch (e) { toast(e.message); }
}
function ratingHours(r, stats = S.pstats) {
  // a rating covers its whole family (the B757/767 rating flies both), so add up every type in it
  const list = (r.fleets && r.fleets.length ? r.fleets : [r.fleet]).map(k => stats?.by_aircraft?.[k]).filter(Boolean);
  const pac = Math.round(list.reduce((s, a) => s + (a.block_hours || 0), 0) * 10) / 10, prior = Number(r.prior_hours) || 0;
  return { pac, prior, total: pac + prior, flights: list.reduce((s, a) => s + (a.flights || 0), 0), landings: list.reduce((s, a) => s + (a.landings_90d || 0), 0),
           last: list.reduce((m, a) => Math.max(m, a.last_flown || 0), 0) || null };
}
function recencyHtml(h, r) {
  if (!r.fleet) return `<span class="recency">Not in PAC fleet</span>`;
  return h.landings >= 3 ? `<span class="recency ok">Current · ${h.landings} landings in 90 days</span>`
                         : `<span class="recency due">${h.landings} of 3 landings in 90 days</span>`;
}
const esch = n => (Math.round(n * 10) / 10).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function renderProfile() {
  const p = S.profile, st = S.pstats || { totals: {}, by_aircraft: {}, recent: [] }, t = st.totals;
  const totalHours = (p.type_ratings || []).reduce((sum, r) => sum + (Number(r.prior_hours) || 0), 0) + (t.block_hours || 0);
  $("#profileRoot").innerHTML = `
  <div class="profile-bar"><h1>Pilot profile</h1><div class="row"><button class="btn" id="openLicence">Pilot license</button><button class="btn ghost" id="editProfile">Edit profile</button></div></div>
  <article class="crew-card">
    <div class="crew-photo">
      <img src="${esc(p.photo)}" alt="Portrait of ${esc(displayName(p))}" class="${frameCls(p.flair)}">
      <div class="profile-rank-block">${S.career?.rank ? rankImg(S.career.rank) : `<img class="wm" src="/static/pac-wordmark-white.png" alt="">`}<span class="profile-rank-caption">${esc(S.career?.rank || p.rank || "PAC pilot")}</span><span class="profile-pilot-id">${esc(p.pilot_id)}</span></div>
    </div>
    <div class="crew-main">
      <div class="crew-rank">${esc(p.rank)} · ${esc(p.pilot_id)}</div>
      <h2 class="crew-name">${esc(displayName(p))}</h2>
      <div class="crew-title">${esc(p.title)}</div>
      ${(p.roles || []).length ? `<div class="crew-roles">${p.roles.map(r => `<span class="role-chip">${esc(r)}</span>`).join("")}</div>` : ""}
      ${patchStrip(p.flair, 44)}${campaignPatchShelf(p.flair)}${publicShelf(p.flair)}
      <p class="crew-bio">${esc(p.bio)}</p>
      <div class="crew-facts">
        <div><span>Callsign</span><b>${esc(p.callsign) || "–"}</b></div>
        <div><span>Home base</span><b>${esc(p.base) || "–"}</b></div>
        <div><span>Secondary base</span><b>${esc(p.secondary_base) || "–"}</b></div>
        <div><span>With Pagani Air Cargo since</span><b>${p.member_since ? new Date(p.member_since + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "long", year: "numeric" }) : "–"}</b></div>
        <div><span>Total hours</span><b class="num">${esch(totalHours)}</b></div>
        ${S.career?.rank ? `<div><span>Career rank</span><b>${esc(S.career.rank)}</b></div>` : ""}
      </div>
      <div class="endorse"><span class="lbl">Type ratings</span>${[...new Map((p.type_ratings || []).filter(r => r.status !== "Inactive").map(r => [r.type, (p.type_ratings || []).filter(x => x.type === r.type && x.status !== "Inactive").map(x => x.name).join(", ")])).entries()].map(([t, names]) => `<b title="${esc(names)}">${esc(t)}</b>`).join("") || '<span class="muted">None yet</span>'}</div>
    </div>
  </article>

  <div class="profile-grid">
    <section class="panel">
      <h2>Type ratings</h2>
      <p class="panel-sub">PAC hours come from filed PIREPs. Prior hours are what you logged before joining. Recency counts completed PAC landings in the last 90 days.</p>
      <div class="table-wrap" style="border:0"><table class="ratings">
        <thead><tr><th>Type</th><th>Aircraft</th><th>Role</th><th>Issued</th><th class="num">PAC hrs</th><th class="num">Prior hrs</th><th class="num">Total</th><th>Recency</th><th>Status</th></tr></thead>
        <tbody>${(p.type_ratings || []).map(r => { const h = ratingHours(r); return `<tr>
          <td><span class="rt-code">${esc(r.type)}</span></td>
          <td><div class="rt-name">${esc(r.name)}</div>${r.notes ? `<div class="rt-notes">${esc(r.notes)}</div>` : ""}</td>
          <td>${esc(r.role)}</td><td style="white-space:nowrap">${r.issued ? esc(r.issued) : "–"}</td>
          <td class="num">${esch(h.pac)}</td><td class="num">${esch(h.prior)}</td><td class="num"><b>${esch(h.total)}</b></td>
          <td>${recencyHtml(h, r)}</td>
          <td><span class="status-pill ${r.status === "Active" ? "" : "off"}">${esc(r.status || "Active")}</span></td></tr>`; }).join("")
          || `<tr><td colspan="9" class="empty">No type ratings yet. Choose Edit profile to add one.</td></tr>`}</tbody>
      </table></div>
    </section>
    <div class="side-stack">
      <section class="panel crewid-panel">
        <h2>Crew badge</h2>
        <p class="panel-sub">Your PAC airport identification. Click it to turn it over.</p>
        ${badgeHtml(undefined, undefined, undefined, { own: true })}
      </section>
      <section class="panel">
        <h2>Credentials</h2>
        <dl class="creds">${(p.credentials || []).map(c => `<div><dt>${esc(c.label)}</dt><dd>${esc(c.value)}${c.detail || c.expires ? `<small>${esc(c.detail)}${c.detail && c.expires ? " · " : ""}${c.expires ? "Valid until " + esc(c.expires) : ""}</small>` : ""}</dd></div>`).join("")
          || `<p class="muted">No credentials listed.${isFounder() ? " Choose Edit profile to add your licenses and ratings." : " Staff keep these on your PAC record."}</p>`}</dl>
      </section>
      <section class="panel">
        <h2>Career with PAC</h2>
        <div class="career">
          <div><span>Flights</span><b>${fmt(t.flights)}</b></div>
          <div><span>Block hours</span><b>${esch(t.block_hours || 0)}</b></div>
          <div><span>Cargo delivered</span><b>${fmt(t.cargo_lbs)} lb</b></div>
          <div><span>Distance flown</span><b>${fmt(t.distance_nm)} nm</b></div>
          <div><span>Average landing</span><b>${t.avg_landing != null ? t.avg_landing + " fpm" : "–"}</b></div>
          <div><span>Average score</span><b>${t.avg_score ?? "–"}</b></div>
          <div><span>On-time deliveries</span><b>${fmt(t.on_time)}</b></div>
          <div><span>Points</span><b>${fmt(t.points)}</b></div>
        </div>
      </section>
      <section class="panel">
        <h2>Recent flights</h2>
        ${st.recent.length ? `<ul class="recent">${st.recent.map(r => `<li><b>${esc(r.flight_number)}</b><span>${r.dep} – ${r.arr} · ${esc(S.fleet[r.aircraft]?.icao || r.aircraft)}</span><span class="muted">${r.grade}</span></li>`).join("")}</ul>`
          : `<p class="panel-sub" style="padding-bottom:16px">No PIREPs filed yet. Your flights appear here once you file them.</p>`}
      </section>
    </div>
  </div>`;
  wireBadge();
  $("#openLicence").onclick = () => openLicence();
  $("#editProfile").onclick = () => { S.editingProfile = true; S.draft = JSON.parse(JSON.stringify(S.profile)); renderProfileEdit(); };
}

function renderProfileEdit() {
  const p = S.draft;
  const opt = (list, v) => list.map(x => `<option ${x === v ? "selected" : ""}>${esc(x)}</option>`).join("");
  const fleetOpts = v => `<option value="">Not in PAC fleet</option>` + Object.entries(S.fleet).map(([k, a]) => `<option value="${k}" ${k === v ? "selected" : ""}>${esc(a.name)}</option>`).join("");
  $("#profileRoot").innerHTML = `
  <div class="edit">
  <div class="profile-bar"><h1>Edit profile</h1></div>
  <article class="crew-card">
    <div class="crew-photo">
      <img src="${esc(p.photo)}" alt="Your profile photo" id="photoPreview">
      <div class="photo-actions">
        <label class="btn small" for="photoInput">Change photo</label>
        <input type="file" id="photoInput" accept="image/png,image/jpeg,image/webp" hidden>
        <button class="btn ghost small" id="photoReset" type="button">Use original</button>
      </div>
    </div>
    <div class="crew-main">
      <div class="grid2">
        <div class="field"><label for="pf_rank">Career rank</label><input id="pf_rank" value="${esc(p.rank || 'Not available')}" readonly aria-describedby="rankHelp"><small class="muted" id="rankHelp">Your official earned or staff-appointed rank. ${S.me?.staff ? 'Manage appointments in Staff → Roster.' : 'View your progress in Career; contact staff about a correction.'}</small></div>
        <div class="field"><label for="pf_id">Pilot ID</label><input id="pf_id" value="${esc(p.pilot_id)}" disabled title="Pilot IDs never change"><small class="muted">Pilot IDs never change.</small></div>
      </div>
      <div class="field"><label for="pf_name">Full name</label><input id="pf_name" class="crew-name-input" data-k="name" maxlength="80" autocomplete="name" value="${esc(p.name)}"><small class="muted">Updates your crew badge, pilot profile and roster name. Pilot ID, rank and ratings stay unchanged.</small></div>
      <div class="field"><label for="pf_title">Title</label><input id="pf_title" ${isFounder() ? `data-k="title"` : `disabled`} value="${esc(p.title)}"></div>
      <div class="field"><label for="pf_bio">Biography</label><textarea id="pf_bio" data-k="bio">${esc(p.bio)}</textarea></div>
      <div class="grid2">
        <div class="field"><label for="pf_cs">Callsign</label><input id="pf_cs" value="${esc(p.callsign || "PAGANI")}" disabled title="PAC's radio callsign"></div>
        <div class="field"><label for="pf_since">With PAC since</label><input id="pf_since" type="date" ${isFounder() ? `data-k="member_since"` : `disabled`} value="${esc(p.member_since)}"></div>
        <div class="field"><label for="pf_base">Home base</label><input id="pf_base" ${isFounder() ? `data-k="base"` : `disabled`} value="${esc(p.base)}"></div>
        <div class="field"><label for="pf_base2">Secondary base</label><input id="pf_base2" data-k="secondary_base" value="${esc(p.secondary_base)}"></div>
      </div>
    </div>
  </article>

  <div class="profile-grid">
${isFounder() ? `    <section class="panel">
      <h2>Type ratings</h2>
      <p class="panel-sub">Link a rating to a PAC aircraft to count your logged hours and recency on it automatically.</p>
      <div class="table-wrap" style="border:0"><table class="ratings">
        <thead><tr><th style="width:90px">Type</th><th>Aircraft name</th><th>PAC fleet link</th><th style="width:130px">Role</th><th style="width:140px">Issued</th><th style="width:100px">Prior hrs</th><th style="width:120px">Status</th><th>Notes</th><th></th></tr></thead>
        <tbody>${p.type_ratings.map((r, i) => `<tr data-i="${i}">
          <td><input data-r="type" value="${esc(r.type)}" aria-label="Type code"></td>
          <td><input data-r="name" value="${esc(r.name)}" aria-label="Aircraft name"></td>
          <td><select data-r="fleet" aria-label="PAC fleet link">${fleetOpts(r.fleet)}</select></td>
          <td><select data-r="role" aria-label="Role">${opt([...new Set([r.role, "Captain", "First Officer", "Flight Engineer", "Instructor"].filter(Boolean))], r.role)}</select></td>
          <td><input data-r="issued" type="date" value="${esc(r.issued)}" aria-label="Issued"></td>
          <td><input data-r="prior_hours" type="number" min="0" step="0.1" value="${esc(r.prior_hours)}" aria-label="Prior hours"></td>
          <td><select data-r="status" aria-label="Status">${opt(RATING_STATUS, r.status || "Active")}</select></td>
          <td><input data-r="notes" value="${esc(r.notes)}" aria-label="Notes"></td>
          <td><button class="row-del" type="button" data-del-rating="${i}" aria-label="Remove ${esc(r.type)} rating">×</button></td></tr>`).join("")}</tbody>
      </table></div>
      <div class="row add-row"><button class="btn ghost small" id="addRating" type="button">Add type rating</button>
      ${Object.keys(S.fleet).some(k => !p.type_ratings.some(r => r.fleet === k)) ? `<button class="btn ghost small" id="addFleetRatings" type="button">Add missing PAC fleet types</button>` : ""}</div>
    </section>
` : `    <section class="panel">
      <h2>Type ratings</h2>
      <p class="panel-sub">Earned by flying a type checkride (see Career) or granted by staff. Hours on each type count from your logbook.</p>
      ${p.type_ratings.length ? `<div class="table-wrap" style="border:0"><table class="ratings"><thead><tr><th style="width:90px">Type</th><th>Aircraft</th><th style="width:140px">Issued</th><th>How</th></tr></thead>
        <tbody>${p.type_ratings.map(r => `<tr><td><b>${esc(r.type)}</b></td><td>${esc(r.name)}</td><td>${esc(r.issued || "–")}</td><td>${esc(r.notes || "")}</td></tr>`).join("")}</tbody></table></div>`
        : `<p class="panel-sub" style="margin-bottom:16px">No type ratings yet. Your line checkride gives you your first.</p>`}
    </section>
`}
    <div class="side-stack">
${isFounder() ? `      <section class="panel">
        <h2>Credentials</h2>
        <p class="panel-sub">Licenses, medical, ratings and endorsements. Validity date is optional.</p>
        ${p.credentials.map((c, i) => `<div class="cred-edit" data-c="${i}">
          <input data-f="label" value="${esc(c.label)}" placeholder="Name, e.g. Medical" aria-label="Credential name">
          <input data-f="value" value="${esc(c.value)}" placeholder="e.g. First class" aria-label="Credential value">
          <button class="row-del" type="button" data-del-cred="${i}" aria-label="Remove ${esc(c.label)}">×</button>
          <input data-f="detail" value="${esc(c.detail)}" placeholder="Detail (optional)" aria-label="Detail">
          <input data-f="expires" type="date" value="${esc(c.expires)}" aria-label="Valid until">
        </div>`).join("")}
        <button class="btn ghost small add-row" id="addCred" type="button">Add credential</button>
      </section>
` : `      <section class="panel">
        <h2>Credentials</h2>
        <p class="panel-sub">Licenses, medical and endorsements on your PAC record. Staff keep these up to date.</p>
        ${p.credentials.length ? p.credentials.map(c => `<div class="cred-view" style="margin:0 20px"><b>${esc(c.label)}</b> ${esc(c.value)}${c.detail ? ` <span class="muted">· ${esc(c.detail)}</span>` : ""}${c.expires ? ` <span class="muted">· valid until ${esc(c.expires)}</span>` : ""}</div>`).join("")
          : `<p class="panel-sub" style="margin-bottom:16px">None recorded yet.</p>`}
      </section>
`}
    </div>
  </div>
  <div class="save-bar"><button class="btn" id="saveProfile" type="button">Save profile</button><button class="btn ghost" id="cancelProfile" type="button">Discard changes</button><span style="font-size:13px;opacity:.8">Career stats and hours on PAC aircraft update from your logbook automatically.</span></div>
  </div>`;

  const root = $("#profileRoot");
  root.querySelectorAll("[data-k]").forEach(el => el.oninput = () => p[el.dataset.k] = el.value);
  root.querySelectorAll("tr[data-i] [data-r]").forEach(el => el.oninput = el.onchange = () => {
    const r = p.type_ratings[el.closest("tr").dataset.i];
    r[el.dataset.r] = el.value;
    if (el.dataset.r === "fleet" && el.value && !r.name) { r.name = S.fleet[el.value].name; renderProfileEdit(); }
  });
  root.querySelectorAll(".cred-edit [data-f]").forEach(el => el.oninput = () => p.credentials[el.closest(".cred-edit").dataset.c][el.dataset.f] = el.value);
  root.querySelectorAll("[data-del-rating]").forEach(b => b.onclick = () => { p.type_ratings.splice(+b.dataset.delRating, 1); renderProfileEdit(); });
  root.querySelectorAll("[data-del-cred]").forEach(b => b.onclick = () => { p.credentials.splice(+b.dataset.delCred, 1); renderProfileEdit(); });
  if ($("#addRating")) $("#addRating").onclick = () => { p.type_ratings.push({ type: "", fleet: "", name: "", role: "Captain", issued: "", prior_hours: 0, status: "Active", notes: "" }); renderProfileEdit(); root.querySelector("tr[data-i]:last-child input")?.focus(); };
  if ($("#addFleetRatings")) $("#addFleetRatings").onclick = () => {
    Object.keys(S.fleet).filter(k => !p.type_ratings.some(r => r.fleet === k)).forEach(k => p.type_ratings.push({ type: S.fleet[k].icao, fleet: k, name: S.fleet[k].name, role: "Captain", issued: "", prior_hours: 0, status: "Active", notes: S.fleet[k].sim === "X-Plane" ? "X-Plane" : "" }));
    renderProfileEdit(); toast("Added. Save the profile to keep them.");
  };
  if ($("#addCred")) $("#addCred").onclick = () => { p.credentials.push({ label: "", value: "", detail: "", expires: "" }); renderProfileEdit(); root.querySelectorAll(".cred-edit")[p.credentials.length - 1]?.querySelector("input").focus(); };
  $("#photoInput").onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append("photo", f);
    try {
      const res = await fetch("/api/profile/photo", { method: "POST", body: fd });
      const d = await res.json(); if (!res.ok) throw new Error(d.error);
      p.photo = S.profile.photo = d.photo; $("#photoPreview").src = d.photo; renderPilot(); toast("Photo updated.");
    } catch (err) { toast(err.message); }
  };
  $("#photoReset").onclick = async () => {
    const d = await api("/api/profile/photo", { method: "DELETE" });
    p.photo = S.profile.photo = d.photo; $("#photoPreview").src = d.photo; renderPilot(); toast("Original photo restored.");
  };
  $("#cancelProfile").onclick = () => { S.editingProfile = false; renderProfile(); };
  $("#saveProfile").onclick = async () => {
    try {
      const r = await api("/api/profile", { method: "POST", body: p });
      S.profile = r.profile; S.settings = r.settings; S.pstats = r.stats; S.editingProfile = false;
      renderPilot(); renderProfile(); toast("Profile saved."); scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) { toast(e.message); }
  };
}

/* ---------------- utils ---------------- */
function gcnm(a, b) {
  const R = 3440.065, r = x => x * Math.PI / 180;
  const dp = r(b.lat - a.lat), dl = r(b.lon - a.lon);
  const h = Math.sin(dp/2)**2 + Math.cos(r(a.lat)) * Math.cos(r(b.lat)) * Math.sin(dl/2)**2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

(async function boot() {
  try {
    const a = await api("/api/auth/me");
    if (!a.signed_in && a.badge_every_visit && !/password=1/.test(location.search) && !location.hash.startsWith("#set-password")) { location.replace("/badge-login"); return; }
    S.me = a.pilot; S.authPilot = a.pilot; S.setupNeeded = a.setup_needed;
    applyAuth();
    if (a.setup_needed) { openSetup(a.founder_id); return; }            // first time: secure the airline
    const inv = location.hash.match(/^#set-password=([\w-]+)/);
    if (inv) { history.replaceState(null, "", location.pathname); openInvite(inv[1]); }
  } catch (e) { console.error(e); toast(`Couldn't reach the PAC website: ${e.message}`, 15000); return; }
  try {
    const d = await api("/api/bootstrap");
    S.partial = d.partial;
    if (d.divisions) S.divisions = d.divisions;
    Object.assign(S, { missions: d.missions, fleet: d.fleet, settings: d.settings, phases: d.phases, booking: d.booking, profile: d.profile, routes: d.routes || [], cargoTypes: d.cargo_types || [] });
    if ((d.live_public || d.settings?.live_map_public) && !PUBLIC_VIEWS.includes("live")) PUBLIC_VIEWS.push("live");
    applyCore(d);
  } catch (e) { console.error(e); toast(e.status ? `The PAC website answered with an error (${e.status}): ${e.message}` : `Couldn't load the PAC website: ${e.message}`, 15000); return; }
  if (S.partial?.length) toast(`Some parts didn't load (${S.partial.join(", ")}). Staff: the server log says why.`, 10000);
  if (S.me) renderPilot();
  const pm = location.hash.match(/^#pilots\/(PAC\d{4})$/i);       // a link straight to a pilot's profile
  if (pm) S.pilotOpen = pm[1].toUpperCase();
  const careerRoute = /^career\/(overview|qualifications|wallet|activities|awards)$/.test(location.hash.slice(1));
  if (careerRoute) S.careerSection = location.hash.slice(1).split('/')[1];
  const v = pm ? "pilots" : careerRoute ? "career" : location.hash.slice(1);
  initialCoreNavigation = true;
  try {
  if (!S.me && VIEWS.includes(v) && !PUBLIC_VIEWS.includes(v)) {  // a bookmark to a members' page: sign in, then go there
    show("home"); openSignIn(null, v);
  } else show(VIEWS.includes(v) && (S.me || PUBLIC_VIEWS.includes(v)) ? v : (S.me ? "dashboard" : "home"));
  } finally { initialCoreNavigation = false; }
})();

/* ================= Appearance ================= */
function applyTheme() {
  const pref = localStorage.getItem("pac-theme") || "auto";
  const dark = pref === "dark" || (pref === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  if ($("#themeSel")) $("#themeSel").value = pref;
}
matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", applyTheme);
if ($("#designSel")) {
  $("#designSel").value = document.documentElement.dataset.design || "loadsheet";
  $("#designSel").onchange = e => {
    localStorage.setItem("pac-design", e.target.value);
    document.documentElement.dataset.design = e.target.value; setTimeout(fitNav, 50);
    if (S.statsMap) S.statsMap.invalidateSize(); if (S.map) S.map.invalidateSize();  // maps re-measure the new layout
  };
}
if ($("#themeSel")) {
  applyTheme();
  $("#themeSel").onchange = e => { localStorage.setItem("pac-theme", e.target.value); applyTheme(); if (!$("#view-stats").hidden) loadStats(); };
}

/* ================= Sign-in ================= */
function applyAuth() {
  updateNewsBadge();
  const me = S.me, staff = !!me?.staff;
  document.body.classList.toggle("guest", !me);
  const caps = me?.staff_caps || [];
  document.querySelectorAll("nav button[data-view]").forEach(b => {
    const v = b.dataset.view, cap = b.dataset.cap;
    // cap-gated items (a scoped role section) show for full admins or a holder of that capability
    const capHidden = cap ? !(staff || caps.includes(cap)) : false;
    b.classList.toggle("auth-hidden", (!me && !PUBLIC_VIEWS.includes(v)) || (v === "staff" && !staff) || capHidden);
  });
  $("#pilotChip").hidden = !me; $("#openSettings").hidden = !me; $("#signOutBtn").hidden = !me; $("#signInBtn").hidden = !!me;
  setTimeout(fitNav, 0);
  if (!me) { ++briefingVersion; if ($("#pilotBriefing")) $("#pilotBriefing").replaceChildren(); const p = $("#bidPill"); if (p) p.hidden = true; }
}
function authErr(el, msg) { const e = $(el); e.textContent = msg || ""; e.hidden = !msg; }
function openSignIn(why = null, next = null) {
  S.afterSignIn = next;
  $("#signinWhy").textContent = why || (next ? "Sign in to continue. Pilots sign in with their PAC pilot ID." : "Pilots sign in with their PAC pilot ID.");
  authErr("#signinErr", "");
  const d = $("#signinDlg"); if (!d.open) d.showModal();
  setTimeout(() => ($("#si_id").value ? $("#si_pw") : $("#si_id")).focus(), 50);
}
async function afterSignedIn(pilot) {
  // reload with the full members' data, landing on the page the pilot was heading for
  const h = location.hash.slice(1);
  const next = S.afterSignIn || ((h !== "home" && VIEWS.includes(h)) || /^pilots\/PAC\d{4}$/i.test(h) ? h : "dashboard");
  location.hash = next ? "#" + next : "";
  location.reload();
}
$("#signInBtn").onclick = () => openSignIn();
$("#signinForm").onsubmit = async e => {
  e.preventDefault();
  const btn = e.target.querySelector("button[type=submit]"); btn.disabled = true;
  try {
    const r = await api("/api/auth/login", { method: "POST", body: { pilot_id: $("#si_id").value.trim(), password: $("#si_pw").value, remember: $("#si_keep").checked } });
    $("#si_pw").value = ""; $("#signinDlg").close(); await afterSignedIn(r.pilot);
  } catch (err) { authErr("#signinErr", err.message); } finally { btn.disabled = false; }
};
$("#signOutBtn").onclick = async () => {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (e) { /* signed out anyway */ }
  location.hash = ""; location.reload();
};
function openSetup(founderId) {
  $("#setupId").textContent = founderId || "PAC0001";
  authErr("#setupErr", "");
  $("#setupDlg").addEventListener("cancel", e => e.preventDefault());  // can't be skipped
  $("#setupDlg").showModal();
}
$("#setupForm").onsubmit = async e => {
  e.preventDefault();
  if ($("#su_pw").value !== $("#su_pw2").value) { authErr("#setupErr", "The two passwords don't match."); return; }
  try {
    const r = await api("/api/auth/setup", { method: "POST", body: { password: $("#su_pw").value } });
    $("#setupDlg").close(); S.me = r.pilot; S.authPilot = r.pilot; S.setupNeeded = false; applyAuth();
    location.hash = ""; location.reload();
  } catch (err) { authErr("#setupErr", err.message); }
};
async function openInvite(token) {
  S.inviteToken = token; authErr("#inviteErr", "");
  try {
    const r = await api(`/api/auth/invite/${encodeURIComponent(token)}`);
    $("#inviteTitle").textContent = r.purpose === "reset" ? "Choose a new password" : "Welcome to Pagani Air Cargo";
    $("#inviteText").innerHTML = `${r.purpose === "reset" ? "Set a new password for" : "Choose a password for your pilot account"} <b>${esc(r.pilot.id)}</b> (${esc(r.pilot.name)}). You'll use it to sign in here and in PAC ACARS.`;
    $("#inviteDlg").showModal();
  } catch (err) { toast(err.message, 9000); }
}
$("#inviteForm").onsubmit = async e => {
  e.preventDefault();
  if ($("#iv_pw").value !== $("#iv_pw2").value) { authErr("#inviteErr", "The two passwords don't match."); return; }
  try {
    const r = await api("/api/auth/accept", { method: "POST", body: { token: S.inviteToken, password: $("#iv_pw").value } });
    $("#inviteDlg").close(); await afterSignedIn(r.pilot);
  } catch (err) { authErr("#inviteErr", err.message); }
};
$("#passwordForm").onsubmit = async e => {
  e.preventDefault();
  try {
    await api("/api/auth/password", { method: "POST", body: { current: $("#pw_cur").value, new: $("#pw_new").value } });
    $("#pw_cur").value = $("#pw_new").value = ""; authErr("#pwErr", ""); toast("Password changed. Use the new one next time you sign in (PAC ACARS stays signed in).");
  } catch (err) { authErr("#pwErr", err.message); }
};
async function staffRatings(pid) {
  let fams;
  try { fams = (await api(`/api/staff/ratings/${encodeURIComponent(pid)}`, { method: "POST", body: { action: "list" } })).ratings; }
  catch (e) { toast(e.message); return; }
  $("#linkTitle").textContent = `Type ratings for ${pid}`;
  $("#linkText").innerHTML = `<div class="rating-staff">${fams.map(f => `<div><b>${esc(f.family)}</b> <span class="muted">${f.rated ? esc(f.rated.source) : "not rated"}</span>
    ${f.rated?.source === "flown" || f.rated?.source === "line checkride" ? `<span class="muted">(kept: earned by flying)</span>`
      : `<button class="btn ghost small" type="button" data-rt="${esc(f.family)}" data-act="${f.rated ? "remove" : "grant"}">${f.rated ? "Remove" : "Grant"}</button>`}</div>`).join("")}</div>`;
  $("#linkUrl").closest(".row").hidden = true; $("#linkDlg").querySelector(".dlg-body > p.muted").hidden = true;
  if (!$("#linkDlg").open) $("#linkDlg").showModal();
  $("#linkText").querySelectorAll("[data-rt]").forEach(b => b.onclick = async () => {
    try { await api(`/api/staff/ratings/${encodeURIComponent(pid)}`, { method: "POST", body: { family: b.dataset.rt, action: b.dataset.act } }); staffRatings(pid); }
    catch (e) { toast(e.message); }
  });
}
$("#linkDlg").addEventListener("close", () => { $("#linkUrl").closest(".row").hidden = false; $("#linkDlg").querySelector(".dlg-body > p.muted").hidden = false; });
/* The official PAC letters: acceptance, rejection and a sign-in reminder, ready to copy or open in a mail program */
/* Removing a pilot: what it affects, then a typed confirmation */
async function removePilot(pid) {
  let f; try { f = await api(`/api/staff/pilots/${encodeURIComponent(pid)}/footprint`); } catch (e) { toast(e.message); return; }
  const p = (S.staff?.roster || []).find(x => x.id === pid) || {};
  $("#linkTitle").textContent = `Remove ${pid}`;
  $("#linkUrl").closest(".row").hidden = true;
  $("#linkDlg").querySelector(".dlg-body > p.muted").hidden = true;
  $("#linkText").innerHTML = `<p>Removing <b>${esc(p.name || pid)}</b> deletes their account, password, sign-in links, API keys, type ratings, goals and wallet history. Anything they have booked is released back to the board. This can't be undone.</p>
    <ul class="rm-list"><li><b>${f.pireps}</b> ${f.pireps === 1 ? "flight" : "flights"} (${f.hours} hours)</li><li><b>${f.gallery}</b> gallery ${f.gallery === 1 ? "photo" : "photos"}</li>
      <li><b>${f.ratings}</b> type ${f.ratings === 1 ? "rating" : "ratings"}, <b>${f.goals}</b> ${f.goals === 1 ? "goal" : "goals"}</li>${f.bookings ? `<li><b>${f.bookings}</b> booked ${f.bookings === 1 ? "flight" : "flights"}, which will be released</li>` : ""}</ul>
    <label class="switch-row"><input type="radio" name="rmFlights" value="keep" checked><span><b>Keep their flights in PAC's history</b> <span class="muted" style="font-size:13px">totals and records stay right; the flights show as a former pilot</span></span></label>
    <label class="switch-row"><input type="radio" name="rmFlights" value="erase"><span><b>Erase everything</b> <span class="muted" style="font-size:13px">their flights and photos are deleted too, as if they'd never flown</span></span></label>
    <div class="field" style="margin-top:10px"><label for="rmConfirm">Type <b>${esc(pid)}</b> to confirm</label>
      <input id="rmConfirm" autocomplete="off" placeholder="${esc(pid)}" style="width:100%;border:1px solid var(--line);padding:8px 10px;font:inherit;background:var(--white);color:var(--ink)"></div>
    <div class="row" style="margin-top:10px"><button class="btn small danger" type="button" id="rmGo" disabled>Remove this pilot</button>
      <button class="btn ghost small" type="button" id="rmCancel">Cancel</button></div>`;
  if (!$("#linkDlg").open) $("#linkDlg").showModal();
  $("#rmConfirm").oninput = e => { $("#rmGo").disabled = e.target.value.trim().toUpperCase() !== pid.toUpperCase(); };
  $("#rmCancel").onclick = () => $("#linkDlg").close();
  $("#rmGo").onclick = async () => {
    const keep = document.querySelector("[name=rmFlights]:checked").value === "keep";
    $("#rmGo").disabled = true;
    try {
      const r = await api(`/api/staff/pilots/${encodeURIComponent(pid)}`, { method: "DELETE", body: { confirm: $("#rmConfirm").value.trim().toUpperCase(), keep_flights: keep } });
      toast(`${r.name} (${pid}) removed.${r.kept_flights ? " Their flights stay in PAC's history." : ""}`);
      $("#linkDlg").close(); loadStaff();
    } catch (e) { toast(e.message, 8000); $("#rmGo").disabled = false; }
  };
}

async function openLetter(kind, o = {}) {
  const dlg = $("#letterDlg");
  $("#letterTitle").textContent = { accepted: "Welcome letter", rejected: "Decline letter", reminder: "Sign-in reminder" }[kind];
  $("#letterBody").innerHTML = `<p class="muted">Preparing the letter…</p>`;
  if (!dlg.open) dlg.showModal();
  let L;
  const q = new URLSearchParams(Object.fromEntries(Object.entries({ name: o.name, email: o.email, reason: o.reason }).filter(([, v]) => v)));
  try { L = await api(kind === "rejected" && !o.pid ? `/api/staff/letter/rejected?${q}` : `/api/staff/letter/${kind}/${encodeURIComponent(o.pid)}${q.toString() ? "?" + q : ""}`); }
  catch (e) { $("#letterBody").innerHTML = `<p>${esc(e.message)}</p>`; return; }
  S.letter = L;
  $("#letterBody").innerHTML = `
    ${o.why ? `<p class="letter-why">${o.why}</p>` : ""}
    <div class="letter-head"><div><span>To</span><b>${esc(L.to || "—")}</b></div><div><span>Subject</span><b>${esc(L.subject)}</b></div></div>
    <textarea id="letterText" rows="18" spellcheck="false">${esc(L.text)}</textarea>
    ${L.link ? `<p class="muted" style="font-size:13px;margin:8px 0 0">The sign-in link inside works once and expires in 7 days. Making this letter again replaces the old link.</p>` : ""}
    <div class="row" style="margin-top:12px">
      ${S.settings?.mail_ready && L.to ? `<button class="btn small" type="button" id="letterSend">Send it now</button>` : ""}
      <button class="btn ${S.settings?.mail_ready && L.to ? "ghost " : ""}small" type="button" id="letterCopy">Copy the letter</button>
      <button class="btn ghost small" type="button" id="letterSubject">Copy the subject</button>
      ${L.to ? `<button class="btn ghost small" type="button" id="letterMail">Open in my mail program</button>` : ""}
      <button class="btn ghost small" type="button" id="letterHtml">Download as HTML</button>
    </div>`;
  const copy = async (text, what) => {
    try { await navigator.clipboard.writeText(text); toast(`${what} copied.`); }
    catch (e) { $("#letterText").select(); document.execCommand("copy"); toast(`${what} copied.`); }
  };
  if ($("#letterSend")) $("#letterSend").onclick = async e => {
    const btn = e.currentTarget; btn.disabled = true; btn.textContent = "Sending…";
    try { await api("/api/staff/letter/send", { method: "POST", body: { to: L.to, subject: L.subject, text: $("#letterText").value, html: L.html } });
      toast(`Sent to ${L.to}.`); $("#letterDlg").close(); }
    catch (err) { toast(err.message, 10000); btn.disabled = false; btn.textContent = "Send it now"; }
  };
  $("#letterCopy").onclick = () => copy($("#letterText").value, "Letter");
  $("#letterSubject").onclick = () => copy(L.subject, "Subject");
  if ($("#letterMail")) $("#letterMail").onclick = () => {
    const href = `mailto:${encodeURIComponent(L.to)}?subject=${encodeURIComponent(L.subject)}&body=${encodeURIComponent($("#letterText").value)}`;
    if (href.length > 1900) { copy($("#letterText").value, "Letter"); toast("The letter is long, so it's been copied: paste it into your email."); return; }
    location.href = href;
  };
  $("#letterHtml").onclick = () => {
    const b = new Blob([L.html], { type: "text/html" }), a = document.createElement("a");
    a.href = URL.createObjectURL(b); a.download = `PAC-${kind}-${(L.pilot_id || L.to || "letter").replace(/[^\w.-]/g, "_")}.html`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };
}

async function showSigninLink(pid) {
  try {
    const r = await api(`/api/staff/pilots/${encodeURIComponent(pid)}/signin-link`, { method: "POST" });
    $("#linkTitle").textContent = r.purpose === "reset" ? `Password reset link for ${r.pilot.id}` : `Welcome link for ${r.pilot.id}`;
    $("#linkText").innerHTML = `Send this to <b>${esc(r.pilot.name)}</b>. It lets them ${r.purpose === "reset" ? "choose a new password" : "choose their password and sign in for the first time"}.`;
    $("#linkUrl").value = r.link; $("#linkDlg").showModal(); $("#linkUrl").select();
  } catch (err) { toast(err.message); }
}
$("#linkCopy").onclick = async () => { try { await navigator.clipboard.writeText($("#linkUrl").value); toast("Link copied."); } catch (e) { $("#linkUrl").select(); document.execCommand("copy"); toast("Link copied."); } };

/* Pilot briefing: fetched independently so a failed briefing never hides Home. */
let briefingVersion = 0;
async function loadPilotBriefing() {
  const version = ++briefingVersion, pilotId = S.me?.id;
  const root = $('#pilotBriefing');
  if (!root || !S.me) return;
  root.innerHTML = '<p class="muted" role="status">Loading your flight briefing…</p>';
  try {
    const d = await api('/api/pilot/dashboard');
    if (version !== briefingVersion || !root.isConnected || !S.me || S.me.id !== pilotId) return;
    const homeIds = new Set(d.home_options.flat().map(r => r.id));
    const departures = d.departures.filter(r => !homeIds.has(r.id));
    const leg = r => `<button class="brief-route" type="button" data-brief-flight="${esc(r.id)}"><span><b>${esc(r.origin.icao)} <span aria-hidden="true">→</span> ${esc(r.destination.icao)}</b><small>${esc(r.id)} · ${esc(hm(r.minutes))} · ${esc(r.aircraft)}</small></span><span class="brief-availability">${r.available ? 'Review flight →' : 'Aircraft unavailable'}</span></button>`;
    root.innerHTML = `<div class="brief-heading"><div><div class="kicker">Pilot dashboard</div><h2>Welcome aboard, ${esc(d.pilot.name)}</h2><p>${esc(d.pilot.id)} · ${esc(d.pilot.rank)}</p></div><button class="btn ghost small" type="button" data-brief-refresh>Refresh briefing</button></div>
    ${startHereHTML(d)}
    <div class="brief-overview"><div><span>Current station</span><strong>${esc(d.location.icao)}</strong><small>${esc(d.location.name || '')}</small></div><div><span>Home hub</span><strong>${esc(d.hub.icao)}</strong><small>${d.at_home ? 'You’re at home base' : 'Return options below'}</small></div><div><span>Total flight hours</span><strong>${esc(d.pilot.hours)}</strong><small>PAC and credited transfer hours</small></div></div>
    <div class="brief-grid"><article class="brief-card"><div class="kicker">Next on your checklist</div><h3>${d.booking ? 'Your flight is booked' : d.checkride_needed ? 'Ready for your checkride?' : 'Ready for your next flight?'}</h3>
    ${d.booking ? `<p><b>${esc(d.booking.flight_number)}</b> · ${esc(d.booking.aircraft)} ${esc(d.booking.registration || '')}</p><button class="btn" type="button" data-brief-view="bids">Review flight & release →</button>` : d.checkride_needed ? '<p>Complete your checkride to progress through your PAC career.</p><button class="btn" type="button" data-brief-view="career/qualifications">View checkride and qualifications</button>' : '<p>Review a departure below, or explore the full mission board.</p><button class="btn" type="button" data-brief-view="missions">Explore missions</button>'}
    <details class="brief-progress"><summary>Career progress</summary><h4>${d.pilot.next ? `Next rank: ${esc(d.pilot.next)}` : esc(d.pilot.rank)}</h4>${d.pilot.requirements.length ? `<ul>${d.pilot.requirements.map(r => `<li><span aria-label="${r.done ? 'Complete' : 'Outstanding'}">${r.done ? '✓' : '○'}</span> ${esc(r.label)}${r.value != null ? ` <span class="muted">(${esc(r.value)} / ${esc(r.target)})</span>` : ''}</li>`).join('')}</ul>` : '<p>Your current rank has no further progression requirements listed.</p>'}<button class="btn ghost small" type="button" data-brief-view="career">View career</button></details></article>
    <article class="brief-card"><div class="kicker">Get back to base</div><h3>${d.at_home ? 'You’re home at ' + esc(d.hub.icao) : esc(d.location.icao) + ' → ' + esc(d.hub.icao)}</h3>${d.at_home ? '<p>Explore departures from your current station to plan your next trip.</p>' : d.home_options.length ? d.home_options.map(legs => `<div class="brief-connection">${legs.map(leg).join('')}${legs.length > 1 ? '<small>Two sectors. Review each leg separately; onward aircraft availability may change.</small>' : ''}</div>`).join('') : '<p>No direct or one-stop scheduled option matches your current qualifications and aircraft requirements.</p><button class="btn ghost small" type="button" data-brief-view="missions">Explore other missions</button>'}<p class="brief-note">Suggestions are not reservations. Aircraft, location and qualification checks apply when booking.</p></article></div>
    <article class="brief-card brief-departures"><div class="kicker">Departures from ${esc(d.location.icao)}</div><h3>Where will you fly next?</h3>${departures.length ? `<div class="brief-departure-grid">${departures.map(leg).join('')}</div><p class="brief-note">Showing ${departures.length} additional scheduled departures. Return options are listed above.</p>` : '<p>No additional matching departures. Review the return options above or explore the mission board.</p>'}</article>`;
    root.querySelector('[data-brief-refresh]').onclick = loadPilotBriefing;
    const now=document.createElement('section');now.className='brief-card now-card';root.querySelector('.brief-overview').after(now);loadHappeningNow(now,d);const crewPanel=document.createElement('section');crewPanel.className='brief-card';now.after(crewPanel);loadDashboardCrew(crewPanel);
    const planner = document.createElement('section');
    planner.className = 'brief-card rotation-planner';
    root.querySelector('.brief-departures').before(planner);
    loadRotationPlanner(planner, d);
    root.querySelectorAll('[data-brief-view]').forEach(b => b.onclick = () => show(b.dataset.briefView));
    root.querySelectorAll('[data-brief-flight]').forEach(b => b.onclick = () => flyMission(b.dataset.briefFlight));
  } catch (e) {
    if (version !== briefingVersion || !root.isConnected) return;
    root.innerHTML = '<p role="status">Your briefing is temporarily unavailable. You can still use Missions and Career.</p><button class="btn ghost small" type="button">Try again</button>';
    root.querySelector('button').onclick = loadPilotBriefing;
  }
}

/* Personal itineraries use scheduled routes and the existing booking flow. */
async function loadRotationPlanner(root, briefing) {
  const pilot = S.me?.id;
  const current = () => root.isConnected && S.me?.id === pilot;
  root.innerHTML = '<p role="status">Loading your rotation planner…</p>';
  try {
    const state = await api('/api/pilot/rotation-plan');
    if (!current()) return;
    const saved = state.saved;
    const routeLine = p => [p.legs[0].origin, ...p.legs.map(l => l.destination)].map(esc).join(' <span aria-hidden="true">→</span> ');
    const legsHTML = (p, progress = null) => `<ol class="rotation-legs">${p.legs.map((l, i) => `<li class="${progress != null && i < progress ? 'rotation-done' : ''}"><div><b>${esc(l.origin)} → ${esc(l.destination)}</b><small>${esc(l.id)} · ${esc(hm(l.minutes))} · ${esc(l.cargo)} · ${esc(fmt(l.payload_lbs))} lb</small></div><span>${progress == null ? `Leg ${i + 1}` : i < progress ? 'Accepted ✓' : i === progress ? 'Next leg' : 'Later'}</span></li>`).join('')}</ol>`;
    root.innerHTML = `<div class="brief-heading"><div><div class="kicker">Your next cargo run</div><h3>Plan my rotation</h3><p>Connected scheduled flights, tailored to your time.</p></div></div>
      ${saved ? `<article class="rotation-saved"><div class="rotation-title"><div><span class="kicker">Saved itinerary · ${esc(saved.aircraft)}</span><h4>${routeLine(saved)}</h4></div><button type="button" class="btn ghost small" data-rotation-clear>Remove plan</button></div><p>${saved.completed}/${saved.legs.length} legs accepted · ${esc(hm(saved.total_minutes))} planned total</p>${legsHTML(saved, saved.completed)}
        ${saved.completed === saved.legs.length ? '<p class="rotation-success">Rotation complete. Welcome to your destination!</p>' : `<button type="button" class="btn" data-rotation-next ${state.booking || saved.legs[saved.completed].origin !== state.location ? 'disabled' : ''}>Review next leg →</button><p class="brief-note">${state.booking ? 'Finish your current booking before starting the next leg.' : saved.legs[saved.completed].origin !== state.location ? `Next leg departs ${esc(saved.legs[saved.completed].origin)}; you are at ${esc(state.location)}. Progress updates after accepted flight reports.` : 'Opens the existing mission planner. Confirm the saved aircraft type before booking.'}</p>`}
        <p class="brief-note">Saved to your pilot account. Only matching, accepted flights filed after saving count toward progress.</p></article>` : ''}
      <details class="rotation-controls" ${saved ? '' : 'open'}><summary>${saved ? 'Find a different rotation' : 'Choose your flying time'}</summary>
      <form class="rotation-form"><label>Aircraft<select name="aircraft" required>${state.eligible_types.map(t => `<option value="${esc(t)}">${esc(t)} · ${esc(S.fleet[t]?.name || t)}</option>`).join('')}</select></label>
      <label>Time available<select name="minutes"><option value="120">2 hours</option><option value="180">3 hours</option><option value="240" selected>4 hours</option><option value="360">6 hours</option><option value="480">8 hours</option><option value="720">12 hours</option><option value="1440">24 hours</option></select></label>
      <label>Between legs<select name="turnaround"><option value="0">No extra time</option><option value="20" selected>20 minutes</option><option value="30">30 minutes</option><option value="45">45 minutes</option><option value="60">60 minutes</option></select></label>
      <label class="rotation-checkbox"><input name="return_home" type="checkbox" checked> Finish at home (${esc(state.hub)})</label>
      <button class="btn" type="submit" ${state.checkride_needed || !state.eligible_types.length ? 'disabled' : ''}>Find rotations →</button></form>
      <p class="brief-note">Starts at ${esc(state.location)} · Up to 4 legs · Full cargo loads · Estimated block time plus time between legs. Allow extra time for preflight. ${state.checkride_needed ? 'Complete your checkride first.' : ''}</p>
      <div class="rotation-results" aria-live="polite"></div></details>
      <p class="brief-note">A plan does not reserve aircraft or flights. Availability, location, qualifications and route details are checked again when booking.</p>`;
    const next = root.querySelector('[data-rotation-next]');
    if (next) next.onclick = () => flyMission(saved.legs[saved.completed].id, saved.aircraft);
    const clear = root.querySelector('[data-rotation-clear]');
    if (clear) clear.onclick = async () => {
      clear.disabled = true;
      try { await api('/api/pilot/rotation-plan', {method:'DELETE'}); if (current()) await loadRotationPlanner(root, briefing); }
      catch (e) { if (current()) { clear.disabled = false; toast(e.message); } }
    };
    root.querySelector('form').onsubmit = async event => {
      event.preventDefault();
      const form = event.currentTarget, button = form.querySelector('button'), results = root.querySelector('.rotation-results');
      const body = {aircraft: form.elements.aircraft.value, minutes: Number(form.elements.minutes.value), turnaround: Number(form.elements.turnaround.value), return_home: form.elements.return_home.checked};
      button.disabled = true;
      results.innerHTML = '<p role="status">Finding connected cargo routes…</p>';
      try {
        const data = await api('/api/pilot/rotation-options', {method:'POST', body});
        if (!current()) return;
        results.innerHTML = `${data.airframes_enforced && !data.available_airframes ? '<p class="rotation-warning">No available airframe of this type at your station right now. You can save a plan for later.</p>' : ''}${data.booking ? '<p class="rotation-warning">You have a booking. These plans start at your current recorded station; your location may change when you finish it.</p>' : ''}
          ${data.plans.length ? data.plans.map((p,i) => `<article class="rotation-option"><div class="rotation-title"><div><span class="kicker">Option ${i + 1} · ${esc(p.aircraft)} · ${p.legs.length} ${p.legs.length === 1 ? 'leg' : 'legs'}</span><h4>${routeLine(p)}</h4></div><strong>${esc(hm(p.total_minutes))}</strong></div><p class="brief-note">${esc(hm(p.flight_minutes))} block time + ${esc(hm(p.total_minutes - p.flight_minutes))} between legs</p>${legsHTML(p)}<button type="button" class="btn ghost" data-save-rotation="${i}">${saved ? 'Replace saved itinerary' : 'Save this itinerary'}</button></article>`).join('') : '<p>No matching rotation found within these limits. Try more time, another aircraft, or uncheck “Finish at home.”</p>'}
          ${data.limited ? '<p class="brief-note">Search limit reached. These are suggestions from a bounded search, not every possible itinerary.</p>' : ''}`;
        results.querySelectorAll('[data-save-rotation]').forEach(b => b.onclick = async () => {
          const p = data.plans[Number(b.dataset.saveRotation)];
          results.querySelectorAll('button').forEach(x => x.disabled = true);
          try {
            await api('/api/pilot/rotation-plan', {method:'POST', body:{...body, route_ids:p.legs.map(l => l.id)}});
            if (current()) { await loadRotationPlanner(root, briefing); toast('Rotation saved to your pilot account.'); }
          } catch (e) { if (current()) { results.querySelectorAll('button').forEach(x => x.disabled = false); toast(e.message); } }
        });
      } catch (e) { if (current()) results.innerHTML = `<p role="alert">${esc(e.message)}</p>`; }
      finally { if (current()) button.disabled = false; }
    };
  } catch (e) {
    if (!current()) return;
    root.innerHTML = '<h3>Plan my rotation</h3><p role="status">The planner is temporarily unavailable.</p><button class="btn ghost small" type="button">Try again</button>';
    root.querySelector('button').onclick = () => loadRotationPlanner(root, briefing);
  }
}


async function staffOperationsHealth() {
  const root = $('#staffBody');
  root.innerHTML = '<p role="status">Reading operations health…</p>';
  const ago = value => value == null ? 'Not available' : value < 60 ? 'Less than a minute ago' : value < 3600 ? `${Math.floor(value / 60)} minutes ago` : value < 86400 ? `${Math.floor(value / 3600)} hours ago` : `${Math.floor(value / 86400)} days ago`;
  const when = value => value ? new Date(value * 1000).toLocaleString() : 'Not recorded';
  try {
    const d = await api('/api/staff/operations-health');
    if (!root.isConnected || S.staffTab !== 'health' || !S.me?.staff) return;
    const card = (title, item, body) => `<article class="ops-card ops-${esc(item.level)}"><div class="ops-card-head"><h2>${esc(title)}</h2><span class="ops-state">${esc({ok:'Healthy',warning:'Attention',unknown:'Unavailable',notice:'Info'}[item.level] || 'Unavailable')}</span></div><p>${esc(item.message)}</p>${body}${item.note ? `<p class="muted">${esc(item.note)}</p>` : ''}</article>`;
    root.innerHTML = `<div class="ops-heading"><div><h2>Operations health</h2><p class="muted">Read-only snapshot · Checked ${esc(when(d.checked_at))}</p></div><button class="btn ghost small" type="button" id="opsRefresh">Refresh status</button></div><div class="ops-grid">` +
      card('Mission worker',d.worker,`<dl><dt>Last successful refresh</dt><dd>${esc(when(d.worker.last_success_at))} · ${esc(ago(d.worker.age_seconds))}</dd><dt>Last run duration</dt><dd>${d.worker.duration_seconds == null ? 'Not recorded' : esc(d.worker.duration_seconds) + ' seconds'}</dd></dl>`) +
      card('Mission boards',d.boards,d.boards.counts ? `<div class="ops-counts">${Object.entries(d.boards.counts).map(([label,count]) => `<div><strong>${esc(count)}</strong><span>${esc(label)}</span></div>`).join('')}</div>` : '') +
      card('Discord bot',d.discord,`<p>Last heartbeat: ${esc(when(d.discord.last_seen))} · ${esc(ago(d.discord.age_seconds))}</p>`) +
      (d.vatsim ? card('VATSIM listing readiness',d.vatsim,`${d.vatsim.counts ? `<div class="ops-counts">${Object.entries(d.vatsim.counts).map(([label,count]) => `<div><strong>${esc(count)}</strong><span>${esc(label)}</span></div>`).join('')}</div>` : ''}<p><a href="/api/staff/vatsim-flights.csv">Download the flight list for VATSIM</a> (callsign, origin, destination, date)</p>`) : '') +
      card('Application backups',d.backups,`<p>${esc(d.backups.name || 'No backup recorded')}</p><p>${esc(ago(d.backups.age_seconds))}</p>`) + '</div><p class="muted">Refreshes only when you open this tab or select Refresh status. No services are restarted and no missions or backups are created by this panel.</p>';
    $('#opsRefresh').onclick = staffOperationsHealth;
  } catch (e) {
    if (!root.isConnected || S.staffTab !== 'health') return;
    root.innerHTML='<p role="status">Operations health could not be loaded.</p><button class="btn ghost small" type="button">Try again</button>';
    root.querySelector('button').onclick=staffOperationsHealth;
  }
}


/* Pilot journey: guidance uses existing actions; the server retains booking authority. */
function setCareerSection(section, updateURL = true) {
  const allowed = ['overview', 'qualifications', 'wallet', 'activities', 'awards'];
  if (!allowed.includes(section)) section = 'overview';
  S.careerSection = section;
  document.querySelectorAll('[data-career-pane]').forEach(p => p.hidden = p.dataset.careerPane !== section);
  document.querySelectorAll('[data-career-section]').forEach(b => {
    b.setAttribute('aria-current', b.dataset.careerSection === section ? 'page' : 'false');
  });
  if (updateURL) location.hash = 'career/' + section;
}
function resetMissionFilters() {
  Object.assign(S, {parkedOrigin:'',shipmentDestinations:[], shipmentFilterTitle:'', boardCampaignId:'', boardSearch:'', boardCargo:'', boardShortHeavy:false, boardQualifiedOnly:false, boardAvailableOnly:false, boardPage:1, sortBy:'default', fromHere:false, simFilter:'', divFilter:'', acFilter:'', lenFilter:'any', netSearch:'', region:'All', filter:'All', partnerFilter:null, jobKind:'all', netLimit:40});
  renderPilotStrip(); renderMissions();
}
function travelGuideHTML() {
  return `<div class="journey-travel-grid">
    <article><h3>Free checkride travel</h3><p><b>Moves you, not the aircraft.</b> Open Career → Qualifications. Choose a fleet checkride and PAC includes free travel when you book it. Dedicated training needs no travel and leaves your normal station unchanged. Generate a matching OFP for your chosen route.</p><button type="button" class="btn ghost small" onclick="closePilotGuide();show('career/qualifications')">View qualifications →</button></article>
    <article><h3>Jumpseat</h3><p><b>Moves you to another station.</b> Your PAC location is shown in Career → Pay & wallet. Travel to your mission's departure, or to the aircraft if you want to fly its ferry yourself. Review the travel quote before confirming.</p><button type="button" class="btn ghost small" onclick="closePilotGuide();show('career/wallet')">View location & wallet →</button></article>
    <article><h3>Have it ferried</h3><p><b>Moves an available aircraft to you.</b> You must be at the mission's departure to see this paid action in its airframe list. The fee is $100 + $0.20 per nautical mile from your PAC wallet. You see the quote before paying. Booked or unavailable aircraft cannot be moved.</p></article>
    <article><h3>Fly it yourself</h3><p><b>A separate ferry flight with no cargo.</b> Choose “Fly it to…” beside an available aircraft. This builds a ferry plan from its current station. You still need to be qualified and positioned there before booking. Finish the ferry before requesting your cargo flight.</p></article>
  </div>`;
}
function pilotWelcomeHTML() {
  let dismissed = false;
  try { dismissed = localStorage.getItem('pac-guide-dismissed-' + S.me?.id) === '1'; } catch (_) {}
  return `<section class="journey-welcome" aria-label="Pilot help"><div><span class="kicker">Your flight starts here</span><h3>${dismissed ? 'Need a hand with your next step?' : 'New to PAC? Let’s get you flying.'}</h3>${dismissed ? '' : '<p>Get qualified, find an aircraft, then plan and release your flight. Training travel is free when offered for your type checkride.</p>'}</div><div class="row"><button class="btn" onclick="openPilotGuide()">First-flight guide</button><button class="btn ghost" onclick="show('career/qualifications')">Qualifications</button>${dismissed ? '' : '<button class="journey-text-button" onclick="dismissPilotWelcome(this)">Keep this compact</button>'}</div></section>`;
}
function dismissPilotWelcome(button) {
  try { localStorage.setItem('pac-guide-dismissed-' + S.me?.id, '1'); } catch (_) {}
  const panel = button.closest('.journey-welcome');
  if (panel) panel.outerHTML = pilotWelcomeHTML();
}
function closePilotGuide() { document.getElementById('pilotGuideDialog')?.close(); }
function openPilotGuide(path = 'checkride') {
  let dialog = document.getElementById('pilotGuideDialog');
  if (!dialog) {
    dialog = document.createElement('dialog'); dialog.id = 'pilotGuideDialog';
    dialog.className = 'journey-dialog'; dialog.setAttribute('aria-labelledby','pilotGuideTitle');
    document.body.append(dialog);
  }
  const training = path !== 'cargo';
  const steps = training ? [
    ['Choose your aircraft', 'Open Qualifications and find the family you want to fly. The card shows your rating, eligibility and available checkride action.'],
    ['Get to an available aircraft', 'Choose dedicated training at a supported airport, or a fleet checkride with free positioning travel. No paid ferry is needed; existing aircraft reservations are respected.'],
    ['Generate and import your plan', 'Book the checkride from its card to open mission planning. Confirm the route and aircraft, then press Generate OFP on the SimBrief & request tab; the plan comes in by itself. (Or open SimBrief yourself, click Generate Flight, then Fetch latest OFP.)'],
    ['Request, review and sign', 'Request the mission, then open My bids. Review the cargo, load and dispatch paperwork. Sign the release before starting tracking.'],
    ['Fly and submit your report', 'Open PAC ACARS, load the correct flight and aircraft in your simulator, and follow the checklist. After the flight, file your report. A passing checkride unlocks the rating when the report is accepted.']
  ] : [
    ['Choose your cargo flight', 'Browse Missions. Check the departure, payload and aircraft. Your qualification and current PAC location matter, as well as the aircraft’s location.'],
    ['Arrange the aircraft and your travel', 'Choose an available tail at the departure. If necessary, jumpseat yourself there, have an available aircraft delivered to you, or fly a separate ferry. The guide below explains each option.'],
    ['Generate and import your plan', 'Check the aircraft and the load sheet, then press Generate OFP on the SimBrief & request tab; the plan comes in by itself. (Or open SimBrief yourself, click Generate Flight, then Fetch latest OFP.) Resolve any mismatch shown.'],
    ['Review the cargo and sign', 'Request the mission, open My bids and review the release, shipments and handling instructions. Use the load planner where supported. Review and sign the final release.'],
    ['Track, fly and file', 'Open PAC ACARS and follow the aircraft checklist. Complete the flight and file your PIREP. Review status determines when accepted-flight credit is awarded.']
  ];
  dialog.innerHTML = `<div class="journey-dialog-head"><div><span class="kicker">PAC crew guide</span><h2 id="pilotGuideTitle">From choosing a flight to flying it</h2></div><button type="button" class="btn ghost small" onclick="closePilotGuide()" aria-label="Close first-flight guide">Close</button></div>
    <div class="journey-dialog-body"><div class="journey-sections" aria-label="Choose your guide"><button type="button" aria-pressed="${training}" onclick="openPilotGuide('checkride')">I need a type checkride</button><button type="button" aria-pressed="${!training}" onclick="openPilotGuide('cargo')">I’m flying cargo</button></div>
    <ol class="journey-guide-steps">${steps.map(([title,body],i) => `<li><span class="journey-number" aria-hidden="true">${i+1}</span><div><h3>${title}</h3><p>${body}</p></div></li>`).join('')}</ol>
    <div class="row"><button class="btn" onclick="closePilotGuide();show('${training ? 'career/qualifications' : 'missions'}')">${training ? 'Find my qualification' : 'Find a cargo flight'} →</button><button class="btn ghost" onclick="closePilotGuide();show('bids')">My current booking</button></div>
    <details class="journey-help"><summary>Jumpseat, company travel or aircraft ferry?</summary>${travelGuideHTML()}</details>
    <p class="muted">This guide explains the workflow. Your qualification cards, mission validation and aircraft checklist provide the applicable requirements.</p></div>`;
  if (!dialog.open) dialog.showModal();
}
function missionReadiness(m) {
  if (S.booking) return '';
  const ac = S.aircraft, dep = m.origin.icao, here = S.me?.location?.icao;
  const messages = [];
  if (S.me?.enforce_location && here !== dep) messages.push(`Your PAC location is ${here || 'not loaded'}; this flight departs ${dep}.`);
  const rating = needsRating(m, ac);
  if (rating) messages.push(`You need the ${rating} type rating for this aircraft.`);
  if (lockedByRank(m, ac)) messages.push('This aircraft is not unlocked at your current rank. Review Qualifications for your options.');
  const frames = (S.airframes || []).filter(a => a.type === ac);
  if (!m.contract && S.settings.enforce_airframes !== false && !frames.some(a => a.status === 'Available' && a.location === dep && (!m.fixed_airframe || a.reg === m.fixed_airframe))) {
    messages.push(`No available ${S.fleet[ac]?.icao || ac} airframe at ${dep}.`);
  }
  const training = !!m.type_checkride || m.category === "Checkride" || m.id === S.checkrideId;
  return `<section class="journey-readiness ${messages.length ? 'needs-attention' : ''}" aria-label="Before you plan"><span class="kicker">Before you plan</span><h3>${messages.length ? 'A few things to arrange first' : 'Check your aircraft, then plan'}</h3>${messages.length ? `<ul>${messages.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '<p>No location, rating or availability blocker was found in the information loaded. Review the aircraft and payload below; final checks run when you request the flight.</p>'}
    ${training ? '<p><b>For a type checkride, look for free company travel in Qualifications before paying for a ferry.</b></p>' : ''}
    <div class="row">${training || rating || lockedByRank(m, ac) ? '<button type="button" class="btn small" onclick="show(\'career/qualifications\')">Qualifications & training travel</button>' : ''}${!training && here !== dep && S.me?.enforce_location ? `<button type="button" class="btn small" onclick="openJumpseat('${esc(dep)}')">Travel to ${esc(dep)}</button>` : ''}<button type="button" class="btn ghost small" onclick="openPilotGuide('${training ? 'checkride' : 'cargo'}')">Step-by-step guide</button></div></section>`;
}

/* Mission browsing uses existing loaded data; booking remains server-validated. */
function missionBoardPool() {
  const pool = [...(S.missions || []), ...(S.checkrides || []), ...(S.urgent || []), ...(S.jobs || []), ...(S.routes || []), ...rotationBoardList(), ...eventsBoardList()];
  return [...new Map(pool.map(m => [m.id, m])).values()];
}
function boardTypes(m) {
  return (m.aircraft || []).filter(a => S.fleet[a] && !S.fleet[a].retired && (!S.acFilter || a === S.acFilter) && (!S.simFilter || fliesIn(a, S.simFilter)));
}
function boardQualified(m, a) {
  if (!S.me || !S.ratings || !S.career) return false;
  return !lockedByRank(m, a) && !needsRating(m, a);
}
function boardAvailable(m, a) {
  // Partner work supplies its own aircraft; never invent a PAC tail for it.
  if (m.contract) return true;
  return (S.airframes || []).some(f => f.type === a && f.status === 'Available' && f.location === m.origin.icao && (!m.fixed_airframe || f.reg === m.fixed_airframe));
}
function boardMatchTypes(m) {
  return boardTypes(m).filter(a => (!S.boardQualifiedOnly || boardQualified(m,a)) && (!S.boardAvailableOnly || boardAvailable(m,a)));
}
function boardSource(m) {
  if (m.category === 'Checkride' || m.type_checkride || m.id === S.checkrideId) return 'Checkride';
  if (m.contract) return 'Partner crew';
  if (m.urgent) return 'Urgent';
  if (m.rotation) return 'Rotation';
  if (m.tour) return 'Tour';
  if (m.job_kind) return 'Job board';
  if ((S.routes || []).some(r => r.id === m.id)) return 'Scheduled';
  return 'Mission';
}
function boardStatus(m) {
  const zq = zoneFor(m);
  if (zq?.level === "restricted") return `Not authorized · ${zq.names.join(", ")} is restricted airspace`;
  const types = boardTypes(m), qualified = types.filter(a => boardQualified(m,a));
  if (!S.me || !S.ratings) return 'Review qualifications before planning';
  if (!qualified.length) return 'Review rank or type-rating requirements';
  if (!qualified.some(a => boardAvailable(m,a))) return 'Aircraft positioning needed for a qualified type';
  if (S.me.enforce_location && S.me.location?.icao !== m.origin.icao) return `Pilot travel needed · departs ${m.origin.icao}`;
  return m.contract ? 'Qualified type · partner supplies aircraft' : `Qualified type · aircraft at ${m.origin.icao}`;
}
function boardAccent(m) {
  if (m.urgent) return 'urgent';
  return ({'Humanitarian':'relief','Express':'express','Heavy lift':'heavy','Medical':'medical','Medicine':'medical'})[m.category] || 'standard';
}
function shedTag(m) {
  const x = S.shedMap?.[m.origin?.icao];
  return x && x.pct >= 85 ? `<span class="tag lane-review" title="The shed at ${esc(x.station)} is ${x.pct}% full">Clears a congested shed</span>` : "";
}
function laneTag(m) {
  const L = S.laneMap?.[`${m.origin?.icao}>${m.destination?.icao}`];
  if (!L || L.tier === "Good") return "";
  const cls = { Preferred: "lane-pref", "Under review": "lane-review", "At risk": "lane-risk" }[L.tier];
  return `<span class="tag ${cls}" title="Lane reputation ${L.score}/100 from ${L.flights} recent flight${L.flights === 1 ? "" : "s"}">${esc(L.tier)} lane · ${L.score}</span>`;
}
async function loadLanes(force) {
  if (!S.me?.id || (S.laneMap && !force && Date.now() - (S.laneAt || 0) < 300000)) return S.laneList || [];
  api("/api/sheds").then(x => { S.shedMap = Object.fromEntries((x.sheds || []).map(y => [y.station, y])); }).catch(() => {});
  try { const d = await api("/api/lanes"); S.laneList = d.lanes; S.accountList = d.accounts || []; S.laneMap = Object.fromEntries(d.lanes.map(L => [`${L.origin}>${L.destination}`, L])); S.laneAt = Date.now(); }
  catch (e) { S.laneMap = S.laneMap || {}; }
  return S.laneList || [];
}
function boardCard(m) {
  return `<button type="button" class="waybill mb-card mb-accent-${boardAccent(m)}${zoneFor(m)?.level === "restricted" ? " wb-restricted" : ""}" data-id="${esc(m.id)}" aria-pressed="${S.selected?.id === m.id}">
    <span class="mb-card-top"><span class="mb-work-label">${m.relief ? '<span class="relief-label">HUMANITARIAN RELIEF</span>' : m.urgent ? '<span class="mb-urgent-label">! URGENT</span>' : ''}${esc([...new Set([m.urgent && m.urgent_kind ? m.urgent_kind : boardSource(m), m.short_heavy ? "Short-haul heavies" : m.category || 'Cargo'])].join(" · "))}</span><span>${esc(m.id)}</span></span>
    <span class="mb-route"><span><b>${esc(m.origin.icao)}</b><small>${esc(m.origin.city || m.origin.name)}</small></span><span aria-hidden="true">→</span><span><b>${esc(m.destination.icao)}</b><small>${esc(m.destination.city || m.destination.name)}</small></span></span>
    <strong class="mb-title">${esc(m.title)}</strong><span class="mb-cargo">${esc(m.cargo)}</span>
    <span class="mb-tags">${shedTag(m)}${laneTag(m)}${zoneTag(m)}${m.short_heavy ? `<span class="tag dark">${fmt(m.distance_nm)} NM · Routine delivery</span>` : ""}${boardCampaignLabels(m)}${bonusTags(m)}${freshTags(m)}${m.tour || m.rotation ? `<span class="tag dark">Leg ${esc(m.leg)}/${esc(m.legs)}</span>` : ''}${m.handling ? `<span class="tag grey">${esc(m.handling.label)}</span>` : ''}${m.challenge ? `<span class="tag amber">${esc(m.challenge.label)}</span>` : ''}${m.urgent ? `<span class="tag amber">URGENT ×1.5 · deliver by ${zulu(m.deliver_by)}</span><span>Offer: <span class="countdown" data-countdown="${Number(m.expires)}"></span></span>` : ''}</span>
    <span class="mb-facts"><span>Estimated block<b>${hm(m.target_block_min)}</b></span><span>Recommended types<b>${(m.aircraft || []).map(a=>esc(S.fleet[a]?.icao || a)).join(', ')}</b>${(() => { const ds = [...new Set((m.aircraft || []).map(divOf).filter(Boolean))]; return ds.length ? `<small class="mb-div">${ds.map(d => esc(divShort(d))).join(" · ")}</small>` : ""; })()}</span><span>Cargo load<b>${fmt(m.payload_lbs || 0)} lb</b></span><span>Reward<b>${fmt(m.reward || 0)} points${m.short_heavy ? ` · includes ${fmt(m.handling_points)} handling points` : ""}${m.contract_bonus ? ` · $${fmt(m.contract_bonus)} bonus` : m.ferry_bonus ? ` · $${fmt(m.ferry_bonus)} ferry bonus` : ''}</b></span></span>
    <span class="mb-status">${esc(boardStatus(m))}</span><span class="mb-card-bottom"><small>Check details before planning</small><b>Review flight →</b></span></button>`;
}
function boardSearchList(list) {
  if(S.parkedOrigin) list=list.filter(m=>m.origin?.icao===S.parkedOrigin);
  const q = (S.boardSearch || '').trim().toLowerCase();
  return list.filter(m => (!S.shipmentDestinations?.length || (Number(m.payload_lbs)>0 && !m.ferry && !m.type_checkride && m.id!==S.checkrideId && !["Ferry","Checkride","Type checkride"].includes(m.category) && m.job_kind!=="ferry" && S.shipmentDestinations.includes(m.destination.icao))) && boardCampaignFilter(m) && (!q || [m.id,m.title,m.cargo,m.category,m.origin.icao,m.origin.city,m.origin.name,m.destination.icao,m.destination.city,m.destination.name].some(x=>String(x || '').toLowerCase().includes(q))) &&
    (!S.boardCargo || m.category === S.boardCargo) && (!S.boardShortHeavy || m.short_heavy === true) &&
    (!(S.acFilter || S.simFilter || S.boardQualifiedOnly || S.boardAvailableOnly) || boardMatchTypes(m).length));
}
function renderBoardTools() {
  const el = $('#missionBrowseTools'); if (!el) return;
  el.hidden = S.board === 'charter';
  const categories = [...new Set(missionBoardPool().map(m=>m.category).filter(Boolean))].sort();
  el.innerHTML = `${S.parkedOrigin ? `<p><b>Departures from ${esc(S.parkedOrigin)}</b> · Use Reset filters to browse all airports.</p>` : ""}<div class="mb-search-row"><label>Find a flight<input type="search" id="boardSearch" placeholder="Airport, city, cargo or flight number" value="${esc(S.boardSearch || '')}"></label><label>Cargo work<select id="boardCargo"><option value="">All cargo types</option>${categories.map(c=>`<option ${S.boardCargo===c?'selected':''}>${esc(c)}</option>`).join('')}</select></label></div>
    <div class="mb-quick"><button type="button" class="chip" data-mb-toggle="boardShortHeavy" aria-pressed="${!!S.boardShortHeavy}">Short-haul heavies · 100–300 NM</button><button type="button" class="chip" data-mb-toggle="boardQualifiedOnly" aria-pressed="${!!S.boardQualifiedOnly}">Qualified recommended types</button><button type="button" class="chip" data-mb-toggle="boardAvailableOnly" aria-pressed="${!!S.boardAvailableOnly}">Aircraft at departure / partner supplied</button><button type="button" class="btn ghost small" id="boardReset">Reset filters</button></div>
    <p class="mb-note">Filters match the same recommended aircraft type. Availability and qualifications are checked again when booking.</p>`;
  $('#boardSearch').oninput = e => { S.boardSearch=e.target.value; clearTimeout(S._boardSearchTimer); S._boardSearchTimer=setTimeout(()=>{renderMissions();const input=$('#boardSearch');input.focus();input.setSelectionRange(input.value.length,input.value.length);},180); };
  $('#boardCargo').onchange=e=>{S.boardCargo=e.target.value;renderMissions();};
  el.querySelectorAll('[data-mb-toggle]').forEach(b=>b.onclick=()=>{S[b.dataset.mbToggle]=!S[b.dataset.mbToggle];renderMissions();});
  $('#boardReset').onclick=resetMissionFilters;
  const drawer=$('#boardInspiration');drawer.hidden=S.board==='charter';
  // Use current data, rather than fabricated flight history or destination claims.
  const options=missionBoardPool().filter(m=>m.origin.icao===S.me?.location?.icao && boardMatchTypes(m).some(a=>boardQualified(m,a)&&boardAvailable(m,a))).sort((a,b)=>(a.target_block_min||0)-(b.target_block_min||0)).slice(0,3);
  $('#boardSuggestions').innerHTML=options.length ? options.map(m=>`<button type="button" class="mb-suggestion" data-suggestion="${esc(m.id)}"><b>${esc(m.origin.icao)} → ${esc(m.destination.icao)}</b><span>${esc(m.title)}</span><small>${hm(m.target_block_min)} · ${esc(boardSource(m))}</small></button>`).join('') : '<p class="mb-note">No matching suggestions at your station right now. Browse the boards or visit Qualifications for checkride and free company-travel options.</p>';
  $('#boardSuggestions').querySelectorAll('[data-suggestion]').forEach(b=>b.onclick=()=>selectMission(b.dataset.suggestion));
}
function boardPage(list) {
  const signature=JSON.stringify([S.board,S.filter,S.region,S.netSearch,S.acFilter,S.simFilter,S.divFilter,S.lenFilter,S.sortBy,S.fromHere,S.partnerFilter,S.jobKind,S.boardSearch,S.boardCargo,S.boardShortHeavy,S.boardQualifiedOnly,S.boardAvailableOnly,S.boardCampaignId,list.map(m=>m.id)]);
  if(signature!==S._boardPageKey){S.boardPage=1;S._boardPageKey=signature;}
  const pages=Math.max(1,Math.ceil(list.length/6));S.boardPage=Math.min(Math.max(1,S.boardPage||1),pages);
  const start=(S.boardPage-1)*6,shown=list.slice(start,start+6);
  const pager=$('#boardPagination');pager.hidden=S.board==='charter';
  pager.innerHTML=`<span role="status">${list.length?`${start+1}–${start+shown.length}`:'0'} of ${list.length} matching flights</span><div><button class="btn ghost small" id="boardPrevious" ${S.boardPage===1?'disabled':''}>Previous</button><span>Page ${S.boardPage} of ${pages}</span><button class="btn small" id="boardNext" ${S.boardPage===pages?'disabled':''}>Next</button></div>`;
  for(const [id,delta] of [['boardPrevious',-1],['boardNext',1]])$('#'+id).onclick=()=>{S.boardPage+=delta;renderMissions();$('#manifest').scrollIntoView({block:'start'});$('#manifest').focus({preventScroll:true});};
  return shown;
}

/* Campaign discovery is advisory. Accepted PIREPs remain the source of credit. */
function boardActiveCampaigns() {
  const now=Date.now()/1000;
  if (S._campaignPilot !== S.me?.id) return [];
  return (S.boardCampaigns || []).filter(c=>c.state==='published' && Number(c.starts)<=now && now<Number(c.ends) && !c.archived_at);
}
function boardCampaignMatches(m) {
  if (!(Number(m.payload_lbs)>0) || m.ferry || m.type_checkride || m.id===S.checkrideId || ['Checkride','Type checkride','Ferry'].includes(m.category) || m.job_kind==='ferry' || m.origin?.icao===m.destination?.icao) return [];
  return boardActiveCampaigns().filter(c=>(c.destinations || []).includes(m.destination?.icao));
}
function boardCampaignLabels(m) {
  return boardCampaignMatches(m).map(c=>`<span class="tag mb-campaign-tag" title="Potential contribution. File within the campaign dates; the cargo report must qualify and be accepted.">Campaign · ${esc(c.title)}</span>`).join('');
}
function boardCampaignFilter(m) {
  return !S.boardCampaignId || boardCampaignMatches(m).some(c=>String(c.id)===String(S.boardCampaignId));
}
async function loadBoardCampaigns(force=false) {
  const pilot=S.me?.id;
  if (!pilot) return;
  if (S._campaignPilot!==pilot) {
    S._campaignPilot=pilot;S.boardCampaigns=[];S.boardCampaignId='';S._campaignAt=0;S._campaignLoading=false;S._campaignError=false;
  }
  if (S._campaignLoading || (!force && Date.now()-(S._campaignAt || 0)<60000)) return;
  S._campaignLoading=true;S._campaignError=false;
  const token={};S._campaignRequest=token;
  try {
    const data=await api('/api/pilot/cargo-campaigns');
    if(S.me?.id!==pilot || S._campaignRequest!==token)return;
    if(!Array.isArray(data.campaigns))throw new Error('Campaign list unavailable');
    S.boardCampaigns=data.campaigns;S._campaignAt=Date.now();
  } catch(error) {
    if(S.me?.id!==pilot || S._campaignRequest!==token)return;
    S.boardCampaigns=[];S._campaignError=true;S._campaignAt=Date.now();
  } finally {
    if(S.me?.id===pilot && S._campaignRequest===token){
      S._campaignLoading=false;
      if(!$('#view-missions')?.hidden)renderMissions();
    }
  }
}
function renderBoardCampaigns() {
  const el=$('#boardCampaignPanel');if(!el)return;
  el.hidden=S.board==='charter';
  if(!S.me){el.innerHTML='';return;}
  if(S._campaignError){
    el.innerHTML=`<p class="mb-note">Campaigns could not load. Flight browsing is still available. <button type="button" class="btn ghost small" id="campaignRetry">Retry campaigns</button>${S.boardCampaignId?' <button type="button" class="btn ghost small" onclick="resetMissionFilters()">Clear campaign filter</button>':''}</p>`;
    $('#campaignRetry').onclick=()=>{loadBoardCampaigns(true);};return;
  }
  const list=boardActiveCampaigns();
  if(!list.length){el.innerHTML=S.boardCampaignId?'<p class="mb-note">The selected campaign is no longer active. <button type="button" class="btn ghost small" onclick="resetMissionFilters()">Browse all flights</button></p>':'';return;}
  const campaign=list.find(c=>String(c.id)===String(S.boardCampaignId || S.boardFeaturedCampaign)) || list[0];
  const pct=Math.min(100,Math.max(0,Number(campaign.pct)||0));
  el.innerHTML=`<div class="mb-campaign-heading"><div><span class="kicker">Fly toward a shared goal</span>${list.length>1?`<label class="mb-note">Active campaign <select id="boardCampaignChoice">${list.map(c=>`<option value="${Number(c.id)}" ${c.id===campaign.id?'selected':''}>${esc(c.title)}</option>`).join('')}</select></label>`:`<h2>${esc(campaign.title)}</h2>`}<p>${(campaign.destinations || []).map(esc).join(' · ')} · ${fmt(campaign.cargo_lbs)} / ${fmt(campaign.target_lbs)} lb delivered · ${pct}%</p></div><div class="row"><button type="button" class="btn small" id="findCampaignFlights">Find campaign flights →</button><button type="button" class="btn ghost small" id="viewCampaignProgress">View progress</button></div></div>
    <progress max="100" value="${pct}" aria-label="${esc(campaign.title)} progress" title="Cargo arrivals at these destinations may contribute. File during the campaign dates; credit follows an accepted, qualifying report.">${pct}%</progress>
    ${S.boardCampaignId?`<p class="mb-note">Cargo arrivals at these destinations may contribute. <b>Campaign filter active: ${esc(list.find(c=>String(c.id)===String(S.boardCampaignId))?.title || 'previous campaign')}.</b> <button type="button" class="btn ghost small" id="clearCampaignFilter">Clear campaign filter</button></p>`:''}`;
  const choice=$('#boardCampaignChoice');if(choice)choice.onchange=()=>{S.boardFeaturedCampaign=choice.value;S.boardCampaignId='';renderMissions();};
  $('#findCampaignFlights').onclick=()=>{
    S.board='all';resetMissionFilters();S.boardCampaignId=String(campaign.id);renderMissions();$('#manifest').scrollIntoView({block:'start'});$('#manifest').focus({preventScroll:true});
  };
  $('#viewCampaignProgress').onclick=()=>{S.statsTab='campaigns';show('stats');};
  const clear=$('#clearCampaignFilter');if(clear)clear.onclick=()=>{S.boardCampaignId='';renderMissions();};
}

function cargoAwardArt(a) {
  if (a.patch) return `<img src="${esc(a.patch)}" alt="${esc(a.title)} patch" style="width:120px;height:120px;object-fit:contain">`;
  const colors=['#173c52','#7d202b','#285342','#493b66'];const color=colors[Math.abs(Number(a.id)||0)%colors.length];
  return `<svg viewBox="0 0 120 120" role="img" aria-label="${esc(a.title)} contributor patch"><circle cx="60" cy="60" r="55" fill="${color}" stroke="#d9ba6e" stroke-width="5"/><circle cx="60" cy="60" r="48" fill="none" stroke="#d9ba6e" stroke-dasharray="2 3"/><text x="60" y="33" text-anchor="middle" fill="white" font-size="17" font-weight="800">PAC</text><path d="M60 44l8 15 28 5-28 7-8 15-8-15-28-7 28-5z" fill="#d9ba6e"/><text x="60" y="101" text-anchor="middle" fill="white" font-size="10">${esc(a.year)} · ${Number(a.id)||0}</text></svg>`;
}
function campaignPatchShelf(flair) {
  const awards=flair?.campaign_awards || [];if(!awards.length)return '';
  return `<section class="ce-awards"><h3>Earned campaign patches</h3><div>${awards.map(a=>`<figure>${cargoAwardArt(a)}<figcaption><b>${esc(a.title)}</b><small>Shared target reached · contributor</small></figcaption></figure>`).join('')}</div></section>`;
}
async function loadFeaturedShipment(force=false) {
  const pid=S.me?.id;if(!pid)return;
  if(S._featurePilot!==pid){S._featurePilot=pid;S.featuredShipment=null;S._featureAt=0;S._featureBusy=false;S._featureError=false;}
  if(S._featureBusy || (!force && Date.now()-(S._featureAt||0)<60000))return;
  S._featureBusy=true;const token={};S._featureToken=token;
  try{const d=await api('/api/pilot/featured-shipment');if(S.me?.id!==pid || S._featureToken!==token)return;S.featuredShipment=d.shipment;S._featureError=false;}
  catch(e){if(S.me?.id!==pid || S._featureToken!==token)return;S.featuredShipment=null;S._featureError=true;}
  finally{if(S.me?.id===pid && S._featureToken===token){S._featureBusy=false;S._featureAt=Date.now();renderFeaturedShipment();}}
}
function renderFeaturedShipment() {
  const el=$('#featuredShipment');if(!el)return;el.hidden=S.board==='charter';
  if(S._featurePilot!==S.me?.id){el.innerHTML='';return;}
  if(S._featureError){el.innerHTML='<p class="muted">Featured shipment could not load. <button class="btn ghost small" onclick="loadFeaturedShipment(true)">Retry</button></p>';return;}
  const f=S.featuredShipment,now=Date.now()/1000;
  if(!f || now<f.starts || now>=f.ends){el.innerHTML='';return;}
  el.innerHTML=`<article class="ce-feature"><div><span class="kicker">Shipment of the Week · fictional cargo story</span><h2>${esc(f.title)}</h2><p class="ce-story">${esc(f.description)}</p><small>${(f.destinations||[]).map(esc).join(' · ')} · through ${new Date((f.ends-1)*1000).toLocaleDateString(undefined,{timeZone:'UTC'})} UTC</small></div><button class="btn" id="ceFindFlights">Find flights to these destinations →</button><p class="ce-note">Choose a suitable cargo flight. This feature does not reserve a consignment or change its load, pay or campaign rules.</p></article>`;
  $('#ceFindFlights').onclick=()=>{S.board='all';resetMissionFilters();S.shipmentDestinations=[...f.destinations];S.shipmentFilterTitle=f.title;renderMissions();$('#manifest').scrollIntoView({block:'start'});};
}
function shipmentFilterNote(){
  if(!S.shipmentDestinations?.length)return '';
  return `<span class="ce-filter">Featured destinations: ${S.shipmentDestinations.map(esc).join(', ')} <button type="button" class="btn ghost small" onclick="S.shipmentDestinations=[];renderMissions()">Clear</button></span>`;
}
function receiptHTML(r) {
  return `<div class="ce-receipt"><div class="ce-receipt-head"><span class="kicker">PAC cargo operations · delivery receipt</span><h2>${esc(r.flight_number)} · ${esc(r.dep)} → ${esc(r.arr)}</h2><span class="tag ${r.qualifies?'green':'amber'}">${esc(r.review_status || 'Not credited')}</span></div><p>${esc(r.reason)}</p>
    <div class="ce-receipt-totals"><div><small>Reported cargo</small><b>${fmt(r.reported_cargo_lbs)} lb</b></div><div><small>Qualifying cargo</small><b>${fmt(r.credited_cargo_lbs)} lb</b></div><div><small>Posted to wallet</small><b>${money(r.posted_total,true)}</b></div></div>
    <h3>Campaign contribution</h3>${r.campaigns.length?`<ul>${r.campaigns.map(c=>`<li><b>${esc(c.title)}</b> · ${fmt(c.cargo_lbs)} lb credited</li>`).join('')}</ul><p class="ce-note">A delivery may support multiple campaigns; cargo and pay are not multiplied.</p>`:'<p class="muted">No campaign credit for this report under the current rules.</p>'}
    <h3>Recorded earnings and adjustments</h3>${r.postings.length?`<div class="ce-ledger">${r.postings.map(p=>`<div><span>${esc(p.description || p.kind)}</span><b>${money(p.amount,true)}</b></div>`).join('')}</div>`:'<p class="muted">No wallet entries have been posted for this flight.</p>'}
    ${campaignPatchShelf({campaign_awards:r.awards})}<p class="ce-note">Receipt #${Number(r.id)} · Reflects the current report review and ledger. Awards shown are your currently earned campaign patches.</p></div>`;
}
async function openDeliveryReceipt(id) {
  let d=$('#deliveryReceiptDialog');if(!d){d=document.createElement('dialog');d.id='deliveryReceiptDialog';d.className='journey-dialog';document.body.append(d);}
  const pid=S.me?.id,token={};d._request=token;
  d.innerHTML='<div class="journey-dialog-head"><h2>Delivery receipt</h2><button class="btn ghost small" onclick="this.closest(\'dialog\').close()">Close</button></div><div class="journey-dialog-body" id="receiptBody"><p role="status">Loading recorded delivery…</p></div>';
  if(!d.open)d.showModal();
  try{const r=await api('/api/pilot/delivery-receipt/'+Number(id));if(d._request!==token || S.me?.id!==pid || !d.open)return;$('#receiptBody').innerHTML=receiptHTML(r);}
  catch(e){if(d._request===token && d.open && S.me?.id===pid)$('#receiptBody').innerHTML=`<p role="alert">${esc(e.message)}</p><button class="btn" onclick="openDeliveryReceipt(${Number(id)})">Retry</button>`;}
}
function offerDeliveryReceipt(id){
  const el=$('#latestDeliveryReceipt');if(!el || !Number.isInteger(id))return;
  el.innerHTML=`<div class="ce-receipt-offer"><div><b>Your flight report is filed.</b><p>See its review status, campaign contribution and posted earnings.</p></div><button class="btn" onclick="openDeliveryReceipt(${id})">View delivery receipt →</button></div>`;
}
async function loadShipmentEditor(){
  const root=$('#shipmentEditor'),pid=S.me?.id;if(!root || !S.me?.staff)return;
  const current=()=>root.isConnected && S.me?.id===pid && S.me?.staff;
  root.innerHTML='<p>Loading shipment features…</p>';
  try{const data=await api('/api/staff/featured-shipments');if(!current())return;
    const today=new Date().toISOString().slice(0,10),last=new Date(Date.now()+6*86400000).toISOString().slice(0,10);
    root.innerHTML=`<details class="cargo-create"><summary>Manage Shipment of the Week</summary><p>Publish a fictional cargo story with links to flights serving its destinations. One published feature can cover any given day.</p><form id="shipmentForm" class="cargo-form"><label>Title<input name="title" required minlength="3" maxlength="80" placeholder="Island clinic resupply"></label><label>Cargo story<textarea name="description" required maxlength="1000" rows="3" placeholder="A fictional shipment, why it matters, and what pilots are carrying."></textarea></label><div class="cargo-form-row"><label>Start (UTC)<input name="start_date" type="date" required value="${today}"></label><label>Last day (UTC)<input name="end_date" type="date" required value="${last}"></label></div><label>Destination ICAOs<input name="destinations" required placeholder="MYNN, TJSJ, TNCM"></label><button class="btn" type="submit">Save private shipment draft</button><p id="shipmentStatus" role="status"></p></form><div class="ce-features">${data.shipments.map(f=>`<article><span class="kicker">${esc(f.state)}</span><h3>${esc(f.title)}</h3><p class="ce-story">${esc(f.description)}</p><p>${f.destinations.map(esc).join(', ')} · ${new Date(f.starts*1000).toISOString().slice(0,10)} – ${new Date((f.ends-1)*1000).toISOString().slice(0,10)} UTC</p>${f.state==='draft'?`<button class="btn small" data-feature="${f.id}" data-action="publish">Publish shipment</button> `:''}${f.state!=='archived'?`<button class="btn ghost small" data-feature="${f.id}" data-action="archive">Archive</button>`:''}</article>`).join('')}</div></details>`;
    $('#shipmentForm').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,b=f.querySelector('button'),fields=f.elements;b.disabled=true;try{await api('/api/staff/featured-shipments',{method:'POST',body:{title:fields.title.value,description:fields.description.value,start_date:fields.start_date.value,end_date:fields.end_date.value,destinations:fields.destinations.value.split(/[\s,]+/).filter(Boolean)}});if(current())loadShipmentEditor();}catch(err){if(current()){$('#shipmentStatus').textContent=err.message;b.disabled=false;}}};
    root.querySelectorAll('[data-feature]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api('/api/staff/featured-shipments/'+b.dataset.feature,{method:'POST',body:{action:b.dataset.action}});S._featureAt=0;if(current())loadShipmentEditor();}catch(e){if(current()){toast(e.message);b.disabled=false;}}});
  }catch(e){if(current())root.innerHTML=`<p role="alert">${esc(e.message)}</p><button class="btn ghost small" onclick="loadShipmentEditor()">Retry shipment editor</button>`;}
}

/* Secondary controls stay available without dominating the flight list. */
function updateBrowseSummary() {
  const drawer = document.getElementById('browseDetails');
  if (!drawer) return;
  drawer.hidden = S.board === 'charter';
  const active = [S.filter && S.filter !== 'All', S.region && S.region !== 'All', S.netSearch,
    S.acFilter, S.simFilter, S.divFilter, S.lenFilter && S.lenFilter !== 'any', S.sortBy && S.sortBy !== 'default',
    S.partnerFilter, S.jobKind && S.jobKind !== 'all'].filter(Boolean).length;
  document.getElementById('browseSummary').textContent = `More filters & sorting${active ? ` · ${active} active` : ''}`;
}


/* Pilot experience: existing booking/release/status remain authoritative. */
function preparationPanel(b, st, available) {
  const m=b.mission,dep=m.origin.icao,here=S.me?.location?.icao;
  const aircraft=!!(m.training || b.airframe || m.contract || S.settings.enforce_airframes===false);
  const positioned=m.training?.mode==='dedicated' || here===dep || S.me?.enforce_location===false;
  const release=!!b.signed && !b.release_amended;
  const connected=!!(available && st.tracking && st.connected && st.booking && st.booking.requested_at===b.requested_at && st.booking.flight_number===b.flight_number);
  const steps=[
    [aircraft,'Aircraft selected',b.airframe || (m.training?'Temporary training aircraft':m.contract?'Partner-supplied aircraft':aircraft?'Airframe assignment not required':'No assigned airframe in this booking'),'<button class="btn ghost small" onclick="show(\'acars\')">Review booked flight</button>'],
    [positioned,'Pilot positioned',m.training?.mode==='dedicated'?`Dedicated session at ${dep}; normal station unchanged`:here===dep?`At ${dep}`:S.me?.enforce_location===false?'Pilot location is not enforced':`Recorded location: ${here||'unavailable'} · departure ${dep}`,`<button class="btn ghost small" onclick="show('career/wallet')">Review location & travel</button>`],
    [release,'Dispatch reviewed',release?'Current release signed':b.release_amended?'Release changed — review again':needsSignature(b)?'Review and sign before tracking':'Signature optional; review your release before departure','<a class="btn ghost small" href="/dispatch" target="_blank" rel="noopener">Review dispatch release →</a>'],
    [connected,'ACARS connected',!available?'Connection status unavailable — try refreshing':connected?'Fresh tracking connection for this booking':st.tracking?'Tracking reported; matching connection not confirmed':'Open PAC ACARS and start this booked flight',`<a class="btn ghost small" href="${appLink(b)}">Open PAC ACARS →</a>`]
  ];
  const n=steps.filter(s=>s[0]).length,next=steps.findIndex(s=>!s[0]);
  return `<section class="px-prep"><div class="px-heading"><div><span class="kicker">YOUR NEXT STEPS</span><h2>Prepare your flight</h2></div><span>${n} of 4 confirmed</span></div><div class="px-progress"><span style="width:${n*25}%"></span></div><div class="px-steps">${steps.map((s,i)=>`<article class="${s[0]?'ready':i===next?'next':''}"><span class="px-number">${s[0]?'✓':i+1}</span><div><h3>${s[1]}</h3><p>${esc(s[2])}</p>${s[3]}</div></article>`).join('')}</div><p class="muted">This is a preparation guide. Aircraft checks and the server’s flight rules still apply.</p><button class="btn ghost small" onclick="refreshPreparation()">Refresh readiness</button></section>`;
}
async function refreshPreparation(){try{await refreshCore();await loadMe();await refreshReleaseGate();await loadBids();}catch(e){toast(e.message)}}
function missionCargoBrief(m){
  if(m.relief)return reliefBrief(m);
  const purpose={Humanitarian:'Relief cargo supports the teams receiving it at the destination.',Medical:'Medical cargo supports care and supply continuity at the destination.',Medicine:'Medical cargo supports care and supply continuity at the destination.',Express:'Express cargo supports time-sensitive connections and deliveries.', 'Heavy lift':'Outsize and heavy cargo needs an aircraft and load plan suited to the shipment.',AOG:'Aircraft parts help a receiving maintenance team return an aircraft to service.'};
  const date=t=>new Date(t*1000).toLocaleString('en-US',{timeZone:'UTC',dateStyle:'medium',timeStyle:'short'})+' UTC';
  const deadline=Number(m.deliver_by)>0?`Arrive by ${date(m.deliver_by)}`:'No fixed delivery deadline listed';
  return `<section class="px-cargo"><span class="kicker">THE CARGO BEHIND THE FLIGHT</span><h3>${esc(m.cargo || m.title)}</h3><p>${esc(m.briefing || 'Review the cargo, route and aircraft requirements below before requesting this flight.')}</p>${purpose[m.category]?`<div class="px-purpose"><b>Why it matters</b><p>${esc(purpose[m.category])}</p></div>`:''}<div class="px-deadline"><b>${esc(deadline)}</b>${Number(m.expires)>0?`<small>Booking offer closes ${esc(date(m.expires))}. This is separate from any arrival deadline.</small>`:''}</div><details><summary>Before you request this flight</summary><ul><li>Check your qualification and the selected aircraft’s payload and range.</li><li>Review pilot location and aircraft availability below.</li><li>${m.handling?'Read the shipment handling instructions below.':'No additional shipment handling instructions are listed in this mission.'}</li>${m.challenge?'<li>Review the airport challenge notes below.</li>':''}</ul></details></section>`;
}
function patchShowcase(c){
  const own=c.patches.filter(p=>p.owned),ids=c.featured_patches||[];
  if(!own.length)return '<section class="px-prep"><h2>Your patch showcase</h2><p>Your purchased patches will appear here. Choose up to three to feature on your profile.</p></section>';
  return `<section class="px-prep"><span class="kicker">YOUR PROFILE SHOWCASE</span><h2>Make it your own</h2><p>Feature up to three patches. Removing one from display keeps it in your collection.</p><div class="px-showcase"><div class="px-patch-grid">${own.map(p=>`<article>${patchSVG(p,80)}<b>${esc(p.name)}</b><button class="btn ghost small" data-feature-patch="${esc(p.id)}" aria-pressed="${ids.includes(p.id)}">${ids.includes(p.id)?'✓ Featured · remove':'Feature patch'}</button></article>`).join('')}</div><aside><h3>On your profile</h3><div class="patch-strip">${ids.map(id=>{const p=own.find(p=>p.id===id);return p?patchSVG(p,64):''}).join('')}</div>${!ids.length?'<p>No patches featured.</p>':''}${ids.map((id,i)=>`<div class="px-order"><span>${esc(own.find(p=>p.id===id)?.name||id)}</span><button class="btn ghost small" data-patch-move="${esc(id)}" data-direction="-1" aria-label="Move ${esc(own.find(p=>p.id===id)?.name)} earlier" ${i===0?'disabled':''}>↑</button><button class="btn ghost small" data-patch-move="${esc(id)}" data-direction="1" aria-label="Move ${esc(own.find(p=>p.id===id)?.name)} later" ${i===ids.length-1?'disabled':''}>↓</button></div>`).join('')}<p class="muted">Changes save immediately. Your earned campaign awards and rank stay separate.</p></aside></div></section>`;
}
let patchSaving=false;
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-feature-patch],[data-patch-move]');if(!b||patchSaving)return;
 const items=[...(S.shop.featured_patches||[])],id=b.dataset.featurePatch||b.dataset.patchMove,i=items.indexOf(id);
 if(b.dataset.patchMove){const j=i+Number(b.dataset.direction);if(i<0||j<0||j>=items.length)return;[items[i],items[j]]=[items[j],items[i]];}
 else if(i>=0)items.splice(i,1);else {if(items.length>=3){toast('Remove a featured patch first. Your showcase has three spaces.');return;}items.push(id);}
 patchSaving=true;b.disabled=true;
 try{S.shop=await api('/api/shop/featured-patches',{method:'POST',body:{items}});await afterShop();toast('Patch showcase saved.');}
 catch(err){toast(err.message);b.disabled=false;}finally{patchSaving=false;}
});
const PAC_UPDATES=[
 {"id": "20261115-radio-cheatsheet", "date": "November 15, 2026", "kind": "New feature", "title": "Radio cheat sheet, built for your flight", "body": "New to talking to ATC on VATSIM? Open your dispatch release and grab the 🗒️ Radio cheat sheet — a full gate-to-gate guide (clearance, push, taxi, takeoff, handoffs, approach, landing) with exactly what to say and what you’ll hear back, prefilled with your callsign, airports and wind-favoured runways. Anything ATC assigns stays as a [bracket] to fill in. Print it or save as PDF. Also at /radio.", "view": "acars", "label": "Open ACARS"},
 {"id": "20261114-unicom-live", "date": "November 14, 2026", "kind": "Improvement", "title": "Unicom calls: smarter and on the ACARS page", "body": "The Unicom call generator now fills your runway automatically from the wind, says the airport\u2019s spoken name in Voice mode (\u201cMemphis traffic\u201d), and \u2014 while PAC ACARS is running \u2014 highlights the exact call for your current phase of flight \u2014 and on IVAO it fills in your next waypoint and ETA on the enroute calls. There\u2019s also a \ud83d\udcfb Unicom calls button right on the ACARS page now, not just the dispatch release.", "view": "acars", "label": "Open ACARS"},
 {"id": "20261114-unicom-gen", "date": "November 14, 2026", "kind": "New feature", "title": "Unicom calls built from your flight", "body": "No controller online? Open your dispatch release and hit \u201c\ud83d\udcfb Unicom calls\u201d \u2014 it builds every call for you, prefilled with your callsign, airports, runways and cruise. Pick VATSIM or IVAO and Text or Voice, then copy each call straight into the sim. Also at /unicom/flight.", "view": "downloads", "label": "Open Downloads"},
 {"id": "20261113-unicom", "date": "November 13, 2026", "kind": "New feature", "title": "Unicom cheat sheet (no ATC online)", "body": "Flying on VATSIM or IVAO with no controller on? There's a new printable cheat sheet for Unicom 122.800: what to do and exactly what to say, phase by phase, with copy-paste text calls. Find it under Learn \u2192 Downloads & cheat sheets, or open /unicom.", "view": "downloads", "label": "Open Downloads"},
 {"id": "20261113-status", "date": "November 13, 2026", "kind": "New feature", "title": "/status in Discord", "body": "Type /status anywhere in the PAC Discord to see your day at a glance: where you are, where you're sleeping tonight, your booked flight or trip leg, your wallet and what's left for your next rank. Only you see the reply. Link your account first with /link (the code is in Settings)."},
 {"id": "20261113-monthly", "date": "November 13, 2026", "kind": "New feature", "title": "Your monthly PAC report", "body": "On the 1st of every month you'll get an email about your month with PAC: flights, hours, cargo moved, best landing, average score and earnings, plus how the whole airline did. The first one arrives December 1. Every email has a one-click link to turn them off."},
 {"id": "20261113-hoppie", "date": "November 13, 2026", "kind": "New feature", "title": "Loadsheet to the cockpit (Hoppie ACARS)", "body": "PAC Load Control (PACLD) can now send your final loadsheet straight to your aircraft's ACARS: weights, CG, limits and trim, as a real load controller would. Use 📡 Send loadsheet to cockpit on the dispatch release, tick Auto-send to have it arrive when you start PAC ACARS, or send REQ LOADSHEET to PACLD from the cockpit. With Auto-send on, PAC Ops (PACOPS) also confirms your OUT/OFF times with an ETA after takeoff and your ON/IN times at the gate. Log on to Hoppie in the aircraft with your own code and the flight's callsign.", "view": "acars", "label": "Open ACARS"},
 {"id": "20261113-new-edition", "date": "November 13, 2026", "kind": "Improvement", "title": "Request a new loadsheet edition", "body": "Changed something after signing the dispatch release? Request new edition reopens it, recalculates the figures and lets you sign again. It works at the gate even with PAC ACARS running, and locks from pushback, like the real thing."},
 {"id": "20261113-a300-cg", "date": "November 13, 2026", "kind": "Improvement", "title": "A300-600F balance matches the aircraft", "body": "The A300's load sheet CG is now calibrated against the iniBuilds EFB at light and heavy loads (within about 0.1% MAC), and the load sheet checks it against the real 15–34% MAC limits."},
 {"id": "20261113-crew-rest", "date": "November 13, 2026", "kind": "New feature", "title": "Crew rest and hotels", "body": "Away from your home base? On a trip, PAC pays your hotel. At KCVG headquarters there are 6 free crew rest rooms, first come, first served. Anywhere else by choice: night 1 is free, nights 2 to 4 are paid from your wallet at the local rate, then charges stop. Your Dashboard shows where you're staying tonight.", "view": "dashboard", "label": "Open Dashboard"},
 {"id": "20261113-badge-signin", "date": "November 13, 2026", "kind": "New feature", "title": "Badge sign-in", "body": "Skip the password: issue your crew badge to your computer (Profile → Sign in with this badge), then drag your badge onto the reader to sign in. Beep, green light, you're in. You can also have the site ask for your badge every time you visit.", "view": "profile", "label": "Open my profile"},
 {"id": "20261112-crew-badges", "date": "November 12, 2026", "kind": "New feature", "title": "Crew badges for everyone, redesigned", "body": "Every pilot's crew page now shows their crew badge, and the badge has a realistic new look: fine-line security pattern, microprint, a holographic photo with a verification seal, a chip, signature and issue stamp. Your badge number now follows your home base, and Download badge saves the front and back.", "view": "profile", "label": "See my badge"},
 {"id": "20261113-daynight", "date": "November 13, 2026", "kind": "New feature", "title": "Day and night on the live map", "body": "The live map and globe have a ☀︎ Day / night button showing where the sun is up right now, with dawn and dusk twilight bands, updated every minute.", "view": "live", "label": "Open the live map"},
 {"id": "20261113-od-swap", "date": "November 13, 2026", "kind": "Improvement", "title": "From / To search with a swap button", "body": "The scheduled network now has separate From and To boxes, and ⇄ reverses the direction in one click.", "view": "missions", "label": "Find a flight"},
 {"id": "20261113-cargo-late", "date": "November 13, 2026", "kind": "Improvement", "title": "Cargo is late only if it misses its own deadline", "body": "Each shipment is now judged against its own promised delivery time, not the flight's block time. Shipments wrongly marked late before have been corrected, and the shipper complaints they caused were withdrawn."},
 {"id": "20261113-hubs", "date": "November 13, 2026", "kind": "New feature", "title": "PAC can open new hubs", "body": "Management can now open new PAC hubs where pilots fly most. A new hub gets missions, trips, cargo orders and a warehouse, and you can choose it as your home base."},
 {"id": "20261113-discord-flights", "date": "November 13, 2026", "kind": "Improvement", "title": "Cleaner flight posts in Discord", "body": "Each flight posts once when you take off and once when you land in #flight-log, never twice."},
 {"id": "20261113-network-nav", "date": "November 13, 2026", "kind": "Improvement", "title": "Easier way back from the network pages", "body": "The Cargo network and tracking pages now have a ← Back to PAC button and menu links, and network buttons inside the site keep the left menu. Thanks, Alex!"},
 {"id": "20261104-acars-11", "date": "November 4, 2026", "kind": "New feature", "title": "PAC ACARS 1.1", "body": "A moving map, a landing debrief after every touchdown, landing practice (circuits and touch-and-goes, never filed), stable approach checks at 1,000 and 500 ft, SOP reminders, fuel checks against your SimBrief plan and your PAC flight in your Discord status. Install 1.1 from Downloads once: from then on PAC ACARS updates itself.", "view": "downloads", "label": "Get PAC ACARS 1.1"},
 {"id": "20261104-academy", "date": "November 4, 2026", "kind": "New feature", "title": "PAC Academy", "body": "Free, interactive 737-800 training: PAC's standard startup flow (based on Boeing's normal procedures) and 22 lessons on every panel of the cockpit, with real screenshots. Open to everyone, members or not, under Resources \u2192 PAC Academy.", "view": "/academy/", "label": "Open PAC Academy"},
 {"id": "20261103-group-flight", "date": "November 3, 2026", "kind": "New feature", "title": "An optional weekly group flight", "body": "Each week there's one suggested route under Crew room \u2192 Group flight. It's entirely optional: fly it at the set time (Saturdays at 23:00 UTC) if you'd like company, or on your own any time that weekend, offline or online, with or without voice chat. It goes out from Cincinnati one week and back home the next, and everyone who flies it shows on the page."},
 {"id": "20261103-globe", "date": "November 3, 2026", "kind": "New feature", "title": "The live map as a globe", "body": "Operations \u2192 Live map now has a Flat map / Globe switch. Spin the globe to follow PAC flights and the parked fleet, with long routes drawn as they really curve. The station buttons and filters work on both, and your choice is remembered on this computer."},
 {"id": "20261103-sports", "date": "November 3, 2026", "kind": "New feature", "title": "Sports and events missions", "body": "A new Sports and events category on the mission board. Fly a hometown pro team's equipment to its games abroad (football, basketball, hockey and baseball, each in its real season), European clubs' summer tours, stock cars to Mexico City, motorcycle grand prix flyaways, bobsleds for the winter World Cup, show-jumping horses and stadium concert tours. Each comes with its own handling notes.", "view": "missions", "label": "Find a sports mission"},
 {"id": "20261103-missions", "date": "November 3, 2026", "kind": "New feature", "title": "Six urgent requests and new kinds of work", "body": "Up to six urgent requests at a time, with new kinds: ship engine parts, grid repairs after a blackout, antivenom, rescue team equipment, servers for a failed data center, race team spares and team equipment for tomorrow's game. The mission board adds durian and mango seasons, sashimi tuna, Alaskan king crab, fashion weeks, the 11.11 shopping festival, smartphone launches, ship spares, data-center builds, Indian Ocean cyclone relief, rhino reintroductions, honeybees and new hot-and-high challenge airports in Africa.", "view": "missions", "label": "See the mission board"},
 {"id": "20261103-divisions", "date": "November 3, 2026", "kind": "New feature", "title": "Fleet divisions", "body": "The fleet is now organized in four divisions: PAC Feeder (the 737s), PAC Mainline (A300, 757, 767), PAC Heavy (MD-11, 777F, 747-400F and 747-8F) and PAC Heritage (727s, 737-200 and 747-200). They show on the Fleet page, on every flight, in your logbook and in My stats, and the mission board can show one division at a time. Your rank and ratings still decide what you fly.", "view": "fleet", "label": "Meet the divisions"},
 {"id": "20261103-roster", "date": "November 3, 2026", "kind": "New feature", "title": "Public roster and flight log", "body": "Crew room now has a Roster and flight log page that anyone can see: every active pilot (first name and initial only), rank, hours and the airline's latest accepted flights. It's part of getting PAC listed with VATSIM and IVAO.", "view": "roster", "label": "Open the roster"},
 {"id": "20261102-partner-photos", "date": "November 2, 2026", "kind": "New feature", "title": "Partner flights look the part", "body": "Fly for FedEx, UPS, Atlas, Cathay, Emirates or Qatar and your landing and takeoff cards now show a real photo of that airline's aircraft, with its logo and Flown for on the card. Partner flights also use the partner's real registrations in SimBrief, on your paperwork and in your logbook.", "view": "missions", "label": "See partner requests"},
 {"id": "20261103-faster", "date": "November 3, 2026", "kind": "Improvement", "title": "A faster website", "body": "Pages for signed-in pilots load several times faster, and your browser now keeps the site's files instead of checking each one on every visit. A website update or restart also no longer drops a flight you're tracking: PAC ACARS picks it straight back up.", "view": "dashboard", "label": "Back to your dashboard"},
 {"id": "20261103-downloads", "date": "November 3, 2026", "kind": "Improvement", "title": "Find your livery faster", "body": "Downloads now filters liveries by simulator and aircraft, and remembers your choice. Links in descriptions are clickable.", "view": "downloads", "label": "Open Downloads"},
 {"id": "20261103-handbook", "date": "November 3, 2026", "kind": "Improvement", "title": "Handbook brought up to date", "body": "The pilot handbook now covers the four-tab flight planning page and Generate OFP, the full scoring table, checkride and direct-entry rules, divisions and partner flights. A printable PDF (v1.3) is in Downloads.", "view": "handbook", "label": "Read the handbook"},
 {id:"20261028-training",date:"October 28, 2026",kind:"New feature",title:"Your checkride. Your choice of airport.",body:"Company-funded checkrides now offer dedicated training at supported airports or an available fleet aircraft with free positioning travel. Same standards, free retakes, no paid ferry needed. Dedicated sessions leave the operational fleet and your normal station untouched.",view:"career/qualifications",label:"Start a checkride"},
{"id": "20261027-dashboard-crew", "date": "October 27, 2026", "kind": "New feature", "title": "Your next crew flight, on the dashboard", "body": "See the next three crew flights with UTC and local departure times, open places and your participation status. View or join a flight and download a calendar entry. Calendar downloads are snapshots; check the board for later changes.", "view": "dashboard", "label": "See upcoming crew flights"},
{"id": "20261027-plan-with-crew", "date": "October 27, 2026", "kind": "Improvement", "title": "Take a mission straight to Fly Together", "body": "Choose Plan with crew in mission details to pre-fill the route and selected aircraft type. Add your departure time and simulator setup before posting. A crew post does not reserve an aircraft.", "view": "missions", "label": "Choose a mission"},
{"id": "20261027-reservations", "date": "October 27, 2026", "kind": "Improvement", "title": "See who has an aircraft reserved", "body": "Aircraft views now show the pilot, flight and planned route when booking details are available. Live ACARS reporting distinguishes flying from ground operations. Availability is checked again when you book.", "view": "fleet", "label": "Check the fleet"},
{"id": "20261027-fly-together", "date": "October 27, 2026", "kind": "New feature", "title": "Find someone to fly with", "body": "Post a shared-cockpit or group flight under Crew room → Fly together. Include your simulator, add-on and an optional Discord username. Join or leave a flight, manage your crew and close finished plans. Past departures leave the upcoming list automatically. Bookings, qualifications and flight credit remain separate.", "view": "crewplans", "label": "Open Fly together"},
{"id": "20261027-parked-fleet", "date": "October 27, 2026", "kind": "New feature", "title": "Find your next aircraft on the map", "body": "Toggle the parked fleet on the Live map to see aircraft grouped at their recorded airport. Filter by type, qualifications or availability, then find departures, arrange pilot travel or request an aircraft-delivery quote before confirming payment.", "view": "live", "label": "Explore the fleet map"},
{"id": "20261026-flight-debrief", "date": "October 26, 2026", "kind": "Improvement", "title": "Understand your flight, not just your score", "body": "Your PIREP now explains recorded deductions, highlights what went well and summarizes shipment timing. Section shortcuts make landing, takeoff and replay details easier to reach. Scores and pay are unchanged; unverified cargo condition and customer handover are clearly identified.", "view": "logbook", "label": "Review your flights"},
 {id:'20261025-short-heavy',date:'October 25, 2026',kind:'New feature',title:'Heavy freighters. Short sectors.',body:'Find 100–300 NM heavy cargo jobs using the Short-haul heavies filter on All flights or the Job board. Four rotating cargo scenarios, estimated block time and 80 handling points included in the reward. Routes favor stations with an available heavy at generation time; availability can change.',view:'missions',label:'Find short-haul heavy jobs'},
 {id:'20261022-preparation',kind:'New feature',title:'Your flight preparation, in one place',body:'My bids now shows your assigned aircraft, recorded pilot location, release signature and ACARS tracking connection, with actions for each step.',view:'bids',label:'Open My bids'},
 {id:'20261022-cargo',kind:'Improvement',title:'Know the cargo before you book',body:'Mission details bring the cargo brief and any arrival deadline together. Booking expiry is shown separately from delivery time.',view:'missions',label:'Browse missions'},
 {id:'20261022-patches',kind:'New feature',title:'Choose your featured patches',body:'Feature up to three owned shop patches on your profile and crew badge, and arrange their order. All your purchases stay in your collection.',view:'shop',label:'Open the shop'}
];
function updatesKey(){return 'pac-read-updates-'+(S.me?.id||'guest')}
function readUpdates(){try{return JSON.parse(localStorage.getItem(updatesKey())||'[]')}catch(e){return []}}
function updateNewsBadge(){const read=readUpdates(),count=PAC_UPDATES.filter(u=>!Array.isArray(read)||!read.includes(u.id)).length;const badge=document.getElementById('pxUpdateCount');if(badge){badge.textContent=count;badge.hidden=!S.me||!count}}
function loadWhatsNew(){updateNewsBadge();const filter=S.updateFilter||'All';$('#updatesRoot').innerHTML=`<div class="profile-bar"><h1>What’s new</h1><button class="btn ghost small" id="pxMarkRead">Mark all as read</button></div><p class="muted">Recent site changes. Operational notices remain in company NOTAMs.</p><p class="notice">Your feedback helps shape PAC. We’re listening and working to make the site better for everyone—this is your VA too. Keep sharing ideas and use Report a problem when something needs fixing.</p><div class="row">${['All','New feature','Improvement'].map(k=>`<button class="btn ${filter===k?'':'ghost'} small" data-update-filter="${k}" aria-pressed="${filter===k}">${k}</button>`).join('')}</div><div class="px-updates">${PAC_UPDATES.filter(u=>filter==='All'||u.kind===filter).map(u=>`<article class="px-prep"><small>${u.date || "October 22, 2026"} · ${u.kind}</small><h2>${u.title}</h2><p>${u.body}</p>${u.view ? `<button class="btn ghost small" data-update-go="${u.view}">${u.label} →</button>` : ""}</article>`).join('')}</div><p class="muted">Read status is saved for your pilot on this browser.</p>`;
 $('#pxMarkRead').onclick=()=>{try{localStorage.setItem(updatesKey(),JSON.stringify(PAC_UPDATES.map(u=>u.id)));updateNewsBadge();toast('Updates marked as read.')}catch(e){toast('This browser could not save your read status.')}};
 document.querySelectorAll('[data-update-filter]').forEach(b=>b.onclick=()=>{S.updateFilter=b.dataset.updateFilter;loadWhatsNew()});
 document.querySelectorAll('[data-update-go]').forEach(b=>b.onclick=()=>{const v=b.dataset.updateGo;if(v.startsWith('/')){location.href=v;return}if(v==='shop')S.shopTab='mine';show(v)});
}
window.addEventListener('hashchange',updateNewsBadge);

function manualReportDetail(p){
 const m=p.detail.manual;
 $('#detailTitle').textContent=`Manual report · ${p.flight_number}`;
 $('#detailBody').innerHTML=`<p><b>${esc(p.review_status)}</b> · ${esc(p.dep)} → ${esc(p.arr)} · ${esc(p.airframe)} · ${hm(p.block_min)}</p><p>Departure: ${new Date(m.departed*1000).toUTCString()}</p><h3>Why ACARS was not used</h3><p style="white-space:pre-wrap">${esc(m.reason)}</p><h3>Supporting information</h3><p style="white-space:pre-wrap">${esc(m.evidence_note||'No supporting information supplied.')}</p>${m.has_screenshot?`<a href="/api/manual-pireps/${Number(p.id)}/evidence" target="_blank" rel="noopener">Open supporting screenshot</a>`:''}<p>Staff note: ${esc(p.review_note||'Awaiting review')}</p><p>Manual reports have no ACARS score, landing measurements, performance bonuses or checkride credit. Approval awards block hours and basic flight pay.${m.completed ? ` Staff also completed the flight: ${m.completed.cargo ? `${m.completed.cargo} shipment${m.completed.cargo === 1 ? "" : "s"} delivered, ` : ""}${m.completed.aircraft_moved ? "aircraft moved, " : ""}${m.completed.booking_closed ? "booking closed" : "no matching booking"}.` : " When they approve it, staff can also deliver the booked cargo and move the aircraft."}</p>`;
 $('#detailDlg').showModal();
}
function openManualReport(){
 let dlg=$('#manualPirepDlg');if(!dlg){dlg=document.createElement('dialog');dlg.id='manualPirepDlg';dlg.style.cssText='width:min(640px,94vw);max-height:90vh;overflow:auto;padding:24px';document.body.append(dlg);}
 dlg.innerHTML=`<form id="manualPirepForm"><h2>Submit a manual PIREP</h2><p>Forgot ACARS or lost tracking? Report the completed flight here. Staff must approve it before hours and basic flight pay are credited.</p><p>No score, landing bonuses or checkride credit. If this was your booked flight, staff can deliver its cargo and move the aircraft when they approve it.</p>${[['flight','Flight number','text'],['dep','Departure ICAO','text'],['arr','Arrival ICAO','text'],['tail','PAC tail number','text'],['departed','Departure date and time (UTC)','datetime-local'],['minutes','Total block time in minutes','number']].map(([id,label,type])=>`<div class="field"><label for="mp-${id}">${label}</label><input id="mp-${id}" name="${id}" type="${type}" required ${id==='minutes'?'min="5" max="1440" step="1"':''}></div>`).join('')}<div class="field"><label for="mp-aircraft">Aircraft type</label><select id="mp-aircraft" name="aircraft">${Object.entries(S.fleet).map(([k,v])=>`<option value="${esc(k)}">${esc(v.name||k)}</option>`).join('')}</select></div><div class="field"><label for="mp-reason">Why was the flight not tracked?</label><textarea id="mp-reason" name="reason" required minlength="10" maxlength="2000"></textarea></div><div class="field"><label for="mp-evidence">Supporting details (optional)</label><textarea id="mp-evidence" name="evidence_note" maxlength="2000" placeholder="Simulator logbook entry, booking reference, or an explanation if no screenshot is available"></textarea></div><div class="field"><label for="mp-image">Screenshot (optional, PNG/JPEG, up to 2 MB)</label><input id="mp-image" type="file" accept="image/png,image/jpeg"></div><p id="mp-error" role="alert"></p><button class="btn" type="submit">Submit for staff review</button> <button class="btn ghost" type="button" id="mp-cancel">Cancel</button></form>`;
 $('#mp-cancel').onclick=()=>dlg.close();
 $('#manualPirepForm').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('[type=submit]');button.disabled=true;$('#mp-error').textContent='';try{const data=Object.fromEntries(new FormData(e.target));const f=$('#mp-image').files[0];if(f){if(f.size>2*1024*1024)throw Error('Screenshot must be under 2 MB.');data.screenshot=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(f)});}await api('/api/manual-pireps',{method:'POST',body:data});dlg.close();toast('Manual PIREP submitted. Awaiting staff review.');await loadLogbook();}catch(err){$('#mp-error').textContent=err.message||'Unable to submit. Please try again.';}finally{button.disabled=false;}};
 dlg.showModal();
}

const PAC_CHARTER_CUSTOMERS=[{"id": "dhl", "name": "DHL Global Forwarding", "role": "Air freight connections", "logo": "/static/charter-customers/dhl.svg", "source": "https://group.dhl.com/en/about-us/corporate-divisions/global-forwarding-freight.html", "shipments": [{"id": "priority-parts", "title": "Production-line spares", "cargo": "Crated production-line spares", "brief": "A factory has grouped replacement components for its next maintenance shift. Carry the consolidated shipment to the receiving distribution station."}, {"id": "medical", "title": "Medical equipment", "cargo": "Packaged medical equipment", "brief": "Move packaged diagnostic equipment to a regional distribution center for onward road delivery."}]}, {"id": "dachser", "name": "DACHSER", "role": "Industrial distribution", "logo": "/static/charter-customers/dachser.svg", "source": "https://www.dachser.com/en/air-sea-logistics-network-53", "shipments": [{"id": "industrial", "title": "Industrial replenishment", "cargo": "Palletized industrial components", "brief": "Connect two regional distribution points with a consolidated shipment of factory components."}, {"id": "retail", "title": "Retail replenishment", "cargo": "Packaged retail stock", "brief": "Bring a mixed shipment of retail goods to a receiving depot preparing its next distribution round."}]}, {"id": "dsv", "name": "DSV", "role": "Project and automotive freight", "logo": "/static/charter-customers/dsv.svg", "source": "https://www.dsv.com/en", "shipments": [{"id": "automotive", "title": "Automotive supply run", "cargo": "Crated automotive components", "brief": "Move replacement assemblies to a regional parts center supporting several customers."}, {"id": "project", "title": "Project cargo connection", "cargo": "Crated machinery subassemblies", "brief": "Fly the air leg of a project shipment. The receiving team handles onward road transport; these are multiple crates, not a certified oversized load."}]}, {"id": "kn", "name": "Kuehne+Nagel", "role": "Healthcare and technology", "logo": "/static/charter-customers/kn.png", "source": "https://home.kuehne-nagel.com/en/-/services/air-freight/overview", "shipments": [{"id": "technology", "title": "Technology distribution", "cargo": "Packaged electronics and server components", "brief": "Deliver a consolidated technology shipment to a distribution station preparing customer orders."}, {"id": "healthcare", "title": "Healthcare supply run", "cargo": "Packaged laboratory equipment", "brief": "Move laboratory equipment and non-temperature-controlled medical supplies for regional distribution."}]}, {"id": "ceva", "name": "CEVA Logistics", "role": "Automotive and aerospace", "logo": "/static/charter-customers/ceva.png", "source": "https://www.cevalogistics.com/en/news-and-media/newsroom/ceva-welcomes-bollore-logistics", "shipments": [{"id": "aerospace", "title": "Maintenance work package", "cargo": "Crated aircraft parts and tooling", "brief": "A maintenance team is preparing its next work package. Deliver boxed components and tooling together."}, {"id": "automotive", "title": "Factory components", "cargo": "Palletized automotive spares", "brief": "Carry a consolidated factory shipment between regional logistics centers."}]}, {"id": "maersk", "name": "Maersk", "role": "Air and onward distribution", "logo": "/static/charter-customers/maersk.png", "source": "https://www.maersk.com/transportation-services/air-freight", "shipments": [{"id": "retail", "title": "Distribution connection", "cargo": "Packaged consumer goods", "brief": "Carry the air segment of a shipment with onward warehouse and road distribution."}, {"id": "industrial", "title": "Supply-chain connection", "cargo": "Crated industrial components", "brief": "Connect a dispatch warehouse with a receiving logistics center using a PAC freighter."}]}, {"id": "noatum", "name": "Noatum Logistics", "role": "Industrial and project logistics", "logo": "/static/charter-customers/noatum.png", "source": "https://www.noatumlogistics.com/air-freight/", "shipments": [{"id": "project", "title": "Project supplies", "cargo": "Crated equipment components", "brief": "Transport a consolidated project shipment to the airport nearest the receiving logistics team."}, {"id": "spares", "title": "Regional spares delivery", "cargo": "Crated maintenance spares", "brief": "Move replacement parts and workshop supplies between regional distribution points."}]}];
PAC_CHARTER_CUSTOMERS.push(
 {"id":"geodis","name":"GEODIS","role":"Global freight forwarding","logo":"/static/charter-customers/geodis.svg","source":"https://geodis.com/","shipments":[{"id":"industrial-spares","title":"Industrial spares","cargo":"Crated industrial replacement parts","brief":"Carry a consolidated shipment of replacement parts to a regional distribution center for onward delivery."},{"id":"retail-stock","title":"Retail replenishment","cargo":"Packaged retail merchandise","brief":"Move packaged retail goods between logistics facilities ahead of a scheduled distribution cycle."}]},
 {"id":"expeditors","name":"Expeditors","role":"Air freight and time-critical logistics","logo":"/static/charter-customers/expeditors.gif","source":"https://www.expeditors.com/","shipments":[{"id":"production-spares","title":"Time-critical production spares","cargo":"Crated production-line replacement parts","brief":"A production facility needs replacement components for an upcoming maintenance window. Deliver the consolidated shipment to its regional logistics hub."},{"id":"electronics","title":"Electronics distribution","cargo":"Packaged electronic equipment","brief":"Transport packaged electronics to a distribution facility for onward delivery to business customers."}]},
 {"id":"nx","name":"NX Group","role":"Nippon Express air freight and supply chains","logo":"/static/charter-customers/nx.svg","source":"https://www.nipponexpress.com/","shipments":[{"id":"automotive","title":"Automotive components","cargo":"Crated automotive components","brief":"Move production components between regional logistics centers supporting an automotive supply chain."},{"id":"industrial-parts","title":"Industrial parts delivery","cargo":"Packaged industrial machinery parts","brief":"Deliver a consolidated shipment of machinery parts to a receiving distribution center."}]}
);
function charterCustomerPanel(c){
 if(!$('#charterCustomerStyle')){const s=document.createElement('style');s.id='charterCustomerStyle';s.textContent='.cc-panel{grid-column:1 / -1;width:100%}.cc-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}.cc-card{background:var(--panel,#fff);color:var(--ink,#20252b);border:1px solid var(--line,#d8dde4);padding:16px;border-radius:6px;text-align:left;cursor:pointer;font:inherit}.cc-card[aria-pressed=true]{outline:2px solid #c80000;outline-offset:-2px}.cc-logo{display:flex;align-items:center;justify-content:center;height:60px;background:white;border-radius:4px;margin-bottom:12px;padding:8px}.cc-logo img{max-width:100%;max-height:44px;object-fit:contain}.cc-logo img[src*="maersk"]{max-width:180px;max-height:58px}.cc-card b,.cc-card small{display:block}.cc-card small{margin-top:4px}.cc-brief{border-left:4px solid #c80000;padding:16px;background:var(--panel,#fff);margin:14px 0}@media(max-width:900px){.cc-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:420px){.cc-grid{grid-template-columns:1fr}}.cc-textmark{font-weight:bold;color:#24324b;font-size:19px}';document.head.append(s);}
 const current=PAC_CHARTER_CUSTOMERS.find(x=>x.id===c.customer_id),shipment=current?.shipments.find(x=>x.id===c.shipment_id);
 return `<section class="cc-panel"><div class="kicker">PAC CHARTER DESK</div><h2>Choose who you're carrying for</h2><p>Pick a simulated customer and shipment, then plan your own PAC flight.</p><div class="cc-grid"><button type="button" class="cc-card" data-customer="" aria-pressed="${!current}"><span class="cc-logo cc-textmark">Your charter</span><b>Independent charter</b><small>Your own cargo or ferry flight</small></button>${PAC_CHARTER_CUSTOMERS.map(x=>`<button type="button" class="cc-card" data-customer="${x.id}" aria-pressed="${c.customer_id===x.id}"><span class="cc-logo">${x.logo?`<img src="${x.logo}" alt="${esc(x.name)}">`:`<span class="cc-textmark">${esc(x.name)}</span>`}</span><b>${esc(x.name)}</b><small>${esc(x.role)}</small></button>`).join('')}</div><p class="muted" style="font-size:12px">Fictional flight-simulation assignments. No affiliation, sponsorship or endorsement is implied. You fly a PAC aircraft.</p>${current?`<div class="field"><label for="ccShipment">Shipment brief</label><select id="ccShipment">${current.shipments.map(x=>`<option value="${x.id}" ${x.id===c.shipment_id?'selected':''}>${esc(x.title)}</option>`).join('')}</select></div><div class="cc-brief"><b>${esc(shipment?.title||'Choose a shipment')}</b><p>${esc(shipment?.brief||'')}</p><small>Set the cargo weight and review aircraft availability below. Standard PAC booking rules and pay apply.</small></div>`:''}</section>`;
}
function bindCharterCustomers(c){
 const choose=(id,sid)=>{const customer=PAC_CHARTER_CUSTOMERS.find(x=>x.id===id),shipment=customer?.shipments.find(x=>x.id===sid)||customer?.shipments[0];c.customer_id=id;c.shipment_id=shipment?.id||'';c.cargo=shipment?.cargo||'General cargo';S.charterMission=null;S.selected=null;S.ofp=null;S.planned=false;renderMissions();};
 document.querySelectorAll('[data-customer]').forEach(b=>b.onclick=()=>choose(b.dataset.customer));if($('#ccShipment'))$('#ccShipment').onchange=e=>choose(c.customer_id,e.target.value);
}

/* Evidence-led presentation only: does not change scoring or pay. */
function pacDebrief(p, d = p) {
  const e = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n = v => typeof v === 'number' && Number.isFinite(v);
  const la = d.landing_analysis || {}, ta = d.takeoff_analysis || {};
  const good = [], focus = [], facts = [];
  for (const [label, points] of (d.breakdown || [])) {
    if (!(points < 0)) continue;
    const readable = pacScoreLabel(label);
    const next = /landing/i.test(label) ? 'Review the flare and touchdown trace alongside the landing load and runway position.' : /250.*(?:fl100|ias)/i.test(label) ? 'Review the speed trace below FL100 and the recorded speed-limit event.' : 'Review the corresponding event and flight trace below.';
    focus.push(`${readable}: ${points} points. ${next}`);
  }
  if (p.source === 'Manual') return '<section class="pac-debrief" data-pd-section="Summary"><h3>Flight debrief unavailable</h3><p>This manual report has no recorded flight telemetry.</p></section>';
  if (la.stable === true) good.push('Approach speed and descent stayed within PAC’s recorded stability checks.');
  if (la.stable === false) focus.push(`${la.stability_note || 'The approach exceeded PAC’s stability checks'}. Review the final approach trace and aim to settle the aircraft earlier.`);
  if (n(d.bounces)) (d.bounces === 0 ? good : focus).push(d.bounces === 0 ? 'No landing bounce was recorded.' : `${d.bounces} bounce(s) recorded. Review the touchdown sequence before your next flight.`);
  if (n(la.rate_fpm)) facts.push(`Touchdown at ${la.rate_fpm} fpm${n(la.g) ? ` and ${la.g.toFixed(2)} G` : ''}${n(la.touchdown_ft) ? `, ${la.touchdown_ft.toLocaleString()} ft past the threshold` : ''}${n(la.float_s) ? ` after ${la.float_s} s of float` : ''}.`);
  const tips = [];
  if (n(la.float_s) && la.float_s > 8) tips.push(`You floated ${la.float_s} seconds from 50 ft to touchdown. Cross the threshold at Vref + 5 kt and close the thrust by 20 ft.`);
  if (n(la.touchdown_ft) && la.touchdown_ft > 3000) tips.push(`Long landing: ${la.touchdown_ft.toLocaleString()} ft past the threshold. Aim for the touchdown zone markers, 1,000 to 2,000 ft down the runway.`);
  else if (n(la.touchdown_ft) && la.touchdown_ft < 500) tips.push(`Short: you touched down ${la.touchdown_ft.toLocaleString()} ft past the threshold. Keep the aiming point steady until the flare.`);
  if (n(la.centerline_ft) && Math.abs(la.centerline_ft) > 15) tips.push(`${Math.abs(la.centerline_ft)} ft ${la.centerline_ft > 0 ? 'right' : 'left'} of the centerline. Small rudder inputs in the flare keep you lined up.`);
  focus.push(...tips);
  if (!tips.length && n(la.touchdown_ft)) good.push(`Touched down in the zone, ${la.touchdown_ft.toLocaleString()} ft past the threshold${n(la.rate_fpm) ? `, at ${la.rate_fpm} fpm` : ''}.`);
  if (n(ta.climb_fpm)) facts.push(`Initial climb averaged ${Math.round(ta.climb_fpm).toLocaleString()} fpm between 50 and 1,000 ft.`);
  if (ta.touchback === true) focus.push('Ground contact was detected after becoming airborne. Review the takeoff trace and simulator conditions.');
  if (ta.tail_strike === true) focus.push('Recorded pitch reached the configured tail-clearance limit. This is a calculated indication, not confirmation of physical contact.');
  if (n(d.trip_burn_lbs) && n(d.planned_trip_lbs) && d.planned_trip_lbs > 0) {
    const pct = (d.trip_burn_lbs / d.planned_trip_lbs - 1) * 100;
    facts.push(`Trip fuel: ${Math.round(d.trip_burn_lbs).toLocaleString()} lb used versus ${Math.round(d.planned_trip_lbs).toLocaleString()} lb planned (${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%). Winds, routing and cruise level all affect this.`);
  }
  const metric = (title, value, unit, note) => `<div class="pd-metric"><small>${e(title)}</small><strong>${n(value) ? e(value.toLocaleString()) : 'Not recorded'}${n(value) ? `<span> ${e(unit)}</span>` : ''}</strong><small>${e(note)}</small></div>`;
  const list = a => a.map(s => `<p>${e(s)}</p>`).join('');
  return `<section class="pac-debrief" data-pd-section="Summary"><div class="pd-head"><div><small>PAC · FLIGHT DEBRIEF</small><h2>Your flight, explained.</h2><p>${e(p.dep)} → ${e(p.arr)} · ${e(p.flight_number)}</p></div><div class="pd-grade"><small>Flight grade</small><strong>${e(p.grade || 'Unscored')}</strong><span>${n(p.score) ? `${e(p.score)} / 100` : 'Score unavailable'}</span></div></div>
    <div class="pd-grid">${metric('Touchdown', la.rate_fpm, 'fpm', 'Recorded vertical speed')}${metric('Landing load', la.g, 'G', 'Around touchdown')}${metric('Touchdown speed', la.ias, 'kt', 'Indicated airspeed')}${metric('Takeoff roll', ta.roll_ft, 'ft', 'Recorded ground roll')}</div>
    <div class="pd-columns"><div><h3>What went well</h3>${list(good) || '<p>Not enough recorded evidence to identify strengths.</p>'}</div><div><h3>${focus.length ? 'Technique notes for next time' : 'Keep it up'}</h3>${list(focus) || '<p>Nothing to work on from this flight. Fly the next one the same way.</p>'}${focus.length && !(d.breakdown || []).some(x => x[1] < 0) ? '<p class="muted" style="font-size:13px">These notes don\'t lower your grade. They\'re what a check captain would mention after the flight.</p>' : ''}</div></div>
    ${pacAfterAction(p.debrief || d.debrief)}
    ${pacShipmentDebrief(p, d)}
    <details><summary>The evidence behind the feedback</summary>${list(facts) || '<p>No detailed measurements available for this report.</p>'}<p class="pd-note">The approach check looks at your speed spread below 1,000 ft and your descent rate below 500 ft.</p></details>
    <details><summary>How this relates to your score</summary><p>What added to or took away from your score:</p>${(d.breakdown || []).map(x => `<p>${e(pacScoreLabel(x[0]))}: <b>${e(x[1])}</b></p>`).join('')}</details></section>`;
}
function pacAfterAction(db) {
  if (!db) return "";
  const e = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const rows = db.planned_actual || [], cargo = db.cargo || [], cu = db.customer || {};
  const mark = r => r.ok === true ? '<span class="aar-ok">Within plan</span>' : r.ok === false ? '<span class="aar-bad">Outside plan</span>' : '<span class="muted">Not compared</span>';
  return `<section class="aar" data-pd-section="After-action review"><h3>After-action review</h3>
    <div class="aar-cols">
      <div class="aar-box ${e(cu.tone)}"><small>Customer feedback</small><div style="font-size:13px;font-weight:600;margin:2px 0 6px">${e(String(cu.from || '').split(/,\s*/).slice(0, 3).join(' · '))}</div><p>${e(cu.text)}</p></div>
      ${db.people ? `<div class="aar-box ${e(db.people.tone)}"><small>People on board</small><p>${e(db.people.text)}</p></div>` : ""}
      <div class="aar-box"><small>Dispatcher debrief</small><p>${e(db.dispatcher)}</p>${(db.takeaways || []).length ? `<ul>${db.takeaways.map(t => `<li>${e(t)}</li>`).join("")}</ul>` : ""}</div>
    </div>
    ${rows.length ? `<h4>Planned versus actual</h4><div class="aar-wrap"><table class="aar-table"><thead><tr><th>Item</th><th class="r">Planned</th><th class="r">Actual</th><th class="r">Variance</th><th></th></tr></thead><tbody>
      ${rows.map(r => `<tr class="${r.ok === false ? "bad" : ""}"><td>${e(r.what)}</td><td class="r mono">${r.planned == null ? "–" : e(r.planned) + (r.unit && r.unit !== "h:mm" ? ` ${e(r.unit)}` : "")}</td><td class="r mono">${r.actual == null ? "Not recorded" : e(r.actual) + (r.unit && r.unit !== "h:mm" ? ` ${e(r.unit)}` : "")}</td><td class="r mono">${r.variance == null ? "–" : e(r.variance)}${r.pct != null ? ` <small>(${r.pct > 0 ? "+" : ""}${e(r.pct)}%)</small>` : ""}</td><td>${mark(r)}</td></tr>`).join("")}
    </tbody></table></div>` : ""}
    ${cargo.some(c => c.care) ? `<div class="care-box"><h4>How the sensitive freight rode</h4>${cargo.filter(c => c.care).map(c => `<div class="care-row"><div><span class="care-tag ${e(c.care.status)}">${e(c.care.label)}</span> <b>${e(c.contents)}</b> <small class="mono muted">${e(c.awb)}</small></div><ul>${c.care.log.map(l => `<li>${e(l)}</li>`).join("")}</ul></div>`).join("")}</div>` : ""}
    ${cargo.length ? `<details class="aar-cargo"><summary>Customer cargo results · ${e(db.on_time)}</summary><div class="aar-wrap"><table class="aar-table"><thead><tr><th>Air waybill</th><th>Customer journey</th><th>Commodity</th><th class="r">Weight</th><th>Delivery</th><th class="r">Charges</th></tr></thead><tbody>
      ${cargo.map(c => `<tr><td class="mono">${trackAwb(c.awb)}</td><td>${e(c.shipper)} → ${e(c.consignee)}</td><td>${e(c.contents)}</td><td class="r mono">${c.weight_lbs != null ? Number(c.weight_lbs).toLocaleString() + " lb" : "–"}</td><td><b class="${/LATE|NOT|HELD/.test(c.status) ? "aar-bad" : "aar-ok"}">${e(c.status)}</b>${c.delivered ? `<br><small class="mono">${e(c.delivered)}</small>` : ""}${c.care ? `<br><span class="care-tag ${e(c.care.status)}">${e(c.care.label)}</span>` : ""}</td><td class="r mono">${c.charges != null ? "$" + Number(c.charges).toLocaleString("en-US", { maximumFractionDigits: 0 }) : "–"}</td></tr>`).join("")}
    </tbody></table></div></details>` : ""}
  </section>`;
}
function pacShipmentDebrief(p, d) {
  if(d?.training || p.training)return `<section class="pd-shipment" data-pd-section="Shipment"><h3>Company-funded training</h3><p>Training ballast only. No commercial shipment, customer handover, profit share, reward points or campaign cargo credit.</p><p>${(d?.training||p.training).mode==='dedicated'?'Dedicated session: operational fleet and normal pilot station unchanged.':'Fleet checkride: normal aircraft and pilot position tracking applies.'}</p><p>Accepted attempts count toward career hours and flight count and receive standard flight pay plus applicable skill or gear bonuses. A failed checkride does not grant a qualification.</p></section>`;
  const e = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n = v => typeof v === 'number' && Number.isFinite(v);
  const delivered = ['Delivered', 'Delivered late'].includes(p.status);
  const pending = p.review_status === 'Pending';
  const deadline = d.urgent?.deliver_by, arrived = d.oooi?.in;
  let timing = 'No delivery deadline recorded.', comparison = '';
  if (n(deadline) && n(arrived) && delivered) {
    const seconds = arrived - deadline, minutes = Math.abs(seconds / 60);
    timing = seconds <= 0 ? 'Delivery deadline met' : 'Delivery deadline missed';
    comparison = `On block ${minutes < 1 ? 'less than 1' : Math.round(minutes)} min ${seconds <= 0 ? 'before' : 'after'} the deadline.`;
  } else if (p.status === 'Delivered late') timing = 'Late under PAC’s delivery rules';
  else if (delivered) timing = 'Within PAC’s delivery allowance';
  else if (p.status === 'Diverted') timing = 'Diverted — intended delivery not completed';
  else if (p.status === 'Failed') timing = 'Delivery not completed';
  if (!comparison && n(p.block_min) && n(d.target_block_min) && d.target_block_min > 0) {
    const delta = Math.round(p.block_min - d.target_block_min);
    comparison = `Block time ${Math.abs(delta)} min ${delta < 0 ? 'shorter' : 'longer'} than planned.`;
  }
  const weight = n(p.payload_lbs) ? p.payload_lbs : d.loaded_lbs;
  const risk = (d.breakdown || []).some(x => /structural damage/i.test(x[0]) && x[1] < 0);
  const cargo = (p.debrief || d.debrief || {}).cargo || [];
  const to = [...new Set(cargo.map(c => c.consignee).filter(Boolean))];
  const inZ = n(arrived) ? new Date(arrived * 1000).toISOString().slice(11, 16).replace(':', '') + 'Z' : '';
  const handover = delivered
    ? `Handed over to ${to.length ? to.slice(0, 3).map(e).join(', ') + (to.length > 3 ? ` and ${to.length - 3} more` : '') : 'the consignee'}${inZ ? ` after on-block at ${inZ}` : ''}.`
    : p.status === 'Diverted' ? 'Held at the diversion airport until it can be flown on.' : 'Not delivered on this flight.';
  return `<section class="pd-shipment" data-pd-section="Shipment"><small>SHIPMENT DEBRIEF</small><h3>${e(p.mission_title || 'Your cargo assignment')}</h3><p><b>${delivered ? 'Delivered' : e(p.status || 'Arrival not confirmed')}</b> · ${e(timing)}${n(weight) ? ` · ${e(weight.toLocaleString())} lb` : ''}${pending ? ' · Awaiting staff review' : ''}</p><p>${handover}</p>${risk ? `<p><b>Handling inspection requested</b>: the flight report flagged possible structural damage, so the ground team will check the freight.</p>` : ''}${comparison ? `<details><summary>Timing</summary><p>${e(comparison)}</p></details>` : ''}</section>`;
}
function pacScoreLabel(label) {
  const text = String(label ?? '');
  const speed = text.match(/250\s*kt.*fl100.*ias\s*(\d+)/i);
  return speed ? `Recorded ${speed[1]} kt IAS below FL100` : text;
}
function pacReportNav(root) {
  if (!root || root.querySelector('.pd-nav')) return;
  const sections = [...root.querySelectorAll('[data-pd-section]')];
  for (const h of root.querySelectorAll('h3')) {
    const name = h.textContent.trim();
    if (['Landing','Takeoff','Replay'].includes(name)) {h.dataset.pdSection=name;sections.push(h);}
  }
  const nav=document.createElement('nav');nav.className='pd-nav';nav.setAttribute('aria-label','Flight report sections');
  for (const name of ['Summary','Shipment','Landing','Takeoff','Replay']) {
    const target=sections.find(x=>x.dataset.pdSection===name);if(!target)continue;
    const b=document.createElement('button');b.type='button';b.textContent=name;
    b.onclick=()=>{target.scrollIntoView({block:'start',behavior:'auto'});target.tabIndex=-1;target.focus({preventScroll:true});};nav.appendChild(b);
  }
  root.prepend(nav);
}

{const style=document.createElement("style");style.textContent=".pac-debrief{border:1px solid var(--line,#d8dce3);border-top:4px solid #c80000;border-radius:8px;background:var(--white,#fff);color:var(--ink,#20252b);padding:24px;margin:18px 0;font:15px/1.6 system-ui}.pd-head{display:flex;justify-content:space-between;gap:24px}.pd-head h2{font-size:30px;margin:5px 0}.pd-head p{margin:4px 0 18px}.pd-head small{font-weight:700;letter-spacing:1px;color:var(--ink,#20252b)}.pd-grade{display:flex;flex-direction:column;align-items:center;min-width:140px}.pd-grade strong{font-size:48px;line-height:1.2}.pd-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.pd-metric{border:1px solid var(--line,#d8dce3);padding:16px;border-radius:6px;display:flex;flex-direction:column}.pd-metric strong{font-size:25px}.pd-metric strong span{font-size:13px;font-weight:400}.pd-columns{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin:20px 0}.pac-debrief h3{font-size:17px;margin:8px 0}.pac-debrief details{border-top:1px solid var(--line,#d8dce3);padding:14px 0}.pac-debrief summary{cursor:pointer;font-weight:700}.pd-note{color:var(--steel,#586575);font-size:13px}.pac-debrief p{max-width:85ch}@media(max-width:700px){.pd-grid{grid-template-columns:1fr 1fr}.pd-columns{grid-template-columns:1fr;gap:8px}.pd-head{flex-direction:column}.pd-grade{align-items:flex-start}.pac-debrief{padding:16px}}\n.pd-shipment{padding:22px;background:var(--paper,#f6f7f9);border-left:4px solid #c80000;margin:22px 0}.pd-shipment>small{font-weight:700;letter-spacing:1px;color:var(--ink,#20252b)}\n\n.pd-nav{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 20px}.pd-nav button{background:var(--white,#fff);color:var(--ink,#20252b);border:1px solid var(--line,#ddd);padding:9px 14px;cursor:pointer;border-radius:4px;font:inherit}.pd-nav button:hover,.pd-nav button:focus,.pd-nav button:focus-visible,.pd-nav button:active{outline:2px solid #c80000;color:var(--ink,#20252b)!important;background:var(--white,#fff)!important}.pd-shipment{padding:16px 20px}.pd-shipment details{padding-bottom:0}[data-pd-section]{scroll-margin-top:16px}\n";document.head.appendChild(style);}

function pacParkedInit() {
  if (document.getElementById('parkedControls')) return;
  const root=document.getElementById('liveRoot'), live=S.live;
  live.parkedLayer=L.layerGroup().addTo(live.base.map);live.airportCache={};
  const el=document.createElement('section');el.id='parkedControls';el.innerHTML=`<div class="row"><label><input id="pmFlying" type="checkbox" checked> Live flights</label><label><input id="pmParked" type="checkbox" checked> Parked fleet</label><label>Aircraft <select id="pmType"><option value="">All types</option>${Object.keys(S.fleet||{}).filter(k=>!S.fleet[k].retired).map(k=>`<option value="${esc(k)}">${esc(S.fleet[k].name||k)}</option>`).join('')}</select></label><label><input id="pmQualified" type="checkbox"> My qualifications</label><label><input id="pmAvailable" type="checkbox"> Available only</label><button class="btn ghost small" id="pmFit">Fit parked fleet</button></div><p class="muted" id="pmStatus" role="status">Loading parked fleet…</p><p class="muted">Numbered circles show aircraft at their recorded airport, not a specific parking stand. Aircraft reporting to ACARS appear as plane symbols.</p><div id="pmStations"></div>`;
  root.querySelector('.live-wrap').before(el);
  for(const id of ['pmType','pmQualified','pmAvailable','pmParked'])document.getElementById(id).onchange=()=>pacParkedRender();
  document.getElementById('pmFlying').onchange=e=>{if(e.target.checked)live.layer.addTo(live.base.map);else live.base.map.removeLayer(live.layer);document.getElementById('liveList').hidden=!e.target.checked;globeSync();};
  document.getElementById('pmFit').onclick=()=>liveFit(live.parkedPoints||[]);
}
async function pacParkedRefresh(force=false) {
  const live=S.live;if(!live || live.parkedBusy)return;
  pacParkedInit();
  if(!force && live.parkedAt && Date.now()-live.parkedAt<30000){pacParkedRender();return;}
  live.parkedBusy=true;
  try {
    const frames=await api('/api/airframes');if(S.live!==live)return;
    live.parkedFrames=frames;S.airframes=frames;
    const codes=[...new Set(frames.map(a=>a.location).filter(Boolean))];
    for(let i=0;i<codes.length;i+=3){await Promise.all(codes.slice(i,i+3).map(async code=>{if(live.airportCache[code])return;try{const a=await api('/api/stations/'+encodeURIComponent(code));if(Number.isFinite(a.lat)&&Number.isFinite(a.lon))live.airportCache[code]=a;}catch(e){/* listed below with coordinates unavailable */}}));}
    live.parkedAt=Date.now();live.parkedError='';pacParkedRender();
  }catch(e){live.parkedError='Fleet refresh failed. Displayed positions may be out of date.';pacParkedRender();}
  finally{live.parkedBusy=false;}
}
function pacParkedGroups(frames,flights,type,qualified,available) {
  const active=new Set((flights||[]).map(f=>f.reg).filter(Boolean));const groups={};
  for(const a of frames||[]){if(active.has(a.reg)||['Flying','Airborne','In flight'].includes(a.status))continue;if(type&&a.type!==type)continue;if(available&&a.status!=='Available')continue;if(qualified&&!boardQualified({id:'parked-fleet',category:'Cargo'},a.type))continue;(groups[a.location||'Unknown']||=[]).push(a);}
  return groups;
}
function pacParkedRender() {
  const live=S.live;if(!live?.parkedLayer)return;
  const visible=document.getElementById('pmParked').checked;
  live.parkedLayer.clearLayers();live.parkedPoints=[];
  const groups=pacParkedGroups(live.parkedFrames,live.flights,document.getElementById('pmType').value,document.getElementById('pmQualified').checked,document.getElementById('pmAvailable').checked);
  live.parkedGroups=groups;const codes=Object.keys(groups).sort();let missing=0;
  const list=document.getElementById('pmStations');list.hidden=!visible;
  list.innerHTML=visible?codes.map(code=>`<button class="btn ghost small" data-parked-station="${esc(code)}">${esc(code)} · ${groups[code].length}</button>`).join(''):'';
  for(const code of codes){const a=live.airportCache[code];if(!a){missing++;continue;}live.parkedPoints.push([a.lat,a.lon]);if(!visible)continue;
    const marker=L.marker([a.lat,a.lon],{icon:L.divIcon({className:'pm-marker',html:`<span>${groups[code].length}</span>`,iconSize:[34,34],iconAnchor:[17,17]})}).addTo(live.parkedLayer);
    marker.bindTooltip(`${esc(code)} · ${groups[code].length} aircraft`);marker.on('click',()=>pacParkedStation(code,groups[code]));
  }
  list.querySelectorAll('[data-parked-station]').forEach(b=>b.onclick=()=>{const a=live.airportCache[b.dataset.parkedStation];if(a)liveFocus(a.lat,a.lon,6);pacParkedStation(b.dataset.parkedStation,groups[b.dataset.parkedStation]);});
  document.getElementById('pmStatus').textContent=live.parkedError || `${Object.values(groups).reduce((n,a)=>n+a.length,0)} aircraft at ${codes.length} airports${live.parkedAt?' · Updated '+new Date(live.parkedAt).toLocaleTimeString():''}${missing?' · '+missing+' airports lack map coordinates; use their buttons above.':''}${!codes.length?' · No aircraft match these filters.':''}`;
  globeSync();
}
function pacParkedStation(code,frames){
  let dlg=document.getElementById('pmDialog');if(!dlg){dlg=document.createElement('dialog');dlg.id='pmDialog';document.body.append(dlg);}
  const a=S.live.airportCache[code],here=S.me?.location?.icao;
  dlg.innerHTML=`<div class="row"><h2>${esc(code)} · ${esc(a?.city||a?.name||'Recorded aircraft location')}</h2><button class="btn ghost small" id="pmClose">Close</button></div><p>Availability is checked again when booking or moving an aircraft.</p>${code!==here&&code!=='Unknown'?'<button class="btn small" id="pmTravel">Travel here · review quote</button>':''}<div>${frames.map((f,i)=>`<article class="pm-airframe"><h3>${esc(f.reg)} · ${esc(S.fleet[f.type]?.name||f.type)}</h3><p>${esc(reservationSummary(f))} · ${boardQualified({id:'parked-fleet',category:'Cargo'},f.type)?'Qualified under current booking rules':'Check qualifications'}${f.name?' · '+esc(f.name):''}</p><div class="row"><button class="btn ghost small" data-pm-flights="${i}">Find departures here</button>${f.status==='Available'&&code!==here&&code!=='Unknown'?`<button class="btn small" data-pm-ferry="${i}">Deliver to my station · quote</button>`:''}<button class="btn ghost small" data-pm-history="${i}">Aircraft details</button></div></article>`).join('')}</div>`;
  dlg.querySelector('#pmClose').onclick=()=>dlg.close();if(dlg.querySelector('#pmTravel'))dlg.querySelector('#pmTravel').onclick=()=>{dlg.close();openJumpseat(code);};
  dlg.querySelectorAll('[data-pm-flights]').forEach(b=>b.onclick=()=>{const f=frames[+b.dataset.pmFlights];dlg.close();resetMissionFilters();S.board='all';S.acFilter=f.type;S.parkedOrigin=code;show('missions');renderMissions();});
  dlg.querySelectorAll('[data-pm-ferry]').forEach(b=>b.onclick=()=>{dlg.close();confirmReposition(frames[+b.dataset.pmFerry].reg,()=>pacParkedRefresh(true));});
  dlg.querySelectorAll('[data-pm-history]').forEach(b=>b.onclick=()=>{dlg.close();openAirframe(frames[+b.dataset.pmHistory].reg);});
  if(!dlg.open)dlg.showModal();
}
{const style=document.createElement('style');style.textContent=`#parkedControls{background:var(--white);color:var(--ink);border:1px solid var(--line);padding:16px;margin-bottom:16px}#parkedControls .row{gap:16px;flex-wrap:wrap}#pmStations{display:flex;gap:8px;flex-wrap:wrap}#pmStations[hidden]{display:none}.pm-marker span{display:grid;place-items:center;width:32px;height:32px;border-radius:50%;background:#176782;color:white;border:2px solid white;font-weight:bold;box-shadow:0 1px 5px #333}#pmDialog{width:min(740px,92vw);max-height:85vh;overflow:auto;background:var(--white);color:var(--ink);border:1px solid var(--line);padding:24px}.pm-airframe{border-top:1px solid var(--line);padding:12px 0}.pm-airframe .row{flex-wrap:wrap;gap:8px}`;document.head.appendChild(style);}

VIEWS.push("crewplans");
async function loadCrewPlans(){
 const root=document.getElementById('crewPlansRoot'),pilot=S.me?.id;if(!pilot)return;
 root.innerHTML='<p role="status">Loading crew plans…</p>';
 try{const d=await api('/api/crew-plans');if(S.me?.id!==pilot)return;
 root.innerHTML=`<div class="profile-bar"><h1>Fly together</h1><button class="btn ghost" id="cpRefresh">Refresh</button></div><p>Find a second seat or arrange a flight with other PAC pilots.</p><div class="notice"><b>Planning only — no aircraft reservation.</b> Book through Missions as usual. This board does not award hours, pay or qualifications. Shared-cockpit pilots must arrange compatible simulator/add-on software and agree their roles.</div><details class="cp-create"><summary>Post a flight</summary><form id="cpForm"><div class="cp-grid"><label>Departure ICAO<input name="dep" maxlength="4" required placeholder="KCVG"></label><label>Arrival ICAO<input name="arr" maxlength="4" required placeholder="KMIA"></label><label>Aircraft type<select name="aircraft">${Object.keys(S.fleet).filter(k=>!S.fleet[k].retired).map(k=>`<option value="${esc(k)}">${esc(S.fleet[k].name||k)}</option>`).join('')}</select></label><label>Departure date and time (UTC)<input name="departure" type="datetime-local" required></label><label>Flight format<select name="mode"><option value="shared">Shared cockpit · one joining pilot</option><option value="group">Separate aircraft · group flight</option></select></label><label>Joining places (group flights)<input name="capacity" type="number" min="1" max="10" value="3" required></label><label>Simulator<input name="simulator" maxlength="60" required placeholder="MSFS 2024 / X-Plane 12"></label><label>Aircraft add-on / shared-cockpit setup<input name="addon" maxlength="100" placeholder="Required for shared cockpit"></label><label>Discord username (optional)<input name="contact" maxlength="80"><small>Only what you enter here is shared with signed-in pilots.</small></label><label>Notes<textarea name="note" maxlength="800" placeholder="Role, briefing time, voice channel or compatibility notes"></textarea></label></div><button class="btn" type="submit">Post flight</button><p id="cpError" role="alert"></p></form></details><h2>Upcoming flights</h2><div class="cp-grid">${d.plans.filter(x=>!x.expired&&!['cancelled','finished'].includes(x.state)).map(cpCard).join('')||'<p>No upcoming flights yet. Be the first to invite the crew.</p>'}</div><details><summary>My recent closed or past posts</summary>${d.plans.filter(x=>x.expired||['cancelled','finished'].includes(x.state)).map(cpCard).join('')||'<p>No past posts.</p>'}</details>`;
 fillCrewMissionDraft();
 focusCrewPost();
 root.querySelector('#cpRefresh').onclick=loadCrewPlans;
 root.querySelector('#cpForm').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,b=Object.fromEntries(new FormData(f));b.departure=Date.parse(b.departure+'Z')/1000;b.capacity=Number(b.capacity);const btn=f.querySelector('button');btn.disabled=true;try{await api('/api/crew-plans',{method:'POST',body:b});loadCrewPlans();}catch(err){root.querySelector('#cpError').textContent=err.message;btn.disabled=false;}};
 root.querySelectorAll('[data-cp-action]').forEach(b=>b.onclick=async()=>{let contact='';if(b.dataset.cpAction==='join'){contact=prompt('Optional Discord username to share with signed-in pilots (leave blank to omit):','');if(contact===null)return;}if(['cancel','finish'].includes(b.dataset.cpAction)&&!confirm('Close this crew-planning post? This does not change any flight booking.'))return;b.disabled=true;try{await api(`/api/crew-plans/${b.dataset.cpId}/${b.dataset.cpAction}`,{method:'POST',body:{contact}});loadCrewPlans();}catch(e){toast(e.message);b.disabled=false;}});
 }catch(e){if(S.me?.id===pilot){root.innerHTML=`<p role="alert">${esc(e.message)}</p><button class="btn" id="cpRetry">Retry</button>`;root.querySelector('#cpRetry').onclick=loadCrewPlans;}}
}
function cpCard(p){
 const joined=p.members.some(m=>m.pilot===S.me.id),closed=p.expired||['cancelled','finished'].includes(p.state),full=p.members.length>=p.capacity;
 const button=(a,t)=>`<button class="btn ghost small" data-cp-id="${p.id}" data-cp-action="${a}">${t}</button>`;
 const status=p.expired&&!['cancelled','finished'].includes(p.state)?'Departure passed':p.state==='complete'?'Crew complete':p.state==='open'?(full?'Places filled':'Looking for crew'):p.state;
 return `<article class="cp-card" data-crew-post="${p.id}"><small>${p.mode==='shared'?'SHARED COCKPIT':'GROUP FLIGHT · SEPARATE AIRCRAFT'}</small><h2>${esc(p.dep)} → ${esc(p.arr)}</h2><b>${new Date(p.departure*1000).toISOString().slice(0,16).replace('T',' ')} UTC</b><p>${esc(S.fleet[p.aircraft]?.name||p.aircraft)}<br>${esc(p.simulator)}${p.addon?' · '+esc(p.addon):''}</p><span class="tag">${esc(status)}</span><p>Organizer: ${esc(p.owner_name)} · ${esc(p.owner)}${p.contact?' · Discord: '+esc(p.contact):''}</p>${p.note?`<p>${esc(p.note)}</p>`:''}<p>${p.members.length} / ${p.capacity} joining places</p>${p.members.map(m=>`<p>${esc(m.name)} · ${esc(m.pilot)}${m.contact?' · Discord: '+esc(m.contact):''}</p>`).join('')}<div class="row">${joined?button('leave','Leave flight'):!closed&&p.state==='open'&&!full&&p.owner!==S.me.id?button('join','Join flight'):''}${p.can_manage&&!['cancelled','finished'].includes(p.state)?`${!p.expired?button(p.state==='open'?'complete':'reopen',p.state==='open'?'Mark crew complete':'Reopen places'):''}${button('finish','Mark finished')}${button('cancel','Cancel post')}`:''}</div></article>`;
}
{const style=document.createElement('style');style.textContent='.cp-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:18px 0}.cp-card,.cp-create{background:var(--white);color:var(--ink);border:1px solid var(--line);border-top:3px solid var(--red);padding:22px;margin:16px 0}.cp-card p{overflow-wrap:anywhere}.cp-card .row{flex-wrap:wrap;gap:8px}.cp-grid label{display:flex;flex-direction:column;gap:6px}.cp-grid input,.cp-grid select,.cp-grid textarea{width:100%;min-width:0;padding:10px;box-sizing:border-box;background:var(--white);color:var(--ink);border:1px solid var(--line)}@media(max-width:700px){.cp-grid{grid-template-columns:1fr}}';document.head.append(style);const nav=document.createElement('button');nav.dataset.view='crewplans';nav.textContent='Fly together';nav.onclick=()=>show('crewplans');document.querySelector('#navGroup2').append(nav);const section=document.createElement('section');section.className='view';section.id='view-crewplans';section.hidden=true;section.innerHTML='<div id="crewPlansRoot"></div>';document.querySelector('#view-pilots').parentElement.append(section);}

function reservationSummary(a){
 const r=a.reservation;
 if(a.liveOperation)return `${a.liveOperation.on_ground?'Operating on the ground':'Currently flying'} · ${a.liveOperation.flight}${r?' · '+r.pilot_name+' · '+r.dep+' → '+r.arr:''}`;
 if(r)return `Reserved for ${r.pilot_name || r.pilot_id} · ${r.pilot_id} · ${r.flight || 'Flight'} · ${r.dep || '?'} → ${r.arr || '?'}`;
 return a.status==='Booked'?'Reserved for a flight · booking details unavailable':a.status==='Available'?'Available':`Unavailable · ${a.status || 'check with Dispatch'}`;
}
function planSelectedWithCrew(){
 const m=S.selected;if(!m)return;
 S.crewDraft={dep:m.origin.icao,arr:m.destination.icao,aircraft:S.aircraft || m.aircraft?.[0],note:`Planning ${m.id}: ${m.title}. This post does not reserve an aircraft.`};
 show('crewplans');
}
function fillCrewMissionDraft(){
 const d=S.crewDraft,f=document.getElementById('cpForm');if(!d||!f)return;
 for(const k of ['dep','arr','aircraft','note'])if(f.elements[k])f.elements[k].value=d[k]||'';
 f.closest('details').open=true;S.crewDraft=null;f.elements.departure.focus();
}

function crewCalendarText(plan, now=new Date()) {
 const escape=s=>String(s??'').replace(/\\/g,'\\\\').replace(/\r\n|\r|\n/g,'\\n').replace(/;/g,'\\;').replace(/,/g,'\\,');
 const stamp=d=>d.toISOString().replace(/[-:]/g,'').replace(/\.\d{3}Z$/,'Z');
 const fold=line=>{let rows=[],part='',size=0;for(const ch of line){const bytes=new TextEncoder().encode(ch).length;if(size+bytes>75){rows.push(part);part=' ';size=1;}part+=ch;size+=bytes;}rows.push(part);return rows.join('\r\n');};
 return ['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Pagani Air Cargo//Crew Planning//EN','CALSCALE:GREGORIAN','BEGIN:VEVENT',`UID:pac-crew-${Number(plan.id)}@pac-va.com`,`DTSTAMP:${stamp(now)}`,`DTSTART:${stamp(new Date(plan.departure*1000))}`,`SUMMARY:${escape('PAC crew flight: '+plan.dep+' to '+plan.arr)}`,`LOCATION:${escape(plan.dep)}`,`DESCRIPTION:${escape((plan.mode==='shared'?'Shared cockpit':'Group flight')+' · '+plan.aircraft+'\nCheck Fly together for changes: https://pac-va.com/#crewplans\nPlanning only; this calendar entry does not join the crew or reserve an aircraft. Departure time only; duration is not specified.')}`,'URL:https://pac-va.com/#crewplans','END:VEVENT','END:VCALENDAR'].map(fold).join('\r\n')+'\r\n';
}
function downloadCrewCalendar(plan){
 const blob=new Blob([crewCalendarText(plan)],{type:'text/calendar;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`PAC-crew-${Number(plan.id)}.ics`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function loadDashboardCrew(root){
 const pilot=S.me?.id,token={};root._crewRequest=token;
 const current=()=>root.isConnected&&S.me?.id===pilot&&root._crewRequest===token;
 root.innerHTML='<h3>Upcoming crew flights</h3><p role="status">Checking the crew board…</p>';
 try{const data=await api('/api/crew-plans');if(!current())return;
 const plans=data.plans.filter(p=>p.departure>data.now&&!['cancelled','finished'].includes(p.state)).sort((a,b)=>a.departure-b.departure).slice(0,3);
 const timezone=Intl.DateTimeFormat().resolvedOptions().timeZone||'your device timezone';
 root.innerHTML=`<div class="row" style="justify-content:space-between;flex-wrap:wrap"><div><div class="kicker">Fly together</div><h3>Upcoming crew flights</h3></div><button class="btn ghost small" data-crew-board>View crew board →</button></div><p class="muted">Local times use ${esc(timezone)}. Crew plans do not reserve aircraft.</p><div class="dc-grid">${plans.map(p=>{const joined=p.members.some(m=>m.pilot===pilot),owner=p.owner===pilot,places=Math.max(0,p.capacity-p.members.length),open=p.state==='open'&&places>0;return `<article class="dc-flight"><strong>${esc(p.dep)} → ${esc(p.arr)}</strong><p>${esc(S.fleet[p.aircraft]?.name||p.aircraft)}<br>${p.mode==='shared'?'Shared cockpit':'Separate aircraft · group flight'}</p><time datetime="${new Date(p.departure*1000).toISOString()}"><b>${esc(new Date(p.departure*1000).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}))} local</b><br>${new Date(p.departure*1000).toISOString().slice(0,16).replace('T',' ')} UTC</time><p>${owner?'You’re organizing':joined?'You’re joining':open?places+' joining place'+(places===1?'':'s')+' open':'Crew complete / places filled'}</p><div class="row"><button class="btn ghost small" data-crew-view="${p.id}">View flight</button>${!joined&&!owner&&open?`<button class="btn small" data-crew-join="${p.id}">Join</button>`:''}<button class="btn ghost small" data-crew-calendar="${p.id}">Add to calendar</button></div></article>`;}).join('')||'<p>No upcoming crew flights yet. Post a flight and invite the crew.</p>'}</div><p class="brief-note">Calendar downloads are a snapshot, not a live subscription. Check the crew board for changes before departure.</p>`;
 root.querySelector('[data-crew-board]').onclick=()=>show('crewplans');
 root.querySelectorAll('[data-crew-view]').forEach(b=>b.onclick=()=>{S.crewFocusId=Number(b.dataset.crewView);show('crewplans');});
 root.querySelectorAll('[data-crew-calendar]').forEach(b=>b.onclick=()=>downloadCrewCalendar(plans.find(p=>p.id===Number(b.dataset.crewCalendar))));
 root.querySelectorAll('[data-crew-join]').forEach(b=>b.onclick=async()=>{const contact=prompt('Optional Discord username shared with signed-in pilots (leave blank to omit):','');if(contact===null)return;b.disabled=true;try{await api(`/api/crew-plans/${b.dataset.crewJoin}/join`,{method:'POST',body:{contact}});if(current())loadDashboardCrew(root);}catch(e){toast(e.message);if(current())loadDashboardCrew(root);}});
 setTimeout(()=>{if(current()&&!document.getElementById('view-dashboard')?.hidden)loadDashboardCrew(root);},60000);
 }catch(e){if(!current())return;root.innerHTML='<h3>Upcoming crew flights</h3><p role="status">Crew plans could not be loaded. Your flight briefing is still available.</p><button class="btn ghost small">Retry crew board</button>';root.querySelector('button').onclick=()=>loadDashboardCrew(root);}
}
function focusCrewPost(){const id=S.crewFocusId;if(!id)return;const el=document.querySelector(`[data-crew-post="${Number(id)}"]`);S.crewFocusId=null;if(el){el.scrollIntoView({block:'center'});el.tabIndex=-1;el.focus({preventScroll:true});}else toast('That flight is no longer on the upcoming board.');}
{const style=document.createElement('style');style.textContent='.dc-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.dc-flight{border:1px solid var(--line);border-top:3px solid var(--red);padding:16px;overflow-wrap:anywhere}.dc-flight .row{flex-wrap:wrap;gap:8px}.dc-flight strong{font-size:20px}.dc-flight time{font-size:13px}@media(max-width:1000px){.dc-grid{grid-template-columns:1fr}}';document.head.append(style);}

function trainingPolicyHTML(){return `<p><b>Checkrides are company-funded and are not restricted to KCVG.</b> Choose a dedicated training session (recommended) or an available fleet aircraft at its current airport.</p><ul><li>Dedicated sessions use a temporary training aircraft. Your normal station and operational fleet remain unchanged.</li><li>Fleet sessions reserve the selected aircraft and include free pilot travel when booked. After the flight, the aircraft stays where it landed. Existing reservations are protected.</li><li>Your home base comes first in the list of training airports. Once you pass the line checkride, PAC moves you to the home base you chose when you applied, free of charge, so your career starts there.</li><li>Accepted checkride attempts count toward career hours and flight count and receive standard flight pay plus applicable skill or gear bonuses. A failed attempt does not grant a qualification.</li><li>Checkrides earn no profit share, commercial cargo credit or reward points. Retakes are free.</li></ul><p>Generate a matching SimBrief plan, review and sign the dispatch release, then track the complete checkride in PAC ACARS. This training option does not unlock other flights before qualification.</p>`}
async function openTraining(course='PAC001'){
 if(!S.me){openSignIn('Sign in to start a checkride.');return;}
 if(S.booking){toast('Finish or cancel your current booking before starting a checkride.');show('bids');return;}
 document.getElementById('trainingDialog')?.remove();
 const dlg=document.createElement('dialog');dlg.id='trainingDialog';dlg.setAttribute('aria-labelledby','trainingTitle');dlg.style.cssText='width:min(760px,94vw);max-height:90vh;overflow:auto;border:1px solid var(--line);padding:24px;background:var(--white);color:var(--ink)';
 dlg.innerHTML='<style>#trainingForm{display:grid;grid-template-columns:1fr 1fr;gap:16px}#trainingForm label{display:flex;flex-direction:column;gap:7px;font-weight:600;min-width:0}#trainingForm select{width:100%;min-height:44px;padding:10px;border:1px solid var(--line);background:var(--white);color:var(--ink);font:inherit;font-weight:400}#trainingForm p,#trainingForm button{grid-column:1/-1;margin:0}#trainingDialog::backdrop{background:rgba(0,0,0,.5)}@media(max-width:600px){#trainingForm{grid-template-columns:1fr}}</style><div class="row" style="justify-content:space-between"><h2 id="trainingTitle">Start checkride</h2><button type="button" class="btn ghost small" id="trainingClose">Close</button></div><div id="trainingContent" aria-live="polite">Loading current training options…</div>';
 document.body.append(dlg);dlg.querySelector('#trainingClose').onclick=()=>dlg.close();dlg.addEventListener('close',()=>dlg.remove());dlg.showModal();
 const root=dlg.querySelector('#trainingContent');
 try{
 const data=await api('/api/training/options');if(!dlg.isConnected)return;
 root.innerHTML=`<p class="notice"><b>$0 to qualify.</b> No paid ferry or jumpseat required. Choose where and how you train.</p><form id="trainingForm"><label>Checkride<select name="course">${data.courses.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('')}</select></label><label>Training option<select name="mode"><option value="dedicated">Dedicated training session — recommended</option><option value="fleet">Use an available fleet aircraft</option></select></label><p id="trainingModeHelp"></p><label>Aircraft type<select name="aircraft"></select></label><label>Departure / aircraft<select name="choice"></select></label><p id="trainingRules"></p><button class="btn" type="submit">Review checkride →</button></form><div id="trainingReview" aria-live="polite"></div><details style="margin-top:20px"><summary>PAC checkride policy</summary>${trainingPolicyHTML()}</details>`;
 const form=root.querySelector('form'),f=form.elements,review=root.querySelector('#trainingReview');let choices=[],revision=0;
 if(data.courses.some(c=>c.id===course))f.course.value=course;
 const refresh=(types=false)=>{
 revision++;review.innerHTML='';const c=data.courses.find(c=>c.id===f.course.value);
 if(types)f.aircraft.innerHTML=c.types.map(t=>`<option value="${esc(t)}">${esc(S.fleet[t]?.name||t)}</option>`).join('');
 choices=c.choices.filter(x=>x.spec.mode===f.mode.value&&x.spec.aircraft===f.aircraft.value);
 f.choice.innerHTML=choices.map((x,i)=>`<option value="${i}">${esc(x.spec.origin)} → ${esc(x.destination)}${x.spec.reg?' · '+esc(x.spec.reg):' · temporary training aircraft'}</option>`).join('');
 if(!choices.length)f.choice.innerHTML='<option>No available options — try another type or dedicated training</option>';
 form.querySelector('[type=submit]').disabled=!choices.length;
 root.querySelector('#trainingModeHelp').textContent=f.mode.value==='dedicated'?'Train at a supported airport without moving your pilot or any fleet aircraft. Start your simulator at the departure airport shown.':'Available aircraft only. PAC pays your positioning travel when you book; the aircraft stays reserved for you. Availability is checked again at booking.';
 const r=c.standard,approach=c.id==='PAC001'?'':` Type checkrides also require an approach within ${r.max_approach_speed_spread} kt speed variation and sustained descent no steeper than ${r.max_sustained_descent_fpm} fpm below 500 ft.`;root.querySelector('#trainingRules').textContent=`Same standards in either mode: score ${r.min_score}+, touchdown no firmer than ${Math.abs(r.min_rate)} fpm, maximum ${r.max_g} G, no more than one bounce; overspeed penalties reduce score, and position jumps fail.${approach} An accepted report is required.`;
 };
 f.course.onchange=()=>refresh(true);f.mode.onchange=()=>refresh();f.aircraft.onchange=()=>refresh();f.choice.onchange=()=>{revision++;review.innerHTML=''};refresh(true);
 form.onsubmit=async e=>{e.preventDefault();const choice=choices[Number(f.choice.value)];if(!choice)return;const rev=++revision;review.textContent='Checking the route…';
 try{const m=await api('/api/training/preview',{method:'POST',body:choice.spec});if(rev!==revision||!dlg.isConnected)return;
 review.innerHTML=`<section class="notice" style="margin-top:20px"><h3>${esc(m.title)}</h3><p>${esc(S.fleet[m.aircraft[0]]?.name)} · ${fmt(m.distance_nm)} nm · ${hm(m.target_block_min)}</p><p><b>Cost: $0 · ${f.mode.value==='dedicated'?'Dedicated training aircraft':'Fleet aircraft '+esc(m.training.reg)}</b></p><p>${f.mode.value==='dedicated'?'Your normal station and operational aircraft will not move.':'Free pilot travel is included at booking. The aircraft will move when you complete the flight.'}</p><p>This creates your booking. Next, prepare the matching OFP and sign your release before starting ACARS.</p><button class="btn" id="trainingBook" type="button">Book checkride · $0</button><p>Accepted attempts count toward career hours and flight count, and earn standard flight pay plus applicable bonuses. Passing is still required for a qualification.</p></section>`;
 review.querySelector('#trainingBook').onclick=async ev=>{ev.target.disabled=true;f.course.disabled=f.mode.disabled=f.aircraft.disabled=f.choice.disabled=true;
 try{S.booking=await api('/api/booking',{method:'POST',body:{training:m.training}});dlg.close();await refreshCore();await loadMe();paintBid();show('bids');toast('Checkride booked at no cost. Prepare your OFP and dispatch release.');}
 catch(err){toast(err.message,8000);if(dlg.isConnected){f.course.disabled=f.mode.disabled=f.aircraft.disabled=f.choice.disabled=false;ev.target.disabled=false;}}
 };
 }catch(err){if(rev===revision)review.textContent=err.message;}
 };
 }catch(e){root.textContent=e.message;}
}


function lineCheckrideCard(status, via) {
 const passed=status==='Passed',waived=status==='Waived',pending=status==='Pending';
 const complete=passed||waived;
 const label=via&&passed?`Satisfied by your ${via} checkride`:passed?'Line checkride passed':waived?'Line checkride waived':pending?'Not yet passed':'Status unavailable';
 const body=via&&passed?`Your ${esc(via)} type checkride counted as your line checkride, so rank progression is open. It doesn't include the B737 qualification: fly the 737 line checkride or the B737 type checkride if you want to fly the 737.`
  :complete?'Your initial rank-progression requirement is satisfied. No additional B737 checkride is required.'
  :pending?'Your first step into rank progression: fly this 737 line checkride, which also grants the B737 qualification, or pass a type checkride for any aircraft family below. Either one counts.'
  :'Refresh Qualifications to load your current line-checkride status.';
 return `<div class="rating ${complete?'rt-held':''}"><h3>737 line checkride</h3><p><span class="tag ${complete?'green':'grey'}">${esc(label)}</span></p><p>${body}</p>${via&&passed?'<button class="btn ghost" onclick="openTraining()">Fly the 737 line checkride (optional)</button>':complete?'<button class="btn ghost" onclick="openTraining()">Retake line checkride (optional)</button>':pending?'<button class="btn" onclick="openTraining()">Start line checkride</button>':'<button class="btn ghost" onclick="fillRatings()">Refresh status</button>'}</div>`;
}

consentNotice();   // the privacy notice on a first visit (VATSIM's VA policy asks for one on the front page)
/* the width of the window's scrollbar (0 where scrollbars float over the page), so full-width bands fit exactly */
(function trackScrollbar() {
  const set = () => document.documentElement.style.setProperty("--sbw", Math.max(0, innerWidth - document.documentElement.clientWidth) + "px");
  set(); addEventListener("resize", set);
  try { new ResizeObserver(set).observe(document.body); } catch (e) { /* older browsers: resize only */ }
})();

/* ================= Weekly group flight =================
   One route, one departure time, everyone flies it together. Visitors can see it too (it's how new pilots find
   out PAC is alive), and signed-in pilots sign up, book it and add it to their calendar. group_flight.py runs it. */
VIEWS.push("groupflight");
PUBLIC_VIEWS.push("groupflight");
function gfWhen(t, opts) { return new Date(t * 1000).toLocaleString("en-US", opts); }
function gfCountdown(t) {
  const s = t - Date.now() / 1000;
  if (s <= 0) return s > -4 * 3600 ? "Departing now" : "Departed";
  const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  return d ? `in ${d}d ${h}h` : h ? `in ${h}h ${m}m` : `in ${m} min`;
}
function gfArc(a, b, n = 64) {
  const r = Math.PI / 180, [la1, lo1, la2, lo2] = [a.lat * r, a.lon * r, b.lat * r, b.lon * r];
  const d = 2 * Math.asin(Math.sqrt(Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2));
  if (!d) return [[a.lat, a.lon], [b.lat, b.lon]];
  return Array.from({ length: n + 1 }, (_, i) => {
    const f = i / n, A = Math.sin((1 - f) * d) / Math.sin(d), B = Math.sin(f * d) / Math.sin(d);
    const x = A * Math.cos(la1) * Math.cos(lo1) + B * Math.cos(la2) * Math.cos(lo2), y = A * Math.cos(la1) * Math.sin(lo1) + B * Math.cos(la2) * Math.sin(lo2), z = A * Math.sin(la1) + B * Math.sin(la2);
    return [Math.atan2(z, Math.hypot(x, y)) / r, Math.atan2(y, x) / r];
  });
}
async function loadGroupFlight() {
  const root = $("#groupFlightRoot");
  if (!root.innerHTML) root.innerHTML = `<p class="muted" role="status">Loading the group flight…</p>`;
  let d;
  try { d = await api("/api/public/group-flight"); } catch (e) { root.innerHTML = `<p class="notice err">${esc(e.message)}</p>`; return; }
  S.groupFlight = d;
  renderGroupFlight(d);
}
function renderGroupFlight(d) {
  const root = $("#groupFlightRoot");
  if (S.gfMap) { try { S.gfMap.remove(); } catch (e) { /* already gone */ } S.gfMap = null; }
  if (!d.enabled) {
    root.innerHTML = `<div class="profile-bar"><h1>Weekly group flight</h1></div><p class="muted">There's no group flight scheduled right now.</p>${d.staff ? gfStaffPanel(d) : ""}`;
    gfBindStaff(d); return;
  }
  const e = d.event, me = e.me, here = S.me?.location?.icao, now = Date.now() / 1000, started = e.start <= now, open = now >= (e.opens || 0) && now <= (e.closes || e.start);
  const local = gfWhen(e.start, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
  const utc = gfWhen(e.start, { timeZone: "UTC", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false }) + " UTC";
  const until = gfWhen(e.closes || e.start, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const acOpts = e.aircraft.map(a => `<option value="${esc(a.code)}" ${me?.aircraft === a.code ? "selected" : ""}>${esc(a.name)}</option>`).join("");
  const action = !S.me
    ? `<button class="btn" id="gfApply">Join PAC to fly it</button><button class="btn ghost" id="gfSignin">Pilots: sign in</button>`
    : `<button class="btn" id="gfBook">Book the flight</button>` + (me?.signed_up
        ? `<span class="tag green">On the list</span><button class="btn ghost small" id="gfLeave">Take me off the list</button>`
        : `<label class="gf-ac">Planning to fly it? <select id="gfAc"><option value="">Any aircraft</option>${acOpts}</select></label><button class="btn ghost" id="gfJoin">Add me to the list</button>`);
  root.innerHTML = `<div class="profile-bar"><h1>Weekly group flight</h1><span class="muted">${esc(d.schedule)} · optional</span></div>
    <section class="gf-hero">
      <div class="gf-main">
        <div class="kicker">${started && open ? "Open now" : "This week's route"} · optional</div>
        <h2>${esc(e.title)}</h2>
        <div class="gf-route"><div><b>${esc(e.dep.icao)}</b><span>${esc(e.dep.name)}</span></div><div class="gf-arrow" aria-hidden="true">${e.distance_nm ? `<small>${fmt(e.distance_nm)} nm</small>` : ""}<i></i></div><div><b>${esc(e.arr.icao)}</b><span>${esc(e.arr.name)}</span></div></div>
        <div class="gf-when"><div><small>Fly-along time</small><b>${esc(local)}</b><span class="gf-sub">${esc(utc)}</span></div><div><small>${started ? "Departed" : "Starts"}</small><b id="gfCount">${gfCountdown(e.start)}</b></div><div><small>Counts until</small><b>${esc(until)}</b></div></div>
        <p class="gf-optional">Fly it at the set time if you'd like company, or on your own any time this weekend. Offline is fine and voice chat is optional. Nobody has to take part.</p>
        <div class="gf-meta"><span><small>Aircraft</small>${e.aircraft.map(a => esc(a.name)).join(" · ")}</span><span><small>Cargo</small>${esc(e.cargo || "General cargo")}</span><span><small>Network</small>${esc(e.network === "Your choice" ? "Your choice: offline or online" : e.network)}</span><span><small>Voice</small>${esc(e.voice)}</span></div>
        <div class="row gf-actions">${action}</div>
        ${S.me && here && here !== e.dep.icao && !me?.flew ? `<p class="gf-note">You're at <b>${esc(here)}</b>. <button class="linkish" id="gfTravel">Jumpseat to ${esc(e.dep.icao)}</button>, or fly yourself there first.</p>` : ""}
        ${me?.flew ? `<p class="gf-note ok">You flew this week's route. Nice work.</p>` : ""}
      </div>
      <div class="gf-map" id="gfMap" role="img" aria-label="Route map from ${esc(e.dep.icao)} to ${esc(e.arr.icao)}"></div>
    </section>
    <div class="gf-cols">
      <section class="gf-card"><h3>Briefing</h3><p style="white-space:pre-line">${esc(e.briefing)}</p>
        <ol class="gf-steps"><li>Get to <b>${esc(e.dep.icao)}</b> with a PAC aircraft (jumpseat, or fly there beforehand).</li><li>Press <b>Book the flight</b>, plan it in SimBrief and sign the release, as for any flight.</li><li>Fly it with PAC ACARS any time before ${esc(until)}: at the set time if you'd like company, or whenever suits you.</li><li>File the PIREP. You'll show under "Flown this week" automatically. The list is optional too.</li></ol>
        <div class="row"><a class="btn ghost small" href="/api/group-flight.ics" download>Add to calendar</a><button class="btn ghost small" id="gfShare">Copy link</button></div></section>
      <section class="gf-card"><h3>Flown this week · ${e.flown.length}</h3>
        ${e.flown.map(n => `<div class="gf-pilot">${esc(n)}</div>`).join("") || `<p class="muted">Nobody's flown it yet.</p>`}
        ${e.count ? `<h3 style="margin-top:18px">Planning to fly · ${e.count}</h3>${e.signups.map(s => `<div class="gf-pilot">${esc(s.name)}${s.aircraft ? `<small>${esc(S.fleet?.[s.aircraft]?.icao || s.aircraft)}</small>` : ""}</div>`).join("")}` : ""}</section>
      <section class="gf-card"><h3>Coming up</h3>${d.next.map(n => `<div class="gf-row"><b>${esc(n.dep)} → ${esc(n.arr)}</b><span>${esc(gfWhen(n.start, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }))}</span></div>`).join("")}
        <p class="muted" style="font-size:13px">The route goes out from Cincinnati one week and back home the next, so if you flew out, you and your aircraft are already in place for the return.</p>
        ${d.past.some(p => p.signed || p.flew) ? `<h3 style="margin-top:18px">Recent</h3>${d.past.filter(p => p.flew).map(p => `<div class="gf-row"><b>${esc(p.dep)} → ${esc(p.arr)}</b><span>${p.flew} flew it</span></div>`).join("")}` : ""}</section>
    </div>
    ${d.staff ? gfStaffPanel(d) : ""}`;
  // map
  if (HAS_MAP && Number.isFinite(e.dep.lat) && Number.isFinite(e.arr.lat)) {
    const base = makeBaseMap($("#gfMap"), { theme: document.documentElement.dataset.theme === "light" ? "light" : "dark", style: S.settings?.map_style });
    const arc = gfArc(e.dep, e.arr);
    L.polyline(arc, { color: "#d4111e", weight: 3, opacity: .9 }).addTo(base.map);
    [[e.dep, "dep"], [e.arr, "arr"]].forEach(([a, k]) => L.marker([a.lat, a.lon], { icon: L.divIcon({ className: "gf-pin " + k, html: `<span>${esc(a.icao)}</span>`, iconSize: [60, 24], iconAnchor: [30, 12] }) }).addTo(base.map));
    base.map.fitBounds(arc, { padding: [40, 40], maxZoom: 6 });
    S.gfMap = base.map;
    setTimeout(() => S.gfMap?.invalidateSize(), 60);
  }
  clearInterval(S.gfTimer);
  S.gfTimer = setInterval(() => { const c = $("#gfCount"); if (!c || $("#view-groupflight").hidden) { clearInterval(S.gfTimer); return; } c.textContent = gfCountdown(e.start); }, 30000);
  const on = (id, fn) => { const b = $("#" + id); if (b) b.onclick = fn; };
  on("gfApply", () => { show("home"); setTimeout(() => $("#apply")?.scrollIntoView({ behavior: "smooth" }), 400); });
  on("gfSignin", () => openSignIn(null, "groupflight"));
  on("gfJoin", async () => { try { renderGroupFlight(await api("/api/group-flight/join", { method: "POST", body: { aircraft: $("#gfAc")?.value || "" } })); toast("You're on the list."); } catch (err) { toast(err.message); } });
  on("gfLeave", async () => { try { renderGroupFlight(await api("/api/group-flight/leave", { method: "POST", body: {} })); toast("Off the list."); } catch (err) { toast(err.message); } });
  on("gfTravel", () => openJumpseat(e.dep.icao));
  on("gfShare", () => navigator.clipboard.writeText(location.origin + "/#groupflight").then(() => toast("Link copied."), () => toast(location.origin + "/#groupflight")));
  on("gfBook", () => gfBook(e));
  gfBindStaff(d);
}
async function gfBook(e) {
  resetMissionFilters();
  if (e.route_id && (S.routes || []).some(r => r.id === e.route_id)) {
    S.board = "network"; S.region = "All"; S.netSearch = e.route_id; S.netLimit = 40; S.selected = null;
    show("missions");
    setTimeout(() => selectMission(e.route_id), 120);
  } else {
    S.charterSpec = { origin: e.dep.icao, destination: e.arr.icao, aircraft: e.aircraft[0]?.code || "B738F", payload_lbs: "", cargo: e.cargo || "General cargo", priority: "Standard", flight_number: "", _o: null, _d: null };
    S.charterMission = null; S.board = "charter"; S.selected = null; show("missions");
  }
}
function gfStaffPanel(d) {
  const s = d.staff, c = s.config, o = s.override || {};
  return `<details class="gf-card gf-staff" ${S.gfStaffOpen ? "open" : ""}><summary>Staff: run the group flight</summary>
    <form id="gfCfg" class="gf-form"><h3>Schedule</h3>
      <label class="check"><input type="checkbox" name="enabled" ${c.enabled ? "checked" : ""}> Weekly group flight is on</label>
      <div class="gf-grid"><label>Day<select name="weekday">${s.days.map((x, i) => `<option value="${i}" ${i === c.weekday ? "selected" : ""}>${x}</option>`).join("")}</select></label>
      <label>Time (UTC)<input name="time" value="${esc(c.time)}" pattern="\\d{1,2}:\\d{2}" required></label>
      <label>Network<select name="network">${s.networks.map(x => `<option ${x === c.network ? "selected" : ""}>${x}</option>`).join("")}</select></label>
      <label>Voice<input name="voice" value="${esc(c.voice)}" maxlength="120"></label></div>
      <label>Standing briefing<textarea name="briefing" rows="3" maxlength="1200">${esc(c.briefing)}</textarea></label>
      <button class="btn small">Save schedule</button></form>
    ${d.enabled ? `<form id="gfOv" class="gf-form"><h3>This week (${esc(d.event.id)})</h3>
      <p class="muted" style="font-size:13px">Leave blank to use the automatic out-and-back route. Enter a scheduled route number (like PAC1001), or a departure and arrival.</p>
      <div class="gf-grid"><label>Route number<input name="route_id" value="${esc(o.route_id || "")}" placeholder="PAC1001"></label>
      <label>Departure<input name="dep" value="${esc(o.dep || "")}" maxlength="4" placeholder="KCVG"></label><label>Arrival<input name="arr" value="${esc(o.arr || "")}" maxlength="4" placeholder="KJFK"></label>
      <label>Aircraft (for a custom route)<select name="aircraft" multiple size="3">${fleetCodes().map(k => `<option value="${k}" ${(o.aircraft || []).includes(k) ? "selected" : ""}>${esc(S.fleet[k].name)}</option>`).join("")}</select></label>
      <label>Title<input name="title" value="${esc(o.title || "")}" maxlength="80" placeholder="${esc(d.event.title)}"></label>
      <label>Network<select name="network"><option value="">Schedule default</option>${s.networks.map(x => `<option ${x === o.network ? "selected" : ""}>${x}</option>`).join("")}</select></label></div>
      <label>Briefing for this week<textarea name="briefing" rows="3" maxlength="1200" placeholder="Uses the standing briefing">${esc(o.briefing || "")}</textarea></label>
      <div class="row"><button class="btn small">Save this week</button><button type="button" class="btn ghost small" id="gfOvClear">Back to automatic</button></div></form>
      <div class="gf-form"><h3>Discord announcement</h3><textarea id="gfAnn" rows="10" readonly>${esc(s.announcement)}</textarea>
      <div class="row"><button class="btn small" id="gfAnnCopy">Copy</button>${s.discord ? `<button class="btn ghost small" id="gfAnnPost">Post to Discord</button>` : `<span class="muted" style="font-size:13px">Add the Discord webhook under Staff › Site and rules to post it in one click.</span>`}</div>
      <p class="muted" style="font-size:13px">The &lt;t:…&gt; codes show the departure in each reader's own time zone on Discord.</p></div>
      ${s.signups.length ? `<div class="gf-form"><h3>Sign-ups (staff view)</h3>${s.signups.map(x => `<div class="gf-row"><b>${esc(x.name)} · ${esc(x.pilot)}</b><span>${esc(x.aircraft || "any type")}</span></div>`).join("")}</div>` : ""}` : ""}
  </details>`;
}
function gfBindStaff(d) {
  if (!d.staff) return;
  const det = $(".gf-staff"); if (det) det.ontoggle = () => S.gfStaffOpen = det.open;
  const send = async body => { try { renderGroupFlight(await api("/api/staff/group-flight", { method: "POST", body })); toast("Saved."); } catch (err) { toast(err.message); } };
  const cfg = $("#gfCfg");
  if (cfg) cfg.onsubmit = ev => { ev.preventDefault(); const f = new FormData(cfg); send({ config: { enabled: cfg.enabled.checked, weekday: Number(f.get("weekday")), time: f.get("time"), network: f.get("network"), voice: f.get("voice"), briefing: f.get("briefing") } }); };
  const ov = $("#gfOv");
  if (ov) ov.onsubmit = ev => { ev.preventDefault(); const f = new FormData(ov); send({ override: { route_id: f.get("route_id"), dep: f.get("dep"), arr: f.get("arr"), aircraft: f.getAll("aircraft"), title: f.get("title"), network: f.get("network"), briefing: f.get("briefing") } }); };
  if ($("#gfOvClear")) $("#gfOvClear").onclick = () => send({ override: {} });
  if ($("#gfAnnCopy")) $("#gfAnnCopy").onclick = () => navigator.clipboard.writeText($("#gfAnn").value).then(() => toast("Announcement copied."), () => { $("#gfAnn").select(); toast("Select and copy it by hand."); });
  if ($("#gfAnnPost")) $("#gfAnnPost").onclick = async ev => { ev.target.disabled = true; try { await api("/api/staff/group-flight/discord", { method: "POST", body: {} }); toast("Posted to Discord."); } catch (err) { toast(err.message); } ev.target.disabled = false; };
}
{
  const nav = document.createElement("button"); nav.dataset.view = "groupflight"; nav.textContent = "Group flight";
  nav.onclick = () => show("groupflight");
  document.querySelector("#navGroup2")?.prepend(nav);
}
/* Home page: a strip announcing the next group flight, under the hero. */
async function gfHomeStrip() {
  try {
    const d = S.groupFlight && S.groupFlight._at > Date.now() - 60000 ? S.groupFlight : await api("/api/public/group-flight");
    S.groupFlight = { ...d, _at: Date.now() };
    const hero = $("#homeRoot .hero");
    if (!S.me) fillJoinGroupFlight(d);
    if (!d.enabled || !hero || !S.me || $("#gfStrip")) return;
    const e = d.event;
    hero.insertAdjacentHTML("afterend", `<a id="gfStrip" class="gf-strip" href="#groupflight"><span class="kicker">Weekly group flight · optional</span><b>${esc(e.dep.icao)} → ${esc(e.arr.icao)} · ${esc(e.title)}</b><span>${esc(gfWhen(e.start, { weekday: "long", hour: "numeric", minute: "2-digit", timeZoneName: "short" }))} · ${gfCountdown(e.start)} · fly it any time this weekend</span><span class="gf-strip-go">Details ›</span></a>`);
    $("#gfStrip").onclick = ev => { ev.preventDefault(); show("groupflight"); };
  } catch (e) { /* the home page works without it */ }
}

/* ================= Live map: globe view =================
   A Flat / Globe switch on the live map. The flat map stays Leaflet; the globe is MapLibre GL (vendored, BSD
   licensed), loaded only the first time someone picks Globe. Both show the same flights and parked fleet, and the
   same filters, station buttons and lists drive both. The choice is remembered on each computer. */
const GLOBE_JS = "/static/vendor/maplibre/maplibre-gl.js", GLOBE_CSS = "/static/vendor/maplibre/maplibre-gl.css";
let globeLib;
function loadGlobeLib() {
  if (window.maplibregl) return Promise.resolve(window.maplibregl);
  return globeLib ||= new Promise((ok, fail) => {
    const css = document.createElement("link"); css.rel = "stylesheet"; css.href = GLOBE_CSS; document.head.append(css);
    const s = document.createElement("script"); s.src = GLOBE_JS; s.onload = () => ok(window.maplibregl); s.onerror = () => { globeLib = null; fail(new Error("The globe couldn't load. Check your connection and try again.")); };
    document.head.append(s);
  });
}
function liveViewPref() { try { return localStorage.getItem("pac.liveView") || "flat"; } catch (e) { return "flat"; } }
function setLiveViewPref(v) { try { localStorage.setItem("pac.liveView", v); } catch (e) { /* not remembered; that's fine */ } }
function globeStyle(theme, key) {
  const dark = theme === "dark", st = MAP_STYLES[key] || MAP_STYLES[dark ? "dark" : "light"];
  const sources = {}, layers = [{ id: "ocean", type: "background", paint: { "background-color": dark ? "#14171b" : "#dfe6ec" } }];
  st.layers.forEach(([url, maxzoom], i) => {
    sources["tiles" + i] = { type: "raster", tiles: [url], tileSize: 256, maxzoom, attribution: i ? "" : st.attr };
    layers.push({ id: "tiles" + i, type: "raster", source: "tiles" + i });
  });
  return { version: 8, projection: { type: "globe" }, sources, layers,
    sky: { "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 1, 7, 0] } };
}
function liveFocus(lat, lon, zoom = 6) {
  const g = S.live?.globe;
  if (g && S.live.view === "globe") g.map.flyTo({ center: [lon, lat], zoom: Math.max(g.map.getZoom(), Math.min(zoom - 1, 5)), duration: 1600, essential: true });
  else S.live?.base.map.setView([lat, lon], Math.max(S.live.base.map.getZoom(), zoom));
}
function liveFit(pts) {
  if (!pts?.length) return;
  const g = S.live?.globe;
  if (g && S.live.view === "globe") {
    const lons = pts.map(p => p[1]), lats = pts.map(p => p[0]);
    g.map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 60, maxZoom: 5, duration: 1400 });
  } else S.live?.base.map.fitBounds(pts, { padding: [40, 40], maxZoom: 6 });
}
async function setLiveView(v) {
  const live = S.live; if (!live) return;
  live.view = v; setLiveViewPref(v);
  document.querySelectorAll("[data-liveview]").forEach(b => b.setAttribute("aria-pressed", b.dataset.liveview === v));
  $("#liveMap").hidden = v === "globe"; $("#liveGlobe").hidden = v !== "globe";
  if (v === "flat") { setTimeout(() => live.base.map.invalidateSize(), 30); return; }
  if (!live.globe) {
    $("#liveGlobe").innerHTML = `<p class="globe-loading">Loading the globe…</p>`;
    try { await loadGlobeLib(); } catch (e) { $("#liveGlobe").innerHTML = `<p class="globe-loading">${esc(e.message)}</p>`; return; }
    if (S.live !== live) return;
    $("#liveGlobe").innerHTML = "";
    const theme = document.documentElement.dataset.theme === "light" ? "light" : "dark";
    let map;
    try {
      map = new maplibregl.Map({ container: "liveGlobe", style: globeStyle(theme, S.settings?.map_style), center: [-84.66, 39.05], zoom: 1.4,
        attributionControl: { compact: true }, maxPitch: 60, renderWorldCopies: false });
    } catch (e) {
      $("#liveGlobe").innerHTML = `<p class="globe-loading">Your browser can't draw the globe (it needs WebGL). The flat map still works.</p>`; return;
    }
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-left");
    live.globe = { map, markers: [], ready: false, tileErr: 0, tileOk: 0 };
    map.on("data", e => { if (e.dataType === "source" && e.tile && String(e.sourceId || "").startsWith("tiles")) live.globe.tileOk++; });
    map.on("error", e => {
      if (!String(e?.sourceId || "").startsWith("tiles")) return;
      live.globe.tileErr++;
      if (live.globe.tileErr >= 6 && !live.globe.tileOk && !live.globe.noted) {
        live.globe.noted = true;
        map.getStyle().layers.filter(l => l.type === "raster").forEach(l => map.setLayoutProperty(l.id, "visibility", "none"));
        $("#liveGlobe").insertAdjacentHTML("beforeend", `<div class="map-note globe-note">Map tiles are unavailable. Showing the offline outline globe.</div>`);
      }
    });
    map.on("load", async () => {
      const w = await loadWorld();
      const dark = theme === "dark";
      if (w) {
        map.addSource("land", { type: "geojson", data: { type: "Feature", properties: {}, geometry: w.land } });
        map.addSource("borders", { type: "geojson", data: { type: "Feature", properties: {}, geometry: w.borders } });
        map.addLayer({ id: "land", type: "fill", source: "land", paint: { "fill-color": dark ? "#262a31" : "#f4f5f7" } }, map.getLayer("tiles0") ? "tiles0" : undefined);
        map.addLayer({ id: "borders", type: "line", source: "borders", paint: { "line-color": dark ? "#3a4049" : "#c3c9d0", "line-width": 0.6 } }, map.getLayer("tiles0") ? "tiles0" : undefined);
      }
      await addZoneOverlayGlobe(map, $("#liveGlobe")).catch(() => {});
      map.addSource("tracks", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "tracks", type: "line", source: "tracks", paint: { "line-color": "#d4111e", "line-width": ["case", ["get", "sel"], 3, 2], "line-opacity": ["case", ["get", "sel"], 0.9, 0.55] } });
      map.addSource("toarr", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "toarr", type: "line", source: "toarr", paint: { "line-color": "#d4111e", "line-width": 1.5, "line-dasharray": [3, 3], "line-opacity": 0.75 } });
      live.globe.ready = true;
      globeSync();
      dayNightSync();
    });
  } else {
    setTimeout(() => live.globe.map.resize(), 30);
    globeSync();
  }
}
function globePlaneEl(f, sel) {
  const col = f.on_ground ? "#9aa1ab" : "#d4111e", el = document.createElement("button");
  el.type = "button"; el.className = "globe-plane" + (sel ? " sel" : ""); el.title = `${f.flight} · ${f.aircraft} · ${f.dep || ""} → ${f.arr || ""}`;
  el.setAttribute("aria-label", `${f.flight}, ${f.dep || ""} to ${f.arr || ""}`);
  el.innerHTML = `<svg viewBox="0 0 32 32" width="30" height="30"><path d="M16 2l2.4 9.6 10.6 6v2.6l-10.6-3.2-.8 7.4 3.6 2.6V29L16 27.6 10.8 29v-2l3.6-2.6-.8-7.4-10.6 3.2v-2.6l10.6-6z" fill="${col}" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/></svg>`;
  return el;
}
function unwrapLon(coords) {  // [lon, lat] pairs: keep each step under 180 degrees so lines cross the date line the short way
  return coords.reduce((out, [lo, la]) => {
    const prev = out.length ? out[out.length - 1][0] : lo;
    let x = lo; while (x - prev > 180) x -= 360; while (prev - x > 180) x += 360;
    out.push([x, la]); return out;
  }, []);
}
function globeSync() {
  const live = S.live, g = live?.globe;
  if (!g?.ready || live.view !== "globe") return;
  const map = g.map;
  g.markers.forEach(m => m.remove()); g.markers = [];
  const showFlights = $("#pmFlying")?.checked !== false, showParked = $("#pmParked")?.checked !== false;
  const flights = showFlights ? live.flights || [] : [];
  map.getSource("tracks")?.setData({ type: "FeatureCollection", features: flights.filter(f => f.track?.length > 1).map(f => ({ type: "Feature", properties: { sel: live.sel === f.flight },
    geometry: { type: "LineString", coordinates: unwrapLon(f.track.map(([la, lo]) => [lo, la])) } })) });
  const s = flights.find(f => f.flight === live.sel && f.arr_pos);
  map.getSource("toarr")?.setData({ type: "FeatureCollection", features: s ? [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: unwrapLon(gfArc({ lat: s.lat, lon: s.lon }, { lat: s.arr_pos[0], lon: s.arr_pos[1] }, 48).map(([la, lo]) => [lo, la])) } }] : [] });
  if (showParked) Object.entries(live.parkedGroups || {}).forEach(([code, frames]) => {
    const a = live.airportCache?.[code]; if (!a) return;
    const el = document.createElement("button"); el.type = "button"; el.className = "pm-marker globe-pm"; el.title = `${code} · ${frames.length} aircraft`;
    el.innerHTML = `<span>${frames.length}</span>`; el.onclick = ev => { ev.stopPropagation(); pacParkedStation(code, frames); };
    g.markers.push(new maplibregl.Marker({ element: el }).setLngLat([a.lon, a.lat]).addTo(map));
  });
  flights.forEach(f => {
    const sel = live.sel === f.flight, el = globePlaneEl(f, sel);
    el.onclick = ev => { ev.stopPropagation(); live.sel = sel ? null : f.flight; pollLive(); };
    g.markers.push(new maplibregl.Marker({ element: el, rotation: f.hdg || 0, rotationAlignment: "map" }).setLngLat([f.lon, f.lat]).addTo(map));
  });
  if (!g.fitted && flights.length) { g.fitted = true; map.flyTo({ center: [flights[0].lon, flights[0].lat], zoom: 2.2, duration: 1800 }); }
}
function liveViewSwitch() {
  const bar = document.querySelector("#liveRoot .profile-bar");
  if (!bar || $("#liveViewSwitch")) return;
  bar.insertAdjacentHTML("beforeend", `<div class="seg-switch" id="liveViewSwitch" role="group" aria-label="Map view"><button type="button" data-liveview="flat" aria-pressed="true">Flat map</button><button type="button" data-liveview="globe" aria-pressed="false">Globe</button></div>`);
  $(".live-wrap").insertAdjacentHTML("afterbegin", `<div id="liveGlobe" class="live-map live-globe" hidden></div>`);
  document.querySelectorAll("[data-liveview]").forEach(b => b.onclick = () => setLiveView(b.dataset.liveview));
  bar.insertAdjacentHTML("beforeend", `<button type="button" class="btn ghost small daynight-btn" id="dayNightBtn" aria-pressed="${dayNightPref()}" title="Show where it's day and night right now">☀︎ Day / night</button>`);
  $("#dayNightBtn").onclick = () => { const on = !dayNightPref(); setDayNightPref(on); $("#dayNightBtn").setAttribute("aria-pressed", on); dayNightSync(); };
  dayNightSync();
  clearInterval(S.dayNightTimer); S.dayNightTimer = setInterval(() => { if (document.getElementById("dayNightBtn")) dayNightSync(); else clearInterval(S.dayNightTimer); }, 60000);
}

/* ================= Day / night: where the sun is up right now (the terminator), on the flat map and the globe ================= */
function dayNightPref() { try { return localStorage.getItem("pac.dayNight") === "1"; } catch (e) { return false; } }
function setDayNightPref(on) { try { localStorage.setItem("pac.dayNight", on ? "1" : "0"); } catch (e) { /* not remembered */ } }
function sunPosition(date = new Date()) {
  // low-precision solar position (good to about 0.1 degree; plenty for a map)
  const rad = Math.PI / 180, n = date.getTime() / 86400000 + 2440587.5 - 2451545;
  const L = (280.460 + 0.9856474 * n) % 360, g = ((357.528 + 0.9856003 * n) % 360) * rad;
  const lam = (L + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * rad, eps = (23.439 - 0.0000004 * n) * rad;
  const ra = Math.atan2(Math.cos(eps) * Math.sin(lam), Math.cos(lam)) / rad, dec = Math.asin(Math.sin(eps) * Math.sin(lam)) / rad;
  const gmst = ((18.697374558 + 24.06570982441908 * n) % 24) * 15;
  return { dec, lon: ((ra - gmst + 540) % 360) - 180 };       // the point on Earth where the sun is overhead
}
function nightRings(date = new Date()) {
  // the night side, plus a softer twilight band (sun up to 6 and 12 degrees below the horizon)
  const sun = sunPosition(date), rad = Math.PI / 180, out = [];
  for (const depress of [0, 6, 12]) {
    const ring = [], pole = sun.dec > 0 ? -90 : 90;
    const d = sun.dec * rad, dir = pole < 0 ? 1 : -1;
    for (let lon = -180; lon <= 180; lon += 2) {
      const ch = Math.cos((lon - sun.lon) * rad);
      const alt = lat => Math.asin(Math.sin(lat * rad) * Math.sin(d) + Math.cos(lat * rad) * Math.cos(d) * ch) / rad;
      // walk from the dark pole toward the sunlit one; the edge is where the sun climbs above -depress
      let lat = pole, edge = -pole;
      for (let x = pole; dir > 0 ? x <= 90 : x >= -90; x += dir * 0.5) { if (alt(x) > -depress) { edge = x; break; } lat = x; }
      ring.push([lon, Math.max(-89.9, Math.min(89.9, edge))]);
    }
    ring.push([180, pole], [-180, pole], ring[0]);
    out.push(ring);
  }
  return out;          // [night edge, civil twilight, nautical twilight], each a closed [lon, lat] ring
}
function dayNightSync() {
  const live = S.live; if (!live) return;
  const on = dayNightPref(), rings = on ? nightRings() : [];
  const dark = document.documentElement.dataset.theme !== "light";
  // flat map (Leaflet)
  const m = live.base?.map;
  if (m) {
    // one canvas with a wide margin, kept between updates: panning and zooming don't redraw it from scratch (no blinking)
    live.nightRenderer ||= L.canvas({ padding: 1.5, pane: "overlayPane" });
    live.nightLayers ||= [];
    rings.forEach((r, i) => {
      const ll = r.map(([x, y]) => [y, x]);
      if (live.nightLayers[i]) live.nightLayers[i].setLatLngs(ll);
      else live.nightLayers[i] = L.polygon(ll, { renderer: live.nightRenderer, stroke: false, fillColor: "#00081a", fillOpacity: dark ? 0.22 : 0.14, interactive: false, smoothFactor: 2 });
      if (!m.hasLayer(live.nightLayers[i])) live.nightLayers[i].addTo(m);
    });
    if (!on) live.nightLayers.forEach(l => m.hasLayer(l) && m.removeLayer(l));
  }
  // globe (MapLibre)
  const g = live.globe;
  if (g?.ready) {
    const fc = { type: "FeatureCollection", features: rings.map(r => ({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [r] } })) };
    if (g.map.getSource("night")) g.map.getSource("night").setData(fc);
    else {
      g.map.addSource("night", { type: "geojson", data: fc });
      g.map.addLayer({ id: "night", type: "fill", source: "night", paint: { "fill-color": "#00081a", "fill-opacity": dark ? 0.22 : 0.14, "fill-antialias": false } }, g.map.getLayer("tracks") ? "tracks" : undefined);
    }
  }
}


/* ================= Home: why PAC + track a shipment; Dashboard: start-here checklist + happening now ================= */
function whyPacHTML() {
  const pillars = [
    ["Real paperwork", "Every flight gets a dispatch release: load sheet with CG, NOTOC, cargo manifest with IATA codes, weather and runway wind.", "Read the cargo guide", "show('cargoguide')"],
    ["Cargo that stays put", "Shipments move station to station across flights. Track any air waybill, and see the whole network live.", "See the network", "(S.me ? show('network') : location.href='/network')"],
    ["Real consequences", "A hard landing or tail strike grounds the aircraft where it is. Then a PAC crew flies in the repair kit.", "How scoring works", "show('handbook')"],
    ["Fly online", "IVAO certified and flying on VATSIM as PGI. A weekly group flight anyone can join.", "This week's group flight", "show('groupflight')"]];
  return `<section class="why-pac" aria-label="Why fly for PAC">
    ${S.me ? "" : `<div class="section-h"><div><div class="kicker">Why PAC</div><h2>A cargo airline that takes the freight seriously</h2></div></div>
    <div class="why-grid">${pillars.map(([h, p, l, go], i) => `<article class="why-card"><img class="why-img" src="/static/illustrations/${["ill-main-deck-pac", "ill-767-main-deck-loading", "ill-hangar-777f", "ill-ake-lower-hold"][i]}.webp" alt="" loading="lazy"><span class="why-n">0${i + 1}</span><h3>${h}</h3><p>${p}</p><button class="why-link" type="button" onclick="${go}">${l} →</button></article>`).join("")}</div>`}
    <form class="track-strip" onsubmit="event.preventDefault();const v=this.awb.value.replace(/\\D/g,'');if(v)location.href='/track/'+v">
      <div><div class="kicker">Track a shipment</div><b>Where's my freight?</b></div>
      <input name="awb" inputmode="numeric" autocomplete="off" placeholder="901-10000123" aria-label="Air waybill number">
      <button class="btn">Track</button>
    </form></section>`;
}

function startHereHTML(d) {
  let acars = false;
  try { acars = localStorage.getItem("pac-start-acars-" + S.me?.id) === "1"; } catch (_) {}
  const filed = (d.flights_filed || 0) > 0;
  const steps = [
    ["Pass your line checkride", !d.checkride_needed, "Your first graded flight, in the 737-800.", "Checkride", "show('career/qualifications')"],
    ["Install PAC ACARS and print the cheat sheets", acars || filed, "PAC ACARS tracks and scores your flight. The Quick-Reference Pack has everything on six pages.", "Downloads", "markStartAcars();show('downloads')"],
    ["Book your first flight", !!d.booking || filed, "Pick a short hop from where you are. The dispatch release comes with it.", "Missions", "show('missions')"],
    ["Fly it and file your PIREP", filed, "Park, brakes set, engines off, then File PIREP in ACARS.", "Gate-to-gate checklist", "show('downloads')"]];
  const done = steps.filter(s => s[1]).length;
  if (done === steps.length) return pilotWelcomeHTML();
  return `<section class="start-here" aria-label="Start here">
    <div class="start-head"><div><span class="kicker">Start here</span><h3>Your first PAC flight, step by step</h3></div>
      <div class="start-meter" role="img" aria-label="${done} of ${steps.length} steps done"><b>${done}/${steps.length}</b><span><i style="width:${done / steps.length * 100}%"></i></span></div></div>
    <ol class="start-steps">${steps.map(([t, ok, p, l, go]) => `<li class="${ok ? "done" : ""}"><span class="start-tick" aria-hidden="true">${ok ? "✓" : ""}</span>
      <div><b>${t}</b><small>${p}</small></div>${ok ? `<span class="start-ok">Done</span>` : `<button class="btn ghost small" type="button" onclick="${go}">${l}</button>`}</li>`).join("")}</ol>
    <div class="row"><button class="btn small" type="button" onclick="openPilotGuide()">Full first-flight guide</button><button class="btn ghost small" type="button" onclick="location.href='/academy/'">PAC Academy</button></div></section>`;
}
function markStartAcars() { try { localStorage.setItem("pac-start-acars-" + S.me?.id, "1"); } catch (_) {} }

async function loadHappeningNow(root, d) {
  root.innerHTML = `<div class="kicker">Happening now</div><h3>What needs a crew</h3><p class="muted" role="status">Checking the network…</p>`;
  const [gf, net] = await Promise.all([api("/api/public/group-flight").catch(() => null), api("/api/public/network").catch(() => null)]);
  if (!root.isConnected) return;
  const items = [];
  let urgent = S.urgent || [];
  const relief = urgent.filter(m => m.relief);
  if (relief.length) items.push(["RELIEF", esc(relief[0].title), `Based on a real disaster: ${esc(relief[0].relief.event)}. No bonus rewards.`, "Read the briefing", "S.board='urgent';show('missions')"]);
  urgent = urgent.filter(m => !m.relief);
  const aog = urgent.filter(m => /aog/i.test(m.urgent_kind || ""));
  if (aog.length) items.push(["AOG", `${aog.length} aircraft grounded`, `${aog.map(m => esc(m.destination.icao)).join(", ")} waiting for parts and engineers.`, "Fly a recovery", "S.board='urgent';show('missions')"]);
  if (urgent.length > aog.length) items.push(["URGENT", `${urgent.length - aog.length} urgent request${urgent.length - aog.length > 1 ? "s" : ""}`, "Time-critical freight with bonus points.", "See urgent flights", "S.board='urgent';show('missions')"]);
  const here = (net?.waiting || []).find(w => w.icao === d.location.icao);
  if (here) items.push(["FREIGHT", `${fmt(here.lbs)} lb waiting at ${esc(here.icao)}`, `${here.shipments} shipment${here.shipments > 1 ? "s" : ""} ready to move from where you are.`, "Find a flight", "show('missions')"]);
  else if (net?.waiting?.length) { const w = net.waiting[0]; items.push(["FREIGHT", `${fmt(w.lbs)} lb waiting at ${esc(w.icao)}`, `The most freight sitting anywhere in the network right now.`, "Cargo network", "(S.me ? show('network') : location.href='/network')"]); }
  if (gf?.enabled && gf.event) items.push(["GROUP", esc(gf.event.title || "Weekly group flight"), `${esc(gfWhen(gf.event.start, { weekday: "long", hour: "numeric", minute: "2-digit" }))} your time. ${esc(gf.schedule || "")}`, "Sign up", "show('groupflight')"]);
  root.innerHTML = `<div class="kicker">Happening now</div><h3>What needs a crew</h3>${items.length ? `<div class="now-grid">${items.map(([tag, h, p, l, go]) => `<div class="now-item"><span class="now-tag now-${tag.toLowerCase()}">${tag}</span><b>${h}</b><small>${p}</small><button class="why-link" type="button" onclick="${go}">${l} →</button></div>`).join("")}</div>` : `<p>All quiet: no urgent flights or waiting freight right now. A good time to fly a scheduled route.</p>`}`;
}


/* ================= Home page layout (Nov 2026 redesign) =================
   The template renders every section; this puts them in order. Visitors get a short page that tells the story
   (hero, proof numbers, why PAC, PAC flying now, the fleet, join in); pilots get the slim welcome bar with notices
   and company news first, then everything else as before. */
function fmtLbShort(n) { n = Number(n) || 0; return n >= 1e6 ? (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M" : n >= 1e3 ? fmt(Math.round(n / 1e3)) + "k" : fmt(n); }
function homeLayout() {
  const root = $("#homeRoot"); if (!root) return;
  const groups = [], byKey = {};
  const solo = el => el.matches(".hero,.stat-band,.proof-band,.dir-badges,.why-pac,.site-foot,#homeCampaigns,.home-notices,.gf-strip");
  let cur = null;
  [...root.children].forEach(el => {
    if (solo(el) || el.classList.contains("section-h") || !cur) {
      const key = el.classList.contains("section-h") ? (el.querySelector(".kicker")?.textContent || "").trim().toLowerCase()
        : el.id === "homeCampaigns" ? "campaigns" : (el.className.split(" ")[0] || el.tagName.toLowerCase());
      cur = { key, els: [el] }; groups.push(cur); byKey[key] = cur;
      if (solo(el)) cur = null;
    } else cur.els.push(el);
  });
  const put = keys => { const seen = new Set(); const out = [];
    keys.forEach(k => { const g = byKey[k]; if (g && !seen.has(g)) { seen.add(g); out.push(g); } });
    groups.forEach(g => { if (!seen.has(g)) out.push(g); }); return out; };
  // See it working: the departure board and the map side by side, under one heading
  const board = byKey["live from the ops center"], net = byKey["the network"];
  if (board && net) {
    const see = document.createElement("section"); see.className = "see-it";
    see.innerHTML = `<div class="section-h"><div><div class="kicker">See it working</div><h2>PAC is flying right now</h2></div><button class="btn ghost small" type="button" onclick="(S.me ? show('network') : location.href='/network')">Open the cargo network</button></div><div class="see-grid"></div>`;
    const grid = see.querySelector(".see-grid");
    board.els.filter(el => !el.classList.contains("section-h")).forEach(el => grid.append(el));
    net.els.filter(el => !el.classList.contains("section-h")).forEach(el => grid.append(el));
    board.els.concat(net.els).filter(el => el.classList.contains("section-h")).forEach(el => el.remove());
    board.els = [see]; net.els = [];
  }
  root.classList.toggle("home-pilot", !!S.me);
  root.classList.remove("home-visitor");
  if (S.me) {
    const gone = new Set(["the liveries", "operations", "our story", "partners", "career path", "community", "join the crew", "dir-badges"]);
    groups.filter(g => gone.has(g.key)).forEach(g => g.els.forEach(el => el.remove()));
    const sb = byKey["stat-band"];
    if (sb) { const h = document.createElement("div"); h.className = "section-h"; h.innerHTML = `<div><div class="kicker">The airline</div><h2>PAC at a glance</h2></div>`; sb.els.unshift(h); }
    const order = put(["hero", "campaigns", "needs a crew now", "on now", "live from the ops center", "company news", "from the flight deck",
      "online networks", "stat-band", "why-pac", "site-foot"]).filter(g => !gone.has(g.key));
    const fi = order.findIndex(g => g.key === "site-foot"); if (fi > -1) order.push(order.splice(fi, 1)[0]);
    order.forEach(g => g.els.forEach(el => root.append(el)));
    return;
  }
  root.classList.add("home-visitor");
  const drop = new Set(["company news", "from the flight deck", "campaigns", "on now", "needs a crew now", "operations"]);
  groups.filter(g => drop.has(g.key)).forEach(g => g.els.forEach(el => el.remove()));
  const join = document.createElement("section"); join.className = "home-join"; join.setAttribute("aria-label", "Join in");
  join.innerHTML = `<div class="join-gf" id="joinGf" hidden></div>
    <div class="join-cta"><h3>Ready for your first load?</h3><p>Free to join. Start in the 737, work up to the 747-8F.</p>
    <div class="row"><a class="btn light" href="#apply" onclick="document.getElementById('apply')?.scrollIntoView({behavior:'smooth'});return false">Apply to fly</a><button class="btn ghost" type="button" onclick="location.href='/academy/'">Try PAC Academy</button></div></div>`;
  byKey.join = { key: "join", els: [join] };
  const track = root.querySelector(".track-strip");
  groups.push(byKey.join);
  // The fleet: one row of every type instead of the big photo grid
  const liv = byKey["the liveries"];
  const lgrid = liv && liv.els.find(el => el.classList.contains("livery-grid"));
  if (lgrid) {
    const row = document.createElement("div"); row.className = "fleet-chips";
    row.innerHTML = fleetCodes().map(k => `<button type="button" onclick="show('fleet')">${esc(S.fleet[k].name.replace(/^(Boeing|Airbus|McDonnell Douglas) /, ""))}</button>`).join("");
    lgrid.replaceWith(row); liv.els[liv.els.indexOf(lgrid)] = row;
  }
  const final = put(["hero", "proof-band", "why-pac", "live from the ops center", "the network", "online networks", "the liveries", "join",
    "our story", "career path", "partners", "community", "join the crew", "dir-badges", "stat-band", "site-foot"]).filter(g => !drop.has(g.key));
  const footIdx = final.findIndex(g => g.key === "site-foot");
  if (footIdx > -1) final.push(final.splice(footIdx, 1)[0]);
  final.forEach(g => g.els.forEach(el => root.append(el)));
  const foot = root.querySelector(".site-foot");
  if (track && foot) { track.classList.add("track-foot"); foot.before(track); }
}
function fillJoinGroupFlight(d) {
  const box = $("#joinGf"); if (!box) return;
  if (!d || !d.enabled || !d.event) { box.hidden = true; return; }
  const e = d.event;
  box.innerHTML = `<div class="kicker">This week's group flight</div><h3>${esc(e.title)}</h3>
    <div class="join-route">${esc(e.dep.icao)} → ${esc(e.arr.icao)} · ${esc(gfWhen(e.start, { weekday: "long", hour: "numeric", minute: "2-digit", timeZoneName: "short" }))}</div>
    <p>Fly together online, or any time that weekend. New pilots welcome.</p>
    <button class="btn ghost small" type="button" onclick="show('groupflight')">See the briefing</button>`;
  box.hidden = false;
}

/* ================= Humanitarian relief missions (real disasters, staff-approved) =================
   Calm styling on purpose: no red, no countdowns, no bonus. The notice and the real sources always come first. */
function reliefCard(m) {
  return `<div class="urgent-card relief-card"><span class="relief-label">HUMANITARIAN RELIEF</span>
    <h3>${esc(m.title)}</h3><div class="rt">${esc(m.origin.icao)} → ${esc(m.destination.icao)}</div>
    <div class="muted" style="font-size:13px">${esc(S.fleet[m.aircraft[0]]?.name || "")} · ${fmt(m.payload_lbs)} lb</div>
    <div style="font-size:13px">Based on a real disaster. Flown in respect for those affected; no bonus rewards.</div>
    <button class="btn ghost small" style="align-self:flex-start;position:relative;z-index:1" onclick="flyMission('${esc(m.id)}')">Read the briefing</button></div>`;
}
function reliefBrief(m) {
  const r = m.relief, day = t => new Date(t * 1000).toLocaleDateString("en-US", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" });
  return `<section class="px-cargo relief-brief">
    <div class="relief-notice"><h3>About this mission</h3><p>${esc(r.notice)}</p>
      <p>Please fly it with respect. If you want to help for real, see the links below. Pagani Air Cargo is a flight simulation community; no real cargo is carried.</p></div>
    <span class="relief-label">HUMANITARIAN RELIEF · ${esc(m.id)}</span>
    <h3>${esc(m.title)}</h3><p>${esc(m.briefing)}</p>
    <div class="relief-facts"><div><small>Event</small><b>${esc(r.type)}</b></div><div><small>Alert level</small><b>${esc(r.alert)} (GDACS)</b></div>
      <div><small>Began</small><b>${esc(day(r.start))}</b></div><div><small>Area</small><b>${esc(r.country || "–")}</b></div></div>
    ${r.severity ? `<p class="muted" style="font-size:14px">${esc(r.severity)}</p>` : ""}
    <p class="muted" style="font-size:14px">Source: <a href="${esc(r.source)}" target="_blank" rel="noopener">GDACS alert</a>. PAC only repeats what the source says; follow the link for the full picture.</p>
    <table class="relief-cargo"><thead><tr><th>Cargo</th><th class="r">Pieces</th><th class="r">Weight</th><th>Code</th></tr></thead><tbody>
      ${r.items.map(i => `<tr><td><b>${esc(i.item)}</b><small>${esc(i.why)}</small></td><td class="r mono">${esc(i.pieces)}</td><td class="r mono">${fmt(i.kg)} kg</td><td class="mono">${esc(i.code)}</td></tr>`).join("")}
    </tbody></table>
    <p class="muted" style="font-size:13px">Shipper: humanitarian response depot, ${esc(r.depot_city)} (simulated). No dangerous goods on this flight.</p>
    <div class="relief-ops">${r.ops.map(([k, v]) => `<div><small>${esc(k)}</small><span>${esc(v)}</span></div>`).join("")}</div>
    <div class="relief-notice"><h3>Scoring and pay</h3><p>Flown and scored like any PAC flight, at normal pay. <b>No bonus points.</b> Booking closes ${esc(day(m.expires))}, or sooner when the real airlift winds down.</p></div>
    <div class="relief-help"><h3>How to help for real</h3><p>These organizations are responding. PAC isn't affiliated with them and receives nothing; the links go straight to them.</p>
      <ul>${r.help.map(([t, u]) => `<li><a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)}</a></li>`).join("")}</ul></div></section>`;
}
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
  const owned = d.fleet.map(f => `<tr><td><b>${esc(f.reg)}</b></td><td>${esc(f.type)}</td><td>${esc(f.status)}</td><td>${esc(f.ownership === "wet_lease" ? "Wet lease" : f.ownership === "leased" ? "Leased" : "Owned")}${f.owner_company ? " · " + esc(d.companies[f.owner_company]?.name || "") : ""}</td><td>${f.lease_rate ? money(f.lease_rate) + (f.ownership === "wet_lease" ? "/wk" : "/mo") : ""}</td><td><button class="btn ghost" type="button" data-back="${esc(f.reg)}">${f.ownership === "owned" ? "Sell" : "Return"}</button></td></tr>`).join("");
  body.innerHTML = `<p class="muted">How real cargo airlines get aircraft. Company cash: <b>${money(d.cash)}</b>. Purchases are paid now; leases are charged monthly; wet leases are paid up front by the week.</p>
    <div class="mkt-filter">${["all", "new", "conversion", "used", "lease", "wet"].map(k => `<button type="button" class="btn ${filter === k ? "" : "ghost"}" data-way="${k}">${k === "all" ? "All" : WAY[k]}</button>`).join("")}</div>
    ${filter === "new" || filter === "all" ? `<p class="notice">${esc(d.companies.airbus.note)}</p>` : ""}
    <div class="mkt-grid">${list.map(card).join("") || `<p class="muted">No offers of this kind for PAC's types.</p>`}</div>
    <div id="mktForm"></div>
    ${owned ? `<h3>Aircraft from the market</h3><div class="table-wrap"><table class="fin-table"><thead><tr><th>Reg</th><th>Type</th><th>Status</th><th>How</th><th>Rate</th><th></th></tr></thead><tbody>${owned}</tbody></table></div>` : ""}
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
  root.innerHTML = `<div class="profile-bar"><h1>Commercial</h1><span class="muted">Shipper relations: answer complaints after a late or failed delivery. How PAC responds changes that shipper's account standing for 90 days.</span></div><div id="commercialBody"></div>`;
  staffComplaints($("#commercialBody"));
}
async function staffRoles() {
  const body = $("#staffBody"); body.innerHTML = `<p class="muted">Loading roles…</p>`;
  let d; try { d = await api("/api/staff/roles"); } catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const by = {}; d.holders.forEach(h => (by[h.role] = by[h.role] || []).push(h));
  body.innerHTML = `<p class="muted">Management work follows the role, not the account. Hand a role to a pilot and its tasks move with it. Only the CEO can change roles.</p>
    <div class="table-wrap"><table class="fin-table"><thead><tr><th>Role</th><th>What they own</th><th class="r">Weekly pay</th><th>Held by</th></tr></thead><tbody>
    ${d.roles.map(r => `<tr><td><b>${esc(r.title)}</b></td><td class="muted">${esc(r.does)}</td><td class="r">${r.pay ? "$" + r.pay.toLocaleString("en-US") + "/wk" : "—"}</td><td>${(by[r.key] || []).map(h => `${esc(h.name || h.pilot_id)} <span class="muted">${esc(h.pilot_id)}</span>${d.can_assign ? ` <button class="btn ghost" type="button" data-rm="${esc(h.pilot_id)}|${r.key}">Remove</button>` : ""}`).join("<br>") || '<span class="muted">Open</span>'}</td></tr>`).join("")}</tbody></table></div>
    ${d.can_assign ? `<section class="panel mkt-order"><h3>Give a role</h3><label>Pilot ID <input id="roPid" placeholder="PAC0002"></label><label>Role <select id="roRole">${d.roles.map(r => `<option value="${r.key}">${esc(r.title)}</option>`).join("")}</select></label><button class="btn" id="roGo" type="button">Give role</button></section>` : ""}`;
  const send = async x => { try { await api("/api/staff/roles", { method: "POST", body: x }); staffRoles(); } catch (e) { toast(e.message); } };
  body.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { const [p, r] = b.dataset.rm.split("|"); send({ pilot_id: p, role: r, remove: true }); });
  if ($("#roGo")) $("#roGo").onclick = () => send({ pilot_id: $("#roPid").value, role: $("#roRole").value });
}

async function staffRelief() {
  const body = $("#staffBody");
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
    f.querySelector('[data-act="edit"]').onclick = async () => { if (await send(id, "edit", edits())) { toast("Draft saved."); staffRelief(); } };
    post.onclick = async () => {
      if (!(await send(id, "edit", edits()))) return;
      const checksOn = Object.fromEntries(checks.map(([k]) => [k, f[k].checked]));
      if (await send(id, "post", { checks: checksOn })) { toast("Relief mission posted."); staffRelief(); }
    };
    f.querySelector('[data-act="later"]').onclick = async () => { if (await send(id, "later", { hours: 24 })) { toast("We'll keep it for later."); staffRelief(); } };
    f.querySelector('[data-act="dismiss"]').onclick = async () => { if (await send(id, "dismiss")) { toast("Dismissed."); staffRelief(); } };
  });
  body.querySelectorAll("[data-close]").forEach(b => b.onclick = async () => { if (await send(b.dataset.close, "close")) { toast("Mission closed."); staffRelief(); } });
}
