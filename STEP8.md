# Phân Tích Kết Quả Thực Nghiệm & Đánh Giá Hệ Thống Memory (Bước 8 & Bonus)

Sau khi hoàn thiện code trong `src/` và chạy benchmark sạch qua lệnh `python src/benchmark.py`, mình ghi nhận được số liệu thực tế giữa hai agent và rút ra các phân tích kỹ thuật dưới đây.

---

## 1. Số Liệu Benchmark Thực Tế

### Standard Benchmark (`data/conversations.json` - 10 hội thoại, user `dungct`)

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline** | 1,747 | 15,142 | 0.00 | 0.20 | 0 | 0 |
| **Advanced** | 4,198 | 24,858 | 1.00 | 1.00 | 250 | 10 |

### Long-Context Stress Benchmark (`data/advanced_long_context.json` - 1 hội thoại 16 lượt dài, user `dungct_stress`)

| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline** | 283 | 22,370 | 0.00 | 0.20 | 0 | 0 |
| **Advanced** | 1,075 | 10,076 | 1.00 | 1.00 | 213 | 27 |

---

## 2. Trả Lời 4 Câu Hỏi Ở Bước 8 (Guide.md)

### 2.1. Vì sao Advanced có recall tốt hơn hẳn Baseline?
Nhìn vào kết quả, Baseline hoàn toàn không nhớ được gì khi sang thread mới (Recall = 0.00 ở cả hai bộ dữ liệu). Ngược lại, Advanced đạt Recall tuyệt đối 1.00. 

Lý do nằm ở cách thiết kế lưu trữ:
- **Baseline** chỉ lưu lịch sử theo `thread_id`. Sang một thread mới để hỏi câu hỏi recall, danh sách tin nhắn trống trơn, agent không còn bất kỳ dữ kiện nào của các phiên trước.
- **Advanced** có thêm tầng Persistent Memory bằng file `User.md`. Trong quá trình chat, mỗi khi người dùng nói về tên, nghề nghiệp, nơi ở hay sở thích, hàm `extract_profile_updates()` lập tức trích xuất và lưu ngay vào đĩa (`state/profiles/<user_id>/User.md`). Sang thread mới, agent chỉ cần đọc file này lên là có đầy đủ thông tin để trả lời chính xác.

### 2.2. Vì sao Advanced lại tốn token hơn ở hội thoại ngắn?
Ở bảng Standard Benchmark (các hội thoại thông thường khoảng 10 lượt ngắn):
- Baseline chỉ tốn **15,142** prompt tokens, trong khi Advanced tốn tới **24,858** tokens.
- Token do agent sinh ra (`Agent tokens only`) của Advanced cũng cao hơn (4,198 so với 1,747).

Điều này phản ánh đúng chi phí duy trì hệ thống memory (overhead):
- Mỗi lượt chat, Advanced phải mang theo toàn bộ nội dung file `User.md` cộng với các tin nhắn gần nhất và bản tóm tắt cũ vào ngữ cảnh prompt.
- Ở hội thoại ngắn, các câu nói chỉ có vài chục ký tự, tổng lượng token chưa đủ lớn để cơ chế compact phát huy tác dụng nén. Việc nhồi thêm profile người dùng vào mỗi lượt làm chi phí prompt context bị đội lên. Nói cách khác, với các tác vụ chat ngắn gọn, việc gắn thêm persistent memory là một sự đánh đổi: đổi thêm token lấy khả năng ghi nhớ dài hạn.

### 2.3. Vì sao compact memory đem lại lợi thế rõ rệt ở hội thoại dài?
Sự khác biệt bộc lộ rõ nhất ở bảng Long-Context Stress:
- Baseline phải kéo theo toàn bộ lịch sử 16 lượt tin tức rất dài, khiến `Prompt tokens processed` tăng vọt lên **22,370 tokens**.
- Advanced chỉ tiêu tốn **10,076 tokens** (tiết kiệm hơn 55% chi phí ngữ cảnh). Cột `Compactions` đạt 27 lần.

Nguyên nhân là nhờ cơ chế nén tự động:
- Baseline không có compact, nên càng về các lượt sau, lượng tin nhắn tích lũy càng phình to theo kiểu cộng dồn.
- Advanced đặt ra một ngưỡng (`compact_threshold_tokens = 350`). Cứ khi nào tổng token trong thread vượt ngưỡng, `CompactMemoryManager` sẽ gom các tin nhắn cũ lại thành một đoạn tóm tắt ngắn (`summary`), chỉ giữ lại 2 tin nhắn gần nhất nguyên văn. 
- Nhờ vậy, cửa sổ ngữ cảnh luôn được chặn trên, giúp kìm hãm lượng **Prompt tokens processed**. Điểm quan trọng cần thấy ở đây: compact memory sinh ra là để tối ưu chi phí ngữ cảnh đầu vào (prompt tokens), chứ không phải để giảm token câu trả lời của agent.

