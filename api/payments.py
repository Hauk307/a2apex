"""
A2Apex Stripe Payment Integration

Handles subscriptions for Pro ($29/mo) and Enterprise ($499/mo) plans.
"""

import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
import stripe

from api.auth import get_current_user, get_db


# ============================================================================
# CONFIGURATION
# ============================================================================

# Load Stripe keys from files
STRIPE_SECRET_KEY_PATH = Path.home() / ".openclaw" / ".stripe_secret_key"
STRIPE_PUBLISHABLE_KEY_PATH = Path.home() / ".openclaw" / ".stripe_publishable_key"
STRIPE_CONFIG_PATH = Path(__file__).parent.parent / "data" / "stripe_config.json"

def load_stripe_key(path: Path) -> str:
    """Load a Stripe key from file."""
    if path.exists():
        return path.read_text().strip()
    raise ValueError(f"Stripe key not found at {path}")

# Initialize Stripe
STRIPE_SECRET_KEY = load_stripe_key(STRIPE_SECRET_KEY_PATH)
STRIPE_PUBLISHABLE_KEY = load_stripe_key(STRIPE_PUBLISHABLE_KEY_PATH)
stripe.api_key = STRIPE_SECRET_KEY

# URLs for redirects
APP_URL = os.getenv("A2APEX_APP_URL", "https://app.a2apex.io")


# ============================================================================
# DATABASE MIGRATIONS
# ============================================================================

def migrate_users_table():
    """Add Stripe-related columns to users table if they don't exist."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get existing columns
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    # Add missing columns
    new_columns = [
        ("stripe_customer_id", "TEXT"),
        ("stripe_subscription_id", "TEXT"),
        ("plan_expires_at", "TEXT"),
    ]
    
    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            print(f"Added column {col_name} to users table")
    
    conn.commit()
    conn.close()


# Run migration on module load
migrate_users_table()


# ============================================================================
# STRIPE PRODUCTS SETUP
# ============================================================================

def load_stripe_config() -> dict:
    """Load Stripe product/price IDs from config file."""
    if STRIPE_CONFIG_PATH.exists():
        return json.loads(STRIPE_CONFIG_PATH.read_text())
    return {}


def save_stripe_config(config: dict):
    """Save Stripe product/price IDs to config file."""
    STRIPE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    STRIPE_CONFIG_PATH.write_text(json.dumps(config, indent=2))


def ensure_stripe_products() -> dict:
    """
    Ensure Stripe products and prices exist. Create if they don't.
    Returns dict with price_ids for pro and enterprise.
    """
    config = load_stripe_config()
    
    # Check if we already have valid price IDs
    if config.get("pro_price_id") and config.get("enterprise_price_id"):
        # Verify they still exist in Stripe
        try:
            stripe.Price.retrieve(config["pro_price_id"])
            stripe.Price.retrieve(config["enterprise_price_id"])
            return config
        except stripe.error.InvalidRequestError:
            # Price doesn't exist, recreate
            pass
    
    # Create or retrieve Pro product
    products = stripe.Product.list(limit=100)
    pro_product = None
    enterprise_product = None
    
    for product in products.auto_paging_iter():
        if product.name == "A2Apex Pro":
            pro_product = product
        elif product.name == "A2Apex Enterprise":
            enterprise_product = product
    
    # Create Pro product if it doesn't exist
    if not pro_product:
        pro_product = stripe.Product.create(
            name="A2Apex Pro",
            description="Unlimited agent tests, 1-year badges, PRO verified indicator, API access (100 req/min), email support",
        )
    
    # Create Enterprise product if it doesn't exist
    if not enterprise_product:
        enterprise_product = stripe.Product.create(
            name="A2Apex Enterprise",
            description="Everything in Pro + permanent badges, custom branding, unlimited API, CI/CD integration, priority support",
        )
    
    # Create or find prices
    pro_price_id = None
    enterprise_price_id = None
    
    prices = stripe.Price.list(limit=100)
    for price in prices.auto_paging_iter():
        if price.product == pro_product.id and price.unit_amount == 2900 and price.recurring:
            pro_price_id = price.id
        elif price.product == enterprise_product.id and price.unit_amount == 49900 and price.recurring:
            enterprise_price_id = price.id
    
    # Create Pro price if needed
    if not pro_price_id:
        pro_price = stripe.Price.create(
            product=pro_product.id,
            unit_amount=2900,  # $29.00 in cents
            currency="usd",
            recurring={"interval": "month"},
        )
        pro_price_id = pro_price.id
    
    # Create Enterprise price if needed
    if not enterprise_price_id:
        enterprise_price = stripe.Price.create(
            product=enterprise_product.id,
            unit_amount=49900,  # $499.00 in cents
            currency="usd",
            recurring={"interval": "month"},
        )
        enterprise_price_id = enterprise_price.id
    
    # Save config
    config = {
        "pro_product_id": pro_product.id,
        "pro_price_id": pro_price_id,
        "enterprise_product_id": enterprise_product.id,
        "enterprise_price_id": enterprise_price_id,
    }
    save_stripe_config(config)
    
    print(f"Stripe products configured: Pro={pro_price_id}, Enterprise={enterprise_price_id}")
    return config


# Lazily initialize Stripe products (will be set on first use)
STRIPE_CONFIG = None

def get_stripe_config() -> dict:
    """Get Stripe config, initializing if needed."""
    global STRIPE_CONFIG
    if STRIPE_CONFIG is None:
        STRIPE_CONFIG = ensure_stripe_products()
    return STRIPE_CONFIG


# ============================================================================
# MODELS
# ============================================================================

class CreateCheckoutSessionRequest(BaseModel):
    """Request to create a Stripe checkout session."""
    plan: str = Field(..., description="Plan to subscribe to: 'pro' or 'enterprise'")


class SubscriptionResponse(BaseModel):
    """Response with subscription status."""
    plan: str
    status: Optional[str] = None
    current_period_end: Optional[str] = None
    stripe_customer_id: Optional[str] = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_or_create_stripe_customer(user: dict) -> str:
    """Get existing Stripe customer ID or create a new customer."""
    if user.get("stripe_customer_id"):
        return user["stripe_customer_id"]
    
    # Create new Stripe customer
    customer = stripe.Customer.create(
        email=user["email"],
        name=user["name"],
        metadata={"a2apex_user_id": str(user["id"])}
    )
    
    # Save to database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET stripe_customer_id = ? WHERE id = ?",
        (customer.id, user["id"])
    )
    conn.commit()
    conn.close()
    
    return customer.id


def update_user_subscription(
    user_id: int = None,
    stripe_customer_id: str = None,
    plan: str = "free",
    subscription_id: str = None,
    expires_at: str = None
):
    """Update user's subscription info in database."""
    conn = get_db()
    cursor = conn.cursor()
    
    if user_id:
        cursor.execute("""
            UPDATE users 
            SET plan = ?, stripe_subscription_id = ?, plan_expires_at = ?, updated_at = ?
            WHERE id = ?
        """, (plan, subscription_id, expires_at, datetime.utcnow().isoformat() + "Z", user_id))
    elif stripe_customer_id:
        cursor.execute("""
            UPDATE users 
            SET plan = ?, stripe_subscription_id = ?, plan_expires_at = ?, updated_at = ?
            WHERE stripe_customer_id = ?
        """, (plan, subscription_id, expires_at, datetime.utcnow().isoformat() + "Z", stripe_customer_id))
    
    conn.commit()
    conn.close()


