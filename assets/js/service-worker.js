// Sets up the website to allow it to be installed as a PWA
const CACHE_NAME = 'eist-radio-cache-v2';

const ASSETS_TO_CACHE = [
    '/',
    '/index.html',
    '/js/*',
    '/eist_online.png',
    '/eist_offline.png',
    '/gradient-96x96.png',
    '/gradient-128x128.png',
    '/gradient-192x192.png',
    '/gradient-256x256.png',
    '/gradient-384x384.png',
    '/gradient-512x512.png'
];

// Install service worker and cache assets
self.addEventListener('install', async (event) => {
    event.waitUntil(
        (async () => {
            const cache = await caches.open(CACHE_NAME);
            const cssFiles = await fetchCssFiles();
            await cache.addAll([...ASSETS_TO_CACHE, ...cssFiles]);
        })()
    );
    self.skipWaiting();
});

// Fetch all CSS files dynamically
async function fetchCssFiles() {
    try {
        const response = await fetch('/css/');
        const text = await response.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(text, 'text/html');
        return [...doc.querySelectorAll('a[href$=".css"]')].map(link => `/css/${link.getAttribute('href')}`);
    } catch (error) {
        console.error('Error fetching CSS files:', error);
        return [];
    }
}

// Activate service worker and clean up old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.filter((name) => name !== CACHE_NAME)
                          .map((name) => caches.delete(name))
            );
        }).then(() => self.clients.matchAll())
          .then((clients) => {
              clients.forEach(client => client.navigate(client.url));
          })
    );
    self.clients.claim();
});

// Fetch event: prefer fresh network response, fallback to cache
self.addEventListener('fetch', (event) => {
    event.respondWith(
        fetch(event.request)
            .then((networkResponse) => {
                return caches.open(CACHE_NAME).then((cache) => {
                    cache.put(event.request, networkResponse.clone());
                    return networkResponse;
                });
            })
            .catch(() => caches.match(event.request))
    );
});

// Check if it's the first visit in this session
document.addEventListener("DOMContentLoaded", function () {
    if (!sessionStorage.getItem("visited")) {
        console.log("First visit detected");
        sessionStorage.setItem("visited", "true");

        // Reload using Turbo
        setTimeout(() => {
            Turbo.visit(window.location.href, { action: "replace" });
        }, 100);
    }
});

