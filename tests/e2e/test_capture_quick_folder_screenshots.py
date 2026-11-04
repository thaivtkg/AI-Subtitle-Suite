# -*- coding: utf-8 -*-
"""
Chụp ảnh giao diện thực tế của tính năng Tạo Dự Án Từ Thư Mục (DEV-SPEC-FOLDER-PROJECT-001 & 002)
với dữ liệu video thực tế trong thư mục D:\\Video.
Lưu ảnh vào thư mục artifact để trình chiếu cho người dùng.
"""
import os
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest

from ui.dialogs.quick_folder_project_dialog import QuickFolderProjectDialog

CURRENT_CONV_ARTIFACT = r"C:\Users\Kuroberus\.gemini\antigravity\brain\d7d2d74d-59ec-4d54-8751-7d91438bdf1d"
LEGACY_ARTIFACT = r"C:\Users\Kuroberus\.gemini\antigravity\brain\bc09a4cd-ebe2-4025-ac00-5b4d8c23e82d"


def _save_both(img_or_widget, filename):
    for art_dir in [CURRENT_CONV_ARTIFACT, LEGACY_ARTIFACT]:
        os.makedirs(art_dir, exist_ok=True)
        out_path = os.path.join(art_dir, filename)
        if hasattr(img_or_widget, "save"):
            img_or_widget.save(out_path)
        else:
            img_or_widget.grab().save(out_path)


def test_capture_folder_project_ui(live_studio_app):
    win, watcher, runner = live_studio_app
    win.resize(1366, 768)
    QTest.qWait(300)

    video_folder = r"D:\Video"

    # 1. Chụp ảnh Project Menu có mục "📁  Tạo Dự Án Từ Thư Mục..."
    if hasattr(win, "btn_project_menu") and win.btn_project_menu.menu():
        menu = win.btn_project_menu.menu()
        menu.adjustSize()
        menu.show()
        QTest.qWait(300)

        path_menu = os.path.join(CURRENT_CONV_ARTIFACT, "ui_01_project_menu.png")
        menu.grab().save(path_menu)

        win_img_path = os.path.join(CURRENT_CONV_ARTIFACT, "ui_01_project_menu_full.png")
        win.grab().save(win_img_path)
        try:
            from PIL import Image
            base = Image.open(win_img_path)
            menu_img = Image.open(path_menu)
            pt = win.btn_project_menu.mapTo(win, QPoint(0, win.btn_project_menu.height()))
            base.paste(menu_img, (pt.x(), pt.y()))
            base.save(win_img_path)
            # also save to legacy
            os.makedirs(LEGACY_ARTIFACT, exist_ok=True)
            base.save(os.path.join(LEGACY_ARTIFACT, "ui_01_project_menu_full.png"))
        except Exception as e:
            print(f"Composite warning: {e}")
        
        menu.close()
        QTest.qWait(100)

    # 2. Chụp ảnh QuickFolderProjectDialog với toàn bộ video thực tế từ D:\Video (Mặc định uncheck & unified bottom bar)
    dialog = QuickFolderProjectDialog(folder_path=video_folder, project_service=win.project_service)
    dialog.resize(960, 600)
    dialog.show()
    QTest.qWait(500)

    _save_both(dialog, "ui_02_quick_folder_dialog_all.png")

    # 2b. Chụp ảnh sau khi bấm "Chọn tất cả"
    dialog.btn_select_all.click()
    QTest.qWait(300)
    _save_both(dialog, "ui_02b_quick_folder_dialog_selected.png")

    # 3. Chụp ảnh QuickFolderProjectDialog khi tìm kiếm theo từ khóa 'wmv'
    dialog.search_input.setText("wmv")
    QTest.qWait(400)
    _save_both(dialog, "ui_03_quick_folder_dialog_search.png")

    dialog.search_input.clear()
    dialog.close()
    dialog.deleteLater()
    QTest.qWait(200)

    # 4. Mở 1 video từ D:\Video vào Workspace và chụp ảnh màn hình chính
    test_video = os.path.join(video_folder, "GGTB04.wmv")
    if os.path.exists(test_video):
        b_dir = win.project_service.get_canonical_bundle_dir(test_video)
        proj, _ = win.project_service.create_or_get_folder_project(test_video)
        win.queue_mgr.add_video(test_video)
        win._queue_project_dirs[test_video] = b_dir
        win._open_project_by_path(b_dir)
        win.switch_page(1)
        QTest.qWait(600)

        _save_both(win, "ui_04_workspace_loaded.png")
