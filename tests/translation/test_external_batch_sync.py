import os
import pytest
from PySide6.QtCore import QCoreApplication
from core.translation.controllers.project_controller import ProjectController
from core.translation.models.subtitle import SubtitleModel
from core.translation.core.srt_exporter import SRTExporter


@pytest.fixture(autouse=True)
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


def test_batch_detection_on_import(tmp_path):
    model = SubtitleModel()
    ctrl = ProjectController(model)

    # 1. Normal file (non-batch)
    normal_file = tmp_path / "movie.srt"
    normal_file.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n\n", encoding="utf-8")
    ctrl.importSrt(str(normal_file))

    assert ctrl.isBatchMode is False
    assert ctrl.batchStartNum == 0
    assert ctrl.batchEndNum == 0
    assert ctrl.batchLabel == ""
    assert ctrl.originalSourcePath == str(normal_file)

    # 2. Batch file matching pattern project_batch_1_to_5.srt
    batch_file = tmp_path / "project_batch_1_to_5.srt"
    batch_file.write_text(
        "1\n00:00:01,123 --> 00:00:03,456\nFirst line\n\n"
        "2\n00:00:04,000 --> 00:00:06,789\nSecond line\n\n",
        encoding="utf-8"
    )
    ctrl.importSrt(str(batch_file))

    assert ctrl.isBatchMode is True
    assert ctrl.batchStartNum == 1
    assert ctrl.batchEndNum == 5
    assert ctrl.batchLabel == "Đợt #1 ➔ #5"
    assert ctrl.originalSourcePath == str(batch_file)


def test_quick_sync_to_original(tmp_path):
    model = SubtitleModel()
    ctrl = ProjectController(model)

    batch_file = tmp_path / "scene_batch_1_to_2.srt"
    batch_file.write_text(
        "1\n00:00:01,100 --> 00:00:03,200\nMagic circle\n\n"
        "2\n00:00:04,500 --> 00:00:07,800\nShadow monarch\n\n",
        encoding="utf-8"
    )
    ctrl.importSrt(str(batch_file))
    assert ctrl.isBatchMode is True

    # Translate lines
    model.update_translation(0, "Vòng ma pháp", "ACCEPTED")
    model.update_translation(1, "Quân vương bóng tối", "ACCEPTED")

    # Quick sync
    ok = ctrl.quickSyncToOriginal()
    assert ok is True

    # Verify content written to original file
    content = batch_file.read_text(encoding="utf-8")
    assert "00:00:01,100 --> 00:00:03,200" in content
    assert "Vòng ma pháp" in content
    assert "00:00:04,500 --> 00:00:07,800" in content
    assert "Quân vương bóng tối" in content


def test_append_next_batch_and_preserve_intelligence(tmp_path):
    model = SubtitleModel()
    ctrl = ProjectController(model)

    # 1. Import Batch 1
    batch1_file = tmp_path / "ep1_batch_1_to_2.srt"
    batch1_file.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nSenpai arrives\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nHe greets teacher\n\n",
        encoding="utf-8"
    )
    ctrl.importSrt(str(batch1_file))
    assert model.rowCount() == 2
    assert ctrl.batchStartNum == 1
    assert ctrl.batchEndNum == 2

    # Add glossary in batch 1
    ctrl.addManualGlossaryTerm("Senpai", "Tiền bối")
    assert len(ctrl.glossaryTerms) == 1

    # 2. Append Batch 2 (lines 3 to 4)
    batch2_file = tmp_path / "ep1_batch_3_to_4.srt"
    batch2_file.write_text(
        "1\n00:00:07,000 --> 00:00:09,000\nSenpai smiles\n\n"
        "2\n00:00:10,000 --> 00:00:12,000\nTeacher waves\n\n",
        encoding="utf-8"
    )
    ok = ctrl.appendNextBatch(str(batch2_file))
    assert ok is True

    # Model now has 4 rows
    assert model.rowCount() == 4
    all_data = model.get_all_data()
    # Check that indices are sequential 1, 2, 3, 4
    assert [d["index"] for d in all_data] == [1, 2, 3, 4]
    assert all_data[2]["original"] == "Senpai smiles"
    assert all_data[3]["original"] == "Teacher waves"

    # Batch end num extended to 4
    assert ctrl.batchEndNum == 4
    assert ctrl.batchLabel == "Đợt #1 ➔ #4"

    # Glossary remains intact
    assert len(ctrl.glossaryTerms) == 1
    assert ctrl.glossaryTerms[0]["source_term"] == "Senpai"


