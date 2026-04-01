"""
Threads 자동 포스팅 - 매일 1회 실행
본문: 링크 없음 / 첫 댓글: 링크 삽입 (알고리즘 최적화)
launchd에 의해 호출됨

[안전 모드]
- 랜덤 딜레이로 봇 감지 회피
- 하루 1개 포스팅 제한
- 제한/정지 감지 시 즉시 종료
- 시작 전 랜덤 지연 (0~2시간, SKIP_RANDOM_DELAY=1 로 건너뛰기)
"""
import asyncio
import json
import os
import random
import time
import urllib.request
from datetime import datetime
from playwright.async_api import async_playwright


# ────────────────────────────────────────────────
# 상수
# ────────────────────────────────────────────────
SESSION_FILE = "/tmp/threads_session.json"
POSTED_FILE  = "/tmp/threads_posted.json"
HISTORY_FILE = "/tmp/threads_post_history.json"

# 제한/정지 감지 키워드
RESTRICTION_KEYWORDS = [
    "restriction", "restricted", "suspended", "suspend",
    "challenge", "verify", "verification", "unusual activity",
    "temporarily", "blocked", "계정이 정지", "일시적으로 제한",
    "비정상적인 활동", "인증이 필요", "보안 확인",
]


# ────────────────────────────────────────────────
# 포스트 목록
# ────────────────────────────────────────────────
POSTS = [
    (
        "💰 연봉 4000만원 실수령액 알아?\n\n세금 다 떼면 월 286만원\n생각보다 훨씬 적지?\n\n너희 연봉 실수령액은 얼마야? 댓글에 써봐 👇\n\n#재테크",
        "▶ 연봉 실수령액 계산기 → calcmoney.kr/salary"
    ),
    (
        "🏠 9억 아파트 취득세 얼마인지 알아?\n\n취득세만 2700만원\n지방교육세까지 합치면 3240만원\n\n집 살 때 이 비용 생각 안 하고 있었으면 꼭 계산해봐 👇\n\n#부동산",
        "▶ 취득세 계산기 → calcmoney.kr/acquisition-tax"
    ),
    (
        "📋 알바하는데 주휴수당 못 받고 있어?\n\n주 15시간 이상이면 무조건 받아야 해\n시급 10000원 × 주 40시간이면 주 8만원 추가\n\n지금 받고 있어? 아니면 못 받고 있어? 👇\n\n#월급",
        "▶ 주휴수당 계산기 → calcmoney.kr/weekly-holiday.html"
    ),
    (
        "💼 10년 다니면 퇴직금 얼마나 될까?\n\n월급 300만원 × 10년 = 3000만원\n근데 IRP로 받으면 세금 아낄 수 있어\n\n퇴직금 얼마 모았어? 댓글에 공유해봐 👇\n\n#재테크",
        "▶ 퇴직금 계산기 → calcmoney.kr/severance.html"
    ),
    (
        "🏡 전세 3억을 월세로 바꾸면 얼마야?\n\n집주인이 터무니없는 금액 부르는 경우 많아\n법정 전환율 연 5% 기준으로 따져봐야 해\n\n전세 vs 월세 어떤 게 나아? 👇\n\n#부동산",
        "▶ 전월세 전환 계산기 → calcmoney.kr/jeonse-monthly"
    ),
    (
        "📊 청약 가점 몇 점인지 알아?\n\n무주택 기간 + 부양가족 수 + 청약통장 기간\n최고 84점 만점\n\n내 점수 계산해봤어? 몇 점 나왔어? 👇\n\n#청약",
        "▶ 청약 가점 계산기 → calcmoney.kr/subscription.html"
    ),
    (
        "💸 집 팔 때 양도세 얼마 나오는지 알아?\n\n2년 보유 + 2년 거주하면 12억까지 비과세\n조건 안 맞으면 수천만원 세금 폭탄\n\n이거 몰랐던 사람 있어? 솔직히 말해봐 👇\n\n#부동산",
        "▶ 양도소득세 계산기 → calcmoney.kr/capital-gains.html"
    ),
    (
        "🏦 3억 대출 30년 갚으면 이자 총 얼마?\n\n금리 4%면 이자만 2억 1500만원\n금리 1% 차이가 30년간 7000만원 차이\n\n지금 대출 금리 얼마야? 댓글에 써봐 👇\n\n#재테크",
        "▶ 대출이자 계산기 → calcmoney.kr/loan"
    ),
    (
        "💡 연봉 협상할 때 이 실수 하지 마\n\n회사가 제시하는 연봉 그대로 받으면 안 돼\n세금 떼고 나면 생각보다 훨씬 적거든\n\n연봉 협상 성공한 사람 있어? 비결 공유해줘 👇\n\n#월급",
        "▶ 연봉 실수령액 계산기 → calcmoney.kr/salary"
    ),
    (
        "🏠 생애 최초 주택 구입하면 취득세 감면돼\n\n12억 이하 주택 → 취득세 200만원 한도 감면\n해당되면 꼭 신청해야 해\n\n이거 알고 있었어? 아니면 처음 알았어? 👇\n\n#부동산",
        "▶ 취득세 계산기 → calcmoney.kr/acquisition-tax"
    ),
    (
        "📋 퇴직금 받을 때 세금 아끼는 법\n\nIRP 계좌로 받고 55세 이후 연금으로 수령\n일시금 vs 연금 세금 차이가 수백만원\n\n퇴직금 어떻게 받을 계획이야? 👇\n\n#재테크",
        "▶ 퇴직금 계산기 → calcmoney.kr/severance.html"
    ),
    (
        "💰 월급 300만원인데 저축 얼마 해야 해?\n\n수입의 30~50% 권장이라는데\n고정지출 빼면 현실적으로 얼마나 가능해?\n\n너희는 월급의 몇 % 저축해? 👇\n\n#월급",
        "▶ 연봉 실수령액 계산기 → calcmoney.kr/salary"
    ),
    (
        "🏡 전세 사기 당하지 않으려면\n\n전세금이 집값의 70% 넘으면 위험\n전입신고 + 확정일자 필수\n\n주변에 전세 사기 피해 본 사람 있어? 👇\n\n#부동산",
        "▶ 금융 계산기 모음 → calcmoney.kr"
    ),
    (
        "📊 무주택 10년이면 청약 가점 몇 점?\n\n무주택 10년 = 32점\n부양가족 4명 = 25점\n청약통장 15년 = 17점 → 총 74점\n\n이 정도면 어느 지역 당첨 가능할까? 👇\n\n#청약",
        "▶ 청약 가점 계산기 → calcmoney.kr/subscription.html"
    ),
    (
        "💸 부모님한테 1억 받으면 증여세 얼마야?\n\n10년 내 5000만원 초과분에 세금\n1억이면 세금 500만원\n\n증여 받아본 사람 있어? 세금 냈어? 👇\n\n#재테크",
        "▶ 전체 금융 계산기 → calcmoney.kr"
    ),
    (
        "💰 연봉 4000만원인데 왜 월급이 286만원이지?\n\n정답은 세금이야\n국민연금 4.5% + 건강보험 4% + 소득세\n다 합치면 월급의 15~20%가 사라짐\n\n내 연봉에서 세금 얼마 떼이는지 알아? 👇\n\n#재테크",
        "▶ 연봉별 실수령액 계산 → calcmoney.kr/salary"
    ),
    (
        "💡 월급에서 세금 합법적으로 줄이는 법\n\n1. 비과세 식대 (월 20만원) 챙기기\n2. IRP 넣으면 연말에 최대 115만원 환급\n3. 체크카드 신용카드보다 공제율 2배\n4. 의료비·교육비 영수증 챙기기\n\n연말정산으로 얼마 돌려받았어? 👇\n\n#재테크",
        "▶ 연봉 실수령액 계산기 → calcmoney.kr/salary"
    ),
    (
        "🏠 집 살 때 취득세 얼마나 나오는지 알아?\n\n9억 아파트 = 취득세 3,240만원\n6억 아파트 = 취득세 660만원\n\n근데 생애최초 구입이면 200만원 감면돼\n내 경우엔 얼마 나오는지 계산해봐 👇\n\n#부동산",
        "▶ 취득세 계산 → calcmoney.kr/acquisition-tax"
    ),
    (
        "ISA 계좌 아직도 안 만든 사람?\n\n납입 한도 연 2000만원, 3년 후 수익에 세금 없어\n일반 계좌로 주식하면 배당세 15.4% 떼이는 거랑 비교하면\n\n직장인이면 그냥 만들어두는 게 나음\n근데 중도 해지하면 혜택 다 날아가니까 주의\n\nISA 알고 있었어? 아니면 처음 들어봤어? 👇\n\n#재테크",
        "▶ 금융 계산기 모음 → calcmoney.kr"
    ),
    (
        "연말정산에서 '환급' 받는 게 무조건 좋은 건 아니야\n\n13월의 월급이라고 좋아하는데\n사실 그건 내가 세금을 더 냈다가 돌려받는 것\n\n반대로 추가 납부가 나오면?\n그건 내가 덜 냈다가 갚는 것\n\n어느 쪽이든 연간 총 세금은 똑같아\n\n올해 연말정산 결과 어떻게 됐어? 👇\n\n#재테크",
        "▶ 연봉 실수령액 계산기 → calcmoney.kr/salary"
    ),
    (
        "사업자 내려는데 일반과세자 vs 간이과세자 차이 알아?\n\n연매출 1억 400만원 기준으로 나뉘어\n간이과세자면 부가세 신고 1년에 1번\n일반과세자면 1년에 2번 + 세금도 더 많이 냄\n\n처음 시작하면 간이과세자로 내는 게 보통 유리한데\n매출이 커지면 자동으로 전환되니까 미리 알아둬야 해\n\n사업자 낸 사람들 어떤 거 선택했어? 👇\n\n#재테크",
        "▶ 금융 계산기 모음 → calcmoney.kr"
    ),
    (
        "실직했을 때 실업급여 얼마나 받는지 알아?\n\n마지막 3개월 평균 임금의 60%\n상한액은 하루 66,000원\n\n근데 조건 있어\n180일 이상 고용보험 납부 + 비자발적 퇴직\n\n자발적으로 나왔으면 원칙적으로 못 받아\n근데 예외 조항도 있긴 해\n\n실업급여 받아본 사람 있어? 👇\n\n#월급",
        "▶ 금융 계산기 모음 → calcmoney.kr"
    ),
    (
        "전세 1억에 전세대출 vs 월세 + 주담대\n\n이게 뭐가 유리한지 진짜 헷갈리는데\n금리 상황마다 답이 달라짐\n\n지금처럼 금리 높은 시기엔\n전세대출 이자 = 그냥 월세랑 비슷하거나 더 비싼 경우도 있어\n\n보증금 크면 이자 부담도 그만큼 커진다는 거\n\n너희는 지금 어떤 선택 했어? 👇\n\n#부동산",
        "▶ 대출이자 계산기 → calcmoney.kr/loan"
    ),
    (
        "적금 vs ETF, 2026년엔 뭐가 나을까?\n\n적금: 연 3~4%, 원금 보장\nETF: 연 10~15% 가능, 원금 손실 위험\n\n근데 물가 상승률 3%면 적금은 사실상 본전이야\n\n너희는 어디에 넣고 있어? 👇\n\n#재테크",
        "▶ 금융 계산기 모음 → calcmoney.kr"
    ),
    (
        "월세 vs 전세, 당신의 선택은?\n\n월세: 목돈 안 묶임, 매달 나가는 돈\n전세: 목돈 묶이지만 월 지출 없음\n\n근데 전세대출 이자 내면 월세랑 비슷한 경우도 있어\n\n지금 뭐로 살고 있어? 이유도 같이 써봐 👇\n\n#부동산",
        "▶ 전월세 전환 계산기 → calcmoney.kr/jeonse-monthly"
    ),
    (
        "재테크 초보가 가장 먼저 해야 할 건 ____\n\n빈칸 채워봐\n\n비상금? 적금? 주식? 보험?\n사람마다 다른데 정답이 있을까?\n\n나는 ____부터 했어 👇\n\n#재테크",
        "▶ 금융 계산기 모음 → calcmoney.kr"
    ),
    (
        "나만 몰랐던 연말정산 꿀팁 3가지\n\n1. 체크카드 공제율이 신용카드의 2배 (30% vs 15%)\n2. IRP 넣으면 최대 115만원 환급\n3. 안경·렌즈도 의료비 공제 대상\n\n이 중에 몰랐던 거 있어? 솔직히 말해봐 👇\n\n#재테크",
        "▶ 연봉 실수령액 계산기 → calcmoney.kr/salary"
    ),
    (
        "연봉 올리기 vs 지출 줄이기, 뭐가 먼저?\n\n연봉 500만원 올리면 실수령 +약 30만원/월\n지출 30만원 줄이면 바로 +30만원/월\n\n근데 연봉은 올리기 어렵고\n지출은 줄이기 쉽잖아\n\n너희는 어느 쪽에 집중하고 있어? 👇\n\n#월급",
        "▶ 연봉 실수령액 계산기 → calcmoney.kr/salary"
    ),
    (
        "📈 1억 모으는 데 복리가 단리보다 얼마나 빠른지 알아?\n\n연 5% 단리로 1억 → 20년 걸려\n연 5% 복리로 1억 → 14.9년이면 돼\n\n5년 차이가 생기는 이유, 복리 때문이야\n\n지금 어디에 복리로 굴리고 있어? 👇\n\n#재테크",
        "▶ 복리 계산기로 직접 확인 → calcmoney.kr/compound-interest"
    ),
    (
        "💡 72의 법칙 알아?\n\n72 ÷ 금리 = 원금이 2배 되는 기간\n\n연 4% 예금 → 18년 후 2배\n연 8% 투자 → 9년 후 2배\n\n지금 내 돈이 2배 되려면 몇 년 걸리는지 계산해봐 👇\n\n#재테크",
        "▶ 복리 계산기 → calcmoney.kr/compound-interest"
    ),
    (
        "🏦 적금 세전 금리 5%인데 세후로 받으면 얼마야?\n\n이자소득세 15.4% 떼면 실제 수익률은 4.23%\n월 30만원씩 1년 → 세전 98,000원 vs 세후 83,000원\n\n은행 앱에 표시된 금리 그대로 믿으면 안 돼 👇\n\n#재테크",
        "▶ 적금이자 세후 계산기 → calcmoney.kr/savings-interest"
    ),
    (
        "💰 비과세 적금 조건 알고 있어?\n\n농특세만 1.4% → 이자 15.4% 아끼는 거야\n조합원 가입하면 연 1200만원 한도로 가능\n\n월 30만원씩 3년이면 이자 차이 약 30만원\n신청 안 했으면 지금 바로 해 👇\n\n#재테크",
        "▶ 적금이자 계산기 → calcmoney.kr/savings-interest"
    ),
    (
        "🏠 5억 아파트 재산세 얼마인지 알아?\n\n공시가격 기준 세율 적용 → 연 약 67만원\n6월 1일 기준으로 보유하고 있으면 납세 대상\n\n집 사기 전에 재산세도 미리 계산해봐 👇\n\n#부동산",
        "▶ 재산세 계산기 → calcmoney.kr/property-tax"
    ),
    (
        "📋 재산세 줄이는 방법 아는 사람 있어?\n\n1. 6월 1일 이후에 잔금 치르면 그해 재산세 안 냄\n2. 공시가격 이의신청으로 세금 낮추는 경우도 있음\n3. 주택 수 조정으로 세율 구간 내려가기\n\n이 중에 실제로 써먹은 사람 있어? 👇\n\n#부동산",
        "▶ 재산세 계산기 → calcmoney.kr/property-tax"
    ),
    (
        "🏡 5억짜리 집 팔 때 공인중개사 수수료 얼마야?\n\n법정 상한요율 0.4% → 최대 200만원\n근데 협의하면 더 내릴 수 있어\n\n계산도 안 하고 그냥 내는 사람 많아 👇\n\n#부동산",
        "▶ 중개수수료 계산기 → calcmoney.kr/real-estate-fee"
    ),
    (
        "💸 중개수수료 협상하는 법 알아?\n\n법정 상한요율은 '최대'일 뿐 깎을 수 있어\n5억 매매 기준 200만원 → 100만원으로 낮춘 사례 많음\n\n계약 전에 미리 계산해두고 당당하게 협상해 👇\n\n#부동산",
        "▶ 중개수수료 계산기 → calcmoney.kr/real-estate-fee"
    ),
    (
        "공시가격 12억 넘는 집 1채 있으면 종부세 내야 해\n\n1주택이면 12억까지 공제라서 그 이하는 종부세 0원\n12억 초과분에만 0.5%~1.0% 세율 적용돼\n\n내 집 종부세 얼마인지 계산해봤어? 👇\n\n#부동산",
        "▶ 종부세 계산기 → calcmoney.kr/property-holding-tax"
    ),
    (
        "1주택자 종부세 vs 2주택자 종부세 차이 알아?\n\n1주택: 12억 공제 + 고령자·장기보유 세액공제 최대 80%\n2주택: 9억 공제, 세액공제 없음\n\n집 2채 보유 시 종부세 얼마나 더 나오는지 확인해봐 👇\n\n#재테크",
        "▶ 종부세 계산기 → calcmoney.kr/property-holding-tax"
    ),
    (
        "DSR 40% 규제 때문에 대출 막혔다는 사람 주변에 많지?\n\n연봉 5,000만원이면 연간 원리금 2,000만원 한도\n기존 신용대출 있으면 그만큼 주담대 한도 줄어\n\nDSR로 내 대출 한도 역산해봐 👇\n\n#내집마련",
        "▶ DSR/DTI 계산기 → calcmoney.kr/dti-dsr"
    ),
    (
        "대출 얼마까지 받을 수 있는지 은행 가기 전에 미리 알 수 있어\n\nDSR = 모든 부채 원리금 ÷ 연소득\n신용대출, 자동차 할부까지 다 합산되니까 주의해\n\n한도 역산해서 미리 계획 세워봐 👇\n\n#부동산",
        "▶ DSR/DTI 계산기 → calcmoney.kr/dti-dsr"
    ),
    (
        "대출 조기상환 고민 중이야?\n\n3년 이내 상환하면 중도상환수수료 나와\n1억 대출 1년 만에 갚으면 수수료만 약 47만원\n\n수수료 얼마인지 계산해보고 갚는 게 이득인지 따져봐 👇\n\n#재테크",
        "▶ 중도상환수수료 계산기 → calcmoney.kr/prepayment-fee"
    ),
    (
        "대출 받은 지 3년 지났어? 그럼 지금 갚아도 수수료 없어\n\n3년 이후 상환은 대부분 시중은행 기준 수수료 면제\n갱신하면 3년 카운트 리셋되니까 시점 꼭 확인해\n\n면제 타이밍 계산해봐 👇\n\n#내집마련",
        "▶ 중도상환수수료 계산기 → calcmoney.kr/prepayment-fee"
    ),
    (
        "월세 받으면 세금 내야 해 - 기준이 뭔지 알아?\n\n1주택자 월세는 비과세 (고가주택 제외)\n2주택 이상부터 전액 과세, 연 2,000만원 이하면 분리과세 14% 선택 가능\n\n임대소득세 얼마인지 계산해봐 👇\n\n#부동산",
        "▶ 임대소득세 계산기 → calcmoney.kr/rental-income-tax"
    ),
    (
        "임대소득 분리과세 vs 종합과세 어느 게 유리해?\n\n연 2,000만원 이하면 분리과세 14% 선택 가능\n다른 소득 많으면 분리과세가 대부분 유리해\n\n두 방식 비교해서 절세 방법 찾아봐 👇\n\n#재테크",
        "▶ 임대소득세 계산기 → calcmoney.kr/rental-income-tax"
    ),
]


