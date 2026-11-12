# Automation test — SA lập test case, DEV viết flow và chạy trên staging

Luật của repo thắng file này: `CLAUDE.md` của surface, test có sẵn trong `e2e_dir` (đặt tên, selector, subflow), project skill về test. Đọc vài flow có sẵn trước khi viết flow mới.

## Test case

Viết từ AC, user flow, design và rủi ro — không từ code. Mỗi AC:
- Case: happy path · biên (rỗng, tối đa, ký tự đặc biệt, nhiều trang) · input sai rồi sửa · lỗi (mạng, server, hết phiên) · quyền / vai trò · trạng thái (loading, rỗng, disabled) · quay lại, huỷ, dữ liệu đã nhập còn giữ — chỉ những case AC hoặc rủi ro chạm.
- Mỗi case: điểm vào thật → bước → kết quả người dùng thấy, và mức: `e2e` (flow UI) · `api` (gọi API staging) · `tay` (thiết bị thật, cảm quan, dịch vụ ngoài, không tự động được). Một hành vi một mức.
- Bug: case tái hiện đúng bước trong issue, fail trên code hiện tại.

## Element id

- Mỗi phần tử flow chạm hoặc assert có id ổn định; theo quy ước id sẵn có của repo, không có thì `<màn>_<phần tử>` (vd `checkout_pay_button`), không chứa dữ liệu động, không đổi theo ngôn ngữ.
- Cách gắn theo nền tảng: React Native `testID` · Flutter `Key('…')` (hoặc `Semantics(identifier: '…')` cho Maestro) · iOS `accessibilityIdentifier` · Android `resource-id` / Compose `Modifier.testTag` · web `data-testid`.
- Gắn id chỉ thêm thuộc tính: không đổi layout, logic, chữ. Flow chọn bằng id; assert bằng chữ người dùng thấy khi AC nói về nội dung.

## Flow

**Maestro trước**, cho mọi case UI, mobile lẫn web (flow web dùng `url:` thay `appId:`). Framework khác chỉ khi `e2e_dir` của surface đang là framework đó, hoặc case cần thứ Maestro không làm được (giả lập network, dựng dữ liệu qua API phức tạp).

- Mỗi case `e2e` ⇒ một flow trong `<surface>/<e2e_dir>`, tên có số issue + TC (vd `af-42-tc2-export-csv.yaml`), `tags: [af-<n>]`. Đi trọn luồng từ điểm vào thật (màn trước, deep link).
- Case `api` ⇒ test chạy lại được trong `e2e_dir` (framework của repo; Maestro: `runScript` dùng `http`, kiểm bằng `assertTrue`): status + body + side effect. Surface không có `e2e_dir` ⇒ `curl` vào `staging.url`, ghi lệnh + kết quả vào PR, thêm vào "Đề xuất kiểm chứng thêm".
- Assert điều người dùng thấy (nội dung, thông báo, trạng thái nút, màn kế tiếp).
- Độc lập, chạy lại được: dữ liệu tự tạo tiền tố `af-<n>-`, không phụ thuộc thứ tự flow hay dữ liệu người khác trên staging; dọn dữ liệu tự tạo, không thao tác hàng loạt.
- Không chờ cố định: `extendedWaitUntil` (`visible:` + `timeout`), `assertVisible` / `assertNotVisible` sau mỗi hành động có kết quả; danh sách dài ⇒ `scrollUntilVisible`.
- Dùng lại subflow sẵn có (`runFlow:` đăng nhập…); subflow mới chỉ khi ≥ 2 flow dùng.
- Không thêm dependency, không sửa config framework hay CI.

## Chạy

- **Chọn flow liên quan**: flow của ticket (`tags: [af-<n>]`) + flow có sẵn đi qua phần diff chạm: `git diff --name-only origin/<base>...` → Grep id, tên màn, route, path API của file bị đổi trong `e2e_dir`. Cả suite (`surfaces.<key>.e2e`) chỉ khi diff chạm phần dùng chung (auth, điều hướng, API client, theme, migration).
- Flow mới chạy **3 lần liên tiếp** mới tính pass; flow có sẵn chạy 1 lần. Vòng sửa: chạy lại flow fail + flow liên quan phần vừa sửa.
- **Web**: `url: ${STAGING_URL}`, value `staging.url`. **Mobile**: build + cài bản trỏ server staging bằng `surfaces.<key>.install` lên emulator/simulator đang chạy (thiếu key ⇒ dò cách build flavor staging một lần theo `CLAUDE.md`/README, journal `slow` đề xuất key); không chờ release mobile của pipeline. Không có thiết bị, `maestro` hay `staging.url` ⇒ case đó thành QC tay, không phải fail.
- Output: `cd "$WT/<surface path>" && maestro test … --format junit --output /tmp/af-<n>-e2e.xml --test-output-dir /tmp/af-<n>-maestro <flows> > /tmp/af-<n>-e2e.log 2>&1; echo "exit $?"`. Chỉ đọc đuôi log và junit khi fail.

