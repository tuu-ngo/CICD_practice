# Lab Chiều — Observability + Canary (W9)

> **Mục tiêu:** Cài Prometheus + Argo Rollouts qua GitOps → deploy Flask app có `/metrics` → thực hành canary deploy thủ công → hiểu nền tảng cho Challenge auto-abort.

---

## Tổng quan luồng

```
Lab 1: Cài hạ tầng (Prometheus + Argo Rollouts) qua app-of-apps
Lab 2: Build Flask app có /metrics
Lab 3: Deploy app → Prometheus scrape → xem metric
Lab 4: Canary deploy thủ công (promote / abort)
Challenge: AnalysisTemplate tự abort + SLO + alert email
```

**Repo:** `https://github.com/tuu-ngo/CICD_practice`
**Cluster:** minikube profile `w9`

---

## Chuẩn bị: Nâng RAM cho cluster

kube-prometheus-stack rất nặng (~2GB RAM). Cần restart cluster với nhiều tài nguyên hơn:

```powershell
# Xóa cluster cũ
minikube delete -p w9

# Tạo lại với nhiều tài nguyên hơn
minikube start -p w9 --driver=docker --cpus=4 --memory=6144

kubectl config use-context w9
kubectl get nodes
# w9   Ready
```

> Sau khi tạo lại cluster, ArgoCD và tất cả app đều mất → cần cài lại ArgoCD và apply root.

**Cài lại ArgoCD:**

```powershell
kubectl create namespace argocd
kubectl apply --server-side -n argocd `
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Đợi ArgoCD sẵn sàng (~3 phút)
kubectl -n argocd rollout status deploy/argocd-server

# Apply root Application (1 lần duy nhất)
kubectl apply -f gitops/argocd/root.yaml

# Tạo lại namespace demo
kubectl create namespace demo
```

**Kiểm tra root đang quản lý web:**

```powershell
kubectl -n argocd get applications
# NAME   SYNC STATUS   HEALTH STATUS
# root   ...           Healthy
# web    Synced        Healthy
```

---

## Lab 1 — Cài Prometheus + Argo Rollouts qua GitOps

> **Mục tiêu:** Dùng app-of-apps từ buổi sáng — thêm 2 file Application vào `gitops/argocd/apps/` → push → root tự cài Prometheus và Argo Rollouts. **Không kubectl apply.**

---

### Bước 1.1 — Tạo Application cho kube-prometheus-stack

Tạo file `gitops/argocd/apps/kube-prometheus-stack.yaml`:

```yaml
# file: gitops/argocd/apps/kube-prometheus-stack.yaml
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
          enabled: true
  destination:
    server: https://kubernetes.default.svc
    namespace: monitoring
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
    - ServerSideApply=true
```

> **Giải thích key config:**
>
> - `serviceMonitorSelectorNilUsesHelmValues: false` → Prometheus scrape **tất cả** ServiceMonitor trong cluster (không giới hạn namespace/label)
> - `ServerSideApply=true` → tránh lỗi annotation quá dài với CRD lớn
> - `CreateNamespace=true` → tự tạo namespace `monitoring`

---

### Bước 1.2 — Tạo Application cho Argo Rollouts

Tạo file `gitops/argocd/apps/argo-rollouts.yaml`:

```yaml
# file: gitops/argocd/apps/argo-rollouts.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: argo-rollouts
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://argoproj.github.io/argo-helm
    chart: argo-rollouts
    targetRevision: 2.37.7
    helm:
      values: |
        dashboard:
          enabled: true
  destination:
    server: https://kubernetes.default.svc
    namespace: argo-rollouts
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
    - ServerSideApply=true
```

---

### Bước 1.3 — Push và quan sát root tự cài

```powershell
git add gitops/argocd/apps/kube-prometheus-stack.yaml
git add gitops/argocd/apps/argo-rollouts.yaml
git commit -m "feat: add prometheus-stack and argo-rollouts via app-of-apps"
git push

