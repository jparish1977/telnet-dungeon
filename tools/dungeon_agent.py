#!/usr/bin/env python3
"""Dungeon Agent — LLM-driven GM that walks the world and improves it.

Connects to the game engine in-process via AgentAdapter. The LLM sees
the map as ASCII text, reasons about improvements, and sends back
structured operations that get applied through the same GM tools a
human would use.

Usage:
    # Architect mode — spruce up dungeon floor 5
    python tools/dungeon_agent.py architect --floor 5

    # Cartographer mode — fix overworld segment 0,0
    python tools/dungeon_agent.py cartographer --segment 0,0

    # Batch architect — improve floors 3 through 20
    python tools/dungeon_agent.py architect --floor-range 3-20

    # Use remote Ollama (T7600)
    python tools/dungeon_agent.py architect --floor 5 --host 10.0.0.177

    # Spectate mode — watch what the agent is doing in real-time
    python tools/dungeon_agent.py architect --floor 5 --spectate
"""

import argparse
import asyncio
import json
import os
import sys
import urllib.request
import urllib.error

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dungeon.floor import get_floor, get_floor_size, set_floor
from dungeon.gm.map_ops import (
    export_map_ascii, export_map_json, look_text,
    apply_ops, save_floor,
)
from dungeon.persistence import save_custom_floor
from dungeon.region import load_region_index


# ── Ollama client (zero deps — just urllib) ──────────────────────

def ollama_chat(messages, model="qwen3:14b", host="localhost", port=11434,
                temperature=0.4, num_ctx=8192):
    """Send a chat request to Ollama. Returns the assistant message content."""
    url = f"http://{host}:{port}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
        },
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result.get('message', {}).get('content', '')
    except urllib.error.URLError as e:
        print(f"[ERROR] Ollama request failed: {e}")
        return None


def extract_json(text):
    """Extract a JSON object from LLM response text (handles markdown fences)."""
    # Try to find JSON in code fences first
    import re
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    # Find the first { ... } block
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    start = None
    return None


# ── System prompts ────────────────────────────────────────────────

ARCHITECT_SYSTEM = """You are the Dungeon Architect — a master builder who improves dungeon floor layouts.

You receive a dungeon floor as an ASCII grid. Your job is to make it more interesting, more fun to explore, and more atmospheric. You have these tools:

TILE CODES:
  0 = floor (walkable)
  1 = wall (impassable)
  2 = door
  3 = stairs down (must have exactly one)
  4 = stairs up (must have exactly one — this is the player spawn point)
  5 = treasure chest
  6 = fountain (heals or harms)

OPERATIONS you can use:
  {"action": "set_tile", "x": N, "y": N, "tile": N}
  {"action": "set_range", "x1": N, "y1": N, "x2": N, "y2": N, "tile": N}
  {"action": "place_room", "x": N, "y": N, "w": N, "h": N, "door_side": "north|south|east|west"}
  {"action": "carve_corridor", "x1": N, "y1": N, "x2": N, "y2": N}
  {"action": "flood_fill", "x": N, "y": N, "tile": N}

RULES:
- Keep exactly ONE stairs up (tile 4) and ONE stairs down (tile 3). Do NOT remove or add extra copies.
- The outer border MUST remain walls (row 0, last row, col 0, last col).
- All rooms must be reachable — don't create isolated areas.
- Add character: secret alcoves, winding corridors, rooms with purpose.
- Place treasures (5) and fountains (6) meaningfully — reward exploration.
- Think like a dungeon master: surprise, challenge, reward.

Respond with ONLY a JSON object: {"ops": [...], "notes": "brief description of changes"}
Do NOT include any text outside the JSON object. No thinking tags, no explanations."""

CARTOGRAPHER_SYSTEM = """You are the Cartographer — a geographer who fixes overworld maps to match real-world terrain.

You receive an overworld segment as an ASCII grid, along with the real-world coordinates it represents. Your job is to make the terrain match reality.

TILE CODES:
  10 = grass (default land)
  11 = forest
  12 = mountain (impassable)
  13 = water (impassable — rivers, lakes, Lake Michigan)
  14 = road (connects towns)
  15 = town (safe zone)
  16 = dungeon entrance

OPERATIONS you can use:
  {"action": "set_tile", "x": N, "y": N, "tile": N}
  {"action": "set_range", "x1": N, "y1": N, "x2": N, "y2": N, "tile": N}
  {"action": "carve_corridor", "x1": N, "y1": N, "x2": N, "y2": N}  (use tile 14 for roads)
  {"action": "flood_fill", "x": N, "y": N, "tile": N}

RULES:
- The map grid is 128x128. Each tile is roughly 40m x 40m.
- Preserve existing towns (tile 15) and dungeon entrances (tile 16).
- Roads (14) should connect towns and follow real-world routes where possible.
- Water features (rivers, lakes) should roughly match real geography.
- Use flood_fill sparingly — it can overwrite large areas.
- The border should be appropriate terrain (water if coastal, grass/forest otherwise).

Respond with ONLY a JSON object: {"ops": [...], "notes": "brief description of changes"}
Do NOT include any text outside the JSON object. No thinking tags, no explanations."""


