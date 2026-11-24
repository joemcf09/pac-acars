let briefingVersion = 0;
async function loadPilotBriefing() {
  const version = ++briefingVersion, pilotId = S.me?.id;
  const root = $('#pilotBriefing');
  if (!root || !S.me) return;
  root.innerHTML = '<p class="muted" role="status">Loading your flight briefing…</p>';
  try {
    const d = await api('/api/pilot/dashboard');
    if (version !== briefingVersion || !root.isConnected || !S.me || S.me.id !== pilotId) return;
    const homeIds = new Set(d.home_options.flat().map(r => r.id));
    const departures = d.departures.filter(r => !homeIds.has(r.id));
    const leg = r => `<button class="brief-route" type="button" data-brief-flight="${esc(r.id)}"><span><b>${esc(r.origin.icao)} <span aria-hidden="true">→</span> ${esc(r.destination.icao)}</b><small>${esc(r.id)} · ${esc(hm(r.minutes))} · ${esc(r.aircraft)}</small></span><span class="brief-availability">${r.available ? 'Review flight →' : 'Aircraft unavailable'}</span></button>`;
    root.innerHTML = `<div class="brief-heading"><div><div class="kicker">Pilot dashboard</div><h2>Welcome aboard, ${esc(d.pilot.name)}</h2><p>${esc(d.pilot.id)} · ${esc(d.pilot.rank)}</p></div><button class="btn ghost small" type="button" data-brief-refresh>Refresh briefing</button></div>
    ${startHereHTML(d)}
    <div class="brief-overview"><div><span>Current station</span><strong>${esc(d.location.icao)}</strong><small>${esc(d.location.name || '')}</small></div><div><span>Home hub</span><strong>${esc(d.hub.icao)}</strong><small>${d.at_home ? 'You’re at home base' : 'Return options below'}</small></div><div><span>Total flight hours</span><strong>${esc(d.pilot.hours)}</strong><small>PAC and credited transfer hours</small></div></div>
    <div class="brief-grid"><article class="brief-card"><div class="kicker">Next on your checklist</div><h3>${d.booking ? 'Your flight is booked' : d.checkride_needed ? 'Ready for your checkride?' : 'Ready for your next flight?'}</h3>
    ${d.booking ? `<p><b>${esc(d.booking.flight_number)}</b> · ${esc(d.booking.aircraft)} ${esc(d.booking.registration || '')}</p><button class="btn" type="button" data-brief-view="bids">Review flight & release →</button>` : d.checkride_needed ? '<p>Complete your checkride to progress through your PAC career.</p><button class="btn" type="button" data-brief-view="career/qualifications">View checkride and qualifications</button>' : '<p>Review a departure below, or explore the full mission board.</p><button class="btn" type="button" data-brief-view="missions">Explore missions</button>'}
    <details class="brief-progress"><summary>Career progress</summary><h4>${d.pilot.next ? `Next rank: ${esc(d.pilot.next)}` : esc(d.pilot.rank)}</h4>${d.pilot.requirements.length ? `<ul>${d.pilot.requirements.map(r => `<li><span aria-label="${r.done ? 'Complete' : 'Outstanding'}">${r.done ? '✓' : '○'}</span> ${esc(r.label)}${r.value != null ? ` <span class="muted">(${esc(r.value)} / ${esc(r.target)})</span>` : ''}</li>`).join('')}</ul>` : '<p>Your current rank has no further progression requirements listed.</p>'}<button class="btn ghost small" type="button" data-brief-view="career">View career</button></details></article>
    <article class="brief-card"><div class="kicker">Get back to base</div><h3>${d.at_home ? 'You’re home at ' + esc(d.hub.icao) : esc(d.location.icao) + ' → ' + esc(d.hub.icao)}</h3>${d.at_home ? '<p>Explore departures from your current station to plan your next trip.</p>' : d.home_options.length ? d.home_options.map(legs => `<div class="brief-connection">${legs.map(leg).join('')}${legs.length > 1 ? '<small>Two sectors. Review each leg separately; onward aircraft availability may change.</small>' : ''}</div>`).join('') : '<p>No direct or one-stop scheduled option matches your current qualifications and aircraft requirements.</p><button class="btn ghost small" type="button" data-brief-view="missions">Explore other missions</button>'}<p class="brief-note">Suggestions are not reservations. Aircraft, location and qualification checks apply when booking.</p></article></div>
    <article class="brief-card brief-departures"><div class="kicker">Departures from ${esc(d.location.icao)}</div><h3>Where will you fly next?</h3>${departures.length ? `<div class="brief-departure-grid">${departures.map(leg).join('')}</div><p class="brief-note">Showing ${departures.length} additional scheduled departures. Return options are listed above.</p>` : '<p>No additional matching departures. Review the return options above or explore the mission board.</p>'}</article>`;
    root.querySelector('[data-brief-refresh]').onclick = loadPilotBriefing;
    if (d.staff_playbook?.length) {
      const duties = document.createElement('section'); duties.className = 'brief-card staff-duty-card';
      const desks = { ceo: ['staff', 'Open Staff'], dir_ops: ['operations', 'Open Ops desk'], fleet_mgr: ['fleetmgr', 'Open Maintenance'], commercial: ['commercial', 'Open Commercial'], creative: ['creative', 'Open Media & comms'], livery_mgr: ['liverylib', 'Open Livery library'], academy_director: ['academy', 'Open Academy'] };
      duties.innerHTML = `<div class="kicker">Your staff responsibilities</div><h3>What to watch and what to do</h3><div class="staff-duty-grid">${d.staff_playbook.map(r => `<div><h4>${esc(r.title)}</h4><p><b>Watch:</b> ${esc(r.watch)}</p><p><b>Action:</b> ${esc(r.action)}</p>${desks[r.role] ? `<button class="btn ghost small" type="button" data-brief-view="${desks[r.role][0]}">${desks[r.role][1]} →</button>` : ''}</div>`).join('')}</div><p class="brief-note">Crew Mail carries direct staff alerts. Check the relevant desk for live details before acting; ask the CEO when the case falls outside your role.</p>`;
      root.querySelector('.brief-overview').after(duties);
    }
    const now=document.createElement('section');now.className='brief-card now-card';root.querySelector('.brief-overview').after(now);loadHappeningNow(now,d);const crewPanel=document.createElement('section');crewPanel.className='brief-card';now.after(crewPanel);loadDashboardCrew(crewPanel);
    const planner = document.createElement('section');
    planner.className = 'brief-card rotation-planner';
    root.querySelector('.brief-departures').before(planner);
    loadRotationPlanner(planner, d);
    root.querySelectorAll('[data-brief-view]').forEach(b => b.onclick = () => {
      if (b.dataset.briefView === 'fleetmgr') S.fleetTab = 'mx';
      if (b.dataset.briefView === 'operations') S.opsTab = 'exceptions';
      show(b.dataset.briefView);
    });
    root.querySelectorAll('[data-brief-flight]').forEach(b => b.onclick = () => flyMission(b.dataset.briefFlight));
  } catch (e) {
    if (version !== briefingVersion || !root.isConnected) return;
    root.innerHTML = '<p role="status">Your briefing is temporarily unavailable. You can still use Missions and Career.</p><button class="btn ghost small" type="button">Try again</button>';
    root.querySelector('button').onclick = loadPilotBriefing;
  }
}

/* Personal itineraries use scheduled routes and the existing booking flow. */
async function loadRotationPlanner(root, briefing) {
  const pilot = S.me?.id;
  const current = () => root.isConnected && S.me?.id === pilot;
  root.innerHTML = '<p role="status">Loading your rotation planner…</p>';
  try {
    const state = await api('/api/pilot/rotation-plan');
    if (!current()) return;
    const saved = state.saved;
    const routeLine = p => [p.legs[0].origin, ...p.legs.map(l => l.destination)].map(esc).join(' <span aria-hidden="true">→</span> ');
    const legsHTML = (p, progress = null) => `<ol class="rotation-legs">${p.legs.map((l, i) => `<li class="${progress != null && i < progress ? 'rotation-done' : ''}"><div><b>${esc(l.origin)} → ${esc(l.destination)}</b><small>${esc(l.id)} · ${esc(hm(l.minutes))} · ${esc(l.cargo)} · ${esc(fmt(l.payload_lbs))} lb</small></div><span>${progress == null ? `Leg ${i + 1}` : i < progress ? 'Accepted ✓' : i === progress ? 'Next leg' : 'Later'}</span></li>`).join('')}</ol>`;
    root.innerHTML = `<div class="brief-heading"><div><div class="kicker">Your next cargo run</div><h3>Plan my rotation</h3><p>Connected scheduled flights, tailored to your time.</p></div></div>
      ${saved ? `<article class="rotation-saved"><div class="rotation-title"><div><span class="kicker">Saved itinerary · ${esc(saved.aircraft)}</span><h4>${routeLine(saved)}</h4></div><button type="button" class="btn ghost small" data-rotation-clear>Remove plan</button></div><p>${saved.completed}/${saved.legs.length} legs accepted · ${esc(hm(saved.total_minutes))} planned total</p>${legsHTML(saved, saved.completed)}
        ${saved.completed === saved.legs.length ? '<p class="rotation-success">Rotation complete. Welcome to your destination!</p>' : `<button type="button" class="btn" data-rotation-next ${state.booking || saved.legs[saved.completed].origin !== state.location ? 'disabled' : ''}>Review next leg →</button><p class="brief-note">${state.booking ? 'Finish your current booking before starting the next leg.' : saved.legs[saved.completed].origin !== state.location ? `Next leg departs ${esc(saved.legs[saved.completed].origin)}; you are at ${esc(state.location)}. Progress updates after accepted flight reports.` : 'Opens the existing mission planner. Confirm the saved aircraft type before booking.'}</p>`}
        <p class="brief-note">Saved to your pilot account. Only matching, accepted flights filed after saving count toward progress.</p></article>` : ''}
      <details class="rotation-controls" ${saved ? '' : 'open'}><summary>${saved ? 'Find a different rotation' : 'Choose your flying time'}</summary>
      <form class="rotation-form"><label>Aircraft<select name="aircraft" required>${state.eligible_types.map(t => `<option value="${esc(t)}">${esc(t)} · ${esc(S.fleet[t]?.name || t)}</option>`).join('')}</select></label>
      <label>Time available<select name="minutes"><option value="120">2 hours</option><option value="180">3 hours</option><option value="240" selected>4 hours</option><option value="360">6 hours</option><option value="480">8 hours</option><option value="720">12 hours</option><option value="1440">24 hours</option></select></label>
      <label>Between legs<select name="turnaround"><option value="0">No extra time</option><option value="20" selected>20 minutes</option><option value="30">30 minutes</option><option value="45">45 minutes</option><option value="60">60 minutes</option></select></label>
      <label class="rotation-checkbox"><input name="return_home" type="checkbox" checked> Finish at home (${esc(state.hub)})</label>
      <button class="btn" type="submit" ${state.checkride_needed || !state.eligible_types.length ? 'disabled' : ''}>Find rotations →</button></form>
      <p class="brief-note">Starts at ${esc(state.location)} · Up to 4 legs · Full cargo loads · Estimated block time plus time between legs. Allow extra time for preflight. ${state.checkride_needed ? 'Complete your checkride first.' : ''}</p>
      <div class="rotation-results" aria-live="polite"></div></details>
      <p class="brief-note">A plan does not reserve aircraft or flights. Availability, location, qualifications and route details are checked again when booking.</p>`;
    const next = root.querySelector('[data-rotation-next]');
    if (next) next.onclick = () => flyMission(saved.legs[saved.completed].id, saved.aircraft);
    const clear = root.querySelector('[data-rotation-clear]');
    if (clear) clear.onclick = async () => {
      clear.disabled = true;
      try { await api('/api/pilot/rotation-plan', {method:'DELETE'}); if (current()) await loadRotationPlanner(root, briefing); }
      catch (e) { if (current()) { clear.disabled = false; toast(e.message); } }
    };
    root.querySelector('form').onsubmit = async event => {
      event.preventDefault();
      const form = event.currentTarget, button = form.querySelector('button'), results = root.querySelector('.rotation-results');
      const body = {aircraft: form.elements.aircraft.value, minutes: Number(form.elements.minutes.value), turnaround: Number(form.elements.turnaround.value), return_home: form.elements.return_home.checked};
      button.disabled = true;
      results.innerHTML = '<p role="status">Finding connected cargo routes…</p>';
      try {
        const data = await api('/api/pilot/rotation-options', {method:'POST', body});
        if (!current()) return;
        results.innerHTML = `${data.airframes_enforced && !data.available_airframes ? '<p class="rotation-warning">No available airframe of this type at your station right now. You can save a plan for later.</p>' : ''}${data.booking ? '<p class="rotation-warning">You have a booking. These plans start at your current recorded station; your location may change when you finish it.</p>' : ''}
          ${data.plans.length ? data.plans.map((p,i) => `<article class="rotation-option"><div class="rotation-title"><div><span class="kicker">Option ${i + 1} · ${esc(p.aircraft)} · ${p.legs.length} ${p.legs.length === 1 ? 'leg' : 'legs'}</span><h4>${routeLine(p)}</h4></div><strong>${esc(hm(p.total_minutes))}</strong></div><p class="brief-note">${esc(hm(p.flight_minutes))} block time + ${esc(hm(p.total_minutes - p.flight_minutes))} between legs</p>${legsHTML(p)}<button type="button" class="btn ghost" data-save-rotation="${i}">${saved ? 'Replace saved itinerary' : 'Save this itinerary'}</button></article>`).join('') : '<p>No matching rotation found within these limits. Try more time, another aircraft, or uncheck “Finish at home.”</p>'}
          ${data.limited ? '<p class="brief-note">Search limit reached. These are suggestions from a bounded search, not every possible itinerary.</p>' : ''}`;
        results.querySelectorAll('[data-save-rotation]').forEach(b => b.onclick = async () => {
          const p = data.plans[Number(b.dataset.saveRotation)];
          results.querySelectorAll('button').forEach(x => x.disabled = true);
          try {
            await api('/api/pilot/rotation-plan', {method:'POST', body:{...body, route_ids:p.legs.map(l => l.id)}});
            if (current()) { await loadRotationPlanner(root, briefing); toast('Rotation saved to your pilot account.'); }
          } catch (e) { if (current()) { results.querySelectorAll('button').forEach(x => x.disabled = false); toast(e.message); } }
        });
      } catch (e) { if (current()) results.innerHTML = `<p role="alert">${esc(e.message)}</p>`; }
      finally { if (current()) button.disabled = false; }
    };
  } catch (e) {
    if (!current()) return;
    root.innerHTML = '<h3>Plan my rotation</h3><p role="status">The planner is temporarily unavailable.</p><button class="btn ghost small" type="button">Try again</button>';
    root.querySelector('button').onclick = () => loadRotationPlanner(root, briefing);
  }
}


async function staffOperationsHealth() {
  const root = $('#staffBody');
  root.innerHTML = '<p role="status">Reading operations health…</p>';
  const ago = value => value == null ? 'Not available' : value < 60 ? 'Less than a minute ago' : value < 3600 ? `${Math.floor(value / 60)} minutes ago` : value < 86400 ? `${Math.floor(value / 3600)} hours ago` : `${Math.floor(value / 86400)} days ago`;
  const when = value => value ? new Date(value * 1000).toLocaleString() : 'Not recorded';
  try {
    const d = await api('/api/staff/operations-health');
    if (!root.isConnected || S.staffTab !== 'health' || !S.me?.staff) return;
    const card = (title, item, body) => `<article class="ops-card ops-${esc(item.level)}"><div class="ops-card-head"><h2>${esc(title)}</h2><span class="ops-state">${esc({ok:'Healthy',warning:'Attention',unknown:'Unavailable',notice:'Info'}[item.level] || 'Unavailable')}</span></div><p>${esc(item.message)}</p>${body}${item.note ? `<p class="muted">${esc(item.note)}</p>` : ''}</article>`;
    root.innerHTML = `<div class="ops-heading"><div><h2>Operations health</h2><p class="muted">Read-only snapshot · Checked ${esc(when(d.checked_at))}</p></div><button class="btn ghost small" type="button" id="opsRefresh">Refresh status</button></div><div class="ops-grid">` +
      card('Mission worker',d.worker,`<dl><dt>Last successful refresh</dt><dd>${esc(when(d.worker.last_success_at))} · ${esc(ago(d.worker.age_seconds))}</dd><dt>Last run duration</dt><dd>${d.worker.duration_seconds == null ? 'Not recorded' : esc(d.worker.duration_seconds) + ' seconds'}</dd></dl>`) +
      card('Mission boards',d.boards,d.boards.counts ? `<div class="ops-counts">${Object.entries(d.boards.counts).map(([label,count]) => `<div><strong>${esc(count)}</strong><span>${esc(label)}</span></div>`).join('')}</div>` : '') +
      card('Discord bot',d.discord,`<p>Last heartbeat: ${esc(when(d.discord.last_seen))} · ${esc(ago(d.discord.age_seconds))}</p>`) +
      (d.vatsim ? card('VATSIM listing readiness',d.vatsim,`${d.vatsim.counts ? `<div class="ops-counts">${Object.entries(d.vatsim.counts).map(([label,count]) => `<div><strong>${esc(count)}</strong><span>${esc(label)}</span></div>`).join('')}</div>` : ''}<p><a href="/api/staff/vatsim-flights.csv">Download the flight list for VATSIM</a> (callsign, origin, destination, date)</p>`) : '') +
      card('Application backups',d.backups,`<p>${esc(d.backups.name || 'No backup recorded')}</p><p>${esc(ago(d.backups.age_seconds))}</p>`) + '</div><p class="muted">Refreshes only when you open this tab or select Refresh status. No services are restarted and no missions or backups are created by this panel.</p>';
    $('#opsRefresh').onclick = staffOperationsHealth;
  } catch (e) {
    if (!root.isConnected || S.staffTab !== 'health') return;
    root.innerHTML='<p role="status">Operations health could not be loaded.</p><button class="btn ghost small" type="button">Try again</button>';
    root.querySelector('button').onclick=staffOperationsHealth;
  }
}


