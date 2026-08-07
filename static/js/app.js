    (function () {

        'use strict';

        // --- SISTEMA DE TEMAS ---
        function toggleTheme() {
            const root = document.documentElement;
            const currentTheme = root.getAttribute('data-theme') || 'dark';
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

            // Aplica o tema visual
            root.setAttribute('data-theme', newTheme);
            localStorage.setItem('coffeelab-theme', newTheme);

            // Redesenha os gráficos com as cores do novo tema se estiver na página de estatísticas.
            if (location.hash === '#/stats' && typeof fetchAndRenderStats === 'function') {
            fetchAndRenderStats();
            }
        }

        function initTheme() {
            const savedTheme = localStorage.getItem('coffeelab-theme') || 'dark';
            document.documentElement.setAttribute('data-theme', savedTheme);
        }

    //O SEGREDO ESTÁ AQUI: Torna a função visível para o onclick="" do HTML
        window.toggleTheme = toggleTheme;

        // Executa a aplicação do tema assim que o JS carregar
        initTheme();

        window.sendAiPrompt = function(promptText) {
            const chatInput = document.getElementById('ai-chat-input');
            const chatForm = document.getElementById('ai-chat-form');
            if (chatInput) chatInput.value = promptText;
            if (chatForm) {
            chatForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
            }
        };

    const state = {
        token: localStorage.getItem("coffee_lab_token") || null,
        user: (() => {
            try {
                const savedUser = localStorage.getItem("coffee_lab_user");
                return savedUser ? JSON.parse(savedUser) : null;
            } catch {
                return null;
            }
        })(),
        coffees: [],
        stockItems: [],
        recipes: [],
        extractions: [],
        sensoryLogs: [],
        filterFav: false,
        recipeFilterFav: false
    };

        const html = document.documentElement;
        const authScreen = document.getElementById('auth-screen');
        const appScreen = document.getElementById('app');
        const welcomeTitle = document.getElementById('welcome-title');
        const userAvatarMini = document.getElementById('user-avatar-mini');
        const profileAvatarBig = document.getElementById('profile-avatar-big');
        const profileNameDisplay = document.getElementById('profile-name-display');
        const profileEmailDisplay = document.getElementById('profile-email-display');
        const coffeeModal = document.getElementById('coffee-modal');
        const coffeeGrid = document.getElementById('coffee-grid');
        const stockTableBody = document.getElementById('stock-table-body');
        const recipeGrid = document.getElementById('recipe-grid');
        const recipeModal = document.getElementById('recipe-modal');
        const recipeStepsBuilder = document.getElementById('recipe-steps-builder');

        function showToast(message, type = 'success') {
            const container = document.getElementById('toast-container');
            if (!container) return;
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerText = message;
            container.appendChild(toast);
            setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s';
            setTimeout(() => toast.remove(), 300);
            }, 3500);
        }

        function isQueuedResponse(result) {
            return Boolean(result && result.offlineQueued);
        }

        function showMutationResult(result, successMessage) {
            if (isQueuedResponse(result)) {
                showToast("Ação salva offline. Ela será sincronizada quando a conexão voltar.", "info");
                return false;
            }

            showToast(successMessage);
            return true;
        }

        function openModal(modal) {
            if (!modal) return;
            modal.classList.remove('hidden');
            modal.style.display = 'flex';
        }

        function closeModal(modal) {
            if (!modal) return;
            modal.classList.add('hidden');
            modal.style.display = 'none';
        }

        const NOTIFICATION_SETTINGS_KEY = "coffee_lab_notification_settings";
        const NOTIFICATION_DISMISSED_KEY = "coffee_lab_notifications_dismissed";
        const NOTIFICATION_SENT_KEY = "coffee_lab_notifications_sent";
        let latestNotifications = [];

        function getNotificationSettings() {
            const defaults = {
                coffeeTimeEnabled: true,
                coffeeTime: "09:00",
                stockEnabled: true,
                achievementsEnabled: true,
                recipesEnabled: true
            };
            try {
                return { ...defaults, ...JSON.parse(localStorage.getItem(NOTIFICATION_SETTINGS_KEY) || "{}") };
            } catch {
                return defaults;
            }
        }

        function saveNotificationSettings(settings) {
            localStorage.setItem(NOTIFICATION_SETTINGS_KEY, JSON.stringify(settings));
        }

        function getStoredIdList(key) {
            try {
                return JSON.parse(localStorage.getItem(key) || "[]");
            } catch {
                return [];
            }
        }

        function saveStoredIdList(key, values) {
            localStorage.setItem(key, JSON.stringify([...new Set(values)].slice(-250)));
        }

        function isNotificationAllowedBySettings(item, settings) {
            if (item.type === "coffee_time") return settings.coffeeTimeEnabled;
            if (item.type === "stock_low" || item.type === "stock_critical") return settings.stockEnabled;
            if (item.type === "achievement") return settings.achievementsEnabled;
            if (item.type === "new_recipe") return settings.recipesEnabled;
            return true;
        }

        function buildCoffeeTimeNotification(settings) {
            if (!settings.coffeeTimeEnabled) return null;
            const now = new Date();
            const todayKey = now.toISOString().slice(0, 10);
            const currentTime = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
            if (currentTime !== settings.coffeeTime) return null;
            return {
                id: `coffee-time-${todayKey}-${settings.coffeeTime}`,
                type: "coffee_time",
                title: "Hora do café",
                message: "Seu ritual diário está chamando. Escolha uma receita e prepare com calma.",
                severity: "info",
                created_at: now.toISOString(),
                action_url: "#/recipes"
            };
        }

        function updateNotificationSettingsUI() {
            const settings = getNotificationSettings();
            const permission = "Notification" in window ? Notification.permission : "unsupported";
            const permissionLabel = document.getElementById("notification-permission-label");
            const enableBtn = document.getElementById("enable-notifications-btn");
            const coffeeTimeEnabled = document.getElementById("notify-coffee-time-enabled");
            const coffeeTime = document.getElementById("notify-coffee-time");
            const stockEnabled = document.getElementById("notify-stock-enabled");
            const achievementsEnabled = document.getElementById("notify-achievements-enabled");
            const recipesEnabled = document.getElementById("notify-recipes-enabled");

            if (permissionLabel) {
                permissionLabel.innerText = permission === "granted"
                    ? "Notificações do navegador ativas"
                    : permission === "denied"
                        ? "Permissão bloqueada no navegador"
                        : "Clique para ativar alertas do navegador";
            }
            if (enableBtn) {
                enableBtn.innerText = permission === "granted" ? "Notificações ativas" : "Ativar notificações";
                enableBtn.disabled = permission === "granted" || permission === "unsupported";
            }
            if (coffeeTimeEnabled) coffeeTimeEnabled.checked = settings.coffeeTimeEnabled;
            if (coffeeTime) coffeeTime.value = settings.coffeeTime;
            if (stockEnabled) stockEnabled.checked = settings.stockEnabled;
            if (achievementsEnabled) achievementsEnabled.checked = settings.achievementsEnabled;
            if (recipesEnabled) recipesEnabled.checked = settings.recipesEnabled;
        }

        function renderNotifications() {
            const settings = getNotificationSettings();
            const dismissed = new Set(getStoredIdList(NOTIFICATION_DISMISSED_KEY));
            const visible = latestNotifications
                .filter(item => isNotificationAllowedBySettings(item, settings))
                .filter(item => !dismissed.has(item.id));
            const badge = document.getElementById("notification-badge");
            const list = document.getElementById("notifications-list");

            if (badge) {
                badge.innerText = String(Math.min(visible.length, 99));
                badge.classList.toggle("hidden", visible.length === 0);
            }
            if (!list) return;
            if (visible.length === 0) {
                list.innerHTML = '<div class="notification-empty">Nenhuma notificação por enquanto.</div>';
                return;
            }
            list.innerHTML = visible.map(item => `
                <a class="notification-item ${item.severity || 'info'}" href="${item.action_url || '#/dashboard'}" data-notification-id="${item.id}">
                    <strong>${item.title}</strong>
                    <p>${item.message}</p>
                </a>
            `).join("");
        }

        async function showNativeNotification(item) {
            if (!("Notification" in window) || Notification.permission !== "granted") return;
            const sent = getStoredIdList(NOTIFICATION_SENT_KEY);
            if (sent.includes(item.id)) return;

            const options = {
                body: item.message,
                icon: "/static/icons/icon-192.png",
                badge: "/static/icons/icon-192.png",
                data: { action_url: item.action_url || "#/dashboard" }
            };
            try {
                if ("serviceWorker" in navigator) {
                    const registration = await navigator.serviceWorker.ready;
                    await registration.showNotification(item.title, options);
                } else {
                    new Notification(item.title, options);
                }
                sent.push(item.id);
                saveStoredIdList(NOTIFICATION_SENT_KEY, sent);
            } catch (error) {
                console.warn("[Notifications] Falha ao exibir notificação nativa:", error);
            }
        }

        async function refreshNotifications({ notify = false } = {}) {
            if (!state.token) return;
            const settings = getNotificationSettings();
            const items = [];

            try {
                const remoteItems = await apiFetch("/api/notifications");
                if (Array.isArray(remoteItems)) items.push(...remoteItems);
            } catch (error) {
                console.warn("[Notifications] Não foi possível carregar alertas remotos:", error.message);
            }

            const coffeeTimeItem = buildCoffeeTimeNotification(settings);
            if (coffeeTimeItem) items.unshift(coffeeTimeItem);

            latestNotifications = items;
            renderNotifications();

            if (notify) {
                const dismissed = new Set(getStoredIdList(NOTIFICATION_DISMISSED_KEY));
                for (const item of items) {
                    if (!dismissed.has(item.id) && isNotificationAllowedBySettings(item, settings)) {
                        await showNativeNotification(item);
                    }
                }
            }
        }

        async function requestNotificationPermission() {
            if (!("Notification" in window)) {
                showToast("Este navegador não oferece suporte a notificações.", "error");
                return;
            }
            const permission = await Notification.requestPermission();
            updateNotificationSettingsUI();
            showToast(
                permission === "granted"
                    ? "Notificações ativadas."
                    : "Permissão de notificações não concedida.",
                permission === "granted" ? "success" : "error"
            );
            if (permission === "granted") refreshNotifications({ notify: true });
        }

        function initNotificationSystem() {
            updateNotificationSettingsUI();
            const panel = document.getElementById("notifications-panel");
            const toggle = document.getElementById("notifications-toggle");
            const markRead = document.getElementById("notifications-mark-read");
            const enableBtn = document.getElementById("enable-notifications-btn");

            toggle?.addEventListener("click", (event) => {
                event.stopPropagation();
                panel?.classList.toggle("hidden");
                toggle.setAttribute("aria-expanded", String(!panel?.classList.contains("hidden")));
                refreshNotifications();
            });
            document.addEventListener("click", (event) => {
                if (!panel || panel.classList.contains("hidden")) return;
                if (!event.target.closest(".notification-wrapper")) {
                    panel.classList.add("hidden");
                    toggle?.setAttribute("aria-expanded", "false");
                }
            });
            document.getElementById("notifications-list")?.addEventListener("click", (event) => {
                const item = event.target.closest("[data-notification-id]");
                if (!item) return;
                const dismissed = getStoredIdList(NOTIFICATION_DISMISSED_KEY);
                dismissed.push(item.dataset.notificationId);
                saveStoredIdList(NOTIFICATION_DISMISSED_KEY, dismissed);
                panel?.classList.add("hidden");
                renderNotifications();
            });
            markRead?.addEventListener("click", () => {
                const dismissed = getStoredIdList(NOTIFICATION_DISMISSED_KEY);
                latestNotifications.forEach(item => dismissed.push(item.id));
                saveStoredIdList(NOTIFICATION_DISMISSED_KEY, dismissed);
                renderNotifications();
            });
            enableBtn?.addEventListener("click", requestNotificationPermission);

            const bindSetting = (id, key) => {
                const el = document.getElementById(id);
                el?.addEventListener("change", () => {
                    const settings = getNotificationSettings();
                    settings[key] = el.type === "checkbox" ? el.checked : el.value;
                    saveNotificationSettings(settings);
                    updateNotificationSettingsUI();
                    refreshNotifications();
                });
            };
            bindSetting("notify-coffee-time-enabled", "coffeeTimeEnabled");
            bindSetting("notify-coffee-time", "coffeeTime");
            bindSetting("notify-stock-enabled", "stockEnabled");
            bindSetting("notify-achievements-enabled", "achievementsEnabled");
            bindSetting("notify-recipes-enabled", "recipesEnabled");

            refreshNotifications({ notify: true });
            setInterval(() => refreshNotifications({ notify: true }), 60000);
        }

    // ==========================================
    // FASE 14 — OFFLINE DATA CACHE
    // IndexedDB
    // ==========================================

    const OFFLINE_DB_NAME = "coffee_lab_offline";
    const OFFLINE_DB_VERSION = 1;
    const OFFLINE_STORE = "api_cache";

    let offlineDBPromise = null;
    let isSyncingOfflineQueue = false;

    function getTokenPayload() {
        const token = state.token || localStorage.getItem("coffee_lab_token") || localStorage.getItem("token");
        if (!token || !token.includes(".")) return null;

        try {
            const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
            return JSON.parse(atob(payload));
        } catch (error) {
            console.warn("[Offline] Nao foi possivel ler o payload do token:", error);
            return null;
        }
    }

    function getCurrentUserCacheKey() {
        const tokenPayload = getTokenPayload();
        const userKey =
            state.user?.id ||
            state.user?.email ||
            tokenPayload?.sub ||
            "anonymous";

        return String(userKey).toLowerCase();
    }

    function getOfflineCacheKey(endpoint) {
        return `${getCurrentUserCacheKey()}::${endpoint}`;
    }

    function shouldSkipOfflineQueue(endpoint, method, body) {
        const normalizedEndpoint = String(endpoint || "");

        if (method === "GET") return true;
        if (normalizedEndpoint.startsWith("/api/ai/")) return true;
        if (
            normalizedEndpoint.startsWith("/api/auth/") &&
            normalizedEndpoint !== "/api/auth/me"
        ) return true;
        if (body instanceof FormData) return true;

        return false;
    }

    async function getStockBaseUpdatedAt(endpoint) {
        const match = String(endpoint || "").match(/^\/api\/stock\/(\d+)/);
        if (!match) return null;

        const cachedStock = await getOfflineCache("/api/stock");
        if (!Array.isArray(cachedStock)) return null;

        const stockItem = cachedStock.find(item => String(item.id) === match[1]);
        return stockItem?.updated_at || null;
    }

    function openOfflineDB() {
        if (offlineDBPromise) {
            return offlineDBPromise;
        }

        offlineDBPromise = new Promise((resolve, reject) => {
            const request = indexedDB.open(
                OFFLINE_DB_NAME,
                OFFLINE_DB_VERSION
            );

            request.onerror = () => {
                console.error(
                    "[Offline] Erro ao abrir IndexedDB:",
                    request.error
                );

                reject(request.error);
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                if (!db.objectStoreNames.contains(OFFLINE_STORE)) {
                    db.createObjectStore(
                        OFFLINE_STORE,
                        {
                            keyPath: "key"
                        }
                    );
                }
            };

            request.onsuccess = () => {
                const db = request.result;

                db.onversionchange = () => {
                    db.close();
                };

                resolve(db);
            };
        });

        return offlineDBPromise;
    }

    async function saveOfflineCache(
        endpoint,
        data
    ) {
        try {
            const db =
                await openOfflineDB();

            return new Promise(
                (resolve, reject) => {

                    const transaction =
                        db.transaction(
                            OFFLINE_STORE,
                            "readwrite"
                        );

                    const store =
                        transaction.objectStore(
                            OFFLINE_STORE
                        );

                    const cacheKey = getOfflineCacheKey(endpoint);

                    store.put({
                        key: cacheKey,
                        endpoint,
                        owner: getCurrentUserCacheKey(),
                        data,
                        updatedAt:
                            new Date().toISOString()
                    });

                    transaction.oncomplete =
                        () => {
                            console.log(
                                "[Offline] Cache salvo:",
                                cacheKey
                            );

                            resolve();
                        };

                    transaction.onerror =
                        () => {
                            console.error(
                                "[Offline] Erro ao salvar cache:",
                                transaction.error
                            );

                            reject(
                                transaction.error
                            );
                        };
                }
            );

        } catch (error) {

            console.error(
                "[Offline] Falha ao salvar dados:",
                error
            );
        }
    }

    async function getOfflineCache(
        endpoint
    ) {
        try {
            const db =
                await openOfflineDB();

            return new Promise(
                (resolve, reject) => {

                    const transaction =
                        db.transaction(
                            OFFLINE_STORE,
                            "readonly"
                        );

                    const store =
                        transaction.objectStore(
                            OFFLINE_STORE
                        );

                    const cacheKey = getOfflineCacheKey(endpoint);
                    const request =
                        store.get(cacheKey);

                    request.onsuccess =
                        () => {

                            const result =
                                request.result;

                            if (!result) {
                                resolve(null);
                                return;
                            }

                            console.log(
                                "[Offline] Cache encontrado:",
                                cacheKey
                            );

                            resolve(
                                result.data
                            );
                        };

                    request.onerror =
                        () => {

                            reject(
                                request.error
                            );
                        };
                }
            );

        } catch (error) {

            console.error(
                "[Offline] Falha ao ler cache:",
                error
            );

            return null;
        }
    }

