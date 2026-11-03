# -*- coding: utf-8 -*-
import os
import pytest
from PySide6.QtWidgets import QApplication, QDialog
from unittest.mock import patch

from ui.dialogs.missing_media_dialog import MissingMediaDialog


@pytest.fixture
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def test_missing_media_dialog_init(app):
    dialog = MissingMediaDialog(
        project_name="Anime_Ep01",
        missing_path="D:/Old/video.mp4",
        suggested_path=None
    )
    assert dialog.project_name == "Anime_Ep01"
    assert dialog.missing_path == "D:/Old/video.mp4"
    assert dialog.suggested_path is None
    assert dialog.result_action == "CANCEL"
    assert dialog.selected_video_path is None
    # Suggested button should not be visible when suggested_path is None
    assert not hasattr(dialog, "btn_use_suggested") or not dialog.btn_use_suggested.isVisible()


def test_missing_media_dialog_with_suggested_path(app):
    dialog = MissingMediaDialog(
        project_name="Anime_Ep01",
        missing_path="D:/Old/video.mp4",
        suggested_path="D:/New/video.mp4"
    )
    dialog.show()
    assert dialog.suggested_path == "D:/New/video.mp4"
    assert hasattr(dialog, "btn_use_suggested")
    assert dialog.btn_use_suggested.isVisible()

    # Click use suggested
    dialog.btn_use_suggested.click()
    assert dialog.result_action == "RELINK"
    assert dialog.selected_video_path == "D:/New/video.mp4"
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_missing_media_dialog_open_without_video(app):
    dialog = MissingMediaDialog(
        project_name="Anime_Ep01",
        missing_path="D:/Old/video.mp4"
    )
    dialog.btn_open_no_video.click()
    assert dialog.result_action == "OPEN_WITHOUT_VIDEO"
    assert dialog.selected_video_path is None
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_missing_media_dialog_cancel(app):
    dialog = MissingMediaDialog(
        project_name="Anime_Ep01",
        missing_path="D:/Old/video.mp4"
    )
    dialog.btn_cancel.click()
    assert dialog.result_action == "CANCEL"
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_missing_media_dialog_browse_relink(app):
    dialog = MissingMediaDialog(
        project_name="Anime_Ep01",
        missing_path="D:/Old/video.mp4"
    )
    with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=("D:/Selected/video.mp4", "Video Files")):
        dialog.btn_browse.click()

    assert dialog.result_action == "RELINK"
    assert dialog.selected_video_path == os.path.normpath("D:/Selected/video.mp4")
    assert dialog.result() == QDialog.DialogCode.Accepted
