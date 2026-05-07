"""List known top-level mission/dataset directories on a PDS node.

For nodes with a mission layer (GEO), returns the hardcoded mission list
where each name is a top-level directory path.

For flat nodes with missions (PPI), returns the mission list where each
name is a **filter keyword** to use with ``list_dataset_dirs``.

For flat nodes without missions (LROC), returns an empty list with a
note directing the agent to use ``list_dataset_dirs`` directly.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .node_registry import get_node_config


class PDSMission(BaseModel):
    """One mission/entry directory on a PDS node."""

    name: str = Field(description="Top-level directory name on the node, or filter keyword for flat nodes")
    description: str = Field(description="Mission name, spacecraft, and key instruments")


# Backward-compat alias
PDSGeoMission = PDSMission


class PDSListMissionsOutput(BaseModel):
    """Output for pds_list_missions."""

    missions: list[PDSMission] = Field(description="Mission directories on the node")
    count: int = Field(description="Number of missions")
    note: str | None = Field(
        default=None,
        description="Usage guidance for this node",
    )


# Backward-compat alias
PDSGeoListMissionsOutput = PDSListMissionsOutput


def pds_list_missions(node: str = "geo") -> PDSListMissionsOutput:
    """Return the mission directories for a PDS node.

    For flat nodes without any mission entries (LROC), returns an empty
    list with a ``note`` telling the agent to use ``list_dataset_dirs``.
    """
    config = get_node_config(node)
    missions = [PDSMission(**m) for m in config.missions]

    if not missions:
        return PDSListMissionsOutput(
            missions=[],
            count=0,
            note=(
                f"Node '{node}' has no mission list. "
                f"Use pds_list_dataset_dirs(path='{config.data_root}', node='{node}') directly."
            ),
        )

    note = None
    if not config.has_mission_layer:
        note = (
            f"Node '{node}' has no mission sub-directories. "
            f"Use each mission 'name' as the filter keyword: "
            f"pds_list_dataset_dirs(path='{config.data_root}', node='{node}', filter='<name>')."
        )

    return PDSListMissionsOutput(missions=missions, count=len(missions), note=note)


# Backward-compat alias
pds_geo_list_missions = pds_list_missions
