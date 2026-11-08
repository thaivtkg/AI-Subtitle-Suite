from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import QObject

def test_task_alert_triggers_flash_and_sound(qtbot):
    from ui.notifications.task_alert_service import TaskAlertService

    win = QWidget()
    qtbot.addWidget(win)
    service = TaskAlertService()
    service.alert_window = MagicMock()
    service.play_chime = MagicMock()

    res = service.notify_task_waiting_approval(win, "Task 1 hoàn tất, đang chờ bạn duyệt!")
    assert res is True
    service.alert_window.assert_called_once_with(win)
    service.play_chime.assert_called_once()

def test_task_alert_fallback_window_when_none(qtbot):
    from ui.notifications.task_alert_service import TaskAlertService

    win = QWidget()
    qtbot.addWidget(win)
    win.show()

    service = TaskAlertService()
    with patch.object(service, "alert_window") as mock_alert, \
         patch.object(service, "play_chime") as mock_chime:
        res = service.notify_task_waiting_approval(None, "Chờ duyệt")
        assert res is True
        mock_alert.assert_called_once()
        mock_chime.assert_called_once()

def test_task_alert_sound_graceful_degradation(qtbot):
    from ui.notifications.task_alert_service import TaskAlertService

    service = TaskAlertService()
    # Calling play_chime directly should not raise any unhandled exceptions
    # even in headless or mock audio environments
    try:
        service.play_chime()
    except Exception as exc:
        pytest.fail(f"play_chime raised unexpected exception: {exc}")

def test_task_alert_real_alert_window_call(qtbot):
    from ui.notifications.task_alert_service import TaskAlertService

    win = QWidget()
    qtbot.addWidget(win)
    service = TaskAlertService()

    with patch.object(QApplication, "alert") as mock_qapp_alert:
        service.alert_window(win)
        mock_qapp_alert.assert_called_once_with(win, 0)
