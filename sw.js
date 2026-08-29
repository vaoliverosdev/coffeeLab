const CACHE_NAME = "coffee-lab-v18.8";

const APP_SHELL = [
    "/",
    "/static/index.html",
    "/static/css/style.css?v=18.8",
    "/static/js/app.js?v=18.8",
    "/static/manifest.json",
    "/static/icons/icon-192.png",
    "/static/icons/icon-512.png"
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches
            .open(CACHE_NAME)
            .then((cache) => cache.addAll(APP_SHELL))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((cacheNames) =>
                Promise.all(
                    cacheNames
                        .filter((cacheName) => cacheName !== CACHE_NAME)
                        .map((cacheName) => caches.delete(cacheName))
                )
            )
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const request = event.request;

    if (request.method !== "GET") return;

    const url = new URL(request.url);

    if (url.origin !== self.location.origin) return;
    if (url.pathname.startsWith("/api/")) return;

    if (request.mode === "navigate") {
        event.respondWith(networkFirst(request, "/static/index.html"));
        return;
    }

    event.respondWith(staleWhileRevalidate(request));
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const actionUrl = event.notification.data?.action_url || "#/dashboard";
    const targetUrl = new URL("/", self.location.origin);
    targetUrl.hash = actionUrl.startsWith("#") ? actionUrl.slice(1) : actionUrl;

    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
            for (const client of clientList) {
                if ("focus" in client) {
                    client.navigate(targetUrl.href);
                    return client.focus();
                }
            }
            return clients.openWindow(targetUrl.href);
        })
    );
});

self.addEventListener("message", (event) => {
    if (event.data?.type === "SKIP_WAITING") {
        self.skipWaiting();
    }
});

async function networkFirst(request, fallbackPath) {
    const cache = await caches.open(CACHE_NAME);

    try {
        const response = await fetch(request);
        if (response && response.ok) {
            cache.put(request, response.clone());
        }
        return response;
    } catch {
        return (
            (await cache.match(request)) ||
            (await cache.match(fallbackPath)) ||
            (await cache.match("/"))
        );
    }
}

async function staleWhileRevalidate(request) {
    const cache = await caches.open(CACHE_NAME);
    const cachedResponse = await cache.match(request);

    const networkResponsePromise = fetch(request)
        .then((response) => {
            if (response && response.ok && response.type === "basic") {
                cache.put(request, response.clone());
            }
            return response;
        })
        .catch(() => null);

    return cachedResponse || (await networkResponsePromise) || new Response(
        "Conteudo indisponivel offline.",
        {
            status: 503,
            headers: {
                "Content-Type": "text/plain; charset=utf-8"
            }
        }
    );
}
