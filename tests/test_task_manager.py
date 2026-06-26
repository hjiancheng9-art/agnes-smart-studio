"""Tests for core.task_manager — persistent task management."""

import json


class TestTaskStatus:
    def test_enum_values(self):
        from core.task_manager import TaskStatus

        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.DELETED.value == "deleted"


class TestTask:
    def test_task_creation(self):
        from core.task_manager import Task, TaskStatus

        task = Task(
            id="task-001",
            subject="Write tests",
            description="Add unit tests",
        )
        assert task.id == "task-001"
        assert task.subject == "Write tests"
        assert task.status == TaskStatus.PENDING
        assert task.blockedBy == []
        assert task.blocks == []

    def test_to_dict(self):
        from core.task_manager import Task

        task = Task(id="t1", subject="test")
        d = task.to_dict()
        assert d["id"] == "t1"
        assert d["status"] == "pending"
        assert isinstance(d, dict)

    def test_from_dict(self):
        from core.task_manager import Task

        data = {
            "id": "t1",
            "subject": "test",
            "status": "pending",
            "description": "",
            "activeForm": "",
            "owner": "",
            "blockedBy": [],
            "blocks": [],
            "metadata": {},
            "created_at": "",
            "updated_at": "",
        }
        task = Task.from_dict(data)
        assert task.id == "t1"
        assert task.subject == "test"


class TestTaskManager:
    def _make_manager(self, tmp_path):
        from core.task_manager import TaskManager

        return TaskManager(path=tmp_path / "tasks.json")

    def test_create_task(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        task = mgr.create("Write tests", "Add unit tests for core modules")
        assert task.id.startswith("task-")
        assert task.subject == "Write tests"
        assert task.status.value == "pending"
        assert task.activeForm == "Write tests"

    def test_create_with_active_form(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        task = mgr.create("Build", activeForm="Building")
        assert task.activeForm == "Building"

    def test_get_task(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        created = mgr.create("Test")
        retrieved = mgr.get(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.subject == "Test"

    def test_get_nonexistent(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr.get("nope") is None

    def test_update_status(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        task = mgr.create("Test")
        updated = mgr.update(task.id, status="in_progress")
        assert updated is not None
        assert updated.status.value == "in_progress"

    def test_update_subject(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        task = mgr.create("Old subject")
        updated = mgr.update(task.id, subject="New subject")
        assert updated is not None
        assert updated.subject == "New subject"

    def test_update_nonexistent(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr.update("nope", subject="x") is None

    def test_list_all(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        mgr.create("Task 1")
        mgr.create("Task 2")
        mgr.create("Task 3")
        tasks = mgr.list()
        assert len(tasks) == 3

    def test_list_excludes_deleted(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        t1 = mgr.create("Active")
        t2 = mgr.create("To delete")
        mgr.delete(t2.id)
        tasks = mgr.list()
        assert len(tasks) == 1
        assert tasks[0].id == t1.id

    def test_list_filter_by_status(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        t1 = mgr.create("Pending")
        t2 = mgr.create("InProgress")
        mgr.update(t2.id, status="in_progress")
        pending = mgr.list(status="pending")
        assert len(pending) == 1
        assert pending[0].id == t1.id

    def test_soft_delete(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        task = mgr.create("Delete me")
        assert mgr.delete(task.id) is True
        assert task.status.value == "deleted"
        assert mgr.delete("nope") is False

    def test_add_blocked_by(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        t1 = mgr.create("Blocker")
        t2 = mgr.create("Blocked")
        assert mgr.add_blocked_by(t2.id, t1.id) is True
        assert t1.id in t2.blockedBy
        assert t2.id in t1.blocks

    def test_add_blocks_reverse(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        t1 = mgr.create("Blocker")
        t2 = mgr.create("Blocked")
        mgr.add_blocks(t1.id, t2.id)
        assert t2.id in t1.blocks

    def test_add_blocked_by_nonexistent(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        t1 = mgr.create("Exists")
        assert mgr.add_blocked_by(t1.id, "nope") is False

    def test_get_blocked_tasks(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        blocker = mgr.create("Blocker")
        blocked = mgr.create("Blocked")
        mgr.add_blocked_by(blocked.id, blocker.id)
        mgr.update(blocker.id, status="in_progress")
        blocked_list = mgr.get_blocked_tasks()
        assert len(blocked_list) == 1
        assert blocked_list[0].id == blocked.id

    def test_get_blocked_tasks_completed_blocker(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        blocker = mgr.create("Blocker")
        blocked = mgr.create("Blocked")
        mgr.add_blocked_by(blocked.id, blocker.id)
        mgr.update(blocker.id, status="completed")
        blocked_list = mgr.get_blocked_tasks()
        assert len(blocked_list) == 0

    def test_get_available_tasks(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        t1 = mgr.create("No deps")
        mgr.get_available_tasks()  # should include t1
        avail = mgr.get_available_tasks()
        assert any(t.id == t1.id for t in avail)

    def test_persistence(self, tmp_path):
        from core.task_manager import TaskManager

        path = tmp_path / "persist_tasks.json"
        mgr1 = TaskManager(path=path)
        mgr1.create("Persistent task")
        # Create new manager loading same file
        mgr2 = TaskManager(path=path)
        tasks = mgr2.list()
        assert len(tasks) == 1
        assert tasks[0].subject == "Persistent task"

    def test_load_corrupted_file(self, tmp_path):
        from core.task_manager import TaskManager

        path = tmp_path / "bad_tasks.json"
        path.write_text("not json{{{", encoding="utf-8")
        mgr = TaskManager(path=path)
        # Should not raise, starts empty
        assert mgr.list() == []

    def test_incrementing_ids(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        t1 = mgr.create("First")
        t2 = mgr.create("Second")
        t3 = mgr.create("Third")
        assert t1.id == "task-001"
        assert t2.id == "task-002"
        assert t3.id == "task-003"


class TestExecutorFunctions:
    def test_exec_task_create(self, tmp_path, monkeypatch):
        from core import task_manager as tm

        mgr = tm.TaskManager(path=tmp_path / "exec_tasks.json")
        monkeypatch.setattr(tm, "_manager", mgr)
        result = json.loads(tm._exec_task_create(subject="Test"))
        assert result["subject"] == "Test"
        assert result["status"] == "pending"

    def test_exec_task_update(self, tmp_path, monkeypatch):
        from core import task_manager as tm

        mgr = tm.TaskManager(path=tmp_path / "exec_tasks.json")
        monkeypatch.setattr(tm, "_manager", mgr)
        created = json.loads(tm._exec_task_create(subject="Test"))
        result = json.loads(tm._exec_task_update(task_id=created["id"], status="in_progress"))
        assert result["status"] == "in_progress"

    def test_exec_task_get_not_found(self, tmp_path, monkeypatch):
        from core import task_manager as tm

        mgr = tm.TaskManager(path=tmp_path / "exec_tasks.json")
        monkeypatch.setattr(tm, "_manager", mgr)
        result = json.loads(tm._exec_task_get(task_id="nope"))
        assert "error" in result

    def test_exec_task_list(self, tmp_path, monkeypatch):
        from core import task_manager as tm

        mgr = tm.TaskManager(path=tmp_path / "exec_tasks.json")
        monkeypatch.setattr(tm, "_manager", mgr)
        tm._exec_task_create(subject="A")
        tm._exec_task_create(subject="B")
        result = json.loads(tm._exec_task_list())
        assert len(result) == 2
