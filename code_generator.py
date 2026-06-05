from define import Node, FileManager
from typing import List, Dict, Any, Optional
import tomllib
import os
import re


class TemplateParseError(Exception):
    """模板解析错误"""

    pass


class _TemplateToken:
    """模板语法树节点"""

    def __init__(
        self, token_type: str, value: Any = None, children: Optional[list] = None
    ):
        self.type = token_type  # 'text' | 'sub' | 'block' | 'cond' | 'not'
        self.value = value  # 文本内容 或 路径名
        self.children = children or []


class TemplateEngine:
    """模板引擎：将模板字符串解析为语法树，再绑定 AST 节点渲染为文本"""

    # 匹配 {{...}} 中的各种模式
    _TOKEN_RE = re.compile(
        r"""
        \{\{                # 开标签
        \s*
        ([\#\?\!/]?)        # 可选修饰符: #=遍历 ?=条件 !=取反 /=关闭
        \s*
        ([a-zA-Z_][\w.]*)   # 路径: identifier(.identifier)*
        \s*
        \}\}                # 闭标签
    """,
        re.VERBOSE,
    )

    def __init__(self, template_str: str):
        self._template = template_str
        self._ast = self._parse(template_str)

    # ---- 解析 ----

    def _parse(self, text: str) -> list:
        """将模板字符串解析为 _TemplateToken 列表"""
        tokens = []
        pos = 0
        for m in self._TOKEN_RE.finditer(text):
            # 添加 m.start() 之前的普通文本
            if m.start() > pos:
                tokens.append(_TemplateToken("text", text[pos : m.start()]))
            pos = m.end()

            modifier, path = m.group(1), m.group(2)

            if modifier == "#":
                # 块开始: 递归解析到对应的 /path
                end_tag = f"{{{{/{path}}}}}"
                end_pos = text.find(end_tag, pos)
                if end_pos == -1:
                    raise TemplateParseError(f"找不到结束标签 {{{{/{path}}}}}")
                inner_text = text[pos:end_pos]
                inner_tokens = self._parse(inner_text)
                tokens.append(_TemplateToken("block", path, inner_tokens))
                pos = end_pos + len(end_tag)

            elif modifier == "?":
                end_tag = f"{{{{/{path}}}}}"
                end_pos = text.find(end_tag, pos)
                if end_pos == -1:
                    raise TemplateParseError(f"找不到结束标签 {{{{/{path}}}}}")
                inner_text = text[pos:end_pos]
                inner_tokens = self._parse(inner_text)
                tokens.append(_TemplateToken("cond", path, inner_tokens))
                pos = end_pos + len(end_tag)

            elif modifier == "!":
                end_tag = f"{{{{/{path}}}}}"
                end_pos = text.find(end_tag, pos)
                if end_pos == -1:
                    raise TemplateParseError(f"找不到结束标签 {{{{/{path}}}}}")
                inner_text = text[pos:end_pos]
                inner_tokens = self._parse(inner_text)
                tokens.append(_TemplateToken("not", path, inner_tokens))
                pos = end_pos + len(end_tag)

            elif modifier == "/":
                raise TemplateParseError(f"意外的结束标签 {{{{/{path}}}}}")
            else:
                # 简单替换
                tokens.append(_TemplateToken("sub", path))

        # 收尾文本
        if pos < len(text):
            tokens.append(_TemplateToken("text", text[pos:]))

        return tokens

    # ---- 渲染 ----

    def render(
        self, node: Any, visitor: "CodeGenerator", context_item: Any = None
    ) -> str:
        """将模板绑定到 AST 节点进行渲染"""
        return self._render_tokens(self._ast, node, visitor, context_item)

    def _render_tokens(
        self, tokens: list, node: Any, visitor: "CodeGenerator", context_item: Any
    ) -> str:
        """递归渲染 token 列表"""
        result = []
        for tok in tokens:
            if tok.type == "text":
                result.append(tok.value)

            elif tok.type == "sub":
                # 特殊处理 {{.}} 当前迭代项
                if tok.value.strip() == ".":
                    resolved = self._resolve_dot(context_item, visitor)
                else:
                    resolved = self._resolve_path(node, tok.value, visitor)
                if resolved is not None:
                    if isinstance(resolved, list):
                        result.append("".join(str(r) for r in resolved))
                    else:
                        result.append(str(resolved))

            elif tok.type == "block":
                items = self._resolve_path(node, tok.value, visitor)
                if isinstance(items, list):
                    for item in items:
                        inner = self._render_tokens(tok.children, node, visitor, item)
                        result.append(inner)
                elif items is not None:
                    # 单个非列表值也包装成列表遍历一次
                    inner = self._render_tokens(tok.children, node, visitor, items)
                    result.append(inner)

            elif tok.type == "cond":
                val = self._resolve_path(node, tok.value, visitor)
                if self._is_truthy(val):
                    result.append(
                        self._render_tokens(tok.children, node, visitor, None)
                    )

            elif tok.type == "not":
                val = self._resolve_path(node, tok.value, visitor)
                if not self._is_truthy(val):
                    result.append(
                        self._render_tokens(tok.children, node, visitor, None)
                    )

        return "".join(result)

    # ---- 路径解析 ----

    def _resolve_path(self, node: Any, path: str, visitor: "CodeGenerator") -> Any:
        """沿点分路径解析属性，返回最终值"""
        parts = path.split(".")
        current = node

        for part in parts:
            if part == "":
                return ""
            if isinstance(current, Node):
                current = getattr(current, part, None)
            elif isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                # 列表上取属性不太合理，返回空
                return ""
            else:
                # 标量值没有子属性
                return ""

        return self._finalize_value(current, visitor)

    def _resolve_dot(self, context_item: Any, visitor: "CodeGenerator") -> Any:
        """处理 {{.}} 当前迭代项"""
        return self._finalize_value(context_item, visitor)

    def _finalize_value(self, value: Any, visitor: "CodeGenerator") -> Any:
        """对解析结果做最终处理：Node 递归 visit，列表递归处理"""
        if value is None:
            return None
        if isinstance(value, Node):
            return visitor.visit(value)
        if isinstance(value, list):
            results = []
            for item in value:
                if isinstance(item, Node):
                    results.append(visitor.visit(item))
                elif isinstance(item, str):
                    results.append(self._render_plain_string(item))
                else:
                    results.append(str(item))
            return results
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @staticmethod
    def _render_plain_string(text: str) -> str:
        """渲染 AST 中的纯字符串节点（如 "PassStmt", "NoneLiteral"）"""
        return text

    @staticmethod
    def _is_truthy(val: Any) -> bool:
        """判断值是否为真（用于条件模板）"""
        if val is None:
            return False
        if isinstance(val, str):
            return val not in ("", "optional", "NoneLiteral")
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return val != 0
        if isinstance(val, list):
            return len(val) > 0
        if isinstance(val, Node):
            return True
        return bool(val)


