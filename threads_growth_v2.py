"""
쓰레드 성장 자동화 v5.0
- 일일 한도 엄격 적용 (팔로우 20, 댓글 15, 좋아요 120)
- 세션 시작 시 로그 파일에서 오늘 수행량 카운트 → 남은 할당량만 수행
- 한도 도달 시 해당 액션 즉시 중단
- 타임아웃 60초, 네트워크 에러 재시도, 세션 만료 감지
"""
import asyncio
import os
import random
import re
import time
import urllib.request
from datetime import datetime
from playwright.async_api import async_playwright


def wait_for_network(max_wait=300, interval=10):
    """네트워크 연결 대기 (맥 잠자기 복귀 대응, 최대 300초)"""
    start = time.time()
    attempt = 0
    while time.time() - start < max_wait:
        try:
            urllib.request.urlopen("https://www.google.com", timeout=10)
            if attempt > 0:
                print(f"[{datetime.now()}] 네트워크 복구됨 ({int(time.time()-start)}초 후)")
            return True
        except:
            attempt += 1
            elapsed = int(time.time() - start)
            print(f"[{datetime.now()}] 네트워크 대기 중... ({elapsed}s/{max_wait}s)")
            time.sleep(interval)
    return False

SESSION_FILE = "/tmp/threads_session.json"
LOG_FILE = "/Users/yongseok/Desktop/쓰레드관리.txt"

MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

SEARCH_KEYWORDS = ["재테크", "월급", "부동산"]

