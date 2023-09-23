from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List
import datetime
import json
import logging
import pathlib
import re
import sys

from . import proto

logger = logging.getLogger(__name__)

@dataclass
class Player:
    client_num: int
    name: str
    raw_name: str
    team: str = ""
    frags: int = 0
    quads: int = 0
    spectator: bool = False
    info: dict = field(default_factory=lambda: defaultdict(int))
    has_flag: int = -1
    top_color: int = 0
    bottom_color: int = 0


@dataclass
class State:
    players: Dict[int, Player] = field(default_factory=dict)
    players_by_name: Dict[str, Player] = field(default_factory=dict)
    time: int = 0
    duration: int = 0
    map_name: str = ""
    msg_buffer: List[str] = field(default_factory=list)

    last_quad_time: int = 0
    last_quad_player: Player = None

    frags: list = field(default_factory=list)
    items: list = field(default_factory=list)

    def set_player_name(self, client_num, name):
        player = self.players.get(client_num)
        if not player:
            player = Player(client_num, fix_text(name), name)
            self.players[client_num] = player
        else:
            player.name = fix_text(name)
            player.raw_name = name
        self.players_by_name[player.raw_name] = player
        return player

    def log_frags(self, player, suicide=False):
        self.frags.append((
            self.time,
            player.client_num,
            player.frags if not suicide else player.frags - 1,
            player.info["deaths"]
        ))

    def log_items(self, player):
        self.items.append((
            self.time,
            player.client_num,
            player.info["quad_count"],
            player.info["pent_count"],
            player.info["ctf-pickups"],
            player.info["ctf-caps"],
        ))

def _format_time(seconds):
    frac = seconds * 1e5
    seconds = frac // int(1e5)
    frac = frac % int(1e5)

    minutes = seconds // 60
    seconds = seconds % 60

    minutes = int(minutes)
    seconds = int(seconds)
    frac = int(frac)

    out = f'{seconds:02d}.{frac:05d}'
    if minutes != 0:
        out = f'{minutes}:{out}'
    return out

def fix_text(n):
    lookupTable = {
        0: "=",
        2: "=",
        5: "•",
        10: " ",
        14: "•",
        15: "•",
        16: "[",
        17: "]",
        18: "0",
        19: "1",
        20: "2",
        21: "3",
        22: "4",
        23: "5",
        24: "6",
        25: "7",
        26: "8",
        27: "9",
        28: "•",
        29: "=",
        30: "=",
        31: "="
    }
    return "".join(
        map(
            lambda c: chr(c) if c >= 32 else lookupTable.get(c, '?'),
            map(
                lambda c: c if c < 128 else c - 128,
                map(ord, n)
            )
        )
    )


