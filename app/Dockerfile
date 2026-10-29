FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY app/requirements.lock /srv/requirements.lock
COPY wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels --require-hashes -r requirements.lock && rm -rf /wheels && useradd --uid 10001 --create-home app && mkdir /data && chown 10001:10001 /data
COPY --chown=root:root app /srv/app
RUN find /srv/app -type d -exec chmod 755 {} + && find /srv/app -type f -exec chmod 644 {} +
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--proxy-headers", "--forwarded-allow-ips=*", "--workers", "1", "--limit-concurrency", "160", "--timeout-keep-alive", "5"]
