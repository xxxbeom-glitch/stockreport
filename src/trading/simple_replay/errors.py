"""SIMPLE_REPLAY failure types (never published as completed)."""


class SimpleReplayError(Exception):
    """Run failed; do not expose on dashboard."""

    def __init__(self, code: str, *, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail or code)