# 카테고리별 댓글 템플릿 (총 85개+)
COMMENTS_BY_CATEGORY = {
    "재테크": [
        "오 이거 몰랐는데 좋은 정보네요",
        "북마크 해둡니다 나중에 꼭 참고할게요",
        "이런 정보 어디서 찾으셨어요 대단하다",
        "저도 올해부터 재테크 시작했는데 도움 많이 되네요",
        "주변에도 공유해야겠다 다들 모르더라고요",
        "와 정리 진짜 깔끔하네요 저장해둡니다",
        "재테크 처음인데 이런 글이 진짜 도움됨",
        "혹시 초보한테 추천하는 것도 있을까요?",
        "이거 보고 바로 실행해봐야겠다",
        "이런 거 학교에서 알려줬으면 좋았을 텐데",
    ],
    "월급": [
        "진짜 공감됨 월급 들어오자마자 사라지는 느낌",
        "세금 떼고 나면 진짜 허무하죠 ㅋㅋ",
        "저도 계산해봤는데 생각보다 훨씬 적더라고요",
        "실수령액 알고 나서 좀 현타왔어요 솔직히",
        "연봉협상 전에 이거 꼭 알아야 하는데 맞는 말",
        "월급 관리 어떻게 하세요 저는 항상 부족",
        "이런 거 미리 알았으면 좋았을 텐데 진심",
        "저 이거 보고 가계부 다시 쓰기 시작함",
        "직장인 필수 정보네요 저장합니다",
        "맞아요 세금 떼고 나면 진짜 얼마 안 남죠",
    ],
    "부동산": [
        "취득세 생각하면 집 사기가 더 무섭긴 하죠",
        "부동산 세금 진짜 복잡한데 정리 잘해주셨네요",
        "전세 vs 매매 고민중인데 참고할게요",
        "이거 보니까 내 집 마련이 더 멀게 느껴진다",
        "혹시 1주택자도 해당되는 건가요?",
        "부동산 공부 시작했는데 이런 글 너무 좋다",
        "세금 계산이 제일 어려운데 감사합니다",
        "요즘 부동산 시장 어떻게 보세요 궁금",
        "저도 내년에 매수 고민중이라 찜해둡니다",
        "주변에 집 산 친구한테도 알려줘야겠다",
    ],
    "주식": [
        "주식 세금도 만만치 않더라고요",
        "오 이 종목 저도 관심 있었는데",
        "장기투자가 답인 건 알겠는데 기다리기가 힘듦",
        "혹시 ETF 쪽도 정리해주실 수 있나요?",
        "이거 보고 포트폴리오 다시 점검해봐야겠다",
        "주식 초보인데 이런 글 진짜 감사해요",
        "배당주 쪽은 어떻게 생각하세요?",
        "양도세 계산 항상 헷갈렸는데 도움됩니다",
        "저도 올해 수익률 고민이 많아서 공감가네요",
        "투자 공부 같이 하는 느낌이라 좋아요",
    ],
    "적금": [
        "요즘 적금 금리 어디가 제일 괜찮아요?",
        "적금이 답인 건 알겠는데 금리가 너무 낮아서",
        "저는 파킹통장이랑 병행중인데 괜찮더라고요",
        "혹시 특판 적금 정보도 있으신가요?",
        "적금 만기까지 버티는 게 제일 어려움 ㅋㅋ",
        "이자 계산해보니 생각보다 차이 나더라고요",
        "비상금은 CMA가 낫다고 하던데 어떤가요",
        "자동이체 걸어놓으니까 모으기 훨씬 편해졌어요",
        "저도 올해 목표가 적금 꽉 채우는 건데 화이팅",
        "적금 풍차돌리기 해보신 분 계세요?",
    ],
    "청약": [
        "청약통장 오래 유지한 보람이 있어야 할 텐데",
        "특별공급 조건 진짜 까다롭지 않나요",
        "청약 점수 계산 해봤는데 아직 멀었더라고요",
        "무주택 기간이 제일 중요한 거 맞죠?",
        "혹시 신혼특공도 정리해주실 수 있나요?",
        "당첨되신 분 계시면 후기 좀 알려주세요",
        "청약홈 매번 들어가는데 복잡해서 힘듦",
        "가점제 vs 추첨제 뭐가 유리한지 항상 고민됨",
        "저도 청약 노리고 있어서 참고할게요",
        "이거 정리 진짜 잘하셨다 저장합니다",
    ],
    "퇴직금": [
        "퇴직금 IRP로 받으면 세금 아낄 수 있다던데 맞나요",
        "퇴직금 계산해보니 생각보다 적어서 놀랐어요",
        "중간정산 받으면 나중에 불이익 있나요?",
        "이직할 때 퇴직금 어떻게 처리하셨어요?",
        "퇴직연금 DC형 DB형 차이가 뭔지 항상 헷갈림",
        "이거 보고 퇴직금 계산기 돌려봤는데 감사합니다",
        "아직 먼 이야기 같지만 미리 알아두면 좋겠네요",
        "퇴직금 세금 생각보다 많이 떼가더라고요",
        "연금저축이랑 같이 굴리면 좋다고 하던데 맞나요",
        "혹시 퇴직금 중간정산 조건도 알려주실 수 있나요",
    ],
}

# 일반 댓글 (키워드 매칭 안 될 때 사용)
COMMENTS_GENERAL = [
    "오 좋은 정보 감사합니다 저장해둘게요",
    "이거 진짜 몰랐는데 알려줘서 고마워요",
    "공감가네요 저도 비슷한 상황이라",
    "이런 글 자주 올려주세요 도움 많이 돼요",
    "저도 해봐야겠다 좋은 팁이네요",
    "와 깔끔한 정리 감사합니다",
    "친구한테도 공유해야겠어요 유용하네요",
    "더 자세히 알고 싶은데 관련 내용 더 있나요?",
    "저는 이거 해봤는데 확실히 도움됐어요",
    "이거 보니까 나도 뭔가 시작해야겠다는 생각이 드네",
    "진짜 유용한 내용이네요 잘 봤습니다",
    "정보 공유 감사해요 많이 배우고 갑니다",
    "이런 거 하나하나 알아가는 재미가 있네요",
    "혹시 다른 팁도 있으면 알려주세요",
    "직접 해본 후기 궁금한데 나중에 올려주실 수 있나요",
]

