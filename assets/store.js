// Каталог extensions.hypede.xyz: вход, профиль, расширения и темы, публикация
// и модерация. Одна страница, разделы по адресу после «#»:
//   #/extensions, #/themes        каталог
//   #/item/extension/имя          расширение или тема
//   #/user/ник                    профиль автора
//   #/account                     вход, регистрация, свой профиль и свои работы
//   #/submit, #/submit/номер      опубликовать новое или новую версию
//   #/moderate                    очередь проверки (для модераторов)
// Всё, что пришло от пользователей, выводится как текст (textContent),
// никогда как HTML.
'use strict';

const API = window.HYPEDE_API;
const RU = document.documentElement.lang === 'ru';
const T = RU ? {
  catalog: 'Каталог', extensions: 'Расширения', themes: 'Темы', publish: 'Опубликовать', account: 'Аккаунт',
  signIn: 'Войти', signOut: 'Выйти', moderate: 'Проверка', search: 'Поиск…', popular: 'Популярные',
  newest: 'Новые', byName: 'По названию', nothing: 'Пока ничего нет', by: 'автор', downloads: 'скачиваний',
  download: 'Скачать', version: 'Версия', license: 'Лицензия', homepage: 'Сайт', uuid: 'UUID', shell: 'GNOME Shell',
  checksum: 'SHA-256', install: 'Как установить', installExt: 'Скачайте архив и выполните в терминале:',
  installExt2: 'Затем включите расширения GNOME: Настройки → Системные настройки → Службы GNOME → Расширения GNOME.',
  installTheme: 'Скачайте файл темы и откройте его: Настройки → Персонализация → Темы → «Импортировать», или выполните:',
  login: 'Почта или ник', email: 'Почта', password: 'Пароль', passwordHint: 'не меньше 10 символов',
  handle: 'Ник', handleHint: 'латиница, цифры, _ и -, от 3 до 24 символов', displayName: 'Имя',
  bio: 'О себе', bioHint: 'до 500 символов', photo: 'Фото', changePhoto: 'Сменить фото', removePhoto: 'Убрать фото',
  createAccount: 'Создать аккаунт', haveAccount: 'Уже есть аккаунт?', noAccount: 'Ещё нет аккаунта?',
  save: 'Сохранить', saved: 'Сохранено', profile: 'Профиль', myWorks: 'Мои расширения и темы',
  newPassword: 'Новый пароль', currentPassword: 'Текущий пароль', changePassword: 'Сменить пароль',
  pending: 'на проверке', approved: 'опубликовано', rejected: 'отклонено', noteFromMod: 'Модератор:',
  newVersion: 'Загрузить новую версию', edit: 'Изменить', remove: 'Удалить', confirmRemove: 'Удалить насовсем?',
  kind: 'Что публикуете', extension: 'Расширение', theme: 'Тема', file: 'Файл',
  fileExt: 'ZIP-архив расширения GNOME Shell (как от «gnome-extensions pack»): metadata.json и extension.js в корне.',
  fileTheme: 'JSON-файл темы HypeDE (Настройки → Персонализация → Темы → «Экспортировать»).',
  name: 'Название', summary: 'Коротко', summaryHint: 'одна строка, до 140 символов',
  description: 'Описание', descriptionHint: 'что делает, как настроить; до 5000 символов',
  preview: 'Картинка', previewHint: 'снимок экрана, PNG или JPEG; для тем — обязательно',
  homepageHint: 'адрес https:// — исходный код или страница проекта', licenseHint: 'например GPL-3.0',
  terms: 'Я автор или имею право публиковать этот файл. Я понимаю, что его проверят антивирусом и вручную и что вредоносный код приведёт к блокировке.',
  send: 'Отправить на проверку', sending: 'Проверяем…',
  sent: 'Отправлено. Автоматическая проверка пройдена — работа появится в каталоге после ручной проверки.',
  sentRejected: 'Автоматическая проверка не пройдена:', report: 'Что нашла проверка', antivirus: 'Антивирус',
  clean: 'угроз не найдено', unavailable: 'не запускался — проверит человек', warnings: 'Стоит посмотреть',
  noWarnings: 'подозрительных мест нет', approve: 'Одобрить', reject: 'Отклонить', notePlaceholder: 'Пояснение автору',
  queueEmpty: 'Проверять нечего', signInFirst: 'Сначала войдите в аккаунт.', joined: 'С нами с',
  notFound: 'Не найдено', back: 'Назад', versions: 'Версии', files: 'файлов', disclaimerTitle: 'Важно',
  openProfile: 'Открыть профиль', serverDown: 'Каталог сейчас недоступен. Попробуйте позже.',
} : {
  catalog: 'Catalog', extensions: 'Extensions', themes: 'Themes', publish: 'Publish', account: 'Account',
  signIn: 'Sign in', signOut: 'Sign out', moderate: 'Review', search: 'Search…', popular: 'Popular',
  newest: 'Newest', byName: 'By name', nothing: 'Nothing here yet', by: 'by', downloads: 'downloads',
  download: 'Download', version: 'Version', license: 'License', homepage: 'Homepage', uuid: 'UUID', shell: 'GNOME Shell',
  checksum: 'SHA-256', install: 'How to install', installExt: 'Download the archive and run in a terminal:',
  installExt2: 'Then turn on GNOME extensions: Settings → System preferences → GNOME services → GNOME extensions.',
  installTheme: 'Download the theme file and open it: Settings → Personalization → Themes → Import, or run:',
  login: 'Email or nickname', email: 'Email', password: 'Password', passwordHint: 'at least 10 characters',
  handle: 'Nickname', handleHint: 'Latin letters, digits, _ and -, 3 to 24 characters', displayName: 'Name',
  bio: 'About you', bioHint: 'up to 500 characters', photo: 'Photo', changePhoto: 'Change photo', removePhoto: 'Remove photo',
  createAccount: 'Create account', haveAccount: 'Have an account?', noAccount: 'No account yet?',
  save: 'Save', saved: 'Saved', profile: 'Profile', myWorks: 'My extensions and themes',
  newPassword: 'New password', currentPassword: 'Current password', changePassword: 'Change password',
  pending: 'in review', approved: 'published', rejected: 'rejected', noteFromMod: 'Moderator:',
  newVersion: 'Upload a new version', edit: 'Edit', remove: 'Delete', confirmRemove: 'Delete for good?',
  kind: 'What are you publishing', extension: 'Extension', theme: 'Theme', file: 'File',
  fileExt: 'A GNOME Shell extension ZIP (as made by “gnome-extensions pack”): metadata.json and extension.js at the root.',
  fileTheme: 'A HypeDE theme JSON file (Settings → Personalization → Themes → Export).',
  name: 'Name', summary: 'Summary', summaryHint: 'one line, up to 140 characters',
  description: 'Description', descriptionHint: 'what it does, how to set it up; up to 5000 characters',
  preview: 'Picture', previewHint: 'a screenshot, PNG or JPEG; required for themes',
  homepageHint: 'an https:// address — source code or project page', licenseHint: 'for example GPL-3.0',
  terms: 'I made this or have the right to publish it. I understand it will be checked by an antivirus and by a person, and that malicious code gets the account blocked.',
  send: 'Send for review', sending: 'Checking…',
  sent: 'Sent. The automatic check passed — it appears in the catalog after a person reviews it.',
  sentRejected: 'The automatic check failed:', report: 'What the check found', antivirus: 'Antivirus',
  clean: 'no threats found', unavailable: 'did not run — a person will check', warnings: 'Worth a look',
  noWarnings: 'nothing suspicious', approve: 'Approve', reject: 'Reject', notePlaceholder: 'Note for the author',
  queueEmpty: 'Nothing to review', signInFirst: 'Sign in first.', joined: 'Joined',
  notFound: 'Not found', back: 'Back', versions: 'Versions', files: 'files', disclaimerTitle: 'Important',
  openProfile: 'Open profile', serverDown: 'The catalog is not available right now. Try again later.',
};
// Ошибки API приходят по-английски — частые переводятся.
const ERRORS_RU = {
  'sign in first': 'Сначала войдите в аккаунт',
  'wrong email, nickname or password': 'Неверная почта, ник или пароль',
  'enter a valid email': 'Введите правильный адрес почты',
  'the password must be at least 10 characters': 'Пароль должен быть не короче 10 символов',
  'the nickname must be 3–24 Latin letters, digits, _ or -': 'Ник — от 3 до 24 латинских букв, цифр, _ или -',
  'this email is already registered': 'Эта почта уже зарегистрирована',
  'this nickname is taken': 'Этот ник занят',
  'too many requests, try again later': 'Слишком много попыток, попробуйте позже',
  'you have to accept the terms': 'Нужно принять условия',
  'this is not a zip archive': 'Это не ZIP-архив',
  'the current password is wrong': 'Текущий пароль неверный',
  'an extension with this uuid is already published by someone else': 'Расширение с таким uuid уже опубликовал другой автор',
  'the homepage must be an https:// address': 'Сайт должен начинаться с https://',
  'tell the author why': 'Напишите автору причину',
};

