import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
import json
import os

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.json")

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f:
            return json.load(f)
    return ["^DJI", "^GSPC", "^IXIC", "^TNX", "USDJPY=X", "1570.T", "1305.T", "318A.T"]

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(watchlist, f)

st.set_page_config(
    page_title="東証株価ツール",
    page_icon="📈",
    layout="wide"
)


def get_stock_data(ticker: str, period: str = "3mo") -> pd.DataFrame | None:
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period)
        if df.empty:
            return None
        df.index = df.index.tz_localize(None)
        return df
    except Exception:
        return None


def calculate_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["MA5"] = df["Close"].rolling(window=5).mean()
    df["MA25"] = df["Close"].rolling(window=25).mean()
    df["MA75"] = df["Close"].rolling(window=75).mean()
    return df


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(df: pd.DataFrame) -> tuple:
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


def analyze_signals(df: pd.DataFrame) -> dict:
    if len(df) < 30:
        return {"signal": "データ不足", "buy_signals": [], "sell_signals": [], "neutral_signals": [], "summary": "⚪ 中立"}

    df = df.copy()
    df["MA5"] = df["Close"].rolling(window=5).mean()
    df["MA25"] = df["Close"].rolling(window=25).mean()
    df["MA75"] = df["Close"].rolling(window=75).mean()
    df["RSI"] = calculate_rsi(df)
    df["MACD"], df["Signal"] = calculate_macd(df)

    close = df["Close"].iloc[-1]
    ma5 = df["MA5"].iloc[-1]
    ma25 = df["MA25"].iloc[-1]
    ma75 = df["MA75"].iloc[-1]
    rsi = df["RSI"].iloc[-1]
    macd = df["MACD"].iloc[-1]
    signal = df["Signal"].iloc[-1]
    macd_prev = df["MACD"].iloc[-2]
    signal_prev = df["Signal"].iloc[-2]

    prev_ma5 = df["MA5"].iloc[-2]
    prev_ma25 = df["MA25"].iloc[-2]

    buy_signals = []
    sell_signals = []
    neutral_signals = []

    if prev_ma5 < prev_ma25 and ma5 > ma25:
        buy_signals.append(("ゴールデンクロス (MA5>MA25)", "強"))
    elif prev_ma5 > prev_ma25 and ma5 < ma25:
        sell_signals.append(("デッドクロス (MA5<MA25)", "強"))

    if close > ma5 and close > ma25 and close > ma75:
        buy_signals.append(("価格 > 3本移動平均線", "中"))
    elif close < ma5 and close < ma25 and close < ma75:
        sell_signals.append(("価格 < 3本移動平均線", "中"))

    if rsi < 30:
        buy_signals.append(("RSI賣超 (RSI {:.1f})".format(rsi), "強"))
    elif rsi > 70:
        sell_signals.append(("RSI賣超 (RSI {:.1f})".format(rsi), "強"))
    else:
        neutral_signals.append(("RSI中性 (RSI {:.1f})".format(rsi), "-"))

    if macd_prev < signal_prev and macd > signal:
        buy_signals.append(("MACD 交差 (MACD>Signal)", "中"))
    elif macd_prev > signal_prev and macd < signal:
        sell_signals.append(("MACD 交差 (MACD<Signal)", "中"))

    if pd.notna(ma75) and close > ma75:
        buy_signals.append(("価格 > MA75 (トレンド上昇)", "弱"))
    elif pd.notna(ma75) and close < ma75:
        sell_signals.append(("価格 < MA75 (トレンド下落)", "弱"))

    buy_strength = sum(3 if s == "強" else 2 if s == "中" else 1 for _, s in buy_signals)
    sell_strength = sum(3 if s == "強" else 2 if s == "中" else 1 for _, s in sell_signals)

    if buy_strength >= 5:
        summary = "🟢 買いシグナル"
    elif sell_strength >= 5:
        summary = "🔴 売りシグナル"
    elif buy_strength > sell_strength:
        summary = "🟢 若干買い優勢"
    elif sell_strength > buy_strength:
        summary = "🔴 若干売り優勢"
    else:
        summary = "⚪ 中立"

    return {
        "signal": summary,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "neutral_signals": neutral_signals,
        "rsi": rsi,
        "macd": macd,
        "signal_line": signal,
    }


