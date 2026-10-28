"""転送先の確認。

公開リポジトリの Actions ログは誰でも見られるため、サーバー上のフォルダ名や
ファイル名の一覧は出力しない。転送先フォルダについて、決まった項目の有無だけを出す。
"""
import ftplib
import os
import sys

EXPECTED = ["feature"]
LEFTOVER = ["wp-config.php", "wp-login.php", "wp-admin", "wp-includes", "xmlrpc.php"]


def names(ftp):
    try:
        return {n.rsplit("/", 1)[-1] for n in ftp.nlst()}
    except ftplib.error_perm:
        return set()


def main():
    host = os.environ["FTP_SERVER"]
    user = os.environ["FTP_USERNAME"]
    password = os.environ["FTP_PASSWORD"]
    target = os.environ["FTP_DIR"]
    ftp = ftplib.FTP_TLS(host, timeout=30)
    ftp.login(user, password)
    ftp.prot_p()
    try:
        ftp.cwd(target)
    except ftplib.error_perm:
        print("転送先フォルダが見つかりません。FTP_DIR を確認してください。")
        return 1
    found = names(ftp)
    ftp.quit()
    print(f"転送先フォルダ：あり（項目数 {len(found)}）")
    ok = True
    for name in EXPECTED:
        has = name in found
        print(f"{name}：{'あり' if has else 'なし'}")
        ok = ok and has
    for name in LEFTOVER:
        if name in found:
            print(f"{name}：あり（直下に WordPress のファイルが残っています）")
            ok = False
    print(f"index.html：{'あり' if 'index.html' in found else 'なし'}")
    if not ok:
        print("転送先として想定と違う点があります。転送は行わないでください。")
        return 1
    print("転送先は new-comics.jp の公開フォルダと判断できます。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
