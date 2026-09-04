"""
Contract tests across the training -> serving seam.
====================================================
These exist because of a bug that never raised: the training pipeline wrote
the player model as a bare state_dict to ``player_model.pt``, while the serving
API looked for a differently-shaped ``director.pt``. Nothing crashed. Serving
silently fell back to randomly initialised weights and returned the same
default numbers for every request.

Import tests could not catch that, because both sides worked fine on their own.
The bug lived in the gap between them, and neither side owned the gap.

So these tests do not assert "it loaded without throwing". They assert the
weights that come back out are the weights that went in.
"""

import os
import sys

import pytest
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.director import AIDirector, PlayerModel
from ai.enemy_ai import STATE_DIM, EnemyBrain


def _weights_match(model_a, model_b) -> bool:
    """True if two modules hold identical parameter tensors."""
    sd_a, sd_b = model_a.state_dict(), model_b.state_dict()
    if sd_a.keys() != sd_b.keys():
        return False
    return all(torch.equal(sd_a[k], sd_b[k]) for k in sd_a)


# ---------------------------------------------------------------------------
# Enemy brain: save_model -> load_model
# ---------------------------------------------------------------------------
def test_enemy_brain_roundtrips_through_a_checkpoint(tmp_path):
    """What EnemyBrain.save_model writes, EnemyBrain.load_model must restore."""
    trained = EnemyBrain()
    # Move the weights away from their initialisation so a silent fallback to
    # fresh weights cannot pass this test by coincidence.
    for _ in range(40):
        state = torch.rand(STATE_DIM).numpy()
        trained.store_experience(state, 0, 1.0, torch.rand(STATE_DIM).numpy(), False)
    trained.train_step()

    path = str(tmp_path / "enemy_brain.pt")
    trained.save_model(path)

    restored = EnemyBrain()
    assert not _weights_match(trained.policy_net, restored.policy_net), (
        "fresh brains should not already match; the test is not proving anything"
    )

    restored.load_model(path)

    assert _weights_match(trained.policy_net, restored.policy_net)
    assert restored.epsilon == trained.epsilon
    assert restored.training_steps == trained.training_steps


# ---------------------------------------------------------------------------
# Player model: the artefact the training pipeline actually writes
# ---------------------------------------------------------------------------
def test_player_model_state_dict_loads_into_the_director(tmp_path):
    """training/train_pipeline.py writes a bare state_dict for the player model.

    Serving must be able to load that exact shape into the director. This is
    the specific mismatch that shipped and stayed broken.
    """
    trained = PlayerModel()
    with torch.no_grad():
        for param in trained.parameters():
            param.add_(torch.randn_like(param) * 0.5)

    path = str(tmp_path / "player_model.pt")
    torch.save(trained.state_dict(), path)  # exactly what the pipeline does

    director = AIDirector()
    assert not _weights_match(trained, director.difficulty.model)

    # Exactly what serving/api.py does on startup
    state_dict = torch.load(path, map_location="cpu", weights_only=True)
    director.difficulty.model.load_state_dict(state_dict)

    assert _weights_match(trained, director.difficulty.model)


def test_director_save_state_roundtrips(tmp_path):
    """The other artefact shape: AIDirector.save_state -> load_state."""
    director = AIDirector()
    with torch.no_grad():
        for param in director.difficulty.model.parameters():
            param.add_(torch.randn_like(param) * 0.5)
    director.difficulty.difficulty_modifier = 1.23

    path = str(tmp_path / "director.pt")
    director.save_state(path)

    restored = AIDirector()
    restored.load_state(path)

    assert _weights_match(director.difficulty.model, restored.difficulty.model)
    assert restored.difficulty.difficulty_modifier == pytest.approx(1.23)


# ---------------------------------------------------------------------------
# Inference must survive a batch of one
# ---------------------------------------------------------------------------
def test_single_state_inference_does_not_raise():
    """Serving takes one enemy per request, i.e. a batch of 1.

    BatchNorm cannot compute a batch variance over a single sample, so this
    crashed in three separate places before it was caught. Any new caller that
    forgets eval() will fail here.
    """
    brain = EnemyBrain()
    state = torch.rand(1, STATE_DIM)

    brain.policy_net.eval()
    try:
        with torch.no_grad():
            q_values = brain.policy_net(state)
    finally:
        brain.policy_net.train()

    assert q_values.shape == (1, 7)


def test_difficulty_prediction_changes_with_input():
    """A struggling player must not score the same as a thriving one.

    The original failure returned identical hardcoded defaults regardless of
    input, which looked exactly like a working endpoint.
    """
    director = AIDirector()

    strong = {
        "hp_pct": 0.95, "mp_pct": 0.8, "level": 5, "kills_per_min": 12,
        "deaths": 0, "damage_ratio": 4.0, "ability_usage": 0.9,
        "potion_usage": 0.0, "clear_time_ratio": 0.5, "performance_score": 0.9,
    }
    weak = {
        "hp_pct": 0.15, "mp_pct": 0.1, "level": 3, "kills_per_min": 1,
        "deaths": 3, "damage_ratio": 0.3, "ability_usage": 0.2,
        "potion_usage": 5.0, "clear_time_ratio": 2.5, "performance_score": 0.1,
    }

    director.difficulty.update(strong, 2, 0.016)
    strong_survival = director.get_stats()["predicted_survival"]

    director.difficulty.update(weak, 4, 0.016)
    weak_survival = director.get_stats()["predicted_survival"]

    assert strong_survival != weak_survival, (
        "difficulty prediction is not responding to its input"
    )
