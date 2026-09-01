#!/usr/bin/env node
/**
 * دفّة — المحوِّل (adapter/compiler)
 * يقرأ دروس PHY (صيغة phy-v1) و PHY6 (صيغة phy6-v1) كما هي، بلا أي تعديل عليها،
 * ويستخلص منها LessonDoc موحّد إلى content/lessons/<id>.json
 *
 * التشغيل من مجلد DAFFA:  node tools/compile.mjs
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

/* ─────────────── مُحلّل HTML صغير (بلا اعتماديات) ─────────────── */
const VOID = new Set(['meta','link','img','br','hr','input','source','area','base','col','embed','param','track','wbr']);

function parseHTML(src) {
  const root = { tag: '#root', attrs: {}, children: [], parent: null, openEnd: 0, closeStart: src.length };
  let cur = root, i = 0;

  function findTagEnd(from) {
    let q = null;
    for (let k = from; k < src.length; k++) {
      const c = src[k];
      if (q) { if (c === q) q = null; }
      else if (c === '"' || c === "'") q = c;
      else if (c === '>') return k;
    }
    return src.length - 1;
  }
  function parseAttrs(s) {
    const attrs = {};
    const re = /([a-zA-Z][\w:-]*)\s*(?:=\s*("([^"]*)"|'([^']*)'|[^\s>]+))?/g;
    let m;
    while ((m = re.exec(s))) attrs[m[1].toLowerCase()] = m[3] ?? m[4] ?? (m[2] || '');
    return attrs;
  }

  while (i < src.length) {
    if (src.startsWith('<!--', i)) { const e = src.indexOf('-->', i); i = e === -1 ? src.length : e + 3; continue; }
    if (src[i] === '<') {
      if (src[i + 1] === '/') {
        const j = src.indexOf('>', i);
        const tag = src.slice(i + 2, j).trim().toLowerCase();
        let n = cur;
        while (n !== root && n.tag !== tag) n = n.parent;
        if (n !== root) { n.closeStart = i; cur = n.parent; }
        i = j + 1; continue;
      }
      if (src[i + 1] === '!') { i = src.indexOf('>', i) + 1; continue; }
      const j = findTagEnd(i + 1);
      const tagText = src.slice(i + 1, j);
      const m = tagText.match(/^([a-zA-Z][\w-]*)/);
      if (!m) { i = j + 1; continue; }
      const tag = m[1].toLowerCase();
      const node = { tag, attrs: parseAttrs(tagText.slice(m[1].length)), children: [], parent: cur, openEnd: j + 1, closeStart: j + 1 };
      cur.children.push(node);
      if (tag === 'script' || tag === 'style') {
        const end = src.indexOf('</' + tag, j + 1);
        node.children.push({ tag: '#text', text: src.slice(j + 1, end === -1 ? src.length : end), parent: node });
        node.closeStart = end === -1 ? src.length : end;
        i = end === -1 ? src.length : src.indexOf('>', end) + 1;
        continue;
      }
      if (!VOID.has(tag) && !/\/\s*$/.test(tagText)) cur = node;
      i = j + 1; continue;
    }
    const j = src.indexOf('<', i);
    const end = j === -1 ? src.length : j;
    cur.children.push({ tag: '#text', text: src.slice(i, end), parent: cur });
    i = end;
  }
  return { root, src };
}

const cls = n => (n.attrs && n.attrs.class ? n.attrs.class.split(/\s+/).filter(Boolean) : []);
const hasClass = (n, c) => cls(n).includes(c);

function* walk(n) { yield n; if (n.children) for (const c of n.children) yield* walk(c); }
function find(root, pred) { for (const n of walk(root)) if (n.tag !== '#text' && pred(n)) return n; return null; }
function findAll(root, pred) { const out = []; for (const n of walk(root)) if (n.tag !== '#text' && pred(n)) out.push(n); return out; }
function text(n) {
  let s = '';
  for (const d of walk(n)) if (d.tag === '#text') s += d.text;
  return s.replace(/\s+/g, ' ').trim();
}
const inner = (doc, n) => doc.src.slice(n.openEnd, n.closeStart).trim();

/** إزالة وسم <span class="tag">..</span> من HTML سؤال */
const stripTagSpan = html => html.replace(/<span class="tag">[\s\S]*?<\/span>/g, '').trim();

