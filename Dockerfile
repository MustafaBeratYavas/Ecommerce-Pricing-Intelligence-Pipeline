# syntax=docker/dockerfile:1.7

FROM python:3.14-slim-bookworm AS base

ARG APP_VERSION=1.0.0
ARG APP_UID=10001
ARG APP_GID=10001

LABEL org.opencontainers.image.title="E-Commerce Pricing Intelligence Pipeline" \
    org.opencontainers.image.description="Containerized Selenium-based pricing intelligence pipeline with SQLite warehousing and analytics." \
    org.opencontainers.image.source="https://github.com/MustafaBeratYavas/ecommerce-pricing-intelligence-pipeline" \
    org.opencontainers.image.version="${APP_VERSION}" \
    org.opencontainers.image.licenses="MIT"

ENV APP_ENV=docker \
    PRICING_PIPELINE_CONFIG_DIR=/app/config \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libu2f-udev \
    libvulkan1 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    wget \
    xdg-utils \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL \
    -o /tmp/google-linux-signing-key.pub \
    https://dl.google.com/linux/linux_signing_key.pub \
    && gpg --dearmor -o /etc/apt/keyrings/google-linux.gpg /tmp/google-linux-signing-key.pub \
    && rm -f /tmp/google-linux-signing-key.pub \
    && chmod a+r /etc/apt/keyrings/google-linux.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-linux.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${APP_GID}" appuser \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /bin/bash appuser

COPY docker/entrypoint.sh /usr/local/bin/ecommerce-pricing-intelligence-pipeline-entrypoint

RUN chmod +x /usr/local/bin/ecommerce-pricing-intelligence-pipeline-entrypoint

FROM base AS production

COPY pyproject.toml README.md requirements.lock ./
COPY src ./src
COPY config ./config
COPY product_codes.txt ./

RUN python -m pip install --upgrade pip \
    && python -m pip install --constraint requirements.lock "." \
    && mkdir -p database logs reports/charts .browser_profile downloaded_files \
    && chown -R appuser:appuser \
    /app \
    /usr/local/lib/python3.11/site-packages/seleniumbase/drivers

USER appuser

ENTRYPOINT ["ecommerce-pricing-intelligence-pipeline-entrypoint"]
CMD ["run"]

FROM production AS development

USER root

COPY tests ./tests

RUN python -m pip install --constraint requirements.lock ".[dev]" \
    && chown -R appuser:appuser /app

USER appuser

FROM production AS final
