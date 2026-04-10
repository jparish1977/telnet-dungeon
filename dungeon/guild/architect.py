"""Architect — the LLM brain that reviews jobs and designs solutions.

Runs asynchronously, pulling jobs from the queue, consulting Ollama,
and posting work orders for the apprentices. Can run on any machine
with Ollama access (M18 GPU for fast, T7600 CPU for batch).
"""

import json
import urllib.request
import urllib.error

from dungeon.gm.map_ops import export_map_ascii
from dungeon.guild.jobs import (
    get_pending_jobs, claim_job, complete_job, fail_job,
    BORING_ROOM, DEAD_END, LONG_CORRIDOR, SPARSE_TREASURES,
    ISOLATED_AREA, EMPTY_FLOOR,
    MISSING_WATER, DISCONNECTED_TOWN, DEAD_END_ROAD, TERRAIN_MISMATCH,
)


def _ollama_chat(messages, model="qwen3:14b", host="localhost", port=11434,
                 temperature=0.4, num_ctx=8192):
    """Send a chat request to Ollama. Returns content string or None."""
    url = f"http://{host}:{port}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result.get('message', {}).get('content', '')
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[Architect] Ollama error: {e}")
        return None


def _extract_json(text):
    """Pull a JSON object out of LLM response text."""
    import re
    fence = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if fence:
        text = fence.group(1)
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


# ── Prompt builders per job type ──────────────────────────────────

SYSTEM_PROMPT = """You are the Dungeon Architect. You receive a map and a specific problem to fix. Return ONLY a JSON object with your solution.

DUNGEON TILE CODES: 0=floor, 1=wall, 2=door, 3=stairs_down, 4=stairs_up, 5=chest, 6=fountain
OVERWORLD TILE CODES: 10=grass, 11=forest, 12=mountain, 13=water, 14=road, 15=town, 16=dungeon_entrance

OPERATIONS:
  {"action": "set_tile", "x": N, "y": N, "tile": N}
  {"action": "set_range", "x1": N, "y1": N, "x2": N, "y2": N, "tile": N}
  {"action": "place_room", "x": N, "y": N, "w": N, "h": N, "door_side": "north|south|east|west"}
  {"action": "carve_corridor", "x1": N, "y1": N, "x2": N, "y2": N}
  {"action": "flood_fill", "x": N, "y": N, "tile": N}

RULES:
- Keep exactly ONE stairs up (4) and ONE stairs down (3). Never remove them.
- Outer border must stay walls (dungeon) or appropriate terrain (overworld).
- All rooms must be reachable from stairs up.
- Doors (2) go BETWEEN a room and a corridor — one door per doorway. Never place multiple doors in a row or in the middle of a corridor.
- Place features (chests, fountains) on FLOOR tiles (0), not inside walls (1). If you need to place something in a wall area, carve the space first.
- Keep changes minimal and focused on the specific problem.

Respond with: {"ops": [...], "notes": "what you did and why"}
No other text. No thinking tags."""


