import asyncio
from codewords import CodeWords
import base64

async def run(inputs):
    url = inputs.get("url", "https://example.com")
    
    async with CodeWords() as cw:
        # CodeWords provides a pre-initialized 'page' object in its environment
        # but for a standalone script we can use the context
        browser = await cw.chromium.launch()
        page = await browser.new_page()
        await page.goto(url)
        screenshot = await page.screenshot()
        await browser.close()
        
        return {
            "screenshot": base64.b64encode(screenshot).decode('utf-8')
        }
