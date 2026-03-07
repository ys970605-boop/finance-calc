"""
Threads 자동 포스팅 - 매일 1회 실행
본문: 링크 없음 / 첫 댓글: 링크 삽입 (알고리즘 최적화)
launchd에 의해 호출됨
"""
import asyncio
import json
import os
import random
from datetime import datetime
from playwright.async_api import async_playwright

SESSION_FILE = "/tmp/threads_session.json"
POSTED_FILE = "/tmp/threads_posted.json"

# (본문, 댓글링크) 튜플
POSTS = [
    (
        "💰 연봉 4000만원 실수령액 알아?\n\n세금 다 떼면 월 286만원\n생각보다 훨씬 적지?\n\n너희 연봉 실수령액은 얼마야? 댓글에 써봐 👇",
        "▶ 연봉 실수령액 계산기 → finance-calc-kr.netlify.app/salary.html"
    ),
    (
        "🏠 9억 아파트 취득세 얼마인지 알아?\n\n취득세만 2700만원\n지방교육세까지 합치면 3240만원\n\n집 살 때 이거 모르고 샀다가 충격받은 사람 있어? 👇",
        "▶ 취득세 계산기 → finance-calc-kr.netlify.app/acquisition-tax.html"
    ),
    (
        "📋 알바하는데 주휴수당 못 받고 있어?\n\n주 15시간 이상이면 무조건 받아야 해\n시급 10000원 × 주 40시간이면 주 8만원 추가\n\n지금 받고 있어? 아니면 못 받고 있어? 👇",
        "▶ 주휴수당 계산기 → finance-calc-kr.netlify.app/weekly-holiday.html"
    ),
    (
        "💼 10년 다니면 퇴직금 얼마나 될까?\n\n월급 300만원 × 10년 = 3000만원\n근데 IRP로 받으면 세금 아낄 수 있어\n\n퇴직금 얼마 모았어? 댓글에 공유해봐 👇",
        "▶ 퇴직금 계산기 → finance-calc-kr.netlify.app/severance.html"
    ),
    (
        "🏡 전세 3억을 월세로 바꾸면 얼마야?\n\n집주인이 터무니없는 금액 부르는 경우 많아\n법정 전환율 연 5% 기준으로 따져봐야 해\n\n전세 vs 월세 어떤 게 나아? 👇",
        "▶ 전월세 전환 계산기 → finance-calc-kr.netlify.app/jeonse-monthly.html"
    ),
    (
        "📊 청약 가점 몇 점인지 알아?\n\n무주택 기간 + 부양가족 수 + 청약통장 기간\n최고 84점 만점\n\n내 점수 계산해봤어? 몇 점 나왔어? 👇",
        "▶ 청약 가점 계산기 → finance-calc-kr.netlify.app/subscription.html"
    ),
    (
        "💸 집 팔 때 양도세 얼마 나오는지 알아?\n\n2년 보유 + 2년 거주하면 12억까지 비과세\n조건 안 맞으면 수천만원 세금 폭탄\n\n이거 몰랐던 사람 있어? 솔직히 말해봐 👇",
        "▶ 양도소득세 계산기 → finance-calc-kr.netlify.app/capital-gains.html"
    ),
    (
        "🏦 3억 대출 30년 갚으면 이자 총 얼마?\n\n금리 4%면 이자만 2억 1500만원\n금리 1% 차이가 30년간 7000만원 차이\n\n지금 대출 금리 얼마야? 댓글에 써봐 👇",
        "▶ 대출이자 계산기 → finance-calc-kr.netlify.app/loan.html"
    ),
    (
        "💡 연봉 협상할 때 이 실수 하지 마\n\n회사가 제시하는 연봉 그대로 받으면 안 돼\n세금 떼고 나면 생각보다 훨씬 적거든\n\n연봉 협상 성공한 사람 있어? 비결 공유해줘 👇",
        "▶ 연봉 실수령액 계산기 → finance-calc-kr.netlify.app/salary.html"
    ),
    (
        "🏠 생애 최초 주택 구입하면 취득세 감면돼\n\n12억 이하 주택 → 취득세 200만원 한도 감면\n몰라서 못 받는 사람 엄청 많아\n\n이거 알고 있었어? 아니면 처음 알았어? 👇",
        "▶ 취득세 계산기 → finance-calc-kr.netlify.app/acquisition-tax.html"
    ),
    (
        "📋 퇴직금 받을 때 세금 아끼는 법\n\nIRP 계좌로 받고 55세 이후 연금으로 수령\n일시금 vs 연금 세금 차이가 수백만원\n\n퇴직금 어떻게 받을 계획이야? 👇",
        "▶ 퇴직금 계산기 → finance-calc-kr.netlify.app/severance.html"
    ),
    (
        "💰 월급 300만원인데 저축 얼마 해야 해?\n\n수입의 30~50% 권장이라는데\n고정지출 빼면 현실적으로 얼마나 가능해?\n\n너희는 월급의 몇 % 저축해? 👇",
        "▶ 연봉 실수령액 계산기 → finance-calc-kr.netlify.app/salary.html"
    ),
    (
        "🏡 전세 사기 당하지 않으려면\n\n전세금이 집값의 70% 넘으면 위험\n전입신고 + 확정일자 필수\n\n주변에 전세 사기 피해 본 사람 있어? 👇",
        "▶ 전월세 전환 계산기 → finance-calc-kr.netlify.app/jeonse-monthly.html"
    ),
    (
        "📊 무주택 10년이면 청약 가점 몇 점?\n\n무주택 10년 = 32점\n부양가족 4명 = 25점\n청약통장 15년 = 17점 → 총 74점\n\n이 정도면 어느 지역 당첨 가능할까? 👇",
        "▶ 청약 가점 계산기 → finance-calc-kr.netlify.app/subscription.html"
    ),
    (
        "💸 부모님한테 1억 받으면 증여세 얼마야?\n\n10년 내 5000만원 초과분에 세금\n1억이면 세금 500만원\n\n증여 받아본 사람 있어? 세금 냈어? 👇",
        "▶ 전체 금융 계산기 → finance-calc-kr.netlify.app"
    ),
]

