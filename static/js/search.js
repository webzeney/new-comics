(function () {
'use strict';

var PER_PAGE = 10;
var DOWS = ['日', '月', '火', '水', '木', '金', '土'];

function $(sel, root) { return (root || document).querySelector(sel); }
function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

function normalize(text) {
return (text || '').normalize('NFKC').toLowerCase().replace(/\s+/g, '');
}

function readParams() {
var p = new URLSearchParams(location.search);
return {
q: p.get('q') || '',
pub: p.get('pub') || '',
label: p.get('label') || '',
month: p.get('month') || '',
ebook: p.get('ebook') === '1',
sort: p.get('sort') === 'added' ? 'added' : 'date',
page: Math.max(1, parseInt(p.get('page') || '1', 10) || 1)
};
}

function writeParams(state) {
var p = new URLSearchParams();
if (state.q) p.set('q', state.q);
if (state.pub) p.set('pub', state.pub);
if (state.label) p.set('label', state.label);
if (state.month) p.set('month', state.month);
if (state.ebook) p.set('ebook', '1');
if (state.sort !== 'date') p.set('sort', state.sort);
if (state.page > 1) p.set('page', String(state.page));
var qs = p.toString();
history.replaceState(null, '', qs ? '?' + qs : location.pathname);
}

function dateLabel(item, today) {
if (!item.d) return '発売日未定';
if (item.d <= today) return '発売中';
var y = Number(item.d.slice(0, 4));
var m = Number(item.d.slice(5, 7));
var d = Number(item.d.slice(8, 10));
return m + '/' + d + '（' + DOWS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()] + '）発売';
}

function todayJst() {
var now = new Date(Date.now() + 9 * 3600 * 1000);
return now.toISOString().slice(0, 10);
}

window.NewComicsSearch = function () {
var root = $('[data-search]');
if (!root) return;
var form = $('[data-search-form]');
var state = readParams();
var items = null;
var rowTemplate = $('#search-row-template');
var today = todayJst();

form.q.value = state.q;
form.pub.value = state.pub;
form.label.value = state.label;
form.month.value = state.month;
form.ebook.checked = state.ebook;

function match(item) {
if (state.pub && item.p !== state.pub) return false;
if (state.label && item.l !== state.label) return false;
if (state.month && (item.d || '').slice(0, 7) !== state.month) return false;
if (state.ebook && !item.e) return false;
if (state.q) {
var words = state.q.normalize('NFKC').split(/\s+/).filter(Boolean);
var hay = normalize([item.t, item.a, item.p, item.l].join(' '));
for (var i = 0; i < words.length; i++) {
if (hay.indexOf(normalize(words[i])) === -1) return false;
}
}
return true;
}

function renderRow(item) {
var li = rowTemplate.content.firstElementChild.cloneNode(true);
$$('a[data-book-url]', li).forEach(function (a) { a.href = item.u; });
var date = $('[data-field="date"]', li);
var label = dateLabel(item, today);
date.textContent = label;
date.classList.add(label === '発売中' ? 'badge--onsale' : 'badge--date');
$('[data-field="pub"]', li).textContent = item.p;
$('[data-field="title"]', li).textContent = item.t;
var cover = $('.bookrow__image', li);
if (cover && item.i) { var img = document.createElement('img'); img.src = item.i; img.alt = item.ia || ''; img.className = 'cover_photo'; img.loading = 'lazy'; cover.textContent = ''; cover.appendChild(img); }
$('[data-field="meta"]', li).textContent = item.m;
if (!item.e) $('[data-field="ebook"]', li).remove();
$$('[data-store]', li).forEach(function (a) { var url = item.s && item.s[a.dataset.store]; if (url) { a.href = url; } else { a.remove(); } });
return li;
}

function conditionList() {
var list = [];
if (state.q) list.push({ key: 'q', name: 'キーワード', label: 'キーワード：' + state.q });
if (state.pub) list.push({ key: 'pub', name: '出版社', label: '出版社：' + state.pub });
if (state.label) list.push({ key: 'label', name: 'レーベル', label: 'レーベル：' + state.label });
if (state.month) list.push({ key: 'month', name: '発売月', label: '発売月：' + state.month.replace('-', '年').replace(/^(\d+年)0?/, '$1') + '月' });
if (state.ebook) list.push({ key: 'ebook', name: '電子書籍', label: '電子書籍版ありのみ' });
return list;
}

function render() {
var found = items.filter(match);
found.sort(function (a, b) {
if (state.sort === 'added') return b.f - a.f;
return (a.d || '9999') < (b.d || '9999') ? -1 : (a.d || '9999') > (b.d || '9999') ? 1 : 0;
});
var pageCount = Math.max(1, Math.ceil(found.length / PER_PAGE));
if (state.page > pageCount) state.page = pageCount;
var start = (state.page - 1) * PER_PAGE;
var pageItems = found.slice(start, start + PER_PAGE);

$('[data-search-heading]').textContent = state.q ? '「' + state.q + '」の検索結果' : '検索結果';
$('[data-search-total]').textContent = found.length;
$('[data-search-range]').textContent = found.length ? (start + 1) + '〜' + (start + pageItems.length) : '0';

var cond = $('[data-conditions]');
$$('.conditions__item', cond).forEach(function (el) { el.remove(); });
conditionList().forEach(function (c) {
var span = document.createElement('span');
span.className = 'conditions__item';
span.appendChild(document.createTextNode(c.label));
var b = document.createElement('button');
b.type = 'button';
b.className = 'conditions__remove';
b.setAttribute('aria-label', c.name + 'の条件を外す');
b.textContent = '×';
b.addEventListener('click', function () {
state[c.key] = c.key === 'ebook' ? false : '';
state.page = 1;
if (form[c.key]) { if (c.key === 'ebook') form.ebook.checked = false; else form[c.key].value = ''; }
update();
});
span.appendChild(b);
cond.appendChild(span);
});
cond.hidden = conditionList().length === 0;

var list = $('[data-search-results]');
list.textContent = '';
pageItems.forEach(function (item) { list.appendChild(renderRow(item)); });
$('[data-search-empty]').hidden = found.length !== 0;

$$('[data-search-sort]').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.searchSort === state.sort ? 'true' : 'false'); });

