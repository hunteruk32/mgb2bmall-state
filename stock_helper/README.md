# 📈 나만의 한국 주식 단기투자 도우미

기술적 지표 + **외국인·기관 수급**을 점수화(-100 ~ +100)해서
매수/매도 타이밍을 추천하는 개인용 CLI 도구입니다.

## 설치 & 실행
```bash
cd stock_helper
pip install -r requirements.txt

python main.py analyze 005930            # 종목 분석 + 매수/매도 의견
python main.py analyze 005930 --chart    # chart_005930.png 저장 (가격/수급/RSI/점수)
python main.py scan watchlist.txt        # 관심종목 점수 랭킹
python main.py scan 005930,000660        # 쉼표로 바로 입력도 가능
python main.py optimize                  # 점수 전략·눌림목 전략을 모두 시험해 비교 후 저장
python main.py optimize --strategy pullback   # 한 전략만 시험
python main.py edge                      # 신호 예측력 진단 (점수/영역/눌림목별 이후 수익률)
python main.py backtest 005930,000660 --show       # 저장된 설정으로 백테스트 (거래내역 포함)
python main.py backtest universe.txt --tp 1 --tp2 3 --sl 2   # 설정 바꿔서 검증
python main.py backtest universe.txt --no-market --no-split  # 시장필터/분할익절 끄고 비교
python main.py monitor                   # 장중 5분마다 watchlist.txt 감시 + 모의매매 기록
python main.py monitor --once            # 1회만 점검 (장외에도 가능)
python main.py paper                     # 모의매매 승률 (100회 목표)
python main.py analyze DEMO              # 인터넷 없이 가상 데이터로 시험
```
데이터: 네이버 금융(로그인 불필요) → 실패 시 pykrx 자동 대체.
장 마감(15:30) 후, 수급 확정치가 올라오는 저녁에 돌리는 것을 권장합니다.

## 매수·매도 조건
- 매수: 종합점수 ≥ 기준 **그리고** 코스피 정상(20일선 위, 급락 아님)
- 매도: 손절 / 1차 목표에서 **절반 익절 후 남은 절반은 본전 스탑** / 2차 목표 / 점수 하락 / 기간 만료

전체 조건표는 [STRATEGY.md](STRATEGY.md)에 코드와 똑같이 정리되어 있습니다.

## 추천 사용 순서
1. `optimize`: 과거 데이터로 설정 선택 (첫 실행은 데이터 수집에 몇 분 걸림, 이후 24시간 동안 저장된 데이터 재사용)
2. **검증 구간** 승률·평균수익 확인
3. 장중 `monitor`로 실시간 모의매매 → `paper`로 100회 누적 성적 확인
4. 모의매매에서도 목표를 달성하면 그때 소액 실전 매매

## 점수 구성
| 영역 | 비중 | 보는 것 |
|---|---|---|
| 추세 | 30 | 20일선 위/아래, 5·20일선 정배열, 20일선 기울기, 20>60일선, 골든/데드크로스 |
| 모멘텀 | 25 | MACD 히스토그램 확대·시그널 돌파, RSI 구간(50~70 우호, 80↑ 과열), 스토캐스틱 침체권 반등 |
| 거래량 | ~18 | 거래량 1.5배↑ 양봉/음봉, OBV(매집/분산), MFI, 20일 신고가 돌파 |
| **수급** | 30 | 외국인·기관 5일 순매수, **쌍끌이 매수**, 순매수 비중(거래량 대비 %), 연속 순매수 일수 |

| 점수 | 의견 |
|---|---|
| ≥ 50 | 강력 매수 |
| 25 ~ 50 | 매수 관심 (분할 매수) |
| -25 ~ 25 | 관망 |
| -50 ~ -25 | 매도 / 비중 축소 |
| ≤ -50 | 강력 매도 |

추가로
- **주의**: RSI 70↑, 볼린저 상단 돌파, 20일선 이격 115%↑ → 추격매수 자제
- **보유자 매도 경고**: 20일선 이탈, 데드크로스, 외인/기관 3일↑ 연속 순매도, 대량거래 하락, RSI 과열권 꺾임
- **매매 가이드**: ATR 기반 손절가(−2ATR 또는 20일선 −3% 중 가까운 값), 1차(+2ATR)/2차(+4ATR) 목표가, 손익비

## 활용 팁
1. 매일 저녁 `scan` → 점수 상위 + 수급 점수 플러스 종목만 추림
2. `analyze`로 근거·경고 확인, `backtest`로 그 종목에서 전략이 통했는지 확인
3. 진입은 분할, 손절가는 **반드시** 지키기
4. 점수 가중치는 `signals.py`의 `add(...)` 숫자를 바꿔 자신에게 맞게 튜닝

## 구조
```
data.py        네이버/pykrx 데이터 수집, DEMO 가상데이터
indicators.py  MA, RSI, MACD, 볼린저, ATR, 스토캐스틱, MFI, OBV, 수급 합계/연속일수
signals.py     점수 산출 · 의견 · 근거 · 손절/목표가
backtest.py    백테스트 · 파라미터 최적화 (학습/검증 분리, 왕복비용 0.25%)
realtime.py    장중 감시 · 모의매매 기록(paper_trades.csv)
market.py      시장 필터 (코스피 20일선·급락 시 신규 매수 금지)
STRATEGY.md    매수/매도 조건 전체
main.py        CLI
tests/         pytest
```

> ⚠️ 참고용 도구이며 투자 권유가 아닙니다. 지표·수급은 과거 데이터 기반이라 미래를 보장하지 않습니다.
