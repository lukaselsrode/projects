#!/usr/bin/python
import random
import time
import numpy as np
from scipy import constants
from pynput import keyboard
from os import system as run

# DEFAULT GAME CONFIGURATION
DEFAULT_WINDOW_LENGTH = 100
DEFAULT_ASSET_SPACING = 4
DEFAULT_BULLET_SPEED = 2
DEFAULT_TIME_PER_LVL = 10
DEFAULT_BULLET_FRAME_CYCLE = 20
DEFAULT_RULES_SET = [
    (2, 8, 1),
    (2, 0.1, 0.1),
    (2, 8, 1),
    (0.01, 0.0001, 0.0001),
    tuple([i * constants.milli for i in [60, 5, 5]]),
    (5, 0.5, 0.5),
]
DEFAULT_PLAYER_CAR, DEFAULT_BULLET = """.-'--`-._\n'-O---O--'""", ">"

OBSTACLES = [
    ("suv", "[O-- O ----]"),
    ("officer", "<o--o/-"),
    ("sedean", "<o##o`"),
    ("motorcycle", """O='`o"""),
    ("roadblock", "X+X+X+X+X"),
    ("truck", ",_( \_|"),
]

POWERUPS = [
    ("shield", """⍟"""),
    ("gun", """︻╦╤─"""),
]

# AUXILARRY FUNCTIONS
ascii_color_map, color_terminate = (
    dict(zip(["red", "green", "yellow"], [f"\x1b[1;3{i};40m" for i in range(1, 4)])),
    "\x1b[0m",
)


def color_string_on_console_stdout(color: str, s: str) -> str:
    return "".join([ascii_color_map[color], s, color_terminate])


def measure_asset(txt: str) -> tuple[int, int]:
    lines = txt.split("\n")
    return len(max(lines, key=len)), len(lines)


# GAME OBJECTS
class KeyListner(object):
    def __init__(self):
        self.direction, self.quit = None, False
        keyboard.Listener(on_press=lambda x: self.process_key(x)).start()

    def process_key(self, key: object) -> None:
        if key in {keyboard.Key.up, keyboard.Key.down, keyboard.Key.esc}:
            self.quit, self.direction = (
                (True, None)
                if key == keyboard.Key.esc
                else (False, str(key).lstrip("."))
            )
            return
        self.direction = None


class Settings(object):
    def __init__(self):
        self.game_world = (
            self.window_len,
            self.edge_char,
            self.mid_char,
            self.open_char,
            self.secs_per_lvl,
        ) = (DEFAULT_WINDOW_LENGTH, "_", "- ", " ", DEFAULT_TIME_PER_LVL)
        self.rules = DEFAULT_RULES_SET
        self.nlanes = (
            self.asset_spawn_time
        ) = (
            self.max_n_assets
        ) = self.pot_pwrup = self.t_per_frame = self.asset_jump_time = None
        self.lvl = 0

    def increment_settings(self):
        rv = []
        for i, v in enumerate(
            [
                self.nlanes,
                self.asset_spawn_time,
                self.max_n_assets,
                self.pot_pwrup,
                self.t_per_frame,
                self.asset_jump_time,
            ]
        ):
            vi, vf, vinc = self.rules[i]
            if not v:
                v = vi
            else:
                goes_up = vi < vf
                if (v < vf and goes_up) or (v > vf and not goes_up):
                    v = v + vinc if goes_up else v - vinc
            rv.append(v)
        (
            self.nlanes,
            self.asset_spawn_time,
            self.max_n_assets,
            self.pot_pwrup,
            self.t_per_frame,
            self.asset_jump_time,
        ) = tuple(rv)
        self.lvl += 1


