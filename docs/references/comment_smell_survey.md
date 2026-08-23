# 注释"AI 味"检测：前人方案调研

> 目的：为 tpc 注释味道审查（`docs/comment_smell_rubric.md`）选型提供依据。
> 调研日期：2026-08-23（仓库首次做注释味道审查）。
> 类别：references/（事实参考）。

## 结论先行

前人有五类做法，按"检测 vs 预防"与"启发式 vs 学习式"分布：

| 方案 | 代表 | 原理 | 优点 | 缺点 |
|------|------|------|------|------|
| 词表黑名单 | [scanaislop](https://scanaislop.com/patterns/)、[llm-witch-hunt](https://www.npmjs.com/package/llm-witch-hunt) | 命中 AI 套话词表 | 便宜、确定、可复现 | 无上下文、误报高、易规避 |
| 信息密度测量 | [signal-oss](https://github.com/Divyesh-5981/signal-oss) | 内容量与废话量的比值 | 模型无关（打症状不打风格） | 特征工程主观，仍属启发式 |
| 风格计量学/ML | [论文 2409.01382](https://huggingface.co/buckets/huggingchat/papers-content/tree/2409/2409.01382.md)、[Claude 3 Haiku 研究](https://www.semanticscholar.org/paper/Automatic-Detection-of-LLM-generated-Code%3A-A-Case-3-Rahman-Khatoonabadi/a4bf4c490fbba21fc8518a1bf3fb6e625b963363)、[UNC 注释自解释研究](https://our.unc.edu/abstract/jones-the-linguistic-signature-of-novice-programmers-quantifying-self-explanation-in-code-comments) | 词法/风格特征训分类器 | 实验室检出率高 | 检测分随模型演化漂移、需标注数据、黑盒 |
| 行为约束（预防） | [slopless](https://github.com/BioInfo/slopless)（CLAUDE.md 反 AI slop 写作系统）、[claude skill 形式先例](https://raw.githubusercontent.com/ruvnet/ruvector/85e475a45335242dc9535d7efc75dd1bc5f6ec7d/.claude/skills/github-code-review/SKILL.md) | 生成源头立规矩 | 便宜、源头塑形 | 只约束服从者、需维护 |
| 评审 rubric + LLM 判定 | [m7madash/AI-Code-Review-Agent](https://github.com/m7madash/AI-Code-Review-Agent) | 维度化评审 + 证据 + 人确认 | 有语境判断，超越关键词 | LLM 判定有偏、成本、prompt 质量敏感 |

## 逐个看

### 1. 词表黑名单（scanaislop / llm-witch-hunt）

- scanaislop 维护公开的 "AI slop patterns" 清单（[patterns 页](https://scanaislop.com/patterns/) 与 [top-10 coding mistakes](https://scanaislop.com/blog/top-ai-coding-mistakes/)），另有一篇完整的[检测指南](https://scanaislop.com/blog/ai-slop-detection-complete-guide/)。
- npm 包 llm-witch-hunt 同样走词表匹配路线。
- 启示：词表只适合当"第一层粗筛"。误报案例（§6）说明脱离上下文的关键词命中不可信；我们的 rubric 用词表启发维度 3（AI 套话），但不作为判定依据。

### 2. 信息密度测量（signal-oss）

- [signal-oss](https://github.com/Divyesh-5981/signal-oss)：自称 "zero-tolerance slop scanner"，通过测量**信息密度**检测"空洞的 AI 生成评审产物"，含 GitHub Action 与实时面板。
- 配套文章 [Measuring Thought, Not Authorship](https://www.raptors.dev/blog/measuring-thought-not-authorship-ai-slop-scan-hackathon) 点题：量"思想"，不量"作者"。
- 启示：与 tpc 最合拍的一条思路——"空话 vs 信息"的比值是模型无关的。rubric 维度 1（冗余复述）与维度 2（空话）即其操作化。

### 3. 风格计量学 / ML 分类（学术路线）

- [Automatic Detection of LLM-generated Code（2409.01382）](https://huggingface.co/buckets/huggingchat/papers-content/tree/2409/2409.01382.md)：函数/类粒度、跨当代模型对比的检测研究；作者自述"具体模型的检测分随模型演化会漂移"。
- [Claude 3 Haiku 案例研究](https://www.semanticscholar.org/paper/Automatic-Detection-of-LLM-generated-Code%3A-A-Case-3-Rahman-Khatoonabadi/a4bf4c490fbba21fc8518a1bf3fb6e625b963363)（Rahman & Khatoonabadi）。
- [UNC：新手程序员的语言特征——量化代码注释中的自解释](https://our.unc.edu/abstract/jones-the-linguistic-signature-of-novice-programmers-quantifying-self-explanation-in-code-comments)。
- 启示：学界证实"注释文本确实携带风格指纹"，但也证实指纹会漂移。对"味道审查"（主观阅读体验）而言，上分类器是杀鸡用牛刀——取它"注释文本可被量化分析"的结论，不取黑盒判定。

### 4. 行为约束规则（预防路线）

- [slopless](https://github.com/BioInfo/slopless)：production-tested 的 CLAUDE.md + rules，"anti-AI-slop writing system"——在生成源头立写作规矩（禁词、语气、信息密度要求）。
- claude skill 形式先例：[ruvnet/ruvector 的 github-code-review skill](https://raw.githubusercontent.com/ruvnet/ruvector/85e475a45335242dc9535d7efc75dd1bc5f6ec7d/.claude/skills/github-code-review/SKILL.md)（SKILL.md 内嵌评审 rubric）。
- 启示：预防比检测便宜，但只对"尚未写的注释"有效。tpc 注释已存在，预防路线只能用于未来；本次审查取它的词表与语气规则做维度素材。

### 5. 评审 rubric + LLM 判定

- [m7madash/AI-Code-Review-Agent](https://github.com/m7madash/AI-Code-Review-Agent)：通用 AI code review agent 的形态参考。
- 启示：评审类工具的共同形态是"维度化 rubric + 证据要求 + 人最终确认"——正是本仓库采用的形态。

### 6. 误报警示（诚实边界）

- [Labeled AI Slop Despite a Correct Fix](https://1devtool.com/blog/ai-slop-label-correctness)：一个"正确修复"被工具误标为 AI slop 的案例分析——任何自动判定都存在误报，误报会伤害产出方信任。
- 结论：我们的审查只做"味道/阅读体验"的定性描述与证据列举，**不做作者判定、不自动改码**；rubric 明确"AI 味 ≠ 错误"，拿不准的标"边界"。

## 我们的取舍

- **不取**：纯词表（无上下文）、ML 分类器（漂移 + 黑盒）、预防规则（时机已过）。
- **取**：信息密度/空话检测（模型无关，打症状）、rubric + 证据 + 人确认（有语境）、"注释文本可量化"（确认注释值得审）。
- **自加**：维度 6"缺失 why/决策痕迹"——tpc 独有的视角：本仓库文档体系（`docs/README.md` 读者维度）明确重视"为什么/历史/权衡"，注释里这些痕迹的密度就是"人味"的可操作定义。