/* Pilot journey: guidance uses existing actions; the server retains booking authority. */
function setCareerSection(section, updateURL = true) {
  const allowed = ['overview', 'qualifications', 'wallet', 'activities', 'awards'];
  if (!allowed.includes(section)) section = 'overview';
  S.careerSection = section;
  document.querySelectorAll('[data-career-pane]').forEach(p => p.hidden = p.dataset.careerPane !== section);
  document.querySelectorAll('[data-career-section]').forEach(b => {
    b.setAttribute('aria-current', b.dataset.careerSection === section ? 'page' : 'false');
  });
  if (updateURL) location.hash = 'career/' + section;
}
function resetMissionFilters(render = true) {
  Object.assign(S, {parkedOrigin:'',shipmentDestinations:[], shipmentFilterTitle:'', boardCampaignId:'', boardSearch:'', boardCargo:'', boardShortHeavy:false, boardQualifiedOnly:false, boardAvailableOnly:false, boardReadyOnly:false, boardPage:1, sortBy:'default', fromHere:false, simFilter:'', divFilter:'', acFilter:'', lenFilter:'any', netSearch:'', region:'All', filter:'All', partnerFilter:null, jobKind:'all', netLimit:40});
  if (render) { renderPilotStrip(); renderMissions(); }
}
function travelGuideHTML() {
  return `<div class="journey-travel-grid">
    <article><h3>Free checkride travel</h3><p><b>Moves you, not the aircraft.</b> Open Career → Qualifications. Choose a fleet checkride and PAC includes free travel when you book it. Dedicated training needs no travel and leaves your normal station unchanged. Generate a matching OFP for your chosen route.</p><button type="button" class="btn ghost small" onclick="closePilotGuide();show('career/qualifications')">View qualifications →</button></article>
    <article><h3>Jumpseat</h3><p><b>Moves you to another station.</b> Your PAC location is shown in Career → Pay & wallet. Travel to your mission's departure, or to the aircraft if you want to fly its ferry yourself. Review the travel quote before confirming.</p><button type="button" class="btn ghost small" onclick="closePilotGuide();show('career/wallet')">View location & wallet →</button></article>
    <article><h3>Have it ferried</h3><p><b>Moves an available aircraft to you.</b> You must be at the mission's departure to see this paid action in its airframe list. The fee is $100 + $0.20 per nautical mile from your PAC wallet. You see the quote before paying. Booked or unavailable aircraft cannot be moved.</p></article>
    <article><h3>Fly it yourself</h3><p><b>A separate ferry flight with no cargo.</b> Choose “Fly it to…” beside an available aircraft. This builds a ferry plan from its current station. You still need to be qualified and positioned there before booking. Finish the ferry before requesting your cargo flight.</p></article>
  </div>`;
}
function pilotWelcomeHTML() {
  let dismissed = false;
  try { dismissed = localStorage.getItem('pac-guide-dismissed-' + S.me?.id) === '1'; } catch (_) {}
  return `<section class="journey-welcome" aria-label="Pilot help"><div><span class="kicker">Your flight starts here</span><h3>${dismissed ? 'Need a hand with your next step?' : 'New to PAC? Let’s get you flying.'}</h3>${dismissed ? '' : '<p>Get qualified, find an aircraft, then plan and release your flight. Training travel is free when offered for your type checkride.</p>'}</div><div class="row"><button class="btn" onclick="openPilotGuide()">First-flight guide</button><button class="btn ghost" onclick="show('career/qualifications')">Qualifications</button>${dismissed ? '' : '<button class="journey-text-button" onclick="dismissPilotWelcome(this)">Keep this compact</button>'}</div></section>`;
}
function dismissPilotWelcome(button) {
  try { localStorage.setItem('pac-guide-dismissed-' + S.me?.id, '1'); } catch (_) {}
  const panel = button.closest('.journey-welcome');
  if (panel) panel.outerHTML = pilotWelcomeHTML();
}
function closePilotGuide() { document.getElementById('pilotGuideDialog')?.close(); }
function openPilotGuide(path = 'checkride') {
  let dialog = document.getElementById('pilotGuideDialog');
  if (!dialog) {
    dialog = document.createElement('dialog'); dialog.id = 'pilotGuideDialog';
    dialog.className = 'journey-dialog'; dialog.setAttribute('aria-labelledby','pilotGuideTitle');
    document.body.append(dialog);
  }
  const training = path !== 'cargo';
  const steps = training ? [
    ['Choose your aircraft', 'Open Qualifications and find the family you want to fly. The card shows your rating, eligibility and available checkride action.'],
    ['Get to an available aircraft', 'Choose dedicated training at a supported airport, or a fleet checkride with free positioning travel. No paid ferry is needed; existing aircraft reservations are respected.'],
    ['Generate and import your plan', 'Book the checkride from its card to open mission planning. Confirm the route and aircraft, then press Generate OFP on the SimBrief & request tab; the plan comes in by itself. (Or open SimBrief yourself, click Generate Flight, then Fetch latest OFP.)'],
    ['Request, review and sign', 'Request the mission, then open My bids. Review the cargo, load and dispatch paperwork. Sign the release before starting tracking.'],
    ['Fly and submit your report', 'Open PAC ACARS, load the correct flight and aircraft in your simulator, and follow the checklist. After the flight, file your report. A passing checkride unlocks the rating when the report is accepted.']
  ] : [
    ['Choose your cargo flight', 'Browse Missions. Check the departure, payload and aircraft. Your qualification and current PAC location matter, as well as the aircraft’s location.'],
    ['Arrange the aircraft and your travel', 'Choose an available tail at the departure. If necessary, jumpseat yourself there, have an available aircraft delivered to you, or fly a separate ferry. The guide below explains each option.'],
    ['Generate and import your plan', 'Check the aircraft and the load sheet, then press Generate OFP on the SimBrief & request tab; the plan comes in by itself. (Or open SimBrief yourself, click Generate Flight, then Fetch latest OFP.) Resolve any mismatch shown.'],
    ['Review the cargo and sign', 'Request the mission, open My bids and review the release, shipments and handling instructions. Use the load planner where supported. Review and sign the final release.'],
    ['Track, fly and file', 'Open PAC ACARS and follow the aircraft checklist. Complete the flight and file your PIREP. Review status determines when accepted-flight credit is awarded.']
  ];
  dialog.innerHTML = `<div class="journey-dialog-head"><div><span class="kicker">PAC crew guide</span><h2 id="pilotGuideTitle">From choosing a flight to flying it</h2></div><button type="button" class="btn ghost small" onclick="closePilotGuide()" aria-label="Close first-flight guide">Close</button></div>
    <div class="journey-dialog-body"><div class="journey-sections" aria-label="Choose your guide"><button type="button" aria-pressed="${training}" onclick="openPilotGuide('checkride')">I need a type checkride</button><button type="button" aria-pressed="${!training}" onclick="openPilotGuide('cargo')">I’m flying cargo</button></div>
    <ol class="journey-guide-steps">${steps.map(([title,body],i) => `<li><span class="journey-number" aria-hidden="true">${i+1}</span><div><h3>${title}</h3><p>${body}</p></div></li>`).join('')}</ol>
    <div class="row"><button class="btn" onclick="closePilotGuide();show('${training ? 'career/qualifications' : 'missions'}')">${training ? 'Find my qualification' : 'Find a cargo flight'} →</button><button class="btn ghost" onclick="closePilotGuide();show('bids')">My current booking</button></div>
    <details class="journey-help"><summary>Jumpseat, company travel or aircraft ferry?</summary>${travelGuideHTML()}</details>
    <p class="muted">This guide explains the workflow. Your qualification cards, mission validation and aircraft checklist provide the applicable requirements.</p></div>`;
  if (!dialog.open) dialog.showModal();
}
function missionReadiness(m) {
  if (S.booking) return '';
  const ac = S.aircraft, dep = m.origin.icao, here = S.me?.location?.icao;
  const messages = [];
  if (S.me?.enforce_location && here !== dep) messages.push(`Your PAC location is ${here || 'not loaded'}; this flight departs ${dep}.`);
  const rating = needsRating(m, ac);
  if (rating) messages.push(`You need the ${rating} type rating for this aircraft.`);
  if (lockedByRank(m, ac)) messages.push('This aircraft is not unlocked at your current rank. Review Qualifications for your options.');
  const frames = (S.airframes || []).filter(a => a.type === ac);
  if (!m.contract && S.settings.enforce_airframes !== false && !frames.some(a => a.status === 'Available' && a.location === dep && (!m.fixed_airframe || a.reg === m.fixed_airframe))) {
    messages.push(`No available ${S.fleet[ac]?.icao || ac} airframe at ${dep}.`);
  }
  const training = !!m.type_checkride || m.category === "Checkride" || m.id === S.checkrideId;
  return `<section class="journey-readiness ${messages.length ? 'needs-attention' : ''}" aria-label="Before you plan"><span class="kicker">Before you plan</span><h3>${messages.length ? 'A few things to arrange first' : 'Check your aircraft, then plan'}</h3>${messages.length ? `<ul>${messages.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '<p>No location, rating or availability blocker was found in the information loaded. Review the aircraft and payload below; final checks run when you request the flight.</p>'}
    ${training ? '<p><b>For a type checkride, look for free company travel in Qualifications before paying for a ferry.</b></p>' : ''}
    <div class="row">${training || rating || lockedByRank(m, ac) ? '<button type="button" class="btn small" onclick="show(\'career/qualifications\')">Qualifications & training travel</button>' : ''}${!training && here !== dep && S.me?.enforce_location ? `<button type="button" class="btn small" onclick="openJumpseat('${esc(dep)}')">Travel to ${esc(dep)}</button>` : ''}<button type="button" class="btn ghost small" onclick="openPilotGuide('${training ? 'checkride' : 'cargo'}')">Step-by-step guide</button></div></section>`;
}

/* Mission browsing uses existing loaded data; booking remains server-validated. */
function missionBoardPool() {
  const pool = [...(S.missions || []), ...(S.checkrides || []), ...(S.urgent || []), ...(S.jobs || []), ...(S.routes || []), ...rotationBoardList(), ...eventsBoardList()];
  return [...new Map(pool.map(m => [m.id, m])).values()];
}
function boardTypes(m) {
  return (m.aircraft || []).filter(a => S.fleet[a] && !S.fleet[a].retired && (!S.acFilter || a === S.acFilter) && (!S.simFilter || fliesIn(a, S.simFilter)));
}
function boardQualified(m, a) {
  if (!S.me || !S.ratings || !S.career) return false;
  return !lockedByRank(m, a) && !needsRating(m, a);
}
function boardAvailable(m, a) {
  // Partner work supplies its own aircraft; never invent a PAC tail for it.
  if (m.contract) return true;
  return (S.airframes || []).some(f => f.type === a && f.status === 'Available' && f.location === m.origin.icao && (!m.fixed_airframe || f.reg === m.fixed_airframe));
}
function boardMatchTypes(m) {
  return boardTypes(m).filter(a => (!S.boardQualifiedOnly || boardQualified(m,a)) && (!S.boardAvailableOnly || boardAvailable(m,a)));
}
function boardReadyAtStation(m, allTypes = false) {
  const here = S.me?.location?.icao;
  const types = allTypes ? (m.aircraft || []).filter(a => S.fleet[a] && !S.fleet[a].retired) : boardTypes(m);
  return !!here && m.origin?.icao === here && zoneFor(m)?.level !== 'restricted' &&
    types.some(a => boardQualified(m, a) &&
      (m.contract || S.settings.enforce_airframes === false || boardAvailable(m, a)));
}
function boardNextAction(m) {
  if (zoneFor(m)?.level === 'restricted') return 'Review airspace restriction';
  const types = boardTypes(m);
  if (!S.me || !S.ratings || !S.career) return 'Review eligibility';
  const qualified = types.filter(a => boardQualified(m, a));
  if (!qualified.length) return 'Review qualifications';
  if (S.me.enforce_location && S.me.location?.icao !== m.origin.icao) return `Travel to ${m.origin.icao}`;
  if (!m.contract && S.settings.enforce_airframes !== false && !qualified.some(a => boardAvailable(m, a))) return 'Arrange an aircraft';
  return 'Review and plan';
}
function renderMissionChoiceBar() {
  const el = $('#missionChoiceBar'); if (!el) return;
  el.hidden = S.board === 'charter';
  if (el.hidden) return;
  const here = S.me?.location?.icao;
  const count = here ? missionBoardPool().filter(m => boardReadyAtStation(m, true)).length : 0;
  el.innerHTML = `<div><span class="kicker">Start from your station</span><strong>${here ? `${count} ${count === 1 ? 'flight' : 'flights'} to review from ${esc(here)}` : 'Station or eligibility still loading'}</strong><small>Current location, ratings and aircraft are checked again when you request a flight.</small></div>
    <div class="mb-choice-actions"><button type="button" class="btn small" id="boardReadyShortcut" aria-pressed="${!!S.boardReadyOnly}" ${!here ? 'disabled' : ''}>${S.boardReadyOnly ? 'Showing ready flights' : 'Ready from my station →'}</button>${S.boardReadyOnly ? '<button type="button" class="btn ghost small" id="boardShowAll">Show all flights</button>' : ''}</div>`;
  $('#boardReadyShortcut').onclick = () => { resetMissionFilters(false); S.board = 'all'; S.boardReadyOnly = true; renderPilotStrip(); renderMissions(); $('#manifest').scrollIntoView({block:'start'}); };
  if ($('#boardShowAll')) $('#boardShowAll').onclick = () => { S.boardReadyOnly = false; renderMissions(); };
}
function boardSource(m) {
  if (m.category === 'Checkride' || m.type_checkride || m.id === S.checkrideId) return 'Checkride';
  if (m.contract) return 'Partner crew';
  if (m.urgent) return 'Urgent';
  if (m.rotation) return 'Rotation';
  if (m.tour) return 'Tour';
  if (m.job_kind) return 'Job board';
  if ((S.routes || []).some(r => r.id === m.id)) return 'Scheduled';
  return 'Mission';
}
function boardStatus(m) {
  const zq = zoneFor(m);
  if (zq?.level === "restricted") return `Not authorized · ${zq.names.join(", ")} is restricted airspace`;
  const types = boardTypes(m), qualified = types.filter(a => boardQualified(m,a));
  if (!S.me || !S.ratings || !S.career) return 'Review qualifications before planning';
  if (!qualified.length) return 'Review rank or type-rating requirements';
  if (S.me.enforce_location && S.me.location?.icao !== m.origin.icao) return `Pilot travel needed · departs ${m.origin.icao}`;
  if (!m.contract && S.settings.enforce_airframes !== false && !qualified.some(a => boardAvailable(m,a))) return 'Aircraft positioning needed for a qualified type';
  return m.contract ? 'Qualified type · partner supplies aircraft' : S.settings.enforce_airframes === false ? 'Qualified type · aircraft assignment checked when requesting' : `Qualified type · aircraft at ${m.origin.icao}`;
}
function boardAccent(m) {
  if (m.urgent) return 'urgent';
  return ({'Humanitarian':'relief','Express':'express','Heavy lift':'heavy','Medical':'medical','Medicine':'medical'})[m.category] || 'standard';
}
function shedTag(m) {
  const x = S.shedMap?.[m.origin?.icao];
  return x && x.pct >= 85 ? `<span class="tag lane-review" title="The shed at ${esc(x.station)} is ${x.pct}% full">Clears a congested shed</span>` : "";
}
function laneTag(m) {
  const L = S.laneMap?.[`${m.origin?.icao}>${m.destination?.icao}`];
  if (!L || L.tier === "Good") return "";
  const cls = { Preferred: "lane-pref", "Under review": "lane-review", "At risk": "lane-risk" }[L.tier];
  return `<span class="tag ${cls}" title="Lane reputation ${L.score}/100 from ${L.flights} recent flight${L.flights === 1 ? "" : "s"}">${esc(L.tier)} lane · ${L.score}</span>`;
}
async function loadLanes(force) {
  if (!S.me?.id || (S.laneMap && !force && Date.now() - (S.laneAt || 0) < 300000)) return S.laneList || [];
  api("/api/sheds").then(x => { S.shedMap = Object.fromEntries((x.sheds || []).map(y => [y.station, y])); }).catch(() => {});
  try { const d = await api("/api/lanes"); S.laneList = d.lanes; S.accountList = d.accounts || []; S.laneMap = Object.fromEntries(d.lanes.map(L => [`${L.origin}>${L.destination}`, L])); S.laneAt = Date.now(); }
  catch (e) { S.laneMap = S.laneMap || {}; }
  return S.laneList || [];
}
function boardCard(m) {
  return `<button type="button" class="waybill mb-card mb-accent-${boardAccent(m)}${zoneFor(m)?.level === "restricted" ? " wb-restricted" : ""}" data-id="${esc(m.id)}" aria-pressed="${S.selected?.id === m.id}">
    <span class="mb-card-top"><span class="mb-work-label">${m.relief ? '<span class="relief-label">HUMANITARIAN RELIEF</span>' : m.urgent ? '<span class="mb-urgent-label">! URGENT</span>' : ''}${esc([...new Set([m.urgent && m.urgent_kind ? m.urgent_kind : boardSource(m), m.short_heavy ? "Short-haul heavies" : m.category || 'Cargo'])].join(" · "))}</span><span>${esc(m.id)}</span></span>
    <span class="mb-route"><span><b>${esc(m.origin.icao)}</b><small>${esc(m.origin.city || m.origin.name)}</small></span><span aria-hidden="true">→</span><span><b>${esc(m.destination.icao)}</b><small>${esc(m.destination.city || m.destination.name)}</small></span></span>
    <strong class="mb-title">${esc(m.title)}</strong><span class="mb-cargo">${esc(m.cargo)}</span>
    <span class="mb-tags">${shedTag(m)}${laneTag(m)}${zoneTag(m)}${m.short_heavy ? `<span class="tag dark">${fmt(m.distance_nm)} NM · Routine delivery</span>` : ""}${boardCampaignLabels(m)}${bonusTags(m)}${freshTags(m)}${m.tour || m.rotation ? `<span class="tag dark">Leg ${esc(m.leg)}/${esc(m.legs)}</span>` : ''}${m.handling ? `<span class="tag grey">${esc(m.handling.label)}</span>` : ''}${m.challenge ? `<span class="tag amber">${esc(m.challenge.label)}</span>` : ''}${m.urgent ? `<span class="tag amber">URGENT ×1.5 · deliver by ${zulu(m.deliver_by)}</span><span>Offer: <span class="countdown" data-countdown="${Number(m.expires)}"></span></span>` : ''}</span>
    <span class="mb-facts"><span>Estimated block<b>${hm(m.target_block_min)}</b></span><span>Recommended types<b>${(m.aircraft || []).map(a=>esc(S.fleet[a]?.icao || a)).join(', ')}</b>${(() => { const ds = [...new Set((m.aircraft || []).map(divOf).filter(Boolean))]; return ds.length ? `<small class="mb-div">${ds.map(d => esc(divShort(d))).join(" · ")}</small>` : ""; })()}</span><span>Cargo load<b>${fmt(m.payload_lbs || 0)} lb</b></span><span>Reward<b>${fmt(m.reward || 0)} points${m.short_heavy ? ` · includes ${fmt(m.handling_points)} handling points` : ""}${m.contract_bonus ? ` · $${fmt(m.contract_bonus)} bonus` : m.ferry_bonus ? ` · $${fmt(m.ferry_bonus)} ferry bonus` : ''}</b></span></span>
    <span class="mb-status"><b>Next: ${esc(boardNextAction(m))}</b><small>${esc(boardStatus(m))}</small></span><span class="mb-card-bottom"><small>Final checks run when you request</small><b>Review flight →</b></span></button>`;
}
function boardSearchList(list) {
  if(S.parkedOrigin) list=list.filter(m=>m.origin?.icao===S.parkedOrigin);
  const q = (S.boardSearch || '').trim().toLowerCase();
  return list.filter(m => (!S.shipmentDestinations?.length || (Number(m.payload_lbs)>0 && !m.ferry && !m.type_checkride && m.id!==S.checkrideId && !["Ferry","Checkride","Type checkride"].includes(m.category) && m.job_kind!=="ferry" && S.shipmentDestinations.includes(m.destination.icao))) && boardCampaignFilter(m) && (!q || [m.id,m.title,m.cargo,m.category,m.origin.icao,m.origin.city,m.origin.name,m.destination.icao,m.destination.city,m.destination.name].some(x=>String(x || '').toLowerCase().includes(q))) &&
    (!S.boardCargo || m.category === S.boardCargo) && (!S.boardShortHeavy || m.short_heavy === true) &&
    (!(S.acFilter || S.simFilter || S.boardQualifiedOnly || S.boardAvailableOnly) || boardMatchTypes(m).length));
}
function renderBoardTools() {
  const el = $('#missionBrowseTools'); if (!el) return;
  el.hidden = S.board === 'charter';
  const categories = [...new Set(missionBoardPool().map(m=>m.category).filter(Boolean))].sort();
  el.innerHTML = `${S.parkedOrigin ? `<p><b>Departures from ${esc(S.parkedOrigin)}</b> · Use Reset filters to browse all airports.</p>` : ""}<div class="mb-search-row"><label>Find a flight<input type="search" id="boardSearch" placeholder="Airport, city, cargo or flight number" value="${esc(S.boardSearch || '')}"></label><label>Cargo work<select id="boardCargo"><option value="">All cargo types</option>${categories.map(c=>`<option ${S.boardCargo===c?'selected':''}>${esc(c)}</option>`).join('')}</select></label></div>
    <div class="mb-quick"><button type="button" class="chip" data-mb-toggle="boardShortHeavy" aria-pressed="${!!S.boardShortHeavy}">Short-haul heavies · 100–300 NM</button><button type="button" class="chip" data-mb-toggle="boardQualifiedOnly" aria-pressed="${!!S.boardQualifiedOnly}">Qualified recommended types</button><button type="button" class="chip" data-mb-toggle="boardAvailableOnly" aria-pressed="${!!S.boardAvailableOnly}">Aircraft at departure / partner supplied</button><button type="button" class="chip" data-mb-toggle="boardReadyOnly" aria-pressed="${!!S.boardReadyOnly}">Ready from my station</button><button type="button" class="btn ghost small" id="boardReset">Reset filters</button></div>
    <p class="mb-note">Filters match the same recommended aircraft type. Availability and qualifications are checked again when booking.</p>`;
  $('#boardSearch').oninput = e => { S.boardSearch=e.target.value; clearTimeout(S._boardSearchTimer); S._boardSearchTimer=setTimeout(()=>{renderMissions();const input=$('#boardSearch');input.focus();input.setSelectionRange(input.value.length,input.value.length);},180); };
  $('#boardCargo').onchange=e=>{S.boardCargo=e.target.value;renderMissions();};
  el.querySelectorAll('[data-mb-toggle]').forEach(b=>b.onclick=()=>{S[b.dataset.mbToggle]=!S[b.dataset.mbToggle];renderMissions();});
  $('#boardReset').onclick=resetMissionFilters;
  const drawer=$('#boardInspiration');drawer.hidden=S.board==='charter';
  // Use current data, rather than fabricated flight history or destination claims.
  const options=missionBoardPool().filter(m=>m.origin.icao===S.me?.location?.icao && boardMatchTypes(m).some(a=>boardQualified(m,a)&&boardAvailable(m,a))).sort((a,b)=>(a.target_block_min||0)-(b.target_block_min||0)).slice(0,3);
  $('#boardSuggestions').innerHTML=options.length ? options.map(m=>`<button type="button" class="mb-suggestion" data-suggestion="${esc(m.id)}"><b>${esc(m.origin.icao)} → ${esc(m.destination.icao)}</b><span>${esc(m.title)}</span><small>${hm(m.target_block_min)} · ${esc(boardSource(m))}</small></button>`).join('') : '<p class="mb-note">No matching suggestions at your station right now. Browse the boards or visit Qualifications for checkride and free company-travel options.</p>';
  $('#boardSuggestions').querySelectorAll('[data-suggestion]').forEach(b=>b.onclick=()=>selectMission(b.dataset.suggestion));
}
function boardPage(list) {
  const signature=JSON.stringify([S.board,S.filter,S.region,S.netSearch,S.acFilter,S.simFilter,S.divFilter,S.lenFilter,S.sortBy,S.fromHere,S.partnerFilter,S.jobKind,S.boardSearch,S.boardCargo,S.boardShortHeavy,S.boardQualifiedOnly,S.boardAvailableOnly,S.boardReadyOnly,S.boardCampaignId,list.map(m=>m.id)]);
  if(signature!==S._boardPageKey){S.boardPage=1;S._boardPageKey=signature;}
  const pages=Math.max(1,Math.ceil(list.length/6));S.boardPage=Math.min(Math.max(1,S.boardPage||1),pages);
  const start=(S.boardPage-1)*6,shown=list.slice(start,start+6);
  const pager=$('#boardPagination');pager.hidden=S.board==='charter';
  pager.innerHTML=`<span role="status">${list.length?`${start+1}–${start+shown.length}`:'0'} of ${list.length} matching flights</span><div><button class="btn ghost small" id="boardPrevious" ${S.boardPage===1?'disabled':''}>Previous</button><span>Page ${S.boardPage} of ${pages}</span><button class="btn small" id="boardNext" ${S.boardPage===pages?'disabled':''}>Next</button></div>`;
  for(const [id,delta] of [['boardPrevious',-1],['boardNext',1]])$('#'+id).onclick=()=>{S.boardPage+=delta;renderMissions();$('#manifest').scrollIntoView({block:'start'});$('#manifest').focus({preventScroll:true});};
  return shown;
}

/* Campaign discovery is advisory. Accepted PIREPs remain the source of credit. */
function boardActiveCampaigns() {
  const now=Date.now()/1000;
  if (S._campaignPilot !== S.me?.id) return [];
  return (S.boardCampaigns || []).filter(c=>c.state==='published' && Number(c.starts)<=now && now<Number(c.ends) && !c.archived_at);
}
function boardCampaignMatches(m) {
  if (!(Number(m.payload_lbs)>0) || m.ferry || m.type_checkride || m.id===S.checkrideId || ['Checkride','Type checkride','Ferry'].includes(m.category) || m.job_kind==='ferry' || m.origin?.icao===m.destination?.icao) return [];
  return boardActiveCampaigns().filter(c=>(c.destinations || []).includes(m.destination?.icao));
}
function boardCampaignLabels(m) {
  return boardCampaignMatches(m).map(c=>`<span class="tag mb-campaign-tag" title="Potential contribution. File within the campaign dates; the cargo report must qualify and be accepted.">Campaign · ${esc(c.title)}</span>`).join('');
}
function boardCampaignFilter(m) {
  return !S.boardCampaignId || boardCampaignMatches(m).some(c=>String(c.id)===String(S.boardCampaignId));
}
async function loadBoardCampaigns(force=false) {
  const pilot=S.me?.id;
  if (!pilot) return;
  if (S._campaignPilot!==pilot) {
    S._campaignPilot=pilot;S.boardCampaigns=[];S.boardCampaignId='';S._campaignAt=0;S._campaignLoading=false;S._campaignError=false;
  }
  if (S._campaignLoading || (!force && Date.now()-(S._campaignAt || 0)<60000)) return;
  S._campaignLoading=true;S._campaignError=false;
  const token={};S._campaignRequest=token;
  try {
    const data=await api('/api/pilot/cargo-campaigns');
    if(S.me?.id!==pilot || S._campaignRequest!==token)return;
    if(!Array.isArray(data.campaigns))throw new Error('Campaign list unavailable');
    S.boardCampaigns=data.campaigns;S._campaignAt=Date.now();
  } catch(error) {
    if(S.me?.id!==pilot || S._campaignRequest!==token)return;
    S.boardCampaigns=[];S._campaignError=true;S._campaignAt=Date.now();
  } finally {
    if(S.me?.id===pilot && S._campaignRequest===token){
      S._campaignLoading=false;
      if(!$('#view-missions')?.hidden)renderMissions();
    }
  }
}
function renderBoardCampaigns() {
  const el=$('#boardCampaignPanel');if(!el)return;
  el.hidden=S.board==='charter';
  if(!S.me){el.innerHTML='';return;}
  if(S._campaignError){
    el.innerHTML=`<p class="mb-note">Campaigns could not load. Flight browsing is still available. <button type="button" class="btn ghost small" id="campaignRetry">Retry campaigns</button>${S.boardCampaignId?' <button type="button" class="btn ghost small" onclick="resetMissionFilters()">Clear campaign filter</button>':''}</p>`;
    $('#campaignRetry').onclick=()=>{loadBoardCampaigns(true);};return;
  }
  const list=boardActiveCampaigns();
  if(!list.length){el.innerHTML=S.boardCampaignId?'<p class="mb-note">The selected campaign is no longer active. <button type="button" class="btn ghost small" onclick="resetMissionFilters()">Browse all flights</button></p>':'';return;}
  const campaign=list.find(c=>String(c.id)===String(S.boardCampaignId || S.boardFeaturedCampaign)) || list[0];
  const pct=Math.min(100,Math.max(0,Number(campaign.pct)||0));
  el.innerHTML=`<div class="mb-campaign-heading"><div><span class="kicker">Fly toward a shared goal</span>${list.length>1?`<label class="mb-note">Active campaign <select id="boardCampaignChoice">${list.map(c=>`<option value="${Number(c.id)}" ${c.id===campaign.id?'selected':''}>${esc(c.title)}</option>`).join('')}</select></label>`:`<h2>${esc(campaign.title)}</h2>`}<p>${(campaign.destinations || []).map(esc).join(' · ')} · ${fmt(campaign.cargo_lbs)} / ${fmt(campaign.target_lbs)} lb delivered · ${pct}%</p></div><div class="row"><button type="button" class="btn small" id="findCampaignFlights">Find campaign flights →</button><button type="button" class="btn ghost small" id="viewCampaignProgress">View progress</button></div></div>
    <progress max="100" value="${pct}" aria-label="${esc(campaign.title)} progress" title="Cargo arrivals at these destinations may contribute. File during the campaign dates; credit follows an accepted, qualifying report.">${pct}%</progress>
    ${S.boardCampaignId?`<p class="mb-note">Cargo arrivals at these destinations may contribute. <b>Campaign filter active: ${esc(list.find(c=>String(c.id)===String(S.boardCampaignId))?.title || 'previous campaign')}.</b> <button type="button" class="btn ghost small" id="clearCampaignFilter">Clear campaign filter</button></p>`:''}`;
  const choice=$('#boardCampaignChoice');if(choice)choice.onchange=()=>{S.boardFeaturedCampaign=choice.value;S.boardCampaignId='';renderMissions();};
  $('#findCampaignFlights').onclick=()=>{
    S.board='all';resetMissionFilters();S.boardCampaignId=String(campaign.id);renderMissions();$('#manifest').scrollIntoView({block:'start'});$('#manifest').focus({preventScroll:true});
  };
  $('#viewCampaignProgress').onclick=()=>{S.statsTab='campaigns';show('stats');};
  const clear=$('#clearCampaignFilter');if(clear)clear.onclick=()=>{S.boardCampaignId='';renderMissions();};
}

function cargoAwardArt(a) {
  if (a.patch) return `<img src="${esc(a.patch)}" alt="${esc(a.title)} patch" style="width:120px;height:120px;object-fit:contain">`;
  const colors=['#173c52','#7d202b','#285342','#493b66'];const color=colors[Math.abs(Number(a.id)||0)%colors.length];
  return `<svg viewBox="0 0 120 120" role="img" aria-label="${esc(a.title)} contributor patch"><circle cx="60" cy="60" r="55" fill="${color}" stroke="#d9ba6e" stroke-width="5"/><circle cx="60" cy="60" r="48" fill="none" stroke="#d9ba6e" stroke-dasharray="2 3"/><text x="60" y="33" text-anchor="middle" fill="white" font-size="17" font-weight="800">PAC</text><path d="M60 44l8 15 28 5-28 7-8 15-8-15-28-7 28-5z" fill="#d9ba6e"/><text x="60" y="101" text-anchor="middle" fill="white" font-size="10">${esc(a.year)} · ${Number(a.id)||0}</text></svg>`;
}
function campaignPatchShelf(flair) {
  const awards=flair?.campaign_awards || [];if(!awards.length)return '';
  return `<section class="ce-awards"><h3>Earned campaign patches</h3><div>${awards.map(a=>`<figure>${cargoAwardArt(a)}<figcaption><b>${esc(a.title)}</b><small>Shared target reached · contributor</small></figcaption></figure>`).join('')}</div></section>`;
}
async function loadFeaturedShipment(force=false) {
  const pid=S.me?.id;if(!pid)return;
  if(S._featurePilot!==pid){S._featurePilot=pid;S.featuredShipment=null;S._featureAt=0;S._featureBusy=false;S._featureError=false;}
  if(S._featureBusy || (!force && Date.now()-(S._featureAt||0)<60000))return;
  S._featureBusy=true;const token={};S._featureToken=token;
  try{const d=await api('/api/pilot/featured-shipment');if(S.me?.id!==pid || S._featureToken!==token)return;S.featuredShipment=d.shipment;S._featureError=false;}
  catch(e){if(S.me?.id!==pid || S._featureToken!==token)return;S.featuredShipment=null;S._featureError=true;}
  finally{if(S.me?.id===pid && S._featureToken===token){S._featureBusy=false;S._featureAt=Date.now();renderFeaturedShipment();}}
}
function renderFeaturedShipment() {
  const el=$('#featuredShipment');if(!el)return;el.hidden=S.board==='charter';
  if(S._featurePilot!==S.me?.id){el.innerHTML='';return;}
  if(S._featureError){el.innerHTML='<p class="muted">Featured shipment could not load. <button class="btn ghost small" onclick="loadFeaturedShipment(true)">Retry</button></p>';return;}
  const f=S.featuredShipment,now=Date.now()/1000;
  if(!f || now<f.starts || now>=f.ends){el.innerHTML='';return;}
  el.innerHTML=`<article class="ce-feature"><div><span class="kicker">Shipment of the Week · fictional cargo story</span><h2>${esc(f.title)}</h2><p class="ce-story">${esc(f.description)}</p><small>${(f.destinations||[]).map(esc).join(' · ')} · through ${new Date((f.ends-1)*1000).toLocaleDateString(undefined,{timeZone:'UTC'})} UTC</small></div><button class="btn" id="ceFindFlights">Find flights to these destinations →</button><p class="ce-note">Choose a suitable cargo flight. This feature does not reserve a consignment or change its load, pay or campaign rules.</p></article>`;
  $('#ceFindFlights').onclick=()=>{S.board='all';resetMissionFilters();S.shipmentDestinations=[...f.destinations];S.shipmentFilterTitle=f.title;renderMissions();$('#manifest').scrollIntoView({block:'start'});};
}
function shipmentFilterNote(){
  if(!S.shipmentDestinations?.length)return '';
  return `<span class="ce-filter">Featured destinations: ${S.shipmentDestinations.map(esc).join(', ')} <button type="button" class="btn ghost small" onclick="S.shipmentDestinations=[];renderMissions()">Clear</button></span>`;
}
function receiptHTML(r) {
  return `<div class="ce-receipt"><div class="ce-receipt-head"><span class="kicker">PAC cargo operations · delivery receipt</span><h2>${esc(r.flight_number)} · ${esc(r.dep)} → ${esc(r.arr)}</h2><span class="tag ${r.qualifies?'green':'amber'}">${esc(r.review_status || 'Not credited')}</span></div><p>${esc(r.reason)}</p>
    <div class="ce-receipt-totals"><div><small>Reported cargo</small><b>${fmt(r.reported_cargo_lbs)} lb</b></div><div><small>Qualifying cargo</small><b>${fmt(r.credited_cargo_lbs)} lb</b></div><div><small>Posted to wallet</small><b>${money(r.posted_total,true)}</b></div></div>
    <h3>Campaign contribution</h3>${r.campaigns.length?`<ul>${r.campaigns.map(c=>`<li><b>${esc(c.title)}</b> · ${fmt(c.cargo_lbs)} lb credited</li>`).join('')}</ul><p class="ce-note">A delivery may support multiple campaigns; cargo and pay are not multiplied.</p>`:'<p class="muted">No campaign credit for this report under the current rules.</p>'}
    <h3>Recorded earnings and adjustments</h3>${r.postings.length?`<div class="ce-ledger">${r.postings.map(p=>`<div><span>${esc(p.description || p.kind)}</span><b>${money(p.amount,true)}</b></div>`).join('')}</div>`:'<p class="muted">No wallet entries have been posted for this flight.</p>'}
    ${campaignPatchShelf({campaign_awards:r.awards})}<p class="ce-note">Receipt #${Number(r.id)} · Reflects the current report review and ledger. Awards shown are your currently earned campaign patches.</p></div>`;
}
async function openDeliveryReceipt(id) {
  let d=$('#deliveryReceiptDialog');if(!d){d=document.createElement('dialog');d.id='deliveryReceiptDialog';d.className='journey-dialog';document.body.append(d);}
  const pid=S.me?.id,token={};d._request=token;
  d.innerHTML='<div class="journey-dialog-head"><h2>Delivery receipt</h2><button class="btn ghost small" onclick="this.closest(\'dialog\').close()">Close</button></div><div class="journey-dialog-body" id="receiptBody"><p role="status">Loading recorded delivery…</p></div>';
  if(!d.open)d.showModal();
  try{const r=await api('/api/pilot/delivery-receipt/'+Number(id));if(d._request!==token || S.me?.id!==pid || !d.open)return;$('#receiptBody').innerHTML=receiptHTML(r);}
  catch(e){if(d._request===token && d.open && S.me?.id===pid)$('#receiptBody').innerHTML=`<p role="alert">${esc(e.message)}</p><button class="btn" onclick="openDeliveryReceipt(${Number(id)})">Retry</button>`;}
}
function offerDeliveryReceipt(id){
  const el=$('#latestDeliveryReceipt');if(!el || !Number.isInteger(id))return;
  el.innerHTML=`<div class="ce-receipt-offer"><div><b>Your flight report is filed.</b><p>See its review status, campaign contribution and posted earnings.</p></div><button class="btn" onclick="openDeliveryReceipt(${id})">View delivery receipt →</button></div>`;
}
async function loadShipmentEditor(root=$('#shipmentEditor')){
  const pid=S.me?.id;if(!root || !hasCap('commercial'))return;
  const current=()=>root.isConnected && S.me?.id===pid && hasCap('commercial');
  root.innerHTML='<p>Loading shipment features…</p>';
  try{const data=await api('/api/staff/featured-shipments');if(!current())return;
    const today=new Date().toISOString().slice(0,10),last=new Date(Date.now()+6*86400000).toISOString().slice(0,10);
    root.innerHTML=`<details class="cargo-create"><summary>Manage Shipment of the Week</summary><p>Publish a fictional cargo story with links to flights serving its destinations. One published feature can cover any given day.</p><form id="shipmentForm" class="cargo-form"><label>Title<input name="title" required minlength="3" maxlength="80" placeholder="Island clinic resupply"></label><label>Cargo story<textarea name="description" required maxlength="1000" rows="3" placeholder="A fictional shipment, why it matters, and what pilots are carrying."></textarea></label><div class="cargo-form-row"><label>Start (UTC)<input name="start_date" type="date" required value="${today}"></label><label>Last day (UTC)<input name="end_date" type="date" required value="${last}"></label></div><label>Destination ICAOs<input name="destinations" required placeholder="MYNN, TJSJ, TNCM"></label><button class="btn" type="submit">Save private shipment draft</button><p id="shipmentStatus" role="status"></p></form><div class="ce-features">${data.shipments.map(f=>`<article><span class="kicker">${esc(f.state)}</span><h3>${esc(f.title)}</h3><p class="ce-story">${esc(f.description)}</p><p>${f.destinations.map(esc).join(', ')} · ${new Date(f.starts*1000).toISOString().slice(0,10)} – ${new Date((f.ends-1)*1000).toISOString().slice(0,10)} UTC</p>${f.state==='draft'?`<button class="btn small" data-feature="${f.id}" data-action="publish">Publish shipment</button> `:''}${f.state!=='archived'?`<button class="btn ghost small" data-feature="${f.id}" data-action="archive">Archive</button>`:''}</article>`).join('')}</div></details>`;
    $('#shipmentForm').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,b=f.querySelector('button'),fields=f.elements;b.disabled=true;try{await api('/api/staff/featured-shipments',{method:'POST',body:{title:fields.title.value,description:fields.description.value,start_date:fields.start_date.value,end_date:fields.end_date.value,destinations:fields.destinations.value.split(/[\s,]+/).filter(Boolean)}});if(current())loadShipmentEditor(root);}catch(err){if(current()){$('#shipmentStatus').textContent=err.message;b.disabled=false;}}};
    root.querySelectorAll('[data-feature]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api('/api/staff/featured-shipments/'+b.dataset.feature,{method:'POST',body:{action:b.dataset.action}});S._featureAt=0;if(current())loadShipmentEditor(root);}catch(e){if(current()){toast(e.message);b.disabled=false;}}});
  }catch(e){if(current())root.innerHTML=`<p role="alert">${esc(e.message)}</p><button class="btn ghost small" onclick="loadShipmentEditor()">Retry shipment editor</button>`;}
}

