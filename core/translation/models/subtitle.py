from PySide6.QtCore import Qt, QAbstractListModel, QModelIndex, Slot, Signal, Property, QByteArray
from core.translation.core.qa_engine import analyze_subtitle


class SubtitleStatus:
    PENDING = "PENDING"
    TRANSLATING = "TRANSLATING"
    TRANSLATED = "TRANSLATED"  # Sửa READY thành TRANSLATED
    EDITED = "EDITED"
    ACCEPTED = "ACCEPTED"
    ERROR = "ERROR"


class SubtitleModel(QAbstractListModel):
    progressStatsChanged = Signal()
    IndexRole = Qt.UserRole + 1
    StartTimeRole = Qt.UserRole + 2
    EndTimeRole = Qt.UserRole + 3
    OriginalRole = Qt.UserRole + 4
    TranslationRole = Qt.UserRole + 5
    StatusRole = Qt.UserRole + 6
    QaSeverityRole = Qt.UserRole + 7
    QaTooltipRole = Qt.UserRole + 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._subtitles = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._subtitles)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < self.rowCount()):
            return None

        sub = self._subtitles[index.row()]
        # Dùng .get() O(1) để tránh lỗi vỡ Binding và đảm bảo hiệu năng 60fps khi scroll
        if role == self.IndexRole:
            return sub.get("index")
        elif role == self.StartTimeRole:
            return sub.get("start_time")
        elif role == self.EndTimeRole:
            return sub.get("end_time")
        elif role == self.OriginalRole:
            return sub.get("original", "")
        elif role == self.TranslationRole:
            return sub.get("translation", "")
        elif role == self.StatusRole:
            return str(sub.get("status", "PENDING") or "PENDING").upper()
        elif role == self.QaSeverityRole:
            return sub.get("_qa_severity", "")
        elif role == self.QaTooltipRole:
            return sub.get("_qa_tooltip", "")
        return None

    def roleNames(self):
        return {
            self.IndexRole: b"subIndex",
            self.StartTimeRole: b"startTime",
            self.EndTimeRole: b"endTime",
            self.OriginalRole: b"originalText",
            self.TranslationRole: b"translationText",
            self.StatusRole: b"status",
            self.QaSeverityRole: b"qaSeverity",
            self.QaTooltipRole: b"qaTooltip",
        }

    def load_data(self, data_list):
        for sub in data_list:
            self._normalize_translation_state(sub)
            self._update_item_qa(sub)
        self.beginResetModel()
        self._subtitles = data_list
        self.endResetModel()
        self.progressStatsChanged.emit()

    def append_data(self, new_data_list):
        if not new_data_list:
            return
        start_row = len(self._subtitles)
        end_row = start_row + len(new_data_list) - 1

        last_index = self._subtitles[-1]["index"] if self._subtitles else 0
        for i, sub in enumerate(new_data_list):
            sub["index"] = last_index + i + 1
            self._normalize_translation_state(sub)
            self._update_item_qa(sub)

        self.beginInsertRows(QModelIndex(), start_row, end_row)
        self._subtitles.extend(new_data_list)
        self.endInsertRows()
        self.progressStatsChanged.emit()

    @Slot(int, result=bool)
    def remove_subtitle(self, index: int) -> bool:
        """Xóa 1 subtitle khỏi danh sách CAT Studio sau khi đã được duyệt."""
        if 0 <= index < len(self._subtitles):
            self.beginRemoveRows(QModelIndex(), index, index)
            self._subtitles.pop(index)
            self.endRemoveRows()
            self.progressStatsChanged.emit()
            return True
        return False

    @Slot(result="QVariantList")
    def get_all_data(self):
        """Trả về toàn bộ danh sách subtitle để Context Engine và QML xử lý"""
        for sub in self._subtitles:
            self._normalize_translation_state(sub)
        return self._subtitles

    @Slot(int, result="QVariantMap")
    def get_item(self, row: int) -> dict:
        if 0 <= row < len(self._subtitles):
            self._normalize_translation_state(self._subtitles[row])
            return self._subtitles[row]
        return {}

    def get_qa_summary(self) -> dict:
        """Thống kê tổng số lỗi và cảnh báo QA trên toàn bộ project."""
        total_errors = sum(1 for sub in self._subtitles if sub.get("_qa_severity") == "ERROR")
        total_warnings = sum(1 for sub in self._subtitles if sub.get("_qa_severity") == "WARNING")
        return {"total_errors": total_errors, "total_warnings": total_warnings}

    @Property("QVariantMap", notify=progressStatsChanged)
    def progressStats(self) -> dict:
        total = len(self._subtitles)
        if total == 0:
            return {
                "total": 0,
                "accepted": 0,
                "translated": 0,
                "pending": 0,
                "error": 0,
                "qa_issues": 0,
                "accepted_pct": 0.0,
                "translated_pct": 0.0,
                "pending_pct": 0.0,
                "error_pct": 0.0,
            }

        accepted = 0
        translated = 0
        pending = 0
        error = 0
        qa_issues = 0

        for sub in self._subtitles:
            st = str(sub.get("status", "PENDING")).upper()
            qa = sub.get("_qa_severity", "")
            if qa == "ERROR":
                qa_issues += 1
            if st == "ACCEPTED":
                accepted += 1
            elif st in ("TRANSLATED", "EDITED"):
                translated += 1
            elif st == "ERROR":
                error += 1
            else:
                pending += 1

        return {
            "total": total,
            "accepted": accepted,
            "translated": translated,
            "pending": pending,
            "error": error,
            "qa_issues": qa_issues,
            "accepted_pct": round(accepted / total * 100, 1),
            "translated_pct": round(translated / total * 100, 1),
            "pending_pct": round(pending / total * 100, 1),
            "error_pct": round((error + qa_issues) / total * 100, 1),
        }

    @staticmethod
    def _update_item_qa(sub):
        """Tính toán trước kết quả QA và lưu vào dict item O(1)."""
        issues = analyze_subtitle(
            sub.get("start_time", 0),
            sub.get("end_time", 0),
            sub.get("original", ""),
            sub.get("translation", ""),
        )
        if not issues:
            sub["_qa_severity"] = ""
            sub["_qa_tooltip"] = ""
        else:
            has_error = any(i.severity == "ERROR" for i in issues)
            sub["_qa_severity"] = "ERROR" if has_error else "WARNING"
            sub["_qa_tooltip"] = "\n".join(f"• {i.message}" for i in issues)

    VALID_CAT_STATUSES = {"PENDING", "TRANSLATING", "TRANSLATED", "EDITED", "ACCEPTED", "ERROR"}

    @classmethod
    def _normalize_translation_state(cls, sub):
        status = str(sub.get("status", "PENDING") or "PENDING").strip().upper()
        if status not in cls.VALID_CAT_STATUSES:
            translation = str(sub.get("translation", "") or "").strip()
            status = "TRANSLATED" if translation else "PENDING"
        sub["status"] = status
        translation = str(sub.get("translation", "") or "")
        if status in {"TRANSLATED", "EDITED", "ACCEPTED"} and not translation.strip():
            sub["translation"] = "Lỗi: Bản dịch rỗng."
            sub["status"] = "ERROR"

    def update_translation(self, row_index, translation_text, status, original_text=None):
        """Cập nhật bản dịch và trạng thái, sau đó báo cho QML vẽ lại"""
        if 0 <= row_index < len(self._subtitles):
            # 1. Cập nhật dữ liệu trong bộ nhớ Python
            if original_text is not None:
                self._subtitles[row_index]["original"] = original_text
            self._subtitles[row_index]["translation"] = translation_text
            self._subtitles[row_index]["status"] = status
            self._normalize_translation_state(self._subtitles[row_index])
            self._update_item_qa(self._subtitles[row_index])
            
            # 2. Tạo index và ÉP QML CẬP NHẬT CHÍNH XÁC CÁC BIẾN NÀY (bao gồm cả OriginalRole)
            q_index = self.createIndex(row_index, 0)
            self.dataChanged.emit(
                q_index,
                q_index,
                [
                    self.OriginalRole,
                    self.TranslationRole,
                    self.StatusRole,
                    self.QaSeverityRole,
                    self.QaTooltipRole,
                ],
            )
            self.progressStatsChanged.emit()



    @Slot(int, "QVariantMap", "QVariantMap", result=bool)
    def split_subtitle(self, row_idx: int, seg1_data: dict, seg2_data: dict) -> bool:
        """Tách 1 dòng phụ đề thành 2 dòng nguyên tử bằng beginInsertRows."""
        if not (0 <= row_idx < len(self._subtitles)):
            return False
        self._subtitles[row_idx].update(seg1_data)
        self._normalize_translation_state(self._subtitles[row_idx])
        self._update_item_qa(self._subtitles[row_idx])

        new_item = dict(seg2_data)
        self._normalize_translation_state(new_item)
        self._update_item_qa(new_item)
        self.beginInsertRows(QModelIndex(), row_idx + 1, row_idx + 1)
        self._subtitles.insert(row_idx + 1, new_item)
        self.endInsertRows()

        for i in range(row_idx, len(self._subtitles)):
            self._subtitles[i]["index"] = i + 1
            if "studio_index" in self._subtitles[i]:
                self._subtitles[i]["studio_index"] = i

        q_start = self.createIndex(row_idx, 0)
        q_end = self.createIndex(len(self._subtitles) - 1, 0)
        self.dataChanged.emit(q_start, q_end, [
            self.IndexRole,
            self.StartTimeRole,
            self.EndTimeRole,
            self.OriginalRole,
            self.TranslationRole,
            self.StatusRole,
            self.QaSeverityRole,
            self.QaTooltipRole,
        ])
        self.progressStatsChanged.emit()
        return True

    @Slot(int, "QVariantMap", result=bool)
    def undo_split_subtitle(self, row_idx: int, original_seg_data: dict) -> bool:
        """Hoàn tác việc tách: xóa câu 2 và phục hồi câu 1 bằng beginRemoveRows."""
        if not (0 <= row_idx < len(self._subtitles) - 1):
            return False
        self.beginRemoveRows(QModelIndex(), row_idx + 1, row_idx + 1)
        self._subtitles.pop(row_idx + 1)
        self.endRemoveRows()

        self._subtitles[row_idx].clear()
        self._subtitles[row_idx].update(original_seg_data)
        self._normalize_translation_state(self._subtitles[row_idx])
        self._update_item_qa(self._subtitles[row_idx])

        for i in range(row_idx, len(self._subtitles)):
            self._subtitles[i]["index"] = i + 1
            if "studio_index" in self._subtitles[i]:
                self._subtitles[i]["studio_index"] = i

        q_start = self.createIndex(row_idx, 0)
        q_end = self.createIndex(len(self._subtitles) - 1, 0)
        self.dataChanged.emit(q_start, q_end, [
            self.IndexRole,
            self.StartTimeRole,
            self.EndTimeRole,
            self.OriginalRole,
            self.TranslationRole,
            self.StatusRole,
            self.QaSeverityRole,
            self.QaTooltipRole,
        ])
        self.progressStatsChanged.emit()
        return True

    @Slot(int, "QVariantMap", result=bool)
    def merge_subtitles(self, row_idx: int, merged_data: dict) -> bool:
        """Gộp 2 dòng phụ đề thành 1 bằng beginRemoveRows."""
        if not (0 <= row_idx < len(self._subtitles) - 1):
            return False
        self.beginRemoveRows(QModelIndex(), row_idx + 1, row_idx + 1)
        self._subtitles.pop(row_idx + 1)
        self.endRemoveRows()

        self._subtitles[row_idx].clear()
        self._subtitles[row_idx].update(merged_data)
        self._normalize_translation_state(self._subtitles[row_idx])
        self._update_item_qa(self._subtitles[row_idx])

        for i in range(row_idx, len(self._subtitles)):
            self._subtitles[i]["index"] = i + 1
            if "studio_index" in self._subtitles[i]:
                self._subtitles[i]["studio_index"] = i

        q_start = self.createIndex(row_idx, 0)
        q_end = self.createIndex(len(self._subtitles) - 1, 0)
        self.dataChanged.emit(q_start, q_end, [
            self.IndexRole,
            self.StartTimeRole,
            self.EndTimeRole,
            self.OriginalRole,
            self.TranslationRole,
            self.StatusRole,
            self.QaSeverityRole,
            self.QaTooltipRole,
        ])
        self.progressStatsChanged.emit()
        return True

    @Slot(int, "QVariantMap", "QVariantMap", result=bool)
    def undo_merge_subtitles(self, row_idx: int, seg1_data: dict, seg2_data: dict) -> bool:
        """Hoàn tác việc gộp: phục hồi câu 1 và chèn lại câu 2 bằng beginInsertRows."""
        if not (0 <= row_idx < len(self._subtitles)):
            return False
        self._subtitles[row_idx].clear()
        self._subtitles[row_idx].update(seg1_data)
        self._normalize_translation_state(self._subtitles[row_idx])
        self._update_item_qa(self._subtitles[row_idx])

        new_item = dict(seg2_data)
        self._normalize_translation_state(new_item)
        self._update_item_qa(new_item)
        self.beginInsertRows(QModelIndex(), row_idx + 1, row_idx + 1)
        self._subtitles.insert(row_idx + 1, new_item)
        self.endInsertRows()

        for i in range(row_idx, len(self._subtitles)):
            self._subtitles[i]["index"] = i + 1
            if "studio_index" in self._subtitles[i]:
                self._subtitles[i]["studio_index"] = i

        q_start = self.createIndex(row_idx, 0)
        q_end = self.createIndex(len(self._subtitles) - 1, 0)
        self.dataChanged.emit(q_start, q_end, [
            self.IndexRole,
            self.StartTimeRole,
            self.EndTimeRole,
            self.OriginalRole,
            self.TranslationRole,
            self.StatusRole,
            self.QaSeverityRole,
            self.QaTooltipRole,
        ])
        self.progressStatsChanged.emit()
        return True


