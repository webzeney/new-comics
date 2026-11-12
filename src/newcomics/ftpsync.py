"""FTPS で公開フォルダへ転送する（差分のみ・並列・途中から再開できる）。

サーバーの転送先フォルダに記録ファイル（STATE_NAME）を置き、前回送ったファイルの
ハッシュと比べて、変わったファイルだけを送る。記録ファイルは名前を「.ht」で始め、
ブラウザから読めないようにする（Apache は .ht で始まるファイルを公開しない）。一定数を送るごとに記録を書き込むので、
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

STATE_NAME = ".htncsync.json"
OLD_STATE_NAME = ".nc-sync-state.json"  # 以前の記録ファイル（ブラウザから読めたため、中身を空にして使わない）
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
        if rel in (STATE_NAME, OLD_STATE_NAME) or any(fnmatch.fnmatch(rel, pat) for pat in excludes):
            continue
        out[rel] = sha256(p, key)
    return out


def order_key(rel):
    """ページが読み込む共通部品を最初に、HTML などのページを次に、CSS・JS を後に、トップページを最後に送る。"""
    if rel.startswith("assets/partials/"):
        return (-1, rel)
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

    def read_file(self, name):
        buf = io.BytesIO()
        try:
            self.ftp.retrbinary(f"RETR {self.base}{name}", buf.write)
        except ftplib.error_perm:
            return None
        try:
            return dict(json.loads(buf.getvalue().decode("utf-8")).get("files", {}))
        except (ValueError, AttributeError):
            return {}

    def read_state(self):
        """記録を読む。新しい記録ファイルがまだなければ、以前の記録ファイルを読む（1回目だけ）。"""
        state = self.read_file(STATE_NAME)
        old = self.read_file(OLD_STATE_NAME)
        return (state if state is not None else (old or {})), bool(old)


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
    ap.add_argument("--first", action="append", default=[], help="先に送るページ（パターン。日付で変わるページなど）")
    ap.add_argument("--until", type=int, default=0, help="この時刻（UNIX 時刻）を過ぎたら新しいファイルを送り始めない（残りは次の転送で送る）")
    args = ap.parse_args(argv)
    env = dict(os.environ)

    # 記録ファイルは公開フォルダに置くため、中身を推測されないよう鍵付きのハッシュにする
    files = local_files(args.local, args.exclude, env.get("FTP_PASSWORD", "").encode("utf-8"))
    main_conn = Conn(env, args.remote)
    if args.make_base:
        with_retry(main_conn, main_conn.ensure_base)
    old, old_file_left = with_retry(main_conn, main_conn.read_state)
    todo = sorted((r for r, h in files.items() if old.get(r) != h), key=order_key)
    print(f"ファイル数 {len(files)}／送るもの {len(todo)}", flush=True)

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

    # ページ・その他のファイルを並列で送り、CSS・JS とトップページは最後にまとめて送る。
    # --first のページは先に送る（CSS・JS を送るときは、トップページだけはそのあとに回す）
    assets_change = any(order_key(r)[0] == 2 for r in todo)
    def is_first(r):
        if r == "index.html" and assets_change:
            return False
        return any(fnmatch.fnmatch(r, pat) for pat in args.first)
    parts = [r for r in todo if order_key(r)[0] < 0]
    early = [r for r in todo if order_key(r)[0] >= 0 and is_first(r)]
    first = [r for r in todo if 0 <= order_key(r)[0] < 2 and not is_first(r)]
    last = [r for r in todo if order_key(r)[0] >= 2 and not is_first(r)]

    def run_batch(batch, workers):
        q = queue.Queue()
        for r in batch:
            q.put(r)

        def worker():
            conn = Conn(env, args.remote)
            try:
                while True:
                    if args.until and time.time() >= args.until:
                        return
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
    run_batch(parts, args.workers)
    if not errors and early:
        run_batch(early, args.workers)
        print(f"先に送るページ {len(early)} 件を送りました（{(time.time() - start) / 60:.1f} 分）", flush=True)
    if not errors:
        run_batch(first, args.workers)
    if not errors:
        run_batch(last, 1)
    save_state(final=True)
    if old_file_left:
        # 以前の記録ファイルはブラウザから読めたので、中身を空にしておく
        with_retry(main_conn, main_conn.put_bytes, OLD_STATE_NAME, b"{}")
        print("以前の記録ファイルを空にしました", flush=True)
    main_conn.close()
    minutes = (time.time() - start) / 60
    print(f"送信 {done_count[0]} 件・{minutes:.1f} 分", flush=True)
    if args.until and done_count[0] < len(todo) and not errors:
        print(f"時間になったため {len(todo) - done_count[0]} 件は次の転送で送ります", flush=True)
    if errors:
        print(f"送れなかったファイルが {len(errors)} 件あります。もう一度実行すると残りだけを送ります。", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
