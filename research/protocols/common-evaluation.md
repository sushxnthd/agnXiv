# Common Evaluation Protocol

All AgnXiv research tracks share this contract.

## Stage logging

For every case record: paper ingest, claim extraction, centrality ranking, repository mapping, environment inference, workflow ordering, artifact resolution, observation locator, execution, numeric comparison, provenance, and final public evidence state.

## Selective verification

Systems may abstain. Report coverage and error jointly; never hide abstentions in a generic failure bucket.

Primary safety metric: `false_pass_rate = false SUPPORTS / all SUPPORTS predictions`.

Secondary metrics: false-divergence rate, selective error among decided cases, coverage, and risk-coverage curve.

## Leakage controls

During output discovery, mask reported numeric values. Freeze the chosen file/path/regex/metric before revealing the target value. Any run that uses the reported answer to select the observed output is invalid for headline evaluation.

## Benchmark contamination

Public benchmark cases with published labels are diagnostic only unless a protocol establishes a true held-out split. Headline generalization claims require held-out or newly curated cases.

## Failure taxonomy

Use one primary blocker: PAPER_PARSE, CLAIM_SELECTION, REPO_MAPPING, ENVIRONMENT, DATA, WORKFLOW, EXECUTION, OUTPUT_LOCATOR, POLICY, SECURITY, or RESOURCE_LIMIT. Preserve secondary blockers separately.

## Independence

Record whether an attempt uses author code, author checkpoint, author data split, shared derived code, or an independent implementation. Multiple correlated attempts must not be presented as independent replications.