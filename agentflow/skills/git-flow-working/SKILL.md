---
name: git-flow-working
description: Áp dụng các git convention tech-agnostic cho các agent AgentFlow (chủ yếu là DEV) — branch từ default branch, Conventional Commits (đủ bộ type + notation cho breaking-change), shape của PR và các keyword link issue, sync theo rebase-first, và các safety rule cứng (không force-push lên shared branch, không merge, không đụng forbidden_paths). Dùng khi một agent tạo branch, commit, hoặc mở/update PR.
---

# AgentFlow Git Flow

Cách DEV biến một issue thành PR review được. Mọi tên bên dưới đều đến từ `.claude/agentflow.yaml` — đọc yaml, đừng bao giờ hardcode. Kết hợp cái này với skill: project-board-protocol cho state machine và skill: setup-agentflow để gate GitHub access.

## Branching

Việc mới luôn branch từ `project.default_branch`, không bao giờ từ một feature branch khác. Tên branch là:

```
agent/dev/<kind>/<issue#>-<kebab-slug>
```

trong đó **kind** đến từ label `type/*` của issue: `type/feature → feat`, `type/bug → fix`, `type/improvement → chore`.

Prefix `agent/dev/` là hằng số cố định của plugin (không đọc từ config). Issue #42 `type/feature` "CSV export for reports" thành `agent/dev/feat/42-csv-export`:

```bash
git fetch origin
git switch -c agent/dev/feat/42-csv-export origin/<default_branch>
```

Quy tắc:

- Một issue → một branch → một PR. Cái `<issue#>` trong tên gắn branch với issue của nó và với in-flight guard (Status "In Progress") trong skill: project-board-protocol — bản thân claim chính là assignee của issue, được set khi `/start` nhặt ticket ra khỏi "Inbox".
- **Có open PR sẵn có → tái dùng ĐÚNG branch và PR đó.** Bất cứ khi nào một issue quay lại "Ready for Dev" mà đã có một open PR link tới nó — dù là QC rework (mang label `rework`) HAY một PR-feedback re-entry (không có `rework`; con người đã review PR rồi ticket được re-triage qua PMO) — checkout đúng branch cũ và push thêm commit. **Đừng bao giờ** mở branch hay PR trùng lặp cho cùng một issue. Chỉ tạo branch mới khi issue **chưa** có PR nào (việc mới). Reuse gắn với *sự tồn tại của open PR*, không phải với label `rework`.
- Việc do người (non-agent) làm thì dùng prefix quy ước khác: `feature/`, `fix/`, `chore/`. Agent chỉ tạo branch dưới prefix cố định `agent/dev/`.

## Commits