/* Secondary controls stay available without dominating the flight list. */
function updateBrowseSummary() {
  const drawer = document.getElementById('browseDetails');
  if (!drawer) return;
  drawer.hidden = S.board === 'charter';
  const active = [S.filter && S.filter !== 'All', S.region && S.region !== 'All', S.netSearch,
    S.acFilter, S.simFilter, S.divFilter, S.lenFilter && S.lenFilter !== 'any', S.sortBy && S.sortBy !== 'default',
    S.partnerFilter, S.jobKind && S.jobKind !== 'all'].filter(Boolean).length;
  document.getElementById('browseSummary').textContent = `More filters & sorting${active ? ` · ${active} active` : ''}`;
}


/* Pilot experience: existing booking/release/status remain authoritative. */
function preparationPanel(b, st, available) {
  const m=b.mission,dep=m.origin.icao,here=S.me?.location?.icao;
  const aircraft=!!(m.training || b.airframe || m.contract || S.settings.enforce_airframes===false);
  const positioned=m.training?.mode==='dedicated' || here===dep || S.me?.enforce_location===false;
  const release=!!b.signed && !b.release_amended;
  const connected=!!(available && st.tracking && st.connected && st.booking && st.booking.requested_at===b.requested_at && st.booking.flight_number===b.flight_number);
  const steps=[
    [aircraft,'Aircraft selected',b.airframe || (m.training?'Temporary training aircraft':m.contract?'Partner-supplied aircraft':aircraft?'Airframe assignment not required':'No assigned airframe in this booking'),'<button class="btn ghost small" onclick="show(\'acars\')">Review booked flight</button>'],
    [positioned,'Pilot positioned',m.training?.mode==='dedicated'?`Dedicated session at ${dep}; normal station unchanged`:here===dep?`At ${dep}`:S.me?.enforce_location===false?'Pilot location is not enforced':`Recorded location: ${here||'unavailable'} · departure ${dep}`,`<button class="btn ghost small" onclick="show('career/wallet')">Review location & travel</button>`],
    [release,'Dispatch reviewed',release?'Current release signed':b.release_amended?'Release changed — review again':needsSignature(b)?'Review and sign before tracking':'Signature optional; review your release before departure','<a class="btn ghost small" href="/dispatch" target="_blank" rel="noopener">Review dispatch release →</a>'],
    [connected,'ACARS connected',!available?'Connection status unavailable — try refreshing':connected?'Fresh tracking connection for this booking':st.tracking?'Tracking reported; matching connection not confirmed':'Open PAC ACARS and start this booked flight',`<a class="btn ghost small" href="${appLink(b)}">Open PAC ACARS →</a>`]
  ];
  const n=steps.filter(s=>s[0]).length,next=steps.findIndex(s=>!s[0]);
  return `<section class="px-prep"><div class="px-heading"><div><span class="kicker">YOUR NEXT STEPS</span><h2>Prepare your flight</h2></div><span>${n} of 4 confirmed</span></div><div class="px-progress"><span style="width:${n*25}%"></span></div><div class="px-steps">${steps.map((s,i)=>`<article class="${s[0]?'ready':i===next?'next':''}"><span class="px-number">${s[0]?'✓':i+1}</span><div><h3>${s[1]}</h3><p>${esc(s[2])}</p>${s[3]}</div></article>`).join('')}</div><p class="muted">This is a preparation guide. Aircraft checks and the server’s flight rules still apply.</p><button class="btn ghost small" onclick="refreshPreparation()">Refresh readiness</button></section>`;
}
async function refreshPreparation(){try{await refreshCore();await loadMe();await refreshReleaseGate();await loadBids();}catch(e){toast(e.message)}}
function missionCargoBrief(m){
  if(m.relief)return reliefBrief(m);
  const purpose={Humanitarian:'Relief cargo supports the teams receiving it at the destination.',Medical:'Medical cargo supports care and supply continuity at the destination.',Medicine:'Medical cargo supports care and supply continuity at the destination.',Express:'Express cargo supports time-sensitive connections and deliveries.', 'Heavy lift':'Outsize and heavy cargo needs an aircraft and load plan suited to the shipment.',AOG:'Aircraft parts help a receiving maintenance team return an aircraft to service.'};
  const date=t=>new Date(t*1000).toLocaleString('en-US',{timeZone:'UTC',dateStyle:'medium',timeStyle:'short'})+' UTC';
  const deadline=Number(m.deliver_by)>0?`Arrive by ${date(m.deliver_by)}`:'No fixed delivery deadline listed';
  return `<section class="px-cargo"><span class="kicker">THE CARGO BEHIND THE FLIGHT</span><h3>${esc(m.cargo || m.title)}</h3><p>${esc(m.briefing || 'Review the cargo, route and aircraft requirements below before requesting this flight.')}</p>${purpose[m.category]?`<div class="px-purpose"><b>Why it matters</b><p>${esc(purpose[m.category])}</p></div>`:''}<div class="px-deadline"><b>${esc(deadline)}</b>${Number(m.expires)>0?`<small>Booking offer closes ${esc(date(m.expires))}. This is separate from any arrival deadline.</small>`:''}</div><details><summary>Before you request this flight</summary><ul><li>Check your qualification and the selected aircraft’s payload and range.</li><li>Review pilot location and aircraft availability below.</li><li>${m.handling?'Read the shipment handling instructions below.':'No additional shipment handling instructions are listed in this mission.'}</li>${m.challenge?'<li>Review the airport challenge notes below.</li>':''}</ul></details></section>`;
}
function patchShowcase(c){
  const own=c.patches.filter(p=>p.owned),ids=c.featured_patches||[];
  if(!own.length)return '<section class="px-prep"><h2>Your patch showcase</h2><p>Your purchased patches will appear here. Choose up to three to feature on your profile.</p></section>';
  return `<section class="px-prep"><span class="kicker">YOUR PROFILE SHOWCASE</span><h2>Make it your own</h2><p>Feature up to three patches. Removing one from display keeps it in your collection.</p><div class="px-showcase"><div class="px-patch-grid">${own.map(p=>`<article>${patchSVG(p,80)}<b>${esc(p.name)}</b><button class="btn ghost small" data-feature-patch="${esc(p.id)}" aria-pressed="${ids.includes(p.id)}">${ids.includes(p.id)?'✓ Featured · remove':'Feature patch'}</button></article>`).join('')}</div><aside><h3>On your profile</h3><div class="patch-strip">${ids.map(id=>{const p=own.find(p=>p.id===id);return p?patchSVG(p,64):''}).join('')}</div>${!ids.length?'<p>No patches featured.</p>':''}${ids.map((id,i)=>`<div class="px-order"><span>${esc(own.find(p=>p.id===id)?.name||id)}</span><button class="btn ghost small" data-patch-move="${esc(id)}" data-direction="-1" aria-label="Move ${esc(own.find(p=>p.id===id)?.name)} earlier" ${i===0?'disabled':''}>↑</button><button class="btn ghost small" data-patch-move="${esc(id)}" data-direction="1" aria-label="Move ${esc(own.find(p=>p.id===id)?.name)} later" ${i===ids.length-1?'disabled':''}>↓</button></div>`).join('')}<p class="muted">Changes save immediately. Your earned campaign awards and rank stay separate.</p></aside></div></section>`;
}
let patchSaving=false;
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-feature-patch],[data-patch-move]');if(!b||patchSaving)return;
 const items=[...(S.shop.featured_patches||[])],id=b.dataset.featurePatch||b.dataset.patchMove,i=items.indexOf(id);
 if(b.dataset.patchMove){const j=i+Number(b.dataset.direction);if(i<0||j<0||j>=items.length)return;[items[i],items[j]]=[items[j],items[i]];}
 else if(i>=0)items.splice(i,1);else {if(items.length>=3){toast('Remove a featured patch first. Your showcase has three spaces.');return;}items.push(id);}
 patchSaving=true;b.disabled=true;
 try{S.shop=await api('/api/shop/featured-patches',{method:'POST',body:{items}});await afterShop();toast('Patch showcase saved.');}
 catch(err){toast(err.message);b.disabled=false;}finally{patchSaving=false;}
});
const PAC_UPDATES=[
 {"id": "20261115-radio-cheatsheet", "date": "November 15, 2026", "kind": "New feature", "title": "Radio cheat sheet, built for your flight", "body": "New to talking to ATC on VATSIM? Open your dispatch release and grab the 🗒️ Radio cheat sheet — a full gate-to-gate guide (clearance, push, taxi, takeoff, handoffs, approach, landing) with exactly what to say and what you’ll hear back, prefilled with your callsign, airports and wind-favoured runways. Anything ATC assigns stays as a [bracket] to fill in. Print it or save as PDF. Also at /radio.", "view": "acars", "label": "Open ACARS"},
 {"id": "20261114-unicom-live", "date": "November 14, 2026", "kind": "Improvement", "title": "Unicom calls: smarter and on the ACARS page", "body": "The Unicom call generator now fills your runway automatically from the wind, says the airport\u2019s spoken name in Voice mode (\u201cMemphis traffic\u201d), and \u2014 while PAC ACARS is running \u2014 highlights the exact call for your current phase of flight \u2014 and on IVAO it fills in your next waypoint and ETA on the enroute calls. There\u2019s also a \ud83d\udcfb Unicom calls button right on the ACARS page now, not just the dispatch release.", "view": "acars", "label": "Open ACARS"},
 {"id": "20261114-unicom-gen", "date": "November 14, 2026", "kind": "New feature", "title": "Unicom calls built from your flight", "body": "No controller online? Open your dispatch release and hit \u201c\ud83d\udcfb Unicom calls\u201d \u2014 it builds every call for you, prefilled with your callsign, airports, runways and cruise. Pick VATSIM or IVAO and Text or Voice, then copy each call straight into the sim. Also at /unicom/flight.", "view": "downloads", "label": "Open Downloads"},
 {"id": "20261113-unicom", "date": "November 13, 2026", "kind": "New feature", "title": "Unicom cheat sheet (no ATC online)", "body": "Flying on VATSIM or IVAO with no controller on? There's a new printable cheat sheet for Unicom 122.800: what to do and exactly what to say, phase by phase, with copy-paste text calls. Find it under Learn \u2192 Downloads & cheat sheets, or open /unicom.", "view": "downloads", "label": "Open Downloads"},
 {"id": "20261113-status", "date": "November 13, 2026", "kind": "New feature", "title": "/status in Discord", "body": "Type /status anywhere in the PAC Discord to see your day at a glance: where you are, where you're sleeping tonight, your booked flight or trip leg, your wallet and what's left for your next rank. Only you see the reply. Link your account first with /link (the code is in Settings)."},
 {"id": "20261113-monthly", "date": "November 13, 2026", "kind": "New feature", "title": "Your monthly PAC report", "body": "On the 1st of every month you'll get an email about your month with PAC: flights, hours, cargo moved, best landing, average score and earnings, plus how the whole airline did. The first one arrives December 1. Every email has a one-click link to turn them off."},
 {"id": "20261113-hoppie", "date": "November 13, 2026", "kind": "New feature", "title": "Loadsheet to the cockpit (Hoppie ACARS)", "body": "PAC Load Control (PACLD) can now send your final loadsheet straight to your aircraft's ACARS: weights, CG, limits and trim, as a real load controller would. Use 📡 Send loadsheet to cockpit on the dispatch release, tick Auto-send to have it arrive when you start PAC ACARS, or send REQ LOADSHEET to PACLD from the cockpit. With Auto-send on, PAC Ops (PACOPS) also confirms your OUT/OFF times with an ETA after takeoff and your ON/IN times at the gate. Log on to Hoppie in the aircraft with your own code and the flight's callsign.", "view": "acars", "label": "Open ACARS"},
 {"id": "20261113-new-edition", "date": "November 13, 2026", "kind": "Improvement", "title": "Request a new loadsheet edition", "body": "Changed something after signing the dispatch release? Request new edition reopens it, recalculates the figures and lets you sign again. It works at the gate even with PAC ACARS running, and locks from pushback, like the real thing."},
 {"id": "20261113-a300-cg", "date": "November 13, 2026", "kind": "Improvement", "title": "A300-600F balance matches the aircraft", "body": "The A300's load sheet CG is now calibrated against the iniBuilds EFB at light and heavy loads (within about 0.1% MAC), and the load sheet checks it against the real 15–34% MAC limits."},
 {"id": "20261113-crew-rest", "date": "November 13, 2026", "kind": "New feature", "title": "Crew rest and hotels", "body": "Away from your home base? On a trip, PAC pays your hotel. At KCVG headquarters there are 6 free crew rest rooms, first come, first served. Anywhere else by choice: night 1 is free, nights 2 to 4 are paid from your wallet at the local rate, then charges stop. Your Dashboard shows where you're staying tonight.", "view": "dashboard", "label": "Open Dashboard"},
 {"id": "20261113-badge-signin", "date": "November 13, 2026", "kind": "New feature", "title": "Badge sign-in", "body": "Skip the password: issue your crew badge to your computer (Profile → Sign in with this badge), then drag your badge onto the reader to sign in. Beep, green light, you're in. You can also have the site ask for your badge every time you visit.", "view": "profile", "label": "Open my profile"},
 {"id": "20261112-crew-badges", "date": "November 12, 2026", "kind": "New feature", "title": "Crew badges for everyone, redesigned", "body": "Every pilot's crew page now shows their crew badge, and the badge has a realistic new look: fine-line security pattern, microprint, a holographic photo with a verification seal, a chip, signature and issue stamp. Your badge number now follows your home base, and Download badge saves the front and back.", "view": "profile", "label": "See my badge"},
 {"id": "20261113-daynight", "date": "November 13, 2026", "kind": "New feature", "title": "Day and night on the live map", "body": "The live map and globe have a ☀︎ Day / night button showing where the sun is up right now, with dawn and dusk twilight bands, updated every minute.", "view": "live", "label": "Open the live map"},
 {"id": "20261113-od-swap", "date": "November 13, 2026", "kind": "Improvement", "title": "From / To search with a swap button", "body": "The scheduled network now has separate From and To boxes, and ⇄ reverses the direction in one click.", "view": "missions", "label": "Find a flight"},
 {"id": "20261113-cargo-late", "date": "November 13, 2026", "kind": "Improvement", "title": "Cargo is late only if it misses its own deadline", "body": "Each shipment is now judged against its own promised delivery time, not the flight's block time. Shipments wrongly marked late before have been corrected, and the shipper complaints they caused were withdrawn."},
 {"id": "20261113-hubs", "date": "November 13, 2026", "kind": "New feature", "title": "PAC can open new hubs", "body": "Management can now open new PAC hubs where pilots fly most. A new hub gets missions, trips, cargo orders and a warehouse, and you can choose it as your home base."},
 {"id": "20261113-discord-flights", "date": "November 13, 2026", "kind": "Improvement", "title": "Cleaner flight posts in Discord", "body": "Each flight posts once when you take off and once when you land in #flight-log, never twice."},
 {"id": "20261113-network-nav", "date": "November 13, 2026", "kind": "Improvement", "title": "Easier way back from the network pages", "body": "The Cargo network and tracking pages now have a ← Back to PAC button and menu links, and network buttons inside the site keep the left menu. Thanks, Alex!"},
 {"id": "20261104-acars-11", "date": "November 4, 2026", "kind": "New feature", "title": "PAC ACARS 1.1", "body": "A moving map, a landing debrief after every touchdown, landing practice (circuits and touch-and-goes, never filed), stable approach checks at 1,000 and 500 ft, SOP reminders, fuel checks against your SimBrief plan and your PAC flight in your Discord status. Install 1.1 from Downloads once: from then on PAC ACARS updates itself.", "view": "downloads", "label": "Get PAC ACARS 1.1"},
 {"id": "20261104-academy", "date": "November 4, 2026", "kind": "New feature", "title": "PAC Academy", "body": "Free, interactive 737-800 training: PAC's standard startup flow (based on Boeing's normal procedures) and 22 lessons on every panel of the cockpit, with real screenshots. Open to everyone, members or not, under Resources \u2192 PAC Academy.", "view": "/academy/", "label": "Open PAC Academy"},
 {"id": "20261103-group-flight", "date": "November 3, 2026", "kind": "New feature", "title": "An optional weekly group flight", "body": "Each week there's one suggested route under Crew room \u2192 Group flight. It's entirely optional: fly it at the set time (Saturdays at 23:00 UTC) if you'd like company, or on your own any time that weekend, offline or online, with or without voice chat. It goes out from Cincinnati one week and back home the next, and everyone who flies it shows on the page."},
 {"id": "20261103-globe", "date": "November 3, 2026", "kind": "New feature", "title": "The live map as a globe", "body": "Operations \u2192 Live map now has a Flat map / Globe switch. Spin the globe to follow PAC flights and the parked fleet, with long routes drawn as they really curve. The station buttons and filters work on both, and your choice is remembered on this computer."},
 {"id": "20261103-sports", "date": "November 3, 2026", "kind": "New feature", "title": "Sports and events missions", "body": "A new Sports and events category on the mission board. Fly a hometown pro team's equipment to its games abroad (football, basketball, hockey and baseball, each in its real season), European clubs' summer tours, stock cars to Mexico City, motorcycle grand prix flyaways, bobsleds for the winter World Cup, show-jumping horses and stadium concert tours. Each comes with its own handling notes.", "view": "missions", "label": "Find a sports mission"},
 {"id": "20261103-missions", "date": "November 3, 2026", "kind": "New feature", "title": "Six urgent requests and new kinds of work", "body": "Up to six urgent requests at a time, with new kinds: ship engine parts, grid repairs after a blackout, antivenom, rescue team equipment, servers for a failed data center, race team spares and team equipment for tomorrow's game. The mission board adds durian and mango seasons, sashimi tuna, Alaskan king crab, fashion weeks, the 11.11 shopping festival, smartphone launches, ship spares, data-center builds, Indian Ocean cyclone relief, rhino reintroductions, honeybees and new hot-and-high challenge airports in Africa.", "view": "missions", "label": "See the mission board"},
 {"id": "20261103-divisions", "date": "November 3, 2026", "kind": "New feature", "title": "Fleet divisions", "body": "The fleet is now organized in four divisions: PAC Feeder (the 737s), PAC Mainline (A300, 757, 767), PAC Heavy (MD-11, 777F, 747-400F and 747-8F) and PAC Heritage (727s, 737-200 and 747-200). They show on the Fleet page, on every flight, in your logbook and in My stats, and the mission board can show one division at a time. Your rank and ratings still decide what you fly.", "view": "fleet", "label": "Meet the divisions"},
 {"id": "20261103-roster", "date": "November 3, 2026", "kind": "New feature", "title": "Public roster and flight log", "body": "Crew room now has a Roster and flight log page that anyone can see: every active pilot (first name and initial only), rank, hours and the airline's latest accepted flights. It's part of getting PAC listed with VATSIM and IVAO.", "view": "roster", "label": "Open the roster"},
 {"id": "20261102-partner-photos", "date": "November 2, 2026", "kind": "New feature", "title": "Partner flights look the part", "body": "Fly for FedEx, UPS, Atlas, Cathay, Emirates or Qatar and your landing and takeoff cards now show a real photo of that airline's aircraft, with its logo and Flown for on the card. Partner flights also use the partner's real registrations in SimBrief, on your paperwork and in your logbook.", "view": "missions", "label": "See partner requests"},
 {"id": "20261103-faster", "date": "November 3, 2026", "kind": "Improvement", "title": "A faster website", "body": "Pages for signed-in pilots load several times faster, and your browser now keeps the site's files instead of checking each one on every visit. A website update or restart also no longer drops a flight you're tracking: PAC ACARS picks it straight back up.", "view": "dashboard", "label": "Back to your dashboard"},
 {"id": "20261103-downloads", "date": "November 3, 2026", "kind": "Improvement", "title": "Find your livery faster", "body": "Downloads now filters liveries by simulator and aircraft, and remembers your choice. Links in descriptions are clickable.", "view": "downloads", "label": "Open Downloads"},
 {"id": "20261103-handbook", "date": "November 3, 2026", "kind": "Improvement", "title": "Handbook brought up to date", "body": "The pilot handbook now covers the four-tab flight planning page and Generate OFP, the full scoring table, checkride and direct-entry rules, divisions and partner flights. A printable PDF (v1.3) is in Downloads.", "view": "handbook", "label": "Read the handbook"},
 {id:"20261028-training",date:"October 28, 2026",kind:"New feature",title:"Your checkride. Your choice of airport.",body:"Company-funded checkrides now offer dedicated training at supported airports or an available fleet aircraft with free positioning travel. Same standards, free retakes, no paid ferry needed. Dedicated sessions leave the operational fleet and your normal station untouched.",view:"career/qualifications",label:"Start a checkride"},
{"id": "20261027-dashboard-crew", "date": "October 27, 2026", "kind": "New feature", "title": "Your next crew flight, on the dashboard", "body": "See the next three crew flights with UTC and local departure times, open places and your participation status. View or join a flight and download a calendar entry. Calendar downloads are snapshots; check the board for later changes.", "view": "dashboard", "label": "See upcoming crew flights"},
{"id": "20261027-plan-with-crew", "date": "October 27, 2026", "kind": "Improvement", "title": "Take a mission straight to Fly Together", "body": "Choose Plan with crew in mission details to pre-fill the route and selected aircraft type. Add your departure time and simulator setup before posting. A crew post does not reserve an aircraft.", "view": "missions", "label": "Choose a mission"},
{"id": "20261027-reservations", "date": "October 27, 2026", "kind": "Improvement", "title": "See who has an aircraft reserved", "body": "Aircraft views now show the pilot, flight and planned route when booking details are available. Live ACARS reporting distinguishes flying from ground operations. Availability is checked again when you book.", "view": "fleet", "label": "Check the fleet"},
{"id": "20261027-fly-together", "date": "October 27, 2026", "kind": "New feature", "title": "Find someone to fly with", "body": "Post a shared-cockpit or group flight under Crew room → Fly together. Include your simulator, add-on and an optional Discord username. Join or leave a flight, manage your crew and close finished plans. Past departures leave the upcoming list automatically. Bookings, qualifications and flight credit remain separate.", "view": "crewplans", "label": "Open Fly together"},
{"id": "20261027-parked-fleet", "date": "October 27, 2026", "kind": "New feature", "title": "Find your next aircraft on the map", "body": "Toggle the parked fleet on the Live map to see aircraft grouped at their recorded airport. Filter by type, qualifications or availability, then find departures, arrange pilot travel or request an aircraft-delivery quote before confirming payment.", "view": "live", "label": "Explore the fleet map"},
{"id": "20261026-flight-debrief", "date": "October 26, 2026", "kind": "Improvement", "title": "Understand your flight, not just your score", "body": "Your PIREP now explains recorded deductions, highlights what went well and summarizes shipment timing. Section shortcuts make landing, takeoff and replay details easier to reach. Scores and pay are unchanged; unverified cargo condition and customer handover are clearly identified.", "view": "logbook", "label": "Review your flights"},
 {id:'20261025-short-heavy',date:'October 25, 2026',kind:'New feature',title:'Heavy freighters. Short sectors.',body:'Find 100–300 NM heavy cargo jobs using the Short-haul heavies filter on All flights or the Job board. Four rotating cargo scenarios, estimated block time and 80 handling points included in the reward. Routes favor stations with an available heavy at generation time; availability can change.',view:'missions',label:'Find short-haul heavy jobs'},
 {id:'20261022-preparation',kind:'New feature',title:'Your flight preparation, in one place',body:'My bids now shows your assigned aircraft, recorded pilot location, release signature and ACARS tracking connection, with actions for each step.',view:'bids',label:'Open My bids'},
 {id:'20261022-cargo',kind:'Improvement',title:'Know the cargo before you book',body:'Mission details bring the cargo brief and any arrival deadline together. Booking expiry is shown separately from delivery time.',view:'missions',label:'Browse missions'},
 {id:'20261022-patches',kind:'New feature',title:'Choose your featured patches',body:'Feature up to three owned shop patches on your profile and crew badge, and arrange their order. All your purchases stay in your collection.',view:'shop',label:'Open the shop'}
];
function updatesKey(){return 'pac-read-updates-'+(S.me?.id||'guest')}
function readUpdates(){try{return JSON.parse(localStorage.getItem(updatesKey())||'[]')}catch(e){return []}}
function updateNewsBadge(){const read=readUpdates(),count=PAC_UPDATES.filter(u=>!Array.isArray(read)||!read.includes(u.id)).length;const badge=document.getElementById('pxUpdateCount');if(badge){badge.textContent=count;badge.hidden=!S.me||!count}}
function loadWhatsNew(){updateNewsBadge();const filter=S.updateFilter||'All';$('#updatesRoot').innerHTML=`<div class="profile-bar"><h1>What’s new</h1><button class="btn ghost small" id="pxMarkRead">Mark all as read</button></div><p class="muted">Recent site changes. Operational notices remain in company NOTAMs.</p><p class="notice">Your feedback helps shape PAC. We’re listening and working to make the site better for everyone—this is your VA too. Keep sharing ideas and use Report a problem when something needs fixing.</p><div class="row">${['All','New feature','Improvement'].map(k=>`<button class="btn ${filter===k?'':'ghost'} small" data-update-filter="${k}" aria-pressed="${filter===k}">${k}</button>`).join('')}</div><div class="px-updates">${PAC_UPDATES.filter(u=>filter==='All'||u.kind===filter).map(u=>`<article class="px-prep"><small>${u.date || "October 22, 2026"} · ${u.kind}</small><h2>${u.title}</h2><p>${u.body}</p>${u.view ? `<button class="btn ghost small" data-update-go="${u.view}">${u.label} →</button>` : ""}</article>`).join('')}</div><p class="muted">Read status is saved for your pilot on this browser.</p>`;
 $('#pxMarkRead').onclick=()=>{try{localStorage.setItem(updatesKey(),JSON.stringify(PAC_UPDATES.map(u=>u.id)));updateNewsBadge();toast('Updates marked as read.')}catch(e){toast('This browser could not save your read status.')}};
 document.querySelectorAll('[data-update-filter]').forEach(b=>b.onclick=()=>{S.updateFilter=b.dataset.updateFilter;loadWhatsNew()});
 document.querySelectorAll('[data-update-go]').forEach(b=>b.onclick=()=>{const v=b.dataset.updateGo;if(v.startsWith('/')){location.href=v;return}if(v==='shop')S.shopTab='mine';show(v)});
}
window.addEventListener('hashchange',updateNewsBadge);

