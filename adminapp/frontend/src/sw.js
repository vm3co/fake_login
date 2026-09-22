// src/sw.js

self.addEventListener('install', () => {
  console.log('[Service Worker] 安裝中...');
  self.skipWaiting(); // 立即啟用新 SW
});

self.addEventListener('activate', (event) => {
  console.log('[Service Worker] 啟用中...');
  // 清理舊的 cache（未來可擴充）
  event.waitUntil(
    caches.keys().then((keyList) => {
      return Promise.all(
        keyList.map((key) => {
          if (key !== 'app-cache-v1') {
            console.log('[Service Worker] 刪除舊 cache', key);
            return caches.delete(key);
          }
        })
      );
    })
  );
});

self.addEventListener('fetch', (event) => {
  // 可選擇使用 Cache First 策略
  event.respondWith(
    caches.match(event.request).then((response) => {
      return (
        response ||
        fetch(event.request).then((res) => {
          // 可以在這裡加 cache 寫入邏輯（未來擴充用）
          return res;
        })
      );
    })
  );
});
