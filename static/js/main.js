(function () {
'use strict';

function $(sel, root) { return (root || document).querySelector(sel); }
function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

/* アナリティクスに操作を記録する（2026-11-16 運営者の判断。個人を特定する情報は送らない） */
function pageType() {
var path = location.pathname.replace(/^\/+/, '');
var seg = path.split('/')[0] || 'top';
if (/^(publisher|label|genre)\/[^/]+\/\d{4}-\d{2}\/$/.test(path)) return seg + '_month';
return seg;
}
function track(name, params) {
try { if (typeof window.gtag === 'function') window.gtag('event', name, Object.assign({ page_type: pageType() }, params || {})); } catch (e) {}
}
window.NewComicsTrack = track;
document.addEventListener('click', function (e) {
var a = e.target.closest ? e.target.closest('a') : null;
if (!a) return;
var store = a.getAttribute('data-ga-store') || a.getAttribute('data-store');
if (store && (a.classList.contains('store_tile') || a.classList.contains('store_button') || a.hasAttribute('data-ga-store'))) {
var place = a.closest('.next_books') ? 'next_books' : a.closest('.buy_bar') ? 'buy_bar' : a.closest('.collect') ? 'collect' : a.closest('.now_read') ? 'now_read' : a.closest('.bookrow') ? 'list' : 'main';
track('store_click', { store: store, buy_type: /予約$/.test(a.getAttribute('aria-label') || '') ? 'reserve' : 'purchase', place: place });
} else if (/feed\.xml$/.test(a.getAttribute('href') || '')) {
track('rss_subscribe', { feed: a.getAttribute('href').replace(/^(\.\.\/)+/, '').replace(/^\//, '').replace(/\/?feed\.xml$/, '') });
} else if (/calendar\.google\.com\/calendar\/render/.test(a.href)) {
track('calendar_subscribe', { service: 'google_one_book' });
} else if (a.hasAttribute('data-cal-label')) {
track('calendar_subscribe', { service: a.getAttribute('data-cal-label') });
} else if (a.hasAttribute('data-month-jump')) {
var tab = document.getElementById('month-tab-' + a.getAttribute('data-month-jump'));
if (tab) { e.preventDefault(); tab.click(); var head = tab.closest('.section_head'); if (head) head.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
} else if (a.hasAttribute('data-cart-go')) {
track('cart_add', { items: $$('[data-cart-pick]:checked').length });
}
}, true);

/* 発売前の本の購入ボタンを「○○で予約」にする（JS で並べる一覧用） */
var RESERVE_WORDS = { amazon: 'Amazon', rakuten: '楽天', seven: 'セブンネット', kindle: 'Kindle', kobo: '楽天Kobo' };
window.NewComicsReserve = function (li, iso) {
var today = new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
if (!iso || iso <= today) return;
$$('[data-store]', li).forEach(function (a) {
var word = RESERVE_WORDS[a.dataset.store];
if (!word) return;
a.textContent = '';
[word, 'で予約'].forEach(function (t) { var s = document.createElement('span'); s.className = 'store_tile__word'; s.textContent = t; a.appendChild(s); });
a.setAttribute('aria-label', a.getAttribute('title') + 'で予約');
});
};

/* 検索の「条件で探す」の開閉（スマホ）。条件を選んでいるときは、初めから開いておく */
function initSearchMore() {
$$('[data-search-more-toggle]').forEach(function (button) {
var box = document.getElementById(button.getAttribute('aria-controls'));
if (!box) return;
function setOpen(open) {
button.setAttribute('aria-expanded', open ? 'true' : 'false');
box.classList.toggle('search_form__more--open', open);
}
button.addEventListener('click', function () { setOpen(button.getAttribute('aria-expanded') !== 'true'); });
var used = $$('select', box).some(function (s) { return s.value; }) || $$('input[type="checkbox"]', box).some(function (c) { return c.checked; });
if (used) setOpen(true);
});
}

/* サイドメニューの開閉（スマホ） */
function initSidemenu() {
var button = $('.sidemenu__toggle');
var body = $('#sidemenu-body');
if (!button || !body) return;
var label = $('.sidemenu__toggle_label', button);
var overlay = $('[data-sidemenu-overlay]');
function setOpen(open) {
button.setAttribute('aria-expanded', open ? 'true' : 'false');
body.classList.toggle('sidemenu__body--closed', !open);
label.textContent = open ? button.dataset.openLabel : button.dataset.closedLabel;
if (overlay) overlay.hidden = !open;
document.documentElement.classList.toggle('is_menu_open', open);
}
button.addEventListener('click', function () {
setOpen(button.getAttribute('aria-expanded') !== 'true');
});
if (overlay) overlay.addEventListener('click', function () { setOpen(false); });
document.addEventListener('keydown', function (e) {
if (e.key === 'Escape' && button.getAttribute('aria-expanded') === 'true') { setOpen(false); button.focus(); }
});
}

/* 「今日・明日発売の新刊」：PC は1段に並ぶ数×2段ぶんだけ表示し、段の途中で欠けないようにする */
function fitReleaseRows() {
var grids = $$('.release__grid');
if (!grids.length) return;
var shown = grids.filter(function (g) { return !g.hidden; })[0];
var limit = 8;
if (shown && window.matchMedia('(min-width: 721px)').matches) {
var cols = getComputedStyle(shown).gridTemplateColumns.split(' ').filter(Boolean).length;
if (cols > 0) limit = cols * 2;
}
grids.forEach(function (g) {
$$('.card', g).forEach(function (c, i) { c.classList.toggle('card--off', i >= limit); });
});
}

function initReleaseRows() {
if (!$('.release__grid')) return;
var timer = null;
window.addEventListener('resize', function () { clearTimeout(timer); timer = setTimeout(fitReleaseRows, 100); });
fitReleaseRows();
}

/* 本のページ「同じ日発売のほかの新刊」：PC は横1列に入る分だけ、スマホは 6 冊まで出す */
function fitOneRow() {
$$('[data-fit-row]').forEach(function (grid) {
var limit = 6;
if (window.matchMedia('(min-width: 721px)').matches) {
var cols = getComputedStyle(grid).gridTemplateColumns.split(' ').filter(Boolean).length;
if (cols > 0) limit = cols;
}
Array.prototype.forEach.call(grid.children, function (item, i) { item.classList.toggle('sameday__item--off', i >= limit); });
});
}
function initOneRow() {
if (!$('[data-fit-row]')) return;
var timer = null;
window.addEventListener('resize', function () { clearTimeout(timer); timer = setTimeout(fitOneRow, 100); });
fitOneRow();
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
fitReleaseRows();
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
if (!b.eo) $('[data-field="ebookonly"]', li).remove();
if (!b.first) $('[data-field="first"]', li).remove();
$$('[data-store]', li).forEach(function (a) { var url = b.stores[a.dataset.store]; if (url) { a.href = url; } else { a.remove(); } });
window.NewComicsReserve(li, b.d);
var fav = $('[data-fav-id]', li);
if (b.fv) { fav.dataset.favId = b.fv[0]; fav.dataset.favName = b.fv[1]; fav.dataset.favUrl = '/series/' + b.fv[0] + '/'; fav.setAttribute('aria-label', b.fv[1] + 'をお気に入りに追加'); bindFav(fav); } else { fav.remove(); }
var pick = $('[data-cart-pick]', li);
var asin = (b.stores.amazon || '').match(/\/dp\/([0-9A-Z]{10})/);
if (asin) { pick.value = asin[1]; pick.setAttribute('aria-label', (b.ia || b.title) + 'をカートに入れる本に選ぶ'); } else { var none = document.createElement('span'); none.className = 'pick pick--none'; none.setAttribute('aria-hidden', 'true'); pick.parentNode.replaceWith(none); }
return li;
}

function render() {
var books = booksOf(state.day);
list.textContent = '';
books.forEach(function (b) { list.appendChild(renderRow(b)); });
document.dispatchEvent(new Event('cart:refresh'));
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

/* 本のページ：今日発売の本の発売日の表示 */
function initReleaseToday() {
var box = $('.book__fact--date[data-release]');
if (!box || !$('.book__bubble--today')) return;
box.classList.add('book__fact--today');
$('.book__fact_label', box).insertAdjacentHTML('beforeend', '<span class="book__fact_today">本日発売</span>');
}

/* トップの特集：ページを作った後に公開された記事（朝7時の予約投稿など）も出すため、開いたときに最新の記事を取り直す（2026-11-25 運営者の判断） */
function initFeatureLatest() {
var list = $('[data-feature-latest]');
if (!list || !window.fetch) return;
var api = list.getAttribute('data-feature-latest');
var esc = function (t) { var d = document.createElement('div'); d.textContent = t; return d.innerHTML; };
var plain = function (h) { var d = document.createElement('div'); d.innerHTML = h; return d.textContent; };
fetch(api + 'categories?slug=column&_fields=id').then(function (r) { return r.json(); }).then(function (cats) {
if (!cats || !cats.length) return null;
return fetch(api + 'posts?per_page=4&categories=' + cats[0].id + '&orderby=date&order=desc&_fields=title,link,date,nc_icon_url').then(function (r) { return r.json(); });
}).then(function (posts) {
if (!posts || !posts.length) return;
list.innerHTML = posts.map(function (p, i) {
var iso = (p.date || '').slice(0, 10);
var day = iso.replace(/-/g, '.');
var icon = p.nc_icon_url ? '<img src="' + esc(p.nc_icon_url) + '" width="64" height="64" alt="" class="feature_panel__icon" loading="lazy">' : '<span class="feature_panel__no">' + ('0' + (i + 1)).slice(-2) + '</span>';
return '<li class="feature_panel__item"><a href="' + esc(p.link) + '" class="feature_panel__link">' + icon + '<span class="feature_panel__body"><span class="feature_panel__meta">' + (iso ? '<time datetime="' + iso + '" class="feature_panel__date">' + day + '</time>' : '') + '<span class="feature_panel__tag">特集</span></span><span class="feature_panel__text">' + esc(plain((p.title || {}).rendered || '')) + '</span></span></a></li>';
}).join('');
}).catch(function () {});
}

/* 本のページ：発売までの日数（日本時間の日付で数える。毎晩の転送を増やさないよう、ページには書かずにここで出す） */
function initCountdown() {
var nums = document.querySelectorAll('[data-countdown]');
var bar = $('.buy_bar');
var box = $('.book__fact--date[data-release]') || bar;
if (!nums.length || !box) return;
var r = (box.getAttribute('data-release') || '').split('-');
if (r.length !== 3) return;
var jst = new Date(Date.now() + 9 * 3600000);
var today = Date.UTC(jst.getUTCFullYear(), jst.getUTCMonth(), jst.getUTCDate());
var days = Math.round((Date.UTC(+r[0], +r[1] - 1, +r[2]) - today) / 86400000);
if (days < 1) return;
nums.forEach(function (n) { n.textContent = days; });
document.querySelectorAll('.countdown, .buy_bar__days').forEach(function (el) { el.hidden = false; });
}

/* 本のページ：スマホの画面の下の購入の帯（ページの中の購入のボタンが見えている間は隠す） */
function initBuyBar() {
var bar = $('.buy_bar');
var buy = $('.book__buy .store_buttons');
if (!bar) return;
document.body.classList.add('has_buy_bar');
if (!buy || !('IntersectionObserver' in window)) { bar.classList.add('buy_bar--show'); return; }
new IntersectionObserver(function (es) {
es.forEach(function (e) { bar.classList.toggle('buy_bar--show', !e.isIntersecting); });
}).observe(buy);
}

/* 本のページ：新刊のお知らせをカレンダーで受け取る案内 */
function initCalendarDialog() {
var dialog = $('.alarm_dialog:not([data-fav-transfer])');
if (!dialog) return;
var backdrop = $('.alarm_dialog__backdrop:not([data-fav-transfer-close])');
var target = $('[data-alarm-target]', dialog);
var submit = $('[data-alarm-submit]', dialog);
var current = null;
var opener = null;
var boxes = Array.prototype.slice.call(dialog.querySelectorAll('input[type="checkbox"]'));
function mark() {
boxes.forEach(function (b) { b.parentNode.classList.toggle('alarm_dialog__option--on', b.checked); });
}
function url() {
var picked = boxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
var webcal = current.endpoint + '&alarm=' + (picked.length ? picked.join(',') : 'none');
return current.kind === 'google' ? 'https://calendar.google.com/calendar/r?cid=' + encodeURIComponent(webcal) : webcal;
}
function close() {
dialog.hidden = true;
backdrop.hidden = true;
if (opener) opener.focus();
}
document.querySelectorAll('[data-subscribe]').forEach(function (a) {
a.addEventListener('click', function (e) {
e.preventDefault();
opener = a;
current = { kind: a.getAttribute('data-subscribe'), endpoint: a.getAttribute('data-subscribe-endpoint') };
target.textContent = current.kind === 'google' ? 'Googleカレンダー' : 'iPhone・Macのカレンダー';
dialog.querySelectorAll('[data-alarm-note]').forEach(function (n) { n.hidden = n.getAttribute('data-alarm-note') !== current.kind; });
mark();
dialog.hidden = false;
backdrop.hidden = false;
boxes[0].focus();
});
});
boxes.forEach(function (b) { b.addEventListener('change', mark); });
dialog.querySelectorAll('[data-alarm-close]').forEach(function (b) { b.addEventListener('click', close); });
backdrop.addEventListener('click', close);
document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !dialog.hidden) close(); });
submit.addEventListener('click', function (e) {
e.preventDefault();
var href = url();
track('calendar_subscribe', { service: current.kind, alarms: boxes.filter(function (x) { return x.checked; }).length });
close();
if (current.kind === 'google') window.open(href, '_blank', 'noopener');
else location.href = href;
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
function perView() { return mq.matches ? 2 : 6; }
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
if (!track) return;
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
try { localStorage.setItem(FAV_KEY, JSON.stringify(list)); } catch (e) {}
}
function bindFav(b) {
var id = String(b.dataset.favId);
var label = $('.fav_button__label', b);
var icon = $('.fav_button__icon', b);
function paint() {
var on = loadFavs().some(function (f) { return String(f.id) === id; });
b.setAttribute('aria-pressed', on ? 'true' : 'false');
if (label) label.textContent = on ? (b.dataset.favLabelOn || 'お気に入りに登録済み') : (b.dataset.favLabelOff || 'この作品をお気に入りに追加');
if (icon) icon.textContent = on ? (b.dataset.favIconOn || '★') : (b.dataset.favIconOff || '☆');
}
b.addEventListener('click', function () {
var list = loadFavs();
var exists = list.some(function (f) { return String(f.id) === id; });
list = exists ? list.filter(function (f) { return String(f.id) !== id; }) : list.concat([{ id: id, name: b.dataset.favName, url: b.dataset.favUrl }]);
track('favorite', { fav_action: exists ? 'remove' : 'add' });
saveFavs(list);
document.dispatchEvent(new CustomEvent('fav:change'));
});
document.addEventListener('fav:change', paint);
paint();
}
function initFavButtons() {
$$('[data-fav-id]').forEach(bindFav);
/* 特集記事の「この記事で紹介した本」：紹介した本の作品をまとめてお気に入りに入れる */
$$('[data-fav-all]').forEach(function (btn) {
var box = btn.closest('section') || document;
btn.addEventListener('click', function () {
var list = loadFavs();
var added = 0;
$$('.bookrow__fav[data-fav-id]', box).forEach(function (b) {
var id = String(b.dataset.favId);
if (list.some(function (f) { return String(f.id) === id; })) return;
list.push({ id: id, name: b.dataset.favName, url: b.dataset.favUrl });
added++;
});
if (added) {
saveFavs(list);
track('favorite', { fav_action: 'bulk_add' });
document.dispatchEvent(new CustomEvent('fav:change'));
}
btn.textContent = btn.dataset.labelDone || btn.textContent;
btn.disabled = true;
});
});
}
window.NewComicsBindFav = bindFav;

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
track('calendar_subscribe', { service: 'ics_one_book' });
var a = document.createElement('a');
a.href = URL.createObjectURL(blob);
a.download = b.dataset.icsFile;
document.body.appendChild(a);
a.click();
setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
});
});
}

/* チェックした本を、まとめて Amazon のカートに入れる（「ショッピングカートに入れる」フォームの URL を組み立てる） */
function initCart() {
var bar = $('[data-cart-bar]');
if (!bar) return;
var count = $('[data-cart-count]', bar);
var go = $('[data-cart-go]', bar);
var chosen = [];
function picks() { return $$('[data-cart-pick]').filter(function (el) { return el.value; }); }
function visible(el) { return el.offsetParent !== null; }
function set(asin, on) {
var i = chosen.indexOf(asin);
if (on && i === -1) chosen.push(asin);
if (!on && i !== -1) chosen.splice(i, 1);
}
function update() {
picks().forEach(function (el) { el.checked = chosen.indexOf(el.value) !== -1; });
count.textContent = chosen.length;
bar.hidden = chosen.length === 0;
var q = chosen.map(function (a, i) { return 'ASIN.' + (i + 1) + '=' + encodeURIComponent(a) + '&Quantity.' + (i + 1) + '=1'; }).join('&');
go.href = 'https://www.amazon.co.jp/gp/aws/cart/add.html?' + (bar.dataset.tag ? 'AssociateTag=' + encodeURIComponent(bar.dataset.tag) + '&' : '') + q;
var shown = picks().filter(visible);
var all = shown.length > 0 && shown.every(function (el) { return el.checked; });
$$('[data-cart-all]').forEach(function (b) { b.textContent = all ? b.dataset.labelOff : b.dataset.labelOn; b.setAttribute('aria-pressed', all ? 'true' : 'false'); });
}
document.addEventListener('change', function (e) {
if (e.target.matches && e.target.matches('[data-cart-pick]') && e.target.value) { set(e.target.value, e.target.checked); update(); }
});
document.addEventListener('cart:refresh', update);
$$('[data-cart-all]').forEach(function (b) {
b.addEventListener('click', function () {
var shown = picks().filter(visible);
var on = !shown.every(function (el) { return el.checked; });
shown.forEach(function (el) { set(el.value, on); });
update();
});
});
$('[data-cart-clear]', bar).addEventListener('click', function () { chosen = []; update(); });
update();
}

/* トップの検索：出版社・レーベル・発売月のどれかを選ぶと、残りの2つを本のある選択肢だけにする（検索のページと同じ動き） */
function initFormNarrow() {
var form = $('form.search_form:not([data-search-form])');
if (!form || !form.pub || !form.label || !form.month) return;
var script = $('script[src*="assets/js/main.js"]');
if (!script) return;
var root = script.getAttribute('src').replace(/assets\/js\/.*$/, '');
var filters = [{ select: form.pub, i: 0 }, { select: form.label, i: 1 }, { select: form.month, i: 2 }];
filters.forEach(function (f) {
f.options = $$('option', f.select).filter(function (o) { return o.value; }).map(function (o) { return { value: o.value, text: o.textContent }; });
});
var rows = null;
function available(target) {
var set = {};
rows.forEach(function (r) {
for (var k = 0; k < filters.length; k++) {
var f = filters[k];
if (f === target || !f.select.value) continue;
if (r[f.i] !== f.select.value) return;
}
set[r[target.i]] = true;
});
return set;
}
function narrow(changed) {
if (!rows) return;
if (changed) filters.forEach(function (f) {
if (f.select === changed || !f.select.value) return;
if (!available(f)[f.select.value]) f.select.value = '';
});
filters.forEach(function (f) {
var set = available(f);
var current = f.select.value;
while (f.select.options.length > 1) f.select.remove(1);
f.options.forEach(function (o) {
if (!set[o.value] && o.value !== current) return;
var option = document.createElement('option');
option.value = o.value;
option.textContent = o.text;
f.select.appendChild(option);
});
f.select.value = current;
});
}
filters.forEach(function (f) { f.select.addEventListener('change', function () { narrow(f.select); }); });
fetch(root + 'search/facets.json').then(function (r) { return r.json(); }).then(function (data) { rows = data.rows; narrow(null); }).catch(function () {});
}

function initPick() {
var box = document.querySelector('[data-pick]');
if (!box) return;
var slides = box.querySelectorAll('[data-pick-slide]');
var dots = box.querySelectorAll('[data-pick-dot]');
if (slides.length < 2) return;
var now = 0, timer = null;
var still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
function show(i) {
now = (i + slides.length) % slides.length;
slides.forEach(function (s, j) { s.hidden = j !== now; });
dots.forEach(function (d, j) { if (j === now) d.setAttribute('aria-current', 'true'); else d.removeAttribute('aria-current'); });
}
function start() { if (!still && !timer) timer = setInterval(function () { show(now + 1); }, 6000); }
function stop() { clearInterval(timer); timer = null; }
dots.forEach(function (d, j) { d.addEventListener('click', function () { show(j); stop(); start(); }); });
/* スマホでは左右にスワイプして切り替える（2026-11-21 運営者の判断） */
var sx = null, sy = 0;
box.addEventListener('touchstart', function (e) { sx = e.touches[0].clientX; sy = e.touches[0].clientY; stop(); }, { passive: true });
box.addEventListener('touchend', function (e) {
if (sx === null) return;
var dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy;
sx = null;
if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
show(now + (dx < 0 ? 1 : -1));
box.setAttribute('data-pick-swiped', '');
setTimeout(function () { box.removeAttribute('data-pick-swiped'); }, 400);
}
start();
}, { passive: true });
box.addEventListener('click', function (e) { if (box.hasAttribute('data-pick-swiped')) e.preventDefault(); }, true);
box.addEventListener('mouseenter', stop);
box.addEventListener('mouseleave', start);
box.addEventListener('focusin', stop);
box.addEventListener('focusout', start);
start();
}

