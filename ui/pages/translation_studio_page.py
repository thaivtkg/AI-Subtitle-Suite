import os
import sys
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtCore import QUrl, Signal, Slot

QQuickStyle.setStyle("Basic")
from core.translation.models.subtitle import SubtitleModel, FilteredSubtitleModel
from core.translation.controllers.translation_controller import TranslationController
from core.translation.controllers.batch_controller import BatchController
from core.translation.controllers.batch_runtime_bridge import BatchRuntimeBridge
from core.translation.controllers.model_controller import ModelController
from core.translation.controllers.project_controller import ProjectController
from core.translation.core.app_settings import AppSettings


class TranslationStudioPage(QWidget):
    """Trang Dịch thuật AI (CAT Studio) nhúng QML trong hệ thống Studio."""

    # Phát tín hiệu khi câu phụ đề được dịch hoặc duyệt để Studio cập nhật Timeline/Video
    translation_committed = Signal(int, str)  # (index_0_based, translated_text)
    batch_translations_updated = Signal(list)  # list of segments

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 1. Khởi tạo Models & Controllers lõi
        self.subtitle_model = SubtitleModel(self)
        self.filtered_model = FilteredSubtitleModel(self.subtitle_model, self)

        models_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models"))
        os.makedirs(models_dir, exist_ok=True)
        # Fallback thông minh: Nếu thư mục models của Suite chưa có file .gguf, tự động trỏ tới kho model đã tải tại E:\AI-Subtitle-Translator\models
        if not any(f.endswith(".gguf") for f in os.listdir(models_dir)):
            alt_models_dir = r"E:\AI-Subtitle-Translator\models"
            if os.path.exists(alt_models_dir) and any(f.endswith(".gguf") for f in os.listdir(alt_models_dir)):
                models_dir = alt_models_dir

        settings_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app_settings.json"))
        self.app_settings = AppSettings(file_path=settings_file)

        self.translation_controller = TranslationController(self.subtitle_model)
        self.batch_runtime = BatchRuntimeBridge(self.translation_controller, parent=self)
        self.batch_controller = BatchController(
            self.subtitle_model, self.batch_runtime, project_id="studio-session", parent=self
        )
        self.project_controller = ProjectController(
            self.subtitle_model, settings=self.app_settings, parent=self
        )

        self.translation_controller.bind_intelligence(
            glossary=self.project_controller.glossary,
            entities=self.project_controller.entity_dictionary,
            translation_memory=self.project_controller.translation_memory,
            project_controller=self.project_controller,
        )
        self.project_controller.bind_translation_controller(self.translation_controller)

        self.model_controller = ModelController(
            models_dir=models_dir,
            translation_controller=self.translation_controller,
            batch_controller=self.batch_controller,
            settings=self.app_settings,
            parent=self,
        )
        self.translation_controller._model_controller = self.model_controller

        # Kết nối sự kiện Model -> Signal Studio
        self.subtitle_model.dataChanged.connect(self._on_subtitle_data_changed)
        self.batch_controller.stateChanged.connect(self._on_batch_state_changed)

        # 2. Khởi tạo QQuickWidget với nền trong suốt / Dark Navy
        self.quick_widget = QQuickWidget(self)
        self.quick_widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        from PySide6.QtGui import QColor
        self.quick_widget.setClearColor(QColor("#0B0F19"))
        self.quick_widget.setStyleSheet("background-color: #0B0F19; border: none;")

        # 3. Đăng ký Context Properties cho QML
        ctx = self.quick_widget.engine().rootContext()
        ctx.setContextProperty("translationController", self.translation_controller)
        ctx.setContextProperty("batchController", self.batch_controller)
        ctx.setContextProperty("projectController", self.project_controller)
        ctx.setContextProperty("modelController", self.model_controller)
        ctx.setContextProperty("subtitleModel", self.subtitle_model)
        ctx.setContextProperty("filteredSubtitleModel", self.filtered_model)
        ctx.setContextProperty("translationStudioPage", self)

        # 4. Nạp QML View
        qml_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "qml_translation", "TranslationStudioView.qml"))
        self.quick_widget.engine().clearComponentCache()
        self.quick_widget.setSource(QUrl.fromLocalFile(qml_path))

        # Kiểm tra lỗi nạp QML (nếu có)
        for err in self.quick_widget.errors():
            print(f"[QML TRANSLATION ERROR] {err.toString()}")

        layout.addWidget(self.quick_widget)

    def _on_subtitle_data_changed(self, top_left, bottom_right, roles=None):
        row = top_left.row()
        item = self.subtitle_model.get_item(row)
        if item:
            trans = item.get("translation", "")
            status = str(item.get("status", "PENDING")).upper()
            # AUD-SYNC-001 (Approval-Gated Sync): Chỉ phát tín hiệu đồng bộ khi câu đã được DUYỆT (ACCEPTED)
            if trans and status == "ACCEPTED":
                studio_idx = int(item.get("studio_index", row))
                self.translation_committed.emit(studio_idx, trans)

    def _on_batch_state_changed(self):
        if self.batch_controller.state == "COMPLETED":
            self.batch_translations_updated.emit(self.subtitle_model.get_all_data())

    @Slot()
    def import_all_from_timeline(self):
        """Người dùng bấm nạp toàn bộ phụ đề từ Video Timeline sang CAT Studio."""
        win = self.parent() if hasattr(self, "parent") else None
        if win and not hasattr(win, "sub_editor") and hasattr(win, "window"):
            win = win.window()
        if win and hasattr(win, "sub_editor") and win.sub_editor:
            segments = getattr(win.sub_editor, "all_segments", [])
            self.load_subtitles_from_studio(segments, selected_indices=None)

    def load_subtitles_from_studio(self, studio_segments: list, selected_indices: list[int] | None = None):
        """Ánh xạ dữ liệu phụ đề từ SubEditor sang SubtitleModel của QML."""
        def _fmt_time(val):
            if isinstance(val, (int, float)):
                s, ms = divmod(max(0, int(val)), 1000)
                m, s = divmod(s, 60)
                h, m = divmod(m, 60)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
            return str(val) if val else "00:00:00,000"

        cat_data = []
        if selected_indices:
            target_indices = [idx for idx in selected_indices if 0 <= idx < len(studio_segments)]
        else:
            target_indices = list(range(len(studio_segments)))

        for idx in target_indices:
            s = studio_segments[idx]
            VALID_CAT_STATUSES = {"PENDING", "TRANSLATING", "TRANSLATED", "EDITED", "ACCEPTED", "ERROR"}
            trans_status = str(s.get("translation_status") or "").strip().upper()
            if trans_status in VALID_CAT_STATUSES:
                status = trans_status
            else:
                status = "TRANSLATED" if str(s.get("translation", "")).strip() else "PENDING" 
            # CAT Queue Invariant: Khi nap chu dong tu Timeline (selected_indices is None),
            # chi nap cac cau chua duyet. Bo qua cac cau da duyet (ACCEPTED).
            if selected_indices is None and str(status).upper() == "ACCEPTED":
                continue
            seg_id = str(s.get("id") or s.get("stt") or (idx + 1))
            s["id"] = seg_id
            cat_data.append({
                "segment_id": seg_id,
                "studio_index": idx,
                "index": int(s.get("stt", idx + 1)),
                "start_time": _fmt_time(s.get("start")),
                "end_time": _fmt_time(s.get("end")),
                "original": s.get("original_text") or s.get("text", ""),
                "translation": s.get("translation", ""),
                "status": status,
            })
        self.subtitle_model.load_data(cat_data)
        from core.translation.core.context_analyzer import ContextAnalyzer
        sample_text = " ".join([seg.get("original_text") or seg.get("text", "") for seg in studio_segments[:20]])
        detected = ContextAnalyzer.detect_native_language(sample_text)
        if hasattr(self.project_controller, "_source_language"):
            self.project_controller._source_language = detected
            self.project_controller.languageLoaded.emit(detected)
        if hasattr(self.project_controller, "_set_project_state"):
            self.project_controller._set_project_state(has_project=True, is_dirty=False)
        if cat_data:
            self.translation_controller.loadSubtitle(0)
        else:
            self.translation_controller.loadSubtitle(-1)

    @staticmethod
    def _format_time(val):
        if isinstance(val, (int, float)):
            s, ms = divmod(max(0, int(val)), 1000)
            m, s = divmod(s, 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        return str(val) if val else "00:00:00,000"

    def _find_cat_index(self, target_id: str) -> int:
        data = self.subtitle_model.get_all_data()
        target = str(target_id).strip()
        if not target:
            return -1

        # Tier 1: segment_id
        for idx, item in enumerate(data):
            sid = str(item.get("segment_id") or "")
            if sid and sid == target:
                return idx

        # Tier 2: STT (index)
        for idx, item in enumerate(data):
            stt = str(item.get("index") or "")
            if stt and stt == target:
                return idx

        # Tier 3: studio_index + 1
        for idx, item in enumerate(data):
            studio_idx = str(item.get("studio_index") if item.get("studio_index") is not None else "")
            if studio_idx.isdigit() and str(int(studio_idx) + 1) == target:
                return idx

        # Tier 4: studio_index
        for idx, item in enumerate(data):
            studio_idx = str(item.get("studio_index") if item.get("studio_index") is not None else "")
            if studio_idx and studio_idx == target:
                return idx

        return -1

    def update_segment_source(self, segment_id: str, new_source_text: str):
        """When a segment's audio is rescanned in Studio, update its source text and invalidate stale translation."""
        matched_idx = self._find_cat_index(segment_id)
        if matched_idx >= 0:
            data = self.subtitle_model.get_all_data()
            item = data[matched_idx]
            item["original"] = new_source_text
            item["translation"] = ""
            item["status"] = "PENDING"
            self.subtitle_model.update_translation(matched_idx, "", "PENDING", original_text=new_source_text)
            if hasattr(self.translation_controller, "is_busy") and self.translation_controller.is_busy():
                if getattr(self.translation_controller, "_active_translation_index", -1) == matched_idx:
                    self.translation_controller.cancelTranslation()
            if matched_idx == getattr(self.translation_controller, "_current_index", -1):
                self.translation_controller.loadSubtitle(matched_idx)

    def handle_segment_split(self, original_id: str, seg1: dict, seg2: dict):
        """Đồng bộ thời gian thực khi 1 câu trên Video Workspace bị cắt làm đôi."""
        matched_idx = self._find_cat_index(original_id)
        if matched_idx < 0:
            return

        if hasattr(self.translation_controller, "is_busy") and self.translation_controller.is_busy():
            if getattr(self.translation_controller, "_active_translation_index", -1) == matched_idx:
                self.translation_controller.cancelTranslation()

        seg1_data = {
            "segment_id": str(seg1.get("id") or original_id),
            "studio_index": matched_idx,
            "index": int(seg1.get("stt", matched_idx + 1)),
            "start_time": self._format_time(seg1.get("start")),
            "end_time": self._format_time(seg1.get("end")),
            "original": seg1.get("original_text") or seg1.get("text", ""),
            "translation": "",
            "status": "PENDING",
        }
        seg2_data = {
            "segment_id": str(seg2.get("id") or (matched_idx + 2)),
            "studio_index": matched_idx + 1,
            "index": int(seg2.get("stt", matched_idx + 2)),
            "start_time": self._format_time(seg2.get("start")),
            "end_time": self._format_time(seg2.get("end")),
            "original": seg2.get("original_text") or seg2.get("text", ""),
            "translation": "",
            "status": "PENDING",
        }
        self.subtitle_model.split_subtitle(matched_idx, seg1_data, seg2_data)

        if getattr(self.translation_controller, "_current_index", -1) == matched_idx:
            self.translation_controller.loadSubtitle(matched_idx)

    def handle_segment_split_undo(self, original_id: str, new_seg_id: str, original_seg: dict):
        """Hoàn tác cắt câu: xóa câu con thứ 2 và phục hồi câu mẹ nguyên bản."""
        matched_idx = self._find_cat_index(original_id)
        if matched_idx < 0:
            return

        if hasattr(self.translation_controller, "is_busy") and self.translation_controller.is_busy():
            if getattr(self.translation_controller, "_active_translation_index", -1) in (matched_idx, matched_idx + 1):
                self.translation_controller.cancelTranslation()

        orig_data = {
            "segment_id": str(original_seg.get("id") or original_id),
            "studio_index": matched_idx,
            "index": int(original_seg.get("stt", matched_idx + 1)),
            "start_time": self._format_time(original_seg.get("start")),
            "end_time": self._format_time(original_seg.get("end")),
            "original": original_seg.get("original_text") or original_seg.get("text", ""),
            "translation": original_seg.get("translation", ""),
            "status": original_seg.get("translation_status", "TRANSLATED" if original_seg.get("translation") else "PENDING"),
        }
        self.subtitle_model.undo_split_subtitle(matched_idx, orig_data)

        if getattr(self.translation_controller, "_current_index", -1) in (matched_idx, matched_idx + 1):
            self.translation_controller.loadSubtitle(matched_idx)

    def handle_segments_merged(self, id1: str, id2: str, merged_seg: dict):
        """Đồng bộ thời gian thực khi 2 câu trên Video Workspace được gộp thành 1."""
        matched_idx = self._find_cat_index(id1)
        if matched_idx < 0 or matched_idx >= self.subtitle_model.rowCount() - 1:
            return

        if hasattr(self.translation_controller, "is_busy") and self.translation_controller.is_busy():
            if getattr(self.translation_controller, "_active_translation_index", -1) in (matched_idx, matched_idx + 1):
                self.translation_controller.cancelTranslation()

        trans = merged_seg.get("translation", "")
        merged_data = {
            "segment_id": str(merged_seg.get("id") or id1),
            "studio_index": matched_idx,
            "index": int(merged_seg.get("stt", matched_idx + 1)),
            "start_time": self._format_time(merged_seg.get("start")),
            "end_time": self._format_time(merged_seg.get("end")),
            "original": merged_seg.get("original_text") or merged_seg.get("text", ""),
            "translation": trans,
            "status": merged_seg.get("translation_status", "EDITED" if trans else "PENDING"),
        }
        self.subtitle_model.merge_subtitles(matched_idx, merged_data)

        if getattr(self.translation_controller, "_current_index", -1) in (matched_idx, matched_idx + 1):
            self.translation_controller.loadSubtitle(matched_idx)

    def handle_segments_merge_undo(self, id1: str, seg1: dict, seg2: dict):
        """Hoàn tác gộp câu: tái lập lại 2 câu riêng rẽ ban đầu."""
        matched_idx = self._find_cat_index(id1)
        if matched_idx < 0:
            return

        if hasattr(self.translation_controller, "is_busy") and self.translation_controller.is_busy():
            if getattr(self.translation_controller, "_active_translation_index", -1) == matched_idx:
                self.translation_controller.cancelTranslation()

        t1 = seg1.get("translation", "")
        t2 = seg2.get("translation", "")
        seg1_data = {
            "segment_id": str(seg1.get("id") or id1),
            "studio_index": matched_idx,
            "index": int(seg1.get("stt", matched_idx + 1)),
            "start_time": self._format_time(seg1.get("start")),
            "end_time": self._format_time(seg1.get("end")),
            "original": seg1.get("original_text") or seg1.get("text", ""),
            "translation": t1,
            "status": seg1.get("translation_status", "TRANSLATED" if t1 else "PENDING"),
        }
        seg2_data = {
            "segment_id": str(seg2.get("id") or (matched_idx + 2)),
            "studio_index": matched_idx + 1,
            "index": int(seg2.get("stt", matched_idx + 2)),
            "start_time": self._format_time(seg2.get("start")),
            "end_time": self._format_time(seg2.get("end")),
            "original": seg2.get("original_text") or seg2.get("text", ""),
            "translation": t2,
            "status": seg2.get("translation_status", "TRANSLATED" if t2 else "PENDING"),
        }
        self.subtitle_model.undo_merge_subtitles(matched_idx, seg1_data, seg2_data)

        if getattr(self.translation_controller, "_current_index", -1) == matched_idx:
            self.translation_controller.loadSubtitle(matched_idx)

    def export_subtitles_to_studio(self, studio_segments: list):
        """Cập nhật bản dịch từ SubtitleModel ngược lại danh sách phụ đề của Studio."""
        cat_data = self.subtitle_model.get_all_data()
        id_map = {}
        for idx, seg in enumerate(studio_segments):
            sid = str(seg.get("id") or seg.get("stt") or (idx + 1))
            id_map[sid] = idx
        
        for i, item in enumerate(cat_data):
            seg_id = str(item.get("segment_id") or "")
            stt = str(item.get("index") or "")
            studio_idx = id_map.get(seg_id)
            if studio_idx is None:
                studio_idx = id_map.get(stt)
            if studio_idx is None:
                studio_idx = int(item.get("studio_index", i))
                
            if 0 <= studio_idx < len(studio_segments):
                timeline_seg = studio_segments[studio_idx]
                timeline_orig = timeline_seg.get("original_text")
                cat_orig = str(item.get("original", "")).strip()
                trans = str(item.get("translation", "")).strip()
                
                # Overwrite Guard: If timeline segment has a new speech and its original_text
                # doesn't match cat_orig, do not overwrite with old translation!
                if timeline_orig and cat_orig and timeline_orig != cat_orig:
                    continue
                    
                if trans:
                    if not timeline_seg.get("original_text"):
                        timeline_seg["original_text"] = cat_orig or timeline_seg.get("text", "")
                    timeline_seg["translation"] = trans
                    timeline_seg["translation_status"] = item.get("status", "TRANSLATED")
                    # AUD-SYNC-001 (Approval-Gated Sync): Chỉ ghi đè text câu trên Timeline/Player khi câu đã DUYỆT (ACCEPTED)
                    if item.get("status") == "ACCEPTED":
                        timeline_seg["text"] = trans
            else:
                trans = str(item.get("translation", "")).strip()
                studio_segments.append({
                    "stt": item.get("index", len(studio_segments) + 1),
                    "start": item.get("start_time", "00:00:00,000"),
                    "end": item.get("end_time", "00:00:00,000"),
                    "text": trans or item.get("original", ""),
                    "original_text": item.get("original", ""),
                    "translation": trans,
                    "translation_status": item.get("status", "TRANSLATED" if trans else "PENDING"),
                })

    def save_translation_project(self, file_path: str):
        """Lưu toàn bộ dữ liệu dịch và bảng thuật ngữ thành tệp .aisrt chuẩn JSON."""
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        self.project_controller.saveProject(
            file_url=file_path,
            story_summary=getattr(self.project_controller, "_story_summary", ""),
            source_lang="English",
            target_lang="Vietnamese",
            notify=False,
        )

    def load_translation_project(self, file_path: str):
        """Nạp tệp .aisrt bảo toàn 100% Glossary, TM và tiến độ dịch."""
        if os.path.exists(file_path):
            self.project_controller.loadProject(file_path)
