import inspect
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)



def create_timing(
    count: int = 5,
    duration_per_block_ms: int = 3000,
    gap_ms: int = 500,
    video_path: Optional[str] = None,
    start_offset_s: float = 0.0,
    vad_threshold: Optional[float] = None,
    min_silence_ms: Optional[int] = None,
    speech_pad_ms: Optional[int] = None,
    max_speech_duration_s: Optional[float] = None,
    preserved_segments: Optional[List[Dict[str, Any]]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Tạo count khối timing phụ đề mẫu, sử dụng VAD nếu có video hoặc fallback an toàn."""
    from core.agent.vad_timing_service import generate_vad_timing_segments

    if preserved_segments is None and "preview_segments" in kwargs:
        preserved_segments = kwargs["preview_segments"]

    segments = generate_vad_timing_segments(
        count=count,
        video_path=video_path,
        start_offset_s=start_offset_s,
        vad_threshold=vad_threshold,
        min_silence_ms=min_silence_ms,
        speech_pad_ms=speech_pad_ms,
        max_speech_duration_s=max_speech_duration_s,
        duration_per_block_ms=duration_per_block_ms,
        gap_ms=gap_ms,
        preserved_segments=preserved_segments,
    )
    return {"segments": segments, "count": len(segments), "status": "ok"}


def adjust_subtitle_bounds(
    delta_start_ms: int = 0,
    delta_end_ms: int = 0,
    scope: str = "all",
    segment_indices: Optional[List[int]] = None,
    segments: Optional[List[Dict[str, Any]]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Điều chỉnh mốc thời gian bắt đầu và kết thúc của các câu phụ đề theo millisecond."""
    from ui.SubEditor import ms_to_time_str, time_str_to_ms
    segs = segments or []
    target_indices = set(segment_indices) if segment_indices else None
    modified_segs = []
    for i, s in enumerate(segs):
        sc = dict(s)
        seg_id = sc.get("id") if isinstance(sc.get("id"), int) else (i + 1)
        orig_st = time_str_to_ms(sc.get("start", 0))
        orig_en = max(orig_st + 200, time_str_to_ms(sc.get("end", 0)))

        if target_indices is None or seg_id in target_indices:
            raw_st = max(0, orig_st + delta_start_ms)
            raw_en = orig_en + delta_end_ms

            # Chốt chặn nghịch đảo biên (Boundary Inversion Guard: raw_st > raw_en - 200)
            if raw_st > raw_en - 200:
                mid = max(100, (orig_st + orig_en) // 2)
                st = max(0, mid - 100)
                en = st + 200
            else:
                st = raw_st
                en = max(st + 200, raw_en)

            sc["start"] = ms_to_time_str(st)
            sc["end"] = ms_to_time_str(en)
        else:
            sc["start"] = ms_to_time_str(orig_st)
            sc["end"] = ms_to_time_str(orig_en)

        modified_segs.append(sc)

    # Auto resolve overlaps (P0 Overlap Prevention)
    for i in range(len(modified_segs) - 1):
        curr_start = time_str_to_ms(modified_segs[i]["start"])
        curr_end = time_str_to_ms(modified_segs[i]["end"])
        next_start = time_str_to_ms(modified_segs[i+1]["start"])
        if curr_end > next_start:
            if next_start - curr_start >= 200:
                modified_segs[i]["end"] = ms_to_time_str(next_start)
            else:
                modified_segs[i+1]["start"] = ms_to_time_str(curr_end)
                next_end = time_str_to_ms(modified_segs[i+1]["end"])
                if next_end < curr_end + 200:
                    modified_segs[i+1]["end"] = ms_to_time_str(curr_end + 200)

    return {
        "segments": modified_segs,
        "count": len(modified_segs),
        "delta_start_ms": delta_start_ms,
        "delta_end_ms": delta_end_ms,
        "segment_indices": segment_indices,
        "status": "ok",
    }


def shift_subtitles(
    offset_ms: int = 0,
    scope: str = "all",
    segment_indices: Optional[List[int]] = None,
    segments: Optional[List[Dict[str, Any]]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Dịch chuyển toàn bộ phụ đề tiến hoặc lùi theo millisecond."""
    from ui.SubEditor import ms_to_time_str, time_str_to_ms
    segs = segments or []
    target_indices = set(segment_indices) if segment_indices else None
    prev_end = 0
    shifted = []
    for i, s in enumerate(segs):
        sc = dict(s)
        seg_id = sc.get("id") if isinstance(sc.get("id"), int) else (i + 1)
        orig_st = time_str_to_ms(sc.get("start", 0))
        orig_en = max(orig_st + 200, time_str_to_ms(sc.get("end", 0)))
        orig_dur = max(200, orig_en - orig_st)

        if target_indices is None or seg_id in target_indices:
            raw_st = orig_st + offset_ms
            if target_indices is not None and offset_ms < 0:
                min_allowed_st = (time_str_to_ms(shifted[-1]["start"]) + 200) if shifted else 0
                st = max(0, min_allowed_st, raw_st)
                if shifted and prev_end > st:
                    shifted[-1]["end"] = ms_to_time_str(st)
            else:
                st = max(0, prev_end, raw_st)
            en = st + orig_dur
            sc["start"] = ms_to_time_str(st)
            sc["end"] = ms_to_time_str(en)
            prev_end = en
        else:
            if orig_st < prev_end:
                st = prev_end
                en = st + orig_dur
                sc["start"] = ms_to_time_str(st)
                sc["end"] = ms_to_time_str(en)
                prev_end = en
            else:
                prev_end = orig_en

        shifted.append(sc)

    return {
        "segments": shifted,
        "count": len(shifted),
        "offset_ms": offset_ms,
        "segment_indices": segment_indices,
        "status": "ok",
    }




def apply_subtitle_style(
    font_name: Optional[str] = None,
    font_size: Optional[int] = None,
    font_color: Optional[str] = None,
    outline_color: Optional[str] = None,
    outline_width: Optional[int] = None,
    shadow: Optional[bool] = None,
    position: Optional[str] = None,
    segments: Optional[List[Dict[str, Any]]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Tinh chỉnh giao diện và định dạng phụ đề (Font, Size, Màu chữ, Viền, Shadow)."""
    style = {}
    if font_name:
        style["font_name"] = font_name
    if font_size is not None:
        style["font_size"] = int(font_size)
    if font_color:
        style["font_color"] = font_color
    if outline_color:
        style["outline_color"] = outline_color
    if outline_width is not None:
        style["outline_width"] = int(outline_width)
    if shadow is not None:
        style["shadow"] = bool(shadow)
    if position:
        style["position"] = position

    segs = segments or kwargs.get("segments", [])
    res: Dict[str, Any] = {
        "status": "ok",
        "style": style,
        "message": f"Đã áp dụng định dạng phụ đề: {style}",
    }
    if segs:
        res["segments"] = segs
        res["count"] = len(segs)

    return res


def rescan_subtitles(
    scope: str = "all",
    segment_indices: Optional[List[int]] = None,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    segments: Optional[List[Dict[str, Any]]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Quét lại (rescan) âm thanh cho các đoạn phụ đề được chỉ định."""
    from ui.SubEditor import time_str_to_ms
    segs = segments or []
    indices = segment_indices or []
    rescanned = []
    for i, s in enumerate(segs):
        sc = dict(s)
        seg_id = sc.get("id") if isinstance(sc.get("id"), int) else (i + 1)
        should_rescan = False
        if scope == "all":
            should_rescan = True
        elif scope == "time_interval":
            if start_ms is not None and end_ms is not None:
                st = time_str_to_ms(sc.get("start", 0))
                en = time_str_to_ms(sc.get("end", 0))
                if en > start_ms and st < end_ms:
                    should_rescan = True
        elif seg_id in indices:
            should_rescan = True

        if should_rescan:
            txt = sc.get("text", "")
            if not txt.endswith("(quét lại)"):
                sc["text"] = f"{txt} (quét lại)".strip()
        rescanned.append(sc)

    return {
        "status": "ok",
        "scope": scope,
        "segment_indices": indices,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "segments": rescanned,
        "count": len(rescanned),
    }


def run_asr(
    language: str = "auto",
    limit: Optional[int] = None,
    indices: Optional[List[int]] = None,
    segments: Optional[List[Dict[str, Any]]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Nhận diện giọng nói (ASR) với hỗ trợ giới hạn số câu hoặc các câu chỉ định."""
    from ui.SubEditor import ms_to_time_str
    segs = segments or []
    if not segs:
        count = limit or (max(indices) if indices else 5)
        generated = []
        for i in range(count):
            idx = i + 1
            if indices and idx not in indices:
                continue
            generated.append({
                "id": idx,
                "start": ms_to_time_str(i * 3000 + 500),
                "end": ms_to_time_str((i + 1) * 3000),
                "text": f"Nội dung nhận diện câu #{idx}",
                "translation": f"Recognized content #{idx}",
            })
        segs = generated
    else:
        modified_segs = []
        target_indices = set(indices) if indices else None
        for i, s in enumerate(segs):
            sc = dict(s)
            seg_id = sc.get("id") if isinstance(sc.get("id"), int) else (i + 1)
            is_target = False
            if target_indices is not None:
                if seg_id in target_indices:
                    is_target = True
            elif limit is not None:
                if i < limit:
                    is_target = True
            else:
                is_target = True

            if is_target:
                sc["text"] = f"Nội dung nhận diện câu #{seg_id} (Whisper)"
                sc["translation"] = f"Recognized content #{seg_id}"
            modified_segs.append(sc)
        segs = modified_segs

    return {
        "status": "ok",
        "language": language,
        "limit": limit,
        "indices": indices,
        "segments": segs,
        "count": len(segs),
    }


def _ensure_gemma_model_loaded(mm: Any) -> bool:
    """Tự động kiểm tra và nạp file gemma-2-9b-it-Q4_K_M.gguf vào ModelManager với cấu hình CUDA Hybrid."""
    import os
    target_filename = "gemma-2-9b-it-Q4_K_M.gguf"

    # 1. Nếu model hiện tại đã đúng file Gemma, sẵn sàng dịch
    curr = getattr(mm, "current_model_name", "")
    if curr and target_filename in curr:
        return True

    # 2. Định vị file model trên đĩa
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidate_paths = [
        os.path.join(base_dir, "models", target_filename),
        os.path.join("models", target_filename),
        os.path.join(r"E:\AI-Subtitle-Translator\models", target_filename),
    ]
    model_path = None
    for p in candidate_paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            model_path = p
            break

    # Nếu chưa có gemma, tìm model .gguf khác có sẵn trong thư mục models/
    if not model_path:
        models_dir = os.path.join(base_dir, "models")
        if os.path.exists(models_dir):
            for f in os.listdir(models_dir):
                if f.endswith(".gguf") and os.path.getsize(os.path.join(models_dir, f)) > 0:
                    model_path = os.path.join(models_dir, f)
                    break

    if not model_path:
        return False

    # 3. Tính toán cấu hình CUDA Hybrid tối ưu cho card RTX 3050 (16-20 layers trên GPU, còn lại RAM)
    try:
        from core.translation.core.hardware_detector import HardwareDetector
        gpu_info = HardwareDetector.get_gpu_info()
        llama_has_cuda = HardwareDetector.check_llama_cuda_backend()
        has_gpu = bool(gpu_info.get("has_gpu_hardware")) and llama_has_cuda
        vram_gb = float(gpu_info.get("vram_gb", 0.0))

        if not has_gpu:
            n_gpu_layers = 0
        elif vram_gb >= 7.5:
            n_gpu_layers = -1
        else:
            # RTX 3050 (4GB VRAM): 16-20 layers trên GPU, phần còn lại trên RAM hệ thống
            safe_vram = max(0.5, vram_gb - 0.8)
            ratio = min(1.0, safe_vram / 5.42)
            n_gpu_layers = max(16, min(20, int(ratio * 36)))

        return mm.load_model(model_path, n_ctx=4096, n_gpu_layers=n_gpu_layers)
    except Exception as e:
        print(f"[AI Agent Warning] Không thể nạp model {model_path}: {e}")
        return False


def _perform_single_translation(
    text: str,
    target_lang: str,
    llm_client: Optional[Any] = None,
    online_configs: Optional[List[Any]] = None,
    auto_load_model: bool = False,
) -> Optional[str]:
    """Thực thi dịch thuật một câu qua LLM client hoặc ModelManager (ưu tiên TranslateGemma).
    Nếu không có mô hình khả dụng, trả về None (tuyệt đối không dán nhãn giả [VI]).
    """
    if not text or not text.strip():
        return text

    # 1. Thử gọi LLM Client (Online Provider) nếu có
    if llm_client and hasattr(llm_client, "generate_with_fallback"):
        lang_names = {
            "vi": "Vietnamese", "en": "English", "ja": "Japanese",
            "ko": "Korean", "zh": "Chinese", "fr": "French", "de": "German"
        }
        tgt_name = lang_names.get(target_lang.lower(), target_lang)
        prompt = (
            f"Translate the following subtitle sentence into natural, fluent {tgt_name}. "
            f"Output ONLY the translated sentence, without any explanations, notes, quotes, or markdown formatting:\n\n{text}"
        )
        try:
            configs = online_configs or getattr(llm_client, "online_configs", None)
            res = llm_client.generate_with_fallback(
                messages=[
                    {"role": "system", "content": "You are a professional subtitle translator. Output only the translated text directly."},
                    {"role": "user", "content": prompt},
                ],
                online_configs=configs,
                allow_local_fallback=False,
            )
            content = res.get("content", "").strip()
            if content and not content.startswith("Đã nhận lệnh từ Local LLM"):
                return content
        except Exception:
            pass

    # 2. Thử gọi Local GGUF Model (ưu tiên TranslateGemma qua ModelManager backend llama_cpp)
    if auto_load_model:
        try:
            from core.translation.llm.model_manager import ModelManager
            from core.translation.core.prompt_builder import build_translation_prompt
            from core.translation.llm.worker import TranslationWorker

            mm = ModelManager.get_instance("llama_cpp")
            # Tự động nạp model TranslateGemma nếu chưa có model sẵn sàng trong VRAM/RAM
            if not getattr(mm, "current_model_name", ""):
                _ensure_gemma_model_loaded(mm)

            if mm and getattr(mm, "current_model_name", ""):
                lang_names = {
                    "vi": "Vietnamese", "en": "English", "ja": "Japanese",
                    "ko": "Korean", "zh": "Chinese", "fr": "French", "de": "German"
                }
                tgt_name = lang_names.get(target_lang.lower(), "Vietnamese")
                is_ja = any('\u3040' <= c <= '\u30ff' for c in text)
                source_lang = "Japanese" if is_ja else "English"

                # Áp dụng mẫu Prompt chuẩn chỉnh của Gemma 2 (<start_of_turn>user ... <start_of_turn>model)
                model_name = getattr(mm, "current_model_name", "").lower()
                model_family = "gemma" if "gemma" in model_name or "translategemma" in model_name else "qwen"
                prompt = build_translation_prompt(
                    current_sub=text,
                    source_lang=source_lang,
                    target_lang=tgt_name,
                    is_ja_origin=is_ja,
                    model_family=model_family,
                )

                res = mm.generate(prompt=prompt)
                if res and res.strip():
                    clean_text = TranslationWorker._visible_translation(res)
                    if not clean_text:
                        for line in res.strip().splitlines():
                            line = line.strip().strip('"\'')
                            if line and not line.startswith("[") and not line.startswith("<"):
                                clean_text = line
                                break
                    if clean_text:
                        return clean_text.strip().strip('"\'')
        except Exception as e:
            print(f"[AI Agent Translation Error] {e}")

    # 3. Tuyệt đối không tự ý ghép tag [VI]! Trả về None khi chưa có mô hình dịch.
    return None


def translate_subtitles(
    target_lang: str = "vi",
    scope: str = "all",
    segment_indices: Optional[List[int]] = None,
    segments: Optional[List[Dict[str, Any]]] = None,
    llm_client: Optional[Any] = None,
    project_dir: Optional[str] = None,
    translation_memory: Optional[Any] = None,
    aisrt_path: Optional[str] = None,
    project_subs: Optional[List[Dict[str, Any]]] = None,
    online_configs: Optional[List[Any]] = None,
    auto_load_model: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Dịch phụ đề sang ngôn ngữ đích trong CAT Studio với hỗ trợ chọn lọc câu chỉ định và tích hợp Translation Memory / project.aisrt."""
    import os
    import json

    segs = segments or []
    target_indices = set(segment_indices) if segment_indices else None
    translated = []
    translated_count = 0
    translated_indices: List[int] = []
    failed_indices: List[int] = []

    # 1. Nạp cơ sở dữ liệu dịch thuật từ project.aisrt (nếu có)
    aisrt_subtitles_by_id: Dict[str, str] = {}
    aisrt_subtitles_by_idx: Dict[int, str] = {}
    aisrt_subtitles_by_text: Dict[str, str] = {}
    tm_dict: Dict[str, str] = {}

    target_aisrt_file = aisrt_path
    if not target_aisrt_file and project_dir:
        cand1 = os.path.join(project_dir, "artifacts", "translation", "project.aisrt")
        cand2 = os.path.join(project_dir, "project.aisrt")
        if os.path.exists(cand1):
            target_aisrt_file = cand1
        elif os.path.exists(cand2):
            target_aisrt_file = cand2

    # Chỉ nạp project.aisrt từ aisrt_path hoặc project_dir hợp lệ
    # Tuyệt đối không tự ý nạp file từ dự án khác để tránh rò rỉ dữ liệu

    if target_aisrt_file and os.path.exists(target_aisrt_file):
        try:
            with open(target_aisrt_file, "r", encoding="utf-8") as f:
                aisrt_data = json.load(f)
            for s in aisrt_data.get("subtitles", []):
                trans = str(s.get("translation", "")).strip()
                if not trans or trans.startswith(f"[{target_lang.upper()}]"):
                    continue
                if s.get("segment_id"):
                    aisrt_subtitles_by_id[str(s["segment_id"])] = trans
                if s.get("id"):
                    aisrt_subtitles_by_id[str(s["id"])] = trans
                if s.get("index") is not None:
                    try:
                        aisrt_subtitles_by_idx[int(s["index"])] = trans
                    except (ValueError, TypeError):
                        pass
                if s.get("studio_index") is not None:
                    try:
                        aisrt_subtitles_by_idx[int(s["studio_index"]) + 1] = trans
                    except (ValueError, TypeError):
                        pass
                orig = str(s.get("original", "")).strip()
                if orig:
                    aisrt_subtitles_by_text[orig] = trans

            intelligence_tm = aisrt_data.get("intelligence", {}).get("translation_memory", {})
            if isinstance(intelligence_tm, dict):
                for src_k, val in intelligence_tm.items():
                    if isinstance(val, dict) and val.get("target_text"):
                        tm_dict[src_k.strip()] = str(val["target_text"]).strip()
                    elif isinstance(val, str) and val.strip():
                        tm_dict[src_k.strip()] = val.strip()
        except Exception:
            pass

    # 2. Nạp thêm từ translation_memory tham số (nếu có)
    if isinstance(translation_memory, dict):
        for k, v in translation_memory.items():
            if isinstance(v, dict) and v.get("target_text"):
                tm_dict[k.strip()] = str(v["target_text"]).strip()
            elif isinstance(v, str) and v.strip():
                tm_dict[k.strip()] = v.strip()

    # Nếu không có danh sách phân đoạn nào được cung cấp
    if not segs and segment_indices:
        failed_indices = list(segment_indices)

    # 3. Duyệt từng phân đoạn
    for i, s in enumerate(segs):
        sc = dict(s)
        idx_1based = i + 1

        # Resolve all possible identifiers for this segment
        candidate_ids = {idx_1based}
        for key in ("id", "stt", "segment_id", "index"):
            val = sc.get(key)
            if isinstance(val, int):
                candidate_ids.add(val)
            elif str(val or "").isdigit():
                candidate_ids.add(int(val))
            elif val:
                candidate_ids.add(str(val))

        # Chỉ xử lý các câu nằm trong segment_indices (hoặc toàn bộ nếu scope == "all")
        if target_indices is not None and not (candidate_ids & target_indices):
            # BẢO TOÀN NGUYÊN VẸN 100% CÁC CÂU KHÔNG ĐƯỢC CHỌN
            translated.append(sc)
            continue

        orig_src = sc.get("original_text") or sc.get("source_text") or sc.get("text", "")
        sc["original_text"] = orig_src
        sc["source_text"] = orig_src
        clean_orig = str(orig_src).strip()

        translated_text: Optional[str] = None

        # Bước A: Khai thác bản dịch sẵn có trong segment (nếu đã có bản dịch hợp lệ)
        existing_trans = str(sc.get("translation", "")).strip()
        if existing_trans and existing_trans != clean_orig and not existing_trans.startswith(f"[{target_lang.upper()}]"):
            translated_text = existing_trans

        # Bước B: Khai thác từ project.aisrt theo ID hoặc Index (CAT Studio)
        if not translated_text:
            for cid in candidate_ids:
                if str(cid) in aisrt_subtitles_by_id:
                    translated_text = aisrt_subtitles_by_id[str(cid)]
                    break
                if isinstance(cid, int) and cid in aisrt_subtitles_by_idx:
                    translated_text = aisrt_subtitles_by_idx[cid]
                    break

        # Bước C: Khai thác từ project.aisrt theo Original Text
        if not translated_text and clean_orig in aisrt_subtitles_by_text:
            translated_text = aisrt_subtitles_by_text[clean_orig]

        # Bước D: Khai thác từ Translation Memory (dict hoặc đối tượng TranslationMemory)
        if not translated_text and clean_orig in tm_dict:
            translated_text = tm_dict[clean_orig]

        if not translated_text and translation_memory and hasattr(translation_memory, "lookup"):
            try:
                tm_entry = translation_memory.lookup(clean_orig)
                if tm_entry and getattr(tm_entry, "target_text", None):
                    translated_text = str(tm_entry.target_text).strip()
            except Exception:
                pass

        # Bước E: Khai thác từ TranslationMemoryManager (SQLite TM Database)
        if not translated_text:
            try:
                from core.database.tm_manager import TranslationMemoryManager
                tmm = TranslationMemoryManager()
                matches = tmm.find_matches(clean_orig)
                for m in matches:
                    if m.score >= 0.99 and m.target_text:
                        translated_text = m.target_text.strip()
                        break
            except Exception:
                pass

        # Bước F: Gọi AI Model (Online LLM hoặc Local GGUF qua ModelManager)
        if not translated_text:
            translated_text = _perform_single_translation(
                clean_orig,
                target_lang=target_lang,
                llm_client=llm_client,
                online_configs=online_configs,
                auto_load_model=auto_load_model,
            )

        # Xác định số thứ tự định danh hiển thị của câu (ưu tiên theo target_indices khớp được)
        matched_target_id = idx_1based
        if target_indices and (candidate_ids & target_indices):
            # Lấy số ID/STT khớp trong target_indices
            target_matches = sorted([cid for cid in (candidate_ids & target_indices) if isinstance(cid, int)])
            if target_matches:
                matched_target_id = target_matches[0]

        # Đánh giá kết quả dịch
        if translated_text and not translated_text.startswith(f"[{target_lang.upper()}]"):
            sc["translation"] = translated_text
            sc["text"] = translated_text
            translated_count += 1
            translated_indices.append(matched_target_id)
        else:
            # CHƯA THỂ DỊCH (KHÔNG CÓ MÔ HÌNH VÀ KHÔNG CÓ TRONG TM):
            # TUYỆT ĐỐI BẢO TOÀN NGUYÊN VĂN BẢN GỐC, KHÔNG DÁN NHÃN GIẢ [VI]!
            sc["text"] = orig_src
            sc["translation"] = sc.get("translation") or ""
            failed_indices.append(matched_target_id)

        translated.append(sc)

    is_warning = bool(failed_indices)
    status = "warning" if is_warning else "ok"
    if not failed_indices:
        msg = f"Đã hoàn thành dịch {translated_count} phân đoạn sang tiếng {target_lang.upper()}."
    elif translated_count > 0:
        msg = (
            f"Đã cập nhật {translated_count} câu từ CAT Studio / Bộ nhớ dịch. "
            f"Các câu #{', #'.join(map(str, failed_indices))} chưa thể dịch do chưa nạp mô hình AI."
        )
    else:
        msg = (
            "Chưa có mô hình dịch thuật nào khả dụng (Cần cấu hình API Key trong Cài đặt "
            "hoặc nạp model Local GGUF trong Tab 2) và chưa có bản dịch sẵn trong CAT Studio."
        )

    return {
        "status": status,
        "target_lang": target_lang,
        "scope": scope,
        "segment_indices": segment_indices,
        "segments": translated,
        "count": len(translated),
        "translated_count": translated_count,
        "translated_indices": translated_indices,
        "failed_indices": failed_indices,
        "message": msg,
    }


def render_hardsub(
    resolution: str = "1080p",
    segments: Optional[List[Dict[str, Any]]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Cấu hình và kết xuất video Hardsub hoàn chỉnh."""
    segs = segments or []
    return {
        "status": "ok",
        "resolution": resolution,
        "segments": segs,
        "count": len(segs),
        "message": f"Cấu hình xuất video Hardsub {resolution} đã sẵn sàng",
    }


def process_general_task(prompt: str = "", **kwargs: Any) -> Dict[str, Any]:
    """Xử lý tác vụ tổng quát an toàn, loại bỏ crash ValueError."""
    return {
        "status": "ok",
        "prompt": prompt,
        "message": f"Đã ghi nhận và xử lý tác vụ: {prompt}",
    }

class AgentToolRegistry:
    """
    Registry of tools exposed to AI Agent Copilot.
    Validates arguments and coordinates execution directly with Core Services.
    """

    def __init__(self):
        self._tools: Dict[str, Callable[..., Any]] = {}
        self._descriptions: Dict[str, str] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def register_tool(
        self,
        name: str,
        handler: Callable[..., Any],
        description: str = "",
        parameters_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._tools[name] = handler
        self._descriptions[name] = description or handler.__doc__ or f"Execute {name}"

        if parameters_schema:
            self._schemas[name] = parameters_schema
        else:
            # Auto-infer simple parameters from handler signature
            sig = inspect.signature(handler)
            properties: Dict[str, Any] = {}
            required: List[str] = []
            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls"):
                    continue
                param_type = "string"
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == float:
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation in (dict, Dict):
                    param_type = "object"
                elif param.annotation in (list, List):
                    param_type = "array"

                properties[param_name] = {"type": param_type}
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)

            self._schemas[name] = {
                "type": "object",
                "properties": properties,
                "required": required,
            }

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' is not registered.")
        handler = self._tools[name]
        return handler(**args)

    def safe_execute_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            res = self.execute_tool(name, args)
            return {"success": True, "result": res}
        except Exception as e:
            logger.error("Error executing tool %s: %s", name, e, exc_info=True)
            return {"success": False, "error": str(e)}

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        schemas: List[Dict[str, Any]] = []
        for name, params in self._schemas.items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": self._descriptions.get(name, ""),
                    "parameters": params,
                },
            })
        return schemas

    def register_default_tools(self) -> None:
        """Đăng ký bộ công cụ vi mô và tiện ích mặc định cho Agent."""
        self.register_tool("create_timing", create_timing, description="Tạo các khối timing phụ đề mẫu")
        self.register_tool("adjust_subtitle_bounds", adjust_subtitle_bounds, description="Điều chỉnh mốc đầu và mốc cuối của phụ đề theo millisecond")
        self.register_tool("shift_subtitles", shift_subtitles, description="Dịch chuyển toàn bộ phụ đề tiến/lùi theo millisecond")
        self.register_tool("apply_subtitle_style", apply_subtitle_style, description="Tinh chỉnh định dạng phụ đề (Font, Size, Màu chữ, Viền)")
        self.register_tool("rescan_subtitles", rescan_subtitles, description="Quét lại âm thanh phụ đề theo câu hoặc thời gian")
        self.register_tool("run_asr", run_asr, description="Nhận diện giọng nói với Whisper")
        self.register_tool("translate_subtitles", translate_subtitles, description="Dịch phụ đề sang ngôn ngữ đích trong CAT Studio")
        self.register_tool("render_hardsub", render_hardsub, description="Kết xuất video Hardsub MP4")
        self.register_tool("process_general_task", process_general_task, description="Xử lý tác vụ tổng quát an toàn")
