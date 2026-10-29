"""One aggregate read budget shared by normal scans and trusted conformance."""

MAX_READ_BYTES = 8 * 1024 * 1024


class ReadLimitExceeded(ValueError):
    pass


class ReadBudget:
    def __init__(self, limit: int = MAX_READ_BYTES):
        if type(limit) is not int or not 0 < limit <= MAX_READ_BYTES:
            raise ValueError("bounded positive aggregate read limit required")
        self.limit = limit
        self.consumed = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.consumed

    def check_size(self, size: int) -> None:
        if type(size) is not int or size < 0:
            raise ValueError("nonnegative integral scan size required")
        if size > self.remaining:
            raise ReadLimitExceeded("aggregate read budget across scans exceeded")

    def consume(self, count: int) -> None:
        self.check_size(count)
        self.consumed += count


def read_memory_lines(lines: list[str], metadata: dict, budget: ReadBudget) -> dict:
    """Actual synthetic broker scan API; its caller owns verified source metadata."""
    budget.check_size(metadata["bytes"])
    if metadata["oversize_line"]:
        raise ReadLimitExceeded("physical line byte cap exceeded")
    raw = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8", "strict")
    if len(raw) != metadata["bytes"]:
        raise ValueError("owned memory source metadata changed")
    budget.consume(len(raw))
    return {"lines": lines, "bytes_read": len(raw)}
