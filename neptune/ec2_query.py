"""
Neptune query script — HTTPS POST to /gremlin (Neptune 1.4.x).
Runs on EC2 bastion via SSM from inside the VPC.
"""
import json
import ssl
import urllib.request

NEPTUNE = "neptune-experiment.cluster-c5iqya6ga2kg.eu-west-1.neptune.amazonaws.com"
URL = f"https://{NEPTUNE}:8182/gremlin"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def run(query):
    payload = json.dumps({"gremlin": query}).encode("utf-8")
    req = urllib.request.Request(
        URL, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15, context=CTX) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("result", {}).get("data", {}).get("@value", [])


def get_id(name):
    """Get vertex ID by name property."""
    result = run(f"g.V().has('name','{name}').id()")
    return result[0] if result else None


print("=" * 50)
print("Neptune Graph Experiment")
print("=" * 50)

# ── DROP any existing data ─────────────────────────
run("g.V().drop()")

# ── LOAD NODES ────────────────────────────────────
print("\n📥 Loading nodes...")
run("g.addV('Person').property('name','Alice').property('age',30).property('city','London')")
run("g.addV('Person').property('name','Bob').property('age',25).property('city','Berlin')")
run("g.addV('Person').property('name','Charlie').property('age',35).property('city','London')")
run("g.addV('Person').property('name','Diana').property('age',28).property('city','Paris')")
run("g.addV('Company').property('name','YARA').property('industry','Agriculture')")
run("g.addV('Company').property('name','AWS').property('industry','Cloud')")
run("g.addV('Project').property('name','AgriBot').property('status','active')")
run("g.addV('Project').property('name','WeatherAI').property('status','active')")
print("  8 nodes created")

# ── LOAD EDGES using vertex IDs ───────────────────
print("📥 Loading edges...")

# Get IDs for all vertices
ids = {name: get_id(name) for name in
       ['Alice','Bob','Charlie','Diana','YARA','AWS','AgriBot','WeatherAI']}

edges = [
    (ids['Alice'],   'KNOWS',    ids['Bob'],       'since:2020'),
    (ids['Bob'],     'KNOWS',    ids['Charlie'],   'since:2021'),
    (ids['Alice'],   'KNOWS',    ids['Diana'],     'since:2019'),
    (ids['Alice'],   'WORKS_AT', ids['YARA'],      ''),
    (ids['Bob'],     'WORKS_AT', ids['YARA'],      ''),
    (ids['Charlie'], 'WORKS_AT', ids['AWS'],       ''),
    (ids['Diana'],   'WORKS_AT', ids['AWS'],       ''),
    (ids['Alice'],   'WORKS_ON', ids['AgriBot'],   ''),
    (ids['Bob'],     'WORKS_ON', ids['AgriBot'],   ''),
    (ids['Charlie'], 'WORKS_ON', ids['WeatherAI'], ''),
    (ids['Diana'],   'WORKS_ON', ids['WeatherAI'], ''),
]

for src, label, dst, prop in edges:
    q = f"g.V('{src}').addE('{label}').to(__.V('{dst}'))"
    run(q)

nodes = run("g.V().count()")[0]
edges_count = run("g.E().count()")[0]
# unwrap GraphSON typed values
nodes = nodes.get('@value', nodes) if isinstance(nodes, dict) else nodes
edges_count = edges_count.get('@value', edges_count) if isinstance(edges_count, dict) else edges_count
print(f"  {nodes} nodes, {edges_count} edges loaded\n")

# ── QUERIES ───────────────────────────────────────
print("=" * 50)
print("Running queries...")
print("=" * 50)

def unwrap(val):
    """Unwrap GraphSON typed values for clean printing."""
    if isinstance(val, dict) and '@value' in val:
        inner = val['@value']
        if isinstance(inner, dict) and 'objects' in inner:
            return unwrap(inner['objects'])
        return unwrap(inner)
    if isinstance(val, list):
        return [unwrap(v) for v in val]
    return val


print("\nQ1: All people")
print(" ->", unwrap(run("g.V().hasLabel('Person').values('name')")))

print("\nQ2: Who does Alice know directly?")
print(" ->", unwrap(run("g.V().has('name','Alice').out('KNOWS').values('name')")))

print("\nQ3: Friends of Alice's friends (2 hops)?")
print(" ->", unwrap(run("g.V().has('name','Alice').out('KNOWS').out('KNOWS').values('name')")))

print("\nQ4: Who works at YARA?")
print(" ->", unwrap(run("g.V().has('name','YARA').in('WORKS_AT').values('name')")))

print("\nQ5: Projects Alice's colleagues work on?")
print(" ->", unwrap(run("g.V().has('name','Alice').out('KNOWS').out('WORKS_ON').values('name').dedup()")))

print("\nQ6: People in London?")
print(" ->", unwrap(run("g.V().hasLabel('Person').has('city','London').values('name')")))

print("\nQ7: Path from Alice to Charlie?")
print(" ->", unwrap(run("g.V().has('name','Alice').repeat(out('KNOWS')).until(has('name','Charlie')).path().by('name')")))

# ── CLEANUP ───────────────────────────────────────
print("\n" + "=" * 50)
run("g.V().drop()")
remaining = run("g.V().count()")[0]
remaining = remaining.get('@value', remaining) if isinstance(remaining, dict) else remaining
print(f"Cleanup done — nodes remaining: {remaining}")
print("=" * 50)
