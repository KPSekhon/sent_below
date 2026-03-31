#!/usr/bin/env python3
"""
Sent Below - A Dungeon Crawler with Adaptive AI
=================================================

Descend through 6 floors of procedurally generated dungeons.
Each floor escalates from teaching encounters to punishing endgame threats.

Core Systems:
  - Adaptive Enemy AI      PyTorch DQN agents that learn from combat
  - Dynamic Difficulty      Neural player modeling adjusts challenge in real time
  - Smart Content           ML-driven room and loot recommendation
  - Procedural Dungeons     BSP room placement with MST corridor generation

Gameplay:
  - 4 Classes               Warrior, Mage, Rogue, Healer - each with 5 abilities
  - 18 Enemy Types          Trash, Elite, and Boss tiers with unique AI behaviors
  - 10 Room Types           Combat, traps, puzzles, survival, merchant, hidden, and more
  - Progression             XP scaling, class-specific stat gains, gold economy
  - Equipment               Weapons, armour, accessories across 5 rarity tiers
  - Boss Mechanics          Enrage, counter, summon, hazard, phase, and dragon fights

Controls:
  Movement        WASD / Arrow Keys
  Attack          Left Click
  Abilities       1-5
  Pick Up / Buy   E
  Use Stairs      F
  Inventory       I / Tab
  Drop Item       Shift + 1-9  or  Q (drop last)
  Sell Item       Ctrl + 1-9   or  S (sell last)
  AI Debug        P
  Pause           ESC
"""

import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    # Check dependencies
    try:
        import pygame
    except ImportError:
        print("pygame not found. Install with: pip install pygame")
        sys.exit(1)

    try:
        import torch
        print(f"  PyTorch {torch.__version__} loaded - adaptive AI active")
    except ImportError:
        print("  PyTorch not found - using fallback AI behavior")
        print("  Install with: pip install torch")

    try:
        import numpy
    except ImportError:
        print("numpy not found. Install with: pip install numpy")
        sys.exit(1)

    print()
    print("  ============================================")
    print("               S E N T   B E L O W            ")
    print("  ============================================")
    print()
    print("  Movement ........... WASD / Arrow Keys")
    print("  Attack ............. Left Click")
    print("  Abilities .......... 1  2  3  4  5")
    print("  Pick Up / Buy ...... E")
    print("  Use Stairs ......... F")
    print("  Inventory .......... I / Tab")
    print("  Drop Item .......... Shift+1-9  |  Q")
    print("  Sell Item .......... Ctrl+1-9   |  S")
    print("  AI Debug ........... P")
    print("  Pause .............. ESC")
    print()
    print("  Floors 1-2  Learn the enemies")
    print("  Floors 3-4  Handle the combinations")
    print("  Floors 5-6  Survive the punishment")
    print()
    print("  Starting...\n")

    from game.engine import GameEngine
    engine = GameEngine()
    engine.run()

if __name__ == "__main__":
    main()