# ────────────────────────────────────────────────
# 유틸
# ────────────────────────────────────────────────
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


def human_delay(min_sec=2.0, max_sec=8.0):
    """사람처럼 보이는 랜덤 대기"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


def load_history():
    """포스팅 히스토리 로드"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {}


def save_history(history):
    """포스팅 히스토리 저장"""
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def already_posted_today():
    """오늘 이미 포스팅했는지 확인"""
    today = datetime.now().strftime("%Y-%m-%d")
    history = load_history()
    return today in history


def record_post(body):
    """오늘 포스팅 기록 저장"""
    today = datetime.now().strftime("%Y-%m-%d")
    history = load_history()
    history[today] = {
        "posted_at": datetime.now().isoformat(),
        "body_preview": body[:50],
    }
    save_history(history)


def detect_restriction(page_text: str) -> str | None:
    """제한/정지 키워드 감지. 감지되면 키워드 반환, 없으면 None"""
    lower = page_text.lower()
    for kw in RESTRICTION_KEYWORDS:
        if kw.lower() in lower:
            return kw
    return None


async def human_type(element, text: str):
    """청크 단위 타이핑으로 사람 타이핑 시뮬레이션
    - 3~8글자 청크, 청크 사이 100~300ms
    - 20% 확률로 1~3초 멈춤
    """
    i = 0
    while i < len(text):
        chunk_size = random.randint(3, 8)
        chunk = text[i:i + chunk_size]
        await element.type(chunk, delay=random.uniform(40, 120))
        i += chunk_size
        # 20% 확률로 1~3초 긴 멈춤
        if random.random() < 0.20:
            await asyncio.sleep(random.uniform(1.0, 3.0))
        else:
            await asyncio.sleep(random.uniform(0.1, 0.3))


