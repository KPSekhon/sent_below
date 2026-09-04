"""
Offline training, benchmarking, and artefact publication.
=========================================================

Modules:
    train_pipeline  Headless training against SimulatedCombatEnv, a light
                    stand-in for the game that models combat with four
                    variables and simplified rules. It is not a faithful
                    simulation, but it uses the same 10-value state vector,
                    the same 7 actions, and the same reward function as the
                    game -- so the artefact it produces drops straight in.
                    Handles TensorBoard logging, checkpointing, early
                    stopping, and ONNX export.

    benchmark       Latency, throughput, and memory profiling against the
                    60fps frame budget. CI fails the build if inference
                    exceeds half of it.

    aws_io          S3 upload/download plus the DynamoDB model registry.
                    S3 stores the artefacts under a timestamped prefix and
                    nothing is overwritten; DynamoDB indexes them by
                    (model_name, version) with the run's metrics attached,
                    so the newest version can be found without listing the
                    bucket or opening checkpoint files.

Training exists because reinforcement learning needs far more combat
encounters than anyone can play by hand. The game then warm-starts from the
resulting checkpoint and keeps adapting to the individual player.
"""
