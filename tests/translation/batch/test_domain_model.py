import pytest

from core.translation.batch.batch_item import BatchItem
from core.translation.batch.batch_job import BatchJob
from core.translation.batch.batch_state import BatchItemState, BatchJobState


def test_tc_p3a1_01_item_default_pending():
    item = BatchItem(target_index=1, source_hash="hash")
    assert item.state == BatchItemState.PENDING


def test_tc_p3a1_02_reject_negative_index():
    with pytest.raises(ValueError, match="target_index must be >= 0"):
        BatchItem(target_index=-1, source_hash="hash")


def test_tc_p3a1_03_reject_empty_hash():
    with pytest.raises(ValueError, match="source_hash must not be empty"):
        BatchItem(target_index=1, source_hash="  ")


def test_tc_p3a1_04_job_default_idle():
    job = BatchJob(job_id="j1", project_id="p1")
    assert job.state == BatchJobState.IDLE


def test_tc_p3a1_05_reject_empty_job_id():
    with pytest.raises(ValueError, match="job_id must not be empty"):
        BatchJob(job_id="", project_id="p1")


def test_tc_p3a1_06_reject_empty_project_id():
    with pytest.raises(ValueError, match="project_id must not be empty"):
        BatchJob(job_id="j1", project_id="   ")


def test_tc_p3a1_07_reject_key_mismatch():
    item = BatchItem(target_index=2, source_hash="hash")
    with pytest.raises(ValueError, match="does not match target_index"):
        BatchJob(job_id="j1", project_id="p1", items={1: item})


def test_tc_p3a1_08_factory_generates_job_id():
    job = BatchJob.create(project_id="p1", items={})
    assert job.job_id
    assert job.project_id == "p1"
    assert job.state == BatchJobState.IDLE


def test_tc_p3a1_09_state_independent():
    assert len(BatchItemState) == 6
    assert not hasattr(BatchItemState, "EDITED")


def test_tc_p3a1_10_no_pyside6_qobject():
    import core.translation.batch.batch_item as bi
    import core.translation.batch.batch_job as bj
    import core.translation.batch.batch_state as bs

    for module in (bs, bi, bj):
        content = open(module.__file__, encoding="utf-8").read()
        assert "PySide6" not in content
        assert "QObject" not in content
        assert "Signal" not in content