class Road(object):
    def __init__(self):
        self.game_rules, self.assets = Settings(), []
        self.last_spawn = self.last_lvl = 0

    def update_rules(self) -> None:
        if self.game_rules.lvl == 0:
            self.game_rules.increment_settings()  # init catch
        # make sure player car doesn't go back to default lane
        if "player_car" in self.__dict__.keys():
            self.player_car.game_rules = self.game_rules
        else:
            self.player_car = Player(self.game_rules)

    def update_road_geometry(self) -> None:
        self.num_lanes, self.width, self.length = (
            self.game_rules.nlanes,
            (self.game_rules.nlanes) * 2,
            self.game_rules.window_len,
        )
        (
            self.barrier,
            self.lane,
        ) = self.game_rules.edge_char * self.length, color_string_on_console_stdout(
            "yellow", self.game_rules.mid_char * round(self.length / 2)
        )

    def update_road(self) -> None:
        self.update_rules(), self.update_road_geometry()

    def try_lvl_up(self) -> None:
        if time.time() - self.last_lvl > self.game_rules.secs_per_lvl:
            self.game_rules.increment_settings(), self.update_road()
            self.last_lvl = time.time()

    def flip_mid_lane(self) -> None:
        self.lane = color_string_on_console_stdout(
            "yellow",
            self.lane[::-1].strip(color_terminate).strip(ascii_color_map["yellow"]),
        )

    def try_spawn(self) -> None:
        if (
            round(time.time() - self.last_spawn) > self.game_rules.asset_spawn_time
        ) and len(self.assets) < self.game_rules.max_n_assets:
            self.spawn_obstacles(), self.spawn_powerup(), self.cleanup_spawn_cycle()
            self.last_spawn = time.time()

    def order_assets(self) -> None:
        self.assets = sorted(self.assets, key=lambda x: x.frame_count, reverse=True)

    def get_assets_to_free(self) -> set:
        return set(filter(lambda i: i.frame_count > len(self.barrier), self.assets))

    def try_destroy(self):
        freeing = self.get_assets_to_free()
        list(map(lambda i: self.remove_asset(i), freeing)), list(
            map(
                lambda f: self.shift_lane_assets(
                    self.in_lane(f.lane_pos), -measure_asset(f.ascii)[0]
                ),
                freeing,
            )
        )

    def in_lane(self, lane_num: int) -> list[object]:
        return list(filter(lambda x: x.lane_pos == lane_num, self.assets))

    def in_player_lane(self) -> list[object]:
        return self.in_lane(self.player_car.lane_pos)

    def limit_approachers(self):
        while len(self.assets) > self.game_rules.max_n_assets:
            self.assets.pop()

    def road_is_clean(self):
        all_counts = [i.frame_count for i in self.assets]
        return True if len(all_counts) == len(set(all_counts)) else False

    def lane_has_colliding_frames(self, lane_pos: int) -> bool:
        asset_frame_nums = [i.frame_count for i in self.in_lane(lane_pos)]
        return False if len(asset_frame_nums) == len(set(asset_frame_nums)) else True

    def cleanup_colliding_asset_frames(self) -> None:
        if self.road_is_clean():
            return
        for ln in range(self.width - 1):
            while self.lane_has_colliding_frames(ln):
                self.assets.remove(max(self.in_lane(ln), key=lambda x: x.frame_count))

    def cleanup_spawn_cycle(self) -> None:
        self.order_assets(), self.limit_approachers(), self.cleanup_colliding_asset_frames()

    def spawn_obstacles(self) -> None:
        self.assets += [
            Approacher(True, self.game_rules)
            for _ in range(random.choice(range(self.width - 1)))
        ]

    def spawn_powerup(self) -> None:
        if not [i for i in self.assets if i.is_obstacle == False]:
            rng = [
                *[[True] * round(self.game_rules.pot_pwrup * 100)],
                *[[False] * round((1 - self.game_rules.pot_pwrup) * 100)],
            ]
            if random.choice(rng):
                self.assets += [Approacher(False, self.game_rules)]

    def create_ascii_player_area(self, lane_index: int) -> str:
        return self.player_car.ascii if self.player_car.lane_pos == lane_index else ""

    def create_ascii_asset(self, asset: object) -> str:
        return color_string_on_console_stdout(
            "red" if asset.is_obstacle else "green", asset.ascii
        )

    def create_asset_lane(self, assets: list[object]) -> str:
        lane = ""
        for i, a in enumerate(assets):
            if i == 0:
                if (
                    self.player_car.power == "gun"
                    and assets[0].lane_pos == self.player_car.lane_pos
                ):
                    lane += self.game_rules.open_char * round(
                        (len(self.barrier) - a.frame_count)
                        - self.player_car.bullet_spacing,
                        3,
                    ) + self.create_ascii_asset(a)
                else:
                    lane += self.game_rules.open_char * round(
                        (len(self.barrier) - a.frame_count)
                    ) + self.create_ascii_asset(a)
            else:
                lane += self.game_rules.open_char * (
                    assets[i - 1].frame_count - a.frame_count
                ) + self.create_ascii_asset(a)
        return lane

    def create_ascii_lane(self, lane_index: int) -> str:
        lane_assets = self.in_lane(lane_index)
        if not lane_assets:
            return self.create_ascii_player_area(lane_index)
        return self.create_ascii_player_area(lane_index) + self.create_asset_lane(
            lane_assets
        )

    def player_hit(self) -> bool:
        lane = self.create_ascii_lane(self.player_car.lane_pos)
        frames_ahead_of_contact_point = (
            lane.split(self.player_car.ascii)[1].split(" ")
            if not self.player_car.power == "gun"
            else lane.split(DEFAULT_BULLET)[1].split(" ")
        )
        return True if frames_ahead_of_contact_point[0] != "" else False

    def shift_lane_assets(self, assets, shift) -> None:
        list(map(lambda x: x.shift(shift), assets))

    def adjust_assests_after_player_move(self, previous_lane: int) -> None:
        initial_lane, final_lane = self.in_lane(previous_lane), self.in_player_lane()
        if not (initial_lane or final_lane):
            return
        if initial_lane:
            self.shift_lane_assets(initial_lane, -self.player_car.sx)
        if final_lane:
            self.shift_lane_assets(final_lane, self.player_car.sx)

    def move_lane(self, Keys: object) -> None:
        prev = self.player_car.lane_pos
        self.player_car.move_lane(
            Keys.direction
        ), self.adjust_assests_after_player_move(prev)
        Keys.direction = None  # key sticks if not reset

    def remove_asset(self, Asset: object) -> None:
        self.assets = list(filter(lambda x: x != Asset, self.assets))

    def process_collision(self) -> None:
        collides_with, powerup = self.in_player_lane()[0], self.player_car.power
        if collides_with.is_obstacle:
            print(
                "GAME OVER"
            ), exit() if not powerup else self.player_car.loose_powers(), self.remove_asset(
                collides_with
            )
            return
        self.player_car.gain_powers(
            collides_with
        ) if not powerup else self.remove_asset(collides_with)

    def check_collisions(self) -> None:
        self.process_collision() if self.player_hit() else None

    def get_asset_positions(self) -> list[tuple]:
        return [(str(id(i)), i.lane_pos, i.frame_count) for i in self.assets]

    def advance_assets(self) -> None:
        list(map(lambda a: a.advance(self), self.assets))

    def advance(self) -> None:
        self.player_car.update_ascii(), self.advance_assets()

    def __repr__(self) -> str:
        return "\n".join(
            [
                self.barrier,
                *[
                    "\n".join(
                        [
                            self.create_ascii_lane(i),
                            self.lane if i % 2 == 0 and i != 0 else "",
                        ]
                    )
                    for i in range(self.width)
                ],
                self.barrier,
            ]
        )


