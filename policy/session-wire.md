# 会话协作（wire）— 多 agent 会话在同一仓库的交接制度

> 适用：**多个 DSH 会话**在同一工作区（`E:\project\tpc_compiler`）协作时的消息交接。
> 不适用于 tpc 产品本身——它是协作层，不改语言/引擎行为。
> 机器执行者：`_drafts/session/tools/wirex.py`（前门）+ `_drafts/session/tools/wire.py`（校验器，vendored）。
> 记录落在 `.scratch/wire/`（**不进库、不受门禁**）；教义（本文件）进库、受评审。

## 为什么记录不进库

门禁与记录互相冲突：**消息一旦发出就不再改写**（见下方纪律 1），而任何"检查记录格式"的
门禁迟早会要求改写历史记录。所以只让**教义**进库；记录树 `.scratch/wire/` 已在 `.gitignore` 内。
同理，`wire.py who|quorum` 硬编码 `<repo>/.scratch/wire`，记录必须放在那里工具才认。

## 组成

| 路径 | 作用 |
|---|---|
| `.scratch/wire/<thread>/NNN-<from>-<id6>.wire` | 消息树；一条消息一个文件，字典序即时间序 |
| `_drafts/session/tools/wire.py` | 校验器/生成器，**逐仓 vendored**（与上游同版本；校验器必须匹配自己树里的消息） |
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

## 已知缺口（继承自上游 WIRE.md，勿当成已解决）

- 没有强制传输层：校验器只管内容，不保证送达/被读。
- `ttl` 过期不会自动执行默认值。
- "谁**应当**回答"由花名册解决了一半；下发任务时仍须在消息里写清 `by=`。
