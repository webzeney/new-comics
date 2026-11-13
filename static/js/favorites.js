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
var DOWS = ['日', '月', '火', '水', '木', '金', '土'];
function dateLabel(d, today) {
if (!d) return '発売日未定';
if (d <= today) return '発売中';
var y = Number(d.slice(0, 4));
var m = Number(d.slice(5, 7));
var day = Number(d.slice(8, 10));
return m + '/' + day + '（' + DOWS[new Date(Date.UTC(y, m - 1, day)).getUTCDay()] + '）発売';
}

function encodeFavs(list) {
var json = JSON.stringify(list.map(function (f) { return [f.id, f.name]; }));
var bin = Array.prototype.map.call(new TextEncoder().encode(json), function (c) { return String.fromCharCode(c); }).join('');
return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function decodeFavs(text) {
try {
var bin = atob(text.replace(/-/g, '+').replace(/_/g, '/'));
var bytes = new Uint8Array(bin.length);
for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
var list = JSON.parse(new TextDecoder().decode(bytes));
return list.filter(function (x) { return Array.isArray(x) && /^\d+$/.test(String(x[0])) && typeof x[1] === 'string'; }).map(function (x) { return { id: Number(x[0]), name: x[1].slice(0, 100), url: '/series/' + Number(x[0]) + '/' }; });
} catch (e) { return []; }
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
if (!item.e || item.eo) $('[data-field="ebook"]', li).remove();
if (!item.eo) $('[data-field="ebookonly"]', li).remove();
var change = $('[data-field="change"]', li);
if (item.ch) { change.textContent = item.ch.k === '日付決定' ? '発売日決定' : '発売日変更'; if (item.ch.k === '日付決定') change.className = 'kind kind--fixed'; } else { change.remove(); }
$$('[data-store]', li).forEach(function (a) { var u = item.s && item.s[a.dataset.store]; if (u) { a.href = u; } else { a.remove(); } });
if (window.NewComicsReserve) window.NewComicsReserve(li, item.d);
var pick = $('[data-cart-pick]', li);
var asin = ((item.s && item.s.amazon) || '').match(/\/dp\/([0-9A-Z]{10})/);
if (asin) { pick.value = asin[1]; pick.setAttribute('aria-label', (item.ia || item.t) + 'をカートに入れる本に選ぶ'); } else { pick.parentNode.remove(); }
return li;
}

function render() {
var favs = load();
$$('.fav_chip', listBox).forEach(function (el) { el.remove(); });
listBox.hidden = favs.length === 0;
updateTransfer();
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
var changesBox = $('[data-fav-changes]');
var changesList = $('[data-fav-changes-list]');
changesList.textContent = '';
found.filter(function (it) { return it.ch; }).forEach(function (it) {
var li = document.createElement('li');
li.className = 'updates__item';
var k = document.createElement('span');
k.className = 'kind ' + (it.ch.k === '日付決定' ? 'kind--fixed' : 'kind--change');
k.textContent = it.ch.k === '日付決定' ? '発売日の決定' : '発売日の変更';
var a = document.createElement('a');
a.className = 'updates__link';
a.href = root + it.u.replace(/^\.\.\//, '');
a.textContent = it.t;
var d = document.createElement('span');
d.className = 'updates__detail';
d.textContent = it.ch.t + '（' + it.ch.at + 'に更新）';
li.appendChild(k); li.appendChild(a); li.appendChild(d);
changesList.appendChild(li);
});
changesBox.hidden = !changesList.children.length;
count.textContent = found.length + '点';
$('[data-fav-cart]').hidden = !$('[data-cart-pick]', booksBox);
document.dispatchEvent(new Event('cart:refresh'));
empty.hidden = found.length > 0;
empty.textContent = favs.length ? 'お気に入りの作品の新刊は、今のところありません。' : 'お気に入りに登録した作品は、まだありません。';
}

window.addEventListener('hashchange', function () { if (/^#import=/.test(location.hash)) location.reload(); });
var importBox = $('[data-fav-import]');
var incoming = /^#import=([A-Za-z0-9_-]+)$/.test(location.hash) ? decodeFavs(location.hash.slice(8)) : [];
function clearHash() { history.replaceState(null, '', location.pathname + location.search); }
if (incoming.length) {
var have = load().map(function (f) { return String(f.id); });
var adding = incoming.filter(function (f) { return have.indexOf(String(f.id)) === -1; });
$('[data-fav-import-text]').textContent = adding.length
? '引き継ぎ用のアドレスから開きました。' + adding.length + '作品（' + adding.slice(0, 3).map(function (f) { return f.name; }).join('、') + (adding.length > 3 ? 'など' : '') + '）を、この端末のお気に入りに追加しますか？'
: '引き継ぎ用のアドレスの作品は、すべてこの端末のお気に入りに登録されています。';
$('[data-fav-import-ok]').hidden = !adding.length;
importBox.hidden = false;
$('[data-fav-import-ok]').addEventListener('click', function () { save(load().concat(adding)); importBox.hidden = true; clearHash(); render(); });
$('[data-fav-import-cancel]').addEventListener('click', function () { importBox.hidden = true; clearHash(); });
}

var transfer = $('[data-fav-transfer]');
var transferBody = $('#fav-transfer-body');
var transferOpen = $('[data-fav-transfer-open]');
var transferUrl = $('[data-fav-transfer-url]');
function updateTransfer() {
var favs = load();
transfer.hidden = favs.length === 0;
if (!favs.length) { transferBody.hidden = true; transferOpen.setAttribute('aria-expanded', 'false'); return; }
transferUrl.value = location.origin + location.pathname + '#import=' + encodeFavs(favs);
if (!transferBody.hidden) drawQr();
}
function drawQr() {
var box = $('[data-fav-transfer-qr]');
var draw = function () {
var qr = window.qrcode(0, 'L');
qr.addData(transferUrl.value, 'Byte');
qr.make();
box.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true, alt: '引き継ぎ用のアドレスのQRコード' });
};
if (window.qrcode) { draw(); return; }
var s = document.createElement('script');
s.src = root + 'assets/js/qrcode.min.js';
s.onload = draw;
document.head.appendChild(s);
}
transferOpen.addEventListener('click', function () {
var open = transferBody.hidden;
transferBody.hidden = !open;
transferOpen.setAttribute('aria-expanded', open ? 'true' : 'false');
if (open) drawQr();
});
$('[data-fav-transfer-copy]').addEventListener('click', function (e) {
var b = e.currentTarget;
var done = function () { b.textContent = 'コピーしました'; setTimeout(function () { b.textContent = 'コピー'; }, 2000); };
if (navigator.clipboard) { navigator.clipboard.writeText(transferUrl.value).then(done, function () { transferUrl.select(); }); } else { transferUrl.select(); }
});

render();
fetch(root + 'search/index.json').then(function (r) { return r.json(); }).then(function (data) { items = data.items || []; render(); }).catch(function () {});
});
})();
