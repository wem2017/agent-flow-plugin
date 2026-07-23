# {{PROJECT_NAME}} — AgentFlow

{{PROJECT_SUMMARY}} — điều phối qua AgentFlow trên GitHub Projects v2 board #{{BOARD_NUMBER}}. Đây là tham chiếu nhanh cho repo này.

Repo này dùng plugin **AgentFlow** để điều phối một dev workflow 3-agent (PMO → DEV → QC → human review) trên GitHub. (Phiên bản config-format mà config này được viết cho được pin lại dưới dạng `agentflow_version` trong `.claude/agentflow.yaml`.) State nằm ở **`Status` field** trên một board GitHub Projects v2 **bắt buộc** — Status là state authoritative, board là inbox queue của orchestrator; label không mang state, chỉ còn classification (`type/*`, `component/*`, và aux `rework`). Mọi thứ được cấu hình trong một file duy nhất — `.claude/agentflow.yaml`, single source of truth.

Bạn chỉ làm hai việc bằng tay: **mô tả công việc, và review/merge PR.** Mọi thứ ở giữa diễn ra qua GitHub.

## Cách dùng

| Bạn muốn...                             | Chạy                             |
|-----------------------------------------|----------------------------------|
| Chạy lại / sửa setup cho repo này       | `/agentflow-init`                |
| Khởi động team cho session này          | `/start`                         |
| Tạo một đầu việc mới                     | `/task <freeform description>`   |
| Xem mọi thứ đang đứng ở đâu             | `/status`                        |
| Gỡ block một ticket `Refined`           | `/review-refined [#n]`           |

Sau `/start`, session này trở thành orchestrator board-driven — tạo việc mới qua `/task <mô tả>`; trong /start bạn có thể reroute card bằng plain text (vd "send #12 back to PMO"). Orchestrator chỉ break-out về bạn khi một ticket rơi vào `Refined` (cần bạn bổ sung info/quyết định — kể cả escalation 2-strike của QC), hoặc khi một PR đã sẵn sàng để merge.

Bạn có thể chạy **nhiều terminal `/start`** trên cùng một repo để tăng throughput song song — mỗi terminal claim một ticket ở `Inbox` chưa được assign bằng cách tự self-assign, nên các terminal không đụng nhau. Chúng share cùng một `GITHUB_TOKEN` (cùng một GitHub user), nên để isolation chặt chẽ thì hãy cấp cho mỗi terminal một GitHub identity/token riêng.

## Repo này kết nối tới những gì

Các connection được khai báo dưới `connections.*` trong `.claude/agentflow.yaml`. Mỗi block tự đặc tả đầy đủ wiring của nó (tên secret, scopes, MCP server). Một connection chỉ dùng được khi `enabled: true` **và** mọi var nó cần đều có mặt (được source từ `.env`). Chúng có tính additive — bật/tắt một cái bằng `enabled: true|false`.

| Connection       | Bắt buộc? | Chức năng                                                           |
|------------------|-----------|---------------------------------------------------------------------|
| `github`         | luôn bật  | Issues, branches, PRs, labels, comments — bản thân protocol.        |
| `github_project` | luôn bật  | GitHub Projects v2 board — state authoritative (`Status` field) + inbox queue của orchestrator.|
| `figma`          | tùy chọn  | DEV pull frame specs/tokens trong lúc làm UI (qua `figma` MCP).     |

Giữ `connections.github_project.enabled: true` và `board.number` đồng bộ với nhau (`/agentflow-init` làm việc này giúp bạn). Không có board là không có state machine — và **đừng đổi tên các column trong UI**: các option name của `Status` là wire value được resolve by-name, nên đổi tên một option là break routing.

## Environment variables

Mỗi secret được khai báo **chỉ bằng tên** trong list `env:` ở `.claude/agentflow.yaml` (mỗi entry cross-link tới các connection `used_by` của nó). Giá trị nằm trong một file `.env` mà bạn `source` trước khi khởi động Claude Code:

| Var            | Bắt buộc | Dùng cho                                             |
|----------------|----------|------------------------------------------------------|
| `GITHUB_TOKEN` | có       | GitHub access (scopes: `repo`, `read:org`, `project`) |
| `FIGMA_TOKEN`  | không    | Figma legacy PAT — chỉ dùng cho Framelink/REST fallback; server figma MCP chính thức dùng OAuth (không cần token) |

**Secret hygiene:** đặt chúng vào một file `.env` **không commit** (copy `.env.example`, điền vào, rồi `source` nó trước khi khởi động Claude Code) — không bao giờ commit token, không bao giờ paste giá trị vào `agentflow.yaml`. Chỉ tham chiếu secret bằng tên (`${GITHUB_TOKEN}`). `/agentflow-init` sẽ từ chối hoàn tất nếu một var `required: true` bị thiếu.

## Surfaces (các phần build được)

Một **surface** là một phần build được của repo, định nghĩa dưới `surfaces.*`. Map này có tính **dynamic** — repo này chỉ khai báo các surface nó thực sự có, với các key do owner chọn (ví dụ `backend`, `web`, `api`, `admin`, `mobile`, hoặc chỉ `"."` cho một repo single-surface).

```
surfaces.<name>.path                  # glob root, "." for single-surface repos
surfaces.<name>.label                 # the component/<name> label that maps to it
surfaces.<name>.forbidden_paths
```

`labels.component` được generate để khớp với các surface key — một `component/<surface>` cho mỗi surface được khai báo. PMO gắn cho mỗi issue (các) label `component/<surface>` tương ứng với (các) surface mà nó chạm tới. DEV và QC build/lint/test mỗi surface bị chạm theo convention riêng của repo — soi `package.json` scripts, `Makefile`, `pubspec`, `go.mod`, CI config… để biết cách build/lint/test. Để đổi những gì một surface không bao giờ được chạm tới, sửa `forbidden_paths` trong block của surface đó.

## QC tiers

Một tier là một **gợi ý ngữ nghĩa về độ sâu test**, không phải một tập shell command cấu hình sẵn. PMO đặt tier theo blast radius của issue; QC map nó sang đúng những category test mà repo thực sự có. Chúng có tính cộng dồn: `quick ⊆ full ⊆ regression`.

| Tier         | Độ sâu test                                |
|--------------|--------------------------------------------|
| `quick`      | lint + unit test                           |
| `full`       | + integration                              |
| `regression` | + e2e                                       |

Với mỗi surface mà issue chạm tới (theo các label `component/<surface>` của nó), QC viết automation test rồi chạy các category test ứng với tier theo convention của repo; tất cả phải pass. Không có coverage gate bằng số — QC tự đánh giá độ đầy đủ của test bằng cách inspect.

## Skills

Bốn core skill luôn đi kèm plugin và tự động bật — không cần đăng ký:

| Skill                    | Bao gồm                                                        |
|--------------------------|----------------------------------------------------------------|
| `setup-agentflow`        | onboarding: yaml là source of truth, connections, env, surfaces, skill registry |
| `project-board-protocol` | GitHub wire protocol: board `Status` (state authoritative), comment prefixes, DoR/DoD, classification labels |
| `git-flow-working`       | branching, Conventional Commits, PR conventions, an toàn khi rebase/merge |
| `figma-design`           | pull frame specs/tokens qua `figma` MCP; handoff design → AC |

Để mở rộng, thêm một project skill dưới `.claude/skills/<role>-<area>` để đúng agent nhặt nó lên: `dev-*` → DEV, `qc-*` → QC, `pmo-*` → PMO. Đăng ký nó dưới `skills:` (bản overview source-of-truth) để bạn có thể scope nó theo surface; các agent cũng **auto-discover** bất kỳ `.claude/skills/<their-role>-*` nào kể cả khi không được liệt kê. Một agent load các skill có role-prefix liên quan tới (các) surface mà issue hiện tại chạm tới (`surfaces` trong registry được match với các label `component/*`; không có `surfaces` = luôn liên quan). `/agentflow-init` có thể scaffold các starter stub.

