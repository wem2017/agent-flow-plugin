# AgentFlow — Design notes (v2)

File này **không bao giờ được load lúc runtime** (hệ số token = 0). Nó giữ *vì sao* thiết kế như vậy, để prompt runtime chỉ cần giữ *làm gì*. `/agentflow:learn` đọc §Non-goals làm gate trước khi sửa plugin.

## Mục tiêu

1. Agent hoàn thành ticket trên GitHub Projects board **tới cổng của con người** (review/merge, QC tay, PO duyệt scope) — không hơn.
2. **Chi phí token thấp, đoán trước được**: prompt ngắn, đọc ít, đọc đúng lúc; subagent mỗi ticket để session chính không phình.
3. **Một plugin cho nhiều project**: mọi thứ khác nhau giữa project (tên cột, label, branch, lệnh check) nằm trong `agentflow.yaml`; plugin chỉ giữ ngữ nghĩa.
4. **Tự cải thiện có kiểm soát**: friction được ghi journal tự động, bài học chỉ vào plugin sau khi người duyệt diff.

## Quyết định chính và lý do

| Quyết định | Lý do | Đánh đổi chấp nhận |
|---|---|---|
| **Stage ngữ nghĩa + map tên cột trong config** (thay cho 6 tên cột hằng số của v1) | Board thật của mỗi team đặt tên khác nhau; ép đổi tên board là rào cản cài đặt lớn nhất | Tên option là wire value — đổi tên trên GitHub UI mà không sửa yaml là hỏng routing; `doctor` bắt lỗi này |
| **QC trước merge, test trên staging** (`in_review → staging → in_qc → ready_to_merge`) | Test trên hệ thống đã deploy thật mới thấy lỗi tích hợp; master chỉ nhận code đã QC. Review trước staging để không build code còn bị review sửa | Mọi repo phải có nhánh staging và pipeline (schema 4 bắt buộc, một luồng để prompt không phải tả hai đường) |
| **Draft PR do DEV mở, chỉ QC pass mới undraft** | Giữ inline review + CI của PR ngay từ vòng review; draft không merge được nên là chặn thật, không chỉ là quy ước. Feedback sau undraft đưa PR về draft | PR draft không gửi review request tự động cho tới khi undraft |
| **Staging merge dồn, không reset, không force-push** | Chạy song song được, giữ nguyên bất biến cấm force-push | Code chưa đạt của ticket khác vẫn nằm trên staging, staging lệch dần master, lỗi có thể đến từ ticket khác ⇒ QC phải phân loại, người tự reset khi cần |
| **REVIEWER tự merge + giải conflict trên staging** (người dùng chọn thay vì script) | Không thêm role; conflict giải bằng model mạnh nhất | Dùng Opus cho việc cơ học, REVIEWER có quyền sửa file (chỉ prompt giới hạn trong worktree staging, hook không chặn). Không chắc ⇒ `blocked` |
| **Chỉ merge PR branch → staging, không bao giờ ngược lại** | Merge ngược sẽ đưa code chưa đạt của ticket khác vào PR master | Conflict không trả về DEV được, phải giải ngay trên staging |
| **Chờ pipeline bằng label `deploying` ở `in_qc`, orchestrator canh** (không thêm cột, không để QC tự poll) | Không tốn token lúc chờ; `agentflow-board checks` trả một dòng JSON, `--wait` chạy nền | Board không tách "đang build" với "đang test" bằng cột |
| **Xét check của head staging, không phải của `deploy_sha`** | Merge dồn + `concurrency: cancel-in-progress` làm build của SHA cũ bị huỷ dù head đã chứa nó | Ticket đợi lâu hơn khi có push liên tiếp |
| **Head không có check nào = pending** | Pipeline cần vài giây để đăng ký; dựa vào `timeout_min` để kết luận | Repo không có pipeline thì mỗi ticket mất trọn timeout rồi `blocked` — init + doctor cảnh báo |
| **QC chỉ test trên staging, không viết test, không commit** (người dùng chọn) | Đơn giản, rẻ, QC đúng vai kiểm thử hệ thống; head PR không đổi sau review nên không cần review/deploy lại | Mất automation test do QC viết và mất kiểm "test tái hiện fail trên code cũ" — chuyển trách nhiệm test sang DEV, REVIEWER ❌ khi thiếu |
| **Review ❌ mọi điểm chưa tối ưu** (người dùng chọn, chấp nhận tốn Opus) | Chất lượng giải pháp là tiêu chí cổng, không phải gợi ý | Nhiều vòng hơn. Giới hạn hội tụ: chỉ phán diff, không nêu điểm mới ở code đã qua review, không ép gu; escalate sau `max_review_rounds` |
| **Đếm round riêng: review 3 liên tiếp, QC 2** | Review khắt khe không được ăn hết lượt của QC | Hai key state + hai key config |
| **QC ❌ về `ready` + `qc_failed`, review ❌ về `in_progress`** (người dùng chọn) | Việc bị QC trả hiện rõ trên board; review ❌ là vòng nội bộ nhanh | Ready không còn chỉ là việc mới: DEV xếp hạng rework trước, DoR defense chỉ áp cho `MODE=new` |
| **Chỉ PO kéo Backlog → Ready** | Ưu tiên + scope là quyết định sản phẩm. Agent chỉ soạn issue (`/task`) vào Backlog | Loop không tự lấy việc mới khi Ready trống |
| **`blocked` / `needs-info` là label, ticket đứng nguyên cột** | Khớp quy ước team ("bị chặn ở cột nào cũng gắn `blocked`"); không mất ngữ cảnh cột | Loop phải lọc label |
| **Người gỡ chặn bằng cách bỏ label** | Thao tác tự nhiên trên GitHub, không cần lệnh riêng | — |
| **GitHub MCP cho mọi thao tác của agent trên ticket**; `bin/agentflow-board` (GraphQL) chỉ cho setup + chẩn đoán (init, doctor, status, metrics) và đọc check pipeline (`checks`) | MCP là đường người dùng chọn cho runtime. MCP không sửa được option/field/view; báo cáo đọc cả board qua MCP tốn K call và đổ JSON dài vào context, script trả kết quả đã gom | Restart khi đổi token. Script tự fallback sang `curl` khi Python không tin được CA (python.org build, proxy công ty) |
| **GitHub MCP auth qua `headersHelper`** (`scripts/mcp-headers.py`) thay cho `${GITHUB_TOKEN}` trong header | Đo ngày 2026-10-30: `${GITHUB_TOKEN}` lấy từ `env` của settings vào header MCP của plugin **không ổn định** (2/8 lần connect được, còn lại HTTP 400 — MCP connect trước khi env được áp); `export` ở shell thì không có tác dụng. Helper đọc thẳng file settings → 3/3. Nó chạy lại mỗi lần reconnect ⇒ đổi token không cần restart | Thêm một script Python chạy lúc connect |
| **`.claude/settings.local.json` là path forbidden; chỉ sửa qua `agentflow-settings`** | Agent Read file này = token vào transcript | Người muốn sửa tay thì mở editor |
| **Label `agentflow` đánh dấu ticket agent sở hữu** | Orchestrator lọc được từ chính kết quả `list_project_items`, không phải đọc body từng issue để tìm state block | Thêm một label trên card |
| **State ẩn trong HTML comment ở cuối issue body** | Issue body do PO viết; block hiển thị to làm rối. Comment HTML không render, vẫn parse được | Phải re-read body trước khi ghi (chống clobber) |
| **Comment có prefix `[AF:…]`** | Agent dùng token của chính người dùng → cùng login. Prefix là cách duy nhất phân biệt agent và người | Người gõ tay `[AF:` sẽ bị coi là agent — chấp nhận |
| **Lệnh check của surface lưu trong config** (v1 tự khám phá mỗi lần) | Khám phá lại `package.json`/`Makefile` mỗi spawn tốn token và kết quả không ổn định | Config phải cập nhật khi repo đổi lệnh — `doctor` + `learn` nhắc |
| **Model theo Size** | Phần lớn ticket XS–M chạy tốt với Sonnet; Opus chỉ cho L | — |
| **Review/QC lặp lại chỉ soát diff kể từ SHA đã phán** (QC thêm một lượt smoke) | Vòng rework thường nhỏ; soát lại toàn bộ là lãng phí | Reviewer phải ghi SHA vào verdict |
| **Song song bằng `isolation: worktree` truyền lúc spawn** | Ticket độc lập không giẫm working tree của nhau | Mỗi worktree cài deps riêng |
| **Bypass permission + hook PreToolUse chặn cứng** | Loop phải chạy được khi người vắng mặt; hook là lớp chặn duy nhất không phụ thuộc prompt | Hook so khớp text lệnh — best-effort, không phải ranh giới bảo mật tuyệt đối |
| **Journal ở cấp user (`~/.claude/agentflow/`)** | Bài học chỉ vào plugin ⇒ gom friction từ mọi project về một chỗ | Journal không đi theo repo |
| **Skill lệnh dùng `disable-model-invocation: true`** | Lệnh chỉ chạy khi người gọi; không tốn context lúc khởi động session | Không tự kích hoạt bằng ngôn ngữ tự nhiên |

