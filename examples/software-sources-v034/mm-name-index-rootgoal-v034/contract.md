# Keep shared name rules consistent across search and export

Deliver reusable `models.NameSchema`, `search.find_matches(names, query)`, and
`exporter.export_names(names)`. Each name and query contains only ASCII letters
and ordinary spaces; stripping leading/trailing spaces leaves a nonempty name.
The input sequence may be empty and may contain duplicates. Schema input has
exactly one `name` key. Extra fields and every other input shape are outside
this contract and are not acceptance cases.

The shared canonical rule is: remove leading/trailing spaces, lowercase ASCII
letters, and preserve interior spaces. `NameSchema.load` maps {"name": raw}
to a fresh {"name": canonical}; `NameSchema.dump` serializes that loaded form
to the same one-field dictionary. Both support Marshmallow's `many=True`.

`find_matches(names, query)` returns the zero-based indices whose canonical
name equals the canonical query, in original index order. `export_names(names)`
returns canonical name strings in original order, retaining duplicates. Each
nonempty consumer call must use the shared NameSchema load and dump results;
matching against its exported names must give the same indices as search.
Both functions return [] for an empty sequence. Preserve caller sequences and
objects. There is no sorting, fuzzy matching, punctuation or locale behavior.

For example, names [" Maple ", "OAK", "maple", "Blue Pine"] with query
" MAPLE " produce matches [0, 2] and export
["maple", "oak", "maple", "blue pine"]. This is the shared root behavior;
it does not assign module ownership or an order of work.

# Work and acceptance

The immutable root goal is shared by two equal executors. There are no assigned
execution tasks, module owners, or required communication patterns. Create and
revise your own work as useful; centralized completion and explicit publication
and import are both permitted. Each executor has a real private working copy.

The pinned Marshmallow source is read-only. Implement the named reusable schema
and application interfaces using its real API. `test_visible.py` checks the
public semantics below plus the same small upstream regression subset. Public
checks do not expose independent inputs or establish independent acceptance.
The full result requires the reusable API and all consumer results to agree with
this contract, along with unchanged caller inputs. Add exploratory checks only
to `test_member.py`. There is no CLI, filesystem service, network or persistence
to implement. No behavior outside the legal input domain below is assessed.
A fixed submission requires current-version public test execution and a fixed
patch; neither tool invocation nor submission implies acceptance.
