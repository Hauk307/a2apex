"""
A2Apex Agent Profiles

Public profile pages, trust scores, and agent directory.
"LinkedIn for AI Agents" — the public face of A2Apex.
"""

import re
import json
import uuid
import sqlite3
import httpx
from datetime import datetime
from typing import Optional
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field


# ============================================================================
# DATABASE SETUP
# ============================================================================

DB_PATH = Path(__file__).parent.parent / "data" / "agent_profiles.db"
CERT_DB_PATH = Path(__file__).parent.parent / "data" / "certifications.db"


def get_db():
    """Get database connection with row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the agent profiles database."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            url TEXT UNIQUE NOT NULL,
            owner_user_id INTEGER DEFAULT NULL,
            agent_card_json TEXT DEFAULT '{}',
            skills TEXT DEFAULT '[]',
            provider TEXT DEFAULT '',
            version TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            claimed INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            test_type TEXT NOT NULL,
            score INTEGER NOT NULL,
            results_json TEXT DEFAULT '{}',
            tested_at TEXT NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trust_scores (
            agent_id TEXT PRIMARY KEY,
            overall_score REAL DEFAULT 0,
            uptime_score REAL DEFAULT 0,
            compliance_score REAL DEFAULT 0,
            response_time_avg REAL DEFAULT 0,
            last_calculated TEXT,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agents_slug ON agents(slug)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agents_url ON agents(url)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_history_agent ON test_history(agent_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trust_scores_overall ON trust_scores(overall_score)")

    conn.commit()
    conn.close()


init_db()


# ============================================================================
# HELPERS
# ============================================================================

def slugify(name: str) -> str:
    """Convert a name into a URL-safe slug."""
    s = name.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s or 'unknown-agent'


def unique_slug(cursor, base_slug: str) -> str:
    """Ensure slug is unique, appending a number if needed."""
    slug = base_slug
    counter = 2
    while True:
        cursor.execute("SELECT id FROM agents WHERE slug = ?", (slug,))
        if not cursor.fetchone():
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


async def fetch_agent_card(agent_url: str) -> Optional[dict]:
    """Fetch the Agent Card from /.well-known/agent-card.json."""
    base = agent_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{base}/.well-known/agent-card.json")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None


def get_certification_for_agent(agent_url: str) -> Optional[dict]:
    """Get latest certification for an agent URL."""
    if not CERT_DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(str(CERT_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, score, certified, badge_style, plan, created_at, expires_at
            FROM certifications
            WHERE agent_url = ? AND certified = 1
            ORDER BY created_at DESC LIMIT 1
        """, (agent_url.rstrip("/"),))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def recalculate_trust_score(agent_id: str):
    """Recalculate trust score from test history."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT score, test_type, tested_at FROM test_history
        WHERE agent_id = ?
        ORDER BY tested_at DESC LIMIT 20
    """, (agent_id,))
    rows = cursor.fetchall()

    if not rows:
        conn.close()
        return

    # Weighted average: recent tests count more
    total_weight = 0
    weighted_sum = 0
    for i, row in enumerate(rows):
        weight = max(1, 20 - i)  # Most recent = weight 20
        weighted_sum += row["score"] * weight
        total_weight += weight

    overall = weighted_sum / total_weight if total_weight else 0

    # Compliance score from certify tests
    certify_scores = [r["score"] for r in rows if r["test_type"] == "certify"]
    compliance = sum(certify_scores) / len(certify_scores) if certify_scores else overall

    now = datetime.utcnow().isoformat() + "Z"
    cursor.execute("""
        INSERT INTO trust_scores (agent_id, overall_score, compliance_score, last_calculated)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(agent_id)
        DO UPDATE SET overall_score = ?, compliance_score = ?, last_calculated = ?
    """, (agent_id, round(overall, 1), round(compliance, 1), now,
          round(overall, 1), round(compliance, 1), now))

    conn.commit()
    conn.close()


# ============================================================================
# PUBLIC FUNCTION: auto-create/update agent profile from test runs
# ============================================================================

