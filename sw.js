/* دفّة — service worker: تخزين كامل للعمل أوفلاين 100% */
const VERSION = 'daffa-v5';
const PRECACHE = [
  './',
  './index.html',
  './manifest.webmanifest',
  './css/app.css',
  './js/store.js',
  './js/engine.js',
  './js/timer.js',
  './js/views.js',
  './js/app.js',
  './schedule.json',
  './content/bundle.js',
  './content/manifest.json',
  './content/lessons/g9-ch1-l1.json',
  './content/lessons/g9-ch1-l2.json',
  './content/lessons/g9-ch1-l3.json',
  './content/lessons/g9-ch1-l6.json',
  './content/lessons/g9-ch1-l7.json',
  './content/lessons/g9-ch2-l1.json',
  './content/lessons/g9-ch2-l2.json',
  './content/lessons/g9-ch2-l3.json',
  './content/lessons/g9-ch2-l4.json',
  './content/lessons/g9-ch3-l1.json',
  './content/lessons/g9-ch3-l2.json',
  './content/lessons/g9-ch3-l5.json',
  './content/lessons/g9-ch3-l6.json',
  './content/lessons/g9-ch3-l7.json',
  './content/lessons/g9-ch5-l1.json',
  './content/lessons/g9-ch5-l2.json',
  './content/lessons/g9-ch5-l3.json',
  './content/lessons/g9-ch5-l5.json',
  './content/lessons/g9-ch6-l1.json',
  './content/lessons/g9-ch6-l2.json',
  './content/lessons/g9-ch6-l3.json',
  './content/lessons/g9-ch6-l4.json',
  './content/lessons/g9-ch6-l6.json',
  './content/lessons/g9-ch6-l7.json',
  './content/lessons/g9-ch6-l8.json',
  './content/lessons/g9-ch7-l1.json',
  './content/lessons/g9-ch7-l2.json',
  './content/lessons/g9-ch7-l4.json',
  './content/lessons/g12-ch1-l1.json',
  './content/lessons/g12-ch1-l2.json',
  './content/lessons/g12-ch1-l3.json',
  './content/lessons/g12-ch2-l1.json',
  './content/lessons/g12-ch2-l2.json',
  './content/lessons/g12-ch2-l3.json',
  './content/lessons/g12-ch2-l4.json',
  './content/lessons/g12-ch3-l1.json',
  './content/lessons/g12-ch3-l2.json',
  './content/lessons/g12-ch3-l3.json',
  './content/lessons/g12-ch6-l1.json',
  './content/lessons/g12-ch7-l2.json',
  './content/lessons/g12-ch7-l3.json',
  './content/lessons/g12-ch8-l1.json',
  './content/lessons/g12-ch8-l2.json',
  './content/lessons/g12-ch8-l3.json',
  './content/lessons/g12-ch9-l1.json',
  './content/lessons/g12-ch9-l2.json',
  './content/lessons/g12-ch9-l3.json',
  './assets/logo-ar.png',
  './assets/icon-192.png',
  './assets/icon-512.png',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

/* قدّم من الكاش فوراً (أوفلاين أولاً) وحدّثه بالخلفية عند توفر الشبكة —
   هكذا يبقى التطبيق سريعاً بلا إنترنت، وتصله التحديثات تلقائياً عند أول اتصال */
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then(hit => {
      const refresh = fetch(e.request).then(res => {
        if (res.ok && new URL(e.request.url).origin === location.origin) {
          const copy = res.clone();
          caches.open(VERSION).then(c => c.put(e.request, copy));
        }
        return res;
      }).catch(() => hit || caches.match('./index.html'));
      return hit || refresh;
    })
  );
});