def demo_stats_entrypoint(events):
    demo_path = pathlib.Path(sys.argv[1])

    state = State()

    ignored = set([
        proto.ServerMessageType.CDTRACK,
        proto.ServerMessageType.CENTERPRINT,
        proto.ServerMessageType.CLIENTDATA,
        proto.ServerMessageType.DISCONNECT,
        proto.ServerMessageType.FOUNDSECRET,
        proto.ServerMessageType.KILLEDMONSTER,
        proto.ServerMessageType.LIGHTSTYLE,
        proto.ServerMessageType.PARTICLE,
        proto.ServerMessageType.SETANGLE,
        proto.ServerMessageType.SETVIEW,
        proto.ServerMessageType.SIGNONNUM,
        proto.ServerMessageType.SOUND,
        proto.ServerMessageType.SPAWNBASELINE,
        proto.ServerMessageType.SPAWNSTATIC,
        proto.ServerMessageType.SPAWNSTATICSOUND,
        proto.ServerMessageType.STUFFTEXT,
        proto.ServerMessageType.TEMP_ENTITY,
        proto.ServerMessageType.UPDATE,
        proto.ServerMessageType.UPDATESTAT,
    ])

    with demo_path.open('rb') as f:
        for msg_end, view_angle, msg in proto.read_demo_file(f):
            if msg.msg_type == proto.ServerMessageType.SERVERINFO:
                state.map_name = msg.models[0].rsplit('/', 1)[1].split('.', 1)[0]
                map_name = msg.level_name
                print(state.map_name, map_name)
            elif msg.msg_type == proto.ServerMessageType.TIME:
                state.time = msg.time
            elif msg.msg_type in (proto.ServerMessageType.INTERMISSION,
                                  proto.ServerMessageType.FINALE):
                if state.time > state.duration:
                    state.duration = state.time
            elif msg.msg_type == proto.ServerMessageType.UPDATENAME:
                if not msg.name:
                    continue
                state.set_player_name(msg.client_num, msg.name)
            elif msg.msg_type == proto.ServerMessageType.UPDATEFRAGS:
                if msg.count != 0:
                    # delta = msg.count - state.players[msg.client_num].frags
                    # p0 = state.players[msg.client_num]
                    # altsum = p0.info.get("ctf-points", 0) + p0.info.get("kills", 0) - p0.info.get("suicides", 0)
                    # matches = "MATCHES" if altsum == msg.count else "DIFF %d" % (msg.count - altsum)
                    # print(int(state.time), state.players[msg.client_num].name, msg.count, "alt:", altsum, "this delta:", delta, matches)
                    state.players[msg.client_num].frags = msg.count
                    state.log_frags(state.players[msg.client_num])
            elif msg.msg_type == proto.ServerMessageType.UPDATECOLORS:
                player = state.players.get(msg.client_num)
                if not player:
                    continue # non-client
                player.top_color = (msg.color & 0xf0) >> 4
                player.bottom_color = msg.color & 0x0f
                if 4 in (player.top_color, player.bottom_color):
                    player.team = "red"
                elif 13 in (player.top_color, player.bottom_color):
                    player.team = "blue"
                else:
                    player.spectator = True
            elif msg.msg_type == proto.ServerMessageType.PRINT:
                if ord(msg.string[0]) == 1:
                    print("chat:", fix_text(msg.string[1:]))
                    continue
                elif ord(msg.string[0]) == 2:
                    print("server:", fix_text(msg.string[1:]))
                    continue

                if msg.string[-1] == '\n':
                    state.msg_buffer.append(msg.string[:-1])
                    found = False
                    for event in events:
                        if event.apply(state, state.msg_buffer):
                            found = True
                            break
                    if not found:
                        logger.debug("NOT FOUND: '%s'", "".join(map(fix_text, state.msg_buffer)))
                    state.msg_buffer.clear()
                else:
                    state.msg_buffer.append(msg.string)
            elif msg.msg_type not in ignored:
                print(msg.msg_type)

    for p in sorted(state.players.values(), key=lambda x: x.frags, reverse=True):
        if p.spectator:
            continue
        kills = p.info.get("kills", 0)
        suicides = p.info.get("suicides", 0)
        points = p.info.get("ctf-points", 0)
        print(p.name, p.team, p.frags, "kills", kills, "ctf-points", points, "sum", kills + points - suicides, "delta", p.frags - (kills + points - suicides))
        print(p.info)

    frag_events = []
    for player in state.players.values():
        if player.spectator:
            continue
        frag_events.append({
            "timestamp": 0,
            "player_id": player.client_num,
            "name": player.raw_name,
            "team": player.team,
            "frags": 0,
            "deaths": 0
        })

    for ts, client_num, frags, deaths in state.frags:
        player = state.players[client_num]
        frag_events.append({
            "timestamp": ts,
            "player_id": client_num,
            "name": player.raw_name,
            "team": player.team,
            "frags": frags,
            "deaths": deaths
        })

    with open("frags.json", "w") as fd:
        json.dump(frag_events, fd)

    item_events = []
    for player in state.players.values():
        if player.spectator:
            continue
        item_events.append({
            "timestamp": 0,
            "player_id": player.client_num,
            "quad": 0,
            "pent": 0,
            "flagtk": 0,
            "flagcap": 0
        })

    for ts, client_num, quads, pents, pickups, captures in state.items:
        item_events.append({
            "timestamp": ts,
            "player_id": client_num,
            "quad": quads,
            "pent": pents,
            "flagtk": pickups,
            "flagcap": captures
        })

    with open("items.json", "w") as fd:
        json.dump(item_events, fd)

    players = []
    for player in state.players.values():
        if player.spectator:
            continue
        player_stats = {
            "top-color": player.top_color,
            "bottom-color": player.bottom_color,
            "ping": 0,
            "login": "",
            "name": player.raw_name,
            "team": player.team,
            "client": "Quake 1.07",
            "player_id": str(player.client_num),
            "stats": {
                "frags": player.frags,
                "deaths": player.info["deaths"],
                "tk": player.info["tkills"],
                "spawn-frags": 0,
                "kills": player.info["kills"],
                "suicides": player.info["suicides"],
            },
            "dmg": {
                "taken": 0,
                "given": 0,
                "team": 0,
                "self": 0,
                "team-weapons": 0,
                "enemy-weapons": 0,
                "taken-to-die": 0,
            },
            "xfer": 0,
            "spree": {
                "max": 0,
                "quad": 0,
            },
            "control": 0,
            "speed": {
                "max": 0,
                "avg": 0,
            },
            "weapons": {
            },
            "items": {
                "health_15": {
                    "took": 0,
                },
                "health_25": {
                    "took": 0,
                },
                "health_100": {
                    "took": 0,
                },
                "ga": {
                    "took": 0,
                },
                "ya": {
                    "took": 0,
                },
                "ra": {
                    "took": 0,
                },
                "q": {
                    "took": player.info["quad_count"],
                    "time": 0,
                },
                "p": {
                    "took": 0,
                    "time": 0,
                },
                "r": {
                    "took": 0,
                },
            },
            "ctf": {
                "points": player.info["ctf-points"],
                "caps": player.info["ctf-caps"],
                "carrier-frags": player.info["ctf-carrier-frags"],
                "carrier-defends": player.info["ctf-carrier-defends"],
                "pickups": player.info["ctf-pickups"],
                "returns": player.info["ctf-returns"],
                "runes": [0, 0, 0, 0],
            }
        }

        weapons = [
            ("sg", "shotgun"),
            ("ssg", "super_shotgun"),
            ("ng", "nailgun"),
            ("sng", "super-nailgun"),
            ("gl", "grenade-launcher"),
            ("rl", "rocket-launcher"),
            ("lg", "lightning-gun")
        ]

        for shortname, weapon in weapons:
            player_stats["weapons"][shortname] = {
                "acc": {
                    "attacks": 0,
                    "hits": 0,
                },
                "kills": {
                    "total": player.info[f"kills-{weapon}"],
                    "team": 0,
                    "enemy": player.info[f"kills-{weapon}"],
                    "self": player.info[f"suicide-{weapon}"],
                },
                "deaths": player.info[f"deaths-{weapon}"],
            }
        players.append(player_stats)

    stats = {
        "version": 3,
        "date": "1997-05-25 20:00:00 +0100",
        "map": state.map_name,
        "hostname": "anka.pobox.se",
        "ip": "127.0.0.1",
        "port": 26000,
        "mode": "ctf",
        "tl": 20,
        "dm": 1,
        "tp": 4,
        "duration": 1200,
        "demo": "sm_970525_cop_vs_tfa_part1_e2m2.dem",
        "teams": [
            "red",
            "blue",
        ],
#        "clans": {
#            "red": {
#                "name": "Combat Plebs",
#                "short": "CoP"
#            },
#            "blue": {
#                "name": "The Fallen Angels",
#                "short": "TFA"
#            }
#        },
        "players": players
    }

    with open("stats.json", "w") as fd:
        json.dump(stats, fd)


