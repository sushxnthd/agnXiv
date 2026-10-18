# Execution-Grounded Paper-Code Alignment

Hypothesis: claim-evidence graphs plus executable probes detect real paper-code discrepancies that static LLM inspection misses.

Ablations: code-only; paper+code; paper+code+DAG; +environment analysis; +executable probes.

Primary metrics: discrepancy recall, precision, F1, and recall at fixed high precision. Report public SciCoQA cases separately from held-out cases.

Never use the known discrepancy description as model input in the detection condition.