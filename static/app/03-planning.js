/* ---------------- Flight planning: four steps on tabs (Briefing, Aircraft, Load sheet, SimBrief & request) ---------------- */
try { S.extraFuel = Number(localStorage.getItem("pac-extra-fuel")) || 0; } catch (_) {}
const DTABS = [["brief", "Briefing"], ["aircraft", "Aircraft"], ["load", "Load sheet"], ["plan", "SimBrief & request"]];
const PLANNING_DRAFT_AGE = 7 * 24 * 60 * 60 * 1000;
function planningDraftKey() { return S.me?.id ? `pac-planning-draft-v1-${S.me.id}` : null; }
function clearPlanningDraft() { const key = planningDraftKey(); if (key) try { localStorage.removeItem(key); } catch (_) {} }
function readPlanningDraft() {
  const key = planningDraftKey(); if (!key) return null;
  try {
    const draft = JSON.parse(localStorage.getItem(key) || "null");
    if (!draft || !draft.savedAt || Date.now() - draft.savedAt > PLANNING_DRAFT_AGE || draft.savedAt > Date.now() + 60000) { clearPlanningDraft(); return null; }
    return draft;
  } catch (_) { clearPlanningDraft(); return null; }
}
function savePlanningDraft() {
  const key = planningDraftKey(), m = S.selected;
  if (!key || !m || S.booking) return;
  const draft = { savedAt: Date.now(), missionId: m.id, origin: m.origin.icao, destination: m.destination.icao, payload: Number(m.payload_lbs || 0), category: m.category,
    board: S.board, aircraft: S.aircraft, airframe: S.airframe, transferIds: S.cargoTransferIds?.[m.id] || [],
    tab: S.dTab || "brief", briefReviewed: !!S.briefReviewed,
    seed: S.lsCache?.[lsKey(m)]?.seed ?? (S.planningSeedByMission?.[m.id]?.aircraft === S.aircraft ? S.planningSeedByMission[m.id].seed : null), seedAircraft: S.aircraft,
    charterSpec: m.charter ? { ...m.charter, customer_id: S.charterSpec?.customer_id || "", shipment_id: S.charterSpec?.shipment_id || "" } : null };
  try { localStorage.setItem(key, JSON.stringify(draft)); } catch (_) { /* private window or storage full */ }
}
function applyPlanningDraft(m, draft, restoreBoard = false) {
  if (!draft || draft.missionId !== m.id || draft.origin !== m.origin.icao || draft.destination !== m.destination.icao || draft.payload !== Number(m.payload_lbs || 0) || draft.category !== m.category) return false;
  if (restoreBoard && document.querySelector(`[data-board="${CSS.escape(draft.board || "")}"]`)) S.board = draft.board;
  if (!m.charter && draft.aircraft && S.fleet[draft.aircraft] && !S.fleet[draft.aircraft].retired && fleetOrder(m).includes(draft.aircraft)) S.aircraft = draft.aircraft;
  S.airframe = null;
  const frame = (S.airframes || []).find(a => a.reg === draft.airframe && a.type === S.aircraft && a.status === "Available" && a.location === m.origin.icao);
  if (frame) S.airframe = frame.reg;
  else if (!draft.airframe) S.airframe = defaultAirframe(m, S.aircraft);
  S.cargoTransferIds[m.id] = Array.isArray(draft.transferIds) ? draft.transferIds.filter(x => typeof x === "string").slice(0, 50) : [];
  if (draft.seedAircraft === S.aircraft && ((typeof draft.seed === "string" && draft.seed.length < 100) || Number.isSafeInteger(draft.seed)))
    (S.planningSeedByMission ||= {})[m.id] = { aircraft: S.aircraft, seed: draft.seed };
  S.dTab = DTABS.some(([key]) => key === draft.tab) ? draft.tab : "brief";
  S.dTabFor = m.id;
  S.briefReviewed = !!draft.briefReviewed;
  return true;
}
async function restorePlanningDraft(clearMissing = false) {
  if (S.booking) { clearPlanningDraft(); S.planningDraftChecked = true; return; }
  const draft = readPlanningDraft();
  if (!draft) { S.planningDraftChecked = true; return; }
  let m = allFlights().find(x => x.id === draft.missionId);
  if (!m && draft.charterSpec) {
    try {
      const quote = await api("/api/charter/quote", { method: "POST", body: draft.charterSpec });
      m = quote.mission;
      S.charterMission = m; S.charterWarnings = quote.warnings;
      S.charterSpec = { ...draft.charterSpec, _o: null, _d: null };
    } catch (_) { if (clearMissing) S.planningDraftChecked = true; return; }
  }
  if (S.selected) { S.planningDraftChecked = true; return; }
  if (!m) { if (clearMissing) S.planningDraftChecked = true; return; }
  S.aircraft = m.aircraft[0];
  if (!applyPlanningDraft(m, draft, true)) { clearPlanningDraft(); S.planningDraftChecked = true; return; }
  S.selected = m;
  S.plannerDraftRestored = true;
  S.planningDraftChecked = true;
}
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
function dossierTabState(m, t) {
  if (t === "brief") return S.briefReviewed ? { label: "Reviewed", kind: "ready" } : { label: "Review", kind: "pending" };
  if (t === "aircraft") return dossierAcReady(m) ? { label: "Ready", kind: "ready" } : { label: "Needs attention", kind: "attention" };
  if (t === "load") {
    if (m.training) return { label: "No cargo", kind: "ready" };
    const ls = S.lsCache?.[lsKey(m)];
    return !ls ? { label: "Check load", kind: "pending" } : !ls.ok ? { label: "Over limit", kind: "attention" }
      : ls.balance?.available && !ls.balance.within_envelope ? { label: "Balance issue", kind: "attention" }
      : { label: "Within limits", kind: "ready" };
  }
  if (t === "plan") return S.ofpErrors?.length ? { label: "Fix OFP", kind: "attention" } : S.ofp ? { label: "OFP ready", kind: "ready" } : { label: "No OFP yet", kind: "pending" };
  return { label: "", kind: "pending" };
}
function updateDossierTabStatus(m) {
  DTABS.forEach(([key], i) => {
    const b = $(`#dpt-${key}`); if (!b) return;
    const state = dossierTabState(m, key);
    b.classList.toggle("done", state.kind === "ready");
    b.classList.toggle("attention", state.kind === "attention");
    b.querySelector(".n").textContent = state.kind === "ready" ? "✓" : i + 1;
    b.querySelector(".dp-step-status").textContent = state.label;
  });
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
    [m.charter && m.payload_lbs ? "Requested cargo" : "Payload", m.payload_lbs ? `${fmt(m.payload_lbs)} lb` : "Ferry"],
    m.reward ? ["Reward", `${fmt(m.reward)} pts`] : null,
    Number(m.deliver_by) > 0 ? ["Arrive by", date(m.deliver_by)] : null,
  ].filter(Boolean);
  const stn = (a, label) => `<div class="dp-stn"><small>${label}</small><b>${esc(a.icao)}</b><span>${esc(a.city || a.name || "")}</span><a href="#stations" class="st-link" data-station="${esc(a.icao)}">Station guide</a></div>`;
  return `<div class="dp-head">
    <div class="dp-top"><button type="button" class="dp-back" onclick="backToFlights()">← Back to flights</button>
      <span class="dp-kind">${esc(m.id)} · ${esc(m.category)} · ${esc(m.priority)} priority</span>
      <button type="button" class="dp-crew" onclick="planSelectedWithCrew()">Plan with crew →</button></div>
    <h2>${esc(m.title)}</h2>
    <div class="dp-route">${stn(m.origin, "From")}<span class="dp-arrow" aria-hidden="true"><i></i></span>${stn(m.destination, "To")}</div>
    <div class="dp-chips">${chips.map(([k, v]) => `<div><span>${k}</span><b>${esc(v)}</b></div>`).join("")}<div id="payChip" class="dp-pay"><span>Your pay</span><b>…</b></div></div>
  </div>`;
}
function renderDossier() {
  const m = S.selected, d = $("#dossier");
  $("#missionBrowse").hidden = !!m;
  d.hidden = !m;
  if (!m) { d.innerHTML = `<div class="d-body"><h2>Choose a mission</h2><p class="muted">Pick a waybill from the list to read the briefing, plan it in SimBrief and request it for your next flight.</p></div>`; return; }
  if (S.dTabFor !== m.id) { S.dTab = "brief"; S.dTabFor = m.id; }
  savePlanningDraft();
  const held = !!S.booking, tab = S.dTab || "brief", ix = DTABS.findIndex(t => t[0] === tab);
  const next = DTABS[ix + 1], prev = DTABS[ix - 1];
  d.innerHTML = `${dossierHeader(m)}
  ${S.plannerDraftRestored ? `<p class="dp-draft-note" role="status">Draft restored on this device. Recheck aircraft availability, cargo and your SimBrief OFP before requesting.</p>` : ""}
  <div class="dp-tabs" role="tablist" aria-label="Plan this flight">${DTABS.map(([k, label], i) => {
    const state = dossierTabState(m, k);
    return `<button type="button" role="tab" id="dpt-${k}" aria-controls="dpPane" aria-selected="${k === tab}" tabindex="${k === tab ? 0 : -1}" data-tab="${k}" class="${state.kind === "ready" ? "done" : state.kind === "attention" ? "attention" : ""}"><span class="n">${state.kind === "ready" ? "✓" : i + 1}</span><span class="dp-tab-copy"><span>${label}</span><small class="dp-step-status">${state.label}</small></span></button>`;
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
  if (tab === "plan" && !held) { loadPlanHelper(m); ensureLoadsheet(m).then(() => { if (S.selected?.id === m.id) { updateDossierTabStatus(m); planVsLoad(m); } }).catch(() => {}); }
  const go = t => { if (tab === "brief" && t !== "brief") S.briefReviewed = true; S.dTab = t; renderDossier(); const top = $("#dossier").getBoundingClientRect().top; if (top < 0) $("#dossier").scrollIntoView({ behavior: "smooth", block: "start" }); $("#dpPane")?.focus({ preventScroll: true }); };
  d.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => go(b.dataset.tab));
  d.querySelectorAll("[data-go]").forEach(b => b.onclick = () => go(b.dataset.go));
  d.querySelector(".dp-tabs").onkeydown = e => {
    const keys = { ArrowRight: 1, ArrowLeft: -1 }; if (!keys[e.key]) return;
    e.preventDefault(); const j = (ix + keys[e.key] + DTABS.length) % DTABS.length; go(DTABS[j][0]); $(`#dpt-${DTABS[j][0]}`)?.focus();
  };
  if (held) return;
  d.querySelectorAll("input[name=ac]").forEach(r => r.onchange = () => { S.aircraft = r.value; S.ofp = null; S.ofpErrors = []; S.airframe = defaultAirframe(m, r.value); S.cargoChange = null; renderDossier(); });
  d.querySelectorAll("input[name=af]").forEach(r => r.onchange = () => { S.airframe = r.value; S.cargoChange = null; renderDossier(); });
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
  const recoveryPositioning = m.aog_case && !(S.airframes || []).some(a => a.status === "Available" && a.location === m.origin.icao && m.aircraft.includes(a.type))
    ? `<div class="notice"><b>Bring an aircraft to ${esc(m.origin.icao)} first.</b> The engineers and kit leave from this airport, but no suitable PAC tail is parked here. Choose a qualified type and an available tail below, then click <b>Fly it to ${esc(m.origin.icao)}</b>. PAC will build a ferry charter from that tail's current airport; you do not need to find a job on that route. Jumpseat to the tail's airport if needed. After the ferry flight is accepted and the aircraft reaches ${esc(m.origin.icao)}, reopen ${esc(m.id)} and fly the recovery leg.</div>` : "";
  const types = m.charter ? `<p class="dp-lead">Charter aircraft: <b>${esc(S.fleet[m.aircraft[0]].name)}</b>. Change it in the charter form and rebuild.</p>${capacityNote(m, S.aircraft)}` : `
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
  return `${recoveryPositioning}${types}${tail}<details class="journey-help"><summary>Aircraft missing? Understand travel and ferry options</summary>${travelGuideHTML()}</details>`;
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
  const savedSeed = S.planningSeedByMission?.[m.id];
  const ls = await api("/api/plan/loadsheet", { method: "POST", body: { mission_id: m.id, charter: m.charter, aircraft: m.charter ? m.aircraft[0] : S.aircraft, airframe: m.contract ? null : S.airframe, seed: prior?.seed ?? (savedSeed?.aircraft === S.aircraft ? savedSeed.seed : null), cargo_transfer_ids: S.cargoTransferIds?.[m.id] || [] } });
  return (S.lsCache[key] = ls);
}
async function loadLoadsheet(m) {
  const el = $("#lsPanel"); if (!el) return;
  const key = lsKey(m);
  try {
    const ls = await ensureLoadsheet(m);
    if ($("#lsPanel") !== el || lsKey(m) !== key) return;
    if (S.cargoPending?.missionId === m.id) {
      S.cargoChange = cargoChangeMessage(S.cargoPending, ls);
      S.cargoPending = null;
    }
    el.innerHTML = loadsheetHTML(ls, m);
    updateDossierTabStatus(m);
    savePlanningDraft();
    el.querySelectorAll("[data-pos]").forEach(c => c.onclick = () => lsFocus(el, c.dataset.pos));
    wireTransferCargo(el, ls, m);
    wireCargoFolder(el, ls);
    wireLsTabs(el, ls);
  } catch (e) {
    S.cargoPending = null;
    updateDossierTabStatus(m);
    el.innerHTML = `<div class="notice">${esc(e.message)}${(S.cargoTransferIds?.[m.id] || []).length ? ' <button type="button" class="linkish" data-clear-transfers>Clear selected transfer cargo</button>' : ""}</div>`;
    el.querySelector("[data-clear-transfers]")?.addEventListener("click", () => {
      S.cargoTransferIds[m.id] = [];
      savePlanningDraft();
      loadLoadsheet(m);
    });
  }
}
function cargoChangeMessage(before, ls) {
  const transfer = Number(ls.cargo_transfer_weight_lbs || 0), payload = Number(ls.totals.weight_lbs || 0);
  const change = (label, delta) => `${label} ${delta > 0 ? "increased" : delta < 0 ? "decreased" : "stayed the same"}${delta ? ` by ${fmt(Math.abs(delta))} lb` : ""}`;
  const payloadDelta = payload - before.payload;
  return `${change("Transfer cargo", transfer - before.transfer)}; ${change("other cargo", payload - transfer - (before.payload - before.transfer))}; ${change("total payload", payloadDelta)} at ${fmt(payload)} lb.${payloadDelta ? " The weight and limit bars have been recalculated." : " The weight bars can stay the same because the cargo mix changed, not the total weight."}`;
}
function lsFocus(root, pos) {
  root.querySelectorAll(".on").forEach(x => x.classList.remove("on"));
  root.querySelectorAll(`[data-pos="${CSS.escape(pos)}"]`).forEach(x => x.classList.add("on"));
  const row = root.querySelector(`tr[data-pos="${CSS.escape(pos)}"]`);
  if (row) { const box = row.closest(".ls-table-wrap"); if (box) box.scrollTop = row.offsetTop - box.clientHeight / 2; }
}
const LS_CLASS = p => p.dg ? "dg" : p.shc.some(c => ["PER", "PIL", "COL", "PES", "PEF", "CRT", "EAT"].includes(c)) ? "cool" : p.shc.includes("VAL") ? "val" : p.shc.some(c => ["AOG", "HEA", "BIG"].includes(c)) ? "heavy" : p.shc.includes("AVI") ? "avi" : "gen";
function deckRow(list, byPos, cap, label, positionLimits = {}) {
  return `<div class="ls-deck-row"><span class="ls-deck-label">${label}</span><div class="ls-cells">${list.map(pos => {
    const p = byPos[pos], limit = Math.min(cap, Number(positionLimits[pos]) || cap);
    const fill = p ? Math.max(.08, Math.min(1, p.weight_lbs / limit)) : 0;
    return p ? `<button type="button" class="ls-cell ${LS_CLASS(p)}" data-pos="${esc(pos)}" title="${esc(`${pos} · ${p.unit} · ${p.contents} · ${fmt(p.weight_lbs)} lb / ${fmt(limit)} lb modeled position limit${p.dg ? " · DG " + p.dg : ""}`)}" aria-label="${esc(`${pos}, ${p.contents}, ${fmt(p.weight_lbs)} pounds of ${fmt(limit)} pound modeled position limit`)}"><i style="height:${Math.round(fill * 100)}%"></i><span>${esc(pos.replace(" BULK", ""))}</span></button>`
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
  const transferWeight = Number(ls.cargo_transfer_weight_lbs || 0);
  const totalPayload = Number(ls.totals.weight_lbs || 0);
  const balanceIssue = ls.balance?.available && !ls.balance.within_envelope;
  return `
  <div class="ls-title"><div><span class="kicker">Preliminary load sheet</span><h3>${esc(ls.aircraft_name)}${tail ? ` · <span class="mono">${esc(tail)}</span>` : ""} · ${esc(ls.origin.icao)} → ${esc(ls.destination.icao)}</h3>
    <p class="muted">${ls.ferry ? "Ferry flight: the hold is empty." : `${units} unit${units === 1 ? "" : "s"} · ${fmt(ls.totals.pieces)} pieces · ${fmt(ls.totals.weight_lbs)} lb · ${(ls.shipments || []).length} shipment${(ls.shipments || []).length === 1 ? "" : "s"}`}</p></div>
    <span class="ls-status ${ls.ok && !balanceIssue ? "ok" : "bad"}">${!ls.ok ? "Over a modeled weight limit" : balanceIssue ? "Balance needs review" : "Within modeled limits"}</span></div>
  <details class="ls-guide"><summary><span class="ls-guide-icon" aria-hidden="true">?</span><span><b>Why do these numbers look like this?</b><small>A quick guide to the cargo, fuel and weight checks on this flight</small></span></summary>
    <div class="ls-guide-grid">
      <section><h4>1 · Cargo makes the payload</h4><p>${fmt(Math.max(0, totalPayload - transferWeight))} lb other cargo + ${fmt(transferWeight)} lb selected transfer cargo = <b>${fmt(totalPayload)} lb payload</b>. Checked transfer freight takes the place of other cargo within the planned load; it does not go on top.</p></section>
      <section><h4>2 · Build up the aircraft weight</h4><p>${fmt(L.dow)} lb dry operating weight + ${fmt(L.payload)} lb payload = <b>${fmt(L.zfw)} lb zero fuel weight</b>. Add ${fmt(L.tof)} lb takeoff fuel for <b>${fmt(L.tow)} lb at takeoff</b>.</p></section>
      <section><h4>3 · Fuel changes during the flight</h4><p>The ${fmt(f.block)} lb block fuel includes ${fmt(f.taxi)} lb for taxi. After taxi, ${fmt(L.tof)} lb remains for takeoff. Burning an estimated ${fmt(L.trip)} lb on the trip leaves an estimated <b>${fmt(L.law)} lb landing weight</b>.</p></section>
      <section><h4>4 · Read the green bars</h4><p>Each bar compares a planned weight with one aircraft limit. The margin is the gap to that limit. The smallest structural margin is <b>${fmt(L.underload)} lb</b>; that is not permission to add that much cargo. Check the separate MAX PL payload bar too.</p></section>
    </div>
    <p class="ls-guide-foot">These are PAC planning estimates. The dispatch release uses the fuel and weights from your SimBrief OFP when you request the flight.</p>
  </details>
  ${!ls.ferry ? `<div class="ls-payload-summary" aria-label="Payload breakdown">
    <div><span>Other cargo</span><b>${fmt(Math.max(0, totalPayload - transferWeight))} lb</b><small>Assigned to this flight</small></div>
    <div><span>Transfer cargo</span><b>${fmt(transferWeight)} lb</b><small>${transferIds.size} selected from this station</small></div>
    <div class="ls-payload-total"><span>Total payload</span><b>${fmt(totalPayload)} lb</b><small>Used in the weight and limit checks below</small></div>
  </div>` : ""}
  ${S.cargoChange ? `<p class="ls-change" role="status"><b>What changed?</b> ${esc(S.cargoChange)}</p>` : ""}
  ${transferOptions.length ? `<section class="ls-transfer"><h4>Choose transfer cargo at ${esc(ls.origin.icao)}</h4><p class="muted">Select freight already at this station and routed through ${esc(ls.destination.icao)}. It keeps its original AWB and is delivered only when it reaches its final destination.</p>
    <p class="ls-transfer-breakdown"><b>Included in this load:</b> ${fmt(transferWeight)} lb selected transfer freight + ${fmt(Math.max(0, totalPayload - transferWeight))} lb other cargo = <b>${fmt(totalPayload)} lb total payload</b>. Checked freight replaces other cargo; it is not added on top. The green limit bars can stay the same when only the cargo mix changes.</p>
    <div class="ls-transfer-list">${transferOptions.map(x => `<label><input type="checkbox" data-transfer-id="${esc(x.id)}" ${transferIds.has(x.id) ? "checked" : ""}><span><b>${esc(x.awb)}</b> · ${esc(x.commodity || "Cargo")} · ${fmt(x.gross_weight_lbs)} lb · ${fmt(x.pieces)} pcs · final ${esc(x.destination)}${x.recovery_for ? ` <span class="tag grey">Split load from ${esc(x.recovery_for)} · prepaid</span>` : ""}${x.claimed_by_me ? ` <span class="tag lane-pref">Held for you</span>` : ""}${x.truck_nm ? ` <span class="tag grey" title="PAC flies it to your destination; the last leg goes by road">last ${fmt(x.truck_nm)} nm by truck</span>` : ""}</span><small>${esc(x.shipper || "—")} → ${esc(x.consignee || "—")}</small>${(x.notes || []).map(n => `<small class="ls-note"><b>Handover note from ${esc(n.pilot)} at ${esc(n.station || "")}:</b> ${esc(n.text)}</small>`).join("")}</label>`).join("")}</div></section>` : ""}
  ${partial ? `<div class="notice">The ${esc(ls.aircraft_name)} carries up to ${fmt(ls.limits.max_payload)} lb, so you'll take ${fmt(ls.totals.weight_lbs)} lb of the ${fmt(ls.payload_requested)} lb consignment.</div>` : ""}
  ${!ls.ok ? `<div class="notice err">This load and fuel go over a structural limit${ls.checks.some(c => c.code === "MTOW" && !c.ok) ? ": SimBrief will cut the cargo to fit under the take-off weight limit" : ""}. Pick a larger type on the Aircraft step, or plan less fuel or cargo.</div>` : ""}
  ${lsTabsHTML(ls, units)}
  <div class="ls-pane" data-lspane="load" ${(S.lsTab || "load") === "load" || !units ? "" : "hidden"}>
  ${ls.ferry ? "" : `<div class="ls-deck" aria-label="Cargo positions, nose on the left">
    <div class="ls-nose" aria-hidden="true">NOSE</div>
    <div class="ls-decks">${deckRow(ls.deck.main, byPos, ls.deck.cap, ls.aircraft === "B738F" ? "Main deck · AAY bays + compact P12" : `Main deck · ${esc(ls.deck.uld)}`, ls.position_limits)}${ls.deck.lower.length ? deckRow(ls.deck.lower, byPos, ls.deck.lcap, `Lower · ${esc(ls.deck.luld)}`, ls.position_limits) : ""}</div></div>
    <div class="ls-legend"><span class="gen">General</span><span class="cool">Temperature / perishable</span><span class="val">Valuable</span><span class="heavy">Heavy / AOG / outsize</span><span class="avi">Live animals</span><span class="dg">Dangerous goods</span><span class="muted">Bar height = planned weight against that position's modeled limit. Select a position for details.</span></div>
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
        <tr class="under"><td>Smallest structural margin</td><td>${fmt(L.underload)}</td></tr></tbody></table>
      <p class="muted ls-fine">${ls.dow_source?.kind === "learned" ? `Dry operating weight estimated from ${ls.dow_source.flights} recent PAC SimBrief plans for this type; check your aircraft's own figures.` : "Dry operating weight estimated from published limits. Recent PAC SimBrief plans may improve the estimate, but do not verify this airframe's actual weight."}</p>
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
    S.cargoPending = { missionId: m.id, transfer: Number(ls.cargo_transfer_weight_lbs || 0), payload: Number(ls.totals.weight_lbs || 0) };
    S.cargoChange = null;
    S.cargoTransferIds[m.id] = ids;
    savePlanningDraft();
    delete S.lsCache?.[lsKey(m)];
    updateDossierTabStatus(m);
    el.querySelectorAll("[data-transfer-id]").forEach(x => x.disabled = true);
    el.querySelector(".ls-change")?.remove();
    el.querySelector(".ls-payload-summary")?.insertAdjacentHTML("afterend", `<p class="ls-change" role="status">Recalculating the cargo mix and weight limits…</p>`);
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
    S.volCap ||= {};
    const vk = `${m.id}|${ac}`, had = JSON.stringify(S.volCap[vk] || null);
    if (e.volume_cap) S.volCap[vk] = e.volume_cap; else delete S.volCap[vk];
    if (S.selected?.id !== m.id) return;
    if (had !== JSON.stringify(S.volCap[vk] || null)) {   // the payload that fits changed: refresh the note and the SimBrief link
      const vn = $("#volNote"); if (vn) vn.innerHTML = volNoteHtml(S.volCap[vk], m);
      const sb = $("#sbPlan"); if (sb) sb.href = simbriefUrl(m, ac);
    }
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
  const vc = S.volCap?.[`${m.id}|${ac}`];
  // the volume note fills in when the estimate arrives (#volNote); with it, the hold, not the weight, sets the load
  return `<div id="volNote">${volNoteHtml(vc, m)}</div>` + (vc ? "" : weightNote(m, ac, f));
}
function weightNote(m, ac, f) {
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
      clearPlanningDraft();
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