class Player(object):
    def __init__(self, Settings: object):
        self.game_rules, self.power, self.ascii = Settings, None, DEFAULT_PLAYER_CAR
        self.sx, self.sy = measure_asset(self.ascii)
        self.lane_pos = self.bullet_spacing = 0

    def move_lane(self, direction: str) -> None:
        lf = (self.game_rules.nlanes * 2) - 1
        self.lane_pos = (
            self.lane_pos - 1 if "u" in set(direction) else self.lane_pos + 1
        )
        self.lane_pos = (
            lf
            if self.lane_pos < 0
            else self.lane_pos and 0
            if self.lane_pos > lf
            else self.lane_pos
        )

    def update_ascii(self) -> None:
        if not self.power:
            self.ascii = DEFAULT_PLAYER_CAR
        elif "s" in set(self.power):
            self.ascii = (
                DEFAULT_PLAYER_CAR
                if "m" in set(self.ascii)
                else color_string_on_console_stdout("green", DEFAULT_PLAYER_CAR)
            )
        else:
            if DEFAULT_BULLET not in set(self.ascii):
                self.ascii = DEFAULT_PLAYER_CAR + DEFAULT_BULLET
            else:
                self.bullet_spacing = (
                    DEFAULT_BULLET_SPEED + self.bullet_spacing
                ) % DEFAULT_BULLET_FRAME_CYCLE
                self.ascii = (
                    DEFAULT_PLAYER_CAR
                    + self.game_rules.open_char
                    * (self.bullet_spacing % self.game_rules.window_len)
                    + DEFAULT_BULLET
                )

    def gain_powers(self, Asset):
        self.power = Asset.name

    def loose_powers(self):
        self.power, self.bullet_spacing = None, 0


