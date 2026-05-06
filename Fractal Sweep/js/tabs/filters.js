import { activeSmt, activeF3, activeF4 } from '../state.js';

function updateFilterChipDeltas(D) {
  const rt = D?.recent_trades || [];
  if (!rt.length) {
    _setChipDelta('smt-checkbox', null);
    _setChipDelta('f3-checkbox', null);
    _setChipDelta('f4-checkbox', null);
    return;
  }
  function countWith(over) {
    let t = rt;
    const sm = over.smt !== undefined ? over.smt : activeSmt;
    const f3 = over.f3 !== undefined ? over.f3 : activeF3;
    const f4 = over.f4 !== undefined ? over.f4 : activeF4;
    if (sm) t = t.filter(x => x.smt === true);
    if (f3) t = t.filter(x => x.passes_f3 === true);
    if (f4) t = t.filter(x => x.passes_f4 === true);
    return t.length;
  }
  const cur = countWith({});
  _setChipDelta('smt-checkbox', countWith({ smt: !activeSmt }) - cur);
  _setChipDelta('f3-checkbox', countWith({ f3: !activeF3 }) - cur);
  _setChipDelta('f4-checkbox', countWith({ f4: !activeF4 }) - cur);
}

function _setChipDelta(checkboxId, delta) {
  const chk = document.getElementById(checkboxId);
  if (!chk) return;
  const lbl = chk.closest('label.filter-chk');
  if (!lbl) return;
  let badge = lbl.querySelector('.filter-delta');
  if (!badge) {
    badge = document.createElement('span');
    badge.className = 'filter-delta';
    lbl.appendChild(badge);
  }
  if (delta === null || delta === undefined) {
    badge.textContent = '';
    return;
  }
  if (delta === 0) {
    badge.textContent = '·0';
    badge.style.color = 'var(--text-muted)';
    badge.style.opacity = '0.55';
  } else {
    const sign = delta > 0 ? '+' : '';
    badge.textContent = `${sign}${delta}`;
    badge.style.color = delta > 0 ? 'var(--green)' : 'var(--red)';
    badge.style.opacity = '1';
  }
}

export { updateFilterChipDeltas, _setChipDelta };
