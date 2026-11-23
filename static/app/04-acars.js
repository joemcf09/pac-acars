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
        <a class="btn ghost" id="sopBtn" href="/static/sop/PAC-SOP.pdf" target="_blank" rel="noopener" title="PAC standard operating procedures (PDF)">📘 SOP procedures</a>
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
// Illustrations come in 640, 1024 and 1600 px widths: the browser picks the smallest that's sharp at the size shown.
function illSrc(name, sizes, v = "") {
  const q = v ? `?v=${v}` : "";
  return `src="/static/illustrations/${name}.webp${q}" srcset="/static/illustrations/640/${name}.webp${q} 640w, /static/illustrations/1024/${name}.webp${q} 1024w, /static/illustrations/${name}.webp${q} 1600w" sizes="${sizes}"`;
}
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
      <div class="map-ctl-row"><select id="trafficSel" aria-label="Live traffic"><option value="">No traffic</option><option value="PAC">PAC company traffic</option><option value="VATSIM">VATSIM traffic</option><option value="IVAO">IVAO traffic</option></select>
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
    const r = net === "PAC" ? await api("/api/live") : await api(`/api/traffic?net=${net}&bbox=${bbox}`);
    if (localStorage.getItem("pac-traffic") !== net || !S.layers?.traffic) return;
    S.layers.traffic.clearLayers();
    const planes = net === "PAC"
      ? (r.flights || []).filter(p => p.lat != null && p.lon != null && b.contains([p.lat, p.lon]))
          .map(p => ({ cs: p.flight, type: p.aircraft, lat: p.lat, lon: p.lon, hdg: p.hdg, alt: p.alt_ft, gs: p.gs, dep: p.dep, arr: p.arr, pilot: p.pilot }))
      : (r.planes || []);
    let shown = 0;
    planes.forEach(p => {
      if (S.booking && p.cs && p.cs.replace(/\s/g, "") === (S.booking.flight_number || "").replace(/\s/g, "")) return;  // own aircraft
      shown++;
      L.marker([p.lat, p.lon], { icon: trafficIcon(p.hdg), keyboard: false })
        .bindTooltip(`<b>${esc(p.cs || "")}</b> ${esc(p.type || "")}${net === "PAC" && p.pilot ? `<br>${esc(p.pilot)}` : ""}<br>${p.alt != null ? (p.alt >= 18000 ? "FL" + Math.round(p.alt / 100) : fmt(p.alt) + " ft") : ""}${p.gs != null ? ` · ${p.gs} kt` : ""}${p.dep || p.arr ? `<br>${esc(p.dep || "?")} → ${esc(p.arr || "?")}` : ""}`, { direction: "top", offset: [0, -8] })
        .addTo(S.layers.traffic);
    });
    liveNote(net === "PAC" ? `${shown} PAC pilot${shown === 1 ? "" : "s"} nearby` : `${r.count} on ${net}`);
  } catch (e) {
    if (localStorage.getItem("pac-traffic") !== net) return;
    S.layers.traffic.clearLayers(); liveNote(`${net} unavailable`);
  }
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
    offerCargoHandoff(r.handoffs || []);
  } catch (e) { toast(e.message); }
}

function offerCargoHandoff(handoffs, preview = false) {
  if (!handoffs.length) return;
  let dlg = $("#cargoHandoffDialog");
  if (!dlg) { dlg = document.createElement("dialog"); dlg.id = "cargoHandoffDialog"; dlg.className = "journey-dialog"; document.body.append(dlg); }
  dlg.innerHTML = `<div class="journey-dialog-head"><h2>Cargo handoff at ${esc(handoffs[0].current_station)}</h2><button type="button" class="btn ghost small" data-close>Close</button></div>
    <div class="journey-dialog-body">${preview ? `<p class="notice">Preview only. This sample does not create a shipment, flight, or note.</p>` : ""}<p>The freight below is waiting for another leg. A note is optional; the next pilot will see it on the load sheet.</p>
      <form id="cargoHandoffForm"><div class="field"><label for="cargoHandoffShipment">Shipment</label><select id="cargoHandoffShipment">${handoffs.map(x => `<option value="${esc(x.id)}">${esc(x.awb)} · ${esc(x.commodity)} · onward to ${esc(x.destination)}</option>`).join("")}</select></div>
      <div class="field"><label for="cargoHandoffText">Note for the next pilot (optional)</label><textarea id="cargoHandoffText" maxlength="280" rows="3" placeholder="Only if there is something the next crew should know."></textarea></div>
      <p id="cargoHandoffStatus" role="status"></p><div class="row"><button class="btn" type="submit">${preview ? "Preview note" : "Save handoff note"}</button><button class="btn ghost" type="button" data-close>No issues to report</button></div></form></div>`;
  dlg.querySelectorAll("[data-close]").forEach(b => b.onclick = () => dlg.close());
  dlg.querySelector("#cargoHandoffForm").onsubmit = async e => {
    e.preventDefault();
    const text = dlg.querySelector("#cargoHandoffText").value.trim();
    if (!text) { dlg.close(); return; }
    const id = dlg.querySelector("#cargoHandoffShipment").value;
    const status = dlg.querySelector("#cargoHandoffStatus");
    if (preview) { status.textContent = "Preview complete. No note was saved."; return; }
    try { await api(`/api/cargo/shipments/${encodeURIComponent(id)}/notes`, { method: "POST", body: { text } }); dlg.close(); toast("Handoff note saved for the next pilot."); }
    catch (err) { status.textContent = err.message; }
  };
  dlg.showModal();
}

