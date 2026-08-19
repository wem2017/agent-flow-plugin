---
name: git-flow-working
description: Git convention tech-agnostic cho agent AgentFlow — branch naming, Conventional Commits, shape của PR, sync rebase-first, và safety rule cứng (không force-push, không merge, không đụng forbidden paths). Dùng khi một agent tạo branch, commit, hoặc mở/update PR.
---

# AgentFlow Git Flow

Cách DEV biến một issue thành PR review được. Default branch suy từ `git rev-parse --abbrev-ref origin/HEAD`, owner/repo từ `git remote get-url origin` — **đừng hardcode, và đừng đi tìm chúng trong config**. Kết hợp với skill `agentflow-protocol` (state machine, forbidden paths, gate secret).

## Branching

Việc mới luôn branch từ **default branch**, không bao giờ từ một feature branch khác:

```
agent/dev/<kind>/<issue#>-<kebab-slug>
```

`kind` đến từ label `type/*` của issue: `type/feature → feat`, `type/bug → fix`, `type/improvement → chore`. Prefix `agent/dev/` là **hằng số plugin**. Issue #42 `type/feature` "CSV export for reports" thành:

```bash
git fetch origin
git switch -c agent/dev/feat/42-csv-export origin/<default_branch>
```

Quy tắc:

- **Một issue → một branch → một PR.** `<issue#>` trong tên gắn branch với issue và với in-flight guard (Status `In Progress`); bản thân claim là **assignee** của issue.
- **Có open PR sẵn có → tái dùng ĐÚNG branch và PR đó.** Bất cứ khi nào một issue quay lại `Ready for Dev` mà đã có open PR link tới nó — QC rework (mang label `rework`) HAY PR-feedback re-entry (không có `rework`; người đã review PR rồi ticket được re-spec) — checkout đúng branch cũ và push thêm commit. **Đừng bao giờ** mở branch/PR trùng lặp cho cùng một issue. Chỉ tạo branch mới khi issue **chưa** có PR nào. Reuse gắn với *sự tồn tại của open PR*, không phải với label `rework`.
- `<kebab-slug>` rút từ tiêu đề issue, **ASCII thường + gạch ngang** (`a-z0-9-`), ~3–5 từ — tiêu đề tiếng Việt phải bỏ dấu. Git từ chối ref chứa khoảng trắng, `~ ^ : ? * [`, `..`, hoặc component kết thúc bằng `.lock`.
- Việc do người (non-agent) làm thì dùng prefix quy ước khác: `feature/`, `fix/`, `chore/`. Agent chỉ tạo branch dưới `agent/dev/`.

## Commits

