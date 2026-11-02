import re
import os
import json
import time
from typing import Optional, Any
from uuid import uuid4
from PySide6.QtCore import QObject, Slot, Signal, Property, QUrl
from core.translation.core.srt_exporter import SRTExporter
from core.translation.core.srt_parser import SRTParser
from core.translation.core.srt_validator import SRTValidator
from core.translation.core.glossary import Glossary
from core.translation.core.entity_dictionary import EntityDictionary
from core.translation.core.translation_memory import TranslationMemory
from core.translation.core.app_settings import AppSettings
from core.translation.core.context_analyzer import (
    ARCHETYPE_CUSTOM,
    ARCHETYPE_ANIME_SCHOOL,
    ARCHETYPE_PURE,
    DEFAULT_PRONOUNS,
    ARCHETYPE_METADATA,
    ContextAnalyzer,
)

def _normalize_file_path(url_or_path: str) -> str:
    if not url_or_path:
        return ""
    if url_or_path.startswith("file:"):
        local = QUrl(url_or_path).toLocalFile()
        return local if local else url_or_path
    return url_or_path

class ProjectController(QObject):
    notify = Signal(str, str)
    projectStateChanged = Signal()
    # Tín hiệu để gửi Story Summary từ file JSON ngược lên giao diện QML
    projectLoaded = Signal(str) 
    # TÍN HIỆU MỚI: Bắn ngôn ngữ nguồn lên UI
    languageLoaded = Signal(str)
    # Tín hiệu xác nhận xuất file khi tồn tại lỗi QA nghiêm trọng
    qaExportWarningRequired = Signal(str, int)
    recentFilesChanged = Signal()
    archetypeChanged = Signal()
    glossaryChanged = Signal()
    batchDetected = Signal(int, int)
    batchAppended = Signal(int)

    def __init__(
        self,
        subtitle_model: Optional[Any] = None,
        settings: Optional[AppSettings] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._subtitle_model = subtitle_model
        self._original_source_file = "unknown.srt"
        self._original_source_path = ""
        self._primary_source_path = ""
        self._batch_slices = []
        self._source_language = "English"
        self._target_language = "Vietnamese"
        self._is_batch_mode = False
        self._batch_start_num = 0
        self._batch_end_num = 0
        self._has_project = False
        self._is_dirty = False
        self._loading_project = False
        self.glossary = Glossary()
        self.entity_dictionary = EntityDictionary()
        self.translation_memory = TranslationMemory()
        self._settings = settings or AppSettings()
        self._active_archetype = ARCHETYPE_PURE
        self._active_pronoun_pair = ""
        self._is_archetype_locked = False
        self.dismissed_auto_terms = set()
        self._is_ja_origin = False
        self._story_summary = ""
        self._translation_controller = None
        if self._subtitle_model is not None:
            self._subtitle_model.dataChanged.connect(self._on_model_changed)
            self._subtitle_model.modelReset.connect(self.projectStateChanged.emit)
            self._subtitle_model.rowsInserted.connect(lambda *args: self.projectStateChanged.emit())
            self._subtitle_model.rowsRemoved.connect(lambda *args: self.projectStateChanged.emit())

    @Property(bool, notify=projectStateChanged)
    def hasProject(self):
        return self._has_project or (self._subtitle_model is not None and self._subtitle_model.rowCount() > 0)

    @Property(bool, notify=projectStateChanged)
    def isDirty(self):
        return self._is_dirty

    @Property(str, notify=archetypeChanged)
    def activeArchetype(self):
        return self._active_archetype

    @Property(str, notify=archetypeChanged)
    def activePronounPair(self):
        return self._active_pronoun_pair

    @Property(bool, notify=archetypeChanged)
    def isArchetypeLocked(self):
        return self._is_archetype_locked

    @Property(bool, notify=archetypeChanged)
    def isJaOrigin(self) -> bool:
        return getattr(self, "_is_ja_origin", False)

    @Property(str, notify=archetypeChanged)
    def storySummary(self) -> str:
        return getattr(self, "_story_summary", "")

    @Property("QVariantList", notify=recentFilesChanged)
    def recentFiles(self) -> list:
        results = []
        for p in self._settings.recent_files:
            if os.path.exists(p):
                ext = os.path.splitext(p)[1].lower()
                is_proj = ext in (".aisrt", ".ai-subtitle")
                results.append({
                    "path": p,
                    "name": os.path.basename(p),
                    "is_project": is_proj,
                })
        return results

    def _add_recent_file(self, file_path: str):
        if file_path and os.path.exists(file_path):
            self._settings.add_recent_file(file_path)
            self.recentFilesChanged.emit()

    @Slot(str)
    def openRecentFile(self, file_path: str):
        clean_path = _normalize_file_path(file_path)
        if not clean_path or not os.path.exists(clean_path):
            self.notify.emit("ERROR", f"Tệp không tồn tại: {file_path}")
            return
        ext = os.path.splitext(clean_path)[1].lower()
        if ext in (".aisrt", ".ai-subtitle"):
            self.loadProject(clean_path)
        else:
            self.importSrt(clean_path)

    @Property(str, notify=projectStateChanged)
    def originalSourcePath(self) -> str:
        return self._original_source_path

    @Property(bool, notify=batchDetected)
    def isBatchMode(self) -> bool:
        return self._is_batch_mode

    @Property(int, notify=batchDetected)
    def batchStartNum(self) -> int:
        return self._batch_start_num

    @Property(int, notify=batchDetected)
    def batchEndNum(self) -> int:
        return self._batch_end_num

    @Property(str, notify=batchDetected)
    def batchLabel(self) -> str:
        if self._is_batch_mode:
            return f"Đợt #{self._batch_start_num} ➔ #{self._batch_end_num}"
        return ""

    @Property(str, notify=archetypeChanged)
    def archetypeDisplayLabel(self):
        meta = ARCHETYPE_METADATA.get(self._active_archetype)
        if meta:
            return meta.get("name", self._active_archetype)
        return self._active_archetype

    @Property("QVariantList", notify=archetypeChanged)
    def archetypeList(self):
        return list(ARCHETYPE_METADATA.values())

    @Property("QVariantList", notify=glossaryChanged)
    def glossaryTerms(self):
        return [
            {
                "source_term": e.source_term,
                "preferred_translation": e.preferred_translation,
                "forbidden_alternatives": list(e.forbidden_alternatives),
                "is_auto": getattr(e, "is_auto", False),
            }
            for e in self.glossary._entries.values()
        ]

    def _set_project_state(self, has_project, is_dirty):
        if self._has_project == has_project and self._is_dirty == is_dirty:
            return
        self._has_project = has_project
        self._is_dirty = is_dirty
        self.projectStateChanged.emit()

    def _on_model_changed(self, *args):
        self.markDirty()

    @Slot()
    def markDirty(self):
        if self._loading_project or not self._has_project:
            return
        self._set_project_state(True, True)

    @Slot(str)
    def analyzeSummary(self, summary_text: str):
        summary_clean = (summary_text or "").strip()
        old_summary = getattr(self, "_story_summary", "")
        self._story_summary = summary_clean
        terms_changed = False
        if summary_clean:
            extracted = ContextAnalyzer.extract_entities(summary_clean)
            for item in extracted:
                src = item.get("source_term") or item.get("source", "")
                target = item.get("preferred_translation") or item.get("target", src)
                if not src:
                    continue
                if src in self.dismissed_auto_terms:
                    continue
                if self.glossary.get(src) is None:
                    self.glossary.add(src, target, (), is_auto=True)
                    terms_changed = True

        sample_subs = ""
        if self._subtitle_model is not None and hasattr(self._subtitle_model, "get_all_data"):
            all_subs = self._subtitle_model.get_all_data()[:30]
            sample_subs = " ".join([
                sub.get("original", "") if isinstance(sub, dict) else getattr(sub, "original", "")
                for sub in all_subs
            ])

        detected_lang = ContextAnalyzer.detect_native_language(sample_subs)
        ja_detection = ContextAnalyzer.detect_ja_translated_en(sample_subs, summary_clean)
        old_is_ja = self._is_ja_origin
        self._is_ja_origin = (detected_lang == "Japanese") or ja_detection.get("is_ja_origin", False)

        archetype_changed = old_summary != summary_clean
        if not self._is_archetype_locked:
            if summary_clean:
                target_archetype, target_pronouns = ContextAnalyzer.classify_archetype(summary_clean)
            else:
                target_archetype = self._active_archetype
                target_pronouns = self._active_pronoun_pair

            if (
                target_archetype != self._active_archetype
                or target_pronouns != self._active_pronoun_pair
            ):
                self._active_archetype = target_archetype
                self._active_pronoun_pair = target_pronouns
                archetype_changed = True

        if old_is_ja != self._is_ja_origin:
            archetype_changed = True

        if terms_changed:
            self.glossaryChanged.emit()
            self.markDirty()
        if archetype_changed:
            self.archetypeChanged.emit()
            self.markDirty()

    @Slot(str)
    @Slot(str, bool)
    def selectArchetype(self, archetype_id: str, manual_lock: bool = True):
        self._active_archetype = ARCHETYPE_PURE
        self._active_pronoun_pair = ""
        self._is_archetype_locked = manual_lock
        self.archetypeChanged.emit()
        self.markDirty()

    @Slot(bool)
    def setIsJaOrigin(self, value: bool) -> None:
        """Cho phép người dùng chủ động đánh dấu hoặc bỏ đánh dấu phụ đề dịch từ tiếng Nhật."""
        if self._is_ja_origin != value:
            self._is_ja_origin = value
            self.archetypeChanged.emit()
            self.markDirty()

    @Slot(str, result=bool)
    def removeGlossaryTerm(self, source_term: str) -> bool:
        """Xóa hoặc bỏ ghim một thuật ngữ khỏi Glossary (cả AI lẫn thủ công)."""
        src = (source_term or "").strip()
        if not src:
            return False
        entry = self.glossary.get(src)
        if entry is not None:
            if getattr(entry, "is_auto", False):
                self.dismissed_auto_terms.add(src)
            self.glossary.remove(src)
            self.glossaryChanged.emit()
            self.markDirty()
            self.notify.emit("SUCCESS", f"Đã bỏ ghim thuật ngữ: '{src}'")
            return True
        return False

    @Slot(str)
    def dismissAutoTerm(self, source_term: str):
        self.removeGlossaryTerm(source_term)

    @Slot(str, str, str, result=bool)
    @Slot(str, str, result=bool)
    def addManualGlossaryTerm(self, source_term: str, preferred_translation: str, forbidden_str: str = "") -> bool:
        src = (source_term or "").strip()
        target = (preferred_translation or "").strip()
        if not src or not target:
            self.notify.emit("ERROR", "Thuật ngữ gốc và bản dịch không được để trống!")
            return False

        forbidden = tuple(f.strip() for f in (forbidden_str or "").split(",") if f.strip())
        self.dismissed_auto_terms.discard(src)
        if self.glossary.get(src) is not None:
            self.glossary.update(src, target, forbidden, is_auto=False)
        else:
            self.glossary.add(src, target, forbidden, is_auto=False)
        self.glossaryChanged.emit()
        self.markDirty()
        self.notify.emit("SUCCESS", f"Đã ghim thuật ngữ: '{src}' ➔ '{target}'")
        return True

    @Slot(str, str, bool, bool, bool, result="QVariantMap")
    @Slot(str, str, bool, bool, result="QVariantMap")
    @Slot(str, str, bool, result="QVariantMap")
    @Slot(str, str, result="QVariantMap")
    @Slot(str, result="QVariantMap")
    def previewFindReplace(
        self,
        find_text: str,
        scope: str = "ALL",
        match_case: bool = False,
        whole_word: bool = False,
        is_regex: bool = False,
    ) -> dict:
        if not find_text or not self._subtitle_model:
            return {"total_matches": 0, "affected_rows": []}

        try:
            pattern = find_text if is_regex else re.escape(find_text)
            if whole_word:
                pattern = rf"\b{pattern}\b"
            flags = 0 if match_case else re.IGNORECASE
            regex = re.compile(pattern, flags)
        except Exception:
            return {"total_matches": 0, "affected_rows": [], "error": "Invalid regex pattern"}

        total_matches = 0
        affected_rows = []
        subtitles = self._subtitle_model.get_all_data()

        for idx, sub in enumerate(subtitles):
            row_matches = 0
            if scope in ("ORIGINAL", "ALL"):
                orig = sub.get("original", "")
                row_matches += len(regex.findall(orig))
            if scope in ("TRANSLATION", "ALL"):
                trans = sub.get("translation", "")
                row_matches += len(regex.findall(trans))

            if row_matches > 0:
                total_matches += row_matches
                affected_rows.append(idx)

        return {"total_matches": total_matches, "affected_rows": affected_rows}

    @Slot(str, str, str, bool, bool, bool, bool, result=int)
    @Slot(str, str, str, bool, bool, bool, result=int)
    @Slot(str, str, str, bool, bool, result=int)
    @Slot(str, str, str, bool, result=int)
    @Slot(str, str, str, result=int)
    @Slot(str, str, result=int)
    def executeFindReplace(
        self,
        find_text: str,
        replace_text: str,
        scope: str = "ALL",
        match_case: bool = False,
        whole_word: bool = False,
        is_regex: bool = False,
        add_to_glossary: bool = False,
    ) -> int:
        if not find_text or not self._subtitle_model:
            return 0

        try:
            pattern = find_text if is_regex else re.escape(find_text)
            if whole_word:
                pattern = rf"\b{pattern}\b"
            flags = 0 if match_case else re.IGNORECASE
            regex = re.compile(pattern, flags)
        except Exception as e:
            self.notify.emit("ERROR", f"Lỗi biểu thức tìm kiếm: {e}")
            return 0

        subtitles = self._subtitle_model.get_all_data()
        total_replacements = 0
        affected_count = 0

        for idx, sub in enumerate(subtitles):
            updated = False
            curr_orig = sub.get("original", "")
            curr_trans = sub.get("translation", "")
            orig_replaces = 0
            trans_replaces = 0

            if scope in ("ORIGINAL", "ALL") and curr_orig:
                new_orig, orig_replaces = regex.subn(replace_text, curr_orig)
                if orig_replaces > 0:
                    sub["original"] = new_orig
                    total_replacements += orig_replaces
                    updated = True

            if scope in ("TRANSLATION", "ALL") and curr_trans:
                new_trans, trans_replaces = regex.subn(replace_text, curr_trans)
                if trans_replaces > 0:
                    sub["translation"] = new_trans
                    total_replacements += trans_replaces
                    updated = True

            if updated:
                affected_count += 1
                curr_status = str(sub.get("status", "PENDING")).upper()
                new_status = "EDITED" if curr_status not in ("ACCEPTED",) else curr_status
                self._subtitle_model.update_translation(idx, sub.get("translation", ""), new_status)
                if orig_replaces > 0:
                    q_idx = self._subtitle_model.index(idx, 0)
                    self._subtitle_model.dataChanged.emit(q_idx, q_idx, [self._subtitle_model.OriginalRole])

        if add_to_glossary and find_text.strip() and replace_text.strip():
            self.addManualGlossaryTerm(find_text.strip(), replace_text.strip())

        if total_replacements > 0:
            self.markDirty()
            self.notify.emit("SUCCESS", f"Đã thay thế {total_replacements} vị trí trên {affected_count} câu.")

        return total_replacements

    def bind_translation_controller(self, translation_controller):
        self._translation_controller = translation_controller

    @property
    def translation_controller(self):
        return self._translation_controller

    @Slot(result=bool)
    def closeProject(self):
        """Đóng dự án hiện tại, giải phóng dữ liệu phụ đề và quay về màn hình khởi động (StudioLaunchpad)."""
        if hasattr(self, "_translation_controller") and self._translation_controller:
            try:
                self._translation_controller.shutdown()
            except Exception:
                pass
        if self._subtitle_model:
            self._subtitle_model.load_data([])
        self._primary_source_path = ""
        self._batch_slices = []
        self._original_source_path = ""
        self._original_source_file = "unknown.srt"
        self._story_summary = ""
        self._is_ja_origin = False
        self._is_archetype_locked = False
        self._active_archetype = ARCHETYPE_CUSTOM
        self._active_pronoun_pair = DEFAULT_PRONOUNS[ARCHETYPE_CUSTOM]
        self.dismissed_auto_terms.clear()
        if hasattr(self.glossary, "_entries"):
            self.glossary._entries.clear()
        if hasattr(self.entity_dictionary, "_entities"):
            self.entity_dictionary._entities.clear()
        if hasattr(self.translation_memory, "_entries"):
            self.translation_memory._entries.clear()
        self._set_project_state(False, False)
        self.projectLoaded.emit("")
        self.languageLoaded.emit("English")
        self.archetypeChanged.emit()
        self.glossaryChanged.emit()
        self.notify.emit("INFO", "Đã đóng dự án và trở về màn hình khởi động.")

    @Slot(result=bool)
    def validateBeforeExport(self):
        """Hàm này sẽ được QML gọi ĐẦU TIÊN khi bấm nút Xuất SRT"""
        subtitles = self._subtitle_model.get_all_data()
        is_valid, val_msg = SRTValidator.validate_for_export(subtitles)
        if not is_valid:
            self.notify.emit("ERROR", f"Lỗi Validator: {val_msg}")
            return False
        return True
    
    @Slot(str)
    @Slot(str, bool)
    def exportSrt(self, file_path, force=False):
        """DEFENSE-IN-DEPTH: Bắt buộc validate bên trong backend trước khi ghi file"""
        file_path = _normalize_file_path(file_path)

        subtitles = self._subtitle_model.get_all_data()
        
        # KIỂM TRA TÍNH TOÀN VỆN NGAY TẠI LÕI
        is_valid, val_msg = SRTValidator.validate_for_export(subtitles)
        if not is_valid:
            self.notify.emit("ERROR", f"Lỗi xuất file: {val_msg}")
            return
            
        # ADVISORY QA CHECK: Nếu có lỗi đỏ và người dùng chưa bấm Force, yêu cầu xác nhận
        if not force:
            error_count = sum(1 for sub in subtitles if sub.get("_qa_severity") == "ERROR")
            if error_count > 0:
                self.qaExportWarningRequired.emit(file_path, error_count)
                return

        success, msg = SRTExporter.export(subtitles, file_path)
        if success:
            self.notify.emit("SUCCESS", msg)
        else:
            self.notify.emit("ERROR", msg)

    @staticmethod
    def _restore_subtitles_from_sidecar(parsed_data, sidecar_subs):
        if not sidecar_subs:
            return
        sub_by_time = {
            (s.get("start_time"), s.get("end_time")): s
            for s in sidecar_subs if isinstance(s, dict)
        }
        sub_by_idx = {
            s.get("index"): s
            for s in sidecar_subs if isinstance(s, dict) and "index" in s
        }
        for i, p_sub in enumerate(parsed_data):
            matched = sub_by_time.get((p_sub.get("start_time"), p_sub.get("end_time")))
            if not matched:
                matched = sub_by_idx.get(p_sub.get("index"))
            if not matched and i < len(sidecar_subs):
                matched = sidecar_subs[i]
            if matched:
                sidecar_status = str(matched.get("status", "")).upper()
                sidecar_trans = matched.get("translation", "")
                if sidecar_trans:
                    p_sub["translation"] = sidecar_trans
                    if sidecar_status in ("ACCEPTED", "TRANSLATED", "EDITED", "ERROR"):
                        p_sub["status"] = sidecar_status
                    else:
                        p_sub["status"] = "TRANSLATED"
                elif sidecar_status:
                    p_sub["status"] = sidecar_status

                if matched.get("original") and sidecar_trans and p_sub.get("original") == sidecar_trans:
                    p_sub["original"] = matched["original"]
                if "_qa_severity" in matched:
                    p_sub["_qa_severity"] = matched["_qa_severity"]

    @Slot(str)
    def importSrt(self, file_url):
        file_path = _normalize_file_path(file_url)
        if not os.path.exists(file_path):
            self.notify.emit("ERROR", "Không tìm thấy file SRT!")
            return
            
        # FIX: Ghi nhận chính xác đường dẫn & tên file gốc lúc import
        self._original_source_path = file_path
        self._primary_source_path = file_path
        self._original_source_file = os.path.basename(file_path)

        m = re.search(r'(?:^|_)batch_(\d+)_to_(\d+)', self._original_source_file, re.IGNORECASE)
        if m:
            self._is_batch_mode = True
            self._batch_start_num = int(m.group(1))
            self._batch_end_num = int(m.group(2))
            self.batchDetected.emit(self._batch_start_num, self._batch_end_num)
        else:
            self._is_batch_mode = False
            self._batch_start_num = 0
            self._batch_end_num = 0
            self.batchDetected.emit(0, 0)
        
        parsed_data = SRTParser.parse(file_path)
        if parsed_data:
            self._batch_slices = [(file_path, 0, len(parsed_data))]
        else:
            self._batch_slices = []
        if not parsed_data:
            self.notify.emit("ERROR", "Không thể đọc nội dung file SRT hoặc file rỗng!")
            return

        sidecar_path = os.path.splitext(file_path)[0] + ".aisrt"
        has_sidecar = False
        sidecar_source_lang = None
        if os.path.exists(sidecar_path):
            try:
                with open(sidecar_path, 'r', encoding='utf-8') as f:
                    sidecar_data = json.load(f)

                self.glossary = self._load_glossary(sidecar_data)
                self.entity_dictionary = self._load_entities(sidecar_data)
                self.translation_memory = self._load_translation_memory(sidecar_data)

                intelligence = sidecar_data.get("intelligence", {})
                if isinstance(intelligence, dict):
                    self._active_archetype = intelligence.get("archetype", ARCHETYPE_CUSTOM)
                    self._active_pronoun_pair = intelligence.get(
                        "pronoun_pair",
                        DEFAULT_PRONOUNS.get(self._active_archetype, DEFAULT_PRONOUNS[ARCHETYPE_CUSTOM]),
                    )
                    self._is_archetype_locked = bool(intelligence.get("is_archetype_locked", False))
                    self.dismissed_auto_terms = set(intelligence.get("dismissed_auto_terms", []))
                    self._is_ja_origin = bool(intelligence.get("is_ja_origin", False))

                self.archetypeChanged.emit()
                self.glossaryChanged.emit()

                story_summary = sidecar_data.get("story_summary", "")
                self._story_summary = (story_summary or "").strip()

                self._restore_subtitles_from_sidecar(parsed_data, sidecar_data.get("subtitles", []))

                metadata = sidecar_data.get("metadata", {})
                sidecar_source_lang = metadata.get("source_language")
                has_sidecar = True
            except Exception as e:
                print(f"[IMPORT_SRT] Failed to restore sidecar {sidecar_path}: {e}")
            
        # 1. Quét 30 câu phụ đề đầu tiên tự động nhận diện ngôn ngữ
        sample_subs = " ".join([
            str(sub.get("original", "")) for sub in parsed_data[:30] if isinstance(sub, dict)
        ])
        detected_lang = ContextAnalyzer.detect_native_language(sample_subs)

        # 2. Tự động khôi phục bản dịch cho file SRT đã dịch sẵn tiếng Việt (khi không có sidecar hoặc sidecar rỗng bản dịch)
        has_any_translation = any(bool(str(sub.get("translation", "")).strip()) for sub in parsed_data if isinstance(sub, dict))
        if (not has_sidecar or not has_any_translation) and detected_lang == "Vietnamese":
            for sub in parsed_data:
                if isinstance(sub, dict) and not str(sub.get("translation", "")).strip():
                    sub["translation"] = sub.get("original", "")
                    sub["status"] = "ACCEPTED"

        # 3. Nạp dữ liệu mới vào Model
        self._subtitle_model.load_data(parsed_data)
        self._set_project_state(True, False if (has_sidecar and has_any_translation) else True)
        
        # 4. Reset trạng thái giao diện hoặc khôi phục Story Summary
        if not has_sidecar:
            self._story_summary = ""
        self.projectLoaded.emit(self._story_summary)

        if not has_sidecar or not sidecar_source_lang or (sidecar_source_lang == "English" and detected_lang != "English"):
            source_lang = detected_lang
        else:
            source_lang = sidecar_source_lang

        self._source_language = source_lang
        self.languageLoaded.emit(source_lang)

        ja_detection = ContextAnalyzer.detect_ja_translated_en(sample_subs, "")
        old_is_ja = self._is_ja_origin
        self._is_ja_origin = (source_lang == "Japanese") or ja_detection.get("is_ja_origin", False)
        if old_is_ja != self._is_ja_origin:
            self.archetypeChanged.emit()

        self._add_recent_file(self._original_source_path)
        if has_sidecar and has_any_translation:
            self.notify.emit("SUCCESS", f"Đã tải {len(parsed_data)} câu từ SRT & khôi phục trạng thái từ dự án: {os.path.basename(sidecar_path)}")
        elif detected_lang == "Vietnamese":
            self.notify.emit("SUCCESS", f"Đã tải {len(parsed_data)} câu tiếng Việt hoàn tất từ SRT: {self._original_source_file}")
        elif has_sidecar:
            self.notify.emit("SUCCESS", f"Đã tải {len(parsed_data)} câu từ SRT & khôi phục trạng thái từ dự án: {os.path.basename(sidecar_path)}")
        else:
            self.notify.emit("SUCCESS", f"Đã tải {len(parsed_data)} câu từ SRT: {self._original_source_file}")

    @Slot(result=bool)
    def quickSyncToOriginal(self):
        """Đồng bộ trực tiếp dữ liệu dịch về các file SRT gốc (hỗ trợ nhiều đợt)."""
        if not self._original_source_path:
            self.notify.emit("ERROR", "Không tìm thấy file nguồn gốc để đồng bộ!")
            return False
        subtitles = self._subtitle_model.get_all_data() if self._subtitle_model else []
        if not subtitles:
            self.notify.emit("ERROR", "Không có dữ liệu phụ đề để đồng bộ!")
            return False

        # Xác định danh sách đợt cần đồng bộ
        if self._batch_slices:
            batch_list = self._batch_slices
        else:
            batch_list = [(self._original_source_path, 0, len(subtitles))]

        sync_errors = []
        synced_files = []

        for b_path, s_start, s_end in batch_list:
            dir_name = os.path.dirname(os.path.abspath(b_path))
            if not os.path.exists(dir_name):
                sync_errors.append(f"Thư mục không tồn tại: {b_path}")
                continue

            b_subs = subtitles[s_start:s_end]
            if not b_subs:
                continue

            export_subs = []
            for i, s in enumerate(b_subs):
                item = dict(s)
                item["index"] = i + 1
                export_subs.append(item)

            ok, msg = SRTExporter.export(export_subs, b_path)
            if ok:
                sidecar_path = os.path.splitext(b_path)[0] + ".aisrt"
                self.saveProject(
                    sidecar_path,
                    getattr(self, "_story_summary", ""),
                    getattr(self, "_source_language", "English"),
                    getattr(self, "_target_language", "Vietnamese"),
                    notify=False,
                )
                synced_files.append(os.path.basename(b_path))
            else:
                sync_errors.append(f"{os.path.basename(b_path)}: {msg}")

        if sync_errors:
            self.notify.emit("ERROR", f"Lỗi đồng bộ: {'; '.join(sync_errors)}")
            return False

        self._is_dirty = False
        self.projectStateChanged.emit()
        if len(synced_files) > 1:
            self.notify.emit("SUCCESS", f"Đã đồng bộ {len(synced_files)} đợt về Studio: {', '.join(synced_files)}")
        else:
            self.notify.emit("SUCCESS", f"Đã đồng bộ trực tiếp về Studio: {synced_files[0] if synced_files else ''}")
        return True

    @Slot(str, result=bool)
    def appendNextBatch(self, file_url):
        """Đọc file đợt mới, nối tiếp vào subtitle model bằng append_data() và bảo toàn ngữ cảnh."""
        file_path = _normalize_file_path(file_url)
        if not os.path.exists(file_path):
            self.notify.emit("ERROR", "Không tìm thấy file đợt dịch tiếp theo!")
            return False

        parsed_data = SRTParser.parse(file_path)
        if not parsed_data:
            self.notify.emit("ERROR", "Không thể đọc nội dung file đợt dịch hoặc file rỗng!")
            return False

        sidecar_path = os.path.splitext(file_path)[0] + ".aisrt"
        if os.path.exists(sidecar_path):
            try:
                with open(sidecar_path, 'r', encoding='utf-8') as f:
                    sidecar_data = json.load(f)
                self._restore_subtitles_from_sidecar(parsed_data, sidecar_data.get("subtitles", []))
            except Exception as e:
                print(f"[APPEND_BATCH] Failed to restore sidecar {sidecar_path}: {e}")

        # KHỬ TRÙNG LẶP THEO MỐC THỜI GIAN (Deduplication by Timecode)
        existing_times = {
            (sub.get("start_time"), sub.get("end_time"))
            for sub in (self._subtitle_model.get_all_data() if self._subtitle_model else [])
        }
        unique_new_subs = [
            sub for sub in parsed_data
            if (sub.get("start_time"), sub.get("end_time")) not in existing_times
        ]
        if not unique_new_subs:
            self.notify.emit("WARNING", "Tất cả các câu trong đợt này đã tồn tại trong dự án!")
            return True

        file_name = os.path.basename(file_path)
        m = re.search(r'(?:^|_)batch_(\d+)_to_(\d+)', file_name, re.IGNORECASE)
        if m:
            new_end = int(m.group(2))
            if self._is_batch_mode:
                self._batch_end_num = new_end
            else:
                self._is_batch_mode = True
                self._batch_start_num = int(m.group(1))
                self._batch_end_num = new_end
            self.batchDetected.emit(self._batch_start_num, self._batch_end_num)

        # Bảo toàn primary source path
        if not self._original_source_path and self._primary_source_path:
            self._original_source_path = self._primary_source_path

        sample_batch = " ".join([
            str(sub.get("original", "")) for sub in unique_new_subs[:30] if isinstance(sub, dict)
        ])
        batch_lang = ContextAnalyzer.detect_native_language(sample_batch)
        has_any_batch_trans = any(bool(str(sub.get("translation", "")).strip()) for sub in unique_new_subs if isinstance(sub, dict))
        if (not os.path.exists(sidecar_path) or not has_any_batch_trans) and batch_lang == "Vietnamese":
            for sub in unique_new_subs:
                if isinstance(sub, dict) and not str(sub.get("translation", "")).strip():
                    sub["translation"] = sub.get("original", "")
                    sub["status"] = "ACCEPTED"

        first_new_index = len(self._subtitle_model.get_all_data()) if self._subtitle_model else 0
        end_new_index = first_new_index + len(unique_new_subs)
        self._batch_slices.append((file_path, first_new_index, end_new_index))

        self._subtitle_model.append_data(unique_new_subs)
        if batch_lang == "Japanese" and not self._is_ja_origin:
            self._is_ja_origin = True
            self.archetypeChanged.emit()
            self.languageLoaded.emit("Japanese")
        self._is_dirty = True
        self.projectStateChanged.emit()
        self.batchAppended.emit(first_new_index)
        self.notify.emit("SUCCESS", f"Đã nối tiếp {len(unique_new_subs)} câu từ đợt mới: {file_name}")
        return True

    # ---- BỔ SUNG 2 HÀM LƯU VÀ MỞ PROJECT ----
    @Slot(str, str, str, str)
    def saveProject(self, file_url, story_summary, source_lang="English", target_lang="Vietnamese", notify=True):
        self._story_summary = (story_summary or "").strip()
        self._source_language = source_lang or getattr(self, "_source_language", "English")
        self._target_language = target_lang or getattr(self, "_target_language", "Vietnamese")
        file_path = _normalize_file_path(file_url)

        if not file_path.endswith('.aisrt'):
            file_path += '.aisrt'
            
        clean_subtitles = [
            {k: v for k, v in sub.items() if not k.startswith("_")}
            for sub in (self._subtitle_model.get_all_data() if self._subtitle_model else [])
            if str(sub.get("status", "")).upper() != "ACCEPTED"
        ]

        intelligence = {
            "glossary": self.glossary.to_payload(),
            "entities": self.entity_dictionary.to_payload(),
            "translation_memory": self.translation_memory.to_payload(),
        }
        if (
            self._active_archetype != ARCHETYPE_CUSTOM
            or self._is_archetype_locked
            or bool(self.dismissed_auto_terms)
            or self._active_pronoun_pair != DEFAULT_PRONOUNS[ARCHETYPE_CUSTOM]
            or self._is_ja_origin
        ):
            intelligence["archetype"] = self._active_archetype
            intelligence["pronoun_pair"] = self._active_pronoun_pair
            intelligence["is_archetype_locked"] = self._is_archetype_locked
            intelligence["dismissed_auto_terms"] = list(self.dismissed_auto_terms)
            intelligence["is_ja_origin"] = self._is_ja_origin

        data = {
            "metadata": {
                # FIX: Dùng biến state đã lưu, không tự đoán từ file_path
                "source_file": getattr(self, "_original_source_file", "unknown.srt"),
                "source_language": source_lang,
                "target_language": target_lang,
                "version": "1.0"
            },
            "story_summary": story_summary,
            "subtitles": clean_subtitles,
            "intelligence": intelligence,
        }
        # Log tổng hợp 1 dòng duy nhất thay vì vòng lặp 2.000 dòng gây đơ UI
        if len(clean_subtitles) > 0:
            print(f"[PROJECT] Đã lưu {len(clean_subtitles)} câu vào {os.path.basename(file_path)}", flush=True)

        temp_path = f"{file_path}.{uuid4().hex[:8]}.tmp"
        try:
            # Bước 1: Ghi vào file tạm, ép flush + fsync xuống đĩa cứng
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Bước 2: Đã đóng file descriptor, thực hiện atomic replace có retry chống Windows Defender lock
            last_err = None
            for attempt in range(3):
                try:
                    os.replace(temp_path, file_path)
                    last_err = None
                    break
                except PermissionError as perm_err:
                    last_err = perm_err
                    time.sleep(0.05)
            if last_err is not None:
                raise last_err

            self._set_project_state(True, False)
            if notify:
                self.notify.emit("SUCCESS", f"Đã lưu dự án: {os.path.basename(file_path)}")
        except Exception as e:
            self.notify.emit("ERROR", f"Lỗi lưu dự án: {str(e)}")
        finally:
            # Bước 3: Dọn dẹp file .tmp rác nếu quá trình lưu gặp sự cố
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    @Slot(str)
    def loadProject(self, file_url):
        file_path = _normalize_file_path(file_url)
        if not os.path.exists(file_path):
            self.notify.emit("ERROR", "Không tìm thấy file dự án!")
            return
            
        self._loading_project = True
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            loaded_glossary = self._load_glossary(data)
            loaded_entities = self._load_entities(data)
            loaded_tm = self._load_translation_memory(data)

            intelligence = data.get("intelligence", {})
            if isinstance(intelligence, dict):
                loaded_archetype = ARCHETYPE_PURE
                loaded_pronoun = ""
                loaded_locked = bool(intelligence.get("is_archetype_locked", False))
                loaded_dismissed = set(intelligence.get("dismissed_auto_terms", []))
                loaded_is_ja = bool(intelligence.get("is_ja_origin", False))
            else:
                loaded_archetype = ARCHETYPE_PURE
                loaded_pronoun = ""
                loaded_locked = False
                loaded_dismissed = set()
                loaded_is_ja = False

            story_summary = data.get("story_summary", "")
            self._story_summary = (story_summary or "").strip()
            subtitles = data.get("subtitles", [])
            self._batch_slices = []

            sample_subs = " ".join([
                str(sub.get("original", "")) for sub in subtitles[:30] if isinstance(sub, dict)
            ])
            detected_lang = ContextAnalyzer.detect_native_language(sample_subs)
            has_any_translation = any(bool(str(s.get("translation", "")).strip()) for s in subtitles if isinstance(s, dict))
            is_healed_vi = False
            if not has_any_translation and detected_lang == "Vietnamese":
                for sub in subtitles:
                    if isinstance(sub, dict) and not str(sub.get("translation", "")).strip():
                        sub["translation"] = sub.get("original", "")
                        sub["status"] = "ACCEPTED"
                is_healed_vi = True

            # CAT Queue Invariant: Chỉ nạp các câu chưa duyệt (PENDING, TRANSLATING, TRANSLATED, ERROR)
            pending_subtitles = [
                sub for sub in subtitles
                if isinstance(sub, dict) and str(sub.get("status", "")).upper() != "ACCEPTED"
            ]
            self._subtitle_model.load_data(pending_subtitles)
            if len(pending_subtitles) == 0:
                tc = getattr(self, "_translation_controller", None) or getattr(self, "translation_controller", None)
                if tc and hasattr(tc, "loadSubtitle"):
                    tc.loadSubtitle(-1)
            self.glossary = loaded_glossary
            self.entity_dictionary = loaded_entities
            self.translation_memory = loaded_tm
            self._active_archetype = loaded_archetype
            self._active_pronoun_pair = loaded_pronoun
            self._is_archetype_locked = loaded_locked
            self.dismissed_auto_terms = loaded_dismissed
            self._is_ja_origin = loaded_is_ja
            self.archetypeChanged.emit()
            self.glossaryChanged.emit()
            print(f"[PROJECT_LOAD] Loaded {len(subtitles)} subtitles from {os.path.basename(file_path)}")
            self.projectLoaded.emit(story_summary)
            
            # --- ĐOẠN ĐÃ SỬA: DỌN DẸP DUPLICATE EMIT ---
            metadata = data.get("metadata", {})
            self._original_source_file = metadata.get("source_file", "unknown.srt")
            self._original_source_path = file_path
            self._is_batch_mode = False
            self._batch_start_num = 0
            self._batch_end_num = 0
            self.batchDetected.emit(0, 0)
            source_lang = metadata.get("source_language", "English")
            sample_subs = " ".join([
                str(sub.get("original", "")) for sub in subtitles[:30] if isinstance(sub, dict)
            ])
            detected_lang = ContextAnalyzer.detect_native_language(sample_subs)
            # Nếu dự án cũ bị lưu nhầm là English nhưng phụ đề thực tế là tiếng Nhật/Hàn/Trung:
            if detected_lang != "English" and (not source_lang or source_lang == "English"):
                source_lang = detected_lang
            if detected_lang == "Japanese" and not self._is_ja_origin:
                self._is_ja_origin = True
                self.archetypeChanged.emit()
            
            self._source_language = source_lang
            self._target_language = metadata.get("target_language", "Vietnamese")
            self.languageLoaded.emit(source_lang) # Chỉ emit 1 lần duy nhất
            # -------------------------------------------

            self._add_recent_file(file_path)
            self._set_project_state(True, is_healed_vi)
            self.notify.emit("SUCCESS", f"Đã mở dự án: {os.path.basename(file_path)}")
        except Exception as e:
            self.notify.emit("ERROR", f"Lỗi mở dự án: {str(e)}")
        finally:
            self._loading_project = False

    @staticmethod
    def _load_glossary(data):
        if "intelligence" not in data:
            return Glossary()
        intelligence = data["intelligence"]
        if not isinstance(intelligence, dict):
            raise ValueError("Invalid intelligence data")
        if "glossary" not in intelligence:
            return Glossary()
        return Glossary.from_payload(intelligence["glossary"])

    @staticmethod
    def _load_entities(data):
        if "intelligence" not in data:
            return EntityDictionary()
        intelligence = data["intelligence"]
        if not isinstance(intelligence, dict):
            raise ValueError("Invalid intelligence data")
        if "entities" not in intelligence:
            return EntityDictionary()
        return EntityDictionary.from_payload(intelligence["entities"])

    @staticmethod
    def _load_translation_memory(data):
        if "intelligence" not in data:
            return TranslationMemory()
        intelligence = data["intelligence"]
        if not isinstance(intelligence, dict):
            raise ValueError("Invalid intelligence data")
        if "translation_memory" not in intelligence:
            return TranslationMemory()
        return TranslationMemory.from_payload(intelligence["translation_memory"])

