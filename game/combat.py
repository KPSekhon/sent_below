"""
combat.py - Status effects, item system, ability handling, projectiles,
damage calculations, loot generation, and floating damage numbers.
"""

import math
import random
import pygame

from config import (
    ABILITY_DATA, ITEM_DATA, DIFFICULTY_BASE, FLOOR_CONFIG, COLORS,
    STATUS_EFFECTS, TILE_SIZE, LOOT_TABLES, GOLD_DROPS, SELL_PRICES,
)


# ---------------------------------------------------------------------------
# StatusEffect
# ---------------------------------------------------------------------------
class StatusEffect:
    """Active status effect on an entity."""

    def __init__(self, name: str, duration: float, source: str = 'unknown'):
        data = STATUS_EFFECTS[name]
        self.name = name
        self.duration = duration
        self.max_duration = duration
        self.timer = 0.0            # for DoT tick tracking
        self.tick_interval = 1.0    # damage every 1 second
        self.damage_per_sec = data.get('damage_per_sec', 0)
        self.speed_mult = data.get('speed_mult', 1.0)
        self.damage_mult = data.get('damage_mult', 1.0)
        self.miss_chance = data.get('miss_chance', 0.0)
        self.defense_reduction = data.get('defense_reduction', 0)
        self.color = tuple(data.get('color', (255, 255, 255)))
        self.source = source

    def update(self, dt: float) -> int:
        """Update the effect. Returns damage to apply this frame (for DoTs)."""
        self.duration -= dt
        damage = 0
        if self.damage_per_sec > 0:
            self.timer += dt
            if self.timer >= self.tick_interval:
                self.timer -= self.tick_interval
                damage = self.damage_per_sec
        return damage

    def is_expired(self) -> bool:
        return self.duration <= 0

    def is_cc(self) -> bool:
        """Is this a crowd-control effect (prevents acting)?"""
        return self.name in ('stun', 'freeze')

    def remaining_fraction(self) -> float:
        """Return 0..1 how much time is left relative to the original duration."""
        if self.max_duration <= 0:
            return 0.0
        return max(0.0, self.duration / self.max_duration)

    def __repr__(self):
        return f"StatusEffect({self.name!r}, {self.duration:.1f}s left)"


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------
class Item:
    """Represents an in-game item (weapon, armor, consumable, or accessory)."""

    def __init__(self, name: str, item_type: str, stats: dict, rarity: str,
                 description: str = ""):
        self.name = name
        self.item_type = item_type   # weapon / armor / consumable / accessory
        self.stats = dict(stats)
        self.rarity = rarity         # common / uncommon / rare / epic / legendary
        self.description = description

    # -- consumable usage --------------------------------------------------
    def apply(self, player) -> str:
        """Apply a consumable to *player*. Returns a short message."""
        if self.item_type != "consumable":
            return f"{self.name} is not consumable."

        msg_parts: list[str] = []

        # --- health restoration ---
        if "restore_hp" in self.stats:
            amount = int(self.stats["restore_hp"]
                         * DIFFICULTY_BASE["potion_effectiveness"])
            player.hp = min(player.hp + amount, player.max_hp)
            msg_parts.append(f"+{amount} HP")

        # --- mana restoration ---
        if "restore_mp" in self.stats:
            amount = int(self.stats["restore_mp"]
                         * DIFFICULTY_BASE["potion_effectiveness"])
            player.mp = min(player.mp + amount, player.max_mp)
            msg_parts.append(f"+{amount} MP")

        # --- strength buff ---
        if "buff_str" in self.stats:
            bonus = self.stats["buff_str"]
            duration = self.stats.get("buff_duration", 10)
            player.buff_str = getattr(player, 'buff_str', 0) + bonus
            player.buff_str_timer = duration
            # Also push into temp_buffs if available
            if hasattr(player, 'temp_buffs'):
                player.temp_buffs['str'] = {
                    'value': bonus, 'duration': duration,
                }
            msg_parts.append(f"STR +{bonus} for {duration}s")

        # --- speed buff ---
        if "buff_spd" in self.stats:
            bonus = self.stats["buff_spd"]
            duration = self.stats.get("buff_duration", 10)
            if hasattr(player, 'temp_buffs'):
                player.temp_buffs['spd'] = {
                    'value': bonus, 'duration': duration,
                }
            msg_parts.append(f"SPD +{bonus} for {duration}s")

        # --- cure / antidote ---
        if "cure" in self.stats:
            ailment = self.stats["cure"]
            cleared = False
            # Support new list-based status_effects
            if hasattr(player, 'status_effects') and isinstance(
                    player.status_effects, list):
                if ailment == "all_dots":
                    before = len(player.status_effects)
                    player.status_effects = [
                        e for e in player.status_effects
                        if e.damage_per_sec <= 0
                    ]
                    cleared = len(player.status_effects) < before
                else:
                    before = len(player.status_effects)
                    player.status_effects = [
                        e for e in player.status_effects
                        if e.name != ailment
                    ]
                    cleared = len(player.status_effects) < before
            # Legacy set-based status_effects
            elif hasattr(player, 'status_effects'):
                if ailment in player.status_effects:
                    player.status_effects.discard(ailment)
                    cleared = True
            if cleared:
                msg_parts.append(f"Cured {ailment}")
            else:
                msg_parts.append(f"No {ailment} to cure")

        # --- revival stone ---
        if "revival" in self.stats:
            player.has_revive = True
            msg_parts.append("Revival stone active")

        # --- cast an ability from a scroll ---
        if "cast_ability" in self.stats:
            msg_parts.append(f"Cast {self.stats['cast_ability']}")

        return (f"{self.name}: " + ", ".join(msg_parts)
                if msg_parts else f"{self.name} used.")

    # -- stat helpers ------------------------------------------------------
    def get_stat_bonus(self, stat_name: str) -> int:
        """Return the bonus this item grants for *stat_name*, or 0."""
        return self.stats.get(stat_name, 0)

    def __repr__(self):
        return f"Item({self.name!r}, {self.rarity})"


