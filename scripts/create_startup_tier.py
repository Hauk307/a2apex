#!/usr/bin/env python3
"""
Create A2Apex Startup tier product and price in Stripe.
Updates stripe_config.json with the new IDs.
"""

import json
from pathlib import Path
import stripe

# Load Stripe secret key
stripe_key_path = Path.home() / ".openclaw" / ".stripe_secret_key"
stripe.api_key = stripe_key_path.read_text().strip()

# Config path
config_path = Path(__file__).parent.parent / "data" / "stripe_config.json"

def main():
    print("Creating A2Apex Startup product and price...")
    
    # Load existing config
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    print(f"Current config: {config}")
    
    # Check if Startup product already exists
    products = stripe.Product.list(limit=100)
    startup_product = None
    for product in products.auto_paging_iter():
        if product.name == "A2Apex Startup":
            startup_product = product
            print(f"Found existing Startup product: {product.id}")
            break
    
    # Create Startup product if it doesn't exist
    if not startup_product:
        startup_product = stripe.Product.create(
            name="A2Apex Startup",
            description="500 tests/mo, 20 certifications, 15 agent profiles, full API/SDK access, priority support",
        )
        print(f"Created Startup product: {startup_product.id}")
    
    # Check if $99/mo price exists for this product
    startup_price_id = None
    prices = stripe.Price.list(product=startup_product.id, limit=100)
    for price in prices.auto_paging_iter():
        if price.unit_amount == 9900 and price.recurring and price.recurring.interval == "month":
            startup_price_id = price.id
            print(f"Found existing Startup price: {price.id}")
            break
    
    # Create price if needed
    if not startup_price_id:
        startup_price = stripe.Price.create(
            product=startup_product.id,
            unit_amount=9900,  # $99.00 in cents
            currency="usd",
            recurring={"interval": "month"},
        )
        startup_price_id = startup_price.id
        print(f"Created Startup price: {startup_price_id}")
    
    # Update config
    config["startup_product_id"] = startup_product.id
    config["startup_price_id"] = startup_price_id
    
    config_path.write_text(json.dumps(config, indent=2))
    print(f"Updated config: {config}")
    print("Done!")

if __name__ == "__main__":
    main()