const app = document.getElementById('app');
let me = null;
let disclaimer = null;

// ------------------------------------------------------------------ помощники

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key.startsWith('on')) el.addEventListener(key.slice(2), value);
    else if (key === 'text') el.textContent = value;
    else el.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

async function api(path, { method = 'GET', json, form } = {}) {
  const options = { method, credentials: 'include', headers: {} };
  if (method !== 'GET') options.headers['X-HypeDE'] = '1';
  if (json !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(json);
  }
  if (form) options.body = form;
  let response;
  try {
    response = await fetch(API + path, options);
  } catch {
    throw new Error(T.serverDown);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof data.detail === 'string' ? data.detail : (data.error || response.statusText);
    throw new Error(RU ? (ERRORS_RU[message] || message) : message);
  }
  return data;
}

function avatar(user, size = '') {
  if (user && user.avatar) return h('img', { class: `avatar ${size}`, src: user.avatar, alt: '' });
  const letter = ((user && (user.displayName || user.handle)) || '?').trim().charAt(0).toUpperCase();
  return h('span', { class: `avatar ${size}`, 'aria-hidden': 'true' }, letter);
}

function byline(author) {
  if (!author) return null;
  return h('span', { class: 'byline' }, avatar(author, 'small'),
    h('a', { href: `#/user/${encodeURIComponent(author.handle)}` }, author.displayName),
    h('span', {}, '@' + author.handle));
}

