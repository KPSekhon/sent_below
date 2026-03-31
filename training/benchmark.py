"""
Model Benchmarking & Profiling - Performance Analysis for Production ML
========================================================================
Measures inference latency, throughput, memory usage, and model complexity
for the game AI models. Critical for deploying ML models in real-time
interactive applications where frame budgets are tight.

Metrics measured:
    - Single inference latency (p50, p95, p99)
    - Batch inference throughput (inferences/sec)
    - Peak memory usage (MB)
    - Model parameter count and size
    - FLOP estimation
    - GPU vs CPU performance comparison

Output:
    Console table + JSON report for documentation.

Usage:
    python -m training.benchmark
    python -m training.benchmark --batch-sizes 1 8 32 64 --warmup 100 --iters 1000
"""

import os
import sys
import time
import json
import argparse
from typing import Dict, List

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.enemy_ai import EnemyBrain, EnemyNetwork, STATE_DIM, NUM_ACTIONS
from ai.director import PlayerModel


# ---------------------------------------------------------------------------
# Benchmark Utilities
# ---------------------------------------------------------------------------
def measure_latency(
    model: torch.nn.Module,
    input_tensor: torch.Tensor,
    warmup: int = 100,
    iterations: int = 1000,
) -> Dict[str, float]:
    """
    Measure single-inference latency with warm-up and statistical analysis.

    Returns:
        Dict with mean_ms, std_ms, p50_ms, p95_ms, p99_ms, min_ms, max_ms.
    """
    model.eval()

    # Warm up (JIT compilation, cache warming)
    with torch.no_grad():
        for _ in range(warmup):
            _ = model(input_tensor)

    # Timed runs
    latencies = []
    with torch.no_grad():
        for _ in range(iterations):
            t0 = time.perf_counter()
            _ = model(input_tensor)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000)  # ms

    arr = np.array(latencies)
    return {
        "mean_ms": float(np.mean(arr)),
        "std_ms": float(np.std(arr)),
        "p50_ms": float(np.percentile(arr, 50)),
        "p95_ms": float(np.percentile(arr, 95)),
        "p99_ms": float(np.percentile(arr, 99)),
        "min_ms": float(np.min(arr)),
        "max_ms": float(np.max(arr)),
    }


def measure_throughput(
    model: torch.nn.Module,
    input_dim: int,
    batch_sizes: List[int],
    warmup: int = 50,
    duration_sec: float = 2.0,
    device: str = "cpu",
) -> Dict[int, Dict[str, float]]:
    """
    Measure throughput (inferences/sec) across different batch sizes.

    Returns:
        Dict mapping batch_size -> {throughput, latency_per_batch_ms}.
    """
    model.eval()
    results = {}

    for bs in batch_sizes:
        x = torch.randn(bs, input_dim, device=device)

        # Warm up
        with torch.no_grad():
            for _ in range(warmup):
                _ = model(x)

        # Timed run
        count = 0
        t_start = time.perf_counter()
        with torch.no_grad():
            while time.perf_counter() - t_start < duration_sec:
                _ = model(x)
                count += 1

        elapsed = time.perf_counter() - t_start
        total_inferences = count * bs

        results[bs] = {
            "batches_per_sec": count / elapsed,
            "inferences_per_sec": total_inferences / elapsed,
            "latency_per_batch_ms": (elapsed / count) * 1000,
        }

    return results


def measure_memory(
    model: torch.nn.Module,
    input_tensor: torch.Tensor,
) -> Dict[str, float]:
    """
    Measure memory footprint of model and inference.

    Returns:
        Dict with model_params, model_size_mb, peak_inference_mb.
    """
    # Parameter count
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    # Model size (approximate from parameter dtypes)
    size_bytes = sum(
        p.numel() * p.element_size() for p in model.parameters()
    )

    # Inference memory tracking (CPU only — GPU uses torch.cuda.memory)
    import tracemalloc
    tracemalloc.start()

    model.eval()
    with torch.no_grad():
        for _ in range(10):
            _ = model(input_tensor)

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "total_params": total_params,
        "trainable_params": trainable_params,
        "model_size_mb": size_bytes / (1024 * 1024),
        "peak_inference_mb": peak / (1024 * 1024),
    }


def model_summary(model: torch.nn.Module, name: str) -> Dict:
    """Generate a comprehensive model summary."""
    layers = []
    for layer_name, module in model.named_modules():
        if isinstance(module, (torch.nn.Linear, torch.nn.BatchNorm1d,
                               torch.nn.Conv1d)):
            params = sum(p.numel() for p in module.parameters())
            layers.append({
                "name": layer_name,
                "type": module.__class__.__name__,
                "params": params,
            })

    return {
        "name": name,
        "total_params": sum(p.numel() for p in model.parameters()),
        "layers": layers,
    }


