#!/usr/bin/env bash
set -euo pipefail
umask 077

root=$(git rev-parse --show-toplevel)
image=${TSB017_APP_IMAGE:-fake_login-admin-app:latest}
output=$(mktemp -d "${TMPDIR:-/tmp}/tsb017-drill.XXXXXXXX")
network=tsb017-drill-net
containers=(tsb017-source tsb017-restore)
owned=()
network_owned=false
cleanup() {
    for container in "${owned[@]}"; do docker rm -f "$container" >/dev/null; done
    if [[ "$network_owned" == true ]]; then docker network rm "$network" >/dev/null; fi
}
trap cleanup EXIT
for container in "${containers[@]}"; do
    if docker container inspect "$container" >/dev/null 2>&1; then
        printf 'Refusing existing container: %s\n' "$container" >&2
        exit 1
    fi
done
if docker network inspect "$network" >/dev/null 2>&1; then
    printf 'Refusing existing network: %s\n' "$network" >&2
    exit 1
fi
git -C "$root" rev-parse HEAD > "$output/revision.txt"
git -C "$root" archive HEAD adminapp | tar -x -C "$output"
mkdir -p "$output/adminapp/Logger" "$output/adminapp/ai_logs"
docker network create --internal "$network" >/dev/null
network_owned=true
for container in "${containers[@]}"; do
    docker run -d --name "$container" --network "$network" \
        --tmpfs /var/lib/postgresql/data \
        -e POSTGRES_USER=tsb017 -e POSTGRES_PASSWORD=synthetic-only \
        -e POSTGRES_DB=tsb017_synthetic postgres:16-bookworm >/dev/null
    owned+=("$container")
    docker exec "$container" bash -c 'for attempt in {1..200}; do if pg_isready -U tsb017 -d tsb017_synthetic >/dev/null 2>&1; then exit 0; fi; done; exit 1'
done
fixture() {
    docker run --rm --network "$network" \
        --mount "type=bind,src=$output/adminapp,dst=/app,readonly" \
        --mount "type=bind,src=$root/adminapp/backend/scripts/tsb017_fixture.py,dst=/fixture.py,readonly" \
        --tmpfs /app/Logger:mode=1777 --tmpfs /app/ai_logs:mode=1777 \
        -e "POSTGRES_HOST=$1" -e POSTGRES_USER=tsb017 -e POSTGRES_PASSWORD=synthetic-only \
        -e POSTGRES_DB=tsb017_synthetic -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 \
        -w /app --entrypoint python "$image" /fixture.py "$2"
}
fingerprint() {
    docker exec "$1" psql -X -U tsb017 -d "${3:-tsb017_synthetic}" -At -v ON_ERROR_STOP=1 -c \
        "SELECT json_build_object('tasks',(SELECT json_agg(t ORDER BY sendtask_uuid) FROM (SELECT sendtask_uuid,sendtask_id,sendtask_owner_gid,sendtask_create_ut FROM sendtasks) t),'stats',(SELECT json_agg(s ORDER BY sendtask_uuid) FROM sendlog_stats s),'details',(SELECT json_agg(d ORDER BY uuid) FROM send_log_details d));" > "$2"
}
fixture tsb017-source seed
docker exec tsb017-source pg_dump -U tsb017 -d tsb017_synthetic -Fc > "$output/synthetic.dump"
test -s "$output/synthetic.dump"
sha256sum "$output/synthetic.dump" > "$output/SHA256SUMS"
docker exec -i tsb017-restore pg_restore --list < "$output/synthetic.dump" > "$output/dump.list"
docker exec -i tsb017-restore pg_restore -U tsb017 -d tsb017_synthetic --exit-on-error --no-owner < "$output/synthetic.dump"
fingerprint tsb017-source "$output/source.json"
fingerprint tsb017-restore "$output/restored.json"
cmp "$output/source.json" "$output/restored.json"
fixture tsb017-restore migrate
fingerprint tsb017-restore "$output/migrated.json"
cmp "$output/source.json" "$output/migrated.json"
docker exec tsb017-restore createdb -U tsb017 tsb017_rollback
docker exec -i tsb017-restore pg_restore -U tsb017 -d tsb017_rollback --exit-on-error --no-owner < "$output/synthetic.dump"
fingerprint tsb017-restore "$output/rollback.json" tsb017_rollback
cmp "$output/source.json" "$output/rollback.json"
docker exec tsb017-restore psql -X -U tsb017 -d tsb017_rollback -At -v ON_ERROR_STOP=1 -c \
    "SELECT count(*)=0 FROM information_schema.columns WHERE table_schema='public' AND table_name='sendtasks' AND column_name='local_generation_id';" > "$output/rollback.txt"
grep -qx t "$output/rollback.txt"
printf 'PASS synthetic dump / independent restore / migration idempotency / legacy rollback\nArtifacts (synthetic only): %s\n' "$output"