def get_realtime_quote(ticker: str) -> dict | None:
    try:
        stock = yf.Ticker(ticker)
        info = stock.fast_info
        hist = stock.history(period="2d")
        if hist.empty:
            return None
        current = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[-2] if len(hist) > 1 else current
        change = current - prev
        change_pct = (change / prev * 100) if prev != 0 else 0

        stock_info = stock.info
        cash = stock_info.get("totalCash", 0) or 0
        total_debt = stock_info.get("totalDebt", 0) or 0
        shares = stock_info.get("sharesOutstanding", 0) or 0
        net_cash_per_share = (cash - total_debt) / shares if shares > 0 else None
        net_cash_multiple = current / net_cash_per_share if net_cash_per_share and net_cash_per_share != 0 else None
        free_cashflow = stock_info.get("freeCashflow", 0) or 0
        operating_cashflow = stock_info.get("operatingCashflow", 0) or 0
        fcf_per_share = free_cashflow / shares if shares > 0 else None
        book_value_per_share = stock_info.get("bookValue", None) or 0
        payback_years = (current - book_value_per_share) / fcf_per_share if fcf_per_share and fcf_per_share > 0 else None

        return {
            "current": current,
            "prev_close": prev,
            "change": change,
            "change_pct": change_pct,
            "open": hist["Open"].iloc[-1],
            "high": hist["High"].iloc[-1],
            "low": hist["Low"].iloc[-1],
            "volume": hist["Volume"].iloc[-1],
            "name": stock_info.get("shortName", ticker),
            "market_cap": stock_info.get("marketCap", None),
            "cash": cash,
            "total_debt": total_debt,
            "net_cash_per_share": net_cash_per_share,
            "net_cash_multiple": net_cash_multiple,
            "per": stock_info.get("trailingPE", None),
            "pbr": stock_info.get("trailingPB", None),
            "roe": stock_info.get("returnOnEquity", None),
            "free_cashflow": free_cashflow,
            "operating_cashflow": operating_cashflow,
            "fcf_per_share": fcf_per_share,
            "book_value_per_share": book_value_per_share if book_value_per_share else None,
            "payback_years": payback_years,
            "dividend_yield": stock_info.get("dividendYield", None),
            "eps": stock_info.get("trailingEps", None),
        }
    except Exception:
        return None


def format_price(value: float, ticker: str = "") -> str:
    if pd.isna(value):
        return "-"
    currency = "¥" if ticker.endswith(".T") else "$"
    return f"{currency}{value:,.2f}"


def format_volume(value: float) -> str:
    if pd.isna(value):
        return "-"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.0f}"


def plot_candlestick_with_ma(df: pd.DataFrame, ticker: str) -> go.Figure:
    fig = go.Figure()

    x_dates = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d) for d in df.index]

    fig.add_trace(go.Candlestick(
        x=x_dates,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Candlestick",
        increasing_line_color="#ff6b6b",
        decreasing_line_color="#4dabf7",
    ))

    if "MA5" in df.columns:
        fig.add_trace(go.Scatter(
            x=x_dates, y=df["MA5"],
            mode="lines", name="MA5",
            line=dict(color="#ffd43b", width=1.5)
        ))

    if "MA25" in df.columns:
        fig.add_trace(go.Scatter(
            x=x_dates, y=df["MA25"],
            mode="lines", name="MA25",
            line=dict(color="#69db7c", width=2)
        ))

    if "MA75" in df.columns:
        fig.add_trace(go.Scatter(
            x=x_dates, y=df["MA75"],
            mode="lines", name="MA75",
            line=dict(color="#da77f2", width=2)
        ))

    fig.update_layout(
        title=dict(text=f"{ticker} 株価チャート & 移動平均線", font=dict(size=18)),
        xaxis_rangeslider_visible=False,
        height=500,
        template="plotly_white",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        xaxis=dict(
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(step="all", label="ALL")
                ]
            )
        ),
    )
    return fig