# 중복 방지: 최근 사용 댓글 기록
_recent_comments = []
_RECENT_LIMIT = 10

def get_comment_for_keyword(keyword):
    """키워드에 맞는 댓글을 중복 없이 반환"""
    global _recent_comments

    # 키워드에 매칭되는 카테고리 찾기
    pool = None
    for cat_key, cat_comments in COMMENTS_BY_CATEGORY.items():
        if cat_key in keyword:
            pool = cat_comments
            break
    if pool is None:
        pool = COMMENTS_GENERAL

    # 최근 사용 안 한 댓글만 후보로
    candidates = [c for c in pool if c not in _recent_comments]
    if not candidates:
        # 카테고리 풀 소진 시 일반 풀에서도 시도
        all_pool = pool + COMMENTS_GENERAL
        candidates = [c for c in all_pool if c not in _recent_comments]
    if not candidates:
        # 전부 소진되면 기록 리셋 후 재선택
        _recent_comments.clear()
        candidates = pool

    comment = random.choice(candidates)

    # 최근 기록 업데이트
    _recent_comments.append(comment)
    if len(_recent_comments) > _RECENT_LIMIT:
        _recent_comments.pop(0)

    return comment

# ── 일일 한도 (절대 초과 금지) ──
DAILY_MAX_FOLLOWS = 20
DAILY_MAX_COMMENTS = 15
DAILY_MAX_LIKES = 120

def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def count_today_actions():
    """로그 파일에서 오늘 날짜의 팔로우/댓글/좋아요 수행량을 카운트"""
    today_str = datetime.now().strftime('%Y-%m-%d')
    follows = 0
    comments = 0
    likes = 0

    if not os.path.exists(LOG_FILE):
        return follows, comments, likes

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                # 오늘 날짜 로그만 처리
                if today_str not in line:
                    continue
                if "팔로우" in line and ("✅" in line):
                    follows += 1
                elif "댓글" in line and ("💬" in line):
                    comments += 1
                elif "좋아요" in line and ("❤️" in line):
                    # "좋아요 N개" 형식에서 숫자 추출
                    m = re.search(r'좋아요\s*(\d+)개', line)
                    if m:
                        likes += int(m.group(1))
    except Exception:
        pass

    return follows, comments, likes

def is_session_expired(url):
    """세션 만료 여부 - threads.com 홈이나 로그인 페이지로 리다이렉트된 경우"""
    normalized = url.rstrip("/")
    return normalized in ("https://www.threads.com", "https://www.threads.net") or "login" in url

async def get_btn(page, text):
    all_btns = await page.query_selector_all('div[role="button"], button')
    for btn in all_btns:
        txt = await btn.text_content()
        if txt and txt.strip() == text:
            return btn
    return None

