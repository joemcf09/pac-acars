/* PAC load planner for every freighter: move main-deck units, see a balance indicator, save to the release.
   The balance is PAC's own index (evenly spaced positions), not a certified CG. */
function balanceIndex(positions, assignments, main) {
  // 0 = all weight at the first position, 100 = all at the last; 50 = centered
  let w = 0, m = 0;
  const n = main.length;
  for (const p of positions) {
    const t = assignments[p.pos];
    const i = main.indexOf(t);
    if (i < 0) continue;
    const wt = Number(p.weight_lbs) || 0;
    w += wt; m += wt * (n > 1 ? i / (n - 1) : 0.5);
  }
  return w ? (m / w) * 100 : 50;
}
function autoLoad(positions, main) {
  const assignments = Object.fromEntries(positions.map(p => [p.pos, p.pos]));
  const movable = positions.filter(p => main.includes(p.pos)).sort((a, b) => b.weight_lbs - a.weight_lbs || a.pos.localeCompare(b.pos));
  const mid = (main.length - 1) / 2, order = [];
  for (let k = 0; order.length < main.length; k++) {
    const a = Math.floor(mid) - k, b = Math.ceil(mid) + k;
    if (a >= 0 && !order.includes(a)) order.push(a);
    if (b < main.length && !order.includes(b)) order.push(b);
  }
  movable.forEach((p, i) => { assignments[p.pos] = main[order[i]]; });
  return assignments;
}
function move(assignments, origin, target, main) {
  if (!main.includes(origin) || !main.includes(target) || !(origin in assignments)) throw Error('Invalid move');
  const next = { ...assignments };
  const occupant = Object.keys(next).find(k => k !== origin && next[k] === target);
  const old = next[origin];
  next[origin] = target;
  if (occupant) next[occupant] = old;
  return next;
}
if (typeof module !== 'undefined') module.exports = { balanceIndex, autoLoad, move };