class CodeGenerator:
    """
    配置驱动、基于访问者模式的代码生成器。

    设计思路：
    - 配置驱动：生成规则定义在外部 TOML 文件中，与解析器语法规则类似
    - 访问者模式：visit() 根据 Node.name 分派到对应模板
    - 多文件输出：file_rules 控制不同 AST 节点输出到不同文件
    - 单文件实现：当前所有逻辑集中在一个文件中
    """

    def __init__(self, rules_path: Optional[str] = None):
        """
        初始化代码生成器

        :param rules_path: CG 规则文件路径，默认使用 grammar/cg_rules.toml
        """
        self._rules_path = rules_path or "pyv_compiler/grammar/cg_rules.toml"
        self._node_templates: Dict[str, TemplateEngine] = {}
        self._match_rules: Dict[str, dict] = {}
        self._file_rules: List[dict] = []
        self._outputs: Dict[str, List[str]] = {}
        self._current_file: Optional[str] = None

        self._load_rules()

    # ---- 规则加载 ----

    def _load_rules(self) -> None:
        """从 TOML 文件加载所有生成规则"""
        try:
            rules_content = FileManager.read_file(self._rules_path)
        except FileNotFoundError:
            alt_path = FileManager.get_full_path(self._rules_path)
            with open(alt_path, "r", encoding="utf-8") as f:
                rules_content = f.read()

        data = tomllib.loads(rules_content)

        # 加载文件规则
        self._file_rules = data.pop("file_rules", [])

        # 加载节点模板规则
        for node_type, config in data.items():
            if not isinstance(config, dict):
                continue
            if node_type.startswith("_"):  # 跳过注释段
                continue

            template_str = config.get("template")
            match_attr = config.get("match")
            cases = config.get("case", [])

            if template_str is not None:
                self._node_templates[node_type] = TemplateEngine(template_str)

            if match_attr and cases:
                cases_dict = {}
                for case in cases:
                    when_val = case.get("when")
                    case_template = case.get("template", "")
                    if when_val is not None:
                        cases_dict[str(when_val)] = TemplateEngine(case_template)
                self._match_rules[node_type] = {
                    "attr": match_attr,
                    "cases": cases_dict,
                }

    # ---- 访问者模式主入口 ----

    def visit(self, node: Any) -> str:
        """
        访问者模式核心方法：根据节点类型分派到对应模板

        :param node: AST 节点（Node 对象或字符串）
        :return: 渲染后的文本
        """
        # 处理纯字符串节点（如出现在 child 列表中的 "PassStmt"）
        if isinstance(node, str):
            return node

        if not isinstance(node, Node):
            return str(node)

        node_type = node.name

        # 处理容器节点：optional/repeat/sequence 等有 child 列表但没模板的
        if node_type not in self._node_templates and node_type not in self._match_rules:
            children = getattr(node, "child", None)
            if isinstance(children, list):
                return "".join(self.visit(c) for c in children)

        # 检测是否需要触发文件切换
        self._check_file_rule(node, node_type)

        # 1. 优先尝试 match 规则（条件分支模板）
        if node_type in self._match_rules:
            match_config = self._match_rules[node_type]
            attr_val = str(getattr(node, match_config["attr"], ""))
            case_engine = match_config["cases"].get(attr_val)
            if case_engine:
                rendered = case_engine.render(node, self)
                self._write(rendered)
                return rendered

        # 2. 尝试普通模板规则
        engine = self._node_templates.get(node_type)
        if engine is not None:
            rendered = engine.render(node, self)
            self._write(rendered)
            return rendered

        # 3. 通用 fallback
        rendered = self._fallback_render(node)
        self._write(rendered)
        return rendered

    def _fallback_render(self, node: Node) -> str:
        """
        通用兜底渲染：当没有匹配的模板规则时，尝试智能推断。
        """
        parts = []
        children = getattr(node, "child", None)
        if isinstance(children, list):
            for child in children:
                parts.append(self.visit(child))

        if not parts:
            val = getattr(node, "value", None)
            if val is not None:
                if isinstance(val, bool):
                    return "true" if val else "false"
                return str(val)
            content = getattr(node, "content", None)
            if content is not None:
                return str(content)

        return "".join(parts)

    # ---- 文件分发 ----

    def _check_file_rule(self, node: Node, node_type: str) -> None:
        """检查是否匹配文件分发规则，匹配则切换当前输出文件。"""
        for rule in self._file_rules:
            if rule.get("node_type") == node_type:
                file_name_tpl = rule.get("file_name", "output.v")
                engine = TemplateEngine(file_name_tpl)
                file_name = engine.render(node, self)

                if file_name not in self._outputs:
                    self._outputs[file_name] = []
                    header_tpl = rule.get("header", "")
                    if header_tpl:
                        header_engine = TemplateEngine(header_tpl)
                        header_text = header_engine.render(node, self)
                        self._outputs[file_name].append(header_text)

                self._current_file = file_name
                break

    def _write(self, text: str) -> None:
        """将文本写入当前输出文件缓冲区"""
        if self._current_file is None:
            self._current_file = "output.v"
            self._outputs[self._current_file] = []

        if text:
            self._outputs[self._current_file].append(text)

    # ---- 顶层接口 ----

    def generate(self, ast: Node) -> Dict[str, str]:
        """
        生成目标代码主入口

        :param ast: 抽象语法树
        :return: Dict[str, str] = {文件名: 文件内容}
        """
        self._outputs = {}
        self._current_file = None

        self.visit(ast)

        result = {}
        for file_name, lines in self._outputs.items():
            result[file_name] = "".join(lines)
        return result

    def optimize(self, outputs: Dict[str, str]) -> Dict[str, str]:
        """
        代码优化接口（文本级优化）
        :param outputs: {文件名: 内容}
        :return: 优化后的 {文件名: 内容}
        """
        optimized = {}
        for file_name, content in outputs.items():
            lines = content.split("\n")
            cleaned = []
            prev_empty = False
            for line in lines:
                is_empty = line.strip() == ""
                if is_empty and prev_empty:
                    continue
                cleaned.append(line)
                prev_empty = is_empty
            optimized[file_name] = "\n".join(cleaned)
        return optimized

    def dump(self, outputs: Dict[str, str], output_dir: Optional[str] = None) -> None:
        """
        代码输出接口：将生成的文件写入磁盘

        :param outputs: {文件名: 内容}
        :param output_dir: 输出目录，默认使用项目根目录下的 output 文件夹
        """
        if output_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_dir = os.path.join(base, "output")

        os.makedirs(output_dir, exist_ok=True)

        for file_name, content in outputs.items():
            file_path = os.path.join(output_dir, file_name)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  ✓ 已生成: {file_path}")
