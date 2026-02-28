"""
A2Apex Certification Badge System

Generate and manage certification badges for A2A protocol compliance.
Supports free/pro/enterprise tiers with different badge styles.
"""

import os
import uuid
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

# Import testing infrastructure
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import (
    fetch_and_validate_agent_card,
    run_live_tests,
    AgentCardValidator,
)


# ============================================================================
# DATABASE SETUP
# ============================================================================

DB_PATH = Path(__file__).parent.parent / "data" / "certifications.db"


def init_db():
    """Initialize the certifications database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS certifications (
            id TEXT PRIMARY KEY,
            agent_url TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            score INTEGER NOT NULL,
            test_results TEXT NOT NULL,
            certified INTEGER NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            badge_style TEXT NOT NULL DEFAULT 'basic'
        )
    """)
    # Create index for fast lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_url ON certifications(agent_url)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_certified ON certifications(certified)
    """)
    conn.commit()
    conn.close()


# Initialize on module load
init_db()


# ============================================================================
# MODELS
# ============================================================================

class CertifyRequest(BaseModel):
    """Request to certify an agent."""
    agent_url: str = Field(..., description="Base URL of the A2A agent to certify")
    plan: str = Field("free", description="Certification plan: free, pro, or enterprise")
    

class CertificationResult(BaseModel):
    """Result of certification."""
    id: str
    agent_url: str
    agent_name: str
    score: int
    certified: bool
    plan: str
    created_at: str
    expires_at: str
    badge_style: str
    badge_url: str
    embed_html: str
    embed_markdown: str


# ============================================================================
# SVG BADGE GENERATION
# ============================================================================

def generate_badge_svg(
    score: int,
    certified: bool,
    badge_style: str = "basic",
    plan: str = "free",
    date_str: Optional[str] = None
) -> str:
    """
    Generate an SVG badge based on certification status.
    
    Styles:
    - basic (free): Simple gray/cyan badge
    - verified (pro): Premium blue/cyan with checkmark
    - premium (enterprise): Gold/cyan with shield
    """
    
    # Badge dimensions
    height = 28
    
    # Colors by style
    if badge_style == "premium":
        # Gold/cyan enterprise style
        left_bg = "#B8860B"  # Dark gold
        right_bg = "#0A1628"  # Navy
        accent = "#FFD700"  # Gold
        text_left = "#FFFFFF"
        text_right = "#00E5FF"
        prefix = "🛡"
        label = "A2Apex Certified"
    elif badge_style == "verified":
        # Blue/cyan pro style
        left_bg = "#0066FF"
        right_bg = "#0A1628"
        accent = "#00E5FF"
        text_left = "#FFFFFF"
        text_right = "#00E5FF"
        prefix = "✓"
        label = "A2Apex Verified"
    else:
        # Gray/cyan free style
        left_bg = "#555555"
        right_bg = "#0A1628"
        accent = "#00E5FF"
        text_left = "#FFFFFF"
        text_right = "#00E5FF"
        prefix = ""
        label = "A2Apex Tested"
    
    # Build score text
    if certified:
        score_text = f"Score: {score}/100"
    else:
        score_text = f"Score: {score}/100"
    
    # Add date for verified/premium
    if date_str and badge_style in ["verified", "premium"]:
        score_text = f"{score_text} | {date_str}"
    
    # Add plan label for enterprise
    if badge_style == "premium":
        score_text = f"{score_text} | Enterprise"
    
    # Calculate widths
    label_with_prefix = f"{prefix} {label}" if prefix else label
    label_width = len(label_with_prefix) * 7 + 16
    score_width = len(score_text) * 6.5 + 16
    total_width = label_width + score_width
    
    # Generate SVG
    if badge_style == "premium":
        # Enterprise badge with gradient
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" viewBox="0 0 {total_width} {height}">
  <defs>
    <linearGradient id="gold-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#FFD700"/>
      <stop offset="100%" style="stop-color:#B8860B"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="1" stdDeviation="1" flood-opacity="0.3"/>
    </filter>
  </defs>
  <rect width="{total_width}" height="{height}" rx="4" fill="{right_bg}"/>
  <rect width="{label_width}" height="{height}" rx="4" fill="url(#gold-grad)" filter="url(#shadow)"/>
  <text x="{label_width/2}" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="{text_left}" text-anchor="middle">{label_with_prefix}</text>
  <text x="{label_width + score_width/2}" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="{text_right}" text-anchor="middle">{score_text}</text>
</svg>'''
    elif badge_style == "verified":
        # Pro badge with subtle gradient
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" viewBox="0 0 {total_width} {height}">
  <defs>
    <linearGradient id="blue-grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#0A3DFF"/>
      <stop offset="100%" style="stop-color:#0066FF"/>
    </linearGradient>
  </defs>
  <rect width="{total_width}" height="{height}" rx="4" fill="{right_bg}"/>
  <rect width="{label_width}" height="{height}" rx="4" fill="url(#blue-grad)"/>
  <text x="{label_width/2}" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="{text_left}" text-anchor="middle">{label_with_prefix}</text>
  <text x="{label_width + score_width/2}" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="{text_right}" text-anchor="middle">{score_text}</text>
</svg>'''
    else:
        # Basic badge
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" viewBox="0 0 {total_width} {height}">
  <rect width="{total_width}" height="{height}" rx="4" fill="{right_bg}"/>
  <rect width="{label_width}" height="{height}" rx="4" fill="{left_bg}"/>
  <text x="{label_width/2}" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="{text_left}" text-anchor="middle">{label}</text>
  <text x="{label_width + score_width/2}" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="{text_right}" text-anchor="middle">{score_text}</text>
</svg>'''
    
    return svg


def generate_failed_badge_svg() -> str:
    """Generate a badge for failed certification."""
    label = "A2Apex"
    score_text = "Not Certified"
    label_width = len(label) * 7 + 16
    score_width = len(score_text) * 6.5 + 16
    total_width = label_width + score_width
    height = 28
    
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" viewBox="0 0 {total_width} {height}">
  <rect width="{total_width}" height="{height}" rx="4" fill="#0A1628"/>
  <rect width="{label_width}" height="{height}" rx="4" fill="#555555"/>
  <text x="{label_width/2}" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="#FFFFFF" text-anchor="middle">{label}</text>
  <text x="{label_width + score_width/2}" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="#FF5252" text-anchor="middle">{score_text}</text>
</svg>'''


# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(prefix="/api", tags=["badges"])


@router.post("/certify", response_model=CertificationResult)
async def certify_agent(request: CertifyRequest, req: Request):
    """
    Run full test suite on an agent URL and create certification record.
    
    If score >= 80/100, creates a valid certification.
    Returns certification data with embed codes.
    """
    agent_url = request.agent_url.rstrip("/")
    plan = request.plan.lower()
    
    if plan not in ["free", "pro", "enterprise"]:
        raise HTTPException(status_code=400, detail="Invalid plan. Must be: free, pro, or enterprise")
    
    # Determine badge style and expiry
    if plan == "enterprise":
        badge_style = "premium"
        expires_days = 365
    elif plan == "pro":
        badge_style = "verified"
        expires_days = 365
    else:
        badge_style = "basic"
        expires_days = 90
    
    # Run tests
    try:
        # First, validate agent card
        card_report = await fetch_and_validate_agent_card(agent_url)
        agent_name = "Unknown Agent"
        
        if card_report.agent_card:
            agent_name = card_report.agent_card.get("name", "Unknown Agent")
        
        # Run live tests
        live_report = await run_live_tests(agent_url, timeout=60.0)
        
        # Calculate score
        # Weight: 40% agent card, 60% live tests
        card_score = card_report.score if hasattr(card_report, 'score') else 0
        live_score = live_report.score if hasattr(live_report, 'score') else 0
        
        total_score = int(card_score * 0.4 + live_score * 0.6)
        
        # Build test results
        test_results = {
            "agent_card": card_report.to_dict(),
            "live_tests": live_report.to_dict(),
            "calculated_score": total_score
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Testing failed: {str(e)}")
    
    # Determine certification status
    certified = total_score >= 80
    
    # Create certification record
    cert_id = str(uuid.uuid4())
    now = datetime.utcnow()
    expires_at = now + timedelta(days=expires_days)
    
    # Store in database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO certifications (
            id, agent_url, agent_name, score, test_results, 
            certified, plan, created_at, expires_at, badge_style
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cert_id,
        agent_url,
        agent_name,
        total_score,
        json.dumps(test_results),
        1 if certified else 0,
        plan,
        now.isoformat() + "Z",
        expires_at.isoformat() + "Z",
        badge_style
    ))
    conn.commit()
    conn.close()
    
    # Build response
    base_url = str(req.base_url).rstrip("/")
    badge_url = f"{base_url}/api/badge/{cert_id}.svg"
    
    embed_html = f'<a href="{base_url}/registry/{quote(agent_url, safe="")}"><img src="{badge_url}" alt="A2Apex Certification"></a>'
    embed_markdown = f'[![A2Apex Certification]({badge_url})]({base_url}/registry/{quote(agent_url, safe="")})'
    
    return CertificationResult(
        id=cert_id,
        agent_url=agent_url,
        agent_name=agent_name,
        score=total_score,
        certified=certified,
        plan=plan,
        created_at=now.isoformat() + "Z",
        expires_at=expires_at.isoformat() + "Z",
        badge_style=badge_style,
        badge_url=badge_url,
        embed_html=embed_html,
        embed_markdown=embed_markdown
    )


@router.get("/badge/{cert_id}.svg")
async def get_badge_svg(cert_id: str):
    """
    Returns an SVG badge image for a certification.
    
    Publicly accessible - no auth required to view badges.
    """
    # Remove .svg extension if present in the ID
    cert_id = cert_id.replace(".svg", "")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT score, certified, badge_style, plan, created_at, expires_at
        FROM certifications WHERE id = ?
    """, (cert_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        # Return a "not found" badge
        svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="120" height="28" viewBox="0 0 120 28">
  <rect width="120" height="28" rx="4" fill="#555555"/>
  <text x="60" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="#FFFFFF" text-anchor="middle">Badge Not Found</text>
</svg>'''
        return Response(content=svg, media_type="image/svg+xml")
    
    score, certified, badge_style, plan, created_at, expires_at = row
    
    # Check if expired
    if expires_at:
        try:
            exp_date = datetime.fromisoformat(expires_at.replace("Z", ""))
            if datetime.utcnow() > exp_date:
                # Return expired badge
                svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="140" height="28" viewBox="0 0 140 28">
  <rect width="140" height="28" rx="4" fill="#555555"/>
  <text x="70" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="#FF5252" text-anchor="middle">Certification Expired</text>
</svg>'''
                return Response(content=svg, media_type="image/svg+xml")
        except:
            pass
    
    # Generate badge
    date_str = None
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", ""))
            date_str = dt.strftime("%b %Y")
        except:
            pass
    
    if certified:
        svg = generate_badge_svg(
            score=score,
            certified=True,
            badge_style=badge_style,
            plan=plan,
            date_str=date_str
        )
    else:
        svg = generate_failed_badge_svg()
    
    return Response(
        content=svg, 
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
        }
    )


