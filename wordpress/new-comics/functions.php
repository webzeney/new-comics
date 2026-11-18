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

/* 看板キャラクター（ねむ）。平日は制服、土日は私服（main.js が data-kumiko-weekend で差し替える） */
function nc_nemu(string $pose, string $text, string $mod = ''): string
{
    $pose = preg_match('/^[a-z0-9]+$/', $pose) ? $pose : 'point';
    $base = nc_site_url() . '/assets/img/kumiko/' . $pose;
    return '<div class="kumiko' . ($mod ? ' kumiko--' . implode(' kumiko--', array_map('esc_attr', explode(' kumiko--', $mod))) : '') . '">'
        . '<img src="' . esc_url($base . '_u.webp') . '" srcset="' . esc_url($base . '_u.webp') . ' 2x" data-kumiko-weekend="' . esc_url($base . '_c.webp') . '" alt="" class="kumiko__image" loading="lazy">'
        . '<p class="kumiko__bubble">' . $text . '</p></div>';
}

/* 記事の本文に [nemu pose="cheer"]セリフ[/nemu] と書くと、ねむが吹き出しで話す。
   置き方は 左 → 右 → 文章の横 の順に入れ替わる。side="left" / "right" / "float" で指定もできる */
add_shortcode('nemu', function ($atts, $content = ''): string {
    static $count = [];
    $atts = shortcode_atts(['pose' => 'point', 'side' => ''], $atts, 'nemu');
    $id = (int) get_the_ID();
    $count[$id] = ($count[$id] ?? 0) + 1;
    $sides = ['left', 'right', 'float'];
    $side = in_array($atts['side'], $sides, true) ? $atts['side'] : $sides[($count[$id] - 1) % 3];
    $mod = 'article' . ($side === 'left' ? '' : ' kumiko--' . $side);
    return nc_nemu((string) $atts['pose'], wp_kses(trim((string) $content), ['br' => [], 'strong' => [], 'a' => ['href' => []]]), $mod);
});

/* 文章の横（float）のねむは、すぐあとに文章が続くところだけにする。
   あとの文章とリストが短く、すぐ表・見出しなどになるときは、右に置く形に変える（2026-11-18 運営者の判断） */
function nc_nemu_float_fit(string $html): string
{
    return preg_replace_callback('/<div class="kumiko kumiko--article kumiko--float">.*?<\/div>/s', function (array $m) use ($html): string {
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
        return $lines >= 6 ? $m[0] : str_replace('kumiko--float', 'kumiko--right', $m[0]);
    }, $html);
}
add_filter('the_content', 'nc_nemu_float_fit', 12);

/* 特集の一覧はコラムだけにする（2026-11-18 運営者の判断） */
add_action('pre_get_posts', function (WP_Query $q): void {
    if (!is_admin() && $q->is_main_query() && $q->is_home()) {
        $q->set('category_name', 'column');
    }
});

/* 一覧と記事のページで、ねむが話すこと */
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