def test_srt_exporter_millisecond_preservation(tmp_path):
    subs = [
        {"index": 1, "start_time": "00:01:23,456", "end_time": "00:01:25,789", "original": "Hi", "translation": "Chào", "status": "ACCEPTED"},
        {"index": 2, "start_time": 90000, "end_time": 92500, "original": "Bye", "translation": "Tạm biệt", "status": "ACCEPTED"},
    ]
    out_file = tmp_path / "test_ms.srt"
    success, _ = SRTExporter.export(subs, str(out_file))
    assert success is True

    content = out_file.read_text(encoding="utf-8")
    assert "00:01:23,456 --> 00:01:25,789" in content
    assert "00:01:30,000 --> 00:01:32,500" in content


def test_quick_sync_creates_sidecar_aisrt(tmp_path):
    import json
    model = SubtitleModel()
    ctrl = ProjectController(model)

    batch_file = tmp_path / "scene_batch_1_to_2.srt"
    batch_file.write_text(
        "1\n00:00:01,100 --> 00:00:03,200\nMagic circle\n\n"
        "2\n00:00:04,500 --> 00:00:07,800\nShadow monarch\n\n",
        encoding="utf-8"
    )
    ctrl.importSrt(str(batch_file))
    ctrl.addManualGlossaryTerm("Magic circle", "Vòng ma pháp")
    model.update_translation(0, "Vòng ma pháp", "ACCEPTED")

    ok = ctrl.quickSyncToOriginal()
    assert ok is True

    # Sidecar .aisrt must exist alongside the .srt
    sidecar_path = tmp_path / "scene_batch_1_to_2.aisrt"
    assert sidecar_path.exists()

    with open(sidecar_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["subtitles"]) == 2
    assert data["subtitles"][0]["status"] == "ACCEPTED"
    assert data["subtitles"][0]["translation"] == "Vòng ma pháp"
    assert len(data["intelligence"]["glossary"]) == 1


def test_import_srt_restores_from_sidecar_aisrt(tmp_path):
    model = SubtitleModel()
    ctrl = ProjectController(model)

    # 1. First session: import, edit, sync (creates sidecar)
    batch_file = tmp_path / "dialogue_batch_1_to_2.srt"
    batch_file.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\n妖魔王やっと見つけたわ\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\n誰だお前は\n\n",
        encoding="utf-8"
    )
    ctrl.importSrt(str(batch_file))
    ctrl.addManualGlossaryTerm("妖魔王", "Yêu Ma Vương")
    model.update_translation(0, "Cuối cùng ta cũng tìm thấy ngươi, Yêu Ma Vương", "ACCEPTED")
    assert ctrl.quickSyncToOriginal() is True

    # 2. Second session: fresh controller imports the same SRT file
    # After sync, the SRT file's line 1 has Vietnamese text
    model2 = SubtitleModel()
    ctrl2 = ProjectController(model2)
    ctrl2.importSrt(str(batch_file))

    # Verification: sentence 1 is ACCEPTED, not PENDING!
    subs = model2.get_all_data()
    assert len(subs) == 2
    assert subs[0]["status"] == "ACCEPTED"
    assert subs[0]["translation"] == "Cuối cùng ta cũng tìm thấy ngươi, Yêu Ma Vương"
    # True original Japanese is restored despite SRT being overwritten with Vietnamese
    assert subs[0]["original"] == "妖魔王やっと見つけたわ"

    # Sentence 2 was never translated, status is pending
    assert str(subs[1]["status"]).upper() == "PENDING"
    assert subs[1]["original"] == "誰だお前は"

    # Intelligence restored
    assert len(ctrl2.glossaryTerms) == 1
    assert ctrl2.glossaryTerms[0]["source_term"] == "妖魔王"