function date(seconds) {
  return seconds ? new Date(seconds * 1000).toLocaleDateString(RU ? 'ru-RU' : 'en-US',
    { year: 'numeric', month: 'long', day: 'numeric' }) : '';
}

function notice(text, kind = '') {
  return h('div', { class: `notice ${kind}`, role: kind === 'error' ? 'alert' : 'status' }, text);
}

function statusChip(status) {
  return h('span', { class: `status ${status}` }, T[status] || status);
}

function spinner() { return h('div', { class: 'spinner', role: 'progressbar' }); }

function show(...nodes) {
  app.replaceChildren(topbar(), ...nodes);
  window.scrollTo({ top: 0 });
}

function field(label, input, hint) {
  return h('label', {}, label, input, hint ? h('span', { class: 'hint' }, hint) : null);
}

function disclaimerBox() {
  if (!disclaimer) return null;
  return notice([h('strong', {}, T.disclaimerTitle + ': '), disclaimer[RU ? 'ru' : 'en']], 'warn');
}

// ------------------------------------------------------------------ шапка

function topbar() {
  const route = location.hash || '#/extensions';
  const link = (href, text) => h('a', { class: 'navlink' + (route.startsWith(href) ? ' active' : ''), href }, text);
  const other = RU ? location.pathname.replace(/^\/ru\//, '/') : '/ru' + location.pathname;
  return h('header', { class: 'topbar' },
    h('a', { class: 'brand', href: RU ? '/ru/' : '/' },
      h('img', { src: '/assets/img/logo.svg', alt: '', width: 32, height: 32 }), 'HypeDE'),
    h('nav', { 'aria-label': T.catalog },
      link('#/extensions', T.extensions), link('#/themes', T.themes), link('#/submit', T.publish),
      me && me.moderator ? link('#/moderate', T.moderate) : null,
      me ? h('a', { class: 'navlink me-chip' + (route.startsWith('#/account') ? ' active' : ''), href: '#/account' },
        avatar(me, 'small'), me.displayName) : link('#/account', T.signIn),
      h('a', { class: 'navlink', href: other + location.hash, hreflang: RU ? 'en' : 'ru' }, RU ? 'English' : 'Русский')));
}

// ------------------------------------------------------------------ каталог

async function browse(kind) {
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  const q = params.get('q') || '', sort = params.get('sort') || 'popular';
  const grid = h('div', { class: 'grid' }, spinner());
  const search = h('input', { type: 'search', placeholder: T.search, value: q, 'aria-label': T.search });
  const order = h('select', { 'aria-label': T.popular },
    ...[['popular', T.popular], ['new', T.newest], ['name', T.byName]].map(([v, t]) =>
      h('option', { value: v, selected: v === sort }, t)));
  const go = () => {
    const query = new URLSearchParams({ q: search.value.trim(), sort: order.value });
    location.hash = `#/${kind === 'theme' ? 'themes' : 'extensions'}?${query}`;
  };
  let timer = 0;
  search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(go, 400); });
  order.addEventListener('change', go);
  show(
    h('div', { class: 'filters' },
      h('div', { class: 'tabs', role: 'tablist' },
        h('button', { class: kind === 'extension' ? 'active' : '', role: 'tab', onclick: () => { location.hash = '#/extensions'; } }, T.extensions),
        h('button', { class: kind === 'theme' ? 'active' : '', role: 'tab', onclick: () => { location.hash = '#/themes'; } }, T.themes)),
      search, order),
    disclaimerBox(),
    grid);
  if (q) { search.focus(); search.setSelectionRange(q.length, q.length); }
  try {
    const data = await api(`/api/items?${new URLSearchParams({ kind, q, sort })}`);
    grid.replaceChildren(...(data.items.length ? data.items.map(card) : [h('p', { class: 'empty' }, T.nothing)]));
  } catch (e) {
    grid.replaceChildren(notice(e.message, 'error'));
  }
}

