from vigia_connectors.bcra import BcraClient, ComunicacionBcra
from vigia_connectors.bocaba import BoCabaClient, BoCabaNorma
from vigia_connectors.bopba import BoPbaClient, BoPbaNorma
from vigia_connectors.bora import BoraAviso, BoraClient
from vigia_connectors.hcdn import HcdnClient, HcdnProyecto
from vigia_connectors.infoleg import InfoLegClient, InfoLegNorm
from vigia_connectors.senado import SenadoClient, SenadoProyecto

__all__ = [
    "InfoLegClient",
    "InfoLegNorm",
    "HcdnClient",
    "HcdnProyecto",
    "BoraClient",
    "BoraAviso",
    "BcraClient",
    "ComunicacionBcra",
    "BoCabaClient",
    "BoCabaNorma",
    "BoPbaClient",
    "BoPbaNorma",
    "SenadoClient",
    "SenadoProyecto",
]
