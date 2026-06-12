# Evidence — Lab Sáng W9: GitOps & CI/CD

> **Repo:** https://github.com/tuu-ngo/CICD_practice
> **Cluster:** minikube profile `w9`
> **Ngày thực hành:** 11/06/2026

---

## Mục lục

- [Lab 0 — Cụm + Repo](#lab-0--cụm--repo)
- [Lab 1 — Cài ArgoCD](#lab-1--cài-argocd)
- [Lab 2 — ArgoCD tự deploy](#lab-2--argocd-tự-deploy)
- [Lab 3 — Sync & Self-Heal](#lab-3--sync--self-heal)
- [Lab 4 — Rollback git revert](#lab-4--rollback-git-revert)
- [Lab 5 — App-of-Apps](#lab-5--app-of-apps)
- [Lab 6 — Sync Waves](#lab-6--sync-waves)
- [Lab 7 — CI + Branch Protection](#lab-7--ci--branch-protection)

---

## Lab 0 — Cụm + Repo

### Kết quả đạt được
- Cluster minikube `w9` khởi động thành công
- Repo `https://github.com/tuu-ngo/CICD_practice` có file `gitops/k8s/web.yaml`

### Terminal output

![alt text](image.png)
```

### File được tạo

**`gitops/k8s/web.yaml`** — Deployment nginx:1.27, replicas: 2, namespace: demo

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  namespace: demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web
        image: nginx:1.27
```

### 📸 Ảnh cần chụp
![alt text](image-1.png)

---

## Lab 1 — Cài ArgoCD

### Kết quả đạt được
- Namespace `argocd` được tạo
- Tất cả pods ArgoCD ở trạng thái `Running`

### Terminal output

```
PS> kubectl create namespace argocd
namespace/argocd created

PS> kubectl apply --server-side -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
[... applied ...]

PS> kubectl -n argocd get pods
NAME                                               READY   STATUS    RESTARTS        AGE
argocd-application-controller-0                    1/1     Running   1 (3m37s ago)   14h
argocd-applicationset-controller-b7669f646-wwfd2   1/1     Running   1 (3m37s ago)   14h
argocd-dex-server-569b757-c5qnr                    1/1     Running   2 (3m37s ago)   14h
argocd-notifications-controller-58ff87546-jm6w6    1/1     Running   2 (3m37s ago)   14h
argocd-redis-b9496d8bf-psl2c                       1/1     Running   1 (3m37s ago)   14h
argocd-repo-server-75ffcfc9df-pbl2z                1/1     Running   1 (3m37s ago)   14h
argocd-server-76755b46f8-6ft47                     1/1     Running   1 (3m37s ago)   14h
```

### 📸 Ảnh cần chụp
![alt text](image-2.png)

![alt text](image-3.png)
---

## Lab 2 — ArgoCD tự deploy (không kubectl apply)

### Kết quả đạt được
- Application `web` được tạo bằng `kubectl apply -f gitops/argocd/apps/web.yaml`
- ArgoCD tự phát hiện repo và deploy Deployment vào namespace `demo`
- **Không chạy** `kubectl apply -f gitops/k8s/web.yaml` — ArgoCD làm thay

### File được tạo

**`gitops/argocd/apps/web.yaml`** — Application object chỉ dẫn cho ArgoCD:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: web
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/tuu-ngo/CICD_practice.git
    targetRevision: main
    path: gitops/k8s
  destination:
    server: https://kubernetes.default.svc
    namespace: demo
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### Terminal output

```
PS> kubectl apply -f gitops/argocd/apps/web.yaml
application.argoproj.io/web created

PS> kubectl -n argocd get application web -w
NAME   SYNC STATUS   HEALTH STATUS
web    Synced        Progressing
web    Synced        Healthy

PS> kubectl -n demo get deployment,pod
NAME                  READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/web   2/2     2            2           117s

NAME                     READY   STATUS    RESTARTS   AGE
pod/web-7dbf7cc5-kkrtd   1/1     Running   0          117s
pod/web-7dbf7cc5-rw5wd   1/1     Running   0          117s
```

### 📸 Ảnh cần chụp
![alt text](image-4.png)

![alt text](image-5.png)

![alt text](image-6.png)

---

## Lab 3 — Sync qua Git & Self-Heal

### Kết quả đạt được
- Thay đổi `replicas: 2 → 4` trong Git → ArgoCD tự scale, không cần kubectl
- Thay đổi tay bằng `kubectl scale --replicas=9` → ArgoCD tự đảo về 4 (theo Git)

### Terminal output — Phần A: Thay đổi qua Git

```
PS> git commit -am "scale: web 2->4 replicas" && git push
[main a666585] scale: web 2->4 replicas

PS> kubectl -n demo get pod -w
# 2 pod mới được tạo → tổng 4 pod
NAME                     READY   STATUS    RESTARTS
web-7dbf7cc5-kkrtd       1/1     Running   0
web-7dbf7cc5-rw5wd       1/1     Running   0
web-7dbf7cc5-new1        1/1     Running   0   ← pod mới ArgoCD tạo
web-7dbf7cc5-new2        1/1     Running   0   ← pod mới ArgoCD tạo
```

### Terminal output — Phần B: Self-Heal

```
PS> kubectl -n demo scale deployment/web --replicas=9
deployment.apps/web scaled

PS> kubectl -n demo get deployment web -w
NAME   READY   UP-TO-DATE   AVAILABLE
web    9/9     9            9          ← tay scale lên 9
web    4/4     4            4          ← ArgoCD self-heal về 4 (Git)
```

### 📸 Ảnh cần chụp
![alt text](image-7.png)

---

## Lab 4 — Rollback bằng `git revert`

### Kết quả đạt được
- Chứng minh `kubectl rollout undo` **thất bại** (ArgoCD self-heal ghi đè lại)
- `git revert HEAD` + `git push` → ArgoCD tự rollback thành công
- Git history đầy đủ: commit "Revert" có author + timestamp

### Terminal output — kubectl rollout undo thất bại

```
# Sau khi push image lỗi (nginx:1.99-FAKE):
PS> kubectl -n demo rollout undo deployment/web
deployment.apps/web rolled back

# Ngay sau đó (image về nginx:1.27):
PS> kubectl -n demo get deployment web -o jsonpath='{.spec.template.spec.containers[0].image}'
nginx:1.27

# Vài phút sau (ArgoCD ghi đè lại):
PS> kubectl -n demo get deployment web -o jsonpath='{.spec.template.spec.containers[0].image}'
nginx:1.99-FAKE    ← ArgoCD self-heal ghi đè → rollback THẤT BẠI
```

### Terminal output — git revert thành công

```
PS> git revert HEAD --no-edit && git push
[main xyz9999] Revert "deploy: nginx v1.99 (version mới)"

PS> git log --oneline -5
xyz9999 Revert "deploy: nginx v1.99 (version mới)"
abc1234 deploy: nginx v1.99 (version mới)
def5678 scale: web 2->4 replicas
...

PS> kubectl -n demo get pod -w
# Pod tự chuyển về Running với nginx:1.27
```



---

## Lab 5 — App-of-Apps Pattern

### Kết quả đạt được
- `root` Application được tạo, trỏ tới `gitops/argocd/apps/`
- `root` tự quản lý `web` Application
- Pattern hoạt động: thêm file vào `apps/` → root tự tạo Application con

### File được tạo

**`gitops/argocd/root.yaml`** — Root Application:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/tuu-ngo/CICD_practice.git
    targetRevision: main
    path: gitops/argocd/apps
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
  ignoreDifferences:
  - group: argoproj.io
    kind: Application
    managedFieldsManagers:
    - argocd-application-controller
```

### Terminal output

```
PS> kubectl apply -f gitops/argocd/root.yaml
application.argoproj.io/root created

PS> kubectl -n argocd get applications
NAME   SYNC STATUS   HEALTH STATUS
root   Synced        Healthy
web    Synced        Healthy
```

### Cấu trúc repo tại thời điểm này

```
CICD_practice/
└── gitops/
    ├── k8s/
    │   └── web.yaml
    └── argocd/
        ├── root.yaml          ← root Application (apply 1 lần duy nhất)
        └── apps/
            └── web.yaml       ← Application con (root tự quản)
```

### 📸 Ảnh cần chụp
![alt text](image-8.png)

![alt text](image-9.png)
---

## Lab 6 — Sync Waves

### Kết quả đạt được
- Namespace, ConfigMap, Deployment, Service apply đúng thứ tự wave
- Pod đọc được ConfigMap qua `envFrom`
- Không bị lỗi `CreateContainerConfigError`

### File được tạo/cập nhật

**`gitops/k8s/namespace.yaml`** — wave -1 (chạy đầu tiên):

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: demo
  annotations:
    argocd.argoproj.io/sync-wave: "-1"
```

**`gitops/k8s/web.yaml`** — 3 resource với sync-wave:

```yaml
# ConfigMap — wave 0
apiVersion: v1
kind: ConfigMap
metadata:
  name: web-config
  namespace: demo
  annotations:
    argocd.argoproj.io/sync-wave: "0"
data:
  MESSAGE: "hello from gitops"
  VERSION: "v1.0"
---
# Deployment — wave 1
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  namespace: demo
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  replicas: 2
  ...
  envFrom:
  - configMapRef:
      name: web-config
---
# Service — wave 2
apiVersion: v1
kind: Service
metadata:
  name: web
  namespace: demo
  annotations:
    argocd.argoproj.io/sync-wave: "2"
```

### Terminal output

```
PS> kubectl -n demo get all,configmap
NAME                       READY   STATUS    RESTARTS
pod/web-xxxxxxxxx-xxxxx    1/1     Running   0
pod/web-xxxxxxxxx-xxxxx    1/1     Running   0

NAME                  READY   UP-TO-DATE   AVAILABLE
deployment.apps/web   2/2     2            2

NAME          TYPE        CLUSTER-IP
service/web   ClusterIP   10.96.xxx.xxx

NAME                         DATA
configmap/web-config         2

PS> kubectl -n demo exec deploy/web -- env | grep MESSAGE
MESSAGE=hello from gitops
```

### 📸 Ảnh cần chụp
![alt text](image-10.png)

![alt text](image-11.png)

---

## Lab 7 — CI plan-on-PR + Branch Protection

### Kết quả đạt được
- GitHub Actions `validate.yml` chạy tự động khi có PR thay đổi `gitops/k8s/**`
- PR với YAML sai schema → CI ❌ → nút Merge bị khóa
- PR với YAML đúng → CI ✅ → Merge được
- Branch protection: không ai push thẳng vào `main`

### File được tạo

**`gitops/.github/workflows/validate.yml`** — CI validate manifest:

```yaml
name: validate
on:
  pull_request:
    paths:
      - "gitops/k8s/**"
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install kubeconform
        run: |
          curl -sSLo kc.tgz https://github.com/yannh/kubeconform/releases/download/v0.6.7/kubeconform-linux-amd64.tar.gz
          tar -xzf kc.tgz && sudo mv kubeconform /usr/local/bin/
      - name: Validate manifests
        run: kubeconform -strict -summary -output pretty gitops/k8s/
```

### Branch Protection rules (GitHub Settings)

| Rule | Trạng thái |
|------|-----------|
| Require a pull request before merging | ✅ Bật |
| Require status checks (`validate`) | ✅ Bật |
| Do not allow bypassing | ✅ Bật |

### 📸 Ảnh cần chụp
![alt text](image-12.png)
![alt text](image-13.png)