/* ─────────────── محوّل phy-v1 (الثالث المتوسط) ─────────────── */
function adaptPhyV1(doc, meta) {
  const { root } = doc;
  const lesson = {
    id: meta.id, grade: meta.grade, format: 'phy-v1',
    title: meta.title || '', subtitle: '', hook: null, sections: [],
    source: meta.source, compiledAt: new Date().toISOString().slice(0, 10),
  };

  const hero = find(root, n => hasClass(n, 'hero'));
  if (hero) {
    const h1 = find(hero, n => n.tag === 'h1');
    const p = find(hero, n => n.tag === 'p');
    if (h1) lesson.title = text(h1);
    if (p) lesson.subtitle = text(p);
  }
  const hook = find(root, n => hasClass(n, 'hook'));
  if (hook) {
    const spans = hook.children.filter(c => c.tag === 'span' && !hasClass(c, 'em'));
    lesson.hook = { html: spans.length ? inner(doc, spans[spans.length - 1]) : inner(doc, hook) };
  }

  // الاختبار من Phy.quiz داخل <script>
  let quizItems = null;
  for (const sc of findAll(root, n => n.tag === 'script')) {
    const js = sc.children.map(c => c.text || '').join('');
    const at = js.indexOf('Phy.quiz(');
    if (at === -1) continue;
    const start = js.indexOf('[', at);
    let depth = 0, end = -1, inStr = null;
    for (let k = start; k < js.length; k++) {
      const c = js[k];
      if (inStr) { if (c === '\\') k++; else if (c === inStr) inStr = null; continue; }
      if (c === '"' || c === "'" || c === '`') inStr = c;
      else if (c === '[') depth++;
      else if (c === ']') { depth--; if (!depth) { end = k; break; } }
    }
    if (end !== -1) {
      try { quizItems = vm.runInNewContext('(' + js.slice(start, end + 1) + ')', {}, { timeout: 1000 }); }
      catch (e) { console.warn(`  ⚠ تعذّر تفسير اختبار ${meta.id}: ${e.message}`); }
    }
    break;
  }

  // مقاطع الدرس بترتيبها داخل .wrap
  const wrap = find(root, n => hasClass(n, 'wrap')) || root;
  let section = null;
  const pushSection = (title, icon) => { section = { title, icon, blocks: [] }; lesson.sections.push(section); };

  const handleCardChild = (ch) => {
    if (ch.tag === 'details' && hasClass(ch, 'qa')) {
      const sum = find(ch, n => n.tag === 'summary');
      const ans = find(ch, n => hasClass(n, 'ans'));
      section.blocks.push({ type: 'qa', q: sum ? stripTagSpan(inner(doc, sum)) : '', a: ans ? inner(doc, ans) : '' });
    } else if (hasClass(ch, 'lawbox')) {
      section.blocks.push({ type: 'law', html: inner(doc, ch) });
    } else if (hasClass(ch, 'tblwrap') || ch.tag === 'table') {
      section.blocks.push({ type: 'table', html: inner(doc, ch) });
    } else if (hasClass(ch, 'notebox')) {
      section.blocks.push({ type: 'note', html: inner(doc, ch), private: true });
    } else if (ch.tag !== '#text') {
      const h = inner(doc, ch);
      if (h) section.blocks.push({ type: 'html', html: h });
    }
  };

  for (const el of wrap.children) {
    if (el.tag === '#text') continue;
    if (hasClass(el, 'topbar') || hasClass(el, 'hero') || hasClass(el, 'hook') ||
        hasClass(el, 'lesson-nav') || el.tag === 'footer' || el.tag === 'script') continue;

    if (hasClass(el, 'section-title')) {
      const ico = find(el, n => hasClass(n, 'ico'));
      const icon = ico ? text(ico) : '';
      const t = text(el).replace(icon, '').trim();
      pushSection(t, icon);
      continue;
    }
    if (!section) pushSection('الدرس', '📘');

    if (hasClass(el, 'card')) { for (const ch of el.children) handleCardChild(ch); continue; }
    if (hasClass(el, 'example')) {
      const exq = find(el, n => hasClass(n, 'exq'));
      const giv = find(el, n => hasClass(n, 'givens'));
      const steps = findAll(el, n => hasClass(n, 'step')).map(s => inner(doc, s));
      section.blocks.push({ type: 'example', q: exq ? inner(doc, exq) : '', givens: giv ? inner(doc, giv) : '', steps });
      continue;
    }
    if (hasClass(el, 'sim')) {
      const h3 = find(el, n => n.tag === 'h3');
      const sub = find(el, n => hasClass(n, 'sim-sub'));
      section.blocks.push({ type: 'sim', title: h3 ? text(h3) : 'محاكاة تفاعلية', sub: sub ? text(sub) : '' });
      continue;
    }
    if (el.attrs && /^quiz/.test(el.attrs.id || '')) {
      if (quizItems) section.blocks.push({ type: 'quiz', items: quizItems });
      continue;
    }
    const h = inner(doc, el);
    if (h) section.blocks.push({ type: 'html', html: h });
  }
  return lesson;
}

