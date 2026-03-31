"""
config.py - Game constants, colors, class definitions, enemy stat tables,
ability data, item data, room types, floor configuration, and difficulty settings.
"""

# ---------------------------------------------------------------------------
# Display / Engine
# ---------------------------------------------------------------------------
SCREEN_W = 1024
SCREEN_H = 768
TILE_SIZE = 32
FPS = 60

# ---------------------------------------------------------------------------
# Colors  (R, G, B)
# ---------------------------------------------------------------------------
COLORS = {
    # UI
    "background":       (10, 10, 15),
    "ui_panel":         (30, 30, 40),
    "ui_border":        (80, 80, 100),
    "ui_text":          (220, 220, 220),
    "ui_highlight":     (255, 215, 0),
    "hp_bar":           (200, 30, 30),
    "mp_bar":           (30, 80, 200),
    "xp_bar":           (80, 200, 80),
    "hp_bar_bg":        (60, 10, 10),
    "mp_bar_bg":        (10, 20, 60),
    "xp_bar_bg":        (20, 60, 20),
    "minimap_bg":       (20, 20, 30),
    "minimap_visited":  (60, 60, 80),
    "minimap_current":  (255, 255, 100),
    "tooltip_bg":       (20, 20, 30),
    "tooltip_border":   (120, 120, 150),

    # Entities
    "player":           (0, 200, 255),
    "warrior":          (200, 50, 50),
    "mage":             (100, 50, 220),
    "rogue":            (50, 200, 50),
    "healer":           (255, 200, 50),

    # Enemies - Trash
    "goblin":           (50, 180, 50),
    "skeleton":         (200, 200, 180),
    "slime":            (80, 200, 80),
    "wolf":             (130, 100, 70),
    "bug":              (160, 120, 40),
    "undead_soldier":   (100, 100, 140),

    # Enemies - Elite
    "assassin":         (80, 0, 80),
    "shaman":           (0, 150, 100),
    "elite_knight":     (180, 180, 200),
    "ogre":             (140, 100, 60),
    "cursed_priest":    (120, 0, 120),
    "enemy_mage":       (60, 60, 200),

    # Enemies - Boss
    "giant_beast":      (180, 60, 20),
    "fallen_hero":      (150, 150, 170),
    "corrupted_king":   (200, 0, 0),
    "dungeon_guardian":  (220, 180, 50),
    "floor_admin":      (255, 80, 80),
    "dragon":           (255, 50, 0),

    # Environment
    "wall":             (50, 50, 60),
    "floor":            (35, 35, 45),
    "door":             (140, 100, 50),
    "chest":            (200, 170, 50),
    "trap":             (180, 40, 40),
    "stairs":           (100, 200, 255),
    "water":            (30, 60, 140),
    "lava":             (220, 80, 20),

    # Rarity
    "common":           (180, 180, 180),
    "uncommon":         (30, 200, 30),
    "rare":             (30, 100, 255),
    "epic":             (180, 50, 255),
    "legendary":        (255, 165, 0),

    # Effects
    "damage":           (255, 60, 60),
    "heal":             (60, 255, 60),
    "crit":             (255, 255, 0),
    "poison":           (100, 200, 0),
    "freeze":           (100, 200, 255),
    "stun":             (255, 255, 100),
    "shield":           (150, 150, 255),

    # Projectiles
    "projectile_fire":  (255, 120, 20),
    "projectile_ice":   (100, 180, 255),
    "projectile_arrow": (200, 180, 100),
    "projectile_magic": (180, 80, 255),
}

# ---------------------------------------------------------------------------
# Player Classes
# ---------------------------------------------------------------------------
PLAYER_CLASSES = {
    "warrior": {
        "hp": 200,
        "mp": 40,
        "str": 20,
        "defense": 18,
        "spd": 8,
        "abilities": [
            "slash",
            "shield_wall",
            "knockback_slam",
            "war_cry",
            "leap",
        ],
    },
    "mage": {
        "hp": 90,
        "mp": 150,
        "str": 8,
        "defense": 6,
        "spd": 9,
        "abilities": [
            "fireball",
            "lightning_bolt",
            "freeze_blast",
            "blink",
            "meteor",
        ],
    },
    "rogue": {
        "hp": 110,
        "mp": 60,
        "str": 15,
        "defense": 8,
        "spd": 14,
        "abilities": [
            "backstab",
            "poison_strike",
            "dash",
            "smoke_bomb",
            "blade_flurry",
        ],
    },
    "healer": {
        "hp": 120,
        "mp": 130,
        "str": 10,
        "defense": 12,
        "spd": 10,
        "abilities": [
            "heal",
            "holy_light",
            "purify",
            "divine_shield",
            "resurrection",
        ],
    },
}

# ---------------------------------------------------------------------------
# Enemy Data
# ---------------------------------------------------------------------------
ENEMY_DATA = {
    # --- Trash tier ---
    "goblin": {
        "hp": 30,
        "str": 6,
        "defense": 3,
        "spd": 10,
        "xp": 10,
        "tier": "trash",
        "color": COLORS["goblin"],
        "behavior": "swarm",
        "size": 20,
    },
    "skeleton": {
        "hp": 50, "str": 8, "defense": 4, "spd": 7, "xp": 12,
        "tier": "trash", "color": COLORS["skeleton"], "behavior": "aggressive", "size": 24,
    },
    "slime": {
        "hp": 40, "str": 4, "defense": 2, "spd": 5, "xp": 8,
        "tier": "trash", "color": COLORS["slime"], "behavior": "slow_chase", "size": 22,
    },
    "wolf": {
        "hp": 35, "str": 10, "defense": 3, "spd": 14, "xp": 14,
        "tier": "trash", "color": COLORS["wolf"], "behavior": "pack", "size": 22,
    },
    "bug": {
        "hp": 20, "str": 5, "defense": 1, "spd": 12, "xp": 6,
        "tier": "trash", "color": COLORS["bug"], "behavior": "erratic", "size": 16,
    },
    "undead_soldier": {
        "hp": 60, "str": 9, "defense": 6, "spd": 6, "xp": 16,
        "tier": "trash", "color": COLORS["undead_soldier"], "behavior": "aggressive", "size": 26,
    },

    # --- Elite tier ---
    "assassin": {
        "hp": 80, "str": 18, "defense": 6, "spd": 16, "xp": 50,
        "tier": "elite", "color": COLORS["assassin"], "behavior": "stealth", "size": 24,
    },
    "shaman": {
        "hp": 70, "str": 14, "defense": 5, "spd": 9, "xp": 45,
        "tier": "elite", "color": COLORS["shaman"], "behavior": "support", "size": 24,
    },
    "elite_knight": {
        "hp": 150, "str": 16, "defense": 14, "spd": 7, "xp": 55,
        "tier": "elite", "color": COLORS["elite_knight"], "behavior": "tank", "size": 30,
    },
    "ogre": {
        "hp": 200, "str": 20, "defense": 10, "spd": 5, "xp": 60,
        "tier": "elite", "color": COLORS["ogre"], "behavior": "brute", "size": 36,
    },
    "cursed_priest": {
        "hp": 90, "str": 12, "defense": 7, "spd": 8, "xp": 48,
        "tier": "elite", "color": COLORS["cursed_priest"], "behavior": "debuffer", "size": 24,
    },
    "dark_mage": {
        "hp": 75, "str": 22, "defense": 4, "spd": 10, "xp": 52,
        "tier": "elite", "color": COLORS["enemy_mage"], "behavior": "ranged_teleport", "size": 24,
    },

    # --- Boss tier ---
    "giant_beast": {
        "hp": 500, "str": 28, "defense": 12, "spd": 6, "xp": 200,
        "tier": "boss", "color": COLORS["giant_beast"], "behavior": "boss", "size": 48,
    },
    "fallen_hero": {
        "hp": 400, "str": 24, "defense": 16, "spd": 12, "xp": 250,
        "tier": "boss", "color": COLORS["fallen_hero"], "behavior": "boss", "size": 40,
    },
    "corrupted_king": {
        "hp": 600, "str": 30, "defense": 18, "spd": 8, "xp": 350,
        "tier": "boss", "color": COLORS["corrupted_king"], "behavior": "boss", "size": 44,
    },
    "dungeon_guardian": {
        "hp": 550, "str": 26, "defense": 22, "spd": 7, "xp": 400,
        "tier": "boss", "color": COLORS["dungeon_guardian"], "behavior": "boss", "size": 50,
    },
    "floor_admin": {
        "hp": 450, "str": 32, "defense": 14, "spd": 14, "xp": 300,
        "tier": "boss", "color": COLORS["floor_admin"], "behavior": "boss", "size": 42,
    },
    "dragon": {
        "hp": 700, "str": 40, "defense": 20, "spd": 10, "xp": 500,
        "tier": "boss", "color": COLORS["dragon"], "behavior": "boss", "size": 52,
    },
}

