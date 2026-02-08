from app.core.win_dlls import patch_nvidia_dlls
patch_nvidia_dlls()

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
