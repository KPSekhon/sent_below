"""
Model Serving API - Production ML Inference Endpoint
=====================================================
FastAPI application that serves the trained DQN enemy AI and player difficulty
models as REST endpoints. Designed for deployment on AWS ECS, GCP Cloud Run,
or any container orchestrator.

Endpoints:
    GET  /health                  - Healthcheck (for load balancers)
    GET  /models                  - List loaded models and metadata
    POST /predict/enemy-action    - DQN inference: state -> action
    POST /predict/enemy-batch     - Batched DQN inference for N enemies
    POST /predict/difficulty      - Player model: stats -> difficulty modifier
    POST /train/enemy-step        - Online training step (experience replay)
    GET  /metrics                 - Prometheus-compatible training metrics

Demonstrates:
    - ML model deployment in production (Docker + REST API)
    - Real-time inference for interactive applications
    - Batch inference optimization
    - Online learning with live gameplay data
    - Model versioning and hot-reload
"""

import os
import time
import json
import tempfile
from typing import List, Optional
from contextlib import asynccontextmanager

import numpy as np
import torch
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# FastAPI setup with lifespan for model loading
# ---------------------------------------------------------------------------
MODEL_DIR = os.environ.get("MODEL_DIR", "models")
DEVICE = os.environ.get("DEVICE", "cpu")

# Global model references (loaded at startup)
_enemy_brain = None
_ai_director = None
_start_time = 0.0
_request_count = 0
_inference_latencies: list = []


def _maybe_download_models_from_s3(model_dir: str) -> str:
    """If S3 env vars are set, download model files and return the local dir."""
    bucket = os.getenv("MODEL_BUCKET")
    prefix = os.getenv("MODEL_S3_PREFIX")

    if not bucket or not prefix:
        return model_dir

    try:
        import boto3
    except ImportError:
        print("[serve] boto3 not installed — skipping S3 download")
        return model_dir

    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "ca-central-1"))
    local_dir = tempfile.mkdtemp(prefix="model_bundle_")

    files = ["enemy_brain.pt", "enemy_brain_best.pt", "player_model.pt"]
    downloaded = 0
    for filename in files:
        try:
            dest = os.path.join(local_dir, filename)
            s3.download_file(bucket, f"{prefix}/{filename}", dest)
            print(f"[serve] Downloaded s3://{bucket}/{prefix}/{filename}")
            downloaded += 1
        except Exception as e:
            print(f"[serve] Skipping {filename}: {e}")

    if downloaded > 0:
        print(f"[serve] Loaded {downloaded} model files from S3")
        return local_dir

    return model_dir


@asynccontextmanager
async def lifespan(app):
    """Load models on startup, clean up on shutdown."""
    global _enemy_brain, _ai_director, _start_time

    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from ai.enemy_ai import EnemyBrain
    from ai.director import AIDirector

    _start_time = time.time()

    # Prefer S3-backed models when configured, otherwise use local
    model_dir = _maybe_download_models_from_s3(MODEL_DIR)
    if model_dir != MODEL_DIR:
        print(f"[serve] Using S3-backed model directory: {model_dir}")

    # Initialize models
    _enemy_brain = EnemyBrain(device=DEVICE)
    _ai_director = AIDirector()

    # Load pre-trained weights if available
    enemy_checkpoint = os.path.join(model_dir, "enemy_brain.pt")
    if os.path.exists(enemy_checkpoint):
        _enemy_brain.load_model(enemy_checkpoint)
        print(f"[serve] Loaded enemy brain from {enemy_checkpoint}")
    else:
        print("[serve] No enemy checkpoint found, using fresh weights")

    director_checkpoint = os.path.join(model_dir, "director.pt")
    if os.path.exists(director_checkpoint):
        _ai_director.load_state(director_checkpoint)
        print(f"[serve] Loaded director from {director_checkpoint}")
    else:
        print("[serve] No director checkpoint found, using fresh weights")

    print(f"[serve] Models ready on device={DEVICE}")

    yield

    # Shutdown: save current model state
    os.makedirs(MODEL_DIR, exist_ok=True)
    save_path = os.path.join(MODEL_DIR, "enemy_brain.pt")
    _enemy_brain.save_model(save_path)
    print("[serve] Models saved on shutdown")


