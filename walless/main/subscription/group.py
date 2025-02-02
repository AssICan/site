from typing import *
import re
from dataclasses import dataclass
import yaml
from collections import defaultdict

from .clash_node import LogicNode, ProxyNode, InfoNode
from ..constants import PROVIDER_GROUPS, HEALTH_CHECK_CFGS
from .user_request import UserRequest

node_pattern = re.compile(r'([A-Z]{2}-[A-Za-z]+)(\d+)')


@dataclass
class Group(LogicNode):
    # group can also be used as clash node
    name: str
    nodes: List[LogicNode]
    key: str | None = None
    select_type: str = 'select'

    def provider_return(self):
        # return as a provider sub
        if self.nodes:
            entries = [node.clash() for node in self.nodes if isinstance(node, ProxyNode) or isinstance(node, InfoNode)]
        else:
            entries = [{'type': 'socks5', 'name': 'disabled', 'server': 'localhost', 'port': 1}]
        return yaml.dump({'proxies': entries}, default_flow_style=False)

    # behavior as a node
    def clash(self):
        return self.name

    def __repr__(self):
        return f'<Group {self.name}, {len(self.nodes)} nodes>'

    def clash_group(self, use_provider):
        if not use_provider:
            proxies = [node.name for node in self.nodes]
        else:
            proxies = [node.name for node in self.nodes if not (isinstance(node, ProxyNode) or isinstance(node, InfoNode))]
        entry = {
            'name': self.name,
            'type': self.select_type,
            'proxies': proxies,
        }
        if use_provider and self.key in PROVIDER_GROUPS:
            entry['use'] = [f'provider-{self.key}']
        else:
            if self.key in HEALTH_CHECK_CFGS:
                entry['url'] = HEALTH_CHECK_CFGS[self.key]['url']
        return entry
    
    def cluster_nodes(self, ur: UserRequest):
        if not ur.use_cluster:
            return self
        nodes = []
        # the clustering is name based
        clusters = defaultdict(list)
        for node in self.nodes:
            fetched = node_pattern.findall(node.name)
            if not fetched or not isinstance(node, ProxyNode):
                nodes.append(node)
                continue
            else:
                key = (fetched[0][0], node.ip_protocol)
                clusters[key].append(node)

        for key, cluster in clusters.items():
            # suppose k out of n nodes are selected, then the order of the first k
            # nodes will be used
            # e.g. we have nodes 3, 4, 5, 10, 12 and would like to select 2 nodes
            # the resultant nodes have the order 3 and 4, regardless what are selected
            cluster.sort()
            # TODO: make #nodes configurable
            node_orders = sorted([n.node_order for n in cluster])
            selected = weighted_sample(ur.rng, cluster, [n.node_weight for n in cluster], 2)
            for i, node in enumerate(selected):
                old_i = node_pattern.findall(node.name)[0][1]
                node.name = node.name.replace(f'{key[0]}{old_i}', f'{key[0]}{i+1}')
                node.node_order = node_orders[i]
            nodes.extend(selected)

        self.nodes = nodes


def weighted_sample(rng, items, weights, k):
    """
    Sample without replacement from items with weights
    """
    k = min(len(items), k)
    items, weights = items.copy(), weights.copy()
    ret = []
    while len(ret) < k:
        i = rng.choices(list(range(len(items))), weights, k=1)[0]
        ret.append(items.pop(i))
        weights.pop(i)
    return ret
