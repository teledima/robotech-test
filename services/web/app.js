(function () {
    'use strict';

    const API_BASE = '/api';
    const WS_URL = 'ws://localhost:1234';
    const PAGE_SIZE = 10;
    const RECONNECT_DELAY = 5000;

    let currentPage = 1;
    let ws = null;
    let reconnectTimer = null;

    // DOM references
    const imagesContainer = document.getElementById('images-container');
    const eventsContainer = document.getElementById('events-container');
    const wsStatus = document.getElementById('ws-status');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const pageInfo = document.getElementById('page-info');

    // --- REST: Images ---

    async function fetchImages(page) {
        imagesContainer.innerHTML = '<div class="loader">Загрузка...</div>';
        try {
            const res = await fetch(`${API_BASE}/images/?page=${page}&count=${PAGE_SIZE}`);
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            renderImages(data);
            updatePagination(data);
        } catch (err) {
            imagesContainer.innerHTML = `<div class="empty">Ошибка загрузки: ${escapeHtml(err.message)}</div>`;
        }
    }

    function getExtensionFromUrl(url) {
        try {
            const pathname = new URL(url).pathname;
            const match = pathname.match(/\.([a-zA-Z0-9]+)$/);
            return match ? match[1].toLowerCase() : null;
        } catch {
            return null;
        }
    }

    function getExtensionFromMime(mime) {
        if (!mime || mime === 'application/octet-stream') return null;
        const sub = mime.split('/')[1];
        return sub ? sub.toLowerCase() : null;
    }

    async function downloadImage(img) {
        try {
            const res = await fetch(img.url);
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const blob = await res.blob();
            const ext =
                getExtensionFromUrl(img.url) ||
                getExtensionFromMime(blob.type) ||
                'jpg';
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `image_${img.id}.${ext}`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(a.href);
        } catch (err) {
            // fallback: open in new tab
            window.open(img.url, '_blank');
        }
    }

    function renderImages(images) {
        if (!Array.isArray(images) || images.length === 0) {
            imagesContainer.innerHTML = '<div class="empty">Нет изображений</div>';
            return;
        }
        imagesContainer.innerHTML = '';
        images.forEach(img => {
            const card = document.createElement('div');
            card.className = 'image-card';

            const imgEl = document.createElement('img');
            imgEl.src = img.url;
            imgEl.alt = 'image ' + img.id;
            imgEl.loading = 'lazy';
            imgEl.onerror = function () {
                this.style.background = '#e5e5ea';
                this.alt = 'недоступно';
            };

            const meta = document.createElement('div');
            meta.className = 'image-meta';
            meta.innerHTML = `<span class="id">#${img.id}</span> · ${img.width}×${img.height}`;

            const dlBtn = document.createElement('button');
            dlBtn.className = 'download-btn';
            dlBtn.textContent = '⬇ Скачать';
            dlBtn.title = 'Скачать изображение';
            dlBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                dlBtn.disabled = true;
                dlBtn.textContent = '⏳ ...';
                downloadImage(img).finally(() => {
                    dlBtn.disabled = false;
                    dlBtn.textContent = '⬇ Скачать';
                });
            });

            card.appendChild(imgEl);
            card.appendChild(meta);
            card.appendChild(dlBtn);
            imagesContainer.appendChild(card);
        });
    }

    function updatePagination(images) {
        pageInfo.textContent = 'Страница ' + currentPage;
        prevBtn.disabled = currentPage <= 1;
        // if we got fewer than PAGE_SIZE, assume it's the last page
        nextBtn.disabled = !Array.isArray(images) || images.length < PAGE_SIZE;
    }

    prevBtn.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            fetchImages(currentPage);
        }
    });

    nextBtn.addEventListener('click', () => {
        currentPage++;
        fetchImages(currentPage);
    });

    // --- WebSocket ---

    function setWsStatus(state, text) {
        wsStatus.className = 'status ' + state;
        wsStatus.textContent = text;
    }

    function connectWs() {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
            return;
        }
        setWsStatus('connecting', 'Подключение...');

        try {
            ws = new WebSocket(WS_URL);
        } catch (err) {
            setWsStatus('disconnected', 'Ошибка: ' + err.message);
            scheduleReconnect();
            return;
        }

        ws.onopen = () => {
            setWsStatus('connected', 'Подключено');
            if (reconnectTimer) {
                clearTimeout(reconnectTimer);
                reconnectTimer = null;
            }
            ws.send('is_checker');
            appendEvent('system', 'Соединение установлено, отправлено: is_checker');
        };

        ws.onmessage = (event) => {
            const raw = event.data;
            try {
                const data = JSON.parse(raw);
                appendEvent('json', data);
            } catch (_) {
                appendEvent('text', raw);
            }
        };

        ws.onerror = () => {
            setWsStatus('disconnected', 'Ошибка соединения');
        };

        ws.onclose = (event) => {
            setWsStatus('disconnected', 'Отключено (код ' + event.code + ')');
            appendEvent('error', 'Соединение закрыто (код ' + event.code + '). Переподключение...');
            scheduleReconnect();
        };
    }

    function scheduleReconnect() {
        if (reconnectTimer) return;
        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            connectWs();
        }, RECONNECT_DELAY);
    }

    function appendEvent(type, payload) {
        const item = document.createElement('div');
        item.className = 'event-item';

        const time = document.createElement('span');
        time.className = 'event-time';
        time.textContent = new Date().toLocaleTimeString();

        let content;
        if (type === 'json') {
            content = document.createElement('span');
            content.className = 'event-json';
            content.textContent = JSON.stringify(payload);
        } else if (type === 'error') {
            content = document.createElement('span');
            content.className = 'event-error';
            content.textContent = payload;
        } else {
            content = document.createElement('span');
            content.className = 'event-text';
            content.textContent = String(payload);
        }

        item.appendChild(time);
        item.appendChild(content);

        // prepend — newest on top
        if (eventsContainer.firstChild) {
            eventsContainer.insertBefore(item, eventsContainer.firstChild);
        } else {
            eventsContainer.appendChild(item);
        }

        // cap to 200 entries
        while (eventsContainer.children.length > 200) {
            eventsContainer.removeChild(eventsContainer.lastChild);
        }
    }

    // --- Utils ---

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function escapeAttr(str) {
        return escapeHtml(str).replace(/'/g, '&#39;');
    }

    // --- Init ---
    fetchImages(1);
    connectWs();
})();
