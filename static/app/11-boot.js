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
    await restorePlanningDraft();
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
  compactMgmt();
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
