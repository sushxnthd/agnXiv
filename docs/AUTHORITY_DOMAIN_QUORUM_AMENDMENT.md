# Protocol amendment: revoked-domain construction

This amendment was frozen after the first primary replay and before rerunning
the experiment. The original protocol remains unchanged as an audit trail.

## Preserved negative result

The first replay reproduced 96/128 parent false passes, not the predicted
128/128. All 32 cases in the `revoked_second_domain` family abstained under the
parent gate because the constructed bundle included an attestation from the
revoked key. The parent implementation already treats any presented revoked
attestation as a blocker, even when two other signatures meet its key quorum.

## Corrected construction

The scientific question is whether registry configuration can be mistaken for
usable domain diversity. The revised family therefore keeps three configured
keys:

- two active, attesting keys in one trust domain; and
- one revoked key in a second trust domain that does not attest.

The parent gate should accept because its two-key threshold is met. The
domain-aware gate should reject because only one trust domain has a valid,
active attestation. All sample counts and success criteria remain unchanged.

This amendment does not discard the initial negative result; it records why the
first construction failed and changes only the revoked-domain stimulus.
