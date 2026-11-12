"""お問い合わせの通知先の設定ファイル（contact/config.php）を書き出す。通知先は環境変数 CONTACT_TO（GitHub の Secrets）から読み、ログには出さない。"""
import json
import os
import sys

out = sys.argv[1]
to = os.environ.get("CONTACT_TO", "").strip()
with open(os.path.join(out, "contact", "config.php"), "w", encoding="utf-8") as f:
    f.write("<?php\nreturn ['to' => " + json.dumps(to) + "];\n")
print("通知先：" + ("設定あり" if to else "未設定（受信内容はサーバーに保存のみ）"))
