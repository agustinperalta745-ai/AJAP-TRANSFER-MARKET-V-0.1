"""Cross-feature protections for active AJAP loans."""

import admin_visibility_patch
import clausulazo_patch as clauses
import data_consistency_patch
# Import early so AS Monaco wraps guild isolation before run_bot captures it.
import monaco_roster_patch  # noqa: F401


APP = None


def apply_loan_integrity_patch(runtime):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_loan_integrity_patch", False):
        return

    original_players_for_club = clauses.players_for_club
    original_search_players = clauses.search_players
    original_create_request = clauses.create_clause_request

    def available_for_clause(player):
        loan = runtime.active_loan_for_player(player["id"])
        return loan is None

    def players_for_club_without_loans(club):
        return [p for p in original_players_for_club(club) if available_for_clause(p)]

    def search_players_without_loans(term):
        return [p for p in original_search_players(term) if available_for_clause(p)]

    def protected_clause_request(interaction, ficha):
        loan = runtime.active_loan_for_player(ficha["id"])
        if loan:
            return False, (
                f"🔒 **{ficha['name']}** está cedido por **{loan['owner_club']}** a "
                f"**{loan['borrower_club']}**. No puede recibir un clausulazo mientras el préstamo esté activo."
            )
        return original_create_request(interaction, ficha)

    clauses.players_for_club = players_for_club_without_loans
    clauses.search_players = search_players_without_loans
    clauses.create_clause_request = protected_clause_request
    runtime._ajap_loan_integrity_patch = True

    # Final UI layer: regular players must not even see admin-only controls.
    admin_visibility_patch.apply_admin_visibility_patch(runtime, runtime.bot)

    # Final data layer: every menu reads the same persistent SQLite state with
    # WAL/busy-timeout protection and guarded list reads.
    data_consistency_patch.apply_data_consistency_patch(runtime)

    print("AJAP préstamos protegidos: jugadores cedidos excluidos de clausulazos")
