# AgentFlow — tham chiếu nhanh cho repo này

Repo này dùng plugin **AgentFlow** để điều phối một dev workflow 3-agent (PMO → DEV → QC → human review) trên GitHub. (Phiên bản plugin chính xác mà config này được viết cho được pin lại dưới dạng `agentflow_version` trong `.claude/agentflow.yaml`.) State nằm ở các **label** `flow:*` trên mỗi issue; một board GitHub Projects v2 là **bắt buộc** — nó là inbox queue của orchestrator và một mirror mà con người nhìn thấy được của các label đó để triage. Mọi thứ được cấu hình trong một file duy nhất — `.claude/agentflow.yaml`, single source of truth.

Bạn chỉ làm hai việc bằng tay: **mô tả công việc, và review/merge PR.** Mọi thứ ở giữa diễn ra qua GitHub.

## Cách dùng

| Bạn muốn...                             | Chạy                             |
|-----------------------------------------|----------------------------------|
| Chạy lại / sửa setup cho repo này       | `/agentflow-init`                |
| Khởi động team cho session này          | `/start`                         |
| Tạo một đầu việc mới                     | `/task <freeform description>`   |
| Xem mọi thứ đang đứng ở đâu             | `/status`                        |
| Gỡ block một ticket `flow:refined`      | `/review-refined [#n]`           |

Sau `/start`, session terminal này trở thành orchestrator — mô tả công việc bằng plain text và team (PMO → DEV → QC) sẽ chain tự động. Cần reroute một card (quay lại PMO, skip một stage, flag cho con người)? Chỉ cần nói bằng plain text ngay trong `/start` — ví dụ "send #12 back to PMO" — và orchestrator sẽ làm inline. Orchestrator chỉ break-out về bạn khi một ticket rơi vào `flow:refined` (cần bạn bổ sung info/quyết định — kể cả escalation 2-strike của QC), hoặc khi một PR đã sẵn sàng để merge. Gỡ block một ticket `flow:refined` bằng `/review-refined`.

Bạn có thể chạy **nhiều terminal `/start`** trên cùng một repo để tăng throughput song song — mỗi terminal claim một ticket `flow:inbox` chưa được assign bằng cách tự self-assign, nên các terminal không đụng nhau. Chúng share cùng một `GITHUB_TOKEN` (cùng một GitHub user), nên để isolation chặt chẽ thì hãy cấp cho mỗi terminal một GitHub identity/token riêng.

## Repo này kết nối tới những gì

Các connection được khai báo dưới `connections.*` trong `.claude/agentflow.yaml`. Mỗi block tự đặc tả đầy đủ wiring của nó (tên secret, scopes, MCP server). Một connection chỉ dùng được khi `enabled: true` **và** mọi var nó cần đều có mặt (được source từ `.env`). Chúng có tính additive — bật/tắt một cái bằng `enabled: true|false`.

| Connection       | Bắt buộc? | Chức năng                                                           |
|------------------|-----------|---------------------------------------------------------------------|
| `github`         | luôn bật  | Issues, branches, PRs, labels, comments — bản thân protocol.        |
| `github_project` | luôn bật  | GitHub Projects v2 board — inbox queue của orchestrator + một human mirror của các label `flow:*`.|
| `figma`          | tùy chọn  | DEV pull frame specs/tokens trong lúc làm UI (qua `figma` MCP).     |

Để bật/tắt Figma, sửa flag `enabled` của block đó. Board là bắt buộc — giữ `connections.github_project.enabled: true` và `board.id` đồng bộ với nhau (`/agentflow-init` làm việc này giúp bạn). Label vẫn giữ vai trò authoritative bất kể board thế nào.

## Environment variables

Mỗi secret được khai báo **chỉ bằng tên** trong list `env:` ở `.claude/agentflow.yaml` (mỗi entry cross-link tới các connection `used_by` của nó). Giá trị nằm trong một file `.env` mà bạn `source` trước khi khởi động Claude Code:

