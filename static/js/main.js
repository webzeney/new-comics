(function () {
'use strict';

function $(sel, root) { return (root || document).querySelector(sel); }
function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

/* サイドメニューの開閉（スマホ） */
function initSidemenu() {
var button = $('.sidemenu__toggle');
var body = $('#sidemenu-body');
if (!button || !body) return;
var label = $('.sidemenu__toggle_label', button);
button.addEventListener('click', function () {
var open = button.getAttribute('aria-expanded') !== 'true';
button.setAttribute('aria-expanded', open ? 'true' : 'false');
body.classList.toggle('sidemenu__body--closed', !open);
label.textContent = open ? button.dataset.openLabel : button.dataset.closedLabel;
});
}

/* トップ：今日・明日のタブ */
function initReleaseTabs() {
var tabs = $$('.release__tab');
if (!tabs.length) return;
tabs.forEach(function (tab) {
tab.addEventListener('click', function () {
tabs.forEach(function (t) {
var on = t === tab;
t.setAttribute('aria-selected', on ? 'true' : 'false');
var panelId = t.getAttribute('aria-controls');
$('#' + panelId).hidden = !on;
$$('.release__more_link[data-panel="' + panelId + '"]').forEach(function (a) { a.hidden = !on; });
});
});
});
}

/* 出版社チップによる絞り込み（複数選択・即時反映） */
function initPubFilter(root, onChange) {
var chips = $$('.chip[data-pub]', root);
if (!chips.length) return null;
var selected = [];
function render() {
chips.forEach(function (c) {
var key = c.dataset.pub;
var on = key === '' ? selected.length === 0 : selected.indexOf(key) !== -1;
c.setAttribute('aria-pressed', on ? 'true' : 'false');
});
onChange(selected.slice());
}
chips.forEach(function (c) {
c.addEventListener('click', function () {
var key = c.dataset.pub;
if (key === '') { selected = []; }
else if (selected.indexOf(key) !== -1) { selected = selected.filter(function (x) { return x !== key; }); }
else { selected.push(key); }
render();
});
});
return render;
}

function filterNote(selected) {
return selected.length === 0 ? 'すべての出版社' : selected.join('・') + 'で絞り込み中';
}

/* 日別一覧 */
function initDayPage() {
var root = $('[data-daypage]');
if (!root) return;
initPubFilter(root, function (selected) {
var shown = 0;
$$('[data-group]').forEach(function (g) {
var on = selected.length === 0 || selected.indexOf(g.dataset.group) !== -1;
g.hidden = !on;
if (on) shown += Number(g.dataset.count);
});
$('[data-shown-count]').textContent = shown + '点';
$('[data-filter-note]').textContent = filterNote(selected);
});
}

/* カレンダー */
function initCalendar() {
var root = $('[data-calendar]');
if (!root) return;
var data = JSON.parse($('#calendar-data').textContent);
var rowTemplate = $('#bookrow-template');
var list = $('[data-day-list]');
var state = { day: Number(root.dataset.selected), pubs: [] };

function booksOf(day) {
return (data.days[day] || []).filter(function (b) {
return state.pubs.length === 0 || state.pubs.indexOf(b.pub) !== -1;
});
}

function renderRow(b) {
var li = rowTemplate.content.firstElementChild.cloneNode(true);
$$('a[data-book-url]', li).forEach(function (a) { a.href = b.url; });
$('[data-field="pub"]', li).textContent = b.pub;
$('[data-field="title"]', li).textContent = b.title;
var cover = $('.bookrow__image', li);
if (cover && b.i) { var img = document.createElement('img'); img.src = b.i; img.alt = b.ia || ''; img.className = 'cover_photo'; img.loading = 'lazy'; cover.textContent = ''; cover.appendChild(img); }
var coverLink = $('.bookrow__cover', li);
if (coverLink && b.c) { coverLink.href = b.c; coverLink.rel = 'sponsored noopener'; coverLink.target = '_blank'; }
$('[data-field="meta"]', li).textContent = b.meta;
if (!b.ebook) $('[data-field="ebook"]', li).remove();
if (!b.first) $('[data-field="first"]', li).remove();
$$('[data-store]', li).forEach(function (a) { var url = b.stores[a.dataset.store]; if (url) { a.href = url; } else { a.remove(); } });
return li;
}

function render() {
var books = booksOf(state.day);
list.textContent = '';
books.forEach(function (b) { list.appendChild(renderRow(b)); });
$('[data-sel-label]').textContent = data.labels[state.day];
$('[data-sel-count]').textContent = books.length + '点';
$('[data-sel-note]').textContent = filterNote(state.pubs);
$('[data-sel-empty]').hidden = books.length !== 0;
$$('.calendar__day').forEach(function (cell) {
var d = Number(cell.dataset.day);
var dayBooks = booksOf(d);
var n = dayBooks.length;
cell.setAttribute('aria-pressed', d === state.day ? 'true' : 'false');
cell.disabled = n === 0;
cell.classList.toggle('calendar__day--empty', n === 0);
var head = $('.calendar__day_head', cell);
var countEl = $('.calendar__count', cell);
if (n === 0 && countEl) countEl.remove();
if (n > 0) {
if (!countEl) { countEl = document.createElement('span'); head.appendChild(countEl); }
countEl.className = 'calendar__count' + (n >= 40 ? ' calendar__count--big' : '');
countEl.textContent = n + '点';
}
$$('.calendar__title, .calendar__more', cell).forEach(function (el) { el.remove(); });
dayBooks.slice(0, 2).forEach(function (b) {
var t = document.createElement('span');
t.className = 'calendar__title';
t.textContent = b.title;
cell.appendChild(t);
});
if (n > 2) {
var more = document.createElement('span');
more.className = 'calendar__more';
more.textContent = '+' + (n - 2) + '点';
cell.appendChild(more);
}
cell.setAttribute('aria-label', data.labels[d] + n + '点');
});
}

$$('.calendar__day').forEach(function (cell) {
cell.addEventListener('click', function () {
if (cell.disabled) return;
state.day = Number(cell.dataset.day);
render();
});
});
initPubFilter(root, function (selected) { state.pubs = selected; render(); });

$$('.calendar__list_more').forEach(function (button) {
button.addEventListener('click', function () {
var open = button.getAttribute('aria-expanded') !== 'true';
button.setAttribute('aria-expanded', open ? 'true' : 'false');
$$('[data-extra]', button.parentNode).forEach(function (a) { a.hidden = !open; });
$('[data-more-label]', button).textContent = open ? '閉じる' : button.dataset.label;
});
});
}

/* 月の切り替え（出版社別・レーベル別・タグ別） */
function initMonthTabs() {
var tabs = $$('.monthtab__item');
if (!tabs.length) return;
tabs.forEach(function (tab) {
tab.addEventListener('click', function () {
tabs.forEach(function (t) {
var on = t === tab;
t.setAttribute('aria-selected', on ? 'true' : 'false');
t.classList.toggle('monthtab__item--current', on);
$('#' + t.getAttribute('aria-controls')).hidden = !on;
});
var heading = $('[data-month-heading]');
if (heading) {
$('[data-month-no]', heading).textContent = tab.dataset.month;
$('[data-month-count]', heading).textContent = tab.dataset.count + '点';
}
});
});
}

/* 既刊スライダー（最新刊を除く・ループ・自動送り） */
function initSlider() {
var slider = $('.slider');
if (!slider) return;
var track = $('.slider__track', slider);
var base = $$('.slider__item', track);
var n = base.length;
if (n === 0) return;
base.slice().reverse().forEach(function (li) { track.insertBefore(li.cloneNode(true), track.firstChild); });
base.forEach(function (li) { track.appendChild(li.cloneNode(true)); });
$$('.slider__item', track).forEach(function (li, i) {
if (i < n || i >= n * 2) $$('a', li).forEach(function (a) { a.tabIndex = -1; });
});
var mq = window.matchMedia('(max-width: 720px)');
var pos = n + Number(slider.dataset.start || 0);
var moving = false;
var hover = false;
function perView() { return mq.matches ? 2 : 4; }
function apply(anim) {
track.style.transition = anim ? 'transform 0.5s ease' : 'none';
track.style.transform = 'translateX(calc(' + (-pos) + ' * (100% + 14px) / ' + perView() + '))';
}
function go(dir) {
if (moving) return;
moving = true;
pos += dir * perView();
apply(true);
setTimeout(function () {
if (pos >= n * 2) pos -= n;
if (pos < n) pos += n;
apply(false);
moving = false;
}, 520);
}
apply(false);
mq.addEventListener('change', function () { apply(false); });
$('[data-slide="prev"]', slider).addEventListener('click', function () { go(-1); });
$('[data-slide="next"]', slider).addEventListener('click', function () { go(1); });
slider.addEventListener('mouseenter', function () { hover = true; });
slider.addEventListener('mouseleave', function () { hover = false; });
var startX = null;
var viewport = $('.slider__viewport', slider);
viewport.addEventListener('pointerdown', function (e) { startX = e.clientX; });
viewport.addEventListener('pointerup', function (e) {
if (startX === null) return;
var dx = e.clientX - startX;
if (dx > 40) go(-1);
if (dx < -40) go(1);
startX = null;
});
if (n > perView() && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
setInterval(function () { if (!hover && !document.hidden) go(1); }, 3000);
}
}

/* 既刊一覧の並び順 */
function initVolumeSort() {
var buttons = $$('[data-sort]');
var list = $('.volumes');
if (!buttons.length || !list) return;
buttons.forEach(function (b) {
b.addEventListener('click', function () {
if (b.getAttribute('aria-pressed') === 'true') return;
buttons.forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
$$('li', list).reverse().forEach(function (li) { list.appendChild(li); });
});
});
}

document.addEventListener('DOMContentLoaded', function () {
initSidemenu();
initReleaseTabs();
initDayPage();
initCalendar();
initMonthTabs();
initSlider();
initVolumeSort();
if (window.NewComicsSearch) window.NewComicsSearch();
});
})();
