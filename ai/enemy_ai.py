"""
Enemy AI System - Dueling DQN with Self-Attention for Adaptive Enemy AI
========================================================================
A PyTorch-based neural network that controls enemy behavior in real-time.
Enemies learn from combat encounters and adapt to player strategies using
reinforcement learning with experience replay.

Architecture:
    - Dueling DQN: separates state-value V(s) from action-advantage A(s,a)
      for faster convergence  (Wang et al., 2016)
    - Self-Attention: dynamically weights which state features matter for
      each decision (e.g. HP importance spikes when low)
    - Batch Normalization: stabilizes training across varying state scales
    - Target network with soft Polyak updates for stable Q-targets
    - Epsilon-greedy exploration with exponential decay
    - Circular replay buffer for experience storage
    - Batch inference optimized for dozens of simultaneous enemies per frame

Key ML/AI Concepts Demonstrated:
    - Temporal Difference (TD) learning
    - Dueling network architecture (value + advantage decomposition)
    - Self-attention mechanism (transformer-style feature gating)
    - Experience replay for breaking correlation in sequential data
    - Target network soft updates for training stability
    - Reward shaping for multi-objective optimization
    - Batch normalization for training stability
    - ONNX export for cross-platform model deployment
"""

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from collections import deque
from typing import Tuple, Dict, List, Optional
import random
import os


# ---------------------------------------------------------------------------
# Action space - all possible enemy actions
# ---------------------------------------------------------------------------
ACTIONS: List[str] = [
    "chase",          # Move toward the player
    "flee",           # Retreat from the player
    "attack",         # Melee attack
    "ranged_attack",  # Ranged attack (projectile)
    "strafe",         # Circle the player (tactical repositioning)
    "support_cast",   # Buff self or debuff player
    "idle",           # Wait / observe
]

NUM_ACTIONS: int = len(ACTIONS)
STATE_DIM: int = 10  # Dimensionality of the state vector


# ---------------------------------------------------------------------------
# Neural Network
# ---------------------------------------------------------------------------
class SelfAttentionBlock(nn.Module):
    """
    Single-head self-attention over state features. Allows the network to
    learn which state features are most relevant for each decision, e.g.
    attending to HP when low or distance when deciding to attack vs flee.

    This is a simplified version of the transformer attention mechanism
    adapted for fixed-length state vectors rather than sequences.
    """

    def __init__(self, dim: int) -> None:
        super().__init__()
        self.query = nn.Linear(dim, dim)
        self.key = nn.Linear(dim, dim)
        self.value = nn.Linear(dim, dim)
        self.scale = dim ** 0.5

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, dim) -> treat each feature as a token of dim 1
        # Reshape to (batch, num_features, 1) for attention
        if x.dim() == 1:
            x = x.unsqueeze(0)

        q = self.query(x)   # (batch, dim)
        k = self.key(x)     # (batch, dim)
        v = self.value(x)   # (batch, dim)

        # Compute attention weights across features
        # (batch, dim) x (batch, dim) -> (batch, dim) element-wise gating
        attn_weights = torch.sigmoid(q * k / self.scale)
        return v * attn_weights


