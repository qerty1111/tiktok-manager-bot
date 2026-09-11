import json
import asyncio
import os
import re
import random
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from config import CAPSOLVER_API_KEY
from services.captcha_solver import CapSolverService

class TikTokService:
    @staticmethod
    def parse_cookies(cookie_input: str) -> List[Dict[str, Any]]:
        """Parses cookies from JSON array or raw string."""
        cookie_input = cookie_input.strip()
        
        # Try JSON first
        if cookie_input.startswith("[") and cookie_input.endswith("]"):
            try:
                cookies = json.loads(cookie_input)
                formatted = []
                for c in cookies:
                    item = {
                        "name": c.get("name"),
                        "value": c.get("value"),
                        "domain": c.get("domain", ".tiktok.com"),
                        "path": c.get("path", "/"),
                    }
                    if "secure" in c:
                        item["secure"] = bool(c["secure"])
                    if "httpOnly" in c:
                        item["httpOnly"] = bool(c["httpOnly"])
                    if "sameSite" in c and c["sameSite"] in ["Strict", "Lax", "None"]:
                        item["sameSite"] = c["sameSite"]
                    formatted.append(item)
                return formatted
            except Exception:
                pass

        # If it's a raw cookie header string (name=val; name2=val2)
        formatted = []
        parts = cookie_input.split(";")
        for part in parts:
            if "=" in part:
                name, val = part.strip().split("=", 1)
                formatted.append({
                    "name": name.strip(),
                    "value": val.strip(),
                    "domain": ".tiktok.com",
                    "path": "/"
                })
        if not formatted:
            raise ValueError("Не удалось распознать cookies. Нужен JSON-массив или строка name=value;...")
        return formatted

    @staticmethod
    def parse_proxy(proxy_str: str) -> Optional[Dict[str, str]]:
        """Parses proxy strings into Playwright proxy dict with sticky session support."""
        if not proxy_str or not proxy_str.strip():
            return None
            
        proxy_str = proxy_str.strip()
        
        if "@" in proxy_str:
            return {"server": proxy_str if "://" in proxy_str else f"http://{proxy_str}"}
            
        parts = proxy_str.split(":")
        if len(parts) == 4:
            host, port, user, pwd = parts
            if "__cr." in user and "sessid" not in user:
                sess = random.randint(100000, 999999)
                user = f"{user};sessid.{sess};sessttl.15"
            return {
                "server": f"http://{host}:{port}",
                "username": user,
                "password": pwd
            }
        elif len(parts) == 2:
            host, port = parts
            return {"server": f"http://{host}:{port}"}
            
        return {"server": proxy_str if "://" in proxy_str else f"http://{proxy_str}"}

    @classmethod
    async def verify_session_and_get_profile(cls, cookies_json: str, proxy_str: str = "") -> Tuple[bool, Dict[str, Any]]:
        """Verifies if TikTok cookies are active and fetches user profile stats."""
        cookies = cls.parse_cookies(cookies_json)
        proxy = cls.parse_proxy(proxy_str)
        
        stats = {
            "username": "",
            "avatar_url": "",
            "followers": 0,
            "views": 0,
            "likes": 0,
            "video_count": 0,
            "is_active": 0
        }
        
        async with async_playwright() as p:
            launch_args = ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]
            browser = await p.chromium.launch(headless=True, args=launch_args)
            
            context_kwargs = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "viewport": {"width": 1440, "height": 900},
            }
            if proxy:
                context_kwargs["proxy"] = proxy
                
            context = await browser.new_context(**context_kwargs)
            try:
                await context.add_cookies(cookies)
                page = await context.new_page()
                
                await page.goto("https://www.tiktok.com/tiktokstudio/upload", timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)
                
                current_url = page.url
                if "login" in current_url:
                    await browser.close()
                    return False, stats
                
                content = await page.content()
                username_match = re.search(r'"uniqueId":"([^"]+)"', content)
                if username_match:
                    stats["username"] = username_match.group(1)
                
                avatar_match = re.search(r'"avatarLarger":"([^"]+)"', content) or re.search(r'"avatarThumb":"([^"]+)"', content)
                if avatar_match:
                    stats["avatar_url"] = avatar_match.group(1).replace("\\u002F", "/").replace("\\u0026", "&")
                    
                stats["is_active"] = 1
                await browser.close()
                return True, stats
            except Exception as e:
                print(f"[Verify Session Error]: {e}")
                await browser.close()
                return False, stats

    @classmethod
    async def upload_video(
        cls,
        cookies_json: str,
        video_path: str,
        description: str = "",
        hashtags: str = "",
        proxy_str: str = ""
    ) -> Tuple[bool, str]:
        """Uploads a video to TikTok using TikTok Studio with onboarding/modal bypass."""
        cookies = cls.parse_cookies(cookies_json)
        proxy = cls.parse_proxy(proxy_str)
        full_caption = f"{description.strip()} {hashtags.strip()}".strip()
        
        async with async_playwright() as p:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage"
            ]
            browser = await p.chromium.launch(channel="chrome", headless=True, args=launch_args)
            
            context_kwargs = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "viewport": {"width": 1440, "height": 900},
            }
            if proxy:
                context_kwargs["proxy"] = proxy
                
            context = await browser.new_context(**context_kwargs)
            try:
                await context.add_cookies(cookies)
                page = await context.new_page()
                await Stealth().apply_stealth_async(page)
                
                print("[TikTok] Navigating to TikTok Studio Upload...")
                await page.goto("https://www.tiktok.com/tiktokstudio/upload", timeout=60000, wait_until="load")
                
                if "login" in page.url:
                    await browser.close()
                    return False, "Сессия TikTok устарела (перенаправлено на страницу входа)."
                
                btn = page.get_by_role("button", name="Select video")
                if await btn.count() == 0:
                    btn = page.locator("button:has-text('Select video')")
                    
                print(f"[TikTok] Attaching video file: {video_path}")
                async with page.expect_file_chooser(timeout=30000) as fc_info:
                    await btn.first.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(video_path)
                    
                print("[TikTok] Waiting for video upload processing and edit form...")
                try:
                    await page.wait_for_selector('div[contenteditable="true"], button[data-e2e="post_video_button"]', timeout=60000)
                except Exception as e:
                    print(f"[TikTok] Form wait note: {e}")
                await page.wait_for_timeout(3000)
                
                # Auto-dismiss popups/onboarding modals (Got it, Cancel, Turn on, Skip)
                for _ in range(5):
                    for btn_text in ["Got it", "Cancel", "Turn on", "Not now", "Skip"]:
                        b = page.locator(f"button:has-text('{btn_text}')")
                        if await b.count() > 0:
                            try:
                                if await b.first.is_visible():
                                    print(f"[TikTok] Closing popup: {btn_text}")
                                    await b.first.click()
                                    await page.wait_for_timeout(1000)
                            except Exception:
                                pass
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(500)
                    
                # Fill description & hashtags
                if full_caption:
                    caption_box = page.locator('div[contenteditable="true"]')
                    if await caption_box.count() > 0:
                        print(f"[TikTok] Setting caption: {full_caption}")
                        await caption_box.first.click()
                        await page.keyboard.press("Control+A")
                        await page.keyboard.press("Backspace")
                        await page.keyboard.type(full_caption, delay=20)
                        await page.wait_for_timeout(2000)
                        
                # Scroll to bottom
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)
                
                # Click Post Button (strictly data-e2e="post_video_button")
                post_btn = page.locator("button[data-e2e='post_video_button']")
                await post_btn.wait_for(state="visible", timeout=30000)
                print("[TikTok] Clicking Post button...")
                await post_btn.click(force=True)
                await page.wait_for_timeout(3000)

                # Solve captcha if triggered on video publish. A failed solve is a hard failure.
                if CAPSOLVER_API_KEY:
                    solver = CapSolverService(CAPSOLVER_API_KEY)
                    solved = await solver.solve_tiktok_puzzle(page)
                    if not solved:
                        await browser.close()
                        return False, "Капча TikTok не пройдена, публикация остановлена."
                
                # Wait for redirect or an explicit success signal.
                print("[TikTok] Waiting for publish confirmation...")
                await page.wait_for_timeout(15000)
                page_text = (await page.locator("body").inner_text()).lower()
                url_ok = "upload" not in page.url.lower()
                success_text = any(marker in page_text for marker in ("video posted", "your video is live", "published", "опубликовано"))
                post_button_visible = await page.locator("button[data-e2e='post_video_button']").count() > 0 and await page.locator("button[data-e2e='post_video_button']").first.is_visible()
                await browser.close()
                if not url_ok and (post_button_visible or not success_text):
                    return False, "TikTok не подтвердил публикацию видео."
                return True, "Видео успешно опубликовано в TikTok!"
            except Exception as e:
                print(f"[TikTok Upload Error]: {e}")
                await browser.close()
                return False, f"Ошибка при загрузке: {str(e)}"


    @classmethod
    async def update_profile_avatar(cls, cookies_json: str, username: str, photo_path: str, proxy_str: str = "") -> Tuple[bool, str]:
        """Upload an avatar once and verify that TikTok persisted a different asset."""
        cookies = cls.parse_cookies(cookies_json)
        proxy = cls.parse_proxy(proxy_str)
        launch_args = ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-infobars", "--disable-dev-shm-usage"]

        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome", headless=False, args=launch_args)
            context = await browser.new_context(proxy=proxy, locale="en-US", viewport={"width": 1440, "height": 900}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
            await context.add_init_script("""Object.defineProperty(navigator, 'webdriver', { get: () => undefined }); window.chrome = { runtime: {} };""")
            cookies.append({"name": "tt_lang", "value": "en", "domain": ".tiktok.com", "path": "/"})
            await context.add_cookies(cookies)
            page = await context.new_page()
            await Stealth().apply_stealth_async(page)
            api_events: List[Dict[str, Any]] = []

            async def on_resp(resp):
                if resp.request.method != "POST":
                    return
                endpoint = ("update/profile" if any(token in resp.url for token in ("update/profile", "user/profile/update", "passport/web/account/info/update")) else ("upload/image" if "upload/image" in resp.url else None))
                if endpoint is None:
                    return
                try:
                    data = await resp.json()
                except Exception:
                    data = {}
                raw_code = data.get("status_code")
                try:
                    code = int(raw_code) if raw_code is not None else None
                except (TypeError, ValueError):
                    code = None
                api_events.append({"endpoint": endpoint, "status_code": code, "status_msg": str(data.get("status_msg") or ""), "http_status": resp.status})
                print(f"[TikTok API] {endpoint}: HTTP {resp.status}, status_code={code}", flush=True)

            page.on("response", on_resp)

            async def captcha_visible() -> bool:
                return bool(await page.evaluate("""() => ['#captcha-verify-container-main-page','div.captcha-verify-container','[class*="captcha-verify"]'].some(s => { const n=document.querySelector(s); if (!n) return false; const r=n.getBoundingClientRect(); return r.width > 0 && r.height > 0; })"""))

            def latest_event(start: int = 0) -> Optional[Dict[str, Any]]:
                recent = api_events[start:]
                updates = [e for e in recent if e["endpoint"] == "update/profile"]
                if updates:
                    return updates[-1]
                uploads = [e for e in recent if e["endpoint"] == "upload/image"]
                return uploads[-1] if uploads else None

            async def wait_for_api(start: int, timeout_ms: int = 6000) -> Optional[Dict[str, Any]]:
                deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
                while asyncio.get_running_loop().time() < deadline:
                    event = latest_event(start)
                    if event is not None:
                        return event
                    await page.wait_for_timeout(250)
                return latest_event(start)

            async def api_error(start: int, action: str) -> Optional[Tuple[bool, str]]:
                event = latest_event(start)
                if event is None:
                    return None
                code = event["status_code"]
                if code == 3002284:
                    return False, "⚠️ TikTok временно ограничил частое редактирование: 'Slow down, you are editing too fast'. Нужно подождать 1-2 часа для сброса анти-спам лимита."
                if code is None:
                    return False, f"TikTok не вернул status_code для операции {action}. Изменение не подтверждено."
                if code != 0 or event["http_status"] >= 400:
                    return False, f"TikTok отклонил изменение аватарки: {event['status_msg'] or code or event['http_status']}"
                return None

            async def avatar_url() -> str:
                image = page.locator("div[data-e2e='user-avatar'] img, span[data-e2e='user-avatar'] img, img[class*='ImgAvatar'], div[class*='DivAvatarContainer'] img").first
                for _ in range(6):
                    if await image.count() > 0:
                        src = (await image.get_attribute("src") or "").strip()
                        if src:
                            return src
                    await page.wait_for_timeout(500)
                return ""

            try:
                profile_url = f"https://www.tiktok.com/@{username}"
                for attempt in range(2):
                    try:
                        await page.goto(profile_url, wait_until="domcontentloaded", timeout=35000)
                        break
                    except Exception as exc:
                        print(f"[TikTok Avatar] Page goto attempt {attempt+1} note: {exc}", flush=True)
                        if attempt == 1:
                            pass
                        await asyncio.sleep(2)
                await page.wait_for_timeout(3000)

                for _ in range(3):
                    dismiss = page.locator("button:has-text('Got it'), button:has-text('Not now'), button[aria-label='Close'], button:has-text('Понятно')").first
                    if await dismiss.count() > 0 and await dismiss.is_visible():
                        await dismiss.click(force=True)
                        await page.wait_for_timeout(500)
                await page.keyboard.press("Escape")

                # Robust polling for Edit profile button across client-side SPA routing & hydration
                edit_btn = None
                for _ in range(45):
                    await page.wait_for_timeout(1000)
                    try:
                        candidates = page.locator("button[data-e2e='edit-profile-entrance'], button:has-text('Edit profile'), button:has-text('Изменить профиль'), button[data-e2e*='edit']")
                        if await candidates.count() > 0 and await candidates.first.is_visible():
                            edit_btn = candidates.first
                            break
                    except Exception:
                        pass
                if not edit_btn:
                    await browser.close()
                    return False, "Кнопка редактирования профиля не появилась (страница профиля не загрузилась)."
                old_avatar_src = await avatar_url()

                await edit_btn.click(force=True)
                await page.wait_for_timeout(2000)
                file_input = page.locator("input[type='file']").first
                await file_input.wait_for(state="attached", timeout=10000)
                await file_input.set_input_files(photo_path)
                await page.wait_for_timeout(3000)

                apply_btn = page.locator("button:has-text('Apply'), button:has-text('Confirm'), button:has-text('Применить')").first
                await apply_btn.wait_for(state="visible", timeout=15000)
                abox = await apply_btn.bounding_box()
                if abox:
                    await page.mouse.click(abox["x"] + abox["width"]/2, abox["y"] + abox["height"]/2)
                else:
                    await apply_btn.click(force=True)
                print("[TikTok] Clicked Apply on crop dialog.", flush=True)

                # Check if SecSDK captcha appeared on Apply
                solver = CapSolverService(CAPSOLVER_API_KEY) if CAPSOLVER_API_KEY else None
                for _ in range(10):
                    await page.wait_for_timeout(500)
                    if await captcha_visible():
                        print("[TikTok] Captcha detected on crop Apply! Solving...", flush=True)
                        if solver:
                            await solver.solve_tiktok_puzzle(page)
                        await page.wait_for_timeout(2500)
                        break

                if await captcha_visible():
                    await browser.close()
                    return False, "Капча TikTok осталась открыта, не удалось подтвердить загрузку фото. Попробуйте еще раз."

                # If crop dialog is still open after captcha, re-click Apply
                await page.wait_for_timeout(1000)
                apply_btn = page.locator("button:has-text('Apply'), button:has-text('Confirm'), button:has-text('Применить')").first
                if await apply_btn.count() > 0 and await apply_btn.is_visible():
                    print("[TikTok] Re-clicking Apply after captcha resolution...", flush=True)
                    abox = await apply_btn.bounding_box()
                    if abox:
                        await page.mouse.click(abox["x"] + abox["width"]/2, abox["y"] + abox["height"]/2)
                    else:
                        await apply_btn.click(force=True)
                    await page.wait_for_timeout(3000)

                save_btn = page.locator("button[data-e2e='edit-profile-save'], button:has-text('Save'), button:has-text('Сохранить')").first
                await save_btn.wait_for(state="visible", timeout=15000)
                # Wait for upload/image to complete and save_btn to become enabled
                for _ in range(50):
                    crop_visible = await page.locator("button:has-text('Apply')").count() > 0 and await page.locator("button:has-text('Apply')").first.is_visible()
                    if not crop_visible and not await save_btn.is_disabled():
                        break
                    await page.wait_for_timeout(500)

                if await save_btn.is_disabled():
                    await browser.close()
                    return False, "Кнопка сохранения аватарки осталась недоступна (фото не загрузилось). Попробуйте фото формата JPG или меньшего размера."

                save_start = len(api_events)
                sbox = await save_btn.bounding_box()
                if sbox:
                    await page.mouse.click(sbox["x"] + sbox["width"]/2, sbox["y"] + sbox["height"]/2)
                else:
                    await save_btn.click(force=True)

                # Wait up to 12s for either captcha or API response
                captcha_detected = False
                for _ in range(24):
                    if await captcha_visible():
                        captcha_detected = True
                        break
                    if latest_event(save_start) is not None:
                        break
                    await page.wait_for_timeout(500)

                if captcha_detected or await captcha_visible():
                    solved = await solver.solve_tiktok_puzzle(page) if solver else False
                    if not solved or await captcha_visible():
                        await browser.close()
                        return False, "Капча TikTok не пройдена, изменение аватарки остановлено."
                    # After captcha solves, SecSDK releases the pending request. Wait up to 10s.
                    api_res = await wait_for_api(save_start, timeout_ms=10000)
                    if api_res is None:
                        save_btn = page.locator("button[data-e2e='edit-profile-save'], button:has-text('Save')").first
                        if await save_btn.count() > 0 and await save_btn.is_visible() and not await save_btn.is_disabled():
                            retry_start = len(api_events)
                            sbox = await save_btn.bounding_box()
                            if sbox:
                                await page.mouse.click(sbox["x"] + sbox["width"]/2, sbox["y"] + sbox["height"]/2)
                            else:
                                await save_btn.click(force=True)
                            await wait_for_api(retry_start, timeout_ms=8000)

                api_res = await wait_for_api(save_start, timeout_ms=8000)
                if api_res is None:
                    await browser.close()
                    return False, "TikTok не вернул ответ API для сохранения аватарки."
                failure = await api_error(save_start, "аватарки")
                if failure:
                    await browser.close()
                    return failure

                # Wait up to 6s for edit modal to close
                for _ in range(12):
                    save_btn = page.locator("button[data-e2e='edit-profile-save'], button:has-text('Save'), button:has-text('Сохранить')").first
                    if await save_btn.count() == 0 or not await save_btn.is_visible():
                        break
                    await page.wait_for_timeout(500)

                save_btn = page.locator("button[data-e2e='edit-profile-save'], button:has-text('Save'), button:has-text('Сохранить')").first
                if await save_btn.count() > 0 and await save_btn.is_visible():
                    await browser.close()
                    return False, "Окно редактирования не закрылось после сохранения аватарки."

                from urllib.parse import urlsplit
                check_url = f"{profile_url}?_profile_check={int(asyncio.get_running_loop().time() * 1000)}"
                await page.goto(check_url, wait_until="load", timeout=60000)
                await page.wait_for_timeout(4000)
                new_avatar_src = await avatar_url()
                if not new_avatar_src:
                    await browser.close()
                    return False, "Не удалось получить новую аватарку профиля для проверки."
                old_path, new_path = urlsplit(old_avatar_src).path, urlsplit(new_avatar_src).path
                if "1594805258216454" in new_path:
                    await browser.close()
                    return False, "TikTok не применил новую аватарку (остался стандартный силуэт)."
                if old_path and new_path and old_path == new_path:
                    await browser.close()
                    return False, "TikTok не применил новую аватарку (asset path изображения не изменился)."
                await browser.close()
                return True, "Аватарка успешно обновлена и подтверждена в TikTok!"
            except Exception as exc:
                print(f"[TikTok Avatar Error]: {exc} (Page URL: {page.url})", flush=True)
                try:
                    await page.screenshot(path=r"C:\Users\Bogdan\tiktok_bot\avatar_error.png")
                    print("Saved avatar_error.png", flush=True)
                except Exception:
                    pass
                await browser.close()
                return False, f"Ошибка смены аватарки: {str(exc)}"

    @classmethod
    async def update_profile_bio(cls, cookies_json: str, username: str, new_bio: str, proxy_str: str = "") -> Tuple[bool, str]:
        """Update the profile bio with one Save and strict captcha/API handling."""
        cookies = cls.parse_cookies(cookies_json)
        proxy = cls.parse_proxy(proxy_str)
        launch_args = ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-infobars", "--disable-dev-shm-usage"]
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome", headless=True, args=launch_args)
            context = await browser.new_context(proxy=proxy, locale="en-US", viewport={"width": 1440, "height": 900}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
            cookies.append({"name": "tt_lang", "value": "en", "domain": ".tiktok.com", "path": "/"})
            await context.add_cookies(cookies)
            page = await context.new_page()
            await Stealth().apply_stealth_async(page)
            api_events: List[Dict[str, Any]] = []

            async def on_resp(resp):
                if resp.request.method != "POST":
                    return
                endpoint = ("update/profile" if any(token in resp.url for token in ("update/profile", "user/profile/update", "passport/web/account/info/update")) else ("upload/image" if "upload/image" in resp.url else None))
                if endpoint is None:
                    return
                try:
                    data = await resp.json()
                except Exception:
                    data = {}
                raw_code = data.get("status_code")
                try:
                    code = int(raw_code) if raw_code is not None else None
                except (TypeError, ValueError):
                    code = None
                api_events.append({"endpoint": endpoint, "status_code": code, "status_msg": str(data.get("status_msg") or ""), "http_status": resp.status})
                print(f"[TikTok API] {endpoint}: HTTP {resp.status}, status_code={code}", flush=True)

            page.on("response", on_resp)

            async def captcha_visible() -> bool:
                return bool(await page.evaluate("""() => ['#captcha-verify-container-main-page','div.captcha-verify-container','[class*="captcha-verify"]'].some(s => { const n=document.querySelector(s); if (!n) return false; const r=n.getBoundingClientRect(); return r.width > 0 && r.height > 0; })"""))

            def latest_event(start: int = 0) -> Optional[Dict[str, Any]]:
                recent = api_events[start:]
                updates = [e for e in recent if e["endpoint"] == "update/profile"]
                if updates:
                    return updates[-1]
                uploads = [e for e in recent if e["endpoint"] == "upload/image"]
                return uploads[-1] if uploads else None

            async def wait_for_api(start: int, timeout_ms: int = 6000) -> Optional[Dict[str, Any]]:
                deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
                while asyncio.get_running_loop().time() < deadline:
                    event = latest_event(start)
                    if event is not None:
                        return event
                    await page.wait_for_timeout(250)
                return latest_event(start)

            async def api_error(start: int, action: str) -> Optional[Tuple[bool, str]]:
                event = latest_event(start)
                if event is None:
                    return None
                code = event["status_code"]
                if code == 3002284:
                    return False, "⚠️ TikTok временно ограничил редактирование: 'Slow down, you are editing too fast'. Подождите 15-20 минут."
                if code is None:
                    return False, f"TikTok не вернул status_code для операции {action}. Изменение не подтверждено."
                if code != 0 or event["http_status"] >= 400:
                    return False, f"TikTok отклонил изменение описания: {event['status_msg'] or code or event['http_status']}"
                return None

            try:
                profile_url = f"https://www.tiktok.com/@{username}"
                for attempt in range(2):
                    try:
                        await page.goto(profile_url, wait_until="domcontentloaded", timeout=35000)
                        break
                    except Exception as exc:
                        print(f"[TikTok Bio] Page goto attempt {attempt+1} note: {exc}", flush=True)
                        if attempt == 1:
                            pass
                        await asyncio.sleep(2)
                await page.wait_for_timeout(3000)
                for _ in range(3):
                    dismiss = page.locator("button:has-text('Got it'), button:has-text('Not now'), button[aria-label='Close'], button:has-text('Понятно')").first
                    if await dismiss.count() > 0 and await dismiss.is_visible():
                        await dismiss.click(force=True)
                        await page.wait_for_timeout(500)
                await page.keyboard.press("Escape")
                # Robust polling for Edit profile button across client-side SPA routing & hydration
                edit_btn = None
                for _ in range(45):
                    await page.wait_for_timeout(1000)
                    try:
                        candidates = page.locator("button[data-e2e='edit-profile-entrance'], button:has-text('Edit profile'), button:has-text('Изменить профиль'), button[data-e2e*='edit']")
                        if await candidates.count() > 0 and await candidates.first.is_visible():
                            edit_btn = candidates.first
                            break
                    except Exception:
                        pass
                if not edit_btn:
                    await browser.close()
                    return False, "Кнопка редактирования профиля не появилась (страница профиля не загрузилась)."
                await edit_btn.click(force=True)
                await page.wait_for_timeout(1500)
                bio_box = page.locator("textarea[data-e2e='edit-profile-bio-input'], textarea").first
                if await bio_box.count() == 0:
                    await browser.close()
                    return False, "Поле описания профиля не найдено."
                await bio_box.fill(new_bio)
                await page.keyboard.press("Tab")
                await page.wait_for_timeout(800)
                save_btn = page.locator("button[data-e2e='edit-profile-save'], button:has-text('Save'), button:has-text('Сохранить')").first
                await save_btn.wait_for(state="visible", timeout=15000)
                if await save_btn.is_disabled():
                    await browser.close()
                    return False, "Кнопка сохранения описания недоступна."
                save_start = len(api_events)
                sbox = await save_btn.bounding_box()
                if sbox:
                    await page.mouse.click(sbox["x"] + sbox["width"]/2, sbox["y"] + sbox["height"]/2)
                else:
                    await save_btn.click(force=True)

                # Wait up to 12s for either captcha or API response
                captcha_detected = False
                for _ in range(24):
                    if await captcha_visible():
                        captcha_detected = True
                        break
                    if latest_event(save_start) is not None:
                        break
                    await page.wait_for_timeout(500)

                if captcha_detected or await captcha_visible():
                    solver = CapSolverService(CAPSOLVER_API_KEY) if CAPSOLVER_API_KEY else None
                    solved = await solver.solve_tiktok_puzzle(page) if solver else False
                    if not solved or await captcha_visible():
                        await browser.close()
                        return False, "Капча TikTok не пройдена, изменение описания остановлено."
                    # After captcha solves, SecSDK releases the pending request. Wait up to 10s.
                    api_res = await wait_for_api(save_start, timeout_ms=10000)
                    if api_res is None:
                        save_btn = page.locator("button[data-e2e='edit-profile-save'], button:has-text('Save'), button:has-text('Сохранить')").first
                        if await save_btn.count() > 0 and await save_btn.is_visible() and not await save_btn.is_disabled():
                            retry_start = len(api_events)
                            sbox = await save_btn.bounding_box()
                            if sbox:
                                await page.mouse.click(sbox["x"] + sbox["width"]/2, sbox["y"] + sbox["height"]/2)
                            else:
                                await save_btn.click(force=True)
                            await wait_for_api(retry_start, timeout_ms=8000)

                api_res = await wait_for_api(save_start, timeout_ms=8000)
                if api_res is None:
                    await browser.close()
                    return False, "TikTok не вернул ответ API для сохранения описания."
                failure = await api_error(save_start, "описания")
                if failure:
                    await browser.close()
                    return failure

                # Wait up to 6s for edit modal to close
                for _ in range(12):
                    save_btn = page.locator("button[data-e2e='edit-profile-save'], button:has-text('Save')").first
                    if await save_btn.count() == 0 or not await save_btn.is_visible():
                        break
                    await page.wait_for_timeout(500)

                save_btn = page.locator("button[data-e2e='edit-profile-save'], button:has-text('Save')").first
                if await save_btn.count() > 0 and await save_btn.is_visible():
                    await browser.close()
                    return False, "Окно редактирования не закрылось после сохранения описания."
                check_url = f"{profile_url}?_profile_check={int(asyncio.get_running_loop().time() * 1000)}"
                await page.goto(check_url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(3500)
                bio_elem = page.locator("h2[data-e2e='user-bio']")
                if await bio_elem.count() == 0:
                    await browser.close()
                    return False, "Не удалось проверить сохранение био в профиле TikTok."
                live_bio = (await bio_elem.inner_text()).strip()
                if live_bio != new_bio.strip():
                    await browser.close()
                    return False, f"TikTok не применил био (актуальное био в TikTok: '{live_bio}'). Попробуйте через несколько минут."
                await browser.close()
                return True, "Описание профиля успешно обновлено и подтверждено в TikTok!"
            except Exception as exc:
                print(f"[TikTok Bio Error]: {exc}", flush=True)
                await browser.close()
                return False, f"Ошибка смены описания: {str(exc)}"

    @classmethod
    async def interact_with_video(
        cls,
        cookies_json: str,
        video_url: str,
        proxy_str: str = "",
        do_like: bool = True,
        comment_text: str = ""
    ) -> Tuple[bool, str, Optional[str]]:
        """Likes and/or comments on a TikTok video with full captcha handling, API response tracking, and screenshot proof."""
        import uuid
        from config import BASE_DIR

        cookies = cls.parse_cookies(cookies_json)
        proxy = cls.parse_proxy(proxy_str)
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage"
        ]

        async with async_playwright() as p:
            # Visible browser mode is required to bypass SecSDK TicketGuard (which silently drops headless likes/comments)
            browser = await p.chromium.launch(channel="chrome", headless=False, args=launch_args)
            context = await browser.new_context(
                proxy=proxy,
                locale="en-US",
                viewport={"width": 1440, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            cookies.append({"name": "tt_lang", "value": "en", "domain": ".tiktok.com", "path": "/"})
            await context.add_cookies(cookies)
            page = await context.new_page()
            await Stealth().apply_stealth_async(page)

            api_events = {"digg": [], "publish": []}

            async def on_resp(resp):
                url = resp.url
                if "commit/item/digg" in url:
                    try:
                        text = await resp.text()
                        api_events["digg"].append({"status": resp.status, "body": text})
                    except Exception:
                        pass
                elif "comment/publish" in url:
                    try:
                        text = await resp.text()
                        api_events["publish"].append({"status": resp.status, "body": text})
                    except Exception:
                        pass

            page.on("response", on_resp)

            try:
                # If a profile URL was passed (e.g. https://www.tiktok.com/@user), find the latest video
                if "/video/" not in video_url:
                    print(f"[TikTok] Profile URL detected: {video_url}. Finding latest video...", flush=True)
                    try:
                        await page.goto(video_url, wait_until="domcontentloaded", timeout=45000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(4000)
                    first_video = await page.evaluate("""() => {
                        const a = document.querySelector('div[data-e2e="user-post-item"] a, a[href*="/video/"]');
                        return a ? a.href : null;
                    }""")
                    if not first_video:
                        await browser.close()
                        return False, "На этом аккаунте пока нет опубликованных видео для лайка/комментария.", None
                    video_url = first_video
                    print(f"[TikTok] Resolved to latest video: {video_url}", flush=True)

                print(f"[TikTok] Opening video for interaction: {video_url}", flush=True)
                try:
                    await page.goto(video_url, wait_until="domcontentloaded", timeout=45000)
                except Exception:
                    pass

                # Wait for interaction buttons to hydrate
                like_btn = page.locator("div[data-e2e='like-icon'], span[data-e2e='like-icon']").first
                await like_btn.wait_for(state="visible", timeout=30000)
                await page.wait_for_timeout(2000)

                # Dismiss popups
                for _ in range(2):
                    close_btn = page.locator("button[aria-label='Close'], div[class*='shop'] button, div[class*='Shop'] button").first
                    if await close_btn.count() > 0 and await close_btn.is_visible():
                        await close_btn.click(force=True)
                        await page.wait_for_timeout(500)
                await page.keyboard.press("Escape")

                liked = False
                commented = False

                # 1. LIKE ACTION
                if do_like:
                    is_already_liked = await page.evaluate("""() => {
                        const btn = document.querySelector('div[data-e2e="like-icon"], span[data-e2e="like-icon"]');
                        if (!btn) return false;
                        const pressed = btn.getAttribute('aria-pressed');
                        const label = btn.getAttribute('aria-label') || '';
                        return pressed === 'true' || label.toLowerCase().includes('unlike');
                    }""")

                    if not is_already_liked:
                        print("[TikTok] Clicking Like button...", flush=True)
                        lbox = await like_btn.bounding_box()
                        if lbox:
                            await page.mouse.move(lbox['x'] + lbox['width']/2, lbox['y'] + lbox['height']/2, steps=8)
                            await page.wait_for_timeout(200)
                            await page.mouse.click(lbox['x'] + lbox['width']/2, lbox['y'] + lbox['height']/2)
                        else:
                            await like_btn.click()
                        await page.wait_for_timeout(2500)

                        # Verify like via aria-pressed or API event
                        liked = await page.evaluate("""() => {
                            const btn = document.querySelector('div[data-e2e="like-icon"], span[data-e2e="like-icon"]');
                            if (!btn) return false;
                            const pressed = btn.getAttribute('aria-pressed');
                            const label = btn.getAttribute('aria-label') || '';
                            return pressed === 'true' || label.toLowerCase().includes('unlike');
                        }""")
                        if not liked and any("is_digg" in e.get("body", "") for e in api_events["digg"]):
                            liked = True
                    else:
                        print("[TikTok] Video is already liked!", flush=True)
                        liked = True

                # 2. COMMENT ACTION
                if comment_text and comment_text.strip():
                    comment_icon = page.locator("div[data-e2e='comment-icon']").first
                    if await comment_icon.count() > 0:
                        await comment_icon.click()
                        await page.wait_for_timeout(2000)

                    # Focus DraftEditor textbox
                    textbox = page.locator("div.public-DraftEditor-content[role='textbox'], div[data-e2e='comment-text']").first
                    await textbox.wait_for(state="visible", timeout=15000)
                    tbox = await textbox.bounding_box()
                    if tbox:
                        await page.mouse.click(tbox['x'] + tbox['width']/2, tbox['y'] + tbox['height']/2)
                    else:
                        await textbox.click()
                    await page.wait_for_timeout(400)

                    clean_comment = comment_text.strip()
                    print(f"[TikTok] Typing comment: {clean_comment}", flush=True)
                    await page.keyboard.type(clean_comment, delay=random.randint(35, 55))
                    await page.wait_for_timeout(800)

                    post_btn = page.locator("div[data-e2e='comment-post'], button[data-e2e='comment-post']").first
                    await post_btn.wait_for(state="visible", timeout=10000)
                    pbox = await post_btn.bounding_box()
                    if pbox:
                        await page.mouse.move(pbox['x'] + pbox['width']/2, pbox['y'] + pbox['height']/2, steps=6)
                        await page.wait_for_timeout(200)
                        await page.mouse.click(pbox['x'] + pbox['width']/2, pbox['y'] + pbox['height']/2)
                    else:
                        await post_btn.click()
                    print("[TikTok] Clicked Comment Post button.", flush=True)

                    solver = CapSolverService(CAPSOLVER_API_KEY) if CAPSOLVER_API_KEY else None
                    for s in range(12):
                        await page.wait_for_timeout(1000)
                        is_cap = await page.evaluate("""() => {
                            const c = document.querySelector("#captcha-verify-container-main-page, div.captcha-verify-container");
                            return c !== null && c.getBoundingClientRect().width > 0;
                        }""")
                        if is_cap:
                            print("[TikTok] Captcha detected on comment! Solving...", flush=True)
                            if solver:
                                solved = await solver.solve_tiktok_puzzle(page)
                                if solved:
                                    await page.wait_for_timeout(2000)
                                    input_has_text = await page.evaluate("""() => {
                                        const el = document.querySelector('div.public-DraftEditor-content[role="textbox"]');
                                        return el && el.innerText.trim().length > 0;
                                    }""")
                                    if input_has_text and pbox:
                                        await page.mouse.click(pbox['x'] + pbox['width']/2, pbox['y'] + pbox['height']/2)
                            break

                    await page.wait_for_timeout(3500)

                    # Verify publication via API response or DOM
                    if any(e.get("status") == 200 and "comment" in e.get("body", "") for e in api_events["publish"]):
                        commented = True
                    else:
                        input_cleared = await page.evaluate("""() => {
                            const el = document.querySelector('div.public-DraftEditor-content[role="textbox"]');
                            return !el || el.innerText.trim() === '';
                        }""")
                        if input_cleared:
                            commented = True

                shot_name = f"interact_{uuid.uuid4().hex[:8]}.png"
                shot_path = str(BASE_DIR / shot_name)
                await page.screenshot(path=shot_path)
                await browser.close()

                actions = []
                if liked:
                    actions.append("❤️ Лайк поставлен")
                elif do_like:
                    actions.append("⚠️ Лайк не подтвержден")

                if commented:
                    actions.append(f"💬 Комментарий опубликован: «{comment_text.strip()}»")
                elif comment_text.strip():
                    actions.append("⚠️ Комментарий не подтвержден (возможно сработал фильтр спама TikTok)")

                is_ok = liked or commented
                res_msg = " и ".join(actions) if actions else "Действие выполнено"
                return is_ok, res_msg, shot_path
            except Exception as e:
                print(f"[TikTok Interaction Error]: {e}", flush=True)
                await browser.close()
                return False, f"Ошибка при взаимодействии с видео: {str(e)}", None

