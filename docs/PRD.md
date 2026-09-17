# Product Requirements Document (PRD): LoopGuard

**Project Name:** LoopGuard  
**Hackathon:** Bharat Builds Tour (WeMakeDevs × AWS Builder Center)  
**Track:** Ship It (Deployed, Live AWS Architecture)  
**Author:** Team Kroid  
**Status:** Locked Specification (Phase 1 Baseline)  

---

## 1. Executive Summary
LoopGuard is an autonomous, event-driven circuit breaker designed to safeguard AWS serverless and agentic pipelines against runaway execution loops. By continuously evaluating invocation velocity and tracking semantic argument stagnation across tool retries, LoopGuard intercepts execution loops in flight. It derives root-cause diagnostics using Amazon Bedrock (Claude 3.5 Sonnet) and enforces targeted isolation—quarantining failing sessions via DynamoDB Time-to-Live (TTL) locks while preserving operational capacity for healthy traffic.

---

## 2. Problem Statement
Serverless architectures and Large Language Model (LLM) agent pipelines present a unique reliability vulnerability: failure through repetitive looping rather than abrupt termination.

- **Recursive Compute Cascades:** An AWS Lambda function writing to an Amazon S3 prefix or DynamoDB table can trigger circular invocations, scaling executions rapidly toward account limits.
- **Agentic Semantic Thrashing:** When an autonomous LLM agent encounters a transient database deadlock or API error, the underlying ReAct planning loop reformulates queries repeatedly, incurring token and compute costs while returning healthy HTTP 200 responses to monitoring systems.
- **Observability Latency:** Native billing tools update on an 8 to 24-hour cycle. Standard CloudWatch alarms flag raw invocation counts but lack semantic awareness, and traditional remediation actions (such as account-level IAM deny policies) cause widespread collateral downtime.

---

## 3. Goals and Rubric Alignment

| Judging Criterion | Alignment in LoopGuard |
|---|---|
| **Idea & Impact** | Solves an urgent operational failure mode across serverless architectures and generative AI agents, moving beyond simple conversational wrappers. |
| **Built on AWS** | Implements an integrated six-service serverless architecture: AWS Lambda, Amazon CloudWatch, Amazon EventBridge, Amazon Bedrock, Amazon DynamoDB, and Amazon API Gateway. |
| **Execution** | Fully functional Infrastructure as Code (AWS SAM) supporting dual blast radii, zero-bloat standard library validation, and deterministic failure recovery. |
| **Learning** | Demonstrates production-grade patterns: programmatic concurrency controls, Bedrock prompt schema constraints, and event-driven remediation. |
| **Demo Video** | Delivers an auditable, verifiable operational cycle (trigger, alarm, diagnosis, surgical isolation, and global throttle) within 180 seconds. |

---

## 4. Module Specifications & Tiered Scope

### Module 1: Telemetry & Runaway Detection Engine (Tier 1, Core)
- **Target Lambda (`GuardTargetFunction`):** Equipped with an execution safety cap (`ReservedConcurrentExecutions: 50`), session lock awareness via DynamoDB, and an asynchronous self-invocation mode to simulate runaway conditions.
- **Metric Alarm (`GuardTargetInvocationAlarm`):** CloudWatch metric alarm configured on `Invocations` ($\ge 20$ invocations in 60 seconds, single evaluation period).
- **Routing Bus:** EventBridge rule matching CloudWatch Alarm State Change where `state.value = ALARM`.
- **Stagnation Engine:** Ingests recent log streams, unpacks nested structured JSON logs, and evaluates query/argument similarity using Python's `difflib.SequenceMatcher`, flagging stagnation when consecutive arguments exceed a 70% match threshold.

