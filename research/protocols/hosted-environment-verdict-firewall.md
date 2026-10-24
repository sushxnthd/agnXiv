# Hosted Environment-Fidelity Verdict Firewall Protocol

Status: frozen before implementation  
Kernel branch: `hardening/scoped-environment-recovery`  
Scope: hosted `auto_verify` and `verify_spec` scientific verdict publication

## Precise question

Can agnXiv prevent a numerically correct run in an historically underdetermined dependency environment from being published as a definitive scientific verification or contradiction, while preserving the measurements and allowing definitive verdicts under an independently checkable environment certificate?

## Existing failure witness

The pinned external-paper workflow records immutable manuscript and repository identity, but the repository dependency manifest is floating and the inferred historical fidelity is approximate. The hosted result nevertheless publishes two `CONTRADICTED` verdicts. This is a fail-open boundary: dependency drift remains a live alternative explanation.

## Frozen enforcement rule

A hosted result may publish `VERIFIED`, `PARTIALLY_VERIFIED`, or `CONTRADICTED` only when all of the following hold:

1. workflow-scoped environment resolution is not ambiguous;
2. inferred historical fidelity is `constrained`;
3. the environment build uses a hash-pinned dependency manifest;
4. the built base image and resulting image have immutable image IDs.

Otherwise the raw numeric decision is retained as `provisional_verdict`, all expected/observed/error fields remain inspectable, the public record verdict becomes `UNABLE_TO_VERIFY`, hosted status becomes `needs_review`, and explicit gate reasons are serialized.

This rule is intentionally stricter than exact direct-version pins: `pkg==x` does not fix transitive dependency artifacts.

## Frozen falsification matrix

| Inferred fidelity | Build precision | Raw numeric decision | Required public decision |
|---|---|---|---|
| constrained | hash-pinned | verified/contradicted | unchanged |
| constrained | version-pinned | verified/contradicted | unable; provisional retained |
| approximate | floating | verified/contradicted | unable; provisional retained |
| unknown | base-only | verified/contradicted | unable; provisional retained |
| any | any | already unable | unchanged |

Additional attacks: ambiguous scoped manifests; missing build evidence; forged high inferred fidelity paired with a floating build; multiple zero-manifest claim bundles where only some are decisive.

## Prospective real-paper prediction

The frozen `synthiumjp/metacognitive-monitoring-battery` run at commit `2f83d0fa506e7af2b72ca191b65ce42e07c9e185` will preserve observed 0.504 vs reported 0.51 and observed 0.67 vs reported 0.68, but both hosted verdicts will become `UNABLE_TO_VERIFY` with provisional `CONTRADICTED`, and the job status will become `needs_review`.

## Strongest alternative explanation

The two target computations may be insensitive to the dependency drift. Unless that invariance is independently proved or the historical environment is fully certified, the current run cannot distinguish a scientific mismatch from environment-induced mismatch.

## Publishable/product threshold

- zero definitive hosted verdicts across every non-hash-pinned or historically unconstrained adversarial case;
- exact hash-pinned controls remain decisive;
- independent checker reproduces the gate decision without importing production code;
- real external-paper hosted evidence matches the frozen prediction;
- all measurements and provisional numeric decisions remain auditable;
- production gate and existing security tests remain green.

## Kill condition

Kill or reformulate this kernel if any underdetermined environment retains a definitive public verdict, any exact hash-pinned control is suppressed, measurements disappear, or the independent checker disagrees.

## Smallest possible claim

AgnXiv's hosted boundary prevents definitive scientific verdict publication when its own dependency evidence leaves environment drift as an unresolved explanation. It does not prove that a certified environment reproduces the authors' historical runtime, nor that a retained provisional numeric comparison is scientifically correct.
