from core.project.source_fingerprint import SourceInfo
from core.recovery.recovery_models import (
    RecoveryManifest,
    RecoveryValidationResult,
    RecoveryWorkingState,
)


def _parse_segment_time(value) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return float(stripped)
        except ValueError:
            pass
        parts = stripped.replace(".", ",").split(":")
        if len(parts) == 3:
            sec_parts = parts[2].split(",")
            if len(sec_parts) == 2 and len(sec_parts[1]) == 3:
                hours, mins = int(parts[0]), int(parts[1])
                secs, ms = int(sec_parts[0]), int(sec_parts[1])
                if 0 <= mins < 60 and 0 <= secs < 60 and 0 <= ms < 1000 and hours >= 0:
                    return (hours * 3600 + mins * 60 + secs) * 1000 + ms
    raise ValueError(f"Invalid segment timestamp: {value!r}")


class RecoveryValidator:
    def validate_data(
        self,
        manifest: RecoveryManifest,
        snapshot: RecoveryWorkingState,
    ) -> RecoveryValidationResult:
        if manifest.schema_version != 1:
            return RecoveryValidationResult(False, "MANIFEST_SCHEMA_MISMATCH")
        if snapshot.schema_version < 2.0:
            return RecoveryValidationResult(False, "SNAPSHOT_SCHEMA_MISMATCH")
        if manifest.session_id != snapshot.session_id:
            return RecoveryValidationResult(False, "SESSION_ID_MISMATCH")
        if manifest.snapshot_revision != snapshot.edit_revision:
            return RecoveryValidationResult(False, "SNAPSHOT_REVISION_MISMATCH")
        revisions = (
            manifest.edit_revision,
            manifest.snapshot_revision,
            manifest.last_saved_revision,
            manifest.last_clean_revision,
            snapshot.edit_revision,
        )
        if any(not isinstance(value, int) or value < 0 for value in revisions):
            return RecoveryValidationResult(False, "INVALID_REVISION")
        if manifest.snapshot_revision > manifest.edit_revision:
            return RecoveryValidationResult(False, "INVALID_REVISION")
        if not isinstance(snapshot.workspace_state, dict):
            return RecoveryValidationResult(False, "INVALID_WORKSPACE_SCHEMA")

        context = getattr(snapshot, "transcription_context", None)
        if context is not None:
            if not isinstance(context, dict):
                return RecoveryValidationResult(
                    False, "INVALID_TRANSCRIPTION_CONTEXT_TYPE"
                )
            if "context" in context and not isinstance(context["context"], str):
                return RecoveryValidationResult(
                    False, "INVALID_TRANSCRIPTION_CONTEXT_STRING"
                )
            glossary = context.get("glossary")
            if "glossary" in context and (
                not isinstance(glossary, list)
                or not all(isinstance(item, str) for item in glossary)
            ):
                return RecoveryValidationResult(
                    False, "INVALID_TRANSCRIPTION_GLOSSARY_LIST"
                )

        for segment in snapshot.segments:
            if not isinstance(segment, dict):
                return RecoveryValidationResult(False, "INVALID_SEGMENT_SCHEMA")
            if not segment.get("id") or not segment.get("stt"):
                return RecoveryValidationResult(False, "INVALID_SEGMENT_SCHEMA")
            if "start" in segment and "end" in segment:
                try:
                    start = _parse_segment_time(segment["start"])
                    end = _parse_segment_time(segment["end"])
                except (TypeError, ValueError):
                    return RecoveryValidationResult(False, "INVALID_SEGMENT_SCHEMA")
                if start < 0 or end < start:
                    return RecoveryValidationResult(False, "INVALID_SEGMENT_SCHEMA")

        return RecoveryValidationResult(True)

    def validate_source(
        self,
        manifest: RecoveryManifest,
        actual_source_info: SourceInfo | None,
    ) -> RecoveryValidationResult:
        if actual_source_info is None:
            return RecoveryValidationResult(
                True,
                source_matches=False,
                source_reason="SOURCE_MISSING",
            )
        if actual_source_info.fingerprint != manifest.source_fingerprint:
            return RecoveryValidationResult(
                True,
                source_matches=False,
                source_reason="SOURCE_MISMATCH",
            )
        return RecoveryValidationResult(True)
