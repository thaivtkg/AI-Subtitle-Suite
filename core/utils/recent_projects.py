import datetime
import os
from typing import List, Dict
from core.utils.settings_utils import load_settings, save_settings


MAX_RECENT_PROJECTS = 10


def get_recent_projects() -> List[Dict[str, str]]:
    """Đọc danh sách dự án gần đây từ settings, lọc loại bỏ bản ghi không hợp lệ."""
    settings = load_settings()
    items = settings.get("recent_projects", [])
    if not isinstance(items, list):
        return []
    valid = []
    for item in items:
        if isinstance(item, dict) and item.get("path") and item.get("name"):
            valid.append({
                "name": str(item["name"]),
                "path": os.path.normpath(str(item["path"])),
                "video_path": str(item.get("video_path", "")),
                "last_opened": str(item.get("last_opened", "")),
            })
    return valid


def add_recent_project(project_dir: str, name: str, video_path: str = "") -> List[Dict[str, str]]:
    """Thêm một dự án vào đầu danh sách gần đây (MRU order), tối đa 10 dự án."""
    if not project_dir:
        return get_recent_projects()
    norm_path = os.path.normpath(project_dir)
    settings = load_settings()
    items = settings.get("recent_projects", [])
    if not isinstance(items, list):
        items = []

    # Loại bỏ bản ghi cũ nếu đã tồn tại đường dẫn này
    filtered = [
        item for item in items
        if isinstance(item, dict) and os.path.normpath(str(item.get("path", ""))) != norm_path
    ]

    new_entry = {
        "name": name or os.path.basename(norm_path),
        "path": norm_path,
        "video_path": str(video_path or ""),
        "last_opened": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    filtered.insert(0, new_entry)
    updated = filtered[:MAX_RECENT_PROJECTS]

    settings["recent_projects"] = updated
    save_settings(settings)
    return updated


def remove_recent_project(project_dir: str) -> List[Dict[str, str]]:
    """Xóa dự án khỏi danh sách gần đây theo đường dẫn."""
    if not project_dir:
        return get_recent_projects()
    norm_path = os.path.normpath(project_dir)
    settings = load_settings()
    items = settings.get("recent_projects", [])
    if not isinstance(items, list):
        return []

    filtered = [
        item for item in items
        if isinstance(item, dict) and os.path.normpath(str(item.get("path", ""))) != norm_path
    ]
    settings["recent_projects"] = filtered
    save_settings(settings)
    return filtered


def clear_recent_projects() -> None:
    """Xóa sạch lịch sử dự án gần đây."""
    settings = load_settings()
    settings["recent_projects"] = []
    save_settings(settings)
