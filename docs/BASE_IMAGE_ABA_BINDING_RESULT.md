# Base-image ABA binding gate

## Decisive falsification

agnXiv previously resolved the approved base tag to content ID `A` before an
environment build and checked that the same tag still resolved to `A` after the
build. The generated Dockerfile nevertheless contained `FROM <mutable-tag>`.
If that tag changed `A -> B -> A` around the build, both endpoint checks passed
while the scientific environment inherited `B`.

Execution-image binding does not catch this: the later execution can faithfully
run the built image derived from `B`. The false statement is in the recorded
base provenance. A compact pre-fix witness is preserved in
`research/results/base-image-aba-pre-fix-witness.json`.

## Enforcement mechanism

After the approved tag is pulled, agnXiv now independently resolves:

1. the local immutable image content ID; and
2. a canonical `repository@sha256:digest` reference.

The build plan is rewritten before its plan ID and environment tag are derived.
Its recorded `base_image` and actual Dockerfile `FROM` instruction therefore
contain the repository digest rather than the mutable tag. The existing
post-build content-ID comparison remains as defense in depth.

Docker documents digest references as immutable identifiers that select an
exact image version rather than a reusable tag:
https://docs.docker.com/reference/cli/docker/image/pull/#pull-an-image-by-digest-immutable-identifier

## Frozen evidence

| Gate | Result |
|---|---:|
| ABA tag schedules | 128 |
| Old endpoint-check false accepts | 128 / 128 |
| Digest-bound schedules neutralized | 128 / 128 |
| Mutable `FROM` lines in bound plans | 0 |
| Exact-tag controls preserved | 8 / 8 |
| Independent audit | 128 / 128 |
| Independent production imports | 0 |

Primary evidence digest:
`65c8ffa7b1f41eb2c7d5590fef89321b88b2669b6ba1c42af6d0c234860ace73`.

Independent audit digest:
`425d6e1f746e967dbd4c6b299490d4174f7d473651f196ae7c7ee076821b1fcf`.

The production gate now includes build tests plus both frozen checkers. The
real-paper hosted workflow is the decisive integration gate because it exercises
an actual Docker build from the digest-bound `FROM` instruction.

## Direct consequence

A definitive hosted scientific verdict can no longer cite base-image content
`A` while its environment was constructed from a transient image `B` selected
through the same mutable tag. The immutable base reference also becomes part of
the plan ID, so differently pinned bases cannot share an environment tag.

## Novelty and limits

Digest-pinned container bases are established software-supply-chain practice;
this is not a new cryptographic mechanism. The defensible agnXiv result is the
pre-fix false-pass witness, explicit scientific-verdict threat model, exact
build-plan binding, adversarial ABA sweep, independent checker, and integration
with the existing build-to-execution publication gate.

This mechanism does not establish registry or publisher authenticity, image
vulnerability freedom, reproducibility of upstream package indexes, dependency
correctness, sandbox isolation, dataset identity, historical equivalence, or
scientific validity. A repository digest pins the registry object selected for
the native runner platform; multi-platform equivalence is outside this result.

## Smallest supported claim

agnXiv's accepted environment-build plan now selects its base through the same
immutable repository digest recorded in the plan, preventing mutable-tag ABA
races from falsifying base-image provenance. Hosted success on the exact commit
is required before claiming the mechanism works in the production workflow.
