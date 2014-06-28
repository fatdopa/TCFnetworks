#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 Frederik Elwert <frederik.elwert@web.de>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
This annotator implements cooccurrence networks as a TCF compatible service.

"""

import sys
import os
import logging
from itertools import combinations

from tcflib import tcf
from tcflib.service import run_as_cli

from tcfnetworks.annotators.base import TokenTestingWorker


class CooccurrenceWorker(TokenTestingWorker):

    __options__ = TokenTestingWorker.__options__.copy()
    __options__.update({
        'method': 'window',  # 'window', 'sentence' or 'textspan'
        'spantype': 'paragraph',
        'window': [2, 5],  # for method='window'
    })

    def __init__(self, **options):
        super().__init__(**options)
        try:
            self.build_graph = getattr(self,
                    'build_graph_{}'.format(self.options.method))
        except AttributeError:
            logging.error('Method "{}" is not supported.'.format(
                    self.options.method))
            sys.exit(-1)

    def add_annotations(self):
        graph = self.build_graph()
        logging.info('Graph has {} nodes and {} edges.'.format(
                len(graph.nodes),
                len(graph.edges)))
        self.corpus.graph = graph

    def get_unique_tokens(self, tokens):
        unique_tokens = []
        for token in tokens:
            if self.test_token(token):
                # Skip empty labels.
                if not str(getattr(token, self.options.label)):
                    continue
                # Skip entity tokens other than the first one.
                entity = token.named_entity
                if entity is not None:
                    if entity.get_value_list('tokenIDs')[0] != token.get('ID'):
                        continue
                unique_tokens.append(token)
        return unique_tokens

    def find_or_add_node(self, graph, token):
        nodes = graph.find(tcf.P_TEXT + 'nodes')
        label = str(getattr(token, self.options.label))
        node = nodes.find_node(label)
        if node is None:
            node = nodes.add_node(label)
        return node

    def add_or_increment_edge(self, graph, source_token, target_token,
                              unique=False):
        if unique:
            if (source_token, target_token) in self.combinations:
                logging.debug('Combination already present, skip.')
                return
        self.combinations.append((source_token, target_token))
        edges = graph.find(tcf.P_TEXT + 'edges')
        source_node, target_node = [self.find_or_add_node(graph, token)
                                      for token in (source_token, target_token)]
        # Prevent loops
        if source_node == target_node:
            return
        edge = edges.find_edge(source_node.get('ID'), target_node.get('ID'))
        if edge is None:
            # add edge
            edge = edges.add_edge(source_node.get('ID'), target_node.get('ID'),
                                  weight='1')
        else:
            # edge exists, increment weight
            edge.set('weight', str(int(edge.get('weight')) + 1))
        # TODO: Add edge instances

    def build_graph(self):
        logging.warn('No graph building method set.')

    def build_graph_window(self):
        """
        This method implements a word-window based cooccurrence network.

        This implementation is based on the method and algorithm described in:
        Paranyushkin, Dmitry. 2011. „Identifying the Pathways for Meaning 
        Circulation using Text Network Analysis“. Nodus Labs.
        <http://noduslabs.com/research/
        pathways-meaning-circulation-text-network-analysis/>.

        """
        # TODO: Take paragraphs into account.
        tokens = self.get_unique_tokens(self.corpus.tokens)
        graph = None
        for window in self.options.window:
            logging.info('Building network with window {}.'.format(window))
            graph = self.build_graph_window_real(tokens, window, graph)
        return graph

    def build_graph_window_real(self, tokens, window=2, graph=None):
        """
        This function does all the heavy-lifting of creating a graph from
        a list of words in a paragraph. It expects to get a list of tokens.

        :parameters:
            - `tokens`: A list of tokens.
            - `window`: The word window for detecting edges.
            - `graph`: A graph node to which the edges will be added.
        :returns:
            - The graph node.

        """
        if graph == None:
            graph = tcf.Element(tcf.P_TEXT + 'graph')
            nodes = tcf.SubElement(graph, tcf.P_TEXT + 'nodes')
            edges = tcf.SubElement(graph, tcf.P_TEXT + 'edges')
        else:
            nodes = graph.find(tcf.P_TEXT + 'nodes')
            edges = graph.find(tcf.P_TEXT + 'edges')
        for i in range(len(tokens) - (window - 1)):
            # try all combinations of words within window
            for a, b in combinations(tokens[i:i + window], 2):
                self.add_or_increment_edge(graph, a, b)
        return graph

    def build_graph_textspan(self):
        graph = tcf.Graph()
        textspans = [span for span in self.corpus.textstructure
                     if span.type == self.options.spantype]
        n = len(textspans)
        for i, span in enumerate(textspans, start=1):
            logging.debug('Creating network for textspan {}/{}.'.format(i, n))
            tokens = set([token for token in span.tokens
                          if self.test_token(token)])
            logging.debug('Using {} tokens.'.format(len(tokens)))
            for token in tokens:
                name = getattr(token, self.options.label)
                node = graph.node(name)
                if node is None:
                    node = graph.add_node(name, tokenIDs=[token.id])
                else:
                    if not token.id in node['tokenIDs']:
                        node['tokenIDs'].append(token.id)
            for combo in combinations(tokens, 2):
                names = [getattr(token, self.options.label)
                         for token in combo]
                graph.add_edge(*names)
        return graph

if __name__ == '__main__':
    run_as_cli(CooccurrenceWorker)
