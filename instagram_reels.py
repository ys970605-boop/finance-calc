"""
Instagram @calcmoney.kr 릴스 자동화
- Pillow로 슬라이드 이미지 생성
- FFmpeg로 15초 슬라이드쇼 영상 변환
- Playwright로 릴스 업로드
"""
import asyncio
import os
import random
import subprocess
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import async_playwright

SESSION_FILE = "/Users/yongseok/cursor/finance-calc/instagram_session.json"
THREADS_SESSION = "/tmp/threads_session.json"
LOG_FILE = "/Users/yongseok/Desktop/인스타관리.txt"
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
VIDEO_PATH = "/tmp/instagram_reel.mp4"

REELS_POSTS = [
    {
        "slides": [
            {"title": "연봉 4000만원",        "body": "실수령액 얼마인지 알아?"},
            {"title": "월 286만원",            "body": "세금 떼고 나면 이것밖에 안 남아"},
            {"title": "국민연금 4.5%",         "body": "건강보험 3.5% + 소득세 3%"},
            {"title": "매달 사라지는 돈",       "body": "월급의 15~20%"},
            {"title": "내 실수령액 계산",       "body": "calcmoney.kr"},
        ],
        "caption": "연봉 4000만원 실수령액 알아?\n\n세금 다 떼면 월 286만원밖에 안 남아\n\n내 실수령액 계산해봐 👇\ncalcmoney.kr\n\n#재테크 #실수령액 #월급 #직장인",
    },
    {
        "slides": [
            {"title": "9억 아파트",            "body": "세금이 얼마인지 알아?"},
            {"title": "취득세 2700만원",       "body": "집값의 3%가 그냥 사라짐"},
            {"title": "지방교육세 포함",        "body": "총 3240만원"},
            {"title": "2주택이면",             "body": "취득세율 8%로 폭탄"},
            {"title": "미리 계산해봐",         "body": "calcmoney.kr"},
        ],
        "caption": "9억 아파트 살 때 세금만 3240만원\n\n이거 모르고 샀다가 충격받는 사람 많아\n\n취득세 미리 계산해봐 👇\ncalcmoney.kr\n\n#부동산 #취득세 #아파트 #내집마련",
    },
    {
        "slides": [
            {"title": "3억 대출 30년",         "body": "이자 총 얼마인지 알아?"},
            {"title": "이자만 2억 1천만원",    "body": "원금보다 이자가 더 많아"},
            {"title": "금리 1% 차이",          "body": "30년간 6000만원 차이"},
            {"title": "지금 금리 확인하고",    "body": "갈아타기 고려해봐"},
            {"title": "대출이자 계산",         "body": "calcmoney.kr"},
        ],
        "caption": "3억 대출 30년이면 이자만 2억 1천만원\n\n금리 1% 차이가 30년 동안 6000만원\n\n내 대출이자 계산해봐 👇\ncalcmoney.kr\n\n#대출 #주담대 #금리 #재테크",
    },
]

W, H = 1080, 1920  # 9:16 세로 비율 (릴스)
BG = (15, 15, 25)
ACCENT = (255, 200, 0)
TEXT_COLOR = (240, 240, 240)
DIM = (150, 150, 170)


def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def load_font(size, index=4):
    try:
        return ImageFont.truetype(FONT_PATH, size, index=index)
    except:
        return ImageFont.load_default()