function jpHolidayBase(y, m, d) {
var dow = new Date(y, m - 1, d).getDay();
var nth = Math.floor((d - 1) / 7) + 1;
var fixed = ['1-1', '2-11', '2-23', '4-29', '5-3', '5-4', '5-5', '8-11', '11-3', '11-23'];
if (fixed.indexOf(m + '-' + d) >= 0) return true;
if (dow === 1 && ((m === 1 && nth === 2) || (m === 7 && nth === 3) || (m === 9 && nth === 3) || (m === 10 && nth === 2))) return true;
var t = y - 1980;
if (m === 3 && d === Math.floor(20.8431 + 0.242194 * t - Math.floor(t / 4))) return true;
if (m === 9 && d === Math.floor(23.2488 + 0.242194 * t - Math.floor(t / 4))) return true;
return false;
}

function jpHoliday(date) {
var y = date.getFullYear(), m = date.getMonth() + 1, d = date.getDate();
if (jpHolidayBase(y, m, d)) return true;
var prev = new Date(y, m - 1, d - 1), next = new Date(y, m - 1, d + 1);
if (date.getDay() !== 0 && jpHolidayBase(prev.getFullYear(), prev.getMonth() + 1, prev.getDate()) && jpHolidayBase(next.getFullYear(), next.getMonth() + 1, next.getDate())) return true;
for (var i = 1; i < 7; i++) {
var p = new Date(y, m - 1, d - i);
if (!jpHolidayBase(p.getFullYear(), p.getMonth() + 1, p.getDate())) return false;
if (p.getDay() === 0) return true;
}
return false;
}

