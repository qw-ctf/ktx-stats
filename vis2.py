#!/usr/bin/env python
import pandas as pd
import json
import sys

players = set([])

result = {
    "frags": [],
    "events": []
}

demo = sys.argv[1]

with open(f"{demo}.frags.json") as fd:
    frags = json.load(fd)[:-1] # [:-1] due to hacky stats generator

with open(f"{demo}.items.json") as fd:
    items = json.load(fd)[:-1] # [:-1] due to hacky stats generator

result["players"] = list(set((event["player_id"], event["team"], event["name"]) for event in frags))

frags_df = pd.DataFrame(frags)

deaths_df = frags_df[["timestamp", "player_id", "deaths"]].copy()
deaths_df.drop_duplicates(subset=["player_id", "deaths"], inplace=True)

frags_df = frags_df.pivot_table(index=["timestamp"], columns=["team", "player_id"], values=["frags", "deaths"]).ffill()

teamscore = frags_df["frags"].groupby(axis=1, level=0).sum()
teamscore["delta"] = teamscore["red"] - teamscore["blue"]

max_delta = max(abs(teamscore["delta"].min()), teamscore["delta"].max())
teamscore["delta_scaled"] = teamscore["delta"] / max_delta

for timestamp, event in teamscore.iterrows():
    result["frags"].append((timestamp, round(event["delta_scaled"], 4)))


items_df = pd.DataFrame(items)
by_type = items_df.melt(id_vars=["timestamp", "player_id"])
by_type["delta"] = by_type.groupby(["player_id", "variable"])["value"].diff()
events = by_type[by_type["delta"] > 0].sort_values(by=["timestamp"])

for idx, event in events.iterrows():
    if event.variable == "quad":
        filter_player = (deaths_df["player_id"] == event.player_id)
        filter_quad_time = (deaths_df["timestamp"].between(event.timestamp, event.timestamp + 30))
        quad_death = deaths_df[filter_player & filter_quad_time][:1]
        quad_time = 1.0
        if quad_death.size > 0:
            quad_time = (quad_death["timestamp"].values[0] - event.timestamp) / 30
        result["events"].append((event["timestamp"], event["player_id"], "quad", event["value"], round(quad_time * 100.0, 0)))
    elif event.variable == "pent":
        result["events"].append((event["timestamp"], event["player_id"], "pent", event["value"], None))
    elif event.variable == "flagcap":
        filter_player = (events["player_id"] == event.player_id)
        filter_take = (events["variable"] == "flagtk")
        filter_take_time = (events["timestamp"] < event.timestamp)
        flag_take = events[filter_player & filter_take & filter_take_time][-1:]
        result["events"].append((event["timestamp"], event["player_id"], "capture", event["value"], flag_take["timestamp"].values[0]))

basename = demo.rstrip(".mvd")

with open(f"{basename}.extra.json", "w") as fd:
    json.dump(result, fd)
