/* دفّة — الإقلاع والتوجيه */
(function () {
  window.DATA = { schedule: null, manifest: null, lessonCache: {} };

  async function boot() {
    if (window.DAFFA_BUNDLE) {
      // حزمة مولّدة بـ compile.mjs — تعمل حتى من الفولدر مباشرة (file://)
      DATA.schedule = DAFFA_BUNDLE.schedule;
      DATA.manifest = DAFFA_BUNDLE.manifest;
      DATA.lessonCache = DAFFA_BUNDLE.lessons || {};
    } else {
      const [sch, man] = await Promise.all([
        fetch('schedule.json').then(r => r.json()),
        fetch('content/manifest.json').then(r => r.json()),
      ]);
      DATA.schedule = sch;
      DATA.manifest = man;
    }

    LessonTimer.bind();

    // وضع العرض للطلاب
    document.getElementById('btnPresent').onclick = () => {
      document.body.classList.toggle('present');
      const on = document.body.classList.contains('present');
      document.querySelector('#btnPresent span').textContent = on ? 'خروج من العرض' : 'وضع العرض';
    };
    document.getElementById('btnSettings').onclick = () => location.hash = '#/settings';
    document.getElementById('brandHome').onclick = () => location.hash = '#/';

    window.addEventListener('hashchange', route);
    route();

    // تسجيل service worker (يعمل فقط عبر http/https)
    if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
      navigator.serviceWorker.register('sw.js').catch(() => {});
    }
  }

  function route() {
    const h = location.hash || '#/';
    const parts = h.replace(/^#\//, '').split('/').filter(Boolean);

    if (!Store.state.settings.setupDone && parts[0] !== 'setup') {
      location.hash = '#/setup';
      return;
    }
    window.scrollTo(0, 0);

    if (parts[0] === 'setup') return Views.renderSetup();
    if (parts[0] === 'settings') return Views.renderSettings();
    if (parts[0] === 'plan' && parts[1]) return Views.renderPlan(parts[1]);
    if (parts[0] === 'week' && parts[1] && parts[2]) return Views.renderWeek(parts[1], parts[2]);
    return Views.renderHome();
  }

  boot().catch(e => {
    document.getElementById('app').innerHTML =
      `<div class="placeholder-lesson"><h2>⚠ تعذّر تحميل البيانات</h2><p>${e.message}</p></div>`;
  });
})();
