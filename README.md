# LoopGuard
> Real-time, closed-loop circuit breaker and surgical session isolation for serverless and Bedrock agent pipelines on AWS.

LoopGuard detects runaway execution loops—such as recursive Lambda self-invocations and autonomous LLM agents trapped in semantic tool-retry loops—while they are actively occurring. Instead of waiting hours for billing alarms or applying blunt account-wide throttles, LoopGuard captures runtime telemetry via CloudWatch and EventBridge, performs real-time fuzzy stagnation analysis, generates a schema-validated root cause analysis using Amazon Bedrock (Claude 3.5 Sonnet), and enables surgical session-level quarantine via DynamoDB Time-to-Live (TTL) locks alongside an emergency global concurrency kill switch.

---

## Architecture Overview

LoopGuard functions as an event-driven closed-loop control system:

```
[Upstream Client / Microservice]
         │
         ├── Payments-Core Workload (Team: Payments-Core) ──> [DynamoDB: LoopGuardState (SESSION#<id>)]
         └── Infra-Core Workload    (Team: Infra-Core)    ──> (HTTP 499 if Quarantined)
                  │
             (Runaway Loop)
                  ▼
[Dual CloudWatch Metric Alarms (Invocations >= 20 / 60s)]
         ├── LoopGuard-TargetInvocationsSpike
         └── LoopGuard-TargetSecondaryInvocationsSpike
                  │
                  ▼
[Amazon EventBridge Rule (LoopGuard-AlarmRoutingRule)]
                  │
                  ▼
[GuardOrchestratorFunction]
   ├── 1. Alarm Dimension Extraction & Log Tail Fetch
   ├── 2. difflib.SequenceMatcher Stagnation Scoring (>= 0.70)
   ├── 3. Amazon Bedrock (Claude 3.5 Sonnet) RCA Synthesis
   ├── 4. AWS Resource Groups Tagging API (tag:GetResources) Team Resolution
   ├── 5. Persist Incident Audit Record (INCIDENT#<id>)
   └── 6. Dynamic Team Webhook Dispatch (HMAC-tokenized Alert Cards)
            ├── Payments-Core Alert ──> Channel A (WebhookUrlPrimary)
            └── Infra-Core Alert    ──> Channel B (WebhookUrlSecondary)
                                                │
                                                ▼
                                    [GuardHttpApi (/remediate)]
                                                │
                                                ▼
                                   [GuardRemediationFunction]
                                      ├── action=session ──> Write SESSION#<id> LOCK (TTL 600s) to DynamoDB
                                      ├── action=global  ──> Set Target Concurrency = 0 via Lambda API
                                      └── S3 Postmortem  ──> Generate & Upload SRE Incident Report (.md)
```

- **Target Execution Layer:** Multiple monitored microservices (`LoopGuard-TargetFunction` and `LoopGuard-TargetFunctionSecondary`) tagged with team ownership (`Team: Payments-Core`, `Team: Infra-Core`), evaluating strongly consistent DynamoDB session locks before execution.
- **Metric Detection Layer:** Dual CloudWatch Alarms track per-function invocation velocity, streaming state changes into Amazon EventBridge.
- **Orchestration & Dynamic Routing Engine:** Orchestrator retrieves structured execution logs, calculates fuzzy parameter stagnation (`difflib.SequenceMatcher`), derives root cause diagnostics via Amazon Bedrock (Claude 3.5 Sonnet), resolves resource ownership via AWS Resource Groups Tagging API, and routes alerts dynamically to dedicated team webhooks.
- **Targeted Remediation & S3 Postmortem Engine:** Cryptographically validated HMAC links enable one-click surgical session isolation (10m DynamoDB TTL lock) or global concurrency shutdowns, while automatically compiling and archiving Markdown SRE postmortems to Amazon S3 with pre-signed download URLs.

---

## Core AWS Services Used

