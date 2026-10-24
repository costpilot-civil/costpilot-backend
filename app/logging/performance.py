import logging
from time import perf_counter


class StageTimer:
    def __init__(self) -> None:
        self._started = perf_counter()
        self._checkpoint = self._started
        self._stages: dict[str, float] = {}

    def mark(self, stage: str) -> None:
        now = perf_counter()

        self._stages[stage] = (now - self._checkpoint) * 1000
        self._checkpoint = now

    def report(
        self,
        logger: logging.Logger,
        operation: str,
        **context: object,
    ) -> None:
        total_ms = (perf_counter() - self._started) * 1000

        fields = [
            f"operation={operation}",
            *(f"{key}={value}" for key, value in context.items()),
            f"total_ms={total_ms:.2f}",
            *(f"{stage}_ms={duration:.2f}" for stage, duration in self._stages.items()),
        ]

        logger.info("PERF | %s", " | ".join(fields))
