import re
from typing import Any, Dict, List, Optional
from core.agent.models import AgentTaskPlan, AgentContextLedger, AgentStep


class DynamicReasoningEngine:
    """
    AI Dynamic Reasoning & Anti-Repetition Engine.
    Synthesizes rich Chain-of-Thought (CoT) explanations for AI Copilot,
    providing technical context, natural Vietnamese phrasing, and strict
    anti-repetition safeguards between consecutive interaction turns.
    """

    def __init__(self):
        self._last_intro_idx: int = -1
        self._last_outro_idx: int = -1
        self._turn_counter: int = 0

    def synthesize_reasoning(
        self,
        prompt: str,
        plan: AgentTaskPlan,
        context_ledger: Optional[AgentContextLedger] = None,
        active_segments_count: int = 0,
    ) -> str:
        """
        Synthesize natural, context-aware reasoning for the proposed plan.
        Never repeats the exact same opening/closing template consecutively.
        """
        self._turn_counter += 1
        ledger = context_ledger or AgentContextLedger()

        # 1. Determine technical context & reasoning details
        reasoning_points: List[str] = []
        action_name = "thực thi tác vụ"

        steps = plan.steps if plan else []
        primary_step = steps[0] if steps else None
        tool_name = primary_step.tool_name if primary_step else ""
        tool_args = primary_step.tool_args if primary_step else {}

        # Context observation
        vid_path = ledger.video_path
        dur_sec = (ledger.duration_ms or 0) / 1000.0 if ledger.duration_ms else 0

        if tool_name == "create_timing":
            count = tool_args.get("count", 5)
            action_name = f"khởi tạo {count} câu timing"
            if vid_path:
                reasoning_points.append(
                    f"Video nguồn đã được nạp ({dur_sec:.1f}s). Tôi sẽ sử dụng engine VAD cấu hình chuyên sâu (CFG-9 Anime JA) "
                    f"với ngưỡng 0.35 và trích xuất âm thanh 16kHz qua PyAV để lọc sạch tạp âm, bắt trọn từng nhịp thoại."
                )
            else:
                reasoning_points.append(
                    f"Tôi sẽ áp dụng bộ lọc VAD thông minh nhằm phát hiện chuẩn xác các khoảng lặng âm thanh và nhịp thoại, "
                    f"loại bỏ nguy cơ đè lên nhạc nền intro."
                )

        elif tool_name == "apply_subtitle_style":
            action_name = "tinh chỉnh định dạng kiểu chữ phụ đề"
            f_name = tool_args.get("font_name", "Arial")
            f_size = tool_args.get("font_size", 24)
            f_color = tool_args.get("font_color", "#FFFF00")
            o_color = tool_args.get("outline_color", "#000000")
            o_width = tool_args.get("outline_width", 2)
            reasoning_points.append(
                f"Để tối ưu độ tương phản và giúp phụ đề dễ đọc trên nền video, tôi thiết lập font {f_name} (cỡ {f_size}px) "
                f"kết hợp màu chữ {f_color} và viền nổi bật {o_color} ({o_width}px). Toàn bộ {active_segments_count} câu hiện có sẽ được đồng bộ."
            )

        elif tool_name == "adjust_subtitle_bounds":
            d_st = tool_args.get("delta_start_ms", 0)
            d_en = tool_args.get("delta_end_ms", 0)
            action_name = "điều chỉnh mốc thời gian phụ đề"
            reasoning_points.append(
                f"Tôi tinh chỉnh mốc đầu ({d_st:+d}ms) và mốc cuối ({d_en:+d}ms) theo yêu cầu, "
                f"kích hoạt cơ chế Overlap Guard để tự động bảo vệ khoảng cách giữa các câu sát nhau."
            )

        elif tool_name == "shift_subtitles":
            off = tool_args.get("offset_ms", 0)
            action_name = f"dịch chuyển thời gian phụ đề ({off:+d}ms)"
            reasoning_points.append(
                f"Tịnh tiến toàn bộ thời gian phụ đề với độ lệch {off:+d}ms, đồng thời bật cơ chế kẹp biên không âm (>= 0ms) "
                f"để bảo vệ tính toàn vẹn của Timeline."
            )

        elif tool_name == "rescan_subtitles":
            scope = tool_args.get("scope", "all")
            indices = tool_args.get("segment_indices", [])
            action_name = "quét lại âm thanh phụ đề"
            if indices:
                reasoning_points.append(
                    f"Tập trung quét lại sóng âm thanh cho câu #{', #'.join(map(str, indices))} bằng engine nhận diện chuyên biệt, "
                    f"cập nhật văn bản mới mà không ảnh hưởng các câu khác."
                )
            else:
                reasoning_points.append(
                    f"Tiến hành quét lại toàn bộ âm thanh các phân đoạn để làm mới nhận diện lời thoại."
                )

        elif tool_name == "run_asr":
            lang = tool_args.get("language", "auto")
            action_name = "nhận diện giọng nói tự động (ASR)"
            reasoning_points.append(
                f"Sử dụng Faster-Whisper (ngôn ngữ: {lang.upper()}) để phân tích âm phổ và bóc tách lời thoại tự động."
            )

        elif tool_name == "translate_subtitles":
            tgt = tool_args.get("target_lang", "vi").upper()
            action_name = f"dịch phụ đề sang tiếng {tgt}"
            reasoning_points.append(
                f"Chuyển đổi phụ đề sang {tgt} qua Translation CAT Studio, bảo tồn văn phong bản địa và thuật ngữ ngữ cảnh."
            )

        else:
            # Fallback safe reasoning for custom/generic tasks
            action_name = "xử lý yêu cầu"
            clean_prompt = prompt.strip().rstrip(".,!?")
            reasoning_points.append(
                f"Tôi đã phân tích nội dung '{clean_prompt}' và thiết lập các bước điều phối an toàn tương ứng."
            )

        # 2. Select varied opening (Anti-Repetition)
        clean_p = prompt.strip().rstrip(".,!?")
        intros = [
            f"🔍 **Phân tích bối cảnh:** Tôi đã xem xét yêu cầu *\"{clean_p}\"* và nhận thấy đây là phương án tối ưu:",
            f"⚡ **Phương án kỹ thuật:** Dựa trên hiện trạng dự án, tôi đã xây dựng lộ trình xử lý cho *\"{clean_p}\"*:",
            f"🎯 **Chiến lược thực hiện:** Tôi hiểu rõ mục đích {action_name}. Kế hoạch chi tiết gồm các bước sau:",
            f"🛠️ **Thiết lập tác vụ:** Tôi đã hoàn thành tính toán thông số kỹ thuật cho *\"{clean_p}\"* như sau:",
        ]
        intro_idx = (self._last_intro_idx + 1) % len(intros)
        self._last_intro_idx = intro_idx
        selected_intro = intros[intro_idx]

        # 3. Steps outline
        steps_outline = []
        for i, s in enumerate(steps):
            steps_outline.append(f"  • **Bước {i+1}:** {s.title}")
        steps_text = "\n".join(steps_outline)

        # 4. Technical CoT detail
        cot_text = " ".join(reasoning_points)

        # 5. Select varied call-to-action (Anti-Repetition)
        outros = [
            "👉 Mời bạn kiểm tra **Thẻ Kế Hoạch (Cổng 1)** ở cột bên phải và bấm **Duyệt Kế Hoạch & Bắt Đầu** để kích hoạt.",
            "👉 Thông số kỹ thuật dự kiến đã được tóm tắt tại **Thẻ Duyệt bên phải**. Khi bạn sẵn sàng, hãy bấm **Duyệt** để tôi tiến hành.",
            "👉 Bạn vui lòng xem qua các cam kết an toàn ở khung bên phải và bấm **Duyệt** để bắt đầu xử lý.",
            "👉 Hãy xác nhận chiến lược tại **Thẻ Kế Hoạch bên phải** để khởi chạy quy trình tự động.",
        ]
        outro_idx = (self._last_outro_idx + 1) % len(outros)
        self._last_outro_idx = outro_idx
        selected_outro = outros[outro_idx]

        # Assemble full dynamic response
        parts = [
            selected_intro,
            cot_text,
            f"\n📋 **Lộ trình thực hiện:**\n{steps_text}",
            f"\n{selected_outro}",
        ]
        return "\n\n".join(parts)
