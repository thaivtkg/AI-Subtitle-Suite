import pytest
from PySide6.QtCore import QModelIndex
from core.translation.models.subtitle import SubtitleModel

def test_subtitle_model_qa_roles_o1():
    model = SubtitleModel()
    data = [
        {
            "index": 1,
            "start_time": "00:00:01,000",
            "end_time": "00:00:02,000",
            "original": "Short text",
            "translation": "Câu ngắn chuẩn",
            "status": "TRANSLATED"
        },
        {
            "index": 2,
            "start_time": "00:00:03,000",
            "end_time": "00:00:04,000",
            "original": "Fast text",
            "translation": "Đây là câu dịch có tốc độ đọc cực kỳ nhanh vượt ngưỡng 20 ký tự trên giây",
            "status": "TRANSLATED"
        }
    ]
    model.load_data(data)

    idx_clean = model.index(0, 0)
    assert model.data(idx_clean, SubtitleModel.QaSeverityRole) == ""
    assert model.data(idx_clean, SubtitleModel.QaTooltipRole) == ""

    idx_error = model.index(1, 0)
    assert model.data(idx_error, SubtitleModel.QaSeverityRole) == "ERROR"
    assert "Tốc độ đọc" in model.data(idx_error, SubtitleModel.QaTooltipRole)

    # Verify cached fields in item dictionary
    assert data[0]["_qa_severity"] == ""
    assert data[1]["_qa_severity"] == "ERROR"

def test_subtitle_model_qa_reactivity():
    model = SubtitleModel()
    data = [{
        "index": 1,
        "start_time": "00:00:01,000",
        "end_time": "00:00:02,000",
        "original": "Hello",
        "translation": "",
        "status": "PENDING"
    }]
    model.load_data(data)
    idx = model.index(0, 0)
    assert model.data(idx, SubtitleModel.QaSeverityRole) == ""

    # Update to an error translation (CPS > 20)
    model.update_translation(0, "Câu này quá dài trong vòng một giây và vượt ngưỡng đọc", "TRANSLATED")
    assert model.data(idx, SubtitleModel.QaSeverityRole) == "ERROR"
    assert data[0]["_qa_severity"] == "ERROR"

    # Fix it to a short translation
    model.update_translation(0, "Ngắn", "EDITED")
    assert model.data(idx, SubtitleModel.QaSeverityRole) == ""
    assert data[0]["_qa_severity"] == ""

def test_subtitle_model_get_all_data_slot_qml_accessible():
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtQml import QQmlEngine, QQmlComponent

    model = SubtitleModel()
    model.load_data([
        {"index": 1, "start_time": "00:01:00,000", "end_time": "00:01:02,000", "original": "First", "translation": "", "status": "PENDING"},
        {"index": 2, "start_time": "00:02:00,000", "end_time": "00:02:02,000", "original": "Second", "translation": "", "status": "PENDING"}
    ])

    app = QCoreApplication.instance() or QCoreApplication([])
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("subtitleModel", model)

    component = QQmlComponent(engine)
    qml = b"""
    import QtQuick 2.15
    QtObject {
        property var allSubs: subtitleModel.get_all_data()
        property int subCount: allSubs ? allSubs.length : -1
    }
    """
    component.setData(qml, "")
    assert not component.isError(), [e.toString() for e in component.errors()]
    obj = component.create()
    assert obj is not None
    assert obj.property("subCount") == 2