async function apiFetch(
    endpoint,
    options = {}
) {
    options.headers = options.headers || {};

    // 💡 AJUSTE AQUI: Busca no state OU no localStorage correto
    const token = state.token || localStorage.getItem('coffee_lab_token') || localStorage.getItem('token');

    if (token) {
        options.headers.Authorization = `Bearer ${token}`;
    }

    const method = (
        options.method || "GET"
    ).toUpperCase();

    const isGet = method === "GET";

    /*
    * Serialização automática de objetos.
    */
    if (
        !(options.body instanceof FormData) &&
        typeof options.body === "object" &&
        options.body !== null
    ) {
        options.headers["Content-Type"] = "application/json";

        options.body = JSON.stringify(options.body);
    }

    /*
    * ======================================
    * GET OFFLINE
    * ======================================
    *
    * Antes de tentar a rede, verificamos
    * se já sabemos que estamos offline.
    */
    if (
        isGet &&
        !navigator.onLine
    ) {
        const cachedData = await getOfflineCache(endpoint);

        if (
            cachedData !== null &&
            cachedData !== undefined
        ) {
            console.log(
                "[Offline] Usando cache:",
                endpoint
            );

            return cachedData;
        }

        console.warn(
            "[Offline] Nenhum cache disponível:",
            endpoint
        );

        throw new Error("OFFLINE_NO_CACHE");
    }

    try {

        const response = await fetch(
            endpoint,
            options
        );

        /*
        * A única situação que invalida
        * a sessão é um 401 real.
        */
        if (response.status === 401) {
            logout();

            throw new Error("Sessão expirada.");
        }

        if (!response.ok) {

            const errData = await response
                .json()
                .catch(() => ({}));

            throw new Error(
                errData.detail ||
                "Erro na requisição."
            );
        }

        /*
        * 204 não possui corpo.
        */
        if (response.status === 204) {
            return null;
        }

        const data = await response.json();

        /*
        * ==================================
        * SALVAR GETS NO CACHE
        * ==================================
        */
        if (isGet) {
            await saveOfflineCache(
                endpoint,
                data
            );
        }

        return data;

    } catch (error) {

        /*
        * Erro de sessão:
        * nunca tratar como offline.
        */
        if (
            error.message === "Sessão expirada."
        ) {
            throw error;
        }

        /*
        * Detectar falha de rede.
        */
        const isNetworkError =
            error.name === "TypeError" ||
            error.message.includes("Failed to fetch") ||
            !navigator.onLine;

        if (isNetworkError) {

            /*
            * ==================================
            * ESCRITAS OFFLINE
            * ==================================
            */
            if (
                [
                    "POST",
                    "PUT",
                    "PATCH",
                    "DELETE"
                ].includes(method)
            ) {
                if (shouldSkipOfflineQueue(endpoint, method, options.body)) {
                    throw new Error(
                        endpoint.startsWith("/api/ai/")
                            ? "Barista IA indisponivel offline."
                            : "Esta acao precisa de conexao com a internet."
                    );
                }

                let body = options.body;

                if (typeof body === "string") {
                    try {
                        body = JSON.parse(body);
                    } catch {
                        // Mantém string
                    }
                }

                const queuedAction = await addToOfflineQueue({
                    endpoint,
                    method,
                    body,
                    baseUpdatedAt: await getStockBaseUpdatedAt(endpoint)
                });

                showToast(
                    "Sem conexão. A ação foi salva e será sincronizada depois."
                );

                return {
                    offlineQueued: true,
                    queueId: queuedAction?.id || null
                };
            }

            /*
            * ==================================
            * GET OFFLINE
            * ==================================
            */
            if (isGet) {

                const cachedData = await getOfflineCache(endpoint);

                if (
                    cachedData !== null &&
                    cachedData !== undefined
                ) {

                    console.log(
                        "[Offline] Usando cache após falha de rede:",
                        endpoint
                    );

                    return cachedData;
                }

                throw new Error("OFFLINE_NO_CACHE");
            }
        }

        throw error;
    }
}

    function saveSession(token, user) {
        state.token = token;
        state.user = user;

        localStorage.setItem("coffee_lab_token", token);
        localStorage.setItem("coffee_lab_user", JSON.stringify(user));

        if (typeof updateUserDOM === "function") {
            updateUserDOM();
        }
        checkAuthUI();
    }

    function logout() {
        state.token = null;
        state.user = null;

        localStorage.removeItem("coffee_lab_token");
        localStorage.removeItem("coffee_lab_user");

        location.hash = "#/dashboard";
        checkAuthUI();
    }

    async function checkAuthUI() {
        const authScreen = document.getElementById("auth-screen");
        const appScreen = document.getElementById("app");

        if (!state.token) {
            appScreen?.classList.add("hidden");
            authScreen?.classList.remove("hidden");
            return;
        }

        authScreen?.classList.add("hidden");
        appScreen?.classList.remove("hidden");

        /* Atualiza a interface com dados em cache, se existirem */
        if (state.user && typeof updateUserDOM === "function") {
            updateUserDOM();
        }

        /* Comportamento Offline */
        if (!navigator.onLine) {
            console.log("[Auth] Offline. Usando sessão local.");
            return;
        }

        /* Comportamento Online: validar sessão atualizada */
        try {
            state.user = await apiFetch("/api/auth/me");
            localStorage.setItem("coffee_lab_user", JSON.stringify(state.user));

            if (typeof updateUserDOM === "function") {
                updateUserDOM();
            }
        } catch (error) {
            // Agora só fazemos logout se a culpa for EXATAMENTE do token
            if (error.message === "Sessão expirada.") {
                console.warn("[Auth] Sessão expirada. Redirecionando para login.");
                logout();
            } else {
                console.warn("[Auth] Servidor inacessível no momento, mantendo sessão local ativa.");
            }
        }
    }

        function updateUserDOM(user = state.user) {
            const avatarImgs = [
                document.getElementById('user-avatar-mini'),
                document.getElementById('profile-avatar-big')
            ].filter(Boolean);
            if (avatarImgs.length === 0) return;

            if (welcomeTitle && user?.name) {
                welcomeTitle.innerText = `Bem-vindo, ${user.name}!`;
            }
            if (profileNameDisplay && user?.name) {
                profileNameDisplay.innerText = user.name;
            }
            if (profileEmailDisplay && user?.email) {
                profileEmailDisplay.innerText = user.email;
            }
            const profileNameInput = document.getElementById('profile-name');
            const profileBioInput = document.getElementById('profile-bio');
            if (profileNameInput && user?.name) {
                profileNameInput.value = user.name;
            }
            if (profileBioInput && user?.bio !== undefined && user?.bio !== null) {
                profileBioInput.value = user.bio;
            }

            // SVG genérico embutido em base64 que funciona 100% offline
            const defaultAvatar = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 24 24' fill='none' stroke='%23a1a1aa' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2'/%3E%3Ccircle cx='12' cy='7' r='4'/%3E%3C/svg%3E";

            avatarImgs.forEach((avatarImg) => {
                avatarImg.onerror = () => {
                    avatarImg.src = defaultAvatar;
                };

                avatarImg.src = user?.avatar_url
                    ? user.avatar_url
                    : defaultAvatar;
            });
            }

        // --- FASE 3: GRÃOS ESPECIAIS ---
        async function fetchAndRenderCoffees() {
            if (!state.token || location.hash !== '#/coffees') return;
            try {
            let url =
    `/api/coffees?search=${encodeURIComponent(document.getElementById('coffee-search')?.
    value || '')}&process=${document.getElementById('filter-process')?.value ||
    ''}&roast_level=${document.getElementById('filter-roast')?.value ||
    ''}&sort_by=${document.getElementById('sort-coffees')?.value || 'name'}`;
            if (state.filterFav) url += '&favorites_only=true';
            state.coffees = await apiFetch(url);
            renderCoffeeGrid();
            } catch (err) {
        if (
            err.message ===
            "OFFLINE_NO_CACHE"
        ) {
            showToast(
                "Este conteúdo ainda não foi salvo para uso offline.",
                "error"
            );

            return;
        }

        showToast(
            err.message,
            "error"
        );
    }
        }

        function renderCoffeeGrid() {
            if (!coffeeGrid) return;
            if (state.coffees.length === 0) {
            coffeeGrid.innerHTML = '<div class="card" style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">Nenhum grão especial na prateleira.</div>';
            return;
            }
            coffeeGrid.innerHTML = state.coffees.map(c => `
            <div class="coffee-card">
                <button class="coffee-card-fav" onclick="window.coffeeActions.toggleFav(${c.id},
    ${c.is_favorite})">${c.is_favorite ? 'â­' : 'â˜†'}</button>
                <div class="coffee-card-img-wrapper"
    onclick="window.coffeeActions.triggerPhotoUpload(${c.id})">
                ${c.photo_url ? `<img src="${c.photo_url}">` : '<span class="placeholder-icon">☕</span>'}
                ${c.sca_score ? `<span class="coffee-card-sca">SCA ${c.sca_score}</span>` : ''}
                </div>
                <div class="coffee-card-content">
                <h3 class="coffee-card-title">${c.name}</h3>
                <div class="coffee-card-roastery">${c.roastery}</div>
                <div class="coffee-meta-grid">
                    <div><b>Origem:</b> ${c.origin}</div>
                    <div><b>Região:</b> ${c.region || 'N/A'}</div>
                    <div><b>Variedade:</b> ${c.variety || 'N/A'}</div>
                    <div><b>Torra:</b> ${c.roast_level || 'N/A'}</div>
                    <div><b>Processo:</b> ${c.process || 'N/A'}</div>
                    <div><b>Altitude:</b> ${c.altitude || 'N/A'}</div>
                </div>
                <div class="coffee-notes-tags">${c.sensory_notes ? c.sensory_notes : 'Sem notas sensoriais cadastradas.'}</div>
                <div class="coffee-card-actions">
                    <button class="btn btn-sm btn-secondary"
    onclick="window.coffeeActions.openEditModal(${c.id})">Editar</button>
                    <button class="btn-danger-text"
    onclick="window.coffeeActions.deleteCoffee(${c.id})">Excluir</button>
                </div>
                </div>
            </div>
            `).join('');
        }

        window.coffeeActions = {
            toggleFav: async (id, status) => {
            try {
                const result = await apiFetch(`/api/coffees/${id}`, { method: 'PUT', body: { is_favorite: !status } });
                if (!showMutationResult(result, 'Alteracao salva!')) return;
                fetchAndRenderCoffees();
            } catch (e) {
                showToast(e.message, 'error');
            }
            },
            deleteCoffee: async (id) => {
            if (confirm('Deletar este café permanentemente?')) {
                try {
                const result = await apiFetch(`/api/coffees/${id}`, { method: 'DELETE' });
                if (!showMutationResult(result, 'Removido')) return;
                fetchAndRenderCoffees();
                } catch (e) {
                showToast(e.message, 'error');
                }
            }
            },
            triggerPhotoUpload: (id) => {
            const i = document.createElement('input');
            i.type = 'file';
            i.accept = 'image/*';
            i.onchange = async (e) => {
                const f = e.target.files[0];
                if (!f) return;
                const fd = new FormData();
                fd.append('file', f);
                try {
                await apiFetch(`/api/coffees/${id}/photo`, { method: 'POST', body: fd });
                showToast('Foto salva!');
                fetchAndRenderCoffees();
                } catch (err) {
                showToast(err.message, 'error');
                }
            };
            i.click();
            },
            openEditModal: (id) => {
            const c = state.coffees.find(item => item.id === id);
            if (!c) return;
            document.getElementById('form-coffee-id').value = c.id;
            document.getElementById('coffee-name-input').value = c.name;
            document.getElementById('coffee-roastery-input').value = c.roastery;
            document.getElementById('coffee-origin-input').value = c.origin;
            document.getElementById('coffee-region-input').value = c.region || '';
            document.getElementById('coffee-variety-input').value = c.variety || '';
            document.getElementById('coffee-process-input').value = c.process || '';
            document.getElementById('coffee-altitude-input').value = c.altitude || '';
            document.getElementById('coffee-roast-input').value = c.roast_level || '';
            document.getElementById('coffee-roastdate-input').value = c.roast_date || '';
            document.getElementById('coffee-sensory-input').value = c.sensory_notes || '';
            document.getElementById('coffee-sca-input').value = c.sca_score || '';
            coffeeModal.classList.remove('hidden');
            }
        };

        document.getElementById('coffee-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const id = document.getElementById('form-coffee-id').value;
            const body = {
            name: document.getElementById('coffee-name-input').value,
            roastery: document.getElementById('coffee-roastery-input').value,
            origin: document.getElementById('coffee-origin-input').value,
            region: document.getElementById('coffee-region-input').value || null,
            variety: document.getElementById('coffee-variety-input').value || null,
            process: document.getElementById('coffee-process-input').value || null,
            altitude: document.getElementById('coffee-altitude-input').value || null,
            roast_level: document.getElementById('coffee-roast-input').value || null,
            roast_date: document.getElementById('coffee-roastdate-input').value || null,
            sensory_notes: document.getElementById('coffee-sensory-input').value || null,
            sca_score: document.getElementById('coffee-sca-input').value ?
    parseFloat(document.getElementById('coffee-sca-input').value) : null
            };

            try {
            if (id) {
                const result = await apiFetch(`/api/coffees/${id}`, { method: 'PUT', body });
                if (!showMutationResult(result, 'Café atualizado!')) { closeModal(coffeeModal); return; }
            } else {
                const result = await apiFetch('/api/coffees', { method: 'POST', body });
                if (!showMutationResult(result, 'Café adicionado!')) { closeModal(coffeeModal); return; }
            }
            closeModal(coffeeModal);
            fetchAndRenderCoffees();
            } catch (err) {
        if (
            err.message ===
            "OFFLINE_NO_CACHE"
        ) {
            showToast(
                "Este conteúdo ainda não foi salvo para uso offline.",
                "error"
            );

            return;
        }

        showToast(
            err.message,
            "error"
        );
    }
        });

        document.getElementById('btn-add-coffee')?.addEventListener('click', () => {
            document.getElementById('coffee-form').reset();
            document.getElementById('form-coffee-id').value = '';
            coffeeModal.classList.remove('hidden');
        });

        document.getElementById('modal-coffee-close')?.addEventListener('click', () =>
    coffeeModal.classList.add('hidden'));

        ['coffee-search', 'filter-process', 'filter-roast', 'sort-coffees'].forEach(id =>
            document.getElementById(id)?.addEventListener('input', fetchAndRenderCoffees)
        );

        document.getElementById('btn-filter-fav')?.addEventListener('click', function () {
            state.filterFav = !state.filterFav;
            this.classList.toggle('active', state.filterFav);
            fetchAndRenderCoffees();
        });

        // --- FASE 4: CONTROLE DE ESTOQUE ---
        async function fetchAndRenderStock() {
            if (!state.token || location.hash !== '#/stock') return;
            try {
            state.stockItems = await apiFetch('/api/stock');
            renderStockTable();
            } catch (err) {
        if (
            err.message ===
            "OFFLINE_NO_CACHE"
        ) {
            showToast(
                "Este conteúdo ainda não foi salvo para uso offline.",
                "error"
            );

            return;
        }

        showToast(
            err.message,
            "error"
        );
    }
        }

        function renderStockTable() {
            if (!stockTableBody) return;
            if (state.stockItems.length === 0) {
            stockTableBody.innerHTML = `<tr><td colspan="6" style="text-align:center;
    color:var(--text-secondary);">Cadastre um café primeiro para gerenciar seu
    estoque.</td></tr>`;
            return;
            }
            stockTableBody.innerHTML = state.stockItems.map(item => {
            const isLowStock = item.current_quantity <= item.min_quantity;
            const quantityBadge = isLowStock
                ? `<span class="badge badge-danger">${item.current_quantity}g (Baixo)</span>`
                : `<span class="badge badge-success">${item.current_quantity}g</span>`;
            const statusBadge = item.is_opened
                ? `<span class="badge badge-warning">Aberto</span>`
                : `<span class="badge badge-success">Lacrado</span>`;

            return `
                <tr>
                <td><b>${item.coffee.name}</b></td>
                <td>${item.coffee.roastery}</td>
                <td>${statusBadge}</td>
                <td>${quantityBadge}</td>
                <td>${item.min_quantity}g</td>
                <td style="text-align: right;">
                    <button class="btn btn-sm btn-secondary"
    onclick="window.stockActions.openRefill(${item.id})">+ Compra</button>
                    ${!item.is_opened ? `<button class="btn btn-sm btn-secondary"
    style="color:#eab308; border-color:#eab308;"
    onclick="window.stockActions.openPackage(${item.id})">Abrir</button>` : ''}
                    <button class="btn btn-sm btn-secondary"
    onclick="window.stockActions.openAdjust(${item.id}, ${item.current_quantity},
    ${item.min_quantity})">Ajustar</button>
                    <button class="btn btn-sm btn-secondary"
    onclick="window.stockActions.viewHistory(${item.id})">Histórico</button>
                </td>
                </tr>
            `;
            }).join('');
        }

        window.stockActions = {
            openRefill: (id) => {
            document.getElementById('stock-refill-form').reset();
            document.getElementById('refill-stock-id').value = id;
            document.getElementById('stock-refill-modal').classList.remove('hidden');
            },
            openAdjust: (id, curr, min) => {
            document.getElementById('adjust-stock-id').value = id;
            document.getElementById('adjust-qty-input').value = curr;
            document.getElementById('adjust-min-input').value = min;
            document.getElementById('stock-adjust-modal').classList.remove('hidden');
            },
            openPackage: async (id) => {
            if (!confirm("Confirmar abertura do pacote?")) return;
            try {
                await apiFetch(`/api/stock/${id}`, { method: 'PUT', body: { is_opened: true } });
                showToast("Pacote aberto para consumo.");
                fetchAndRenderStock();
            } catch (err) {
                showToast(err.message, 'error');
            }
            },
            viewHistory: async (id) => {
            try {
                const history = await apiFetch(`/api/stock/${id}/movements`);
                const listContainer = document.getElementById('stock-history-list');
                if (!listContainer) return;

                if (history.length === 0) {
                listContainer.innerHTML = '<li style="color:var(--text-secondary); text-align:center; padding: 10px;">Nenhuma movimentação registrada.</li>';
                } else {
                listContainer.innerHTML = history.map(h => {
                    let qtyClass = h.quantity_changed > 0 ? 'qty-positive' : (h.quantity_changed < 0 ?
    'qty-negative' : 'qty-neutral');
                    let prefix = h.quantity_changed > 0 ? '+' : '';
                    return `
                    <li class="history-log-item">
                        <div class="history-log-meta">
                        <b>${h.action_type.toUpperCase()}</b>
                        <span>${h.notes || ''}</span>
                        <span class="history-log-date">${new
    Date(h.created_at).toLocaleString('pt-BR')}</span>
                        </div>
                        <div class="qty-change-tag ${qtyClass}">${prefix}${h.quantity_changed}g</div>
                    </li>
                    `;
                }).join('');
                }
                document.getElementById('stock-history-modal').classList.remove('hidden');
            } catch (err) {
                showToast(err.message, 'error');
            }
            }
        };

        document.getElementById('stock-refill-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const id = document.getElementById('refill-stock-id').value;
            const qty = document.getElementById('refill-qty-input').value;
            const notes = document.getElementById('refill-notes-input').value;
            try {
            await
    apiFetch(`/api/stock/${id}/refill?quantity_added=${qty}&notes=${encodeURIComponent(notes)}`, { method: 'POST' });
            showToast('Estoque reabastecido!');
            document.getElementById('stock-refill-modal').classList.add('hidden');
            fetchAndRenderStock();
            } catch (err) {
        if (
            err.message ===
            "OFFLINE_NO_CACHE"
        ) {
            showToast(
                "Este conteúdo ainda não foi salvo para uso offline.",
                "error"
            );

            return;
        }

        showToast(
            err.message,
            "error"
        );
    }
        });

        document.getElementById('stock-adjust-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const id = document.getElementById('adjust-stock-id').value;
            const qty = document.getElementById('adjust-qty-input').value;
            const min = document.getElementById('adjust-min-input').value;
            try {
            await apiFetch(`/api/stock/${id}`, { method: 'PUT', body: { current_quantity:
    parseFloat(qty), min_quantity: parseFloat(min) } });
            showToast('Níveis atualizados!');
            document.getElementById('stock-adjust-modal').classList.add('hidden');
            fetchAndRenderStock();
            } catch (err) {
        if (
            err.message ===
            "OFFLINE_NO_CACHE"
        ) {
            showToast(
                "Este conteúdo ainda não foi salvo para uso offline.",
                "error"
            );

            return;
        }

        showToast(
            err.message,
            "error"
        );
    }
        });

        document.getElementById('modal-refill-close')?.addEventListener('click', () =>
    document.getElementById('stock-refill-modal').classList.add('hidden'));
        document.getElementById('modal-adjust-close')?.addEventListener('click', () =>
    document.getElementById('stock-adjust-modal').classList.add('hidden'));
        document.getElementById('modal-history-close')?.addEventListener('click', () =>
    document.getElementById('stock-history-modal').classList.add('hidden'));

        // --- FASE 5: LIVRO DE RECEITAS ---

            // ==========================================
        // RECEITAS - PREENCHIMENTO DE CAFÉS
        // ==========================================
        async function populateRecipeCoffeeDropdown() {
        const select = document.getElementById('recipe-coffee-select');
        if (!select) return;

        select.required = false;

        try {
            const response = await apiFetch('/api/coffees?search=&process=&roast_level=&sort_by=name');

            let coffeesList = Array.isArray(response)
            ? response
            : (response?.coffees || response?.data || []);

            select.innerHTML = '<option value="" disabled selected>Selecione um café...</option>';

            if (coffeesList.length === 0) {
            select.innerHTML = '<option value="" disabled selected>Nenhum café no estoque</option>';
            return;
            }

            coffeesList.forEach(coffee => {
            const option = document.createElement('option');
            option.value = coffee.id;
            option.textContent = `${coffee.name}${coffee.roaster ? ` (${coffee.roaster})` : ''}`;
            select.appendChild(option);
            });

        } catch (err) {
            console.error("Erro ao carregar cafés para a receita:", err);
        }
        }
        async function fetchAndRenderRecipes() {
            if (!state.token || location.hash !== '#/recipes') return;
            const search = document.getElementById('recipe-search')?.value || '';
            const method = document.getElementById('filter-recipe-method')?.value || '';
            try {
            let url = `/api/recipes?search=${encodeURIComponent(search)}&method=${method}`;
            if (state.recipeFilterFav) url += '&favorites_only=true';
            state.recipes = await apiFetch(url);
            renderRecipeGrid();
            } catch (err) {
        if (
            err.message ===
            "OFFLINE_NO_CACHE"
        ) {
            showToast(
                "Este conteúdo ainda não foi salvo para uso offline.",
                "error"
            );

            return;
        }

        showToast(
            err.message,
            "error"
        );
    }
        }

        function renderRecipeGrid() {
            if (!recipeGrid) return;
            if (state.recipes.length === 0) {
            recipeGrid.innerHTML = `<div class="card" style="grid-column:1/-1; text-align:center;
    color:var(--text-secondary);">Nenhuma receita cadastrada.</div>`;
            return;
            }
            recipeGrid.innerHTML = state.recipes.map(r => {
            const ratio = (r.water_weight / r.coffee_weight).toFixed(1);
            const stepsList = r.steps && r.steps.length > 0 ? `<ol
    class="recipe-preview-steps">${r.steps.map(s => `<li>${s}</li>`).join('')}</ol>` : '';
            const coffeeBind = r.coffee ? `
    ðŸŒ
    <b>Grão:</b> ${r.coffee.name}` : '✨ <b>Grão:</b> Qualquer grão livre';
            return `
                <div class="coffee-card">
                <button class="coffee-card-fav" onclick="window.recipeActions.toggleFav(${r.id},
    ${r.is_favorite})">${r.is_favorite ? 'â­' : 'â˜†'}</button>
                <div class="coffee-card-content" style="padding-top:28px;">
                    <div class="recipe-method-badge">${r.method}</div>
                    <h3 class="coffee-card-title">${r.name}</h3>
                    <div style="font-size:13px; color:var(--text-secondary); margin: 6px 0 12px;">
                    ${coffeeBind}
                    </div>
                    <div class="coffee-meta-grid">
                    <div>
    ⚖
    <b>Café:</b> ${r.coffee_weight}g</div>
                    <div>
    💧
    <b>Água:</b> ${r.water_weight}g <span
    class="recipe-ratio-tag">1:${ratio}</span></div>
                    <div>
    🪵
    <b>Moagem:</b> ${r.grind_size || 'N/A'}</div>
                    <div>
    🌡
    <b>Temp:</b> ${r.water_temp ? `${r.water_temp}°C` : 'N/A'}</div>
                    </div>
                    ${r.description ? `<p style="font-size:12px; margin: 8px 0; line-height:1.4;">
    ðŸ“

    ${r.description}</p>` : ''}
                    ${stepsList}
                    <div class="coffee-card-actions">
                    <button class="btn btn-sm" style="background:#22c55e;"
    onclick="window.recipeActions.startExtraction(${r.id})">
    ☕
    Preparar</button>
                    <button class="btn btn-sm btn-secondary"
    onclick="window.recipeActions.openEdit(${r.id})">Editar</button>
                    <button class="btn btn-sm btn-secondary" style="color:var(--accent);"
    onclick="window.recipeActions.duplicate(${r.id})">Duplicar</button>
                    <button class="btn-danger-text"
    onclick="window.recipeActions.deleteRecipe(${r.id})">Excluir</button>
                    </div>
                </div>
                </div>
            `;
            }).join('');
        }

        function addStepRow(val = "") {
            if (!recipeStepsBuilder) return;
            const div = document.createElement('div');
            div.className = 'recipe-step-entry';
            div.innerHTML = `
            <input type="text" class="recipe-step-input-field" required placeholder="Ex: Despejar
    50g de água..." value="${val}">
            <button type="button" class="btn-remove-step"
    onclick="this.parentElement.remove()">×</button>
            `;
            recipeStepsBuilder.appendChild(div);
        }

        window.recipeActions = {
            ...(window.recipeActions || {}),
            toggleFav: async (id, status) => {
            try {
                const result = await apiFetch(`/api/recipes/${id}`, { method: 'PUT', body: { is_favorite: !status } });
                if (!showMutationResult(result, 'Alteracao salva!')) return;
                fetchAndRenderRecipes();
            } catch (e) {
                showToast(e.message, 'error');
            }
            },
            deleteRecipe: async (id) => {
            if (!confirm('Deseja excluir permanentemente esta receita?')) return;
            try {
                const result = await apiFetch(`/api/recipes/${id}`, { method: 'DELETE' });
                if (!showMutationResult(result, 'Receita removida.')) return;
                fetchAndRenderRecipes();
            } catch (e) {
                showToast(e.message, 'error');
            }
            },
            duplicate: async (id) => {
            try {
                const result = await apiFetch(`/api/recipes/${id}/duplicate`, { method: 'POST' });
                if (!showMutationResult(result, 'Receita clonada!')) return;
                fetchAndRenderRecipes();
            } catch (e) {
                showToast(e.message, 'error');
            }
            },
            openEdit: async (id) => {
            const r = state.recipes.find(item => item.id === id);
            if (!r) return;
            document.getElementById('modal-recipe-title').innerText = "Editar Perfil de Receita";
            document.getElementById('form-recipe-id').value = r.id;
            document.getElementById('recipe-name-input').value = r.name;
            document.getElementById('recipe-method-input').value = r.method;
            document.getElementById('recipe-grind-input').value = r.grind_size || '';
            document.getElementById('recipe-coffee-weight').value = r.coffee_weight;
            document.getElementById('recipe-water-weight').value = r.water_weight;
            document.getElementById('recipe-temp-input').value = r.water_temp || '';
            document.getElementById('recipe-desc-input').value = r.description || '';
            if (recipeStepsBuilder) recipeStepsBuilder.innerHTML = '';
            if (r.steps && Array.isArray(r.steps)) {
                r.steps.forEach(s => addStepRow(s));
            }
            const select = document.getElementById('recipe-coffee-select');
            try {
                state.coffees = await apiFetch('/api/coffees');
                if (select) {
                select.innerHTML = '<option value="">Receita Livre (Qualquer grão)</option>' +
                    state.coffees.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
                select.value = r.coffee_id || '';
                }
            } catch (e) {}
            recipeModal.classList.remove('hidden');
            }
        };

        document.getElementById('btn-add-recipe')?.addEventListener('click', async () => {
            populateRecipeCoffeeDropdown();
            document.getElementById('recipe-form').reset();
            document.getElementById('form-recipe-id').value = '';
            document.getElementById('modal-recipe-title').innerText = "Criar Nova Receita";
            if (recipeStepsBuilder) recipeStepsBuilder.innerHTML = '';
            const select = document.getElementById('recipe-coffee-select');
            try {
            state.coffees = await apiFetch('/api/coffees');
            if (select) {
                select.innerHTML = '<option value="">Receita Livre (Qualquer grão)</option>' +
                state.coffees.map(c => `<option value="${c.id}">${c.name}
    (${c.roastery})</option>`).join('');
            }
            } catch (e) {}
            addStepRow("Pré-infusão inicial com 50g de água por 30 segundos.");
            recipeModal.classList.remove('hidden');
        });

        document.getElementById('btn-add-step-row')?.addEventListener('click', () =>
    addStepRow());
        document.getElementById('modal-recipe-close')?.addEventListener('click', () =>
    recipeModal.classList.add('hidden'));
        document.getElementById('modal-recipe-cancel')?.addEventListener('click', () =>
    recipeModal.classList.add('hidden'));

        document.getElementById('recipe-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const id = document.getElementById('form-recipe-id').value;
            const stepInputs = document.querySelectorAll('.recipe-step-input-field');
            const stepsArray = Array.from(stepInputs).map(i => i.value.trim()).filter(v => v !== "");
            const body = {
            name: document.getElementById('recipe-name-input').value,
            method: document.getElementById('recipe-method-input').value,
            coffee_id: document.getElementById('recipe-coffee-select').value ?
    parseInt(document.getElementById('recipe-coffee-select').value) : null,
            grind_size: document.getElementById('recipe-grind-input').value || null,
            coffee_weight: parseFloat(document.getElementById('recipe-coffee-weight').value),
            water_weight: parseFloat(document.getElementById('recipe-water-weight').value),
            water_temp: document.getElementById('recipe-temp-input').value ?
    parseInt(document.getElementById('recipe-temp-input').value) : null,
            description: document.getElementById('recipe-desc-input').value || null,
            steps: stepsArray
            };

            try {
            if (id) {
                const result = await apiFetch(`/api/recipes/${id}`, { method: 'PUT', body });
                if (!showMutationResult(result, 'Receita atualizada!')) { closeModal(recipeModal); return; }
            } else {
                const result = await apiFetch('/api/recipes', { method: 'POST', body });
                if (!showMutationResult(result, 'Receita salva!')) { closeModal(recipeModal); return; }
            }
            closeModal(recipeModal);
            fetchAndRenderRecipes();
            } catch (err) {
        if (
            err.message ===
            "OFFLINE_NO_CACHE"
        ) {
            showToast(
                "Este conteúdo ainda não foi salvo para uso offline.",
                "error"
            );

            return;
        }

        showToast(
            err.message,
            "error"
        );
    }
        });

        ['recipe-search', 'filter-recipe-method'].forEach(id =>
            document.getElementById(id)?.addEventListener('input', fetchAndRenderRecipes)
        );

        document.getElementById('btn-filter-recipe-fav')?.addEventListener('click', function () {
            state.recipeFilterFav = !state.recipeFilterFav;
            this.classList.toggle('active', state.recipeFilterFav);
            fetchAndRenderRecipes();
        });

        // --- FLUXOS COMUNS (SESSÃO E LOGIN) ---
        function showAuthForm(target) {
            const forms = {
                login: document.getElementById('login-form'),
                register: document.getElementById('register-form'),
                recover: document.getElementById('recover-form')
            };
            Object.entries(forms).forEach(([name, form]) => {
                form?.classList.toggle('hidden', name !== target);
            });
            const subtitle = document.getElementById('auth-subtitle');
            if (subtitle) {
                subtitle.innerText = {
                    login: 'Entre na sua conta para acessar seus cafés e receitas',
                    register: 'Crie sua conta para começar seu laboratório de cafés',
                    recover: 'Informe seu e-mail para receber instruções de recuperação'
                }[target];
            }
        }

        document.getElementById('go-to-register')?.addEventListener('click', (e) => {
            e.preventDefault();
            showAuthForm('register');
        });

        document.getElementById('go-to-login')?.addEventListener('click', (e) => {
            e.preventDefault();
            showAuthForm('login');
        });

        document.getElementById('back-to-login')?.addEventListener('click', (e) => {
            e.preventDefault();
            showAuthForm('login');
        });

        document.getElementById('go-to-recover')?.addEventListener('click', (e) => {
            e.preventDefault();
            showAuthForm('recover');
        });

        document.getElementById('login-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            try {
            const r = await apiFetch('/api/auth/login', {
                method: 'POST',
                body: {
                email: document.getElementById('login-email').value,
                password: document.getElementById('login-password').value
                }
            });
            saveSession(r.access_token, r.user);
            } catch (err) {
            showToast(err.message, 'error');
            }
        });

        document.getElementById('register-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = document.getElementById('reg-name').value.trim();
            const email = document.getElementById('reg-email').value.trim();
            const password = document.getElementById('reg-password').value;

            if (!name || !email || password.length < 6) {
                showToast('Preencha nome, e-mail e uma senha com pelo menos 6 caracteres.', 'error');
                return;
            }

            try {
                await apiFetch('/api/auth/register', {
                    method: 'POST',
                    body: { name, email, password }
                });
                showToast('Conta criada! Agora faça login.');
                showAuthForm('login');
                document.getElementById('login-email').value = email;
            } catch (err) {
                showToast(err.message, 'error');
            }
        });

        document.getElementById('recover-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('rec-email').value.trim();
            if (!email) {
                showToast('Informe o e-mail cadastrado.', 'error');
                return;
            }

            try {
                const result = await apiFetch('/api/auth/recover', {
                    method: 'POST',
                    body: { email }
                });
                showToast(result.detail || 'Se o e-mail existir, as instruções serão enviadas.');
                showAuthForm('login');
            } catch (err) {
                showToast(err.message, 'error');
            }
        });

        document.getElementById('profile-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            try {
                const result = await apiFetch('/api/auth/me', {
                    method: 'PUT',
                    body: {
                        name: document.getElementById('profile-name').value.trim(),
                        bio: document.getElementById('profile-bio').value
                    }
                });
                if (isQueuedResponse(result)) {
                    showToast('Perfil salvo offline. Será sincronizado quando a conexão voltar.', 'info');
                    return;
                }
                state.user = result;
                localStorage.setItem("coffee_lab_user", JSON.stringify(state.user));
                updateUserDOM();
                showToast('Perfil atualizado!');
            } catch (err) {
                showToast(err.message, 'error');
            }
        });

        document.getElementById('avatar-input')?.addEventListener('change', async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            const body = new FormData();
            body.append('file', file);

            try {
                const result = await apiFetch('/api/auth/me/avatar', {
                    method: 'POST',
                    body
                });
                state.user = {
                    ...state.user,
                    avatar_url: result.avatar_url
                };
                localStorage.setItem("coffee_lab_user", JSON.stringify(state.user));
                updateUserDOM();
                showToast('Foto de perfil atualizada!');
            } catch (err) {
                showToast(err.message, 'error');
            } finally {
                e.target.value = '';
            }
        });

        document.getElementById('logout-btn')?.addEventListener('click', () => logout());

        // --- FASE 8: HISTÓRICO DE EXTRAÇÕES ---
        async function fetchAndRenderExtractions() {
            const currentView = location.hash.replace('#', '').replace('/', '') || 'dashboard';
            if (!state.token || currentView !== 'extractions') return;
            try {
            state.extractions = await apiFetch('/api/extractions');
            renderExtractionsTimeline();
            } catch (err) {
        if (
            err.message ===
            "OFFLINE_NO_CACHE"
        ) {
            showToast(
                "Este conteúdo ainda não foi salvo para uso offline.",
                "error"
            );

            return;
        }

        showToast(
            err.message,
            "error"
        );
    }
        }

        function renderExtractionsTimeline() {
            const container = document.getElementById('extractions-timeline');
            if (!container) return;
            if (!state.extractions || !Array.isArray(state.extractions) || state.extractions.length === 0)
    {
            container.innerHTML = `
                <div class="card" style="text-align:center; color:var(--text-secondary); padding: 40px
    20px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px;">
                <span style="font-size: 32px; display:block; margin-bottom: 12px;">
    ☕
    </span>
                Nenhuma extração registrada ainda. Prepare uma receita no Modo Guiado para
    iniciar seu histórico!
                </div>`;
            return;
            }
            container.innerHTML = state.extractions.map(ext => {
            const mins = String(Math.floor((ext.total_time || 0) / 60)).padStart(2, '0');
            const secs = String((ext.total_time || 0) % 60).padStart(2, '0');
            const date = ext.extraction_date
                ? new Date(ext.extraction_date).toLocaleDateString('pt-BR', { day: '2-digit', month:
    '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
                : 'Data desconhecida';
            const coffeeName = ext.coffee ? ext.coffee.name : (ext.coffee_name || 'Grão Livre / Qualquer Grão');
            const recipeName = ext.recipe ? ext.recipe.name : (ext.recipe_name || 'Preparo Manual');

            return `
                <div class="card timeline-item" style="margin-bottom: 16px; display: flex;
    flex-direction: column; gap: 8px; background: var(--surface); padding: 16px; border: 1px solid
    var(--border); border-radius: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;
    border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 4px;">
                    <div>
                    <span style="font-size: 12px; color: var(--text-secondary); font-weight: 500;">📅${date}</span>
                    <h3 style="margin: 4px 0 0 0; font-size: 16px; color:
    var(--text-primary);">${recipeName}</h3>
                    </div>
                    <span class="recipe-ratio-tag" style="background: var(--surface-raised);
    font-family: monospace; font-size: 14px; padding: 4px 8px; border-radius: 4px; border: 1px
    solid var(--border);">${mins}:${secs}</span>
                </div>
                <div style="font-size: 13px; color: var(--text-secondary);">
                    <b>Grão utilizado:</b> <span style="color:
    var(--text-primary);">${coffeeName}</span>
                </div>
                ${ext.notes ? `<div style="font-size: 13px; background: rgba(0,0,0,0.2); padding: 8px;
    border-radius: 6px; font-style: italic; margin-top: 4px; border-left: 3px solid var(--accent);
    color: var(--text-secondary);">
    ðŸ“
    ${ext.notes}</div>` : ''}
                </div>
            `;
            }).join('');
        }

        // --- ROTEADOR SPA ---
        const views = document.querySelectorAll('.view');
        const navLinks = document.querySelectorAll('.nav-link');

        function route() {
            const hash = location.hash.replace('#', '') || '/dashboard';
            const name = hash.replace('/', '') || 'dashboard';
            navLinks.forEach(n => n.classList.toggle('active', n.dataset.view === name));
            views.forEach(v => v.classList.remove('active'));
            const activeView = document.getElementById('view-' + name);
            if (activeView) activeView.classList.add('active');

            if (name === 'coffees') fetchAndRenderCoffees();
            if (name === 'stock') fetchAndRenderStock();
            if (name === 'extractions') fetchAndRenderExtractions();
            if (name === 'recipes') fetchAndRenderRecipes();
            if (name === 'sensory') fetchAndRenderSensoryLogs();
            if (name === 'explorer') fetchAndRenderSensoryExplorer();
            if (name === 'beverages') fetchAndRenderBeverages();
            if (name === 'ai') loadAiSessions(true);
            if (name === 'stats') fetchAndRenderStats();

            setTimeout(() => {
            const motorCoffee = document.getElementById('motor-coffee');
            const motorRatio = document.getElementById('motor-ratio');
            const motorWater = document.getElementById('motor-water');
            const motorFeedback = document.getElementById('motor-feedback');

            if (motorCoffee && motorRatio && motorWater) {
                const newCoffee = motorCoffee.cloneNode(true);
                const newRatio = motorRatio.cloneNode(true);
                const newWater = motorWater.cloneNode(true);

                motorCoffee.parentNode.replaceChild(newCoffee, motorCoffee);
                motorRatio.parentNode.replaceChild(newRatio, motorRatio);
                motorWater.parentNode.replaceChild(newWater, motorWater);

                function calculate(trigger) {
                let c = parseFloat(newCoffee.value) || 0;
                let r = parseFloat(newRatio.value) || 0;
                let w = parseFloat(newWater.value) || 0;

                if (trigger === 'coffee' || trigger === 'ratio') {
                    if (c > 0 && r > 0) {
                    w = c * r;
                    newWater.value = Math.round(w);
                    }
                } else if (trigger === 'water') {
                    if (w > 0 && r > 0) {
                    c = w / r;
                    newCoffee.value = c.toFixed(1);
                    } else if (w > 0 && c > 0) {
                    r = w / c;
                    newRatio.value = r.toFixed(1);
                    }
                }

                if (motorFeedback) {
                    if (w > 500) {
                    motorFeedback.innerText = `
    ⚠
    Volume alto (1:${r.toFixed(1)}). Recomendamos
    engrossar a granulometria para evitar super-extração.`;
                    } else if (w < 150 && w > 0) {
                    motorFeedback.innerText = `
    💡
    Volume baixo (1:${r.toFixed(1)}). Sugere-se
    moagem levemente mais fina para reter o fluxo.`;
                    } else if (w > 0) {
                    motorFeedback.innerText = `
    ✅
    Proporção equilibrada 1:${r.toFixed(1)} calculada
    com sucesso.`;
                    }
                }
                }

                newCoffee.addEventListener('input', () => calculate('coffee'));
                newRatio.addEventListener('input', () => calculate('ratio'));
                newWater.addEventListener('input', () => calculate('water'));
            }
            }, 50);
        }

        // --- FASE 7: EXECUÇÃO DA RECEITA ---
        let timerInterval = null;
        let secondsElapsed = 0;
        let currentStepIndex = 0;
        let activeRecipeForExtraction = null;
        let isTimerRunning = false;

        window.recipeActions = window.recipeActions || {};
        window.recipeActions.startExtraction = (id) => {
            const r = state.recipes.find(item => item.id === id);
            if (!r) return;
            activeRecipeForExtraction = r;
            secondsElapsed = 0;
            currentStepIndex = 0;
            isTimerRunning = false;
            document.getElementById('guided-recipe-title').innerText = r.name;
            document.getElementById('guided-method-badge').innerText = r.method;
            document.getElementById('guided-timer').innerText = "00:00";
            updateGuidedStepsDisplay();
            document.getElementById('guided-mode-modal').classList.remove('hidden');
        };

        function updateGuidedStepsDisplay() {
            const r = activeRecipeForExtraction;
            if (!r) return;
            const steps = r.steps || [];
            if (currentStepIndex < steps.length) {
            document.getElementById('guided-step-indicator').innerText = steps[currentStepIndex];
            if (currentStepIndex + 1 < steps.length) {
                document.getElementById('guided-next-step-text').innerText =
    steps[currentStepIndex + 1];
            } else {
                document.getElementById('guided-next-step-text').innerText = "Finalizar Extração";
            }
            } else {
            document.getElementById('guided-step-indicator').innerText = "Extração concluída! Despejos finalizados.";
            document.getElementById('guided-next-step-text').innerText = "-";
            }
        }

        function toggleGuidedTimer() {
            const btn = document.getElementById('btn-guided-playpause');
            if (isTimerRunning) {
            clearInterval(timerInterval);
            isTimerRunning = false;
            if (btn) btn.innerText = "Iniciar";
            } else {
            isTimerRunning = true;
            if (btn) btn.innerText = "Pausar";
            timerInterval = setInterval(() => {
                secondsElapsed++;
                const mins = String(Math.floor(secondsElapsed / 60)).padStart(2, '0');
                const secs = String(secondsElapsed % 60).padStart(2, '0');
                document.getElementById('guided-timer').innerText = `${mins}:${secs}`;
            }, 1000);
            }
        }

        document.getElementById('btn-guided-playpause')?.addEventListener('click',
    toggleGuidedTimer);

        document.getElementById('btn-guided-next')?.addEventListener('click', () => {
            if (!activeRecipeForExtraction) return;
            const steps = activeRecipeForExtraction.steps || [];
            if (currentStepIndex < steps.length - 1) {
            currentStepIndex++;
            updateGuidedStepsDisplay();
            } else {
            finalizeExtractionProcess();
            }
        });

        document.getElementById('btn-guided-reset')?.addEventListener('click', () => {
            clearInterval(timerInterval);
            secondsElapsed = 0;
            currentStepIndex = 0;
            isTimerRunning = false;
            document.getElementById('guided-timer').innerText = "00:00";
            const btn = document.getElementById('btn-guided-playpause');
            if (btn) btn.innerText = "Iniciar";
            updateGuidedStepsDisplay();
        });

        async function finalizeExtractionProcess() {
            clearInterval(timerInterval);
            isTimerRunning = false;
            const btn = document.getElementById('btn-guided-playpause');
            if (btn) btn.innerText = "Iniciar";
            if (!confirm("Deseja finalizar o preparo e registrar essa extração para controle de estoque?")) return;
            try {
            await apiFetch('/api/extractions', {
                method: 'POST',
                body: {
                recipe_id: activeRecipeForExtraction.id,
                coffee_id: activeRecipeForExtraction.coffee_id,
                total_time: secondsElapsed,
                notes: `Preparo guiado via método ${activeRecipeForExtraction.method}`
                }
            });
            showToast("Extração registrada! Estoque atualizado automaticamente.");
            document.getElementById('guided-mode-modal').classList.add('hidden');
            if (typeof fetchAndRenderStock === "function") fetchAndRenderStock();
            } catch (err) {
        if (
            err.message ===
            "OFFLINE_NO_CACHE"
        ) {
            showToast(
                "Este conteúdo ainda não foi salvo para uso offline.",
                "error"
            );

            return;
        }

        showToast(
            err.message,
            "error"
        );
    }
        }

        document.getElementById('btn-close-guided')?.addEventListener('click', () => {
            clearInterval(timerInterval);
            isTimerRunning = false;
            document.getElementById('guided-mode-modal').classList.add('hidden');
        });

// --- FASE 9: DIÁRIO SENSORIAL ---
async function fetchAndRenderSensoryLogs() {
    const currentView = location.hash.replace('#', '').replace('/', '') || 'dashboard';
    if (!state.token || currentView !== 'sensory') return;
    try {
        state.sensoryLogs = await apiFetch('/api/sensory-logs');
        renderSensoryLogsList();
    } catch (err) {
        if (err.message === "OFFLINE_NO_CACHE") {
            showToast("Este conteúdo ainda não foi salvo para uso offline.", "error");
            return;
        }
        showToast(err.message || "Erro ao buscar registros sensoriais", "error");
    }
}

function renderSensoryLogsList() {
    const container = document.getElementById('sensory-logs-list');
    if (!container) return;

    if (!state.sensoryLogs || !Array.isArray(state.sensoryLogs) || state.sensoryLogs.length === 0) {
        container.innerHTML = `
            <div class="card" style="text-align:center; color:var(--text-secondary); padding: 40px 20px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px;">
                <span style="font-size: 32px; display:block; margin-bottom: 12px;">ðŸ“</span>
                Nenhum registro sensorial cadastrado ainda. Clique em "+ Nova Degustação" para avaliar seu primeiro café!
            </div>`;
        return;
    }

    container.innerHTML = state.sensoryLogs.map(log => {
        const coffeeName = log.coffee ? log.coffee.name : (log.coffee_name || 'Café não identificado');
        const roastery = log.coffee && log.coffee.roastery ? ` (${log.coffee.roastery})` : '';
        const date = log.created_at
            ? new Date(log.created_at).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' })
            : 'Data não registrada';

        const scores = [log.aroma_score, log.acidity_score, log.body_score, log.sweetness_score, log.aftertaste_score].filter(n => typeof n === 'number');
        const avgScore = scores.length > 0 ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1) : '-';

        return `
            <div class="card" style="margin-bottom: 16px; background: var(--surface); padding: 18px; border: 1px solid var(--border); border-radius: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid var(--border); padding-bottom: 10px; margin-bottom: 12px;">
                    <div>
                        <span style="font-size: 12px; color: var(--text-secondary); font-weight: 500;">📅 ${date}</span>
                        <h3 style="margin: 4px 0 0 0; font-size: 18px; color: var(--text-primary);">${coffeeName}${roastery}</h3>
                    </div>
                    <span style="background: var(--accent-light, rgba(230, 81, 0, 0.1)); color: var(--accent); font-weight: bold; font-size: 14px; padding: 4px 10px; border-radius: 20px; border: 1px solid var(--accent);">
                        ★ ${avgScore} / 5
                    </span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; margin-bottom: 12px; background: var(--surface-raised); padding: 10px; border-radius: 6px; font-size: 13px; text-align: center;">
                    <div><b>Aroma:</b> ${log.aroma_score ?? '-'}/5</div>
                    <div><b>Acidez:</b> ${log.acidity_score ?? '-'}/5</div>
                    <div><b>Corpo:</b> ${log.body_score ?? '-'}/5</div>
                    <div><b>Doçura:</b> ${log.sweetness_score ?? '-'}/5</div>
                    <div><b>Finalização:</b> ${log.aftertaste_score ?? '-'}/5</div>
                </div>
                ${log.perceived_notes ? `<div style="font-size: 13px; color: var(--text-primary); margin-bottom: 4px;"><b>Notas Percebidas:</b> ${log.perceived_notes}</div>` : ''}
                ${log.unperceived_notes ? `<div style="font-size: 13px; color: var(--text-secondary); margin-bottom: 4px;"><b>Não Percebidas:</b> ${log.unperceived_notes}</div>` : ''}
                ${log.comments ? `<div style="font-size: 13px; background: rgba(0,0,0,0.15); padding: 8px; border-radius: 6px; font-style: italic; margin-top: 8px; color: var(--text-secondary);">${log.comments}</div>` : ''}
            </div>
        `;
    }).join('');
}

async function populateSensoryCoffeeDropdown() {
    const select = document.getElementById('sensory-coffee-id');
    if (!select) return;

    select.innerHTML = '<option value="">Carregando estoque de cafés...</option>';

    try {
        let stockItems = [];

        // 1. Busca do estoque (/api/stock)
        try {
            const response = await apiFetch('/api/stock');
            stockItems = Array.isArray(response)
                ? response
                : (response.stock || response.data || response.items || []);
        } catch (stockErr) {
            console.warn('Não foi possível carregar via /api/stock, tentando state/coffees:', stockErr);
        }

        // 2. Se o estoque veio vazio da API, tenta usar o estado local do app
        if ((!stockItems || stockItems.length === 0) && state.stock && state.stock.length > 0) {
            stockItems = state.stock;
        }

        // 3. Fallback: Se não houver módulo de estoque atrelado, busca a lista de cafés (/api/coffees)
        if (!stockItems || stockItems.length === 0) {
            const coffeeRes = await apiFetch('/api/coffees');
            stockItems = Array.isArray(coffeeRes)
                ? coffeeRes
                : (coffeeRes.coffees || coffeeRes.data || []);
        }

        // 4. Se realmente não houver nenhum café disponível
        if (!stockItems || stockItems.length === 0) {
            select.innerHTML = '<option value="">Nenhum café em estoque no momento</option>';
            return;
        }

        // 5. Normaliza os dados (seja item de estoque ou objeto direto de café)
        const optionsHTML = stockItems
            .filter(item => {
                const qty = item.quantity ?? item.weight_grams ?? item.stock_quantity ?? 1;
                return qty > 0;
            })
            .map(item => {
                const coffee = item.coffee || item;
                const coffeeId = coffee.id || item.coffee_id || item.id;
                const name = coffee.name || item.coffee_name || item.name || 'Café Sem Nome';
                const roastery = coffee.roastery || coffee.roaster || item.roastery || '';
                const roasteryText = roastery ? ` (${roastery})` : '';

                return `<option value="${coffeeId}">${name}${roasteryText}</option>`;
            })
            .join('');

        if (!optionsHTML) {
            select.innerHTML = '<option value="">Nenhum café com estoque disponível</option>';
            return;
        }

        select.innerHTML = '<option value="">Selecione um café...</option>' + optionsHTML;

    } catch (err) {
        console.error('Erro ao carregar cafés para o diário:', err);
        select.innerHTML = '<option value="">Erro ao carregar lista de cafés</option>';
    }
}

// Handler de abertura da modal sensorial
function openSensoryModal() {
    const modal = document.getElementById('sensory-modal');
    if (modal) {
        modal.classList.remove('hidden');
        modal.style.display = 'flex';
    }
    populateSensoryCoffeeDropdown();
}

// Vincula o clique do botão de Nova Degustação (APENAS UMA VEZ)
document.getElementById('btn-open-sensory-modal')?.addEventListener('click', openSensoryModal);

// Submit do formulário Sensorial
document.getElementById('sensory-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
        const coffeeIdVal = document.getElementById('sensory-coffee-id').value;
        if (!coffeeIdVal) {
            showToast('Por favor, selecione um café.', 'error');
            return;
        }

        const body = {
            coffee_id: parseInt(coffeeIdVal),
            aroma_score: parseInt(document.getElementById('sensory-aroma').value) || 0,
            acidity_score: parseInt(document.getElementById('sensory-acidity').value) || 0,
            body_score: parseInt(document.getElementById('sensory-body').value) || 0,
            sweetness_score: parseInt(document.getElementById('sensory-sweetness').value) || 0,
            aftertaste_score: parseInt(document.getElementById('sensory-aftertaste').value) || 0,
            perceived_notes: document.getElementById('sensory-perceived').value,
            unperceived_notes: document.getElementById('sensory-unperceived').value,
            comments: document.getElementById('sensory-comments').value
        };

        const result = await apiFetch('/api/sensory-logs', { method: 'POST', body });
        if (!showMutationResult(result, 'Registro sensorial salvo com sucesso!')) {
            const modal = document.getElementById('sensory-modal');
            if (modal) {
                modal.classList.add('hidden');
                modal.style.display = 'none';
            }
            document.getElementById('sensory-form').reset();
            return;
        }

        // Fechamento padronizado da modal
        const modal = document.getElementById('sensory-modal');
        if (modal) {
            modal.classList.add('hidden');
            modal.style.display = 'none';
        }

        document.getElementById('sensory-form').reset();
        if (typeof fetchAndRenderSensoryLogs === 'function') {
            fetchAndRenderSensoryLogs();
        }
    } catch (err) {
        if (err.message === "OFFLINE_NO_CACHE") {
            showToast("Este conteúdo ainda não foi salvo para uso offline.", "error");
            return;
        }
        showToast(err.message || "Erro ao salvar registro", "error");
    }
});