# KHÔNG kubectl apply — root tự phát hiện và tạo Application
# Đợi ArgoCD poll (~3 phút) rồi kiểm tra:
kubectl -n argocd get applications
```

**Output mong đợi:**

```
NAME                     SYNC STATUS   HEALTH STATUS
kube-prometheus-stack    Synced        Healthy
argo-rollouts            Synced        Healthy
root                     ...           Healthy
web                      Synced        Healthy
```

---

### Bước 1.4 — Đợi pods khởi động

kube-prometheus-stack nặng, có thể mất 5-10 phút:

```powershell
# Theo dõi pods monitoring
kubectl -n monitoring get pods -w

# Theo dõi pods argo-rollouts
kubectl -n argo-rollouts get pods -w
```

**Output mong đợi:**

```
# monitoring namespace
NAME                                                   READY   STATUS
alertmanager-kube-prometheus-stack-alertmanager-0      2/2     Running
kube-prometheus-stack-grafana-xxxxxxxxx-xxxxx          3/3     Running
kube-prometheus-stack-prometheus-node-exporter-xxxxx   1/1     Running
prometheus-kube-prometheus-stack-prometheus-0          2/2     Running
...

# argo-rollouts namespace
NAME                             READY   STATUS
argo-rollouts-xxxxxxxxx-xxxxx    1/1     Running
```

---

### Bước 1.5 — Cài kubectl-argo-rollouts plugin (Windows)

Plugin này cần để chạy lệnh `kubectl argo rollouts` ở Lab 4:

```powershell
# Tải plugin (PowerShell)
Invoke-WebRequest -Uri "https://github.com/argoproj/argo-rollouts/releases/latest/download/kubectl-argo-rollouts-windows-amd64" `
  -OutFile "kubectl-argo-rollouts.exe"

# Di chuyển vào PATH (thư mục kubectl đang nằm)
# Tìm kubectl đang ở đâu:
(Get-Command kubectl).Source
# Ví dụ: C:\Program Files\kubectl\kubectl.exe

# Copy plugin vào cùng thư mục:
Move-Item "kubectl-argo-rollouts.exe" "C:\Program Files\kubectl\kubectl-argo-rollouts.exe"

# Kiểm tra
kubectl argo rollouts version
```

---

### ✅ Checkpoint Lab 1

- [x] `kubectl -n monitoring get pods` → `prometheus-*`, `grafana-*` đều `Running`
- [x] `kubectl -n argo-rollouts get pods` → `argo-rollouts-*` Running
- [x] `kubectl argo rollouts version` → hiện version

---

## Lab 2 — Viết Flask app có `/metrics`

> **Mục tiêu:** Tạo app Python đơn giản, expose `/metrics` cho Prometheus scrape, có thể inject lỗi qua env var.

---

### Bước 2.1 — Tạo thư mục app

```powershell
mkdir gitops\app
```

---

### Bước 2.2 — Tạo `gitops/app/app.py`

```python
# file: gitops/app/app.py
import os, random
from flask import Flask, jsonify
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
PrometheusMetrics(app)              # tự thêm endpoint /metrics

ERR = float(os.getenv("ERROR_RATE", "0"))   # 0.0 = không lỗi, 0.5 = 50% lỗi
VER = os.getenv("VERSION", "v1")

@app.get("/")
def index():
    if random.random() < ERR:
        return jsonify(error="injected", version=VER), 500
    return jsonify(ok=True, version=VER)

@app.get("/healthz")
def healthz():
    return "ok", 200
```

> **Giải thích:**
>
> - `PrometheusMetrics(app)` → tự expose `/metrics` với các counter về HTTP request (status, duration, total)
> - `ERROR_RATE` env var → inject lỗi để demo canary abort ở Lab 4
> - `VERSION` env var → phân biệt v1 và v2 khi canary

---

### Bước 2.3 — Tạo `gitops/app/Dockerfile`

```dockerfile
# file: gitops/app/Dockerfile
FROM python:3.12-slim
RUN pip install flask prometheus-flask-exporter
COPY app.py /app/app.py
WORKDIR /app
ENV FLASK_APP=app.py
EXPOSE 8080
CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]
```

---

### Bước 2.4 — Build image và nạp vào minikube

```powershell
# Build image (từ root repo)
docker build -t w9-api:1 gitops/app/

# Nạp image vào minikube (không cần registry)
minikube image load w9-api:1 -p w9

# Kiểm tra image đã vào chưa
minikube image ls -p w9 | Select-String "w9-api"
# Phải thấy: docker.io/library/w9-api:1
```

