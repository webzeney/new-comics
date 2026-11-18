<?php
declare(strict_types=1);

function nc_site_url(): string
{
    return (string)preg_replace('#/feature/?$#', '', untrailingslashit(home_url()));
}

function nc_partial(string $name): void
{
    $file = dirname(rtrim(ABSPATH, '/')) . '/assets/partials/' . $name . '.html';
    if (is_file($file)) {
        echo file_get_contents($file);
    }
}

add_action('init', function (): void {
    register_post_meta('post', 'nc_banner', [
        'type' => 'integer',
        'single' => true,
        'default' => 0,
        'show_in_rest' => true,
        'auth_callback' => fn() => current_user_can('edit_posts'),
    ]);
});

function nc_banner_url(): string
{
    $id = (int) get_post_meta(get_the_ID(), 'nc_banner', true);
    return $id ? (string) wp_get_attachment_image_url($id, 'full') : '';
}

add_shortcode('books', function ($atts): string {
    $atts = shortcode_atts(['isbn' => ''], $atts, 'books');
    $dir = dirname(rtrim(ABSPATH, '/')) . '/assets/partials/bookrow/';
    $rows = [];
    foreach (preg_split('/[\s,、]+/u', (string) $atts['isbn'], -1, PREG_SPLIT_NO_EMPTY) as $key) {
        $key = preg_replace('/-/', '', $key);
        if (!preg_match('/^[0-9A-Za-z]+$/', $key)) {
            continue;
        }
        $file = $dir . $key . '.html';
        if (is_file($file)) {
            $rows[] = trim((string) file_get_contents($file));
        }
    }
    if (!$rows) {
        return '';
    }
    return '<ul class="article__books">' . "\n" . implode("\n", $rows) . "\n" . '</ul>';
});

/* 看板キャラクターなどの画像は2倍の大きさで作っているので、表示する幅と高さ（半分）を属性で書く。
   srcset の 2x だけでは、画素の細かくない画面で2倍の大きさに出てしまうため */
function nc_half_size(string $file): string
{
    $size = @getimagesize(dirname(rtrim(ABSPATH, '/')) . '/assets/img/' . $file);
    return $size ? ' width="' . intdiv($size[0], 2) . '" height="' . intdiv($size[1], 2) . '"' : '';
}

/* 看板キャラクター（櫻塚こはる）。平日は制服、土日は私服（main.js が data-kumiko-weekend で差し替える） */
function nc_nemu(string $pose, string $text, string $mod = ''): string
{
    $pose = preg_match('/^[a-z0-9]+$/', $pose) ? $pose : 'point';
    $base = nc_site_url() . '/assets/img/kumiko/' . $pose;
    $size = nc_half_size('kumiko/' . $pose . '_u.webp');
    return '<div class="kumiko' . ($mod ? ' kumiko--' . implode(' kumiko--', array_map('esc_attr', explode(' kumiko--', $mod))) : '') . '">'
        . '<img src="' . esc_url($base . '_u.webp') . '" srcset="' . esc_url($base . '_u.webp') . ' 2x"' . $size . ' data-kumiko-weekend="' . esc_url($base . '_c.webp') . '" alt="" class="kumiko__image" loading="lazy">'
        . '<p class="kumiko__bubble">' . $text . '</p></div>';
}

/* 記事の本文に [koharu pose="cheer"]セリフ[/koharu] と書くと、こはるが吹き出しで話す（前の名前の [nemu] も使える）。
   PC では、こはる（吹き出しはこはるの上か横）のよこに、あとに続く文章が回り込む。
   こはるの位置は 左 → 右 の順に入れ替わる。side="left" / "right" で指定もできる（2026-11-18 運営者の判断） */
$nc_koharu_shortcode = function ($atts, $content = ''): string {
    static $count = [];
    $atts = shortcode_atts(['pose' => 'point', 'side' => ''], $atts, 'koharu');
    $id = (int) get_the_ID();
    $count[$id] = ($count[$id] ?? 0) + 1;
    $side = in_array($atts['side'], ['left', 'right'], true) ? $atts['side'] : ($count[$id] % 2 ? 'left' : 'right');
    return str_replace(' loading="lazy"', '', nc_nemu((string) $atts['pose'], wp_kses(trim((string) $content), ['br' => [], 'strong' => [], 'a' => ['href' => []]]), 'article kumiko--' . $side));
};
add_shortcode('koharu', $nc_koharu_shortcode);
add_shortcode('nemu', $nc_koharu_shortcode);

/* あとに文章もリストもなく、すぐ表・見出しなどになるときは回り込ませない。
   PC では main.js（initNemuFloat）が表示したあとに余白を測って、吹き出しを上にした形・横に並べた形と大きさを選ぶ（2026-11-18 運営者の判断） */
