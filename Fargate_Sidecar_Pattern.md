# AWS ECS Fargate — Sidecar Pattern (Single Task Definition)

## Overview

Two containers deployed **within the same ECS Task Definition**. The frontend (main)
container handles inbound user traffic; the processor (sidecar) container runs alongside
it in the same task, sharing the local network namespace. Inter-container communication
happens over `localhost` — no internal load balancer required.



## Traffic Flow

```
1. End User  ──HTTP:80──►  External ALB
                               │
                    frontend-tg (Port <frontend-port>)
                               │
2.                    Frontend Container
                               │
                    localhost:<processor-port>  (no ALB, no SG)
                               │
3.                    Processor Container
```
---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ VPC                                                                             │
│                                                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │ ECS Cluster                                                               │  │
│  │                                                                           │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │  │
│  │  │ ECS Service (single service, one task definition)                   │  │  │
│  │  │                                                                     │  │  │
│  │  │  ┌───────────────────────────────────────────────────────────────┐  │  │  │
│  │  │  │ Task (shared network namespace — awsvpc mode)                 │  │  │  │
│  │  │  │                                                               │  │  │  │
│  │  │  │  ┌─────────────────────────┐     ┌─────────────────────────┐  │  │  │  │
│  │  │  │  │ Frontend Container      │     │ Processor Container     │  │  │  │  │
│  │  │  │  │ (main)                  │     │ (sidecar)               │  │  │  │  │
│  │  │  │  │                         │     │                         │  │  │  │  │
│  │  │  │  │ Port: <frontend-port>   │     │ Port: <processor-port>  │  │  │  │  │
│  │  │  │  │ Runtime: gunicorn       │     │ Runtime: gunicorn       │  │  │  │  │
│  │  │  │  │                         │     │                         │  │  │  │  │
│  │  │  │  │ Env Vars:               │     │ Env Vars:               │  │  │  │  │
│  │  │  │  │ SERVICE2_URL=           │     │ (none required)         │  │  │  │  │
│  │  │  │  │ http://localhost:       │     │                         │  │  │  │  │
│  │  │  │  │ <processor-port>        │     │                         │  │  │  │  │
│  │  │  │  └────────────┬────────────┘     └────────────▲────────────┘  │  │  │  │
│  │  │  │               │ localhost:<processor-port>    │               │  │  │  │
│  │  │  │               └───────────────────────────────┘               │  │  │  │
│  │  │  └───────────────────────────────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                │                                                │
│  ┌─────────────────────────────┴─────────────────────────────────────────────┐  │
│  │ External ALB                                                              │  │
│  │ (public-facing)                                                           │  │
│  │                                                                           │  │
│  │ Listener: HTTP:80                                                         │  │
│  │ Target Group: frontend-tg → Port <frontend-port>                          │  │
│  │ SG: external-alb-sg                                                       │  │
│  └─────────────────────────────▲─────────────────────────────────────────────┘  │
│                                │                                                │
└────────────────────────────────┼────────────────────────────────────────────────┘
                                 │ HTTP:80
                        ┌────────┴────────┐
                        │   Internet /    │
                        │   End Users     │
                        └─────────────────┘
```

---

## Security Groups

### external-alb-sg
| Direction | Protocol | Port | Source    | Purpose                      |
|-----------|----------|------|-----------|------------------------------|
| Inbound   | TCP      | 80   | 0.0.0.0/0 | Allow HTTP from the internet |
| Outbound  | All      | All  | 0.0.0.0/0 | Allow all outbound           |

### ecs-task-sg
> One security group covers both containers — they share the same task network interface.

| Direction | Protocol | Port              | Source          | Purpose                              |
|-----------|----------|-------------------|-----------------|--------------------------------------|
| Inbound   | TCP      | `<frontend-port>` | external-alb-sg | Allow traffic from external ALB only |
| Outbound  | All      | All               | 0.0.0.0/0       | Allow outbound (ECR pull, logging)   |

> **Note:** The processor port does **not** need an inbound rule — traffic arrives via
> `localhost` inside the task and never crosses a security group boundary.

---

## Load Balancer

### External ALB
| Property       | Value                                    |
|----------------|------------------------------------------|
| Scheme         | internet-facing                          |
| Listener       | HTTP:80                                  |
| Target Group   | frontend-tg → `<frontend-port>`          |
| Health Check   | HTTP GET `/health` or `/`                |
| Subnets        | Public subnets (min. 2 AZs)             |
| Security Group | external-alb-sg                          |

> No internal ALB is needed. The processor is reached directly over `localhost`.

---

## Task Definition

### sidecar-task
| Property         | Value                          |
|------------------|--------------------------------|
| Network Mode     | `awsvpc`                       |
| Launch Type      | Fargate                        |
| CPU              | Shared across both containers  |
| Memory           | Shared across both containers  |
| Task Role        | ecs-task-role                  |
| Execution Role   | ecs-task-execution-role        |

#### Container 1 — Frontend (main)
| Property       | Value                                                     |
|----------------|-----------------------------------------------------------|
| Image          | `<account>.dkr.ecr.<region>.amazonaws.com/frontend:N`     |
| Port Mapping   | `<frontend-port>` (TCP)                                   |
| Essential      | `true`                                                    |
| Env Vars       | `SERVICE2_URL=http://localhost:<processor-port>`          |
| Log Driver     | `awslogs` → `/ecs/sidecar-task` (frontend)               |

#### Container 2 — Processor (sidecar)
| Property       | Value                                                     |
|----------------|-----------------------------------------------------------|
| Image          | `<account>.dkr.ecr.<region>.amazonaws.com/processor:N`    |
| Port Mapping   | `<processor-port>` (TCP, not exposed externally)          |
| Essential      | `true` or `false` depending on desired failure behavior   |
| Env Vars       | (none required)                                           |
| Log Driver     | `awslogs` → `/ecs/sidecar-task` (processor)              |
| Depends On     | `frontend` → condition: `START` (optional ordering)      |

---

## ECS Service

### sidecar-service
| Property         | Value                                                       |
|------------------|-------------------------------------------------------------|
| Launch Type      | Fargate                                                     |
| Task Definition  | sidecar-task:N                                              |
| Desired Count    | N                                                           |
| Public IP        | Enabled (required for ECR image pull without NAT Gateway)   |
| Security Group   | ecs-task-sg                                                 |
| Load Balancer    | External ALB → frontend-tg                                  |
| Subnets          | Any subnets within the VPC (min. 2 AZs)                    |

> Only **one** ECS service is needed — both containers are launched together as a single task.

---



## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Single task definition | Both containers share CPU, memory, and network — simplest deployment unit |
| `localhost` for inter-container calls | No internal ALB needed; lowest possible latency between frontend and processor |
| `SERVICE2_URL=http://localhost:<processor-port>` | Same env var name as decoupled pattern — easy to switch between architectures |
| One security group for the task | Both containers share one ENI in `awsvpc` mode — only one SG needed |
| Processor port not opened in SG | Traffic never leaves the task network namespace — no inbound rule required |
| `essential: true` on both containers | If either container crashes, the whole task is replaced — keeps state consistent |