function manualReportDetail(p){
 const m=p.detail.manual;
 $('#detailTitle').textContent=`Manual report · ${p.flight_number}`;
 $('#detailBody').innerHTML=`<p><b>${esc(p.review_status)}</b> · ${esc(p.dep)} → ${esc(p.arr)} · ${esc(p.airframe)} · ${hm(p.block_min)}</p><p>Departure: ${new Date(m.departed*1000).toUTCString()}</p><h3>Why ACARS was not used</h3><p style="white-space:pre-wrap">${esc(m.reason)}</p><h3>Supporting information</h3><p style="white-space:pre-wrap">${esc(m.evidence_note||'No supporting information supplied.')}</p>${m.has_screenshot?`<a href="/api/manual-pireps/${Number(p.id)}/evidence" target="_blank" rel="noopener">Open supporting screenshot</a>`:''}<p>Staff note: ${esc(p.review_note||'Awaiting review')}</p><p>Manual reports have no ACARS score, landing measurements, performance bonuses or checkride credit. Approval awards block hours and basic flight pay.${m.completed ? ` Staff also completed the flight: ${m.completed.cargo ? `${m.completed.cargo} shipment${m.completed.cargo === 1 ? "" : "s"} delivered, ` : ""}${m.completed.aircraft_moved ? "aircraft moved, " : ""}${m.completed.booking_closed ? "booking closed" : "no matching booking"}.` : " When they approve it, staff can also deliver the booked cargo and move the aircraft."}</p>`;
 $('#detailDlg').showModal();
}
function openManualReport(){
 let dlg=$('#manualPirepDlg');if(!dlg){dlg=document.createElement('dialog');dlg.id='manualPirepDlg';dlg.style.cssText='width:min(640px,94vw);max-height:90vh;overflow:auto;padding:24px';document.body.append(dlg);}
 dlg.innerHTML=`<form id="manualPirepForm"><h2>Submit a manual PIREP</h2><p>Forgot ACARS or lost tracking? Report the completed flight here. Staff must approve it before hours and basic flight pay are credited.</p><p>No score, landing bonuses or checkride credit. If this was your booked flight, staff can deliver its cargo and move the aircraft when they approve it.</p>${[['flight','Flight number','text'],['dep','Departure ICAO','text'],['arr','Arrival ICAO','text'],['tail','PAC tail number','text'],['departed','Departure date and time (UTC)','datetime-local'],['minutes','Total block time in minutes','number']].map(([id,label,type])=>`<div class="field"><label for="mp-${id}">${label}</label><input id="mp-${id}" name="${id}" type="${type}" required ${id==='minutes'?'min="5" max="1440" step="1"':''}></div>`).join('')}<div class="field"><label for="mp-aircraft">Aircraft type</label><select id="mp-aircraft" name="aircraft">${Object.entries(S.fleet).map(([k,v])=>`<option value="${esc(k)}">${esc(v.name||k)}</option>`).join('')}</select></div><div class="field"><label for="mp-reason">Why was the flight not tracked?</label><textarea id="mp-reason" name="reason" required minlength="10" maxlength="2000"></textarea></div><div class="field"><label for="mp-evidence">Supporting details (optional)</label><textarea id="mp-evidence" name="evidence_note" maxlength="2000" placeholder="Simulator logbook entry, booking reference, or an explanation if no screenshot is available"></textarea></div><div class="field"><label for="mp-image">Screenshot (optional, PNG/JPEG/WebP, up to 2 MB)</label><input id="mp-image" type="file" accept="image/png,image/jpeg,image/webp"></div><p id="mp-error" role="alert"></p><button class="btn" type="submit">Submit for staff review</button> <button class="btn ghost" type="button" id="mp-cancel">Cancel</button></form>`;
 const error=$('#mp-error');
 error.className='notice err';error.hidden=true;error.tabIndex=-1;
 dlg.querySelector('#manualPirepForm > p:nth-of-type(2)').insertAdjacentElement('afterend',error);
 error.insertAdjacentHTML('afterend','<button class="btn ghost" type="button" id="mp-latest">Use my latest PAC booking</button><p class="muted" id="mp-latest-status" role="status">This fills the booked flight, route and aircraft only. Enter your actual departure time, block time and explanation.</p>');
 $('#mp-latest').onclick=async()=>{
   const button=$('#mp-latest'),status=$('#mp-latest-status');button.disabled=true;status.textContent='Looking up your recent booking…';
   try{
     const booking=await api('/api/manual-pireps/latest-flight');
     for(const field of ['flight','dep','arr','aircraft','tail']){
       const input=$(`#mp-${field}`);
       if(input&&booking[field])input.value=booking[field];
     }
     status.textContent=`Filled from your ${booking.source}. Check the details and enter your actual departure time, block time and explanation before submitting.`;
   }catch(err){status.textContent=err.message||'Could not find a recent booking. Enter the details manually.';}
   finally{button.disabled=false;}
 };
 $('#mp-cancel').onclick=()=>dlg.close();
 $('#manualPirepForm').onsubmit=async e=>{
   e.preventDefault();
   const button=e.target.querySelector('[type=submit]');button.disabled=true;error.hidden=true;error.textContent='';
   try{
     const data=Object.fromEntries(new FormData(e.target));const f=$('#mp-image').files[0];
     if(f){
       if(f.size>2*1024*1024)throw Error('Screenshot must be under 2 MB.');
       data.screenshot=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(f)});
     }
     await api('/api/manual-pireps',{method:'POST',body:data});
     dlg.close();toast('Manual PIREP submitted. Awaiting staff review.');await loadLogbook();
   }catch(err){
     error.textContent=err.message||'Unable to submit. Please try again.';
     error.hidden=false;error.focus();dlg.scrollTop=0;
   }finally{button.disabled=false;}
 };
 dlg.showModal();
}

const PAC_CHARTER_CUSTOMERS=[{"id": "dhl", "name": "DHL Global Forwarding", "role": "Air freight connections", "logo": "/static/charter-customers/dhl.svg", "source": "https://group.dhl.com/en/about-us/corporate-divisions/global-forwarding-freight.html", "shipments": [{"id": "priority-parts", "title": "Production-line spares", "cargo": "Crated production-line spares", "brief": "A factory has grouped replacement components for its next maintenance shift. Carry the consolidated shipment to the receiving distribution station."}, {"id": "medical", "title": "Medical equipment", "cargo": "Packaged medical equipment", "brief": "Move packaged diagnostic equipment to a regional distribution center for onward road delivery."}]}, {"id": "dachser", "name": "DACHSER", "role": "Industrial distribution", "logo": "/static/charter-customers/dachser.svg", "source": "https://www.dachser.com/en/air-sea-logistics-network-53", "shipments": [{"id": "industrial", "title": "Industrial replenishment", "cargo": "Palletized industrial components", "brief": "Connect two regional distribution points with a consolidated shipment of factory components."}, {"id": "retail", "title": "Retail replenishment", "cargo": "Packaged retail stock", "brief": "Bring a mixed shipment of retail goods to a receiving depot preparing its next distribution round."}]}, {"id": "dsv", "name": "DSV", "role": "Project and automotive freight", "logo": "/static/charter-customers/dsv.svg", "source": "https://www.dsv.com/en", "shipments": [{"id": "automotive", "title": "Automotive supply run", "cargo": "Crated automotive components", "brief": "Move replacement assemblies to a regional parts center supporting several customers."}, {"id": "project", "title": "Project cargo connection", "cargo": "Crated machinery subassemblies", "brief": "Fly the air leg of a project shipment. The receiving team handles onward road transport; these are multiple crates, not a certified oversized load."}]}, {"id": "kn", "name": "Kuehne+Nagel", "role": "Healthcare and technology", "logo": "/static/charter-customers/kn.png", "source": "https://home.kuehne-nagel.com/en/-/services/air-freight/overview", "shipments": [{"id": "technology", "title": "Technology distribution", "cargo": "Packaged electronics and server components", "brief": "Deliver a consolidated technology shipment to a distribution station preparing customer orders."}, {"id": "healthcare", "title": "Healthcare supply run", "cargo": "Packaged laboratory equipment", "brief": "Move laboratory equipment and non-temperature-controlled medical supplies for regional distribution."}]}, {"id": "ceva", "name": "CEVA Logistics", "role": "Automotive and aerospace", "logo": "/static/charter-customers/ceva.png", "source": "https://www.cevalogistics.com/en/news-and-media/newsroom/ceva-welcomes-bollore-logistics", "shipments": [{"id": "aerospace", "title": "Maintenance work package", "cargo": "Crated aircraft parts and tooling", "brief": "A maintenance team is preparing its next work package. Deliver boxed components and tooling together."}, {"id": "automotive", "title": "Factory components", "cargo": "Palletized automotive spares", "brief": "Carry a consolidated factory shipment between regional logistics centers."}]}, {"id": "maersk", "name": "Maersk", "role": "Air and onward distribution", "logo": "/static/charter-customers/maersk.png", "source": "https://www.maersk.com/transportation-services/air-freight", "shipments": [{"id": "retail", "title": "Distribution connection", "cargo": "Packaged consumer goods", "brief": "Carry the air segment of a shipment with onward warehouse and road distribution."}, {"id": "industrial", "title": "Supply-chain connection", "cargo": "Crated industrial components", "brief": "Connect a dispatch warehouse with a receiving logistics center using a PAC freighter."}]}, {"id": "noatum", "name": "Noatum Logistics", "role": "Industrial and project logistics", "logo": "/static/charter-customers/noatum.png", "source": "https://www.noatumlogistics.com/air-freight/", "shipments": [{"id": "project", "title": "Project supplies", "cargo": "Crated equipment components", "brief": "Transport a consolidated project shipment to the airport nearest the receiving logistics team."}, {"id": "spares", "title": "Regional spares delivery", "cargo": "Crated maintenance spares", "brief": "Move replacement parts and workshop supplies between regional distribution points."}]}];
PAC_CHARTER_CUSTOMERS.push(
 {"id":"geodis","name":"GEODIS","role":"Global freight forwarding","logo":"/static/charter-customers/geodis.svg","source":"https://geodis.com/","shipments":[{"id":"industrial-spares","title":"Industrial spares","cargo":"Crated industrial replacement parts","brief":"Carry a consolidated shipment of replacement parts to a regional distribution center for onward delivery."},{"id":"retail-stock","title":"Retail replenishment","cargo":"Packaged retail merchandise","brief":"Move packaged retail goods between logistics facilities ahead of a scheduled distribution cycle."}]},
 {"id":"expeditors","name":"Expeditors","role":"Air freight and time-critical logistics","logo":"/static/charter-customers/expeditors.gif","source":"https://www.expeditors.com/","shipments":[{"id":"production-spares","title":"Time-critical production spares","cargo":"Crated production-line replacement parts","brief":"A production facility needs replacement components for an upcoming maintenance window. Deliver the consolidated shipment to its regional logistics hub."},{"id":"electronics","title":"Electronics distribution","cargo":"Packaged electronic equipment","brief":"Transport packaged electronics to a distribution facility for onward delivery to business customers."}]},
 {"id":"nx","name":"NX Group","role":"Nippon Express air freight and supply chains","logo":"/static/charter-customers/nx.svg","source":"https://www.nipponexpress.com/","shipments":[{"id":"automotive","title":"Automotive components","cargo":"Crated automotive components","brief":"Move production components between regional logistics centers supporting an automotive supply chain."},{"id":"industrial-parts","title":"Industrial parts delivery","cargo":"Packaged industrial machinery parts","brief":"Deliver a consolidated shipment of machinery parts to a receiving distribution center."}]}
);
function charterCustomerPanel(c){
 if(!$('#charterCustomerStyle')){const s=document.createElement('style');s.id='charterCustomerStyle';s.textContent='.cc-panel{grid-column:1 / -1;width:100%}.cc-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}.cc-card{background:var(--panel,#fff);color:var(--ink,#20252b);border:1px solid var(--line,#d8dde4);padding:16px;border-radius:6px;text-align:left;cursor:pointer;font:inherit}.cc-card[aria-pressed=true]{outline:2px solid #c80000;outline-offset:-2px}.cc-logo{display:flex;align-items:center;justify-content:center;height:60px;background:white;border-radius:4px;margin-bottom:12px;padding:8px}.cc-logo img{max-width:100%;max-height:44px;object-fit:contain}.cc-logo img[src*="maersk"]{max-width:180px;max-height:58px}.cc-card b,.cc-card small{display:block}.cc-card small{margin-top:4px}.cc-brief{border-left:4px solid #c80000;padding:16px;background:var(--panel,#fff);margin:14px 0}@media(max-width:900px){.cc-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:420px){.cc-grid{grid-template-columns:1fr}}.cc-textmark{font-weight:bold;color:#24324b;font-size:19px}';document.head.append(s);}
 const current=PAC_CHARTER_CUSTOMERS.find(x=>x.id===c.customer_id),shipment=current?.shipments.find(x=>x.id===c.shipment_id);
 return `<section class="cc-panel"><div class="kicker">PAC CHARTER DESK</div><h2>Choose who you're carrying for</h2><p>Pick a simulated customer and shipment, then plan your own PAC flight.</p><div class="cc-grid"><button type="button" class="cc-card" data-customer="" aria-pressed="${!current}"><span class="cc-logo cc-textmark">Your charter</span><b>Independent charter</b><small>Your own cargo or ferry flight</small></button>${PAC_CHARTER_CUSTOMERS.map(x=>`<button type="button" class="cc-card" data-customer="${x.id}" aria-pressed="${c.customer_id===x.id}"><span class="cc-logo">${x.logo?`<img src="${x.logo}" alt="${esc(x.name)}">`:`<span class="cc-textmark">${esc(x.name)}</span>`}</span><b>${esc(x.name)}</b><small>${esc(x.role)}</small></button>`).join('')}</div><p class="muted" style="font-size:12px">Fictional flight-simulation assignments. No affiliation, sponsorship or endorsement is implied. You fly a PAC aircraft.</p>${current?`<div class="field"><label for="ccShipment">Shipment brief</label><select id="ccShipment">${current.shipments.map(x=>`<option value="${x.id}" ${x.id===c.shipment_id?'selected':''}>${esc(x.title)}</option>`).join('')}</select></div><div class="cc-brief"><b>${esc(shipment?.title||'Choose a shipment')}</b><p>${esc(shipment?.brief||'')}</p><small>Set the cargo weight and review aircraft availability below. Standard PAC booking rules and pay apply.</small></div>`:''}</section>`;
}
function bindCharterCustomers(c){
 const choose=(id,sid)=>{const customer=PAC_CHARTER_CUSTOMERS.find(x=>x.id===id),shipment=customer?.shipments.find(x=>x.id===sid)||customer?.shipments[0];c.customer_id=id;c.shipment_id=shipment?.id||'';c.cargo=shipment?.cargo||'General cargo';S.charterMission=null;S.selected=null;S.ofp=null;S.planned=false;renderMissions();};
 document.querySelectorAll('[data-customer]').forEach(b=>b.onclick=()=>choose(b.dataset.customer));if($('#ccShipment'))$('#ccShipment').onchange=e=>choose(c.customer_id,e.target.value);
}

