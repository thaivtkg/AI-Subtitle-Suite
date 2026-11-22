import importlib
import unittest


def segment(start, end, text="speech", **metadata):
    return {
        "start_ms": start,
        "end_ms": end,
        "text": text,
        "words": [{"word": text, "start_ms": start, "end_ms": end}],
        **metadata,
    }


class TestGenerationTimingReconciler(unittest.TestCase):
    def _api(self):
        return importlib.import_module(
            "core.subtitle_generation.generation_timing_reconciler"
        )

    def test_exact_and_inside_batches_preserve_timing_and_content(self):
        api = self._api()
        for rows in (
            [segment(1000, 2000), segment(2500, 3500)],
            [segment(1200, 2200), segment(2700, 3700)],
        ):
            result = api.reconcile_generated_timing(
                api.GenerationRange(1000, 5000), rows, 6000
            )
            self.assertEqual(result.status, api.ReconciliationStatus.SUCCESS)
            self.assertEqual(list(result.segments), rows)
            self.assertEqual(result.global_shift_ms, 0)
            self.assertEqual(result.overlap_repairs, 0)
            self.assertEqual(result.changed_segment_count, 0)

    def test_left_overflow_uses_one_global_shift_and_preserves_gap(self):
        api = self._api()
        raw = [segment(900, 1900), segment(2000, 3000)]
        result = api.reconcile_generated_timing(api.GenerationRange(1000, 5000), raw, 6000)
        self.assertEqual(result.status, api.ReconciliationStatus.SUCCESS)
        self.assertEqual(
            [(row["start_ms"], row["end_ms"]) for row in result.segments],
            [(1000, 2000), (2100, 3100)],
        )
        self.assertEqual(result.global_shift_ms, 100)
        self.assertEqual(result.changed_segment_count, 2)
        self.assertEqual(result.segments[0]["words"][0]["start_ms"], 1000)
        self.assertEqual(result.segments[0]["words"][0]["end_ms"], 2000)
        self.assertEqual(result.segments[0]["words"][0]["word"], "speech")
        self.assertEqual((raw[0]["start_ms"], raw[0]["end_ms"]), (900, 1900))

    def test_right_overflow_uses_one_global_shift_and_preserves_gap(self):
        api = self._api()
        result = api.reconcile_generated_timing(
            api.GenerationRange(1000, 5000),
            [segment(2000, 4000), segment(4500, 5100)],
            6000,
        )
        self.assertEqual(
            [(row["start_ms"], row["end_ms"]) for row in result.segments],
            [(1900, 3900), (4400, 5000)],
        )
        self.assertEqual(result.global_shift_ms, -100)
        self.assertEqual(result.segments[1]["start_ms"] - result.segments[0]["end_ms"], 500)

    def test_global_shift_preserves_durations_and_all_internal_gaps(self):
        api = self._api()
        raw = [segment(900, 1400), segment(1600, 2200), segment(2400, 3000)]
        result = api.reconcile_generated_timing(api.GenerationRange(1000, 4000), raw, 5000)
        self.assertEqual(result.global_shift_ms, 100)
        self.assertEqual(
            [(row["start_ms"], row["end_ms"]) for row in result.segments],
            [(1000, 1500), (1700, 2300), (2500, 3100)],
        )
        self.assertEqual(
            [row["end_ms"] - row["start_ms"] for row in result.segments],
            [500, 600, 600],
        )

    def test_crossing_outer_boundaries_is_clamped_when_global_shift_cannot_fit(self):
        api = self._api()
        raw = [segment(9800, 10800), segment(14200, 15300)]
        result = api.reconcile_generated_timing(api.GenerationRange(10000, 15000), raw, 20000)
        self.assertEqual(result.status, api.ReconciliationStatus.SUCCESS)
        self.assertEqual(
            [(row["start_ms"], row["end_ms"]) for row in result.segments],
            [(10000, 10800), (14200, 15000)],
        )
        self.assertEqual(result.global_shift_ms, 0)
        self.assertEqual(result.boundary_clamps, 2)
        self.assertEqual(result.changed_segment_count, 2)

    def test_boundary_clamp_preserves_generated_gap(self):
        api = self._api()
        result = api.reconcile_generated_timing(
            api.GenerationRange(10000, 15000),
            [segment(9800, 10800), segment(12000, 13000), segment(14200, 15300)],
            20000,
        )
        self.assertEqual(
            [(row["start_ms"], row["end_ms"]) for row in result.segments],
            [(10000, 10800), (12000, 13000), (14200, 15000)],
        )
        self.assertEqual(result.segments[1]["start_ms"] - result.segments[0]["end_ms"], 1200)
        self.assertEqual(result.segments[2]["start_ms"] - result.segments[1]["end_ms"], 1200)

    def test_wholly_outside_segment_is_not_pulled_into_range_when_clamping(self):
        api = self._api()
        for rows in (
            [segment(9000, 11000), segment(16000, 17000)],
            [segment(9000, 10000), segment(14000, 16000)],
        ):
            result = api.reconcile_generated_timing(api.GenerationRange(10000, 15000), rows, 20000)
            self.assertEqual(result.status, api.ReconciliationStatus.CONFLICT)
            self.assertEqual(rows[0]["start_ms"], 9000)

    def test_clamp_that_breaks_minimum_duration_is_rejected(self):
        api = self._api()
        result = api.reconcile_generated_timing(
            api.GenerationRange(1000, 1500),
            [segment(900, 1050), segment(1400, 1550)],
            3000,
        )
        self.assertEqual(result.status, api.ReconciliationStatus.CONFLICT)
        self.assertIn("minimum", result.reason.casefold())

    def test_one_internal_overlap_is_split_at_midpoint(self):
        api = self._api()
        raw = [segment(1000, 3500), segment(3000, 5000)]
        result = api.reconcile_generated_timing(api.GenerationRange(0, 6000), raw, 7000)
        self.assertEqual(
            [(row["start_ms"], row["end_ms"]) for row in result.segments],
            [(1000, 3250), (3250, 5000)],
        )
        self.assertEqual(result.overlap_repairs, 1)
        self.assertEqual(result.segments[0]["text"], "speech")
        self.assertEqual(result.segments[1]["text"], "speech")
        self.assertEqual(raw[0]["end_ms"], 3500)
        self.assertEqual(raw[1]["start_ms"], 3000)

    def test_chained_overlaps_are_repaired_in_original_order(self):
        api = self._api()
        rows = [segment(1000, 3000), segment(2500, 5000), segment(4500, 6500)]
        result = api.reconcile_generated_timing(api.GenerationRange(0, 8000), rows, 9000)
        self.assertEqual(
            [(row["start_ms"], row["end_ms"]) for row in result.segments],
            [(1000, 2750), (2750, 4750), (4750, 6500)],
        )
        self.assertEqual(result.overlap_repairs, 2)
        self.assertEqual([row["text"] for row in result.segments], ["speech"] * 3)

    def test_overlap_requiring_sub_minimum_segments_is_unsafe(self):
        api = self._api()
        result = api.reconcile_generated_timing(
            api.GenerationRange(0, 2000),
            [segment(1000, 1100), segment(1050, 1150)],
            3000,
        )
        self.assertEqual(result.status, api.ReconciliationStatus.CONFLICT)
        self.assertIn("minimum", result.reason.casefold())

    def test_valid_gaps_are_never_closed(self):
        api = self._api()
        result = api.reconcile_generated_timing(
            api.GenerationRange(0, 5000),
            [segment(1000, 2000), segment(2500, 3500)],
            6000,
        )
        self.assertEqual(result.segments[1]["start_ms"] - result.segments[0]["end_ms"], 500)
        self.assertEqual(result.overlap_repairs, 0)

    def test_current_subtitle_intersection_is_reported_as_stale_range_conflict(self):
        api = self._api()
        rows = [segment(1200, 1800, id="new-current")]
        result = api.reconcile_generated_timing(
            api.GenerationRange(1000, 2000),
            [segment(1000, 1400)],
            5000,
            current_subtitles=rows,
        )
        self.assertEqual(result.status, api.ReconciliationStatus.STALE_RANGE_CONFLICT)
        self.assertEqual(rows, [segment(1200, 1800, id="new-current")])

    def test_uncovered_range_uses_neighbor_safe_window_and_keeps_neighbors_unchanged(self):
        api = self._api()
        before = segment(0, 1000, id="before", extra={"stable": True})
        after = segment(3000, 4000, id="after", extra={"stable": True})
        current = [before, after]
        result = api.reconcile_generated_timing(
            api.GenerationRange(1000, 3000),
            [segment(900, 2600)],
            5000,
            current_subtitles=current,
        )
        self.assertEqual(result.status, api.ReconciliationStatus.SUCCESS)
        self.assertEqual((result.segments[0]["start_ms"], result.segments[0]["end_ms"]), (1000, 2700))
        self.assertEqual(current, [before, after])
        self.assertEqual(before, segment(0, 1000, id="before", extra={"stable": True}))
        self.assertEqual(after, segment(3000, 4000, id="after", extra={"stable": True}))

    def test_invalid_structure_empty_and_unsorted_batches_fail_without_mutation(self):
        api = self._api()
        empty = api.reconcile_generated_timing(api.GenerationRange(0, 1000), [], 1000)
        self.assertEqual(empty.status, api.ReconciliationStatus.EMPTY_RESULT)
        for rows in (
            [segment(500, 500)],
            [segment(500, 400)],
            [segment(float("inf"), 700)],
            [segment(600, 800), segment(100, 300)],
        ):
            original = [dict(row) for row in rows]
            result = api.reconcile_generated_timing(api.GenerationRange(0, 1000), rows, 1000)
            self.assertEqual(result.status, api.ReconciliationStatus.CONFLICT)
            self.assertEqual(rows, original)

    def test_invalid_safe_window_outside_media_is_rejected(self):
        api = self._api()
        result = api.reconcile_generated_timing(
            api.GenerationRange(1000, 3000), [segment(1000, 2000)], 2500
        )
        self.assertEqual(result.status, api.ReconciliationStatus.CONFLICT)

    def test_zero_duration_word_token_is_preserved_without_conflict(self):
        api = self._api()
        seg_with_zero_word = {
            "start_ms": 331500,
            "end_ms": 335000,
            "text": "特にこのピュアマーメイド",
            "words": [
                {"word": "特に", "start_ms": 331500, "end_ms": 332200},
                {"word": "ピュ", "start_ms": 332600, "end_ms": 332980},
                {"word": "ア", "start_ms": 332980, "end_ms": 332980},
                {"word": "マーメイド", "start_ms": 332980, "end_ms": 335000},
            ],
        }
        result = api.reconcile_generated_timing(
            api.GenerationRange(331000, 345000), [seg_with_zero_word], 600000
        )
        self.assertEqual(result.status, api.ReconciliationStatus.SUCCESS)
        self.assertEqual(result.global_shift_ms, 0)
        self.assertEqual(len(result.segments[0]["words"]), 4)
        self.assertEqual(
            result.segments[0]["words"][2],
            {"word": "ア", "start_ms": 332980, "end_ms": 332980},
        )

        # Edge clamp on a 0-ms token keeps start_ms == end_ms clamped inside [start_ms, end_ms]
        clamped_segs = [
            {
                "start_ms": 9800,
                "end_ms": 10800,
                "text": "a",
                "words": [
                    {"word": "、", "start_ms": 9850, "end_ms": 9850},
                    {"word": "a", "start_ms": 10050, "end_ms": 10800},
                ],
            },
            segment(14200, 15300, text="b"),
        ]
        clamped_res = api.reconcile_generated_timing(
            api.GenerationRange(10000, 15000), clamped_segs, 20000
        )
        self.assertEqual(clamped_res.status, api.ReconciliationStatus.SUCCESS)
        self.assertEqual(clamped_res.segments[0]["words"][0]["start_ms"], 10000)
        self.assertEqual(clamped_res.segments[0]["words"][0]["end_ms"], 10000)

    def test_positive_duration_word_collapsed_by_boundary_clamp_still_conflicts(self):
        api = self._api()
        # Positive-duration word [9800..9950] lies wholly outside clamped [10000..10800] -> CONFLICT
        rows = [
            {
                "start_ms": 9800,
                "end_ms": 10800,
                "text": "ab",
                "words": [
                    {"word": "a", "start_ms": 9800, "end_ms": 9950},
                    {"word": "b", "start_ms": 10100, "end_ms": 10800},
                ],
            },
            segment(14200, 15300, text="c"),
        ]
        result = api.reconcile_generated_timing(
            api.GenerationRange(10000, 15000), rows, 20000
        )
        self.assertEqual(result.status, api.ReconciliationStatus.CONFLICT)
        self.assertEqual(result.reason, "Boundary adjustment would invalidate word timing.")

        # Negative-duration word (orig_end < orig_start) -> invalid word timing CONFLICT
        neg_row = {
            "start_ms": 1000,
            "end_ms": 2000,
            "text": "bad",
            "words": [{"word": "bad", "start_ms": 1500, "end_ms": 1400}],
        }
        neg_result = api.reconcile_generated_timing(
            api.GenerationRange(1000, 3000), [neg_row], 5000
        )
        self.assertEqual(neg_result.status, api.ReconciliationStatus.CONFLICT)
        self.assertEqual(neg_result.reason, "Generated word timing is invalid.")