// --- FASE 10: EXPLORADOR SENSORIAL ---
async function fetchAndRenderSensoryExplorer() {
    const currentView = location.hash.replace('#', '').replace('/', '') || 'dashboard';
    if (!state.token || currentView !== 'explorer') return;

    try {
        const data = await apiFetch('/api/sensory-explorer/profile');
        renderSensoryExplorer(data);
    } catch (err) {
        if (err.message === "OFFLINE_NO_CACHE") {
            showToast("Este conteúdo ainda não foi salvo para uso offline.", "error");
            return;
        }
        showToast(err.message, 'error');
    }
}

function renderSensoryExplorer(data) {
    const summaryContainer = document.getElementById('explorer-summary-metrics');
    const suggestionsContainer = document.getElementById('explorer-suggestions-list');

    if (summaryContainer) {
        summaryContainer.innerHTML = `
            <div><b>Degustações Registradas:</b> ${data.total_evaluations}</div>
            <div><b>Aroma Médio:</b> ${data.avg_aroma} / 10</div>
            <div><b>Acidez Média:</b> ${data.avg_acidity} / 10</div>
            <div><b>Corpo Médio:</b> ${data.avg_body} / 10</div>
            <div><b>Doçura Média:</b> ${data.avg_sweetness} / 10</div>
            <div><b>Finalização Média:</b> ${data.avg_aftertaste} / 10</div>
            <div><b>Notas mais Frequentes:</b> ${data.top_notes && data.top_notes.length > 0 ? data.top_notes.join(', ') : 'Nenhuma ainda'}</div> `;
    }

    if (suggestionsContainer && data.suggestions) {
        suggestionsContainer.innerHTML = data.suggestions.map(s => `<li>${s}</li>`).join('');
    }
}

