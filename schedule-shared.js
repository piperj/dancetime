// Neutral home for rendering/logic shared symmetrically by the Heats and
// Rounds tabs, so neither tab depends on the other's module.
(function (global) {
  'use strict';

  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function formatTime(s) {
    const d = new Date(s);
    let h = d.getHours();
    const m = String(d.getMinutes()).padStart(2, '0');
    const ap = h >= 12 ? 'pm' : 'am';
    h = h % 12 || 12;
    return `${h}:${m} ${ap}`;
  }

  function firstName(name) { return String(name ?? '').split(' ')[0]; }
  function firstNames(names) { return names.map(firstName); }

  function groupHeatsByHeatNumber(sessionHeats) {
    const groups = [];
    sessionHeats.forEach(heat => {
      const prev = groups[groups.length - 1];
      if (prev && prev[0].heat_number === heat.heat_number) prev.push(heat);
      else groups.push([heat]);
    });
    return groups;
  }

  function groupHeatsBySession(heats) {
    const sessions = [];
    let cur = [], curId = null;
    heats.forEach(h => {
      if (h.session !== curId) { if (cur.length) sessions.push(cur); cur = [h]; curId = h.session; }
      else cur.push(h);
    });
    if (cur.length) sessions.push(cur);
    return sessions;
  }

  function getSessionType(t) {
    const h = new Date(t).getHours();
    return h < 12 ? 'Matinee' : h < 18 ? 'Afternoon' : 'Evening';
  }

  // NDCA's own session names say "Morning" -- competitions and dancers
  // actually call that session "Matinee", so relabel for display only.
  // `heatsData` is passed explicitly since this module holds no state of
  // its own (Heats and Rounds each own their own heatsData reference).
  function sessionName(heat, heatsData) {
    const raw = heatsData?.sessions?.[heat.session];
    return raw ? raw.replace(/\bMorning\b/, 'Matinee') : raw;
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

  // A competitor's own block of the schedule only ever sees a *slice* of a
  // session's program-marker activities ({time, title, category}) -- their
  // own block usually starts and ends well after/before the session's
  // actual first/last heat, so the raw activities lying in that slice's
  // leading/trailing edges are frequently *other* heats' award notices, not
  // theirs. Both trims agree on one rule: an 'award' notice is only
  // relevant if it's the one right after this competitor's own last heat of
  // the block; a 'top' (studio/teacher/comp-wide) ceremony is always
  // relevant regardless of position. Shared by both tabs so this rule only
  // has one implementation -- Rounds previously reimplemented only the
  // trailing half and never got the leading half at all, which showed every
  // stale award notice before a competitor's own first heat. See thor.md.

  // Leading edge (before this competitor's first heat of a block): drop
  // every 'award' entirely -- none of them are for a heat this competitor
  // danced -- keeping only 'top' ceremonies (position-independent) and
  // anything (rare) that happens to fall after the very last award.
  function trimLeadingActivities(pending) {
    let lastAwardIdx = -1;
    pending.forEach((a, i) => { if (a.category === 'award') lastAwardIdx = i; });
    return pending.filter((a, i) => a.category === 'top' || i > lastAwardIdx);
  }

  // Trailing edge (after this competitor's last heat of a block): keep
  // everything up through the first 'award' (the one covering their last
  // heat), plus any 'top' ceremony wherever it falls; drop every 'award'
  // after that first one -- those belong to other heats this competitor has
  // no stake in.
  function trimTrailingActivities(remaining) {
    const kept = [];
    let sawAward = false;
    for (const a of remaining) {
      if (a.category !== 'top' && sawAward) continue;
      kept.push(a);
      if (a.category === 'award') sawAward = true;
    }
    return kept;
  }

  global.ScheduleShared = {
    esc, formatTime, firstName, firstNames,
    groupHeatsByHeatNumber, groupHeatsBySession, getSessionType, sessionName,
    getPartner, renderBreakPill, trimLeadingActivities, trimTrailingActivities,
  };
})(window);
