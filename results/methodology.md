# Methodology

This Adaptive Workflow benchmark uses the same frozen task prompts and deterministic EvalPlus base/Plus tests for all conditions. Base and Plus outcomes come from the same completion. Model-weighted token values are cost proxies, not FLOPs or hardware compute. Physical efficiency evidence is CPU, RAM, and time measured during the run. A checksum-bound post-run reconciliation restores one measured Ollama token counter pair while leaving raw records and verification outcomes unchanged.
