#!/usr/bin/env bash
# Install NVIDIA Container Toolkit in WSL so Docker can passthrough the GTX 1650.
# Run ONCE: bash scripts/install_nvidia_docker.sh  (it will prompt for sudo)
set -e

echo "[1/4] Adding NVIDIA container repo..."
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --yes --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null

echo "[2/4] Installing nvidia-container-toolkit..."
sudo apt-get update -qq
sudo apt-get install -y nvidia-container-toolkit

echo "[3/4] Configuring Docker to use the nvidia runtime..."
sudo nvidia-ctk runtime configure --runtime=docker

echo "[4/4] Restarting Docker..."
if command -v systemctl >/dev/null && systemctl is-active --quiet docker; then
  sudo systemctl restart docker
else
  sudo service docker restart || true
fi

echo
echo "Verification:"
docker info 2>/dev/null | grep -i "runtime" || true
echo
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi || {
  echo "GPU test failed. You can still proceed — some setups use --runtime=nvidia instead of --gpus all."
  exit 1
}
echo "GPU passthrough is live."