def test_append_batch_emits_batch_appended(tmp_path):
    model = SubtitleModel()
    ctrl = ProjectController(model)

    batch1_file = tmp_path / "ep1_batch_1_to_2.srt"
    batch1_file.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nLine 1\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nLine 2\n\n",
        encoding="utf-8"
    )
    ctrl.importSrt(str(batch1_file))

    batch2_file = tmp_path / "ep1_batch_3_to_4.srt"
    batch2_file.write_text(
        "1\n00:00:07,000 --> 00:00:09,000\nLine 3\n\n"
        "2\n00:00:10,000 --> 00:00:12,000\nLine 4\n\n",
        encoding="utf-8"
    )

    emitted_indices = []
    ctrl.batchAppended.connect(lambda idx: emitted_indices.append(idx))

    ok = ctrl.appendNextBatch(str(batch2_file))
    assert ok is True
    assert emitted_indices == [2]


def test_multi_batch_sync_writes_to_respective_batch_files(tmp_path):
    model = SubtitleModel()
    ctrl = ProjectController(model)

    batch1 = tmp_path / "ep1_batch_1_to_5.srt"
    batch1.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nOriginal 1\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nOriginal 2\n\n",
        encoding="utf-8"
    )
    ctrl.importSrt(str(batch1))
    assert model.rowCount() == 2

    batch2 = tmp_path / "ep1_batch_6_to_10.srt"
    batch2.write_text(
        "1\n00:00:05,000 --> 00:00:06,000\nOriginal 3\n\n"
        "2\n00:00:07,000 --> 00:00:08,000\nOriginal 4\n\n",
        encoding="utf-8"
    )
    ok = ctrl.appendNextBatch(str(batch2))
    assert ok is True
    assert model.rowCount() == 4

    # Update translations in both batches
    model.update_translation(0, "Dịch 1", "ACCEPTED")
    model.update_translation(2, "Dịch 3", "ACCEPTED")

    # Quick sync must update BOTH files without overwriting each other
    sync_ok = ctrl.quickSyncToOriginal()
    assert sync_ok is True

    # Check batch 1
    content1 = batch1.read_text(encoding="utf-8")
    assert "Dịch 1" in content1
    assert "Original 2" in content1
    assert "Dịch 3" not in content1  # Batch 2 line must NOT be in batch 1!
    assert (tmp_path / "ep1_batch_1_to_5.aisrt").exists()

    # Check batch 2
    content2 = batch2.read_text(encoding="utf-8")
    assert "Dịch 3" in content2
    assert "Original 4" in content2
    assert "Dịch 1" not in content2  # Batch 1 line must NOT be in batch 2!
    assert (tmp_path / "ep1_batch_6_to_10.aisrt").exists()


def test_batch_append_deduplication_by_timecode(tmp_path):
    model = SubtitleModel()
    ctrl = ProjectController(model)

    # Batch 1 has lines 1 and 2
    batch1 = tmp_path / "scene_batch_1_to_2.srt"
    batch1.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nLine 1\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nLine 2\n\n",
        encoding="utf-8"
    )
    ctrl.importSrt(str(batch1))
    assert model.rowCount() == 2

    # Cumulative batch has lines 1 and 2 (duplicate timecodes) plus lines 3 and 4
    batch_cumulative = tmp_path / "scene_batch_3_to_4.srt"
    batch_cumulative.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nLine 1 Duplicate\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nLine 2 Duplicate\n\n"
        "3\n00:00:05,000 --> 00:00:06,000\nLine 3 New\n\n"
        "4\n00:00:07,000 --> 00:00:08,000\nLine 4 New\n\n",
        encoding="utf-8"
    )
    ok = ctrl.appendNextBatch(str(batch_cumulative))
    assert ok is True
    # Rows must be 4, NOT 6!
    assert model.rowCount() == 4
    all_data = model.get_all_data()
    assert all_data[0]["original"] == "Line 1"
    assert all_data[1]["original"] == "Line 2"
    assert all_data[2]["original"] == "Line 3 New"
    assert all_data[3]["original"] == "Line 4 New"


