/* ---------------- Fleet ---------------- */
/* PAC's fleet divisions (Feeder, Mainline, Heavy, Heritage): the server labels each type */
const DIVISION_FALLBACK = [{ name: "PAC Feeder", short: "Feeder" }, { name: "PAC Mainline", short: "Mainline" }, { name: "PAC Heavy", short: "Heavy" }, { name: "PAC Heritage", short: "Heritage" }];
const divisions = () => (S.divisions && S.divisions.length ? S.divisions : DIVISION_FALLBACK);
const divOf = code => S.fleet?.[code]?.division || "";
const divShort = name => (divisions().find(d => d.name === name) || {}).short || String(name || "").replace(/^PAC\s+/, "");
const FLEET_ORDER = ["B738F", "B722F", "A306F", "MD11F", "A332F", "B77F", "B744F", "B748F", "B732F", "B733F", "B752F", "B763F", "B742F"];
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
    ${list.map(a => { const g = a.aog, mission = (S.urgent || []).find(m => m.id === g.mission_id);
      const needsFerry = mission && !(S.airframes || []).some(f => f.status === "Available" && f.location === g.hub && mission.aircraft.includes(f.type));
      return `<div class="aog-card">
      <div class="aog-top"><b>${esc(a.reg)}</b> <span class="muted">${esc(S.fleet[a.type]?.name || a.type)} · at ${esc(g.station)}</span><span class="aog-title">${esc(g.title)}</span></div>
      <ol class="aog-steps"><li class="done">Grounded after ${esc(g.cause_flight || "its last flight")}</li>
        <li class="${step(a, 1)}">${g.status === "awaiting_parts" ? (g.contractor ? `Contractor flying ${fmt(g.weight_lbs)} lb of parts in, due ${when(g.parts_due)}` : `Waiting for ${fmt(g.weight_lbs)} lb of parts and the ${esc(g.team || "engineers")} from ${esc(g.hub)}`) : "Parts and engineers on site"}</li>
        <li class="${step(a, 2)}">${g.status === "repairing" ? `Repair under way, back in service about ${when(g.repair_until)}` : "Repair"}</li>
        <li>Back in service</li></ol>
      ${g.status === "awaiting_parts" && g.mission_id && !g.contractor ? `${needsFerry ? `<p class="muted"><b>Aircraft positioning needed at ${esc(g.hub)}.</b> Open the recovery plan, choose an available aircraft on the Aircraft step, and use <b>Fly it to ${esc(g.hub)}</b> to create a ferry charter. No matching job-board route is required.</p>` : ""}<button class="btn small" onclick="flyMission('${esc(g.mission_id)}')">Plan recovery mission ${esc(g.mission_id)} →</button>` : ""}
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

