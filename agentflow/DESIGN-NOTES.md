# AgentFlow — Design notes

File này **không bao giờ được load lúc runtime** (hệ số token = 0). Nó giữ *vì sao* thiết kế như vậy, để prompt runtime chỉ cần giữ *làm gì*. `/agentflow:learn` đọc §Non-goals làm gate trước khi sửa plugin.

## Mục tiêu

1. Agent hoàn thành ticket trên GitHub Projects board **tới cổng của con người** (review/merge, QC tay, PO duyệt scope) — không hơn.
2. **Chi phí token thấp, đoán trước được**: prompt ngắn, đọc ít, đọc đúng lúc; subagent mỗi ticket để session chính không phình.
3. **Một plugin cho nhiều project**: mọi thứ khác nhau giữa project (tên cột, label, branch, lệnh check) nằm trong `agentflow.yaml`; plugin chỉ giữ ngữ nghĩa.
4. **Tự cải thiện có kiểm soát**: friction được ghi journal tự động, bài học chỉ vào plugin sau khi người duyệt diff.

## Quyết định chính và lý do

| Quyết định | Lý do | Đánh đổi chấp nhận |
|---|---|---|
| **Stage ngữ nghĩa + map tên cột trong config** | Board thật của mỗi team đặt tên khác nhau; ép đổi tên board là rào cản cài đặt lớn nhất | Tên option là wire value — đổi tên trên GitHub UI mà không sửa yaml là hỏng routing; `doctor` bắt lỗi này |
| **QC trước merge, test trên staging** (`in_review → staging → in_qc → ready_to_merge`) | Test trên hệ thống đã deploy thật mới thấy lỗi tích hợp; master chỉ nhận code đã QC. Review trước staging để không build code còn bị review sửa | Mọi repo phải có nhánh staging và pipeline (bắt buộc, một luồng để prompt không phải tả hai đường) |
| **Draft PR do DEV mở, chỉ QC pass mới undraft** | Giữ inline review + CI của PR ngay từ vòng review; draft không merge được nên là chặn thật, không chỉ là quy ước. Feedback sau undraft đưa PR về draft | PR draft không gửi review request tự động cho tới khi undraft |
| **Staging merge dồn, không reset, không force-push** | Chạy song song được, giữ nguyên bất biến cấm force-push | Code chưa đạt của ticket khác vẫn nằm trên staging, staging lệch dần master, lỗi có thể đến từ ticket khác ⇒ QC phải phân loại. Người tự reset khi cần; ticket đang chờ build tự quay về In Review để deploy lại |
| **REVIEWER tự merge + giải conflict trên staging** (người dùng chọn thay vì script) | Không thêm role; conflict giải bằng model mạnh nhất | Dùng Opus cho việc cơ học, REVIEWER có quyền `Edit` (hook giới hạn trong worktree staging). Không chắc ⇒ `blocked` |
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
| **GitHub MCP cho mọi thao tác của agent trên ticket**; `bin/agentflow-board` (GraphQL) chỉ cho setup + chẩn đoán (init, doctor, status, metrics) và đọc check pipeline (`checks`) | MCP là đường người dùng chọn cho runtime. MCP không sửa được option/field/view; báo cáo đọc cả board qua MCP tốn K call và đổ JSON dài vào context, script trả kết quả đã gom | Đổi token phải Reconnect MCP. Script tự fallback sang `curl` khi Python không tin được CA (python.org build, proxy công ty) |
| **GitHub MCP auth qua `headersHelper`** (`scripts/mcp-headers.py`) thay cho `${GITHUB_TOKEN}` trong header | Đo ngày 2026-10-30: `${GITHUB_TOKEN}` lấy từ `env` của settings vào header MCP của plugin **không ổn định** (2/8 lần connect được, còn lại HTTP 400 — MCP connect trước khi env được áp); `export` ở shell thì không có tác dụng. Helper đọc thẳng file settings → 3/3. Nó chạy lại mỗi lần reconnect ⇒ đổi token không cần restart | Thêm một script Python chạy lúc connect |
| **`.claude/settings.local.json` là path forbidden; chỉ sửa qua `agentflow-settings`** | Agent Read file này = token vào transcript | Người muốn sửa tay thì mở editor |
| **Label `agentflow` đánh dấu ticket agent sở hữu** | Orchestrator lọc được từ chính kết quả `list_project_items`, không phải đọc body từng issue để tìm state block | Thêm một label trên card |
| **State ẩn trong HTML comment ở cuối issue body** | Issue body do PO viết; block hiển thị to làm rối. Comment HTML không render, vẫn parse được | Phải re-read body trước khi ghi (chống clobber) |
| **Comment có prefix `[AF:…]`** | Agent dùng token của chính người dùng → cùng login. Prefix là cách duy nhất phân biệt agent và người | Collaborator gõ tay `[AF:` sẽ bị coi là agent — chấp nhận. Tác giả ngoài (`author_association` khác OWNER/MEMBER/COLLABORATOR) không bao giờ được tin, nếu không repo public có thể giả verdict ✅ để bỏ qua review |
| **Lệnh check của surface lưu trong config** | Khám phá lại `package.json`/`Makefile` mỗi spawn tốn token và kết quả không ổn định | Config phải cập nhật khi repo đổi lệnh — `doctor` + `learn` nhắc |
| **DEV và REVIEWER chạy Opus effort xhigh** (người dùng chọn, chấp nhận chi phí) | Chất lượng code và giải pháp ưu tiên hơn chi phí; QC giữ Sonnet | Mỗi ticket tốn hơn nhiều so với Sonnet. Effort nằm ở frontmatter nên không đổi theo repo; `run.models` vẫn đổi được model |
| **Review/QC lặp lại chỉ soát diff kể từ SHA đã phán** (QC thêm một lượt smoke) | Vòng rework thường nhỏ; soát lại toàn bộ là lãng phí | Reviewer phải ghi SHA vào verdict |
| **Song song bằng worktree do DEV tự tạo ở `.claude/worktrees/af-<n>`** (không dùng `isolation: worktree` của Agent tool) | Worktree phải sống qua nhiều lần spawn của cùng ticket (rework, resume) và orchestrator phải tìm lại được theo số issue; isolation tự dọn khi agent xong | Mỗi worktree cài deps riêng; orchestrator tự dọn |
| **Bypass permission + hook PreToolUse chặn cứng** | Loop phải chạy được khi người vắng mặt; hook là lớp chặn duy nhất không phụ thuộc prompt | Best-effort, không phải ranh giới bảo mật: không thấy thứ chỉ lộ ra lúc chạy. Branch protection của GitHub vẫn là lớp chắc nhất |
| **Guard đọc cấu trúc lệnh** (`scripts/shellparse.py`, thay `shlex`), mở lệnh bọc, shell `-c`, `eval`, here-doc, pipe vào shell, code truyền cho interpreter | Đo ngày 2026-10-31: bản cũ dựa `shlex` chỉ bắt 7/67 kịch bản lách (`bash -c`, `env`, `timeout`, `$(…)`, `if…then`). So khớp theo argv nên `git commit -m "gh pr merge"` không bị chặn nhầm | ~300 dòng parser phải giữ có test. Red-team độc lập cùng ngày tìm thêm được lệch nhịp parser (`$'\''`, `case` trong `$()`), option viết tắt, `-c remote.*.push`, và các chặn nhầm với lệnh hằng ngày; tất cả nằm trong `tests/test_guard.py` |
| **Lệnh đọc path secret: mặc định chặn, chỉ miễn lệnh không mở nội dung** (`PATH_SAFE`: metadata + runner như `docker`, `flutter`, `pnpm`, `dotenv`) | Danh sách lệnh in nội dung không bao giờ đủ (`jq`, `dd`, `vim`…) | Một lệnh lạ nhận path secret làm tham số sẽ bị chặn. Runner trong `PATH_SAFE` về lý thuyết có thể in file — coi là chấp nhận được vì chặn nhầm làm loop dừng |
| **Hook `onFailure: block` + `python3 -I`** | Thiếu Python hoặc hook quá 10 giây mà cho qua là chạy không lớp chặn dưới bypass. `-I` để `PYTHONPATH` không thay được module của guard | Không có `python3` thì session bị chặn mọi tool cho tới khi cài; cần Claude Code ≥ 2.1.295 |
| **Guard enforce theo role qua `agent_type` của hook** (`agentflow:dev`…) | Trước đây giới hạn role chỉ nằm ở prompt. Đo thật 2026-10-31: payload của subagent plugin có `agent_type: "<plugin>:<agent>"` | Session chính (orchestrator, người) không có role, chỉ chịu luật chung |
| **Allowlist `tools:` theo role** | Giảm từ ~70 tool còn đúng thứ cần: ít bề mặt khi bị prompt injection qua issue, ít tên tool trong context. Đo thật: allowlist có `ToolSearch` + `mcp__…__*` vẫn gọi được MCP deferred | MCP riêng của repo (vd DB, Dart) không tới được subagent, thêm vào frontmatter nếu cần. Project khai trùng URL GitHub MCP thì server plugin bị loại trùng và đổi tên tool — doctor báo |
| **Hook `SubagentStop` ép khối `RESULT`** | Orchestrator chỉ đọc khối này; thiếu thì trước đây chỉ biết khi đã tốn thêm lượt đọc. Hook trả agent về một lần | Agent chạm `maxTurns` vẫn có thể không có `RESULT` — dispatch §6 xử lý thành `blocked` |
| **Worktree dùng config và settings của checkout chính, kể cả khi branch có bản riêng** | `agentflow.yaml` chưa commit thì branch của worktree không có file: guard từng tắt hẳn. Còn nếu ưu tiên bản trong worktree thì DEV tự sửa `git.base` là qua được guard (audit độc lập phát hiện) | Đổi config phải vào checkout chính mới có hiệu lực với guard |
| **Hàng đợi lọc `repo:` + `is:issue`** | Board org dùng chung nhiều repo, số issue trùng nhau: không lọc thì DEV làm nhầm issue cùng số của repo này | — |
| **Journal ở cấp user (`~/.claude/agentflow/`)** | Bài học chỉ vào plugin ⇒ gom friction từ mọi project về một chỗ | Journal không đi theo repo |
| **Skill lệnh dùng `disable-model-invocation: true`** | Lệnh chỉ chạy khi người gọi; không tốn context lúc khởi động session | Không tự kích hoạt bằng ngôn ngữ tự nhiên |

