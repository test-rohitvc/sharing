# BMO Loan Pre-Booking Backend System

An asynchronous backend processing system designed to automate the ingestion, parsing, AI-driven approval checks, data extraction, document scrutiny, and automated booking datasheet generation for home loan requests.

The system incorporates **FastAPI** for its high-performance REST API layer, **RabbitMQ** as a centralized enterprise message broker, **Celery Workers** for asynchronous pipeline processing, and **LangGraph** to orchestrate state transitions and Human-in-the-Loop (HITL) verification points via dedicated resumption queues.

---

## Table of Contents
1. [System Architecture & Workflow](#system-architecture--workflow)
2. [Data Processing Pipeline Stages](#data-processing-pipeline-stages)
3. [LangGraph State Machine Topology](#langgraph-state-machine-topology)
4. [Technology Stack](#technology-stack)
5. [Database Schema & ER Model](#database-schema--er-model)
6. [Project Directory Layout](#project-directory-layout)
7. [API Routing Reference](#api-routing-reference)
8. [Setup & Installation](#setup--installation)
9. [Database Seeding & Management](#database-seeding--management)
10. [Production Considerations](#production-considerations)

---

## System Architecture & Workflow

The BMO Loan Pre-Booking system is built on an event-driven, multi-worker architecture that completely decouples task production, ingestion, heavy document processing, and manual review states:

```mermaid
graph TD
    subgraph External Email System
        A[Email Producer Service] -->|Dispatches Email Task| B{RabbitMQ Broker}
    end

    subgraph BMO Celery Ingestion & Pipeline Worker
        B -->|Consumes Email Task| C[Celery Ingestion Worker]
        C -->|Downloads Attachments & Creates Loan Request| D[(Shared Database)]
        C -->|Spawns Pipeline Nodes| E[LangGraph Processing Engine]
    end

    subgraph LangGraph Orchestration & HITL Loop
        E -->|AI Node Fails/Awaits HITL| F[Halt Graph & Update Status]
        G[FastAPI REST Layer] -->|Reviewer Action/Override| H[Publish Resume Message]
        H -->|Dedicated Resume Queue| B
        B -->|Consumes Resume Task| I[Celery Resumption Worker]
        I -->|Fetches JSON State & Injects Input| E
    end

    subgraph Data Output
        E -->|Pipeline Completed| J[Excel/openpyxl Generator]
        J -->|Dispatches Notification| K(SMTP Email Service)
    end

```

1. **Decoupled Ingestion**: An external system triggers an email task by publishing it directly to a shared **RabbitMQ** queue. The BMO Celery Ingestion worker consumes this task, downloads the attached binary files, and initializes the core loan request database record.
2. **Asynchronous LangGraph Processing**: The core pipeline worker executes intensive computational processing (document parsing, entity extraction, AI verification) sequentially using a state machine layout.
3. **State Management & Persistence**: After every node execution, the intermediate transactional state is saved as a serialized JSON object inside the database, enabling perfect fault-tolerance and effortless workflow recovery.
4. **Human-in-the-Loop (HITL) Queue**: When AI confidence thresholds drop or data mismatches are detected, LangGraph securely **halts** its graph execution context. Once a reviewer provides input via the FastAPI web dashboard, a message is dispatched to a specialized resumption worker queue to safely restore the JSON state and continue processing.

---

## Data Processing Pipeline Stages

The system coordinates loan applications through these precise behavioral states:

| Status Name | Description | Next Triggered Task / Consumer |
| --- | --- | --- |
| `INGESTED` | Task consumed from RabbitMQ; attachments downloaded and raw metadata persisted. | `process_doc_parsing` (Pipeline Worker) |
| `DOCS_PARSED` | Input files successfully targeted and structured by the `DocParser` module. | `process_entity_extraction` (Pipeline Worker) |
| `ENTITIES_EXTRACTED` | Key-value entities completely parsed out by the processing engine. | `process_approval_check` (Pipeline Worker) |
| `APPROVAL_PASSED` | Automated AI safety and verification policies completely satisfied. | `process_doc_scrutiny` (Pipeline Worker) |
| `SCRUTINY_PASSED` | Discrepancies between extracted fields and reference systems found to be zero. | `process_booking_datasheet` (Pipeline Worker) |
| `PENDING_MANUAL_REVIEW` | Automated AI precheck failed. Graph halted; awaiting user decision. | Pushed to **Resumption Worker Queue** on HTTP override |
| `PENDING_SCRUTINY_REVIEW` | Discrepancy flags triggered. Graph halted; awaiting reviewer scrutiny adjustment. | Pushed to **Resumption Worker Queue** on HTTP override |
| `PENDING_BOOKING_REVIEW` | Spreadsheet layout ready. Graph halted; awaiting reviewer structural sign-off. | Pushed to **Resumption Worker Queue** on HTTP approval |
| `BOOKING_APPROVED` | Spreadsheet finalized. Dispatches SMTP traffic toward delivery targets. | `COMPLETED` or `EMAIL_SEND_FAILED` |
| `COMPLETED` | Booking workbook securely written to storage and successfully delivered via SMTP. | *Terminal state* |
| `REJECTED` | Request explicitly canceled by an authorized human reviewer. | *Terminal state* |
| `ERROR` | Unhandled code failure, exception, or physical parsing timeout. | Requires admin intervention |
| `EMAIL_SEND_FAILED` | Spreadsheet compilation succeeded, but SMTP gateways refused delivery. | `retry_booking_email` endpoint |

---

## LangGraph State Machine Topology

To enforce transactional sanity and track complex state logic across multiple nodes, the system implements a **LangGraph StateGraph** defined in `app/pipeline/orchestrator.py` with the following structure:

* **State Representation**: The orchestrator tracks a `LoanPipelineState` typed dictionary that contains transient state variables (like `loan_request_id`, `current_node`, `result`, `hitl_required`, `hitl_decision`).
* **Graph Topology**:
* `doc_parsing` → `entity_extraction` → `approval_check`
* `approval_check` routes to:
* `PASS` → `doc_scrutiny`
* `FAIL` → `hitl_approval_wait` *(Suspends; awaits HTTP decision)*
* `ERROR` → `END` (Terminal)


* `hitl_approval_wait` resumes and routes to:
* `APPROVE` → `doc_scrutiny`
* `REJECT` → `END` (Terminal)


* `doc_scrutiny` routes to:
* `VALID` → `booking_datasheet`
* `INVALID` → `hitl_scrutiny_wait` *(Suspends; awaits HTTP decision)*
* `ERROR` → `END` (Terminal)


* `hitl_scrutiny_wait` resumes and routes to:
* `REVERT_TO_MANUAL_SCRUTINY` → `END` (Terminal)
* `REJECT` → `END` (Terminal)


* `booking_datasheet` → `END` (Terminal)


* **State Serialization & Resumption**: When a suspension node is hit, execution pauses, and the transient state is serialized into JSON inside the `pipeline_state_json` column of the `LoanRequest` database record. When an operational action is taken on FastAPI, a payload hits the **Resumption Worker Queue**, triggering `resume_pipeline()`. This restores the exact state profile, feeds the human decision variable back into the frame, and signals LangGraph to execute subsequent tasks seamlessly.

---

## Technology Stack

* **Core Framework**: [FastAPI](https://fastapi.tiangolo.com/) (v0.136+) for high performance, standard dependency injection, and automatic OpenAPI documentation generation.
* **ORM / Database**: [SQLAlchemy](https://www.sqlalchemy.org/) (v2.0+) declarative base mapping with SQLite (development) or PostgreSQL (production).
* **Enterprise Message Broker**: [RabbitMQ](https://www.rabbitmq.com/) for reliable, multi-queue task dispatching and delivery guarantees across decoupled execution systems.
* **Asynchronous Task Architecture**: [Celery](https://docs.celeryq.dev/) (v5.4+) managing two distinct worker modes (Pipeline Execution Worker & Resumption Worker).
* **Orchestration Engine**: [LangGraph](https://github.com/langchain-ai/langgraph) (v1.2+) to define state graphs, short-circuit transitions, and structural execution forks.
* **Office Automation**: [openpyxl](https://openpyxl.readthedocs.io/) (v3.1+) to dynamically construct, write, and format official `.xlsx` booking sheets.
* **Security & Hashing**: [python-jose`for HS256 JWT cookie-based protection;`passlib` using bcrypt for password hashing.

---

## Database Schema & ER Model

The relational structural model remains consistent; all workers connect to the same central database, keeping data mutations synchronized and allowing FastAPI to serve live dashboard telemetry to the frontend:

```
    ┌──────────────┐
    │     User     │◀──────────────────────────────────────┐
    └──────────────┘                                       │
           ▲                                               │
           │ (Foreign Key: locked_by / approved_by)        │
           │                                               │
    ┌──────────────┐         ┌──────────────┐      ┌──────────────┐
    │ LoanRequest  │◀─────────│  Attachment  │      │ScrutinyResult│
    └──────────────┘         └──────────────┘      └──────────────┘
      │   │      ▲                                         ▲
      │   │      └─────────────────────────────────────────┘
      │   │                       (1 : 1..N)
      │   │
      │   │(1 : 1..N)        ┌──────────────────┐
      │   ├─────────────────▶│ ExtractedEntity  │
      │   │                  └──────────────────┘
      │   │
      │   │(1 : 1)           ┌──────────────────┐
      │   ├─────────────────▶│ BookingDatasheet │
      │   │                  └──────────────────┘
      │   │
      │   │(1 : 1..N)        ┌──────────────────┐
      │   └─────────────────▶│   PipelineLog    │
      │                      └──────────────────┘
      │
      └───────────────────────▶ [ParsedDocument]

```

---

## Project Directory Layout

```
loan_backend-main/
│
├── app/
│   ├── middleware/
│   │   └── auth_middleware.py     # JWT cookie extraction and RBAC checks
│   │
│   ├── models/                    # SQLAlchemy database tables (Shared across workers)
│   │   ├── attachment.py
│   │   ├── booking_datasheet.py
│   │   ├── extracted_entity.py
│   │   ├── loan_request.py
│   │   ├── parsed_document.py
│   │   ├── pipeline_log.py
│   │   ├── scrutiny_result.py
│   │   └── user.py
│   │
│   ├── pipeline/                  # LangGraph orchestrator & processing nodes
│   │   ├── nodes/
│   │   │   ├── approval_check.py  # AI Approval check node stub
│   │   │   ├── booking_populator.py # EMI calculation and openpyxl writer
│   │   │   ├── doc_parser.py      # File parser stub
│   │   │   ├── doc_scrutinizer.py # Reference verification stub
│   │   │   └── entity_extractor.py# Key entity extraction stub
│   │   ├── orchestrator.py        # LangGraph StateGraph topology definition
│   │   └── state.py               # TypedDict state structure
│   │
│   ├── routers/                   # FastAPI route controllers (REST resources)
│   │   ├── auth.py                # Login, signup, logout
│   │   ├── booking.py             # Booking sheet updates, approvals, downloads
│   │   ├── dashboard.py           # Status counters for real-time frontend updates
│   │   ├── loan_requests.py       # List, detail view, locking mechanisms
│   │   ├── pipeline.py            # Log history, manual dashboard overrides
│   │   ├── review.py              # HITL validation endpoints
│   │   └── scrutiny.py            # HITL scrutiny overrides
│   │
│   ├── schemas/                   # Pydantic schemas (DTO validation & serialization)
│   │   └── ...
│   │
│   ├── services/                  # Business logic services
│   │   ├── auth_service.py        # JWT coding & bcrypt hashing
│   │   └── email_sender.py        # HTML generator and SMTP client
│   │
│   ├── celery_app.py              # Celery config detailing RabbitMQ exchanges & queues
│   ├── config.py                  # Pydantic Settings management (.env file reader)
│   ├── database.py                # Engine, DeclarativeBase, sessionmaker, dependencies
│   └── main.py                    # FastAPI entry point & API Router registration
│
├── attachments/                   # Processing folder for temporary file streams
├── booking_sheets/                # Output directory for generated booking spreadsheets
├── seed.py                        # Database resetting and mock-data seeder script
├── run_worker.py                  # CLI entry point to start the main Pipeline Worker
├── run_resumption_worker.py       # CLI entry point to start the HITL Resumption Worker
├── requirements.txt               # Main Python dependencies list
└── start_backend.bat              # Script utility for development launch

```

---

## API Routing Reference

All endpoints are mapped under the `/api` prefix and secure resources require valid HTTP-only `access_token` cookies. The API layer provides immediate telemetry adjustments to the frontend while interacting seamlessly with the background message broker.

### 1. Authentication (`/api/auth`)

* `POST /auth/signup` - Registers a new user.
* `POST /auth/login` - Validates credentials and sets `access_token` Cookie.
* `POST /auth/logout` - Clears authentication cookies.
* `GET /auth/me` - Details of the current logged-in user session.

### 2. Loan Requests (`/api/loan-requests`)

* `GET /loan-requests` - Paginated list of requests with filters for status and search terms.
* `GET /loan-requests/{loan_id}` - Detailed object including attachments, extracted entities, and scrutiny.
* `POST /loan-requests/{loan_id}/lock` - Locks a request to prevent multiple reviewers from editing simultaneously.
* `POST /loan-requests/{loan_id}/unlock` - Releases the review lock.

### 3. Pipeline Control & HITL Checkpoints (`/api/loan-requests/{loan_id}`)

* `POST /loan-requests/{loan_id}/approve` - Submits approval on `PENDING_MANUAL_REVIEW` (Publishes resume task).
* `POST /loan-requests/{loan_id}/scrutiny/review` - Submits a choice on `PENDING_SCRUTINY_REVIEW` (Publishes resume task).
* `POST /loan-requests/{loan_id}/booking-datasheet/approve` - Finalizes datasheet verification (Triggers outbound SMTP).

---

## Setup & Installation

### Prerequisites

1. **Python 3.10+**
2. **RabbitMQ Server** (Running and listening on default port `5672`)

### Configuration (`.env`)

Configure your `.env` tracking variables to target your RabbitMQ instance:

```env
DATABASE_URL=sqlite:///./bmo.db
SECRET_KEY=generate-a-secure-random-token-here
JWT_EXPIRE_HOURS=8
RABBITMQ_URL=amqp://guest:guest@localhost:5672//
SMTP_HOST=smtp.example.com
SMTP_USER=bmo-notifications@example.com
SMTP_PASSWORD=smtp_password_here

```

### Installation Steps

1. **Activate Environment & Install Packages**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
pip install -r requirements.txt

```


2. **Initialize and Seed Database**:
```bash
python seed.py --reset

```


3. **Start the FastAPI Web App**:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

```


4. **Start the Primary Celery Ingestion & Pipeline Worker**:
Open a separate terminal window, activate the environment, and run:
```bash
python run_worker.py worker --loglevel=info -Q ingestion_pipeline_queue

```


5. **Start the LangGraph Resumption Worker**:
Open an additional terminal window to host the dedicated HITL resumption processor:
```bash
python run_resumption_worker.py worker --loglevel=info -Q hitl_resumption_queue

```



---

## Database Seeding & Management

The system provides a robust seeding script (`seed.py`) to create a predictable sandbox development environment.

* **Seeding Users**:
* `admin` (password: `admin123`, role: `admin`)
* `reviewer` (password: `reviewer123`, role: `reviewer`)


* **Commands**:
* Seed and preserve existing records:
```bash
python seed.py

```


* Reinitialize the database cleanly from scratch:
```bash
python seed.py --reset

```





---

## Production Considerations

1. **Multi-Worker Scaling**: In production environments, scale your main ingestion/pipeline worker separately from your resumption worker to ensure manual UI interactions are never delayed by heavy upstream document parsing.
2. **PostgreSQL Migration**: Switch out SQLite for an enterprise deployment:
```env
DATABASE_URL=postgresql://user:password@db-host:5432/dbname

```

3. **RabbitMQ Virtual Hosts**: Ensure secure user isolation configurations and appropriate dead-letter exchanges (DLX) are specified within the production Celery connection mappings to track processing exceptions safely.

