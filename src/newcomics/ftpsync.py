"""FTPS で公開フォルダへ転送する（差分のみ・並列・途中から再開できる）。

サーバーの転送先フォルダに記録ファイル（STATE_NAME）を置き、前回送ったファイルの
ハッシュと比べて、変わったファイルだけを送る。一定数を送るごとに記録を書き込むので、
途中で接続が切れても、次の実行では残りだけを送る。

公開リポジトリの Actions ログは誰でも見られるため、ファイル名やフォルダ名は出力しない。
"""
import argparse
import fnmatch
import ftplib
import hashlib
import hmac
import io
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

STATE_NAME = ".nc-sync-state.json"
SAVE_EVERY = 150
RETRIES = 6
TIMEOUT = 60


def sha256(path, key=b""):
    h = hmac.new(key, digestmod="sha256") if key else hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def local_files(root, excludes, key=b""):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel == STATE_NAME or any(fnmatch.fnmatch(rel, pat) for pat in excludes):
            continue
        out[rel] = sha256(p, key)
    return out


def order_key(rel):
    """HTML などのページを先に、CSS・JS を後に、トップページを最後に送る。"""
    if rel == "index.html":
        return (3, rel)
    if rel.startswith("assets/"):
        return (2, rel)
    if rel.endswith(".html"):
        return (0, rel)
    return (1, rel)


class Conn:
    def __init__(self, env, base):
        self.env = env
        self.base = base.rstrip("/") + "/"
        self.ftp = None
        self.dirs = set()

    def open(self):
        self.close()
        if self.env.get("FTPSYNC_PLAIN") == "1":
            ftp = ftplib.FTP(timeout=TIMEOUT)
            ftp.connect(self.env["FTP_SERVER"], int(self.env.get("FTPSYNC_PORT", "21")))
            ftp.login(self.env["FTP_USERNAME"], self.env["FTP_PASSWORD"])
        else:
            ftp = ftplib.FTP_TLS(self.env["FTP_SERVER"], timeout=TIMEOUT)
            ftp.login(self.env["FTP_USERNAME"], self.env["FTP_PASSWORD"])
            ftp.prot_p()
        ftp.set_pasv(True)
        self.ftp = ftp

    def close(self):
        if self.ftp is not None:
            try:
                self.ftp.quit()
            except Exception:
                try:
                    self.ftp.close()
                except Exception:
                    pass
        self.ftp = None

    def ensure_dir(self, rel_dir):
        if not rel_dir or rel_dir in self.dirs:
            return
        path = ""
        for part in rel_dir.split("/"):
            path = f"{path}/{part}" if path else part
            if path in self.dirs:
                continue
            try:
                self.ftp.mkd(self.base + path)
            except ftplib.error_perm:
                pass
            self.dirs.add(path)

    def ensure_base(self):
        lead = "/" if self.base.startswith("/") else ""
        path = ""
        for part in [p for p in self.base.split("/") if p]:
            path = f"{path}/{part}" if path else lead + part
            try:
                self.ftp.mkd(path)
            except ftplib.error_perm:
                pass

    def put_bytes(self, rel, data):
        self.ftp.storbinary(f"STOR {self.base}{rel}", io.BytesIO(data))

    def upload(self, local_root, rel):
        rel_dir = rel.rsplit("/", 1)[0] if "/" in rel else ""
        with open(Path(local_root) / rel, "rb") as f:
            try:
                self.ftp.storbinary(f"STOR {self.base}{rel}", f)
            except ftplib.error_perm:
                self.ensure_dir(rel_dir)
                f.seek(0)
                self.ftp.storbinary(f"STOR {self.base}{rel}", f)

    def delete(self, rel):
        try:
            self.ftp.delete(self.base + rel)
        except ftplib.error_perm:
            pass

    def read_state(self):
        buf = io.BytesIO()
        try:
            self.ftp.retrbinary(f"RETR {self.base}{STATE_NAME}", buf.write)
        except ftplib.error_perm:
            return {}
        try:
            data = json.loads(buf.getvalue().decode("utf-8"))
            return dict(data.get("files", {}))
        except (ValueError, AttributeError):
            return {}


def with_retry(conn, fn, *args):
    for attempt in range(1, RETRIES + 1):
        try:
            if conn.ftp is None:
                conn.open()
            return fn(*args)
        except (ftplib.error_temp, ftplib.error_reply, OSError, EOFError) as exc:
            conn.close()
            if attempt == RETRIES:
                raise
            wait = min(60, 5 * attempt)
            print(f"  接続をやり直します（{attempt}回目・{type(exc).__name__}）", flush=True)
            time.sleep(wait)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--local", required=True)
    ap.add_argument("--remote", required=True)
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--make-base", action="store_true", help="転送先フォルダがなければ作る")
    ap.add_argument("--delete", action="store_true", help="前回送ったが今回ないファイルを消す")
    args = ap.parse_args(argv)
    env = dict(os.environ)

    # 記録ファイルは公開フォルダに置くため、中身を推測されないよう鍵付きのハッシュにする
    files = local_files(args.local, args.exclude, env.get("FTP_PASSWORD", "").encode("utf-8"))
    main_conn = Conn(env, args.remote)
    if args.make_base:
        with_retry(main_conn, main_conn.ensure_base)
    old = with_retry(main_conn, main_conn.read_state)
    todo = sorted((r for r, h in files.items() if old.get(r) != h), key=order_key)
    gone = sorted(r for r in old if r not in files) if args.delete else []
    print(f"ファイル数 {len(files)}／送るもの {len(todo)}／消すもの {len(gone)}", flush=True)

    state = dict(old)
    lock = threading.Lock()
    done_count = [0]
    errors = []

    def save_state(final=False):
        with lock:
            snap = {"files": dict(state)}
        data = json.dumps(snap, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with_retry(main_conn, main_conn.put_bytes, STATE_NAME, data)
        if final:
            print("記録を保存しました", flush=True)

    # ページ・その他のファイルを並列で送り、CSS・JS とトップページは最後にまとめて送る
    first = [r for r in todo if order_key(r)[0] < 2]
    last = [r for r in todo if order_key(r)[0] >= 2]

    def run_batch(batch, workers):
        q = queue.Queue()
        for r in batch:
            q.put(r)

        def worker():
            conn = Conn(env, args.remote)
            try:
                while True:
                    try:
                        rel = q.get_nowait()
                    except queue.Empty:
                        return
                    try:
                        with_retry(conn, conn.upload, args.local, rel)
                    except Exception as exc:
                        with lock:
                            errors.append(type(exc).__name__)
                        continue
                    with lock:
                        state[rel] = files[rel]
                        done_count[0] += 1
                        n = done_count[0]
                    if n % SAVE_EVERY == 0:
                        print(f"  {n}/{len(todo)} 件を送りました", flush=True)
                        save_state()
            finally:
                conn.close()

        threads = [threading.Thread(target=worker) for _ in range(max(1, min(workers, len(batch))))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    start = time.time()
    run_batch(first, args.workers)
    if not errors:
        run_batch(last, 1)
    for rel in gone:
        try:
            with_retry(main_conn, main_conn.delete, rel)
            state.pop(rel, None)
        except Exception as exc:
            errors.append(type(exc).__name__)
    save_state(final=True)
    main_conn.close()
    minutes = (time.time() - start) / 60
    print(f"送信 {done_count[0]} 件・{minutes:.1f} 分", flush=True)
    if errors:
        print(f"送れなかったファイルが {len(errors)} 件あります。もう一度実行すると残りだけを送ります。", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
