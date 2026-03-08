"""
Threads 자동 답글 - 내 게시물 댓글에 자동 응답
Playwright 기반 (API 토큰 없이 동작)
10분 간격 launchd로 실행
"""
import asyncio
import json
import os
import random
from datetime import datetime
from playwright.async_api import async_playwright

SESSION_FILE = "/tmp/threads_session.json"
REPLIED_FILE = "/tmp/threads_replied.json"
LOG_FILE = "/Users/yongseok/Desktop/쓰레드관리.txt"

MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

# 답글 템플릿 (카테고리별)
REPLY_TEMPLATES = [
    "고마워! 혹시 더 궁금한 거 있으면 물어봐",
    "맞아 진짜 많은 사람들이 모르고 넘어가더라",
    "이거 알면 확실히 다르지",
    "ㅋㅋ 다들 비슷한 상황이구나",
    "정보 필요하면 프로필 링크에 계산기 있어!",
    "공감해줘서 고마워 ㅎㅎ",
    "맞아 이거 진짜 중요한데 아는 사람이 별로 없어",
    "좋은 질문이야! 상황마다 다를 수 있는데 계산기로 확인해봐",
]


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
        page.set_default_timeout(15000)

        # 내 프로필 방문
        await page.goto(
            "https://www.threads.com/@calcmoney.kr",
            wait_until="domcontentloaded",
            timeout=30000,
        )
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
            await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
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
                        reply_text = random.choice(REPLY_TEMPLATES)
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
    if not os.path.exists(SESSION_FILE):
        log("세션 파일 없음")
        return
    asyncio.run(auto_reply())


if __name__ == "__main__":
    main()
