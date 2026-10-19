# Scientific validation release v1 — 2026-10-19

AgnXiv's three P0 scientific-safety validation gates are now closed with
externally seeded or held-out evidence.

| Gate | Result | Evidence |
| --- | --- | --- |
| False-pass safety | PASS | 308 distinct external negative-control paper clusters, 0 false passes, one-sided 95% upper bound 0.9679% |
| Central-claim routing | PASS | 86 held-out papers across two external sources; R@3 98.84%, R@5 100% |
| Historical environment recovery | PASS | 30/31 dependency-source classifications correct; 7/8 dependency-only builds successful |

Primary evidence:

- `research/results/external-false-pass-v1-2026-10-19.md`
- `research/results/centrality-production-v1-2026-10-19.md`
- `research/results/historical-environment-v1-2026-10-19.md`

The final scientific-validation workflow at commit
`9ca32bb5949854dcd9c340f6b30b8899e1bac966` completed successfully in GitHub
Actions run 39225677632. The independent multi-source centrality production
workflow completed successfully in run 39224459349.

These results close the **scientific validation** section of the P0 launch
checklist. They do not close the remaining execution-security,
control-plane/DR, or evidence-durability production gaps listed in
`docs/PRODUCTION_READINESS.md`.
