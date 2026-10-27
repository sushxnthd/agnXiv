# Service-image CVE-2026-84782 remediation protocol

Status: frozen before implementation.

## Trigger

The hosted `service-image` run `40457964887` built commit
`aedfbc8d35d1f07035ad33149a0bbc2c6f44a540`, then failed its mandatory
Trivy gate on 2026-10-27. The exact finding was:

- image: `agnxiv-service:test` (`debian 12.15`)
- packages: `openssl`, `libssl3`
- installed version: `3.0.22-1~deb12u1`
- vulnerability: `CVE-2026-84782` (HIGH)
- first fixed version reported by Trivy: `3.0.22-1~deb12u2`
- aggregate result: 2 HIGH package findings, 0 CRITICAL

This is preserved as a production-gate negative result. The scanner must not
be weakened, ignored, or supplied with a VEX assertion merely to make the gate
green.

## Frozen remediation

Keep the digest-pinned Python base and install the current Debian security
updates for `openssl` and `libssl3` before application dependencies. Record the
installed package versions during the hosted build so the repair remains
auditable even though Debian's security repository advances.

## Acceptance criteria

1. The built image reports both `openssl` and `libssl3` at a version not older
   than `3.0.22-1~deb12u2` according to Debian version ordering.
2. The unchanged Trivy policy (`os,library`, `HIGH,CRITICAL`, `ignore-unfixed`)
   reports zero findings and exits successfully.
3. The container health endpoint returns 200.
4. The readiness endpoint remains fail-closed with 503 when production
   configuration is absent.
5. The repository's full tests, Ruff checks, production gate, and security
   audit remain green.

## Falsifiers

- either affected package remains at `3.0.22-1~deb12u1`;
- the scan passes only after suppressing or narrowing the existing policy;
- the service fails to start; or
- the unconfigured container reports ready.

## Claim boundary

Passing this protocol establishes removal of the two observed fixed-package
findings at build time. It does not establish perpetual image safety, absence
of lower-severity or unfixed vulnerabilities, or a live deployment.
