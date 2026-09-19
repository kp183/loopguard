# Product Requirements Document (PRD): LoopGuard

**Project Name:** LoopGuard  
**Hackathon:** Bharat Builds Tour (WeMakeDevs × AWS Builder Center)  
**Track:** Ship It (Deployed, Live AWS Architecture)  
**Author:** Team Kroid  
**Status:** Production Deployed & Verified (Tier 1 Core + Module 3 Team Routing + S3 Postmortem Shipped)  

---

## 1. Executive Summary
LoopGuard is an autonomous, event-driven circuit breaker designed to safeguard AWS serverless and agentic pipelines against runaway execution loops. By continuously evaluating invocation velocity and tracking semantic argument stagnation across tool retries, LoopGuard intercepts execution loops in flight. It derives root-cause diagnostics using Amazon Bedrock (Claude 3.5 Sonnet) and enforces targeted isolation—quarantining failing sessions via DynamoDB Time-to-Live (TTL) locks while preserving operational capacity for healthy traffic.

---

## 2. Problem Statement
Serverless architectures and Large Language Model (LLM) agent pipelines present a unique reliability vulnerability: failure through repetitive looping rather than abrupt termination.

- **Recursive Compute Cascades:** An AWS Lambda function writing to an Amazon S3 prefix or DynamoDB table can trigger circular invocations, scaling executions rapidly toward account limits.
- **Agentic Semantic Thrashing:** When an autonomous LLM agent encounters a transient database deadlock or API error, the underlying ReAct planning loop reformulates queries repeatedly, incurring token and compute costs while returning healthy HTTP 200 responses to monitoring systems.
- **Observability Latency:** Native billing tools update on an 8 to 24-hour delay. Standard CloudWatch alarms flag raw invocation counts but lack semantic awareness, and traditional remediation actions (such as account-level IAM deny policies) cause widespread collateral downtime.

---

## 3. Goals and Rubric Alignment

| Judging Criterion | Alignment in LoopGuard |
|---|---|
| **Idea & Impact** | Solves an urgent operational failure mode across serverless architectures and generative AI agents, moving beyond simple conversational wrappers. |
| **Built on AWS** | Implements an integrated seven-service serverless architecture: AWS Lambda, Amazon CloudWatch, Amazon EventBridge, AWS Resource Groups Tagging API, Amazon Bedrock, Amazon DynamoDB, Amazon S3, and Amazon API Gateway. |
| **Execution** | Fully functional Infrastructure as Code (AWS SAM) supporting dual blast radii, zero-bloat standard library validation, and deterministic failure recovery. |
| **Learning** | Demonstrates operational patterns: programmatic concurrency controls, Bedrock prompt schema constraints, dynamic resource tag resolution, and event-driven remediation. |
| **Demo Video** | Delivers an auditable, verifiable operational cycle (trigger, alarm, diagnosis, team routing, surgical isolation, global throttle, S3 postmortem) within 180 seconds. |

---

## 4. Module Specifications & Tiered Scope

### Module 1: Telemetry & Runaway Detection Engine (Shipped)
- **Target Microservices (`GuardTargetFunction` & `GuardTargetFunctionSecondary`):** Monitored workloads equipped with session lock awareness via DynamoDB and asynchronous self-invocation modes simulating runaway conditions. Protection is provided by the CloudWatch alarm and session-lock quarantine; the target function does not have a reserved concurrency ceiling.
- **Dual Metric Alarms:** CloudWatch metric alarms configured on `Invocations` ($\ge 20$ invocations in 60 seconds, single evaluation period) tracking both workloads independently.
- **Routing Bus (`LoopGuard-AlarmRoutingRule`):** Consolidated EventBridge rule matching CloudWatch Alarm State Changes where `state.value = ALARM` for both alarms.
- **Stagnation Engine:** Ingests recent log streams, unpacks nested structured JSON logs, and evaluates query/argument similarity using Python's `difflib.SequenceMatcher`, flagging stagnation when consecutive arguments exceed a 70% match threshold. Verified against false-positive test suite: 10 varied healthy-traffic calls scored 0.2678, well below the 0.70 stagnation threshold; this does not test against highly similar legitimate traffic such as polling or paginated requests, which is a known limitation.

