"""Pre-outcome organizational opportunity: exclude mere setup completion."""
from .storage import digest,json_bytes
KEYS=('owner','mode','children','scope','depends_on')
def structure(g):
 return {t:{k:w.get(k,[]) if k in ('children','scope','depends_on') else w.get(k) for k in KEYS} for t,w in sorted(g['work'].items())}
def distinct_structure(state,candidate):return structure(state['graph'])!=structure(candidate['target'])
def admit_bank(bank,state):
 alternatives=[z for z,c in bank['candidates'].items() if z!='KEEP' and distinct_structure(state,c)]
 return {'qualified':bool(alternatives) and bank['remaining_branch_token_limit']>=2_000_000,'structural_alternatives':alternatives,'remaining_tokens':bank['remaining_branch_token_limit'],'reason':'pre_outcome_structural_opportunity' if alternatives else 'no_grounded_structural_alternative','no_scores_used':True}
