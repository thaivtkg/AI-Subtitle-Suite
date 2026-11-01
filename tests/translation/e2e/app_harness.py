from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from core.translation.controllers.project_controller import ProjectController
from core.translation.controllers.batch_controller import BatchController
from core.translation.controllers.batch_runtime_bridge import BatchRuntimeBridge
from core.translation.controllers.translation_controller import TranslationController
from core.translation.core.hardware_detector import HardwareDetector
from core.translation.core.srt_parser import SRTParser
from core.translation.models.subtitle import SubtitleModel, FilteredSubtitleModel

from .user_driver import UserDriver


QQuickStyle.setStyle("Basic")


class AppHarness:
    def __init__(self, fixture_path, worker_factory=None, use_hardware_profile=False, profile_overrides=None):
        self.app = QGuiApplication.instance() or QGuiApplication([])
        self.engine = QQmlApplicationEngine()
        self.model = SubtitleModel()
        if fixture_path is not None:
            self.model.load_data(SRTParser.parse(str(fixture_path)))

        if use_hardware_profile:
            self.translation_controller = TranslationController(self.model, worker_factory=worker_factory)
        else:
            original_profile = HardwareDetector.get_recommended_profile
            HardwareDetector.get_recommended_profile = staticmethod(lambda: {
                "gpu_info": {"name": "T15 test", "vram_gb": 0.0},
                "backend_status": "T15 test profile",
                "model_name": "missing-test-model.gguf",
                "n_ctx": 2048,
                "n_gpu_layers": 0,
            })
            try:
                self.translation_controller = TranslationController(self.model, worker_factory=worker_factory)
            finally:
                HardwareDetector.get_recommended_profile = original_profile
        if profile_overrides:
            self.translation_controller.hardware_profile.update(profile_overrides)

        self.project_controller = ProjectController(self.model)
        if fixture_path is not None:
            self.project_controller._set_project_state(True, False)
        self.translation_controller.bind_intelligence(
            glossary=self.project_controller.glossary,
            entities=self.project_controller.entity_dictionary,
            translation_memory=self.project_controller.translation_memory,
            project_controller=self.project_controller,
        )
        self.project_controller.bind_translation_controller(self.translation_controller)
        self.batch_runtime = BatchRuntimeBridge(self.translation_controller)
        self.batch_controller = BatchController(
            self.model,
            self.batch_runtime,
            project_id=str(uuid4()),
        )
        self.filtered_subtitle_model = FilteredSubtitleModel(self.model)
        self.engine.rootContext().setContextProperty("translationController", self.translation_controller)
        self.engine.rootContext().setContextProperty("projectController", self.project_controller)
        self.engine.rootContext().setContextProperty("subtitleModel", self.model)
        self.engine.rootContext().setContextProperty("filteredSubtitleModel", self.filtered_subtitle_model)
        self.engine.rootContext().setContextProperty("batchController", self.batch_controller)

        qml_file = Path(__file__).parents[3] / "ui" / "qml_translation" / "Main.qml"
        self.engine.load(QUrl.fromLocalFile(str(qml_file)))
        roots = self.engine.rootObjects()
        if not roots:
            raise RuntimeError(f"Could not load QML root: {qml_file}")
        self.window = roots[0]
        self.window.show()
        self.app.processEvents()
        self.driver = UserDriver(self.window)

    def close(self):
        worker = getattr(self.translation_controller, "worker", None)
        if worker is not None:
            if worker.isRunning():
                worker.requestInterruption()
            assert worker.wait(5000), "Worker did not stop during harness teardown"
            assert not worker.isRunning()

        if self.window is not None:
            self.window.close()
            self.window.deleteLater()

        if self.engine is not None:
            self.engine.deleteLater()

        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.window = None
        self.engine = None
        self.driver = None
        self.translation_controller = None
        self.project_controller = None
        self.batch_controller = None
        self.batch_runtime = None
        self.model = None