window.explorerActions = {
    showFlavorDetail: (title, desc) => {
        const box = document.getElementById('flavor-detail-box');
        document.getElementById('flavor-detail-title').innerText = title;
        document.getElementById('flavor-detail-desc').innerText = desc;
        if (box) box.style.display = 'block';
    }
};

// --- FASE 11: CADERNO DE BEBIDAS ---
async function fetchAndRenderBeverages() {
    if (!state.token) return;
    try {
        const beverages = await apiFetch('/api/beverages');
        const list = document.getElementById('beverages-list');
        if (!list) return;

        if (!beverages || beverages.length === 0) {
            list.innerHTML = '<div class="card" style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">Nenhuma bebida no cardápio ainda. Crie a primeira abaixo!</div>';
            return;
        }

        list.innerHTML = beverages.map(b => `
            <div class="card" style="border-top: 4px solid ${b.is_cold ? '#3b82f6' : '#ef4444'};">
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <h3 style="margin-bottom: 4px;">${b.is_cold ? '🧊' : '☕'} ${b.name}</h3>
                    <div style="display:flex; gap: 6px;">
                        <button onclick="editBeverage(${b.id})" class="btn btn-sm btn-secondary" style="width:auto;">Editar</button>
                        <button onclick="deleteBeverage(${b.id})" style="background: none; border: none; cursor: pointer; color: #ef4444; font-weight: bold;">x</button>
                    </div>
                </div>
                <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 12px;">${b.ingredients || 'Sem ingredientes listados'}</p>
                <div style="display: flex; gap: 16px; font-size: 13px; font-weight: 500; margin-bottom: 12px;">
                    <span>Shots: ${b.espresso_shots}</span>
                    <span>Vol: ${b.total_volume_ml ? b.total_volume_ml + 'ml' : '--'}</span>
                </div>
                ${b.description ? `<p style="font-size: 14px; padding-top: 12px; border-top: 1px solid var(--border);">${b.description}</p>` : ''}
            </div>
        `).join('');
    } catch (err) {
        showToast(err.message || "Erro ao carregar bebidas", 'error');
    }
}

