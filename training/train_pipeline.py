"""
ML Training Pipeline - Scalable Offline Training with Experiment Tracking
==========================================================================
Standalone training script for the DQN enemy AI and player difficulty models.
Designed to run on cloud GPU instances (AWS EC2, GCP Compute, Azure VM) or
locally via Docker.

Features:
    - Configurable hyperparameters via environment variables or CLI args
    - TensorBoard integration for loss curves, Q-value distributions, and
      reward tracking
    - Model checkpointing with versioned saves
    - Learning rate scheduling (cosine annealing)
    - Gradient norm monitoring
    - Simulated gameplay episodes for offline training
    - Early stopping based on convergence
    - ONNX model export for cross-platform deployment

Usage:
    # Local
    python -m training.train_pipeline --epochs 200 --batch-size 64

    # Docker
    docker compose up train

    # Cloud (environment variables)
    EPOCHS=500 BATCH_SIZE=128 DEVICE=cuda python -m training.train_pipeline

Demonstrates:
    - PyTorch training loops with modern best practices
    - TensorBoard experiment tracking
    - Hyperparameter configuration for cloud workloads
    - Model checkpointing and versioning
    - Learning rate scheduling
    - ONNX export for production inference
"""

import os
import sys
import time
import argparse
import json
from datetime import datetime, timezone
from typing import Dict, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.enemy_ai import (
    EnemyBrain, EnemyNetwork, ReplayBuffer,
    ACTIONS, NUM_ACTIONS, STATE_DIM,
)
from ai.director import PlayerModel

# Optional TensorBoard
try:
    from torch.utils.tensorboard import SummaryWriter
    HAS_TENSORBOARD = True
except ImportError:
    HAS_TENSORBOARD = False
    print("[train] TensorBoard not available, logging to console only")


# ---------------------------------------------------------------------------
# Simulated Game Environment for Offline Training
# ---------------------------------------------------------------------------
class SimulatedCombatEnv:
    """
    Lightweight game simulation that generates realistic state transitions
    for offline DQN training. Models enemy-player encounters without the
    full game engine, enabling fast iteration on cloud instances.

    State space: 10 continuous features (see EnemyNetwork docstring)
    Action space: 7 discrete actions
    Episode: One combat encounter (variable length, max 100 steps)
    """

    def __init__(self) -> None:
        self.enemy_hp = 1.0
        self.player_hp = 1.0
        self.distance = 0.5
        self.time = 0.0
        self.behavior = "aggressive"
        self.rng = np.random.default_rng()

    def reset(self, behavior: str = "aggressive") -> np.ndarray:
        """Reset to a new combat encounter."""
        self.enemy_hp = 1.0
        self.player_hp = 0.5 + self.rng.random() * 0.5
        self.distance = 0.3 + self.rng.random() * 0.5
        self.time = 0.0
        self.behavior = behavior
        return self._get_state()

    def step(self, action_idx: int) -> tuple:
        """Execute one step: returns (next_state, reward, done, info)."""
        action = ACTIONS[action_idx]
        prev_enemy_hp = self.enemy_hp
        prev_player_hp = self.player_hp

        # Simulate action effects
        if action == "chase":
            self.distance = max(0.05, self.distance - 0.1)
        elif action == "flee":
            self.distance = min(1.0, self.distance + 0.15)
        elif action == "attack" and self.distance < 0.3:
            if self.rng.random() < 0.6:
                self.player_hp -= 0.08 + self.rng.random() * 0.05
        elif action == "ranged_attack" and self.distance > 0.2:
            if self.rng.random() < 0.4:
                self.player_hp -= 0.05 + self.rng.random() * 0.03
        elif action == "strafe":
            self.distance += (self.rng.random() - 0.5) * 0.1

        # Player fights back
        if self.rng.random() < 0.3:
            dmg = 0.06 + self.rng.random() * 0.04
            if self.distance < 0.3:
                dmg *= 1.5
            self.enemy_hp -= dmg

        self.time += 0.05
        self.player_hp = max(0, self.player_hp)
        self.enemy_hp = max(0, self.enemy_hp)

        done = self.enemy_hp <= 0 or self.player_hp <= 0 or self.time >= 1.0

        hit_landed = (action in ("attack", "ranged_attack")
                      and prev_player_hp > self.player_hp)
        damage_taken = prev_enemy_hp > self.enemy_hp

        reward = EnemyBrain.compute_reward(
            self.enemy_hp, self.player_hp, action,
            prev_enemy_hp, prev_player_hp, self.distance,
            hit_landed=hit_landed, damage_taken=damage_taken,
        )

        return self._get_state(), reward, done, {
            "hit_landed": hit_landed,
            "enemy_alive": self.enemy_hp > 0,
            "player_alive": self.player_hp > 0,
        }

    def _get_state(self) -> np.ndarray:
        is_agg = 1.0 if self.behavior == "aggressive" else 0.0
        is_def = 1.0 if self.behavior == "defensive" else 0.0
        is_sup = 1.0 if self.behavior == "support" else 0.0
        return np.array([
            self.enemy_hp, self.player_hp, self.distance,
            1.0,  # attack_ready
            0.5 + self.rng.random() * 0.3,  # enemy_strength
            0.3 + self.rng.random() * 0.3,  # player_defense
            is_agg, is_def, is_sup,
            min(1.0, self.time),
        ], dtype=np.float32)


