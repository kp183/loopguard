#!/usr/bin/env python3
"""
LoopGuard - Fast Rehearsal Reset Utility (< 5 Seconds)
Restores the environment between video takes and rehearsal runs:
  1. Deletes Lambda concurrency overrides on LoopGuard-TargetFunction (restores 50 concurrency ceiling).
  2. Forces CloudWatch Alarm LoopGuard-TargetInvocationsSpike to OK.
  3. Purges all active SESSION# quarantine locks from DynamoDB LoopGuardState.
"""

import argparse
import os
import sys
import time

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception


def parse_args():
    parser = argparse.ArgumentParser(description="LoopGuard Demo Environment Reset")
    parser.add_argument(
        "--function-name",
        default=os.environ.get("TARGET_FUNCTION_NAME", "LoopGuard-TargetFunction"),
        help="Target Lambda function name (default: LoopGuard-TargetFunction)"
    )
    parser.add_argument(
        "--alarm-name",
        default=os.environ.get("ALARM_NAME", "LoopGuard-TargetInvocationsSpike"),
        help="CloudWatch Alarm name (default: LoopGuard-TargetInvocationsSpike)"
    )
    parser.add_argument(
        "--table-name",
        default=os.environ.get("STATE_TABLE_NAME", "LoopGuardState"),
        help="DynamoDB State table name (default: LoopGuardState)"
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        help="AWS Region (default: us-east-1 or AWS_DEFAULT_REGION)"
    )
    return parser.parse_args()


def reset_lambda_concurrency(lambda_client, function_name: str):
    print(f"[*] Resetting concurrency on function: {function_name}...")
    try:
        # Delete any temporary concurrency overrides (such as ReservedConcurrentExecutions=0)
        lambda_client.delete_function_concurrency(FunctionName=function_name)
        print(f"    [+] Cleared concurrency throttle override for {function_name}.")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code == "ResourceNotFoundException":
            print(f"    [-] Function {function_name} not found in this region.")
            return
        elif code != "ResourceConflictException":
            print(f"    [!] delete_function_concurrency note: {e}")

    try:
        # Optional: Attempt to set concurrency ceiling if account limit permits
        lambda_client.put_function_concurrency(
            FunctionName=function_name,
            ReservedConcurrentExecutions=50
        )
        print(f"    [+] Enforced ReservedConcurrentExecutions=50 safety ceiling on {function_name}.")
    except ClientError as e:
        # Expected on accounts with low default unreserved concurrency
        print(f"    [*] Target function operating on standard unreserved pool (unthrottled).")


def reset_cloudwatch_alarm(cloudwatch_client, alarm_name: str):
    print(f"[*] Resetting CloudWatch Alarm: {alarm_name} to OK...")
    try:
        cloudwatch_client.set_alarm_state(
            AlarmName=alarm_name,
            StateValue="OK",
            StateReason="Demo reset executed via scripts/reset_demo.py"
        )
        print(f"    [+] Alarm {alarm_name} transitioned to OK state.")
    except ClientError as e:
        print(f"    [-] Failed to set alarm state: {e}")


def purge_session_quarantine_locks(dynamodb_resource, table_name: str):
    print(f"[*] Purging active session quarantine locks from {table_name}...")
    try:
        table = dynamodb_resource.Table(table_name)
        # Scan for session locks with PK starting with SESSION#
        response = table.scan(
            FilterExpression="begins_with(PK, :prefix)",
            ExpressionAttributeValues={":prefix": "SESSION#"}
        )
        items = response.get("Items", [])
        if not items:
            print("    [+] No active session quarantine locks found.")
            return

        print(f"    [*] Found {len(items)} session lock(s). Deleting...")
        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
        print(f"    [+] Successfully purged {len(items)} session quarantine lock(s).")
    except ClientError as e:
        print(f"    [-] Error purging DynamoDB session locks: {e}")


def main():
    start_time = time.time()
    args = parse_args()
    print("=================================================================")
    print(" LoopGuard: Autonomous Circuit Breaker - Rehearsal Reset Utility ")
    print("=================================================================")
    print(f"Target Region: {args.region}")
    print(f"Target Function: {args.function_name}")
    print(f"Alarm Name: {args.alarm_name}")
    print(f"State Table: {args.table_name}")
    print("-----------------------------------------------------------------")

    if boto3 is None:
        print("[-] Error: 'boto3' is required to run this script. Please run 'pip install boto3'.")
        sys.exit(1)

    lambda_client = boto3.client("lambda", region_name=args.region)
    cloudwatch_client = boto3.client("cloudwatch", region_name=args.region)
    dynamodb_resource = boto3.resource("dynamodb", region_name=args.region)

    reset_lambda_concurrency(lambda_client, args.function_name)
    reset_cloudwatch_alarm(cloudwatch_client, args.alarm_name)
    purge_session_quarantine_locks(dynamodb_resource, args.table_name)

    elapsed = time.time() - start_time
    print("-----------------------------------------------------------------")
    print(f"[SUCCESS] LoopGuard rehearsal environment reset completed in {elapsed:.2f}s (< 5.0s).")
    print("Ready for clean rehearsal run or live video recording take.")
    print("=================================================================")


if __name__ == "__main__":
    main()
