# Temporal-OpenClaw MVP Implementation - Execution List

**Status**: 🟡 In Progress
**Start Date**: 2026-02-28
**Target MVP**: WhatsApp-integrated agentic system with Temporal orchestration

---

## Quick Reference: Token-Saving Iteration Guide

### Daily Development Loop
```bash
# Morning: Start once
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Edit code → auto-reload (no rebuild!)
vim src/workflows/agent_workflow.py
docker-compose logs -f worker --tail=20

# Run single test (fast!)
docker-compose run --rm pytest tests/test_llm.py::test_call_llm -v

# View state files directly
cat ./state/whatsapp-*/state.md

# Evening: Stop
docker-compose down
```

### When to Rebuild (Rare)
- ✅ Only when: requirements.txt, Dockerfile, or system dependencies change
- ❌ NOT when: Python code changes (hot reload handles it!)

---

## Phase 0: Project Setup & Documentation 📚

**Goal**: Set up project structure and developer documentation

### 0.1 Documentation Files
- [x] Create `README.md` with:
  - [x] Quick start guide (3 commands to run MVP)
  - [x] WhatsApp setup instructions (Neonize)
  - [x] Architecture diagram
  - [x] Link to full plan.md
- [x] Create `CLAUDE.md` with:
  - [x] Token-saving iteration workflow (from plan.md)
  - [x] How to run specific tests
  - [x] How to view state.md files
  - [x] Common development patterns
  - [x] File structure overview
- [x] Create `.env.example` with all required variables


### 0.2 Python Project Setup
- [ ] Create `requirements.txt`
- [ ] Create `pyproject.toml` (optional)
- [ ] Create `.gitignore`

---

## Phase 1: Foundation (Week 1) 🏗️

**Goal**: Temporal infrastructure + basic workflow + state persistence

### 1.1 Docker Compose Setup
- [ ] Create `docker-compose.yml` (base/production)
- [ ] Create `docker-compose.dev.yml` (hot reload)
- [ ] Create `docker-compose.test.yml` (testing)
- [ ] Create `Dockerfile` (production)
- [ ] Create `Dockerfile.dev` (development)

### 1.2 Basic Models (Data Schemas)
- [ ] Create `src/models/messages.py` (Message, MessageRole, TokenUsage)
- [ ] Create `src/models/tools.py` (ToolDefinition, ToolCall, ToolResult)
- [ ] Create `src/models/state.py` (AgentWorkflowState, WorkflowConfig)

### 1.3 State File I/O Activity
- [ ] Create `src/activities/state_file_io.py`
- [ ] Create `src/utils/state_manager.py`
- [ ] Create tests `tests/test_activities/test_state_file_io.py`

### 1.4 Basic Agent Workflow
- [ ] Create `src/workflows/agent_workflow.py` (echo mode, no LLM)
- [ ] Create `src/worker/worker.py`
- [ ] Create tests `tests/test_workflows/test_agent_workflow.py`

---

## Phase 2: LLM Integration (Week 2) 🤖

**Goal**: Call LLM, load tools, execute bash commands

### 2.1 Tool System (Markdown-Based)
- [ ] Create 8 MVP TOOL.md files in `tools/` directory
- [ ] Create `tools/README.md`
- [ ] Create `src/utils/tool_loader.py`
- [ ] Create tests `tests/test_utils/test_tool_loader.py`

### 2.2 LLM Provider Configuration
- [ ] Create `src/llm/anthropic_client.py`
- [ ] Create `src/llm/llm.py` (LLMRegistry)
- [ ] Create tests `tests/test_llm/test_anthropic_client.py`

### 2.3 LLM Call Activity
- [ ] Create `src/activities/llm_call.py`
- [ ] Create tests `tests/test_activities/test_llm_call.py`

### 2.4 Core Tool Activities
- [ ] Create `src/activities/bash_executor.py`
- [ ] Create `src/activities/file_operations.py`
- [ ] Create tests for all activities

