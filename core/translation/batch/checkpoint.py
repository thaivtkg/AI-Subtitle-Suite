import json
import os
import tempfile
from pathlib import Path

from .batch_item import BatchItem
from .batch_job import BatchJob
from .batch_state import BatchItemState, BatchJobState
from .errors import CheckpointError, CheckpointFormatError, CheckpointIdentityError
from .fingerprint import compute_job_fingerprint


_SCHEMA_VERSION = 1


class CheckpointStore:
    @staticmethod
    def save(path, job: BatchJob) -> None:
        destination = Path(path)
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "fingerprint": compute_job_fingerprint(job),
            "job": {
                "job_id": job.job_id,
                "project_id": job.project_id,
                "state": job.state.name,
                "items": [
                    {
                        "target_index": target_index,
                        "source_hash": job.items[target_index].source_hash,
                        "state": job.items[target_index].state.name,
                        "error_msg": job.items[target_index].error_msg,
                    }
                    for target_index in sorted(job.items)
                ],
            },
        }

        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                json.dump(payload, temp_file, ensure_ascii=False, indent=2)
                temp_file.flush()
                os.fsync(temp_file.fileno())

            os.replace(temp_path, destination)
        except Exception as error:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise CheckpointError(f"Failed to save checkpoint: {error}") from error

    @staticmethod
    def load(
        path,
        expected_project_id: str | None = None,
        expected_fingerprint: str | None = None,
    ) -> BatchJob:
        checkpoint_path = Path(path)
        try:
            payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CheckpointFormatError(f"Invalid checkpoint file: {error}") from error

        job, stored_fingerprint = CheckpointStore._decode(payload)

        actual_fingerprint = compute_job_fingerprint(job)
        if stored_fingerprint != actual_fingerprint:
            raise CheckpointIdentityError(
                "Checkpoint fingerprint does not match its stored source identity"
            )

        if expected_project_id is not None and job.project_id != expected_project_id:
            raise CheckpointIdentityError(
                f"Checkpoint project mismatch: expected {expected_project_id}, "
                f"got {job.project_id}"
            )

        if (
            expected_fingerprint is not None
            and actual_fingerprint != expected_fingerprint
        ):
            raise CheckpointIdentityError("Checkpoint fingerprint mismatch")

        return job

    @staticmethod
    def _decode(payload) -> tuple[BatchJob, str]:
        if not isinstance(payload, dict):
            raise CheckpointFormatError("Checkpoint root must be an object")
        if payload.get("schema_version") != _SCHEMA_VERSION:
            raise CheckpointFormatError("Unsupported checkpoint schema version")

        fingerprint = payload.get("fingerprint")
        if not CheckpointStore._is_sha256(fingerprint):
            raise CheckpointFormatError("Invalid checkpoint fingerprint")

        job_data = payload.get("job")
        if not isinstance(job_data, dict):
            raise CheckpointFormatError("Missing checkpoint job")

        job_id = job_data.get("job_id")
        project_id = job_data.get("project_id")
        state_name = job_data.get("state")
        items_data = job_data.get("items")

        if not isinstance(job_id, str) or not job_id.strip():
            raise CheckpointFormatError("Invalid job_id")
        if not isinstance(project_id, str) or not project_id.strip():
            raise CheckpointFormatError("Invalid project_id")
        if not isinstance(state_name, str):
            raise CheckpointFormatError("Invalid job state")
        if not isinstance(items_data, list):
            raise CheckpointFormatError("Invalid job items")

        try:
            job_state = BatchJobState[state_name]
        except KeyError as error:
            raise CheckpointFormatError(f"Unknown job state: {state_name}") from error

        items = {}
        for item_data in items_data:
            if not isinstance(item_data, dict):
                raise CheckpointFormatError("Invalid checkpoint item")

            target_index = item_data.get("target_index")
            source_hash = item_data.get("source_hash")
            item_state_name = item_data.get("state")
            error_msg = item_data.get("error_msg")

            if not isinstance(target_index, int) or isinstance(target_index, bool):
                raise CheckpointFormatError("Invalid target_index")
            if target_index < 0:
                raise CheckpointFormatError("Invalid target_index")
            if target_index in items:
                raise CheckpointFormatError(
                    f"Duplicate target_index: {target_index}"
                )
            if not CheckpointStore._is_sha256(source_hash):
                raise CheckpointFormatError("Invalid source_hash")
            if not isinstance(item_state_name, str):
                raise CheckpointFormatError("Invalid item state")
            if error_msg is not None and not isinstance(error_msg, str):
                raise CheckpointFormatError("Invalid error_msg")

            try:
                item_state = BatchItemState[item_state_name]
            except KeyError as error:
                raise CheckpointFormatError(
                    f"Unknown item state: {item_state_name}"
                ) from error

            items[target_index] = BatchItem(
                target_index=target_index,
                source_hash=source_hash,
                state=item_state,
                error_msg=error_msg,
            )

        try:
            job = BatchJob(
                job_id=job_id,
                project_id=project_id,
                items=items,
                state=job_state,
            )
        except (TypeError, ValueError) as error:
            raise CheckpointFormatError(f"Invalid checkpoint job: {error}") from error

        return job, fingerprint

    @staticmethod
    def _is_sha256(value) -> bool:
        if not isinstance(value, str) or not value.startswith("sha256:"):
            return False
        digest = value[len("sha256:"):]
        return len(digest) == 64 and all(
            character in "0123456789abcdef"
            for character in digest
        )