@router.get("/badge/{cert_id}.json")
async def get_badge_json(cert_id: str):
    """
    Returns certification data as JSON.
    
    Publicly accessible.
    """
    cert_id = cert_id.replace(".json", "")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, agent_url, agent_name, score, certified, plan, 
               created_at, expires_at, badge_style
        FROM certifications WHERE id = ?
    """, (cert_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Certification not found")
    
    return {
        "id": row[0],
        "agent_url": row[1],
        "agent_name": row[2],
        "score": row[3],
        "certified": bool(row[4]),
        "plan": row[5],
        "created_at": row[6],
        "expires_at": row[7],
        "badge_style": row[8]
    }


@router.get("/registry/{agent_url:path}")
async def lookup_agent(agent_url: str):
    """
    Look up if an agent URL is certified.
    
    Returns the most recent certification for the agent.
    """
    # Decode URL
    agent_url = unquote(agent_url).rstrip("/")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, agent_url, agent_name, score, certified, plan,
               created_at, expires_at, badge_style
        FROM certifications 
        WHERE agent_url = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (agent_url,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found in registry")
    
    return {
        "id": row[0],
        "agent_url": row[1],
        "agent_name": row[2],
        "score": row[3],
        "certified": bool(row[4]),
        "plan": row[5],
        "created_at": row[6],
        "expires_at": row[7],
        "badge_style": row[8]
    }


@router.get("/registry")
async def list_certified_agents(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    certified_only: bool = Query(True)
):
    """
    List all certified agents in the public registry.
    
    Returns paginated list of certifications.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Build query
    if certified_only:
        cursor.execute("""
            SELECT id, agent_url, agent_name, score, certified, plan,
                   created_at, expires_at, badge_style
            FROM certifications 
            WHERE certified = 1
            ORDER BY score DESC, created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
    else:
        cursor.execute("""
            SELECT id, agent_url, agent_name, score, certified, plan,
                   created_at, expires_at, badge_style
            FROM certifications 
            ORDER BY score DESC, created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
    
    rows = cursor.fetchall()
    
    # Get total count
    if certified_only:
        cursor.execute("SELECT COUNT(*) FROM certifications WHERE certified = 1")
    else:
        cursor.execute("SELECT COUNT(*) FROM certifications")
    total = cursor.fetchone()[0]
    
    conn.close()
    
    agents = []
    for row in rows:
        agents.append({
            "id": row[0],
            "agent_url": row[1],
            "agent_name": row[2],
            "score": row[3],
            "certified": bool(row[4]),
            "plan": row[5],
            "created_at": row[6],
            "expires_at": row[7],
            "badge_style": row[8]
        })
    
    return {
        "agents": agents,
        "total": total,
        "limit": limit,
        "offset": offset
    }


# ============================================================================
# PUBLIC REGISTRY HTML PAGE
# ============================================================================

@router.get("/registry-page", response_class=HTMLResponse)
async def registry_page(req: Request):
    """
    Serve the public registry HTML page.
    """
    base_url = str(req.base_url).rstrip("/")
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A2Apex Certified Agents Registry</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚡</text></svg>">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Orbitron:wght@700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0A1628;
            --bg-secondary: #0D1D31;
            --bg-card: #111F36;
            --bg-elevated: #162740;
            --cyan: #00E5FF;
            --cyan-dim: rgba(0, 229, 255, 0.15);
            --cyan-glow: rgba(0, 229, 255, 0.25);
            --success: #00E676;
            --success-bg: rgba(0, 230, 118, 0.15);
            --warning: #FFB300;
            --warning-bg: rgba(255, 179, 0, 0.15);
            --text-primary: #FFFFFF;
            --text-secondary: rgba(255, 255, 255, 0.7);
            --text-muted: rgba(255, 255, 255, 0.45);
            --border: rgba(255, 255, 255, 0.1);
            --shadow-md: 0 4px 20px rgba(0, 0, 0, 0.3);
        }}
        
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        
        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            min-height: 100vh;
        }}
        
        .header {{
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
            padding: 1rem 2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        
        .logo {{
            font-family: 'Orbitron', monospace;
            font-size: 1.5rem;
            font-weight: 800;
            color: var(--cyan);
            text-decoration: none;
        }}
        
        .main {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }}
        
        .page-header {{
            text-align: center;
            margin-bottom: 3rem;
        }}
        
        .page-header h1 {{
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }}
        
        .page-header h1 span {{
            color: var(--cyan);
        }}
        
        .page-header p {{
            color: var(--text-secondary);
            font-size: 1.125rem;
        }}
        
        .search-bar {{
            max-width: 600px;
            margin: 0 auto 2rem;
            position: relative;
        }}
        
        .search-input {{
            width: 100%;
            padding: 1rem 1rem 1rem 3rem;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            color: var(--text-primary);
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s;
        }}
        
        .search-input:focus {{
            border-color: var(--cyan);
        }}
        
        .search-icon {{
            position: absolute;
            left: 1rem;
            top: 50%;
            transform: translateY(-50%);
            opacity: 0.5;
        }}
        
        .stats {{
            display: flex;
            justify-content: center;
            gap: 3rem;
            margin-bottom: 2rem;
        }}
        
        .stat {{
            text-align: center;
        }}
        
        .stat-value {{
            font-size: 2.5rem;
            font-weight: 700;
            color: var(--cyan);
        }}
        
        .stat-label {{
            font-size: 0.875rem;
            color: var(--text-muted);
            text-transform: uppercase;
        }}
        
        .agents-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 1.25rem;
        }}
        
        .agent-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.5rem;
            transition: all 0.2s;
        }}
        
        .agent-card:hover {{
            border-color: var(--cyan-glow);
            transform: translateY(-2px);
            box-shadow: var(--shadow-md);
        }}
        
        .agent-header {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            margin-bottom: 1rem;
        }}
        
        .agent-name {{
            font-size: 1.125rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
        }}
        
        .agent-url {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8125rem;
            color: var(--text-muted);
            word-break: break-all;
        }}
        
        .agent-score {{
            font-family: 'Orbitron', monospace;
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--success);
        }}
        
        .agent-score.warning {{
            color: var(--warning);
        }}
        
        .agent-meta {{
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
        }}
        
        .meta-tag {{
            font-size: 0.75rem;
            padding: 0.3rem 0.6rem;
            background: var(--bg-elevated);
            border-radius: 6px;
            color: var(--text-secondary);
        }}
        
        .meta-tag.pro {{
            background: rgba(0, 102, 255, 0.2);
            color: #66B2FF;
        }}
        
        .meta-tag.enterprise {{
            background: rgba(255, 215, 0, 0.2);
            color: #FFD700;
        }}
        
        .badge-embed {{
            margin-top: 0.75rem;
        }}
        
        .badge-embed img {{
            display: inline-block;
        }}
        
        .empty-state {{
            text-align: center;
            padding: 4rem 2rem;
            color: var(--text-muted);
        }}
        
        .empty-state h3 {{
            font-size: 1.25rem;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
        }}
        
        .footer {{
            text-align: center;
            padding: 2rem;
            color: var(--text-muted);
            font-size: 0.875rem;
            border-top: 1px solid var(--border);
            margin-top: 3rem;
        }}
        
        .footer a {{
            color: var(--cyan);
            text-decoration: none;
        }}
    </style>