def main():
    st.title("📈 東証株価リアルタイム確認ツール")
    st.caption("Yahoo Finance API 使用（約20分遅延）")

    with st.expander("📖 分析手法・シグナル強度の見方", expanded=False):
        col_left, col_center, col_right = st.columns(3)

        with col_left:
            st.markdown("### 分析手法")
            st.markdown("""
            | 手法 | 買いシグナル | 売りシグナル |
            |------|------------|------------|
            | **移動平均線交差** | ゴールデンクロス<br>(MA5 > MA25) | デッドクロス<br>(MA5 < MA25) |
            | **RSI** | RSI < 30 (賣超) | RSI > 70 (買超) |
            | **MACD** | MACD が Signal 線を上抜け | MACD が Signal 線を下抜け |
            | **3本線トレンド** | 価格が3本全て上回る | 価格が3本全て下回る |
            | **MA75 トレンド** | 価格 > MA75 | 価格 < MA75 |
            """)
            st.markdown("**RSI** = 相対力指数（14日）、**MACD** = 12日EMA - 26日EMA")

        with col_center:
            st.markdown("### シグナル強度")
            st.markdown("""
            | 強度 | 点数 | 対象シグナル |
            |------|------|------------|
            | 🔴 **強** | 3点 | ゴールデンクロス / RSI賣超・買超 |
            | 🟡 **中** | 2点 | MACD交差 / 3本線一致 |
            | ⚪ **弱** | 1点 | MA75トレンド乖離 |
            """)

            st.markdown("### 総合判断")
            st.markdown("""
            シグナル点数の合計で判断します。

            | 合計点 | 判定 | 色 |
            |--------|------|----|
            | **5点以上** | 🟢 **買いシグナル** | 買い優勢 |
            | 3〜4点 | 🟢 若干買い優勢 | 買い優勢 |
            | 0〜2点 | ⚪ **中立** | 均衡 |
            | ▲3〜4点 | 🔴 若干売り優勢 | 売り優勢 |
            | **▲5点以上** | 🔴 **売りシグナル** | 売り優勢 |
            """)
            st.caption("※ 買いシグナル・売りシグナルは各5点以上で発動")



    st.divider()

    if "watchlist" not in st.session_state:
        st.session_state.watchlist = load_watchlist()

    if "refresh_key" not in st.session_state:
        st.session_state.refresh_key = 0

    with st.sidebar:
        st.header("🔍 銘柄検索")
        ticker_input = st.text_input(
            "ティッカーコード",
            placeholder="例: 7203.T (トヨタ)",
            help="日本株は「証券コード.T」で入力"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ 追加", use_container_width=True):
                if ticker_input and ticker_input not in st.session_state.watchlist:
                    st.session_state.watchlist.append(ticker_input)
                    save_watchlist(st.session_state.watchlist)
                    st.rerun()
        with col2:
            if st.button("🔄 更新", use_container_width=True):
                st.session_state.refresh_key += 1
                st.rerun()

        st.divider()
        st.subheader("📋 ウォッチリスト")
        watchlist_to_remove = []
        for item in st.session_state.watchlist:
            col_item, col_del = st.columns([4, 1])
            with col_item:
                st.text(f"• {item}")
            with col_del:
                if st.button("✕", key=f"del_{item}"):
                    watchlist_to_remove.append(item)
        for item in watchlist_to_remove:
            st.session_state.watchlist.remove(item)
            save_watchlist(st.session_state.watchlist)
            st.rerun()

        st.divider()
        st.subheader("⚙️ 設定")
        auto_refresh = st.checkbox("自動更新 (30秒)", value=False)
        refresh_interval = 30

    st.divider()

    col_search_btn = st.columns([1, 4])
    with col_search_btn[0]:
        search_clicked = st.button("🔎 検索", type="primary", use_container_width=True)

    if search_clicked and ticker_input:
        quote = get_realtime_quote(ticker_input)
        if quote:
            with st.container():
                st.subheader(f"{quote['name']} ({ticker_input})")

                m_col1, m_col2, m_col3, m_col4 = st.columns(4)

                if quote["change"] > 0:
                    change_color = "🔴"
                    change_str = f"+{quote['change']:.2f} ({quote['change_pct']:+.2f}%)"
                elif quote["change"] < 0:
                    change_color = "🔵"
                    change_str = f"{quote['change']:.2f} ({quote['change_pct']:+.2f}%)"
                else:
                    change_color = "⚪"
                    change_str = f"0.00 (0.00%)"

                m_col1.metric("現在値", format_price(quote["current"], ticker_input), change_str)
                m_col2.metric("前日終値", format_price(quote["prev_close"], ticker_input))
                m_col3.metric("始値", format_price(quote["open"], ticker_input))
                m_col4.metric("出来高", format_volume(quote["volume"]))

                s_col1, s_col2, s_col3, s_col4 = st.columns(4)
                s_col1.metric("高値", format_price(quote["high"], ticker_input))
                s_col2.metric("安値", format_price(quote["low"], ticker_input))
                s_col3.metric("前日比", change_color)
                s_col4.metric("取得時刻", datetime.now().strftime("%H:%M:%S"))

                period = st.selectbox(
                    "表示期間",
                    options=["1mo", "3mo", "6mo", "1y", "2y"],
                    index=1,
                )

                df = get_stock_data(ticker_input, period)
                if df is not None:
                    df = calculate_moving_averages(df)
                    fig = plot_candlestick_with_ma(df, ticker_input)
                    st.plotly_chart(fig, use_container_width=True)

                    st.subheader("移動平均線 概要")
                    ma_col1, ma_col2, ma_col3 = st.columns(3)
                    latest = df.iloc[-1]
                    ma_col1.metric("MA5 (5日線)", format_price(latest["MA5"], ticker_input) if pd.notna(latest["MA5"]) else "-")
                    ma_col2.metric("MA25 (25日線)", format_price(latest["MA25"], ticker_input) if pd.notna(latest["MA25"]) else "-")
                    ma_col3.metric("MA75 (75日線)", format_price(latest["MA75"], ticker_input) if pd.notna(latest["MA75"]) else "-")

                    st.subheader("直近データ")
                    st.dataframe(
                        df[["Open", "High", "Low", "Close", "Volume", "MA5", "MA25", "MA75"]]
                        .tail(10)
                        .style.format({
                            "Open": "{:,.2f}",
                            "High": "{:,.2f}",
                            "Low": "{:,.2f}",
                            "Close": "{:,.2f}",
                            "Volume": "{:,.0f}",
                            "MA5": "{:,.2f}",
                            "MA25": "{:,.2f}",
                            "MA75": "{:,.2f}",
                        }),
                        use_container_width=True
                    )
                else:
                    st.error("データを取得できませんでした。ティッカーコードを確認してください。")
        else:
            st.error("銘柄が見つかりません。ティッカーコードを確認してください。")

    st.divider()
    st.subheader("📋 ウォッチリスト")

    if "selected_ticker" not in st.session_state:
        st.session_state.selected_ticker = None

    watch_data = []
    for ticker in st.session_state.watchlist:
        quote = get_realtime_quote(ticker)
        signals = None
        if quote:
            df_hist = get_stock_data(ticker, "3mo")
            if df_hist is not None:
                signals = analyze_signals(df_hist)
            change_str = f"{quote['change_pct']:+.2f}%"
            if quote["change"] > 0:
                change_str = f"🔴 {change_str}"
            elif quote["change"] < 0:
                change_str = f"🔵 {change_str}"
            watch_data.append({
                "ティッカー": ticker,
                "銘柄名": quote["name"],
                "現在値": format_price(quote["current"], ticker),
                "前日比": change_str,
                "出来高": format_volume(quote["volume"]),
                "quote": quote,
                "signals": signals,
            })
        else:
            watch_data.append({
                "ティッカー": ticker,
                "銘柄名": "取得エラー",
                "現在値": "-",
                "前日比": "-",
                "出来高": "-",
                "quote": None,
                "signals": None,
            })

    if watch_data:
        cols = st.columns(len(watch_data)) if len(watch_data) <= 4 else st.columns(4)
        for i, w in enumerate(watch_data):
            with cols[i % 4]:
                signal_label = w["signals"]["signal"] if w["signals"] else "⚪ 分析不可"
                st.markdown(f"**{w['ティッカー']}** | {signal_label}")
                st.metric("現在値", w["現在値"], w["前日比"])
                st.caption(w["銘柄名"])
                if w["signals"] and w["signals"]["buy_signals"]:
                    for sig, strength in w["signals"]["buy_signals"][:2]:
                        st.markdown(f"<span style='color:green'>• {sig}</span>", unsafe_allow_html=True)
                if w["signals"] and w["signals"]["sell_signals"]:
                    for sig, strength in w["signals"]["sell_signals"][:2]:
                        st.markdown(f"<span style='color:red'>• {sig}</span>", unsafe_allow_html=True)
                if st.button("📊 詳細", key=f"detail_{w['ティッカー']}"):
                    st.session_state.selected_ticker = w["ティッカー"]
                    st.rerun()
                st.divider()

        if st.session_state.selected_ticker:
            selected = st.session_state.selected_ticker
            st.markdown(f"### 📈 {selected} の詳細")
            if st.button("✕ 閉じる"):
                st.session_state.selected_ticker = None
                st.rerun()

            for w in watch_data:
                if w["ティッカー"] == selected:
                    quote = w["quote"]
                    if quote:
                        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                        if quote["change"] > 0:
                            change_str = f"+{quote['change']:.2f} ({quote['change_pct']:+.2f}%)"
                        elif quote["change"] < 0:
                            change_str = f"{quote['change']:.2f} ({quote['change_pct']:+.2f}%)"
                        else:
                            change_str = "0.00 (0.00%)"
                        m_col1.metric("現在値", format_price(quote["current"], selected), change_str)
                        m_col2.metric("前日終値", format_price(quote["prev_close"], selected))
                        m_col3.metric("始値", format_price(quote["open"], selected))
                        m_col4.metric("出来高", format_volume(quote["volume"]))

                        s_col1, s_col2, s_col3, s_col4 = st.columns(4)
                        s_col1.metric("高値", format_price(quote["high"], selected))
                        s_col2.metric("安値", format_price(quote["low"], selected))
                        s_col3.metric("前日比", "🔴" if quote["change"] > 0 else ("🔵" if quote["change"] < 0 else "⚪"))
                        s_col4.metric("取得時刻", datetime.now().strftime("%H:%M:%S"))

                        period = st.selectbox(
                            "表示期間",
                            options=["1mo", "3mo", "6mo", "1y", "2y"],
                            index=1,
                        )
                        df = get_stock_data(selected, period)
                        if df is not None:
                            df = calculate_moving_averages(df)
                            fig = plot_candlestick_with_ma(df, selected)
                            st.plotly_chart(fig, use_container_width=True)

                            ma_col1, ma_col2, ma_col3 = st.columns(3)
                            latest = df.iloc[-1]
                            ma_col1.metric("MA5 (5日線)", format_price(latest["MA5"], selected) if pd.notna(latest["MA5"]) else "-")
                            ma_col2.metric("MA25 (25日線)", format_price(latest["MA25"], selected) if pd.notna(latest["MA25"]) else "-")
                            ma_col3.metric("MA75 (75日線)", format_price(latest["MA75"], selected) if pd.notna(latest["MA75"]) else "-")

                        st.markdown("---")
                        st.subheader("直近データ")
                        st.dataframe(
                            df[["Open", "High", "Low", "Close", "Volume", "MA5", "MA25", "MA75"]]
                            .tail(10)
                            .style.format({
                                "Open": "{:,.2f}",
                                "High": "{:,.2f}",
                                "Low": "{:,.2f}",
                                "Close": "{:,.2f}",
                                "Volume": "{:,.0f}",
                                "MA5": "{:,.2f}",
                                "MA25": "{:,.2f}",
                                "MA75": "{:,.2f}",
                            }),
                            use_container_width=True
                        )
                    break
    else:
        st.info("ウォッチリストに銘柄を追加してください")

    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
