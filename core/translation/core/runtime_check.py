import ctypes
import os
import sys
import webbrowser


def check_vc_redist() -> bool:
    """Kiểm tra sự tồn tại của Microsoft Visual C++ 2015-2022 Redistributable (x64) trên Windows."""
    if sys.platform != "win32":
        return True

    required_dlls = ["msvcp140.dll", "vcruntime140.dll"]
    for dll_name in required_dlls:
        try:
            handle = ctypes.windll.kernel32.LoadLibraryW(dll_name)
            if not handle:
                return False
            ctypes.windll.kernel32.FreeLibrary(handle)
        except Exception:
            return False
    return True


def prompt_missing_vc_redist() -> None:
    """Hiển thị hộp thoại Native Win32 khi thiếu VC++ Runtime mà không phụ thuộc vào GUI Framework."""
    MB_YESNO = 0x00000004
    MB_ICONEXCLAMATION = 0x00000030
    IDYES = 6

    title = "Thiếu Microsoft Visual C++ Runtime"
    message = (
        "Ứng dụng AI Subtitle Studio yêu cầu Microsoft Visual C++ 2015-2022 Redistributable (x64) "
        "để khởi chạy mô hình AI và các thư viện tăng tốc đồ họa.\n\n"
        "Hệ thống của bạn hiện chưa cài đặt hoặc thiếu thư viện msvcp140.dll / vcruntime140.dll.\n\n"
        "Bạn có muốn mở trang web để tải và cài đặt bản chính thức từ Microsoft ngay bây giờ không?"
    )

    try:
        user_choice = ctypes.windll.user32.MessageBoxW(0, message, title, MB_YESNO | MB_ICONEXCLAMATION)
        if user_choice == IDYES:
            webbrowser.open("https://aka.ms/vs/17/release/vc_redist.x64.exe")
    except Exception:
        print(f"[FATAL ERROR] {title}: {message}", file=sys.stderr)

    sys.exit(1)


def verify_environment(interactive: bool = True) -> bool:
    """Xác thực toàn bộ môi trường thực thi trước khi nạp bất kỳ thư viện bên thứ ba nào."""
    if not check_vc_redist():
        if interactive:
            prompt_missing_vc_redist()
        return False
    return True
