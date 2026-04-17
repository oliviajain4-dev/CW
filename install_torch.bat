@echo off
chcp 65001 > nul

echo.
echo === Install missing packages into venv ===
echo.

set VENV_PIP=venv\Scripts\pip.exe
set VENV_PYTHON=venv\Scripts\python.exe

echo Installing: transformers scipy opencv-python ultralytics rembg pandas polars open_clip_torch
echo.

%VENV_PIP% install transformers scipy opencv-python ultralytics rembg pandas polars open_clip_torch

echo.
echo === Verify ===
%VENV_PYTHON% -c "import torch; print('torch       :', torch.__version__)"
%VENV_PYTHON% -c "import open_clip; print('open_clip   : OK')"
%VENV_PYTHON% -c "import transformers; print('transformers:', transformers.__version__)"
%VENV_PYTHON% -c "import scipy; print('scipy       :', scipy.__version__)"
%VENV_PYTHON% -c "import cv2; print('opencv      :', cv2.__version__)"
%VENV_PYTHON% -c "import pandas; print('pandas      :', pandas.__version__)"
%VENV_PYTHON% -c "import polars; print('polars      :', polars.__version__)"

echo.
echo Done. Restart the app.
pause