function kumikoHoliday(date) {
var day = date.getDay();
return day === 0 || day === 6 || jpHoliday(date);
}

function kumikoWeekend() {
return kumikoHoliday(new Date());
}

function kumikoSuffix() {
var now = new Date();
if (!kumikoHoliday(now)) return '_u';
var d = new Date(2026, 0, 1), end = new Date(now.getFullYear(), now.getMonth(), now.getDate()), n = 0;
while (d < end) {
if (kumikoHoliday(d)) n++;
d.setDate(d.getDate() + 1);
}
return '_c' + (n % 5 + 1);
}
window.kumikoSuffix = kumikoSuffix;

function kumikoJstHour() {
return (new Date().getUTCHours() + 9) % 24;
}

function kumikoNight() {
var h = kumikoJstHour();
return h >= 22 || h < 6;
}
window.kumikoNight = kumikoNight;

function kumikoSrc(img, src) {
var probe = new Image();
probe.onload = function () { img.width = Math.round(probe.naturalWidth / 2); img.height = Math.round(probe.naturalHeight / 2); };
probe.src = src;
img.src = src;
img.srcset = src + ' 2x';
}

function initKumiko() {
var box = document.querySelector('[data-kumiko-random]');
if (box) {
var lines = [];
try { lines = JSON.parse(box.getAttribute('data-lines') || '[]'); } catch (e) { lines = []; }
var now = new Date(), h = now.getHours(), day = now.getDay();
var today = parseInt(box.getAttribute('data-today') || '0', 10), tomorrow = parseInt(box.getAttribute('data-tomorrow') || '0', 10);
var ok = {
all: true,
morning: h >= 5 && h < 10,
noon: h >= 10 && h < 16,
evening: h >= 16 && h < 19,
night: h >= 19,
late: h < 5,
weekend: day === 0 || day === 6,
friday: day === 5,
today: today > 0,
notoday: today === 0,
tomorrow: tomorrow > 0
};
var night = kumikoNight(), jh = kumikoJstHour();
ok.p_all = true;
ok.p_late = jh < 5;
ok.p_dawn = jh >= 5 && jh < 6;
ok.p_tomorrow = tomorrow > 0;
ok.p_notoday = today === 0;
var pool = lines.filter(function (l) { return (l.w.indexOf('p_') === 0) === night && ok[l.w]; });
if (today === 0) {
var none = pool.filter(function (l) { return l.w === 'notoday' || l.w === 'p_notoday'; });
if (none.length) pool = none;
}
if (pool.length) {
var pick = pool[Math.floor(Math.random() * pool.length)];
var base = box.getAttribute('data-base');
var img = box.querySelector('[data-kumiko-image]');
kumikoSrc(img, base + pick.p + (night ? '_p' : kumikoSuffix()) + '.webp');
img.removeAttribute('data-kumiko-weekend');
box.querySelector('[data-kumiko-text]').textContent = pick.t.replace('{n}', today).replace('{m}', tomorrow);
}
}
var isNight = kumikoNight();
if (isNight) {
document.querySelectorAll('[data-kumiko-night]').forEach(function (img) {
kumikoSrc(img, img.getAttribute('data-kumiko-night'));
});
document.querySelectorAll('[data-kumiko-night-text]').forEach(function (el) {
el.textContent = el.getAttribute('data-kumiko-night-text');
});
}
if (kumikoWeekend()) {
var suffix = kumikoSuffix();
document.querySelectorAll('[data-kumiko-weekend]').forEach(function (img) {
if (isNight && img.hasAttribute('data-kumiko-night')) return;
var src = img.getAttribute('data-kumiko-weekend');
kumikoSrc(img, img.hasAttribute('data-kumiko-fixed') ? src : src.replace(/_c\.webp$/, suffix + '.webp'));
});
}
}

