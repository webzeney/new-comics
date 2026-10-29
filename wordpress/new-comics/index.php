<?php get_header(); ?>
<article aria-labelledby="page-title" class="panel">
<?php nc_breadcrumb([['トップ', nc_site_url() . '/'], [is_category() ? single_cat_title('', false) : '特集', null]]); ?>
<div class="doc">
<div class="heading">
<span class="heading__en">FEATURE</span>
<h1 id="page-title" class="heading__title"><?php echo is_category() ? esc_html(single_cat_title('', false)) : '特集'; ?></h1>
</div>
<?php if (have_posts()): ?>
<ul class="feature_list">
<?php while (have_posts()): the_post(); $cat = nc_category(); ?>
<li class="feature_list__item">
<a href="<?php the_permalink(); ?>" class="feature_list__link">
<span class="feature_list__meta"><time class="feature_list__date" datetime="<?php echo esc_attr(get_the_date('Y-m-d')); ?>"><?php echo esc_html(get_the_date('Y.m.d')); ?></time><?php if ($cat): ?><span class="feature_list__tag"><?php echo esc_html($cat->name); ?></span><?php endif; ?></span>
<h2 class="feature_list__title"><?php the_title(); ?></h2>
<p class="feature_list__excerpt"><?php echo esc_html(get_the_excerpt()); ?></p>
</a>
</li>
<?php endwhile; ?>
</ul>
<?php the_posts_pagination(['class' => 'pager', 'mid_size' => 1, 'prev_text' => '‹', 'next_text' => '›']); ?>
<?php else: ?>
<p class="feature_list__empty">特集記事は準備中です。</p>
<?php endif; ?>
</div>
</article>
<?php get_footer(); ?>
