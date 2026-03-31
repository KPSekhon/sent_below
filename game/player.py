"""
player.py - Player class with impactful abilities and status effect support.
Each class (Warrior, Mage, Rogue, Healer) has five distinct abilities that
produce rich results the engine can process.
"""

import pygame
import math
import time
from config import PLAYER_CLASSES, ABILITY_DATA, TILE_SIZE, COLORS, STATUS_EFFECTS
from game.combat import Ability, Item, Projectile, calculate_damage


# ---------------------------------------------------------------------------
# StatusEffect
# ---------------------------------------------------------------------------
class StatusEffect:
    """A timed status effect applied to the player or an enemy."""

    def __init__(self, name, duration, source="unknown"):
        self.name = name
        self.duration = duration
        self.remaining = duration
        self.source = source
        # Pull properties from config, with safe defaults
        cfg = STATUS_EFFECTS.get(name, {})
        self.damage_per_sec = cfg.get("damage_per_sec", 0)
        self.speed_mult = cfg.get("speed_mult", 1.0)
        self.damage_mult = cfg.get("damage_mult", 1.0)
        self.miss_chance = cfg.get("miss_chance", 0.0)
        self.defense_reduction = cfg.get("defense_reduction", 0)
        self.color = cfg.get("color", (200, 200, 200))

    def tick(self, dt):
        """Advance the timer. Returns damage dealt this tick (float)."""
        self.remaining -= dt
        return self.damage_per_sec * dt

    def is_expired(self):
        return self.remaining <= 0

    def __repr__(self):
        return f"StatusEffect({self.name!r}, {self.remaining:.1f}s)"