## Non-goals (bất biến — `/learn` phải DỪNG nếu bài học đụng vào)

- **Agent không bao giờ merge PR**, không approve PR, không force-push, không push vào nhánh `git.protected`, không chạy/dispatch workflow (ở nhiều repo chạy workflow là deploy). Hook chặn cả năm. Push thường vào `staging.branch` là ngoại lệ duy nhất, chỉ REVIEWER làm — hook không phân biệt role, nên giới hạn role nằm ở prompt.
- **Agent không bao giờ chuyển ticket ra khỏi `backlog`** khi chưa có xác nhận tường minh của người trong session.
- **Agent không bao giờ chuyển ticket ra khỏi `ready_to_merge`** trừ hai trường hợp: PR đã merge (→ `done`) hoặc có feedback của người trên PR (→ `in_progress`, PR về draft).
- **Agent không bao giờ sửa hay in nội dung path trong `forbidden`** (mặc định: secret).
- **Không message bus, không database ngoài GitHub.** Trạng thái = Status trên board + label + state block + comment.
- **Không thêm field bắt buộc vào state block** khi chưa có consumer đọc nó.
- **Không có bản sao thứ hai của một fact** trong prompt runtime — một nơi gốc, chỗ khác trỏ về.

## Giới hạn đã biết

- Projects v2 không có compare-and-swap; compare-then-write chỉ thu hẹp cửa sổ race. **Một loop session cho mỗi repo** là giả định vận hành.
- Projects v2 không có history API; metrics dựng lại từ timestamp của comment `[AF:…]`.
- `updateProjectV2Field` thay toàn bộ option; `ProjectV2SingleSelectFieldOptionInput.id` (introspect 2026-10-30) cho phép giữ option sẵn có ⇒ `status-apply` luôn truyền id của option cũ, chỉ option bị bỏ mới mất Status của card (cần `--allow-drop`). Hành vi giữ id mới verify qua schema, chưa verify end-to-end trên board có card — `status-plan` luôn chạy trước.
- Mention chính mình không tạo notification — mention người khác (`people.*`) mới có tác dụng.
