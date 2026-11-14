# Contexture optional LAN gateway deployment

This guide describes the optional authenticated gateway and native worker setup.
Replace every angle-bracket value with a value for your own private network. Do
not commit deployment tokens, private configuration, model files, or task data.
The gateway runs in Docker; workers run as native Python 3.12 services on Linux
or macOS.

| Node | Project and working root | CPU affinity |
| --- | --- | --- |
| worker-a | `<linux-worker-root>` | Set for the cores allocated to this service |
| worker-b | `<linux-worker-root>` | Set for the cores allocated to this service |
| worker-c | `<macos-worker-root>` | macOS chooses the cores used by the worker |

CPU numbering is host-specific. Recheck topology after hardware changes. Set each
worker's affinity, CPU quota, memory limit, native BLAS/OpenMP thread count, and
ScreenAI/Indra concurrency according to its host capacity. The service limits
apply to the worker process tree; they do not constrain unrelated applications.
Validate memory and throughput with representative documents before deployment.

Workers use user-provided Indra models and Chrome ScreenAI components. Each input
is OCRed through ScreenAI, then passed through Indra's strict layout path and the
Middle adapter and scholarly renderer. Internal Indra OCR is disabled. Models and
task directories stay outside the source tree. Set the gateway data directory on
the Docker host's persistent disk. Linux dependencies use CPU PyTorch; no GPU
inference is required.
Install requirements with `-c deploy/cluster/native-constraints.txt` to avoid
unrelated PDF major-version upgrades. Store uv's cache under each node's cache/.
Additional Unicode fonts can be installed under `models/fonts/` and selected with
`CONTEXTURE_SCREENAI_FONT_DIR`. The directory must exist. Its TTF/OTF/TTC files
extend the system fonts used for searchable PDF overlays.

## Unified gateway API

The Docker gateway uses Python's standard library and PyMuPDF for PDF inspection
and assembly. Set its persistent data
directory in the private gateway configuration. Every API requires Bearer
authentication.

| Request | Result |
| --- | --- |
| `POST /jobs` with raw PDF bytes | Submit one book, HTTP 202 with id, status_url and result_url |
| `POST /jobs` with a ZIP of PDFs | Submit a document group with one book task per PDF |
| `GET /jobs/<id>` | Durable status, page/batch progress, children and attempt history |
| `GET /jobs/<id>/result` | Completed gzip tar, one book's Markdown/Middle/execution or documents/<book-id>/ for a group |
| `PUT /process` with raw PDF bytes | Submit, wait and return page_content plus metadata for the knowledge loader |
| `PUT /process` with a ZIP of PDFs | Return a list of completed document objects |
| `GET /health` | Node online/busy/available state and timeout settings |

`X-Filename` carries the URL-encoded original filename. `batch_pages` defaults to
40. The gateway creates prepare, extract and merge tasks automatically. Native
workers split the PDF, recognize batches and render the complete book after
checking hashes, page coverage, global block IDs and interval anchors.
Multiple books share the queue by their most recent dispatch time. Each node
owns one attempt at a time and keeps its fixed CPU/model allocation.

`Idempotency-Key` identifies one logical submission. Repeating the same key,
input and settings returns the same job. A different input with that key returns
409. Clients can reconnect and query the job after a connection failure.
The synchronous /process response follows the existing knowledge loader shape,
including source, page_count and contexture_job_id in metadata.

Request bodies and expanded ZIP contents have a 256 MiB limit. Uploads and
result downloads stream through files on the gateway disk. A ZIP may contain
multiple PDF files. Results become available after all required stages succeed.

The optional `node` query parameter prefers worker-a, worker-b or worker-c. If that
node remains offline for the configured offline interval, another node can take
the task. `stage=extract` continues to expose direct raw Middle extraction for
the existing CLI coordinator.

## Recovery and deadlines

| Configuration | Default |
| --- | --- |
| lease_seconds | 60 seconds |
| offline_seconds | 45 seconds |
| attempt_timeout | 900 seconds |
| queue_timeout | 1800 seconds |
| document_timeout | 7200 seconds |
| max_attempts | 3 |
| retry_delay | 3 seconds, exponential backoff capped at 30 seconds |

Workers heartbeat every 10 seconds. Each claim creates a unique lease token.
Heartbeats, results and failures require that token. Expired or timed-out work
is queued for another attempt. Returning workers receive 409 for an obsolete
lease and stop that attempt's process group. Successful completion is idempotent
for its current token. Attempt errors and node assignments remain in SQLite.

The gateway checks leases and deadlines once per second. Worker heartbeat
traffic supplies node availability. CPU sampling is used for acceptance runs.
Execution deadlines remain fixed while heartbeats renew the lease. A book
failure cancels its unfinished stages, and a group failure cancels unfinished
books. Completed batches remain on disk. Gateway restart resumes the durable
workflow. The node worker cleans up process groups left by a previous crash.

The private gateway configuration accepts the settings in the table alongside
port, token and data_dir. Native workers use protocol 2. Upgrade all native
workers with the gateway. Keep the service on the private LAN.

## Deployment and operation

Stage cluster.py, cluster_gateway.py, cluster_admin.py, cluster_production.py,
cluster_ui/, Dockerfile and gateway.dockerignore
(renamed .dockerignore) in the gateway build directory. Build an image tagged
with the release commit. Set CPU and memory limits for the host, configure
restart=unless-stopped, bind port 8766 to a private LAN interface, and mount

- gateway.json to /app/config.json read-only
- data/ to /data

Native worker command is `python -m aih_contexture.scripts.cluster worker <config>`.
Configuration contains node, gateway, token, work_dir, indra_model_dir,
screenai_model_dir, cores and screenai_workers. Keep private configurations mode
0600. The Mac uses http_transport=curl and the existing font directory setting.
Credentials pass to curl through stdin. Each attempt gets its own directory,
process log and output under work/<task-id>/<lease-token>/.

