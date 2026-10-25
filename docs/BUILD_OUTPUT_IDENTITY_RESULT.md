# Build-output identity binding result

## Decisive falsification

agnXiv previously tagged a successful environment build and then resolved that
mutable tag with `docker image inspect`. A concurrent local actor could reassign
the tag from genuine build output `A` to unrelated image `B` in the interval.
The later execution-identity gate would then compare `B` to recorded build ID
`B` and pass, even though the build plan and logs describe `A`.

The frozen protocol is in `BUILD_OUTPUT_IDENTITY_PROTOCOL.md`.

## Enforcement mechanism

The builder now supplies Docker an `--iidfile` outside the build context. Docker
writes the image ID produced by the build operation into that file. agnXiv
accepts exactly one canonical lowercase `sha256:<64 hex>` line and uses that
immutable ID for execution and verdict provenance. The human-readable tag is
still emitted, but it no longer supplies scientific identity evidence.

Missing, empty, malformed, non-canonical, or multi-line identity evidence fails
closed before the result can reach the verdict gate.

## Adversarial evidence

| Gate | Result |
|---|---:|
| Tag-substitution schedules | 128 |
| Old inspect-after-build false accepts | 128 / 128 |
| Build-output identities correctly bound | 128 / 128 |
| Unchanged controls preserved | 16 / 16 |
| Malformed/missing classes rejected | 4 / 4 |
| Independent stdlib-only audit | 128 / 128 |
| Independent production imports | 0 |
| Primary digest | `39728e4b946ebbc2dc4c894aa3fa6216f62f8195026408bcea318edb373e5a6a` |
| Independent digest | `a38f6937c4e9e0adbdb6a533a82a1ac3451345036fd320f2c580786182ac2bd5` |

Production integration tests additionally assert that a substituted tag is
never resolved after the build. The full repository suite, Ruff, deterministic
evidence reruns, and diff checks pass locally.

## Direct consequence

A definitive agnXiv verdict can no longer attribute a build plan to an image
selected only through a post-build mutable-tag lookup. The exact ID returned by
the build operation is the ID later executed and checked by the existing verdict
firewall.

## Novelty and limitations

Docker's iidfile is an established build feature; this is not a new container or
cryptographic primitive. The defensible contribution is discovery of the
cross-gate false pass, its adversarial reproduction, strict fail-closed identity
parser, and integration at agnXiv's scientific-verdict boundary.

The result assumes a trusted Docker daemon, build client, filesystem, kernel,
and SHA-256. It does not establish builder correctness, image safety, registry
authenticity, dependency fidelity, historical reproducibility, sandbox
isolation, or scientific correctness.

## Smallest supported claim

agnXiv now derives a successful environment build's provenance identity from
Docker's build output rather than a later mutable-tag lookup, preventing local
tag reassignment from substituting another image under the audited build plan.
Hosted success on the exact commit is required before claiming the mechanism
works in the production workflow.