---

### ✅ Checkpoint Lab 2

- [ ] `docker images | findstr w9-api` → thấy `w9-api:1`
  - [ ] `minikube image ls -p w9 | Select-String "w9-api"` → thấy image

---

## Lab 3 — Deploy app + Prometheus scrape + xem metric

> **Mục tiêu:** Tạo manifest Rollout + Service + ServiceMonitor → push → ArgoCD deploy → Prometheus tự scrape → verify metric xuất hiện.

---

### Bước 3.1 — Tạo thư mục k8s-api

```powershell
mkdir gitops\k8s-api
```

---

### Bước 3.2 — Tạo `gitops/k8s-api/api.yaml` (Rollout + Service)

```yaml
# file: gitops/k8s-api/api.yaml

# ─── Rollout (thay thế Deployment, biết thả canary) ───
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: api
  namespace: demo
  labels:
    app: api
spec:
  replicas: 4
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: w9-api:1
        imagePullPolicy: IfNotPresent
        ports:
        - name: http
          containerPort: 8080
        env:
        - name: ERROR_RATE
          value: "0"          # 0 = không lỗi
        - name: VERSION
          value: "v1"
        readinessProbe:
          httpGet:
            path: /healthz
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
  strategy:
    canary:
      steps:
      - setWeight: 25          # bước 1: 25% traffic sang bản mới
      - pause: {}              # dừng vô hạn, chờ người promote
      - setWeight: 50          # bước 2: 50%
      - pause:
          duration: 30s        # tự động sau 30 giây
      - setWeight: 100         # bước 3: full 100%

---

# ─── Service ───
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: demo
  labels:
    app: api
spec:
  selector:
    app: api
  ports:
  - name: http
    port: 8080
    targetPort: 8080
```

> **Tại sao dùng `Rollout` thay `Deployment`?**
> Rollout là CRD của Argo Rollouts — giống Deployment nhưng thêm `strategy.canary` để điều khiển traffic từng bước. Deployment chỉ biết rolling update (tất cả hoặc không).

---

### Bước 3.3 — Tạo `gitops/k8s-api/servicemonitor.yaml`

```yaml
# file: gitops/k8s-api/servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: api
  namespace: demo
  labels:
    app: api
spec:
  selector:
    matchLabels:
      app: api          # match với label của Service
  endpoints:
  - port: http          # tên port trong Service (http: 8080)
    path: /metrics      # endpoint metrics của Flask
    interval: 15s       # scrape mỗi 15 giây
```

> **ServiceMonitor là gì?** CRD của Prometheus Operator. Thay vì config scrape thủ công trong `prometheus.yaml`, bạn tạo ServiceMonitor → Prometheus Operator tự thêm scrape job. Đây là cách "GitOps-friendly" để config Prometheus.

---

### Bước 3.4 — Tạo `gitops/argocd/apps/api.yaml`

```yaml
# file: gitops/argocd/apps/api.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: api
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/tuu-ngo/CICD_practice.git
    targetRevision: main
    path: gitops/k8s-api
  destination:
    server: https://kubernetes.default.svc
    namespace: demo
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
```

---

### Bước 3.5 — Push tất cả lên Git

```powershell
git add gitops/app/
git add gitops/k8s-api/
git add gitops/argocd/apps/api.yaml
git commit -m "feat: add api app with Rollout + ServiceMonitor"
git push

# Kiểm tra Application api được tạo
kubectl -n argocd get applications
# NAME   SYNC STATUS   HEALTH STATUS
# api    Synced        Healthy   ← root tự tạo

# Kiểm tra pods chạy
kubectl -n demo get pods
# NAME                 READY   STATUS
# api-xxxxxxxxx-xxxxx  1/1     Running  (x4)
```

---

### Bước 3.6 — Gửi traffic vào app

Mở terminal riêng và chạy load generator:

```powershell
# Chạy loop gửi request liên tục vào app
kubectl -n demo run load --image=busybox --restart=Never -- `
  sh -c "while true; do wget -qO- http://api:8080/; sleep 0.5; done"