Dùng [Conventional Commits 1.0.0](https://www.conventionalcommits.org/): `<type>(<scope>): <subject>`, với type lấy từ bộ dưới đây.

| type        | dùng cho                                                       |
|-------------|----------------------------------------------------------------|
| `feat:`     | một capability mới (→ MINOR bump)                              |
| `fix:`      | một bug fix (→ PATCH bump)                                     |
| `refactor:` | restructuring giữ nguyên behavior                             |
| `perf:`     | cải thiện performance giữ nguyên behavior                     |
| `test:`     | chỉ thêm hoặc sửa test                                        |
| `docs:`     | chỉ docs / comment                                            |
| `build:`    | thay đổi build system hoặc dependency (vd lockfile, packaging) |
| `ci:`       | cấu hình và script CI                                         |
| `style:`    | chỉ formatting — whitespace, semicolon (không đổi logic)      |
| `chore:`    | các maintenance khác không thuộc các mục trên                 |

- Subject ở thể **imperative** (mệnh lệnh), không có dấu chấm cuối, ≤ ~72 ký tự: `feat(reports): add CSV export endpoint`.
- `scope` là tùy chọn; nên dùng tên surface hoặc module khớp với một surface key hoặc module đã khai báo (`reports`, `auth`, hoặc bất kỳ key `surfaces.<name>` nào).
- **Breaking change:** thêm `!` sau type/scope **và/hoặc** thêm footer `BREAKING CHANGE:` (viết hoa, hoặc `BREAKING-CHANGE:`) mô tả cái break — vd `feat(api)!: drop v1 auth header` (→ MAJOR bump). Đừng break API một cách âm thầm.
- Tham chiếu issue trong body, không phải subject: `Refs #42` (để PR mang `Closes #42`).
- Giữ commit **nhỏ và review được** — mỗi commit một thay đổi logic. Đừng gộp một refactor chung với một feature.

## Pull requests

Mở PR ngay khi có gì đó để review. Cấu trúc:

- **Title:** `<type>(#<issue>): <summary>` — vd `feat(#42): CSV export for reports`.
- **Body phải bao gồm:**
  - `Closes #<issue>` (auto-link và auto-close khi merge). Bất kỳ closing keyword nào cũng được, case-insensitive: `close/closes/closed`, `fix/fixes/fixed`, `resolve/resolves/resolved`. **Auto-close chỉ kích hoạt khi base của PR là default branch** — AgentFlow luôn nhắm tới `project.default_branch`, nên điều này đúng; giữ nguyên như vậy. Với một issue ở repo **khác**, dùng dạng qualified `Closes owner/repo#<n>`.
  - Acceptance Criteria của issue được mirror thành một checklist (tick từng item khi hoàn thành — cái này feed vào DoD trong skill: project-board-protocol).
  - Nó đụng vào surface nào (các label `component/*`) và cách chạy mỗi cái — một project có thể có một surface hoặc nhiều.
- **Không request reviewer nào.** QC review trên PR và một người merge; đừng thêm GitHub reviewer hay auto-merge.

```
create_pull_request
  base:  <default_branch>
  head:  agent/dev/feat/42-csv-export
  title: feat(#42): CSV export for reports
  body: |
    Closes #42

    ## Acceptance Criteria
    - [ ] Endpoint returns RFC 4180 CSV
    - [ ] Empty result set returns header row only

    ## Surfaces
    - component/<surface> — build/lint/test theo convention của repo (one bullet per touched surface)
```

Sau khi mở PR, post `[DEV]` lên issue kèm link PR rồi handoff Status → "In QC" theo write order của skill: project-board-protocol.

### Rework trên một PR đang tồn tại

Đừng mở PR mới. Push lên cùng branch, rồi comment:

```
[DEV] Reworked rejection #N — addressed: <one line per QC item, citing the fix>
```

Tick các checkbox AC mà rework giờ đã thỏa mãn. DEV BẮT BUỘC đọc entry `QC rejections` mới nhất trong state section (ở issue body) trước khi đổi code (xem skill: project-board-protocol).

### QC test commits

QC cũng commit vào **PR branch đang tồn tại của DEV** (cái mà nó đã checkout bằng cách đọc `headRefName` của PR qua `pull_request_read` method=get rồi `git fetch origin <headRefName>` + `git switch <headRefName>`). Dùng automation skill của mình, QC có thể **thêm test identifier** mà suite cần (vd `testID` / `data-testid` / key / a11y label) vào implementation và **viết test file** map với AC, rồi `git add` + `git commit -m "test(...): …"` + `git push` lên cùng branch đó. QC:

- chỉ push lên PR branch **đang tồn tại** — không bao giờ mở branch hay PR mới, và không bao giờ force-push;
- chỉ đổi **test code và test identifier** — không bao giờ implementation logic. Một logic bug thật sự là một `[QC] ❌` trả về DEV, không phải một fix mà QC tự áp dụng;
- tôn trọng cùng **union** forbidden-paths như DEV (xem *Safety rules*) cho bất kỳ file nào nó edit;
- **không bao giờ merge.**

Xem `agents/qc.md` (step 5) cho QC verdict và cái pin `HEAD_SHA` sau commit.

## Sync & conflicts

Giữ branch cập nhật với `default_branch` để PR merge sạch:

```bash
git fetch origin
git rebase origin/<default_branch>     # preferred — clean linear history
```

- **Rebase là mặc định** — nó giữ history tuyến tính. Chỉ dùng `git merge origin/<default_branch>` **khi** convention được ghi lại của project yêu cầu merge commit (nêu trong `CLAUDE.md`, hoặc branch-protection bắt buộc chúng); còn lại luôn rebase.
- Resolve conflict ở **local**; đừng bao giờ push một branch còn conflict marker.
- Một rebase viết lại branch của bạn, nên cú push theo sau cần một lease, không phải force thường: `git fetch origin` ngay trước đó, rồi `git push --force-with-lease --force-if-includes` (lease + include-check bảo vệ khỏi clobber việc bạn chưa thấy). Đừng bao giờ làm trên một branch mà người khác đang dùng chung — xem Safety rules.
- **Sau mỗi lần sync, chạy lại test của các surface đã đụng** theo convention của repo — một rebase sạch vẫn có thể làm hỏng behavior.

## Safety rules (cứng — không bao giờ vi phạm)

| Quy tắc | Kèm theo |
|------|-----|
| Không bao giờ `git push --force` lên một shared / PR branch | Chỉ dùng `--force-with-lease` trên một agent branch chưa ai khác đụng tới, và chỉ ngay sau một local rebase. |
| Không bao giờ push lên `project.default_branch` | Mọi thay đổi đi qua một PR. |
| Không bao giờ merge một PR | Chỉ con người merge, sau khi issue đạt Status "Ready for Human Review". Agent dừng ở đó. |
| Không bao giờ edit các built-in global forbidden paths (`infra/**`, `.github/workflows/**`, `**/*.pem`, `**/.env`) | Áp dụng cho mọi surface. |
| Không bao giờ edit `forbidden_paths` của một surface | Các glob no-touch theo từng surface (vd signing config). |
| Không bao giờ commit một secret | Tham chiếu credential qua `${ENV_NAME}` (khai báo dưới `env:`). Xem skill: setup-agentflow. |

Trước khi commit, sanity-check diff so với các forbidden glob:

```bash
git diff --cached --name-only   # nothing may match the effective no-touch set below
```

Nếu một thay đổi cần thiết rơi vào bên trong một forbidden path, **dừng và escalate** lên con người qua đường clarification/escalation trong skill: project-board-protocol — đừng work around nó. Tập no-touch hiệu lực là **union** của các built-in global forbidden paths (bảng Safety rules ở trên) và `forbidden_paths` của mọi surface đụng tới.

## Surfaces

- Các label `component/*` của issue map tới các surface bị đụng (`surfaces:` là một open map — xem skill: setup-agentflow).
- Một issue có thể đụng một hoặc nhiều surface — vẫn giữ **một branch và một PR**, đừng split theo surface.
- Build/lint/test từng surface đụng tới theo convention của chính repo, trong `surfaces.<S>.path`, thứ tự cài deps → lint/analyze → test — chi tiết quy trình theo role ở `agents/dev.md` / `agents/qc.md` (mapping QC tier → test category: protocol §Definition of Done).