def get_user_by_stripe_customer(customer_id: str) -> Optional[dict]:
    """Get user by Stripe customer ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE stripe_customer_id = ?", (customer_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(prefix="/api", tags=["Payments"])


@router.get("/stripe-config")
async def get_stripe_config_endpoint():
    """Get the Stripe publishable key for client-side use."""
    return {"publishable_key": STRIPE_PUBLISHABLE_KEY}


@router.post("/create-checkout-session")
async def create_checkout_session(
    request: CreateCheckoutSessionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a Stripe Checkout session for subscribing to Pro or Enterprise.
    
    Returns the checkout URL to redirect the user to.
    """
    plan = request.plan.lower()
    
    if plan not in ("pro", "enterprise"):
        raise HTTPException(status_code=400, detail="Invalid plan. Must be 'pro' or 'enterprise'")
    
    # Get or create Stripe customer
    customer_id = get_or_create_stripe_customer(current_user)
    
    # Get the price ID
    config = get_stripe_config()
    price_id = config["pro_price_id"] if plan == "pro" else config["enterprise_price_id"]
    
    try:
        # Create checkout session
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1,
            }],
            mode="subscription",
            success_url=f"{APP_URL}/?success=true&plan={plan}",
            cancel_url=f"{APP_URL}/?canceled=true",
            metadata={
                "a2apex_user_id": str(current_user["id"]),
                "plan": plan,
            },
            subscription_data={
                "metadata": {
                    "a2apex_user_id": str(current_user["id"]),
                    "plan": plan,
                }
            }
        )
        
        return {"checkout_url": session.url}
    
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/create-portal-session")
async def create_portal_session(current_user: dict = Depends(get_current_user)):
    """
    Create a Stripe Customer Portal session for managing subscription.
    
    Allows users to cancel, upgrade, update payment method, etc.
    """
    if not current_user.get("stripe_customer_id"):
        raise HTTPException(status_code=400, detail="No subscription found")
    
    try:
        session = stripe.billing_portal.Session.create(
            customer=current_user["stripe_customer_id"],
            return_url=f"{APP_URL}/?tab=pricing",
        )
        
        return {"portal_url": session.url}
    
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/subscription")
async def get_subscription(current_user: dict = Depends(get_current_user)):
    """
    Get the current user's subscription status.
    """
    response = SubscriptionResponse(
        plan=current_user.get("plan", "free"),
        stripe_customer_id=current_user.get("stripe_customer_id"),
    )
    
    # If user has a subscription, get details from Stripe
    if current_user.get("stripe_subscription_id"):
        try:
            subscription = stripe.Subscription.retrieve(current_user["stripe_subscription_id"])
            response.status = subscription.status
            response.current_period_end = datetime.fromtimestamp(
                subscription.current_period_end
            ).isoformat() + "Z"
        except stripe.error.InvalidRequestError:
            # Subscription no longer exists
            pass
    
    return response


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events.
    
    Processes subscription lifecycle events to keep user plans in sync.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    # For now, we'll process without signature verification
    # In production, you should set up a webhook secret and verify
    try:
        event = stripe.Event.construct_from(
            json.loads(payload),
            stripe.api_key
        )
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    event_type = event.type
    data = event.data.object
    
    print(f"Stripe webhook received: {event_type}")
    
    # Handle checkout.session.completed
    if event_type == "checkout.session.completed":
        customer_id = data.customer
        subscription_id = data.subscription
        metadata = data.metadata or {}
        plan = metadata.get("plan", "pro")
        
        # Get subscription details
        subscription = stripe.Subscription.retrieve(subscription_id)
        expires_at = datetime.fromtimestamp(subscription.current_period_end).isoformat() + "Z"
        
        # Update user's plan
        user_id = metadata.get("a2apex_user_id")
        if user_id:
            update_user_subscription(
                user_id=int(user_id),
                plan=plan,
                subscription_id=subscription_id,
                expires_at=expires_at
            )
            print(f"User {user_id} upgraded to {plan}")
        else:
            # Fallback to customer ID lookup
            update_user_subscription(
                stripe_customer_id=customer_id,
                plan=plan,
                subscription_id=subscription_id,
                expires_at=expires_at
            )
            print(f"Customer {customer_id} upgraded to {plan}")
    
    # Handle subscription updated (renewal, plan change)
    elif event_type == "customer.subscription.updated":
        customer_id = data.customer
        subscription_id = data.id
        status = data.status
        
        if status == "active":
            # Get plan from metadata or infer from price
            metadata = data.metadata or {}
            plan = metadata.get("plan")
            
            if not plan:
                # Infer from price
                price_id = data.items.data[0].price.id if data.items.data else None
                config = get_stripe_config()
                if price_id == config.get("enterprise_price_id"):
                    plan = "enterprise"
                else:
                    plan = "pro"
            
            expires_at = datetime.fromtimestamp(data.current_period_end).isoformat() + "Z"
            
            update_user_subscription(
                stripe_customer_id=customer_id,
                plan=plan,
                subscription_id=subscription_id,
                expires_at=expires_at
            )
            print(f"Subscription {subscription_id} renewed/updated")
        
        elif status in ("past_due", "unpaid"):
            # Keep plan but mark status
            print(f"Subscription {subscription_id} is {status}")
        
        elif status == "canceled":
            # Downgrade to free
            update_user_subscription(
                stripe_customer_id=customer_id,
                plan="free",
                subscription_id=None,
                expires_at=None
            )
            print(f"Subscription {subscription_id} canceled, downgraded to free")
    
    # Handle subscription deleted (canceled and ended)
    elif event_type == "customer.subscription.deleted":
        customer_id = data.customer
        
        update_user_subscription(
            stripe_customer_id=customer_id,
            plan="free",
            subscription_id=None,
            expires_at=None
        )
        print(f"Customer {customer_id} subscription deleted, downgraded to free")
    
    return {"status": "ok"}
