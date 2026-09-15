"""Offline synthetic BKT fitting; never imported by the API or used as personal parameters."""
import numpy as np

from app.learning.knowledge_tracing import DEFAULT

TRUTH = {'initial': .08, 'learn': .06, 'guess': .18, 'slip': .22}
VERSION = 'synthetic-bkt-v1'


def observations(value):
    data = np.asarray(value)
    if data.size == 0 or not np.isin(data, [0, 1]).all():
        raise ValueError('Observations must be nonempty binary values')
    return data.astype(float)


def predict(sequence, parameters):
    data = observations(sequence)
    if data.ndim != 2 or set(parameters) != set(DEFAULT) or any(not np.isfinite(v) or not 0 < v < 1 for v in parameters.values()):
        raise ValueError('Expected a learner-by-attempt matrix and four interior probabilities')
    prior = np.full(data.shape[0], parameters['initial'], dtype=float)
    output = np.empty_like(data)
    for step in range(data.shape[1]):
        probability = prior * (1 - parameters['slip']) + (1 - prior) * parameters['guess']
        output[:, step] = probability
        correct = data[:, step]
        likelihood = correct * (1 - parameters['slip']) + (1 - correct) * parameters['slip']
        denominator = correct * probability + (1 - correct) * (1 - probability)
        posterior = prior * likelihood / denominator
        prior = posterior + (1 - posterior) * parameters['learn']
    return output


def simulate(learners=800, attempts=30, seed=20260915):
    if not 10 <= learners <= 10000 or not 2 <= attempts <= 100:
        raise ValueError('Synthetic experiment size is bounded')
    rng = np.random.default_rng(seed)
    mastered = rng.random(learners) < TRUTH['initial']
    data = np.empty((learners, attempts), dtype=np.int8)
    for step in range(attempts):
        data[:, step] = rng.random(learners) < np.where(mastered, 1 - TRUTH['slip'], TRUTH['guess'])
        mastered |= rng.random(learners) < TRUTH['learn']
    return data


def split_learners(count, seed):
    if count < 10:
        raise ValueError('At least ten learners required')
    ids = np.random.default_rng(seed).permutation(count)
    train, validation = int(count * .6), int(count * .8)
    return {'train': ids[:train], 'validation': ids[train:validation], 'test': ids[validation:]}


def log_loss(actual, probabilities):
    p = np.clip(probabilities, 1e-12, 1 - 1e-12)
    return float(-np.mean(actual * np.log(p) + (1 - actual) * np.log1p(-p)))


def metrics(actual, probabilities):
    y, p = observations(actual), np.asarray(probabilities, dtype=float)
    if y.shape != p.shape or not np.isfinite(p).all() or (p < 0).any() or (p > 1).any():
        raise ValueError('Probabilities must match observations and be finite in [0, 1]')
    bins, ece = [], 0.
    for index in range(10):
        mask = (p >= index / 10) & ((p < (index + 1) / 10) if index < 9 else (p <= 1))
        n = int(mask.sum())
        if n:
            confidence, frequency = float(p[mask].mean()), float(y[mask].mean())
            ece += n / y.size * abs(confidence - frequency)
            bins.append({'lower': index / 10, 'upper': (index + 1) / 10, 'count': n, 'confidence': confidence, 'observed_frequency': frequency})
    return {'log_loss': log_loss(y, p), 'brier': float(np.mean((p - y) ** 2)), 'ece_10': ece, 'count': int(y.size), 'bins': bins}


def fit(train, seed=20260917, candidates=256):
    data = observations(train)
    if not 1 <= candidates <= 1024:
        raise ValueError('Candidate search exceeds experiment budget')
    keys = list(DEFAULT)
    lower, upper = np.array([.01, .005, .01, .01]), np.array([.9, .5, .45, .45])
    best = np.array(list(DEFAULT.values()))
    best_loss = log_loss(data, predict(data, DEFAULT))
    trace = [{'evaluation': 0, 'train_log_loss': best_loss, 'parameters': dict(DEFAULT)}]
    count = 0

    def consider(candidate):
        nonlocal best, best_loss, count
        count += 1
        parameters = dict(zip(keys, candidate.tolist()))
        loss = log_loss(data, predict(data, parameters))
        if loss < best_loss:
            best, best_loss = candidate.copy(), loss
            trace.append({'evaluation': count, 'train_log_loss': loss, 'parameters': parameters})

    rng = np.random.default_rng(seed)
    for candidate in rng.uniform(lower, upper, size=(candidates, 4)):
        consider(candidate)
    # A bounded coarse-to-fine coordinate search refines the best random start.
    for step in [.08, .04, .02, .01, .005]:
        for _ in range(4):
            previous = best_loss
            for axis in range(4):
                for direction in [-1, 1]:
                    candidate = best.copy()
                    candidate[axis] = np.clip(candidate[axis] + direction * step, lower[axis], upper[axis])
                    consider(candidate)
            if best_loss == previous:
                break
    return dict(zip(keys, best.tolist())), trace


def rescale(probabilities, temperature, bias):
    p = np.clip(probabilities, 1e-12, 1 - 1e-12)
    return 1 / (1 + np.exp(-(np.log(p / (1 - p)) / temperature + bias)))


def calibrate(probabilities, validation):
    data = observations(validation)
    metrics(data, probabilities)
    result = {'temperature': 1., 'bias': 0., 'validation_log_loss': log_loss(data, probabilities)}
    for temperature in np.unique(np.r_[1., np.linspace(.6, 1.8, 21)]):
        for bias in np.linspace(-.5, .5, 21):
            loss = log_loss(data, rescale(probabilities, temperature, bias))
            if loss < result['validation_log_loss']:
                result = {'temperature': float(temperature), 'bias': float(bias), 'validation_log_loss': loss}
    return result


def paired_bootstrap(actual, baseline, candidate, seed, repetitions=200):
    data = observations(actual)
    if data.ndim != 2 or not 20 <= repetitions <= 1000:
        raise ValueError('Bootstrap requires learner sequences and a bounded repetition count')
    metrics(data, baseline)
    metrics(data, candidate)
    per_learner = ((candidate - data) ** 2 - (baseline - data) ** 2).mean(axis=1)
    rng = np.random.default_rng(seed)
    sampled = per_learner[rng.integers(0, len(data), size=(repetitions, len(data)))].mean(axis=1)
    return {'metric': 'candidate_minus_default_brier', 'estimate': float(per_learner.mean()),
            'interval_95': np.quantile(sampled, [.025, .975]).tolist(), 'repetitions': repetitions,
            'resampling_unit': 'learner', 'seed': seed}