# ---------------------------------------------------------------------------
# Ability Data
# ---------------------------------------------------------------------------
ABILITY_DATA = {
    # Damage
    "slash": {
        "type": "damage",
        "mp_cost": 0,
        "cooldown": 0.5,
        "damage": 12,
        "range": 48,
        "effect": None,
        "description": "A quick melee slash.",
    },
    "fireball": {
        "type": "damage",
        "mp_cost": 15,
        "cooldown": 2.0,
        "damage": 35,
        "range": 256,
        "effect": "burn",
        "description": "Launches an explosive fireball that burns on impact.",
    },
    "lightning_bolt": {
        "type": "damage",
        "mp_cost": 20,
        "cooldown": 3.0,
        "damage": 45,
        "range": 320,
        "effect": "stun",
        "description": "A bolt of lightning that can stun the target.",
    },
    "poison_strike": {
        "type": "damage",
        "mp_cost": 8,
        "cooldown": 1.5,
        "damage": 10,
        "range": 48,
        "effect": "poison",
        "description": "Melee strike that poisons the target over time.",
    },
    "backstab": {
        "type": "damage",
        "mp_cost": 12,
        "cooldown": 2.5,
        "damage": 40,
        "range": 48,
        "effect": "crit_boost",
        "description": "High-damage strike with guaranteed critical from behind.",
    },

    # Control
    "stun_strike": {
        "type": "control",
        "mp_cost": 10,
        "cooldown": 4.0,
        "damage": 8,
        "range": 48,
        "effect": "stun",
        "description": "A heavy blow that stuns the target for 2 seconds.",
    },
    "freeze_blast": {
        "type": "control",
        "mp_cost": 18,
        "cooldown": 5.0,
        "damage": 15,
        "range": 192,
        "effect": "freeze",
        "description": "Freezes enemies in an area, slowing them drastically.",
    },
    "knockback_slam": {
        "type": "control",
        "mp_cost": 14,
        "cooldown": 3.5,
        "damage": 18,
        "range": 64,
        "effect": "knockback",
        "description": "Slams the ground, knocking back nearby enemies.",
    },
    "silence_arrow": {
        "type": "control",
        "mp_cost": 10,
        "cooldown": 6.0,
        "damage": 8,
        "range": 288,
        "effect": "silence",
        "description": "Fires an arrow that silences the target, preventing abilities.",
    },

    # Mobility
    "dash": {
        "type": "mobility",
        "mp_cost": 5,
        "cooldown": 1.5,
        "damage": 0,
        "range": 128,
        "effect": "invulnerable_frames",
        "description": "Quick dash in the current direction with brief invulnerability.",
    },
    "blink": {
        "type": "mobility",
        "mp_cost": 15,
        "cooldown": 4.0,
        "damage": 0,
        "range": 192,
        "effect": "teleport",
        "description": "Instantly teleport to the target location.",
    },
    "leap": {
        "type": "mobility",
        "mp_cost": 8,
        "cooldown": 3.0,
        "damage": 10,
        "range": 160,
        "effect": "aoe_land",
        "description": "Leap to a location, dealing damage on landing.",
    },

    # Warrior extras
    "war_cry": {
        "type": "control",
        "mp_cost": 15,
        "cooldown": 15.0,
        "damage": 0,
        "range": 200,
        "effect": "taunt",
        "description": "Taunt all nearby enemies and gain +30% STR for 5s.",
    },
    "meteor": {
        "type": "damage",
        "mp_cost": 40,
        "cooldown": 20.0,
        "damage": 80,
        "range": 400,
        "effect": "burn",
        "description": "After 1s delay, massive AoE impact dealing huge damage.",
    },
    "smoke_bomb": {
        "type": "control",
        "mp_cost": 20,
        "cooldown": 12.0,
        "damage": 0,
        "range": 100,
        "effect": "blind",
        "description": "Blinds and slows enemies in area. Grants stealth for 3s.",
    },
    "blade_flurry": {
        "type": "damage",
        "mp_cost": 25,
        "cooldown": 8.0,
        "damage": 15,
        "range": 70,
        "effect": None,
        "description": "5 rapid strikes, each dealing 60% damage. Shreds groups.",
    },
    "holy_light": {
        "type": "damage",
        "mp_cost": 15,
        "cooldown": 3.0,
        "damage": 25,
        "range": 300,
        "effect": None,
        "description": "Light projectile. 2x damage to undead, heals player 20 on hit.",
    },
    "purify": {
        "type": "survival",
        "mp_cost": 15,
        "cooldown": 8.0,
        "damage": 0,
        "range": 0,
        "effect": "cleanse",
        "description": "Remove all negative status effects and heal 20 HP.",
    },
    "divine_shield": {
        "type": "survival",
        "mp_cost": 30,
        "cooldown": 15.0,
        "damage": 0,
        "range": 300,
        "effect": "shield_zone",
        "description": "Place a holy barrier that blocks projectiles and heals inside.",
    },
    "resurrection": {
        "type": "survival",
        "mp_cost": 50,
        "cooldown": 60.0,
        "damage": 0,
        "range": 0,
        "effect": "revive",
        "description": "Passive: auto-revive at 30% HP when killed. 60s cooldown.",
    },

    # Survival
    "shield_wall": {
        "type": "survival",
        "mp_cost": 15,
        "cooldown": 12.0,
        "damage": 0,
        "range": 0,
        "effect": "damage_reduction",
        "description": "80% damage reduction for 3 seconds. Stand your ground.",
    },
    "heal": {
        "type": "survival",
        "mp_cost": 20,
        "cooldown": 4.0,
        "damage": -60,
        "range": 0,
        "effect": "restore_hp",
        "description": "Instantly restore 60 HP.",
    },
    "lifesteal_strike": {
        "type": "survival",
        "mp_cost": 14,
        "cooldown": 3.0,
        "damage": 15,
        "range": 48,
        "effect": "lifesteal",
        "description": "Melee strike that heals for 50% of damage dealt.",
    },

    # Utility
    "trap_sense": {
        "type": "utility",
        "mp_cost": 5,
        "cooldown": 10.0,
        "damage": 0,
        "range": 192,
        "effect": "reveal_traps",
        "description": "Reveals all traps within a wide radius for 10 seconds.",
    },
    "enemy_scan": {
        "type": "utility",
        "mp_cost": 8,
        "cooldown": 12.0,
        "damage": 0,
        "range": 256,
        "effect": "reveal_stats",
        "description": "Reveals the stats and weaknesses of enemies in range.",
    },
}

