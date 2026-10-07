ARG PYTHON_IMAGE=mlops.gitlab.yandexcloud.net:5050/s87443/mlops_final_project_reznik_vasilii/build-deps/python@sha256:6e13e65c55e33adf203d77ee371cf8bf5d81bd4902ef07565721f46bf44917af
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    ca-certificates curl openssh-client skopeo jq \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv==0.11.20
COPY scripts/install_k8s_tools.sh /tmp/install_k8s_tools.sh
RUN TOOLS_DIR=/usr/local/bin sh /tmp/install_k8s_tools.sh \
    && rm /tmp/install_k8s_tools.sh
