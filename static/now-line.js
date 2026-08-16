// "Now" line for the Heats tab -- a red current-time indicator that lives
// inside the scrollable page content (like Apple Calendar's current-time
// line), not pinned to the viewport, plus a floating play/pause button that
// controls only whether the screen tracks it. The line itself always keeps
// advancing from Date.now() regardless of Play/Pause -- there's nothing to
// pause, since it's real wall-clock time, not a simulated clock.
//
// Stops are read from the DOM via a `data-now-time="<ISO time>"` convention
// (set by heat-card.js on each .heat-box, and by renderProgramActivity() on
// break/award markers) rather than any callback from the four schedule
// render functions -- there is no single choke point for "the schedule
// changed" (heat-card.js's own rerender() bypasses the shared
// setScheduleHTML() wholesale-replace path when a couples list expands), so
// a MutationObserver on #scheduleContent is the only thing that sees every
// path uniformly.
(function () {
  'use strict';

  const LEAD_MS = 60000;       // stops hold, then ease onto the next one in the last minute before its time
  const LINE_FRACTION = 0.34;  // where the line should land on screen (fraction of viewport height) while tracking
  const RELEASE_MS = 150;      // quiet period after the last user scroll input before tracking resumes
  const DOUBLE_TAP_MS = 300;   // FAB single-tap commit delay, to leave room for a double-tap

  // ── Pure math -- no DOM reads, unit-testable in isolation (see `_test`) ──

  function smoothstep(t) { return t * t * (3 - 2 * t); }

  // Where the line itself sits in page-coordinate space at time `t`, given
  // `stops` = [{t, y}, ...] sorted ascending by t. Holds at the current
  // stop's y until LEAD_MS before the next stop's time, then eases onto it.
  function contentYFor(stops, t) {
    if (!stops.length) return 0;
    if (t <= stops[0].t) return stops[0].y;
    if (t >= stops[stops.length - 1].t) return stops[stops.length - 1].y;
    let c = 0;
    while (c < stops.length - 1 && stops[c + 1].t <= t) c++;
    const cur = stops[c], next = stops[c + 1];
    if (!next) return cur.y;
    const leadStart = next.t - LEAD_MS;
    if (t <= leadStart) return cur.y;
    const frac = (t - leadStart) / LEAD_MS;
    return cur.y + (next.y - cur.y) * smoothstep(frac);
  }

  // Where the screen should scroll to, if it's tracking the line, so the
  // line lands `lineFraction` down the viewport rather than at its very top.
  function scrollTargetFor(stops, t, viewportH, lineFraction) {
    return contentYFor(stops, t) - viewportH * (lineFraction == null ? LINE_FRACTION : lineFraction);
  }

  // The additive hand-over formula: once a user-chosen `offset` is
  // established, the tracked scroll position keeps moving at the same rate
  // as the line (same `target` growth) while preserving that offset,
  // instead of snapping back to `target` itself.
  function trackedScroll(target, offset) { return target + offset; }

  // ── DOM / browser glue ──────────────────────────────────────────────────

  let scheduleContent = null;
  let root = null, lineEl = null, chipEl = null, fabEl = null;
  let stops = [];
  let active = false;    // mirrors the Heats tab being the active tab, via setActive()
  let playing = true;
  let pointerDown = false;
  let interacting = false;
  let offset = 0;
  let settleTimer = null;
  let fabTapTimer = null;
  let lastWrittenScrollY = null; // what we last set scrollY to ourselves, so an unmatched 'scroll' event is recognizable as external
  let justRebuilt = false; // one frame of grace right after any rebuildStops(), so a transient page-height shrink (e.g. a momentary empty/placeholder render) that the browser itself clamps scrollY for doesn't get misread as external interference

  function maxScroll() { return document.documentElement.scrollHeight - window.innerHeight; }
  function clampScroll(y) { return Math.max(0, Math.min(maxScroll(), y)); }
  function writeScroll(y) { lastWrittenScrollY = y; window.scrollTo(0, y); }
  function idealTarget(now) { return scrollTargetFor(stops, now, window.innerHeight); }

  function fmtClock(ms) {
    const d = new Date(ms);
    let h = d.getHours() % 12 || 12;
    const m = String(d.getMinutes()).padStart(2, '0');
    const ap = d.getHours() >= 12 ? 'PM' : 'AM';
    return `${h}:${m} ${ap}`;
  }

  function buildRoot() {
    root = document.createElement('div');
    root.id = 'now-line-root';
    root.className = 'hidden';

    lineEl = document.createElement('div');
    lineEl.id = 'now-line';
    lineEl.innerHTML = '<span class="now-line-bar"></span><span class="now-line-chip"></span>';
    chipEl = lineEl.querySelector('.now-line-chip');
    root.appendChild(lineEl);

    fabEl = document.createElement('button');
    fabEl.id = 'now-fab';
    fabEl.type = 'button';
    fabEl.setAttribute('aria-label', 'Play/pause schedule tracking');
    fabEl.textContent = '▶';
    root.appendChild(fabEl);

    document.body.appendChild(root);
  }

  // Rebuilds the stops list AND, if we're actively tracking, immediately
  // re-asserts our own scroll position -- both done synchronously from the
  // MutationObserver callback (see wireEvents), not lazily on the next rAF
  // frame. This matters: index.html's setScheduleHTML() (the thing that
  // triggers this rebuild in the first place) captures scrollY before
  // replacing #scheduleContent's content and restores it after, so an
  // expand/collapse or the 10s auto-refresh doesn't yank the page out from
  // under a manually-scrolled user. That restore call is synchronous, so a
  // MutationObserver callback -- a microtask, guaranteed to run after it but
  // before the next paint -- is the one place we can reliably act as the
  // last word for this render, rather than reactively detecting the
  // resulting position mismatch a frame later and guessing whether it was
  // "us" or "them". An earlier version tried exactly that (compare
  // window.scrollY against what we last wrote, once per rAF frame) and it
  // was genuinely racy: with several renders landing within the same
  // second (a competition switch can trigger three or four), the
  // detect-after-the-fact version intermittently misread setScheduleHTML's
  // own restore as external interference and permanently locked in a
  // garbage hand-over offset.
  function rebuildStops() {
    const nodes = scheduleContent ? scheduleContent.querySelectorAll('[data-now-time]') : [];
    stops = Array.prototype.map.call(nodes, el => ({
      t: new Date(el.dataset.nowTime).getTime(),
      y: el.getBoundingClientRect().top + window.scrollY,
    }))
      .filter(s => !isNaN(s.t))
      .sort((a, b) => a.t - b.t);
    // Empty-state views (e.g. "{name} is not competing in {comp}", "No
    // heats found for this studio/bib") render zero data-now-time stops --
    // there's nothing for the line to point at, so hide it even though the
    // Heats tab itself is still active.
    if (root) root.classList.toggle('hidden', !active || !stops.length);
    // Bookkeeping baseline for the paused/inactive case (no corrective write
    // follows below) -- keeps the tick() drift-check from misreading this
    // same restore as external interference later, if/when Play resumes.
    lastWrittenScrollY = window.scrollY;
    // A render can briefly swap in placeholder/empty content before the
    // real one lands (a couple of these can fire within the same second
    // during a competition switch) -- the page can genuinely get shorter
    // for a moment, and the browser's own scroll-clamping (nothing to do
    // with any scrollTo() call, ours or index.html's) can then move
    // scrollY again *after* this synchronous rebuild already finished, in
    // the gap before the next rAF frame. One frame of grace in tick()
    // absorbs that too, rather than mistaking it for interference.
    justRebuilt = true;
    if (active && playing && !interacting && stops.length) {
      writeScroll(clampScroll(trackedScroll(idealTarget(Date.now()), offset)));
    }
  }

  // Re-anchors both the hand-over offset AND the drift baseline to wherever
  // the screen actually is right now, without writing anything. Every place
  // that computes a fresh `offset` from a bare read of window.scrollY must
  // also update lastWrittenScrollY here -- otherwise the tick() drift-check
  // (comparing window.scrollY against a now-stale lastWrittenScrollY) would
  // see the same "drift" again on the very next frame, before a real write
  // ever gets a chance to happen, and re-freeze forever.
  function resyncBaseline() {
    const y = window.scrollY;
    offset = y - idealTarget(Date.now());
    lastWrittenScrollY = y;
  }

  function setPlaying(p) {
    if (p && !playing) {
      // Resuming: pick up from wherever the screen currently sits rather
      // than snapping -- moves at the line's rate from here on, not "jumps
      // to the line".
      resyncBaseline();
    }
    playing = p;
    if (fabEl) fabEl.textContent = p ? '▶' : '⏸';
  }

  function recenter() {
    clearTimeout(settleTimer);
    pointerDown = false;
    interacting = false;
    offset = 0;
    writeScroll(clampScroll(idealTarget(Date.now())));
  }

  // Waits out native momentum/scroll before treating the user as "done" --
  // every fresh scroll event pushes this back out, so it only fires once
  // motion has actually stopped. No-ops while a finger is still down; gets
  // scheduled again on release.
  function scheduleRelease() {
    if (pointerDown) return;
    clearTimeout(settleTimer);
    settleTimer = setTimeout(() => {
      interacting = false;
      resyncBaseline();
    }, RELEASE_MS);
  }

  // Freeze is triggered by pointerdown/wheel -- input events that fire
  // before the browser actually moves the scroll position -- not by
  // reacting to the resulting 'scroll' event after the fact, which would
  // race our own per-frame tracking write and cause jitter/resistance.
  function beginInteraction() {
    interacting = true;
    clearTimeout(settleTimer);
  }

  function tick() {
    const now = Date.now();

    if (lineEl) lineEl.style.top = contentYFor(stops, now) + 'px';
    if (chipEl) chipEl.textContent = fmtClock(now);

    // Catch-all for scrolls we didn't cause ourselves and that aren't a
    // #scheduleContent re-render (that case is handled synchronously in
    // rebuildStops(), called from the MutationObserver -- see there for
    // why): a keyboard scroll, an OS scrollbar drag, a screen reader's
    // focus-scroll, or (the case that actually broke) a browser/test-
    // automation scrollIntoView() ahead of a click on something outside the
    // schedule area entirely. None of those fire 'pointerdown'/'wheel', so
    // this is the real catch-all; those two listeners just react a frame
    // sooner for the gestures they do cover. Checked synchronously once per
    // frame, reading window.scrollY directly, rather than off the 'scroll'
    // event -- that event's dispatch timing can lag behind our own rapid
    // per-frame writeScroll() calls, and comparing against a stale event
    // caused this to falsely freeze itself almost immediately (own writes
    // misread as external) the first time it was tried.
    //
    // Only evaluated while NOT already interacting: once frozen, we stop
    // writing, so lastWrittenScrollY stops advancing too -- re-running this
    // check every frame against that now-stale value would see "drift"
    // forever (nothing is closing the gap) and keep re-arming
    // scheduleRelease() on every single frame, so its timer could never get
    // an uninterrupted window to actually fire. A permanent, self-inflicted
    // freeze, not a browser timing quirk.
    //
    // Also skipped for exactly one frame right after a rebuildStops() call
    // (justRebuilt) -- absorb wherever scrollY lands as the new baseline
    // instead of comparing, since a render can briefly swap in
    // placeholder/empty content before the real one lands, and the
    // browser's own scroll-clamping in response to that momentary height
    // change can still be settling by the time this frame runs, after
    // rebuildStops() already finished. Without this, that one-off,
    // nobody's-fault settling gets misread as external interference, and
    // because it blocks the *next* rebuild's corrective write too (that one
    // also requires !interacting), the eventual 150ms release ends up
    // computing its offset from the wrong scrollY -- silently pinning
    // tracking to the wrong position instead of just costing one frame.
    if (justRebuilt) {
      justRebuilt = false;
      lastWrittenScrollY = window.scrollY;
    } else if (!interacting && lastWrittenScrollY !== null && Math.abs(window.scrollY - lastWrittenScrollY) >= 1) {
      beginInteraction();
      scheduleRelease();
    }

    // User control always wins: while a finger is down, or while a swipe /
    // wheel scroll is still settling, we never touch the scroll position.
    if (active && playing && !interacting && stops.length) {
      writeScroll(clampScroll(trackedScroll(idealTarget(now), offset)));
    }
    requestAnimationFrame(tick);
  }

  function wireEvents() {
    // Listened on `document`, not scoped to #scheduleContent -- the freeze
    // has to cover *any* user interaction with the page, not just the
    // schedule list. A user (or a test) tapping the nav bar or the
    // hamburger menu while Play is on is exactly the case that broke:
    // #scheduleContent-only freeze meant our per-frame scrollTo() kept
    // fighting the browser's own scroll-into-view for anything outside the
    // schedule area, since nothing there ever set interacting=true.
    document.addEventListener('pointerdown', () => { pointerDown = true; beginInteraction(); });
    ['pointerup', 'pointercancel'].forEach(ev => {
      document.addEventListener(ev, () => {
        if (!pointerDown) return;
        pointerDown = false;
        scheduleRelease();
      });
    });
    document.addEventListener('wheel', () => {
      beginInteraction();
      scheduleRelease(); // no-ops while pointerDown; otherwise restarts the wait on every tick
    }, { passive: true });
    // The general catch-all for scrolls with no matching gesture (keyboard,
    // scrollbar drag, screen reader, programmatic scrollIntoView() ahead of
    // a click elsewhere) lives in tick() itself, checked synchronously once
    // per frame against window.scrollY -- see the comment there for why a
    // 'scroll'-event-based version of this same check raced our own writes.

    // A screen lock or app-switch mid-gesture can swallow the
    // pointerup/pointercancel that would normally end it, leaving tracking
    // stuck frozen forever. Force-clear on hide rather than wait on an
    // event that may never arrive -- the wall-clock line position needs no
    // equivalent fix, since it's recomputed fresh from Date.now() every
    // frame with nothing accumulated to drift.
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) return;
      if (!pointerDown && !interacting) return;
      clearTimeout(settleTimer);
      pointerDown = false;
      interacting = false;
      resyncBaseline();
    });

    // Single tap toggles Play/Pause; a second tap inside the window cancels
    // the toggle and recenters instead.
    fabEl.addEventListener('click', () => {
      if (fabTapTimer) {
        clearTimeout(fabTapTimer);
        fabTapTimer = null;
        recenter();
        return;
      }
      fabTapTimer = setTimeout(() => {
        fabTapTimer = null;
        setPlaying(!playing);
      }, DOUBLE_TAP_MS);
    });

    // Rebuilds synchronously right here rather than lazily on the next rAF
    // frame -- see the comment on rebuildStops() for why that laziness was
    // itself the source of the race this replaced.
    new MutationObserver(rebuildStops).observe(scheduleContent, { childList: true, subtree: true });
  }

  function setActive(isActive) {
    active = !!isActive;
    // rebuildStops() re-derives visibility from `active && stops.length`
    // (empty-state views have no stops to point at) -- but it only runs
    // when going active, so the deactivate path needs its own hide here.
    if (!active && root) root.classList.add('hidden');
    // Force a fresh scan -- #scheduleContent may have been hidden (zeroed
    // rects) while inactive -- and, now that we're active again, let it
    // immediately re-assert the correct scroll position too.
    if (active) rebuildStops();
  }

  function init() {
    scheduleContent = document.getElementById('scheduleContent');
    if (!scheduleContent) return; // defensive -- not expected given script load order
    lastWrittenScrollY = window.scrollY;
    buildRoot();
    wireEvents();
    setPlaying(true);
    requestAnimationFrame(tick);
  }

  init();

  window.NowLine = {
    setActive,
    _test: {
      smoothstep, contentYFor, scrollTargetFor, trackedScroll, LEAD_MS, LINE_FRACTION,
      // Read-only introspection for integration tests -- not used by the
      // module itself. debugStops() lets a test confirm the MutationObserver
      // rebuild actually picked up a layout change (e.g. a card expanding)
      // without guessing at exact pixel values; isInteracting() lets a test
      // confirm a frozen gesture actually got cleared (e.g. after a
      // simulated backgrounding) without depending on scroll position, which
      // may coincidentally already match the target.
      debugStops: () => stops.map(s => ({ t: s.t, y: s.y })),
      isInteracting: () => pointerDown || interacting,
    },
  };
})();
