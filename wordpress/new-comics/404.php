<?php get_header(); ?>
<article aria-labelledby="page-title" class="panel">
<?php nc_breadcrumb([['トップ', nc_site_url() . '/'], ['ページが見つかりません', null]]); ?>
<div class="doc">
<div class="heading">
<span class="heading__en">NOT FOUND</span>
<h1 id="page-title" class="heading__title">ページが見つかりません</h1>
</div>
<p class="doc__text">お探しのページは移動または削除された可能性があります。</p>
<a href="<?php echo esc_url(home_url('/')); ?>" class="article__back">特集の一覧へ</a>
</div>
</article>
<?php get_footer(); ?>
