<?php get_header(); ?>
<?php while (have_posts()): the_post(); $cat = nc_category(); ?>
<article aria-labelledby="page-title" class="panel">
<?php nc_breadcrumb([['トップ', nc_site_url() . '/'], ['特集', home_url('/')], [get_the_title(), null]]); ?>
<div class="article">
<div class="heading">
<span class="heading__en">FEATURE</span>
<h1 id="page-title" class="heading__title"><?php the_title(); ?></h1>
</div>
<div class="article__meta"><time class="article__date" datetime="<?php echo esc_attr(get_the_date('Y-m-d')); ?>"><?php echo esc_html(get_the_date('Y.m.d')); ?></time><?php if ($cat): ?><a href="<?php echo esc_url(get_category_link($cat)); ?>" class="article__tag"><?php echo esc_html($cat->name); ?></a><?php endif; ?></div>
<div class="article__body">
<?php the_content(); ?>
</div>
<p class="article__note">発売日・価格は変更される場合があります。最新の情報は各出版社・販売店でご確認ください。</p>
<a href="<?php echo esc_url(home_url('/')); ?>" class="article__back">特集の一覧へ</a>
</div>
</article>
<?php endwhile; ?>
<?php get_footer(); ?>
