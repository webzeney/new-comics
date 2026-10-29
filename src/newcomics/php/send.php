<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
date_default_timezone_set('Asia/Tokyo');
nc_session();
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    header('Location: ./', true, 303);
    exit;
}
$token = isset($_POST['token']) && is_string($_POST['token']) ? $_POST['token'] : '';
$expected = $_SESSION['token'] ?? '';
$v = $_SESSION['contact'] ?? null;
if ($expected === '' || !hash_equals($expected, $token) || !is_array($v)) {
    header('Location: ./', true, 303);
    exit;
}
unset($_SESSION['token'], $_SESSION['contact']);
$ip = (string)($_SERVER['REMOTE_ADDR'] ?? '');
if (nc_rate_ok($ip)) {
    nc_save($v, $ip);
    nc_notify($v, nc_config());
}
header('Location: thanks/', true, 303);
exit;
