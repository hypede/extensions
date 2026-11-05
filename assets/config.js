// Адрес API каталога (сервис из server/). Для проверки на своём компьютере:
//   localStorage.hypedeApi = 'http://127.0.0.1:8080'
window.HYPEDE_API = (() => {
  try {
    if (localStorage.hypedeApi) return localStorage.hypedeApi;
  } catch {}
  return 'https://api.extensions.hypede.xyz';
})();
