import concurrent.futures
import pytest
from core.database.tm_manager import TranslationMemoryManager

def test_tm_manager_respects_custom_db_path(tmp_path):
    custom_db = tmp_path / "custom_tm.db"
    tm = TranslationMemoryManager(str(custom_db))
    
    assert tm.db_path == str(custom_db)
    assert custom_db.exists()
    
    tm.add_segment("Hello", "Xin chào", lang_pair="en-vi")
    matches = tm.find_matches("Hello", lang_pair="en-vi")
    assert len(matches) == 1
    assert matches[0].target_text == "Xin chào"
    tm.close()

def test_tm_manager_multithreaded_concurrent_access(tmp_path):
    custom_db = tmp_path / "thread_tm.db"
    tm = TranslationMemoryManager(str(custom_db))
    
    def worker(i):
        tm.add_segment(f"Source sentence {i}", f"Target sentence {i}", lang_pair="en-vi")
        matches = tm.find_matches(f"Source sentence {i}", lang_pair="en-vi")
        assert len(matches) >= 1
        return len(matches)
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(30)]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            assert res >= 1
            
    tm.close()
