#!/usr/bin/env python3
"""
Automated Demo Recorder for Sent Below
========================================
Records a scripted demo video showcasing all player classes, combat,
AI debug overlay, and game systems. Outputs an MP4 video.

Usage:
    python record_demo.py
    python record_demo.py --output demo.mp4 --fps 30
"""

import os
import sys
import math
import time
import argparse
import numpy as np

os.environ['SDL_AUDIODRIVER'] = 'dummy'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame
import imageio.v3 as iio

from config import SCREEN_W, SCREEN_H, FPS, PLAYER_CLASSES, FLOOR_EXIT_TYPE, FLOOR_ENEMY_POOLS
from game.engine import GameEngine
from game.combat import Projectile
from game.enemies import Enemy


# ---------------------------------------------------------------------------
# Frame capture helper
# ---------------------------------------------------------------------------
def capture_frame(screen: pygame.Surface) -> np.ndarray:
    """Convert a pygame surface to a numpy RGB array for imageio."""
    raw = pygame.image.tobytes(screen, "RGB")
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(
        (screen.get_height(), screen.get_width(), 3)
    )
    return arr.copy()


def draw_section_title(screen, text, subtext=""):
    """Draw a cinematic section title card on screen."""
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((10, 10, 20, 220))
    screen.blit(overlay, (0, 0))

    cx, cy = SCREEN_W // 2, SCREEN_H // 2

    font_title = pygame.font.Font(None, 56)
    font_sub = pygame.font.Font(None, 28)

    # Title
    title_surf = font_title.render(text, True, (220, 195, 55))
    screen.blit(title_surf, (cx - title_surf.get_width() // 2, cy - 40))

    # Decorative lines
    line_w = max(title_surf.get_width() + 40, 300)
    pygame.draw.line(screen, (120, 100, 40),
                     (cx - line_w // 2, cy - 50), (cx + line_w // 2, cy - 50), 2)
    pygame.draw.line(screen, (120, 100, 40),
                     (cx - line_w // 2, cy + 25), (cx + line_w // 2, cy + 25), 2)

    if subtext:
        sub_surf = font_sub.render(subtext, True, (160, 160, 180))
        screen.blit(sub_surf, (cx - sub_surf.get_width() // 2, cy + 40))


def draw_overlay_text(screen, text, y=None, color=(220, 220, 240), size=22):
    """Draw overlay text at the top or custom Y position."""
    font = pygame.font.Font(None, size)
    surf = font.render(text, True, color)
    x = SCREEN_W // 2 - surf.get_width() // 2
    if y is None:
        y = 10
    screen.blit(surf, (x, y))


# ---------------------------------------------------------------------------
# Demo Scenes
# ---------------------------------------------------------------------------
class DemoRecorder:
    def __init__(self, output_path: str = "demo.mp4", video_fps: int = 30):
        self.output_path = output_path
        self.video_fps = video_fps
        self.frames = []
        self.engine = None

        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Sent Below - Demo Recording")

    def capture(self, n=1):
        """Capture current screen frame(s)."""
        frame = capture_frame(self.screen)
        for _ in range(n):
            self.frames.append(frame)

    def title_card(self, text, subtext="", duration_sec=2.5):
        """Record a title card screen."""
        frames_count = int(duration_sec * self.video_fps)
        for i in range(frames_count):
            self.screen.fill((10, 10, 20))
            draw_section_title(self.screen, text, subtext)
            pygame.display.flip()
            self.capture()

    def simulate_frames(self, n_frames, move_dx=0, move_dy=0,
                        attack_target=None, use_ability=None,
                        show_debug=False, overlay_text=None):
        """
        Run the game engine for N frames with simulated inputs.
        Captures each frame for the video.
        """
        for i in range(n_frames):
            dt = 1.0 / 60.0

            # Simulate movement by directly moving the player
            if (move_dx != 0 or move_dy != 0) and self.engine.player:
                self.engine.player.move(
                    move_dx, move_dy, self.engine.floor, dt
                )

            # Simulate attack toward nearest enemy
            if attack_target and self.engine.player and i % 8 == 0:
                nearby = self.engine.floor.get_nearby_enemies(
                    self.engine.player.x, self.engine.player.y, 200
                )
                if nearby:
                    enemy = nearby[0]
                    results = self.engine.player.basic_attack(
                        (enemy.x, enemy.y), nearby
                    )
                    self.engine._process_attack_results(results)

            # Use ability periodically
            if use_ability is not None and self.engine.player and i % 30 == 0:
                nearby = self.engine.floor.get_nearby_enemies(
                    self.engine.player.x, self.engine.player.y, 500
                )
                if nearby:
                    target = (nearby[0].x, nearby[0].y)
                else:
                    facing = self.engine.player.facing
                    target = (
                        self.engine.player.x + facing[0] * 100,
                        self.engine.player.y + facing[1] * 100,
                    )
                results = self.engine.player.use_ability(
                    use_ability, target, nearby
                )
                self.engine._process_ability_results(results)

            # Set debug overlay
            self.engine.show_ai_debug = show_debug

            # Update and render
            self.engine._update(dt)
            self.engine._render()

            if overlay_text:
                draw_overlay_text(self.screen, overlay_text, y=SCREEN_H - 35,
                                  color=(180, 180, 200), size=20)

            pygame.display.flip()
            self.capture()

    def move_toward_enemies(self, max_frames=300, show_debug=False,
                            use_ability=None, overlay_text=None,
                            cycle_abilities=False):
        """Move the player toward the nearest enemy and fight."""
        ability_cycle_idx = 0

        for i in range(max_frames):
            dt = 1.0 / 60.0

            if not self.engine.player or not self.engine.player.alive:
                break

            # Keep MP topped up during demo
            self.engine.player.mp = self.engine.player.max_mp

            # Find nearest enemy
            nearby = self.engine.floor.get_nearby_enemies(
                self.engine.player.x, self.engine.player.y, 800
            )
            alive_enemies = [e for e in nearby if e.alive]

            if alive_enemies:
                target = alive_enemies[0]
                edx = target.x - self.engine.player.x
                edy = target.y - self.engine.player.y
                dist = math.sqrt(edx * edx + edy * edy)

                if dist > 40:
                    # Move toward enemy
                    ndx = edx / dist if dist > 0 else 0
                    ndy = edy / dist if dist > 0 else 0
                    self.engine.player.move(ndx, ndy, self.engine.floor, dt)
                else:
                    # Attack!
                    atk_nearby = self.engine.floor.get_nearby_enemies(
                        self.engine.player.x, self.engine.player.y, 200
                    )
                    results = self.engine.player.basic_attack(
                        (target.x, target.y), atk_nearby
                    )
                    self.engine._process_attack_results(results)

                # Use ability when close
                if dist < 250 and i % 20 == 0:
                    if cycle_abilities:
                        ab_idx = ability_cycle_idx % 5
                        ability_cycle_idx += 1
                    elif use_ability is not None:
                        ab_idx = use_ability
                    else:
                        ab_idx = None

                    if ab_idx is not None:
                        # Reset cooldowns for demo
                        for cd_key in self.engine.player.cooldowns:
                            self.engine.player.cooldowns[cd_key] = 0
                        results = self.engine.player.use_ability(
                            ab_idx, (target.x, target.y), alive_enemies
                        )
                        self.engine._process_ability_results(results)
            else:
                # No enemies nearby — move toward center of next undiscovered room
                rooms = [r for r in self.engine.floor.rooms if not r.discovered]
                if rooms:
                    room = rooms[0]
                    rx = room.pixel_center_x
                    ry = room.pixel_center_y
                    rdx = rx - self.engine.player.x
                    rdy = ry - self.engine.player.y
                    rdist = math.sqrt(rdx * rdx + rdy * rdy)
                    if rdist > 10:
                        self.engine.player.move(
                            rdx / rdist, rdy / rdist, self.engine.floor, dt
                        )

            self.engine.show_ai_debug = show_debug
            self.engine._update(dt)
            self.engine._render()

            if overlay_text:
                draw_overlay_text(self.screen, overlay_text, y=SCREEN_H - 35,
                                  color=(180, 180, 200), size=20)

            pygame.display.flip()
            self.capture()

    def record_intro(self):
        """Record the intro title sequence."""
        self.title_card(
            "S E N T   B E L O W",
            "Adaptive AI Dungeon Crawler  |  PyTorch  |  Deep RL",
            duration_sec=3.0,
        )
        self.title_card(
            "ML-Powered Game AI",
            "Dueling DQN  |  Dynamic Difficulty  |  Content Recommendation",
            duration_sec=2.5,
        )

    def _teleport_to_enemies(self):
        """Teleport player to the room with the most enemies."""
        best_room = None
        best_count = 0
        for room in self.engine.floor.rooms:
            count = sum(1 for e in room.enemies if e.alive)
            if count > best_count:
                best_count = count
                best_room = room
        if best_room:
            self.engine.player.x = float(best_room.pixel_center_x)
            self.engine.player.y = float(best_room.pixel_center_y)
        # Discover all rooms for the minimap
        for r in self.engine.floor.rooms:
            r.discovered = True

    def _spawn_enemies_near_player(self, count=6, hp_mult=5):
        """Spawn a ring of diverse enemies around the player for demo combat."""
        if not self.engine.player or not self.engine.floor:
            return

        px, py = self.engine.player.x, self.engine.player.y
        pool = FLOOR_ENEMY_POOLS.get(3, {})
        names = pool.get('trash', ['goblin', 'skeleton', 'slime'])
        elite_names = pool.get('elite', [])

        from config import TILE_SIZE
        # Find which room the player is in
        player_room = None
        for room in self.engine.floor.rooms:
            rx = room.x * TILE_SIZE
            ry = room.y * TILE_SIZE
            rw = room.w * TILE_SIZE
            rh = room.h * TILE_SIZE
            if rx <= px <= rx + rw and ry <= py <= ry + rh:
                player_room = room
                break
        if player_room is None:
            # Fallback: use room closest to player
            player_room = min(
                self.engine.floor.rooms,
                key=lambda r: (r.pixel_center_x - px)**2 + (r.pixel_center_y - py)**2
            )

        import random
        for i in range(count):
            angle = (2 * math.pi * i) / count
            dist = 80 + random.random() * 40
            ex = px + math.cos(angle) * dist
            ey = py + math.sin(angle) * dist

            # Mix in an elite every 3rd enemy
            if i % 3 == 0 and elite_names:
                ename = random.choice(elite_names)
            else:
                ename = random.choice(names)

            enemy = Enemy(ename, ex, ey, floor_num=1, difficulty_mod=1.0)
            enemy.hp *= hp_mult
            enemy.max_hp = enemy.hp
            player_room.enemies.append(enemy)

    def record_class_showcase(self, class_name, ability_idx, duration_frames=300):
        """Record gameplay for a specific class."""
        # Create fresh engine state
        self.engine = GameEngine()
        self.engine.screen = self.screen
        self.engine.renderer.screen = self.screen

        self.engine._start_game(class_name)
        self.engine._generate_floor()
        self.engine.state = 'playing'

        # Make player tanky for the demo
        self.engine.player.hp = self.engine.player.max_hp * 5
        self.engine.player.max_hp = self.engine.player.hp
        self.engine.player.mp = 999
        self.engine.player.max_mp = 999

        # Teleport to enemies for immediate action
        self._teleport_to_enemies()
        # Spawn a crowd of enemies right around the player
        self._spawn_enemies_near_player(count=8, hp_mult=6)

        class_display = class_name.upper()
        abilities = PLAYER_CLASSES[class_name]['abilities']
        ability_name = abilities[ability_idx].replace('_', ' ').title()

        # Show class title card
        self.title_card(
            f"{class_display}",
            f"Ability Showcase: {ability_name}",
            duration_sec=1.5,
        )

        # Combat showcasing the featured ability
        self.move_toward_enemies(
            max_frames=duration_frames // 2,
            show_debug=False,
            use_ability=ability_idx,
            overlay_text=f"{class_display}  —  {ability_name}",
        )

        # Then cycle through all 5 abilities in second half
        self._spawn_enemies_near_player(count=8, hp_mult=6)
        self.engine.player.mp = 999
        self.move_toward_enemies(
            max_frames=duration_frames // 2,
            show_debug=False,
            use_ability=None,  # cycle all
            cycle_abilities=True,
            overlay_text=f"{class_display}  —  Full Ability Rotation",
        )

    def record_ai_debug(self):
        """Record the AI debug overlay during combat."""
        self.title_card(
            "AI Debug Overlay",
            "DQN Training Stats  |  DDA Metrics  |  Real-Time Learning",
            duration_sec=2.0,
        )

        self.engine = GameEngine()
        self.engine.screen = self.screen
        self.engine.renderer.screen = self.screen
        self.engine._start_game('mage')
        self.engine._generate_floor()
        self.engine.state = 'playing'
        self.engine.player.hp = self.engine.player.max_hp * 5
        self.engine.player.max_hp = self.engine.player.hp
        self.engine.player.mp = 999
        self.engine.player.max_mp = 999

        # Teleport into action and spawn a crowd
        self._teleport_to_enemies()
        self._spawn_enemies_near_player(count=10, hp_mult=8)

        # Pre-fill training data so stats are interesting
        for _ in range(500):
            s = np.random.rand(10).astype(np.float32)
            self.engine.enemy_brain.store_experience(
                s, np.random.randint(7), np.random.randn(),
                np.random.rand(10).astype(np.float32), False
            )
        for _ in range(50):
            self.engine.enemy_brain.train_step()

        self.move_toward_enemies(
            max_frames=350,
            show_debug=True,
            use_ability=0,
            cycle_abilities=True,
            overlay_text="AI Debug: DQN Training, DDA Metrics, Real-Time Adaptation",
        )

    def record_floor_transition(self):
        """Record floor transition screens for different exit types."""
        self.title_card(
            "Floor Variety",
            "Boss  |  Survival  |  Elite Formation  |  Trap Gauntlet  |  Puzzle Gate",
            duration_sec=2.0,
        )

        for floor_num in [1, 2, 3, 4, 5, 6]:
            exit_type = FLOOR_EXIT_TYPE.get(floor_num, 'boss')
            # Render the transition screen
            for _ in range(int(1.2 * self.video_fps)):
                self.engine.renderer.render_floor_transition(
                    floor_num, exit_type=exit_type
                )
                draw_overlay_text(
                    self.screen,
                    f"Floor {floor_num} — Exit: {exit_type.replace('_', ' ').title()}",
                    y=SCREEN_H - 35, color=(180, 180, 200), size=20,
                )
                pygame.display.flip()
                self.capture()

    def record_pause_screen(self):
        """Record the pause screen with controls."""
        self.engine.state = 'paused'
        self.engine._render()
        draw_overlay_text(self.screen, "Game Controls & Floor Info",
                          y=SCREEN_H - 35, color=(180, 180, 200), size=20)
        pygame.display.flip()
        self.capture(n=int(2.0 * self.video_fps))

    def record_outro(self):
        """Record the closing title."""
        self.title_card(
            "S E N T   B E L O W",
            "PyTorch DQN  |  Docker  |  FastAPI  |  AWS/GCP/Azure  |  TensorBoard",
            duration_sec=2.0,
        )

        # Tech stack summary card
        frames_count = int(4.0 * self.video_fps)
        font_title = pygame.font.Font(None, 44)
        font_item = pygame.font.Font(None, 24)

        tech_items = [
            ("Deep RL", "Dueling DQN + Self-Attention for enemy AI"),
            ("Player Modeling", "Neural DDA targeting 60% survival (flow zone)"),
            ("Content Rec.", "Embedding model for room & loot recommendation"),
            ("Training", "Offline pipeline + TensorBoard + LR scheduling"),
            ("Serving", "FastAPI REST API for real-time inference"),
            ("Docker", "Multi-stage build (train / serve / game)"),
            ("Cloud", "AWS ECS, GCP Cloud Run, Azure ACI configs"),
            ("CI/CD", "GitHub Actions: test -> train -> benchmark -> deploy"),
            ("A/B Testing", "Statistical model comparison framework"),
            ("Data Pipeline", "Event logging -> PyTorch Dataset -> DataLoader"),
        ]

        for f in range(frames_count):
            self.screen.fill((10, 10, 20))
            cx = SCREEN_W // 2

            title = font_title.render("Technical Stack", True, (220, 195, 55))
            self.screen.blit(title, (cx - title.get_width() // 2, 40))

            pygame.draw.line(self.screen, (120, 100, 40),
                             (cx - 200, 80), (cx + 200, 80), 2)

            for i, (label, desc) in enumerate(tech_items):
                y = 105 + i * 58

                # Fade-in effect
                alpha_progress = min(1.0, (f / self.video_fps - i * 0.15) * 3)
                if alpha_progress <= 0:
                    continue

                alpha = int(255 * min(1.0, alpha_progress))

                label_surf = font_item.render(f"  {label}", True, (220, 195, 55))
                desc_surf = font_item.render(f"    {desc}", True, (160, 160, 180))

                label_surf.set_alpha(alpha)
                desc_surf.set_alpha(alpha)

                self.screen.blit(label_surf, (100, y))
                self.screen.blit(desc_surf, (100, y + 22))

                # Bullet
                if alpha_progress > 0.5:
                    pygame.draw.circle(self.screen, (220, 195, 55),
                                       (90, y + 8), 3)

            pygame.display.flip()
            self.capture()

    def record_full_demo(self):
        """Record the complete demo video."""
        print("=" * 60)
        print("  Sent Below — Demo Recording")
        print("=" * 60)

        # Intro
        print("  [1/8] Recording intro...")
        self.record_intro()

        # Class showcases
        classes_and_abilities = [
            ('warrior', 2, "Shield Wall + Sword Combat"),
            ('mage', 0, "Fireball — Burn Projectiles"),
            ('rogue', 4, "Blade Flurry — Spinning Blade Projectiles"),
            ('healer', 1, "Holy Light — Radiant Beam Projectiles"),
        ]

        for i, (cls, ability, desc) in enumerate(classes_and_abilities):
            print(f"  [{i+2}/8] Recording {cls} — {desc}...")
            self.record_class_showcase(cls, ability, duration_frames=400)

        # AI Debug
        print("  [6/8] Recording AI debug overlay...")
        self.record_ai_debug()

        # Floor transitions
        print("  [7/8] Recording floor transitions...")
        self.record_floor_transition()

        # Pause + Outro
        print("  [8/8] Recording outro...")
        self.record_pause_screen()
        self.record_outro()

        # Export video
        total_frames = len(self.frames)
        duration = total_frames / self.video_fps
        print(f"\n  Total frames: {total_frames}")
        print(f"  Duration: {duration:.1f}s at {self.video_fps}fps")
        print(f"  Exporting to {self.output_path}...")

        with iio.imopen(self.output_path, "w", plugin="pyav") as writer:
            writer.init_video_stream("libx264", fps=self.video_fps)
            for frame in self.frames:
                writer.write_frame(frame)

        file_size = os.path.getsize(self.output_path) / (1024 * 1024)
        print(f"  Output: {self.output_path} ({file_size:.1f} MB)")
        print("=" * 60)
        print("  Done!")
        print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Record Sent Below demo video")
    parser.add_argument("--output", default="demo.mp4", help="Output video path")
    parser.add_argument("--fps", type=int, default=30, help="Video framerate")
    args = parser.parse_args()

    recorder = DemoRecorder(output_path=args.output, video_fps=args.fps)
    recorder.record_full_demo()
    pygame.quit()


if __name__ == "__main__":
    main()