### 2.5 Tool Execution in Workflow
- [ ] Update workflow with LLM thinking loop
- [ ] Implement parallel tool execution
- [ ] Create integration test


---

## Phase 3: WhatsApp Integration (Week 3) 📱 **MVP CRITICAL**

**Goal**: Complete request-response loop via WhatsApp

### 3.1 WhatsApp Send Message Activity
- [ ] Create `src/activities/whatsapp.py`
- [ ] Create tests `tests/test_activities/test_whatsapp.py`

### 3.2 Neonize WhatsApp Client
- [ ] Create `src/whatsapp/listener.py`
- [ ] Create tests `tests/test_whatsapp/test_listener.py`

### 3.3 WhatsApp Listener Service
- [ ] Create `src/whatsapp/listener.py` (event-driven via neonize)
- [ ] Update `docker-compose.yml` with listener service
- [ ] Create tests `tests/test_whatsapp/test_listener.py`

### 3.4 Signal Handling in Workflow
- [ ] Add signal handlers to workflow
- [ ] Add WhatsApp response sending

### 3.5 Heartbeat Mechanism
- [ ] Implement heartbeat timer in workflow
- [ ] Configure heartbeat interval

### 3.6 End-to-End MVP Test
- [ ] Create `tests/test_integration/test_e2e_whatsapp.py`
- [ ] Test full stack with real WhatsApp

---

## Phase 4: State Management & Compaction (Week 4) 📝

### 4.1 Conversation Compaction Activity
- [ ] Create `src/activities/conversation_compaction.py`
- [ ] Integrate into workflow

### 4.2 State.md Section-Based Updates
- [ ] Update `src/utils/state_manager.py` with sections
- [ ] Update workflow to use section updates

---

## Phase 5: Error Handling & Resilience (Week 5) 🛡️

### 5.1 Activity Retry Policies
- [ ] Define retry policies in `src/worker/config.py`
- [ ] Test retry behavior

### 5.2 Error Handling in Workflow
- [ ] Add try/catch around tool execution
- [ ] Return errors to LLM

### 5.3 Worker Resilience
- [ ] Add graceful shutdown
- [ ] Add health check endpoint

---

## Phase 6: Testing & Documentation (Week 6) ✅

### 6.1 Unit Test Coverage
- [ ] Achieve 80%+ coverage

### 6.2 Integration Tests
- [ ] Create comprehensive integration tests

### 6.3 Documentation
- [ ] Complete README.md
- [ ] Complete CLAUDE.md
- [ ] Create docs/ARCHITECTURE.md
- [ ] Create docs/DEPLOYMENT.md

---

## Phase 7: Deployment & Production (Week 7-8) 🚀

### 7.1 Docker Production Images
- [ ] Optimize Dockerfile
- [ ] Create production docker-compose

### 7.2 Monitoring & Observability
- [ ] Set up logging
- [ ] Document Temporal UI usage
- [ ] Create runbook

### 7.3 Production Testing
- [ ] Load testing
- [ ] Failover testing
- [ ] End-to-end production test

---

## Quick Commands Reference

### Development
```bash
# Start dev environment
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# View logs
docker-compose logs -f worker whatsapp-listener

# Run single test
docker-compose run --rm pytest tests/test_llm.py::test_call_llm -v

# View state files
cat ./state/whatsapp-*/state.md
```

### Testing
```bash
# Unit tests
pytest tests/test_activities/ -v

# Coverage
pytest --cov=src --cov-report=term-missing

# Single test
pytest tests/test_llm.py::test_anthropic_client -v
```

### Production
```bash
# Start
docker-compose up -d

# Status
docker-compose ps

# Stop
docker-compose down
```

---

## Progress Tracking

**Current Phase**: Phase 0 (Project Setup)
**Next Milestone**: Complete Phase 1 by [DATE]

**Blockers**: None
