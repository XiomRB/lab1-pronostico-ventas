"""Panel de un corte: una fila por serie y día objetivo, solo con lo conocido en el corte."""
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from pronostico_ventas.almacen.consulta import as_of, series_esperadas
from pronostico_ventas.config import Configuracion

VERSION = 1
DIAS_HISTORIA = 400
CARACTERISTICAS = [
    "h", "dia_semana", "dia_mes", "mes", "quincena", "store_nbr", "familia_codigo", "cluster", "tipo_tienda",
    "media_7", "media_28", "media_91", "desvio_28", "ceros_28", "media_dia_semana", "lag_364", "dias_sin_venta",
    "promociones", "promociones_media_28", "feriado", "evento", "dia_laboral_extra", "petroleo",
    "petroleo_cambio_28", "transacciones_media_28",
]


def _resumen_series(ventas: pd.DataFrame, corte: date) -> pd.DataFrame:
    fin = pd.Timestamp(corte)
    grupos = ["store_nbr", "family"]

    def ventana(dias: int) -> pd.DataFrame:
        return ventas[ventas["date"] >= fin - pd.Timedelta(days=dias)]

    ultimos = ventana(28).groupby(grupos)
    resumen = pd.DataFrame({
        "media_28": ultimos["sales"].mean(),
        "desvio_28": ultimos["sales"].std(),
        "ceros_28": ultimos["sales"].agg(lambda s: (s == 0).mean()),
        "promociones_media_28": ultimos["onpromotion"].mean(),
    })
    resumen["media_7"] = ventana(7).groupby(grupos)["sales"].mean()
    resumen["media_91"] = ventana(91).groupby(grupos)["sales"].mean()
    con_venta = ventas[ventas["sales"] > 0].groupby(grupos)["date"].max()
    resumen["dias_sin_venta"] = (fin - con_venta).dt.days
    return resumen.reset_index()


def _media_mismo_dia(ventas: pd.DataFrame) -> pd.DataFrame:
    recientes = ventas.assign(dia_semana=ventas["date"].dt.dayofweek).sort_values("date", kind="stable")
    ultimas = recientes.groupby(["store_nbr", "family", "dia_semana"]).tail(4)
    return (
        ultimas.groupby(["store_nbr", "family", "dia_semana"])["sales"].mean()
        .rename("media_dia_semana").reset_index()
    )


def _calendario(cfg: Configuracion, corte: date, fechas: pd.DatetimeIndex, tiendas: pd.DataFrame) -> pd.DataFrame:
    feriados = as_of(cfg, "feriados", corte, desde=fechas[0].date())
    feriados = feriados[feriados["date"].isin(fechas) & ~feriados["transferred"]]
    filas = []
    for tienda in tiendas.itertuples():
        aplica = (
            (feriados["locale"] == "National")
            | ((feriados["locale"] == "Regional") & (feriados["locale_name"] == tienda.state))
            | ((feriados["locale"] == "Local") & (feriados["locale_name"] == tienda.city))
        )
        propios = feriados[aplica]
        filas.append(pd.DataFrame({
            "store_nbr": tienda.store_nbr,
            "date": fechas,
            "feriado": fechas.isin(propios.loc[propios["type"].isin(["Holiday", "Additional", "Transfer", "Bridge"]), "date"]),
            "evento": fechas.isin(propios.loc[propios["type"] == "Event", "date"]),
            "dia_laboral_extra": fechas.isin(propios.loc[propios["type"] == "Work Day", "date"]),
        }))
    return pd.concat(filas, ignore_index=True)


