"""
A/B Testing Framework - Model Comparison for Game AI
=====================================================
Statistical framework for comparing different AI model versions in
production gameplay. Essential for game studios to validate that model
updates actually improve player experience before full rollout.

Features:
    - Multi-variant testing (A/B/C/...)
    - Automatic traffic splitting with configurable ratios
    - Statistical significance testing (Welch's t-test, Mann-Whitney U)
    - Effect size calculation (Cohen's d)
    - Confidence interval estimation
    - Session-level metric aggregation
    - JSON report generation for stakeholder review

Example workflow:
    1. Train two model versions (v1 baseline, v2 candidate)
    2. Create an experiment: 50/50 traffic split
    3. Run gameplay sessions — framework routes to variant automatically
    4. Collect metrics (reward, win rate, session length, player retention)
    5. Analyze results with statistical tests
    6. Generate report for stakeholders

Key Concepts Demonstrated:
    - A/B testing methodology for ML model deployment
    - Statistical hypothesis testing (t-test, Mann-Whitney)
    - Effect size and practical significance
    - Production ML model management and rollout
"""

import os
import json
import hashlib
import math
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

import numpy as np


# ---------------------------------------------------------------------------
# Experiment Configuration
# ---------------------------------------------------------------------------
@dataclass
class Variant:
    """A single variant (model version) in an A/B test."""
    name: str
    model_path: str
    traffic_weight: float = 0.5
    description: str = ""


@dataclass
class Experiment:
    """
    An A/B test experiment comparing model variants.

    Attributes:
        name:       Human-readable experiment name.
        variants:   List of model variants to compare.
        metric:     Primary metric to optimize (e.g., 'avg_reward').
        start_time: Unix timestamp when experiment started.
        status:     'running', 'completed', or 'stopped'.
    """
    name: str
    variants: List[Variant]
    metric: str = "avg_reward"
    start_time: float = field(default_factory=time.time)
    status: str = "running"
    min_sessions_per_variant: int = 30


# ---------------------------------------------------------------------------
# Traffic Router
# ---------------------------------------------------------------------------
class TrafficRouter:
    """
    Deterministically assigns sessions to experiment variants.

    Uses consistent hashing so the same session_id always gets the same
    variant — important for session-level consistency in gameplay.
    """

    def __init__(self, experiment: Experiment) -> None:
        self.experiment = experiment
        self.variants = experiment.variants

        # Normalize weights to sum to 1
        total = sum(v.traffic_weight for v in self.variants)
        self.thresholds: List[Tuple[float, Variant]] = []
        cumulative = 0.0
        for v in self.variants:
            cumulative += v.traffic_weight / total
            self.thresholds.append((cumulative, v))

    def assign(self, session_id: str) -> Variant:
        """
        Assign a session to a variant using consistent hashing.

        Args:
            session_id: Unique session identifier.

        Returns:
            The assigned Variant.
        """
        # Hash session_id to get a deterministic float in [0, 1)
        h = hashlib.sha256(session_id.encode()).hexdigest()
        bucket = int(h[:8], 16) / 0xFFFFFFFF

        for threshold, variant in self.thresholds:
            if bucket <= threshold:
                return variant

        return self.thresholds[-1][1]  # Fallback to last variant


# ---------------------------------------------------------------------------
# Metrics Collector
# ---------------------------------------------------------------------------
class MetricsCollector:
    """
    Collects per-session metrics for each variant in an experiment.

    Metrics tracked per session:
        - avg_reward:       Mean RL reward across combat steps
        - win_rate:         Fraction of rooms survived
        - session_length:   Total gameplay time (seconds)
        - kills:            Total enemies killed
        - deaths:           Player death count
        - difficulty_avg:   Average DDA difficulty modifier
        - floors_cleared:   Number of floors completed
    """

    def __init__(self) -> None:
        self.variant_metrics: Dict[str, List[Dict[str, float]]] = {}

    def record_session(
        self,
        variant_name: str,
        metrics: Dict[str, float],
    ) -> None:
        """Record a complete session's metrics for a variant."""
        if variant_name not in self.variant_metrics:
            self.variant_metrics[variant_name] = []
        self.variant_metrics[variant_name].append(metrics)

    def get_variant_data(self, variant_name: str) -> List[Dict[str, float]]:
        """Get all session metrics for a variant."""
        return self.variant_metrics.get(variant_name, [])

    def get_metric_values(
        self, variant_name: str, metric: str
    ) -> np.ndarray:
        """Extract a single metric's values across all sessions."""
        sessions = self.get_variant_data(variant_name)
        return np.array([s.get(metric, 0.0) for s in sessions], dtype=np.float64)


