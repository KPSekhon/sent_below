"""
Game runtime: the loop, the world, and everything drawn on screen.
==================================================================

Modules:
    engine     Game loop and state machine. Owns the shared EnemyBrain and
               AIDirector, warm-starting the brain from the trained checkpoint
               when one exists. Also where enemy transitions are scored and
               pushed into the replay buffer.

    player     Player classes, the 20 abilities, stats, and status effects.

    enemies    18 enemy types across trash, elite, and boss tiers. Behaviour
               trees for the scripted archetypes, plus the DQN path for
               generic enemies. Builds the 10-value state vector the model
               consumes.

    dungeon    Procedural floor generation: BSP room placement, MST corridor
               connection, and room typing.

    combat     Damage calculation, projectiles, items, and loot tables.

    renderer   Drawing, camera, particles, HUD, and the AI debug overlay
               bound to the P key.

The game runs at 60fps, which leaves a 16.7ms frame budget. Model inference
is expected to stay well inside it -- training/benchmark.py asserts the
ceiling and CI fails the build if it is breached.
"""
