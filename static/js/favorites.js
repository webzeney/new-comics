/* お気に入りページ：登録した作品の新刊を表示する */
(function () {
var $ = function (s, r) { return (r || document).querySelector(s); };
var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
var KEY = 'nc_favorites';

function load() {
try { return JSON.parse(localStorage.getItem(KEY) || '[]') || []; } catch (e) { return []; }
}
function save(list) {
try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) {}
}
function todayJst() {
var t = new Date(Date.now() + 9 * 3600 * 1000);
return t.toISOString().slice(0, 10);
}
function dateLabel(d, today) {
if (!d) return '発売日未定';
if (d <= today) return '発売中';
var p = d.split('-');
return Number(p[1]) + '/' + Number(p[2]) + ' 発売';
}

document.addEventListener('DOMContentLoaded', function () {
var listBox = $('[data-fav-list]');
var booksBox = $('[data-fav-books]');
var empty = $('[data-fav-empty]');
var count = $('[data-fav-count]');
var tpl = $('#fav-row-template');
var root = document.querySelector('link[rel="stylesheet"][href*="assets/css"]').getAttribute('href').replace(/assets\/css\/.*$/, '');
var items = null;

function renderRow(item, today) {
var li = tpl.content.firstElementChild.cloneNode(true);
var url = root + item.u.replace(/^\.\.\//, '');
$$('a[data-book-url]', li).forEach(function (a) { a.href = url; });
var date = $('[data-field="date"]', li);
var label = dateLabel(item.d, today);
date.textContent = label;
date.classList.add(label === '発売中' ? 'badge--onsale' : 'badge--date');
$('[data-field="pub"]', li).textContent = item.p;
$('[data-field="title"]', li).textContent = item.t;
var cover = $('.bookrow__image', li);
if (cover && item.i) { var img = document.createElement('img'); img.src = item.i; img.alt = item.ia || ''; img.className = 'cover_photo'; img.loading = 'lazy'; cover.textContent = ''; cover.appendChild(img); }
$('[data-field="meta"]', li).textContent = item.m;
if (!item.e) $('[data-field="ebook"]', li).remove();
$$('[data-store]', li).forEach(function (a) { var u = item.s && item.s[a.dataset.store]; if (u) { a.href = u; } else { a.remove(); } });
return li;
}

function render() {
var favs = load();
$$('.fav_chip', listBox).forEach(function (el) { el.remove(); });
listBox.hidden = favs.length === 0;
favs.forEach(function (f) {
var wrap = document.createElement('span');
wrap.className = 'fav_chip';
var a = document.createElement('a');
a.href = f.url;
a.className = 'fav_chip__link';
a.textContent = f.name;
var x = document.createElement('button');
x.type = 'button';
x.className = 'fav_chip__remove';
x.setAttribute('aria-label', f.name + 'をお気に入りから外す');
x.textContent = '×';
x.addEventListener('click', function () {
save(load().filter(function (g) { return String(g.id) !== String(f.id); }));
render();
});
wrap.appendChild(a);
wrap.appendChild(x);
listBox.appendChild(wrap);
});
booksBox.textContent = '';
if (!items) return;
var ids = favs.map(function (f) { return String(f.id); });
var today = todayJst();
var since = new Date(Date.now() + 9 * 3600 * 1000 - 30 * 86400 * 1000).toISOString().slice(0, 10);
var found = items.filter(function (it) { return it.sr != null && ids.indexOf(String(it.sr)) !== -1 && (!it.d || it.d >= since); });
found.sort(function (a, b) { return (a.d || '9999') < (b.d || '9999') ? -1 : (a.d || '9999') > (b.d || '9999') ? 1 : 0; });
found.forEach(function (it) { booksBox.appendChild(renderRow(it, today)); });
count.textContent = found.length + '点';
empty.hidden = found.length > 0;
empty.textContent = favs.length ? 'お気に入りの作品の新刊は、今のところありません。' : 'お気に入りに登録した作品は、まだありません。';
}

render();
fetch(root + 'search/index.json').then(function (r) { return r.json(); }).then(function (data) { items = data.items || []; render(); }).catch(function () {});
});
})();
