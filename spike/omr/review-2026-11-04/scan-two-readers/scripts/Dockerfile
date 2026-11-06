FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends time libgl1 libglib2.0-0 && pip install --no-cache-dir homr==0.6.2 && homr --init
COPY safe.py job.sh /
COPY pages /pages
CMD ["bash","/job.sh"]
