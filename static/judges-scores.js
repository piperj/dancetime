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

  global.JudgesScores = { fetchJudgesData };
})(window);
