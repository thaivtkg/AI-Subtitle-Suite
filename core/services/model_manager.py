import errno
import shutil
import stat
from pathlib import Path
from core.runtime.runtime_paths import RuntimePaths


class ModelStorageError(RuntimeError):
    def __init__(self, operation: str, path: Path):
        self.operation = operation
        self.path = Path(path)
        super().__init__(f"Model storage unavailable during {operation}: {self.path}")


class ModelManager:
    SUPPORTED_MODELS = {
        "tiny": "150 MB", "base": "290 MB", "small": "960 MB",
        "large-v3-turbo": "1.6 GB", "medium": "3.0 GB",
        "large-v1": "5.8 GB", "large-v2": "5.8 GB", "large-v3": "5.8 GB"
    }

    SPECIALIZED_MODELS = {
        "kotoba-whisper-v2.0": {
            "repo_id": "kotoba-tech/kotoba-whisper-v2.0-faster",
            "weight": "1.5 GB",
            "language": "ja",
            "label": "kotoba-v2.0 [JA]",
        },
        "kotoba-whisper-v2.2": {
            "repo_id": "RoachLin/kotoba-whisper-v2.2-faster",
            "weight": "1.5 GB",
            "language": "ja",
            "label": "kotoba-v2.2 [JA]",
        },
    }

    @classmethod
    def resolve_repo_id(cls, model_size: str) -> str:
        spec = cls.SPECIALIZED_MODELS.get(model_size)
        return spec["repo_id"] if spec else model_size

    @classmethod
    def get_specialized_info(cls, model_size: str) -> dict | None:
        return cls.SPECIALIZED_MODELS.get(model_size)

    @staticmethod
    def supports_word_timestamps(model_size: str | None) -> bool:
        """Distilled models (kotoba/distil) with 2 decoder layers crash CTranslate2 align() on large-v3 alignment_heads."""
        lowered = str(model_size or "").strip().lower()
        return not ("kotoba" in lowered or "distil" in lowered)

    @staticmethod
    def _has_ct2_files(directory: Path, operation: str, models_dir: Path) -> bool:
        has_config = ModelManager._storage_stat(
            directory / "config.json", operation, models_dir
        ) is not None
        has_bin = ModelManager._storage_stat(
            directory / "model.bin", operation, models_dir
        ) is not None
        has_st = ModelManager._storage_stat(
            directory / "model.safetensors", operation, models_dir
        ) is not None
        return has_config and (has_bin or has_st)

    @staticmethod
    def _storage_stat(path: Path, operation: str, models_dir: Path):
        try:
            return path.stat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ModelStorageError(operation, models_dir) from exc

    @staticmethod
    def _matches_cache_dir(dir_name: str, model_size: str) -> bool:
        repo_id = ModelManager.resolve_repo_id(model_size)
        hf_slug = repo_id.replace("/", "--")
        return (
            dir_name.endswith(f"--faster-whisper-{model_size}")
            or dir_name == f"faster-whisper-{model_size}"
            or (repo_id != model_size and (dir_name == f"models--{hf_slug}" or dir_name == hf_slug))
        )

    @staticmethod
    def _raise_invalid_storage(operation: str, models_dir: Path):
        cause = NotADirectoryError(
            errno.ENOTDIR, "Model storage path is not a directory", str(models_dir)
        )
        raise ModelStorageError(operation, models_dir) from cause

    @staticmethod
    def _find_cached_snapshot(models_dir: Path, model_size: str, operation: str) -> Path | None:
        try:
            model_dirs = list(models_dir.iterdir())
        except OSError as exc:
            raise ModelStorageError(operation, models_dir) from exc
        for model_dir in model_dirs:
            model_dir_stat = ModelManager._storage_stat(model_dir, operation, models_dir)
            if (
                model_dir_stat is not None
                and stat.S_ISDIR(model_dir_stat.st_mode)
                and ModelManager._matches_cache_dir(model_dir.name, model_size)
            ):
                snapshots_dir = model_dir / "snapshots"
                snapshots_stat = ModelManager._storage_stat(snapshots_dir, operation, models_dir)
                if snapshots_stat is not None and stat.S_ISDIR(snapshots_stat.st_mode):
                    try:
                        snapshots = list(snapshots_dir.iterdir())
                    except OSError as exc:
                        raise ModelStorageError(operation, models_dir) from exc
                    for snapshot in snapshots:
                        snapshot_stat = ModelManager._storage_stat(snapshot, operation, models_dir)
                        if (
                            snapshot_stat is not None
                            and stat.S_ISDIR(snapshot_stat.st_mode)
                            and ModelManager._storage_stat(snapshot / "config.json", operation, models_dir) is not None
                        ):
                            return snapshot
        return None

    @staticmethod
    def get_model_path_for_inference(model_size: str) -> str:
        resolved = ModelManager.resolve_repo_id(model_size)
        models_dir = RuntimePaths.get_models_dir()
        offline_path = models_dir / model_size

        models_stat = ModelManager._storage_stat(
            models_dir, "resolve model", models_dir
        )
        if models_stat is None:
            return resolved
        if not stat.S_ISDIR(models_stat.st_mode):
            ModelManager._raise_invalid_storage("resolve model", models_dir)

        if ModelManager._has_ct2_files(offline_path, "resolve model", models_dir):
            return str(offline_path)

        if resolved != model_size:
            snapshot = ModelManager._find_cached_snapshot(models_dir, model_size, "resolve model")
            if snapshot is not None:
                return str(snapshot)

        return resolved

    @staticmethod
    def prepare_models_storage(operation: str) -> Path:
        models_dir = RuntimePaths.get_models_dir()
        existing_path_error = None
        try:
            try:
                models_dir.mkdir(parents=True, exist_ok=True)
            except FileExistsError as exc:
                # Probe separately: pathlib may report FileExistsError when
                # its exist_ok check cannot stat an inaccessible directory.
                existing_path_error = exc
            models_stat = models_dir.stat()
        except OSError as exc:
            raise ModelStorageError(operation, models_dir) from exc
        if not stat.S_ISDIR(models_stat.st_mode):
            cause = existing_path_error or NotADirectoryError(
                errno.ENOTDIR, "Model storage path is not a directory", str(models_dir)
            )
            raise ModelStorageError(operation, models_dir) from cause
        return models_dir

    @staticmethod
    def is_installed(model_size: str) -> bool:
        models_dir = RuntimePaths.get_models_dir()
        models_stat = ModelManager._storage_stat(
            models_dir, "discover models", models_dir
        )
        if models_stat is None:
            return False
        if not stat.S_ISDIR(models_stat.st_mode):
            ModelManager._raise_invalid_storage("discover models", models_dir)

        offline_path = models_dir / model_size
        if ModelManager._has_ct2_files(offline_path, "discover models", models_dir):
            return True

        return ModelManager._find_cached_snapshot(models_dir, model_size, "discover models") is not None

    @staticmethod
    def ensure_windows_hf_no_symlink() -> None:
        """Disable HF symlink creation on Windows to avoid WinError 1314 without Developer Mode."""
        import os
        if os.name != "nt":
            return
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        try:
            import huggingface_hub.file_download as fd
            fd.are_symlinks_supported = lambda *_args, **_kwargs: False
        except Exception:
            pass

    @staticmethod
    def download_model_sync(model_size: str):
        """[BLOCKER 1 FIX] Download API - Tải model trực tiếp qua HuggingFace"""
        from faster_whisper import download_model
        # Tải và lưu vào đúng models_dir theo kiến trúc S7.2
        models_dir = ModelManager.prepare_models_storage("download model")
        ModelManager.ensure_windows_hf_no_symlink()
        repo_or_size = ModelManager.resolve_repo_id(model_size)
        download_model(repo_or_size, cache_dir=str(models_dir))

    @staticmethod
    def delete_model(model_size: str) -> bool:
        models_dir = RuntimePaths.get_models_dir()
        deleted = False
        offline_path = models_dir / model_size
        if offline_path.exists():
            shutil.rmtree(offline_path, ignore_errors=True)
            deleted = True
            
        if models_dir.exists():
            for d in models_dir.iterdir():
                if d.is_dir() and ModelManager._matches_cache_dir(d.name, model_size):
                    shutil.rmtree(d, ignore_errors=True)
                    deleted = True
        return deleted

    @staticmethod
    def import_offline_model(model_size: str, source_folder: str) -> bool:
        source_path = Path(source_folder)
        if not source_path.exists() or not (source_path / "config.json").exists():
            raise ValueError("Thư mục không hợp lệ! Cần chứa file config.json của CTranslate2.")
        models_dir = ModelManager.prepare_models_storage("import model")
        target_dir = models_dir / model_size
        shutil.copytree(source_path, target_dir, dirs_exist_ok=True)
        return True

    @classmethod
    def get_discovery_list(cls) -> list:
        results = []
        for size, weight in cls.SUPPORTED_MODELS.items():
            results.append({
                "size": size,
                "weight": weight,
                "installed": cls.is_installed(size)
            })
        return results

    @classmethod
    def get_specialized_discovery_list(cls) -> list:
        results = []
        for model_id, meta in cls.SPECIALIZED_MODELS.items():
            results.append({
                "size": model_id,
                "repo_id": meta["repo_id"],
                "weight": meta["weight"],
                "language": meta["language"],
                "label": meta["label"],
                "installed": cls.is_installed(model_id),
            })
        return results
