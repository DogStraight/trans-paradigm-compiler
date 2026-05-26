# parser/parser_context.py
from define import Token, Node, GrammarRule
import copy


class ParseContext:
    """解析上下文，管理解析过程中的所有状态"""

    def __init__(self, tokens: list[Token]) -> None:
        self._snapshot_stack = []  # 添加快照栈
        self.tokens = tokens
        self.token_pointer = 0
        self.match_length = 0
        self.current_node: Node | None = None
        self.current_rule: GrammarRule | None = None
        self.production_pointer = 0
        self.exc_type = None
        self.exc_tb = None

    def __enter__(self):
        # 修复：进入with块时压入快照
        snapshot = self.create_snapshot()
        self._snapshot_stack.append(snapshot)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 修复：先判断栈非空，再pop
        if not self._snapshot_stack:
            return False
        snapshot = self._snapshot_stack.pop()
        if exc_type is not None:
            self.restore_snapshot(snapshot)
        # 返回False让异常继续传播（如需捕获可在外层处理）
        return False

    def advance_token(self, count=1):
        """向前移动token指针"""
        self.token_pointer += count
        self.match_length += count

    def advance_production(self, count=1):
        """向前移动产生式指针"""
        self.production_pointer += count

    def create_snapshot(self):
        """创建解析状态快照，用于回溯"""
        snapshot = {
            "token_pointer": self.token_pointer,
            "match_length": self.match_length,
            "current_node": copy.deepcopy(self.current_node),
            "current_rule": self.current_rule,
            "production_pointer": self.production_pointer,
        }
        return snapshot

    def restore_snapshot(self, snapshot):
        """恢复到之前的解析状态"""
        self.token_pointer = snapshot["token_pointer"]
        self.match_length = snapshot["match_length"]
        self.current_node = snapshot["current_node"]
        self.current_rule = snapshot["current_rule"]
        self.production_pointer = snapshot["production_pointer"]

    def update_current_node(self, node: Node):
        self.current_node = node

    def update_current_rule(self, rule: GrammarRule):
        self.current_rule = rule

    def update_match_length(self, length: int):
        self.match_length = length

    def has_more_tokens(self) -> bool:
        """判断是否还有未解析的token"""
        return self.token_pointer < len(self.tokens)

    def peek_token(self, offset=0) -> Token | None:
        """查看指定偏移的token（不移动指针）"""
        pos = self.token_pointer + offset
        return self.tokens[pos] if pos < len(self.tokens) else None

    def check_end_case(self, end_case: list[str]) -> bool:
        """检查当前 token 是否属于结束符集合（或已无更多 token）"""
        if not self.has_more_tokens():
            return True
        next_token = self.peek_token()
        if next_token is None:
            return True
        return next_token.type in end_case