async def human_scroll(page, count: int, min_delay=2.0, max_delay=5.0):
    """피드 스크롤 시뮬레이션"""
    for _ in range(count):
        scroll_px = random.randint(300, 800)
        await page.mouse.wheel(0, scroll_px)
        await asyncio.sleep(random.uniform(min_delay, max_delay))


async def random_mouse_move(page, moves: int = 2):
    """마우스를 랜덤 위치로 이동"""
    vp = page.viewport_size or {"width": 1280, "height": 720}
    for _ in range(moves):
        x = random.randint(100, vp["width"] - 100)
        y = random.randint(100, vp["height"] - 100)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.3, 0.8))


# ────────────────────────────────────────────────
# 핵심 포스팅 로직
# ────────────────────────────────────────────────
async def post_thread(body, comment):
    # 랜덤 viewport
    vw = random.randint(1280, 1920)
    vh = random.randint(720, 1080)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=SESSION_FILE,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": vw, "height": vh},
        )

        # webdriver 속성 제거
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()
        page.set_default_timeout(45000)

        # ── 페이지 이동
        for attempt in range(3):
            try:
                await page.goto("https://www.threads.com/", wait_until="domcontentloaded", timeout=60000)
                break
            except Exception as e:
                if attempt < 2:
                    print(f"[{datetime.now()}] 접속 재시도 {attempt+2}/3...")
                    await asyncio.sleep(random.uniform(5, 10))
                else:
                    await browser.close()
                    raise e

        await asyncio.sleep(random.uniform(3, 7))

        # ── 제한 감지
        page_text = await page.inner_text("body")
        kw = detect_restriction(page_text)
        if kw:
            print(f"[{datetime.now()}] 제한 감지 ({kw}) - 즉시 종료")
            await browser.close()
            return False, "restriction"

        # ── 포스팅 전: 피드 스크롤 3~7회
        scroll_count = random.randint(3, 7)
        print(f"[{datetime.now()}] 피드 스크롤 {scroll_count}회 (포스팅 전)")
        await human_scroll(page, scroll_count, min_delay=2.0, max_delay=5.0)

        # ── Create 버튼 클릭
        clicked = False
        btns = await page.query_selector_all("div[role='button'], button")
        for btn in btns:
            txt = await btn.text_content()
            if txt and txt.strip() == "Create":
                is_visible = await btn.is_visible()
                if is_visible:
                    await asyncio.sleep(random.uniform(1, 3))
                    await btn.click()
                    clicked = True
                    break

        if not clicked:
            for placeholder in ["새로운 소식이 있나요?", "What's new?"]:
                try:
                    el = await page.wait_for_selector(f'text={placeholder}', timeout=3000)
                    await asyncio.sleep(random.uniform(1, 3))
                    await el.click()
                    clicked = True
                    break
                except:
                    continue

        await asyncio.sleep(random.uniform(2, 5))

        # ── 제한 재확인 (composer 열린 후)
        page_text = await page.inner_text("body")
        kw = detect_restriction(page_text)
        if kw:
            print(f"[{datetime.now()}] 제한 감지 ({kw}) - 즉시 종료")
            await browser.close()
            return False, "restriction"

        # ── 본문 입력
        editors = await page.query_selector_all('[contenteditable="true"]')
        if not editors:
            await browser.close()
            return False, "no_editor"

        editor = editors[-1]

        # 글 작성 전: 마우스 랜덤 위치로 2~3회 이동
        mouse_moves = random.randint(2, 3)
        await random_mouse_move(page, mouse_moves)

        await asyncio.sleep(random.uniform(1, 3))
        await editor.click()
        await asyncio.sleep(random.uniform(0.5, 1.5))
        await human_type(editor, body)
        await asyncio.sleep(random.uniform(2, 5))

        # ── 게시 버튼 클릭
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

        await asyncio.sleep(random.uniform(4, 8))

        if not posted:
            await browser.close()
            return False, "post_btn_not_found"

        # ── 포스팅 후: 피드를 30~60초 더 보기 (스크롤 2~4회)
        post_scroll_count = random.randint(2, 4)
        post_linger = random.uniform(30, 60)
        print(f"[{datetime.now()}] 포스팅 후 피드 {post_scroll_count}회 스크롤, {post_linger:.0f}초 체류")
        await human_scroll(page, post_scroll_count, min_delay=post_linger / (post_scroll_count + 1) * 0.8,
                           max_delay=post_linger / (post_scroll_count + 1) * 1.2)

        # ── 댓글 달기 (링크)
        try:
            await asyncio.sleep(random.uniform(3, 7))
            # 페이지 이동 전 마우스 랜덤 이동 후 클릭
            await random_mouse_move(page, random.randint(1, 2))
            await page.goto("https://www.threads.com/@calcmoney.kr", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(3, 6))

            # 제한 감지
            page_text = await page.inner_text("body")
            kw = detect_restriction(page_text)
            if kw:
                print(f"[{datetime.now()}] 댓글 전 제한 감지 ({kw}) - 본문만 게시됨")
                await browser.close()
                return True, "ok_no_comment"

            comment_btn = await page.wait_for_selector('[aria-label="댓글 달기"], [aria-label="Reply"]', timeout=5000)
            await asyncio.sleep(random.uniform(1, 3))
            await comment_btn.click()
            await asyncio.sleep(random.uniform(2, 4))

            reply_editors = await page.query_selector_all('[contenteditable="true"]')
            if reply_editors:
                reply_editor = reply_editors[-1]
                await asyncio.sleep(random.uniform(1, 2))
                await reply_editor.click()
                await asyncio.sleep(random.uniform(0.5, 1.5))
                await human_type(reply_editor, comment)
                await asyncio.sleep(random.uniform(2, 5))

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
                await asyncio.sleep(random.uniform(2, 4))
                print(f"[{datetime.now()}] 댓글(링크) 추가 완료")
        except Exception as e:
            print(f"댓글 추가 실패 (무시): {e}")

        await browser.close()
        return True, "ok"