# ── Agent modes ───────────────────────────────────────────────────

def run_architect(floor_num, model, host, port, spectate=False, dry_run=False):
    """Improve a single dungeon floor."""
    print(f"\n[Architect] Floor {floor_num} — exporting map...")
    header, ascii_lines, legend = export_map_ascii(floor_num)
    grid_text = '\n'.join(ascii_lines)
    legend_text = ', '.join(f'{ch}={name}' for ch, name in legend.items())

    prompt = (
        f"Here is dungeon floor {floor_num} ({len(ascii_lines)}x{len(ascii_lines[0])} tiles):\n\n"
        f"```\n{grid_text}\n```\n\n"
        f"Legend: {legend_text}\n\n"
        f"Improve this floor. Add interesting features, better room shapes, "
        f"secret areas, meaningful treasure placement. Make it fun to explore."
    )

    if spectate:
        print(f"\n--- Current Map ---")
        print(f"  {header}")
        for line in ascii_lines:
            print(f"  {line}")
        print(f"  {legend_text}")
        print(f"\n[Architect] Sending to {model} at {host}:{port}...")

    messages = [
        {"role": "system", "content": ARCHITECT_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    response = ollama_chat(messages, model=model, host=host, port=port)
    if not response:
        print("[ERROR] No response from LLM.")
        return False

    if spectate:
        print(f"\n--- LLM Response ---")
        print(response[:500] + ("..." if len(response) > 500 else ""))

    data = extract_json(response)
    if not data or 'ops' not in data:
        print(f"[ERROR] Could not parse ops from response.")
        if spectate:
            print(f"Full response:\n{response}")
        return False

    ops = data['ops']
    notes = data.get('notes', '')
    print(f"[Architect] Got {len(ops)} operations. {notes}")

    if dry_run:
        print("[DRY RUN] Would apply:")
        for op in ops:
            print(f"  {op}")
        return True

    result = apply_ops(floor_num, ops)
    print(f"[Architect] Applied {result['applied']} ops.")
    if result['errors']:
        for err in result['errors']:
            print(f"  [WARN] {err}")

    save_floor(floor_num)
    print(f"[Architect] Floor {floor_num} saved.")

    if spectate:
        print(f"\n--- Updated Map ---")
        header2, lines2, _ = export_map_ascii(floor_num)
        print(f"  {header2}")
        for line in lines2:
            print(f"  {line}")

    return True


def run_cartographer(col, row, model, host, port, spectate=False, dry_run=False):
    """Fix a single overworld segment."""
    from dungeon.region import load_segment
    from dungeon.floor import set_overworld

    idx = load_region_index()
    segments = idx.get('segments', [])

    # Find this segment's metadata
    seg_meta = None
    for seg in segments:
        g = seg.get('grid', [0, 0])
        if g[0] == col and g[1] == row:
            seg_meta = seg
            break

    seg_grid = load_segment(col, row)
    if not seg_grid:
        print(f"[ERROR] Segment ({col},{row}) not found.")
        return False

    # Export as ASCII using the overworld floor
    set_overworld(seg_grid)
    header, ascii_lines, legend = export_map_ascii(-1)
    grid_text = '\n'.join(ascii_lines)
    legend_text = ', '.join(f'{ch}={name}' for ch, name in legend.items())

    # Build context about what this segment should contain
    context_parts = [f"Overworld segment ({col},{row})"]
    if seg_meta:
        if seg_meta.get('towns'):
            context_parts.append(f"Towns: {', '.join(seg_meta['towns'])}")
        if seg_meta.get('center'):
            lat, lon = seg_meta['center']
            context_parts.append(f"Center coordinates: {lat:.4f}N, {lon:.4f}W")
        if seg_meta.get('name'):
            context_parts.append(f"Segment name: {seg_meta['name']}")
    context = '. '.join(context_parts)

    # Regional context
    region_name = idx.get('name', 'Unknown Region')
    seg_km = idx.get('seg_km', 5.0)

    prompt = (
        f"Region: {region_name}. Each segment covers ~{seg_km}km x {seg_km}km.\n"
        f"{context}\n\n"
        f"Here is the current map ({len(ascii_lines)}x{len(ascii_lines[0])} tiles):\n\n"
        f"```\n{grid_text}\n```\n\n"
        f"Legend: {legend_text}\n\n"
        f"Fix this map to better match real-world geography. "
        f"Consider: water features (rivers, lakes, Lake Michigan if western edge), "
        f"forested areas, elevation, road placement between towns. "
        f"Keep existing towns and dungeon entrances in place."
    )

    if spectate:
        print(f"\n--- Current Segment ({col},{row}) ---")
        print(f"  {context}")
        print(f"  {header}")
        for i, line in enumerate(ascii_lines):
            if i < 20 or i > len(ascii_lines) - 5:
                print(f"  {line}")
            elif i == 20:
                print(f"  ... ({len(ascii_lines) - 25} rows omitted) ...")
        print(f"\n[Cartographer] Sending to {model} at {host}:{port}...")

    messages = [
        {"role": "system", "content": CARTOGRAPHER_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    response = ollama_chat(messages, model=model, host=host, port=port,
                           num_ctx=16384)  # bigger context for 128x128 maps
    if not response:
        print("[ERROR] No response from LLM.")
        return False

    if spectate:
        print(f"\n--- LLM Response ---")
        print(response[:500] + ("..." if len(response) > 500 else ""))

    data = extract_json(response)
    if not data or 'ops' not in data:
        print(f"[ERROR] Could not parse ops from response.")
        return False

    ops = data['ops']
    notes = data.get('notes', '')
    print(f"[Cartographer] Got {len(ops)} operations. {notes}")

    if dry_run:
        print("[DRY RUN] Would apply:")
        for op in ops[:20]:
            print(f"  {op}")
        if len(ops) > 20:
            print(f"  ... and {len(ops) - 20} more")
        return True

    result = apply_ops(-1, ops)
    print(f"[Cartographer] Applied {result['applied']} ops.")
    if result['errors']:
        for err in result['errors'][:10]:
            print(f"  [WARN] {err}")

    # Save the modified segment
    from dungeon.floor import get_floor
    updated = get_floor(-1)
    save_custom_floor(-1, updated)
    # Also save as the segment file
    seg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'region_maps', f'seg_{col}_{row}.json')
    with open(seg_path, 'w') as f:
        json.dump(updated, f)
    print(f"[Cartographer] Segment ({col},{row}) saved.")

    return True


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Dungeon Agent — LLM-powered GM")
    parser.add_argument('mode', choices=['architect', 'cartographer'],
                        help="Agent mode")
    parser.add_argument('--floor', type=int, default=None,
                        help="Dungeon floor number (architect mode)")
    parser.add_argument('--floor-range', type=str, default=None,
                        help="Floor range, e.g. 3-20 (architect batch mode)")
    parser.add_argument('--segment', type=str, default=None,
                        help="Overworld segment col,row (cartographer mode)")
    parser.add_argument('--all-segments', action='store_true',
                        help="Process all overworld segments")
    parser.add_argument('--model', type=str, default='qwen3:14b',
                        help="Ollama model name")
    parser.add_argument('--host', type=str, default='localhost',
                        help="Ollama host")
    parser.add_argument('--port', type=int, default=11434,
                        help="Ollama port")
    parser.add_argument('--spectate', action='store_true',
                        help="Show maps and LLM responses in real-time")
    parser.add_argument('--dry-run', action='store_true',
                        help="Show what would be done without applying changes")
    args = parser.parse_args()

    if args.mode == 'architect':
        if args.floor_range:
            start, end = args.floor_range.split('-')
            floors = range(int(start), int(end) + 1)
            print(f"[Architect] Batch mode: floors {start}-{end}")
            for f in floors:
                run_architect(f, args.model, args.host, args.port,
                              args.spectate, args.dry_run)
        elif args.floor is not None:
            run_architect(args.floor, args.model, args.host, args.port,
                          args.spectate, args.dry_run)
        else:
            parser.error("architect mode requires --floor or --floor-range")

    elif args.mode == 'cartographer':
        if args.all_segments:
            idx = load_region_index()
            for seg in idx.get('segments', []):
                g = seg.get('grid', [0, 0])
                run_cartographer(g[0], g[1], args.model, args.host, args.port,
                                 args.spectate, args.dry_run)
        elif args.segment:
            col, row = args.segment.split(',')
            run_cartographer(int(col), int(row), args.model, args.host, args.port,
                             args.spectate, args.dry_run)
        else:
            parser.error("cartographer mode requires --segment or --all-segments")


if __name__ == '__main__':
    main()
