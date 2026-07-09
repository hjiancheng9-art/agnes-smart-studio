"""Tests for core/task_manager.py — 持久化任务管理系统"""

import pytest

from core.task_manager import Task, TaskManager, TaskStatus


@pytest.fixture
def tm(tmp_path):
    return TaskManager(path=tmp_path / "tasks.db")


class TestTaskCRUD:
    """任务增删改查测试"""

    def test_create(self, tm):
        task = tm.create("修复登录bug", "用户无法登录时无错误提示")
        assert task.id is not None
        assert task.subject == "修复登录bug"
        assert task.description == "用户无法登录时无错误提示"

    def test_create_minimal(self, tm):
        task = tm.create("简单任务")
        assert task.subject == "简单任务"

    def test_create_unique_ids(self, tm):
        ids = [tm.create(f"任务{i}").id for i in range(10)]
        assert len(set(ids)) == 10

    def test_get_by_id(self, tm):
        created = tm.create("任务", "描述")
        fetched = tm.get(created.id)
        assert fetched.id == created.id

    def test_get_missing(self, tm):
        assert tm.get("no_such_id") is None

    def test_update_status(self, tm):
        task = tm.create("任务")
        tm.update(task.id, status="completed")
        updated = tm.get(task.id)
        assert updated.status == TaskStatus.COMPLETED

    def test_delete_soft(self, tm):
        task = tm.create("将被删除")
        tm.delete(task.id)
        deleted = tm.get(task.id)
        assert deleted.status == TaskStatus.DELETED  # 软删除

    def test_list(self, tm):
        tm.create("任务1")
        tm.create("任务2")
        assert len(tm.list()) >= 2


class TestTaskDependencies:
    """任务依赖测试"""

    def test_add_blocked_by(self, tm):
        t1 = tm.create("前置任务")
        t2 = tm.create("依赖任务")
        tm.add_blocked_by(t2.id, t1.id)
        blocked = tm.get_blocked_tasks()
        assert any(b.id == t2.id for b in blocked)

    def test_add_blocks(self, tm):
        t1 = tm.create("前置任务")
        t2 = tm.create("依赖任务")
        tm.add_blocks(t1.id, t2.id)
        blocked = tm.get_blocked_tasks()
        assert any(b.id == t2.id for b in blocked)


class TestTaskModel:
    """数据类测试"""

    def test_from_dict_required_only(self):
        d = {
            "id": "t-001",
            "subject": "测试",
            "description": "描述",
            "activeForm": "",
            "status": "pending",
            "owner": "",
            "blockedBy": [],
            "blocks": [],
            "metadata": {},
            "created_at": "",
            "updated_at": "",
        }
        task = Task.from_dict(d)
        assert task.id == "t-001"
        assert task.subject == "测试"

    def test_fields(self):
        task = Task(id="t-002", subject="测试", description="")
        assert task.id == "t-002"
        assert task.subject == "测试"
        assert task.status == TaskStatus.PENDING
