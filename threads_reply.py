"""
Threads 자동 답글 - 내 게시물 댓글에 자동 응답
Playwright 기반 (API 토큰 없이 동작)
10분 간격 launchd로 실행
"""
import asyncio
import json
import os
import random
import time
import urllib.request
from datetime import datetime
from playwright.async_api import async_playwright


def wait_for_network(max_wait=300, interval=30):
    """네트워크 연결 대기 (맥 잠자기 복귀 대응)"""
    for i in range(max_wait // interval):
        try:
            urllib.request.urlopen("https://www.google.com", timeout=10)
            return True
        except:
            print(f"[{datetime.now()}] 네트워크 대기 중... ({(i+1)*interval}s)")
            time.sleep(interval)
    return False

SESSION_FILE = "/tmp/threads_session.json"
REPLIED_FILE = "/tmp/threads_replied.json"
LOG_FILE = "/Users/yongseok/Desktop/쓰레드관리.txt"

MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

# 답글 템플릿 (카테고리별로 분류)
_REPLY_THANK = [
    "고마워! 혹시 더 궁금한 거 있으면 편하게 물어봐",
    "와 댓글 고마워 ㅎㅎ 힘이 된다",
    "읽어줘서 감사해요!",
    "이런 댓글이 진짜 힘이 돼 고마워",
    "관심 가져줘서 고마워!",
    "ㅎㅎ 봐줘서 감사합니다",
]

_REPLY_EMPATHY = [
    "맞아 진짜 많은 사람들이 모르고 넘어가더라",
    "ㅋㅋ 다들 비슷한 상황이구나",
    "공감해줘서 고마워 ㅎㅎ",
    "진짜 이거 겪어보면 공감할 수밖에 없지",
    "나도 처음엔 몰랐는데 알고 나니까 완전 다르더라",
    "맞아 나도 똑같은 생각이었어",
    "이거 나만 그런 줄 알았는데 다들 비슷하구나 ㅋㅋ",
]

_REPLY_INFO = [
    "이거 알면 확실히 다르지",
    "맞아 이거 진짜 중요한데 아는 사람이 별로 없어",
    "정보 필요하면 프로필 링크에 계산기 있어!",
    "프로필에 계산기 링크 있으니까 한번 써봐 도움 될 거야",
    "이건 직접 계산해보는 게 제일 정확해 프로필 참고해봐",
    "좀 더 자세한 내용은 프로필 링크에서 확인할 수 있어",
]

_REPLY_QUESTION = [
    "좋은 질문이야! 상황마다 다를 수 있는데 계산기로 확인해봐",
    "오 그 부분은 개인 상황마다 달라서 직접 계산해보는 게 좋아",
    "그건 소득이랑 상황에 따라 다른데 한번 계산해봐!",
    "궁금한 거 있으면 더 물어봐 아는 선에서 답해줄게",
    "그 부분은 케이스마다 다른데 혹시 구체적으로 궁금한 거 있어?",
]

_REPLY_EXPERIENCE = [
    "나도 이거 직접 해보고 차이를 느꼈어",
    "주변에서도 이거 알려주면 다들 놀라더라",
    "실제로 해보면 생각보다 간단해",
    "이거 한번 해보면 왜 진작 안 했나 싶을 거야",
    "나도 처음엔 귀찮았는데 해보니까 확실히 달라",
    "친구한테 알려줬더니 진짜 고맙다고 하더라 ㅋㅋ",
]

# 전체 템플릿 합산 (카테고리 혼합)
REPLY_TEMPLATES = _REPLY_THANK + _REPLY_EMPATHY + _REPLY_INFO + _REPLY_QUESTION + _REPLY_EXPERIENCE

# 최근 사용 답글 추적 (중복 방지)
RECENT_REPLIES_FILE = "/tmp/threads_recent_replies.json"


def _load_recent_replies():
    if os.path.exists(RECENT_REPLIES_FILE):
        with open(RECENT_REPLIES_FILE) as f:
            return json.load(f)
    return []


def _save_recent_replies(recent):
    with open(RECENT_REPLIES_FILE, "w") as f:
        json.dump(recent[-15:], f)


def pick_reply():
    """중복 방지하며 답글 선택 (최근 15개와 겹치지 않게)"""
    recent = _load_recent_replies()
    available = [t for t in REPLY_TEMPLATES if t not in recent]
    if not available:
        # 전부 소진되면 최근 절반만 유지하고 리셋
        recent = recent[len(recent) // 2:]
        _save_recent_replies(recent)
        available = [t for t in REPLY_TEMPLATES if t not in recent]
    choice = random.choice(available)
    recent.append(choice)
    _save_recent_replies(recent)
    return choice


def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] [답글] {msg}\n")


def load_replied():
    if os.path.exists(REPLIED_FILE):
        with open(REPLIED_FILE) as f:
            return json.load(f)
    return []


def save_replied(replied):
    with open(REPLIED_FILE, "w") as f:
        json.dump(replied[-200:], f)  # 최근 200개만 유지


async def auto_reply():
    replied = load_replied()
    new_replies = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=SESSION_FILE,
            user_agent=MOBILE_UA,
            viewport={"width": 390, "height": 844},
        )
        page = await context.new_page()
        page.set_default_timeout(45000)

        # 내 프로필 방문 (재시도 로직)
        for attempt in range(3):
            try:
                await page.goto(
                    "https://www.threads.com/@calcmoney.kr",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                break
            except Exception as e:
                if attempt < 2:
                    log(f"프로필 로드 실패 (시도 {attempt+1}/3): {e}")
                    if not wait_for_network(max_wait=30, interval=5):
                        log("네트워크 복구 안 됨 - 재시도 대기")
                    await page.wait_for_timeout(5000)
                else:
                    log(f"프로필 로드 최종 실패: {e}")
                    await browser.close()
                    return
        await page.wait_for_timeout(3000)

        # 최근 게시물 링크 수집 (최대 5개)
        post_links = await page.evaluate("""
            () => {
                const links = [];
                const anchors = document.querySelectorAll('a[href*="/post/"]');
                for (const a of anchors) {
                    const href = a.getAttribute('href');
                    if (href && !links.includes(href)) {
                        links.push(href);
                        if (links.length >= 5) break;
                    }
                }
                return links;
            }
        """)

        if not post_links:
            log("게시물 못 찾음")
            await browser.close()
            return

        log(f"게시물 {len(post_links)}개 확인")

        # 각 게시물의 댓글 확인
        for post_href in post_links[:3]:  # 최근 3개만
            post_url = f"https://www.threads.com{post_href}"
            load_ok = False
            for attempt in range(3):
                try:
                    await page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
                    load_ok = True
                    break
                except Exception as e:
                    if attempt < 2:
                        log(f"게시물 로드 실패 (시도 {attempt+1}/3): {e}")
                        if not wait_for_network(max_wait=30, interval=5):
                            log("네트워크 복구 안 됨 - 재시도 대기")
                        await page.wait_for_timeout(5000)
                    else:
                        log(f"게시물 로드 최종 실패: {post_url}")
            if not load_ok:
                continue
            await page.wait_for_timeout(2000)

            # 댓글 영역에서 다른 사람의 댓글 찾기
            comments = await page.evaluate("""
                () => {
                    const results = [];
                    // 모든 텍스트 블록에서 댓글 추출
                    const blocks = document.querySelectorAll('[data-pressable-container="true"]');
                    for (const block of blocks) {
                        const text = block.textContent || '';
                        // 내 댓글은 제외
                        if (text.includes('calcmoney.kr') && text.length < 200) continue;
                        // 유저네임 + 댓글 내용 추출
                        const links = block.querySelectorAll('a[href^="/@"]');
                        for (const link of links) {
                            const username = link.getAttribute('href').replace('/@', '');
                            if (username !== 'calcmoney.kr' && username.length > 0) {
                                results.push({
                                    username: username,
                                    text: text.substring(0, 100),
                                    id: username + ':' + text.substring(0, 50)
                                });
                            }
                        }
                    }
                    return results.slice(0, 5);
                }
            """)

            for comment in comments:
                comment_id = comment["id"]
                if comment_id in replied:
                    continue

                # 댓글의 답글 버튼 찾기
                try:
                    reply_btns = await page.query_selector_all(
                        '[aria-label="댓글 달기"], [aria-label="Reply"]'
                    )
                    if not reply_btns:
                        continue

                    # 가장 가까운 답글 버튼 클릭
                    await reply_btns[0].click()
                    await page.wait_for_timeout(1500)

                    # 답글 입력
                    editors = await page.query_selector_all(
                        '[contenteditable="true"]'
                    )
                    if editors:
                        editor = editors[-1]
                        await editor.click()
                        reply_text = pick_reply()
                        await editor.type(reply_text, delay=30)
                        await page.wait_for_timeout(800)

                        # 게시
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
                            replied.append(comment_id)
                            new_replies += 1
                            log(f"답글 완료: @{comment['username']} → {reply_text}")
                            await page.wait_for_timeout(
                                random.randint(3000, 6000)
                            )
                        else:
                            log(f"답글 게시 실패: @{comment['username']}")

                except Exception as e:
                    log(f"답글 오류: {e}")
                    continue

                # 답글 간 간격
                if new_replies >= 5:
                    break

            if new_replies >= 5:
                break

        await browser.close()

    save_replied(replied)
    log(f"완료: 답글 {new_replies}개")


def main():
    if not wait_for_network():
        log("네트워크 연결 실패 - 종료")
        return
    if not os.path.exists(SESSION_FILE):
        log("세션 파일 없음")
        return
    asyncio.run(auto_reply())


if __name__ == "__main__":
    main()
