#!/usr/bin/env python3
"""
A2Apex Demo Screenshot Generator - v2
Better UI interactions for quality screenshots
"""

import time
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = "./docs/screenshots"
BASE_URL = "http://127.0.0.1:8091"
AGENT_URL = "http://127.0.0.1:8092"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            device_scale_factor=2  # Retina quality
        )
        page = context.new_page()
        
        # 1. Hero/Empty State
        print("📸 Capturing hero/empty state...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/01_hero.png")
        print("   ✅ 01_hero.png saved")
        
        # 2. Validation Results - Click Validate tab, enter URL, click Validate button
        print("📸 Capturing validation result...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        
        # Click Validate tab
        page.click('button:has-text("Validate"):not(:has-text("Run"))')
        time.sleep(0.5)
        
        # Enter agent URL 
        url_input = page.locator('input[type="url"], input[type="text"]').first
        url_input.fill(AGENT_URL)
        
        # Click the primary validate button (the cyan one)
        page.click('button.btn-primary:has-text("Validate"), button:has-text("Validate"):visible')
        page.wait_for_load_state("networkidle")
        time.sleep(3)  # Wait for validation to complete
        
        page.screenshot(path=f"{SCREENSHOTS_DIR}/02_validate.png")
        print("   ✅ 02_validate.png saved")
        
        # 3. Live Test Results
        print("📸 Capturing live test results...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        
        # Enter URL
        url_input = page.locator('input[type="url"], input[type="text"]').first
        url_input.fill(AGENT_URL)
        
        # Click Run Tests (should be on Live Test tab by default)
        page.click('button:has-text("Run Tests")')
        page.wait_for_load_state("networkidle")
        time.sleep(5)  # Wait for all tests to complete
        
        page.screenshot(path=f"{SCREENSHOTS_DIR}/03_live_test.png")
        print("   ✅ 03_live_test.png saved")
        
        # 4. Demo Mode (best one - use this)
        print("📸 Capturing demo mode...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        
        # Click Demo button
        page.click('button:has-text("Demo")')
        page.wait_for_load_state("networkidle")
        time.sleep(4)  # Wait for demo to complete
        
        page.screenshot(path=f"{SCREENSHOTS_DIR}/04_demo.png")
        print("   ✅ 04_demo.png saved")
        
        # 5. Debug Chat with actual conversation
        print("📸 Capturing debug chat with conversation...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        
        # First enter agent URL
        url_input = page.locator('input[type="url"], input[type="text"]').first
        url_input.fill(AGENT_URL)
        
        # Click Debug Chat tab
        page.click('button:has-text("Debug Chat")')
        time.sleep(0.5)
        
        # Find chat input and send message
        chat_input = page.locator('input[placeholder*="message"], input[placeholder*="Message"], textarea')
        if chat_input.count() > 0:
            chat_input.first.fill("What's the weather in Tokyo?")
            time.sleep(0.3)
            # Press Enter or click Send
            chat_input.first.press("Enter")
            time.sleep(3)  # Wait for response
        
        # Enable JSON view for the technical look
        json_toggle = page.locator('input[type="checkbox"], label:has-text("JSON"), button:has-text("JSON")')
        if json_toggle.count() > 0:
            json_toggle.first.click()
            time.sleep(0.5)
        
        page.screenshot(path=f"{SCREENSHOTS_DIR}/05_chat.png")
        print("   ✅ 05_chat.png saved")
        
        browser.close()
        print("\n🎉 All screenshots captured!")

if __name__ == "__main__":
    main()
