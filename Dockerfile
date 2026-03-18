FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3-pip git curl build-essential ca-certificates ffmpeg libgl1 && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade pip setuptools wheel

WORKDIR /workspace

# copy minimal project files and requirements
COPY requirements.txt ./
RUN pip3 install --extra-index-url https://download.pytorch.org/whl/cu121 torch==2.5.1 --prefer-binary || true
RUN pip3 install -r requirements.txt

# Copy the repo
COPY . /workspace

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["/bin/bash"]
