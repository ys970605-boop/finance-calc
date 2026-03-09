"""
Instagram @calcmoney.kr 성장 자동화
- 재테크 해시태그 탐색 → 좋아요 + 댓글 + 팔로우
- 팔로워 맞팔 처리
- 일일 한도: 좋아요 120 / 팔로우 50 / 댓글 30
"""
import asyncio
import random
import os
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

SESSION_FILE = "/Users/yongseok/cursor/finance-calc/instagram_session.json"
THREADS_SESSION = "/tmp/threads_session.json"
LOG_FILE = "/Users/yongseok/Desktop/인스타관리.txt"

HASHTAGS = ["재테크", "월급실수령액", "부동산세금", "청약가점", "주택담보대출", "직장인재테크", "실수령액", "취득세", "퇴직금"]

COMMENTS = [
    "진짜 이런 정보 필요했어요",
    "저도 몰랐는데 도움됐어요",
    "계산해보니까 생각보다 많이 차이나네요",
    "직장인이면 다 알아야 하는 내용이죠",
    "공유해주셔서 감사해요",
    "세금 진짜 복잡한데 잘 정리해주셨네요",
    "저도 이거 몰랐는데 진작 알았으면",
    "이런 거 학교에서 안 가르쳐주는 게 아쉬워요",
    "실수령액 계산해보면 진짜 멘붕오죠",
    "부동산 세금 진짜 생각보다 많네요",
    "청약통장 진작 만들걸 싶네요",
    "대출이자 계산하면 무서워지죠",
    "이런 정보 더 많이 알고 싶어요",
    "재테크 공부 열심히 해야겠어요",
    "좋은 정보 감사합니다",
]

DAILY_LIMITS = {"likes": 120, "follows": 50, "comments": 30}
MAX_RETRIES = 3
RETRY_DELAY = 5


def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


async def wait_for_network(page, timeout=10000):
    """네트워크 요청이 안정될 때까지 대기"""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except PlaywrightTimeout:
        log("네트워크 안정화 타임아웃 - 계속 진행")