# ---------------------------------------------------------------------------
# Item Data
# ---------------------------------------------------------------------------
ITEM_DATA = {
    # Weapons
    "iron_sword": {
        "item_type": "weapon",
        "stats": {"str": 5},
        "rarity": "common",
        "description": "A basic iron sword.",
    },
    "steel_longsword": {
        "item_type": "weapon",
        "stats": {"str": 10, "spd": -1},
        "rarity": "uncommon",
        "description": "A sturdy steel longsword.",
    },
    "shadow_dagger": {
        "item_type": "weapon",
        "stats": {"str": 7, "spd": 4, "crit": 10},
        "rarity": "rare",
        "description": "A dagger that strikes from the shadows.",
    },
    "arcane_staff": {
        "item_type": "weapon",
        "stats": {"str": 3, "mp_bonus": 30},
        "rarity": "uncommon",
        "description": "A staff humming with arcane energy.",
    },
    "flame_blade": {
        "item_type": "weapon",
        "stats": {"str": 14, "burn_chance": 15},
        "rarity": "epic",
        "description": "A blade wreathed in eternal flame.",
    },
    "dragonslayer": {
        "item_type": "weapon",
        "stats": {"str": 22, "crit": 8, "bonus_vs_boss": 20},
        "rarity": "legendary",
        "description": "Forged to slay the mightiest beasts.",
    },
    "crystal_wand": {
        "item_type": "weapon",
        "stats": {"str": 6, "mp_bonus": 50, "spell_power": 15},
        "rarity": "epic",
        "description": "A wand carved from a single crystal shard.",
    },

    # Armor
    "leather_vest": {
        "item_type": "armor",
        "stats": {"defense": 3},
        "rarity": "common",
        "description": "Simple leather protection.",
    },
    "chainmail": {
        "item_type": "armor",
        "stats": {"defense": 7, "spd": -2},
        "rarity": "uncommon",
        "description": "Interlocking steel rings offer solid defense.",
    },
    "shadow_cloak": {
        "item_type": "armor",
        "stats": {"defense": 4, "spd": 3, "dodge": 10},
        "rarity": "rare",
        "description": "A cloak that bends light around the wearer.",
    },
    "plate_armor": {
        "item_type": "armor",
        "stats": {"defense": 14, "spd": -4},
        "rarity": "epic",
        "description": "Heavy plate armor offering supreme protection.",
    },
    "dragon_scale_mail": {
        "item_type": "armor",
        "stats": {"defense": 18, "hp_bonus": 30, "fire_resist": 50},
        "rarity": "legendary",
        "description": "Armor forged from shed dragon scales.",
    },
    "mage_robes": {
        "item_type": "armor",
        "stats": {"defense": 2, "mp_bonus": 20, "spell_power": 8},
        "rarity": "uncommon",
        "description": "Enchanted robes favoured by spellcasters.",
    },

    # Consumables
    "health_potion": {
        "item_type": "consumable",
        "stats": {"restore_hp": 40},
        "rarity": "common",
        "description": "Restores 40 HP.",
    },
    "mana_potion": {
        "item_type": "consumable",
        "stats": {"restore_mp": 30},
        "rarity": "common",
        "description": "Restores 30 MP.",
    },
    "greater_health_potion": {
        "item_type": "consumable",
        "stats": {"restore_hp": 100},
        "rarity": "uncommon",
        "description": "Restores 100 HP.",
    },
    "elixir_of_might": {
        "item_type": "consumable",
        "stats": {"buff_str": 5, "buff_duration": 30},
        "rarity": "rare",
        "description": "Temporarily boosts strength by 5.",
    },
    "scroll_of_fireball": {
        "item_type": "consumable",
        "stats": {"cast_ability": "fireball"},
        "rarity": "rare",
        "description": "Casts Fireball without using MP.",
    },
    "antidote": {
        "item_type": "consumable",
        "stats": {"cure": "poison"},
        "rarity": "common",
        "description": "Cures poison.",
    },

    # Accessories
    "iron_ring": {
        "item_type": "accessory",
        "stats": {"defense": 2},
        "rarity": "common",
        "description": "A plain iron ring.",
    },
    "amulet_of_speed": {
        "item_type": "accessory",
        "stats": {"spd": 5},
        "rarity": "uncommon",
        "description": "An amulet that quickens the wearer.",
    },
    "ring_of_power": {
        "item_type": "accessory",
        "stats": {"str": 6, "crit": 5},
        "rarity": "rare",
        "description": "A ring pulsing with raw power.",
    },
    "pendant_of_life": {
        "item_type": "accessory",
        "stats": {"hp_bonus": 40, "hp_regen": 2},
        "rarity": "epic",
        "description": "Grants vitality and slow regeneration.",
    },
    "crown_of_the_abyss": {
        "item_type": "accessory",
        "stats": {"str": 10, "defense": 8, "spd": 4, "mp_bonus": 20},
        "rarity": "legendary",
        "description": "A crown whispered to hold the dungeon's will.",
    },
}

# ---------------------------------------------------------------------------
# Room Types
# ---------------------------------------------------------------------------
ROOM_TYPES = [
    "start",
    "combat",
    "elite_combat",
    "boss",
    "treasure",
    "shop",
    "rest",
    "trap",
    "puzzle",
    "secret",
    "corridor",
    "arena",
]

