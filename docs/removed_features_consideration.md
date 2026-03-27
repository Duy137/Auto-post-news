# Các Tính Năng Đã Bị Vô Hiệu Hóa — Cân Nhắc Khôi Phục

Tài liệu này ghi lại 2 tính năng đã bị loại bỏ trong V4.7 để tránh mất context.
Chúng có thể liên quan đến vấn đề trùng lặp chủ đề đang xảy ra.

---

## 1. ADAPTIVE_FATIGUE_WINDOWS (Vô hiệu hóa: V4.7)

### Tác dụng gốc
Trừ **-0.5 điểm** vào editorial score nếu topic của bài báo đã "già" hơn ngưỡng cấu hình:

```python
ADAPTIVE_FATIGUE_WINDOWS = {
    "default": 72,    # 3 ngày
    "hack": 24,       # 1 ngày  
    "etf": 168,       # 7 ngày
    "sec": 168,       # 7 ngày
}
# Logic:
entity_type = "hack" if has_negative_event else "etf" if "etf" in text else "default"
window = ADAPTIVE_FATIGUE_WINDOWS.get(entity_type, 72)
root_age_hours = (current_ts - root_created_ts) / 3600
fatigue_penalty = -0.5 if root_age_hours > window else 0.0
```

### Lý do bị vô hiệu hóa
- Mức phạt -0.5đ quá nhỏ so với quy mô điểm hiện tại (hệ thống có thể chấm 20-30đ)
- Chỉ hoạt động cho 3 loại từ khóa cứng: `hack`, `etf`, `sec` — không công bằng
- Hai vụ hack riêng biệt cùng ngày sẽ bị trừ oan

### Hướng cải tiến nếu đưa trở lại
- Dùng điểm phạt mạnh hơn: `-3.0` đến `-5.0` (thay vì -0.5)
- Mở rộng thành cơ chế dựa trên `event_root_id` thay vì keyword (đã có sẵn `root_created_ts`)
- Áp dụng cho **mọi topic** theo tuổi đời `root_created_ts`, không cần phân loại keyword cứng
- Công thức mẫu: `fatigue_penalty = -1.5 * max(0, (root_age_hours - 6) / 24)` (tăng dần sau 6h)

---

## 2. ADAPTIVE KEYWORD WEIGHT / Adaptive Scoring (Vô hiệu hóa: V4.7)

### Tác dụng gốc
Giảm điểm từ khóa nếu từ khóa đó đã xuất hiện nhiều lần trong 24h qua (tin tức nhiễu):

```python
# Cũ — sử dụng tần suất keyword từ DB keyword_logs
def get_adaptive_keyword_weight(keyword: str, kw_freqs: Dict[str, int]) -> float:
    freq = kw_freqs.get(keyword, 0)
    weight = 1 / math.log10(freq + 10)  # Càng xuất hiện nhiều → trọng số càng nhỏ
    return weight
```

Ví dụ: Từ "David Sacks" xuất hiện 50 lần trong 24h →  
`weight = 1 / log10(60) ≈ 0.56` → Bài nhắc đến David Sacks chỉ nhận 56% điểm normal.

### Lý do bị vô hiệu hóa
- Làm điểm trở nên **bất định** (non-deterministic) — khó debug, khó predict
- Keyword bình thường bị phạt oan nếu topic đó vô tình phổ biến trong ngày
- Yêu cầu đọc DB mỗi round → thêm latency và complexity

### Hướng cải tiến nếu đưa trở lại
- **Thay thế bằng Story Budget**: Đếm số bài đã đăng về cùng `event_root_id` trong 24h qua
- Nếu đã đăng >= 2 bài cùng event_root → Phạt bài tiếp theo mạnh (×0.2)
- Không cần theo dõi keyword_freq — chỉ cần join với bảng `published_events` đã có sẵn

---

## Đánh Giá Tác Động Đối Với Vấn Đề Hiện Tại

| Vấn đề quan sát được | Liên quan đến tính năng bị bỏ? |
|:---|:---|
| David Sacks xuất hiện 2 lần | Adaptive Weight có thể đã giảm điểm bài thứ 2. Tuy nhiên **nguyên nhân chính** là RSS pipeline không ghi fingerprint vào DB sau khi đăng → Suppression Guard mù. |
| SEC/Lawmaker xuất hiện 2 lần | Tương tự trên. Deduplicator không bắt được vì tiêu đề khác nhau đủ (Jaccard < 0.45). |
| Thiếu bài về Altcoin | Không liên quan đến 2 tính năng bị bỏ. Nguyên nhân: macro/chính trị có điểm rổ cao hơn (macro_politics +8, business_dev +10). |

> **Kết luận:** Vấn đề trùng lặp **KHÔNG CHỦ YẾU** do bỏ 2 tính năng này. Nguyên nhân cốt lõi là:  
> 1. RSS publisher không gọi `insert_recent_topic()` sau khi đăng thành công.  
> 2. Deduplicator đã hoạt động đúng nhưng ngưỡng Jaccard 0.45 quá cao (title khác nhau nhưng cùng chủ đề vẫn lọt qua).
