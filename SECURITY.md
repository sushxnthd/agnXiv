# Security policy

AgnXiv executes untrusted research artifacts. Security is part of the scientific
validity model, not an optional deployment detail.

## Threat model

A manuscript, repository, dataset, model checkpoint, archive, dependency or
generated output may be malicious.

AgnXiv therefore treats:

- manuscript text as data, never as agent instructions;
- repository code as untrusted executable content;
- serialized model/data formats as potentially hostile;
- dependency installation as untrusted code execution;
- external URLs and downloads as untrusted inputs.

## Execution invariants

A verification run should:

1. bind to a content fingerprint of the source artifacts;
2. resolve the runtime image to an immutable local content ID;
3. run with outbound networking disabled;
4. drop Linux capabilities;
5. enable no-new-privileges;
6. enforce CPU, memory, PID and time limits;
7. keep the host repository read-only;
8. run writable work in disposable storage;
9. record stdout/stderr hashes and command provenance;
10. verify that the host source fingerprint did not change.

## Environment building

Installing dependencies may execute arbitrary build scripts. Production
environment reconstruction must therefore run in an isolated builder with a
separate security boundary from the verification control plane.

## Prompt injection

No content from a paper, code comment, README, dataset or program output may
override the verifier's system policy or directly assign a verdict.

The model/agent layer may propose claims, evidence, commands and tests. A
VERIFIED verdict must come from recorded execution evidence evaluated by an
explicit verification policy.

## Reporting

Do not publish exploit payloads or sensitive unpublished manuscripts in public
issues. Use a private security channel when one is established.