pattern = re.compile('#DEFINE\\s+(?:(?:(?P<type1>[^\\s]+)\\s+(?P<subtype1>[^\\s]+)\\s+(?P<cause1>[^\\s]+))|(?:(?P<type2>[^\\s]+)\\s+(?P<subtype2>[^\\s]+)))\\s+"(?P<msg1>[^"]+)"(?:\\s+"(?P<msg2>[^"]+)")?(?:\\s+"(?P<msg3>[^"]+)")?.*')


class ConstMatcher:
    def __init__(self, value):
        self.value = value

    def test(self, state, msg):
        return msg == self.value

    def __repr__(self):
        return self.value


class PlayerMatcher:
    def test(self, state, msg):
        return state.players_by_name.get(msg)

    def __repr__(self):
        return "<player>"


def carrier(state):
    players = []
    for player in state.players.values():
        if player.has_flag > 0:
            players.append(player.name)
    return players


class FragEvent:
    def __init__(self, matchers, cause=None):
        self.matchers = matchers

        if cause is not None and cause.startswith("Q_"):
            self.cause = cause[2:]
            self.quad = True
        else:
            self.cause = cause
            self.quad = False

    def apply(self, state, messages):
        players = []
        for (matcher, message) in zip(self.matchers, messages):
            result = matcher.test(state, message)
            if not result:
                return False
            if isinstance(result, Player):
                players.append(result)
        logger.debug(
            "%d %s %s, carriers: %s",
            int(state.time),
            self.__class__.__name__,
            ", ".join(map(lambda x: x.name, players)),
            ", ".join(carrier(state))
        )
        self.update_stats(state, players)
        return True

    def update_stats(self, players):
        raise NotImplementedError(f"{self.__class__.__name__} does not update stats")

    def __repr__(self):
        return repr(self.matchers)


