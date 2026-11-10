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
from core.agent.reasoning_engine import DynamicReasoningEngine
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
    step_reverted = Signal(int, object, list)  # (step_index, AgentStep, reverted_segments)

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
        self._pre_task_segments: Optional[List[Dict[str, Any]]] = None
        self.reasoning_engine = DynamicReasoningEngine()
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

        # 3. Record agent response with dynamic CoT reasoning & anti-repetition
        active_count = len(self._active_segments) if self._active_segments else 0
        summary_text = self.reasoning_engine.synthesize_reasoning(
            prompt=prompt,
            plan=plan,
            context_ledger=self.context_ledger,
            active_segments_count=active_count,
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

        def _extract_sentence_indices(text: str) -> Optional[List[int]]:
            m_rng = re.search(r"từ\s+(?:câu|sub|phụ\s+đề)\s+(\d+)\s+đến\s+(?:(?:câu|sub|phụ\s+đề)\s+)?(\d+)", text) or re.search(r"(?:câu|sub|phụ\s+đề)\s+(\d+)\s+đến\s+(?:(?:câu|sub|phụ\s+đề)\s+)?(\d+)", text)
            if m_rng:
                raw_a, raw_b = int(m_rng.group(1)), int(m_rng.group(2))
                return list(range(min(raw_a, raw_b), max(raw_a, raw_b) + 1))
            m_first_n = re.search(r"(\d+)\s*(?:câu|sub|phụ\s+đề)\s*đầu", text)
            if m_first_n:
                return list(range(1, int(m_first_n.group(1)) + 1))
            pat = r"(?:câu|sub|phụ\s+đề)\s+(?:sub\s+|phụ\s+đề\s+|số\s+|thứ\s+)?(\d+(?:\s*(?:,|và|hoặc)\s*(?:(?:câu|sub|phụ\s+đề)\s+)?(?:số\s+|thứ\s+)?\d+)*)"
            m_multi = re.search(pat, text)
            if m_multi:
                nums = [int(x) for x in re.findall(r"\d+", m_multi.group(1))]
                if nums:
                    return sorted(list(set(nums)))
            return None

        # 1. Check Subtitle Timing Bounds (Micro-editing duration: đầu / cuối)
        is_duration = ("thời lượng" in lower or "mốc" in lower or "đầu" in lower or "cuối" in lower) and any(k in lower for k in ["mốc đầu", "mốc cuối", "đầu câu", "cuối câu", "mốc", "đầu", "cuối"])
        is_duration_action = False
        if is_duration and any(k in lower for k in ["đầu", "cuối"]):
            d_start = 0
            d_end = 0

            def _parse_delta(text: str, pos_key: str, dir_mult: int, words: list) -> int:
                if re.search(r"\d+\s*câu\s+đầu", text) and pos_key == "đầu" and not any(k in text for k in ["mốc đầu", "đầu câu"]):
                    return 0
                w_pat = "|".join(words)
                # Form 1: (tăng|giảm) [val] [unit] (ở|cho)? (mốc đầu|đầu câu)
                p1 = rf"(?:{w_pat})\s+(?:thêm\s+)?([+-]?\d+(?:\.\d+)?)\s*(s|giây|ms)?\s*(?:ở|cho)?\s*(?:mốc\s*{pos_key}|{pos_key}\s*câu|{pos_key})"
                # Form 2: (mốc đầu|đầu câu) (tăng|giảm) (thêm)? [val] [unit]
                p2 = rf"(?:mốc\s*{pos_key}|{pos_key}\s*câu|{pos_key})\s*(?:{w_pat})\s*(?:thêm\s+)?([+-]?\d+(?:\.\d+)?)\s*(s|giây|ms)?"
                # Form 3 (Vietnamese natural order): (giảm|tăng) [mốc đầu|mốc cuối] (dải câu / câu X)? (thêm|đi)? [val] [unit]
                sent_spec = r"(?:\s+(?:từ\s+câu\s+\d+\s+đến\s+(?:câu\s+)?\d+|câu\s+\d+\s+đến\s+(?:câu\s+)?\d+|câu\s+(?:số\s+|thứ\s+)?\d+(?:\s*(?:,|và|hoặc)\s*(?:câu\s+)?(?:số\s+|thứ\s+)?\d+)*|\d+\s*câu\s*đầu))?"
                p3 = rf"(?:{w_pat})\s+(?:ở\s+|cho\s+)?(?:mốc\s*{pos_key}|{pos_key}\s*câu|{pos_key}){sent_spec}\s*(?:thêm\s+|đi\s+|bớt\s+|lên\s+|xuống\s+)?([+-]?\d+(?:\.\d+)?)\s*(s|giây|ms)?"
                m = re.search(p1, text) or re.search(p2, text) or re.search(p3, text)
                if m:
                    val_str, unit = m.group(1), m.group(2)
                    val = float(val_str)
                    ms = int(val * 1000) if unit in ("s", "giây") else int(val)
                    return ms * dir_mult
                return 0

            # Mốc đầu: giảm/lùi/trừ/sớm (-1) vs tăng/tiến/cộng/thêm/muộn (+1)
            ds_neg = _parse_delta(lower, "đầu", -1, ["giảm", "lùi", "trừ", "sớm", "bớt"])
            ds_pos = _parse_delta(lower, "đầu", 1, ["tăng", "tiến", "cộng", "thêm", "muộn"])
            d_start = ds_neg if ds_neg != 0 else ds_pos

            # Mốc cuối: tăng/tiến/cộng/thêm (+1) vs giảm/lùi/trừ/bớt/sớm (-1)
            de_pos = _parse_delta(lower, "cuối", 1, ["tăng", "tiến", "cộng", "thêm", "muộn"])
            de_neg = _parse_delta(lower, "cuối", -1, ["giảm", "lùi", "trừ", "bớt", "sớm"])
            d_end = de_pos if de_pos != 0 else de_neg

            if d_start != 0 or d_end != 0 or "thời lượng" in lower:
                is_duration_action = True
                bound_indices = _extract_sentence_indices(lower)
                bound_args: Dict[str, Any] = {
                    "delta_start_ms": d_start,
                    "delta_end_ms": d_end,
                    "scope": "selected" if bound_indices else "all",
                }
                if bound_indices:
                    bound_args["segment_indices"] = bound_indices
                    title = f"Điều chỉnh thời lượng các câu {bound_indices} (Đầu: {d_start:+d}ms, Cuối: {d_end:+d}ms)"
                else:
                    title = f"Điều chỉnh thời lượng phụ đề (Đầu: {d_start:+d}ms, Cuối: {d_end:+d}ms)"

                steps.append(
                    AgentStep(
                        id=f"step_{len(steps)+1}",
                        title=title,
                        tool_name="adjust_subtitle_bounds",
                        tool_args=bound_args,
                    )
                )

        # 2. Check Subtitle Time Shift (Micro-editing offset: lên / lùi)
        time_unit_pattern = r"(?:[+-]?\d+(?:\.\d+)?\s*(?:giây|ms|miligiây|s\b)|\b(?:giây|ms|miligiây)\b)"
        has_time_unit = bool(re.search(time_unit_pattern, lower))
        has_shift_verb = any(k in lower for k in ["đưa", "dịch chuyển", "đẩy", "dời", "lùi", "tiến"])
        is_shift = (
            has_shift_verb
            or ("dịch" in lower and has_time_unit)
        ) and any(k in lower for k in ["sub", "phụ đề", "đoạn", "câu", "timing"])
        if is_shift and not is_duration_action:
            direction = -1 if any(k in lower for k in ["lùi", "xuống", "giảm", "trừ", "sớm"]) else 1
            matches = list(re.finditer(r"([+-]?\d+(?:\.\d+)?)\s*(giây|ms|miligiây|s\b)", lower))
            m_num = matches[-1] if matches else None
            if m_num:
                val_s, unit = m_num.groups()
                val = float(val_s)
                if val < 0:
                    direction = -1
                    val = abs(val)
                ms = int(val * 1000) if unit in ("s", "giây") else int(val)
                offset = ms * direction

                shift_indices = _extract_sentence_indices(lower)
                shift_args: Dict[str, Any] = {
                    "offset_ms": offset,
                    "scope": "selected" if shift_indices else "all",
                }
                if shift_indices:
                    shift_args["segment_indices"] = shift_indices
                    title = f"Dịch chuyển các câu {shift_indices} ({offset:+d}ms)"
                else:
                    title = f"Dịch chuyển thời gian phụ đề ({offset:+d}ms)"

                steps.append(
                    AgentStep(
                        id=f"step_{len(steps)+1}",
                        title=title,
                        tool_name="shift_subtitles",
                        tool_args=shift_args,
                    )
                )

        # 3. Check Timing Creation (tạo timing N câu - VAD Preset CFG-9 & Gate 1 Preview)
        preview_segments = None
        if "tạo timing" in lower or ("timing" in lower and any(w in lower for w in ["tạo", "khởi tạo", "add"])):
            m_count = re.search(r"(\d+)\s*câu", lower)
            count = int(m_count.group(1)) if m_count else 5

            start_offset_s = 0.0
            m_tc = re.search(r"từ\s+(\d{1,2}):(\d{2})", lower)
            if m_tc:
                start_offset_s = float(int(m_tc.group(1)) * 60 + int(m_tc.group(2)))
            else:
                m_sec = re.search(r"từ\s+(?:giây\s+)?(\d+(?:\.\d+)?)\s*(?:giây|s)?", lower)
                if m_sec:
                    start_offset_s = float(m_sec.group(1))

            vad_threshold = None
            m_th = re.search(r"(?:ngưỡng|threshold)\s*[:=]?\s*(\d+(?:\.\d+)?)", lower)
            if m_th:
                vad_threshold = float(m_th.group(1))

            min_silence_ms = None
            m_sil = re.search(r"(?:min_silence|im lặng tối thiểu)\s*[:=]?\s*(\d+)(?:\s*ms)?", lower)
            if m_sil:
                min_silence_ms = int(m_sil.group(1))

            video_path = self.context_ledger.video_path
            tool_args = {"count": count}
            if video_path:
                tool_args["video_path"] = video_path
            if start_offset_s > 0:
                tool_args["start_offset_s"] = start_offset_s
            if vad_threshold is not None:
                tool_args["vad_threshold"] = vad_threshold
            if min_silence_ms is not None:
                tool_args["min_silence_ms"] = min_silence_ms
            tool_args["preview_segments"] = None

            steps.append(
                AgentStep(
                    id=f"step_{len(steps)+1}",
                    title=f"Khởi tạo Timing {count} câu đầu",
                    tool_name="create_timing",
                    tool_args=tool_args,
                )
            )

        # 4. Check Subtitle Rescan ("quét lại", "rescan", "scan lại")
        elif any(w in lower for w in ["quét lại", "rescan", "scan lại"]):
            m_rng = re.search(r"từ\s+câu\s+(\d+)\s+đến\s+(?:câu\s+)?(\d+)", lower)
            m_time = re.search(r"từ\s+(?:giây\s+)?(\d+(?:\.\d+)?)(?:\s*s|\s*giây)?\s+đến\s+(?:giây\s+)?(\d+(?:\.\d+)?)(?:\s*s|\s*giây)?", lower)
            m_multi = re.search(
                r"câu\s+(?:số\s+|thứ\s+)?(\d+(?:\s*(?:,|và|hoặc)\s*(?:câu\s+)?(?:số\s+|thứ\s+)?\d+)*)",
                lower,
            )

            if m_rng:
                raw_a = int(m_rng.group(1))
                raw_b = int(m_rng.group(2))
                st_idx, en_idx = min(raw_a, raw_b), max(raw_a, raw_b)
                indices = list(range(st_idx, en_idx + 1))
                steps.append(
                    AgentStep(
                        id=f"step_{len(steps)+1}",
                        title=f"Quét lại phụ đề từ câu {st_idx} đến câu {en_idx}",
                        tool_name="rescan_subtitles",
                        tool_args={"scope": "range", "segment_indices": indices},
                    )
                )
            elif m_time:
                raw_s = float(m_time.group(1))
                raw_e = float(m_time.group(2))
                s_sec, e_sec = min(raw_s, raw_e), max(raw_s, raw_e)
                s_title = int(s_sec) if s_sec.is_integer() else s_sec
                e_title = int(e_sec) if e_sec.is_integer() else e_sec
                steps.append(
                    AgentStep(
                        id=f"step_{len(steps)+1}",
                        title=f"Quét lại phụ đề từ giây {s_title} đến giây {e_title}",
                        tool_name="rescan_subtitles",
                        tool_args={"scope": "time_interval", "start_ms": int(s_sec * 1000), "end_ms": int(e_sec * 1000)},
                    )
                )
            elif m_multi:
                nums = [int(x) for x in re.findall(r"\d+", m_multi.group(1))]
                if len(nums) > 1:
                    indices = sorted(list(set(nums)))
                    steps.append(
                        AgentStep(
                            id=f"step_{len(steps)+1}",
                            title=f"Quét lại phụ đề các câu: {', '.join(str(x) for x in indices)}",
                            tool_name="rescan_subtitles",
                            tool_args={"scope": "selected", "segment_indices": indices},
                        )
                    )
                elif len(nums) == 1:
                    s_idx = nums[0]
                    steps.append(
                        AgentStep(
                            id=f"step_{len(steps)+1}",
                            title=f"Quét lại phụ đề câu #{s_idx}",
                            tool_name="rescan_subtitles",
                            tool_args={"scope": "selected", "segment_indices": [s_idx]},
                        )
                    )
            else:
                steps.append(
                    AgentStep(
                        id=f"step_{len(steps)+1}",
                        title="Quét lại toàn bộ âm thanh phụ đề",
                        tool_name="rescan_subtitles",
                        tool_args={"scope": "all", "segment_indices": []},
                    )
                )

        # 5. Check ASR Gen Sub (odd sentence, range, or limit)
        elif any(w in lower for w in ["nhận diện", "gen sub", "asr", "whisper", "tạo sub"]):
            m_rng = re.search(r"từ\s+câu\s+(\d+)\s+đến\s+(?:câu\s+)?(\d+)", lower)
            m_multi = re.search(
                r"câu\s+(?:số\s+|thứ\s+)?(\d+(?:\s*(?:,|và|hoặc)\s*(?:câu\s+)?(?:số\s+|thứ\s+)?\d+)*)",
                lower,
            )
            m_lim = re.search(r"(\d+)\s*câu(?:\s*đầu)?", lower)

            args = {"language": self.context_ledger.source_lang or "auto"}
            if m_rng:
                raw_a = int(m_rng.group(1))
                raw_b = int(m_rng.group(2))
                st_idx, en_idx = min(raw_a, raw_b), max(raw_a, raw_b)
                indices = list(range(st_idx, en_idx + 1))
                args["indices"] = indices
                title = f"ASR Gen Sub từ câu {st_idx} đến câu {en_idx} (Faster-Whisper)"
            elif m_multi:
                nums = [int(x) for x in re.findall(r"\d+", m_multi.group(1))]
                if len(nums) > 1:
                    indices = sorted(list(set(nums)))
                    args["indices"] = indices
                    title = f"ASR Gen Sub các câu: {', '.join(str(x) for x in indices)} (Faster-Whisper)"
                elif len(nums) == 1:
                    idx = nums[0]
                    args["indices"] = [idx]
                    title = f"ASR Gen Sub câu #{idx} (Faster-Whisper)"
            elif m_lim:
                limit = int(m_lim.group(1))
                args["limit"] = limit
                title = f"ASR Gen Sub {limit} câu đầu (Faster-Whisper)"
            else:
                title = "ASR Gen Sub (Faster-Whisper)"

            steps.append(
                AgentStep(
                    id=f"step_{len(steps)+1}",
                    title=title,
                    tool_name="run_asr",
                    tool_args=args,
                )
            )

        is_trans = False
        if any(w in lower for w in ["translate", "cat", "tiếng việt", "tiếng hàn", "tiếng anh", "tiếng nhật", "sang tiếng"]):
            is_trans = True
        elif "dịch" in lower and not is_shift and not has_time_unit:
            is_trans = True
        elif ("dịch phụ đề" in lower or "dịch sub" in lower) and not has_time_unit:
            is_trans = True

        if is_trans:
            target = "vi"
            if "hàn" in lower:
                target = "ko"
            elif "anh" in lower or "english" in lower:
                target = "en"
            elif "nhật" in lower or "japanese" in lower:
                target = "ja"
            self.context_ledger.target_lang = target
            trans_indices = _extract_sentence_indices(lower)
            trans_args: Dict[str, Any] = {
                "target_lang": target,
                "scope": "selected" if trans_indices else "all",
            }
            if trans_indices:
                trans_args["segment_indices"] = trans_indices
                idx_str = f"các câu: {', '.join(str(x) for x in trans_indices)}"
                title = f"Dịch Phụ Đề {idx_str} Sang Tiếng {target.upper()} (CAT Studio)"
            else:
                title = f"Dịch Phụ Đề Sang Tiếng {target.upper()} (CAT Studio)"
            steps.append(
                AgentStep(
                    id=f"step_{len(steps)+1}",
                    title=title,
                    tool_name="translate_subtitles",
                    tool_args=trans_args,
                )
            )

        if any(w in lower for w in ["style", "font", "cỡ", "size", "màu", "viền", "bóng đổ", "shadow", "hiệu ứng"]) and not is_duration_action and not is_shift:
            color_map = {
                "vàng": "#FFFF00",
                "đỏ": "#FF0000",
                "trắng": "#FFFFFF",
                "đen": "#000000",
                "xanh lá": "#22C55E",
                "xanh dương": "#38BDF8",
                "xanh": "#38BDF8",
                "cam": "#F97316",
                "tím": "#A855F7",
                "hồng": "#EC4899",
                "xám": "#94A3B8",
            }
            font_name = None
            m_f = re.search(r"font\s+([A-Za-z0-9_-]+)", lower)
            if m_f:
                raw_font = m_f.group(1)
                font_name = "Roboto" if raw_font.lower() == "roboto" else raw_font.capitalize()
            elif "roboto" in lower:
                font_name = "Roboto"
            elif "arial" in lower:
                font_name = "Arial"
            else:
                font_name = "Arial"

            font_size = None
            m_sz = re.search(r"(?:cỡ(?:\s*chữ)?|size)\s*[:=]?\s*(\d+)", lower)
            if m_sz:
                font_size = int(m_sz.group(1))

            font_color = None
            m_hx = re.search(r"#([0-9a-fA-F]{6})", lower)
            if m_hx:
                font_color = f"#{m_hx.group(1).upper()}"
            else:
                for c_name, c_hex in color_map.items():
                    if f"chữ {c_name}" in lower or f"màu {c_name}" in lower:
                        font_color = c_hex
                        break
            if not font_color and "vàng" in lower:
                font_color = "#FFFF00"

            outline_color = None
            for c_name, c_hex in color_map.items():
                if f"viền {c_name}" in lower:
                    outline_color = c_hex
                    break

            outline_width = None
            m_ow = re.search(r"viền\s+(?:dày\s+)?(\d+)(?:\s*px)?", lower)
            if m_ow:
                outline_width = int(m_ow.group(1))

            shadow = None
            if "bóng đổ" in lower or "shadow" in lower:
                shadow = True

            style_args = {"font_name": font_name}
            if font_size is not None:
                style_args["font_size"] = font_size
            if font_color:
                style_args["font_color"] = font_color
            if outline_color:
                style_args["outline_color"] = outline_color
            if outline_width is not None:
                style_args["outline_width"] = outline_width
            if shadow is not None:
                style_args["shadow"] = shadow

            steps.append(
                AgentStep(
                    id=f"step_{len(steps)+1}",
                    title=f"Tinh Chỉnh Subtitle Style (Font: {font_name}, Cỡ: {font_size or 24})",
                    tool_name="apply_subtitle_style",
                    tool_args=style_args,
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

        return AgentTaskPlan(prompt=prompt, steps=steps, current_step_index=0, preview_segments=preview_segments)

    def approve_plan(self, preserved_segments: Optional[List[Dict[str, Any]]] = None) -> None:
        if not self.active_plan or not self.active_plan.steps:
            return
        self._waiting_plan_approval = False
        if preserved_segments and self.active_plan.steps:
            curr_step = self.active_plan.current_step()
            if curr_step and curr_step.tool_name == "create_timing":
                curr_step.tool_args["preserved_segments"] = preserved_segments
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
        import copy
        self._pre_task_segments = copy.deepcopy(self._active_segments)
        if self.snapshot_manager:
            self._last_pre_task_snapshot_id = self.snapshot_manager.take_snapshot(f"pre_task_{step.id}")

        # 2. Execute tool
        args = dict(step.tool_args)
        if step.tool_name == "create_timing" and "video_path" not in args and self.context_ledger.video_path:
            args["video_path"] = self.context_ledger.video_path
        if step.tool_name == "translate_subtitles" and "llm_client" not in args and getattr(self, "llm_client", None):
            args["llm_client"] = self.llm_client
        if step.tool_name in ("adjust_subtitle_bounds", "shift_subtitles", "rescan_subtitles", "run_asr", "apply_subtitle_style", "translate_subtitles", "render_hardsub") and "segments" not in args:
            if not self._active_segments:
                if step.tool_name != "apply_subtitle_style":
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
                self._active_segments = res_dict["segments"]

            self._last_step_result = res_dict

            # PAUSE and WAIT for user approval
            self._waiting_task_approval = True

            report_msg = self.reasoning_engine.synthesize_completion(
                step=step,
                result=res_dict,
                context_ledger=self.context_ledger,
                active_segments_count=len(self._active_segments),
            )
            chat_reply = ChatMessage(role="assistant", content=report_msg, timestamp=time.time())
            self.chat_history.append(chat_reply)
            self.chat_message_added.emit(chat_reply)

            self.step_completed.emit(idx, step, exec_res.get("result", {}))
            if step.tool_name != "process_general_task":
                self.notification_requested.emit(f"Task #{idx+1} ({step.title}) hoàn tất! Đang chờ bạn duyệt.")
            else:
                self.notification_requested.emit(f"Task #{idx+1}: Đã tiếp nhận yêu cầu.")
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
        curr_step = self.active_plan.current_step()
        if curr_step and curr_step.status == StepStatus.PENDING:
            self._run_current_step()
            return

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
        if not self.active_plan or self._waiting_plan_approval:
            return

        # 1. Rollback to pre-task snapshot
        import copy
        if self._pre_task_segments is not None:
            self._active_segments = copy.deepcopy(self._pre_task_segments)
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
        if step:
            self.step_reverted.emit(self.current_step_index, step, copy.deepcopy(self._active_segments))