# ---------------------------------------------------------------------------
# Ability
# ---------------------------------------------------------------------------
class Ability:
    """Wraps a single ability with cost, cooldown, and damage logic."""

    def __init__(self, name: str):
        data = ABILITY_DATA[name]
        self.name = name
        self.ab_type = data["type"]
        self.mp_cost = data["mp_cost"]
        self.cooldown = data["cooldown"]
        self.base_damage = data["damage"]
        self.range = data["range"]
        self.effect = data["effect"]
        self.description = data["description"]
        # New fields with safe defaults for backward compatibility
        self.duration = data.get("duration", 0.0)
        self.area_of_effect = data.get("area_of_effect", 0)

    def can_use(self, caster_mp: int, current_cooldown: float) -> bool:
        """Return True if the caster has enough MP and the cooldown is ready."""
        return caster_mp >= self.mp_cost and current_cooldown <= 0

    def calculate_damage(self, caster_str: int, target_def: int) -> int:
        """Compute final damage taking caster strength and target defense into
        account.  Healing abilities return negative values (health restored)."""
        if self.base_damage < 0:
            # Healing: return the raw heal amount (negative = restore)
            return self.base_damage

        raw = self.base_damage + caster_str * 0.8
        reduction = target_def * 0.5
        return max(1, int(raw - reduction))

    def __repr__(self):
        return f"Ability({self.name!r})"


