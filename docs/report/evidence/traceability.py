"""Requirement -> test traceability table (Chapter 9.4 / 9.8).

    python docs/report/evidence/traceability.py

The mapping below was written by reading what each test asserts. The script
checks that every named test exists in the collected results and takes its
pass/fail status from the repeated full-suite runs in results/tests.json, so
the table cannot drift from the code. Requirements with no automated test are
listed as such, with the reason.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = HERE.parents[0] / "latex" / "generated"
BS = chr(92)

# requirement id -> (tests, kind)   kind: A automated | M automated + manual UI check | P partial | I inspection
MAP: dict[str, tuple[list[str], str]] = {
    "DIS-1": (["test_hello_is_broadcast_on_start"], "A"),
    "DIS-2": (["test_update_reports_new_neighbour_once", "test_get_and_snapshot", "test_neighbour_table_learns_public_key_from_hello", "test_perfect_reception_scores_one"], "A"),
    "DIS-3": (["test_neighbour_added_on_hello_received", "test_on_peer_up_fires_once_for_new_neighbour"], "A"),
    "DIS-4": (["test_neighbour_marked_dead_after_timeout", "test_prune_removes_only_stale_neighbours"], "A"),
    "DIS-5": (["test_perfect_reception_scores_one", "test_losing_every_other_hello_scores_about_half", "test_a_new_link_is_not_penalised_for_hellos_not_yet_due"], "A"),
    "DIS-6": (["test_message_to_discovered_neighbour_delivers_without_manual_next_hop", "test_snapshot_describes_a_converged_mesh"], "A"),
    "DIS-7": (["test_visible_neighbours_filters_unlisted_senders", "test_full_node_mesh_over_real_tcp_discovers_routes_and_delivers_with_ack"], "A"),
    "MSG-1": (["test_send_with_ack_delivers_and_gets_acknowledged", "test_send_to_an_unknown_destination_is_held_not_raised"], "A"),
    "MSG-2": (["test_rescue_dst_routes_to_gateway_across_multiple_hops", "test_rescue_dst_resolves_to_nearest_gateway"], "A"),
    "MSG-3": (["test_sos_reaches_the_rescue_queue_and_the_sender_sees_it_delivered"], "M"),
    "MSG-4": (["test_msg_id_defaults_to_uuid4_and_round_trips", "test_msg_id_is_16_bytes_on_wire"], "A"),
    "MSG-5": (["test_timestamp_is_uint64_milliseconds", "test_store_logs_sent_message_and_delivery_lifecycle"], "A"),
    "MSG-6": (["test_store_logs_sent_message_and_delivery_lifecycle", "test_sos_reaches_the_rescue_queue_and_the_sender_sees_it_delivered"], "M"),
    "MSG-7": (["test_update_message_route_records_hops_and_path", "test_node_view_reports_peers_with_hop_distance"], "M"),
    "FWD-1": (["test_two_hop_relay_a_to_b_to_c", "test_middle_node_auto_relays_across_a_chain"], "A"),
    "FWD-2": (["test_on_forward_hook_called_with_next_hop"], "A"),
    "FWD-3": (["test_drops_when_ttl_expired"], "A"),
    "FWD-4": (["test_on_forward_hook_called_with_next_hop", "test_two_hop_relay_a_to_b_to_c"], "A"),
    "FWD-5": (["test_drops_on_loop_detected"], "A"),
    "FWD-6": (["test_bad_magic_rejected", "test_truncated_header_rejected", "test_random_bytes_never_crash_the_parser", "test_node_survives_garbage_arriving_on_the_wire"], "A"),
    "FWD-7": (["test_relay_never_sees_plaintext_payload"], "A"),
    "RTE-1": (["test_send_report_reaches_each_neighbour", "test_send_report_includes_role_from_role_provider"], "A"),
    "RTE-2": (["test_receiving_report_merges_reported_edges_into_graph", "test_two_nodes_converge_on_each_others_graph_view"], "A"),
    "RTE-3": (["test_shortest_path_multi_hop_chain", "test_weighted_routing_avoids_lossy_shortcut"], "A"),
    "RTE-4": (["test_edge_cost_matches_section_8_2_formula", "test_recent_failures_also_penalise_a_link"], "A"),
    "RTE-5": (["test_record_failure_invalidates_cached_routes", "test_route_is_cached_until_invalidated", "test_killing_a_node_reroutes_and_reviving_restores_it"], "A"),
    "RTE-6": (["test_rescue_dst_resolves_to_nearest_gateway", "test_normal_node_role_not_treated_as_terminal", "test_receiving_report_teaches_learned_role"], "A"),
    "RTE-7": (["test_rescue_dst_picks_cheapest_of_multiple_gateways"], "A"),
    "RTE-8": (["test_report_reflooded_reaches_a_node_two_hops_away", "test_node_originates_a_message_three_hops_away_via_reflooded_gossip"], "A"),
    "PRI-1": (["test_all_three_priorities_ordered_correctly", "test_round_trip_all_message_types_and_priorities"], "A"),
    "PRI-2": (["test_sos_pops_before_normal_regardless_of_insertion_order"], "A"),
    "PRI-3": (["test_sos_forwarded_before_already_queued_normal", "test_sos_reapplied_mid_route_overtakes_already_queued_normal"], "A"),
    "PRI-4": (["test_ties_broken_by_oldest_timestamp_first"], "A"),
    "PRI-5": (["test_sos_reaches_the_rescue_queue_and_the_sender_sees_it_delivered"], "M"),
    "PRI-6": ([], "U"),
    "REL-1": (["test_drops_when_ttl_expired", "test_default_ttl_is_10", "test_on_forward_hook_called_with_next_hop"], "A"),
    "REL-2": (["test_entry_expires_after_window", "test_entry_still_duplicate_just_inside_window"], "A"),
    "REL-3": (["test_duplicate_delivery_is_dropped", "test_duplicate_forward_is_dropped_not_resent", "test_replayed_packet_is_delivered_only_once"], "A"),
    "REL-4": (["test_send_with_ack_delivers_and_gets_acknowledged", "test_ack_returns_over_the_path_the_data_took"], "A"),
    "REL-5": (["test_timeout_triggers_retry_and_resets_timer", "test_a_lost_ack_is_re_sent_when_the_sender_retries"], "A"),
    "REL-6": (["test_record_failure_updates_graph_immediately_not_just_on_next_report", "test_a_retry_crosses_relays_that_already_forwarded_the_original"], "A"),
    "REL-7": (["test_exhausting_max_retries_reports_failed_and_stops_tracking", "test_ack_never_arriving_exhausts_retries_and_queues_for_store_forward"], "A"),
    "REL-8": (["test_route_forgotten_when_neighbour_dies", "test_store_logs_peer_up_and_down", "test_a_dead_node_stops_being_reachable_once_its_neighbours_stop_reporting_it"], "A"),
    "SNF-1": (["test_send_without_route_queues_to_store_forward"], "A"),
    "SNF-2": (["test_store_forward_flushes_once_a_route_appears"], "A"),
    "SNF-3": (["test_store_forward_flushes_once_a_route_appears"], "P"),
    "SNF-4": (["test_enqueue_over_the_bound_evicts_lowest_priority", "test_store_forward_expires_messages_past_max_age", "test_default_max_count_matches_design_of_algorithms_c_max"], "A"),
    "SNF-5": (["test_enqueue_over_the_bound_evicts_lowest_priority", "test_eviction_never_displaces_sos_for_routine_traffic", "test_store_forward_evicts_lowest_priority_when_queue_is_full"], "A"),
    "SNF-6": ([], "U"),
    "SEC-1": (["test_encrypt_decrypt_round_trip", "test_encrypted_payload_decrypts_correctly_at_destination", "test_ciphertext_does_not_contain_plaintext"], "A"),
    "SEC-2": (["test_relay_never_sees_plaintext_payload"], "A"),
    "SEC-3": (["test_signed_message_verifies_and_delivers_one_hop", "test_signature_survives_multi_hop_relay_and_verifies_at_destination", "test_sign_verify_round_trip"], "A"),
    "SEC-4": (["test_forged_signature_is_rejected_not_delivered", "test_unknown_signer_is_rejected"], "A"),
    "SEC-5": (["test_forged_signature_is_rejected_not_delivered", "test_tampered_ciphertext_fails_gcm_tag_check", "test_wrong_session_key_is_rejected_not_delivered"], "A"),
    "SEC-6": (["test_hello_includes_public_key_when_configured", "test_receiving_report_teaches_learned_public_key"], "A"),
    "SEC-7": ([], "I"),
    "LOG-1": (["test_store_logs_forward_on_middle_node", "test_store_logs_sent_message_and_delivery_lifecycle"], "A"),
    "LOG-2": (["test_record_message_stores_path_as_comma_separated", "test_update_message_route_records_hops_and_path", "test_update_message_status"], "A"),
    "LOG-3": (["test_store_logs_peer_up_and_down", "test_store_logs_drop_reason", "test_events_by_kind"], "A"),
    "LOG-4": (["test_store_logs_forward_on_middle_node"], "I"),
    "LOG-5": (["test_list_and_count_messages_filter_by_direction_and_status"], "P"),
    "LOG-6": (["test_list_and_count_messages_filter_by_direction_and_status", "test_snapshot_describes_a_converged_mesh"], "A"),
    "DSH-1": (["test_snapshot_describes_a_converged_mesh"], "M"),
    "DSH-2": (["test_killing_a_node_reroutes_and_reviving_restores_it"], "M"),
    "DSH-3": (["test_sos_reaches_the_rescue_queue_and_the_sender_sees_it_delivered"], "M"),
    "DSH-4": (["test_sos_reaches_the_rescue_queue_and_the_sender_sees_it_delivered", "test_update_message_route_records_hops_and_path"], "M"),
    "DSH-5": (["test_snapshot_describes_a_converged_mesh"], "M"),
    "DSH-6": (["test_websocket_streams_a_hello_snapshot_then_events"], "M"),
}
NOTES = {
    "SNF-3": "Retained messages are retried every flush interval (10 s default); an immediate trigger on neighbour arrival is not implemented.",
    "LOG-5": "History and filter queries exist in the store; the device screens list recent messages but offer no filter control.",
    "PRI-6": "Priority badges are shown on the screens (manual check); no automated UI test.",
    "SNF-6": "The held-message count is shown on the screens (manual check); no automated UI test.",
    "SEC-7": "Code inspection: crypto.py only calls the cryptography library (AESGCM, Ed25519).",
    "LOG-4": "Forwarded rows have body NULL (Table~\\ref{tab:samples}); asserted for the relay's log, otherwise by inspection.",
}
KIND = {"A": "Automated", "M": "Automated + manual UI", "P": "Partial", "U": "Manual only", "I": "Inspection"}


def esc(t: str) -> str:
    return t.replace("&", BS + "&").replace("%", BS + "%").replace("_", BS + "_" + BS + "allowbreak{}")


def main() -> None:
    tests = json.loads((HERE / "results" / "tests.json").read_text(encoding="utf-8"))
    status = {}
    for c in tests["cases"]:
        status.setdefault(c["name"], []).append(c["status"])
    missing = sorted({t for ts, _ in MAP.values() for t in ts if t not in status})
    if missing:
        print("UNKNOWN TESTS:", missing)
        sys.exit(1)

    def verdict(ts):
        if not ts:
            return "--"
        st = [s for t in ts for s in status[t]]
        return "pass" if all(s == "passed" for s in st) else ("flaky" if "passed" in st else "FAIL")

    req = json.loads((HERE / "requirements.json").read_text(encoding="utf-8"))
    CODE = {"A": "Auto", "M": "Auto+UI", "P": "Partial", "U": "Manual", "I": "Inspect"}
    def sh(t):
        return esc(t).replace("::", "::" + BS + "allowbreak{}")
    lines = [BS + "begingroup" + BS + "scriptsize", BS + "setlength{" + BS + "tabcolsep}{3pt}",
             BS + "begin{longtable}{@{}p{0.95cm}p{6.6cm}p{1.15cm}p{8.6cm}@{}}",
             BS + "caption{Requirements (the system shall " + BS + "ldots), how each is verified, and the tests that verify it. Auto = automated tests; Auto+UI = automated tests plus a manual check of the screen; * = one mapped test was occasionally flaky; all other mapped tests passed in all " + str(len(tests["runs"])) + " complete runs}" + BS + BS,
             BS + "label{tab:trace}" + BS + BS,
             BS + "toprule " + BS + "textbf{ID} & " + BS + "textbf{Requirement} & " + BS + "textbf{Check} & " + BS + "textbf{Tests / note} " + BS + BS + " " + BS + "midrule " + BS + "endfirsthead",
             BS + "toprule " + BS + "textbf{ID} & " + BS + "textbf{Requirement} & " + BS + "textbf{Check} & " + BS + "textbf{Tests / note} " + BS + BS + " " + BS + "midrule " + BS + "endhead"]
    counts = {k: 0 for k in KIND}
    fails = 0
    for rid, (ts, kind) in MAP.items():
        counts[kind] += 1
        v = verdict(ts)
        fails += v in ("FAIL",)
        shown = ts[:2]
        body = ", ".join(BS + "texttt{" + sh(t) + "}" for t in shown)
        if len(ts) > 2:
            body += f" (+{len(ts) - 2})"
        if rid in NOTES:
            body = (body + " " if body else "") + BS + "textit{" + NOTES[rid] + "}"
        mark = "*" if v == "flaky" else ""
        text = esc(req.get(rid, "")).replace(BS + "_" + BS + "allowbreak{}", "_")
        lines.append(f"{rid} & {text} & {CODE[kind]}{mark} & {body} " + BS + BS)
    lines += [BS + "bottomrule", BS + "end{longtable}", BS + "endgroup"]
    (GEN / "traceability.tex").write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    total = len(MAP)
    auto = counts["A"] + counts["M"]
    summ = (f"{total} functional requirements: {counts['A']} verified by automated tests alone, {counts['M']} by automated tests plus a manual check of the screen, "
            f"{counts['P']} partially implemented, {counts['I']} by code inspection, {counts['U']} by manual check only.")
    (GEN / "trace_summary.tex").write_text(summ + "\n", encoding="utf-8")
    (GEN / "trace_numbers.tex").write_text(
        "".join(BS + f"providecommand{{{BS}{n}}}{{{v}}}" for n, v in (("NFR", total), ("NAuto", counts["A"]), ("NAutoUI", counts["M"]), ("NPartial", counts["P"]),
                                                                      ("NInspect", counts["I"]), ("NManual", counts["U"]))) + "\n", encoding="utf-8")
    print(summ)
    print("failing mapped tests:", fails)


if __name__ == "__main__":
    main()