# ---------------------------------------------------------------------------
# Floor Configuration
# ---------------------------------------------------------------------------
FLOOR_CONFIG = {
    "rooms_per_floor": 8,
    "rooms_per_floor_min": 6,
    "rooms_per_floor_max": 12,
    "enemy_hp_scale": 1.15,        # multiplier per floor
    "enemy_str_scale": 1.10,
    "enemy_def_scale": 1.08,
    "enemy_xp_scale": 1.12,
    "trash_per_room_min": 1,
    "trash_per_room_max": 4,
    "elite_chance_base": 0.15,     # 15% base chance for elite per room
    "elite_chance_per_floor": 0.03,
    "boss_floor_interval": 5,      # boss every 5 floors
    "loot_quality_per_floor": 0.05,
    "max_floors": 50,
}

# ---------------------------------------------------------------------------
# Difficulty Base Settings
# ---------------------------------------------------------------------------
DIFFICULTY_BASE = {
    "player_hp_scale": 1.0,
    "player_damage_scale": 1.0,
    "enemy_hp_scale": 1.0,
    "enemy_damage_scale": 1.0,
    "xp_multiplier": 1.0,
    "loot_drop_rate": 0.35,
    "potion_effectiveness": 1.0,
    "respawn_penalty_xp": 0.10,    # lose 10% of current XP on death
    "crit_base_chance": 0.05,
    "dodge_base_chance": 0.03,
}

# ---------------------------------------------------------------------------
# Status Effects
# ---------------------------------------------------------------------------
STATUS_EFFECTS = {
    "burn": {
        "damage_per_sec": 5,
        "speed_mult": 1.0,
        "damage_mult": 1.0,
        "miss_chance": 0.0,
        "defense_reduction": 0,
        "color": (255, 120, 20),
    },
    "poison": {
        "damage_per_sec": 3,
        "speed_mult": 0.9,
        "damage_mult": 1.0,
        "miss_chance": 0.0,
        "defense_reduction": 0,
        "color": (100, 200, 0),
    },
    "freeze": {
        "damage_per_sec": 0,
        "speed_mult": 0.2,
        "damage_mult": 1.0,
        "miss_chance": 0.0,
        "defense_reduction": 0,
        "color": (100, 200, 255),
    },
    "stun": {
        "damage_per_sec": 0,
        "speed_mult": 0.0,
        "damage_mult": 1.0,
        "miss_chance": 0.0,
        "defense_reduction": 0,
        "color": (255, 255, 100),
    },
    "blind": {
        "damage_per_sec": 0,
        "speed_mult": 0.7,
        "damage_mult": 0.8,
        "miss_chance": 0.5,
        "defense_reduction": 0,
        "color": (80, 80, 80),
    },
    "curse": {
        "damage_per_sec": 2,
        "speed_mult": 0.85,
        "damage_mult": 1.0,
        "miss_chance": 0.0,
        "defense_reduction": 8,
        "color": (120, 0, 120),
    },
    "silence": {
        "damage_per_sec": 0,
        "speed_mult": 1.0,
        "damage_mult": 1.0,
        "miss_chance": 0.0,
        "defense_reduction": 0,
        "color": (150, 150, 180),
    },
    "slow": {
        "damage_per_sec": 0,
        "speed_mult": 0.5,
        "damage_mult": 1.0,
        "miss_chance": 0.0,
        "defense_reduction": 0,
        "color": (80, 80, 200),
    },
    "weaken": {
        "damage_per_sec": 0,
        "speed_mult": 1.0,
        "damage_mult": 0.6,
        "miss_chance": 0.0,
        "defense_reduction": 4,
        "color": (180, 100, 100),
    },
}

# ---------------------------------------------------------------------------
# Floor Progression System - Enemy pools, compositions, and scaling
# ---------------------------------------------------------------------------
# 6 floors total: Early (1-2), Mid (3-4), Late (5-6)

# Which enemies can appear on each floor
FLOOR_ENEMY_POOLS = {
    1: {
        'trash': ['goblin', 'skeleton', 'slime'],
        'elite': [],  # no elites floor 1
        'boss': [],   # floor 1 ends with survival waves, not a boss
    },
    2: {
        'trash': ['goblin', 'skeleton', 'slime', 'wolf', 'bug', 'undead_soldier'],
        'elite': ['shaman'],  # first support elite teaches target priority
        'boss': ['giant_beast'],  # first real boss, enrage = simplest
    },
    3: {
        'trash': ['goblin', 'skeleton', 'slime', 'wolf', 'bug', 'undead_soldier'],
        'elite': ['shaman', 'assassin', 'elite_knight'],
        'boss': [],   # floor 3 ends with puzzle gate + elite formation
    },
    4: {
        'trash': ['skeleton', 'wolf', 'bug', 'undead_soldier'],
        'elite': ['assassin', 'elite_knight', 'ogre', 'cursed_priest', 'dark_mage'],
        'boss': ['corrupted_king'],  # summoner boss
    },
    5: {
        'trash': ['wolf', 'bug', 'undead_soldier', 'skeleton'],
        'elite': ['elite_knight', 'ogre', 'cursed_priest', 'dark_mage', 'assassin'],
        'boss': [],   # floor 5 ends with trap gauntlet escape
    },
    6: {
        'trash': ['undead_soldier', 'wolf', 'skeleton', 'bug'],
        'elite': ['dark_mage', 'cursed_priest', 'assassin', 'elite_knight', 'ogre'],
        'boss': ['dragon'],  # dragon final boss
    },
}

# Floor exit types: how each floor ends
# 'boss' = standard boss fight, 'survival' = survive 3 waves,
# 'trap_gauntlet' = get through trap room to reach stairs,
# 'puzzle_gate' = solve puzzle to unlock exit, 'elite_formation' = clear elite squad
FLOOR_EXIT_TYPE = {
    1: 'survival',          # intro: survive waves to prove you can handle pressure
    2: 'boss',              # first boss: Giant Beast teaches enrage reading
    3: 'elite_formation',   # no boss: clear a squad of elites working together
    4: 'boss',              # Corrupted King: summoner boss
    5: 'trap_gauntlet',     # no boss: navigate deadly trap room to escape
    6: 'boss',              # Dragon: final boss, the real test
}

