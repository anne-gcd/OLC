#!/usr/bin/env python3
import os
import sys
import re
import subprocess
import collections
from main import start, stop, s, o_min, a, max_length, readList


#----------------------------------------------------
# Graph class
#----------------------------------------------------
#Initializes a Graph object: a dictionary will be used for storing the nodes and their corresponding neighbouring nodes
class Graph:
    def __init__(self, graph_dict):          
        self.graph = graph_dict

    #return a list of the graph' nodes
    def nodes(self):
        nodes = []    
        for node in self.graph.keys():
            nodes.append(node)                     
        return nodes

    #return a list of the graph' edges, represented as a set, with one node (a loop back to the node) or two nodes and their overlapping length
    def edges(self):                        
        edges = []
        for node in self.graph:
            for neighbour in self.graph[node]:
                if [node, neighbour[0], neighbour[1]] not in edges:
                    edges.append([node, neighbour[0], neighbour[1]])
        return edges

    #create graph from the extension groups (e.g. reads sharing the same extension and overlapping with the source node)
    '''NB: add only the first read for each extension group, e.g. the read having the larger overlap'''
    def create_graph_from_extensions(self, source_node, extGroup):
        self.add_node(source_node)
        for reads in extGroup.values():
            self.add_node(reads[0][0])
            self.add_edge((source_node, reads[0][0], len(source_node)-reads[0][1]))

    #add the node 'node' to the graph if it's not already in the graph
    def add_node(self, node):                   
        if node not in self.graph:
            self.graph[node] = []

    #add an 'edge' between a node and its neighbours
    def add_edge(self, edge):         
        (source_node, neighbour, overlap) = edge
        #add an edge between the source_node, its neighbour node and their overlap length
        if source_node in self.graph:
            self.graph[source_node].append([neighbour, overlap])                                                 
        else:
            self.graph[source_node] = [[neighbour, overlap]]

    #return all the paths from the start_node to the end_node
    def find_all_paths(self, start_node, end_node, path, all_paths):          
        if start_node not in self.graph or end_node not in self.graph:
            return []
        #path found from end_node to start_node
        if end_node == start_node:
            path.reverse()
            all_paths.append(path)
            return
        #traverse the graph to find the path from end_node to start_node
        prev_nodes = []
        for node in self.graph:
            for neighbour in self.graph[node]:
                if end_node in neighbour:
                    prev_nodes.append(node)
        for node in prev_nodes:
            self.find_all_paths(start_node, node, path+[node], all_paths)
        return all_paths




#----------------------------------------------------
# reverse_complement function
#----------------------------------------------------
'''
To reverse complement a sequence:
    - it takes as input the sequence we want to reverse complement
    - it outputs the reverse complement's sequence of the input sequence
'''
def reverse_complement(S):  
    complement = {'A': 'T', 'C': 'G', 'G': 'C', 'T': 'A'} 
    return ''.join([complement[base] for base in S[::-1]])


#----------------------------------------------------
# index_reads function
#----------------------------------------------------
'''
To index a read by its seed:
    - it takes as input the sequence of the read, its position in readList (list containing all reads' sequences) and the seedDict dictionary it will output
    - it outputs a dictionary seedDict: key = seed's sequence ; value = list of positions of reads having this seed in readList
'''
def index_reads(read, i, seedDict):                
    #Index reads by their seed
    seed = read[:s]
    if seed in seedDict:
        seedDict[seed].append(str(i))           
    else:
        seedDict[seed] = [str(i)]

    #Index reverse complement of reads by their seed as well
    read_rc = reverse_complement(read)
    seed = read_rc[:s]
    if seed in seedDict:
        seedDict[seed].append("-"+str(i))
    else:
        seedDict[seed] = ["-"+str(i)]

    return seedDict


