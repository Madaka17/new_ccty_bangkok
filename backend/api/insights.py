"""
AI analyses read by the pages (BMA risk map, Traffy reports), Traffy history and the news.
"""
from fastapi import APIRouter, Query

from backend.core.news_feed import news_feed
from backend.services import risk_agent, traffy_agent, traffy_history

router = APIRouter()


@router.get("/api/riskbkk/analysis")
def riskbkk_analysis():
    """AI analysis of the BMA risk-map traffic layers plus the numbers behind it."""
    return risk_agent.status()

@router.post("/api/riskbkk/analysis/run")
def riskbkk_analysis_run():
    """Re-run the analysis now (operator only through access_guard)."""
    return risk_agent.run(force=True)

@router.get("/api/traffy/analysis")
def traffy_analysis():
    """AI analysis of the flood reports people sent through Traffy Fondue in the last 6 h, plus the numbers."""
    return traffy_agent.status()

@router.post("/api/traffy/analysis/run")
def traffy_analysis_run():
    """Re-run the analysis now (operator only through access_guard)."""
    return traffy_agent.run(force=True)

@router.get("/api/traffy/history")
def traffy_history_compare():
    """Traffy flood reports today vs yesterday and this week vs last week (same time), by hour / day / district."""
    return traffy_history.compare()

@router.get("/api/news")
def news(kind: str = Query(None, pattern="^(flood|accident)$")):
    """Flood and road-accident headlines from Thai news outlets' own RSS feeds, newest first (news_feed.py)."""
    return news_feed.status(kind)
