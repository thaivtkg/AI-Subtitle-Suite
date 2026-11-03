import os
import json
import uuid
from datetime import datetime
from dataclasses import asdict

from core.project.project import Project, SourceInfo as ProjectSourceInfo
from core.project.source_fingerprint import generate_source_info, SourceInfo
from core.project.project_state import ProjectState, WorkspaceState, TimingState
from core.subtitle_placement import SubtitlePlacementState
from core.project.transcription_context import TranscriptionContext
from core.artifacts.artifact_store import ArtifactStore
from core.utils.file_utils import atomic_save_json
from core.timing.timing_checkpoint import TimingCheckpoint


class MissingVideoError(FileNotFoundError):
    """Ngoại lệ khi mở dự án mà không tìm thấy file video gốc."""

    def __init__(
        self,
        video_path: str,
        project_dir: str,
        source_info: ProjectSourceInfo,
        suggested_path: str | None = None,
    ):
        self.video_path = video_path
        self.project_dir = project_dir
        self.source_info = source_info
        self.suggested_path = suggested_path
        msg = f"Không tìm thấy file video gốc tại:\n{video_path}\nVui lòng kiểm tra lại thư mục."
        if suggested_path:
            msg += f"\nĐã tìm thấy tệp khả dụng cùng tên tại:\n{suggested_path}"
        super().__init__(msg)


