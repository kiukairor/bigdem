import time
import logging
import newrelic.agent

log = logging.getLogger("circuit-breaker")


class CircuitBreaker:
    """
    States:
      CLOSED   → normal operation, requests go through
      OPEN     → too many failures, requests blocked, fallback used
      HALF_OPEN → testing if service recovered
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"

    def record_success(self):
        self.failure_count = 0
        if self.state != "CLOSED":
            log.info("Circuit breaker → CLOSED (recovered)")
        self.state = "CLOSED"
        self._record_nr_metric()

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            if self.state != "OPEN":
                log.warning(
                    f"Circuit breaker → OPEN after {self.failure_count} failures"
                )
            self.state = "OPEN"
        self._record_nr_metric()

    def _check_recovery(self):
        if self.state == "OPEN" and self.last_failure_time:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                log.info("Circuit breaker → HALF_OPEN (trying recovery)")
                self.state = "HALF_OPEN"
                self.failure_count = 0

    def _record_nr_metric(self):
        state_val = {"CLOSED": 1, "HALF_OPEN": 0.5, "OPEN": 0}.get(self.state, 0)
        newrelic.agent.record_custom_metric("Custom/AICircuitBreaker/State", state_val)
        newrelic.agent.record_custom_metric(
            "Custom/AICircuitBreaker/FailureCount", self.failure_count
        )
