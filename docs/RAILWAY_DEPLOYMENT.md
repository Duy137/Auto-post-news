# Hướng Dẫn Kéo Tàu Bot Lên Đám Mây Railway (Cực Kỳ Đơn Giản)

Việc treo máy tính 24/7 ở nhà rất tốn điện và mạng không ổn định. Railway là một dịch vụ máy chủ đám mây siêu việt, tự động lấy code từ GitHub của bạn và chạy suốt ngày đêm.

Để đưa con Bot này lên Railway trơn tru mà không bị lỗi xác thực Telegram (Express Lane), hãy làm chính xác 3 bước sau:

---

## BƯỚC 1: LẤY "CHÌA KHÓA" TELEGRAM STRING SESSION (QUAN TRỌNG NHẤT)
Khi chạy trên Railway, Bot không có màn hình đen (Terminal) để bạn nhập mã Code 5 số mà Telegram gửi về điện thoại. Do đó, ta phải lấy sẵn một "String Session" trên máy tính nhà rồi ném lên Railway.

1. Bật thư mục gốc của Bot lên (trên máy tính của bạn).
2. Chắc chắn file `.env` đã có `TG_API_ID` và `TG_API_HASH`.
3. Mở Terminal, chạy lệnh sau:
   ```bash
   python generate_string_session.py
   ```
4. Nó sẽ hỏi bạn nhập số điện thoại (`+84...`) và mã Code từ App Telegram.
5. Sau khi thành công, nó sẽ in ra một đoạn chữ loằng ngoằng. Hãy **COPY đoạn mã đó**, đây chính là "Chìa Khóa Nhà" của bạn.
6. Mở file `.env` lên, tạo thêm một dòng mới ở dưới cùng:
   ```env
   TG_STRING_SESSION=dán_đoạn_mã_vào_đây
   ```

---

## BƯỚC 2: UP CODE LÊN GITHUB
Railway chỉ có thể tự động lấy code từ tài khoản GitHub của bạn.

1. Hãy xóa file `.env` khỏi repo (hoặc chắc chắn nó đã nằm trong `.gitignore` để không bị lộ API KEY ra ngoài mạng).
2. Tải GitHub Desktop hoặc dùng lệnh Git để Đẩy (Push) toàn bộ thư mục Bot này lên một Repo **Private** (Riêng Tư) mới tinh trên GitHub của bạn.

---

## BƯỚC 3: KẾT NỐI VÀ LÊN ĐỒ TRÊN RAILWAY

1. Vào [Railway.app](https://railway.app), đăng nhập bằng tài khoản GitHub vừa tạo repo.
2. Bấm nút chọn `New Project` -> Chọn `Deploy from GitHub repo`.
3. Tìm đến Repo chứa Code Bot của bạn rồi bấm Deploy.
4. Nó sẽ chạy deploy lần đầu (có thể báo lỗi, mặc kệ nó).

### Cài Đặt Lưu Trữ (Volume) Để Không Bị Mất Trí Nhớ:
Bot cần bộ nhớ để ghi nhớ log và tin nhắn cũ.
1. Nhấp vào Ứng dụng của bạn (thanh hình chữ nhật) -> Qua tab **Volumes**.
2. Bấm tạo một ổ cứng Volume mới.
3. Ở ô **Mount Path**, gõ chính xác: `/app/data`
4. Ấn Save.

### Truyền Biến Môi Trường (Variables):
Bởi vì file `.env` không được đẩy lên GitHub (để bảo mật), bạn phải đưa các "Chìa khóa" vào cài đặt của Railway.
1. Chuyển sang tab **Variables**.
2. Thay vì gõ lại từng dòng, bấm nút **"Raw Editor"**.
3. Copy toàn bộ nội dung trong file `.env` ở máy tính của bạn, dán thả vào ô Raw Editor này. (Đặc biệt đảm bảo đã dán cả dòng `TG_STRING_SESSION` siêu dài kia vào).
4. Bấm `Update Variables`.

Đây là một dự án "Set and Forget" nhưng thỉnh thoảng bạn nên kiểm tra Logs để đảm bảo mọi thứ trơn tru.

### Cách đọc Log Chuyên Nghiệp trên Railway:
1. Nhấp vào dịch vụ của bạn -> Tab **Deployments** -> **View Logs**.
2. **Theo dõi Telegram Send (MỚI):** Tìm các dòng có chữ `TELEGRAM_SEND`. Đây là bằng chứng thép bài đã được đẩy đi.
3. **Phân biệt Trùng Lặp (Idempotency):**
   - ✅ `POSTED`: Bài mới được đăng thành công.
   - ⏭️ `SKIPPED (Duplicate)`: Bot nhận diện bài này đã đăng rồi hoặc trùng lặp, nó sẽ bỏ qua để không làm phiền người dùng.
4. **Debug Ranking bài viết:** Tìm các dòng mang nhãn `📊 [RANK DEBUG]` để xem chi tiết tại sao bài đó được điểm cao hoặc bị trừ điểm nặng.

---

## BƯỚC 4: BẢO TRÌ VÀ CẬP NHẬT
Mỗi khi bạn có code mới (Sửa từ khóa, đổi Prompt AI), chỉ cần **Push** lên GitHub. Railway sẽ thấy sự thay đổi và tự động Deploy bản mới nhất trong 60 giây. Không cần bấm nút gì cả!

🎉 Tận hưởng cảm giác nhàn nhã nhìn Bot tự làm việc 24/7!