/* Evidence-led presentation only: does not change scoring or pay. */
function pacFlightConfiguration(c) {
  if (!c || typeof c !== 'object') return '';
  const e = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const starts = (Array.isArray(c.eng_starts) ? c.eng_starts : [])
    .filter(x => x && Number.isInteger(x.n) && x.n >= 1 && x.n <= 4)
    .map(x => `ENG ${x.n}`);
  const lightNames = [['beacon','Beacon'],['nav','Navigation'],['strobe','Strobe'],['landing','Landing'],['taxi','Taxi']];
  const lights = snapshot => {
    if (!snapshot || typeof snapshot !== 'object' || !Object.keys(snapshot).length) return '<p>Not recorded</p>';
    return lightNames.map(([key, label]) => `<div><span>${label}</span><b>${snapshot[key] === true ? 'On' : snapshot[key] === false ? 'Off' : 'Not recorded'}</b></div>`).join('');
  };
  return `<section class="pd-configuration" data-pd-section="Configuration">
    <h3>Flight configuration</h3>
    <div class="pd-grid">
      <div class="pd-metric"><small>Engine start order</small><strong>${e(starts.join(' → ') || 'No starts recorded')}</strong></div>
      <div class="pd-metric"><small>Single-engine taxi</small><strong>${c.single_eng_taxi === true ? 'Recorded' : 'No single-engine taxi recorded'}</strong></div>
      <div class="pd-metric"><small>Departure lights · OUT</small><div class="pd-light-list">${lights(c.dep_config)}</div></div>
      <div class="pd-metric"><small>Arrival lights · IN</small><div class="pd-light-list">${lights(c.arr_config)}</div></div>
    </div>
    <p class="pd-note">Recorded flight observations only. Configuration does not change the flight grade.</p>
  </section>`;
}
function pacTimingReview(tc, er) {
  if (!tc && !er) return '';
  const e = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const mins = v => v == null ? '–' : (v >= 60 ? `${Math.floor(v / 60)}h ${String(Math.round(v % 60)).padStart(2, '0')}m` : `${Math.round(v)} min`);
  const verdict = {ok: ['On plan', ''], late: ['Late', 'warn'], early: ['Early', 'warn'], over: ['Over', 'warn'], under: ['Short', 'warn'], na: ['Not compared', 'na']};
  let out = '';
  if (tc && tc.segments) {
    const s = tc.segments, z = s.zulu || {};
    const time = (label, code, sub) => `<div class="pd-metric"><small>${label}</small><strong>${e(code || '–')}</strong><span class="pd-sub">${sub}</span></div>`;
    out += `<div class="pd-grid">${time('Out of the gate', z.out, 'Block starts')}${time('Airborne', z.off, `Taxi out ${mins(s.taxi_out_min)}`)}${time('Touchdown', z.on, `Airborne ${mins(s.airborne_min)}`)}${time('On the stand', z.in, `Taxi in ${mins(s.taxi_in_min)}`)}</div>
      <p class="pd-note">Block time ${mins(s.block_min)}. It runs from leaving the gate to the parking brake on the stand.</p>
      <div class="pd-scroll"><table class="pd-checks"><tbody>${(tc.checks || []).map(c => {
        const [word, cls] = verdict[c.status] || verdict.na;
        return `<tr><td>${e(c.label)}</td><td>${e(c.text)}</td><td><span class="pd-pill ${cls}">${word}</span></td></tr>`;
      }).join('')}</tbody></table></div>`;
  }
  if (er) {
    const gaps = (er.gaps_s || []).map(g => `${Math.round(g)} s`).join(', ');
    const seqTone = er.sequence && ['listed'].includes(er.sequence.status) ? '' : (er.sequence && ['unlisted', 'incomplete'].includes(er.sequence.status) ? 'warn' : 'na');
    out += `<h4>Engine start review</h4>
      <div class="pd-grid pd-grid-3">
        <div class="pd-metric"><small>Start order</small><strong>${e(er.order_text)}</strong><span class="pd-sub">${er.started} of ${er.expected} engines</span></div>
        <div class="pd-metric"><small>First to last</small><strong>${er.span_s == null ? '–' : `${Math.round(er.span_s)} s`}</strong><span class="pd-sub">${gaps ? `Gaps ${e(gaps)}` : 'Single start'}</span></div>
        <div class="pd-metric"><small>First engine</small><strong>${e(er.first_z || '–')}</strong><span class="pd-sub">${e(er.last_z && er.started > 1 ? `Last ${er.last_z}` : '')}</span></div>
      </div>
      <div class="pd-scroll"><table class="pd-checks"><tbody>
        <tr><td>Sequence</td><td>${e(er.sequence ? er.sequence.text : '')}</td><td><span class="pd-pill ${seqTone}">${er.sequence && er.sequence.status === 'listed' ? 'Standard' : er.sequence && er.sequence.status === 'unlisted' ? 'Not listed' : er.sequence && er.sequence.status === 'incomplete' ? 'Incomplete' : 'No standard yet'}</span></td></tr>
        ${er.timing ? `<tr><td>Start time</td><td>${e(er.timing.text)}</td><td><span class="pd-pill ${er.timing.status === 'ok' ? '' : 'warn'}">${er.timing.status === 'ok' ? 'On target' : 'Slow'}</span></td></tr>` : ''}
        ${(er.notes || []).map(n => `<tr><td>Note</td><td>${e(n)}</td><td></td></tr>`).join('')}
      </tbody></table></div>`;
  }
  return `<section class="pd-timing" data-pd-section="Timing">
    <h3>Block time and engine start</h3>${out}
    <p class="pd-note">Recorded observations only. They do not change the flight grade or your pay.</p>
  </section>`;
}
function pacLoadFactor(lf) {
  if (!lf) return '';
  const n = v => Number(v).toLocaleString('en-US');
  const bar = (label, pct, sub) => `<div class="pd-metric"><small>${label}</small><strong>${Math.round(pct)}%</strong>
    <span class="pd-lf"><i style="width:${Math.min(100, Math.max(0, pct))}%"></i></span><span class="pd-sub">${sub}</span></div>`;
  const pill = lf.over_volume ? ['Over the hold volume', 'warn'] : lf.limited_by === 'volume' ? ['Volume limited', ''] : ['Weight limited', ''];
  const why = lf.over_volume
    ? `As planned, this freight would take more space than the hold has. PAC plans loads by weight today; capping them by volume comes in a later update.`
    : lf.limited_by === 'volume'
      ? `The hold fills before the weight limit: this freight averages ${n(lf.load_density)} kg/m³, lighter than the ${n(lf.design_density)} kg/m³ at which this aircraft fills by weight and space together.`
      : `This freight averages ${n(lf.load_density)} kg/m³, denser than the ${n(lf.design_density)} kg/m³ at which this aircraft fills by weight and space together, so weight runs out first.`;
  return `<section class="pd-timing" data-pd-section="Load factor">
    <h3>Load factor</h3>
    <div class="pd-grid pd-grid-3">
      ${bar('By weight', lf.weight_pct, `${n(lf.payload_lbs)} of ${n(lf.max_payload_lbs)} lb`)}
      ${bar('By volume', lf.volume_pct, `${n(lf.volume_ft3)} of ${n(lf.capacity_ft3)} ft³`)}
      <div class="pd-metric"><small>Limited by</small><strong>${lf.limited_by === 'volume' ? 'Volume' : 'Weight'}</strong><span class="pd-sub"><span class="pd-pill ${pill[1]}">${pill[0]}</span></span></div>
    </div>
    <p class="pd-note">${why}${lf.provisional ? ' This aircraft\'s cargo volume is a provisional figure.' : ''} Shown for information: it does not change the grade, pay or revenue.</p>
  </section>`;
}
function pacDebrief(p, d = p) {
  const e = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n = v => typeof v === 'number' && Number.isFinite(v);
  const la = d.landing_analysis || {}, ta = d.takeoff_analysis || {};
  const good = [], focus = [], facts = [];
  for (const [label, points] of (d.breakdown || [])) {
    if (!(points < 0)) continue;
    const readable = pacScoreLabel(label);
    const next = /landing/i.test(label) ? 'Review the flare and touchdown trace alongside the landing load and runway position.' : /250.*(?:fl100|ias)/i.test(label) ? 'Review the speed trace below FL100 and the recorded speed-limit event.' : 'Review the corresponding event and flight trace below.';
    focus.push(`${readable}: ${points} points. ${next}`);
  }
  if (p.source === 'Manual') return '<section class="pac-debrief" data-pd-section="Summary"><h3>Flight debrief unavailable</h3><p>This manual report has no recorded flight telemetry.</p></section>';
  if (la.stable === true) good.push('Approach speed and descent stayed within PAC’s recorded stability checks.');
  if (la.stable === false) focus.push(`${la.stability_note || 'The approach exceeded PAC’s stability checks'}. Review the final approach trace and aim to settle the aircraft earlier.`);
  if (n(d.bounces)) (d.bounces === 0 ? good : focus).push(d.bounces === 0 ? 'No landing bounce was recorded.' : `${d.bounces} bounce(s) recorded. Review the touchdown sequence before your next flight.`);
  if (n(la.rate_fpm)) facts.push(`Touchdown at ${la.rate_fpm} fpm${n(la.g) ? ` and ${la.g.toFixed(2)} G` : ''}${n(la.touchdown_ft) ? `, ${la.touchdown_ft.toLocaleString()} ft past the threshold` : ''}${n(la.float_s) ? ` after ${la.float_s} s of float` : ''}.`);
  const tips = [];
  if (n(la.float_s) && la.float_s > 8) tips.push(`You floated ${la.float_s} seconds from 50 ft to touchdown. Cross the threshold at Vref + 5 kt and close the thrust by 20 ft.`);
  if (n(la.touchdown_ft) && la.touchdown_ft > 3000) tips.push(`Long landing: ${la.touchdown_ft.toLocaleString()} ft past the threshold. Aim for the touchdown zone markers, 1,000 to 2,000 ft down the runway.`);
  else if (n(la.touchdown_ft) && la.touchdown_ft < 500) tips.push(`Short: you touched down ${la.touchdown_ft.toLocaleString()} ft past the threshold. Keep the aiming point steady until the flare.`);
  if (n(la.centerline_ft) && Math.abs(la.centerline_ft) > 15) tips.push(`${Math.abs(la.centerline_ft)} ft ${la.centerline_ft > 0 ? 'right' : 'left'} of the centerline. Small rudder inputs in the flare keep you lined up.`);
  focus.push(...tips);
  if (!tips.length && n(la.touchdown_ft)) good.push(`Touched down in the zone, ${la.touchdown_ft.toLocaleString()} ft past the threshold${n(la.rate_fpm) ? `, at ${la.rate_fpm} fpm` : ''}.`);
  if (n(ta.climb_fpm)) facts.push(`Initial climb averaged ${Math.round(ta.climb_fpm).toLocaleString()} fpm between 50 and 1,000 ft.`);
  if (ta.touchback === true) focus.push('Ground contact was detected after becoming airborne. Review the takeoff trace and simulator conditions.');
  if (ta.tail_clearance_warning === true || ta.tail_strike === true) focus.push('Recorded pitch reached the estimated tail-clearance reference. Staff should review possible contact; ACARS did not measure a strike.');
  if (n(d.trip_burn_lbs) && n(d.planned_trip_lbs) && d.planned_trip_lbs > 0) {
    const pct = (d.trip_burn_lbs / d.planned_trip_lbs - 1) * 100;
    facts.push(`Trip fuel: ${Math.round(d.trip_burn_lbs).toLocaleString()} lb used versus ${Math.round(d.planned_trip_lbs).toLocaleString()} lb planned (${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%). Winds, routing and cruise level all affect this.`);
  }
  const metric = (title, value, unit, note) => `<div class="pd-metric"><small>${e(title)}</small><strong>${n(value) ? e(value.toLocaleString()) : 'Not recorded'}${n(value) ? `<span> ${e(unit)}</span>` : ''}</strong><small>${e(note)}</small></div>`;
  const list = a => a.map(s => `<p>${e(s)}</p>`).join('');
  return `<section class="pac-debrief" data-pd-section="Summary"><div class="pd-head"><div><small>PAC · FLIGHT DEBRIEF</small><h2>Your flight, explained.</h2><p>${e(p.dep)} → ${e(p.arr)} · ${e(p.flight_number)}</p></div><div class="pd-grade"><small>Flight grade</small><strong>${e(p.grade || 'Unscored')}</strong><span>${n(p.score) ? `${e(p.score)} / 100` : 'Score unavailable'}</span></div></div>
    <div class="pd-grid">${metric('Touchdown', la.rate_fpm, 'fpm', 'Recorded vertical speed')}${metric('Landing load', la.g, 'G', 'Around touchdown')}${metric('Touchdown speed', la.ias, 'kt', 'Indicated airspeed')}${metric('Takeoff roll', ta.roll_ft, 'ft', 'Recorded ground roll')}</div>
    <div class="pd-columns"><div><h3>What went well</h3>${list(good) || '<p>Not enough recorded evidence to identify strengths.</p>'}</div><div><h3>${focus.length ? 'Technique notes for next time' : 'Keep it up'}</h3>${list(focus) || '<p>Nothing to work on from this flight. Fly the next one the same way.</p>'}${focus.length && !(d.breakdown || []).some(x => x[1] < 0) ? '<p class="muted" style="font-size:13px">These notes don\'t lower your grade. They\'re what a check captain would mention after the flight.</p>' : ''}</div></div>
    ${pacFlightConfiguration(d.flight_configuration || p.flight_configuration)}
    ${pacTimingReview(d.time_checks || p.time_checks, d.engine_review || p.engine_review)}
    ${pacLoadFactor(d.load_factors || p.load_factors)}
    ${pacAfterAction(p.debrief || d.debrief)}
    ${pacShipmentDebrief(p, d)}
    <details><summary>The evidence behind the feedback</summary>${list(facts) || '<p>No detailed measurements available for this report.</p>'}<p class="pd-note">The approach check looks at your speed spread below 1,000 ft and your descent rate below 500 ft.</p></details>
    <details><summary>How this relates to your score</summary><p>What added to or took away from your score:</p>${(d.breakdown || []).map(x => `<p>${e(pacScoreLabel(x[0]))}: <b>${e(x[1])}</b></p>`).join('')}</details></section>`;
}
function pacAfterAction(db) {
  if (!db) return "";
  const e = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const rows = db.planned_actual || [], cargo = db.cargo || [], cu = db.customer || {};
  const mark = r => r.ok === true ? '<span class="aar-ok">Within plan</span>' : r.ok === false ? '<span class="aar-bad">Outside plan</span>' : '<span class="muted">Not compared</span>';
  return `<section class="aar" data-pd-section="After-action review"><h3>After-action review</h3>
    <div class="aar-cols">
      <div class="aar-box ${e(cu.tone)}"><small>${e(cu.label || 'Customer feedback')}</small><div style="font-size:13px;font-weight:600;margin:2px 0 6px">${e(String(cu.from || '').split(/,\s*/).slice(0, 3).join(' · '))}</div><p>${e(cu.text)}</p></div>
      ${db.people ? `<div class="aar-box ${e(db.people.tone)}"><small>People on board</small><p>${e(db.people.text)}</p></div>` : ""}
      <div class="aar-box"><small>Dispatcher debrief</small><p>${e(db.dispatcher)}</p>${(db.takeaways || []).length ? `<ul>${db.takeaways.map(t => `<li>${e(t)}</li>`).join("")}</ul>` : ""}</div>
    </div>
    ${rows.length ? `<h4>Planned versus actual</h4><div class="aar-wrap"><table class="aar-table"><thead><tr><th>Item</th><th class="r">Planned</th><th class="r">Actual</th><th class="r">Variance</th><th></th></tr></thead><tbody>
      ${rows.map(r => `<tr class="${r.ok === false ? "bad" : ""}"><td>${e(r.what)}</td><td class="r mono">${r.planned == null ? "–" : e(r.planned) + (r.unit && r.unit !== "h:mm" ? ` ${e(r.unit)}` : "")}</td><td class="r mono">${r.actual == null ? "Not recorded" : e(r.actual) + (r.unit && r.unit !== "h:mm" ? ` ${e(r.unit)}` : "")}</td><td class="r mono">${r.variance == null ? "–" : e(r.variance)}${r.pct != null ? ` <small>(${r.pct > 0 ? "+" : ""}${e(r.pct)}%)</small>` : ""}</td><td>${mark(r)}</td></tr>`).join("")}
    </tbody></table></div>` : ""}
    ${cargo.some(c => c.care) ? `<div class="care-box"><h4>How the sensitive freight rode</h4>${cargo.filter(c => c.care).map(c => `<div class="care-row"><div><span class="care-tag ${e(c.care.status)}">${e(c.care.label)}</span> <b>${e(c.contents)}</b> <small class="mono muted">${e(c.awb)}</small></div><ul>${c.care.log.map(l => `<li>${e(l)}</li>`).join("")}</ul></div>`).join("")}</div>` : ""}
    ${cargo.length ? `<details class="aar-cargo"><summary>Customer cargo results · ${e(db.on_time)}</summary><div class="aar-wrap"><table class="aar-table"><thead><tr><th>Air waybill</th><th>Customer journey</th><th>Commodity</th><th class="r">Weight</th><th>Delivery</th><th class="r">Charges</th></tr></thead><tbody>
      ${cargo.map(c => `<tr><td class="mono">${trackAwb(c.awb)}</td><td>${e(c.shipper)} → ${e(c.consignee)}</td><td>${e(c.contents)}</td><td class="r mono">${c.weight_lbs != null ? Number(c.weight_lbs).toLocaleString() + " lb" : "–"}</td><td><b class="${/LATE|NOT|HELD/.test(c.status) ? "aar-bad" : "aar-ok"}">${e(c.status)}</b>${c.delivered ? `<br><small class="mono">${e(c.delivered)}</small>` : ""}${c.care ? `<br><span class="care-tag ${e(c.care.status)}">${e(c.care.label)}</span>` : ""}</td><td class="r mono">${c.charges != null ? "$" + Number(c.charges).toLocaleString("en-US", { maximumFractionDigits: 0 }) : "–"}</td></tr>`).join("")}
    </tbody></table></div></details>` : ""}
  </section>`;
}
function pacShipmentDebrief(p, d) {
  if(d?.training || p.training)return `<section class="pd-shipment" data-pd-section="Shipment"><h3>Company-funded training</h3><p>Training ballast only. No commercial shipment, customer handover, profit share, reward points or campaign cargo credit.</p><p>${(d?.training||p.training).mode==='dedicated'?'Dedicated session: operational fleet and normal pilot station unchanged.':'Fleet checkride: normal aircraft and pilot position tracking applies.'}</p><p>Accepted attempts count toward career hours and flight count and receive standard flight pay plus applicable skill or gear bonuses. A failed checkride does not grant a qualification.</p></section>`;
  const e = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n = v => typeof v === 'number' && Number.isFinite(v);
  const delivered = ['Delivered', 'Delivered late'].includes(p.status);
  const pending = p.review_status === 'Pending';
  const deadline = d.urgent?.deliver_by, arrived = d.oooi?.in;
  let timing = 'No delivery deadline recorded.', comparison = '';
  if (n(deadline) && n(arrived) && delivered) {
    const seconds = arrived - deadline, minutes = Math.abs(seconds / 60);
    timing = seconds <= 0 ? 'Delivery deadline met' : 'Delivery deadline missed';
    comparison = `On block ${minutes < 1 ? 'less than 1' : Math.round(minutes)} min ${seconds <= 0 ? 'before' : 'after'} the deadline.`;
  } else if (p.status === 'Delivered late') timing = 'Late under PAC’s delivery rules';
  else if (delivered) timing = 'Within PAC’s delivery allowance';
  else if (p.status === 'Diverted') timing = 'Diverted — intended delivery not completed';
  else if (p.status === 'Failed') timing = 'Delivery not completed';
  if (!comparison && n(p.block_min) && n(d.target_block_min) && d.target_block_min > 0) {
    const delta = Math.round(p.block_min - d.target_block_min);
    comparison = `Block time ${Math.abs(delta)} min ${delta < 0 ? 'shorter' : 'longer'} than planned.`;
  }
  const weight = n(p.payload_lbs) ? p.payload_lbs : d.loaded_lbs;
  const risk = (d.breakdown || []).some(x => /structural damage/i.test(x[0]) && x[1] < 0);
  const cargo = (p.debrief || d.debrief || {}).cargo || [];
  const to = [...new Set(cargo.map(c => c.consignee).filter(Boolean))];
  const inZ = n(arrived) ? new Date(arrived * 1000).toISOString().slice(11, 16).replace(':', '') + 'Z' : '';
  const handover = delivered
    ? `Handed over to ${to.length ? to.slice(0, 3).map(e).join(', ') + (to.length > 3 ? ` and ${to.length - 3} more` : '') : 'the consignee'}${inZ ? ` after on-block at ${inZ}` : ''}.`
    : p.status === 'Diverted' ? 'Held at the diversion airport until it can be flown on.' : 'Not delivered on this flight.';
  return `<section class="pd-shipment" data-pd-section="Shipment"><small>SHIPMENT DEBRIEF</small><h3>${e(p.mission_title || 'Your cargo assignment')}</h3><p><b>${delivered ? 'Delivered' : e(p.status || 'Arrival not confirmed')}</b> · ${e(timing)}${n(weight) ? ` · ${e(weight.toLocaleString())} lb` : ''}${pending ? ' · Awaiting staff review' : ''}</p><p>${handover}</p>${risk ? `<p><b>Handling inspection requested</b>: the flight report flagged possible structural damage, so the ground team will check the freight.</p>` : ''}${comparison ? `<details><summary>Timing</summary><p>${e(comparison)}</p></details>` : ''}</section>`;
}
function pacScoreLabel(label) {
  const text = String(label ?? '');
  const speed = text.match(/250\s*kt.*fl100.*ias\s*(\d+)/i);
  return speed ? `Recorded ${speed[1]} kt IAS below FL100` : text;
}
function pacReportNav(root) {
  if (!root || root.querySelector('.pd-nav')) return;
  const sections = [...root.querySelectorAll('[data-pd-section]')];
  for (const h of root.querySelectorAll('h3')) {
    const name = h.textContent.trim();
    if (['Landing','Takeoff','Replay'].includes(name)) {h.dataset.pdSection=name;sections.push(h);}
  }
  const nav=document.createElement('nav');nav.className='pd-nav';nav.setAttribute('aria-label','Flight report sections');
  for (const name of ['Summary','Configuration','Timing','Load factor','Shipment','Landing','Takeoff','Replay']) {
    const target=sections.find(x=>x.dataset.pdSection===name);if(!target)continue;
    const b=document.createElement('button');b.type='button';b.textContent=name;
    b.onclick=()=>{target.scrollIntoView({block:'start',behavior:'auto'});target.tabIndex=-1;target.focus({preventScroll:true});};nav.appendChild(b);
  }
  root.prepend(nav);
}

{const style=document.createElement("style");style.textContent=".pac-debrief{border:1px solid var(--line,#d8dce3);border-top:4px solid #c80000;border-radius:8px;background:var(--white,#fff);color:var(--ink,#20252b);padding:24px;margin:18px 0;font:15px/1.6 system-ui}.pd-head{display:flex;justify-content:space-between;gap:24px}.pd-head h2{font-size:30px;margin:5px 0}.pd-head p{margin:4px 0 18px}.pd-head small{font-weight:700;letter-spacing:1px;color:var(--ink,#20252b)}.pd-grade{display:flex;flex-direction:column;align-items:center;min-width:140px}.pd-grade strong{font-size:48px;line-height:1.2}.pd-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.pd-metric{border:1px solid var(--line,#d8dce3);padding:16px;border-radius:6px;display:flex;flex-direction:column}.pd-metric strong{font-size:25px}.pd-metric strong span{font-size:13px;font-weight:400}.pd-columns{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin:20px 0}.pac-debrief h3{font-size:17px;margin:8px 0}.pac-debrief details{border-top:1px solid var(--line,#d8dce3);padding:14px 0}.pac-debrief summary{cursor:pointer;font-weight:700}.pd-note{color:var(--steel,#586575);font-size:13px}.pac-debrief p{max-width:85ch}@media(max-width:700px){.pd-grid{grid-template-columns:1fr 1fr}.pd-columns{grid-template-columns:1fr;gap:8px}.pd-head{flex-direction:column}.pd-grade{align-items:flex-start}.pac-debrief{padding:16px}}\n.pd-shipment{padding:22px;background:var(--paper,#f6f7f9);border-left:4px solid #c80000;margin:22px 0}.pd-shipment>small{font-weight:700;letter-spacing:1px;color:var(--ink,#20252b)}\n\n.pd-nav{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 20px}.pd-nav button{background:var(--white,#fff);color:var(--ink,#20252b);border:1px solid var(--line,#ddd);padding:9px 14px;cursor:pointer;border-radius:4px;font:inherit}.pd-nav button:hover,.pd-nav button:focus,.pd-nav button:focus-visible,.pd-nav button:active{outline:2px solid #c80000;color:var(--ink,#20252b)!important;background:var(--white,#fff)!important}.pd-shipment{padding:16px 20px}.pd-shipment details{padding-bottom:0}[data-pd-section]{scroll-margin-top:16px}.pd-configuration{border-top:1px solid var(--line,#d8dce3);padding-top:18px;margin:20px 0}.pd-configuration .pd-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.pd-configuration .pd-metric strong{font-size:19px}.pd-light-list{display:grid;gap:2px;margin-top:7px}.pd-light-list>div{display:flex;justify-content:space-between;gap:12px;font-size:13px}.pd-light-list b{font-weight:600}.pd-configuration .pd-note{margin:12px 0 0}@media(max-width:700px){.pd-configuration .pd-grid{grid-template-columns:1fr}}\n.pd-timing{border-top:1px solid var(--line,#d8dce3);padding-top:18px;margin:20px 0}.pd-timing h4{font-size:16px;margin:22px 0 8px}.pd-timing .pd-metric strong{font-size:21px}.pd-sub{font-size:13px;color:var(--steel,#586575)}.pd-grid-3{grid-template-columns:repeat(3,minmax(0,1fr))}.pd-scroll{overflow-x:auto}.pd-checks{width:100%;border-collapse:collapse;margin-top:12px}.pd-checks td{padding:9px 10px;border-top:1px solid var(--line,#d8dce3);vertical-align:top;font-size:14px}.pd-checks td:first-child{font-weight:600;white-space:nowrap}.pd-checks td:last-child{text-align:right;white-space:nowrap}.pd-pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:700;background:#e6f4ea;color:#17623a}.pd-pill.warn{background:#fff1dc;color:#8a4b00}.pd-pill.na{background:#eceff3;color:#586575}.pd-lf{display:block;height:6px;border-radius:3px;background:var(--line,#e3e6eb);margin:6px 0 4px;overflow:hidden}.pd-lf i{display:block;height:100%;background:#C80000}.pd-timing .pd-note{margin:12px 0 0}@media(max-width:700px){.pd-grid-3{grid-template-columns:1fr}}\n";document.head.appendChild(style);}