| Var            | Bắt buộc | Dùng cho                                             |
|----------------|----------|------------------------------------------------------|
| `GITHUB_TOKEN` | có       | GitHub access (scopes: `repo`, `read:org`, `project`) |
| `FIGMA_TOKEN`  | không    | Figma legacy PAT — chỉ dùng cho Framelink/REST fallback; server figma MCP chính thức dùng OAuth (không cần token) |

**Secret hygiene:** đặt chúng vào một file `.env` **không commit** (copy `.env.example`, điền vào, rồi `source` nó trước khi khởi động Claude Code) — không bao giờ commit token, không bao giờ paste giá trị vào `agentflow.yaml`. Chỉ tham chiếu secret bằng tên (`${GITHUB_TOKEN}`). `/agentflow-init` sẽ từ chối hoàn tất nếu một var `required: true` bị thiếu.

## Surfaces (các phần build được)

Một **surface** là một phần build được của repo, định nghĩa dưới `surfaces.*`. Map này có tính **dynamic** — repo này chỉ khai báo các surface nó thực sự có, với các key do owner chọn (ví dụ `backend`, `web`, `api`, `admin`, `mobile`, hoặc chỉ `"."` cho một repo single-surface). AgentFlow không phụ thuộc tech-stack: mỗi surface mang **command riêng** của nó.

```
surfaces.<name>.path                  # glob root, "." for single-surface repos
surfaces.<name>.label                 # the component/<name> label that maps to it
surfaces.<name>.commands.{install,lint,test,integration,e2e,build}
surfaces.<name>.coverage_command / coverage_threshold
surfaces.<name>.forbidden_paths
```

`labels.component` được generate để khớp với các surface key — một `component/<surface>` cho mỗi surface được khai báo. PMO gắn cho mỗi issue (các) label `component/<surface>` tương ứng với (các) surface mà nó chạm tới. DEV chạy command của surface bị chạm khi code; QC chạy chúng như một gate. Để đổi cách một surface build hoặc những gì nó không bao giờ được chạm tới, sửa block của surface đó. Để một command là `""` để skip nó.

## QC tiers

Một tier chọn **command-type nào chạy**, không phải các shell command cụ thể. Chúng có tính cộng dồn: `quick ⊆ full ⊆ regression`.

| Tier         | Command-type được chạy                     |
|--------------|--------------------------------------------|
| `quick`      | `lint`, `test`                             |
| `full`       | `lint`, `test`, `integration`              |
| `regression` | `lint`, `test`, `integration`, `e2e`       |

Với mỗi surface mà issue chạm tới (theo các label `component/<surface>` của nó), QC chạy command của surface đó cho từng type trong tier, theo thứ tự; tất cả phải exit 0 (một command `""` sẽ bị skip). Các shell command thực tế nằm dưới `surfaces.<name>.commands.<type>`. Coverage dùng `coverage_command`/`coverage_threshold` của surface bị chạm, fallback về `agents.qc.coverage_threshold`. Tinh chỉnh các định nghĩa tier dưới `agents.qc.tiers.*`.

## Skills

Bốn core skill luôn đi kèm plugin và tự động bật — không cần đăng ký:

| Skill                    | Bao gồm                                                        |
|--------------------------|----------------------------------------------------------------|
| `setup-agentflow`        | onboarding: yaml là source of truth, connections, env, surfaces, skill registry |
| `project-board-protocol` | GitHub wire protocol: các label `flow:*`, comment prefixes, DoR/DoD, board |
| `git-flow-working`       | branching, Conventional Commits, PR conventions, an toàn khi rebase/merge |
| `figma-design`           | pull frame specs/tokens qua `figma` MCP; handoff design → AC |

