#!/usr/bin/env bash
# Run: bash scripts/final_check.sh (inside WSL)
B=http://localhost:8001
F=http://localhost:3001

line() { printf "  %-48s %s\n" "$1" "$2"; }

echo "================================================================"
echo " MedAI Assistant Platform — FINAL LIVE CHECK"
echo "================================================================"
echo
echo "[BACKEND ENDPOINTS]"
line "GET  /health"                       "$(curl -s -o /dev/null -w %{http_code} $B/health)"
line "GET  /docs"                         "$(curl -s -o /dev/null -w %{http_code} $B/docs)"
line "GET  /openapi.json"                 "$(curl -s -o /dev/null -w %{http_code} $B/openapi.json)"
line "POST /auth/login"                   "$(curl -s -o /dev/null -w %{http_code} -X POST "$B/auth/login?username=a&password=b")"
line "GET  /api/admin/models"             "$(curl -s -o /dev/null -w %{http_code} $B/api/admin/models)"
line "GET  /api/admin/metrics"            "$(curl -s -o /dev/null -w %{http_code} $B/api/admin/metrics?hours=24)"
line "GET  /api/admin/feedback-stats"     "$(curl -s -o /dev/null -w %{http_code} $B/api/admin/feedback-stats)"
line "GET  /api/admin/routing-policies"   "$(curl -s -o /dev/null -w %{http_code} $B/api/admin/routing-policies)"
line "POST /api/admin/routing-policies"   "$(curl -s -o /dev/null -w %{http_code} -X POST $B/api/admin/routing-policies -H 'Content-Type: application/json' -d '{"use_case":"UC1_DIAGNOSTIC","override":"local"}')"
line "GET  /api/admin/audit"              "$(curl -s -o /dev/null -w %{http_code} $B/api/admin/audit?limit=5)"
line "GET  /api/admin/audit/verify"       "$(curl -s -o /dev/null -w %{http_code} $B/api/admin/audit/verify)"
line "POST /api/admin/rl/train (501)"     "$(curl -s -o /dev/null -w %{http_code} -X POST $B/api/admin/rl/train)"
line "POST /api/uc1/diagnose"             "$(curl -s -o /dev/null -w %{http_code} -X POST $B/api/uc1/diagnose -H 'Content-Type: application/json' -d '{"symptoms":"toux fievre","patient_id":"P1"}')"
line "POST /api/uc1/feedback"             "$(curl -s -o /dev/null -w %{http_code} -X POST $B/api/uc1/feedback -H 'Content-Type: application/json' -d '{"audit_log_id":1,"use_case":"UC1_DIAGNOSTIC","action":"validate"}')"
line "POST /api/uc2/generate"             "$(curl -s -o /dev/null -w %{http_code} -X POST $B/api/uc2/generate -H 'Content-Type: application/json' -d '{"report_type":"Consultation","raw_text":"ok","patient_id":"P1","physician_key":"k"}')"
line "POST /api/uc3/check warfarin+asp."  "$(curl -s -o /dev/null -w %{http_code} -X POST $B/api/uc3/check -H 'Content-Type: application/json' -d '{"new_medications":[{"name":"aspirin"}],"patient":{"current_medications":[{"name":"warfarin"}]}}')"
line "POST /api/uc3/check benign"         "$(curl -s -o /dev/null -w %{http_code} -X POST $B/api/uc3/check -H 'Content-Type: application/json' -d '{"new_medications":[{"name":"paracetamol"}],"patient":{}}')"

echo
echo "[FRONTEND PAGES]"
for p in / /diagnostic /report /prescription /admin; do
  line "GET  :3001$p" "$(curl -s -o /dev/null -w %{http_code} $F$p)"
done

echo
echo "[AUDIT CHAIN]"
curl -s $B/api/admin/audit/verify | sed 's/^/  /'
echo

echo
echo "[DATA]"
docker exec medai-platform-postgres-1 psql -U medai -d medai -tAc "
  select table_name, count::text from (
    select 'drugs' table_name, (select count(*) from drugs) count
    union all select 'drug_compositions', (select count(*) from drug_compositions)
    union all select 'drug_interactions', (select count(*) from drug_interactions)
    union all select 'generic_group_entries', (select count(*) from generic_group_entries)
    union all select 'audit_log', (select count(*) from audit_log)
    union all select 'feedback', (select count(*) from feedback)
    union all select 'routing_policies', (select count(*) from routing_policies)
  ) t order by 1;
" | awk -F'|' '{printf "  %-25s %8s\n", $1, $2}'
PTS=$(curl -s http://localhost:6335/collections/medai_knowledge | grep -oP 'points_count":\K[0-9]+')
printf "  %-25s %8s\n" "qdrant_points" "$PTS"
