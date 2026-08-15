// Heat-card rendering + click behavior, extracted out of index.html's inline
// script. One HeatCard instance per physical heat, kept in a registry that
// survives the 10s auto-refresh full-HTML rebuild, so expansion state and
// fetched judges-score data persist across renders without any DOM-side
// state (no ids to look up, no onclick strings to build/escape).
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

    // Per-round, per-event contested groups -- derived fresh from allRounds,
    // not from any selected competitor, so identical across all 4 views.
    contestedGroups() {
      const groups = [];
      this.allRounds.forEach(round => {
        const byEvent = {};
        round.entries.forEach(e => { (byEvent[e.event] ??= []).push(e); });
        Object.entries(byEvent).forEach(([evt, entries], idx) => {
          if (entries.length <= 1) return;
          const sorted = entries.slice().sort(byResult);
          // byResult sorts advancing/unresolved (blank-result) entries first,
          // which is right for the couples-list display but wrong for "best
          // placement" -- find the best *numeric* result instead, if any.
          const best = sorted.find(e => e.result !== '');
          groups.push({
            panelKey: `${round.key}__${idx}`,
            eventIdx: Number(evt),
            heatNumber: round.heat_number,
            entries: sorted,
            anchorName: sorted[0].competitor1,
            clickable: !!best,
            labelResult: best?.result,
          });
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
      const solo = this.n === 1;
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
      return `<div class="heat-box" data-card-key="${esc(this.key)}">
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

  global.HeatCard = { init, render, collapseAll };
})(window);
