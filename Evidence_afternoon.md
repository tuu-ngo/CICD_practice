# Evidence — Lab Chiều W9: Observability + Canary

> **Repo:** https://github.com/tuu-ngo/CICD_practice
> **Cluster:** minikube profile `w9`
> **Ngày thực hành:** 12/06/2026

---

## Mục lục

- [Lab 1 — Cài Prometheus + Argo Rollouts qua GitOps](#lab-1--cài-prometheus--argo-rollouts-qua-gitops)
- [Lab 2 — Flask App có /metrics](#lab-2--flask-app-có-metrics)
- [Lab 3 — Deploy + Prometheus scrape](#lab-3--deploy--prometheus-scrape)
- [Lab 4 — Canary Deploy thủ công](#lab-4--canary-deploy-thủ-công)
- [Challenge 1 — AlertManager gửi email](#challenge-1--alertmanager-gửi-email)
- [Challenge 2 — AnalysisTemplate tự abort](#challenge-2--analysistemplate-tự-abort)
- [Bonus — Fullstack App (Frontend + Backend)](#bonus--fullstack-app-frontend--backend)

---

## Lab 1 — Cài Prometheus + Argo Rollouts qua GitOps

### Kết quả đạt được
- Thêm 2 file Application vào `gitops/argocd/apps/` → push → **root tự cài** (không kubectl apply)
- `kube-prometheus-stack` (Prometheus + Grafana + AlertManager) running
- `argo-rollouts` running

### Files tạo qua Git

**`gitops/argocd/apps/kube-prometheus-stack.yaml`** — Helm Application:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: kube-prometheus-stack
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://prometheus-community.github.io/helm-charts
    chart: kube-prometheus-stack
    targetRevision: 65.1.1
    helm:
      values: |
        prometheus:
          prometheusSpec:
            serviceMonitorSelectorNilUsesHelmValues: false
        grafana:
          adminPassword: admin123
        alertmanager:
          config: ...
  destination:
    namespace: monitoring
  syncPolicy:
    automated: { prune: true, selfHeal: true }
    syncOptions: [CreateNamespace=true, ServerSideApply=true]
```

**`gitops/argocd/apps/argo-rollouts.yaml`** — Helm Application:
```yaml
chart: argo-rollouts
targetRevision: 2.37.7
namespace: argo-rollouts
```

### Terminal output

```
PS> kubectl -n monitoring get pods
NAME                                                   READY   STATUS
alertmanager-kube-prometheus-stack-alertmanager-0      2/2     Running
kube-prometheus-stack-grafana-65bcd9c88-q5p2r          3/3     Running
kube-prometheus-stack-operator-d69fb75b9-6kwgp         1/1     Running
kube-prometheus-stack-prometheus-node-exporter-xxxxx   1/1     Running
prometheus-kube-prometheus-stack-prometheus-0          2/2     Running

PS> kubectl -n argo-rollouts get pods
NAME                                       READY   STATUS
argo-rollouts-67cbbf7967-d85kd             1/1     Running
argo-rollouts-67cbbf7967-hjxw8             1/1     Running
argo-rollouts-dashboard-7bb48748b5-7668x   1/1     Running
```


![alt text](image-14.png)

![alt text](image-15.png)

![alt text](image-16.png)

---

## Lab 2 — Flask App có `/metrics`

### Kết quả đạt được
- Viết app Flask với `PrometheusMetrics` tự expose `/metrics`
- Build image `w9-api:1` và load vào minikube

### Files tạo

**`gitops/app/app.py`:**
```python
import os, random
from flask import Flask, jsonify
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
PrometheusMetrics(app)      # tự thêm /metrics

ERR = float(os.getenv("ERROR_RATE", "0"))
VER = os.getenv("VERSION", "v1")

@app.get("/")
def index():
    if random.random() < ERR:
        return jsonify(error="injected", version=VER), 500
    return jsonify(ok=True, version=VER)

@app.get("/healthz")
def healthz(): return "ok", 200
```

**`gitops/app/Dockerfile`:**
```dockerfile
FROM python:3.12-slim
RUN pip install flask prometheus-flask-exporter
COPY app.py /app/app.py
WORKDIR /app
ENV FLASK_APP=app.py
EXPOSE 8080
CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]
```

### Terminal output

```
PS> docker build -t w9-api:1 gitops/app/
[+] Building ... Successfully built w9-api:1

PS> minikube image load w9-api:1 -p w9

PS> minikube image ls -p w9 | Select-String "w9-api"
docker.io/library/w9-api:1
```


![alt text](image-17.png)
---

## Lab 3 — Deploy + Prometheus scrape

### Kết quả đạt được
- Rollout `api` chạy 4 pods trong namespace `demo`
- ServiceMonitor tạo → Prometheus tự scrape `/metrics` mỗi 15s
- Metric `flask_http_request_total` tăng dần theo traffic

### Files tạo

**`gitops/k8s-api/api.yml`** — Rollout (thay Deployment) + Service:
```yaml
kind: Rollout
spec:
  replicas: 4
  strategy:
    canary:
      steps:
      - setWeight: 25
      - pause: {}
      - setWeight: 50
      - pause: { duration: 30s }
      - setWeight: 100
```

**`gitops/k8s-api/servicemonitor.yml`** — để Prometheus tự scrape:
```yaml
kind: ServiceMonitor
spec:
  endpoints:
  - port: http
    path: /metrics
    interval: 15s
```

**`gitops/argocd/apps/api.yaml`** — Application (root tự tạo):
```yaml
path: gitops/k8s-api
destination.namespace: demo
```


![alt text](image-18.png)

![alt text](image-19.png)
![alt text](image-20.png)

---

## Lab 4 — Canary Deploy thủ công

### Kết quả đạt được
- Deploy v2 qua Git → Rollout dừng ở 25% chờ lệnh
- `kubectl argo rollouts promote` → lên 50% → 100% (Good run)
- `kubectl argo rollouts abort` → về bản cũ ngay (Bad run)

### Good Run — Promote

```
# Sau khi push VERSION v1→v2:
PS> kubectl argo rollouts get rollout api -n demo --watch

Name:            api
Status:          ॥ Paused
Strategy:        Canary
  Step:          1/5
  SetWeight:     25
  ActualWeight:  25

Revision:
  canary   api-new-xxx   1   25%   Running   ← bản mới
  stable   api-old-xxx   3   75%   Running   ← bản cũ

PS> kubectl argo rollouts promote api -n demo
rollout 'api' promoted

# Sau khi promote:
Status: ✔ Healthy   (100% bản mới)
```

### Bad Run — Abort

```
# Sau khi push ERROR_RATE 0.8:
PS> kubectl argo rollouts abort api -n demo
rollout 'api' aborted

Status: ✖ Degraded
Message: RolloutAborted: Rollout aborted update to revision 3

# Chỉ 25% user bị ảnh hưởng → rollback về bản cũ ngay
```

---

## Challenge 1 — AlertManager gửi email

### Kết quả đạt được
- AlertManager cấu hình SMTP Gmail với App Password
- **Email nhận được thực tế** với 10 alerts firing (xác nhận pipeline hoạt động)
- PrometheusRule `api-slo` tạo alert `ApiSLOBreach` khi success rate < 95%

### File tạo

**`gitops/k8s-api/prometheusrule.yaml`:**
```yaml
kind: PrometheusRule
metadata:
  name: api-slo
  namespace: demo
  labels:
    release: kube-prometheus-stack
spec:
  groups:
  - name: api.slo
    rules:
    - record: job:api_success_rate:rate2m
      expr: |
        sum(rate(flask_http_request_total{namespace="demo",status!~"5.."}[2m]))
        / sum(rate(flask_http_request_total{namespace="demo"}[2m]))
    - alert: ApiSLOBreach
      expr: job:api_success_rate:rate2m < 0.95
      for: 1m
      labels:
        severity: critical
      annotations:
        summary: "API success rate below SLO (95%)"
```

### Email nhận được

```
[10] Firing
Labels: alertname = TargetDown, severity = warning
Labels: alertname = Watchdog, severity = none   ← heartbeat: pipeline OK
Labels: alertname = KubeControllerManagerDown
...
```

> **Watchdog alert** = xác nhận toàn bộ alerting pipeline hoạt động (Prometheus → AlertManager → Gmail).

### 📸 Ảnh cần chụp
![alt text](image-21.png)
![alt text](image-22.png)
![alt text](image-23.png)
![alt text](image-24.png)

---

## Challenge 2 — AnalysisTemplate tự abort

### Kết quả đạt được
- `AnalysisTemplate` `success-rate` query Prometheus mỗi 30s
- Bản lỗi (ERROR_RATE=0.8): AnalysisRun thấy success rate < 95% → **tự abort < 3 phút**
- Không cần người canh dashboard, không cần bấm abort thủ công

### File tạo

**`gitops/k8s-api/analysis.yaml`:**
```yaml
kind: AnalysisTemplate
metadata:
  name: success-rate
  namespace: demo
spec:
  metrics:
  - name: success-rate
    interval: 30s
    count: 3
    successCondition: result[0] >= 0.95
    failureLimit: 1
    provider:
      prometheus:
        address: http://kube-prometheus-stack-prometheus.monitoring:9090
        query: |
          sum(rate(flask_http_request_total{namespace="demo",status!~"5.."}[2m]))
          / sum(rate(flask_http_request_total{namespace="demo"}[2m]))
```

**`gitops/k8s-api/api.yml`** — Rollout với analysis tích hợp:
```yaml
strategy:
  canary:
    analysis:
      templates:
      - templateName: success-rate
      startingStep: 1
    steps:
    - setWeight: 25
    - pause: { duration: 2m }
    - setWeight: 50
    - pause: { duration: 2m }
    - setWeight: 100
```

### Flow auto-abort

```
git push (bad version, ERROR_RATE=0.8)
     ↓
ArgoCD sync → Rollout bắt đầu canary 25%
     ↓
AnalysisRun khởi động → query Prometheus mỗi 30s
     ↓
success rate = 0.2 < 0.95 → FAIL
     ↓ (sau 1 lần fail, failureLimit=1)
AnalysisRun: Failed → Rollout: Auto-Abort
     ↓
100% traffic về bản cũ (stable)
Chỉ 25% user từng bị ảnh hưởng
```


---

## Bonus — Fullstack App (Frontend + Backend)

### Kết quả đạt được
- Backend Flask API expose `/api/status`, `/api/ping`, `/metrics`
- Frontend nginx dashboard real-time kéo data từ backend
- Deploy qua GitOps (app-of-apps: thêm `fullstack.yaml` → root tự deploy)

### Files tạo

```
gitops/
├── app-fullstack/
│   ├── backend/app.py         ← Flask API
│   ├── backend/Dockerfile
│   ├── frontend/index.html    ← Dashboard UI
│   ├── frontend/nginx.conf    ← proxy /api/ → backend
│   └── frontend/Dockerfile
├── k8s-fullstack/
│   └── fullstack.yaml         ← Namespace + Backend + Frontend (sync-wave)
└── argocd/apps/
    └── fullstack.yaml         ← Application (root tự tạo)
```

### Architecture

```
Browser → Frontend Service (nginx:80)
               ├── /          → Dashboard (real-time update 5s)
               └── /api/*     → proxy → Backend Service (Flask:5000)
                                             └── /api/status  (version, uptime, requests)
                                             └── /api/ping    (latency test)
                                             └── /metrics     (Prometheus)
```

### 📸 Ảnh cần chụp
![alt text](image-25.png)
![alt text](image-26.png)
![alt text](image-27.png)

---
