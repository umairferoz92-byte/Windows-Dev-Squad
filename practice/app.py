"""Practice target project (throwaway). Deliberately contains one bug."""


def add(a: int, b: int) -> int:
    """Add two integers.

    Intentional bug for the agents to find and fix in Phase 5: this returns the
    product instead of the sum.
    """
    return a * b
