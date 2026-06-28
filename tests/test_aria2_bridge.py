"""Tests for core/aria2_bridge.py — DownloadTask, Aria2Bridge singleton."""

from core.aria2_bridge import Aria2Bridge, DownloadTask, get_bridge


class TestDownloadTask:
    def test_defaults(self):
        t = DownloadTask(gid="abc", url="http://example.com/file")
        assert t.gid == "abc"
        assert t.url == "http://example.com/file"
        assert t.status == "waiting"
        assert t.total_length == 0
        assert t.completed_length == 0
        assert t.progress == 0.0

    def test_from_aria2_minimal(self):
        data = {"gid": "1", "status": "active"}
        t = DownloadTask.from_aria2(data)
        assert t.gid == "1"
        assert t.status == "active"

    def test_from_aria2_with_progress(self):
        data = {
            "gid": "2",
            "status": "active",
            "totalLength": "1000",
            "completedLength": "500",
            "downloadSpeed": "100",
        }
        t = DownloadTask.from_aria2(data)
        assert t.total_length == 1000
        assert t.completed_length == 500
        assert t.progress == 50.0
        assert t.download_speed == 100

    def test_from_aria2_zero_total(self):
        data = {"gid": "3", "totalLength": "0", "completedLength": "0"}
        t = DownloadTask.from_aria2(data)
        assert t.progress == 0.0

    def test_from_aria2_with_files(self):
        data = {
            "gid": "4",
            "files": [{"uris": [{"uri": "http://example.com/file.zip"}]}],
        }
        t = DownloadTask.from_aria2(data)
        assert t.url == "http://example.com/file.zip"

    def test_from_aria2_no_files(self):
        data = {"gid": "5"}
        t = DownloadTask.from_aria2(data)
        assert t.url == ""

    def test_from_aria2_error(self):
        data = {"gid": "6", "status": "error", "errorMessage": "not found"}
        t = DownloadTask.from_aria2(data)
        assert t.status == "error"
        assert t.error_message == "not found"


class TestAria2Bridge:
    def test_singleton(self):
        b1 = get_bridge()
        b2 = get_bridge()
        assert b1 is b2
        assert isinstance(b1, Aria2Bridge)

    def test_has_default_dir(self):
        from core.aria2_bridge import DEFAULT_DIR
        assert DEFAULT_DIR.exists()