## Phân định fail

- Do test (selector, chờ, dữ liệu, thiếu id) ⇒ sửa flow, gắn id. Dò phần tử: `maestro hierarchy` lúc màn đang mở. Không bỏ bước, không làm yếu assert, không thêm `retry`/`optional` để che.
- Chập chờn ⇒ chạy lại 2 lần, đọc log. Do test ⇒ sửa cách chờ/selector. Do app (race, timeout) ⇒ sửa code.
- Sai hành vi so với AC ⇒ sửa code (tái hiện trước bằng chính flow đó).
- Do ticket khác trên staging hoặc hạ tầng ⇒ không sửa code mình, không tính vòng: `[AF:DEV] blocked` + bằng chứng.
- AC mơ hồ, không phán được đúng sai ⇒ `[AF:DEV] ?` + `@<people.po>`, gắn `needs_info`, giữ cột.

## Ảnh UI/UX

Flow `takeScreenshot: af-<n>-tc<j>` ở state cuối mỗi case UI (ảnh ở `/tmp/af-<n>-maestro`). Chỉ mở ảnh (Read) khi flow fail, cộng **một** ảnh cuối mỗi AC UI để soát lệch rõ so với design/AC: chữ cắt, tràn, chồng, sai ngôn ngữ, sai bố cục, thiếu trạng thái. Lệch do ticket ⇒ sửa. Góp ý cảm quan ⇒ "Đề xuất kiểm chứng thêm". Không dùng `assertWithAI`, `assertNoDefectsWithAI`, `extractTextWithAI` (cần API key, gửi ảnh staging ra ngoài). `assertScreenshot` chỉ khi repo đã có ảnh chuẩn.

## Maestro

- Header: `appId: ${APP_ID}` (mobile, hoặc như flow có sẵn) / `url: ${STAGING_URL}` (web), `name:`, `tags: [af-<n>]`, rồi `---`. Mobile mở đầu `launchApp` với `clearState: true`, `permissions: { all: allow }`.
- App id, tài khoản test: đọc ở secret folder `staging.notes` của `<repo root>` (không phải worktree). Flow dùng `${VAR}`, value qua `-e`: `maestro test -e APP_ID=<…> <flow>`. Không ghi value vào file, PR, comment.
- Nhiều thiết bị đang chạy ⇒ `maestro --device <udid> test …`. Chạy 3 lần = lặp lệnh, không `repeat` trong flow.

## Framework khác của repo

Surface đã dùng Playwright, Cypress, Flutter `integration_test`, Detox… trong `e2e_dir` ⇒ theo đúng framework đó với cùng nguyên tắc: chọn bằng test id (Playwright `getByTestId`, rồi `getByRole` / `getByLabel`), assert web-first, không `waitForTimeout`, dữ liệu riêng, nhắm `staging.url`, flow mới chạy 3 lần (`--repeat-each=3`), output ra `/tmp/af-<n>-…`.

## Kiểm chứng lại (mục của PR)

- **QC tay** (chặn merge, QC người làm trên staging): `- [ ]` mỗi case `tay` và mỗi case không chạy được (thiếu thiết bị, công cụ, dữ liệu thật): bước + kỳ vọng + môi trường (`staging.url` / build theo `staging.build`) + link frame design nếu có.
- **Đề xuất kiểm chứng thêm** (không chặn): regression ở vùng rủi ro SA nêu và phần diff thật chạm mà flow không phủ, rủi ro còn lại, góp ý UX. Mỗi dòng: vùng → vì sao → cách kiểm.
- Rework sau khi QC người báo fail (`qc_round` > 0) ⇒ QC tay **luôn** có `- [ ] Xác nhận lại lỗi QC đã báo: <bước của họ>`. Mục QC tay đã có chỉ bỏ khi flow phủ đúng case đó (ghi lý do).
- Không có mục QC tay ⇒ ghi `QC tay: —`.
