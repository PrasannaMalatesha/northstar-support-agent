# LangSmith experiments

## dev split, dataset tag slice3-photo, 3 cases, 3 repetition(s), with the quiz judge

### v0: `northstar-v0-dev-cfdbc93e`

Mean scores: {'citation_valid': 1.0, 'label_match': 0.0, 'photo_verdict': 0.0}

Misses:
- photo-no-damage: label_match (got answer, wanted approve_refund)
- photo-no-damage: photo_verdict (wanted no visible damage)
- photo-not-the-item: label_match (got answer, wanted approve_refund)
- photo-not-the-item: photo_verdict (wanted does not show the item)
- photo-visible-damage: label_match (got answer, wanted approve_refund)
- photo-visible-damage: photo_verdict (wanted visible damage)

### v1: `northstar-v1-dev-95292eda`

Mean scores: {'citation_valid': 1.0, 'label_match': 1.0, 'photo_verdict': 1.0, 'status_correct': 1.0}

Misses:
- none

### router: `northstar-router-c2071900`

Mean scores: {'correct': 1.0}

Misses:
- none
