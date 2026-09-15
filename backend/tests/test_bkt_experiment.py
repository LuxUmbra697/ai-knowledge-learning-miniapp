import numpy as np
import pytest
from app.learning.bkt_experiment import (
    calibrate,
    fit,
    metrics,
    paired_bootstrap,
    predict,
    simulate,
    split_learners,
)
from app.learning.knowledge_tracing import DEFAULT, update


def test_vectorized_predictions_match_runtime_and_never_use_future_answers():
    observations = np.array([[0, 1, 1, 0], [1, 0, 1, 1]])
    predicted = predict(observations, DEFAULT)
    for i, sequence in enumerate(observations):
        prior = DEFAULT['initial']
        for j, answer in enumerate(sequence):
            result = update(prior, bool(answer))
            assert predicted[i, j] == pytest.approx(result['predicted_correct'])
            prior = result['mastery']
    changed = observations.copy()
    changed[:, 2:] = 1 - changed[:, 2:]
    np.testing.assert_allclose(predict(changed, DEFAULT)[:, :3], predicted[:, :3])


def test_synthetic_data_and_learner_splits_are_reproducible_and_disjoint():
    a, b = simulate(100, 12, 81), simulate(100, 12, 81)
    np.testing.assert_array_equal(a, b)
    split = split_learners(100, 82)
    assert sorted(len(part) for part in split.values()) == [20, 20, 60]
    assert len(set(np.concatenate(list(split.values())))) == 100
    assert len(set(split['train']) & set(split['test'])) == 0


def test_fit_and_calibration_use_bounded_search_and_do_not_mutate_runtime_defaults():
    data = simulate(80, 12, 71)
    saved = dict(DEFAULT)
    fitted, trace = fit(data[:60], seed=72, candidates=16)
    assert trace and trace[-1]['train_log_loss'] <= trace[0]['train_log_loss']
    assert metrics(data[:60], predict(data[:60], fitted))['log_loss'] <= metrics(data[:60], predict(data[:60], DEFAULT))['log_loss'] + 1e-12
    probability = predict(data[60:], fitted)
    parameters = calibrate(probability, data[60:])
    assert parameters['validation_log_loss'] <= metrics(data[60:], probability)['log_loss'] + 1e-12
    assert DEFAULT == saved


def test_probability_metrics_have_known_values_and_reject_invalid_inputs():
    result = metrics(np.array([0, 1]), np.array([.25, .75]))
    assert result['brier'] == pytest.approx(.0625)
    assert result['ece_10'] == pytest.approx(.25)
    for value in (np.array([1.5, .5]), np.array([np.nan, .5])):
        with pytest.raises(ValueError):
            metrics(np.array([0, 1]), value)


def test_bootstrap_resamples_learners_and_exact_ties_have_zero_interval():
    data = simulate(20, 10, 12)
    probabilities = predict(data, DEFAULT)
    result = paired_bootstrap(data, probabilities, probabilities, seed=42, repetitions=20)
    assert result['estimate'] == 0
    assert result['interval_95'] == [0, 0]
    assert result['resampling_unit'] == 'learner'


def test_experiment_manifest_hash_matches_actual_dataset_bytes(tmp_path):
    import hashlib
    import json
    import subprocess
    import sys
    from pathlib import Path
    script = Path(__file__).resolve().parents[2] / 'scripts/experiment_bkt.py'
    subprocess.run([sys.executable, str(script), '--learners', '30', '--output', str(tmp_path)],
                   check=True, capture_output=True, timeout=30)
    manifest = json.loads((tmp_path / 'results-v1.json').read_text())
    assert manifest['dataset_sha256'] == hashlib.sha256((tmp_path / 'dataset-v1.jsonl').read_bytes()).hexdigest()
    assert manifest['provider_calls'] == 0
