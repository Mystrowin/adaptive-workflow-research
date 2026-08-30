"""Container-only one-task adapter for the pinned EvalPlus evaluator.

This module is copied read-only into a locked-down local container. It must not
be imported by the benchmark host process because candidate code is untrusted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RESULT_PREFIX = "ADAPTIVE_BENCHMARK_RESULT="


def _to_result(value):
    status, details = value
    return {"status": str(status), "details": [bool(item) for item in details]}


def main() -> int:
    from evalplus.eval._special_oracle import (  # type: ignore[import-not-found]
        MBPP_OUTPUT_NOT_NONE_TASKS,
    )
    from evalplus.evaluate import (  # type: ignore[import-not-found]
        check_correctness,
        get_groundtruth,
    )

    request_path = Path(sys.argv[1])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request_path.unlink()
    dataset = request["dataset"]
    task_id = request["task_id"]
    if dataset == "humaneval":
        output_not_none = []
    elif dataset == "mbpp":
        output_not_none = MBPP_OUTPUT_NOT_NONE_TASKS
    else:
        raise ValueError("dataset must be humaneval or mbpp")
    problem = request["problem"]
    if problem["task_id"] != task_id:
        raise ValueError("task identity does not match the frozen problem")
    expected = get_groundtruth(
        {task_id: problem},
        f"{request['dataset_hash']}-{task_id.replace('/', '_')}",
        output_not_none,
    )[task_id]
    checked = check_correctness(
        dataset,
        0,
        problem,
        request["solution"],
        expected,
        base_only=False,
        fast_check=False,
        identifier=request["identifier"],
        min_time_limit=float(request["min_time_limit"]),
        gt_time_limit_factor=float(request["gt_time_limit_factor"]),
    )
    result = {
        "task_id": task_id,
        "base": _to_result(checked["base"]),
        "plus": _to_result(checked["plus"]),
    }
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
