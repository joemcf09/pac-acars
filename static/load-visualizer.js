/* PAC cargo distribution view. A schematic, not certified weight and balance. */
const MAIN = Array.from({length:11}, (_, i) => 'M' + String(i + 1).padStart(2, '0'));

function identityAssignments(positions) {
  const assignments = {};
  for (const p of positions) {
    if (assignments[p.pos]) throw Error('Duplicate manifest position');
    assignments[p.pos] = p.pos;
  }
  return assignments;
}

function moveAssignment(assignments, origin, destination) {
  if (!MAIN.includes(origin) || !MAIN.includes(destination) || !(origin in assignments)) throw Error('Invalid cargo move');
  const next = {...assignments};
  const occupant = Object.keys(next).find(key => key !== origin && next[key] === destination);
  const oldTarget = next[origin];
  next[origin] = destination;
  if (occupant) next[occupant] = oldTarget;
  return next;
}

function distribution(positions, assignments) {
  const sums = {total:0, forward:0, center:0, aft:0, fixed:0};
  const used = new Set();
  for (const p of positions) {
    const weight = Number(p.weight_lbs);
    if (!Number.isFinite(weight) || weight < 0) throw Error('Invalid manifest weight');
    const target = assignments[p.pos];
    if (!target || used.has(target)) throw Error('Invalid cargo allocation');
    used.add(target);
    sums.total += weight;
    if (!MAIN.includes(p.pos)) sums.fixed += weight;
    else if (MAIN.indexOf(target) < 5) sums.forward += weight;
    else if (target === 'M06') sums.center += weight;
    else sums.aft += weight;
  }
  return sums;
}

if (typeof module !== 'undefined') module.exports = {MAIN, identityAssignments, moveAssignment, distribution};

