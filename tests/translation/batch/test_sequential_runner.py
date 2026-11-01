from core.translation.batch.batch_item import BatchItem
from core.translation.batch.batch_job import BatchJob
from core.translation.batch.batch_state import BatchItemState, BatchJobState
from core.translation.services.batch_translation_service import BatchTranslationService


class ControlledTranslationPort:
    def __init__(self):
        self.calls = []
        self.current = None
        self.active_count = 0
        self.max_concurrent = 0

    def translate(self, target_index, on_success, on_error):
        if self.current is not None:
            raise AssertionError("Second inference dispatched before first completed")

        self.calls.append(target_index)
        self.current = (target_index, on_success, on_error)
        self.active_count += 1
        self.max_concurrent = max(self.max_concurrent, self.active_count)

    def complete_current(self):
        target_index, on_success, _ = self.current
        self.current = None
        self.active_count -= 1
        on_success(target_index)

    def fail_current(self, message):
        target_index, _, on_error = self.current
        self.current = None
        self.active_count -= 1
        on_error(target_index, message)


def test_tc_p3a2_03_executes_items_sequentially():
    port = ControlledTranslationPort()
    items = {
        2: BatchItem(target_index=2, source_hash="hash-2"),
        0: BatchItem(target_index=0, source_hash="hash-0"),
        1: BatchItem(target_index=1, source_hash="hash-1"),
    }
    job = BatchJob(job_id="job-1", project_id="project-1", items=items)
    service = BatchTranslationService(port)

    service.start(job)

    assert job.state is BatchJobState.RUNNING
    assert job.items[0].state is BatchItemState.RUNNING
    assert job.items[1].state is BatchItemState.PENDING
    assert job.items[2].state is BatchItemState.PENDING
    assert port.calls == [0]
    assert port.max_concurrent == 1

    port.complete_current()

    assert port.calls == [0, 1]
    assert job.items[0].state is BatchItemState.COMPLETED
    assert job.items[1].state is BatchItemState.RUNNING
    assert job.items[2].state is BatchItemState.PENDING
    assert port.max_concurrent == 1

    port.complete_current()

    assert port.calls == [0, 1, 2]
    assert job.items[1].state is BatchItemState.COMPLETED
    assert job.items[2].state is BatchItemState.RUNNING
    assert port.max_concurrent == 1

    port.complete_current()

    assert job.state is BatchJobState.COMPLETED
    assert all(item.state is BatchItemState.COMPLETED for item in job.items.values())
    assert port.calls == [0, 1, 2]
    assert port.max_concurrent == 1


def test_tc_p3a2_04_item_error_is_isolated_and_batch_continues():
    port = ControlledTranslationPort()
    items = {
        2: BatchItem(target_index=2, source_hash="hash-2"),
        0: BatchItem(target_index=0, source_hash="hash-0"),
        1: BatchItem(target_index=1, source_hash="hash-1"),
    }
    job = BatchJob(job_id="tc-p3a2-04", project_id="project-1", items=items)
    service = BatchTranslationService(port)

    service.start(job)
    assert port.calls == [0]
    assert job.items[0].state is BatchItemState.RUNNING

    port.complete_current()

    assert job.items[0].state is BatchItemState.COMPLETED
    assert job.items[1].state is BatchItemState.RUNNING
    assert job.state is BatchJobState.RUNNING
    assert port.calls == [0, 1]

    port.fail_current("deterministic translation failure")

    assert job.items[1].state is BatchItemState.FAILED
    assert job.items[1].error_msg == "deterministic translation failure"
    assert job.items[2].state is BatchItemState.RUNNING
    assert job.items[1].state is BatchItemState.FAILED
    assert job.state is BatchJobState.RUNNING
    assert port.calls == [0, 1, 2]
    assert port.max_concurrent == 1

    port.complete_current()

    assert job.items[0].state is BatchItemState.COMPLETED
    assert job.items[1].state is BatchItemState.FAILED
    assert job.items[2].state is BatchItemState.COMPLETED
    assert job.state is BatchJobState.COMPLETED
    assert port.calls == [0, 1, 2]
    assert port.max_concurrent == 1


def test_tc_p3a2_06_never_dispatches_second_inference_while_first_is_active():
    port = ControlledTranslationPort()
    items = {
        1: BatchItem(target_index=1, source_hash="hash-1"),
        0: BatchItem(target_index=0, source_hash="hash-0"),
    }
    job = BatchJob(job_id="tc-p3a2-06", project_id="project-1", items=items)
    service = BatchTranslationService(port)

    service.start(job)

    # The first request is deliberately held without a terminal callback.
    assert job.state is BatchJobState.RUNNING
    assert job.items[0].state is BatchItemState.RUNNING
    assert job.items[1].state is BatchItemState.PENDING
    assert port.calls == [0]
    assert port.active_count == 1
    assert port.max_concurrent == 1

    # A second dispatch would trip ControlledTranslationPort's concurrency guard.
    assert port.current[0] == 0
    assert port.calls == [0]

    port.complete_current()

    assert job.items[0].state is BatchItemState.COMPLETED
    assert job.items[1].state is BatchItemState.RUNNING
    assert port.calls == [0, 1]
    assert port.active_count == 1
    assert port.max_concurrent == 1

    port.complete_current()

    assert job.items[1].state is BatchItemState.COMPLETED
    assert job.state is BatchJobState.COMPLETED
    assert port.active_count == 0
    assert port.max_concurrent == 1

