# AWS Neptune — Beginner Guide & Hands-on Experiment

A standalone guide to understand, create, and query AWS Neptune from scratch.

---

## What is Neptune?

AWS Neptune is a **managed graph database**. It stores data as **nodes** (things) and **edges** (relationships between things) — instead of rows/tables like RDS.

```
Relational DB (RDS)          Graph DB (Neptune)
────────────────────         ──────────────────────────────────
Rows and columns             Nodes and relationships

Users table                  (Alice) ──KNOWS──► (Bob)
Orders table                     │                  │
JOIN to connect              WORKS_AT           WORKS_AT
                             (YARA)             (AWS)
```

**When to use Neptune over RDS/DynamoDB:**
- Data is naturally connected (social graphs, org charts, supply chains)
- You need "how are these things related?" queries
- Multi-hop traversals: "colleagues of colleagues who work on X"

---

## Core Concepts

| Concept | What it is | Example |
|---|---|---|
| Node (Vertex) | A thing in the graph | Person, Company, Project |
| Edge | A relationship between two nodes | Alice KNOWS Bob |
| Property | Key-value on a node or edge | name="Alice", age=30 |
| Label | Type of node or edge | 'Person', 'KNOWS' |
| Traversal | Walking the graph | Start at Alice → follow KNOWS → get names |

---

## Gremlin — The Query Language

Gremlin is how you talk to Neptune. Think of it as **walking the graph step by step**.

```groovy
g.V()                                          // all nodes
g.V().hasLabel('Person')                       // all Person nodes
g.V().has('name', 'Alice')                     // find Alice
g.V().has('name', 'Alice').out('KNOWS')        // who Alice knows
g.V().has('name', 'Alice').out('KNOWS').out()  // 2 hops out
g.V().count()                                  // count all nodes
g.E().count()                                  // count all edges
g.V().drop()                                   // delete everything
```

---

## Neptune vs Other AWS Databases

| | Neptune | RDS | DynamoDB |
|---|---|---|---|
| Data model | Graph | Tables | Key-value |
| Best for | Relationships | Structured data | Fast lookups |
| Query language | Gremlin / SPARQL | SQL | PartiQL |
| Public endpoint | ❌ VPC only | ✅ | ✅ |
| Serverless option | ✅ | ✅ | ✅ |

**Important:** Neptune has **no public endpoint** — you must access it from inside the same VPC.

---

## What We Built (Hands-on Experiment)

```
Graph loaded into Neptune:

(Alice) ──KNOWS──► (Bob) ──KNOWS──► (Charlie)
   │                 │
   └──KNOWS──► (Diana)
   │
   ├──WORKS_AT──► (YARA)
   ├──WORKS_ON──► (AgriBot)
   │
(Bob) ──WORKS_AT──► (YARA)
(Charlie) ──WORKS_AT──► (AWS) ──WORKS_ON──► (WeatherAI)
(Diana) ──WORKS_AT──► (AWS)
```

**Queries we ran and results:**

| Query | Result |
|---|---|
| All people | Alice, Bob, Charlie, Diana |
| Who does Alice know? | Bob, Diana |
| Friends of Alice's friends (2 hops) | Charlie |
| Who works at YARA? | Alice, Bob |
| Projects Alice's colleagues work on? | AgriBot, WeatherAI |
| People in London? | Alice, Charlie |
| Path from Alice to Charlie? | Alice → Bob → Charlie |

---

## Architecture Used

```
Local machine (you)
      │
      │  aws ssm send-command
      ▼
EC2 Bastion (t3.micro, Amazon Linux 2023)
  inside sandbox-hackathon-vpc
      │
      │  HTTPS port 8182
      ▼
Neptune Serverless Cluster
  neptune-experiment.cluster-c5iqya6ga2kg.eu-west-1.neptune.amazonaws.com
```

**Why EC2 bastion via SSM?**
- Neptune has no public endpoint (VPC only)
- SSM lets you run commands on EC2 without SSH keys or open ports
- Script uploaded to S3, downloaded and run on EC2

---

## Reproduce From Scratch

### Prerequisites
```bash
aws sts get-caller-identity   # confirm AWS access
```

### Step 1 — Create Neptune Subnet Group
```bash
aws neptune create-db-subnet-group \
  --db-subnet-group-name neptune-experiment-subnet-group \
  --db-subnet-group-description "Neptune experiment" \
  --subnet-ids <private-subnet-1> <private-subnet-2> <private-subnet-3> \
  --region eu-west-1
```

### Step 2 — Create Neptune Serverless Cluster + Instance
```bash
aws neptune create-db-cluster \
  --db-cluster-identifier neptune-experiment \
  --engine neptune \
  --db-subnet-group-name neptune-experiment-subnet-group \
  --vpc-security-group-ids <your-sg-id> \
  --serverless-v2-scaling-configuration MinCapacity=1,MaxCapacity=4 \
  --no-deletion-protection \
  --region eu-west-1

aws neptune create-db-instance \
  --db-instance-identifier neptune-experiment-instance \
  --db-cluster-identifier neptune-experiment \
  --db-instance-class db.serverless \
  --engine neptune \
  --region eu-west-1

# Wait ~8 min for status: available
aws neptune describe-db-instances \
  --db-instance-identifier neptune-experiment-instance \
  --region eu-west-1 \
  --query 'DBInstances[0].DBInstanceStatus'
```

