# Phase 1 — Infrastructure Setup

## 1. Plain Kubernetes on Raspberry Pi

### Install K8s on your Pi (kubeadm)

```bash
# On all nodes — disable swap
sudo swapoff -a
sudo sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab

# Install containerd
sudo apt-get update
sudo apt-get install -y containerd
sudo mkdir -p /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml
sudo systemctl restart containerd

# Install kubeadm, kubelet, kubectl
sudo apt-get install -y apt-transport-https ca-certificates curl
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /' | sudo tee /etc/apt/sources.list.d/kubernetes.list
sudo apt-get update
sudo apt-get install -y kubelet kubeadm kubectl
sudo apt-mark hold kubelet kubeadm kubectl

# Init cluster (on master node)
sudo kubeadm init --pod-network-cidr=10.244.0.0/16

# Setup kubectl
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

# Install Flannel CNI
kubectl apply -f https://raw.githubusercontent.com/flannel-io/flannel/master/Documentation/kube-flannel.yml
```

### Install NGINX Ingress Controller

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.0/deploy/static/provider/baremetal/deploy.yaml
```

### Install cert-manager (optional, for TLS)

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml
```

---

## 2. ArgoCD Setup

### Install ArgoCD

```bash
kubectl create namespace argocd

kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for pods to be ready
kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd
```

### Access ArgoCD UI

```bash
# Port-forward (initial access)
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Get initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d
```

### Expose ArgoCD via Ingress (optional)

```bash
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: argocd-ingress
  namespace: argocd
  annotations:
    nginx.ingress.kubernetes.io/ssl-passthrough: "true"
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
spec:
  ingressClassName: nginx
  rules:
  - host: argocd.versus.local
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: argocd-server
            port:
              number: 443
EOF
```

### Connect ArgoCD to your GitHub repo

```bash
# Login via CLI
argocd login localhost:8080 --username admin --password <password> --insecure

# Add your repo (use HTTPS + PAT or SSH)
argocd repo add https://github.com/YOUR_ORG/versus \
  --username YOUR_GITHUB_USER \
  --password YOUR_GITHUB_PAT
```

---

## 3. Namespaces & Secrets

### Create namespaces

```bash
kubectl create namespace versus-prod
kubectl create namespace versus-staging
```

### Create secrets

```bash
# Anthropic API key (for soul-svc)
kubectl create secret generic anthropic-secret \
  --from-literal=api-key=YOUR_ANTHROPIC_API_KEY \
  -n versus-prod

# New Relic license key (for all services)
kubectl create secret generic newrelic-secret \
  --from-literal=license-key=YOUR_NEWRELIC_LICENSE_KEY \
  -n versus-prod

# PostgreSQL credentials
kubectl create secret generic postgres-secret \
  --from-literal=username=versus \
  --from-literal=password=YOUR_POSTGRES_PASSWORD \
  --from-literal=database=versus \
  -n versus-prod

# GitHub Container Registry (GHCR) pull secret
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=YOUR_GITHUB_USER \
  --docker-password=YOUR_GITHUB_PAT \
  --docker-email=YOUR_EMAIL \
  -n versus-prod
```

---

## 4. Deploy App-of-Apps via ArgoCD

Once your repo is pushed to GitHub:

```bash
kubectl apply -f argocd/app-of-apps.yaml
```

ArgoCD will automatically pick up all child apps and deploy them.

---

## 5. Verify Everything

```bash
# Check ArgoCD apps
kubectl get applications -n argocd

# Check versus namespace
kubectl get all -n versus-prod

# Check ingress
kubectl get ingress -n versus-prod
```

---

## 6. Local DNS (optional, for Pi LAN access)

Add to your `/etc/hosts` (or router DNS):

```
<PI_IP>  versus.local
<PI_IP>  argocd.versus.local
```
