import pygame
import math

from config import SCREEN_W, SCREEN_H, TILE_SIZE, COLORS, PLAYER_CLASSES, ENEMY_VISUALS, PLAYER_VISUALS


class Camera:
    def __init__(self):
        self.x = 0
        self.y = 0
        self.target_x = 0
        self.target_y = 0
        self.smooth_speed = 5.0

    def update(self, target_x, target_y, dt):
        self.target_x = target_x - SCREEN_W // 2
        self.target_y = target_y - SCREEN_H // 2
        # Smooth follow
        self.x += (self.target_x - self.x) * self.smooth_speed * dt
        self.y += (self.target_y - self.y) * self.smooth_speed * dt

    def apply(self, x, y):
        return int(x - self.x), int(y - self.y)


class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.camera = Camera()
        self.font_large = pygame.font.Font(None, 48)
        self.font_medium = pygame.font.Font(None, 32)
        self.font_small = pygame.font.Font(None, 24)
        self.font_tiny = pygame.font.Font(None, 18)
        self.minimap_size = 160
        self.minimap_surface = pygame.Surface((self.minimap_size, self.minimap_size))
        self.particles = []  # list of (x, y, dx, dy, color, lifetime)
        self.screen_shake = 0
        self.shake_intensity = 0

    def update(self, player_x, player_y, dt):
        self.camera.update(player_x, player_y, dt)
        # Update screen shake
        if self.screen_shake > 0:
            self.screen_shake -= dt
        # Update particles
        self.particles = [
            (x + dx * dt, y + dy * dt, dx, dy * 0.98, c, l - dt)
            for x, y, dx, dy, c, l in self.particles
            if l > 0
        ]

    def add_shake(self, intensity=5, duration=0.2):
        self.screen_shake = duration
        self.shake_intensity = intensity

    def add_particles(self, x, y, color, count=10):
        import random

        for _ in range(count):
            dx = random.uniform(-100, 100)
            dy = random.uniform(-100, 100)
            self.particles.append(
                (x, y, dx, dy, color, random.uniform(0.3, 0.8))
            )

    def render_game(
        self, player, floor, projectiles, damage_numbers, game_time, ai_stats=None,
        zone_effects=None
    ):
        """Main render function called each frame."""
        self.screen.fill((10, 10, 15))  # dark background

        # Apply screen shake offset
        shake_x, shake_y = 0, 0
        if self.screen_shake > 0:
            import random

            shake_x = random.randint(-self.shake_intensity, self.shake_intensity)
            shake_y = random.randint(-self.shake_intensity, self.shake_intensity)

        # Draw dungeon tiles
        self._draw_tiles(floor, shake_x, shake_y)

        # Draw zone effects (ground layer: hazards, smoke, shields)
        self._draw_zone_effects(zone_effects or [], shake_x, shake_y)

        # Draw items on ground
        self._draw_items(floor, shake_x, shake_y)

        # Draw traps
        self._draw_traps(floor, shake_x, shake_y, game_time)

        # Draw puzzle elements
        self._draw_puzzles(floor, shake_x, shake_y)

        # Draw enemies
        self._draw_enemies(floor, shake_x, shake_y)

        # Draw player
        self._draw_player(player, shake_x, shake_y)

        # Draw projectiles
        self._draw_projectiles(projectiles, shake_x, shake_y)

        # Draw particles
        self._draw_particles(shake_x, shake_y)

        # Draw damage numbers
        self._draw_damage_numbers(damage_numbers, shake_x, shake_y)

        # Draw HUD (not affected by camera)
        self._draw_hud(player, floor, game_time, ai_stats)

        # Draw minimap
        self._draw_minimap(player, floor)

    def _draw_tiles(self, floor, sx, sy):
        """Draw visible dungeon tiles."""
        # Calculate visible tile range
        cam_tx = int(self.camera.x // TILE_SIZE) - 1
        cam_ty = int(self.camera.y // TILE_SIZE) - 1
        tiles_x = SCREEN_W // TILE_SIZE + 3
        tiles_y = SCREEN_H // TILE_SIZE + 3

        for ty in range(max(0, cam_ty), min(floor.height, cam_ty + tiles_y)):
            for tx in range(max(0, cam_tx), min(floor.width, cam_tx + tiles_x)):
                tile = floor.grid[ty][tx]
                if tile == 0:
                    continue  # wall - don't draw (black background)

                screen_x, screen_y = self.camera.apply(
                    tx * TILE_SIZE, ty * TILE_SIZE
                )
                screen_x += sx
                screen_y += sy

                rect = pygame.Rect(screen_x, screen_y, TILE_SIZE, TILE_SIZE)

                if tile == 1:  # floor
                    # Subtle checkerboard pattern
                    if (tx + ty) % 2 == 0:
                        color = (35, 35, 45)
                    else:
                        color = (30, 30, 40)
                    pygame.draw.rect(self.screen, color, rect)
                elif tile == 2:  # door
                    pygame.draw.rect(self.screen, (80, 60, 30), rect)
                elif tile == 3:  # trap tile
                    pygame.draw.rect(self.screen, (35, 25, 25), rect)
                    # Draw trap indicator
                    pygame.draw.circle(
                        self.screen,
                        (180, 50, 50),
                        (screen_x + TILE_SIZE // 2, screen_y + TILE_SIZE // 2),
                        4,
                    )
                elif tile == 4:  # stairs
                    pygame.draw.rect(self.screen, (30, 30, 40), rect)
                    # Draw stairs symbol
                    pygame.draw.polygon(
                        self.screen,
                        (200, 200, 50),
                        [
                            (screen_x + 8, screen_y + 24),
                            (screen_x + 16, screen_y + 8),
                            (screen_x + 24, screen_y + 24),
                        ],
                    )

                # Draw wall borders for floor tiles adjacent to walls
                if tile >= 1:
                    if ty > 0 and floor.grid[ty - 1][tx] == 0:
                        pygame.draw.line(
                            self.screen,
                            (60, 60, 70),
                            (screen_x, screen_y),
                            (screen_x + TILE_SIZE, screen_y),
                            2,
                        )
                    if ty < floor.height - 1 and floor.grid[ty + 1][tx] == 0:
                        pygame.draw.line(
                            self.screen,
                            (60, 60, 70),
                            (screen_x, screen_y + TILE_SIZE),
                            (screen_x + TILE_SIZE, screen_y + TILE_SIZE),
                            2,
                        )
                    if tx > 0 and floor.grid[ty][tx - 1] == 0:
                        pygame.draw.line(
                            self.screen,
                            (60, 60, 70),
                            (screen_x, screen_y),
                            (screen_x, screen_y + TILE_SIZE),
                            2,
                        )
                    if tx < floor.width - 1 and floor.grid[ty][tx + 1] == 0:
                        pygame.draw.line(
                            self.screen,
                            (60, 60, 70),
                            (screen_x + TILE_SIZE, screen_y),
                            (screen_x + TILE_SIZE, screen_y + TILE_SIZE),
                            2,
                        )

    def _draw_items(self, floor, sx, sy):
        for room in floor.rooms:
            for item in room.items:
                ix, iy = self.camera.apply(item.x, item.y)
                ix += sx
                iy += sy
                # Draw item as small colored diamond
                rarity_colors = {
                    "common": (200, 200, 200),
                    "uncommon": (100, 255, 100),
                    "rare": (100, 100, 255),
                    "epic": (200, 50, 255),
                    "legendary": (255, 200, 50),
                }
                color = rarity_colors.get(item.rarity, (200, 200, 200))
                # Bobbing animation
                bob = (
                    math.sin(pygame.time.get_ticks() * 0.005 + hash(item.name)) * 3
                )
                points = [
                    (ix, iy - 6 + bob),
                    (ix + 6, iy + bob),
                    (ix, iy + 6 + bob),
                    (ix - 6, iy + bob),
                ]
                pygame.draw.polygon(self.screen, color, points)
                # Glow for rare+
                if item.rarity in ("rare", "epic", "legendary"):
                    glow_surf = pygame.Surface((20, 20), pygame.SRCALPHA)
                    pygame.draw.circle(glow_surf, (*color, 50), (10, 10), 10)
                    self.screen.blit(glow_surf, (ix - 10, iy - 10 + bob))

    def _draw_traps(self, floor, sx, sy, game_time=0.0):
        """Draw trap tiles with warning/active pulsing based on timing patterns."""
        ticks = pygame.time.get_ticks()
        for room in floor.rooms:
            if room.room_type != 'trap':
                continue
            template_name = getattr(room, 'trap_template', None)
            if not template_name:
                continue
            from config import TRAP_TEMPLATES
            template = TRAP_TEMPLATES.get(template_name, {})
            cycle_time = template.get('cycle_time', 2.0)
            pattern = template.get('pattern', 'lanes')
            hazard = template.get('hazard_type', 'spike')

            # Hazard colour map
            haz_colors = {
                'arrow': (200, 180, 80),
                'poison': (80, 200, 60),
                'spike': (200, 80, 80),
                'fire': (255, 120, 30),
                'crusher': (160, 160, 180),
                'mixed': (200, 150, 80),
            }
            haz_c = haz_colors.get(hazard, (200, 80, 80))

            for trap_x, trap_y, _ in room.traps:
                screen_x, screen_y = self.camera.apply(
                    trap_x * TILE_SIZE, trap_y * TILE_SIZE)
                screen_x += sx
                screen_y += sy

                # Determine if this tile is currently active
                if cycle_time > 0:
                    cycle_phase = (game_time % cycle_time) / cycle_time
                else:
                    cycle_phase = 0

                active = True
                if pattern == 'lanes':
                    row_even = (trap_y % 2 == 0)
                    active = (cycle_phase < 0.5) == row_even
                elif pattern == 'checkerboard':
                    flip = int(game_time / cycle_time) % 2
                    active = ((trap_x + trap_y) % 2 == flip)
                elif pattern in ('sequential', 'timing'):
                    col_phase = (trap_x - room.x) / max(room.w, 1)
                    active = abs(cycle_phase - col_phase) < 0.2

                if active:
                    # Active: bright pulsing danger
                    pulse = 0.6 + 0.4 * math.sin(ticks * 0.01)
                    alpha = int(120 * pulse)
                    trap_surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                    trap_surf.fill((*haz_c, alpha))
                    self.screen.blit(trap_surf, (screen_x, screen_y))
                    # Danger indicator
                    pygame.draw.circle(self.screen, haz_c,
                                       (screen_x + TILE_SIZE // 2, screen_y + TILE_SIZE // 2), 3)
                else:
                    # Inactive: very faint warning
                    trap_surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                    trap_surf.fill((*haz_c, 20))
                    self.screen.blit(trap_surf, (screen_x, screen_y))

    def _draw_puzzles(self, floor, sx, sy):
        ticks = pygame.time.get_ticks()
        for room in floor.rooms:
            ps = room.puzzle_state
            if not ps or ps.get('solved', False):
                continue
            if room.room_type not in ('puzzle', 'trap'):
                continue

            plates = ps.get("plates", [])
            activated = ps.get("activated", [])
            correct_order = ps.get("correct_order")
            clue_type = ps.get("clue_type", "glow")
            template = ps.get("puzzle_template", "")

            for i, plate in enumerate(plates):
                if isinstance(plate, tuple) and len(plate) == 2:
                    px, py = plate
                else:
                    continue
                screen_x, screen_y = self.camera.apply(px * TILE_SIZE, py * TILE_SIZE)
                screen_x += sx
                screen_y += sy

                is_activated = activated[i] if i < len(activated) else False

                # Base plate colour
                if is_activated:
                    color = (50, 220, 50)
                else:
                    # Pulse glow for unactivated plates
                    pulse = 0.6 + 0.4 * math.sin(ticks * 0.004 + i * 1.5)
                    color = (int(200 * pulse), int(200 * pulse), int(50 * pulse))

                # Draw plate/rune/statue
                pygame.draw.rect(self.screen, color,
                                 (screen_x + 3, screen_y + 3, TILE_SIZE - 6, TILE_SIZE - 6), 3)

                # Clue rendering
                if clue_type in ('wall_symbols', 'numbers') and correct_order is not None:
                    # Show the step number this plate corresponds to
                    for step_idx, plate_idx in enumerate(correct_order):
                        if plate_idx == i and not is_activated:
                            num_surf = self.font_tiny.render(str(step_idx + 1), True, (255, 255, 200))
                            self.screen.blit(num_surf,
                                             (screen_x + TILE_SIZE // 2 - num_surf.get_width() // 2,
                                              screen_y + TILE_SIZE // 2 - num_surf.get_height() // 2))
                            break
                elif clue_type == 'colour' and not is_activated:
                    # Element braziers: coloured inner glow
                    elem_colors = [(255, 100, 30), (80, 180, 255), (255, 255, 80)]
                    ec = elem_colors[i % len(elem_colors)]
                    inner = pygame.Surface((TILE_SIZE - 12, TILE_SIZE - 12), pygame.SRCALPHA)
                    pygame.draw.rect(inner, (*ec, 80), inner.get_rect())
                    self.screen.blit(inner, (screen_x + 6, screen_y + 6))
                elif clue_type == 'glow' and not is_activated:
                    # Subtle glow pulse
                    glow_r = int(TILE_SIZE * 0.6 + 4 * math.sin(ticks * 0.005 + i))
                    glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
                    pygame.draw.circle(glow_surf, (200, 200, 100, 30), (glow_r, glow_r), glow_r)
                    self.screen.blit(glow_surf,
                                     (screen_x + TILE_SIZE // 2 - glow_r,
                                      screen_y + TILE_SIZE // 2 - glow_r))

            # Safe-path puzzle: draw safe tiles with subtle highlight
            safe_tiles = ps.get('safe_tiles')
            if safe_tiles:
                for stx, sty in safe_tiles:
                    sx2, sy2 = self.camera.apply(stx * TILE_SIZE, sty * TILE_SIZE)
                    sx2 += sx
                    sy2 += sy
                    pulse = 0.3 + 0.2 * math.sin(ticks * 0.003 + stx + sty)
                    safe_surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                    safe_surf.fill((80, 200, 80, int(30 * pulse)))
                    self.screen.blit(safe_surf, (sx2, sy2))

    def _draw_zone_effects(self, zones, sx, sy):
        """Draw zone effects like smoke bombs, divine shields, hazard zones, meteor targets."""
        for zone in zones:
            zx, zy = self.camera.apply(zone['x'], zone['y'])
            zx += sx
            zy += sy
            radius = zone['radius']
            ztype = zone['type']

            surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)

            if ztype == 'hazard':
                # Pulsing red circle
                pulse = 0.5 + 0.3 * math.sin(pygame.time.get_ticks() * 0.005)
                alpha = int(60 * pulse)
                pygame.draw.circle(surf, (200, 50, 30, alpha), (radius, radius), radius)
                pygame.draw.circle(surf, (255, 80, 40, 100), (radius, radius), radius, 2)
            elif ztype == 'smoke':
                # ROGUE SMOKE BOMB: dark swirling cloud
                t = pygame.time.get_ticks()
                alpha = int(100 * min(1.0, zone['duration'] / max(zone.get('duration', 1), 0.1)))
                alpha = min(100, max(20, alpha))
                pygame.draw.circle(surf, (80, 80, 100, alpha), (radius, radius), radius)
                # Swirling tendrils
                for i in range(4):
                    angle = t * 0.003 + i * 1.571
                    inner_r = int(radius * 0.6)
                    tx = radius + int(inner_r * math.cos(angle))
                    ty = radius + int(inner_r * math.sin(angle))
                    pygame.draw.circle(surf, (60, 60, 80, alpha // 2), (tx, ty), radius // 3)
            elif ztype == 'divine_shield':
                # HEALER DIVINE SHIELD: warm gold dome with light particles
                t = pygame.time.get_ticks()
                pulse = 0.6 + 0.4 * math.sin(t * 0.004)
                alpha = int(45 * pulse)
                pygame.draw.circle(surf, (230, 220, 100, alpha), (radius, radius), radius)
                pygame.draw.circle(surf, (255, 245, 150, 100), (radius, radius), radius, 2)
                # Floating light particles inside
                for i in range(5):
                    angle = t * 0.002 + i * 1.257
                    pr = int(radius * 0.5 * (0.5 + 0.5 * math.sin(t * 0.003 + i)))
                    px = radius + int(pr * math.cos(angle))
                    py = radius + int(pr * math.sin(angle))
                    pygame.draw.circle(surf, (255, 255, 200, 80), (px, py), 2)
            elif ztype == 'meteor':
                # MAGE METEOR: growing warning circle with fiery centre
                frac = 1.0 - zone.get('delay', 0) / max(zone.get('duration', 1), 0.01)
                frac = max(0, min(1, frac))
                inner_r = int(radius * frac)
                # Warning ring
                pygame.draw.circle(surf, (255, 100, 0, 40), (radius, radius), radius)
                # Growing fire core
                if inner_r > 0:
                    pygame.draw.circle(surf, (255, 180, 0, 80), (radius, radius), inner_r)
                    # Flame flicker inside
                    t = pygame.time.get_ticks()
                    for i in range(3):
                        angle = t * 0.01 + i * 2.094
                        fr = int(inner_r * 0.5)
                        fx = radius + int(fr * math.cos(angle))
                        fy = radius + int(fr * math.sin(angle))
                        pygame.draw.circle(surf, (255, 220, 60, 100), (fx, fy), max(2, inner_r // 4))
                pygame.draw.circle(surf, (255, 50, 0, 150), (radius, radius), radius, 2)

            self.screen.blit(surf, (zx - radius, zy - radius))

    # ------------------------------------------------------------------
    # Helper: lerp two colours by t (0..1)
    # ------------------------------------------------------------------
    @staticmethod
    def _lerp_color(c1, c2, t):
        t = max(0.0, min(1.0, t))
        return (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t),
        )

    # ------------------------------------------------------------------
    # Pixel-art enemy sprites with unique visuals per type
    # ------------------------------------------------------------------
    def _draw_enemies(self, floor, sx, sy):
        ticks = pygame.time.get_ticks()
        for room in floor.rooms:
            for enemy in room.enemies:
                if not enemy.alive:
                    continue
                ex, ey = self.camera.apply(enemy.x, enemy.y)
                ex += sx
                ey += sy

                if not (-60 < ex < SCREEN_W + 60 and -60 < ey < SCREEN_H + 60):
                    continue

                vis = ENEMY_VISUALS.get(enemy.name)
                if not vis:
                    # Fallback: plain coloured square
                    half = enemy.size // 2
                    pygame.draw.rect(self.screen, enemy.color,
                                     (ex - half, ey - half, enemy.size, enemy.size))
                    self._draw_enemy_overlays(enemy, ex, ey, ticks)
                    continue

                s = enemy.size
                half = s // 2
                anim_t = getattr(enemy, 'anim_timer', 0.0)
                bob_off = getattr(enemy, 'bob_offset', 0.0)
                hp_pct = enemy.hp / max(enemy.max_hp, 1)
                hurt = getattr(enemy, 'hurt_flash', 0.0)

                body = vis['body']
                sec = vis['secondary']
                acc = vis['accent']
                acc2 = vis.get('accent2')
                shad = vis['shadow']
                hi = vis['highlight']
                weap = vis.get('weapon')

                # Hurt flash override
                if hurt > 0:
                    flash_t = hurt / 0.15
                    body = self._lerp_color(body, (255, 255, 255), flash_t * 0.7)
                    sec = self._lerp_color(sec, (255, 255, 255), flash_t * 0.5)

                # --- Shadow (all enemies) ---
                shad_w = int(s * 0.9)
                shad_h = max(4, s // 4)
                shad_surf = pygame.Surface((shad_w, shad_h), pygame.SRCALPHA)
                pygame.draw.ellipse(shad_surf, (0, 0, 0, 55), shad_surf.get_rect())
                self.screen.blit(shad_surf, (ex - shad_w // 2, ey + half - 2))

                # --- Dispatch to per-enemy sprite draw ---
                draw_fn = getattr(self, f'_sprite_{enemy.name}', None)
                if draw_fn:
                    draw_fn(ex, ey, s, half, enemy, vis, ticks, anim_t, bob_off, hp_pct)
                else:
                    # Generic fallback with body/secondary split
                    self._sprite_generic(ex, ey, s, half, enemy, vis, ticks, anim_t, bob_off, hp_pct)

                # --- Overlays: HP bar, stun, status, name ---
                self._draw_enemy_overlays(enemy, ex, ey, ticks)

    # ------------------------------------------------------------------
    # Overlay drawing (HP, stun stars, status dots, names)
    # ------------------------------------------------------------------
    def _draw_enemy_overlays(self, enemy, ex, ey, ticks):
        half = enemy.size // 2

        # HP bar
        if enemy.hp < enemy.max_hp:
            bar_w = enemy.size + 6
            bar_h = 4
            bar_x = ex - bar_w // 2
            bar_y = ey - half - 10
            pygame.draw.rect(self.screen, (50, 0, 0), (bar_x, bar_y, bar_w, bar_h))
            hp_pct = enemy.hp / max(enemy.max_hp, 1)
            if hp_pct > 0.5:
                hp_color = (0, 200, 0)
            elif hp_pct > 0.25:
                hp_color = (200, 200, 0)
            else:
                hp_color = (200, 0, 0)
            pygame.draw.rect(self.screen, hp_color,
                             (bar_x, bar_y, int(bar_w * hp_pct), bar_h))

        # Stunned indicator (spinning stars)
        if enemy.stunned > 0:
            for i in range(3):
                angle = ticks * 0.01 + i * 2.094
                star_x = ex + int(12 * math.cos(angle))
                star_y = ey - half - 15 + int(4 * math.sin(angle * 2))
                pygame.draw.circle(self.screen, (255, 255, 100), (star_x, star_y), 2)

        # Status effect dots
        effects = getattr(enemy, 'status_effects', [])
        if effects:
            effect_x = ex - len(effects) * 4
            effect_y = ey + half + 5
            for eff in effects:
                ecolor = getattr(eff, 'color', (255, 255, 255))
                if isinstance(ecolor, (list, tuple)) and len(ecolor) >= 3:
                    pygame.draw.circle(self.screen, ecolor[:3],
                                       (int(effect_x), int(effect_y)), 3)
                effect_x += 8

        # Name label for elites and bosses
        if enemy.tier in ("elite", "boss"):
            label_color = (255, 220, 100) if enemy.tier == "boss" else (200, 200, 220)
            name_surf = self.font_tiny.render(
                enemy.name.replace("_", " ").title(), True, label_color)
            self.screen.blit(name_surf,
                             (ex - name_surf.get_width() // 2, ey - half - 22))

    # ==================================================================
    #  TRASH SPRITES
    # ==================================================================

    def _sprite_goblin(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Small squat square, large head, jittery side-bob, knife, yellow eyes, red headband."""
        # Jittery side-bob animation
        jitter_x = int(2.5 * math.sin(ticks * 0.012 + bob))
        jitter_y = int(1.5 * abs(math.sin(ticks * 0.015 + bob)))
        cx = ex + jitter_x
        cy = ey - jitter_y

        body_w = int(s * 0.8)
        body_h = int(s * 0.55)
        head_s = int(s * 0.55)

        # Body (brown leather lower)
        pygame.draw.rect(self.screen, vis['secondary'],
                         (cx - body_w // 2, cy - body_h // 4, body_w, body_h))
        # Head (green, large)
        pygame.draw.rect(self.screen, vis['body'],
                         (cx - head_s // 2, cy - half, head_s, head_s))
        # Shadow on head bottom-right
        sr = pygame.Surface((head_s // 2, head_s // 2), pygame.SRCALPHA)
        sr.fill((*vis['shadow'], 60))
        self.screen.blit(sr, (cx, cy - half + head_s // 2))
        # Highlight top-left
        pygame.draw.rect(self.screen, vis['highlight'],
                         (cx - head_s // 2, cy - half, head_s // 3, 2))
        # Red headband
        pygame.draw.rect(self.screen, vis['accent2'],
                         (cx - head_s // 2, cy - half + head_s // 3, head_s, 3))
        # Yellow eyes (2 pixels)
        ey_off = cy - half + head_s // 3 + 4
        pygame.draw.rect(self.screen, vis['accent'], (cx - 4, ey_off, 3, 3))
        pygame.draw.rect(self.screen, vis['accent'], (cx + 2, ey_off, 3, 3))
        # Knife (dark grey, right side)
        if vis['weapon']:
            kx = cx + body_w // 2 - 2
            ky = cy - 2
            pygame.draw.line(self.screen, vis['weapon'], (kx, ky), (kx + 5, ky - 6), 2)

    def _sprite_skeleton(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Thin vertical sprite, visible rib lines, jerky snap movement."""
        # Jerky: quantize position to simulate snapping steps
        snap = int(ticks * 0.006 + bob) % 4
        snap_y = -1 if snap < 2 else 1

        body_w = int(s * 0.45)
        body_h = int(s * 0.9)
        skull_s = int(s * 0.4)

        # Spine / body (off-white)
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - body_w // 2, ey - half + skull_s, body_w, body_h - skull_s))
        # Rib lines (dark grey cracks)
        for i in range(3):
            ry = ey - half + skull_s + 6 + i * 5
            pygame.draw.line(self.screen, vis['secondary'],
                             (ex - body_w // 2, ry), (ex + body_w // 2, ry), 1)
        # Skull (square with dark sockets)
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - skull_s // 2, ey - half + snap_y, skull_s, skull_s))
        # Eye sockets (dark)
        pygame.draw.rect(self.screen, (20, 18, 15),
                         (ex - skull_s // 4 - 1, ey - half + skull_s // 3 + snap_y, 4, 4))
        pygame.draw.rect(self.screen, (20, 18, 15),
                         (ex + skull_s // 4 - 3, ey - half + skull_s // 3 + snap_y, 4, 4))
        # Eye glow (red or blue)
        pygame.draw.rect(self.screen, vis['accent'],
                         (ex - skull_s // 4, ey - half + skull_s // 3 + 1 + snap_y, 2, 2))
        pygame.draw.rect(self.screen, vis['accent'],
                         (ex + skull_s // 4 - 2, ey - half + skull_s // 3 + 1 + snap_y, 2, 2))
        # Weapon (rusted line off right side)
        if vis['weapon']:
            pygame.draw.line(self.screen, vis['weapon'],
                             (ex + body_w // 2, ey - half + skull_s + 2),
                             (ex + body_w // 2 + 7, ey + half), 2)

    def _sprite_slime(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Rounded blob, compress-stretch hop, inner core, wet highlight."""
        # Hop animation: compress then stretch
        hop_phase = math.sin(ticks * 0.005 + bob)
        squeeze_x = 1.0 + 0.12 * hop_phase
        squeeze_y = 1.0 - 0.12 * hop_phase
        bounce_y = -abs(hop_phase) * 4

        w = int(s * squeeze_x)
        h = int(s * 0.75 * squeeze_y)
        cy = ey + int(bounce_y)

        # Main gel body (rounded rect via ellipse)
        pygame.draw.ellipse(self.screen, vis['body'],
                            (ex - w // 2, cy - h // 2, w, h))
        # Inner core (darker, floating centre)
        core_r = max(3, int(s * 0.18))
        core_y = cy + int(2 * math.sin(ticks * 0.003 + bob))
        pygame.draw.circle(self.screen, vis['secondary'], (ex, core_y), core_r)
        # Wet highlight top-left
        pygame.draw.ellipse(self.screen, vis['highlight'],
                            (ex - w // 3, cy - h // 2 + 1, w // 3, max(2, h // 5)))
        # Eyes (bright spots)
        pygame.draw.rect(self.screen, vis['accent'], (ex - 3, cy - h // 4, 2, 2))
        pygame.draw.rect(self.screen, vis['accent'], (ex + 2, cy - h // 4, 2, 2))
        # Poison highlight at bottom
        if vis['accent']:
            pygame.draw.ellipse(self.screen, (*vis['accent'][:3],),
                                (ex - w // 4, cy + h // 4 - 2, w // 2, max(2, h // 5)))

    def _sprite_wolf(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Low horizontal shape, head forward, running silhouette, fluid loping."""
        # Loping animation: gentle body wave
        lope = math.sin(ticks * 0.008 + bob) * 2
        run_lean = int(lope)

        body_w = int(s * 1.2)
        body_h = int(s * 0.55)
        head_s = int(s * 0.4)
        fd = getattr(enemy, 'facing_dir', (0, 1))
        face_right = fd[0] >= 0

        # Body (dark fur, horizontal)
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - body_w // 2, ey - body_h // 2 + run_lean, body_w, body_h))
        # Lighter back stripe
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - body_w // 2 + 3, ey - body_h // 2 + run_lean, body_w - 6, body_h // 3))
        # Head (pushed forward)
        hx = ex + (body_w // 2 - 2 if face_right else -body_w // 2 - head_s + 2)
        hy = ey - body_h // 3 + run_lean
        pygame.draw.rect(self.screen, vis['body'], (hx, hy, head_s, head_s))
        # Eye (red-amber, near front of head)
        eye_x = hx + (head_s - 4 if face_right else 2)
        pygame.draw.rect(self.screen, vis['accent'], (eye_x, hy + 3, 3, 3))
        # Teeth (pale)
        if vis['weapon']:
            tx = hx + (head_s if face_right else -3)
            pygame.draw.rect(self.screen, vis['weapon'], (tx, hy + head_s - 4, 3, 3))
        # Tail (rear)
        tail_x = ex + (-body_w // 2 - 4 if face_right else body_w // 2 + 1)
        tail_wave = int(3 * math.sin(ticks * 0.01 + bob))
        pygame.draw.line(self.screen, vis['shadow'],
                         (tail_x, ey + run_lean), (tail_x - (3 if face_right else -3), ey - 4 + tail_wave + run_lean), 2)
        # Legs (tiny pixels underneath)
        leg_phase = int(ticks * 0.01 + bob) % 4
        for i, lx in enumerate([ex - body_w // 3, ex - body_w // 6, ex + body_w // 6, ex + body_w // 3]):
            leg_y_off = 2 if (i + leg_phase) % 2 == 0 else 0
            pygame.draw.rect(self.screen, vis['shadow'],
                             (lx, ey + body_h // 2 + run_lean + leg_y_off, 2, 4))

    def _sprite_bug(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Compact oval body, hard shell, scuttling start-stop, bright venom sac."""
        # Scuttle: quick direction changes
        scuttle_x = int(3 * math.sin(ticks * 0.018 + bob))
        scuttle_y = int(1.5 * math.sin(ticks * 0.022 + bob * 1.3))
        cx = ex + scuttle_x
        cy = ey + scuttle_y

        w = int(s * 0.9)
        h = int(s * 0.65)

        # Dark shell (oval)
        pygame.draw.ellipse(self.screen, vis['body'], (cx - w // 2, cy - h // 2, w, h))
        # Carapace highlight line
        pygame.draw.ellipse(self.screen, vis['secondary'],
                            (cx - w // 3, cy - h // 2, w * 2 // 3, h // 2))
        # Bright abdomen / venom sac (back section)
        sac_r = max(3, s // 6)
        pygame.draw.circle(self.screen, vis['accent'], (cx, cy + h // 4), sac_r)
        # Eye / mandible accent (front)
        pygame.draw.rect(self.screen, vis['accent'], (cx - 2, cy - h // 3, 2, 2))
        pygame.draw.rect(self.screen, vis['accent'], (cx + 1, cy - h // 3, 2, 2))
        # Leg pixels (3 per side)
        for i in range(3):
            lx_off = -w // 2 - 2 + i * 0
            ly_off = -h // 4 + i * (h // 4)
            pygame.draw.rect(self.screen, vis['shadow'], (cx - w // 2 - 2, cy + ly_off, 2, 1))
            pygame.draw.rect(self.screen, vis['shadow'], (cx + w // 2, cy + ly_off, 2, 1))

    def _sprite_undead_soldier(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Bulky iron armour, broken shield silhouette, slow march lean, blue glow."""
        # Slow march: slight lean forward
        lean = int(1.5 * math.sin(ticks * 0.003 + bob))

        body_w = int(s * 0.75)
        body_h = int(s * 0.85)
        head_s = int(s * 0.35)

        # Iron armour body
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - body_w // 2, ey - half + head_s + lean, body_w, body_h - head_s))
        # Shadow (bottom-right)
        sr = pygame.Surface((body_w // 2, body_h // 2), pygame.SRCALPHA)
        sr.fill((*vis['shadow'], 50))
        self.screen.blit(sr, (ex, ey - half + head_s + (body_h - head_s) // 2 + lean))
        # Rotting cloth (secondary, middle band)
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - body_w // 2, ey - half + head_s + body_h // 3 + lean, body_w, body_h // 4))
        # Helmet / head
        pygame.draw.rect(self.screen, vis['highlight'],
                         (ex - head_s // 2, ey - half + lean, head_s, head_s))
        # Undead eye glow (dim blue/green)
        pygame.draw.rect(self.screen, vis['accent'],
                         (ex - 3, ey - half + head_s // 3 + lean, 3, 2))
        pygame.draw.rect(self.screen, vis['accent'],
                         (ex + 1, ey - half + head_s // 3 + lean, 3, 2))
        # Broken shield (left side)
        shield_active = getattr(enemy, 'special_data', {}).get('shield_active', False)
        shield_c = vis['highlight'] if shield_active else vis['shadow']
        pygame.draw.rect(self.screen, shield_c,
                         (ex - body_w // 2 - 5, ey - body_h // 6 + lean, 5, body_h // 2))
        # Sword (right side)
        if vis['weapon']:
            pygame.draw.line(self.screen, vis['weapon'],
                             (ex + body_w // 2, ey - 4 + lean),
                             (ex + body_w // 2 + 4, ey + half - 2 + lean), 2)

    # ==================================================================
    #  ELITE SPRITES
    # ==================================================================

    def _sprite_assassin(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Narrow cloak, silver blade, red eyes. Stealth shimmer when invisible."""
        stealth = getattr(enemy, 'special_data', {}).get('invisible', False)

        if stealth:
            # Nearly invisible: faint shimmer outline only
            shimmer_a = int(25 + 15 * math.sin(ticks * 0.012))
            shimmer = pygame.Surface((s + 8, s + 8), pygame.SRCALPHA)
            pygame.draw.rect(shimmer, (*vis['secondary'], shimmer_a), shimmer.get_rect(), 2)
            self.screen.blit(shimmer, (ex - half - 4, ey - half - 4))
            # Faint red eye flash
            if int(ticks * 0.005) % 3 == 0:
                pygame.draw.rect(self.screen, (*vis['accent'], 120), (ex - 2, ey - half // 2, 2, 2))
                pygame.draw.rect(self.screen, (*vis['accent'], 120), (ex + 1, ey - half // 2, 2, 2))
            return

        # Visible assassin
        body_w = int(s * 0.5)
        body_h = int(s * 0.85)
        cloak_w = int(s * 0.75)

        # Cloak (breaks silhouette - wider at bottom)
        cloak_pts = [
            (ex - body_w // 2, ey - half + 4),
            (ex + body_w // 2, ey - half + 4),
            (ex + cloak_w // 2, ey + half),
            (ex - cloak_w // 2, ey + half),
        ]
        pygame.draw.polygon(self.screen, vis['body'], cloak_pts)
        # Purple cloth layer
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - body_w // 2 + 2, ey - half + body_h // 3, body_w - 4, body_h // 3))
        # Head (dark)
        head_s = int(s * 0.3)
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - head_s // 2, ey - half, head_s, head_s))
        # Bright red eyes (key readability accent)
        pygame.draw.rect(self.screen, vis['accent'], (ex - 3, ey - half + head_s // 3, 3, 2))
        pygame.draw.rect(self.screen, vis['accent'], (ex + 1, ey - half + head_s // 3, 3, 2))
        # Silver blade (right side, bright)
        pygame.draw.line(self.screen, vis['weapon'],
                         (ex + body_w // 2 + 1, ey - 6),
                         (ex + body_w // 2 + 1, ey + 8), 2)
        # Blade tip gleam
        pygame.draw.rect(self.screen, (255, 255, 255),
                         (ex + body_w // 2, ey - 7, 2, 2))

    def _sprite_shaman(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Robe-heavy, staff raised above head, bone charms, floaty bob."""
        # Floaty bob animation
        float_y = int(3 * math.sin(ticks * 0.004 + bob))
        cy = ey + float_y

        body_w = int(s * 0.65)
        body_h = int(s * 0.8)
        head_s = int(s * 0.35)

        # Robe body
        robe_pts = [
            (ex - body_w // 3, cy - half + head_s),
            (ex + body_w // 3, cy - half + head_s),
            (ex + body_w // 2, cy + half),
            (ex - body_w // 2, cy + half),
        ]
        pygame.draw.polygon(self.screen, vis['body'], robe_pts)
        # Bone charms (secondary dots on robe)
        for i in range(3):
            cx_off = -6 + i * 6
            pygame.draw.circle(self.screen, vis['secondary'],
                               (ex + cx_off, cy - half + head_s + 10 + i * 4), 2)
        # Head
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - head_s // 2, cy - half, head_s, head_s))
        # Skin face
        pygame.draw.rect(self.screen, (160, 130, 90),
                         (ex - head_s // 3, cy - half + 2, head_s * 2 // 3, head_s - 4))
        # Staff (raised above head, with bright tip)
        staff_x = ex + body_w // 3 + 2
        pygame.draw.line(self.screen, vis.get('weapon', vis['secondary']),
                         (staff_x, cy + half), (staff_x, cy - half - 10), 2)
        # Spell glow at staff tip
        glow_pulse = int(3 + 2 * math.sin(ticks * 0.006 + bob))
        pygame.draw.circle(self.screen, vis['accent'], (staff_x, cy - half - 12), glow_pulse)

    def _sprite_elite_knight(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Very square broad shoulders, steel plate, gold crest, charge telegraph."""
        charging = getattr(enemy, 'special_data', {}).get('charging', False)

        body_w = int(s * 0.85)
        body_h = int(s * 0.8)
        head_s = int(s * 0.35)
        shoulder_w = int(s * 0.95)

        # Brace animation before charge
        lean = -3 if charging else 0

        # Body (steel plate)
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - body_w // 2, ey - half + head_s + lean, body_w, body_h - head_s))
        # Broad shoulders (wider band)
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - shoulder_w // 2, ey - half + head_s + lean, shoulder_w, s // 5))
        # Crimson tabard (centre)
        tabard_w = body_w // 3
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - tabard_w // 2, ey - half + head_s + s // 5 + lean, tabard_w, body_h // 2))
        # Helmet
        pygame.draw.rect(self.screen, vis['highlight'],
                         (ex - head_s // 2, ey - half + lean, head_s, head_s))
        # Gold crest (top of helmet)
        pygame.draw.rect(self.screen, vis['accent'],
                         (ex - 2, ey - half - 4 + lean, 5, 5))
        # Eye slit glow
        if vis['accent2']:
            pygame.draw.rect(self.screen, vis['accent2'],
                             (ex - head_s // 3, ey - half + head_s // 3 + lean, head_s * 2 // 3, 2))
        # Shield (left) or lance (right)
        pygame.draw.rect(self.screen, vis['shadow'],
                         (ex - body_w // 2 - 5, ey - body_h // 6 + lean, 5, body_h // 2))
        pygame.draw.line(self.screen, vis['weapon'],
                         (ex + body_w // 2 + 2, ey - half + lean),
                         (ex + body_w // 2 + 2, ey + half + lean), 2)
        # Charge telegraph: bright dust line
        if charging:
            for i in range(4):
                dx = ex - 8 - i * 6
                pygame.draw.rect(self.screen, (200, 200, 180, 150), (dx, ey + half - 2, 4, 2))

    def _sprite_ogre(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Very large blocky, tiny head, giant arms, club, heavy stomp."""
        # Stomp animation
        stomp = abs(math.sin(ticks * 0.003 + bob)) * 2
        cy = ey + int(stomp)

        body_w = int(s * 0.9)
        body_h = int(s * 0.75)
        head_s = int(s * 0.25)  # tiny head
        arm_w = int(s * 0.2)

        # Massive body
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - body_w // 2, cy - body_h // 2, body_w, body_h))
        # Ragged cloth (waist band)
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - body_w // 2, cy, body_w, body_h // 4))
        # Shadow on right side
        sr = pygame.Surface((body_w // 3, body_h), pygame.SRCALPHA)
        sr.fill((*vis['shadow'], 40))
        self.screen.blit(sr, (ex + body_w // 6, cy - body_h // 2))
        # Giant arms
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - body_w // 2 - arm_w, cy - body_h // 4, arm_w, body_h * 2 // 3))
        pygame.draw.rect(self.screen, vis['body'],
                         (ex + body_w // 2, cy - body_h // 4, arm_w, body_h * 2 // 3))
        # Tiny head
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - head_s // 2, cy - body_h // 2 - head_s + 2, head_s, head_s))
        # Red scars / rage cracks
        pygame.draw.line(self.screen, vis['accent'],
                         (ex - body_w // 4, cy - body_h // 4),
                         (ex - body_w // 6, cy + body_h // 6), 2)
        pygame.draw.line(self.screen, vis['accent'],
                         (ex + body_w // 6, cy - body_h // 3),
                         (ex + body_w // 4, cy), 2)
        # Club (dark wood, right side extending)
        if vis['weapon']:
            pygame.draw.rect(self.screen, vis['weapon'],
                             (ex + body_w // 2 + arm_w - 2, cy - body_h // 4 - 6, 6, body_h // 2 + 6))

    def _sprite_cursed_priest(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Tall dark robe, hollow hood, purple curse glow, eerie glide."""
        # Eerie glide: minimal motion
        glide_y = int(1.5 * math.sin(ticks * 0.003 + bob))
        cy = ey + glide_y

        body_w = int(s * 0.55)
        robe_h = int(s * 0.9)
        hood_s = int(s * 0.4)

        # Robe (tall, tapering slightly)
        robe_pts = [
            (ex - body_w // 3, cy - half + hood_s - 2),
            (ex + body_w // 3, cy - half + hood_s - 2),
            (ex + body_w // 2 + 2, cy + half),
            (ex - body_w // 2 - 2, cy + half),
        ]
        pygame.draw.polygon(self.screen, vis['body'], robe_pts)
        # Corrupted gold trim (secondary lines)
        for i in range(2):
            ty = cy - half + hood_s + robe_h // 3 + i * (robe_h // 4)
            pygame.draw.line(self.screen, vis['secondary'],
                             (ex - body_w // 2, ty), (ex + body_w // 2, ty), 1)
        # Hood (dark, hollow)
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - hood_s // 2, cy - half, hood_s, hood_s))
        # Hollow inside (darker)
        pygame.draw.rect(self.screen, vis['shadow'],
                         (ex - hood_s // 3, cy - half + 3, hood_s * 2 // 3, hood_s - 5))
        # Purple curse glow (chest/centre)
        glow_r = int(4 + 2 * math.sin(ticks * 0.005 + bob))
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*vis['accent'], 120), (glow_r, glow_r), glow_r)
        self.screen.blit(glow_surf, (ex - glow_r, cy - glow_r))
        # Floating book/censer (left side)
        book_y = cy - half + hood_s + int(2 * math.sin(ticks * 0.004 + bob + 1))
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - body_w // 2 - 6, book_y, 5, 6))

    def _sprite_dark_mage(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Deep purple robe, glowing orb/hand, vivid spell colour, cleaner than shaman."""
        body_w = int(s * 0.6)
        robe_h = int(s * 0.85)
        head_s = int(s * 0.32)

        # Clean robe body
        robe_pts = [
            (ex - body_w // 3, ey - half + head_s),
            (ex + body_w // 3, ey - half + head_s),
            (ex + body_w // 2, ey + half),
            (ex - body_w // 2, ey + half),
        ]
        pygame.draw.polygon(self.screen, vis['body'], robe_pts)
        # Pale skin hands (secondary, at sides)
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - body_w // 2 - 2, ey, 4, 4))
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex + body_w // 2 - 2, ey, 4, 4))
        # Head (hidden face)
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - head_s // 2, ey - half, head_s, head_s))
        pygame.draw.rect(self.screen, vis['shadow'],
                         (ex - head_s // 3, ey - half + 3, head_s * 2 // 3, head_s - 5))
        # Staff/orb (right side)
        staff_x = ex + body_w // 3 + 3
        pygame.draw.line(self.screen, vis['weapon'],
                         (staff_x, ey + half), (staff_x, ey - half + head_s), 2)
        # Vivid spell orb at top of staff (pulsing)
        orb_r = int(4 + 2 * math.sin(ticks * 0.006 + bob))
        orb_surf = pygame.Surface((orb_r * 2 + 4, orb_r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(orb_surf, (*vis['accent'], 180),
                           (orb_r + 2, orb_r + 2), orb_r)
        pygame.draw.circle(orb_surf, (*vis['accent'], 60),
                           (orb_r + 2, orb_r + 2), orb_r + 2)
        self.screen.blit(orb_surf, (staff_x - orb_r - 2, ey - half + head_s - orb_r - 4))
        # Glowing hand (casting)
        cast_glow = pygame.Surface((8, 8), pygame.SRCALPHA)
        acc2_c = vis['accent2'] if vis['accent2'] else vis['accent']
        pygame.draw.circle(cast_glow, (*acc2_c, 100), (4, 4), 4)
        self.screen.blit(cast_glow, (ex - body_w // 2 - 5, ey - 4))

    # ==================================================================
    #  BOSS SPRITES
    # ==================================================================

    def _sprite_giant_beast(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Enrage boss: massive dark hide, rage cracks glow more at low HP."""
        pulse = 1 + 0.04 * math.sin(ticks * 0.003)
        size = int(s * pulse)
        sh = size // 2
        rage_t = 1.0 - hp_pct  # 0 at full HP, 1 at dead

        # Body colour shifts toward rage as HP drops
        body_c = self._lerp_color(vis['body'], vis.get('danger_color', vis['accent']), rage_t * 0.5)

        # Massive body
        pygame.draw.rect(self.screen, body_c, (ex - sh, ey - sh, size, size))
        # Lighter plating (secondary, upper)
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - sh + 3, ey - sh + 2, size - 6, size // 3))
        # Shadow bottom-right
        sr = pygame.Surface((sh, sh), pygame.SRCALPHA)
        sr.fill((*vis['shadow'], 50))
        self.screen.blit(sr, (ex, ey))
        # Highlight top-left
        pygame.draw.rect(self.screen, vis['highlight'], (ex - sh, ey - sh, size // 3, 3))
        # Rage cracks (glow more with lost HP)
        crack_c = self._lerp_color(vis['accent'], vis['accent2'] or vis['accent'], rage_t)
        crack_a = int(80 + 175 * rage_t)
        for i in range(3):
            cx1 = ex - sh + 5 + i * (size // 3)
            cy1 = ey - sh + size // 4 + i * 3
            cx2 = cx1 + size // 5
            cy2 = cy1 + size // 3
            crack_surf = pygame.Surface((abs(cx2 - cx1) + 4, abs(cy2 - cy1) + 4), pygame.SRCALPHA)
            pygame.draw.line(crack_surf, (*crack_c, crack_a), (0, 0), (abs(cx2 - cx1), abs(cy2 - cy1)), 2)
            self.screen.blit(crack_surf, (min(cx1, cx2), min(cy1, cy2)))
        # Eyes (orange, glow brighter with rage)
        eye_c = self._lerp_color(vis['accent'], (255, 255, 200), rage_t)
        pygame.draw.rect(self.screen, eye_c, (ex - sh + size // 4, ey - sh + size // 4, 4, 3))
        pygame.draw.rect(self.screen, eye_c, (ex + size // 8, ey - sh + size // 4, 4, 3))
        # Horns/claws (weapon colour)
        if vis['weapon']:
            pygame.draw.line(self.screen, vis['weapon'],
                             (ex - sh + 2, ey - sh - 3), (ex - sh + 6, ey - sh + 4), 2)
            pygame.draw.line(self.screen, vis['weapon'],
                             (ex + sh - 2, ey - sh - 3), (ex + sh - 6, ey - sh + 4), 2)

    def _sprite_fallen_hero(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Counter boss: clean duelist, polished steel, teal accent, minimal motion."""
        size = s
        sh = size // 2
        body_w = int(size * 0.7)
        body_h = int(size * 0.8)
        head_s = int(size * 0.3)

        # Body (polished steel)
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - body_w // 2, ey - sh + head_s, body_w, body_h - head_s))
        # Cape (secondary, behind and to one side)
        cape_pts = [
            (ex + body_w // 2 - 3, ey - sh + head_s + 2),
            (ex + body_w // 2 + 6, ey - sh + head_s + 2),
            (ex + body_w // 2 + 8, ey + sh + 4),
            (ex + body_w // 2 - 2, ey + sh),
        ]
        pygame.draw.polygon(self.screen, vis['secondary'], cape_pts)
        # Helmet
        pygame.draw.rect(self.screen, vis['highlight'],
                         (ex - head_s // 2, ey - sh, head_s, head_s))
        # Teal visor slit
        pygame.draw.rect(self.screen, vis['accent'],
                         (ex - head_s // 3, ey - sh + head_s // 3, head_s * 2 // 3, 2))
        # Weapon flash (bright steel sword, held forward)
        fd = getattr(enemy, 'facing_dir', (0, 1))
        wx = ex + int(fd[0] * size * 0.5)
        wy = ey + int(fd[1] * size * 0.5)
        pygame.draw.line(self.screen, vis['weapon'], (ex, ey), (wx, wy), 2)
        # Weapon tip gleam
        pygame.draw.circle(self.screen, (255, 255, 255), (wx, wy), 2)
        # Counter-stance shimmer (when special_data indicates guarding)
        windup = getattr(enemy, 'special_data', {}).get('windup_timer', 0)
        if windup > 0:
            guard_surf = pygame.Surface((size + 8, size + 8), pygame.SRCALPHA)
            ga = int(60 + 40 * math.sin(ticks * 0.01))
            pygame.draw.circle(guard_surf, (*vis['accent'], ga),
                               (size // 2 + 4, size // 2 + 4), size // 2 + 4, 2)
            self.screen.blit(guard_surf, (ex - size // 2 - 4, ey - size // 2 - 4))

    def _sprite_corrupted_king(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Summoner boss: dark robes, orbiting sigils, summon glow."""
        pulse = 1 + 0.03 * math.sin(ticks * 0.003)
        size = int(s * pulse)
        sh = size // 2

        # Core body (robes/chitin)
        robe_pts = [
            (ex - sh // 2, ey - sh + 6),
            (ex + sh // 2, ey - sh + 6),
            (ex + sh, ey + sh),
            (ex - sh, ey + sh),
        ]
        pygame.draw.polygon(self.screen, vis['body'], robe_pts)
        # Bone/totem structures (secondary, decorating body)
        for i in range(3):
            bx = ex - sh // 2 + i * (sh // 2)
            by = ey - sh + 12 + i * 4
            pygame.draw.rect(self.screen, vis['secondary'], (bx, by, 4, 8))
        # Head glow (core)
        head_r = size // 5
        pygame.draw.circle(self.screen, vis['body'], (ex, ey - sh + 4), head_r)
        pygame.draw.circle(self.screen, vis['accent'], (ex, ey - sh + 4), head_r - 2)
        # Orbiting sigils (3 accent-colored dots circling)
        for i in range(3):
            angle = ticks * 0.004 + i * (math.pi * 2 / 3)
            orbit_r = int(sh * 0.8)
            sx_o = ex + int(orbit_r * math.cos(angle))
            sy_o = ey + int(orbit_r * 0.6 * math.sin(angle))
            sigil_c = vis['accent'] if i % 2 == 0 else (vis['accent2'] or vis['accent'])
            pygame.draw.circle(self.screen, sigil_c, (sx_o, sy_o), 3)
            # Trail
            tx = sx_o - int(5 * math.cos(angle))
            ty = sy_o - int(3 * math.sin(angle))
            pygame.draw.line(self.screen, (*sigil_c[:3],), (tx, ty), (sx_o, sy_o), 1)

    def _sprite_dungeon_guardian(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Hazard boss: earthy/corrupted, fused with room, spikes/growths, toxic glow."""
        size = s
        sh = size // 2

        # Main body (earthy block, anchored)
        pygame.draw.rect(self.screen, vis['body'], (ex - sh, ey - sh, size, size))
        # Armour structure (secondary bands)
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - sh + 2, ey - sh + size // 4, size - 4, size // 5))
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - sh + 2, ey + size // 6, size - 4, size // 5))
        # Shadow
        sr = pygame.Surface((sh, size), pygame.SRCALPHA)
        sr.fill((*vis['shadow'], 40))
        self.screen.blit(sr, (ex, ey - sh))
        # Spikes/growths (extending from body)
        for i in range(4):
            angle = i * (math.pi / 2) + ticks * 0.001
            spike_len = size // 3 + int(3 * math.sin(ticks * 0.004 + i))
            sx_s = ex + int(math.cos(angle) * (sh + spike_len))
            sy_s = ey + int(math.sin(angle) * (sh + spike_len))
            pygame.draw.line(self.screen, vis['highlight'],
                             (ex + int(math.cos(angle) * sh), ey + int(math.sin(angle) * sh)),
                             (sx_s, sy_s), 3)
        # Toxic green hazard glow (pulsing from centre)
        glow_r = int(sh * 0.5 + 4 * math.sin(ticks * 0.005 + bob))
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*vis['accent'], 80), (glow_r, glow_r), glow_r)
        self.screen.blit(glow_surf, (ex - glow_r, ey - glow_r))
        # Eyes
        pygame.draw.rect(self.screen, vis['accent'],
                         (ex - size // 6, ey - sh + size // 4, 4, 3))
        pygame.draw.rect(self.screen, vis['accent'],
                         (ex + size // 6 - 3, ey - sh + size // 4, 4, 3))

    def _sprite_floor_admin(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Phase boss: visual changes across 3 phases. Mask breaks, colour intensifies."""
        phase = getattr(enemy, 'phase', 1)
        phase_colors = vis.get('phase_colors', {})
        phase_accent = phase_colors.get(phase, vis['accent'])

        pulse = 1 + 0.03 * math.sin(ticks * 0.003) * phase  # more pulse in later phases
        size = int(s * pulse)
        sh = size // 2

        body_w = int(size * 0.75)
        body_h = int(size * 0.85)
        head_s = int(size * 0.35)

        # Body — gets brighter cracks per phase
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - body_w // 2, ey - sh + head_s, body_w, body_h - head_s))
        # Phase 2+: cracks/added details
        if phase >= 2:
            for i in range(phase):
                cx1 = ex - body_w // 3 + i * (body_w // 3)
                cy1 = ey - sh + head_s + 4
                pygame.draw.line(self.screen, phase_accent,
                                 (cx1, cy1), (cx1 + 6, cy1 + body_h // 2), 2)
        # Phase 3: wings / extra limbs
        if phase >= 3:
            wing_pts_l = [(ex - body_w // 2, ey - sh + head_s + 4),
                          (ex - body_w // 2 - 12, ey - sh),
                          (ex - body_w // 2 - 8, ey)]
            wing_pts_r = [(ex + body_w // 2, ey - sh + head_s + 4),
                          (ex + body_w // 2 + 12, ey - sh),
                          (ex + body_w // 2 + 8, ey)]
            pygame.draw.polygon(self.screen, vis['secondary'], wing_pts_l)
            pygame.draw.polygon(self.screen, vis['secondary'], wing_pts_r)
        # Helmet/mask — breaks in phase 2+
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - head_s // 2, ey - sh, head_s, head_s))
        if phase >= 2:
            # Mask crack
            pygame.draw.line(self.screen, phase_accent,
                             (ex - 2, ey - sh + 2), (ex + 3, ey - sh + head_s - 2), 2)
        # Eye glow (phase colour)
        pygame.draw.rect(self.screen, phase_accent,
                         (ex - head_s // 4 - 1, ey - sh + head_s // 3, 3, 2))
        pygame.draw.rect(self.screen, phase_accent,
                         (ex + head_s // 4 - 2, ey - sh + head_s // 3, 3, 2))
        # Weapon
        if vis['weapon']:
            pygame.draw.line(self.screen, vis['weapon'],
                             (ex + body_w // 2, ey - 4), (ex + body_w // 2 + 6, ey + sh), 2)
            if phase >= 2:
                # Second weapon in phase 2+
                pygame.draw.line(self.screen, vis['weapon'],
                                 (ex - body_w // 2, ey - 4), (ex - body_w // 2 - 6, ey + sh), 2)
        # Centre glow intensifies per phase
        glow_r = int(4 * phase + 2 * math.sin(ticks * 0.005))
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*phase_accent, int(40 * phase)),
                           (glow_r, glow_r), glow_r)
        self.screen.blit(glow_surf, (ex - glow_r, ey - sh + head_s - glow_r + body_h // 3))

    def _sprite_dragon(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        """Dragon boss: big triangular head, wing blocks, tail, fire breath accent."""
        pulse = 1 + 0.04 * math.sin(ticks * 0.0025)
        size = int(s * pulse)
        sh = size // 2

        fd = getattr(enemy, 'facing_dir', (0, 1))
        face_right = fd[0] >= 0

        # Main body (large scale block)
        pygame.draw.rect(self.screen, vis['body'], (ex - sh, ey - sh + 6, size, size - 6))
        # Underbelly (secondary, lighter strip)
        belly_h = size // 4
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - sh + 4, ey + sh - belly_h - 2, size - 8, belly_h))
        # Shadow
        sr = pygame.Surface((sh, size), pygame.SRCALPHA)
        sr.fill((*vis['shadow'], 45))
        self.screen.blit(sr, (ex, ey - sh + 6))
        # Highlight
        pygame.draw.rect(self.screen, vis['highlight'], (ex - sh, ey - sh + 6, size // 3, 3))
        # Wings (triangular blocks on sides)
        wing_size = int(size * 0.5)
        wing_bob = int(4 * math.sin(ticks * 0.004 + bob))
        # Left wing
        w_pts_l = [(ex - sh, ey - sh + 10),
                    (ex - sh - wing_size, ey - sh - wing_bob),
                    (ex - sh - wing_size // 2, ey)]
        pygame.draw.polygon(self.screen, vis['secondary'], w_pts_l)
        pygame.draw.polygon(self.screen, vis['shadow'], w_pts_l, 2)
        # Right wing
        w_pts_r = [(ex + sh, ey - sh + 10),
                    (ex + sh + wing_size, ey - sh - wing_bob),
                    (ex + sh + wing_size // 2, ey)]
        pygame.draw.polygon(self.screen, vis['secondary'], w_pts_r)
        pygame.draw.polygon(self.screen, vis['shadow'], w_pts_r, 2)
        # Triangular head (pushed forward)
        head_w = size // 3
        head_h = size // 3
        hx = ex + (sh - 2 if face_right else -sh - head_w + 2)
        head_pts = [
            (hx, ey - sh + 6),
            (hx + head_w, ey - sh + 6),
            (hx + (head_w if face_right else 0), ey - sh + 6 + head_h),
        ]
        pygame.draw.polygon(self.screen, vis['body'], head_pts)
        # Eye (fire accent)
        eye_x = hx + (head_w - 5 if face_right else 3)
        eye_y = ey - sh + 10
        pygame.draw.rect(self.screen, vis['accent'], (eye_x, eye_y, 4, 3))
        # Horns (weapon colour)
        if vis['weapon']:
            pygame.draw.line(self.screen, vis['weapon'],
                             (hx + 2, ey - sh + 4), (hx - 3, ey - sh - 4), 2)
            pygame.draw.line(self.screen, vis['weapon'],
                             (hx + head_w - 2, ey - sh + 4), (hx + head_w + 3, ey - sh - 4), 2)
        # Tail (extending from rear)
        tail_x = ex + (-sh - 4 if face_right else sh + 4)
        tail_wave = int(6 * math.sin(ticks * 0.005 + bob))
        tail_pts = [
            (ex + (-sh if face_right else sh), ey + sh // 3),
            (tail_x, ey + tail_wave),
            (tail_x + (-6 if face_right else 6), ey + sh // 3 + tail_wave),
        ]
        pygame.draw.polygon(self.screen, vis['shadow'], tail_pts)
        # Fire breath glow (mouth area, pulsing)
        breath_r = int(5 + 3 * math.sin(ticks * 0.008))
        mouth_x = hx + (head_w + 2 if face_right else -2)
        mouth_y = ey - sh + 6 + head_h - 4
        breath_surf = pygame.Surface((breath_r * 2, breath_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(breath_surf, (*vis['accent'], 100), (breath_r, breath_r), breath_r)
        self.screen.blit(breath_surf, (mouth_x - breath_r, mouth_y - breath_r))
        # Totem link glow (if totems active, show accent2 pulse)
        totem_count = len(getattr(enemy, 'summons', []))
        if totem_count > 0 and vis['accent2']:
            link_r = int(sh * 0.3 + 2 * math.sin(ticks * 0.006))
            link_surf = pygame.Surface((link_r * 2, link_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(link_surf, (*vis['accent2'], 50), (link_r, link_r), link_r)
            self.screen.blit(link_surf, (ex - link_r, ey - link_r))

    # ------------------------------------------------------------------
    # Generic fallback sprite (body/secondary split with accent eyes)
    # ------------------------------------------------------------------
    def _sprite_generic(self, ex, ey, s, half, enemy, vis, ticks, at, bob, hp_pct):
        body_w = int(s * 0.8)
        body_h = int(s * 0.8)
        # Body
        pygame.draw.rect(self.screen, vis['body'],
                         (ex - body_w // 2, ey - body_h // 2, body_w, body_h))
        # Secondary lower half
        pygame.draw.rect(self.screen, vis['secondary'],
                         (ex - body_w // 2, ey, body_w, body_h // 2))
        # Shadow bottom-right
        sr = pygame.Surface((body_w // 2, body_h // 2), pygame.SRCALPHA)
        sr.fill((*vis['shadow'], 50))
        self.screen.blit(sr, (ex, ey))
        # Highlight top-left
        pygame.draw.rect(self.screen, vis['highlight'],
                         (ex - body_w // 2, ey - body_h // 2, body_w // 3, 2))
        # Accent eyes
        if vis['accent']:
            pygame.draw.rect(self.screen, vis['accent'], (ex - 3, ey - body_h // 4, 3, 3))
            pygame.draw.rect(self.screen, vis['accent'], (ex + 1, ey - body_h // 4, 3, 3))

    def _draw_player(self, player, sx, sy):
        px, py = self.camera.apply(player.x, player.y)
        px += sx
        py += sy
        half = player.size // 2
        s = player.size
        ticks = pygame.time.get_ticks()

        vis = PLAYER_VISUALS.get(player.class_name)
        invincible = player.invincible_timer > 0
        flash = invincible and int(player.invincible_timer * 20) % 2

        # Shadow
        shadow = pygame.Surface((s, s // 2), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 80), shadow.get_rect())
        self.screen.blit(shadow, (px - half, py + half - 4))

        # Stealth check (rogue)
        temp_buffs = getattr(player, 'temp_buffs', {})
        if 'stealth' in temp_buffs:
            stealth_surf = pygame.Surface((s + 16, s + 16), pygame.SRCALPHA)
            alpha = int(30 + 20 * math.sin(ticks * 0.008))
            stealth_surf.fill((100, 100, 150, alpha))
            self.screen.blit(stealth_surf, (px - half - 8, py - half - 8))

        if vis and not flash:
            body_c = vis['body']
            sec_c = vis['secondary']
            det_c = vis['detail']
            acc_c = vis['accent']
            shad_c = vis['shadow']
            hi_c = vis['highlight']

            fd = getattr(player, 'facing', (1, 0))
            face_right = fd[0] >= 0

            if player.class_name == 'warrior':
                # Blocky, broad-shouldered, heavy stance
                body_w = int(s * 0.85)
                body_h = int(s * 0.7)
                head_s = int(s * 0.35)
                shoulder_w = int(s * 0.95)

                # Body (steel armour)
                pygame.draw.rect(self.screen, body_c,
                                 (px - body_w // 2, py - half + head_s, body_w, body_h))
                # Broad shoulders
                pygame.draw.rect(self.screen, body_c,
                                 (px - shoulder_w // 2, py - half + head_s, shoulder_w, s // 6))
                # Red cloth chest stripe
                pygame.draw.rect(self.screen, sec_c,
                                 (px - body_w // 4, py - half + head_s + s // 5, body_w // 2, body_h // 2))
                # Leather belt/trim
                pygame.draw.rect(self.screen, det_c,
                                 (px - body_w // 2, py + body_h // 4, body_w, 3))
                # Helmet
                pygame.draw.rect(self.screen, hi_c,
                                 (px - head_s // 2, py - half, head_s, head_s))
                # Gold crest
                pygame.draw.rect(self.screen, acc_c,
                                 (px - 2, py - half - 3, 5, 4))
                # Visor slit
                pygame.draw.rect(self.screen, (40, 30, 30),
                                 (px - head_s // 3, py - half + head_s // 3, head_s * 2 // 3, 2))
                # Shadow bottom-right
                sr = pygame.Surface((body_w // 2, body_h // 2), pygame.SRCALPHA)
                sr.fill((*shad_c, 50))
                self.screen.blit(sr, (px, py - half + head_s + body_h // 2))
                # Sword (weapon side)
                wx = px + (body_w // 2 + 2 if face_right else -body_w // 2 - 4)
                pygame.draw.line(self.screen, (200, 200, 210),
                                 (wx, py - 4), (wx, py + half), 2)
                # Shield (off side)
                sx2 = px + (-body_w // 2 - 5 if face_right else body_w // 2 + 1)
                pygame.draw.rect(self.screen, det_c,
                                 (sx2, py - body_h // 4, 5, body_h // 2))

            elif player.class_name == 'mage':
                # Narrow vertical, robe shape, staff with glowing tip
                body_w = int(s * 0.55)
                robe_h = int(s * 0.85)
                head_s = int(s * 0.32)

                # Robe (tapers wider at bottom)
                robe_pts = [
                    (px - body_w // 3, py - half + head_s),
                    (px + body_w // 3, py - half + head_s),
                    (px + body_w // 2 + 2, py + half),
                    (px - body_w // 2 - 2, py + half),
                ]
                pygame.draw.polygon(self.screen, body_c, robe_pts)
                # Darker sash/trim
                pygame.draw.rect(self.screen, sec_c,
                                 (px - body_w // 2, py, body_w, 3))
                # Head/hood
                pygame.draw.rect(self.screen, body_c,
                                 (px - head_s // 2, py - half, head_s, head_s))
                # Pale face
                pygame.draw.rect(self.screen, det_c,
                                 (px - head_s // 3, py - half + 3, head_s * 2 // 3, head_s - 5))
                # Staff
                staff_x = px + (body_w // 3 + 3 if face_right else -body_w // 3 - 5)
                pygame.draw.line(self.screen, det_c,
                                 (staff_x, py + half), (staff_x, py - half - 8), 2)
                # Glowing orb at staff tip
                orb_r = int(3 + 2 * math.sin(ticks * 0.006))
                orb_surf = pygame.Surface((orb_r * 2 + 4, orb_r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(orb_surf, (*acc_c, 180), (orb_r + 2, orb_r + 2), orb_r)
                pygame.draw.circle(orb_surf, (*acc_c, 60), (orb_r + 2, orb_r + 2), orb_r + 2)
                self.screen.blit(orb_surf, (staff_x - orb_r - 2, py - half - 10 - orb_r))

            elif player.class_name == 'rogue':
                # Slim, hooded, daggers on both sides
                body_w = int(s * 0.5)
                body_h = int(s * 0.8)
                hood_s = int(s * 0.3)
                cloak_w = int(s * 0.7)

                # Cloak (wider at bottom)
                cloak_pts = [
                    (px - body_w // 2, py - half + hood_s),
                    (px + body_w // 2, py - half + hood_s),
                    (px + cloak_w // 2, py + half),
                    (px - cloak_w // 2, py + half),
                ]
                pygame.draw.polygon(self.screen, body_c, cloak_pts)
                # Leather straps
                pygame.draw.rect(self.screen, sec_c,
                                 (px - body_w // 2 + 2, py - half + body_h // 3, body_w - 4, body_h // 4))
                # Hood
                pygame.draw.rect(self.screen, body_c,
                                 (px - hood_s // 2, py - half, hood_s, hood_s))
                # Red scarf accent
                pygame.draw.rect(self.screen, acc_c,
                                 (px - hood_s // 2, py - half + hood_s - 3, hood_s, 3))
                # Eye slit (bright)
                pygame.draw.rect(self.screen, (200, 200, 210),
                                 (px - hood_s // 4, py - half + hood_s // 3, hood_s // 2, 2))
                # Dual daggers (silver)
                pygame.draw.line(self.screen, det_c,
                                 (px + body_w // 2 + 1, py - 4),
                                 (px + body_w // 2 + 1, py + 8), 2)
                pygame.draw.line(self.screen, det_c,
                                 (px - body_w // 2 - 2, py - 4),
                                 (px - body_w // 2 - 2, py + 8), 2)
                # Blade gleam
                pygame.draw.rect(self.screen, (255, 255, 255),
                                 (px + body_w // 2, py - 5, 2, 2))
                pygame.draw.rect(self.screen, (255, 255, 255),
                                 (px - body_w // 2 - 3, py - 5, 2, 2))

            elif player.class_name == 'healer':
                # Soft robes, staff with warm glow, approachable shape
                body_w = int(s * 0.6)
                robe_h = int(s * 0.85)
                head_s = int(s * 0.33)

                # Light robes
                robe_pts = [
                    (px - body_w // 3, py - half + head_s),
                    (px + body_w // 3, py - half + head_s),
                    (px + body_w // 2, py + half),
                    (px - body_w // 2, py + half),
                ]
                pygame.draw.polygon(self.screen, body_c, robe_pts)
                # Green secondary accent on chest
                pygame.draw.rect(self.screen, sec_c,
                                 (px - body_w // 4, py - half + head_s + 4, body_w // 2, s // 4))
                # Head (warm, visible)
                pygame.draw.rect(self.screen, hi_c,
                                 (px - head_s // 2, py - half, head_s, head_s))
                # Face
                pygame.draw.rect(self.screen, (200, 175, 145),
                                 (px - head_s // 3, py - half + 3, head_s * 2 // 3, head_s - 4))
                # Staff
                staff_x = px + (body_w // 3 + 2 if face_right else -body_w // 3 - 4)
                pygame.draw.line(self.screen, det_c,
                                 (staff_x, py + half), (staff_x, py - half - 6), 2)
                # Warm glow at staff head (gold/green pulse)
                glow_r = int(4 + 2 * math.sin(ticks * 0.004))
                glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(glow_surf, (*acc_c, 120), (glow_r + 2, glow_r + 2), glow_r)
                pygame.draw.circle(glow_surf, (*acc_c, 40), (glow_r + 2, glow_r + 2), glow_r + 2)
                self.screen.blit(glow_surf, (staff_x - glow_r - 2, py - half - 8 - glow_r))

            else:
                # Fallback
                pygame.draw.rect(self.screen, player.color,
                                 (px - half, py - half, s, s))
        else:
            # Flash white or no vis data
            color = (255, 255, 255) if flash else player.color
            pygame.draw.rect(self.screen, color, (px - half, py - half, s, s))

        # Facing direction indicator (small white dot)
        fx = px + int(player.facing[0] * 16)
        fy = py + int(player.facing[1] * 16)
        pygame.draw.circle(self.screen, (255, 255, 255), (fx, fy), 3)

        # Status effects on player
        effects = getattr(player, 'status_effects', [])
        if effects:
            effect_x = px - len(effects) * 4
            effect_y = py + half + 6
            for eff in effects:
                ecolor = getattr(eff, 'color', (255, 255, 255))
                if isinstance(ecolor, (list, tuple)) and len(ecolor) >= 3:
                    pygame.draw.circle(self.screen, ecolor[:3], (int(effect_x), int(effect_y)), 3)
                effect_x += 8

        # Temp buff visuals
        if 'shield_wall' in temp_buffs:
            pygame.draw.circle(self.screen, (100, 150, 255), (px, py), half + 10, 3)
        if 'str_boost' in temp_buffs:
            pygame.draw.circle(self.screen, (255, 200, 50), (px, py), half + 6, 2)

        # Shield effect
        if player.invincible_timer > 1.0:
            pygame.draw.circle(self.screen, (100, 150, 255), (px, py), half + 8, 2)

    def _draw_projectiles(self, projectiles, sx, sy):
        ticks = pygame.time.get_ticks()
        for proj in projectiles:
            prx, pry = self.camera.apply(proj.x, proj.y)
            prx += sx
            pry += sy

            effect = getattr(proj, 'effect', None)
            effect_name = getattr(proj, 'effect_name', None)
            owner = getattr(proj, 'owner', 'player')
            is_holy = getattr(proj, 'holy_light', False)

            is_blade = getattr(proj, 'blade_flurry', False)

            if is_blade:
                # BLADE FLURRY: spinning silver blade projectiles
                spin = ticks * 0.015 + id(proj) * 0.7
                bx, by = int(prx), int(pry)
                blade_len = 7
                # Spinning blade shape — two crossed lines
                for offset_angle in (0, math.pi / 2):
                    a = spin + offset_angle
                    x1 = bx + int(math.cos(a) * blade_len)
                    y1 = by + int(math.sin(a) * blade_len)
                    x2 = bx - int(math.cos(a) * blade_len)
                    y2 = by - int(math.sin(a) * blade_len)
                    pygame.draw.line(self.screen, (220, 220, 240), (x1, y1), (x2, y2), 2)
                # Bright center point
                pygame.draw.circle(self.screen, (255, 255, 255), (bx, by), 2)
                # Metallic glint trail
                trail_x = prx - proj.dx * 10
                trail_y = pry - proj.dy * 10
                ts = pygame.Surface((8, 8), pygame.SRCALPHA)
                glint_alpha = int(80 + 40 * math.sin(ticks * 0.02 + id(proj)))
                pygame.draw.circle(ts, (200, 200, 220, glint_alpha), (4, 4), 4)
                self.screen.blit(ts, (int(trail_x) - 4, int(trail_y) - 4))

            elif owner == 'player' and effect == 'burn':
                # FIREBALL: orange-red with flickering flame trail
                flicker = int(3 + 2 * math.sin(ticks * 0.02))
                # Outer glow
                glow_surf = pygame.Surface((20, 20), pygame.SRCALPHA)
                pygame.draw.circle(glow_surf, (255, 120, 20, 60), (10, 10), 10)
                self.screen.blit(glow_surf, (int(prx) - 10, int(pry) - 10))
                # Core
                pygame.draw.circle(self.screen, (255, 200, 60), (int(prx), int(pry)), flicker)
                pygame.draw.circle(self.screen, (255, 100, 20), (int(prx), int(pry)), flicker + 2, 1)
                # Flame trail
                for i in range(3):
                    tx = prx - proj.dx * (8 + i * 6) + math.sin(ticks * 0.03 + i) * 3
                    ty = pry - proj.dy * (8 + i * 6) + math.cos(ticks * 0.03 + i) * 3
                    r = max(1, 3 - i)
                    alpha = 150 - i * 40
                    ts = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                    pygame.draw.circle(ts, (255, 120 + i * 20, 20, alpha), (r, r), r)
                    self.screen.blit(ts, (int(tx) - r, int(ty) - r))

            elif owner == 'player' and effect == 'stun':
                # LIGHTNING BOLT: jagged yellow-white line
                # Bright core
                pygame.draw.circle(self.screen, (255, 255, 200), (int(prx), int(pry)), 4)
                # Crackling sparks
                for i in range(2):
                    spark_x = prx + math.sin(ticks * 0.04 + i * 2) * 6
                    spark_y = pry + math.cos(ticks * 0.04 + i * 2) * 6
                    pygame.draw.circle(self.screen, (200, 200, 255), (int(spark_x), int(spark_y)), 1)
                # Jagged trail
                trail_pts = [(int(prx), int(pry))]
                cx, cy = prx, pry
                for i in range(3):
                    cx -= proj.dx * 7
                    cy -= proj.dy * 7
                    cx += math.sin(ticks * 0.05 + i * 3) * 4
                    cy += math.cos(ticks * 0.05 + i * 3) * 4
                    trail_pts.append((int(cx), int(cy)))
                if len(trail_pts) > 1:
                    pygame.draw.lines(self.screen, (255, 255, 150), False, trail_pts, 2)

            elif owner == 'player' and effect == 'freeze':
                # FREEZE BLAST: pale blue expanding cone/burst
                pygame.draw.circle(self.screen, (150, 220, 255), (int(prx), int(pry)), 6)
                # Ice crystal sparkles
                for i in range(3):
                    angle = ticks * 0.01 + i * 2.094
                    sx2 = prx + math.cos(angle) * 8
                    sy2 = pry + math.sin(angle) * 8
                    pygame.draw.rect(self.screen, (200, 240, 255), (int(sx2), int(sy2), 2, 2))
                # Cold trail
                trail_x = prx - proj.dx * 12
                trail_y = pry - proj.dy * 12
                ts = pygame.Surface((16, 16), pygame.SRCALPHA)
                pygame.draw.circle(ts, (100, 200, 255, 50), (8, 8), 8)
                self.screen.blit(ts, (int(trail_x) - 8, int(trail_y) - 8))

            elif owner == 'player' and effect == 'poison':
                # POISON STRIKE projectile: green with dripping trail
                pygame.draw.circle(self.screen, (80, 200, 40), (int(prx), int(pry)), 4)
                # Drip trail
                for i in range(2):
                    dx = prx - proj.dx * (6 + i * 8)
                    dy = pry - proj.dy * (6 + i * 8) + i * 3
                    pygame.draw.circle(self.screen, (60, 180, 30), (int(dx), int(dy)), 2 - i)

            elif is_holy:
                # HOLY LIGHT: warm gold-white beam
                pygame.draw.circle(self.screen, (255, 255, 200), (int(prx), int(pry)), 5)
                # Radiant glow
                glow_surf = pygame.Surface((18, 18), pygame.SRCALPHA)
                pulse = int(40 + 20 * math.sin(ticks * 0.008))
                pygame.draw.circle(glow_surf, (255, 240, 150, pulse), (9, 9), 9)
                self.screen.blit(glow_surf, (int(prx) - 9, int(pry) - 9))
                # Light trail
                trail_x = prx - proj.dx * 10
                trail_y = pry - proj.dy * 10
                pygame.draw.line(self.screen, (255, 230, 150),
                                 (int(trail_x), int(trail_y)), (int(prx), int(pry)), 2)

            else:
                # Default projectile
                pygame.draw.circle(
                    self.screen, proj.color, (int(prx), int(pry)), 5
                )
                # Trail
                trail_x = prx - proj.dx * 10
                trail_y = pry - proj.dy * 10
                pygame.draw.line(
                    self.screen,
                    (*proj.color[:3],),
                    (int(trail_x), int(trail_y)),
                    (int(prx), int(pry)),
                    2,
                )

    def _draw_particles(self, sx, sy):
        for x, y, dx, dy, color, life in self.particles:
            px, py = self.camera.apply(x, y)
            px += sx
            py += sy
            alpha = min(255, int(life * 400))
            size = max(1, int(life * 4))
            pygame.draw.circle(self.screen, color, (int(px), int(py)), size)

    def _draw_damage_numbers(self, damage_numbers, sx, sy):
        for dmg_num in damage_numbers:
            if dmg_num.is_alive():
                dx, dy = self.camera.apply(dmg_num.x, dmg_num.y)
                dx += sx
                dy += sy
                text = self.font_small.render(
                    str(dmg_num.value), True, dmg_num.color
                )
                alpha = min(255, int(dmg_num.timer * 400))
                text.set_alpha(alpha)
                self.screen.blit(
                    text, (int(dx) - text.get_width() // 2, int(dy))
                )

    def _draw_hud(self, player, floor, game_time, ai_stats):
        """Draw the heads-up display."""
        # Semi-transparent HUD background
        hud_height = 100
        hud_surf = pygame.Surface((SCREEN_W, hud_height), pygame.SRCALPHA)
        hud_surf.fill((0, 0, 0, 180))
        self.screen.blit(hud_surf, (0, SCREEN_H - hud_height))

        y_base = SCREEN_H - hud_height + 10

        # Player info
        class_text = self.font_medium.render(
            f"{player.class_name} Lv.{player.level}", True, player.color
        )
        self.screen.blit(class_text, (10, y_base))

        # HP bar
        self._draw_bar(
            10, y_base + 30, 200, 16, player.hp, player.max_hp, (200, 30, 30), "HP"
        )

        # MP bar
        self._draw_bar(
            10,
            y_base + 50,
            200,
            16,
            int(player.mp),
            player.max_mp,
            (30, 80, 200),
            "MP",
        )

        # XP bar
        self._draw_bar(
            10,
            y_base + 70,
            200,
            10,
            player.xp,
            player.xp_to_level,
            (200, 200, 50),
            "XP",
        )

        # Abilities
        ab_x = 240
        for i, ability in enumerate(player.abilities):
            cd = player.cooldowns.get(ability.name, 0)
            # Ability box
            if cd > 0:
                box_color = (80, 80, 80)
            elif player.mp < ability.mp_cost:
                box_color = (80, 40, 40)
            else:
                box_color = (50, 120, 50)
            pygame.draw.rect(
                self.screen, box_color, (ab_x, y_base + 25, 55, 55)
            )
            pygame.draw.rect(
                self.screen, (150, 150, 150), (ab_x, y_base + 25, 55, 55), 1
            )

            # Key number
            key_text = self.font_tiny.render(str(i + 1), True, (200, 200, 200))
            self.screen.blit(key_text, (ab_x + 2, y_base + 27))

            # Ability name (abbreviated)
            ab_name = ability.name[:6]
            name_text = self.font_tiny.render(ab_name, True, (255, 255, 255))
            self.screen.blit(name_text, (ab_x + 5, y_base + 45))

            # Cooldown overlay
            if cd > 0:
                cd_text = self.font_small.render(
                    f"{cd:.1f}", True, (255, 100, 100)
                )
                self.screen.blit(cd_text, (ab_x + 15, y_base + 55))

            # MP cost
            mp_text = self.font_tiny.render(
                f"{ability.mp_cost}MP", True, (100, 150, 255)
            )
            self.screen.blit(mp_text, (ab_x + 5, y_base + 62))

            ab_x += 60

        # Floor info
        floor_text = self.font_medium.render(
            f"Floor {floor.floor_num}", True, (200, 200, 200)
        )
        self.screen.blit(floor_text, (SCREEN_W - 200, y_base))

        # Time
        mins = int(game_time) // 60
        secs = int(game_time) % 60
        time_text = self.font_small.render(
            f"Time: {mins:02d}:{secs:02d}", True, (180, 180, 180)
        )
        self.screen.blit(time_text, (SCREEN_W - 200, y_base + 30))

        # Gold and Kills
        gold = getattr(player, 'gold', 0)
        gold_text = self.font_small.render(
            f"Gold: {gold}", True, (255, 215, 0)
        )
        self.screen.blit(gold_text, (SCREEN_W - 200, y_base + 50))

        kills_text = self.font_small.render(
            f"Kills: {player.kills}", True, (180, 180, 180)
        )
        self.screen.blit(kills_text, (SCREEN_W - 100, y_base + 50))

        # AI difficulty indicator (shows ML is active)
        if ai_stats:
            diff_mod = ai_stats.get("difficulty_mod", 1.0)
            perf = ai_stats.get("performance_score", 0.5)
            if diff_mod < 1.0:
                diff_color = (50, 200, 50)
            elif diff_mod < 1.3:
                diff_color = (200, 200, 50)
            else:
                diff_color = (200, 50, 50)
            diff_text = self.font_tiny.render(
                f"AI Diff: {diff_mod:.2f} | Perf: {perf:.2f}",
                True,
                diff_color,
            )
            self.screen.blit(diff_text, (SCREEN_W - 200, y_base + 70))

    def _draw_bar(self, x, y, w, h, current, maximum, color, label):
        # Background
        pygame.draw.rect(self.screen, (30, 30, 30), (x, y, w, h))
        # Fill
        pct = current / max(maximum, 1)
        pygame.draw.rect(self.screen, color, (x, y, int(w * pct), h))
        # Border
        pygame.draw.rect(self.screen, (100, 100, 100), (x, y, w, h), 1)
        # Text
        text = self.font_tiny.render(
            f"{label}: {current}/{maximum}", True, (255, 255, 255)
        )
        self.screen.blit(text, (x + 4, y + 1))

    def _draw_minimap(self, player, floor):
        """Draw minimap in top-right corner."""
        self.minimap_surface.fill((0, 0, 0))
        scale = self.minimap_size / max(floor.width, floor.height)

        # Draw rooms
        for room in floor.rooms:
            if room.discovered:
                rx = int(room.x * scale)
                ry = int(room.y * scale)
                rw = max(2, int(room.w * scale))
                rh = max(2, int(room.h * scale))

                room_colors = {
                    "start": (100, 100, 200),
                    "mob": (80, 80, 80),
                    "elite": (200, 150, 50),
                    "boss": (200, 50, 50),
                    "treasure": (50, 200, 50),
                    "merchant": (200, 200, 100),
                    "trap": (200, 100, 50),
                    "puzzle": (100, 50, 200),
                    "hidden": (150, 50, 200),
                    "survival": (200, 100, 100),
                }
                color = room_colors.get(room.room_type, (80, 80, 80))
                if room.cleared:
                    color = tuple(max(c - 40, 30) for c in color)
                pygame.draw.rect(
                    self.minimap_surface, color, (rx, ry, rw, rh)
                )

        # Draw player position
        pp_x = int((player.x / TILE_SIZE) * scale)
        pp_y = int((player.y / TILE_SIZE) * scale)
        pygame.draw.circle(
            self.minimap_surface, (0, 255, 0), (pp_x, pp_y), 3
        )

        # Draw minimap border and blit
        pygame.draw.rect(
            self.minimap_surface,
            (100, 100, 100),
            (0, 0, self.minimap_size, self.minimap_size),
            1,
        )
        self.screen.blit(
            self.minimap_surface, (SCREEN_W - self.minimap_size - 10, 10)
        )

    def render_menu(self, selected=0):
        """Render main menu screen."""
        self.screen.fill((8, 8, 14))
        ticks = pygame.time.get_ticks()
        cx = SCREEN_W // 2

        # Ambient background particles
        for i in range(20):
            px = (ticks * 0.02 + i * 137) % SCREEN_W
            py = (ticks * 0.01 + i * 89) % SCREEN_H
            alpha = int(30 + 20 * math.sin(ticks * 0.002 + i))
            r = 1 + (i % 2)
            pygame.draw.circle(self.screen, (40, 40, 60), (int(px), int(py)), r)

        # Title: "SENT BELOW"
        title = self.font_large.render("SENT BELOW", True, (220, 195, 55))
        title_x = cx - title.get_width() // 2
        title_y = 100
        # Subtle glow behind title
        glow = pygame.Surface((title.get_width() + 40, title.get_height() + 20), pygame.SRCALPHA)
        pygame.draw.rect(glow, (220, 195, 55, 15), glow.get_rect(), border_radius=8)
        self.screen.blit(glow, (title_x - 20, title_y - 10))
        self.screen.blit(title, (title_x, title_y))

        # Tagline
        tagline = self.font_small.render(
            "Descend. Adapt. Survive.", True, (130, 130, 160)
        )
        self.screen.blit(tagline, (cx - tagline.get_width() // 2, 155))

        # Separator line
        line_w = 300
        pygame.draw.line(self.screen, (60, 60, 80),
                         (cx - line_w // 2, 185), (cx + line_w // 2, 185), 1)

        # Menu options
        options = ["New Game", "Quit"]
        for i, opt in enumerate(options):
            y = 230 + i * 55
            if i == selected:
                # Selected: highlighted box
                box_w = 200
                box_rect = pygame.Rect(cx - box_w // 2, y - 5, box_w, 40)
                sel_surf = pygame.Surface((box_w, 40), pygame.SRCALPHA)
                sel_surf.fill((220, 195, 55, 25))
                self.screen.blit(sel_surf, box_rect.topleft)
                pygame.draw.rect(self.screen, (220, 195, 55), box_rect, 2, border_radius=4)
                color = (255, 255, 130)
                arrow = self.font_medium.render(">", True, (220, 195, 55))
                self.screen.blit(arrow, (cx - box_w // 2 - 25, y))
            else:
                color = (140, 140, 150)
            text = self.font_medium.render(opt, True, color)
            self.screen.blit(text, (cx - text.get_width() // 2, y))

        # Feature cards - organized in two columns
        card_y = 380
        card_w = 230
        card_h = 58
        gap = 20
        left_x = cx - card_w - gap // 2
        right_x = cx + gap // 2

        features = [
            ("Adaptive AI", "DQN enemy agents that learn",     (100, 180, 255)),
            ("Smart Scaling", "Difficulty adjusts to your play", (180, 255, 100)),
            ("18 Enemies", "Unique behaviors across 3 tiers",   (255, 180, 80)),
            ("4 Classes", "Warrior  Mage  Rogue  Healer",       (200, 150, 255)),
            ("6 Floors", "Teach > Combine > Punish",            (255, 130, 130)),
            ("Deep Loot", "5 rarities, gold economy, merchant", (255, 215, 80)),
        ]

        for i, (label, desc, accent) in enumerate(features):
            col = i % 2
            row = i // 2
            fx = left_x if col == 0 else right_x
            fy = card_y + row * (card_h + 8)

            # Card background
            card_surf = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            card_surf.fill((20, 20, 30, 180))
            self.screen.blit(card_surf, (fx, fy))
            # Accent left edge
            pygame.draw.line(self.screen, accent, (fx, fy), (fx, fy + card_h), 3)
            # Label
            lbl = self.font_small.render(label, True, accent)
            self.screen.blit(lbl, (fx + 10, fy + 6))
            # Description
            d = self.font_tiny.render(desc, True, (150, 150, 170))
            self.screen.blit(d, (fx + 10, fy + 30))

        # Controls hint at bottom
        hint = self.font_tiny.render(
            "Arrow Keys to navigate  |  Enter to select  |  ESC to quit", True, (90, 90, 110)
        )
        self.screen.blit(hint, (cx - hint.get_width() // 2, SCREEN_H - 30))

    def render_class_select(self, selected=0):
        """Render class selection screen."""
        self.screen.fill((8, 8, 14))
        cx = SCREEN_W // 2

        title = self.font_large.render("Choose Your Class", True, (200, 200, 240))
        self.screen.blit(title, (cx - title.get_width() // 2, 35))

        classes = list(PLAYER_CLASSES.keys())
        class_colors = {
            "warrior": (220, 70, 70),
            "mage":    (80, 80, 240),
            "rogue":   (70, 220, 70),
            "healer":  (230, 210, 60),
        }
        class_desc = {
            "warrior": "Frontline tank. High HP and defence. Excels in melee brawls.",
            "mage":    "Ranged burst damage. Huge MP pool. Controls the battlefield.",
            "rogue":   "Fast and deadly. High crit chance. Thrives on positioning.",
            "healer":  "Sustain and support. Heals, purifies, and outlasts enemies.",
        }

        card_w = 220
        total_w = len(classes) * card_w + (len(classes) - 1) * 15
        start_x = cx - total_w // 2

        for i, cls_name in enumerate(classes):
            data = PLAYER_CLASSES[cls_name]
            x = start_x + i * (card_w + 15)
            y = 95
            card_h = 560
            accent = class_colors.get(cls_name, (150, 150, 150))
            is_sel = (i == selected)

            # Card background
            card_surf = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            bg_alpha = 40 if is_sel else 20
            card_surf.fill((20, 20, 35, bg_alpha + 140))
            self.screen.blit(card_surf, (x, y))

            # Border
            border_c = accent if is_sel else (50, 50, 65)
            border_w = 3 if is_sel else 1
            pygame.draw.rect(self.screen, border_c,
                             (x, y, card_w, card_h), border_w, border_radius=4)

            # Selected glow
            if is_sel:
                glow = pygame.Surface((card_w + 12, card_h + 12), pygame.SRCALPHA)
                pygame.draw.rect(glow, (*accent, 20), glow.get_rect(), border_radius=8)
                self.screen.blit(glow, (x - 6, y - 6))

            # Class colour swatch at top
            pygame.draw.rect(self.screen, accent, (x, y, card_w, 5))

            # Class name
            name_text = self.font_medium.render(cls_name.title(), True, accent)
            self.screen.blit(name_text, (x + card_w // 2 - name_text.get_width() // 2, y + 14))

            # Description
            desc = class_desc.get(cls_name, "")
            # Word-wrap description
            words = desc.split()
            lines = []
            line = ""
            for w in words:
                test = line + (" " if line else "") + w
                if self.font_tiny.size(test)[0] > card_w - 20:
                    lines.append(line)
                    line = w
                else:
                    line = test
            if line:
                lines.append(line)
            for j, ln in enumerate(lines):
                dt = self.font_tiny.render(ln, True, (140, 140, 160))
                self.screen.blit(dt, (x + 12, y + 50 + j * 16))

            # Separator
            sep_y = y + 50 + len(lines) * 16 + 8
            pygame.draw.line(self.screen, (50, 50, 65), (x + 10, sep_y), (x + card_w - 10, sep_y))

            # Stats with bars
            stat_y = sep_y + 10
            stat_defs = [
                ("HP",  data['hp'],      200, (200, 60, 60)),
                ("MP",  data['mp'],      150, (60, 80, 220)),
                ("STR", data['str'],     25,  (220, 160, 60)),
                ("DEF", data['defense'], 22,  (100, 180, 220)),
                ("SPD", data['spd'],     16,  (100, 220, 100)),
            ]
            for j, (label, val, max_val, bar_c) in enumerate(stat_defs):
                sy = stat_y + j * 26
                lbl = self.font_tiny.render(f"{label}", True, (160, 160, 180))
                self.screen.blit(lbl, (x + 12, sy))
                # Value
                vt = self.font_tiny.render(str(val), True, (200, 200, 200))
                self.screen.blit(vt, (x + 50, sy))
                # Bar
                bar_x = x + 80
                bar_w = card_w - 95
                bar_h = 8
                pygame.draw.rect(self.screen, (30, 30, 40), (bar_x, sy + 4, bar_w, bar_h))
                fill_w = int(bar_w * min(val / max_val, 1.0))
                pygame.draw.rect(self.screen, bar_c, (bar_x, sy + 4, fill_w, bar_h))

            # Abilities section
            ab_y = stat_y + 5 * 26 + 10
            ab_label = self.font_small.render("Abilities", True, (160, 160, 200))
            self.screen.blit(ab_label, (x + 12, ab_y))
            pygame.draw.line(self.screen, (50, 50, 65),
                             (x + 10, ab_y + 22), (x + card_w - 10, ab_y + 22))

            for j, ab in enumerate(data["abilities"]):
                ay = ab_y + 28 + j * 22
                # Key number
                key_c = accent if is_sel else (100, 100, 120)
                kt = self.font_tiny.render(f"[{j+1}]", True, key_c)
                self.screen.blit(kt, (x + 14, ay))
                # Ability name
                ab_text = ab.replace('_', ' ').title()
                at = self.font_tiny.render(ab_text, True, (180, 180, 200))
                self.screen.blit(at, (x + 42, ay))

        # Bottom instructions
        inst_lines = [
            ("Left / Right", "Select class"),
            ("Enter", "Confirm"),
            ("ESC", "Back to menu"),
        ]
        inst_y = SCREEN_H - 50
        total_inst_w = 0
        rendered = []
        for key, desc in inst_lines:
            k = self.font_tiny.render(f"[{key}]", True, (180, 180, 100))
            d = self.font_tiny.render(f" {desc}   ", True, (120, 120, 140))
            rendered.append((k, d))
            total_inst_w += k.get_width() + d.get_width()
        ix = cx - total_inst_w // 2
        for k, d in rendered:
            self.screen.blit(k, (ix, inst_y))
            ix += k.get_width()
            self.screen.blit(d, (ix, inst_y))
            ix += d.get_width()

    def render_inventory(self, player):
        """Render inventory overlay."""
        # Semi-transparent overlay
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        title = self.font_large.render("Inventory", True, (255, 255, 255))
        self.screen.blit(title, (SCREEN_W // 2 - title.get_width() // 2, 30))

        # Equipment slots
        equip_y = 90
        eq_label = self.font_medium.render("Equipment:", True, (200, 200, 100))
        self.screen.blit(eq_label, (50, equip_y))

        for i, (slot, item) in enumerate(player.equipment.items()):
            slot_text = f"{slot.title()}: "
            if item:
                slot_text += f"{item.name} ({item.rarity})"
                color = {
                    "common": (200, 200, 200),
                    "uncommon": (100, 255, 100),
                    "rare": (100, 100, 255),
                    "epic": (200, 50, 255),
                    "legendary": (255, 200, 50),
                }.get(item.rarity, (200, 200, 200))
            else:
                slot_text += "Empty"
                color = (100, 100, 100)
            text = self.font_small.render(slot_text, True, color)
            self.screen.blit(text, (70, equip_y + 35 + i * 30))

        # Gold display
        gold = getattr(player, 'gold', 0)
        max_inv = getattr(player, 'max_inventory', 12)
        gold_text = self.font_medium.render(f"Gold: {gold}", True, (255, 215, 0))
        self.screen.blit(gold_text, (50, 220))

        # Inventory items
        inv_y = 260
        inv_label = self.font_medium.render(
            f"Items: ({len(player.inventory)}/{max_inv})", True, (200, 200, 100))
        self.screen.blit(inv_label, (50, inv_y))

        if not player.inventory:
            text = self.font_small.render("Empty", True, (100, 100, 100))
            self.screen.blit(text, (70, inv_y + 35))
        else:
            for i, item in enumerate(player.inventory[:max_inv]):
                rarity_color = {
                    "common": (200, 200, 200),
                    "uncommon": (100, 255, 100),
                    "rare": (100, 100, 255),
                    "epic": (200, 50, 255),
                    "legendary": (255, 200, 50),
                }.get(item.rarity, (200, 200, 200))
                # Show stat summary
                stat_str = ""
                for k, v in list(item.stats.items())[:3]:
                    stat_str += f" {k}:{v:+d}" if isinstance(v, int) else f" {k}:{v}"
                text = self.font_small.render(
                    f"[{i+1}] {item.name} ({item.rarity}){stat_str}",
                    True,
                    rarity_color,
                )
                self.screen.blit(text, (70, inv_y + 35 + i * 25))

        # Player stats
        stats_x = SCREEN_W // 2 + 50
        stats_label = self.font_medium.render("Stats:", True, (200, 200, 100))
        self.screen.blit(stats_label, (stats_x, 90))

        xp_to_next = getattr(player, 'xp_to_level', 100)
        stats = [
            f"Class: {player.class_name.title()}",
            f"Level: {player.level}  (XP: {player.xp}/{xp_to_next})",
            f"HP: {player.hp}/{player.max_hp}",
            f"MP: {int(player.mp)}/{player.max_mp}",
            f"STR: {player.strength}",
            f"DEF: {player.defense}",
            f"SPD: {player.speed:.1f}",
            f"Crit: {player.crit_chance*100:.0f}%",
            f"Gold: {gold}",
            f"Kills: {player.kills}",
        ]
        for i, stat in enumerate(stats):
            text = self.font_small.render(stat, True, (180, 180, 180))
            self.screen.blit(text, (stats_x + 10, 130 + i * 28))

        # Instructions
        lines = [
            "[1-9] Use/Equip  |  [E] Auto-equip best",
            "[Shift+1-9] Drop  |  [Ctrl+1-9] Sell",
            "[Q] Drop last  |  [S] Sell last  |  [I/ESC] Close",
        ]
        for i, line in enumerate(lines):
            inst = self.font_small.render(line, True, (150, 150, 150))
            self.screen.blit(
                inst, (SCREEN_W // 2 - inst.get_width() // 2, SCREEN_H - 70 + i * 22)
            )

    def render_game_over(self, player, floor_num, game_time):
        """Render game over screen."""
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 210))
        self.screen.blit(overlay, (0, 0))
        cx = SCREEN_W // 2

        # Victory or defeat?
        max_floor = 6
        won = floor_num > max_floor
        if won:
            title_text = "DUNGEON CONQUERED"
            title_color = (220, 195, 55)
        else:
            title_text = "YOU FELL"
            title_color = (200, 60, 60)

        title = self.font_large.render(title_text, True, title_color)
        self.screen.blit(title, (cx - title.get_width() // 2, 150))

        # Subtitle
        if won:
            sub = self.font_small.render("You have escaped the depths.", True, (180, 180, 130))
        else:
            sub = self.font_small.render(
                f"Defeated on Floor {floor_num} as {player.class_name.title()}", True, (150, 150, 170))
        self.screen.blit(sub, (cx - sub.get_width() // 2, 200))

        # Stats card
        card_w = 360
        card_h = 220
        card_x = cx - card_w // 2
        card_y = 240
        card = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        card.fill((15, 15, 25, 200))
        self.screen.blit(card, (card_x, card_y))
        pygame.draw.rect(self.screen, (60, 60, 80), (card_x, card_y, card_w, card_h), 1, border_radius=4)

        mins = int(game_time) // 60
        secs = int(game_time) % 60
        gold = getattr(player, 'gold', 0)
        stats = [
            ("Floor Reached",  str(floor_num), (200, 200, 255)),
            ("Level",          str(player.level), (255, 255, 130)),
            ("Kills",          str(player.kills), (255, 150, 100)),
            ("Damage Dealt",   str(player.damage_dealt), (255, 180, 80)),
            ("Gold Earned",    str(gold), (255, 215, 80)),
            ("Time",           f"{mins:02d}:{secs:02d}", (180, 200, 220)),
        ]
        for i, (label, val, val_c) in enumerate(stats):
            sy = card_y + 15 + i * 32
            lt = self.font_small.render(label, True, (140, 140, 160))
            self.screen.blit(lt, (card_x + 20, sy))
            vt = self.font_small.render(val, True, val_c)
            self.screen.blit(vt, (card_x + card_w - vt.get_width() - 20, sy))

        # Actions
        actions = [
            ("[R]", "Play again"),
            ("[ESC]", "Quit"),
        ]
        act_y = card_y + card_h + 30
        total_w = 0
        rendered = []
        for key, desc in actions:
            k = self.font_small.render(key, True, (220, 195, 55))
            d = self.font_small.render(f" {desc}    ", True, (150, 150, 160))
            rendered.append((k, d))
            total_w += k.get_width() + d.get_width()
        ax = cx - total_w // 2
        for k, d in rendered:
            self.screen.blit(k, (ax, act_y))
            ax += k.get_width()
            self.screen.blit(d, (ax, act_y))
            ax += d.get_width()

    def render_floor_transition(self, floor_num, exit_type=None):
        """Render floor transition screen with phase context and exit type."""
        self.screen.fill((8, 8, 14))
        cx = SCREEN_W // 2
        cy = SCREEN_H // 2

        # Phase info
        if floor_num <= 2:
            phase_name = "THE DESCENT"
            phase_desc = "Learn the enemy patterns. Stay calm."
            phase_color = (100, 200, 130)
        elif floor_num <= 4:
            phase_name = "THE DEPTHS"
            phase_desc = "Enemies combine. Prioritise your targets."
            phase_color = (220, 180, 60)
        else:
            phase_name = "THE ABYSS"
            phase_desc = "Every mistake is punished. Play precisely."
            phase_color = (220, 80, 80)

        # Floor number (large)
        floor_text = self.font_large.render(f"Floor {floor_num}", True, (220, 220, 240))
        self.screen.blit(floor_text, (cx - floor_text.get_width() // 2, cy - 70))

        # Phase name
        phase_text = self.font_medium.render(phase_name, True, phase_color)
        self.screen.blit(phase_text, (cx - phase_text.get_width() // 2, cy - 10))

        # Phase description
        desc_text = self.font_small.render(phase_desc, True, (130, 130, 160))
        self.screen.blit(desc_text, (cx - desc_text.get_width() // 2, cy + 25))

        # Decorative lines
        line_w = 200
        pygame.draw.line(self.screen, (40, 40, 55),
                         (cx - line_w // 2, cy - 25), (cx + line_w // 2, cy - 25), 1)
        pygame.draw.line(self.screen, (40, 40, 55),
                         (cx - line_w // 2, cy + 55), (cx + line_w // 2, cy + 55), 1)

        # Exit type hint
        exit_hints = {
            'boss': ("A powerful foe guards the exit.", (255, 100, 100)),
            'survival': ("Survive the onslaught to advance.", (255, 180, 80)),
            'elite_formation': ("An elite squad blocks the way.", (255, 200, 100)),
            'trap_gauntlet': ("Navigate deadly traps to escape.", (255, 150, 50)),
            'puzzle_gate': ("A puzzle seals the path forward.", (150, 150, 255)),
        }
        if exit_type and exit_type in exit_hints:
            hint_text, hint_color = exit_hints[exit_type]
            hint = self.font_small.render(hint_text, True, hint_color)
            self.screen.blit(hint, (cx - hint.get_width() // 2, cy + 75))

    def render_notification(self, message, color=(255, 255, 100)):
        """Render a notification at top of screen."""
        text = self.font_medium.render(message, True, color)
        bg = pygame.Surface(
            (text.get_width() + 20, text.get_height() + 10), pygame.SRCALPHA
        )
        bg.fill((0, 0, 0, 150))
        self.screen.blit(
            bg, (SCREEN_W // 2 - text.get_width() // 2 - 10, 10)
        )
        self.screen.blit(text, (SCREEN_W // 2 - text.get_width() // 2, 15))

    # ------------------------------------------------------------------
    # AI / ML Debug Overlay (F3)
    # ------------------------------------------------------------------
    def render_ai_debug(self, ai_stats, training_stats, player, floor,
                        zone_effects, survival_rooms, projectile_count=0):
        """Draw a semi-transparent developer overlay with ML/AI metrics."""
        panel_w = 280
        panel = pygame.Surface((panel_w, SCREEN_H), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 200))
        self.screen.blit(panel, (0, 0))

        GREEN = (100, 255, 100)
        WHITE = (220, 220, 220)
        YELLOW = (255, 255, 100)
        x = 8
        y = 8

        def header(text):
            nonlocal y
            surf = self.font_small.render(text, True, GREEN)
            self.screen.blit(surf, (x, y))
            y += surf.get_height() + 4

        def line(label, value):
            nonlocal y
            lbl = self.font_tiny.render(f"{label}: ", True, WHITE)
            val = self.font_tiny.render(str(value), True, YELLOW)
            self.screen.blit(lbl, (x + 4, y))
            self.screen.blit(val, (x + 4 + lbl.get_width(), y))
            y += lbl.get_height() + 2

        def separator():
            nonlocal y
            y += 6

        # --- Panel 1: ML Enemy AI (DQN) ---
        header("ML Enemy AI (DQN)")
        line("Epsilon", f"{training_stats.get('epsilon', 0):.4f}")
        line("Training steps", training_stats.get('training_steps', 0))
        buf_size = training_stats.get('num_experiences', 0)
        line("Replay buffer", f"{buf_size} / 10000")
        line("Last loss", f"{training_stats.get('loss', 0):.6f}")
        line("Avg loss", f"{training_stats.get('avg_loss', 0):.6f}")
        line("Total actions", training_stats.get('total_steps', 0))
        separator()

        # --- Panel 2: Dynamic Difficulty ---
        header("Dynamic Difficulty")
        line("Difficulty mod", f"{ai_stats.get('difficulty_mod', 0):.3f}")
        line("Performance", f"{ai_stats.get('performance_score', 0):.3f}")
        # Survival / enjoyment from most recent history entry
        history = ai_stats.get('history', [])
        if history:
            latest = history[-1]
            line("Survival prob", f"{latest.get('predicted_survival', 0):.3f}")
            line("Enjoyment pred", f"{latest.get('predicted_enjoyment', 0):.3f}")
        else:
            line("Survival prob", "N/A")
            line("Enjoyment pred", "N/A")
        line("Total kills", ai_stats.get('total_kills', 0))
        line("Total deaths", ai_stats.get('total_deaths', 0))
        line("Rooms cleared", ai_stats.get('rooms_cleared', 0))
        separator()

        # --- Panel 3: Game State ---
        header("Game State")
        # Count alive enemies across all rooms
        alive_enemies = 0
        if floor and hasattr(floor, 'rooms'):
            for room in floor.rooms:
                alive_enemies += sum(1 for e in room.enemies if e.alive)
        line("Active enemies", alive_enemies)
        line("Active projectiles", projectile_count)
        line("Zone effects", len(zone_effects) if zone_effects else 0)
        line("Survival rooms", len(survival_rooms) if survival_rooms else 0)

        if player:
            hp_pct = player.hp / max(player.max_hp, 1) * 100
            mp_pct = player.mp / max(player.max_mp, 1) * 100
            line("Player HP", f"{hp_pct:.0f}%")
            line("Player MP", f"{mp_pct:.0f}%")
            # Status effects
            effects = getattr(player, 'status_effects', [])
            if effects:
                names = [e.name if hasattr(e, 'name') else str(e) for e in effects]
                line("Status FX", ", ".join(names))
            else:
                line("Status FX", "none")
            # Temp buffs
            buffs = getattr(player, 'temp_buffs', [])
            if buffs:
                buff_strs = []
                for b in buffs:
                    if isinstance(b, dict):
                        buff_strs.append(b.get('name', str(b)))
                    else:
                        buff_strs.append(str(b))
                line("Temp buffs", ", ".join(buff_strs))
            else:
                line("Temp buffs", "none")
        separator()

        # --- Panel 4: Content Recommendation ---
        header("Content Recommendation")
        room_weights = ai_stats.get('room_weights', None)
        if room_weights:
            for rtype, weight in sorted(room_weights.items(),
                                         key=lambda kv: -kv[1]):
                line(rtype, f"{weight:.3f}")
        else:
            lbl = self.font_tiny.render("  (use get_room_weights)", True,
                                         (150, 150, 150))
            self.screen.blit(lbl, (x, y))
            y += lbl.get_height() + 2

        # Footer hint
        separator()
        hint = self.font_tiny.render("F3 to close", True, (120, 120, 120))
        self.screen.blit(hint, (x + 4, y))