function card(item) {
  return h('a', { class: 'card', href: `#/item/${item.kind}/${encodeURIComponent(item.slug)}` },
    item.preview ? h('img', { class: 'shot', src: item.preview, alt: '', loading: 'lazy' }) : h('div', { class: 'shot' }),
    h('div', { class: 'body' },
      h('h3', {}, item.name),
      h('p', { class: 'summary' }, item.summary),
      h('span', { class: 'byline' }, avatar(item.author, 'small'), item.author ? item.author.displayName : '',
        ` · ${item.downloads} ${T.downloads}`)));
}

async function itemPage(kind, slug) {
  show(spinner());
  let item;
  try {
    item = await api(`/api/items/${kind}/${encodeURIComponent(slug)}`);
  } catch (e) {
    show(notice(e.message === 'not found' ? T.notFound : e.message, 'error'));
    return;
  }
  const v = item.version;
  const facts = h('dl', { class: 'facts' });
  const fact = (k, val) => { if (val) facts.append(h('dt', {}, k), h('dd', {}, val)); };
  fact(T.version, v ? String(v.meta.version ?? v.number) : '—');
  fact(T.license, item.license);
  if (item.homepage) facts.append(h('dt', {}, T.homepage), h('dd', {}, h('a', { href: item.homepage, rel: 'nofollow noopener', target: '_blank' }, item.homepage)));
  fact(T.uuid, item.uuid);
  if (v && v.meta['shell-version']) fact(T.shell, v.meta['shell-version'].join(', '));
  if (v) fact(T.checksum, v.sha256);
  const file = kind === 'extension' ? `${item.uuid || item.slug}.zip` : `${item.slug}.json`;
  const install = kind === 'extension'
    ? [h('p', {}, T.installExt), h('div', { class: 'code-line' }, `gnome-extensions install --force ~/Downloads/${file}`), h('p', {}, T.installExt2)]
    : [h('p', {}, T.installTheme), h('div', { class: 'code-line' }, `hypede-theme import ~/Downloads/${file}`)];
  show(
    h('div', { class: 'item-head' },
      item.preview ? h('img', { class: 'shot', src: item.preview, alt: '' }) : h('div', { class: 'shot' }),
      h('div', { class: 'panel' },
        h('span', { class: 'eyebrow' }, kind === 'extension' ? T.extension : T.theme),
        h('h1', { style: 'font-size: var(--step-2)' }, item.name),
        byline(item.author),
        h('p', {}, item.summary),
        disclaimerBox(),
        v ? h('a', { class: 'btn primary', href: v.download, download: file }, T.download) : statusChip('pending'),
        h('span', { class: 'byline' }, `${item.downloads} ${T.downloads}`))),
    item.description ? h('div', { class: 'panel' }, h('h2', {}, T.description), h('p', { class: 'description' }, item.description)) : null,
    h('div', { class: 'two' },
      h('div', { class: 'panel' }, h('h2', {}, T.install), ...install),
      h('div', { class: 'panel' }, facts)),
    item.versions ? versionsPanel(item) : null);
}

