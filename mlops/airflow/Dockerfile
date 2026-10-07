FROM apache/airflow:2.11.0-python3.12
RUN pip install --no-cache-dir apache-airflow==2.11.0 pandas==2.2.3 numpy==2.2.5 pyarrow==22.0.0 boto3==1.40.69
COPY --chown=airflow:root src /opt/airflow/project/src
COPY --chown=airflow:root mlops/airflow/preprocessing_data.py /opt/airflow/dags/preprocessing_data.py
ENV PYTHONPATH=/opt/airflow/project
