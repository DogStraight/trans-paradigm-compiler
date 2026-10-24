# 会话协作（wire）— 多 agent 会话在同一仓库的交接制度

> 适用：**多个 DSH 会话**在同一工作区（`E:\project\tpc_compiler`）协作时的消息交接。
> 不适用于 tpc 产品本身——它是协作层，不改语言/引擎行为。
> 机器执行者：`_drafts/session/tools/wirex.py`（前门）+ `_drafts/session/wire.py`（校验器，vendored）。
> 记录落在 `.scratch/wire/`（**不进库、不受门禁**）；教义（本文件）进库、受评审。

## 为什么记录不进库

门禁与记录互相冲突：**消息一旦发出就不再改写**（见下方纪律 1），而任何"检查记录格式"的
门禁迟早会要求改写历史记录。所以只让**教义**进库；记录树 `.scratch/wire/` 已在 `.gitignore` 内。
同理，`wire.py who|quorum` 硬编码 `<repo>/.scratch/wire`，记录必须放在那里工具才认。

## 组成

| 路径 | 作用 |
|---|---|
| `.scratch/wire/<thread>/NNN-<from>-<id6>.wire` | 消息树；一条消息一个文件，字典序即时间序 |
| `_drafts/session/wire.py` | 校验器/生成器，**逐仓 vendored**（与上游同版本；校验器必须匹配自己树里的消息）。位置受「vendor 深度契约」约束 |
| `_drafts/session/tools/wirex.py` | tpc 前门：花名册解析 + 版本自检 + 委托校验器 |
| `_drafts/session/roster.toml` | 花名册：`label -> session id -> role`（**地址只能来自这里**） |
| `_drafts/session/roster.py` | 从 DSH 会话库生成本工作区的会话清单（查 id 用） |

## 寻址：label 不是地址

- `--to` 必须是**完整 session id**，或 `roster.toml` 里登记的 label。
- label 解析不到 → `E-NO-SESSION-BEHIND-LABEL`（退出码 2），**拒写**，不静默变成坏地址。
- 这是实测过的失败：一个没有 session id 支撑的名字，写出去谁也不会收到。

```powershell
python _drafts/session/tools/wirex.py who        # label / id / role / turns / running
python _drafts/session/roster.py                 # 扫会话库，补 roster
```

## 最小闭合集（够用即可，不预铺）

**六个 sigil**：`@` 证据 · `>` 任务 · `<` 回执 · `-` 撤回 · `+` 状态 · `?` 提问。
暂缓：`= # $ ~`（契约/度量/花费/延后）与 `digest/quorum`——它们需要锚机制，等真需要再加。

**五个子命令**：`new` `check` `thread` `mailbox` `who`。

**从第一天就守住**：一条消息一个 `#W1` 头；每个 `>` 必须带 `^check`；`silent=hold` 必须带
`then=`；单原子文本 ≤160 字符；单消息 ≤20 原子。

## 消息形状

```
#W1 from=<label> to=<session-id> thread=<thread> session=<我的 session id> re=<回的键>
@ evidence.x = 指向证据，不复述证据 ~path:policy/session-wire.md
> task.y by=<id> rev=y silent=hold then=<我先做什么> = 请对方做什么 ~path:... ^python -m pytest -q tests/...
```

- 键是小写点分标识符；`;` 开头是注释；`~引用`/`^命令` 各至多一个，`^` 必须写在行尾。
- 文本里要写字面的 `^` / `~` 时转义成 `\^` / `\~`。

## 跨仓线程：引用要用 `~ext:`

消息留在**线程所在仓库**的 `.scratch/wire/<thread>/`（对方只读自己的树）。因此跨仓线程里：

- 引用**本仓**文件必须写 `~ext:<绝对路径>`——`~path:` 会被按**线程所在仓库**解析，指向不存在的
  路径会报 `E-REF-MISSING`（实测：首次用 `~path:` 发往 fuzz 仓，6 条全红）。
- `~ext:` 按设计**不校验**（外部世界的引用不假装能校验），所以跨仓时要在正文里写清路径。

## 投递与回执（复用机器级技能，不自己造传输）

```powershell
$S = "C:\Users\micro\.dsh\skills\dsh-session-messaging\scripts"
python $S\send.py --session <对方 id> --file <正文文件>     # 投递（桥每 2s 轮询 spool）
python $S\read_reply.py --session <对方 id> --after-turn <N> --wait 300
```

- 正文**先自报身份与来路**（桥把消息当"用户发言"投，对方不知道你是谁）。
- 回程目标若是主控会话，走 `mailbox.json` 重定向，避免占用用户通道。
- **送达 ≠ 被消费**：判据是对方 `inbox["next-turn"]` 清空且 `lastTurn` 增长。

