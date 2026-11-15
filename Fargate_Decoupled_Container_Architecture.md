# AWS ECS Fargate — Decoupled Container Architecture

## Overview

Two independent containers deployed as separate ECS Fargate services within the same
cluster. The frontend service handles all inbound user traffic; the processor service
is only reachable internally via a private Application Load Balancer.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  VPC                                                                            │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  ECS Cluster                                                             │   │
│  │                                                                          │   │
│  │  ┌─────────────────────────┐       ┌──────────────────────────────────┐  │   │
│  │  │  Frontend Service       │       │  Processor Service               │  │   │
│  │  │  (ECS Fargate)          │       │  (ECS Fargate)                   │  │   │
│  │  │                         │       │                                  │  │   │
│  │  │  Task Definition:       │       │  Task Definition:                │  │   │
│  │  │  frontend-task:N        │       │  processor-task:N                │  │   │
│  │  │                         │       │                                  │  │   │
│  │  │  Container Port: 8080   │       │  Container Port: 8081            │  │   │
│  │  │  Runtime: gunicorn      │       │  Runtime: gunicorn               │  │   │
│  │  │  Public IP: enabled     │       │  Public IP: enabled (ECR pull)   │  │   │
│  │  │                         │       │                                  │  │   │
│  │  │  Env Vars:              │       │  Env Vars:                       │  │   │
│  │  │  SERVICE2_URL=          │       │  (none required)                 │  │   │
│  │  │  http://<internal-alb>  │       │                                  │  │   │
│  │  │  :<processor-port>      │       │                                  │  │   │
│  │  │                         │       │                                  │  │   │
│  │  │  SG: frontend-ecs-sg    │       │  SG: processor-ecs-sg            │  │   │
│  │  └──────────┬──────────────┘       └──────────────────┬───────────────┘  │   │
│  │             │                                         ▲                  │   │
│  └─────────────┼─────────────────────────────────────────┼──────────────────┘   │
│                │                                         │                      │
│                │ SERVICE2_URL                            │                      │
│                ▼                                         │                      │
│  ┌─────────────────────────┐       ┌────────────────────┴─────────────────────┐ │
│  │  External ALB           │       │  Internal ALB                            │ │
│  │  (public-facing)        │       │  (private, VPC-only)                     │ │
│  │                         │       │                                          │ │
│  │  Listener: HTTP:80      │       │  Listener: HTTP:<processor-port>         │ │
│  │  Target Group:          │       │  Target Group:                           │ │
│  │  frontend-tg            │       │  processor-tg                            │ │
│  │  → Port <frontend-port> │       │  → Port <processor-port>                 │ │
│  │                         │       │                                          │ │
│  │  SG: external-alb-sg    │       │  SG: internal-alb-sg                     │ │
│  └──────────▲──────────────┘       └──────────────────────────────────────────┘ │
│             │                                                                   │
└─────────────┼───────────────────────────────────────────────────────────────────┘
              │ HTTP:80
     ┌────────┴────────┐
     │   Internet /    │
     │   End Users     │
     └─────────────────┘
```

---

## Security Groups

### external-alb-sg
| Direction | Protocol | Port | Source      | Purpose                        |
|-----------|----------|------|-------------|--------------------------------|
| Inbound   | TCP      | 80   | 0.0.0.0/0   | Allow HTTP from the internet   |
| Outbound  | All      | All  | 0.0.0.0/0   | Allow all outbound             |

### frontend-ecs-sg
| Direction | Protocol | Port              | Source           | Purpose                              |
|-----------|----------|-------------------|------------------|--------------------------------------|
| Inbound   | TCP      | `<frontend-port>` | external-alb-sg  | Allow traffic from external ALB only |
| Outbound  | All      | All               | 0.0.0.0/0        | Allow outbound (ECR pull, ALB calls) |

### internal-alb-sg
| Direction | Protocol | Port                | Source           | Purpose                                  |
|-----------|----------|---------------------|------------------|------------------------------------------|
| Inbound   | TCP      | `<processor-port>`  | frontend-ecs-sg  | Allow traffic from frontend service only |
| Outbound  | All      | All                 | 0.0.0.0/0        | Allow all outbound                       |

### processor-ecs-sg
| Direction | Protocol | Port                | Source           | Purpose                               |
|-----------|----------|---------------------|------------------|---------------------------------------|
| Inbound   | TCP      | `<processor-port>`  | internal-alb-sg  | Allow traffic from internal ALB only  |
| Outbound  | All      | All                 | 0.0.0.0/0        | Allow outbound (ECR pull, logging)    |

---

## Load Balancers

### External ALB
| Property       | Value                                      |
|----------------|--------------------------------------------|
| Scheme         | internet-facing                            |
| Listener       | HTTP:80                                    |
| Target Group   | frontend-tg → `<frontend-port>`            |
| Health Check   | HTTP GET `/health` or `/`                  |
| Subnets        | Public subnets (min. 2 AZs)               |
| Security Group | external-alb-sg                            |

### Internal ALB
| Property       | Value                                      |
|----------------|--------------------------------------------|
| Scheme         | internal                                   |
| Listener       | HTTP:`<processor-port>`                    |
| Target Group   | processor-tg → `<processor-port>`          |
| Health Check   | HTTP GET `/health` or `/`                  |
| Subnets        | Any subnets within the VPC (min. 2 AZs)   |
| Security Group | internal-alb-sg                            |

---

## ECS Services

### Frontend Service
| Property         | Value                                                        |
|------------------|--------------------------------------------------------------|
| Launch Type      | Fargate                                                      |
| Task Definition  | frontend-task:N                                              |
| Container Port   | `<frontend-port>`                                            |
| Public IP        | Enabled (required for ECR image pull without NAT Gateway)    |
| Security Group   | frontend-ecs-sg                                              |
| Load Balancer    | External ALB → frontend-tg                                   |
| Key Env Var      | `SERVICE2_URL=http://<internal-alb-dns>:<processor-port>`    |

### Processor Service
| Property         | Value                                                        |
|------------------|--------------------------------------------------------------|
| Launch Type      | Fargate                                                      |
| Task Definition  | processor-task:N                                             |
| Container Port   | `<processor-port>`                                           |
| Public IP        | Enabled (required for ECR image pull without NAT Gateway)    |
| Security Group   | processor-ecs-sg                                             |
| Load Balancer    | Internal ALB → processor-tg                                  |
| Key Env Var      | None required                                                |

---

## Traffic Flow

```
1. End User  ──HTTP:80──►  External ALB
                               │
                    frontend-tg (Port <frontend-port>)
                               │
2.                    Frontend Container
                               │
                    SERVICE2_URL (HTTP:<processor-port>)
                               │
3.                    Internal ALB
                               │
                    processor-tg (Port <processor-port>)
                               │
4.                    Processor Container
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Two independent ECS services (not sidecar) | Each service scales independently; no task coupling |
| Internal ALB between services | Decouples frontend from processor IP/DNS; enables health checks and future scaling |
| Public IP enabled on Fargate tasks | Avoids NAT Gateway cost; tasks pull images directly from ECR via public IP |
| Processor not exposed to internet | processor-ecs-sg only allows traffic from internal-alb-sg — zero direct internet access |
| SERVICE2_URL as environment variable | Allows swapping the processor endpoint without rebuilding the frontend image |
| Separate security groups per layer | Least-privilege: each layer only accepts traffic from the layer directly above it |
