import numpy as np
import pandas as pd

def summarize(risk,outlet=None,threshold=0.05):
    items=sorted(risk.items(),key=lambda kv:(-kv[1],kv[0]))
    vals=np.array(list(risk.values()),float)
    return {"max_risk":float(vals.max()),"mean_risk":float(vals.mean()),
            "affected_nodes":int((vals>threshold).sum()),
            "top_node":items[0][0],"top_3":"|".join(x[0] for x in items[:3]),
            "outlet_risk":float(risk[outlet]) if outlet in risk else np.nan}

def spearman(a,b):
    keys=sorted(set(a)&set(b))
    ra=pd.Series([a[k] for k in keys]).rank(method="average").to_numpy(float)
    rb=pd.Series([b[k] for k in keys]).rank(method="average").to_numpy(float)
    if np.std(ra)==0 or np.std(rb)==0:return float("nan")
    return float(np.corrcoef(ra,rb)[0,1])

def topk(r,k=3):
    return set(x[0] for x in sorted(r.items(),key=lambda kv:(-kv[1],kv[0]))[:k])

def jaccard(a,b):
    return 1.0 if not a and not b else len(a&b)/len(a|b)