### 2.4. File memory tăng trưởng ra sao và những rủi ro đi kèm trong thực tế?
Ở Baseline, dung lượng file tăng thêm bằng 0 vì không ghi gì xuống đĩa. Ở Advanced, file `User.md` tăng 250 bytes cho user `dungct` và 213 bytes cho user `dungct_stress`. Con số này khá gọn gàng, nhưng khi đưa vào thực tế sẽ có những rủi ro lớn:
1. **Rủi ro phình to file (Memory Bloat)**: Nếu người dùng chat qua hàng tháng trời với hàng trăm thông tin lặt vặt, file `User.md` sẽ dài ra liên tục. Nếu không có cơ chế dọn dẹp hoặc chọn lọc, việc đọc toàn bộ file này vào prompt mỗi lượt sẽ biến chính persistent memory thành gánh nặng token.
2. **Rủi ro lưu dữ liệu nhiễu và đùa cợt**: Người dùng rất hay nói đùa (như câu đùa muốn làm "product manager") hoặc nhắc đến địa điểm tạm thời ("bay ra Hà Nội họp"). Nếu bot cứ thấy từ khóa là lưu, file profile sẽ bị rác và agent sẽ nhớ sai lệch.
3. **Rủi ro xung đột thông tin cũ - mới**: Người dùng chuyển nơi ở từ Đà Nẵng sang Huế rồi lại về Đà Nẵng. Nếu chỉ đơn thuần append thêm dòng mới vào file, file sẽ chứa cả 2 thông tin trái ngược nhau, khiến agent bị hallucinate khi trả lời.

---

## 3. Phần Mở Rộng Kỹ Thuật (Bonus)

Để xử lý các rủi ro trên và hướng đến mốc điểm 90–100 theo Rubric, mình đã triển khai 3 cải tiến trong `src/memory_store.py`:

### 3.1. Xử lý xung đột thông tin (Conflict Handling)
- **Vấn đề**: Trong dữ liệu benchmark, user `dungct` đổi nơi ở từ Đà Nẵng sang Huế (`conv-03`), chuyển nghề từ backend sang MLOps (`conv-06`), và ở stress test lại đổi từ Huế về Đà Nẵng. Nếu lưu cả hai, agent sẽ không biết đâu là thông tin hiện tại.
- **Giải pháp**: Viết phương thức `upsert_fact()` và `edit_text()` trong `UserProfileStore`. Khi phát hiện fact mới cùng key (ví dụ `location`, `profession`), hệ thống sẽ thay thế trực tiếp giá trị cũ bằng giá trị mới thay vì ghi thêm dòng. Riêng với sở thích kỹ thuật (`tech`), hệ thống gom chung để giữ cả `Python` và `AI`.
- **Hiệu quả**: Agent trả lời chính xác 100% các câu hỏi phân biệt nghề cũ/mới và nơi ở hiện tại.
- **Rủi ro phát sinh**: Nếu người dùng chỉ đang hoài niệm về quá khứ ("trước đây mình từng làm backend"), việc ghi đè mù quáng có thể làm mất thông tin nghề nghiệp hiện tại nếu không có bộ phân tích ngữ cảnh thời gian tốt hơn.

### 3.2. Lọc nhiễu và kiểm tra độ tin cậy (Confidence & Noise Filtering)
- **Vấn đề**: Tránh các câu hỏi tu từ ("mình tên gì?"), câu đùa ("product manager"), và địa điểm công tác tạm thời ("Hà Nội chỉ là nơi mình vừa bay ra họp hai ngày").
- **Giải pháp**: Thêm các điều kiện lọc trong `extract_profile_updates()`: bỏ qua các turn mang tính chất hỏi đáp, kiểm tra các cụm từ đùa cợt hoặc công tác ngắn hạn trước khi trích xuất.
- **Hiệu quả**: Không bị lưu nhầm "product manager" hay "Hà Nội" vào `User.md`, giữ file sạch và đúng trọng tâm.
- **Rủi ro phát sinh**: Có thể bị false negative (bỏ sót thông tin thật) nếu người dùng cung cấp thông tin bằng cách diễn đạt phức tạp mà bộ lọc chưa lường trước.

### 3.3. Định dạng thực thể có cấu trúc (Structured Entity Extraction)
- Thay vì ghi text tự do, `User.md` được lưu dưới dạng danh sách markdown key-value rõ ràng (`- **key**: value`). Việc này giúp code đọc lại bằng hàm `get_facts()` rất nhanh, ổn định và không bị phụ thuộc vào việc parse chuỗi phức tạp.

---

## 4. Tóm Tắt Luồng Kiến Trúc

Toàn bộ bài lab này cho thấy một câu chuyện thiết kế rất thực tế:
1. **Baseline** đơn giản nhưng không thể nhớ xuyên phiên (Recall = 0).
2. **Advanced** thêm `User.md` giúp recall đạt mức hoàn hảo (100%), nhưng phải chấp nhận tốn thêm token overhead ở các lượt chat ngắn.
3. Khi bước vào hội thoại dài, **Compact Memory** phát huy tác dụng nén, kéo lượng prompt context processed giảm hơn một nửa so với Baseline.
4. Một hệ thống memory hoàn chỉnh không thể chỉ lưu mọi thứ, mà bắt buộc phải có guardrail: lọc nhiễu, xử lý xung đột fact và cấu trúc hóa dữ liệu để tránh phình bộ nhớ.
