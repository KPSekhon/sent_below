"""
Gameplay Data Pipeline - End-to-End ML Data Processing
=======================================================
Structured logging, processing, and dataset creation from live gameplay
sessions. Captures player behavior, enemy decisions, and game outcomes
for offline model training and analysis.

This module implements the data side of the ML lifecycle:
    1. Collection  - Event-driven logging during gameplay
    2. Storage     - Structured JSON-Lines format with timestamps
    3. Processing  - Feature extraction and normalization
    4. Dataset     - PyTorch Dataset/DataLoader for training

Pipeline Architecture:
    Live Game -> EventLogger -> .jsonl files
                                    |
                    GameplayDataset (PyTorch) <- DataProcessor
                                    |
                            DataLoader -> Training Pipeline

Key ML/Data Concepts Demonstrated:
    - Event-driven data collection from real-time systems
    - Structured logging for ML training data
    - Feature engineering from raw gameplay events
    - PyTorch Dataset and DataLoader integration
    - Data normalization and preprocessing
    - Train/validation/test splitting
"""

import os
import json
import time
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from datetime import datetime

import torch
from torch.utils.data import Dataset, DataLoader


# ---------------------------------------------------------------------------
# Event Logger - Collects raw gameplay events
# ---------------------------------------------------------------------------
class EventLogger:
    """
    Captures gameplay events in a structured format for ML training.

    Events are buffered in memory and flushed to disk as JSON-Lines files.
    Each line is a self-contained JSON object with a timestamp, event type,
    and payload — making the format appendable, streamable, and easy to
    process with standard tools.

    Event types:
        combat_step   - Per-frame enemy decision + outcome
        player_action - Player ability/attack usage
        enemy_killed  - Enemy death with context
        player_death  - Player death with context
        room_clear    - Room completion metrics
        floor_clear   - Floor completion summary
        item_drop     - Loot generation event
        difficulty    - DDA adjustment event
    """

    def __init__(self, log_dir: str = "data/logs", buffer_size: int = 500) -> None:
        self.log_dir = log_dir
        self.buffer_size = buffer_size
        self.buffer: List[Dict] = []
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.event_count = 0

        os.makedirs(log_dir, exist_ok=True)

    def log(self, event_type: str, payload: Dict[str, Any],
            game_time: float = 0.0) -> None:
        """Record a gameplay event."""
        event = {
            "timestamp": time.time(),
            "game_time": game_time,
            "session": self.session_id,
            "event": event_type,
            "seq": self.event_count,
            **payload,
        }
        self.buffer.append(event)
        self.event_count += 1

        if len(self.buffer) >= self.buffer_size:
            self.flush()

    def log_combat_step(
        self,
        enemy_state: np.ndarray,
        action: str,
        reward: float,
        next_state: np.ndarray,
        done: bool,
        behavior_type: str,
        game_time: float = 0.0,
    ) -> None:
        """Log a single RL transition from enemy combat."""
        self.log("combat_step", {
            "state": enemy_state.tolist(),
            "action": action,
            "reward": round(reward, 4),
            "next_state": next_state.tolist(),
            "done": done,
            "behavior_type": behavior_type,
        }, game_time)

    def log_player_action(
        self,
        action_type: str,
        ability_name: Optional[str],
        target_x: float,
        target_y: float,
        player_hp_pct: float,
        player_mp_pct: float,
        game_time: float = 0.0,
    ) -> None:
        """Log a player action (attack, ability, movement)."""
        self.log("player_action", {
            "action_type": action_type,
            "ability": ability_name,
            "target": [round(target_x, 1), round(target_y, 1)],
            "hp_pct": round(player_hp_pct, 3),
            "mp_pct": round(player_mp_pct, 3),
        }, game_time)

    def log_difficulty_update(
        self,
        modifier: float,
        predicted_survival: float,
        predicted_enjoyment: float,
        performance_score: float,
        game_time: float = 0.0,
    ) -> None:
        """Log a DDA difficulty adjustment."""
        self.log("difficulty", {
            "modifier": round(modifier, 4),
            "predicted_survival": round(predicted_survival, 4),
            "predicted_enjoyment": round(predicted_enjoyment, 4),
            "performance_score": round(performance_score, 4),
        }, game_time)

    def flush(self) -> None:
        """Write buffered events to disk."""
        if not self.buffer:
            return

        path = os.path.join(self.log_dir, f"session_{self.session_id}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            for event in self.buffer:
                f.write(json.dumps(event) + "\n")

        self.buffer.clear()

    def close(self) -> None:
        """Flush remaining events and finalize the session."""
        self.flush()


# ---------------------------------------------------------------------------
# Data Processor - Feature extraction from raw events
# ---------------------------------------------------------------------------
class DataProcessor:
    """
    Processes raw gameplay event logs into ML-ready feature tensors.

    Handles:
        - Loading JSON-Lines log files
        - Filtering by event type
        - Feature extraction and normalization
        - Sequence windowing for temporal models
        - Train/val/test splitting
    """

    def __init__(self, log_dir: str = "data/logs") -> None:
        self.log_dir = log_dir

    def load_events(
        self,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict]:
        """Load events from all session files, optionally filtered."""
        events = []
        for filename in sorted(os.listdir(self.log_dir)):
            if not filename.endswith(".jsonl"):
                continue
            if session_id and session_id not in filename:
                continue

            path = os.path.join(self.log_dir, filename)
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    event = json.loads(line)
                    if event_type is None or event.get("event") == event_type:
                        events.append(event)

        return events

    def extract_combat_transitions(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Extract (state, action, reward, next_state, done) arrays from
        combat_step events for DQN training.

        Returns:
            Tuple of numpy arrays ready for ReplayBuffer or Dataset.
        """
        events = self.load_events(event_type="combat_step")
        if not events:
            return (np.empty((0, 10)), np.empty(0), np.empty(0),
                    np.empty((0, 10)), np.empty(0))

        action_to_idx = {a: i for i, a in enumerate(
            ["chase", "flee", "attack", "ranged_attack",
             "strafe", "support_cast", "idle"]
        )}

        states, actions, rewards, next_states, dones = [], [], [], [], []
        for e in events:
            states.append(e["state"])
            actions.append(action_to_idx.get(e["action"], 6))
            rewards.append(e["reward"])
            next_states.append(e["next_state"])
            dones.append(float(e["done"]))

        return (
            np.array(states, dtype=np.float32),
            np.array(actions, dtype=np.int64),
            np.array(rewards, dtype=np.float32),
            np.array(next_states, dtype=np.float32),
            np.array(dones, dtype=np.float32),
        )

    def extract_player_sequences(
        self, window_size: int = 20
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extract windowed player action sequences for behavioral analysis.

        Returns:
            features: (N, window_size, feature_dim) array of action windows
            labels:   (N,) array of subsequent player survival outcomes
        """
        events = self.load_events(event_type="player_action")
        if len(events) < window_size + 1:
            return np.empty((0, window_size, 4)), np.empty(0)

        # Feature: [hp_pct, mp_pct, action_encoded, game_time_delta]
        action_map = {"attack": 0, "ability": 1, "move": 2, "interact": 3}
        features_list = []
        for e in events:
            features_list.append([
                e.get("hp_pct", 0.5),
                e.get("mp_pct", 0.5),
                action_map.get(e.get("action_type", "attack"), 0) / 3.0,
                min(1.0, e.get("game_time", 0) / 600.0),
            ])

        features = np.array(features_list, dtype=np.float32)

        # Create sliding windows
        windows = []
        labels = []
        for i in range(len(features) - window_size):
            windows.append(features[i:i + window_size])
            # Label: did HP stay above 30% at end of window?
            labels.append(float(features[i + window_size][0] > 0.3))

        return np.array(windows, dtype=np.float32), np.array(labels, dtype=np.float32)

    def compute_session_summary(self) -> List[Dict]:
        """
        Aggregate per-session statistics for high-level analysis.
        Useful for A/B testing and model comparison.
        """
        events = self.load_events()
        sessions = defaultdict(lambda: {
            "total_events": 0,
            "combat_steps": 0,
            "player_actions": 0,
            "kills": 0,
            "deaths": 0,
            "rooms_cleared": 0,
            "avg_reward": [],
            "difficulty_adjustments": [],
        })

        for e in events:
            sid = e.get("session", "unknown")
            sessions[sid]["total_events"] += 1
            etype = e.get("event")

            if etype == "combat_step":
                sessions[sid]["combat_steps"] += 1
                sessions[sid]["avg_reward"].append(e.get("reward", 0))
            elif etype == "player_action":
                sessions[sid]["player_actions"] += 1
            elif etype == "enemy_killed":
                sessions[sid]["kills"] += 1
            elif etype == "player_death":
                sessions[sid]["deaths"] += 1
            elif etype == "room_clear":
                sessions[sid]["rooms_cleared"] += 1
            elif etype == "difficulty":
                sessions[sid]["difficulty_adjustments"].append(
                    e.get("modifier", 1.0)
                )

        summaries = []
        for sid, stats in sessions.items():
            rewards = stats["avg_reward"]
            diffs = stats["difficulty_adjustments"]
            summaries.append({
                "session_id": sid,
                "total_events": stats["total_events"],
                "combat_steps": stats["combat_steps"],
                "kills": stats["kills"],
                "deaths": stats["deaths"],
                "rooms_cleared": stats["rooms_cleared"],
                "avg_reward": float(np.mean(rewards)) if rewards else 0.0,
                "avg_difficulty": float(np.mean(diffs)) if diffs else 1.0,
            })

        return summaries


# ---------------------------------------------------------------------------
# PyTorch Dataset - For DataLoader integration
# ---------------------------------------------------------------------------
class CombatTransitionDataset(Dataset):
    """
    PyTorch Dataset wrapping combat RL transitions for training.

    Integrates with standard DataLoader for batching, shuffling, and
    multi-worker data loading.
    """

    def __init__(
        self,
        states: np.ndarray,
        actions: np.ndarray,
        rewards: np.ndarray,
        next_states: np.ndarray,
        dones: np.ndarray,
    ) -> None:
        self.states = torch.tensor(states, dtype=torch.float32)
        self.actions = torch.tensor(actions, dtype=torch.long)
        self.rewards = torch.tensor(rewards, dtype=torch.float32)
        self.next_states = torch.tensor(next_states, dtype=torch.float32)
        self.dones = torch.tensor(dones, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.states)

    def __getitem__(self, idx: int) -> Tuple:
        return (
            self.states[idx],
            self.actions[idx],
            self.rewards[idx],
            self.next_states[idx],
            self.dones[idx],
        )

    @classmethod
    def from_logs(cls, log_dir: str = "data/logs") -> "CombatTransitionDataset":
        """Factory: create dataset directly from log files."""
        processor = DataProcessor(log_dir)
        states, actions, rewards, next_states, dones = (
            processor.extract_combat_transitions()
        )
        return cls(states, actions, rewards, next_states, dones)


class PlayerSequenceDataset(Dataset):
    """
    PyTorch Dataset for windowed player action sequences.
    Suitable for LSTM/Transformer-based player modeling.
    """

    def __init__(self, sequences: np.ndarray, labels: np.ndarray) -> None:
        self.sequences = torch.tensor(sequences, dtype=torch.float32)
        self.labels = torch.tensor(labels, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.sequences)

    def __getitem__(self, idx: int) -> Tuple:
        return self.sequences[idx], self.labels[idx]

    @classmethod
    def from_logs(
        cls, log_dir: str = "data/logs", window_size: int = 20
    ) -> "PlayerSequenceDataset":
        """Factory: create dataset directly from log files."""
        processor = DataProcessor(log_dir)
        sequences, labels = processor.extract_player_sequences(window_size)
        return cls(sequences, labels)


def create_data_loaders(
    dataset: Dataset,
    batch_size: int = 64,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """
    Split a dataset into train/val/test and create DataLoaders.

    Args:
        dataset:     Source dataset.
        batch_size:  Batch size for all loaders.
        train_ratio: Fraction of data for training.
        val_ratio:   Fraction for validation (rest is test).

    Returns:
        (train_loader, val_loader, test_loader)
    """
    n = len(dataset)
    train_n = int(n * train_ratio)
    val_n = int(n * val_ratio)
    test_n = n - train_n - val_n

    train_set, val_set, test_set = torch.utils.data.random_split(
        dataset, [train_n, val_n, test_n]
    )

    return (
        DataLoader(train_set, batch_size=batch_size, shuffle=True),
        DataLoader(val_set, batch_size=batch_size, shuffle=False),
        DataLoader(test_set, batch_size=batch_size, shuffle=False),
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Data Pipeline Self-Test ===\n")

    # Test event logging
    logger = EventLogger(log_dir="data/test_logs", buffer_size=10)

    for i in range(25):
        state = np.random.rand(10).astype(np.float32)
        next_state = np.random.rand(10).astype(np.float32)
        logger.log_combat_step(
            state, "attack", 0.5, next_state, False, "aggressive", i * 0.1
        )
        logger.log_player_action(
            "ability", "fireball", 100.0, 200.0, 0.8, 0.6, i * 0.1
        )

    logger.close()
    print(f"Logged {logger.event_count} events")

    # Test data processing
    processor = DataProcessor(log_dir="data/test_logs")
    events = processor.load_events()
    print(f"Loaded {len(events)} events")

    states, actions, rewards, next_states, dones = (
        processor.extract_combat_transitions()
    )
    print(f"Combat transitions: {states.shape}")

    summaries = processor.compute_session_summary()
    print(f"Session summaries: {len(summaries)}")

    # Test PyTorch Dataset
    dataset = CombatTransitionDataset(states, actions, rewards, next_states, dones)
    print(f"Dataset size: {len(dataset)}")

    if len(dataset) >= 10:
        train_loader, val_loader, test_loader = create_data_loaders(
            dataset, batch_size=8
        )
        batch = next(iter(train_loader))
        print(f"Batch shapes: {[b.shape for b in batch]}")

    # Cleanup
    import shutil
    shutil.rmtree("data/test_logs", ignore_errors=True)

    print("\nSelf-test passed!")