// Listener para ABRIR a Modal de Bebidas (garantindo classe hidden)
document.getElementById('btn-open-beverage-modal')?.addEventListener('click', () => {
    const modal = document.getElementById('modal-beverage');
    document.getElementById('bev-id').value = '';
    document.getElementById('beverage-form')?.reset();
    if (modal) {
        modal.classList.remove('hidden');
        modal.style.display = 'flex'; // Garante visibilidade em qualquer padrão CSS
    }
});

// Submit do formulário de Bebidas
const formBeverage = document.getElementById('beverage-form');
if (formBeverage) {
    formBeverage.addEventListener('submit', async (e) => {
        e.preventDefault();
        const id = document.getElementById('bev-id').value;
        const payload = {
            name: document.getElementById('bev-name').value,
            ingredients: document.getElementById('bev-ingredients').value,
            is_cold: document.getElementById('bev-iscold').checked,
            espresso_shots: parseInt(document.getElementById('bev-shots').value) || 0,
            total_volume_ml: document.getElementById('bev-volume').value ? parseInt(document.getElementById('bev-volume').value) : null,
            description: document.getElementById('bev-desc').value
        };
        try {
            const result = await apiFetch(id ? `/api/beverages/${id}` : '/api/beverages', {
                method: id ? 'PUT' : 'POST',
                body: payload
            });
            if (!showMutationResult(result, id ? "Bebida atualizada!" : "Bebida adicionada ao menu!")) {
                closeModal(document.getElementById('modal-beverage'));
                return;
            }
            formBeverage.reset();
            document.getElementById('bev-id').value = '';
            fetchAndRenderBeverages();

            // Fechamento padronizado da modal
            const modal = document.getElementById('modal-beverage');
            if (modal) {
                modal.classList.add('hidden');
                modal.style.display = 'none';
            }
        } catch (err) {
            showToast(err.message || "Erro ao salvar bebida", 'error');
        }
    });
}