function pacParkedInit() {
  if (document.getElementById('parkedControls')) return;
  const root=document.getElementById('liveRoot'), live=S.live;
  live.parkedLayer=L.layerGroup().addTo(live.base.map);live.airportCache={};
  const el=document.createElement('section');el.id='parkedControls';el.innerHTML=`<div class="row"><label><input id="pmFlying" type="checkbox" checked> Live flights</label><label><input id="pmParked" type="checkbox" checked> Parked fleet</label><label>Aircraft <select id="pmType"><option value="">All types</option>${Object.keys(S.fleet||{}).filter(k=>!S.fleet[k].retired).map(k=>`<option value="${esc(k)}">${esc(S.fleet[k].name||k)}</option>`).join('')}</select></label><label><input id="pmQualified" type="checkbox"> My qualifications</label><label><input id="pmAvailable" type="checkbox"> Available only</label><button class="btn ghost small" id="pmFit">Fit parked fleet</button></div><p class="muted" id="pmStatus" role="status">Loading parked fleet…</p><p class="muted">Numbered circles show aircraft at their recorded airport, not a specific parking stand. Aircraft reporting to ACARS appear as plane symbols.</p><div id="pmStations"></div>`;
  root.querySelector('.live-wrap').before(el);
  for(const id of ['pmType','pmQualified','pmAvailable','pmParked'])document.getElementById(id).onchange=()=>pacParkedRender();
  document.getElementById('pmFlying').onchange=e=>{if(e.target.checked)live.layer.addTo(live.base.map);else live.base.map.removeLayer(live.layer);document.getElementById('liveList').hidden=!e.target.checked;globeSync();};
  document.getElementById('pmFit').onclick=()=>liveFit(live.parkedPoints||[]);
}
async function pacParkedRefresh(force=false) {
  const live=S.live;if(!live || live.parkedBusy)return;
  pacParkedInit();
  if(!force && live.parkedAt && Date.now()-live.parkedAt<30000){pacParkedRender();return;}
  live.parkedBusy=true;
  try {
    const frames=await api('/api/airframes');if(S.live!==live)return;
    live.parkedFrames=frames;S.airframes=frames;
    const codes=[...new Set(frames.map(a=>a.location).filter(Boolean))];
    for(let i=0;i<codes.length;i+=3){await Promise.all(codes.slice(i,i+3).map(async code=>{if(live.airportCache[code])return;try{const a=await api('/api/stations/'+encodeURIComponent(code));if(Number.isFinite(a.lat)&&Number.isFinite(a.lon))live.airportCache[code]=a;}catch(e){/* listed below with coordinates unavailable */}}));}
    live.parkedAt=Date.now();live.parkedError='';pacParkedRender();
  }catch(e){live.parkedError='Fleet refresh failed. Displayed positions may be out of date.';pacParkedRender();}
  finally{live.parkedBusy=false;}
}
function pacParkedGroups(frames,flights,type,qualified,available) {
  const active=new Set((flights||[]).map(f=>f.reg).filter(Boolean));const groups={};
  for(const a of frames||[]){if(active.has(a.reg)||['Flying','Airborne','In flight'].includes(a.status))continue;if(type&&a.type!==type)continue;if(available&&a.status!=='Available')continue;if(qualified&&!boardQualified({id:'parked-fleet',category:'Cargo'},a.type))continue;(groups[a.location||'Unknown']||=[]).push(a);}
  return groups;
}
function pacParkedRender() {
  const live=S.live;if(!live?.parkedLayer)return;
  const visible=document.getElementById('pmParked').checked;
  live.parkedLayer.clearLayers();live.parkedPoints=[];
  const groups=pacParkedGroups(live.parkedFrames,live.flights,document.getElementById('pmType').value,document.getElementById('pmQualified').checked,document.getElementById('pmAvailable').checked);
  live.parkedGroups=groups;const codes=Object.keys(groups).sort();let missing=0;
  const list=document.getElementById('pmStations');list.hidden=!visible;
  list.innerHTML=visible?codes.map(code=>`<button class="btn ghost small" data-parked-station="${esc(code)}">${esc(code)} · ${groups[code].length}</button>`).join(''):'';
  for(const code of codes){const a=live.airportCache[code];if(!a){missing++;continue;}live.parkedPoints.push([a.lat,a.lon]);if(!visible)continue;
    const marker=L.marker([a.lat,a.lon],{icon:L.divIcon({className:'pm-marker',html:`<span>${groups[code].length}</span>`,iconSize:[34,34],iconAnchor:[17,17]})}).addTo(live.parkedLayer);
    marker.bindTooltip(`${esc(code)} · ${groups[code].length} aircraft`);marker.on('click',()=>pacParkedStation(code,groups[code]));
  }
  list.querySelectorAll('[data-parked-station]').forEach(b=>b.onclick=()=>{const a=live.airportCache[b.dataset.parkedStation];if(a)liveFocus(a.lat,a.lon,6);pacParkedStation(b.dataset.parkedStation,groups[b.dataset.parkedStation]);});
  document.getElementById('pmStatus').textContent=live.parkedError || `${Object.values(groups).reduce((n,a)=>n+a.length,0)} aircraft at ${codes.length} airports${live.parkedAt?' · Updated '+new Date(live.parkedAt).toLocaleTimeString():''}${missing?' · '+missing+' airports lack map coordinates; use their buttons above.':''}${!codes.length?' · No aircraft match these filters.':''}`;
  globeSync();
}
function pacParkedStation(code,frames){
  let dlg=document.getElementById('pmDialog');if(!dlg){dlg=document.createElement('dialog');dlg.id='pmDialog';document.body.append(dlg);}
  const a=S.live.airportCache[code],here=S.me?.location?.icao;
  dlg.innerHTML=`<div class="row"><h2>${esc(code)} · ${esc(a?.city||a?.name||'Recorded aircraft location')}</h2><button class="btn ghost small" id="pmClose">Close</button></div><p>Availability is checked again when booking or moving an aircraft.</p>${code!==here&&code!=='Unknown'?'<button class="btn small" id="pmTravel">Travel here · review quote</button>':''}<div>${frames.map((f,i)=>`<article class="pm-airframe"><h3>${esc(f.reg)} · ${esc(S.fleet[f.type]?.name||f.type)}</h3><p>${esc(reservationSummary(f))} · ${boardQualified({id:'parked-fleet',category:'Cargo'},f.type)?'Qualified under current booking rules':'Check qualifications'}${f.name?' · '+esc(f.name):''}</p><div class="row"><button class="btn ghost small" data-pm-flights="${i}">Find departures here</button>${f.status==='Available'&&code!==here&&code!=='Unknown'?`<button class="btn small" data-pm-ferry="${i}">Deliver to my station · quote</button>`:''}<button class="btn ghost small" data-pm-history="${i}">Aircraft details</button></div></article>`).join('')}</div>`;
  dlg.querySelector('#pmClose').onclick=()=>dlg.close();if(dlg.querySelector('#pmTravel'))dlg.querySelector('#pmTravel').onclick=()=>{dlg.close();openJumpseat(code);};
  dlg.querySelectorAll('[data-pm-flights]').forEach(b=>b.onclick=()=>{const f=frames[+b.dataset.pmFlights];dlg.close();resetMissionFilters();S.board='all';S.acFilter=f.type;S.parkedOrigin=code;show('missions');renderMissions();});
  dlg.querySelectorAll('[data-pm-ferry]').forEach(b=>b.onclick=()=>{dlg.close();confirmReposition(frames[+b.dataset.pmFerry].reg,()=>pacParkedRefresh(true));});
  dlg.querySelectorAll('[data-pm-history]').forEach(b=>b.onclick=()=>{dlg.close();openAirframe(frames[+b.dataset.pmHistory].reg);});
  if(!dlg.open)dlg.showModal();
}
{const style=document.createElement('style');style.textContent=`#parkedControls{background:var(--white);color:var(--ink);border:1px solid var(--line);padding:16px;margin-bottom:16px}#parkedControls .row{gap:16px;flex-wrap:wrap}#pmStations{display:flex;gap:8px;flex-wrap:wrap}#pmStations[hidden]{display:none}.pm-marker span{display:grid;place-items:center;width:32px;height:32px;border-radius:50%;background:#176782;color:white;border:2px solid white;font-weight:bold;box-shadow:0 1px 5px #333}#pmDialog{width:min(740px,92vw);max-height:85vh;overflow:auto;background:var(--white);color:var(--ink);border:1px solid var(--line);padding:24px}.pm-airframe{border-top:1px solid var(--line);padding:12px 0}.pm-airframe .row{flex-wrap:wrap;gap:8px}`;document.head.appendChild(style);}

VIEWS.push("crewplans");
async function loadCrewPlans(){
 const root=document.getElementById('crewPlansRoot'),pilot=S.me?.id;if(!pilot)return;
 root.innerHTML='<p role="status">Loading crew plans…</p>';
 try{const d=await api('/api/crew-plans');if(S.me?.id!==pilot)return;
 root.innerHTML=`<div class="profile-bar"><h1>Fly together</h1><button class="btn ghost" id="cpRefresh">Refresh</button></div><p>Find a second seat or arrange a flight with other PAC pilots.</p><div class="notice"><b>Planning only — no aircraft reservation.</b> Book through Missions as usual. This board does not award hours, pay or qualifications. Shared-cockpit pilots must arrange compatible simulator/add-on software and agree their roles.</div><details class="cp-create"><summary>Post a flight</summary><form id="cpForm"><div class="cp-grid"><label>Departure ICAO<input name="dep" maxlength="4" required placeholder="KCVG"></label><label>Arrival ICAO<input name="arr" maxlength="4" required placeholder="KMIA"></label><label>Aircraft type<select name="aircraft">${Object.keys(S.fleet).filter(k=>!S.fleet[k].retired).map(k=>`<option value="${esc(k)}">${esc(S.fleet[k].name||k)}</option>`).join('')}</select></label><label>Departure date and time (UTC)<input name="departure" type="datetime-local" required></label><label>Flight format<select name="mode"><option value="shared">Shared cockpit · one joining pilot</option><option value="group">Separate aircraft · group flight</option></select></label><label>Joining places (group flights)<input name="capacity" type="number" min="1" max="10" value="3" required></label><label>Simulator<input name="simulator" maxlength="60" required placeholder="MSFS 2024 / X-Plane 12"></label><label>Aircraft add-on / shared-cockpit setup<input name="addon" maxlength="100" placeholder="Required for shared cockpit"></label><label>Discord username (optional)<input name="contact" maxlength="80"><small>Only what you enter here is shared with signed-in pilots.</small></label><label>Notes<textarea name="note" maxlength="800" placeholder="Role, briefing time, voice channel or compatibility notes"></textarea></label></div><button class="btn" type="submit">Post flight</button><p id="cpError" role="alert"></p></form></details><h2>Upcoming flights</h2><div class="cp-grid">${d.plans.filter(x=>!x.expired&&!['cancelled','finished'].includes(x.state)).map(cpCard).join('')||'<p>No upcoming flights yet. Be the first to invite the crew.</p>'}</div><details><summary>My recent closed or past posts</summary>${d.plans.filter(x=>x.expired||['cancelled','finished'].includes(x.state)).map(cpCard).join('')||'<p>No past posts.</p>'}</details>`;
 fillCrewMissionDraft();
 focusCrewPost();
 root.querySelector('#cpRefresh').onclick=loadCrewPlans;
 root.querySelector('#cpForm').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,b=Object.fromEntries(new FormData(f));b.departure=Date.parse(b.departure+'Z')/1000;b.capacity=Number(b.capacity);const btn=f.querySelector('button');btn.disabled=true;try{await api('/api/crew-plans',{method:'POST',body:b});loadCrewPlans();}catch(err){root.querySelector('#cpError').textContent=err.message;btn.disabled=false;}};
 root.querySelectorAll('[data-cp-action]').forEach(b=>b.onclick=async()=>{let contact='';if(b.dataset.cpAction==='join'){contact=prompt('Optional Discord username to share with signed-in pilots (leave blank to omit):','');if(contact===null)return;}if(['cancel','finish'].includes(b.dataset.cpAction)&&!confirm('Close this crew-planning post? This does not change any flight booking.'))return;b.disabled=true;try{await api(`/api/crew-plans/${b.dataset.cpId}/${b.dataset.cpAction}`,{method:'POST',body:{contact}});loadCrewPlans();}catch(e){toast(e.message);b.disabled=false;}});
 }catch(e){if(S.me?.id===pilot){root.innerHTML=`<p role="alert">${esc(e.message)}</p><button class="btn" id="cpRetry">Retry</button>`;root.querySelector('#cpRetry').onclick=loadCrewPlans;}}
}
function cpCard(p){
 const joined=p.members.some(m=>m.pilot===S.me.id),closed=p.expired||['cancelled','finished'].includes(p.state),full=p.members.length>=p.capacity;
 const button=(a,t)=>`<button class="btn ghost small" data-cp-id="${p.id}" data-cp-action="${a}">${t}</button>`;
 const status=p.expired&&!['cancelled','finished'].includes(p.state)?'Departure passed':p.state==='complete'?'Crew complete':p.state==='open'?(full?'Places filled':'Looking for crew'):p.state;
 return `<article class="cp-card" data-crew-post="${p.id}"><small>${p.mode==='shared'?'SHARED COCKPIT':'GROUP FLIGHT · SEPARATE AIRCRAFT'}</small><h2>${esc(p.dep)} → ${esc(p.arr)}</h2><b>${new Date(p.departure*1000).toISOString().slice(0,16).replace('T',' ')} UTC</b><p>${esc(S.fleet[p.aircraft]?.name||p.aircraft)}<br>${esc(p.simulator)}${p.addon?' · '+esc(p.addon):''}</p><span class="tag">${esc(status)}</span><p>Organizer: ${esc(p.owner_name)} · ${esc(p.owner)}${p.contact?' · Discord: '+esc(p.contact):''}</p>${p.note?`<p>${esc(p.note)}</p>`:''}<p>${p.members.length} / ${p.capacity} joining places</p>${p.members.map(m=>`<p>${esc(m.name)} · ${esc(m.pilot)}${m.contact?' · Discord: '+esc(m.contact):''}</p>`).join('')}<div class="row">${joined?button('leave','Leave flight'):!closed&&p.state==='open'&&!full&&p.owner!==S.me.id?button('join','Join flight'):''}${p.can_manage&&!['cancelled','finished'].includes(p.state)?`${!p.expired?button(p.state==='open'?'complete':'reopen',p.state==='open'?'Mark crew complete':'Reopen places'):''}${button('finish','Mark finished')}${button('cancel','Cancel post')}`:''}</div></article>`;
}
{const style=document.createElement('style');style.textContent='.cp-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:18px 0}.cp-card,.cp-create{background:var(--white);color:var(--ink);border:1px solid var(--line);border-top:3px solid var(--red);padding:22px;margin:16px 0}.cp-card p{overflow-wrap:anywhere}.cp-card .row{flex-wrap:wrap;gap:8px}.cp-grid label{display:flex;flex-direction:column;gap:6px}.cp-grid input,.cp-grid select,.cp-grid textarea{width:100%;min-width:0;padding:10px;box-sizing:border-box;background:var(--white);color:var(--ink);border:1px solid var(--line)}@media(max-width:700px){.cp-grid{grid-template-columns:1fr}}';document.head.append(style);const nav=document.createElement('button');nav.dataset.view='crewplans';nav.textContent='Fly together';nav.onclick=()=>show('crewplans');document.querySelector('#navGroup2').append(nav);const section=document.createElement('section');section.className='view';section.id='view-crewplans';section.hidden=true;section.innerHTML='<div id="crewPlansRoot"></div>';document.querySelector('#view-pilots').parentElement.append(section);}

function reservationSummary(a){
 const r=a.reservation;
 if(a.liveOperation)return `${a.liveOperation.on_ground?'Operating on the ground':'Currently flying'} · ${a.liveOperation.flight}${r?' · '+r.pilot_name+' · '+r.dep+' → '+r.arr:''}`;
 if(r)return `Reserved for ${r.pilot_name || r.pilot_id} · ${r.pilot_id} · ${r.flight || 'Flight'} · ${r.dep || '?'} → ${r.arr || '?'}`;
 return a.status==='Booked'?'Reserved for a flight · booking details unavailable':a.status==='Available'?'Available':`Unavailable · ${a.status || 'check with Dispatch'}`;
}
function planSelectedWithCrew(){
 const m=S.selected;if(!m)return;
 S.crewDraft={dep:m.origin.icao,arr:m.destination.icao,aircraft:S.aircraft || m.aircraft?.[0],note:`Planning ${m.id}: ${m.title}. This post does not reserve an aircraft.`};
 show('crewplans');
}
function fillCrewMissionDraft(){
 const d=S.crewDraft,f=document.getElementById('cpForm');if(!d||!f)return;
 for(const k of ['dep','arr','aircraft','note'])if(f.elements[k])f.elements[k].value=d[k]||'';
 f.closest('details').open=true;S.crewDraft=null;f.elements.departure.focus();
}

function crewCalendarText(plan, now=new Date()) {
 const escape=s=>String(s??'').replace(/\\/g,'\\\\').replace(/\r\n|\r|\n/g,'\\n').replace(/;/g,'\\;').replace(/,/g,'\\,');
 const stamp=d=>d.toISOString().replace(/[-:]/g,'').replace(/\.\d{3}Z$/,'Z');
 const fold=line=>{let rows=[],part='',size=0;for(const ch of line){const bytes=new TextEncoder().encode(ch).length;if(size+bytes>75){rows.push(part);part=' ';size=1;}part+=ch;size+=bytes;}rows.push(part);return rows.join('\r\n');};
 return ['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Pagani Air Cargo//Crew Planning//EN','CALSCALE:GREGORIAN','BEGIN:VEVENT',`UID:pac-crew-${Number(plan.id)}@pac-va.com`,`DTSTAMP:${stamp(now)}`,`DTSTART:${stamp(new Date(plan.departure*1000))}`,`SUMMARY:${escape('PAC crew flight: '+plan.dep+' to '+plan.arr)}`,`LOCATION:${escape(plan.dep)}`,`DESCRIPTION:${escape((plan.mode==='shared'?'Shared cockpit':'Group flight')+' · '+plan.aircraft+'\nCheck Fly together for changes: https://pac-va.com/#crewplans\nPlanning only; this calendar entry does not join the crew or reserve an aircraft. Departure time only; duration is not specified.')}`,'URL:https://pac-va.com/#crewplans','END:VEVENT','END:VCALENDAR'].map(fold).join('\r\n')+'\r\n';
}
function downloadCrewCalendar(plan){
 const blob=new Blob([crewCalendarText(plan)],{type:'text/calendar;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`PAC-crew-${Number(plan.id)}.ics`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function loadDashboardCrew(root){
 const pilot=S.me?.id,token={};root._crewRequest=token;
 const current=()=>root.isConnected&&S.me?.id===pilot&&root._crewRequest===token;
 root.innerHTML='<h3>Upcoming crew flights</h3><p role="status">Checking the crew board…</p>';
 try{const data=await api('/api/crew-plans');if(!current())return;
 const plans=data.plans.filter(p=>p.departure>data.now&&!['cancelled','finished'].includes(p.state)).sort((a,b)=>a.departure-b.departure).slice(0,3);
 const timezone=Intl.DateTimeFormat().resolvedOptions().timeZone||'your device timezone';
 root.innerHTML=`<div class="row" style="justify-content:space-between;flex-wrap:wrap"><div><div class="kicker">Fly together</div><h3>Upcoming crew flights</h3></div><button class="btn ghost small" data-crew-board>View crew board →</button></div><p class="muted">Local times use ${esc(timezone)}. Crew plans do not reserve aircraft.</p><div class="dc-grid">${plans.map(p=>{const joined=p.members.some(m=>m.pilot===pilot),owner=p.owner===pilot,places=Math.max(0,p.capacity-p.members.length),open=p.state==='open'&&places>0;return `<article class="dc-flight"><strong>${esc(p.dep)} → ${esc(p.arr)}</strong><p>${esc(S.fleet[p.aircraft]?.name||p.aircraft)}<br>${p.mode==='shared'?'Shared cockpit':'Separate aircraft · group flight'}</p><time datetime="${new Date(p.departure*1000).toISOString()}"><b>${esc(new Date(p.departure*1000).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}))} local</b><br>${new Date(p.departure*1000).toISOString().slice(0,16).replace('T',' ')} UTC</time><p>${owner?'You’re organizing':joined?'You’re joining':open?places+' joining place'+(places===1?'':'s')+' open':'Crew complete / places filled'}</p><div class="row"><button class="btn ghost small" data-crew-view="${p.id}">View flight</button>${!joined&&!owner&&open?`<button class="btn small" data-crew-join="${p.id}">Join</button>`:''}<button class="btn ghost small" data-crew-calendar="${p.id}">Add to calendar</button></div></article>`;}).join('')||'<p>No upcoming crew flights yet. Post a flight and invite the crew.</p>'}</div><p class="brief-note">Calendar downloads are a snapshot, not a live subscription. Check the crew board for changes before departure.</p>`;
 root.querySelector('[data-crew-board]').onclick=()=>show('crewplans');
 root.querySelectorAll('[data-crew-view]').forEach(b=>b.onclick=()=>{S.crewFocusId=Number(b.dataset.crewView);show('crewplans');});
 root.querySelectorAll('[data-crew-calendar]').forEach(b=>b.onclick=()=>downloadCrewCalendar(plans.find(p=>p.id===Number(b.dataset.crewCalendar))));
 root.querySelectorAll('[data-crew-join]').forEach(b=>b.onclick=async()=>{const contact=prompt('Optional Discord username shared with signed-in pilots (leave blank to omit):','');if(contact===null)return;b.disabled=true;try{await api(`/api/crew-plans/${b.dataset.crewJoin}/join`,{method:'POST',body:{contact}});if(current())loadDashboardCrew(root);}catch(e){toast(e.message);if(current())loadDashboardCrew(root);}});
 setTimeout(()=>{if(current()&&!document.getElementById('view-dashboard')?.hidden)loadDashboardCrew(root);},60000);
 }catch(e){if(!current())return;root.innerHTML='<h3>Upcoming crew flights</h3><p role="status">Crew plans could not be loaded. Your flight briefing is still available.</p><button class="btn ghost small">Retry crew board</button>';root.querySelector('button').onclick=()=>loadDashboardCrew(root);}
}
function focusCrewPost(){const id=S.crewFocusId;if(!id)return;const el=document.querySelector(`[data-crew-post="${Number(id)}"]`);S.crewFocusId=null;if(el){el.scrollIntoView({block:'center'});el.tabIndex=-1;el.focus({preventScroll:true});}else toast('That flight is no longer on the upcoming board.');}
{const style=document.createElement('style');style.textContent='.dc-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.dc-flight{border:1px solid var(--line);border-top:3px solid var(--red);padding:16px;overflow-wrap:anywhere}.dc-flight .row{flex-wrap:wrap;gap:8px}.dc-flight strong{font-size:20px}.dc-flight time{font-size:13px}@media(max-width:1000px){.dc-grid{grid-template-columns:1fr}}';document.head.append(style);}

function trainingPolicyHTML(){return `<p><b>Checkrides are company-funded and are not restricted to KCVG.</b> Choose a dedicated training session (recommended) or an available fleet aircraft at its current airport.</p><ul><li>Dedicated sessions use a temporary training aircraft. Your normal station and operational fleet remain unchanged.</li><li>Fleet sessions reserve the selected aircraft and include free pilot travel when booked. After the flight, the aircraft stays where it landed. Existing reservations are protected.</li><li>Your home base comes first in the list of training airports. Once you pass the line checkride, PAC moves you to the home base you chose when you applied, free of charge, so your career starts there.</li><li>Accepted checkride attempts count toward career hours and flight count and receive standard flight pay plus applicable skill or gear bonuses. A failed attempt does not grant a qualification.</li><li>Checkrides earn no profit share, commercial cargo credit or reward points. Retakes are free.</li></ul><p>Generate a matching SimBrief plan, review and sign the dispatch release, then track the complete checkride in PAC ACARS. This training option does not unlock other flights before qualification.</p>`}
async function openTraining(course='PAC001'){
 if(!S.me){openSignIn('Sign in to start a checkride.');return;}
 if(S.booking){toast('Finish or cancel your current booking before starting a checkride.');show('bids');return;}
 document.getElementById('trainingDialog')?.remove();
 const dlg=document.createElement('dialog');dlg.id='trainingDialog';dlg.setAttribute('aria-labelledby','trainingTitle');dlg.style.cssText='width:min(760px,94vw);max-height:90vh;overflow:auto;border:1px solid var(--line);padding:24px;background:var(--white);color:var(--ink)';
 dlg.innerHTML='<style>#trainingForm{display:grid;grid-template-columns:1fr 1fr;gap:16px}#trainingForm label{display:flex;flex-direction:column;gap:7px;font-weight:600;min-width:0}#trainingForm select{width:100%;min-height:44px;padding:10px;border:1px solid var(--line);background:var(--white);color:var(--ink);font:inherit;font-weight:400}#trainingForm p,#trainingForm button{grid-column:1/-1;margin:0}#trainingDialog::backdrop{background:rgba(0,0,0,.5)}@media(max-width:600px){#trainingForm{grid-template-columns:1fr}}</style><div class="row" style="justify-content:space-between"><h2 id="trainingTitle">Start checkride</h2><button type="button" class="btn ghost small" id="trainingClose">Close</button></div><div id="trainingContent" aria-live="polite">Loading current training options…</div>';
 document.body.append(dlg);dlg.querySelector('#trainingClose').onclick=()=>dlg.close();dlg.addEventListener('close',()=>dlg.remove());dlg.showModal();
 const root=dlg.querySelector('#trainingContent');
 try{
 const data=await api('/api/training/options');if(!dlg.isConnected)return;
 root.innerHTML=`<p class="notice"><b>$0 to qualify.</b> No paid ferry or jumpseat required. Choose where and how you train.</p><form id="trainingForm"><label>Checkride<select name="course">${data.courses.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('')}</select></label><label>Training option<select name="mode"><option value="dedicated">Dedicated training session — recommended</option><option value="fleet">Use an available fleet aircraft</option></select></label><p id="trainingModeHelp"></p><label>Aircraft type<select name="aircraft"></select></label><label>Departure / aircraft<select name="choice"></select></label><p id="trainingRules"></p><button class="btn" type="submit">Review checkride →</button></form><div id="trainingReview" aria-live="polite"></div><details style="margin-top:20px"><summary>PAC checkride policy</summary>${trainingPolicyHTML()}</details>`;
 const form=root.querySelector('form'),f=form.elements,review=root.querySelector('#trainingReview');let choices=[],revision=0;
 if(data.courses.some(c=>c.id===course))f.course.value=course;
 const refresh=(types=false)=>{
 revision++;review.innerHTML='';const c=data.courses.find(c=>c.id===f.course.value);
 if(types)f.aircraft.innerHTML=c.types.map(t=>`<option value="${esc(t)}">${esc(S.fleet[t]?.name||t)}</option>`).join('');
 choices=c.choices.filter(x=>x.spec.mode===f.mode.value&&x.spec.aircraft===f.aircraft.value);
 f.choice.innerHTML=choices.map((x,i)=>`<option value="${i}">${esc(x.spec.origin)} → ${esc(x.destination)}${x.spec.reg?' · '+esc(x.spec.reg):' · temporary training aircraft'}</option>`).join('');
 if(!choices.length)f.choice.innerHTML='<option>No available options — try another type or dedicated training</option>';
 form.querySelector('[type=submit]').disabled=!choices.length;
 root.querySelector('#trainingModeHelp').textContent=f.mode.value==='dedicated'?'Train at a supported airport without moving your pilot or any fleet aircraft. Start your simulator at the departure airport shown.':'Available aircraft only. PAC pays your positioning travel when you book; the aircraft stays reserved for you. Availability is checked again at booking.';
 const r=c.standard,approach=c.id==='PAC001'?'':` Type checkrides also require an approach within ${r.max_approach_speed_spread} kt speed variation and sustained descent no steeper than ${r.max_sustained_descent_fpm} fpm below 500 ft.`;root.querySelector('#trainingRules').textContent=`Same standards in either mode: score ${r.min_score}+, touchdown no firmer than ${Math.abs(r.min_rate)} fpm, maximum ${r.max_g} G, no more than one bounce; overspeed penalties reduce score, and position jumps fail.${approach} An accepted report is required.`;
 };
 f.course.onchange=()=>refresh(true);f.mode.onchange=()=>refresh();f.aircraft.onchange=()=>refresh();f.choice.onchange=()=>{revision++;review.innerHTML=''};refresh(true);
 form.onsubmit=async e=>{e.preventDefault();const choice=choices[Number(f.choice.value)];if(!choice)return;const rev=++revision;review.textContent='Checking the route…';
 try{const m=await api('/api/training/preview',{method:'POST',body:choice.spec});if(rev!==revision||!dlg.isConnected)return;
 review.innerHTML=`<section class="notice" style="margin-top:20px"><h3>${esc(m.title)}</h3><p>${esc(S.fleet[m.aircraft[0]]?.name)} · ${fmt(m.distance_nm)} nm · ${hm(m.target_block_min)}</p><p><b>Cost: $0 · ${f.mode.value==='dedicated'?'Dedicated training aircraft':'Fleet aircraft '+esc(m.training.reg)}</b></p><p>${f.mode.value==='dedicated'?'Your normal station and operational aircraft will not move.':'Free pilot travel is included at booking. The aircraft will move when you complete the flight.'}</p><p>This creates your booking. Next, prepare the matching OFP and sign your release before starting ACARS.</p><button class="btn" id="trainingBook" type="button">Book checkride · $0</button><p>Accepted attempts count toward career hours and flight count, and earn standard flight pay plus applicable bonuses. Passing is still required for a qualification.</p></section>`;
 review.querySelector('#trainingBook').onclick=async ev=>{ev.target.disabled=true;f.course.disabled=f.mode.disabled=f.aircraft.disabled=f.choice.disabled=true;
 try{S.booking=await api('/api/booking',{method:'POST',body:{training:m.training}});dlg.close();await refreshCore();await loadMe();paintBid();show('bids');toast('Checkride booked at no cost. Prepare your OFP and dispatch release.');}
 catch(err){toast(err.message,8000);if(dlg.isConnected){f.course.disabled=f.mode.disabled=f.aircraft.disabled=f.choice.disabled=false;ev.target.disabled=false;}}
 };
 }catch(err){if(rev===revision)review.textContent=err.message;}
 };
 }catch(e){root.textContent=e.message;}
}


