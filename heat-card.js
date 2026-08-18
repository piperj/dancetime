// Heat-card rendering + click behavior, extracted out of index.html's inline
// script. One HeatCard instance per physical heat, kept in a registry that
// survives full-HTML rebuilds (a search change, tab switch, or the one-shot
// "all done" rebuild), so expansion state and fetched judges-score data
// persist across renders without any DOM-side state (no ids to look up, no
// onclick strings to build/escape).
//
// Click model (all four heat-card views: Studio, Bib, All-Heats, individual
// competitor):
//   - the couples-count pill is the only thing that opens the couples list
//   - a Contested pill is the only thing that opens its judges-score panel
//     (inert -- no click -- until the event has at least one posted result)
//   - clicking anything else on the card (blank space, a couples row, inside
//     an open judges panel) unconditionally closes whatever's open; it never
//     opens anything
//   - at most one expansion (couples list, or one specific judges panel) is
//     open per card at a time
(function (global) {
  'use strict';

  // Local duplicates of small generic helpers, matching the existing
  // judges-scores.js precedent (it already duplicates esc/rankPrefix rather
  // than reach across the script boundary into index.html).
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

  function coupleName(comp1, comp2) {
    return comp2 ? `${comp1} & ${comp2}` : comp1;
  }

  const ORDINAL_SFX = ['th', 'st', 'nd', 'rd', 'th'];
  function ordinal(n) {
    const v = n % 100;
    return n + (v >= 11 && v <= 13 ? 'th' : ORDINAL_SFX[Math.min(n % 10, 4)]);
  }

  function rankPrefix(r) {
    return r === 1 ? '🥇' : r === 2 ? '🥈' : r === 3 ? '🥉' : null;
  }

  // Group label uses the *field's* best placement (lowest result), not any
  // one competitor's -- the pill is no longer tied to a selected competitor.
  function contestedLabel(result) {
    const r = parseInt(result);
    if (isNaN(r)) return 'Contested';
    const medal = rankPrefix(r);
    return medal ? `${medal} Contested` : `${ordinal(r)} Contested`;
  }

  function byResult(a, b) {
    const ra = parseInt(a.result), rb = parseInt(b.result);
    const aAdv = isNaN(ra), bAdv = isNaN(rb);
    if (aAdv && bAdv) return 0;
    if (aAdv) return -1;
    if (bAdv) return 1;
    return ra - rb;
  }

  // ── Module state ────────────────────────────────────────────────────────
  const registry = new Map(); // groupKey -> HeatCard
  let ctx = { cyi: null, eventLabels: [] }; // set once per competition via init()

  class HeatCard {
    // Search context, shared by every instance -- describes who/what the
    // current view is scoped to, set once per render pass by the caller
    // (generateStudioSchedule/generateBibSchedule/generateAllHeatsSchedule/
    // generateSchedule) via HeatCard.setContext(). A contested group is only
    // shown if it's relevant to this context -- e.g. searching a bib on a
    // multi-event heat only shows the pill for *that bib's* event, not an
    // unrelated event sharing the same physical heat.
    //   { type: 'all' }                                -- All-Heats: no filter
    //   { type: 'studio', members: Set<name> }          -- Studio view
    //   { type: 'bib', bib: string }                    -- Bib view
    //   { type: 'competitor', name: string }            -- individual competitor view
    static context = { type: 'all' };

    static isRelevant(entry) {
      const ctx = HeatCard.context;
      switch (ctx.type) {
        case 'competitor': return entry.competitor1 === ctx.name || entry.competitor2 === ctx.name;
        case 'bib': return entry.bib === ctx.bib;
        case 'studio': return ctx.members.has(entry.competitor1) || ctx.members.has(entry.competitor2);
        default: return true; // 'all'
      }
    }

    // Pure, instance-free: true iff more than one couple danced this event
    // within this one round -- the same rule contestedGroups() uses
    // (byRound.length > 1), stripped down for callers (Rounds' static amber
    // dot) that don't need the click-panel wrapping. `allRounds` is a
    // physical heat's rounds (as passed to HeatCard.render); `roundIndex`
    // picks one of them; `eventId` is the event index to check.
    static roundHasMultipleCouples(allRounds, roundIndex, eventId) {
      const round = allRounds[roundIndex];
      if (!round) return false;
      return round.entries.filter(e => e.event === eventId).length > 1;
    }

    // Pure, instance-free: true iff exactly one couple danced the last
    // (most advanced) round of this physical heat -- the same rule
    // renderCouplesBadge() uses (this.n === 1), stripped down for Rounds'
    // static blue solo dot.
    static isSoloHeat(allRounds) {
      return allRounds[allRounds.length - 1]?.entries.length === 1;
    }

    constructor(key) {
      this.key = key;
      this.expansion = null; // null | 'couples' | a contested-group panelKey
      this.judgesCache = new Map(); // panelKey -> { loading } | { error } | { html }
    }

    update({ primary, allRounds, eventName, sessionLabel }) {
      this.primary = primary;
      this.allRounds = allRounds;
      this.eventName = eventName;
      this.sessionLabel = sessionLabel;
      this.n = allRounds[allRounds.length - 1].entries.length;
    }

    // One pill per contested *event* -- collapsed across every round of this
    // heat, not one pill per round. A couple that advances from a contested
    // Semi-Final to a contested Final is the same contested field, still in
    // progress; showing two separate pills for it (one dead-ended in the
    // semi, since JudgesScores.fetchJudgesData always returns the whole
    // heat's rounds together regardless which pill you click) was a real
    // regression found by spot-checking real data (CYI 373 heat 628,
    // searching "Jasher Kuehn" -- recalled from Semi-Final to Final). Each
    // resulting group is still gated by HeatCard.isRelevant, so a
    // competitor/bib search (always exactly one couple) yields at most one
    // pill; only a studio search spanning two simultaneous events can yield
    // more than one.
    contestedGroups() {
      // Flatten every round's entries into one list per event id, each
      // tagged with which round (and that round's position) it came from.
      const byEvent = new Map(); // event id -> [{ round, roundIndex, entry }]
      this.allRounds.forEach((round, roundIndex) => {
        round.entries.forEach(entry => {
          if (!byEvent.has(entry.event)) byEvent.set(entry.event, []);
          byEvent.get(entry.event).push({ round, roundIndex, entry });
        });
      });

      const groups = [];
      byEvent.forEach((appearances, evt) => {
        // Contested if any single round had more than one couple in this
        // event -- a couple who danced alone every round they appear in
        // was never actually contested, even if the event recurs.
        const appearedInRounds = new Set(appearances.map(a => a.roundIndex));
        const contested = [...appearedInRounds].some(ri => HeatCard.roundHasMultipleCouples(this.allRounds, ri, evt));
        if (!contested) return;

        const relevant = appearances.filter(a => HeatCard.isRelevant(a.entry));
        if (relevant.length === 0) return;

        // Final results trump Semi-Final results, if available: walk rounds
        // latest-first and use the first one where a relevant entry has a
        // posted result. Falls back to the latest relevant round, unscored,
        // if nothing's been judged yet.
        const roundIndices = [...new Set(relevant.map(a => a.roundIndex))].sort((a, b) => b - a);
        let chosen = null, clickable = false;
        for (const ri of roundIndices) {
          const scored = relevant.filter(a => a.roundIndex === ri && a.entry.result !== '');
          if (scored.length > 0) {
            chosen = scored.reduce((best, a) => parseInt(a.entry.result) < parseInt(best.entry.result) ? a : best);
            clickable = true;
            break;
          }
        }
        if (!chosen) chosen = relevant.find(a => a.roundIndex === roundIndices[0]);

        groups.push({
          panelKey: `${this.key}__evt${evt}`,
          heatNumber: chosen.round.heat_number,
          anchorName: chosen.entry.competitor1,
          clickable,
          labelResult: clickable ? chosen.entry.result : undefined,
        });
      });
      return groups;
    }

    couplesOpen() { return this.expansion === 'couples'; }
    panelOpen(panelKey) { return this.expansion === panelKey; }
    isExpanded() { return this.expansion !== null; }

    toggleCouples() {
      this.expansion = this.couplesOpen() ? null : 'couples';
    }

    close() { this.expansion = null; }

    // Accordion via the single `expansion` field -- setting it to a new
    // panelKey (or 'couples') automatically supersedes whatever was open
    // before, no explicit "close siblings" step needed.
    async toggleJudges(panelKey, anchorName, heatNumber) {
      const opening = !this.panelOpen(panelKey);
      this.expansion = opening ? panelKey : null;
      if (!opening || this.judgesCache.has(panelKey)) return;
      this.judgesCache.set(panelKey, { loading: true });
      try {
        const data = await JudgesScores.fetchJudgesData(ctx.cyi, anchorName, heatNumber);
        this.judgesCache.set(panelKey, { html: JudgesScores.renderPanel(data) });
      } catch (err) {
        this.judgesCache.set(panelKey, { error: err.message });
      }
    }

    renderJudgesPanelContent(panelKey) {
      const cached = this.judgesCache.get(panelKey);
      if (!cached) return '';
      if (cached.error) return `<div class="text-xs text-red-600 p-2">Couldn't load judges scores: ${esc(cached.error)}</div>`;
      if (cached.loading) return '<div class="text-xs text-gray-500 p-2">Loading judges scores…</div>';
      return cached.html;
    }

    renderContestedPill(g) {
      const active = this.panelOpen(g.panelKey);
      const label = esc(contestedLabel(g.labelResult));
      if (!g.clickable) {
        return `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 ml-2 opacity-70">${label}</span>`;
      }
      return `<span data-role="contested-pill" data-clickable="true" data-panel-key="${esc(g.panelKey)}" data-anchor-name="${esc(g.anchorName)}" data-heat-number="${esc(g.heatNumber)}"` +
        ` class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 ml-2 cursor-pointer hover:underline${active ? ' ring-2 ring-yellow-400' : ''}">${label}</span>`;
    }

    renderJudgesPanelWrapper(g) {
      const expanded = this.panelOpen(g.panelKey);
      const content = expanded ? this.renderJudgesPanelContent(g.panelKey) : '';
      return `<div data-role="judges-panel" data-panel-key="${esc(g.panelKey)}" class="judges-panel${expanded ? ' expanded' : ''}">${content}</div>`;
    }

    renderCouplesBadge() {
      const active = this.couplesOpen();
      const solo = HeatCard.isSoloHeat(this.allRounds);
      const label = solo ? 'Solo on floor' : `${this.n} couples`;
      const colorClasses = solo ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800';
      return `<span data-role="couples-pill" class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colorClasses} ml-2 cursor-pointer${active ? ' ring-2 ring-indigo-400' : ''}">${esc(label)}</span>`;
    }

    renderRoundEntries(round) {
      const byEvent = {};
      round.entries.forEach(e => { (byEvent[e.event] ??= []).push(e); });
      return Object.entries(byEvent).map(([evt, entries]) => {
        const someHaveResult = entries.some(e => e.result !== '');
        const sorted = entries.slice().sort(byResult);
        const rows = sorted.map(e => {
          const r = parseInt(e.result);
          const advanced = isNaN(r) && someHaveResult;
          const medal = advanced ? '🥇' : rankPrefix(r);
          const rank = medal ? medal + ' ' : !isNaN(r) ? `${ordinal(r)} ` : '';
          return `<div>${rank}${esc(e.bib)} ${esc(coupleName(e.competitor1, e.competitor2))}</div>`;
        }).join('');
        return `<div class="mb-1"><strong>${esc(ctx.eventLabels[Number(evt)] ?? '')}:</strong><div class="ml-2">${rows}</div></div>`;
      }).join('');
    }

    renderAllRounds() {
      return this.allRounds.map((round, gi) => {
        const roundHeader = this.allRounds.length > 1
          ? `<div class="font-semibold text-gray-600 mb-1">${esc(round.round)}</div>`
          : '';
        return (gi > 0 ? '<hr class="my-2 border-gray-200">' : '') + roundHeader + this.renderRoundEntries(round);
      }).join('');
    }

    render() {
      const { primary, allRounds, eventName, sessionLabel } = this;
      const groups = this.contestedGroups();
      const pillsHtml = groups.map(g => this.renderContestedPill(g)).join('');
      const panelsHtml = groups.map(g => this.renderJudgesPanelWrapper(g)).join('');
      const roundLabel = allRounds.length === 1 ? `<div><strong>Round:</strong> ${esc(primary.round)}</div>` : '';
      const expanded = this.couplesOpen();
      return `<div class="heat-box" data-card-key="${esc(this.key)}" data-now-time="${esc(primary.time)}">
      <div class="text-base text-gray-900">
        <strong>${esc(primary.heat_number)}</strong> · ${esc(formatTime(primary.time))}${pillsHtml} ${this.renderCouplesBadge()}
      </div>
      <div class="text-sm text-gray-700 mt-1">${esc(eventName)}</div>
      ${panelsHtml}
      <div class="heat-details${expanded ? ' expanded' : ''}">
        <div class="text-xs text-gray-600 space-y-2">
          <div><strong>Session:</strong> ${esc(sessionLabel)}</div>
          ${roundLabel}
          <div class="mt-3"><strong>All Competitors:</strong><div class="ml-2 mt-1">${this.renderAllRounds()}</div></div>
        </div>
      </div>
    </div>`;
    }
  }

  function getOrCreate(key) {
    let card = registry.get(key);
    if (!card) { card = new HeatCard(key); registry.set(key, card); }
    return card;
  }

  function render(primary, allRounds, eventName, sessionLabel) {
    const groupKey = allRounds.map(h => h.key).join('-');
    const card = getOrCreate(groupKey);
    card.update({ primary, allRounds, eventName, sessionLabel });
    return card.render();
  }

  // Full reset -- called once per competition load, since a different
  // competition's heat keys/judges data are entirely unrelated.
  function init({ cyi, eventLabels }) {
    registry.clear();
    ctx = { cyi, eventLabels: eventLabels || [] };
  }

  // Closes every open expansion but keeps fetched judges-score data cached --
  // called on competitor reselection within the same competition.
  function collapseAll() {
    registry.forEach(card => card.close());
  }

  // Sets which contested groups are relevant to the current view -- called
  // once per render pass by each of the 4 generate*Schedule functions, before
  // their render loop. See HeatCard.isRelevant() for the context shapes.
  function setContext(context) {
    HeatCard.context = context;
  }

  // ── Click dispatch ──────────────────────────────────────────────────────
  // One delegated listener replaces every per-element onclick="" string.
  function rerender(card) {
    const el = document.querySelector(`.heat-box[data-card-key="${CSS.escape(card.key)}"]`);
    if (el) el.outerHTML = card.render();
  }

  function onContainerClick(event) {
    const cardEl = event.target.closest('.heat-box[data-card-key]');
    if (!cardEl) return;
    const card = registry.get(cardEl.dataset.cardKey);
    if (!card) return;

    const couplesPill = event.target.closest('[data-role="couples-pill"]');
    if (couplesPill) {
      card.toggleCouples();
      rerender(card);
      return;
    }

    const contestedPill = event.target.closest('[data-role="contested-pill"]');
    if (contestedPill) {
      if (contestedPill.dataset.clickable !== 'true') return;
      const panelKey = contestedPill.dataset.panelKey;
      const anchorName = contestedPill.dataset.anchorName;
      const heatNumber = contestedPill.dataset.heatNumber;
      const p = card.toggleJudges(panelKey, anchorName, heatNumber);
      rerender(card); // paint the 'expanded'/'loading' state immediately
      p.then(() => rerender(card));
      return;
    }

    // Anywhere else on the card (blank space, a couples row, inside an open
    // judges panel): unconditionally close, never open.
    if (card.isExpanded()) {
      card.close();
      rerender(card);
    }
  }

  document.getElementById('scheduleContent')?.addEventListener('click', onContainerClick);

  global.HeatCard = {
    init, render, collapseAll, setContext,
    roundHasMultipleCouples: HeatCard.roundHasMultipleCouples,
    isSoloHeat: HeatCard.isSoloHeat,
  };
})(window);
