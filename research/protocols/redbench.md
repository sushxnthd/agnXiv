# AgnXiv RedBench

Adversarial classes: hardcoded claimed metrics; expected-value echoing; sandbox detection; prompt injection in README/comments; symlink/path escape; network attempts; source mutation; seed cherry-picking; test-set leakage; conditional outputs; malicious dependency forms.

Primary metric: adversarial false-pass rate. Secondary metrics: safe abstention rate, exploit detection rate, false alarm rate, and sandbox containment.

Every attack fixture must be safe, local, and non-destructive.