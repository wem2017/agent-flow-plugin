## Issue

{{LINK}} #

## Thay đổi

-

## Giải pháp

- Theo thiết kế SA: <link comment `[AF:SA] design`>
- Lệch thiết kế: — <!-- hoặc: lệch gì, vì sao, bằng chứng -->

## Tiêu chí nghiệm thu

- [ ]

| AC | Code chính | TC | Flow |
|---|---|---|---|
| AC1 | | TC1 | |

## Test tự động (trên staging)

Staging @ <!-- deploy sha --> · <!-- k/k TC pass, flow mới pass 3/3 -->

| Flow | TC | Kết quả |
|---|---|---|
| | | |

## Kiểm chứng lại

### QC tay

<!-- chặn merge: case không tự động được (thiết bị thật, dịch vụ ngoài, cảm quan) — bước + kỳ vọng + môi trường. Không có: ghi "—" -->
- [ ]

### Đề xuất kiểm chứng thêm

<!-- không chặn: regression ở vùng rủi ro và phần diff chạm mà flow không phủ — vùng → vì sao → cách kiểm -->
-

## Ảnh chụp / Design

## Checklist

- [ ] Tự review diff theo chuẩn kỹ thuật, đã tìm mọi nơi gọi của hàm/kiểu bị đổi
- [ ] Đã gắn element id cho mọi phần tử flow chạm hoặc assert
- [ ] Check + test có sẵn của surface bị chạm xanh; flow liên quan pass trên staging
