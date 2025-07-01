import time

def detect_ai_like_answer(answer_text, typing_start_time, total_start_time, min_chars=30, max_cps=3.0, min_suspect_chars=50):
    """
    用於偵測是否為可疑的 AI 或複製貼上輸入。
    
    回傳: (is_suspected: bool, cps: float)
    """
    char_len = len(answer_text.strip())

    if char_len < min_chars:
        return False, 0.0

    duration = time.time() - typing_start_time
    cps = char_len / duration if duration > 0 else float('inf')

    is_copy = cps > max_cps and char_len >= min_suspect_chars
    return is_copy, cps