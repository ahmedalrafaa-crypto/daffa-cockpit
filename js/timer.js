/* دفّة — مؤقّت إيقاع الحصة: تمهيد ← شرح ← تطبيق/حل ← تقويم */
(function () {
  const bar = () => document.getElementById('timerbar');

  const T = {
    phases: [], idx: 0, remaining: 0, running: false, _iv: null,

    load() {
      T.phases = Store.state.settings.timerPhases.map(p => ({ name: p.name, secs: p.min * 60 }));
      T.idx = 0;
      T.remaining = T.phases.length ? T.phases[0].secs : 0;
      T.running = false;
      clearInterval(T._iv);
      T.renderTrack();
      T.paint();
    },

    show() {
      // لا تصفّر مؤقّتاً شغّالاً عند إعادة رسم الشاشة
      if (bar().classList.contains('hidden')) { bar().classList.remove('hidden'); T.load(); }
    },
    hide() { bar().classList.add('hidden'); T.running = false; clearInterval(T._iv); },

    toggle() { T.running ? T.pause() : T.start(); },
    start() {
      if (!T.phases.length) return;
      T.running = true;
      clearInterval(T._iv);
      T._iv = setInterval(() => { T.remaining--; T.paint(); }, 1000);
      T.paint();
    },
    pause() { T.running = false; clearInterval(T._iv); T.paint(); },
    reset() { T.load(); },
    skip() {
      if (T.idx < T.phases.length - 1) {
        T.idx++;
        T.remaining = T.phases[T.idx].secs;
        if (navigator.vibrate) navigator.vibrate(120);
      } else {
        T.pause();
      }
      T.renderTrack();
      T.paint();
    },

    renderTrack() {
      const tr = document.getElementById('tTrack');
      tr.innerHTML = T.phases.map((p, i) =>
        `<div class="t-seg ${i < T.idx ? 'done' : ''}" title="${p.name}"><div class="fill"></div></div>`
      ).join('');
    },

    paint() {
      const ph = T.phases[T.idx];
      if (!ph) return;
      const neg = T.remaining < 0;
      const a = Math.abs(T.remaining);
      const mm = String(Math.floor(a / 60)).padStart(2, '0');
      const ss = String(a % 60).padStart(2, '0');
      const clock = document.getElementById('tClock');
      clock.textContent = (neg ? '+' : '') + mm + ':' + ss;
      clock.classList.toggle('running', T.running && !neg);
      clock.classList.toggle('overtime', neg);

      document.getElementById('tPhaseName').textContent =
        `${T.idx + 1}/${T.phases.length} · ${ph.name}`;
      const nxt = T.phases[T.idx + 1];
      document.getElementById('tPhaseNext').textContent = nxt ? `التالي: ${nxt.name}` : 'المرحلة الأخيرة';
      document.getElementById('tStart').textContent = T.running ? '⏸ إيقاف' : '▶ ابدأ';

      const segs = document.querySelectorAll('.t-seg');
      segs.forEach((seg, i) => {
        const f = seg.querySelector('.fill');
        if (i < T.idx) f.style.width = '100%';
        else if (i === T.idx) {
          const pct = neg ? 100 : Math.min(100, 100 * (1 - T.remaining / ph.secs));
          f.style.width = pct + '%';
        } else f.style.width = '0%';
      });

      // نهاية مرحلة: اهتزاز وانتقال تلقائي
      if (neg && T.remaining === -1 && T.idx < T.phases.length - 1) {
        if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
      }
    },

    bind() {
      document.getElementById('tStart').onclick = T.toggle;
      document.getElementById('tClock').onclick = T.toggle;
      document.getElementById('tSkip').onclick = T.skip;
      document.getElementById('tReset').onclick = T.reset;
    },
  };

  window.LessonTimer = T;
})();
