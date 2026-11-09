/* Cargo programs share accepted PIREPs with the logbook; no separate flight credit. */
let cargoStatsVersion = 0;
function cargoStatsNav() {
  return `<nav class="cargo-tabs" aria-label="My stats sections">${[['overview','Overview'],['passport','Cargo Passport'],['campaigns','Cargo Campaigns']].map(([id,label]) => `<button type="button" class="${(S.statsTab || 'overview') === id ? 'active' : ''}" data-stats-tab="${id}" aria-current="${(S.statsTab || 'overview') === id ? 'page' : 'false'}">${label}</button>`).join('')}</nav>`;
}
document.addEventListener('click', event => {
  const tab = event.target.closest('[data-stats-tab]');
  const airport = event.target.closest('[data-passport-airport]');
  if (!tab && !airport) return;
  S.statsTab = airport ? 'passport' : tab.dataset.statsTab;
  S.cargoAirport = airport ? airport.dataset.passportAirport : '';
  if ($('#view-stats').hidden) show('stats'); else loadStats();
});
const cargoDate = t => new Date(t * 1000).toLocaleDateString('en-US', {timeZone:'UTC',year:'numeric',month:'short',day:'numeric'});
function cargoCollectionCards(collections) {
  return collections.map(c => `<article class="cargo-collection ${c.earned ? 'earned' : ''}"><div class="kicker">${c.earned ? 'Collection earned' : `${c.stamped.length} / ${c.required.length} stamps`}</div><h3>${esc(c.title)}</h3><p>${esc(c.description)}</p><div class="cargo-airports">${c.required.map(i => `<span class="${c.stamped.includes(i) ? 'stamped' : ''}">${esc(i)} ${c.stamped.includes(i) ? '✓' : '○'}</span>`).join('')}</div>${c.earned ? `<small>Completed ${cargoDate(c.earned_at)} UTC</small>` : '<small>Make an accepted cargo delivery to every station.</small>'}</article>`).join('');
}
function cargoCampaignCards(items, staff = false) {
  return items.map(c => `<article class="cargo-campaign"><div class="cargo-card-top">${c.patch ? `<img class="cargo-patch-img" src="${esc(c.patch)}" alt="${esc(c.title)} patch">` : ''}<div><span class="kicker">${esc(c.phase)}${c.goal_met ? ' · Target reached' : ''}</span><h3>${esc(c.title)}</h3></div>${c.contributor_badge ? '<span class="cargo-badge">PAC contributor ✓</span>' : ''}</div><p>${esc(c.description)}</p><p class="brief-note">${cargoDate(c.starts)} – ${cargoDate(c.ends - 1)} UTC${c.archived_at ? ` · Credit closed ${cargoDate(c.archived_at)} UTC` : ''}</p><div class="cargo-airports">${c.destinations.map(i => `<button type="button" class="btn ghost small" data-station="${esc(i)}">${esc(i)}</button>`).join('')}</div>
    <div class="cargo-progress"><strong>${fmt(c.cargo_lbs)} <small>/ ${fmt(c.target_lbs)} lb</small></strong><span>${c.pct}%</span></div><progress max="100" value="${c.pct}" aria-label="${esc(c.title)} cargo target">${c.pct}%</progress><p>${fmt(c.flights)} ${c.flights === 1 ? 'delivery' : 'deliveries'} · ${fmt(c.pilots)} ${c.pilots === 1 ? 'pilot' : 'pilots'}${staff ? '' : ` · Your contribution: <b>${fmt(c.personal_lbs)} lb</b>`}</p>${c.reward_cash > 0 ? `<p class="brief-note">Reward if the target is reached: the patch and a <b>$${fmt(c.reward_cash)}</b> bonus for every contributor, paid when the campaign closes.</p>` : ''}${c.baseline_lbs > 0 ? `<p class="brief-note">Includes ${fmt(c.baseline_lbs)} lb delivered before tracking moved to the website.</p>` : ''}${(c.top || []).length ? `<p class="brief-note"><b>Top contributors:</b> ${c.top.map(t => `${esc(t.name)} (${fmt(t.cargo_lbs)} lb)`).join(' · ')}</p>` : ''}
    ${staff ? `<div class="row">${c.state === 'draft' ? `<button type="button" class="btn small" data-campaign-action="publish" data-campaign-id="${c.id}">Publish campaign</button><button type="button" class="btn ghost small" data-campaign-action="archive" data-campaign-id="${c.id}">Discard draft</button>` : c.state === 'published' ? `<button type="button" class="btn ghost small" data-campaign-action="archive" data-campaign-id="${c.id}">Archive and stop credit</button>` : ''}</div>${c.state === 'draft' ? `<details class="cargo-create"><summary>Edit draft</summary><form class="cargo-form" data-edit="${c.id}"><label>Campaign title<input name="title" required minlength="3" maxlength="80" value="${esc(c.title)}"></label><label>Description<textarea name="description" maxlength="1000" rows="4">${esc(c.description || '')}</textarea></label><div class="cargo-form-row"><label>Start date (UTC)<input name="start_date" type="date" required value="${new Date(c.starts*1000).toISOString().slice(0,10)}"></label><label>Last day (UTC, inclusive)<input name="end_date" type="date" required value="${new Date(c.ends*1000-86400000).toISOString().slice(0,10)}"></label><label>Target cargo (lb)<input name="target_lbs" type="number" required min="1" max="1000000000" step="1" value="${Number(c.target_lbs) || 0}"></label></div><label>Destination ICAOs<input name="destinations" required value="${esc((c.destinations || []).join(', '))}"></label><button class="btn small" type="submit">Save changes</button></form></details>` : ''}${c.state !== 'archived' ? `<details class="cargo-create"><summary>Patch, reward and starting total</summary><form class="cargo-form" data-extras="${c.id}"><div class="cargo-form-row"><label>Patch image link<input name="patch" value="${esc(c.patch || '')}" placeholder="/static/patches/island-supply.png"></label><label>Cash reward per contributor ($)<input name="reward_cash" type="number" min="0" step="1" value="${Number(c.reward_cash) || 0}"></label><label>Pounds already delivered (before the website tracked it)<input name="baseline_lbs" type="number" min="0" step="1" value="${Number(c.baseline_lbs) || 0}"></label></div><button class="btn small" type="submit">Save</button></form></details>` : ''}${c.state === 'draft' ? '<p class="brief-note">Private draft. Totals preview qualifying history within these dates. Publishing makes it visible to pilots; campaign rules are then fixed.</p>' : ''}` : ''}</article>`).join('');
}
async function loadCargoPanel(version) {
  const root = $('#statsRoot'), pilot = S.me?.id, section = S.statsTab;
  const current = () => version === cargoStatsVersion && S.me?.id === pilot && S.statsTab === section;
  root.innerHTML = `<div class="profile-bar"><h1>My stats</h1><span class="muted">Your cargo journey</span></div>${cargoStatsNav()}<p role="status">Loading ${section === 'passport' ? 'your passport' : 'cargo campaigns'}…</p>`;
  try {
    const data = await api(section === 'passport' ? '/api/pilot/cargo-passport' : '/api/pilot/cargo-campaigns');
    if (!current()) return;
    if (section === 'campaigns') {
      root.innerHTML = `<div class="profile-bar"><h1>My stats</h1></div>${cargoStatsNav()}<div class="cargo-hero"><div><div class="kicker">Move freight together</div><h2>Cargo Campaigns</h2><p>Every qualifying delivery brings the airline closer to a shared goal.</p></div></div><p class="brief-note">Accepted cargo arrivals at the listed destinations count by report filing time in UTC. Pending, failed, demo, checkride, ferry and diverted flights do not count. A flight can support multiple campaigns, but your normal cargo total is never multiplied. Contributors earn the campaign patch when the target is reached, plus any cash reward shown on the campaign.</p>
      ${data.campaigns.length ? `<div class="cargo-campaign-grid">${cargoCampaignCards(data.campaigns)}</div>` : '<div class="notice">No campaigns published yet. Staff can create the first operation in Staff → Cargo campaigns.</div>'}`;
      return;
    }
    const t = data.totals;
    root.innerHTML = `<div class="profile-bar"><h1>My stats</h1></div>${cargoStatsNav()}<div class="cargo-hero"><div><div class="kicker">Pagani Air Cargo · Pilot passport</div><h2>Every delivery leaves a mark.</h2><p>Your accepted cargo history, collected one destination at a time.</p></div><div class="cargo-hero-count"><strong>${t.airports}</strong><span>destination stamps</span></div></div>
      <div class="cargo-summary"><span><b>${t.countries}</b> countries / territories</span><span><b>${fmt(t.deliveries)}</b> deliveries</span><span><b>${fmt(t.cargo_lbs)} lb</b> delivered</span><span><b>${data.collections.filter(c => c.earned).length} / ${data.collections.length}</b> collections earned</span></div>
      <p class="brief-note">Historical flights count automatically. Stamps are for accepted, successful cargo arrivals—not departure visits. Pending, demo, checkride, ferry and diverted flights are excluded, so totals can differ from Overview. Review corrections update stamps and collection awards.</p>
      ${data.unknown_deliveries ? `<p class="notice">${fmt(data.unknown_deliveries)} deliveries have destinations missing from the airport directory and cannot receive a stamp yet.</p>` : ''}
      <div class="section-h"><div><h2>Your delivery map</h2><p>Select a destination for its first delivery and total cargo.</p></div></div><div class="stats-map" id="cargoPassportMap"></div>
      <div class="section-h"><div><h2>Cargo collections</h2><p>Earn recognition for connecting freight gateways. These awards also appear on Career.</p></div></div><div class="cargo-collection-grid">${cargoCollectionCards(data.collections)}</div>
      <div class="section-h"><div><h2>Passport stamps</h2><p>One stamp per destination, with all qualifying deliveries combined.</p></div><label class="cargo-search">Find a stamp<input type="search" id="cargoStampSearch" placeholder="ICAO, city or country code" value="${esc(S.cargoAirport || '')}"></label></div><div id="cargoStamps"></div>`;
    let visible = 24;
    const draw = () => {
      const q = $('#cargoStampSearch').value.trim().toLowerCase();
      const stamps = data.stamps.filter(s => `${s.icao} ${s.city} ${s.name} ${s.country}`.toLowerCase().includes(q));
      $('#cargoStamps').innerHTML = `<p class="brief-note">${Math.min(visible,stamps.length)} of ${stamps.length} matching stamps</p><div class="cargo-stamp-grid">${stamps.slice(0,visible).map(s => `<article class="cargo-stamp"><div class="cargo-stamp-top"><span>PAC · CARGO DELIVERED</span><b>${esc(s.country)}</b></div><h3>${esc(s.icao)}</h3><p>${esc(s.city || s.name)}</p><span class="cargo-stamp-date">${cargoDate(s.first)} UTC</span><p>${fmt(s.deliveries)} ${s.deliveries === 1 ? 'delivery' : 'deliveries'} · ${fmt(s.cargo_lbs)} lb</p><button type="button" class="btn ghost small" data-cargo-pirep="${s.first_pirep}">First delivery report →</button></article>`).join('')}</div>${!stamps.length ? '<p class="notice">No matching stamps yet. Your next accepted cargo delivery could be your first.</p>' : ''}${visible < stamps.length ? '<button class="btn ghost" type="button" id="moreCargoStamps">Show more stamps</button>' : ''}`;
      root.querySelectorAll('[data-cargo-pirep]').forEach(b => b.onclick = () => openDetail(Number(b.dataset.cargoPirep)));
      if ($('#moreCargoStamps')) $('#moreCargoStamps').onclick = () => {visible += 24; draw();};
    };
    $('#cargoStampSearch').oninput = () => {visible=24;draw();}; draw();
    if (HAS_MAP) {
      const map = S.cargoMap = makeBaseMap($('#cargoPassportMap'), {theme:document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'}).map;
      const points = data.stamps.filter(s => Number.isFinite(s.lat) && Number.isFinite(s.lon));
      points.forEach(s => L.circleMarker([s.lat,s.lon],{radius:7,color:'#fff',weight:2,fillColor:'#C80000',fillOpacity:.9}).addTo(map).bindPopup(`<b>${esc(s.icao)} · ${esc(s.city || s.name)}</b><br>First delivery ${cargoDate(s.first)} UTC<br>${fmt(s.deliveries)} ${s.deliveries === 1 ? 'delivery' : 'deliveries'} · ${fmt(s.cargo_lbs)} lb`).on('click',()=>{$('#cargoStampSearch').value=s.icao;visible=24;draw();}));
      if(points.length)map.fitBounds(points.map(s=>[s.lat,s.lon]),{padding:[30,30],maxZoom:6});else map.setView([30,-40],2);
    } else $('#cargoPassportMap').innerHTML='<p class="muted" style="padding:20px">Map unavailable. Your stamps and collections are listed below.</p>';
  } catch(e) {
    if(current()) {root.innerHTML=`<div class="profile-bar"><h1>My stats</h1></div>${cargoStatsNav()}<p role="alert">${esc(e.message)}</p><button class="btn ghost" type="button" id="cargoRetry">Try again</button>`;$('#cargoRetry').onclick=loadStats;}
  }
}
async function fillCargoAwards() {
  const root=$('#cargoCareerAwards'),pilot=S.me?.id;
  if(!root)return;
  try {
    const p=await api('/api/pilot/cargo-passport');
    if(!root.isConnected || S.me?.id!==pilot)return;
    root.innerHTML=`<div class="section-h"><div><h2>Cargo Passport awards</h2><p>${p.collections.filter(c=>c.earned).length} of ${p.collections.length} collections earned from accepted cargo deliveries.</p></div><button class="btn ghost small" data-stats-tab="passport">Open passport</button></div><div class="cargo-collection-grid">${cargoCollectionCards(p.collections)}</div>`;
  } catch(e){if(root.isConnected)root.innerHTML='<p class="muted">Cargo Passport awards are temporarily unavailable.</p>';}
}
async function staffCargoCampaigns() {
  const root=$('#staffBody'),pilot=S.me?.id;
  const current=()=>root.isConnected && S.staffTab==='campaigns' && S.me?.id===pilot && S.me?.staff;
  root.innerHTML='<p role="status">Loading cargo campaigns…</p>';
  try {
    const data=await api('/api/staff/cargo-campaigns');if(!current())return;
    const today=new Date().toISOString().slice(0,10);
    root.innerHTML=`<div id="shipmentEditor"></div><h2>Cargo campaigns</h2><p>Create a private draft, review its dates and destinations, then publish it for pilots.</p><details class="cargo-create"><summary>Create a campaign</summary><form id="cargoCampaignForm" class="cargo-form">
      <label>Campaign title<input name="title" required minlength="3" maxlength="80" placeholder="Operation Caribbean Supply"></label><label>Description<textarea name="description" maxlength="1000" rows="3" placeholder="Tell pilots what this cargo operation is about."></textarea></label>
      <div class="cargo-form-row"><label>Start date (UTC)<input name="start_date" type="date" required value="${today}"></label><label>Last day (UTC, inclusive)<input name="end_date" type="date" required value="${today}"></label><label>Target cargo (lb)<input name="target_lbs" type="number" required min="1" max="1000000000" step="1" value="500000"></label></div>
      <label>Destination ICAOs<input name="destinations" required placeholder="MYNN, TJSJ, TNCM"></label><p class="brief-note">Separate up to 40 known airports with commas or spaces. All qualifying cargo arrivals at these airports count during the date window, based on report filing time. Earlier dates include historical flights. You can edit a draft until you publish it; publishing fixes the rules. A cash reward and patch image can be added after saving.</p><button class="btn" type="submit">Save private draft</button><p id="cargoFormStatus" role="status"></p></form></details>
      <div class="cargo-campaign-grid">${cargoCampaignCards(data.campaigns,true)}</div>${data.campaigns.length ? '' : '<p class="notice">No campaigns yet. Your first draft will appear here.</p>'}`;
    loadShipmentEditor();
    $('#cargoCampaignForm').onsubmit=async e=>{
      e.preventDefault();const form=e.currentTarget,fields=form.elements,button=form.querySelector('button');button.disabled=true;
      const body={title:fields.title.value,description:fields.description.value,start_date:fields.start_date.value,end_date:fields.end_date.value,target_lbs:Number(fields.target_lbs.value),destinations:fields.destinations.value.split(/[\s,]+/).filter(Boolean)};
      try{await api('/api/staff/cargo-campaigns',{method:'POST',body});if(current()){toast('Private draft saved. Review it before publishing.');staffCargoCampaigns();}}
      catch(err){if(current()){$('#cargoFormStatus').textContent=err.message;button.disabled=false;}}
    };
    root.querySelectorAll('[data-edit]').forEach(f=>f.onsubmit=async e=>{
      e.preventDefault();const x=f.elements;
      const body={action:'edit',title:x.title.value,description:x.description.value,start_date:x.start_date.value,end_date:x.end_date.value,target_lbs:Number(x.target_lbs.value),destinations:x.destinations.value.split(/[\s,]+/).filter(Boolean)};
      try{await api(`/api/staff/cargo-campaigns/${f.dataset.edit}`,{method:'POST',body});toast('Draft updated.');if(current())staffCargoCampaigns();}
      catch(err){toast(err.message);}
    });
    root.querySelectorAll('[data-extras]').forEach(f=>f.onsubmit=async e=>{
      e.preventDefault();const x=f.elements;
      try{await api(`/api/staff/cargo-campaigns/${f.dataset.extras}`,{method:'POST',body:{action:'extras',patch:x.patch.value,reward_cash:Number(x.reward_cash.value),baseline_lbs:Number(x.baseline_lbs.value)}});toast('Saved.');if(current())staffCargoCampaigns();}
      catch(err){toast(err.message);}
    });
    root.querySelectorAll('[data-campaign-action]').forEach(b=>b.onclick=async()=>{
      b.disabled=true;
      try{await api(`/api/staff/cargo-campaigns/${b.dataset.campaignId}`,{method:'POST',body:{action:b.dataset.campaignAction}});if(current())staffCargoCampaigns();}
      catch(e){if(current()){toast(e.message);b.disabled=false;}}
    });
  }catch(e){if(current())root.innerHTML=`<p role="alert">${esc(e.message)}</p>`;}
}