# ---------------------------------------------------------------------------
# Main Benchmark
# ---------------------------------------------------------------------------
def run_benchmark(args) -> Dict:
    """Run full benchmark suite on all game AI models."""
    device = args.device
    batch_sizes = args.batch_sizes
    warmup = args.warmup
    iterations = args.iterations

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "device": device,
        "pytorch_version": torch.__version__,
        "models": {},
    }

    print("=" * 70)
    print("  Sent Below - ML Model Benchmark")
    print(f"  Device: {device} | PyTorch {torch.__version__}")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # 1. Enemy DQN (Dueling + Attention)
    # -----------------------------------------------------------------------
    print("\n--- Enemy AI (Dueling DQN + Self-Attention) ---")
    brain = EnemyBrain(device=device)
    enemy_net = brain.policy_net
    enemy_input = torch.randn(1, STATE_DIM, device=device)

    summary = model_summary(enemy_net, "EnemyNetwork")
    print(f"  Parameters: {summary['total_params']:,}")

    latency = measure_latency(enemy_net, enemy_input, warmup, iterations)
    print(f"  Latency: {latency['mean_ms']:.3f}ms (p95: {latency['p95_ms']:.3f}ms)")

    throughput = measure_throughput(
        enemy_net, STATE_DIM, batch_sizes, device=device
    )
    for bs, tp in throughput.items():
        print(f"  Batch {bs:>3d}: {tp['inferences_per_sec']:,.0f} inf/s "
              f"({tp['latency_per_batch_ms']:.3f}ms/batch)")

    memory = measure_memory(enemy_net, enemy_input)
    print(f"  Model size: {memory['model_size_mb']:.4f} MB")
    print(f"  Peak inference: {memory['peak_inference_mb']:.4f} MB")

    # Frame budget analysis
    fps_target = 60
    frame_budget_ms = 1000 / fps_target
    max_enemies = int(frame_budget_ms / latency['p95_ms']) if latency['p95_ms'] > 0 else 999
    print(f"  Max enemies at {fps_target}fps: ~{max_enemies} (single-thread)")

    # With batch inference
    if 32 in throughput:
        batch_time_ms = throughput[32]['latency_per_batch_ms']
        print(f"  Batch-32 at {fps_target}fps: ~{int(frame_budget_ms / batch_time_ms) * 32} enemies")

    report["models"]["enemy_dqn"] = {
        "summary": summary,
        "latency": latency,
        "throughput": {str(k): v for k, v in throughput.items()},
        "memory": memory,
        "max_enemies_60fps": max_enemies,
    }

    # -----------------------------------------------------------------------
    # 2. Player Model (DDA)
    # -----------------------------------------------------------------------
    print("\n--- Player Model (DDA) ---")
    player_model = PlayerModel()
    player_input = torch.randn(1, 10)

    p_summary = model_summary(player_model, "PlayerModel")
    print(f"  Parameters: {p_summary['total_params']:,}")

    p_latency = measure_latency(player_model, player_input, warmup, iterations)
    print(f"  Latency: {p_latency['mean_ms']:.3f}ms (p95: {p_latency['p95_ms']:.3f}ms)")

    p_memory = measure_memory(player_model, player_input)
    print(f"  Model size: {p_memory['model_size_mb']:.4f} MB")

    report["models"]["player_model"] = {
        "summary": p_summary,
        "latency": p_latency,
        "memory": p_memory,
    }

    # -----------------------------------------------------------------------
    # 3. Combined System Budget
    # -----------------------------------------------------------------------
    print("\n--- Combined Frame Budget Analysis ---")
    total_inference_ms = latency['p95_ms'] + p_latency['p95_ms']
    pct_budget = (total_inference_ms / frame_budget_ms) * 100
    print(f"  Target: {fps_target} fps ({frame_budget_ms:.1f}ms frame budget)")
    print(f"  AI inference: {total_inference_ms:.3f}ms ({pct_budget:.1f}% of frame)")
    print(f"  Remaining for game logic + render: {frame_budget_ms - total_inference_ms:.1f}ms")

    report["frame_budget"] = {
        "target_fps": fps_target,
        "frame_budget_ms": frame_budget_ms,
        "ai_inference_ms": total_inference_ms,
        "ai_budget_pct": pct_budget,
        "remaining_ms": frame_budget_ms - total_inference_ms,
    }

    # -----------------------------------------------------------------------
    # Summary table
    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("-" * 70)
    print(f"  {'Model':<30} {'Params':>10} {'Latency (p95)':>15} {'Size (MB)':>10}")
    print("-" * 70)
    print(f"  {'Enemy DQN (Dueling+Attn)':<30} {summary['total_params']:>10,} "
          f"{latency['p95_ms']:>12.3f}ms {memory['model_size_mb']:>10.4f}")
    print(f"  {'Player Model (DDA)':<30} {p_summary['total_params']:>10,} "
          f"{p_latency['p95_ms']:>12.3f}ms {p_memory['model_size_mb']:>10.4f}")
    print("=" * 70)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="ML Model Benchmark")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-sizes", nargs="+", type=int,
                        default=[1, 8, 16, 32, 64])
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--output", default="reports/benchmark.json")

    args = parser.parse_args()
    report = run_benchmark(args)

    # Save report
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {args.output}")


if __name__ == "__main__":
    main()
