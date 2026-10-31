"""Explainable A* itinerary ordering for selected attractions.

The optimizer orders a selected set of attractions for ONE geographic area/day. It uses
A* over (last stop, visited-set) states and an admissible MST lower-bound heuristic. Travel
minutes are derived from supplied pairwise estimates when present, otherwise from haversine
distance at a conservative configurable average speed. The fallback is an estimate, not live
road/public-transport routing. Opening hours and visit duration are enforced during expansion.
"""
from __future__ import annotations

from datetime import datetime
from heapq import heappop, heappush
from math import asin, cos, radians, sin, sqrt
from typing import Any


def haversine_km(a: dict, b: dict) -> float:
    lat1, lon1, lat2, lon2 = map(float, (a["lat"], a["lon"], b["lat"], b["lon"]))
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(min(1.0, h)))


def _clock(value: str) -> int:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except (TypeError, ValueError):
        raise ValueError(f"Time '{value}' must use 24-hour HH:MM format.")
    return parsed.hour * 60 + parsed.minute


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _travel_matrix(nodes: list[dict], speed_kmh: float, supplied: dict | None) -> list[list[int]]:
    matrix = []
    for i, a in enumerate(nodes):
        row = []
        for j, b in enumerate(nodes):
            if i == j:
                row.append(0)
                continue
            key1, key2 = f"{a['id']}->{b['id']}", f"{b['id']}->{a['id']}"
            minutes = (supplied or {}).get(key1, (supplied or {}).get(key2))
            if minutes is None:
                minutes = haversine_km(a, b) / speed_kmh * 60
            try:
                minutes = float(minutes)
            except (TypeError, ValueError):
                raise ValueError(f"Travel time for {key1} must be numeric.")
            if minutes < 0 or minutes != minutes or minutes == float("inf"):
                raise ValueError(f"Travel time for {key1} must be finite and non-negative.")
            row.append(int(round(minutes)))
        matrix.append(row)
    return matrix


def _mst_cost(remaining: tuple[int, ...], matrix: list[list[int]]) -> int:
    """Minimum spanning-tree lower bound over remaining attractions."""
    if len(remaining) < 2:
        return 0
    visited = {remaining[0]}
    total = 0
    while len(visited) < len(remaining):
        best = min((matrix[u][v], v) for u in visited for v in remaining if v not in visited)
        total += best[0]
        visited.add(best[1])
    return total


