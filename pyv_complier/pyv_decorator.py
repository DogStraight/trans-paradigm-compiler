__all__ = [
    "override"
]


def override(func):
    """
    A decorator to mark a method as an override of a base class method.
    This is purely a convention to indicate intent, and will not enforce
    anything at runtime.
    """
    # You can do some additional checks here if desired, but they would be
    # optional and not enforced by Python itself.
    return func