function versionsPanel(item) {
  return h('div', { class: 'panel' }, h('h2', {}, T.versions),
    h('div', { class: 'list' }, ...item.versions.map(v => h('div', { class: 'list-item' },
      h('div', { class: 'row' }, h('strong', {}, `#${v.number}`), statusChip(v.status), h('span', { class: 'byline' }, date(v.created)),
        h('a', { href: `${API}/api/items/${item.id}/download?version=${v.number}` }, T.download)),
      v.note ? h('p', {}, T.noteFromMod + ' ' + v.note) : null,
      reportView(v.report)))));
}

function reportView(report) {
  if (!report || !report.kind) return null;
  const av = report.antivirus || 'unavailable';
  const avText = av === 'clean' ? T.clean : av === 'unavailable' ? T.unavailable : av;
  const warnings = report.warnings || [];
  return h('details', {},
    h('summary', {}, `${T.report}: ${T.antivirus} — ${avText}; ${warnings.length ? `${T.warnings}: ${warnings.length}` : T.noWarnings}`),
    (report.errors || []).length ? h('ul', { class: 'warnings' }, ...report.errors.map(e => h('li', {}, e))) : null,
    warnings.length ? h('ul', { class: 'warnings' }, ...warnings.map(w => h('li', {},
      `${w.file}${w.line ? ':' + w.line : ''} — ${w.what} `, w.code ? h('code', {}, w.code) : null))) : null);
}

async function userPage(handle) {
  show(spinner());
  try {
    const data = await api(`/api/users/${encodeURIComponent(handle)}`);
    const u = data.user;
    show(
      h('div', { class: 'panel profile' }, avatar(u, 'large'),
        h('div', { style: 'display: grid; gap: 6px' }, h('h1', { style: 'font-size: var(--step-2)' }, u.displayName),
          h('span', { class: 'byline' }, '@' + u.handle + ' · ' + T.joined + ' ' + date(u.joined)),
          u.bio ? h('p', { class: 'bio' }, u.bio) : null)),
      data.items.length ? h('div', { class: 'grid' }, ...data.items.map(card)) : h('p', { class: 'empty' }, T.nothing));
  } catch (e) {
    show(notice(e.message === 'no such user' ? T.notFound : e.message, 'error'));
  }
}

// ------------------------------------------------------------------ аккаунт