## Non-goals (bất biến — `/learn` phải DỪNG nếu bài học đụng vào)

- **Agent không bao giờ merge PR**, không approve PR, không force-push, không push vào nhánh `git.protected`, không chạy/dispatch workflow (ở nhiều repo chạy workflow là deploy). Hook chặn cả năm. Push thường vào `staging.branch` là ngoại lệ duy nhất, chỉ REVIEWER làm — hook kiểm cả role.
- **Agent không bao giờ chuyển ticket ra khỏi `backlog`** khi chưa có xác nhận tường minh của người trong session.
- **Agent không bao giờ chuyển ticket ra khỏi `ready_to_merge`** trừ hai trường hợp: PR đã merge (→ `done`) hoặc có feedback của người trên PR (→ `in_progress`, PR về draft).
- **Agent không bao giờ sửa hay in nội dung path trong `forbidden`** (mặc định: secret).
- **Không message bus, không database ngoài GitHub.** Trạng thái = Status trên board + label + state block + comment.
- **Không thêm field bắt buộc vào state block** khi chưa có consumer đọc nó.
- **Không có bản sao thứ hai của một fact** trong prompt runtime — một nơi gốc, chỗ khác trỏ về.

## Giới hạn đã biết

- Pipeline báo xanh trước khi deploy xong thì QC có thể test bản cũ: plugin chỉ thấy check, không thấy phiên bản đang chạy trên staging. Giảm nhẹ: chờ tối thiểu 2 phút từ `deploy_at`, init yêu cầu check bao trùm bước deploy.
- Guard không thấy thứ chỉ lộ ra lúc chạy: script được ghi rồi chạy ở lệnh sau mà nội dung tạo động, `make deploy`, `npm run x`, payload decode (`base64 -d | sh`), `grep -r` trên thư mục con có file secret (guard chỉ soát file secret ở ngay thư mục được chỉ định), tên file ghép động (`cat "$(printf .%s env)"`). Agent cố tình lách vẫn lách được; guard nhắm vào agent bình thường hoặc bị văn bản trong issue dẫn dắt. Đọc file script chỉ áp luật git/gh, không áp luật path secret.
- Guard coi `source .env` là được phép: giá trị vào env của lệnh, không vào transcript; lệnh in env bị chặn riêng.
- `disableAllHooks` trong settings do người đặt thì hook không chạy; subagent không sửa được file đó, session chính bị chặn khi ghi key này.
- Projects v2 không có compare-and-swap; compare-then-write chỉ thu hẹp cửa sổ race. So sánh Status đặt **trước** khi ghi state/comment/label: eval 2026-10-31 cho thấy so sánh ở cuối làm abort để lại state block và label nửa vời. **Một loop session cho mỗi repo** là giả định vận hành.
- Projects v2 không có history API; metrics dựng lại từ timestamp của comment `[AF:…]`.
- `updateProjectV2Field` thay toàn bộ option; `ProjectV2SingleSelectFieldOptionInput.id` (introspect 2026-10-30) cho phép giữ option sẵn có ⇒ `status-apply` luôn truyền id của option cũ, chỉ option bị bỏ mới mất Status của card (cần `--allow-drop`). Hành vi giữ id mới verify qua schema, chưa verify end-to-end trên board có card — `status-plan` luôn chạy trước.
- Mention chính mình không tạo notification — mention người khác (`people.*`) mới có tác dụng.
