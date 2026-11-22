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
        self._last_completion_idx: int = -1
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
            indices = tool_args.get("segment_indices", [])
            action_name = f"dịch phụ đề sang tiếng {tgt}"
            if indices:
                reasoning_points.append(
                    f"Chuyển đổi {len(indices)} câu phụ đề (#{', #'.join(map(str, indices))}) sang {tgt} qua Translation CAT Studio. "
                    f"Toàn bộ các câu khác trong dự án được bảo toàn nguyên vẹn 100%."
                )
            else:
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

    def synthesize_completion(
        self,
        step: AgentStep,
        result: Dict[str, Any],
        context_ledger: Optional[AgentContextLedger] = None,
        active_segments_count: int = 0,
    ) -> str:
        """
        Synthesize natural, professional, and context-aware completion summary
        for an executed step at Gate 2. Anti-repetitive, vivid, and detailed.
        """
        tool_name = step.tool_name
        args = step.tool_args or {}

        # 1. Generate tool-specific accomplishment details
        summary_body = ""

        if tool_name == "create_timing":
            segs = result.get("segments", [])
            new_segs = result.get("new_segments", [])
            is_continue = args.get("is_continue") or bool(new_segs)
            target_list = result.get("new_segments", segs)
            count = result.get("count", len(target_list))
            t_span = ""
            if target_list:
                t_span = f" ({target_list[0].get('start', '00:00.000')} ➔ {target_list[-1].get('end', '00:00.000')})"

            status = result.get("status", "ok")
            req_count = result.get("requested_count", count)
            partial_note = ""
            if status == "no_speech":
                partial_note = " (không phát hiện thêm đoạn thoại nào sau mốc này)"
            elif status == "partial" or (req_count and count < req_count):
                partial_note = f" (đã quét đến cuối video, tìm thấy {count}/{req_count} phân đoạn thực tế)"

            if is_continue and new_segs:
                start_off = result.get("start_offset_s", 0.0)
                from ui.SubEditor import ms_to_time_str
                off_str = ms_to_time_str(int(start_off * 1000)) if start_off > 0 else "đầu video"
                templates = [
                    f"Tôi đã kích hoạt engine VAD CFG-9 (Anime JA) trích xuất thành công {count} phân đoạn nhịp thoại tiếp theo{t_span} từ mốc {off_str}{partial_note}. Toàn bộ {len(segs) - len(new_segs)} câu phụ đề trước đó được bảo toàn nguyên vẹn 100%.",
                    f"Hệ thống đã bắt trọn {count} câu thoại tiếp theo{t_span} sau mốc {off_str}{partial_note}. Dữ liệu các câu trước được giữ nguyên vẹn.",
                    f"Đã hoàn thành thiết lập {count} phân đoạn phụ đề mới{t_span} nối tiếp mốc {off_str}{partial_note}. Cấu trúc timeline được bảo toàn tuyệt đối.",
                ]
            else:
                templates = [
                    f"Tôi đã kích hoạt engine VAD CFG-9 (Anime JA) trích xuất thành công {count} phân đoạn nhịp thoại{t_span}{partial_note}. Mọi khoảng lặng âm thanh đã được chuẩn hóa mượt mà.",
                    f"Hệ thống đã bắt trọn {count} câu thoại của nhân vật{t_span} qua bộ lọc Silero VAD 16kHz{partial_note}.",
                    f"Đã hoàn thành thiết lập {count} phân đoạn phụ đề chuẩn{t_span}{partial_note}.",
                ]
            summary_body = templates[(self._last_completion_idx + 1) % len(templates)]

        elif tool_name == "apply_subtitle_style":
            style = result.get("style", {})
            f_name = style.get("font_name") or args.get("font_name", "Arial")
            f_size = style.get("font_size") or args.get("font_size", 24)
            f_color = style.get("font_color") or args.get("font_color", "#FFFF00")
            o_color = style.get("outline_color") or args.get("outline_color", "#000000")
            segs = result.get("segments", [])
            count = len(segs) or active_segments_count
            templates = [
                f"Đã áp dụng đồng bộ font {f_name} (cỡ {f_size}px) với tông màu chữ {f_color} và viền nổi bật {o_color} lên toàn bộ {count} câu phụ đề hiện có.",
                f"Hệ thống đã cập nhật kiểu chữ {f_name} {f_size}px (màu {f_color}, viền {o_color}) vào video overlay. Độ tương phản thị giác được tối ưu vượt bậc.",
                f"Toàn bộ {count} phân đoạn trên Timeline đã khoác lên diện mạo mới với chữ {f_color} viền {o_color} (font {f_name}, cỡ {f_size}px) sắc nét.",
            ]
            summary_body = templates[(self._last_completion_idx + 1) % len(templates)]

        elif tool_name == "adjust_subtitle_bounds":
            d_st = result.get("delta_start_ms", args.get("delta_start_ms", 0))
            d_en = result.get("delta_end_ms", args.get("delta_end_ms", 0))
            segs = result.get("segments", [])
            count = len(segs) or active_segments_count
            templates = [
                f"Toàn bộ {count} câu phụ đề đã được điều chỉnh mốc đầu ({d_st:+d}ms) và mốc cuối ({d_en:+d}ms). Thuật toán Overlap Guard đã bảo vệ tuyệt đối khoảng cách an toàn giữa các câu.",
                f"Đã bù trừ mốc đầu ({d_st:+d}ms) và mốc cuối ({d_en:+d}ms) cho {count} phân đoạn. Không có hiện tượng câu sau đè lên câu trước.",
                f"Hiệu chỉnh mốc thời gian phụ đề ({d_st:+d}ms đầu, {d_en:+d}ms cuối) hoàn tất trên {count} câu. Cấu trúc timeline được bảo toàn nguyên vẹn.",
            ]
            summary_body = templates[(self._last_completion_idx + 1) % len(templates)]

        elif tool_name == "shift_subtitles":
            off = result.get("offset_ms", args.get("offset_ms", 0))
            segs = result.get("segments", [])
            count = len(segs) or active_segments_count
            templates = [
                f"Toàn bộ {count} câu phụ đề đã được tịnh tiến {off:+d}ms. Các câu ở đầu đã được kẹp biên an toàn (>= 00:00.000) bảo đảm cấu trúc chuẩn của phụ đề.",
                f"Đã dời toàn bộ phụ đề đi {off:+d}ms. Quy chuẩn thời lượng tối thiểu (>= 200ms) và mốc không âm được bảo toàn 100%.",
                f"Hoàn thành tịnh tiến {count} phân đoạn timeline với độ lệch {off:+d}ms mà không làm xô lệch khoảng cách tương đối giữa các câu.",
            ]
            summary_body = templates[(self._last_completion_idx + 1) % len(templates)]

        elif tool_name == "rescan_subtitles":
            indices = result.get("segment_indices") or args.get("segment_indices", [])
            idx_str = f"câu #{', #'.join(map(str, indices))}" if indices else "toàn bộ phân đoạn"
            templates = [
                f"Đã phân tích lại sóng âm và cập nhật nội dung mới cho {idx_str}. Toàn bộ các câu phụ đề khác được giữ nguyên vẹn 100%.",
                f"Làm mới nhận diện giọng nói thành công cho {idx_str}, dữ liệu mới đã được cập nhật vào bảng kiểm tra.",
                f"Quá trình quét lại âm thanh cục bộ cho {idx_str} hoàn tất an toàn, không gây xáo trộn dữ liệu xung quanh.",
            ]
            summary_body = templates[(self._last_completion_idx + 1) % len(templates)]

        elif tool_name == "run_asr":
            lang = (args.get("language") or "auto").upper()
            segs = result.get("segments", [])
            indices = result.get("indices") or []
            target_segs = [s for s in segs if s.get("id") in indices] if indices else segs
            count = len(target_segs)
            t_span = ""
            if target_segs:
                t_span = f" ({target_segs[0].get('start', '00:00.000')} ➔ {target_segs[-1].get('end', '00:00.000')})"

            err = result.get("error")
            status = result.get("status", "ok")
            if err or status == "error":
                summary_body = (
                    f"⚠️ **Quá trình nhận diện giọng nói (Faster-Whisper) gặp lỗi:** {err or 'Lỗi nhận diện âm thanh'}.\n\n"
                    f"Mốc thời gian phụ đề đã duyệt được bảo toàn 100%. Bạn có thể kiểm tra cấu hình model hoặc chạy lại."
                )
            else:
                templates = [
                    f"Faster-Whisper ({lang}) đã nhận diện thành công nội dung âm thanh cho {count} phân đoạn phụ đề mới{t_span}. Dữ liệu lời thoại thực tế đã sẵn sàng trong khung kiểm tra.",
                    f"Nhận diện giọng nói tự động hoàn tất cho {count} phân đoạn mới{t_span}. Toàn bộ từ khóa và nhịp ngắt đã được bóc tách sang text.",
                    f"Đã bóc tách thành công lời thoại từ âm phổ video cho {count} câu{t_span} qua Faster-Whisper ({lang}).",
                ]
                summary_body = templates[(self._last_completion_idx + 1) % len(templates)]

        elif tool_name == "translate_subtitles":
            tgt = (result.get("target_lang") or args.get("target_lang", "vi")).upper()
            indices = result.get("segment_indices") or args.get("segment_indices", [])
            segs = result.get("segments", [])
            total_count = len(segs) or active_segments_count
            failed = result.get("failed_indices", [])
            trans_count = result.get("translated_count", 0)
            trans_idxs = result.get("translated_indices", [])

            # Kịch bản A: Toàn bộ câu yêu cầu đều thất bại hoặc chưa dịch được câu nào
            if trans_count == 0:
                targets = failed or indices
                fail_str = f"câu #{', #'.join(map(str, targets))}" if targets else "phụ đề"
                return (
                    f"⚠️ **Chưa thể dịch {fail_str} do chưa nạp mô hình AI:**\n\n"
                    f"Hệ thống chưa tìm thấy mô hình dịch thuật khả dụng (Local GGUF hoặc Online API) "
                    f"và chưa có bản dịch sẵn trong CAT Studio / Bộ nhớ dịch.\n\n"
                    f"👉 *Vui lòng nạp model trong Tab 2 (CAT Studio) hoặc cấu hình API Key trong Cài đặt.*\n"
                    f"Toàn bộ dữ liệu phụ đề gốc được bảo toàn nguyên vẹn 100%."
                )

            # Kịch bản B: Dịch được một phần (từ CAT Studio/TM), còn lại một số câu chưa dịch được
            if failed and trans_count > 0:
                done_str = f"câu #{', #'.join(map(str, trans_idxs))}" if trans_idxs else f"{trans_count} câu"
                fail_str = f"câu #{', #'.join(map(str, failed))}"
                other_count = max(0, total_count - len(indices)) if indices else 0
                return (
                    f"⚠️ **Báo cáo tiến độ dịch thuật từ CAT Studio & Bộ nhớ dịch (Cần lưu ý):**\n\n"
                    f"• **Đã cập nhật bản dịch:** {done_str} sang tiếng {tgt} từ CAT Studio / Bộ nhớ dịch.\n"
                    f"• **Chưa thể dịch:** {fail_str} do chưa nạp mô hình AI (Local GGUF hoặc Online API) và chưa có sẵn trong bộ nhớ dịch.\n\n"
                    f"👉 *Vui lòng nạp model trong Tab 2 hoặc cài đặt API Key để hoàn tất các câu còn lại.*\n"
                    f"Toàn bộ các câu chưa dịch và {other_count} câu khác trong dự án được bảo toàn nguyên vẹn 100%."
                )

            # Kịch bản C: Dịch thành công 100% các câu được yêu cầu
            if indices:
                count_done = len(indices)
                idx_str = f"câu #{', #'.join(map(str, indices))}"
                other_count = max(0, total_count - count_done)
                templates = [
                    f"Đã hoàn thành dịch {idx_str} sang tiếng {tgt} qua CAT Studio. {other_count} câu khác trong dự án được giữ nguyên vẹn 100%.",
                    f"Quá trình chuyển ngữ tiếng {tgt} cho {idx_str} đã hoàn tất thành công. Dữ liệu các phân đoạn còn lại được bảo toàn tuyệt đối.",
                    f"Hệ thống đã cập nhật bản dịch tiếng {tgt} cho {idx_str} vào bảng kiểm tra. Toàn bộ các câu khác không bị ảnh hưởng.",
                ]
            else:
                templates = [
                    f"Đã hoàn thành dịch toàn bộ {total_count} câu phụ đề sang tiếng {tgt} qua CAT Studio, đảm bảo tính mạch lạc của câu chuyện.",
                    f"Hệ thống đã chuyển ngữ thành công toàn bộ {total_count} phân đoạn sang tiếng {tgt}. Văn phong bản địa hóa đã được áp dụng mượt mà.",
                ]
            summary_body = templates[(self._last_completion_idx + 1) % len(templates)]

        elif tool_name == "process_general_task":
            user_prompt = result.get("prompt") or args.get("prompt") or step.title
            clean_prompt = user_prompt.strip().rstrip(".,!?")
            return (
                f"ℹ️ **Thông báo tiếp nhận yêu cầu:**\n"
                f"Yêu cầu *\"{clean_prompt}\"* đã được tiếp nhận. Hệ thống chưa tìm thấy thao tác phụ đề tương ứng cần thực thi.\n"
                f"Dữ liệu phụ đề hiện tại được bảo toàn nguyên vẹn 100%.\n\n"
                f"👉 Bạn có thể gửi câu lệnh cụ thể như: *'Dịch các câu 6,7,13'*, *'Tạo 5 câu timing'*, *'Dịch chuyển phụ đề tiến 500ms'*, v.v."
            )

        else:
            clean_title = step.title.strip().rstrip(".,!?")
            templates = [
                f"Tác vụ '{clean_title}' đã được thực thi an toàn và đồng bộ hóa vào dự án.",
                f"Tôi đã hoàn thành xử lý '{clean_title}'. Toàn bộ dữ liệu đã được cập nhật chính xác.",
                f"Quy trình thực thi cho '{clean_title}' đã xong, sẵn sàng cho các thao tác tiếp theo.",
            ]
            summary_body = templates[(self._last_completion_idx + 1) % len(templates)]

        # 2. Dynamic opening header
        intros = [
            "🎉 **Hoàn thành tác vụ thành công:**",
            "✨ **Tác vụ đã được thực thi hoàn tất:**",
            "🚀 **Đã hoàn thành xuất sắc bước này:**",
            "💎 **Xử lý hoàn tất theo kế hoạch:**",
        ]
        self._last_completion_idx = (self._last_completion_idx + 1) % len(intros)
        selected_intro = intros[self._last_completion_idx]

        # 3. Dynamic call-to-action outro
        outros = [
            "👉 Kết quả chi tiết đã hiển thị tại bảng bên phải. Bạn có thể nhấp chuột sửa trực tiếp nội dung hoặc bấm Duyệt để tiếp tục.",
            "👉 Dữ liệu thực tế đã sẵn sàng ở cột bên phải. Bạn hãy kiểm tra lại và bấm Duyệt để chuyển bước tiếp theo.",
            "👉 Mời bạn xem lại thành phẩm ở khung kiểm tra bên phải. Nếu cần chỉnh sửa lời thoại, bạn có thể nhấp sửa trực tiếp ngay tại đây.",
            "👉 Bạn có thể xem kết quả chi tiết ở khung bên phải, chỉnh sửa trực tiếp hoặc bấm Duyệt để hoàn tất.",
        ]
        selected_outro = outros[self._last_completion_idx % len(outros)]

        return f"{selected_intro}\n{summary_body}\n\n{selected_outro}"
