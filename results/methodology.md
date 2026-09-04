# Methodology summary

The historical study used identical frozen prompts and task order across three
conditions. Adaptive received at most one candidate per reached tier and used
the same EvalPlus Plus result as both escalation gate and final endpoint. Later
tiers received the original prompt, never failed code or test feedback.

The run is an online sequential oracle-gated evaluation: routing statistics
were updated from earlier EvalPlus labels; FAST saw nearly all tasks while
later tiers saw selected failures. Conditional tier rates are not standalone
capability estimates. Adaptive also received more oracle-checked attempts than
one-attempt baselines.

Model-size-weighted token quantities are accounting proxies only. CPU-seconds
are sample-integrated estimates and wall seconds are summed
generation-and-verification time. EvalPlus is a finite test instrument, not
proof of semantic correctness. Exact historical generated programs were not
retained.
