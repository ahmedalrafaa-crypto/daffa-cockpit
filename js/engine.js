/* دفّة — محرك الجدولة: حساب تواريخ الأسابيع، الحصص، التقدّم مقابل الخطة */
(function () {
  const DAY = 86400000;

  function parseDate(s) { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); }
  function fmtDate(d) {
    return d.toLocaleDateString('ar-IQ', { weekday: 'long', day: 'numeric', month: 'long' });
  }
  function fmtShort(d) { return d.toLocaleDateString('ar-IQ', { day: 'numeric', month: 'short' }); }
  function today0() { const t = new Date(); t.setHours(0, 0, 0, 0); return t; }

  /** أحد الأسبوع الذي يقع فيه التاريخ (الأسبوع الدراسي: أحد–خميس) */
  function sundayOf(d) {
    const x = new Date(d); x.setHours(0, 0, 0, 0);
    x.setDate(x.getDate() - x.getDay()); // getDay: الأحد = 0
    return x;
  }

  /** توزيع حصص الأسبوع على أيام الدوام (0=أحد .. 4=خميس) */
  function dayOffsets(perWeek) {
    if (perWeek >= 5) return [0, 1, 2, 3, 4];
    return { 1: [0], 2: [0, 2], 3: [0, 2, 4], 4: [0, 1, 2, 3] }[perWeek] || [0, 2];
  }

  const isHolidayType = t => t.includes('عطلة') || t.includes('امتحان');

  /**
   * كل حصص السنة لصف معيّن بترتيبها الثابت.
   * ترقّم الأسابيع من الأنكر (تاريخ بداية الدروس اليدوي).
   */
  function allSlots(schedule, cls) {
    const cfg = Store.state.settings[cls];
    const cw = schedule.classes[cls];
    const anchor = parseDate(cfg.anchor || cw.defaultAnchor);
    const w0 = sundayOf(anchor);
    const perWeek = cfg.perWeek || cw.defaultPerWeek;
    const offs = dayOffsets(perWeek);
    const slots = [];
    for (const wk of cw.weeks) {
      if (isHolidayType(wk.type)) continue;
      const wkSunday = new Date(w0.getTime() + (wk.n - 1) * 7 * DAY);
      for (let s = 0; s < perWeek; s++) {
        const date = new Date(wkSunday.getTime() + offs[s] * DAY);
        // الأسبوع الأول: لا حصص قبل يوم الأنكر نفسه
        if (wk.n === 1 && date < anchor) continue;
        slots.push({
          cls, week: wk.n, slot: s + 1, date,
          topic: wk.topic, type: wk.type, lessons: wk.lessons || [],
          key: `${cls}:w${wk.n}:s${s + 1}`,
        });
      }
    }
    return slots;
  }

  function statusOf(key) { return Store.session(key).status || ''; }

  /** الحصة القادمة = أول حصة غير منجزة وغير جزئية (المؤجلة تبقى في مكانها) */
  function nextSlot(slots) {
    return slots.find(s => !['done', 'partial'].includes(statusOf(s.key))) || null;
  }

  /** المؤشّر: (ما أنجزته فعلاً) − (ما كان مخططاً حتى اليوم) */
  function pace(slots) {
    const t = today0();
    const planned = slots.filter(s => s.date <= t).length;
    let done = 0;
    for (const s of slots) {
      const st = statusOf(s.key);
      if (st === 'done') done += 1;
      else if (st === 'partial') done += 0.5;
    }
    return { planned, done, delta: done - planned };
  }

  /** بيانات أسبوع واحد مع تاريخه المحسوب */
  function weekInfo(schedule, cls, n) {
    const cfg = Store.state.settings[cls];
    const cw = schedule.classes[cls];
    const wk = cw.weeks.find(w => w.n === n);
    if (!wk) return null;
    const anchor = parseDate(cfg.anchor || cw.defaultAnchor);
    const w0 = sundayOf(anchor);
    const start = new Date(w0.getTime() + (n - 1) * 7 * DAY);
    const end = new Date(start.getTime() + 4 * DAY);
    return Object.assign({ start, end }, wk);
  }

  function currentWeekN(schedule, cls) {
    const cfg = Store.state.settings[cls];
    const cw = schedule.classes[cls];
    const anchor = parseDate(cfg.anchor || cw.defaultAnchor);
    const diff = Math.floor((today0() - sundayOf(anchor)) / (7 * DAY)) + 1;
    return Math.max(1, Math.min(diff, cw.weeks.length));
  }

  window.Engine = { parseDate, fmtDate, fmtShort, today0, allSlots, nextSlot, pace, weekInfo, currentWeekN, statusOf, isHolidayType };
})();
