// Neutral home for rendering/logic shared symmetrically by the Heats and
// Rounds tabs, so neither tab depends on the other's module.
(function (global) {
  'use strict';

  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Session-level partner lookup: who `competitor` is dancing with in `heat`,
  // or null if they don't appear in it. Moved from index.html's inline
  // script (previously a bare global) so both tabs call the one
  // implementation -- no duplicated partner-swap detection logic.
  function getPartner(competitor, heat) {
    const e = heat.entries.find(e => e.competitor1 === competitor || e.competitor2 === competitor);
    if (!e) return null;
    return e.competitor1 === competitor ? e.competitor2 : e.competitor1;
  }

  // The dashed-line + centered-pill break visual from the Rounds mockup,
  // now shared by both tabs. `time` is the data-now-time stop this pill
  // represents (the incoming heat's own time, matching the convention used
  // by every other stop in the schedule).
  function renderBreakPill({ minutes, label, time }) {
    const text = label || `${minutes} min break`;
    return `<div class="break-row" data-now-time="${esc(time)}"><div class="line"></div><div class="pill">${esc(text)}</div><div class="line"></div></div>`;
  }

  global.ScheduleShared = { getPartner, renderBreakPill };
})(window);
