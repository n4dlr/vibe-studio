"""Tests for Plugin Marketplace and Community Plugins."""
from __future__ import annotations

import pytest
from pathlib import Path
from vibe_studio.plugins.marketplace import PluginMarketplace


def test_marketplace_list_and_search(tmp_path):
    mp = PluginMarketplace(workspace_root=tmp_path)
    available = mp.list_available()
    assert len(available) >= 30

    devops_plugins = mp.search("DevOps")
    assert len(devops_plugins) >= 5

    docker_p = mp.search("docker")
    assert len(docker_p) >= 1
    assert docker_p[0]["name"] == "docker_deploy"


def test_marketplace_install_and_uninstall(tmp_path):
    mp = PluginMarketplace(workspace_root=tmp_path)

    # Install docker_deploy
    success = mp.install("docker_deploy")
    assert success is True

    dest_plugin = tmp_path / ".vibe_studio" / "plugins" / "docker_deploy.py"
    assert dest_plugin.exists()

    # Install kubernetes
    success_k8s = mp.install("kubernetes")
    assert success_k8s is True
    assert (tmp_path / ".vibe_studio" / "plugins" / "kubernetes.py").exists()

    # Uninstall docker_deploy
    uninstalled = mp.uninstall("docker_deploy")
    assert uninstalled is True
    assert not dest_plugin.exists()
