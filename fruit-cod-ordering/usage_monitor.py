import json
import math
import os
import re
from datetime import datetime, timezone


METRIC_DEFINITIONS = [
    {
        "id": "fluid_active_cpu",
        "label": "Fluid Active CPU",
        "unit": "duration_seconds",
        "included_limit": 4 * 60 * 60,
        "higher_plan_limit": 16 * 60 * 60,
        "watch_at": 0.30,
    },
    {
        "id": "edge_requests",
        "label": "Edge Requests",
        "unit": "count",
        "included_limit": 1_000_000,
        "higher_plan_limit": 10_000_000,
    },
    {
        "id": "fast_origin_transfer",
        "label": "Fast Origin Transfer",
        "unit": "bytes",
        "included_limit": 10 * 1024**3,
        "higher_plan_limit": 100 * 1024**3,
    },
    {
        "id": "function_invocations",
        "label": "Function Invocations",
        "unit": "count",
        "included_limit": 1_000_000,
    },
    {
        "id": "fluid_provisioned_memory",
        "label": "Fluid Provisioned Memory",
        "unit": "gb_hours",
        "included_limit": 360,
        "higher_plan_limit": 1440,
    },
    {
        "id": "fast_data_transfer",
        "label": "Fast Data Transfer",
        "unit": "bytes",
        "included_limit": 100 * 1024**3,
        "higher_plan_limit": 1024 * 1024**3,
    },
    {
        "id": "edge_request_cpu_duration",
        "label": "Edge Request CPU Duration",
        "unit": "duration_seconds",
        "included_limit": 60 * 60,
    },
    {
        "id": "isr_reads",
        "label": "ISR Reads",
        "unit": "count",
        "included_limit": 1_000_000,
        "higher_plan_limit": 10_000_000,
    },
]


DEFAULT_USAGE_SNAPSHOT = {
    "source": "manual dashboard snapshot pasted 2026-06-29",
    "metrics": {
        "Fluid Active CPU": "1h 15m",
        "Edge Requests": "29K",
        "Fast Origin Transfer": "178.87 MB",
        "Function Invocations": "14K",
        "Fluid Provisioned Memory": "4.6 GB-Hrs",
        "Fast Data Transfer": "470.24 MB",
        "Edge Request CPU Duration": "3s",
        "ISR Reads": "74",
    },
}


SEVERITY_RANK = {
    "unknown": 0,
    "healthy": 1,
    "watch": 2,
    "warning": 3,
    "danger": 4,
}


def usage_health_report(snapshot=None):
    raw_snapshot, error, using_default = load_usage_snapshot(snapshot)
    metrics_input = raw_snapshot.get("metrics", raw_snapshot) if isinstance(raw_snapshot, dict) else {}
    source = raw_snapshot.get("source", "") if isinstance(raw_snapshot, dict) else ""
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    metrics = [
        build_metric_status(definition, metrics_input)
        for definition in METRIC_DEFINITIONS
    ]
    metrics.sort(key=lambda item: (SEVERITY_RANK[item["level"]], item["ratio"] or 0), reverse=True)

    overall = build_overall_status(metrics, error, using_default)
    return {
        "ok": not error,
        "generated_at": generated_at,
        "source": source or ("default snapshot" if using_default else "configured snapshot"),
        "using_default_snapshot": using_default,
        "snapshot_error": error,
        "overall": overall,
        "metrics": metrics,
    }


def load_usage_snapshot(snapshot=None):
    if snapshot is not None:
        return snapshot, "", False

    raw_value = os.getenv("VERCEL_USAGE_SNAPSHOT_JSON", "").strip()
    if not raw_value:
        return DEFAULT_USAGE_SNAPSHOT, "", True

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as error:
        return DEFAULT_USAGE_SNAPSHOT, f"VERCEL_USAGE_SNAPSHOT_JSON is invalid JSON: {error}", True

    if not isinstance(parsed, dict):
        return DEFAULT_USAGE_SNAPSHOT, "VERCEL_USAGE_SNAPSHOT_JSON must be a JSON object.", True

    return parsed, "", False


def build_metric_status(definition, metrics_input):
    used = find_metric_value(definition, metrics_input)
    limit = definition.get("included_limit")
    ratio = None
    level = "unknown"

    if used is not None and limit:
        ratio = used / limit
        level = level_for_ratio(ratio, definition.get("watch_at", 0.50))

    return {
        "id": definition["id"],
        "label": definition["label"],
        "level": level,
        "used": used,
        "limit": limit,
        "higher_plan_limit": definition.get("higher_plan_limit"),
        "ratio": ratio,
        "percent": round((ratio or 0) * 100, 1),
        "percent_clamped": min(round((ratio or 0) * 100, 1), 100),
        "percent_label": "n/a" if ratio is None else f"{round(ratio * 100, 1)}%",
        "used_display": "n/a" if used is None else format_metric_value(used, definition["unit"]),
        "limit_display": "n/a" if not limit else format_metric_value(limit, definition["unit"]),
        "higher_plan_limit_display": (
            format_metric_value(definition["higher_plan_limit"], definition["unit"])
            if definition.get("higher_plan_limit")
            else ""
        ),
        "message": metric_message(definition, used, ratio),
    }


