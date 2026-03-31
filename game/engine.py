import pygame
import sys
import math
import random
from config import SCREEN_W, SCREEN_H, FPS, TILE_SIZE, PLAYER_CLASSES, ENEMY_DATA, FLOOR_EXIT_TYPE
from game.player import Player, StatusEffect
from game.enemies import Enemy, Totem
from game.dungeon import Floor
from game.combat import Projectile, DamageNumber, generate_loot, generate_enemy_loot, calculate_damage
from game.renderer import Renderer
from ai.enemy_ai import EnemyBrain
from ai.director import AIDirector


def _nearest_walkable(x, y, dungeon, search_radius=5):
    """Find the nearest walkable pixel position to (x, y).

    Searches in a spiral of tiles around the given pixel position.
    Returns (new_x, new_y) snapped to the centre of the nearest walkable tile,
    or the original position if nothing is found within *search_radius* tiles.
    """
    tx = int(x // TILE_SIZE)
    ty = int(y // TILE_SIZE)
    if dungeon.is_walkable(tx, ty):
        return x, y  # already fine
    best = None
    best_dist = float('inf')
    for r in range(1, search_radius + 1):
        for dtx in range(-r, r + 1):
            for dty in range(-r, r + 1):
                if abs(dtx) != r and abs(dty) != r:
                    continue  # only check the ring
                ntx, nty = tx + dtx, ty + dty
                if dungeon.is_walkable(ntx, nty):
                    cx = ntx * TILE_SIZE + TILE_SIZE // 2
                    cy = nty * TILE_SIZE + TILE_SIZE // 2
                    d = (cx - x) ** 2 + (cy - y) ** 2
                    if d < best_dist:
                        best_dist = d
                        best = (float(cx), float(cy))
        if best is not None:
            return best
    return x, y

class GameEngine:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Sent Below")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()
        self.renderer = Renderer(self.screen)

        # Game state
        self.state = 'menu'
        self.menu_selection = 0
        self.class_selection = 0

        # Game objects
        self.player = None
        self.floor = None
        self.floor_num = 1
        self.max_floors = 6
        self.projectiles = []
        self.damage_numbers = []
        self.game_time = 0
        self.floor_start_time = 0

        # ML systems
        self.enemy_brain = EnemyBrain()
        self.ai_director = AIDirector()

        # Notifications
        self.notifications = []  # (message, color, timer)

        # Floor transition
        self.transition_timer = 0

        # Active zone effects (smoke bombs, divine shields, hazard zones, meteors)
        self.zone_effects = []  # list of dicts: {type, x, y, radius, duration, ...}

        # Survival room state
        self.survival_rooms = {}  # room_idx -> {wave, timer, spawned}

        # Totems spawned by bosses
        self.totems = []

        # Developer AI debug overlay (toggle with F3)
        self.show_ai_debug = False

        self.running = True

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 0.05)  # cap delta time

            self._handle_events()
            self._update(dt)
            self._render()

            pygame.display.flip()

        pygame.quit()
        sys.exit()

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            if event.type == pygame.KEYDOWN:
                if self.state == 'menu':
                    self._handle_menu_input(event)
                elif self.state == 'class_select':
                    self._handle_class_select_input(event)
                elif self.state == 'playing':
                    self._handle_game_input(event)
                elif self.state == 'inventory':
                    self._handle_inventory_input(event)
                elif self.state == 'game_over':
                    self._handle_game_over_input(event)
                elif self.state == 'paused':
                    if event.key == pygame.K_ESCAPE:
                        self.state = 'playing'

            if event.type == pygame.MOUSEBUTTONDOWN and self.state == 'playing':
                self._handle_mouse_click(event)

    def _handle_menu_input(self, event):
        if event.key == pygame.K_UP:
            self.menu_selection = max(0, self.menu_selection - 1)
        elif event.key == pygame.K_DOWN:
            self.menu_selection = min(1, self.menu_selection + 1)
        elif event.key == pygame.K_RETURN:
            if self.menu_selection == 0:
                self.state = 'class_select'
            else:
                self.running = False

    def _handle_class_select_input(self, event):
        classes = list(PLAYER_CLASSES.keys())
        if event.key == pygame.K_LEFT:
            self.class_selection = (self.class_selection - 1) % len(classes)
        elif event.key == pygame.K_RIGHT:
            self.class_selection = (self.class_selection + 1) % len(classes)
        elif event.key == pygame.K_RETURN:
            self._start_game(classes[self.class_selection])
        elif event.key == pygame.K_ESCAPE:
            self.state = 'menu'

    def _handle_game_input(self, event):
        if event.key == pygame.K_ESCAPE:
            self.state = 'paused'
        elif event.key == pygame.K_i or event.key == pygame.K_TAB:
            self.state = 'inventory'
        elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
            # Use ability
            idx = event.key - pygame.K_1
            mouse_pos = pygame.mouse.get_pos()
            cam = self.renderer.camera
            target_x = mouse_pos[0] + cam.x
            target_y = mouse_pos[1] + cam.y
            nearby = self.floor.get_nearby_enemies(self.player.x, self.player.y, 500)
            results = self.player.use_ability(idx, (target_x, target_y), nearby)
            self._process_ability_results(results)
        elif event.key == pygame.K_e:
            # Pick up nearby items
            self._pickup_items()
        elif event.key == pygame.K_f:
            # Interact (stairs, merchant, puzzle)
            self._interact()
        elif event.key == pygame.K_p:
            self.show_ai_debug = not self.show_ai_debug

    def _handle_inventory_input(self, event):
        if event.key == pygame.K_i or event.key == pygame.K_TAB or event.key == pygame.K_ESCAPE:
            self.state = 'playing'
        elif event.key == pygame.K_e:
            # Auto-equip best items
            self._auto_equip()
        elif event.key == pygame.K_q:
            # Drop mode: drop the last item or selected item
            if self.player.inventory:
                self._drop_item(len(self.player.inventory) - 1)
        elif event.key == pygame.K_s:
            # Sell last item for gold
            if self.player.inventory:
                self._sell_item(len(self.player.inventory) - 1)
        elif pygame.K_1 <= event.key <= pygame.K_9:
            idx = event.key - pygame.K_1
            if idx < len(self.player.inventory):
                # Hold shift (check mod keys) to drop, otherwise use/equip
                mods = pygame.key.get_mods()
                if mods & pygame.KMOD_SHIFT:
                    self._drop_item(idx)
                elif mods & pygame.KMOD_CTRL:
                    self._sell_item(idx)
                else:
                    item = self.player.inventory[idx]
                    if item.item_type == 'consumable':
                        self.player.use_consumable(item)
                        self._add_notification(f"Used {item.name}!", (100, 255, 100))
                    elif item.item_type in ('weapon', 'armor', 'accessory'):
                        self.player.equip_item(item)
                        self._add_notification(f"Equipped {item.name}!", (100, 200, 255))

    def _handle_game_over_input(self, event):
        if event.key == pygame.K_r:
            self.state = 'class_select'
        elif event.key == pygame.K_ESCAPE:
            self.running = False

    def _handle_mouse_click(self, event):
        if event.button == 1:  # Left click - basic attack
            cam = self.renderer.camera
            target_x = event.pos[0] + cam.x
            target_y = event.pos[1] + cam.y
            nearby = self.floor.get_nearby_enemies(self.player.x, self.player.y, 200)
            results = self.player.basic_attack((target_x, target_y), nearby)
            self._process_attack_results(results)

    def _start_game(self, class_name):
        self.player = Player(class_name)
        self.floor_num = 1
        self.projectiles = []
        self.damage_numbers = []
        self.game_time = 0
        self.notifications = []
        self.ai_director = AIDirector()
        self.enemy_brain = EnemyBrain()
        self._generate_floor()
        self.state = 'floor_transition'
        self.transition_timer = 2.0
        self._add_notification(f"Starting as {class_name}!", self.player.color)

    def _generate_floor(self):
        """Generate a new dungeon floor."""
        # Get room weights from AI director
        room_weights = self.ai_director.get_room_weights(
            self.player.get_stats_dict() if self.player else {},
            self.floor_num
        )
        diff_mod = self.ai_director.get_difficulty_modifier()

        self.floor = Floor(self.floor_num)
        self.floor.generate(difficulty_mod=diff_mod, room_type_weights=room_weights)

        # Place player at start room
        start = self.floor.start_room
        self.player.x = float(start.pixel_center_x)
        self.player.y = float(start.pixel_center_y)
        self.floor_start_time = self.game_time

        self.projectiles = []

        self.ai_director.record_event('floor_start', {'floor': self.floor_num}, self.game_time)

    def _update(self, dt):
        if self.state == 'floor_transition':
            self.transition_timer -= dt
            if self.transition_timer <= 0:
                self.state = 'playing'
            return

        if self.state != 'playing':
            return

        self.game_time += dt

        # Update player
        self._update_player_movement(dt)
        self.player.update(dt)

        # --- Out-of-bounds wall damage for player ---
        ptx = int(self.player.x // TILE_SIZE)
        pty = int(self.player.y // TILE_SIZE)
        if not self.floor.is_walkable(ptx, pty):
            # 15% of current HP per second while inside a wall
            wall_dmg = max(1, int(self.player.hp * 0.15 * dt))
            self.player.hp -= wall_dmg
            self.player.damage_taken += wall_dmg
            self.damage_numbers.append(
                DamageNumber(self.player.x, self.player.y - 30, wall_dmg, (200, 50, 50)))
            if self.player.hp <= 0:
                self.player.hp = 0
                self.player.alive = False

        # Check if player is dead
        if not self.player.alive:
            self.state = 'game_over'
            self.ai_director.record_event('death', {'floor': self.floor_num}, self.game_time)
            return

        # Update enemies
        self._update_enemies(dt)

        # Update projectiles
        self._update_projectiles(dt)

        # Update zone effects (smoke, divine shield, hazard zones, meteors)
        self._update_zone_effects(dt)

        # Update survival rooms
        self._update_survival_rooms(dt)

        # Update totems
        self._update_totems(dt)

        # Check traps
        trap_dmg, trap_type = self.floor.check_traps(self.player, self.game_time)
        if trap_dmg > 0:
            actual = self.player.take_damage(trap_dmg)
            if actual > 0:
                self.damage_numbers.append(DamageNumber(self.player.x, self.player.y - 20, actual, (255, 150, 50)))
                self.renderer.add_shake(3, 0.1)
                if trap_type:
                    self._add_notification(f"Hit a {trap_type} trap!", (255, 150, 50))

        # Check puzzle plates
        self._check_puzzles()

        # Discover rooms
        self._discover_rooms()

        # Check room clears
        self._check_room_clears()

        # Update AI director
        self.ai_director.update(self.player.get_stats_dict(), self.floor_num, self.game_time, dt)

        # Train enemy brain periodically
        if len(self.enemy_brain.replay_buffer) > 64:
            self.enemy_brain.train_step()

        # Update damage numbers
        self.damage_numbers = [d for d in self.damage_numbers if d.is_alive()]
        for d in self.damage_numbers:
            d.update(dt)

        # Update notifications
        self.notifications = [(m, c, t - dt) for m, c, t in self.notifications if t > 0]

        # Update renderer
        self.renderer.update(self.player.x, self.player.y, dt)

    def _update_player_movement(self, dt):
        keys = pygame.key.get_pressed()
        dx, dy = 0, 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy = -1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy = 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx = -1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx = 1

        # Normalize diagonal movement
        if dx != 0 and dy != 0:
            dx *= 0.707
            dy *= 0.707

        if dx != 0 or dy != 0:
            self.player.move(dx, dy, self.floor, dt)

    def _update_enemies(self, dt):
        nearby_enemies = self.floor.get_nearby_enemies(self.player.x, self.player.y, 500)

        for enemy in nearby_enemies:
            if not enemy.alive:
                continue

            # Store pre-action state for ML
            prev_state = enemy._get_state_vector(self.player,
                math.sqrt((enemy.x - self.player.x)**2 + (enemy.y - self.player.y)**2))
            prev_hp = self.player.hp

            # Update enemy
            results = enemy.update(self.player, self.floor, dt, self.enemy_brain)

            # Process enemy action results
            for result in results:
                if isinstance(result, Projectile):
                    self.projectiles.append(result)
                elif isinstance(result, tuple) and len(result) >= 2:
                    rtype = result[0]
                    if rtype == 'melee':
                        dmg = result[1]
                        if dmg > 0:
                            self.damage_numbers.append(
                                DamageNumber(self.player.x, self.player.y - 20, dmg, (255, 80, 80)))
                            self.renderer.add_shake(4, 0.15)
                            self.ai_director.record_event('player_hit', {'damage': dmg}, self.game_time)

                    elif rtype == 'split':
                        # Slime split: spawn a smaller slime at the given position
                        sx, sy = result[1], result[2]
                        room_idx, room = self.floor.get_room_at(int(sx // TILE_SIZE), int(sy // TILE_SIZE))
                        if room:
                            child = Enemy('slime', sx, sy, self.floor_num, self.ai_director.get_difficulty_modifier())
                            child.max_hp = enemy.max_hp // 3
                            child.hp = child.max_hp
                            child.strength = max(1, enemy.strength // 2)
                            child.size = max(8, enemy.size * 0.6)
                            room.enemies.append(child)

                    elif rtype == 'charge':
                        # Enemy charged to a position and dealt damage
                        tx, ty, dmg = result[1], result[2], result[3]
                        if dmg > 0:
                            self.damage_numbers.append(
                                DamageNumber(self.player.x, self.player.y - 20, dmg, (255, 120, 50)))
                            self.renderer.add_shake(6, 0.2)
                            self.ai_director.record_event('player_hit', {'damage': dmg}, self.game_time)

                    elif rtype == 'aoe':
                        # Area of effect damage at position
                        ax, ay, aradius, admg = result[1], result[2], result[3], result[4]
                        pdist = math.sqrt((self.player.x - ax)**2 + (self.player.y - ay)**2)
                        if pdist < aradius:
                            actual = self.player.take_damage(admg)
                            if actual > 0:
                                self.damage_numbers.append(
                                    DamageNumber(self.player.x, self.player.y - 20, actual, (255, 100, 50)))
                                self.renderer.add_shake(5, 0.2)
                                self.ai_director.record_event('player_hit', {'damage': actual}, self.game_time)
                        self.renderer.add_particles(ax, ay, (255, 150, 50), 12)

                    elif rtype == 'heal_allies':
                        heal_amount, heal_radius = result[1], result[2]
                        for e in nearby_enemies:
                            if e != enemy and e.alive:
                                edist = math.sqrt((e.x - enemy.x)**2 + (e.y - enemy.y)**2)
                                if edist < heal_radius:
                                    e.hp = min(e.max_hp, e.hp + heal_amount)
                                    self.damage_numbers.append(
                                        DamageNumber(e.x, e.y - 20, heal_amount, (100, 255, 100)))

                    elif rtype == 'buff_allies':
                        stat, amount, duration, buff_radius = result[1], result[2], result[3], result[4]
                        for e in nearby_enemies:
                            if e != enemy and e.alive:
                                edist = math.sqrt((e.x - enemy.x)**2 + (e.y - enemy.y)**2)
                                if edist < buff_radius:
                                    if stat == 'strength':
                                        e.strength = int(e.strength * (1.0 + amount))
                                    self._add_notification(f"Enemies empowered!", (255, 150, 150))

                    elif rtype == 'hazard_zone':
                        hx, hy, hradius = result[1], result[2], result[3]
                        self.zone_effects.append({
                            'type': 'hazard', 'x': hx, 'y': hy,
                            'radius': hradius, 'duration': 5.0,
                            'damage': 15, 'tick': 0.0,
                            'color': (200, 50, 50, 80),
                        })

                    elif rtype == 'teleport':
                        # Enemy teleported — add visual at old position
                        ox, oy = result[1], result[2]
                        self.renderer.add_particles(ox, oy, (150, 50, 200), 10)

                    elif rtype == 'summon':
                        self._spawn_summons(enemy)

                    elif rtype == 'summon_totem':
                        tx, ty = result[1], result[2]
                        totem = Totem(tx, ty)
                        room_idx, room = self.floor.get_room_at(int(tx // TILE_SIZE), int(ty // TILE_SIZE))
                        if room:
                            room.enemies.append(totem)
                        self.totems.append(totem)
                        self._add_notification("A healing totem appeared!", (100, 255, 100))

                    elif rtype == 'counter_stance':
                        self._add_notification(f"{enemy.name} enters counter stance!", (255, 200, 50))

            # --- Clamp enemy back to walkable tile if knocked outside walls ---
            etx = int(enemy.x // TILE_SIZE)
            ety = int(enemy.y // TILE_SIZE)
            if not self.floor.is_walkable(etx, ety):
                enemy.x, enemy.y = _nearest_walkable(
                    enemy.x, enemy.y, self.floor)

            # ML: compute reward and store experience
            if enemy.alive and len(enemy.actions_taken) > 0:
                post_state = enemy._get_state_vector(self.player,
                    math.sqrt((enemy.x - self.player.x)**2 + (enemy.y - self.player.y)**2))
                action_idx = ['chase', 'flee', 'attack', 'ranged_attack', 'strafe', 'support_cast', 'idle'].index(
                    enemy.actions_taken[-1]) if enemy.actions_taken[-1] in ['chase', 'flee', 'attack', 'ranged_attack', 'strafe', 'support_cast', 'idle'] else 6

                # Reward: positive for damaging player, negative for getting close to death
                reward = 0
                if self.player.hp < prev_hp:
                    reward += (prev_hp - self.player.hp) * 0.1
                reward -= (1 - enemy.hp / max(enemy.max_hp, 1)) * 0.05

                self.enemy_brain.store_experience(prev_state, action_idx, reward, post_state, not enemy.alive)

    def _update_projectiles(self, dt):
        alive_projectiles = []
        for proj in self.projectiles:
            # Homing: find nearest target for the projectile
            homing_target = None
            if proj.homing > 0:
                if proj.owner == 'player':
                    nearest_dist = 300
                    for e in self.floor.get_nearby_enemies(proj.x, proj.y, 300):
                        if e.alive:
                            d = math.sqrt((e.x - proj.x)**2 + (e.y - proj.y)**2)
                            if d < nearest_dist:
                                nearest_dist = d
                                homing_target = e
                else:
                    homing_target = self.player

            if not proj.update(dt, target=homing_target, dungeon=self.floor):
                continue  # projectile expired

            if proj.owner == 'player':
                # Check divine shield zones blocking enemy projectiles — N/A for player proj
                hit_any = False
                for enemy in self.floor.get_nearby_enemies(proj.x, proj.y, 100):
                    if not enemy.alive:
                        continue
                    # Skip already-hit enemies for piercing projectiles
                    if proj.piercing and proj.has_hit(id(enemy)):
                        continue
                    if proj.get_rect().colliderect(enemy.get_rect()):
                        dmg, crit, miss = calculate_damage(proj.damage, 0, enemy.defense, 0.1)
                        if miss:
                            self.damage_numbers.append(
                                DamageNumber(enemy.x, enemy.y - 20, "MISS!", (180, 180, 180)))
                        else:
                            # Holy light: 2x vs undead, heal player on hit
                            if getattr(proj, 'holy_light', False):
                                if getattr(enemy, 'behavior', '') in ('undead_soldier', 'skeleton'):
                                    dmg = int(dmg * getattr(proj, 'undead_multiplier', 2.0))
                                heal_amt = getattr(proj, 'heal_on_hit', 0)
                                if heal_amt > 0:
                                    self.player.hp = min(self.player.max_hp, self.player.hp + heal_amt)
                                    self.damage_numbers.append(
                                        DamageNumber(self.player.x, self.player.y - 30, heal_amt, (100, 255, 100)))

                            enemy.take_damage(dmg)
                            self.player.damage_dealt += dmg
                            color = (255, 255, 100) if crit else (255, 255, 255)
                            self.damage_numbers.append(DamageNumber(enemy.x, enemy.y - 20, dmg, color))
                            self.renderer.add_particles(enemy.x, enemy.y, enemy.color, 5)

                            # Apply status effect from projectile
                            if proj.effect and hasattr(enemy, 'apply_status_effect'):
                                try:
                                    from game.combat import StatusEffect as CombatStatusEffect
                                    dur = proj.effect_duration if proj.effect_duration > 0 else 3.0
                                    enemy.apply_status_effect(CombatStatusEffect(proj.effect, dur))
                                except (KeyError, Exception):
                                    pass

                            if not enemy.alive:
                                self._on_enemy_killed(enemy)

                        proj.register_hit(id(enemy))
                        hit_any = True
                        if not proj.piercing:
                            break

                if not hit_any or (proj.piercing and proj.alive):
                    alive_projectiles.append(proj)

            elif proj.owner == 'enemy':
                # Check if blocked by divine shield zone
                blocked = False
                for zone in self.zone_effects:
                    if zone['type'] == 'divine_shield':
                        zdist = math.sqrt((proj.x - zone['x'])**2 + (proj.y - zone['y'])**2)
                        if zdist < zone['radius']:
                            blocked = True
                            self.renderer.add_particles(proj.x, proj.y, (255, 255, 200), 4)
                            break

                if blocked:
                    continue  # projectile destroyed by shield

                if proj.get_rect().colliderect(self.player.get_rect()):
                    # Apply effect on player
                    if proj.effect and proj.effect in ('burn', 'poison', 'slow', 'curse', 'blind'):
                        dur = proj.effect_duration if proj.effect_duration > 0 else 3.0
                        self.player.apply_status_effect(StatusEffect(proj.effect, dur))

                    actual = self.player.take_damage(proj.damage)
                    if actual > 0:
                        self.damage_numbers.append(
                            DamageNumber(self.player.x, self.player.y - 20, actual, (255, 80, 80)))
                        self.renderer.add_shake(3, 0.1)
                        self.ai_director.record_event('player_hit', {'damage': actual}, self.game_time)
                else:
                    alive_projectiles.append(proj)
            else:
                alive_projectiles.append(proj)

        self.projectiles = alive_projectiles

    def _on_enemy_killed(self, enemy):
        self.player.kills += 1
        leveled = self.player.gain_xp(enemy.xp_reward)
        if leveled:
            self._add_notification(f"Level Up! Lv.{self.player.level} - Stats increased!", (255, 255, 100))
            self.renderer.add_shake(3, 0.3)

        # --- New loot system: gold + item based on tier/floor phase ---
        gold, item = generate_enemy_loot(self.floor_num, enemy.tier)
        self.player.gold += gold
        self.damage_numbers.append(DamageNumber(enemy.x, enemy.y - 30, f"+{gold}g", (255, 215, 0)))

        self.ai_director.record_event('enemy_killed', {
            'enemy': enemy.name, 'tier': enemy.tier,
            'time_alive': enemy.time_alive
        }, self.game_time)

        self.renderer.add_particles(enemy.x, enemy.y, enemy.color, 15)

        # Place dropped item on the ground
        if item is not None:
            item.x = enemy.x + random.randint(-15, 15)
            item.y = enemy.y + random.randint(-15, 15)
            room_idx, room = self.floor.get_room_at(int(enemy.x // TILE_SIZE), int(enemy.y // TILE_SIZE))
            if room:
                room.items.append(item)
                rarity_color = {
                    'common': (200, 200, 200), 'uncommon': (100, 255, 100),
                    'rare': (100, 100, 255), 'epic': (200, 50, 255),
                    'legendary': (255, 200, 50),
                }.get(item.rarity, (200, 200, 200))
                self._add_notification(f"{item.rarity.title()} drop!", rarity_color)

        # Boss: guaranteed extra loot drops (2-3 items)
        if enemy.tier == 'boss':
            bonus_loot = generate_loot(self.floor_num, 'boss')
            room_idx, room = self.floor.get_room_at(int(enemy.x // TILE_SIZE), int(enemy.y // TILE_SIZE))
            if room:
                for bitem in bonus_loot:
                    bitem.x = enemy.x + random.randint(-30, 30)
                    bitem.y = enemy.y + random.randint(-30, 30)
                    room.items.append(bitem)
                if bonus_loot:
                    self._add_notification(f"Boss loot! {len(bonus_loot)} items dropped!", (255, 215, 0))

    def _spawn_summons(self, boss):
        """Spawn adds for summoning bosses."""
        import random
        from config import FLOOR_ENEMY_POOLS
        pool = FLOOR_ENEMY_POOLS.get(self.floor_num, FLOOR_ENEMY_POOLS[6])
        trash = pool['trash'] if pool['trash'] else ['goblin', 'skeleton']
        room_idx, room = self.floor.get_room_at(int(boss.x // TILE_SIZE), int(boss.y // TILE_SIZE))
        if room:
            for _ in range(2):
                name = random.choice(trash)
                ex = boss.x + random.randint(-80, 80)
                ey = boss.y + random.randint(-80, 80)
                new_enemy = Enemy(name, ex, ey, self.floor_num, self.ai_director.get_difficulty_modifier())
                room.enemies.append(new_enemy)
            self._add_notification("The boss summons reinforcements!", (255, 100, 100))

    def _pickup_items(self):
        """Pick up items near the player. Respects inventory limit."""
        px, py = self.player.x, self.player.y

        if len(self.player.inventory) >= self.player.max_inventory:
            self._add_notification(f"Inventory full! ({self.player.max_inventory}/{self.player.max_inventory}) Drop items first.", (255, 100, 100))
            return

        for room in self.floor.rooms:
            items_to_remove = []
            for item in room.items:
                if len(self.player.inventory) >= self.player.max_inventory:
                    break
                dist = math.sqrt((item.x - px)**2 + (item.y - py)**2)
                if dist < 50:
                    self.player.inventory.append(item)
                    items_to_remove.append(item)
                    self._add_notification(f"Picked up {item.name}! ({len(self.player.inventory)}/{self.player.max_inventory})", (200, 200, 50))
            for item in items_to_remove:
                room.items.remove(item)

        # Merchant: buy with gold
        room_idx, room = self.floor.get_room_at(int(px // TILE_SIZE), int(py // TILE_SIZE))
        if room and room.room_type == 'merchant' and room.merchant_items:
            if len(self.player.inventory) >= self.player.max_inventory:
                self._add_notification("Inventory full! Can't buy.", (255, 100, 100))
                return
            item = room.merchant_items[0]
            price = self._get_item_price(item)
            if self.player.gold >= price:
                self.player.gold -= price
                room.merchant_items.pop(0)
                self.player.inventory.append(item)
                self._add_notification(f"Bought {item.name} for {price}g! ({self.player.gold}g left)", (200, 200, 100))
            else:
                self._add_notification(f"{item.name} costs {price}g (you have {self.player.gold}g)", (255, 150, 100))

    def _get_item_price(self, item):
        """Calculate buy price based on rarity ranges from SELL_PRICES (buy = ~2.5x sell)."""
        from config import SELL_PRICES
        price_range = SELL_PRICES.get(item.rarity, (8, 12))
        base = int((price_range[0] + price_range[1]) / 2 * 2.5)
        stat_bonus = sum(abs(v) for v in item.stats.values() if isinstance(v, (int, float)))
        return base + int(stat_bonus * 1.5)

    def _get_sell_price(self, item):
        """Sell price from rarity-based ranges."""
        from config import SELL_PRICES
        price_range = SELL_PRICES.get(item.rarity, (8, 12))
        base = random.randint(price_range[0], price_range[1])
        stat_bonus = sum(abs(v) for v in item.stats.values() if isinstance(v, (int, float)))
        return max(1, base + int(stat_bonus * 0.5))

    def _drop_item(self, idx):
        """Drop an item from inventory onto the ground."""
        if idx >= len(self.player.inventory):
            return
        item = self.player.inventory.pop(idx)
        item.x = self.player.x + random.randint(-20, 20)
        item.y = self.player.y + random.randint(-20, 20)
        room_idx, room = self.floor.get_room_at(
            int(self.player.x // TILE_SIZE), int(self.player.y // TILE_SIZE))
        if room:
            room.items.append(item)
        self._add_notification(f"Dropped {item.name}", (180, 180, 150))

    def _sell_item(self, idx):
        """Sell an item from inventory for gold."""
        if idx >= len(self.player.inventory):
            return
        item = self.player.inventory[idx]
        price = self._get_sell_price(item)
        self.player.inventory.pop(idx)
        self.player.gold += price
        self._add_notification(f"Sold {item.name} for {price}g! ({self.player.gold}g)", (255, 215, 0))

    def _interact(self):
        """Interact with stairs, puzzles, etc. Uses radius check so you
        don't need pixel-perfect positioning."""
        px, py = self.player.x, self.player.y
        interact_radius = TILE_SIZE * 1.5  # generous radius

        # Check stairs — scan nearby tiles in a radius
        found_stairs = False
        cx, cy = int(px // TILE_SIZE), int(py // TILE_SIZE)
        for oy in range(-2, 3):
            for ox in range(-2, 3):
                ttx, tty = cx + ox, cy + oy
                if 0 <= ttx < self.floor.width and 0 <= tty < self.floor.height:
                    if self.floor.grid[tty][ttx] == 4:
                        # Check pixel distance to tile center
                        tile_cx = ttx * TILE_SIZE + TILE_SIZE // 2
                        tile_cy = tty * TILE_SIZE + TILE_SIZE // 2
                        dist = math.sqrt((px - tile_cx)**2 + (py - tile_cy)**2)
                        if dist < interact_radius:
                            found_stairs = True
                            break
            if found_stairs:
                break

        if found_stairs:
            exit_type = getattr(self.floor, 'exit_type', 'boss')
            exit_room = getattr(self.floor, 'exit_room', self.floor.boss_room)

            if exit_type == 'boss':
                if self.floor.boss_room and self.floor.boss_room.cleared:
                    self._next_floor()
                elif self.floor.boss_room:
                    self._add_notification("Defeat the boss first!", (255, 100, 100))
                else:
                    self._next_floor()
            elif exit_type == 'survival':
                if exit_room and exit_room.cleared:
                    self._next_floor()
                else:
                    self._add_notification("Survive all waves first!", (255, 100, 100))
            elif exit_type == 'elite_formation':
                if exit_room and exit_room.cleared:
                    self._next_floor()
                else:
                    self._add_notification("Defeat the elite formation!", (255, 100, 100))
            elif exit_type == 'trap_gauntlet':
                # Trap gauntlet: puzzle_state solved or traps cleared
                ps = getattr(exit_room, 'puzzle_state', None) if exit_room else None
                if exit_room and (exit_room.cleared or (ps and ps.get('solved', False))):
                    self._next_floor()
                elif exit_room and not exit_room.traps:
                    self._next_floor()  # traps already cleared
                else:
                    self._add_notification("Navigate through the traps to escape!", (255, 150, 50))
            elif exit_type == 'puzzle_gate':
                ps = getattr(exit_room, 'puzzle_state', None) if exit_room else None
                if exit_room and ps and ps.get('solved', False):
                    self._next_floor()
                elif exit_room and exit_room.cleared:
                    self._next_floor()
                else:
                    self._add_notification("Solve the puzzle to unlock the exit!", (200, 200, 255))
            else:
                self._next_floor()

    def _next_floor(self):
        """Advance to next floor."""
        floor_time = self.game_time - self.floor_start_time
        self.player.floor_times.append(floor_time)
        self.ai_director.record_event('floor_clear', {
            'floor': self.floor_num, 'time': floor_time,
            'hp_remaining': self.player.hp / self.player.max_hp
        }, self.game_time)

        self.floor_num += 1
        if self.floor_num > self.max_floors:
            self.state = 'game_over'  # Victory!
            self._add_notification("You conquered the dungeon!", (255, 255, 100))
            return

        # Heal player partially between floors
        self.player.hp = min(self.player.max_hp, self.player.hp + self.player.max_hp // 3)
        self.player.mp = self.player.max_mp

        self._generate_floor()
        self.state = 'floor_transition'
        self.transition_timer = 2.0
        self._add_notification(f"Descending to Floor {self.floor_num}...", (200, 200, 255))

    def _check_puzzles(self):
        """Check puzzle interactions: sequence, alignment, element, pathing, combat, weight."""
        tx = int(self.player.x // TILE_SIZE)
        ty = int(self.player.y // TILE_SIZE)

        for room in self.floor.rooms:
            if room.room_type not in ('puzzle', 'trap'):
                continue
            if not room.puzzle_state or room.puzzle_state.get('solved', False):
                continue

            ps = room.puzzle_state
            template_name = ps.get('puzzle_template', ps.get('trap_template', ''))
            n_elements = len(ps['plates'])

            # --- Sequence / rune / statue / element / weight puzzles ---
            if ps.get('correct_order') is not None:
                # Player must step on plates in correct_order sequence
                step = ps.get('current_step', 0)
                for i, (px, py) in enumerate(ps['plates']):
                    if tx == px and ty == py and not ps['activated'][i]:
                        expected_idx = ps['correct_order'][step]
                        if i == expected_idx:
                            # Correct!
                            ps['activated'][i] = True
                            ps['current_step'] = step + 1
                            self._add_notification(
                                f"Step {step + 1}/{n_elements} correct!",
                                (100, 255, 100))
                        else:
                            # Wrong order - apply fail penalty
                            penalty = ps.get('fail_penalty', 'reset')
                            if penalty == 'spawn':
                                # Spawn a skeleton as punishment
                                from config import FLOOR_ENEMY_POOLS
                                pool = FLOOR_ENEMY_POOLS.get(self.floor_num, FLOOR_ENEMY_POOLS[6])
                                name = random.choice(pool['trash']) if pool['trash'] else 'skeleton'
                                e = Enemy(name, room.pixel_center_x + random.randint(-40, 40),
                                          room.pixel_center_y + random.randint(-40, 40),
                                          self.floor_num)
                                room.enemies.append(e)
                                self._add_notification("Wrong order! Enemy spawned!", (255, 100, 100))
                            elif penalty == 'dart':
                                self.player.take_damage(8)
                                self._add_notification("Wrong! Dart trap fires!", (255, 100, 100))
                                self.damage_numbers.append(
                                    DamageNumber(self.player.x, self.player.y - 20, "8", (255, 100, 100)))
                            elif penalty == 'heal_all':
                                # Heal remaining enemies
                                for e in room.enemies:
                                    if e.alive:
                                        e.hp = min(e.max_hp, e.hp + e.max_hp // 3)
                                self._add_notification("Wrong kill order! Enemies healed!", (255, 100, 100))
                            else:
                                self._add_notification("Wrong! Sequence reset.", (255, 200, 100))
                            # Reset the puzzle
                            ps['activated'] = [False] * n_elements
                            ps['current_step'] = 0
                        break

                # Check if all steps completed
                if all(ps['activated']):
                    self._solve_puzzle(room)

            elif ps.get('safe_tiles') is not None:
                # Pathing puzzle: damage on unsafe tiles
                if (tx, ty) not in ps['safe_tiles']:
                    # Check if player is inside this room
                    if room.contains_point(tx, ty):
                        self.player.take_damage(10)
                        self.damage_numbers.append(
                            DamageNumber(self.player.x, self.player.y - 20, "10", (255, 100, 100)))
                # Solved when player reaches room centre
                if tx == room.center_x and ty == room.center_y:
                    self._solve_puzzle(room)

            else:
                # Simple weight/pressure plate puzzle (all plates at once or in sequence)
                for i, (px, py) in enumerate(ps['plates']):
                    if tx == px and ty == py:
                        ps['activated'][i] = True
                    # Weight plates deactivate when you step off
                    # (only for weight type puzzles)
                    if template_name == 'weight_plates':
                        if tx != px or ty != py:
                            ps['activated'][i] = False

                if all(ps['activated']):
                    self._solve_puzzle(room)

            # Also check trap rooms with switch-based puzzles
            if ps.get('trap_active') and all(ps['activated']):
                ps['trap_active'] = False
                ps['solved'] = True
                room.cleared = True
                room.traps = []  # disable all traps
                self._add_notification("Switches hit! Traps disabled!", (100, 255, 100))

    def _solve_puzzle(self, room):
        """Mark puzzle as solved and spawn purpose-based rewards."""
        room.puzzle_state['solved'] = True
        room.cleared = True
        purpose = getattr(room, 'room_purpose', 'treasure_chest')
        is_exit = getattr(room, 'is_exit_room', False)

        if is_exit:
            # Exit room puzzle: no extra loot, just unlock stairs
            self._add_notification("Puzzle solved! The path forward is open!", (100, 255, 200))
            self.renderer.add_shake(5, 0.3)
            return

        if purpose == 'treasure_chest':
            loot = generate_loot(self.floor_num, 'treasure')
            for item in loot:
                item.x = room.pixel_center_x + random.randint(-15, 15)
                item.y = room.pixel_center_y + random.randint(-15, 15)
                room.items.append(item)
            self._add_notification("Puzzle solved! Treasure revealed!", (100, 255, 100))
        elif purpose == 'rare_item':
            from game.combat import _make_item
            rarity = random.choice(['rare', 'epic'])
            item = _make_item(rarity, equip_weight=0.8)
            item.x = room.pixel_center_x
            item.y = room.pixel_center_y
            room.items.append(item)
            self._add_notification(f"Puzzle solved! A {rarity} item appears!", (180, 100, 255))
        elif purpose == 'legendary_chance':
            from game.combat import _make_item
            rarity = 'legendary' if random.random() < 0.35 else 'epic'
            item = _make_item(rarity, equip_weight=0.9)
            item.x = room.pixel_center_x
            item.y = room.pixel_center_y
            room.items.append(item)
            color = (255, 200, 50) if rarity == 'legendary' else (200, 50, 255)
            self._add_notification(f"Puzzle solved! {rarity.title()} reward!", color)
        elif purpose == 'bonus_gold':
            bonus = random.randint(30, 80) + self.floor_num * 15
            self.player.gold += bonus
            self._add_notification(f"Puzzle solved! +{bonus} gold!", (255, 215, 0))
        elif purpose == 'full_heal':
            self.player.hp = self.player.max_hp
            self.player.mp = self.player.max_mp
            self._add_notification("Puzzle solved! Fully restored!", (100, 255, 150))
        elif purpose == 'disable_next_traps':
            # Disable traps in all nearby trap rooms
            for other_room in self.floor.rooms:
                if other_room.room_type == 'trap' and not other_room.cleared:
                    other_room.traps = []
                    other_room.cleared = True
            self._add_notification("Puzzle solved! All traps disabled!", (100, 255, 200))
        else:
            loot = generate_loot(self.floor_num, 'treasure')
            for item in loot:
                item.x = room.pixel_center_x + random.randint(-15, 15)
                item.y = room.pixel_center_y + random.randint(-15, 15)
                room.items.append(item)
            self._add_notification("Puzzle solved! Treasure revealed!", (100, 255, 100))

        self.renderer.add_shake(3, 0.2)

    def _give_room_purpose_reward(self, room, purpose):
        """Give a trap room its purpose-based reward on clear."""
        if purpose == 'treasure_chest':
            loot = generate_loot(self.floor_num, 'treasure')
            for item in loot:
                item.x = room.pixel_center_x + random.randint(-15, 15)
                item.y = room.pixel_center_y + random.randint(-15, 15)
                room.items.append(item)
        elif purpose == 'rare_item':
            from game.combat import _make_item
            rarity = random.choice(['rare', 'epic'])
            item = _make_item(rarity, equip_weight=0.8)
            item.x = room.pixel_center_x
            item.y = room.pixel_center_y
            room.items.append(item)
        elif purpose == 'bonus_gold':
            bonus = random.randint(20, 50) + self.floor_num * 10
            self.player.gold += bonus
            self._add_notification(f"Traps cleared! +{bonus} gold!", (255, 215, 0))
        elif purpose == 'legendary_chance':
            from game.combat import _make_item
            rarity = 'legendary' if random.random() < 0.25 else 'epic'
            item = _make_item(rarity, equip_weight=0.9)
            item.x = room.pixel_center_x
            item.y = room.pixel_center_y
            room.items.append(item)
        elif purpose == 'shortcut':
            # Reveal all rooms on the map
            for r in self.floor.rooms:
                r.discovered = True
            self._add_notification("Traps cleared! Map revealed!", (150, 200, 255))

    def _discover_rooms(self):
        """Mark rooms as discovered when player enters."""
        room_idx, room = self.floor.get_room_at(
            int(self.player.x // TILE_SIZE), int(self.player.y // TILE_SIZE))
        if room and not room.discovered:
            room.discovered = True
            is_exit = getattr(room, 'is_exit_room', False)
            purpose = getattr(room, 'room_purpose', None)

            if room.room_type == 'boss':
                self._add_notification("BOSS ROOM!", (255, 50, 50))
                self.renderer.add_shake(5, 0.5)
            elif room.room_type == 'treasure':
                self._add_notification("Treasure room!", (255, 200, 50))
            elif room.room_type == 'merchant':
                count = len(room.merchant_items)
                self._add_notification(f"Merchant! {count} items for sale - press E to buy", (255, 215, 0))
            elif room.room_type == 'trap':
                template_name = getattr(room, 'trap_template', None)
                if is_exit:
                    self._add_notification("TRAP GAUNTLET - Navigate to the stairs!", (255, 100, 50))
                    self.renderer.add_shake(4, 0.3)
                elif template_name:
                    from config import TRAP_TEMPLATES
                    desc = TRAP_TEMPLATES.get(template_name, {}).get('description', 'Trap room!')
                    purpose_hint = ""
                    if purpose == 'treasure_chest':
                        purpose_hint = " Treasure awaits beyond!"
                    elif purpose == 'rare_item':
                        purpose_hint = " A rare prize lies ahead!"
                    elif purpose == 'shortcut':
                        purpose_hint = " A shortcut awaits!"
                    self._add_notification(f"Trap: {desc}{purpose_hint}", (255, 150, 50))
                else:
                    self._add_notification("Watch your step... trap room!", (255, 150, 50))
            elif room.room_type == 'elite':
                if is_exit:
                    self._add_notification("ELITE FORMATION - Clear them to advance!", (255, 150, 50))
                    self.renderer.add_shake(4, 0.3)
                else:
                    self._add_notification("Elite enemy ahead!", (255, 200, 100))
            elif room.room_type == 'puzzle':
                if is_exit:
                    self._add_notification("PUZZLE GATE - Solve it to unlock the exit!", (150, 150, 255))
                    self.renderer.add_shake(4, 0.3)
                elif room.puzzle_state:
                    tmpl = room.puzzle_state.get('puzzle_template', '')
                    from config import PUZZLE_TEMPLATES
                    desc = PUZZLE_TEMPLATES.get(tmpl, {}).get('description', 'Puzzle room!')
                    purpose_hint = ""
                    if purpose == 'treasure_chest':
                        purpose_hint = " Treasure awaits!"
                    elif purpose == 'rare_item':
                        purpose_hint = " A rare prize is hidden here!"
                    elif purpose == 'full_heal':
                        purpose_hint = " A healing spring awaits!"
                    self._add_notification(f"Puzzle: {desc}{purpose_hint}", (200, 200, 255))
                else:
                    self._add_notification("Puzzle room!", (200, 200, 255))
            elif room.room_type == 'survival':
                if is_exit:
                    self._add_notification("SURVIVAL CHALLENGE - Last through all waves to escape!", (255, 120, 80))
                    self.renderer.add_shake(4, 0.3)
                else:
                    self._add_notification("Survival challenge! Defeat all waves!", (255, 150, 100))

    def _check_room_clears(self):
        """Check if rooms have been cleared and reward the player."""
        import random
        for i, room in enumerate(self.floor.rooms):
            if self.floor.check_room_cleared(i):
                # Only drop bonus room-clear loot for special rooms, not regular mob rooms
                # (enemies already drop their own loot via generate_enemy_loot)
                is_exit = getattr(room, 'is_exit_room', False)
                purpose = getattr(room, 'room_purpose', None)

                if room.room_type in ('elite', 'hidden'):
                    # Elite/hidden rooms get a small bonus drop on clear
                    loot = generate_loot(self.floor_num, room.room_type)
                    for item in loot:
                        item.x = room.pixel_center_x + random.randint(-30, 30)
                        item.y = room.pixel_center_y + random.randint(-30, 30)
                        room.items.append(item)
                elif room.room_type == 'trap' and not is_exit and purpose:
                    # Trap rooms with purpose: spawn reward on clear
                    self._give_room_purpose_reward(room, purpose)

                # Exit rooms get a special clear message
                if is_exit:
                    self._add_notification("Exit room cleared! Use stairs (F) to descend!", (100, 255, 200))
                else:
                    self._add_notification("Room cleared!", (100, 255, 100))

                self.ai_director.record_event('room_clear', {
                    'type': room.room_type, 'floor': self.floor_num
                }, self.game_time)

    def _auto_equip(self):
        """Auto-equip best items from inventory."""
        for item in list(self.player.inventory):
            if item.item_type in ('weapon', 'armor', 'accessory'):
                current = self.player.equipment.get(item.item_type)
                if current is None:
                    self.player.equip_item(item)
                    self._add_notification(f"Equipped {item.name}", (100, 200, 255))
                else:
                    # Compare total stats
                    new_total = sum(item.stats.values())
                    old_total = sum(current.stats.values())
                    if new_total > old_total:
                        self.player.equip_item(item)
                        self._add_notification(f"Upgraded to {item.name}!", (100, 255, 200))

    def _add_notification(self, message, color=(255, 255, 100)):
        self.notifications.append((message, color, 3.0))  # 3 second duration

    def _process_attack_results(self, results):
        """Process results from player basic attack."""
        for result in results:
            if isinstance(result, Projectile):
                self.projectiles.append(result)
            elif isinstance(result, tuple) and len(result) == 3:
                enemy, dmg, crit = result
                color = (255, 255, 100) if crit else (255, 255, 255)
                self.damage_numbers.append(DamageNumber(enemy.x, enemy.y - 20, dmg, color))
                self.renderer.add_particles(enemy.x, enemy.y, enemy.color, 5 if not crit else 10)
                if crit:
                    self._add_notification("Critical Hit!", (255, 200, 50))
                if not enemy.alive:
                    self._on_enemy_killed(enemy)

    def _process_ability_results(self, results):
        """Process results from ability use."""
        for result in results:
            if isinstance(result, Projectile):
                self.projectiles.append(result)
            elif isinstance(result, Enemy):
                # Crowd control applied (from fallback handler)
                self.damage_numbers.append(
                    DamageNumber(result.x, result.y - 20, "CC!", (150, 150, 255)))
            elif isinstance(result, tuple):
                if len(result) >= 2 and isinstance(result[0], Enemy):
                    # (enemy, damage, crit) — direct hit
                    enemy, dmg, crit = result[0], result[1], result[2] if len(result) > 2 else False
                    color = (255, 255, 100) if crit else (255, 200, 100)
                    self.damage_numbers.append(DamageNumber(enemy.x, enemy.y - 20, dmg, color))
                    self.renderer.add_particles(enemy.x, enemy.y, enemy.color, 5 if not crit else 10)
                    if crit:
                        self._add_notification("Critical Hit!", (255, 200, 50))
                    if not enemy.alive:
                        self._on_enemy_killed(enemy)
                elif len(result) >= 2 and isinstance(result[0], str):
                    rtype = result[0]

                    if rtype == 'heal':
                        self.damage_numbers.append(
                            DamageNumber(self.player.x, self.player.y - 30, result[1], (100, 255, 100)))
                        self._add_notification(f"Healed for {result[1]}!", (100, 255, 100))

                    elif rtype == 'status_self':
                        effect_name = result[1]
                        duration = result[2] if len(result) > 2 else 3.0
                        if effect_name == 'shield_wall':
                            self._add_notification("Shield Wall!", (100, 150, 255))
                        elif effect_name == 'war_cry':
                            self._add_notification("War Cry! +30% STR!", (255, 200, 50))
                            self.renderer.add_shake(3, 0.2)
                        elif effect_name == 'stealth':
                            self._add_notification("Vanished into smoke!", (150, 150, 200))
                        elif effect_name == 'purify':
                            self._add_notification("Purified!", (255, 255, 200))
                            self.renderer.add_particles(self.player.x, self.player.y, (255, 255, 150), 12)
                        else:
                            self._add_notification(f"{effect_name} active!", (200, 200, 255))

                    elif rtype == 'aoe_damage':
                        # ('aoe_damage', x, y, radius, damage, effect_name, effect_duration)
                        ax, ay = result[1], result[2]
                        aradius = result[3]
                        self.renderer.add_particles(ax, ay, (255, 150, 50), 15)

                    elif rtype == 'leap':
                        tx, ty = result[1], result[2]
                        self.renderer.add_particles(tx, ty, self.player.color, 12)
                        self.renderer.add_shake(4, 0.15)
                        self._add_notification("Leap!", (200, 200, 100))

                    elif rtype == 'chain_lightning':
                        # ('chain_lightning', target_enemy, damage, chains_left)
                        target, chain_dmg, chains = result[1], result[2], result[3]
                        nearby = self.floor.get_nearby_enemies(target.x, target.y, 200)
                        chain_targets = [e for e in nearby if e.alive and e != target]
                        for i, ct in enumerate(chain_targets[:chains]):
                            reduced = int(chain_dmg * (0.7 ** (i + 1)))
                            ct.take_damage(reduced)
                            self.damage_numbers.append(
                                DamageNumber(ct.x, ct.y - 20, reduced, (100, 200, 255)))
                            self.renderer.add_particles(ct.x, ct.y, (100, 200, 255), 6)
                            if hasattr(ct, 'apply_status_effect'):
                                ct.apply_status_effect(StatusEffect('stun', 0.2))
                            if not ct.alive:
                                self._on_enemy_killed(ct)

                    elif rtype == 'smoke_bomb':
                        sx, sy, sradius, sdur = result[1], result[2], result[3], result[4]
                        self.zone_effects.append({
                            'type': 'smoke', 'x': sx, 'y': sy,
                            'radius': sradius, 'duration': sdur,
                            'color': (100, 100, 100, 120),
                        })
                        self.renderer.add_particles(sx, sy, (150, 150, 150), 20)

                    elif rtype == 'divine_shield':
                        dx, dy, dradius, ddur = result[1], result[2], result[3], result[4]
                        self.zone_effects.append({
                            'type': 'divine_shield', 'x': dx, 'y': dy,
                            'radius': dradius, 'duration': ddur,
                            'heal_tick': 0.0, 'heal_rate': 1.0, 'heal_amount': 5,
                            'color': (200, 200, 100, 80),
                        })
                        self._add_notification("Divine Shield placed!", (255, 255, 150))

                    elif rtype == 'meteor_target':
                        # ('meteor_target', x, y, radius, damage, delay)
                        mx, my, mradius, mdmg, mdelay = result[1], result[2], result[3], result[4], result[5]
                        self.zone_effects.append({
                            'type': 'meteor', 'x': mx, 'y': my,
                            'radius': mradius, 'damage': mdmg,
                            'delay': mdelay, 'duration': mdelay,
                            'detonated': False,
                            'color': (255, 100, 0, 60),
                        })
                        self._add_notification("Meteor incoming!", (255, 100, 0))

                    elif rtype == 'utility':
                        if result[1] == 'scan':
                            for room in self.floor.rooms:
                                room.discovered = True
                            self._add_notification("All rooms revealed!", (150, 150, 255))
                        elif result[1] == 'trap_sense':
                            self._add_notification("Traps highlighted!", (255, 200, 100))

    def _update_zone_effects(self, dt):
        """Update smoke bombs, divine shields, hazard zones, and meteors."""
        active = []
        for zone in self.zone_effects:
            zone['duration'] -= dt
            if zone['duration'] <= 0 and zone['type'] != 'meteor':
                continue  # expired

            ztype = zone['type']

            if ztype == 'hazard':
                # Damage player if inside
                pdist = math.sqrt((self.player.x - zone['x'])**2 + (self.player.y - zone['y'])**2)
                if pdist < zone['radius']:
                    zone['tick'] = zone.get('tick', 0) + dt
                    if zone['tick'] >= 1.0:
                        zone['tick'] -= 1.0
                        actual = self.player.take_damage(zone['damage'])
                        if actual > 0:
                            self.damage_numbers.append(
                                DamageNumber(self.player.x, self.player.y - 20, actual, (255, 80, 50)))
                if zone['duration'] > 0:
                    active.append(zone)

            elif ztype == 'divine_shield':
                # Heal player if inside
                pdist = math.sqrt((self.player.x - zone['x'])**2 + (self.player.y - zone['y'])**2)
                if pdist < zone['radius']:
                    zone['heal_tick'] = zone.get('heal_tick', 0) + dt
                    if zone['heal_tick'] >= zone.get('heal_rate', 1.0):
                        zone['heal_tick'] -= zone.get('heal_rate', 1.0)
                        heal = zone.get('heal_amount', 5)
                        self.player.hp = min(self.player.max_hp, self.player.hp + heal)
                        self.damage_numbers.append(
                            DamageNumber(self.player.x, self.player.y - 30, heal, (100, 255, 100)))
                if zone['duration'] > 0:
                    active.append(zone)

            elif ztype == 'smoke':
                if zone['duration'] > 0:
                    active.append(zone)

            elif ztype == 'meteor':
                if not zone.get('detonated', False):
                    zone['delay'] -= dt
                    if zone['delay'] <= 0:
                        # Detonate
                        zone['detonated'] = True
                        mx, my = zone['x'], zone['y']
                        mradius = zone['radius']
                        mdmg = zone['damage']
                        self.renderer.add_shake(8, 0.4)
                        self.renderer.add_particles(mx, my, (255, 120, 0), 25)
                        # Hit all enemies in radius
                        for enemy in self.floor.get_nearby_enemies(mx, my, mradius):
                            if enemy.alive:
                                edist = math.sqrt((enemy.x - mx)**2 + (enemy.y - my)**2)
                                if edist < mradius:
                                    enemy.take_damage(mdmg)
                                    self.damage_numbers.append(
                                        DamageNumber(enemy.x, enemy.y - 20, mdmg, (255, 200, 50)))
                                    # Apply burn
                                    if hasattr(enemy, 'apply_status_effect'):
                                        try:
                                            from game.combat import StatusEffect as CSE
                                            enemy.apply_status_effect(CSE('burn', 4.0))
                                        except Exception:
                                            pass
                                    if not enemy.alive:
                                        self._on_enemy_killed(enemy)
                    else:
                        active.append(zone)
                # detonated meteors are removed

        self.zone_effects = active

    def _update_survival_rooms(self, dt):
        """Handle survival room wave spawning."""
        room_idx, room = self.floor.get_room_at(
            int(self.player.x // TILE_SIZE), int(self.player.y // TILE_SIZE))
        if room is None or room.room_type != 'survival':
            return

        if room.cleared:
            return

        if room_idx not in self.survival_rooms:
            self.survival_rooms[room_idx] = {
                'wave': 0, 'max_waves': 3, 'timer': 3.0,
                'spawned': False, 'enemies_total': 0,
            }

        state = self.survival_rooms[room_idx]
        if state['wave'] >= state['max_waves']:
            # All waves done, check if cleared
            alive = [e for e in room.enemies if e.alive]
            if len(alive) == 0 and state['enemies_total'] > 0:
                room.cleared = True
                self._add_notification("Survival challenge complete!", (100, 255, 100))
                loot = generate_loot(self.floor_num, 'survival')
                for item in loot:
                    item.x = room.pixel_center_x + random.randint(-30, 30)
                    item.y = room.pixel_center_y + random.randint(-30, 30)
                    room.items.append(item)
            return

        state['timer'] -= dt
        if state['timer'] <= 0:
            # Spawn a wave
            state['wave'] += 1
            wave_size = 3 + state['wave'] + self.floor_num // 2
            from config import FLOOR_ENEMY_POOLS
            pool = FLOOR_ENEMY_POOLS.get(self.floor_num, FLOOR_ENEMY_POOLS[6])
            trash = pool['trash'] if pool['trash'] else ['goblin', 'skeleton']
            diff = self.ai_director.get_difficulty_modifier()
            for _ in range(wave_size):
                name = random.choice(trash)
                ex = random.randint(room.x + 1, room.x + room.w - 2) * TILE_SIZE + TILE_SIZE // 2
                ey = random.randint(room.y + 1, room.y + room.h - 2) * TILE_SIZE + TILE_SIZE // 2
                e = Enemy(name, ex, ey, self.floor_num, diff)
                room.enemies.append(e)
                state['enemies_total'] += 1
            state['timer'] = 5.0  # 5 seconds between waves
            self._add_notification(f"Wave {state['wave']}/{state['max_waves']}!", (255, 200, 100))

    def _update_totems(self, dt):
        """Update boss heal totems."""
        alive_totems = []
        for totem in self.totems:
            if not totem.alive:
                continue
            totem.update(dt)
            # Heal nearby enemies
            if hasattr(totem, 'heal_timer'):
                totem.heal_timer = getattr(totem, 'heal_timer', 0) - dt
                if totem.heal_timer <= 0:
                    totem.heal_timer = 2.0
                    heal_amt = getattr(totem, 'heal_amount', 10)
                    for enemy in self.floor.get_nearby_enemies(totem.x, totem.y, 200):
                        if enemy.alive and enemy is not totem:
                            enemy.hp = min(enemy.max_hp, enemy.hp + heal_amt)
                            self.damage_numbers.append(
                                DamageNumber(enemy.x, enemy.y - 20, heal_amt, (100, 255, 100)))
            alive_totems.append(totem)
        self.totems = alive_totems

    def _render(self):
        if self.state == 'menu':
            self.renderer.render_menu(self.menu_selection)
        elif self.state == 'class_select':
            self.renderer.render_class_select(self.class_selection)
        elif self.state == 'floor_transition':
            exit_type = FLOOR_EXIT_TYPE.get(self.floor_num, 'boss')
            self.renderer.render_floor_transition(self.floor_num, exit_type=exit_type)
        elif self.state in ('playing', 'paused'):
            ai_stats = self.ai_director.get_stats()
            self.renderer.render_game(self.player, self.floor, self.projectiles,
                                     self.damage_numbers, self.game_time, ai_stats,
                                     self.zone_effects)
            # AI debug overlay
            if self.show_ai_debug:
                self.renderer.render_ai_debug(
                    ai_stats,
                    self.enemy_brain.get_training_stats(),
                    self.player,
                    self.floor,
                    self.zone_effects,
                    self.survival_rooms,
                    len(self.projectiles),
                )

            # Draw notifications
            for i, (msg, color, timer) in enumerate(self.notifications):
                self.renderer.render_notification(msg, color)
                # Only show the most recent notification
                break

            if self.state == 'paused':
                # Pause overlay
                overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 180))
                self.screen.blit(overlay, (0, 0))
                cx = SCREEN_W // 2
                cy = SCREEN_H // 2

                # Title
                font_lg = pygame.font.Font(None, 48)
                font_sm = pygame.font.Font(None, 24)
                title = font_lg.render("PAUSED", True, (220, 195, 55))
                self.screen.blit(title, (cx - title.get_width() // 2, cy - 60))

                # Separator
                pygame.draw.line(self.screen, (60, 60, 80),
                                 (cx - 100, cy - 25), (cx + 100, cy - 25), 1)

                # Controls reminder
                controls = [
                    ("[ESC]  Resume game",     (180, 180, 200)),
                    ("[I]  Inventory",          (180, 180, 200)),
                    ("[1-5]  Use abilities",    (180, 180, 200)),
                    ("[P]  AI Debug overlay",   (150, 150, 170)),
                ]
                for i, (text, color) in enumerate(controls):
                    ct = font_sm.render(text, True, color)
                    self.screen.blit(ct, (cx - ct.get_width() // 2, cy - 5 + i * 28))

                # Floor info
                exit_type = FLOOR_EXIT_TYPE.get(self.floor_num, 'boss')
                exit_labels = {
                    'boss': 'Boss Fight', 'survival': 'Survival Waves',
                    'elite_formation': 'Elite Formation', 'trap_gauntlet': 'Trap Gauntlet',
                    'puzzle_gate': 'Puzzle Gate',
                }
                floor_info = font_sm.render(
                    f"Floor {self.floor_num}  |  Exit: {exit_labels.get(exit_type, 'Unknown')}",
                    True, (120, 120, 150))
                self.screen.blit(floor_info, (cx - floor_info.get_width() // 2, cy + 120))
        elif self.state == 'inventory':
            # Render game behind inventory
            ai_stats = self.ai_director.get_stats()
            self.renderer.render_game(self.player, self.floor, self.projectiles,
                                     self.damage_numbers, self.game_time, ai_stats,
                                     self.zone_effects)
            self.renderer.render_inventory(self.player)
        elif self.state == 'game_over':
            self.renderer.render_game_over(self.player, self.floor_num, self.game_time)
