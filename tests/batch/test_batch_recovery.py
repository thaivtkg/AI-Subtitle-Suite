import os
import json
import unittest
from unittest.mock import patch, MagicMock
from PySide6.QtCore import QCoreApplication, QThreadPool
import sys

from core.batch.batch_models import BatchJob, BatchSession, BatchStatus
from core.batch.batch_manager import BatchManager
from core.runtime.runtime_paths import RuntimePaths

if not QCoreApplication.instance():
    app = QCoreApplication(sys.argv)

class TestBatchRecovery(unittest.TestCase):
    def setUp(self):
        self.batch_file = RuntimePaths.get_batch_active_file()
        if os.path.exists(self.batch_file):
            os.remove(self.batch_file)

    @patch('core.batch.batch_manager.ExportService')
    @patch('core.batch.batch_manager.FasterWhisperService')
    @patch('core.batch.batch_manager.MediaImportService')
    def test_manager_saves_session_to_disk_on_status_change(self, mock_import, mock_whisper, mock_export):
        mock_whisper.return_value.run.return_value = "mock_art_1"
        mock_export.return_value.run.return_value = MagicMock()
        manager = BatchManager()
        job = BatchJob(id="job_1", input_file="test.mp4")
        session = BatchSession("s1", "tiny", "en", "srt", [job])
        
        manager.start_session(session)
        QThreadPool.globalInstance().waitForDone()
        QCoreApplication.processEvents()
        
        self.assertTrue(os.path.exists(self.batch_file))
        with open(self.batch_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        self.assertEqual(data['session_id'], "s1")
        self.assertEqual(data['jobs'][0]['status'], "COMPLETED")
        
        from core.recovery.recovery_manager import RecoveryManager
        rec_mgr = RecoveryManager(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        self.assertTrue(rec_mgr.has_active_batch_session())
        loaded_data = rec_mgr.load_active_batch_session()
        self.assertEqual(loaded_data['session_id'], "s1")

if __name__ == '__main__':
    unittest.main()
