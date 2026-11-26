PROJECT_NAME = "周转托盘回空回收"
ROLE = "周转器具结算员"
MODEL_LABEL = "分层 Kaplan–Meier"
TARGET = "censored"
UNIT = "天"
ACTION_LABEL = "派回空提货单"
RESERVE_LABEL = "同链路回收班组"
DEFAULT_DAY = 144
DEFAULT_BUDGET = 16
REPORT_LAG = 1
GROUPS = ("县域专线", "同城循环", "干线中转", "门店联配")
SIGNAL_NAMES = ("elapsed", "turnover", "lane_distance", "load_units")
WATCH_FEATURE = "elapsed"
METRIC_LABEL = "已回空单平均绝对误差"
FIELD_LABELS = {
    "age": "已在途天数",
    "loops": "近月流转次数",
    "distance": "往返里程 km",
    "collectors": "可到仓提货班组",
    "pallets": "同运单托盘数",
    "deposit": "单托押金 元",
    "disputed": "押金争议",
}
FIELD_BOUNDS = {
    "age": (0, 24),
    "loops": (1, 20),
    "distance": (3, 190),
    "collectors": (0, 6),
    "pallets": (1, 25),
    "deposit": (15, 85),
    "disputed": (0, 1),
}
CRITICAL_FIELDS = frozenset(("age", "deposit", "disputed"))
