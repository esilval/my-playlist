"""Puerto de métricas y su implementación EMF (feature 004, plan D11)."""

import json

import pytest

from app.shared.infrastructure.emf import EmfMetrics, emf_fields, namespace_for
from app.shared.metrics import InMemoryMetrics, Metrics, Recorded


def test_F004_R011_emf_escribe_una_linea_json_con_el_bloque_aws_y_el_valor() -> None:
    lines: list[str] = []
    metrics: Metrics = EmfMetrics("MyPlaylist/production", write=lines.append)

    metrics.timing("RequestLatency", 41.7, Route="/api/public/establishments/{code}/search")
    metrics.count("TrackStarted")

    assert len(lines) == 2
    timing, count = (json.loads(line) for line in lines)
    # Una línea JSON por métrica, sin saltos dentro.
    assert all("\n" not in line for line in lines)

    directive = timing["_aws"]["CloudWatchMetrics"][0]
    assert directive["Dimensions"] == [["Route"]]
    assert directive["Metrics"] == [{"Name": "RequestLatency", "Unit": "Milliseconds"}]
    assert isinstance(timing["_aws"]["Timestamp"], int)
    assert timing["Route"] == "/api/public/establishments/{code}/search"
    assert timing["RequestLatency"] == 41.7
    assert timing["event"] == "metric"

    directive = count["_aws"]["CloudWatchMetrics"][0]
    assert directive["Dimensions"] == [[]]
    assert directive["Metrics"] == [{"Name": "TrackStarted", "Unit": "Count"}]
    assert count["TrackStarted"] == 1


def test_F004_R011_emf_usa_el_espacio_de_nombres_del_entorno() -> None:
    assert namespace_for("production") == "MyPlaylist/production"
    assert namespace_for("preproduction") == "MyPlaylist/preproduction"

    lines: list[str] = []
    EmfMetrics(namespace_for("preproduction"), write=lines.append).count("SearchUnavailable")

    [line] = lines
    assert json.loads(line)["_aws"]["CloudWatchMetrics"][0]["Namespace"] == (
        "MyPlaylist/preproduction"
    )
    # Los mismos campos sirven para meterlos en otra línea de registro, con su hora.
    fields = emf_fields("MyPlaylist/production", "RequestLatency", 3.0, "Milliseconds", {}, 1000)
    assert fields["_aws"]["Timestamp"] == 1000
    assert fields["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "MyPlaylist/production"


def test_F004_R011_emf_rechaza_dimensiones_fuera_de_route_y_service() -> None:
    lines: list[str] = []
    metrics = EmfMetrics("MyPlaylist/production", write=lines.append)

    for dimension in ("Establishment", "Device", "route"):
        with pytest.raises(ValueError, match="Route, Service"):
            metrics.count("TrackStarted", 1, **{dimension: "x"})
    with pytest.raises(ValueError, match="Establishment"):
        emf_fields("MyPlaylist/production", "X", 1, "Count", {"Establishment": "x"})

    # El nombre de la métrica tampoco puede pisar una dimensión ni el bloque de EMF.
    for name in ("Route", "Service", "_aws"):
        with pytest.raises(ValueError, match="nombre de métrica"):
            metrics.count(name)

    assert lines == []
    metrics.count("EventsRelayed", Service="realtime")
    assert json.loads(lines[0])["Service"] == "realtime"


def test_F004_R011_una_linea_por_metrica_en_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    # Con el escritor por defecto, el que usa producción.
    metrics = EmfMetrics("MyPlaylist/production")

    metrics.count("TrackStarted")
    metrics.timing("TrackGap", 120.0)

    out = capsys.readouterr().out
    assert out.endswith("\n")
    lines = out.splitlines()
    assert [
        next(iter(json.loads(line)["_aws"]["CloudWatchMetrics"][0]["Metrics"]))["Name"]
        for line in lines
    ] == ["TrackStarted", "TrackGap"]


def test_F004_R011_la_implementacion_en_memoria_guarda_lo_emitido() -> None:
    metrics = InMemoryMetrics()

    metrics.count("TrackFailed")
    metrics.count("TrackFailed", 2)
    metrics.timing("TrackGap", 850.0)

    assert metrics.values("TrackFailed") == [1, 2]
    assert metrics.recorded[-1] == Recorded("TrackGap", 850.0, "Milliseconds", {})
    with pytest.raises(ValueError, match="Device"):
        metrics.count("TrackStarted", Device="x")
