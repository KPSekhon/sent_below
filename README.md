# Sent Below

A real-time top-down dungeon crawler with integrated ML/AI systems, built with Python, Pygame, and PyTorch. Trained models are stored in **Amazon S3** with version metadata tracked in **DynamoDB**, and served via a containerised **FastAPI** inference API.

## Demo Video

[Watch the gameplay demo](demo.mp4)

## ML/AI Architecture

### Dueling DQN Enemy AI with Self-Attention
Enemies make decisions through a **Dueling DQN** that decomposes Q-values into a value stream and per-action advantage stream. A learned **self-attention gate** dynamically re-weights the 10-dimensional state vector (HP ratios, distance, combat readiness, behaviour type flags) so the network attends to the features that matter most in each situation. Training uses experience replay, epsilon-greedy exploration, target-network soft updates, batch normalisation, and cosine LR scheduling.

`ai/enemy_ai.py`

### Dynamic Difficulty Adjustment (DDA)
A neural **player model** (10 -> 32 -> 16 -> 2) predicts survival probability and enjoyment from rolling performance metrics. A PID-style controller adjusts enemy scaling in real time to keep the player in the flow zone (~60% survival target).

`ai/director.py`

### Content Recommendation
Embedding-based content recommender scores items via dot-product similarity with a learned player-state encoder, then uses softmax temperature scaling to balance variety and player needs for room-type weighting and loot distribution.

`ai/director.py`

### A/B Testing Framework
Statistical comparison of model variants using Welch's t-test, Mann-Whitney U, Cohen's d effect size, and bootstrap confidence intervals. Consistent-hash traffic routing ensures repeatable session-to-variant assignment.

`ai/ab_testing.py`

### Gameplay Data Pipeline
Event-driven pipeline: structured JSON-Lines logging -> NumPy feature extraction -> PyTorch `Dataset` / `DataLoader` with train/val/test splits. Supports combat transition replay and windowed action sequences for sequence modelling.

`ai/data_pipeline.py`

## AWS Integration

| Service | Purpose |
|---------|---------|
| **S3** | Versioned storage for `.pt`, `.onnx`, and scaler artefacts |
| **DynamoDB** | Lightweight model registry (model name + version + metrics) |
| **ECS Fargate** | Optional container deployment for the FastAPI serving API |

After training completes locally (or in CI), artefacts are uploaded to S3 and a version record is written to DynamoDB. The serving API checks for `MODEL_BUCKET` / `MODEL_S3_PREFIX` at startup and downloads the model bundle from S3 if configured; otherwise it falls back to a local `models/` directory.

```bash
# One-time: create the DynamoDB table
python deploy/setup_dynamodb.py

# Training uploads to S3 automatically when env vars are set
MODEL_BUCKET=adaptive-dungeon-ai-models \
MODEL_REGISTRY_TABLE=AdaptiveDungeonModelRegistry \
python -m training.train_pipeline
```

`training/aws_io.py` | `deploy/setup_dynamodb.py` | `deploy/aws-ecs-task.json`

## Model Serving API

FastAPI + Uvicorn application with endpoints for single and batched DQN inference, difficulty prediction, online training, health checks, and Prometheus-compatible metrics.

```bash
# Local
uvicorn serving.api:app --host 0.0.0.0 --port 8000

# Docker
docker compose up serve
```

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Container orchestrator healthcheck |
| `/models` | GET | Loaded model metadata + parameter counts |
| `/predict/enemy-action` | POST | Single DQN inference (state -> action + Q-values) |
| `/predict/enemy-batch` | POST | Batched inference for N enemies |
| `/predict/difficulty` | POST | Player model -> difficulty modifier |
| `/train/enemy-step` | POST | Online training with a live experience tuple |
| `/metrics` | GET | Training loss, epsilon, buffer size, latency |

`serving/api.py`

## Docker

Multi-stage Dockerfile with four targets:

| Target | Purpose |
|--------|---------|
| `train` | Offline training pipeline + TensorBoard |
| `serve` | FastAPI inference endpoint (production) |
| `game` | Full game with SDL display forwarding |

```bash
docker compose up train          # Run training pipeline
docker compose up serve          # Start model serving API
docker compose up tensorboard    # Launch TensorBoard dashboard
```

## CI/CD

GitHub Actions workflow (`.github/workflows/ml-pipeline.yml`) runs on every push to `main` that touches `ai/`, `training/`, or `serving/`:

1. **Test** - Import checks + module self-tests
2. **Benchmark** - Latency/throughput profiling with regression gate (<50% frame budget)
3. **Train** - Full training pipeline with artefact upload
4. **Docker** - Build and cache serve + train images

## Gameplay

### Classes
**Warrior** - Slash, Shield Wall, Knockback Slam, War Cry, Leap
**Mage** - Fireball, Lightning Bolt, Freeze Blast, Blink, Meteor
**Rogue** - Backstab, Poison Strike, Dash, Smoke Bomb, Blade Flurry
**Healer** - Heal, Holy Light, Purify, Divine Shield, Chain Heal

### Controls

| Key | Action |
|-----|--------|
| WASD / Arrows | Move |
| Left Click | Attack |
| 1-5 | Abilities |
| E | Pick up items |
| F | Interact (stairs, merchant) |
| I / Tab | Inventory |
| P | AI debug overlay |
| ESC | Pause |

### Features
- 6 procedurally generated floors with BSP room placement and MST corridor connections
- 18 enemy types across trash, elite, and boss tiers with unique AI behaviours
- 10+ room types: mob, trap, puzzle, elite, boss, treasure, merchant, hidden, survival
- Boss gimmicks: enrage, counter windows, summons, heal totems, hazard zones, phase transitions
- Equipment system with 5 rarity tiers
- Real-time particle effects, screen shake, floating damage numbers, smooth camera

## Project Structure

```
sent-below/
├── main.py                     # Game entry point
├── config.py                   # All game constants, class/enemy/ability data
├── requirements.txt            # Python dependencies (pygame, torch, boto3, fastapi)
├── Dockerfile                  # Multi-stage build (train / serve / game)
├── docker-compose.yml          # Orchestration with AWS env vars
│
├── game/
│   ├── engine.py               # Game loop, state machine, wall-clamp logic
│   ├── player.py               # Player classes, 20 abilities, status effects
│   ├── enemies.py              # 18 enemy types, behaviour trees, boss gimmicks
│   ├── dungeon.py              # Procedural floor generation, room system
│   ├── combat.py               # Damage calc, projectiles, items, loot tables
│   └── renderer.py             # Rendering, camera, particles, HUD, debug overlay
│
├── ai/
│   ├── enemy_ai.py             # Dueling DQN + Self-Attention + BatchNorm
│   ├── director.py             # DDA, player modelling, content recommendation
│   ├── data_pipeline.py        # Event logging, Dataset/DataLoader pipeline
│   └── ab_testing.py           # Statistical A/B testing framework
│
├── training/
│   ├── train_pipeline.py       # Offline training, TensorBoard, ONNX export
│   ├── benchmark.py            # Latency/throughput/memory profiling
│   └── aws_io.py               # S3 upload/download + DynamoDB registry helpers
│
├── serving/
│   └── api.py                  # FastAPI model serving (single + batch inference)
│
├── deploy/
│   ├── aws-ecs-task.json       # ECS Fargate task definition
│   └── setup_dynamodb.py       # One-time DynamoDB table creation
│
├── notebooks/
│   └── ml_technical_demo.ipynb # Interactive ML walkthrough (7 sections)
│
└── .github/workflows/
    └── ml-pipeline.yml         # CI/CD: test -> benchmark -> train -> docker
```

## Setup

```bash
pip install -r requirements.txt
python main.py
```

### Requirements
- Python 3.10+
- pygame-ce
- PyTorch
- NumPy
- boto3 (for AWS integration)
- FastAPI + Uvicorn (for model serving)
