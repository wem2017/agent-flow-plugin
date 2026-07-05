---
name: git-flow-working
description: Áp dụng các git convention tech-agnostic cho các agent AgentFlow (chủ yếu là DEV) — branch từ default branch, Conventional Commits (đủ bộ type + notation cho breaking-change), shape của PR và các keyword link issue, sync theo rebase-first, và các safety rule cứng (không force-push lên shared branch, không merge, không đụng forbidden_paths). Dùng khi một agent tạo branch, commit, hoặc mở/update PR.
---

# AgentFlow Git Flow

Cách DEV biến một issue thành PR review được mà không bao giờ làm hỏng repo. Cái này language- và framework-agnostic: chỉ giả định có git và các GitHub primitive. Mọi tên bên dưới đều đến từ `.claude/agentflow.yaml` — đọc yaml, đừng bao giờ hardcode. Kết hợp cái này với skill: project-board-protocol cho state machine và skill: setup-agentflow để gate GitHub access.

## Branching

Việc mới luôn branch từ `project.default_branch`, không bao giờ từ một feature branch khác. Tên branch là:

```
<agents.dev.branch_prefix><kind>/<issue#>-<kebab-slug>
```

trong đó **kind** đến từ label `type/*` của issue: `type/feature → feat`, `type/bug → fix`, `type/improvement → chore`.

Với default `agents.dev.branch_prefix: "agent/dev/"`, issue #42 `type/feature` "CSV export for reports" thành `agent/dev/feat/42-csv-export`; issue #43 `type/bug` "logo redirect" thành `agent/dev/fix/43-logo-redirect`:

```bash
git fetch origin
git switch -c agent/dev/feat/42-csv-export origin/<default_branch>
```

Quy tắc:

- Một issue → một branch → một PR. Cái `<issue#>` trong tên gắn branch với issue của nó và với in-flight guard (`flow:in-progress`) trong skill: project-board-protocol — bản thân claim chính là assignee của issue, được set khi `/start` nhặt ticket ra khỏi `flow:inbox`.
- **Rework tái dùng ĐÚNG branch và PR cũ.** Khi một issue quay lại dưới dạng `flow:ready-for-dev` với label `rework`, checkout nó và push thêm commit — đừng bao giờ mở branch hay PR trùng lặp cho cùng một issue.
- Việc do người (non-agent) làm thì dùng prefix quy ước khác: `feature/`, `fix/`, `chore/`. Agent chỉ tạo branch dưới `agents.dev.branch_prefix`.

```bash
# resume an existing rework branch
git fetch origin
git switch agent/dev/feat/42-csv-export   # already exists from the first attempt
```

## Commits

