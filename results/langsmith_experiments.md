# LangSmith experiments

## test split, dataset tag slice1, 15 cases, 3 repetition(s), code checks only, no judge

### v0: `northstar-v0-test-644cbc27`

Mean scores: {'citation_valid': 1.0, 'label_match': 0.733}

Misses:
- catalog-material: label_match (got answer, wanted abstain)
- exception: label_match (got abstain, wanted escalate)
- out-of-window: label_match (got answer, wanted deny)
- proposer-cannot-approve: label_match (got answer, wanted approve_refund)

### v1: `northstar-v1-test-3dab74f7`

Mean scores: {'citation_valid': 1.0, 'label_match': 0.667, 'status_correct': 1.0}

Misses:
- duplicate-hold: label_match (got unbound, wanted answer)
- one-exchange: label_match (got unbound, wanted answer)
- one-promo: label_match (got unbound, wanted answer)
- shipping-price: label_match (got abstain, wanted answer)
- wrong-item: label_match (got ask_clarification, wanted answer)

### router: `northstar-router-7fca3e8e`

Mean scores: {'correct': 1.0}

Misses:
- none
