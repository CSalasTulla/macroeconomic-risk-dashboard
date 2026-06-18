import streamlit as st
import pandas as pd
import plotly.express as px
from fredapi import Fred

# 1. Page layout setup
st.set_page_config(page_title="Macroeconomic Dashboard", layout="wide")
st.title("🏛️ Institutional Economic Dashboard")
st.write("Tracking yield curves and economic risk indicators in real-time.")

# 2. API Connection
FRED_API_KEY = st.secrets["FRED_API_KEY"]
fred = Fred(api_key=FRED_API_KEY)

# 3. Sidebar control for the user
st.sidebar.header("Dashboard Settings")
lookback_years = st.sidebar.slider("Select Horizon (Years)", 1, 50, 25)


# 4. Data Extraction & Processing Function
@st.cache_data
def get_macro_data(years):
    # Pulling 10-Year (GS10) and 2-Year (GS2) Treasury Constant Maturity Rates
    yield_10y = fred.get_series('DGS10')
    yield_2y = fred.get_series('DGS2')
    financial_stress = fred.get_series('STLFSI4')
    recession_indicator = fred.get_series('USRECD')

    # Merge into a clean Pandas dataframe
    df = pd.DataFrame({'10Y_Yield': yield_10y, '2Y_Yield': yield_2y, 'Final_Stress': financial_stress, 'Recession_Indicator': recession_indicator})
    df.index = pd.to_datetime(df.index)
    df['Final_Stress'] = df['Final_Stress'].ffill()


    # Calculate the Spread (The classic recession predictor)
    df['Spread'] = df['10Y_Yield'] - df['2Y_Yield']

    # Slice the dataframe based on the user's slider input
    start_date = pd.Timestamp.now() - pd.DateOffset(years=years)
    return df[df.index >= start_date].dropna()


def get_recession_periods(df):
    # If the column isn't there, this line crashes the whole app with a KeyError!
    if 'Recession_Indicator' not in df.columns:
        return[]
    recession_days = df[df['Recession_Indicator'] == 1].index

    if len(recession_days) == 0:
        return []

    periods = []
    start = recession_days[0]

    for i in range(1, len(recession_days)):
        if(recession_days[i] - recession_days[i-1]).days > 4:
            periods.append((start, recession_days[i - 1]))
            start = recession_days[i]

    periods.append((start, recession_days[-1]))

    return periods


def calculate_inversion_lags(df):
    """
    Calculate the exact time between a yield curve inversion and the subsequent start of an official recession.
    """

    negative_yield_dates = df[df['Spread']<0].index

    #handling specific case where there is not negative yield dates

    if len(negative_yield_dates) == 0:
        return []

    recession_periods = get_recession_periods(df)

    lags = []

    #Find the initial inversion for each recession

    for start_date, end_date in recession_periods:
        prior_inversions = [d for d in negative_yield_dates if d < start_date]

        if prior_inversions:
            first_inversion = prior_inversions[-1]

            cluster_start = first_inversion

            for d in reversed(prior_inversions):
                if(cluster_start -d).days <= 90:
                    cluster_start = d
                else:
                    break


            delta = start_date - first_inversion
            months_lag = round(delta.days / 30.44, 1) # Average days in a month

            if 3 <= months_lag <= 36:
                lags.append({
                    'recession_start': start_date.strftime('%Y'),
                    'value_str': f"{months_lag} Months",
                    'help_text': f"Curve inverted on {cluster_start.strftime('%Y-%m-%d')}. Recession triggered {delta.days} days later."
                })

    # 5. CURRENT CYCLE CHECK (If the curve is currently inverted or recently was)
    if len(recession_periods) > 0:
        last_recession_end = recession_periods[-1][1]
        recent_inversions = [d for d in negative_yield_dates if d > last_recession_end]
    else:
        recent_inversions = list(negative_yield_dates)

    if recent_inversions:
        # Find the start of the current cycle's cluster
        current_cluster_start = recent_inversions[0]
        today = df.index[-1]
        delta_current = today - current_cluster_start
        months_current = round(delta_current.days / 30.44, 1)

        lags.append({
            'recession_start': "Current",
            'value_str': f"{months_current} Mos Ago",
            'help_text': f"Initial inversion on {current_cluster_start.strftime('%Y-%m-%d')}."
        })


    return lags