# Xem log để confirm traffic đang chạy
kubectl -n demo logs load -f
# {"ok": true, "version": "v1"}
# {"ok": true, "version": "v1"}
```

---

### Bước 3.7 — Mở Prometheus và xem metric

```powershell
# Terminal riêng: port-forward Prometheus
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090
```

Mở `http://localhost:9090`:

1. **Status → Targets** → tìm `api` → phải thấy `State: UP`
2. **Graph** → nhập query:

```
flask_http_request_total{namespace="demo"}
```

Bấm **Execute** → thấy counter tăng dần.

Thử thêm query:

```promql
# Tỉ lệ request thành công (không phải 5xx)
sum(rate(flask_http_request_total{namespace="demo", status!~"5.."}[2m]))
/
sum(rate(flask_http_request_total{namespace="demo"}[2m]))
```

---

### Bước 3.8 — Mở Grafana

```powershell
# Terminal riêng: port-forward Grafana
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
```

Mở `http://localhost:3000`:

- Username: `admin`
- Password: `admin123`

Vào **Explore** → Data source: Prometheus → thử các query trên.

---

### ✅ Checkpoint Lab 3

- [x] `kubectl -n demo get pods` → 4 pod `api-`* Running
- [x] Prometheus Targets → `api` UP
- [x] Query `flask_http_request_total{namespace="demo"}` tăng dần
- [x] Load pod đang chạy và gửi request

---

## Lab 4 — Canary Deploy thủ công

> **Mục tiêu:** Deploy bản mới (`v2`) qua Git → Rollout dừng ở 25% chờ lệnh → bạn quyết định promote (lên 100%) hoặc abort (về v1).

---

### Bước 4.1 — Hiểu cấu trúc canary trong api.yaml

```yaml
strategy:
  canary:
    steps:
    - setWeight: 25    # bước 1: 1 trong 4 pod chạy bản mới (25%)
    - pause: {}        # ← DỪNG VÔ HẠN, chờ lệnh promote
    - setWeight: 50    # bước 2: 2 trong 4 pod chạy bản mới
    - pause:
        duration: 30s  # tự động tiếp sau 30 giây
    - setWeight: 100   # bước 3: tất cả pod chạy bản mới
```

Với 4 replicas:

- `25%` = 1 pod mới + 3 pod cũ
- `50%` = 2 pod mới + 2 pod cũ
- `100%` = 4 pod mới + 0 pod cũ

---

### Phần A: Good Run — Deploy bản tốt (v2)

**Bước 4A.1 — Sửa VERSION trong `gitops/k8s-api/api.yaml`**

```yaml
        env:
        - name: ERROR_RATE
          value: "0"        # giữ nguyên 0 lỗi
        - name: VERSION
          value: "v2"       # ← đổi v1 thành v2
```

**Bước 4A.2 — Commit và push**

```powershell
git add gitops/k8s-api/api.yaml
git commit -m "deploy: api v2 (good version)"
git push
```

**Bước 4A.3 — Quan sát canary bắt đầu**

```powershell
# Xem trạng thái canary real-time
kubectl argo rollouts get rollout api -n demo --watch
```

**Output mong đợi:**

```
Name:            api
Namespace:       demo
Status:          ॥ Paused
Message:         CanaryPauseStep
Strategy:        Canary
  Step:          1/5
  SetWeight:     25
  ActualWeight:  25

Revision:
  canary     api-xxxxxxxxx  1     25%      1   Running     ← bản mới
  stable     api-yyyyyyyyy  3     75%      3   Running     ← bản cũ
```

**Bước 4A.4 — Quan sát metric trên Prometheus**

Mở `http://localhost:9090` → query:

```promql
flask_http_request_total{namespace="demo", status="200"}
```

Thấy cả v1 và v2 đều trả về 200 OK.

**Bước 4A.5 — Promote: cho lên tiếp**

```powershell
# Thấy ổn → cho lên bước tiếp
kubectl argo rollouts promote api -n demo
```

Rollout tự động: `25% → 50% (đợi 30s) → 100%`

**Output cuối:**

```
Status:    ✔ Healthy
Strategy:  Canary
  Step:    5/5
  SetWeight: 100
```

---

### Phần B: Bad Run — Deploy bản lỗi (abort)

