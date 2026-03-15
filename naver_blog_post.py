"""
네이버 블로그 자동 포스팅
- naver-blog/ 폴더의 .txt 파일에서 미포스팅 글 선택
- Playwright로 네이버 SmartEditor에 제목+본문 입력 후 발행
- headed 모드 + stealth / 클립보드 붙여넣기 방식
- launchd 또는 cron으로 호출
"""
import asyncio
import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# ── 설정 ────────────────────────────────────────────────────────────────────
SESSION_FILE = "/Users/yongseok/cursor/finance-calc/naver_session.json"
BLOG_CONTENT_DIR = "/Users/yongseok/cursor/finance-calc/naver-blog/"
POSTED_LOG = "/Users/yongseok/cursor/finance-calc/naver-blog/posted.json"
LOG_FILE = "/Users/yongseok/Desktop/네이버블로그관리.txt"

DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

STEALTH_INIT_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    window.chrome = { runtime: {} };
"""

TITLE_SELECTORS = [
    ".se-section-documentTitle .se-text-paragraph",
    ".se-component.se-documentTitle .se-text-paragraph",
    ".se-component.se-documentTitle .se-module-text",
    ".se-component.se-documentTitle",
]

BODY_SELECTORS = [
    ".se-section-text .se-text-paragraph",
    ".se-component.se-text .se-text-paragraph",
    ".se-component.se-text",
]

PUBLISH_SELECTORS = [
    'button[data-click-area="tpb.publish"]',
    'div.publish_btn_area__KjA2i button.publish_btn__m9KHH',
    "button.publish_btn__m9KHH",
]

PUBLISH_CONFIRM_SELECTORS = [
    'button.confirm_btn__WEaBq',
    'button[data-click-area*="publish"]',
    'button:has-text("발행")',
    'button:has-text("확인")',
]

HELP_CLOSE_SELECTORS = [
    "button.se-help-panel-close-button",
    ".se-help-panel-close",
    '[class*="help"] button[class*="close"]',
]


# ── 유틸 ────────────────────────────────────────────────────────────────────
def log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def clipboard_copy(text: str):
    """macOS pbcopy로 클립보드에 텍스트 복사"""
    process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
    process.communicate(text.encode('utf-8'))


def wait_for_network(max_wait: int = 300, interval: int = 30) -> bool:
    for i in range(max_wait // interval):
        try:
            urllib.request.urlopen("https://www.naver.com", timeout=10)
            return True
        except Exception:
            log(f"네트워크 대기 중... ({(i+1)*interval}s)")
            time.sleep(interval)
    return False


def load_posted() -> list:
    if os.path.exists(POSTED_LOG):
        try:
            with open(POSTED_LOG, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_posted(posted: list):
    os.makedirs(os.path.dirname(POSTED_LOG), exist_ok=True)
    with open(POSTED_LOG, "w", encoding="utf-8") as f:
        json.dump(posted, f, ensure_ascii=False, indent=2)


def pick_next_post() -> tuple[str, str, str] | None:
    """(파일명, 제목, 본문) 반환. 없으면 None"""
    posted = load_posted()
    content_dir = Path(BLOG_CONTENT_DIR)
    if not content_dir.exists():
        log(f"콘텐츠 폴더 없음: {BLOG_CONTENT_DIR}")
        return None

    txt_files = sorted(content_dir.glob("*.txt"))
    remaining = [f for f in txt_files if f.name not in posted]

    if not remaining:
        log("포스팅할 파일 없음 (모두 완료됨)")
        return None

    target = remaining[0]
    raw = target.read_text(encoding="utf-8").strip()
    lines = raw.splitlines()

    title = lines[0].strip() if lines else target.stem
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

    return target.name, title, body


# ── 브라우저 생성 (headless → headed fallback) ───────────────────────────────
async def _create_browser_context(p, headless: bool = True):
    """브라우저+컨텍스트 생성. headless 실패 시 headed로 fallback."""
    browser = await p.chromium.launch(headless=headless, args=BROWSER_ARGS)
    context = await browser.new_context(
        storage_state=SESSION_FILE,
        user_agent=DESKTOP_UA,
        viewport={"width": 1280, "height": 900},
        locale="ko-KR",
        timezone_id="Asia/Seoul",
    )
    await context.add_init_script(STEALTH_INIT_SCRIPT)
    return browser, context


# ── 블로그 ID 자동 감지 ─────────────────────────────────────────────────────
async def detect_blog_id(page) -> str | None:
    """MyBlog.naver 접속 → 리다이렉트된 URL에서 블로그 ID 추출"""
    try:
        # MyBlog.naver는 자기 블로그로 리다이렉트됨 (blog.naver.com/{blogId})
        await page.goto("https://blog.naver.com/MyBlog.naver", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        url = page.url
        log(f"MyBlog 리다이렉트 URL: {url}")

        # https://blog.naver.com/{blogId} 패턴 (.naver 확장자 없는 것만)
        m = re.search(r'blog\.naver\.com/([A-Za-z0-9_\-]+)(?!\.\w)', url)
        if m:
            blog_id = m.group(1)
            # 네이버 시스템 경로 제외
            system_paths = {
                'PostList', 'PostView', 'NBlogTop', 'MyBlog',
                'BlogHome', 'NVisitorg498Main', 'naver', 'section',
            }
            if blog_id not in system_paths and not blog_id.endswith('.naver'):
                log(f"블로그 ID 감지: {blog_id}")
                return blog_id

        log("블로그 ID를 URL에서 추출할 수 없음 — 블로그 미개설 상태일 수 있음")
        return None
    except Exception as e:
        log(f"블로그 ID 감지 실패: {e}")
        return None


# ── 로그인 확인 ──────────────────────────────────────────────────────────────
async def is_logged_in(page) -> bool:
    """네이버 로그인 상태 확인"""
    try:
        url = page.url
        if "nid.naver.com/nidlogin" in url:
            return False
        login_btn = await page.query_selector("a[href*='nidlogin'], .MyView-module__btn_login")
        if login_btn and await login_btn.is_visible():
            return False
        return True
    except Exception:
        return False


async def find_visible_locator(target, selectors: list[str], timeout_ms: int = 5000):
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        for selector in selectors:
            try:
                locator = target.locator(selector)
                count = await locator.count()
                if count == 0:
                    continue
                first = locator.first
                if await first.is_visible():
                    return selector, first
            except Exception:
                continue
        await asyncio.sleep(0.25)
    return None, None


async def close_help_panel(page):
    selector, button = await find_visible_locator(page, HELP_CLOSE_SELECTORS, timeout_ms=2000)
    if not button:
        return
    try:
        await button.click(force=True)
        await page.wait_for_timeout(500)
        log(f"도움말 패널 닫기 (selector: {selector})")
    except Exception as e:
        log(f"도움말 패널 닫기 실패: {e}")


# ── 블로그 접근 테스트 ───────────────────────────────────────────────────────
async def check_blog_access():
    """블로그 접근 + ID 확인만 하는 테스트 함수 (포스팅 없음)"""
    if not os.path.exists(SESSION_FILE):
        log(f"세션 파일 없음: {SESSION_FILE}")
        return

    async with async_playwright() as p:
        # headless 먼저 시도
        for headless in [True, False]:
            mode = "headless" if headless else "headed"
            log(f"브라우저 시작 ({mode})...")
            try:
                browser, context = await _create_browser_context(p, headless=headless)
                page = await context.new_page()
                page.set_default_timeout(30000)

                # 네이버 메인 접속하여 로그인 상태 확인
                await page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                logged_in = await is_logged_in(page)
                log(f"로그인 상태: {'성공' if logged_in else '실패'}")

                if not logged_in:
                    await page.screenshot(path="/tmp/naver_blog_login_fail.png")
                    log(f"스크린샷: /tmp/naver_blog_login_fail.png")
                    await browser.close()
                    if headless:
                        log("headless 모드에서 로그인 실패, headed 모드로 재시도...")
                        continue
                    else:
                        log("headed 모드에서도 로그인 실패 — 세션 만료. naver_login.py 재실행 필요")
                        return

                # 블로그 ID 감지
                blog_id = await detect_blog_id(page)
                if not blog_id:
                    log("블로그 미개설 상태이거나 접근 불가")
                    await page.screenshot(path="/tmp/naver_blog_no_blog.png")
                    await browser.close()
                    return

                # 글쓰기 페이지 접근 테스트
                write_url = f"https://blog.naver.com/{blog_id}/postwrite"
                log(f"글쓰기 페이지 접근 테스트: {write_url}")
                await page.goto(write_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

                # iframe 존재 확인
                frame = page.frame(name="mainFrame")
                if frame:
                    log("mainFrame iframe 감지 성공")
                else:
                    log("mainFrame iframe 없음 — 에디터가 iframe 없이 로드되었거나 접근 차단")

                await page.screenshot(path="/tmp/naver_blog_access_test.png")
                log(f"접근 테스트 스크린샷: /tmp/naver_blog_access_test.png")
                log(f"블로그 접근 테스트 완료 — 블로그 ID: {blog_id}, 모드: {mode}")
                await browser.close()
                return

            except Exception as e:
                log(f"{mode} 모드 오류: {e}")
                try:
                    await browser.close()
                except Exception:
                    pass
                if headless:
                    log("headed 모드로 재시도...")
                    continue
                else:
                    log("headed 모드에서도 실패")
                    return


# ── 실제 포스팅 ──────────────────────────────────────────────────────────────
async def _do_post(title: str, body: str) -> bool:
    if not os.path.exists(SESSION_FILE):
        log(f"세션 파일 없음: {SESSION_FILE} — naver_login.py 실행 필요")
        return False

    async with async_playwright() as p:
        for headless in [True, False]:
            mode = "headless" if headless else "headed"
            log(f"포스팅 시도 ({mode})...")
            try:
                browser, context = await _create_browser_context(p, headless=headless)
                page = await context.new_page()
                page.set_default_timeout(45000)

                # ── 블로그 존재 확인 + ID 감지 ──────────────────────────────────
                await page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                if not await is_logged_in(page):
                    log(f"로그인 실패 ({mode})")
                    await browser.close()
                    if headless:
                        continue
                    else:
                        log("세션 만료. naver_login.py 재실행 필요")
                        return False

                blog_id = await detect_blog_id(page)
                if not blog_id:
                    log("블로그 ID 감지 실패")
                    await browser.close()
                    return False

                # ── 글쓰기 페이지 접속 ──────────────────────────────────────────
                write_url = f"https://blog.naver.com/{blog_id}/postwrite"
                log(f"글쓰기 페이지 접속: {write_url}")

                for attempt in range(3):
                    try:
                        await page.goto(write_url, wait_until="domcontentloaded", timeout=60000)
                        break
                    except Exception as e:
                        if attempt < 2:
                            log(f"페이지 접속 재시도 {attempt+2}/3...")
                            await page.wait_for_timeout(5000)
                        else:
                            log(f"페이지 접속 실패: {e}")
                            await browser.close()
                            if headless:
                                continue
                            return False

                await page.wait_for_timeout(3000)

                # ── "작성 중인 글이 있습니다" 팝업 처리 ────────────────────────
                # 취소 버튼은 페이지를 닫아버리므로, 확인(이어서 작성)을 클릭
                for popup_wait in range(5):
                    try:
                        confirm_btn = await page.query_selector('button.se-popup-button-confirm')
                        if confirm_btn and await confirm_btn.is_visible():
                            await confirm_btn.click()
                            await page.wait_for_timeout(3000)
                            log("'작성 중인 글' 팝업 — 확인 클릭 (이어서 작성)")
                            break
                    except Exception:
                        pass
                    await page.wait_for_timeout(1000)

                # ── iframe 전환 (없으면 page 직접 사용) ───────────────────────
                editor_frame = None
                try:
                    frame_el = await page.query_selector('iframe#mainFrame')
                    if frame_el:
                        editor_frame = await frame_el.content_frame()
                except Exception:
                    pass
                if not editor_frame:
                    editor_frame = page.frame(name="mainFrame")

                target = editor_frame if editor_frame else page
                log(f"에디터 타겟: {'iframe' if editor_frame else 'page'}")

                # 에디터 로드 대기 — 제목 영역이 나타날 때까지
                title_selector, title_locator = await find_visible_locator(target, TITLE_SELECTORS, timeout_ms=15000)
                if not title_locator:
                    log("에디터 로드 대기 실패 — .se-documentTitle 미발견")
                    await page.screenshot(path="/tmp/naver_blog_editor_load_fail.png")
                    await browser.close()
                    if headless:
                        continue
                    return False

                await close_help_panel(page)
                await page.wait_for_timeout(1000)

                # ── 제목 입력 ─────────────────────────────────────────────────
                try:
                    await title_locator.scroll_into_view_if_needed()
                    await title_locator.click(force=True)
                    await page.wait_for_timeout(300)
                    await page.keyboard.press("Meta+a")
                    await page.wait_for_timeout(100)
                    await page.keyboard.press("Backspace")
                    await page.wait_for_timeout(300)
                    await page.keyboard.insert_text(title)
                    await page.wait_for_timeout(500)
                    log(f"제목 입력 완료: {title[:30]} (selector: {title_selector})")
                except Exception as e:
                    log(f"제목 입력 실패: {e}")
                    log("제목 입력 요소 찾기 실패")
                    await page.screenshot(path="/tmp/naver_blog_title_fail.png")
                    await browser.close()
                    if headless:
                        continue
                    return False

                # ── 본문 입력 (클립보드 붙여넣기) ───────────────────────────────
                body_selector, body_locator = await find_visible_locator(target, BODY_SELECTORS, timeout_ms=8000)
                if not body_locator:
                    log("본문 입력 요소 찾기 실패")
                    await page.screenshot(path="/tmp/naver_blog_body_fail.png")
                    await browser.close()
                    if headless:
                        continue
                    return False

                try:
                    await body_locator.scroll_into_view_if_needed()
                    await body_locator.click(force=True)
                    await page.wait_for_timeout(300)
                    await page.keyboard.press("Meta+a")
                    await page.wait_for_timeout(100)
                    await page.keyboard.press("Backspace")
                    await page.wait_for_timeout(300)
                    paragraphs = body.split('\n\n')
                    for i, para in enumerate(paragraphs):
                        await page.keyboard.insert_text(para)
                        if i < len(paragraphs) - 1:
                            await page.keyboard.press('Enter')
                            await page.keyboard.press('Enter')
                        await page.wait_for_timeout(80)
                    log(f"본문 입력 완료: {len(body)}자 (selector: {body_selector})")
                except Exception as e:
                    log(f"본문 입력 실패: {e}")
                    await page.screenshot(path="/tmp/naver_blog_body_fail.png")
                    await browser.close()
                    if headless:
                        continue
                    return False

                await page.wait_for_timeout(2000)

                # ── 도움말 패널 닫기 (있으면) ─────────────────────────────────────
                await close_help_panel(page)

                # ── 발행 버튼 클릭 ──────────────────────────────────────────────
                # 발행 버튼은 항상 page level에 있음 (iframe 밖)
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(500)
                publish_selector, publish_button = await find_visible_locator(page, PUBLISH_SELECTORS, timeout_ms=5000)
                if not publish_button:
                    log("발행 버튼을 찾지 못함")
                    await page.screenshot(path="/tmp/naver_blog_publish_fail.png")
                    await browser.close()
                    if headless:
                        continue
                    return False
                try:
                    await publish_button.click(force=True)
                    await page.wait_for_timeout(3000)
                    log(f"발행 버튼 클릭 (selector: {publish_selector})")
                except Exception as e:
                    log(f"발행 버튼 클릭 실패: {e}")
                    await page.screenshot(path="/tmp/naver_blog_publish_fail.png")
                    await browser.close()
                    if headless:
                        continue
                    return False

                # ── 발행 확인 팝업 ──────────────────────────────────────────────
                await page.wait_for_timeout(2000)
                confirm_selector, confirm_button = await find_visible_locator(page, PUBLISH_CONFIRM_SELECTORS, timeout_ms=5000)
                if confirm_button:
                    try:
                        await confirm_button.click(force=True)
                        await page.wait_for_timeout(3000)
                        log(f"발행 확인 팝업 처리 (selector: {confirm_selector})")
                    except Exception as e:
                        log(f"발행 확인 클릭 실패: {e}")
                        await page.screenshot(path="/tmp/naver_blog_publish_confirm_fail.png")
                        await browser.close()
                        if headless:
                            continue
                        return False
                else:
                    log("발행 확인 팝업 없음 (바로 발행된 것으로 추정)")

                await page.wait_for_timeout(3000)
                log(f"포스팅 완료: {title[:30]}")
                await browser.close()
                return True

            except Exception as e:
                log(f"포스팅 오류 ({mode}): {e}")
                try:
                    await browser.close()
                except Exception:
                    pass
                if headless:
                    log("headed 모드로 재시도...")
                    continue
                return False

    return False


# ── 재시도 래퍼 ──────────────────────────────────────────────────────────────
async def post_to_naver_blog(title: str, body: str) -> bool:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await _do_post(title, body)
        except Exception as e:
            log(f"포스팅 네트워크 오류 (시도 {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
            else:
                log("포스팅 최대 재시도 초과")
                return False
    return False


# ── 진입점 ───────────────────────────────────────────────────────────────────
def main():
    # 네트워크 연결 확인
    if not wait_for_network():
        log("네트워크 연결 실패 - 종료")
        return

    # 세션 파일 확인
    if not os.path.exists(SESSION_FILE):
        log(f"세션 파일 없음: {SESSION_FILE} — naver_login.py 실행 필요")
        return

    # 포스팅할 파일 선택
    result = pick_next_post()
    if result is None:
        return

    filename, title, body = result
    log(f"선택된 파일: {filename} / 제목: {title[:30]}")

    # 포스팅 실행
    success = asyncio.run(post_to_naver_blog(title, body))

    if success:
        posted = load_posted()
        posted.append(filename)
        save_posted(posted)
        log(f"포스팅 기록 저장: {filename}")
        print(f"[{datetime.now()}] 네이버 블로그 포스팅 완료: {title[:30]}")
    else:
        log(f"포스팅 실패: {filename}")
        print(f"[{datetime.now()}] 네이버 블로그 포스팅 실패")


if __name__ == "__main__":
    main()
