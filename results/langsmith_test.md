# LangSmith experiments

## test split, dataset tag slice1, 15 cases, 3 repetition(s), code checks only, no judge

### v0: `northstar-v0-test-7e6b80ed`

Mean scores: {'citation_valid': 1.0, 'label_match': 0.733}

Misses:
- catalog-material: label_match (got answer, wanted abstain)
- exception: label_match (got abstain, wanted escalate)
- out-of-window: label_match (got answer, wanted deny)
- proposer-cannot-approve: label_match (got answer, wanted approve_refund)

### v1: `northstar-v1-test-972d2010`

Mean scores: {'citation_valid': 1.0, 'label_match': 1.0, 'status_correct': 1.0}

Misses:
- none

### router: `northstar-router-579de7e9`

Mean scores: {'correct': 1.0}

Misses:
- none
