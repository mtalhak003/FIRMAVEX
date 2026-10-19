# FIRMAVEX product test result

Outcome: **reproduced_in_emulator**
Run state: **completed**
Measurement mode: **real_firmware**
Execution evidence: **complete**

Triggering input: [2, 1]
Charged evaluator attempts: 3
Completed observations: 3
Infrastructure failures: 0

No configured failure within a budget is not proof that firmware is safe.
Charged evaluator attempts are not independently verified physical executions.
Observations concern the declared QEMU environment, not physical hardware.
A matching runtime signature is not a coverage or complete-path guarantee.

Reproduction: {"completed_observations": 3, "input": [2, 1], "matching_observations": 3, "requested_attempts": 3, "status": "reproduced_in_emulator"}

Publication note: QEMU exited with code 1 after recorded firmware completion on all three attempts. This is not evidence of a clean natural QEMU exit. See README.md for scope and sanitization details.