function lineCheckrideCard(status, via) {
 const passed=status==='Passed',waived=status==='Waived',pending=status==='Pending';
 const complete=passed||waived;
 const label=via&&passed?`Satisfied by your ${via} checkride`:passed?'Line checkride passed':waived?'Line checkride waived':pending?'Not yet passed':'Status unavailable';
 const body=via&&passed?`Your ${esc(via)} type checkride counted as your line checkride, so rank progression is open. It doesn't include the B737 qualification: fly the 737 line checkride or the B737 type checkride if you want to fly the 737.`
  :complete?'Your initial rank-progression requirement is satisfied. No additional B737 checkride is required.'
  :pending?'Your first step into rank progression: fly this 737 line checkride, which also grants the B737 qualification, or pass a type checkride for any aircraft family below. Either one counts.'
  :'Refresh Qualifications to load your current line-checkride status.';
 return `<div class="rating ${complete?'rt-held':''}"><h3>737 line checkride</h3><p><span class="tag ${complete?'green':'grey'}">${esc(label)}</span></p><p>${body}</p>${via&&passed?'<button class="btn ghost" onclick="openTraining()">Fly the 737 line checkride (optional)</button>':complete?'<button class="btn ghost" onclick="openTraining()">Retake line checkride (optional)</button>':pending?'<button class="btn" onclick="openTraining()">Start line checkride</button>':'<button class="btn ghost" onclick="fillRatings()">Refresh status</button>'}</div>`;
}

consentNotice();   // the privacy notice on a first visit (VATSIM's VA policy asks for one on the front page)
/* the width of the window's scrollbar (0 where scrollbars float over the page), so full-width bands fit exactly */
(function trackScrollbar() {
  const set = () => document.documentElement.style.setProperty("--sbw", Math.max(0, innerWidth - document.documentElement.clientWidth) + "px");
  set(); addEventListener("resize", set);
  try { new ResizeObserver(set).observe(document.body); } catch (e) { /* older browsers: resize only */ }
})();

/* ================= Weekly group flight =================
   One route, one departure time, everyone flies it together. Visitors can see it too (it's how new pilots find
   out PAC is alive), and signed-in pilots sign up, book it and add it to their calendar. group_flight.py runs it. */
VIEWS.push("groupflight");
PUBLIC_VIEWS.push("groupflight");
function gfWhen(t, opts) { return new Date(t * 1000).toLocaleString("en-US", opts); }
function gfCountdown(t) {
  const s = t - Date.now() / 1000;
  if (s <= 0) return s > -4 * 3600 ? "Departing now" : "Departed";
  const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  return d ? `in ${d}d ${h}h` : h ? `in ${h}h ${m}m` : `in ${m} min`;
}
function gfArc(a, b, n = 64) {
  const r = Math.PI / 180, [la1, lo1, la2, lo2] = [a.lat * r, a.lon * r, b.lat * r, b.lon * r];
  const d = 2 * Math.asin(Math.sqrt(Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2));
  if (!d) return [[a.lat, a.lon], [b.lat, b.lon]];
  return Array.from({ length: n + 1 }, (_, i) => {
    const f = i / n, A = Math.sin((1 - f) * d) / Math.sin(d), B = Math.sin(f * d) / Math.sin(d);
    const x = A * Math.cos(la1) * Math.cos(lo1) + B * Math.cos(la2) * Math.cos(lo2), y = A * Math.cos(la1) * Math.sin(lo1) + B * Math.cos(la2) * Math.sin(lo2), z = A * Math.sin(la1) + B * Math.sin(la2);
    return [Math.atan2(z, Math.hypot(x, y)) / r, Math.atan2(y, x) / r];
  });
}
async function loadGroupFlight() {
  const root = $("#groupFlightRoot");
  if (!root.innerHTML) root.innerHTML = `<p class="muted" role="status">Loading the group flight…</p>`;
  let d;
  try { d = await api("/api/public/group-flight"); } catch (e) { root.innerHTML = `<p class="notice err">${esc(e.message)}</p>`; return; }
  S.groupFlight = d;
  renderGroupFlight(d);
}
function renderGroupFlight(d) {
  const root = $("#groupFlightRoot");
  if (S.gfMap) { try { S.gfMap.remove(); } catch (e) { /* already gone */ } S.gfMap = null; }
  if (!d.enabled) {
    root.innerHTML = `<div class="profile-bar"><h1>Weekly group flight</h1></div><p class="muted">There's no group flight scheduled right now.</p>${d.staff ? gfStaffPanel(d) : ""}`;
    gfBindStaff(d); return;
  }
  const e = d.event, me = e.me, here = S.me?.location?.icao, now = Date.now() / 1000, started = e.start <= now, open = now >= (e.opens || 0) && now <= (e.closes || e.start);
  const local = gfWhen(e.start, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
  const utc = gfWhen(e.start, { timeZone: "UTC", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false }) + " UTC";
  const until = gfWhen(e.closes || e.start, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const acOpts = e.aircraft.map(a => `<option value="${esc(a.code)}" ${me?.aircraft === a.code ? "selected" : ""}>${esc(a.name)}</option>`).join("");
  const action = !S.me
    ? `<button class="btn" id="gfApply">Join PAC to fly it</button><button class="btn ghost" id="gfSignin">Pilots: sign in</button>`
    : `<button class="btn" id="gfBook">Book the flight</button>` + (me?.signed_up
        ? `<span class="tag green">On the list</span><button class="btn ghost small" id="gfLeave">Take me off the list</button>`
        : `<label class="gf-ac">Planning to fly it? <select id="gfAc"><option value="">Any aircraft</option>${acOpts}</select></label><button class="btn ghost" id="gfJoin">Add me to the list</button>`);
  root.innerHTML = `<div class="profile-bar"><h1>Weekly group flight</h1><span class="muted">${esc(d.schedule)} · optional</span></div>
    <section class="gf-hero">
      <div class="gf-main">
        <div class="kicker">${started && open ? "Open now" : "This week's route"} · optional</div>
        <h2>${esc(e.title)}</h2>
        <div class="gf-route"><div><b>${esc(e.dep.icao)}</b><span>${esc(e.dep.name)}</span></div><div class="gf-arrow" aria-hidden="true">${e.distance_nm ? `<small>${fmt(e.distance_nm)} nm</small>` : ""}<i></i></div><div><b>${esc(e.arr.icao)}</b><span>${esc(e.arr.name)}</span></div></div>
        <div class="gf-when"><div><small>Fly-along time</small><b>${esc(local)}</b><span class="gf-sub">${esc(utc)}</span></div><div><small>${started ? "Departed" : "Starts"}</small><b id="gfCount">${gfCountdown(e.start)}</b></div><div><small>Counts until</small><b>${esc(until)}</b></div></div>
        <p class="gf-optional">Fly it at the set time if you'd like company, or on your own any time this weekend. Offline is fine and voice chat is optional. Nobody has to take part.</p>
        <div class="gf-meta"><span><small>Aircraft</small>${e.aircraft.map(a => esc(a.name)).join(" · ")}</span><span><small>Cargo</small>${esc(e.cargo || "General cargo")}</span><span><small>Network</small>${esc(e.network === "Your choice" ? "Your choice: offline or online" : e.network)}</span><span><small>Voice</small>${esc(e.voice)}</span></div>
        <div class="row gf-actions">${action}</div>
        ${S.me && here && here !== e.dep.icao && !me?.flew ? `<p class="gf-note">You're at <b>${esc(here)}</b>. <button class="linkish" id="gfTravel">Jumpseat to ${esc(e.dep.icao)}</button>, or fly yourself there first.</p>` : ""}
        ${me?.flew ? `<p class="gf-note ok">You flew this week's route. Nice work.</p>` : ""}
      </div>
      <div class="gf-map" id="gfMap" role="img" aria-label="Route map from ${esc(e.dep.icao)} to ${esc(e.arr.icao)}"></div>
    </section>
    <div class="gf-cols">
      <section class="gf-card"><h3>Briefing</h3><p style="white-space:pre-line">${esc(e.briefing)}</p>
        <ol class="gf-steps"><li>Get to <b>${esc(e.dep.icao)}</b> with a PAC aircraft (jumpseat, or fly there beforehand).</li><li>Press <b>Book the flight</b>, plan it in SimBrief and sign the release, as for any flight.</li><li>Fly it with PAC ACARS any time before ${esc(until)}: at the set time if you'd like company, or whenever suits you.</li><li>File the PIREP. You'll show under "Flown this week" automatically. The list is optional too.</li></ol>
        <div class="row"><a class="btn ghost small" href="/api/group-flight.ics" download>Add to calendar</a><button class="btn ghost small" id="gfShare">Copy link</button></div></section>
      <section class="gf-card"><h3>Flown this week · ${e.flown.length}</h3>
        ${e.flown.map(n => `<div class="gf-pilot">${esc(n)}</div>`).join("") || `<p class="muted">Nobody's flown it yet.</p>`}
        ${e.count ? `<h3 style="margin-top:18px">Planning to fly · ${e.count}</h3>${e.signups.map(s => `<div class="gf-pilot">${esc(s.name)}${s.aircraft ? `<small>${esc(S.fleet?.[s.aircraft]?.icao || s.aircraft)}</small>` : ""}</div>`).join("")}` : ""}</section>
      <section class="gf-card"><h3>Coming up</h3>${d.next.map(n => `<div class="gf-row"><b>${esc(n.dep)} → ${esc(n.arr)}</b><span>${esc(gfWhen(n.start, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }))}</span></div>`).join("")}
        <p class="muted" style="font-size:13px">The route goes out from Cincinnati one week and back home the next, so if you flew out, you and your aircraft are already in place for the return.</p>
        ${d.past.some(p => p.signed || p.flew) ? `<h3 style="margin-top:18px">Recent</h3>${d.past.filter(p => p.flew).map(p => `<div class="gf-row"><b>${esc(p.dep)} → ${esc(p.arr)}</b><span>${p.flew} flew it</span></div>`).join("")}` : ""}</section>
    </div>
    ${d.staff ? gfStaffPanel(d) : ""}`;
  // map
  if (HAS_MAP && Number.isFinite(e.dep.lat) && Number.isFinite(e.arr.lat)) {
    const base = makeBaseMap($("#gfMap"), { theme: document.documentElement.dataset.theme === "light" ? "light" : "dark", style: S.settings?.map_style });
    const arc = gfArc(e.dep, e.arr);
    L.polyline(arc, { color: "#d4111e", weight: 3, opacity: .9 }).addTo(base.map);
    [[e.dep, "dep"], [e.arr, "arr"]].forEach(([a, k]) => L.marker([a.lat, a.lon], { icon: L.divIcon({ className: "gf-pin " + k, html: `<span>${esc(a.icao)}</span>`, iconSize: [60, 24], iconAnchor: [30, 12] }) }).addTo(base.map));
    base.map.fitBounds(arc, { padding: [40, 40], maxZoom: 6 });
    S.gfMap = base.map;
    setTimeout(() => S.gfMap?.invalidateSize(), 60);
  }
  clearInterval(S.gfTimer);
  S.gfTimer = setInterval(() => { const c = $("#gfCount"); if (!c || $("#view-groupflight").hidden) { clearInterval(S.gfTimer); return; } c.textContent = gfCountdown(e.start); }, 30000);
  const on = (id, fn) => { const b = $("#" + id); if (b) b.onclick = fn; };
  on("gfApply", () => { show("home"); setTimeout(() => $("#apply")?.scrollIntoView({ behavior: "smooth" }), 400); });
  on("gfSignin", () => openSignIn(null, "groupflight"));
  on("gfJoin", async () => { try { renderGroupFlight(await api("/api/group-flight/join", { method: "POST", body: { aircraft: $("#gfAc")?.value || "" } })); toast("You're on the list."); } catch (err) { toast(err.message); } });
  on("gfLeave", async () => { try { renderGroupFlight(await api("/api/group-flight/leave", { method: "POST", body: {} })); toast("Off the list."); } catch (err) { toast(err.message); } });
  on("gfTravel", () => openJumpseat(e.dep.icao));
  on("gfShare", () => navigator.clipboard.writeText(location.origin + "/#groupflight").then(() => toast("Link copied."), () => toast(location.origin + "/#groupflight")));
  on("gfBook", () => gfBook(e));
  gfBindStaff(d);
}
async function gfBook(e) {
  resetMissionFilters();
  if (e.route_id && (S.routes || []).some(r => r.id === e.route_id)) {
    S.board = "network"; S.region = "All"; S.netSearch = e.route_id; S.netLimit = 40; S.selected = null;
    show("missions");
    setTimeout(() => selectMission(e.route_id), 120);
  } else {
    S.charterSpec = { origin: e.dep.icao, destination: e.arr.icao, aircraft: e.aircraft[0]?.code || "B738F", payload_lbs: "", cargo: e.cargo || "General cargo", priority: "Standard", flight_number: "", _o: null, _d: null };
    S.charterMission = null; S.board = "charter"; S.selected = null; show("missions");
  }
}
function gfStaffPanel(d) {
  const s = d.staff, c = s.config, o = s.override || {};
  return `<details class="gf-card gf-staff" ${S.gfStaffOpen ? "open" : ""}><summary>Staff: run the group flight</summary>
    <form id="gfCfg" class="gf-form"><h3>Schedule</h3>
      <label class="check"><input type="checkbox" name="enabled" ${c.enabled ? "checked" : ""}> Weekly group flight is on</label>
      <div class="gf-grid"><label>Day<select name="weekday">${s.days.map((x, i) => `<option value="${i}" ${i === c.weekday ? "selected" : ""}>${x}</option>`).join("")}</select></label>
      <label>Time (UTC)<input name="time" value="${esc(c.time)}" pattern="\\d{1,2}:\\d{2}" required></label>
      <label>Network<select name="network">${s.networks.map(x => `<option ${x === c.network ? "selected" : ""}>${x}</option>`).join("")}</select></label>
      <label>Voice<input name="voice" value="${esc(c.voice)}" maxlength="120"></label></div>
      <label>Standing briefing<textarea name="briefing" rows="3" maxlength="1200">${esc(c.briefing)}</textarea></label>
      <button class="btn small">Save schedule</button></form>
    ${d.enabled ? `<form id="gfOv" class="gf-form"><h3>This week (${esc(d.event.id)})</h3>
      <p class="muted" style="font-size:13px">Leave blank to use the automatic out-and-back route. Enter a scheduled route number (like PAC1001), or a departure and arrival.</p>
      <div class="gf-grid"><label>Route number<input name="route_id" value="${esc(o.route_id || "")}" placeholder="PAC1001"></label>
      <label>Departure<input name="dep" value="${esc(o.dep || "")}" maxlength="4" placeholder="KCVG"></label><label>Arrival<input name="arr" value="${esc(o.arr || "")}" maxlength="4" placeholder="KJFK"></label>
      <label>Aircraft (for a custom route)<select name="aircraft" multiple size="3">${fleetCodes().map(k => `<option value="${k}" ${(o.aircraft || []).includes(k) ? "selected" : ""}>${esc(S.fleet[k].name)}</option>`).join("")}</select></label>
      <label>Title<input name="title" value="${esc(o.title || "")}" maxlength="80" placeholder="${esc(d.event.title)}"></label>
      <label>Network<select name="network"><option value="">Schedule default</option>${s.networks.map(x => `<option ${x === o.network ? "selected" : ""}>${x}</option>`).join("")}</select></label></div>
      <label>Briefing for this week<textarea name="briefing" rows="3" maxlength="1200" placeholder="Uses the standing briefing">${esc(o.briefing || "")}</textarea></label>
      <div class="row"><button class="btn small">Save this week</button><button type="button" class="btn ghost small" id="gfOvClear">Back to automatic</button></div></form>
      <div class="gf-form"><h3>Discord announcement</h3><textarea id="gfAnn" rows="10" readonly>${esc(s.announcement)}</textarea>
      <div class="row"><button class="btn small" id="gfAnnCopy">Copy</button>${s.discord ? `<button class="btn ghost small" id="gfAnnPost">Post to Discord</button>` : `<span class="muted" style="font-size:13px">Add the Discord webhook under Staff › Site and rules to post it in one click.</span>`}</div>
      <p class="muted" style="font-size:13px">The &lt;t:…&gt; codes show the departure in each reader's own time zone on Discord.</p></div>
      ${s.signups.length ? `<div class="gf-form"><h3>Sign-ups (staff view)</h3>${s.signups.map(x => `<div class="gf-row"><b>${esc(x.name)} · ${esc(x.pilot)}</b><span>${esc(x.aircraft || "any type")}</span></div>`).join("")}</div>` : ""}` : ""}
  </details>`;
}
function gfBindStaff(d) {
  if (!d.staff) return;
  const det = $(".gf-staff"); if (det) det.ontoggle = () => S.gfStaffOpen = det.open;
  const send = async body => { try { renderGroupFlight(await api("/api/staff/group-flight", { method: "POST", body })); toast("Saved."); } catch (err) { toast(err.message); } };
  const cfg = $("#gfCfg");
  if (cfg) cfg.onsubmit = ev => { ev.preventDefault(); const f = new FormData(cfg); send({ config: { enabled: cfg.enabled.checked, weekday: Number(f.get("weekday")), time: f.get("time"), network: f.get("network"), voice: f.get("voice"), briefing: f.get("briefing") } }); };
  const ov = $("#gfOv");
  if (ov) ov.onsubmit = ev => { ev.preventDefault(); const f = new FormData(ov); send({ override: { route_id: f.get("route_id"), dep: f.get("dep"), arr: f.get("arr"), aircraft: f.getAll("aircraft"), title: f.get("title"), network: f.get("network"), briefing: f.get("briefing") } }); };
  if ($("#gfOvClear")) $("#gfOvClear").onclick = () => send({ override: {} });
  if ($("#gfAnnCopy")) $("#gfAnnCopy").onclick = () => navigator.clipboard.writeText($("#gfAnn").value).then(() => toast("Announcement copied."), () => { $("#gfAnn").select(); toast("Select and copy it by hand."); });
  if ($("#gfAnnPost")) $("#gfAnnPost").onclick = async ev => { ev.target.disabled = true; try { await api("/api/staff/group-flight/discord", { method: "POST", body: {} }); toast("Posted to Discord."); } catch (err) { toast(err.message); } ev.target.disabled = false; };
}
{
  const nav = document.createElement("button"); nav.dataset.view = "groupflight"; nav.textContent = "Group flight";
  nav.onclick = () => show("groupflight");
  document.querySelector("#navGroup2")?.prepend(nav);
}
/* Home page: a strip announcing the next group flight, under the hero. */
async function gfHomeStrip() {
  try {
    const d = S.groupFlight && S.groupFlight._at > Date.now() - 60000 ? S.groupFlight : await api("/api/public/group-flight");
    S.groupFlight = { ...d, _at: Date.now() };
    const hero = $("#homeRoot .hero");
    if (!S.me) fillJoinGroupFlight(d);
    if (!d.enabled || !hero || !S.me || $("#gfStrip")) return;
    const e = d.event;
    hero.insertAdjacentHTML("afterend", `<a id="gfStrip" class="gf-strip" href="#groupflight"><span class="kicker">Weekly group flight · optional</span><b>${esc(e.dep.icao)} → ${esc(e.arr.icao)} · ${esc(e.title)}</b><span>${esc(gfWhen(e.start, { weekday: "long", hour: "numeric", minute: "2-digit", timeZoneName: "short" }))} · ${gfCountdown(e.start)} · fly it any time this weekend</span><span class="gf-strip-go">Details ›</span></a>`);
    $("#gfStrip").onclick = ev => { ev.preventDefault(); show("groupflight"); };
  } catch (e) { /* the home page works without it */ }
}

/* ================= Live map: globe view =================
   A Flat / Globe switch on the live map. The flat map stays Leaflet; the globe is MapLibre GL (vendored, BSD
   licensed), loaded only the first time someone picks Globe. Both show the same flights and parked fleet, and the
   same filters, station buttons and lists drive both. The choice is remembered on each computer. */
const GLOBE_JS = "/static/vendor/maplibre/maplibre-gl.js", GLOBE_CSS = "/static/vendor/maplibre/maplibre-gl.css";
let globeLib;
function loadGlobeLib() {
  if (window.maplibregl) return Promise.resolve(window.maplibregl);
  return globeLib ||= new Promise((ok, fail) => {
    const css = document.createElement("link"); css.rel = "stylesheet"; css.href = GLOBE_CSS; document.head.append(css);
    const s = document.createElement("script"); s.src = GLOBE_JS; s.onload = () => ok(window.maplibregl); s.onerror = () => { globeLib = null; fail(new Error("The globe couldn't load. Check your connection and try again.")); };
    document.head.append(s);
  });
}
function liveViewPref() { try { return localStorage.getItem("pac.liveView") || "flat"; } catch (e) { return "flat"; } }
function setLiveViewPref(v) { try { localStorage.setItem("pac.liveView", v); } catch (e) { /* not remembered; that's fine */ } }
function globeStyle(theme, key) {
  const dark = theme === "dark", st = MAP_STYLES[key] || MAP_STYLES[dark ? "dark" : "light"];
  const sources = {}, layers = [{ id: "ocean", type: "background", paint: { "background-color": dark ? "#14171b" : "#dfe6ec" } }];
  st.layers.forEach(([url, maxzoom], i) => {
    sources["tiles" + i] = { type: "raster", tiles: [url], tileSize: 256, maxzoom, attribution: i ? "" : st.attr };
    layers.push({ id: "tiles" + i, type: "raster", source: "tiles" + i });
  });
  return { version: 8, projection: { type: "globe" }, sources, layers,
    sky: { "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 1, 7, 0] } };
}
function liveFocus(lat, lon, zoom = 6) {
  const g = S.live?.globe;
  if (g && S.live.view === "globe") g.map.flyTo({ center: [lon, lat], zoom: Math.max(g.map.getZoom(), Math.min(zoom - 1, 5)), duration: 1600, essential: true });
  else S.live?.base.map.setView([lat, lon], Math.max(S.live.base.map.getZoom(), zoom));
}
function liveFit(pts) {
  if (!pts?.length) return;
  const g = S.live?.globe;
  if (g && S.live.view === "globe") {
    const lons = pts.map(p => p[1]), lats = pts.map(p => p[0]);
    g.map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 60, maxZoom: 5, duration: 1400 });
  } else S.live?.base.map.fitBounds(pts, { padding: [40, 40], maxZoom: 6 });
}
async function setLiveView(v) {
  const live = S.live; if (!live) return;
  live.view = v; setLiveViewPref(v);
  document.querySelectorAll("[data-liveview]").forEach(b => b.setAttribute("aria-pressed", b.dataset.liveview === v));
  $("#liveMap").hidden = v === "globe"; $("#liveGlobe").hidden = v !== "globe";
  if (v === "flat") { setTimeout(() => live.base.map.invalidateSize(), 30); return; }
  if (!live.globe) {
    $("#liveGlobe").innerHTML = `<p class="globe-loading">Loading the globe…</p>`;
    try { await loadGlobeLib(); } catch (e) { $("#liveGlobe").innerHTML = `<p class="globe-loading">${esc(e.message)}</p>`; return; }
    if (S.live !== live) return;
    $("#liveGlobe").innerHTML = "";
    const theme = document.documentElement.dataset.theme === "light" ? "light" : "dark";
    let map;
    try {
      map = new maplibregl.Map({ container: "liveGlobe", style: globeStyle(theme, S.settings?.map_style), center: [-84.66, 39.05], zoom: 1.4,
        attributionControl: { compact: true }, maxPitch: 60, renderWorldCopies: false });
    } catch (e) {
      $("#liveGlobe").innerHTML = `<p class="globe-loading">Your browser can't draw the globe (it needs WebGL). The flat map still works.</p>`; return;
    }
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-left");
    live.globe = { map, markers: [], ready: false, tileErr: 0, tileOk: 0 };
    map.on("data", e => { if (e.dataType === "source" && e.tile && String(e.sourceId || "").startsWith("tiles")) live.globe.tileOk++; });
    map.on("error", e => {
      if (!String(e?.sourceId || "").startsWith("tiles")) return;
      live.globe.tileErr++;
      if (live.globe.tileErr >= 6 && !live.globe.tileOk && !live.globe.noted) {
        live.globe.noted = true;
        map.getStyle().layers.filter(l => l.type === "raster").forEach(l => map.setLayoutProperty(l.id, "visibility", "none"));
        $("#liveGlobe").insertAdjacentHTML("beforeend", `<div class="map-note globe-note">Map tiles are unavailable. Showing the offline outline globe.</div>`);
      }
    });
    map.on("load", async () => {
      const w = await loadWorld();
      const dark = theme === "dark";
      if (w) {
        map.addSource("land", { type: "geojson", data: { type: "Feature", properties: {}, geometry: w.land } });
        map.addSource("borders", { type: "geojson", data: { type: "Feature", properties: {}, geometry: w.borders } });
        map.addLayer({ id: "land", type: "fill", source: "land", paint: { "fill-color": dark ? "#262a31" : "#f4f5f7" } }, map.getLayer("tiles0") ? "tiles0" : undefined);
        map.addLayer({ id: "borders", type: "line", source: "borders", paint: { "line-color": dark ? "#3a4049" : "#c3c9d0", "line-width": 0.6 } }, map.getLayer("tiles0") ? "tiles0" : undefined);
      }
      await addZoneOverlayGlobe(map, $("#liveGlobe")).catch(() => {});
      map.addSource("tracks", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "tracks", type: "line", source: "tracks", paint: { "line-color": "#d4111e", "line-width": ["case", ["get", "sel"], 3, 2], "line-opacity": ["case", ["get", "sel"], 0.9, 0.55] } });
      map.addSource("toarr", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "toarr", type: "line", source: "toarr", paint: { "line-color": "#d4111e", "line-width": 1.5, "line-dasharray": [3, 3], "line-opacity": 0.75 } });
      live.globe.ready = true;
      globeSync();
      dayNightSync();
    });
  } else {
    setTimeout(() => live.globe.map.resize(), 30);
    globeSync();
  }
}
function globePlaneEl(f, sel) {
  const col = f.on_ground ? "#9aa1ab" : "#d4111e", el = document.createElement("button");
  el.type = "button"; el.className = "globe-plane" + (sel ? " sel" : ""); el.title = `${f.flight} · ${f.aircraft} · ${f.dep || ""} → ${f.arr || ""}`;
  el.setAttribute("aria-label", `${f.flight}, ${f.dep || ""} to ${f.arr || ""}`);
  el.innerHTML = `<svg viewBox="0 0 32 32" width="30" height="30"><path d="M16 2l2.4 9.6 10.6 6v2.6l-10.6-3.2-.8 7.4 3.6 2.6V29L16 27.6 10.8 29v-2l3.6-2.6-.8-7.4-10.6 3.2v-2.6l10.6-6z" fill="${col}" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/></svg>`;
  return el;
}
function unwrapLon(coords) {  // [lon, lat] pairs: keep each step under 180 degrees so lines cross the date line the short way
  return coords.reduce((out, [lo, la]) => {
    const prev = out.length ? out[out.length - 1][0] : lo;
    let x = lo; while (x - prev > 180) x -= 360; while (prev - x > 180) x += 360;
    out.push([x, la]); return out;
  }, []);
}
function globeSync() {
  const live = S.live, g = live?.globe;
  if (!g?.ready || live.view !== "globe") return;
  const map = g.map;
  g.markers.forEach(m => m.remove()); g.markers = [];
  const showFlights = $("#pmFlying")?.checked !== false, showParked = $("#pmParked")?.checked !== false;
  const flights = showFlights ? live.flights || [] : [];
  map.getSource("tracks")?.setData({ type: "FeatureCollection", features: flights.filter(f => f.track?.length > 1).map(f => ({ type: "Feature", properties: { sel: live.sel === f.flight },
    geometry: { type: "LineString", coordinates: unwrapLon(f.track.map(([la, lo]) => [lo, la])) } })) });
  const s = flights.find(f => f.flight === live.sel && f.arr_pos);
  map.getSource("toarr")?.setData({ type: "FeatureCollection", features: s ? [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: unwrapLon(gfArc({ lat: s.lat, lon: s.lon }, { lat: s.arr_pos[0], lon: s.arr_pos[1] }, 48).map(([la, lo]) => [lo, la])) } }] : [] });
  if (showParked) Object.entries(live.parkedGroups || {}).forEach(([code, frames]) => {
    const a = live.airportCache?.[code]; if (!a) return;
    const el = document.createElement("button"); el.type = "button"; el.className = "pm-marker globe-pm"; el.title = `${code} · ${frames.length} aircraft`;
    el.innerHTML = `<span>${frames.length}</span>`; el.onclick = ev => { ev.stopPropagation(); pacParkedStation(code, frames); };
    g.markers.push(new maplibregl.Marker({ element: el }).setLngLat([a.lon, a.lat]).addTo(map));
  });
  flights.forEach(f => {
    const sel = live.sel === f.flight, el = globePlaneEl(f, sel);
    el.onclick = ev => { ev.stopPropagation(); live.sel = sel ? null : f.flight; pollLive(); };
    g.markers.push(new maplibregl.Marker({ element: el, rotation: f.hdg || 0, rotationAlignment: "map" }).setLngLat([f.lon, f.lat]).addTo(map));
  });
  if (!g.fitted && flights.length) { g.fitted = true; map.flyTo({ center: [flights[0].lon, flights[0].lat], zoom: 2.2, duration: 1800 }); }
}
function liveViewSwitch() {
  const bar = document.querySelector("#liveRoot .profile-bar");
  if (!bar || $("#liveViewSwitch")) return;
  bar.insertAdjacentHTML("beforeend", `<div class="seg-switch" id="liveViewSwitch" role="group" aria-label="Map view"><button type="button" data-liveview="flat" aria-pressed="true">Flat map</button><button type="button" data-liveview="globe" aria-pressed="false">Globe</button></div>`);
  $(".live-wrap").insertAdjacentHTML("afterbegin", `<div id="liveGlobe" class="live-map live-globe" hidden></div>`);
  document.querySelectorAll("[data-liveview]").forEach(b => b.onclick = () => setLiveView(b.dataset.liveview));
  bar.insertAdjacentHTML("beforeend", `<button type="button" class="btn ghost small daynight-btn" id="dayNightBtn" aria-pressed="${dayNightPref()}" title="Show where it's day and night right now">☀︎ Day / night</button>`);
  $("#dayNightBtn").onclick = () => { const on = !dayNightPref(); setDayNightPref(on); $("#dayNightBtn").setAttribute("aria-pressed", on); dayNightSync(); };
  dayNightSync();
  clearInterval(S.dayNightTimer); S.dayNightTimer = setInterval(() => { if (document.getElementById("dayNightBtn")) dayNightSync(); else clearInterval(S.dayNightTimer); }, 60000);
}