def optimize_day_route(
    hotel: dict,
    attractions: list[dict],
    start_time: str = "09:00",
    end_time: str = "19:00",
    *,
    average_speed_kmh: float = 25.0,
    travel_times: dict[str, float] | None = None,
    buffer_minutes: int = 15,
    meal_break_minutes: int = 60,
) -> dict[str, Any]:
    """Find a minimum-travel-time order visiting all selected attractions in one area.

    Required attraction fields: id, name, lat, lon, visit_minutes, open_time, close_time.
    Hotel requires lat/lon. The hotel is both start and end. Every attraction must be
    schedulable within the requested daily window; otherwise a structured infeasibility
    report is returned rather than silently dropping selected stops.
    """
    if not isinstance(hotel, dict) or not all(k in hotel for k in ("lat", "lon")):
        raise ValueError("Hotel must include numeric lat and lon coordinates.")
    start, end = _clock(start_time), _clock(end_time)
    if end <= start:
        raise ValueError("Daily end time must be later than start time.")
    try:
        speed = float(average_speed_kmh)
    except (TypeError, ValueError):
        raise ValueError("Average speed must be numeric.")
    if speed <= 0 or speed != speed or speed == float("inf"):
        raise ValueError("Average speed must be finite and greater than zero.")
    if not isinstance(attractions, list):
        raise ValueError("Attractions must be a list.")
    if isinstance(buffer_minutes, bool) or not isinstance(buffer_minutes, int) or not 0 <= buffer_minutes <= 120:
        raise ValueError("Buffer between stops must be an integer from 0 to 120 minutes.")
    if isinstance(meal_break_minutes, bool) or not isinstance(meal_break_minutes, int) or not 0 <= meal_break_minutes <= 180:
        raise ValueError("Meal break must be an integer from 0 to 180 minutes.")
    if not attractions:
        return {"feasible": True, "route": [], "total_travel_minutes": 0, "total_visit_minutes": 0,
                "day_start": start_time, "day_end": end_time, "algorithm": "A* with MST heuristic",
                "explanation": "No attractions were selected."}

    normalized = []
    ids = set()
    for item in attractions:
        if not isinstance(item, dict):
            raise ValueError("Each attraction must be an object.")
        required = ("id", "name", "lat", "lon", "visit_minutes", "open_time", "close_time")
        missing = [key for key in required if key not in item]
        if missing:
            raise ValueError(f"Attraction is missing required fields: {', '.join(missing)}.")
        item = dict(item)
        item["id"] = str(item["id"])
        if item["id"] in ids:
            raise ValueError(f"Duplicate attraction id '{item['id']}'.")
        ids.add(item["id"])
        try:
            item["lat"], item["lon"] = float(item["lat"]), float(item["lon"])
            item["visit_minutes"] = int(item["visit_minutes"])
        except (TypeError, ValueError):
            raise ValueError(f"Coordinates and visit_minutes for {item['name']} must be numeric.")
        if not (-90 <= item["lat"] <= 90 and -180 <= item["lon"] <= 180):
            raise ValueError(f"Coordinates for {item['name']} are out of range.")
        if item["visit_minutes"] <= 0:
            raise ValueError(f"visit_minutes for {item['name']} must be positive.")
        item["open_min"], item["close_min"] = _clock(item["open_time"]), _clock(item["close_time"])
        if item["close_min"] <= item["open_min"]:
            raise ValueError(f"Opening hours for {item['name']} must end later on the same day.")
        normalized.append(item)

    # Hotel is index 0; attractions are 1..n. Distances and time costs are symmetric only
    # for fallback estimates. Supplied directional times override either direction if present.
    hotel_node = {"id": "__hotel__", "name": "Hotel", "lat": float(hotel["lat"]), "lon": float(hotel["lon"])}
    nodes = [hotel_node] + normalized
    matrix = _travel_matrix(nodes, speed, travel_times)
    n = len(normalized)
    full_mask = (1 << n) - 1

    def heuristic(last_node: int, mask: int) -> int:
        remaining = tuple(i + 1 for i in range(n) if not (mask & (1 << i)))
        if not remaining:
            return matrix[last_node][0]
        connection = min(matrix[last_node][i] for i in remaining)
        return connection + _mst_cost(remaining, matrix) + min(matrix[i][0] for i in remaining)

    # State carries elapsed clock time as well as visited set, so opening-hour feasibility
    # participates in search instead of being checked only after a route is chosen.
    initial = (0, 0, start)
    frontier = []
    heappush(frontier, (heuristic(0, 0), 0, initial, ()))
    best_g = {initial: 0}
    goal = None
    explored = 0
    while frontier:
        _, travel_cost, state, path = heappop(frontier)
        last_node, mask, clock = state
        if travel_cost != best_g.get(state):
            continue
        explored += 1
        if mask == full_mask:
            return_home = matrix[last_node][0]
            if clock + return_home <= end:
                goal = (travel_cost + return_home, clock + return_home, path, return_home)
                break
            continue
        for i, attraction in enumerate(normalized):
            bit = 1 << i
            if mask & bit:
                continue
            node_index = i + 1
            drive = matrix[last_node][node_index]
            arrival = clock + drive
            visit_start = max(arrival, attraction["open_min"])
            visit_end = visit_start + attraction["visit_minutes"]
            if visit_start < start or visit_end > attraction["close_min"] or visit_end > end:
                continue
            is_last_stop = (mask | bit) == full_mask
            visited_count = (mask | bit).bit_count()
            meal_after = (not is_last_stop and n >= 3 and visited_count == max(1, n // 2))
            next_clock = visit_end if is_last_stop else visit_end + buffer_minutes + (meal_break_minutes if meal_after else 0)
            if next_clock > end:
                continue
            next_state = (node_index, mask | bit, next_clock)
            next_g = travel_cost + drive
            if next_g < best_g.get(next_state, float("inf")):
                best_g[next_state] = next_g
                new_path = path + ((i, arrival, visit_start, visit_end, drive),)
                heappush(frontier, (next_g + heuristic(node_index, mask | bit), next_g, next_state, new_path))

    if goal is None:
        # Diagnose simple causes without pretending the fallback data is authoritative.
        total_visits = sum(a["visit_minutes"] for a in normalized)
        earliest_open = min(a["open_min"] for a in normalized)
        latest_close = max(a["close_min"] for a in normalized)
        reasons = []
        if total_visits > end - start:
            reasons.append("Combined visit durations exceed the available daily window, before travel time.")
        if earliest_open >= end or latest_close <= start:
            reasons.append("At least one attraction's opening window does not overlap the selected day.")
        if not reasons:
            reasons.append("No visit order satisfies all opening-hour, visit-duration, travel-time, and hotel-return constraints.")
        return {"feasible": False, "route": [], "total_travel_minutes": None, "total_visit_minutes": total_visits,
                "day_start": start_time, "day_end": end_time, "selected_count": n, "explored_states": explored,
                "algorithm": "A* with MST heuristic", "reasons": reasons,
                "suggestions": ["Extend the day if possible.", "Move one or more selected attractions to another day.",
                                "Verify attraction hours and travel-time estimates."]}

    total_travel, return_clock, path, return_minutes = goal
    route = []
    for order, (i, arrival, visit_start, visit_end, drive) in enumerate(path, start=1):
        a = normalized[i]
        route.append({"order": order, "id": a["id"], "name": a["name"], "area": a.get("area", "Unspecified area"),
                      "travel_from_previous_minutes": drive, "distance_from_previous_km": round(haversine_km(nodes[0] if order == 1 else normalized[path[order - 2][0]], a), 2), "arrival_time": _fmt(arrival),
                      "visit_start": _fmt(visit_start), "visit_end": _fmt(visit_end),
                      "visit_minutes": a["visit_minutes"], "buffer_after_minutes": (buffer_minutes if order < len(path) else 0), "meal_break_after_minutes": (meal_break_minutes if len(path) >= 3 and order == max(1, len(path) // 2) and order < len(path) else 0), "opening_hours": f"{a['open_time']}–{a['close_time']}", "hours_confidence": a.get("hours_confidence", "unknown"), "coordinate_confidence": a.get("coordinate_confidence", "unknown"), "source_note": a.get("source_note", "")})
    return {"feasible": True, "route": route, "total_travel_minutes": total_travel,
            "total_visit_minutes": sum(a["visit_minutes"] for a in normalized),
            "total_buffer_minutes": max(0, len(path) - 1) * buffer_minutes + (meal_break_minutes if len(path) >= 3 else 0),
            "meal_break_minutes": (meal_break_minutes if len(path) >= 3 else 0),
            "total_distance_km": round(sum(item["distance_from_previous_km"] for item in route) + haversine_km(normalized[path[-1][0]], hotel_node), 2),
            "hotel_return_distance_km": round(haversine_km(normalized[path[-1][0]], hotel_node), 2),
            "hotel_return_time": _fmt(return_clock), "hotel_return_travel_minutes": return_minutes,
            "day_start": start_time, "day_end": end_time, "selected_count": n,
            "explored_states": explored, "algorithm": "A* with admissible minimum-spanning-tree heuristic",
            "travel_time_source": "Provided pairwise travel estimates where supplied; otherwise haversine distance divided by configurable average speed.",
            "explanation": "All selected attractions were scheduled within their stated opening hours, and the route returns to the hotel within the selected daily window. Estimated travel times are not live routing results."}


def optimize_itinerary(hotel: dict, attractions: list[dict], start_time: str = "09:00", end_time: str = "19:00", *, average_speed_kmh: float = 25.0, travel_times: dict[str, float] | None = None, buffer_minutes: int = 15, meal_break_minutes: int = 60) -> dict[str, Any]:
    """Plan strict area-by-area coverage: each distinct area is completed on its own day.

    Area order follows first appearance in the user's selected list. This preserves a stable,
    explainable area sequence rather than inventing a geographic area order.
    """
    groups: dict[str, list[dict]] = {}
    for attraction in attractions:
        area = str(attraction.get("area") or "Unspecified area").strip() or "Unspecified area"
        groups.setdefault(area, []).append(attraction)
    days = []
    for day_number, (area, stops) in enumerate(groups.items(), start=1):
        result = optimize_day_route(hotel, stops, start_time, end_time, average_speed_kmh=average_speed_kmh, travel_times=travel_times, buffer_minutes=buffer_minutes, meal_break_minutes=meal_break_minutes)
        days.append({"day": day_number, "area": area, **result})
    infeasible = [day for day in days if not day["feasible"]]
    return {
        "feasible": not infeasible,
        "algorithm": "Geographic area grouping + A* with admissible MST heuristic",
        "coverage_policy": "All selected attractions in an area are scheduled together before moving to the next area; one area per day.",
        "buffer_minutes_between_stops": buffer_minutes,
        "meal_break_minutes": meal_break_minutes,
        "days": days,
        "selected_count": len(attractions),
        "scheduled_count": sum(len(day.get("route", [])) for day in days),
        "infeasible_areas": [day["area"] for day in infeasible],
        "explanation": ("All selected attractions were scheduled with area-by-area coverage." if not infeasible else "Some areas cannot fit within the selected daily window. No selected attractions were silently dropped; see each infeasible day for reasons and suggestions."),
    }
