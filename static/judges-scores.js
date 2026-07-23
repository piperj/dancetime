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

  // Renders the NDCA "Event" object returned by fetchJudgesData() as a card
  // matching the SPA's .heat-box / pill styling conventions.
  function renderPanel(event) {
    const round = event.Rounds[0];
    const dancesHtml = round.Dances.map(dance => {
      const judgeCols = dance.Judges.map(j => `<th title="${esc(j.Name.join(' '))}">${esc(j.Judge_Letter)}</th>`).join('');
      const rows = [...dance.Competitors].sort((a, b) => a.Result - b.Result).map(c => {
        const names = c.Participants.map(p => p.Name.join(' ')).join(' &amp; ');
        const marks = c.Marks.map(m => `<td>${esc(m)}</td>`).join('');
        const medal = rankPrefix(c.Result);
        const resultLabel = medal ? `${medal} ${c.Result}` : c.Result;
        return `<tr><td>${esc(c.Bib)}</td><td>${names}</td>${marks}<td><strong>${esc(resultLabel)}</strong></td></tr>`;
      }).join('');
      const judgeList = dance.Judges.map(j => `${esc(j.Judge_Letter)} ${esc(j.Name.join(' '))}`).join(', ');
      return `
        <div class="mb-3">
          <div class="font-semibold text-gray-700 text-sm mb-1">${esc(dance.Dance_Name)}</div>
          <table class="judges-table">
            <thead><tr><th>Bib</th><th>Couple</th>${judgeCols}<th>Result</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
          <div class="text-xs text-gray-500 mt-1">Judges: ${judgeList}</div>
        </div>`;
    }).join('');

    return `
      <div class="heat-box judges-card">
        <div class="text-base text-gray-900">
          <strong>Heat ${esc(event.Heat)}</strong>
          <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 ml-2">${esc(round.Scoring_Method)}</span>
        </div>
        <div class="text-sm text-gray-700 mt-1 mb-2">${esc(event.Name)}</div>
        ${dancesHtml}
      </div>`;
  }

  global.JudgesScores = { fetchJudgesData, renderPanel };
})(window);