class Approacher(object):
    def __init__(self, is_obstacle: bool, Settings: object):
        self.is_obstacle, self.a_id = is_obstacle, str(id(self))
        self.name, self.ascii = random.choice(OBSTACLES if is_obstacle else POWERUPS)
        self.lane_pos = random.choice([i for i in range(Settings.nlanes * 2)])
        self.sx, self.sy = measure_asset(self.ascii)
        self.frame_count, self.last_jumped = self.sx, time.time()

    def advance(self, Road: object) -> None:
        if round(time.time() - self.last_jumped) > Road.game_rules.asset_jump_time:
            prev_lane = [i[1] for i in Road.get_asset_positions() if i[0] == self.a_id][
                0
            ]
            self.lane_jump(Road.width - 1)
            self.last_jumped = time.time()
            self.adjust_after_jump(prev_lane, Road)
        self.frame_count += 1

    def adjust_after_jump(self, prev: list[tuple], Road: object):
        li_assets, lf_assets = Road.in_lane(prev), list(
            filter(lambda x: x.a_id != self.a_id, Road.in_lane(self.lane_pos))
        )
        if not li_assets and not lf_assets:
            return
        if li_assets:
            Road.shift_lane_assets(li_assets, -self.sx)
        if lf_assets:
            Road.shift_lane_assets(lf_assets, self.sx)

    def shift(self, units):
        self.frame_count += units

    def lane_jump(self, lf):
        self.lane_pos += np.random.choice(np.arange(-1, 2, 2))
        self.lane_pos = (
            lf
            if self.lane_pos < 0
            else self.lane_pos and 0
            if self.lane_pos > lf
            else self.lane_pos
        )


class Game(object):
    def __init__(self):
        self.Keys, self.Road = KeyListner(), Road()

    def process_inputs(self) -> None:
        if self.Keys.direction or self.Keys.quit:
            if self.Keys.quit:
                print("***EXITING GAME***"), exit()
            else:
                self.Road.move_lane(self.Keys)

    def update(self) -> None:
        def update_ai() -> None:
            self.Road.try_lvl_up(), self.Road.try_spawn(), self.Road.try_destroy()

        def update_physics() -> None:
            self.Road.flip_mid_lane(), self.Road.advance(), self.Road.check_collisions()

        update_ai(), update_physics()

    def calc_score(self, t, t_start, level) -> str:
        return str(round(round(t - t_start, 2) * level))

    def render(self, t, t_start) -> None:
        run("clear")
        buff, mid = "\n" * 2, "\t" * 3
        print(
            "ASCII DRIVER",
            f"{buff*2}{mid}SCORE: {self.calc_score(t,t_start,self.Road.num_lanes)}",
            f"LEVEL:{self.Road.game_rules.lvl}",
            buff,
            self.Road,
            buff,
            "MOVE WITH ARROW-KEYS : [↑] & [↓]",
            "QUIT:[ESC]",
            sep="\n",
        )
        time.sleep(self.Road.game_rules.t_per_frame)

    def main_game_loop(self):
        start = time.time()
        while True:
            self.process_inputs(), self.update(), self.render(time.time(), start)


if __name__ == "__main__":
    Game().main_game_loop()
