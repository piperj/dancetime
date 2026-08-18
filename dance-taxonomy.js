// Free-text NDCA event-string parser -- maps strings like
// "AC-B1 Cl. Full Bronze Amer. Rumba" or a multi-dance grouped event like
// "Closed Silver Multi Dance Full Silver S1 Amer. Smooth (W,T,F,VW)" to
// structured { level, styleFamily, danceName, isAmerican, raw } entries.
// Backed by data/dance_taxonomy.json (the single source of truth for the
// dance-code/style-family tables -- no literal tables duplicated here).
//
// Real event strings are messy (see thor.md 2026-08-16): level phrasing
// varies wildly, a trailing "/P" needs stripping, some dances (Peabody,
// Argentine Tango, Country Western dances) carry no "Amer."/"Int'l" marker
// at all, and some strings (freestyle/showcase titles, ambiguous bare dance
// names) can't be resolved with confidence. This parser never throws --
// anything it can't confidently resolve comes back tagged styleFamily
// 'unknown' rather than corrupting or crashing the caller's render.
(function (global) {
  'use strict';

  let taxonomy = null;
  const ready = fetch('data/dance_taxonomy.json')
    .then(r => r.json())
    .then(data => { taxonomy = data; return data; })
    .catch(() => { taxonomy = null; });

  const MARKER_PATTERNS = [
    { key: 'american', re: /\bAmer(?:ican)?\.?\b/i },
    { key: 'international', re: /\bInt'?l\.?|International\b/i },
    { key: 'countryWestern', re: /\bC\/W\b/i },
  ];

  const ROLE_AGE_PREFIX = /^(AC|mG|mL|G|L)-([A-Za-z0-9]+)\s+/;
  const MULTI_DANCE_CODES = /\(([A-Za-z0-9]{1,4}(?:\s*,\s*[A-Za-z0-9]{1,4}){1,})\)\s*$/;
  // A trailing "/P", "/J", etc. -- a single-heat qualifier suffix (only "/P"
  // was confirmed at design time, but "/J" turned up in real data too, see
  // thor.md 2026-08-16) -- generalized to 1-2 uppercase letters rather than
  // hardcoding each one as it's found.
  const TRAILING_SLASH_QUALIFIER = /\/[A-Z]{1,2}\s*$/;
  const TRAILING_PAREN_NOTE = /\([^()]*\)\s*$/;

  function familiesForMarker(markerKey) {
    if (!taxonomy) return [];
    if (!markerKey) return taxonomy.familySearchOrder || Object.keys(taxonomy.families || {});
    const group = taxonomy.markers?.[markerKey];
    return group ? group.families : [];
  }

  function findDanceInFamily(familyKey, danceName) {
    const fam = taxonomy?.families?.[familyKey];
    if (!fam) return null;
    const needle = danceName.trim().toLowerCase();
    for (const [name, code] of Object.entries(fam.dances)) {
      if (name.toLowerCase() === needle) return { code, danceName: name };
    }
    return null;
  }

  function resolveDanceName(markerKey, danceName) {
    const families = familiesForMarker(markerKey);
    for (const fam of families) {
      const hit = findDanceInFamily(fam, danceName);
      if (hit) return { styleFamily: fam, code: hit.code, danceName: hit.danceName };
    }
    return null;
  }

  // No marker at all (Peabody, Argentine Tango, Country Western dances,
  // ambiguous solos) -- the dance name is some trailing word-run of
  // `remainder`, with the rest being level text, and there's no marker to
  // narrow the family search. Try every known dance name (taxonomy-wide,
  // in familySearchOrder priority) as a candidate trailing match against
  // `remainder`, and keep the longest (most specific) hit -- e.g. "Full
  // Silver Peabody" must resolve to "Peabody", not fail because "Silver
  // Peabody" as a whole isn't a known dance name.
  function bestSuffixDanceMatch(remainder) {
    const rLower = remainder.toLowerCase();
    let best = null;
    for (const fam of taxonomy.familySearchOrder || []) {
      const famDef = taxonomy.families?.[fam];
      if (!famDef) continue;
      for (const [name, code] of Object.entries(famDef.dances)) {
        const nameLower = name.toLowerCase();
        const matches = rLower === nameLower || rLower.endsWith(' ' + nameLower);
        if (!matches) continue;
        if (!best || name.length > best.danceName.length) {
          best = { styleFamily: fam, danceName: name, code, level: remainder.slice(0, remainder.length - name.length).trim() };
        }
      }
    }
    return best;
  }

  function findCodeInFamily(familyKey, code) {
    const fam = taxonomy?.families?.[familyKey];
    if (!fam) return null;
    let needle = code.trim().toUpperCase();
    // Real multi-dance code lists don't always agree with single-dance
    // event strings on a family's own codes -- American Rhythm's Cha Cha
    // is "C" in single-dance events but "CC" inside a "(CC,R,SW)"-style
    // group (confirmed in real data, see thor.md 2026-08-16). codeAliases
    // normalizes those known multi-dance-only spellings before matching.
    needle = (fam.codeAliases?.[needle] || needle).toUpperCase();
    for (const [name, c] of Object.entries(fam.dances)) {
      if (c.toUpperCase() === needle) return { code: c, danceName: name };
    }
    return null;
  }

  function resolveCode(markerKey, code) {
    const families = familiesForMarker(markerKey);
    for (const fam of families) {
      const hit = findCodeInFamily(fam, code);
      if (hit) return { styleFamily: fam, code: hit.code, danceName: hit.danceName };
    }
    // With no markerKey, familiesForMarker already returned the full
    // familySearchOrder above -- only fall back to a taxonomy-wide search
    // here when the marker narrowed the first pass to a smaller group.
    if (markerKey) {
      for (const fam of taxonomy.familySearchOrder || []) {
        const hit = findCodeInFamily(fam, code);
        if (hit) return { styleFamily: fam, code: hit.code, danceName: hit.danceName };
      }
    }
    return null;
  }

  function unknownEntry(raw, level, code) {
    return { level: level || '', styleFamily: 'unknown', danceName: code || raw, code: code || null, isAmerican: null, raw };
  }

  function isAmericanForFamily(styleFamily) {
    const fam = taxonomy?.families?.[styleFamily];
    if (!fam || !fam.marker) return null;
    return fam.marker === 'american' || fam.marker === 'countryWestern';
  }

  // Event strings are static per competition and this parser is pure over
  // `taxonomy` (fixed once ready() resolves), so a raw-string cache avoids
  // re-running the marker/family scan for the same event on every render --
  // Heats and Rounds both call parseEvent per heat group, and Rounds calls
  // it again per gap cell.
  const parseCache = new Map();

  function parseEvent(eventString) {
    const raw = String(eventString ?? '');
    if (!taxonomy) return [unknownEntry(raw, '', null)]; // not cached -- pre-ready() callers shouldn't pin a placeholder result
    if (parseCache.has(raw)) return parseCache.get(raw);
    const result = parseEventUncached(raw);
    parseCache.set(raw, result);
    return result;
  }

  function parseEventUncached(raw) {
    let s = raw.trim();

    // Multi-dance grouped events: a trailing "(W,T,F,VW)"-style code list.
    let codes = null;
    const codeMatch = MULTI_DANCE_CODES.exec(s);
    if (codeMatch) {
      codes = codeMatch[1].split(',').map(c => c.trim()).filter(Boolean);
      s = s.slice(0, codeMatch.index).trim();
    }

    s = s.replace(TRAILING_SLASH_QUALIFIER, '').trim();
    // Strip a single trailing parenthetical note that isn't a dance-code
    // group (e.g. "(Wed.)", "(Wednesday)") -- solos carry these.
    s = s.replace(TRAILING_PAREN_NOTE, '').trim();

    let markerKey = null;
    let marker = null;
    for (const m of MARKER_PATTERNS) {
      const hit = m.re.exec(s);
      if (hit && (!marker || hit.index < marker.index)) { marker = hit; markerKey = m.key; }
    }

    let levelPart = s, dancePart = '';
    if (marker) {
      levelPart = s.slice(0, marker.index).trim();
      dancePart = s.slice(marker.index + marker[0].length).trim();
      dancePart = dancePart.replace(/^\.?\s*/, '');
    }

    const roleMatch = ROLE_AGE_PREFIX.exec(levelPart);
    if (roleMatch) levelPart = levelPart.slice(roleMatch[0].length).trim();
    levelPart = levelPart.replace(/\s+/g, ' ').trim();

    if (!marker && !codes) {
      // No explicit style marker at all (Peabody, Argentine Tango, Country
      // Western dances, ambiguous solos) -- the dance name is some trailing
      // word-run of levelPart (itself already role/age-prefix-stripped),
      // not the whole remainder, since a level phrase normally precedes it
      // (e.g. "Full Silver Peabody"). See bestSuffixDanceMatch().
      const best = bestSuffixDanceMatch(levelPart);
      if (!best) return [unknownEntry(raw, levelPart, levelPart)];
      return [{
        level: best.level,
        styleFamily: best.styleFamily,
        danceName: best.danceName,
        code: best.code,
        isAmerican: isAmericanForFamily(best.styleFamily),
        raw,
      }];
    }

    if (codes && codes.length > 1) {
      return codes.map(code => {
        const resolved = resolveCode(markerKey, code);
        if (!resolved) return unknownEntry(raw, levelPart, code);
        return {
          level: levelPart,
          styleFamily: resolved.styleFamily,
          danceName: resolved.danceName,
          code: resolved.code,
          isAmerican: isAmericanForFamily(resolved.styleFamily),
          raw,
        };
      });
    }

    if (!dancePart) return [unknownEntry(raw, levelPart, null)];
    const resolved = resolveDanceName(markerKey, dancePart);
    if (!resolved) return [unknownEntry(raw, levelPart, dancePart)];
    return [{
      level: levelPart,
      styleFamily: resolved.styleFamily,
      danceName: resolved.danceName,
      code: resolved.code,
      isAmerican: isAmericanForFamily(resolved.styleFamily),
      raw,
    }];
  }

  // The one shared rule behind the costume-change marker in both tabs: a
  // change fires only on a style-family change, never a level-only change
  // within the same family. Compares the *set* of style families present in
  // each parsed event (plural, since a multi-dance event can span more than
  // one -- though in practice it never mixes families today).
  function styleFamilyChanged(prevParsed, nextParsed) {
    const prevFamilies = new Set((prevParsed || []).map(p => p.styleFamily));
    const nextFamilies = new Set((nextParsed || []).map(p => p.styleFamily));
    if (prevFamilies.size === 0 || nextFamilies.size === 0) return false;
    if (prevFamilies.size !== nextFamilies.size) return true;
    for (const f of prevFamilies) if (!nextFamilies.has(f)) return true;
    return false;
  }

  // The canonical dance order for one round of a style family (e.g.
  // International Ballroom: W, T, VW, F, Q) -- the basis for Rounds'
  // round-sequence cell layout (static/rounds.js): a couple's own danced
  // codes are matched against this order to detect which canonical dances
  // they skip within a round, rather than comparing against other couples'
  // entries. Returns null for an unrecognized family (no skip detection
  // possible without a known sequence).
  function roundSequence(styleFamily) {
    return taxonomy?.families?.[styleFamily]?.roundSequence || null;
  }

  global.DanceTaxonomy = { ready, parseEvent, styleFamilyChanged, roundSequence };
})(window);
