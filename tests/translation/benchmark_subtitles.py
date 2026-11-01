import sys
import time
from pathlib import Path

# Đưa thư mục gốc dự án vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.translation.core.backends.ollama_backend import OllamaBackend

TEST_DATASET = [
    {
        "source_lang": "English",
        "story": "A (nam, 30t, thanh tra cấp cao) và B (nữ, 22t, thực tập sinh). Bối cảnh: Arkham City.",
        "prev": "We need to secure the perimeter before midnight.",
        "current": "Understood, Detective. I won't let you down.",
        "next": "Good. Watch your back."
    },
    {
        "source_lang": "English",
        "story": "Hai người bạn thân cùng tuổi nói chuyện phiếm.",
        "prev": "Did you see that movie yesterday?",
        "current": "No way, I was stuck at work all day!",
        "next": "You missed out big time."
    },
    {
        "source_lang": "Japanese",
        "story": "A (tiền bối) nhắc nhở B (hậu bối).",
        "prev": "気をつけろよ、この先は危険だ。",
        "current": "はい、先輩！ついていきます！",
        "next": "よし、行くぞ。"
    },
    {
        "source_lang": "Chinese (Simplified)",
        "story": "Bối cảnh võ hiệp. A đe dọa đối thủ.",
        "prev": "拿命来！",
        "current": "痴心妄想！就凭你也想动我？",
        "next": "今日就是你的死期！"
    }
]

def build_test_prompt(item: dict) -> tuple[str, str]:
    """Hàm tạo prompt độc lập dùng riêng cho Benchmark"""
    sys_prompt = (
        f"You are a professional subtitle translator. Translate the given subtitle from {item['source_lang']} to Vietnamese.\n"
        f"Rules:\n"
        f"1. Output ONLY the translated subtitle. No explanations, no notes.\n"
        f"2. Use appropriate Vietnamese pronouns based on the Story Summary.\n"
        f"3. Maintain the concise format of subtitles.\n\n"
        f"Story Summary: {item['story']}"
    )

    user_prompt = (
        f"Previous context: {item['prev']}\n"
        f"Current subtitle to translate: {item['current']}\n"
        f"Next context: {item['next']}\n\n"
        f"Vietnamese translation:"
    )

    return sys_prompt, user_prompt

def run_benchmark(models=["translategemma:12b", "qwen2.5:7b"]):
    backend = OllamaBackend()

    print(f"{'='*60}\n🚀 RUNNING SUBTITLE TRANSLATION BENCHMARK\n{'='*60}")

    for model_name in models:
        print(f"\n[MODEL]: {model_name}")
        if not backend.load_model(model_name):
            print(f"❌ Không thể load model {model_name}. Kiểm tra lại Ollama.")
            continue

        total_time = 0.0

        for idx, item in enumerate(TEST_DATASET, 1):
            sys_prompt, user_prompt = build_test_prompt(item)

            start = time.perf_counter()
            result = backend.generate(user_prompt, system_prompt=sys_prompt)
            duration = time.perf_counter() - start
            total_time += duration

            print(f"\n  #{idx} [{item['source_lang']}] -> Time: {duration:.2f}s")
            print(f"  Input   : {item['current']}")
            print(f"  Output  : {result}")

        print(f"\n[AVG SPEED] {model_name}: {total_time/len(TEST_DATASET):.2f}s / câu")
        backend.unload_model()

if __name__ == "__main__":
    run_benchmark()
