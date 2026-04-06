# Tính Năng Đã Bị Vô Hiệu Hóa — Lưu Trữ Lịch Sử

> Cập nhật: 2026-04-07 | Đánh dấu trạng thái sau V5.1

Tài liệu này ghi lại 2 tính năng đã bị loại bỏ trong V4.7. Một phần logic đã được **thay thế** bằng Entity Fatigue V5.1.

---

## 1. ADAPTIVE_FATIGUE_WINDOWS (Bỏ từ V4.7)

### Tác dụng gốc
Trừ **-0.5 điểm** vào editorial score nếu topic đã "già" hơn ngưỡng cấu hình:

```python
ADAPTIVE_FATIGUE_WINDOWS = {
    "default": 72,    # 3 ngày
    "hack": 24,       # 1 ngày  
    "etf": 168,       # 7 ngày
    "sec": 168,       # 7 ngày
}
```

### Lý do bỏ
- Mức phạt -0.5đ quá nhỏ so với quy mô điểm hiện tại (20-30đ)
- Chỉ hoạt động cho 3 từ khóa cứng: `hack`, `etf`, `sec`
- Hai vụ hack riêng biệt cùng ngày sẽ bị trừ oan

### Trạng thái hiện tại
**Đã được thay thế bằng Entity Fatigue V5.1** — dùng `extract_fingerprints()` để detect MỌI entity, phạt tuyến tính (×0.8 / ×0.6 / ×0.4...) theo số lần entity đã POSTED trong 24h. Hiệu quả hơn vì:
- Không giới hạn 3 keyword, detect tất cả proper nouns tự động
- Phạt mạnh hơn nhiều (×0.2 mỗi lần thay vì -0.5 cố định)
- Dựa trên tần suất thực tế, không phải tuổi event

---

## 2. ADAPTIVE KEYWORD WEIGHT (Bỏ từ V4.7)

### Tác dụng gốc
Giảm trọng số keyword nếu keyword đó xuất hiện nhiều lần trong 24h:

```python
def get_adaptive_keyword_weight(keyword, kw_freqs):
    freq = kw_freqs.get(keyword, 0)
    weight = 1 / math.log10(freq + 10)
    return weight
```

### Lý do bỏ
- Non-deterministic — khó debug, khó predict
- Keyword bình thường bị phạt oan nếu topic phổ biến trong ngày
- Yêu cầu đọc DB mỗi round → thêm latency

### Trạng thái hiện tại
**Không được khôi phục.** Entity Fatigue V5.1 đã đảm nhận vai trò tương tự — phạt bài có entity lặp lại nhiều — nhưng ở cấp độ entity (tên riêng, token) thay vì keyword chung chung.

---

## Tổng kết

| Tính năng cũ | Trạng thái | Thay thế bởi |
|:---|:---|:---|
| Adaptive Fatigue Windows | ❌ Bỏ (V4.7) | ✅ Entity Fatigue V5.1 |
| Adaptive Keyword Weight | ❌ Bỏ (V4.7) | ✅ Entity Fatigue V5.1 (một phần) |

Bảng `keyword_logs` trong DB vẫn tồn tại nhưng không còn được ghi hay đọc. Có thể xóa an toàn trong tương lai.