async def try_like(page):
    try:
        all_btns = await page.query_selector_all('div[role="button"], button')
        for btn in all_btns:
            txt = (await btn.text_content() or "").strip()
            if txt in ("Like", "좋아요"):
                box = await btn.bounding_box()
                if box and box["width"] > 0:
                    await btn.click()
                    await page.wait_for_timeout(500)
                    return True
        return False
    except:
        return False

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=SESSION_FILE,
            user_agent=MOBILE_UA,
            viewport={"width": 390, "height": 844}
        )
        page = await context.new_page()
        page.set_default_timeout(45000)  # 45초 기본 타임아웃

        async def goto_with_retry(url, max_retries=3, retry_delay=5):
            """page.goto 래퍼 — 타임아웃/네트워크 에러 시 재시도"""
            for attempt in range(max_retries):
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    return True
                except Exception as e:
                    err = str(e)
                    is_network_err = "net::ERR" in err or "ERR_INTERNET_DISCONNECTED" in err
                    is_timeout = "Timeout" in err

                    if attempt < max_retries - 1:
                        if is_network_err:
                            log(f"  🔄 네트워크 에러 (시도 {attempt+1}/{max_retries}): {err[:60]}")
                            # 네트워크 복구 대기
                            if not wait_for_network(max_wait=300, interval=10):
                                log("  ⛔ 네트워크 복구 실패")
                                raise
                        elif is_timeout:
                            log(f"  🔄 타임아웃 재시도 ({attempt+1}/{max_retries}): {url[:60]}")
                            await asyncio.sleep(retry_delay)
                        else:
                            raise
                    else:
                        raise
            return False

        total_followed = 0
        total_commented = 0
        total_liked = 0

        # 오늘 이미 수행한 양을 로그에서 카운트
        done_follows, done_comments, done_likes = count_today_actions()
        remain_follows = max(0, DAILY_MAX_FOLLOWS - done_follows)
        remain_comments = max(0, DAILY_MAX_COMMENTS - done_comments)
        remain_likes = max(0, DAILY_MAX_LIKES - done_likes)

        log(f"── 세션 시작 | 오늘 누적: 팔로우 {done_follows}/{DAILY_MAX_FOLLOWS}, 댓글 {done_comments}/{DAILY_MAX_COMMENTS}, 좋아요 {done_likes}/{DAILY_MAX_LIKES}")
        log(f"── 남은 할당: 팔로우 {remain_follows}, 댓글 {remain_comments}, 좋아요 {remain_likes}")

        if remain_follows == 0 and remain_comments == 0 and remain_likes == 0:
            log("⛔ 오늘 일일 한도 모두 소진 — 종료")
            await browser.close()
            return

        # 키워드별 할당량 분배
        num_kw = len(SEARCH_KEYWORDS)
        follows_per_kw = max(1, remain_follows // num_kw) if remain_follows > 0 else 0
        comments_per_kw = max(1, remain_comments // num_kw) if remain_comments > 0 else 0

        for keyword in SEARCH_KEYWORDS:
            try:
                search_url = f"https://www.threads.com/search?q={keyword}&serp_type=default"
                await goto_with_retry(search_url)
                await page.wait_for_timeout(4000)

                # 세션 만료 체크
                if is_session_expired(page.url):
                    log(f"  ⛔ 세션 만료 감지 ({page.url}) — 중단")
                    break

                # 프로필 수집 → 팔로우
                profile_links = await page.evaluate("""
                    () => {
                        const links = document.querySelectorAll('a[href*="/@"]');
                        const seen = new Set();
                        const result = [];
                        for (const a of links) {
                            const href = a.href;
                            if (href.includes('/@') && !href.includes('/post/') && !seen.has(href)) {
                                seen.add(href);
                                result.push(href);
                            }
                        }
                        return result.slice(0, 8);
                    }
                """)

                followed_this_kw = 0
                for profile_url in profile_links:
                    if followed_this_kw >= follows_per_kw or total_followed >= remain_follows:
                        break
                    if "calcmoney" in profile_url:
                        continue
                    try:
                        await goto_with_retry(profile_url)
                        await page.wait_for_timeout(2000)
                        if is_session_expired(page.url):
                            log("  ⛔ 팔로우 중 세션 만료 — 중단")
                            break
                        follow_btn = await get_btn(page, "Follow") or await get_btn(page, "팔로우")
                        if follow_btn:
                            await follow_btn.click()
                            await page.wait_for_timeout(2000)
                            new_txt = await follow_btn.text_content()
                            if new_txt and new_txt.strip() in ("Following", "팔로잉", "Requested"):
                                total_followed += 1
                                followed_this_kw += 1
                                log(f"  ✅ 팔로우 ({keyword}): {profile_url.split('/@')[-1]}")
                                await asyncio.sleep(random.uniform(4, 7))
                    except Exception as e:
                        err_str = str(e)
                        if "session_expired" in err_str:
                            break
                        if "ERR_INTERNET_DISCONNECTED" in err_str or "net::ERR" in err_str:
                            log("  🔄 팔로우 중 네트워크 에러 — 복구 대기")
                            if not wait_for_network(max_wait=300, interval=10):
                                break
                        continue

                # 검색 결과로 돌아가기 → 게시물 좋아요 + 댓글
                await goto_with_retry(search_url)
                await page.wait_for_timeout(3000)
                if is_session_expired(page.url):
                    log("  ⛔ 세션 만료 — 중단")
                    break

                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 1200)")
                    await page.wait_for_timeout(1000)

                post_links = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('a[href*="/post/"]'))
                        .map(a => a.href).filter((v,i,a) => a.indexOf(v)===i).slice(0, 10)
                """)

                liked_this_kw = 0
                commented_this_kw = 0
                for i, post_url in enumerate(post_links):
                    if total_liked >= remain_likes:
                        break
                    try:
                        await goto_with_retry(post_url)
                        await page.wait_for_timeout(2000)
                        if is_session_expired(page.url):
                            log("  ⛔ 세션 만료 — 중단")
                            break

                        ok = await try_like(page)
                        if ok:
                            total_liked += 1
                            liked_this_kw += 1

                        # 댓글 (키워드당 할당량 + 일일 한도)
                        if commented_this_kw < comments_per_kw and total_commented < remain_comments:
                            reply_btn = await get_btn(page, "Reply") or await get_btn(page, "답글")
                            if reply_btn:
                                await reply_btn.click()
                                await page.wait_for_timeout(1500)

                            editors = await page.query_selector_all('[contenteditable="true"]')
                            if editors:
                                comment = get_comment_for_keyword(keyword)
                                await editors[-1].click()
                                await editors[-1].type(comment, delay=40)
                                await page.wait_for_timeout(800)

                                posted = await page.evaluate("""
                                    () => {
                                        const btns = document.querySelectorAll('div[role="button"], button');
                                        for (const b of btns) {
                                            const t = b.textContent.trim();
                                            if (t === 'Post' || t === '게시') {
                                                const r = b.getBoundingClientRect();
                                                if (r.width > 0) { b.click(); return true; }
                                            }
                                        }
                                        return false;
                                    }
                                """)
                                if posted:
                                    total_commented += 1
                                    commented_this_kw += 1
                                    log(f"  💬 댓글 ({keyword}): '{comment[:20]}...'")
                                    await page.wait_for_timeout(3000)

                        await asyncio.sleep(random.uniform(5, 10))
                    except:
                        continue

                if liked_this_kw > 0:
                    log(f"  ❤️ 좋아요 {liked_this_kw}개 ({keyword})")

                await asyncio.sleep(random.uniform(8, 15))

            except Exception as e:
                err = str(e)[:80]
                log(f"  ⚠️ {keyword} 오류: {err}")
                if "ERR_INTERNET_DISCONNECTED" in err or "net::ERR" in err:
                    log("  🔄 네트워크 에러 — 복구 대기 중...")
                    if not wait_for_network(max_wait=300, interval=10):
                        log("  ⛔ 네트워크 복구 실패 — 종료")
                        break
                elif "Timeout" in err:
                    await asyncio.sleep(10)
                continue

        await browser.close()
        final_f = done_follows + total_followed
        final_c = done_comments + total_commented
        final_l = done_likes + total_liked
        log(f"\n━━ 세션 완료: 팔로우 {total_followed} | 좋아요 {total_liked} | 댓글 {total_commented}")
        log(f"━━ 오늘 누적: 팔로우 {final_f}/{DAILY_MAX_FOLLOWS} | 댓글 {final_c}/{DAILY_MAX_COMMENTS} | 좋아요 {final_l}/{DAILY_MAX_LIKES} ━━")

if not wait_for_network():
    print(f"[{datetime.now()}] 네트워크 연결 실패 - 종료")
else:
    asyncio.run(run())