### Module 2: Bedrock Diagnostic Engine (Tier 1, Core)
- **Log Ingestion:** Extracts the preceding 50 log records from `/aws/lambda/LoopGuard-TargetFunction`.
- **Model Orchestration:** Invokes Anthropic Claude 3.5 Sonnet on Amazon Bedrock with a strict JSON schema enforcing four fields: `root_cause_summary`, `detected_pattern`, `estimated_burn_rate`, and `recommended_action`.
- **Resilience:** Integrates automated retry handling, standard library dataclass/dict schema validation, and a deterministic fallback diagnostic to guarantee pipeline stability.

### Module 3: Alert & Dispatch Engine (Tier 1 Core + Tier 2 Dynamic Routing)
- **Tier 1 (Core Base Webhook Dispatch):** Orchestrator automatically formats a Discord/Slack embed card containing root-cause analysis, stagnation metrics, and HMAC-signed URLs for both remediation actions. Dispatches immediately via standard library HTTP client (`urllib.request`).
- **Tier 2 (Dynamic Team Routing):** Calls AWS Resource Groups Tagging API to resolve `Team` tags on the target function, mapping alerts to team-specific webhook channels via a DynamoDB routing table.

### Module 4: Remediation Control Plane & Rehearsal Tooling (Tier 1, Core)
- **HTTP API (`GuardHttpApi`):** Secure Amazon API Gateway endpoint exposing `/remediate`.
- **Authentication:** Validates shared secret authentication tokens before executing actions.
- **Dual Action Support:**
  - `action=session`: Enforces localized DynamoDB session locks with a 600-second TTL.
  - `action=global`: Enforces an emergency kill switch via `lambda:PutFunctionConcurrency(0)`.
- **Rehearsal Reset Script (`scripts/reset_demo.py`):** CLI utility that deletes concurrency overrides, purges DynamoDB session locks, and resets CloudWatch alarm states to OK in under 5 seconds.

### Module 5: Visual Orchestration & Reporting (Tier 2 Extension)
- **Step Functions State Machine:** Visual workflow graph lighting up state transitions in the AWS Console for video presentation.
- **Automated Postmortem to S3:** Generates a structured Markdown incident postmortem via Bedrock, uploaded to S3 with pre-signed download links.

### Module 6: Chaos Harness & Test Tooling (Tier 3 Extension)
- **Deterministic Chaos Harness:** CLI script simulating multi-turn agent deadlocks on demand.
- **Client-Side Burn Ticker:** Frontend dashboard rendering real-time compute burn rate and flatline response.

---

## 5. Acceptance Criteria (Definition of Done)

### Module 1: Telemetry & Runaway Detection Engine
- **AC 1.1:** Triggering the target function with `{"runaway_mode": true}` causes CloudWatch metric `Invocations` to cross $\ge 20$ in a 60-second window.
- **AC 1.2:** The CloudWatch alarm transitions to `ALARM` state within 65 seconds of initial trigger and emits an event to EventBridge.
- **AC 1.3:** The target function never exceeds 50 concurrent executions under any test condition (enforced by `ReservedConcurrentExecutions: 50`).

### Module 2: Bedrock Diagnostic Engine
- **AC 2.1:** The orchestrator retrieves the last 50 log lines from `/aws/lambda/LoopGuard-TargetFunction` and successfully unpacks both raw and structured JSON log envelopes.
- **AC 2.2:** `difflib.SequenceMatcher` calculates argument similarity across retried queries; queries with $\ge 70\%$ similarity are flagged with `is_stagnant: true`.
- **AC 2.3:** Amazon Bedrock (Claude 3.5 Sonnet) returns a valid JSON diagnostic within 5 seconds; if Bedrock encounters rate limits or JSON parsing errors, the deterministic fallback diagnostic engages without raising an unhandled exception.

### Module 3: Alert & Dispatch Engine
- **AC 3.1 (Tier 1):** Within 3 seconds of diagnostic completion, an incident card renders in the target webhook channel containing the root cause summary, estimated burn rate, stagnation ratio, and both remediation links.
- **AC 3.2 (Tier 2):** When dynamic routing is enabled, functions tagged `Team: Payments-Core` route to Channel A, while functions tagged `Team: Risk` route to Channel B.