function signInView() {
  const message = h('div');
  const login = h('input', { type: 'text', autocomplete: 'username', required: true });
  const password = h('input', { type: 'password', autocomplete: 'current-password', required: true });
  const signIn = h('form', { class: 'form panel', onsubmit: async e => {
    e.preventDefault();
    try {
      me = await api('/api/auth/login', { method: 'POST', json: { login: login.value, password: password.value } });
      route();
    } catch (err) { message.replaceChildren(notice(err.message, 'error')); }
  } }, h('h2', {}, T.signIn), field(T.login, login), field(T.password, password), h('button', { class: 'btn primary', type: 'submit' }, T.signIn));

  const msg2 = h('div');
  const email = h('input', { type: 'email', autocomplete: 'email', required: true });
  const handle = h('input', { type: 'text', autocomplete: 'nickname', pattern: '[a-z0-9_\\-]{3,24}', required: true });
  const display = h('input', { type: 'text', autocomplete: 'name', maxlength: 60 });
  const pass = h('input', { type: 'password', autocomplete: 'new-password', minlength: 10, required: true });
  const register = h('form', { class: 'form panel', onsubmit: async e => {
    e.preventDefault();
    try {
      me = await api('/api/auth/register', { method: 'POST', json: {
        email: email.value, handle: handle.value.toLowerCase(), displayName: display.value, password: pass.value } });
      route();
    } catch (err) { msg2.replaceChildren(notice(err.message, 'error')); }
  } }, h('h2', {}, T.createAccount), field(T.email, email), field(T.handle, handle, T.handleHint),
    field(T.displayName, display), field(T.password, pass, T.passwordHint), h('button', { class: 'btn primary', type: 'submit' }, T.createAccount));
  show(h('div', { class: 'two' }, h('div', {}, signIn, message), h('div', {}, register, msg2)));
}

async function accountPage() {
  if (!me) { signInView(); return; }
  const status = h('div');
  const display = h('input', { type: 'text', value: me.displayName, maxlength: 60 });
  const handle = h('input', { type: 'text', value: me.handle, pattern: '[a-z0-9_\\-]{3,24}' });
  const bio = h('textarea', { maxlength: 500 }, me.bio || '');
  const photoBox = h('div', { class: 'row' }, avatar(me, 'large'));
  const photo = h('input', { type: 'file', accept: 'image/png,image/jpeg,image/webp', hidden: true, onchange: async () => {
    if (!photo.files[0]) return;
    const form = new FormData();
    form.append('file', photo.files[0]);
    try {
      const r = await api('/api/me/avatar', { method: 'POST', form });
      me.avatar = r.avatar;
      accountPage();
    } catch (e) { status.replaceChildren(notice(e.message, 'error')); }
  } });
  photoBox.append(h('div', { class: 'row' },
    h('button', { class: 'btn', type: 'button', onclick: () => photo.click() }, T.changePhoto),
    me.avatar ? h('button', { class: 'btn flat', type: 'button', onclick: async () => {
      await api('/api/me/avatar', { method: 'DELETE' });
      me.avatar = '';
      accountPage();
    } }, T.removePhoto) : null, photo));

  const profileForm = h('form', { class: 'form', onsubmit: async e => {
    e.preventDefault();
    try {
      me = await api('/api/me', { method: 'PATCH', json: { displayName: display.value, handle: handle.value.toLowerCase(), bio: bio.value } });
      status.replaceChildren(notice(T.saved));
      app.querySelector('header').replaceWith(topbar());
    } catch (err) { status.replaceChildren(notice(err.message, 'error')); }
  } }, photoBox, field(T.displayName, display), field(T.handle, handle, T.handleHint), field(T.bio, bio, T.bioHint),
  h('div', { class: 'row' }, h('button', { class: 'btn primary', type: 'submit' }, T.save),
    h('a', { class: 'btn flat', href: `#/user/${encodeURIComponent(me.handle)}` }, T.openProfile)), status);

  const current = h('input', { type: 'password', autocomplete: 'current-password' });
  const next = h('input', { type: 'password', autocomplete: 'new-password', minlength: 10 });
  const passStatus = h('div');
  const passwordForm = h('form', { class: 'form', onsubmit: async e => {
    e.preventDefault();
    try {
      await api('/api/me', { method: 'PATCH', json: { currentPassword: current.value, password: next.value } });
      passStatus.replaceChildren(notice(T.saved));
      current.value = next.value = '';
    } catch (err) { passStatus.replaceChildren(notice(err.message, 'error')); }
  } }, field(T.currentPassword, current), field(T.newPassword, next, T.passwordHint),
  h('button', { class: 'btn', type: 'submit' }, T.changePassword), passStatus);

  const works = h('div', { class: 'list' }, spinner());
  show(
    h('div', { class: 'two' },
      h('section', { class: 'panel' }, h('h2', {}, T.profile), profileForm),
      h('section', { class: 'panel' }, h('h2', {}, T.myWorks), works,
        h('a', { class: 'btn primary', href: '#/submit' }, T.publish))),
    h('section', { class: 'panel' }, h('h2', {}, T.changePassword), passwordForm),
    h('div', {}, h('button', { class: 'btn flat', onclick: async () => {
      await api('/api/auth/logout', { method: 'POST' });
      me = null;
      location.hash = '#/extensions';
    } }, T.signOut)));
  try {
    const data = await api('/api/my/items');
    works.replaceChildren(...(data.items.length ? data.items.map(myWork) : [h('p', { class: 'empty' }, T.nothing)]));
  } catch (e) { works.replaceChildren(notice(e.message, 'error')); }
}

