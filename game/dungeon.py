import random
import math

from config import (TILE_SIZE, ROOM_TYPES, ENEMY_DATA, FLOOR_CONFIG, COLORS,
                     FLOOR_ENEMY_POOLS, ROOM_COMPOSITIONS, FLOOR_ROOM_WEIGHTS,
                     TRAP_TEMPLATES, TRAP_POOLS, PUZZLE_TEMPLATES, PUZZLE_POOLS,
                     FLOOR_EXIT_TYPE, ROOM_REWARDS)
from game.enemies import Enemy, Totem
from game.combat import generate_loot, Item


class Room:
    def __init__(self, x, y, w, h, room_type='mob'):
        self.x = x  # tile coords
        self.y = y
        self.w = w  # width in tiles
        self.h = h  # height in tiles
        self.room_type = room_type  # mob, trap, puzzle, elite, boss, treasure, merchant, hidden, start
        self.enemies = []
        self.items = []
        self.cleared = False
        self.discovered = False
        self.connected_rooms = []  # indices of connected rooms
        self.center_x = x + w // 2  # tile center
        self.center_y = y + h // 2
        self.pixel_center_x = self.center_x * TILE_SIZE + TILE_SIZE // 2
        self.pixel_center_y = self.center_y * TILE_SIZE + TILE_SIZE // 2
        self.traps = []  # list of (tile_x, tile_y, trap_type) for trap rooms
        self.puzzle_state = None
        self.merchant_items = []
        self.is_exit_room = False   # True if this is the floor's exit room
        self.room_purpose = None    # what reward this room gates (for trap/puzzle)

    def contains_point(self, tx, ty):
        return self.x <= tx < self.x + self.w and self.y <= ty < self.y + self.h

    def get_pixel_rect(self):
        import pygame
        return pygame.Rect(self.x * TILE_SIZE, self.y * TILE_SIZE,
                           self.w * TILE_SIZE, self.h * TILE_SIZE)

    @staticmethod
    def _get_phase(floor_num):
        """Return game phase: 'early', 'mid', or 'late'."""
        if floor_num <= 2:
            return 'early'
        elif floor_num <= 4:
            return 'mid'
        return 'late'

    @staticmethod
    def _weighted_pick(templates):
        """Pick from a list of dicts with 'weight' keys."""
        total = sum(t['weight'] for t in templates)
        r = random.random() * total
        cumulative = 0
        for t in templates:
            cumulative += t['weight']
            if r <= cumulative:
                return t
        return templates[-1]

    def _rand_pos(self):
        """Random pixel position inside this room (with margin)."""
        ex = random.randint(self.x + 1, self.x + self.w - 2) * TILE_SIZE + TILE_SIZE // 2
        ey = random.randint(self.y + 1, self.y + self.h - 2) * TILE_SIZE + TILE_SIZE // 2
        return ex, ey

    def spawn_enemies(self, floor_num, difficulty_mod=1.0):
        """Populate room with enemies using floor-aware pools and composition templates."""
        from game.enemies import Enemy

        if self.room_type in ('start', 'treasure', 'merchant'):
            return

        phase = self._get_phase(floor_num)
        pool = FLOOR_ENEMY_POOLS.get(floor_num, FLOOR_ENEMY_POOLS[6])

        if self.room_type == 'mob':
            # --- MOB ROOM: use composition templates ---
            comp_key = f'mob_{phase}'
            templates = ROOM_COMPOSITIONS.get(comp_key, ROOM_COMPOSITIONS['mob_early'])
            comp = self._weighted_pick(templates)
            for enemy_name, count_min, count_max in comp['trash']:
                # Only spawn if this enemy is in the floor pool
                if enemy_name in pool['trash']:
                    count = random.randint(count_min, count_max)
                    for _ in range(count):
                        ex, ey = self._rand_pos()
                        self.enemies.append(Enemy(enemy_name, ex, ey, floor_num, difficulty_mod))
                else:
                    # Substitute from pool
                    sub = random.choice(pool['trash'])
                    count = random.randint(count_min, count_max)
                    for _ in range(count):
                        ex, ey = self._rand_pos()
                        self.enemies.append(Enemy(sub, ex, ey, floor_num, difficulty_mod))

        elif self.room_type == 'elite':
            # --- ELITE ROOM: elite + synergy trash from templates ---
            if not pool['elite']:
                # No elites available on this floor — downgrade to mob room
                self.room_type = 'mob'
                self.spawn_enemies(floor_num, difficulty_mod)
                return

            is_exit = getattr(self, 'is_exit_room', False)

            if is_exit:
                # EXIT ELITE FORMATION: 2-3 elites working together, tougher fight
                num_elites = min(len(pool['elite']), random.randint(2, 3))
                elite_picks = random.sample(pool['elite'], num_elites)
                for i, elite_name in enumerate(elite_picks):
                    offset_x = (i - num_elites // 2) * 60
                    self.enemies.append(Enemy(elite_name,
                                              self.pixel_center_x + offset_x,
                                              self.pixel_center_y,
                                              floor_num, difficulty_mod * 1.1))
                # Supporting trash
                if pool['trash']:
                    for _ in range(random.randint(2, 4)):
                        name = random.choice(pool['trash'])
                        ex, ey = self._rand_pos()
                        self.enemies.append(Enemy(name, ex, ey, floor_num, difficulty_mod))
            else:
                comp_key = f'elite_{phase}'
                templates = ROOM_COMPOSITIONS.get(comp_key, ROOM_COMPOSITIONS['elite_early'])
                comp = self._weighted_pick(templates)
                # Spawn elite (pick from pool if template elite isn't available)
                elite_name = comp.get('elite', random.choice(pool['elite']))
                if elite_name not in pool['elite']:
                    elite_name = random.choice(pool['elite'])
                self.enemies.append(Enemy(elite_name, self.pixel_center_x, self.pixel_center_y,
                                          floor_num, difficulty_mod))
                # Spawn supporting trash
                for enemy_name, count_min, count_max in comp['trash']:
                    name = enemy_name if enemy_name in pool['trash'] else random.choice(pool['trash'])
                    count = random.randint(count_min, count_max)
                    for _ in range(count):
                        ex, ey = self._rand_pos()
                        self.enemies.append(Enemy(name, ex, ey, floor_num, difficulty_mod))

        elif self.room_type == 'boss':
            # --- BOSS: specific boss per floor ---
            if pool['boss']:
                boss_name = random.choice(pool['boss'])
                self.enemies.append(Enemy(boss_name, self.pixel_center_x, self.pixel_center_y,
                                          floor_num, difficulty_mod))
            else:
                # No boss on this floor - spawn tough elite formation instead
                if pool['elite']:
                    for name in random.sample(pool['elite'], min(2, len(pool['elite']))):
                        ex, ey = self._rand_pos()
                        self.enemies.append(Enemy(name, ex, ey, floor_num, difficulty_mod * 1.2))
                elif pool['trash']:
                    for _ in range(5):
                        name = random.choice(pool['trash'])
                        ex, ey = self._rand_pos()
                        self.enemies.append(Enemy(name, ex, ey, floor_num, difficulty_mod * 1.3))

        elif self.room_type == 'trap':
            # --- TRAP ROOM: readable hazards with proper templates ---
            trap_pool = TRAP_POOLS.get(phase, TRAP_POOLS['early'])
            template_name = random.choice(trap_pool)
            template = TRAP_TEMPLATES[template_name]
            self.trap_template = template_name

            # Generate trap hazards based on template pattern
            if template['pattern'] == 'lanes':
                # Arrow lanes: rows of the room become hazard lanes
                for lane_y in range(self.y + 1, self.y + self.h - 1, 2):
                    for tx in range(self.x + 1, self.x + self.w - 1):
                        self.traps.append((tx, lane_y, template['hazard_type']))
            elif template['pattern'] in ('rotating', 'switches'):
                # Place switch targets the player must reach
                n_switches = template.get('switches', 2)
                corners = [
                    (self.x + 1, self.y + 1),
                    (self.x + self.w - 2, self.y + 1),
                    (self.x + 1, self.y + self.h - 2),
                    (self.x + self.w - 2, self.y + self.h - 2),
                ]
                random.shuffle(corners)
                switch_positions = corners[:n_switches]
                self.puzzle_state = {
                    'plates': switch_positions,
                    'activated': [False] * n_switches,
                    'solved': False,
                    'trap_active': True,
                    'trap_timer': 0.0,
                    'trap_template': template_name,
                }
                # Hazard tiles cover most of the room
                for ty in range(self.y + 1, self.y + self.h - 1):
                    for tx in range(self.x + 1, self.x + self.w - 1):
                        if (tx, ty) not in switch_positions:
                            self.traps.append((tx, ty, template['hazard_type']))
            elif template['pattern'] in ('checkerboard', 'sequential', 'timing'):
                # Pattern-based hazard tiles
                for ty in range(self.y + 1, self.y + self.h - 1):
                    for tx in range(self.x + 1, self.x + self.w - 1):
                        if template['pattern'] == 'checkerboard':
                            if (tx + ty) % 2 == 0:
                                self.traps.append((tx, ty, template['hazard_type']))
                        else:
                            # Sequential/timing: every other row
                            if ty % 2 == 0:
                                self.traps.append((tx, ty, template['hazard_type']))
            # Add light enemy pressure in mid/late trap rooms
            if phase in ('mid', 'late') and pool['trash']:
                count = 1 if phase == 'mid' else 2
                for _ in range(count):
                    name = random.choice(pool['trash'])
                    ex, ey = self._rand_pos()
                    self.enemies.append(Enemy(name, ex, ey, floor_num, difficulty_mod))

        elif self.room_type == 'puzzle':
            # --- PUZZLE ROOM: template-based puzzles ---
            puzzle_pool = PUZZLE_POOLS.get(phase, PUZZLE_POOLS['early'])
            template_name = random.choice(puzzle_pool)
            template = PUZZLE_TEMPLATES[template_name]
            n_elements = template['elements'] if template['elements'] > 0 else 3

            if template['type'] in ('sequence', 'alignment', 'element', 'weight'):
                # Place interactive elements (plates/statues/braziers)
                positions = []
                for _ in range(n_elements):
                    tx = random.randint(self.x + 1, self.x + self.w - 2)
                    ty = random.randint(self.y + 1, self.y + self.h - 2)
                    positions.append((tx, ty))
                # Correct order is the order they were generated
                correct_order = list(range(n_elements))
                if template['type'] != 'weight':
                    random.shuffle(correct_order)
                self.puzzle_state = {
                    'plates': positions,
                    'activated': [False] * n_elements,
                    'solved': False,
                    'puzzle_template': template_name,
                    'correct_order': correct_order,
                    'current_step': 0,
                    'fail_penalty': template['fail_penalty'],
                    'clue_type': template.get('clue', 'glow'),
                }
            elif template['type'] == 'pathing':
                # Safe path puzzle: some tiles are safe, rest are dangerous
                safe_tiles = set()
                # Create a winding safe path from entrance to centre
                cx, cy = self.center_x, self.center_y
                path_x, path_y = self.x + 1, self.y + self.h // 2
                while (path_x, path_y) != (cx, cy):
                    safe_tiles.add((path_x, path_y))
                    if path_x < cx:
                        path_x += 1
                    elif path_x > cx:
                        path_x -= 1
                    if path_y < cy:
                        path_y += 1
                    elif path_y > cy:
                        path_y -= 1
                safe_tiles.add((cx, cy))
                # Add some extra safe tiles for multiple valid paths
                for _ in range(len(safe_tiles) // 2):
                    t = random.choice(list(safe_tiles))
                    safe_tiles.add((t[0] + random.choice([-1, 0, 1]),
                                    t[1] + random.choice([-1, 0, 1])))
                self.puzzle_state = {
                    'plates': list(safe_tiles),
                    'activated': [True] * len(safe_tiles),
                    'solved': False,
                    'puzzle_template': template_name,
                    'safe_tiles': safe_tiles,
                    'fail_penalty': 'damage',
                    'clue_type': 'glow',
                }
            elif template['type'] == 'combat_sequence':
                # Spawn marked enemies that must be killed in order
                names = random.sample(pool['trash'] if pool['trash'] else ['goblin', 'skeleton', 'slime'],
                                      min(n_elements, len(pool['trash']) if pool['trash'] else 3))
                positions = []
                for i, name in enumerate(names):
                    ex, ey = self._rand_pos()
                    e = Enemy(name, ex, ey, floor_num, difficulty_mod)
                    e.puzzle_order = i + 1  # mark with kill order
                    self.enemies.append(e)
                    positions.append((int(ex // TILE_SIZE), int(ey // TILE_SIZE)))
                self.puzzle_state = {
                    'plates': positions,
                    'activated': [False] * n_elements,
                    'solved': False,
                    'puzzle_template': template_name,
                    'correct_order': list(range(n_elements)),
                    'current_step': 0,
                    'fail_penalty': template['fail_penalty'],
                    'clue_type': 'numbers',
                }

        elif self.room_type == 'survival':
            # Survival rooms start empty; waves are spawned by the engine
            pass

        elif self.room_type == 'hidden':
            # Strong elite from this floor's pool (or next floor) with great loot
            if pool['elite']:
                name = random.choice(pool['elite'])
            else:
                # Fallback: use a higher floor's elite
                next_pool = FLOOR_ENEMY_POOLS.get(min(floor_num + 1, 6), FLOOR_ENEMY_POOLS[6])
                name = random.choice(next_pool['elite']) if next_pool['elite'] else 'shaman'
            self.enemies.append(Enemy(name, self.pixel_center_x, self.pixel_center_y,
                                      floor_num + 1, difficulty_mod * 1.3))

    def spawn_items(self, floor_num):
        from game.combat import generate_loot
        if self.room_type in ('treasure', 'hidden'):
            self.items = generate_loot(floor_num, self.room_type)
            for i, item in enumerate(self.items):
                item.x = self.pixel_center_x + (i % 3 - 1) * 20
                item.y = self.pixel_center_y + (i // 3) * 20
        elif self.room_type == 'merchant':
            self.merchant_items = generate_loot(floor_num, 'merchant')
            for i, item in enumerate(self.merchant_items):
                item.x = self.pixel_center_x + (i % 3 - 1) * 20
                item.y = self.pixel_center_y + (i // 3) * 20
        # Trap and puzzle rooms have reward purpose set — items spawn on solve/clear
        # (handled by engine._solve_puzzle and _solve_trap_room)
        # Mob/elite rooms drop loot on clear


class Floor:
    def __init__(self, floor_num, width=60, height=60):
        self.floor_num = floor_num
        self.width = width
        self.height = height
        self.grid = [[0] * width for _ in range(height)]  # 0=wall, 1=floor, 2=door, 3=trap, 4=stairs
        self.rooms = []
        self.start_room = None
        self.boss_room = None
        self.current_room_idx = 0

    def generate(self, difficulty_mod=1.0, room_type_weights=None):
        """Generate the floor layout with rooms and corridors."""
        from config import FLOOR_CONFIG

        num_rooms = FLOOR_CONFIG.get('rooms_per_floor', 8) + self.floor_num
        num_rooms = min(num_rooms, 15)  # cap

        # Room type distribution - use floor-tier weights
        if room_type_weights is None:
            if self.floor_num <= 2:
                room_type_weights = FLOOR_ROOM_WEIGHTS['early']
            elif self.floor_num <= 4:
                room_type_weights = FLOOR_ROOM_WEIGHTS['mid']
            else:
                room_type_weights = FLOOR_ROOM_WEIGHTS['late']

        # Determine exit type for this floor
        self.exit_type = FLOOR_EXIT_TYPE.get(self.floor_num, 'boss')

        # Generate rooms using BSP-like approach
        self._generate_rooms(num_rooms, room_type_weights)

        # Connect rooms with corridors
        self._connect_rooms()

        # Populate rooms
        for room in self.rooms:
            room.spawn_enemies(self.floor_num, difficulty_mod)
            room.spawn_items(self.floor_num)

        # Assign purpose to trap/puzzle rooms based on layout
        self._assign_room_purposes()

        return self

    def _generate_rooms(self, num_rooms, type_weights):
        """Place rooms without overlap."""
        attempts = 0
        max_attempts = 500

        # First room is always start
        start_w = random.randint(5, 7)
        start_h = random.randint(5, 7)
        start_x = self.width // 2 - start_w // 2
        start_y = self.height // 2 - start_h // 2
        start_room = Room(start_x, start_y, start_w, start_h, 'start')
        start_room.discovered = True
        self.rooms.append(start_room)
        self.start_room = start_room
        self._carve_room(start_room)

        # Determine exit room type based on floor exit type
        exit_type = getattr(self, 'exit_type', 'boss')
        exit_room_map = {
            'boss': 'boss',
            'survival': 'survival',
            'trap_gauntlet': 'trap',
            'puzzle_gate': 'puzzle',
            'elite_formation': 'elite',
        }
        exit_room_type = exit_room_map.get(exit_type, 'boss')

        # Generate remaining rooms
        while len(self.rooms) < num_rooms and attempts < max_attempts:
            attempts += 1
            w = random.randint(5, 10)
            h = random.randint(5, 10)
            x = random.randint(1, self.width - w - 1)
            y = random.randint(1, self.height - h - 1)

            # Check overlap with existing rooms (with margin)
            overlap = False
            for room in self.rooms:
                if (x - 2 < room.x + room.w and x + w + 2 > room.x and
                        y - 2 < room.y + room.h and y + h + 2 > room.y):
                    overlap = True
                    break

            if not overlap:
                # Last room is the exit room
                if len(self.rooms) == num_rooms - 1:
                    room_type = exit_room_type
                    # Make exit rooms bigger for dramatic encounters
                    w = max(w, 8)
                    h = max(h, 8)
                else:
                    room_type = self._weighted_choice(type_weights)

                room = Room(x, y, w, h, room_type)
                room.is_exit_room = (len(self.rooms) == num_rooms - 1)
                self.rooms.append(room)
                self._carve_room(room)

                if room_type == 'boss':
                    self.boss_room = room
                # For non-boss exits, mark the exit room so engine knows
                if room.is_exit_room:
                    self.exit_room = room

        # Ensure we have an exit room
        if not hasattr(self, 'exit_room') or self.exit_room is None:
            if len(self.rooms) > 1:
                last = self.rooms[-1]
                last.room_type = exit_room_type
                last.is_exit_room = True
                self.exit_room = last
                if exit_room_type == 'boss':
                    self.boss_room = last

        # For boss exits, also set boss_room
        if exit_type == 'boss' and not self.boss_room:
            if hasattr(self, 'exit_room') and self.exit_room:
                self.boss_room = self.exit_room

    def _weighted_choice(self, weights):
        items = list(weights.keys())
        probs = list(weights.values())
        total = sum(probs)
        probs = [p / total for p in probs]
        r = random.random()
        cumulative = 0
        for item, prob in zip(items, probs):
            cumulative += prob
            if r <= cumulative:
                return item
        return items[-1]

    def _carve_room(self, room):
        """Set room tiles to floor."""
        for y in range(room.y, room.y + room.h):
            for x in range(room.x, room.x + room.w):
                if 0 <= y < self.height and 0 <= x < self.width:
                    self.grid[y][x] = 1
        # Carve traps
        if room.room_type == 'trap':
            for tx, ty, _ in room.traps:
                if 0 <= ty < self.height and 0 <= tx < self.width:
                    self.grid[ty][tx] = 3
        # Stairs down in exit room (boss, survival, trap gauntlet, etc.)
        is_exit = getattr(room, 'is_exit_room', False)
        if room.room_type == 'boss' or is_exit:
            self.grid[room.center_y][room.center_x] = 4

    def _connect_rooms(self):
        """Connect rooms with corridors using minimum spanning tree + some extras."""
        if len(self.rooms) < 2:
            return

        # Build MST using Prim's algorithm on room centers
        connected = {0}
        edges = []

        while len(connected) < len(self.rooms):
            best_dist = float('inf')
            best_edge = None
            for i in connected:
                for j in range(len(self.rooms)):
                    if j not in connected:
                        dist = self._room_distance(self.rooms[i], self.rooms[j])
                        if dist < best_dist:
                            best_dist = dist
                            best_edge = (i, j)

            if best_edge is None:
                break

            edges.append(best_edge)
            connected.add(best_edge[1])
            self.rooms[best_edge[0]].connected_rooms.append(best_edge[1])
            self.rooms[best_edge[1]].connected_rooms.append(best_edge[0])

        # Add a few extra connections for loops
        for _ in range(len(self.rooms) // 3):
            i = random.randint(0, len(self.rooms) - 1)
            j = random.randint(0, len(self.rooms) - 1)
            if i != j and j not in self.rooms[i].connected_rooms:
                edges.append((i, j))
                self.rooms[i].connected_rooms.append(j)
                self.rooms[j].connected_rooms.append(i)

        # Carve corridors
        for i, j in edges:
            self._carve_corridor(self.rooms[i], self.rooms[j])

    def _room_distance(self, r1, r2):
        return math.sqrt((r1.center_x - r2.center_x) ** 2 + (r1.center_y - r2.center_y) ** 2)

    def _carve_corridor(self, room1, room2):
        """Carve an L-shaped corridor between two rooms."""
        x1, y1 = room1.center_x, room1.center_y
        x2, y2 = room2.center_x, room2.center_y

        # Randomly choose horizontal-first or vertical-first
        if random.random() < 0.5:
            self._carve_h_corridor(x1, x2, y1)
            self._carve_v_corridor(y1, y2, x2)
        else:
            self._carve_v_corridor(y1, y2, x1)
            self._carve_h_corridor(x1, x2, y2)

    def _carve_h_corridor(self, x1, x2, y):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for dy in range(-1, 2):
                ny = y + dy
                if 0 <= ny < self.height and 0 <= x < self.width:
                    if self.grid[ny][x] == 0:
                        self.grid[ny][x] = 1

    def _carve_v_corridor(self, y1, y2, x):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            for dx in range(-1, 2):
                nx = x + dx
                if 0 <= y < self.height and 0 <= nx < self.width:
                    if self.grid[y][nx] == 0:
                        self.grid[y][nx] = 1

    def _assign_room_purposes(self):
        """Give trap and puzzle rooms a meaningful purpose based on what they're near."""
        phase = 'early' if self.floor_num <= 2 else ('mid' if self.floor_num <= 4 else 'late')

        for room in self.rooms:
            if room.room_type == 'trap' and not room.is_exit_room:
                purposes = ROOM_REWARDS['trap'].get(phase, ['treasure_chest'])
                room.room_purpose = random.choice(purposes)
            elif room.room_type == 'puzzle' and not room.is_exit_room:
                purposes = ROOM_REWARDS['puzzle'].get(phase, ['treasure_chest'])
                room.room_purpose = random.choice(purposes)

            # Exit trap/puzzle rooms have a special purpose: unlock the stairs
            if room.is_exit_room and room.room_type in ('trap', 'puzzle'):
                room.room_purpose = 'unlock_exit'

    def is_walkable(self, tx, ty):
        """Check if a tile coordinate is walkable."""
        if 0 <= tx < self.width and 0 <= ty < self.height:
            return self.grid[ty][tx] != 0
        return False

    def get_room_at(self, tx, ty):
        """Get the room containing tile coords, or None."""
        for i, room in enumerate(self.rooms):
            if room.contains_point(tx, ty):
                return i, room
        return None, None

    def check_traps(self, player, game_time=0.0):
        """Check if player is standing on an active trap. Returns (damage, trap_type).

        Traps use timing patterns: not all tiles are active at once.
        - lanes/sequential: alternating rows active on even/odd cycles
        - checkerboard: alternating pattern flips each cycle
        - rotating: safe zone rotates around room centre
        """
        tx = int(player.x // TILE_SIZE)
        ty = int(player.y // TILE_SIZE)
        for room in self.rooms:
            if room.room_type == 'trap':
                template_name = getattr(room, 'trap_template', None)
                template = TRAP_TEMPLATES.get(template_name, {}) if template_name else {}
                cycle_time = template.get('cycle_time', 2.0)
                safe_window = template.get('safe_window', 0.5)
                pattern = template.get('pattern', 'lanes')
                base_dmg = template.get('damage', 12)

                # Check if player is on a trap tile
                for trap_x, trap_y, trap_type in room.traps:
                    if tx == trap_x and ty == trap_y:
                        # Timing check: is this tile currently active?
                        cycle_phase = (game_time % cycle_time) / cycle_time
                        tile_active = True

                        if pattern == 'lanes':
                            # Even rows active first half, odd rows second half
                            row_even = (trap_y % 2 == 0)
                            tile_active = (cycle_phase < 0.5) == row_even
                            # Safe window in the middle
                            if 0.45 < cycle_phase < 0.45 + safe_window / cycle_time:
                                tile_active = False
                        elif pattern == 'checkerboard':
                            # Pattern flips each cycle
                            flip = int(game_time / cycle_time) % 2
                            tile_even = ((trap_x + trap_y) % 2 == flip)
                            tile_active = tile_even
                            # Warning window before activation
                            if cycle_phase > 1.0 - template.get('warning_time', 0.5) / cycle_time:
                                tile_active = False  # telegraph: briefly safe during warning
                        elif pattern in ('sequential', 'timing'):
                            # Fire sequentially across room
                            col_phase = (trap_x - room.x) / max(room.w, 1)
                            tile_active = abs(cycle_phase - col_phase) < 0.2
                        elif pattern in ('rotating', 'switches'):
                            # Safe zone rotates: check if player is in safe quadrant
                            angle = (game_time / cycle_time) * math.pi * 2
                            safe_x = room.pixel_center_x + math.cos(angle) * (room.w * TILE_SIZE * 0.3)
                            safe_y = room.pixel_center_y + math.sin(angle) * (room.h * TILE_SIZE * 0.3)
                            dist_to_safe = math.sqrt((player.x - safe_x)**2 + (player.y - safe_y)**2)
                            tile_active = dist_to_safe > TILE_SIZE * 3  # safe within 3 tiles of safe spot

                        if tile_active:
                            return base_dmg, trap_type

                        # Even if tile exists but inactive, no damage
                        return 0, None
        return 0, None

    def get_all_enemies(self):
        """Get all alive enemies across all rooms."""
        enemies = []
        for room in self.rooms:
            enemies.extend([e for e in room.enemies if e.alive])
        return enemies

    def get_nearby_enemies(self, px, py, radius=400):
        """Get enemies near a pixel position."""
        enemies = []
        for room in self.rooms:
            for enemy in room.enemies:
                if enemy.alive:
                    dist = math.sqrt((enemy.x - px) ** 2 + (enemy.y - py) ** 2)
                    if dist < radius:
                        enemies.append(enemy)
        return enemies

    def check_room_cleared(self, room_idx):
        """Check if all enemies in a room are dead."""
        room = self.rooms[room_idx]
        if not room.cleared:
            alive_enemies = [e for e in room.enemies if e.alive]
            if len(alive_enemies) == 0 and len(room.enemies) > 0:
                room.cleared = True
                return True
        return False
