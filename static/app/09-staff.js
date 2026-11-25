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
/* ---------------- Fleet & maintenance (scoped: Fleet Manager + full admin) ---------------- */
async function loadFleetMgr() {
  const root = $("#fleetMgrRoot");
  if (!root) return;
  S.fleetTab = S.fleetTab || "types";
  const tabs = [["types", "Fleet types"], ["airframes", "Airframes"], ["mx", "Maintenance"], ["recs", "Recommendations"]];
  root.innerHTML = `<div class="profile-bar"><h1>Fleet &amp; maintenance</h1><span class="muted">Manage aircraft types, the airframe roster and open maintenance write-ups. Buying and leasing aircraft needs the owner's approval.</span></div>
    <div class="msg-tabs" style="margin-bottom:16px">${tabs.map(([k, t]) => `<button class="${S.fleetTab === k ? "on" : ""}" data-ftab="${k}">${t}</button>`).join("")}</div>
    <div id="fleetMgrBody"></div>`;
  root.querySelectorAll("[data-ftab]").forEach(b => b.onclick = () => { S.fleetTab = b.dataset.ftab; loadFleetMgr(); });
  const body = $("#fleetMgrBody");
  if (S.fleetTab === "airframes") staffAirframes(body);
  else if (S.fleetTab === "mx") staffMx(body);
  else if (S.fleetTab === "recs") fleetRecs(body);
  else staffTypes(undefined, body);
}
const REC_WAY = { new: "Buy new", conversion: "Buy & convert", used: "Buy used", lease: "Lease", wet: "Wet lease" };
const REC_STATUS = { pending: "amber", approved: "green", declined: "" };
function recPrice(o) { return o.way === "lease" ? money(o.monthly) + "/mo" : o.way === "wet" ? money(o.weekly) + "/wk" : money(o.price); }
async function fleetRecs(body) {
  body.innerHTML = `<p class="muted">Loading…</p>`;
  let cat, data;
  try { [cat, data] = await Promise.all([api("/api/staff/fleet-catalog"), api("/api/staff/fleet-recs")]); }
  catch (e) { body.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
  const offers = cat.offers || [], canDecide = !!data.can_decide;
  const recCard = r => {
    const when = r.created ? new Date(r.created * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
    const acts = (r.status === "pending" && canDecide)
      ? `<div class="row" style="margin-top:8px"><button class="btn small" data-rec-ok="${r.id}">Approve &amp; order</button><button class="btn ghost small" data-rec-no="${r.id}">Decline</button></div>`
      : r.status !== "pending" ? `<p class="muted" style="margin:6px 0 0;font-size:13px">${esc(r.status === "approved" ? "Approved" : "Declined")}${r.decided_name ? " by " + esc(r.decided_name) : ""}${r.decide_note ? " · " + esc(r.decide_note) : ""}</p>` : "";
    return `<article class="rec-card"><div class="row" style="justify-content:space-between;gap:10px;align-items:baseline"><b>${esc(r.aircraft_name)} · ${esc(r.reg)}</b><span class="tag ${REC_STATUS[r.status] || "grey"}" style="margin:0">${esc(r.status)}</span></div>
      <p class="muted" style="margin:2px 0;font-size:13px">${REC_WAY[r.way] || r.way} · to ${esc(r.hub)}${r.weeks ? " · " + r.weeks + " wk" : ""} · by ${esc(r.by_name || r.by_pilot)} · ${when}</p>
      ${r.note ? `<p style="margin:4px 0 0">${esc(r.note)}</p>` : ""}${acts}</article>`;
  };
  // the same cards as the owner's Fleet market, but the button files a recommendation instead of placing an order
  const WAY = { new: "Buy new", conversion: "Buy used + convert", used: "Buy used", lease: "Lease", wet: "Wet lease (ACMI)" };
  const filter = S.recWay || "all";
  const list = offers.filter(o => filter === "all" || o.way === filter);
  const price = o => o.price ? money(o.price) : o.monthly ? `${money(o.monthly)} <small>/ month</small>` : `${money(o.weekly)} <small>/ week</small>`;
  const card = o => `<div class="mkt-card"><div class="mkt-co">${o.logo ? `<img src="${esc(o.logo)}" alt="${esc(o.company_name)}">` : `<span class="mkt-name">${esc(o.company_name || "Second-hand market")}</span>`}<small>${esc(o.company_kind || "Used aircraft")}${o.company_country ? " · " + esc(o.company_country) : ""}</small></div>
    <div class="mkt-ac"><b>${esc(o.aircraft_name)}</b><span class="tag dark">${esc(WAY[o.way])}</span></div><p class="muted">${esc(o.what)}</p>
    <div class="mkt-foot"><span class="mkt-price">${price(o)}</span><span class="muted">ready in ${o.lead_days} days</span><button class="btn" type="button" data-rec-offer="${esc(o.id)}">Request for recommendation</button></div></div>`;
  body.innerHTML = `<p class="muted" style="max-width:90ch">The aircraft PAC could buy or lease. Pick one and send it to the owner as a recommendation; approving it places the order and spends company cash. You can't buy aircraft directly.</p>
    <div class="mkt-filter">${["all", "new", "conversion", "used", "lease", "wet"].map(k => `<button type="button" class="btn ${filter === k ? "" : "ghost"}" data-rec-way="${k}">${k === "all" ? "All" : WAY[k]}</button>`).join("")}</div>
    <div class="mkt-grid">${list.map(card).join("") || `<p class="muted">No offers of this kind for PAC's types.</p>`}</div>
    <div id="recFormHost"></div>
    <h3 style="margin:22px 0 10px">Recommendations</h3>
    ${(data.recs || []).length ? `<div class="rec-grid">${data.recs.map(recCard).join("")}</div>` : `<p class="muted">None yet.</p>`}`;
  body.querySelectorAll("[data-rec-way]").forEach(b => b.onclick = () => { S.recWay = b.dataset.recWay; fleetRecs(body); });
  body.querySelectorAll("[data-rec-offer]").forEach(b => b.onclick = () => {
    const o = offers.find(x => x.id === b.dataset.recOffer), host = body.querySelector("#recFormHost");
    host.innerHTML = `<form class="form-card" id="recForm"><h3 class="full" style="margin:0">Recommend: ${esc(WAY[o.way])}, ${esc(o.aircraft_name)}${o.company_name ? " from " + esc(o.company_name) : ""} · ${price(o)}</h3>
      <div class="field"><label for="recReg">Proposed registration</label><input id="recReg" name="reg" placeholder="N306PC" maxlength="8" required></div>
      <div class="field"><label for="recHub">Deliver to hub</label><select id="recHub" name="hub">${(cat.hubs || []).map(h => `<option>${esc(h)}</option>`).join("")}</select></div>
      ${o.way === "wet" ? `<div class="field"><label for="recWeeks">Weeks (wet lease)</label><input id="recWeeks" name="weeks" type="number" min="1" max="12" value="4"></div>` : ""}
      <div class="field full"><label for="recNote">Why PAC needs it (note to the owner)</label><textarea id="recNote" name="note" rows="2" maxlength="500" placeholder="Capacity on a growing lane, replacing an aging airframe, a good lease rate…"></textarea></div>
      <div class="full row"><button class="btn" type="submit">Send recommendation to the owner</button><button class="btn ghost" type="button" id="recCancel">Cancel</button></div></form>`;
    host.scrollIntoView({ behavior: "smooth" });
    host.querySelector("#recCancel").onclick = () => { host.innerHTML = ""; };
    host.querySelector("#recForm").onsubmit = async e => {
      e.preventDefault();
      const f = e.target, payload = { offer: o.id, reg: f.reg.value, hub: f.hub.value, note: f.note.value };
      if (f.weeks) payload.weeks = f.weeks.value;
      const btn = f.querySelector("button[type=submit]"); btn.disabled = true;
      try { await api("/api/staff/fleet-recs", { method: "POST", body: payload }); toast("Recommendation sent to the owner."); fleetRecs(body); }
      catch (ex) { toast(ex.message); btn.disabled = false; }
    };
  });
  body.querySelectorAll("[data-rec-ok]").forEach(b => b.onclick = async () => {
    if (!confirm("Approve this and place the order? This spends company cash.")) return;
    b.disabled = true;
    try { const r = await api("/api/staff/market/rec/" + b.dataset.recOk, { method: "POST", body: { action: "approve" } }); toast(`Ordered ${r.ordered.reg}, delivering to ${r.ordered.deliver_to}.`); fleetRecs(body); }
    catch (e) { toast(e.message); b.disabled = false; }
  });
  body.querySelectorAll("[data-rec-no]").forEach(b => b.onclick = async () => {
    const note = (prompt("Decline this recommendation. Optional note back to the Fleet Manager:") ?? "").trim();
    b.disabled = true;
    try { await api("/api/staff/market/rec/" + b.dataset.recNo, { method: "POST", body: { action: "decline", note } }); toast("Recommendation declined."); fleetRecs(body); }
    catch (e) { toast(e.message); b.disabled = false; }
  });
}
/* ---------------- Ops desk (scoped: Director of Operations + full admin) ---------------- */
async function loadOps() {
  const root = $("#opsRoot");
  if (!root) return;
  S.opsTab = S.opsTab || "events";
  const tabs = [["exceptions", "Exceptions"], ["notices", "Notices & announcements"], ["events", "Events"], ["campaigns", "Campaigns"], ["relief", "Relief missions"]];
  root.innerHTML = `<div class="profile-bar"><h1>Ops desk</h1><span class="muted">The airline's operational tempo: points events, cargo campaigns and relief missions.</span></div>
    <div class="msg-tabs" style="margin-bottom:16px">${tabs.map(([k, t]) => `<button class="${S.opsTab === k ? "on" : ""}" data-otab="${k}">${t}</button>`).join("")}</div>
    <div id="opsBody"></div>`;
  root.querySelectorAll("[data-otab]").forEach(b => b.onclick = () => { S.opsTab = b.dataset.otab; loadOps(); });
  const body = $("#opsBody");
  if (S.opsTab === "exceptions") staffOpsExceptions(body);
  else if (S.opsTab === "notices") staffNews(undefined, body);
  else if (S.opsTab === "campaigns") staffCargoCampaigns(body);
  else if (S.opsTab === "relief") staffRelief(body);
  else staffEvents(undefined, body);
}
async function loadStaff() {
  try { S.staff = await api("/api/staff/overview"); renderStaff(); } catch (e) { toast(e.message); }
}
function renderStaff() {
  const d = S.staff;
  const pendingReviews = d.reviews.filter(r => r.review_status === "Pending").length;
  const pendingApps = d.applications.filter(a => a.status === "Pending").length;
  const tabs = [["ceo", "CEO desk", 0], ["market", "Fleet market", 0], ["complaints", "Complaints", 0], ["roles", "Roles", 0], ["reports", "Problem reports", 0], ["flightops", "Flight support", 0], ["exceptions", "Exceptions", 0], ["health", "Operations health", 0], ["usage", "Usage", 0], ["campaigns", "Cargo campaigns", 0], ["relief", "Relief missions", 0], ["cargostock", "Cargo stock", 0], ["reviews", "PIREP review", pendingReviews], ["applications", "Applications", pendingApps], ["transfers", "Transfer hours", d.transfer_pending || 0], ["activity", "Activity", d.activity_overdue || 0], ["engagement", "Engagement", d.engagement_pending || 0], ["roster", "Roster", 0], ["support", "Pilot support view", 0],
    ["news", "News", 0], ["mx", "Maintenance", d.airframes.reduce((n, a) => n + (a.open_items || []).length, 0)], ["types", "Fleet types", 0], ["pphotos", "Partner photos", 0], ["airframes", "Airframes", d.airframes.filter(a => ["Maintenance", "Inspection", "A-check due", "Heavy check due", "Heavy check", "Damaged"].includes(a.status)).length], ["events", "Events", 0], ["site", "Site and rules", 0]];
  const GROUPS = [["Company", ["ceo", "market", "complaints", "roles"]], ["Pilots", ["reviews", "applications", "transfers", "activity", "engagement", "roster", "support"]],
    ["Operations", ["flightops", "exceptions", "reports", "health", "usage", "events", "news"]], ["Cargo", ["campaigns", "relief", "cargostock"]], ["Fleet", ["airframes", "mx", "types", "pphotos"]], ["Settings", ["site"]]];
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
  ({ ceo: staffCeo, market: staffMarket, complaints: staffComplaints, roles: staffRoles, reports: staffProblemReports, flightops: staffFlightOps, exceptions: staffOpsExceptions, health: staffOperationsHealth, usage: staffUsage, campaigns: staffCargoCampaigns, relief: staffRelief, cargostock: staffCargoStock, reviews: staffReviews, applications: staffApps, transfers: staffTransfers, activity: staffActivity, engagement: staffEngagement, roster: staffRoster, support: staffPilotSupport, news: staffNews, mx: staffMx, types: staffTypes, pphotos: staffPartnerPhotos, airframes: staffAirframes, events: staffEvents, site: staffSite })[S.staffTab]();
}
async function staffPilotSupport() {
  const host = $("#staffBody");
  const roster = S.staff.roster || [];
  if (!roster.length) { host.innerHTML = '<p class="muted">No pilots in the roster.</p>'; return; }
  const pid = roster.some(p => p.id === S.supportPilot) ? S.supportPilot : roster[0].id;
  S.supportPilot = pid;
  host.innerHTML = `<div class="card" style="padding:18px"><h2 style="margin-top:0">Pilot support view</h2>
    <p class="muted">Read-only preview of the pilot's website access and server-side flight state. It does not sign in as the pilot or change their flight.</p>
    <label for="supportPilot">Pilot</label> <select id="supportPilot">${roster.map(p => `<option value="${esc(p.id)}" ${p.id === pid ? "selected" : ""}>${esc(p.name)} · ${esc(p.id)}</option>`).join("")}</select>
    <div id="supportResult" style="margin-top:18px"><p class="muted">Loading pilot state…</p></div></div>`;
  $("#supportPilot").onchange = e => { S.supportPilot = e.target.value; staffPilotSupport(); };
  try {
    const d = await api(`/api/staff/pilot-support/${encodeURIComponent(pid)}`);
    if (S.staffTab !== "support" || S.supportPilot !== pid || !host.isConnected) return;
    const p = d.pilot, b = d.booking, a = d.acars;
    const all = [["Main", ["Home", "Dashboard", "Missions", "My bids", "ACARS"]],
      ["Operations", ["Fleet", "Live map", "Stations", "Cargo inventory", "Cargo network", "Track a shipment"]],
      ["My career", ["Career", "Logbook", "My stats", "Shop", "Finance"]],
      ["Crew room", ["Crew mail", "Pilots", "Roster & flight log", "Gallery", "What's new"]],
      ["Learn", ["PAC Academy", "Handbook", "Cargo guide", "Downloads", "Report a problem"]]];
    const management = [["Livery library", "liveries"], ["Media", "creative"], ["Commercial", "commercial"],
      ["Fleet & maintenance", "fleet"], ["Ops desk", "operations"], ["Academy desk", "academy"]];
    const item = x => `<span class="tag grey" style="margin:3px">${esc(x)}</span>`;
    const line = (label, value) => `<tr><th style="text-align:left;padding:7px 16px 7px 0">${esc(label)}</th><td>${esc(value ?? "—")}</td></tr>`;
    const phase = a.phase || "No active server tracking";
    const acarsAction = !b ? "No booking: book a flight before starting ACARS." :
      b.release_required && !b.release_signed ? "Start blocked: captain must sign the current dispatch release." :
      a.remote_live ? "Desktop ACARS is reporting live; use that flight session." :
      a.unfiled_draft ? "Completed unfiled draft detected; review and file its PIREP." :
      a.saved_state || a.checkpoint ? "A saved flight state exists; ACARS may offer Resume." :
      "Booking and release permit ACARS start, subject to the pilot's local app connection.";
    $("#supportResult").innerHTML = `<div class="row" style="gap:8px;flex-wrap:wrap;margin-bottom:14px"><b>${esc(p.name)} · ${esc(p.id)}</b><span class="tag ${p.status === "Active" ? "green" : "amber"}">${esc(p.status || "Unknown")}</span>${p.staff ? '<span class="tag dark">Full admin</span>' : ""}</div>
      ${p.can_sign_in ? "" : '<p class="tag amber">This pilot cannot currently sign in; the menu below is their projected access after sign-in is restored.</p>'}
      <div class="row" style="gap:18px;flex-wrap:wrap;align-items:start">
        <section class="card" style="padding:14px;flex:1;min-width:260px"><h3 style="margin-top:0">What appears in their menu</h3>
          ${all.map(([group, items]) => `<p style="margin:10px 0 3px"><b>${esc(group)}</b></p><div>${items.map(item).join("")}</div>`).join("")}
          ${p.staff || d.caps.length ? `<p style="margin:10px 0 3px"><b>Management</b></p><div>${management.filter(([, cap]) => p.staff || d.caps.includes(cap)).map(([name]) => item(name)).join("")}${p.staff ? item("Staff") : ""}</div>` : '<p class="muted">Management menu is hidden for this pilot.</p>'}
        </section>
        <section class="card" style="padding:14px;flex:1;min-width:260px"><h3 style="margin-top:0">Pilot and flight state</h3>
          <table>${line("Home hub", p.hub)}${line("Current station", p.location)}${line("Line checkride", p.checkride)}${line("Roles", d.roles.join(", ") || "None")}${line("Scoped access", d.caps.join(", ") || "None")}${line("Booked flight", b ? `${b.number || "—"} · ${b.origin || "?"} → ${b.destination || "?"}` : "None")}${line("Aircraft", b ? `${b.aircraft || "—"}${b.airframe ? " · " + b.airframe : ""}` : "—")}${line("Dispatch release", b ? (b.release_required ? (b.release_signed ? "Signed" : "Signature needed") : "Signature not required") : "—")}${line("ACARS phase", phase)}${line("Desktop connected", a.remote_live ? "Yes, recent signal" : "No recent signal")}${line("Unfiled draft", a.unfiled_draft ? "Yes" : "No server draft")}${line("Saved flight", a.saved_state ? "Yes" : "No")}${line("Desktop checkpoint", a.checkpoint ? `${a.checkpoint.phase || "Saved"}` : "No")}</table>
        </section></div>
      <div class="card" style="padding:14px;margin-top:14px"><h3 style="margin-top:0">Control checks</h3><p><b>ACARS start or resume:</b> ${esc(acarsAction)}</p><p><b>File PIREP:</b> ${a.unfiled_draft ? "A completed server draft is available." : "No completed server draft is detected."}</p><p class="muted" style="margin-bottom:0">This reflects server records at the time of lookup. A pilot's desktop ACARS cache, browser cache, and device connection can differ. Ask them to refresh their page when comparing a missing control.</p></div>`;
  } catch (e) { if (S.staffTab === "support" && S.supportPilot === pid && host.isConnected) $("#supportResult").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}
async function staffOpsExceptions(root) {
  const host = root || $("#staffBody");
  host.innerHTML = '<p class="muted">Checking diverted freight and grounded aircraft…</p>';
  let data;
  try { data = await api('/api/staff/ops-exceptions'); }
  catch (err) { host.innerHTML = `<div class="notice err">${esc(err.message)}</div>`; return; }
  if (!host.isConnected) return;
  const when = t => t ? new Date(t * 1000).toLocaleString() : '—';
  const pilotOptions = `<option value="">Choose a pilot…</option>${data.pilots.map(p => `<option value="${esc(p.id)}">${esc(p.name)} · ${esc(p.id)}</option>`).join('')}`;
  host.innerHTML = `<h2>Ops exception desk</h2><div class="notice"><b>OCC handoff:</b> Review the flight and affected freight, coordinate the aircraft restriction with Fleet, then record a hold, onward or recovery decision with a specific pilot instruction. For AOG aircraft, the write-up and recovery mission are created automatically; Fleet owns inspection and clearance. Your decision sends Crew Mail but does not move cargo or release the aircraft. Confirm actual delivery through the accepted PIREP and shipment records.</div>
    ${data.cases.length ? data.cases.map(c => {
      const options = data.bookings.filter(b => b.origin === c.station && b.flight).map(b => `<option value="${esc(b.pilot_id)}|${esc(b.flight)}">${esc(b.flight)} · ${esc(b.origin)} → ${esc(b.destination)} · ${esc(b.pilot_id)}</option>`).join('');
      return `<section class="card" style="padding:16px;margin:14px 0" data-exception="${esc(c.key)}">
        <div class="row" style="gap:8px;flex-wrap:wrap;align-items:center"><span class="tag ${c.kind === 'aog' ? 'amber' : 'dark'}">${c.kind === 'aog' ? 'AOG' : 'DIVERTED'}</span><h3 style="margin:0">${esc(c.flight || c.airframe || c.key)} · ${esc(c.station)}</h3><span class="muted">${when(c.opened)}</span></div>
        <p>${c.kind === 'aog' ? `${esc(c.airframe)} · ${esc(c.title || 'Aircraft grounded')}${c.mission_id ? ` · Recovery mission ${esc(c.mission_id)}` : ''}<br>Landing: ${c.landing_rate == null ? 'rate not recorded' : `${fmt(c.landing_rate)} fpm`} · ${c.landing_g == null ? 'G not recorded' : `${Number(c.landing_g).toFixed(2)} G`} · PIREP ${esc(c.review_status || 'unknown')}` : `${c.shipments.length} held shipment${c.shipments.length === 1 ? '' : 's'} awaiting an onward leg`}</p>
        ${c.shipments.length ? `<div class="table-wrap"><table class="staff-table"><thead><tr><th>Air waybill</th><th>Freight</th><th>Destination</th><th>Weight</th><th>Due</th></tr></thead><tbody>${c.shipments.map(s => `<tr><td><b>${esc(s.awb)}</b></td><td>${esc(s.commodity)} · ${esc(s.pieces)} pcs</td><td>${esc(s.destination)}</td><td>${Math.round(s.weight_lbs || 0).toLocaleString()} lb</td><td>${when(s.deadline)}</td></tr>`).join('')}</tbody></table></div>` : ''}
        ${c.decision ? `<p class="muted">Latest OCC decision: <b>${esc(c.decision.choice)}</b> by ${esc(c.decision.actor)} · ${when(c.decision.at)}${c.decision.target_flight ? ` · ${esc(c.decision.target_flight)}` : ''}<br>${esc(c.decision.note)}</p>` : '<p class="muted">No OCC decision recorded yet.</p>'}
        <form class="ops-exception-form" style="display:grid;gap:8px;max-width:760px">
          <label>Decision <select name="choice"><option value="hold">Hold at station</option>${c.kind === 'diversion' ? '<option value="onward">Plan on a booked PAC flight</option>' : ''}${c.kind === 'diversion' || c.status === 'awaiting_parts' ? '<option value="recovery">Request recovery flight</option>' : ''}</select></label>
          <label data-recovery-pilot>Receiving pilot (for recovery) <select name="target_pilot">${pilotOptions}</select></label>
          ${c.kind === 'diversion' ? `<label data-onward-flight>Onward booking (for onward carriage) <select name="target_flight"><option value="">Choose an unsigned flight from ${esc(c.station)}…</option>${options}</select></label>` : ''}
          <label>OCC instruction / reason <textarea name="note" required minlength="10" maxlength="500" rows="2" placeholder="What should the pilot do next?"></textarea></label>
          <button class="btn" type="submit">Record decision &amp; send instruction</button>
        </form></section>`;
    }).join('') : '<div class="notice">No diverted freight or active AOG cases need a decision.</div>'}
    <h3>Recent decisions</h3>${data.recent.length ? `<ul>${data.recent.map(a => `<li>${when(a.at)} · ${esc(a.actor)} · ${esc(a.case_key)} · ${esc(a.choice)}${a.target_pilot ? ` → ${esc(a.target_pilot)}` : ''}: ${esc(a.note)}</li>`).join('')}</ul>` : '<p class="muted">None yet.</p>'}`;
  host.querySelectorAll('.ops-exception-form').forEach(form => {
    const update = () => {
      const choice = form.elements.choice.value;
      form.querySelector('[data-recovery-pilot]').hidden = choice !== 'recovery';
      const onward = form.querySelector('[data-onward-flight]');
      if (onward) onward.hidden = choice !== 'onward';
    };
    form.elements.choice.onchange = update; update();
    form.onsubmit = async e => {
    e.preventDefault();
    const key = form.closest('[data-exception]').dataset.exception;
    const values = new FormData(form), choice = values.get('choice');
    const [bookPilot, bookFlight] = String(values.get('target_flight') || '').split('|');
    const target_pilot = choice === 'onward' ? bookPilot : choice === 'recovery' ? values.get('target_pilot') : '';
    const target_flight = choice === 'onward' ? bookFlight : '';
    const button = form.querySelector('[type=submit]'); button.disabled = true;
    try {
      const result = await api(`/api/staff/ops-exceptions/${encodeURIComponent(key)}/decision`, { method: 'POST',
        body: { choice, target_pilot, target_flight, note: values.get('note') } });
      toast(result.sent ? 'OCC decision recorded and dispatch instruction sent.' : 'OCC decision recorded. No pilot is linked to this case.'); staffOpsExceptions(host);
    } catch (err) { toast(err.message); button.disabled = false; }
    };
  });
}

async function staffFlightOps() {
  const host = $("#staffBody");
  host.innerHTML = '<p class="muted">Loading flight support…</p>';
  let d;
  try { d = await api('/api/staff/flight-ops'); }
  catch (err) { host.innerHTML = `<div class="notice err">${esc(err.message)}</div>`; return; }
  const pilots = (S.staff?.roster || []).map(p => `<option value="${esc(p.id)}">${esc(p.name)} · ${esc(p.id)}</option>`).join('');
  const when = t => t ? new Date(t * 1000).toLocaleString() : '—';
  host.innerHTML = `<h2>Flight intervention desk</h2><p class="muted">Inspect a pilot's booking and saved ACARS state. Ask the pilot to stop their desktop ACARS first. Clearing a draft keeps the booking; releasing it returns the aircraft and cargo to the board. Neither action files a PIREP.</p>
    ${d.flights.length ? `<div class="table-wrap"><table class="staff-table"><thead><tr><th>Pilot / flight</th><th>Booking</th><th>ACARS state</th><th>Action</th></tr></thead><tbody>${d.flights.map(f => `<tr><td><b>${esc(f.pilot)}</b><br><small>${esc(f.pilot_id)} · ${esc(f.flight || '—')}</small></td><td>${esc(f.dep || '—')} → ${esc(f.arr || '—')}<br><small>${esc(f.airframe || f.aircraft || '—')} · ${when(f.booked_at)}</small></td><td>${f.draft ? '<span class="tag amber">Unfiled draft</span> ' : ''}${f.remote ? '<span class="tag green">ACARS connected</span> ' : ''}${f.saved_state ? '<span class="tag">Saved state</span> ' : ''}${f.checkpoint ? `<span class="tag">Checkpoint ${esc(f.checkpoint.phase || 'saved')} · ${when(f.checkpoint.saved_at)}</span> ` : ''}${esc(f.phase || '')}</td><td><div class="row" style="flex-wrap:wrap;gap:5px"><button class="btn ghost small" data-intervene="clear_draft" data-pilot="${esc(f.pilot_id)}" data-key="${esc(f.booking_key)}">Clear draft</button><button class="btn ghost small danger" data-intervene="release_booking" data-pilot="${esc(f.pilot_id)}" data-key="${esc(f.booking_key)}">Release booking</button></div></td></tr>`).join('')}</tbody></table></div>` : '<p class="muted">No active bookings.</p>'}
    <h3>Simulator and operations incidents</h3><p class="muted">Record the issue and evidence. A goodwill payment is a wallet adjustment; it does not add flight hours, deliver cargo, or move an aircraft.</p>
    <form id="flightIncidentForm" class="panel" style="padding:14px;display:grid;gap:8px;max-width:720px">
      <label>Pilot <select name="pilot_id" required>${pilots}</select></label>
      <label>Type <select name="kind"><option value="simulator_crash">Simulator crash</option><option value="acars_error">ACARS error</option><option value="dispatch_error">Dispatch error</option><option value="other">Other</option></select></label>
      <label>Flight number (optional) <input name="flight" maxlength="20" placeholder="PAC1234"></label>
      <label>What happened? <textarea name="summary" required minlength="10" maxlength="500" rows="2"></textarea></label>
      <label>Evidence or links (optional) <textarea name="evidence_note" maxlength="2000" rows="2"></textarea></label>
      <label>Screenshot (optional, PNG/JPEG up to 2 MB) <input name="screenshot" type="file" accept="image/png,image/jpeg,image/webp"></label>
      <button class="btn" type="submit">Open incident</button></form>
    ${d.incidents.length ? `<div class="table-wrap" style="margin-top:14px"><table class="staff-table"><thead><tr><th>Case</th><th>Issue</th><th>Resolution</th><th>Action</th></tr></thead><tbody>${d.incidents.map(i => `<tr><td><b>#${i.id}</b> · ${esc(i.status)}<br><small>${esc(i.pilot || i.pilot_id)} · ${esc(i.flight || '—')}<br>${when(i.created_at)}</small></td><td><b>${esc(i.kind.replaceAll('_', ' '))}</b><br>${esc(i.summary)}${i.evidence_note ? `<br><small>${esc(i.evidence_note)}</small>` : ''}${i.evidence_mime ? `<br><a href="/api/staff/flight-incidents/${i.id}/evidence" target="_blank" rel="noopener">View screenshot</a>` : ''}</td><td>${i.goodwill_amount ? `${money(i.goodwill_amount)} goodwill<br><small>${esc(i.goodwill_note || '')}</small>` : 'No goodwill paid'}${i.resolution ? `<br>${esc(i.resolution)}` : ''}</td><td>${i.status === 'Open' ? `<div class="row" style="gap:5px;flex-wrap:wrap">${i.goodwill_at ? '' : `<button class="btn ghost small" data-goodwill="${i.id}">Award goodwill</button>`}<button class="btn ghost small" data-close-incident="${i.id}">Close case</button></div>` : ''}</td></tr>`).join('')}</tbody></table></div>` : '<p class="muted">No incidents recorded.</p>'}
    <h3>Recent interventions</h3>${d.actions.length ? `<ul>${d.actions.map(a => `<li>${when(a.at)} · ${esc(a.actor)} ${esc(a.action.replaceAll('_', ' '))} for ${esc(a.pilot_id)} (${esc(a.flight || '—')}): ${esc(a.reason)}</li>`).join('')}</ul>` : '<p class="muted">None yet.</p>'}`;
  host.querySelectorAll('[data-intervene]').forEach(btn => btn.onclick = async () => {
    const action = btn.dataset.intervene;
    const reason = prompt(`Reason for ${action === 'clear_draft' ? 'clearing this draft' : 'releasing this booking'}?`, 'Simulator crash; pilot cannot complete flight');
    if (!reason) return;
    if (!confirm(`${action === 'clear_draft' ? 'Clear the saved draft and keep the booking' : 'Release the booking, aircraft and cargo'} for ${btn.dataset.pilot}?`)) return;
    try { await api(`/api/staff/flight-ops/${encodeURIComponent(btn.dataset.pilot)}/intervene`, { method: 'POST', body: { action, reason, booking_key: Number(btn.dataset.key) } }); toast('Intervention recorded. Ask the pilot to reopen ACARS.'); loadStaff(); }
    catch (err) { toast(err.message); }
  });
  host.querySelector('#flightIncidentForm').onsubmit = async e => {
    e.preventDefault(); const form = e.currentTarget, button = form.querySelector('[type=submit]'); button.disabled = true;
    try { const body = Object.fromEntries(new FormData(form)); const file = form.querySelector('[name=screenshot]').files[0];
      if (file) { if (file.size > 2*1024*1024) throw Error('Screenshot must be under 2 MB.'); body.screenshot = await new Promise((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(r.result); r.onerror = reject; r.readAsDataURL(file); }); }
      else delete body.screenshot;
      await api('/api/staff/flight-incidents', { method: 'POST', body }); toast('Incident opened.'); staffFlightOps();
    } catch (err) { toast(err.message); button.disabled = false; }
  };
  host.querySelectorAll('[data-goodwill]').forEach(btn => btn.onclick = async () => {
    const amount = Number(prompt('Goodwill payment in PAC dollars (maximum $5,000):', ''));
    if (!amount) return;
    const note = prompt('Why is this payment being awarded?', 'Simulator crash goodwill payment');
    if (!note || !confirm(`Pay ${money(amount)} goodwill for incident #${btn.dataset.goodwill}? This updates the pilot wallet.`)) return;
    try { await api(`/api/staff/flight-incidents/${btn.dataset.goodwill}/goodwill`, { method: 'POST', body: { amount, note } }); toast('Goodwill payment recorded.'); loadStaff(); loadMe(); }
    catch (err) { toast(err.message); }
  });
  host.querySelectorAll('[data-close-incident]').forEach(btn => btn.onclick = async () => {
    const resolution = prompt('How was this incident resolved?', 'Draft cleared and pilot informed'); if (!resolution) return;
    try { await api(`/api/staff/flight-incidents/${btn.dataset.closeIncident}/close`, { method: 'POST', body: { resolution } }); toast('Incident closed.'); staffFlightOps(); }
    catch (err) { toast(err.message); }
  });
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
        <button class="btn ghost small" type="button" data-ratings="${p.id}" title="Grant or remove type ratings">Ratings</button>
        <button class="btn ghost small" type="button" data-support="${p.id}" title="Inspect this pilot's access and flight state">Support view</button></td></tr>`).join("")}</tbody></table></div>
    <p class="muted" style="font-size:13px">Transfer hours count towards rank, not towards PAC totals or leaderboards. Pilots normally request them under Career (reviewed in the Transfer hours tab); editing them here is for corrections. Tick <b>PRA</b> for pilots cleared to fly the Kodiak for Pagani Remote Aviation; they show in that division on the group hub. Each pilot signs in with their own pilot ID; <b>Sign-in link</b> makes a one-time link to set or reset a pilot's password.</p>`;
  document.querySelectorAll("[data-signin]").forEach(b => b.onclick = () => showSigninLink(b.dataset.signin));
  document.querySelectorAll("[data-ratings]").forEach(b => b.onclick = () => staffRatings(b.dataset.ratings));
  document.querySelectorAll("[data-support]").forEach(b => b.onclick = () => { S.supportPilot = b.dataset.support; S.staffTab = "support"; renderStaff(); });
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
      <p class="muted full" style="margin:0;font-size:13px">News appears on the home page. Company NOTAMs also show as a banner on the home page and mission board, and are sent to pilots as ACARS messages when they start tracking, so keep them short: one rule or warning each. Use News for longer announcements. An OCC decision in Exceptions only sends Crew Mail to the affected pilot; publish a separate post here for a company-wide update. Discord posting uses the selected channel only when the box is checked and the bot is available.</p>
      <div class="full row"><button class="btn" type="submit">${n ? "Save" : "Post"}</button>${n ? `<button class="btn ghost" type="button" id="nwCancel">Cancel</button>` : ""}</div></form>
    <div class="table-wrap"><table class="staff-table"><thead><tr><th>Posted</th><th>Type</th><th>Title</th><th>Until</th><th></th></tr></thead><tbody>
    ${list.map(x => `<tr><td>${new Date(x.time * 1000).toISOString().substr(0, 10)}</td><td>${x.kind === "notam" ? '<span class="tag amber" style="margin:0">NOTAM</span>' : '<span class="tag grey" style="margin:0">News</span>'}${x.important ? ' <span class="tag" style="margin:0">Important</span>' : ""}</td>
      <td><b>${esc(x.title)}</b><br><small class="muted">${esc((x.body || "").slice(0, 110))}</small></td><td>${x.expires ? (x.expires < now ? "Expired" : new Date(x.expires * 1000).toISOString().substr(0, 10)) : "–"}</td>
      <td style="white-space:nowrap"><button class="btn small" type="button" data-nedit="${x.id}">Edit</button> <button class="btn ghost small" type="button" data-ndel="${x.id}" aria-label="Delete">×</button></td></tr>`).join("")}</tbody></table></div>`;
  $("#newsForm").onsubmit = async e => {
    e.preventDefault();
    const body2 = Object.fromEntries(new FormData(e.target).entries());
    body2.important = !!e.target.important.checked; body2.discord = !!e.target.discord.checked; if (n) body2.id = n.id;
    try { await api("/api/staff/news", { method: "POST", body: body2 }); toast(n ? "Post updated on the site." : "Posted on the site."); S.news = null; staffNews(undefined, body); } catch (err) { toast(err.message); }
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
  ["mach", "Cruise Mach", "number", ""], ["tailstrike_pitch", "Tail-clearance reference pitch (°)", "number", ""], ["fuel_burn_pph", "Fuel burn (lb/h)", "number", ""],
  ["maint_per_bh", "Maintenance ($/block h)", "number", ""], ["ownership_per_bh", "Ownership ($/block h)", "number", ""],
  ["engines", "Engines", "text", ""], ["crew", "Flight crew", "text", ""], ["main_deck", "Main deck", "text", ""], ["entered_service", "Type in service since", "number", ""],
  ["cargo_volume_ft3", "Cargo volume, main + lower (ft³)", "number", ""], ["volume_source", "Volume source", "text", ""],
  ["description", "Description", "textarea", ""]];
async function staffTypes(editCode, host = $("#staffBody")) {
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
  host.innerHTML = `${form || `<div class="row" style="margin-bottom:14px"><button class="btn" type="button" id="typeNew">Add an aircraft type</button>
      <span class="muted" style="font-size:13px">Retired types can't be booked but stay in logbooks. Types with airframes or logged flights can't be deleted.</span></div>`}
    <div class="table-wrap"><table class="staff-table"><thead><tr><th>Type</th><th>Name</th><th>Sim</th><th>Payload</th><th>Range</th><th>Unlocks at</th><th>Airframes</th><th>Flights</th><th>Status</th><th></th></tr></thead><tbody>
    ${d.types.map(x => `<tr><td><b>${esc(x.code)}</b><br><small class="muted">${esc(x.icao)} · SimBrief ${esc(x.simbrief_type)}${x.simbrief_airframe ? " · custom airframe" : ""}</small></td><td>${esc(x.name)}</td><td>${esc(x.sim || "MSFS")}</td>
      <td>${fmt(x.max_payload_lbs)} lb</td><td>${fmt(x.range_nm)} nm</td><td>${esc(x.unlock_rank_effective)}</td><td>${x.airframes}</td><td>${x.pireps}</td>
      <td>${x.retired ? '<span class="tag grey" style="margin:0">Retired</span>' : '<span class="tag green" style="margin:0">Active</span>'}${x.custom_type ? ' <span class="tag dark">Added</span>' : ""}</td>
      <td style="white-space:nowrap"><button class="btn small" type="button" data-tedit="${x.code}">Edit</button>
        <button class="btn ghost small" type="button" data-tretire="${x.code}" data-r="${x.retired ? 0 : 1}">${x.retired ? "Restore" : "Retire"}</button>
        <button class="btn ghost small" type="button" data-tdel="${x.code}" aria-label="Delete ${esc(x.code)}">×</button></td></tr>`).join("")}</tbody></table></div>`;
  const q = s => host.querySelector(s);
  if (q("#typeNew")) q("#typeNew").onclick = () => staffTypes("__new", host);
  if (q("#typeCancel")) q("#typeCancel").onclick = () => staffTypes(undefined, host);
  host.querySelectorAll("[data-tedit]").forEach(b => b.onclick = () => { staffTypes(b.dataset.tedit, host); scrollTo({ top: 0, behavior: "smooth" }); });
  host.querySelectorAll("[data-tretire]").forEach(b => b.onclick = async () => {
    const retire = b.dataset.r === "1";
    if (retire && !confirm(`Retire the ${b.dataset.tretire}? It can't be booked until you restore it.`)) return;
    try { await api(`/api/staff/fleet-types/${b.dataset.tretire}/retire`, { method: "POST", body: { retired: retire } }); toast(retire ? "Type retired." : "Type restored."); await refreshCore(); staffTypes(undefined, host); } catch (e) { toast(e.message); }
  });
  host.querySelectorAll("[data-tdel]").forEach(b => b.onclick = async () => {
    if (!confirm(`Delete the ${b.dataset.tdel} type completely?`)) return;
    try { await api(`/api/staff/fleet-types/${b.dataset.tdel}`, { method: "DELETE" }); toast("Type deleted."); await refreshCore(); staffTypes(undefined, host); } catch (e) { toast(e.message); }
  });
  const f = q("#typeForm");
  if (f) f.onsubmit = async e => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(f).entries());
    try {
      const r = await api("/api/staff/fleet-types", { method: "POST", body });
      const file = q("#tf_photo")?.files?.[0];
      if (file) { const fd = new FormData(); fd.append("photo", file); await fetch(`/api/fleet/${r.code}/photo`, { method: "POST", body: fd }); }
      toast(r.new ? `${r.code} added. Now add airframes for it in the Airframes tab.` : `${r.code} saved.`);
      const d2 = await api("/api/bootstrap"); S.fleet = d2.fleet; applyCore(d2); staffTypes(undefined, host);
    } catch (err) { toast(err.message); }
  };
}
const AF_STATUS = ["Available", "Maintenance", "Inspection", "A-check due", "Heavy check due", "Heavy check", "Damaged", "Stored"];
async function staffAirframes(host = $("#staffBody")) {
  const types = fleetCodes();
  let frames;
  if (S.staff?.airframes) frames = S.staff.airframes;
  else { try { frames = (await api("/api/staff/airframes")).airframes || []; } catch (e) { host.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; } }
  const setFrames = fr => { frames = fr; if (S.staff) S.staff.airframes = fr; };
  // sortable roster: click a column to sort, click again to reverse
  S.afSort = S.afSort || { key: "reg", dir: "asc" };
  const NUM_SORT = new Set(["hours", "cycles", "check_due_in", "heavy_due_in"]);
  const sdir = S.afSort.dir === "desc" ? -1 : 1;
  const sorted = [...frames].sort((a, b) => {
    const k = S.afSort.key;
    if (NUM_SORT.has(k)) return ((Number(a[k]) || 0) - (Number(b[k]) || 0)) * sdir;
    return String(a[k] || "").localeCompare(String(b[k] || "")) * sdir;
  });
  const arrow = k => S.afSort.key === k ? (S.afSort.dir === "desc" ? " ↓" : " ↑") : "";
  const sh = (k, label) => `<th class="af-sortable" data-afsort="${k}" style="cursor:pointer;user-select:none" title="Sort by ${label.toLowerCase()}">${label}${arrow(k)}</th>`;
  host.innerHTML = `<form class="form-card" id="afAdd"><div class="field"><label for="af_reg">Registration</label><input id="af_reg" name="reg" placeholder="N805PC" required></div>
    <div class="field"><label for="af_type">Type</label><select id="af_type" name="type">${types.map(t => `<option value="${t}">${esc(S.fleet[t].name)}</option>`).join("")}</select></div>
    <div class="field"><label for="af_loc">Location (ICAO)</label><input id="af_loc" name="location" value="KCVG" required></div>
    <div class="field" style="align-self:end"><button class="btn" type="submit">Add airframe</button></div></form>
    <div class="table-wrap"><table class="staff-table"><thead><tr>${sh("reg", "Registration")}${sh("type", "Type")}${sh("location", "Location")}${sh("status", "Status")}${sh("hours", "Hours")}${sh("cycles", "Cycles")}${sh("check_due_in", "A-check in")}${sh("heavy_due_in", "C-check in")}${sh("last_flight", "Last flight")}<th></th></tr></thead><tbody>
    ${sorted.map(a => `<tr data-reg="${a.reg}"><td><a href="#" data-af-open="${a.reg}" style="color:var(--ink)"><b style="font-family:var(--mono)">${a.reg}</b></a>${a.name ? `<br><small>“${esc(a.name)}” · named by ${esc(a.named_by_name || a.named_by)} <a href="#" data-af-unname="${a.reg}" style="color:var(--red)">remove</a></small>` : ""}${a.note ? `<br><small class="muted">${esc(a.note)}</small>` : ""}</td>
      <td><select data-f="type" aria-label="Type">${fleetCodes(true).map(t => `<option value="${t}" ${t === a.type ? "selected" : ""}>${esc(S.fleet[t].icao)}${S.fleet[t].retired ? " (retired)" : ""}</option>`).join("")}</select></td>
      <td><input data-f="location" value="${a.location}" aria-label="Location" style="width:80px"></td>
      <td>${a.status === "Booked" ? `<span class="tag dark">Booked</span>` : `<select data-f="status" aria-label="Status">${AF_STATUS.map(o => `<option ${o === a.status ? "selected" : ""}>${o}</option>`).join("")}</select>`}</td>
      <td>${esch(a.hours || 0)}</td><td>${a.cycles || 0}</td><td>${esch(Math.max(0, a.check_due_in))} h</td>
      <td>${(a.heavy_due_in ?? 1) <= 0 ? `<span class="tag amber" style="margin:0">C-check due</span>` : fmt(Math.max(0, a.heavy_due_in)) + " h"}</td><td>${esc(a.last_flight || "–")}</td>
      <td style="white-space:nowrap">${a.status === "Booked" ? "" : `<button class="btn small" data-af-save="${a.reg}">Save</button> <button class="btn ghost small" data-af-rename="${a.reg}" title="Give this airframe a new registration. Its hours, history and write-ups go with it.">Rename</button> <button class="btn ghost small" data-af-check="${a.reg}" title="Sign off an A-check and return to service">Sign off check</button> <button class="btn ghost small" data-af-del="${a.reg}" aria-label="Remove ${a.reg}">×</button>`}</td></tr>`).join("")}</tbody></table></div>`;
  const save = async (reg, extra = {}) => {
    const tr = host.querySelector(`tr[data-reg="${reg}"]`), body = { reg, ...extra };
    tr.querySelectorAll("[data-f]").forEach(el => body[el.dataset.f] = el.value.toUpperCase ? (el.dataset.f === "location" ? el.value.toUpperCase() : el.value) : el.value);
    Object.assign(body, extra);
    try { setFrames(await api("/api/staff/airframes", { method: "POST", body })); toast(`${reg} saved.`); staffAirframes(host); refreshCore(); } catch (e) { toast(e.message); }
  };
  host.querySelectorAll("[data-afsort]").forEach(th => th.onclick = () => {
    const k = th.dataset.afsort;
    if (S.afSort.key === k) S.afSort.dir = S.afSort.dir === "asc" ? "desc" : "asc";
    else S.afSort = { key: k, dir: "asc" };
    staffAirframes(host);
  });
  host.querySelectorAll("[data-af-save]").forEach(b => b.onclick = () => save(b.dataset.afSave));
  host.querySelectorAll("[data-af-unname]").forEach(b => b.onclick = async e => {
    e.preventDefault();
    if (!confirm(`Remove the name from ${b.dataset.afUnname}? The pilot isn't refunded.`)) return;
    try { await api("/api/staff/shop/name", { method: "POST", body: { reg: b.dataset.afUnname } }); toast("Name removed."); staffAirframes(host); } catch (err) { toast(err.message); }
  });
  host.querySelectorAll("[data-af-open]").forEach(a => a.onclick = e => { e.preventDefault(); openAirframe(a.dataset.afOpen); });
  host.querySelectorAll("[data-af-rename]").forEach(b => b.onclick = async () => {
    const from = b.dataset.afRename, to = (prompt(`New registration for ${from}?\nIts hours, cycles, flight history and write-ups move with it.`) || "").trim().toUpperCase();
    if (!to || to === from) return;
    try {
      const r = await api(`/api/staff/airframes/${encodeURIComponent(from)}/rename`, { method: "POST", body: { to } });
      setFrames(r.airframes); const m = r.renamed;
      toast(`${m.from} is now ${m.to}${m.flights ? ` · ${m.flights} flight${m.flights === 1 ? "" : "s"} moved` : ""}${m.write_ups ? ` · ${m.write_ups} write-up${m.write_ups === 1 ? "" : "s"} moved` : ""}.`);
      staffAirframes(host); refreshCore();
    } catch (e) { toast(e.message); }
  });
  host.querySelectorAll("[data-af-check]").forEach(b => b.onclick = () => save(b.dataset.afCheck, { status: "Available", reset_check: true }));
  host.querySelectorAll("[data-af-del]").forEach(b => b.onclick = async () => {
    if (!confirm(`Remove ${b.dataset.afDel} from the fleet?`)) return;
    try { setFrames(await api("/api/staff/airframes/" + b.dataset.afDel, { method: "DELETE" })); staffAirframes(host); refreshCore(); } catch (e) { toast(e.message); }
  });
  host.querySelector("#afAdd").onsubmit = async e => {
    e.preventDefault(); const body = Object.fromEntries(new FormData(e.target).entries()); body.location = body.location.toUpperCase();
    if (frames.some(a => a.reg === body.reg.toUpperCase())) { toast("That registration already exists."); return; }
    try { setFrames(await api("/api/staff/airframes", { method: "POST", body })); toast(`${body.reg.toUpperCase()} added.`); staffAirframes(host); refreshCore(); } catch (err) { toast(err.message); }
  };
}
async function staffEvents(edit, host = $("#staffBody")) {
  let events;
  if (S.staff?.events) events = S.staff.events;
  else { try { events = (await api("/api/staff/events")).events || []; } catch (err) { host.innerHTML = `<div class="notice err">${esc(err.message)}</div>`; return; } }
  const reload = () => { if (S.staff) loadStaff(); else staffEvents(undefined, host); };
  const e = edit || { id: "", name: "", start: "", end: "", multiplier: 1.25, categories: [], regions: [], airports: [], description: "" };
  const checks = (name, list, sel) => list.map(x => `<label style="display:inline-flex;align-items:center;gap:6px;margin:0 14px 8px 0;font-size:14px;white-space:nowrap"><input type="checkbox" name="${name}" value="${esc(x)}" ${sel.includes(x) ? "checked" : ""} style="accent-color:var(--red);flex:none;width:16px;height:16px;min-height:0;margin:0;padding:0">${esc(x)}</label>`).join("");
  host.innerHTML = `<form class="form-card" id="evForm"><input type="hidden" name="id" value="${esc(e.id)}">
      <div class="field half"><label for="ev_name">Event name</label><input id="ev_name" name="name" value="${esc(e.name)}" required></div>
      <div class="field"><label for="ev_start">Start</label><input id="ev_start" type="date" name="start" value="${e.start}" required></div>
      <div class="field"><label for="ev_end">End</label><input id="ev_end" type="date" name="end" value="${e.end}" required></div>
      <div class="field"><label for="ev_mult">Points multiplier</label><input id="ev_mult" type="number" step="0.05" min="1" max="3" name="multiplier" value="${e.multiplier}"></div>
      <div class="field half"><label for="ev_ap">Airports (ICAO, comma separated; empty = any)</label><input id="ev_ap" name="airports" value="${esc(e.airports.join(", "))}"></div>
      <div class="field full"><label>Categories (none ticked = any)</label><div>${checks("categories", CATEGORY_LIST, e.categories)}</div></div>
      <div class="field full"><label>Regions (none ticked = any)</label><div>${checks("regions", REGION_LIST, e.regions)}</div></div>
      <div class="field full"><label for="ev_desc">Description</label><textarea id="ev_desc" name="description" rows="2">${esc(e.description)}</textarea></div>
      <div class="full row"><button class="btn" type="submit">${e.id ? "Save event" : "Add event"}</button>${e.id ? `<button class="btn ghost" type="button" id="evCancel">Cancel</button>` : ""}</div></form>
    ${events.map(ev => `<div class="q-item"><div><b>${esc(ev.name)}</b> <span class="tag dark">×${ev.multiplier}</span>
      <div class="meta">${ev.start} to ${ev.end}${ev.categories.length ? " · " + ev.categories.join(", ") : ""}${ev.regions.length ? " · " + ev.regions.join(", ") : ""}${ev.airports.length ? " · " + ev.airports.join(", ") : ""}</div>
      <p style="margin:4px 0 0">${esc(ev.description)}</p></div>
      <div class="q-actions"><button class="btn ghost small" data-ev-edit="${esc(ev.id)}">Edit</button><button class="btn ghost small" data-ev-del="${esc(ev.id)}">Delete</button></div></div>`).join("")}`;
  host.querySelector("#evForm").onsubmit = async ev => {
    ev.preventDefault(); const f = ev.target, fd = new FormData(f);
    const body = { id: fd.get("id"), name: fd.get("name"), start: fd.get("start"), end: fd.get("end"), multiplier: Number(fd.get("multiplier")),
      categories: fd.getAll("categories"), regions: fd.getAll("regions"), airports: fd.get("airports").split(/[,\s]+/).filter(Boolean), description: fd.get("description") };
    try { await api("/api/staff/events", { method: "POST", body }); toast("Event saved."); reload(); refreshCore(); } catch (err) { toast(err.message); }
  };
  if (host.querySelector("#evCancel")) host.querySelector("#evCancel").onclick = () => staffEvents(undefined, host);
  host.querySelectorAll("[data-ev-edit]").forEach(b => b.onclick = () => staffEvents(events.find(x => x.id === b.dataset.evEdit), host));
  host.querySelectorAll("[data-ev-del]").forEach(b => b.onclick = async () => {
    if (!confirm("Delete this event?")) return;
    await api("/api/staff/events/" + encodeURIComponent(b.dataset.evDel), { method: "DELETE" }); reload(); refreshCore();
  });
}
function staffSite() {
  const r = S.staff.rules, st = S.staff.site;
  $("#staffBody").innerHTML = `<div class="two-col" style="align-items:start">
    <section class="panel" style="padding:4px 20px 12px"><h2 style="padding:14px 0 0">Airline rules</h2>
      <p class="muted" style="font-size:13px;margin:4px 0">Changes to these switches save automatically.</p>
      <label class="switch-row"><input type="checkbox" data-rule="enforce_airframes" ${r.enforce_airframes ? "checked" : ""}><span><b>Airframes must be at the departure airport</b><br><span class="muted" style="font-size:13px">Pilots fly the aircraft that's physically there, or ferry one in first. Off: any available airframe of the type can be used, and it moves to wherever it lands.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="reuse_pilot_ids" ${r.reuse_pilot_ids ? "checked" : ""}><span><b>Reuse pilot IDs <span class="tag amber">Testing</span></b><br><span class="muted" style="font-size:13px">While this is on, a removed pilot's ID is given to the next pilot, so you can test joining over and over. <b>Turn it off before PAC goes live</b>, or a new pilot could inherit an old pilot's ID.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="require_type_ratings" ${r.require_type_ratings ? "checked" : ""}><span><b>Type ratings required</b><br><span class="muted" style="font-size:13px">Pilots need the type rating for an aircraft family before flying it (earned with a short checkride; types already flown count).</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="shop_enabled" ${r.shop_enabled !== false ? "checked" : ""}><span><b>PAC shop open</b><br><span class="muted" style="font-size:13px">Pilots can spend wallet money on patches, frames, jumpseat passes, aircraft repositions and naming rights. Closing it keeps what they've already bought.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="live_map_public" ${r.live_map_public ? "checked" : ""}><span><b>Live map on the public site</b><br><span class="muted" style="font-size:13px">Visitors can watch PAC flights on the live map (flight numbers, aircraft and routes; never pilots' names). Members always see it.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="enforce_pilot_location" ${r.enforce_pilot_location ? "checked" : ""}><span><b>Pilots fly from where they are</b><br><span class="muted" style="font-size:13px">A pilot's location is where their last flight ended. To fly from anywhere else they jumpseat there, paid from their wallet.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="direct_entry_checkrides" ${r.direct_entry_checkrides !== false ? "checked" : ""}><span><b>Direct entry type checkrides</b><br><span class="muted" style="font-size:13px">Experienced pilots can take any type checkride regardless of rank or hours. An accepted passing report unlocks that family for line flights. Rank and pay keep their existing progression rules. Turning this off restores rank-based access.</span></span></label>
      <label class="switch-row"><input type="checkbox" data-rule="volumetric_loading" ${r.volumetric_loading ? "checked" : ""}><span><b>Volumetric loading <span class="tag amber">New</span></b><br><span class="muted" style="font-size:13px">Flights carry only what physically fits in the hold. Light, bulky freight (e-commerce, garments, flowers) fills the aircraft before its weight limit, so those flights load less weight, and PAC's contract price uses chargeable weight so a full hold still pays. Off: loads are planned by weight alone.</span></span></label>
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
    const enabled = el.checked;
    el.disabled = true;
    try {
      const saved = await api("/api/settings", { method: "POST", body: { [el.dataset.rule]: enabled } });
      if (saved[el.dataset.rule] !== enabled) throw new Error("The rule was not saved. Please try again.");
      S.settings = saved;
      S.staff.rules[el.dataset.rule] = enabled;
      toast("Rule saved.");
    } catch (e) {
      el.checked = !enabled;
      toast(e.message);
    } finally {
      el.disabled = false;
    }
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