function initNemuFloat() {
var boxes = Array.prototype.slice.call(document.querySelectorAll('.kumiko--article:not(.kumiko--nowrap)'));
if (!boxes.length) return;
var pc = window.matchMedia('(min-width: 721px)');
function blankBelow(box) {
var el = box.nextElementSibling, last = null;
while (el && /^(P|UL|OL)$/.test(el.tagName)) { last = el; el = el.nextElementSibling; }
var textBottom = last ? last.getBoundingClientRect().bottom : box.getBoundingClientRect().top;
return box.getBoundingClientRect().bottom + 12 - textBottom;
}
function fit() {
var tries = [[], ['kumiko--fit_small'], ['kumiko--fit_row'], ['kumiko--fit_row', 'kumiko--fit_small']];
boxes.forEach(function (box) {
box.classList.remove('kumiko--fit_small', 'kumiko--fit_row');
if (!pc.matches) return;
var best = null, bestBlank = Infinity;
for (var i = 0; i < tries.length; i += 1) {
box.classList.remove('kumiko--fit_small', 'kumiko--fit_row');
tries[i].forEach(function (c) { box.classList.add(c); });
var blank = blankBelow(box);
if (blank <= 24) return;
if (blank < bestBlank) { bestBlank = blank; best = tries[i]; }
}
box.classList.remove('kumiko--fit_small', 'kumiko--fit_row');
best.forEach(function (c) { box.classList.add(c); });
});
}
var imgs = boxes.map(function (box) { return box.querySelector('img'); });
var wait = imgs.filter(function (img) { return img && !img.complete; });
var left = wait.length;
if (!left) fit();
wait.forEach(function (img) {
var done = function () { left -= 1; if (!left) fit(); };
img.addEventListener('load', done, { once: true });
img.addEventListener('error', done, { once: true });
});
var timer;
window.addEventListener('load', fit);
window.addEventListener('resize', function () { clearTimeout(timer); timer = setTimeout(fit, 150); });
}

