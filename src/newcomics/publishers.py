"""出版社名と URL 用の名前（slug）の対応。

楽天ブックスなどから届く出版社名を、サイト内で使う1つの出版社にまとめる。
表にない出版社は名前から作った仮の slug にし、取得のログに出す。見つけたら表に足す。
"""
import hashlib
import re
import unicodedata

PUBLISHERS = {
    "kadokawa": ("KADOKAWA", ["KADOKAWA", "角川書店", "アスキー・メディアワークス", "エンターブレイン", "メディアファクトリー", "富士見書房"]),
    "kodansha": ("講談社", ["講談社"]),
    "shogakukan": ("小学館", ["小学館"]),
    "shueisha": ("集英社", ["集英社"]),
    "akitashoten": ("秋田書店", ["秋田書店"]),
    "square-enix": ("スクウェア・エニックス", ["スクウェア・エニックス", "スクウェアエニックス"]),
    "futabasha": ("双葉社", ["双葉社"]),
    "ichijinsha": ("一迅社", ["一迅社"]),
    "houbunsha": ("芳文社", ["芳文社"]),
    "hakusensha": ("白泉社", ["白泉社"]),
    "takeshobo": ("竹書房", ["竹書房"]),
    "overlap": ("オーバーラップ", ["オーバーラップ"]),
    "shonengahosha": ("少年画報社", ["少年画報社"]),
    "harpercollins": ("ハーパーコリンズ・ジャパン", ["ハーパーコリンズ・ジャパン", "ハーパーコリンズジャパン"]),
    "starts": ("スターツ出版", ["スターツ出版"]),
    "leed": ("リイド社", ["リイド社"]),
    "alphapolis": ("アルファポリス", ["アルファポリス"]),
    "got": ("ジーオーティー", ["ジーオーティー"]),
    "hifumi": ("一二三書房", ["一二三書房"]),
    "tobooks": ("TOブックス", ["TOブックス"]),
    "ktc": ("キルタイムコミュニケーション", ["キルタイムコミュニケーション"]),
    "mag-garden": ("マッグガーデン", ["マッグガーデン"]),
    "shinchosha": ("新潮社", ["新潮社"]),
    "earth-star": ("アース・スター エンターテイメント", ["アース・スター エンターテイメント", "アース・スターエンターテイメント", "泰文堂"]),
    "nihonbungeisha": ("日本文芸社", ["日本文芸社"]),
    "coamix": ("コアミックス", ["コアミックス"]),
    "heros": ("ヒーローズ", ["ヒーローズ"]),
    "kaiohsha": ("海王社", ["海王社"]),
    "libre": ("リブレ", ["リブレ"]),
    "tokuma": ("徳間書店", ["徳間書店"]),
    "suiseisha": ("彗星社", ["彗星社"]),
    "shufu-to-seikatsu": ("主婦と生活社", ["主婦と生活社"]),
    "sb-creative": ("SBクリエイティブ", ["SBクリエイティブ"]),
    "wani-magazine": ("ワニマガジン社", ["ワニマガジン社"]),
    "gentosha-comics": ("幻冬舎コミックス", ["幻冬舎コミックス"]),
    "shinshokan": ("新書館", ["新書館"]),
    "flex-comix": ("フレックスコミックス", ["フレックスコミックス"]),
    "number-nine": ("ナンバーナイン", ["ナンバーナイン"]),
    "bunkasha": ("ぶんか社", ["ぶんか社"]),
    "shodensha": ("祥伝社", ["祥伝社"]),
    "fanguild": ("ファンギルド", ["ファンギルド"]),
    "bright": ("ブライト出版", ["ブライト出版"]),
    "mugenup": ("MUGENUP", ["MUGENUP"]),
    "coremagazine": ("コアマガジン", ["コアマガジン"]),
    "hobbyjapan": ("ホビージャパン", ["ホビージャパン"]),
    "shusuisha": ("秋水社", ["秋水社"]),
    "daitosha": ("大都社", ["大都社"]),
    "frontier-works": ("フロンティアワークス", ["フロンティアワークス"]),
    "j-publishing": ("Jパブリッシング", ["Jパブリッシング"]),
    "micromagazine": ("マイクロマガジン社", ["マイクロマガジン社"]),
    "tinet": ("ティーアイネット", ["ティーアイネット"]),
    "bunendo": ("文苑堂", ["文苑堂"]),
    "taiyohtosho": ("大洋図書", ["大洋図書"]),
    "printemps": ("プランタン出版", ["プランタン出版"]),
    "angel": ("エンジェル出版", ["エンジェル出版"]),
    "akaneshinsha": ("茜新社", ["茜新社"]),
    "taiseisha": ("大誠社", ["大誠社"]),
    "j-n": ("実業之日本社", ["実業之日本社"]),
    "bunshun": ("文藝春秋", ["文藝春秋", "文芸春秋"]),
    "hit": ("ヒット出版社", ["ヒット出版社"]),
    "eastpress": ("イースト・プレス", ["イースト・プレス", "イーストプレス"]),
    "tokyomangasha": ("東京漫画社", ["東京漫画社"]),
    "g-walk": ("ジーウォーク", ["ジーウォーク"]),
    "takarajimasha": ("宝島社", ["宝島社"]),
    "asahi": ("朝日新聞出版", ["朝日新聞出版"]),
    "cosmic": ("コスミック出版", ["コスミック出版"]),
    "mobile-media-research": ("モバイルメディアリサーチ", ["モバイルメディアリサーチ"]),
    "kobunsha": ("光文社", ["光文社"]),
    "vivion": ("viviON", ["viviON"]),
    "chouxcreme": ("シュークリーム", ["シュークリーム"]),
    "chloe": ("クロエ出版", ["クロエ出版"]),
    "solajima": ("ソラジマ", ["ソラジマ"]),
    "sanko": ("三交社", ["三交社"]),
    "haseisha": ("波星社", ["波星社"]),
    "fusion-product": ("ふゅーじょんぷろだくと", ["ふゅーじょんぷろだくと"]),
    "oakla": ("オークラ出版", ["オークラ出版"]),
    "blast": ("ブラスト出版", ["ブラスト出版"]),
    "futami": ("二見書房", ["二見書房"]),
    "wani-books": ("ワニブックス", ["ワニブックス"]),
    "kasakura": ("笠倉出版社", ["笠倉出版社"]),
    "sanwa": ("三和出版", ["三和出版"]),
    "tatsumi": ("辰巳出版", ["辰巳出版"]),
    "drecom": ("ドリコム", ["ドリコム"]),
    "renga": ("れんが書房新社", ["れんが書房新社"]),
    "golf-digest": ("ゴルフダイジェスト社", ["ゴルフダイジェスト社"]),
    "seisensha": ("青泉社", ["青泉社"]),
    "gakken": ("Gakken", ["Gakken", "学研プラス", "学研"]),
    "one-publishing": ("ワン・パブリッシング", ["ワン・パブリッシング", "ワンパブリッシング"]),
    "seirinkogeisha": ("青林工藝舎", ["青林工藝舎", "青林工芸舎"]),
    "mediax": ("メディアックス", ["メディアックス"]),
    "ammo98": ("アムモ98", ["アムモ98"]),
    "eiwa": ("英和出版社", ["英和出版社"]),
    "culture-entertainment": ("カルチュア・エンタテインメント", ["カルチュア・エンタテインメント"]),
    "ohta": ("太田出版", ["太田出版"]),
    "kayashobo": ("かや書房", ["かや書房"]),
    "seiunsha": ("星雲社", ["星雲社"]),
    "gentosha": ("幻冬舎", ["幻冬舎"]),
    "shogakukan-creative": ("小学館クリエイティブ", ["小学館クリエイティブ"]),
    "nippan-ips": ("日販アイ・ピー・エス", ["日販アイ・ピー・エス"]),
}


def _key(name):
    t = unicodedata.normalize("NFKC", name or "")
    t = re.sub(r"\(株\)|株式会社|有限会社", "", t)
    return re.sub(r"[\s・･]", "", t).lower()


_INDEX = {}
for _slug, (_name, _aliases) in PUBLISHERS.items():
    for _alias in [_name] + _aliases:
        _INDEX[_key(_alias)] = _slug


def resolve(raw_name):
    """出版社名から (slug, 表示名, 表にあったか) を返す。"""
    raw = unicodedata.normalize("NFKC", raw_name or "").strip()
    slug = _INDEX.get(_key(raw))
    if slug:
        return slug, PUBLISHERS[slug][0], True
    name = re.sub(r"\(株\)|株式会社|有限会社", "", raw).strip() or "不明"
    return "p" + hashlib.sha1(_key(name).encode()).hexdigest()[:8], name, False