## 纪律（每条都有实测代价）

1. **绝不改写已发出的消息**；纠正/关闭用**新序号**回复。原地改写会抹掉对方的审计痕迹。
2. **红色断言发送时重测**（`check --run-checks`）：先检查后发送会让红过期，对方读到的是旧红。
3. **按 session id 寻址**，不按自造名字；label 只是花名册里的别名。
4. **同源分叉**：分叉方必须声明 `forked_from`，且**不继承父会话的 `session=`**；
   父会话的未决义务不属于分叉方；度量原子附 git rev（分叉工作树会漂移）。
5. **意见预算**：无锚也无判定的原子记作意见，≤2 条或 ≤25%。
6. **一条消息最多一条门铃，且只在 `check` 绿之后响**。门铃（`WIRE <文件> -> <路径>`）
   只说"记录在哪"，不带内容。`wire.py new` 原本先响后验——实测 2026-10-24：一条红草稿响了、
   被前门拒收，改好重发又响一次，一条消息两个门铃，其中一个指向已被移走的文件。
   现在前门恒用 `--no-notify`，绿了才由前门发门铃（投递仍走机器技能 `send.py`）。
   同时每次发铃顺手 `prune_spool(180)`：spool 只追加不删、桥按水位去重，重启会把旧铃重放
   （实测积了 16 条旧铃，其中 4 条被当成新消息再投一遍）。
7. **`new` 已 fail-closed**：前门写完立即 `check`，红则移入 `<thread>/.rejected/` 并退出 3。
   `new` 的静默成功**不是**合格证明（实测：2026-10-24 review session 报 `new` 对非法原子 rc=0，
   一条缺 `rev=`/`silent=` 的 ASK 就这样躺在树里冒充记录）。vendored 校验器因此仍逐字节不变，
   这条策略只活在前门。
8. **不必逐条回**：只对**阻塞义务**（`?`/`>` 的 key）和**新事实**回；同一内容被反复讨论时，
   沉默是正确行为——要收口就发**一条** `-`（撤回）或 `+`（收敛），不逐条对账、不复述已答过的话。
   实测代价：一次教学往来 14 条，同一个问题被问了 4 次（其中 2 次纯格式自纠），噪声盖过内容。

## 已知缺口（继承自上游 WIRE.md，勿当成已解决）

- 没有强制传输层：校验器只管内容，不保证送达/被读。
- `ttl` 过期不会自动执行默认值。
- "谁**应当**回答"由花名册解决了一半；下发任务时仍须在消息里写清 `by=`。

## 谁该用它：审计循环里的三类外部问题

审计制度要求「判断不可外包」，但**同一个人不能既提结论又当证伪者**。三类问题只能跨会话问：

| 问题 | 找谁 | 自己为什么答不了 |
|---|---|---|
| 我这个探针代理的**还是**当前那条性质吗（`invalidated_if` 发生了吗） | 无利害关系的另一个会话 | 自证：作者对自己写的探针总是宽容 |
| 另一仓/另一会话的实测事实（上游行为、用户口径） | 该仓/该会话 | 本仓没有那份事实，只有它的转述 |
| 制度要不要改（决策权归属） | 作者 | 授权不在我手里 |

**不该用它的地方**：同步等待（wire 没有阻塞原语，`read_reply --wait` 不是锁）；搬大段正文
（写文件 + `~path:`/`~ext:`，消息里只放判定句）；闲聊。

### 提问模板（四行够用）

```
#W1 from=<我> to=<完整 session id> thread=t.<主题> session=<我的 id> re=<键>
? q.<键> by=<我> = 一句话、一次一个、必须能用一个事实回答 ~path:<证据文件>
+ ask.<键> = 我拿这个答案去决定什么（对方据此判断该给多细）
> by=<我> rev=n silent=hold then=<我先做什么> = 回答请指证据路径，不接受散文结论
```

**判据**：好的跨会话问题，对方答完你就能**删掉一个探针**或**冻结/解冻一个维度**；
答完还要你再解释一遍的，是没问清。

## vendor 深度契约（实测代价）

`wire.py` 用 `REPO_ROOT = Path(__file__).resolve().parents[2]` 认仓库根，而 `check` 的
`~path:` 一律按**它**解析——`--repo` 只喂给 `thread/who/quorum`，**不传给** `ref_finding`。
所以 vendored 副本必须落在**仓库根下恰好两级**：本仓因此是 `_drafts/session/wire.py`。
曾下沉到 `_drafts/session/tools/wire.py`，结果 `~path:README.md` 全红——**红的是工具的位置，
不是引用**。改位置后同一字节（SHA256 相同）的副本立刻判绿。
