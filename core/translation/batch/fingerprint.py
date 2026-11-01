import hashlib
import json

from .batch_job import BatchJob


def _sha256_text(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def compute_source_hash(source_text: str) -> str:
    if not isinstance(source_text, str):
        raise TypeError("source_text must be a string")
    return _sha256_text(source_text)


def compute_job_fingerprint(job: BatchJob) -> str:
    payload = {
        "project_id": job.project_id,
        "items": [
            {
                "target_index": target_index,
                "source_hash": job.items[target_index].source_hash,
            }
            for target_index in sorted(job.items)
        ],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_text(canonical)