function initToc() {
var nav = document.querySelector('[data-toc]');
if (!nav || !('IntersectionObserver' in window)) return;
var links = Array.prototype.slice.call(nav.querySelectorAll('.article_toc__link'));
var heads = links.map(function (a) { return document.getElementById(a.getAttribute('href').slice(1)); }).filter(Boolean);
var current = null;
function update() {
var pick = heads[0];
heads.forEach(function (h) { if (h.getBoundingClientRect().top < window.innerHeight * 0.3) pick = h; });
if (pick === current) return;
current = pick;
links.forEach(function (a) {
if (a.getAttribute('href') === '#' + pick.id) a.setAttribute('data-current', ''); else a.removeAttribute('data-current');
});
}
var ticking = false;
window.addEventListener('scroll', function () {
if (ticking) return;
ticking = true;
window.requestAnimationFrame(function () { ticking = false; update(); });
}, { passive: true });
update();
}

function initToTop() {
var btns = document.querySelectorAll('[data-totop]');
if (!btns.length) return;
function update() {
var show = window.scrollY > 800 && document.documentElement.scrollHeight > window.innerHeight * 2;
btns.forEach(function (b) { b.toggleAttribute('data-shown', show); });
}
btns.forEach(function (b) {
b.addEventListener('click', function () {
var still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
window.scrollTo({ top: 0, behavior: still ? 'auto' : 'smooth' });
var target = document.querySelector('main') || document.body;
if (target) { target.setAttribute('tabindex', '-1'); target.focus({ preventScroll: true }); }
});
});
window.addEventListener('scroll', update, { passive: true });
update();
}

document.addEventListener('DOMContentLoaded', function () {
initSidemenu();
initKumiko();
initNemuFloat();
initToc();
initToTop();
initPick();
initFormNarrow();
initCart();
initTicker();
initFilterMore();
initFavButtons();
initOneRow();
initIcs();
initReleaseTabs();
initReleaseRows();
initDayPage();
initCalendar();
initMonthTabs();
initSlider();
initVolumeSort();
initReleaseToday();
initCountdown();
initFeatureLatest();
initBuyBar();
initCalendarDialog();
if (window.NewComicsSearch) window.NewComicsSearch();
initSearchMore();
});
})();