/* ─────────────── محوّل phy6-v1 (السادس العلمي — ملزمة) ─────────────── */
function adaptPhy6V1(doc, meta) {
  const { root } = doc;
  const lesson = {
    id: meta.id, grade: meta.grade, format: 'phy6-v1',
    title: meta.title || '', subtitle: '', hook: null, sections: [],
    source: meta.source, compiledAt: new Date().toISOString().slice(0, 10),
  };
  const hero = find(root, n => hasClass(n, 'lesson-hero'));
  if (hero) {
    const h1 = find(hero, n => n.tag === 'h1');
    const sub = find(hero, n => hasClass(n, 'sub'));
    if (h1) lesson.title = text(h1);
    if (sub) lesson.subtitle = text(sub);
  }
  const ideaBox = find(root, n => hasClass(n, 'idea-box'));
  if (ideaBox) {
    const ps = ideaBox.children.filter(c => c.tag === 'p');
    lesson.hook = { html: ps.map(p => '<p>' + inner(doc, p) + '</p>').join('') };
  }

  const rtl = find(root, n => hasClass(n, 'rtl-root')) || root;
  let section = null;
  const pushSection = (title, icon) => { section = { title, icon, blocks: [] }; lesson.sections.push(section); };

  for (const el of rtl.children) {
    if (el.tag === '#text' || el.tag === 'script' || hasClass(el, 'lesson-hero') || hasClass(el, 'idea-box')) continue;

    if (hasClass(el, 'idea')) {
      const h2 = find(el, n => n.tag === 'h2');
      const num = find(el, n => hasClass(n, 'n'));
      pushSection(h2 ? text(h2) : 'فكرة', num ? text(num) : '💡');
      continue;
    }
    if (!section) pushSection('الدرس', '📘');

    if (hasClass(el, 'formula')) { section.blocks.push({ type: 'law', html: inner(doc, el) }); continue; }
    if (hasClass(el, 'box')) {
      const c = cls(el);
      const body = inner(doc, el).replace(/<span class="tab">[\s\S]*?<\/span>/, '').trim();
      if (c.includes('gold')) section.blocks.push({ type: 'law', label: 'قاعدة ذهبية · التعريف الوزاري', html: body });
      else if (c.includes('warn')) section.blocks.push({ type: 'note', label: 'أخطاء شائعة — انتبه', html: body, private: true });
      else if (c.includes('ministry')) section.blocks.push({ type: 'ministry', html: body });
      else if (c.includes('try')) section.blocks.push({ type: 'try', html: body });
      else section.blocks.push({ type: 'html', html: body });
      continue;
    }
    if (hasClass(el, 'chk')) { section.blocks.push({ type: 'qa', q: inner(doc, el), a: '' }); continue; }
    if (el.tag === 'figure') {
      const svg = find(el, n => n.tag === 'svg');
      const cap = find(el, n => n.tag === 'figcaption');
      if (svg) section.blocks.push({ type: 'figure', html: doc.src.slice(svg.openEnd - (svg.closeStart - svg.openEnd) === 0 ? svg.openEnd : doc.src.lastIndexOf('<svg', svg.openEnd), svg.closeStart) + '</svg>', caption: cap ? text(cap) : '' });
      continue;
    }
    const h = inner(doc, el);
    if (h) section.blocks.push({ type: 'html', html: h });
  }
  return lesson;
}

/* ─────────────── التنفيذ ─────────────── */
const manifest = JSON.parse(readFileSync(resolve(ROOT, 'content/manifest.json'), 'utf8'));
let ok = 0, fail = 0;

for (const m of manifest.lessons) {
  if (m.status === 'empty') continue; // قالب فارغ — لا مصدر له
  const srcPath = resolve(ROOT, m.source);
  if (!existsSync(srcPath)) { console.error(`✘ ${m.id}: الملف غير موجود ${m.source}`); fail++; continue; }
  const doc = parseHTML(readFileSync(srcPath, 'utf8'));
  const lesson = m.format === 'phy6-v1' ? adaptPhy6V1(doc, m) : adaptPhyV1(doc, m);
  const out = resolve(ROOT, 'content/lessons', m.id + '.json');
  writeFileSync(out, JSON.stringify(lesson, null, 1), 'utf8');
  const nBlocks = lesson.sections.reduce((a, s) => a + s.blocks.length, 0);
  console.log(`✔ ${m.id} ← ${m.source}  (${lesson.sections.length} مقاطع، ${nBlocks} كتلة)`);
  ok++;
}
/* حزمة بيانات موحّدة تُحمَّل كسكربت — تجعل التطبيق يعمل من الفولدر مباشرة (file://)
   حيث يمنع المتصفح fetch. تشمل: الخطة + السجل + كل الدروس المحوَّلة. */
const schedule = JSON.parse(readFileSync(resolve(ROOT, 'schedule.json'), 'utf8'));
const lessons = {};
for (const m of manifest.lessons) {
  const p = resolve(ROOT, 'content/lessons', m.id + '.json');
  if (existsSync(p)) lessons[m.id] = JSON.parse(readFileSync(p, 'utf8'));
}
const bundle = { schedule, manifest, lessons, builtAt: new Date().toISOString() };
writeFileSync(resolve(ROOT, 'content/bundle.js'),
  '/* يُولَّد آلياً بـ tools/compile.mjs — لا يُحرَّر يدوياً */\n' +
  'window.DAFFA_BUNDLE = ' + JSON.stringify(bundle) + ';\n', 'utf8');
console.log(`✔ content/bundle.js (${Object.keys(lessons).length} درس مضمّن)`);

console.log(`\nتم: ${ok} درس${fail ? ` — فشل: ${fail}` : ''}`);
