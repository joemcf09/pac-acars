function displayPhoto(src, width = 800) {
  if (!src || !/^\/(?:api\/fleet\/[^/]+\/photo(?:\?|$)|gallery\/|static\/fleet\/)/.test(src)) return src;
  return '/media/image?src=' + encodeURIComponent(src) + '&w=' + width + '&pipeline=2';
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
  if (view === "fleetmgr" && S.me && !hasCap("fleet")) view = "home";   // scoped section: full admin or the Fleet & Maintenance Manager only
  if (view === "operations" && S.me && !hasCap("operations")) view = "home";   // scoped section: full admin or the Director of Operations only
  if (view === "academy" && S.me && !hasCap("academy")) view = "home";
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
  if (view === "fleetmgr") loadFleetMgr();
  if (view === "operations") loadOps();
  if (view === "academy") loadAcademyDesk();
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
  if (b.dataset.solo) { closeNavigation(); show(b.dataset.solo); return; }   // single management section: act as a direct button
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
// The management dropdown (role sections + Staff) collapses the CEO's long menu. A holder of just one
// section sees a direct button instead of a one-item dropdown, so ordinary pilots keep it simple.
function compactMgmt() {
  const disc = document.getElementById('mgmtDisclosure'), panel = document.getElementById('navGroupMgmt');
  if (!disc || !panel) return;
  const vis = [...panel.querySelectorAll('button[data-view]')].filter(b => !b.classList.contains('auth-hidden'));
  const label = disc.querySelector('.disc-text');
  if (vis.length === 1) {
    disc.classList.add('solo'); disc.dataset.solo = vis[0].dataset.view;
    if (label) label.textContent = vis[0].textContent.trim();
  } else {
    disc.classList.remove('solo'); delete disc.dataset.solo;
    if (label) label.textContent = 'Management';
  }
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

