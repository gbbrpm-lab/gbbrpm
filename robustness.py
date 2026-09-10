import numpy as np, pandas as pd
from model import evaluate_gbbrpm
from metrics import spearman,topk,jaccard

def perturbation_trials(nodes,edges,pct=0.05,trials=100,seed=41,k=3):
    rng=np.random.default_rng(seed)
    baseline=evaluate_gbbrpm(nodes,edges)[0]; bt=topk(baseline,k)
    rows=[]
    for t in range(trials):
        n=nodes.copy(); e=edges.copy()
        mask=n.B>0
        if mask.any():
            n.loc[mask,"B"]=(n.loc[mask,"B"].to_numpy()*rng.uniform(1-pct,1+pct,int(mask.sum()))).clip(0,1)
        e["L"]=(e.L.to_numpy()*rng.uniform(1-pct,1+pct,len(e))).clip(0,None)
        e["C"]=(e.C.to_numpy()*rng.uniform(1-pct,1+pct,len(e))).clip(1e-9,None)
        r=evaluate_gbbrpm(n,e)[0]
        rows.append({"pct":pct,"trial":t,"seed":seed,"spearman":spearman(baseline,r),f"top{k}_jaccard":jaccard(bt,topk(r,k))})
    return pd.DataFrame(rows)

def summarize_robustness(df,k=3):
    c=f"top{k}_jaccard"
    return {"pct":float(df.pct.iloc[0]),"trials":len(df),"mean_spearman":float(df.spearman.mean()),
            "p05_spearman":float(df.spearman.quantile(.05)),"p95_spearman":float(df.spearman.quantile(.95)),
            f"mean_{c}":float(df[c].mean())}
