# Packa — Kubernetes deployment

## Prerequisites

- Kubernetes cluster (vanilla k8s or k3s)
- `kubectl` configured
- NAS with NFS or CIFS exports for media and output directories
- `kustomize` (built into `kubectl` — use `kubectl apply -k`)

---

## Step 1 — Edit the config

Open [configmap.yaml](configmap.yaml) and optionally set:

- `[web] username` / `password` — leave empty to disable auth

Paths (`/media`, `/output`) are fixed in the manifests. Mount your NFS/CIFS shares
at those paths on the nodes — see Step 2.

---

## Step 2 — Set NFS/CIFS mount points

Edit the `volumes` section in:

- [master/statefulset.yaml](master/statefulset.yaml) — `media` volume (read-only)
- [worker/statefulset.yaml](worker/statefulset.yaml) — `media` (read-only) and `output` volumes

For NFS, set `server` and `path`:

```yaml
- name: media
  nfs:
    server: nas.local        # your NAS hostname or IP
    path: /volume1/media     # NFS export path
    readOnly: true
```

For CIFS/SMB, uncomment the `flexVolume` block and create a credentials Secret:

```bash
kubectl create secret generic packa-cifs-credentials -n packa \
  --from-literal=username=myuser \
  --from-literal=password=mypassword
```

---

## Step 3 — Add workers

The file [worker/statefulset.yaml](worker/statefulset.yaml) is a template for one worker (`worker-01`).

For each additional worker, copy both files and replace `worker-01` with a unique ID:

```bash
sed 's/worker-01/worker-02/g' worker/statefulset.yaml > worker/statefulset-worker-02.yaml
sed 's/worker-01/worker-02/g' worker/service.yaml     > worker/service-worker-02.yaml
```

Add the new files to [kustomization.yaml](kustomization.yaml):

```yaml
- worker/statefulset-worker-02.yaml
- worker/service-worker-02.yaml
```

To configure per-worker ffmpeg settings (e.g. hardware encoding), uncomment and set
`PACKA_WORKER_FFMPEG_EXTRA_ARGS` in the worker's env section.

---

## Step 4 — Configure storage classes (optional)

By default the StatefulSets use the cluster's default StorageClass for their data volumes
(`master.db`, `worker.db`). To use a specific class, uncomment and set `storageClassName`
in the `volumeClaimTemplates` section of each StatefulSet.

---

## Step 5 — Deploy

```bash
kubectl apply -k k8s/
```

Watch everything come up:

```bash
kubectl get pods -n packa -w
```

---

## Step 6 — TLS bootstrap (automatic)

When master starts it generates a bootstrap token and the `token-exporter` sidecar writes
it to the `packa-bootstrap-token` Secret within ~60 seconds.

Web and worker pods read this token via `PACKA_WEB_BOOTSTRAP_TOKEN` /
`PACKA_WORKER_BOOTSTRAP_TOKEN` on startup and onboard themselves automatically.
No manual steps required.

To verify:

```bash
kubectl logs -n packa statefulset/master -c token-exporter
kubectl logs -n packa statefulset/master -c master | grep tls
```

---

## Step 7 — Access the dashboard

By default the web Service is `ClusterIP`. To access it:

**Port-forward (quick access):**

```bash
kubectl port-forward -n packa svc/web 8080:8080
```

Then open http://localhost:8080.

**Ingress (permanent):**

Uncomment and fill in [web/ingress.yaml](web/ingress.yaml), then re-apply.

---

## Adding a worker later

Deploy it — it will start, register with master, and appear in the dashboard with an
**Onboard TLS** button on the Workers tab. Click it to issue a cert and restart the worker.

---

## External workers (outside the cluster)

External workers connect directly to master on port 9000. Expose master externally with
a `LoadBalancer` or `NodePort` service — mTLS keeps the connection secure.

Change the master Service type in [master/service.yaml](master/service.yaml):

```yaml
spec:
  type: LoadBalancer   # or NodePort
  clusterIP: ~         # remove headless setting
  ports:
    - port: 9000
      targetPort: 9000
```

---

## Layout

```
k8s/
  namespace.yaml
  configmap.yaml              # packa.toml for all nodes
  secret.yaml                 # optional web credentials
  kustomization.yaml          # kubectl apply -k k8s/
  master/
    serviceaccount.yaml       # SA for token-exporter sidecar
    rbac.yaml                 # Role + RoleBinding to patch the bootstrap Secret
    secret-bootstrap.yaml     # bootstrap token Secret (patched at runtime)
    statefulset.yaml          # master + token-exporter sidecar
    service.yaml              # headless ClusterIP
  worker/
    statefulset.yaml          # template — copy per worker
    service.yaml              # headless ClusterIP
  web/
    deployment.yaml
    service.yaml
    ingress.yaml              # commented-out template
```
