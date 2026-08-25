from types import SimpleNamespace
from uuid import uuid4

from app.core.job_groups import (
    check_job_group_complete,
    evaluate_job_group,
    inspect_job_group,
)
from app.models.enums import JobStatus


def _eval(*statuses: JobStatus):
    return evaluate_job_group(uuid4(), uuid4(), list(statuses))


def test_empty_group_is_not_complete():
    result = _eval()
    assert result.complete is False
    assert result.total == 0
    assert result.all_succeeded is False


def test_in_flight_jobs_block_completion():
    queued = _eval(JobStatus.SUCCEEDED, JobStatus.QUEUED)
    running = _eval(JobStatus.SUCCEEDED, JobStatus.RUNNING)
    retrying = _eval(JobStatus.SUCCEEDED, JobStatus.RETRYING)
    assert queued.complete is False
    assert running.complete is False
    assert retrying.complete is False
    assert retrying.in_flight == 1


def test_all_succeeded_is_complete():
    result = _eval(JobStatus.SUCCEEDED, JobStatus.SUCCEEDED, JobStatus.SUCCEEDED)
    assert result.complete is True
    assert result.all_succeeded is True
    assert result.succeeded == 3
    assert result.failed == 0
    assert result.retries_exhausted_failures is False


def test_mixed_terminal_is_complete_but_not_all_succeeded():
    result = _eval(JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.SUCCEEDED)
    assert result.complete is True
    assert result.all_succeeded is False
    assert result.failed == 1
    assert result.retries_exhausted_failures is True


def test_all_failed_after_retries_is_complete():
    result = _eval(JobStatus.FAILED, JobStatus.FAILED)
    assert result.complete is True
    assert result.all_succeeded is False
    assert result.retries_exhausted_failures is True


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, jobs):
        self.jobs = jobs

    def scalars(self, _stmt):
        return _ScalarResult(self.jobs)


def test_check_job_group_complete_reads_session():
    project_id = uuid4()
    group_id = uuid4()
    jobs = [
        SimpleNamespace(status=JobStatus.SUCCEEDED),
        SimpleNamespace(status=JobStatus.FAILED),
    ]
    db = _FakeSession(jobs)
    inspected = inspect_job_group(project_id, group_id, db=db)
    assert inspected.complete is True
    assert inspected.all_succeeded is False
    assert check_job_group_complete(project_id, group_id, db=db) is True


def test_check_job_group_complete_false_while_retrying():
    project_id = uuid4()
    group_id = uuid4()
    db = _FakeSession(
        [
            SimpleNamespace(status=JobStatus.SUCCEEDED),
            SimpleNamespace(status=JobStatus.RETRYING),
        ]
    )
    assert check_job_group_complete(project_id, group_id, db=db) is False
