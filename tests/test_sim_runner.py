import pytest

from mesh.core.transport_sim import SimulatedNetwork
from sim.runner import build_chain_topology, build_full_mesh_topology, run_discovery_sim, summarize


def test_build_chain_topology_links_only_adjacent_nodes():
    net = SimulatedNetwork()
    build_chain_topology(net, ["N1", "N2", "N3"])
    assert net.linked("N1", "N2")
    assert net.linked("N2", "N3")
    assert not net.linked("N1", "N3")


def test_build_full_mesh_topology_links_every_pair():
    net = SimulatedNetwork()
    build_full_mesh_topology(net, ["N1", "N2", "N3"])
    assert net.linked("N1", "N2")
    assert net.linked("N1", "N3")
    assert net.linked("N2", "N3")


@pytest.mark.asyncio
async def test_chain_topology_discovers_only_direct_neighbours():
    net = SimulatedNetwork(seed=1)
    node_ids = ["N1", "N2", "N3"]
    build_chain_topology(net, node_ids)

    discoveries = await run_discovery_sim(
        node_ids, net, hello_interval=0.02, neighbour_timeout=1.0, duration=0.08
    )
    result = summarize(discoveries)

    assert result["N1"] == ["N2"]
    assert result["N2"] == ["N1", "N3"]
    assert result["N3"] == ["N2"]


@pytest.mark.asyncio
async def test_full_mesh_topology_discovers_all_other_nodes():
    net = SimulatedNetwork(seed=1)
    node_ids = ["N1", "N2", "N3"]
    build_full_mesh_topology(net, node_ids)

    discoveries = await run_discovery_sim(
        node_ids, net, hello_interval=0.02, neighbour_timeout=1.0, duration=0.08
    )
    result = summarize(discoveries)

    assert result["N1"] == ["N2", "N3"]
    assert result["N2"] == ["N1", "N3"]
    assert result["N3"] == ["N1", "N2"]


@pytest.mark.asyncio
async def test_visible_neighbours_map_restricts_discovery_within_a_linked_topology():
    net = SimulatedNetwork(seed=1)
    node_ids = ["N1", "N2", "N3"]
    build_full_mesh_topology(net, node_ids)  # everyone is in radio range...

    discoveries = await run_discovery_sim(
        node_ids,
        net,
        hello_interval=0.02,
        neighbour_timeout=1.0,
        duration=0.08,
        visible_neighbours_map={"N1": ["N2"]},  # ...but N1 only listens to N2
    )
    result = summarize(discoveries)

    assert result["N1"] == ["N2"]
    assert result["N2"] == ["N1", "N3"]