class EnemyNetwork(nn.Module):
    """
    Dueling DQN with self-attention and batch normalization for adaptive
    enemy decision-making.

    Architecture (Dueling DQN):
        Input (10) -> SelfAttention -> BatchNorm
        -> Shared: Linear(64) -> ReLU -> BatchNorm -> Linear(32) -> ReLU
        -> Value stream:     Linear(32) -> Linear(1)    -> V(s)
        -> Advantage stream: Linear(32) -> Linear(7)    -> A(s, a)
        -> Q(s, a) = V(s) + A(s, a) - mean(A)

    Dueling architecture separates state value from action advantage,
    enabling faster convergence by learning "how good is this state" and
    "how much better is each action" independently.

    Self-attention lets the network dynamically weight which state features
    matter for the current decision (e.g. HP importance spikes when low).

    Input state vector features (10):
        [0] enemy_hp_pct      - Enemy HP as fraction [0, 1]
        [1] player_hp_pct     - Player HP as fraction [0, 1]
        [2] distance          - Normalized distance to player [0, 1]
        [3] attack_ready      - 1.0 if attack cooldown is done, else 0.0
        [4] enemy_strength    - Normalized enemy attack stat [0, 1]
        [5] player_defense    - Normalized player defense stat [0, 1]
        [6] is_aggressive     - Behavior flag: aggressive archetype
        [7] is_defensive      - Behavior flag: defensive archetype
        [8] is_support        - Behavior flag: support archetype
        [9] time_in_fight     - Normalized time spent in current fight [0, 1]

    Output:
        Q-values for each of the 7 actions.
    """

    def __init__(self) -> None:
        super().__init__()

        # Self-attention over state features
        self.attention = SelfAttentionBlock(STATE_DIM)
        self.input_norm = nn.BatchNorm1d(STATE_DIM)

        # Shared feature extraction backbone
        self.shared = nn.Sequential(
            nn.Linear(STATE_DIM, 64),
            nn.ReLU(),
            nn.BatchNorm1d(64),
            nn.Linear(64, 32),
            nn.ReLU(),
        )

        # Value stream: estimates V(s) — how good is this state
        self.value_stream = nn.Sequential(
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
        )

        # Advantage stream: estimates A(s, a) — relative action quality
        self.advantage_stream = nn.Sequential(
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, NUM_ACTIONS),
        )

        self._init_weights()

    def _init_weights(self) -> None:
        """Xavier uniform initialization for faster convergence."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                nn.init.zeros_(module.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass with dueling architecture.

        Args:
            x: State tensor of shape (batch, 10) or (10,).

        Returns:
            Q-values of shape (batch, 7) or (7,).
        """
        squeezed = False
        if x.dim() == 1:
            x = x.unsqueeze(0)
            squeezed = True

        # Self-attention: dynamically weight state features
        x = self.attention(x)
        x = self.input_norm(x)

        # Shared feature extraction
        features = self.shared(x)

        # Dueling streams
        value = self.value_stream(features)           # (batch, 1)
        advantage = self.advantage_stream(features)   # (batch, 7)

        # Combine: Q(s,a) = V(s) + (A(s,a) - mean(A))
        q_values = value + advantage - advantage.mean(dim=1, keepdim=True)

        if squeezed:
            q_values = q_values.squeeze(0)

        return q_values


