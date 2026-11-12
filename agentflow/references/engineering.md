# Chuẩn kỹ thuật — SA thiết kế và review, DEV code và tự review theo file này

Luật của repo thắng file này: `CLAUDE.md` (root + thư mục bị chạm), project skill, pattern repo đang dùng. Repo đã chọn cách khác thì theo repo, không "sửa" repo cho giống file này.

## Kiến trúc

- Theo tầng sẵn có của repo (vd presentation → domain → data, controller → service → repository). Phụ thuộc chỉ hướng vào lõi: UI và hạ tầng phụ thuộc domain, domain không import framework, DB, HTTP.
- Một module một trách nhiệm; module khác dùng nó qua interface/contract, không với vào chi tiết bên trong.
- Contract (API, event, schema DB, type public) tương thích ngược; đổi phá vỡ ⇒ thêm trước, bỏ sau, hoặc version mới.
- Migration: file mới, không sửa migration đã push (staging đã chạy), chạy được với code đang chạy, có đường lùi.
- Backend/microservice: ranh giới service rõ, idempotent, timeout + retry có giới hạn, lỗi có mã, transaction đúng chỗ.
- Mobile/web: UI không chứa nghiệp vụ, state theo thư viện repo đang dùng, async theo vòng đời (huỷ khi rời màn), component/widget nhỏ dùng lại được, tối ưu render theo framework (`const`, memo, key).

## Code

- SOLID: một lý do để đổi mỗi lớp/hàm; mở rộng bằng thêm thay vì sửa chuỗi if-else; interface nhỏ theo nhu cầu; phụ thuộc abstraction, inject qua constructor.
- Pattern chỉ khi giải đúng vấn đề của AC (Strategy cho nhánh hành vi, Repository cho nguồn dữ liệu, Adapter cho dịch vụ ngoài, Factory khi tạo phức tạp…), không để trang trí.
- KISS, YAGNI, DRY: dùng lại tiện ích/component sẵn có trước khi viết mới; không trừu tượng hoá cho một chỗ dùng; không over-engineer so với AC.
- Tên nói ý định; hàm ngắn, một việc; guard clause thay lồng sâu; không số/chuỗi ma thuật (hằng có tên, token design).
- Biểu thức ngắn bị formatter bẻ dòng (thân `=>`, điều kiện `&&`/`||`, ternary) ⇒ biến có tên, guard clause hoặc `if-else`. Vừa một dòng thì giữ.
- Lỗi: không nuốt exception; thông báo người dùng biết cách xử lý; log đủ ngữ cảnh, không dữ liệu nhạy cảm.
- Không code chết, log debug, TODO không có ticket, thay đổi ngoài scope.

## Bảo mật, hiệu năng

- Validate input ở biên, kiểm quyền phía server, query tham số hoá, escape output; không secret trong code, log, commit; dependency mới phải cần thiết và còn được bảo trì.
- Không N+1; danh sách có phân trang/giới hạn; truy vấn mới có index; cache có cách invalidate; không chặn main/UI thread; giải phóng tài nguyên.

## Test

- Kiểm chứng bằng automation chạy thật trên staging (`automation.md`). Không viết unit/integration test có mock, trừ khi `CLAUDE.md` bắt buộc; test có sẵn vẫn phải xanh.
- Flow phải fail nếu bỏ thay đổi. Bug: flow tái hiện fail trước, pass sau.

## Tự review

`git diff origin/<base>...` một lượt theo các mục trên. Mỗi hàm, kiểu, contract bị đổi ⇒ Grep mọi nơi gọi, sửa hết hoặc giữ tương thích. `agentflow-style` sạch.
