from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.job_groups import settle_job_group
from app.core.provider_limiter import ProviderSemaphore, RateLimitExceeded, _ACQUIRE, _RELEASE
from app.core.retries import retry_countdown
from app.core.state_machine import dispatch_job_group
from app.models.enums import JobStatus, ProjectStage, ProjectStatus
from tests.test_state_machine import FakeDB, _project


def test_retry_countdown_is_exponential():
    assert retry_countdown(0, base=2) == 2
    assert retry_countdown(1, base=2) == 4
    assert retry_countdown(2, base=2) == 8


class MemoryRedis:
    """Implementa o recorte das Lua scripts do semáforo (ZSET + TTL lógico)."""

    def __init__(self):
        self.zsets: dict[str, dict[str, float]] = {}

    def register_script(self, src: str):
        if "ZADD" in src:

            def acquire(*, keys, args):
                key, limit, token, now, ttl = keys[0], int(args[0]), args[1], float(args[2]), int(args[3])
                members = self.zsets.setdefault(key, {})
                cutoff = now - ttl
                self.zsets[key] = {member: score for member, score in members.items() if score > cutoff}
                if len(self.zsets[key]) < limit:
                    self.zsets[key][token] = now
                    return 1
                return 0

            return acquire

        def release(*, keys, args):
            return 1 if self.zsets.setdefault(keys[0], {}).pop(args[0], None) is not None else 0

        return release


def _semaphore(monkeypatch, limit: int = 1) -> ProviderSemaphore:
    fake = MemoryRedis()
    sem = ProviderSemaphore()
    sem._redis = fake
    sem._acquire = fake.register_script(_ACQUIRE)
    sem._release = fake.register_script(_RELEASE)
    monkeypatch.setattr(
        "app.core.provider_limiter.settings",
        SimpleNamespace(provider_concurrency_for=lambda _provider: limit),
    )
    return sem


def test_provider_semaphore_allows_up_to_limit(monkeypatch):
    sem = _semaphore(monkeypatch, limit=2)
    a = sem.acquire("higgsfield", timeout=0.2)
    b = sem.acquire("higgsfield", timeout=0.2)
    assert a and b and a != b
    sem.release("higgsfield", a)
    sem.release("higgsfield", b)


def test_provider_semaphore_times_out_when_full(monkeypatch):
    sem = _semaphore(monkeypatch, limit=1)
    token = sem.acquire("elevenlabs", timeout=0.2)
    with pytest.raises(RateLimitExceeded):
        sem.acquire("elevenlabs", timeout=0.15, poll_seconds=0.05)
    sem.release("elevenlabs", token)
    assert sem.acquire("elevenlabs", timeout=0.2)


def test_provider_hold_releases_on_error(monkeypatch):
    sem = _semaphore(monkeypatch, limit=1)
    with pytest.raises(RuntimeError):
        with sem.hold("anthropic", timeout=0.2):
            raise RuntimeError("provider down")
    assert sem.acquire("anthropic", timeout=0.2)


def test_provider_hold_skips_when_provider_is_none(monkeypatch):
    sem = _semaphore(monkeypatch, limit=1)
    with sem.hold(None):
        pass


def test_dispatch_job_group_shares_group_id(monkeypatch):
    monkeypatch.setattr("app.core.state_machine.enqueue_job", lambda *a, **k: None)
    project = _project(current_stage=ProjectStage.GENERATING_MEDIA, status=ProjectStatus.RUNNING)
    db = FakeDB(project)
    group_id, jobs = dispatch_job_group(
        db,
        project,
        ProjectStage.GENERATING_MEDIA,
        [{"scene": 1}, {"scene": 2}, {"scene": 3}],
    )
    assert len(jobs) == 3
    assert {job.job_group_id for job in jobs} == {group_id}
    assert all(job.status is JobStatus.QUEUED for job in jobs)
    assert all(job.payload["scene"] in (1, 2, 3) for job in jobs)


def test_settle_job_group_waits_then_advances(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        "app.core.job_groups.inspect_job_group",
        lambda *a, **k: SimpleNamespace(complete=False, all_succeeded=False),
    )
    monkeypatch.setattr("app.core.state_machine.advance_stage", lambda *a, **k: calls.append("advance"))
    monkeypatch.setattr("app.core.state_machine.fail_project", lambda *a, **k: calls.append("fail"))
    job = SimpleNamespace(id=uuid4(), job_group_id=uuid4(), stage=ProjectStage.TRANSCRIBING, error=None)
    settle_job_group(SimpleNamespace(), job, _project())
    assert calls == []

    monkeypatch.setattr(
        "app.core.job_groups.inspect_job_group",
        lambda *a, **k: SimpleNamespace(complete=True, all_succeeded=True),
    )
    settle_job_group(SimpleNamespace(), job, _project())
    assert calls == ["advance"]


def test_settle_job_group_fails_project_when_group_has_failures(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        "app.core.job_groups.inspect_job_group",
        lambda *a, **k: SimpleNamespace(complete=True, all_succeeded=False),
    )
    monkeypatch.setattr("app.core.state_machine.advance_stage", lambda *a, **k: calls.append("advance"))
    monkeypatch.setattr("app.core.state_machine.fail_project", lambda *a, **k: calls.append("fail"))
    job = SimpleNamespace(
        id=uuid4(),
        job_group_id=uuid4(),
        stage=ProjectStage.GENERATING_MEDIA,
        error="boom",
    )
    settle_job_group(SimpleNamespace(), job, _project())
    assert calls == ["fail"]