def make_slide(title: str, body: str, idx: int, total: int) -> str:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # 상단 브랜드
    draw.text((80, 100), "@calcmoney.kr", font=load_font(40), fill=ACCENT)
    draw.rectangle([(80, 150), (200, 158)], fill=ACCENT)

    # 슬라이드 번호
    draw.text((W - 150, 100), f"{idx+1}/{total}", font=load_font(36), fill=DIM)

    # 메인 타이틀 (중앙)
    title_font = load_font(100 if len(title) <= 8 else 80)
    y = H // 2 - 200
    for line in title.split("\n"):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        x = (W - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=title_font, fill=TEXT_COLOR)
        y += bbox[3] - bbox[1] + 20

    # 구분선
    draw.rectangle([(100, H // 2 + 20), (W - 100, H // 2 + 24)], fill=(60, 60, 80))

    # 서브 텍스트
    body_font = load_font(60)
    y2 = H // 2 + 60
    for line in body.split("\n"):
        bbox = draw.textbbox((0, 0), line, font=body_font)
        x = (W - (bbox[2] - bbox[0])) // 2
        color = ACCENT if "finance" in line else TEXT_COLOR
        draw.text((x, y2), line, font=body_font, fill=color)
        y2 += bbox[3] - bbox[1] + 20

    # 하단 스와이프 힌트
    if idx < total - 1:
        draw.text((W // 2 - 80, H - 150), "다음 →", font=load_font(40), fill=DIM)

    path = f"/tmp/reel_slide_{idx}.png"
    img.save(path, "PNG")
    return path


def make_video(slide_paths: list, output: str, duration_per_slide: float = 3.0) -> bool:
    """FFmpeg로 슬라이드 → 15초 영상"""
    try:
        # 각 슬라이드를 duration_per_slide초씩
        filter_parts = []
        inputs = []
        for i, path in enumerate(slide_paths):
            inputs += ["-loop", "1", "-t", str(duration_per_slide), "-i", path]
            filter_parts.append(f"[{i}:v]scale={W}:{H},setsar=1[v{i}]")

        concat = "".join(f"[v{i}]" for i in range(len(slide_paths)))
        filter_complex = ";".join(filter_parts) + f";{concat}concat=n={len(slide_paths)}:v=1:a=0[out]"

        cmd = [
            "/opt/homebrew/bin/ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            output
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            log(f"영상 생성 완료: {output}")
            return True
        else:
            log(f"FFmpeg 오류: {result.stderr[-200:]}")
            return False
    except Exception as e:
        log(f"영상 생성 오류: {e}")
        return False


async def is_logged_in(page) -> bool:
    """프로필 선택 다이얼로그가 아닌 진짜 로그인 상태인지 확인"""
    arias = []
    for el in await page.query_selector_all('[aria-label]'):
        aria = await el.get_attribute("aria-label")
        if aria:
            arias.append(aria.lower())
    combined = " ".join(arias)
    return any(kw in combined for kw in ["new post", "새 게시물", "home", "홈", "search", "탐색"])


async def refresh_session():
    import json
    with open(THREADS_SESSION) as f:
        data = json.load(f)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                ctx = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                )
                await ctx.add_cookies(data["cookies"])
                page = await ctx.new_page()
                page.set_default_timeout(45000)
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(4000)
                if await is_logged_in(page):
                    await ctx.storage_state(path=SESSION_FILE)
                    log("세션 갱신 완료")
                else:
                    log("세션 갱신 실패 - 직접 로그인 필요: /tmp/instagram_login_once.py 실행")
                await browser.close()
                return
        except Exception as e:
            log(f"세션 갱신 네트워크 오류 (시도 {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
            else:
                log("세션 갱신 최대 재시도 초과")


async def upload_reel(video_path: str, caption: str):
    if not os.path.exists(SESSION_FILE):
        await refresh_session()

    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await _do_upload_reel(video_path, caption)
        except Exception as e:
            log(f"릴스 업로드 네트워크 오류 (시도 {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
            else:
                log("릴스 업로드 최대 재시도 초과")
                return False


async def _do_upload_reel(video_path: str, caption: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            storage_state=SESSION_FILE,
            viewport={"width": 1280, "height": 900},
        )
        page = await ctx.new_page()
        page.set_default_timeout(45000)
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)

        if "accounts/login" in page.url or not await is_logged_in(page):
            await browser.close()
            log("세션 만료 - /tmp/instagram_login_once.py 실행 필요")
            return False

        # 게시물 만들기 버튼 (여러 방식으로 시도)
        create_btn = None
        for selector in [
            '[aria-label="New post"]',
            '[aria-label="새 게시물"]',
            '[aria-label="Create"]',
            '[aria-label="만들기"]',
        ]:
            try:
                el = await page.wait_for_selector(selector, timeout=3000)
                if el:
                    create_btn = el
                    break
            except:
                continue

        if not create_btn:
            for btn in await page.query_selector_all('[role="link"], [role="button"], svg'):
                aria = (await btn.get_attribute("aria-label") or "").lower()
                if any(kw in aria for kw in ["new post", "새 게시물", "create", "만들기"]):
                    create_btn = btn
                    break

        if not create_btn:
            log("게시물 버튼 못 찾음")
            await page.screenshot(path="/tmp/reel_debug.png")
            await browser.close()
            return False

        await create_btn.click()
        await page.wait_for_timeout(2000)

        # 파일 업로드
        file_input = await page.query_selector('input[type="file"]')
        if not file_input:
            log("파일 입력 못 찾음")
            await browser.close()
            return False

        await file_input.set_input_files(video_path)
        await page.wait_for_timeout(5000)

        # OK 버튼 (영상 자르기 스킵)
        for text in ["OK", "확인", "괜찮아요"]:
            try:
                btn = page.locator(f'button:has-text("{text}")')
                if await btn.count() > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(2000)
                    break
            except:
                pass

        # Next 버튼 반복
        for _ in range(3):
            for text in ["다음", "Next"]:
                try:
                    btn = page.locator(f'button:has-text("{text}"), div[role="button"]:has-text("{text}")')
                    if await btn.count() > 0:
                        await btn.first.click()
                        await page.wait_for_timeout(2500)
                        break
                except:
                    pass

        # 캡션 입력
        caption_box = await page.query_selector('[aria-label="Write a caption..."], [aria-label="캡션 입력..."], [contenteditable="true"]')
        if caption_box:
            await caption_box.click()
            await caption_box.type(caption, delay=15)
            await page.wait_for_timeout(1000)

        # 공유
        for text in ["공유", "Share"]:
            try:
                btn = page.locator(f'button:has-text("{text}"), div[role="button"]:has-text("{text}")')
                if await btn.count() > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(8000)
                    log(f"릴스 업로드 완료: {caption[:30]}...")
                    await browser.close()
                    return True
            except:
                pass

        log("공유 버튼 못 찾음")
        await page.screenshot(path="/tmp/reel_debug.png")
        await browser.close()
        return False


async def main():
    post = random.choice(REELS_POSTS)
    slides = post["slides"]

    # 슬라이드 이미지 생성
    slide_paths = []
    for i, s in enumerate(slides):
        path = make_slide(s["title"], s["body"], i, len(slides))
        slide_paths.append(path)
    log(f"슬라이드 {len(slide_paths)}장 생성")

    # 영상 변환
    ok = make_video(slide_paths, VIDEO_PATH)
    if not ok:
        log("영상 생성 실패")
        return

    # 업로드
    await upload_reel(VIDEO_PATH, post["caption"])


if __name__ == "__main__":
    asyncio.run(main())