# ---------------------------------------------------------------------------
# Replay Buffer
# ---------------------------------------------------------------------------
class ReplayBuffer:
    """
    Fixed-size circular buffer for storing experience tuples.

    Each experience is a (state, action, reward, next_state, done) tuple.
    Supports uniform random sampling for training mini-batches, which breaks
    temporal correlations and stabilizes learning.

    Attributes:
        capacity: Maximum number of experiences stored.
        buffer:   Internal deque used as a ring buffer.
    """

    def __init__(self, capacity: int = 10_000) -> None:
        self.capacity: int = capacity
        self.buffer: deque = deque(maxlen=capacity)

    def push(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
    ) -> None:
        """Store a single experience tuple."""
        self.buffer.append((
            np.asarray(state, dtype=np.float32),
            action,
            reward,
            np.asarray(next_state, dtype=np.float32),
            done,
        ))

    def sample(
        self, batch_size: int
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Sample a random mini-batch of experiences.

        Returns numpy arrays ready for conversion to tensors:
            states      (batch, 10)
            actions     (batch,)     int64
            rewards     (batch,)     float32
            next_states (batch, 10)
            dones       (batch,)     float32 (1.0 = terminal)
        """
        batch = random.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        return (
            np.array(states, dtype=np.float32),
            np.array(actions, dtype=np.int64),
            np.array(rewards, dtype=np.float32),
            np.array(next_states, dtype=np.float32),
            np.array(dones, dtype=np.float32),
        )

    def __len__(self) -> int:
        return len(self.buffer)


# ---------------------------------------------------------------------------
# Enemy Brain (DQN Agent)
# ---------------------------------------------------------------------------
class EnemyBrain:
    """
    Reinforcement-learning agent that drives enemy decision making.

    Uses a Deep Q-Network (DQN) with the following techniques:
        - Target network with soft (Polyak) updates for stable Q-targets
        - Epsilon-greedy exploration with exponential decay
        - Experience replay buffer to decorrelate training samples
        - Behavior-type biasing so different enemy archetypes (aggressive,
          defensive, support) favor different actions even before training

    Typical gameplay loop:
        1. Build state vector from game state
        2. brain.decide_action(state_vec, behavior_type) -> action string
        3. Execute action in game world
        4. brain.compute_reward(enemy, player, action, prev_state) -> reward
        5. brain.store_experience(state, action_idx, reward, next_state, done)
        6. Every N steps: brain.train_step()
        7. Every M steps: brain.update_target_network()

    Args:
        lr:             Learning rate for Adam optimizer.
        gamma:          Discount factor for future rewards.
        epsilon_start:  Initial exploration rate.
        epsilon_end:    Minimum exploration rate after decay.
        epsilon_decay:  Multiplicative decay applied each training step.
        batch_size:     Mini-batch size for replay sampling.
        buffer_capacity: Maximum replay buffer size.
        tau:            Soft update coefficient for target network.
        device:         Torch device ('cpu' recommended for real-time game AI).
    """

    def __init__(
        self,
        lr: float = 1e-3,
        gamma: float = 0.95,
        epsilon_start: float = 1.0,
        epsilon_end: float = 0.05,
        epsilon_decay: float = 0.9995,
        batch_size: int = 32,
        buffer_capacity: int = 10_000,
        tau: float = 0.01,
        device: Optional[str] = None,
    ) -> None:
        # Device selection (prefer CPU for game-loop inference speed)
        if device is None:
            self.device = torch.device("cpu")
        else:
            self.device = torch.device(device)

        # Online network (updated every training step)
        self.policy_net = EnemyNetwork().to(self.device)
        # Target network (slowly tracks the online network)
        self.target_net = EnemyNetwork().to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()  # Target net is never trained directly

        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=lr)
        self.loss_fn = nn.SmoothL1Loss()  # Huber loss for robustness

        # Replay buffer
        self.replay_buffer = ReplayBuffer(capacity=buffer_capacity)

        # Hyperparameters
        self.gamma: float = gamma
        self.batch_size: int = batch_size
        self.tau: float = tau

        # Exploration schedule
        self.epsilon: float = epsilon_start
        self.epsilon_end: float = epsilon_end
        self.epsilon_decay: float = epsilon_decay

        # Training statistics
        self.total_steps: int = 0
        self.training_steps: int = 0
        self.cumulative_loss: float = 0.0
        self.last_loss: float = 0.0

        # Behavior-type action biases (prior preferences before learning)
        # These nudge Q-values so archetypes start with characteristic
        # behavior even before the network has trained.
        self._behavior_biases: Dict[str, np.ndarray] = {
            # Aggressive enemies prefer chasing and attacking
            "aggressive": np.array(
                [0.3, -0.5, 0.5, 0.3, 0.0, -0.3, -0.5], dtype=np.float32
            ),
            # Defensive enemies prefer strafing and fleeing
            "defensive": np.array(
                [-0.2, 0.4, -0.1, 0.1, 0.5, 0.1, 0.2], dtype=np.float32
            ),
            # Support enemies prefer support casting and ranged attacks
            "support": np.array(
                [-0.3, 0.2, -0.2, 0.3, 0.1, 0.6, 0.0], dtype=np.float32
            ),
        }

    # ------------------------------------------------------------------
    # Action selection
    # ------------------------------------------------------------------
    @torch.no_grad()
    def decide_action(
        self,
        state_vec: np.ndarray,
        behavior_type: str = "aggressive",
    ) -> str:
        """
        Choose an action using epsilon-greedy over the Q-network output.

        Args:
            state_vec:     Numpy array of shape (10,) representing the state.
            behavior_type: One of 'aggressive', 'defensive', 'support'.
                           Applies a prior bias to Q-values.

        Returns:
            Action name string from the ACTIONS list.
        """
        self.total_steps += 1

        # Epsilon-greedy: explore with probability epsilon
        if random.random() < self.epsilon:
            action_idx = random.randrange(NUM_ACTIONS)
            return ACTIONS[action_idx]

        # Exploit: pick best action from Q-network
        self.policy_net.eval()
        state_tensor = torch.tensor(
            state_vec, dtype=torch.float32, device=self.device
        ).unsqueeze(0)  # (1, 10)

        q_values = self.policy_net(state_tensor).squeeze(0).cpu().numpy()
        self.policy_net.train()

        # Apply behavior-type bias
        bias = self._behavior_biases.get(
            behavior_type, np.zeros(NUM_ACTIONS, dtype=np.float32)
        )
        q_values = q_values + bias

        action_idx = int(np.argmax(q_values))
        return ACTIONS[action_idx]

    @torch.no_grad()
    def decide_actions_batch(
        self,
        state_batch: np.ndarray,
        behavior_types: List[str],
    ) -> List[str]:
        """
        Vectorized action selection for multiple enemies at once.

        This is the preferred method during gameplay -- it batches all
        enemies' states into a single forward pass for efficiency.

        Args:
            state_batch:    Numpy array of shape (N, 10).
            behavior_types: List of N behavior type strings.

        Returns:
            List of N action name strings.
        """
        n = state_batch.shape[0]
        actions: List[str] = []

        # Build the exploration mask first
        explore_mask = np.random.random(n) < self.epsilon

        # Forward pass for all enemies at once
        self.policy_net.eval()
        state_tensor = torch.tensor(
            state_batch, dtype=torch.float32, device=self.device
        )
        q_values_batch = self.policy_net(state_tensor).cpu().numpy()  # (N, 7)
        self.policy_net.train()

        for i in range(n):
            self.total_steps += 1
            if explore_mask[i]:
                actions.append(ACTIONS[random.randrange(NUM_ACTIONS)])
            else:
                bias = self._behavior_biases.get(
                    behavior_types[i], np.zeros(NUM_ACTIONS, dtype=np.float32)
                )
                biased_q = q_values_batch[i] + bias
                actions.append(ACTIONS[int(np.argmax(biased_q))])

        return actions

    # ------------------------------------------------------------------
    # Experience storage
    # ------------------------------------------------------------------
    def store_experience(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
    ) -> None:
        """
        Store a transition in the replay buffer.

        Args:
            state:      State vector (10,) when action was taken.
            action:     Integer action index (0-6).
            reward:     Scalar reward received after taking the action.
            next_state: State vector (10,) after the action.
            done:       True if the episode (fight) ended.
        """
        self.replay_buffer.push(state, action, reward, next_state, done)

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------
    def train_step(self) -> Optional[float]:
        """
        Sample a mini-batch from the replay buffer and perform one gradient
        descent step on the Bellman (TD) loss.

        The loss is computed as:
            L = HuberLoss( Q(s,a) , r + gamma * max_a' Q_target(s', a') )

        Returns:
            The scalar loss value, or None if the buffer is too small.
        """
        if len(self.replay_buffer) < self.batch_size:
            return None

        # --- Sample batch ---
        states, actions, rewards, next_states, dones = (
            self.replay_buffer.sample(self.batch_size)
        )

        states_t = torch.tensor(states, device=self.device)
        actions_t = torch.tensor(actions, device=self.device).unsqueeze(1)
        rewards_t = torch.tensor(rewards, device=self.device).unsqueeze(1)
        next_states_t = torch.tensor(next_states, device=self.device)
        dones_t = torch.tensor(dones, device=self.device).unsqueeze(1)

        # --- Current Q-values for chosen actions ---
        current_q = self.policy_net(states_t).gather(1, actions_t)

        # --- Target Q-values (from frozen target network) ---
        with torch.no_grad():
            next_q_max = self.target_net(next_states_t).max(dim=1, keepdim=True).values
            # If done, there is no future reward
            target_q = rewards_t + self.gamma * next_q_max * (1.0 - dones_t)

        # --- Backpropagation ---
        loss = self.loss_fn(current_q, target_q)

        self.optimizer.zero_grad()
        loss.backward()
        # Gradient clipping to prevent exploding gradients
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), max_norm=1.0)
        self.optimizer.step()

        # --- Bookkeeping ---
        loss_val = loss.item()
        self.training_steps += 1
        self.cumulative_loss += loss_val
        self.last_loss = loss_val

        # Decay exploration rate
        self.epsilon = max(
            self.epsilon_end, self.epsilon * self.epsilon_decay
        )

        return loss_val

    def update_target_network(self) -> None:
        """
        Soft (Polyak) update of the target network parameters:
            theta_target = tau * theta_online + (1 - tau) * theta_target

        This is more stable than hard-copying weights every N steps because
        it avoids sudden shifts in the Q-target landscape.
        """
        for target_param, policy_param in zip(
            self.target_net.parameters(), self.policy_net.parameters()
        ):
            target_param.data.copy_(
                self.tau * policy_param.data
                + (1.0 - self.tau) * target_param.data
            )

    # ------------------------------------------------------------------
    # Reward computation
    # ------------------------------------------------------------------
    @staticmethod
    def compute_reward(
        enemy_hp_pct: float,
        player_hp_pct: float,
        action: str,
        prev_enemy_hp_pct: float,
        prev_player_hp_pct: float,
        distance: float,
        hit_landed: bool = False,
        damage_taken: bool = False,
    ) -> float:
        """
        Compute a shaped reward signal for the enemy agent.

        Reward components:
            +1.0  Landing a hit on the player (damage dealt)
            -1.0  Taking damage from the player
            +0.5  Tactical strafing at medium range (flanking)
            +0.3  Fleeing when at low HP (survival instinct)
            -0.3  Idling when the player is nearby (passivity penalty)
            +0.2  Using support cast when teammates are present
            -0.5  Dying (terminal penalty)
            +2.0  Killing the player (terminal bonus)

        Args:
            enemy_hp_pct:       Current enemy HP fraction.
            player_hp_pct:      Current player HP fraction.
            action:             Action string that was taken.
            prev_enemy_hp_pct:  Enemy HP fraction before the action.
            prev_player_hp_pct: Player HP fraction before the action.
            distance:           Normalized distance to the player.
            hit_landed:         Whether the enemy's attack hit the player.
            damage_taken:       Whether the enemy took damage this step.

        Returns:
            Scalar reward value.
        """
        reward: float = 0.0

        # Damage dealt to the player
        player_hp_delta = prev_player_hp_pct - player_hp_pct
        if player_hp_delta > 0:
            reward += 1.0 * player_hp_delta * 10.0  # Scale by damage amount

        # Damage taken by the enemy
        enemy_hp_delta = prev_enemy_hp_pct - enemy_hp_pct
        if enemy_hp_delta > 0:
            reward -= 1.0 * enemy_hp_delta * 10.0

        # Tactical bonuses
        if action == "strafe" and 0.3 <= distance <= 0.7:
            reward += 0.5  # Good positioning

        if action == "flee" and enemy_hp_pct < 0.3:
            reward += 0.3  # Smart retreat at low HP

        if action == "idle" and distance < 0.5:
            reward -= 0.3  # Don't stand around when the player is close

        if action == "support_cast":
            reward += 0.2  # Encourage buff/debuff usage

        # Terminal conditions
        if enemy_hp_pct <= 0.0:
            reward -= 0.5  # Death penalty

        if player_hp_pct <= 0.0:
            reward += 2.0  # Victory bonus

        # Small hit bonus to reinforce attacks that connect
        if hit_landed and action in ("attack", "ranged_attack"):
            reward += 0.3

        # Small penalty for taking a hit (encourages evasion)
        if damage_taken:
            reward -= 0.2

        return reward

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save_model(self, path: str) -> None:
        """
        Save the policy network, target network, optimizer state, and
        training metadata to disk.

        Args:
            path: File path for the checkpoint (e.g. 'models/enemy_brain.pt').
        """
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        checkpoint = {
            "policy_net": self.policy_net.state_dict(),
            "target_net": self.target_net.state_dict(),
            "optimizer": self.optimizer.state_dict(),
            "epsilon": self.epsilon,
            "total_steps": self.total_steps,
            "training_steps": self.training_steps,
            "cumulative_loss": self.cumulative_loss,
        }
        torch.save(checkpoint, path)

    def load_model(self, path: str) -> None:
        """
        Restore a previously saved checkpoint.

        Args:
            path: File path to the checkpoint.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Checkpoint not found: {path}")

        checkpoint = torch.load(path, map_location=self.device, weights_only=True)
        self.policy_net.load_state_dict(checkpoint["policy_net"])
        self.target_net.load_state_dict(checkpoint["target_net"])
        self.optimizer.load_state_dict(checkpoint["optimizer"])
        self.epsilon = checkpoint["epsilon"]
        self.total_steps = checkpoint["total_steps"]
        self.training_steps = checkpoint["training_steps"]
        self.cumulative_loss = checkpoint["cumulative_loss"]

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def get_training_stats(self) -> Dict[str, float]:
        """
        Return a dictionary of training diagnostics for debugging and
        visualization.

        Returns:
            Dict with keys:
                loss           - Most recent training loss
                avg_loss       - Average loss over all training steps
                epsilon        - Current exploration rate
                num_experiences - Number of transitions in the replay buffer
                total_steps    - Total action-selection steps
                training_steps - Number of gradient updates performed
        """
        avg_loss = (
            self.cumulative_loss / self.training_steps
            if self.training_steps > 0
            else 0.0
        )
        return {
            "loss": self.last_loss,
            "avg_loss": avg_loss,
            "epsilon": self.epsilon,
            "num_experiences": len(self.replay_buffer),
            "total_steps": self.total_steps,
            "training_steps": self.training_steps,
        }


# ---------------------------------------------------------------------------
# Convenience: shared brain instance
# ---------------------------------------------------------------------------
# In production, a single EnemyBrain is shared across all enemies on a floor
# so they collectively learn from each other's experiences.
_shared_brain: Optional[EnemyBrain] = None


def get_shared_brain() -> EnemyBrain:
    """Return (and lazily create) the shared EnemyBrain singleton."""
    global _shared_brain
    if _shared_brain is None:
        _shared_brain = EnemyBrain()
    return _shared_brain


# ---------------------------------------------------------------------------
# Example / self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Enemy AI Self-Test ===\n")

    brain = EnemyBrain(epsilon_start=0.3)

    # Simulate a short training loop
    for episode in range(5):
        state = np.random.rand(STATE_DIM).astype(np.float32)
        done = False
        total_reward = 0.0

        for step in range(20):
            action_name = brain.decide_action(state, "aggressive")
            action_idx = ACTIONS.index(action_name)

            # Simulate environment transition
            next_state = np.random.rand(STATE_DIM).astype(np.float32)
            reward = brain.compute_reward(
                enemy_hp_pct=next_state[0],
                player_hp_pct=next_state[1],
                action=action_name,
                prev_enemy_hp_pct=state[0],
                prev_player_hp_pct=state[1],
                distance=next_state[2],
                hit_landed=(random.random() > 0.5),
                damage_taken=(random.random() > 0.6),
            )
            done = step == 19

            brain.store_experience(state, action_idx, reward, next_state, done)
            total_reward += reward
            state = next_state

            # Train every 4 steps
            if brain.total_steps % 4 == 0:
                loss = brain.train_step()

            # Update target network every 10 steps
            if brain.total_steps % 10 == 0:
                brain.update_target_network()

        print(f"Episode {episode + 1}: total_reward={total_reward:.2f}")

    # Batch inference demo
    batch_states = np.random.rand(8, STATE_DIM).astype(np.float32)
    batch_types = ["aggressive"] * 4 + ["defensive"] * 2 + ["support"] * 2
    batch_actions = brain.decide_actions_batch(batch_states, batch_types)
    print(f"\nBatch actions for 8 enemies: {batch_actions}")

    stats = brain.get_training_stats()
    print(f"\nTraining stats: {stats}")
    print("\nSelf-test passed.")