#----------------------------------------------------
# find_overlapping_reads function
#----------------------------------------------------
'''
To find the reads overlapping with the current assembly S sequence
    - it takes as input the current assembly's sequence (S), the read's sequence from which we want to extend and the seedDict dictionary
    - it outputs an overlapping_reads list containing all the overlapping reads' sequences, along with the index of the beginning of the overlap, referenced as [read's sequence, index of beginning of overlap]
      (NB: list sorted automatically by smallest i, e.g. by larger overlap and so by smallest extension)
'''
def find_overlapping_reads(S, read, seedDict):
    overlapping_reads = []

    #Get the putative reads (e.g. reads having a seed onto the S sequence)
    for i in range(len(S)-len(read)+1, len(S)-o_min-s):
        seed = S[i:i+s]
        if seed in seedDict:
            putative_reads = seedDict[seed]

            #For each putative read, search for an overlap between the S sequence and the putative read
            for put_read in putative_reads:
                nb_substitutions = 0
                l = i + s
                j = s
                length_overlap = 0

                #get the sequence of the read
                if '-' in str(put_read):
                    read = reverse_complement(readList[int(put_read.split('-')[1])])
                else:
                    read = readList[int(put_read)]

                while l < len(S) and j < len(read):
                    #match
                    if S[l] == read[j]:
                        l += 1
                        j += 1
                        length_overlap += 1
                    #mismatch
                    elif nb_substitutions < 2:              #error in reads: we allow 2 substitutions maximum
                        l += 1
                        j += 1
                        length_overlap += 1
                        nb_substitutions += 1
                    else:
                        break

                #Overlap found
                if l == len(S):
                    overlapping_reads.append([read, i])

    return overlapping_reads


#----------------------------------------------------
# extend function
#----------------------------------------------------
'''
To extend a read's sequence with overlapping reads
    - it takes as input the current assembly's sequence (S), the read's sequence from which we want to extend, the seedDict dictionary and the current graph to update
    - it outputs the gapfilled sequence (S) if found/or the reason why the gapfilled failed, and a Boolean variable representing the success of the gapfilling
extGroup = dictionary containing the extension's sequence as key, and the reads sharing this extension as value (value format: [read's sequence, index of beginning of overlap])
'''
def extend(S, read, seedDict, graph):
    #Base cases
    if stop in S[-len(read):]:
        print("Path found from kmer start to kmer stop !")
        graph.add_node(stop)
        graph.add_edge((read, stop, 0))
        return S, True

    if len(S) > max_length:
        return "|S| > max_length", False

    #Search for reads overlapping with the current assembly S sequence
    overlapping_reads = find_overlapping_reads(S, read, seedDict)
    if len(overlapping_reads) == 0:
        return "No overlapping reads", False

    #Group the overlapping reads by their extension
    extGroup = {}

    #add the smallest extension to extGroup
    i = overlapping_reads[0][1]
    min_ext = overlapping_reads[0][0][len(S)-i:]
    extGroup[min_ext] = [overlapping_reads[0]]

    #populate extGroup
    '''NB: overlapping_reads list sorted automatically by smallest extension'''
    added_to_extGroup = True
    for (read_seq, index) in overlapping_reads[1:]:
        if len(extGroup) == 1:
            if read_seq[len(S)-index:len(S)-index+len(min_ext)] == min_ext:
                extGroup[min_ext].append([read_seq, index])
            else:
                extGroup[read_seq[len(S)-index:]] = [[read_seq, index]]
        elif len(extGroup) > 1:
            for extension in extGroup:
                if read_seq[len(S)-index:len(S)-index+len(extension)] == extension:
                    extGroup[extension].append([read_seq, index])
                    added_to_extGroup = True
                    break
                else:
                    added_to_extGroup = False
            if added_to_extGroup == False:
                extGroup[read_seq[len(S)-index:]] = [[read_seq, index]]

    #Filter extGroup by the number of reads sharing an extension (argument '-a')
    for extension in list(extGroup.keys()):
        if len(extGroup[extension]) < a:
            del extGroup[extension]

    if len(extGroup) == 0:
        return "No extension", False

    #Sort extGroup by the maximum overlap (e.g. by the minimal extension)
    extGroup = collections.OrderedDict(sorted(extGroup.items(), key=lambda t: len(t[0])))

    #Create graph "à la volée"
    graph.create_graph_from_extensions(read, extGroup)

    #Iterative extension of the assembly's sequence S
    for extension in extGroup:
        res, success = extend(S+extension, extGroup[extension][0][0], seedDict, graph)
        if success:
            return res, True    
    return res, False




#TODO: check that if extension already in graph, do not gapfill again: actually, do gapfill again because the seq before ext could be different so not the same reads overlapping
#TODO: do not gapfill again if search on same region as one previously done (same nodes with same window length)
#TODO: use path to find all possible sequence (with only one stop in graph) ??
#TODO: add time for each step