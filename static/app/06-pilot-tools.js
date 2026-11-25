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
  const bar = n => `<div class="notam-bar ${n.important ? "important" : ""}"><b class="k">CO NOTAM</b><span><b>${esc(n.title)}</b>${n.body ? ` · <span style="white-space:pre-line">${esc(n.body)}</span>` : ""}</span></div>`;
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
  applyAuth();   // staff_caps arrive with /api/pilot/me, so re-evaluate cap-gated nav (Livery, Media, Commercial, Fleet)
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

