# Validate job policy and report the accepted work list

Deliver policy.validate_job(job, queues, ceiling) and
consumer.review_jobs(jobs, queues, ceiling), using the real schema package.
queues is a nonempty list of distinct lowercase ASCII names; ceiling is an
integer from 0 through 5. Each job has exactly queue (a lowercase ASCII name)
and priority (an integer from 0 through 9). A queue outside queues or a priority
above ceiling is a policy rejection, not an invalid input shape. Booleans, extra
fields and other input shapes are outside this contract. Jobs may repeat.

policy.validate_job constructs and uses schema.Schema.validate to enforce both
queue membership and 0 <= priority <= ceiling. Return the validated job record
when permitted and None on schema.SchemaError when the policy rejects it.
The record contains the same queue string and integer priority. No normalization
or default insertion is needed. Do not replace schema validation with a separate
hand-written validator.

consumer.review_jobs consumes policy.validate_job for each job and returns
{"accepted": [validated records in input order], "rejected_indices": [indices]}
with zero-based rejection indices in input order. Preserve duplicates and caller
objects. Empty jobs returns both lists empty. A rejection does not discard other
permitted jobs. For queues ["fast"], ceiling 2, jobs fast/2, slow/1, fast/4 accept
only fast/2 and reject indices [1, 2].

# Work and acceptance

This is one immutable root goal, not an execution task list. Two equal members
start with private copies and no assigned tasks or owners. Create, revise, claim
and coordinate your own work as useful. One member may complete everything;
communication, two-person editing and a particular work order are not required.

Only the declared application modules and test_member.py are editable. The real
pinned library, contract, public checks and supplied grammar assets are read-only.
Public checks cover the declared semantics plus a bounded original upstream
regression subset. Private acceptance uses different inputs under the same
contract. No behavior outside the declared legal input domain is assessed.
Use the stated real API and reusable product: calling a dummy API and ignoring
its result does not implement the contract. Preserve caller inputs including
JSON scalar types. Output types are exact; floats and booleans do not substitute
for required integers. A current tested fixed submission is needed, but saving
a submission is not independent acceptance. There is no CLI, network, persistent
service or external producer to build.
