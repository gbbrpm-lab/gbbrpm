import numpy as np,pandas as pd
from model import evaluate_gbbrpm

def random_dag(rng,n=12,p=0.18):
    nodes=pd.DataFrame({"node":[f"v{i}" for i in range(n)],"B":rng.uniform(0,1,n)})
    rows=[]
    for i in range(n):
        for j in range(i+1,n):
            if rng.random()<p:
                C=float(rng.uniform(50,150)); L=float(rng.uniform(0,C*1.3))
                rows.append((f"v{i}",f"v{j}",C,L,1.0))
    if not rows: rows=[("v0","v1",100.0,50.0,1.0)]
    return nodes,pd.DataFrame(rows,columns=["source","target","C","L","tau"])

def run_property_tests(trials=100,seed=41):
    rng=np.random.default_rng(seed); rows=[]
    for t in range(trials):
        n,e=random_dag(rng); base,_=evaluate_gbbrpm(n,e)
        bounded=all(0<=x<=1 for x in base.values())
        idx=int(rng.integers(0,len(n))); node=str(n.iloc[idx].node)
        n2=n.copy(); n2.loc[n2.index[idx],"B"]=min(1.0,float(n2.iloc[idx].B)+0.1)
        inc,_=evaluate_gbbrpm(n2,e)
        monotone=all(inc[k]+1e-12>=base[k] for k in base)
        n3=n.copy(); n3.loc[n3.node.astype(str)==node,"B"]=1.0
        b1,_=evaluate_gbbrpm(n3,e); b1ok=abs(b1[node]-1)<1e-12
        e2=e.copy(); e2.loc[e2.index[0],"L"]=0.0
        _,q=evaluate_gbbrpm(n,e2)
        u,v=str(e2.iloc[0].source),str(e2.iloc[0].target)
        qr=q[(q.source==u)&(q.target==v)]
        s0ok=(len(qr)==1 and abs(float(qr.iloc[0].Q))<1e-12)
        rows.append({"trial":t,"bounded":bounded,"monotone_B":monotone,"B1_implies_R1":b1ok,"S0_gates_edge":s0ok})
    return pd.DataFrame(rows)