function nc_nemu_float_fit(string $html): string
{
    return preg_replace_callback('/<div class="kumiko kumiko--article kumiko--(?:left|right)">.*?<\/div>/s', function (array $m) use ($html): string {
        static $offset = 0;
        $pos = strpos($html, $m[0], $offset);
        $offset = $pos + strlen($m[0]);
        $rest = substr($html, $offset);
        $lines = 0;
        while (preg_match('/\A\s*<(p|ul|ol)(?:\s[^>]*)?>(.*?)<\/\1>/s', $rest, $p)) {
            $items = $p[1] === 'p' ? [$p[2]] : (preg_match_all('/<li(?:\s[^>]*)?>(.*?)<\/li>/s', $p[2], $li) ? $li[1] : []);
            foreach ($items as $item) {
                $lines += (int) ceil(mb_strlen(trim(strip_tags($item))) / 36);
            }
            $rest = substr($rest, strlen($p[0]));
        }
        return $lines > 0 ? $m[0] : str_replace('kumiko--article', 'kumiko--article kumiko--nowrap', $m[0]);
    }, $html);
}
add_filter('the_content', 'nc_nemu_float_fit', 12);

/* 記事の本文に [beta pose="happy"]セリフ[/beta] と書くと、こはるの飼い犬のパグ「ベタ」が吹き出しで話す */
add_shortcode('beta', function ($atts, $content = ''): string {
    $atts = shortcode_atts(['pose' => 'normal'], $atts, 'beta');
    $pose = in_array($atts['pose'], ['normal', 'happy', 'surprise', 'sleepy', 'tilt', 'proud', 'sad', 'wink'], true) ? $atts['pose'] : 'normal';
    $src = nc_site_url() . '/assets/img/beta/' . $pose . '.webp';
    return '<div class="beta"><img src="' . esc_url($src) . '" srcset="' . esc_url($src) . ' 2x"' . nc_half_size('beta/' . $pose . '.webp') . ' alt="" class="beta__image">'
        . '<p class="beta__bubble">' . wp_kses(trim((string) $content), ['br' => [], 'strong' => []]) . '</p></div>';
});

/* 記事の本文に [box title="作品情報"]…[/box] と書くと、見出し付きの枠で囲む */
add_shortcode('box', function ($atts, $content = ''): string {
    $atts = shortcode_atts(['title' => ''], $atts, 'box');
    $title = trim((string) $atts['title']);
    return '<div class="article__box">' . ($title !== '' ? '<p class="article__box_label">' . esc_html($title) . '</p>' : '')
        . '<div class="article__box_body">' . wpautop(do_shortcode(trim((string) $content))) . '</div></div>';
});

/* 記事の見出し（h2・h3）から目次を作り、最初の見出しの前に入れる。サイドの目次にも同じものを使う */
$GLOBALS['nc_toc'] = '';
function nc_toc_build(string $html): string
{
    if (!is_single() || !in_the_loop() || !is_main_query()) {
        return $html;
    }
    $items = [];
    $n = 0;
    $html = preg_replace_callback('/<h([23])([^>]*)>(.*?)<\/h\1>/s', function (array $m) use (&$items, &$n): string {
        $n += 1;
        $id = preg_match('/\sid="([^"]+)"/', $m[2], $a) ? $a[1] : 'sec' . $n;
        $items[] = [(int) $m[1], $id, trim(wp_strip_all_tags($m[3]))];
        $attr = preg_match('/\sid="/', $m[2]) ? $m[2] : $m[2] . ' id="' . $id . '"';
        return '<h' . $m[1] . $attr . '>' . $m[3] . '</h' . $m[1] . '>';
    }, $html);
    if (count(array_filter($items, fn ($i) => $i[0] === 2)) < 3) {
        $GLOBALS['nc_toc'] = '';
        return $html;
    }
    $list = '';
    $num = 0;
    $open = false;
    foreach ($items as [$level, $id, $text]) {
        if ($level === 2) {
            if ($open) {
                $list .= '</ul>';
                $open = false;
            }
            $list .= ($num ? '</li>' : '') . '<li class="article_toc__item"><a href="#' . esc_attr($id) . '" class="article_toc__link"><span class="article_toc__num">' . sprintf('%02d', ++$num) . '</span>' . esc_html($text) . '</a>';
        } elseif ($num) {
            if (!$open) {
                $list .= '<ul class="article_toc__sub">';
                $open = true;
            }
            $list .= '<li class="article_toc__item article_toc__item--sub"><a href="#' . esc_attr($id) . '" class="article_toc__link">' . esc_html($text) . '</a></li>';
        }
    }
    $list .= ($open ? '</ul>' : '') . '</li>';
    $GLOBALS['nc_toc'] = '<ol class="article_toc__list">' . $list . '</ol>';
    $box = '<nav class="article_toc" aria-label="もくじ"><p class="article_toc__title">もくじ</p>' . $GLOBALS['nc_toc'] . '</nav>';
    return preg_match('/<h2[\s>]/', $html, $h, PREG_OFFSET_CAPTURE) ? substr_replace($html, $box, $h[0][1], 0) : $html;
}
add_filter('the_content', 'nc_toc_build', 20);