class FragEventPlayerDeath(FragEvent):
    def __init__(self, cause, msg1):
        super(FragEventPlayerDeath, self).__init__([
            PlayerMatcher(),
            ConstMatcher(msg1)
        ], cause)

    def update_stats(self, state, players):
        players[0].info["deaths"] += 1

        state.log_frags(players[0], suicide=True)
        if state.last_quad_player == players[0]:
            state.last_quad_player = None
            state.last_quad_time = -score.quad_duration


class FragEventPlayerSuicide(FragEvent):
    def __init__(self, cause, msg1):
        super(FragEventPlayerSuicide, self).__init__([
            PlayerMatcher(),
            ConstMatcher(msg1)
        ], cause)

    def update_stats(self, state, players):
        players[0].info["suicides"] += 1
        players[0].info["deaths"] += 1

        weapon = self.cause.lower().replace("_", "-")

        players[0].info[f"suicide-{weapon}"] += 1


        state.log_frags(players[0], suicide=True)
        if state.last_quad_player == players[0]:
            state.last_quad_player = None
            state.last_quad_time = -score.quad_duration


@dataclass
class Settings:
    quad_duration: int = 30
    carrier_frag_timeout: int = 2
    carrier_frag_bonus: int = 2
    carrier_defend_bonus: int = 1
    carrier_danger_defend_bonus: int = 2
    flag_defend_bonus: int = 1
    capture_carrier_bonus: int = 15
    capture_team_bonus: int = 10
    flag_return_bonus: int = 1


score = Settings()


