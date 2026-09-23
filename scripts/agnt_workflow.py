"""
User-Interactive Agent Workflow for RakshaQuant.
Orchestrates market regime, news sentiment, and risk analysis based on a conversational user query.
"""

import asyncio
import os
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph

from src.agents.market_regime import market_regime_node as run_market_regime_node
from src.agents.news_analyst import NewsAnalyst
from src.config.settings import get_settings
from src.market.yfinance_feed import YFinanceFeed

import logging
logger = logging.getLogger(__name__)


# 1. Extended TradingState to carry user context and stock data
class InteractiveTradingState(TypedDict):
    user_query: str
    target_symbol: str
    market_data: dict[str, Any]
    regime: str
    regime_confidence: float
    news_sentiment: dict[str, Any]
    risk_assessment: dict[str, Any]
    final_response: str


# Initialize LLM
settings = get_settings()
# print(f"api key for {settings.groq_model_primary}: {settings.groq_api_key.get_secret_value()}")
llm = ChatGroq(
    model_name=settings.groq_model_primary,
    api_key=settings.groq_api_key.get_secret_value(),
)


# --- Node 1: Query Parser / Intent Extractor ---
def parse_user_query_node(state: InteractiveTradingState) -> dict[str, Any]:
    """Extracts ticker symbol and intent from the user query."""
    query = state["user_query"]
    prompt = f"""
    You are an intent extraction agent for an Indian stock market (NSE) trading bot.
    Extract the primary NSE stock symbol from this query and output ONLY the clean ticker symbol (e.g., RELIANCE, TCS, KOTAKBANK).
    If no specific stock is mentioned, return 'NIFTY'.

    User Query: "{query}"
    """
    response = llm.invoke(
        [SystemMessage(content="Return only the ticker string."), HumanMessage(content=prompt)]
    )
    symbol = response.content.strip().upper().replace(".NS", "")

    # Fetch live price data via YFinance
    feed = YFinanceFeed()
    raw_data = feed.get_quote(f"{symbol}.NS")

    return {"target_symbol": symbol, "market_data": raw_data}


# --- Node 2: Market Regime Analysis ---
def market_regime_node(state: InteractiveTradingState) -> dict[str, Any]:
    """Evaluates market regime for the extracted stock."""
    agent_state = {
        "market_data": {state["target_symbol"]: state["market_data"]},
        "indicators": {},
        "memory_lessons": [],
        "news_sentiment": state.get("news_sentiment", {}),
        "market_mood": {},
        "prediction_signals": [],
    }
    result = run_market_regime_node(agent_state)
    return {
        "regime": result.get("regime", "ranging"),
        "regime_confidence": result.get("regime_confidence", 0.5),
    }


# --- Node 3: News & Sentiment Analysis ---
def news_sentiment_node(state: InteractiveTradingState) -> dict[str, Any]:
    """Fetches and evaluates news sentiment for the target stock."""
    sentiment = asyncio.run(NewsAnalyst().get_stock_sentiment(state["target_symbol"]))
    return {"news_sentiment": sentiment.to_dict()}


async def async_news_sentiment_node(state: InteractiveTradingState) -> dict[str, Any]:
    """Async variant used by callers that already run an event loop."""
    sentiment = await NewsAnalyst().get_stock_sentiment(state["target_symbol"])
    return {"news_sentiment": sentiment.to_dict()}


# --- Node 4: Synthesis & Final Answer Node ---
def interactive_response_node(state: InteractiveTradingState) -> dict[str, Any]:
    """Synthesizes agent finding outputs into a clear, direct conversational answer."""
    prompt = f"""
    You are RakshaQuant's AI Assistant. Answer the user's query using the multi-agent findings below.

    User Query: "{state["user_query"]}"
    Target Stock: {state["target_symbol"]}
    Market Data: {state["market_data"]}
    Market Regime: {state["regime"]} (Confidence: {state["regime_confidence"] * 100:.0f}%)
    News Sentiment: {state.get("news_sentiment", {})}

    Provide a concise, direct response with:
    1. Direct recommendation or answer to their question.
    2. Key technical regime indicators.
    3. Sentiment summary.
    4. Important risk warning/stop-loss advice.
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"final_response": response.content}


# --- Build Graph Workflow ---
def create_interactive_graph(async_mode: bool = False):
    workflow = StateGraph(InteractiveTradingState)

    # Add Nodes
    workflow.add_node("parse_query", parse_user_query_node)
    workflow.add_node("market_regime", market_regime_node)
    workflow.add_node(
        "news_sentiment",
        async_news_sentiment_node if async_mode else news_sentiment_node,
    )
    workflow.add_node("synthesize", interactive_response_node)

    # Define Edges / Execution Flow
    workflow.set_entry_point("parse_query")
    workflow.add_edge("parse_query", "market_regime")
    workflow.add_edge("market_regime", "news_sentiment")
    workflow.add_edge("news_sentiment", "synthesize")
    workflow.add_edge("synthesize", END)

    return workflow.compile()


# --- CLI Runner for Testing ---
if __name__ == "__main__":
    app = create_interactive_graph()

    user_input = input("Ask RakshaQuant a question (e.g., 'Should I buy RELIANCE today?'): ")

    initial_state = {
        "user_query": user_input,
        "target_symbol": "",
        "market_data": {},
        "regime": "",
        "regime_confidence": 0.0,
        "news_sentiment": {},
        "risk_assessment": {},
        "final_response": "",
    }

    output = app.invoke(initial_state)
    print("\n" + "=" * 50)
    print(output["final_response"])
    print("=" * 50)