| Service | Architectural Role in LoopGuard |
|---|---|
| **AWS Lambda** | Monitored target microservices, alarm orchestration, diagnostic extraction, and remediation execution. |
| **Amazon CloudWatch** | Velocity alarms ($\ge 20$ invocations/60s) and structured JSON log streaming. |
| **Amazon EventBridge** | Real-time event bus capturing multi-alarm state transitions and routing to the orchestrator. |
| **AWS Resource Groups Tagging API** | Zero-config dynamic ownership resolution (`tag:GetResources`) mapping microservices to team channels. |
| **Amazon Bedrock** | Foundation model inference (Claude 3.5 Sonnet) delivering schema-enforced root-cause analysis. |
| **Amazon DynamoDB** | Single-table state store managing incident audit logs and session-scoped TTL quarantine locks. |
| **Amazon S3** | Secure long-term storage for auto-generated Markdown SRE incident postmortems with pre-signed URLs. |
| **Amazon API Gateway** | Authenticated HTTP API (`/remediate`) validating HMAC signature tokens. |

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
- **AWS Region:** `us-east-1`
- **Parameter WebhookUrlPrimary:** Primary webhook URL for Team `Payments-Core` (e.g., Discord or Webhook.site).
- **Parameter WebhookUrlSecondary:** Secondary webhook URL for Team `Infra-Core`.
- **Parameter RemediationAuthToken:** HMAC secret token for `/remediate` signature verification.
- **Parameter BedrockModelId:** `us.anthropic.claude-sonnet-4-20250514-v1:0` or foundation model ID.
- Allow SAM CLI to create IAM roles and confirm authorization.

---

## Verification & Operational Testing

### 1. Trigger Runaway Workloads (Multi-Team)
Initiate an asynchronous runaway loop on either or both microservices:
```bash
# Payments-Core Workload
aws lambda invoke \
  --function-name LoopGuard-TargetFunction \
  --invocation-type Event \
  --cli-binary-format raw-in-base64-out \
  --payload '{"runaway_mode": true, "session_id": "sess-live-payments-88"}' \
  out.json

# Infra-Core Workload
aws lambda invoke \
  --function-name LoopGuard-TargetFunctionSecondary \
  --invocation-type Event \
  --cli-binary-format raw-in-base64-out \
  --payload '{"runaway_mode": true, "session_id": "sess-live-infra-99"}' \
  out.json
```

### 2. Verify Alarm Trigger, Tag Resolution & Dual-Channel Webhook Delivery
Monitor orchestrator execution logs:
```bash
sam logs -n LoopGuard-OrchestratorFunction --tail
```
Confirm:
- Invocations breach velocity threshold ($\ge 20$ in 60s).
- CloudWatch Alarm fires and EventBridge invokes `LoopGuard-OrchestratorFunction`.
- Fuzzy stagnation ratio calculated via `difflib.SequenceMatcher` ($S_{\text{stagnant}} \ge 0.70$).
- Tag resolution queries `tag:GetResources`, resolving `Payments-Core` or `Infra-Core`.
- Distinct alert payloads land in `WebhookUrlPrimary` and `WebhookUrlSecondary` with `HTTP 200` egress receipts.

### 3. Apply Surgical Session Isolation (0% Blast Radius)
Click the surgical quarantine link or invoke the remediation API:
```bash
curl -i "https://<api-id>.execute-api.us-east-1.amazonaws.com/remediate?token=<HMAC_TOKEN>&action=session&session_id=sess-live-payments-88&incident_id=INC-LIVE"
```
Re-invoke using the quarantined session ID to verify it returns **`HTTP 499 (SURGICAL_QUARANTINE_ENFORCED)`**, while concurrent requests with a healthy session ID return **`HTTP 200 (SUCCESS)`**.

### 4. Download SRE Incident Postmortem (.md) from S3
Upon remediation, the confirmation screen renders a one-click download button for an automated, audit-ready Markdown incident postmortem stored in Amazon S3 (`loopguard-postmortems-...`) with pre-signed authorization.

### 5. Apply Emergency Global Kill Switch
Click the emergency global kill switch or execute:
```bash
curl -i "https://<api-id>.execute-api.us-east-1.amazonaws.com/remediate?token=<HMAC_TOKEN>&action=global&function=LoopGuard-TargetFunction&incident_id=INC-LIVE"
```
Verify that function concurrency is set to 0, instantly throttling all new invocations (**`HTTP 429 TooManyRequestsException`**).

### 6. Fast Rehearsal Reset (< 6 Seconds)
Restore both functions, clear concurrency throttles, purge quarantine locks, and reset alarms to `OK`:
```bash
python scripts/reset_demo.py
```

---

## License
MIT License. Built for the Bharat Builds Tour (WeMakeDevs × AWS Builder Center).

