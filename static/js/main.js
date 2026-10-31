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
var more = $('.release__more');
if (more) more.hidden = !$('.release__more_link[data-panel="' + tab.getAttribute('aria-controls') + '"]');
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

/* なめらかなスクロール */
function smoothScrollTo(target) {
if (!target) return;
var start = window.pageYOffset;
var end = Math.max(0, Math.min(target.getBoundingClientRect().top + start - 16, document.documentElement.scrollHeight - window.innerHeight));
var distance = end - start;
if (Math.abs(distance) < 2) return;
if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) { window.scrollTo(0, end); return; }
var duration = Math.min(1100, Math.max(600, Math.abs(distance) * 0.6));
var begin = null;
var stopped = false;
var stop = function () { stopped = true; };
var events = ['wheel', 'touchstart', 'keydown', 'mousedown'];
events.forEach(function (name) { window.addEventListener(name, stop, { passive: true, once: true }); });
var ease = function (t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
function step(now) {
if (stopped) return;
if (begin === null) begin = now;
var t = Math.min(1, (now - begin) / duration);
window.scrollTo(0, start + distance * ease(t));
if (t < 1) { requestAnimationFrame(step); } else { events.forEach(function (name) { window.removeEventListener(name, stop); }); }
}
requestAnimationFrame(step);
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
smoothScrollTo($('.dayrelease'));
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

/* TODAY の流れる文字：文字の量にかかわらず一定の速さ（1秒あたり60px）で流す */
function initTicker() {
var track = $('.ticker__track');
if (!track || track.classList.contains('ticker__track--static')) return;
var set = function () { track.style.animationDuration = Math.max(20, track.scrollWidth / 2 / 60) + 's'; };
set();
if (document.fonts && document.fonts.ready) document.fonts.ready.then(set);
}

/* カレンダー：出版社の絞り込みボタンの折りたたみ */
function initFilterMore() {
$$('.chip--more').forEach(function (b) {
var box = document.getElementById(b.getAttribute('aria-controls'));
if (!box) return;
b.addEventListener('click', function () {
var open = b.getAttribute('aria-expanded') !== 'true';
b.setAttribute('aria-expanded', open ? 'true' : 'false');
box.hidden = !open;
b.textContent = open ? b.dataset.lessLabel : b.dataset.moreLabel;
});
});
}

/* お気に入り（作品単位・このブラウザに保存） */
var FAV_KEY = 'nc_favorites';
function loadFavs() {
try { return JSON.parse(localStorage.getItem(FAV_KEY) || '[]') || []; } catch (e) { return []; }
}
function saveFavs(list) {
try { localStorage.setItem(FAV_KEY, JSON.stringify(list)); return true; } catch (e) { return false; }
}
function initFavButtons() {
$$('[data-fav-id]').forEach(function (b) {
var id = String(b.dataset.favId);
var label = $('.fav_button__label', b);
var icon = $('.fav_button__icon', b);
function paint() {
var on = loadFavs().some(function (f) { return String(f.id) === id; });
b.setAttribute('aria-pressed', on ? 'true' : 'false');
if (label) label.textContent = on ? 'お気に入りに登録済み' : 'この作品をお気に入りに追加';
if (icon) icon.textContent = on ? '★' : '☆';
}
b.addEventListener('click', function () {
var list = loadFavs();
var exists = list.some(function (f) { return String(f.id) === id; });
list = exists ? list.filter(function (f) { return String(f.id) !== id; }) : list.concat([{ id: id, name: b.dataset.favName, url: b.dataset.favUrl }]);
saveFavs(list);
paint();
});
paint();
});
}

/* 本のページ：発売日をカレンダー（.ics）に追加 */
function initIcs() {
$$('[data-ics-start]').forEach(function (b) {
b.addEventListener('click', function () {
var esc = function (t) { return String(t).replace(/[\;,]/g, function (c) { return '\\' + c; }); };
var lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//new-comics.jp//JA', 'BEGIN:VEVENT',
'UID:' + b.dataset.icsStart + '-' + b.dataset.icsFile + '@new-comics.jp',
'DTSTAMP:' + new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z'),
'DTSTART;VALUE=DATE:' + b.dataset.icsStart, 'DTEND;VALUE=DATE:' + b.dataset.icsEnd,
'SUMMARY:' + esc(b.dataset.icsName), 'URL:' + location.href.split('#')[0], 'END:VEVENT', 'END:VCALENDAR'];
var blob = new Blob([lines.join('\r\n') + '\r\n'], { type: 'text/calendar' });
var a = document.createElement('a');
a.href = URL.createObjectURL(blob);
a.download = b.dataset.icsFile;
document.body.appendChild(a);
a.click();
setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
});
});
}

document.addEventListener('DOMContentLoaded', function () {
initSidemenu();
initTicker();
initFilterMore();
initFavButtons();
initIcs();
initReleaseTabs();
initDayPage();
initCalendar();
initMonthTabs();
initSlider();
initVolumeSort();
if (window.NewComicsSearch) window.NewComicsSearch();
});
})();
