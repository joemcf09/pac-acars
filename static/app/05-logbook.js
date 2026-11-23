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
          <div><span>C-check due in</span><b>${a.heavy_due_in == null ? "–" : esch(Math.max(0, a.heavy_due_in)) + " h"}</b></div>
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
      ${i.severity === "grounding" ? `<button class="btn ghost small" type="button" data-mxdefer="${i.id}">Defer</button>` : `<button class="btn ghost small" type="button" data-mxground="${i.id}">Ground</button>`}</span>` : "<span></span>"}
    ${staff && i.pirep_id ? `<div class="mx-context"><button class="btn ghost small" type="button" data-mxcontext="${i.id}">Flight details · ${esc(i.flight || 'PIREP')}</button><div data-mxcontext-body="${i.id}" hidden></div></div>` : ''}</div>`).join("")}</div>`;
}
function mxContextHTML(data) {
  const p = data.report, a = data.aog, when = t => t ? new Date(t * 1000).toLocaleString() : '—';
  return `<div class="mx-context-grid"><div><h4>Flight evidence</h4>${p ? `<p><b>${esc(p.flight_number)}</b> · ${esc(p.dep)} → ${esc(p.arr)} · ${esc(p.pilot_name || p.pilot_id)}<br>Landing: <b>${p.landing_rate == null ? 'Not recorded' : `${fmt(p.landing_rate)} fpm`}</b> · <b>${p.landing_g == null ? 'G not recorded' : `${Number(p.landing_g).toFixed(2)} G`}</b><br>PIREP: ${esc(p.status || '—')} · ${esc(p.review_status || '—')} · ${when(p.filed_at)}${p.remarks ? `<br>Remarks: ${esc(p.remarks)}` : ''}</p>` : '<p>There is no linked PIREP for this write-up.</p>'}</div>
    <div><h4>Aircraft recovery</h4>${a ? `<p><b>${esc(a.status.replaceAll('_', ' '))}</b> at ${esc(a.station)}${a.mission_id ? ` · Recovery mission ${esc(a.mission_id)} from ${esc(a.hub)}` : a.contractor ? ' · Contractor bringing parts' : ''}<br>${a.repair_until ? `Repair estimate: ${when(a.repair_until)}` : a.parts_due ? `Parts due: ${when(a.parts_due)}` : 'Parts or inspection status is pending.'}</p>` : '<p>No AOG recovery case is linked to this write-up.</p>'}</div></div>
    <h4>Freight on this arrival</h4>${data.cargo.length ? `<ul>${data.cargo.map(s => `<li><b>${esc(s.awb)}</b> · ${esc(s.commodity)} · ${fmt(s.gross_weight_lbs)} lb · ${esc(s.arrival_status)} at ${esc(s.current_station)} · final ${esc(s.destination)}</li>`).join('')}</ul>` : '<p>No shipment arrival records are linked to this PIREP.</p>'}<p class="muted">Fleet verifies the aircraft and records maintenance. Operations handles held or diverted freight and sends the pilot an OCC instruction; the accepted PIREP and shipment records determine cargo movement.</p>`;
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
async function staffMx(host = $("#staffBody")) {
  let open = [], all = [];
  try { [open, all] = await Promise.all([api("/api/maintenance").then(r => r.items), api("/api/maintenance?all=1").then(r => r.items)]); } catch (e) { toast(e.message); }
  host.innerHTML = `<div class="notice" style="margin-bottom:12px"><b>When an aircraft is grounded:</b> ACARS automatically opens a write-up for a recorded hard landing or tail strike; you do not need to issue a second report. Open Flight details for the touchdown measurements, PIREP state, recovery mission and freight record. Keep the aircraft grounded while the inspection or repair is pending. Record the rectification before clearing a write-up; the AOG recovery flow can clear it automatically when repairs finish. Operations owns pilot instructions and cargo rerouting.</div>
    <h3 style="margin:0 0 8px">Open (${open.length})</h3>${mxItems(open, true)}
    <h3 style="margin:18px 0 8px">Recently cleared</h3>${mxItems(all.filter(i => i.status === "cleared").slice(0, 15), true)}`;
  const act = async (id, body, msg) => { try { await api("/api/staff/maintenance/" + id, { method: "POST", body }); toast(msg); await refreshCore(); staffMx(host); } catch (e) { toast(e.message); } };
  host.querySelectorAll("[data-mxclear]").forEach(b => b.onclick = () => act(b.dataset.mxclear, { action: "clear", note: host.querySelector(`[data-mxnote="${b.dataset.mxclear}"]`).value }, "Write-up cleared."));
  host.querySelectorAll("[data-mxdefer]").forEach(b => b.onclick = () => act(b.dataset.mxdefer, { action: "defer", category: "C" }, "Deferred for 10 days."));
  host.querySelectorAll("[data-mxground]").forEach(b => b.onclick = () => act(b.dataset.mxground, { action: "ground" }, "Aircraft grounded."));
  host.querySelectorAll("[data-mxcontext]").forEach(b => b.onclick = async () => {
    const panel = host.querySelector(`[data-mxcontext-body="${b.dataset.mxcontext}"]`);
    if (!panel.hidden) { panel.hidden = true; return; }
    panel.hidden = false; panel.innerHTML = '<p class="muted">Loading flight details…</p>';
    try { panel.innerHTML = mxContextHTML(await api(`/api/staff/maintenance/${b.dataset.mxcontext}/context`)); }
    catch (e) { panel.innerHTML = `<p class="error">${esc(e.message)}</p>`; }
  });
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
      <section id="cgoActivity" class="cgo-activity" aria-label="Cargo network activity"></section>
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
    const seenKey = `pac-cargo-seen-${S.me?.id || "pilot"}`;
    let lastSeen = 0;
    try { lastSeen = Number(localStorage.getItem(seenKey)) || 0; } catch (e) { /* private window */ }
    if (!Number.isFinite(lastSeen)) lastSeen = 0;
    const [stations, ov] = await Promise.all([api("/api/cargo/stations"), api("/api/cargo/overview" + (lastSeen ? `?since=${encodeURIComponent(lastSeen)}` : ""))]);
    overview = ov;
    renderCargoActivity(ov, lastSeen);
    try { localStorage.setItem(seenKey, String(ov.activity_at)); } catch (e) { /* private window */ }
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
          <td><span class="cgo-com">${esc(x.commodity || "—")}</span>${x.season_name ? ` <span class="tag cgo-season">${esc(x.season_name)}</span>` : ""}${x.recovery_for ? ` <span class="tag grey">Split load · ${esc(x.recovery_for)}</span>` : ""}<small class="muted">${esc(x.shipper || "")} → ${esc(x.consignee || "")}</small></td>
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

function renderCargoActivity(overview, lastSeen) {
  const el = $("#cgoActivity"); if (!el) return;
  const n = overview.activity_counts || {};
  const period = lastSeen && lastSeen < overview.activity_since ? "In the past 7 days"
    : lastSeen ? "Since your last visit" : "In the past 24 hours";
  const events = (overview.activity || []).map(e => {
    const label = e.event_type === "ORDER_WITHDRAWN" ? `${e.awb} moved to another carrier after its deadline`
      : e.event_type === "TRANSFER_RELEASED" ? `${e.awb} returned to the shelf at ${e.from_station || e.to_station}`
      : e.status === "AT_STATION" || e.status === "HELD_AT_STATION"
        ? `${e.awb} arrived at ${e.to_station} and awaits an onward flight to ${e.destination}`
        : `${e.awb} arrived at ${e.to_station} on ${e.flight_number || "a PAC flight"}`;
    return `<li><time>${cargoInventoryDate(e.event_time)}</time><span>${esc(label)}</span></li>`;
  }).join("");
  el.innerHTML = `<h2>While you were away</h2><p class="muted">${period}, PAC received <b>${fmt(n.ORDER_RECEIVED || 0)}</b> new customer shipments, recorded <b>${fmt(n.FLIGHT_ARRIVAL || 0)}</b> shipment arrivals on PAC flights, and <b>${fmt(n.ORDER_WITHDRAWN || 0)}</b> overdue shipments moved to other carriers. Ground and partner movements never count as a pilot flight.</p>
    ${S.me?.staff ? `<button class="btn ghost small" type="button" id="cgoPreviewHandoff">Preview postflight handoff</button>` : ""}
    ${events ? `<ul>${events}</ul>` : `<p class="muted">No other cargo movements in this period. Freight waiting below is available for PAC flights.</p>`}`;
  if (S.me?.staff) $("#cgoPreviewHandoff").onclick = () => offerCargoHandoff([{
    id: "preview", awb: "TRAINING-ONLY", commodity: "Fresh flowers", current_station: "KMIA", destination: "TJSJ",
  }], true);
}

function cargoInventoryDate(timestamp) {
  if (!timestamp) return "—";
  const d = new Date(timestamp * 1000);
  return `${String(d.getUTCDate()).padStart(2, "0")} ${d.toLocaleString("en-US", { month: "short", timeZone: "UTC" }).toUpperCase()} ${String(d.getUTCHours()).padStart(2, "0")}${String(d.getUTCMinutes()).padStart(2, "0")}Z`;
}

const CARGO_EVENT = {
  SPLIT_LOAD_WAITING: e => `Left at ${e.to_station} after ${e.flight_number}; ready for a later flight (customer already charged)`,
  SPLIT_LOAD_REVOKED: e => `Recovery withdrawn after the original flight was rejected`,
  SPLIT_LOAD_RESTORED: e => `Recovery restored after the original flight was accepted`,
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
        ${d.recovery_for ? `<dt>Split load</dt><dd>Left after ${esc(d.recovery_for)} · already paid on the original charter <button type="button" class="linkish" data-pirep="${Number(d.recovery_pirep_id) || 0}">Original PIREP</button></dd>` : ""}
        ${d.recovery_awbs?.length ? `<dt>Follow-up freight</dt><dd>${d.recovery_awbs.map(trackAwb).join(" · ")}</dd>` : ""}
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
