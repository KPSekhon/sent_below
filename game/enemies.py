import pygame
import math
import random
from config import ENEMY_DATA, TILE_SIZE, FLOOR_SCALING, BOSS_SCALING
from game.combat import Projectile, calculate_damage


class Enemy:
    def __init__(self, name, x, y, floor_num=1, difficulty_mod=1.0):
        data = ENEMY_DATA[name]
        self.name = name
        self.x = float(x)
        self.y = float(y)
        floor_num = max(1, min(floor_num, 6))
        self.floor_num = floor_num
        self.tier = data['tier']

        # --- Floor-based scaling from lookup tables ---
        # Early (1-2): enemies die in 2-4 hits, hit softly, move slowly
        # Mid (3-4):   enemies take 4-7 hits, real threat in combos
        # Late (5-6):  enemies hit hard, move smart, punish mistakes
        if self.tier == 'boss':
            sc = BOSS_SCALING.get(floor_num, BOSS_SCALING[6])
            self.hp = int(data['hp'] * sc['hp'] * difficulty_mod)
            self.max_hp = self.hp
            self.strength = int(data['str'] * sc['str'] * difficulty_mod)
            self.defense = int(data['defense'] * difficulty_mod)
            self.speed = data['spd'] * sc['spd']
            self.attack_speed = 3.0 * sc['atk_cd']
            self.aggro_range = 350  # bosses always see you in their room
        else:
            sc = FLOOR_SCALING.get(floor_num, FLOOR_SCALING[6])
            self.hp = int(data['hp'] * sc['hp'] * difficulty_mod)
            self.max_hp = self.hp
            self.strength = int(data['str'] * sc['str'] * difficulty_mod)
            self.defense = int(data['defense'] * sc['def'] * difficulty_mod)
            self.speed = data['spd'] * sc['spd']
            if self.tier == 'trash':
                self.attack_speed = 1.5 * sc['atk_cd']
                self.aggro_range = int(120 * sc['aggro'])
            else:  # elite
                self.attack_speed = 2.0 * sc['atk_cd']
                self.aggro_range = int(200 * sc['aggro'])

        self.xp_reward = int(data['xp'] * (0.8 + floor_num * 0.1) * difficulty_mod)
        self.color = tuple(data['color'])
        self.behavior = data['behavior']
        self.size = data.get('size', 24)
        self.alive = True
        self.stunned = 0.0
        self.silenced = 0.0
        self.frozen = 0.0
        self.attack_cooldown = 0.0
        self.state = 'idle'
        self.state_timer = 0.0
        self.path_target = None

        # Patrol / idle wander
        self.patrol_timer = random.uniform(0, 2.0)  # stagger initial patrols
        self.patrol_target = None

        # --- New systems ---
        self.status_effects = []  # list of {'type', 'damage', 'duration', 'tick_timer'}
        self.behavior_timer = 0.0
        self.special_data = {}

        # Boss-specific
        self.phase = 1
        self.special_cooldown = 0.0
        self.special_timer = 0.0
        self.gimmick = None
        self.summons = []
        self.hazard_zones = []
        self.summon_count = 0

        # ML tracking
        self.actions_taken = []
        self.total_damage_dealt = 0
        self.time_alive = 0.0

        # Animation state for renderer
        self.anim_timer = 0.0
        self.bob_offset = random.uniform(0, math.pi * 2)  # stagger animations
        self.facing_dir = (0, 1)  # normalized facing direction
        self.move_amount = 0.0  # how much this enemy moved this frame (for walk anim)
        self.is_attacking = False
        self.attack_anim_timer = 0.0
        self.hurt_flash = 0.0  # flash white when hit

        # Initialize behavior-specific data
        self._init_behavior()
        if self.tier == 'boss':
            self._init_boss_gimmick()

    # ------------------------------------------------------------------
    # Behavior-specific initialization
    # ------------------------------------------------------------------
    def _init_behavior(self):
        """Set up special_data based on enemy type."""
        if self.name == 'goblin':
            self.behavior = 'swarm'
            self.special_data = {'swarm_bonus': False, 'flank_angle': random.uniform(0, math.pi * 2)}

        elif self.name == 'skeleton':
            self.behavior = 'aggressive'
            self.special_data = {'blocking': False, 'block_timer': 0.0, 'block_cooldown': 0.0}

        elif self.name == 'slime':
            self.behavior = 'slow_chase'
            self.can_split = True
            self.special_data = {'poison_trail': [], 'trail_timer': 0.0}

        elif self.name == 'wolf':
            self.behavior = 'pack'
            self.special_data = {
                'pack_bonus': 0.0, 'circling': True, 'circle_angle': random.uniform(0, math.pi * 2),
                'lunge_cooldown': 0.0, 'lunging': False, 'lunge_target': None,
            }

        elif self.name == 'bug':
            self.behavior = 'erratic'
            self.special_data = {'dodge_chance': 0.5, 'direction_timer': 0.0, 'move_dx': 0.0, 'move_dy': 0.0}

        elif self.name == 'undead_soldier':
            self.behavior = 'aggressive'
            self.special_data = {'shield_hp': 3, 'shield_active': True}

        elif self.name == 'assassin':
            self.behavior = 'stealth'
            self.special_data = {
                'invisible': False, 'invis_timer': 0.0, 'invis_cooldown': 5.0,
                'backstab_ready': False,
            }
            self.aggro_range = 350

        elif self.name == 'shaman':
            self.behavior = 'support'
            self.special_data = {'heal_cooldown': 4.0, 'buff_cooldown': 8.0}
            self.aggro_range = 350

        elif self.name == 'elite_knight':
            self.behavior = 'tank'
            self.special_data = {
                'charge_cooldown': 0.0, 'charging': False, 'charge_target': None,
                'facing_dx': 0.0, 'facing_dy': 1.0,
            }
            self.aggro_range = 350

        elif self.name == 'ogre':
            self.behavior = 'brute'
            self.special_data = {
                'ground_pound_cooldown': 6.0, 'throw_cooldown': 0.0,
            }
            self.aggro_range = 300

        elif self.name == 'cursed_priest':
            self.behavior = 'debuffer'
            self.special_data = {
                'curse_cooldown': 0.0, 'silence_cooldown': 0.0, 'heal_tick': 0.0,
            }
            self.aggro_range = 350

        elif self.name in ('mage', 'dark_mage'):
            self.behavior = 'ranged_teleport'
            self.special_data = {
                'teleport_cooldown': 4.0, 'freeze_cooldown': 0.0, 'cast_cooldown': 0.0,
            }
            self.aggro_range = 400

    # ------------------------------------------------------------------
    # Boss gimmick init
    # ------------------------------------------------------------------
    def _init_boss_gimmick(self):
        gimmicks = {
            'giant_beast': 'enrage',
            'fallen_hero': 'counter',
            'corrupted_king': 'summons',
            'dungeon_guardian': 'hazard',
            'floor_admin': 'phases',
            'dragon': 'heal_totem',
        }
        self.gimmick = gimmicks.get(self.name, 'enrage')
        # Boss attack_speed and aggro_range are already set in __init__ with
        # floor-based scaling — don't override them here.

        if self.gimmick == 'counter':
            self.special_data['damage_reduction'] = 0.8
            self.special_data['windup_timer'] = 0.0
            self.special_data['recovery_timer'] = 0.0
            self.special_data['swing_cooldown'] = 6.0
        elif self.gimmick == 'summons':
            self.special_data['summon_cooldown'] = 8.0
            self.special_data['wave_number'] = 0
        elif self.gimmick == 'enrage':
            self.special_data['enraged'] = False
        elif self.gimmick == 'hazard':
            self.special_data['hazard_timer'] = 10.0
        elif self.gimmick == 'phases':
            self.special_data['transition_invuln'] = 0.0
            self.special_data['heal_amount'] = 0
        elif self.gimmick == 'heal_totem':
            self.special_data['totem_cooldown'] = 15.0
            self.special_data['fire_breath_cooldown'] = 0.0

    # ------------------------------------------------------------------
    # Collision rect
    # ------------------------------------------------------------------
    def get_rect(self):
        return pygame.Rect(
            self.x - self.size // 2, self.y - self.size // 2,
            self.size, self.size
        )

    # ------------------------------------------------------------------
    # Damage handling
    # ------------------------------------------------------------------
    def take_damage(self, amount, from_direction=None):
        """Apply damage with behavior-specific defenses.

        *from_direction* is an (x, y) unit vector from attacker toward this enemy,
        used for directional blocking (elite_knight, undead_soldier shield).
        """
        # Bug dodge
        if self.name == 'bug' and random.random() < self.special_data.get('dodge_chance', 0.5):
            return 0  # dodged

        # Assassin invisibility -- attacks reveal
        if self.name == 'assassin' and self.special_data.get('invisible'):
            self.special_data['invisible'] = False
            self.special_data['backstab_ready'] = False

        # Undead soldier shield
        if self.name == 'undead_soldier' and self.special_data.get('shield_active'):
            self.special_data['shield_hp'] -= 1
            if self.special_data['shield_hp'] <= 0:
                self.special_data['shield_active'] = False
            return 0  # shield absorbed the hit

        # Skeleton blocking
        if self.name == 'skeleton' and self.special_data.get('blocking'):
            amount = amount // 2

        # Elite knight frontal block
        if self.name == 'elite_knight' and from_direction is not None:
            fd = self.special_data
            dot = fd.get('facing_dx', 0) * from_direction[0] + fd.get('facing_dy', 0) * from_direction[1]
            if dot > 0.3:  # attack is coming from the front
                amount = amount // 2

        # Fallen hero counter gimmick -- massive reduction unless recovering
        if self.gimmick == 'counter':
            if self.special_data.get('recovery_timer', 0) > 0:
                pass  # full damage during recovery
            else:
                amount = int(amount * (1 - self.special_data.get('damage_reduction', 0.8)))

        # Floor admin phase transition invulnerability
        if self.gimmick == 'phases' and self.special_data.get('transition_invuln', 0) > 0:
            return 0

        self.hp -= amount
        self.hurt_flash = 0.15
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
        return amount

    # ------------------------------------------------------------------
    # Status effect processing
    # ------------------------------------------------------------------
    def _process_status_effects(self, dt):
        """Tick all active status effects. Returns total DoT damage taken this frame."""
        dot_total = 0
        remaining = []
        for effect in self.status_effects:
            effect['duration'] -= dt
            if effect['duration'] <= 0:
                continue
            if effect['type'] == 'dot':
                effect['tick_timer'] -= dt
                if effect['tick_timer'] <= 0:
                    effect['tick_timer'] = 1.0
                    self.hp -= effect['damage']
                    dot_total += effect['damage']
                    if self.hp <= 0:
                        self.hp = 0
                        self.alive = False
            elif effect['type'] == 'stun':
                self.stunned = max(self.stunned, effect['duration'])
            elif effect['type'] == 'freeze':
                self.frozen = max(self.frozen, effect['duration'])
            elif effect['type'] == 'silence':
                self.silenced = max(self.silenced, effect['duration'])
            remaining.append(effect)
        self.status_effects = remaining
        return dot_total

    # ------------------------------------------------------------------
    # Main update
    # ------------------------------------------------------------------
    def update(self, player, dungeon, dt, ai_brain=None, nearby_enemies=None):
        """Update enemy behavior. Returns list of action tuples / Projectile objects.

        *nearby_enemies* is an optional list of other alive enemies in the room,
        used for pack/swarm/support behaviours.
        """
        if not self.alive:
            return []

        self.time_alive += dt
        self.anim_timer += dt
        self.attack_anim_timer = max(0, self.attack_anim_timer - dt)
        self.hurt_flash = max(0, self.hurt_flash - dt)
        self.stunned = max(0, self.stunned - dt)
        self.silenced = max(0, self.silenced - dt)
        self.frozen = max(0, self.frozen - dt)
        self.attack_cooldown = max(0, self.attack_cooldown - dt)
        self.special_cooldown = max(0, self.special_cooldown - dt)
        self.behavior_timer = max(0, self.behavior_timer - dt)

        self._process_status_effects(dt)
        if not self.alive:
            return []

        if self.stunned > 0 or self.frozen > 0:
            return []

        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.sqrt(dx * dx + dy * dy)

        if nearby_enemies is None:
            nearby_enemies = []

        # Idle patrol: wander randomly when outside aggro range (non-boss only)
        if self.tier != 'boss' and dist > self.aggro_range:
            self.patrol_timer -= dt
            if self.patrol_timer <= 0:
                # Pick a new random nearby point to drift toward
                angle = random.uniform(0, math.pi * 2)
                wander_dist = random.uniform(30, 80)
                px = self.x + math.cos(angle) * wander_dist
                py = self.y + math.sin(angle) * wander_dist
                self.patrol_target = (px, py)
                self.patrol_timer = random.uniform(2.0, 3.0)
            if self.patrol_target is not None:
                self._move_toward(self.patrol_target[0], self.patrol_target[1],
                                  dungeon, dt, speed_mult=0.3)
                # Clear target if we're close enough
                pdx = self.patrol_target[0] - self.x
                pdy = self.patrol_target[1] - self.y
                if math.sqrt(pdx * pdx + pdy * pdy) < 5:
                    self.patrol_target = None
            return []

        # Dispatch to behaviour-specific update
        if self.tier == 'boss':
            results = self._update_boss(player, dungeon, dt, dist, dx, dy, nearby_enemies)
        else:
            results = self._update_mob(player, dungeon, dt, dist, dx, dy, nearby_enemies, ai_brain)

        return results

    # ------------------------------------------------------------------
    # Movement helpers
    # ------------------------------------------------------------------
    def _move_toward(self, tx, ty, dungeon, dt, speed_mult=1.0):
        dx = tx - self.x
        dy = ty - self.y
        d = math.sqrt(dx * dx + dy * dy)
        if d < 1:
            return
        # Hesitation: slow down when very close, don't glue onto player
        if d < 60:
            speed_mult *= 0.5
        elif d < 100:
            speed_mult *= 0.75
        ndx, ndy = dx / d, dy / d
        move_speed = self.speed * 80 * dt * speed_mult
        new_x = self.x + ndx * move_speed
        new_y = self.y + ndy * move_speed
        gx, gy = int(new_x // TILE_SIZE), int(new_y // TILE_SIZE)
        if dungeon.is_walkable(gx, gy):
            self.x = new_x
            self.y = new_y
            self.facing_dir = (ndx, ndy)
            self.move_amount = move_speed
            return ndx, ndy
        return None

    def _move_away(self, tx, ty, dungeon, dt, speed_mult=1.0):
        dx = self.x - tx
        dy = self.y - ty
        d = math.sqrt(dx * dx + dy * dy)
        if d < 1:
            dx, dy = random.uniform(-1, 1), random.uniform(-1, 1)
            d = math.sqrt(dx * dx + dy * dy) or 1
        ndx, ndy = dx / d, dy / d
        move_speed = self.speed * 80 * dt * speed_mult
        new_x = self.x + ndx * move_speed
        new_y = self.y + ndy * move_speed
        gx, gy = int(new_x // TILE_SIZE), int(new_y // TILE_SIZE)
        if dungeon.is_walkable(gx, gy):
            self.x = new_x
            self.y = new_y

    def _strafe(self, target_x, target_y, dungeon, dt, clockwise=True, speed_mult=1.0):
        dx = target_x - self.x
        dy = target_y - self.y
        d = math.sqrt(dx * dx + dy * dy)
        if d < 1:
            return
        ndx, ndy = dx / d, dy / d
        if clockwise:
            perp_x, perp_y = -ndy, ndx
        else:
            perp_x, perp_y = ndy, -ndx
        move_speed = self.speed * 60 * dt * speed_mult
        new_x = self.x + perp_x * move_speed
        new_y = self.y + perp_y * move_speed
        gx, gy = int(new_x // TILE_SIZE), int(new_y // TILE_SIZE)
        if dungeon.is_walkable(gx, gy):
            self.x = new_x
            self.y = new_y

    # ------------------------------------------------------------------
    # ML state vector (unchanged from original)
    # ------------------------------------------------------------------
    def _get_state_vector(self, player, dist):
        return [
            self.hp / max(self.max_hp, 1),
            player.hp / max(player.max_hp, 1),
            min(dist / 500, 1.0),
            1.0 if self.attack_cooldown <= 0 else 0.0,
            self.strength / 50.0,
            player.defense / 50.0,
            1.0 if self.behavior in ('aggressive', 'swarm', 'pack') else 0.0,
            1.0 if self.behavior in ('ranged_teleport', 'debuffer') else 0.0,
            1.0 if self.behavior == 'support' else 0.0,
            len(self.actions_taken) / 100.0,
        ]

    # ==================================================================
    # MOB UPDATE (trash + elite)
    # ==================================================================
    def _update_mob(self, player, dungeon, dt, dist, dx, dy, nearby_enemies, ai_brain):
        results = []
        norm = max(dist, 1)
        ndx, ndy = dx / norm, dy / norm

        # --- GOBLIN: swarm behaviour ---
        if self.behavior == 'swarm' and self.name == 'goblin':
            results += self._ai_goblin(player, dungeon, dt, dist, ndx, ndy, nearby_enemies)

        # --- SKELETON: aggressive with occasional block ---
        elif self.behavior == 'aggressive' and self.name == 'skeleton':
            results += self._ai_skeleton(player, dungeon, dt, dist, ndx, ndy)

        # --- SLIME: slow chase, poison trail, splits ---
        elif self.behavior == 'slow_chase':
            results += self._ai_slime(player, dungeon, dt, dist, ndx, ndy)

        # --- WOLF: pack tactics, circling, lunging ---
        elif self.behavior == 'pack':
            results += self._ai_wolf(player, dungeon, dt, dist, ndx, ndy, nearby_enemies)

        # --- BUG: erratic movement, dodge ---
        elif self.behavior == 'erratic':
            results += self._ai_bug(player, dungeon, dt, dist, ndx, ndy)

        # --- UNDEAD SOLDIER: aggressive with shield ---
        elif self.behavior == 'aggressive' and self.name == 'undead_soldier':
            results += self._ai_undead_soldier(player, dungeon, dt, dist, ndx, ndy)

        # --- ASSASSIN: stealth + backstab ---
        elif self.behavior == 'stealth':
            results += self._ai_assassin(player, dungeon, dt, dist, ndx, ndy)

        # --- SHAMAN: healer / buffer ---
        elif self.behavior == 'support':
            results += self._ai_shaman(player, dungeon, dt, dist, ndx, ndy, nearby_enemies)

        # --- ELITE KNIGHT: tank with charge ---
        elif self.behavior == 'tank':
            results += self._ai_elite_knight(player, dungeon, dt, dist, ndx, ndy)

        # --- OGRE: brute with ground pound ---
        elif self.behavior == 'brute':
            results += self._ai_ogre(player, dungeon, dt, dist, ndx, ndy)

        # --- CURSED PRIEST: debuffer ---
        elif self.behavior == 'debuffer':
            results += self._ai_cursed_priest(player, dungeon, dt, dist, ndx, ndy)

        # --- DARK MAGE: ranged teleport ---
        elif self.behavior == 'ranged_teleport':
            results += self._ai_dark_mage(player, dungeon, dt, dist, ndx, ndy)

        # --- Fallback: generic aggressive ---
        else:
            if ai_brain:
                sv = self._get_state_vector(player, dist)
                action = ai_brain.decide_action(sv, self.behavior)
            else:
                action = 'chase' if dist > 50 else 'attack'
            results += self._execute_generic(action, player, dungeon, dt, dist, ndx, ndy)

        return results

    # ------------------------------------------------------------------
    # GOBLIN AI -- swarm, flank, group damage bonus
    # ------------------------------------------------------------------
    def _ai_goblin(self, player, dungeon, dt, dist, ndx, ndy, nearby):
        results = []
        # Count nearby goblins for swarm bonus
        goblin_count = sum(
            1 for e in nearby
            if e is not self and e.alive and e.name == 'goblin'
            and math.hypot(e.x - self.x, e.y - self.y) < 120
        )
        self.special_data['swarm_bonus'] = goblin_count >= 2  # 3+ total goblins

        if dist > self.aggro_range:
            return results

        # Try to flank: move to the side/behind the player
        if dist > 50:
            angle = self.special_data.get('flank_angle', 0)
            offset = 70
            target_x = player.x + math.cos(angle) * offset
            target_y = player.y + math.sin(angle) * offset
            self._move_toward(target_x, target_y, dungeon, dt, speed_mult=1.2)
            # Slowly rotate flank angle
            self.special_data['flank_angle'] = angle + dt * 1.5
        elif self.attack_cooldown <= 0:
            damage_mult = 1.5 if self.special_data['swarm_bonus'] else 1.0
            dmg, _, _ = calculate_damage(int(self.strength * damage_mult), 0, player.defense)
            actual = player.take_damage(dmg)
            self.total_damage_dealt += actual
            self.attack_cooldown = self.attack_speed
            results.append(('melee', actual))
            self.actions_taken.append('attack')

        return results

    # ------------------------------------------------------------------
    # SKELETON AI -- walk toward, attack, occasionally block
    # ------------------------------------------------------------------
    def _ai_skeleton(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data

        # Block cooldown
        sd['block_cooldown'] = max(0, sd['block_cooldown'] - dt)
        if sd['blocking']:
            sd['block_timer'] -= dt
            if sd['block_timer'] <= 0:
                sd['blocking'] = False
                sd['block_cooldown'] = 4.0
            return results  # can't act while blocking

        if dist > self.aggro_range:
            return results

        if dist > 50:
            self._move_toward(player.x, player.y, dungeon, dt)
        elif self.attack_cooldown <= 0:
            dmg, _, _ = calculate_damage(self.strength, 0, player.defense)
            actual = player.take_damage(dmg)
            self.total_damage_dealt += actual
            self.attack_cooldown = self.attack_speed
            results.append(('melee', actual))
            self.actions_taken.append('attack')
            # Random chance to start blocking after attacking
            if sd['block_cooldown'] <= 0 and random.random() < 0.25:
                sd['blocking'] = True
                sd['block_timer'] = 1.0

        return results

    # ------------------------------------------------------------------
    # SLIME AI -- slow, tanky, poison trail, splits on death
    # ------------------------------------------------------------------
    def _ai_slime(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data

        # Leave poison trail
        sd['trail_timer'] -= dt
        if sd['trail_timer'] <= 0:
            sd['trail_timer'] = 0.5
            sd['poison_trail'].append({'x': self.x, 'y': self.y, 'life': 3.0})

        # Age out old trail tiles
        remaining = []
        for tile in sd['poison_trail']:
            tile['life'] -= dt
            if tile['life'] > 0:
                remaining.append(tile)
                # Check if player is on this poison tile
                pdist = math.hypot(player.x - tile['x'], player.y - tile['y'])
                if pdist < 20:
                    # 3 damage per second from poison
                    player.take_damage(max(1, int(3 * dt)))
        sd['poison_trail'] = remaining

        if dist > self.aggro_range:
            return results

        if dist > 40:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.6)
        elif self.attack_cooldown <= 0:
            dmg, _, _ = calculate_damage(self.strength, 0, player.defense)
            actual = player.take_damage(dmg)
            self.total_damage_dealt += actual
            self.attack_cooldown = self.attack_speed * 1.5  # slow attacks
            results.append(('melee', actual))
            self.actions_taken.append('attack')

        # On death, signal to split
        if not self.alive and getattr(self, 'can_split', False):
            self.can_split = False
            results.append(('split', self.x - 12, self.y))
            results.append(('split', self.x + 12, self.y))

        return results

    # ------------------------------------------------------------------
    # WOLF AI -- pack bonus, circling, lunge attack
    # ------------------------------------------------------------------
    def _ai_wolf(self, player, dungeon, dt, dist, ndx, ndy, nearby):
        results = []
        sd = self.special_data

        # Pack bonus: +25% damage per nearby wolf
        wolf_count = sum(
            1 for e in nearby
            if e is not self and e.alive and e.name == 'wolf'
            and math.hypot(e.x - self.x, e.y - self.y) < 150
        )
        sd['pack_bonus'] = wolf_count * 0.25

        sd['lunge_cooldown'] = max(0, sd['lunge_cooldown'] - dt)

        if dist > self.aggro_range:
            return results

        # Lunge attack
        if sd.get('lunging'):
            lt = sd.get('lunge_target')
            if lt:
                self._move_toward(lt[0], lt[1], dungeon, dt, speed_mult=3.0)
                ldist = math.hypot(lt[0] - self.x, lt[1] - self.y)
                if ldist < 30:
                    sd['lunging'] = False
                    sd['lunge_cooldown'] = 4.0
                    # Deal lunge damage
                    pdist = math.hypot(player.x - self.x, player.y - self.y)
                    if pdist < 50:
                        mult = 1.0 + sd['pack_bonus']
                        dmg, _, _ = calculate_damage(int(self.strength * mult * 1.5), 0, player.defense)
                        actual = player.take_damage(dmg)
                        self.total_damage_dealt += actual
                        results.append(('charge', player.x, player.y, actual))
            return results

        # Circle before attacking
        if dist > 60 and dist < 200:
            sd['circle_angle'] += dt * 2.5
            circle_r = min(dist, 100)
            target_x = player.x + math.cos(sd['circle_angle']) * circle_r
            target_y = player.y + math.sin(sd['circle_angle']) * circle_r
            self._move_toward(target_x, target_y, dungeon, dt, speed_mult=1.3)

            # Initiate lunge if cooldown is ready
            if sd['lunge_cooldown'] <= 0 and dist < 180:
                sd['lunging'] = True
                sd['lunge_target'] = (player.x, player.y)
        elif dist >= 200:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=1.3)
        elif self.attack_cooldown <= 0:
            mult = 1.0 + sd['pack_bonus']
            dmg, _, _ = calculate_damage(int(self.strength * mult), 0, player.defense)
            actual = player.take_damage(dmg)
            self.total_damage_dealt += actual
            self.attack_cooldown = self.attack_speed * 0.7
            results.append(('melee', actual))
            self.actions_taken.append('attack')

        return results

    # ------------------------------------------------------------------
    # BUG AI -- tiny, erratic, dodgy
    # ------------------------------------------------------------------
    def _ai_bug(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data

        sd['direction_timer'] -= dt
        if sd['direction_timer'] <= 0:
            # Pick a new random-ish direction, biased toward player
            angle = math.atan2(ndy, ndx) + random.uniform(-1.5, 1.5)
            sd['move_dx'] = math.cos(angle)
            sd['move_dy'] = math.sin(angle)
            sd['direction_timer'] = random.uniform(0.3, 0.8)

        if dist > self.aggro_range:
            return results

        # Move erratically
        move_speed = self.speed * 90 * dt
        new_x = self.x + sd['move_dx'] * move_speed
        new_y = self.y + sd['move_dy'] * move_speed
        gx, gy = int(new_x // TILE_SIZE), int(new_y // TILE_SIZE)
        if dungeon.is_walkable(gx, gy):
            self.x = new_x
            self.y = new_y

        if dist < 40 and self.attack_cooldown <= 0:
            dmg, _, _ = calculate_damage(self.strength, 0, player.defense)
            actual = player.take_damage(dmg)
            self.total_damage_dealt += actual
            self.attack_cooldown = self.attack_speed * 0.5  # fast nibbles
            results.append(('melee', actual))
            self.actions_taken.append('attack')

        return results

    # ------------------------------------------------------------------
    # UNDEAD SOLDIER AI -- shield blocks first 3 hits, then aggressive
    # ------------------------------------------------------------------
    def _ai_undead_soldier(self, player, dungeon, dt, dist, ndx, ndy):
        results = []

        if dist > self.aggro_range:
            return results

        if dist > 50:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.7)
        elif self.attack_cooldown <= 0:
            dmg, _, _ = calculate_damage(self.strength, 0, player.defense)
            actual = player.take_damage(dmg)
            self.total_damage_dealt += actual
            self.attack_cooldown = self.attack_speed * 1.3  # slow heavy swings
            results.append(('melee', actual))
            self.actions_taken.append('attack')

        return results

    # ------------------------------------------------------------------
    # ASSASSIN AI -- stealth, backstab
    # ------------------------------------------------------------------
    def _ai_assassin(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data

        sd['invis_cooldown'] = max(0, sd['invis_cooldown'] - dt)

        if sd['invisible']:
            sd['invis_timer'] -= dt
            if sd['invis_timer'] <= 0:
                sd['invisible'] = False
                sd['invis_cooldown'] = 5.0

        # Go invisible if cooldown is ready
        if not sd['invisible'] and sd['invis_cooldown'] <= 0 and dist < self.aggro_range:
            sd['invisible'] = True
            sd['invis_timer'] = 3.0
            sd['backstab_ready'] = True

        if dist > self.aggro_range:
            return results

        # While invisible, sneak toward player
        if sd['invisible']:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=1.4)
            # Backstab when close
            if dist < 45 and self.attack_cooldown <= 0 and sd['backstab_ready']:
                dmg, _, _ = calculate_damage(self.strength * 3, 0, player.defense)
                actual = player.take_damage(dmg)
                self.total_damage_dealt += actual
                self.attack_cooldown = self.attack_speed
                sd['invisible'] = False
                sd['backstab_ready'] = False
                sd['invis_cooldown'] = 5.0
                results.append(('melee', actual))
                self.actions_taken.append('backstab')
        else:
            # Visible: strafe and attack normally
            if dist > 60:
                self._move_toward(player.x, player.y, dungeon, dt, speed_mult=1.2)
            elif dist > 40:
                self._strafe(player.x, player.y, dungeon, dt)
            elif self.attack_cooldown <= 0:
                dmg, _, _ = calculate_damage(self.strength, 0, player.defense)
                actual = player.take_damage(dmg)
                self.total_damage_dealt += actual
                self.attack_cooldown = self.attack_speed
                results.append(('melee', actual))
                self.actions_taken.append('attack')

        return results

    # ------------------------------------------------------------------
    # SHAMAN AI -- heal lowest ally, buff all allies, stay back
    # ------------------------------------------------------------------
    def _ai_shaman(self, player, dungeon, dt, dist, ndx, ndy, nearby):
        results = []
        sd = self.special_data

        sd['heal_cooldown'] = max(0, sd['heal_cooldown'] - dt)
        sd['buff_cooldown'] = max(0, sd['buff_cooldown'] - dt)

        # Stay away from player
        if dist < 120:
            self._move_away(player.x, player.y, dungeon, dt)
        elif dist > 250:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.5)

        # Heal lowest-HP ally
        if sd['heal_cooldown'] <= 0 and not self.silenced:
            lowest = None
            lowest_pct = 1.0
            for e in nearby:
                if e is not self and e.alive and e.tier != 'special':
                    pct = e.hp / max(e.max_hp, 1)
                    if pct < lowest_pct:
                        lowest_pct = pct
                        lowest = e
            if lowest and lowest_pct < 0.9:
                heal_amount = 30
                lowest.hp = min(lowest.max_hp, lowest.hp + heal_amount)
                sd['heal_cooldown'] = 4.0
                results.append(('heal_allies', heal_amount, 300))
                self.actions_taken.append('heal')

        # Buff all nearby allies
        if sd['buff_cooldown'] <= 0 and not self.silenced:
            sd['buff_cooldown'] = 8.0
            results.append(('buff_allies', 'strength', 0.25, 5.0, 200))
            self.actions_taken.append('buff')

        # Basic ranged attack if nothing else to do
        if self.attack_cooldown <= 0 and dist < self.aggro_range:
            proj = Projectile(
                self.x, self.y, ndx, ndy, speed=200,
                damage=self.strength, effect=None,
                owner='enemy', color=self.color, lifetime=2.0
            )
            self.attack_cooldown = self.attack_speed * 2
            results.append(proj)

        return results

    # ------------------------------------------------------------------
    # ELITE KNIGHT AI -- frontal block, charge stun
    # ------------------------------------------------------------------
    def _ai_elite_knight(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data

        sd['charge_cooldown'] = max(0, sd['charge_cooldown'] - dt)

        # Update facing direction
        if dist > 1:
            sd['facing_dx'] = ndx
            sd['facing_dy'] = ndy

        if dist > self.aggro_range:
            return results

        # Charge attack from distance
        if sd['charge_cooldown'] <= 0 and dist > 120 and dist < 350:
            sd['charging'] = True
            sd['charge_target'] = (player.x, player.y)
            sd['charge_cooldown'] = 8.0

        if sd.get('charging'):
            ct = sd['charge_target']
            self._move_toward(ct[0], ct[1], dungeon, dt, speed_mult=1.8)
            cdist = math.hypot(ct[0] - self.x, ct[1] - self.y)
            if cdist < 40 or dist < 40:
                sd['charging'] = False
                # Stun player on hit
                if dist < 60:
                    dmg, _, _ = calculate_damage(int(self.strength * 1.5), 0, player.defense)
                    actual = player.take_damage(dmg)
                    self.total_damage_dealt += actual
                    # Apply stun
                    if hasattr(player, 'stunned'):
                        player.stunned = max(getattr(player, 'stunned', 0), 1.0)
                    results.append(('charge', player.x, player.y, actual))
                    self.actions_taken.append('charge')
            return results

        # Normal combat: advance and melee
        if dist > 55:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.8)
        elif self.attack_cooldown <= 0:
            dmg, _, _ = calculate_damage(self.strength, 0, player.defense)
            actual = player.take_damage(dmg)
            self.total_damage_dealt += actual
            self.attack_cooldown = self.attack_speed
            results.append(('melee', actual))
            self.actions_taken.append('attack')

        return results

    # ------------------------------------------------------------------
    # OGRE AI -- ground pound AoE, rock throw
    # ------------------------------------------------------------------
    def _ai_ogre(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data

        sd['ground_pound_cooldown'] = max(0, sd['ground_pound_cooldown'] - dt)
        sd['throw_cooldown'] = max(0, sd['throw_cooldown'] - dt)

        if dist > self.aggro_range:
            return results

        # Ground pound when player is close
        if sd['ground_pound_cooldown'] <= 0 and dist < 120:
            sd['ground_pound_cooldown'] = 6.0
            results.append(('aoe', self.x, self.y, 100, 40))
            self.actions_taken.append('ground_pound')
            return results

        # Throw rock at range
        if sd['throw_cooldown'] <= 0 and dist > 100 and dist < 300:
            sd['throw_cooldown'] = 5.0
            proj = Projectile(
                self.x, self.y, ndx, ndy, speed=250,
                damage=int(self.strength * 1.2), effect=None,
                owner='enemy', color=(120, 100, 80), lifetime=2.5
            )
            results.append(proj)
            self.actions_taken.append('throw')
            return results

        # Lumber toward player
        if dist > 50:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.6)
        elif self.attack_cooldown <= 0:
            dmg, _, _ = calculate_damage(int(self.strength * 1.3), 0, player.defense)
            actual = player.take_damage(dmg)
            self.total_damage_dealt += actual
            self.attack_cooldown = self.attack_speed * 1.5
            results.append(('melee', actual))
            self.actions_taken.append('attack')

        return results

    # ------------------------------------------------------------------
    # CURSED PRIEST AI -- curse DoT, silence, self-heal
    # ------------------------------------------------------------------
    def _ai_cursed_priest(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data

        sd['curse_cooldown'] = max(0, sd['curse_cooldown'] - dt)
        sd['silence_cooldown'] = max(0, sd['silence_cooldown'] - dt)
        sd['heal_tick'] += dt

        # Slow self-heal: 2 HP per second
        if sd['heal_tick'] >= 1.0:
            sd['heal_tick'] -= 1.0
            self.hp = min(self.max_hp, self.hp + 2)

        # Keep distance
        if dist < 100:
            self._move_away(player.x, player.y, dungeon, dt)
        elif dist > 280:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.7)

        if dist > self.aggro_range:
            return results

        # Apply curse (DoT + defense reduction)
        if sd['curse_cooldown'] <= 0 and not self.silenced:
            sd['curse_cooldown'] = 6.0
            # Signal curse application to game engine
            proj = Projectile(
                self.x, self.y, ndx, ndy, speed=220,
                damage=7, effect='curse',
                owner='enemy', color=(100, 0, 120), lifetime=2.0
            )
            results.append(proj)
            self.actions_taken.append('curse')

        # Apply silence
        if sd['silence_cooldown'] <= 0 and not self.silenced and dist < 250:
            sd['silence_cooldown'] = 10.0
            proj = Projectile(
                self.x, self.y, ndx, ndy, speed=200,
                damage=0, effect='silence',
                owner='enemy', color=(80, 0, 80), lifetime=2.0
            )
            results.append(proj)
            self.actions_taken.append('silence')

        return results

    # ------------------------------------------------------------------
    # DARK MAGE AI -- teleport, homing projectiles, freeze
    # ------------------------------------------------------------------
    def _ai_dark_mage(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data

        sd['teleport_cooldown'] = max(0, sd['teleport_cooldown'] - dt)
        sd['freeze_cooldown'] = max(0, sd['freeze_cooldown'] - dt)
        sd['cast_cooldown'] = max(0, sd['cast_cooldown'] - dt)

        if dist > self.aggro_range:
            return results

        # Teleport to random position
        if sd['teleport_cooldown'] <= 0:
            sd['teleport_cooldown'] = 4.0
            # Pick a random walkable spot within the room
            for _ in range(10):
                ox = self.x + random.uniform(-200, 200)
                oy = self.y + random.uniform(-200, 200)
                gx, gy = int(ox // TILE_SIZE), int(oy // TILE_SIZE)
                if dungeon.is_walkable(gx, gy):
                    self.x = ox
                    self.y = oy
                    results.append(('teleport', ox, oy))
                    self.actions_taken.append('teleport')
                    break
            # Recalculate direction after teleport
            dx = player.x - self.x
            dy = player.y - self.y
            d = math.sqrt(dx * dx + dy * dy)
            if d > 1:
                ndx, ndy = dx / d, dy / d
            dist = d

        # Freeze spell
        if sd['freeze_cooldown'] <= 0 and dist < 300:
            sd['freeze_cooldown'] = 8.0
            proj = Projectile(
                self.x, self.y, ndx, ndy, speed=180,
                damage=5, effect='freeze',
                owner='enemy', color=(100, 180, 255), lifetime=2.5
            )
            results.append(proj)
            self.actions_taken.append('freeze')

        # Homing projectile (slow tracking simulated by aiming at current player pos)
        if sd['cast_cooldown'] <= 0:
            sd['cast_cooldown'] = 2.0
            proj = Projectile(
                self.x, self.y, ndx, ndy, speed=150,
                damage=self.strength, effect=None,
                owner='enemy', color=self.color, lifetime=3.0
            )
            results.append(proj)
            self.actions_taken.append('ranged_attack')

        # Keep distance
        if dist < 120:
            self._move_away(player.x, player.y, dungeon, dt, speed_mult=1.2)

        return results

    # ------------------------------------------------------------------
    # Generic fallback action executor
    # ------------------------------------------------------------------
    def _execute_generic(self, action, player, dungeon, dt, dist, ndx, ndy):
        results = []
        if action == 'chase':
            self._move_toward(player.x, player.y, dungeon, dt)
        elif action == 'flee':
            self._move_away(player.x, player.y, dungeon, dt)
        elif action == 'strafe':
            self._strafe(player.x, player.y, dungeon, dt)
        elif action == 'attack' and self.attack_cooldown <= 0 and dist < 60:
            dmg, _, _ = calculate_damage(self.strength, 0, player.defense)
            actual = player.take_damage(dmg)
            self.total_damage_dealt += actual
            self.attack_cooldown = self.attack_speed
            results.append(('melee', actual))
        elif action == 'ranged_attack' and self.attack_cooldown <= 0:
            proj = Projectile(
                self.x, self.y, ndx, ndy, speed=300,
                damage=self.strength, effect=None,
                owner='enemy', color=self.color, lifetime=2.0
            )
            self.attack_cooldown = self.attack_speed
            results.append(proj)
        self.actions_taken.append(action)
        return results

    # ==================================================================
    # BOSS UPDATE
    # ==================================================================
    def _update_boss(self, player, dungeon, dt, dist, dx, dy, nearby_enemies):
        norm = max(dist, 1)
        ndx, ndy = dx / norm, dy / norm

        if self.gimmick == 'enrage':
            return self._boss_enrage(player, dungeon, dt, dist, ndx, ndy)
        elif self.gimmick == 'counter':
            return self._boss_counter(player, dungeon, dt, dist, ndx, ndy)
        elif self.gimmick == 'summons':
            return self._boss_summons(player, dungeon, dt, dist, ndx, ndy)
        elif self.gimmick == 'hazard':
            return self._boss_hazard(player, dungeon, dt, dist, ndx, ndy)
        elif self.gimmick == 'phases':
            return self._boss_phases(player, dungeon, dt, dist, ndx, ndy)
        elif self.gimmick == 'heal_totem':
            return self._boss_dragon(player, dungeon, dt, dist, ndx, ndy)
        return []

    # ------------------------------------------------------------------
    # GIANT BEAST -- enrage at 30% HP
    # ------------------------------------------------------------------
    def _boss_enrage(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data
        hp_pct = self.hp / max(self.max_hp, 1)

        # Check for enrage trigger
        if not sd['enraged'] and hp_pct < 0.3:
            sd['enraged'] = True
            self.speed *= 1.4  # moderate speed boost, not 2x
            self.strength = int(self.strength * 1.5)

        speed_mult = 0.8  # bosses move deliberately
        if sd['enraged']:
            speed_mult = 1.0

        # Ground slam AoE
        self.special_cooldown = max(0, self.special_cooldown - dt)
        if self.special_cooldown <= 0 and dist < 100:
            slam_cd = 5.0 if sd['enraged'] else 8.0
            self.special_cooldown = slam_cd
            results.append(('aoe', self.x, self.y, 120, int(30)))
            self.actions_taken.append('ground_slam')

        # Chase and melee — boss pauses briefly after reaching the player
        if dist > 80:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=speed_mult)
        elif dist > 50:
            # Slow approach in melee range
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=speed_mult * 0.4)
        elif self.attack_cooldown <= 0:
            dmg, _, _ = calculate_damage(self.strength, 0, player.defense)
            actual = player.take_damage(dmg)
            self.total_damage_dealt += actual
            cd = self.attack_speed * (0.7 if sd['enraged'] else 1.0)
            self.attack_cooldown = cd
            results.append(('melee', actual))
            self.actions_taken.append('attack')

        return results

    # ------------------------------------------------------------------
    # FALLEN HERO -- counter window, 80% DR except during recovery
    # ------------------------------------------------------------------
    def _boss_counter(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data

        sd['swing_cooldown'] = max(0, sd['swing_cooldown'] - dt)
        sd['windup_timer'] = max(0, sd['windup_timer'] - dt)
        sd['recovery_timer'] = max(0, sd['recovery_timer'] - dt)

        # State machine: idle -> windup -> swing -> recovery -> idle
        if self.state == 'windup':
            # 3 second telegraph - boss is winding up
            sd['windup_timer'] -= dt
            if sd['windup_timer'] <= 0:
                # Execute the big swing
                self.state = 'swing'
                results.append(('aoe', self.x, self.y, 90, int(self.strength * 2)))
                self.actions_taken.append('overhead_swing')
                sd['recovery_timer'] = 2.0
                self.state = 'recovery'
            return results

        if self.state == 'recovery':
            # Vulnerable! Takes full damage (handled in take_damage)
            if sd['recovery_timer'] <= 0:
                self.state = 'idle'
                sd['swing_cooldown'] = 6.0
            return results

        # Normal state: chase with high DR
        if sd['swing_cooldown'] <= 0:
            self.state = 'windup'
            sd['windup_timer'] = 3.0
            return results

        if dist > 90:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.7)
        elif dist > 50:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.3)
        elif self.attack_cooldown <= 0:
            # Light poke attacks (still has 80% DR so player should wait)
            dmg, _, _ = calculate_damage(int(self.strength * 0.5), 0, player.defense)
            actual = player.take_damage(dmg)
            self.total_damage_dealt += actual
            self.attack_cooldown = self.attack_speed
            results.append(('melee', actual))
            self.actions_taken.append('poke')

        return results

    # ------------------------------------------------------------------
    # CORRUPTED KING -- summons waves of undead soldiers
    # ------------------------------------------------------------------
    def _boss_summons(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data

        sd['summon_cooldown'] = max(0, sd['summon_cooldown'] - dt)

        # Summon wave
        if sd['summon_cooldown'] <= 0:
            sd['summon_cooldown'] = 8.0
            sd['wave_number'] += 1
            self.summon_count += 1
            # 3-4 soldiers, getting stronger each wave
            count = 3 + min(sd['wave_number'] // 3, 2)  # caps at 5
            results.append(('summon', 'undead_soldier', count))
            self.actions_taken.append('summon_wave')

        # King does basic melee if player is close, otherwise sits
        if dist < 80 and self.attack_cooldown <= 0:
            dmg, _, _ = calculate_damage(self.strength, 0, player.defense)
            actual = player.take_damage(dmg)
            self.total_damage_dealt += actual
            self.attack_cooldown = self.attack_speed
            results.append(('melee', actual))
            self.actions_taken.append('attack')
        elif dist > 150:
            # Slowly drift toward player
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.3)

        return results

    # ------------------------------------------------------------------
    # DUNGEON GUARDIAN -- shrinking safe zone, hazards accumulate
    # ------------------------------------------------------------------
    def _boss_hazard(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data

        sd['hazard_timer'] = max(0, sd['hazard_timer'] - dt)

        # Spawn new hazard zone every 10s
        if sd['hazard_timer'] <= 0:
            sd['hazard_timer'] = 10.0
            # Place hazard somewhat near the player to pressure them
            hx = player.x + random.uniform(-150, 150)
            hy = player.y + random.uniform(-150, 150)
            radius = random.randint(60, 100)
            self.hazard_zones.append((hx, hy, radius))
            results.append(('hazard_zone', hx, hy, radius))
            self.actions_taken.append('hazard_spawn')

        # Check if player is standing in any hazard
        for hx, hy, hr in self.hazard_zones:
            pdist = math.hypot(player.x - hx, player.y - hy)
            if pdist < hr:
                player.take_damage(max(1, int(15 * dt)))

        # Tanky melee fighter — slow and deliberate
        if dist > 90:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.6)
        elif dist > 50:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.25)
        elif self.attack_cooldown <= 0:
            dmg, _, _ = calculate_damage(self.strength, 0, player.defense)
            actual = player.take_damage(dmg)
            self.total_damage_dealt += actual
            self.attack_cooldown = self.attack_speed
            results.append(('melee', actual))
            self.actions_taken.append('attack')

        return results

    # ------------------------------------------------------------------
    # FLOOR ADMIN -- three phase boss
    # ------------------------------------------------------------------
    def _boss_phases(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data
        hp_pct = self.hp / max(self.max_hp, 1)

        # Phase transitions
        new_phase = self.phase
        if hp_pct <= 0.33:
            new_phase = 3
        elif hp_pct <= 0.66:
            new_phase = 2

        # Handle phase transition
        if new_phase != self.phase:
            self.phase = new_phase
            sd['transition_invuln'] = 1.5  # brief invulnerability
            # Heal 5% on transition
            heal = int(self.max_hp * 0.05)
            self.hp = min(self.max_hp, self.hp + heal)
            sd['heal_amount'] = heal
            self.actions_taken.append(f'phase_transition_{self.phase}')
            return results

        # Tick invuln
        if sd.get('transition_invuln', 0) > 0:
            sd['transition_invuln'] -= dt
            return results

        # Phase 1: Melee fighter
        if self.phase == 1:
            if dist > 80:
                self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.7)
                # Occasional charge (telegraphed by distance)
                self.special_cooldown = max(0, self.special_cooldown - dt)
                if self.special_cooldown <= 0 and dist > 150:
                    self.special_cooldown = 8.0
                    results.append(('charge', player.x, player.y, self.strength))
                    self._move_toward(player.x, player.y, dungeon, dt, speed_mult=1.5)
                    self.actions_taken.append('charge')
            elif dist > 50:
                self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.3)
            elif self.attack_cooldown <= 0:
                dmg, _, _ = calculate_damage(self.strength, 0, player.defense)
                actual = player.take_damage(dmg)
                self.total_damage_dealt += actual
                self.attack_cooldown = self.attack_speed
                results.append(('melee', actual))
                self.actions_taken.append('attack')

        # Phase 2: Ranged + teleport
        elif self.phase == 2:
            sd['teleport_cooldown'] = sd.get('teleport_cooldown', 0) - dt
            if sd.get('teleport_cooldown', 0) <= 0:
                sd['teleport_cooldown'] = 5.0
                for _ in range(10):
                    ox = self.x + random.uniform(-200, 200)
                    oy = self.y + random.uniform(-200, 200)
                    gx, gy = int(ox // TILE_SIZE), int(oy // TILE_SIZE)
                    if dungeon.is_walkable(gx, gy):
                        self.x = ox
                        self.y = oy
                        results.append(('teleport', ox, oy))
                        break

            if dist < 120:
                self._move_away(player.x, player.y, dungeon, dt)

            if self.attack_cooldown <= 0:
                # Fire a spread of 3 projectiles
                for angle_off in [-0.3, 0.0, 0.3]:
                    cos_a = math.cos(angle_off)
                    sin_a = math.sin(angle_off)
                    pdx = ndx * cos_a - ndy * sin_a
                    pdy = ndx * sin_a + ndy * cos_a
                    proj = Projectile(
                        self.x, self.y, pdx, pdy, speed=280,
                        damage=int(self.strength * 0.7), effect=None,
                        owner='enemy', color=self.color, lifetime=2.0
                    )
                    results.append(proj)
                self.attack_cooldown = self.attack_speed * 1.2
                self.actions_taken.append('barrage')

        # Phase 3: Berserk -- combines both, faster
        elif self.phase == 3:
            speed_mult = 1.0

            # Teleport less often but still does it
            sd['teleport_cooldown'] = sd.get('teleport_cooldown', 0) - dt
            if sd.get('teleport_cooldown', 0) <= 0:
                sd['teleport_cooldown'] = 7.0
                for _ in range(10):
                    ox = self.x + random.uniform(-150, 150)
                    oy = self.y + random.uniform(-150, 150)
                    gx, gy = int(ox // TILE_SIZE), int(oy // TILE_SIZE)
                    if dungeon.is_walkable(gx, gy):
                        self.x = ox
                        self.y = oy
                        results.append(('teleport', ox, oy))
                        break

            if dist > 50:
                self._move_toward(player.x, player.y, dungeon, dt, speed_mult=speed_mult)

            if self.attack_cooldown <= 0:
                if dist < 70:
                    # Strong melee
                    dmg, _, _ = calculate_damage(int(self.strength * 1.5), 0, player.defense)
                    actual = player.take_damage(dmg)
                    self.total_damage_dealt += actual
                    self.attack_cooldown = self.attack_speed * 0.6
                    results.append(('melee', actual))
                else:
                    # Ranged
                    proj = Projectile(
                        self.x, self.y, ndx, ndy, speed=320,
                        damage=self.strength, effect=None,
                        owner='enemy', color=self.color, lifetime=2.0
                    )
                    self.attack_cooldown = self.attack_speed * 0.8
                    results.append(proj)
                self.actions_taken.append('berserk_attack')

        return results

    # ------------------------------------------------------------------
    # DRAGON -- heal totem gimmick, fire breath
    # ------------------------------------------------------------------
    def _boss_dragon(self, player, dungeon, dt, dist, ndx, ndy):
        results = []
        sd = self.special_data

        sd['totem_cooldown'] = max(0, sd['totem_cooldown'] - dt)
        sd['fire_breath_cooldown'] = max(0, sd['fire_breath_cooldown'] - dt)

        # Spawn heal totem
        if sd['totem_cooldown'] <= 0:
            sd['totem_cooldown'] = 15.0
            # Place totem behind the dragon relative to player
            tx = self.x - ndx * 80 + random.uniform(-40, 40)
            ty = self.y - ndy * 80 + random.uniform(-40, 40)
            results.append(('summon_totem', tx, ty))
            self.actions_taken.append('spawn_totem')

        # Fire breath -- cone AoE in player direction
        if sd['fire_breath_cooldown'] <= 0 and dist < 200:
            sd['fire_breath_cooldown'] = 7.0
            # Cone represented as AoE in front of dragon
            bx = self.x + ndx * 60
            by = self.y + ndy * 60
            results.append(('aoe', bx, by, 80, int(self.strength * 1.2)))
            # Apply burn DoT via projectile
            proj = Projectile(
                self.x, self.y, ndx, ndy, speed=200,
                damage=int(self.strength * 0.5), effect='burn',
                owner='enemy', color=(255, 100, 0), lifetime=1.5
            )
            results.append(proj)
            self.actions_taken.append('fire_breath')

        # Normal ranged attack
        if self.attack_cooldown <= 0 and dist < 350:
            proj = Projectile(
                self.x, self.y, ndx, ndy, speed=250,
                damage=self.strength, effect=None,
                owner='enemy', color=self.color, lifetime=2.5
            )
            self.attack_cooldown = self.attack_speed
            results.append(proj)

        # Move to maintain mid-range distance
        if dist < 100:
            self._move_away(player.x, player.y, dungeon, dt, speed_mult=0.8)
        elif dist > 250:
            self._move_toward(player.x, player.y, dungeon, dt, speed_mult=0.6)
        else:
            self._strafe(player.x, player.y, dungeon, dt, speed_mult=0.5)

        return results


class Totem(Enemy):
    """Heal totem spawned by dragon's heal_totem gimmick.

    Heals the parent boss 20 HP/sec. If alive for 10 seconds, fully heals
    the boss to max HP. Must be destroyed immediately by the player.
    """

    def __init__(self, x, y, parent_boss):
        super().__init__('goblin', x, y)  # goblin as stat base
        self.name = 'Heal Totem'
        self.hp = 80
        self.max_hp = 80
        self.color = (0, 255, 100)
        self.size = 20
        self.behavior = 'stationary'
        self.parent_boss = parent_boss
        self.heal_rate = 20  # HP per second to boss
        self.tier = 'special'
        self.lifetime = 0.0
        self.full_heal_time = 10.0  # fully heals boss after 10s

    def update(self, player, dungeon, dt, ai_brain=None, nearby_enemies=None):
        if not self.alive or not self.parent_boss.alive:
            return []

        self.lifetime += dt

        # If totem survives 10 seconds, fully heal boss
        if self.lifetime >= self.full_heal_time:
            self.parent_boss.hp = self.parent_boss.max_hp
            self.alive = False  # totem expires after full heal
            return []

        # Heal boss continuously
        heal = int(self.heal_rate * dt)
        self.parent_boss.hp = min(
            self.parent_boss.max_hp, self.parent_boss.hp + heal
        )
        return []
