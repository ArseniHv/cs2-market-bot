"""
Shared result dataclasses returned by all analytics components.
Using dataclasses keeps results structured and easy to pass between components.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class LiquidityResult:
    item_name: str
    score: float
    interpretation: str  # "highly liquid" / "moderate" / "illiquid"
    rolling_7d_avg_volume: float
    median_price: float


@dataclass
class InflationResult:
    item_name: str
    avg_7d: float
    avg_30d: float
    deviation_pct: float
    alert_tier: int        # 0=none, 1=mild, 2=significant, 3=superflag
    alert_label: str       # "", "🟡 mild", "🟠 significant", "🚨 SUPERFLAG"
    volume_confirmed: bool # True if volume also elevated (superflag condition)
    is_anomaly: bool       # True if price spike but volume normal


@dataclass
class SpikeResult:
    item_name: str
    z_score: float
    deviation_pct: float
    alert_tier: int
    alert_label: str
    current_price: float
    rolling_avg: float


@dataclass
class TrendResult:
    item_name: str
    slope: float
    classification: str  # "strong uptrend" / "uptrend" / "sideways" / "downtrend" / "strong downtrend"
    last_14_prices: list[float] = field(default_factory=list)


@dataclass
class CategoryResult:
    category: str
    median_price_index: float
    inflation_rate: float
    most_liquid_item: str
    least_liquid_item: str
    item_count: int


@dataclass
class AlertState:
    item_name: str
    last_inflation_tier: int = 0
    last_spike_tier: int = 0
    last_alert_time: Optional[str] = None  # ISO format string