function myWork(item) {
  const last = (item.versions || [])[0];
  return h('div', { class: 'list-item' },
    h('div', { class: 'row' }, h('a', { href: `#/item/${item.kind}/${encodeURIComponent(item.slug)}` }, h('strong', {}, item.name)),
      h('span', { class: 'byline' }, item.kind === 'extension' ? T.extension : T.theme),
      last ? statusChip(last.status) : null),
    last && last.note ? h('p', {}, T.noteFromMod + ' ' + last.note) : null,
    h('div', { class: 'row' },
      h('a', { class: 'btn', href: `#/submit/${item.id}` }, T.newVersion),
      h('button', { class: 'btn danger', onclick: async () => {
        if (!confirm(T.confirmRemove)) return;
        await api(`/api/items/${item.id}`, { method: 'DELETE' });
        accountPage();
      } }, T.remove)));
}

// ------------------------------------------------------------------ публикация

function submitPage(itemId) {
  if (!me) { show(notice(T.signInFirst), h('a', { class: 'btn primary', href: '#/account' }, T.signIn)); return; }
  const result = h('div');
  let kind = 'extension';
  const fileHint = h('span', { class: 'hint' }, T.fileExt);
  const file = h('input', { type: 'file', accept: '.zip,application/zip', required: true });
  const kinds = h('div', { class: 'tabs', role: 'tablist' });
  const setKind = k => {
    kind = k;
    fileHint.textContent = k === 'extension' ? T.fileExt : T.fileTheme;
    file.accept = k === 'extension' ? '.zip,application/zip' : '.json,application/json';
    preview.required = k === 'theme';
    kinds.querySelectorAll('button').forEach(b => b.classList.toggle('active', b.dataset.kind === k));
  };
  for (const k of ['extension', 'theme'])
    kinds.append(h('button', { type: 'button', role: 'tab', 'data-kind': k, class: k === kind ? 'active' : '', onclick: () => setKind(k) }, T[k]));
  const name = h('input', { type: 'text', maxlength: 60, required: !itemId });
  const summary = h('input', { type: 'text', maxlength: 140, required: !itemId });
  const description = h('textarea', { maxlength: 5000 });
  const license = h('input', { type: 'text', maxlength: 60, placeholder: 'GPL-3.0' });
  const homepage = h('input', { type: 'url', placeholder: 'https://github.com/…' });
  const preview = h('input', { type: 'file', accept: 'image/png,image/jpeg,image/webp' });
  const terms = h('input', { type: 'checkbox', required: true });
  const send = h('button', { class: 'btn primary', type: 'submit' }, T.send);

  const form = h('form', { class: 'form', onsubmit: async e => {
    e.preventDefault();
    const data = new FormData();
    data.append('accept_terms', terms.checked ? 'true' : '');
    data.append('file', file.files[0]);
    if (!itemId) {
      for (const [k, v] of [['kind', kind], ['name', name.value], ['summary', summary.value], ['description', description.value],
        ['license', license.value], ['homepage', homepage.value]]) data.append(k, v);
      if (preview.files[0]) data.append('preview', preview.files[0]);
    }
    send.disabled = true;
    send.textContent = T.sending;
    try {
      const r = await api(itemId ? `/api/items/${itemId}/versions` : '/api/items', { method: 'POST', form: data });
      const version = r.version || r;
      result.replaceChildren(version.status === 'rejected'
        ? notice([T.sentRejected + ' ', version.note], 'error')
        : notice(T.sent), reportView(version.report));
      if (version.status !== 'rejected') form.reset();
    } catch (err) {
      result.replaceChildren(notice(err.message, 'error'));
    }
    send.disabled = false;
    send.textContent = T.send;
  } },
  itemId ? null : field(T.kind, kinds),
  h('label', {}, T.file, file, fileHint),
  itemId ? null : [field(T.name, name), field(T.summary, summary, T.summaryHint), field(T.description, description, T.descriptionHint),
    field(T.preview, preview, T.previewHint), field(T.homepage, homepage, T.homepageHint), field(T.license, license, T.licenseHint)],
  disclaimerBox(),
  h('label', { class: 'terms' }, terms, h('span', {}, T.terms)),
  h('div', {}, send), result);
  show(h('section', { class: 'panel' }, h('h2', {}, itemId ? T.newVersion : T.publish), form));
}

