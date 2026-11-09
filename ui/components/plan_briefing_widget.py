from typing import Optional, Dict, Any, List
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
)

from core.agent.models import AgentTaskPlan, AgentStep


class PlanBriefingCardWidget(QWidget):
    """
    Thẻ tóm tắt kế hoạch dự kiến tại Cổng 1 (Plan Briefing Card).
    Bảo đảm Strict Gate Isolation: Chỉ tóm tắt Mục tiêu, Chiến lược,
    Tham số dự kiến và Cam kết an toàn; Tuyệt đối KHÔNG làm lộ kết quả đầu ra.
    """

    def __init__(self, plan: AgentTaskPlan, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("plan_briefing_card")
        self.plan = plan
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.setStyleSheet("""
            QWidget#plan_briefing_card {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
            }
        """)

        # 1. Header
        header_box = QHBoxLayout()
        header_box.setSpacing(6)
        lbl_title = QLabel("📋 <strong>KẾ HOẠCH DỰ KIẾN (CỔNG 1)</strong>", self)
        lbl_title.setStyleSheet("color: #38bdf8; font-size: 11px; background: transparent;")
        header_box.addWidget(lbl_title)
        header_box.addStretch()

        step_count = len(self.plan.steps) if self.plan and self.plan.steps else 1
        lbl_badge = QLabel(f" {step_count} BƯỚC THỰC THI ", self)
        lbl_badge.setStyleSheet("""
            background: #1e293b;
            color: #94a3b8;
            font-size: 9px;
            font-weight: bold;
            border: 1px solid #334155;
            border-radius: 3px;
            padding: 2px 4px;
        """)
        header_box.addWidget(lbl_badge)
        layout.addLayout(header_box)

        # 2. Objective
        prompt_text = self.plan.prompt if self.plan and self.plan.prompt else "Thực thi tác vụ theo yêu cầu"
        lbl_obj = QLabel(f"🎯 <strong>Mục tiêu:</strong> {prompt_text}", self)
        lbl_obj.setStyleSheet("color: #e2e8f0; font-size: 10px; background: transparent;")
        lbl_obj.setWordWrap(True)
        layout.addWidget(lbl_obj)

        # 3. Strategy & Tools
        strat_box = QVBoxLayout()
        strat_box.setSpacing(4)
        lbl_strat_title = QLabel("🛠️ <strong>Chiến lược & Công cụ điều phối:</strong>", self)
        lbl_strat_title.setStyleSheet("color: #94a3b8; font-size: 10px; background: transparent;")
        strat_box.addWidget(lbl_strat_title)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)

        tools_used = set()
        for step in (self.plan.steps if self.plan else []):
            tools_used.add(step.tool_name)

        strategy_labels: List[str] = []
        if "create_timing" in tools_used:
            strategy_labels.extend(["VAD CFG-9 (Anime JA)", "PyAV 16kHz Windowing"])
        if "apply_subtitle_style" in tools_used:
            strategy_labels.append("Subtitle Styler (Tương phản cao)")
        if "adjust_subtitle_bounds" in tools_used:
            strategy_labels.extend(["Bounds Adjuster", "Overlap Guard"])
        if "shift_subtitles" in tools_used:
            strategy_labels.extend(["Timeline Shifter", "Kẹp biên >= 0ms"])
        if "rescan_subtitles" in tools_used:
            strategy_labels.append("Rescan Engine")
        if "run_asr" in tools_used:
            strategy_labels.append("Faster-Whisper ASR")
        if not strategy_labels:
            strategy_labels.append("Safe Tool Dispatcher")

        for s_lbl in strategy_labels:
            chip = QFrame(self)
            chip.setStyleSheet("background: #1e293b; border: 1px solid #334155; border-radius: 3px;")
            c_l = QHBoxLayout(chip)
            c_l.setContentsMargins(5, 2, 5, 2)
            lbl = QLabel(s_lbl, chip)
            lbl.setStyleSheet("color: #38bdf8; font-size: 9px; background: transparent; border: none;")
            c_l.addWidget(lbl)
            chips_row.addWidget(chip)
        chips_row.addStretch()
        strat_box.addLayout(chips_row)
        layout.addLayout(strat_box)

        # 4. Target Parameters
        primary_step = self.plan.steps[0] if (self.plan and self.plan.steps) else None
        args = primary_step.tool_args if primary_step else {}

        if args:
            param_box = QVBoxLayout()
            param_box.setSpacing(4)
            lbl_p_title = QLabel("⚙️ <strong>Thông số dự kiến áp dụng:</strong>", self)
            lbl_p_title.setStyleSheet("color: #94a3b8; font-size: 10px; background: transparent;")
            param_box.addWidget(lbl_p_title)

            p_chips_row = QHBoxLayout()
            p_chips_row.setSpacing(6)
            for k, v in list(args.items())[:5]:
                if k in ("segments", "video_path", "preview_segments"):
                    continue
                p_chip = QFrame(self)
                p_chip.setStyleSheet("background: #1e293b; border: 1px solid #334155; border-radius: 3px;")
                p_l = QHBoxLayout(p_chip)
                p_l.setContentsMargins(5, 2, 5, 2)
                lbl_val = QLabel(f"{k}: {v}", p_chip)
                lbl_val.setStyleSheet("color: #cbd5e1; font-size: 9px; background: transparent; border: none;")
                p_l.addWidget(lbl_val)
                p_chips_row.addWidget(p_chip)
            p_chips_row.addStretch()
            param_box.addLayout(p_chips_row)
            layout.addLayout(param_box)

        # 5. Safety Assurance
        safety_box = QFrame(self)
        safety_box.setStyleSheet("background: rgba(30, 41, 59, 0.5); border: 1px dashed #334155; border-radius: 4px;")
        s_l = QVBoxLayout(safety_box)
        s_l.setContentsMargins(6, 6, 6, 6)
        s_l.setSpacing(2)

        lbl_safe = QLabel("🛡️ <strong>Cam kết an toàn:</strong> Snapshot sao lưu tự động trước khi chạy; hỗ trợ Redo/Rollback 100%.", safety_box)
        lbl_safe.setStyleSheet("color: #4ade80; font-size: 9px; background: transparent; border: none;")
        lbl_safe.setWordWrap(True)
        s_l.addWidget(lbl_safe)

        lbl_hint = QLabel("💡 <em>Kết quả thực tế sẽ được hiển thị đầy đủ để bạn nghiệm thu và chỉnh sửa trực tiếp sau khi bấm Duyệt và tác vụ chạy xong.</em>", safety_box)
        lbl_hint.setStyleSheet("color: #94a3b8; font-size: 9px; background: transparent; border: none;")
        lbl_hint.setWordWrap(True)
        s_l.addWidget(lbl_hint)

        layout.addWidget(safety_box)
