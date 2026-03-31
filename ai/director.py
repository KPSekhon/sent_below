"""
AI Director - Dynamic Difficulty Adjustment and Content Recommendation
======================================================================
A neural-network-powered system that monitors player performance in
real-time and adjusts the game experience to keep players in the "flow"
zone: challenged but not frustrated.

Components:
    PlayerModel          - PyTorch network predicting survival and enjoyment
    PerformanceTracker   - Rolling window metrics over gameplay events
    DifficultyAdjuster   - PID-style controller driven by model predictions
    ContentRecommender   - Utility-based item/room recommendation engine
    AIDirector           - Master controller orchestrating all subsystems

Key ML/AI Concepts Demonstrated:
    - Player modeling with neural networks
    - Dynamic Difficulty Adjustment (DDA) -- a standard game AI technique
    - Utility-based recommendation with softmax scoring
    - Online learning from streaming gameplay data
"""

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from collections import deque
from typing import Dict, List, Optional, Tuple, Any
import math


# ---------------------------------------------------------------------------
# Player Model (neural network)
# ---------------------------------------------------------------------------
class PlayerModel(nn.Module):
    """
    Neural network that predicts player success probability and enjoyment
    given current game state metrics.

    Input features (10):
        [0] hp_pct              - Player HP fraction [0, 1]
        [1] mp_pct              - Player MP/mana fraction [0, 1]
        [2] level               - Player level (normalized by max_level)
        [3] floor               - Current dungeon floor (normalized)
        [4] kills_per_min       - Combat efficiency metric [0, 1]
        [5] deaths              - Deaths this floor (normalized)
        [6] damage_ratio        - Damage dealt / damage taken [0, 1] clamped
        [7] ability_usage_rate  - Fraction of abilities actively used [0, 1]
        [8] potion_usage_rate   - Potions consumed per minute (normalized)
        [9] clear_time_ratio    - Actual clear time / expected time [0, 1]

    Output (2):
        [0] predicted_survival_prob  - P(player survives current floor)
        [1] predicted_enjoyment      - Estimated engagement score [0, 1]

    Architecture:
        10 -> 32 -> ReLU -> 16 -> ReLU -> 2 -> Sigmoid
    """

    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(10, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 2),
            nn.Sigmoid(),  # Output in [0, 1]
        )
        self._init_weights()

    def _init_weights(self) -> None:
        for layer in self.net:
            if isinstance(layer, nn.Linear):
                nn.init.xavier_uniform_(layer.weight)
                nn.init.zeros_(layer.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: Tensor of shape (batch, 10) or (10,).
        Returns:
            Tensor of shape (batch, 2) or (2,) with [survival_prob, enjoyment].
        """
        return self.net(x)


# ---------------------------------------------------------------------------
# Performance Tracker
# ---------------------------------------------------------------------------
class PerformanceTracker:
    """
    Tracks player performance metrics over sliding time windows.

    Records discrete gameplay events and computes rolling aggregates that
    feed into the PlayerModel and DifficultyAdjuster.

    Supported event types:
        'kill'         - Enemy killed.        data: {'enemy_type': str}
        'death'        - Player died.         data: {}
        'damage_dealt' - Damage to enemy.     data: {'amount': float}
        'damage_taken' - Damage from enemy.   data: {'amount': float}
        'ability_used' - Ability activated.   data: {'ability': str}
        'potion_used'  - Potion consumed.     data: {'potion_type': str}
        'room_cleared' - Room completed.      data: {'room_type': str, 'hp_pct': float, 'time': float}
        'floor_start'  - Entered new floor.   data: {'floor': int}
    """

    def __init__(self, window_size: float = 60.0, max_events: int = 1000) -> None:
        self.events: deque = deque(maxlen=max_events)
        self.floor_stats: Dict[int, Dict[str, Any]] = {}
        self.window_size: float = window_size  # seconds

        # Running counters (reset per floor)
        self.total_kills: int = 0
        self.total_deaths: int = 0
        self.total_damage_dealt: float = 0.0
        self.total_damage_taken: float = 0.0
        self.abilities_used: int = 0
        self.potions_used: int = 0
        self.rooms_cleared: int = 0
        self.floor_start_time: float = 0.0
        self.current_floor: int = 0

    def record_event(
        self, event_type: str, data: Dict[str, Any], timestamp: float
    ) -> None:
        """
        Record a gameplay event.

        Args:
            event_type: One of the supported event type strings.
            data:       Event-specific payload dictionary.
            timestamp:  Game time in seconds when the event occurred.
        """
        self.events.append((event_type, data, timestamp))

        # Update running counters
        if event_type == "kill":
            self.total_kills += 1
        elif event_type == "death":
            self.total_deaths += 1
        elif event_type == "damage_dealt":
            self.total_damage_dealt += data.get("amount", 0.0)
        elif event_type == "damage_taken":
            self.total_damage_taken += data.get("amount", 0.0)
        elif event_type == "ability_used":
            self.abilities_used += 1
        elif event_type == "potion_used":
            self.potions_used += 1
        elif event_type == "room_cleared":
            self.rooms_cleared += 1
            # Store per-floor room clear data
            floor = self.current_floor
            if floor not in self.floor_stats:
                self.floor_stats[floor] = {
                    "rooms_cleared": 0,
                    "avg_hp_at_clear": 0.0,
                    "total_time": 0.0,
                    "room_types_seen": [],
                }
            fs = self.floor_stats[floor]
            fs["rooms_cleared"] += 1
            hp_pct = data.get("hp_pct", 1.0)
            # Incremental mean update
            n = fs["rooms_cleared"]
            fs["avg_hp_at_clear"] = (
                fs["avg_hp_at_clear"] * (n - 1) + hp_pct
            ) / n
            fs["total_time"] += data.get("time", 0.0)
            fs["room_types_seen"].append(data.get("room_type", "unknown"))
        elif event_type == "floor_start":
            self.current_floor = data.get("floor", 0)
            self.floor_start_time = timestamp
            # Reset per-floor counters
            self.total_kills = 0
            self.total_deaths = 0
            self.total_damage_dealt = 0.0
            self.total_damage_taken = 0.0
            self.abilities_used = 0
            self.potions_used = 0
            self.rooms_cleared = 0

    def get_metrics(self, current_time: float) -> Dict[str, float]:
        """
        Compute rolling metrics over the recent time window.

        Args:
            current_time: Current game time in seconds.

        Returns:
            Dictionary of performance indicators.
        """
        window_start = current_time - self.window_size

        # Filter events within the window
        window_kills = 0
        window_deaths = 0
        window_damage_dealt = 0.0
        window_damage_taken = 0.0
        window_abilities = 0
        window_potions = 0

        for event_type, data, ts in self.events:
            if ts < window_start:
                continue
            if event_type == "kill":
                window_kills += 1
            elif event_type == "death":
                window_deaths += 1
            elif event_type == "damage_dealt":
                window_damage_dealt += data.get("amount", 0.0)
            elif event_type == "damage_taken":
                window_damage_taken += data.get("amount", 0.0)
            elif event_type == "ability_used":
                window_abilities += 1
            elif event_type == "potion_used":
                window_potions += 1

        elapsed = max(current_time - self.floor_start_time, 1.0)
        window_elapsed = min(elapsed, self.window_size)
        minutes = max(window_elapsed / 60.0, 1.0 / 60.0)

        damage_ratio = (
            window_damage_dealt / max(window_damage_taken, 1.0)
        )

        return {
            "kills_per_min": window_kills / minutes,
            "deaths_in_window": float(window_deaths),
            "damage_dealt": window_damage_dealt,
            "damage_taken": window_damage_taken,
            "damage_ratio": min(damage_ratio, 5.0),  # Cap at 5x
            "abilities_per_min": window_abilities / minutes,
            "potions_per_min": window_potions / minutes,
            "total_kills": float(self.total_kills),
            "total_deaths": float(self.total_deaths),
            "rooms_cleared": float(self.rooms_cleared),
            "elapsed_time": elapsed,
        }

    def get_performance_score(self) -> float:
        """
        Compute a scalar performance score in [0, 1].

        0.0 = struggling badly (many deaths, low damage, high potion use)
        1.0 = dominating (no deaths, high damage ratio, minimal resource use)

        The score blends multiple signals with hand-tuned weights.
        """
        # Damage ratio component (capped at 3.0 for normalization)
        if self.total_damage_taken > 0:
            dr = min(self.total_damage_dealt / self.total_damage_taken, 3.0) / 3.0
        else:
            dr = 1.0 if self.total_damage_dealt > 0 else 0.5

        # Death penalty (each death reduces score)
        death_factor = max(0.0, 1.0 - self.total_deaths * 0.2)

        # Efficiency: rooms cleared relative to time spent
        elapsed_minutes = max(
            (self.rooms_cleared * 30.0) if self.rooms_cleared > 0 else 1.0,
            1.0,
        )
        # Rough heuristic: ~1 room/30s is average pace
        pace_factor = min(self.rooms_cleared / max(elapsed_minutes / 30.0, 1.0), 1.5) / 1.5

        # Potion usage: heavy use suggests struggling
        potion_factor = max(0.0, 1.0 - self.potions_used * 0.05)

        # Weighted combination
        score = (
            0.35 * dr
            + 0.25 * death_factor
            + 0.20 * pace_factor
            + 0.20 * potion_factor
        )
        return float(np.clip(score, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Difficulty Adjuster
# ---------------------------------------------------------------------------
class DifficultyAdjuster:
    """
    Uses the PlayerModel to continuously adjust game difficulty so the
    player stays in the "flow" zone.

    The adjuster maintains a difficulty_modifier (default 1.0) that is
    applied as a multiplier to enemy stats (HP, damage, spawn rate).
    Values < 1.0 make the game easier; values > 1.0 make it harder.

    The adjustment loop:
        1. Build a feature vector from player stats and tracker metrics.
        2. Feed it through the PlayerModel to predict survival probability.
        3. Compare predicted survival to the target (default 60%).
        4. Adjust difficulty_modifier smoothly toward the target.

    The model is trained online using (feature_vector, actual_outcome)
    pairs collected at the end of each floor.

    Attributes:
        model:              PlayerModel neural network.
        tracker:            PerformanceTracker instance.
        target_difficulty:  Desired survival probability (0.6 = 60%).
        difficulty_modifier: Current multiplier applied to enemy stats.
        adjustment_rate:    How quickly the modifier changes per update.
        history:            List of (timestamp, modifier, predicted_survival) tuples.
    """

    def __init__(self) -> None:
        self.model = PlayerModel()
        self.optimizer = optim.Adam(self.model.parameters(), lr=5e-4)
        self.loss_fn = nn.MSELoss()
        self.tracker = PerformanceTracker()

        self.target_difficulty: float = 0.6
        self.difficulty_modifier: float = 1.0
        self.adjustment_rate: float = 0.05
        self.min_modifier: float = 0.5
        self.max_modifier: float = 2.0

        self.history: List[Dict[str, float]] = []

        # Training data: collected (input_vec, actual_outcome) pairs
        self._training_inputs: List[np.ndarray] = []
        self._training_targets: List[np.ndarray] = []
        self._max_training_samples: int = 500

    def _build_feature_vector(
        self, player_stats: Dict[str, float], floor_num: int
    ) -> np.ndarray:
        """
        Construct the 10-dimensional feature vector for the PlayerModel.

        Args:
            player_stats: Dictionary with keys like 'hp_pct', 'mp_pct', etc.
            floor_num:    Current dungeon floor number.

        Returns:
            Numpy array of shape (10,) with normalized features.
        """
        perf = self.tracker.get_performance_score()
        metrics = self.tracker.get_metrics(
            player_stats.get("game_time", 0.0)
        )

        max_level = 50.0
        max_floor = 30.0

        vec = np.array([
            player_stats.get("hp_pct", 1.0),
            player_stats.get("mp_pct", 1.0),
            min(player_stats.get("level", 1) / max_level, 1.0),
            min(floor_num / max_floor, 1.0),
            min(metrics["kills_per_min"] / 10.0, 1.0),
            min(metrics["total_deaths"] / 10.0, 1.0),
            min(metrics["damage_ratio"] / 5.0, 1.0),
            min(metrics["abilities_per_min"] / 20.0, 1.0),
            min(metrics["potions_per_min"] / 5.0, 1.0),
            min(
                metrics["elapsed_time"]
                / max(metrics.get("expected_clear_time", 300.0), 1.0),
                1.0,
            ),
        ], dtype=np.float32)
        return vec

    @torch.no_grad()
    def update(
        self,
        player_stats: Dict[str, float],
        floor_num: int,
        dt: float,
    ) -> None:
        """
        Run one DDA update cycle.

        Predicts the player's survival probability, compares it to the
        target, and smoothly adjusts the difficulty modifier.

        Args:
            player_stats: Current player statistics dictionary.
            floor_num:    Current dungeon floor.
            dt:           Time delta since last update (seconds).
        """
        feature_vec = self._build_feature_vector(player_stats, floor_num)
        input_tensor = torch.tensor(feature_vec, dtype=torch.float32).unsqueeze(0)
        prediction = self.model(input_tensor).squeeze(0).numpy()

        predicted_survival = float(prediction[0])
        predicted_enjoyment = float(prediction[1])

        # PID-style adjustment:
        # If predicted survival > target -> make it harder (increase modifier)
        # If predicted survival < target -> make it easier (decrease modifier)
        error = predicted_survival - self.target_difficulty
        adjustment = error * self.adjustment_rate

        # Smooth the adjustment with the enjoyment signal:
        # If enjoyment is low, bias toward making things easier
        enjoyment_bias = (predicted_enjoyment - 0.5) * 0.02
        adjustment += enjoyment_bias

        self.difficulty_modifier = float(np.clip(
            self.difficulty_modifier + adjustment,
            self.min_modifier,
            self.max_modifier,
        ))

        self.history.append({
            "predicted_survival": predicted_survival,
            "predicted_enjoyment": predicted_enjoyment,
            "difficulty_modifier": self.difficulty_modifier,
            "performance_score": self.tracker.get_performance_score(),
        })

    def record_outcome(
        self,
        player_stats: Dict[str, float],
        floor_num: int,
        survived: bool,
        enjoyment_proxy: float,
    ) -> None:
        """
        Record an actual floor outcome for online training of the model.

        Args:
            player_stats:     Stats at the time of the outcome.
            floor_num:        Floor number.
            survived:         Whether the player survived the floor.
            enjoyment_proxy:  Heuristic enjoyment score [0, 1].
                              (e.g. based on time spent, abilities used, etc.)
        """
        feature_vec = self._build_feature_vector(player_stats, floor_num)
        target = np.array(
            [1.0 if survived else 0.0, enjoyment_proxy], dtype=np.float32
        )
        self._training_inputs.append(feature_vec)
        self._training_targets.append(target)

        # Keep buffer bounded
        if len(self._training_inputs) > self._max_training_samples:
            self._training_inputs.pop(0)
            self._training_targets.pop(0)

        # Train on collected data if we have enough
        if len(self._training_inputs) >= 10:
            self._train_model()

    def _train_model(self) -> None:
        """
        Train the PlayerModel on all collected (feature, outcome) pairs.
        Uses a single epoch over all data, which is fine for the small
        dataset sizes we accumulate during a play session.
        """
        inputs = torch.tensor(
            np.array(self._training_inputs), dtype=torch.float32
        )
        targets = torch.tensor(
            np.array(self._training_targets), dtype=torch.float32
        )

        self.model.train()
        predictions = self.model(inputs)
        loss = self.loss_fn(predictions, targets)

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        self.model.eval()

    def get_difficulty_modifier(self) -> float:
        """Return the current difficulty multiplier."""
        return self.difficulty_modifier


# ---------------------------------------------------------------------------
# Content Recommender
# ---------------------------------------------------------------------------

# Room types the dungeon generator can produce
ROOM_TYPES: List[str] = [
    "combat_easy",
    "combat_medium",
    "combat_hard",
    "elite",
    "boss",
    "treasure",
    "merchant",
    "rest",
    "puzzle",
    "trap",
]

# Equipment slot names
EQUIPMENT_SLOTS: List[str] = [
    "weapon",
    "armor",
    "helmet",
    "boots",
    "accessory",
    "shield",
]

# Consumable types
CONSUMABLE_TYPES: List[str] = [
    "health_potion",
    "mana_potion",
    "buff_scroll",
    "escape_scroll",
]


class ContentRecommender:
    """
    Recommends dungeon room types and loot drops based on player state,
    performance, and implicit preferences.

    Uses utility scoring with softmax normalization:
        1. Compute a utility score for each option based on player needs.
        2. Apply softmax to convert utilities into probability weights.
        3. Return the weights so the dungeon generator can sample from them.

    This ensures variety (every option has nonzero probability) while
    biasing toward what the player needs most.

    Attributes:
        room_performance:    Tracks player success rate per room type.
        item_usage_counts:   Tracks how often the player uses each item type.
        base_room_weights:   Default room type distribution.
        temperature:         Softmax temperature (higher = more uniform).
    """

    def __init__(self, temperature: float = 1.5) -> None:
        self.temperature: float = temperature

        # Track per-room-type performance: (successes, attempts)
        self.room_performance: Dict[str, List[int]] = {
            rt: [0, 0] for rt in ROOM_TYPES
        }

        # Track item usage frequency
        self.item_usage_counts: Dict[str, int] = {}

        # Default room weights (before any adaptation)
        self.base_room_weights: Dict[str, float] = {
            "combat_easy": 0.15,
            "combat_medium": 0.20,
            "combat_hard": 0.15,
            "elite": 0.08,
            "boss": 0.02,
            "treasure": 0.12,
            "merchant": 0.08,
            "rest": 0.08,
            "puzzle": 0.07,
            "trap": 0.05,
        }

    def record_room_result(
        self, room_type: str, success: bool
    ) -> None:
        """
        Record whether the player succeeded in a room of the given type.

        Args:
            room_type: The type of room that was completed.
            success:   True if the player cleared it without dying.
        """
        if room_type in self.room_performance:
            self.room_performance[room_type][1] += 1  # attempts
            if success:
                self.room_performance[room_type][0] += 1  # successes

    def record_item_usage(self, item_type: str) -> None:
        """Track that the player used an item of the given type."""
        self.item_usage_counts[item_type] = (
            self.item_usage_counts.get(item_type, 0) + 1
        )

    def _softmax(self, values: np.ndarray) -> np.ndarray:
        """
        Temperature-scaled softmax over a vector of utility scores.

        Higher temperature -> more uniform distribution.
        Lower temperature -> more peaked toward highest utility.
        """
        scaled = values / max(self.temperature, 0.01)
        exp_vals = np.exp(scaled - np.max(scaled))  # Numerical stability
        return exp_vals / exp_vals.sum()

    def recommend_room_weights(
        self,
        player_stats: Dict[str, float],
        floor_num: int,
    ) -> Dict[str, float]:
        """
        Compute adjusted room type weights for dungeon generation.

        Strategy:
            - If the player is struggling: boost treasure, merchant, rest rooms;
              reduce elite and boss rooms.
            - If the player is dominating: boost elite, boss, hard combat;
              reduce easy rooms.
            - Always maintain minimum variety to prevent monotony.

        Args:
            player_stats: Player statistics dictionary.
            floor_num:    Current dungeon floor.

        Returns:
            Dictionary mapping room type -> sampling weight (sums to ~1.0).
        """
        performance = player_stats.get("performance_score", 0.5)
        hp_pct = player_stats.get("hp_pct", 1.0)

        # Start with base weights
        utilities = np.zeros(len(ROOM_TYPES), dtype=np.float32)

        for i, rt in enumerate(ROOM_TYPES):
            base = self.base_room_weights.get(rt, 0.1)
            utility = math.log(base + 0.01)  # Log scale for smoother blending

            # Performance-based adjustments
            if rt in ("combat_easy", "treasure", "merchant", "rest"):
                # Helpful rooms: boost when player is struggling
                utility += (1.0 - performance) * 1.5
            elif rt in ("combat_hard", "elite", "boss"):
                # Challenge rooms: boost when player is dominating
                utility += performance * 1.5
            elif rt == "combat_medium":
                # Neutral: slight boost around mid-performance
                utility += (1.0 - abs(performance - 0.5) * 2.0) * 0.5

            # HP-based emergency adjustments
            if hp_pct < 0.3 and rt in ("rest", "merchant", "treasure"):
                utility += 2.0  # Strongly prefer recovery when HP is low
            if hp_pct < 0.3 and rt in ("elite", "boss", "combat_hard"):
                utility -= 2.0  # Avoid hard fights when nearly dead

            # Floor scaling: more challenging rooms on deeper floors
            floor_factor = min(floor_num / 20.0, 1.0)
            if rt in ("elite", "boss"):
                utility += floor_factor * 0.5
            if rt == "combat_easy":
                utility -= floor_factor * 0.3

            # Historical success rate adjustment
            successes, attempts = self.room_performance[rt]
            if attempts >= 3:
                success_rate = successes / attempts
                # If player consistently fails a room type, reduce it slightly
                if success_rate < 0.3:
                    utility -= 0.5
                # If player crushes a room type, it can appear more
                elif success_rate > 0.8:
                    utility += 0.3

            utilities[i] = utility

        # Apply softmax to get proper probability distribution
        weights = self._softmax(utilities)

        return {rt: float(w) for rt, w in zip(ROOM_TYPES, weights)}

    def recommend_loot(
        self,
        player_stats: Dict[str, float],
        floor_num: int,
    ) -> Dict[str, float]:
        """
        Recommend loot drop type weights based on player needs.

        Checks:
            1. Which equipment slots are weakest (biggest upgrade potential).
            2. Whether the player is low on consumables.
            3. Class-specific needs (e.g. mages need mana potions more).

        Args:
            player_stats: Must include 'equipment_levels' dict mapping slot ->
                          item level, 'class' string, 'hp_pct', 'mp_pct',
                          'inventory_potions' dict.
            floor_num:    Current dungeon floor.

        Returns:
            Dictionary mapping loot category -> weight.
        """
        equipment_levels = player_stats.get("equipment_levels", {})
        player_class = player_stats.get("class", "warrior")
        hp_pct = player_stats.get("hp_pct", 1.0)
        mp_pct = player_stats.get("mp_pct", 1.0)
        potions = player_stats.get("inventory_potions", {})

        utilities: Dict[str, float] = {}

        # --- Equipment slot analysis ---
        if equipment_levels:
            avg_level = (
                sum(equipment_levels.values()) / len(equipment_levels)
                if equipment_levels
                else float(floor_num)
            )
            for slot in EQUIPMENT_SLOTS:
                slot_level = equipment_levels.get(slot, 0)
                # Higher utility for weaker slots (bigger upgrade potential)
                deficit = max(avg_level - slot_level, 0.0)
                utilities[f"equip_{slot}"] = 1.0 + deficit * 0.5
        else:
            # No equipment data: assign uniform equipment weights
            for slot in EQUIPMENT_SLOTS:
                utilities[f"equip_{slot}"] = 1.0

        # --- Consumable analysis ---
        health_potions = potions.get("health_potion", 0)
        mana_potions = potions.get("mana_potion", 0)
        buff_scrolls = potions.get("buff_scroll", 0)
        escape_scrolls = potions.get("escape_scroll", 0)

        # Low stock -> high utility for that consumable
        utilities["health_potion"] = max(0.5, 3.0 - health_potions * 0.5)
        utilities["mana_potion"] = max(0.5, 3.0 - mana_potions * 0.5)
        utilities["buff_scroll"] = max(0.3, 2.0 - buff_scrolls * 0.4)
        utilities["escape_scroll"] = max(0.2, 1.5 - escape_scrolls * 0.3)

        # If player HP is low, prioritize health potions even more
        if hp_pct < 0.4:
            utilities["health_potion"] += 2.0

        # If player MP is low, prioritize mana potions
        if mp_pct < 0.3:
            utilities["mana_potion"] += 2.0

        # --- Class-specific adjustments ---
        class_boosts: Dict[str, Dict[str, float]] = {
            "warrior": {"equip_weapon": 0.8, "equip_armor": 0.5, "health_potion": 0.5},
            "mage": {"mana_potion": 1.0, "equip_accessory": 0.5, "buff_scroll": 0.5},
            "rogue": {"equip_weapon": 0.5, "equip_boots": 0.5, "escape_scroll": 0.5},
            "cleric": {"mana_potion": 0.8, "equip_shield": 0.5, "buff_scroll": 0.3},
        }
        for item, boost in class_boosts.get(player_class, {}).items():
            if item in utilities:
                utilities[item] += boost

        # --- Item usage preference (collaborative filtering lite) ---
        total_usage = sum(self.item_usage_counts.values()) or 1
        for item_type, count in self.item_usage_counts.items():
            usage_pref = count / total_usage
            # Slightly boost items the player actually uses
            for key in utilities:
                if item_type in key:
                    utilities[key] += usage_pref * 0.5

        # --- Floor scaling: better loot on deeper floors ---
        floor_bonus = min(floor_num / 20.0, 1.0) * 0.5
        for slot in EQUIPMENT_SLOTS:
            key = f"equip_{slot}"
            if key in utilities:
                utilities[key] += floor_bonus

        # Convert to probability weights via softmax
        keys = list(utilities.keys())
        values = np.array([utilities[k] for k in keys], dtype=np.float32)
        weights = self._softmax(values)

        return {k: float(w) for k, w in zip(keys, weights)}


# ---------------------------------------------------------------------------
# Embedding-Based Content Recommendation Network
# ---------------------------------------------------------------------------
class ContentEmbeddingModel(nn.Module):
    """
    Neural content recommendation model that learns dense embeddings for
    player states and content items (rooms/loot). Predicts player preference
    scores using dot-product similarity in the embedding space.

    This is the same architecture used in production recommendation systems
    at game studios — learning a shared embedding space where similar player
    states and preferred content items are close together.

    Architecture:
        Player state (10) -> Linear(32) -> ReLU -> Linear(16) -> player_embed
        Content ID   (1)  -> Embedding(num_items, 16)           -> item_embed
        Score = dot(player_embed, item_embed)

    Key ML Concepts:
        - Learned dense embeddings (analogous to word2vec for game content)
        - Dot-product scoring (efficient, scalable to large item catalogs)
        - Implicit feedback learning (player actions = positive signal)
        - Online fine-tuning from live gameplay
    """

    def __init__(self, num_items: int = 10, embed_dim: int = 16) -> None:
        super().__init__()
        self.num_items = num_items
        self.embed_dim = embed_dim

        # Player state encoder: maps 10D stats to 16D embedding
        self.player_encoder = nn.Sequential(
            nn.Linear(10, 32),
            nn.ReLU(),
            nn.Linear(32, embed_dim),
        )

        # Content item embeddings: each room/loot type gets a learned vector
        self.item_embeddings = nn.Embedding(num_items, embed_dim)

        # Temperature parameter for score scaling
        self.temperature = nn.Parameter(torch.tensor(1.0))

        self._init_weights()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                nn.init.zeros_(module.bias)
        nn.init.normal_(self.item_embeddings.weight, std=0.1)

    def forward(
        self, player_state: torch.Tensor, item_ids: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Compute preference scores for all items given a player state.

        Args:
            player_state: (batch, 10) player feature vector.
            item_ids: Optional (batch, K) specific item indices to score.
                      If None, scores all items.

        Returns:
            Scores tensor of shape (batch, num_items) or (batch, K).
        """
        # Encode player state to embedding space
        player_embed = self.player_encoder(player_state)  # (batch, 16)

        if item_ids is not None:
            # Score specific items
            item_embed = self.item_embeddings(item_ids)  # (batch, K, 16)
            scores = torch.sum(
                player_embed.unsqueeze(1) * item_embed, dim=-1
            )  # (batch, K)
        else:
            # Score all items: dot product with full embedding table
            all_embeds = self.item_embeddings.weight  # (num_items, 16)
            scores = torch.mm(player_embed, all_embeds.t())  # (batch, num_items)

        return scores / self.temperature

    def get_recommendations(
        self, player_state: np.ndarray, top_k: int = 5
    ) -> List[Tuple[int, float]]:
        """
        Get top-K item recommendations for a player state.

        Returns:
            List of (item_idx, score) tuples sorted by score descending.
        """
        self.eval()
        with torch.no_grad():
            state_t = torch.tensor(
                player_state, dtype=torch.float32
            ).unsqueeze(0)
            scores = self.forward(state_t).squeeze(0)
            probs = torch.softmax(scores, dim=0)

        indices = probs.argsort(descending=True)[:top_k]
        return [(int(idx), float(probs[idx])) for idx in indices]


# ---------------------------------------------------------------------------
# AI Director (Master Controller)
# ---------------------------------------------------------------------------
class AIDirector:
    """
    Master controller that orchestrates Dynamic Difficulty Adjustment and
    Content Recommendation.

    The director runs on a fixed update interval (default 5 seconds) to
    avoid unnecessary computation every frame. It exposes simple methods
    for the game loop to query difficulty modifiers, room weights, and
    loot recommendations.

    Usage in game loop:
        director = AIDirector()

        # Each frame:
        director.update(player, floor_num, game_time, dt)

        # When generating dungeon rooms:
        weights = director.get_room_weights(player.get_stats_dict(), floor_num)

        # When spawning loot:
        loot = director.get_loot_recommendation(player.get_stats_dict(), floor_num)

        # When spawning enemies (apply modifier to their stats):
        modifier = director.get_difficulty_modifier()
        enemy.hp *= modifier
        enemy.damage *= modifier

        # When events happen:
        director.record_event('kill', {'enemy_type': 'goblin'}, game_time)

    Attributes:
        difficulty:       DifficultyAdjuster instance.
        recommender:      ContentRecommender instance.
        update_interval:  Seconds between DDA updates.
        timer:            Accumulator for update timing.
    """

    def __init__(self, update_interval: float = 5.0) -> None:
        self.difficulty = DifficultyAdjuster()
        self.recommender = ContentRecommender()
        self.content_model = ContentEmbeddingModel(
            num_items=len(ROOM_TYPES), embed_dim=16
        )
        self.content_optimizer = optim.Adam(
            self.content_model.parameters(), lr=1e-3
        )
        self.update_interval: float = update_interval
        self.timer: float = 0.0

    def update(
        self,
        player_stats: Dict[str, float],
        floor_num: int,
        game_time: float,
        dt: float,
    ) -> None:
        """
        Tick the director. Runs the DDA update when the interval elapses.

        Args:
            player_stats: Dictionary of player statistics (hp_pct, mp_pct, etc.)
            floor_num:    Current dungeon floor number.
            game_time:    Total elapsed game time in seconds.
            dt:           Time delta since last frame in seconds.
        """
        self.timer += dt
        if self.timer >= self.update_interval:
            self.timer = 0.0
            # Inject game_time into stats for the tracker
            stats_with_time = dict(player_stats)
            stats_with_time["game_time"] = game_time
            stats_with_time["performance_score"] = (
                self.difficulty.tracker.get_performance_score()
            )
            self.difficulty.update(stats_with_time, floor_num, dt)

    def record_event(
        self, event_type: str, data: Dict[str, Any], game_time: float
    ) -> None:
        """Forward a gameplay event to the performance tracker."""
        self.difficulty.tracker.record_event(event_type, data, game_time)

    def record_room_result(self, room_type: str, success: bool) -> None:
        """Record whether the player succeeded in a room."""
        self.recommender.record_room_result(room_type, success)

    def record_item_usage(self, item_type: str) -> None:
        """Record that the player used an item."""
        self.recommender.record_item_usage(item_type)

    def record_floor_outcome(
        self,
        player_stats: Dict[str, float],
        floor_num: int,
        survived: bool,
        enjoyment_proxy: float,
    ) -> None:
        """
        Record an actual floor outcome for model training.

        Should be called when the player finishes or dies on a floor.
        """
        self.difficulty.record_outcome(
            player_stats, floor_num, survived, enjoyment_proxy
        )

    def get_difficulty_modifier(self) -> float:
        """Return the current difficulty multiplier for enemy stats."""
        return self.difficulty.get_difficulty_modifier()

    def get_room_weights(
        self, player_stats: Dict[str, float], floor_num: int
    ) -> Dict[str, float]:
        """Return adjusted room type weights for dungeon generation."""
        return self.recommender.recommend_room_weights(player_stats, floor_num)

    def get_loot_recommendation(
        self, player_stats: Dict[str, float], floor_num: int
    ) -> Dict[str, float]:
        """Return loot type weights for item drop selection."""
        return self.recommender.recommend_loot(player_stats, floor_num)

    def get_stats(self) -> Dict[str, Any]:
        """
        Return a summary of the director's internal state for debugging
        and visualization.

        Returns:
            Dictionary with difficulty modifier, performance score, and
            recent history entries.
        """
        return {
            "difficulty_modifier": self.difficulty.difficulty_modifier,
            "difficulty_mod": self.difficulty.difficulty_modifier,
            "predicted_survival": getattr(self.difficulty, '_last_survival', 0.6),
            "predicted_enjoyment": getattr(self.difficulty, '_last_enjoyment', 0.5),
            "performance_score": self.difficulty.tracker.get_performance_score(),
            "total_kills": self.difficulty.tracker.total_kills,
            "total_deaths": self.difficulty.tracker.total_deaths,
            "rooms_cleared": self.difficulty.tracker.rooms_cleared,
            "history": self.difficulty.history[-10:],
        }

    def save_state(self, path: str) -> None:
        """Save director model weights and state to disk."""
        import os
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        checkpoint = {
            "player_model": self.difficulty.model.state_dict(),
            "difficulty_modifier": self.difficulty.difficulty_modifier,
        }
        torch.save(checkpoint, path)

    def load_state(self, path: str) -> None:
        """Restore director model weights from a checkpoint."""
        import os
        if not os.path.exists(path):
            return
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        self.difficulty.model.load_state_dict(checkpoint["player_model"])
        self.difficulty.difficulty_modifier = checkpoint["difficulty_modifier"]


# ---------------------------------------------------------------------------
# Example / self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== AI Director Self-Test ===\n")

    director = AIDirector(update_interval=1.0)

    # Simulate a player progressing through a floor
    game_time = 0.0
    dt = 0.5  # 500ms ticks

    player_stats = {
        "hp_pct": 0.9,
        "mp_pct": 0.7,
        "level": 5,
        "class": "warrior",
        "equipment_levels": {
            "weapon": 4, "armor": 3, "helmet": 2,
            "boots": 5, "accessory": 1, "shield": 3,
        },
        "inventory_potions": {
            "health_potion": 2, "mana_potion": 1,
            "buff_scroll": 0, "escape_scroll": 1,
        },
    }

    director.record_event("floor_start", {"floor": 3}, game_time)

    for tick in range(40):
        game_time += dt

        # Simulate some events
        if tick % 5 == 0:
            director.record_event("kill", {"enemy_type": "goblin"}, game_time)
            director.record_event("damage_dealt", {"amount": 25.0}, game_time)
        if tick % 8 == 0:
            director.record_event("damage_taken", {"amount": 15.0}, game_time)
            player_stats["hp_pct"] = max(0.1, player_stats["hp_pct"] - 0.05)
        if tick % 12 == 0:
            director.record_event("ability_used", {"ability": "slash"}, game_time)
        if tick == 20:
            director.record_event(
                "room_cleared",
                {"room_type": "combat_medium", "hp_pct": player_stats["hp_pct"], "time": 10.0},
                game_time,
            )
            director.record_room_result("combat_medium", success=True)

        director.update(player_stats, floor_num=3, game_time=game_time, dt=dt)

    # Check outputs
    stats = director.get_stats()
    print(f"Difficulty modifier: {stats['difficulty_mod']:.3f}")
    print(f"Performance score:   {stats['performance_score']:.3f}")
    print(f"Total kills:         {stats['total_kills']}")
    print(f"Rooms cleared:       {stats['rooms_cleared']}")

    room_weights = director.get_room_weights(player_stats, floor_num=3)
    print(f"\nRoom weights:")
    for rt, w in sorted(room_weights.items(), key=lambda x: -x[1]):
        print(f"  {rt:20s} {w:.3f}")

    loot = director.get_loot_recommendation(player_stats, floor_num=3)
    print(f"\nLoot recommendations (top 5):")
    for item, w in sorted(loot.items(), key=lambda x: -x[1])[:5]:
        print(f"  {item:20s} {w:.3f}")

    # Test model training
    director.record_floor_outcome(player_stats, 3, survived=True, enjoyment_proxy=0.7)
    print(f"\nRecorded floor outcome for model training.")
    print(f"Training samples collected: {len(director.difficulty._training_inputs)}")

    print("\nSelf-test passed.")