class FragEventXFraggedByY(FragEvent):
    def __init__(self, cause, msg1, msg2):
        super(FragEventXFraggedByY, self).__init__([
            PlayerMatcher(),
            ConstMatcher(msg1),
            PlayerMatcher(),
            ConstMatcher(msg2)
        ] if msg2 is not None else [
            PlayerMatcher(),
            ConstMatcher(msg1),
            PlayerMatcher()
        ], cause)

    def update_stats(self, state, players):
        players[0].info["deaths"] += 1
        players[1].info["kills"] += 1

        weapon = self.cause.lower().replace("_", "-")

        players[0].info[f"deaths-{weapon}"] += 1
        players[1].info[f"kills-{weapon}"] += 1

        state.log_frags(players[0])

        if players[0].team == players[1].team:
            players[1].info["tkills"] += 1

        if self.quad:
            if state.last_quad_player != players[1]:
                state.last_quad_time = state.time
                state.last_quad_player = players[1]
                players[1].info["quad_count"] += 1
                state.log_items(players[1])
        elif self.cause in ("ROCKET_LAUNCHER", "LIGHTNING_GUN") and players[1] == state.last_quad_player:
            state.last_quad_player = None
            state.last_quad_time = -score.quad_duration

        if state.last_quad_player == players[0]:
            state.last_quad_player = None
            state.last_quad_time = -score.quad_duration

        if state.last_quad_player is not None and state.time > (state.last_quad_time + score.quad_duration):
            state.last_quad_player = None
            state.last_quad_time = -score.quad_duration

        # print(state.time, self.quad, self.cause, players[0].name, players[1].name)
        # print("QUAD PLAYER:", (state.last_quad_player.name + " " + self.cause) if state.last_quad_player else "")

        if (players[0].has_flag > 0):
            logger.debug("%d carrier time: %s %.2f", state.time, players[0].name, state.time - players[0].has_flag)
            if (state.time - players[0].has_flag) > score.carrier_frag_timeout:
                players[1].info["ctf-points"] += score.carrier_frag_bonus


class FragEventFlagBase(FragEvent):
    def __init__(self, *msgs):
        super(FragEventFlagBase, self).__init__([
            PlayerMatcher(),
        ] + list(map(ConstMatcher, msgs)))


class FlagEventTouchesFlag(FragEventFlagBase):
    def __init__(self, msg):
        super(FlagEventTouchesFlag, self).__init__(msg)

    def update_stats(self, state, players):
        players[0].info["ctf-pickups"] += 1
        players[0].has_flag = state.time
        state.log_items(players[0])

class FlagEventDropsFlag(FragEventFlagBase):
    def __init__(self, msg):
        super(FlagEventDropsFlag, self).__init__(msg)

    def update_stats(self, state, players):
        players[0].info["ctf-drops"] += 1
        players[0].has_flag = -1



class FlagEventCapturesFlag(FragEventFlagBase):
    def __init__(self, msg):
        super(FlagEventCapturesFlag, self).__init__(msg)

    def update_stats(self, state, players):
        players[0].info["ctf-caps"] += 1
        players[0].has_flag = -1
        state.log_items(players[0])
        for player in state.players.values():
            if player.name == players[0].name:
                player.info["ctf-points"] += score.capture_carrier_bonus
            elif player.team == players[0].team:
                player.info["ctf-points"] += score.capture_team_bonus


class FlagEventFlagReturnAssist(FragEventFlagBase):
    def __init__(self, msg):
        super(FlagEventFlagReturnAssist, self).__init__(msg)

    def update_stats(self, state, players):
        players[0].info["ctf-returns"] += 1
        players[0].info["ctf-points"] += 1


class FlagEventFlagFragAssist(FragEventFlagBase):
    def __init__(self, msg):
        super(FlagEventFlagFragAssist, self).__init__(msg)

    def update_stats(self, state, players):
        players[0].info["ctf-carrier-frags"] += 1
        players[0].info["ctf-points"] += score.carrier_frag_bonus


class FlagEventFlagReturn(FragEventFlagBase):
    def __init__(self, msg):
        super(FlagEventFlagReturn, self).__init__(msg)

    def update_stats(self, state, players):
        players[0].info["ctf-returns"] += 1
        players[0].info["ctf-points"] += score.flag_return_bonus


