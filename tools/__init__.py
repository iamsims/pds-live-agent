"""Tool functions and pydantic models backing the pydantic-ai PDS finder agent."""

from .inspect_collections import (
    PDSCollection,
    PDSGeoCollection,
    PDSGeoInspectCollectionsOutput,
    PDSInspectCollectionsOutput,
    pds_geo_inspect_collections,
    pds_inspect_collections,
)
from .list_dataset_dirs import (
    PDSDatasetDir,
    PDSGeoDatasetDir,
    PDSGeoListDatasetDirsOutput,
    PDSListDatasetDirsOutput,
    pds_geo_list_dataset_dirs,
    pds_list_dataset_dirs,
)
from .list_missions import (
    PDSGeoListMissionsOutput,
    PDSGeoMission,
    PDSListMissionsOutput,
    PDSMission,
    pds_geo_list_missions,
    pds_list_missions,
)
from .node_registry import (
    NODE_REGISTRY,
    NodeConfig,
    get_base_url,
    get_node_config,
)
from .probe_datasets import (
    PDSGeoProbeError,
    PDSGeoProbeDatasetsOutput,
    PDSGeoProbeResult,
    PDSProbeDatasetsOutput,
    PDSProbeError,
    PDSProbeResult,
    pds_geo_probe_datasets,
    pds_probe_datasets,
)

__all__ = [
    # node_registry
    "NodeConfig",
    "NODE_REGISTRY",
    "get_node_config",
    "get_base_url",
    # list_missions (new + compat)
    "PDSMission",
    "PDSListMissionsOutput",
    "pds_list_missions",
    "PDSGeoListMissionsOutput",
    "PDSGeoMission",
    "pds_geo_list_missions",
    # list_dataset_dirs (new + compat)
    "PDSDatasetDir",
    "PDSListDatasetDirsOutput",
    "pds_list_dataset_dirs",
    "PDSGeoDatasetDir",
    "PDSGeoListDatasetDirsOutput",
    "pds_geo_list_dataset_dirs",
    # probe_datasets (new + compat)
    "PDSProbeResult",
    "PDSProbeError",
    "PDSProbeDatasetsOutput",
    "pds_probe_datasets",
    "PDSGeoProbeResult",
    "PDSGeoProbeError",
    "PDSGeoProbeDatasetsOutput",
    "pds_geo_probe_datasets",
    # inspect_collections (new + compat)
    "PDSCollection",
    "PDSInspectCollectionsOutput",
    "pds_inspect_collections",
    "PDSGeoCollection",
    "PDSGeoInspectCollectionsOutput",
    "pds_geo_inspect_collections",
]