# Room enemy composition templates - what mix of enemies goes in each room type
# Each template is (count_min, count_max, composition_type)
ROOM_COMPOSITIONS = {
    # --- MOB ROOMS ---
    # Early: simple groups, one type at a time to teach
    'mob_early': [
        {'weight': 30, 'trash': [('goblin', 3, 4)], 'label': 'goblin_swarm'},
        {'weight': 25, 'trash': [('skeleton', 2, 3)], 'label': 'skeleton_patrol'},
        {'weight': 20, 'trash': [('slime', 2, 3)], 'label': 'slime_pit'},
        {'weight': 15, 'trash': [('goblin', 2, 2), ('skeleton', 1, 1)], 'label': 'mixed_basic'},
        {'weight': 10, 'trash': [('slime', 1, 2), ('goblin', 1, 2)], 'label': 'slime_goblins'},
    ],
    # Mid: synergy combinations
    'mob_mid': [
        {'weight': 20, 'trash': [('wolf', 2, 3), ('skeleton', 1, 2)], 'label': 'wolf_pack'},
        {'weight': 20, 'trash': [('undead_soldier', 2, 2), ('bug', 2, 3)], 'label': 'soldier_bugs'},
        {'weight': 15, 'trash': [('goblin', 3, 4), ('wolf', 1, 2)], 'label': 'goblin_wolves'},
        {'weight': 15, 'trash': [('skeleton', 2, 3), ('undead_soldier', 1, 2)], 'label': 'undead_line'},
        {'weight': 15, 'trash': [('wolf', 2, 3), ('bug', 2, 2)], 'label': 'fast_pack'},
        {'weight': 15, 'trash': [('slime', 2, 3), ('undead_soldier', 1, 2)], 'label': 'hazard_wall'},
    ],
    # Late: dangerous combos, trash supports the real threats
    'mob_late': [
        {'weight': 20, 'trash': [('undead_soldier', 2, 3), ('wolf', 2, 3)], 'label': 'frontline_flank'},
        {'weight': 20, 'trash': [('skeleton', 2, 3), ('bug', 3, 4)], 'label': 'swarm_pressure'},
        {'weight': 20, 'trash': [('wolf', 3, 4), ('undead_soldier', 1, 2)], 'label': 'wolf_wall'},
        {'weight': 20, 'trash': [('bug', 2, 3), ('undead_soldier', 2, 2), ('skeleton', 1, 2)], 'label': 'full_mix'},
        {'weight': 20, 'trash': [('wolf', 2, 2), ('skeleton', 2, 3), ('bug', 1, 2)], 'label': 'chaos_pack'},
    ],
    # --- ELITE ROOMS - elite + supporting trash ---
    'elite_early': [
        {'weight': 100, 'elite': 'shaman', 'trash': [('goblin', 2, 3)], 'label': 'shaman_goblins'},
    ],
    'elite_mid': [
        {'weight': 20, 'elite': 'assassin', 'trash': [('goblin', 2, 2)], 'label': 'assassin_ambush'},
        {'weight': 20, 'elite': 'elite_knight', 'trash': [('skeleton', 2, 3)], 'label': 'knight_guard'},
        {'weight': 20, 'elite': 'ogre', 'trash': [('bug', 2, 3)], 'label': 'ogre_swarm'},
        {'weight': 20, 'elite': 'cursed_priest', 'trash': [('undead_soldier', 1, 2)], 'label': 'priest_undead'},
        {'weight': 20, 'elite': 'dark_mage', 'trash': [('wolf', 1, 2)], 'label': 'mage_wolves'},
    ],
    'elite_late': [
        {'weight': 15, 'elite': 'dark_mage', 'trash': [('undead_soldier', 2, 3)], 'label': 'mage_wall'},
        {'weight': 15, 'elite': 'assassin', 'trash': [('wolf', 2, 3)], 'label': 'assassin_wolves'},
        {'weight': 15, 'elite': 'elite_knight', 'trash': [('undead_soldier', 2, 2), ('skeleton', 1, 2)], 'label': 'knight_army'},
        {'weight': 15, 'elite': 'cursed_priest', 'trash': [('wolf', 2, 2), ('bug', 1, 2)], 'label': 'cursed_pack'},
        {'weight': 20, 'elite': 'ogre', 'trash': [('undead_soldier', 1, 2), ('skeleton', 2, 2)], 'label': 'ogre_legion'},
        {'weight': 20, 'elite': 'dark_mage', 'trash': [('skeleton', 2, 3), ('bug', 1, 2)], 'label': 'mage_horde'},
    ],
}

# Per-floor stat scaling curves
# The design: early enemies are easy (2-4 hits to kill trash), mid enemies take longer,
# late enemies hit hard but don't become HP sponges
FLOOR_SCALING = {
    # floor: (hp_mult, str_mult, def_mult, speed_mult, aggro_mult)
    # HP mult controls how many hits enemies take
    # STR mult controls how much they hurt
    # Speed mult controls how fast they move
    # Aggro mult scales detection range
    1: {'hp': 0.8,  'str': 0.7,  'def': 0.6,  'spd': 0.70, 'aggro': 0.7,  'atk_cd': 1.4},
    2: {'hp': 1.0,  'str': 0.85, 'def': 0.8,  'spd': 0.80, 'aggro': 0.85, 'atk_cd': 1.2},
    3: {'hp': 1.2,  'str': 1.0,  'def': 1.0,  'spd': 0.90, 'aggro': 1.0,  'atk_cd': 1.0},
    4: {'hp': 1.4,  'str': 1.15, 'def': 1.1,  'spd': 0.95, 'aggro': 1.1,  'atk_cd': 0.9},
    5: {'hp': 1.6,  'str': 1.3,  'def': 1.2,  'spd': 1.0,  'aggro': 1.15, 'atk_cd': 0.85},
    6: {'hp': 1.8,  'str': 1.5,  'def': 1.3,  'spd': 1.05, 'aggro': 1.2,  'atk_cd': 0.80},
}

# Boss-specific scaling - bosses are deliberately slower and more readable early
BOSS_SCALING = {
    1: {'hp': 0.7,  'str': 0.6,  'spd': 0.50, 'atk_cd': 1.6},  # very slow, very readable
    2: {'hp': 0.85, 'str': 0.75, 'spd': 0.60, 'atk_cd': 1.4},
    3: {'hp': 1.0,  'str': 0.9,  'spd': 0.70, 'atk_cd': 1.2},
    4: {'hp': 1.2,  'str': 1.05, 'spd': 0.80, 'atk_cd': 1.0},
    5: {'hp': 1.5,  'str': 1.25, 'spd': 0.90, 'atk_cd': 0.85},
    6: {'hp': 1.8,  'str': 1.5,  'spd': 1.0,  'atk_cd': 0.75},
}

# Room type weights per floor tier (overrides the flat weights)
FLOOR_ROOM_WEIGHTS = {
    'early': {  # floors 1-2
        'mob': 0.40, 'trap': 0.05, 'puzzle': 0.08, 'elite': 0.05,
        'survival': 0.05, 'treasure': 0.15, 'merchant': 0.12, 'hidden': 0.03,
    },
    'mid': {  # floors 3-4
        'mob': 0.30, 'trap': 0.10, 'puzzle': 0.08, 'elite': 0.18,
        'survival': 0.08, 'treasure': 0.10, 'merchant': 0.08, 'hidden': 0.05,
    },
    'late': {  # floors 5-6
        'mob': 0.25, 'trap': 0.12, 'puzzle': 0.05, 'elite': 0.22,
        'survival': 0.10, 'treasure': 0.08, 'merchant': 0.08, 'hidden': 0.07,
    },
}

