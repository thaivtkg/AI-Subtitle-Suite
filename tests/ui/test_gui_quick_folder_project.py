# -*- coding: utf-8 -*-
import os
import shutil
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from PySide6.QtCore import QUrl, QMimeData
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication

from ui.Gui import MainWindow
from ui.dialogs.quick_folder_project_dialog import QuickFolderProjectDialog


@pytest.fixture
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


@pytest.fixture
def folder_env():
    root = tempfile.mkdtemp(prefix="test_gui_quick_folder_")
    vids = []
    for name in ["scene_01.mp4", "scene_02.mp4", "scene_03.mkv"]:
        vpath = os.path.join(root, name)
        with open(vpath, "wb") as f:
            f.write(b"SAMPLE_VIDEO_CONTENT_" + name.encode() * 100)
        vids.append(vpath)

    yield {"root": root, "videos": vids}
    shutil.rmtree(root, ignore_errors=True)


def test_menu_action_exists(app):
    win = MainWindow()
    assert hasattr(win, "action_quick_folder_project")
    assert "Tạo Dự Án Từ Thư Mục" in win.action_quick_folder_project.text()


def test_action_quick_folder_project_single_video(app, folder_env):
    root = folder_env["root"]
    v1 = folder_env["videos"][0]

    win = MainWindow()

    with patch.object(QuickFolderProjectDialog, "exec", return_value=1):
        with patch.object(
            QuickFolderProjectDialog,
            "selected_video_paths",
            new_callable=lambda: property(lambda self: [v1]),
        ):
            win._action_quick_folder_project(folder_path=root)

    # 1. Project bundle must exist adjacent to video
    expected_bundle = win.project_service.get_canonical_bundle_dir(v1)
    assert os.path.isdir(expected_bundle)
    assert os.path.exists(os.path.join(expected_bundle, "project.json"))

    # 2. Workspace must be open with this project active
    assert win.project_service.current_project is not None
    assert os.path.normpath(win.project_service.project_dir) == os.path.normpath(expected_bundle)

    # 3. Queue Manager & mappings must be updated
    assert v1 in win.queue_mgr.get_items()
    assert win._queue_project_dirs.get(v1) == expected_bundle


def test_action_quick_folder_project_multi_videos(app, folder_env):
    root = folder_env["root"]
    all_vids = folder_env["videos"]
    v1, v2, v3 = all_vids

    win = MainWindow()

    with patch.object(QuickFolderProjectDialog, "exec", return_value=1):
        with patch.object(
            QuickFolderProjectDialog,
            "selected_video_paths",
            new_callable=lambda: property(lambda self: all_vids),
        ):
            win._action_quick_folder_project(folder_path=root)

    # All 3 bundles must exist
    for v in all_vids:
        b_dir = win.project_service.get_canonical_bundle_dir(v)
        assert os.path.isdir(b_dir), f"Bundle directory not found for {v}"
        assert os.path.exists(os.path.join(b_dir, "project.json"))
        assert v in win.queue_mgr.get_items()
        assert win._queue_project_dirs.get(v) == b_dir

    # First video must be the active workspace project
    b1_dir = win.project_service.get_canonical_bundle_dir(v1)
    assert win.project_service.current_project is not None
    assert os.path.normpath(win.project_service.project_dir) == os.path.normpath(b1_dir)


def test_drop_event_folder_directory(app, folder_env):
    root = folder_env["root"]
    win = MainWindow()

    mime_data = QMimeData()
    mime_data.setUrls([QUrl.fromLocalFile(root)])
    mock_event = MagicMock()
    mock_event.mimeData.return_value = mime_data

    with patch.object(win, "_action_quick_folder_project") as mock_action:
        win.dropEvent(mock_event)
        mock_action.assert_called_once_with(folder_path=os.path.normpath(root))