def _build_prompt(job):
    """Build a focused prompt for the specific job type."""
    header, lines, legend = export_map_ascii(job['floor'])
    grid_text = '\n'.join(lines)
    legend_str = ', '.join(f'{ch}={name}' for ch, name in legend.items())
    area = job.get('area')

    base = (
        f"Map: {header}\n"
        f"Legend: {legend_str}\n\n"
        f"```\n{grid_text}\n```\n\n"
    )

    area_str = ""
    if area:
        area_str = f"({area[0]},{area[1]}) to ({area[2]},{area[3]})"

    jtype = job['type']
    context = job.get('context', '')

    if jtype == BORING_ROOM:
        specific = (
            f"Problem: There's a boring empty room at area {area_str}. "
            f"It has no features — no chests, fountains, or interesting layout.\n"
            f"Task: Add character to this room. Consider: alcoves, pillars (wall tiles inside), "
            f"a chest reward, a fountain, or interesting shape. Don't change the rest of the map."
        )
    elif jtype == DEAD_END:
        specific = (
            f"Problem: Dead end at {area_str}.\n"
            f"Task: Either connect this dead end to another area (carve a corridor or add a door), "
            f"or reward the player for exploring it (add a chest or fountain). Keep changes minimal."
        )
    elif jtype == LONG_CORRIDOR:
        specific = (
            f"Problem: Long boring corridor from {area_str}. {context}\n"
            f"Task: Break up the monotony. Add a room branching off, a door, an alcove with treasure, "
            f"or a slight bend. Don't block the corridor entirely."
        )
    elif jtype == SPARSE_TREASURES:
        specific = (
            f"Problem: {context or 'Too few treasures on this floor.'}\n"
            f"Task: Add chests (tile 5) in interesting locations — hidden alcoves, "
            f"end of corridors, inside rooms. Place them where they reward exploration."
        )
    elif jtype == ISOLATED_AREA:
        specific = (
            f"Problem: {context or 'Unreachable area on this floor.'}\n"
            f"Area: {area_str}\n"
            f"Task: Connect the isolated area to the main dungeon by carving a corridor "
            f"or adding a door. Make sure stairs up and stairs down are both reachable."
        )
    elif jtype == MISSING_WATER:
        specific = (
            f"Problem: {context or 'Missing water features.'}\n"
            f"Task: Add water tiles (13) where they should be based on real geography. "
            f"Rivers are typically 2-4 tiles wide. Lakes are larger flood-filled areas."
        )
    elif jtype == DISCONNECTED_TOWN:
        specific = (
            f"Problem: {context or 'Town with no road.'}\n"
            f"Task: Build a road (tile 14) connecting this town to the nearest other "
            f"town or existing road network."
        )
    else:
        specific = (
            f"Problem: {context or 'General improvement needed.'}\n"
            f"Task: Improve this area based on the problem description."
        )

    return base + specific


# ── Main architect loop ───────────────────────────────────────────

class Architect:
    """Consults the LLM for each job and produces work orders."""

    def __init__(self, model="qwen3:14b", host="localhost", port=11434):
        self.model = model
        self.host = host
        self.port = port
        self.jobs_completed = 0
        self.jobs_failed = 0

    def process_one(self, verbose=False):
        """Pick up one pending job, consult the LLM, return the plan.

        Returns the job dict with ops filled in, or None.
        """
        pending = get_pending_jobs(limit=1)
        if not pending:
            if verbose:
                print("[Architect] No pending jobs.")
            return None

        job = pending[0]
        claimed = claim_job(job['id'])
        if not claimed:
            return None

        if verbose:
            print(f"[Architect] Job #{job['id']}: {job['type']} on floor {job['floor']}")
            if job.get('context'):
                print(f"  Context: {job['context']}")

        prompt = _build_prompt(job)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        if verbose:
            print(f"[Architect] Consulting {self.model} at {self.host}:{self.port}...")

        response = _ollama_chat(messages, model=self.model,
                                host=self.host, port=self.port)
        if not response:
            fail_job(job['id'], "No LLM response")
            self.jobs_failed += 1
            return None

        data = _extract_json(response)
        if not data or 'ops' not in data:
            fail_job(job['id'], f"Bad LLM response: could not parse JSON")
            self.jobs_failed += 1
            if verbose:
                print(f"[Architect] Failed to parse response:\n{response[:300]}")
            return None

        ops = data['ops']
        notes = data.get('notes', '')

        complete_job(job['id'], ops, notes)
        self.jobs_completed += 1

        if verbose:
            print(f"[Architect] Planned {len(ops)} operations: {notes}")

        return job

    def process_all(self, verbose=False):
        """Process all pending jobs."""
        count = 0
        while True:
            result = self.process_one(verbose=verbose)
            if result is None:
                break
            count += 1
        return count

    def status(self):
        return {
            'model': self.model,
            'host': f"{self.host}:{self.port}",
            'completed': self.jobs_completed,
            'failed': self.jobs_failed,
        }
