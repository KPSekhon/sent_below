"""
AI systems: learned enemy behaviour, difficulty control, and evaluation.
=======================================================================

This package holds everything that makes a decision from data rather than
from a hand-written rule.

Modules:
    enemy_ai       Dueling DQN with self-attention that drives enemy actions.
                   Exposes EnemyBrain (the agent), EnemyNetwork (the model),
                   ReplayBuffer, and the shared ACTIONS list. One EnemyBrain
                   is shared across every enemy on a floor, so their
                   experience pools into a single replay buffer.

    director       Dynamic difficulty adjustment. PlayerModel predicts
                   survival and enjoyment from rolling performance metrics;
                   DifficultyAdjuster nudges a modifier to hold the player
                   near the target survival rate. Also holds the
                   content recommender for room and loot weighting.

    data_pipeline  Gameplay telemetry: JSON-Lines event logging, feature
                   extraction, and PyTorch Dataset/DataLoader construction
                   with train/val/test splits.

    ab_testing     Statistical comparison of model variants. Consistent-hash
                   traffic routing, Welch's t-test, Mann-Whitney U, Cohen's d,
                   and bootstrap confidence intervals.

The state vector and action space defined in enemy_ai are the contract that
the game loop, the offline simulator, and the serving API all share. Changing
either one means changing all three.
"""
