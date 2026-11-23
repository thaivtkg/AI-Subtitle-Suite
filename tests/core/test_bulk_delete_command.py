# -*- coding: utf-8 -*-
from core.subtitle_editing.commands.delete_command import DeleteCommand
from core.subtitle_editing.global_undo_manager import GlobalUndoManager


def _make_segments(count: int) -> list[dict]:
    return [
        {
            "id": f"seg-{i + 1}",
            "stt": str(i + 1),
            "start": f"00:00:{i * 2:02d},000",
            "end": f"00:00:{i * 2 + 1:02d},500",
            "start_ms": i * 2000,
            "end_ms": i * 2000 + 1500,
            "text": f"Line {i + 1}",
            "style_preset": "loud" if i % 2 else "normal",
            "translation": f"Dịch {i + 1}",
            "words": [{"word": f"Line{i + 1}", "start_ms": i * 2000, "end_ms": i * 2000 + 1500}],
        }
        for i in range(count)
    ]


def test_delete_command_single_int_backward_compatible():
    segs = _make_segments(4)
    mgr = GlobalUndoManager()
    cmd = DeleteCommand(1, segs)

    assert cmd.segment_index == 1
    assert cmd.indices == [1]
    assert cmd.text() == "Xóa Subtitle"

    mgr.push(cmd)
    assert cmd.deleted_segment["id"] == "seg-2"
    assert [s["id"] for s in segs] == ["seg-1", "seg-3", "seg-4"]
    assert [s["stt"] for s in segs] == ["1", "2", "3"]

    mgr.undo()
    assert [s["id"] for s in segs] == ["seg-1", "seg-2", "seg-3", "seg-4"]
    assert [s["stt"] for s in segs] == ["1", "2", "3", "4"]

    mgr.redo()
    assert [s["id"] for s in segs] == ["seg-1", "seg-3", "seg-4"]


def test_delete_command_bulk_non_contiguous_and_contiguous_atomic_undo_redo():
    segs = _make_segments(7)
    snapshot = [dict(s) for s in segs]
    mgr = GlobalUndoManager()

    # Non-contiguous [0, 3, 5] -> 1 atomic command
    cmd = DeleteCommand([5, 0, 3], segs)
    assert cmd.indices == [0, 3, 5]
    assert cmd.text() == "Xóa 3 Subtitle"
    assert cmd.deleted_segment is None

    mgr.push(cmd)
    assert [s["id"] for s in segs] == ["seg-2", "seg-3", "seg-5", "seg-7"]
    assert [s["stt"] for s in segs] == ["1", "2", "3", "4"]

    # Single Ctrl+Z restores all 3 with exact positions and metadata
    mgr.undo()
    assert [s["id"] for s in segs] == [s["id"] for s in snapshot]
    assert [s["stt"] for s in segs] == [str(i + 1) for i in range(7)]
    for orig, restored in zip(snapshot, segs):
        assert restored["text"] == orig["text"]
        assert restored["translation"] == orig["translation"]
        assert restored["style_preset"] == orig["style_preset"]
        assert restored["words"] == orig["words"]

    # Single Ctrl+Y deletes all 3 again
    mgr.redo()
    assert [s["id"] for s in segs] == ["seg-2", "seg-3", "seg-5", "seg-7"]
    assert [s["stt"] for s in segs] == ["1", "2", "3", "4"]


def test_delete_command_all_segments_and_full_restore():
    segs = _make_segments(3)
    mgr = GlobalUndoManager()

    mgr.push(DeleteCommand([0, 1, 2], segs))
    assert segs == []

    mgr.undo()
    assert [s["id"] for s in segs] == ["seg-1", "seg-2", "seg-3"]
    assert [s["stt"] for s in segs] == ["1", "2", "3"]


def test_delete_command_deduplicates_and_ignores_out_of_bounds_indices():
    segs = _make_segments(4)
    mgr = GlobalUndoManager()

    cmd = DeleteCommand([-1, 2, 2, 999, 0], segs)
    assert cmd.indices == [0, 2]
    assert cmd.text() == "Xóa 2 Subtitle"

    mgr.push(cmd)
    assert [s["id"] for s in segs] == ["seg-2", "seg-4"]
    assert [s["stt"] for s in segs] == ["1", "2"]

    mgr.undo()
    assert [s["id"] for s in segs] == ["seg-1", "seg-2", "seg-3", "seg-4"]
