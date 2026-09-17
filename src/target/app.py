"""
LoopGuard - Monitored Target Workload (GuardTargetFunction)
Simulates an agentic/serverless workload with inline DynamoDB session lock checks
and controlled asynchronous self-invocation loops to demonstrate runaway failure modes.
"""

import json
import logging
import os
import time
import uuid
import boto3
from botocore.exceptions import ClientError

# Configure structured logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

STATE_TABLE_NAME = os.environ.get("STATE_TABLE_NAME", "LoopGuardState")
TARGET_FUNCTION_NAME = os.environ.get("TARGET_FUNCTION_NAME", "LoopGuard-TargetFunction")
state_table = dynamodb.Table(STATE_TABLE_NAME)


def check_session_quarantine(session_id: str) -> bool:
    """
    Performs a strongly consistent read against DynamoDB to verify if the session
    has been placed into surgical quarantine.
    Trap Defense: ConsistentRead=True prevents eventual consistency race conditions during rapid retries.
    """
    try:
        response = state_table.get_item(
            Key={
                "PK": f"SESSION#{session_id}",
                "SK": "LOCK"
            },
            ConsistentRead=True
        )
        item = response.get("Item")
        if item:
            # Check TTL if present
            ttl = item.get("ttl", 0)
            if ttl == 0 or ttl > time.time():
                return True
        return False
    except ClientError as err:
        logger.error(json.dumps({
            "event": "guard_session_check_error",
            "error": str(err),
            "session_id": session_id
        }))
        return False


def build_stagnant_query(iteration: int) -> str:
    """
    Generates slightly mutated SQL/tool queries across retries,
    simulating an LLM agent reformulating failing queries (semantic stagnation).
    """
    base_query = "SELECT account_id, balance, risk_score FROM ledger_transactions WHERE status = 'pending_verification'"
    mutations = [
        f"{base_query} ORDER BY created_at DESC LIMIT 10",
        f"{base_query} AND retry_counter = {iteration} ORDER BY created_at DESC LIMIT 10",
        f"{base_query} AND retry_sequence = {iteration} LIMIT 10",
        f"{base_query} AND attempt_id = {iteration} ORDER BY transaction_id ASC",
        f"{base_query} /* retry attempt {iteration} */ ORDER BY created_at DESC",
    ]
    return mutations[iteration % len(mutations)]


def lambda_handler(event, context):
    """
    Target Lambda handler.
    Evaluates in-flight session quarantine before processing.
    """
    # Defensive input parsing
    if isinstance(event, str):
        try:
            event = json.loads(event)
        except Exception:
            event = {}

    session_id = event.get("session_id", f"session-{uuid.uuid4().hex[:8]}")
    runaway_mode = event.get("runaway_mode", False)
    iteration = int(event.get("iteration", 1))
    max_iterations = int(event.get("max_iterations", 25))

    # 1. Inline Circuit Breaker: Strongly Consistent Session Lock Check
    if check_session_quarantine(session_id):
        # Explicit log string for CloudWatch citation & verification
        logger.warning(json.dumps({
            "event": "guard_circuit_breaker_triggered",
            "status": "SURGICAL_QUARANTINE_ENFORCED",
            "session_id": session_id,
            "message": f"blocked: session {session_id} quarantined"
        }))
        return {
            "statusCode": 499,
            "body": json.dumps({
                "status": "SURGICAL_QUARANTINE_ENFORCED",
                "message": f"blocked: session {session_id} quarantined",
                "session_id": session_id
            })
        }

    # 2. Simulate Workload Execution & Log Query Payload
    current_query = build_stagnant_query(iteration)
    logger.info(json.dumps({
        "event": "agent_query",
        "session_id": session_id,
        "iteration": iteration,
        "query_payload": current_query,
        "timestamp": time.time()
    }))

    # 3. Asynchronous Self-Invocation Runaway Loop Simulation
    if runaway_mode and iteration < max_iterations:
        next_payload = {
            "runaway_mode": True,
            "session_id": session_id,
            "iteration": iteration + 1,
            "max_iterations": max_iterations
        }
        try:
            lambda_client.invoke(
                FunctionName=TARGET_FUNCTION_NAME,
                InvocationType="Event",
                Payload=json.dumps(next_payload)
            )
            logger.info(json.dumps({
                "event": "guard_self_invoke_dispatched",
                "session_id": session_id,
                "next_iteration": iteration + 1
            }))
        except ClientError as e:
            logger.error(json.dumps({
                "event": "guard_self_invoke_error",
                "error": str(e),
                "session_id": session_id
            }))

        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "RUNAWAY_RETRY_DISPATCHED",
                "session_id": session_id,
                "iteration": iteration,
                "query_payload": current_query
            })
        }

    # Standard healthy termination
    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "SUCCESS",
            "session_id": session_id,
            "iteration": iteration,
            "message": "Execution completed normally."
        })
    }
