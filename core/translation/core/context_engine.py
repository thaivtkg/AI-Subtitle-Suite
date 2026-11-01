class ContextEngine:
    @staticmethod
    def get_context(subtitles, current_index):
        prev_ctx = []
        next_ctx = []
        
        # Lấy tối đa 3 câu trước (PREVIOUS)
        start_prev = max(0, current_index - 3)
        for i in range(start_prev, current_index):
            sub = subtitles[i]
            status = str(sub.get("status", "")).strip().upper()
            translation = str(sub.get("translation", "")).strip()
            
            # Đồng bộ hội thoại: Sử dụng bản dịch nếu câu đã duyệt, đã dịch hoặc đã sửa
            if status in ("ACCEPTED", "TRANSLATED", "EDITED") and translation:
                prev_ctx.append(translation)
            else:
                prev_ctx.append(sub.get("original", ""))
                
        # Lấy tối đa 3 câu sau (NEXT - Luôn dùng Original vì tương lai chưa dịch/duyệt)
        end_next = min(len(subtitles), current_index + 4)
        for i in range(current_index + 1, end_next):
            sub = subtitles[i]
            next_ctx.append(sub.get("original", ""))
            
        current_sub = subtitles[current_index].get("original", "")
        
        return prev_ctx, current_sub, next_ctx
