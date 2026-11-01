import pytest
from PySide6.QtCore import QCoreApplication
from core.translation.controllers.project_controller import ProjectController
from core.translation.controllers.translation_controller import TranslationController
from core.translation.models.subtitle import SubtitleModel


@pytest.fixture(autouse=True)
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


def test_sprint1_manual_glossary_and_flow():
    model = SubtitleModel()
    model.load_data([
        {"index": 1, "start_time": "00:00:01,000", "end_time": "00:00:03,000", "original": "Hello Senpai", "translation": "", "status": "PENDING"},
        {"index": 2, "start_time": "00:00:04,000", "end_time": "00:00:06,000", "original": "How are you Sensei", "translation": "", "status": "PENDING"},
    ])
    project_ctrl = ProjectController(model)
    trans_ctrl = TranslationController(model)
    trans_ctrl.bind_intelligence(
        glossary=project_ctrl.glossary,
        entities=project_ctrl.entity_dictionary,
        translation_memory=project_ctrl.translation_memory,
    )
    project_ctrl.bind_translation_controller(trans_ctrl)

    # 1. Add manual glossary term
    assert project_ctrl.addManualGlossaryTerm("Senpai", "Tiền bối", "anh, sếp") is True
    assert len(project_ctrl.glossaryTerms) == 1
    term = project_ctrl.glossaryTerms[0]
    assert term["source_term"] == "Senpai"
    assert term["preferred_translation"] == "Tiền bối"
    assert list(term["forbidden_alternatives"]) == ["anh", "sếp"]
    assert term["is_auto"] is False

    # 2. Check translation controller accept flow
    trans_ctrl.loadSubtitle(0)
    assert trans_ctrl.currentSubtitleIndex == 0
    ok = trans_ctrl.acceptTranslation(0, "Xin chào Tiền bối")
    assert ok is True
    assert model.get_all_data()[0]["status"] == "ACCEPTED"
    assert model.get_all_data()[0]["translation"] == "Xin chào Tiền bối"

    # TM has auto-cached it
    hit = trans_ctrl.translation_memory.lookup("Hello Senpai")
    assert hit is not None
    assert hit.target_text == "Xin chào Tiền bối"