# ---------------------------------------------------------------------------
# Projectile
# ---------------------------------------------------------------------------
class Projectile:
    """A moving projectile with position, velocity, damage, and lifetime."""

    def __init__(self, x: float, y: float, dx: float, dy: float,
                 speed: float, damage: int, effect: str | None,
                 owner: str, color: tuple, lifetime: float = 3.0,
                 effect_name: str | None = None,
                 effect_duration: float = 0.0,
                 piercing: bool = False,
                 homing: float = 0.0):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.speed = speed
        self.damage = damage
        self.effect = effect
        self.owner = owner          # "player" or enemy name
        self.color = color
        self.lifetime = lifetime
        self.alive = True
        self._width = 8
        self._height = 8

        # New properties
        self.effect_name = effect_name      # StatusEffect name to apply on hit
        self.effect_duration = effect_duration
        self.piercing = piercing            # passes through enemies
        self.homing = max(0.0, min(1.0, homing))  # 0=straight, 1=perfect tracking
        self._hit_ids: set[int] = set()     # track already-hit entities for piercing
        self.bounces = 0                    # wall-bounce counter
        self.max_bounces = 3               # die after this many bounces

    def update(self, dt: float, target=None, dungeon=None) -> bool:
        """Advance the projectile by *dt* seconds.

        If *target* is provided and the projectile has homing > 0, it curves
        toward *target* (must have .x and .y attributes).

        If *dungeon* is provided, the projectile bounces off walls instead of
        flying through them.

        Returns True while alive.
        """
        if not self.alive:
            return False

        # Homing logic: blend current direction toward target
        if self.homing > 0 and target is not None:
            tx = getattr(target, 'x', self.x)
            ty = getattr(target, 'y', self.y)
            to_x = tx - self.x
            to_y = ty - self.y
            dist = math.hypot(to_x, to_y)
            if dist > 0.01:
                desired_dx = to_x / dist
                desired_dy = to_y / dist
                # Blend factor increases with homing strength and dt
                blend = min(1.0, self.homing * 5.0 * dt)
                self.dx = self.dx * (1 - blend) + desired_dx * blend
                self.dy = self.dy * (1 - blend) + desired_dy * blend
                # Re-normalize direction
                mag = math.hypot(self.dx, self.dy)
                if mag > 0.01:
                    self.dx /= mag
                    self.dy /= mag

        old_x, old_y = self.x, self.y
        self.x += self.dx * self.speed * dt
        self.y += self.dy * self.speed * dt

        # Wall collision: bounce off walls if dungeon is available
        if dungeon is not None:
            gx = int(self.x // TILE_SIZE)
            gy = int(self.y // TILE_SIZE)
            if not dungeon.is_walkable(gx, gy):
                # Check each axis independently to determine bounce direction
                gx_only = int(self.x // TILE_SIZE)
                gy_old = int(old_y // TILE_SIZE)
                gx_old = int(old_x // TILE_SIZE)
                gy_only = int(self.y // TILE_SIZE)

                bounced = False
                # Horizontal wall hit
                if not dungeon.is_walkable(gx_only, gy_old):
                    self.dx = -self.dx
                    self.x = old_x
                    bounced = True
                # Vertical wall hit
                if not dungeon.is_walkable(gx_old, gy_only):
                    self.dy = -self.dy
                    self.y = old_y
                    bounced = True
                # Corner case: both axes blocked but neither individually
                if not bounced:
                    self.dx = -self.dx
                    self.dy = -self.dy
                    self.x = old_x
                    self.y = old_y

                self.bounces += 1
                self.speed *= 0.8  # lose 20% speed on each bounce
                if self.bounces >= self.max_bounces:
                    self.alive = False
                    return False

        self.lifetime -= dt
        if self.lifetime <= 0:
            self.alive = False
        return self.alive

    def has_hit(self, entity_id: int) -> bool:
        """Check if this piercing projectile already hit *entity_id*."""
        return entity_id in self._hit_ids

    def register_hit(self, entity_id: int) -> None:
        """Mark *entity_id* as already hit (for piercing projectiles)."""
        self._hit_ids.add(entity_id)
        if not self.piercing:
            self.alive = False

    def get_rect(self) -> pygame.Rect:
        """Return the bounding rectangle for collision checks."""
        return pygame.Rect(int(self.x) - self._width // 2,
                           int(self.y) - self._height // 2,
                           self._width, self._height)

    def __repr__(self):
        return (f"Projectile(pos=({self.x:.0f},{self.y:.0f}), "
                f"dmg={self.damage}, owner={self.owner!r})")


# ---------------------------------------------------------------------------
# Damage Calculation
# ---------------------------------------------------------------------------
def _collect_effect_stats(effects: list | None):
    """Aggregate multipliers and modifiers from a list of StatusEffect."""
    speed_mult = 1.0
    damage_mult = 1.0
    miss_chance = 0.0
    defense_reduction = 0
    has_freeze = False
    has_curse = False
    has_blind = False

    if effects:
        for eff in effects:
            speed_mult *= eff.speed_mult
            damage_mult *= eff.damage_mult
            miss_chance = max(miss_chance, eff.miss_chance)
            defense_reduction += eff.defense_reduction
            if eff.name == 'freeze':
                has_freeze = True
            if eff.name == 'curse':
                has_curse = True
            if eff.name == 'blind':
                has_blind = True

    return {
        'speed_mult': speed_mult,
        'damage_mult': damage_mult,
        'miss_chance': miss_chance,
        'defense_reduction': defense_reduction,
        'has_freeze': has_freeze,
        'has_curse': has_curse,
        'has_blind': has_blind,
    }


def calculate_damage(attacker_str: int, base_damage: int, defender_def: int,
                     crit_chance: float = 0,
                     damage_type: str = 'physical',
                     attacker_effects: list | None = None,
                     defender_effects: list | None = None,
                     ) -> tuple[int, bool, bool]:
    """Calculate final damage, whether a critical hit occurred, and whether
    the attack missed.

    *damage_type* can be ``'physical'``, ``'magical'``, or ``'true'``
    (true damage ignores defense entirely).

    *attacker_effects* and *defender_effects* are optional lists of
    :class:`StatusEffect` instances currently active on each entity.

    Returns:
        ``(damage, is_crit, was_miss)``
    """
    atk_stats = _collect_effect_stats(attacker_effects)
    def_stats = _collect_effect_stats(defender_effects)

    # --- Miss check (attacker blind) ---
    if atk_stats['has_blind'] and random.random() < atk_stats['miss_chance']:
        return (0, False, True)

    # --- Base crit roll ---
    effective_crit = crit_chance + DIFFICULTY_BASE["crit_base_chance"]
    is_crit = random.random() < effective_crit

    # --- Raw damage ---
    raw = base_damage + attacker_str * 0.8

    # Attacker damage multiplier from status effects
    raw *= atk_stats['damage_mult']

    # --- Defense ---
    if damage_type == 'true':
        reduction = 0
    else:
        effective_def = max(0, defender_def - def_stats['defense_reduction'])
        reduction = effective_def * 0.5

    damage = max(1, int(raw - reduction))

    # --- Crit multiplier ---
    if is_crit:
        damage = int(damage * 1.75)

    # --- Frozen defender takes 50% more ---
    if def_stats['has_freeze']:
        damage = int(damage * 1.5)

    return (damage, is_crit, False)


# ---------------------------------------------------------------------------
# Loot Generation
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Loot system using LOOT_TABLES from config
# ---------------------------------------------------------------------------
_RARITY_ORDER = ("common", "uncommon", "rare", "epic", "legendary")
_RARITY_RANK = {r: i for i, r in enumerate(_RARITY_ORDER)}


def _get_phase(floor_num):
    """Return 'early', 'mid', or 'late' based on floor number."""
    if floor_num <= 2:
        return 'early'
    elif floor_num <= 4:
        return 'mid'
    return 'late'


def _pick_rarity_from_table(rarity_weights):
    """Pick a rarity using weighted table dict like {'common': 60, 'rare': 30, ...}."""
    rarities = list(rarity_weights.keys())
    weights = list(rarity_weights.values())
    return random.choices(rarities, weights=weights, k=1)[0]


def _make_item(rarity, equip_weight=0.5):
    """Create a random Item of the given rarity."""
    want_equip = random.random() < equip_weight

    if want_equip:
        type_filter = ("weapon", "armor", "accessory")
    else:
        type_filter = ("consumable",)

    candidates = [
        (name, data) for name, data in ITEM_DATA.items()
        if data["rarity"] == rarity and data["item_type"] in type_filter
    ]
    # Fallback: same rarity any type
    if not candidates:
        candidates = [
            (name, data) for name, data in ITEM_DATA.items()
            if data["rarity"] == rarity
        ]
    # Fallback: any item
    if not candidates:
        candidates = list(ITEM_DATA.items())

    name, data = random.choice(candidates)
    return Item(
        name=name,
        item_type=data["item_type"],
        stats=data["stats"],
        rarity=data["rarity"],
        description=data.get("description", ""),
    )


def generate_enemy_loot(floor_num, enemy_tier):
    """Generate loot dropped by a killed enemy based on tier and floor phase.

    Returns (gold_amount, item_or_None).
    Trash: mostly gold, rarely gear. Elite: often gear. Boss: guaranteed gear.
    """
    phase = _get_phase(floor_num)

    # Gold drop
    gold_range = GOLD_DROPS.get(enemy_tier, GOLD_DROPS['trash']).get(phase, (2, 6))
    gold = random.randint(gold_range[0], gold_range[1])

    # Item drop
    table = LOOT_TABLES.get(enemy_tier, LOOT_TABLES['trash']).get(phase)
    if table is None:
        return gold, None

    if random.random() > table['drop_chance']:
        return gold, None  # no item, just gold

    rarity = _pick_rarity_from_table(table['rarities'])

    # Trash drops mostly consumables, elites/bosses drop more gear
    if enemy_tier == 'trash':
        equip_weight = 0.2  # 20% chance of gear vs consumable
    elif enemy_tier == 'elite':
        equip_weight = 0.65
    else:  # boss
        equip_weight = 0.85

    item = _make_item(rarity, equip_weight)
    return gold, item


def generate_loot(floor_num, room_type):
    """Generate loot for room types (treasure, merchant, survival, hidden, etc.).

    Returns a list of Item instances.
    """
    phase = _get_phase(floor_num)

    # Room-type item counts
    _room_items = {
        'boss': (2, 4),
        'treasure': (2, 3),
        'hidden': (1, 3),
        'merchant': (3, 5),
        'survival': (1, 3),
    }
    min_items, max_items = _room_items.get(room_type, (1, 2))
    num_items = random.randint(min_items, max_items)

    # Get rarity table for this room type and phase
    table = LOOT_TABLES.get(room_type, LOOT_TABLES.get('treasure', {})).get(phase)
    if table is None:
        # Fallback
        table = {'drop_chance': 1.0, 'rarities': {'common': 50, 'uncommon': 30, 'rare': 15, 'epic': 5}}

    loot = []
    for _ in range(num_items):
        rarity = _pick_rarity_from_table(table['rarities'])
        equip_weight = 0.6 if room_type != 'merchant' else 0.7
        item = _make_item(rarity, equip_weight)
        loot.append(item)

    return loot


def get_sell_price(item):
    """Get the sell price for an item based on its rarity."""
    price_range = SELL_PRICES.get(item.rarity, (8, 12))
    base = random.randint(price_range[0], price_range[1])
    # Bonus for stat value
    stat_bonus = sum(abs(v) for v in item.stats.values() if isinstance(v, (int, float)))
    return base + int(stat_bonus * 0.5)


# ---------------------------------------------------------------------------
# Floating Damage Number
# ---------------------------------------------------------------------------
class DamageNumber:
    """A floating number (or text) that drifts upward and fades out."""

    FLOAT_SPEED = 40.0   # pixels per second upward
    LIFETIME = 1.0       # seconds

    def __init__(self, x: float, y: float, value, color: tuple):
        """*value* can be an int (damage amount) or a str like 'MISS!'."""
        self.x = x
        self.y = y
        self.value = value
        self.color = color
        self.timer = self.LIFETIME
        # Text labels float a bit slower and last longer
        if isinstance(value, str):
            self.timer = 1.4

    @property
    def text(self) -> str:
        """Return the display string."""
        if isinstance(self.value, str):
            return self.value
        return str(self.value)

    def update(self, dt: float) -> None:
        """Move upward and count down the timer."""
        self.y -= self.FLOAT_SPEED * dt
        self.timer -= dt

    def is_alive(self) -> bool:
        """Return True while the number should still be displayed."""
        return self.timer > 0

    def alpha(self) -> int:
        """Return 0..255 opacity based on remaining lifetime."""
        if self.timer <= 0:
            return 0
        base = self.LIFETIME if isinstance(self.value, int) else 1.4
        return max(0, min(255, int(255 * (self.timer / base))))

    def __repr__(self):
        return f"DamageNumber({self.value!r}, t={self.timer:.2f})"
