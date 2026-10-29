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
    wp_enqueue_style('nc-fonts', 'https://fonts.googleapis.com/css2?family=Fredoka:wght@300;400;500;600&family=Noto+Sans+JP:wght@400;500;700;900&display=swap', [], null);
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
