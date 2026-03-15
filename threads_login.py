"""
Threads 수동 로그인 → 세션 저장
세션 만료 시 이 스크립트 실행: python3 threads_login.py

headless=False로 Chrome 열어서 직접 로그인 → 세션 자동 저장
"""
import asyncio
import json
import os
from playwright.async_api import async_playwright

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "threads-data")
os.makedirs(DATA_DIR, exist_ok=True)
SESSION_FILE = os.path.join(DATA_DIR, "threads_session.json")

MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"


async def login():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        # 기존 세션 있으면 로드
        if os.path.exists(SESSION_FILE):
            context = await browser.new_context(
                storage_state=SESSION_FILE,
                user_agent=MOBILE_UA,
                viewport={"width": 390, "height": 844},
            )
        else:
            context = await browser.new_context(
                user_agent=MOBILE_UA,
                viewport={"width": 390, "height": 844},
            )

        page = await context.new_page()
        await page.goto("https://www.threads.com/login", wait_until="domcontentloaded")

        print("=" * 50)
        print("브라우저에서 Instagram 계정으로 로그인하세요.")
        print("로그인 완료 후 이 터미널에서 Enter를 누르세요.")
        print("=" * 50)

        # Enter 대기
        await asyncio.get_event_loop().run_in_executor(None, input)

        # 로그인 확인
        url = page.url
        if "login" in url:
            print("아직 로그인 안 됨. 다시 시도하세요.")
            await browser.close()
            return False

        # 프로필 접근 테스트
        await page.goto(
            "https://www.threads.com/@calcmoney.kr",
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(3000)

        final_url = page.url
        if "login" in final_url:
            print("프로필 접근 실패 — 로그인 상태 확인 필요")
            await browser.close()
            return False

        # 세션 저장
        state = await context.storage_state()
        with open(SESSION_FILE, "w") as f:
            json.dump(state, f, indent=2)

        print(f"세션 저장 완료: {SESSION_FILE}")
        print(f"쿠키 수: {len(state.get('cookies', []))}")

        await browser.close()
        return True


if __name__ == "__main__":
    success = asyncio.run(login())
    if success:
        print("Threads 세션 재생성 완료. 자동화 정상 동작할 것.")
    else:
        print("로그인 실패. 다시 시도하세요.")
