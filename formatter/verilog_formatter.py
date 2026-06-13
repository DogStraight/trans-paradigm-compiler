#!/usr/bin/env python3
# verilog_formatter.py - 完全修复版，支持单字符行畸形代码

class VerilogFormatter:
    def __init__(self, indent=4, section_gaps=True):
        self.indent = indent
        self.section_gaps = section_gaps

    def format(self, code):
        code = code.replace('\r\n', '\n').replace('\r', '\n')
        lines = code.split('\n')
        module_info = self._parse_module(lines)
        if not module_info:
            return code

        name, param_items, port_items, body_lines = module_info

        header = self._format_header(name, param_items is not None)
        formatted_params = self._format_params(param_items) if param_items else []
        formatted_ports = self._format_ports(port_items) if port_items else []
        declarations, other_lines, always_blocks = self._split_body(body_lines)
        formatted_decls = self._format_declarations(declarations)
        formatted_other = self._format_other_lines(other_lines)
        formatted_always = self._format_always_blocks(always_blocks)

        return self._assemble(header, formatted_params, formatted_ports,
                              formatted_decls, formatted_other, formatted_always,
                              has_params=param_items is not None)


    # ------------------------------------------------------------
    # 解析阶段
    # ------------------------------------------------------------
    def _parse_module(self, lines):
        start_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith('module'):
                start_idx = i
                break
        if start_idx is None:
            return None

        full_text = '\n'.join(lines)
        semicolon_pos = self._find_semicolon_outside_paren(full_text, 0)
        if semicolon_pos == -1:
            return None
        module_decl = full_text[:semicolon_pos+1]

        mod_line = lines[start_idx].strip()
        mod_name = mod_line.split()[1] if len(mod_line.split()) > 1 else ''

        param_block = None
        port_block = None
        i = 0
        while i < len(module_decl):
            if module_decl[i] == '#':
                j = i+1
                while j < len(module_decl) and module_decl[j] == ' ':
                    j += 1
                if j < len(module_decl) and module_decl[j] == '(':
                    param_end = self._find_matching_paren(module_decl, j)
                    if param_end != -1:
                        param_block = module_decl[j+1:param_end].strip()
                        i = param_end + 1
                        continue
            elif module_decl[i] == '(':
                port_end = self._find_matching_paren(module_decl, i)
                if port_end != -1:
                    port_block = module_decl[i+1:port_end].strip()
                    break
            i += 1

        param_items = self._split_top_level(param_block) if param_block is not None else None
        port_items = self._split_top_level(port_block) if port_block is not None else []

        body_start = semicolon_pos + 1
        endmodule_pos = full_text.find('endmodule', body_start)
        if endmodule_pos == -1:
            body_lines = []
        else:
            body_text = full_text[body_start:endmodule_pos]
            body_lines = body_text.split('\n')

        # 关键修复：合并并重建畸形 always 块
        body_lines = self._reconstruct_mangled_body(body_lines)
        return (mod_name, param_items, port_items, body_lines)

    def _find_matching_paren(self, s, start):
        if start >= len(s) or s[start] != '(':
            return -1
        depth = 0
        for i in range(start, len(s)):
            if s[i] == '(':
                depth += 1
            elif s[i] == ')':
                depth -= 1
                if depth == 0:
                    return i
        return -1

    def _find_semicolon_outside_paren(self, s, start):
        depth = 0
        for i in range(start, len(s)):
            if s[i] == '(':
                depth += 1
            elif s[i] == ')':
                depth -= 1
            elif s[i] == ';' and depth == 0:
                return i
        return -1

    def _split_top_level(self, text):
        if not text:
            return []
        parts = []
        current = []
        depth = 0
        for ch in text:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == ',' and depth == 0:
                parts.append(''.join(current).strip())
                current = []
                continue
            current.append(ch)
        if current:
            parts.append(''.join(current).strip())
        return parts

    def _reconstruct_mangled_body(self, body_lines):
        """检测并修复单字符行的畸形代码"""
        # 统计非空行长度
        non_empty = [ln for ln in body_lines if ln.strip()]
        if not non_empty:
            return body_lines
        short_count = sum(1 for ln in non_empty if len(ln.strip()) <= 2)
        # 条件2：存在 endelse/beginxxx 等关键字合并
        merged_kw = any('endelse' in ln or 'beginif' in ln or 'endbegin' in ln
                        for ln in non_empty)
        # 如果大部分行都是短行（单字符）或关键字合并，则进行重建
        if short_count > len(non_empty) // 2 or merged_kw:
            # 将所有行拼接成一个字符串
            raw = ''.join(body_lines)
            # 压缩连续空白为单个空格
            compressed = []
            last_was_space = False
            for ch in raw:
                if ch.isspace():
                    if not last_was_space:
                        compressed.append(' ')
                        last_was_space = True
                else:
                    compressed.append(ch)
                    last_was_space = False
            code_str = ''.join(compressed).strip()
            # 根据 Verilog 语法插入换行（忽略字符串内，但这里没有字符串）
            # 策略：在 ';' 后换行，在 'begin' 和 'end' 前后换行
            result = []
            i = 0
            n = len(code_str)
            while i < n:
                # 检查 begin
                if code_str.startswith('begin', i):
                    result.append('\nbegin')
                    i += 5
                    # begin 后如果有内容，换行（用空格判断更精确）
                    if i < n and code_str[i] == ' ':
                        i += 1  # 跳过空格
                    if i < n and code_str[i] not in ';\n)':
                        result.append('\n')
                # 检查 end（换行到新行，处理 end else 合并）
                elif code_str.startswith('end', i):
                    after = code_str[i+3:i+7].strip()
                    if after == 'else':
                        result.append('end else')
                        i += 7  # 'end' + 'else'
                    elif after.startswith('else'):
                        result.append('end else')
                        i += 7
                    else:
                        result.append('\nend')
                        i += 3
                # 检查分号
                elif code_str[i] == ';':
                    result.append(';\n')
                    i += 1
                else:
                    result.append(code_str[i])
                    i += 1
            final_str = ''.join(result)
            # 分割成行，去除空行和首尾空白
            new_lines = [ln.strip() for ln in final_str.split('\n') if ln.strip()]
            # 合并 "always @(...)" 为一行
            merged_lines = []
            j = 0
            while j < len(new_lines):
                line = new_lines[j]
                if line == 'always' and j+1 < len(new_lines) and new_lines[j+1].startswith('@'):
                    merged_lines.append(line + ' ' + new_lines[j+1])
                    j += 2
                else:
                    merged_lines.append(line)
                    j += 1
            return merged_lines
        return body_lines

    def _split_body(self, body_lines):
        declarations = []
        always_blocks = []
        i = 0
        other_lines = []
        while i < len(body_lines):
            line = body_lines[i].strip()
            if not line:
                i += 1
                continue
            if line.startswith(('reg', 'wire', 'assign', 'localparam')):
                declarations.append(line)
                i += 1
            elif line.startswith('always'):
                # 收集整个 always 块（直到匹配的 end）
                block_lines = []
                depth = 0
                first_line = True
                while i < len(body_lines):
                    curr = body_lines[i].rstrip()
                    block_lines.append(curr)
                    # 统计本行中 begin / end 作为独立单词的出现次数
                    words = curr.split()
                    begin_cnt = words.count('begin')
                    end_cnt = words.count('end')
                    depth += begin_cnt - end_cnt
                    if depth <= 0 and not first_line:
                        # 此 end 已闭合 always 块
                        i += 1
                        break
                    first_line = False
                    i += 1
                always_blocks.append(block_lines)
            else:
                # 注释、空白等其他行保持原样
                other_lines.append(body_lines[i].rstrip())
                i += 1
        return declarations, other_lines, always_blocks

    # ------------------------------------------------------------
    # 格式化阶段
    # ------------------------------------------------------------
    def _format_header(self, mod_name, has_params):
        if has_params:
            return f"module {mod_name} # ("
        else:
            return f"module {mod_name} ("

    def _format_params(self, param_items):
        if not param_items:
            return []
        lines = []
        for i, p in enumerate(param_items):
            p = p.strip()
            if not p.startswith('parameter'):
                p = 'parameter ' + p
            if i < len(param_items) - 1:
                p += ','
            lines.append(' ' * self.indent + p)
        return lines

    def _format_ports(self, port_items):
        if not port_items:
            return []
        ports = []
        max_dir = max_type = max_width = 0
        for p in port_items:
            d, t, w, name = self._parse_port(p)
            ports.append((d, t, w, name))
            max_dir = max(max_dir, len(d))
            max_type = max(max_type, len(t))
            max_width = max(max_width, len(w))
        lines = []
        for i, (d, t, w, name) in enumerate(ports):
            line = ' ' * self.indent
            line += d.ljust(max_dir)
            if t:
                line += ' ' + t.ljust(max_type)
            if w:
                line += ' ' + w.ljust(max_width)
            line += ' ' + name
            if i < len(ports) - 1:
                line += ','
            lines.append(line)
        return lines

    def _parse_port(self, port_str):
        if '//' in port_str:
            port_str = port_str[:port_str.find('//')].strip()
        parts = port_str.split()
        if not parts:
            return ('', '', '', '')
        direction = parts[0]
        idx = 1
        type_part = ''
        if idx < len(parts) and parts[idx] in ('wire', 'reg'):
            type_part = parts[idx]
            idx += 1
        width_part = ''
        if idx < len(parts) and parts[idx].startswith('['):
            width_parts = [parts[idx]]
            idx += 1
            while idx < len(parts) and ']' not in width_parts[-1]:
                width_parts.append(parts[idx])
                idx += 1
            width_part = ' '.join(width_parts)
        name_part = parts[idx] if idx < len(parts) else ''
        if name_part.endswith(','):
            name_part = name_part[:-1]
        return (direction, type_part, width_part, name_part)

    def _format_declarations(self, decl_lines):
        if not decl_lines:
            return []
        return [' ' * self.indent + line.strip() for line in decl_lines if line.strip()]

    def _format_other_lines(self, other_lines):
        """注释等行保持原样，仅去除多余首尾空白"""
        if not other_lines:
            return []
        return [line.rstrip() for line in other_lines if line.strip()]

    def _format_always_blocks(self, blocks):
        if not blocks:
            return []
        formatted = []
        for block in blocks:
            formatted.extend(self._format_single_always(block))
        return formatted

    def _format_single_always(self, lines):
        out = []
        first = lines[0].strip()
        indent_level = 1  # always 内部缩进 1 层
        indent_next_body = False  # if/else 无 begin 时，下一句需缩进
        i = 1

        # 合并 always @(...) + begin → "always @(...) begin"
        if i < len(lines) and lines[i].strip() == 'begin':
            out.append(' ' * self.indent + first + ' begin')
            i += 1
        else:
            out.append(' ' * self.indent + first)

        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            words = line.split()

            # ---- 判断是否 if/else if/else 无 begin（单句体） ----
            is_if_cond = ('if' in words and 'begin' not in words
                          and 'end' not in words and 'endcase' not in words)
            is_else_only = (words == ['else'] or (len(words) >= 1 and words[0] == 'else'
                                                   and 'if' not in words
                                                   and 'begin' not in words))
            is_else_if = (len(words) >= 2 and words[0] == 'else' and words[1] == 'if')

            # ---- 处理 end/endcase 减少缩进 ----
            has_endcase = 'endcase' in words
            if has_endcase:
                indent_level -= 1
            has_end_word = ('end' in words and 'endmodule' not in words
                            and 'endcase' not in words)
            if has_end_word:
                indent_level -= 1

            # ---- 合并下一行逻辑 ----
            merged = False
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()

                # end + else/else if[ + begin] → "end else if (...) begin"
                if has_end_word and nxt.startswith('else'):
                    merged_line = line + ' ' + nxt
                    i += 2
                    has_new_begin = False
                    if i < len(lines) and lines[i].strip() == 'begin':
                        merged_line += ' begin'
                        has_new_begin = True
                        i += 1
                    indent_str = ' ' * self.indent * (indent_level + 1)
                    out.append(indent_str + merged_line)
                    if has_new_begin:
                        indent_level += 1
                    merged = True
                    continue

                # end else + begin → "end else begin"
                if has_end_word and 'else' in words and nxt == 'begin':
                    indent_str = ' ' * self.indent * (indent_level + 1)
                    out.append(indent_str + line + ' begin')
                    indent_level += 1
                    i += 2
                    merged = True
                    continue

                # else/if(...)/case标签 + begin → "else begin" / "if (...) begin"
                if nxt == 'begin' and not has_end_word:
                    indent_str = ' ' * self.indent * (indent_level + 1)
                    out.append(indent_str + line + ' begin')
                    indent_level += 1
                    i += 2
                    merged = True
                    continue

            if merged:
                indent_next_body = False
                continue

            # ---- 应用 if/else 单句体缩进 ----
            if indent_next_body and not has_end_word:
                if is_else_only or is_else_if:
                    # else/else if 与 if 同级，不额外缩进
                    indent_str = ' ' * self.indent * (indent_level + 1)
                    out.append(indent_str + line)
                else:
                    # 单句体（含嵌套 if）缩进 +1
                    indent_level += 1
                    indent_str = ' ' * self.indent * (indent_level + 1)
                    out.append(indent_str + line)
                    indent_level -= 1
                indent_next_body = False
            else:
                # ---- 常规缩进输出 ----
                indent_str = ' ' * self.indent * (indent_level + 1)
                out.append(indent_str + line)
                indent_next_body = False

            # ---- 设置 if/else 无 begin 标记 ----
            if is_if_cond or is_else_only:
                indent_next_body = True

            if self._has_begin_word(line) and not has_end_word:
                indent_level += 1
            if 'case' in words and 'endcase' not in words:
                indent_level += 1
            i += 1
        return out

    @staticmethod
    def _has_begin_word(s):
        """检查字符串中是否包含 begin 作为独立单词"""
        words = s.split()
        return 'begin' in words

    def _assemble(self, header, params, ports, decls, other_lines, always_blocks, has_params=False):
        lines = [header]
        if has_params:
            if params:
                lines.extend(params)
            lines.append(') (')
        if ports:
            lines.extend(ports)
        lines.append(');')

        if self.section_gaps and (decls or other_lines or always_blocks):
            lines.append('')
        if decls:
            lines.extend(decls)
        if other_lines:
            lines.extend(other_lines)
        if always_blocks:
            if self.section_gaps:
                lines.append('')
            if always_blocks and isinstance(always_blocks[0], str):
                # 扁平列表（_format_always_blocks 返回格式）
                lines.extend(always_blocks)
                lines.append('')
            else:
                # 嵌套列表（_split_body 返回格式）
                for block in always_blocks:
                    lines.extend(block)
                    lines.append('')
        lines.append('endmodule')
        while lines and lines[-1] == '':
            lines.pop()
        return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            code = f.read()
    else:
        code = sys.stdin.read()
    formatter = VerilogFormatter(indent=4, section_gaps=True)
    print(formatter.format(code), end='')