# LangSmith experiments

## dev split, dataset tag slice3-es, 6 cases, 3 repetition(s), with the quiz judge

### v0: `northstar-v0-dev-ccc3db54`

Mean scores: {'answer_correct': 0.5, 'citation_valid': 1.0, 'label_match': 0.333, 'reply_language': 0.0}

Misses:
- es-chargeback: label_match (got abstain, wanted escalate)
- es-chargeback: reply_language (no comment)
- es-favorite-color: reply_language (no comment)
- es-jailbreak: label_match (got abstain, wanted safe)
- es-jailbreak: reply_language (no comment)
- es-refund: label_match (got abstain, wanted approve_refund)
- es-refund: reply_language (no comment)
- es-shoe-window: answer_correct (no comment)
- es-shoe-window: label_match (got abstain, wanted answer)
- es-shoe-window: reply_language (no comment)
- es-unknown-item: reply_language (no comment)

### v1: `northstar-v1-dev-9c62c32c`

Mean scores: {'answer_correct': 1.0, 'citation_valid': 1.0, 'label_match': 1.0, 'reply_language': 1.0, 'status_correct': 1.0}

Misses:
- none

### router: `northstar-router-a486112a`

Mean scores: {'correct': 1.0}

Misses:
- none
