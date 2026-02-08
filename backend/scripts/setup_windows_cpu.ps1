# Run from backend/ folder
python -m venv venv
.\venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -r requirements\cpu.txt

# Verify torch works
python -c "import torch; print('Torch:', torch.__version__); print('CUDA:', torch.version.cuda); print('GPU:', torch.cuda.is_available())"