</head>
<body>
    <header class="header">
        <a href="/" class="logo">A2APEX</a>
        <a href="/" style="color: var(--text-secondary); text-decoration: none; font-size: 0.875rem;">← Back to Testing Tool</a>
    </header>
    
    <main class="main">
        <div class="page-header">
            <h1>Certified <span>Agents</span> Registry</h1>
            <p>Discover A2A protocol-compliant agents that have passed certification</p>
        </div>
        
        <div class="search-bar">
            <span class="search-icon">🔍</span>
            <input type="text" class="search-input" id="searchInput" placeholder="Search agents by name or URL...">
        </div>
        
        <div class="stats" id="stats">
            <div class="stat">
                <div class="stat-value" id="totalAgents">-</div>
                <div class="stat-label">Certified Agents</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="avgScore">-</div>
                <div class="stat-label">Average Score</div>
            </div>
        </div>
        
        <div class="agents-grid" id="agentsGrid">
            <div class="empty-state">
                <h3>Loading agents...</h3>
            </div>
        </div>
    </main>
    
    <footer class="footer">
        <p>
            <a href="/">A2Apex</a> — The A2A Protocol Testing Tool
            <span style="margin: 0 0.5rem;">|</span>
            <a href="https://github.com/Hauk307/a2apex" target="_blank">GitHub</a>
        </p>
    </footer>
    
    <script>
        const BASE_URL = "{base_url}";
        let allAgents = [];
        
        async function loadAgents() {{
            try {{
                const response = await fetch(`${{BASE_URL}}/api/registry?limit=200`);
                const data = await response.json();
                allAgents = data.agents;
                
                // Update stats
                document.getElementById('totalAgents').textContent = data.total;
                if (allAgents.length > 0) {{
                    const avgScore = Math.round(allAgents.reduce((sum, a) => sum + a.score, 0) / allAgents.length);
                    document.getElementById('avgScore').textContent = avgScore + '%';
                }}
                
                renderAgents(allAgents);
            }} catch (error) {{
                console.error('Failed to load agents:', error);
                document.getElementById('agentsGrid').innerHTML = `
                    <div class="empty-state">
                        <h3>Failed to load agents</h3>
                        <p>Please try again later</p>
                    </div>
                `;
            }}
        }}
        
        function renderAgents(agents) {{
            const grid = document.getElementById('agentsGrid');
            
            if (agents.length === 0) {{
                grid.innerHTML = `
                    <div class="empty-state">
                        <h3>No certified agents yet</h3>
                        <p>Be the first to certify your A2A agent!</p>
                    </div>
                `;
                return;
            }}
            
            grid.innerHTML = agents.map(agent => {{
                const date = new Date(agent.created_at).toLocaleDateString('en-US', {{ 
                    year: 'numeric', month: 'short', day: 'numeric' 
                }});
                const scoreClass = agent.score >= 90 ? '' : 'warning';
                const planClass = agent.plan === 'enterprise' ? 'enterprise' : (agent.plan === 'pro' ? 'pro' : '');
                const planLabel = agent.plan.charAt(0).toUpperCase() + agent.plan.slice(1);
                
                return `
                    <div class="agent-card">
                        <div class="agent-header">
                            <div>
                                <div class="agent-name">${{agent.agent_name}}</div>
                                <div class="agent-url">${{agent.agent_url}}</div>
                            </div>
                            <div class="agent-score ${{scoreClass}}">${{agent.score}}</div>
                        </div>
                        <div class="badge-embed">
                            <img src="${{BASE_URL}}/api/badge/${{agent.id}}.svg" alt="A2Apex Badge">
                        </div>
                        <div class="agent-meta">
                            <span class="meta-tag ${{planClass}}">${{planLabel}}</span>
                            <span class="meta-tag">Certified ${{date}}</span>
                        </div>
                    </div>
                `;
            }}).join('');
        }}
        
        // Search functionality
        document.getElementById('searchInput').addEventListener('input', (e) => {{
            const query = e.target.value.toLowerCase();
            const filtered = allAgents.filter(agent => 
                agent.agent_name.toLowerCase().includes(query) ||
                agent.agent_url.toLowerCase().includes(query)
            );
            renderAgents(filtered);
        }});
        
        // Initial load
        loadAgents();
    </script>
</body>
</html>'''
    
    return HTMLResponse(content=html)
