# v0.2.0 release-candidate gate

This gate turns the reviewed research branch into reproducible candidate
artifacts without creating a public tag or claiming a deployment.

The hosted workflow must:

1. build both the wheel and source archive from one exact commit;
2. install only the wheel into a fresh virtual environment with the PDF extra;
3. confirm package metadata reports version 0.2.0 and all dependencies are
   consistent;
4. pass the machine-readiness check, including the Docker daemon;
5. complete the pinned external paper/repository workflow from the installed
   wheel;
6. reproduce the measured value 0.504 for the paper's reported 0.51 while
   retaining the final conservative UNABLE_TO_VERIFY verdict;
7. emit a manifest binding the exact commit, distribution hashes, audit-record
   hash, and bounded acceptance outcome; and
8. preserve both distributions, the audit record, and manifest as one hosted
   artifact.

A passing candidate is necessary but not sufficient for release. It does not
authorize merging PR #50, creating a tag, publishing to PyPI, claiming a hosted
deployment, or broadening scientific coverage. Those remain explicit human
review and release decisions.
