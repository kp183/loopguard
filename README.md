# LoopGuard
> Real-time, closed-loop circuit breaker and surgical session isolation for serverless and Bedrock agent pipelines on AWS.

LoopGuard detects runaway execution loops—such as recursive Lambda self-invocations and autonomous LLM agents trapped in semantic tool-retry loops—while they are actively occurring. Instead of waiting hours for billing alarms or applying blunt account-wide throttles, LoopGuard captures runtime telemetry via CloudWatch and EventBridge, performs real-time fuzzy stagnation analysis, generates a schema-validated root cause analysis using Amazon Bedrock (Claude 3.5 Sonnet), and enables surgical session-level quarantine via DynamoDB Time-to-Live (TTL) locks alongside an emergency global concurrency kill switch.

---

## Architecture Overview

LoopGuard functions as an event-driven closed-loop control system:

```
[Upstream Client / Test]
         │
         ▼
[GuardTargetFunction] ──(ConsistentRead=True)──> [DynamoDB: LoopGuardState (SESSION#<id>)]
         │                                                      │
    (Runaway Loop)                                         (HTTP 499 if Quarantined)
         ▼
[CloudWatch Metrics (Invocations >= 20 / 60s)]
         │
         ▼
[CloudWatch Alarm: LoopGuard-TargetInvocationsSpike]
         │
         ▼
[Amazon EventBridge Rule]
         │
         ▼
[GuardOrchestratorFunction]
   ├── 1. Defensive Dimension Parsing (dict or list format)
   ├── 2. CloudWatch Log Tail Fetch & Recursive JSON Log Unwrapping
   ├── 3. difflib.SequenceMatcher Stagnation Scoring (>= 0.70)
   ├── 4. Bedrock (Claude 3.5 Sonnet) RCA Synthesis
   ├── 5. Persist Incident Audit Record (INCIDENT#<id>)
   └── 6. Base Webhook Dispatch (Discord/Slack Embed with HMAC Links)
                                    │
                                    ▼
                          [Webhook Notification]
                           ├── Surgical Isolation: action=session
                           └── Global Kill Switch: action=global
                                    │
                                    ▼
                         [GuardHttpApi (/remediate)]
                                    │
                                    ▼
                        [GuardRemediationFunction]
                           ├── action=session ──> Write SESSION#<id> LOCK (TTL 600s) to DynamoDB
                           └── action=global  ──> Set Target Concurrency = 0 via Lambda API
```

- **Target Execution Layer:** An AWS Lambda function executes transactions while checking an active DynamoDB quarantine registry before running or re-invoking.
- **Metric Detection Layer:** CloudWatch Alarms evaluate execution spikes over a 60-second window, emitting state-change events directly into Amazon EventBridge upon threshold breach.
- **Orchestration & Analysis Engine:** An orchestrator Lambda retrieves recent log events, runs fuzzy sequence matching to detect semantic parameter stagnation across retries, and invokes Amazon Bedrock to extract structured diagnostics (root cause, pattern, estimated burn rate).
- **Targeted Remediation Engine:** An API Gateway endpoint accepts cryptographically validated remediation tokens, allowing operators to trigger either surgical session isolation (halting only the affected session ID via a 10-minute DynamoDB TTL lock) or an emergency global throttle (setting function concurrency to 0).

---

## Core AWS Services Used

| Service | Architectural Role in LoopGuard |
|---|---|
| **AWS Lambda** | Target execution, alarm orchestration, diagnostic extraction, and concurrency remediation. |
| **Amazon CloudWatch** | High-frequency metric alarms tracking invocation rates and structured JSON execution logs. |
| **Amazon EventBridge** | Event bus capturing alarm state transitions and routing them directly to orchestrator handlers. |
| **Amazon Bedrock** | Foundation model inference (Claude 3.5 Sonnet) delivering schema-enforced root-cause analysis. |
| **Amazon DynamoDB** | Single-table state store managing active incidents and session-scoped TTL quarantine locks. |
| **Amazon API Gateway** | HTTP API exposing secure callback routes for authenticated remediation actions. |

---

## Architectural Differentiation

