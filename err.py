class UnexpectedTokenError(Exception):
    pass


class UnexpectedTokenTypeError(Exception):
    pass


class IndentationError(Exception):
    pass


class BracketMismatchError(Exception):
    pass


class GrammarRuleNoFoundError(Exception):
    pass


class FullMatchFilterError(Exception):
    pass


class _SequenceMatchError(Exception):
    """序列匹配失败时抛出的内部异常，用于触发 with 块自动回滚"""

    pass


class _BranchMatchError(Exception):
    """分支匹配失败时抛出的内部异常，用于触发 with 块自动回滚"""

    pass
