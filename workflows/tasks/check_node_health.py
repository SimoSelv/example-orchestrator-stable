# Copyright 2019-2026 SURF.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Health check workflow: verifica se i nodi sono raggiungibili."""

import socket
import subprocess

import structlog
from orchestrator import workflow
from orchestrator.targets import Target
from orchestrator.types import SubscriptionLifecycle
from orchestrator.workflow import StepList, done, init, step
from pydantic_forms.types import State

from products.product_types.node import Node
from services import netbox
from workflows.shared import subscriptions_by_product_type

logger = structlog.get_logger(__name__)


@step("Recupera nodi attivi")
def get_active_nodes() -> State:
    """Recupera tutti i nodi attivi dall'orchestrator e raccoglie le info da NetBox."""
    node_subscriptions = subscriptions_by_product_type(
        "Node", [SubscriptionLifecycle.ACTIVE]
    )

    if not node_subscriptions:
        raise ValueError("Nessun nodo attivo trovato nell'orchestrator")

    nodes = []
    for sub in node_subscriptions:
        node = Node.from_subscription(sub.subscription_id)
        device = netbox.get_device(id=node.node.ims_id)

        mgmt_ip = None
        if device.primary_ip4:
            mgmt_ip = str(device.primary_ip4).split("/")[0]

        nodes.append({
            "device_name": device.name,
            "mgmt_ip": mgmt_ip,
            "subscription_id": str(sub.subscription_id),
        })

        logger.info(
            "Nodo trovato",
            device_name=device.name,
            mgmt_ip=mgmt_ip,
            ims_id=node.node.ims_id,
        )

    return {"nodes": nodes}


@step("Esegui ping verso i nodi")
def ping_nodes(nodes: list) -> State:
    """Esegue un ping ICMP verso ogni nodo per verificare se è raggiungibile."""
    for node_info in nodes:
        device_name = node_info["device_name"]
        mgmt_ip = node_info["mgmt_ip"]

        if not mgmt_ip:
            logger.warning("Nessun IP di management configurato", device_name=device_name)
            node_info["ping_success"] = False
            node_info["ping_output"] = "Nessun IP di management configurato in NetBox"
            continue

        logger.info("Esecuzione ping", device_name=device_name, mgmt_ip=mgmt_ip)

        try:
            result = subprocess.run(
                ["ping", "-c", "3", "-W", "2", mgmt_ip],
                capture_output=True,
                text=True,
                timeout=15,
            )
            node_info["ping_success"] = result.returncode == 0
            node_info["ping_output"] = result.stdout if result.stdout else result.stderr
        except subprocess.TimeoutExpired:
            node_info["ping_success"] = False
            node_info["ping_output"] = "Ping command timed out after 15 seconds"
        except FileNotFoundError:
            # Il comando ping potrebbe non essere disponibile nel container
            node_info["ping_success"] = False
            node_info["ping_output"] = "Comando ping non disponibile nel sistema"

        logger.info("Risultato ping", device_name=device_name, success=node_info["ping_success"])

    return {"nodes": nodes}


@step("Verifica porta SSH")
def check_ssh_ports(nodes: list) -> State:
    """Verifica se la porta SSH (22) è aperta su ogni nodo."""
    for node_info in nodes:
        device_name = node_info["device_name"]
        mgmt_ip = node_info["mgmt_ip"]

        if not mgmt_ip:
            node_info["ssh_open"] = False
            continue

        logger.info("Verifica porta SSH", device_name=device_name, mgmt_ip=mgmt_ip)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((mgmt_ip, 22))
            node_info["ssh_open"] = result == 0
            sock.close()
        except Exception as e:
            logger.warning("Errore verifica SSH", error=str(e))
            node_info["ssh_open"] = False

        logger.info("Risultato SSH", device_name=device_name, ssh_open=node_info["ssh_open"])

    return {"nodes": nodes}


@step("Genera report di stato")
def generate_health_report(nodes: list) -> State:
    """Genera il report finale sullo stato di salute di tutti i nodi."""
    health_reports = []

    for node_info in nodes:
        ping_success = node_info.get("ping_success", False)
        ssh_open = node_info.get("ssh_open", False)

        if ping_success and ssh_open:
            status = "UP - Raggiungibile e SSH attivo"
        elif ping_success:
            status = "PARTIAL - Raggiungibile ma SSH non disponibile"
        else:
            status = "DOWN - Non raggiungibile"

        report = {
            "node_health_status": status,
            "device_name": node_info["device_name"],
            "management_ip": node_info["mgmt_ip"],
            "icmp_reachable": ping_success,
            "ssh_available": ssh_open,
        }

        logger.info("Health report generato", **report)
        health_reports.append(report)

    return {"health_reports": health_reports}


@workflow("Check Node Health", target=Target.SYSTEM)
def task_check_node_health() -> StepList:
    return (
        init
        >> get_active_nodes
        >> ping_nodes
        >> check_ssh_ports
        >> generate_health_report
        >> done
    )