if (typeof document !== 'undefined') (function () {
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const lb = v => Math.round(v).toLocaleString() + ' lb';
  let plan = null, asg = null, MAIN = [];
  const status = (msg, err = false) => { $('status').textContent = msg; $('status').classList.toggle('error', err); };
  const dirty = () => plan && plan.positions.some(p => asg[p.pos] !== p.pos);
  const at = pos => plan.positions.find(p => MAIN.includes(p.pos) && asg[p.pos] === pos);
  function render() {
    const n = MAIN.length, third = Math.ceil(n / 3);
    let f = 0, c = 0, a = 0, fixed = 0, total = 0;
    for (const p of plan.positions) {
      const w = Number(p.weight_lbs) || 0; total += w;
      const i = MAIN.indexOf(asg[p.pos]);
      if (!MAIN.includes(p.pos) || i < 0) fixed += w; else if (i < third) f += w; else if (i >= n - third) a += w; else c += w;
    }
    $('cargoTotal').textContent = lb(total); $('forwardTotal').textContent = lb(f); $('centerTotal').textContent = lb(c);
    $('aftTotal').textContent = lb(a); $('fixedTotal').textContent = lb(fixed);
    const idx = balanceIndex(plan.positions, asg, MAIN), off = idx - 50;
    $('needle').style.left = Math.max(0, Math.min(100, idx)) + '%';
    const cls = Math.abs(off) <= 12 ? 'ok' : Math.abs(off) <= 25 ? 'warn' : 'bad';
    $('balanceRead').innerHTML = `Balance index <b class="${cls}">${idx.toFixed(0)}</b> (50 is centered). ` +
      (cls === 'ok' ? 'The weight is well centered.' : `The weight sits ${off < 0 ? 'forward' : 'aft'}. ${cls === 'bad' ? 'Move heavy units toward the middle, or press Auto-load.' : 'Consider moving a heavy unit toward the middle.'}`);
    const heavy = [...plan.positions].filter(p => MAIN.includes(p.pos)).map(p => p.weight_lbs).sort((x, y) => y - x)[Math.max(0, Math.floor(n / 4) - 1)] || Infinity;
    $('deck').style.setProperty('--n', n);
    $('deck').innerHTML = MAIN.map(pos => {
      const p = at(pos);
      const block = p ? `<div class="block" draggable="true" data-origin="${esc(p.pos)}"><strong>${esc(p.uld || p.pos)}</strong><span class="unit">${esc(p.contents || p.unit || p.awb || 'Cargo')}</span><span class="weight">${lb(p.weight_lbs)}</span>${(p.shc || []).length ? `<span class="unit" style="display:block;margin-bottom:4px">${esc(p.shc.join(' '))}</span>` : ''}<label class="unit">Move to <select data-origin="${esc(p.pos)}" aria-label="Move ${esc(p.uld || p.pos)}">${MAIN.map(t => `<option value="${esc(t)}"${t === pos ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select></label></div>` : '<div class="empty">Open</div>';
      return `<div class="slot${p && p.weight_lbs >= heavy ? ' heavy' : ''}" data-pos="${esc(pos)}"><div class="slot-label">${esc(pos)}</div>${block}</div>`;
    }).join('');
    const fx = plan.positions.filter(p => !MAIN.includes(p.pos));
    $('fixedWrap').hidden = !fx.length;
    $('fixedDeck').innerHTML = fx.map(p => `<div class="fixed-card"><strong>${esc(p.pos)} · ${esc(p.uld || 'Cargo')}</strong><span>${esc(p.contents || p.unit || '')}</span><span>${lb(p.weight_lbs)}</span></div>`).join('');
    const d = dirty();
    $('save').disabled = !d; $('reset').disabled = !d; $('auto').disabled = false;
    $('planState').textContent = d ? (plan.signed ? 'Unsaved changes · saving clears the release signature' : 'Unsaved changes') : 'No changes to save';
  }
  async function load() {
    status('Loading your manifest…');
    try {
      const r = await fetch('/api/load-plan', { credentials: 'same-origin' }); const b = await r.json();
      if (!r.ok) throw Error(b.error || 'Could not load the manifest');
      if (!Array.isArray(b.positions) || !Array.isArray(b.main) || !b.main.length) throw Error('This flight has no main-deck positions to plan.');
      plan = b; MAIN = b.main; asg = Object.fromEntries(b.positions.map(p => [p.pos, p.pos]));
      $('eyebrow').textContent = `${(b.aircraft_name || b.aircraft || '').toUpperCase()} · CARGO PLANNING`;
      $('title').textContent = `Load plan · ${b.flight || 'booked flight'}${b.airframe ? ' · ' + b.airframe : ''}`;
      render(); status('Manifest loaded. Move a unit or press Auto-load.');
    } catch (e) { status(e.message, true); $('title').textContent = 'Load plan unavailable'; }
  }
  $('deck').addEventListener('dragstart', e => { const b = e.target.closest('.block'); if (b) { e.dataTransfer.setData('text/plain', b.dataset.origin); e.dataTransfer.effectAllowed = 'move'; } });
  $('deck').addEventListener('dragover', e => { const s = e.target.closest('.slot'); if (s) { e.preventDefault(); s.classList.add('dragover'); } });
  $('deck').addEventListener('dragleave', e => { const s = e.target.closest('.slot'); if (s && !s.contains(e.relatedTarget)) s.classList.remove('dragover'); });
  $('deck').addEventListener('drop', e => { const s = e.target.closest('.slot'); if (!s) return; e.preventDefault();
    try { asg = move(asg, e.dataTransfer.getData('text/plain'), s.dataset.pos, MAIN); render(); status(`Moved to ${s.dataset.pos}. Save to amend the release.`); } catch (err) { status(err.message, true); } });
  $('deck').addEventListener('change', e => { const sel = e.target.closest('select[data-origin]'); if (!sel) return;
    asg = move(asg, sel.dataset.origin, sel.value, MAIN); render(); status(`Moved to ${sel.value}. Save to amend the release.`); });
  $('auto').onclick = () => { asg = autoLoad(plan.positions, MAIN); render(); status('Auto-load applied. Review it, then save.'); };
  $('reset').onclick = () => { asg = Object.fromEntries(plan.positions.map(p => [p.pos, p.pos])); render(); status('Back to the saved manifest.'); };
  $('save').onclick = async () => {
    $('save').disabled = true; status('Saving…');
    try {
      const r = await fetch('/api/load-plan', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ assignments: asg, revision: plan.revision, requested_at: plan.requested_at }) });
      const b = await r.json(); if (!r.ok) throw Error(b.error || 'Could not save');
      plan = b; MAIN = b.main; asg = Object.fromEntries(b.positions.map(p => [p.pos, p.pos])); render(); status('Saved. Review and sign the amended release.');
    } catch (e) { render(); status(e.message, true); }
  };
  load();
})();
