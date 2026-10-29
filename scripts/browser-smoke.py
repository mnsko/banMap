#!/usr/bin/env python3
"""Run after Compose startup; optional Playwright/Chromium dependency."""
import json
import os
from pathlib import Path
import shutil
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    executable=os.getenv('CHROMIUM_PATH') or shutil.which('chromium')
    browser=p.chromium.launch(executable_path=executable,headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    response=page.goto('http://127.0.0.1:8080/',wait_until='networkidle',timeout=30000)
    expect(page.locator('#attempts')).not_to_have_text('—')
    assert response.status==200
    assert not errors,errors
    page.get_by_role('button',name='7 days',exact=True).click()
    page.wait_for_timeout(500)
    assert page.locator('button[data-range="7d"]').get_attribute('aria-pressed')=='true'
    page.get_by_role('button',name='About the project').click()
    assert page.locator('#about').is_visible()
    page.get_by_role('button',name='Close',exact=True).click()
    page.select_option('#detail-kind','commands')
    page.wait_for_timeout(500)
    assert not page.locator('#error').is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    Path('artifacts').mkdir(exist_ok=True)
    page.screenshot(path='artifacts/desktop.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_timeout(300)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Mobile horizontal overflow'
    page.screenshot(path='artifacts/mobile.png',full_page=True)
    # Isolated hostile-data case: mock the public payload, without contaminating the DB.
    hostile='<img src=x onerror="window.__xss=1">'
    page.route('**/api/top/commands*',lambda route:route.fulfill(json=[{'value':hostile+' hxxp://evil[.]example','count':3,'distinct_ips':3}]))
    page.select_option('#detail-kind','hassh'); page.wait_for_timeout(300)
    page.select_option('#detail-kind','commands')
    expect(page.locator('#top-details')).to_contain_text('onerror')
    assert page.locator('#top-details img').count()==0
    assert page.locator('#top-details a').count()==0
    assert page.evaluate('window.__xss') is None
    assert not errors,errors
    print(json.dumps({'desktop':'passed','mobile':'passed','hostile_text':'passed','javascript_errors':errors}))
    browser.close()