/* ================= Day / night: where the sun is up right now (the terminator), on the flat map and the globe ================= */
function dayNightPref() { try { return localStorage.getItem("pac.dayNight") === "1"; } catch (e) { return false; } }
function setDayNightPref(on) { try { localStorage.setItem("pac.dayNight", on ? "1" : "0"); } catch (e) { /* not remembered */ } }
function sunPosition(date = new Date()) {
  // low-precision solar position (good to about 0.1 degree; plenty for a map)
  const rad = Math.PI / 180, n = date.getTime() / 86400000 + 2440587.5 - 2451545;
  const L = (280.460 + 0.9856474 * n) % 360, g = ((357.528 + 0.9856003 * n) % 360) * rad;
  const lam = (L + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * rad, eps = (23.439 - 0.0000004 * n) * rad;
  const ra = Math.atan2(Math.cos(eps) * Math.sin(lam), Math.cos(lam)) / rad, dec = Math.asin(Math.sin(eps) * Math.sin(lam)) / rad;
  const gmst = ((18.697374558 + 24.06570982441908 * n) % 24) * 15;
  return { dec, lon: ((ra - gmst + 540) % 360) - 180 };       // the point on Earth where the sun is overhead
}
function nightRings(date = new Date()) {
  // the night side, plus a softer twilight band (sun up to 6 and 12 degrees below the horizon)
  const sun = sunPosition(date), rad = Math.PI / 180, out = [];
  for (const depress of [0, 6, 12]) {
    const ring = [], pole = sun.dec > 0 ? -90 : 90;
    const d = sun.dec * rad, dir = pole < 0 ? 1 : -1;
    for (let lon = -180; lon <= 180; lon += 2) {
      const ch = Math.cos((lon - sun.lon) * rad);
      const alt = lat => Math.asin(Math.sin(lat * rad) * Math.sin(d) + Math.cos(lat * rad) * Math.cos(d) * ch) / rad;
      // walk from the dark pole toward the sunlit one; the edge is where the sun climbs above -depress
      let lat = pole, edge = -pole;
      for (let x = pole; dir > 0 ? x <= 90 : x >= -90; x += dir * 0.5) { if (alt(x) > -depress) { edge = x; break; } lat = x; }
      ring.push([lon, Math.max(-89.9, Math.min(89.9, edge))]);
    }
    ring.push([180, pole], [-180, pole], ring[0]);
    out.push(ring);
  }
  return out;          // [night edge, civil twilight, nautical twilight], each a closed [lon, lat] ring
}
function dayNightSync() {
  const live = S.live; if (!live) return;
  const on = dayNightPref(), rings = on ? nightRings() : [];
  const dark = document.documentElement.dataset.theme !== "light";
  // flat map (Leaflet)
  const m = live.base?.map;
  if (m) {
    // one canvas with a wide margin, kept between updates: panning and zooming don't redraw it from scratch (no blinking)
    live.nightRenderer ||= L.canvas({ padding: 1.5, pane: "overlayPane" });
    live.nightLayers ||= [];
    rings.forEach((r, i) => {
      const ll = r.map(([x, y]) => [y, x]);
      if (live.nightLayers[i]) live.nightLayers[i].setLatLngs(ll);
      else live.nightLayers[i] = L.polygon(ll, { renderer: live.nightRenderer, stroke: false, fillColor: "#00081a", fillOpacity: dark ? 0.22 : 0.14, interactive: false, smoothFactor: 2 });
      if (!m.hasLayer(live.nightLayers[i])) live.nightLayers[i].addTo(m);
    });
    if (!on) live.nightLayers.forEach(l => m.hasLayer(l) && m.removeLayer(l));
  }
  // globe (MapLibre)
  const g = live.globe;
  if (g?.ready) {
    const fc = { type: "FeatureCollection", features: rings.map(r => ({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [r] } })) };
    if (g.map.getSource("night")) g.map.getSource("night").setData(fc);
    else {
      g.map.addSource("night", { type: "geojson", data: fc });
      g.map.addLayer({ id: "night", type: "fill", source: "night", paint: { "fill-color": "#00081a", "fill-opacity": dark ? 0.22 : 0.14, "fill-antialias": false } }, g.map.getLayer("tracks") ? "tracks" : undefined);
    }
  }
}


/* ================= Home: why PAC + track a shipment; Dashboard: start-here checklist + happening now ================= */
function whyPacHTML() {
  const pillars = [
    ["Real paperwork", "Every flight gets a dispatch release: load sheet with CG, NOTOC, cargo manifest with IATA codes, weather and runway wind.", "Read the cargo guide", "show('cargoguide')"],
    ["Cargo that stays put", "Shipments move station to station across flights. Track any air waybill, and see the whole network live.", "See the network", "(S.me ? show('network') : location.href='/network')"],
    ["Real consequences", "A hard landing or tail strike grounds the aircraft where it is. Then a PAC crew flies in the repair kit.", "How scoring works", "show('handbook')"],
    ["Fly online", "IVAO certified and flying on VATSIM as PGI. A weekly group flight anyone can join.", "This week's group flight", "show('groupflight')"]];
  return `<section class="why-pac" aria-label="Why fly for PAC">
    ${S.me ? "" : `<div class="section-h"><div><div class="kicker">Why PAC</div><h2>A cargo airline that takes the freight seriously</h2></div></div>
    <div class="why-grid">${pillars.map(([h, p, l, go], i) => `<article class="why-card"><img class="why-img" ${illSrc(["ill-main-deck-pac", "ill-767-main-deck-loading", "ill-hangar-777f", "ill-ake-lower-hold"][i], "(max-width: 760px) 100vw, 300px")} alt="" loading="lazy" width="640" height="360"><span class="why-n">0${i + 1}</span><h3>${h}</h3><p>${p}</p><button class="why-link" type="button" onclick="${go}">${l} →</button></article>`).join("")}</div>`}
    <form class="track-strip" onsubmit="event.preventDefault();const v=this.awb.value.replace(/\\D/g,'');if(v)location.href='/track/'+v">
      <div><div class="kicker">Track a shipment</div><b>Where's my freight?</b></div>
      <input name="awb" inputmode="numeric" autocomplete="off" placeholder="901-10000123" aria-label="Air waybill number">
      <button class="btn">Track</button>
    </form></section>`;
}

function startHereHTML(d) {
  let acars = false;
  try { acars = localStorage.getItem("pac-start-acars-" + S.me?.id) === "1"; } catch (_) {}
  const filed = (d.flights_filed || 0) > 0;
  const steps = [
    ["Install PAC ACARS and print the cheat sheets", acars || filed || !d.checkride_needed, "PAC ACARS tracks and scores your flight, including your checkride. The Quick-Reference Pack has everything on six pages.", "Downloads", "markStartAcars();show('downloads')"],
    ["Pass your line checkride", !d.checkride_needed, "Your first graded flight, in the 737-800. Fly it with ACARS running.", "Checkride", "show('career/qualifications')"],
    ["Book your first flight", !!d.booking || filed, "Pick a short hop from where you are. The dispatch release comes with it.", "Missions", "show('missions')"],
    ["Fly it and file your PIREP", filed, "Park, brakes set, engines off, then File PIREP in ACARS.", "Gate-to-gate checklist", "show('downloads')"]];
  const done = steps.filter(s => s[1]).length;
  if (done === steps.length) return pilotWelcomeHTML();
  const next = steps.find(s => !s[1]);   // the one thing to do right now
  const nextN = steps.indexOf(next) + 1;
  return `<section class="start-here" aria-label="Start here">
    <div class="start-head"><div><span class="kicker">Start here</span><h3>Your first PAC flight</h3></div>
      <div class="start-meter" role="img" aria-label="${done} of ${steps.length} steps done"><b>${done}/${steps.length}</b><span><i style="width:${done / steps.length * 100}%"></i></span></div></div>
    ${next ? `<div class="next-step"><div class="next-step-body"><span class="kicker">Your next step · ${nextN} of ${steps.length}</span><h4>${next[0]}</h4><p>${next[2]}</p></div>
      <button class="btn" type="button" onclick="${next[4]}">${next[3]} →</button></div>` : ""}
    <ol class="start-steps">${steps.map(([t, ok, p, l, go]) => `<li class="${ok ? "done" : t === next[0] ? "next" : ""}"><span class="start-tick" aria-hidden="true">${ok ? "✓" : ""}</span>
      <div><b>${t}</b><small>${p}</small></div>${ok ? `<span class="start-ok">Done</span>` : `<button class="btn ghost small" type="button" onclick="${go}">${l}</button>`}</li>`).join("")}</ol>
    <div class="row"><button class="btn small" type="button" onclick="openPilotGuide()">Full first-flight guide</button><button class="btn ghost small" type="button" onclick="location.href='/academy/'">PAC Academy</button></div></section>`;
}
function markStartAcars() { try { localStorage.setItem("pac-start-acars-" + S.me?.id, "1"); } catch (_) {} }

async function loadHappeningNow(root, d) {
  root.innerHTML = `<div class="kicker">Happening now</div><h3>What needs a crew</h3><p class="muted" role="status">Checking the network…</p>`;
  const [gf, net] = await Promise.all([api("/api/public/group-flight").catch(() => null), api("/api/public/network").catch(() => null)]);
  if (!root.isConnected) return;
  const items = [];
  let urgent = S.urgent || [];
  const relief = urgent.filter(m => m.relief);
  if (relief.length) items.push(["RELIEF", esc(relief[0].title), `Based on a real disaster: ${esc(relief[0].relief.event)}. No bonus rewards.`, "Read the briefing", "S.board='urgent';show('missions')"]);
  urgent = urgent.filter(m => !m.relief);
  const aog = urgent.filter(m => /aog/i.test(m.urgent_kind || ""));
  if (aog.length) items.push(["AOG", `${aog.length} aircraft grounded`, `${aog.map(m => esc(m.destination.icao)).join(", ")} waiting for parts and engineers.`, "Fly a recovery", "S.board='urgent';show('missions')"]);
  if (urgent.length > aog.length) items.push(["URGENT", `${urgent.length - aog.length} urgent request${urgent.length - aog.length > 1 ? "s" : ""}`, "Time-critical freight with bonus points.", "See urgent flights", "S.board='urgent';show('missions')"]);
  const here = (net?.waiting || []).find(w => w.icao === d.location.icao);
  if (here) items.push(["FREIGHT", `${fmt(here.lbs)} lb waiting at ${esc(here.icao)}`, `${here.shipments} shipment${here.shipments > 1 ? "s" : ""} ready to move from where you are.`, "Find a flight", "show('missions')"]);
  else if (net?.waiting?.length) { const w = net.waiting[0]; items.push(["FREIGHT", `${fmt(w.lbs)} lb waiting at ${esc(w.icao)}`, `The most freight sitting anywhere in the network right now.`, "Cargo network", "(S.me ? show('network') : location.href='/network')"]); }
  if (gf?.enabled && gf.event) items.push(["GROUP", esc(gf.event.title || "Weekly group flight"), `${esc(gfWhen(gf.event.start, { weekday: "long", hour: "numeric", minute: "2-digit" }))} your time. ${esc(gf.schedule || "")}`, "Sign up", "show('groupflight')"]);
  root.innerHTML = `<div class="kicker">Happening now</div><h3>What needs a crew</h3>${items.length ? `<div class="now-grid">${items.map(([tag, h, p, l, go]) => `<div class="now-item"><span class="now-tag now-${tag.toLowerCase()}">${tag}</span><b>${h}</b><small>${p}</small><button class="why-link" type="button" onclick="${go}">${l} →</button></div>`).join("")}</div>` : `<p>All quiet: no urgent flights or waiting freight right now. A good time to fly a scheduled route.</p>`}`;
}


/* ================= Home page layout (Nov 2026 redesign) =================
   The template renders every section; this puts them in order. Visitors get a short page that tells the story
   (hero, proof numbers, why PAC, PAC flying now, the fleet, join in); pilots get the slim welcome bar with notices
   and company news first, then everything else as before. */
function fmtLbShort(n) { n = Number(n) || 0; return n >= 1e6 ? (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M" : n >= 1e3 ? fmt(Math.round(n / 1e3)) + "k" : fmt(n); }
function homeLayout() {
  const root = $("#homeRoot"); if (!root) return;
  const groups = [], byKey = {};
  const solo = el => el.matches(".hero,.stat-band,.proof-band,.why-pac,.site-foot,#homeCampaigns,.home-notices,.gf-strip");
  let cur = null;
  [...root.children].forEach(el => {
    if (solo(el) || el.classList.contains("section-h") || !cur) {
      const key = el.classList.contains("section-h") ? (el.querySelector(".kicker")?.textContent || "").trim().toLowerCase()
        : el.id === "homeCampaigns" ? "campaigns" : (el.className.split(" ")[0] || el.tagName.toLowerCase());
      cur = { key, els: [el] }; groups.push(cur); byKey[key] = cur;
      if (solo(el)) cur = null;
    } else cur.els.push(el);
  });
  const put = keys => { const seen = new Set(); const out = [];
    keys.forEach(k => { const g = byKey[k]; if (g && !seen.has(g)) { seen.add(g); out.push(g); } });
    groups.forEach(g => { if (!seen.has(g)) out.push(g); }); return out; };
  // See it working: the departure board and the map side by side, under one heading
  const board = byKey["live from the ops center"], net = byKey["the network"];
  if (board && net) {
    const see = document.createElement("section"); see.className = "see-it";
    see.innerHTML = `<div class="section-h"><div><div class="kicker">See it working</div><h2>PAC is flying right now</h2></div><button class="btn ghost small" type="button" onclick="(S.me ? show('network') : location.href='/network')">Open the cargo network</button></div><div class="see-grid"></div>`;
    const grid = see.querySelector(".see-grid");
    board.els.filter(el => !el.classList.contains("section-h")).forEach(el => grid.append(el));
    net.els.filter(el => !el.classList.contains("section-h")).forEach(el => grid.append(el));
    board.els.concat(net.els).filter(el => el.classList.contains("section-h")).forEach(el => el.remove());
    board.els = [see]; net.els = [];
  }
  root.classList.toggle("home-pilot", !!S.me);
  root.classList.remove("home-visitor");
  if (S.me) {
    const gone = new Set(["the liveries", "operations", "our story", "partners", "career path", "community", "join the crew"]);
    groups.filter(g => gone.has(g.key)).forEach(g => g.els.forEach(el => el.remove()));
    const sb = byKey["stat-band"];
    if (sb) { const h = document.createElement("div"); h.className = "section-h"; h.innerHTML = `<div><div class="kicker">The airline</div><h2>PAC at a glance</h2></div>`; sb.els.unshift(h); }
    const order = put(["hero", "campaigns", "needs a crew now", "on now", "live from the ops center", "company news", "from the flight deck",
      "online networks", "stat-band", "why-pac", "site-foot"]).filter(g => !gone.has(g.key));
    const fi = order.findIndex(g => g.key === "site-foot"); if (fi > -1) order.push(order.splice(fi, 1)[0]);
    order.forEach(g => g.els.forEach(el => root.append(el)));
    return;
  }
  root.classList.add("home-visitor");
  const drop = new Set(["company news", "from the flight deck", "campaigns", "on now", "needs a crew now", "operations"]);
  groups.filter(g => drop.has(g.key)).forEach(g => g.els.forEach(el => el.remove()));
  const join = document.createElement("section"); join.className = "home-join"; join.setAttribute("aria-label", "Join in");
  join.innerHTML = `<div class="join-gf" id="joinGf" hidden></div>
    <div class="join-cta"><h3>Ready for your first load?</h3><p>Free to join. Start in the 737, work up to the 747-8F.</p>
    <div class="row"><a class="btn light" href="#apply" onclick="document.getElementById('apply')?.scrollIntoView({behavior:'smooth'});return false">Apply to fly</a><button class="btn ghost" type="button" onclick="location.href='/academy/'">Try PAC Academy</button></div></div>`;
  byKey.join = { key: "join", els: [join] };
  const track = root.querySelector(".track-strip");
  groups.push(byKey.join);
  // The fleet: one row of every type instead of the big photo grid
  const liv = byKey["the liveries"];
  const lgrid = liv && liv.els.find(el => el.classList.contains("livery-grid"));
  if (lgrid) {
    const row = document.createElement("div"); row.className = "fleet-chips";
    row.innerHTML = fleetCodes().map(k => `<button type="button" onclick="show('fleet')">${esc(S.fleet[k].name.replace(/^(Boeing|Airbus|McDonnell Douglas) /, ""))}</button>`).join("");
    lgrid.replaceWith(row); liv.els[liv.els.indexOf(lgrid)] = row;
  }
  const final = put(["hero", "proof-band", "why-pac", "live from the ops center", "the network", "online networks", "the liveries", "join",
    "our story", "career path", "partners", "community", "join the crew", "stat-band", "site-foot"]).filter(g => !drop.has(g.key));
  const footIdx = final.findIndex(g => g.key === "site-foot");
  if (footIdx > -1) final.push(final.splice(footIdx, 1)[0]);
  final.forEach(g => g.els.forEach(el => root.append(el)));
  const foot = root.querySelector(".site-foot");
  if (track && foot) { track.classList.add("track-foot"); foot.before(track); }
}
function fillJoinGroupFlight(d) {
  const box = $("#joinGf"); if (!box) return;
  if (!d || !d.enabled || !d.event) { box.hidden = true; return; }
  const e = d.event;
  box.innerHTML = `<div class="kicker">This week's group flight</div><h3>${esc(e.title)}</h3>
    <div class="join-route">${esc(e.dep.icao)} → ${esc(e.arr.icao)} · ${esc(gfWhen(e.start, { weekday: "long", hour: "numeric", minute: "2-digit", timeZoneName: "short" }))}</div>
    <p>Fly together online, or any time that weekend. New pilots welcome.</p>
    <button class="btn ghost small" type="button" onclick="show('groupflight')">See the briefing</button>`;
  box.hidden = false;
}

/* ================= Humanitarian relief missions (real disasters, staff-approved) =================
   Calm styling on purpose: no red, no countdowns, no bonus. The notice and the real sources always come first. */
function reliefCard(m) {
  return `<div class="urgent-card relief-card"><span class="relief-label">HUMANITARIAN RELIEF</span>
    <h3>${esc(m.title)}</h3><div class="rt">${esc(m.origin.icao)} → ${esc(m.destination.icao)}</div>
    <div class="muted" style="font-size:13px">${esc(S.fleet[m.aircraft[0]]?.name || "")} · ${fmt(m.payload_lbs)} lb</div>
    <div style="font-size:13px">Based on a real disaster. Flown in respect for those affected; no bonus rewards.</div>
    <button class="btn ghost small" style="align-self:flex-start;position:relative;z-index:1" onclick="flyMission('${esc(m.id)}')">Read the briefing</button></div>`;
}
function reliefBrief(m) {
  const r = m.relief, day = t => new Date(t * 1000).toLocaleDateString("en-US", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" });
  return `<section class="px-cargo relief-brief">
    <div class="relief-notice"><h3>About this mission</h3><p>${esc(r.notice)}</p>
      <p>Please fly it with respect. If you want to help for real, see the links below. Pagani Air Cargo is a flight simulation community; no real cargo is carried.</p></div>
    <span class="relief-label">HUMANITARIAN RELIEF · ${esc(m.id)}</span>
    <h3>${esc(m.title)}</h3><p>${esc(m.briefing)}</p>
    <div class="relief-facts"><div><small>Event</small><b>${esc(r.type)}</b></div><div><small>Alert level</small><b>${esc(r.alert)} (GDACS)</b></div>
      <div><small>Began</small><b>${esc(day(r.start))}</b></div><div><small>Area</small><b>${esc(r.country || "–")}</b></div></div>
    ${r.severity ? `<p class="muted" style="font-size:14px">${esc(r.severity)}</p>` : ""}
    <p class="muted" style="font-size:14px">Source: <a href="${esc(r.source)}" target="_blank" rel="noopener">GDACS alert</a>. PAC only repeats what the source says; follow the link for the full picture.</p>
    <table class="relief-cargo"><thead><tr><th>Cargo</th><th class="r">Pieces</th><th class="r">Weight</th><th>Code</th></tr></thead><tbody>
      ${r.items.map(i => `<tr><td><b>${esc(i.item)}</b><small>${esc(i.why)}</small></td><td class="r mono">${esc(i.pieces)}</td><td class="r mono">${fmt(i.kg)} kg</td><td class="mono">${esc(i.code)}</td></tr>`).join("")}
    </tbody></table>
    <p class="muted" style="font-size:13px">Shipper: humanitarian response depot, ${esc(r.depot_city)} (simulated). No dangerous goods on this flight.</p>
    <div class="relief-ops">${r.ops.map(([k, v]) => `<div><small>${esc(k)}</small><span>${esc(v)}</span></div>`).join("")}</div>
    <div class="relief-notice"><h3>Scoring and pay</h3><p>Flown and scored like any PAC flight, at normal pay. <b>No bonus points.</b> Booking closes ${esc(day(m.expires))}, or sooner when the real airlift winds down.</p></div>
    <div class="relief-help"><h3>How to help for real</h3><p>These organizations are responding. PAC isn't affiliated with them and receives nothing; the links go straight to them.</p>
      <ul>${r.help.map(([t, u]) => `<li><a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)}</a></li>`).join("")}</ul></div></section>`;
}