var pager = $('[data-search-pager]');
pager.textContent = '';
if (pageCount > 1) {
var start = Math.max(1, Math.min(state.page - 1, pageCount - 3));
var end = Math.min(pageCount, start + 3);
if (start > 1) pager.appendChild(pageButton('« 最初', 1, false));
if (state.page > 1) pager.appendChild(pageButton('‹ 前へ', state.page - 1, false));
for (var i = start; i <= end; i++) pager.appendChild(pageButton(String(i), i, i === state.page));
if (state.page < pageCount) pager.appendChild(pageButton('次へ ›', state.page + 1, false));
if (end < pageCount) pager.appendChild(pageButton('最後 »', pageCount, false));
}
}

function pageButton(label, page, current) {
var b = document.createElement('button');
b.type = 'button';
b.className = 'pager__item' + (current ? ' pager__item--current' : '');
if (current) b.setAttribute('aria-current', 'page');
b.textContent = label;
b.addEventListener('click', function () {
state.page = page;
update();
root.scrollIntoView({ behavior: 'smooth', block: 'start' });
});
return b;
}

function update() {
writeParams(state);
if (items) render();
}

form.addEventListener('submit', function (e) {
e.preventDefault();
state.q = form.q.value.trim();
state.pub = form.pub.value;
state.label = form.label.value;
state.month = form.month.value;
state.ebook = form.ebook.checked;
state.page = 1;
update();
});
$$('[data-search-sort]').forEach(function (b) {
b.addEventListener('click', function () {
state.sort = b.dataset.searchSort;
state.page = 1;
update();
});
});

fetch(root.dataset.index).then(function (r) { return r.json(); }).then(function (data) {
items = data.items;
render();
}).catch(function () {
$('[data-search-empty]').hidden = false;
$('[data-search-empty]').textContent = '検索データを読み込めませんでした。時間をおいて再度お試しください。';
});
};
})();
