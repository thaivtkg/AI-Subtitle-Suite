from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class AgentStep:
    id: str
    title: str
    tool_name: str
    tool_args: Dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result_summary: Optional[str] = None
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "status": self.status.value if isinstance(self.status, StepStatus) else str(self.status),
            "result_summary": self.result_summary,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentStep":
        status_val = data.get("status", StepStatus.PENDING)
        if isinstance(status_val, str):
            try:
                status_enum = StepStatus(status_val)
            except ValueError:
                status_enum = StepStatus.PENDING
        else:
            status_enum = status_val

        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            tool_name=data.get("tool_name", ""),
            tool_args=data.get("tool_args", {}) or {},
            status=status_enum,
            result_summary=data.get("result_summary"),
            error_message=data.get("error_message"),
            created_at=data.get("created_at", time.time()),
            completed_at=data.get("completed_at"),
        )


@dataclass
class AgentTaskPlan:
    prompt: str
    steps: List[AgentStep] = field(default_factory=list)
    current_step_index: int = 0
    status: StepStatus = StepStatus.PENDING
    created_at: float = field(default_factory=time.time)

    def current_step(self) -> Optional[AgentStep]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def advance_step(self) -> bool:
        if self.current_step_index + 1 < len(self.steps):
            self.current_step_index += 1
            return True
        return False

    def is_finished(self) -> bool:
        return self.current_step_index >= len(self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "status": self.status.value if isinstance(self.status, StepStatus) else str(self.status),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentTaskPlan":
        steps = [AgentStep.from_dict(s) for s in data.get("steps", [])]
        status_val = data.get("status", StepStatus.PENDING)
        if isinstance(status_val, str):
            try:
                status_enum = StepStatus(status_val)
            except ValueError:
                status_enum = StepStatus.PENDING
        else:
            status_enum = status_val

        return cls(
            prompt=data.get("prompt", ""),
            steps=steps,
            current_step_index=data.get("current_step_index", 0),
            status=status_enum,
            created_at=data.get("created_at", time.time()),
        )


@dataclass
class ChatMessage:
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatMessage":
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}) or {},
        )


@dataclass
class AgentContextLedger:
    project_id: str = ""
    video_path: str = ""
    duration_ms: int = 0
    source_lang: str = "auto"
    target_lang: str = "vi"
    active_rules: List[str] = field(default_factory=list)
    style_settings: Dict[str, Any] = field(default_factory=dict)

    def lock_rule(self, rule: str) -> None:
        clean = rule.strip()
        if clean and clean not in self.active_rules:
            self.active_rules.append(clean)

    def remove_rule(self, rule: str) -> None:
        clean = rule.strip()
        if clean in self.active_rules:
            self.active_rules.remove(clean)

    def set_style_setting(self, key: str, value: Any) -> None:
        self.style_settings[key] = value

    def active_rule_count(self) -> int:
        return len(self.active_rules)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "video_path": self.video_path,
            "duration_ms": self.duration_ms,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "active_rules": list(self.active_rules),
            "style_settings": dict(self.style_settings),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentContextLedger":
        return cls(
            project_id=data.get("project_id", ""),
            video_path=data.get("video_path", ""),
            duration_ms=data.get("duration_ms", 0),
            source_lang=data.get("source_lang", "auto"),
            target_lang=data.get("target_lang", "vi"),
            active_rules=list(data.get("active_rules", [])),
            style_settings=dict(data.get("style_settings", {})),
        )
