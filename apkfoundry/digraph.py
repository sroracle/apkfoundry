# SPDX-License-Identifier: MIT
# Copyright (c) 2017 Travis Thieman
# Copyright (c) 2018-2019 Max Rees
# Based on py-dag 3.0.1
# https://github.com/thieman/py-dag
# See LICENSE.dag for more information.
import collections   # deque, OrderedDict
import copy          # deepcopy

class DAGValidationError(Exception):
    pass

class Digraph:
    def __init__(self, cyclic_fatal=True):
        """
        .. class:: Digraph([cyclic_fatal=True])

           Construct a new directed graph with no nodes or edges.
           :param bool cyclic_fatal:
              If ``True``, the digraph represents a directed acyclic graph. If
              any cycles are detected when adding new edges,
              :exc:`DAGValidationError` will be raised.
        """
        self.reset_graph()
        self.cyclic_fatal = cyclic_fatal
        self.missing = set()

    def add_node(self, node, graph=None):
        """
        .. method:: Digraph.add_node(node, [graph=None])

           Add the given node to the graph. If the node already exists, raise
           :exc:`KeyError`.
        """
        if graph is None:
            graph = self.graph

        if node in graph:
            raise KeyError(f"Node '{node}' already exists in graph")
        graph[node] = set()

    def add_node_if_not_exists(self, node, graph=None):
        """
        .. method:: Digraph.add_node_if_not_exists(node, [graph=None])

           Add the given node if it is not already in the graph.
        """
        try:
            self.add_node(node, graph=graph)
        except KeyError:
            pass

    def delete_node(self, node, graph=None):
        """
        .. method:: Digraph.delete_node(node, [graph=None])

           Deletes the given node and all edges referencing it. Raises
           :exc:`KeyError` if the node does not exist.
        """
        if graph is None:
            graph = self.graph

        if node not in graph:
            raise KeyError(f"Node '{node}' is not in graph")

        graph.pop(node)

        for ignored_node, edges in graph.items():
            if node in edges:
                edges.remove(node)

    def delete_node_if_exists(self, node, graph=None):
        """
        .. method:: Digraph.delete_node_if_exists(node, [graph=None])

           Delete the given node from the graph (and all referring edges) if it
           exists.
        """
        try:
            self.delete_node(node, graph=graph)
        except KeyError:
            pass

    def add_edge(self, ind_node, dep_node, graph=None):
        """
        .. method:: Digraph.add_edge(ind_node, dep_node, [graph=None])

           Add an edge (dependency) between the specified nodes. If no cycles
           are introduced by this edge, return ``True``. If
           :attr:`.Digraph.cyclic_fatal` is ``True`` and the new edge
           would introduce a cycle, raise :exc:`.DAGValidationError`.
           Otherwise, return ``False``.

           :rtype: bool
        """
        if not graph:
            graph = self.graph
        if ind_node not in graph or dep_node not in graph:
            raise KeyError("One or both nodes do not exist in graph")

        test_graph = copy.deepcopy(graph)
        test_graph[ind_node].add(dep_node)

        if self.is_acyclic(test_graph):
            graph[ind_node].add(dep_node)
            return True

        if self.cyclic_fatal:
            raise DAGValidationError
        else:
            graph[ind_node].add(dep_node)
            return False

    def delete_edge(self, ind_node, dep_node, graph=None):
        """
        .. method:: Digraph.delete_edge(ind_node, dep_node, [graph=None])

           Delete an edge from the graph.
        """
        if not graph:
            graph = self.graph
        if dep_node not in graph.get(ind_node, []):
            raise KeyError("Edge does not exist")

        graph[ind_node].remove(dep_node)

    def predecessors(self, node, graph=None):
        """
        .. method:: Digraph.predecessors(node, [graph=None])

           Returns a list of all predecessors (dependencies) of the given node.
           :rtype: list
        """
        if graph is None:
            graph = self.graph

        return [key for key in graph if node in graph[key]]

    def downstream(self, node, graph=None):
        """
        .. method:: Digraph.downstream(node, [graph=None])

           Returns a list of all first level reverse dependencies of the given
           node (i.e. nodes that depend on this node).
           :rtype: list
        """
        if graph is None:
            graph = self.graph
        if node not in graph:
            raise KeyError(f"Node '{node}' is not in graph")

        return list(graph[node])

    def all_downstreams(self, node, graph=None):
        """
        .. method:: Digraph.all_downstreams(node, [graph=None])

           Returns a set of all nodes ultimately downstream of the given node
           in the dependency graph (i.e. ultimately depend on this node).
           :rtype: set
        """
        if graph is None:
            graph = self.graph

        nodes = [node]
        nodes_seen = set()
        i = 0
        while i < len(nodes):
            downstreams = self.downstream(nodes[i], graph)
            for downstream_node in downstreams:
                if downstream_node not in nodes_seen:
                    nodes_seen.add(downstream_node)
                    nodes.append(downstream_node)
            i += 1
        return nodes_seen

    def all_leaves(self, graph=None):
        """
        .. method:: Digraph.all_leaves([graph=None])

           Return a list of all leaves (nodes with no downstreams / reverse
           dependencies).
           :rtype: list
        """
        if graph is None:
            graph = self.graph

        return [key for key in graph if not graph[key]]

    def from_dict(self, graph_dict):
        """
        .. method:: Digraph.from_dict(graph_dict)

           Reset the graph and build it from the passed dictionary.
           :param dict graph_dict:
              The dictionary takes the form of ``{node: set(dependent nodes)}``
        """
        self.reset_graph()
        for new_node in graph_dict:
            self.add_node(new_node)

        for ind_node, dep_nodes in graph_dict.items():
            for dep_node in dep_nodes:
                self.add_edge(ind_node, dep_node)

    def reset_graph(self):
        """
        .. method:: Digraph.reset_graph()

           Restore the graph to an empty state.
        """
        self.graph = collections.OrderedDict()

    def ind_nodes(self, graph=None):
        """
        .. method:: Digraph.ind_nodes([graph=None])

           Returns a list of all nodes in the graph with no dependencies.
        """
        if graph is None:
            graph = self.graph

        dependent_nodes = set(
            node for dependents in graph.values() for node in dependents
        )
        return [node for node in graph.keys() if node not in dependent_nodes]

    def is_acyclic(self, graph=None):
        """
        .. method:: Digraph.is_acyclic([graph=None])

           Checks whether the graph is acyclic or not.
           :rtype: bool
        """
        graph = graph if graph is not None else self.graph
        if not self.ind_nodes(graph):
            return False
        try:
            self.topological_sort(graph)
        except DAGValidationError:
            return False
        return True

    def topological_sort(self, graph=None):
        """
        .. method:: Digraph.topological_sort([graph=None])

           If the digraph is a directed acyclic graph, return the topological
           ordering. If any cycles are detected, raise
           :exc:`.DAGValidationError`.
           :rtype: list
        """
        if graph is None:
            graph = self.graph

        in_degree = {}
        for u in graph:
            in_degree[u] = 0

        for u in graph:
            for v in graph[u]:
                in_degree[v] += 1

        queue = collections.deque()
        for u in in_degree:
            if in_degree[u] == 0:
                queue.appendleft(u)

        l = []
        while queue:
            u = queue.pop()
            l.append(u)
            for v in graph[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.appendleft(v)

        if len(l) == len(graph):
            return l

        raise DAGValidationError

    def size(self):
        """
        .. method:: Digraph.size()

           Return the number of nodes in the graph.
           :rtype: int
        """
        return len(self.graph)

