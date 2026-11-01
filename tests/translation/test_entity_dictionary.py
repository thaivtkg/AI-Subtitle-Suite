from dataclasses import FrozenInstanceError

import pytest

from core.translation.core.entity_dictionary import (
    EntityDictionary,
    EntityEntry,
    EntityHit,
    VALID_ENTITY_TYPES,
)


# ---------------------------------------------------------------------------
# TC-P3B2-01  Valid entry
# ---------------------------------------------------------------------------
def test_tc_p3b2_01_valid_entry_preserves_literal_values():
    entry = EntityEntry(
        "  Tony Stark  ", "CHARACTER", "  Tony Stark  ", ("  Iron Man  ",)
    )
    dictionary = EntityDictionary.from_entries([entry])
    assert dictionary.to_payload() == {
        "  Tony Stark  ": {
            "entity_type": "CHARACTER",
            "canonical_translation": "  Tony Stark  ",
            "aliases": ["  Iron Man  "],
        }
    }


def test_tc_p3b2_01_all_valid_entity_types_accepted():
    for entity_type in sorted(VALID_ENTITY_TYPES):
        entry = EntityEntry(f"E_{entity_type}", entity_type, "trans", ())
        assert entry.entity_type == entity_type


# ---------------------------------------------------------------------------
# TC-P3B2-02  Entry validity
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name,canonical_translation",
    [("", "Trans"), ("   ", "Trans"), ("Name", ""), ("Name", "   ")],
)
def test_tc_p3b2_02_rejects_empty_or_whitespace_entry_fields(
    name, canonical_translation
):
    with pytest.raises(ValueError):
        EntityDictionary.from_entries(
            [(name, "CHARACTER", canonical_translation, [])]
        )


# ---------------------------------------------------------------------------
# TC-P3B2-03  Entity type validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_type", ["character", "Person", "ANIMAL", "", " "])
def test_tc_p3b2_03_rejects_invalid_entity_type(bad_type):
    with pytest.raises(ValueError):
        EntityDictionary.from_entries([("Name", bad_type, "Trans", [])])


# ---------------------------------------------------------------------------
# TC-P3B2-04  Alias validity
# ---------------------------------------------------------------------------
def test_tc_p3b2_04_rejects_invalid_alias_and_deduplicates_literals():
    with pytest.raises(ValueError):
        EntityDictionary.from_entries(
            [("Name", "CHARACTER", "Trans", ["Valid", " "])]
        )
    dictionary = EntityDictionary.from_entries(
        [("Name", "CHARACTER", "Trans", ["A", "B", "A", "B"])]
    )
    assert dictionary.to_payload()["Name"]["aliases"] == ["A", "B"]


def test_tc_p3b2_04_first_occurrence_order_preserved():
    dictionary = EntityDictionary.from_entries(
        [("Name", "CHARACTER", "Trans", ["B", "A", "B"])]
    )
    assert dictionary.to_payload()["Name"]["aliases"] == ["B", "A"]


# ---------------------------------------------------------------------------
# TC-P3B2-05  Alias self-reference
# ---------------------------------------------------------------------------
def test_tc_p3b2_05_rejects_alias_equals_own_name():
    with pytest.raises(ValueError):
        EntityDictionary.from_entries(
            [("Tony", "CHARACTER", "Trans", ["Tony"])]
        )


# ---------------------------------------------------------------------------
# TC-P3B2-06  Matchable-form cross-entity uniqueness
# ---------------------------------------------------------------------------
def test_tc_p3b2_06_alias_collides_with_other_entity_name():
    """A.alias == B.name → rejected."""
    with pytest.raises(ValueError):
        EntityDictionary.from_entries([
            ("Iron Man", "CHARACTER", "Iron Man", ["Tony"]),
            ("Tony", "CHARACTER", "Tony", []),
        ])


def test_tc_p3b2_06_alias_collides_with_other_entity_alias():
    """A.alias == B.alias → rejected."""
    with pytest.raises(ValueError):
        EntityDictionary.from_entries([
            ("Iron Man", "CHARACTER", "Iron Man", ["Stark"]),
            ("Captain", "CHARACTER", "Đại úy", ["Stark"]),
        ])


def test_tc_p3b2_06_name_collides_with_existing_alias():
    """B.name == A.alias (symmetric direction) → rejected."""
    dictionary = EntityDictionary.from_entries(
        [("Iron Man", "CHARACTER", "Iron Man", ["Tony"])]
    )
    with pytest.raises(ValueError):
        dictionary.add("Tony", "CHARACTER", "Tony", [])
    # Prior state unchanged
    assert len(dictionary) == 1
    assert dictionary.get("Iron Man") is not None