window.deleteBeverage = async (id) => {
    if (!confirm("Tem certeza que deseja excluir esta bebida?")) return;
    try {
        const result = await apiFetch(`/api/beverages/${id}`, { method: 'DELETE' });
        if (!showMutationResult(result, "Bebida excluida!")) return;
        fetchAndRenderBeverages();
    } catch (err) {
        showToast(err.message || "Erro ao excluir bebida", 'error');
    }
};

window.editBeverage = async (id) => {
    try {
        const beverages = await apiFetch('/api/beverages');
        const beverage = Array.isArray(beverages) ? beverages.find(b => b.id === id) : null;
        if (!beverage) {
            showToast("Bebida não encontrada.", "error");
            return;
        }

        document.getElementById('bev-id').value = beverage.id;
        document.getElementById('bev-name').value = beverage.name || '';
        document.getElementById('bev-ingredients').value = beverage.ingredients || '';
        document.getElementById('bev-iscold').checked = Boolean(beverage.is_cold);
        document.getElementById('bev-shots').value = beverage.espresso_shots ?? 1;
        document.getElementById('bev-volume').value = beverage.total_volume_ml ?? '';
        document.getElementById('bev-desc').value = beverage.description || '';
        openModal(document.getElementById('modal-beverage'));
    } catch (err) {
        showToast(err.message || "Erro ao abrir bebida", "error");
    }
};

    // --- FASE 12: BARISTA DE IA COM HISTÓRICO ---
    let currentAiSessionId = null;
    const chatMessagesContainer = document.getElementById('ai-chat-messages');
    const chatForm = document.getElementById('ai-chat-form');
    const chatInput = document.getElementById('ai-chat-input');
    const sessionsListContainer = document.getElementById('ai-sessions-list');
    const newChatBtn = document.getElementById('ai-new-chat-btn');
    const toggleSidebarBtn = document.getElementById('ai-toggle-sidebar');
    const aiSidebar = document.getElementById('ai-sidebar');

    // Toggle do Sidebar
    if (toggleSidebarBtn && aiSidebar) {
    toggleSidebarBtn.addEventListener('click', () => {
        aiSidebar.style.display = (aiSidebar.style.display === 'none') ? 'flex' : 'none';
    });
    }

    // Botão "Novo Chat"
    if (newChatBtn) {
    newChatBtn.addEventListener('click', () => {
        currentAiSessionId = null;
        if (chatMessagesContainer) chatMessagesContainer.innerHTML = '';
        if (chatInput) chatInput.value = '';
        loadAiSessions(false); // 'false' impede que o chat antigo seja aberto automaticamente
    });
    }

    // Função para botões de sugestão/prompt no HTML
    window.sendAiPrompt = function(promptText) {
    if (!chatInput) return;
    chatInput.value = promptText;
    if (chatForm) {
        chatForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    }
    };

    // Evento de Envio do Formulário de Chat (Unificado)
    if (chatForm) {
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const messageText = chatInput.value.trim();
        if (!messageText) return;

        // Checagem imediata de conexão offline para a IA
        if (!navigator.onLine) {
        appendChatMessage('user', messageText);
        chatInput.value = '';
        appendChatMessage('assistant', 'Barista IA indispon?vel offline.');
        return;
        }

        appendChatMessage('user', messageText);
        chatInput.value = '';

        try {
        const token = state.token || localStorage.getItem("coffee_lab_token") || localStorage.getItem("token");

        const response = await fetch('/api/ai/chat', {
            method: 'POST',
            headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
            session_id: currentAiSessionId,
            message: messageText
            })
        });

        if (!response.ok) throw new Error("Erro ao responder mensagem.");
        const data = await response.json();

        if (data.session_id) {
            currentAiSessionId = data.session_id;
        }

        appendChatMessage('assistant', data.response);
        await loadAiSessions(true);
        } catch (err) {
        // Captura falha de conexão no fetch ou resposta com erro
        appendChatMessage('assistant', 'Barista IA indispon?vel offline.');
        console.warn("IA indisponível ou sem conexão:", err.message);
        }
    });
    }

    // Desenha os balões de conversa no container
    function appendChatMessage(role, text) {
    if (!chatMessagesContainer) return;
    const msgDiv = document.createElement('div');
    msgDiv.style.cssText = `
        margin-bottom: 12px; padding: 10px 14px; border-radius: 8px; font-size: 14px; line-height: 1.5;
        max-width: 80%; align-self: ${role === 'user' ? 'flex-end' : 'flex-start'};
        background: ${role === 'user' ? '#2563eb' : '#27272a'};
        color: #ffffff;
    `;
    msgDiv.innerText = text;
    chatMessagesContainer.appendChild(msgDiv);
    chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
    }

    // Carregar lista de sessões/histórico
    async function loadAiSessions(autoSelect = false) {
    if (!sessionsListContainer) return;

    if (false && !navigator.onLine) {
        sessionsListContainer.innerHTML = '<div style="padding: 10px; font-size: 12px; color: #a1a1aa; text-align: center;">Barista IA indisponível offline.</div>';
        return;
    }

    try {
        const sessions = await apiFetch('/api/ai/sessions');
        sessionsListContainer.innerHTML = '';

        if (sessions.length === 0) return;

        sessions.forEach(session => {
        const item = document.createElement('div');
        const isActive = session.id === currentAiSessionId;
        const isDarkTheme = document.documentElement.getAttribute('data-theme') === 'dark';
        const activeBackground = isDarkTheme ? '#27272a' : 'transparent';
        const activeColor = isDarkTheme ? '#ffffff' : 'var(--text)';
        const inactiveColor = 'var(--text-secondary)';
        const activeBorder = isDarkTheme ? '#3f3f46' : '#18181b';

        item.style.cssText = `
            display: flex; justify-content: space-between; align-items: center; position: relative;
            padding: 8px 12px; border-radius: 6px; cursor: pointer; font-size: 13px;
            color: ${isActive ? activeColor : inactiveColor};
            background: ${isActive ? activeBackground : 'transparent'};
            border: 1px solid ${isActive ? activeBorder : 'transparent'};
        `;

        const titleSpan = document.createElement('span');
        titleSpan.style.cssText = 'white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1;';
        titleSpan.innerText = session.title;
        titleSpan.title = session.title;
        titleSpan.addEventListener('click', (e) => {
            e.stopPropagation();
            selectAiSession(session.id);
        });

        const optionsBtn = document.createElement('button');
        optionsBtn.innerText = '⋮';
        optionsBtn.style.cssText = 'display: none; background: transparent; border: none; color: var(--text-secondary); cursor: pointer; font-size: 16px; padding: 0 4px; font-weight: bold; margin-left: 8px; flex-shrink: 0;';

        const menuDiv = document.createElement('div');
        menuDiv.style.cssText = `
            display: none; position: absolute; right: 8px; top: 32px; background: var(--surface-raised);
            border: 1px solid var(--border); border-radius: 6px; padding: 4px; z-index: 50;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5); flex-direction: column; min-width: 120px;
        `;

        const renameBtn = document.createElement('button');
        renameBtn.innerText = 'Renomear';
        renameBtn.style.cssText = 'background: transparent; border: none; color: var(--text); text-align: left; padding: 8px; cursor: pointer; font-size: 12px; width: 100%; border-radius: 4px;';
        renameBtn.onmouseover = () => renameBtn.style.background = 'var(--surface)';
        renameBtn.onmouseout = () => renameBtn.style.background = 'transparent';
        renameBtn.onclick = (e) => {
            e.stopPropagation();
            menuDiv.style.display = 'none';
            renameAiSession(session.id, session.title);
        };

        const deleteBtn = document.createElement('button');
        deleteBtn.innerText = 'Excluir';
        deleteBtn.style.cssText = 'background: transparent; border: none; color: #ef4444; text-align: left; padding: 8px; cursor: pointer; font-size: 12px; width: 100%; border-radius: 4px;';
        deleteBtn.onmouseover = () => deleteBtn.style.background = 'var(--surface)';
        deleteBtn.onmouseout = () => deleteBtn.style.background = 'transparent';
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            menuDiv.style.display = 'none';
            deleteAiSession(session.id);
        };

        menuDiv.appendChild(renameBtn);
        menuDiv.appendChild(deleteBtn);

        item.addEventListener('mouseenter', () => {
            if (!isActive) item.style.background = '#18181b';
            optionsBtn.style.display = 'inline-block';
        });

        item.addEventListener('mouseleave', () => {
            if (!isActive) item.style.background = 'transparent';
            if (menuDiv.style.display !== 'flex') {
            optionsBtn.style.display = 'none';
            }
        });

        optionsBtn.onclick = (e) => {
            e.stopPropagation();
            const isVisible = menuDiv.style.display === 'flex';

            document.querySelectorAll('#ai-sessions-list > div').forEach(div => {
            const otherMenu = div.querySelector('div');
            if (otherMenu && otherMenu !== menuDiv) otherMenu.style.display = 'none';
            });

            if (isVisible) {
            menuDiv.style.display = 'none';
            optionsBtn.style.display = 'none';
            } else {
            menuDiv.style.display = 'flex';
            optionsBtn.style.display = 'inline-block';
            }
        };

        item.appendChild(titleSpan);
        item.appendChild(optionsBtn);
        item.appendChild(menuDiv);
        sessionsListContainer.appendChild(item);
        });

        if (autoSelect && !currentAiSessionId && sessions.length > 0) {
        selectAiSession(sessions[0].id);
        }
    } catch (err) {
        console.error("Erro ao carregar sessões de IA:", err);
    }
    }

    async function selectAiSession(sessionId) {
    currentAiSessionId = sessionId;
    if (chatMessagesContainer) chatMessagesContainer.innerHTML = '';

    if (false && !navigator.onLine) {
        appendChatMessage('assistant', 'Barista IA indispon?vel offline.');
        return;
    }

    try {
        const messages = await apiFetch(`/api/ai/sessions/${sessionId}/messages`);
        messages.forEach(msg => {
            appendChatMessage(msg.role, msg.content);
        });
    } catch (err) {
        console.error("Erro ao carregar mensagens da sessão:", err);
        appendChatMessage('assistant', 'Barista IA indispon?vel offline.');
    }

    loadAiSessions(true);
    }

    async function renameAiSession(sessionId, currentTitle) {
    if (!navigator.onLine) {
        if (typeof showToast === 'function') showToast("Barista IA indisponível offline.", "error");
        else alert("Barista IA indisponível offline.");
        return;
    }

    const newTitle = prompt("Digite o novo nome para este chat:", currentTitle);
    if (!newTitle || newTitle === currentTitle) return;

    try {
        const token = state.token || localStorage.getItem("coffee_lab_token") || localStorage.getItem("token");
        const response = await fetch(`/api/ai/sessions/${sessionId}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ title: newTitle })
        });
        if (!response.ok) throw new Error("Erro ao renomear conversa.");
        await loadAiSessions(true);
    } catch (err) {
        alert(err.message);
    }
    }

    async function deleteAiSession(sessionId) {
    if (!navigator.onLine) {
        if (typeof showToast === 'function') showToast("Barista IA indisponível offline.", "error");
        else alert("Barista IA indisponível offline.");
        return;
    }

    if (!confirm("Tem certeza que deseja excluir esta conversa?")) return;

    try {
        const token = state.token || localStorage.getItem("coffee_lab_token") || localStorage.getItem("token");
        const response = await fetch(`/api/ai/sessions/${sessionId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error("Erro ao excluir conversa.");
        if (currentAiSessionId === sessionId) {
        currentAiSessionId = null;
        if (chatMessagesContainer) chatMessagesContainer.innerHTML = '';
        }
        await loadAiSessions(true);
    } catch (err) {
        alert(err.message);
    }
    }

        // --- FASE 13: ESTATÍSTICAS E GRÁFICOS ---
        // Armazenar as instâncias dos gráficos para podermos destruí-las e recriá-las (evita bugs de hover)
        window.consumptionChart = null;
        window.methodsChart = null;

        async function fetchAndRenderStats() {
        if (!state.token || location.hash !== '#/stats') return;

        try {
            const extractionsData = await apiFetch('/api/extractions').catch(() => []);
            const extractionsRaw = Array.isArray(extractionsData) ? extractionsData : [];

            const coffeesData = await apiFetch('/api/coffees').catch(() => []);
            const coffees = Array.isArray(coffeesData) ? coffeesData : [];

            const sensoryData = await apiFetch('/api/sensory-logs').catch(() => []);
            const sensory = Array.isArray(sensoryData) ? sensoryData : [];

            // --- LER OS FILTROS DA TELA ---
            const timeFilter = document.getElementById('stats-filter-time')?.value || 'all';
            const methodFilter = document.getElementById('stats-filter-method')?.value || 'all';
            const profileFilter = document.getElementById('stats-filter-profile')?.value || 'all';

            // --- POPULAR O SELECT DE MÉTODOS DINAMICAMENTE ---
            const methodSelect = document.getElementById('stats-filter-method');
            if (methodSelect && methodSelect.options.length <= 1) {
                const uniqueMethods = [...new Set(extractionsRaw.map(e => e.method || (e.recipe ?
    e.recipe.method : 'Outro')))];
                uniqueMethods.filter(Boolean).forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m;
                    opt.textContent = m;
                    methodSelect.appendChild(opt);
                });
            }

            const now = new Date();

            // --- APLICAR OS FILTROS ---
            let extractions = extractionsRaw.filter(ext => {
                const extDate = new Date(ext.extraction_date || ext.created_at || Date.now());
                const method = ext.method || (ext.recipe ? ext.recipe.method : 'Outro');
                const coffeeId = ext.coffee_id || (ext.recipe ? ext.recipe.coffee_id : null);
                const coffeeObj = coffees.find(c => c.id == coffeeId);

                // Filtro de Tempo
                let passTime = true;
                if (timeFilter === 'year') {
                    passTime = extDate.getFullYear() === now.getFullYear();
                } else if (timeFilter !== 'all') {
                    const days = parseInt(timeFilter);
                    const diffTime = Math.abs(now - extDate);
                    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                    passTime = diffDays <= days;
                }

                // Filtro de Método
                let passMethod = true;
                if (methodFilter !== 'all') {
                    passMethod = method === methodFilter;
                }

                // Filtro de Perfil Sensorial (Procura o termo nas notas sensoriais do café)
                let passProfile = true;
                if (profileFilter !== 'all') {
                    if (coffeeObj && coffeeObj.sensory_notes) {
                        passProfile =
    coffeeObj.sensory_notes.toLowerCase().includes(profileFilter.toLowerCase());
                    } else {
                        passProfile = false; // Se não tem café ou notas, não passa no filtro
                    }
                }

                return passTime && passMethod && passProfile;
            });

            // --- CÃLCULO DAS MÃ‰TRICAS COM OS DADOS FILTRADOS ---
            const totalExtractions = extractions.length;
            let totalConsumption = 0;

            const methodCounts = {};
            const coffeeCounts = {};

            // Estrutura para os últimos 6 meses (Gráfico de Consumo)
            const monthlyData = {};
            for (let i = 5; i >= 0; i--) {
                const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
                monthlyData[`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`] = 0;
            }

            extractions.forEach(ext => {
                const weight = ext.coffee_weight || (ext.recipe ? ext.recipe.coffee_weight : 0) || 15;
                totalConsumption += weight;

                const extDate = new Date(ext.extraction_date || ext.created_at || Date.now());
                const monthKey = `${extDate.getFullYear()}-${String(extDate.getMonth() +
    1).padStart(2, '0')}`;

                // Só soma no gráfico se o mês estiver na janela dos últimos 6 meses
                if (monthlyData[monthKey] !== undefined) {
                    monthlyData[monthKey] += weight;
                }

                const method = ext.method || (ext.recipe ? ext.recipe.method : 'Outro');
                methodCounts[method] = (methodCounts[method] || 0) + 1;

                const coffeeId = ext.coffee_id || (ext.recipe ? ext.recipe.coffee_id : null);
                if (coffeeId) coffeeCounts[coffeeId] = (coffeeCounts[coffeeId] || 0) + 1;
            });

            let favMethod = "Nenhum";
            let favCoffeeName = "Nenhum";

            if (Object.keys(methodCounts).length > 0) {
                favMethod = Object.keys(methodCounts).reduce((a, b) => methodCounts[a] >
    methodCounts[b] ? a : b);
            }
            if (Object.keys(coffeeCounts).length > 0) {
                const favCoffeeId = Object.keys(coffeeCounts).reduce((a, b) => coffeeCounts[a] >
    coffeeCounts[b] ? a : b);
                const favCoffeeObj = coffees.find(c => c.id == favCoffeeId);
                if (favCoffeeObj) favCoffeeName = favCoffeeObj.name;
            }

            // Calcular Média de Avaliações (apenas dos cafés extraídos neste filtro)
            let avgRating = "N/A";
            const filteredSensory = sensory.filter(log => extractions.some(e => e.id ===
    log.extraction_id));
            if (filteredSensory.length > 0) {
                const total = filteredSensory.reduce((acc, log) => acc + ((log.aroma_score + log.acidity_score +
    log.body_score + log.sweetness_score + log.aftertaste_score) / 5), 0);
                avgRating = (total / filteredSensory.length).toFixed(1) + " / 10";
            }

            // --- RENDERIZAÇÃO ---
            const cardsContainer = document.getElementById('stats-summary-cards');
            if (cardsContainer) {
                cardsContainer.innerHTML = `
                    <div class="card" style="padding: 16px;">
                        <div style="font-size: 12px; color: var(--text-secondary);">Extrações no
    Período</div>
                        <div style="font-size: 26px; font-weight: 700; color:
    var(--text);">${totalExtractions}</div>
                    </div>
                    <div class="card" style="padding: 16px;">
                        <div style="font-size: 12px; color: var(--text-secondary);">Consumo
    (Filtro)</div>
                        <div style="font-size: 26px; font-weight: 700; color:
    var(--accent);">${totalConsumption.toFixed(0)}g</div>
                    </div>
                    <div class="card" style="padding: 16px;">
                        <div style="font-size: 12px; color: var(--text-secondary);">Método Favorito</div>
                        <div style="font-size: 18px; font-weight: 700; color: var(--text); margin-top:
    6px;">${favMethod}</div>
                    </div>
                    <div class="card" style="padding: 16px;">
                        <div style="font-size: 12px; color: var(--text-secondary);">Café Favorito</div>
                        <div style="font-size: 18px; font-weight: 700; color: var(--text); margin-top: 6px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${favCoffeeName}</div>
                    </div>
                `;
            }

            renderCharts(monthlyData, methodCounts);

        } catch (err) {
            console.error(err);
            showToast('Erro ao processar estatísticas.', 'error');
        }
        }

        function drawFallbackChart(canvas, labels, values, title) {
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const rect = canvas.parentElement?.getBoundingClientRect();
            const width = Math.max(320, Math.floor(rect?.width || canvas.clientWidth || 420));
            const height = Math.max(260, Math.floor(rect?.height || canvas.clientHeight || 280));
            const dpr = window.devicePixelRatio || 1;
            canvas.width = width * dpr;
            canvas.height = height * dpr;
            canvas.style.width = `${width}px`;
            canvas.style.height = `${height}px`;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const textColor = isDark ? '#f4f4f5' : '#1a1a1e';
            const mutedColor = isDark ? '#a1a1aa' : '#62626a';
            const gridColor = isDark ? '#27272a' : '#e4e4e7';
            const accentColor = isDark ? '#a1785e' : '#6f4e37';
            const safeLabels = labels.length ? labels : ['Sem dados'];
            const safeValues = values.length ? values : [0];
            const maxValue = Math.max(...safeValues, 1);
            const padding = 42;
            const barAreaWidth = width - padding * 2;
            const barAreaHeight = height - padding * 2 - 18;
            const barWidth = Math.max(12, barAreaWidth / safeValues.length * 0.58);

            ctx.clearRect(0, 0, width, height);
            ctx.fillStyle = textColor;
            ctx.font = '600 13px Inter, system-ui, sans-serif';
            ctx.fillText(title, padding, 24);
            ctx.strokeStyle = gridColor;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(padding, height - padding);
            ctx.lineTo(width - padding / 2, height - padding);
            ctx.stroke();

            safeValues.forEach((value, index) => {
                const x = padding + (barAreaWidth / safeValues.length) * index + (barAreaWidth / safeValues.length - barWidth) / 2;
                const barHeight = Math.max(2, (Number(value) / maxValue) * barAreaHeight);
                const y = height - padding - barHeight;
                ctx.fillStyle = accentColor;
                ctx.fillRect(x, y, barWidth, barHeight);
                ctx.fillStyle = mutedColor;
                ctx.font = '11px Inter, system-ui, sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText(String(safeLabels[index]).slice(0, 12), x + barWidth / 2, height - 18);
                ctx.fillText(String(value), x + barWidth / 2, y - 6);
            });
            ctx.textAlign = 'left';
        }

        function renderCharts(monthlyData, methodCounts) {
            // Fallback offline quando o Chart.js do CDN ainda nao esta disponivel.
            if (typeof Chart === 'undefined') {
                drawFallbackChart(
                    document.getElementById('chart-consumption'),
                    Object.keys(monthlyData).map(k => {
                        const [y, m] = k.split('-');
                        return new Date(y, m - 1).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' }).replace('.', '');
                    }),
                    Object.values(monthlyData),
                    'Consumo mensal'
                );
                drawFallbackChart(
                    document.getElementById('chart-methods'),
                    Object.keys(methodCounts),
                    Object.values(methodCounts),
                    'Metodos favoritos'
                );
                return;
            }
            const ctxConsumption = document.getElementById('chart-consumption');
            const ctxMethods = document.getElementById('chart-methods');
            if (!ctxConsumption || !ctxMethods) return;

            // Destrói os gráficos antigos antes de recriar
            if (window.consumptionChart) window.consumptionChart.destroy();
            if (window.methodsChart) window.methodsChart.destroy();

            // Detecta o tema atual para estilizar os eixos do gráfico (Modo Claro/Escuro)
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const textColor = isDark ? '#a1a1aa' : '#62626a';
            const gridColor = isDark ? '#27272a' : '#e4e4e7';
            const accentColor = isDark ? '#a1785e' : '#6f4e37';

            // Configurações Globais do Chart.js
            Chart.defaults.color = textColor;
            Chart.defaults.font.family = "'Inter', system-ui, sans-serif";

            // Gráfico de Barras: Consumo
            window.consumptionChart = new Chart(ctxConsumption, {
                type: 'bar',
                data: {
                    labels: Object.keys(monthlyData).map(k => {
                        const [y, m] = k.split('-');
                        return new Date(y, m - 1).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' }).replace('.', '');
                    }),
                    datasets: [{
                        label: 'Gramas Consumidas',
                        data: Object.values(monthlyData),
                        backgroundColor: accentColor,
                        borderRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { grid: { color: gridColor }, beginAtZero: true },
                        x: { grid: { display: false } }
                    },
                    plugins: { legend: { display: false } }
                }
            });

            // Gráfico de Rosca: Métodos
            const methodsLabels = Object.keys(methodCounts);
            const methodsValues = Object.values(methodCounts);

            window.methodsChart = new Chart(ctxMethods, {
                type: 'doughnut',
                data: {
                    labels: methodsLabels.length ? methodsLabels : ['Sem dados'],
                    datasets: [{
                        data: methodsValues.length ? methodsValues : [1],
                        backgroundColor: methodsValues.length ? [
                            '#f38721', '#2563eb', '#10b981', '#ef4444', '#8b5cf6', '#eab308'
                        ] : [gridColor],
                        borderWidth: 0,
                        cutout: '65%'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'right' }
                    }
                }
            });
        }

        // ==========================================
        // FASE 14 — PWA
        // ==========================================

        let deferredInstallPrompt = null;

        function registerServiceWorker() {
            if (!("serviceWorker" in navigator)) {
                console.warn(
                    "Service Worker não é suportado neste navegador."
                );

                return;
            }

            window.addEventListener("load", async () => {
                try {
                    const registration =
                        await navigator.serviceWorker.register(
                            "/sw.js",
                            {
                                scope: "/"
                            }
                        );

                    console.log(
                        "Service Worker registrado:",
                        registration.scope
                    );

                } catch (error) {
                    console.error(
                        "Erro ao registrar Service Worker:",
                        error
                    );
                }
            });
        }
        registerServiceWorker();

        function setupPWAInstall() {
            const installButton =
                document.getElementById("install-pwa-btn");

            if (!installButton) {
                return;
            }

            const isStandalone =
                window.matchMedia("(display-mode: standalone)").matches ||
                window.navigator.standalone === true;

            if (isStandalone) {
                installButton.classList.add("hidden");
                return;
            }

            window.addEventListener(
                "beforeinstallprompt",
                (event) => {
                    event.preventDefault();

                    deferredInstallPrompt = event;

                    installButton.classList.remove("hidden");
                }
            );

            installButton.addEventListener(
                "click",
                async () => {

                    if (!deferredInstallPrompt) {
                        return;
                    }

                    deferredInstallPrompt.prompt();

                    const result =
                        await deferredInstallPrompt.userChoice;

                    console.log(
                        "Resultado da instalação PWA:",
                        result.outcome
                    );

                    deferredInstallPrompt = null;

                    installButton.classList.add("hidden");
                }
            );

            window.addEventListener(
                "appinstalled",
                () => {

                    deferredInstallPrompt = null;

                    installButton.classList.add("hidden");

                    if (typeof showToast === "function") {
                        showToast(
                            "Coffee Lab instalado com sucesso!"
                        );
                    }
                }
            );
        }
        setupPWAInstall();

    function updateConnectionStatus() {
        const indicator =
            document.getElementById(
                "offline-indicator"
            );

        const text =
            document.getElementById(
                "offline-indicator-text"
            );

        if (!indicator || !text) {
            return;
        }

        const queue =
            getOfflineQueue();

        if (!navigator.onLine) {

            if (queue.length > 0) {
                text.textContent =
                    `Você está offline. ${queue.length} ação(ões) aguardando sincronização.`;
            } else {
                text.textContent =
                    "Você está offline. Os dados serão sincronizados quando a conexão voltar.";
            }

            indicator.classList.remove(
                "hidden"
            );

            return;
        }

        if (queue.length > 0) {
            text.textContent =
                `Conexão restaurada. ${queue.length} ação(ões) aguardando sincronização.`;

            indicator.classList.remove(
                "hidden"
            );

            return;
        }

        indicator.classList.add(
            "hidden"
        );
    }

    window.addEventListener('online', async () => {
    if (typeof showToast === 'function') {
        showToast("Conexão reestabelecida! Sincronizando dados...", "info");
    }

    // 1. Processa fila de requisições pendentes gravadas offline
    if (typeof processOfflineQueue === 'function') {
        await processOfflineQueue();
    }

    // 2. Re-executa o roteador para recarregar a tela atual com dados novos
    if (typeof route === 'function') {
        route();
    }
    refreshNotifications({ notify: true });
    });

    window.addEventListener('focus', () => {
        if (navigator.onLine && typeof processOfflineQueue === 'function') {
            processOfflineQueue();
        }
    });

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && navigator.onLine && typeof processOfflineQueue === 'function') {
            processOfflineQueue();
        }
    });

    setInterval(() => {
        if (
            navigator.onLine &&
            typeof processOfflineQueue === 'function' &&
            getOfflineQueue().some(action => !action.failedPermanently)
        ) {
            processOfflineQueue();
        }
    }, 15000);

    window.addEventListener(
        "offline",
        () => {

            console.log(
                "[Connection] Conexão perdida."
            );

            updateConnectionStatus();

            if (
                typeof showToast ===
                "function"
            ) {
                showToast(
                    "Você está offline. Algumas ações serão sincronizadas depois."
                );
            }
        }
    );

        // ## "Backup" ofline no localStorage inicialmente ## //
    const OFFLINE_QUEUE_KEY =
        "coffee_lab_offline_queue";

    function getOfflineQueueKey() {
        return `${OFFLINE_QUEUE_KEY}:${getCurrentUserCacheKey()}`;
    }

    function getOfflineQueue() {
        try {
            const queue = JSON.parse(
                localStorage.getItem(getOfflineQueueKey()) ||
                "[]"
            );

            return Array.isArray(queue)
                ? queue
                : [];

        } catch (error) {
            console.error(
                "[Offline] Erro ao ler fila:",
                error
            );

            return [];
        }
    }

    function saveOfflineQueue(queue) {
        try {
            if (!queue || queue.length === 0) {
                localStorage.removeItem(
                    getOfflineQueueKey()
                );
                localStorage.removeItem(
                    OFFLINE_QUEUE_KEY
                );
            } else {
                localStorage.setItem(
                    getOfflineQueueKey(),
                    JSON.stringify(queue)
                );
            }

            updateConnectionStatus();

        } catch (error) {
            console.error(
                "[Offline] Erro ao salvar fila:",
                error
            );
        }
    }

    async function addToOfflineQueue(action) {
        try {
            const queue =
                getOfflineQueue();

            const newAction = {
                id: crypto.randomUUID(),
                createdAt:
                    new Date().toISOString(),
                endpoint:
                    action.endpoint,
                method:
                    action.method,
                body:
                    action.body ?? null,
                baseUpdatedAt:
                    action.baseUpdatedAt || null,
                failedPermanently:
                    false,
                lastError:
                    null
            };

            queue.push(newAction);

            saveOfflineQueue(queue);

            console.log(
                "[Offline] Ação adicionada:",
                newAction
            );

            return newAction;

        } catch (error) {
            console.error(
                "[Offline] Erro ao adicionar ação:",
                error
            );

            throw error;
        }
    }

    // ==========================================
    // 1. SINCRONIZAÇÃO DA FILA OFFLINE
    // ==========================================
    async function processOfflineQueueLegacy() {
    let queue = [];
    try {
        queue = JSON.parse(localStorage.getItem('coffee_lab_offline_queue') || '[]');
    } catch (e) {
        console.warn("Não foi possível acessar o storage para sincronização offline:", e);
        return;
    }

    if (queue.length === 0) return;

    console.log(`[Offline] Sincronizando ${queue.length} ação(ões).`);
    const remainingActions = [];

    for (const action of queue) {
        try {
        console.log("[Offline] Enviando:", action);

        const headers = action.headers || {};
        if (state.token && !headers.Authorization) {
            headers.Authorization = `Bearer ${state.token}`;
        }
        if (action.body !== null && action.body !== undefined && !headers["Content-Type"]) {
            headers["Content-Type"] = "application/json";
        }

        const endpoint = action.endpoint || action.url;
        const response = await fetch(endpoint, {
            method: action.method,
            headers,
            body: action.body !== null && action.body !== undefined ? JSON.stringify(action.body) : undefined
        });

        if (response.ok) {
            console.log("[Offline] Sincronizado com sucesso:", endpoint);
            continue;
        }

        // Erros temporários de servidor: mantêm o item na fila para tentar na próxima
        if (response.status === 408 || response.status === 429 || response.status >= 500) {
            remainingActions.push(action);
            continue;
        }

        // Erros permanentes (ex: 400 Bad Request, 404, 403)
        console.error("[Offline] Ação rejeitada pelo servidor:", response.status, action);
        if (typeof showToast === 'function') {
            showToast("Uma ação offline não pôde ser sincronizada.", "error");
        }

        } catch (error) {
        console.error("[Offline] Erro de rede durante a sincronização:", error);
        remainingActions.push(action);
        }
    }

    // Atualiza a fila no localStorage apenas com os itens restantes
    try {
        localStorage.setItem('coffee_lab_offline_queue', JSON.stringify(remainingActions));
        if (remainingActions.length === 0 && typeof showToast === 'function') {
        showToast("Dados offline sincronizados com sucesso!", "success");
        }
    } catch (e) {
        console.error("Erro ao salvar fila atualizada no localStorage:", e);
    }

    if (typeof updateConnectionStatus === 'function') {
        updateConnectionStatus();
    }
    }

        // --- EVENTOS DE NAVEGAÇÃO E ENCERRAMENTO ---
    async function hasStockConflict(action, headers) {
        if (
            !action.baseUpdatedAt ||
            action.method !== "PUT" ||
            !String(action.endpoint || "").startsWith("/api/stock/")
        ) {
            return false;
        }

        const stockId = String(action.endpoint).match(/^\/api\/stock\/(\d+)/)?.[1];
        if (!stockId) return false;

        const response = await fetch("/api/stock", { headers });
        if (!response.ok) return false;

        const stock = await response.json();
        const current = Array.isArray(stock)
            ? stock.find(item => String(item.id) === stockId)
            : null;

        if (!current?.updated_at) return false;

        return new Date(current.updated_at).getTime() > new Date(action.baseUpdatedAt).getTime();
    }

    async function processOfflineQueue() {
        if (isSyncingOfflineQueue || !navigator.onLine) return;

        isSyncingOfflineQueue = true;

        try {
            const queue = getOfflineQueue()
                .slice()
                .sort((a, b) => new Date(a.createdAt || 0) - new Date(b.createdAt || 0));

            if (queue.length === 0) return;

            console.log(`[Offline] Sincronizando ${queue.length} acao(oes).`);
            const remainingActions = [];
            let syncedCount = 0;

            for (const action of queue) {
                try {
                    if (action.failedPermanently) {
                        remainingActions.push(action);
                        continue;
                    }

                    const endpoint = action.endpoint || action.url;
                    const headers = action.headers || {};

                    if (state.token && !headers.Authorization) {
                        headers.Authorization = `Bearer ${state.token}`;
                    }

                    if (action.body !== null && action.body !== undefined && !headers["Content-Type"]) {
                        headers["Content-Type"] = "application/json";
                    }

                    if (await hasStockConflict(action, headers)) {
                        remainingActions.push({
                            ...action,
                            failedPermanently: true,
                            lastError: "Conflito de estoque: o registro mudou em outro dispositivo antes da sincronizacao."
                        });
                        showToast(
                            "Conflito de estoque detectado. A acao offline foi mantida na fila para revisao.",
                            "error"
                        );
                        continue;
                    }

                    const response = await fetch(endpoint, {
                        method: action.method,
                        headers,
                        body: action.body !== null && action.body !== undefined ? JSON.stringify(action.body) : undefined
                    });

                    if (response.ok) {
                        console.log("[Offline] Sincronizado com sucesso:", endpoint);
                        syncedCount++;
                        continue;
                    }

                    if (response.status === 408 || response.status === 429 || response.status >= 500) {
                        remainingActions.push(action);
                        continue;
                    }

                    const errorBody = await response.text().catch(() => "");
                    remainingActions.push({
                        ...action,
                        failedPermanently: true,
                        lastError: `Erro permanente ${response.status}: ${errorBody || response.statusText}`
                    });
                    showToast(
                        "Uma acao offline nao pode ser sincronizada e foi mantida na fila.",
                        "error"
                    );
                } catch (error) {
                    console.error("[Offline] Erro de rede durante a sincronizacao:", error);
                    remainingActions.push(action);
                }
            }

            saveOfflineQueue(remainingActions);

            if (remainingActions.length === 0 && syncedCount > 0) {
                showToast("Dados offline sincronizados com sucesso!", "success");
            } else if (syncedCount > 0) {
                showToast(`${syncedCount} acao(oes) sincronizada(s). ${remainingActions.length} ainda precisam de atencao.`, "info");
            }

            if (syncedCount > 0 && typeof route === "function") {
                route();
            }
        } finally {
            if (typeof updateConnectionStatus === "function") {
                updateConnectionStatus();
            }

            isSyncingOfflineQueue = false;
        }
    }

        window.addEventListener('hashchange', route);
        document.addEventListener('DOMContentLoaded', () => {
            checkAuthUI();
            initNotificationSystem();
            const appShell = document.getElementById('app');
            const appMenuToggle = document.getElementById('app-menu-toggle');
            const isMobileLayout = () => window.matchMedia('(max-width: 768px)').matches;

            function closeAppSidebarOnMobile() {
                if (!appShell || !isMobileLayout()) return;
                appShell.classList.remove('mobile-sidebar-open');
                appMenuToggle?.setAttribute('aria-expanded', 'false');
            }

            appMenuToggle?.addEventListener('click', () => {
                if (!appShell) return;

                if (isMobileLayout()) {
                    const isOpen = appShell.classList.toggle('mobile-sidebar-open');
                    appShell.classList.remove('app-sidebar-hidden');
                    appMenuToggle.setAttribute('aria-expanded', String(isOpen));
                    return;
                }

                const isHidden = appShell.classList.toggle('app-sidebar-hidden');
                appShell.classList.remove('mobile-sidebar-open');
                appMenuToggle.setAttribute('aria-expanded', String(!isHidden));
            });

            window.addEventListener('resize', () => {
                if (!appShell) return;
                if (!isMobileLayout()) {
                    appShell.classList.remove('mobile-sidebar-open');
                    appMenuToggle?.setAttribute('aria-expanded', String(!appShell.classList.contains('app-sidebar-hidden')));
                } else {
                    appShell.classList.remove('app-sidebar-hidden');
                    appMenuToggle?.setAttribute('aria-expanded', String(appShell.classList.contains('mobile-sidebar-open')));
                }
            });

            document.querySelectorAll('.nav-link').forEach(link => {
                link.addEventListener('click', () => {
                    closeAppSidebarOnMobile();
                });
            });
            route();
        });
        })();
