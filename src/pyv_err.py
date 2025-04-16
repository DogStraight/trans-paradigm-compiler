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