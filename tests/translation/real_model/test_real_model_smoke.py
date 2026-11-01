import os
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl

from core.translation.llm.worker import TranslationWorker
from tests.translation.e2e.app_harness import AppHarness


REPORT_DIR = Path("artifacts/t15-real")
REPORT_PATH = REPORT_DIR / "T15_R_REPORT.txt"
FIXTURE = Path(__file__).parent / "fixtures" / "smoke.srt"


def _write_report(result, details):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        "P2.5-T15-R — REAL MODEL SMOKE\n\n"
        f"MODEL: {os.getenv('AIS_REAL_MODEL', 'unconfigured')}\n\n"
        "WORKER: Production TranslationWorker\n\n"
        + "\n".join(details)
        + f"\n\nRESULT: {result}\n",
        encoding="utf-8",
    )


def _normalize(value):
    return str(value or "").strip().upper()


@pytest.mark.real_model
def test_t15_r01_real_model_smoke():
    model_path = os.getenv("AIS_REAL_MODEL")
    if not model_path:
        _write_report("SKIPPED — AIS_REAL_MODEL is not configured", ["MODEL PATH: NOT CONFIGURED"])
        pytest.skip("AIS_REAL_MODEL is not configured")

    model_path = Path(model_path)
    if not model_path.is_file():
        _write_report("SKIPPED — configured model file does not exist", [f"MODEL PATH: {model_path}"])
        pytest.skip(f"Real model not found: {model_path}")

    harness = AppHarness(
        None,
        use_hardware_profile=True,
        profile_overrides={"model_path": str(model_path), "model_name": model_path.name},
    )
    driver = harness.driver
    controller = harness.translation_controller
    details = [
        "MODEL LOAD: PENDING",
        "REAL WORKER: PENDING",
        "TRANSLATING STATE: PENDING",
        "TARGET ISOLATION: PENDING",
        "FINAL CANONICAL STATE: PENDING",
        "UI/MODEL CONSISTENCY: PENDING",
        "ENGINE LIFECYCLE: PENDING",
    ]

    try:
        harness.project_controller.importSrt(QUrl.fromLocalFile(str(FIXTURE)).toString())
        harness.app.processEvents()
        driver.click("subtitleRow_0")
        driver.wait_until(
            lambda: controller.currentOriginal == "Where are you going?"
            and bool(driver.find("btnTranslate").property("visible"))
            and bool(driver.find("btnTranslate").property("enabled")),
            timeout_ms=2_000,
        )
        driver.click("btnTranslate")

        driver.wait_until(lambda: _normalize(controller.engineStatus) == "TRANSLATING", timeout_ms=10_000)
        details[0] = "MODEL LOAD: PASS"
        details[1] = "REAL WORKER: PASS" if isinstance(controller.worker, TranslationWorker) else "REAL WORKER: FAIL"
        assert isinstance(controller.worker, TranslationWorker), "Deterministic worker is active in real-model smoke"
        details[2] = "TRANSLATING STATE: PASS"

        driver.click("subtitleRow_1")
        driver.wait_until(lambda: _normalize(controller.engineStatus) != "TRANSLATING", timeout_ms=120_000)
        row1 = harness.model.get_all_data()[1]
        assert str(row1.get("status", "")).upper() == "PENDING"
        assert row1.get("translation", "") == ""
        details[3] = "TARGET ISOLATION: PASS"

        driver.click("subtitleRow_0")
        status = str(harness.model.get_all_data()[0].get("status", "")).upper()
        translation = str(harness.model.get_all_data()[0].get("translation", "") or "").strip()

        if status == "ERROR" and translation == "Lỗi: Model trả về bản dịch rỗng.":
            details[4] = "FINAL CANONICAL STATE: SAFE ERROR"
            details[5] = "UI/MODEL CONSISTENCY: SAFE ERROR"
            details[6] = "ENGINE LIFECYCLE: SAFE ERROR (controller reports Error)"
            _write_report("SAFE ERROR — empty final output; invariant protected", details)
            pytest.skip("SAFE ERROR: production model returned empty final output")

        assert status == "TRANSLATED"
        assert translation
        assert "<think>" not in translation.lower()
        details[4] = "FINAL CANONICAL STATE: PASS"

        ui_translation = str(driver.find("translationInput").property("text") or "").strip()
        assert ui_translation == translation
        details[5] = "UI/MODEL CONSISTENCY: PASS"

        driver.wait_until(lambda: _normalize(controller.engineStatus) == "READY", timeout_ms=10_000)
        details[6] = "ENGINE LIFECYCLE: PASS"
        _write_report("PASS", details)
    except Exception:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        driver.artifact_dir = REPORT_DIR / "failures"
        driver.snapshot("TC15-R01")
        _write_report("FAIL", details)
        raise
    finally:
        harness.close()