| Dimension | AWS-Native Tooling (Budgets, Cost Anomaly) | Prior Hackathon Winners (SRE Sentinel, OpsGuard) | LoopGuard |
|---|---|---|---|
| **Detection Latency** | 8 to 24-hour ingestion delay via billing reports. | Minutes to hours via retrospective log analysis. | Sub-60-second detection via metric alarms and inline checks. |
| **Detection Method** | Aggregated spend thresholds. | Log-level keyword search and container health checks. | Metric velocity combined with fuzzy semantic argument diffing (`difflib`). |
| **Blast Radius** | Account-wide IAM deny policies or full service blocks. | Manual human patches or container restarts. | Dual blast radii: surgical session-level TTL lock or global concurrency zero. |
| **System Architecture** | Open-loop passive alerting. | Open-loop reporting with human-gated approvals. | Closed-loop control system with autonomous isolation and manual override. |
| **Target Workload** | General cloud infrastructure. | Monolithic microservices and containers. | Modern serverless pipelines and Bedrock agent tool loops. |

---

## Note on Project Lineage & Independence

LoopGuard is an infrastructure-level, closed-loop reliability system built natively using serverless AWS primitives (AWS SAM, EventBridge, Bedrock, DynamoDB). It is structurally and architecturally distinct from prior LLM observability dashboards and post-incident analysis tools (such as AgentLens and Clarity). LoopGuard operates at the infrastructure control plane to manipulate runtime concurrency and session states, maintaining zero shared code, frameworks, or dependencies with earlier projects.

---

## Quickstart & Deployment

### Prerequisites
- AWS CLI installed and configured with appropriate administrator credentials.
- AWS SAM CLI installed (`sam --version >= 1.100.0`).
- Python 3.11 or 3.12 installed locally.
- Amazon Bedrock model access enabled for Anthropic Claude 3.5 Sonnet (`anthropic.claude-3-5-sonnet-20240620-v1:0`) in your deployment region.

### Build and Deploy
```bash
# Clone repository
git clone https://github.com/team-kroid/loopguard.git
cd loopguard

# Build application artifacts
sam build

# Deploy infrastructure to AWS
sam deploy --guided
```

During guided deployment, specify:
- **Stack Name:** `LoopGuardStack`
- **AWS Region:** `us-east-1` or `us-west-2`
- **Parameter WebhookUrl:** Target Slack or Discord webhook URL for incident dispatch (or leave empty).
- **Parameter HmacSecret:** Enter a secure secret token.
- Allow SAM CLI to create IAM roles and confirm authorization.

---

## Verification & Testing

### 1. Trigger Runaway Execution Loop
Initiate an asynchronous runaway loop with an active session ID:
```bash
aws lambda invoke \
  --function-name LoopGuard-TargetFunction \
  --invocation-type Event \
  --payload '{"runaway_mode": true, "session_id": "session-runaway-01"}' \
  out.json
```

### 2. Verify Alarm Trigger and Bedrock RCA
Monitor orchestrator execution logs:
```bash
sam logs -n LoopGuard-OrchestratorFunction --tail
```
Confirm that the CloudWatch alarm transitions to ALARM, the log tail is retrieved, fuzzy similarity is computed, and Bedrock generates a structured root-cause diagnostic.

### 3. Apply Surgical Session Isolation
Call the remediation endpoint with `action=session`:
```bash
curl -i "https://<api-id>.execute-api.<region>.amazonaws.com/remediate?token=<TOKEN>&action=session&session_id=session-runaway-01&incident_id=INC-TEST"
```
Re-invoke using the quarantined session ID to verify it returns HTTP 499 (`SURGICAL_QUARANTINE_ENFORCED`), while concurrent invocations with a different session ID execute with HTTP 200 (`SUCCESS`).

### 4. Apply Emergency Global Kill Switch
Call the remediation endpoint with `action=global`:
```bash
curl -i "https://<api-id>.execute-api.<region>.amazonaws.com/remediate?token=<TOKEN>&action=global&function=LoopGuard-TargetFunction&incident_id=INC-TEST"
```
Verify that reserved concurrency is set to 0:
```bash
aws lambda get-function-concurrency --function-name LoopGuard-TargetFunction
```

### 5. Fast Rehearsal Reset (< 5 Seconds)
Restore the environment between video takes and rehearsal drills:
```bash
python scripts/reset_demo.py
```

---

## License
MIT License. Built for the Bharat Builds Tour (WeMakeDevs × AWS Builder Center).