**Bước 4B.1 — Deploy bản lỗi với ERROR_RATE cao**

Sửa `gitops/k8s-api/api.yaml`:

```yaml
        env:
        - name: ERROR_RATE
          value: "0.8"     # ← 80% request sẽ trả về 500
        - name: VERSION
          value: "v3-bad"
```

```powershell
git add gitops/k8s-api/api.yaml
git commit -m "deploy: api v3 (bad - 80% error rate)"
git push
```

**Bước 4B.2 — Quan sát canary dừng ở 25%**

```powershell
kubectl argo rollouts get rollout api -n demo --watch
```

**Bước 4B.3 — Kiểm tra metric lỗi tăng vọt**

```powershell
# Query trên Prometheus:
flask_http_request_total{namespace="demo", status="500"}
```

Thấy counter 500 tăng nhanh.

**Bước 4B.4 — Abort thủ công**

```powershell
# Quyết định abort → về bản cũ
kubectl argo rollouts abort api -n demo
```

**Output:**

```
Status:    ✖ Degraded
Message:   RolloutAborted: Rollout aborted update to revision 3
```

Sau abort, Rollout tự scale stable lên 100% → tất cả pod chạy bản v2 (bản tốt trước đó).

**Bước 4B.5 — Rollback về Git**

```powershell
# Revert commit lỗi
git revert HEAD --no-edit
git push
# ArgoCD sync → Rollout clean state
```

---

### ✅ Checkpoint Lab 4

- [x] Good run: `kubectl argo rollouts promote` → lên được 100%, Healthy
- [ ] Bad run: `kubectl argo rollouts abort` → về bản cũ ngay lập tức
- [ ] `git revert` + `git push` → Rollout về trạng thái sạch

---

## Challenge: "Ship Smartly" — Tự động hoàn toàn

> **Mục tiêu:** Thay `pause: {}` (chờ người) bằng `AnalysisTemplate` (máy tự chấm) + thêm SLO alert gửi email.

### Phần 1: AnalysisTemplate — tự abort khi metric tệ

Tạo file `gitops/k8s-api/analysis.yaml`:

```yaml
# file: gitops/k8s-api/analysis.yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
  namespace: demo
spec:
  metrics:
  - name: success-rate
    interval: 30s
    count: 3                           # chạy 3 lần
    successCondition: result[0] >= 0.95  # >= 95% thành công
    failureLimit: 1                    # fail 1 lần → ABORT
    provider:
      prometheus:
        address: http://kube-prometheus-stack-prometheus.monitoring:9090
        query: |
          sum(rate(flask_http_request_total{namespace="demo",status!~"5.."}[2m]))
          /
          sum(rate(flask_http_request_total{namespace="demo"}[2m]))
```

Cập nhật `gitops/k8s-api/api.yaml` — thêm `analysis` vào canary steps:

```yaml
  strategy:
    canary:
      analysis:
        templates:
        - templateName: success-rate   # ← dùng AnalysisTemplate trên
        startingStep: 1                # bắt đầu chấm từ bước 1
      steps:
      - setWeight: 25
      - pause:
          duration: 2m                 # đợi 2 phút (đủ data cho analysis)
      - setWeight: 50
      - pause:
          duration: 2m
      - setWeight: 100
```

### Phần 2: SLO Alert gửi email

Tạo file `gitops/k8s-api/prometheusrule.yaml`:

```yaml
# file: gitops/k8s-api/prometheusrule.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: api-slo
  namespace: demo
  labels:
    release: kube-prometheus-stack    # label để Prometheus Operator nhận
spec:
  groups:
  - name: api.slo
    interval: 30s
    rules:
    # SLI: tỉ lệ request thành công
    - record: job:api_success_rate:rate2m
      expr: |
        sum(rate(flask_http_request_total{namespace="demo",status!~"5.."}[2m]))
        /
        sum(rate(flask_http_request_total{namespace="demo"}[2m]))

    # Alert khi SLI < 95% (SLO = 95%)
    - alert: ApiSLOBreach
      expr: job:api_success_rate:rate2m < 0.95
      for: 1m
      labels:
        severity: critical
      annotations:
        summary: "API success rate below SLO"
        description: "Success rate {{ $value | humanizePercentage }} < 95% SLO"
```

