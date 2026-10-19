# DOI and publisher-registry integration

AgnXiv can bind a hosted verification to a DOI in addition to the versioned
arXiv manuscript identifier.

## Resolution path

When a DOI is supplied with a job, AgnXiv:

1. normalizes `doi:` and `doi.org` URL forms to one canonical lower-case DOI;
2. validates the DOI syntax locally;
3. queries Crossref first;
4. falls back to DataCite when Crossref cannot resolve the identifier;
5. requires the registry-returned DOI to exactly match the requested normalized
   DOI;
6. captures title, publisher, work type, publication date, canonical URL, and
   registry identity where available;
7. hashes the canonical registry record with SHA-256.

If neither registry can bind the exact DOI, the DOI-bearing job fails
conservatively rather than attaching uncertain metadata.

## Signed provenance

The resolved publication binding is stored with the job before execution. When
the worker returns, the control plane injects that binding into every
verification bundle before validating and signing it. Consequently the
publication metadata and registry-record hash are covered by the bundle digest,
in-toto Statement, and DSSE signature.

The same binding is included in the long-term evidence capsule and exposed in
the public evidence commitment.

## Registry scope

Crossref primarily covers publisher-registered scholarly works. DataCite
broadens coverage to research datasets, software, Zenodo records, and other
research objects. AgnXiv does not infer equivalence between different DOIs,
preprint versions, or publisher versions: the submitted DOI is bound only when
the registry returns that exact normalized identifier.
