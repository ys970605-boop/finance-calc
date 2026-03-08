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
        "💰 연봉 4000만원 실수령액 알아?\n\n세금 다 떼면 월 286만원\n생각보다 훨씬 적지?\n\n너희 연봉 실수령액은 얼마야? 댓글에 써봐 👇\n\n#재테크",
        "▶ 연봉 실수령액 계산기 → finance-calc-kr.netlify.app/salary.html"
    ),
    (
        "🏠 9억 아파트 취득세 얼마인지 알아?\n\n취득세만 2700만원\n지방교육세까지 합치면 3240만원\n\n집 살 때 이 비용 생각 안 하고 있었으면 꼭 계산해봐 👇\n\n#부동산",
        "▶ 취득세 계산기 → finance-calc-kr.netlify.app/acquisition-tax.html"
    ),
    (
        "📋 알바하는데 주휴수당 못 받고 있어?\n\n주 15시간 이상이면 무조건 받아야 해\n시급 10000원 × 주 40시간이면 주 8만원 추가\n\n지금 받고 있어? 아니면 못 받고 있어? 👇\n\n#월급",
        "▶ 주휴수당 계산기 → finance-calc-kr.netlify.app/weekly-holiday.html"
    ),
    (
        "💼 10년 다니면 퇴직금 얼마나 될까?\n\n월급 300만원 × 10년 = 3000만원\n근데 IRP로 받으면 세금 아낄 수 있어\n\n퇴직금 얼마 모았어? 댓글에 공유해봐 👇\n\n#재테크",
        "▶ 퇴직금 계산기 → finance-calc-kr.netlify.app/severance.html"
    ),
    (
        "🏡 전세 3억을 월세로 바꾸면 얼마야?\n\n집주인이 터무니없는 금액 부르는 경우 많아\n법정 전환율 연 5% 기준으로 따져봐야 해\n\n전세 vs 월세 어떤 게 나아? 👇\n\n#부동산",
        "▶ 전월세 전환 계산기 → finance-calc-kr.netlify.app/jeonse-monthly.html"
    ),
    (
        "📊 청약 가점 몇 점인지 알아?\n\n무주택 기간 + 부양가족 수 + 청약통장 기간\n최고 84점 만점\n\n내 점수 계산해봤어? 몇 점 나왔어? 👇\n\n#청약",
        "▶ 청약 가점 계산기 → finance-calc-kr.netlify.app/subscription.html"
    ),
    (
        "💸 집 팔 때 양도세 얼마 나오는지 알아?\n\n2년 보유 + 2년 거주하면 12억까지 비과세\n조건 안 맞으면 수천만원 세금 폭탄\n\n이거 몰랐던 사람 있어? 솔직히 말해봐 👇\n\n#부동산",
        "▶ 양도소득세 계산기 → finance-calc-kr.netlify.app/capital-gains.html"
    ),
    (
        "🏦 3억 대출 30년 갚으면 이자 총 얼마?\n\n금리 4%면 이자만 2억 1500만원\n금리 1% 차이가 30년간 7000만원 차이\n\n지금 대출 금리 얼마야? 댓글에 써봐 👇\n\n#재테크",
        "▶ 대출이자 계산기 → finance-calc-kr.netlify.app/loan.html"
    ),
    (
        "💡 연봉 협상할 때 이 실수 하지 마\n\n회사가 제시하는 연봉 그대로 받으면 안 돼\n세금 떼고 나면 생각보다 훨씬 적거든\n\n연봉 협상 성공한 사람 있어? 비결 공유해줘 👇\n\n#월급",
        "▶ 연봉 실수령액 계산기 → finance-calc-kr.netlify.app/salary.html"
    ),
    (
        "🏠 생애 최초 주택 구입하면 취득세 감면돼\n\n12억 이하 주택 → 취득세 200만원 한도 감면\n해당되면 꼭 신청해야 해\n\n이거 알고 있었어? 아니면 처음 알았어? 👇\n\n#부동산",
        "▶ 취득세 계산기 → finance-calc-kr.netlify.app/acquisition-tax.html"
    ),
    (
        "📋 퇴직금 받을 때 세금 아끼는 법\n\nIRP 계좌로 받고 55세 이후 연금으로 수령\n일시금 vs 연금 세금 차이가 수백만원\n\n퇴직금 어떻게 받을 계획이야? 👇\n\n#재테크",
        "▶ 퇴직금 계산기 → finance-calc-kr.netlify.app/severance.html"
    ),
    (
        "💰 월급 300만원인데 저축 얼마 해야 해?\n\n수입의 30~50% 권장이라는데\n고정지출 빼면 현실적으로 얼마나 가능해?\n\n너희는 월급의 몇 % 저축해? 👇\n\n#월급",
        "▶ 연봉 실수령액 계산기 → finance-calc-kr.netlify.app/salary.html"
    ),
    (
        "🏡 전세 사기 당하지 않으려면\n\n전세금이 집값의 70% 넘으면 위험\n전입신고 + 확정일자 필수\n\n주변에 전세 사기 피해 본 사람 있어? 👇\n\n#부동산",
        "▶ 금융 계산기 모음 → finance-calc-kr.netlify.app"
    ),
    (
        "📊 무주택 10년이면 청약 가점 몇 점?\n\n무주택 10년 = 32점\n부양가족 4명 = 25점\n청약통장 15년 = 17점 → 총 74점\n\n이 정도면 어느 지역 당첨 가능할까? 👇\n\n#청약",
        "▶ 청약 가점 계산기 → finance-calc-kr.netlify.app/subscription.html"
    ),
    (
        "💸 부모님한테 1억 받으면 증여세 얼마야?\n\n10년 내 5000만원 초과분에 세금\n1억이면 세금 500만원\n\n증여 받아본 사람 있어? 세금 냈어? 👇\n\n#재테크",
        "▶ 전체 금융 계산기 → finance-calc-kr.netlify.app"
    ),
    (
        "💰 연봉 4000만원인데 왜 월급이 286만원이지?\n\n정답은 세금이야\n국민연금 4.5% + 건강보험 4% + 소득세\n다 합치면 월급의 15~20%가 사라짐\n\n내 연봉에서 세금 얼마 떼이는지 알아? 👇\n\n#재테크",
        "▶ 연봉별 실수령액 계산 → finance-calc-kr.netlify.app/salary.html"
    ),
    (
        "💡 월급에서 세금 합법적으로 줄이는 법\n\n1. 비과세 식대 (월 20만원) 챙기기\n2. IRP 넣으면 연말에 최대 115만원 환급\n3. 체크카드 신용카드보다 공제율 2배\n4. 의료비·교육비 영수증 챙기기\n\n연말정산으로 얼마 돌려받았어? 👇\n\n#재테크",
        "▶ 연봉 실수령액 계산기 → finance-calc-kr.netlify.app/salary.html"
    ),
    (
        "🏠 집 살 때 취득세 얼마나 나오는지 알아?\n\n9억 아파트 = 취득세 3,240만원\n6억 아파트 = 취득세 660만원\n\n근데 생애최초 구입이면 200만원 감면돼\n내 경우엔 얼마 나오는지 계산해봐 👇\n\n#부동산",
        "▶ 취득세 계산 → finance-calc-kr.netlify.app/acquisition-tax.html"
    ),
    (
        "ISA 계좌 아직도 안 만든 사람?\n\n납입 한도 연 2000만원, 3년 후 수익에 세금 없어\n일반 계좌로 주식하면 배당세 15.4% 떼이는 거랑 비교하면\n\n직장인이면 그냥 만들어두는 게 나음\n근데 중도 해지하면 혜택 다 날아가니까 주의\n\nISA 알고 있었어? 아니면 처음 들어봤어? 👇\n\n#재테크",
        "▶ 금융 계산기 모음 → finance-calc-kr.netlify.app"
    ),
    (
        "연말정산에서 '환급' 받는 게 무조건 좋은 건 아니야\n\n13월의 월급이라고 좋아하는데\n사실 그건 내가 세금을 더 냈다가 돌려받는 것\n\n반대로 추가 납부가 나오면?\n그건 내가 덜 냈다가 갚는 것\n\n어느 쪽이든 연간 총 세금은 똑같아\n\n올해 연말정산 결과 어떻게 됐어? 👇\n\n#재테크",
        "▶ 연봉 실수령액 계산기 → finance-calc-kr.netlify.app/salary.html"
    ),
    (
        "사업자 내려는데 일반과세자 vs 간이과세자 차이 알아?\n\n연매출 1억 400만원 기준으로 나뉘어\n간이과세자면 부가세 신고 1년에 1번\n일반과세자면 1년에 2번 + 세금도 더 많이 냄\n\n처음 시작하면 간이과세자로 내는 게 보통 유리한데\n매출이 커지면 자동으로 전환되니까 미리 알아둬야 해\n\n사업자 낸 사람들 어떤 거 선택했어? 👇\n\n#재테크",
        "▶ 금융 계산기 모음 → finance-calc-kr.netlify.app"
    ),
    (
        "실직했을 때 실업급여 얼마나 받는지 알아?\n\n마지막 3개월 평균 임금의 60%\n상한액은 하루 66,000원\n\n근데 조건 있어\n180일 이상 고용보험 납부 + 비자발적 퇴직\n\n자발적으로 나왔으면 원칙적으로 못 받아\n근데 예외 조항도 있긴 해\n\n실업급여 받아본 사람 있어? 👇\n\n#월급",
        "▶ 금융 계산기 모음 → finance-calc-kr.netlify.app"
    ),
    (
        "전세 1억에 전세대출 vs 월세 + 주담대\n\n이게 뭐가 유리한지 진짜 헷갈리는데\n금리 상황마다 답이 달라짐\n\n지금처럼 금리 높은 시기엔\n전세대출 이자 = 그냥 월세랑 비슷하거나 더 비싼 경우도 있어\n\n보증금 크면 이자 부담도 그만큼 커진다는 거\n\n너희는 지금 어떤 선택 했어? 👇\n\n#부동산",
        "▶ 대출이자 계산기 → finance-calc-kr.netlify.app/loan.html"
    ),
    (
        "적금 vs ETF, 2026년엔 뭐가 나을까?\n\n적금: 연 3~4%, 원금 보장\nETF: 연 10~15% 가능, 원금 손실 위험\n\n근데 물가 상승률 3%면 적금은 사실상 본전이야\n\n너희는 어디에 넣고 있어? 👇\n\n#재테크",
        "▶ 금융 계산기 모음 → finance-calc-kr.netlify.app"
    ),
    (
        "월세 vs 전세, 당신의 선택은?\n\n월세: 목돈 안 묶임, 매달 나가는 돈\n전세: 목돈 묶이지만 월 지출 없음\n\n근데 전세대출 이자 내면 월세랑 비슷한 경우도 있어\n\n지금 뭐로 살고 있어? 이유도 같이 써봐 👇\n\n#부동산",
        "▶ 전월세 전환 계산기 → finance-calc-kr.netlify.app/jeonse-monthly.html"
    ),
    (
        "재테크 초보가 가장 먼저 해야 할 건 ____\n\n빈칸 채워봐\n\n비상금? 적금? 주식? 보험?\n사람마다 다른데 정답이 있을까?\n\n나는 ____부터 했어 👇\n\n#재테크",
        "▶ 금융 계산기 모음 → finance-calc-kr.netlify.app"
    ),
    (
        "나만 몰랐던 연말정산 꿀팁 3가지\n\n1. 체크카드 공제율이 신용카드의 2배 (30% vs 15%)\n2. IRP 넣으면 최대 115만원 환급\n3. 안경·렌즈도 의료비 공제 대상\n\n이 중에 몰랐던 거 있어? 솔직히 말해봐 👇\n\n#재테크",
        "▶ 연봉 실수령액 계산기 → finance-calc-kr.netlify.app/salary.html"
    ),
    (
        "연봉 올리기 vs 지출 줄이기, 뭐가 먼저?\n\n연봉 500만원 올리면 실수령 +약 30만원/월\n지출 30만원 줄이면 바로 +30만원/월\n\n근데 연봉은 올리기 어렵고\n지출은 줄이기 쉽잖아\n\n너희는 어느 쪽에 집중하고 있어? 👇\n\n#월급",
        "▶ 연봉 실수령액 계산기 → finance-calc-kr.netlify.app/salary.html"
    ),
]

async def post_thread(body, comment):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=SESSION_FILE,
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844}
        )
        page = await context.new_page()

        page.set_default_timeout(30000)
        await page.goto("https://www.threads.com/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        # 입력창 클릭 - text content 기반 (안정적)
        clicked = False
        btns = await page.query_selector_all("div[role='button'], button")
        for btn in btns:
            txt = await btn.text_content()
            if txt and txt.strip() == "Create":
                is_visible = await btn.is_visible()
                if is_visible:
                    await btn.click()
                    clicked = True
                    break

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
            await page.goto("https://www.threads.com/@calcmoney.kr", wait_until="domcontentloaded", timeout=30000)
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
