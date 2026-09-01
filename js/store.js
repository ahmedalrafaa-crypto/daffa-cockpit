/* دفّة — التخزين المحلي: الإعدادات، حالة الحصص، الملاحظات. تصدير/استيراد JSON */
(function () {
  const KEY = 'daffa.v1';

  const DEFAULTS = {
    settings: {
      g9: { anchor: null, perWeek: 2 },
      g12: { anchor: null, perWeek: 4 },
      calendar: null, // يُملأ من schedule.json ويُعدَّل من الإعدادات
      timerPhases: [
        { name: 'تمهيد', min: 5 },
        { name: 'شرح', min: 15 },
        { name: 'تطبيق وحل', min: 15 },
        { name: 'تقويم', min: 5 },
      ],
      setupDone: false,
    },
    // "g9:w3:s1" → { status: 'done'|'partial'|'deferred', note: '', homework: '' }
    sessions: {},
    // "g9-ch1-l6:sec2" → "ملاحظتي التلقينية"
    notes: {},
  };

  let state;
  try { state = JSON.parse(localStorage.getItem(KEY)) || null; } catch (e) { state = null; }
  if (!state) state = JSON.parse(JSON.stringify(DEFAULTS));
  // دمج أي حقول جديدة بعد تحديثات مستقبلية
  state.settings = Object.assign({}, DEFAULTS.settings, state.settings);
  state.sessions = state.sessions || {};
  state.notes = state.notes || {};

  function save() { localStorage.setItem(KEY, JSON.stringify(state)); }

  window.Store = {
    get state() { return state; },
    save,
    session(k) { return state.sessions[k] || {}; },
    setSession(k, patch) {
      state.sessions[k] = Object.assign({}, state.sessions[k], patch);
      save();
    },
    note(k) { return state.notes[k] || ''; },
    setNote(k, v) {
      if (v) state.notes[k] = v; else delete state.notes[k];
      save();
    },
    exportJSON() {
      const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      const d = new Date().toISOString().slice(0, 10);
      a.download = `daffa-backup-${d}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    },
    importJSON(file, cb) {
      const r = new FileReader();
      r.onload = () => {
        try {
          const data = JSON.parse(r.result);
          if (!data.settings) throw new Error('ملف غير صالح');
          state = data;
          save();
          cb(null);
        } catch (e) { cb(e); }
      };
      r.readAsText(file);
    },
    reset() { localStorage.removeItem(KEY); location.reload(); },
  };
})();
