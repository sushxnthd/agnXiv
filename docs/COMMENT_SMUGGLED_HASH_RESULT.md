# Comment-smuggled dependency-hash result

## Decisive falsification

Before this correction, agnXiv classified a requirement such as

```text
package==1.0 # --hash=sha256:<64 hex characters>
```

as `hash-pinned`. Pip discards the apparent hash as comment text, leaving an
unhashed requirement whose artifact may be selected from mutable index state.
Because the hosted verdict firewall trusted the `hash-pinned` classification,
this was a concrete false-pass path for definitive scientific verdicts.

## Enforcement mechanism

1. Requirement comments are removed before logical requirements and hash
   tokens are parsed.
2. A package is hash-pinned only when a valid SHA-256 token remains in the
   effective, non-comment requirement.
3. Every accepted hash-pinned build now invokes pip with explicit
   `--require-hashes`; the build itself therefore fails if a classifier/parser
   discrepancy leaves any effective dependency unhashed.
4. Unhashed version pins remain usable for conditional evidence, but cannot
   authorize a definitive hosted verdict.

## Adversarial evidence

| Gate | Result |
|---|---:|
| Old-classifier false accepts | 128/128 |
| Corrected attack rejections | 128/128 |
| Genuine hash controls preserved | 32/32 |
| False definitive-evidence cases after correction | 0 |
| Independent stdlib-only audit | 128/128 attacks; 32/32 controls |
| Independent production imports | 0 |
| Primary digest | `30badedd4e540984a4be121837590201c90c3930fdeb7793d4361865516c3909` |
| Independent digest | `b248c3949b3ae78f2b719bbb3498cde7a0b1ebec137f55f91ac2b7ddc4e79609` |

The attack matrix covers spaces, tabs, mixed whitespace, upper/lowercase hex,
multiple packages, trailing comment text and comment-contained continuations.
Controls cover both inline and continued effective hash syntax.

## Production consequence

Comment text can no longer satisfy agnXiv's dependency-artifact identity gate.
Even if a future parsing error incorrectly upgrades a manifest, explicit pip
hash mode supplies a second fail-closed boundary during image construction.
The manifest snapshot digest, immutable base binding, immutable built-image ID
and execution-image identity checks remain unchanged.

## Novelty and limitations

Pip comment syntax and `--require-hashes` are established package-management
features. This is not claimed as a new dependency-security primitive. The
defensible result is discovery, adversarial reproduction and closure of a
specific scientific-verdict false pass in agnXiv's evidence chain.

The correction does not establish package-index authenticity, historical
environment fidelity, immunity to SHA-256 collision, malicious wheel safety,
build-host integrity, sandbox isolation, or scientific correctness. It covers
only whether effective pip requirement tokens, rather than discarded comment
text, supply the artifact hashes used to authorize decisive evidence.
