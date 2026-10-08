# LangSmith experiments

## test split, dataset tag slice1, 15 cases, 3 repetition(s), with the quiz judge

### v0: `northstar-v0-test-2ff656df`

Mean scores: {'answer_correct': 1.0, 'citation_valid': 1.0, 'label_match': 0.733}

Misses:
- catalog-material: label_match (got answer, wanted abstain)
- exception: label_match (got abstain, wanted escalate)
- out-of-window: label_match (got answer, wanted deny)
- proposer-cannot-approve: label_match (got answer, wanted approve_refund)

### v1: `northstar-v1-test-8e1772ba`

Mean scores: {'answer_correct': 1.0, 'citation_valid': 1.0, 'label_match': 1.0, 'status_correct': 1.0}

Misses:
- none

### router: `northstar-router-f56578be`

Mean scores: {'correct': 1.0}

Misses:
- none
