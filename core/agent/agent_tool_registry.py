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
    segments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Điều chỉnh mốc thời gian bắt đầu và kết thúc của các câu phụ đề theo millisecond."""
    from ui.SubEditor import ms_to_time_str, time_str_to_ms
    segs = segments or []
    modified_segs = []
    for i, s in enumerate(segs):
        sc = dict(s)
        st = max(0, time_str_to_ms(sc.get("start", 0)) + delta_start_ms)
        en = max(st + 200, time_str_to_ms(sc.get("end", 0)) + delta_end_ms)
        sc["start"] = ms_to_time_str(st)
        sc["end"] = ms_to_time_str(en)
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
        "status": "ok",
    }


def shift_subtitles(
    offset_ms: int = 0,
    scope: str = "all",
    segments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Dịch chuyển toàn bộ phụ đề tiến hoặc lùi theo millisecond."""
    from ui.SubEditor import ms_to_time_str, time_str_to_ms
    segs = segments or []
    shifted = []
    for s in segs:
        sc = dict(s)
        st = max(0, time_str_to_ms(sc.get("start", 0)) + offset_ms)
        en = max(st + 200, time_str_to_ms(sc.get("end", 0)) + offset_ms)
        sc["start"] = ms_to_time_str(st)
        sc["end"] = ms_to_time_str(en)
        shifted.append(sc)

    return {
        "segments": shifted,
        "count": len(shifted),
        "offset_ms": offset_ms,
        "status": "ok",
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