Dùng [Conventional Commits 1.0.0](https://www.conventionalcommits.org/): `<type>(<scope>): <subject>`. Spec công nhận `feat` và `fix`; phần còn lại bên dưới là bộ conventional (Angular) mà tooling kỳ vọng — dùng chúng để automation changelog/semver phân loại mỗi commit cho đúng.

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
- **Breaking change:** thêm `!` sau type/scope **và/hoặc** thêm footer `BREAKING CHANGE:` (viết hoa, hoặc `BREAKING-CHANGE:`) mô tả cái break — vd `feat(api)!: drop v1 auth header`. Cái này báo hiệu một API break cho QC và người (→ MAJOR bump). Đừng break API một cách âm thầm.
- Tham chiếu issue trong body, không phải subject: `Refs #42` (để PR mang `Closes #42`).
- Giữ commit **nhỏ và review được** — mỗi commit một thay đổi logic. Đừng gộp một refactor chung với một feature.

```bash
git add src/reports/export.*
git commit -m "feat(reports): add CSV export endpoint" -m "Refs #42"
```

## Pull requests

Mở PR ngay khi có gì đó để review. Cấu trúc:

- **Title:** `<type>(#<issue>): <summary>` — vd `feat(#42): CSV export for reports`.
- **Body phải bao gồm:**
  - `Closes #<issue>` (auto-link và auto-close khi merge). Bất kỳ closing keyword nào cũng được, case-insensitive: `close/closes/closed`, `fix/fixes/fixed`, `resolve/resolves/resolved`. **Auto-close chỉ kích hoạt khi base của PR là default branch** — AgentFlow luôn nhắm tới `project.default_branch`, nên điều này đúng; giữ nguyên như vậy. Với một issue ở repo **khác**, dùng dạng qualified `Closes owner/repo#<n>`.
  - Acceptance Criteria của issue được mirror thành một checklist (tick từng item khi hoàn thành — cái này feed vào DoD trong skill: project-board-protocol).
  - Nó đụng vào surface nào (các label `component/*`) và cách chạy mỗi cái — một project có thể có một surface hoặc nhiều.
- **Không request reviewer nào.** QC review trên PR và một người merge; đừng thêm GitHub reviewer hay auto-merge.

```bash
gh pr create \
  --base "<default_branch>" \
  --head "agent/dev/feat/42-csv-export" \
  --title "feat(#42): CSV export for reports" \
  --body "Closes #42

## Acceptance Criteria
- [ ] Endpoint returns RFC 4180 CSV
- [ ] Empty result set returns header row only

## Surfaces
- component/<surface> — install/lint/test via surfaces.<surface>.commands (one bullet per touched surface)"
```

Sau khi mở PR, post `[DEV]` lên issue kèm link PR và swap label `flow:*` theo skill: project-board-protocol.

### Rework trên một PR đang tồn tại

Đừng mở PR mới. Push lên cùng branch, rồi comment:

```
[DEV] Reworked rejection #N — addressed: <one line per QC item, citing the fix>
```

Tick các checkbox AC mà rework giờ đã thỏa mãn. DEV BẮT BUỘC đọc entry `QC rejections` mới nhất trong state comment trước khi đổi code (xem skill: project-board-protocol).

### QC test commits

QC cũng commit vào **PR branch đang tồn tại của DEV** (cái mà nó đã checkout bằng `gh pr checkout <n>`). Dùng automation skill của mình, QC có thể **thêm test identifier** mà suite cần (vd `testID` / `data-testid` / key / a11y label) vào implementation và **viết test file** map với AC, rồi `git add` + `git commit -m "test(...): …"` + `git push` lên cùng branch đó. QC:

- chỉ push lên PR branch **đang tồn tại** — không bao giờ mở branch hay PR mới, và không bao giờ force-push;
- chỉ đổi **test code và test identifier** — không bao giờ implementation logic. Một logic bug thật sự là một `[QC] ❌` trả về DEV, không phải một fix mà QC tự áp dụng;
- tôn trọng cùng **union** forbidden-paths như DEV (`agents.dev.forbidden_paths` + `forbidden_paths` của mọi surface đụng tới) cho bất kỳ file nào nó edit;
- **không bao giờ merge.**

```bash
gh pr checkout 42                       # DEV's existing branch (e.g. agent/dev/feat/42-csv-export)
git add <test files + touched impl test-ids>
git commit -m "test(reports): cover CSV export AC1-AC3"
git push                                # same branch — no new branch, no --force
```

Xem skill: project-board-protocol cho QC verdict và cái pin `HEAD_SHA` sau commit.

## Sync & conflicts

Giữ branch cập nhật với `default_branch` để PR merge sạch:

```bash
git fetch origin
git rebase origin/<default_branch>     # preferred — clean linear history
# ...resolve any conflicts locally...
git add <resolved-files>
git rebase --continue
```

- **Rebase là mặc định** — nó giữ history tuyến tính. Chỉ dùng `git merge origin/<default_branch>` **khi** convention được ghi lại của project yêu cầu merge commit (nêu trong `CLAUDE.md`, hoặc branch-protection bắt buộc chúng); còn lại luôn rebase.
- Resolve conflict ở **local**; đừng bao giờ push một branch còn conflict marker.
- Một rebase viết lại branch của bạn, nên cú push theo sau cần một lease, không phải force thường: `git fetch origin` ngay trước đó, rồi `git push --force-with-lease --force-if-includes` (lease + include-check bảo vệ khỏi clobber việc bạn chưa thấy). Đừng bao giờ làm trên một branch mà người khác đang dùng chung — xem Safety rules.
- **Sau mỗi lần sync, chạy lại các tier command của surface đã đụng** (các type trong `agents.qc.tiers.<tier>`, map tới `surfaces.<name>.commands`) — một rebase sạch vẫn có thể làm hỏng behavior.

## Safety rules (cứng — không bao giờ vi phạm)

| Quy tắc | Lý do |
|------|-----|
| Không bao giờ `git push --force` lên một shared / PR branch | Viết lại history mà QC có thể đã review; làm hỏng PR. Chỉ dùng `--force-with-lease` trên một agent branch chưa ai khác đụng tới, và chỉ ngay sau một local rebase. |
| Không bao giờ push lên `project.default_branch` | Nó được protect và thuộc sở hữu của con người. Mọi thay đổi đi qua một PR. |
| Không bao giờ merge một PR | Chỉ con người merge, sau khi issue đạt `flow:ready-for-human-review`. Agent dừng ở đó. |
| Không bao giờ edit `agents.dev.forbidden_paths` | Các glob no-touch global (CI, infra, secret, keystore). Áp dụng cho mọi surface. |
| Không bao giờ edit `forbidden_paths` của một surface | Các glob no-touch theo từng surface (vd signing config). |
| Không bao giờ commit một secret | Tham chiếu credential qua `${ENV_NAME}` (khai báo dưới `env:`); đừng bao giờ hardcode một token. Xem skill: setup-agentflow. |

Trước khi commit, sanity-check diff so với các forbidden glob:

```bash
git diff --cached --name-only   # confirm nothing matches agents.dev.forbidden_paths
                                # or the touched surface's forbidden_paths
```

Nếu một thay đổi cần thiết rơi vào bên trong một forbidden path, **dừng và escalate** lên con người qua đường clarification/escalation trong skill: project-board-protocol — đừng work around nó. Tập no-touch hiệu lực là **union** của `agents.dev.forbidden_paths` và `forbidden_paths` của mọi surface đụng tới.

## Surfaces & commands

`surfaces:` là một open map — một project chỉ khai báo những surface nó có (các key nó chọn: có thể chỉ `.`, có thể `backend`+`web`+`mobile`, mix bất kỳ). Đừng bao giờ giả định một bộ ba cố định. Các label `component/*` của một issue chỉ đích danh nó đụng vào surface nào.

Một issue có thể mang một label `component/*` hoặc nhiều. Dù sao vẫn giữ nó trong **một branch và một PR** — đừng split theo surface. Nhưng chạy command của từng surface đụng tới một cách độc lập:

- DEV: trong khi code, chạy `surfaces.<name>.commands` liên quan cho mọi surface bạn đã đổi (skip bất kỳ command nào được set thành `""`). Trên một branch fresh hoặc vừa rebase, chạy `commands.install` **trước** để deps có sẵn trước khi lint/test. **Lint/analyze phải green trước khi handoff** — `commands.lint` của mọi surface đụng tới (vd `go vet`, `flutter analyze`, `eslint`) phải exit 0 trước khi DEV bàn giao issue cho QC. Đây là một pre-handoff gate có tên hẳn hoi, không phải tùy chọn.
- QC: với tier của issue, chạy từng type trong `agents.qc.tiers.<tier>` trên **mọi** surface đụng tới, theo thứ tự; tất cả phải exit 0 (xem skill: project-board-protocol). QC cũng chạy `commands.install` trước trên bản checkout PR-head fresh của mình.

```bash
# For each surface S named by the issue's component/* labels (could be one, could be many):
for S in <the touched surface keys>; do
  ( cd <surfaces.$S.path> \
      && <surfaces.$S.commands.install> \   # FIRST — skip if "" (missing deps cause false-fail lint/test)
      && <surfaces.$S.commands.lint> \
      && <surfaces.$S.commands.test> )      # skip any "" command
done
```

Nhắc tới mọi surface đụng tới trong body PR để QC biết đủ bộ command cần chạy.