Cấu hình AlertManager gửi email trong kube-prometheus-stack Application (thêm vào `helm.values`):

```yaml
    helm:
      values: |
        prometheus:
          prometheusSpec:
            serviceMonitorSelectorNilUsesHelmValues: false
        grafana:
          adminPassword: admin123
        alertmanager:
          config:
            global:
              smtp_smarthost: 'smtp.gmail.com:587'
              smtp_from: 'your-email@gmail.com'
              smtp_auth_username: 'your-email@gmail.com'
              smtp_auth_password: 'your-app-password'
            route:
              receiver: 'email'
            receivers:
            - name: 'email'
              email_configs:
              - to: 'your-email@gmail.com'
```

> **Lưu ý Gmail:** cần tạo App Password tại [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (bật 2FA trước).

### Phần 3: Demo auto-abort

```powershell
# Build image v4 với error rate cao
# Sửa app.py hoặc dùng env var

# Push image v4 vào minikube
docker build -t w9-api:4-bad gitops/app/
minikube image load w9-api:4-bad -p w9

# Sửa api.yaml: image: w9-api:4-bad, ERROR_RATE: "0.8"
git commit -am "deploy: v4-bad with 80% errors"
git push

# Quan sát AnalysisRun tự chấm và abort
kubectl argo rollouts get rollout api -n demo --watch
# Sau ~2 phút: Status: ✖ Degraded (auto-aborted by analysis)
```

---

## Bảng lệnh hay dùng (buổi chiều)

```powershell
# ──── ARGO ROLLOUTS ────
kubectl argo rollouts get rollout api -n demo --watch    # theo dõi canary
kubectl argo rollouts promote api -n demo                # cho lên bước tiếp
kubectl argo rollouts abort api -n demo                  # hủy, về bản cũ
kubectl argo rollouts list rollouts -n demo              # liệt kê

# ──── PORT-FORWARD ────
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090   # Prometheus
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80        # Grafana
kubectl -n argocd port-forward svc/argocd-server 8080:443                           # ArgoCD

# ──── DEBUG ────
kubectl -n demo get rollout api -o yaml                  # xem full Rollout spec
kubectl -n demo get analysisrun                          # xem kết quả analysis
kubectl -n demo describe analysisrun <name>              # chi tiết analysis

# ──── LOAD TEST ────
kubectl -n demo run load --image=busybox --restart=Never -- `
  sh -c "while true; do wget -qO- http://api:8080/; sleep 0.2; done"
kubectl -n demo delete pod load                          # dừng load test

# ──── PROMETHEUS QUERIES ────
# Tổng request
flask_http_request_total{namespace="demo"}

# Tỉ lệ thành công (SLI)
sum(rate(flask_http_request_total{namespace="demo",status!~"5.."}[2m]))
/ sum(rate(flask_http_request_total{namespace="demo"}[2m]))

# Chỉ request lỗi
flask_http_request_total{namespace="demo", status="500"}
```

---

## Các lỗi thường gặp


| Lỗi                                             | Nguyên nhân                                              | Cách sửa                                                                                        |
| ----------------------------------------------- | -------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Pod `Pending` sau khi cài kube-prometheus-stack | Node không đủ RAM                                        | `minikube delete -p w9` rồi start lại với `--memory=6144`                                       |
| Prometheus Targets không thấy `api`             | ServiceMonitor sai selector hoặc label                   | Kiểm tra `app: api` có khớp Service và ServiceMonitor không                                     |
| `kubectl argo rollouts` không nhận ra           | Plugin chưa cài                                          | Download `.exe` và để vào PATH                                                                  |
| Rollout bị `Degraded` sau abort                 | Trạng thái bình thường sau abort                         | `git revert + push` để clean                                                                    |
| AnalysisRun không chạy                          | `startingStep` chưa đúng hoặc Prometheus không reachable | Kiểm tra address của Prometheus trong AnalysisTemplate                                          |
| Alert không gửi email                           | SMTP config sai hoặc App Password chưa đúng              | Kiểm tra AlertManager logs: `kubectl -n monitoring logs -l app.kubernetes.io/name=alertmanager` |


