#!/usr/bin/env python
import os
import os.path
import sys
import subprocess
import tempfile

template = """
#EVENT DEMOSTART 1
[
#EVENT_END

#EVENT DEMOEND 2
{}
]
#EVENT_END

#FILE output frags.json

#EVENT MATCHSTART_ALL 20
{ "timestamp": 0.0, "player_id": %playerid%, "name": "%nameraw%", "team": "%team%", "frags": 0, "deaths": 0 },
#EVENT_END

#EVENT FRAG 21
{ "timestamp": %demotime%, "player_id": %playerid%, "name": "%nameraw%", "team": "%team%", "frags": %frags%, "deaths": %deaths% },
#EVENT_END

#EVENT DEATH 22
{ "timestamp": %demotime%, "player_id": %playerid%, "name": "%nameraw%", "team": "%team%", "frags": %frags%, "deaths": %deaths% },
#EVENT_END

#OUTPUT 1  output
#OUTPUT 20 output
#OUTPUT 21 output
#OUTPUT 22 output

#OUTPUT 2  output

////////////////////////////////////////////////////////////
// Events: Quads, Pents, Caps...                          //
////////////////////////////////////////////////////////////
#FILE items items.json

#EVENT MATCHSTART_ALL 50
{ "timestamp": 0.0, "player_id": %playerid%, "quad": 0, "pent": 0, "flagtk": 0, "flagcap": 0 },
#EVENT_END

#EVENT ITEMPICKUP 51
{ "timestamp": %demotime%, "player_id": %playerid%, "quad": %quadcount%, "pent": %pentcount%, "flagtk": %flagtouch%, "flagcap": %flagcap% },
#EVENT_END

#OUTPUT 1 items
#OUTPUT 50 items
#OUTPUT 51 items
#OUTPUT 2 items
"""

template_runes = """
#FILE json runes.json

#EVENT MATCHEND 1
[
#EVENT_END

#EVENT MATCHEND_ALL 2
{ "name": %name%, "res": %runerestime%, "str": %runestrtime%, "hst": %runehsttime%, "reg": %runeregtime% }
#EVENT_END

#EVENT MATCHEND_ALL_BETWEEN 3
,
#EVENT_END

#EVENT MATCHEND_FINAL 4
]
#EVENT_END

#OUTPUT 1 json
#OUTPUT 2 json
#OUTPUT 4 json
"""

fragfile = """
#FRAGFILE   VERSION         ezquake-1.00        //DONT CHANGE THIS

#DEFINE FLAG_ALERT  X_TOUCHES_FLAG  " got the RED flag!"
#DEFINE FLAG_ALERT  X_TOUCHES_FLAG  " got the BLUE flag!"

#DEFINE FLAG_ALERT  X_DROPS_FLAG    " lost the RED flag!"
#DEFINE FLAG_ALERT  X_DROPS_FLAG    " lost the BLUE flag!"

#DEFINE FLAG_ALERT  X_DROPS_FLAG    " tossed the RED flag!"
#DEFINE FLAG_ALERT  X_DROPS_FLAG    " tossed the BLUE flag!"

#DEFINE FLAG_ALERT  X_CAPTURES_FLAG " captured the RED flag!"
#DEFINE FLAG_ALERT  X_CAPTURES_FLAG " captured the BLUE flag!"

#DEFINE FLAG_ALERT  X_ASSISTS_FLAG  " gets an assist for returning his flag!"
#DEFINE FLAG_ALERT  X_ASSISTS_FLAG  " gets an assist for fragging the flag carrier!"

#DEFINE FLAG_ALERT  X_RETURNS_FLAG  " returned the RED flag!"
#DEFINE FLAG_ALERT  X_RETURNS_FLAG  " returned the BLUE flag!"

#DEFINE FLAG_ALERT  X_RUNE_RES    "You got the resistance rune"
#DEFINE FLAG_ALERT  X_RUNE_STR    "You got the strength rune"
#DEFINE FLAG_ALERT  X_RUNE_HST    "You got the haste rune"
#DEFINE FLAG_ALERT  X_RUNE_REG    "You got the regeneration rune"
"""

def exists(path):
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return False

if len(sys.argv) < 2:
    raise SystemExit("ERR: Need demo argument")

demofile = sys.argv[1]

os.makedirs("process", exist_ok=True)

with open("process/template.dat", "w") as fd:
    fd.write(template)

with open("process/fragfile.dat", "w") as fd:
    fd.write(fragfile)


workfile = "process/demo.mvd"

if exists(workfile):
    if not os.path.islink(workfile):
        raise SystemExit(f"ERR: {workfile} is not a symlink!")
    os.unlink(workfile)

if exists("process/frags.json"):
    os.unlink("process/frags.json")

if exists("process/items.json"):
    os.unlink("process/items.json")

os.symlink(demofile, workfile)

subprocess.run(["mvdparser", "demo.mvd"], cwd="process", capture_output=True)

if not exists("process/frags.json"):
    raise SystemExit("ERR: No frags.json generated")

if not exists("process/items.json"):
    raise SystemExit("ERR: No items.json generated")

basename, _ = os.path.splitext(os.path.basename(demofile))

os.rename("process/frags.json", f"process/{basename}.frags.json")
os.rename("process/items.json", f"process/{basename}.items.json")

visualize = os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "vis2.py")

subprocess.run([visualize, f"{basename}"], cwd="process")

os.unlink(f"process/{basename}.frags.json")
os.unlink(f"process/{basename}.items.json")