def test_pure_model_archetype_prompt():
    from core.translation.core.prompt_builder import PromptBuilder
    from core.translation.core.context_analyzer import ARCHETYPE_PURE

    prompt = PromptBuilder.build(
        story_summary="Cuộc chiến Ma Vương và Thủy Thủ Thiên Thần",
        source_lang="Japanese",
        target_lang="Vietnamese",
        current_sub="妖魔王やっと見つけたわ",
        is_ja_origin=True,
        archetype=ARCHETYPE_PURE,
        active_pronoun_pair="",
    )

    # Pillars present
    assert "STORY SUMMARY" in prompt
    assert "Cuộc chiến Ma Vương" in prompt
    assert "STRICT OUTPUT FORMAT" in prompt
    assert "VIETNAMESE PURITY" in prompt

    # No forced pronouns or school honorifics
    assert "PRONOUN RELATIONSHIP" not in prompt
    assert "JAPANESE TRANSLATION ARTIFACTS" not in prompt
    assert "tiền bối" not in prompt
    assert "senpai" not in prompt


def test_japanese_origin_does_not_force_anime_school_archetype(tmp_path):
    from core.translation.core.context_analyzer import ARCHETYPE_CUSTOM
    model = SubtitleModel()
    ctrl = ProjectController(model)

    ja_file = tmp_path / "ja_scene.srt"
    ja_file.write_text(
        "1\n00:00:15,350 --> 00:00:17,540\n妖魔王やっと見つけたわ\n\n"
        "2\n00:00:19,720 --> 00:00:20,660\n誰だお前は\n\n",
        encoding="utf-8"
    )
    ctrl.importSrt(str(ja_file))

    assert ctrl.isJaOrigin is True
    # Must remain CUSTOM (or whichever user picked), NOT forced to anime_school!
    assert ctrl.activeArchetype == ARCHETYPE_CUSTOM
    assert "Tiền bối" not in ctrl.activePronounPair


def test_import_pretranslated_vietnamese_srt_without_sidecar(tmp_path):
    model = SubtitleModel()
    ctrl = ProjectController(model)

    vi_file = tmp_path / 'JMSZ38_02_batch_1_to_5.srt'
    vi_file.write_text(
        '1\n00:00:15,350 --> 00:00:17,540\nCuối cùng đã tìm thấy ngươi rồi Ma Vương\n\n'
        '2\n00:00:19,720 --> 00:00:20,660\nNgươi là ai vậy hả?\n\n',
        encoding='utf-8'
    )
    ctrl.importSrt(str(vi_file))

    assert ctrl._source_language == 'Vietnamese'
    data = model.get_all_data()
    assert len(data) == 2
    assert data[0]['original'] == 'Cuối cùng đã tìm thấy ngươi rồi Ma Vương'
    assert data[0]['translation'] == 'Cuối cùng đã tìm thấy ngươi rồi Ma Vương'
    assert data[0]['status'] == 'ACCEPTED'
    assert data[1]['original'] == 'Ngươi là ai vậy hả?'
    assert data[1]['translation'] == 'Ngươi là ai vậy hả?'
    assert data[1]['status'] == 'ACCEPTED'


