from pathlib import Path
p=Path('/tmp/v054-interleave-session-r1/src/proworksim/software_benchmark_resident_session_v054.py');s=p.read_text();a=s.index('\ndef admitted_resident(')
helper='''
def interleaved_status(status):
    """Validate both isolated claims and the single dispatched numerical turn."""
    active = status.get("active_claims")
    sessions = status.get("sessions")
    if (status.get("resident") is not True or "poisoned" not in status
            or status["poisoned"] is not None or not isinstance(active, list)
            or not isinstance(sessions, dict) or len(active) > 2 or len(set(active)) != len(active)
            or any(not isinstance(claim, str) or not re.fullmatch(r"[a-f0-9]{32}", claim)
                   for claim in active)):
        raise ValueError("Invalid interleaved resident health or claim inventory")
    occupied = []
    for claim in active:
        entry = sessions.get(claim, {})
        slot = entry.get("session_slot")
        if (type(slot) is not int or slot not in (0, 1)
                or entry.get("phase") not in {"acquired", "collecting", "closing"}
                or any(value is not False and not isinstance(value, str)
                       for value in (entry.get("queued"), entry.get("dispatched")))):
            raise ValueError("An active interleaved claim lost its slot or turn identity")
        occupied.append(slot)
    if (len(set(occupied)) != len(occupied)
            or status.get("available_session_slots") != sorted({0, 1} - set(occupied))
            or status.get("state") != ("busy" if active else "idle")):
        raise ValueError("Interleaved slot availability differs from the active claims")
    inflight = status.get("inflight")
    dispatched = [(claim, sessions[claim]["dispatched"]) for claim in active
                  if sessions[claim]["dispatched"] is not False]
    if inflight is None:
        if dispatched:
            raise ValueError("A dispatched turn has no bound resident operation")
    elif (not isinstance(inflight, dict) or len(dispatched) != 1
          or (inflight.get("claim_id"), inflight.get("ticket_id")) != dispatched[0]
          or not isinstance(inflight.get("operation"), str)):
        raise ValueError("More than one turn, or an unbound turn, is executing")
    return list(active)


def require_interleaved_release(result, claim_id):
    proof = result.get("quiescence", {})
    if (result.get("state") != "released" or result.get("claim_id") != claim_id
            or any(proof.get(key) is not True for key in (
                "session_quiescent", "queued_removed", "learning_unchanged", "rng_restored_exactly",
                "session_rng_closed", "model_object_retained", "old_session_socket_removed",
                "resident_still_loaded"))
            or proof.get("own_inflight") != 0 or proof.get("weights_reloaded") is not False
            or not isinstance(proof.get("other_active_claims"), list)
            or claim_id in proof["other_active_claims"]
            or proof.get("resident_generator_active") == claim_id):
        raise ValueError("Interleaved release lacks this exact session's complete closure")
    return proof

'''
s=s[:a]+helper+s[a:]
needle='''    status = admin_client(declaration, identity).call("status") if query else None
    if status is not None:'''
repl='''    capacity = session_capacity(declaration, ready=ready, identity=identity)
    status = admin_client(declaration, identity).call("status") if query else None
    active_claims = None
    if status is not None:'''
assert needle in s;s=s.replace(needle,repl)
needle='''        if declaration["mode"] == "MATCH_PROJECT":
            # The raw-owner manager uses None'''
repl='''        if capacity == 2:
            active_claims = interleaved_status(status)
            healthy = True
        elif declaration["mode"] == "MATCH_PROJECT":
            # The raw-owner manager uses None'''
assert needle in s;s=s.replace(needle,repl)
needle='''        if not healthy:
            raise RuntimeError("Registered resident is poisoned or its health evidence is invalid; no automatic reuse")
    return {"declaration": declaration,'''
repl='''        if not healthy:
            raise RuntimeError("Registered resident is poisoned or its health evidence is invalid; no automatic reuse")
        if capacity == 1:
            active_claims = [status["active_claim"]] if status.get("active_claim") is not None else []
    return {"session_capacity": capacity, "active_claims": active_claims,
            "declaration": declaration,'''
assert needle in s;s=s.replace(needle,repl)
s=s.replace('''        if observed is not None and observed["status"].get("active_claim") is None:''','''        if observed is not None and len(observed["active_claims"]) < observed["session_capacity"]:''')
s=s.replace('''    else:
        proof = result.get("quiescence", {})
        if (result.get("state") != "released"''','''    elif session_capacity(declaration) == 2:
        require_interleaved_release(result, session["claim_id"])
    else:
        proof = result.get("quiescence", {})
        if (result.get("state") != "released"''',1)
needle='''    else:
        idle = (status.get("resident") is True and "poisoned" in status'''
repl='''    elif session_capacity(declaration) == 2:
        active = interleaved_status(status)
        own = status["sessions"].get(session["claim_id"])
        idle = (session["claim_id"] not in active and (own is None or (
            own.get("phase") == "closed" and own.get("queued") is False
            and own.get("dispatched") is False)))
    else:
        idle = (status.get("resident") is True and "poisoned" in status'''
assert needle in s;s=s.replace(needle,repl)
s=s.replace('''        raise ValueError("The released resident is not independently healthy and idle")''','''        raise ValueError("The released session is not independently closed in a healthy resident")''')
s=s.replace('''"resident_poison_skipped": "exact_released_session_and_live_idle",''','''"resident_poison_skipped": ("exact_released_session_and_live_own_claim_closed"
                          if session_capacity(declaration) == 2 else "exact_released_session_and_live_idle"),''')
