"""Four-parameter Bayesian knowledge tracing, separate from FSRS review scheduling."""
import hashlib
import json
import math
import unicodedata

DEFAULT = dict(initial=.2, learn=.12, guess=.25, slip=.1)
VERSION = 'bkt-default-v1'


def update(prior, correct, parameters=None):
    params = parameters or DEFAULT
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in (prior, *params.values())):
        raise ValueError('BKT probabilities must be finite and within [0, 1]')
    predicted = prior * (1 - params['slip']) + (1 - prior) * params['guess']
    numerator = prior * ((1 - params['slip']) if correct else params['slip'])
    denominator = predicted if correct else 1 - predicted
    if denominator <= 0:
        raise ValueError('Observation has zero probability under this model')
    posterior = numerator / denominator
    mastery = posterior + (1 - posterior) * params['learn']
    return dict(prior=prior, predicted_correct=predicted, posterior=posterior, mastery=mastery,
                parameters=dict(params), version=VERSION)


def concept_mapping(question, quiz_id):
    label = unicodedata.normalize('NFKC', question.get('knowledge_point', '')).strip()[:120] or '未映射知识点'
    documents = sorted({c['doc_id'] for c in question.get('citations', []) if c.get('doc_id')})
    scope = documents or [quiz_id]
    fingerprint = json.dumps([scope, label.casefold()], ensure_ascii=False, separators=(',', ':'))
    return {'id': hashlib.sha256(fingerprint.encode()).hexdigest(), 'label': label,
            'confidence': 'quote_linked_not_human_verified' if documents else 'model_label_unverified'}