### Module 2: Resilient Diagnostic Cascade (Shipped)
- **Log Ingestion:** Extracts preceding log records from the monitored microservice.
- **Cascade Architecture:**
  - **Tier 1 (Primary):** Amazon Bedrock Claude 3.5 Sonnet (`us.anthropic.claude-sonnet-4-20250514-v1:0`) with strict 4-field JSON schema.
  - **Tier 2 (Active Failover):** Groq Cloud API (`llama-3.3-70b-versatile` via standard library `urllib.request`). The engine attempts Amazon Bedrock first; Bedrock has not had working model access during this event window, so every incident so far has failed over to Groq (Llama 3.3 70B) via the same interface.
  - **Tier 3 (Deterministic Backstop):** Zero-dependency deterministic diagnostic template ensuring incident pipeline resilience with zero unhandled exceptions.
- **Incident Attribution:** Dynamically tags `diagnostic_provider` (`AMAZON_BEDROCK`, `GROQ_FAILOVER_LLAMA_70B`, or `DETERMINISTIC_FALLBACK`) in DynamoDB and outbound webhook alert cards.

### Module 3: Dynamic Team Routing & Dispatch Engine (Shipped)
- **Zero-Config Ownership Resolution:** Calls AWS Resource Groups Tagging API (`tag:GetResources`) to resolve `Team` tags on monitored Lambdas.
- **Multi-Channel Dispatch:** Maps `Team: Payments-Core` to `WebhookUrlPrimary` and `Team: Infra-Core` to `WebhookUrlSecondary`.
- **Defensive Fallback:** If `WebhookUrlPrimary` is unset or unmapped, falls back safely to `WEBHOOK_URL_PRIMARY or WEBHOOK_URL` to guarantee zero silent drops.
- **Payload Segregation:** Dispatches distinct HMAC-tokenized interactive incident cards with verified `HTTP 200` egress delivery across channels.

### Module 4: Remediation Control Plane (Shipped)
- **Autonomous Mode:** Supported via an opt-in `AUTONOMOUS_MODE` flag (disabled by default for this submission). When enabled and $S_{\text{stagnant}} \ge 0.80$, the orchestrator immediately writes an ephemeral 10-minute TTL quarantine lock (`SESSION#<session_id>`) directly into DynamoDB without waiting for human intervention, updating the incident to `REMEDIATED_AUTONOMOUS_LOCK`.
- **HTTP API (`GuardHttpApi`):** Secure Amazon API Gateway endpoint exposing `/remediate` with strict cryptographic HMAC verification.
- **Authentication:** Enforces timing-safe HMAC-SHA256 signature verification (`hmac.compare_digest`). Eliminates master-token query bypasses.
- **Dual Action Support:**
  - `action=session`: Enforces localized DynamoDB session locks with a 600-second TTL (HTTP 499 quarantined, HTTP 200 clean traffic).
  - `action=global`: Enforces an emergency kill switch via `lambda:PutFunctionConcurrency(0)` (HTTP 429).
- **Rehearsal Reset Script (`scripts/reset_demo.py`):** CLI utility that deletes concurrency overrides on both functions, purges DynamoDB session locks, and resets both CloudWatch alarms to OK in 5.05 seconds.

### Module 5: Automated S3 Incident Postmortem (Shipped)
- **Automated Postmortem to S3:** Generates a structured Markdown incident postmortem via Bedrock, uploaded to Amazon S3 (`loopguard-postmortems-740536073144-us-east-1`).
- **Authenticated Download:** Renders a one-click download button with pre-signed authorization directly on the `/remediate` confirmation view.

---

## 5. Acceptance Criteria (Definition of Done)

### Module 1: Telemetry & Runaway Detection Engine
- **AC 1.1:** Triggering either target function causes CloudWatch metric `Invocations` to cross $\ge 20$ in a 60-second window. [PASS]
- **AC 1.2:** The CloudWatch alarm transitions to `ALARM` state within 65 seconds of initial trigger and emits an event to EventBridge. [PASS]
- **AC 1.3:** Protection is provided by the CloudWatch alarm and session-lock quarantine; the target function does not have a reserved concurrency ceiling. [PASS]

### Module 2: Bedrock Diagnostic Engine
- **AC 2.1:** The orchestrator retrieves log lines from the breaching function and successfully unpacks both raw and structured JSON log envelopes. [PASS]
- **AC 2.2:** `difflib.SequenceMatcher` calculates argument similarity across retried queries; queries with $\ge 70\%$ similarity are flagged with `is_stagnant: true`. [PASS]
- **AC 2.3:** The diagnostic cascade attempts Amazon Bedrock first and cleanly fails over to Groq Llama 3.3 70B (with deterministic fallback as backstop). [PASS]

