from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TMEntry:
    source_text: str
    target_text: str

    def __post_init__(self):
        _validate_text(self.source_text, "source_text")
        _validate_text(self.target_text, "target_text")


class TranslationMemory:
    def __init__(self, entries=()):
        self._entries = {}
        self.add_entries(entries)

    @classmethod
    def from_entries(cls, entries):
        return cls(entries)

    @classmethod
    def from_payload(cls, payload):
        if not isinstance(payload, dict):
            raise ValueError("translation_memory must be an object")

        entries = []
        for source_text, value in payload.items():
            if not isinstance(value, dict):
                raise ValueError("tm entry must be an object")
            if "target_text" not in value:
                raise ValueError("missing target_text")
            entries.append(
                TMEntry(
                    source_text=source_text,
                    target_text=value["target_text"],
                )
            )
        return cls(entries)

    def add(self, source_text, target_text):
        self.add_entries([(source_text, target_text)])

    def add_entries(self, entries):
        candidate = dict(self._entries)
        for raw_entry in entries:
            entry = _coerce_entry(raw_entry)
            candidate[entry.source_text] = entry  # Last-Write-Wins overwrite
        self._entries = candidate

    def update(self, source_text, target_text):
        if source_text not in self._entries:
            raise KeyError(source_text)
        entry = TMEntry(source_text, target_text)
        candidate = dict(self._entries)
        candidate[source_text] = entry
        self._entries = candidate

    def remove(self, source_text):
        if source_text not in self._entries:
            raise KeyError(source_text)
        candidate = dict(self._entries)
        del candidate[source_text]
        self._entries = candidate

    def get(self, source_text, default=None):
        return self._entries.get(source_text, default)

    def lookup(self, source_text: str) -> Optional[TMEntry]:
        if not isinstance(source_text, str):
            raise ValueError("source_text must be a string")
        return self._entries.get(source_text, None)

    def to_payload(self):
        return {
            source_text: {
                "target_text": entry.target_text,
            }
            for source_text, entry in self._entries.items()
        }

    def __len__(self):
        return len(self._entries)


def _coerce_entry(raw_entry):
    if isinstance(raw_entry, TMEntry):
        return raw_entry
    try:
        source_text, target_text = raw_entry
    except (TypeError, ValueError) as error:
        raise ValueError("tm entry must have two values") from error
    return TMEntry(source_text, target_text)


def _validate_text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