# ---------------------------------------------------------------------------
# Training Pipeline
# ---------------------------------------------------------------------------
class TrainingPipeline:
    """
    End-to-end training pipeline with experiment tracking, checkpointing,
    and hyperparameter management.
    """

    def __init__(self, config: Dict) -> None:
        self.config = config
        self.device = torch.device(config["device"])
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create output directories
        self.model_dir = config.get("model_dir", "models")
        self.log_dir = os.path.join(
            config.get("tensorboard_log_dir", "runs"),
            f"dqn_{self.run_id}",
        )
        os.makedirs(self.model_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

        # Initialize model
        self.brain = EnemyBrain(
            lr=config["learning_rate"],
            gamma=config["gamma"],
            epsilon_start=config["epsilon_start"],
            epsilon_end=config["epsilon_end"],
            epsilon_decay=config["epsilon_decay"],
            batch_size=config["batch_size"],
            buffer_capacity=config["buffer_capacity"],
            tau=config["tau"],
            device=config["device"],
        )

        # Learning rate scheduler
        self.scheduler = optim.lr_scheduler.CosineAnnealingLR(
            self.brain.optimizer,
            T_max=config["epochs"],
            eta_min=config["learning_rate"] * 0.01,
        )

        # TensorBoard writer
        self.writer = None
        if HAS_TENSORBOARD:
            self.writer = SummaryWriter(self.log_dir)
            print(f"[train] TensorBoard logs: {self.log_dir}")

        # Environment
        self.env = SimulatedCombatEnv()

        # Save config
        config_path = os.path.join(self.log_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        print(f"[train] Run ID: {self.run_id}")
        print(f"[train] Device: {self.device}")
        print(f"[train] Config: {json.dumps(config, indent=2)}")

    def warmup_buffer(self, num_episodes: int = 50) -> None:
        """Fill replay buffer with random experiences before training."""
        print(f"[train] Warming up replay buffer with {num_episodes} episodes...")
        behaviors = ["aggressive", "defensive", "support"]

        for ep in range(num_episodes):
            behavior = behaviors[ep % len(behaviors)]
            state = self.env.reset(behavior)
            done = False

            while not done:
                action_idx = np.random.randint(NUM_ACTIONS)
                next_state, reward, done, _ = self.env.step(action_idx)
                self.brain.store_experience(
                    state, action_idx, reward, next_state, done,
                )
                state = next_state

        print(f"[train] Buffer size: {len(self.brain.replay_buffer)}")

    def train(self) -> Dict:
        """
        Main training loop. Runs simulated episodes, trains the DQN, and
        logs metrics to TensorBoard.

        Returns:
            Dictionary of final training statistics.
        """
        epochs = self.config["epochs"]
        episodes_per_epoch = self.config["episodes_per_epoch"]
        best_avg_reward = float("-inf")
        patience = self.config.get("early_stop_patience", 30)
        no_improve_count = 0

        print(f"\n[train] Starting training: {epochs} epochs x "
              f"{episodes_per_epoch} episodes/epoch")
        print("=" * 60)

        t_start = time.time()

        for epoch in range(1, epochs + 1):
            epoch_rewards = []
            epoch_losses = []
            epoch_wins = 0
            epoch_kills = 0

            behaviors = ["aggressive", "defensive", "support"]

            for ep in range(episodes_per_epoch):
                behavior = behaviors[ep % len(behaviors)]
                state = self.env.reset(behavior)
                done = False
                episode_reward = 0.0
                steps = 0

                while not done:
                    action_name = self.brain.decide_action(state, behavior)
                    action_idx = ACTIONS.index(action_name)
                    next_state, reward, done, info = self.env.step(action_idx)

                    self.brain.store_experience(
                        state, action_idx, reward, next_state, done,
                    )
                    episode_reward += reward
                    state = next_state
                    steps += 1

                    # Train every 4 steps
                    if self.brain.total_steps % 4 == 0:
                        loss = self.brain.train_step()
                        if loss is not None:
                            epoch_losses.append(loss)

                    # Update target network every 10 steps
                    if self.brain.total_steps % 10 == 0:
                        self.brain.update_target_network()

                epoch_rewards.append(episode_reward)
                if info.get("player_alive") is False:
                    epoch_kills += 1
                if info.get("enemy_alive", True):
                    epoch_wins += 1

            # Step learning rate scheduler
            self.scheduler.step()

            # Compute epoch metrics
            avg_reward = np.mean(epoch_rewards)
            avg_loss = np.mean(epoch_losses) if epoch_losses else 0.0
            win_rate = epoch_wins / episodes_per_epoch
            kill_rate = epoch_kills / episodes_per_epoch
            current_lr = self.scheduler.get_last_lr()[0]

            # Compute gradient norm
            grad_norm = 0.0
            for p in self.brain.policy_net.parameters():
                if p.grad is not None:
                    grad_norm += p.grad.data.norm(2).item() ** 2
            grad_norm = grad_norm ** 0.5

            # Log to TensorBoard
            if self.writer:
                self.writer.add_scalar("reward/avg", avg_reward, epoch)
                self.writer.add_scalar("reward/min", min(epoch_rewards), epoch)
                self.writer.add_scalar("reward/max", max(epoch_rewards), epoch)
                self.writer.add_scalar("loss/train", avg_loss, epoch)
                self.writer.add_scalar("rates/win_rate", win_rate, epoch)
                self.writer.add_scalar("rates/kill_rate", kill_rate, epoch)
                self.writer.add_scalar("exploration/epsilon", self.brain.epsilon, epoch)
                self.writer.add_scalar("training/learning_rate", current_lr, epoch)
                self.writer.add_scalar("training/grad_norm", grad_norm, epoch)
                self.writer.add_scalar("training/buffer_size",
                                       len(self.brain.replay_buffer), epoch)

                # Log Q-value distribution every 10 epochs
                if epoch % 10 == 0:
                    sample_state = torch.randn(1, STATE_DIM, device=self.device)
                    with torch.no_grad():
                        q_vals = self.brain.policy_net(sample_state).squeeze()
                    self.writer.add_histogram("q_values", q_vals, epoch)

            # Console output
            if epoch % 10 == 0 or epoch == 1:
                elapsed = time.time() - t_start
                print(
                    f"  Epoch {epoch:>4d}/{epochs} | "
                    f"reward={avg_reward:+.2f} | "
                    f"loss={avg_loss:.4f} | "
                    f"win={win_rate:.0%} | "
                    f"kill={kill_rate:.0%} | "
                    f"eps={self.brain.epsilon:.3f} | "
                    f"lr={current_lr:.2e} | "
                    f"time={elapsed:.0f}s"
                )

            # Checkpointing (save best model)
            if avg_reward > best_avg_reward:
                best_avg_reward = avg_reward
                no_improve_count = 0
                self._save_checkpoint("best")
            else:
                no_improve_count += 1

            # Periodic checkpoint every 50 epochs
            if epoch % 50 == 0:
                self._save_checkpoint(f"epoch_{epoch}")

            # Early stopping
            if no_improve_count >= patience:
                print(f"\n[train] Early stopping at epoch {epoch} "
                      f"(no improvement for {patience} epochs)")
                break

        total_time = time.time() - t_start
        print("=" * 60)
        print(f"[train] Training complete in {total_time:.1f}s")
        print(f"[train] Best avg reward: {best_avg_reward:.3f}")

        # Save final model
        self._save_checkpoint("final")

        # Export to ONNX for cross-platform deployment
        self._export_onnx()

        if self.writer:
            self.writer.close()

        return {
            "run_id": self.run_id,
            "epochs_completed": epoch,
            "best_avg_reward": best_avg_reward,
            "final_epsilon": self.brain.epsilon,
            "training_steps": self.brain.training_steps,
            "total_time_seconds": total_time,
        }

    def _save_checkpoint(self, tag: str) -> None:
        """Save model checkpoint with metadata."""
        path = os.path.join(self.model_dir, f"enemy_brain_{tag}.pt")
        self.brain.save_model(path)

        # Also save as the default checkpoint
        default_path = os.path.join(self.model_dir, "enemy_brain.pt")
        self.brain.save_model(default_path)

    def _export_onnx(self) -> None:
        """Export the policy network to ONNX format for cross-platform inference."""
        try:
            onnx_path = os.path.join(self.model_dir, "enemy_brain.onnx")
            dummy_input = torch.randn(1, STATE_DIM, device=self.device)

            torch.onnx.export(
                self.brain.policy_net,
                dummy_input,
                onnx_path,
                input_names=["state"],
                output_names=["q_values"],
                dynamic_axes={
                    "state": {0: "batch_size"},
                    "q_values": {0: "batch_size"},
                },
                opset_version=17,
            )
            print(f"[train] ONNX model exported to {onnx_path}")
        except Exception as e:
            print(f"[train] ONNX export failed (non-critical): {e}")


# ---------------------------------------------------------------------------
# Player Model Training
# ---------------------------------------------------------------------------
class PlayerModelTrainer:
    """
    Offline training for the player difficulty model using simulated
    gameplay sessions.
    """

    def __init__(self, config: Dict) -> None:
        self.config = config
        self.device = torch.device(config["device"])
        self.model = PlayerModel().to(self.device)
        self.optimizer = optim.Adam(
            self.model.parameters(), lr=config.get("player_lr", 5e-4)
        )
        self.loss_fn = nn.MSELoss()

    def generate_training_data(self, n_samples: int = 5000) -> tuple:
        """Generate synthetic player performance data for training."""
        rng = np.random.default_rng(42)

        features = rng.random((n_samples, 10)).astype(np.float32)
        # Normalize ranges to realistic values
        features[:, 2] /= 50   # level
        features[:, 3] /= 30   # floor
        features[:, 4] /= 10   # kills_per_min
        features[:, 5] /= 10   # deaths
        features[:, 6] /= 5    # damage_ratio
        features[:, 7] /= 20   # ability_usage
        features[:, 8] /= 5    # potion_usage

        # Generate labels based on feature correlations
        # High HP + high damage ratio + low deaths -> high survival
        survival = (
            0.3 * features[:, 0]   # hp_pct
            + 0.2 * features[:, 6] # damage_ratio
            - 0.3 * features[:, 5] # deaths (negative)
            + 0.1 * features[:, 7] # ability_usage
            + 0.1 * features[:, 4] # kills_per_min
        )
        survival = np.clip(survival + rng.normal(0, 0.05, n_samples), 0, 1)

        # Enjoyment correlates with balanced challenge and ability usage
        enjoyment = (
            0.3 * np.abs(features[:, 6] - 0.5) * -1 + 0.5  # balanced damage
            + 0.2 * features[:, 7]  # ability_usage
            + 0.1 * features[:, 4]  # kills_per_min
            - 0.2 * features[:, 5]  # deaths (negative)
        )
        enjoyment = np.clip(enjoyment + rng.normal(0, 0.05, n_samples), 0, 1)

        labels = np.stack([survival, enjoyment], axis=1).astype(np.float32)
        return features, labels

    def train(self, writer: Optional[object] = None) -> Dict:
        """Train the player model on synthetic data."""
        features, labels = self.generate_training_data()
        n = len(features)
        split = int(0.8 * n)

        train_x = torch.tensor(features[:split], device=self.device)
        train_y = torch.tensor(labels[:split], device=self.device)
        val_x = torch.tensor(features[split:], device=self.device)
        val_y = torch.tensor(labels[split:], device=self.device)

        epochs = self.config.get("player_epochs", 100)
        batch_size = self.config.get("player_batch_size", 64)
        best_val_loss = float("inf")

        print("\n[train] Training Player Model...")

        for epoch in range(1, epochs + 1):
            self.model.train()
            indices = torch.randperm(split, device=self.device)
            epoch_loss = 0.0
            batches = 0

            for i in range(0, split, batch_size):
                batch_idx = indices[i:i + batch_size]
                pred = self.model(train_x[batch_idx])
                loss = self.loss_fn(pred, train_y[batch_idx])

                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()

                epoch_loss += loss.item()
                batches += 1

            # Validation
            self.model.eval()
            with torch.no_grad():
                val_pred = self.model(val_x)
                val_loss = self.loss_fn(val_pred, val_y).item()

            avg_loss = epoch_loss / batches

            if writer and HAS_TENSORBOARD:
                writer.add_scalar("player_model/train_loss", avg_loss, epoch)
                writer.add_scalar("player_model/val_loss", val_loss, epoch)

            if epoch % 20 == 0:
                print(f"  Epoch {epoch:>3d}/{epochs} | "
                      f"train_loss={avg_loss:.4f} | val_loss={val_loss:.4f}")

            if val_loss < best_val_loss:
                best_val_loss = val_loss

        print(f"[train] Player model best val loss: {best_val_loss:.4f}")
        return {"best_val_loss": best_val_loss}


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
def get_config() -> Dict:
    """Build config from CLI args and environment variables."""
    parser = argparse.ArgumentParser(
        description="Sent Below - ML Training Pipeline"
    )
    parser.add_argument("--epochs", type=int,
                        default=int(os.environ.get("EPOCHS", 200)))
    parser.add_argument("--batch-size", type=int,
                        default=int(os.environ.get("BATCH_SIZE", 64)))
    parser.add_argument("--learning-rate", type=float,
                        default=float(os.environ.get("LEARNING_RATE", 1e-3)))
    parser.add_argument("--device", type=str,
                        default=os.environ.get("DEVICE", "cpu"))
    parser.add_argument("--episodes-per-epoch", type=int,
                        default=int(os.environ.get("EPISODES_PER_EPOCH", 20)))
    parser.add_argument("--model-dir", type=str,
                        default=os.environ.get("MODEL_DIR", "models"))
    parser.add_argument("--tensorboard-log-dir", type=str,
                        default=os.environ.get("TENSORBOARD_LOG_DIR", "runs"))
    parser.add_argument("--gamma", type=float, default=0.95)
    parser.add_argument("--epsilon-start", type=float, default=1.0)
    parser.add_argument("--epsilon-end", type=float, default=0.05)
    parser.add_argument("--epsilon-decay", type=float, default=0.9995)
    parser.add_argument("--buffer-capacity", type=int, default=50_000)
    parser.add_argument("--tau", type=float, default=0.01)
    parser.add_argument("--early-stop-patience", type=int, default=30)

    args = parser.parse_args()
    return vars(args)


def _upload_to_aws(model_dir: str, dqn_results: Dict, player_results: Dict):
    """Upload trained artefacts to S3 and register in DynamoDB (if configured)."""
    bucket = os.getenv("MODEL_BUCKET")
    if not bucket:
        print("[aws] MODEL_BUCKET not set — skipping S3 upload")
        return

    try:
        from training.aws_io import upload_file_to_s3, put_model_registry_item
    except ImportError:
        from aws_io import upload_file_to_s3, put_model_registry_item

    version = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    prefix = f"models/enemy-brain/{version}"

    files_to_upload = [
        "enemy_brain.pt",
        "enemy_brain_best.pt",
        "enemy_brain.onnx",
        "player_model.pt",
    ]

    uploaded = 0
    for filename in files_to_upload:
        local_path = os.path.join(model_dir, filename)
        if os.path.exists(local_path):
            s3_key = f"{prefix}/{filename}"
            upload_file_to_s3(local_path, bucket, s3_key)
            print(f"[aws] Uploaded {filename} → s3://{bucket}/{s3_key}")
            uploaded += 1

    if uploaded == 0:
        print("[aws] No model files found to upload")
        return

    # Register in DynamoDB
    registry_table = os.getenv("MODEL_REGISTRY_TABLE")
    if registry_table:
        put_model_registry_item({
            "model_name": "enemy-brain",
            "version": version,
            "s3_bucket": bucket,
            "s3_prefix": prefix,
            "best_avg_reward": dqn_results.get("best_avg_reward", 0.0),
            "epochs_completed": dqn_results.get("epochs_completed", 0),
            "training_steps": dqn_results.get("training_steps", 0),
            "player_val_loss": player_results.get("best_val_loss", 0.0),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "framework": "pytorch",
            "status": "ready",
        })
        print(f"[aws] Registered version {version} in DynamoDB")
    else:
        print("[aws] MODEL_REGISTRY_TABLE not set — skipping registry")


def main():
    config = get_config()

    print("=" * 60)
    print("  Sent Below - ML Training Pipeline")
    print("=" * 60)

    # Phase 1: DQN Enemy AI Training
    pipeline = TrainingPipeline(config)
    pipeline.warmup_buffer(num_episodes=100)
    dqn_results = pipeline.train()

    # Phase 2: Player Model Training
    player_trainer = PlayerModelTrainer(config)
    writer = pipeline.writer if HAS_TENSORBOARD else None
    player_results = player_trainer.train(writer=writer)

    # Save player model
    player_path = os.path.join(config["model_dir"], "player_model.pt")
    torch.save(player_trainer.model.state_dict(), player_path)
    print(f"[train] Player model saved to {player_path}")

    # --- Upload artefacts to S3 and register in DynamoDB ---
    _upload_to_aws(config["model_dir"], dqn_results, player_results)

    # Summary
    print("\n" + "=" * 60)
    print("  Training Summary")
    print("=" * 60)
    print(f"  Run ID:          {dqn_results['run_id']}")
    print(f"  DQN epochs:      {dqn_results['epochs_completed']}")
    print(f"  Best reward:     {dqn_results['best_avg_reward']:.3f}")
    print(f"  Training steps:  {dqn_results['training_steps']}")
    print(f"  Final epsilon:   {dqn_results['final_epsilon']:.4f}")
    print(f"  Player val loss: {player_results['best_val_loss']:.4f}")
    print(f"  Total time:      {dqn_results['total_time_seconds']:.1f}s")
    print(f"  Models saved to: {config['model_dir']}/")
    if HAS_TENSORBOARD:
        print(f"  TensorBoard:     tensorboard --logdir {config['tensorboard_log_dir']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