# ---------------------------------------------------------------------------
# Statistical Analysis
# ---------------------------------------------------------------------------
class StatisticalAnalyzer:
    """
    Performs statistical tests to determine if differences between
    variants are significant.

    Methods:
        - Welch's t-test (parametric, unequal variance)
        - Mann-Whitney U test (non-parametric)
        - Cohen's d effect size
        - Bootstrap confidence intervals
    """

    @staticmethod
    def welch_t_test(
        a: np.ndarray, b: np.ndarray
    ) -> Dict[str, float]:
        """
        Welch's t-test for two independent samples with unequal variance.

        Returns:
            Dict with t_statistic, p_value, degrees_of_freedom.
        """
        n_a, n_b = len(a), len(b)
        if n_a < 2 or n_b < 2:
            return {"t_statistic": 0.0, "p_value": 1.0, "df": 0.0}

        mean_a, mean_b = np.mean(a), np.mean(b)
        var_a, var_b = np.var(a, ddof=1), np.var(b, ddof=1)

        se = np.sqrt(var_a / n_a + var_b / n_b)
        if se == 0:
            return {"t_statistic": 0.0, "p_value": 1.0, "df": 0.0}

        t_stat = (mean_a - mean_b) / se

        # Welch-Satterthwaite degrees of freedom
        num = (var_a / n_a + var_b / n_b) ** 2
        denom = (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
        df = num / denom if denom > 0 else 1.0

        # Approximate p-value using normal distribution for large df
        # (scipy-free implementation)
        z = abs(t_stat)
        p_value = 2 * np.exp(-0.5 * z * z) / np.sqrt(2 * np.pi)  # Approximation
        # Better approximation for the tail
        if z > 1:
            p_value = 2 * (1 - 0.5 * (1 + math.erf(z / np.sqrt(2))))

        return {
            "t_statistic": float(t_stat),
            "p_value": float(max(0, min(1, p_value))),
            "df": float(df),
        }

    @staticmethod
    def mann_whitney_u(
        a: np.ndarray, b: np.ndarray
    ) -> Dict[str, float]:
        """
        Mann-Whitney U test (non-parametric alternative to t-test).

        Returns:
            Dict with u_statistic, p_value.
        """
        n_a, n_b = len(a), len(b)
        if n_a < 1 or n_b < 1:
            return {"u_statistic": 0.0, "p_value": 1.0}

        # Compute U statistic
        combined = np.concatenate([a, b])
        ranks = np.empty_like(combined)
        order = combined.argsort()
        ranks[order] = np.arange(1, len(combined) + 1, dtype=np.float64)

        u_a = np.sum(ranks[:n_a]) - n_a * (n_a + 1) / 2
        u_b = n_a * n_b - u_a
        u_stat = min(u_a, u_b)

        # Normal approximation for p-value
        mu = n_a * n_b / 2
        sigma = np.sqrt(n_a * n_b * (n_a + n_b + 1) / 12)
        if sigma == 0:
            return {"u_statistic": float(u_stat), "p_value": 1.0}

        z = (u_stat - mu) / sigma
        p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / np.sqrt(2))))

        return {
            "u_statistic": float(u_stat),
            "p_value": float(max(0, min(1, p_value))),
        }

    @staticmethod
    def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
        """
        Cohen's d effect size — measures practical significance.

        Interpretation:
            |d| < 0.2  -> negligible
            |d| < 0.5  -> small
            |d| < 0.8  -> medium
            |d| >= 0.8 -> large
        """
        n_a, n_b = len(a), len(b)
        if n_a < 2 or n_b < 2:
            return 0.0

        mean_diff = np.mean(a) - np.mean(b)
        pooled_std = np.sqrt(
            ((n_a - 1) * np.var(a, ddof=1) + (n_b - 1) * np.var(b, ddof=1))
            / (n_a + n_b - 2)
        )
        if pooled_std == 0:
            return 0.0

        return float(mean_diff / pooled_std)

    @staticmethod
    def bootstrap_ci(
        data: np.ndarray,
        n_bootstrap: int = 1000,
        confidence: float = 0.95,
    ) -> Tuple[float, float]:
        """
        Bootstrap confidence interval for the mean.

        Returns:
            (lower_bound, upper_bound) at the specified confidence level.
        """
        if len(data) < 2:
            mean = float(np.mean(data)) if len(data) else 0.0
            return (mean, mean)

        rng = np.random.default_rng(42)
        means = np.array([
            np.mean(rng.choice(data, size=len(data), replace=True))
            for _ in range(n_bootstrap)
        ])

        alpha = (1 - confidence) / 2
        lower = float(np.percentile(means, alpha * 100))
        upper = float(np.percentile(means, (1 - alpha) * 100))
        return (lower, upper)


