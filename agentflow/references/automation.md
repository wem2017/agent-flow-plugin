# Automation test — chỉ QC đọc, khi viết hoặc sửa test e2e

Luật của repo thắng file này: `CLAUDE.md` của surface, test có sẵn trong `e2e_dir` (đặt tên, selector, subflow), project skill về test. Đọc vài test có sẵn trước khi viết test mới.

## Chọn framework

**Maestro trước**, cho mọi AC UI, mobile lẫn web (flow web dùng `url:` thay `appId:`): test như một người dùng — nhìn màn hình, chạm, gõ, đọc kết quả. Framework khác chỉ khi `e2e_dir` của surface đang là framework đó (repo đã chọn), hoặc AC cần thứ Maestro không làm được (giả lập network, dựng dữ liệu qua API phức tạp). AC thuần API ⇒ `curl`, không cần e2e.

## Test như người dùng

- Mỗi AC tự động hoá được ⇒ ít nhất một flow, tên có số issue + AC (vd `af-42-ac2-export-csv.yaml`). Đi trọn luồng từ điểm vào thật (màn trước, deep link), gồm quay lại, huỷ, nhập sai rồi sửa nếu AC chạm.
- Thao tác qua thứ người dùng thấy: chữ, accessibility label; dùng `id` khi repo quy ước (vd chữ đã dịch). Assert điều người dùng thấy (nội dung, thông báo, trạng thái nút, màn kế tiếp), không assert chi tiết cài đặt.
- Case: happy path + biên + input sai + quyền / trạng thái lỗi mà AC chạm. Không viết test cho thứ ngoài AC.
- Độc lập, chạy lại được: dữ liệu tự tạo tiền tố `af-<n>-`, không phụ thuộc thứ tự flow hay dữ liệu người khác trên staging.
- Không chờ cố định: `extendedWaitUntil` (`visible:` + `timeout`), `assertVisible` / `assertNotVisible` sau mỗi hành động có kết quả; danh sách dài ⇒ `scrollUntilVisible`.
- Dùng lại subflow sẵn có (`runFlow:` đăng nhập…); subflow mới chỉ khi ≥ 2 flow dùng.
- Flow mới phải pass **3 lần liên tiếp** trước khi tính là pass. Fail một lần = flaky: sửa cách chờ, selector, dữ liệu; không thêm `retry` để che.
- Không thêm dependency, không sửa config framework, CI hay code app (hook chặn). Thiếu id để chọn ổn định ⇒ không sửa app: dùng chữ / label, ghi "đề xuất thêm id" vào verdict.

## Maestro

- Header: `appId: ${APP_ID}` (mobile, hoặc như flow có sẵn) / `url: ${STAGING_URL}` (web), `name:`, `tags: [af-<n>]`, rồi `---`. Mobile mở đầu `launchApp` với `clearState: true`, `permissions: { all: allow }`.
- Dò phần tử bằng `maestro hierarchy` khi màn đang mở, đừng đoán.
- Secret chỉ qua tên biến env của `staging.notes`, truyền bằng `-e` trong `sh -c` để value không lộ: `agentflow-settings exec -- sh -c 'maestro test -e APP_ID="$APP_ID" -e E2E_EMAIL="$<TÊN BIẾN>" --test-output-dir /tmp/af-<n>-maestro <flow>'`.
- Nhiều thiết bị đang chạy ⇒ `maestro --device <udid> test …`. Chạy 3 lần = lặp lệnh, không `repeat` trong flow. Báo cáo: `--format junit --output /tmp/af-<n>-maestro.xml`.

## UI/UX

AC chạm UI ⇒ `takeScreenshot: af-<n>-ac<k>-<state>` ở mỗi màn và state AC chạm (mặc định, lỗi, rỗng; dark mode, xoay màn nếu app hỗ trợ). Ảnh ở `/tmp/af-<n>-maestro`; **tự xem từng ảnh** (Read), so với design (`design.md` §QC) và màn cùng loại có sẵn:

- **UI**: bố cục, căn lề, khoảng cách, màu, font; chữ đúng nội dung và ngôn ngữ, không bị cắt / tràn / chồng; icon, ảnh; trạng thái nút (disabled, loading); safe area, bàn phím che input; vùng chạm quá nhỏ.
- **UX**: mỗi thao tác có phản hồi (loading, thành công, lỗi nói rõ cách sửa); không mất dữ liệu đã nhập khi lỗi hay quay lại; back đúng màn; số bước gọn; nhất quán với các màn khác.

Lệch design / AC rõ, hoặc lỗi hiển thị do ticket (cắt chữ, tràn, sai ngôn ngữ) ⇒ ❌, ghi tên ảnh + vị trí (DEV mở được ảnh, cùng máy). Góp ý UX ngoài AC ⇒ mục "Đề xuất UX" trong verdict, không ❌. Cảm quan khó phán ⇒ checklist test tay. Luồng fail khó tả ⇒ quay video bằng `startRecording` / `stopRecording`.

Không dùng `assertWithAI`, `assertNoDefectsWithAI`, `extractTextWithAI`: cần API key và gửi ảnh staging ra dịch vụ ngoài — bạn tự xem ảnh. `assertScreenshot` chỉ khi repo đã có ảnh chuẩn.

## Framework khác của repo

Surface đã dùng Playwright, Cypress, Flutter `integration_test`, Detox… trong `e2e_dir` ⇒ theo đúng framework đó với cùng nguyên tắc: thao tác như người dùng (Playwright: `getByRole` / `getByLabel` / `getByText`, assert web-first, không `waitForTimeout`), dữ liệu riêng, chạy 3 lần (`--repeat-each=3`), output ra `/tmp/af-<n>-…`, và vẫn chụp ảnh từng state để soát UI/UX như trên.
