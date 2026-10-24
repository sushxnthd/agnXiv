# Frozen protocol: base-image ABA binding

## Question

Can a hosted scientific verdict remain definitive when agnXiv records an
immutable base-image ID before and after environment construction, but the
generated Dockerfile still selects that base through a mutable tag?

## Threat model

The approved tag resolves to image `A` before the build. During the build it is
retagged to a distinct canonical image `B`, and after the build it is restored
to `A`. The existing before/after equality check sees `A == A`, while the built
scientific environment inherits `B`. Execution can still match the built-image
ID, so the downstream build-to-execution gate does not expose the wrong base.

This models concurrent pulls/retags, registry or daemon races, and a compromised
intermediate component. It does not assume a SHA-256 collision.

## Frozen mechanism

Resolve the approved base tag once, require both a canonical local content ID
and a canonical repository digest, and rewrite the build plan so its `FROM`
instruction and recorded `base_image` select `repository@sha256:digest`.
Derive the environment tag and plan ID from the bound plan. Keep the post-build
tag/content-ID check as defense in depth, but do not rely on it for identity.

## Decisive experiment

- Generate 128 distinct canonical `(A, B)` pairs.
- For each pair, simulate a tag transcript `A -> B -> A`.
- Confirm the pre-fix tag-based plan selects `B` and passes the endpoint check.
- Confirm the frozen plan selects `A` regardless of the intermediate tag.
- Require the serialized build result to record `A` in both the bound plan and
  `base_image_id`.
- Preserve exact-tag controls where no mutation occurs.
- Run an independent standard-library checker without production imports.
- Run focused build/verdict tests, the full repository suite, and hosted gates.

## Strongest alternative

The existing before/after equality check is sufficient. The ABA transcript is
the direct falsifier: equal endpoints do not imply that the build consumed the
same object.

## Pass threshold

- 128/128 ABA schedules neutralized;
- zero mutable `FROM` instructions in accepted bound plans;
- all exact-tag controls preserved;
- independent checker agrees on every schedule;
- no regression in environment, verdict, or hosted-runner tests;
- production workflow runs both checkers.

## Kill condition

Kill the mechanism if Docker cannot consume the resolved local image ID as a
`FROM` reference, if the final recorded plan differs from the actual
Dockerfile, or if any accepted adversarial schedule selects `B`.

## Smallest possible claim

If the gate passes, agnXiv may claim that environment construction selects the
same locally resolved immutable base-image content ID recorded in its build
evidence, even under mutable-tag ABA races. It may not claim registry
provenance, publisher authenticity, vulnerability freedom, or historical
equivalence from this mechanism alone.