# ---------------------------------------------------------------------------
# Loot Drop Tables - per tier per game phase
# ---------------------------------------------------------------------------
# Each entry: drop_chance (0-1), rarity_weights {rarity: weight}
LOOT_TABLES = {
    'trash': {
        # Trash enemies rarely drop items - gold is their main reward
        'early':  {'drop_chance': 0.08, 'rarities': {'common': 90, 'uncommon': 10}},
        'mid':    {'drop_chance': 0.12, 'rarities': {'common': 70, 'uncommon': 25, 'rare': 5}},
        'late':   {'drop_chance': 0.15, 'rarities': {'common': 50, 'uncommon': 35, 'rare': 13, 'epic': 2}},
    },
    'elite': {
        # Elites are the reliable loot source - killing one should feel rewarding
        'early':  {'drop_chance': 0.55, 'rarities': {'common': 40, 'uncommon': 40, 'rare': 18, 'epic': 2}},
        'mid':    {'drop_chance': 0.70, 'rarities': {'common': 15, 'uncommon': 35, 'rare': 35, 'epic': 13, 'legendary': 2}},
        'late':   {'drop_chance': 0.85, 'rarities': {'uncommon': 20, 'rare': 35, 'epic': 35, 'legendary': 10}},
    },
    'boss': {
        # Bosses are guaranteed meaningful loot - the big payoff
        'early':  {'drop_chance': 1.00, 'rarities': {'uncommon': 30, 'rare': 50, 'epic': 18, 'legendary': 2}},
        'mid':    {'drop_chance': 1.00, 'rarities': {'rare': 35, 'epic': 45, 'legendary': 20}},
        'late':   {'drop_chance': 1.00, 'rarities': {'rare': 20, 'epic': 45, 'legendary': 35}},
    },
    # Special room types
    'treasure': {
        'early':  {'drop_chance': 1.00, 'rarities': {'common': 30, 'uncommon': 45, 'rare': 20, 'epic': 5}},
        'mid':    {'drop_chance': 1.00, 'rarities': {'uncommon': 30, 'rare': 40, 'epic': 25, 'legendary': 5}},
        'late':   {'drop_chance': 1.00, 'rarities': {'rare': 30, 'epic': 45, 'legendary': 25}},
    },
    'merchant': {
        'early':  {'drop_chance': 1.00, 'rarities': {'common': 40, 'uncommon': 40, 'rare': 18, 'epic': 2}},
        'mid':    {'drop_chance': 1.00, 'rarities': {'uncommon': 30, 'rare': 40, 'epic': 25, 'legendary': 5}},
        'late':   {'drop_chance': 1.00, 'rarities': {'rare': 25, 'epic': 45, 'legendary': 30}},
    },
    'survival': {
        'early':  {'drop_chance': 1.00, 'rarities': {'uncommon': 40, 'rare': 40, 'epic': 18, 'legendary': 2}},
        'mid':    {'drop_chance': 1.00, 'rarities': {'rare': 35, 'epic': 45, 'legendary': 20}},
        'late':   {'drop_chance': 1.00, 'rarities': {'rare': 20, 'epic': 50, 'legendary': 30}},
    },
}

# Gold drops by tier and game phase
GOLD_DROPS = {
    'trash':  {'early': (2, 6),   'mid': (5, 10),  'late': (8, 15)},
    'elite':  {'early': (10, 20), 'mid': (18, 35),  'late': (30, 60)},
    'boss':   {'early': (30, 50), 'mid': (50, 80),  'late': (80, 140)},
}

# Sell prices by rarity (range)
SELL_PRICES = {
    'common':    (8, 12),
    'uncommon':  (20, 30),
    'rare':      (45, 60),
    'epic':      (90, 120),
    'legendary': (180, 240),
}

# ---------------------------------------------------------------------------
# Trap Room Templates
# ---------------------------------------------------------------------------
TRAP_TEMPLATES = {
    'arrow_hall': {
        'description': 'Cross during the arrow gaps',
        'hazard_type': 'arrow',
        'pattern': 'lanes',        # lanes fire in alternating pattern
        'damage': 15,
        'cycle_time': 2.0,        # seconds per pattern cycle
        'safe_window': 0.8,        # seconds of safe gap
    },
    'poison_vent': {
        'description': 'Survive while poison rotates around the room',
        'hazard_type': 'poison',
        'pattern': 'rotating',     # safe area rotates clockwise
        'damage': 8,
        'tick_rate': 0.5,          # damage every 0.5s while standing in gas
        'duration': 15.0,          # survive this long or hit switches
        'switches': 2,
    },
    'spike_floor': {
        'description': 'Stand on safe tiles when the floor lights up',
        'hazard_type': 'spike',
        'pattern': 'checkerboard', # alternating safe/danger tiles
        'damage': 20,
        'cycle_time': 3.0,
        'warning_time': 1.0,       # tiles glow 1s before activating
    },
    'fire_corridor': {
        'description': 'Time your crossing between fire jets',
        'hazard_type': 'fire',
        'pattern': 'sequential',   # fire jets activate left-to-right
        'damage': 18,
        'cycle_time': 1.5,
        'safe_window': 0.6,
    },
    'crusher_hall': {
        'description': 'Dash through when crushers retract',
        'hazard_type': 'crusher',
        'pattern': 'timing',
        'damage': 25,
        'cycle_time': 2.5,
        'safe_window': 1.0,
    },
    'disable_switch': {
        'description': 'Reach the switches while dodging hazards',
        'hazard_type': 'mixed',
        'pattern': 'switches',
        'damage': 12,
        'switches': 3,
        'cycle_time': 2.0,
    },
}

# Which trap types appear per game phase
TRAP_POOLS = {
    'early': ['arrow_hall', 'spike_floor'],
    'mid':   ['arrow_hall', 'poison_vent', 'spike_floor', 'fire_corridor'],
    'late':  ['poison_vent', 'fire_corridor', 'crusher_hall', 'disable_switch'],
}

# ---------------------------------------------------------------------------
# Puzzle Room Templates
# ---------------------------------------------------------------------------
PUZZLE_TEMPLATES = {
    'rune_order': {
        'description': 'Step on runes in the order shown on the wall',
        'type': 'sequence',
        'elements': 3,             # 3 runes to activate in order
        'fail_penalty': 'spawn',   # wrong order spawns a skeleton
        'clue': 'wall_symbols',    # wall shows brightness order
    },
    'statue_facing': {
        'description': 'Turn all statues to face the door',
        'type': 'alignment',
        'elements': 4,             # 4 statues to rotate
        'fail_penalty': 'dart',    # wrong rotation fires a dart
        'clue': 'mural',           # mural shows correct directions
    },
    'element_match': {
        'description': 'Use the right damage type on each brazier',
        'type': 'element',
        'elements': 3,             # 3 braziers needing fire/ice/lightning
        'fail_penalty': 'reset',
        'clue': 'colour',          # brazier colour hints at needed element
    },
    'safe_path': {
        'description': 'Only walk on tiles that match the floor pattern',
        'type': 'pathing',
        'elements': 0,             # grid-based
        'fail_penalty': 'damage',  # wrong tile does 10 damage
        'clue': 'glow',            # safe tiles pulse faintly
    },
    'combat_order': {
        'description': 'Kill enemies in the marked order',
        'type': 'combat_sequence',
        'elements': 3,             # 3 marked enemies
        'fail_penalty': 'heal_all', # wrong kill heals remaining enemies
        'clue': 'numbers',          # enemies have visible 1, 2, 3 markers
    },
    'weight_plates': {
        'description': 'Stand on all pressure plates at once',
        'type': 'weight',
        'elements': 3,
        'fail_penalty': 'none',
        'clue': 'glow',
    },
}

