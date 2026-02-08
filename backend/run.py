from app.core.win_dlls import add_nvidia_dll_dirs
add_nvidia_dll_dirs()

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)