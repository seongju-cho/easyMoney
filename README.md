# easyMoney — Heikin-Ashi + 200 EMA + Stoch RSI Backtester

BTC/USDT 1H 전략 백테스터. Windows에서 바로 동작.

## 전략

**Long 진입** (모두 만족, 1H 종가 기준)
1. `Close > EMA200`
2. Stochastic RSI K가 D를 **상향** 돌파 (golden cross)
3. Heikin-Ashi **양봉**이면서 **아래꼬리 없음** (`HA_low >= HA_open`)

**Short 진입** (대칭)
1. `Close < EMA200`
2. Stochastic RSI K가 D를 **하향** 돌파 (dead cross)
3. Heikin-Ashi **음봉**이면서 **위꼬리 없음** (`HA_high <= HA_open`)

**청산**: 손절 -1.5%, 익절 +3% 고정. 한 봉에서 둘 다 닿으면 손절 우선 (보수).
**체결 모델**: 신호 봉 종가에 평가 → **다음 봉 시가** 진입(룩어헤드 방지). 슬리피지는 진입과 SL 체결에 불리하게 적용, TP는 지정가 정확 체결.

## Windows 설치

1. Python 3.10+ 설치 (https://www.python.org/downloads/)
2. 프로젝트 폴더에서:
   ```
   setup.bat
   ```
3. 백테스트 실행:
   ```
   run_backtest.bat
   ```
4. 결과는 `results/` 폴더 (`summary.txt`, `trades.csv`, `equity.csv`, `equity_curve.png`, `signals.png`)

데이터는 Binance public REST API에서 자동 다운로드되어 `data/`에 캐시됩니다 (API 키 불필요).

## 설정 (`config.yaml`)

```yaml
symbol: BTCUSDT
timeframe: 1h
start: "2023-01-01"
end: "2025-05-09"
initial_capital: 10000
position_pct: 1.0           # 자본의 100%
fee_pct: 0.001              # 0.1% per side
slippage_pct: 0.0002        # 0.02% adverse
sl_pct: 0.015
tp_pct: 0.03
same_bar_priority: SL
ema_length: 200
stoch_rsi: { rsi_length: 14, stoch_length: 14, k_smooth: 3, d_smooth: 3 }
```

## 디렉토리

```
easyMoney/
├── config.yaml
├── requirements.txt
├── setup.bat
├── run_backtest.bat
├── data/                # OHLCV 캐시 (parquet)
├── results/             # 백테스트 산출물
└── src/
    ├── data_loader.py
    ├── indicators.py    # Heikin-Ashi, EMA, Stoch RSI
    ├── strategy.py      # 시그널 생성
    ├── backtester.py    # 이벤트 루프, SL/TP, 수수료
    ├── metrics.py       # 승률, PF, MDD, Sharpe 등
    ├── plotter.py
    └── main.py
```

## 다음 단계 (TODO)

- [ ] 자동매매 어댑터 (Binance/Bybit/Bitget 중 수수료 비교 후 결정)
- [ ] 파라미터 스윕 (SL/TP 비율, 추세 필터 길이)
- [ ] 멀티 심볼 / 멀티 타임프레임
- [ ] 워크포워드 분석
