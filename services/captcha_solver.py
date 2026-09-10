import asyncio
import base64
import random
import re
import io
import aiohttp
from typing import Optional, Dict, Any
from PIL import Image, ImageDraw
from playwright.async_api import Page

class CapSolverService:
    API_URL = "https://api.capsolver.com"

    def __init__(self, api_key: str):
        self.api_key = api_key

    @staticmethod
    def create_concentric_composite(inner_b64: str, outer_b64: str) -> str:
        """Creates a clean concentric composite image for CapSolver rotate_2."""
        try:
            im_out = Image.open(io.BytesIO(base64.b64decode(outer_b64))).convert("RGBA")
            im_in = Image.open(io.BytesIO(base64.b64decode(inner_b64))).convert("RGBA")
            
            mask = Image.new("L", im_in.size, 0)
            d = ImageDraw.Draw(mask)
            d.ellipse((0, 0, im_in.size[0] - 1, im_in.size[1] - 1), fill=255)
            
            offset_x = (im_out.size[0] - im_in.size[0]) // 2
            offset_y = (im_out.size[1] - im_in.size[1]) // 2
            
            comp = im_out.copy()
            comp.paste(im_in, (offset_x, offset_y), mask)
            
            buf = io.BytesIO()
            comp.convert("RGB").save(buf, format="JPEG")
            return base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            print(f"[CapSolver] Composite creation note: {e}", flush=True)
            return inner_b64

    async def _solve_single_round(self, page: Page, round_num: int) -> bool:
        """Solves a single round of TikTok whirl or puzzle slider."""
        # 1. Bring captcha to the very front so it is not covered by modals
        await page.evaluate("""() => {
            const captchaModal = document.querySelector('.captcha-verify-container') || document.querySelector('#captcha-verify-container-main-page');
            if (captchaModal) {
                let el = captchaModal;
                while (el && el !== document.body) {
                    el.style.zIndex = '99999999';
                    el = el.parentElement;
                }
            }
        }""")

        # 2. Wait for images and slider thumb button
        imgs_ready = False
        for attempt in range(15):
            await page.wait_for_timeout(1000)
            imgs = await page.query_selector_all("#captcha-verify-container-main-page img, div.captcha-verify-container img")
            thumb = await page.query_selector("#captcha_slide_button")
            if len(imgs) >= 2 and thumb:
                s1 = await imgs[0].get_attribute("src") or ""
                s2 = await imgs[1].get_attribute("src") or ""
                if len(s1) > 100 and len(s2) > 100:
                    imgs_ready = True
                    print(f"[CapSolver] Round {round_num}: Images and slider ready (attempt {attempt+1})!", flush=True)
                    break

        if not imgs_ready:
            print(f"[CapSolver] Round {round_num}: Captcha images failed to load.", flush=True)
            return False

        imgs = await page.query_selector_all("#captcha-verify-container-main-page img, div.captcha-verify-container img")
        bg_src = await imgs[0].get_attribute("src") or ""
        piece_src = await imgs[1].get_attribute("src") or ""
        clean_bg = bg_src.split(",")[-1]
        clean_piece = piece_src.split(",")[-1]

        # 3. Detect whirl (concentric circle rotation) vs slider puzzle
        # 3. Detect whirl (concentric circle rotation) vs slider puzzle
        is_whirl = await page.evaluate("""() => {
            const piece = document.querySelectorAll('#captcha-verify-container-main-page img, div.captcha-verify-container img')[1];
            if (!piece) return true;
            return (piece.style.clipPath && piece.style.clipPath.includes('circle')) || 
                   (piece.style.transform && piece.style.transform.includes('rotate')) ||
                   (piece.getAttribute('style') && piece.getAttribute('style').includes('circle'));
        }""")

        # If whirl is detected, try refreshing up to 4 times to get an easy puzzle slider
        if is_whirl:
            for ref_idx in range(1, 5):
                print(f"[CapSolver] Whirl detected. Refreshing captcha ({ref_idx}/4) to get a puzzle slider...", flush=True)
                ref_btn = page.locator("#captcha_refresh_button").first
                if await ref_btn.count() > 0:
                    await ref_btn.click(force=True)
                else:
                    await page.evaluate("""() => {
                        const b = document.querySelector('#captcha_refresh_button');
                        if (b) b.click();
                    }""")
                await page.wait_for_timeout(3000)

                # Wait for new captcha images to mount
                for _ in range(10):
                    ready = await page.evaluate("""() => {
                        const imgs = document.querySelectorAll('#captcha-verify-container-main-page img, div.captcha-verify-container img');
                        const thumb = document.querySelector('#captcha_slide_button');
                        return imgs.length >= 2 && !!thumb && thumb.getBoundingClientRect().width > 0;
                    }""")
                    if ready:
                        break
                    await page.wait_for_timeout(500)

                is_whirl = await page.evaluate("""() => {
                    const piece = document.querySelectorAll('#captcha-verify-container-main-page img, div.captcha-verify-container img')[1];
                    if (!piece) return true; // not ready or still whirl
                    return (piece.style.clipPath && piece.style.clipPath.includes('circle')) || 
                           (piece.style.transform && piece.style.transform.includes('rotate')) ||
                           (piece.getAttribute('style') && piece.getAttribute('style').includes('circle'));
                }""")
                if not is_whirl:
                    print(f"[CapSolver] Success! Refresh #{ref_idx} converted captcha into a puzzle slider.", flush=True)
                    break

        # Re-fetch latest clean images
        imgs = await page.query_selector_all("#captcha-verify-container-main-page img, div.captcha-verify-container img")
        if len(imgs) >= 2:
            bg_src = await imgs[0].get_attribute("src") or ""
            piece_src = await imgs[1].get_attribute("src") or ""
            clean_bg = bg_src.split(",")[-1]
            clean_piece = piece_src.split(",")[-1]

        # Get track metrics with retry
        track_data = None
        for _ in range(6):
            track_data = await page.evaluate("""() => {
                const thumb = document.querySelector('#captcha_slide_button');
                const track = thumb ? (thumb.closest('.cap-bg-UISheetGrouped3') || thumb.parentElement.parentElement) : null;
                if (!thumb || !track) return null;
                const tb = thumb.getBoundingClientRect();
                const trb = track.getBoundingClientRect();
                if (tb.width === 0 || trb.width === 0) return null;
                return {
                    thumb: {x: tb.x, y: tb.y, width: tb.width, height: tb.height},
                    track: {x: trb.x, y: trb.y, width: trb.width, height: trb.height},
                    maxDrag: trb.width - tb.width
                };
            }""")
            if track_data:
                break
            await page.wait_for_timeout(500)

        if not track_data:
            print("[CapSolver] Could not calculate track geometry.", flush=True)
            return False

        start_x = track_data["thumb"]["x"] + track_data["thumb"]["width"] / 2
        start_y = track_data["thumb"]["y"] + track_data["thumb"]["height"] / 2
        max_drag = track_data["maxDrag"]

        async with aiohttp.ClientSession() as session:
            if is_whirl:
                print(f"[CapSolver] Round {round_num}: Whirl rotation detected. Creating concentric image...", flush=True)
                composite_b64 = self.create_concentric_composite(clean_piece, clean_bg)
                
                payload = {
                    "clientKey": self.api_key,
                    "task": {
                        "type": "VisionEngine",
                        "module": "rotate_2",
                        "image": composite_b64,
                        "websiteURL": "https://www.tiktok.com"
                    }
                }
                async with session.post(f"{self.API_URL}/createTask", json=payload, timeout=20) as resp:
                    data = await resp.json()
                    raw_angle = data.get("solution", {}).get("angle")
                    print(f"[CapSolver] rotate_2 result: raw angle={raw_angle}", flush=True)

                if raw_angle is None:
                    print("[CapSolver] Failed to get rotation angle.", flush=True)
                    return False

                # Map CapSolver angle to clockwise slider rotation (0..180 deg)
                effective_angle = (360 - raw_angle) if raw_angle > 180 else raw_angle
                effective_angle = min(180.0, max(0.0, float(effective_angle)))

                # Closed-loop drag matching DOM rotation
                print(f"[CapSolver] Dragging thumb to rotate piece to {effective_angle} deg...", flush=True)
                await page.mouse.move(start_x, start_y)
                await page.mouse.down()

                cur_x = start_x
                step_px = 2.5
                for s in range(150):
                    cur_x += step_px
                    if cur_x - start_x > max_drag:
                        break
                    cur_y = start_y + random.uniform(-0.5, 0.5)
                    await page.mouse.move(cur_x, cur_y, steps=1)
                    await asyncio.sleep(0.015)

                    rot_str = await page.evaluate("""() => {
                        const piece = document.querySelectorAll('#captcha-verify-container-main-page img, div.captcha-verify-container img')[1];
                        return piece ? piece.style.transform : '';
                    }""")
                    m = re.search(r'rotate\(([-0-9.]+)deg\)', rot_str)
                    if m:
                        cur_deg = float(m.group(1))
                        if cur_deg >= effective_angle - 1.0:
                            break

                await asyncio.sleep(0.3)
                await page.mouse.up()
                print(f"[CapSolver] Round {round_num}: Released at target rotation!", flush=True)
            else:
                # Puzzle slider
                print(f"[CapSolver] Round {round_num}: Puzzle slider detected. Calling slider_1...", flush=True)
                payload = {
                    "clientKey": self.api_key,
                    "task": {
                        "type": "VisionEngine",
                        "module": "slider_1",
                        "image": clean_piece,
                        "imageBackground": clean_bg,
                        "websiteURL": "https://www.tiktok.com"
                    }
                }
                async with session.post(f"{self.API_URL}/createTask", json=payload, timeout=20) as resp:
                    data = await resp.json()
                    raw_dist = data.get("solution", {}).get("distance")
                    print(f"[CapSolver] slider_1 result: dist={raw_dist}", flush=True)

                if raw_dist is None:
                    return False

                scale = await page.evaluate("""() => {
                    const bg = document.querySelectorAll('#captcha-verify-container-main-page img, div.captcha-verify-container img')[0];
                    return bg ? (bg.clientWidth / bg.naturalWidth) : 1.0;
                }""")
                scaled_dist = raw_dist * scale
                target_x = start_x + scaled_dist

                # Humanized smooth drag with slight overshoot
                await page.mouse.move(start_x, start_y)
                await asyncio.sleep(random.uniform(0.08, 0.15))
                await page.mouse.down()
                await asyncio.sleep(random.uniform(0.08, 0.15))

                steps = random.randint(30, 40)
                overshoot = random.uniform(1.0, 2.5)
                peak_x = target_x + overshoot

                for i in range(1, steps + 1):
                    t = i / steps
                    progress = 1 - (1 - t) ** 2
                    cur_x = start_x + (peak_x - start_x) * progress
                    cur_y = start_y + random.uniform(-0.8, 0.8)
                    await page.mouse.move(cur_x, cur_y, steps=1)
                    await asyncio.sleep(random.uniform(0.012, 0.018))

                await asyncio.sleep(random.uniform(0.05, 0.09))
                for c in range(1, 6):
                    cx = peak_x + (target_x - peak_x) * (c / 5)
                    cy = start_y + random.uniform(-0.3, 0.3)
                    await page.mouse.move(cx, cy, steps=1)
                    await asyncio.sleep(0.015)

                await asyncio.sleep(random.uniform(0.2, 0.3))
                await page.mouse.up()
                print(f"[CapSolver] Round {round_num}: Released slider with human motion!", flush=True)

        await page.wait_for_timeout(4000)
        return True

    async def solve_tiktok_puzzle(self, page: Page) -> bool:
        """Detects and solves TikTok slider / puzzle / whirl rotate captcha across multiple rounds."""
        if not self.api_key or self.api_key.startswith("your_"):
            print("[CapSolver] API key is missing or not set!")
            return False

        try:
            print("[CapSolver] Checking for TikTok captcha on page (waiting up to 15s)...", flush=True)
            captcha_container = False
            for _ in range(15):
                await page.wait_for_timeout(1000)
                is_vis = await page.evaluate("""() => {
                    const c = document.querySelector("#captcha-verify-container-main-page, div.captcha-verify-container, [class*='captcha-verify']");
                    return c !== null && c.getBoundingClientRect().width > 0;
                }""")
                if is_vis:
                    captcha_container = True
                    break

            if not captcha_container:
                print("[CapSolver] No captcha detected on page.", flush=True)
                return True

            print("[CapSolver] Captcha detected! Starting multi-round solver...", flush=True)
            for round_num in range(1, 4):
                is_open = await page.evaluate("""() => {
                    const c = document.querySelector("#captcha-verify-container-main-page, div.captcha-verify-container, [class*='captcha-verify']");
                    return c !== null && c.getBoundingClientRect().width > 0;
                }""")
                if not is_open:
                    print(f"[CapSolver] Captcha container closed before round {round_num}! Challenge solved.", flush=True)
                    return True

                success = await self._solve_single_round(page, round_num)
                if not success:
                    print(f"[CapSolver] Round {round_num} failed.", flush=True)
                    return False

            # Final check that captcha closed
            for _ in range(12):
                is_open = await page.evaluate("""() => {
                    const c = document.querySelector("#captcha-verify-container-main-page, div.captcha-verify-container, [class*='captcha-verify']");
                    return c !== null && c.getBoundingClientRect().width > 0;
                }""")
                if not is_open:
                    print("[CapSolver] All captcha challenges resolved and closed successfully!", flush=True)
                    return True
                await page.wait_for_timeout(1000)

            return False
        except Exception as e:
            print(f"[CapSolver Error]: {e}", flush=True)
            return False