def test_append_pretranslated_vietnamese_batch_without_sidecar(tmp_path):
    model = SubtitleModel()
    ctrl = ProjectController(model)

    batch1 = tmp_path / 'proj_batch_1_to_2.srt'
    batch1.write_text(
        '1\n00:00:01,000 --> 00:00:03,000\nHello world\n\n'
        '2\n00:00:04,000 --> 00:00:06,000\nWelcome here\n\n',
        encoding='utf-8'
    )
    ctrl.importSrt(str(batch1))
    assert model.rowCount() == 2

    batch2 = tmp_path / 'proj_batch_3_to_4.srt'
    batch2.write_text(
        '1\n00:00:07,000 --> 00:00:09,000\nChào mừng bạn đến đây\n\n'
        '2\n00:00:10,000 --> 00:00:12,000\nHẹn gặp lại lần sau\n\n',
        encoding='utf-8'
    )
    ok = ctrl.appendNextBatch(str(batch2))
    assert ok is True
    assert model.rowCount() == 4

    data = model.get_all_data()
    assert data[0]['original'] == 'Hello world'
    assert data[0]['translation'] == ''
    assert data[0]['status'] == 'PENDING'
    assert data[2]['original'] == 'Chào mừng bạn đến đây'
    assert data[2]['translation'] == 'Chào mừng bạn đến đây'
    assert data[2]['status'] == 'ACCEPTED'
    assert data[3]['original'] == 'Hẹn gặp lại lần sau'
    assert data[3]['translation'] == 'Hẹn gặp lại lần sau'
    assert data[3]['status'] == 'ACCEPTED'


def test_import_pretranslated_vietnamese_srt_with_empty_sidecar(tmp_path):
    import json
    model = SubtitleModel()
    ctrl = ProjectController(model)

    srt_file = tmp_path / 'batch_6_to_10.srt'
    srt_file.write_text(
        '1\n00:00:15,350 --> 00:00:17,540\nCuối cùng đã tìm thấy ngươi rồi Ma Vương\n\n'
        '2\n00:00:19,720 --> 00:00:20,660\nNgươi là ai vậy hả?\n\n',
        encoding='utf-8'
    )
    aisrt_file = tmp_path / 'batch_6_to_10.aisrt'
    aisrt_payload = {
        'metadata': {'source_language': 'English', 'source_file': 'batch_6_to_10.srt'},
        'story_summary': '',
        'subtitles': [
            {'index': 1, 'start_time': '00:00:15,350', 'end_time': '00:00:17,540', 'original': 'Cuối cùng đã tìm thấy ngươi rồi Ma Vương', 'translation': '', 'status': 'pending'},
            {'index': 2, 'start_time': '00:00:19,720', 'end_time': '00:00:20,660', 'original': 'Ngươi là ai vậy hả?', 'translation': '', 'status': 'pending'}
        ]
    }
    aisrt_file.write_text(json.dumps(aisrt_payload, ensure_ascii=False), encoding='utf-8')

    ctrl.importSrt(str(srt_file))
    data = model.get_all_data()
    assert len(data) == 2
    assert data[0]['translation'] == 'Cuối cùng đã tìm thấy ngươi rồi Ma Vương'
    assert data[0]['status'] == 'ACCEPTED'
    assert data[1]['translation'] == 'Ngươi là ai vậy hả?'
    assert data[1]['status'] == 'ACCEPTED'


def test_load_project_pretranslated_vietnamese_with_empty_sidecar(tmp_path):
    import json
    model = SubtitleModel()
    ctrl = ProjectController(model)

    aisrt_file = tmp_path / 'batch_legacy.aisrt'
    aisrt_payload = {
        'metadata': {'source_language': 'English', 'source_file': 'batch_legacy.srt'},
        'story_summary': '',
        'subtitles': [
            {'index': 1, 'start_time': '00:00:15,350', 'end_time': '00:00:17,540', 'original': 'Cuối cùng đã tìm thấy ngươi rồi Ma Vương', 'translation': '', 'status': 'pending'},
            {'index': 2, 'start_time': '00:00:19,720', 'end_time': '00:00:20,660', 'original': 'Ngươi là ai vậy hả?', 'translation': '', 'status': 'pending'}
        ]
    }
    aisrt_file.write_text(json.dumps(aisrt_payload, ensure_ascii=False), encoding='utf-8')

    ctrl.loadProject(str(aisrt_file))
    data = model.get_all_data()
    assert len(data) == 2
    assert data[0]['translation'] == 'Cuối cùng đã tìm thấy ngươi rồi Ma Vương'
    assert data[0]['status'] == 'ACCEPTED'
    assert data[1]['translation'] == 'Ngươi là ai vậy hả?'
    assert data[1]['status'] == 'ACCEPTED'

