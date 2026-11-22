from core.subtitle_editing.global_undo_manager import GlobalUndoManager
from ui.SubEditor import SubtitleEditorWidget
from ui.pages.translation_studio_page import TranslationStudioPage


def _studio_segment():
    return {
        "id": "segment-6",
        "stt": "6",
        "start": "00:00:33,960",
        "end": "00:00:37,070",
        "text": "この俺様に一体何の",
        "original_text": "この俺様に一体何の",
        "translation": "Đến tớ đây thì làm cái gì",
        "translation_status": "TRANSLATED",
    }


def _cat_row():
    return {
        "segment_id": "segment-6",
        "studio_index": 0,
        "index": 6,
        "original": "この俺様に一体何の",
        "translation": "Đến tớ đây thì làm cái gì",
        "status": "TRANSLATED",
    }


def test_editor_translation_is_approved_and_undo_restores_draft(qtbot):
    editor = SubtitleEditorWidget()
    qtbot.addWidget(editor)
    manager = GlobalUndoManager()
    editor.undo_manager = manager
    editor.all_segments = [_studio_segment()]
    editor.render_page()
    editor.select_segment(0)

    editor._apply_current_editor({
        "start": "00:00:33,960",
        "end": "00:00:37,070",
        "text": "Rốt cuộc ngươi tìm ta có chuyện gì?",
    })
    segment = editor.all_segments[0]
    assert segment["text"] == segment["translation"]
    assert segment["translation_status"] == "ACCEPTED"

    manager.undo()
    assert segment["text"] == segment["original_text"]
    assert segment["translation"] == _cat_row()["translation"]
    assert segment["translation_status"] == "TRANSLATED"
    manager.redo()
    assert segment["translation_status"] == "ACCEPTED"

    editor._apply_current_editor({
        "start": segment["start"],
        "end": segment["end"],
        "text": "Rốt cuộc ngươi tìm ta làm gì?",
    })
    assert segment["translation"] == "Rốt cuộc ngươi tìm ta làm gì?"
    manager.undo()
    assert segment["text"] == segment["original_text"]
    assert segment["translation_status"] == "TRANSLATED"
    manager.redo()

    page = TranslationStudioPage()
    qtbot.addWidget(page)
    page.subtitle_model.load_data([_cat_row()])
    page._has_loaded_from_studio = True
    page.sync_translations_from_studio(editor.all_segments)
    assert page.subtitle_model.rowCount() == 0


def test_existing_editor_translation_pruned_without_rewriting_source(qtbot):
    page = TranslationStudioPage()
    qtbot.addWidget(page)
    page.subtitle_model.load_data([_cat_row()])
    page._has_loaded_from_studio = True
    segment = _studio_segment()
    segment.pop("original_text")
    segment.pop("translation")
    segment.pop("translation_status")
    segment["text"] = "Rốt cuộc ngươi tìm ta có chuyện gì?"
    # Follow the real project-loading order: export the saved CAT draft, then sync.
    page.export_subtitles_to_studio([segment])

    page.sync_translations_from_studio([segment])

    assert page.subtitle_model.rowCount() == 0
    assert segment["original_text"] == _cat_row()["original"]
    assert segment["translation"] == segment["text"]
    assert segment["translation_status"] == "ACCEPTED"


def test_unchanged_source_stays_in_translation_queue(qtbot):
    page = TranslationStudioPage()
    qtbot.addWidget(page)
    page.subtitle_model.load_data([_cat_row()])
    page._has_loaded_from_studio = True
    segment = _studio_segment()

    page.sync_translations_from_studio([segment])

    assert page.subtitle_model.rowCount() == 1
    assert segment["translation_status"] == "TRANSLATED"


def test_editing_source_without_translation_does_not_approve(qtbot):
    editor = SubtitleEditorWidget()
    qtbot.addWidget(editor)
    editor.undo_manager = GlobalUndoManager()
    segment = _studio_segment()
    segment["translation"] = ""
    segment["translation_status"] = "PENDING"
    editor.all_segments = [segment]
    editor.render_page()
    editor.select_segment(0)

    editor._apply_current_editor({
        "start": segment["start"],
        "end": segment["end"],
        "text": "この俺様に一体何の？",
    })

    assert segment["translation"] == ""
    assert segment["translation_status"] == "PENDING"

    page = TranslationStudioPage()
    qtbot.addWidget(page)
    page.subtitle_model.load_data([_cat_row()])
    page._has_loaded_from_studio = True
    page.sync_translations_from_studio(editor.all_segments)
    assert page.subtitle_model.rowCount() == 1
    assert page.subtitle_model.get_item(0)["translation"] == _cat_row()["translation"]


def test_table_text_edit_approves_translation(qtbot):
    editor = SubtitleEditorWidget()
    qtbot.addWidget(editor)
    editor.undo_manager = GlobalUndoManager()
    editor.all_segments = [_studio_segment()]
    editor.render_page()

    editor.table.item(0, editor.COL_TEXT).setText("Bản dịch do người dùng sửa")
    editor.on_table_edit(0, editor.COL_TEXT)

    segment = editor.all_segments[0]
    assert segment["translation"] == "Bản dịch do người dùng sửa"
    assert segment["translation_status"] == "ACCEPTED"