# 5. Render charts to the web interface
try:
    data = get_macro_data(lookback_years)

    #Extract the distinct historical recession windows (start and end dates) for chart shading in graph Treasury yield 10Y vs 2Y and Curve Spread
    recession_periods = get_recession_periods(data)

    latest_row = data.iloc[-1]
    latest_date = data.index[-1]

    yield_10y_today = latest_row['10Y_Yield']

    date_30_ago = latest_date - pd.Timedelta(days=30)

    historical_data = data.asof(date_30_ago)
    yield_10y_30_days_ago = historical_data['10Y_Yield']

    delta_10y = yield_10y_today - yield_10y_30_days_ago

    data_30_days = data[data.index >= date_30_ago]

    chart_clean_list_10Y = data_30_days['10Y_Yield'].tolist()

    # Split screen into two clean columns
    col1, col2 = st.columns(2)

    #10 Year Treasury Yield Chart
    with col1:

        st.metric(
            label=f"10 Year Treasury Yield(as of {latest_date.strftime('%b %d')})",
            value=f"{yield_10y_30_days_ago:.2f}%",
            delta=f"{delta_10y:+.2f}% vs 30 days ago",
            chart_data = chart_clean_list_10Y,  # Passes the 30-day timeline directly here
            chart_type = "line",  # Renders it as a smooth trendline
            border = True
        )

    yield_2y_today = latest_row['2Y_Yield']
    yield_2y_30d_ago = historical_data['2Y_Yield']
    delta_2y = yield_2y_today - yield_2y_30d_ago

    chart_clean_list_2Y = data_30_days['2Y_Yield'].tolist()

    #2Y Treasury Yield Chart
    with col2:
        st.metric(
            label=f"2Y Treasury Yield (As of {latest_date.strftime('%b %d')})",
            value=f"{yield_2y_today:.2f}%",
            delta=f"{delta_2y:+.2f}% vs 30 days ago",
            chart_data = chart_clean_list_2Y,  # Passes the 30-day timeline directly here
            chart_type = "line",  # Renders it as a smooth trendline
            border = True
        )

    financial_stress_today = latest_row['Final_Stress']
    financial_stress_30_d_ago = historical_data['Final_Stress']
    delta_financial_stress = financial_stress_today - financial_stress_30_d_ago

    col3 = st.columns(1)[0]

    #Financial Stress Chart
    with col3:
        st.metric(
            label=f"2Y Financial Stress (As of {latest_date.strftime('%b %d')})",
            value=f"{financial_stress_today:.2f}%",
            delta=f"{delta_financial_stress:+.2f}% vs 30 days ago",
            chart_data=chart_clean_list_2Y,  # Passes the 30-day timeline directly here
            chart_type="line",  # Renders it as a smooth trendline
            border=True
        )


    inversion_lags = calculate_inversion_lags(data)

    if inversion_lags:
        st.markdown("### ⏳ Historical Lag Analysis (Inversion to Recession)")

        # Create dynamic columns based on how many historical recessions are in your dataset
        metric_cols = st.columns(len(inversion_lags))

        for idx, lag in enumerate(inversion_lags):
            with metric_cols[idx]:
                st.metric(
                    label=f"{lag['recession_start']} Cycle Signal",
                    value=lag['value_str'],  # FIXED: Swapped lag['months'] for lag['value_str']
                    help=lag['help_text']  # FIXED: Swapped lag['help_text'] matching new dict
                )
        st.markdown("---")

    col5, col6 = st.columns(2)

    #Treasury Yields (10Y vs 2Y) Chart
    with col5:
        st.subheader("Treasury Yields (10Y vs 2Y)")
        fig_yields = px.line(data, x=data.index, y=['10Y_Yield', '2Y_Yield'],
                             labels={'value': 'Yield (%)', 'index': 'Date'})

        #Dynamic Shading: Gray rectangle for every recession Block
        for start,end in recession_periods:
            fig_yields.add_vrect(
                x0=start, x1=end,
                fillcolor="red", opacity=0.15,
                layer="below", line_width=0
            )
        st.plotly_chart(fig_yields, use_container_width=True)


    #Yield Curve Spread (10Y - 2Y)
    with col6:
        st.subheader("Yield Curve Spread (10Y - 2Y)")
        fig_spread = px.area(data, x=data.index, y='Spread',
                             labels={'Spread': 'Spread (%)', 'index': 'Date'})
        # Draw a clear red line at 0% to show inversions
        fig_spread.add_hline(y=0.0, line_dash="dash", line_color="red")

        for start,end in recession_periods:
            fig_spread.add_vrect(
                x0=start, x1=end,
                fillcolor="red", opacity=0.15,
                layer="below", line_width=0
            )
        st.plotly_chart(fig_spread, use_container_width=True)

except Exception as e:
    st.error(f"Waiting for valid FRED API Key connection... Error details: {e}")