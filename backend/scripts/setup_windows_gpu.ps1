# Run from backend/ folder
python -m venv venv
.\venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -r requirements\gpu-cu124.txt

# Verify torch + CUDA works
python -c "import torch; import torch.backends.cudnn as cudnn; print('Torch:', torch.__version__); print('CUDA:', torch.version.cuda); print('GPU:', torch.cuda.is_available()); print('cuDNN:', cudnn.version())"
