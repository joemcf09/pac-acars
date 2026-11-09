// PAC 737 load planner: live center of gravity, envelope chart and trim, from the server's weight-and-balance engine.
(function () {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const fmt = n => Math.round(n).toLocaleString('en-US');
  let timer = null, seq = 0;

  function chart(b) {
    const W = 520, H = 300, L = 54, R = 14, T = 14, B = 40;
    const env = b.envelope, kgToLb = 2.20462262;
    const all = [...env.takeoff.fwd, ...env.takeoff.aft];
    const wMin = Math.min(...all.map(p => p[0])) * kgToLb, wMax = Math.max(...all.map(p => p[0])) * kgToLb;
    const x = pct => L + (pct / 40) * (W - L - R), y = lb => T + (1 - (lb - wMin) / (wMax - wMin)) * (H - T - B);
    const poly = e => [...e.fwd, ...[...e.aft].reverse()].map(p => `${x(p[1]).toFixed(1)},${y(p[0] * kgToLb).toFixed(1)}`).join(' ');
    let g = '';
    for (let p = 0; p <= 40; p += 5) g += `<line x1="${x(p)}" x2="${x(p)}" y1="${T}" y2="${H - B}" class="cg-grid"/><text x="${x(p)}" y="${H - B + 16}" class="cg-ax" text-anchor="middle">${p}</text>`;
    for (let lb = Math.ceil(wMin / 20000) * 20000; lb <= wMax; lb += 20000) g += `<line x1="${L}" x2="${W - R}" y1="${y(lb)}" y2="${y(lb)}" class="cg-grid"/><text x="${L - 6}" y="${y(lb) + 4}" class="cg-ax" text-anchor="end">${lb / 1000}k</text>`;
    const dot = (ph, cls) => `<circle cx="${x(ph.pct_mac)}" cy="${y(ph.weight_lbs)}" r="6" class="${cls}"><title>${ph.name} ${ph.pct_mac}% MAC, ${fmt(ph.weight_lbs)} lb</title></circle>
      <text x="${x(ph.pct_mac) + 9}" y="${y(ph.weight_lbs) + 4}" class="cg-lbl">${ph.name}</text>`;
    const [zf, to, lw] = b.phases;
    return `<svg viewBox="0 0 ${W} ${H}" class="cg-chart" role="img" aria-label="CG envelope: takeoff ${to.pct_mac}% MAC, zero fuel ${zf.pct_mac}%, landing ${lw.pct_mac}%">
      ${g}<polygon points="${poly(env.takeoff)}" class="cg-env"/><polygon points="${poly(env.zero_fuel)}" class="cg-env-zf"/>
      <line x1="${x(zf.pct_mac)}" y1="${y(zf.weight_lbs)}" x2="${x(to.pct_mac)}" y2="${y(to.weight_lbs)}" class="cg-path"/>
      <line x1="${x(to.pct_mac)}" y1="${y(to.weight_lbs)}" x2="${x(lw.pct_mac)}" y2="${y(lw.weight_lbs)}" class="cg-path"/>
      ${dot(zf, 'cg-zf')}${dot(lw, 'cg-lw')}${dot(to, 'cg-to')}
      <text x="${(L + W - R) / 2}" y="${H - 6}" class="cg-ax" text-anchor="middle">Center of gravity, % MAC</text>
      <text x="14" y="${(T + H - B) / 2}" class="cg-ax" text-anchor="middle" transform="rotate(-90 14 ${(T + H - B) / 2})">Weight (lb)</text></svg>`;
  }

  function render(b, pending) {
    const box = $('cgPanel'); if (!box) return;
    if (!b) { box.hidden = true; return; }
    box.hidden = false;
    if (!b.available) { box.innerHTML = `<h2>Balance</h2><p class="notice">${esc(b.reason)}</p>`; return; }
    const [zf, to, lw] = b.phases;
    const cell = ph => `<div class="cg-cell ${ph.ok ? '' : 'bad'}"><span>CG at ${ph.name === 'ZFW' ? 'zero fuel' : ph.name === 'TOW' ? 'takeoff' : 'landing'}</span>
      <strong>${ph.pct_mac}% <small>MAC</small></strong><small>Limits ${ph.fwd_limit}–${ph.aft_limit}% · index ${ph.index}</small></div>`;
    const tow = $('cgTowMetric'); if (tow) tow.textContent = `${to.pct_mac}% MAC`;
    box.innerHTML = `<div class="panel-heading"><div><span class="eyebrow">WEIGHT AND BALANCE${pending ? ' · UPDATING…' : ''}</span><h2>Center of gravity</h2></div>
        <span class="cg-status ${b.ok ? 'ok' : 'bad'}">${b.ok ? 'Within limits' : 'Out of limits'}</span></div>
      ${b.provisional ? `<p class="notice"><strong>Provisional.</strong> ${esc(b.provisional_note)}</p>` : ''}
      <div class="cg-grid3">${cell(zf)}${cell(to)}${cell(lw)}
        <div class="cg-cell"><span>Takeoff trim</span><strong>${b.trim_units.toFixed(2)} <small>units</small></strong><small>Flaps ${esc(b.trim_flaps)} · set before takeoff</small></div></div>
      ${b.advice ? `<p class="cg-alert">${esc(b.advice)}</p>` : ''}${(b.warnings || []).map(w => `<p class="cg-alert">${esc(w)}</p>`).join('')}
      ${chart(b)}
      <p class="cg-legend"><span class="k zf"></span>Zero fuel <span class="k to"></span>Takeoff <span class="k lw"></span>Landing · shaded: takeoff envelope, dashed: zero fuel limits · DOW ${fmt(b.dow_lbs)} lb, DOI ${b.doi}</p>
      <details class="reference"><summary>Where these numbers come from</summary><p>${esc(b.note)}</p><ul>${b.sources.map(s => `<li>${esc(s)}</li>`).join('')}</ul></details>`;
  }

  window.pacBalanceUpdate = function (plan, assignments, changed) {
    if (!plan || !plan.balance) { render(null); return; }
    if (!changed) { render(plan.balance, false); return; }
    clearTimeout(timer);
    const mine = ++seq;
    timer = setTimeout(async () => {
      try {
        const r = await fetch('/api/load-plan', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({preview: true, assignments})});
        const body = await r.json();
        if (mine === seq && body.balance) render(body.balance, false);
      } catch (e) { /* keep the last figures */ }
    }, 250);
  };
})();
