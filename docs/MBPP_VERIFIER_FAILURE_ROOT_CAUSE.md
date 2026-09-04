# Sanitized evidence for six shared MBPP verifier failures

This artifact exposes the non-sensitive evidence used to classify the six
condition-independent MBPP failures in the August 2026 run. It was produced by
selectively reading preserved records and source; no benchmark task was
executed and no candidate was regenerated.

## Evidence boundary

- Bound raw-results SHA-256:
  `6926147073d0e5b3ffe93ecb3d9c8619707b24f0b48a843d25db6627602268da`.
- Each task has one affected cell in `small_only`, `strong_only`, and
  `adaptive`: 18 records total.
- Every record has `status=verifier_error`, `base_status=error`,
  `plus_status=error`, and the stored wrapper message
  `invalid EvalPlus verifier output: result marker was not present`.
- The terminal exception lines below are copied from the preserved container
  stderr after removing redundant stack frames. They contain no prompt,
  generated candidate, credential, personal path, or private source.
- The exact frozen historical source tree is unavailable. The public current
  harness is corroborating static evidence, not proof of byte-identical
  historical code.

## Task-level evidence

| Task | Conditions | Preserved terminal exception | Static source correspondence | Conclusion |
| --- | --- | --- | --- | --- |
| `Mbpp/106` | small-only, strong-only, Adaptive | `TypeError: can only concatenate list (not "tuple") to list` in `add_lists` during `get_groundtruth` | EvalPlus v0.3.1 converts the second argument to a tuple for task 106; the public harness loads raw `MbppPlus.jsonl.gz` records and passes them directly to `get_groundtruth`. | **Strongly inferred:** required MBPP deserialization was bypassed. The failure itself is directly established. |
| `Mbpp/124` | small-only, strong-only, Adaptive | `TypeError: must be real number, not str` in `angle_complex` during `get_groundtruth` | EvalPlus v0.3.1 converts the serialized inputs to `float` and `complex` for task 124. | **Strongly inferred:** required MBPP deserialization was bypassed. The failure itself is directly established. |
| `Mbpp/252` | small-only, strong-only, Adaptive | `TypeError: must be real number, not str` in `convert` during Plus ground-truth generation | EvalPlus v0.3.1 converts the serialized input to `complex` for task 252. | **Strongly inferred:** required MBPP deserialization was bypassed. The failure itself is directly established. |
| `Mbpp/580` | small-only, strong-only, Adaptive | `TypeError: unsupported operand type(s) for %: 'list' and 'int'` in `even_ele` during `get_groundtruth` | EvalPlus v0.3.1 recursively converts nested lists to tuples for task 580. | **Strongly inferred:** required MBPP deserialization was bypassed. The failure itself is directly established. |
| `Mbpp/720` | small-only, strong-only, Adaptive | `TypeError: can only concatenate list (not "tuple") to list` in `add_dict_to_tuple` during `get_groundtruth` | EvalPlus v0.3.1 performs task-specific tuple conversion for task 720. | **Strongly inferred:** required MBPP deserialization was bypassed. The failure itself is directly established. |
| `Mbpp/255` | small-only, strong-only, Adaptive | `OSError: [Errno 28] No space left on device` at `pickle.dump(expected_output, f)` | All three stdout records say expected outputs completed before the cache write. The public harness creates `/tmp` as a 536,870,912-byte tmpfs. Static input analysis shows a dominant `combinations_with_replacement` case producing 1,663,740 length-77 tuples. | **Directly established:** cache-pickle write failed for lack of space after ground-truth computation. **Strongly inferred:** the 512 MiB tmpfs was the binding limit, because the exact historical source is unavailable. |

The five deserialization conclusions follow the same causal chain: preserved
tracebacks show canonical ground-truth execution receiving the wrong runtime
types; the publication-safe harness loads raw compressed JSON rather than
calling EvalPlus's loader; and EvalPlus v0.3.1's `get_mbpp_plus()` explicitly
calls `mbpp_deserialize_inputs()` for both base and Plus inputs, including the
five task-specific conversions above.

## Mbpp/255 expansion calculation

The pinned canonical function returns
`list(combinations_with_replacement(colors, n))`. Static inspection of the
pinned inputs, without executing the function, gives:

- dominant case: 5 colors and tuple length 77;
- tuple count: `C(5 + 77 - 1, 77) = C(81, 77) = 1,663,740`;
- a length-77 tuple container on the 64-bit CPython layout used for this static
  estimate occupies 656 bytes including element-reference slots;
- dominant-case tuple containers therefore require approximately
  `1,663,740 x 656 = 1,091,413,440` bytes (1.09 GB decimal, 1.016 GiB), before
  the outer list and pickle representation;
- across the 112 base/Plus cases, the static combinatorial count is 2,015,960
  tuples, with an estimated 1.321 GB of tuple/list container footprint before
  pickle overhead.

This calculation is explanatory evidence, not a measurement of the serialized
pickle size. The preserved `Errno 28` is the direct evidence that the actual
cache write exhausted its filesystem.

## Public source anchors

- `benchmark/engine/src/agents/adaptive_workflow/benchmark/verifier.py` loads
  raw `MbppPlus.jsonl.gz`, passes the problem record to the container, and
  declares `/tmp:rw,noexec,nosuid,size=536870912`.
- `benchmark/engine/src/agents/adaptive_workflow/benchmark/evalplus_adapter.py`
  passes that problem directly to `get_groundtruth`.
- EvalPlus v0.3.1 MBPP loader:
  <https://github.com/evalplus/evalplus/blob/v0.3.1/evalplus/data/mbpp.py>
- EvalPlus v0.3.1 ground-truth cache path:
  <https://github.com/evalplus/evalplus/blob/v0.3.1/evalplus/evaluate.py>

## Interpretation

These failures remain failures in the primary 542-task denominator. The
evidence explains why the historical verifier rejected the cells; it does not
recover the generated candidates or establish what their corrected EvalPlus
outcomes would have been. Corrected outcomes require a new experiment.