def build_overall_status(metrics, error, using_default):
    if error:
        return {
            "level": "warning",
            "title": "Usage snapshot needs attention",
            "message": error,
        }

    known_metrics = [metric for metric in metrics if metric["level"] != "unknown"]
    if not known_metrics:
        return {
            "level": "unknown",
            "title": "Usage is not configured",
            "message": "No usage metrics are available yet.",
        }

    top_metric = max(
        known_metrics,
        key=lambda metric: (SEVERITY_RANK[metric["level"]], metric["ratio"] or 0),
    )

    prefix = "Seeded snapshot" if using_default else "Latest snapshot"
    if top_metric["level"] == "danger":
        title = "Usage needs action"
    elif top_metric["level"] == "warning":
        title = "Usage is getting high"
    elif top_metric["level"] == "watch":
        title = "Usage is worth watching"
    else:
        title = "Usage is healthy"

    return {
        "level": top_metric["level"],
        "title": title,
        "message": (
            f"{prefix}: {top_metric['label']} is at {top_metric['percent_label']} "
            f"of the included limit."
        ),
    }


def find_metric_value(definition, metrics_input):
    if not isinstance(metrics_input, dict):
        return None

    aliases = {
        normalize_key(definition["id"]),
        normalize_key(definition["label"]),
    }
    for key, value in metrics_input.items():
        if normalize_key(key) in aliases:
            return parse_metric_value(value, definition["unit"])
    return None


def parse_metric_value(value, unit):
    if value is None:
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)

    text = str(value).strip()
    if not text:
        return None
    text = text.split("/", 1)[0].strip()

    if unit == "duration_seconds":
        return parse_duration_seconds(text)
    if unit == "bytes":
        return parse_bytes(text)
    if unit == "gb_hours":
        return parse_number(text)
    return parse_count(text)


def parse_duration_seconds(text):
    total = 0.0
    for amount, suffix in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes|s|sec|secs|second|seconds)\b", text, flags=re.I):
        value = float(amount)
        suffix = suffix.lower()
        if suffix.startswith("h"):
            total += value * 60 * 60
        elif suffix.startswith("m"):
            total += value * 60
        else:
            total += value
    if total:
        return total
    return parse_count(text)


def parse_bytes(text):
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(b|kb|mb|gb|tb)\b", text, flags=re.I)
    if not match:
        return parse_count(text)
    value = float(match.group(1))
    unit = match.group(2).lower()
    multiplier = {
        "b": 1,
        "kb": 1024,
        "mb": 1024**2,
        "gb": 1024**3,
        "tb": 1024**4,
    }[unit]
    return value * multiplier


def parse_count(text):
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([kmb])?\b", text.replace(",", ""), flags=re.I)
    if not match:
        return None
    value = float(match.group(1))
    suffix = (match.group(2) or "").lower()
    if suffix == "k":
        value *= 1_000
    elif suffix == "m":
        value *= 1_000_000
    elif suffix == "b":
        value *= 1_000_000_000
    return value


def parse_number(text):
    return parse_count(text)


def level_for_ratio(ratio, watch_at):
    if ratio >= 0.90:
        return "danger"
    if ratio >= 0.70:
        return "warning"
    if ratio >= watch_at:
        return "watch"
    return "healthy"


def metric_message(definition, used, ratio):
    if used is None or ratio is None:
        return "No snapshot value available."
    if definition["id"] == "fluid_active_cpu" and ratio >= definition.get("watch_at", 0.50):
        return "Highest-risk metric; inspect slow request logs if this keeps climbing."
    if ratio >= 0.90:
        return "Near the included limit."
    if ratio >= 0.70:
        return "Approaching the included limit."
    if ratio >= definition.get("watch_at", 0.50):
        return "Worth watching."
    return "Comfortable."


def format_metric_value(value, unit):
    if unit == "duration_seconds":
        return format_duration(value)
    if unit == "bytes":
        return format_bytes(value)
    if unit == "gb_hours":
        return f"{value:g} GB-Hrs"
    return format_count(value)


def format_duration(seconds):
    seconds = int(round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def format_bytes(value):
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(value)
    unit_index = 0
    while abs(amount) >= 1024 and unit_index < len(units) - 1:
        amount /= 1024
        unit_index += 1
    return f"{amount:.2f} {units[unit_index]}" if unit_index else f"{int(amount)} B"


def format_count(value):
    amount = float(value)
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:g}M"
    if amount >= 1_000:
        return f"{amount / 1_000:g}K"
    return f"{int(amount)}"


def normalize_key(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