def test_tc_p3b2_06_no_collision_when_independent():
    """Non-overlapping forms → accepted."""
    dictionary = EntityDictionary.from_entries([
        ("Iron Man", "CHARACTER", "Iron Man", ["Stark"]),
        ("Captain", "CHARACTER", "Đại úy", ["Steve"]),
    ])
    assert len(dictionary) == 2


# ---------------------------------------------------------------------------
# TC-P3B2-07  Duplicate deduplication
# ---------------------------------------------------------------------------
def test_tc_p3b2_07_deduplicates_identical_definitions():
    dictionary = EntityDictionary.from_entries([
        ("Tony", "CHARACTER", "Tony", ["A", "B"]),
        ("Tony", "CHARACTER", "Tony", ["B", "A", "B"]),
    ])
    payload = dictionary.to_payload()
    assert payload == {
        "Tony": {
            "entity_type": "CHARACTER",
            "canonical_translation": "Tony",
            "aliases": ["A", "B"],
        }
    }


# ---------------------------------------------------------------------------
# TC-P3B2-08  Duplicate conflict
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "entries",
    [
        # Different canonical_translation
        [("Tony", "CHARACTER", "Tony", []), ("Tony", "CHARACTER", "Toni", [])],
        # Different entity_type
        [("Tony", "CHARACTER", "Tony", []), ("Tony", "LOCATION", "Tony", [])],
        # Different effective aliases
        [
            ("Tony", "CHARACTER", "Tony", ["A"]),
            ("Tony", "CHARACTER", "Tony", ["B"]),
        ],
    ],
)
def test_tc_p3b2_08_rejects_duplicate_conflicts_without_partial_state(entries):
    dictionary = EntityDictionary.from_entries(
        [("Existing", "LOCATION", "Có sẵn", [])]
    )
    with pytest.raises(ValueError):
        dictionary.add_entries(entries)
    assert dictionary.to_payload() == {
        "Existing": {
            "entity_type": "LOCATION",
            "canonical_translation": "Có sẵn",
            "aliases": [],
        }
    }


# ---------------------------------------------------------------------------
# TC-P3B2-09  Case-sensitive matching
# ---------------------------------------------------------------------------
def test_tc_p3b2_09_case_sensitive_matching():
    dictionary = EntityDictionary.from_entries(
        [("Tony", "CHARACTER", "Tony", [])]
    )
    hits = dictionary.match("tony Tony TONY")
    assert hits == (
        EntityHit("Tony", "Tony", "Tony", "CHARACTER", 5, 9),
    )


# ---------------------------------------------------------------------------
# TC-P3B2-10  Literal substring matching
# ---------------------------------------------------------------------------
def test_tc_p3b2_10_literal_substring_matching_inside_words():
    dictionary = EntityDictionary.from_entries(
        [("art", "OTHER", "nghệ thuật", [])]
    )
    hits = dictionary.match("cart.art")
    assert hits == (
        EntityHit("art", "art", "nghệ thuật", "OTHER", 1, 4),
        EntityHit("art", "art", "nghệ thuật", "OTHER", 5, 8),
    )


# ---------------------------------------------------------------------------
# TC-P3B2-11  Alias resolution
# ---------------------------------------------------------------------------
def test_tc_p3b2_11_alias_resolves_to_canonical_entity():
    dictionary = EntityDictionary.from_entries(
        [("Tony Stark", "CHARACTER", "Tony Stark", ["Iron Man"])]
    )
    hits = dictionary.match("Iron Man flies")
    assert len(hits) == 1
    assert hits[0].entity_name == "Tony Stark"
    assert hits[0].matched_form == "Iron Man"
    assert hits[0].canonical_translation == "Tony Stark"
    assert hits[0].entity_type == "CHARACTER"
    assert hits[0].start == 0
    assert hits[0].end == 8


# ---------------------------------------------------------------------------
# TC-P3B2-12  Multiple occurrences
# ---------------------------------------------------------------------------
def test_tc_p3b2_12_multiple_occurrences_have_half_open_spans():
    dictionary = EntityDictionary.from_entries(
        [("ha", "OTHER", "ha", [])]
    )
    hits = dictionary.match("ha ha")
    assert hits == (
        EntityHit("ha", "ha", "ha", "OTHER", 0, 2),
        EntityHit("ha", "ha", "ha", "OTHER", 3, 5),
    )