async def post_thread(body, comment):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=SESSION_FILE)
        page = await context.new_page()

        await page.goto("https://www.threads.com/")
        await page.wait_for_timeout(4000)

        # 입력창 클릭 - aria-label 방식 (가장 안정적)
        clicked = False
        for selector in ['[aria-label*="Create"]', '[aria-label*="만들기"]']:
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    await el.click()
                    clicked = True
                    break
            except:
                continue

        if not clicked:
            for placeholder in ["새로운 소식이 있나요?", "What's new?"]:
                try:
                    el = await page.wait_for_selector(f'text={placeholder}', timeout=3000)
                    await el.click()
                    clicked = True
                    break
                except:
                    continue

        await page.wait_for_timeout(2000)

        # 본문 입력
        editors = await page.query_selector_all('[contenteditable="true"]')
        if not editors:
            await browser.close()
            return False

        editor = editors[-1]
        await editor.click()
        await page.wait_for_timeout(500)
        await editor.type(body, delay=30)
        await page.wait_for_timeout(1000)

        # 게시 - y좌표 가장 아래 버튼 클릭 (composer 안의 버튼)
        posted = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('div[role="button"], button');
                let best = null, bestY = -1;
                for (const btn of btns) {
                    const txt = btn.textContent.trim();
                    if (txt === '게시' || txt === 'Post') {
                        const rect = btn.getBoundingClientRect();
                        if (rect.width > 0 && rect.top > bestY) {
                            best = btn; bestY = rect.top;
                        }
                    }
                }
                if (best) { best.click(); return true; }
                return false;
            }
        """)
        await page.wait_for_timeout(5000)

        if not posted:
            await browser.close()
            return False

        # 방금 올린 글에 댓글 달기
        try:
            # 내 프로필로 이동해서 최신 글 찾기
            await page.goto("https://www.threads.com/@calcmoney.kr")
            await page.wait_for_timeout(3000)

            # 첫 번째 글의 댓글 버튼 클릭
            comment_btn = await page.wait_for_selector('[aria-label="댓글 달기"], [aria-label="Reply"]', timeout=5000)
            await comment_btn.click()
            await page.wait_for_timeout(2000)

            # 댓글 입력
            reply_editors = await page.query_selector_all('[contenteditable="true"]')
            if reply_editors:
                reply_editor = reply_editors[-1]
                await reply_editor.click()
                await reply_editor.type(comment, delay=30)
                await page.wait_for_timeout(1000)

                # 댓글 게시
                await page.evaluate("""
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
                await page.wait_for_timeout(2000)
                print(f"[{datetime.now()}] 댓글(링크) 추가 완료")
        except Exception as e:
            print(f"댓글 추가 실패 (무시): {e}")

        await browser.close()
        return True

def main():
    posted_list = json.load(open(POSTED_FILE)) if os.path.exists(POSTED_FILE) else []
    remaining = [p for p in POSTS if p[0] not in posted_list]

    if not remaining:
        print(f"[{datetime.now()}] 순환 초기화")
        posted_list = []
        remaining = POSTS

    body, comment = random.choice(remaining)
    success = asyncio.run(post_thread(body, comment))

    if success:
        posted_list.append(body)
        with open(POSTED_FILE, "w") as f:
            json.dump(posted_list, f)
        print(f"[{datetime.now()}] Threads 게시 완료")
    else:
        print(f"[{datetime.now()}] Threads 게시 실패")

if __name__ == "__main__":
    main()
