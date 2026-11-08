import logging
import re
import time
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QObject, Signal

from core.agent.models import (
    AgentStep,
    AgentTaskPlan,
    ChatMessage,
    StepStatus,
    AgentContextLedger,
)
from core.agent.agent_tool_registry import AgentToolRegistry
from core.agent.multi_provider_client import MultiProviderLLMClient, ProviderConfig
from core.agent.snapshot_manager import SnapshotManager

logger = logging.getLogger(__name__)


class AgentCopilotController(QObject):
    """
    Human-in-the-Loop State Machine Controller for AI Agent Copilot.
    Governs plan proposal, approval gates, task execution, result reporting,
    and rollback checkpoints.
    """

    plan_ready = Signal(object)  # (AgentTaskPlan)
    step_started = Signal(int, object)  # (step_index, AgentStep)
    step_completed = Signal(int, object, dict)  # (step_index, AgentStep, result_dict)
    step_failed = Signal(int, object, str)  # (step_index, AgentStep, error_msg)
    plan_completed = Signal(object)  # (AgentTaskPlan)
    chat_message_added = Signal(object)  # (ChatMessage)
    notification_requested = Signal(str)  # (notification_text)

    def __init__(
        self,
        tool_registry: Optional[AgentToolRegistry] = None,
        llm_client: Optional[MultiProviderLLMClient] = None,
        snapshot_manager: Optional[SnapshotManager] = None,
        context_ledger: Optional[AgentContextLedger] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.tool_registry = tool_registry or AgentToolRegistry()
        if not self.tool_registry.has_tool("create_timing"):
            self.tool_registry.register_default_tools()
        self._active_segments: List[Dict[str, Any]] = []
        self.llm_client = llm_client or MultiProviderLLMClient()
        self.snapshot_manager = snapshot_manager
        self.context_ledger = context_ledger or AgentContextLedger()

        self.chat_history: List[ChatMessage] = []
        self.active_plan: Optional[AgentTaskPlan] = None
        self._waiting_plan_approval: bool = False
        self._waiting_task_approval: bool = False
        self._last_pre_task_snapshot_id: Optional[str] = None
        self._last_step_result: Optional[Dict[str, Any]] = None

    @property
    def current_step_index(self) -> int:
        return self.active_plan.current_step_index if self.active_plan else 0

    def is_waiting_plan_approval(self) -> bool:
        return self._waiting_plan_approval

    def is_waiting_task_approval(self) -> bool:
        return self._waiting_task_approval

    def is_plan_completed(self) -> bool:
        return bool(self.active_plan and self.active_plan.status == StepStatus.COMPLETED)

    def submit_prompt(
        self,
        prompt: str,
        online_configs: Optional[List[ProviderConfig]] = None,
    ) -> AgentTaskPlan:
        # 1. Record user message
        user_msg = ChatMessage(role="user", content=prompt, timestamp=time.time())
        self.chat_history.append(user_msg)
        self.chat_message_added.emit(user_msg)

        # 2. Synthesize plan
        plan = self._synthesize_plan(prompt, online_configs)
        self.active_plan = plan
        self._waiting_plan_approval = True
        self._waiting_task_approval = False

        # 3. Record agent response
        summary_text = (
            f"Kế hoạch gồm {len(plan.steps)} bước đã sẵn sàng:\n"
            + "\n".join([f"[{i+1}] {s.title}" for i, s in enumerate(plan.steps)])
            + "\nMời bạn kiểm tra và duyệt kế hoạch để bắt đầu."
        )
        agent_msg = ChatMessage(role="assistant", content=summary_text, timestamp=time.time())
        self.chat_history.append(agent_msg)
        self.chat_message_added.emit(agent_msg)

        self.plan_ready.emit(plan)
        return plan

    def _synthesize_plan(
        self,
        prompt: str,
        online_configs: Optional[List[ProviderConfig]] = None,
    ) -> AgentTaskPlan:
        # Default smart heuristic decomposition if LLM does not return structured plan
        lower = prompt.lower()
        steps: List[AgentStep] = []

        # 1. Check Subtitle Timing Bounds (Micro-editing duration: đầu / cuối)
        is_duration = ("thời lượng" in lower or "mốc" in lower) and any(k in lower for k in ["đầu", "cuối"])
        if is_duration:
            d_start = 0
            d_end = 0
            m_s1 = re.search(r"(?:giảm|lùi|trừ|sớm)\s+(\d+)\s*ms\s*(?:ở\s+)?mốc\s*đầu", lower) or re.search(r"mốc\s*đầu\s*(?:giảm|lùi|trừ|sớm)\s+(\d+)\s*ms", lower)
            if m_s1:
                d_start = -int(m_s1.group(1))
            m_s2 = re.search(r"(?:tăng|tiến|cộng|muộn)\s+(\d+)\s*ms\s*(?:ở\s+)?mốc\s*đầu", lower) or re.search(r"mốc\s*đầu\s*(?:tăng|tiến|cộng|muộn)\s+(\d+)\s*ms", lower)
            if m_s2:
                d_start = int(m_s2.group(1))

            m_e1 = re.search(r"(?:tăng|tiến|cộng|thêm)\s+(\d+)\s*ms\s*(?:ở\s+)?mốc\s*cuối", lower) or re.search(r"mốc\s*cuối\s*(?:tăng|tiến|cộng|thêm)\s+(\d+)\s*ms", lower)
            if m_e1:
                d_end = int(m_e1.group(1))
            m_e2 = re.search(r"(?:giảm|lùi|trừ|bớt)\s+(\d+)\s*ms\s*(?:ở\s+)?mốc\s*cuối", lower) or re.search(r"mốc\s*cuối\s*(?:giảm|lùi|trừ|bớt)\s+(\d+)\s*ms", lower)
            if m_e2:
                d_end = -int(m_e2.group(1))

            steps.append(
                AgentStep(
                    id=f"step_{len(steps)+1}",
                    title=f"Điều chỉnh thời lượng phụ đề (Đầu: {d_start:+d}ms, Cuối: {d_end:+d}ms)",
                    tool_name="adjust_subtitle_bounds",
                    tool_args={"delta_start_ms": d_start, "delta_end_ms": d_end, "scope": "all"},
                )
            )

        # 2. Check Subtitle Time Shift (Micro-editing offset: lên / lùi)
        is_shift = any(k in lower for k in ["đưa", "dịch chuyển", "đẩy", "dời", "lùi", "tiến"]) and any(k in lower for k in ["sub", "phụ đề", "đoạn"])
        if is_shift and not is_duration:
            direction = -1 if any(k in lower for k in ["lùi", "xuống", "giảm", "trừ", "sớm"]) else 1
            m_num = re.search(r"(\d+(?:\.\d+)?)\s*(s|giây|ms)", lower)
            if m_num:
                val_s, unit = m_num.groups()
                val = float(val_s)
                ms = int(val * 1000) if unit in ("s", "giây") else int(val)
                offset = ms * direction
                steps.append(
                    AgentStep(
                        id=f"step_{len(steps)+1}",
                        title=f"Dịch chuyển thời gian phụ đề ({offset:+d}ms)",
                        tool_name="shift_subtitles",
                        tool_args={"offset_ms": offset, "scope": "all"},
                    )
                )

        # 3. Check Timing Creation (tạo timing N câu)
        if "tạo timing" in lower or ("timing" in lower and any(w in lower for w in ["tạo", "khởi tạo", "add"])):
            m_count = re.search(r"(\d+)\s*câu", lower)
            count = int(m_count.group(1)) if m_count else 5
            steps.append(
                AgentStep(
                    id=f"step_{len(steps)+1}",
                    title=f"Khởi tạo Timing {count} câu đầu",
                    tool_name="create_timing",
                    tool_args={"count": count},
                )
            )

        # 4. Check ASR Gen Sub (support N segments limit)
        elif any(w in lower for w in ["nhận diện", "gen sub", "asr", "whisper", "tạo sub"]):
            m_lim = re.search(r"(\d+)\s*câu", lower)
            limit = int(m_lim.group(1)) if m_lim else None
            title = f"ASR Gen Sub {limit} câu đầu (Faster-Whisper)" if limit else "ASR Gen Sub (Faster-Whisper)"
            args = {"language": self.context_ledger.source_lang or "auto"}
            if limit:
                args["limit"] = limit
            steps.append(
                AgentStep(
                    id=f"step_{len(steps)+1}",
                    title=title,
                    tool_name="run_asr",
                    tool_args=args,
                )
            )

        if any(w in lower for w in ["dịch", "translate", "cat", "tiếng việt", "tiếng hàn", "tiếng anh"]):
            target = "vi"
            if "hàn" in lower:
                target = "ko"
            elif "anh" in lower or "english" in lower:
                target = "en"
            elif "nhật" in lower or "japanese" in lower:
                target = "ja"
            self.context_ledger.target_lang = target
            steps.append(
                AgentStep(
                    id=f"step_{len(steps)+1}",
                    title=f"Dịch Phụ Đề Sang Tiếng {target.upper()} (CAT Studio)",
                    tool_name="translate_subtitles",
                    tool_args={"target_lang": target},
                )
            )

        if any(w in lower for w in ["style", "font", "màu", "viền", "vàng", "bóng đổ", "hiệu ứng"]):
            steps.append(
                AgentStep(
                    id=f"step_{len(steps)+1}",
                    title="Tinh Chỉnh Subtitle Style & Formatting",
                    tool_name="apply_subtitle_style",
                    tool_args={"font_name": "Arial", "primary_color": "#FFFF00"},
                )
            )

        if any(w in lower for w in ["hardsub", "mp4", "render", "xuất video", "burn"]):
            steps.append(
                AgentStep(
                    id=f"step_{len(steps)+1}",
                    title="Render Hardsub MP4 Video Hoàn Chỉnh",
                    tool_name="render_hardsub",
                    tool_args={"resolution": "1080p"},
                )
            )

        if not steps:
            # Fallback single step
            steps.append(
                AgentStep(
                    id="step_1",
                    title="Thực thi tác vụ tổng quát",
                    tool_name="process_general_task",
                    tool_args={"prompt": prompt},
                )
            )

        return AgentTaskPlan(prompt=prompt, steps=steps, current_step_index=0)

    def approve_plan(self) -> None:
        if not self.active_plan or not self.active_plan.steps:
            return
        self._waiting_plan_approval = False
        self._run_current_step()

    def _run_current_step(self) -> None:
        if not self.active_plan:
            return

        idx = self.active_plan.current_step_index
        step = self.active_plan.current_step()
        if not step:
            return

        step.status = StepStatus.RUNNING
        self.step_started.emit(idx, step)

        # 1. Take transactional pre-task snapshot for rollback
        if self.snapshot_manager:
            self._last_pre_task_snapshot_id = self.snapshot_manager.take_snapshot(f"pre_task_{step.id}")

        # 2. Execute tool
        args = dict(step.tool_args)
        if step.tool_name in ("adjust_subtitle_bounds", "shift_subtitles") and "segments" not in args:
            if not self._active_segments:
                from core.agent.agent_tool_registry import create_timing
                init_res = create_timing(count=5)
                self._active_segments = init_res.get("segments", [])
            args["segments"] = self._active_segments

        exec_res = self.tool_registry.safe_execute_tool(step.tool_name, args)

        if exec_res.get("success"):
            step.status = StepStatus.COMPLETED
            step.completed_at = time.time()
            step.result_summary = f"Hoàn thành {step.title}"
            res_dict = exec_res.get("result", {})
            if isinstance(res_dict, dict) and "segments" in res_dict:
                limit = args.get("limit")
                if limit and isinstance(res_dict["segments"], list):
                    res_dict["segments"] = res_dict["segments"][:limit]
                self._active_segments = res_dict["segments"]

            self._last_step_result = res_dict

            # PAUSE and WAIT for user approval
            self._waiting_task_approval = True

            report_msg = (
                f"✅ **Hoàn thành Task #{idx+1} ({step.title})**\n"
                f"Kết quả đã được cập nhật vào khung kiểm tra bên phải. Mời bạn kiểm tra/sửa đổi hoặc bấm Duyệt để tiếp tục."
            )
            chat_reply = ChatMessage(role="assistant", content=report_msg, timestamp=time.time())
            self.chat_history.append(chat_reply)
            self.chat_message_added.emit(chat_reply)

            self.step_completed.emit(idx, step, exec_res.get("result", {}))
            self.notification_requested.emit(f"Task #{idx+1} ({step.title}) hoàn tất! Đang chờ bạn duyệt.")
        else:
            step.status = StepStatus.FAILED
            err = exec_res.get("error", "Lỗi không xác định")
            step.error_message = err
            self._waiting_task_approval = False

            err_msg = ChatMessage(role="assistant", content=f"❌ Task #{idx+1} thất bại: {err}", timestamp=time.time())
            self.chat_history.append(err_msg)
            self.chat_message_added.emit(err_msg)

            self.step_failed.emit(idx, step, err)

    def approve_next_step(self) -> None:
        if not self.active_plan or not self._waiting_task_approval:
            return

        self._waiting_task_approval = False
        if self.active_plan.advance_step():
            self._run_current_step()
        else:
            self.active_plan.status = StepStatus.COMPLETED
            done_msg = ChatMessage(
                role="assistant",
                content="🎉 **Chúc mừng! Toàn bộ kế hoạch đã hoàn thành thành công.**",
                timestamp=time.time(),
            )
            self.chat_history.append(done_msg)
            self.chat_message_added.emit(done_msg)
            self.plan_completed.emit(self.active_plan)

    def request_task_revision(self, critique_text: str = "") -> None:
        if not self.active_plan:
            return

        # 1. Rollback to pre-task snapshot
        if self.snapshot_manager and self._last_pre_task_snapshot_id:
            restored = self.snapshot_manager.restore_snapshot(self._last_pre_task_snapshot_id)
            if restored:
                logger.info("Rolled back to snapshot %s", self._last_pre_task_snapshot_id)

        # 2. Record user critique
        if critique_text:
            user_msg = ChatMessage(role="user", content=critique_text, timestamp=time.time())
            self.chat_history.append(user_msg)
            self.chat_message_added.emit(user_msg)

        step = self.active_plan.current_step()
        if step:
            step.status = StepStatus.PENDING

        rollback_msg = ChatMessage(
            role="assistant",
            content=f"Đã khôi phục dữ liệu về trước Task #{self.current_step_index+1}. Bạn có thể chỉnh sửa tham số hoặc gửi lệnh mới.",
            timestamp=time.time(),
        )
        self.chat_history.append(rollback_msg)
        self.chat_message_added.emit(rollback_msg)
        self._waiting_task_approval = True
