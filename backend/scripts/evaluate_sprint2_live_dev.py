"""Live developer evaluation is disabled pending an owner-approved cost policy.

Offline validation remains available through tests/test_orchestration_benchmark.py.
The baseline arms' US$5 policy does not authorize this separate developer runner.
"""


def main() -> None:
    raise SystemExit(
        "Live developer evaluation is disabled pending an owner-approved pre-request cost policy. "
        "No settings, credentials or model clients were loaded. "
        "Use the offline orchestration benchmark tests instead."
    )


if __name__ == "__main__":
    main()
