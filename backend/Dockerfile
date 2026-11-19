FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EDUSCAN_DATA_DIR=/var/lib/eduscan

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --user-group eduscan \
    && install -d -o eduscan -g eduscan -m 0700 /var/lib/eduscan

WORKDIR /srv/eduscan
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app app/
COPY resources resources/
COPY templates templates/
COPY production.py ./

USER eduscan
EXPOSE 8000
CMD ["python", "production.py"]