// ------------------------------------------------------------------ модерация

async function moderatePage() {
  if (!me || !me.moderator) { show(notice(T.signInFirst)); return; }
  show(spinner());
  const data = await api('/api/mod/queue').catch(e => ({ error: e.message }));
  if (data.error) { show(notice(data.error, 'error')); return; }
  if (!data.queue.length) { show(h('p', { class: 'empty' }, T.queueEmpty)); return; }
  show(h('div', { class: 'list' }, ...data.queue.map(item => {
    const v = item.pending;
    const note = h('input', { type: 'text', placeholder: T.notePlaceholder, maxlength: 1000 });
    const out = h('div');
    const decide = async decision => {
      try {
        await api(`/api/mod/versions/${v.id}/${decision}`, { method: 'POST', json: { note: note.value } });
        moderatePage();
      } catch (e) { out.replaceChildren(notice(e.message, 'error')); }
    };
    return h('div', { class: 'panel' },
      h('div', { class: 'row' }, h('strong', {}, item.name), h('span', { class: 'byline' }, `${T[item.kind]} · #${v.number} · ${date(v.created)}`), byline(item.author)),
      h('p', {}, item.summary),
      item.preview ? h('img', { src: item.preview, alt: '', style: 'max-width: 360px; border-radius: 12px' }) : null,
      item.homepage ? h('a', { href: item.homepage, rel: 'nofollow noopener', target: '_blank' }, item.homepage) : null,
      item.description ? h('details', {}, h('summary', {}, T.description), h('p', { class: 'description' }, item.description)) : null,
      item.uuid ? h('p', { class: 'byline' }, 'UUID: ' + item.uuid) : null,
      reportView(v.report),
      h('div', { class: 'row' },
        h('a', { class: 'btn', href: `${API}/api/items/${item.id}/download?version=${v.number}` }, T.download),
        note,
        h('button', { class: 'btn primary', onclick: () => decide('approve') }, T.approve),
        h('button', { class: 'btn danger', onclick: () => decide('reject') }, T.reject)),
      out);
  })));
}

// ------------------------------------------------------------------ маршруты

function route() {
  const [path] = (location.hash || '#/extensions').slice(1).split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  switch (parts[0]) {
    case 'themes': return browse('theme');
    case 'item': return itemPage(parts[1], parts[2]);
    case 'user': return userPage(parts[1]);
    case 'account': return accountPage();
    case 'submit': return submitPage(parts[1] ? Number(parts[1]) : null);
    case 'moderate': return moderatePage();
    default: return browse('extension');
  }
}

window.addEventListener('hashchange', route);
(async () => {
  app.replaceChildren(topbar(), spinner());
  const [who, info] = await Promise.all([api('/api/me').catch(() => null), api('/api/info').catch(() => null)]);
  me = who && who.handle ? who : null;
  disclaimer = info ? info.disclaimer : {
    en: 'Extensions and themes are made by users. HypeDE is not responsible for your system: you install them at your own risk.',
    ru: 'Расширения и темы создают пользователи. HypeDE не несёт ответственности за вашу систему: устанавливаете вы их на свой риск.',
  };
  route();
})();
