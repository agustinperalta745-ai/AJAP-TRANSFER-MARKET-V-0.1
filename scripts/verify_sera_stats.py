from sera_stats_authority_patch import EXPECTED_RECORDS, _load_official_payload, build_identity_map, _norm

payload = _load_official_payload()
records = payload["records"]
assert len(records) == EXPECTED_RECORDS, (len(records), EXPECTED_RECORDS)

identity, problems = build_identity_map()
if problems:
    raise SystemExit("SERA mapping problems:\n" + "\n".join(problems))
assert len(identity) == EXPECTED_RECORDS, len(identity)

checks = {
    "juan roman riquelme": ("Riquelme", 83, 98, 93),
    "huntelaar": ("Huntelaar", 85, None, None),
    "cahill": ("Cahill", None, None, None),
    "leo": ("Léo", None, None, None),
    "gardner": ("Gardner", None, None, None),
    "walker": ("Walker", None, None, None),
    "adriano": ("Adriano", None, None, None),
}
for roster_name, (pes_name, attack, short_pass, technique) in checks.items():
    record = identity.get(_norm(roster_name))
    assert record is not None, roster_name
    assert record["pes_name"] == pes_name, (roster_name, record["pes_name"], pes_name)
    if attack is not None:
        assert record["stats"]["attack"] == attack
    if short_pass is not None:
        assert record["stats"]["short_pass_accuracy"] == short_pass
    if technique is not None:
        assert record["stats"]["technique"] == technique

# Verify the five duplicate display names resolve to the exact surviving AJPA identity.
assert identity[_norm("Cahill")]["pes_club"] == "Merseyside Blue"
assert identity[_norm("Leo")]["pes_club"] == "Benfica"
assert identity[_norm("Gardner")]["pes_club"] == "Middlebrook"
assert identity[_norm("Walker")]["pes_club"] == "East London"
assert identity[_norm("Adriano")]["pes_club"] == "Sevilla F.C."

print(f"SERA mapping OK: {len(identity)}/{EXPECTED_RECORDS} AJPA players")
print("Riquelme:", identity[_norm("Juan Román Riquelme")])
