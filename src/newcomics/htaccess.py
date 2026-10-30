"""転送先の一番上の .htaccess に、.html を PHP として動かす設定を足す。

ページは head・サイドメニュー・フッターを PHP の readfile で読み込むので、.html のまま PHP を動かす必要がある。
サーバーにはもとから .htaccess があるため、上書きはせず、決まった印のついた行がなければ末尾に足すだけにする。
足す前の .htaccess は「.htaccess.nc-backup」として同じ場所に残す（.ht で始まるのでブラウザからは見えない）。
公開リポジトリの Actions ログは誰でも見られるため、.htaccess の中身は出力しない。
"""
import ftplib
import io
import os
import sys

MARK = "# new-comics: html-php"
BLOCK = MARK + "\n<FilesMatch \"\\.html$\">\nAddHandler php-script .php .html\n</FilesMatch>\n"


def read(ftp, name):
    buf = io.BytesIO()
    try:
        ftp.retrbinary(f"RETR {name}", buf.write)
    except ftplib.error_perm:
        return None
    return buf.getvalue()


def write(ftp, name, data):
    ftp.storbinary(f"STOR {name}", io.BytesIO(data))


def patched(current):
    """印がなければ末尾に設定を足した中身を返す。足す必要がなければ None。"""
    text = (current or b"").decode("utf-8", errors="surrogateescape")
    if MARK in text:
        return None
    if text and not text.endswith("\n"):
        text += "\n"
    if text:
        text += "\n"
    return (text + BLOCK).encode("utf-8", errors="surrogateescape")


def main():
    ftp = ftplib.FTP_TLS(os.environ["FTP_SERVER"], timeout=60)
    ftp.login(os.environ["FTP_USERNAME"], os.environ["FTP_PASSWORD"])
    ftp.prot_p()
    ftp.cwd(os.environ["FTP_DIR"])
    current = read(ftp, ".htaccess")
    data = patched(current)
    if data is None:
        print(".htaccess：設定は入っています（変更なし）")
    else:
        if current is not None and read(ftp, ".htaccess.nc-backup") is None:
            write(ftp, ".htaccess.nc-backup", current)
            print(".htaccess：もとの内容を控えとして残しました")
        write(ftp, ".htaccess", data)
        if read(ftp, ".htaccess") != data:
            print(".htaccess：書き込んだ内容を確かめられませんでした")
            return 1
        print(".htaccess：.html を PHP として動かす設定を末尾に足しました")
    ftp.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