Linux can use a systemd user service with lingering enabled. macOS can use a
launchd user agent in the login session. Restart a worker after replacing its
owned modules. Record the deployed source commit in DEPLOYED_COMMIT. Models,
virtual environments, and private configuration live outside the source tree.

The standalone cluster_batch CLI remains available for existing callers. The
knowledge loader submits files through PUT /process. Asynchronous clients use
POST /jobs and poll status_url before downloading result_url.

## PDF routing in the knowledge service

The knowledge loader selects the external gateway for PDF extension or PDF MIME
type when EXTERNAL_DOCUMENT_LOADER_URL and EXTERNAL_DOCUMENT_LOADER_API_KEY are
configured. Keep CONTENT_EXTRACTION_ENGINE at its existing value. Other formats
continue through their configured loader branches.

For an existing knowledge service, configure its PDF loader to use the gateway
URL and API key through that service's private settings. Keep its other extraction
settings and data volumes unchanged. The PDF transport should supply an
Idempotency-Key and reconnect to the same gateway after a network failure so the
client can retrieve the persisted job.

## Management console

Open `http://<gateway-host>:8766/` and sign in with the administrator access key
from the private gateway configuration.
The same-origin console provides an overview, task search and history, document
submission and downloads, task cancellation and retry, and node pause/resume.
Pausing stops new assignments while the current attempt finishes. Cancellation
revokes active leases. Manual retry keeps completed batches and execution history
and starts a fresh retry budget and deadline for unfinished work.

Node allocations come from each worker's reported cores and ScreenAI workers.
The configuration page displays the active timeout policy and request-size limit.
Change those values in the existing private configurations and restart the
corresponding service. The console uses heartbeat status for node availability.

Login creates a 12-hour HttpOnly SameSite session with CSRF protection. Sessions
survive gateway restarts and expire when the access key changes. Logout revokes
the current session. The browser downloads only artifacts present in the result
archive. Markdown and structure data are available after successful processing.

## Retention and capacity configuration

Retention periods for original files, final outputs, intermediate payloads,
diagnostics, and task history are deployment settings. Cleanup preserves active
work. A manual retry can rebuild expired intermediate stages from a retained
original while keeping attempt history. Newly submitted books require
`searchable.pdf` in each extraction and merge result. The worker reuses
ScreenAI's existing searchable PDF and concatenates batches in source order.

The private gateway configuration accepts limits for request and result size,
document pages, documents per request, pending documents and pages, free disk
space, concurrent uploads, intermediate and diagnostic retention, and backup
copies. Set these values for the deployment's capacity. Queue admission is
transactional and accounts for pending source bytes and pages alongside the
configured free-space floor. Snapshots persist effective limits and timeouts
alongside the private credentials; no production configuration is included.

Malformed, empty, encrypted or excessive-page PDFs are rejected before enqueue.
HTTP 413 means the configured request or document limit was exceeded. HTTP 429
means queue capacity was reached. HTTP 503 means upload slots or disk reserve are
unavailable. Temporary capacity responses include Retry-After. Clients retain
the same Idempotency-Key when retrying a logical submission. The management
uploader retains its key after an interrupted or rejected attempt.

Private credentials separate clients and workers, each a mapping of name to
an independently generated access key. Worker mapping names match the configured
node IDs. A separate token is the administrator key. Clients submit and
read documents. Workers claim and report work for their own identity. Management
controls require the administrator key or its browser session. Keep these keys
in private configuration and the knowledge service's existing persistent setting.

## Backups and restore

Schedule `gateway_backup.py create` on the source host and
`gateway_backup.py pull` on the replica host. Configure the schedules and archive
retention for the deployment. Systemd user timers can use `Persistent=true` so
missed runs resume after the host returns. Local snapshots can continue while the
replica is unavailable. Replica pulls reuse an already verified copy when the
local snapshot has not changed.

The source configuration supplies container, backup_dir, replica_host and copies.
The replica configuration supplies backup_dir, source_host, source_script,
source_config, source_backup_dir and copies. Configuration stays outside the repo.
Install the script under each native working root's ops directory and use an
absolute ExecStart in the corresponding systemd user service. Set UMask=0077.
The replica checks archive SHA256 and size before publishing the copy. It then
records a verified receipt on the gateway. Management displays the most recent
snapshot and replica status.

A snapshot pins canonical payload files using hard links under a short SQLite
writer transaction and captures SQLite with its backup API. Hashing, archive
creation and network copying happen after releasing that transaction. The
manifest records every payload size and SHA256. Private gateway configuration
is included. Archives and backup directories have modes 0600 and 0700.

Restore into a new empty location with
`python -m aih_contexture.scripts.cluster_production restore <archive> <new-directory>`.
The command checks archive paths, payload hashes and database integrity before
publishing the directory. It fences former leases, resets active task deadlines,
clears browser sessions and node online state, and retains finished stages.
The restored gateway.json points at the new data directory. Set the deployment's
port/data mount as appropriate before starting the recovered gateway. Native
models and venvs remain on their existing disks. Preserve worker pause states
and explicitly resume the intended nodes during recovery acceptance.

A standby gateway can be validated on an isolated port. For a production recovery,
stop the former gateway, restore and verify the selected backup, point the source
container at the recovered data directory, then start it on the established URL.
Workers reconnect using their existing configurations. Verify node heartbeats,
unfinished job completion, original and final artifact downloads, and the
knowledge loader's existing PUT /process contract before reopening submission.
For recovery on another host, keep a single active gateway and either move the
established address or update the worker gateway URLs and knowledge connection
setting together after validating the recovered service.