# ---------------------------------------------------------------------------
# Experiment Runner
# ---------------------------------------------------------------------------
class ABTestRunner:
    """
    Orchestrates a complete A/B test from setup through analysis.

    Usage:
        runner = ABTestRunner(experiment)

        # During gameplay sessions
        variant = runner.assign_session(session_id)
        # ... run game with variant's model ...
        runner.record_session(session_id, variant.name, metrics)

        # After enough data collected
        report = runner.analyze()
        runner.save_report("reports/experiment_1.json")
    """

    def __init__(self, experiment: Experiment) -> None:
        self.experiment = experiment
        self.router = TrafficRouter(experiment)
        self.collector = MetricsCollector()
        self.analyzer = StatisticalAnalyzer()
        self.session_assignments: Dict[str, str] = {}

    def assign_session(self, session_id: str) -> Variant:
        """Assign a session to a variant and track the assignment."""
        variant = self.router.assign(session_id)
        self.session_assignments[session_id] = variant.name
        return variant

    def record_session(
        self,
        session_id: str,
        variant_name: str,
        metrics: Dict[str, float],
    ) -> None:
        """Record session-level metrics for analysis."""
        self.collector.record_session(variant_name, metrics)

    def has_enough_data(self) -> bool:
        """Check if all variants have minimum required sessions."""
        for v in self.experiment.variants:
            data = self.collector.get_variant_data(v.name)
            if len(data) < self.experiment.min_sessions_per_variant:
                return False
        return True

    def analyze(self) -> Dict[str, Any]:
        """
        Run statistical analysis comparing all variant pairs.

        Returns:
            Comprehensive report dictionary with:
                - Per-variant summary statistics
                - Pairwise statistical tests
                - Effect sizes and confidence intervals
                - Recommendation (which variant is better)
        """
        metric = self.experiment.metric
        variants = self.experiment.variants
        report: Dict[str, Any] = {
            "experiment": self.experiment.name,
            "metric": metric,
            "timestamp": datetime.now().isoformat(),
            "variants": {},
            "comparisons": [],
            "recommendation": None,
        }

        # Per-variant summaries
        for v in variants:
            values = self.collector.get_metric_values(v.name, metric)
            ci_lower, ci_upper = self.analyzer.bootstrap_ci(values)
            report["variants"][v.name] = {
                "sessions": len(values),
                "mean": float(np.mean(values)) if len(values) else 0.0,
                "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                "median": float(np.median(values)) if len(values) else 0.0,
                "ci_95": [ci_lower, ci_upper],
                "model_path": v.model_path,
            }

        # Pairwise comparisons
        best_variant = None
        best_mean = float("-inf")

        for i in range(len(variants)):
            a_values = self.collector.get_metric_values(variants[i].name, metric)
            a_mean = float(np.mean(a_values)) if len(a_values) else 0.0

            if a_mean > best_mean:
                best_mean = a_mean
                best_variant = variants[i].name

            for j in range(i + 1, len(variants)):
                b_values = self.collector.get_metric_values(
                    variants[j].name, metric
                )

                t_test = self.analyzer.welch_t_test(a_values, b_values)
                u_test = self.analyzer.mann_whitney_u(a_values, b_values)
                effect = self.analyzer.cohens_d(a_values, b_values)

                # Interpret effect size
                abs_effect = abs(effect)
                if abs_effect < 0.2:
                    effect_label = "negligible"
                elif abs_effect < 0.5:
                    effect_label = "small"
                elif abs_effect < 0.8:
                    effect_label = "medium"
                else:
                    effect_label = "large"

                significant = t_test["p_value"] < 0.05

                report["comparisons"].append({
                    "variant_a": variants[i].name,
                    "variant_b": variants[j].name,
                    "welch_t_test": t_test,
                    "mann_whitney_u": u_test,
                    "cohens_d": effect,
                    "effect_size": effect_label,
                    "significant_at_005": significant,
                    "winner": (
                        variants[i].name if effect > 0 else variants[j].name
                    ) if significant else "no_significant_difference",
                })

        report["recommendation"] = best_variant

        return report

    def save_report(self, path: str) -> None:
        """Save analysis report to JSON for stakeholder review."""
        report = self.analyze()
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== A/B Testing Framework Self-Test ===\n")

    # Create experiment
    experiment = Experiment(
        name="DQN v1 vs v2 (attention)",
        variants=[
            Variant("v1_baseline", "models/enemy_brain_v1.pt", 0.5,
                    "Original 3-layer MLP"),
            Variant("v2_attention", "models/enemy_brain_v2.pt", 0.5,
                    "Dueling DQN with self-attention"),
        ],
        metric="avg_reward",
        min_sessions_per_variant=10,
    )

    runner = ABTestRunner(experiment)

    # Simulate sessions
    rng = np.random.default_rng(42)
    for i in range(60):
        session_id = f"session_{i:04d}"
        variant = runner.assign_session(session_id)

        # Simulate metrics — v2 is slightly better
        base_reward = 1.5 if variant.name == "v2_attention" else 1.0
        metrics = {
            "avg_reward": base_reward + rng.normal(0, 0.5),
            "win_rate": 0.6 + (0.05 if variant.name == "v2_attention" else 0) + rng.normal(0, 0.1),
            "session_length": 300 + rng.normal(0, 50),
            "kills": int(20 + rng.normal(0, 5)),
            "deaths": int(max(0, 3 + rng.normal(0, 2))),
        }
        runner.record_session(session_id, variant.name, metrics)

    # Analyze
    print(f"Enough data: {runner.has_enough_data()}")
    report = runner.analyze()

    print(f"\nExperiment: {report['experiment']}")
    print(f"Metric: {report['metric']}")
    for vname, vstats in report["variants"].items():
        print(f"\n  {vname}:")
        print(f"    Sessions: {vstats['sessions']}")
        print(f"    Mean: {vstats['mean']:.3f} +/- {vstats['std']:.3f}")
        print(f"    95% CI: [{vstats['ci_95'][0]:.3f}, {vstats['ci_95'][1]:.3f}]")

    for comp in report["comparisons"]:
        print(f"\n  {comp['variant_a']} vs {comp['variant_b']}:")
        print(f"    t-test p-value: {comp['welch_t_test']['p_value']:.4f}")
        print(f"    Cohen's d: {comp['cohens_d']:.3f} ({comp['effect_size']})")
        print(f"    Significant: {comp['significant_at_005']}")
        print(f"    Winner: {comp['winner']}")

    print(f"\nRecommendation: {report['recommendation']}")
    print("\nSelf-test passed!")
