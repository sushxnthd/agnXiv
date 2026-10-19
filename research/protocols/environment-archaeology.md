# Environment Archaeology

Goal: reconstruct the minimal publication-era environment that makes a historical research artifact executable.

Compare: newest-compatible; publication-date constrained; manifest/Git-history inferred; API-signature inferred; iterative build-error repair; lineage-informed.

Metrics: build success, experiment success, result fidelity, dependency precision, repair count, wall-clock time, and unresolved ambiguity.

Do not call an environment scientifically faithful merely because it builds.

## Production v2 threshold

The fixed SciCoQA eight-paper diagnostic suite is the predeclared environment
recovery set for production-hardening v2.

Two rates are reported separately:

- **safe builder support** — the active dependency-only builder can reconstruct
  the detected metadata without executing repository-controlled build code;
- **historical reproduction readiness** — builder support is present **and** the
  dependency metadata is version-pinned/locked with constrained historical
  fidelity.

The v2 production threshold is **historical reproduction readiness >= 50% (4/8)**
with zero cases incorrectly labeled constrained when their metadata is floating,
import-inferred, or unsupported. This threshold is frozen before additional
environment-recovery changes. Safe builder support is diagnostic and cannot
substitute for historical fidelity.
