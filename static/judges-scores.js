// Live judges' scores lookup, resolved fresh against NDCA's public feed on every
// call — no Event_ID is cached to disk anywhere in this project. Mirrors the
// lookup flow used by ndcapremier.com/results/: competitor name -> competitor ID
// -> that competitor's full event list, filtered client-side to one heat.
(function (global) {
  const NDCA_BASE = 'https://ndcapremier.com';

  // cyi -> Promise<Map<name, competitorId>>, so repeated clicks within the same
  // competition don't re-fetch the full competitor list.
  const competitorListCache = new Map();

  async function fetchCompetitorIdMap(cyi) {
    if (!competitorListCache.has(cyi)) {
      competitorListCache.set(cyi, (async () => {
        const res = await fetch(`${NDCA_BASE}/feed/results/?cyi=${cyi}&date=${Date.now()}`);
        const data = await res.json();
        const map = new Map();
        (data.Result || []).forEach(c => {
          map.set((c.Name || []).join(' '), c.ID);
        });
        return map;
      })());
    }
    return competitorListCache.get(cyi);
  }

  async function fetchCompetitorEvents(cyi, competitorId) {
    const res = await fetch(`${NDCA_BASE}/feed/results/?cyi=${cyi}&id=${competitorId}`);
    const data = await res.json();
    return (data.Result && data.Result.Events) || [];
  }

  // Resolves live judges' marks for one competitor's heat. Returns the NDCA
  // "Event" object (Name, Heat, Rounds[].Dances[].Judges[]/Competitors[].Marks).
  async function fetchJudgesData(cyi, competitorName, heatNumber) {
    const idMap = await fetchCompetitorIdMap(cyi);
    const competitorId = idMap.get(competitorName);
    if (!competitorId) {
      throw new Error(`No published NDCA results found for "${competitorName}" in cyi ${cyi}`);
    }
    const events = await fetchCompetitorEvents(cyi, competitorId);
    const heatStr = String(heatNumber);
    const event = events.find(e => String(e.Heat) === heatStr);
    if (!event) {
      throw new Error(`No event found for heat ${heatNumber}`);
    }
    return event;
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function rankPrefix(r) {
    return r === 1 ? '🥇' : r === 2 ? '🥈' : r === 3 ? '🥉' : null;
  }

  function scoringBadge(method) {
    return `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 ml-2">${esc(method)}</span>`;
  }

  // Skated rounds: each dance is judged/placed independently — one table per
  // dance, columns per judge, final column is that dance's placement.
  function renderSkatedRound(round) {
    return round.Dances.map(dance => {
      const judgeCols = dance.Judges.map(j => `<th title="${esc(j.Name.join(' '))}">${esc(j.Judge_Letter)}</th>`).join('');
      const rows = [...dance.Competitors]
        .sort((a, b) => (a.Result ?? 999) - (b.Result ?? 999))
        .map(c => {
          const names = c.Participants.map(p => p.Name.join(' ')).join(' &amp; ');
          const marks = c.Marks.map(m => `<td>${esc(m)}</td>`).join('');
          const medal = rankPrefix(c.Result);
          const resultLabel = c.Result == null ? '—' : (medal ? `${medal} ${c.Result}` : c.Result);
          return `<tr><td>${esc(c.Bib)}</td><td>${names}</td><td><strong>${esc(resultLabel)}</strong></td>${marks}</tr>`;
        }).join('');
      const judgeList = dance.Judges.map(j => `${esc(j.Judge_Letter)} ${esc(j.Name.join(' '))}`).join(', ');
      return `
        <div class="mb-3">
          <div class="font-semibold text-gray-700 text-sm mb-1">${esc(dance.Dance_Name)}</div>
          <table class="judges-table">
            <thead><tr><th>Bib</th><th>Couple</th><th>Result</th>${judgeCols}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
          <div class="text-xs text-gray-500 mt-1">Judges: ${judgeList}</div>
        </div>`;
    }).join('');
  }

  // Prelims rounds: judges cast a recall vote (1/0) per couple per dance, not
  // a placement. Render one table per dance with each judge's vote (like
  // Skated), ordered by the round's overall recall-vote total, then a final
  // summary table (from round.Summary) with each couple's total votes and
  // whether they were recalled.
  function renderPrelimsRound(round) {
    const summary = round.Summary;
    const order = summary
      ? [...summary.Competitors].sort((a, b) => (b.Total ?? 0) - (a.Total ?? 0)).map(c => c.ID)
      : null;
    const orderIndex = id => (order ? order.indexOf(id) : 0);

    const danceTables = round.Dances.map(dance => {
      const judgeCols = dance.Judges.map(j => `<th title="${esc(j.Name.join(' '))}">${esc(j.Judge_Letter)}</th>`).join('');
      const rows = [...dance.Competitors]
        .sort((a, b) => orderIndex(a.ID) - orderIndex(b.ID))
        .map(c => {
          const names = c.Participants.map(p => p.Name.join(' ')).join(' &amp; ');
          const marks = c.Marks.map(m => `<td>${m ? '✓' : ''}</td>`).join('');
          const votes = c.Marks.reduce((sum, m) => sum + m, 0);
          return `<tr><td>${esc(c.Bib)}</td><td>${names}</td><td><strong>${votes}</strong></td>${marks}</tr>`;
        }).join('');
      const judgeList = dance.Judges.map(j => `${esc(j.Judge_Letter)} ${esc(j.Name.join(' '))}`).join(', ');
      return `
        <div class="mb-3">
          <div class="font-semibold text-gray-700 text-sm mb-1">${esc(dance.Dance_Name)}</div>
          <table class="judges-table">
            <thead><tr><th>Bib</th><th>Couple</th><th>Votes</th>${judgeCols}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
          <div class="text-xs text-gray-500 mt-1">Judges: ${judgeList}</div>
        </div>`;
    }).join('');

    if (!summary) return danceTables;

    const summaryRows = [...summary.Competitors]
      .sort((a, b) => (b.Total ?? 0) - (a.Total ?? 0))
      .map(c => {
        const names = c.Participants.map(p => p.Name.join(' ')).join(' &amp; ');
        const recalled = c.Recalled
          ? '<span class="text-green-700">✓ Recalled</span>'
          : '<span class="text-gray-400">Not recalled</span>';
        return `<tr><td>${esc(c.Bib)}</td><td>${names}</td><td>${recalled}</td><td>${esc(c.Total ?? '—')}</td></tr>`;
      }).join('');
    const summaryTable = `
      <div class="mb-3">
        <div class="font-semibold text-gray-700 text-sm mb-1">Round summary</div>
        <table class="judges-table">
          <thead><tr><th>Bib</th><th>Couple</th><th>Result</th><th>Total votes</th></tr></thead>
          <tbody>${summaryRows}</tbody>
        </table>
      </div>`;
    return summaryTable + danceTables;
  }

  function renderRound(round) {
    const header = `<div class="font-semibold text-gray-700 text-sm mt-2 mb-1">${esc(round.Name)}${scoringBadge(round.Scoring_Method)}</div>`;
    const body = round.Scoring_Method === 'Prelims' ? renderPrelimsRound(round) : renderSkatedRound(round);
    return header + body;
  }

  // Renders the NDCA "Event" object returned by fetchJudgesData() as a card
  // matching the SPA's .heat-box / pill styling conventions. An event can
  // carry more than one round (e.g. a Prelims semi-final plus a Skated final)
  // — NDCA lists them chronologically, but we show the most conclusive one
  // (the final) first and earlier rounds after.
  function renderPanel(event) {
    const roundsHtml = [...event.Rounds].reverse().map(renderRound).join('<hr class="my-2 border-gray-200">');
    return `
      <div class="heat-box judges-card">
        <div class="text-base text-gray-900"><strong>Heat ${esc(event.Heat)}</strong></div>
        <div class="text-sm text-gray-700 mt-1 mb-2">${esc(event.Name)}</div>
        ${roundsHtml}
      </div>`;
  }

  global.JudgesScores = { fetchJudgesData, renderPanel };
})(window);
