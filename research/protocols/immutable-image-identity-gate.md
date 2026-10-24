# Frozen protocol: immutable image identity grammar

## Question

Can agnXiv's hosted publication boundary distinguish canonical Docker content
identities from strings that merely begin with `sha256:`?

## Threat model

The verdict gate currently uses a prefix test for both the base and built image
IDs. A truncated digest, a non-hex payload, surrounding whitespace, another
algorithm, or a human placeholder can therefore be represented as immutable
evidence. Although the normal Docker inspector should emit canonical IDs, the
publication boundary must validate rather than trust upstream evidence shape.

## Frozen experiment

- Generate at least 100 deterministic adversarial identity pairs covering empty
  payloads, lengths 1--63 and 65--96, non-hex characters, uppercase encodings,
  whitespace, wrong algorithms, prefixes/suffixes, and human placeholders.
- Require zero decisive verdicts when either base or built identity is invalid.
- Preserve the provisional measurement and original numeric decision.
- Require canonical lowercase `sha256:` plus exactly 64 hexadecimal characters
  to preserve the decisive positive control.
- Run an independent standard-library checker with no agnXiv imports.
- Use the hosted real-paper, service-image, production, and test workflows as
  prospective controls for genuine Docker-generated identities.

## Strongest alternative explanation

The upstream Docker inspector normally returns valid IDs, so malformed values
may seem unreachable. The decisive falsification is at the independent verdict
boundary: construct valid typed build records carrying malformed identity
strings and test whether they can still publish a scientific verdict.

## Acceptance threshold

Accept only with zero false decisive verdicts across the frozen attack matrix,
an unchanged canonical positive control, independent-checker agreement, full
local regression, and all relevant hosted workflows green.

## Kill condition

Kill or reformulate on any malformed identity that remains decisive, any loss
of provisional evidence, any rejection of a canonical Docker ID, or a hosted
regression.

## Smallest intended consequence

The result may claim only that agnXiv validates the canonical syntax of image
content IDs at inspection and publication boundaries. It does not prove image
availability, registry authenticity, runtime isolation, or historical fidelity.