PUZZLE_POOLS = {
    'early': ['rune_order', 'weight_plates'],
    'mid':   ['rune_order', 'statue_facing', 'element_match', 'safe_path'],
    'late':  ['element_match', 'combat_order', 'safe_path', 'statue_facing'],
}

# ---------------------------------------------------------------------------
# Room Purpose System - trap/puzzle rooms gate meaningful rewards
# ---------------------------------------------------------------------------
# What a trap or puzzle room can guard (picked based on context)
ROOM_REWARDS = {
    'trap': {
        'early':  ['treasure_chest', 'bonus_gold'],
        'mid':    ['treasure_chest', 'rare_item', 'shortcut'],
        'late':   ['rare_item', 'legendary_chance', 'hidden_passage'],
    },
    'puzzle': {
        'early':  ['treasure_chest', 'bonus_gold'],
        'mid':    ['rare_item', 'disable_next_traps', 'treasure_chest'],
        'late':   ['legendary_chance', 'full_heal', 'rare_item'],
    },
}

# ---------------------------------------------------------------------------
# Player Visual Design - Class Sprites
# ---------------------------------------------------------------------------
PLAYER_VISUALS = {
    'warrior': {
        'body': (170, 175, 185),        # steel grey armour
        'secondary': (160, 50, 50),     # deep red cloth
        'detail': (110, 90, 70),        # leather/darker trim
        'accent': (220, 190, 50),       # gold accent
        'shadow': (110, 115, 125),
        'highlight': (210, 215, 230),
        'silhouette': 'blocky',         # broad shoulders, planted stance
        'anim_style': 'heavy',          # weighted steps, big swings
    },
    'mage': {
        'body': (70, 40, 130),          # deep purple robe
        'secondary': (40, 35, 80),      # darker trim/sash
        'detail': (160, 150, 140),      # pale skin / staff
        'accent': (80, 200, 255),       # cyan magical glow
        'shadow': (45, 25, 90),
        'highlight': (110, 70, 180),
        'silhouette': 'narrow_tall',    # thin vertical, robe shape
        'anim_style': 'glide',          # smooth, less physical motion
    },
    'rogue': {
        'body': (30, 30, 40),           # black/charcoal
        'secondary': (80, 60, 45),      # leather brown
        'detail': (160, 165, 170),      # metal/dagger/belt
        'accent': (200, 40, 40),        # bright red scarf
        'shadow': (18, 18, 25),
        'highlight': (55, 55, 70),
        'silhouette': 'slim',           # narrow, hooded, angled
        'anim_style': 'twitchy',        # fast stop-start, slight crouch
    },
    'healer': {
        'body': (230, 225, 210),        # white/cream robes
        'secondary': (80, 180, 80),     # soft green secondary
        'detail': (160, 140, 100),      # wood staff/accessory
        'accent': (220, 200, 60),       # gold healing glow
        'shadow': (180, 175, 165),
        'highlight': (245, 240, 230),
        'silhouette': 'soft',           # softer than mage, approachable
        'anim_style': 'calm',           # gentle walk, minimal aggression
    },
}

