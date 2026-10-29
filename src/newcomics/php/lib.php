<?php
declare(strict_types=1);

const NC_KINDS = ['修正' => '掲載内容の修正', '削除' => '掲載の削除依頼', 'その他' => 'その他'];
const NC_LIMITS = ['name' => 100, 'email' => 254, 'url' => 500, 'body' => 5000];
const NC_RATE_LIMIT = 5;
const NC_RATE_WINDOW = 3600;

function h($value): string
{
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

function nc_config(): array
{
    $file = __DIR__ . '/config.php';
    if (!is_file($file)) {
        return [];
    }
    $config = require $file;
    return is_array($config) ? $config : [];
}

function nc_session(): void
{
    session_name('nc_contact');
    session_start([
        'cookie_httponly' => true,
        'cookie_samesite' => 'Lax',
        'cookie_secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off',
        'use_strict_mode' => true,
    ]);
}

function nc_text(string $key): string
{
    $value = isset($_POST[$key]) && is_string($_POST[$key]) ? $_POST[$key] : '';
    $value = str_replace(["\r\n", "\r"], "\n", $value);
    $value = preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u', '', $value) ?? '';
    return trim($value);
}

function nc_input(): array
{
    $kind = nc_text('kind');
    return [
        'kind' => array_key_exists($kind, NC_KINDS) ? $kind : '',
        'name' => str_replace("\n", ' ', nc_text('name')),
        'email' => str_replace("\n", '', nc_text('email')),
        'url' => str_replace("\n", '', nc_text('url')),
        'body' => nc_text('body'),
        'agree' => nc_text('agree') === '1',
        'website' => nc_text('website'),
    ];
}

function nc_validate(array $v): array
{
    $errors = [];
    if ($v['kind'] === '') {
        $errors[] = 'お問い合わせの種類を選んでください。';
    }
    if ($v['email'] === '' || filter_var($v['email'], FILTER_VALIDATE_EMAIL) === false) {
        $errors[] = 'メールアドレスを正しく入力してください。';
    }
    if ($v['url'] !== '' && !preg_match('#\Ahttps?://#', $v['url'])) {
        $errors[] = '対象ページのURLは http:// または https:// から入力してください。';
    }
    if ($v['body'] === '') {
        $errors[] = 'お問い合わせ内容を入力してください。';
    }
    foreach (NC_LIMITS as $key => $limit) {
        if (mb_strlen($v[$key], 'UTF-8') > $limit) {
            $errors[] = '入力が長すぎる項目があります。';
            break;
        }
    }
    if (!$v['agree']) {
        $errors[] = 'プライバシーポリシーへの同意が必要です。';
    }
    return $errors;
}

function nc_data_dir(): string
{
    $dir = __DIR__ . '/_data';
    if (!is_dir($dir)) {
        mkdir($dir, 0700, true);
    }
    $guard = $dir . '/.htaccess';
    if (!is_file($guard)) {
        file_put_contents($guard, "Order allow,deny\nDeny from all\n");
    }
    return $dir;
}

function nc_rate_ok(string $ip): bool
{
    $file = nc_data_dir() . '/rate.json';
    $fp = fopen($file, 'c+');
    if ($fp === false) {
        return true;
    }
    flock($fp, LOCK_EX);
    $data = json_decode(stream_get_contents($fp) ?: '{}', true) ?: [];
    $now = time();
    $key = hash('sha256', $ip);
    $hits = array_values(array_filter($data[$key] ?? [], fn($t) => $t > $now - NC_RATE_WINDOW));
    $ok = count($hits) < NC_RATE_LIMIT;
    if ($ok) {
        $hits[] = $now;
    }
    $data[$key] = $hits;
    foreach ($data as $k => $list) {
        if (!array_filter($list, fn($t) => $t > $now - NC_RATE_WINDOW)) {
            unset($data[$k]);
        }
    }
    ftruncate($fp, 0);
    rewind($fp);
    fwrite($fp, json_encode($data));
    flock($fp, LOCK_UN);
    fclose($fp);
    return $ok;
}

function nc_save(array $v, string $ip): void
{
    $record = [
        'received_at' => date('c'),
        'kind' => $v['kind'],
        'name' => $v['name'],
        'email' => $v['email'],
        'url' => $v['url'],
        'body' => $v['body'],
        'ip' => $ip,
        'user_agent' => substr((string)($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 300),
    ];
    $file = nc_data_dir() . '/messages-' . date('Ym') . '.jsonl';
    file_put_contents($file, json_encode($record, JSON_UNESCAPED_UNICODE) . "\n", FILE_APPEND | LOCK_EX);
}

function nc_notify(array $v, array $config): bool
{
    $to = $config['to'] ?? '';
    if ($to === '' || filter_var($to, FILTER_VALIDATE_EMAIL) === false) {
        return false;
    }
    mb_language('Japanese');
    mb_internal_encoding('UTF-8');
    $subject = '[漫画新刊JP] お問い合わせ（' . NC_KINDS[$v['kind']] . '）';
    $lines = [
        '漫画新刊JPのお問い合わせフォームから送信がありました。',
        '',
        '種類：' . NC_KINDS[$v['kind']],
        'お名前：' . ($v['name'] !== '' ? $v['name'] : '（未記入）'),
        'メールアドレス：' . $v['email'],
        '対象ページ：' . ($v['url'] !== '' ? $v['url'] : '（未記入）'),
        '',
        '内容：',
        $v['body'],
        '',
        '受付日時：' . date('Y-m-d H:i:s'),
    ];
    $from = $config['from'] ?? 'noreply@new-comics.jp';
    $headers = 'From: ' . $from . "\r\n" . 'Reply-To: ' . $v['email'];
    return mb_send_mail($to, $subject, implode("\n", $lines), $headers);
}
