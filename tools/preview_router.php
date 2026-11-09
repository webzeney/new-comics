<?php
$p = $_SERVER['DOCUMENT_ROOT'] . parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
if (is_dir($p)) $p = rtrim($p, '/') . '/index.html';
if (substr($p, -5) === '.html' && is_file($p)) { chdir(dirname($p)); $__f = $p; (function () use ($__f) { include $__f; })(); return true; }
return false;
