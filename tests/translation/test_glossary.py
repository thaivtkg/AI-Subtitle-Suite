from dataclasses import FrozenInstanceError

import pytest

from core.translation.core.glossary import Glossary, GlossaryEntry, GlossaryHit


def test_tc_p3b1_01_valid_entry_preserves_literal_values():
    entry = GlossaryEntry("  King  ", "  Vua  ", ("  Monarch  ",))

    glossary = Glossary.from_entries([entry])

    assert glossary.to_payload() == {
        "  King  ": {
            "preferred_translation": "  Vua  ",
            "forbidden_alternatives": ["  Monarch  "],
        }
    }


@pytest.mark.parametrize(
    "source_term,preferred_translation",
    [("", "Vua"), ("   ", "Vua"), ("King", ""), ("King", "   ")],
)
def test_tc_p3b1_02_rejects_empty_or_whitespace_entry_fields(
    source_term, preferred_translation
):
    with pytest.raises(ValueError):
        Glossary.from_entries([(source_term, preferred_translation, [])])


def test_tc_p3b1_03_rejects_invalid_forbidden_and_deduplicates_literals():
    with pytest.raises(ValueError):
        Glossary.from_entries([("King", "Vua", ["Valid", " "])])

    glossary = Glossary.from_entries(
        [("King", "Vua", ["A", "B", "A", "B"])]
    )

    assert glossary.to_payload()["King"]["forbidden_alternatives"] == ["A", "B"]


def test_tc_p3b1_04_deduplicates_identical_source_mappings():
    glossary = Glossary.from_entries(
        [
            ("King", "Vua", ["A", "B"]),
            ("King", "Vua", ["B", "A", "B"]),
        ]
    )

    assert glossary.to_payload() == {
        "King": {
            "preferred_translation": "Vua",
            "forbidden_alternatives": ["A", "B"],
        }
    }


@pytest.mark.parametrize(
    "entries",
    [
        [("King", "Vua", []), ("King", "The King", [])],
        [("King", "Vua", ["A"]), ("King", "Vua", ["B"])],
    ],
)
def test_tc_p3b1_05_rejects_duplicate_conflicts_without_partial_state(entries):
    glossary = Glossary.from_entries([("Queen", "Nữ hoàng", [])])

    with pytest.raises(ValueError):
        glossary.add_entries(entries)

    assert glossary.to_payload() == {
        "Queen": {
            "preferred_translation": "Nữ hoàng",
            "forbidden_alternatives": [],
        }
    }


def test_tc_p3b1_05_equivalent_forbidden_order_is_not_a_conflict():
    glossary = Glossary.from_entries([("King", "Vua", ["A", "B"])])

    glossary.add("King", "Vua", ["B", "A", "B"])

    assert glossary.to_payload()["King"]["forbidden_alternatives"] == ["A", "B"]


def test_glossary_identity_updates_translation_and_renames_by_remove_add():
    glossary = Glossary.from_entries([("King", "Vua", [])])

    glossary.update("King", "Đức vua", [])
    assert glossary.get("King").preferred_translation == "Đức vua"

    glossary.replace_source_term("King", "Monarch", "Quân vương", [])
    assert glossary.get("King") is None
    assert glossary.get("Monarch").preferred_translation == "Quân vương"

    glossary.remove("Monarch")
    assert len(glossary) == 0


def test_tc_p3b1_06_case_sensitive_matching():
    glossary = Glossary.from_entries([("King", "Vua", [])])

    assert glossary.match("king King KING") == (
        GlossaryHit("King", "Vua", 5, 9),
    )


def test_tc_p3b1_07_literal_substring_matching_inside_words():
    glossary = Glossary.from_entries([("art", "nghệ thuật", [])])

    assert glossary.match("cart.art") == (
        GlossaryHit("art", "nghệ thuật", 1, 4),
        GlossaryHit("art", "nghệ thuật", 5, 8),
    )


def test_tc_p3b1_08_multiple_occurrences_have_half_open_spans():
    glossary = Glossary.from_entries([("ha", "ha", [])])

    assert glossary.match("ha ha") == (
        GlossaryHit("ha", "ha", 0, 2),
        GlossaryHit("ha", "ha", 3, 5),
    )


def test_tc_p3b1_09_longest_overlapping_term_wins():
    glossary = Glossary.from_entries(
        [("New", "Mới", []), ("New York", "New York", []), ("York", "York", [])]
    )

    assert glossary.match("New York") == (
        GlossaryHit("New York", "New York", 0, 8),
    )


def test_tc_p3b1_10_equal_length_overlap_prefers_smaller_start():
    glossary = Glossary.from_entries(
        [("abc", "ABC", []), ("bca", "BCA", [])]
    )

    assert glossary.match("abca") == (
        GlossaryHit("abc", "ABC", 0, 3),
    )


def test_tc_p3b1_11_keeps_non_overlapping_candidates():
    glossary = Glossary.from_entries(
        [("cat", "mèo", []), ("dog", "chó", []), ("at", "tại", [])]
    )

    assert glossary.match("cat and dog") == (
        GlossaryHit("cat", "mèo", 0, 3),
        GlossaryHit("dog", "chó", 8, 11),
    )


def test_tc_p3b1_12_final_hits_are_sorted_by_start():
    glossary = Glossary.from_entries(
        [("dog", "chó", []), ("cat", "mèo", [])]
    )

    assert glossary.match("cat and dog") == (
        GlossaryHit("cat", "mèo", 0, 3),
        GlossaryHit("dog", "chó", 8, 11),
    )


def test_tc_p3b1_13_matching_is_immutable_and_ignores_forbidden_values():
    glossary = Glossary.from_entries([("King", "Vua", ["Monarch"])])
    before = glossary.to_payload()

    hits = glossary.match("King")

    assert glossary.to_payload() == before
    assert hits == (GlossaryHit("King", "Vua", 0, 4),)
    with pytest.raises(FrozenInstanceError):
        hits[0].start = 99


def test_tc_p3b1_09_to_12_matching_is_independent_of_insertion_order():
    first = Glossary.from_entries(
        [("York", "York", []), ("New", "Mới", []), ("New York", "New York", [])]
    )
    second = Glossary.from_entries(
        [("New York", "New York", []), ("New", "Mới", []), ("York", "York", [])]
    )

    assert first.match("New York") == second.match("New York")