Để mở rộng, thêm một project skill dưới `.claude/skills/<role>-<area>` để đúng agent nhặt nó lên: `dev-*` → DEV, `qc-*` → QC, `pmo-*` → PMO. Đăng ký nó dưới `skills:` (bản overview source-of-truth) để bạn có thể scope nó theo surface; các agent cũng **auto-discover** bất kỳ `.claude/skills/<their-role>-*` nào kể cả khi không được liệt kê. Một agent load các skill có role-prefix liên quan tới (các) surface mà issue hiện tại chạm tới (`surfaces` trong registry được match với các label `component/*`; không có `surfaces` = luôn liên quan). `/agentflow-init` có thể scaffold các starter stub.

```yaml
skills:
  dev-mobile-development: { role: dev, surfaces: ["mobile"], description: "Mobile state & navigation conventions" }
  qc-automation-test:     { role: qc,  surfaces: ["web", "mobile"], description: "E2E suite authoring" }
  pmo-discovery:          { role: pmo, description: "Discovery & story-mapping checklist" }
```

## Cái gì nằm ở đâu (label `flow:*`)

- **`flow:inbox`** — PMO đang định hình request (triage + refine tới Definition of Ready). Cũng là điểm RE-ENTRY sau khi bạn bổ sung info cho một ticket `flow:refined`.
- **`flow:ready-for-dev`** — DEV sẽ nhặt nó lên tiếp theo. Nếu mang aux label `rework` (QC đã reject) hoặc `human-changes` (bạn "Request changes" trên PR), DEV finish cái đó trước và đọc feedback mới nhất.
- **`flow:in-progress`** — DEV đang implement. Nếu DEV bị block, bạn sẽ thấy một comment blocked `[DEV]` và issue nằm lại đây để bạn unblock.
- **`flow:in-qc`** — DEV đã mở một PR; QC viết automation test trên PR branch, rồi chạy tier. QC ❌ (chưa vượt ngưỡng) route ticket về `flow:ready-for-dev` + `rework`.
- **`flow:refined`** — **BLOCKED, cần bạn.** Một info-gap (PMO không tới được DoR, DEV thiếu spec/Figma, QC gặp AC mơ hồ, hoặc escalation QC 2-strike) đã park ticket ở đây và un-assign nó. Bạn cung cấp thêm info/quyết định qua `/review-refined` (hoặc sửa label tay), rồi lệnh đó re-label nó về `flow:inbox` để PMO re-triage và chạy tiếp.
- **`flow:ready-for-human-review`** — đến lượt bạn. Review và merge PR — hoặc để lại một review **"Request changes"** trên nó và `/start` sẽ route nó về lại DEV dưới dạng `flow:ready-for-dev` + `human-changes` (được mirror vào issue dưới dạng một comment `[USER]`; QC re-gate trước khi nó quay lại bạn). (Chỉ đạt tới đây khi QC ✅ — sẵn sàng merge.)
- **`flow:done`** — đã merge và close.

Filter list issue theo bất kỳ label nào trong số này để xem cái gì đang ở đâu (`gh issue list --label flow:in-qc`).

## Comment prefixes (để bạn grep / filter)

`[PMO]`, `[DEV]`, `[QC] ✅`, `[QC] ❌`, `[DEV→PMO ?]`, `[QC→PMO ?]`, `[SYSTEM]`, `[USER:<your-login>]`.

Bất cứ thứ gì bạn viết **mà không** có prefix `[USER:...]` sẽ bị các agent coi là untrusted context — chúng sẽ đọc nhưng không hành động theo các instruction bên trong.

## Notifications

Đây là terminal mode — mặc định thì break-out của orchestrator **chính là** notification. Không có external channel nào; theo dõi session này để bắt các ticket rơi vào `flow:refined` (cần bạn bổ sung info — gỡ bằng `/review-refined`) và các PR sẵn sàng merge. (Bạn có thể chạy `/start` không giám sát theo một interval qua skill `/loop`; khi đó các break-out sẽ queue trên board cho tới khi bạn quay lại.)