class ProjectService:
    """Service điều phối toàn bộ Vòng đời của Dự án (Tạo, Lưu, Mở, Đóng)"""
    
    def __init__(self, artifact_store: ArtifactStore | None = None):
        self.artifact_store = artifact_store or ArtifactStore()
        self.current_project: Project | None = None
        self.project_dir: str | None = None

    @staticmethod
    def serialize_project_state(state: ProjectState) -> dict:
        """Build the canonical persisted state payload without performing I/O."""
        return {
            "task_mode": state.task_mode,
            "timing_status": state.timing_status,
            "text_status": state.text_status,
            "export_status": state.export_status,
            "active_artifact_id": state.active_artifact_id,
            "subtitle_artifact_id": state.subtitle_artifact_id,
            "selected_segment_id": state.selected_segment_id,
            "dirty": False,
            "subtitle_placement": asdict(state.subtitle_placement),
            "subtitle_style": getattr(state, "subtitle_style", {}),
            "segment_styles": getattr(state, "segment_styles", {}),
            "style_presets": getattr(state, "style_presets", {}),
            "timing": asdict(state.timing),
        }

    def save_draft(self, filepath: str, segments: list[dict], video_path: str = ""):
        data = {"version": 2.0, "video_path": video_path, "segments": []}
        for segment in segments:
            segment_id = segment.get("id") or uuid.uuid4().hex
            segment["id"] = segment_id
            seg_dict = {
                "id": segment_id, "stt": str(segment.get("stt", "")),
                "start": segment.get("start", 0), "end": segment.get("end", 0),
                "text": segment.get("text", ""), "status": segment.get("status", "draft"),
                "metadata": segment.get("metadata", {"type": "normal"}),
            }
            if "style_preset" in segment:
                seg_dict["style_preset"] = segment["style_preset"]
            data["segments"].append(seg_dict)
        with open(filepath, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)

    def load_draft(self, filepath: str) -> dict:
        with open(filepath, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        result = []
        for index, segment in enumerate(data.get("segments", [])):
            raw_stt, raw_id = segment.get("stt"), segment.get("id")
            legacy = raw_stt in (None, "")
            seg_dict = {
                "id": uuid.uuid4().hex if legacy else (raw_id or uuid.uuid4().hex),
                "stt": str(raw_id or index + 1) if legacy else str(raw_stt),
                "start": segment.get("start", segment.get("start_ms", 0)),
                "end": segment.get("end", segment.get("end_ms", 0)),
                "text": segment.get("text", ""), "status": segment.get("status", "draft"),
                "metadata": segment.get("metadata", {"type": "normal"}),
            }
            if "style_preset" in segment:
                seg_dict["style_preset"] = segment["style_preset"]
            result.append(seg_dict)
        return {"version": data.get("version", 1.0), "segments": result, "video_path": data.get("video_path", "")}

    def _generate_fingerprint(self, video_path: str) -> SourceInfo:
        return generate_source_info(video_path)

    def create_project(self, project_dir: str, name: str, video_path: str) -> Project:
        """Tạo một Project mới hoàn toàn"""
        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(os.path.join(project_dir, "artifacts"), exist_ok=True)
        
        generated_source = self._generate_fingerprint(video_path)
        source_info = ProjectSourceInfo(**generated_source.__dict__)
        now_str = datetime.now().isoformat()
        
        self.current_project = Project(
            project_id=str(uuid.uuid4()),
            name=name,
            created_at=now_str,
            updated_at=now_str,
            source=source_info,
            state=ProjectState()
        )
        self.project_dir = project_dir
        self.artifact_store.clear()
        
        self.save_project()
        return self.current_project

    def create_auto_project(
        self,
        output_dir: str,
        name: str,
        video_path: str,
        session_id: str,
    ) -> Project:
        """Create isolated state for a raw Queue import in this app session."""
        safe_name = "".join(
            char if char.isalnum() else "_"
            for char in os.path.splitext(name)[0]
        ).strip("_") or "video"
        safe_session_id = "".join(
            char for char in str(session_id) if char.isalnum()
        ) or uuid.uuid4().hex
        project_dir = os.path.join(
            output_dir, f"{safe_name}_auto_{safe_session_id}.ai-subtitle"
        )
        return self.create_project(project_dir, name, video_path)

    SUPPORTED_VIDEO_EXTENSIONS = {
        ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts"
    }

    @staticmethod
    def get_canonical_bundle_dir(video_path: str) -> str:
        """Trả về đường dẫn bundle dự án chuẩn mực kề bên file video."""
        folder = os.path.dirname(os.path.abspath(video_path))
        filename = os.path.basename(video_path)
        stem = os.path.splitext(filename)[0]
        safe_name = "".join(
            char if char.isalnum() or char in ("-", "_") else "_"
            for char in stem
        ).strip("_") or "video"

        stem_bundle = os.path.join(folder, f"{stem}.ai-subtitle")
        safe_bundle = os.path.join(folder, f"{safe_name}.ai-subtitle")
        if os.path.isdir(stem_bundle):
            return stem_bundle
        if os.path.isdir(safe_bundle):
            return safe_bundle
        return safe_bundle

    def scan_video_folder(self, folder_path: str) -> list[dict]:
        """Quét thư mục chứa các file video và phát hiện bundle dự án tương ứng."""
        if not folder_path or not os.path.isdir(folder_path):
            return []

        results = []
        try:
            entries = os.listdir(folder_path)
        except OSError:
            return []

        for entry in entries:
            if entry.startswith("."):
                continue
            full_path = os.path.join(folder_path, entry)
            if not os.path.isfile(full_path):
                continue
            ext = os.path.splitext(entry)[1].lower()
            if ext not in self.SUPPORTED_VIDEO_EXTENSIONS:
                continue

            try:
                size_bytes = os.path.getsize(full_path)
            except OSError:
                size_bytes = 0
            size_mb = round(size_bytes / (1024 * 1024), 2)
            if size_mb >= 1024:
                size_str = f"{round(size_mb / 1024, 2)} GB"
            else:
                size_str = f"{size_mb} MB"

            expected_dir = self.get_canonical_bundle_dir(full_path)
            has_project = os.path.isdir(expected_dir) and os.path.exists(
                os.path.join(expected_dir, "project.json")
            )

            results.append({
                "video_path": os.path.abspath(full_path),
                "filename": entry,
                "size_mb": size_mb,
                "size_str": size_str,
                "has_project": has_project,
                "expected_project_dir": expected_dir,
            })

        results.sort(key=lambda item: item["filename"].lower())
        return results

    def create_or_get_folder_project(self, video_path: str) -> tuple[Project, bool]:
        """Tạo dự án mới kề bên video nếu chưa có; mở lại dự án cũ nếu đã tồn tại."""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Không tìm thấy file video tại: {video_path}")

        bundle_dir = self.get_canonical_bundle_dir(video_path)
        proj_json = os.path.join(bundle_dir, "project.json")

        if os.path.isdir(bundle_dir) and os.path.exists(proj_json):
            project = self.open_project(bundle_dir)
            return project, False

        name = os.path.splitext(os.path.basename(video_path))[0]
        project = self.create_project(bundle_dir, name, video_path)
        return project, True

    def save_project(self) -> None:
        """Lưu Project hiện tại xuống đĩa cứng, chia thành các file riêng biệt"""
        if not self.current_project or not self.project_dir:
            return
            
        self.current_project.updated_at = datetime.now().isoformat()
        normalized_context = self.current_project.transcription_context.normalized()
        self.current_project.transcription_context = normalized_context
        
        # 1. Lưu project.json
        proj_data = {
            "schema_version": self.current_project.schema_version,
            "project_id": self.current_project.project_id,
            "name": self.current_project.name,
            "created_at": self.current_project.created_at,
            "updated_at": self.current_project.updated_at,
            "source": asdict(self.current_project.source),
            "transcription_context": asdict(normalized_context),
        }
        atomic_save_json(os.path.join(self.project_dir, "project.json"), proj_data)
        
        # 2. Lưu state.json
        state_data = self.serialize_project_state(self.current_project.state)
        atomic_save_json(os.path.join(self.project_dir, "state.json"), state_data)
        
        # 3. Lưu workspace.json
        workspace_data = asdict(self.current_project.state.workspace)
        atomic_save_json(os.path.join(self.project_dir, "workspace.json"), workspace_data)

        # 4. Lưu Artifact Manifest
        manifest_path = os.path.join(self.project_dir, "artifacts", "manifest.json")
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        atomic_save_json(manifest_path, self.artifact_store.to_dict(self.project_dir))
        
        self.current_project.state.dirty = False
        return True

    def probe_project_source(self, project_dir: str) -> tuple[ProjectSourceInfo, str, bool, str | None]:
        """Kiểm tra nguồn video của dự án trước khi mở.
        
        Trả về tuple (source_info, current_path, is_valid, suggested_path).
        """
        proj_file = os.path.join(project_dir, "project.json")
        if not os.path.exists(proj_file):
            raise FileNotFoundError("Thư mục này không phải là một Project AI Subtitle Studio hợp lệ.")
            
        with open(proj_file, 'r', encoding='utf-8') as f:
            p_data = json.load(f)
        source_info = ProjectSourceInfo(**p_data["source"])
        video_path = source_info.path
        
        if os.path.exists(video_path):
            return source_info, video_path, True, None
            
        # Dò tìm ứng viên lân cận (cùng thư mục cha với project_dir hoặc trong project_dir)
        suggested_path = None
        candidates = [
            os.path.join(os.path.dirname(project_dir), source_info.filename),
            os.path.join(project_dir, source_info.filename),
        ]
        for cand in candidates:
            if os.path.exists(cand):
                suggested_path = os.path.normpath(cand)
                break
                
        return source_info, video_path, False, suggested_path

    def relink_project_video(self, project_dir: str, new_video_path: str, force: bool = False) -> ProjectSourceInfo:
        """Định vị lại video gốc cho dự án và cập nhật project.json"""
        if not os.path.exists(new_video_path):
            raise FileNotFoundError(f"Không tìm thấy file video mới tại:\n{new_video_path}")
            
        proj_file = os.path.join(project_dir, "project.json")
        if not os.path.exists(proj_file):
            raise FileNotFoundError("Không tìm thấy tệp project.json trong thư mục dự án.")
            
        with open(proj_file, 'r', encoding='utf-8') as f:
            p_data = json.load(f)
            
        original_source = ProjectSourceInfo(**p_data["source"])
        new_source_info = self._generate_fingerprint(new_video_path)
        
        if not force and original_source.fingerprint != new_source_info.fingerprint:
            raise ValueError(
                f"File video mới có mã băm (Hash) khác với video ban đầu!\n"
                f"Gốc: {original_source.fingerprint[:12]}... - Mới: {new_source_info.fingerprint[:12]}..."
            )
            
        p_data["source"] = asdict(new_source_info) if hasattr(new_source_info, '__dataclass_fields__') else new_source_info.__dict__
        p_data["updated_at"] = datetime.now().isoformat()
        atomic_save_json(proj_file, p_data)
        
        updated_source = ProjectSourceInfo(**p_data["source"])
        if self.current_project and self.project_dir == project_dir:
            self.current_project.source = updated_source
            self.current_project.state.is_video_missing = False
            
        return updated_source

    def open_project(
        self,
        project_dir: str,
        allow_missing_video: bool = False,
        relink_video_path: str | None = None,
    ) -> Project:
        """Đọc và khôi phục Project từ thư mục"""
        if relink_video_path:
            self.relink_project_video(project_dir, relink_video_path, force=True)

        proj_file = os.path.join(project_dir, "project.json")
        state_file = os.path.join(project_dir, "state.json")
        workspace_file = os.path.join(project_dir, "workspace.json")
        
        if not os.path.exists(proj_file):
            raise FileNotFoundError("Thư mục này không phải là một Project AI Subtitle Studio hợp lệ.")
            
        with open(proj_file, 'r', encoding='utf-8') as f:
            p_data = json.load(f)
        source_info = ProjectSourceInfo(**p_data["source"])
        
        # Source Validation
        video_path = source_info.path
        is_missing = False
        if not os.path.exists(video_path):
            if not allow_missing_video:
                _, _, _, suggested = self.probe_project_source(project_dir)
                raise MissingVideoError(video_path, project_dir, source_info, suggested)
            is_missing = True
        else:
            current_source_info = self._generate_fingerprint(video_path)
            if current_source_info.fingerprint != source_info.fingerprint:
                raise ValueError(
                    f"File video gốc đã bị thay đổi hoặc ghi đè (Sai lệch mã Hash)!\n"
                    f"Không thể mở dự án để bảo vệ an toàn cho dữ liệu Timing."
                )
        
        project_state = ProjectState()
        if os.path.exists(state_file):
            with open(state_file, 'r', encoding='utf-8') as f:
                s_data = json.load(f)
                project_state.task_mode = s_data.get("task_mode", "asr")
                project_state.timing_status = s_data.get("timing_status", "EMPTY")
                project_state.text_status = s_data.get("text_status", "EMPTY")
                project_state.export_status = s_data.get("export_status", "EMPTY")
                project_state.active_artifact_id = s_data.get("active_artifact_id")
                project_state.subtitle_artifact_id = s_data.get("subtitle_artifact_id")
                project_state.selected_segment_id = s_data.get("selected_segment_id")

                raw_placement = s_data.get("subtitle_placement")
                if isinstance(raw_placement, dict):
                    try:
                        project_state.subtitle_placement = SubtitlePlacementState(
                            mode=raw_placement.get("mode", "bottom"),
                            x=raw_placement.get("x", 0.5),
                            y=raw_placement.get("y", 0.85),
                        )
                    except (TypeError, ValueError):
                        project_state.subtitle_placement = SubtitlePlacementState()
                project_state.subtitle_style = s_data.get("subtitle_style", {})
                project_state.segment_styles = s_data.get("segment_styles", {})
                project_state.style_presets = s_data.get("style_presets", {})
                
                # --- [S7.1-T05 & T08] Backward Compatibility cho TimingState ---
                if "timing" in s_data:
                    valid_timing_keys = {k for k in s_data["timing"].keys() if k in TimingState.__dataclass_fields__}
                    project_state.timing = TimingState(**{k: s_data["timing"][k] for k in valid_timing_keys})
                else:
                    project_state.timing = TimingState()
                # ---------------------------------------------------------------
        project_state.is_video_missing = is_missing
        
        if os.path.exists(workspace_file):
            with open(workspace_file, 'r', encoding='utf-8') as f:
                w_data = json.load(f)
                valid_ws_keys = {k for k in w_data.keys() if k in WorkspaceState.__dataclass_fields__}
                project_state.workspace = WorkspaceState(**{k: w_data[k] for k in valid_ws_keys})
                
        self.current_project = Project(
            project_id=p_data["project_id"],
            name=p_data["name"],
            created_at=p_data["created_at"],
            updated_at=p_data["updated_at"],
            source=source_info,
            state=project_state,
            transcription_context=TranscriptionContext(
                context=str((p_data.get("transcription_context") or {}).get("context", "")),
                glossary=list((p_data.get("transcription_context") or {}).get("glossary", [])),
                domain=str((p_data.get("transcription_context") or {}).get("domain", "general")),
                lang_pair=str((p_data.get("transcription_context") or {}).get("lang_pair", "")),
            ).normalized(),
            schema_version=max(2, int(p_data.get("schema_version", 1)))
        )
        self.project_dir = project_dir
        self.artifact_store.clear()
        
        manifest_path = os.path.join(self.project_dir, "artifacts", "manifest.json")
        if os.path.exists(manifest_path):
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest_data = json.load(f)
            self.artifact_store.from_dict(manifest_data, self.project_dir)
        
        return self.current_project

    def close_project(self) -> None:
        self.current_project = None
        self.project_dir = None
        self.artifact_store.clear()

    def is_current_project_for_video(self, video_path: str) -> bool:
        """Return whether the open project owns exactly this source video."""
        source_path = getattr(
            getattr(self.current_project, "source", None), "path", None
        )
        if not source_path or not video_path:
            return False
        return os.path.normcase(os.path.abspath(source_path)) == os.path.normcase(
            os.path.abspath(video_path)
        )

    def is_current_project_identity(self, project_id=None, project_root=None) -> bool:
        """Return whether the open project matches an explicit Queue identity."""
        if not self.current_project:
            return False
        if project_id is not None and self.current_project.project_id != project_id:
            return False
        if project_root is not None and not self.project_dir:
            return False
        if project_root is not None and os.path.normcase(os.path.abspath(self.project_dir)) != os.path.normcase(
            os.path.abspath(project_root)
        ):
            return False
        return project_id is not None or project_root is not None

    def requires_project_switch(
        self, video_path: str, fresh_project: bool = False
    ) -> bool:
        """A fresh raw import always owns new state, even for the same file."""
        return bool(fresh_project) or not self.is_current_project_for_video(
            video_path
        )

    def mark_dirty(self) -> None:
        if self.current_project:
            self.current_project.state.dirty = True
            tracker = getattr(self, "revision_tracker", None)
            if tracker is not None and not tracker.is_transitioning:
                tracker.record_external_change()

    # ========================================================
    # [SPRINT 7.1] TIMING CHECKPOINT I/O
    # ========================================================
    def save_timing_checkpoint(self, checkpoint: TimingCheckpoint) -> None:
        """[S7.1-T06] Lưu cấu trúc Checkpoint xuống thư mục con của artifacts"""
        if not self.project_dir:
            return
        checkpoint_dir = os.path.join(self.project_dir, "artifacts", "timing")
        os.makedirs(checkpoint_dir, exist_ok=True)
        checkpoint_path = os.path.join(checkpoint_dir, "checkpoint.json")
        atomic_save_json(checkpoint_path, asdict(checkpoint))

    def load_timing_checkpoint(self) -> TimingCheckpoint | None:
        """Khôi phục Checkpoint, trả về None nếu chưa tồn tại"""
        if not self.project_dir:
            return None
        checkpoint_path = os.path.join(self.project_dir, "artifacts", "timing", "checkpoint.json")
        if os.path.exists(checkpoint_path):
            try:
                with open(checkpoint_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                valid_keys = {k for k in data.keys() if k in TimingCheckpoint.__dataclass_fields__}
                return TimingCheckpoint(**{k: data[k] for k in valid_keys})
            except Exception as e:
                print(f"[ERROR] Không thể nạp Timing Checkpoint: {e}")
                return None
        return None
