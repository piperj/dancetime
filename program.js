// Live NDCA "program" feed — awards / costume breaks / top-award ceremonies.
// Mirrors judges-scores.js: fetched client-side straight from ndcapremier.com,
// no local caching in the data pipeline. Session Activity titles are free text
// and inconsistent across competitions (typos included, e.g. "Top Teahcers
// and Studios"), so activities are categorized by keyword rather than an
// exact-match table.
(function () {
  const NDCA_BASE = 'https://ndcapremier.com';
  const cache = {};

  function categorize(title) {
    const t = title.toLowerCase();
    if (t.includes('top')) return 'top';
    if (t.includes('award')) return 'award';
    if (t.includes('break') || t.includes('costume')) return 'break';
    return null;
  }

  // "7/25/2026 10:04 AM" or "7/25/2026 9:00:00 AM" -> "2026-07-25T10:04:00"
  // (matches the naive-local timestamp format used throughout heats_*.json)
  function parseNdcaTime(s) {
    const m = /^(\d+)\/(\d+)\/(\d+)\s+(\d+):(\d+)(?::(\d+))?\s*(AM|PM)$/i.exec((s || '').trim());
    if (!m) return null;
    let [, mo, da, yr, hh, mi, se, ap] = m;
    hh = parseInt(hh, 10);
    if (/pm/i.test(ap) && hh !== 12) hh += 12;
    if (/am/i.test(ap) && hh === 12) hh = 0;
    const pad = n => String(n).padStart(2, '0');
    return `${yr}-${pad(mo)}-${pad(da)}T${pad(hh)}:${pad(mi)}:${pad(se || 0)}`;
  }

  function sessionCode(name) {
    const m = /^(\d+)-/.exec(name || '');
    return m ? m[1] : null;
  }

  async function fetchJson(url) {
    const res = await fetch(url);
    return res.json();
  }

  // Returns { bySession: { [code]: { sessionStart, activities: [{time,title,category}] } } }
  async function loadProgramMarkers(cyi) {
    if (cache[cyi]) return cache[cyi];
    cache[cyi] = (async () => {
      const bySession = {};
      try {
        const list = await fetchJson(`${NDCA_BASE}/feed/program/?cyi=${cyi}`);
        if (list.Status !== 1) return { bySession };
        const ballrooms = list.Result.Ballrooms || [];
        await Promise.all(ballrooms.flatMap(ballroom =>
          (ballroom.Sessions || []).map(async session => {
            const code = sessionCode(session.Name);
            if (!code) return;
            const sessionStart = parseNdcaTime(session.Date_Time);
            let activities = [];
            try {
              const detail = await fetchJson(
                `${NDCA_BASE}/feed/program/?cyi=${cyi}&ballroom=${ballroom.ID}&session=${session.ID}&type=0`
              );
              if (detail.Status === 1) {
                activities = (detail.Result || [])
                  .filter(item => item.Type === 'Activity')
                  .map(item => {
                    const category = categorize(item.Title || '');
                    if (!category) return null;
                    const time = parseNdcaTime(item.Date_Time);
                    if (!time) return null;
                    return { time, title: (item.Title || '').trim(), category };
                  })
                  .filter(Boolean)
                  .sort((a, b) => a.time.localeCompare(b.time));
              }
            } catch { /* leave activities empty for this session */ }
            bySession[code] = { sessionStart, activities };
          })
        ));
      } catch { /* return whatever partial data we gathered */ }
      return { bySession };
    })();
    return cache[cyi];
  }

  window.loadProgramMarkers = loadProgramMarkers;
})();