class FilteredSubtitleModel(QAbstractListModel):
    RawIndexRole = Qt.UserRole + 9

    filteredCountChanged = Signal()
    totalCountChanged = Signal()
    currentPageChanged = Signal()
    totalPagesChanged = Signal()
    pageSizeChanged = Signal()
    qaOnlyChanged = Signal()

    def __init__(self, source_model: SubtitleModel, parent=None):
        super().__init__(parent)
        self._source = source_model
        self._matching_indices = []
        self._page_indices = []
        self._search_query = ""
        self._status_filter = "ALL"
        self._time_filter_active = False
        self._filter_start_min = 0
        self._filter_end_min = 9999
        self._page_size = 0  # 0 = Tất cả câu
        self._current_page = 1
        self._total_pages = 1
        self._qa_only = False

        self._source.modelReset.connect(self._recompute_and_reset)
        self._source.rowsInserted.connect(self._recompute_and_reset)
        self._source.rowsRemoved.connect(self._recompute_and_reset)
        self._source.dataChanged.connect(self._on_source_data_changed)
        self._recompute_and_reset()

    def _recompute_and_reset(self):
        all_data = self._source.get_all_data()
        matching = []

        sq = self._search_query.strip().lower()
        cf = self._status_filter.strip().upper()
        tf = self._time_filter_active
        s_min = self._filter_start_min
        e_min = self._filter_end_min

        for i, sub in enumerate(all_data):
            # 1. Search text filter
            if sq:
                orig = str(sub.get("original", "")).lower()
                trans = str(sub.get("translation", "")).lower()
                if sq not in orig and sq not in trans:
                    continue

            # 2. Status filter
            if cf != "ALL":
                st = str(sub.get("status", "PENDING")).upper()
                if cf == "PENDING" and st not in ("PENDING", ""):
                    continue
                elif cf != "PENDING" and st != cf:
                    continue

            # QA filter
            if self._qa_only:
                qa = sub.get("_qa_severity", "")
                st = str(sub.get("status", "PENDING")).upper()
                if qa != "ERROR" and st != "ERROR":
                    continue

            # 3. Time filter (parse HH:MM from start_time)
            if tf:
                t_str = str(sub.get("start_time", ""))
                if len(t_str) >= 5:
                    try:
                        sub_m = int(t_str[:2]) * 60 + int(t_str[3:5])
                    except ValueError:
                        sub_m = 0
                else:
                    sub_m = 0
                if sub_m < s_min or sub_m > e_min:
                    continue

            matching.append(i)

        self._matching_indices = matching
        total_matching = len(matching)

        if self._page_size > 0:
            self._total_pages = max(1, (total_matching + self._page_size - 1) // self._page_size)
        else:
            self._total_pages = 1

        if self._current_page > self._total_pages:
            self._current_page = self._total_pages
        if self._current_page < 1:
            self._current_page = 1

        if self._page_size > 0 and total_matching > 0:
            start = (self._current_page - 1) * self._page_size
            end = start + self._page_size
            self._page_indices = matching[start:end]
        else:
            self._page_indices = matching

        self.beginResetModel()
        self.endResetModel()

        self.filteredCountChanged.emit()
        self.totalCountChanged.emit()
        self.currentPageChanged.emit()
        self.totalPagesChanged.emit()
        self.pageSizeChanged.emit()

    def _on_source_data_changed(self, top_left, bottom_right, roles):
        start_row = top_left.row()
        end_row = bottom_right.row()
        for raw_idx in range(start_row, end_row + 1):
            if raw_idx in self._page_indices:
                view_row = self._page_indices.index(raw_idx)
                q_idx = self.createIndex(view_row, 0)
                self.dataChanged.emit(q_idx, q_idx, roles)

    def rowCount(self, parent=QModelIndex()):
        return len(self._page_indices)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._page_indices)):
            return None
        raw_idx = self._page_indices[index.row()]
        if role == self.RawIndexRole:
            return raw_idx
        return self._source.data(self._source.index(raw_idx, 0), role)

    def roleNames(self):
        roles = dict(self._source.roleNames())
        roles[self.RawIndexRole] = b"rawIndex"
        return roles

    @Property(int, notify=filteredCountChanged)
    def filteredCount(self):
        return len(self._matching_indices)

    @Property(int, notify=totalCountChanged)
    def totalCount(self):
        return self._source.rowCount()

    @Property(int, notify=currentPageChanged)
    def currentPage(self):
        return self._current_page

    @Property(int, notify=totalPagesChanged)
    def totalPages(self):
        return self._total_pages

    @Property(int, notify=pageSizeChanged)
    def pageSize(self):
        return self._page_size

    @Property(bool, notify=qaOnlyChanged)
    def qaOnly(self) -> bool:
        return self._qa_only

    @Slot(bool)
    def setQaOnlyFilter(self, enabled: bool):
        if self._qa_only != enabled:
            self._qa_only = enabled
            self._current_page = 1
            self.qaOnlyChanged.emit()
            self._recompute_and_reset()

    @Property(bool, notify=currentPageChanged)
    def hasPrevPage(self):
        return self._current_page > 1

    @Property(bool, notify=currentPageChanged)
    def hasNextPage(self):
        return self._current_page < self._total_pages

    @Slot(str)
    def setSearchQuery(self, query: str):
        if self._search_query != query:
            self._search_query = query
            self._current_page = 1
            self._recompute_and_reset()

    @Slot(str)
    def setStatusFilter(self, status: str):
        if self._status_filter != status:
            self._status_filter = status
            self._current_page = 1
            self._recompute_and_reset()

    @Slot(bool, int, int)
    def setTimeFilter(self, active: bool, start_min: int, end_min: int):
        if (self._time_filter_active != active or
                self._filter_start_min != start_min or
                self._filter_end_min != end_min):
            self._time_filter_active = active
            self._filter_start_min = start_min
            self._filter_end_min = end_min
            self._current_page = 1
            self._recompute_and_reset()

    @Slot(int)
    def setPageSize(self, size: int):
        if self._page_size != size:
            self._page_size = size
            self._current_page = 1
            self._recompute_and_reset()

    @Slot(int)
    def setCurrentPage(self, page: int):
        if 1 <= page <= self._total_pages and self._current_page != page:
            self._current_page = page
            self._recompute_and_reset()

    @Slot()
    def nextPage(self):
        if self._current_page < self._total_pages:
            self.setCurrentPage(self._current_page + 1)

    @Slot()
    def prevPage(self):
        if self._current_page > 1:
            self.setCurrentPage(self._current_page - 1)

    @Slot(int, result=int)
    def getRawIndex(self, view_row: int) -> int:
        if 0 <= view_row < len(self._page_indices):
            return self._page_indices[view_row]
        return -1

    @Slot(int, result=int)
    def getViewIndex(self, raw_index: int) -> int:
        if raw_index in self._page_indices:
            return self._page_indices.index(raw_index)
        return -1

    @Slot(int, result=int)
    def ensureRawIndexVisible(self, raw_index: int) -> int:
        """Nếu raw_index thuộc danh sách khớp, chuyển trang nếu cần và trả về view index."""
        if raw_index in self._matching_indices:
            if self._page_size > 0:
                target_page = (self._matching_indices.index(raw_index) // self._page_size) + 1
                if target_page != self._current_page:
                    self.setCurrentPage(target_page)
            if raw_index in self._page_indices:
                return self._page_indices.index(raw_index)
        return -1


