/* ---------------- anonymous usage counts (usage.py): which pages are opened, load time, script errors ----------------
   No cookies and nothing stored on the device. Each beacon says only the page, whether the visitor is a guest, a pilot
   or staff, and the kind of screen. Staff read the totals under Staff › Operations › Usage. */
function usageKind() { return S.me ? (S.me.staff ? "staff" : "pilot") : "guest"; }
function usageDevice() { const w = window.innerWidth || 1200; return w < 700 ? "phone" : w < 1100 ? "tablet" : "desktop"; }
function usageSend(body) {
  try {
    const data = JSON.stringify({ kind: usageKind(), device: usageDevice(), ...body });
    if (navigator.sendBeacon) navigator.sendBeacon("/api/usage", data);
    else fetch("/api/usage", { method: "POST", body: data, keepalive: true }).catch(() => {});
  } catch (e) { /* counting must never get in the way of the page */ }
}
var usageLast = "";   // var, not let: show() may run before this line has, and must not trip on it
function usageView(view) {
  if (!view || view === usageLast) return;      // re-rendering the same page isn't another visit to it
  usageLast = view;
  usageSend({ view });
}
var usageErrors = 0;
function usageError(message, place) {
  if (!message || ++usageErrors > 5) return;     // a broken page reports its first few errors, not a flood
  usageSend({ error: { message: String(message).slice(0, 200), place: String(place || "").slice(0, 120) } });
}
// Browser warnings that aren't bugs: "ResizeObserver loop …" only means a layout settled a frame later.
const USAGE_IGNORE = /ResizeObserver loop/i;
window.addEventListener("error", e => {
  if (USAGE_IGNORE.test(e.message || "")) return;
  const file = e.filename || "";
  if (!file.startsWith(location.origin)) return;   // browser extensions and other sites' scripts aren't PAC's errors
  usageError(e.message, file.replace(location.origin, "").replace(/\?.*$/, "") + ":" + (e.lineno || 0));
});
window.addEventListener("unhandledrejection", e => {
  const r = e.reason;
  if (!r || r.status) return;                      // an API answer the page already shows (sign in, not found) isn't a bug
  if (r instanceof Error && !/Failed to fetch|NetworkError|Load failed|aborted/i.test(r.message)) usageError(r.message, ((r.stack || "").match(/\/static\/[^\s)]+:\d+/) || [""])[0].replace(/\?[^:]*/, ""));
});
window.addEventListener("load", () => setTimeout(() => {
  try {
    const nav = performance.getEntriesByType("navigation")[0];
    const ms = nav && (nav.loadEventEnd || nav.domContentLoadedEventEnd);
    if (ms > 0) usageSend({ load_ms: Math.round(ms) });
  } catch (e) { /* older browsers: no timing */ }
}, 0));

/* Staff › Operations › Usage */
const USAGE_NAMES = { home: "Home", dashboard: "Dashboard", missions: "Missions", acars: "ACARS", logbook: "Logbook", stats: "My stats",
  career: "Career", finance: "Finance", shop: "Shop", live: "Live map", network: "Network map", track: "Shipment tracking",
  fleet: "Fleet", pilots: "Pilots", roster: "Roster", stations: "Stations", cargo: "Cargo", downloads: "Downloads",
  handbook: "Handbook", cargoguide: "Cargo guide", gallery: "Gallery", bids: "Bids", messages: "Messages", profile: "Profile",
  staff: "Staff", reports: "Problem reports", updates: "What's new", crewplans: "Crew plans", groupflight: "Group flight",
  privacy: "Privacy policy", piracy: "Piracy", academy: "Academy", liverylib: "Livery library", creative: "Media",
  commercial: "Commercial", fleetmgr: "Fleet manager", operations: "Ops desk" };
