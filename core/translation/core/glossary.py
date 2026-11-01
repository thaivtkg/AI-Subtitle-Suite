from dataclasses import dataclass
import re


@dataclass(frozen=True)
class GlossaryEntry:
    source_term: str
    preferred_translation: str
    forbidden_alternatives: tuple[str, ...] = ()
    is_auto: bool = False

    def __post_init__(self):
        _validate_text(self.source_term, "source_term")
        _validate_text(self.preferred_translation, "preferred_translation")
        if not isinstance(self.forbidden_alternatives, (list, tuple)):
            raise ValueError("forbidden_alternatives must be a sequence")

        values = []
        for value in self.forbidden_alternatives:
            _validate_text(value, "forbidden_alternative")
            if value not in values:
                values.append(value)
        object.__setattr__(self, "forbidden_alternatives", tuple(values))
        object.__setattr__(self, "is_auto", bool(self.is_auto))


@dataclass(frozen=True)
class GlossaryHit:
    source_term: str
    preferred_translation: str
    start: int
    end: int


class Glossary:
    def __init__(self, entries=()):
        self._entries = {}
        self.add_entries(entries)

    @classmethod
    def from_entries(cls, entries):
        return cls(entries)

    @classmethod
    def from_payload(cls, payload):
        if not isinstance(payload, dict):
            raise ValueError("glossary must be an object")

        entries = []
        for source_term, value in payload.items():
            if not isinstance(value, dict):
                raise ValueError("glossary entry must be an object")
            if "preferred_translation" not in value:
                raise ValueError("missing preferred_translation")
            if "forbidden_alternatives" not in value:
                raise ValueError("missing forbidden_alternatives")
            is_auto = bool(value.get("is_auto", False))
            entries.append(
                GlossaryEntry(
                    source_term,
                    value["preferred_translation"],
                    value["forbidden_alternatives"],
                    is_auto=is_auto,
                )
            )
        return cls(entries)

    def add(self, source_term, preferred_translation, forbidden_alternatives=(), is_auto=False):
        self.add_entries(
            [(source_term, preferred_translation, forbidden_alternatives, is_auto)]
        )

    def add_entries(self, entries):
        candidate = dict(self._entries)
        for raw_entry in entries:
            entry = _coerce_entry(raw_entry)
            existing = candidate.get(entry.source_term)
            if existing is None:
                candidate[entry.source_term] = entry
                continue
            if (
                existing.preferred_translation != entry.preferred_translation
                or set(existing.forbidden_alternatives)
                != set(entry.forbidden_alternatives)
            ):
                raise ValueError(
                    f"Conflicting glossary entry: {entry.source_term!r}"
                )
        self._entries = candidate

    def update(self, source_term, preferred_translation, forbidden_alternatives=(), is_auto=False):
        if source_term not in self._entries:
            raise KeyError(source_term)
        entry = GlossaryEntry(
            source_term, preferred_translation, forbidden_alternatives, is_auto=is_auto
        )
        candidate = dict(self._entries)
        candidate[source_term] = entry
        self._entries = candidate

    def remove(self, source_term):
        candidate = dict(self._entries)
        del candidate[source_term]
        self._entries = candidate

    def replace_source_term(
        self, old_source_term, new_source_term, preferred_translation, forbidden_alternatives=(), is_auto=False
    ):
        if old_source_term not in self._entries:
            raise KeyError(old_source_term)
        replacement = GlossaryEntry(
            new_source_term, preferred_translation, forbidden_alternatives, is_auto=is_auto
        )
        candidate = dict(self._entries)
        del candidate[old_source_term]
        existing = candidate.get(new_source_term)
        if existing is not None and existing != replacement:
            raise ValueError(f"Conflicting glossary entry: {new_source_term!r}")
        candidate[new_source_term] = replacement
        self._entries = candidate

    def get(self, source_term, default=None):
        return self._entries.get(source_term, default)

    def to_payload(self):
        payload = {}
        for source_term, entry in self._entries.items():
            item = {
                "preferred_translation": entry.preferred_translation,
                "forbidden_alternatives": list(entry.forbidden_alternatives),
            }
            if getattr(entry, "is_auto", False):
                item["is_auto"] = True
            payload[source_term] = item
        return payload

    def match(self, source_text, word_boundary: bool = False):
        if not isinstance(source_text, str):
            raise ValueError("source_text must be a string")

        candidates = []
        for entry in self._entries.values():
            term = entry.source_term
            is_cjk = bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", term))
            if word_boundary and not is_cjk and re.match(r"^[\w\s-]+$", term):
                pattern = rf"\b{re.escape(term)}\b"
                for m in re.finditer(pattern, source_text, flags=re.IGNORECASE):
                    s, e = m.span()
                    candidates.append(
                        GlossaryHit(
                            term,
                            entry.preferred_translation,
                            s,
                            e,
                        )
                    )
            else:
                start = source_text.find(term)
                while start >= 0:
                    candidates.append(
                        GlossaryHit(
                            term,
                            entry.preferred_translation,
                            start,
                            start + len(term),
                        )
                    )
                    start = source_text.find(term, start + 1)

        candidates.sort(key=lambda hit: (-len(hit.source_term), hit.start))
        selected = []
        for candidate in candidates:
            if not any(_overlaps(candidate, hit) for hit in selected):
                selected.append(candidate)
        return tuple(sorted(selected, key=lambda hit: hit.start))

    def __len__(self):
        return len(self._entries)


def _coerce_entry(raw_entry):
    if isinstance(raw_entry, GlossaryEntry):
        return raw_entry
    if isinstance(raw_entry, (list, tuple)):
        if len(raw_entry) == 4:
            source_term, preferred_translation, forbidden_alternatives, is_auto = raw_entry
            return GlossaryEntry(
                source_term, preferred_translation, forbidden_alternatives, is_auto=bool(is_auto)
            )
        if len(raw_entry) == 3:
            source_term, preferred_translation, forbidden_alternatives = raw_entry
            return GlossaryEntry(
                source_term, preferred_translation, forbidden_alternatives
            )
    raise ValueError("glossary entry must have three or four values")


def _validate_text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _overlaps(left, right):
    return left.start < right.end and right.start < left.end