async def ensure_agent_profile(agent_url: str, test_type: str = "unknown", score: int = 0, results_json: str = "{}"):
    """
    Auto-create or update an agent profile when a test/certify runs.
    Called from main.py test endpoints.
    """
    url = agent_url.rstrip("/")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM agents WHERE url = ?", (url,))
    row = cursor.fetchone()

    if row:
        agent_id = row["id"]
        # Re-fetch agent card to keep profile current
        card = await fetch_agent_card(url)
        if card:
            now = datetime.utcnow().isoformat() + "Z"
            skills_list = [s.get("name", s.get("id", "")) for s in card.get("skills", [])]
            cursor.execute("""
                UPDATE agents SET agent_card_json = ?, skills = ?, updated_at = ?
                WHERE id = ?
            """, (json.dumps(card), json.dumps(skills_list), now, agent_id))
    else:
        # Create profile
        card = await fetch_agent_card(url)
        name = "Unknown Agent"
        description = ""
        skills_list = []
        provider = ""
        version = ""
        card_json = "{}"

        if card:
            name = card.get("name", "Unknown Agent")
            description = card.get("description", "")
            skills_list = [s.get("name", s.get("id", "")) for s in card.get("skills", [])]
            provider_info = card.get("provider", {})
            provider = provider_info.get("organization", "") if isinstance(provider_info, dict) else str(provider_info)
            version = card.get("version", "")
            card_json = json.dumps(card)

        agent_id = str(uuid.uuid4())
        slug = unique_slug(cursor, slugify(name))
        now = datetime.utcnow().isoformat() + "Z"

        cursor.execute("""
            INSERT INTO agents (id, slug, name, description, url, agent_card_json, skills, provider, version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (agent_id, slug, name, description, url, card_json, json.dumps(skills_list), provider, version, now, now))

    # Record test
    now = datetime.utcnow().isoformat() + "Z"
    cursor.execute("""
        INSERT INTO test_history (agent_id, test_type, score, results_json, tested_at)
        VALUES (?, ?, ?, ?, ?)
    """, (agent_id, test_type, score, results_json, now))

    conn.commit()
    conn.close()

    recalculate_trust_score(agent_id)


# ============================================================================
# MIGRATION: import existing certifications
# ============================================================================

def migrate_certifications():
    """Import existing certifications into agent profiles."""
    if not CERT_DB_PATH.exists():
        return 0

    cert_conn = sqlite3.connect(str(CERT_DB_PATH))
    cert_conn.row_factory = sqlite3.Row
    cert_cursor = cert_conn.cursor()

    cert_cursor.execute("""
        SELECT DISTINCT agent_url, agent_name, score, test_results, certified, created_at
        FROM certifications
        ORDER BY created_at ASC
    """)
    rows = cert_cursor.fetchall()
    cert_conn.close()

    if not rows:
        return 0

    conn = get_db()
    cursor = conn.cursor()
    count = 0
    agent_map = {}  # url -> agent_id

    for row in rows:
        url = row["agent_url"].rstrip("/")

        if url not in agent_map:
            # Check if already exists
            cursor.execute("SELECT id FROM agents WHERE url = ?", (url,))
            existing = cursor.fetchone()
            if existing:
                agent_map[url] = existing["id"]
            else:
                agent_id = str(uuid.uuid4())
                slug = unique_slug(cursor, slugify(row["agent_name"]))
                now = datetime.utcnow().isoformat() + "Z"

                # Try to parse test_results for the agent card
                card_json = "{}"
                skills = "[]"
                try:
                    results = json.loads(row["test_results"])
                    ac = results.get("agent_card", {})
                    if ac.get("agent_card"):
                        card_json = json.dumps(ac["agent_card"])
                        skills_list = [s.get("name", "") for s in ac["agent_card"].get("skills", [])]
                        skills = json.dumps(skills_list)
                except Exception:
                    pass

                cursor.execute("""
                    INSERT OR IGNORE INTO agents (id, slug, name, description, url, agent_card_json, skills, provider, version, created_at, updated_at)
                    VALUES (?, ?, ?, '', ?, ?, ?, '', '', ?, ?)
                """, (agent_id, slug, row["agent_name"], url, card_json, skills, now, now))
                agent_map[url] = agent_id
                count += 1

        # Record test history
        agent_id = agent_map[url]
        cursor.execute("""
            INSERT INTO test_history (agent_id, test_type, score, results_json, tested_at)
            VALUES (?, 'certify', ?, ?, ?)
        """, (agent_id, row["score"], row["test_results"], row["created_at"]))

    conn.commit()
    conn.close()

    # Recalculate trust scores
    for agent_id in set(agent_map.values()):
        recalculate_trust_score(agent_id)

    return count


# Run migration on module load
_migrated = migrate_certifications()
if _migrated:
    print(f"[profiles] Migrated {_migrated} agents from certifications.db")


# ============================================================================
# MODELS
# ============================================================================

class RegisterAgentRequest(BaseModel):
    agent_url: str = Field(..., description="Base URL of the A2A agent")


class ClaimAgentRequest(BaseModel):
    pass  # Auth comes from JWT header


# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(tags=["Agent Profiles"])


# ---------------------------------------------------------------------------
# API ENDPOINTS (mounted under /api/agents via main.py prefix or direct)
# ---------------------------------------------------------------------------

@router.get("/api/agents/")
async def list_agents(
    q: Optional[str] = Query(None, description="Search query"),
    sort: str = Query("score", description="Sort by: score, newest, name"),
    certified_only: bool = Query(False),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List and search agents in the directory."""
    conn = get_db()
    cursor = conn.cursor()

    base_query = """
        SELECT a.*, COALESCE(t.overall_score, 0) as trust_score
        FROM agents a
        LEFT JOIN trust_scores t ON a.id = t.agent_id
    """
    conditions = []
    params = []

    if q:
        conditions.append("(a.name LIKE ? OR a.description LIKE ? OR a.skills LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])

    if certified_only:
        conditions.append("t.overall_score >= 70")

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    order_map = {
        "score": "trust_score DESC",
        "newest": "a.created_at DESC",
        "name": "a.name ASC",
    }
    order = order_map.get(sort, "trust_score DESC")

    query = f"{base_query}{where} ORDER BY {order} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()

    # Total count
    count_query = f"SELECT COUNT(*) FROM agents a LEFT JOIN trust_scores t ON a.id = t.agent_id{where}"
    cursor.execute(count_query, params[:-2])  # exclude limit/offset
    total = cursor.fetchone()[0]

    conn.close()

    agents = []
    for row in rows:
        skills = []
        try:
            skills = json.loads(row["skills"])
        except Exception:
            pass

        cert = get_certification_for_agent(row["url"])

        agents.append({
            "slug": row["slug"],
            "name": row["name"],
            "description": row["description"],
            "url": row["url"],
            "skills": skills,
            "provider": row["provider"],
            "trust_score": row["trust_score"],
            "certified": cert is not None,
            "certification_id": cert["id"] if cert else None,
            "badge_style": cert["badge_style"] if cert else None,
            "created_at": row["created_at"],
        })

    return {"agents": agents, "total": total, "limit": limit, "offset": offset}


@router.post("/api/agents/register")
async def register_agent(request: RegisterAgentRequest):
    """Register an agent by URL. Auto-fetches Agent Card."""
    url = request.agent_url.rstrip("/")

    # Check if already registered
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT slug, name FROM agents WHERE url = ?", (url,))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return {
            "message": "Agent already registered",
            "slug": existing["slug"],
            "name": existing["name"],
            "profile_url": f"/agents/{existing['slug']}",
        }

    # Fetch agent card
    card = await fetch_agent_card(url)
    name = "Unknown Agent"
    description = ""
    skills_list = []
    provider = ""
    version = ""
    card_json = "{}"

    if card:
        name = card.get("name", "Unknown Agent")
        description = card.get("description", "")
        skills_list = [s.get("name", s.get("id", "")) for s in card.get("skills", [])]
        provider_info = card.get("provider", {})
        provider = provider_info.get("organization", "") if isinstance(provider_info, dict) else str(provider_info)
        version = card.get("version", "")
        card_json = json.dumps(card)

    agent_id = str(uuid.uuid4())
    slug = unique_slug(cursor, slugify(name))
    now = datetime.utcnow().isoformat() + "Z"

    cursor.execute("""
        INSERT INTO agents (id, slug, name, description, url, agent_card_json, skills, provider, version, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (agent_id, slug, name, description, url, card_json, json.dumps(skills_list), provider, version, now, now))

    # Initialize trust score at 0
    cursor.execute("""
        INSERT INTO trust_scores (agent_id, overall_score, last_calculated)
        VALUES (?, 0, ?)
    """, (agent_id, now))

    conn.commit()
    conn.close()

    return {
        "message": "Agent registered successfully",
        "slug": slug,
        "name": name,
        "profile_url": f"/agents/{slug}",
        "agent_id": agent_id,
    }


@router.get("/api/agents/{slug}")
async def get_agent_profile_json(slug: str):
    """Get agent profile data as JSON."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.*, COALESCE(t.overall_score, 0) as trust_score,
               t.compliance_score, t.uptime_score, t.response_time_avg
        FROM agents a
        LEFT JOIN trust_scores t ON a.id = t.agent_id
        WHERE a.slug = ?
    """, (slug,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get test history
    cursor.execute("""
        SELECT test_type, score, tested_at FROM test_history
        WHERE agent_id = ? ORDER BY tested_at DESC LIMIT 10
    """, (row["id"],))
    history = [dict(r) for r in cursor.fetchall()]
    conn.close()

    skills = []
    try:
        skills = json.loads(row["skills"])
    except Exception:
        pass

    cert = get_certification_for_agent(row["url"])

    return {
        "slug": row["slug"],
        "name": row["name"],
        "description": row["description"],
        "url": row["url"],
        "skills": skills,
        "provider": row["provider"],
        "version": row["version"],
        "trust_score": row["trust_score"],
        "compliance_score": row["compliance_score"] or 0,
        "uptime_score": row["uptime_score"] or 0,
        "response_time_avg": row["response_time_avg"] or 0,
        "certified": cert is not None,
        "certification": cert,
        "test_history": history,
        "claimed": bool(row["claimed"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("/api/agents/{slug}/history")
async def get_agent_history(slug: str, limit: int = Query(20, ge=1, le=100)):
    """Get test history for an agent."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM agents WHERE slug = ?", (slug,))
    agent = cursor.fetchone()
    if not agent:
        conn.close()
        raise HTTPException(status_code=404, detail="Agent not found")

    cursor.execute("""
        SELECT test_type, score, results_json, tested_at FROM test_history
        WHERE agent_id = ? ORDER BY tested_at DESC LIMIT ?
    """, (agent["id"], limit))
    rows = cursor.fetchall()
    conn.close()
    return {"slug": slug, "history": [dict(r) for r in rows]}


@router.get("/api/agents/{slug}/badge")
async def get_agent_badge(slug: str):
    """Dynamic trust score badge SVG for an agent."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.name, a.url, COALESCE(t.overall_score, 0) as trust_score
        FROM agents a LEFT JOIN trust_scores t ON a.id = t.agent_id
        WHERE a.slug = ?
    """, (slug,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="28"><rect width="160" height="28" rx="4" fill="#555"/><text x="80" y="18" font-family="sans-serif" font-size="11" font-weight="600" fill="#fff" text-anchor="middle">Agent Not Found</text></svg>'
        return Response(content=svg, media_type="image/svg+xml")

    # Use certification score if available (more accurate than averaged trust score)
    cert = get_certification_for_agent(row["url"])
    if cert and cert.get("score"):
        score = int(cert["score"])
        plan = cert.get("plan", "free")
    else:
        score = int(row["trust_score"])
        plan = "free"

    # Use the proper badge from badges.py (★ A2Apex Certified | Score: 100/100)
    from api.badges import generate_badge_svg
    svg = generate_badge_svg(score=score, certified=score >= 70, plan=plan)
    return Response(content=svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=300"})


@router.put("/api/agents/{slug}/claim")
async def claim_agent(slug: str, request: Request):
    """Claim ownership of an agent (requires auth)."""
    # Extract user from JWT
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required to claim an agent")

    try:
        from api.auth import SECRET_KEY, ALGORITHM, get_user_by_id
        from jose import jwt
        token = auth_header.split(" ", 1)[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", 0))
        user = get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid user")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, claimed, owner_user_id FROM agents WHERE slug = ?", (slug,))
    agent = cursor.fetchone()
    if not agent:
        conn.close()
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent["claimed"] and agent["owner_user_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=409, detail="Agent already claimed by another user")

    now = datetime.utcnow().isoformat() + "Z"
    cursor.execute("UPDATE agents SET claimed = 1, owner_user_id = ?, updated_at = ? WHERE slug = ?",
                    (user_id, now, slug))
    conn.commit()
    conn.close()

    return {"message": "Agent claimed successfully", "slug": slug, "owner": user["email"]}


# ---------------------------------------------------------------------------
# HTML PAGES
# ---------------------------------------------------------------------------

def _base_head(title: str, description: str, og_image: str = "", extra_head: str = "") -> str:
    return f'''<meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <meta name="description" content="{description}">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">
    <meta property="og:type" content="website">
    {"<meta property='og:image' content='" + og_image + "'>" if og_image else ""}
    <meta name="twitter:card" content="summary_large_image">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Orbitron:wght@700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    {extra_head}'''


COMMON_CSS = '''
:root {
    --bg: #0A1628;
    --bg2: #0D1D31;
    --card: #111F36;
    --elevated: #162740;
    --cyan: #00E5FF;
    --cyan-dim: rgba(0,229,255,.15);
    --cyan-glow: rgba(0,229,255,.25);
    --gold: #FFD700;
    --silver: #C0C0C0;
    --bronze: #CD7F32;
    --success: #00E676;
    --danger: #FF5252;
    --text: #FFFFFF;
    --text2: rgba(255,255,255,.7);
    --text3: rgba(255,255,255,.45);
    --border: rgba(255,255,255,.1);
    --shadow: 0 4px 24px rgba(0,0,0,.35);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;min-height:100vh}
a{color:var(--cyan);text-decoration:none}
a:hover{text-decoration:underline}

.topbar{
    background:var(--bg2);border-bottom:1px solid var(--border);
    padding:.75rem 2rem;display:flex;align-items:center;justify-content:space-between;
    position:sticky;top:0;z-index:100;backdrop-filter:blur(12px);
}
.topbar-logo{display:flex;align-items:center;gap:.75rem;text-decoration:none}
.topbar-logo img{height:32px;filter:brightness(1.5) drop-shadow(0 0 12px rgba(25,193,244,.4))}
.topbar-nav{display:flex;gap:1.5rem;align-items:center;font-size:.875rem}
.topbar-nav a{color:var(--text2);transition:color .2s}
.topbar-nav a:hover{color:var(--cyan);text-decoration:none}
.btn{
    display:inline-flex;align-items:center;gap:.5rem;
    padding:.6rem 1.25rem;border-radius:8px;font-weight:600;font-size:.875rem;
    cursor:pointer;border:none;transition:all .2s;text-decoration:none;
}
.btn-cyan{background:var(--cyan);color:#0A1628}
.btn-cyan:hover{background:#33ECFF;text-decoration:none;transform:translateY(-1px)}
.btn-outline{border:1px solid var(--border);color:var(--text2);background:transparent}
.btn-outline:hover{border-color:var(--cyan);color:var(--cyan);text-decoration:none}
'''

LOGO_SVG_B64 = "PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPHN2ZyBpZD0iTGF5ZXJfMSIgZGF0YS1uYW1lPSJMYXllciAxIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnhsaW5rPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5L3hsaW5rIiB2aWV3Qm94PSIwIDAgMTE0Ni42MyAzMTcuMSI+CiAgPGRlZnM+CiAgICA8c3R5bGU+CiAgICAgIC5jbHMtMSB7CiAgICAgICAgZmlsbDogdXJsKCNsaW5lYXItZ3JhZGllbnQtMik7CiAgICAgIH0KCiAgICAgIC5jbHMtMiB7CiAgICAgICAgZmlsbDogI2ZmZmZmZjsKICAgICAgfQoKICAgICAgLmNscy0zIHsKICAgICAgICBmaWxsOiB1cmwoI3JhZGlhbC1ncmFkaWVudCk7CiAgICAgIH0KCiAgICAgIC5jbHMtNCB7CiAgICAgICAgZmlsbDogdXJsKCNsaW5lYXItZ3JhZGllbnQtMyk7CiAgICAgICAgb3BhY2l0eTogLjg1OwogICAgICB9CgogICAgICAuY2xzLTUgewogICAgICAgIGZpbGw6IHVybCgjbGluZWFyLWdyYWRpZW50KTsKICAgICAgfQogICAgPC9zdHlsZT4KICAgIDxyYWRpYWxHcmFkaWVudCBpZD0icmFkaWFsLWdyYWRpZW50IiBjeD0iMjIxLjciIGN5PSIxNTguNTUiIGZ4PSIyMjEuNyIgZnk9IjE1OC41NSIgcj0iNjMuNTEiIGdyYWRpZW50VHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTEwMi40NyAtNDIuOTQpIHJvdGF0ZSgtMjIuNjMpIHNjYWxlKDEgMS45NikiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjMTljMWY0Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjI2IiBzdG9wLWNvbG9yPSIjMThiZWYyIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjQyIiBzdG9wLWNvbG9yPSIjMTdiNmVkIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjU1IiBzdG9wLWNvbG9yPSIjMTVhN2U1Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjY3IiBzdG9wLWNvbG9yPSIjMTI5M2RhIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjc3IiBzdG9wLWNvbG9yPSIjMGY3OGNiIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjg3IiBzdG9wLWNvbG9yPSIjMGE1OGI5Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjk2IiBzdG9wLWNvbG9yPSIjMDUzMmE0Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzAzMjE5YiIvPgogICAgPC9yYWRpYWxHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudCBpZD0ibGluZWFyLWdyYWRpZW50IiB4MT0iMjMxLjQ5IiB5MT0iMTg4LjI0IiB4Mj0iMTgyLjUxIiB5Mj0iMjM4LjgzIiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+CiAgICAgIDxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzE5YzFmNCIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii4wOSIgc3RvcC1jb2xvcj0iIzE2YWJlOCIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii4zMSIgc3RvcC1jb2xvcj0iIzBmN2FjYyIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii41MiIgc3RvcC1jb2xvcj0iIzA5NTNiNyIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii43MSIgc3RvcC1jb2xvcj0iIzA2MzdhNyIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii44NyIgc3RvcC1jb2xvcj0iIzAzMjY5ZSIvPgogICAgICA8c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiMwMzIxOWIiLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQgaWQ9ImxpbmVhci1ncmFkaWVudC0yIiB4MT0iMTIxLjg4IiB5MT0iMTM3LjI5IiB4Mj0iMTA1LjIyIiB5Mj0iMjQ4LjMiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjMTljMWY0Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzAzMjE5YiIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudCBpZD0ibGluZWFyLWdyYWRpZW50LTMiIHgxPSIxODUuMjciIHkxPSIxODYuNjMiIHgyPSIxNTIuODEiIHkyPSIyNDkuMTEiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjMTljMWY0Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjEzIiBzdG9wLWNvbG9yPSIjMThiYmYxIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjI5IiBzdG9wLWNvbG9yPSIjMTZhY2U4Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjQ4IiBzdG9wLWNvbG9yPSIjMTI5MmRhIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjY3IiBzdG9wLWNvbG9yPSIjMGQ2ZmM2Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjg3IiBzdG9wLWNvbG9yPSIjMDc0MmFkIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzAzMjE5YiIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICA8L2RlZnM+CiAgPGc+CiAgICA8cG9seWdvbiBjbGFzcz0iY2xzLTMiIHBvaW50cz0iMjkwLjc5IDI2My41MiAyNjAuMzYgMjYzLjUyIDE4NC41MSAxMTMuNyAxNjcuODMgMTQ2LjY1IDE1Mi42MiAxMTYuNTkgMTg0LjUxIDUzLjU3IDI5MC43OSAyNjMuNTIiLz4KICAgIDxwb2x5Z29uIGNsYXNzPSJjbHMtNSIgcG9pbnRzPSIxNjYuNTMgMTkwLjA4IDE4Ni4zMyAyMjkuMiAyMDMuNzIgMjYzLjUyIDIzNi45NCAyNjMuNTIgMTgzLjE1IDE1Ny4yNSAxNjYuNTMgMTkwLjA4Ii8+CiAgICA8cG9seWdvbiBjbGFzcz0iY2xzLTEiIHBvaW50cz0iMTY3LjgzIDE0Ni42NSAxNTMuNjkgMTc0LjYgMTQxLjI5IDE1MC4xIDkzLjMgMjQ0LjkgMTI3IDI0NC45IDExNi44NCAyNjMuNTIgNTUuNTggMjYzLjUyIDE0MS4yOSA5NC4yIDE1Mi42MiAxMTYuNTkgMTY3LjgzIDE0Ni42NSIvPgogICAgPHBvbHlnb24gY2xhc3M9ImNscy00IiBwb2ludHM9IjE5OS44MyAxOTAuMDggMTgwLjAzIDIyOS4yIDE2Mi42NSAyNjMuNTIgMTI5LjQyIDI2My41MiAxODMuMjEgMTU3LjI1IDE5OS44MyAxOTAuMDgiLz4KICA8L2c+CiAgPGc+CiAgICA8cGF0aCBjbGFzcz0iY2xzLTIiIGQ9Ik00NzAuOTcsMjE0LjA2di0yNy4xYzAtMTYuNDIsMTEuMzYtMjQuMzYsMzIuMTYtMjQuMzZoMzkuOTZjMTQuNjQsMCwyMS4wOC00Ljc5LDIxLjA4LTEzLjU1LDAtMTAuNjctOS43Mi0xMy45Ni0yOC42LTEzLjk2aC01OS4yNmw5LjU4LTEyLjU5aDU1Ljg0YzI2LjQyLDAsMzYuNjgsMTAuNTQsMzYuNjgsMjUuNzNzLTkuODUsMjUuMzItMzMuOTQsMjUuMzJoLTM5Ljk2Yy0xMi41OSwwLTE5LjE2LDMuOTctMTkuMTYsMTMuMjh2MTQuNzhoOTQuNDRsLTkuNTgsMTIuNDVoLTk5LjIzWiIvPgogICAgPHBhdGggY2xhc3M9ImNscy0yIiBkPSJNNzQ4LjEsMTg0LjIydjI5Ljg0aC0xNC43OHYtNDIuMTVoNjUuNDJjMTcuMzgsMCwzMS40OC00LjkzLDMxLjQ4LTE4LjIsMC0xNC4yMy0xMi44Ny0xOC42MS0zMS42MS0xOC42MWgtNjUuNTZsOS44NS0xMi41OWg2MC45YzI1LjE4LDAsNDEuMiwxMS43Nyw0MS4yLDMxLjM0cy0xNS44OCwzMC4zOC00MS4yLDMwLjM4aC01NS43WiIvPgogICAgPHBhdGggY2xhc3M9ImNscy0yIiBkPSJNODU4LjY3LDIxNC4wNnYtOTEuNTZoOTcuMTdsLTkuNzIsMTIuNTloLTcyLjY3djI3LjUxaDc4LjE1bC04LjQ5LDEwLjk1aC02OS42NnYyOC4wNmg4My4wOGwtOS43MiwxMi40NWgtODguMTRaIi8+CiAgICA8cGF0aCBjbGFzcz0iY2xzLTIiIGQ9Ik0xMDY3LjI0LDIxNC4wNmwtNDQuMzQtMzguNi00NC42MiwzOC42aC0xOC42MWw1NC42MS00Ny4wOC01MS4wNS00NC40OGgyMC41M2w0MC41MSwzNS43Miw0MC43OS0zNS43MmgxOS4zbC01MS4wNSw0My45Myw1NC44OCw0Ny42M2gtMjAuOTRaIi8+CiAgICA8cGF0aCBjbGFzcz0iY2xzLTIiIGQ9Ik00NDUuNDUsMjE0LjA2aDE4LjE1bC01OC41OC0xMDUuNGMtMi4wNS0zLjE1LTUuMzQtNS42MS05LjcyLTUuNjFzLTcuOCwyLjc0LTkuNzIsNS42MWwtNTkuNCwxMDUuNGgxNy41MmwxNi4xOC0yOS43aDY5LjY2bDE1LjksMjkuN1pNMzY2LjY3LDE3MS45bDI4LjM1LTUyLjAzLDI3Ljg1LDUyLjAzaC01Ni4yMVoiLz4KICAgIDxwYXRoIGNsYXNzPSJjbHMtMiIgZD0iTTcwNS43NCwyMTQuMDZoMTguMTVsLTU4LjU4LTEwNS40Yy0yLjA1LTMuMTUtNS4zNC01LjYxLTkuNzItNS42MXMtNy44LDIuNzQtOS43Miw1LjYxbC01OS40LDEwNS40aDE3LjUybDE2LjE4LTI5LjdoNjkuNjZsMTUuOSwyOS43Wk02MjYuOTYsMTcxLjlsMjguMzUtNTIuMDMsMjcuODUsNTIuMDNoLTU2LjIxWiIvPgogIDwvZz4KPC9zdmc+"


def _topbar_html() -> str:
    return f'''<nav class="topbar">
    <a href="https://a2apex.io" class="topbar-logo">
        <img src="data:image/svg+xml;base64,{LOGO_SVG_B64}" alt="A2Apex">
    </a>
    <div class="topbar-nav">
        <a href="/agents">Agent Directory</a>
        <a href="/">Test an Agent</a>
        <a href="https://a2apex.io">Home</a>
    </div>
</nav>'''


# ---------------------------------------------------------------------------
# AGENT DIRECTORY PAGE  /agents
# ---------------------------------------------------------------------------

@router.get("/agents", response_class=HTMLResponse)
async def agent_directory_page(request: Request):
    """The public agent directory — LinkedIn for AI Agents."""
    base_url = str(request.base_url).rstrip("/")
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    {_base_head("Agent Directory — A2Apex", "Discover trusted AI agents. Search, compare, and verify A2A protocol compliance.")}
    <style>
    {COMMON_CSS}

    .hero{{text-align:center;padding:3rem 2rem 2rem}}
    .hero h1{{font-size:2.5rem;font-weight:700;margin-bottom:.5rem}}
    .hero h1 span{{color:var(--cyan)}}
    .hero p{{color:var(--text2);font-size:1.125rem;max-width:600px;margin:0 auto}}

    .controls{{
        max-width:1200px;margin:0 auto 2rem;padding:0 2rem;
        display:flex;gap:1rem;flex-wrap:wrap;align-items:center;
    }}
    .search-box{{
        flex:1;min-width:240px;position:relative;
    }}
    .search-box input{{
        width:100%;padding:.75rem 1rem .75rem 2.75rem;
        background:var(--card);border:1px solid var(--border);border-radius:10px;
        color:var(--text);font-size:.95rem;outline:none;transition:border-color .2s;
    }}
    .search-box input:focus{{border-color:var(--cyan)}}
    .search-box svg{{position:absolute;left:.85rem;top:50%;transform:translateY(-50%);opacity:.4;pointer-events:none}}
    .filter-btn{{
        padding:.6rem 1rem;border-radius:8px;font-size:.8rem;font-weight:600;
        cursor:pointer;border:1px solid var(--border);background:transparent;
        color:var(--text2);transition:all .2s;
    }}
    .filter-btn:hover,.filter-btn.active{{border-color:var(--cyan);color:var(--cyan);background:var(--cyan-dim)}}
    select.sort-select{{
        padding:.6rem 1rem;border-radius:8px;font-size:.85rem;
        background:var(--card);border:1px solid var(--border);color:var(--text2);
        outline:none;cursor:pointer;
    }}

    .grid{{
        max-width:1200px;margin:0 auto;padding:0 2rem 4rem;
        display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:1.25rem;
    }}
    .agent-card{{
        background:var(--card);border:1px solid var(--border);border-radius:16px;
        padding:1.5rem;transition:all .25s;cursor:pointer;position:relative;overflow:hidden;
    }}
    .agent-card:hover{{border-color:var(--cyan-glow);transform:translateY(-3px);box-shadow:var(--shadow)}}
    .agent-card::before{{
        content:'';position:absolute;top:0;left:0;right:0;height:3px;
        background:linear-gradient(90deg,transparent,var(--cyan),transparent);
        opacity:0;transition:opacity .3s;
    }}
    .agent-card:hover::before{{opacity:1}}
    .card-top{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.75rem}}
    .card-name{{font-size:1.125rem;font-weight:600}}
    .card-score{{
        font-family:'Orbitron',monospace;font-size:1.5rem;font-weight:700;
        min-width:50px;text-align:right;
    }}
    .card-score.gold{{color:var(--gold)}}
    .card-score.silver{{color:var(--silver)}}
    .card-score.bronze{{color:var(--bronze)}}
    .card-score.low{{color:var(--danger)}}
    .card-score.none{{color:var(--text3)}}
    .card-desc{{color:var(--text2);font-size:.85rem;margin-bottom:.75rem;
        display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
    .card-skills{{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.75rem}}
    .skill-tag{{
        font-size:.7rem;padding:.2rem .55rem;border-radius:20px;
        background:var(--cyan-dim);color:var(--cyan);font-weight:500;
    }}
    .card-meta{{
        display:flex;justify-content:space-between;align-items:center;
        padding-top:.75rem;border-top:1px solid var(--border);
        font-size:.75rem;color:var(--text3);
    }}
    .cert-badge{{
        display:inline-flex;align-items:center;gap:.3rem;
        padding:.15rem .5rem;border-radius:20px;font-size:.7rem;font-weight:600;
    }}
    .cert-badge.gold{{background:rgba(255,215,0,.15);color:var(--gold)}}
    .cert-badge.silver{{background:rgba(192,192,192,.15);color:var(--silver)}}
    .cert-badge.bronze{{background:rgba(205,127,50,.15);color:var(--bronze)}}

    .empty{{text-align:center;padding:5rem 2rem;color:var(--text3)}}
    .empty h3{{font-size:1.25rem;color:var(--text2);margin-bottom:.5rem}}

    .stats-bar{{
        max-width:1200px;margin:0 auto 2rem;padding:0 2rem;
        display:flex;gap:2rem;flex-wrap:wrap;
    }}
    .stat{{
        background:var(--card);border:1px solid var(--border);border-radius:12px;
        padding:1rem 1.5rem;flex:1;min-width:150px;text-align:center;
    }}
    .stat-val{{font-family:'Orbitron',monospace;font-size:1.75rem;font-weight:700;color:var(--cyan)}}
    .stat-label{{font-size:.75rem;color:var(--text3);text-transform:uppercase;letter-spacing:.5px}}

    .register-cta{{
        max-width:1200px;margin:0 auto;padding:0 2rem 2rem;text-align:center;
    }}

    @media(max-width:600px){{
        .hero h1{{font-size:1.75rem}}
        .grid{{grid-template-columns:1fr}}
        .controls{{flex-direction:column}}
    }}
    </style>
</head>
<body>
    {_topbar_html()}

    <div class="hero">
        <h1>Agent <span>Directory</span></h1>
        <p>Discover, verify, and connect with trusted AI agents. The trust layer for the A2A ecosystem.</p>
    </div>

    <div class="stats-bar" id="stats-bar"></div>

    <div class="controls">
        <div class="search-box">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
            <input type="text" id="search" placeholder="Search agents by name, skill, or description…" oninput="filterAgents()">
        </div>
        <button class="filter-btn" onclick="toggleCertified(this)" id="cert-filter">✓ Certified Only</button>
        <select class="sort-select" id="sort-select" onchange="filterAgents()">
            <option value="score">Sort by Score</option>
            <option value="newest">Newest First</option>
            <option value="name">Alphabetical</option>
        </select>
    </div>

    <div class="grid" id="agents-grid"></div>

    <div class="register-cta">
        <p style="color:var(--text3);margin-bottom:1rem">Don't see your agent? Register it in seconds.</p>
        <button class="btn btn-cyan" onclick="showRegisterModal()">+ Register an Agent</button>
    </div>

    <!-- Register Modal -->
    <div id="register-modal" style="display:none;position:fixed;inset:0;z-index:200;background:rgba(0,0,0,.6);backdrop-filter:blur(4px);align-items:center;justify-content:center">
        <div style="background:var(--card);border:1px solid var(--border);border-radius:20px;padding:2rem;max-width:480px;width:90%;margin:auto;position:relative;top:50%;transform:translateY(-50%)">
            <h3 style="font-size:1.25rem;margin-bottom:.5rem">Register an Agent</h3>
            <p style="color:var(--text2);font-size:.875rem;margin-bottom:1.25rem">Enter your agent's base URL. We'll fetch the Agent Card and create its profile.</p>
            <input type="text" id="register-url" placeholder="https://your-agent.example.com" style="width:100%;padding:.75rem 1rem;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:.95rem;outline:none;margin-bottom:1rem">
            <div style="display:flex;gap:.75rem;justify-content:flex-end">
                <button class="btn btn-outline" onclick="hideRegisterModal()">Cancel</button>
                <button class="btn btn-cyan" onclick="registerAgent()" id="register-btn">Register</button>
            </div>
            <div id="register-result" style="margin-top:1rem;font-size:.875rem;display:none"></div>
        </div>
    </div>

    <script>
    let allAgents = [];
    let certOnly = false;

    async function loadAgents() {{
        try {{
            const sort = document.getElementById('sort-select').value;
            const q = document.getElementById('search').value;
            const params = new URLSearchParams({{sort, limit: 100, offset: 0}});
            if (q) params.set('q', q);
            if (certOnly) params.set('certified_only', 'true');
            const res = await fetch('/api/agents/?' + params);
            const data = await res.json();
            allAgents = data.agents;
            renderAgents(allAgents);
            renderStats(data);
        }} catch(e) {{
            document.getElementById('agents-grid').innerHTML = '<div class="empty"><h3>Could not load agents</h3><p>' + e.message + '</p></div>';
        }}
    }}

    function renderStats(data) {{
        const total = data.total;
        const certified = allAgents.filter(a => a.certified).length;
        const avgScore = allAgents.length ? Math.round(allAgents.reduce((s,a) => s + a.trust_score, 0) / allAgents.length) : 0;
        document.getElementById('stats-bar').innerHTML = `
            <div class="stat"><div class="stat-val">${{total}}</div><div class="stat-label">Agents</div></div>
            <div class="stat"><div class="stat-val">${{certified}}</div><div class="stat-label">Certified</div></div>
            <div class="stat"><div class="stat-val">${{avgScore}}</div><div class="stat-label">Avg Score</div></div>
        `;
    }}

    function renderAgents(agents) {{
        const grid = document.getElementById('agents-grid');
        if (!agents.length) {{
            grid.innerHTML = '<div class="empty"><h3>No agents found</h3><p>Be the first to register one!</p></div>';
            return;
        }}
        grid.innerHTML = agents.map(a => {{
            const scoreClass = a.trust_score >= 90 ? 'gold' : a.trust_score >= 80 ? 'silver' : a.trust_score >= 70 ? 'bronze' : a.trust_score > 0 ? 'low' : 'none';
            const skills = (a.skills || []).slice(0, 4).map(s => `<span class="skill-tag">${{s}}</span>`).join('');
            const certHtml = a.certified
                ? `<span class="cert-badge ${{a.badge_style || 'bronze'}}">✓ ${{a.badge_style === 'gold' ? 'Certified' : a.badge_style === 'silver' ? 'Verified' : 'Tested'}}</span>`
                : '';
            const date = a.created_at ? new Date(a.created_at).toLocaleDateString('en-US', {{month:'short',year:'numeric'}}) : '';
            return `
                <div class="agent-card" onclick="location.href='/agents/${{a.slug}}'">
                    <div class="card-top">
                        <div class="card-name">${{a.name}}</div>
                        <div class="card-score ${{scoreClass}}">${{a.trust_score > 0 ? Math.round(a.trust_score) : '—'}}</div>
                    </div>
                    <div class="card-desc">${{a.description || 'No description available'}}</div>
                    <div class="card-skills">${{skills}}</div>
                    <div class="card-meta">
                        <span>${{date}}${{a.provider ? ' · ' + a.provider : ''}}</span>
                        ${{certHtml}}
                    </div>
                </div>`;
        }}).join('');
    }}

    function filterAgents() {{ loadAgents(); }}
    function toggleCertified(btn) {{
        certOnly = !certOnly;
        btn.classList.toggle('active', certOnly);
        loadAgents();
    }}

    function showRegisterModal() {{ document.getElementById('register-modal').style.display = 'flex'; }}
    function hideRegisterModal() {{ document.getElementById('register-modal').style.display = 'none'; document.getElementById('register-result').style.display='none'; }}

    async function registerAgent() {{
        const url = document.getElementById('register-url').value.trim();
        if (!url) return;
        const btn = document.getElementById('register-btn');
        btn.textContent = 'Registering…'; btn.disabled = true;
        try {{
            const res = await fetch('/api/agents/register', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{agent_url: url}})
            }});
            const data = await res.json();
            const el = document.getElementById('register-result');
            el.style.display = 'block';
            if (data.slug) {{
                el.innerHTML = `<span style="color:var(--success)">✓ Registered!</span> <a href="/agents/${{data.slug}}" style="color:var(--cyan)">View profile →</a>`;
                setTimeout(() => location.href = '/agents/' + data.slug, 1500);
            }} else {{
                el.innerHTML = `<span style="color:var(--danger)">Error: ${{data.detail || 'Unknown error'}}</span>`;
            }}
        }} catch(e) {{
            document.getElementById('register-result').innerHTML = `<span style="color:var(--danger)">${{e.message}}</span>`;
            document.getElementById('register-result').style.display = 'block';
        }}
        btn.textContent = 'Register'; btn.disabled = false;
    }}

    // Keyboard shortcut
    document.addEventListener('keydown', e => {{
        if (e.key === 'Escape') hideRegisterModal();
        if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {{
            e.preventDefault();
            document.getElementById('search').focus();
        }}
    }});

    loadAgents();
    </script>
</body>
</html>'''
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# AGENT PROFILE PAGE  /agents/{slug}
# ---------------------------------------------------------------------------

@router.get("/agents/{slug}", response_class=HTMLResponse)
async def agent_profile_page(slug: str, request: Request):
    """Beautiful public profile page for an AI agent."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.*, COALESCE(t.overall_score, 0) as trust_score,
               t.compliance_score, t.uptime_score, t.response_time_avg
        FROM agents a
        LEFT JOIN trust_scores t ON a.id = t.agent_id
        WHERE a.slug = ?
    """, (slug,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Agent not found")

    agent = dict(row)

    # Test history (show last 5 only)
    cursor.execute("""
        SELECT test_type, score, tested_at FROM test_history
        WHERE agent_id = ? ORDER BY tested_at DESC LIMIT 5
    """, (agent["id"],))
    history = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Parse data
    skills = []
    try:
        skills = json.loads(agent["skills"])
    except Exception:
        pass

    card = {}
    try:
        card = json.loads(agent["agent_card_json"])
    except Exception:
        pass

    cert = get_certification_for_agent(agent["url"])

    # Use certification score if available (more meaningful than averaged trust score)
    if cert and cert.get("score"):
        score = int(cert["score"])
    else:
        score = int(agent["trust_score"])
    compliance = int(agent.get("compliance_score") or 0)
    name = agent["name"]
    desc = agent["description"] or card.get("description", "An A2A protocol agent.")
    provider = agent["provider"] or ""
    version = agent["version"] or card.get("version", "")
    url = agent["url"]
    base_url = str(request.base_url).rstrip("/")
    # Public proxy URL for agents (so localhost agents are reachable from internet)
    public_url = f"{base_url}/a2a/proxy/{slug}"

    # Score styling
    if score >= 90:
        ring_c1, ring_c2, score_color, grade_label = "#FFD700", "#FFA500", "#FFD700", "Certified"
    elif score >= 80:
        ring_c1, ring_c2, score_color, grade_label = "#E8E8E8", "#A8A8A8", "#C0C0C0", "Verified"
    elif score >= 70:
        ring_c1, ring_c2, score_color, grade_label = "#CD7F32", "#8B4513", "#CD7F32", "Tested"
    elif score > 0:
        ring_c1, ring_c2, score_color, grade_label = "#FF5252", "#CC0000", "#FF5252", "Low"
    else:
        ring_c1, ring_c2, score_color, grade_label = "#334455", "#223344", "#667788", "Unrated"

    # Build skills HTML
    skills_html = ''.join(f'<span class="skill-tag">{s}</span>' for s in skills) if skills else '<span style="color:var(--text3)">No skills listed</span>'

    # Build card details from Agent Card
    card_details = []
    if card.get("capabilities"):
        caps = card["capabilities"]
        if caps.get("streaming"):
            card_details.append("📡 Streaming")
        if caps.get("pushNotifications"):
            card_details.append("🔔 Push Notifications")
        if caps.get("stateTransitionHistory"):
            card_details.append("📝 State History")
    if card.get("defaultInputModes"):
        card_details.append(f"📥 Input: {', '.join(card['defaultInputModes'][:3])}")
    if card.get("defaultOutputModes"):
        card_details.append(f"📤 Output: {', '.join(card['defaultOutputModes'][:3])}")

    card_details_html = ''.join(f'<div class="cap-item">{c}</div>' for c in card_details) if card_details else ''

    # Build history HTML
    history_html_items = []
    for h in history:
        h_score = h["score"]
        h_type = h["test_type"]
        h_date = ""
        try:
            dt = datetime.fromisoformat(h["tested_at"].replace("Z", ""))
            h_date = dt.strftime("%b %d, %Y %H:%M")
        except Exception:
            h_date = h["tested_at"][:16]
        h_color = "#00E676" if h_score >= 70 else "#FF5252"
        type_label = {"certify": "Certification", "full": "Full Suite", "live": "Live Test", "validate": "Validation"}.get(h_type, h_type.title())
        history_html_items.append(f'''
            <div class="history-item">
                <div class="history-score" style="color:{h_color}">{h_score}</div>
                <div class="history-info">
                    <div class="history-type">{type_label}</div>
                    <div class="history-date">{h_date}</div>
                </div>
            </div>''')
    history_html = ''.join(history_html_items) if history_html_items else '<div style="color:var(--text3);padding:1rem;text-align:center">No tests yet</div>'

    # Certification badge HTML
    cert_html = ""
    if cert:
        badge_style = cert.get("badge_style", "bronze")
        cert_id = cert["id"]
        c_label = {"gold": "🥇 Gold Certified", "silver": "🥈 Silver Verified", "bronze": "🥉 Bronze Tested"}.get(badge_style, "Tested")
        cert_html = f'''
        <div class="section">
            <h3 class="section-title">🏅 Certification</h3>
            <div class="cert-card {badge_style}">
                <div class="cert-label">{c_label}</div>
                <div class="cert-score">Score: {cert["score"]}/100</div>
                <a href="{base_url}/api/certificate/{cert_id}" class="btn btn-outline" style="margin-top:.75rem;font-size:.8rem">View Certificate →</a>
            </div>
        </div>'''

    # Embed section
    badge_url = f"{base_url}/api/agents/{slug}/badge"
    profile_url = f"{base_url}/agents/{slug}"

    # Claim CTA (hidden until claim flow is built)
    claim_html = ""

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    {_base_head(
        f"{name} — A2Apex Agent Profile",
        desc[:160],
        badge_url
    )}
    <style>
    {COMMON_CSS}

    .profile-hero{{
        max-width:900px;margin:0 auto;padding:2.5rem 2rem 1.5rem;
        display:flex;gap:2rem;align-items:flex-start;flex-wrap:wrap;
    }}
    .score-ring-wrap{{flex-shrink:0}}
    .score-ring{{width:160px;height:160px;position:relative}}
    .score-ring svg{{transform:rotate(-90deg)}}
    .score-ring .bg{{fill:none;stroke:#1A2A3F;stroke-width:8}}
    .score-ring .progress{{
        fill:none;stroke:url(#scoreGrad);stroke-width:8;stroke-linecap:round;
        stroke-dasharray:{score * 3.77} 377;
        animation:fill-ring 1.5s ease-out forwards;
    }}
    @keyframes fill-ring{{0%{{stroke-dasharray:0 377}}}}
    .score-number{{
        position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
        font-family:'Orbitron',monospace;font-size:2.75rem;font-weight:800;
        color:{score_color};
    }}
    .score-label{{
        text-align:center;margin-top:.25rem;font-size:.8rem;color:var(--text3);
        font-weight:600;text-transform:uppercase;letter-spacing:1px;
    }}
    .hero-info{{flex:1;min-width:250px}}
    .hero-name{{font-size:2rem;font-weight:700;margin-bottom:.25rem}}
    .hero-url{{font-family:'JetBrains Mono',monospace;font-size:.85rem;color:var(--cyan);word-break:break-all;margin-bottom:.75rem}}
    .hero-desc{{color:var(--text2);font-size:.95rem;margin-bottom:1rem;line-height:1.6}}
    .hero-meta{{display:flex;gap:1rem;flex-wrap:wrap;font-size:.8rem;color:var(--text3)}}
    .hero-meta span{{display:inline-flex;align-items:center;gap:.3rem}}

    .content{{max-width:900px;margin:0 auto;padding:0 2rem 3rem}}
    .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem}}
    @media(max-width:700px){{.two-col{{grid-template-columns:1fr}}.profile-hero{{flex-direction:column;align-items:center;text-align:center}}.hero-meta{{justify-content:center}}}}

    .section{{margin-bottom:1.5rem}}
    .section-title{{font-size:1rem;font-weight:600;margin-bottom:.75rem;color:var(--text2)}}

    .skills-grid{{display:flex;flex-wrap:wrap;gap:.5rem}}
    .skill-tag{{
        font-size:.8rem;padding:.35rem .75rem;border-radius:20px;
        background:var(--cyan-dim);color:var(--cyan);font-weight:500;
    }}

    .cap-item{{
        display:inline-flex;align-items:center;gap:.4rem;
        font-size:.8rem;padding:.3rem .7rem;border-radius:8px;
        background:var(--elevated);color:var(--text2);margin:.25rem;
    }}

    .history-item{{
        display:flex;align-items:center;gap:1rem;
        padding:.75rem 0;border-bottom:1px solid var(--border);
    }}
    .history-item:last-child{{border-bottom:none}}
    .history-score{{
        font-family:'Orbitron',monospace;font-size:1.25rem;font-weight:700;
        min-width:45px;text-align:right;
    }}
    .history-type{{font-size:.85rem;font-weight:500}}
    .history-date{{font-size:.75rem;color:var(--text3)}}

    .cert-card{{
        background:var(--elevated);border-radius:12px;padding:1.25rem;
        border:1px solid var(--border);
    }}
    .cert-card.gold{{border-color:rgba(255,215,0,.3);background:rgba(255,215,0,.05)}}
    .cert-card.silver{{border-color:rgba(192,192,192,.3);background:rgba(192,192,192,.05)}}
    .cert-card.bronze{{border-color:rgba(205,127,50,.3);background:rgba(205,127,50,.05)}}
    .cert-label{{font-size:1.1rem;font-weight:700;margin-bottom:.25rem}}
    .cert-score{{font-size:.85rem;color:var(--text2)}}

    .embed-section{{
        background:var(--bg2);border:1px solid var(--border);border-radius:12px;
        padding:1.25rem;
    }}
    .embed-code{{
        background:var(--bg);border:1px solid var(--border);border-radius:8px;
        padding:.6rem .75rem;font-family:'JetBrains Mono',monospace;font-size:.75rem;
        color:var(--cyan);word-break:break-all;cursor:pointer;
        transition:border-color .2s;margin-top:.5rem;
    }}
    .embed-code:hover{{border-color:var(--cyan)}}

    .actions{{display:flex;gap:.75rem;margin-top:1.5rem;flex-wrap:wrap}}

    /* Try This Agent Chat */
    .chat-container{{
        background:var(--bg2);border:1px solid var(--border);border-radius:12px;
        overflow:hidden;
    }}
    .chat-messages{{
        height:320px;overflow-y:auto;padding:1rem;display:flex;flex-direction:column;gap:.6rem;
    }}
    .chat-welcome{{
        text-align:center;color:var(--text3);font-size:.85rem;padding:2rem 1rem;
    }}
    .chat-bubble{{
        max-width:80%;padding:.65rem 1rem;border-radius:14px;font-size:.9rem;
        line-height:1.5;word-wrap:break-word;white-space:pre-wrap;
        animation:chatFadeIn .25s ease-out;
    }}
    @keyframes chatFadeIn{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:translateY(0)}}}}
    .chat-user{{
        align-self:flex-end;background:var(--cyan);color:#0d1b2a;
        border-bottom-right-radius:4px;
    }}
    .chat-agent{{
        align-self:flex-start;background:var(--elevated);color:var(--text1);
        border:1px solid var(--border);border-bottom-left-radius:4px;
    }}
    .chat-error{{
        align-self:center;background:rgba(255,82,82,.12);color:#FF5252;
        border:1px solid rgba(255,82,82,.25);font-size:.82rem;text-align:center;
    }}
    .chat-input-row{{
        display:flex;gap:0;border-top:1px solid var(--border);
    }}
    .chat-input{{
        flex:1;padding:.75rem 1rem;background:var(--bg);border:none;
        color:var(--text1);font-size:.9rem;font-family:inherit;outline:none;
    }}
    .chat-input::placeholder{{color:var(--text3)}}
    .chat-send-btn{{
        border-radius:0;padding:.75rem 1.25rem;font-size:.85rem;
        border:none;cursor:pointer;font-weight:600;
    }}
    .chat-send-btn:disabled{{opacity:.5;cursor:not-allowed}}
    .chat-status{{
        text-align:center;padding:.4rem;font-size:.8rem;color:var(--cyan);
        background:var(--cyan-dim);
    }}
    </style>
</head>
<body>
    {_topbar_html()}

    <div class="profile-hero">
        <div class="score-ring-wrap">
            <div class="score-ring">
                <svg width="160" height="160" viewBox="0 0 160 160">
                    <defs>
                        <linearGradient id="scoreGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" style="stop-color:{ring_c1}"/>
                            <stop offset="100%" style="stop-color:{ring_c2}"/>
                        </linearGradient>
                    </defs>
                    <circle class="bg" cx="80" cy="80" r="60"/>
                    <circle class="progress" cx="80" cy="80" r="60"/>
                </svg>
                <div class="score-number">{score if score > 0 else '—'}</div>
            </div>
            <div class="score-label">{grade_label}</div>
        </div>

        <div class="hero-info">
            <div class="hero-name">{name}</div>
            <div class="hero-url"><a href="{public_url}/.well-known/agent-card.json" target="_blank" style="color:var(--cyan);text-decoration:none">{public_url}</a></div>
            <div class="hero-desc">{desc}</div>
            <div class="hero-meta">
                {f'<span>🏢 {provider}</span>' if provider else ''}
                {f'<span>📦 v{version}</span>' if version else ''}
                <span>📅 Registered {agent["created_at"][:10]}</span>
            </div>
            <div class="actions">
                <a href="/agents" class="btn btn-cyan">← Directory</a>
            </div>
        </div>
    </div>

    <div class="content">
        <div class="two-col">
            <div>
                <div class="section">
                    <h3 class="section-title">🛠 Skills</h3>
                    <div class="skills-grid">{skills_html}</div>
                </div>

                {f'<div class="section"><h3 class="section-title">⚙️ Capabilities</h3><div>{card_details_html}</div></div>' if card_details_html else ''}

                {cert_html}
            </div>

            <div>
                <div class="section">
                    <h3 class="section-title">📊 Test History</h3>
                    <div>{history_html}</div>
                </div>

                <div class="section">
                    <h3 class="section-title">📛 Embed Badge</h3>
                    <div class="embed-section">
                        <div style="text-align:center;margin-bottom:.75rem">
                            <img src="{badge_url}" alt="{name} trust score" style="height:28px">
                        </div>
                        <div style="font-size:.8rem;color:var(--text3);margin-bottom:.25rem">Markdown</div>
                        <div class="embed-code" onclick="copyText(this)">[![{name}]({badge_url})]({profile_url})</div>
                        <div style="font-size:.8rem;color:var(--text3);margin-top:.75rem;margin-bottom:.25rem">HTML</div>
                        <div class="embed-code" onclick="copyText(this)">&lt;a href="{profile_url}"&gt;&lt;img src="{badge_url}" alt="{name}"&gt;&lt;/a&gt;</div>
                    </div>
                </div>
            </div>
        </div>

        {claim_html}

        <!-- Try This Agent Chat -->
        <div class="section" style="margin-top:2rem">
            <h3 class="section-title">💬 Try This Agent</h3>
            <p style="color:var(--text3);font-size:.85rem;margin-bottom:1rem">Send a message and see how this agent responds</p>
            <div class="chat-container">
                <div class="chat-messages" id="chatMessages">
                    <div class="chat-welcome">Type a message below to start a conversation with <strong>{name}</strong></div>
                </div>
                <div class="chat-input-row">
                    <input type="text" id="chatInput" class="chat-input" placeholder="Say something to this agent…" maxlength="2000" autocomplete="off"/>
                    <button id="chatSendBtn" class="btn btn-cyan chat-send-btn">Send</button>
                </div>
                <div class="chat-status" id="chatStatus" style="display:none">Agent is thinking…</div>
            </div>
        </div>
    </div>

    <script>
    function copyText(el) {{
        navigator.clipboard.writeText(el.textContent.trim()).then(() => {{
            const orig = el.style.borderColor;
            el.style.borderColor = 'var(--cyan)';
            el.setAttribute('data-copied', '1');
            setTimeout(() => {{ el.style.borderColor = orig; }}, 2000);
        }});
    }}

    // ---------- Try This Agent Chat ----------
    const chatMessages = document.getElementById('chatMessages');
    const chatInput = document.getElementById('chatInput');
    const chatSendBtn = document.getElementById('chatSendBtn');
    const chatStatus = document.getElementById('chatStatus');

    function appendMessage(role, text) {{
        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble chat-' + role;
        bubble.textContent = text;
        chatMessages.appendChild(bubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }}

    async function sendChatMessage() {{
        const text = chatInput.value.trim();
        if (!text) return;
        chatInput.value = '';
        appendMessage('user', text);
        chatSendBtn.disabled = true;
        chatInput.disabled = true;
        chatStatus.textContent = 'Agent is thinking…';
        chatStatus.style.display = 'block';
        try {{
            const res = await fetch('/api/agents/{slug}/chat', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{message: text}})
            }});
            const data = await res.json();
            chatStatus.style.display = 'none';
            if (data.error) {{
                appendMessage('error', data.error);
            }} else {{
                appendMessage('agent', data.reply || '(empty response)');
            }}
        }} catch(e) {{
            chatStatus.style.display = 'none';
            appendMessage('error', 'Network error: ' + e.message);
        }}
        chatSendBtn.disabled = false;
        chatInput.disabled = false;
        chatInput.focus();
    }}

    chatSendBtn.addEventListener('click', sendChatMessage);
    chatInput.addEventListener('keydown', e => {{
        if (e.key === 'Enter' && !e.shiftKey) {{
            e.preventDefault();
            sendChatMessage();
        }}
    }});
    </script>
</body>
</html>'''

    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# TRY THIS AGENT — Chat proxy endpoint
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


@router.post("/api/agents/{slug}/chat")
async def agent_chat_proxy(slug: str, body: ChatRequest):
    """Proxy a chat message to an agent via A2A protocol and return the reply."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM agents WHERE slug = ?", (slug,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_url = row["url"]

    # Build A2A JSON-RPC message/send payload
    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": str(uuid.uuid4()),
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "type": "text", "text": body.message}]
            }
        }
    }

    # Try the URL as-is first, then with /a2a appended (common A2A convention)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(agent_url, json=payload)
            if resp.status_code == 404:
                # Try with /a2a suffix
                alt_url = agent_url.rstrip("/") + "/a2a"
                resp = await client.post(alt_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        return JSONResponse({"error": "Agent did not respond in time (30s timeout). It may be offline."})
    except httpx.ConnectError:
        return JSONResponse({"error": "Could not connect to the agent. It may be offline or unreachable."})
    except Exception as e:
        return JSONResponse({"error": f"Error contacting agent: {str(e)}"})

    # Extract reply text from A2A response
    # A2A responses vary: result.artifacts[].parts[].text or result.status.message.parts[].text
    reply_text = ""
    try:
        result = data.get("result", {})
        # Try artifacts first (common in task responses)
        artifacts = result.get("artifacts", [])
        if artifacts:
            for art in artifacts:
                for part in art.get("parts", []):
                    part_type = part.get("type") or part.get("kind")
                    if part_type == "text" and part.get("text"):
                        reply_text += part["text"] + "\n"
        # Fall back to status message
        if not reply_text:
            status_msg = result.get("status", {}).get("message", {})
            for part in status_msg.get("parts", []):
                part_type = part.get("type") or part.get("kind")
                if part_type == "text" and part.get("text"):
                    reply_text += part["text"] + "\n"
        # Fall back: check for error in JSON-RPC response
        if not reply_text and "error" in data:
            err = data["error"]
            reply_text = f"Agent error: {err.get('message', str(err))}"
    except Exception:
        reply_text = "(Could not parse agent response)"

    return JSONResponse({"reply": reply_text.strip()})


# ============================================================================
# PUBLIC A2A PROXY — Makes local agents accessible to the internet
# ============================================================================

@router.post("/a2a/proxy/{slug}")
async def a2a_proxy(slug: str, request: Request):
    """
    Public A2A endpoint that proxies requests to the agent's real URL.
    This lets local agents (like localhost:8092) be reachable from the internet.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM agents WHERE slug = ?", (slug,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32001, "message": "Agent not found"}}, status_code=404)

    agent_url = row["url"]
    body = await request.json()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(agent_url, json=body)
            if resp.status_code == 404:
                alt_url = agent_url.rstrip("/") + "/a2a"
                resp = await client.post(alt_url, json=body)
            return JSONResponse(resp.json(), status_code=resp.status_code)
    except httpx.TimeoutException:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32000, "message": "Agent timeout"}}, status_code=504)
    except httpx.ConnectError:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32000, "message": "Agent unreachable"}}, status_code=502)
    except Exception as e:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}}, status_code=500)


@router.get("/a2a/proxy/{slug}/.well-known/agent-card.json")
async def a2a_proxy_agent_card(slug: str, request: Request):
    """Proxy the agent's Agent Card, rewriting the URL to our public proxy."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM agents WHERE slug = ?", (slug,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return JSONResponse({"error": "Agent not found"}, status_code=404)

    agent_url = row["url"].rstrip("/")
    card_url = f"{agent_url}/.well-known/agent-card.json"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(card_url)
            card = resp.json()
            # Rewrite the URL to our public proxy
            base = str(request.base_url).rstrip("/")
            card["url"] = f"{base}/a2a/proxy/{slug}"
            return JSONResponse(card)
    except Exception as e:
        return JSONResponse({"error": f"Could not fetch agent card: {str(e)}"}, status_code=502)
