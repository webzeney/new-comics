<?php get_header(); ?>
<article aria-labelledby="page-title" class="panel">
<?php nc_breadcrumb([['トップ', nc_site_url() . '/'], [is_category() ? single_cat_title('', false) : '特集', null]]); ?>
<div class="doc doc--wide">
<div class="page_head page_head--nemu">
<div class="heading">
<span class="heading__en"><?php echo is_category('news') ? 'NEWS' : 'FEATURE'; ?></span>
<h1 id="page-title" class="heading__title"><?php echo is_category() ? esc_html(single_cat_title('', false)) : '特集'; ?></h1>
</div>
<?php echo nc_nemu_head(); ?>
</div>
<?php if (have_posts()): ?>
<ul class="feature_list">
<?php while (have_posts()): the_post(); $cat = nc_category(); ?>
<li class="feature_list__item">
<a href="<?php the_permalink(); ?>" class="feature_list__link">
<?php if (has_post_thumbnail()): $banner = nc_banner_url(); ?><span class="feature_list__thumb<?php echo $banner ? ' feature_list__thumb--banner' : ''; ?>"><?php if ($banner): ?><picture><source media="(min-width: 721px)" srcset="<?php echo esc_url($banner); ?>"><?php endif; ?><?php the_post_thumbnail('large', ['class' => 'feature_list__img', 'alt' => '', 'loading' => 'lazy']); ?><?php if ($banner): ?></picture><?php endif; ?></span><?php endif; ?>
<span class="feature_list__text">
<span class="feature_list__meta"><time class="feature_list__date" datetime="<?php echo esc_attr(get_the_date('Y-m-d')); ?>"><?php echo esc_html(get_the_date('Y.m.d')); ?></time><?php if ($cat): ?><span class="feature_list__tag"><?php echo esc_html($cat->name); ?></span><?php endif; ?></span>
<span class="feature_list__title"><?php the_title(); ?></span>
<span class="feature_list__excerpt"><?php echo esc_html(get_the_excerpt()); ?></span>
</span>
</a>
</li>
<?php endwhile; ?>
</ul>
<?php nc_pager(); ?>
<?php else: ?>
<p class="feature_list__empty">特集記事は準備中です。</p>
<?php endif; ?>
</div>
</article>
<?php get_footer(); ?>
