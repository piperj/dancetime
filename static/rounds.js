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

  // esc/formatTime/firstName(s)/groupHeatsBy*/getSessionType/sessionName all
  // live in schedule-shared.js -- pure, stateless, and identical to the
  // versions index.html's inline script uses, so both tabs share one copy.
  const { esc, formatTime, firstName, firstNames, groupHeatsByHeatNumber, groupHeatsBySession, getSessionType } = ScheduleShared;

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
    return ScheduleShared.sessionName(heat, ctx.heatsData);
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
  //
  // Night Club is the exception -- real data (Manhattan, cyi 904) shows its
  // sub-levels genuinely interleaved within one tight heat_number range
  // (e.g. heat 269 "Beginner1 Hustle" and heat 274 "Beginner 2 Hustle" are
  // only 5 apart, with other sub-levels' heats in between), not scheduled
  // as separate blocks the way standard families' sub-levels are. Splitting
  // by verbatim level there resets the sequencer's gap-fill state between
  // two heats that are actually right next to each other on the real
  // schedule -- so for Night Club, the fine key collapses to the broad key
  // instead, keeping one continuous RoundSequencer across the whole broad
  // tier. See thor.md 2026-08-17.
  function fineBlockKeyFor(parsed) {
    const p = parsed[0] || {};
    if (p.styleFamily === 'nightclub') return broadBlockKeyFor(parsed);
    return `${p.level || ''}||${p.styleFamily || 'unknown'}`;
  }
  function broadBlockKeyFor(parsed) {
    const p = parsed[0] || {};
    return `${broadLevel(p.level)}||${p.styleFamily || 'unknown'}`;
  }

  function renderCell({ code, contested, solo, empty, num, swapPartner, title, styleFamily, roundKey }) {
    // A dance the organizer couldn't fill (no real heat_number at all)
    // contributes no cell whatsoever -- see fillGap()'s caller.
    // `empty`: this couple has no entry for this dance, but the heat exists
    // (someone else dances it) -- shown as an outlined box with that real
    // heat's own number/dance letter, just not filled in with this
    // couple's color, so the round still reads as one continuous sequence.
    // No `data-round-key` -- an empty cell is someone else's heat, not this
    // competitor's, so there's no heat-box for it to open.
    if (empty) return `<div class="cell empty" title="${esc(title || '')}">` +
      `<span class="num">${esc(num)}</span><span class="letter">${esc(code || '?')}</span></div>`;
    const dots = [
      contested ? `<span class="dot contested" title="contested"></span>` : '',
      !contested && solo ? `<span class="dot solo" title="solo on floor"></span>` : '',
    ].join('');
    // Tappable, not just hover -- title alone doesn't work on a phone. Sized
    // to match the gutter icons (large enough to actually tap) and revealed
    // via the shared [data-reveal]/.revealed click toggle.
    const swap = swapPartner
      ? `<span class="badge-swap" data-reveal title="partner swap">🔄<span class="reveal-text">${esc(firstName(swapPartner))}</span></span>`
      : '';
    const cellColor = STYLE_COLOR[styleFamily] || STYLE_COLOR.unknown;
    // `data-round-key` is this heat_number's group key (see render()'s
    // groupData) -- the click handler below uses it to look up and drop a
    // HeatCard-rendered heat-box under this cell's row.
    return `<div class="cell" style="--cell-color:${cellColor}" title="${esc(title || '')}" data-round-key="${esc(roundKey)}">` +
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

  // Forced-round-close gap threshold for a style family the taxonomy
  // doesn't recognize (roundSequenceFor returns null, so there's no real
  // round width to measure against). Every known family's roundSequence
  // (data/dance_taxonomy.json) is 5 dances wide; 3 is a deliberately
  // smaller, arbitrary fallback -- small enough to still catch a genuine
  // multi-round skip, large enough not to fire on every single skipped
  // heat_number within one round.
  const UNKNOWN_FAMILY_ROUND_LEN = 3;

  // Below this, a gap between two rounds is just ordinary between-round
  // pacing (walking off/on the floor, judges resetting); at or above it,
  // it's a real wait worth flagging with the ⏸️ gutter icon.
  const BREAK_THRESHOLD_MINUTES = 8;

  function renderRow(row) {
    // A gap since the previous round large enough to be a real wait, not
    // just normal between-round pacing -- tap to see how long.
    const gutterIcon = row.breakMinutes
      ? `<span class="icon" data-reveal title="break">⏸️<span class="reveal-text">${row.breakMinutes} min</span></span>`
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
    // heat_number of the last real cell this couple has had placed by this
    // sequencer instance so far -- deliberately NOT row-scoped (see
    // newRow()'s doc comment below).
    let lastPlacedNum = null;
    let rowCodes = null; // Set of this couple's own dance codes already placed in the *current* row -- null-seq families only (see place())

    // `lastTime` tracks the most recent heat placed into this row (updated
    // on every place() call, not just the first) -- the caller's emitRow
    // callback uses it as the "end" side of the break-gap measurement
    // against the next row's own start time.
    //
    // `lastPlacedNum` is deliberately NOT reset here -- it tracks the last
    // real heat_number placed across the whole sequencer instance (one fine
    // block/sub-level), not just the current row. A new row starting mid-
    // block (round rollover, or a mid-row split) still needs a real anchor
    // for its own first placement's gap math -- resetting it to null on
    // every row start silently fell back to sequence-position math there,
    // which reintroduced the exact duplicate-gap-cell bug this file's
    // history already fixed once for the *within-row* case (a dance
    // dropped for everyone landing as a round's first danced position, not
    // just a middle one). See thor.md 2026-08-17.
    function newRow(time) {
      row = { cells: [], time, lastTime: time, hadMultiDance: false, roundKeys: new Set() };
      rowCodes = new Set();
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
    //
    // Walks real heat_numbers forward one at a time from `lastPlacedNum`,
    // rather than assuming one heat_number per remaining canonical
    // position -- a dance dropped for everyone doesn't reliably open (or
    // skip) a fixed number of real heat_numbers; real data has shown both
    // a genuinely unused number (a "hole") and no hole at all (the next
    // real dance renumbered right in). A hole is harmless here -- probing
    // it just finds no real heat and the walk moves on to the next number,
    // still within the iteration budget below.
    //
    // What the walk must not do is wander into the *next* round's own real
    // heats once this round's real trailing dances are exhausted -- same
    // style family, so describeIfExpected's family check alone can't tell
    // the difference. The iteration budget (`seq.length - pos`, one
    // attempt per remaining canonical position) bounds *how far* the walk
    // can reach, but a dropped dance with no hole shifts every later
    // dance's real heat_number back by one, which can let the budget still
    // land on the next round's first heat. The real signal that we've
    // crossed into a new round is a *repeated* dance code -- `rowCodes`
    // (shared with place()'s own repeat-detection) already tracks every
    // code placed in this row, real or filled; a candidate whose code is
    // already in there belongs to the next pass, not this round's tail, so
    // the walk stops there instead of rendering it. See thor.md 2026-08-17.
    function fillTrailing() {
      if (!seq || !row || row.hadMultiDance || lastPlacedNum == null) return;
      let n = lastPlacedNum;
      for (let i = pos; i < seq.length; i++) {
        n++;
        const info = describeIfExpected(n);
        if (!info) continue; // a hole -- no real heat at this number, keep walking
        if (rowCodes.has(info.code)) break; // repeated code -- this is the next round's own dance
        row.cells.push(renderCell({ empty: true, num: n, code: info.code, title: info.danceName }));
        rowCodes.add(info.code);
      }
    }

    // Shared by both gap-fill call sites below -- the real heat_number
    // distance since the last cell this couple actually danced, or null
    // when there's no real placement yet to anchor from (this sequencer
    // instance's very first placement).
    function anchoredGap(heatNumber) {
      return lastPlacedNum != null ? heatNumber - lastPlacedNum - 1 : null;
    }

    // Pads the current round out to its full canonical width before
    // emitting -- "if a competitor is in a heat, show all the boxes from
    // the round" -- then resets for the next round.
    function flush() {
      fillTrailing();
      if (row) emitRow(row);
      row = null;
      pos = 0;
    }

    // Called by the caller when it force-closes a round because a gap of a
    // full round's worth of heat_numbers (or more) means whole rounds
    // passed with no entry for this couple at all (see render()'s
    // heatNumberGap check) -- `lastPlacedNum` is stale across a skip that
    // large, so the next placement must fall back to leading-gap math
    // rather than treat the entire skipped stretch as a gap to fill.
    function resetAnchor() {
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
        if (info) {
          row.cells.push(renderCell({ empty: true, num: gapNum, code: info.code, title: info.danceName }));
          rowCodes.add(info.code);
        }
      }
    }

    // Places one physical heat_number's parsed dance(s). `roundKey` is
    // recorded onto whichever row ends up holding this heat_number's
    // cell(s) -- render()'s emitRow uses it to decide whether the row it's
    // about to emit needs the open heat-box appended after it (see
    // render()'s `openRoundKey`).
    function place({ time, heatNumber, parsed, cellFor, roundKey }) {
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
          // With a fixed seq, a row rolls over once it's full (pos reaches
          // the round's canonical width). With no seq (Night Club/unknown),
          // there's no width to measure against -- instead, this couple's
          // own code repeating within one row is the signal that a new
          // pass through the syllabus has started (see the single-dance
          // branch's identical check below for why).
          if ((seq && pos >= seq.length) || (!seq && rowCodes.has(p.code))) {
            flushGroup(); flush(); newRow(time); row.hadMultiDance = true;
          }
          groupCells.push(cellFor(p, i));
          rowCodes.add(p.code);
          pos++;
        });
        flushGroup();
        lastPlacedNum = heatNumber;
      } else {
        const p = parsed[0];
        let idx = seq ? seq.indexOf(p.code, pos) : -1;
        // Doesn't fit the remainder of this round -- close it (padded) and
        // start a fresh one. With a fixed seq, "doesn't fit" means the code
        // isn't in the remaining sequence positions. With no seq (Night
        // Club/unknown), there's no sequence to check against -- instead,
        // this couple's own code showing up a second time in one row means
        // they've wrapped back around to a dance they already danced this
        // row, i.e. a new pass through the syllabus has started (a real bug
        // against Manhattan data: Beginner1 and Beginner2 Hustle, two
        // genuinely separate heats, otherwise landed in the same row as one
        // heat_number-continuous line). See thor.md 2026-08-17.
        if ((seq && idx === -1) || (!seq && rowCodes.has(p.code))) {
          // For a null-seq family, capture any real intervening heat into
          // the row being closed *before* flushing it -- fillTrailing()
          // (called by flush()) is a no-op without a seq to measure against,
          // so this is the only chance for that gap to render anywhere.
          if (!seq) {
            const missingBeforeSplit = anchoredGap(heatNumber);
            if (missingBeforeSplit != null && missingBeforeSplit > 0) fillGap(missingBeforeSplit, heatNumber);
          }
          flush();
          // The gap up to this heat_number has already been fully paid off
          // by the fillTrailing() call inside flush() (seq case) or the
          // missingBeforeSplit fillGap() above (null-seq case) -- without
          // this reset, the unconditional anchoredGap(heatNumber) below
          // would recompute the exact same real-heat-number distance from
          // the still-stale `lastPlacedNum` and render the same gap heats
          // a second time, now attributed to the new row.
          lastPlacedNum = null;
          newRow(time);
          idx = seq ? seq.indexOf(p.code) : -1;
        }
        if (idx === -1) idx = pos; // unrecognized code/family -- just append, no gap detection

        // "missing" must be measured in real heat_numbers, not sequence
        // positions -- a sequence position that the organizers dropped
        // *entirely* (no heat_number reserved for anyone, e.g. IGB 2026
        // dropping Viennese Waltz) never opens a heat_number gap at all,
        // even though it's still a `seq` position skipped. Trusting
        // sequence-position distance there (idx - pos) computed a phantom
        // "missing" count and called fillGap on a heat_number that was
        // actually the *next* real dance already placed, re-rendering it
        // as a duplicate empty cell -- a confirmed bug against IGB 2026
        // real data (444 W, 445 T, 446 F, 447 Q with VW dropped: placing F
        // wrongly inserted a second "445 T" gap cell). Once there's a real
        // `lastPlacedNum` to anchor from, the heat_number difference is
        // ground truth for both seq and no-seq families alike. Only this
        // sequencer instance's very first placement ever (no `lastPlacedNum`
        // yet at all -- it now persists across row/round boundaries within
        // one fine block, see newRow()'s doc comment) still falls back to
        // sequence-position math for the leading-gap case (e.g. a couple
        // only dancing Jive in an Int'l Latin round) -- there's no real
        // heat_number anchor to measure from there. See thor.md 2026-08-17.
        const anchored = anchoredGap(heatNumber);
        const missing = anchored != null ? anchored : (seq ? idx - pos : 0);
        if (missing > 0) fillGap(missing, heatNumber);
        row.cells.push(cellFor(p, 0));
        rowCodes.add(p.code);
        pos = idx + 1;
        lastPlacedNum = heatNumber;
      }

      // Applied last so it always lands on whichever row actually ended up
      // holding this heat_number's cell(s), even if the sequence-mismatch
      // or multi-dance branch above rolled over into a fresh row first.
      row.lastTime = time;
      row.roundKeys.add(roundKey);
      if (seq && pos >= seq.length) flush();
    }

    return { place, flush, resetAnchor };
  }

  // Populated fresh on every render() call; read by the delegated click
  // handler below (which fires long after render() returns, on whatever
  // cell the user happens to tap) -- keyed the same way HeatCard.render's
  // own groupKey is (`allRounds.map(h => h.key).join('-')`), so a click
  // handed straight to HeatCard.render reproduces exactly the card the
  // Heats tab would show for that same physical heat.
  let groupData = new Map();

  // Which cell's heat-box (if any) is currently open -- deliberately NOT
  // reset inside render(). Any full rebuild of #scheduleContent (a search
  // change, or the one-shot "all done" rebuild in index.html) would
  // otherwise silently close a box the user just opened; surviving that
  // rebuild here is what makes render() re-embed it below instead of the
  // click handler owning it as one-off DOM state. Cleared on competitor
  // reselection via
  // Rounds.collapseOpen() (see index.html's selectHeatsCompetitor).
  let openRoundKey = null;

  function heatBoxWrapperHtml(roundKey, data) {
    return `<div class="round-heat-box" data-round-key="${esc(roundKey)}">` +
      HeatCard.render(data.primary, data.allRounds, data.eventName, data.sessionLabel) + `</div>`;
  }

  // ── Main entry point ─────────────────────────────────────────────────────
  function render(selectedCompetitor) {
    if (!selectedCompetitor || !ctx.heatsData) return '';
    groupData = new Map();

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

      // A gap between this row's start and the previous row's own last
      // placed heat, big enough to read as a real wait rather than normal
      // pacing between rounds -- flagged with the ⏸️ gutter icon (see
      // renderRow). Reset per session so a session boundary never reads as
      // a break.
      let prevRowEndTime = null;
      const emitRow = row => {
        if (prevRowEndTime != null) {
          const gapMin = Math.round((new Date(row.time) - prevRowEndTime) / 60000);
          if (gapMin >= BREAK_THRESHOLD_MINUTES) row.breakMinutes = gapMin;
        }
        prevRowEndTime = new Date(row.lastTime);
        html += renderRow(row);
        // Re-embed the open heat-box right after whichever row actually
        // holds its cell(s), so it reappears in the same spot across every
        // auto-refresh rebuild without the click handler having to fight
        // setScheduleHTML for ownership of that DOM node.
        if (openRoundKey && row.roundKeys.has(openRoundKey) && groupData.has(openRoundKey)) {
          html += heatBoxWrapperHtml(openRoundKey, groupData.get(openRoundKey));
        }
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
        // rounds into a Break" case: just close out whatever's pending, no
        // Break pill (per the user, Rounds has no break-time treatment at
        // all). Any family with no fixed round width -- Night Club (opts
        // out deliberately, see roundSequenceFor) or a genuinely
        // unrecognized 'unknown' family (no taxonomy entry at all) -- is
        // exempt from this forced close: both rely on place()'s null-seq
        // branch to fill gaps via heat_number continuity instead (see
        // place() above), so forcing a row break here would just hide real
        // intervening heats that fillGap would otherwise show -- a
        // confirmed bug against Manhattan real data (heat 269 -> 274, a
        // 4-heat gap, rendered nothing at all). See thor.md 2026-08-17.
        const styleFamily = parsed[0]?.styleFamily;
        const seqForFamily = roundSequenceFor(styleFamily);
        const roundLen = (seqForFamily || []).length || UNKNOWN_FAMILY_ROUND_LEN;
        const heatNumberGap = lastHeatNumber != null ? Math.max(0, heatNumber - lastHeatNumber - 1) : 0;
        if (seqForFamily && heatNumberGap >= roundLen) {
          // A gap this size crosses a full round's worth of heat_numbers --
          // force the round closed rather than let fillGap's within-round
          // empty-cell logic (bounded to a handful of sequence positions)
          // try to represent it. resetAnchor() clears the sequencer's own
          // memory of the last real heat placed too -- lastPlacedNum now
          // persists across row boundaries (see newRow()'s doc comment), so
          // without this the *next* placement's gap math would measure the
          // real heat_number distance across this entire skipped stretch
          // and try to render an empty cell for every real heat in it.
          sequencer.flush();
          sequencer.resetAnchor();
        }

        // Contested if *any* round this couple actually appeared in (for
        // this event) had more than one couple -- not just the physical
        // heat's last round. Mirrors HeatCard.contestedGroups()'s own rule:
        // a couple contested in the Semi-Final but recalled alone to the
        // Final is still a contested field, in progress. Checking only the
        // last round (as this used to) missed exactly that case.
        const myRoundIndices = allRounds.reduce((acc, round, ri) => {
          const hasMe = round.entries.some(e => e.event === myEvent &&
            (e.competitor1 === selectedCompetitor || e.competitor2 === selectedCompetitor));
          if (hasMe) acc.push(ri);
          return acc;
        }, []);
        const contested = myRoundIndices.some(ri => HeatCard.roundHasMultipleCouples(allRounds, ri, myEvent));

        // Same key HeatCard.render derives internally -- lets the click
        // handler hand this group straight to HeatCard.render and get back
        // exactly the card the Heats tab would show for this physical heat.
        const roundKey = allRounds.map(h => h.key).join('-');
        groupData.set(roundKey, { primary, allRounds, eventName: eventLabel(myEvent), sessionLabel: sessionType });

        const cellFor = (p, i) => renderCell({
          code: p.code, num: primary.heat_number,
          contested,
          solo: HeatCard.isSoloHeat(allRounds),
          swapPartner: partnerSwapped && i === 0 ? currentPartner : null,
          title: p.danceName,
          styleFamily: p.styleFamily,
          roundKey,
        });
        sequencer.place({ time: primary.time, heatNumber, parsed, cellFor, roundKey });

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

  // Tap-to-reveal for the break (⏸️) and partner-swap (🔄) icons -- title
  // tooltips don't work on a phone. One delegated listener toggles a
  // `.revealed` class on whatever [data-reveal] element was tapped; the
  // label itself is CSS-hidden until then (see .reveal-text in index.html).
  // Content resets every render (setScheduleHTML replaces #scheduleContent
  // wholesale), so no explicit close-on-rerender bookkeeping is needed.
  document.getElementById('scheduleContent')?.addEventListener('click', e => {
    const el = e.target.closest('[data-reveal]');
    if (el) el.classList.toggle('revealed');
  });

  // Tapping a filled cell drops the same Heats-tab heat-box card right under
  // that cell's row (one at a time -- a second tap elsewhere closes whatever
  // was already open, mirroring HeatCard's own single-expansion model).
  // Ignores taps that landed on the swap/break reveal icons above (those
  // sit inside a `.cell`, so without this guard every reveal tap would also
  // pop the heat-box open). Only patches the DOM directly for instant
  // feedback -- `openRoundKey` is the durable record; render() re-embeds it
  // from there on every subsequent call, so the box doesn't need this
  // handler's help to survive a rebuild.
  document.getElementById('scheduleContent')?.addEventListener('click', e => {
    if (e.target.closest('[data-reveal]')) return;
    const cell = e.target.closest('.cell[data-round-key]');
    if (!cell) return;
    const row = cell.closest('.heat-row');
    if (!row) return;

    const roundKey = cell.dataset.roundKey;
    const existingBox = document.querySelector('.round-heat-box[data-round-key]');
    const reopeningSame = existingBox?.dataset.roundKey === roundKey;
    if (existingBox) existingBox.remove();
    openRoundKey = reopeningSame ? null : roundKey;
    if (reopeningSame) return;

    const data = groupData.get(roundKey);
    if (!data) return;
    row.insertAdjacentHTML('afterend', heatBoxWrapperHtml(roundKey, data));
  });

  // Closes any open heat-box without needing a live #scheduleContent DOM
  // (e.g. reselecting a competitor, which rebuilds the whole subtree right
  // after) -- called from index.html's selectHeatsCompetitor alongside the
  // equivalent HeatCard.collapseAll(), so an open box never leaks across
  // to a different competitor's grid.
  function collapseOpen() {
    openRoundKey = null;
  }

  global.Rounds = { init, render, collapseOpen };
})(window);