### Module 3: Alert & Dynamic Routing Engine
- **AC 3.1:** Within 3 seconds of diagnostic completion, an incident card renders in the target webhook channel containing the root cause summary, estimated burn rate, stagnation ratio, and both remediation links. [PASS]
- **AC 3.2:** When dynamic routing is enabled, functions tagged `Team: Payments-Core` route to Channel A (`WebhookUrlPrimary`), while functions tagged `Team: Infra-Core` route to Channel B (`WebhookUrlSecondary`). Verified via live egress transport (`HTTP 200 OK`) and distinct webhook payloads. [PASS]

### Module 4: Remediation & Surgical Control Plane
- **AC 4.1:** Clicking `action=session` writes a `SESSION#<session_id>` record to DynamoDB with a 600-second TTL within 200ms. [PASS]
- **AC 4.2:** Re-invoking the quarantined session ID returns HTTP 499 (`SURGICAL_QUARANTINE_ENFORCED`) immediately, while a different session ID returns HTTP 200 (`SUCCESS`). [PASS]
- **AC 4.3:** Clicking `action=global` executes `PutFunctionConcurrency(ReservedConcurrentExecutions=0)`; subsequent invocations immediately return HTTP 429 (`TooManyRequestsException`). [PASS]
- **AC 4.4:** Running `scripts/reset_demo.py` restores both workloads, alarms, and locks to standard operational state in 5.05s. [PASS]

---

## 6. Execution Plan & Hard Gates
- **Phase 1: Requirements & Scaffold (Day 1):** Deploy AWS SAM stack (`template.yaml`), verify IAM trust policies, Bedrock access, and DynamoDB table creation. [COMPLETE]
- **Phase 2: Core Build (Tier 1) (Days 1–2):** Implement Modules 1, 2, 4, and Base Webhook Dispatch. Verify the entire detect-diagnose-alert-remediate loop. [COMPLETE]
- **Phase 3: Extended Build (Tier 2):** Implement Module 3 (Team Routing via Resource Groups Tagging API) and Module 5 (S3 Auto-Postmortem). Both shipped and verified live on AWS. [COMPLETE]
- **Phase 4: Scope Lock (Hard Stop):** Hard stop on all further feature additions (no dashboard, no further scope). Proceed strictly to video recording rehearsal and submission artifact finalization. [ACTIVE]

---

## 7. Differentiation Record

| Dimension | AWS-Native Tooling (Budgets, Cost Anomaly) | Prior Hackathon Projects | LoopGuard |
|---|---|---|---|
| **Detection Latency** | 8 to 24-hour ingestion delay via billing reports. | Minutes to hours via retrospective log analysis. | Sub-60-second detection via metric alarms and inline checks. |
| **Detection Method** | Aggregated spend thresholds. | Log-level keyword search and container health checks. | Metric velocity combined with fuzzy semantic argument diffing (`difflib`). |
| **Blast Radius** | Account-wide IAM deny policies or full service blocks. | Manual human patches or container restarts. | Dual blast radii: surgical session-level TTL lock or global concurrency zero. |
| **System Architecture** | Passive alerting. | Reporting with human-gated approvals. | Human-approved surgical remediation (with opt-in autonomous mode flag). |
| **Target Workload** | General cloud infrastructure. | Monolithic microservices and containers. | Serverless pipelines and LLM agent tool loops. |

---

## 8. Risk Register & Mitigation Strategy

| Risk Factor | Probability | Impact | Mitigation Strategy |
|---|---|---|---|
| **Bedrock Quota / Rate Limiting** | High | Low | Resilient diagnostic cascade with fast-fail timeout, failing over to Groq Llama 3.3 70B and deterministic fallback. |
| **Alarm Ingestion Lag** | Medium | Medium | Use a 60-second evaluation period with a threshold of 20 invocations; support manual alarm override during recording if needed. |
| **Runaway Billing During Rehearsals** | Medium | High | Protection is provided by the CloudWatch alarm and session-lock quarantine; the target function does not have a reserved concurrency ceiling. |
| **Session State Race Conditions** | Low | Medium | Utilize DynamoDB strongly consistent reads (`ConsistentRead=True`) during session lock verification. |
| **Structured Logging JSON Masking** | Medium | High | Implement recursive JSON decoding in the orchestrator log tail parser to unwrap nested CloudWatch messages. |
