#!/usr/bin/env bash
set -u
B=http://localhost:8001
F=http://localhost:3001
pass(){ printf "  %-55s %s\n" "$1" "$2"; }

echo "=== FULL LIVE API SWEEP ==="
pass "GET /health"                                    "$(curl -s $B/health)"
pass "GET /docs"                                      "http=$(curl -s -o /dev/null -w %{http_code} $B/docs)"
pass "GET /openapi.json"                              "http=$(curl -s -o /dev/null -w %{http_code} $B/openapi.json)"
pass "POST /auth/login"                               "$(curl -s -X POST "$B/auth/login?username=alice&password=x")"
pass "GET /api/admin/models"                          "$(curl -s $B/api/admin/models | head -c 90)..."
pass "GET /api/admin/metrics"                         "$(curl -s "$B/api/admin/metrics?hours=24")"
pass "GET /api/admin/feedback-stats"                  "$(curl -s $B/api/admin/feedback-stats)"
pass "GET /api/admin/audit/verify (initial)"          "$(curl -s $B/api/admin/audit/verify)"
pass "POST /api/admin/routing-policies"               "$(curl -s -X POST $B/api/admin/routing-policies -H 'Content-Type: application/json' -d '{"use_case":"UC1_DIAGNOSTIC","override":"local"}' | head -c 110)"
pass "GET /api/admin/routing-policies"                "$(curl -s $B/api/admin/routing-policies | head -c 90)..."
pass "POST /api/admin/rl/train (must be 501)"         "http=$(curl -s -o /dev/null -w %{http_code} -X POST $B/api/admin/rl/train)"
pass "GET /api/admin/audit (rows)"                    "$(curl -s "$B/api/admin/audit?limit=20" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))') rows"

UC1_REQ='{"symptoms":"fièvre 39, toux, douleur thoracique","patient_id":"P10","physician_id":"DR1"}'
pass "POST /api/uc1/diagnose"                         "$(curl -s -X POST $B/api/uc1/diagnose -H 'Content-Type: application/json' -d "$UC1_REQ" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(f"rule={d[\"rule\"]} prov={d[\"provider_used\"]} diag={len(d[\"diagnoses\"])} cites={len(d[\"citations\"])}")')"
pass "POST /api/uc1/feedback"                         "$(curl -s -X POST $B/api/uc1/feedback -H 'Content-Type: application/json' -d '{"audit_log_id":1,"use_case":"UC1_DIAGNOSTIC","action":"validate"}')"

UC2_REQ='{"report_type":"Consultation","raw_text":"PA 130/80, examen RAS","patient_id":"P11","physician_id":"DR1","physician_key":"k"}'
pass "POST /api/uc2/generate"                         "$(curl -s -X POST $B/api/uc2/generate -H 'Content-Type: application/json' -d "$UC2_REQ" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(f"sections={len(d[\"sections\"])} sig={d[\"signature\"][:12]}.. rule={d[\"rule\"]}")')"

UC3_BLOCK='{"new_medications":[{"name":"aspirin"}],"patient":{"current_medications":[{"name":"warfarin"}]},"patient_id":"P12"}'
pass "POST /api/uc3/check (warfarin+aspirin)"          "http=$(curl -s -o /dev/null -w %{http_code} -X POST $B/api/uc3/check -H 'Content-Type: application/json' -d "$UC3_BLOCK") (expect 409)"
UC3_OK='{"new_medications":[{"name":"paracetamol"}],"patient":{}}'
pass "POST /api/uc3/check (benign)"                    "http=$(curl -s -o /dev/null -w %{http_code} -X POST $B/api/uc3/check -H 'Content-Type: application/json' -d "$UC3_OK") (expect 200)"

echo "=== FRONTEND PAGES ==="
for p in / /diagnostic /report /prescription /admin; do
  pass "GET $F$p" "http=$(curl -s -o /dev/null -w %{http_code} $F$p)"
done

echo "=== AUDIT CHAIN FINAL ==="
curl -s $B/api/admin/audit/verify; echo

echo "=== DATASTORE COUNTS ==="
docker exec medai-platform-postgres-1 psql -U medai -d medai -tAc "select 'drugs', count(*) from drugs union all select 'drug_compositions', count(*) from drug_compositions union all select 'drug_interactions', count(*) from drug_interactions union all select 'audit_log', count(*) from audit_log union all select 'feedback', count(*) from feedback union all select 'routing_policies', count(*) from routing_policies;"
echo "qdrant points:"
curl -s http://localhost:6335/collections/medai_knowledge | python3 -c 'import json,sys; r=json.load(sys.stdin)["result"]; print(f"  medai_knowledge: {r[\"points_count\"]} points, status={r[\"status\"]}")'
