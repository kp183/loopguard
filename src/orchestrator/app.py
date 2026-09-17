"""
LoopGuard - Incident Diagnostic Orchestrator (GuardOrchestratorFunction)
Processes CloudWatch Alarm state changes, extracts log streams, unwraps JSON envelopes,
computes semantic stagnation with difflib, calls Amazon Bedrock (Claude 3.5 Sonnet)
for root cause analysis, records incident state, and dispatches webhook alerts.
"""

import dataclasses
import difflib
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
logs_client = boto3.client("logs")
dynamodb = boto3.resource("dynamodb")
bedrock_client = boto3.client("bedrock-runtime")

STATE_TABLE_NAME = os.environ.get("STATE_TABLE_NAME", "LoopGuardState")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
REMEDIATION_ENDPOINT = os.environ.get(
    "REMEDIATION_ENDPOINT",
    os.environ.get("CONTROL_API_URL", "https://localhost/remediate")
)
if not REMEDIATION_ENDPOINT.endswith("/remediate"):
    REMEDIATION_ENDPOINT = f"{REMEDIATION_ENDPOINT}/remediate"

HMAC_SECRET = os.environ.get(
    "REMEDIATION_AUTH_TOKEN",
    os.environ.get("HMAC_SECRET", "kroid-guard-sec-token-2026")
)
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "us.anthropic.claude-sonnet-4-20250514-v1:0"
)

state_table = dynamodb.Table(STATE_TABLE_NAME)


@dataclasses.dataclass
class DiagnosticResult:
    root_cause_summary: str
    detected_pattern: str
    estimated_burn_rate: str
    recommended_action: str

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def generate_hmac_token(secret: str, message: str) -> str:
    """Generates an HMAC-SHA256 signature for authenticated remediation links."""
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def extract_target_function_name(event: Dict[str, Any]) -> str:
    """
    Defensively parses the target function name from EventBridge CloudWatch alarm events.
    Trap Defense: EventBridge emits CloudWatch alarm dimensions either as a dictionary
    ({'FunctionName': '...'}) or as a list of objects ([{'name': 'FunctionName', 'value': '...'}]).
    """
    detail = event.get("detail", {})
    if not isinstance(detail, dict):
        return "LoopGuard-TargetFunction"

    # Direct dimensions check if present
    dimensions = detail.get("dimensions")
    if isinstance(dimensions, dict) and "FunctionName" in dimensions:
        return dimensions["FunctionName"]
    elif isinstance(dimensions, list):
        for dim in dimensions:
            if isinstance(dim, dict) and dim.get("name") == "FunctionName":
                return dim.get("value", "LoopGuard-TargetFunction")

    # Deep configuration metrics check
    config = detail.get("configuration", {})
    metrics = config.get("metrics", [])
    if isinstance(metrics, list):
        for metric_item in metrics:
            metric_stat = metric_item.get("metricStat", {})
            metric = metric_stat.get("metric", {})
            metric_dims = metric.get("dimensions", {})
            if isinstance(metric_dims, dict) and "FunctionName" in metric_dims:
                return metric_dims["FunctionName"]
            elif isinstance(metric_dims, list):
                for dim in metric_dims:
                    if isinstance(dim, dict) and dim.get("name") == "FunctionName":
                        return dim.get("value", "LoopGuard-TargetFunction")

    return "LoopGuard-TargetFunction"


