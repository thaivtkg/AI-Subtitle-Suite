import subprocess
import sys
import os

def build_app():
    print("==================================================")
    print(" BAT DAU QUY TRINH DONG GOI AI SUBTITLE SUITE     ")
    print("==================================================")
    
    project_root = os.path.dirname(os.path.abspath(__file__))
    spec_path = os.path.join(project_root, "AI Subtitle Suite.spec")
    
    venv_python = os.path.join(project_root, ".venv", "Scripts", "python.exe")
    python_bin = venv_python if os.path.exists(venv_python) else sys.executable
    print(f"Using Python: {python_bin}")

    if os.path.exists(spec_path):
        cmd = [
            python_bin, "-m", "PyInstaller",
            spec_path,
            "--noconfirm",
            "--clean"
        ]
    else:
        hidden_imports = [
            "PySide6.QtCore",
            "PySide6.QtGui",
            "PySide6.QtWidgets",
            "PySide6.QtMultimedia",
            "PySide6.QtMultimediaWidgets",
            "PySide6.QtQuick",
            "PySide6.QtQuickWidgets",
            "PySide6.QtQml",
            "pydantic",
            "sqlite3",
            "faster_whisper",
            "ctranslate2",
            "torch",
            "torchaudio",
            "llama_cpp",
            "psutil"
        ]
        datas = ["--add-data=resources;resources"]
        qml_dir = os.path.join(project_root, "ui", "qml_translation")
        if os.path.exists(qml_dir):
            datas.append(f"--add-data={qml_dir};ui/qml_translation")
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--name=AI Subtitle Suite",
            "--windowed",
            "--icon=resources/app_icon.ico",
            "--noconfirm",
            "--clean",
        ]
        for imp in hidden_imports:
            cmd.append(f"--hidden-import={imp}")
        cmd.extend(datas)
        cmd.append("main.py")
        
    print(f"PyInstaller command: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True, cwd=project_root)
        print("\n[SUCCESS] Build thanh cong! Thu muc ket xuat: 'dist/AI Subtitle Suite/'")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Build that bai: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build_app()