# ---------------------------------------------------------------------------
# Undead enemy names (for holy_light bonus)
# ---------------------------------------------------------------------------
UNDEAD_TYPES = frozenset({
    "skeleton", "undead_soldier", "cursed_priest", "fallen_hero", "corrupted_king",
})


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------
class Player:
    def __init__(self, player_class_name):
        data = PLAYER_CLASSES[player_class_name]
        self.class_name = player_class_name
        self.x = 0.0
        self.y = 0.0
        self.hp = data['hp']
        self.max_hp = data['hp']
        self.mp = data['mp']
        self.max_mp = data['mp']
        self.strength = data['str']
        self.defense = data['defense']
        self.speed = data['spd']
        self.level = 1
        self.xp = 0
        self.xp_to_level = 100
        self.color = COLORS.get(player_class_name, (0, 200, 255))
        self.size = 28
        self.abilities = []
        self.cooldowns = {}
        self.inventory = []
        self.equipment = {'weapon': None, 'armor': None, 'accessory': None}
        self.facing = (1, 0)
        self.attack_cooldown = 0.0
        self.attack_speed = 0.5
        self.invincible_timer = 0.0
        self.alive = True
        self.kills = 0
        self.damage_dealt = 0
        self.damage_taken = 0
        self.potions_used = 0
        self.abilities_used = 0
        self.crit_chance = 0.05 if player_class_name != 'rogue' else 0.20
        self.floor_times = []

        # Gold and inventory
        self.gold = 0
        self.max_inventory = 12  # inventory cap

        # --- Status effect support ---
        self.status_effects = []        # list of StatusEffect
        self.temp_buffs = {}            # name -> {stat, amount, duration}
        self.has_revive = False          # from revival_stone accessory

        # Buff helpers consumed by item system
        self.buff_str = 0
        self.buff_str_timer = 0.0

        self._load_abilities()

    # ------------------------------------------------------------------
    # Ability loading
    # ------------------------------------------------------------------
    def _load_abilities(self):
        class_data = PLAYER_CLASSES[self.class_name]
        for ab_name in class_data['abilities']:
            if ab_name in ABILITY_DATA:
                self.abilities.append(Ability(ab_name))
                self.cooldowns[ab_name] = 0.0

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    def get_rect(self):
        return pygame.Rect(
            self.x - self.size // 2, self.y - self.size // 2,
            self.size, self.size
        )

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------
    def move(self, dx, dy, dungeon, dt):
        """Move player by dx,dy scaled by effective speed and dt."""
        if self.is_cc_locked():
            return
        eff_speed = self.get_effective_speed()
        speed = eff_speed * 100 * dt
        new_x = self.x + dx * speed
        new_y = self.y + dy * speed
        margin = self.size // 2
        corners = [
            (new_x - margin, new_y - margin),
            (new_x + margin, new_y - margin),
            (new_x - margin, new_y + margin),
            (new_x + margin, new_y + margin),
        ]
        can_move = True
        for cx, cy in corners:
            tx, ty = int(cx // TILE_SIZE), int(cy // TILE_SIZE)
            if not dungeon.is_walkable(tx, ty):
                can_move = False
                break
        if can_move:
            self.x = new_x
            self.y = new_y
        if dx != 0 or dy != 0:
            length = math.sqrt(dx * dx + dy * dy)
            self.facing = (dx / length, dy / length)

    # ------------------------------------------------------------------
    # Effective speed (base * equipment * status)
    # ------------------------------------------------------------------
    def get_effective_speed(self):
        base = self.speed
        # Equipment speed bonus
        for slot in ('weapon', 'armor', 'accessory'):
            item = self.equipment.get(slot)
            if item:
                base += item.get_stat_bonus('spd')
        # Temp buff speed
        if 'speed_boost' in self.temp_buffs:
            base *= (1.0 + self.temp_buffs['speed_boost']['amount'])
        # Status effect speed multipliers (take the worst)
        worst_mult = 1.0
        for eff in self.status_effects:
            if eff.speed_mult < worst_mult:
                worst_mult = eff.speed_mult
        return max(0.0, base * worst_mult)

    # ------------------------------------------------------------------
    # CC locked (stun / freeze)
    # ------------------------------------------------------------------
    def is_cc_locked(self):
        """Return True if the player has stun or freeze and cannot act."""
        for eff in self.status_effects:
            if eff.name in ('stun', 'freeze') and not eff.is_expired():
                return True
        return False

    # ------------------------------------------------------------------
    # Status effect management
    # ------------------------------------------------------------------
    def apply_status_effect(self, effect):
        """Apply a StatusEffect. If the same effect exists, refresh duration."""
        for existing in self.status_effects:
            if existing.name == effect.name:
                existing.remaining = max(existing.remaining, effect.duration)
                return
        self.status_effects.append(effect)

    def remove_status_effect(self, name):
        """Remove all instances of a status effect by name."""
        self.status_effects = [e for e in self.status_effects if e.name != name]

    def remove_negative_effects(self):
        """Remove all negative status effects (not buffs)."""
        negative = {'burn', 'poison', 'freeze', 'stun', 'blind', 'curse',
                     'silence', 'slow', 'weaken'}
        self.status_effects = [
            e for e in self.status_effects if e.name not in negative
        ]

    # ------------------------------------------------------------------
    # Basic attack
    # ------------------------------------------------------------------
    def basic_attack(self, target_pos, enemies):
        if self.attack_cooldown > 0 or self.is_cc_locked():
            return []
        self.attack_cooldown = self.attack_speed
        dx = target_pos[0] - self.x
        dy = target_pos[1] - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist == 0:
            return []
        dx, dy = dx / dist, dy / dist
        self.facing = (dx, dy)

        weapon = self.equipment.get('weapon')
        bonus_str = weapon.get_stat_bonus('str') if weapon else 0
        base_dmg = self.strength + bonus_str + self.buff_str

        if self.class_name in ('mage', 'healer'):
            proj = Projectile(
                self.x, self.y, dx, dy, speed=400, damage=base_dmg,
                effect=None, owner='player', color=self.color, lifetime=1.0
            )
            return [proj]
        else:
            hits = []
            for enemy in enemies:
                ex, ey = enemy.x, enemy.y
                edist = math.sqrt((ex - self.x) ** 2 + (ey - self.y) ** 2)
                if edist < 60:
                    if dx * (ex - self.x) + dy * (ey - self.y) > 0:
                        dmg, crit, _miss = calculate_damage(
                            base_dmg, 0, enemy.defense, self.crit_chance
                        )
                        enemy.take_damage(dmg)
                        self.damage_dealt += dmg
                        hits.append((enemy, dmg, crit))
            return hits

    # ------------------------------------------------------------------
    # Ability use  (returns list of results for the engine)
    # ------------------------------------------------------------------
    def use_ability(self, index, target_pos, enemies):
        """Use ability at *index* toward *target_pos*.

        Returns a list of result objects/tuples:
            Projectile              - engine adds to projectile list
            (enemy, damage, crit)   - direct hit on enemy
            ('aoe_damage', x, y, radius, damage, effect_name, effect_duration)
            ('status_self', effect_name, duration)
            ('heal', amount)
            ('leap', target_x, target_y)
            ('chain_lightning', target_enemy, damage, chains_left)
            ('smoke_bomb', x, y, radius, duration)
            ('divine_shield', x, y, radius, duration)
            ('meteor_target', x, y, radius, damage, delay)
        """
        if index >= len(self.abilities):
            return []
        ability = self.abilities[index]

        # Resurrection is passive -- cannot be activated manually
        if ability.name == 'resurrection':
            return []

        if self.is_cc_locked():
            return []
        if not ability.can_use(self.mp, self.cooldowns.get(ability.name, 0)):
            return []

        self.mp -= ability.mp_cost
        self.cooldowns[ability.name] = ability.cooldown
        self.abilities_used += 1

        dx = target_pos[0] - self.x
        dy = target_pos[1] - self.y
        dist = max(math.sqrt(dx * dx + dy * dy), 1)
        ndx, ndy = dx / dist, dy / dist
        self.facing = (ndx, ndy)

        weapon = self.equipment.get('weapon')
        bonus_str = weapon.get_stat_bonus('str') if weapon else 0
        total_str = self.strength + bonus_str + self.buff_str
        # Apply STR temp buff
        if 'str_boost' in self.temp_buffs:
            total_str = int(total_str * (1.0 + self.temp_buffs['str_boost']['amount']))

        results = []
        name = ability.name

        # =============================================================
        # WARRIOR ABILITIES
        # =============================================================
        if name == 'slash':
            # Wide 180-degree cone, 70px range, hits all enemies in arc
            for enemy in enemies:
                edx = enemy.x - self.x
                edy = enemy.y - self.y
                edist = math.sqrt(edx * edx + edy * edy)
                if edist < 70:
                    # Dot product for facing check (180 deg = anything with dot > 0)
                    dot = ndx * edx + ndy * edy
                    if dot > 0 or edist < 20:  # very close always hits
                        dmg, crit, _miss = calculate_damage(
                            total_str, ability.base_damage, enemy.defense,
                            self.crit_chance
                        )
                        enemy.take_damage(dmg)
                        self.damage_dealt += dmg
                        results.append((enemy, dmg, crit))

        elif name == 'shield_wall':
            # 3s of 80% damage reduction, player glows blue
            self.temp_buffs['shield_wall'] = {
                'stat': 'damage_reduction',
                'amount': 0.80,
                'duration': 3.0,
            }
            results.append(('status_self', 'shield_wall', 3.0))

        elif name == 'knockback_slam':
            # AoE 100px radius around player, damage + knockback 120px + 1.5s stun
            results.append((
                'aoe_damage', self.x, self.y, 100,
                ability.base_damage + int(total_str * 0.8),
                'stun', 1.5
            ))
            for enemy in enemies:
                edx = enemy.x - self.x
                edy = enemy.y - self.y
                edist = math.sqrt(edx * edx + edy * edy)
                if edist < 100:
                    dmg, crit, _miss = calculate_damage(
                        total_str, ability.base_damage, enemy.defense,
                        self.crit_chance
                    )
                    enemy.take_damage(dmg)
                    self.damage_dealt += dmg
                    # Knockback 120px (engine clamps to walkable after)
                    if edist > 0:
                        kx = (enemy.x - self.x) / edist
                        ky = (enemy.y - self.y) / edist
                        enemy.x += kx * 120
                        enemy.y += ky * 120
                    # Stun 1.5s
                    if hasattr(enemy, 'apply_status_effect'):
                        enemy.apply_status_effect(StatusEffect('stun', 1.5))
                    else:
                        enemy.stunned = 1.5
                    results.append((enemy, dmg, crit))

        elif name == 'war_cry':
            # Taunt enemies within 200px for 3s, +30% STR for 5s
            for enemy in enemies:
                edist = math.sqrt(
                    (enemy.x - self.x) ** 2 + (enemy.y - self.y) ** 2
                )
                if edist < 200:
                    if hasattr(enemy, 'taunted_by'):
                        enemy.taunted_by = self
                        enemy.taunt_timer = 3.0
                    elif hasattr(enemy, 'apply_status_effect'):
                        enemy.apply_status_effect(StatusEffect('stun', 0.5))
            self.temp_buffs['str_boost'] = {
                'stat': 'str',
                'amount': 0.30,
                'duration': 5.0,
            }
            results.append(('status_self', 'war_cry', 5.0))

        elif name == 'leap':
            # Jump to target (max 200px), AoE on landing 80px, iframes during
            leap_dist = min(dist, 200)
            target_x = self.x + ndx * leap_dist
            target_y = self.y + ndy * leap_dist
            self.x = target_x
            self.y = target_y
            self.invincible_timer = 0.4
            landing_dmg = ability.base_damage + int(total_str * 0.6)
            results.append(('leap', target_x, target_y))
            results.append((
                'aoe_damage', target_x, target_y, 80,
                landing_dmg, None, 0
            ))
            for enemy in enemies:
                edist = math.sqrt(
                    (enemy.x - target_x) ** 2 + (enemy.y - target_y) ** 2
                )
                if edist < 80:
                    dmg, crit, _miss = calculate_damage(
                        total_str, ability.base_damage, enemy.defense,
                        self.crit_chance
                    )
                    enemy.take_damage(dmg)
                    self.damage_dealt += dmg
                    results.append((enemy, dmg, crit))

        # =============================================================
        # MAGE ABILITIES
        # =============================================================
        elif name == 'fireball':
            # Fast projectile, 40 base, 4s burn
            proj = Projectile(
                self.x, self.y, ndx, ndy, speed=550,
                damage=40 + int(total_str * 0.8),
                effect='burn', owner='player',
                color=COLORS.get('projectile_fire', (255, 120, 20)),
                lifetime=1.5
            )
            results.append(proj)

        elif name == 'lightning_bolt':
            # Instant hit nearest enemy within 300px, chain to 2 more
            nearest = None
            nearest_dist = 300
            for enemy in enemies:
                edist = math.sqrt(
                    (enemy.x - self.x) ** 2 + (enemy.y - self.y) ** 2
                )
                if edist < nearest_dist and enemy.alive:
                    nearest = enemy
                    nearest_dist = edist
            if nearest:
                dmg, crit, _miss = calculate_damage(
                    total_str, ability.base_damage, nearest.defense,
                    self.crit_chance
                )
                nearest.take_damage(dmg)
                self.damage_dealt += dmg
                if hasattr(nearest, 'apply_status_effect'):
                    nearest.apply_status_effect(StatusEffect('stun', 0.3))
                elif hasattr(nearest, 'stunned'):
                    nearest.stunned = 0.3
                results.append((nearest, dmg, crit))
                results.append(('chain_lightning', nearest, dmg, 2))

        elif name == 'freeze_blast':
            # AoE 120px at cursor, freeze 3s, frozen = 1.5x damage taken
            tx = target_pos[0]
            ty = target_pos[1]
            results.append((
                'aoe_damage', tx, ty, 120, 0, 'freeze', 3.0
            ))
            for enemy in enemies:
                edist = math.sqrt(
                    (enemy.x - tx) ** 2 + (enemy.y - ty) ** 2
                )
                if edist < 120:
                    if hasattr(enemy, 'apply_status_effect'):
                        enemy.apply_status_effect(StatusEffect('freeze', 3.0))
                    else:
                        enemy.stunned = 3.0

        elif name == 'blink':
            # Teleport to cursor (max 250px), 0.5s iframes, damaging afterimage
            blink_dist = min(dist, 250)
            old_x, old_y = self.x, self.y
            self.x = self.x + ndx * blink_dist
            self.y = self.y + ndy * blink_dist
            self.invincible_timer = 0.5
            # Afterimage deals damage at old position
            afterimage_dmg = 15 + int(total_str * 0.4)
            results.append((
                'aoe_damage', old_x, old_y, 50, afterimage_dmg, None, 0
            ))
            for enemy in enemies:
                edist = math.sqrt(
                    (enemy.x - old_x) ** 2 + (enemy.y - old_y) ** 2
                )
                if edist < 50:
                    enemy.take_damage(afterimage_dmg)
                    self.damage_dealt += afterimage_dmg
                    results.append((enemy, afterimage_dmg, False))

        elif name == 'meteor':
            # 1s delay, 150px AoE at cursor, 80 base, burn
            tx = target_pos[0]
            ty = target_pos[1]
            meteor_dmg = 80 + int(total_str * 1.0)
            results.append(('meteor_target', tx, ty, 150, meteor_dmg, 1.0))

        # =============================================================
        # ROGUE ABILITIES
        # =============================================================
        elif name == 'backstab':
            # Dash behind nearest enemy within 100px, 3x if from behind
            nearest = None
            nearest_dist = 100
            for enemy in enemies:
                edist = math.sqrt(
                    (enemy.x - self.x) ** 2 + (enemy.y - self.y) ** 2
                )
                if edist < nearest_dist and enemy.alive:
                    nearest = enemy
                    nearest_dist = edist
            if nearest:
                # Move behind the enemy
                efx = getattr(nearest, 'facing', (0, 1))
                if isinstance(efx, tuple) and len(efx) == 2:
                    behind_x = nearest.x - efx[0] * 30
                    behind_y = nearest.y - efx[1] * 30
                else:
                    behind_x = nearest.x - ndx * 30
                    behind_y = nearest.y - ndy * 30
                self.x = behind_x
                self.y = behind_y
                # Check if hitting from behind (dot product of our attack
                # direction and enemy facing should be positive = same dir)
                attack_dx = nearest.x - self.x
                attack_dy = nearest.y - self.y
                adist = math.sqrt(attack_dx ** 2 + attack_dy ** 2)
                if adist > 0:
                    attack_dx /= adist
                    attack_dy /= adist
                e_facing = getattr(nearest, 'facing', (0, 1))
                if isinstance(e_facing, tuple) and len(e_facing) == 2:
                    dot = attack_dx * e_facing[0] + attack_dy * e_facing[1]
                else:
                    dot = 0
                multiplier = 3.0 if dot > 0 else 1.0
                base_dmg = int((ability.base_damage + total_str * 0.8) * multiplier)
                dmg, crit, _miss = calculate_damage(
                    0, base_dmg, nearest.defense, self.crit_chance + 0.15
                )
                nearest.take_damage(dmg)
                self.damage_dealt += dmg
                results.append((nearest, dmg, crit))

        elif name == 'poison_strike':
            # Melee, applies 6s poison + 4s slow
            for enemy in enemies:
                edist = math.sqrt(
                    (enemy.x - self.x) ** 2 + (enemy.y - self.y) ** 2
                )
                if edist < 60:
                    dot = ndx * (enemy.x - self.x) + ndy * (enemy.y - self.y)
                    if dot > 0 or edist < 20:
                        dmg, crit, _miss = calculate_damage(
                            total_str, ability.base_damage, enemy.defense,
                            self.crit_chance
                        )
                        enemy.take_damage(dmg)
                        self.damage_dealt += dmg
                        if hasattr(enemy, 'apply_status_effect'):
                            enemy.apply_status_effect(StatusEffect('poison', 6.0))
                            enemy.apply_status_effect(StatusEffect('slow', 4.0))
                        else:
                            enemy.poisoned = 6.0
                        results.append((enemy, dmg, crit))

        elif name == 'dash':
            # Quick dash 200px in movement direction, iframes, afterimage trail
            dash_dx, dash_dy = self.facing
            old_x, old_y = self.x, self.y
            self.x += dash_dx * 200
            self.y += dash_dy * 200
            self.invincible_timer = 0.3
            results.append(('leap', self.x, self.y))  # engine uses for visual

        elif name == 'smoke_bomb':
            # Drop at position, 100px radius, 3s blind+slow, semi-invisible
            results.append(('smoke_bomb', self.x, self.y, 100, 3.0))
            for enemy in enemies:
                edist = math.sqrt(
                    (enemy.x - self.x) ** 2 + (enemy.y - self.y) ** 2
                )
                if edist < 100:
                    if hasattr(enemy, 'apply_status_effect'):
                        enemy.apply_status_effect(StatusEffect('blind', 3.0))
                        enemy.apply_status_effect(StatusEffect('slow', 3.0))
                    else:
                        enemy.stunned = 1.5
            # Player becomes semi-invisible (enemies lose aggro)
            self.temp_buffs['stealth'] = {
                'stat': 'stealth',
                'amount': 1.0,
                'duration': 3.0,
            }
            results.append(('status_self', 'stealth', 3.0))

        elif name == 'blade_flurry':
            # 5 rapid blade projectiles fanning out in facing direction
            strike_dmg = int((ability.base_damage + total_str * 0.8) * 0.6)
            spread_angles = [-0.3, -0.15, 0.0, 0.15, 0.3]
            for angle_off in spread_angles:
                cos_a = math.cos(angle_off)
                sin_a = math.sin(angle_off)
                bdx = ndx * cos_a - ndy * sin_a
                bdy = ndx * sin_a + ndy * cos_a
                proj = Projectile(
                    self.x, self.y, bdx, bdy, speed=500,
                    damage=strike_dmg, effect=None, owner='player',
                    color=(200, 200, 220), lifetime=0.5,
                    piercing=True,
                )
                proj.blade_flurry = True
                results.append(proj)

        # =============================================================
        # HEALER ABILITIES
        # =============================================================
        elif name == 'heal':
            # Instant heal 60 HP
            heal_amount = 60
            self.hp = min(self.max_hp, self.hp + heal_amount)
            results.append(('heal', heal_amount))

        elif name == 'holy_light':
            # Projectile, 2x vs undead, heals player 20 on hit
            base_holy = ability.base_damage + int(total_str * 0.8)
            proj = Projectile(
                self.x, self.y, ndx, ndy, speed=450,
                damage=base_holy,
                effect='holy', owner='player',
                color=(255, 255, 150), lifetime=1.5
            )
            # Tag projectile so engine can check undead bonus and heal
            proj.holy_light = True
            proj.heal_on_hit = 20
            proj.undead_multiplier = 2.0
            results.append(proj)

        elif name == 'purify':
            # Remove ALL negative status effects, heal 20 HP
            self.remove_negative_effects()
            self.hp = min(self.max_hp, self.hp + 20)
            results.append(('heal', 20))
            results.append(('status_self', 'purify', 0.5))

        elif name == 'divine_shield':
            # Shield zone at cursor, 100px radius, blocks projectiles,
            # heals 5 HP/sec inside, lasts 5s
            tx = target_pos[0]
            ty = target_pos[1]
            results.append(('divine_shield', tx, ty, 100, 5.0))

        elif name == 'resurrection':
            # Passive only -- handled in take_damage, never activated manually
            pass

        # =============================================================
        # FALLBACK: generic handling for any ABILITY_DATA-driven ability
        # that is not explicitly handled above
        # =============================================================
        else:
            if ability.ab_type == 'damage':
                if ability.range > 100:
                    proj = Projectile(
                        self.x, self.y, ndx, ndy, speed=500,
                        damage=ability.calculate_damage(total_str, 0),
                        effect=ability.effect, owner='player',
                        color=(255, 100, 0), lifetime=1.5
                    )
                    results.append(proj)
                else:
                    for enemy in enemies:
                        edist = math.sqrt(
                            (enemy.x - self.x) ** 2 + (enemy.y - self.y) ** 2
                        )
                        if edist < ability.range:
                            dmg = ability.calculate_damage(total_str, enemy.defense)
                            enemy.take_damage(dmg)
                            self.damage_dealt += dmg
                            results.append((enemy, dmg, False))
            elif ability.ab_type == 'control':
                for enemy in enemies:
                    edist = math.sqrt(
                        (enemy.x - self.x) ** 2 + (enemy.y - self.y) ** 2
                    )
                    if edist < ability.range:
                        if ability.effect == 'stun':
                            enemy.stunned = 2.0
                        elif ability.effect == 'freeze':
                            enemy.stunned = 3.0
                        elif ability.effect == 'silence':
                            enemy.silenced = 2.0
                        results.append(enemy)
            elif ability.ab_type == 'mobility':
                move_dist = ability.range
                self.x += ndx * move_dist
                self.y += ndy * move_dist
                self.invincible_timer = 0.3
            elif ability.ab_type == 'survival':
                if ability.effect == 'heal' or ability.effect == 'restore_hp':
                    heal_amt = abs(ability.base_damage)
                    self.hp = min(self.max_hp, self.hp + heal_amt)
                    results.append(('heal', heal_amt))
                elif ability.effect == 'shield' or ability.effect == 'damage_reduction':
                    self.invincible_timer = 3.0
                    results.append(('status_self', 'shield', 3.0))
            elif ability.ab_type == 'utility':
                results.append(('utility', ability.effect))

        return results

    # ------------------------------------------------------------------
    # Take damage (with shield_wall, freeze multiplier, revive logic)
    # ------------------------------------------------------------------
    def take_damage(self, amount):
        if self.invincible_timer > 0:
            return 0

        # Armor defense bonus
        armor = self.equipment.get('armor')
        bonus_def = armor.get_stat_bonus('defense') if armor else 0
        total_def = self.defense + bonus_def

        # Status-based defense reduction
        for eff in self.status_effects:
            total_def -= eff.defense_reduction

        reduced = max(1, amount - total_def // 3)

        # Shield wall: 80% damage reduction
        if 'shield_wall' in self.temp_buffs:
            reduced = max(1, int(reduced * (1.0 - self.temp_buffs['shield_wall']['amount'])))

        # Frozen player takes 1.5x damage
        for eff in self.status_effects:
            if eff.name == 'freeze' and not eff.is_expired():
                reduced = int(reduced * 1.5)
                break

        self.hp -= reduced
        self.damage_taken += reduced
        self.invincible_timer = 0.3

        if self.hp <= 0:
            # Check resurrection ability (passive auto-revive)
            if self._try_resurrection():
                return reduced

            # Check revival stone accessory
            if self.has_revive:
                self.hp = int(self.max_hp * 0.25)
                self.has_revive = False
                self.invincible_timer = 2.0
                return reduced

            self.hp = 0
            self.alive = False

        return reduced

    def _try_resurrection(self):
        """Check if the healer resurrection ability can trigger. Returns True
        if the player was revived."""
        for ab in self.abilities:
            if ab.name == 'resurrection':
                cd = self.cooldowns.get('resurrection', 0)
                if cd <= 0 and self.mp >= ab.mp_cost:
                    # Auto-revive at 30% HP with 2s invincibility
                    self.hp = int(self.max_hp * 0.30)
                    self.mp -= ab.mp_cost
                    self.cooldowns['resurrection'] = ab.cooldown
                    self.invincible_timer = 2.0
                    self.alive = True
                    return True
        return False

    # ------------------------------------------------------------------
    # XP / Leveling
    # ------------------------------------------------------------------
    def gain_xp(self, amount):
        self.xp += amount
        leveled = False
        while self.xp >= self.xp_to_level:
            self.xp -= self.xp_to_level
            self.level += 1
            # XP curve: fast early, slows down.  Levels 1-5 are quick, 6+ get harder
            # Formula: base * level^1.4  (e.g. 50, 132, 237, 360, 500, 655, 825...)
            self.xp_to_level = int(50 * (self.level ** 1.4))

            # Class-specific stat gains per level
            if self.class_name == 'warrior':
                self.max_hp += 18
                self.max_mp += 3
                self.strength += 3
                self.defense += 2
                self.speed += 0.05
            elif self.class_name == 'mage':
                self.max_hp += 8
                self.max_mp += 12
                self.strength += 4  # spell power
                self.defense += 1
                self.speed += 0.1
            elif self.class_name == 'rogue':
                self.max_hp += 10
                self.max_mp += 5
                self.strength += 3
                self.defense += 1
                self.speed += 0.2
                self.crit_chance = min(0.50, self.crit_chance + 0.01)
            elif self.class_name == 'healer':
                self.max_hp += 12
                self.max_mp += 10
                self.strength += 2
                self.defense += 2
                self.speed += 0.1

            # Full heal on level up
            self.hp = self.max_hp
            self.mp = self.max_mp
            leveled = True
        return leveled

    # ------------------------------------------------------------------
    # Equipment / Consumables
    # ------------------------------------------------------------------
    def equip_item(self, item):
        if item.item_type in ('weapon', 'armor', 'accessory'):
            old = self.equipment.get(item.item_type)
            self.equipment[item.item_type] = item
            if item in self.inventory:
                self.inventory.remove(item)
            if old:
                self.inventory.append(old)
            # Check for revival stone accessory
            if item.item_type == 'accessory' and 'revive' in item.stats:
                self.has_revive = True

    def use_consumable(self, item):
        if item.item_type == 'consumable' and item in self.inventory:
            item.apply(self)
            self.inventory.remove(item)
            self.potions_used += 1

    # ------------------------------------------------------------------
    # Update (cooldowns, status effects, buffs, regen)
    # ------------------------------------------------------------------
    def update(self, dt):
        """Tick all timers, process status effects, regen MP."""
        # Cooldowns
        self.attack_cooldown = max(0, self.attack_cooldown - dt)
        self.invincible_timer = max(0, self.invincible_timer - dt)
        for name in self.cooldowns:
            self.cooldowns[name] = max(0, self.cooldowns[name] - dt)

        # Buff str timer
        if self.buff_str_timer > 0:
            self.buff_str_timer -= dt
            if self.buff_str_timer <= 0:
                self.buff_str = 0
                self.buff_str_timer = 0

        # --- Process status effects ---
        dot_total = 0.0
        for eff in self.status_effects:
            dot_total += eff.tick(dt)

        # Apply DoT damage
        if dot_total > 0 and self.alive:
            dot_dmg = int(dot_total)
            if dot_dmg > 0:
                self.hp -= dot_dmg
                self.damage_taken += dot_dmg
                if self.hp <= 0:
                    if not self._try_resurrection() and not self.has_revive:
                        self.hp = 0
                        self.alive = False
                    elif self.has_revive:
                        self.hp = int(self.max_hp * 0.25)
                        self.has_revive = False
                        self.invincible_timer = 2.0

        # Remove expired status effects
        self.status_effects = [e for e in self.status_effects if not e.is_expired()]

        # --- Process temp buffs ---
        expired_buffs = []
        for buff_name, buff_data in self.temp_buffs.items():
            buff_data['duration'] -= dt
            if buff_data['duration'] <= 0:
                expired_buffs.append(buff_name)
        for buff_name in expired_buffs:
            del self.temp_buffs[buff_name]

        # MP regen
        self.mp = min(self.max_mp, self.mp + 1.0 * dt)

    # ------------------------------------------------------------------
    # Stats dict (for ML / UI)
    # ------------------------------------------------------------------
    def get_stats_dict(self):
        """Return current stats as dict for ML systems."""
        return {
            'hp_pct': self.hp / max(self.max_hp, 1),
            'mp_pct': self.mp / max(self.max_mp, 1),
            'level': self.level,
            'kills': self.kills,
            'damage_dealt': self.damage_dealt,
            'damage_taken': self.damage_taken,
            'potions_used': self.potions_used,
            'abilities_used': self.abilities_used,
            'class': self.class_name,
            'status_effects': [e.name for e in self.status_effects],
            'active_buffs': list(self.temp_buffs.keys()),
            'effective_speed': self.get_effective_speed(),
            'cc_locked': self.is_cc_locked(),
            'gold': self.gold,
            'inventory_count': len(self.inventory),
        }