needle='''    try:
        value["admin"] = admin_client(declaration, session["admin_identity"], timeout=2).call(
            "poison", claim_id=session["claim_id"], reason=reason)
    except BaseException as error:
        value["admin_error"] = {"type": type(error).__name__, "message": str(error)}
    # Unknown communication/usage cannot prove a generation has stopped.'''
repl='''    if session_capacity(declaration) == 2:
        client = admin_client(declaration, session["admin_identity"], timeout=2)
        try:
            aborted = client.call("abort_session", claim_id=session["claim_id"], reason=reason)
            if (aborted.get("claim_id") != session["claim_id"]
                    or type(aborted.get("shared_poisoned")) is not bool):
                raise ValueError("Session abort lost its exact claim/shared-fault identity")
            if aborted["shared_poisoned"] is False:
                if (aborted.get("session_aborted") is not True
                        or aborted.get("own_dispatched") is not False
                        or aborted.get("resident_still_loaded") is not True
                        or not isinstance(aborted.get("not_dispatched_receipts"), list)):
                    raise ValueError("Session-local abort lacks proof that no own turn is dispatched")
                for item in aborted["not_dispatched_receipts"]:
                    checked(item)
                value.update(poisoned=False, session_aborted=True, shared_poisoned=False,
                             admin=aborted, other_sessions_undisturbed=True)
                atomic_write(marker, json_bytes(value))
                return value
            value.update(admin=aborted, shared_poisoned=True)
        except BaseException as error:
            value["admin_error"] = {"type": type(error).__name__, "message": str(error)}
            try:
                # A fresh administrative client is permitted solely to close
                # dispatch; it never retries a numerical request.
                value["shared_guard"] = admin_client(
                    declaration, session["admin_identity"], timeout=2).call(
                        "poison_shared", reason="unproved_session_abort: " + reason)
            except BaseException as guard_error:
                value["shared_guard_error"] = {"type": type(guard_error).__name__, "message": str(guard_error)}
        try:
            value["suspended"] = suspend_registered(declaration, ready)
        except BaseException as error:
            value["suspension_error"] = {"type": type(error).__name__, "message": str(error)}
        atomic_write(marker, json_bytes(value))
        return value
    try:
        value["admin"] = admin_client(declaration, session["admin_identity"], timeout=2).call(
            "poison", claim_id=session["claim_id"], reason=reason)
    except BaseException as error:
        value["admin_error"] = {"type": type(error).__name__, "message": str(error)}
    # Unknown communication/usage cannot prove a generation has stopped.'''
assert needle in s;s=s.replace(needle,repl)
needle='''        self.lock = Path(declaration["session_lock_path"]).open("a+")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            client = admin_client(declaration, observed["identity"])
            acquired = client.call("acquire", slot=slot, claim_id=claim_id, authorization=authorization,
                                   host_process=process_identity(os.getpid()))'''
repl='''        self.lock, session_slot = lock_session_slot(declaration)
        capacity = observed["session_capacity"]
        try:
            client = admin_client(declaration, observed["identity"])
            extra = {"session_slot": session_slot} if capacity == 2 else {}
            acquired = client.call("acquire", slot=slot, claim_id=claim_id, authorization=authorization,
                                   host_process=process_identity(os.getpid()), **extra)'''
assert needle in s;s=s.replace(needle,repl)
needle='''            if acquired.get("claim_id") != claim_id:
                raise ValueError("Resident acquired a different claim nonce")
            self.session = {"version": VERSION,'''
repl='''            if acquired.get("claim_id") != claim_id:
                raise ValueError("Resident acquired a different claim nonce")
            if capacity == 2 and (acquired.get("session_slot") != session_slot
                    or acquired.get("session_protocol") != INTERLEAVE_PROTOCOL
                    or acquired.get("maximum_sessions") != 2):
                raise ValueError("Acquired resident session differs from its leased slot/protocol")
            self.session = {"session_slot": session_slot, "maximum_sessions": capacity,
                            "session_protocol": declaration.get("session_protocol"), "version": VERSION,'''
assert needle in s;s=s.replace(needle,repl)
needle='''            proof = result.get("quiescence", {})
            if (result.get("state") != "released" or proof.get("owner_idle") is not True
                    or proof.get("model_busy") is not False or proof.get("active_session") is not None
                    or proof.get("learning_unchanged") is not True or proof.get("rng_restored_exactly") is not True
                    or proof.get("weights_reloaded") is not False):
                raise ValueError("Raw owner release did not prove independent-window restoration")'''
repl='''            if session_capacity(session["resident_declaration"]) == 2:
                require_interleaved_release(result, session["claim_id"])
            else:
                proof = result.get("quiescence", {})
                if (result.get("state") != "released" or proof.get("owner_idle") is not True
                        or proof.get("model_busy") is not False or proof.get("active_session") is not None
                        or proof.get("learning_unchanged") is not True or proof.get("rng_restored_exactly") is not True
                        or proof.get("weights_reloaded") is not False):
                    raise ValueError("Raw owner release did not prove independent-window restoration")'''
assert needle in s;s=s.replace(needle,repl)
p.write_text(s)
