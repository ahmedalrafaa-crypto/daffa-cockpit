/* دفّة — شاشات التطبيق: الإعداد الأول، قمرة اليوم، الخطة، الدرس، الإعدادات */
(function () {
  const app = () => document.getElementById('app');
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  const STATUS = { done: 'منجزة ✔', partial: 'جزئية ◐', deferred: 'مؤجّلة ⏸', '': 'لم تُعطَ بعد' };
  const NEXT_STATUS = { '': 'done', done: 'partial', partial: 'deferred', deferred: '' };

  const typeChip = t => {
    let cls = '';
    if (t === 'رمضان') cls = 'ramadan';
    else if (t === 'مراجعة') cls = 'review';
    else if (t.includes('امتحان') || t.includes('عطلة')) cls = 'exam';
    return `<span class="type-chip ${cls}">${t === 'رمضان' ? '🌙 ' : ''}${esc(t)}</span>`;
  };

  /* ─────────── شاشة الإعداد الأول ─────────── */
  function renderSetup() {
    LessonTimer.hide();
    const sc = DATA.schedule.classes;
    app().innerHTML = `
      <div class="setup-hero">
        <img src="assets/logo-ar.png" alt="">
        <h1>أهلاً أستاذ أحمد 👋</h1>
        <p>إعداد أول مرة — كل شيء قابل للتعديل لاحقاً من ⚙️ الإعدادات</p>
      </div>
      ${['g9', 'g12'].map(c => `
        <div class="settings-grp">
          <h3>${esc(sc[c].label)}</h3>
          <div class="field">
            <label>📅 تاريخ بداية إعطاء الدروس</label>
            <input type="date" id="anchor-${c}" value="${Store.state.settings[c].anchor || sc[c].defaultAnchor}">
          </div>
          <div class="field">
            <label>🔢 عدد الحصص الأسبوعية</label>
            <input type="number" id="pw-${c}" min="1" max="6" value="${Store.state.settings[c].perWeek || sc[c].defaultPerWeek}">
          </div>
        </div>`).join('')}
      <button class="tbtn primary" id="setupSave" style="width:100%;font-size:1.15rem;min-height:60px">🚀 ابدأ السنة الدراسية</button>
    `;
    document.getElementById('setupSave').onclick = () => {
      for (const c of ['g9', 'g12']) {
        Store.state.settings[c].anchor = document.getElementById('anchor-' + c).value;
        Store.state.settings[c].perWeek = Math.max(1, +document.getElementById('pw-' + c).value || sc[c].defaultPerWeek);
      }
      Store.state.settings.setupDone = true;
      Store.save();
      location.hash = '#/';
    };
  }

  /* ─────────── قمرة اليوم ─────────── */
  function paceBadge(p) {
    const d = Math.round(p.delta * 2) / 2;
    if (d >= 0.5) return `<div class="pace ahead"><span class="dot"></span> متقدّم عن الخطة ${d} حصة</div>`;
    if (d <= -0.5) return `<div class="pace late"><span class="dot"></span> متأخّر عن الخطة ${Math.abs(d)} حصة</div>`;
    return `<div class="pace ok"><span class="dot"></span> على الخطة تماماً</div>`;
  }

  function renderHome() {
    LessonTimer.hide();
    const t = Engine.today0();
    const cards = ['g9', 'g12'].map(c => {
      const cw = DATA.schedule.classes[c];
      const slots = Engine.allSlots(DATA.schedule, c);
      const nxt = Engine.nextSlot(slots);
      const p = Engine.pace(slots);
      if (!nxt) return `
        <div class="class-card ${c}">
          <h2>${esc(cw.label)}</h2>
          <div class="topic">🎉 اكتملت خطة السنة كاملة!</div>
          ${paceBadge(p)}
        </div>`;
      return `
        <div class="class-card ${c}" data-go="#/week/${c}/${nxt.week}">
          <h2>${esc(cw.label)}</h2>
          <div class="week-tag">الحصة القادمة · الأسبوع ${nxt.week} · حصة ${nxt.slot} من ${Store.state.settings[c].perWeek}</div>
          <div class="topic">${esc(nxt.topic)}</div>
          ${typeChip(nxt.type)}
          ${paceBadge(p)}
        </div>`;
    }).join('');

    app().innerHTML = `
      <div class="today-line">اليوم: <b>${Engine.fmtDate(t)}</b> · العام الدراسي ${esc(DATA.schedule.year)}</div>
      <h1 class="screen-title">🧭 قمرة اليوم</h1>
      <div class="cockpit">${cards}</div>
      <div class="home-links teacher-ui">
        <button class="tbtn" data-go="#/plan/g9">📋 خطة الثالث</button>
        <button class="tbtn" data-go="#/plan/g12">📋 خطة السادس</button>
        <button class="tbtn ghost" data-go="#/settings">⚙️ الإعدادات</button>
      </div>
      <footer class="app-foot">دفّة · أ. أحمد رافع · فيزياء تُفهَم لا تُحفَظ</footer>
    `;
    app().querySelectorAll('[data-go]').forEach(el => el.onclick = () => location.hash = el.dataset.go);
  }

  /* ─────────── شاشة الخطة ─────────── */
  function renderPlan(cls) {
    LessonTimer.hide();
    const cw = DATA.schedule.classes[cls];
    const curN = Engine.currentWeekN(DATA.schedule, cls);
    const perWeek = Store.state.settings[cls].perWeek;
    const rows = cw.weeks.map(wk => {
      const wi = Engine.weekInfo(DATA.schedule, cls, wk.n);
      const holiday = Engine.isHolidayType(wk.type);
      const dots = holiday ? '' : Array.from({ length: perWeek }, (_, s) => {
        const st = Engine.statusOf(`${cls}:w${wk.n}:s${s + 1}`);
        return `<span class="wdot ${st}"></span>`;
      }).join('');
      return `
        <div class="week-row ${holiday ? 'holiday' : ''} ${wk.n === curN ? 'current' : ''}" ${holiday ? '' : `data-go="#/week/${cls}/${wk.n}"`}>
          <div class="wnum">${wk.n}</div>
          <div class="winfo">
            <div class="wtopic">${esc(wk.topic)}</div>
            <div class="wdate">${Engine.fmtShort(wi.start)} – ${Engine.fmtShort(wi.end)} ${typeChip(wk.type)}</div>
          </div>
          <div class="wdots">${dots}</div>
        </div>`;
    }).join('');

    app().innerHTML = `
      <div class="plan-head">
        <h1 class="screen-title">📋 خطة ${esc(cw.label)}</h1>
        <button class="tbtn ghost" data-go="#/">⬆ القمرة</button>
      </div>
      ${rows}
    `;
    app().querySelectorAll('[data-go]').forEach(el => el.onclick = () => location.hash = el.dataset.go);
    const cur = app().querySelector('.week-row.current');
    if (cur) cur.scrollIntoView({ block: 'center' });
  }

  /* ─────────── كتل محتوى الدرس ─────────── */
  function blockHTML(b, ctx) {
    switch (b.type) {
      case 'qa':
        return `<div class="blk blk-qa">
          <div class="q">${b.q}</div>
          ${b.a ? `<div class="private-blk"><div class="p-label">🔒 الجواب — طبقتي الخاصة</div>${b.a}</div>` : ''}
        </div>`;
      case 'law':
        return `<div class="blk blk-law">${b.label ? `<div class="label">📌 ${esc(b.label)}</div>` : ''}${b.html}</div>`;
      case 'table':
        return `<div class="blk blk-table">${b.html}</div>`;
      case 'note':
        return `<div class="blk private-blk"><div class="p-label">🔒 ${esc(b.label || 'تنبيهات التلقين — طبقتي الخاصة')}</div>${b.html}</div>`;
      case 'example': {
        const id = 'ex' + (ctx.exIdx++);
        const steps = b.steps.map((s, i) =>
          `<div class="step-item ${i ? 'veiled' : ''}" data-ex="${id}" data-i="${i}">${s}</div>`).join('');
        const more = b.steps.length > 1
          ? `<button class="reveal-btn" data-reveal="${id}">👁 أظهر الخطوة التالية (١/${b.steps.length})</button>` : '';
        return `<div class="blk blk-example">
          <div class="exq">${b.q}</div>
          ${b.givens ? `<div class="givens">${b.givens}</div>` : ''}
          <div class="steps">${steps}${more}</div>
        </div>`;
      }
      case 'quiz':
        return b.items.map((it, qi) => `
          <div class="blk-quiz-item">
            <div class="q">${qi + 1}. ${it.q}</div>
            <div class="opts">${it.opts.map((o, oi) =>
              `<div class="opt ${oi === it.a ? 'correct-mark' : ''}"><span class="letter">${'أبجد'[oi] || oi + 1}</span>${o}</div>`).join('')}
            </div>
            <div class="private-blk"><div class="p-label">🔒 الجواب: ${'أبجد'[it.a]}</div>${it.why || ''}</div>
          </div>`).join('');
      case 'sim':
        return `<div class="blk blk-sim">🧪 <b>${esc(b.title)}</b> — محاكاة تفاعلية متوفرة في موقع الطلاب. ${esc(b.sub)}</div>`;
      case 'ministry':
        return `<div class="blk blk-qa">${b.html}</div>`;
      case 'try':
        return `<div class="blk blk-qa"><div class="q">✍ جرّب بنفسك</div>${b.html}</div>`;
      case 'figure':
        return `<div class="blk" style="text-align:center;background:#fff;border-radius:14px;padding:10px">${b.html}${b.caption ? `<div style="color:#334;font-size:.85rem">${esc(b.caption)}</div>` : ''}</div>`;
      default:
        return `<div class="blk">${b.html || ''}</div>`;
    }
  }

  /* ─────────── شاشة الدرس (أسبوع + محتوى) ─────────── */
  async function renderWeek(cls, n) {
    const cw = DATA.schedule.classes[cls];
    const wi = Engine.weekInfo(DATA.schedule, cls, +n);
    if (!wi) { location.hash = '#/'; return; }
    const perWeek = Store.state.settings[cls].perWeek;

    // حصص هذا الأسبوع + الحصة السابقة (لعرض ملاحظتها وواجبها)
    const slots = Engine.allSlots(DATA.schedule, cls);
    const weekSlots = slots.filter(s => s.week === +n);
    const firstIdx = slots.findIndex(s => s.week === +n);
    // آخر حصة سابقة لها ملاحظة أو واجب فعلي
    let prev = null, prevData = {};
    for (let i = firstIdx - 1; i >= 0; i--) {
      const d = Store.session(slots[i].key);
      if (d.note || d.homework) { prev = slots[i]; prevData = d; break; }
    }

    // تحميل الدروس المرتبطة
    const docs = [];
    for (const id of (wi.lessons || [])) {
      if (!DATA.lessonCache[id]) {
        try {
          const r = await fetch('content/lessons/' + id + '.json');
          DATA.lessonCache[id] = r.ok ? await r.json() : { missing: true, id };
        } catch (e) { DATA.lessonCache[id] = { missing: true, id }; }
      }
      docs.push(DATA.lessonCache[id]);
    }

    const sessionsHTML = weekSlots.map(s => {
      const st = Engine.statusOf(s.key);
      return `<button class="session-chip ${st}" data-key="${s.key}">
        حصة ${s.slot} · ${Engine.fmtShort(s.date)}
        <span class="st">${STATUS[st]}</span>
      </button>`;
    }).join('');

    // الشرائح: تمهيد + مقاطع كل درس
    const slides = [];
    for (const doc of docs) {
      if (doc.missing) {
        slides.push({
          title: 'المحتوى', icon: '📦',
          html: `<div class="placeholder-lesson">
            <h2>📦 قالب فارغ — بانتظار المحتوى</h2>
            <p>هذا الدرس (<b>${esc(doc.id)}</b>) لم يُحوَّل بعد من مشروعك.<br>
            أضِفه إلى <b>content/manifest.json</b> ثم شغّل <b>node tools/compile.mjs</b> — بلا لمس أي كود.</p>
          </div>`,
        });
        continue;
      }
      const ctx = { exIdx: 0 };
      if (doc.hook) slides.push({
        title: 'التمهيد', icon: '🚀',
        html: `<div class="blk blk-qa" style="font-size:1.15rem">${doc.hook.html}</div>
               ${doc.subtitle ? `<p style="color:var(--muted)">${esc(doc.subtitle)}</p>` : ''}`,
        noteKey: doc.id + ':hook',
      });
      doc.sections.forEach((sec, si) => {
        slides.push({
          title: sec.title, icon: sec.icon || '📘',
          html: sec.blocks.map(b => blockHTML(b, ctx)).join(''),
          noteKey: doc.id + ':sec' + si,
        });
      });
    }
    if (!docs.length) slides.push({
      title: 'المحتوى', icon: '📦',
      html: `<div class="placeholder-lesson">
        <h2>📦 لا محتوى مرتبط بهذا الأسبوع بعد</h2>
        <p>موضوع الأسبوع: <b>${esc(wi.topic)}</b><br>اربط درساً في <b>schedule.json</b> (حقل lessons) بعد تحويله.</p>
      </div>`,
    });

    const navBtns = slides.map((s, i) =>
      `<button class="snav-btn ${i === 0 ? 'active' : ''}" data-slide="${i}">${s.icon} ${esc(s.title)}</button>`).join('');
    const slidesHTML = slides.map((s, i) => `
      <section class="slide" data-i="${i}">
        <h2 class="sec-title">${s.icon} ${esc(s.title)}</h2>
        ${s.html}
        ${s.noteKey ? `<div class="my-note-box teacher-ui">
          <div class="p-label">🗒 ملاحظتي التلقينية لهذا المقطع (تُحفظ تلقائياً)</div>
          <textarea data-notekey="${s.noteKey}" placeholder="مثال: اكتب القانون بالأحمر، انتبه لإشارة الشحنة..."></textarea>
        </div>` : ''}
      </section>`).join('');

    const lessonTitle = docs.length && !docs[0].missing ? docs[0].title : wi.topic;

    app().innerHTML = `
      <div class="lesson-head">
        <div class="crumb"><a href="#/">القمرة</a> / <a href="#/plan/${cls}">خطة ${esc(cw.short)}</a> / الأسبوع ${n}</div>
        <h1>${esc(lessonTitle)}</h1>
        <div class="sub">${esc(cw.label)} · ${Engine.fmtShort(wi.start)} – ${Engine.fmtShort(wi.end)} ${typeChip(wi.type)}</div>
      </div>

      <div class="sessions teacher-ui">${sessionsHTML}</div>

      <div class="notes-panel teacher-ui">
        ${prev && (prevData.note || prevData.homework) ? `
          <div class="prev-note">
            <b>من الحصة السابقة (أسبوع ${prev.week} حصة ${prev.slot}):</b>
            ${prevData.note ? `📝 ${esc(prevData.note)}` : ''}
            ${prevData.homework ? ` · 📚 الواجب: ${esc(prevData.homework)}` : ''}
          </div>` : ''}
        <label>📝 ملاحظة الحصة</label>
        <textarea id="sessNote" placeholder="ماذا جرى بالحصة؟ أين وصلت؟"></textarea>
        <label>📚 الواجب المُعطى</label>
        <textarea id="sessHW" placeholder="مثال: حل مسائل الفصل س1–س4"></textarea>
      </div>

      <div class="slides-nav">${navBtns}</div>
      <div class="slides" id="slides">${slidesHTML}</div>
      <div class="slide-arrows">
        <button class="tbtn" id="slPrev">→ السابق</button>
        <button class="tbtn primary" id="slNext">التالي ←</button>
      </div>
    `;

    /* ربط الأحداث */
    app().querySelectorAll('[data-go]').forEach(el => el.onclick = () => location.hash = el.dataset.go);

    // حالة الحصص: نقرة تدوّر الحالة — تحديث موضعي كي لا يتصفّر المؤقّت أثناء الحصة
    app().querySelectorAll('.session-chip').forEach(chip => {
      chip.onclick = () => {
        const k = chip.dataset.key;
        const nxt = NEXT_STATUS[Engine.statusOf(k)];
        Store.setSession(k, { status: nxt });
        chip.className = 'session-chip ' + nxt;
        chip.querySelector('.st').textContent = STATUS[nxt];
      };
    });

    // ملاحظة الحصة والواجب — تُخزَّن على مفتاح الحصة القادمة غير المنجزة في هذا الأسبوع (أو الأولى)
    const target = weekSlots.find(s => !['done'].includes(Engine.statusOf(s.key))) || weekSlots[0];
    if (target) {
      const sd = Store.session(target.key);
      const nEl = document.getElementById('sessNote'), hEl = document.getElementById('sessHW');
      nEl.value = sd.note || ''; hEl.value = sd.homework || '';
      nEl.oninput = () => Store.setSession(target.key, { note: nEl.value });
      hEl.oninput = () => Store.setSession(target.key, { homework: hEl.value });
    }

    // ملاحظاتي التلقينية لكل مقطع
    app().querySelectorAll('textarea[data-notekey]').forEach(ta => {
      ta.value = Store.note(ta.dataset.notekey);
      ta.oninput = () => Store.setNote(ta.dataset.notekey, ta.value);
    });

    // كشف خطوات الأمثلة تدريجياً
    app().querySelectorAll('[data-reveal]').forEach(btn => {
      btn.onclick = () => {
        const id = btn.dataset.reveal;
        const hidden = app().querySelectorAll(`.step-item.veiled[data-ex="${id}"]`);
        if (hidden.length) {
          hidden[0].classList.remove('veiled');
          const total = app().querySelectorAll(`.step-item[data-ex="${id}"]`).length;
          const shown = total - hidden.length + 1;
          if (hidden.length === 1) btn.remove();
          else btn.textContent = `👁 أظهر الخطوة التالية (${shown}/${total})`;
        }
      };
    });

    // تنقّل الشرائح
    const slidesEl = document.getElementById('slides');
    const navEls = app().querySelectorAll('.snav-btn');
    const goSlide = i => {
      const el = slidesEl.querySelector(`.slide[data-i="${i}"]`);
      if (el) el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    };
    navEls.forEach(b => b.onclick = () => goSlide(+b.dataset.slide));
    let curSlide = 0;
    slidesEl.addEventListener('scroll', () => {
      const w = slidesEl.clientWidth;
      const i = Math.round(Math.abs(slidesEl.scrollLeft) / (w + 14));
      if (i !== curSlide && i < slides.length) {
        curSlide = i;
        navEls.forEach((b, bi) => b.classList.toggle('active', bi === i));
        const nb = navEls[i];
        if (nb) nb.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
      }
    }, { passive: true });
    document.getElementById('slPrev').onclick = () => goSlide(Math.max(0, curSlide - 1));
    document.getElementById('slNext').onclick = () => goSlide(Math.min(slides.length - 1, curSlide + 1));

    LessonTimer.show();
  }

  /* ─────────── الإعدادات ─────────── */
  function renderSettings() {
    LessonTimer.hide();
    const sc = DATA.schedule.classes;
    const cal = Store.state.settings.calendar || DATA.schedule.calendar;
    const phases = Store.state.settings.timerPhases;

    app().innerHTML = `
      <div class="plan-head">
        <h1 class="screen-title">⚙️ الإعدادات</h1>
        <button class="tbtn ghost" data-go="#/">⬆ القمرة</button>
      </div>

      ${['g9', 'g12'].map(c => `
        <div class="settings-grp">
          <h3>${esc(sc[c].label)}</h3>
          <div class="field">
            <label>📅 تاريخ بداية الدروس (الأنكر)</label>
            <input type="date" id="anchor-${c}" value="${Store.state.settings[c].anchor || sc[c].defaultAnchor}">
          </div>
          <div class="field">
            <label>🔢 الحصص الأسبوعية</label>
            <input type="number" id="pw-${c}" min="1" max="6" value="${Store.state.settings[c].perWeek}">
          </div>
        </div>`).join('')}

      <div class="settings-grp">
        <h3>⏱ مراحل الحصة (بالدقائق)</h3>
        ${phases.map((p, i) => `
          <div class="field">
            <label>${esc(p.name)}</label>
            <input type="number" id="ph-${i}" min="1" max="60" value="${p.min}">
          </div>`).join('')}
      </div>

      <div class="settings-grp">
        <h3>📆 تواريخ الوزارة (قابلة للتحديث عند الإعلان)</h3>
        ${Object.entries(cal).map(([k, v]) => `
          <div class="field">
            <label>${esc(v.label)}</label>
            <span style="display:flex;gap:6px">
              <input type="date" id="cal-${k}-from" value="${v.from}">
              <input type="date" id="cal-${k}-to" value="${v.to}">
            </span>
          </div>`).join('')}
      </div>

      <div class="settings-grp">
        <h3>💾 النسخ الاحتياطي</h3>
        <div class="settings-actions">
          <button class="tbtn primary" id="btnExport">⬇ تصدير JSON</button>
          <button class="tbtn" id="btnImport">⬆ استيراد JSON</button>
          <button class="tbtn danger" id="btnReset">🗑 إعادة ضبط كاملة</button>
        </div>
        <input type="file" id="importFile" accept="application/json" class="hidden">
      </div>

      <button class="tbtn primary" id="saveSettings" style="width:100%;min-height:58px;font-size:1.1rem">💾 حفظ الإعدادات</button>
    `;

    app().querySelectorAll('[data-go]').forEach(el => el.onclick = () => location.hash = el.dataset.go);
    document.getElementById('saveSettings').onclick = () => {
      for (const c of ['g9', 'g12']) {
        Store.state.settings[c].anchor = document.getElementById('anchor-' + c).value;
        Store.state.settings[c].perWeek = Math.max(1, +document.getElementById('pw-' + c).value || 1);
      }
      phases.forEach((p, i) => p.min = Math.max(1, +document.getElementById('ph-' + i).value || p.min));
      const newCal = {};
      for (const [k, v] of Object.entries(cal)) {
        newCal[k] = { from: document.getElementById(`cal-${k}-from`).value, to: document.getElementById(`cal-${k}-to`).value, label: v.label };
      }
      Store.state.settings.calendar = newCal;
      Store.save();
      location.hash = '#/';
    };
    document.getElementById('btnExport').onclick = Store.exportJSON;
    document.getElementById('btnImport').onclick = () => document.getElementById('importFile').click();
    document.getElementById('importFile').onchange = e => {
      const f = e.target.files[0];
      if (f) Store.importJSON(f, err => {
        alert(err ? '⚠ الملف غير صالح: ' + err.message : '✔ تم الاستيراد بنجاح');
        if (!err) location.reload();
      });
    };
    document.getElementById('btnReset').onclick = () => {
      if (confirm('سيُمسح كل التقدّم والملاحظات نهائياً. متأكد؟')) Store.reset();
    };
  }

  window.Views = { renderSetup, renderHome, renderPlan, renderWeek, renderSettings };
})();
