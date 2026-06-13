from define import Node, FileManager
from typing import List, Dict, Any, Optional
import tomllib
import os
import re


from err import TemplateParseError


class _TemplateToken:
    """模板语法树节点"""

    def __init__(
        self, token_type: str, value: Any = None, children: Optional[list] = None
    ):
        self.type = token_type  # 'text' | 'sub' | 'block' | 'cond' | 'not'
        self.value = value  # 文本内容 或 路径名
        self.children = children or []


class TemplateEngine:
    """模板引擎：将模板字符串解析为语法树，再绑定 AST 节点渲染为文本，支持 @first/@last/@index 迭代控制"""

    _TOKEN_RE = re.compile(
        r"""
        \{\{                # 开标签
        \s*
        ([\#\?\!/]?)        # 可选修饰符: #=遍历 ?=条件 !=取反 /=关闭
        \s*
        ([a-zA-Z_@][\w.]*|\.)   # 路径: identifier(.identifier)* 或 .，支持 @first/@last
        \s*
        \}\}                # 闭标签
    """,
        re.VERBOSE,
    )

    class _IterItem:
        """包装列表迭代元素，提供 @first/@last/@index 元数据"""

        def __init__(self, value: Any, index: int, first: bool, last: bool):
            self.value = value
            self.index = index
            self.first = first
            self.last = last

    def __init__(self, template_str: str):
        self._template = template_str
        self._ast = self._parse(template_str)

    # ---- 解析 ----
    def _parse(self, text: str) -> list:
        tokens = []
        pos = 0
        while True:
            m = self._TOKEN_RE.search(text, pos)
            if m is None:
                break
            if m.start() > pos:
                tokens.append(_TemplateToken("text", text[pos : m.start()]))
            pos = m.end()

            modifier, path = m.group(1), m.group(2)

            if modifier == "#":
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
                tokens.append(_TemplateToken("sub", path))

        if pos < len(text):
            tokens.append(_TemplateToken("text", text[pos:]))
        return tokens

    # ---- 渲染 ----
    def render(
        self, node: Any, visitor: "CodeGenerator", context_item: Any = None
    ) -> str:
        return self._render_tokens(self._ast, node, visitor, context_item)

    def _render_tokens(
        self, tokens: list, node: Any, visitor: "CodeGenerator", context_item: Any
    ) -> str:
        result = []
        for tok in tokens:
            if tok.type == "text":
                result.append(tok.value)

            elif tok.type == "sub":
                if tok.value.strip() == ".":
                    resolved = self._resolve_dot(context_item, visitor)
                else:
                    resolved = self._resolve_path(
                        node, tok.value, visitor, context_item
                    )
                if resolved is not None:
                    if isinstance(resolved, list):
                        result.append("".join(str(r) for r in resolved))
                    else:
                        result.append(str(resolved))

            elif tok.type == "block":
                items = self._resolve_path(node, tok.value, visitor, context_item)
                if isinstance(items, list):
                    # 包装为 _IterItem 列表，提供 @first/@last/@index
                    wrapped = [
                        self._IterItem(v, i, i == 0, i == len(items) - 1)
                        for i, v in enumerate(items)
                    ]
                    for item in wrapped:
                        inner = self._render_tokens(tok.children, node, visitor, item)
                        result.append(inner)
                elif items is not None:
                    # 单个非列表值也包装成列表遍历一次
                    wrapped = self._IterItem(items, 0, True, True)
                    inner = self._render_tokens(tok.children, node, visitor, wrapped)
                    result.append(inner)

            elif tok.type == "cond":
                val = self._resolve_path(node, tok.value, visitor, context_item)
                if self._is_truthy(val):
                    result.append(
                        self._render_tokens(tok.children, node, visitor, context_item)
                    )

            elif tok.type == "not":
                val = self._resolve_path(node, tok.value, visitor, context_item)
                if not self._is_truthy(val):
                    result.append(
                        self._render_tokens(tok.children, node, visitor, context_item)
                    )

        return "".join(result)

    # ---- 路径解析 ----
    def _resolve_path(
        self, node: Any, path: str, visitor: "CodeGenerator", context_item: Any
    ) -> Any:
        """沿点分路径解析属性，context_item 优先于 node（用于迭代元数据）"""
        parts = path.split(".")
        # 如果路径以 @ 开头，从 context_item 解析特殊变量
        if parts[0].startswith("@"):
            if context_item is not None and isinstance(context_item, self._IterItem):
                if parts[0] == "@first":
                    return context_item.first
                if parts[0] == "@last":
                    return context_item.last
                if parts[0] == "@index":
                    return context_item.index
            return None

        # 正常路径：先从 context_item.value（如果有）开始，再回溯到 node
        current = None
        if context_item is not None and isinstance(context_item, self._IterItem):
            current = context_item.value
        else:
            current = node

        for part in parts:
            if part == "":
                return ""
            if current is None:
                return None
            if isinstance(current, Node):
                current = getattr(current, part, None)
            elif isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                # 列表上取属性不合理
                return None
            else:
                # 标量值无子属性
                return None

        return self._finalize_value(current, visitor)

    def _resolve_dot(self, context_item: Any, visitor: "CodeGenerator") -> Any:
        """处理 {{.}} 当前迭代项"""
        if context_item is None:
            return None
        if isinstance(context_item, self._IterItem):
            return self._finalize_value(context_item.value, visitor)
        return self._finalize_value(context_item, visitor)

    def _finalize_value(self, value: Any, visitor: "CodeGenerator") -> Any:
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
                elif isinstance(item, dict):
                    results.append(item)
                else:
                    results.append(str(item))
            return results
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @staticmethod
    def _render_plain_string(text: str) -> str:
        return text

    @staticmethod
    def _is_truthy(val: Any) -> bool:
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
    """配置驱动代码生成器"""

    def __init__(
        self, rules_path: Optional[str] = None, rules_dir: Optional[str] = None
    ):
        self._rules_path = rules_path or "pyv_compiler/grammar/cg_rules.toml"
        self._rules_dir = rules_dir or FileManager.cg_rules_dir
        self._node_templates: Dict[str, TemplateEngine] = {}
        self._match_rules: Dict[str, dict] = {}
        self._file_rules: List[dict] = []
        self._outputs: Dict[str, List[str]] = {}
        self._current_file: Optional[str] = None
        self._load_rules()

    # ---- 规则加载 ----
    def _load_rules(self) -> None:
        data = FileManager.load_all_toml(self._rules_dir)
        if not data:
            try:
                rules_content = FileManager.read_file(self._rules_path)
            except FileNotFoundError:
                alt_path = FileManager.get_full_path(self._rules_path)
                with open(alt_path, "r", encoding="utf-8") as f:
                    rules_content = f.read()
            data = tomllib.loads(rules_content)

        self._file_rules = data.pop("file_rules", [])

        for node_type, config in data.items():
            if not isinstance(config, dict):
                continue
            if node_type.startswith("_"):
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
        if isinstance(node, str):
            return node
        if not isinstance(node, Node):
            return str(node)

        node_type = node.name

        # 容器节点兜底（通过统一的 iter_children 接口）
        if node_type not in self._node_templates and node_type not in self._match_rules:
            all_kids = list(node.iter_children())
            if all_kids:
                return "".join(self.visit(c) for c in all_kids)

        self._check_file_rule(node, node_type)

        if node_type in self._match_rules:
            match_config = self._match_rules[node_type]
            attr_val = str(getattr(node, match_config["attr"], ""))
            case_engine = match_config["cases"].get(attr_val)
            if case_engine:
                return case_engine.render(node, self)

        engine = self._node_templates.get(node_type)
        if engine is not None:
            return engine.render(node, self)

        return self._fallback_render(node)

    def _fallback_render(self, node: Node) -> str:
        parts = [self.visit(c) for c in node.iter_children()]
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
        if self._current_file is None:
            self._current_file = "output.v"
            self._outputs[self._current_file] = []
        if text:
            self._outputs[self._current_file].append(text)

    # ---- 顶层接口 ----
    def generate(self, ast: Node) -> Dict[str, str]:
        self._outputs = {}
        self._current_file = None
        if self._file_rules:
            self._check_file_rule(ast, "Root")
        rendered = self.visit(ast)
        if self._current_file and self._current_file in self._outputs:
            self._outputs[self._current_file].append(rendered)
        else:
            self._outputs["output.v"] = [rendered]
        return {fname: "".join(lines) for fname, lines in self._outputs.items()}

    def optimize(self, outputs: Dict[str, str]) -> Dict[str, str]:
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
        if output_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_dir = os.path.join(base, "output")
        os.makedirs(output_dir, exist_ok=True)
        for file_name, content in outputs.items():
            file_path = os.path.join(output_dir, file_name)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  ✓ 已生成: {file_path}")