```yaml
skills:
  dev-mobile-development: { role: dev, surfaces: ["mobile"], description: "Mobile state & navigation conventions" }
  qc-automation-test:     { role: qc,  surfaces: ["web", "mobile"], description: "E2E suite authoring" }
  pmo-discovery:          { role: pmo, description: "Discovery & story-mapping checklist" }
```

## Cái gì nằm ở đâu (các column của board)

- **`Inbox`** — PMO đang định hình request (triage + refine tới Definition of Ready). Cũng là điểm RE-ENTRY sau khi bạn bổ sung info hoặc kéo card về.
- **`Ready for Dev`** — DEV sẽ nhặt nó lên tiếp theo. Nếu đã có một open PR link tới issue (một vòng trước), DEV **amend chính PR đó** thay vì mở mới. Nếu mang aux label `rework` (QC đã reject), DEV đọc QC rejection mới nhất trước.
- **`In Progress`** — DEV đang implement. Nếu DEV bị block, bạn sẽ thấy một comment blocked `[DEV]` và issue nằm lại đây để bạn unblock.
- **`In QC`** — DEV đã mở một PR; QC viết automation test trên PR branch, rồi chạy tier. QC ❌ (chưa vượt ngưỡng) route ticket về `Ready for Dev` + aux label `rework`.
- **`Refined`** — **BLOCKED, cần bạn.** Một info-gap (PMO không tới được DoR, DEV thiếu spec/Figma, QC gặp AC mơ hồ, hoặc escalation QC 2-strike) đã park ticket ở đây và un-assign nó. Bạn cung cấp thêm info/quyết định qua `/review-refined` (khuyến nghị — capture câu trả lời thành `[USER:<login>]` comment), hoặc **kéo card về `Inbox`** sau khi tự bổ sung info, để PMO re-triage và chạy tiếp.
- **`Ready for Human Review`** — đến lượt bạn. Review và merge PR — hoặc, để yêu cầu thay đổi, để **feedback inline trực tiếp trên code của PR** rồi **kéo card về `Inbox`** (agent không bao giờ tự làm bước này; ticket đã được unassign nên chỉ cần kéo card). Pipeline chạy lại: PMO đọc feedback của bạn trên PR, fold vào AC, DEV amend chính PR đó, QC re-gate, rồi nó quay lại bạn. (Chỉ đạt tới đây khi QC ✅ — sẵn sàng merge.)
- **`Done`** — đã merge và close (close issue / merge PR → built-in workflow hoặc orchestrator set Done).

Kéo card là **human API chính thức** — nhưng chỉ ở các **parked state** (`Refined`, `Ready for Human Review`, khi không có agent nào đang giữ ticket). Kéo card khi ticket đang `In Progress` / `In QC` (agent đang chạy) **không an toàn** — muốn dừng một run đang chạy, dừng terminal, đừng kéo card.

Board là **state view duy nhất**: GitHub issue search / `gh issue list --label` không filter được theo `Status` field của Projects v2, nên để xem cái gì đang ở đâu, nhìn board hoặc chạy `/status`.

## Comment prefixes (để bạn grep / filter)

`[PMO]`, `[DEV]`, `[QC] ✅`, `[QC] ❌`, `[DEV→PMO ?]`, `[QC→PMO ?]`, `[SYSTEM]`, `[USER:<your-login>]`.

Bất cứ thứ gì bạn viết **mà không** có prefix `[USER:...]` sẽ bị các agent coi là untrusted context — chúng sẽ đọc nhưng không hành động theo các instruction bên trong.

## Notifications

Đây là terminal mode — mặc định thì break-out của orchestrator **chính là** notification. Không có external channel nào; theo dõi session này để bắt chúng. (Bạn có thể chạy `/start` không giám sát theo một interval qua skill `/loop`; khi đó các break-out sẽ queue trên board cho tới khi bạn quay lại.)