async def goto_with_retry(page, url, max_retries=MAX_RETRIES):
    """page.goto에 재시도 로직 적용 (최대 max_retries회, RETRY_DELAY초 대기)"""
    for attempt in range(1, max_retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await wait_for_network(page)
            return True
        except (PlaywrightTimeout, Exception) as e:
            log(f"  페이지 로드 실패 (시도 {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                await asyncio.sleep(RETRY_DELAY)
            else:
                raise
    return False


async def is_logged_in(page) -> bool:
    """프로필 선택 다이얼로그가 아닌 진짜 로그인 상태인지 확인"""
    if "accounts/login" in page.url:
        return False
    arias = []
    for el in await page.query_selector_all('[aria-label]'):
        aria = await el.get_attribute("aria-label")
        if aria:
            arias.append(aria.lower())
    # 프로필 선택 다이얼로그면 false
    combined = " ".join(arias)
    if "remove profiles from this browser" in combined:
        return False
    return True


async def refresh_session_if_needed(page):
    if not await is_logged_in(page):
        log("세션 만료 - /tmp/instagram_login_once.py 실행 필요")


async def run_growth():
    if not os.path.exists(SESSION_FILE):
        log("세션 없음 - 스킵")
        return

    counts = {"likes": 0, "follows": 0, "comments": 0}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=SESSION_FILE,
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        page.set_default_timeout(45000)

        # 1. 팔로워 맞팔 처리
        log("맞팔 처리 시작")
        await followback(page, counts)

        # 2. 해시태그 탐색 → 좋아요 + 댓글 + 팔로우
        tags = random.sample(HASHTAGS, min(3, len(HASHTAGS)))
        for tag in tags:
            if counts["likes"] >= DAILY_LIMITS["likes"]:
                break
            log(f"해시태그 탐색: #{tag}")
            await explore_hashtag(page, tag, counts)
            await asyncio.sleep(random.uniform(10, 20))

        await browser.close()

    log(f"완료 - 좋아요:{counts['likes']} 팔로우:{counts['follows']} 댓글:{counts['comments']}")


async def followback(page, counts):
    """팔로워 목록에서 내가 안 팔로우한 사람 팔로우"""
    try:
        await goto_with_retry(page, "https://www.instagram.com/calcmoney.kr/followers/")
        await page.wait_for_timeout(3000)
        await refresh_session_if_needed(page)

        # 팔로워 모달이 열리는지 확인
        for _ in range(5):
            btns = await page.query_selector_all('button')
            for btn in btns:
                txt = (await btn.text_content() or "").strip()
                if txt in ("팔로우", "Follow") and counts["follows"] < DAILY_LIMITS["follows"]:
                    try:
                        await btn.click()
                        counts["follows"] += 1
                        log(f"  맞팔: {counts['follows']}번째")
                        await asyncio.sleep(random.uniform(3, 6))
                    except:
                        pass
            await asyncio.sleep(2)
    except Exception as e:
        log(f"맞팔 오류: {e}")


async def explore_hashtag(page, tag: str, counts: dict):
    try:
        await goto_with_retry(page, f"https://www.instagram.com/explore/tags/{tag}/")
        await page.wait_for_timeout(4000)
        await refresh_session_if_needed(page)

        # 게시물 링크 수집
        links = await page.query_selector_all('a[href*="/p/"]')
        post_urls = []
        for link in links:
            href = await link.get_attribute("href")
            if href and "/p/" in href and href not in post_urls:
                post_urls.append("https://www.instagram.com" + href if href.startswith("/") else href)

        log(f"  #{tag} 게시물 {len(post_urls)}개 발견")
        random.shuffle(post_urls)

        for url in post_urls[:8]:
            if counts["likes"] >= DAILY_LIMITS["likes"]:
                break
            await engage_post(page, url, counts)
            await asyncio.sleep(random.uniform(8, 15))

    except Exception as e:
        log(f"  #{tag} 탐색 오류: {e}")


async def engage_post(page, url: str, counts: dict):
    try:
        await goto_with_retry(page, url)
        await page.wait_for_timeout(3000)

        # 좋아요
        if counts["likes"] < DAILY_LIMITS["likes"]:
            liked = await try_like(page)
            if liked:
                counts["likes"] += 1
                log(f"  좋아요 {counts['likes']}: {url[-20:]}")
                await asyncio.sleep(random.uniform(2, 4))

        # 댓글 (40% 확률)
        if counts["comments"] < DAILY_LIMITS["comments"] and random.random() < 0.4:
            comment = random.choice(COMMENTS)
            commented = await try_comment(page, comment)
            if commented:
                counts["comments"] += 1
                log(f"  댓글 {counts['comments']}: {comment[:20]}")
                await asyncio.sleep(random.uniform(5, 10))

        # 팔로우 (50% 확률)
        if counts["follows"] < DAILY_LIMITS["follows"] and random.random() < 0.5:
            followed = await try_follow(page)
            if followed:
                counts["follows"] += 1
                log(f"  팔로우 {counts['follows']}: {url[-20:]}")
                await asyncio.sleep(random.uniform(4, 8))

    except Exception as e:
        log(f"  engage 오류: {e}")


async def try_like(page) -> bool:
    for selector in [
        'svg[aria-label="Like"]',
        'svg[aria-label="좋아요"]',
        '[aria-label="Like"]',
        '[aria-label="좋아요"]',
    ]:
        try:
            el = await page.query_selector(selector)
            if el:
                parent = await el.evaluate_handle("el => el.closest('button, [role=button]')")
                if parent:
                    await parent.click()
                    return True
        except:
            continue
    return False


async def try_comment(page, text: str) -> bool:
    try:
        # 클릭 전 query
        box = await page.query_selector('[aria-label="Add a comment…"]')
        if not box:
            log("  [댓글] 입력창 못 찾음")
            return False
        await box.click()
        await page.wait_for_timeout(1200)
        # 클릭 후 DOM 재구성 → 재쿼리
        box2 = await page.query_selector('[aria-label="Add a comment…"]')
        if not box2:
            return False
        await box2.fill(text)
        await page.wait_for_timeout(800)
        # Post 버튼 클릭
        post_btn = await page.query_selector('button:has-text("Post")')
        if post_btn:
            await post_btn.click()
            return True
        # 폴백: Enter
        await page.keyboard.press("Enter")
        return True
    except Exception as e:
        log(f"  [댓글] 오류: {e}")
        return False


async def try_follow(page) -> bool:
    try:
        # Instagram 버튼은 div[role="button"] 포함
        btns = await page.query_selector_all('button, [role="button"]')
        for btn in btns:
            txt = (await btn.text_content() or "").strip()
            if txt in ("Follow", "팔로우"):
                visible = await btn.is_visible()
                if visible:
                    await btn.click()
                    return True
            elif txt in ("Following", "팔로잉", "Requested", "요청됨"):
                return False  # 이미 팔로우 중
        return False
    except Exception as e:
        log(f"  [팔로우] 오류: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(run_growth())
