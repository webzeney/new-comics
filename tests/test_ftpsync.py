import ftplib
import json
import unittest

from newcomics import ftpsync


class FakeFtp:
    def __init__(self, files):
        self.files = files

    def retrbinary(self, cmd, write):
        name = cmd.split("/")[-1]
        if name not in self.files:
            raise ftplib.error_perm("550")
        write(self.files[name])


def conn(files):
    c = ftpsync.Conn({}, "/site/")
    c.ftp = FakeFtp(files)
    return c


class StateTest(unittest.TestCase):
    def test_state_file_is_hidden_from_browsers(self):
        self.assertTrue(ftpsync.STATE_NAME.startswith(".ht"))

    def test_reads_old_state_once_and_asks_to_empty_it(self):
        old = json.dumps({"files": {"a.html": "x"}}).encode()
        self.assertEqual(conn({ftpsync.OLD_STATE_NAME: old}).read_state(), ({"a.html": "x"}, True))

    def test_prefers_new_state(self):
        new = json.dumps({"files": {"b.html": "y"}}).encode()
        self.assertEqual(conn({ftpsync.STATE_NAME: new, ftpsync.OLD_STATE_NAME: b"{}"}).read_state(), ({"b.html": "y"}, False))

    def test_no_state(self):
        self.assertEqual(conn({}).read_state(), ({}, False))


if __name__ == "__main__":
    unittest.main()
