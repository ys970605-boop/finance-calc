"""
Instagram @calcmoney.kr 캐러셀 자동 포스팅
- 캐러셀 (3~4장): 훅 → 설명 → CTA
- Threads 쿠키로 세션 갱신 (별도 로그인 불필요)
"""
import asyncio
import json
import os
import random
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import async_playwright

SESSION_FILE = "/Users/yongseok/cursor/finance-calc/instagram_session.json"
THREADS_SESSION = "/tmp/threads_session.json"
POSTED_FILE = "/tmp/instagram_posted.json"
LOG_FILE = "/Users/yongseok/Desktop/인스타관리.txt"
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

# 캐러셀 포스트: [슬라이드 리스트, 캡션]
# 슬라이드: {"type": "hook"|"info"|"cta", "title": str, "body": str}
CAROUSEL_POSTS = [
    {
        "slides": [
            {"type": "hook",  "title": "연봉 4000만원인데\n왜 월급이 286만원?",         "body": "이 질문 해본 적 있어?\n세금 때문이야"},
            {"type": "info",  "title": "매달 빠져나가는 세금",                            "body": "국민연금  4.5%\n건강보험  3.5%\n고용보험  0.9%\n소득세    약 3~5%\n\n합계: 월급의 15~20%"},
            {"type": "info",  "title": "연봉별 실수령액",                                 "body": "3000만원 → 월 216만원\n4000만원 → 월 286만원\n5000만원 → 월 351만원\n6000만원 → 월 412만원"},
            {"type": "cta",   "title": "내 실수령액\n직접 계산해봐",                      "body": "finance-calc-kr.netlify.app\n\n연봉 입력하면 바로 나옴"},
        ],
        "caption": "연봉 4000만원인데 왜 월급이 286만원일까?\n\n세금 종류별로 다 뜯기고 나면 이것밖에 안 남아\n\n내 연봉 실수령액 얼마야? 댓글에 써봐\n\n#재테크 #실수령액 #월급 #연봉 #직장인",
    },
    {
        "slides": [
            {"type": "hook",  "title": "9억 아파트 살 때\n세금만 3240만원",              "body": "집값의 3.6%가 그냥 사라짐"},
            {"type": "info",  "title": "취득세 세율",                                     "body": "1주택 6억 이하  →  1%\n1주택 9억 이하  →  1~3%\n1주택 9억 초과  →  3%\n2주택              →  8%\n3주택 이상        →  12%"},
            {"type": "info",  "title": "생애최초 혜택",                                   "body": "생애최초 주택 구입 시\n취득세 최대 200만원 감면\n\n조건: 소득·가격 기준 충족"},
            {"type": "cta",   "title": "취득세 얼마인지\n미리 계산해봐",                  "body": "finance-calc-kr.netlify.app\n\n주소 없이도 금액만 입력 가능"},
        ],
        "caption": "9억 아파트 사면 취득세만 2700만원\n지방교육세 합치면 3240만원\n\n집 살 때 이거 모르면 진짜 충격\n\n생애최초면 감면받을 수 있어 꼭 확인해\n\n#부동산 #취득세 #아파트 #내집마련 #부동산세금",
    },
    {
        "slides": [
            {"type": "hook",  "title": "3억 대출 30년\n이자만 2억 1천만원",              "body": "원금보다 이자가 더 많다"},
            {"type": "info",  "title": "금리별 총이자 비교\n(3억, 30년)",                 "body": "금리 3%  →  1억 5,500만원\n금리 4%  →  2억 1,500만원\n금리 5%  →  2억 7,900만원\n\n1% 차이 = 6,000만원 차이"},
            {"type": "info",  "title": "이자 줄이는 법",                                  "body": "① 대출 갈아타기 (금리 비교)\n② 중도상환 (원금 미리 갚기)\n③ 거치기간 없애기\n④ 혼합형 → 변동형 시점 선택"},
            {"type": "cta",   "title": "내 대출이자\n얼마인지 계산해봐",                  "body": "finance-calc-kr.netlify.app\n\n원금·금리·기간 입력하면 바로"},
        ],
        "caption": "3억 대출 30년 갚으면 이자만 2억 1500만원\n\n금리 1% 차이가 30년간 6000만원 차이야\n\n지금 대출 금리 얼마야? 댓글에 써봐\n\n#대출 #주택담보대출 #재테크 #금리 #내집마련",
    },
    {
        "slides": [
            {"type": "hook",  "title": "청약 가점 낮으면\n아파트 못 산다",                "body": "최고 84점 만점\n평균 당첨자 60점대"},
            {"type": "info",  "title": "가점 계산법",                                     "body": "무주택 기간   최대 32점\n부양가족 수   최대 35점\n청약통장 기간 최대 17점\n\n합계 84점 만점"},
            {"type": "info",  "title": "가점 높이는 전략",                                "body": "① 지금 당장 청약통장 개설\n② 무주택 유지 (주택 취득 X)\n③ 배우자·자녀 부양가족 등록\n④ 납입 회차 꾸준히 쌓기"},
            {"type": "cta",   "title": "내 청약 가점\n계산해봐",                          "body": "finance-calc-kr.netlify.app\n\n항목별로 입력하면 바로 나옴"},
        ],
        "caption": "청약 가점 몇 점인지 알아?\n\n84점 만점인데 당첨자 평균이 60점대야\n지금부터 관리 안 하면 진짜 늦어\n\n내 가점 계산해봤어? 몇 점 나왔어?\n\n#청약 #청약가점 #아파트 #내집마련 #청약통장",
    },
    {
        "slides": [
            {"type": "hook",  "title": "10년 다녔는데\n퇴직금 3000만원?",                      "body": "월급 300만원 기준\n생각보다 적다"},
            {"type": "info",  "title": "퇴직금 계산법",                                        "body": "1일 평균임금 × 30일\n× 근속연수\n\n월급 300만원 × 10년\n= 약 3,000만원"},
            {"type": "info",  "title": "퇴직금 세금 아끼는 법",                                "body": "① IRP 계좌로 수령\n② 55세 이후 연금 수령\n③ 일시금 대비 세금 30~40% 절감\n④ 퇴직소득세 공제 활용"},
            {"type": "cta",   "title": "내 퇴직금\n얼마인지 계산해봐",                          "body": "finance-calc-kr.netlify.app\n\n월급·근속연수 입력하면 바로"},
        ],
        "caption": "10년 다녔는데 퇴직금 3000만원밖에 안 된다고?\n\nIRP로 받으면 세금 수백만원 아낄 수 있어\n모르면 그냥 날리는 돈이야\n\n저장해두고 퇴직할 때 꺼내봐\n\n#퇴직금 #재테크 #직장인 #IRP #연금",
    },
    {
        "slides": [
            {"type": "hook",  "title": "전세 3억을\n월세로 바꾸면?",                            "body": "집주인이 부르는 금액\n그대로 내면 손해"},
            {"type": "info",  "title": "법정 전환율 기준",                                     "body": "2026년 법정 전환율: 연 5%\n\n전세 3억 → 월세 전환 시\n보증금 0원 기준 월 125만원\n보증금 1억 기준 월 83만원"},
            {"type": "info",  "title": "이렇게 따져봐",                                        "body": "① 집주인 제시 금액 확인\n② 법정 전환율로 계산\n③ 차이 나면 협상 근거로 사용\n④ 주변 시세도 함께 비교"},
            {"type": "cta",   "title": "전월세 전환\n직접 계산해봐",                            "body": "finance-calc-kr.netlify.app\n\n전세금·보증금 입력하면 바로"},
        ],
        "caption": "전세를 월세로 바꿀 때 집주인 말만 믿으면 안 돼\n\n법정 전환율 기준으로 직접 계산해봐야 해\n이거 모르면 매달 돈 더 내는 거야\n\n이사 앞두고 있으면 저장해둬\n\n#전세 #월세 #전월세전환 #부동산 #자취",
    },
    {
        "slides": [
            {"type": "hook",  "title": "알바하는데\n주휴수당 못 받고 있어?",                    "body": "주 15시간 이상이면\n무조건 받아야 해"},
            {"type": "info",  "title": "주휴수당 계산법",                                      "body": "주 근무시간 ÷ 5 × 시급\n\n시급 10,320원 × 주 40시간\n= 주휴수당 주 82,560원\n= 월 약 33만원 추가"},
            {"type": "info",  "title": "이런 경우 해당돼",                                     "body": "① 주 15시간 이상 근무\n② 정해진 근무일 개근\n③ 아르바이트도 해당\n④ 안 주면 노동청 신고 가능"},
            {"type": "cta",   "title": "내 주휴수당\n계산해봐",                                 "body": "finance-calc-kr.netlify.app\n\n시급·시간 입력하면 바로"},
        ],
        "caption": "알바비에 주휴수당 안 들어있으면 불법이야\n\n주 15시간 이상이면 무조건 받아야 하는 돈\n월 33만원 차이인데 모르고 넘어가는 사람 많아\n\n알바하는 친구한테 보내줘\n\n#주휴수당 #알바 #시급 #최저시급 #노동법",
    },
    {
        "slides": [
            {"type": "hook",  "title": "집 팔았는데\n세금이 수천만원?",                         "body": "양도소득세\n모르면 폭탄 맞는다"},
            {"type": "info",  "title": "비과세 조건",                                          "body": "1세대 1주택\n2년 보유 + 2년 거주\n→ 12억까지 비과세\n\n조건 하나라도 안 맞으면\n세금 수천만원"},
            {"type": "info",  "title": "양도세 줄이는 법",                                     "body": "① 2년 거주 요건 채우기\n② 장기보유 특별공제 활용\n③ 필요경비 영수증 챙기기\n④ 양도 시기 조절 (연도 분산)"},
            {"type": "cta",   "title": "양도세 얼마인지\n미리 계산해봐",                        "body": "finance-calc-kr.netlify.app\n\n매입가·매도가 입력하면 바로"},
        ],
        "caption": "집 팔기 전에 양도세부터 계산해봐\n\n조건 안 맞으면 수천만원 세금 나와\n2년 보유+거주 비과세 조건 꼭 확인해야 해\n\n집 살 계획 있으면 저장해둬\n\n#양도소득세 #부동산 #부동산세금 #1주택 #비과세",
    },
    {
        "slides": [
            {"type": "hook",  "title": "부모님한테 1억 받으면\n세금 500만원",                   "body": "증여세 모르면\n가족끼리 돈 주고받기 무섭다"},
            {"type": "info",  "title": "증여 공제 한도",                                       "body": "성인 자녀 ← 부모: 5,000만원\n미성년 자녀 ← 부모: 2,000만원\n배우자 간: 6억원\n\n10년 합산 기준"},
            {"type": "info",  "title": "증여세율",                                             "body": "1억 이하    10%\n5억 이하    20%\n10억 이하   30%\n30억 이하   40%\n30억 초과   50%\n\n공제 초과분에 적용"},
            {"type": "cta",   "title": "증여세 얼마인지\n계산해봐",                             "body": "finance-calc-kr.netlify.app\n\n금액 입력하면 바로 나옴"},
        ],
        "caption": "부모님한테 돈 받을 때 증여세 안 내면 가산세까지 붙어\n\n10년간 5000만원까지는 비과세\n그 이상은 신고해야 해\n\n가족한테 돈 받을 일 있으면 저장\n\n#증여세 #재테크 #부모님 #세금 #절세",
    },
    {
        "slides": [
            {"type": "hook",  "title": "ISA 계좌\n아직도 안 만들었어?",                         "body": "세금 없이 투자하는\n합법적인 방법"},
            {"type": "info",  "title": "ISA 핵심 정리",                                        "body": "납입 한도: 연 2,000만원\n의무 보유: 3년\n\n비과세 한도:\n일반형 200만원\n서민형 400만원\n\n초과분도 9.9% 분리과세"},
            {"type": "info",  "title": "ISA vs 일반 계좌",                                     "body": "배당 받을 때\n일반: 15.4% 세금\nISA: 비과세 (한도 내)\n\n3년 후 해지하면\n세금 아낀 만큼 그대로 수익"},
            {"type": "cta",   "title": "금융 계산기로\n내 절세 효과 확인",                      "body": "finance-calc-kr.netlify.app\n\n다양한 금융 계산기 모음"},
        ],
        "caption": "ISA 계좌 안 만들면 배당세 15.4% 그냥 내는 거야\n\n3년만 넣어두면 수익에 세금 없음\n직장인이면 그냥 만들어두는 게 이득\n\n투자하는 친구한테 보내줘\n\n#ISA #재테크 #절세 #투자 #배당",
    },
]