[Conventional Commits 1.0.0](https://www.conventionalcommits.org/): `<type>(<scope>): <subject>` — `feat` · `fix` · `refactor` · `perf` · `test` · `docs` · `build` · `ci` · `style` · `chore`.

- Subject **imperative**, không dấu chấm cuối, ≤ ~72 ký tự: `feat(reports): add CSV export endpoint`. `scope` nên là tên surface hoặc module.
- **Breaking change:** `!` sau type/scope và/hoặc footer `BREAKING CHANGE:` — vd `feat(api)!: drop v1 auth header`. Đừng break API âm thầm.
- Tham chiếu issue trong **body** (`Refs #42`), không phải subject — PR mới mới mang `Closes #42`.
- Commit **nhỏ và review được** — mỗi commit một thay đổi logic. Đừng gộp refactor với feature.

## Pull requests

**Push branch lên origin trước** — `create_pull_request` với `head` chưa tồn tại trên origin trả **422**:

```bash
git push -u origin <branch>     # lần đầu
git push                        # các lần sau — fast-forward, không bao giờ --force
```

Mở PR ngay khi có gì đó để review.

- **Title:** `<type>(#<issue>): <summary>` — vd `feat(#42): CSV export for reports`.
- **Body phải có:**
  - `Closes #<issue>` (auto-link + auto-close khi merge). Keyword nào cũng được, case-insensitive: `close/closes/closed`, `fix/fixes/fixed`, `resolve/resolves/resolved`. **Auto-close chỉ kích hoạt khi base của PR là default branch** — AgentFlow luôn nhắm tới đó, giữ nguyên như vậy. Issue ở repo khác → dạng qualified `Closes owner/repo#<n>`.
  - Acceptance Criteria của issue mirror thành checklist (tick từng item khi xong — feed vào DoD). Checklist phải nằm trong **body PR**, không phải một comment — GitHub chỉ hiện tiến độ task list của comment đầu tiên.
  - **Thay đổi gì** — mô tả kỹ thuật ngắn: vùng code đã đụng và cách tiếp cận. **PR là chỗ ĐẦU TIÊN được nói bằng code**: ticket cố ý chỉ mô tả hành vi quan sát được, còn reviewer cần biết cách làm. Ranh giới: phần mirror AC giữ nguyên ngôn ngữ hành vi của ticket — đừng viết lại nó thành mô tả implementation.
  - `type/bug` → thêm một dòng cho regression test: nó tái hiện đúng repro steps nào, và bằng chứng nó **fail trên code trước fix** (DoD của bug, `agentflow-protocol` §5).
  - Nó đụng surface nào (các label `component/*`) và cách chạy mỗi cái.
- **Không request reviewer nào.** QC review trên PR và một con người merge; đừng thêm GitHub reviewer hay auto-merge.

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

    ## Thay đổi
    - <vùng code đã đụng + cách tiếp cận — nói bằng ngôn ngữ kỹ thuật>

    ## Surfaces
    - component/<surface> — build/lint/test theo convention của repo
```

Sau khi mở PR, post `[DEV] Opened PR #<n>` lên issue rồi handoff Status → `In QC` theo write order (`agentflow-protocol` §8).

### Rework trên một PR đang tồn tại

Đừng mở PR mới. Push lên cùng branch, rồi comment:

```
[DEV] Reworked rejection #N — addressed: <một dòng mỗi QC item, trích cách fix>
```

Tick các AC checkbox mà rework giờ đã thỏa mãn. DEV **bắt buộc** đọc entry `QC rejections` mới nhất trong section state trước khi đổi code.

- **Đồng bộ branch trước khi sửa:** `git fetch origin` rồi `git pull --rebase origin <branch>` — QC đã có thể push test commit lên chính branch này, và commit rework của bạn phải nằm trên nó.
- **Một khi QC đã push test commit lên branch, đừng viết lại history của nó.** QC author test ở *mọi* vòng QC, nên điều này đúng ngay từ vòng rework ĐẦU TIÊN — đừng đợi tới vòng thứ hai. Rebase lên default branch (và cú `--force-with-lease` đi kèm) chỉ hợp lệ khi branch **chưa có commit của ai khác**; QC đã đụng vào rồi thì rebase là ghi đè commit của QC — an toàn duy nhất là commit thêm rồi push thường (fast-forward). Vẫn cần sync với default branch (QC reject vì PR `BEHIND`) → `git merge origin/<default_branch>` là **ngoại lệ có chủ đích** của rebase-first ở §Sync: nó là cách sync duy nhất không viết lại commit của QC.

### QC test commits trên cùng branch

QC cũng commit test lên **PR branch đang tồn tại của DEV** (luật đầy đủ: `agents/qc.md` §3a). Hệ quả cho DEV: branch này **có commit của người khác** kể từ vòng QC đầu tiên — xem luật rebase ở §Rework ngay trên.

## Sync & conflicts

```bash
git fetch origin
git rebase origin/<default_branch>     # preferred — history tuyến tính
```

- **Rebase là mặc định.** Chỉ `git merge origin/<default_branch>` khi convention có ghi lại của project yêu cầu merge commit (nêu trong `CLAUDE.md`, hoặc branch-protection bắt buộc); còn lại luôn rebase.
- Resolve conflict ở **local**; đừng bao giờ push branch còn conflict marker.
- Rebase viết lại branch của bạn, nên cú push sau đó cần một **lease**, không phải force thường: `git fetch origin` ngay trước, rồi `git push --force-with-lease --force-if-includes`. Đừng bao giờ làm trên branch người khác đang dùng chung.
- **Sau mỗi lần sync, chạy lại test của các surface đã đụng** — một rebase sạch vẫn có thể làm hỏng behavior.

## Safety rules (cứng — không bao giờ vi phạm)

| Quy tắc | Kèm theo |
|---|---|
| Không bao giờ `git push --force` lên shared / PR branch | Chỉ `--force-with-lease` trên agent branch chưa ai khác đụng, và chỉ ngay sau một local rebase. |
| Không bao giờ push lên default branch | Mọi thay đổi đi qua một PR. |
| Không bao giờ merge một PR | Chỉ con người merge, sau khi ticket đạt Status `Ready for Review`. Agent dừng ở đó. |
| Không bao giờ edit path trong forbidden set | Công thức: `agentflow-protocol` §1. |
| Không bao giờ commit một secret | Tham chiếu credential bằng TÊN key (`${TELEGRAM_BOT_TOKEN}`, `${GITHUB_TOKEN}`), không bao giờ bằng giá trị. `GITHUB_TOKEN` **có** trong env nên Bash đọc được — vì vậy không bao giờ `echo` nó, không nội suy nó vào command string, không ghi nó vào file. |

Trước khi commit, sanity-check diff so với forbidden glob:

```bash
git diff --cached --name-only   # không file nào được khớp tập no-touch hiệu lực
```

Tập no-touch hiệu lực — công thức ở `agentflow-protocol` §1.

Nếu một thay đổi cần thiết rơi vào forbidden path, **dừng và escalate** qua clarification flow (`agents/dev.md`) — đừng work around nó.

## Surfaces

- Label `component/*` của issue map tới surface bị chạm. Repo không khai báo `surfaces` → không có label component, agent gate toàn repo.
- Một issue có thể đụng nhiều surface — vẫn giữ **một branch và một PR**, đừng split theo surface.
- Build/lint/test từng surface theo convention của chính repo, trong `surfaces.<key>.path`, thứ tự: cài deps → lint/analyze → test. Chi tiết theo role ở `agents/dev.md` / `agents/qc.md`; mapping QC tier → test category ở `agentflow-protocol` §1 (bảng hằng số).
