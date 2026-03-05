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
# TEST USAGE TRACKING (Shared with main.py)
# ============================================================================

TEST_USAGE_DB_PATH = Path(__file__).parent.parent / "data" / "test_usage.db"
FREE_TESTS_PER_MONTH = 3
ANON_TESTS_TOTAL = 5


def init_test_usage_db():
    """Initialize the test usage database."""
    TEST_USAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(TEST_USAGE_DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_test_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            month TEXT NOT NULL,
            test_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, month)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anon_test_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT UNIQUE NOT NULL,
            test_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()


init_test_usage_db()


def get_client_ip(request: Request) -> str:
    """Get client IP address from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.client.host if request.client else "unknown"


def check_test_limit_badges(request: Request, plan: str = "free") -> tuple[bool, int, str]:
    """
    Check if user can run a test based on their plan and usage.
    Returns: (allowed, remaining, message)
    """
    # Pro and Enterprise have unlimited tests
    if plan in ("pro", "enterprise"):
        return True, -1, "Unlimited tests"
    
    conn = sqlite3.connect(TEST_USAGE_DB_PATH)
    cursor = conn.cursor()
    
    # For badges, we use IP-based tracking for simplicity
    ip_address = get_client_ip(request)
    
    cursor.execute("""
        SELECT test_count FROM anon_test_usage WHERE ip_address = ?
    """, (ip_address,))
    row = cursor.fetchone()
    
    test_count = row[0] if row else 0
    remaining = ANON_TESTS_TOTAL - test_count
    
    conn.close()
    
    if test_count >= ANON_TESTS_TOTAL:
        return False, 0, f"You've used all {ANON_TESTS_TOTAL} free tests. Upgrade to Pro for unlimited testing."
    
    return True, remaining, f"{remaining} tests remaining"


def record_test_usage_badges(request: Request) -> None:
    """Record that a test was run."""
    ip_address = get_client_ip(request)
    now = datetime.utcnow().isoformat() + "Z"
    
    conn = sqlite3.connect(TEST_USAGE_DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO anon_test_usage (ip_address, test_count, created_at)
        VALUES (?, 1, ?)
        ON CONFLICT(ip_address) 
        DO UPDATE SET test_count = test_count + 1
    """, (ip_address, now))
    
    conn.commit()
    conn.close()


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

def get_grade_info(score: int) -> dict:
    """
    Get grade information based on score.
    Returns grade name, emoji, colors, and label.
    """
    if score >= 90:
        return {
            "grade": "gold",
            "emoji": "★",
            "medal": "🥇",
            "label": "A2Apex Certified",
            "colors": {
                "start": "#FFD700",
                "end": "#FFA500",
                "text": "#0A1628"  # Dark text for contrast on gold
            }
        }
    elif score >= 80:
        return {
            "grade": "silver",
            "emoji": "✓",
            "medal": "🥈",
            "label": "A2Apex Verified",
            "colors": {
                "start": "#C0C0C0",
                "end": "#A8A8A8",
                "text": "#FFFFFF"
            }
        }
    else:  # 70-79 (Bronze)
        return {
            "grade": "bronze",
            "emoji": "",
            "medal": "🥉",
            "label": "A2Apex Tested",
            "colors": {
                "start": "#CD7F32",
                "end": "#CD7F32",
                "text": "#FFFFFF"
            }
        }


def generate_badge_svg(
    score: int,
    certified: bool,
    badge_style: str = "basic",
    plan: str = "free",
    date_str: Optional[str] = None
) -> str:
    """
    Generate an SVG badge based on score grade.
    
    Grade levels (based on score):
    - Gold (90-100): Premium gold gradient, star icon
    - Silver (80-89): Silver gradient, checkmark
    - Bronze (70-79): Bronze/copper, basic look
    
    Plan controls additional features:
    - Free: 90-day expiry
    - Pro: 1-year expiry + "PRO" indicator
    - Enterprise: Permanent + "ENTERPRISE" indicator
    """
    
    # Badge dimensions
    height = 28
    brand_bg = "#0A1628"  # Navy left section
    brand_text = "#00E5FF"  # Cyan A2Apex text
    
    # Get grade-based styling
    grade_info = get_grade_info(score)
    
    # Build the label with grade emoji
    if grade_info["emoji"]:
        label = f"{grade_info['emoji']} {grade_info['label']}"
    else:
        label = grade_info['label']
    
    # Build score text with plan indicator
    score_text = f"Score: {score}/100"
    
    # Add plan indicator for Pro/Enterprise
    if plan == "enterprise":
        score_text = f"{score_text} | ENT"
    elif plan == "pro":
        score_text = f"{score_text} | PRO"
    
    # Calculate width — single full-width badge, no brand section
    full_label = f"{label} | {score_text}"
    total_width = len(full_label) * 7 + 32
    
    grade = grade_info["grade"]
    colors = grade_info["colors"]
    
    if grade == "gold":
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" viewBox="0 0 {total_width} {height}">
  <defs>
    <linearGradient id="grade-grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:{colors['start']}"/>
      <stop offset="100%" style="stop-color:{colors['end']}"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="1" stdDeviation="1" flood-color="#FFD700" flood-opacity="0.4"/>
    </filter>
  </defs>
  <rect width="{total_width}" height="{height}" rx="4" fill="url(#grade-grad)"/>
  <text x="{total_width/2}" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="{colors['text']}" text-anchor="middle" filter="url(#glow)">{full_label}</text>
