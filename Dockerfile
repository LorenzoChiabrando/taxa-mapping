
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-tk \
    xvfb \
    x11vnc \
    fluxbox \
    novnc \
    websockify \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libxtst6 \
    libgl1 \
    libglx-mesa0 \
    libfontconfig1 \
    libxcb-cursor0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN echo '#!/bin/bash\n\
Xvfb :0 -screen 0 1200x800x24 &\n\
sleep 1\n\
fluxbox &\n\
x11vnc -display :0 -forever -nopw -listen localhost -xkb &\n\
/usr/share/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 8080 &\n\
export DISPLAY=:0\n\
python ui/app.py' > /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh

EXPOSE 8080

CMD ["/app/entrypoint.sh"]