### Module 4: Remediation & Surgical Control Plane
- **AC 4.1:** Clicking `action=session` writes a `SESSION#<session_id>` record to DynamoDB with a 600-second TTL within 200ms.
- **AC 4.2:** Re-invoking the quarantined session ID returns HTTP 499 (`SURGICAL_QUARANTINE_ENFORCED`) immediately, while a different session ID returns HTTP 200 (`SUCCESS`).
- **AC 4.3:** Clicking `action=global` executes `PutFunctionConcurrency(ReservedConcurrentExecutions=0)`; subsequent invocations immediately return HTTP 429 (`TooManyRequestsException`).
- **AC 4.4:** Running `scripts/reset_demo.py` restores the system to standard operational state in under 5 seconds.

---

## 6. Execution Plan & Hard Gates
- **Phase 1: Requirements & Scaffold (Day 1):** Deploy AWS SAM stack (`template.yaml`), verify IAM trust policies, Bedrock access, and DynamoDB table creation.
- **Phase 2: Core Build (Tier 1) (Days 1–2):** Implement Modules 1, 2, 4, and Tier 1 Base Webhook Dispatch. Verify the entire detect-diagnose-alert-remediate loop.
- **Phase 3: Extended Build (Tier 2) (Day 3, Cutoff: 6:00 PM):** Implement Module 3 (Team Routing) and Module 5 (Step Functions). **Hard Gate:** If Tier 2 is not fully functional and committed by Saturday 6:00 PM, stop immediately and proceed to video production with Tier 1.
- **Phase 4: Production Polish & Video Production (Day 4):** Rehearse with `scripts/reset_demo.py`, record the 180-second split-screen demo, and finalize documentation.

---

## 7. Differentiation Record

| Dimension | AWS-Native Tooling (Budgets, Cost Anomaly) | Prior Hackathon Winners (SRE Sentinel, OpsGuard) | LoopGuard |
|---|---|---|---|
| **Detection Latency** | 8 to 24-hour ingestion delay via billing reports. | Minutes to hours via retrospective log analysis. | Sub-60-second detection via metric alarms and inline checks. |
| **Detection Method** | Aggregated spend thresholds. | Log-level keyword search and container health checks. | Metric velocity combined with fuzzy semantic argument diffing (`difflib`). |
| **Blast Radius** | Account-wide IAM deny policies or full service blocks. | Manual human patches or container restarts. | Dual blast radii: surgical session-level TTL lock or global concurrency zero. |
| **System Architecture** | Open-loop passive alerting. | Open-loop reporting with human-gated approvals. | Closed-loop control system with autonomous isolation and manual override. |
| **Target Workload** | General cloud infrastructure. | Monolithic microservices and containers. | Modern serverless pipelines and Bedrock agent tool loops. |

---

## 8. Risk Register & Mitigation Strategy

| Risk Factor | Probability | Impact | Mitigation Strategy |
|---|---|---|---|
| **Bedrock Quota / Rate Limiting** | Low | High | Enforce low token generation limits (`max_tokens: 400`) and configure a local fallback diagnostic object. |
| **Alarm Ingestion Lag** | Medium | Medium | Use a 60-second evaluation period with a threshold of 20 invocations; support manual alarm override during recording if needed. |
| **Runaway Billing During Rehearsals** | Medium | High | Hardcode `ReservedConcurrentExecutions: 50` on the target function to enforce a strict concurrency ceiling. |
| **Session State Race Conditions** | Low | Medium | Utilize DynamoDB strongly consistent reads (`ConsistentRead=True`) during session lock verification. |
| **Structured Logging JSON Masking** | Medium | High | Implement recursive JSON decoding in the orchestrator log tail parser to unwrap nested CloudWatch messages. |
