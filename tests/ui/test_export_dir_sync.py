import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QLineEdit

from ui.Gui import MainWindow
from ui.pages.export_center_page import ExportCenterPage


class TestExportDirSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_two_way_sync_export_and_out_input(self):
        win = MainWindow.__new__(MainWindow)
        win.out_input = QLineEdit()
        win.page_export = ExportCenterPage()
        win.output_dir = ""
        win._persist_canonical_setting = MagicMock()

        # Connect signals like in init_ui
        win.page_export.out_edit.textChanged.connect(win._on_export_dir_changed)
        win.out_input.textChanged.connect(win._on_out_input_changed)

        # 1. User types in page_export.out_edit
        test_dir_1 = "D:/MyVideos/Export"
        win.page_export.out_edit.setText(test_dir_1)

        self.assertEqual(win.out_input.text(), test_dir_1)
        self.assertEqual(win.output_dir, test_dir_1)
        win._persist_canonical_setting.assert_called_with("output_dir", test_dir_1)

        # 2. User types in out_input
        test_dir_2 = "E:/Output/Subtitles"
        win.out_input.setText(test_dir_2)

        self.assertEqual(win.page_export.out_edit.text(), test_dir_2)
        self.assertEqual(win.output_dir, test_dir_2)
        win._persist_canonical_setting.assert_called_with("output_dir", test_dir_2)

    def test_apply_saved_settings_filters_stale_temp_dir(self):
        win = MainWindow.__new__(MainWindow)
        win.out_input = QLineEdit()
        win.page_export = ExportCenterPage()
        win.page_settings = MagicMock()
        win.page_settings.canonical_autosave_delay_combo.findData.return_value = 0
        win.page_settings.motion_preset_combo.findData.return_value = -1
        win.page_settings.appear_combo.findData.return_value = -1
        win.page_settings.disappear_combo.findData.return_value = -1
        win.page_settings.text_effect_combo.findData.return_value = -1
        win.canonical_save_coordinator = MagicMock()
        win.apply_motion_config_to_player = MagicMock()

        # Case A: Stale non-existent temp dir
        stale_temp = os.path.join(tempfile.gettempdir(), "non_existent_stale_temp_dir_12345")
        mock_settings_stale = {"output_dir": stale_temp}

        with patch("ui.Gui.load_settings", return_value=mock_settings_stale):
            win.apply_saved_settings()

        self.assertEqual(win.out_input.text(), "")
        self.assertEqual(win.page_export.out_edit.text(), "")
        self.assertEqual(win.output_dir, "")

        # Case B: Valid existing dir (non-temp)
        real_dir = os.path.abspath(os.path.dirname(__file__))  # this dir actually exists and is non-temp
        mock_settings_real = {"output_dir": real_dir}

        with patch("ui.Gui.load_settings", return_value=mock_settings_real):
            win.apply_saved_settings()

        self.assertEqual(win.out_input.text(), real_dir)
        self.assertEqual(win.page_export.out_edit.text(), real_dir)
        self.assertEqual(win.output_dir, real_dir)

    def test_close_event_prioritizes_page_export_out_edit(self):
        win = MainWindow.__new__(MainWindow)
        win.out_input = QLineEdit()
        win.page_export = ExportCenterPage()
        win.page_settings = MagicMock()
        win.canonical_save_coordinator = MagicMock()
        win.project_service = None
        win._flush_canonical_save_before_close = MagicMock()
        win.recovery_manager = None
        win.worker = None
        win.stdout_redirector = None
        win.stderr_redirector = None
        win.queue_mgr = MagicMock()

        # Set different paths
        win.out_input.setText("C:/Temp/OldStale")
        win.page_export.out_edit.setText("D:/Projects/ChosenExport")

        saved_dict = {}
        with patch("ui.Gui.load_settings", return_value={}), \
             patch("ui.Gui.save_settings", side_effect=lambda s: saved_dict.update(s)):
            mock_event = MagicMock()
            win.closeEvent(mock_event)

        self.assertEqual(saved_dict.get("output_dir"), "D:/Projects/ChosenExport")
