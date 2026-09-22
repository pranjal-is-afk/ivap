@echo off
cd /d "%~dp0.."
set UVEXE=C:\Users\pranj\AppData\Local\hermes\bin\uv.exe
echo [%date% %time%] starting pip installs > install_progress.txt
"%UVEXE%" pip install --python .venv\Scripts\python.exe torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121 >> install_progress.txt 2>&1 || goto :fail
echo [%date% %time%] torch done >> install_progress.txt
"%UVEXE%" pip install --python .venv\Scripts\python.exe fastapi==0.115.6 uvicorn==0.34.0 sqlalchemy==2.0.36 psycopg2-binary==2.9.10 pydantic==2.10.4 pydantic-settings==2.7.0 pyjwt==2.10.1 python-multipart==0.0.20 ultralytics==8.3.58 lapx>=0.5.9 shapely==2.0.6 numpy==1.26.4 opencv-python==4.10.0.84 easyocr==1.7.2 websockets==14.1 pytest==8.3.4 httpx==0.28.1 python-dotenv==1.0.1 >> install_progress.txt 2>&1 || goto :fail
echo [%date% %time%] ALL DONE >> install_progress.txt
echo DONE > install_done.marker
exit /b 0
:fail
echo [%date% %time%] INSTALL FAILED >> install_progress.txt
