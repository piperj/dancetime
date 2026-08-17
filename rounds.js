// Rounds tab -- a higher-altitude alternative to the Heats tab's text list:
// a grid of dance-letter cells, one row per round, grouped into blocks by
// style family + level. Owns grid/block construction only; delegates to
// DanceTaxonomy (dance parsing, costume-change rule), ScheduleShared (break
// pills, partner lookup) and HeatCard's static helpers (contested/solo
// rules) for everything they already own.
//
// Explicit data access, not bare-global closures -- Rounds.init({...}) is
// called once per competition load (mirroring HeatCard.init), and again
// (merged, not reset) once program markers finish loading, since that fetch
// resolves after the first init call. See thor.md 2026-08-16.
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

  // ── Small physical-heat helpers, duplicated from index.html's inline
  // script rather than reached across the script boundary (heat-card.js's
  // existing precedent) -- pure over their inputs, no shared state. ────────
  function partitionRounds(sorted) {
    const partitions = [];
    let cur = [], names = new Set();
    for (const h of sorted) {
      if (names.has(h.round)) { partitions.push(cur); cur = []; names = new Set(); }
      cur.push(h);
      names.add(h.round);
    }
    if (cur.length) partitions.push(cur);
    return partitions;
  }

  function splitHeatRounds(sorted, anchorKey) {
    const partitions = partitionRounds(sorted);
    return partitions.find(p => p.some(h => h.key === anchorKey)) || partitions[0] || sorted;
  }

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

  // ── Module context, set via init() ───────────────────────────────────────
  let ctx = {
    cyi: null, heatsData: null, heatsByKey: {}, heatsByNumber: {},
    floorPositionByKey: {}, sessionFirstHeatTime: {}, programMarkers: null,
  };

  function init(opts) {
    ctx = Object.assign({}, ctx, opts);
    if (opts.heatsData) {
      ctx.heatsByNumber = {};
      (opts.heatsData.heats || []).forEach(h => {
        (ctx.heatsByNumber[h.heat_number] ??= []).push(h);
      });
    }
  }

  function sessionName(heat) {
    const raw = ctx.heatsData?.sessions?.[heat.session];
    return raw ? raw.replace(/\bMorning\b/, 'Matinee') : raw;
  }

  function eventLabel(idx) {
    return ctx.heatsData?.events?.[idx] ?? '';
  }

  function getHeatRounds(heatNumber, session, fallback) {
    const sorted = (ctx.heatsByNumber[heatNumber] || fallback)
      .filter(h => h.session === session)
      .sort((a, b) => a.time < b.time ? -1 : a.time > b.time ? 1 : 0);
    return splitHeatRounds(sorted, fallback?.[0]?.key);
  }

  // ── Style presentation ───────────────────────────────────────────────────
  // Country Western folds into Night Club as one category (not its own
  // family) -- data/dance_taxonomy.json's "countryWestern" marker resolves
  // to the "nightclub" family directly, so styleFamily is always
  // 'nightclub' here regardless of whether the source event carried a
  // "C/W" marker or none at all. See thor.md 2026-08-16.
  const STYLE_COLOR = {
    amSmooth: '#3bb8c9', amRhythm: '#5fb87c', intlBallroom: '#3f7ce0',
    intlLatin: '#1c7a46', nightclub: '#a24f81', unknown: '#9ca3af',
  };
  const STYLE_LABEL = {
    amSmooth: 'American Smooth', amRhythm: 'American Rhythm',
    intlBallroom: 'International Ballroom', intlLatin: 'International Latin',
    nightclub: 'Night Club', unknown: '',
  };
  // Night Club deliberately opts out of the fixed round-sequence grid: its
  // syllabus (11 possible dances) is sparse and irregular per couple, so a
  // canonical-order layout with a slot for every dance reads as more noise
  // than signal -- per the user, "a Night Club round is a single line".
  // Passing `seq: null` to RoundSequencer already gets exactly that
  // behavior for free (flat sequential append, no gap detection, no round-
  // boundary resets from filling the sequence).
  function roundSequenceFor(styleFamily) {
    if (styleFamily === 'nightclub') return null;
    return DanceTaxonomy.roundSequence(styleFamily);
  }

  // A block groups by the *broad* syllabus tier (Bronze/Silver/Gold/...),
  // not the verbatim level phrase -- "Cl. Pre-Bronze", "Cl. Full Bronze",
  // "Cl. Intermediate Bronze" and even a no-separator "PreBronze" are all
  // just "Bronze" for grouping and display purposes; a dancer thinks of the
  // whole Bronze/International block as one category, not three. Plain
  // substring match, deliberately no \b word-boundary -- a boundary would
  // require a separator before "Bronze" and miss the concatenated
  // "PreBronze" form seen in real event strings. "Newcomer", "Novice",
  // "Beginner 1" and "Beginner 2" are all one entry-level tier too, shown
  // as "Beginner". Checked in order; the first matching pattern wins.
  const BROAD_LEVEL_GROUPS = [
    { label: 'Beginner', match: /Newcomer|Novice|Beginner/i },
    { label: 'Bronze', match: /Bronze/i },
    { label: 'Silver', match: /Silver/i },
    { label: 'Gold', match: /Gold/i },
    { label: 'Open', match: /Open/i },
  ];
  function broadLevel(level) {
    const s = String(level || '');
    for (const { label, match } of BROAD_LEVEL_GROUPS) {
      if (match.test(s)) return label;
    }
    return s; // unrecognized phrasing -- fall back to showing it verbatim
  }

  // Two different keys, deliberately kept separate: the *broad* key groups
  // Pre-Bronze/Full Bronze/Intermediate Bronze under one visible header
  // ("Bronze International Ballroom"), but each of those sub-levels still
  // has its own independent heat_number range/round structure on the
  // actual schedule -- collapsing them onto one RoundSequencer would treat
  // unrelated sub-levels' heat_numbers as gaps within the same round (a
  // real bug caught by checking against real data, see thor.md 2026-08-16).
  // So the *fine* key (verbatim level) still drives when a new
  // RoundSequencer starts; the broad key only drives when a new header
  // actually prints.
  function fineBlockKeyFor(parsed) {
    const p = parsed[0] || {};
    return `${p.level || ''}||${p.styleFamily || 'unknown'}`;
  }
  function broadBlockKeyFor(parsed) {
    const p = parsed[0] || {};
    return `${broadLevel(p.level)}||${p.styleFamily || 'unknown'}`;
  }

  function renderCell({ code, contested, solo, empty, num, badgeSwap, title, styleFamily }) {
    // A dance the organizer couldn't fill (no real heat_number at all)
    // contributes no cell whatsoever -- see fillGap()'s caller.
    // `empty`: this couple has no entry for this dance, but the heat exists
    // (someone else dances it) -- shown as an outlined box with that real
    // heat's own number/dance letter, just not filled in with this
    // couple's color, so the round still reads as one continuous sequence.
    if (empty) return `<div class="cell empty" title="${esc(title || '')}">` +
      `<span class="num">${esc(num)}</span><span class="letter">${esc(code || '?')}</span></div>`;
    const dots = [
      contested ? `<span class="dot contested" title="contested"></span>` : '',
      !contested && solo ? `<span class="dot solo" title="solo on floor"></span>` : '',
    ].join('');
    const swap = badgeSwap ? `<span class="badge-swap" title="partner swap">🔁</span>` : '';
    const cellColor = STYLE_COLOR[styleFamily] || STYLE_COLOR.unknown;
    return `<div class="cell" style="--cell-color:${cellColor}" title="${esc(title || '')}">` +
      `<span class="num">${esc(num)}</span><span class="letter">${esc(code || '?')}</span>${swap}${dots}</div>`;
  }

  // Wraps a multi-dance grouped heat's exploded cells (e.g. one heat_number
  // covering W,T,F,VW) in one bounding box spanning that many grid tracks,
  // so the group still visually reads as one heat rather than N unrelated
  // cells sitting side by side.
  function renderMultiDanceGroup(cells) {
    return `<div class="multi-dance-group" style="grid-column:span ${cells.length}">${cells.join('')}</div>`;
  }

  // Grid width: always a fixed 7 columns, so a cell's on-screen size is
  // driven by the container width alone ((width - gutter) / 7), not by how
  // many dances happen to be in any one row -- a lone single-dance row
  // renders at the same cell size as a full 5-dance Ballroom round, it just
  // leaves the trailing columns empty rather than stretching to fill them.
  // A round with more than 7 dances (Night Club) wraps onto additional grid
  // rows automatically, since the grid only ever declares 7 column tracks.
  const MAX_COLS = 7;

  function renderRow(row) {
    const gutterIcon = row.isFirst
      ? `<span class="icon" title="first heat">▶️</span>`
      : row.swapped
        ? `<span class="icon" title="partner swap in this round">🔁</span>`
        : '';
    return `<div class="heat-row" data-now-time="${esc(row.time)}">` +
      `<div class="gutter">${gutterIcon}</div>` +
      `<div class="cells" style="grid-template-columns:repeat(${MAX_COLS},1fr)">${row.cells.join('')}</div></div>`;
  }

  // ── Round-sequence cell layout ───────────────────────────────────────────
  // The competition organizes heats into rounds of fixed size (one round =
  // one pass through a style family's canonical dance order, e.g.
  // International Ballroom: W, T, VW, F, Q), always in that same order --
  // this is a property of the competition's schedule, not of any one
  // couple's own dancing. So every round this couple takes part in renders
  // a cell for each dance they danced, plus an `empty` outlined box (that
  // heat's own number/dance letter shown) for any canonical position where
  // a real heat_number exists (someone else dances it) but this couple has
  // no entry -- a different partner's heat, or their syllabus just doesn't
  // include that dance. `describeGapHeat` resolves which real heat sits at
  // each missing position by walking the actual integer gap between the
  // last cell placed and this one.
  //
  // A position with no real heat_number at all (the organizer never filled
  // it) contributes no cell whatsoever -- the round just reads left-
  // aligned, shorter than the family's full canonical width, rather than
  // showing a placeholder for a dance that plain never happened. Per the
  // user, a horizontal-line placeholder there read as confusing, especially
  // for a sparse Night Club round (which also skips round-sequence layout
  // entirely -- see render()'s `seq` construction).
  //
  // A round the couple sits out *entirely* never gets a row at all (no row
  // is created until a real dance is placed) -- any stretch of fully-empty
  // rounds collapses into a single Break marker, driven by heatNumberGap
  // crossing a full round's worth of heat_numbers (see render()), not by
  // floor-position/rest-time heuristics.
  function RoundSequencer(emitRow, seq, describeGapHeat, expectedFamily) {
    let pos = 0;
    let row = null;
    let lastPlacedNum = null; // heat_number of the last real cell placed in the *current* row

    // isFirst (the ▶️ "first heat" gutter icon) is a session-wide property,
    // not per-block -- left false here and set by the caller's emitRow
    // callback instead, since a fresh RoundSequencer is constructed on
    // every block change within one session.
    function newRow(time) {
      row = { cells: [], time, isFirst: false, swapped: false, hadMultiDance: false };
      lastPlacedNum = null;
    }

    // A `removed` position (no real heat_number found, for anyone, at that
    // number) contributes no cell at all. Validated against `expectedFamily`,
    // not just `seq.includes(code)` -- several families reuse the same
    // one-letter code (e.g. "W" is Waltz in both American Smooth and
    // International Ballroom), so a code match alone can't tell a genuine
    // gap-fill from a heat_number lookup that wandered into a completely
    // different round after this one ended (a confirmed bug -- see
    // thor.md 2026-08-17).
    function describeIfExpected(gapNum) {
      const info = gapNum != null ? describeGapHeat(gapNum) : null;
      return info && info.styleFamily === expectedFamily ? info : null;
    }

    // Every canonical position in the round is expected to show a box --
    // "if a competitor is in a heat, show all the boxes from the round,"
    // filled for what they danced, empty (real heat, someone else's) for
    // what they didn't -- and a position is only skipped entirely when the
    // organizers truly never scheduled a heat there for anyone. Applies to
    // the *tail* of the round too (after the couple's own last dance, up to
    // the round's full width), not just gaps between two of their own
    // cells -- see thor.md 2026-08-17.
    //
    // Skipped entirely when this row contained a multi-dance grouped heat:
    // that branch (below) increments `pos` by one per code in whatever
    // order the event string gave them, not by matching each code to its
    // real `seq` index -- so `pos` no longer reliably means "how far into
    // the canonical sequence we are." Trusting it here wandered forward
    // into the *next* physical round's real heat_numbers and mislabeled
    // them as this round's missing tail (a confirmed bug against IGB 2026
    // real data -- see thor.md 2026-08-17).
    function fillTrailing() {
      if (!seq || !row || row.hadMultiDance) return;
      for (let i = pos; i < seq.length; i++) {
        const gapNum = lastPlacedNum != null ? lastPlacedNum + 1 + (i - pos) : null;
        const info = describeIfExpected(gapNum);
        if (info) row.cells.push(renderCell({ empty: true, num: gapNum, code: info.code, title: info.danceName }));
      }
    }

    // Pads the current round out to its full canonical width before
    // emitting -- "if a competitor is in a heat, show all the boxes from
    // the round" -- then resets for the next round.
    function flush() {
      fillTrailing();
      if (row) emitRow(row);
      row = null;
      pos = 0;
      lastPlacedNum = null;
    }

    // Anchored off `heatNumber` (the position actually being placed right
    // now) and counted *backward*, not forward from `lastPlacedNum` --
    // `lastPlacedNum` is null for a row's very first placement, which used
    // to make every leading gap unfillable even when the couple's first
    // dance of a round was its last canonical position (e.g. only dancing
    // Jive in an Int'l Latin round that also has Cha Cha/Samba/Rumba/Paso
    // Doble): with no lastPlacedNum to anchor from, none of those leading
    // boxes ever rendered (a confirmed bug against Manhattan real data --
    // see thor.md 2026-08-17). Counting backward from `heatNumber` needs no
    // prior placement and can never reach `heatNumber` itself (the minimum
    // subtracted term is 1), so the old `gapNum < heatNumber` bound check
    // is now automatic rather than a separate guard.
    function fillGap(missing, heatNumber) {
      for (let i = 0; i < missing; i++) {
        const gapNum = heatNumber - (missing - i);
        const info = describeIfExpected(gapNum);
        if (info) row.cells.push(renderCell({ empty: true, num: gapNum, code: info.code, title: info.danceName }));
      }
    }

    // Places one physical heat_number's parsed dance(s).
    function place({ time, heatNumber, parsed, cellFor, swapped }) {
      if (!row) newRow(time);

      if (parsed.length > 1) {
        // Multi-dance grouped heat: consecutive run, no gap detection --
        // real multi-dance code lists aren't always given in canonical
        // order (see thor.md 2026-08-16), so per-position gap/skip
        // detection meant for one-dance-per-heat_number rounds doesn't
        // generalize cleanly here. All cells from one heat_number are
        // wrapped in one bounding box (renderMultiDanceGroup) so the group
        // still reads as one heat, even if a rare column-overflow forces it
        // to split across two rows.
        row.hadMultiDance = true;
        let groupCells = [];
        const flushGroup = () => {
          if (groupCells.length) { row.cells.push(renderMultiDanceGroup(groupCells)); groupCells = []; }
        };
        parsed.forEach((p, i) => {
          if (seq && pos >= seq.length) { flushGroup(); flush(); newRow(time); row.hadMultiDance = true; }
          groupCells.push(cellFor(p, i));
          pos++;
        });
        flushGroup();
        lastPlacedNum = heatNumber;
      } else {
        const p = parsed[0];
        let idx = seq ? seq.indexOf(p.code, pos) : -1;
        if (seq && idx === -1) {
          // Doesn't fit the remainder of this round -- close it (padded)
          // and start a fresh one, searching from the top of the sequence.
          flush();
          newRow(time);
          idx = seq.indexOf(p.code);
        }
        if (idx === -1) idx = pos; // unrecognized code/family -- just append, no gap detection

        const missing = idx - pos;
        if (missing > 0) fillGap(missing, heatNumber);
        row.cells.push(cellFor(p, 0));
        pos = idx + 1;
        lastPlacedNum = heatNumber;
      }

      // Applied last so it always lands on whichever row actually ended up
      // holding this heat_number's cell(s), even if the sequence-mismatch
      // or multi-dance branch above rolled over into a fresh row first.
      if (swapped) row.swapped = true;
      if (seq && pos >= seq.length) flush();
    }

    return { place, flush };
  }

  // ── Main entry point ─────────────────────────────────────────────────────
  function render(selectedCompetitor) {
    if (!selectedCompetitor || !ctx.heatsData) return '';

    const myHeatKeys = ctx.heatsData.competitor_heats[selectedCompetitor] || [];
    const myHeats = myHeatKeys.map(k => ctx.heatsByKey[k]).filter(Boolean);
    myHeats.sort((a, b) => new Date(a.time) - new Date(b.time));
    if (!myHeats.length) return '<p class="text-gray-500 text-center">No heats found for this competitor</p>';

    const sessions = groupHeatsBySession(myHeats);
    let html = '';

    sessions.forEach(sessionHeats => {
      const first = sessionHeats[0];
      const last = sessionHeats[sessionHeats.length - 1];
      const sessionType = sessionName(first) || getSessionType(first.time);
      const code = first.session;

      const partners = new Set();
      sessionHeats.forEach(h => { const p = ScheduleShared.getPartner(selectedCompetitor, h); if (p) partners.add(p); });
      const who = partners.size ? firstNames(Array.from(partners)).join(', ') : 'Solo';

      // Same "blue-box" markup Heats uses for its own session header --
      // Rounds previously had its own gradient .session-header style; the
      // user wants one consistent look between the two tabs.
      html += `<div class="blue-box">` +
        `<div class="text-sm">${esc(sessionType)} · ${esc(formatTime(first.time))} - ${esc(formatTime(last.time))}</div>` +
        `<div class="font-semibold">${esc(who)}</div></div>`;

      const acts = ctx.programMarkers?.bySession?.[code]?.activities || [];
      let actIdx = 0;
      const addActivity = a => {
        html += `<div class="awards-row" data-now-time="${esc(a.time)}"><div class="gutter"><span class="icon" title="awards">🏆</span></div><div class="marker">${esc(a.title)} · ${esc(formatTime(a.time))}</div></div>`;
      };

      let sessionEmittedRow = false;
      const emitRow = row => {
        row.isFirst = !sessionEmittedRow;
        sessionEmittedRow = true;
        html += renderRow(row);
      };
      // Resolves which real heat (if any) sits at a given heat_number, for
      // labeling `empty` cells -- any entry works, since we only need that
      // heat's own dance code/name, not who's dancing it. Includes
      // styleFamily so callers can reject a match that landed in some other
      // family's heat -- several families reuse the same one-letter code
      // (e.g. "W" is Waltz in both American Smooth and International
      // Ballroom), so code alone isn't enough to confirm it belongs to
      // *this* round. See thor.md 2026-08-17.
      const describeGapHeat = heatNumber => {
        const heats = (ctx.heatsByNumber[heatNumber] || []).filter(h => h.session === code);
        const entry = heats[0]?.entries?.[0];
        if (!entry) return null;
        const p0 = DanceTaxonomy.parseEvent(eventLabel(entry.event))[0];
        return p0 ? { code: p0.code, danceName: p0.danceName, styleFamily: p0.styleFamily } : null;
      };

      let sequencer = RoundSequencer(emitRow, null, describeGapHeat, null);
      let currentFineKey = null, currentBroadKey = null, currentFamily = null;
      let lastPartner = null, lastHeatNumber = null, isFirstGroup = true;

      groupHeatsByHeatNumber(sessionHeats).forEach(group => {
        const allRounds = getHeatRounds(group[0].heat_number, group[0].session, group);
        const primary = allRounds[0];
        const heatNumber = parseInt(primary.heat_number, 10);

        const pending = [];
        while (actIdx < acts.length && acts[actIdx].time <= primary.time) { pending.push(acts[actIdx]); actIdx++; }
        if (pending.length) sequencer.flush();
        // The competitor's own block usually starts well after the
        // session's actual first heat -- on the very first group, drop
        // stale award notices for heats that happened before their block
        // even started (only 'top' ceremonies survive there). Mirrors
        // generateSchedule()'s identical leading-edge trim in index.html --
        // shared with ScheduleShared so both tabs use one implementation.
        // See thor.md.
        (isFirstGroup ? ScheduleShared.trimLeadingActivities(pending) : pending).forEach(addActivity);
        isFirstGroup = false;

        const myEntry = group.reduce(
          (found, h) => found || h.entries.find(e => e.competitor1 === selectedCompetitor || e.competitor2 === selectedCompetitor),
          null
        );
        const myEvent = myEntry?.event;
        const currentPartner = group.reduce((found, h) => found || ScheduleShared.getPartner(selectedCompetitor, h), null);
        const partnerSwapped = lastPartner !== null && currentPartner !== lastPartner;

        const parsed = DanceTaxonomy.parseEvent(eventLabel(myEvent));
        const fineKey = fineBlockKeyFor(parsed);
        if (fineKey !== currentFineKey) {
          // Flush the outgoing sub-level's own sequencer *before* printing
          // anything new -- otherwise its trailing partial round lands in
          // the HTML after a new header, visually misattributed to the
          // wrong block. See thor.md 2026-08-16.
          sequencer.flush();
          const p0 = parsed[0] || {};
          const broadKey = broadBlockKeyFor(parsed);
          // Only a *broad* change (Bronze -> Silver, or a style-family
          // change) prints a new header -- Pre-Bronze -> Full Bronze ->
          // Intermediate Bronze all share one "Bronze International
          // Ballroom" header, since a dancer thinks of that as one
          // category, even though each sub-level still gets its own
          // RoundSequencer (see fineBlockKeyFor's doc comment above).
          if (broadKey !== currentBroadKey) {
            const costumeChange = currentFamily !== null &&
              DanceTaxonomy.styleFamilyChanged([{ styleFamily: currentFamily }], parsed);
            const styleColor = STYLE_COLOR[p0.styleFamily] || STYLE_COLOR.unknown;
            const styleLabel = [broadLevel(p0.level), STYLE_LABEL[p0.styleFamily]].filter(Boolean).join(' ') || 'Unknown';
            html += `<div class="style-block" style="--style-color:${styleColor}">` +
              `<div class="gutter">${costumeChange ? '<span class="icon" title="costume change">👗</span>' : ''}</div>` +
              `<div class="style-label">${esc(styleLabel)} · ${esc(formatTime(primary.time))}</div></div>`;
            currentBroadKey = broadKey;
            currentFamily = p0.styleFamily;
          }
          currentFineKey = fineKey;
          sequencer = RoundSequencer(emitRow, roundSequenceFor(p0.styleFamily), describeGapHeat, p0.styleFamily);
          lastHeatNumber = null; // a new sub-level always starts its own first round, no cross-block gap math
        }

        // A gap of a full round's worth of heat_numbers (or more) means
        // whole rounds passed with no entry for this couple at all -- those
        // rounds never got a row in the first place (place() only creates
        // one on a real dance), so this is exactly the "collapse empty
        // rounds into a Break" case: just close out whatever's pending and
        // show one marker, not a floor-position/rest-time heuristic. Night
        // Club and any unrecognized family have no round length at all
        // (roundSequenceFor returns null) -- fall back to a fixed
        // small-gap threshold instead of firing on every single skipped
        // heat_number.
        const roundLen = (roundSequenceFor(parsed[0]?.styleFamily) || []).length || 3;
        const heatNumberGap = lastHeatNumber != null ? Math.max(0, heatNumber - lastHeatNumber - 1) : 0;
        if (heatNumberGap >= roundLen) {
          // A gap this size crosses a full round's worth of heat_numbers --
          // force the round closed rather than let fillGap's within-round
          // empty-cell logic (bounded to a handful of sequence positions)
          // try to represent it. No Break pill in Rounds -- per the user,
          // the tab has no break-time treatment at all.
          sequencer.flush();
        }

        const cellFor = (p, i) => renderCell({
          code: p.code, num: primary.heat_number,
          contested: HeatCard.roundHasMultipleCouples(allRounds, allRounds.length - 1, myEvent),
          solo: HeatCard.isSoloHeat(allRounds),
          badgeSwap: partnerSwapped && i === 0,
          title: p.danceName,
          styleFamily: p.styleFamily,
        });
        sequencer.place({ time: primary.time, heatNumber, parsed, cellFor, swapped: partnerSwapped });

        lastPartner = currentPartner;
        lastHeatNumber = heatNumber;
      });

      sequencer.flush();
      // Past this competitor's last heat of the session, only the notice
      // covering *that* heat is relevant -- see trimTrailingActivities's
      // doc comment in schedule-shared.js.
      ScheduleShared.trimTrailingActivities(acts.slice(actIdx)).forEach(addActivity);
    });

    return html;
  }

  global.Rounds = { init, render };
})(window);
