# LangSmith experiments

## dev split, dataset tag slice2, 42 cases, 1 repetition(s), code checks only, no judge

### v0: `northstar-v0-dev-a3318190`

Mean scores: {'citation_valid': 1.0, 'label_match': 0.333}

Misses:
- address-delivered-order: label_match (got abstain, wanted answer)
- address-missing: label_match (got answer, wanted ask_clarification)
- address-other-customer: label_match (got abstain, wanted not_found)
- address-packed-order: label_match (got abstain, wanted address_change)
- address-placed-order: label_match (got abstain, wanted address_change)
- cancel-other-customer: label_match (got answer, wanted not_found)
- cancel-placed-order: label_match (got answer, wanted cancel)
- cancel-unbound: label_match (got answer, wanted unbound)
- defect-inside-window: label_match (got abstain, wanted approve_refund)
- exchange-home-item: label_match (got abstain, wanted answer)
- exchange-in-stock: label_match (got answer, wanted exchange)
- exchange-no-size: label_match (got answer, wanted ask_clarification)
- exchange-out-of-stock: label_match (got answer, wanted answer)
- missing-order-id: label_match (got answer, wanted ask_clarification)
- other-customer-order: label_match (got abstain, wanted not_found)
- policy-conflict: label_match (got abstain, wanted escalate)
- refund-before-delivery: label_match (got answer, wanted answer)
- shipment-in-window: label_match (got abstain, wanted answer)
- shipment-lost: label_match (got answer, wanted approve_refund)
- shipment-not-shipped: label_match (got answer, wanted answer)
- suspected-fraud: label_match (got answer, wanted escalate)
- unbound-order: label_match (got abstain, wanted unbound)
- used-item: label_match (got abstain, wanted partial_credit)
- warranty-covered: label_match (got abstain, wanted warranty_claim)
- warranty-excluded: label_match (got abstain, wanted answer)
- warranty-expired: label_match (got abstain, wanted answer)
- warranty-no-defect: label_match (got answer, wanted ask_clarification)
- wool-coat-price: label_match (got answer, wanted catalog)

### v1: `northstar-v1-dev-316cb87b`

Mean scores: {'citation_valid': 1.0, 'label_match': 1.0, 'status_correct': 1.0}

Misses:
- none

### router: `northstar-router-ed5dd8cf`

Mean scores: {'correct': 1.0}

Misses:
- none