# ---------------------------------------------------------------------------
# Enemy Visual Design - Pixel Art Color Palettes
# ---------------------------------------------------------------------------
# Rule: 60-70% body, 20-30% secondary, 5-10% accent
# Shadows: darker bottom-right, brighter top-left, accent near head/weapon
ENEMY_VISUALS = {
    # --- TRASH ---
    "goblin": {
        "body": (85, 140, 60),        # dirty green skin
        "secondary": (110, 75, 45),    # brown leather
        "weapon": (90, 90, 95),        # dark grey knife
        "accent": (220, 200, 40),      # yellow eyes
        "accent2": (180, 40, 40),      # red headband
        "shadow": (55, 100, 35),       # darker green
        "highlight": (120, 180, 80),   # lighter green
        "shape": "squat",              # small squat square, large head
        "anim": "jittery",             # quick side-to-side bob, hesitate then rush
    },
    "skeleton": {
        "body": (210, 205, 190),       # off-white bone
        "secondary": (90, 85, 80),     # dark grey cracks
        "weapon": (140, 110, 80),      # rusted metal
        "accent": (200, 40, 40),       # red eye glow
        "accent2": (60, 80, 180),      # alt blue eye glow
        "shadow": (160, 155, 140),     # darker bone
        "highlight": (240, 235, 225),  # bright bone
        "shape": "thin_tall",          # thin vertical, visible rib lines
        "anim": "jerky",              # sharp snapping steps, no bounce
    },
    "slime": {
        "body": (60, 180, 60),         # green gel (poison variant)
        "secondary": (35, 100, 35),    # darker inner core
        "weapon": None,
        "accent": (150, 255, 80),      # bright poison highlight
        "accent2": None,
        "shadow": (30, 120, 30),       # deep green
        "highlight": (100, 220, 100),  # wet top-left shine
        "shape": "blob",              # rounded square blob
        "anim": "hop",                # compress-stretch hop cycle
    },
    "wolf": {
        "body": (100, 90, 75),         # dark grey-brown fur
        "secondary": (145, 135, 120),  # lighter back fur
        "weapon": (210, 200, 185),     # pale teeth/claws
        "accent": (200, 60, 30),       # red-amber eyes
        "accent2": None,
        "shadow": (65, 55, 45),        # darker fur
        "highlight": (130, 120, 105),  # lit fur
        "shape": "horizontal",        # low wide shape, head forward
        "anim": "loping",             # smooth curved movement
    },
    "bug": {
        "body": (55, 50, 45),          # dark shell
        "secondary": (110, 95, 70),    # lighter carapace
        "weapon": None,
        "accent": (100, 255, 60),      # neon green venom sac
        "accent2": (200, 140, 40),     # orange alt
        "shadow": (30, 28, 25),        # very dark
        "highlight": (90, 80, 65),     # shell gleam
        "shape": "oval",              # compact oval body
        "anim": "scuttle",            # quick start-stop, direction changes
    },
    "undead_soldier": {
        "body": (120, 120, 130),       # dull iron armour
        "secondary": (90, 75, 60),     # rotting cloth
        "weapon": (100, 95, 90),       # worn sword
        "accent": (60, 120, 160),      # dim blue undead glow
        "accent2": (80, 160, 80),      # alt green glow
        "shadow": (80, 80, 90),        # dark iron
        "highlight": (160, 160, 170),  # iron gleam
        "shape": "bulky",             # wider than skeleton, broken shield
        "anim": "march",              # slow steady forward lean
    },
    # --- ELITE ---
    "assassin": {
        "body": (25, 25, 40),          # deep navy/black
        "secondary": (60, 30, 70),     # dark purple cloth
        "weapon": (180, 185, 190),     # silver blade
        "accent": (220, 40, 40),       # bright red eyes
        "accent2": (120, 200, 60),     # poison accent
        "shadow": (15, 15, 25),        # near black
        "highlight": (50, 50, 70),     # subtle edge
        "shape": "narrow",            # slim, cloak breaks silhouette
        "anim": "fade",               # burst-then-stop, slippery
    },
    "shaman": {
        "body": (130, 110, 80),        # muted robes
        "secondary": (200, 190, 160),  # bone charms/staff
        "weapon": (160, 140, 100),     # staff wood
        "accent": (80, 220, 100),      # green healing glow
        "accent2": (160, 60, 200),     # purple curse variant
        "shadow": (90, 75, 55),        # dark robe
        "highlight": (170, 150, 115),  # lit robe
        "shape": "robed",             # robe-heavy, staff above head
        "anim": "float",              # keeps distance, small floaty bob
    },
    "elite_knight": {
        "body": (170, 175, 185),       # steel plate
        "secondary": (130, 50, 50),    # crimson tabard
        "weapon": (200, 200, 210),     # bright steel
        "accent": (220, 190, 50),      # gold crest
        "accent2": (255, 80, 40),      # eye slit glow
        "shadow": (110, 115, 125),     # dark steel
        "highlight": (210, 215, 230),  # polished gleam
        "shape": "broad",             # very square, broad shoulders
        "anim": "deliberate",         # brace pose before charging
    },
    "ogre": {
        "body": (120, 130, 95),        # desaturated green-grey skin
        "secondary": (90, 70, 50),     # ragged cloth
        "weapon": (80, 65, 45),        # dark wood club
        "accent": (200, 50, 40),       # red scars/rage cracks
        "accent2": (255, 140, 40),     # glowing rage
        "shadow": (80, 90, 60),        # dark skin
        "highlight": (155, 165, 125),  # lit skin
        "shape": "massive",           # very large, tiny head, giant arms
        "anim": "stomp",              # heavy slow stomp, turns slowly
    },
    "cursed_priest": {
        "body": (40, 35, 50),          # dark robes
        "secondary": (170, 150, 60),   # corrupted gold trim
        "weapon": None,
        "accent": (160, 50, 200),      # purple curse glow
        "accent2": (100, 200, 60),     # sickly green variant
        "shadow": (25, 20, 35),        # deep shadow
        "highlight": (70, 65, 85),     # edge light
        "shape": "tall_robe",         # tall hollow hood
        "anim": "glide",              # slow minimal body motion, eerie
    },
    "dark_mage": {
        "body": (55, 30, 80),          # deep purple robe
        "secondary": (140, 135, 130),  # pale skin/grey
        "weapon": (170, 175, 185),     # silver staff/orb
        "accent": (180, 50, 255),      # vivid violet spell
        "accent2": (50, 200, 220),     # cyan forbidden arcane
        "shadow": (35, 18, 55),        # dark purple
        "highlight": (85, 55, 120),    # lit robe
        "shape": "robed_clean",       # cleaner than shaman, glowing orb
        "anim": "strafe",             # maintains range, stops to cast
    },
    # --- BOSS ---
    "giant_beast": {
        "body": (80, 60, 50),          # dark hide
        "secondary": (110, 90, 70),    # lighter plating
        "weapon": (140, 120, 100),     # horn/claw
        "accent": (220, 80, 30),       # orange rage glow
        "accent2": (255, 40, 20),      # intensified rage (low HP)
        "shadow": (50, 35, 28),        # dark hide shadow
        "highlight": (120, 95, 80),    # lit hide
        "shape": "beast_large",       # massive, cracks glow when enraged
        "anim": "heavy",              # moderate then faster as HP drops
        "danger_color": (255, 100, 30),  # rage accent grows during fight
    },
    "fallen_hero": {
        "body": (160, 165, 175),       # polished steel/obsidian
        "secondary": (70, 90, 110),    # dark cape
        "weapon": (200, 205, 215),     # bright weapon flash
        "accent": (80, 180, 220),      # cool teal
        "accent2": (220, 220, 240),    # white shimmer on parry
        "shadow": (100, 105, 115),     # dark steel
        "highlight": (200, 205, 220),  # gleaming
        "shape": "duelist",           # clean disciplined, smaller but precise
        "anim": "precise",            # minimal wasted motion, sidesteps
        "danger_color": (100, 200, 255),
    },
    "corrupted_king": {
        "body": (60, 30, 40),          # dark robes/chitin
        "secondary": (180, 170, 140),  # bone/totem structures
        "weapon": None,
        "accent": (200, 50, 255),      # vivid purple summon glow
        "accent2": (140, 220, 100),    # sickly green minion link
        "shadow": (35, 18, 25),        # deep shadow
        "highlight": (90, 55, 70),     # edge
        "shape": "summoner",          # core body + orbiting sigils
        "anim": "hover",              # hangs back, repositions
        "danger_color": (220, 80, 255),
    },
    "dungeon_guardian": {
        "body": (100, 85, 60),         # earthy/corrupted base
        "secondary": (130, 120, 100),  # armour/structure
        "weapon": None,
        "accent": (80, 220, 80),       # toxic green hazard
        "accent2": (220, 140, 30),     # lava orange variant
        "shadow": (65, 55, 38),        # dark earth
        "highlight": (140, 125, 90),   # lit earth
        "shape": "anchored",          # fused with room, spikes/growths
        "anim": "anchor",             # slow central control, less chasing
        "danger_color": (120, 255, 80),
    },
    "floor_admin": {
        "body": (90, 70, 90),          # dark base (phase 1 restrained)
        "secondary": (140, 120, 140),  # lighter detail
        "weapon": (180, 160, 180),     # weapon/limb
        "accent": (200, 60, 60),       # phase 1 subtle glow
        "accent2": (255, 200, 60),     # phase 3 intense glow
        "shadow": (55, 40, 55),        # deep
        "highlight": (130, 110, 130),  # lit
        "shape": "phase_morph",       # changes across 3 phases
        "anim": "phase_shift",        # readable -> aggressive -> desperate
        "danger_color": (255, 100, 100),
        "phase_colors": {
            1: (200, 60, 60),          # stable red
            2: (255, 160, 40),         # bright orange
            3: (255, 255, 80),         # intense yellow
        },
    },
    "dragon": {
        "body": (180, 45, 30),         # red scales
        "secondary": (220, 150, 80),   # underbelly/wing membrane
        "weapon": (200, 190, 170),     # horn/claw/bone
        "accent": (255, 160, 40),      # orange fire breath
        "accent2": (255, 220, 80),     # totem glow link
        "shadow": (120, 25, 15),       # dark scales
        "highlight": (220, 80, 50),    # lit scales
        "shape": "dragon",            # triangular head, wing blocks, tail
        "anim": "sweeping",           # deliberate head turns, large lunges
        "danger_color": (255, 200, 60),
    },
}
