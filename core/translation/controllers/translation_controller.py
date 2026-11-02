import re
from PySide6.QtCore import QObject, Slot, Signal, Property, QTimer, QCoreApplication
from core.translation.llm.worker import TranslationWorker
from core.translation.core.context_engine import ContextEngine
from core.translation.core.prompt_builder import PromptBuilder
from core.translation.core.hardware_detector import HardwareDetector
from core.translation.core.context_analyzer import ContextAnalyzer

class TranslationController(QObject):
    statusChanged = Signal(str)
    translationUpdated = Signal(str)
    originalUpdated = Signal(str)
    notify = Signal(str, str)
    contextUpdated = Signal() # TÍN HIỆU MỚI CHO CONTEXT
    progressChanged = Signal()
    engineStatusChanged = Signal(str)
    translationCompleted = Signal(int)
    translationFailed = Signal(int, str)
    qaStatusChanged = Signal()
    alternativeTranslationReady = Signal(int, str, str)
    alternativeTranslationLoading = Signal(bool)
    appliedTermsChanged = Signal()
    translationProgressChanged = Signal(int)

    def __init__(self, subtitle_model, worker_factory=None):
        super().__init__()
        self._status = "PENDING"
        self._engine_status = "Not loaded"
        self._active_translation_index = -1
        self._current_index = -1
        self._current_display_index = -1
        self._selection_changed_during_translation = False
        self._current_translation = ""
        self._current_original = ""
        self._current_start_time = ""
        self._current_end_time = ""
        self._context_prev = "" # LƯU CONTEXT TRƯỚC
        self._context_next = "" # LƯU CONTEXT SAU
        self._current_source_language = "English"
        self._translation_progress = 0
        
        self._subtitle_model = subtitle_model
        self._worker_factory = worker_factory or TranslationWorker
        self.worker = None
        self.alt_worker = None
        self._extract_worker = None
        self.hardware_profile = HardwareDetector.get_recommended_profile()
        self._glossary = None
        self._entities = None
        self._translation_memory = None
        self._project_controller = None
        self._subtitle_model.modelReset.connect(self._emit_progress)
        self._subtitle_model.dataChanged.connect(self._emit_progress)
        self._subtitle_model.modelReset.connect(self._emit_qa_status)
        self._subtitle_model.dataChanged.connect(self._emit_qa_status)
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(250)
        self._progress_timer.timeout.connect(self._on_thinking_progress_tick)
        app = QCoreApplication.instance()
        if app:
            app.aboutToQuit.connect(self.shutdown)

    def shutdown(self):
        if hasattr(self, "_progress_timer") and self._progress_timer.isActive():
            self._progress_timer.stop()
        for w in (self.worker, self.alt_worker, self._extract_worker):
            if w is not None:
                try:
                    if hasattr(w, "isRunning") and w.isRunning():
                        if hasattr(w, "cancel"):
                            w.cancel()
                        w.wait(2000)
                    if hasattr(w, "deleteLater"):
                        w.deleteLater()
                except (RuntimeError, Exception):
                    pass
        self.worker = None
        self.alt_worker = None
        self._extract_worker = None

    def _safe_cleanup_worker(self, worker_attr: str):
        """AUD-MEM-001: Thu hồi C++ QThread an toàn khi thay thế worker cũ."""
        w = getattr(self, worker_attr, None)
        if w is not None:
            try:
                if hasattr(w, "isRunning") and not w.isRunning() and hasattr(w, "deleteLater"):
                    w.deleteLater()
            except (RuntimeError, Exception):
                pass
            setattr(self, worker_attr, None)

    def is_busy(self) -> bool:
        """AUD-CONCUR-001: Kiểm tra xem có worker LLM nào đang chạy hay không để ngăn race condition."""
        for attr in ("worker", "alt_worker", "_extract_worker"):
            w = getattr(self, attr, None)
            if w is not None:
                try:
                    if hasattr(w, "isRunning") and w.isRunning():
                        return True
                except (RuntimeError, Exception):
                    pass
        return False

    def _on_thinking_progress_tick(self):
        """AUD-UX-001: Tăng tiến độ động từ 10% và tiếp tục bò mượt trong giai đoạn model suy luận (<think>)."""
        if self._status == "TRANSLATING":
            if self._translation_progress < 35:
                self._translation_progress = min(35, self._translation_progress + 2)
            elif self._translation_progress < 70:
                self._translation_progress += 1
            elif self._translation_progress < 85:
                if getattr(self, "_progress_tick_count", 0) % 3 == 0:
                    self._translation_progress = min(85, self._translation_progress + 1)
            elif self._translation_progress < 95:
                if getattr(self, "_progress_tick_count", 0) % 6 == 0:
                    self._translation_progress = min(95, self._translation_progress + 1)
            self._progress_tick_count = getattr(self, "_progress_tick_count", 0) + 1
            self.translationProgressChanged.emit(self._translation_progress)
        else:
            self._progress_timer.stop()

    @Slot()
    def openHotkeys(self):
        """AUD-UX-003: Mở Bảng tra cứu phím tắt từ CAT Studio."""
        from ui.dialogs.hotkeys_cheatsheet_dialog import HotkeysCheatsheetDialog
        dialog = HotkeysCheatsheetDialog()
        dialog.exec()

    def _emit_qa_status(self, *args):
        self.qaStatusChanged.emit()

    def bind_intelligence(self, glossary=None, entities=None, translation_memory=None, project_controller=None):
        """Kết nối các thành phần trí tuệ: glossary, entities, translation_memory, project_controller."""
        self._glossary = glossary
        self._entities = entities
        self._translation_memory = translation_memory
        self._project_controller = project_controller
        if project_controller and hasattr(project_controller, "glossaryChanged"):
            try:
                project_controller.glossaryChanged.connect(self.appliedTermsChanged.emit)
            except Exception:
                pass

    @property
    def glossary(self):
        if self._project_controller and hasattr(self._project_controller, "glossary"):
            return self._project_controller.glossary
        return self._glossary

    @property
    def entities(self):
        if self._project_controller and hasattr(self._project_controller, "entity_dictionary"):
            return self._project_controller.entity_dictionary
        return self._entities

    @property
    def translation_memory(self):
        if self._project_controller and hasattr(self._project_controller, "translation_memory"):
            return self._project_controller.translation_memory
        return self._translation_memory

    @property
    def _worker(self):
        return self.worker

    @Property(int, notify=progressChanged)
    def totalSubtitleCount(self):
        return len(self._subtitle_model.get_all_data())

    @Property(int, notify=progressChanged)
    def acceptedCount(self):
        return sum(1 for sub in self._subtitle_model.get_all_data() if str(sub.get("status", "")).upper() == "ACCEPTED")

    def _emit_progress(self, *args):
        self.progressChanged.emit()

    @Property(str, notify=engineStatusChanged)
    def engineStatus(self):
        return self._engine_status

    def _set_engine_status(self, status):
        if self._engine_status != status:
            self._engine_status = status
            self.engineStatusChanged.emit(status)

    @Property(int, notify=translationProgressChanged)
    def translationProgress(self):
        return self._translation_progress

    @Property(str, notify=statusChanged)
    def status(self): return self._status

    @Property(int, notify=statusChanged)
    def activeTranslationIndex(self):
        return self._active_translation_index

    @Property(int, notify=statusChanged)
    def currentSubtitleIndex(self):
        return self._current_index

    @Property(int, notify=originalUpdated)
    def currentDisplayIndex(self):
        return getattr(self, "_current_display_index", self._current_index + 1 if self._current_index >= 0 else 0)

    @Property(str, notify=translationUpdated)
    def currentTranslation(self): return self._current_translation

    @Property(str, notify=originalUpdated)
    def currentOriginal(self): return self._current_original

    @Property(str, notify=originalUpdated)
    def currentSourceLanguage(self):
        return getattr(self, "_current_source_language", "English")
    
    @Property(str, notify=originalUpdated)
    def currentStartTime(self): return self._current_start_time
    
    @Property(str, notify=originalUpdated)
    def currentEndTime(self): return self._current_end_time

    # EXPOSE CONTEXT RA QML
    @Property(str, notify=contextUpdated)
    def contextPrev(self): return self._context_prev

    @Property(str, notify=contextUpdated)
    def contextNext(self): return self._context_next

    @Property(str, notify=qaStatusChanged)
    def currentQaSeverity(self):
        subtitles = self._subtitle_model.get_all_data()
        if 0 <= self._current_index < len(subtitles):
            return subtitles[self._current_index].get("_qa_severity", "")
        return ""

    @Property(str, notify=qaStatusChanged)
    def currentQaTooltip(self):
        subtitles = self._subtitle_model.get_all_data()
        if 0 <= self._current_index < len(subtitles):
            return subtitles[self._current_index].get("_qa_tooltip", "")
        return ""

    @Property("QVariantList", notify=appliedTermsChanged)
    def currentAppliedTerms(self):
        if not self._current_original:
            return []
        terms = []
        seen = set()

        # Ưu tiên 1: Các từ khớp với Glossary và Entity Dictionary (is_glossary: True)
        if self.glossary:
            for hit in self.glossary.match(self._current_original, word_boundary=True):
                src = hit.source_term
                tgt = hit.preferred_translation
                if src.lower() not in seen:
                    seen.add(src.lower())
                    terms.append({"source": src, "target": tgt, "is_glossary": True})
        if self.entities:
            for hit in self.entities.match(self._current_original, word_boundary=True):
                src = getattr(hit, "matched_form", "") or getattr(hit, "entity_name", "")
                tgt = getattr(hit, "canonical_translation", "")
                if src and src.lower() not in seen:
                    seen.add(src.lower())
                    terms.append({"source": src, "target": tgt, "is_glossary": True})

        # Ưu tiên 2: Toàn bộ các từ gốc tự động bóc tách (auto_terms) của câu đang chọn
        subtitles = self._subtitle_model.get_all_data()
        if 0 <= self._current_index < len(subtitles):
            sub = subtitles[self._current_index]
            auto_terms = sub.get("auto_terms", [])
            if isinstance(auto_terms, list):
                for item in auto_terms:
                    if isinstance(item, dict):
                        src = (item.get("source") or "").strip()
                        tgt = (item.get("target") or "").strip()
                        if src and tgt and src.lower() not in seen:
                            seen.add(src.lower())
                            terms.append({"source": src, "target": tgt, "is_glossary": False})
        return terms

    @Slot(int)
    def loadSubtitle(self, index):
        if index < 0: 
            self._current_index = -1
            self._current_display_index = -1
            self._current_original = ""
            self._current_source_language = "English"
            self._current_translation = ""
            self._current_start_time = ""
            self._current_end_time = ""
            self._context_prev = ""
            self._context_next = ""
            self._status = "IDLE"
            self._translation_progress = 0
            self.translationProgressChanged.emit(0)
            self.statusChanged.emit(self._status)
            self.translationUpdated.emit(self._current_translation)
            self.originalUpdated.emit(self._current_original)
            self.contextUpdated.emit()
            self.qaStatusChanged.emit()
            return
            
        subtitles = self._subtitle_model.get_all_data()
        if index >= len(subtitles): return
        sub = subtitles[index]
        if (
            self._active_translation_index >= 0
            and index != self._active_translation_index
        ):
            self._selection_changed_during_translation = True
        self._current_index = index
        self._current_display_index = int(sub.get("index", index + 1))
        
        self._current_original = sub.get("original", "")
        self._current_source_language = ContextAnalyzer.detect_native_language(self._current_original)
        self._current_start_time = sub.get("start_time", "")
        self._current_end_time = sub.get("end_time", "")
        status = str(sub.get("status", "PENDING")).upper()
        
        if status in ["ACCEPTED", "EDITED", "TRANSLATED", "TRANSLATING", "ERROR"]:
            self._current_translation = sub.get("translation", "")
        else:
            self._current_translation = ""
            
        self._status = "TRANSLATING" if index == self._active_translation_index else status
        
        # TRÍCH XUẤT CONTEXT ĐỂ HIỂN THỊ LÊN UI
        prev_ctx, _, next_ctx = ContextEngine.get_context(subtitles, index)
        self._context_prev = "\n\n".join(prev_ctx) if prev_ctx else "Không có dữ liệu trước."
        self._context_next = "\n\n".join(next_ctx) if next_ctx else "Không có dữ liệu sau."
        
        # Bảo toàn mốc tiến trình nếu câu đang được dịch
        if self._active_translation_index >= 0 and index == self._active_translation_index:
            self.translationProgressChanged.emit(self._translation_progress)
        else:
            self._translation_progress = 0
            self.translationProgressChanged.emit(0)
        self.statusChanged.emit(self._status)
        self.translationUpdated.emit(self._current_translation)
        self.originalUpdated.emit(self._current_original)
        self.contextUpdated.emit()
        self.qaStatusChanged.emit()
        self.appliedTermsChanged.emit()

    @Slot()
    def markAsEdited(self):
        if self._status in ["PENDING", "TRANSLATED", "ACCEPTED"]:
            self._status = "EDITED"
            self.statusChanged.emit(self._status)

    @Slot(str)
    def updateCurrentTranslation(self, text: str):
        self._current_translation = text
        self._status = "EDITED"
        if 0 <= self._active_translation_index < len(self._subtitle_model.get_all_data()):
            self._subtitle_model.update_translation(self._active_translation_index, text, "EDITED")
        self.statusChanged.emit(self._status)
        self.translationUpdated.emit(self._current_translation)

    @Slot(int, str, str, str)
    def requestTranslation(self, index, source_lang, target_lang, story_summary):
        subtitles = self._subtitle_model.get_all_data()
        if index < 0 or index >= len(subtitles):
            return

        # Gate 1: Data Sanity Check (Bỏ qua câu rỗng hoặc placeholder)
        current_raw = (subtitles[index].get("original") or "").strip()
        if not current_raw or current_raw in {"[ Chưa có nội dung ]", "[Chưa có nội dung]"}:
            self.notify.emit("WARNING", "Phân đoạn phụ đề trống hoặc không có nội dung để dịch!")
            return

        # AUD-CONCUR-001: Khóa kiểm tra bận liên luồng toàn bộ worker LLM
        if self.is_busy():
            return

        if not source_lang or (source_lang == "English" and getattr(self, "_current_source_language", "English") != "English"):
            source_lang = self._current_source_language

        # Gate 2: Language Sanity Check (Chặn nguồn trùng đích)
        if source_lang and target_lang and source_lang.strip().lower() == target_lang.strip().lower():
            self.notify.emit("WARNING", "Ngôn ngữ nguồn và ngôn ngữ đích không được trùng nhau!")
            return

        # Gate 3: Model Readiness Check (Chặn khi model chưa sẵn sàng)
        mc = getattr(self, "_model_controller", None)
        if mc is not None and hasattr(mc, "hasValidModel") and not mc.hasValidModel:
            self.notify.emit("WARNING", "Mô hình AI chưa sẵn sàng hoặc chưa được tải về máy!")
            return

        self._active_translation_index = index
        self._selection_changed_during_translation = False
        self._status = "TRANSLATING"
        self._set_engine_status("Translating")
        self._translation_progress = 10
        self._progress_tick_count = 0
        self.translationProgressChanged.emit(10)
        self.statusChanged.emit(self._status)
        self._current_translation = ""
        self.translationUpdated.emit("")
        self._subtitle_model.update_translation(index, "", "TRANSLATING")

        subtitles = self._subtitle_model.get_all_data()
        prev_ctx, current, next_ctx = ContextEngine.get_context(subtitles, index)

        # TM short-circuit: 100% exact match
        if self.translation_memory:
            hit = self.translation_memory.lookup(current)
            if hit:
                self._subtitle_model.update_translation(index, hit.target_text, "TRANSLATED")
                self._status = "TRANSLATED"
                self._current_translation = hit.target_text
                self._set_engine_status("Ready")

                def _emit_tm_hit(idx=index, text=hit.target_text):
                    self.translationUpdated.emit(text)
                    self.statusChanged.emit("TRANSLATED")
                    self.translationCompleted.emit(idx)

                QTimer.singleShot(0, _emit_tm_hit)
                return

        # Thu thập các matches từ Glossary và Entity Dictionary
        enriched_glossary_hits = []
        if self.glossary:
            for hit in self.glossary.match(current, word_boundary=True):
                entry = self.glossary.get(hit.source_term)
                forbidden = entry.forbidden_alternatives if entry else ()
                enriched_glossary_hits.append((hit, forbidden))

        entity_hits = self.entities.match(current, word_boundary=True) if self.entities else ()
        active_pronoun = (
            getattr(self._project_controller, "activePronounPair", "")
            if self._project_controller
            else ""
        )
        active_archetype = (
            getattr(self._project_controller, "activeArchetype", "")
            if self._project_controller
            else ""
        )
        is_ja = (
            getattr(self._project_controller, "isJaOrigin", False)
            if self._project_controller
            else False
        )
        model_name = (self.hardware_profile.get("model_name") or "").lower()
        if "gemma" in model_name:
            model_family = "gemma"
        elif "llama" in model_name:
            model_family = "llama"
        elif "deepseek" in model_name:
            model_family = "deepseek"
        else:
            model_family = "qwen"

        prompt = PromptBuilder.build(
            story_summary,
            source_lang,
            target_lang,
            prev_ctx,
            current,
            next_ctx,
            glossary_hits=tuple(enriched_glossary_hits),
            entity_hits=tuple(entity_hits),
            active_pronoun_pair=active_pronoun,
            is_ja_origin=is_ja,
            model_family=model_family,
            archetype=active_archetype,
        )

        self._safe_cleanup_worker("worker")
        if hasattr(self._worker_factory, "create_worker"):
            self.worker = self._worker_factory(index, prompt, self.hardware_profile) if not hasattr(self._worker_factory, "create_worker") else self._worker_factory.create_worker(index, prompt, self.hardware_profile)
        else:
            self.worker = self._worker_factory(index, prompt, self.hardware_profile)
        if hasattr(self.worker, "termsExtracted"):
            self.worker.termsExtracted.connect(self.on_terms_extracted)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self._progress_timer.start()
        self.worker.start()

    @Slot(int, list)
    def on_terms_extracted(self, index, terms):
        subtitles = self._subtitle_model.get_all_data()
        if 0 <= index < len(subtitles):
            subtitles[index]["auto_terms"] = terms
            if index == self._current_index:
                self.appliedTermsChanged.emit()

    @Slot(int, str)
    def on_progress(self, index, text):
        sender = self.sender()
        if sender is not None and sender is not self.worker:
            return
        if hasattr(self, "_progress_timer") and self._progress_timer.isActive():
            self._progress_timer.stop()
        self._subtitle_model.update_translation(index, text, "TRANSLATING")
        if index == self._active_translation_index and (
            self._current_index < 0 or index == self._current_index
        ):
            self._current_translation = text
            self._status = "TRANSLATING"
            expected_len = max(len(self._current_original) * 2, 20)
            if hasattr(self, "_progress_timer") and self._progress_timer.isActive():
                self._progress_timer.stop()
            self._translation_progress = min(95, max(35, int((len(text) / expected_len) * 60) + 35))
            self.translationProgressChanged.emit(self._translation_progress)
            self.translationUpdated.emit(text)

    @Slot(int, str)
    def on_finished(self, index, text):
        if hasattr(self, "_progress_timer") and self._progress_timer.isActive():
            self._progress_timer.stop()
        sender = self.sender()
        if sender is not None and sender is not self.worker:
            return
        clean_text = self._clean_translated_text(text)
        print(
            f"[TRANSLATION_CALLBACK] target={index} "
            f"clean_len={len(clean_text)} clean_text={clean_text!a} "
            f"active_target={self._active_translation_index} "
            f"controller_status_before={self._status} "
            f"current_translation_before={self._current_translation!a}",
            flush=True,
        )
        if not clean_text:
            message = "Lỗi: Model trả về bản dịch rỗng."
            self._subtitle_model.update_translation(index, message, "ERROR")
            if index == self._active_translation_index:
                self._active_translation_index = -1
                if (
                    not self._selection_changed_during_translation
                    or index == self._current_index
                ):
                    self._status = "ERROR"
                    self._current_translation = message
                    self.statusChanged.emit(self._status)
                    self.translationUpdated.emit(message)
            self._set_engine_status("Error")
            self.translationFailed.emit(index, message)
            return

        # Lưu trữ auto_terms từ worker nếu chưa lưu qua signal
        if hasattr(self.worker, "extracted_terms") and self.worker.extracted_terms:
            subtitles = self._subtitle_model.get_all_data()
            if 0 <= index < len(subtitles) and not subtitles[index].get("auto_terms"):
                subtitles[index]["auto_terms"] = self.worker.extracted_terms

        self._subtitle_model.update_translation(index, clean_text, "TRANSLATED")
        self.appliedTermsChanged.emit()
        self._translation_progress = 100
        self.translationProgressChanged.emit(100)
        if index == self._active_translation_index:
            self._active_translation_index = -1
            if (
                not self._selection_changed_during_translation
                or index == self._current_index
            ):
                self._status = "TRANSLATED"
                self._current_translation = clean_text
                self.statusChanged.emit(self._status)
                self.translationUpdated.emit(clean_text)
        print(
            f"[TRANSLATION_CALLBACK_AFTER] target={index} "
            f"controller_status={self._status} "
            f"current_translation_len={len(self._current_translation)} "
            f"current_translation={self._current_translation!a} "
            f"active_target={self._active_translation_index}",
            flush=True,
        )
        self._set_engine_status("Ready")
        self.translationCompleted.emit(index)

    @Slot(int, str)
    def on_error(self, index, err_msg):
        if hasattr(self, "_progress_timer") and self._progress_timer.isActive():
            self._progress_timer.stop()
        sender = self.sender()
        if sender is not None and sender is not self.worker:
            return
        message = f"Lỗi: {err_msg}"
        self._subtitle_model.update_translation(index, message, "ERROR")
        if index == self._active_translation_index:
            self._active_translation_index = -1
            if (
                not self._selection_changed_during_translation
                or index == self._current_index
            ):
                self._status = "ERROR"
                self._current_translation = message
                self.statusChanged.emit(self._status)
                self.translationUpdated.emit(self._current_translation)
        self._translation_progress = 0
        self.translationProgressChanged.emit(0)
        self._set_engine_status("Error")
        self.translationFailed.emit(index, message)

    @Slot(int, str, result=bool)
    def acceptTranslation(self, index, final_text):
        subtitles = self._subtitle_model.get_all_data()
        if not (0 <= index < len(subtitles)):
            return False

        original = subtitles[index].get("original", "").strip()
        clean_text = final_text.strip()
        
        if not clean_text:
            self.notify.emit("ERROR", "Lỗi: Không thể duyệt bản dịch trống!")
            return False
        if clean_text == original:
            self.notify.emit("ERROR", "Lỗi: Bản dịch không được trùng khớp y hệt văn bản gốc!")
            return False

        self._subtitle_model.update_translation(index, final_text, "ACCEPTED")
        if self.translation_memory is not None and original:
            self.translation_memory.add(original, clean_text)
        self.notify.emit("SUCCESS", f"Đã duyệt và đồng bộ câu #{index + 1} sang Timeline")

        # Xóa câu đã duyệt khỏi hàng đợi CAT Studio theo yêu cầu của người dùng
        self._subtitle_model.remove_subtitle(index)

        # Tự động chọn câu tiếp theo trong hàng đợi
        remaining = self._subtitle_model.rowCount()
        if remaining > 0:
            next_idx = min(index, remaining - 1)
            self.loadSubtitle(next_idx)
        else:
            self.loadSubtitle(-1)
        return True

    @staticmethod
    def _clean_translated_text(text: str) -> str:
        clean_text = (text or "").strip()
        if "</think>" in clean_text:
            clean_text = clean_text.split("</think>", 1)[1].strip()
        if "<think>" in clean_text:
            clean_text = clean_text.split("<think>", 1)[0].strip()

        # Cát bỏ Prompt Echo nếu model lặp lại prompt
        if "--- CURRENT SUBTITLE" in clean_text or "--- current subtitle" in clean_text:
            out_match = re.search(r'(?:---\s*Output[^\n]*\n|Translation:\s*\n?)(.*)', clean_text, re.DOTALL | re.IGNORECASE)
            if out_match:
                clean_text = out_match.group(1).strip()

        # Chặn độc thoại suy luận thô
        if "So final output:" in clean_text or "Final output:" in clean_text:
            clean_text = re.split(r'(?:So final output:|Final output:)', clean_text, flags=re.IGNORECASE)[-1].strip()

        clean_text = re.split(
            r'(?im)(?:^\s*[-*•]?\s*|\n\s*[-*•]?\s*)(?:\[?\s*(?:TỪ GỐC|Tu goc|Từ gốc|VOCAB|Vocabulary|Thuật ngữ)\s*\]?|Từ gốc\s*->|Tu goc\s*->|从根源\s*->)',
            clean_text
        )[0].strip()
        clean_text = re.sub(r'(?im)\n+\s*\[\s*(?:TỪ|TU|VOCAB|Thuật ngữ).*$', '', clean_text).strip()
        clean_text = re.sub(r'^\[Line \d+\]:\s*', '', clean_text, flags=re.IGNORECASE).strip()
        clean_text = re.sub(r'(?i)^\s*[*_]*(?:Translation|Bản dịch|Direct translation)[:*_]*\s*', '', clean_text).strip()
        clean_text = re.split(
            r'(?i)(?:(?:Either\s+(?:this|switch)|Given\s+the|Switch\s+to)\b|Note:|Explanation:|(?:cuối cùng,?\s*)?(?:nếu bạn có thể cho tôi biết|cho tôi biết thêm về ngữ cảnh))', 
            clean_text
        )[0].strip()
        clean_text = re.sub(r'(?im)^(?:cuối cùng,?\s*)?nếu bạn có thể cho tôi biết thêm.*$', '', clean_text).strip()
        clean_text = re.sub(r'(?i)\n*cuối cùng,?\s*$', '', clean_text).strip()
        return clean_text.strip('"\'')

    @Slot(int, str, str)
    @Slot(int, str)
    def requestAlternativeTranslation(self, index: int, source_lang: str, style_mode: str = "CREATIVE"):
        if index < 0 or index >= len(self._subtitle_model.get_all_data()):
            return
        # AUD-CONCUR-001: Khóa kiểm tra bận liên luồng toàn bộ worker LLM
        if self.is_busy():
            return

        if not source_lang or (source_lang == "English" and getattr(self, "_current_source_language", "English") != "English"):
            source_lang = self._current_source_language

        subtitles = self._subtitle_model.get_all_data()
        prev_ctx, current, next_ctx = ContextEngine.get_context(subtitles, index)

        enriched_glossary_hits = []
        if self.glossary:
            for hit in self.glossary.match(current, word_boundary=True):
                entry = self.glossary.get(hit.source_term)
                forbidden = entry.forbidden_alternatives if entry else ()
                enriched_glossary_hits.append((hit, forbidden))

        entity_hits = self.entities.match(current, word_boundary=True) if self.entities else ()
        active_pronoun = getattr(self._project_controller, "activePronounPair", "") if self._project_controller else ""
        is_ja = getattr(self._project_controller, "isJaOrigin", False) if self._project_controller else False
        story_summary = getattr(self._project_controller, "storySummary", "") if self._project_controller else ""
        target_lang = "Vietnamese"

        model_name = (self.hardware_profile.get("model_name") or "").lower()
        if "gemma" in model_name:
            model_family = "gemma"
        elif "llama" in model_name:
            model_family = "llama"
        elif "deepseek" in model_name:
            model_family = "deepseek"
        else:
            model_family = "qwen"

        profile = dict(self.hardware_profile)
        if style_mode == "CREATIVE":
            profile["temperature"] = 0.7
            style_instruction = "Lưu ý phong cách: Dịch thật phóng khoáng, giàu cảm xúc, tự nhiên theo khẩu ngữ tiếng Việt."
        else:
            profile["temperature"] = 0.2
            style_instruction = "Lưu ý phong cách: Dịch bám sát từng từ ngữ gốc (literal), cấu trúc nghiêm ngặt và chuẩn xác."

        active_archetype = (
            getattr(self._project_controller, "activeArchetype", "")
            if self._project_controller
            else ""
        )
        prompt = PromptBuilder.build(
            story_summary,
            source_lang,
            target_lang,
            prev_ctx,
            current,
            next_ctx,
            glossary_hits=tuple(enriched_glossary_hits),
            entity_hits=tuple(entity_hits),
            active_pronoun_pair=active_pronoun,
            is_ja_origin=is_ja,
            model_family=model_family,
            style_instruction=style_instruction,
            archetype=active_archetype,
        )
        self.alternativeTranslationLoading.emit(True)

        self._safe_cleanup_worker("alt_worker")
        if hasattr(self._worker_factory, "create_worker"):
            self.alt_worker = self._worker_factory.create_worker(index, prompt, profile)
        else:
            self.alt_worker = self._worker_factory(index, prompt, profile)

        def _on_alt_finished(idx, text, sm=style_mode):
            clean = self._clean_translated_text(text)
            self.alternativeTranslationLoading.emit(False)
            self.alternativeTranslationReady.emit(idx, clean, sm)

        def _on_alt_error(idx, err):
            self.alternativeTranslationLoading.emit(False)
            self.alternativeTranslationReady.emit(idx, f"Lỗi: {err}", style_mode)

        self.alt_worker.finished.connect(_on_alt_finished)
        self.alt_worker.error.connect(_on_alt_error)
        self.alt_worker.start()

    @Slot(int, str)
    def applyAlternativeTranslation(self, index: int, text: str):
        if 0 <= index < len(self._subtitle_model.get_all_data()):
            self._subtitle_model.update_translation(index, text, "EDITED")
            if index == self._current_index:
                self._current_translation = text
                self._status = "EDITED"
                self.translationUpdated.emit(text)
                self.statusChanged.emit(self._status)

    @Slot(int)
    def extractTermsForSubtitle(self, index: int):
        """Dành cho câu đã có bản dịch sẵn (như khi mở file cũ): chạy phân tích nhanh để bóc tách từ gốc."""
        subtitles = self._subtitle_model.get_all_data()
        if not (0 <= index < len(subtitles)):
            return
        sub = subtitles[index]
        original = (sub.get("original") or "").strip()
        translation = (sub.get("translation") or "").strip()
        if not original or not translation:
            return

        # Nếu câu đã có sẵn auto_terms, kích hoạt hiển thị ngay
        if sub.get("auto_terms"):
            self.appliedTermsChanged.emit()
            return

        # Kiểm tra nếu translation chứa sẵn khối [TỪ GỐC]
        inline_terms = TranslationWorker.extract_auto_terms(translation)
        if inline_terms:
            sub["auto_terms"] = inline_terms
            self.appliedTermsChanged.emit()
            return

        # AUD-CONCUR-001: Khóa kiểm tra bận liên luồng toàn bộ worker LLM
        if self.is_busy():
            return

        source_lang = "Japanese" if getattr(self._project_controller, "isJaOrigin", False) else "English"
        target_lang = "Vietnamese"
        model_name = (self.hardware_profile.get("model_name") or "").lower()
        model_family = "gemma" if "gemma" in model_name else ("llama" if "llama" in model_name else ("deepseek" if "deepseek" in model_name else "qwen"))

        prompt = PromptBuilder.build_alignment(
            source_sub=original,
            translated_sub=translation,
            source_lang=source_lang,
            target_lang=target_lang,
            model_family=model_family,
        )

        profile = dict(self.hardware_profile)
        profile["temperature"] = 0.1

        if hasattr(self._worker_factory, "create_worker"):
            worker = self._worker_factory.create_worker(index, prompt, profile)
        else:
            worker = self._worker_factory(index, prompt, profile)

        self._extract_worker = worker

        def _on_extracted(idx, text):
            terms = getattr(worker, "extracted_terms", None)
            if not terms:
                terms = TranslationWorker.extract_auto_terms(text)
            if not terms and text:
                terms = TranslationWorker.extract_auto_terms("[TỪ GỐC]\n" + text)
            if 0 <= idx < len(subtitles) and terms:
                subtitles[idx]["auto_terms"] = terms
                if idx == self._current_index:
                    self.appliedTermsChanged.emit()

        if hasattr(worker, "termsExtracted"):
            worker.termsExtracted.connect(lambda idx, t: _on_extracted(idx, ""))
        worker.finished.connect(_on_extracted)
        # AUD-MEM-001: Thu hồi C++ QThread an toàn khi hoàn tất
        if hasattr(worker, "deleteLater"):
            worker.finished.connect(worker.deleteLater)
        worker.start()

    @Slot(str, str, result=bool)
    def pinTermToGlossary(self, source_term: str, target_term: str) -> bool:
        """Ghim thuật ngữ vào Glossary của dự án vĩnh viễn (1-click)."""
        src = (source_term or "").strip()
        tgt = (target_term or "").strip()
        if not src or not tgt:
            return False

        if self._project_controller and hasattr(self._project_controller, "addManualGlossaryTerm"):
            ok = self._project_controller.addManualGlossaryTerm(src, tgt)
            if ok:
                self.appliedTermsChanged.emit()
                self.notify.emit("SUCCESS", f"Đã ghim '{src}' ➔ '{tgt}' vào Thuật ngữ dự án.")
                return True
        elif self.glossary:
            self.glossary.add(src, tgt, (), is_auto=False)
            self.appliedTermsChanged.emit()
            self.notify.emit("SUCCESS", f"Đã ghim '{src}' ➔ '{tgt}' vào Thuật ngữ.")
            return True
        return False

    @Slot(str, result=bool)
    def unpinTermFromGlossary(self, source_term: str) -> bool:
        """Bỏ ghim thuật ngữ khỏi Glossary của dự án (1-click)."""
        src = (source_term or "").strip()
        if not src:
            return False
        if self._project_controller and hasattr(self._project_controller, "removeGlossaryTerm"):
            ok = self._project_controller.removeGlossaryTerm(src)
            if ok:
                self.appliedTermsChanged.emit()
                return True
        elif self.glossary:
            if self.glossary.get(src) is not None:
                self.glossary.remove(src)
                self.appliedTermsChanged.emit()
                self.notify.emit("SUCCESS", f"Đã bỏ ghim thuật ngữ: '{src}'")
                return True
        return False

