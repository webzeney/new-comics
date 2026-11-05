<?php
declare(strict_types=1);
$sid = isset($_GET['s']) && is_string($_GET['s']) ? $_GET['s'] : '';
if (!preg_match('/^[0-9]{1,9}$/', $sid)) {
    http_response_code(404);
    exit;
}
$file = __DIR__ . '/' . $sid . '/calendar.ics';
if (!is_file($file)) {
    http_response_code(404);
    exit;
}
$choices = [
    '7d' => ['-P6DT15H', '1週間後に発売：'],
    '3d' => ['-P2DT15H', '3日後に発売：'],
    '1d' => ['-PT3H', '明日発売：'],
    '0d' => ['PT9H', '今日発売：'],
];
$raw = isset($_GET['alarm']) && is_string($_GET['alarm']) ? $_GET['alarm'] : '1d,0d';
$picked = array_values(array_intersect(array_keys($choices), explode(',', $raw)));
$text = str_replace("\r\n ", '', (string)file_get_contents($file));
$text = preg_replace('/BEGIN:VALARM\r\n.*?END:VALARM\r\n/s', '', $text);
$text = preg_replace_callback('/(SUMMARY:(.*?) 発売日\r\n.*?)(END:VEVENT\r\n)/s', function ($m) use ($choices, $picked) {
    $alarms = '';
    foreach ($picked as $key) {
        $alarms .= "BEGIN:VALARM\r\nACTION:DISPLAY\r\nDESCRIPTION:" . $choices[$key][1] . $m[2] . "\r\nTRIGGER:" . $choices[$key][0] . "\r\nEND:VALARM\r\n";
    }
    return $m[1] . $alarms . $m[3];
}, $text);
$out = '';
foreach (explode("\r\n", rtrim($text, "\r\n")) as $line) {
    $first = true;
    while (strlen($line) > ($first ? 75 : 74)) {
        $part = mb_strcut($line, 0, $first ? 75 : 74, 'UTF-8');
        $out .= ($first ? '' : ' ') . $part . "\r\n";
        $line = substr($line, strlen($part));
        $first = false;
    }
    $out .= ($first ? '' : ' ') . $line . "\r\n";
}
header('Content-Type: text/calendar; charset=utf-8');
header('Cache-Control: public, max-age=3600');
echo $out;