### Step 3 — Open Port 8182 in Security Group
```bash
# Allow Neptune port within the security group
aws ec2 authorize-security-group-ingress \
  --region eu-west-1 \
  --group-id <your-sg-id> \
  --protocol tcp --port 8182 \
  --source-group <your-sg-id>
```

### Step 4 — Launch EC2 Bastion (SSM-enabled)
```bash
# Create IAM role for EC2
aws iam create-role --role-name neptune-bastion-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy --role-name neptune-bastion-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore

aws iam attach-role-policy --role-name neptune-bastion-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess

aws iam create-instance-profile --instance-profile-name neptune-bastion-profile
aws iam add-role-to-instance-profile \
  --instance-profile-name neptune-bastion-profile \
  --role-name neptune-bastion-role

# Launch EC2 (Amazon Linux 2023, t3.micro)
aws ec2 run-instances \
  --image-id ami-0442403fb8d244144 \
  --instance-type t3.micro \
  --subnet-id <private-subnet-id> \
  --security-group-ids <your-sg-id> \
  --iam-instance-profile Name=neptune-bastion-profile \
  --no-associate-public-ip-address \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=neptune-bastion}]' \
  --region eu-west-1

# Wait ~1 min then check SSM is online
aws ssm describe-instance-information --region eu-west-1 \
  --filters "Key=InstanceIds,Values=<instance-id>" \
  --query 'InstanceInformationList[0].PingStatus'
```

### Step 5 — Install gremlinpython on EC2
```bash
INSTANCE_ID="<your-instance-id>"

aws ssm send-command \
  --instance-ids $INSTANCE_ID \
  --document-name AWS-RunShellScript \
  --parameters '{"commands":["pip3 install gremlinpython"]}' \
  --region eu-west-1
```

### Step 6 — Upload and Run the Query Script
```bash
# Upload script to S3
aws s3 cp neptune/ec2_query.py s3://<your-bucket>/neptune_query.py

# Run it on EC2 via SSM
aws ssm send-command \
  --instance-ids $INSTANCE_ID \
  --document-name AWS-RunShellScript \
  --parameters '{"commands":["aws s3 cp s3://<your-bucket>/neptune_query.py /tmp/neptune_query.py --region eu-west-1","python3 /tmp/neptune_query.py"]}' \
  --region eu-west-1 \
  --query 'Command.CommandId' --output text

# Get output (wait ~30s first)
aws ssm get-command-invocation \
  --command-id <command-id> \
  --instance-id $INSTANCE_ID \
  --region eu-west-1 \
  --query 'StandardOutputContent' --output text
```

---

## The Query Script (`neptune/ec2_query.py`)

The script does 4 things in order:
1. **Drop** any existing data (clean slate)
2. **Load** 8 nodes + 11 edges
3. **Run** 7 read queries
4. **Cleanup** — drop all data

Key things learned about Neptune HTTP API:
- Requires **HTTPS** (port 8182), not plain HTTP
- Edge creation needs `__.V()` (anonymous traversal) not `g.V()` inside `to()`
- Results come back as **GraphSON** typed values — unwrap `@value` for clean output

---

## Cleanup (Avoid Charges)

```bash
# 1. Terminate EC2 bastion
aws ec2 terminate-instances --instance-ids <instance-id> --region eu-west-1

# 2. Delete Neptune instance (wait ~3 min)
aws neptune delete-db-instance \
  --db-instance-identifier neptune-experiment-instance \
  --region eu-west-1

# 3. Delete Neptune cluster
aws neptune delete-db-cluster \
  --db-cluster-identifier neptune-experiment \
  --skip-final-snapshot \
  --region eu-west-1

# 4. Delete subnet group
aws neptune delete-db-subnet-group \
  --db-subnet-group-name neptune-experiment-subnet-group \
  --region eu-west-1

# 5. Revoke port 8182 SG rule
aws ec2 revoke-security-group-ingress \
  --region eu-west-1 \
  --group-id <your-sg-id> \
  --protocol tcp --port 8182 \
  --source-group <your-sg-id>
```

---

## Key Takeaways

- Neptune is **VPC-only** — always need a bastion or Lambda inside the VPC
- Neptune 1.4.x requires **HTTPS/WSS** — plain HTTP returns empty response
- Edge creation via HTTP needs `__.V()` not `g.V()` inside `to()`
- **SSM Run Command** is the cleanest way to run scripts on EC2 without SSH
- GraphSON responses need `@value` unwrapping for readable output
- Serverless Neptune costs ~$0.10/hr when active, $0 when idle