if (typeof document !== 'undefined') (function () {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pounds = value => Math.round(value).toLocaleString() + ' lb';
  let plan = null;
  let assignments = null;

  function status(message, error=false) { $('status').textContent = message; $('status').classList.toggle('error', error); }
  function changed() { return plan && plan.positions.some(p => assignments[p.pos] !== p.pos); }
  function occupantAt(pos) { return plan.positions.find(p => MAIN.includes(p.pos) && assignments[p.pos] === pos); }
  function renderDiagram() {
    const group = $('aircraftStations');
    group.replaceChildren();
      // Coordinates follow the twelve printed cargo blocks in the PAC two-view artwork.
      // Only the overlay changes; the illustration and its station labels remain intact.
      const station = (pos, x, y, width, height, view, compact=false) => {
        const p = pos === 'M12' ? plan.positions.find(unit => unit.pos === 'M12') : occupantAt(pos);
        if (!p) return;
        const mark = document.createElement('div');
        mark.className = `map-station ${view} occupied${compact ? ' compact' : ''}`;
        Object.assign(mark.style, {left:x+'%', top:y+'%', width:width+'%', height:height+'%'});
        mark.title = `${pos}: ${p.uld || 'Cargo'} · ${pounds(p.weight_lbs)}`;
        group.appendChild(mark);
      };
      MAIN.forEach((pos, i) => {
        const x = 21.42 + i * 5.14;
        station(pos, x, 38.28, 4.95, 7.81, 'side');
        station(pos, x, 64.84, 4.95, 11.82, 'top');
      });
      station('M12', 77.86, 40.72, 4.95, 5.27, 'side', true);
      station('M12', 77.86, 66.8, 4.95, 9.86, 'top', true);
  }
  function render() {
    if (!plan) return;
    const sums = distribution(plan.positions, assignments);
    $('cargoTotal').textContent = pounds(sums.total);
    $('forwardTotal').textContent = pounds(sums.forward);
    $('centerTotal').textContent = pounds(sums.center);
    $('aftTotal').textContent = pounds(sums.aft);
    $('fixedTotal').textContent = pounds(sums.fixed);
    renderDiagram();
    $('deck').innerHTML = MAIN.map((pos, i) => {
      const p = occupantAt(pos);
      const zone = i === 5 ? ' center' : i > 5 ? ' aft' : '';
      const block = p ? `<div class="block" draggable="true" data-origin="${esc(p.pos)}"><strong>${esc(p.uld || p.pos)}</strong><span class="unit">${esc(p.unit || p.awb || p.contents || 'Cargo unit')}</span><span class="weight">${pounds(p.weight_lbs)}</span><label class="unit">Move to <select data-origin="${esc(p.pos)}" aria-label="Move ${esc(p.uld || p.pos)} to position">${MAIN.map(target => `<option value="${target}"${target === pos ? ' selected' : ''}>${target}</option>`).join('')}</select></label></div>` : '<div class="empty">Open</div>';
      return `<div class="slot${zone}" data-pos="${pos}"><div class="slot-label">${pos}</div>${block}</div>`;
    }).join('');
    const fixed = plan.positions.filter(p => !MAIN.includes(p.pos));
    $('fixedWrap').hidden = fixed.length === 0;
    $('fixedDeck').innerHTML = fixed.map(p => `<div class="fixed-card"><strong>${esc(p.pos)} · ${esc(p.uld || 'Cargo')}</strong><span>${esc(p.contents || p.unit || '')}</span><span>${pounds(p.weight_lbs)}</span></div>`).join('');
    const dirty = changed();
    $('save').disabled = !dirty;
    $('reset').disabled = !dirty;
    $('auto').disabled = false;
    $('planState').textContent = dirty ? (plan.signed ? 'Unsaved changes · saving will clear the release signature' : 'Unsaved allocation changes') : 'No changes to save';
  }
  async function load() {
    status('Loading current manifest…');
    try {
      const response = await fetch('/api/load-plan', {credentials:'same-origin'});
      const body = await response.json();
      if (!response.ok) throw Error(body.error || body.message || 'Could not load the manifest');
      if (body.aircraft !== 'B738F') throw Error('This page is for a booked 737 freighter. Open the planner for your booked aircraft.');
      if (!Array.isArray(body.positions)) throw Error('The manifest response is incomplete');
      plan = body;
      assignments = identityAssignments(plan.positions);
      $('title').textContent = `Load plan · ${body.flight || 'booked flight'} · ${body.airframe || '737-800BCF'}`;
      render();
      status('Current manifest loaded. Move a block or choose Auto-allocate.');
    } catch (err) { status(err.message, true); $('title').textContent = 'Load plan unavailable'; }
  }
  $('deck').addEventListener('dragstart', event => {
    const block = event.target.closest('.block');
    if (!block) return;
    event.dataTransfer.setData('text/plain', block.dataset.origin);
    event.dataTransfer.effectAllowed = 'move';
  });
  $('deck').addEventListener('dragover', event => {
    const slot = event.target.closest('.slot');
    if (slot) { event.preventDefault(); slot.classList.add('dragover'); }
  });
  $('deck').addEventListener('dragleave', event => {
    const slot = event.target.closest('.slot');
    if (slot && !slot.contains(event.relatedTarget)) slot.classList.remove('dragover');
  });
  $('deck').addEventListener('drop', event => {
    const slot = event.target.closest('.slot');
    if (!slot) return;
    event.preventDefault();
    assignments = moveAssignment(assignments, event.dataTransfer.getData('text/plain'), slot.dataset.pos);
    render(); status(`Moved cargo to ${slot.dataset.pos}. Save to amend the release.`);
  });
  $('deck').addEventListener('change', event => {
    const select = event.target.closest('select[data-origin]');
    if (!select) return;
    assignments = moveAssignment(assignments, select.dataset.origin, select.value);
    render(); status(`Moved cargo to ${select.value}. Save to amend the release.`);
  });
  $('auto').addEventListener('click', () => {
    try { assignments = proposeAllocation(plan.positions); render(); status('Suggested distribution applied. Review it before saving.'); }
    catch (err) { status(err.message, true); }
  });
  $('reset').addEventListener('click', () => { assignments = identityAssignments(plan.positions); render(); status('Changes reset to the saved manifest.'); });
  $('save').addEventListener('click', async () => {
    $('save').disabled = true; status('Saving allocation…');
    try {
      const response = await fetch('/api/load-plan', {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify({assignments, revision:plan.revision, requested_at:plan.requested_at})});
      const body = await response.json();
      if (!response.ok) throw Error(body.error || body.message || 'Could not save allocation');
      if (!Array.isArray(body.positions)) throw Error('Saved, but the refreshed manifest was incomplete. Reload this page.');
      plan = body; assignments = identityAssignments(plan.positions); render(); status('Allocation saved. Review and sign the amended release.');
    } catch (err) { render(); status(err.message, true); }
  });
  load();
})();