BG_COLORS = {
    "hook": (15, 15, 25),
    "info": (20, 20, 35),
    "cta":  (10, 10, 20),
}
ACCENT = (255, 200, 0)
TEXT_COLOR = (240, 240, 240)
DIM_COLOR = (160, 160, 180)
W, H = 1080, 1080


def load_font(size, index=4):
    try:
        return ImageFont.truetype(FONT_PATH, size, index=index)
    except:
        return ImageFont.load_default()


def draw_slide(slide: dict, idx: int, total: int) -> str:
    img = Image.new("RGB", (W, H), BG_COLORS.get(slide["type"], (15, 15, 25)))
    draw = ImageDraw.Draw(img)

    # 상단 액센트
    draw.rectangle([(80, 100), (160, 108)], fill=ACCENT)
    draw.text((80, 60), "@calcmoney.kr", font=load_font(28), fill=ACCENT)

    # 슬라이드 번호
    num_text = f"{idx + 1} / {total}"
    draw.text((W - 120, 60), num_text, font=load_font(26), fill=DIM_COLOR)

    # 타이틀
    title = slide["title"]
    title_font = load_font(68 if len(title) < 16 else 56)
    y = 200
    for line in title.split("\n"):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        x = (W - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=title_font, fill=TEXT_COLOR)
        y += bbox[3] - bbox[1] + 16

    # 구분선
    y += 30
    draw.rectangle([(80, y), (W - 80, y + 2)], fill=(60, 60, 80))
    y += 40

    # 본문
    body = slide["body"]
    body_font = load_font(40)
    for line in body.split("\n"):
        if not line.strip():
            y += 20
            continue
        bbox = draw.textbbox((0, 0), line, font=body_font)
        x = (W - (bbox[2] - bbox[0])) // 2
        color = ACCENT if slide["type"] == "cta" and "finance" in line else TEXT_COLOR
        draw.text((x, y), line, font=body_font, fill=color)
        y += bbox[3] - bbox[1] + 18

    # CTA 슬라이드 하단 화살표 힌트
    if slide["type"] != "cta" and idx < total - 1:
        draw.text((W // 2 - 30, H - 80), "→ 다음", font=load_font(28), fill=DIM_COLOR)

    path = f"/tmp/insta_slide_{idx}.png"
    img.save(path, "PNG")
    return path


def make_carousel(slides: list) -> list:
    paths = []
    for i, slide in enumerate(slides):
        paths.append(draw_slide(slide, i, len(slides)))
    return paths


def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


async def refresh_session():
    import json
    with open(THREADS_SESSION) as f:
        data = json.load(f)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(data["cookies"])
        page = await context.new_page()
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        if "accounts/login" not in page.url:
            await context.storage_state(path=SESSION_FILE)
            log("세션 갱신 완료")
        await browser.close()


async def post_carousel(img_paths: list, caption: str):
    if not os.path.exists(SESSION_FILE):
        await refresh_session()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=SESSION_FILE,
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        # 세션 만료 판단: 실제 login 페이지 리다이렉트만 체크
        current_url = page.url
        is_login_page = "accounts/login" in current_url or "accounts/onetap" in current_url
        if is_login_page:
            # 2차 확인: login form 존재 여부
            login_form = await page.query_selector('input[name="username"], #loginForm, [aria-label="Phone number, username, or email"]')
            if login_form:
                log("세션 만료 - login 페이지 리다이렉트 확인, 갱신 후 재시도")
                await browser.close()
                await refresh_session()
                await post_carousel(img_paths, caption)
                return
            else:
                log("login URL 감지되었으나 login form 없음 - 세션 유효로 판단, 메인으로 이동")
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

        # 게시물 만들기 버튼 (2026 Instagram UI selectors)
        create_btn = None
        create_selectors = [
            '[aria-label="New post"]',
            '[aria-label="새 게시물"]',
            '[aria-label="새로운 게시물"]',
            '[aria-label="Create"]',
            '[aria-label="만들기"]',
            'a[href="/create/style/"]',
            'a[href="/create/select/"]',
            'svg[aria-label="New post"]',
            'svg[aria-label="새 게시물"]',
            'svg[aria-label="새로운 게시물"]',
        ]
        for selector in create_selectors:
            try:
                el = await page.wait_for_selector(selector, timeout=3000)
                if el:
                    create_btn = el
                    break
            except:
                continue

        if not create_btn:
            # role 기반 재탐색
            for btn in await page.query_selector_all('[role="link"], [role="button"], [role="menuitem"]'):
                aria = (await btn.get_attribute("aria-label") or "").lower()
                if any(k in aria for k in ["new post", "새 게시물", "새로운 게시물", "create", "만들기"]):
                    create_btn = btn
                    break

        if not create_btn:
            # 사이드바 nav 링크 중 create 관련 탐색
            for link in await page.query_selector_all('nav a, aside a'):
                href = (await link.get_attribute("href") or "")
                if "/create" in href:
                    create_btn = link
                    break

        if not create_btn:
            log("게시물 버튼 못 찾음")
            await page.screenshot(path="/tmp/insta_debug.png")
            await browser.close()
            return False

        await create_btn.click()
        await page.wait_for_timeout(3000)

        # 파일 업로드 (다중 파일 = 캐러셀)
        file_input = None
        file_input_selectors = [
            'input[type="file"]',
            'input[accept="image/jpeg,image/png,image/heic,image/heif,video/mp4,video/quicktime"]',
            'input[accept*="image"]',
            'form input[type="file"]',
        ]
        for attempt in range(3):
            for fselector in file_input_selectors:
                file_input = await page.query_selector(fselector)
                if file_input:
                    break
            if file_input:
                break
            # 다시 create 버튼 클릭 시도
            await page.wait_for_timeout(2000)
            try:
                for sel in create_selectors[:5]:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        await page.wait_for_timeout(2000)
                        break
            except:
                pass
            # "컴퓨터에서 선택" 버튼 클릭 시도
            try:
                select_btn = await page.query_selector('button:has-text("컴퓨터에서 선택"), button:has-text("Select from computer"), button:has-text("Select from device")')
                if select_btn:
                    await select_btn.click()
                    await page.wait_for_timeout(1500)
            except:
                pass
        if not file_input:
            log("파일 입력 못 찾음 - selector 불일치 (세션은 유효)")
            await page.screenshot(path="/tmp/insta_debug.png")
            await browser.close()
            return False

        await file_input.set_input_files(img_paths)
        await page.wait_for_timeout(4000)

        # Next 버튼 3번 (crop → filter → caption)
        for step in range(3):
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
        caption_box = await page.query_selector(
            '[aria-label="Write a caption..."], [aria-label="캡션 입력..."], [contenteditable="true"]'
        )
        if caption_box:
            await caption_box.click()
            await caption_box.type(caption, delay=15)
            await page.wait_for_timeout(1000)

        # 공유 버튼
        for text in ["공유", "Share"]:
            try:
                btn = page.locator(f'button:has-text("{text}"), div[role="button"]:has-text("{text}")')
                if await btn.count() > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(5000)
                    log(f"캐러셀 업로드 완료 ({len(img_paths)}장): {caption[:30]}...")
                    await browser.close()
                    return True
            except:
                pass

        log("공유 버튼 못 찾음")
        await page.screenshot(path="/tmp/insta_share_debug.png")
        await browser.close()
        return False


async def main():
    posted_list = json.load(open(POSTED_FILE)) if os.path.exists(POSTED_FILE) else []
    remaining = [p for p in CAROUSEL_POSTS if p["caption"] not in posted_list]

    if not remaining:
        log("순환 초기화")
        posted_list = []
        remaining = CAROUSEL_POSTS

    post = random.choice(remaining)
    img_paths = make_carousel(post["slides"])
    log(f"캐러셀 이미지 {len(img_paths)}장 생성")
    result = await post_carousel(img_paths, post["caption"])
    if result:
        posted_list.append(post["caption"])
        with open(POSTED_FILE, "w") as f:
            json.dump(posted_list, f)
    else:
        log("업로드 실패 - /tmp/insta_debug.png 확인")


if __name__ == "__main__":
    asyncio.run(main())
