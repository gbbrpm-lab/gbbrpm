from pathlib import Path
import pandas as pd
import networkx as nx

def load_network(data_dir, network):
    d=Path(data_dir)
    n=pd.read_csv(d/f"{network}_nodes.csv")
    e=pd.read_csv(d/f"{network}_edges.csv")
    if "tau" not in e.columns: e["tau"]=1.0
    return n,e

def derive_susceptibility(edges):
    e=edges.copy()
    if (e.C<=0).any(): raise ValueError("C must be > 0")
    if (e.L<0).any(): raise ValueError("L must be >= 0")
    e["u"]=e.L/e.C
    e["S"]=e.u.clip(0,1)
    return e

def evaluate_gbbrpm(nodes, edges):
    e=derive_susceptibility(edges)
    G=nx.DiGraph()
    B={}
    for r in nodes.itertuples(index=False):
        b=float(r.B)
        if not 0<=b<=1: raise ValueError("B must be in [0,1]")
        node=str(r.node); G.add_node(node); B[node]=b
    lookup={}
    for r in e.itertuples(index=False):
        u,v=str(r.source),str(r.target)
        G.add_edge(u,v)
        lookup[(u,v)]={"S":float(r.S),"tau":float(r.tau),"L":float(r.L),"C":float(r.C),"u":float(r.u)}
    if not nx.is_directed_acyclic_graph(G): raise ValueError("GBBRPM v1 requires a DAG")
    risk={}; contrib=[]
    for j in nx.topological_sort(G):
        prod=1.0
        for i in G.predecessors(j):
            p=lookup[(i,j)]
            q=max(0.0,min(1.0,p["S"]*p["tau"]*risk[i]))
            prod*=1-q
            contrib.append({"source":i,"target":j,"R_source":risk[i],"S":p["S"],"tau":p["tau"],"Q":q,"L":p["L"],"C":p["C"],"u":p["u"]})
        risk[j]=max(0.0,min(1.0,1-(1-B[j])*prod))
    return risk,pd.DataFrame(contrib)