/* 特集の一覧はコラムだけにする（2026-11-18 運営者の判断） */
add_action('pre_get_posts', function (WP_Query $q): void {
    if (!is_admin() && $q->is_main_query() && $q->is_home()) {
        $q->set('category_name', 'column');
    }
});

/* 一覧と記事のページで、こはるが話すこと */
function nc_nemu_head(): string
{
    if (is_category('news')) {
        return nc_nemu('wave', '漫画新刊JPの新しい機能や、見せ方を変えたことをお知らせするよ！', 'side');
    }
    if (is_single() && has_category('news')) {
        return nc_nemu('surprise', 'お知らせだよ！ 新しくなったところ、ぜひ使ってみてね。', 'side');
    }
    if (is_single()) {
        return nc_nemu('laptop', 'このコラムは、わたしが書いたよ！ 最後まで読んでくれるとうれしいな。', 'side');
    }
    return nc_nemu('laptop', 'わたしが書いた漫画のコラムを集めているよ！ 気になる記事から読んでみてね。', 'side');
}

add_action('after_setup_theme', function (): void {
    add_theme_support('title-tag');
    add_theme_support('post-thumbnails');
    add_theme_support('html5', ['search-form', 'gallery', 'caption', 'style', 'script']);
});

add_action('wp_enqueue_scripts', function (): void {
    $site = nc_site_url();
    $root = dirname(untrailingslashit(ABSPATH));
    $css_ver = @filemtime($root . '/assets/css/style.css') ?: null;
    $js_ver = @filemtime($root . '/assets/js/main.js') ?: null;
    $theme_ver = @filemtime(get_stylesheet_directory() . '/style.css') ?: wp_get_theme()->get('Version');
    wp_enqueue_style('nc-fonts', 'https://fonts.googleapis.com/css2?family=Yusei+Magic&family=Noto+Sans+JP:wght@400;500;700;900&display=swap', [], null);
    wp_enqueue_style('nc-site', $site . '/assets/css/style.css', ['nc-fonts'], $css_ver);
    wp_enqueue_style('nc-theme', get_stylesheet_uri(), ['nc-site'], $theme_ver);
    wp_enqueue_script('nc-main', $site . '/assets/js/main.js', [], $js_ver, ['strategy' => 'defer', 'in_footer' => false]);
    wp_dequeue_style('wp-block-library');
    wp_dequeue_style('global-styles');
    wp_dequeue_style('classic-theme-styles');
}, 20);

add_filter('document_title_separator', fn() => '｜');
add_filter('document_title_parts', function (array $parts): array {
    if (is_home() || is_front_page()) {
        $parts['title'] = '特集';
    }
    $parts['site'] = '漫画新刊JP';
    unset($parts['tagline']);
    return $parts;
});
add_filter('excerpt_length', fn() => 80);
add_filter('excerpt_more', fn() => '…');
remove_action('wp_head', 'print_emoji_detection_script', 7);
remove_action('wp_print_styles', 'print_emoji_styles');
remove_action('wp_head', 'wp_generator');

function nc_pager(): void
{
    global $wp_query;
    $last = (int) $wp_query->max_num_pages;
    if ($last <= 1) {
        return;
    }
    $current = max(1, (int) get_query_var('paged'));
    $start = max(1, min($current - 1, $last - 3));
    $end = min($last, $start + 3);
    $items = [];
    if ($start > 1) {
        $items[] = [1, '« 最初'];
    }
    if ($current > 1) {
        $items[] = [$current - 1, '‹ 前へ'];
    }
    for ($k = $start; $k <= $end; $k++) {
        $items[] = [$k, (string) $k];
    }
    if ($current < $last) {
        $items[] = [$current + 1, '次へ ›'];
    }
    if ($end < $last) {
        $items[] = [$last, '最後 »'];
    }
    echo '<nav aria-label="ページ送り" class="pager"><div class="nav-links">';
    foreach ($items as [$page, $label]) {
        if ($label === (string) $current && $page === $current) {
            echo '<span aria-current="page" class="page-numbers current">' . esc_html($label) . '</span>';
        } else {
            echo '<a href="' . esc_url(get_pagenum_link($page)) . '" class="page-numbers">' . esc_html($label) . '</a>';
        }
    }
    echo '</div></nav>';
}

function nc_breadcrumb(array $items): void
{
    echo '<nav aria-label="パンくずリスト" class="breadcrumb breadcrumb--wide">';
    foreach ($items as $i => $item) {
        if ($i > 0) {
            echo '<span class="breadcrumb__sep">›</span>';
        }
        if (!empty($item[1])) {
            echo '<a href="' . esc_url($item[1]) . '" class="breadcrumb__link">' . esc_html($item[0]) . '</a>';
        } else {
            echo '<span>' . esc_html($item[0]) . '</span>';
        }
    }
    echo '</nav>';
}

function nc_category(): ?WP_Term
{
    $cats = get_the_category();
    return $cats ? $cats[0] : null;
}