</svg>'''
    elif grade == "silver":
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" viewBox="0 0 {total_width} {height}">
  <defs>
    <linearGradient id="grade-grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:{colors['start']}"/>
      <stop offset="100%" style="stop-color:{colors['end']}"/>
    </linearGradient>
  </defs>
  <rect width="{total_width}" height="{height}" rx="4" fill="url(#grade-grad)"/>
  <text x="{total_width/2}" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="{colors['text']}" text-anchor="middle">{full_label}</text>
</svg>'''
    else:
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" viewBox="0 0 {total_width} {height}">
  <rect width="{total_width}" height="{height}" rx="4" fill="{colors['start']}"/>
  <text x="{total_width/2}" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="{colors['text']}" text-anchor="middle">{full_label}</text>
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
    
    If score >= 70/100, creates a valid certification.
    Returns certification data with embed codes.
    """
    agent_url = request.agent_url.rstrip("/")
    plan = request.plan.lower()
    
    if plan not in ["free", "pro", "enterprise"]:
        raise HTTPException(status_code=400, detail="Invalid plan. Must be: free, pro, or enterprise")
    
    # Check test limit for free plan users
    allowed, remaining, message = check_test_limit_badges(req, plan)
    if not allowed:
        return JSONResponse(
            status_code=403,
            content={
                "error": "free_limit_reached",
                "message": "You've used all 5 free tests this month. Upgrade to Pro for unlimited testing.",
                "upgrade_url": "/"
            }
        )
    
    # Determine expiry based on plan
    # Badge style is now determined by score, not plan
    if plan == "enterprise":
        expires_days = 36500  # ~100 years = permanent
    elif plan == "pro":
        expires_days = 365  # 1 year
    else:
        expires_days = 90  # 90 days for free
    
    # Badge style will be set after we know the score
    badge_style = "basic"  # Placeholder, updated after scoring
    
    # Run the FULL test suite (same as Full Suite tab) for consistent scoring
    import asyncio
    from core import run_live_tests, run_auth_tests, run_error_tests, run_streaming_tests, run_perf_tests
    
    try:
        # First, get agent name from card
        card_report = await fetch_and_validate_agent_card(agent_url)
        agent_name = "Unknown Agent"
        if card_report.agent_card:
            agent_name = card_report.agent_card.get("name", "Unknown Agent")
        
        # Run ALL test suites concurrently (same as Full Suite)
        results = await asyncio.gather(
            run_live_tests(agent_url, timeout=60.0),
            run_auth_tests(agent_url, timeout=60.0),
            run_error_tests(agent_url, timeout=60.0),
            run_streaming_tests(agent_url, timeout=60.0),
            run_perf_tests(agent_url, timeout=60.0),
            return_exceptions=True
        )
        
        # Calculate score same way as Full Suite
        total_passed = 0
        total_tests = 0
        for report in results:
            if isinstance(report, Exception):
                continue
            report_dict = report.to_dict()
            summary = report_dict.get("summary", {})
            total_passed += summary.get("passed", 0)
            total_tests += summary.get("total", 0)
        
        total_score = int((total_passed / total_tests * 100) if total_tests > 0 else 0)
        
        test_results = {
            "total_tests": total_tests,
            "total_passed": total_passed,
            "calculated_score": total_score
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Testing failed: {str(e)}")
    
    # Determine certification status
    certified = total_score >= 70
    
    # Determine badge style based on score (grade)
    if total_score >= 90:
        badge_style = "gold"
    elif total_score >= 80:
        badge_style = "silver"
    elif total_score >= 70:
        badge_style = "bronze"
    else:
        badge_style = "failed"
    
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
    
    # Record test usage for free tier users
    if plan == "free":
        record_test_usage_badges(req)
    
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


@router.get("/certificate/{cert_id}", response_class=HTMLResponse)
async def get_certificate_page(cert_id: str, request: Request):
    """Full certificate celebration page."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT agent_name, agent_url, score, certified, badge_style, plan, created_at, expires_at
        FROM certifications WHERE id = ?
    """, (cert_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Certificate not found")

    agent_name, agent_url, score, certified, badge_style, plan, created_at, expires_at = row

    date_str = ""
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", ""))
            date_str = dt.strftime("%B %d, %Y")
        except:
            date_str = created_at[:10]

    exp_str = ""
    if expires_at:
        try:
            dt = datetime.fromisoformat(expires_at.replace("Z", ""))
            exp_str = dt.strftime("%B %d, %Y")
        except:
            pass

    # Determine grade
    if score >= 90:
        grade = "GOLD"
        grade_emoji = "🥇"
        grade_title = "A2Apex Certified"
        grade_color = "#FFD700"
        grade_gradient = "linear-gradient(135deg, #FFD700, #FFA500)"
        grade_glow = "rgba(255, 215, 0, 0.4)"
        ring_color_1 = "#FFD700"
        ring_color_2 = "#FFA500"
        congrats = "Your agent demonstrates exceptional A2A protocol compliance."
        particle_color = "#FFD700"
    elif score >= 80:
        grade = "SILVER"
        grade_emoji = "🥈"
        grade_title = "A2Apex Verified"
        grade_color = "#C0C0C0"
        grade_gradient = "linear-gradient(135deg, #E8E8E8, #A8A8A8)"
        grade_glow = "rgba(192, 192, 192, 0.4)"
        ring_color_1 = "#E8E8E8"
        ring_color_2 = "#A8A8A8"
        congrats = "Your agent meets A2A protocol verification standards."
        particle_color = "#C0C0C0"
    else:
        grade = "BRONZE"
        grade_emoji = "🥉"
        grade_title = "A2Apex Tested"
        grade_color = "#CD7F32"
        grade_gradient = "linear-gradient(135deg, #CD7F32, #8B4513)"
        grade_glow = "rgba(205, 127, 50, 0.4)"
        ring_color_1 = "#CD7F32"
        ring_color_2 = "#8B4513"
        congrats = "Your agent has passed A2A protocol testing."
        particle_color = "#CD7F32"

    next_tier_html = ""
    if score < 80:
        next_tier_html = f'<p class="next-tier">Score 80+ to earn <span style="color: #C0C0C0">🥈 Silver — A2Apex Verified</span></p>'
    elif score < 90:
        next_tier_html = f'<p class="next-tier">Score 90+ to earn <span style="color: #FFD700">🥇 Gold — A2Apex Certified</span></p>'

    base = str(request.base_url).rstrip("/")
    badge_url = f"{base}/api/badge/{cert_id}.svg"
    cert_url = f"{base}/api/certificate/{cert_id}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{grade_emoji} {agent_name} — {grade_title}</title>
    <meta property="og:title" content="{agent_name} — {grade_title}">
    <meta property="og:description" content="Scored {score}/100 on A2A protocol compliance testing">
    <meta property="og:image" content="{badge_url}">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Orbitron:wght@700;800&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #0A1628;
            color: #E0E0E0;
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            overflow-x: hidden;
        }}
        .particles {{
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            pointer-events: none;
            z-index: 0;
        }}
        .particle {{
            position: absolute;
            border-radius: 50%;
            background: {particle_color};
            opacity: 0;
            animation: float-up 3s ease-out forwards;
        }}
        @keyframes float-up {{
            0% {{ opacity: 0; transform: translateY(100vh) scale(0); }}
            20% {{ opacity: 0.8; }}
            100% {{ opacity: 0; transform: translateY(-20vh) scale(1); }}
        }}
        .container {{
            position: relative;
            z-index: 1;
            max-width: 640px;
            width: 100%;
            padding: 2rem 1.5rem;
            text-align: center;
        }}
        .logo {{
            font-family: 'Orbitron', monospace;
            font-size: 1.2rem;
            font-weight: 800;
            color: #00E5FF;
            text-decoration: none;
            margin-bottom: 2rem;
            display: inline-block;
            filter: brightness(1.3) drop-shadow(0 0 10px rgba(0, 229, 255, 0.3));
        }}
        .congrats {{
            font-size: 1.1rem;
            color: #8899AA;
            margin-bottom: 2rem;
            line-height: 1.6;
        }}
        .certificate {{
            background: linear-gradient(135deg, #0D1D31, #111F36);
            border: 2px solid {grade_color}40;
            border-radius: 20px;
            padding: 2.5rem 2rem;
            margin-bottom: 2rem;
            position: relative;
            overflow: hidden;
        }}
        .certificate::before {{
            content: '';
            position: absolute;
            top: -2px; left: -2px; right: -2px; bottom: -2px;
            border-radius: 20px;
            background: {grade_gradient};
            opacity: 0.1;
            z-index: 0;
        }}
        .certificate > * {{ position: relative; z-index: 1; }}
        .medal {{
            font-size: 4rem;
            margin-bottom: 0.5rem;
            animation: medal-drop 0.8s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
        }}
        @keyframes medal-drop {{
            0% {{ opacity: 0; transform: translateY(-60px) scale(0.3); }}
            100% {{ opacity: 1; transform: translateY(0) scale(1); }}
        }}
        .grade-label {{
            font-family: 'Orbitron', monospace;
            font-size: 1.8rem;
            font-weight: 800;
            background: {grade_gradient};
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 0.5rem;
            letter-spacing: 3px;
        }}
        .grade-title {{
            font-size: 1.1rem;
            color: {grade_color};
            margin-bottom: 1.5rem;
            font-weight: 600;
        }}
        .score-ring {{
            width: 140px;
            height: 140px;
            margin: 0 auto 1.5rem;
            position: relative;
        }}
        .score-ring svg {{
            transform: rotate(-90deg);
        }}
        .score-ring .bg {{
            fill: none;
            stroke: #1A2A3F;
            stroke-width: 8;
        }}
        .score-ring .progress {{
            fill: none;
            stroke: url(#scoreGrad);
            stroke-width: 8;
            stroke-linecap: round;
            stroke-dasharray: {score * 3.77} 377;
            animation: fill-ring 1.5s ease-out forwards;
        }}
        @keyframes fill-ring {{
            0% {{ stroke-dasharray: 0 377; }}
        }}
        .score-number {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-family: 'Orbitron', monospace;
            font-size: 2.5rem;
            font-weight: 800;
            color: {grade_color};
        }}
        .score-label {{
            font-size: 0.85rem;
            color: #667788;
            margin-bottom: 1.5rem;
        }}
        .agent-name {{
            font-size: 1.4rem;
            font-weight: 700;
            color: #FFFFFF;
            margin-bottom: 0.3rem;
        }}
        .agent-url {{
            font-size: 0.85rem;
            color: #00E5FF;
            word-break: break-all;
            margin-bottom: 1rem;
        }}
        .cert-date {{
            font-size: 0.8rem;
            color: #556677;
        }}
        .next-tier {{
            font-size: 0.95rem;
            color: #667788;
            margin-bottom: 2rem;
        }}
        .embed-section {{
            background: #0D1D31;
            border: 1px solid #1A2A3F;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1rem;
            text-align: left;
        }}
        .embed-title {{
            font-size: 0.85rem;
            font-weight: 600;
            color: #8899AA;
            margin-bottom: 0.75rem;
        }}
        .embed-preview {{
            text-align: center;
            margin-bottom: 1rem;
            padding: 1rem;
            background: #0A1628;
            border-radius: 8px;
        }}
        .embed-code {{
            background: #0A1628;
            border: 1px solid #1A2A3F;
            border-radius: 8px;
            padding: 0.75rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: #00E5FF;
            word-break: break-all;
            cursor: pointer;
            position: relative;
            transition: border-color 0.2s;
        }}
        .embed-code:hover {{
            border-color: #00E5FF40;
        }}
        .embed-code::after {{
            content: 'Click to copy';
            position: absolute;
            top: -8px;
            right: 8px;
            background: #0D1D31;
            padding: 0 6px;
            font-size: 0.65rem;
            color: #556677;
        }}
        .embed-label {{
            font-size: 0.85rem;
            color: #8899AA;
            margin-bottom: 0.5rem;
            line-height: 1.4;
        }}
        .embed-label strong {{
            color: #CCDDEE;
        }}
        .copied {{
            border-color: #00E5FF !important;
        }}
        .copied::after {{
            content: '✓ Copied!' !important;
            color: #00E5FF !important;
        }}
        .footer {{
            margin-top: 2rem;
            font-size: 0.8rem;
            color: #445566;
        }}
        .footer a {{
            color: #00E5FF;
            text-decoration: none;
        }}
        @media (max-width: 480px) {{
            .grade-label {{ font-size: 1.4rem; }}
            .certificate {{ padding: 2rem 1.5rem; }}
            .score-number {{ font-size: 2rem; }}
        }}
    </style>
</head>
<body>
    <div class="particles" id="particles"></div>
    <div class="container">
        <a href="https://a2apex.io" class="logo"><img src="data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPHN2ZyBpZD0iTGF5ZXJfMSIgZGF0YS1uYW1lPSJMYXllciAxIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnhsaW5rPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5L3hsaW5rIiB2aWV3Qm94PSIwIDAgMTE0Ni42MyAzMTcuMSI+CiAgPGRlZnM+CiAgICA8c3R5bGU+CiAgICAgIC5jbHMtMSB7CiAgICAgICAgZmlsbDogdXJsKCNsaW5lYXItZ3JhZGllbnQtMik7CiAgICAgIH0KCiAgICAgIC5jbHMtMiB7CiAgICAgICAgZmlsbDogI2ZmZmZmZjsKICAgICAgfQoKICAgICAgLmNscy0zIHsKICAgICAgICBmaWxsOiB1cmwoI3JhZGlhbC1ncmFkaWVudCk7CiAgICAgIH0KCiAgICAgIC5jbHMtNCB7CiAgICAgICAgZmlsbDogdXJsKCNsaW5lYXItZ3JhZGllbnQtMyk7CiAgICAgICAgb3BhY2l0eTogLjg1OwogICAgICB9CgogICAgICAuY2xzLTUgewogICAgICAgIGZpbGw6IHVybCgjbGluZWFyLWdyYWRpZW50KTsKICAgICAgfQogICAgPC9zdHlsZT4KICAgIDxyYWRpYWxHcmFkaWVudCBpZD0icmFkaWFsLWdyYWRpZW50IiBjeD0iMjIxLjciIGN5PSIxNTguNTUiIGZ4PSIyMjEuNyIgZnk9IjE1OC41NSIgcj0iNjMuNTEiIGdyYWRpZW50VHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTEwMi40NyAtNDIuOTQpIHJvdGF0ZSgtMjIuNjMpIHNjYWxlKDEgMS45NikiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjMTljMWY0Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjI2IiBzdG9wLWNvbG9yPSIjMThiZWYyIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjQyIiBzdG9wLWNvbG9yPSIjMTdiNmVkIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjU1IiBzdG9wLWNvbG9yPSIjMTVhN2U1Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjY3IiBzdG9wLWNvbG9yPSIjMTI5M2RhIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjc3IiBzdG9wLWNvbG9yPSIjMGY3OGNiIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjg3IiBzdG9wLWNvbG9yPSIjMGE1OGI5Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjk2IiBzdG9wLWNvbG9yPSIjMDUzMmE0Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzAzMjE5YiIvPgogICAgPC9yYWRpYWxHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudCBpZD0ibGluZWFyLWdyYWRpZW50IiB4MT0iMjMxLjQ5IiB5MT0iMTg4LjI0IiB4Mj0iMTgyLjUxIiB5Mj0iMjM4LjgzIiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+CiAgICAgIDxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzE5YzFmNCIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii4wOSIgc3RvcC1jb2xvcj0iIzE2YWJlOCIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii4zMSIgc3RvcC1jb2xvcj0iIzBmN2FjYyIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii41MiIgc3RvcC1jb2xvcj0iIzA5NTNiNyIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii43MSIgc3RvcC1jb2xvcj0iIzA2MzdhNyIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii44NyIgc3RvcC1jb2xvcj0iIzAzMjY5ZSIvPgogICAgICA8c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiMwMzIxOWIiLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQgaWQ9ImxpbmVhci1ncmFkaWVudC0yIiB4MT0iMTIxLjg4IiB5MT0iMTM3LjI5IiB4Mj0iMTA1LjIyIiB5Mj0iMjQ4LjMiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjMTljMWY0Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzAzMjE5YiIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudCBpZD0ibGluZWFyLWdyYWRpZW50LTMiIHgxPSIxODUuMjciIHkxPSIxODYuNjMiIHgyPSIxNTIuODEiIHkyPSIyNDkuMTEiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjMTljMWY0Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjEzIiBzdG9wLWNvbG9yPSIjMThiYmYxIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjI5IiBzdG9wLWNvbG9yPSIjMTZhY2U4Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjQ4IiBzdG9wLWNvbG9yPSIjMTI5MmRhIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjY3IiBzdG9wLWNvbG9yPSIjMGQ2ZmM2Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjg3IiBzdG9wLWNvbG9yPSIjMDc0MmFkIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzAzMjE5YiIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICA8L2RlZnM+CiAgPGc+CiAgICA8cG9seWdvbiBjbGFzcz0iY2xzLTMiIHBvaW50cz0iMjkwLjc5IDI2My41MiAyNjAuMzYgMjYzLjUyIDE4NC41MSAxMTMuNyAxNjcuODMgMTQ2LjY1IDE1Mi42MiAxMTYuNTkgMTg0LjUxIDUzLjU3IDI5MC43OSAyNjMuNTIiLz4KICAgIDxwb2x5Z29uIGNsYXNzPSJjbHMtNSIgcG9pbnRzPSIxNjYuNTMgMTkwLjA4IDE4Ni4zMyAyMjkuMiAyMDMuNzIgMjYzLjUyIDIzNi45NCAyNjMuNTIgMTgzLjE1IDE1Ny4yNSAxNjYuNTMgMTkwLjA4Ii8+CiAgICA8cG9seWdvbiBjbGFzcz0iY2xzLTEiIHBvaW50cz0iMTY3LjgzIDE0Ni42NSAxNTMuNjkgMTc0LjYgMTQxLjI5IDE1MC4xIDkzLjMgMjQ0LjkgMTI3IDI0NC45IDExNi44NCAyNjMuNTIgNTUuNTggMjYzLjUyIDE0MS4yOSA5NC4yIDE1Mi42MiAxMTYuNTkgMTY3LjgzIDE0Ni42NSIvPgogICAgPHBvbHlnb24gY2xhc3M9ImNscy00IiBwb2ludHM9IjE5OS44MyAxOTAuMDggMTgwLjAzIDIyOS4yIDE2Mi42NSAyNjMuNTIgMTI5LjQyIDI2My41MiAxODMuMjEgMTU3LjI1IDE5OS44MyAxOTAuMDgiLz4KICA8L2c+CiAgPGc+CiAgICA8cGF0aCBjbGFzcz0iY2xzLTIiIGQ9Ik00NzAuOTcsMjE0LjA2di0yNy4xYzAtMTYuNDIsMTEuMzYtMjQuMzYsMzIuMTYtMjQuMzZoMzkuOTZjMTQuNjQsMCwyMS4wOC00Ljc5LDIxLjA4LTEzLjU1LDAtMTAuNjctOS43Mi0xMy45Ni0yOC42LTEzLjk2aC01OS4yNmw5LjU4LTEyLjU5aDU1Ljg0YzI2LjQyLDAsMzYuNjgsMTAuNTQsMzYuNjgsMjUuNzNzLTkuODUsMjUuMzItMzMuOTQsMjUuMzJoLTM5Ljk2Yy0xMi41OSwwLTE5LjE2LDMuOTctMTkuMTYsMTMuMjh2MTQuNzhoOTQuNDRsLTkuNTgsMTIuNDVoLTk5LjIzWiIvPgogICAgPHBhdGggY2xhc3M9ImNscy0yIiBkPSJNNzQ4LjEsMTg0LjIydjI5Ljg0aC0xNC43OHYtNDIuMTVoNjUuNDJjMTcuMzgsMCwzMS40OC00LjkzLDMxLjQ4LTE4LjIsMC0xNC4yMy0xMi44Ny0xOC42MS0zMS42MS0xOC42MWgtNjUuNTZsOS44NS0xMi41OWg2MC45YzI1LjE4LDAsNDEuMiwxMS43Nyw0MS4yLDMxLjM0cy0xNS44OCwzMC4zOC00MS4yLDMwLjM4aC01NS43WiIvPgogICAgPHBhdGggY2xhc3M9ImNscy0yIiBkPSJNODU4LjY3LDIxNC4wNnYtOTEuNTZoOTcuMTdsLTkuNzIsMTIuNTloLTcyLjY3djI3LjUxaDc4LjE1bC04LjQ5LDEwLjk1aC02OS42NnYyOC4wNmg4My4wOGwtOS43MiwxMi40NWgtODguMTRaIi8+CiAgICA8cGF0aCBjbGFzcz0iY2xzLTIiIGQ9Ik0xMDY3LjI0LDIxNC4wNmwtNDQuMzQtMzguNi00NC42MiwzOC42aC0xOC42MWw1NC42MS00Ny4wOC01MS4wNS00NC40OGgyMC41M2w0MC41MSwzNS43Miw0MC43OS0zNS43MmgxOS4zbC01MS4wNSw0My45Myw1NC44OCw0Ny42M2gtMjAuOTRaIi8+CiAgICA8cGF0aCBjbGFzcz0iY2xzLTIiIGQ9Ik00NDUuNDUsMjE0LjA2aDE4LjE1bC01OC41OC0xMDUuNGMtMi4wNS0zLjE1LTUuMzQtNS42MS05LjcyLTUuNjFzLTcuOCwyLjc0LTkuNzIsNS42MWwtNTkuNCwxMDUuNGgxNy41MmwxNi4xOC0yOS43aDY5LjY2bDE1LjksMjkuN1pNMzY2LjY3LDE3MS45bDI4LjM1LTUyLjAzLDI3Ljg1LDUyLjAzaC01Ni4yMVoiLz4KICAgIDxwYXRoIGNsYXNzPSJjbHMtMiIgZD0iTTcwNS43NCwyMTQuMDZoMTguMTVsLTU4LjU4LTEwNS40Yy0yLjA1LTMuMTUtNS4zNC01LjYxLTkuNzItNS42MXMtNy44LDIuNzQtOS43Miw1LjYxbC01OS40LDEwNS40aDE3LjUybDE2LjE4LTI5LjdoNjkuNjZsMTUuOSwyOS43Wk02MjYuOTYsMTcxLjlsMjguMzUtNTIuMDMsMjcuODUsNTIuMDNoLTU2LjIxWiIvPgogIDwvZz4KPC9zdmc+" alt="A2Apex" style="height: 40px; filter: brightness(1.5) drop-shadow(0 0 20px rgba(25, 193, 244, 0.5));"></a>
        
        <p class="congrats">🎉 Congratulations! {congrats}</p>
        
        <div class="certificate">
            <div class="medal">{grade_emoji}</div>
            <div class="grade-label">{grade}</div>
            <div class="grade-title">{grade_title}</div>
            
            <div class="score-ring">
                <svg width="140" height="140" viewBox="0 0 140 140">
                    <defs>
                        <linearGradient id="scoreGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" style="stop-color: {ring_color_1}"/>
                            <stop offset="100%" style="stop-color: {ring_color_2}"/>
                        </linearGradient>
                    </defs>
                    <circle class="bg" cx="70" cy="70" r="60"/>
                    <circle class="progress" cx="70" cy="70" r="60"/>
                </svg>
                <div class="score-number">{score}</div>
            </div>
            <div class="score-label">Compliance Score out of 100</div>
            
            <div class="agent-name">{agent_name}</div>
            <div class="agent-url">{agent_url}</div>
            <div class="cert-date">Certified on {date_str}{f' · Expires {exp_str}' if exp_str else ''}</div>
        </div>
        
        {next_tier_html}
        
        <div class="embed-section">
            <div class="embed-title">📛 Embed this badge</div>
            <div class="embed-preview">
                <img src="{badge_url}" alt="A2Apex Badge" style="height: 28px;">
            </div>
            <p class="embed-label">📝 <strong>Markdown</strong> — Paste into your GitHub README, docs, or any .md file</p>
            <div class="embed-code" onclick="copyEmbed(this, 'md')">
                [![A2Apex {grade_title}]({badge_url})]({cert_url})
            </div>
            <br>
            <p class="embed-label">🌐 <strong>HTML</strong> — Add to your website, landing page, or agent documentation</p>
            <div class="embed-code" onclick="copyEmbed(this, 'html')">
                &lt;a href="{cert_url}"&gt;&lt;img src="{badge_url}" alt="A2Apex {grade_title}"&gt;&lt;/a&gt;
            </div>
            <br>
            <p class="embed-label">🔗 <strong>Direct URL</strong> — Share anywhere or use as an image link</p>
            <div class="embed-code" onclick="copyEmbed(this, 'url')">
                {badge_url}
            </div>
        </div>
        
        <div class="footer">
            <a href="https://a2apex.io">A2Apex</a> — The Testing Platform for AI Agents<br>
            <a href="/agents">View Public Registry</a>
        </div>
    </div>
    
    <script>
        // Particle celebration
        const container = document.getElementById('particles');
        for (let i = 0; i < 40; i++) {{
            const p = document.createElement('div');
            p.className = 'particle';
            p.style.left = Math.random() * 100 + '%';
            p.style.width = p.style.height = (Math.random() * 8 + 4) + 'px';
            p.style.animationDelay = (Math.random() * 2) + 's';
            p.style.animationDuration = (Math.random() * 2 + 2) + 's';
            container.appendChild(p);
        }}
        
        function copyEmbed(el, type) {{
            const text = el.textContent.trim();
            navigator.clipboard.writeText(text).then(() => {{
                el.classList.add('copied');
                setTimeout(() => el.classList.remove('copied'), 2000);
            }});
        }}
    </script>
</body>
</html>"""

    return HTMLResponse(content=html)


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
        <a href="/" class="logo"><img src="data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPHN2ZyBpZD0iTGF5ZXJfMSIgZGF0YS1uYW1lPSJMYXllciAxIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnhsaW5rPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5L3hsaW5rIiB2aWV3Qm94PSIwIDAgMTE0Ni42MyAzMTcuMSI+CiAgPGRlZnM+CiAgICA8c3R5bGU+CiAgICAgIC5jbHMtMSB7CiAgICAgICAgZmlsbDogdXJsKCNsaW5lYXItZ3JhZGllbnQtMik7CiAgICAgIH0KCiAgICAgIC5jbHMtMiB7CiAgICAgICAgZmlsbDogI2ZmZmZmZjsKICAgICAgfQoKICAgICAgLmNscy0zIHsKICAgICAgICBmaWxsOiB1cmwoI3JhZGlhbC1ncmFkaWVudCk7CiAgICAgIH0KCiAgICAgIC5jbHMtNCB7CiAgICAgICAgZmlsbDogdXJsKCNsaW5lYXItZ3JhZGllbnQtMyk7CiAgICAgICAgb3BhY2l0eTogLjg1OwogICAgICB9CgogICAgICAuY2xzLTUgewogICAgICAgIGZpbGw6IHVybCgjbGluZWFyLWdyYWRpZW50KTsKICAgICAgfQogICAgPC9zdHlsZT4KICAgIDxyYWRpYWxHcmFkaWVudCBpZD0icmFkaWFsLWdyYWRpZW50IiBjeD0iMjIxLjciIGN5PSIxNTguNTUiIGZ4PSIyMjEuNyIgZnk9IjE1OC41NSIgcj0iNjMuNTEiIGdyYWRpZW50VHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTEwMi40NyAtNDIuOTQpIHJvdGF0ZSgtMjIuNjMpIHNjYWxlKDEgMS45NikiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjMTljMWY0Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjI2IiBzdG9wLWNvbG9yPSIjMThiZWYyIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjQyIiBzdG9wLWNvbG9yPSIjMTdiNmVkIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjU1IiBzdG9wLWNvbG9yPSIjMTVhN2U1Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjY3IiBzdG9wLWNvbG9yPSIjMTI5M2RhIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjc3IiBzdG9wLWNvbG9yPSIjMGY3OGNiIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjg3IiBzdG9wLWNvbG9yPSIjMGE1OGI5Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjk2IiBzdG9wLWNvbG9yPSIjMDUzMmE0Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzAzMjE5YiIvPgogICAgPC9yYWRpYWxHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudCBpZD0ibGluZWFyLWdyYWRpZW50IiB4MT0iMjMxLjQ5IiB5MT0iMTg4LjI0IiB4Mj0iMTgyLjUxIiB5Mj0iMjM4LjgzIiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+CiAgICAgIDxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzE5YzFmNCIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii4wOSIgc3RvcC1jb2xvcj0iIzE2YWJlOCIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii4zMSIgc3RvcC1jb2xvcj0iIzBmN2FjYyIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii41MiIgc3RvcC1jb2xvcj0iIzA5NTNiNyIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii43MSIgc3RvcC1jb2xvcj0iIzA2MzdhNyIvPgogICAgICA8c3RvcCBvZmZzZXQ9Ii44NyIgc3RvcC1jb2xvcj0iIzAzMjY5ZSIvPgogICAgICA8c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiMwMzIxOWIiLz4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8bGluZWFyR3JhZGllbnQgaWQ9ImxpbmVhci1ncmFkaWVudC0yIiB4MT0iMTIxLjg4IiB5MT0iMTM3LjI5IiB4Mj0iMTA1LjIyIiB5Mj0iMjQ4LjMiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjMTljMWY0Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzAzMjE5YiIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICAgIDxsaW5lYXJHcmFkaWVudCBpZD0ibGluZWFyLWdyYWRpZW50LTMiIHgxPSIxODUuMjciIHkxPSIxODYuNjMiIHgyPSIxNTIuODEiIHkyPSIyNDkuMTEiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KICAgICAgPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjMTljMWY0Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjEzIiBzdG9wLWNvbG9yPSIjMThiYmYxIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjI5IiBzdG9wLWNvbG9yPSIjMTZhY2U4Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjQ4IiBzdG9wLWNvbG9yPSIjMTI5MmRhIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjY3IiBzdG9wLWNvbG9yPSIjMGQ2ZmM2Ii8+CiAgICAgIDxzdG9wIG9mZnNldD0iLjg3IiBzdG9wLWNvbG9yPSIjMDc0MmFkIi8+CiAgICAgIDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzAzMjE5YiIvPgogICAgPC9saW5lYXJHcmFkaWVudD4KICA8L2RlZnM+CiAgPGc+CiAgICA8cG9seWdvbiBjbGFzcz0iY2xzLTMiIHBvaW50cz0iMjkwLjc5IDI2My41MiAyNjAuMzYgMjYzLjUyIDE4NC41MSAxMTMuNyAxNjcuODMgMTQ2LjY1IDE1Mi42MiAxMTYuNTkgMTg0LjUxIDUzLjU3IDI5MC43OSAyNjMuNTIiLz4KICAgIDxwb2x5Z29uIGNsYXNzPSJjbHMtNSIgcG9pbnRzPSIxNjYuNTMgMTkwLjA4IDE4Ni4zMyAyMjkuMiAyMDMuNzIgMjYzLjUyIDIzNi45NCAyNjMuNTIgMTgzLjE1IDE1Ny4yNSAxNjYuNTMgMTkwLjA4Ii8+CiAgICA8cG9seWdvbiBjbGFzcz0iY2xzLTEiIHBvaW50cz0iMTY3LjgzIDE0Ni42NSAxNTMuNjkgMTc0LjYgMTQxLjI5IDE1MC4xIDkzLjMgMjQ0LjkgMTI3IDI0NC45IDExNi44NCAyNjMuNTIgNTUuNTggMjYzLjUyIDE0MS4yOSA5NC4yIDE1Mi42MiAxMTYuNTkgMTY3LjgzIDE0Ni42NSIvPgogICAgPHBvbHlnb24gY2xhc3M9ImNscy00IiBwb2ludHM9IjE5OS44MyAxOTAuMDggMTgwLjAzIDIyOS4yIDE2Mi42NSAyNjMuNTIgMTI5LjQyIDI2My41MiAxODMuMjEgMTU3LjI1IDE5OS44MyAxOTAuMDgiLz4KICA8L2c+CiAgPGc+CiAgICA8cGF0aCBjbGFzcz0iY2xzLTIiIGQ9Ik00NzAuOTcsMjE0LjA2di0yNy4xYzAtMTYuNDIsMTEuMzYtMjQuMzYsMzIuMTYtMjQuMzZoMzkuOTZjMTQuNjQsMCwyMS4wOC00Ljc5LDIxLjA4LTEzLjU1LDAtMTAuNjctOS43Mi0xMy45Ni0yOC42LTEzLjk2aC01OS4yNmw5LjU4LTEyLjU5aDU1Ljg0YzI2LjQyLDAsMzYuNjgsMTAuNTQsMzYuNjgsMjUuNzNzLTkuODUsMjUuMzItMzMuOTQsMjUuMzJoLTM5Ljk2Yy0xMi41OSwwLTE5LjE2LDMuOTctMTkuMTYsMTMuMjh2MTQuNzhoOTQuNDRsLTkuNTgsMTIuNDVoLTk5LjIzWiIvPgogICAgPHBhdGggY2xhc3M9ImNscy0yIiBkPSJNNzQ4LjEsMTg0LjIydjI5Ljg0aC0xNC43OHYtNDIuMTVoNjUuNDJjMTcuMzgsMCwzMS40OC00LjkzLDMxLjQ4LTE4LjIsMC0xNC4yMy0xMi44Ny0xOC42MS0zMS42MS0xOC42MWgtNjUuNTZsOS44NS0xMi41OWg2MC45YzI1LjE4LDAsNDEuMiwxMS43Nyw0MS4yLDMxLjM0cy0xNS44OCwzMC4zOC00MS4yLDMwLjM4aC01NS43WiIvPgogICAgPHBhdGggY2xhc3M9ImNscy0yIiBkPSJNODU4LjY3LDIxNC4wNnYtOTEuNTZoOTcuMTdsLTkuNzIsMTIuNTloLTcyLjY3djI3LjUxaDc4LjE1bC04LjQ5LDEwLjk1aC02OS42NnYyOC4wNmg4My4wOGwtOS43MiwxMi40NWgtODguMTRaIi8+CiAgICA8cGF0aCBjbGFzcz0iY2xzLTIiIGQ9Ik0xMDY3LjI0LDIxNC4wNmwtNDQuMzQtMzguNi00NC42MiwzOC42aC0xOC42MWw1NC42MS00Ny4wOC01MS4wNS00NC40OGgyMC41M2w0MC41MSwzNS43Miw0MC43OS0zNS43MmgxOS4zbC01MS4wNSw0My45Myw1NC44OCw0Ny42M2gtMjAuOTRaIi8+CiAgICA8cGF0aCBjbGFzcz0iY2xzLTIiIGQ9Ik00NDUuNDUsMjE0LjA2aDE4LjE1bC01OC41OC0xMDUuNGMtMi4wNS0zLjE1LTUuMzQtNS42MS05LjcyLTUuNjFzLTcuOCwyLjc0LTkuNzIsNS42MWwtNTkuNCwxMDUuNGgxNy41MmwxNi4xOC0yOS43aDY5LjY2bDE1LjksMjkuN1pNMzY2LjY3LDE3MS45bDI4LjM1LTUyLjAzLDI3Ljg1LDUyLjAzaC01Ni4yMVoiLz4KICAgIDxwYXRoIGNsYXNzPSJjbHMtMiIgZD0iTTcwNS43NCwyMTQuMDZoMTguMTVsLTU4LjU4LTEwNS40Yy0yLjA1LTMuMTUtNS4zNC01LjYxLTkuNzItNS42MXMtNy44LDIuNzQtOS43Miw1LjYxbC01OS40LDEwNS40aDE3LjUybDE2LjE4LTI5LjdoNjkuNjZsMTUuOSwyOS43Wk02MjYuOTYsMTcxLjlsMjguMzUtNTIuMDMsMjcuODUsNTIuMDNoLTU2LjIxWiIvPgogIDwvZz4KPC9zdmc+" alt="A2Apex" style="height: 32px; filter: brightness(1.5) drop-shadow(0 0 20px rgba(25, 193, 244, 0.5));"></a>
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
        
        function getGradeInfo(score) {{
            if (score >= 90) return {{ medal: '🥇', grade: 'GOLD', color: '#FFD700' }};
            if (score >= 80) return {{ medal: '🥈', grade: 'SILVER', color: '#C0C0C0' }};
            return {{ medal: '🥉', grade: 'BRONZE', color: '#CD7F32' }};
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
            
            // Sort by score (highest first)
            agents.sort((a, b) => b.score - a.score);
            
            grid.innerHTML = agents.map(agent => {{
                const date = new Date(agent.created_at).toLocaleDateString('en-US', {{ 
                    year: 'numeric', month: 'short', day: 'numeric' 
                }});
                const gradeInfo = getGradeInfo(agent.score);
                const planClass = agent.plan === 'enterprise' ? 'enterprise' : (agent.plan === 'pro' ? 'pro' : '');
                const planLabel = agent.plan.charAt(0).toUpperCase() + agent.plan.slice(1);
                
                return `
                    <div class="agent-card">
                        <div class="agent-header">
                            <div>
                                <div class="agent-name">${{gradeInfo.medal}} ${{agent.agent_name}}</div>
                                <div class="agent-url">${{agent.agent_url}}</div>
                            </div>
                            <div class="agent-score" style="color: ${{gradeInfo.color}}">${{agent.score}}</div>
                        </div>
                        <div class="badge-embed">
                            <img src="${{BASE_URL}}/api/badge/${{agent.id}}.svg" alt="A2Apex Badge">
                        </div>
                        <div class="agent-meta">
                            <span class="meta-tag" style="background: ${{gradeInfo.color}}22; color: ${{gradeInfo.color}}">${{gradeInfo.grade}}</span>
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
