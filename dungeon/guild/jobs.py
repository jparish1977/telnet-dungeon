"""Job queue — craftsmen post findings, the architect picks them up.

Jobs are persisted to guild_jobs.json so they survive restarts.
The architect consumes jobs asynchronously and produces work orders
for the apprentices.
"""

import json
import os
import time

_JOBS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'guild_jobs.json')

_WORK_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'guild_work.json')


# ── Job statuses ──────────────────────────────────────────────────

PENDING = 'pending'        # craftsman posted it, architect hasn't seen it
CLAIMED = 'claimed'        # architect is working on it
PLANNED = 'planned'        # architect returned ops, waiting for apprentice
IN_PROGRESS = 'in_progress'  # apprentice is executing
DONE = 'done'
FAILED = 'failed'


# ── Job types ─────────────────────────────────────────────────────

# Dungeon floor issues
BORING_ROOM = 'boring_room'           # large room with no features
DEAD_END = 'dead_end'                 # corridor with only one exit
EMPTY_FLOOR = 'empty_floor'           # floor with too few features overall
ISOLATED_AREA = 'isolated_area'       # unreachable tiles
LONG_CORRIDOR = 'long_corridor'       # straight corridor > N tiles
SPARSE_TREASURES = 'sparse_treasures' # too few chests for floor size

# Overworld issues
MISSING_WATER = 'missing_water'       # segment should have water but doesn't
DISCONNECTED_TOWN = 'disconnected_town'  # town with no road
DEAD_END_ROAD = 'dead_end_road'       # road that goes nowhere
TERRAIN_MISMATCH = 'terrain_mismatch' # terrain doesn't match real geography


# ── Queue operations ──────────────────────────────────────────────

def _load_jobs():
    if os.path.exists(_JOBS_FILE):
        with open(_JOBS_FILE, 'r') as f:
            return json.load(f)
    return []


def _save_jobs(jobs):
    with open(_JOBS_FILE, 'w') as f:
        json.dump(jobs, f, indent=2)


def post_job(job_type, floor, area=None, context=None, priority=0):
    """Craftsman posts a finding to the queue. Returns job ID."""
    jobs = _load_jobs()

    # Deduplicate — don't post the same issue twice
    for j in jobs:
        if (j['type'] == job_type and j['floor'] == floor
                and j.get('area') == area and j['status'] in (PENDING, CLAIMED)):
            return None  # already queued

    job = {
        'id': len(jobs) + 1,
        'type': job_type,
        'floor': floor,
        'area': area,       # [x1, y1, x2, y2] bounding box, or None
        'context': context,  # extra info for the architect
        'priority': priority,
        'status': PENDING,
        'created_at': time.time(),
        'ops': None,         # filled by architect
        'notes': None,       # architect's reasoning
    }
    jobs.append(job)
    _save_jobs(jobs)
    return job['id']


def get_pending_jobs(limit=10):
    """Get jobs waiting for the architect, highest priority first."""
    jobs = _load_jobs()
    pending = [j for j in jobs if j['status'] == PENDING]
    pending.sort(key=lambda j: -j['priority'])
    return pending[:limit]


def claim_job(job_id):
    """Architect claims a job. Returns the job or None."""
    jobs = _load_jobs()
    for j in jobs:
        if j['id'] == job_id and j['status'] == PENDING:
            j['status'] = CLAIMED
            j['claimed_at'] = time.time()
            _save_jobs(jobs)
            return j
    return None


def complete_job(job_id, ops, notes=""):
    """Architect returns a plan. Job moves to PLANNED status."""
    jobs = _load_jobs()
    for j in jobs:
        if j['id'] == job_id and j['status'] == CLAIMED:
            j['status'] = PLANNED
            j['ops'] = ops
            j['notes'] = notes
            j['planned_at'] = time.time()
            _save_jobs(jobs)
            return True
    return False


def fail_job(job_id, reason=""):
    """Mark a job as failed (LLM gave bad response, etc.)."""
    jobs = _load_jobs()
    for j in jobs:
        if j['id'] == job_id:
            j['status'] = FAILED
            j['notes'] = reason
            _save_jobs(jobs)
            return True
    return False


def get_planned_jobs(limit=10):
    """Get jobs ready for apprentices to execute."""
    jobs = _load_jobs()
    planned = [j for j in jobs if j['status'] == PLANNED]
    planned.sort(key=lambda j: -j.get('priority', 0))
    return planned[:limit]


def start_work(job_id):
    """Apprentice starts executing a planned job."""
    jobs = _load_jobs()
    for j in jobs:
        if j['id'] == job_id and j['status'] == PLANNED:
            j['status'] = IN_PROGRESS
            j['started_at'] = time.time()
            _save_jobs(jobs)
            return j
    return None


def finish_work(job_id):
    """Apprentice finished executing."""
    jobs = _load_jobs()
    for j in jobs:
        if j['id'] == job_id and j['status'] == IN_PROGRESS:
            j['status'] = DONE
            j['finished_at'] = time.time()
            _save_jobs(jobs)
            return True
    return False


def get_stats():
    """Summary of job queue state."""
    jobs = _load_jobs()
    counts = {}
    for j in jobs:
        counts[j['status']] = counts.get(j['status'], 0) + 1
    return {
        'total': len(jobs),
        'by_status': counts,
    }