def unwrap_log_message(raw_message: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Recursively unwraps CloudWatch JSON structured log messages.
    Trap Defense: In template.yaml, LoggingConfig: LogFormat: JSON causes AWS Lambda
    to wrap stdout inside an outer JSON object ({"timestamp": "...", "level": "INFO", "message": "..."}).
    data["message"] may be a nested JSON string or already parsed dict.
    """
    cleaned = raw_message.strip()
    try:
        data = json.loads(cleaned)
    except Exception:
        return None, cleaned

    if not isinstance(data, dict):
        return None, cleaned

    # Check if this is the outer Lambda JSON envelope
    if "message" in data:
        inner_msg = data["message"]
        if isinstance(inner_msg, dict):
            return inner_msg, str(inner_msg)
        elif isinstance(inner_msg, str):
            inner_cleaned = inner_msg.strip()
            if inner_cleaned.startswith("{") and inner_cleaned.endswith("}"):
                try:
                    inner_data = json.loads(inner_cleaned)
                    if isinstance(inner_data, dict):
                        return inner_data, inner_cleaned
                except Exception:
                    pass
            return data, inner_cleaned

    return data, cleaned


def fetch_recent_log_events(function_name: str, limit: int = 50) -> Tuple[List[str], List[str], Optional[str]]:
    """
    Retrieves the last log lines for the target function and extracts query payloads and session IDs.
    Returns: (raw_log_lines, query_payloads, latest_session_id)
    """
    log_group_name = f"/aws/lambda/{function_name}"
    raw_lines: List[str] = []
    queries: List[str] = []
    session_id: Optional[str] = None

    try:
        # Describe log streams ordered by LastEventTime descending
        streams_resp = logs_client.describe_log_streams(
            logGroupName=log_group_name,
            orderBy="LastEventTime",
            descending=True,
            limit=3
        )
        streams = streams_resp.get("logStreams", [])
        if not streams:
            logger.info(json.dumps({"event": "no_log_streams_found", "log_group": log_group_name}))
            return raw_lines, queries, session_id

        # Read events from the most recent stream
        for stream in streams:
            stream_name = stream["logStreamName"]
            events_resp = logs_client.get_log_events(
                logGroupName=log_group_name,
                logStreamName=stream_name,
                limit=limit,
                startFromHead=False
            )
            events = events_resp.get("events", [])
            for ev in events:
                msg = ev.get("message", "")
                raw_lines.append(msg)
                payload_dict, _ = unwrap_log_message(msg)
                if payload_dict:
                    if "session_id" in payload_dict and not session_id:
                        session_id = str(payload_dict["session_id"])
                    if "query_payload" in payload_dict:
                        queries.append(str(payload_dict["query_payload"]))

            if queries and session_id:
                break

    except ClientError as err:
        logger.warning(json.dumps({
            "event": "guard_log_fetch_warning",
            "error": str(err),
            "log_group": log_group_name
        }))

    return raw_lines[-limit:], queries, session_id


def compute_stagnation_ratio(queries: List[str]) -> Tuple[float, bool]:
    """
    Computes fuzzy similarity across sequential tool queries using Python's difflib.SequenceMatcher.
    Formula: S_stagnant = (1 / (N - 1)) * sum( (2 * M(q_i, q_i+1)) / (|q_i| + |q_i+1|) )
    Threshold: S_stagnant >= 0.70 flags is_stagnant = True.
    """
    if len(queries) < 2:
        return 0.0, False

    total_similarity = 0.0
    comparisons = len(queries) - 1

    for i in range(comparisons):
        q1 = queries[i].strip()
        q2 = queries[i + 1].strip()
        matcher = difflib.SequenceMatcher(None, q1, q2)
        total_similarity += matcher.ratio()

    ratio = total_similarity / comparisons
    is_stagnant = ratio >= 0.70
    return round(ratio, 4), is_stagnant


def generate_fallback_diagnostic(function_name: str, stagnation_ratio: float, is_stagnant: bool) -> DiagnosticResult:
    """Generates a guaranteed, deterministic diagnostic result if Bedrock is unreachable or rate-limited."""
    pattern = "SEMANTIC_RETRY_STAGNATION" if is_stagnant else "HIGH_VELOCITY_CASCADE_LOOP"
    burn_rate = "~30-60 invocations/min ($0.15-$0.50/min at scale)"
    summary = (
        f"Automated analysis detected invocation velocity breach on {function_name}. "
        f"Semantic argument stagnation ratio={stagnation_ratio:.3f} indicates repetitive agent retry thrashing."
    )
    action = (
        "Enforce surgical session quarantine via action=session to isolate the failing session without downtime."
    )
    return DiagnosticResult(
        root_cause_summary=summary,
        detected_pattern=pattern,
        estimated_burn_rate=burn_rate,
        recommended_action=action
    )


def invoke_bedrock_diagnostic(
    function_name: str,
    stagnation_ratio: float,
    is_stagnant: bool,
    recent_logs: List[str]
) -> DiagnosticResult:
    """
    Synthesizes a root-cause diagnostic using Amazon Bedrock (Anthropic Claude 3.5 Sonnet).
    Enforces a strict 4-key JSON schema with automatic fallback.
    """
    prompt = f"""Human: You are LoopGuard's automated incident diagnostics engine.
Analyze the following CloudWatch log lines from monitored AWS Lambda function '{function_name}'.
The telemetry pipeline computed a semantic argument stagnation ratio of {stagnation_ratio:.3f} (is_stagnant={is_stagnant}).

Recent logs:
{chr(10).join(recent_logs[-15:])}

You MUST return ONLY a valid JSON object with EXACTLY these four keys and no preamble or explanation:
{{
  "root_cause_summary": "<One sentence explaining why the loop occurred>",
  "detected_pattern": "<SEMANTIC_RETRY_STAGNATION | RECURSIVE_CASCADE_LOOP | POISON_PILL_BATCH>",
  "estimated_burn_rate": "<Estimated invocations or dollar cost burn per minute>",
  "recommended_action": "<Recommended surgical or global remediation step>"
}}

Assistant:"""

    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 400,
            "temperature": 0.0,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        })

        response = bedrock_client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=body
        )

        response_body = json.loads(response["body"].read().decode("utf-8"))
        content = response_body.get("content", [])
        if content and isinstance(content, list):
            text = content[0].get("text", "").strip()
            # Clean markdown JSON block formatting if present
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            parsed = json.loads(text.strip())

            # Validate expected keys
            required_keys = ["root_cause_summary", "detected_pattern", "estimated_burn_rate", "recommended_action"]
            if all(k in parsed for k in required_keys):
                return DiagnosticResult(
                    root_cause_summary=str(parsed["root_cause_summary"]),
                    detected_pattern=str(parsed["detected_pattern"]),
                    estimated_burn_rate=str(parsed["estimated_burn_rate"]),
                    recommended_action=str(parsed["recommended_action"])
                )

    except Exception as err:
        logger.warning(json.dumps({
            "event": "guard_bedrock_invocation_fallback",
            "error": str(err),
            "model_id": BEDROCK_MODEL_ID
        }))

    return generate_fallback_diagnostic(function_name, stagnation_ratio, is_stagnant)


def dispatch_webhook_notification(
    webhook_url: str,
    incident_id: str,
    target_function: str,
    session_id: str,
    stagnation_ratio: float,
    diagnostic: DiagnosticResult,
    surgical_url: str,
    global_url: str
) -> bool:
    """
    Tier 1 Base Webhook Dispatch.
    Dispatches a structured embed card to Discord or Slack using Python standard library urllib.
    Zero external dependencies required.
    """
    if not webhook_url or webhook_url.startswith("https://placeholder") or webhook_url.strip() == "":
        logger.info(json.dumps({
            "event": "guard_webhook_skipped_no_url",
            "incident_id": incident_id,
            "surgical_url": surgical_url,
            "global_url": global_url
        }))
        return False

    # Universal payload structured for Discord and Slack webhooks
    card = {
        "content": f"🚨 **LoopGuard Circuit Breaker Alert: {incident_id}**",
        "embeds": [
            {
                "title": f"Runaway Loop Intercepted: `{target_function}`",
                "color": 15158332,  # Crimson Red
                "fields": [
                    {"name": "Target Function", "value": f"`{target_function}`", "inline": True},
                    {"name": "Session ID", "value": f"`{session_id}`", "inline": True},
                    {"name": "Stagnation Ratio", "value": f"**{stagnation_ratio:.3f}** (Threshold: 0.700)", "inline": True},
                    {"name": "Detected Pattern", "value": f"`{diagnostic.detected_pattern}`", "inline": True},
                    {"name": "Estimated Burn Rate", "value": diagnostic.estimated_burn_rate, "inline": True},
                    {"name": "Root Cause Summary", "value": diagnostic.root_cause_summary, "inline": False},
                    {
                        "name": "🎯 Surgical Session Isolation (10m TTL Lock)",
                        "value": f"[Click to Quarantine Session `{session_id}`]({surgical_url})",
                        "inline": False
                    },
                    {
                        "name": "🛑 Global Emergency Override (Kill Switch)",
                        "value": f"[Click to Throttle Target Concurrency to 0]({global_url})",
                        "inline": False
                    }
                ],
                "footer": {
                    "text": "LoopGuard Autonomous Reliability Engine • Bharat Builds Tour"
                }
            }
        ]
    }

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(card).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "LoopGuard-AlertEngine/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            logger.info(json.dumps({
                "event": "guard_webhook_dispatched",
                "incident_id": incident_id,
                "status_code": response.status
            }))
            return True
    except urllib.error.URLError as e:
        logger.error(json.dumps({
            "event": "guard_webhook_dispatch_error",
            "error": str(e),
            "incident_id": incident_id
        }))
        return False


def lambda_handler(event, context):
    """
    Main Orchestrator Entrypoint.
    Triggered by EventBridge rule on CloudWatch Alarm State Change (ALARM).
    """
    logger.info(json.dumps({
        "event": "guard_orchestrator_triggered",
        "raw_event": event
    }))

    # 1. Defensive Dimension Parsing
    target_function = extract_target_function_name(event)
    alarm_name = event.get("detail", {}).get("alarmName", "LoopGuard-TargetInvocationsSpike")
    incident_id = f"INC-{int(time.time())}"

    # 2. Ingest Log Streams and Unwrap Nested JSON Messages
    raw_logs, queries, extracted_session = fetch_recent_log_events(target_function, limit=50)
    session_id = extracted_session or "session-live-01"

    # 3. Compute Semantic Stagnation Ratio (difflib)
    stagnation_ratio, is_stagnant = compute_stagnation_ratio(queries)

    # 4. Amazon Bedrock Claude 3.5 Sonnet Diagnostic Analysis
    diagnostic = invoke_bedrock_diagnostic(
        function_name=target_function,
        stagnation_ratio=stagnation_ratio,
        is_stagnant=is_stagnant,
        recent_logs=raw_logs
    )

    # 5. Persist Incident Audit Record in DynamoDB (Single Table Schema)
    try:
        state_table.put_item(
            Item={
                "PK": f"INCIDENT#{incident_id}",
                "SK": "METADATA",
                "target_function": target_function,
                "session_id": session_id,
                "alarm_name": alarm_name,
                "stagnation_ratio": str(stagnation_ratio),
                "is_stagnant": is_stagnant,
                "root_cause_summary": diagnostic.root_cause_summary,
                "detected_pattern": diagnostic.detected_pattern,
                "estimated_burn_rate": diagnostic.estimated_burn_rate,
                "status": "ANALYZED",
                "ttl": int(time.time()) + 86400  # 24-hour audit retention
            }
        )
        logger.info(json.dumps({
            "event": "guard_incident_persisted",
            "incident_id": incident_id,
            "session_id": session_id
        }))
    except ClientError as e:
        logger.error(json.dumps({
            "event": "guard_incident_persist_error",
            "error": str(e),
            "incident_id": incident_id
        }))

    # 6. Generate Authenticated Remediation URLs
    token_session = generate_hmac_token(HMAC_SECRET, f"{incident_id}:session:{session_id}")
    token_global = generate_hmac_token(HMAC_SECRET, f"{incident_id}:global:{target_function}")

    surgical_url = (
        f"{REMEDIATION_ENDPOINT}?"
        f"token={token_session}&action=session&session_id={session_id}&incident_id={incident_id}"
    )
    global_url = (
        f"{REMEDIATION_ENDPOINT}?"
        f"token={token_global}&action=global&function={target_function}&incident_id={incident_id}"
    )

    # 7. Dispatch Webhook Card (Tier 1 Core)
    dispatch_webhook_notification(
        webhook_url=WEBHOOK_URL,
        incident_id=incident_id,
        target_function=target_function,
        session_id=session_id,
        stagnation_ratio=stagnation_ratio,
        diagnostic=diagnostic,
        surgical_url=surgical_url,
        global_url=global_url
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "incident_id": incident_id,
            "target_function": target_function,
            "session_id": session_id,
            "stagnation_ratio": stagnation_ratio,
            "is_stagnant": is_stagnant,
            "diagnostic": diagnostic.to_dict(),
            "surgical_url": surgical_url,
            "global_url": global_url
        })
    }