const usageName = v => USAGE_NAMES[v] || v;
async function staffUsage() {
  const root = $("#staffBody");
  S.usageDays = S.usageDays || 30;
  root.innerHTML = '<p role="status">Counting…</p>';
  let d;
  try { d = await api(`/api/staff/usage?days=${S.usageDays}`); }
  catch (e) { if (root.isConnected) root.innerHTML = `<div class="notice">Usage couldn't be loaded: ${esc(e.message)}</div>`; return; }
  if (!root.isConnected || S.staffTab !== "usage") return;
  const t = d.totals || {}, pct = (a, b) => b ? Math.round(a * 100 / b) + "%" : "–";
  const tile = (label, value, sub = "") => `<div><span>${label}</span><b>${value}</b>${sub ? `<small>${sub}</small>` : ""}</div>`;
  // the pages the menu offers that nobody opened in this period
  const offered = [...new Set([...document.querySelectorAll("nav [data-view]")].map(b => b.dataset.view))];
  const opened = new Set(d.pages.map(p => p.view));
  const unused = offered.filter(v => !opened.has(v));
  // pages opened per day, guests / pilots / staff stacked
  const days = [];
  for (let i = d.days - 1; i >= 0; i--) { const day = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10); days.push(d.daily.find(x => x.day === day) || { day, guest: 0, pilot: 0, staff: 0, visitors: 0 }); }
  const top = Math.max(1, ...days.map(x => x.guest + x.pilot + x.staff)), W = 720, H = 140, bw = W / days.length;
  const bars = days.map((x, i) => { let y = H; return ["staff", "pilot", "guest"].map(k => { const h = x[k] * H / top; y -= h;
    return h ? `<rect x="${(i * bw + 1).toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(1, bw - 2).toFixed(1)}" height="${h.toFixed(1)}" class="u-${k}"><title>${x.day}: ${x[k]} ${k} page opens</title></rect>` : ""; }).join(""); }).join("");
  // first-load time: share under 2 s and the bucket the middle visitor falls in, per kind of screen
  const labels = ["under 1 s", "1–2 s", "2–3 s", "3–5 s", "5–8 s", "over 8 s"];
  const loadRow = dev => { const b = d.loads[dev]; if (!b) return ""; const n = b.reduce((s, x) => s + x, 0); let acc = 0, mid = 0;
    for (let i = 0; i < b.length; i++) { acc += b[i]; if (acc >= n / 2) { mid = i; break; } }
    return `<tr><td>${dev[0].toUpperCase() + dev.slice(1)}</td><td class="num">${fmt(n)}</td><td>${labels[mid]}</td><td class="num">${pct(b[0] + b[1], n)}</td><td class="num">${pct(b[4] + b[5], n)}</td></tr>`; };
  const when = s => s ? new Date(s * 1000).toLocaleString() : "";
  root.innerHTML = `<div class="ops-heading"><div><h2>Usage</h2><p class="muted">Anonymous counts of which pages get opened, how fast the site loads and which script errors visitors hit. No cookies, no IP addresses, no pilot names: see usage.py.</p></div>
      <div class="row">${[7, 30, 90].map(n => `<button class="btn small ${n === S.usageDays ? "" : "ghost"}" type="button" data-udays="${n}">${n} days</button>`).join("")}</div></div>
    <div class="stat-tiles">${tile("Page opens", fmt(t.opens))}${tile("Visitors a day", fmt(t.avg_visitors), "on average, about")}${tile("By pilots", pct(t.pilot, t.opens), fmt(t.pilot) + " opens")}${tile("By guests", pct(t.guest, t.opens), fmt(t.guest) + " opens")}${tile("By staff", pct(t.staff, t.opens), fmt(t.staff) + " opens")}${tile("On phones", pct(t.phone, t.opens))}</div>
    <h3>Page opens per day</h3>
    <div class="table-wrap" style="padding:10px"><svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" preserveAspectRatio="none" role="img" aria-label="Page opens per day">${bars}</svg>
      <p class="muted u-legend"><span class="u-key u-guest"></span>Guests <span class="u-key u-pilot"></span>Pilots <span class="u-key u-staff"></span>Staff · ${days[0].day} to ${days[days.length - 1].day}</p></div>
    <h3>Pages</h3>
    ${d.pages.length ? `<div class="table-wrap"><table class="ratings"><thead><tr><th>Page</th><th class="num">Opens</th><th class="num">Visitors</th><th class="num">Share</th><th class="num">Pilots</th><th class="num">Guests</th><th class="num">Staff</th><th class="num">On phones</th></tr></thead><tbody>
      ${d.pages.map(p => `<tr><td>${esc(usageName(p.view))} <span class="muted mono">${esc(p.view)}</span></td><td class="num">${fmt(p.opens)}</td><td class="num">${fmt(p.visitors)}</td><td class="num">${pct(p.opens, t.opens)}</td><td class="num">${fmt(p.pilot)}</td><td class="num">${fmt(p.guest)}</td><td class="num">${fmt(p.staff)}</td><td class="num">${pct(p.phone, p.opens)}</td></tr>`).join("")}</tbody></table></div>`
      : `<div class="notice">Nothing counted yet in this period. Counting starts once this version is live; check back in a day or two.</div>`}
    ${d.pages.length && unused.length ? `<p><b>Not opened at all in ${d.days} days:</b> ${unused.map(v => esc(usageName(v))).join(", ")}.</p>` : ""}
    <h3>How fast the site loads</h3>
    ${Object.keys(d.loads).length ? `<div class="table-wrap"><table class="ratings"><thead><tr><th>Screen</th><th class="num">First loads</th><th>Typical</th><th class="num">Under 2 s</th><th class="num">Over 5 s</th></tr></thead><tbody>${["desktop", "tablet", "phone"].map(loadRow).join("")}</tbody></table></div>
      <p class="muted">From opening the address to the page being ready, as the visitor's browser measured it. Later page changes inside the site are quicker.</p>` : `<p class="muted">No load times yet.</p>`}
    <h3>Script errors</h3>
    ${d.errors.length ? `<div class="table-wrap"><table class="ratings"><thead><tr><th>Error</th><th>Where</th><th class="num">Times</th><th>Last seen</th></tr></thead><tbody>${d.errors.map(e => `<tr><td>${esc(e.message)}</td><td class="mono">${esc(e.place || "–")}</td><td class="num">${fmt(e.n)}</td><td>${esc(when(e.last_at))}</td></tr>`).join("")}</tbody></table></div>
      <p class="muted">"Where" names the piece of the site script in static/app/ and the line in it. Send these to whoever is fixing the site.</p>` : `<p class="muted">No script errors reported in this period.</p>`}`;
  root.querySelectorAll("[data-udays]").forEach(b => b.onclick = () => { S.usageDays = Number(b.dataset.udays); staffUsage(); });
}