class FlagEventFlagDefend(FragEventFlagBase):
    def __init__(self, msg):
        super(FlagEventFlagDefend, self).__init__(msg)

    def update_stats(self, state, players):
        players[0].info["ctf-flag-defends"] += 1
        players[0].info["ctf-points"] += score.flag_defend_bonus


class FlagEventFlagCarrierDefend(FragEventFlagBase):
    def __init__(self, *msgs):
        super(FlagEventFlagCarrierDefend, self).__init__(*msgs)

    def update_stats(self, state, players):
        players[0].info["ctf-carrier-defends"] += 1
        players[0].info["ctf-points"] += score.carrier_defend_bonus


class FlagEventFlagCarrierDangerDefend(FragEventFlagBase):
    def __init__(self, *msgs):
        super(FlagEventFlagCarrierDangerDefend, self).__init__(*msgs)

    def update_stats(self, state, players):
        players[0].info["ctf-carrier-defends"] += 1
        players[0].info["ctf-points"] += score.carrier_danger_defend_bonus



def load_fragfile():
    msgs = []
    with open("fragfile.dat", "r", encoding="latin1") as fd:
        for line in fd:
            message_found = True

            if not line.startswith("#DEFINE"):
                continue

            line = line.rstrip("\n")

            type1, subtype1, cause, type2, subtype2, msg1, msg2, msg3 = pattern.match(line).groups()
            if type1 == "WEAPON_CLASS" or type2 == "WEAPON_CLASS":
                continue
            elif type1 == "OBITUARY":
                if subtype1 == "PLAYER_DEATH":
                    msgs.append(FragEventPlayerDeath(cause, msg1))
                elif subtype1 == "PLAYER_SUICIDE":
                    msgs.append(FragEventPlayerSuicide(cause, msg1))
                elif subtype1 == "X_FRAGGED_BY_Y":
                    msgs.append(FragEventXFraggedByY(cause, msg1, msg2))
                else:
                    message_found = False
            elif type2 == "FLAG_ALERT":
                if subtype2 == "X_TOUCHES_FLAG":
                    msgs.append(FlagEventTouchesFlag(msg1))
                elif subtype2 == "X_DROPS_FLAG":
                    msgs.append(FlagEventDropsFlag(msg1))
                elif subtype2 == "X_CAPTURES_FLAG":
                    msgs.append(FlagEventCapturesFlag(msg1))
                elif subtype2 == "X_FLAG_ASSIST_RETURN":
                    msgs.append(FlagEventFlagReturnAssist(msg1))
                elif subtype2 == "X_FLAG_ASSIST_FRAG":
                    msgs.append(FlagEventFlagFragAssist(msg1))
                elif subtype2 == "X_FLAG_RETURN":
                    msgs.append(FlagEventFlagReturn(msg1))
                elif subtype2 == "X_FLAG_DEFEND":
                    msgs.append(FlagEventFlagDefend(msg1))
                elif subtype2 == "X_CARRIER_DANGER_DEFEND":
                    parts = list(filter(lambda x: x, (msg1, msg2, msg3)))
                    msgs.append(FlagEventFlagCarrierDangerDefend(*parts))
                elif subtype2 == "X_CARRIER_DEFEND":
                    parts = list(filter(lambda x: x, (msg1, msg2, msg3)))
                    msgs.append(FlagEventFlagCarrierDefend(*parts))
                else:
                    message_found = False
            else:
                message_found = False

            if not message_found:
                raise NotImplementedError(f"Message not found: '{line}'")

    return msgs

# #DEFINE\s(?:(?:(?P<type1>[^\s]+)\s+(?P<subtype1>[^\s]+)\s+(?P<cause1>[^\s]+))|(?:(?P<type2>[^\s]+)\s+(?P<subtype2>[^\s]+)))\s+"(?P<prefix>[^"]+)"(?:\s+"(?P<suffix>[^"]+)")?.*


evs = load_fragfile()

demo_stats_entrypoint(evs)
