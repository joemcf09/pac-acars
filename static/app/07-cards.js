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
  // pitch gauge 0..16 deg with a tail-clearance reference (not a contact sensor)
  const cx = 300, cy = 1030, R = 210, max = 16, lim = ta.tail_limit || 12;
  const ang = v => Math.PI + Math.min(Math.max(v, 0), max) / max * Math.PI;
  [[0, lim - 2, "#4BD07F"], [lim - 2, lim, "#FFC845"], [lim, max, "#FF4D4D"]].forEach(([a, b, col]) => { x.beginPath(); x.strokeStyle = col; x.lineWidth = 34; x.arc(cx, cy, R, ang(a) + .01, ang(b) - .01); x.stroke(); });
  x.fillStyle = "rgba(255,255,255,.5)"; x.font = F(600, 22); x.textAlign = "center";
  [0, 4, 8, 12, 16].forEach(v => { const a = ang(v); x.fillText(`${v}°`, cx + Math.cos(a) * (R - 58), cy + Math.sin(a) * (R - 58) + 8); });
  const pv = ta.max_pitch_ground ?? ta.liftoff_pitch;
  if (pv != null) { const a = ang(pv); x.strokeStyle = "#fff"; x.lineWidth = 10; x.lineCap = "round"; x.beginPath(); x.moveTo(cx, cy); x.lineTo(cx + Math.cos(a) * (R - 18), cy + Math.sin(a) * (R - 18)); x.stroke();
    x.fillStyle = "#fff"; x.beginPath(); x.arc(cx, cy, 16, 0, Math.PI * 2); x.fill(); }
  x.fillStyle = "#fff"; x.font = F(800, 92); x.fillText(pv != null ? `${pv}°` : "–", cx, cy + 98);
  const clearanceWarning = ta.tail_clearance_warning === true || ta.tail_strike === true; // older PIREPs used this name for a pitch estimate
  x.fillStyle = clearanceWarning ? "#FFC845" : "#4BD07F"; x.font = F(700, 28);
  x.fillText(clearanceWarning ? "CLEARANCE REVIEW" : ta.tail_margin != null ? `${ta.tail_margin}° BELOW REFERENCE` : "PITCH ON THE GROUND", cx, cy + 142);
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
    <text x="${X(ta.liftoff_ft)}" y="${ry - 16}" fill="#fff" font-size="28" text-anchor="${X(ta.liftoff_ft) > 760 ? "end" : "middle"}" font-family="Saira, sans-serif">Liftoff ${fmt(ta.liftoff_ft)} ft${ta.liftoff_ft > L ? " (past the runway end)" : ""}</text>
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
  const clearanceWarning = ta.tail_clearance_warning === true || ta.tail_strike === true;
  const cells = [
    ["Runway", ta.runway ? `${ta.airport} ${ta.runway}` : "–", ta.runway_length_ft ? `${fmt(ta.runway_length_ft)} ft long` : ""],
    ["Rotate", ta.rotate_ias != null ? `${ta.rotate_ias} kt` : "–", ta.rotation_rate != null ? `${ta.rotation_rate}°/s rotation rate` : ""],
    ["Liftoff", `${ta.liftoff_ias} kt`, ta.liftoff_pitch != null ? `${ta.liftoff_pitch}° pitch` : ""],
    ["Pitch on the ground", ta.max_pitch_ground != null ? `${ta.max_pitch_ground}°` : "–", ta.tail_limit ? (clearanceWarning ? `Above ${ta.tail_limit}° clearance reference; review possible contact` : `${ta.tail_margin}° below the ${ta.tail_limit}° clearance reference`) : ""],
    ["Ground roll", ta.roll_ft != null ? `${fmt(ta.roll_ft)} ft` : "–", ta.remaining_ft != null ? `${fmt(ta.remaining_ft)} ft of runway left` : ""],
    ["Initial climb", ta.climb_fpm != null ? `${fmt(ta.climb_fpm)} fpm` : "–", ta.time_to_1000_s != null ? `1,000 ft after ${ta.time_to_1000_s} s` : ""],
  ];
  return `<div class="landing-wrap"><div class="landing-card"><canvas id="${id}" width="1080" height="1350" aria-label="Takeoff card for ${esc(c.flight)}"></canvas>
      <div class="row"><button class="btn small" type="button" data-dl-card="${id}">Download takeoff card</button></div></div>
    <div><div class="la-facts">${cells.map(([l, v, sub]) => `<div><span>${l}</span><b style="${l === "Pitch on the ground" && clearanceWarning ? "color:#9a6700" : ""}">${esc(v)}</b>${sub ? `<small>${esc(sub)}</small>` : ""}</div>`).join("")}</div>
      ${clearanceWarning ? `<div class="notice" style="margin-top:12px">Recorded pitch crossed the type's estimated tail-clearance reference. ACARS did not measure tail contact. Review the takeoff; this reading alone does not confirm damage.${ta.tail_strike === true && ta.tail_clearance_warning !== true ? " This older PIREP was scored under the previous rule." : ""}</div>` : ""}
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