def construir(cfg: Configuracion, corte: date, conocido: date | None = None) -> pd.DataFrame:
    """Construye el panel de `corte`. Toda fuente se lee con as_of, nunca directamente.

    Con `conocido` usa las correcciones sabidas en esa fecha, para reprocesar un corte pasado.
    """
    visto = conocido or corte
    horizonte = cfg.modelo["horizonte_dias"]
    desde = corte - timedelta(days=DIAS_HISTORIA)
    ventas = as_of(cfg, "ventas", visto, columnas=["date", "store_nbr", "family", "sales", "onpromotion"], desde=desde)
    ventas = ventas[ventas["date"] < pd.Timestamp(corte)]
    tiendas = as_of(cfg, "tiendas", visto, columnas=["store_nbr", "city", "state", "type", "cluster"])
    familias = sorted(series_esperadas(cfg)["family"].unique())
    codigos = {familia: indice for indice, familia in enumerate(familias)}

    series = pd.concat([series_esperadas(cfg), ventas[["store_nbr", "family"]]]).drop_duplicates()
    series = series.sort_values(["store_nbr", "family"], ignore_index=True)
    fechas = pd.date_range(corte + timedelta(days=1), corte + timedelta(days=horizonte))
    panel = series.merge(pd.DataFrame({"date": fechas}), how="cross")
    panel["corte"] = pd.Timestamp(corte)
    panel["h"] = (panel["date"] - panel["corte"]).dt.days
    panel["dia_semana"] = panel["date"].dt.dayofweek
    panel["dia_mes"] = panel["date"].dt.day
    panel["mes"] = panel["date"].dt.month
    panel["quincena"] = panel["dia_mes"].isin([1, 2, 15, 16, 30, 31]).astype(int)
    panel["familia_codigo"] = panel["family"].map(codigos).astype(float)

    panel = panel.merge(_resumen_series(ventas, corte), how="left", on=["store_nbr", "family"])
    panel = panel.merge(_media_mismo_dia(ventas), how="left", on=["store_nbr", "family", "dia_semana"])
    anterior = ventas[["date", "store_nbr", "family", "sales"]].rename(columns={"sales": "lag_364", "date": "fecha_anterior"})
    panel["fecha_anterior"] = panel["date"] - pd.Timedelta(days=364)
    panel = panel.merge(anterior, how="left", on=["fecha_anterior", "store_nbr", "family"]).drop(columns="fecha_anterior")

    plan = as_of(cfg, "promociones", visto, columnas=["date", "store_nbr", "family", "onpromotion"], desde=corte + timedelta(days=1))
    panel = panel.merge(plan.rename(columns={"onpromotion": "promociones"}), how="left", on=["date", "store_nbr", "family"])

    panel = panel.merge(tiendas[["store_nbr", "cluster", "type"]], how="left", on="store_nbr")
    panel["tipo_tienda"] = panel.pop("type").map(lambda t: ord(t) - 65 if isinstance(t, str) else np.nan)
    panel = panel.merge(_calendario(cfg, visto, fechas, tiendas), how="left", on=["store_nbr", "date"])
    for columna in ("feriado", "evento", "dia_laboral_extra"):
        panel[columna] = panel[columna].astype(float)

    petroleo = as_of(cfg, "petroleo", visto, columnas=["date", "dcoilwtico"], desde=corte - timedelta(days=60)).dropna()
    petroleo = petroleo[petroleo["date"] < pd.Timestamp(corte)]
    panel["petroleo"] = petroleo["dcoilwtico"].iloc[-1] if len(petroleo) else np.nan
    panel["petroleo_cambio_28"] = petroleo["dcoilwtico"].iloc[-1] - petroleo["dcoilwtico"].iloc[0] if len(petroleo) else np.nan
    transacciones = as_of(cfg, "transacciones", visto, columnas=["date", "store_nbr", "transactions"], desde=corte - timedelta(days=28))
    transacciones = transacciones[transacciones["date"] < pd.Timestamp(corte)]
    panel = panel.merge(
        transacciones.groupby("store_nbr")["transactions"].mean().rename("transacciones_media_28").reset_index(),
        how="left", on="store_nbr",
    )
    panel["escala"] = panel["media_28"].fillna(0).clip(lower=0) + 1
    numericas = [c for c in CARACTERISTICAS if c != "store_nbr"] + ["escala"]
    panel[numericas] = panel[numericas].astype("float32")
    return panel


def _ruta(cfg: Configuracion, corte: date) -> Path:
    return cfg.procesado / f"v{VERSION}" / f"panel_{corte.isoformat()}.parquet"


def obtener(cfg: Configuracion, corte: date) -> pd.DataFrame:
    """Panel persistido de un corte. Lo conocido en un corte no cambia, así que se reutiliza."""
    ruta = _ruta(cfg, corte)
    if ruta.is_file():
        return pd.read_parquet(ruta)
    panel = construir(cfg, corte)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f".{ruta.name}.tmp")
    panel.to_parquet(temporal, index=False, compression="zstd")
    os.replace(temporal, ruta)
    return pd.read_parquet(ruta)


def objetivos(cfg: Configuracion, conocido: date, desde: date, hasta: date) -> pd.DataFrame:
    """Ventas reales conocidas en `conocido`. Una fecha sin datos no aparece: nunca se asume 0."""
    ventas = as_of(cfg, "ventas", conocido, columnas=["date", "store_nbr", "family", "sales"], desde=desde)
    return ventas[ventas["date"] <= pd.Timestamp(hasta)]