# ────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────
def main():
    # ── 0. 랜덤 시작 지연 (0~2시간)
    if os.environ.get("SKIP_RANDOM_DELAY") != "1":
        delay_sec = random.uniform(0, 7200)
        print(f"[{datetime.now()}] 랜덤 지연 시작: {delay_sec/60:.1f}분 후 실행")
        time.sleep(delay_sec)

    # ── 1. 네트워크 대기
    if not wait_for_network():
        print(f"[{datetime.now()}] 네트워크 연결 실패 - 종료")
        return

    # ── 2. 오늘 이미 포스팅 여부 확인
    if already_posted_today():
        print(f"[{datetime.now()}] 오늘 이미 포스팅 완료 - 스킵")
        return

    # ── 3. 포스트 선택 (기존 로직 유지)
    posted_list = json.load(open(POSTED_FILE)) if os.path.exists(POSTED_FILE) else []
    remaining = [p for p in POSTS if p[0] not in posted_list]

    if not remaining:
        print(f"[{datetime.now()}] 순환 초기화")
        posted_list = []
        remaining = POSTS

    body, comment = random.choice(remaining)

    # ── 4. 포스팅 실행
    success, reason = asyncio.run(post_thread(body, comment))

    if success:
        # 기존 POSTED_FILE 업데이트
        posted_list.append(body)
        with open(POSTED_FILE, "w") as f:
            json.dump(posted_list, f)

        # 날짜별 히스토리 저장
        record_post(body)
        print(f"[{datetime.now()}] Threads 게시 완료 (reason={reason})")
    elif reason == "restriction":
        print(f"[{datetime.now()}] 계정 제한 감지 - 재시도 없이 종료")
    else:
        print(f"[{datetime.now()}] Threads 게시 실패 (reason={reason})")


if __name__ == "__main__":
    main()
