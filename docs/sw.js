const CACHE_NAME = 'cotacao-campo-v16';

// Arquivos do próprio app (mesma origem): falha em qualquer um cancela a instalação
const LOCAL = [
  './',
  './index.html',
  './util.js',
  './grafico.js',
  './auth.js',
  './app.js',
  './manifest.json',
  './dados.json',
  './icon-192.png',
  './icon-512.png'
];

// CDNs: guardados um a um (respostas "opaque" quebram o addAll)
const CDN = [
  'https://cdn.tailwindcss.com',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css'
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll(LOCAL);
    await Promise.allSettled(CDN.map(async (url) => {
      const resp = await fetch(new Request(url, { mode: 'no-cors' }));
      await cache.put(url, resp);
    }));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const nomes = await caches.keys();
    await Promise.all(nomes.filter(n => n !== CACHE_NAME).map(n => caches.delete(n)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // Cotações: rede primeiro (sempre o dado mais novo); offline usa o último salvo
  if (url.origin === self.location.origin && url.pathname.endsWith('/dados.json')) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);
      try {
        const resp = await fetch(req, { cache: 'no-cache' });
        if (resp.ok) cache.put(req, resp.clone());
        return resp;
      } catch {
        return (await cache.match(req)) || Response.error();
      }
    })());
    return;
  }

  // Demais arquivos: cache primeiro e atualização em segundo plano
  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const guardado = await cache.match(req, { ignoreSearch: true });
    const rede = fetch(req).then((resp) => {
      if (resp && (resp.ok || resp.type === 'opaque')) cache.put(req, resp.clone());
      return resp;
    }).catch(() => null);
    return guardado || (await rede) || (req.mode === 'navigate' ? cache.match('./index.html') : Response.error());
  })());
});
