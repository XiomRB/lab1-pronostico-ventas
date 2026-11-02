"""Fechas de operación compartidas por los DAGs."""
import os
from datetime import datetime, timedelta

INICIO = datetime.fromisoformat(os.environ.get("LAB1_INICIO", "2017-04-01"))
FIN = datetime.fromisoformat(os.environ.get("LAB1_FIN", "2017-08-24")) + timedelta(hours=23, minutes=59)
RAPIDOS = {"retries": 2, "retry_delay": timedelta(seconds=15)}