# ---------------------------------------------------------------------------
# TC-P3B2-13  Longest overlap
# ---------------------------------------------------------------------------
def test_tc_p3b2_13_longest_overlap_wins():
    dictionary = EntityDictionary.from_entries([
        ("New", "LOCATION", "Mới", []),
        ("New York", "LOCATION", "New York", []),
        ("York", "LOCATION", "York", []),
    ])
    hits = dictionary.match("New York")
    assert hits == (
        EntityHit("New York", "New York", "New York", "LOCATION", 0, 8),
    )


def test_tc_p3b2_13_longest_alias_wins_over_shorter_name():
    dictionary = EntityDictionary.from_entries([
        ("Tony Stark", "CHARACTER", "Tony Stark", ["Iron Man"]),
        ("Iron", "OTHER", "Sắt", []),
    ])
    hits = dictionary.match("Iron Man saves the day")
    assert hits == (
        EntityHit("Tony Stark", "Iron Man", "Tony Stark", "CHARACTER", 0, 8),
    )


# ---------------------------------------------------------------------------
# TC-P3B2-14  Equal-length tie
# ---------------------------------------------------------------------------
def test_tc_p3b2_14_equal_length_overlap_prefers_smaller_start():
    dictionary = EntityDictionary.from_entries([
        ("abc", "OTHER", "ABC", []),
        ("bca", "OTHER", "BCA", []),
    ])
    hits = dictionary.match("abca")
    assert hits == (EntityHit("abc", "abc", "ABC", "OTHER", 0, 3),)


# ---------------------------------------------------------------------------
# TC-P3B2-15  Non-overlap retention
# ---------------------------------------------------------------------------
def test_tc_p3b2_15_keeps_non_overlapping_candidates():
    dictionary = EntityDictionary.from_entries([
        ("cat", "OTHER", "mèo", []),
        ("dog", "OTHER", "chó", []),
        ("at", "OTHER", "tại", []),
    ])
    hits = dictionary.match("cat and dog")
    assert hits == (
        EntityHit("cat", "cat", "mèo", "OTHER", 0, 3),
        EntityHit("dog", "dog", "chó", "OTHER", 8, 11),
    )


# ---------------------------------------------------------------------------
# TC-P3B2-16  Result order
# ---------------------------------------------------------------------------
def test_tc_p3b2_16_final_hits_are_sorted_by_start():
    dictionary = EntityDictionary.from_entries([
        ("dog", "OTHER", "chó", []),
        ("cat", "OTHER", "mèo", []),
    ])
    hits = dictionary.match("cat and dog")
    assert hits == (
        EntityHit("cat", "cat", "mèo", "OTHER", 0, 3),
        EntityHit("dog", "dog", "chó", "OTHER", 8, 11),
    )


# ---------------------------------------------------------------------------
# TC-P3B2-17  Matcher immutability
# ---------------------------------------------------------------------------
def test_tc_p3b2_17_matching_is_immutable():
    dictionary = EntityDictionary.from_entries(
        [("Tony", "CHARACTER", "Tony", ["Stark"])]
    )
    before = dictionary.to_payload()
    hits = dictionary.match("Tony meets Stark")
    assert dictionary.to_payload() == before
    assert len(hits) == 2
    with pytest.raises(FrozenInstanceError):
        hits[0].start = 99


# ---------------------------------------------------------------------------
# Supplementary: update, remove, replace_name
# ---------------------------------------------------------------------------
def test_entity_identity_updates_and_renames():
    dictionary = EntityDictionary.from_entries(
        [("Tony", "CHARACTER", "Tony", [])]
    )
    dictionary.update("Tony", "CHARACTER", "Toni", [])
    assert dictionary.get("Tony").canonical_translation == "Toni"

    dictionary.replace_name("Tony", "Stark", "CHARACTER", "Stark", [])
    assert dictionary.get("Tony") is None
    assert dictionary.get("Stark").canonical_translation == "Stark"

    dictionary.remove("Stark")
    assert len(dictionary) == 0


def test_matching_is_independent_of_insertion_order():
    first = EntityDictionary.from_entries([
        ("York", "LOCATION", "York", []),
        ("New", "LOCATION", "Mới", []),
        ("New York", "LOCATION", "New York", []),
    ])
    second = EntityDictionary.from_entries([
        ("New York", "LOCATION", "New York", []),
        ("New", "LOCATION", "Mới", []),
        ("York", "LOCATION", "York", []),
    ])
    assert first.match("New York") == second.match("New York")

