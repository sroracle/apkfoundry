# SPDX-License-Identifier: MIT
# Copyright (c) 2017 Travis Thieman
# Copyright (c) 2018-2020 Max Rees
# Based on py-dag 3.0.1
# https://github.com/thieman/py-dag
# See LICENSE.MIT for more information.
import collections # deque, OrderedDict
import logging     # getLogger
import subprocess  # PIPE, run

_LOGGER = logging.getLogger(__name__)

class DAGValidationError(Exception):
    def __init__(self, cycle):
        self.cycle = cycle
        super().__init__()

class Digraph:
    def __init__(self):
        """
        .. class:: Digraph()

           Construct a new directed graph with no nodes or edges.
        """
        self.reset_graph()

    def reset_graph(self):
        """
        .. method:: Digraph.reset_graph()

           Restore the graph to an empty state.
        """
        self.graph = collections.OrderedDict()

    def size(self):
        """
        .. method:: Digraph.size()

           Return the number of nodes in the graph.

           :rtype: int
        """
        return len(self.graph)

    def add_node(self, node):
        """
        .. method:: Digraph.add_node(node)

           Add the given node to the graph.
        """
        if node not in self.graph:
            self.graph[node] = set()

    def delete_node(self, node):
        """
        .. method:: Digraph.delete_node(node)

           Deletes the given node and all edges referencing it.
        """
        if node not in self.graph:
            return

        del self.graph[node]

        for edges in self.graph.values():
            if node in edges:
                edges.remove(node)

    def add_edge(self, ind_node, dep_node):
        """
        .. method:: Digraph.add_edge(ind_node, dep_node)

           Add an edge between the specified nodes. dep_node will depend
           on ind_node (thus ind_node is the dependency of dep_node, and
           dep_node is the reverse dependency of ind_node). In DAG
           terminology, it is said that the edge points from ind_node to
           dep_node.
        """
        self.add_node(ind_node)
        self.add_node(dep_node)
        self.graph[ind_node].add(dep_node)

    def delete_edge(self, ind_node, dep_node):
        """
        .. method:: Digraph.delete_edge(ind_node, dep_node)

           Delete an edge from the graph.
        """
        if dep_node not in self.graph.get(ind_node, []):
            return

        self.graph[ind_node].remove(dep_node)

    def predecessors(self, node):
        """
        .. method:: Digraph.predecessors(node)

           Returns a list of all predecessors (dependencies) of the given node.
           :rtype: list
        """
        return [i for i, j in self.graph.items() if node in j]

    def downstream(self, node):
        """
        .. method:: Digraph.downstream(node)

           Returns a list of all first level reverse dependencies of the
           given node (i.e. nodes that depend on this node). Raises
           :exc:`KeyError` if the node doesn't exist.

           :rtype: list
        """
        if node not in self.graph:
            raise KeyError(f"Node '{node}' is not in graph")

        return list(self.graph[node])

    def all_downstreams(self, node):
        """
        .. method:: Digraph.all_downstreams(node)

           Returns a set of all nodes ultimately downstream of the given
           node in the dependency graph (i.e. ultimately depend on this
           node). Raises :exc:`KeyError` if the node doesn't exist.

           :rtype: list
        """
        nodes = [node]
        nodes_seen = set()
        i = 0
        while i < len(nodes):
            downstreams = self.downstream(nodes[i])
            for downstream_node in downstreams:
                if downstream_node not in nodes_seen:
                    nodes_seen.add(downstream_node)
                    nodes.append(downstream_node)
            i += 1
        return list(nodes_seen)

    def all_leaves(self):
        """
        .. method:: Digraph.all_leaves()

           Return a list of all leaves (nodes with no downstreams /
           reverse dependencies).

           :rtype: list
        """
        return [i for i, j in self.graph.items() if not j]

    def ind_nodes(self):
        """
        .. method:: Digraph.ind_nodes()

           Returns a list of all nodes in the graph with no dependencies.

           :rtype: list
        """
        dependent_nodes = {k for j in self.graph.values() for k in j}
        return [i for i in self.graph if i not in dependent_nodes]

    def is_acyclic(self, exc=False):
        """
        .. method:: Digraph.is_acyclic([verbose=False])

           Checks whether the graph is acyclic or not.
           :param bool exc:
              If ``True``, return the exception instead of ``False`` on
              validation failure.

           :rtype: bool
        """
        if not self.ind_nodes():
            return False
        try:
            self.topological_sort()
        except DAGValidationError as e:
            _LOGGER.error("cycle detected: %s", " -> ".join(e.cycle))
            if exc:
                return e
            return False
        return True

    def topological_sort(self):
        """
        .. method:: Digraph.is_acyclic()

           Returns a topological sort of the nodes in the graph. Results
           are not deterministic. Raises :exc:`.DAGValidationError` if a
           dependency cycle is detected.

           :rtype: list
        """
        nodes = {i: 0 for i in self.graph}
        unvisited = [i for i, visited in nodes.items() if visited == 0]
        tsort = collections.deque()

        def visit(i, *ctx):
            if nodes[i] == 1:
                raise DAGValidationError((i, *ctx))

            if nodes[i] == 0:
                nodes[i] = 1
                for j in self.graph[i]:
                    visit(j, i, *ctx)
                nodes[i] = 2
                tsort.appendleft(i)

        while unvisited:
            i = unvisited.pop()
            visit(i)
            unvisited = [i for i, visited in nodes.items() if visited == 0]

        return tsort

def generate_graph(ignored_deps, skip_check=False, cont=None):
    graph = Digraph()
    args = ["af-deps"]
    if skip_check:
        args.append("-s")

    if cont:
        args[0] = "/af/libexec/af-deps"
        rc, proc = cont.run(
            args,
            stdout=subprocess.PIPE,
            encoding="utf-8",
            skip_rootd=True,
        )
    else:
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            encoding="utf-8",
        )
        rc = proc.returncode

    if rc != 0:
        _LOGGER.error("af-deps failed with status %d", rc)
        return None

    origins = {}
    deps = {}
    for line in proc.stdout.split("\n"):
        line = line.strip().split(maxsplit=2)
        if not line:
            continue

        assert len(line) == 3

        if line[0] == "o":
            name = line[1]
            startdir = line[2]
            origins[name] = startdir
            graph.add_node(startdir)
        elif line[0] == "d":
            startdir = line[1]
            name = line[2]
            if startdir not in deps:
                deps[startdir] = []
            deps[startdir].append(name)
        else:
            _LOGGER.error("invalid af-deps output: %r", line)
            return None

    for rdep, names in deps.items():
        graph.add_node(rdep)

        for name in names:
            if name not in origins:
                _LOGGER.warning("unknown dependency: %s", name)
                continue
            dep = origins[name]
            graph.add_node(dep)

            if dep == rdep:
                continue

            if [dep, rdep] in ignored_deps or [rdep, dep] in ignored_deps:
                continue

            graph.add_edge(dep, rdep)

    return graph