from fastapi import FastAPI, HTTPException

app = FastAPI(
    title="Sent Below - ML Model Serving API",
    description="Real-time inference endpoints for game AI models",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------
class EnemyState(BaseModel):
    """10-dimensional state vector for a single enemy."""
    enemy_hp_pct: float = Field(..., ge=0, le=1)
    player_hp_pct: float = Field(..., ge=0, le=1)
    distance: float = Field(..., ge=0, le=1)
    attack_ready: float = Field(..., ge=0, le=1)
    enemy_strength: float = Field(..., ge=0, le=1)
    player_defense: float = Field(..., ge=0, le=1)
    is_aggressive: float = Field(..., ge=0, le=1)
    is_defensive: float = Field(..., ge=0, le=1)
    is_support: float = Field(..., ge=0, le=1)
    time_in_fight: float = Field(..., ge=0, le=1)
    behavior_type: str = Field(default="aggressive")

    def to_array(self) -> np.ndarray:
        return np.array([
            self.enemy_hp_pct, self.player_hp_pct, self.distance,
            self.attack_ready, self.enemy_strength, self.player_defense,
            self.is_aggressive, self.is_defensive, self.is_support,
            self.time_in_fight,
        ], dtype=np.float32)


class ActionResponse(BaseModel):
    action: str
    q_values: List[float]
    inference_ms: float


class BatchEnemyRequest(BaseModel):
    enemies: List[EnemyState]


class BatchActionResponse(BaseModel):
    actions: List[str]
    count: int
    inference_ms: float


class PlayerStats(BaseModel):
    """Player stats for difficulty prediction."""
    hp_pct: float = Field(..., ge=0, le=1)
    mp_pct: float = Field(..., ge=0, le=1)
    level: int = Field(..., ge=1)
    floor: int = Field(..., ge=1)
    kills_per_min: float = Field(default=0.0, ge=0)
    deaths: int = Field(default=0, ge=0)
    damage_ratio: float = Field(default=1.0, ge=0)
    ability_usage: float = Field(default=0.0, ge=0)
    potion_usage: float = Field(default=0.0, ge=0)
    clear_time_ratio: float = Field(default=1.0, ge=0)


class DifficultyResponse(BaseModel):
    difficulty_modifier: float
    predicted_survival: float
    predicted_enjoyment: float
    inference_ms: float


class ExperienceTuple(BaseModel):
    """Single RL experience for online training."""
    state: List[float] = Field(..., min_length=10, max_length=10)
    action: int = Field(..., ge=0, le=6)
    reward: float
    next_state: List[float] = Field(..., min_length=10, max_length=10)
    done: bool


class TrainResponse(BaseModel):
    loss: Optional[float]
    buffer_size: int
    training_steps: int
    epsilon: float


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    """Healthcheck for load balancers and container orchestrators."""
    return {
        "status": "healthy",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "models_loaded": _enemy_brain is not None,
        "device": DEVICE,
    }


@app.get("/models")
async def list_models():
    """Return metadata about loaded models."""
    enemy_stats = _enemy_brain.get_training_stats() if _enemy_brain else {}
    return {
        "enemy_brain": {
            "architecture": "DQN (10 -> 64 -> 32 -> 7)",
            "parameters": sum(p.numel() for p in _enemy_brain.policy_net.parameters()),
            "device": str(_enemy_brain.device),
            **enemy_stats,
        },
        "ai_director": {
            "architecture": "PlayerModel (10 -> 32 -> 16 -> 2) + ContentRecommender",
            "components": ["DifficultyAdjuster", "ContentRecommender", "PerformanceTracker"],
        },
    }


@app.post("/predict/enemy-action", response_model=ActionResponse)
async def predict_enemy_action(state: EnemyState):
    """
    Single enemy inference: given a state vector, return the optimal action.
    Uses the DQN policy network with behavior-type biasing.
    """
    global _request_count
    _request_count += 1

    t0 = time.perf_counter()
    state_vec = state.to_array()

    # Get Q-values for diagnostics
    state_tensor = torch.tensor(state_vec, dtype=torch.float32,
                                device=_enemy_brain.device).unsqueeze(0)
    with torch.no_grad():
        q_values = _enemy_brain.policy_net(state_tensor).squeeze(0).cpu().numpy()

    action = _enemy_brain.decide_action(state_vec, state.behavior_type)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    _inference_latencies.append(elapsed_ms)

    return ActionResponse(
        action=action,
        q_values=q_values.tolist(),
        inference_ms=round(elapsed_ms, 3),
    )


@app.post("/predict/enemy-batch", response_model=BatchActionResponse)
async def predict_enemy_batch(request: BatchEnemyRequest):
    """
    Batched inference for multiple enemies. Processes all states in a single
    forward pass through the network for optimal throughput.
    """
    global _request_count
    _request_count += 1

    t0 = time.perf_counter()
    states = np.array([e.to_array() for e in request.enemies], dtype=np.float32)
    behavior_types = [e.behavior_type for e in request.enemies]

    actions = _enemy_brain.decide_actions_batch(states, behavior_types)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    return BatchActionResponse(
        actions=actions,
        count=len(actions),
        inference_ms=round(elapsed_ms, 3),
    )


@app.post("/predict/difficulty", response_model=DifficultyResponse)
async def predict_difficulty(stats: PlayerStats):
    """
    Predict appropriate difficulty modifier based on player performance.
    Uses the neural player model to estimate survival probability, then
    adjusts difficulty to target ~60% survival rate (flow zone).
    """
    t0 = time.perf_counter()

    player_dict = {
        "hp_pct": stats.hp_pct,
        "mp_pct": stats.mp_pct,
        "level": stats.level,
        "kills_per_min": stats.kills_per_min,
        "deaths": stats.deaths,
        "damage_ratio": stats.damage_ratio,
        "ability_usage": stats.ability_usage,
        "potion_usage": stats.potion_usage,
        "clear_time_ratio": stats.clear_time_ratio,
    }

    _ai_director.update(player_dict, stats.floor, 0.0, 0.016)
    director_stats = _ai_director.get_stats()

    elapsed_ms = (time.perf_counter() - t0) * 1000

    return DifficultyResponse(
        difficulty_modifier=director_stats.get("difficulty_modifier", 1.0),
        predicted_survival=director_stats.get("predicted_survival", 0.6),
        predicted_enjoyment=director_stats.get("predicted_enjoyment", 0.5),
        inference_ms=round(elapsed_ms, 3),
    )


@app.post("/train/enemy-step", response_model=TrainResponse)
async def train_step(experience: ExperienceTuple):
    """
    Online training: accept a single experience tuple from a live game
    session, store it in the replay buffer, and optionally perform a
    training step if enough experiences have accumulated.
    """
    state = np.array(experience.state, dtype=np.float32)
    next_state = np.array(experience.next_state, dtype=np.float32)

    _enemy_brain.store_experience(
        state, experience.action, experience.reward,
        next_state, experience.done,
    )

    loss = None
    if len(_enemy_brain.replay_buffer) >= _enemy_brain.batch_size:
        loss = _enemy_brain.train_step()
        if _enemy_brain.total_steps % 10 == 0:
            _enemy_brain.update_target_network()

    stats = _enemy_brain.get_training_stats()
    return TrainResponse(
        loss=loss,
        buffer_size=stats["num_experiences"],
        training_steps=stats["training_steps"],
        epsilon=stats["epsilon"],
    )


@app.get("/metrics")
async def metrics():
    """Prometheus-compatible metrics endpoint for monitoring."""
    stats = _enemy_brain.get_training_stats() if _enemy_brain else {}
    avg_latency = (
        sum(_inference_latencies[-100:]) / len(_inference_latencies[-100:])
        if _inference_latencies else 0.0
    )
    return {
        "uptime_seconds": round(time.time() - _start_time, 1),
        "total_requests": _request_count,
        "avg_inference_ms": round(avg_latency, 3),
        "model": {
            "training_loss": stats.get("loss", 0),
            "avg_loss": stats.get("avg_loss", 0),
            "epsilon": stats.get("epsilon", 1.0),
            "replay_buffer_size": stats.get("num_experiences", 0),
            "training_steps": stats.get("training_steps", 0),
        },
    }
