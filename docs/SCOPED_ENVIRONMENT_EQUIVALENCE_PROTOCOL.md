# Frozen protocol: proof-carrying requirements-alias equivalence

## Question

Can AgnXiv reduce unnecessary abstention when a workflow directory contains both
`requirements.txt` and the common `requirement.txt` alias without allowing a
filename-priority false pass?

## Rule frozen before implementation

Multiple colocated manifests resolve automatically **only** when all of the
following hold:

1. every candidate is a regular, non-symlink file named `requirements.txt` or
   `requirement.txt`;
2. there are exactly two distinct candidate paths;
3. both files have the same SHA-256 digest over their exact bytes.

The priority-ordered path is used only after this equality proof. Both paths
remain in `dependency_files` as audit evidence. Cross-format pairs, byte
differences of any kind, multiple workflow directories, unreadable files, and
all other candidate sets remain ambiguous and produce no install command.

Exact-byte identity is intentionally narrower than semantic equivalence. It
does not normalize comments, whitespace, newlines, ordering, encodings,
markers, URLs, hashes, constraints, or includes.

## Frozen evaluation

- Positive matrix: exact duplicate aliases over adversarial payload families
  (pins, markers, URLs/hashes, options/includes, comments, blank files, and
  non-UTF-8 bytes). Expected: resolved, both paths audited, deterministic
  preferred path, install command targets that path.
- Negative one-edit matrix: version, marker, URL/hash, option/include, comment,
  whitespace, newline, order, encoding, and extra-dependency changes. Expected:
  ambiguous with zero install commands.
- Cross-format controls: retain the full 36-pair manifest conflict matrix,
  except the exact duplicate requirements-alias pair which is now the one
  proved-safe positive case. The conflicting requirements-alias case remains
  ambiguous.
- Ordinary controls: every singleton manifest resolves as before; scoped
  metadata retains precedence over root metadata.

## Gates

The change survives only if the frozen matrices report zero false accepts and
zero control failures, an independent checker recomputes byte digests without
calling the production equivalence helper, the full test suite passes, and the
hosted production gate reproduces the evidence.

## Bounded claim

If the gates pass, AgnXiv may claim only that exact-byte equality is a compact,
independently checkable certificate for safely collapsing the two supported
requirements filename aliases. It may not claim semantic equivalence,
cross-format equivalence, historical reproducibility, or safety of arbitrary
duplicate manifests.
