from dataclasses import dataclass
import re


VALID_ENTITY_TYPES = {"CHARACTER", "LOCATION", "ORGANIZATION", "OTHER"}


@dataclass(frozen=True)
class EntityEntry:
    name: str
    entity_type: str
    canonical_translation: str
    aliases: tuple[str, ...] = ()

    def __post_init__(self):
        _validate_text(self.name, "name")
        if self.entity_type not in VALID_ENTITY_TYPES:
            raise ValueError(
                f"entity_type must be one of {sorted(VALID_ENTITY_TYPES)}, "
                f"got {self.entity_type!r}"
            )
        _validate_text(self.canonical_translation, "canonical_translation")
        if not isinstance(self.aliases, (list, tuple)):
            raise ValueError("aliases must be a sequence")

        values = []
        for value in self.aliases:
            _validate_text(value, "alias")
            if value == self.name:
                raise ValueError(
                    f"alias {value!r} must not equal the entry's own name"
                )
            if value not in values:
                values.append(value)
        object.__setattr__(self, "aliases", tuple(values))


@dataclass(frozen=True)
class EntityHit:
    entity_name: str
    matched_form: str
    canonical_translation: str
    entity_type: str
    start: int
    end: int


class EntityDictionary:
    def __init__(self, entries=()):
        self._entries = {}
        self.add_entries(entries)

    @classmethod
    def from_entries(cls, entries):
        return cls(entries)

    @classmethod
    def from_payload(cls, payload):
        if not isinstance(payload, dict):
            raise ValueError("entities must be an object")

        entries = []
        for name, value in payload.items():
            if not isinstance(value, dict):
                raise ValueError("entity entry must be an object")
            if "entity_type" not in value:
                raise ValueError("missing entity_type")
            if "canonical_translation" not in value:
                raise ValueError("missing canonical_translation")
            if "aliases" not in value:
                raise ValueError("missing aliases")
            entries.append(
                EntityEntry(
                    name,
                    value["entity_type"],
                    value["canonical_translation"],
                    value["aliases"],
                )
            )
        return cls(entries)

    def add(self, name, entity_type, canonical_translation, aliases=()):
        self.add_entries(
            [(name, entity_type, canonical_translation, aliases)]
        )

    def add_entries(self, entries):
        candidate = dict(self._entries)
        for raw_entry in entries:
            entry = _coerce_entry(raw_entry)
            existing = candidate.get(entry.name)
            if existing is None:
                candidate[entry.name] = entry
                continue
            if (
                existing.canonical_translation != entry.canonical_translation
                or existing.entity_type != entry.entity_type
                or set(existing.aliases) != set(entry.aliases)
            ):
                raise ValueError(
                    f"Conflicting entity entry: {entry.name!r}"
                )
        _check_uniqueness(candidate)
        self._entries = candidate

    def update(self, name, entity_type, canonical_translation, aliases=()):
        if name not in self._entries:
            raise KeyError(name)
        entry = EntityEntry(name, entity_type, canonical_translation, aliases)
        candidate = dict(self._entries)
        candidate[name] = entry
        _check_uniqueness(candidate)
        self._entries = candidate

    def remove(self, name):
        candidate = dict(self._entries)
        del candidate[name]
        self._entries = candidate

    def replace_name(
        self, old_name, new_name, entity_type, canonical_translation, aliases=()
    ):
        if old_name not in self._entries:
            raise KeyError(old_name)
        replacement = EntityEntry(
            new_name, entity_type, canonical_translation, aliases
        )
        candidate = dict(self._entries)
        del candidate[old_name]
        existing = candidate.get(new_name)
        if existing is not None and (
            existing.canonical_translation != replacement.canonical_translation
            or existing.entity_type != replacement.entity_type
            or set(existing.aliases) != set(replacement.aliases)
        ):
            raise ValueError(f"Conflicting entity entry: {new_name!r}")
        candidate[new_name] = replacement
        _check_uniqueness(candidate)
        self._entries = candidate

    def get(self, name, default=None):
        return self._entries.get(name, default)

    def to_payload(self):
        return {
            name: {
                "entity_type": entry.entity_type,
                "canonical_translation": entry.canonical_translation,
                "aliases": list(entry.aliases),
            }
            for name, entry in self._entries.items()
        }

    def match(self, source_text, word_boundary: bool = False):
        if not isinstance(source_text, str):
            raise ValueError("source_text must be a string")

        candidates = []
        for entry in self._entries.values():
            matchable_forms = [entry.name] + list(entry.aliases)
            for form in matchable_forms:
                is_cjk = bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", form))
                if word_boundary and not is_cjk and re.match(r"^[\w\s-]+$", form):
                    pattern = rf"\b{re.escape(form)}\b"
                    for m in re.finditer(pattern, source_text, flags=re.IGNORECASE):
                        s, e = m.span()
                        candidates.append(
                            EntityHit(
                                entity_name=entry.name,
                                matched_form=m.group(0),
                                canonical_translation=entry.canonical_translation,
                                entity_type=entry.entity_type,
                                start=s,
                                end=e,
                            )
                        )
                else:
                    start = source_text.find(form)
                    while start >= 0:
                        candidates.append(
                            EntityHit(
                                entity_name=entry.name,
                                matched_form=form,
                                canonical_translation=entry.canonical_translation,
                                entity_type=entry.entity_type,
                                start=start,
                                end=start + len(form),
                            )
                        )
                        start = source_text.find(form, start + 1)

        candidates.sort(key=lambda hit: (-len(hit.matched_form), hit.start))
        selected = []
        for candidate in candidates:
            if not any(_overlaps(candidate, hit) for hit in selected):
                selected.append(candidate)
        return tuple(sorted(selected, key=lambda hit: hit.start))

    def __len__(self):
        return len(self._entries)


def _check_uniqueness(entries_dict):
    """Check that all matchable forms are globally unique across the dictionary."""
    forms = {}
    for entry in entries_dict.values():
        if entry.name in forms:
            owner = forms[entry.name]
            if owner != entry.name:
                raise ValueError(
                    f"Matchable form {entry.name!r} conflicts: "
                    f"name of {entry.name!r} collides with form owned by {owner!r}"
                )
        else:
            forms[entry.name] = entry.name

        for alias in entry.aliases:
            if alias in forms:
                owner = forms[alias]
                if owner != entry.name:
                    raise ValueError(
                        f"Matchable form {alias!r} conflicts: "
                        f"alias of {entry.name!r} collides with form owned by {owner!r}"
                    )
            else:
                forms[alias] = entry.name


def _coerce_entry(raw_entry):
    if isinstance(raw_entry, EntityEntry):
        return raw_entry
    try:
        name, entity_type, canonical_translation, aliases = raw_entry
    except (TypeError, ValueError) as error:
        raise ValueError("entity entry must have four values") from error
    return EntityEntry(name, entity_type, canonical_translation, aliases)


def _validate_text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _overlaps(left, right):
    return left.start < right.end and right.start < left.end
